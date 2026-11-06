"""クレーンの車体とフックを動かす（パレットの「クレーン操作」の小窓から呼ぶ。SCP の手引 p.5「車両・フックの移動」）.

利用者の指定（2026-11-06）「SCPに入っているクレーンの機能全て入れて揚重検討が楽になるように」。

  python3 scripts/crane_move.py --car 1 0 0 0        # 選んだクレーンの車体を X・Y・Z（m）に動かし、回転（度）
  python3 scripts/crane_move.py --hook 0 1 0 0 0     # フックを X・Y・Z・半径（m）に動かし、旋回（度）
  python3 scripts/crane_move.py --ground             # 真下の要素に接地（柱・梁・壁・床・屋根・シェル・モルフ・オブジェクト）

X・Y は図面の向き。ラフターは一緒に置いた敷鉄板（控えの クレーン.json）も動かす。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

GROUND_TYPES = ("Column", "Beam", "Wall", "Slab", "Roof", "Shell", "Morph", "Object")


def hook_local(radius: float, slew: float) -> tuple[float, float]:
    """作業半径と旋回角 → 部品の座標のフック（m）."""
    return radius * math.cos(math.radians(slew)), radius * math.sin(math.radians(slew))


def move_hook(radius: float, slew: float, car: float, dx: float, dy: float, dr: float, da: float) -> tuple[float, float]:
    """図面の向きの移動 → 新しい（作業半径, 旋回角）. 半径は dr を足し、旋回は da を足す."""
    x, y = hook_local(radius, slew)
    a = math.radians(-car)
    x += dx * math.cos(a) - dy * math.sin(a)
    y += dx * math.sin(a) + dy * math.cos(a)
    r = math.hypot(x, y)
    s = math.degrees(math.atan2(y, x)) if dx or dy else slew
    return r + dr, (s + da) % 360.0


def ground_z(boxes: list, x: float, y: float, z: float) -> float | None:
    """(x, y) の真下にある要素の天端でいちばん高いもの mm（z より上の要素は見ない）. 無ければ None."""
    tops = [b[1][2] for b in boxes if b and b[0][0] <= x <= b[1][0] and b[0][1] <= y <= b[1][1] and b[1][2] <= z + 1.0]
    return max(tops) if tops else None


def group_of(rec: dict, guid: str) -> list:
    """控えから、クレーンと一緒に動かす要素（敷鉄板）の GUID."""
    for v in rec.values():
        gs = v if isinstance(v, list) else []
        if guid in gs:
            return gs
    return [guid]


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.tapir_adapter import ArchicadClient, TapirError
    from crane_check import _params, boxes, find_crane, hook_point

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--car", nargs=4, type=float, metavar=("DX", "DY", "DZ", "DA"), help="車体を動かす（m・度）")
    ap.add_argument("--hook", nargs=5, type=float, metavar=("DX", "DY", "DZ", "DR", "DA"), help="フックを動かす（m・度）")
    ap.add_argument("--ground", action="store_true", help="真下の要素に接地")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    sel = c.get_selected_elements()
    if not sel:
        print("クレーンを選んでください")
        return 1
    crane, cd = find_crane(c, sel, c.get_details(sel))
    if crane is None or crane not in sel:
        print("クレーンを選んでください")
        return 1
    guid = crane["elementId"]["guid"]
    ps = _params(c, crane)
    name = cd["details"]["libPart"]["name"]
    kind = "tower" if name.startswith("ashiba_tower") else "crawler" if name.startswith("ashiba_machine") else "rough"
    o = cd["details"]["origin"]
    origin = (o["x"] * 1000.0, o["y"] * 1000.0, o.get("z", 0.0) * 1000.0)
    car = math.degrees(cd["details"].get("angle", 0.0))
    try:
        rec = json.loads((R.OUT_DIR / "クレーン.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    group = [{"elementId": {"guid": g}} for g in group_of(rec, guid)]
    if a.ground:
        els = [e for ty in GROUND_TYPES for e in c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])
               if e["elementId"]["guid"] not in {g["elementId"]["guid"] for g in group}]
        z = ground_z(boxes(c, els), origin[0], origin[1], origin[2])
        if z is None:
            print("真下に要素がありません")
            return 0
        a.car = [0.0, 0.0, (z - origin[2]) / 1000.0, 0.0]
    if a.car:
        dx, dy, dz, da = a.car
        if dx or dy or dz:
            c.tapir("MoveElements", {"elementsWithMoveVectors": [{**e, "moveVector": {"x": dx, "y": dy, "z": dz}} for e in group]})
        if da:
            at = {"x": origin[0] / 1000.0 + dx, "y": origin[1] / 1000.0 + dy}
            end = {"x": at["x"] + math.cos(math.radians(da)), "y": at["y"] + math.sin(math.radians(da))}
            c.tapir("RotateElements", {"elementsWithRotations": [
                {**e, "rotation": {"beginPoint": {"x": at["x"] + 1.0, "y": at["y"]}, "endPoint": end, "origin": at}} for e in group]})
        print(f"車体 X {origin[0] / 1000 + dx:.2f}・Y {origin[1] / 1000 + dy:.2f}・Z {origin[2] / 1000 + dz:.2f}m・向き {(car + da) % 360:.0f}°")
        return 0
    dx, dy, dz, dr, da = a.hook
    slew = float(ps.get("slew", 0.0))
    if kind == "tower":
        rad = float(ps.get("pvX", 1.0)) + float(ps.get("jbL", 40.0)) * math.cos(math.radians(float(ps.get("jbA", 45.0))))
    elif kind == "crawler":
        from ashiba.machine import hook_radius

        rad = hook_radius(ps)
    else:
        rad = float(ps.get("hkR", 10.0))
    r, s = move_hook(rad, slew, car, dx, dy, dr, da)
    try:
        if dx or dy or da:
            c.set_gdl_parameters(crane, {"slew": s})
        if dx or dy or dr:
            if kind == "tower":
                if int(ps.get("tcType", 1) or 1) == 1:
                    c.set_gdl_parameters(crane, {"jbA": math.degrees(math.acos(max(-1.0, min(1.0, (r - float(ps.get("pvX", 1.0))) / float(ps.get("jbL", 40.0))))))})
            else:
                c.set_gdl_parameters(crane, {"lbR" if kind == "crawler" else "hkR": r})
        if dz:
            if kind == "rough":
                c.set_gdl_parameters(crane, {"hkZ": (hook_point(ps, origin, car, kind)[2] - origin[2]) / 1000.0 + dz})
            else:
                c.set_gdl_parameters(crane, {"hkD": float(ps.get("hkD", 6.0)) - dz})
    except TapirError:
        pass                                             # 部品が届く所へ戻した（値の確かめは下の読み直しで）
    q = _params(c, crane)
    now = q.get("lbR" if kind == "crawler" else "hkR", r)
    print(f"フック 半径 {float(now):.2f}m・旋回 {float(q.get('slew', s)):.0f}°")
    return 0


if __name__ == "__main__":
    sys.exit(main())
