"""足場断面図（建物を横切る断面 A-A・B-B）.

利用者の指定（2026-10-21）: 断面図も必要。足場の組立図（平面・立面・断面）の断面にあたる図で、
躯体からの離れ・足場の幅・根がらみと各作業床の高さ・足場高さを、足場を横から切って示す。

立面図と同じく Archicad の断面図ビューポイントで作り、サブセット「仮設足場」のレイアウト
「<工事名> 足場断面図」に図面として置く（実際のモデルを切るので、躯体の壁・床も一緒に出る）。

- A-A: いちばん長い面に直交して建物を横切る。B-B: それに直交（A-A と平行な面を横切る）。
- 切る位置は面のスパンの中央（支柱の位置で切ると支柱が切断面に重なって読みにくい）。
  階段室・開口部・荷受けステージのスパンは避ける（避けられなければ中央に近いスパン）。
- 注記（寸法・高さ）は断面図ウィンドウに寸法と文字で書く（立面図と同じ書き方）。
- 詳細も読めるよう 1/50 で置く（利用者の指定 2026-10-23: 断面図は詳細もわかるようにするので1/50でおさまるように）。
  建物を横切る線のままでは 1/50 で用紙に入らないので、面ごとに切る（足場の外から躯体の内側少しまで。
  split_cross_specs）。A-A の2面で1枚、B-B の2面で1枚のレイアウトにする。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .elevation_sections import (
    LEVEL_DIM_OFFSET_M, SectionNotes, SectionSpec, _tick, draw_height_chains, label_text_width_m, section_x,
)
from .model import ScaffoldModel

CROSS_SCALES = (50, 100, 200)   # 断面は 1/50 から（離れ・幅・手すりの高さが読める）
PARALLEL_CLEAR_MM = 1500.0   # 切断線に平行な面の足場（離れ＋建地列）から切断線を離す
CLEAR_MM = 3500.0          # 外側建地列から切断線の端まで（立面図と同じ余裕）
FAR_EXTRA_MM = 1500.0      # 反対側の面の離れ＋幅を越える分
SECTION_LETTERS = ("A", "B", "C", "D")
DIM_BELOW_M = -0.8         # 離れ・幅の寸法線（GL の下）
# 面ごとの断面: 躯体面から建物の内側へ切る長さ。足場ラインは断面・立面で躯体面の 1m 奥に向こう側を隠す幕を
# 立てる（3d.gdl）ので、その手前で止める。2m 切っていたときは幕の切り口が縦の線になって断面図に出た
INSIDE_MM = 800.0
DETAIL_SCALE = 50          # 断面図の縮尺（詳細も読める）


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
    verts = [(float(x), float(y)) for x, y in model.plan.outline.vertices]
    clear = max((float(e.standoff) for e in edges), default=300.0) + float(model.post_row_spacing_mm) + PARALLEL_CLEAR_MM
    for letter, ep in zip(SECTION_LETTERS, picks):
        ux, uy = direction(ep)
        avoid = _avoid_ranges(model, ep.edge_index, stair_plan, openings, platforms)
        # 切断線に平行な外形の辺（入隅の面など）の足場に沿って切らない（L 字で B-B が入隅の北面の足場の上を
        # 通り、断面図がその面の足場を縦に切った姿になった）
        sx, sy = ep.start_post
        for i in range(len(verts)):
            (ax, ay), (bx, by) = verts[i], verts[(i + 1) % len(verts)]
            L = math.hypot(bx - ax, by - ay)
            if L < 1e-6 or abs(((bx - ax) * ux + (by - ay) * uy) / L) > 0.1:
                continue                                       # この面と直交する（切断線と平行な）辺だけ
            c = (ax - sx) * ux + (ay - sy) * uy
            avoid.append((c - clear, c + clear))
        d = _cut_on_edge(ep, avoid)
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


def split_cross_specs(model: ScaffoldModel, specs: list[SectionSpec]) -> list[SectionSpec]:
    """建物を横切る断面を面ごとに分ける（足場の外 CLEAR_MM から躯体の内側 INSIDE_MM まで、向きは元のまま）.
    face_name は「A-A 南面」、name は「<prefix> 足場断面 A-A 南面」."""
    return [s for s, _own in split_cross_specs_with_owner([(model,)], specs)]


def split_cross_specs_with_owner(owners, specs: list[SectionSpec]) -> list[tuple[SectionSpec, tuple]]:
    """split_cross_specs を面の組ごとの模型で（owners は (模型, …) の並び）→ [(面ごとの断面, その面の組)].

    面ごとに足場を替えた建物で、先頭の組の模型だけで分けると替えた面の断面図が出なかった。
    """
    out = []
    for sp in specs:
        ax = (sp.end_mm[0] - sp.start_mm[0]) / max(sp.length_mm, 1e-9)
        ay = (sp.end_mm[1] - sp.start_mm[1]) / max(sp.length_mm, 1e-9)
        s0 = section_x(sp, sp.start_mm)                         # 断面座標の始点（section_x は始点からではない）
        faces = sorted(((f, tuple(own)) for own in owners for f in cut_faces(own[0], sp)), key=lambda x: x[0].x_in)
        for f, own in faces:
            outer = 1.0 if f.x_out > f.x_wall else -1.0          # 断面座標で外側の向き
            a_m = f.x_out + outer * CLEAR_MM / 1000.0 - s0
            b_m = f.x_wall - outer * INSIDE_MM / 1000.0 - s0
            lo, hi = max(0.0, min(a_m, b_m)), min(sp.length_mm / 1000.0, max(a_m, b_m))
            st = (sp.start_mm[0] + ax * lo * 1000.0, sp.start_mm[1] + ay * lo * 1000.0)
            en = (sp.start_mm[0] + ax * hi * 1000.0, sp.start_mm[1] + ay * hi * 1000.0)
            out.append((SectionSpec(f"{sp.face_name} {f.face_name}", f"{sp.name} {f.face_name}", st, en,
                                    sp.depth_mm, (hi - lo) * 1000.0, f.edge_index), own))
    return out


def cross_sheet_name(prefix: str, letter_pair: str = "") -> str:
    """断面図のレイアウト名（A-A・B-B ごと）. letter_pair が空なら従来の1枚の名前."""
    return cross_layout_name(prefix) + (f" {letter_pair}" if letter_pair else "")


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


def cross_section_annotations(model: ScaffoldModel, spec: SectionSpec, terrain=None,
                              text_scale: float = 100.0, stair_plan=None) -> SectionNotes:
    """断面に置く注記: GL・離れと幅の寸法・段の高さ・支柱の高さ・足場の高さの寸法・面の名前・見出し."""
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
        if row_mm > 1.0:                              # 単管抱き足場は建地1列（幅の「0」は書かない）
            out.texts.append({"x": (f.x_in + f.x_out) / 2.0, "y": y - 0.45, "text": f"{row_mm:.0f}",
                              "just": "Center"})
        # 高さ（外側に縦の寸法線を3本: 段の高さ・支柱の高さ・足場の高さ。層の高さの文字は書かない）。
        # 外付けの階段室がある面は3列目のさらに外から（寸法の文字が階段に重なっていた）
        ext = 0.0
        if getattr(stair_plan, "outside", False) and any(
                t.edge_index == f.edge_index for t in getattr(stair_plan, "towers", []) or []):
            ext = float(model.post_row_spacing_mm) / 1000.0
        draw_height_chains(out, e, f.x_out + side * ext, f.x_out + side * (ext + LEVEL_DIM_OFFSET_M), side,
                           text_scale)
        # 面の名前（足場の上）
        out.texts.append({"x": (f.x_in + f.x_out) / 2.0, "y": top + 0.6, "text": f.face_name, "just": "Center"})
    from .master import SERIES_LABELS

    kind = SERIES_LABELS.get(model.master.series_id, model.master.series_id)
    out.texts.append({"x": lo, "y": tall + 1.8,
                      "text": f"{spec.face_name} 足場断面図　{kind}・階高 {model.master.floor_height}"
                              + (f"・幅 {model.post_row_spacing_mm:.0f}" if model.post_row_spacing_mm > 0 else ""),
                      "just": "Left"})
    out.texts.append({"x": lo, "y": -1.9, "text": "GL±0（離れは躯体面から内側建地の芯まで）", "just": "Left"})
    base = float(getattr(model, "base_height_mm", 0.0) or 0.0) / 1000.0
    if base:
        out = out.shifted(base)
    return out


def place_cross_sections(model: ScaffoldModel, client, prefix: str = "足場", previous: Optional[dict] = None,
                         terrain=None, stair_plan=None, openings=None, platforms=None, on_sections=None,
                         others=()) -> list:
    """断面 A-A・B-B を作り、注記を書いて、レイアウト「<prefix> 足場断面図」に1枚で置く.

    previous は前回の控え {断面名: 要素GUID}（立面図と同じ控え elevation_sections.json）。再実行で置き換える。
    戻り値は立面図と同じ ElevationPlacement の並び（face_name に "A-A" など）。
    others は面の組（face_forms）のほかの組の (模型, 階段, 地盤)。切断線は先頭の組で決め、横切る面はどの組の面も。
    """
    from .elevation_sections import (
        ElevationPlacement, _place_on_one_sheet, _tree, activate_floor_plan, ensure_subset,
        find_items, hide_section_markers, open_section_window, pick_master_layout, remove_elevations, walk_tree,
        write_section_notes,
    )

    full = cross_section_specs(model, prefix, stair_plan, openings, platforms)
    owned = split_cross_specs_with_owner([(model, stair_plan, terrain), *others], full)
    specs = [s for s, _own in owned]
    owner_of = {s.name: own for s, own in owned}
    if not specs:
        return []
    activate_floor_plan(client)
    prev = previous or {}
    # 前回の断面（横切る1本の頃の名前・面ごとの名前）とレイアウト（1枚・A-A ごと）を消す
    old_names = [s_.name for s_ in full] + [s_.name for s_ in specs]
    # 前回この工事で作って今回は作らない断面（面の組が変わって横切る面が変わった等）も控えから消す
    old_names += [n for n in prev if n.startswith(f"{prefix} 足場断面 ") and n not in old_names]
    remove_elevations(client, old_names,
                      [cross_layout_name(prefix)] + [cross_sheet_name(prefix, f"{c}-{c}") + k for c in SECTION_LETTERS
                                                     for k in ("", " 1", " 2", " 3", " 4")],
                      [prev.get(n, "") for n in old_names])
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
    # Archicad のマーカー（「S-01」）は隠し、足場平面図に切断線と A・B を書く（place_plan_sheet の cuts）
    note = hide_section_markers(client, [pl.section_guid for pl in results if pl.section_guid])
    if note and results:
        results[0].notes.append(note)
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
    est_scale = float(DETAIL_SCALE)                   # 文字の大きさは 1/50 の用紙で読める大きさ
    by_name = {s.name: s for s in specs}
    for pl in results:
        if not pl.section_item_guid or not pl.section_guid:
            continue
        try:
            if not open_section_window(client, pl.section_item_guid):
                pl.notes.append("断面図のウィンドウが開かなかったので注記を置きませんでした（もう一度実行してください）")
                continue
            om, osp, ot = owner_of[pl.section_name]
            write_section_notes(client, cross_section_annotations(om, by_name[pl.section_name], ot,
                                                                  text_scale=est_scale, stair_plan=osp))
        except Exception as ex:
            pl.notes.append(f"注記を置けませんでした: {ex}")
    activate_floor_plan(client)
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    ok = [pl for pl in results if pl.section_item_guid]
    # A-A の2面で1枚、B-B の2面で1枚（1/50）。2面で入らなければ面ごとに1枚（1/50）、それでも入らなければ縮尺を下げる
    groups: dict[str, list] = {}
    for pl in ok:
        groups.setdefault(pl.face_name.split(" ")[0], []).append(pl)
    # キープラン用の切断線（建物を横切る元の線）
    cuts_by = {s_.face_name: {"label": s_.face_name.split("-")[0], "start": s_.start_mm, "end": s_.end_mm} for s_ in full}
    for pair, pls in groups.items():
        name = cross_sheet_name(prefix, pair)
        sp = [by_name[pl.section_name] for pl in pls]
        cuts = [cuts_by[pair]] if pair in cuts_by else []
        if _place_on_one_sheet(client, model, prefix, sp, pls, subset, master, annotate=True, name=name,
                               kind="足場断面図", scales=(DETAIL_SCALE,), panel_kind="cross", cuts=cuts):
            continue
        # 入らなければ2面ずつ（L 字で B-B が3面を横切ると1面ずつ3枚になっていた）、それでも入らない組は1面ずつ
        rest, k = [], 0
        if len(pls) > 2:
            for g in range(0, len(pls), 2):
                pair2 = pls[g:g + 2]
                k += 1
                if len(pair2) == 2 and _place_on_one_sheet(
                        client, model, prefix, [by_name[pl.section_name] for pl in pair2], pair2, subset, master,
                        annotate=True, name=f"{name} {k}", kind="足場断面図", scales=(DETAIL_SCALE,),
                        panel_kind="cross", cuts=cuts):
                    continue
                k -= 1
                rest += pair2
        else:
            rest = pls
        for pl in rest:
            k += 1
            one = f"{name} {k}" if len(pls) > 1 else name
            if _place_on_one_sheet(client, model, prefix, [by_name[pl.section_name]], [pl], subset, master,
                                   annotate=True, name=one, kind="足場断面図", scales=(DETAIL_SCALE,),
                                   panel_kind="cross", cuts=cuts):
                continue
            if _place_on_one_sheet(client, model, prefix, [by_name[pl.section_name]], [pl], subset, master,
                                   annotate=True, name=one, kind="足場断面図", scales=CROSS_SCALES,
                                   panel_kind="cross", cuts=cuts):
                pl.notes.append(f"断面図 {pl.face_name} は 1/{DETAIL_SCALE} で用紙に入らないので縮尺を下げて置きました")
            else:
                pl.notes.append("断面図が用紙に収まらないのでレイアウトに置きませんでした（断面図はプロジェクトマップにあります）")
    activate_floor_plan(client)
    return results
