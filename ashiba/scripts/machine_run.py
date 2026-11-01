"""重機（パレットの「重機」「重機を消す」）.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。

  python3 scripts/machine_run.py --type bh045            # 選んだ線の始め＝旋回中心（車は真ん中）、始めの辺の向き＝車体の前
  python3 scripts/machine_run.py --type pump36 --slew 90  # ブーム・上部を 90° 回す
  python3 scripts/machine_run.py --type cc50 --soil-q 150 # 地盤の許容支持力（短期 kN/m²）
  python3 scripts/machine_run.py --list                   # 機種の一覧
  python3 scripts/machine_run.py --remove                 # 置いた重機を消す

部品 ashiba_machine を線1本に1台（src/ashiba/machine.py が機種・寸法・判定）。前に同じ線に置いたものは控え
（ashiba_out/重機.json）で消して置き直す。手配表と判定は ashiba_out/重機.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_machine"
RECORD = "重機.json"


def main(argv=None) -> int:
    import argparse

    from ashiba.machine import MACHINES, SOIL_Q, Placed, check, find, part_params, report

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", default="bh045", help="機種（" + "・".join(MACHINES) + "）")
    ap.add_argument("--slew", type=float, default=0.0, help="上部・ブームの旋回角（度。車体の前から左回り）")
    ap.add_argument("--soil-q", type=float, default=SOIL_Q, help="地盤の許容支持力（短期 kN/m²）")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--list", action="store_true", help="機種の一覧を出す")
    ap.add_argument("--remove", action="store_true", help="置いた重機を消す")
    a = ap.parse_args(argv)
    if a.list:
        for k, m in MACHINES.items():
            print(f"{k:8s} {m.name}（{m.model}）")
        return 0
    try:
        mach = find(a.type)
    except KeyError as e:
        print(e.args[0])
        return 1

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, [v["guid"] for v in rec.values()])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"重機: {n}台を消しました")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("重機: 線（始め＝旋回中心・始めの辺の向き＝車体の前）を選んでから押してください")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    n0 = len(rec)
    for n, (key, pts) in enumerate(lines, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)["guid"]])
        (x0, y0), (x1, y1) = pts[0], pts[1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        p = check(Placed(f"重機{n0 + n}", mach, a.slew), a.soil_q)
        z = a.z if a.z is not None else (ground(x0, y0) if ground else 0.0)
        el = _place(c, part, (x0, y0), z, ang)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(p), **pens})
        rec[key] = {"guid": el["elementId"]["guid"], "type": mach.key, "name": p.name, "slew": a.slew}
        bad = [x.item for x in p.checks if x.status not in ("OK", "注意")]
        print(f"  {p.name}: {mach.name}（{mach.model}）" + (f" 要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    placed = [check(Placed(v["name"], MACHINES[v["type"]], v.get("slew", 0.0)), a.soil_q)
              for v in rec.values() if v.get("type") in MACHINES]
    md = R.OUT_DIR / "重機.md"
    md.write_text(report(placed, a.soil_q), encoding="utf-8")
    print(f"重機: {len(placed)}台（{md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
