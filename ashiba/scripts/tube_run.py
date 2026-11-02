"""別の足場を単管でつなぐ（パレットの「単管でつなぐ」「単管のつなぎを消す」）.

GLOOBE の「別の足場と接続する単管」に当たる（2026-11-02 の開発ループ）。平面で、つなぐ足場の支柱の芯から相手の足場の支柱の芯へ
線を引いて選んで押す（折れ線は区間ごとに1つ）。

  python3 scripts/tube_run.py                              # 高さ 1800 から 1800 おきに 3 段（--levels で直接も）
  python3 scripts/tube_run.py --first 1800 --pitch 1800 --n 5
  python3 scripts/tube_run.py --levels 1700,3400,5100      # つなぐ高さ mm（足場の立つ面から）
  python3 scripts/tube_run.py --guard                      # 各層の上に中桟 450・手すり 950（足場の間のすき間が開口のとき）
  python3 scripts/tube_run.py --brace                      # 層の間に斜めの単管（自在クランプ）
  python3 scripts/tube_run.py --z 0                        # 足場の立つ面の高さ mm（省くと地盤から）
  python3 scripts/tube_run.py --remove                     # 置いたつなぎを消す

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
RECORD = "単管でつなぐ.json"


def levels_from(a) -> list[float]:
    if a.levels:
        return [float(v) for v in a.levels.replace("、", ",").split(",") if v.strip()]
    return [a.first + i * a.pitch for i in range(max(1, a.n))]


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from ashiba.tube_join import Join, part_params, plan_join, report
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
    a = ap.parse_args(argv)
    c = ArchicadClient()
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
    segs = []
    for key, pts, _closed in chains(selected_guides(c)):
        for i, (p0, p1) in enumerate(zip(pts, pts[1:])):
            segs.append((f"{key}:{i}", tuple(p0), tuple(p1)))
    if not segs:
        print("単管でつなぐ: つなぐ足場の支柱の芯から、相手の足場の支柱の芯へ線を引いて選んでから押してください")
        return 1
    levels = levels_from(a)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, p0, p1 in segs for p in (p0, p1)])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    joins = []
    for n, (key, p0, p1) in enumerate(segs, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)])
        j = plan_join(Join(f"つなぎ{n}", p0, p1, levels, a.guard, a.brace))
        z = a.z if a.z is not None else (min(ground(*p0), ground(*p1)) if ground else 0.0)
        el = _place(c, part, p0, z, math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])))
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(j), **pens}, PART)
        rec[key] = el["elementId"]["guid"]
        joins.append(j)
        bad = [x.item for x in j.checks if x.status != "OK"]
        print(f"  {j.name}: 支柱の間 {j.span / 1000:.2f}m・単管 {j.tube / 1000:.1f}M×{len(j.rows)}本"
              + (f"・要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "単管でつなぐ.md"
    md.write_text(report(joins), encoding="utf-8")
    print(f"単管でつなぐ: {len(joins)}か所に置きました（発注表: {md}）")
    return 0 if all(x.status != "NG" for j in joins for x in j.checks) else 2


if __name__ == "__main__":
    sys.exit(main())
