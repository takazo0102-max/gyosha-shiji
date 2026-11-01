"""仮囲い（パレットの「仮囲い」「仮囲いを消す」）.

利用者の指定（2026-11-01）「仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ」、
同日「ゲート 仮囲いに必要な部材リサーチして」→「全部入れて 3Dも詳細度上げて」（日建リース工業 仮設資材カタログ Vol.10）。

  python3 scripts/kakoi_run.py                      # 選んだ線・ポリライン（斜めの辺も）に沿って仮囲い
  python3 scripts/kakoi_run.py --boundary           # 線を選んでいなければ（付けなくても）敷地境界（足場条件か、レイヤー名に
                                                     #   敷地・境界・道路 のポリライン）から --inset だけ中に
  python3 scripts/kakoi_run.py --height 2000 --panel フラットパネル --found H形鋼
  python3 scripts/kakoi_run.py --height 4000 --panel 安全鋼板（パンチング） --found アンカー --wind 30
  python3 scripts/kakoi_run.py --gate 4000:5400:キャスター --gate 12000:7200:パネルキャスター:両開き --gate 20000:1000:ドア
                                                     # ポリラインの始めからの位置:幅:種類[:両開き|片開き]
  python3 scripts/kakoi_run.py --found 山留め --pile H-300 --pile-pitch 1200   # 選んだ山留め（壁）か線の親杭を継ぎ足して支柱に
                                                     #   （控えなし。根切りの側でなく地山の側＝道路の側にパネル）
  python3 scripts/kakoi_run.py --bottom 200         # パネルの下端を地盤から浮かす（既定 0＝日建の標準。-100 は根入れ）
  python3 scripts/kakoi_run.py --soil-n 10          # 打込みの杭の地盤の N値（風の検討。既定 20）
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
    from ashiba.hoarding import gate_kind

    parts = text.replace("：", ":").split(":")
    kind = "".join(parts[2:4]) if len(parts) > 2 and parts[2] else "キャスター"
    try:
        gate_kind(kind)
    except ValueError as e:
        raise SystemExit(str(e)) from None
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


def wall_chains(c, sel=None) -> tuple[list[tuple[str, list, bool]], float | None, list]:
    """選んだ山留め（壁）→ (山留めの線, 山留めの天端 mm, 壁の芯の線 [(始め, 終わり)])。地山（根切りの反対）の側を進む向きの右
    （パネルの側）にそろえ、角の合う壁はつなぐ。天端（親杭の頭）は地盤が読めないときの置く高さ."""
    from ashiba.wall_form import wall_from_details
    from excav_run import rail_lines

    sel = c.get_selected_elements() if sel is None else sel
    if not sel:
        return [], None, []
    walls = []
    for e, d in zip(sel, c.get_details(sel)):
        if d.get("type") == "Wall":
            w = wall_from_details(d)
            if w is not None:
                w["guid"] = e["elementId"]["guid"]
                walls.append(w)
    lines = rail_lines(walls)                        # 地山が左 → 逆に回して地山を右（パネルの側）に
    guides = [({"elementId": {"guid": w["guid"]}}, [(b, a)]) for (a, b, _z, _n), w in zip(lines, walls)]
    tops = [z for _a, _b, z, _n in lines]
    return (chains(guides) if guides else []), (max(tops) if tops else None), [(b, a) for a, b, _z, _n in lines]


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.hoarding import (FOUNDATION_ALIAS, FOUNDATIONS, PANELS, PILES, hoarding_plan, inset_polygon, offset_polyline,
                                 outside_is_right, panel_off, part_params, pile_ref, polyline_layout, report, split_gates,
                                 wind_limit)
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import building_plan, selected_guides

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--height", type=float, default=3000.0,
                    help="パネルの高さ（安全鋼板 2000・2300・3000・4000、フラットパネル 2000・3000。メッシュは 1800）")
    ap.add_argument("--panel", default="安全鋼板", choices=list(PANELS), help="パネルの種類")
    ap.add_argument("--found", default="打込み", choices=list(FOUNDATIONS) + list(FOUNDATION_ALIAS),
                    help="基礎（山留め＝山留め控え: 控えだけ親杭に取る、親杭支柱: 親杭を継ぎ足して支柱に）")
    ap.add_argument("--gate", action="append", default=[],
                    help="ゲート 位置:幅:種類[:両開き]（ポリラインの始めから mm。種類はキャスター・パネルキャスター・ローキャスター・"
                         "ドア・ワイドドア。ジャバラ＝キャスター）")
    ap.add_argument("--bottom", type=float, default=None, help="パネルの下端 mm（地盤から。既定 0、負は根入れ）")
    ap.add_argument("--soil-n", type=float, default=20.0, help="打込みの杭の地盤の N値（風の検討）")
    ap.add_argument("--pile", default="H-300", choices=list(PILES), help="山留めから取るときの親杭")
    ap.add_argument("--pile-pitch", type=float, default=1200.0, help="親杭の間隔 mm（山留めの図面の値）")
    ap.add_argument("--pile-top", type=float, default=0.0, help="親杭の天端 mm（地盤から。継ぎ足しはここから）")
    ap.add_argument("--wall-dist", type=float, default=1000.0,
                    help="山留め控え: 山留め（壁）だけ選んだときの仮囲いの芯から親杭の芯まで mm（線も選べば測る）")
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
    a.found = FOUNDATION_ALIAS.get(a.found, a.found)
    walled = False                                        # 線が山留め（地山の側を右にそろえてある）
    wall_lines: list = []
    wall_top = None
    w_chains: list = []
    if a.found in ("親杭支柱", "山留め控え"):
        w_chains, wall_top, wall_lines = wall_chains(c)
    lines = chains(selected_guides(c))
    if a.found == "親杭支柱" and w_chains:
        lines, walled = w_chains, True                    # 仮囲いは山留めの上
    elif a.found == "山留め控え" and w_chains and not lines:
        # 山留め（壁）だけ選んだ: 仮囲いの線は山留めから地山の側へ --wall-dist
        lines = [(k, offset_polyline(pts, a.wall_dist, closed), closed) for k, pts, closed in w_chains]
        walled = True
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
        if wall_lines and a.found == "山留め控え":          # 敷地の中＝根切りの中（山留めの重心）
            inside = (sum(x[0][0] + x[1][0] for x in wall_lines) / (2 * len(wall_lines)),
                      sum(x[0][1] + x[1][1] for x in wall_lines) / (2 * len(wall_lines)))
        right = (True if walled else outside_is_right(pts, inside)) != a.flip     # 山留めは地山の側を右にそろえてある
        segs = polyline_layout(pts, closed=closed, outside_right=right, off=panel_off(a.panel, a.found, a.pile))
        total = sum(sg.length for sg in segs)
        # ゲートの位置は線を引いた始めから。外を右にそろえるため逆に回したら測り直す
        gs = split_gates(segs, gates if right else [(total - g0 - w, w, k) for g0, w, k in gates])
        placed = []
        for i, (s, g) in enumerate(zip(segs, gs), 1):
            if s.length < 300.0:
                continue
            wd, x0 = pile_ref(s, wall_lines, a.pile_pitch) if a.found == "山留め控え" else (a.wall_dist, 0.0)
            if a.found == "山留め控え" and not wall_lines:
                wd = a.wall_dist
            p = hoarding_plan(f"{'敷地境界' if key == '敷地境界' else '線'}{len(plans) + 1}", s, a.height, a.panel, a.found, g,
                              a.brace_every, a.wind, ground, bottom=a.bottom, soil_n=a.soil_n, pile=a.pile,
                              pile_pitch=a.pile_pitch, pile_top=a.pile_top, wall_dist=wd, pile_x0=x0)
            z = a.z if a.z is not None else (ground(*s.p0) if ground else (wall_top if wall_top is not None
                                                                         and a.found in ("親杭支柱", "山留め控え") else 0.0))
            el = _place(c, part, s.p0, z, s.angle)
            if el is None:
                continue
            c.set_gdl_parameters(el, {**part_params(p), **pens})
            placed.append(el["elementId"]["guid"])
            plans.append(p)
            made += 1
            print(f"  {p.name}: 長さ {s.length:.0f}・向き {s.angle:.1f}°・支柱 {len(p.posts)}本・パネル上端 {p.top:.0f}"
                  + (f"・ゲート {len(g)}" if g else "") + (f"・持つ風速 約 {wind_limit(p):.0f}m/s" if p.wind else ""))
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
