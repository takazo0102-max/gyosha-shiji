"""別の足場を単管でつなぐ（パレットの「単管でつなぐ」「火打ちの単管」「単管に壁つなぎ」）.

GLOOBE の「別の足場と接続する単管」に当たる（2026-11-02 の開発ループ）。平面で、つなぐ足場の支柱の芯から相手の足場の支柱の芯へ
線を引いて選んで押す（折れ線は区間ごとに1つ）。

  python3 scripts/tube_run.py                              # 高さ 1800 から 1800 おきに 3 段（--levels で直接も）
  python3 scripts/tube_run.py --first 1800 --pitch 1800 --n 5
  python3 scripts/tube_run.py --levels 1700,3400,5100      # つなぐ高さ mm（足場の立つ面から）
  python3 scripts/tube_run.py --guard                      # 各層の上に中桟 450・手すり 950（足場の間のすき間が開口のとき）
  python3 scripts/tube_run.py --brace                      # 層の間に斜めの単管（自在クランプ）
  python3 scripts/tube_run.py --z 0                        # 足場の立つ面の高さ mm（省くと地盤から）
  python3 scripts/tube_run.py --remove                     # 置いたつなぎを消す
  python3 scripts/tube_run.py --hiuchi                     # 火打ち: 3点の線（片方の面の支柱 → 隅の支柱 → もう片方の面の支柱）
  python3 scripts/tube_run.py --tie                        # 単管に壁つなぎ: 支柱から支柱への線と鉄骨柱を一緒に選ぶ
  python3 scripts/tube_run.py --tie --tie-at 900 --tie-len 300   # 柱を選ばずに、線の始めから 900 に・長さ 300 の壁つなぎ
  python3 scripts/tube_run.py --tie --double               # 単管を上下2本抱かせる（既定でも、1本で足りず2本で足りれば2本）

火打ち・単管に壁つなぎは GLOOBE 2026 の「単管の単独入力（火打ち）」「壁つなぎの単管配置」に当たる（2026-11-02）。壁つなぎは
部品 ashiba_tie を柱の位置・層ごとに1つ（+Y が柱の側）、単管は ashiba_tube。品（KS200〜KS1000 等）は条件の系列の部材マスタ
から柱の面までの長さで選ぶ。単管が壁つなぎの力を受けられるか（単純梁の曲げ）を帳票で確かめる.

部品 ashiba_tube を線（区間）に1つ（src/ashiba/tube_join.py が単管の長さ・判定・数量）。前に同じ線に置いたものは控え
（ashiba_out/単管でつなぐ.json）で消して置き直す。帳票は ashiba_out/単管でつなぐ.md（発注表）.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_tube"
TIE_PART = "ashiba_tie"
RECORD = "単管でつなぐ.json"


def selected_columns(c) -> list:
    """選んでいる柱 → [(芯 (x, y) mm, 幅, 奥行き, 向き（度）)]（長方形の柱。鉄骨の H 形・角形も外形の矩形で）."""
    from ashiba.column_form import column_from_details

    sel = c.get_selected_elements()
    out = []
    for d in (c.get_details(sel) if sel else []):
        if d.get("type") != "Column":
            continue
        col = column_from_details(d)
        if col:
            out.append((tuple(col["c"]), float(col["width"]), float(col["depth"]), float(col["ang"])))
    return out


def half_across(cc, w: float, d: float, ang: float, p0, p1) -> float:
    """柱の矩形の、線に直角の向きの半分の大きさ mm（柱の面までの長さを出す）."""
    L = math.dist(p0, p1) or 1.0
    nx, ny = -(p1[1] - p0[1]) / L, (p1[0] - p0[0]) / L
    a = math.radians(ang)
    return abs(w / 2.0 * (math.cos(a) * nx + math.sin(a) * ny)) + abs(d / 2.0 * (-math.sin(a) * nx + math.cos(a) * ny))


def levels_from(a) -> list[float]:
    if a.levels:
        return [float(v) for v in a.levels.replace("、", ",").split(",") if v.strip()]
    return [a.first + i * a.pitch for i in range(max(1, a.n))]


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from ashiba.tube_join import Join, columns_on, part_params, pick_tie, plan_join, report, tie_spots, tie_weight
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", default=None, help="つなぐ高さ mm（カンマ区切り。足場の立つ面から）")
    ap.add_argument("--first", type=float, default=1800.0, help="いちばん下の高さ mm（既定 1800）")
    ap.add_argument("--pitch", type=float, default=1800.0, help="層の高さ mm（既定 1800）")
    ap.add_argument("--n", type=int, default=3, help="段の数（既定 3）")
    ap.add_argument("--guard", action="store_true", help="各層の上に中桟・手すり")
    ap.add_argument("--brace", action="store_true", help="層の間に斜めの単管")
    ap.add_argument("--z", type=float, default=None, help="足場の立つ面の高さ mm（省くと地盤から）")
    ap.add_argument("--remove", action="store_true", help="置いたつなぎを消す")
    ap.add_argument("--hiuchi", action="store_true", help="火打ち（3点の線: 面の支柱 → 隅の支柱 → 面の支柱）")
    ap.add_argument("--tie", action="store_true", help="単管に壁つなぎ（支柱から支柱への線と鉄骨柱を選ぶ）")
    ap.add_argument("--tie-at", default=None, help="壁つなぎの位置 mm（線の始めから。カンマ区切り。柱を選ばないとき）")
    ap.add_argument("--tie-len", type=float, default=300.0, help="--tie-at の壁つなぎの長さ mm（柱の面まで。既定 300）")
    ap.add_argument("--tie-side", default="左", choices=("左", "右"), help="--tie-at の柱の側（線の向きの左か右。既定 左）")
    ap.add_argument("--double", action="store_true", help="壁つなぎを受ける単管を上下2本抱かせる")
    ap.add_argument("--single", action="store_true",
                    help="1本で壁つなぎの力が足りなくても2本にしない（既定は、足りなければ2本で足りるときは2本に）")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    try:                                                   # 平面図で置く（前面がレイアウトだと置けない・そこへ描く）
        from ashiba.elevation_sections import activate_floor_plan

        activate_floor_plan(c)
    except Exception:
        pass
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, list(rec.values()))
        rec_path.write_text("{}", encoding="utf-8")
        print(f"単管でつなぐ: {n}か所を消しました")
        return 0
    kind = "火打ち" if a.hiuchi else "壁つなぎ" if a.tie else "つなぎ"
    segs = []
    for key, pts, _closed in chains(selected_guides(c)):
        if a.hiuchi:
            # 3点ずつ（面の支柱・隅の支柱・面の支柱）。4点以上の折れ線は 0-1-2・2-3-4 …
            for i in range(0, len(pts) - 2, 2):
                segs.append((f"{key}:h{i}", tuple(pts[i]), tuple(pts[i + 2]), tuple(pts[i + 1])))
            continue
        for i, (p0, p1) in enumerate(zip(pts, pts[1:])):
            segs.append((f"{key}:{i}" if kind == "つなぎ" else f"{key}:t{i}", tuple(p0), tuple(p1), ()))
    if not segs:
        print({"火打ち": "火打ちの単管: 片方の面の支柱の芯 → 隅の支柱の芯 → もう片方の面の支柱の芯 の3点の線を引いて選んでから押してください",
               "壁つなぎ": "単管に壁つなぎ: 柱の両側の支柱の芯から芯へ線を引き、鉄骨柱と一緒に選んでから押してください"}.get(
            kind, "単管でつなぐ: つなぐ足場の支柱の芯から、相手の足場の支柱の芯へ線を引いて選んでから押してください"))
        return 1
    cols = selected_columns(c) if a.tie else []
    levels = levels_from(a)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, p0, p1, _q in segs for p in (p0, p1)])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    master = None
    if a.tie:
        from ashiba.master import load_master

        try:
            master = load_master(spec.get("series_id") or "nikken_nd1800")
        except Exception:
            master = load_master("nikken_nd1800")
        tie_part = R.versioned_part_name(TIE_PART)
        tie_pens = gdl_pens(parse_pens(spec.get("pens")), TIE_PART)
    joins = []
    for n, (key, p0, p1, corner) in enumerate(segs, 1):
        old = [g for k, g in rec.items() if k == key or k.startswith(key + "#")]
        if old:
            _delete_alive(c, [g for g in old])
            for k in [k for k in rec if k == key or k.startswith(key + "#")]:
                rec.pop(k)
        j = Join(f"{kind}{n}", p0, p1, levels, a.guard and kind == "つなぎ", a.brace, kind=kind, corner=corner, double=a.double)
        if a.tie:
            if a.tie_at:
                side = 1 if a.tie_side == "左" else -1
                j.ties = sorted((float(x), side, a.tie_len) for x in a.tie_at.replace("、", ",").split(",") if x.strip())
            else:
                j.ties = columns_on(j, [(cc, half_across(cc, w, d, ca, p0, p1)) for cc, w, d, ca in cols])
            j.tie_parts = [pick_tie(master, need) for _x, _s, need in j.ties]
            j.tie_kg = [tie_weight(master, nm) for nm in j.tie_parts]
        j = plan_join(j)
        weak = lambda jj: any(x.item == "壁つなぎ" and x.status == "WARN" for x in jj.checks)  # noqa: E731
        if a.tie and not a.double and not a.single and weak(j):
            # パレットからは --double を選べないので、1本で足りず2本で足りるなら2本に（2026-11-05 の全部のコマンドの試験から）
            j.double = True
            j = plan_join(j)
            if weak(j):
                j.double = False
                j = plan_join(j)
            else:
                print(f"{'単管に壁つなぎ'}: {j.name} 単管1本では壁つなぎの力（4.41kN）を受けられないので、上下2本を抱かせます（--single で1本）")
        z = a.z if a.z is not None else (min(ground(*p0), ground(*p1)) if ground else 0.0)
        el = _place(c, part, p0, z, math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])))
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(j), **pens}, PART)
        rec[key] = el["elementId"]["guid"]
        if a.tie:
            for k, sp in enumerate(tie_spots(j)):
                for lv in sorted(levels):
                    te = _place(c, tie_part, (sp["x"], sp["y"]), z, sp["faceAng"])
                    if te is None:
                        continue
                    c.set_gdl_parameters(te, {"faceAng": 0.0, "zH": lv / 1000.0, "tieL": sp["tieL"] / 1000.0, "wallD": 0.0,
                                              "steelD": 0.0, "tieName": sp["name"], "lineMode": False, **tie_pens}, TIE_PART)
                    rec[f"{key}#{k}:{lv:.0f}"] = te["elementId"]["guid"]
        joins.append(j)
        bad = [x.item for x in j.checks if x.status != "OK"]
        print(f"  {j.name}: 支柱の間 {j.span / 1000:.2f}m・" + (f"単管 {j.tube / 1000:.1f}M×{len(j.rows)}本" if j.tube else "単管が届かない")
              + (f"・壁つなぎ {len(j.ties)}か所×{len(levels)}段" if a.tie else "")
              + (f"・要確認 {'・'.join(dict.fromkeys(bad))}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / {"火打ち": "火打ちの単管.md", "壁つなぎ": "単管に壁つなぎ.md"}.get(kind, "単管でつなぐ.md")
    md.write_text(report(joins), encoding="utf-8")
    title = {"火打ち": "火打ちの単管", "壁つなぎ": "単管に壁つなぎ"}.get(kind, "単管でつなぐ")
    print(f"{title}: {len(joins)}か所に置きました（発注表: {md}）")
    # 要確認・NG は窓にも（「1か所に置きました」だけで、単管が壁つなぎの力を受けられない WARN が帳票にしか無かった 2026-11-05）
    for j in joins:
        for x in j.checks:
            if x.status != "OK":
                print(f"{title}: {j.name} {'要確認' if x.status == 'WARN' else x.status} {x.item} — {x.message.split('→')[0].strip()}"
                      + (f" → {x.message.split('→', 1)[1].strip().split('、')[0]}" if "→" in x.message else ""))
    return 0 if all(x.status != "NG" for j in joins for x in j.checks) else 2


if __name__ == "__main__":
    sys.exit(main())
