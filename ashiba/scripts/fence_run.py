"""歩行者の安全（パレットの「歩行者通路の柵」「防護柵」「柵を消す」）.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の6番。

  python3 scripts/fence_run.py                          # 選んだ線（ポリライン）に PPフェンス
  python3 scripts/fence_run.py --kind stand             # スタンドバリケード C型＋単管（pp・stand・vulcan・guardrail）
  python3 scripts/fence_run.py --kind vulcan --road     # 車両の通路と接する所にバルカンバリア
  python3 scripts/fence_run.py --walk 1500 --busy       # 歩行者通路の幅を判定（歩行者の多い所は 1.5m 以上）
  python3 scripts/fence_run.py --remove                 # 置いた柵を消す

部品 ashiba_fence を線に1つ（src/ashiba/fence.py が割付・判定・数量）。前に同じ線に置いたものは控え（ashiba_out/柵.json）で
消して置き直す。帳票は ashiba_out/柵.md（発注表）.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_fence"
RECORD = "柵.json"


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.fence import KIND_KEYS, FenceRun, part_params, plan_run, report
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", default="pp", choices=list(KIND_KEYS), help="柵の種類")
    ap.add_argument("--walk", type=float, default=0.0, help="歩行者通路の幅 mm（判定する）")
    ap.add_argument("--busy", action="store_true", help="歩行者の多い所（幅 1.5m 以上）")
    ap.add_argument("--road", action="store_true", help="車両の通路と接する（防護柵か見る）")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--remove", action="store_true", help="置いた柵を消す")
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
        print(f"柵: {n}本を消しました")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("柵: 柵を立てる線（ポリライン・線）を選んでから押してください")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    runs = []
    for n, (key, pts) in enumerate(lines, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)])
        r = plan_run(FenceRun(f"柵{n}", [tuple(p) for p in pts], KIND_KEYS[a.kind], a.walk, a.busy, a.road))
        z = a.z if a.z is not None else (ground(*pts[0]) if ground else 0.0)
        el = _place(c, part, pts[0], z, 0.0)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(r), **pens})
        rec[key] = el["elementId"]["guid"]
        runs.append(r)
        bad = [x.item for x in r.checks if x.status != "OK"]
        print(f"  {r.name}: {r.length / 1000:.1f}m・{sum(r.units)}基" + (f"・要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "柵.md"
    md.write_text(report(runs), encoding="utf-8")
    print(f"柵: {len(runs)}本を置きました（発注表: {md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
