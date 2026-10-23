"""敷地境界線と足場の離れ（利用者の指定 2026-10-23: 建物と敷地境界線を作成して足場計画を繰り返してみて）.

足場の外は敷地境界線まで。境界を越える足場は組めない（道路側は道路占用の許可が要る）。面ごとに、足場の
外側建地列から外向きに敷地境界線までの距離（離れ）を測り、
- 越える（離れ < 0）            → NG「境界を越えます」
- 足場の外の作業・養生の余裕が無い（離れ < WARN_MM） → 要確認
- 朝顔（張り出し）が境界を越える → 要確認（道路側は道路占用、隣地側は隣地の承諾）
- 外付けの階段室が入らない      → NG（足場の中に組むか、面を替える）
を出す。外付け階段を自動で決めるときの「足場の外の空き」にも面ごとの離れを使う。

入力: site_boundary_mm: [[x, y], ...]（敷地境界線の閉じた多角形、躯体外形と同じ座標）、
      road_edges: [0, 2]（道路境界線の辺の番号。境界の i 番目の頂点から i+1 番目まで）。
Archicad からは、レイヤー名に「敷地」か「境界」を含む閉じたポリラインを拾う（名前に「道路」を含む
レイヤーのポリラインは、その辺を道路境界とみなす）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .model import ScaffoldModel

WARN_MM = 300.0            # これより狭いと足場の外の作業・養生（シート・朝顔）の余裕が無い
SAMPLE_PITCH_MM = 250.0
POST_R_MM = 25.0


@dataclass
class FaceClearance:
    edge_index: int
    face: str
    min_mm: float              # 外側建地の外面から敷地境界線までの最小（負なら越える）
    at_mm: float               # 最小になる位置（面の始点の支柱から）
    road: bool                 # その位置の境界が道路境界か
    over_from_mm: float = 0.0  # 越える区間（越えなければ 0, 0）
    over_to_mm: float = 0.0


def parse_boundary(spec: dict) -> tuple[list[tuple[float, float]], set[int]]:
    pts = [(float(p[0]), float(p[1])) for p in (spec.get("site_boundary_mm") or [])]
    if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1.0:
        pts = pts[:-1]
    roads = {int(i) for i in (spec.get("road_edges") or [])}
    return (pts if len(pts) >= 3 else []), roads


def _ray_hit(p, d, a, b) -> Optional[float]:
    """点 p から向き d（単位）の半直線と線分 a-b の交点までの距離（無ければ None）."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = d[0] * ey - d[1] * ex
    if abs(den) < 1e-12:
        return None
    qx, qy = a[0] - p[0], a[1] - p[1]
    t = (qx * ey - qy * ex) / den
    u = (qx * d[1] - qy * d[0]) / den
    if t >= -1e-6 and -1e-9 <= u <= 1 + 1e-9:
        return t
    return None


def face_clearances(model: ScaffoldModel, boundary: list[tuple[float, float]],
                    road_edges: Optional[set[int]] = None) -> list[FaceClearance]:
    """面ごとの、外側建地の外面から敷地境界線までの離れ（外向きに測る）."""
    if len(boundary) < 3:
        return []
    road_edges = road_edges or set()
    row = float(model.post_row_spacing_mm)
    segs = [(boundary[i], boundary[(i + 1) % len(boundary)], i) for i in range(len(boundary))]
    out: list[FaceClearance] = []
    for ep in model.plan.edges:
        (sx, sy), (ex, ey) = ep.start_post, ep.end_post
        L = math.hypot(ex - sx, ey - sy)
        if L < 1.0:
            continue
        ux, uy = (ex - sx) / L, (ey - sy) / L
        ox, oy = uy, -ux                     # 外向き（躯体の反対。躯体側が左手）
        n = max(2, int(L // SAMPLE_PITCH_MM) + 1)
        best = None
        over = []
        for k in range(n + 1):
            s = L * k / n
            p = (sx + ux * s + ox * row, sy + uy * s + oy * row)       # 外側建地の芯
            if not _inside(p, boundary):
                # 外側建地が境界の外に出ている: 越えた量＝いちばん近い境界の辺までの距離（＋支柱の半径）
                d, i = min((_seg_dist(p, a, b), i) for a, b, i in segs)
                c = -d - POST_R_MM
            else:
                hits = [(t, i) for a, b, i in segs if (t := _ray_hit(p, (ox, oy), a, b)) is not None]
                if not hits:
                    continue
                t, i = min(hits)
                c = t - POST_R_MM
            if best is None or c < best[0]:
                best = (c, s, i in road_edges)
            if c < 0:
                over.append(s)
        if best is None:
            continue
        out.append(FaceClearance(ep.edge_index, model.face_name(ep.edge_index), best[0], best[1], best[2],
                                 min(over) if over else 0.0, max(over) if over else 0.0))
    return out


def boundary_issues(model: ScaffoldModel, clearances: list[FaceClearance], stair_plan=None) -> list:
    """離れから NG・要確認（conflicts.ConflictIssue の形）."""
    from .conflicts import ConflictIssue

    out = []
    basis = "敷地境界（民法234条・道路法32条の道路占用）"
    asg = getattr(model.config, "asagao", None)
    asa_proj = float(getattr(asg, "projection_mm", 0.0) or 0.0) if model.asagao_heights() else 0.0
    towers = list(getattr(stair_plan, "towers", []) or [])
    outside = bool(getattr(stair_plan, "outside", False))
    for c in clearances:
        side = "道路境界" if c.road else "隣地境界"
        if c.min_mm < 0:
            out.append(ConflictIssue(
                "足場×敷地境界", "NG",
                f"{c.face}: 足場の外側建地が{side}線を最大 {-c.min_mm:.0f}mm 越えます"
                f"（面の始点から {c.over_from_mm:.0f}〜{c.over_to_mm:.0f}mm）。離れを詰める・幅を狭める・"
                f"一側足場にする{'・道路占用の許可を取る' if c.road else ''}", basis))
            continue
        if c.min_mm < WARN_MM:
            out.append(ConflictIssue(
                "足場×敷地境界", "WARN",
                f"{c.face}: 足場の外から{side}線まで {c.min_mm:.0f}mm しかありません（養生シート・作業の余裕に注意）",
                basis))
        if asa_proj > 0 and c.min_mm < asa_proj:
            out.append(ConflictIssue(
                "朝顔×敷地境界", "WARN",
                f"{c.face}: 朝顔の張り出し {asa_proj:.0f}mm が{side}線を越えます（境界まで {c.min_mm:.0f}mm）。"
                + ("道路占用の許可が要ります" if c.road else "隣地の承諾を取るか、張り出しの短い防護棚にします"),
                basis))
        if outside and any(t.edge_index == c.edge_index for t in towers):
            need = float(model.post_row_spacing_mm) + 100.0
            if c.min_mm < need:
                out.append(ConflictIssue(
                    "外付け階段×敷地境界", "NG",
                    f"{c.face}: 外付けの階段室（{need:.0f}mm）が{side}線まで {c.min_mm:.0f}mm に入りません。"
                    "足場の中に組むか、ほかの面にします", basis))
    return out


def _inside(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def _seg_dist(p, a, b) -> float:
    ex, ey = b[0] - a[0], b[1] - a[1]
    L2 = ex * ex + ey * ey or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / L2))
    return math.hypot(p[0] - a[0] - t * ex, p[1] - a[1] - t * ey)


def pick_boundary(polylines: list[dict], outline_mm: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], set[int]]:
    """レイヤー名つきのポリライン [{"layer": 名前, "pts": [(x,y)mm...]}] から、建物を囲む敷地境界線と道路境界の辺.

    敷地境界: レイヤー名に「敷地」か「境界」を含み、閉じていて建物の重心を囲むもののうち最も小さいもの。
    道路境界: レイヤー名に「道路」を含むポリラインに沿う（中点が 200mm 以内の）境界の辺。
    """
    if not outline_mm:
        return [], set()
    cx = sum(p[0] for p in outline_mm) / len(outline_mm)
    cy = sum(p[1] for p in outline_mm) / len(outline_mm)
    best = None
    for pl in polylines:
        name = str(pl.get("layer") or "")
        if not any(k in name for k in ("敷地", "境界")):
            continue
        pts = [(float(x), float(y)) for x, y in pl.get("pts") or []]
        if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1.0:
            pts = pts[:-1]
        if len(pts) < 3 or not _inside((cx, cy), pts):
            continue
        area = abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                       for i in range(len(pts)))) / 2.0
        if best is None or area < best[0]:
            best = (area, pts)
    if best is None:
        return [], set()
    pts = best[1]
    roads: set[int] = set()
    road_lines = [[(float(x), float(y)) for x, y in pl.get("pts") or []] for pl in polylines
                  if "道路" in str(pl.get("layer") or "")]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        for rl in road_lines:
            if any(_seg_dist(mid, rl[j], rl[j + 1]) < 200.0 for j in range(len(rl) - 1)):
                roads.add(i)
    return pts, roads


def read_boundary_from_archicad(client, outline_mm) -> tuple[list[tuple[float, float]], set[int]]:
    """Archicad の平面のポリライン（レイヤー名に 敷地・境界・道路）から敷地境界線を拾う. 無ければ ([], set())."""
    try:
        layers = {int(a.get("index", -1)): str(a.get("name", ""))
                  for a in client.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])}
        want = {i for i, n in layers.items() if any(k in n for k in ("敷地", "境界", "道路"))}
        if not want:
            return [], set()
        els = client.tapir("GetElementsByType", {"elementType": "PolyLine"}).get("elements", [])
        if not els:
            return [], set()
        dets = client.get_details(els)
    except Exception:
        return [], set()
    polys = []
    for d in dets:
        li = int(d.get("layerIndex", -1))
        if li not in want:
            continue
        coords = (d.get("details") or {}).get("coordinates") or []
        polys.append({"layer": layers.get(li, ""), "pts": [(c["x"] * 1000.0, c["y"] * 1000.0) for c in coords]})
    return pick_boundary(polys, [tuple(p) for p in outline_mm])


# 境界を越える面を、張り出しの小さい形式に順に替える（一側足場は建地1列、単管抱き足場は建地の線の上だけ）
FIT_FORMS = ("本足場（狭い幅）", "一側足場", "単管抱き足場")


def _narrow_helps(spec: dict) -> bool:
    """本足場（狭い幅）にして細くなるか（指定の幅が系列のいちばん細い幅より広い）."""
    try:
        from .cli import narrow_width_mm, resolve_series_id
        from .master import load_master

        nw = narrow_width_mm(load_master(resolve_series_id(spec)))
    except Exception:  # noqa: BLE001 — 系列が引けなければ試さない
        return False
    w = spec.get("scaffold_width_mm")
    if nw is None:
        return False
    if w:
        return int(w) > nw
    # 幅の指定が無い: 既定の幅（系列の既定の床）がいちばん細い幅より広ければ
    from .cli import build_model

    try:
        m = build_model({k: v for k, v in spec.items() if k not in ("face_forms", "form_standoff")})
    except Exception:  # noqa: BLE001
        return False
    return m.config.scaffold_form == "本足場" and m.post_row_spacing_mm > nw


def _corner_side(fc: "FaceClearance", length_mm: float, tol_mm: float = 1.0) -> int:
    """越える区間が面の端の支柱1本だけなら、その端（始点 -1・終点 +1）。そうでなければ 0."""
    if fc.over_to_mm - fc.over_from_mm > tol_mm:
        return 0
    if fc.over_from_mm <= tol_mm:
        return -1
    if fc.over_to_mm >= length_mm - tol_mm:
        return 1
    return 0


def _adjacent_edge(model, edge_index: int, side: int) -> int:
    n = len(model.plan.outline.vertices)
    return (edge_index + side) % n


def _outline_face_name(model, edge_index: int) -> str:
    """外形の辺の面の名前（面の組で建てていない面でも。model.face_name は建てる面しか引けない）."""
    from .plan_solver import _compass

    raw = [_compass(e.outward) for e in model.plan.outline.edges]
    n = raw[edge_index]
    return f"{n}面(辺{edge_index})" if raw.count(n) > 1 else f"{n}面"


HUG_FLOOR_OUT_MM = 100.0      # 単管抱き足場の床の離れの線より外（法規#1 の必要幅と同じ）
MIN_FIT_STANDOFF_MM = 200.0   # 境界に収めるために詰める離れの下限


def _floor10(v: float) -> float:
    return math.floor(v / 10.0) * 10.0


def plan_within_boundary(spec: dict, max_rounds: int = 4) -> tuple[dict, list[str]]:
    """敷地境界を越える面の足場の形式を替えて解き直す（越えなくなるか、替える形式が無くなるまで）.

    いちばん小さい形式（単管抱き足場）でも越える面は、その形式の離れを詰める（境界まで −床の外側 100、
    下限 200）。どの組にも階段が入らない（全部の面が単管抱き足場など）ときは、はしごの箇所数を入れる。
    戻り値は (使う入力, 何をしたかの文)。境界が無い・越えない・fit_boundary=false なら入力のまま。
    """
    from .cli import solve_groups
    from .face_forms import format_face_forms, parse_face_forms

    if not spec.get("site_boundary_mm") or spec.get("fit_boundary") is False:
        return spec, []
    spec = dict(spec)
    notes: list[str] = []
    groups = []
    for rnd in range(1, max_rounds + 1):
        # ブラケットの面へ延ばす本足場の端（corner_joins）はブラケットの支柱の列までで、ブラケットが収まれば収まる。
        # 形式を選ぶ間は延ばさずに見る（延ばした端を本足場の面の越えと取ると、その面まで形式を替えてしまう）
        groups = solve_groups({**spec, "corner_joins": False})
        bad: dict[str, float] = {}           # 面 → 躯体から境界まで（越える区間の最小）
        corner: dict[str, str] = {}          # 角の支柱だけ越える面 → 角を決める隣の面
        for _label, r in groups:
            ng = {c.message.split(":", 1)[0] for c in r.conflicts if c.kind == "足場×敷地境界" and c.severity == "NG"}
            if not ng:
                continue
            bnd, roads = parse_boundary({"site_boundary_mm": r.model.site_boundary_mm})
            for fc in face_clearances(r.model, bnd, getattr(r.model, "site_road_edges", None) or roads):
                if fc.face in ng:
                    ep = next(e for e in r.model.plan.edges if e.edge_index == fc.edge_index)
                    wall = fc.min_mm + float(ep.standoff) + float(r.model.post_row_spacing_mm) + POST_R_MM
                    side = _corner_side(fc, float(sum(ep.spans)))
                    if side:
                        # 角の支柱だけが越える: 角の位置は隣の面の離れで決まる。この面の形式は替えない
                        corner[fc.face] = _outline_face_name(r.model, _adjacent_edge(r.model, fc.edge_index, side))
                    else:
                        bad[fc.face] = wall
        # 角だけ越える面の隣の面が越えていなければ、この面を替える（隣の面では直らない）
        for face, adj in corner.items():
            if adj not in bad:
                bad.setdefault(face, float("inf"))
        if not bad:
            break
        ff = parse_face_forms(spec.get("face_forms"))
        changed = False
        tighten: dict[str, float] = {}
        narrow_ok = _narrow_helps(spec)
        for face, wall_to_bnd in bad.items():
            cur = ff.get(face, "")
            i = FIT_FORMS.index(cur) + 1 if cur in FIT_FORMS else 0
            if i == 0 and not narrow_ok:
                i = 1                                   # 細くならないなら一側足場から
            if i < len(FIT_FORMS):
                ff[face] = FIT_FORMS[i]
                notes.append(f"{face}: 敷地境界を越えるので {FIT_FORMS[i]} にしました（{rnd}回目）")
                changed = True
            elif wall_to_bnd < float("inf"):
                tighten[face] = wall_to_bnd
        fs = dict(spec.get("form_standoff") or {})
        if tighten:
            form = FIT_FORMS[-1]
            cur_so = fs.get(form) or dict(spec.get("standoff") or {})
            cur_t = float(cur_so.get("target", 300))
            want = _floor10(min(tighten.values()) - HUG_FLOOR_OUT_MM)
            if want >= MIN_FIT_STANDOFF_MM and want < cur_t:
                fs[form] = {"target": want, "max": want, "min": min(want, float(cur_so.get("min", 250))),
                            "hard_min": min(want, float(cur_so.get("hard_min", 250)))}
                notes.append(f"{'・'.join(tighten)}: {form} でも敷地境界を越えるので、{form}の離れを {want:.0f}mm に"
                             f"詰めました（{rnd}回目）")
                changed = True
            else:
                notes.append(f"{'・'.join(tighten)}: {form} の離れを {MIN_FIT_STANDOFF_MM:.0f}mm まで詰めても敷地境界を"
                             "越えます（境界・形式を見直してください）")
        for face, adj in corner.items():
            if adj in bad:
                notes.append(f"{face}: 角の支柱だけが敷地境界を越えます（角の位置は{adj}の離れで決まるので、{adj}で直します）")
        if not changed:
            break
        spec["face_forms"] = format_face_forms(ff)
        if fs:
            spec["form_standoff"] = fs
    else:
        groups = solve_groups(spec)
    # 昇降設備: どの組にも階段が入らないなら、はしご（水平移動 30m 以内 → 外周 60m ごとに1箇所）
    from .stairs import DEFAULT_MAX_TRAVEL_MM, MIN_HEIGHT_FOR_STAIRS_MM

    if (groups and not spec.get("ladders") and spec.get("face_forms")
            and not any(getattr(r.stair_plan, "towers", None) for _l, r in groups)
            and max(r.model.scaffold_height_mm for _l, r in groups) > MIN_HEIGHT_FOR_STAIRS_MM):
        pts = [(float(p[0]), float(p[1])) for p in spec["outline_mm"]]
        per = sum(math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0], pts[(i + 1) % len(pts)][1] - pts[i][1])
                  for i in range(len(pts)))
        n = max(1, math.ceil(per / (2.0 * DEFAULT_MAX_TRAVEL_MM)))
        spec["ladders"] = n
        notes.append(f"どの面にも階段が入らないので、昇降設備ははしご {n}箇所（外周 {per / 1000:.1f}m・"
                     "水平移動 30m 以内。部材は別途手配）にしました")
    return spec, list(dict.fromkeys(notes))         # 回ごとに同じ文（角の支柱）が並ばないように
