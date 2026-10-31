"""仮囲い（パレットの「仮囲い」「仮囲いを消す」）.

利用者の指定（2026-11-01）「仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ」。

  python3 scripts/kakoi_run.py                      # 選んだ線・ポリライン（斜めの辺も）に沿って仮囲い
  python3 scripts/kakoi_run.py --boundary           # 線を選んでいなければ（付けなくても）敷地境界（足場条件か、レイヤー名に
                                                     #   敷地・境界・道路 のポリライン）から --inset だけ中に
  python3 scripts/kakoi_run.py --height 2000 --panel フラットパネル --found H形鋼
  python3 scripts/kakoi_run.py --gate 4000:3600:キャスター --gate 15000:900:ドア   # ポリラインの始めからの位置:幅:種類
  python3 scripts/kakoi_run.py --flip               # 外（パネル）と中（控え）を入れ替える
  python3 scripts/kakoi_run.py --remove             # 置いた仮囲いを消す

部品 ashiba_kakoi を区間ごとに1つ（src/ashiba/hoarding.py が割付・数量・検定）。外（道路の側）は建物の配置の控えか閉じた形の
中から決める（無ければ線を引いた向きの右）。地盤は敷地メッシュがあれば支柱ごとに読む（高低差・傾斜地）。前に同じ線に置いたものは
控え（ashiba_out/仮囲い.json）で消して置き直す。数量と検定は ashiba_out/仮囲い.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_kakoi"
RECORD = "仮囲い.json"


def _gate(text: str) -> tuple[float, float, str]:
    from ashiba.hoarding import GATES

    parts = text.replace("：", ":").split(":")
    kind = parts[2] if len(parts) > 2 and parts[2] else "キャスター"
    if kind not in GATES:
        raise SystemExit(f"ゲートの種類は {'・'.join(GATES)} のどれか（{text}）")
    return float(parts[0]), float(parts[1]) if len(parts) > 1 else 3600.0, kind


def chains(guides) -> list[tuple[str, list, bool]]:
    """選んだ線・ポリライン → [(控えの鍵, 点列, 閉じているか)]。端のつながる線はつなぐ（斜めの線も）."""
    out, loose = [], []
    for el, segs in guides:
        key = el["elementId"]["guid"] if isinstance(el, dict) else str(el)
        pts = [segs[0][0]] + [b for _a, b in segs]
        if len(segs) > 1 or len(guides) == 1:
            out.append((key, pts, len(pts) > 3 and math.dist(pts[0], pts[-1]) < 10.0))
        else:
            loose.append((key, pts))
    while loose:                                          # 1本ずつの線は端が 10mm 以内ならつなぐ
        key, pts = loose.pop(0)
        grown = True
        while grown:
            grown = False
            for j, (k2, q) in enumerate(loose):
                for qq in (q, q[::-1]):
                    if math.dist(pts[-1], qq[0]) < 10.0:
                        pts, key = pts + qq[1:], key + "+" + k2
                    elif math.dist(pts[0], qq[-1]) < 10.0:
                        pts, key = qq[:-1] + pts, key + "+" + k2
                    else:
                        continue
                    loose.pop(j)
                    grown = True
                    break
                if grown:
                    break
        out.append((key, pts, len(pts) > 3 and math.dist(pts[0], pts[-1]) < 10.0))
    return out


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.hoarding import (FOUNDATIONS, PANELS, hoarding_plan, inset_polygon, outside_is_right, part_params,
                                 polyline_layout, report, split_gates)
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import building_plan, selected_guides

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--height", type=float, default=3000.0, help="パネルの高さ（2000・3000。メッシュは 1800）")
    ap.add_argument("--panel", default="安全鋼板", choices=list(PANELS), help="パネルの種類")
    ap.add_argument("--found", default="打込み", choices=list(FOUNDATIONS), help="基礎")
    ap.add_argument("--gate", action="append", default=[], help="ゲート 位置:幅:種類（ポリラインの始めから mm。種類はキャスター・ジャバラ・ドア）")
    ap.add_argument("--brace-every", type=int, default=1, help="控えを何本の支柱ごとに（1＝全部・2＝1本おき）")
    ap.add_argument("--wind", type=float, default=25.0, help="設計風速 m/s")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--boundary", action="store_true", help="敷地境界から（線を選んでいなければ同じ）")
    ap.add_argument("--inset", type=float, default=150.0, help="敷地境界から支柱の芯まで mm")
    ap.add_argument("--flip", action="store_true", help="外（パネル）と中（控え）を入れ替える")
    ap.add_argument("--remove", action="store_true", help="置いた仮囲いを消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, [g for v in rec.values() for g in v])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"仮囲い: {n}個を消しました")
        return 0
    gates = [_gate(t) for t in a.gate]
    lines = chains(selected_guides(c))
    if not lines:                                         # 線を選んでいなければ敷地境界から
        spec = {**R.SPEC, **R.load_spec_override()}
        bnd = [tuple(map(float, p)) for p in (spec.get("site_boundary_mm") or [])]
        if not bnd:
            from ashiba.site_boundary import read_boundary_from_archicad

            plan = building_plan([(0.0, 0.0)]) or {}
            bnd, _roads = read_boundary_from_archicad(c, plan.get("outline_mm") or [])
        if len(bnd) >= 3:
            lines = [("敷地境界", inset_polygon(bnd, a.inset), True)]
    if not lines:
        print("仮囲い: 仮囲いの線（線・ポリライン。斜めでも）を選んでから押してください（--boundary で敷地境界から）")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts, _c in lines for p in pts])
        if getattr(gm, "points", None):
            ground = gm.elevation_at
    plans, made = [], 0
    for key, pts, closed in lines:
        if key in rec:
            _delete_alive(c, rec.pop(key))
        plan = building_plan(pts)
        inside = None
        if plan and plan.get("outline_mm"):
            ol = plan["outline_mm"]
            inside = (sum(float(p[0]) for p in ol) / len(ol), sum(float(p[1]) for p in ol) / len(ol))
        right = outside_is_right(pts, inside) != a.flip
        segs = polyline_layout(pts, closed=closed, outside_right=right)
        total = sum(sg.length for sg in segs)
        # ゲートの位置は線を引いた始めから。外を右にそろえるため逆に回したら測り直す
        gs = split_gates(segs, gates if right else [(total - g0 - w, w, k) for g0, w, k in gates])
        placed = []
        for i, (s, g) in enumerate(zip(segs, gs), 1):
            if s.length < 300.0:
                continue
            p = hoarding_plan(f"{'敷地境界' if key == '敷地境界' else '線'}{len(plans) + 1}", s, a.height, a.panel, a.found, g,
                              a.brace_every, a.wind, ground)
            z = a.z if a.z is not None else (ground(*s.p0) if ground else 0.0)
            el = _place(c, part, s.p0, z, s.angle)
            if el is None:
                continue
            c.set_gdl_parameters(el, {**part_params(p), **pens})
            placed.append(el["elementId"]["guid"])
            plans.append(p)
            made += 1
            print(f"  {p.name}: 長さ {s.length:.0f}・向き {s.angle:.1f}°・支柱 {len(p.posts)}本・パネル上端 {p.top:.0f}"
                  + (f"・ゲート {len(g)}" if g else ""))
        rec[key] = placed
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "仮囲い.md"
    md.write_text(report(plans), encoding="utf-8")
    print(f"仮囲い: {made}区間を置きました（数量と検定: {md}）")
    for p in plans:
        for ck in p.checks:
            if ck.status != "OK":
                print(f"  {ck.status} {p.name} {ck.item}: {ck.message}")
    return 0 if all(p.ok for p in plans) else 2


if __name__ == "__main__":
    sys.exit(main())
