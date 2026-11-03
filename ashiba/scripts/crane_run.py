"""移動式クレーン（パレットの「クレーン」「クレーンを消す」）.

利用者の指定（2026-11-01）「クレーン リサーチして追加して」。

  python3 scripts/crane_run.py --load 2.5 --lift-z 15000      # 選んだ線（ポリライン）の始めの点＝旋回中心、ほかの点＝吊り荷
  python3 scripts/crane_run.py --load 2.5,1.0 --lift-z 15000,12000 --model 25t
  python3 scripts/crane_run.py --soil-q 150 --spread 5.0     # 地盤の許容支持力（短期 kN/m²）・アウトリガの張出幅 m
  python3 scripts/crane_run.py --carrier-angle 0             # 車体の向き（度。省くと線の始めの辺の向き）
  python3 scripts/crane_run.py --remove                      # 置いたクレーンを消す

線1本に部品 ashiba_crane を1台（src/ashiba/crane.py が機種・ブーム・アウトリガ・敷鉄板・検定）と、アウトリガの下に敷鉄板の部品
ashiba_plate（脚ごとに1枚か十字に2枚。ホットスポットで広げられる。利用者の指定 2026-11-01: 敷鉄板は別オブジェクトにして）。機種を省くと全部の吊り荷を満たす
一番小さい機種（25t・50t・70t）。ブームはいちばん厳しい吊り荷へ向けて描く。前に同じ線に置いたものは控え（ashiba_out/クレーン.json）
で消して置き直す。数量と検定は ashiba_out/クレーン.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

POSE_KEYS = ("pivB", "hkR", "prio", "boomL", "boomA")    # クレーンの姿勢（2回めに入れ直す）
PART = "ashiba_crane"
PLATE_PART = "ashiba_plate"
RECORD = "クレーン.json"


def _floats(text: str | None, n: int, default: float) -> list[float]:
    """「2.5,1.0」→ 吊り荷の数だけ（足りなければ最後の値を繰り返す）."""
    vals = [float(v) for v in (text or "").replace("、", ",").split(",") if v.strip()] or [default]
    return [vals[min(i, len(vals) - 1)] for i in range(n)]


def lifts_from_points(pts: list, loads: str | None, lift_z: str | None):
    """点列 → (旋回中心, [Lift])。始めの点が旋回中心、ほかが吊り荷の位置."""
    from ashiba.crane import Lift

    c, rest = pts[0], pts[1:]
    ws = _floats(loads, len(rest), 1.0)
    zs = _floats(lift_z, len(rest), 10000.0)
    return c, [Lift(f"吊り荷{i}", math.dist(c, p), w, z) for i, (p, w, z) in enumerate(zip(rest, ws, zs), 1)]


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.crane import LOAD_RATIO, MODELS, PLATE, SOIL_Q, crane_plan, outrigger_plates, part_params, report
    from ashiba.steel_plate import layout
    from ashiba.steel_plate import part_params as plate_params
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", choices=list(MODELS), default=None, help="機種（省くと吊り荷を満たす一番小さい機種）")
    ap.add_argument("--load", default=None, help="吊り荷 t（点の順にカンマ区切り。1つなら全部）")
    ap.add_argument("--lift-z", default=None, help="要るフックの高さ mm（地盤から。点の順にカンマ区切り。既定 10000）")
    ap.add_argument("--spread", type=float, default=None, help="アウトリガの張出幅 m（省くと最大）")
    ap.add_argument("--soil-q", type=float, default=SOIL_Q, help="地盤の許容支持力（短期）kN/m²")
    ap.add_argument("--ratio", type=float, default=LOAD_RATIO, help="計画の率（定格総荷重に対して。既定 0.9）")
    ap.add_argument("--carrier-angle", type=float, default=None, help="車体の向き（度。省くと線の始めの辺の向き）")
    ap.add_argument("--remove", action="store_true", help="置いたクレーンを消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, [g for v in rec.values() for g in (v if isinstance(v, list) else [v])])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"クレーン: {n}台を消しました")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("クレーン: 線（ポリライン）を選んでから押してください（始めの点＝クレーンの旋回中心、ほかの点＝吊り荷の位置）")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    plate_part = R.versioned_part_name(PLATE_PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
    ground = gm.elevation_at if getattr(gm, "points", None) else None
    plans = []
    for n, (key, pts) in enumerate(lines, 1):
        if key in rec:
            old = rec.pop(key)
            _delete_alive(c, old if isinstance(old, list) else [old])
        center, lifts = lifts_from_points(pts, a.load, a.lift_z)
        p = crane_plan(f"クレーン{n}", lifts, a.model, a.spread, a.soil_q, a.ratio)
        car = a.carrier_angle if a.carrier_angle is not None else math.degrees(
            math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]))
        g = p.governing
        gi = p.lifts.index(g) + 1 if g else 1
        to = math.degrees(math.atan2(pts[gi][1] - center[1], pts[gi][0] - center[0]))
        slew = (to - car + 540.0) % 360.0 - 180.0
        z = ground(*center) if ground else 0.0
        el = _place(c, part, center, z, car)
        if el is None:
            continue
        # 脚の吸い付きは先に切る（Tapir は1つずつ入れ、脚の時点では既定の 25t の段に吸い付いて 3.8m が 3.3m になった）
        c.set_gdl_parameters(el, {"oSnap": False})
        cps = part_params(p, slew, ratio=a.ratio)
        c.set_gdl_parameters(el, {**cps, **pens})
        # 姿勢はもう一度入れる。1回だと pivB・hkR が入る前の古い値で起伏角と作業半径が書き戻された（2026-11-03 実機:
        # 25t の hkR 8.0 が 6.75・起伏角 49.7° が 55.2° に。2回めで一致）
        c.set_gdl_parameters(el, {k: cps[k] for k in POSE_KEYS if k in cps})
        c.set_gdl_parameters(el, {"oSnap": True})        # 置いたあとで脚の吸い付きを入れる（手で引いたときだけ吸い付く）
        placed = [el["elementId"]["guid"]]
        # アウトリガの下の敷鉄板（別の部品。車体の座標 → 図面の座標）
        ca, sa = math.cos(math.radians(car)), math.sin(math.radians(car))
        plens = gdl_pens(parse_pens(spec.get("pens")), PLATE_PART)
        _n, s_mm, lg_mm, _t, _kg = PLATE
        for (lx, ly), along_y, dz in outrigger_plates(p):
            at = (center[0] + lx * ca - ly * sa, center[1] + lx * sa + ly * ca)
            pe = _place(c, plate_part, at, z + dz, car)
            if pe is None:
                continue
            lay = layout(s_mm if along_y else lg_mm, lg_mm if along_y else s_mm, "NT22×5×10", along_y)
            c.set_gdl_parameters(pe, {**plate_params(lay, f"{p.name} 敷鉄板", text=False), **plens})
            placed.append(pe["elementId"]["guid"])
        rec[key] = placed
        plans.append(p)
        print(f"  {p.name}: {p.model.name}・張出 {p.spread:g}m・ブーム {p.boom:g}m・敷鉄板 {p.plates}枚／脚・接地圧 {p.pressure:.0f}kN/m²")
        for x in p.lifts:
            print(f"    {x.name}: 半径 {x.radius / 1000:.1f}m・{x.load_t:g}t → {x.status} {x.note}")
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "クレーン.md"
    md.write_text(report(plans), encoding="utf-8")
    print(f"クレーン: {len(plans)}台を置きました（数量と検定: {md}）")
    for p in plans:
        for ck in p.checks:
            if ck.status != "OK":
                print(f"  {ck.status} {p.name} {ck.item}: {ck.message}")
    return 0 if all(p.ok for p in plans) else 2


if __name__ == "__main__":
    sys.exit(main())
