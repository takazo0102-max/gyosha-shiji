"""足場断面図（建物を横切る断面 A-A・B-B）.

利用者の指定（2026-10-21）: 断面図も必要。足場の組立図（平面・立面・断面）の断面にあたる図で、
躯体からの離れ・足場の幅・根がらみと各作業床の高さ・足場高さを、足場を横から切って示す。

立面図と同じく Archicad の断面図ビューポイントで作り、サブセット「仮設足場」のレイアウト
「<工事名> 足場断面図」に図面として置く（実際のモデルを切るので、躯体の壁・床も一緒に出る）。

- A-A: いちばん長い面に直交して建物を横切る。B-B: それに直交（A-A と平行な面を横切る）。
- 切る位置は面のスパンの中央（支柱の位置で切ると支柱が切断面に重なって読みにくい）。
  階段室・開口部・荷受けステージのスパンは避ける（避けられなければ中央に近いスパン）。
- 注記（寸法・高さ）は断面図ウィンドウに線と文字で書く（立面図と同じ書き方）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .elevation_sections import (
    LEVEL_DIM_OFFSET_M, SectionNotes, SectionSpec, _tick, label_text_width_m, section_x,
)
from .model import ScaffoldModel

CROSS_SCALES = (50, 100, 200)   # 断面は 1/50 から（離れ・幅・手すりの高さが読める）
CLEAR_MM = 3500.0          # 外側建地列から切断線の端まで（立面図と同じ余裕）
FAR_EXTRA_MM = 1500.0      # 反対側の面の離れ＋幅を越える分
SECTION_LETTERS = ("A", "B", "C", "D")
DIM_BELOW_M = -0.8         # 離れ・幅の寸法線（GL の下）
HEIGHT_DIM_EXTRA_M = 2.2   # 高さの寸法線から足場高さの寸法線まで


def cross_section_name(prefix: str, letter: str) -> str:
    return f"{prefix} 足場断面 {letter}-{letter}"


def cross_layout_name(prefix: str) -> str:
    return f"{prefix} 足場断面図"


@dataclass
class CrossCut:
    letter: str
    point_mm: tuple[float, float]     # 切る点（面の内側建地列の上、スパンの中央）
    normal: tuple[float, float]       # 面の外向き（切断線の向きは -normal）
    edge_index: int


def _unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _avoid_ranges(model: ScaffoldModel, edge_index: int, stair_plan=None, openings=None,
                  platforms=None) -> list[tuple[float, float]]:
    from .platforms import platform_ranges

    out = list(platform_ranges(model, platforms).get(edge_index, []))
    for t in getattr(stair_plan, "towers", []) or []:
        if t.edge_index == edge_index:
            out.append((t.start_mm, t.start_mm + t.length_mm))
    for o in getattr(openings, "openings", []) or []:
        if o.edge_index == edge_index:
            out.append((o.start_mm, o.end_mm))
    return out


def _cut_on_edge(ep, avoid) -> float:
    """面の始点からの距離（mm）: 中央にいちばん近いスパンの中央。避ける区間に掛かるスパンは後回し."""
    xs, x = [], 0.0
    for s in ep.spans:
        xs.append((x, x + s))
        x += s
    mid = x / 2.0
    cands = []
    for a, b in xs:
        bad = any(a < e - 1.0 and b > s + 1.0 for s, e in avoid)
        cands.append((bad, abs((a + b) / 2.0 - mid), (a + b) / 2.0))
    cands.sort()
    return cands[0][2] if cands else mid


def choose_cuts(model: ScaffoldModel, stair_plan=None, openings=None, platforms=None) -> list[CrossCut]:
    """A-A（いちばん長い面に直交）と B-B（それに直交する向きでいちばん長い面に直交）."""
    edges = [e for e in model.plan.edges if e.spans]
    if not edges:
        return []

    def length(e):
        return sum(e.spans)

    def direction(e):
        (sx, sy), (ex, ey) = e.start_post, e.end_post
        return _unit(ex - sx, ey - sy)

    first = max(edges, key=length)
    u0 = direction(first)
    # B-B は A-A の面とおおむね直交する面（|cos| < 0.5）のうち最長
    others = [e for e in edges if abs(direction(e)[0] * u0[0] + direction(e)[1] * u0[1]) < 0.5]
    picks = [first] + ([max(others, key=length)] if others else [])
    cuts = []
    for letter, ep in zip(SECTION_LETTERS, picks):
        ux, uy = direction(ep)
        d = _cut_on_edge(ep, _avoid_ranges(model, ep.edge_index, stair_plan, openings, platforms))
        sx, sy = ep.start_post
        cuts.append(CrossCut(letter, (sx + ux * d, sy + uy * d), (uy, -ux), ep.edge_index))
    return cuts


def cross_section_specs(model: ScaffoldModel, prefix: str = "足場", stair_plan=None, openings=None,
                        platforms=None) -> list[SectionSpec]:
    """切断線（外側から建物を横切って反対側の足場の外まで）。奥行きは立面図と同じく無限扱い."""
    verts = [(float(x), float(y)) for x, y in model.plan.outline.vertices]
    row = float(model.post_row_spacing_mm)
    out = []
    for c in choose_cuts(model, stair_plan, openings, platforms):
        (px, py), (nx, ny) = c.point_mm, c.normal
        far = max(((px - vx) * nx + (py - vy) * ny) for vx, vy in verts) if verts else 0.0
        start = (px + nx * (row + CLEAR_MM), py + ny * (row + CLEAR_MM))
        reach = far + row + FAR_EXTRA_MM + CLEAR_MM
        end = (px - nx * reach, py - ny * reach)
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        out.append(SectionSpec(f"{c.letter}-{c.letter}", cross_section_name(prefix, c.letter), start, end,
                               1000.0, length, c.edge_index))
    return out


def _segment_hit(p0, p1, q0, q1) -> Optional[float]:
    """線分 p0→p1 と q0→q1 の交点の q 側のパラメータ（0..1）。交わらなければ None."""
    rx, ry = p1[0] - p0[0], p1[1] - p0[1]
    sx, sy = q1[0] - q0[0], q1[1] - q0[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    qpx, qpy = q0[0] - p0[0], q0[1] - p0[1]
    t = (qpx * sy - qpy * sx) / den
    u = (qpx * ry - qpy * rx) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return u
    return None


@dataclass
class CutFace:
    edge_index: int
    face_name: str
    x_wall: float      # 断面座標（m）: 躯体面
    x_in: float        # 内側建地
    x_out: float       # 外側建地
    standoff_mm: float


def cut_faces(model: ScaffoldModel, spec: SectionSpec) -> list[CutFace]:
    """切断線が横切る面（足場の内側建地列との交点）と、躯体・内側・外側建地の断面座標."""
    row = float(model.post_row_spacing_mm)
    out = []
    for ep in model.plan.edges:
        u = _segment_hit(spec.start_mm, spec.end_mm, ep.start_post, ep.end_post)
        if u is None:
            continue
        (sx, sy), (ex, ey) = ep.start_post, ep.end_post
        ux, uy = _unit(ex - sx, ey - sy)
        ox, oy = uy, -ux
        p = (sx + (ex - sx) * u, sy + (ey - sy) * u)
        so = float(ep.standoff)
        out.append(CutFace(ep.edge_index, model.face_name(ep.edge_index),
                           section_x(spec, (p[0] - ox * so, p[1] - oy * so)), section_x(spec, p),
                           section_x(spec, (p[0] + ox * row, p[1] + oy * row)), so))
    return out


def _left_text(x: float, y: float, text: str, side: float, text_scale: float) -> dict:
    """寸法線の外側（side=+1 は右、-1 は左）に置く文字。左側は文字幅を見積もって左寄せで置く."""
    if side >= 0:
        return {"x": x + 0.25, "y": y + 0.05, "text": text, "just": "Left"}
    return {"x": x - 0.25 - label_text_width_m(text, 0.25 * text_scale / 100.0), "y": y + 0.05,
            "text": text, "just": "Left"}


def cross_section_annotations(model: ScaffoldModel, spec: SectionSpec, terrain=None,
                              text_scale: float = 100.0, stair_plan=None) -> SectionNotes:
    """断面に置く注記: GL・離れと幅の寸法・根がらみと各作業床の高さ・足場高さ・面の名前・見出し."""
    out = SectionNotes()
    faces = cut_faces(model, spec)
    if not faces:
        return out
    xs = [v for f in faces for v in (f.x_wall, f.x_in, f.x_out)]
    lo, hi = min(xs), max(xs)
    out.lines.append([(lo - 2.0, 0.0), (hi + 2.0, 0.0)])
    tall = 0.0
    for f in faces:
        e = model.elevation_of(f.edge_index)
        top = float(e.total_height) / 1000.0
        tall = max(tall, top)
        side = 1.0 if f.x_out >= f.x_in else -1.0
        # 離れ・幅（GL の下に横の寸法線。躯体面・内側建地・外側建地に目盛り）
        y = DIM_BELOW_M
        out.lines.append([(f.x_wall, y), (f.x_out, y)])
        for x in (f.x_wall, f.x_in, f.x_out):
            out.lines.append(_tick(x, y))
            out.lines.append([(x, -0.1), (x, y - 0.15)])
        row_mm = abs(f.x_out - f.x_in) * 1000.0
        out.texts.append({"x": (f.x_wall + f.x_in) / 2.0, "y": y + 0.12, "text": f"離れ{f.standoff_mm:.0f}",
                          "just": "Center"})
        out.texts.append({"x": (f.x_in + f.x_out) / 2.0, "y": y - 0.45, "text": f"{row_mm:.0f}", "just": "Center"})
        # 高さ（外側に縦の寸法線。GL・根がらみ・各作業床・天端に目盛り、高さを外側、間隔を内側）。
        # 外付けの階段室がある面は3列目のさらに外から（寸法の文字が階段に重なっていた）
        ext = 0.0
        if getattr(stair_plan, "outside", False) and any(
                t.edge_index == f.edge_index for t in getattr(stair_plan, "towers", []) or []):
            ext = float(model.post_row_spacing_mm) / 1000.0
        xc = f.x_out + side * (ext + LEVEL_DIM_OFFSET_M)
        marks = [("GL", 0.0), ("根がらみ", float(e.first_ledger_height))] + [
            (f"{i}層", float(h)) for i, h in enumerate(e.level_heights, start=1)] + [("天端", top * 1000.0)]
        out.lines.append([(xc, 0.0), (xc, top)])
        prev = None
        for label, h in marks:
            yy = h / 1000.0
            out.lines.append(_tick(xc, yy))
            out.lines.append([(f.x_out + side * 0.1, yy), (xc - side * 0.15, yy)])
            if label not in ("GL", "天端"):
                out.texts.append(_left_text(xc, yy, f"{label} +{h:.0f}", side, text_scale))
            if prev is not None and h - prev > 1.0:
                gap = f"{h - prev:.0f}"
                gx = xc - side * 0.15
                if side >= 0:
                    gx -= label_text_width_m(gap, 0.25 * text_scale / 100.0)
                out.texts.append({"x": gx, "y": (prev + h) / 2000.0, "text": gap, "just": "Left", "gap": True})
            prev = h
        xd = xc + side * HEIGHT_DIM_EXTRA_M
        out.lines.append([(xd, 0.0), (xd, top)])
        out.lines.append(_tick(xd, 0.0))
        out.lines.append(_tick(xd, top))
        out.texts.append(_left_text(xd, top / 2.0, f"足場高さ {top * 1000:.0f}", side, text_scale))
        # 面の名前（足場の上）
        out.texts.append({"x": (f.x_in + f.x_out) / 2.0, "y": top + 0.6, "text": f.face_name, "just": "Center"})
    from .master import SERIES_LABELS

    kind = SERIES_LABELS.get(model.master.series_id, model.master.series_id)
    out.texts.append({"x": lo, "y": tall + 1.8,
                      "text": f"{spec.face_name} 足場断面図　{kind}・階高 {model.master.floor_height}・"
                              f"幅 {model.post_row_spacing_mm:.0f}", "just": "Left"})
    out.texts.append({"x": lo, "y": -1.9, "text": "GL±0（離れは躯体面から内側建地の芯まで）", "just": "Left"})
    base = float(getattr(model, "base_height_mm", 0.0) or 0.0) / 1000.0
    if base:
        out.texts = [{**t, "y": t["y"] + base} for t in out.texts]
        out.lines = [[(x, y + base) for x, y in pts] for pts in out.lines]
    return out


def place_cross_sections(model: ScaffoldModel, client, prefix: str = "足場", previous: Optional[dict] = None,
                         terrain=None, stair_plan=None, openings=None, platforms=None, on_sections=None) -> list:
    """断面 A-A・B-B を作り、注記を書いて、レイアウト「<prefix> 足場断面図」に1枚で置く.

    previous は前回の控え {断面名: 要素GUID}（立面図と同じ控え elevation_sections.json）。再実行で置き換える。
    戻り値は立面図と同じ ElevationPlacement の並び（face_name に "A-A" など）。
    """
    from .elevation_sections import (
        ElevationPlacement, _place_on_one_sheet, _tree, activate_floor_plan, ensure_subset,
        find_items, open_section_window, pick_master_layout, remove_elevations, walk_tree, write_section_notes,
    )

    specs = cross_section_specs(model, prefix, stair_plan, openings, platforms)
    if not specs:
        return []
    activate_floor_plan(client)
    prev = previous or {}
    remove_elevations(client, [s.name for s in specs], [cross_layout_name(prefix)], [prev.get(s.name, "") for s in specs])
    resp = client.tapir("CreateSections", {"sectionsData": [
        {"startCoordinate": {"x": s.start_mm[0] / 1000.0, "y": s.start_mm[1] / 1000.0},
         "endCoordinate": {"x": s.end_mm[0] / 1000.0, "y": s.end_mm[1] / 1000.0},
         "depth": s.depth_mm / 1000.0, "name": s.name} for s in specs]})
    results = []
    for s, el in zip(specs, resp.get("elements", [])):
        pl = ElevationPlacement(face_name=s.face_name, section_name=s.name)
        if "elementId" in el:
            pl.section_guid = el["elementId"]["guid"]
        else:
            pl.notes.append(f"断面を作れませんでした（{el.get('error', {}).get('message', el)}）")
        results.append(pl)
    if on_sections is not None:
        try:
            on_sections(results)
        except Exception:
            pass
    pm = _tree(client, "ProjectMap")
    for pl in results:
        hit = find_items(pm, "SectionItem", name=pl.section_name)
        if hit:
            pl.section_item_guid = hit[-1]["guid"]
        else:
            pl.notes.append("プロジェクトマップに断面が見つかりません")
    from .elevation_sections import arrange_boxes

    est = arrange_boxes([(s.length_mm + 6000.0, float(model.scaffold_height_mm) + 7000.0) for s in specs],
                        (841.0, 594.0), scales=CROSS_SCALES)
    est_scale = float(est.scale) if est is not None else 200.0
    by_name = {s.name: s for s in specs}
    for pl in results:
        if not pl.section_item_guid or not pl.section_guid:
            continue
        try:
            if not open_section_window(client, pl.section_item_guid):
                pl.notes.append("断面図のウィンドウが開かなかったので注記を置きませんでした（もう一度実行してください）")
                continue
            write_section_notes(client, cross_section_annotations(model, by_name[pl.section_name], terrain,
                                                                  text_scale=est_scale, stair_plan=stair_plan))
        except Exception as ex:
            pl.notes.append(f"注記を置けませんでした: {ex}")
    activate_floor_plan(client)
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    ok = [pl for pl in results if pl.section_item_guid]
    if ok and not _place_on_one_sheet(client, model, prefix, [by_name[pl.section_name] for pl in ok], ok, subset,
                                      master, annotate=True, name=cross_layout_name(prefix), kind="足場断面図",
                                      scales=CROSS_SCALES):
        for pl in ok:
            pl.notes.append("断面図が1枚の用紙に収まらないのでレイアウトに置きませんでした（断面図はプロジェクトマップにあります）")
    activate_floor_plan(client)
    return results
