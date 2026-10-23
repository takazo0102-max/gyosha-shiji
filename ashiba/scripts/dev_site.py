"""実機検証用の「建物＋敷地境界線」を作り、足場計画を置く（利用者の指定 2026-10-23: 建物と敷地境界線を作成して
足場計画を繰り返してみて）.

建物（躯体スラブ）と、レイヤー「敷地境界線」の閉じたポリライン、レイヤー「道路境界線」の道路側の線を作る。
配置（run_from_archicad.main）はこの敷地境界線を拾い、面ごとの境界までの離れで NG・要確認を出す。

使い方:
  python3 scripts/dev_site.py create [--at 3000000,2000000] [--road 1200] [--west 1500] [--east 3000] [--north 4000]
  python3 scripts/dev_site.py boundary [--at ...] [--road ...] ...  # 境界線だけ引き直す（建物はそのまま）
  python3 scripts/dev_site.py place  [--at ...] [条件の JSON を ASHIBA_SPEC で]
  python3 scripts/dev_site.py clear  [--at ...]      # 作った境界線を消す（足場は remove_from_archicad で）
  python3 scripts/dev_site.py zoom   [--at ...]      # 平面図をこの建物の足場に合わせる（place の後にも自動で）
建物は 24m×10m（--size 24000x10000）。--shape L で北東を欠いた L 字。境界までの距離は躯体の面から。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402

BOUNDARY_LAYER = "敷地境界線"
ROAD_LAYER = "道路境界線"


def _arg(name: str, default: str) -> str:
    for a in sys.argv:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    if f"--{name}" in sys.argv:
        i = sys.argv.index(f"--{name}")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def site(ox: float, oy: float) -> dict:
    w, h = (float(v) for v in _arg("size", "24000x10000").split("x"))
    road, west, east, north = (float(_arg(k, d)) for k, d in
                               (("road", "1200"), ("west", "1500"), ("east", "3000"), ("north", "4000")))
    if _arg("shape", "rect") == "L":
        # L字（北東を欠く）。入隅の面（東面(辺3)・北面(辺2)）は境界から遠い
        building = [(ox, oy), (ox + w, oy), (ox + w, oy + h / 2), (ox + w / 2, oy + h / 2), (ox + w / 2, oy + h),
                    (ox, oy + h)]
    else:
        building = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
    boundary = [(ox - west, oy - road), (ox + w + east, oy - road), (ox + w + east, oy + h + north),
                (ox - west, oy + h + north)]
    road_line = [(ox - west - 3000, oy - road), (ox + w + east + 3000, oy - road)]
    return {"building": building, "boundary": boundary, "road": road_line}


def _layer(c: ArchicadClient, name: str) -> int:
    attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
    hit = next((a for a in attrs if a.get("name") == name), None)
    if hit is None:
        c.tapir("CreateLayers", {"layerDataArray": [{"name": name}]})
        attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        hit = next(a for a in attrs if a.get("name") == name)
    return int(hit["index"])


def create_boundary(c: ArchicadClient, s: dict) -> None:
    from ashiba.elevation_sections import activate_floor_plan

    activate_floor_plan(c)
    lb, lr = _layer(c, BOUNDARY_LAYER), _layer(c, ROAD_LAYER)
    pts = s["boundary"] + [s["boundary"][0]]
    c.tapir("CreatePolylines", {"polylinesData": [
        {"coordinates": [{"x": x / 1000.0, "y": y / 1000.0} for x, y in pts], "layerIndex": lb},
        {"coordinates": [{"x": x / 1000.0, "y": y / 1000.0} for x, y in s["road"]], "layerIndex": lr}]})


def create(c: ArchicadClient, s: dict) -> None:
    create_boundary(c, s)
    c.tapir("CreateSlabs", {"slabsData": [{"level": 0.0, "thickness": 0.2, "polygonCoordinates": [
        {"x": x / 1000.0, "y": y / 1000.0} for x, y in s["building"]]}]})
    print("建物と敷地境界線を作りました", json.dumps({k: v[:2] for k, v in s.items()}))


def place(s: dict) -> int:
    import run_from_archicad

    spec = {"project_name": _arg("name", "敷地 見本"), "eaves_height_mm": float(_arg("eaves", "9000")),
            "height_from_slabs": False, "elevation_mode": _arg("elev", "section")}
    extra = os.environ.get("ASHIBA_SPEC")
    if extra and Path(extra).exists():
        spec.update(json.loads(Path(extra).read_text(encoding="utf-8")))
    run_from_archicad.main(outline_mm=s["building"], spec_override=spec, use_spec_object=False, fill_title=False,
                           out_dir=ROOT / "out" / "dev_site")
    zoom_to_building(ArchicadClient(timeout=60), s)
    return 0


def zoom_to_building(c: ArchicadClient, s: dict) -> None:
    """平面図をこの建物の足場に合わせる（建物は原点から離れた所に置くので、開いたままだと何も映らない）."""
    from ashiba.elevation_sections import activate_floor_plan

    activate_floor_plan(c)
    els = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    xs = [p[0] for p in s["building"]]
    ys = [p[1] for p in s["building"]]
    mine = []
    for e, d in zip(els, c.get_details(els) if els else []):
        o = (d.get("details") or {}).get("origin") or {}
        x, y = float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0
        if min(xs) - 5000 <= x <= max(xs) + 5000 and min(ys) - 5000 <= y <= max(ys) + 5000:
            mine.append(e)
    if mine:
        c.tapir("FitInWindow", {"elements": mine})


def clear(c: ArchicadClient, s: dict) -> None:
    from ashiba.site_boundary import _inside

    els = c.tapir("GetElementsByType", {"elementType": "PolyLine"}).get("elements", [])
    names = {int(a["index"]): a.get("name") for a in
             c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])}
    # 建物の南辺の中央から 1m 内側（長方形でも L 字でも建物の中）
    cx = (s["building"][0][0] + s["building"][1][0]) / 2.0
    cy = s["building"][0][1] + 1000.0
    gone = []
    for e, d in zip(els, c.get_details(els) if els else []):
        if names.get(int(d.get("layerIndex", -1))) not in (BOUNDARY_LAYER, ROAD_LAYER):
            continue
        pts = [(p["x"] * 1000.0, p["y"] * 1000.0) for p in (d.get("details") or {}).get("coordinates") or []]
        # 境界線は建物を囲むもの。道路境界線は建物の近く（外形から 10m 以内）にあるもの（前の条件で引いた分も）
        xs = [p[0] for p in s["building"]]
        ys = [p[1] for p in s["building"]]
        near = pts and any(min(xs) - 10000 <= x <= max(xs) + 10000 and min(ys) - 10000 <= y <= max(ys) + 10000
                           for x, y in pts)
        if pts and (_inside((cx, cy), pts) or (names.get(int(d.get("layerIndex", -1))) == ROAD_LAYER and near)):
            gone.append(e)
    if gone:
        c.tapir("DeleteElements", {"elements": gone})
    print(f"境界線 {len(gone)}本を消しました")


def main() -> int:
    ox, oy = (float(v) for v in _arg("at", "3000000,2000000").split(","))
    s = site(ox, oy)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "place":
        return place(s)
    c = ArchicadClient(timeout=120)
    if cmd == "create":
        create(c, s)
    elif cmd == "clear":
        clear(c, s)
    elif cmd == "boundary":
        clear(c, s)
        create_boundary(c, s)
    elif cmd == "zoom":
        zoom_to_building(c, s)
        print("境界線を引き直しました", json.dumps(s["boundary"]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
