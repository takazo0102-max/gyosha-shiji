"""詳細図をレイアウト「<工事名> 足場詳細図」に並べる（Phase 9-3）.

詳細図の部品（ashiba_detail）は平面（1/100）の建物の下に一列に置く。そのままでは文字が
1/100 の大きさで描かれ、詳細図どうしが横に重なっていた（実機で幅7〜10m、間隔4m）。

やり方:
1. 部品に detScale（詳細図の縮尺の分母）を渡し、その縮尺で読める文字の大きさで描かせる
2. 実際の外形（API.Get2DBoundingBoxes）を測り、重ならないよう一列に詰め直す（MoveElements）
3. 詳細図ごとに外形で切り抜いた平面の図面を、1/detScale でレイアウトに並べる
   （図面は 1/100 の平面の拡大なので、比率 scale = 100/detScale）

用紙に入らなければ縮尺を 1/20 → 1/30 → 1/50 と下げて測り直す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .elevation_sections import (
    _create_layout,
    _delete_items,
    _layout_paper_mm,
    _tree,
    activate_floor_plan,
    active_story_item,
    plan_source,
    arrange_boxes,
    clipped_drawing_geometry,
    ensure_subset,
    pick_master_layout,
    walk_tree,
)

DETAIL_SCALES = (20, 30, 50)
GAP_MM = 1500.0          # 詳細図どうしの間（モデル mm）
CLIP_MARGIN_MM = 300.0   # 切り抜き枠を外形から広げる量（モデル mm）
SOURCE_SCALE = 100       # 図面の元になる平面の縮尺（ツールバーの平面は 1/100）


def detail_layout_name(prefix: str) -> str:
    return f"{prefix} 足場詳細図"


def row_origins(bboxes_rel: list[tuple[float, float, float, float]], start_x: float, gap_mm: float = GAP_MM) -> list[float]:
    """原点からの相対外形 (xmin, ymin, xmax, ymax) の並びを、重ならないよう左から詰めた各原点の x.

    i 番目の外形の左端が前の右端＋gap に来るように置く。
    """
    xs = []
    cursor = start_x
    for xmin, _ymin, xmax, _ymax in bboxes_rel:
        x = cursor - xmin
        xs.append(x)
        cursor = x + xmax + gap_mm
    return xs


def clip_regions(origins: list[tuple[float, float]], bboxes_rel: list[tuple[float, float, float, float]],
                 margin_mm: float = CLIP_MARGIN_MM) -> list[tuple[float, float, float, float]]:
    """各詳細図の切り抜く範囲（モデル mm の絶対座標）."""
    return [(ox + b[0] - margin_mm, oy + b[1] - margin_mm, ox + b[2] + margin_mm, oy + b[3] + margin_mm)
            for (ox, oy), b in zip(origins, bboxes_rel)]


def drawing_ratio(scale: int, source_scale: int = SOURCE_SCALE) -> float:
    """CreateDrawings の scale（元の図の縮尺に対する比率）。1/100 の平面を 1/20 で置くなら 5."""
    return source_scale / scale


@dataclass
class DetailSheet:
    layout_name: str = ""
    layout_item_guid: str = ""
    drawing_guids: list[str] = field(default_factory=list)
    scale: int = 20
    notes: list[str] = field(default_factory=list)


def _bboxes(client, elements: list[dict]) -> list[Optional[tuple[float, float, float, float]]]:
    """要素の平面の外形（mm、絶対）。測れなければ None."""
    resp = client.post("API.Get2DBoundingBoxes", {"elements": elements})
    out = []
    for item in resp.get("boundingBoxes2D", []):
        b = item.get("boundingBox2D")
        out.append((b["xMin"] * 1000, b["yMin"] * 1000, b["xMax"] * 1000, b["yMax"] * 1000) if b else None)
    return out


def _origins(client, elements: list[dict]) -> list[tuple[float, float]]:
    out = []
    for d in client.get_details(elements):
        o = (d.get("details") or {}).get("origin") or {}
        out.append((float(o.get("x", 0)) * 1000, float(o.get("y", 0)) * 1000))
    return out


def respace_details(client, elements: list[dict], scale: int) -> tuple[list[tuple[float, float]], list[tuple]]:
    """detScale を入れ、外形を測って一列に詰め直す。戻り値は (各原点, 原点からの相対外形)."""
    for el in elements:
        client.set_gdl_parameters(el, {"detScale": int(scale)})
    origins = _origins(client, elements)
    boxes = _bboxes(client, elements)
    rel = []
    for (ox, oy), b in zip(origins, boxes):
        if b is None:
            b = (ox - 1000, oy - 3000, ox + 3000, oy + 1000)     # 測れないときは大きめに見込む
        rel.append((b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy))
    if not origins:
        return [], []
    xs = row_origins(rel, origins[0][0] + rel[0][0])
    moves = [{"elementId": el["elementId"], "moveVector": {"x": (nx - ox) / 1000, "y": 0.0, "z": 0.0}}
             for el, nx, (ox, _oy) in zip(elements, xs, origins) if abs(nx - ox) > 1.0]
    if moves:
        client.tapir("MoveElements", {"elementsWithMoveVectors": moves})
    return [(x, oy) for x, (_ox, oy) in zip(xs, origins)], rel


def place_detail_sheet(client, details: list[dict], titles: list[str], prefix: str = "足場",
                       replace: bool = True, floor_index=None) -> DetailSheet:
    """詳細図の部品を詰め直し、レイアウト「<prefix> 足場詳細図」に1枚ずつ切り抜いて並べる."""
    out = DetailSheet(layout_name=detail_layout_name(prefix))
    if not details:
        return out
    activate_floor_plan(client)
    story, src_scale, src_note = plan_source(client, floor_index)
    if src_note:
        out.notes.append(src_note)
    if story is None:
        return out
    if replace:
        lb = _tree(client, "LayoutBook")
        _delete_items(client, [it["guid"] for it in walk_tree(lb)
                               if it["type"] == "LayoutItem" and it["name"] == out.layout_name])
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    lay = _create_layout(client, out.layout_name, subset, master)
    if not lay:
        out.notes.append("レイアウトを作れませんでした")
        return out
    out.layout_item_guid = lay
    paper, margins = _layout_paper_mm(client, lay)

    plan = None
    regions: list = []
    activate_floor_plan(client)
    for scale in DETAIL_SCALES:
        origins, rel = respace_details(client, details, scale)
        regions = clip_regions(origins, rel)
        boxes = [(r[2] - r[0], r[3] - r[1]) for r in regions]
        plan = arrange_boxes(boxes, paper, margins, scales=(scale,), max_scale=scale)
        if plan is not None:
            break
    if plan is None:
        out.notes.append(f"詳細図が用紙に収まりません（1/{DETAIL_SCALES[-1]} でも）。部品は平面に残しています")
        activate_floor_plan(client)
        return out
    out.scale = plan.scale

    db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": lay}}]})
    dbid = db["databases"][0]["databaseId"]
    data = []
    for region, pos, title in zip(regions, plan.positions_mm, titles):
        clip, position = clipped_drawing_geometry(region, plan.scale, pos, src_scale)
        data.append({"navigatorItemId": {"guid": story["guid"]}, "layoutDatabaseId": dbid, "position": position,
                     "clipPolygon": clip, "scale": drawing_ratio(plan.scale, src_scale), "drawingScale": float(plan.scale),
                     "name": f"{title} 1/{plan.scale}"})
    r = client.tapir("CreateDrawings", {"drawingsData": data})
    els = [e for e in (r.get("elements") or []) if "elementId" in e]
    out.drawing_guids = [e["elementId"]["guid"] for e in els]
    bad = [e for e in (r.get("elements") or []) if "elementId" not in e]
    if bad:
        out.notes.append(f"置けなかった図面 {len(bad)}枚: {bad[0].get('error', bad[0])}")
    if els:
        try:
            client.tapir("UpdateDrawings", {"elements": els})
        except Exception:
            pass
    activate_floor_plan(client)
    return out
