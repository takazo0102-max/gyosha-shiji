"""親綱と親綱支柱（パレットの「親綱」）.

利用者の指定（2026-11-01）「親綱と親綱支柱も追加して」。

  python3 scripts/lifeline_run.py                     # 選んだ鉄骨梁（選んでいなければ全部の梁）の上に親綱支柱と親綱
  python3 scripts/lifeline_run.py --post alpa         # アルミ製親綱支柱 ALPA12（つかみ厚 50mm まで。既定は NTP）
  python3 scripts/lifeline_run.py --flange 22         # 上フランジの厚さ mm（ALPA12 のつかみ厚を見る）
  python3 scripts/lifeline_run.py --top 12000 --drop 8000   # 梁でなく線を選んだとき: 梁の上端と下の床までの落差 mm
  python3 scripts/lifeline_run.py --remove            # 置いた親綱を消す

部品 ashiba_lifeline を梁（線）に1つ（src/ashiba/lifeline.py が割付・判定・数量）。落差は梁の真ん中から下の床（床の穴は除く）か
地盤まで。前に同じ梁に置いたものは控え（ashiba_out/親綱.json）で消して置き直す。帳票は ashiba_out/親綱.md（発注表）.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_lifeline"
RECORD = "親綱.json"


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.beams import beam_from_details
    from ashiba.lifeline import Run, part_params, plan_run, report
    from ashiba.opening_guard import drop_below
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains
    from opening_run import slab_info

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post", default="ntp", choices=("ntp", "alpa"), help="親綱支柱（ntp＝NTP H鋼取付用・alpa＝ALPA12 アルミ）")
    ap.add_argument("--flange", type=float, default=0.0, help="上フランジの厚さ mm")
    ap.add_argument("--top", type=float, default=None, help="線を選んだときの梁の上端 mm")
    ap.add_argument("--drop", type=float, default=None, help="下の床までの落差 mm（省くと床・地盤から求める）")
    ap.add_argument("--remove", action="store_true", help="置いた親綱を消す")
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
        print(f"親綱: {n}本を消しました")
        return 0
    sel = c.get_selected_elements()
    dets = c.get_details(sel) if sel else []
    targets = []                                             # (控えのキー, 始め, 終わり, 上端 mm)
    for e, d in zip(sel, dets):
        if d.get("type") == "Beam":
            bm = beam_from_details(d.get("details") or {})
            if bm:
                targets.append((e["elementId"]["guid"], bm.a, bm.b, bm.top_mm))
    if not targets:
        for key, pts, _closed in chains(selected_guides(c)):
            for i, (p0, p1) in enumerate(zip(pts, pts[1:])):
                targets.append((f"{key}:{i}", tuple(p0), tuple(p1), a.top or 0.0))
    if not targets:
        els = c.tapir("GetElementsByType", {"elementType": "Beam"}).get("elements", [])
        for e, d in zip(els, c.get_details(els) if els else []):
            bm = beam_from_details(d.get("details") or {})
            if bm:
                targets.append((e["elementId"]["guid"], bm.a, bm.b, bm.top_mm))
    if not targets:
        print("親綱: 鉄骨梁か、梁に沿った線を選んでから押してください")
        return 1
    slabs = []
    sl = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
    for d in c.get_details(sl) if sl else []:
        s = slab_info(d)
        if s:
            slabs.append(s)
    gm = read_ground_model(c, [p for _k, p0, p1, _t in targets for p in (p0, p1)])
    ground = gm.elevation_at if getattr(gm, "points", None) else None
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    runs = []
    for n, (key, p0, p1, top) in enumerate(targets, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)])
        mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        drop = a.drop if a.drop is not None else drop_below(mid, top, slabs, ground(*mid) if ground else 0.0)
        r = plan_run(Run(f"親綱{n}", p0, p1, top, drop, "ALPA12" if a.post == "alpa" else "NTP", a.flange))
        el = _place(c, part, p0, top, math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])))
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(r), **pens})
        rec[key] = el["elementId"]["guid"]
        runs.append(r)
        bad = [x.item for x in r.checks if x.status != "OK"]
        print(f"  {r.name}: {r.length / 1000:.1f}m・{len(r.spans)}スパン・落差 {drop / 1000:.1f}m" + (f"・要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "親綱.md"
    md.write_text(report(runs), encoding="utf-8")
    print(f"親綱: {len(runs)}本の梁に置きました（発注表: {md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
