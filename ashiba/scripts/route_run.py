"""場内の車両動線と敷鉄板（パレットの「場内通路」）.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の3番。

  python3 scripts/route_run.py                         # 選んだ中心線（ポリライン。始め＝ゲートの側）に通路と敷鉄板
  python3 scripts/route_run.py --vehicle mixer         # 車両（4t・10t・mixer・mixer_m・R25・std）
  python3 scripts/route_run.py --vehicle lb4           # 搬入トラック・トレーラー（重機の搬入車両の機種。--list-vehicles）
  python3 scripts/route_run.py --two-way --width 6500  # 対面通行・幅
  python3 scripts/route_run.py --across --plate 5x10   # 敷鉄板を横敷き・5×10 で
  python3 scripts/route_run.py --no-plates             # 通路だけ
  python3 scripts/route_run.py --remove                # 置いた通路と敷鉄板を消す

部品 ashiba_route を通路に1つ、敷鉄板は ashiba_plate を区間ごとに（src/ashiba/site_route.py が割付・検定・数量）。前に同じ線に
置いたものは控え（ashiba_out/場内通路.json）で消して置き直す。帳票は ashiba_out/場内通路.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_route"
RECORD = "場内通路.json"


def main(argv=None) -> int:
    from ashiba.naming import ordinal, prune_gone

    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.site_route import part_params, report, route_plan, vehicle_keys, vehicle_name
    from ashiba.steel_plate import part_params as plate_params
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains
    from plate_run import plate_code

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vehicle", default="10t", choices=vehicle_keys(),
                    help="一番大きい車両（搬入トラック tr2〜sl10・トレーラー lb2・lb4・lbl・fb3・pt2 は追従の軌跡で曲がり角を見る）")
    ap.add_argument("--list-vehicles", action="store_true", help="車両の一覧を出して終わる")
    ap.add_argument("--width", type=float, default=0.0, help="通路の幅 mm（省くと一方通行 4,000・対面 6,000）")
    ap.add_argument("--two-way", action="store_true", help="対面通行")
    ap.add_argument("--plate", default="5x20", help="敷鉄板（5x20・5x10・4x8・3x6）")
    ap.add_argument("--across", action="store_true", help="敷鉄板を横敷き（長い辺を走る向きと直角に）")
    ap.add_argument("--no-plates", action="store_true", help="敷鉄板を置かない")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--remove", action="store_true", help="置いた通路と敷鉄板を消す")
    a = ap.parse_args(argv)
    if a.list_vehicles:
        for k in vehicle_keys():
            print(f"  {k:8s} {vehicle_name(k)}")
        return 0
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    rec = prune_gone(c, rec)                     # Archicad で消したものは控えから除く（番号・帳票）
    if a.remove:
        n = _delete_alive(c, [g for v in rec.values() for g in v])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"場内通路: {n}個を消しました")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("場内通路: 通路の中心線（ポリライン。始め＝ゲートの側）を選んでから押してください")
        return 1
    R.ensure_parts(c)
    part, ppart = R.versioned_part_name(PART), R.versioned_part_name("ashiba_plate")
    spec = {**R.SPEC, **R.load_spec_override()}
    pens, ppens = gdl_pens(parse_pens(spec.get("pens")), PART), gdl_pens(parse_pens(spec.get("pens")), "ashiba_plate")
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    ppens.update(draft_pens_for(c, ppens.get("penEquip", 1)))
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    code = plate_code(a.plate)
    plans = []
    fresh = 0
    for _n, (key, pts) in enumerate(lines, 1):
        n = ordinal(rec, key, fresh)                    # 名前の番号は控えの続き（同じ線は前の番号のまま）
        fresh += key not in rec
        if key in rec:
            _delete_alive(c, rec[key])
        p = route_plan(f"通路{n}", pts, a.width, a.vehicle, a.two_way, not a.no_plates, code, a.across)
        z = a.z if a.z is not None else (ground(*pts[0]) if ground else 0.0)
        el = _place(c, part, pts[0], z, 0.0)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(p), **pens})
        guids = [el["elementId"]["guid"]]
        for k, (corner, ang, lay) in enumerate(p.plates, 1):
            zp = a.z if a.z is not None else (ground(*corner) if ground else 0.0)
            pe = _place(c, ppart, corner, zp, ang)
            if pe is None:
                continue
            c.set_gdl_parameters(pe, {**plate_params(lay, f"{p.name} 敷鉄板{k}", text=False), **ppens})
            guids.append(pe["elementId"]["guid"])
        rec[key] = guids
        plans.append(p)
        ng = [x.item for x in p.checks if x.status != "OK"]
        print(f"  {p.name}: {p.length / 1000:.1f}m・幅 {p.width / 1000:.1f}m・曲がり角 {len(p.corners)}・敷鉄板 {len(p.plates)}区画"
              + (f"・要確認 {'・'.join(ng)}" if ng else "・検定 OK"))
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "場内通路.md"
    md.write_text(report(plans), encoding="utf-8")
    print(f"場内通路: {len(plans)}本を置きました（検定・数量: {md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
