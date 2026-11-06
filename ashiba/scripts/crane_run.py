"""移動式クレーン（パレットの「クレーン」）.

利用者の指定（2026-11-01）「クレーン リサーチして追加して」。

  python3 scripts/crane_run.py --load 2.5 --lift-z 15000      # 線を選ばなければ平面図で 2回クリック（旋回中心・吊り荷の位置。Esc でやめる）
                                                             # 選んだ線（ポリライン）があれば始めの点＝旋回中心、ほかの点＝吊り荷
  python3 scripts/crane_run.py --load 2.5,1.0 --lift-z 15000,12000 --model 25t
  python3 scripts/crane_run.py --soil-q 150 --spread 5.0     # 地盤の許容支持力（短期 kN/m²）・アウトリガの張出幅 m
  python3 scripts/crane_run.py --carrier-angle 0             # 車体の向き（度。省くと線の始めの辺の向き）
  python3 scripts/crane_run.py --boom 23.45 --jib 8.2 --jib-off 5   # ブーム長さ・ジブ長さ・オフセット角（ジブの定格は性能表で）
  python3 scripts/crane_run.py --ask                         # 機種・ブーム・ジブ・安全率を窓で選ぶ（パレットのボタン）
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

POSE_KEYS = ("pivB", "jbL", "jbO", "hkR", "prio", "boomL", "boomA")    # クレーンの姿勢（2回めに入れ直す）
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


def ask(a) -> bool:
    """機種・ブーム・ジブ・安全率を窓で選ぶ. やめたら False."""
    from form_dialog import show_form

    from ashiba.crane import JIB_OFFSET, JIBS, MODELS

    auto = "自動（吊り荷を満たす一番小さい機種）"
    names = {f"{m.name.split(' ', 1)[1]}": k for k, m in MODELS.items()}
    jibs = "・".join(f"{MODELS[k].name.split(' ')[1]} {'・'.join(f'{v:g}' for v in vs)}" for k, vs in JIBS.items())
    res = show_form({
        "title": "クレーン",
        "intro": "線を選んでいなければ、置くを押したあと平面図で 1回目に旋回中心、2回目に吊り荷の位置をクリック（車体はその向き）。"
                 "線を選んでいれば、その線に置きます。平面のブームの先に定格総荷重と安全率を掛けた荷重、作業の最小半径を描きます。ホットスポットで、ブームの先は起伏角、"
                 "平面のフックは作業半径を動かせます。ジブの長さ（m）: " + jibs,
        "fields": [{"key": "model", "label": "機種", "kind": "choice", "options": [auto] + list(names), "value": auto},
                   {"key": "load", "label": "吊り荷 t（線の点ごとはカンマ区切り）", "kind": "text", "value": a.load or "1"},
                   {"key": "liftz", "label": "要るフックの高さ mm（地盤から）", "kind": "text", "value": a.lift_z or "10000"},
                   {"key": "boom", "label": "ブーム長さ m（空＝吊り荷から自動）", "kind": "number", "value": ""},
                   {"key": "jib", "label": "ジブ長さ m（空＝なし）", "kind": "number", "value": ""},
                   {"key": "off", "label": "ジブのオフセット角 度", "kind": "number", "value": f"{JIB_OFFSET:g}"},
                   {"key": "ratio", "label": "安全率（定格総荷重に掛ける。0.9＝90%）", "kind": "number", "value": f"{a.ratio:g}"}],
        "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        return False
    v = res.get("values") or {}
    a.model = names.get(str(v.get("model")), a.model)
    a.load = str(v.get("load") or "").strip() or a.load
    a.lift_z = str(v.get("liftz") or "").strip() or a.lift_z
    for key, attr in (("boom", "boom"), ("jib", "jib"), ("off", "jib_off"), ("ratio", "ratio")):
        try:
            setattr(a, attr, float(str(v.get(key) or "").replace(",", "")))
        except ValueError:
            pass
    return True


def main(argv=None) -> int:
    from ashiba.naming import ordinal, prune_gone

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
    ap.add_argument("--boom", type=float, default=0.0, help="ブーム長さ m（省くと吊り荷から）")
    ap.add_argument("--jib", type=float, default=0.0, help="ジブ長さ m（0＝なし）")
    ap.add_argument("--jib-off", dest="jib_off", type=float, default=5.0, help="ジブのオフセット角")
    ap.add_argument("--ask", action="store_true", help="機種・ブーム・ジブ・安全率を窓で選ぶ")
    ap.add_argument("--pick", action="store_true", help="線を選んでいてもクリックで置く")
    ap.add_argument("--remove", action="store_true", help="置いたクレーンを消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    rec = prune_gone(c, rec)                     # Archicad で消したものは控えから除く（番号・帳票）
    if a.remove:
        n = _delete_alive(c, [g for v in rec.values() for g in (v if isinstance(v, list) else [v])])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"クレーン: {n}台を消しました")
        return 0
    if a.ask and not ask(a):
        print("クレーン: やめました（何も置いていません）")
        return 0
    lines = [] if a.pick else [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        from machine_run import front_archicad, pick_line

        if c.tapir("GetCurrentWindowType", {}).get("currentWindowType") != "FloorPlan":
            print("クレーン: 平面図の窓を前にしてから押してください（線を選んであれば、その線に置きます）")
            return 1
        front_archicad(c)
        print("  平面図で 旋回中心 → 吊り荷の位置 の順にクリック（Esc でやめる）", flush=True)
        pts = pick_line(c, "Click the crane center", "Click the load position")
        if pts is None:
            print("クレーン: やめました（何も置いていません）")
            return 0
        lines = [(f"クリック:{pts[0][0]:.0f}:{pts[0][1]:.0f}", pts)]
    R.ensure_parts(c)                                    # クリックを待たせないよう、部品の確認はあとで
    part = R.versioned_part_name(PART)
    plate_part = R.versioned_part_name(PLATE_PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
    ground = gm.elevation_at if getattr(gm, "points", None) else None
    plans = []
    fresh = 0
    for _n, (key, pts) in enumerate(lines, 1):
        n = ordinal(rec, key, fresh)                    # 名前の番号は控えの続き（同じ線は前の番号のまま）
        fresh += key not in rec
        if key in rec:
            old = rec[key]
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
        cps = part_params(p, slew, ratio=a.ratio, boom_m=a.boom, jib=a.jib, jib_off=a.jib_off)
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
