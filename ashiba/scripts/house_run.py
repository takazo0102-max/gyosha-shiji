"""仮設建物（パレットの「仮設建物」「仮設事務所 2階」「仮設トイレ」「仮設建物の検定」「仮設建物を消す」）.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の4番。

  python3 scripts/house_run.py                          # 選んだ線（始めの辺＝建物の手前の長手、始め＝左の隅）に1棟
  python3 scripts/house_run.py --type 4 --units 3 --tiers 2 --use 事務所,事務所 --stair right
  python3 scripts/house_run.py --type 6 --units 4 --use トイレ      # 仮設トイレを横に4基
  python3 scripts/house_run.py --people 5,30,2          # 人数（職員・作業員の男性・女性）を控えて判定し直す
  python3 scripts/house_run.py --recheck                # 置いた建物の今の形（設定を変えたあと）で判定し直す
  python3 scripts/house_run.py --remove                 # 置いた仮設建物を消す

部品 ashiba_house を1棟に1つ（src/ashiba/site_house.py が型・判定・数量）。判定は置いたすべての建物と人数（控え
ashiba_out/仮設建物の人数.json。無ければ 職員 5・男性 30・女性 2）で、帳票は ashiba_out/仮設建物.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_house"
RECORD = "仮設建物.json"
PEOPLE = "仮設建物の人数.json"
DEFAULT_PEOPLE = {"staff": 5, "men": 30, "women": 2, "fire_zone": False}


def parse_uses(text: str) -> tuple[int, ...]:
    from ashiba.site_house import USES

    inv = {v: k for k, v in USES.items()}
    out = []
    for t in [x.strip() for x in str(text).replace("、", ",").split(",") if x.strip()]:
        if t.isdigit() and int(t) in USES:
            out.append(int(t))
        elif t in inv:
            out.append(inv[t])
        else:
            raise SystemExit(f"用途は {'・'.join(USES.values())} のどれか（{t}）")
    return tuple(out) or (1,)


def site_report(c, R, rec: dict, people: dict) -> str:
    """置いたすべての建物（控えの GUID）を部品のパラメータから読み、人数で判定する."""
    from ashiba.site_house import Site, check, house_from_params, report

    alive = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])}
    houses = []
    for g in [g for g in rec.values() if g in alive]:
        it = c.tapir("GetGDLParametersOfElements", {"elements": [{"elementId": {"guid": g}}]})["gdlParametersOfElements"][0]
        ps = {x["name"]: x.get("value") for x in it.get("gdlParameters", it.get("parameters", []))}
        houses.append(house_from_params(ps))
    site = check(Site(houses, int(people["staff"]), int(people["men"]), int(people["women"]), bool(people.get("fire_zone"))))
    md = R.OUT_DIR / "仮設建物.md"
    md.write_text(report(site), encoding="utf-8")
    bad = [x.item for x in site.checks if x.status != "OK"]
    print(f"仮設建物の判定: {len(houses)}棟・" + (f"要確認 {'・'.join(bad)}" if bad else "OK") + f"（{md}）")
    return md


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.site_house import HOUSES, House, part_params
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--type", type=int, default=4, choices=list(HOUSES), help="型（1〜5 スーパーハウス・6 仮設トイレ・7 快適トイレハウス）")
    ap.add_argument("--units", type=int, default=1, help="連棟の数")
    ap.add_argument("--tiers", type=int, default=1, choices=(1, 2, 3), help="段の数")
    ap.add_argument("--use", default="", help="段ごとの用途（事務所,詰所 など。省くと事務所、トイレの型はトイレ）")
    ap.add_argument("--stair", default="left", choices=("left", "right"), help="2階への外階段の端")
    ap.add_argument("--people", default="", help="人数 職員,男性,女性（控えて、以後の判定に使う）")
    ap.add_argument("--fire-zone", action="store_true", help="防火・準防火地域（人数の控えに入れる）")
    ap.add_argument("--recheck", action="store_true", help="置いた建物で判定し直すだけ")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--remove", action="store_true", help="置いた仮設建物を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path, ppl_path = R.OUT_DIR / RECORD, R.OUT_DIR / PEOPLE
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    try:
        people = {**DEFAULT_PEOPLE, **json.loads(ppl_path.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        people = dict(DEFAULT_PEOPLE)
    if a.people:
        st, mn, wm = (int(x) for x in a.people.split(","))
        people.update(staff=st, men=mn, women=wm)
    if a.fire_zone:
        people["fire_zone"] = True
    ppl_path.write_text(json.dumps(people, ensure_ascii=False), encoding="utf-8")
    if a.remove:
        n = _delete_alive(c, list(rec.values()))
        rec_path.write_text("{}", encoding="utf-8")
        print(f"仮設建物: {n}棟を消しました")
        return 0
    if a.recheck or (a.people and not selected_guides(c)):
        site_report(c, R, rec, people)
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("仮設建物: 建物の手前の線（始めの辺＝長手、始め＝左の隅）を選んでから押してください")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    uses = parse_uses(a.use) if a.use else ((7,) if HOUSES[a.type][5] else (1,))
    n0 = len(rec)
    for n, (key, pts) in enumerate(lines, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)])
        (x0, y0), (x1, y1) = pts[0], pts[1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        h = House(f"{'トイレ' if HOUSES[a.type][5] else '仮設建物'}{n0 + n}", a.type, max(1, a.units), a.tiers, uses,
                  0 if a.stair == "left" else 1)
        z = a.z if a.z is not None else (ground(x0, y0) if ground else 0.0)
        el = _place(c, part, (x0, y0), z, ang)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(h), **pens})
        rec[key] = el["elementId"]["guid"]
        w, d, _h = h.size
        print(f"  {h.name}: {HOUSES[a.type][0]} {h.units}連棟×{h.tiers}段（{w / 1000:.2f}×{d / 1000:.2f}m）")
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    site_report(c, R, rec, people)
    return 0


if __name__ == "__main__":
    sys.exit(main())
