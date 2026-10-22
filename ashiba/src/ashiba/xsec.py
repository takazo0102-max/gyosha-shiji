"""足場断面図を2Dの作図の形で描く（ashiba_xsec 部品。利用者の指定 2026-10-23: 案1）.

Archicad の断面図ビューポイントで3Dを切ると、スパンの中ほどの切り口しか写らず、手で書く断面図
（足場を横から見た形: 支柱2本・腕木・踏板の切り口・手すりの丸・幅木・壁つなぎ・朝顔・ジャッキ・躯体）
にならない。面ごとにこの形を描く2Dの部品（ashiba_xsec）を、平面図の建物の下の行に置き、詳細図と同じく
切り抜いた平面の図面をレイアウト「<工事名> 足場断面図 A-A」などへ 1/50 で貼る。

どの面を描くかは断面 A-A・B-B（cross_sections.choose_cuts）と同じで、名前も「A-A 南面」など。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import ScaffoldModel

XSEC_OBJECT = "ashiba_xsec"
XSEC_SCALE = 50
XSEC_OFFSET_MM = -80000.0     # 平面の建物の左下から、この下の行に置く（詳細図の行 -20000 より下）
PITCH_EXTRA_MM = 4000.0       # 隣の断面との間（幅に足す）


@dataclass
class XsecItem:
    face_name: str               # 「A-A 南面」
    pair: str                    # 「A-A」
    edge_index: int
    params: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return f"{self.face_name} 足場断面図"

    def width_mm(self) -> float:
        """部品の横の大きさの見積り（寸法線の外 4.6m ＋ 足場 ＋ 離れ ＋ 躯体側 2m ＋ 名前）."""
        return (4600.0 + float(self.params.get("rowW", 0.9)) * 1000.0 + float(self.params.get("standoff", 0.3)) * 1000.0
                + 2500.0 + 2000.0)


def _mm_list(vals) -> str:
    return ",".join(f"{float(v):.0f}" for v in vals)


def xsec_params(model: ScaffoldModel, edge_index: int, title: str, stories_mm: Optional[list[float]] = None,
                det_scale: int = XSEC_SCALE) -> dict:
    """面1つの断面の部品のパラメータ（長さは m、一覧は mm のカンマ区切り）."""
    from .model import GUARD_RAIL_ADVANCE

    ep = next(e for e in model.plan.edges if e.edge_index == edge_index)
    e = model.elevation_of(edge_index)
    ws = list(model.deck_widths_in_use) or [0]
    asa = model.config.asagao
    ser = "W" if model.master.is_frame else ("T" if model.master.is_tube else "K")
    bldg = float(getattr(model, "building_height_mm", 0.0) or 0.0)
    if bldg <= 0.0:
        bldg = max([0.0] + [float(h) for h in e.level_heights[:-1]])
    ties = sorted({int(t.height_mm) for t in model.wall_ties if t.edge_index == edge_index})
    floors = sorted({float(s) for s in (stories_mm or []) if 1.0 < float(s) < bldg - 1.0})
    return {
        "ttlTxt": title,
        "serType": ser,
        "rowW": float(model.post_row_spacing_mm) / 1000.0,
        "standoff": float(ep.standoff) / 1000.0,
        "jackOut": float(e.jack_extension) / 1000.0,
        "postList": _mm_list(e.posts),
        "lvList": _mm_list(e.level_heights),
        "negaH": float(e.first_ledger_height) / 1000.0 if e.has_negarami else 0.0,
        "railH": float(model.guard_rail_height_mm) / 1000.0,
        "midH": float(model.midrail_height_mm) / 1000.0,
        "railAdv": 1 if (model.config.guard_rail_type == GUARD_RAIL_ADVANCE and not model.master.is_frame) else 0,
        "railIn": 1 if (model.config.inner_guard_rail and not model.master.is_frame
                        and model.post_row_spacing_mm > 0) else 0,
        "toeOn": 1 if model.config.has_toe_board else 0,
        "deckW1": float(ws[0]) / 1000.0,
        "deckW2": float(ws[1]) / 1000.0 if len(ws) > 1 else 0.0,
        "tieHList": _mm_list(ties),
        "asaList": _mm_list(model.asagao_heights()),
        "asaProj": float(getattr(asa, "projection_mm", 2000.0) or 2000.0) / 1000.0 if asa else 2.0,
        "asaAng": float(getattr(asa, "angle_deg", 20.0) or 20.0) if asa else 20.0,
        "bldgH": bldg / 1000.0,
        "flList": _mm_list(floors),
        "detScale": int(det_scale),
    }


def xsec_items(model: ScaffoldModel, stair_plan=None, openings=None, platforms=None,
               stories_mm: Optional[list[float]] = None) -> list[XsecItem]:
    """断面 A-A・B-B が横切る面ごとの断面（A-A の2面、B-B の2面）."""
    from .cross_sections import cross_section_specs, split_cross_specs

    out = []
    for sp in split_cross_specs(model, cross_section_specs(model, "x", stair_plan, openings, platforms)):
        pair = sp.face_name.split(" ")[0]
        it = XsecItem(sp.face_name, pair, sp.edge_index)
        it.params = xsec_params(model, sp.edge_index, it.title, stories_mm)
        out.append(it)
    return out


def xsec_origins(items: list[XsecItem], origin_mm: tuple[float, float]) -> list[tuple[float, float]]:
    """部品を左から並べる原点（内側建地の芯の GL）。部品の左は寸法線の外 4.6m ＋ 足場の幅まで張り出す."""
    out, x = [], float(origin_mm[0])
    for it in items:
        left = 4600.0 + float(it.params["rowW"]) * 1000.0
        out.append((x + left, float(origin_mm[1])))
        x += it.width_mm() + PITCH_EXTRA_MM
    return out


@dataclass
class XsecSheets:
    layouts: list[str] = field(default_factory=list)
    drawing_guids: list[str] = field(default_factory=list)
    scale: int = XSEC_SCALE
    notes: list[str] = field(default_factory=list)


def place_xsec(client, model: ScaffoldModel, part_name: str, origin_mm: tuple[float, float], prefix: str,
               stair_plan=None, openings=None, platforms=None, stories_mm: Optional[list[float]] = None,
               floor_index=None) -> tuple[list[dict], XsecSheets]:
    """面ごとの断面の部品を平面の下の行に置き、A-A・B-B ごとのレイアウトへ 1/50 で切り抜いて貼る."""
    from .cross_sections import cross_sheet_name
    from .detail_sheet import _bboxes, _origins, clip_regions, drawing_ratio
    from .elevation_sections import (
        _create_layout, _delete_items, _layout_paper_mm, _tree, activate_floor_plan, arrange_boxes,
        clipped_drawing_geometry, create_clipped_drawings, ensure_subset, pick_master_layout, plan_source, walk_tree,
    )

    sheets = XsecSheets()
    items = xsec_items(model, stair_plan, openings, platforms, stories_mm)
    if not items:
        return [], sheets
    activate_floor_plan(client)
    placed: list[dict] = []
    for it, (ox, oy) in zip(items, xsec_origins(items, origin_mm)):
        el = client.create_object(part_name, ox, oy)
        placed.append(el)
        client.set_gdl_parameters(el, it.params, part_name)
    story, src_scale, src_note = plan_source(client, floor_index)
    if src_note:
        sheets.notes.append(src_note)
    if story is None:
        return placed, sheets
    origins = _origins(client, placed)
    boxes = _bboxes(client, placed)
    rel = []
    for (ox, oy), b, it in zip(origins, boxes, items):
        if b is None:
            b = (ox - 4600 - it.params["rowW"] * 1000, oy - 1500, ox + 6000, oy + 30000)
        rel.append((b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy))
    regions = clip_regions(origins, rel)
    names = {it.pair: cross_sheet_name(prefix, it.pair) for it in items}
    lb = _tree(client, "LayoutBook")
    _delete_items(client, [x["guid"] for x in walk_tree(lb) if x["type"] == "LayoutItem" and x["name"] in names.values()])
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([x for x in walk_tree(lb) if x["type"] and "Master" in x["type"]])
    for pair, name in names.items():
        idx = [i for i, it in enumerate(items) if it.pair == pair]
        lay = _create_layout(client, name, subset, master)
        if not lay:
            sheets.notes.append(f"レイアウト「{name}」を作れませんでした")
            continue
        paper, margins = _layout_paper_mm(client, lay)
        grp = [regions[i] for i in idx]
        plan = arrange_boxes([(r[2] - r[0], r[3] - r[1]) for r in grp], paper, margins,
                             scales=(XSEC_SCALE,), max_scale=XSEC_SCALE)
        scale = XSEC_SCALE
        if plan is None:
            plan = arrange_boxes([(r[2] - r[0], r[3] - r[1]) for r in grp], paper, margins, scales=(100, 200))
            if plan is None:
                sheets.notes.append(f"{pair} の断面図が用紙に収まりません（部品は平面に残しています）")
                continue
            scale = plan.scale
            sheets.notes.append(f"{pair} の断面図は 1/{XSEC_SCALE} で用紙に入らないので 1/{scale} で置きました")
            for i in idx:
                client.set_gdl_parameters(placed[i], {"detScale": int(scale)}, part_name)
        db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": lay}}]})
        dbid = db["databases"][0]["databaseId"]
        data = []
        for i, pos in zip(idx, plan.positions_mm):
            clip, position = clipped_drawing_geometry(regions[i], scale, pos, src_scale)
            data.append({"navigatorItemId": {"guid": story["guid"]}, "layoutDatabaseId": dbid, "position": position,
                         "clipPolygon": clip, "scale": drawing_ratio(scale, src_scale), "drawingScale": float(scale),
                         "name": f"{items[i].title} 1/{scale}"})
        made = create_clipped_drawings(client, data, lay)
        els = [x for x in made if "elementId" in x]
        sheets.drawing_guids += [x["elementId"]["guid"] for x in els]
        bad = [x for x in made if "elementId" not in x]
        if bad:
            sheets.notes.append(f"置けなかった図面 {len(bad)}枚: {bad[0].get('error', bad[0])}")
        if els:
            try:
                client.tapir("UpdateDrawings", {"elements": els})
            except Exception:
                pass
        sheets.layouts.append(name)
        sheets.scale = max(sheets.scale, scale)
    activate_floor_plan(client)
    return placed, sheets
