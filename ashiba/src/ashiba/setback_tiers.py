"""大きなセットバック: 上の階の面の足場を、途中の屋根（下の階の屋根）の上から建てて本体の足場に繋ぐ.

利用者の指定（2026-10-24）「セットバックの時は途中の屋根から足場が繋がるようにする仕組みを作って」。奥行きが小さい
セットバック（setback_bracket_max_mm 以下）は今までどおり足場を上の屋根まで上げて内ブラケットでかわす（obstacles）。
それより奥へ下がった上の階は、本体の足場（面は下の屋根の高さで止まる）とは別に、上の階のスラブの外形で
「上段」の足場を解く:

- 上段の外形: 本体の外形より小さく、本体の中に収まるスラブの外形（同じ外形の床スラブは1つにまとめ、天端はいちばん高い値）
- 上段で建てる面: 外形の面のうち、面から外へ（奥行きの上限＋200）出た点がまだ本体の外形の中にある面（本体の足場から
  離れている面）。本体の面と重なる面は、本体の足場が上まで上がっているので建てない
- 立つ高さ: その面の外側（600）の点を含む、上段の天端より 1000 以上低いスラブ（途中の屋根）のいちばん高い天端。
  面ごとに違えば低い方
- 上段の端が、建てない面（本体の足場が通る面）に当たるところは、本体の足場に繋ぐ（_joined_ends。妻側の手すりを付けない）

上段は面の組（cli.solve_groups）の後ろに「上段」「上段（2）」… の組として足す。置くのは面の切替の組と同じ流れ。

上の階が外へ張り出す（拡張。利用者の指定 2026-10-24: 上階で拡張する仕組みと拡小する仕組みを作って）: 本体の外形を
含み、どこかの面で奥行きの上限より外へ出るスラブの外形（張り出した上の階）は、張り出しのいちばん下の床の天端から
「跳ね出しブラケット」（床スラブの縁から外へ持ち出す受け。足場ラインの haneD）の上に上段の足場を全周に建てる。
本体の足場はブラケットの下で止める（overhang_caps。面の軒高を ブラケット下端−手すり分 に抑え、その張り出しを
庇としてかわさない）。縮小（上の階が奥へ下がる）は上の setback の上段と、小さいものは内ブラケット。
"""

from __future__ import annotations

import math

from typing import Optional

from .obstacles import SETBACK_MAX_MM, _inside

PROBE_OUT_MM = 600.0         # 上段の面の外側（足場の下）の点
# これより外へ張り出した上の階は拡張（跳ね出し）にする。セットバックの奥行きの上限（内ブラケットでかわす 900）とは別:
# 上の階の壁の前に本体の足場を通すと、上の壁との離れ（最小 250）と下の壁との離れ（最大 350）が両立しない（実機
# 2026-10-25: 300出してるのにできてない拡張に。庇として離れ 384 で通し、上の壁まで 84 しかなかった）
OVERHANG_MIN_MM = 200.0
# 跳ね出しブラケットの形（利用者の指定 2026-10-25: ブラケットの向き反対じゃない？ コマンドでどっちか選べるようにして）:
#   方杖（既定）: 腕の先から方杖で下の階の壁へ突っ張る（写真の形）。張り出しの下の本体の足場は方杖の下端より下で止める
#   吊り: 腕の先から吊り材で上の階の壁へ吊る
HANE_TYPES = ("方杖", "吊り")


def hane_type(spec: dict) -> str:
    """拡張（張り出した上の階）の作り方 "方杖"（既定）・"吊り"・"なし"（跳ね出さず、本体の足場を上まで通して庇としてかわす）."""
    v = str(spec.get("hane_bracket_type") or "").strip()
    if v in ("なし", "跳ね出さない", "通す", "none"):
        return "なし"
    return "吊り" if v in ("吊り", "吊", "吊り材", "hang") else "方杖"


def brace_drop_mm(depth_mm: float, row_mm: float) -> float:
    """方杖の下端の、床の天端からの下がり mm（腕の長さ＝張り出し＋離れ＋建地列間隔＋先の分 の 0.6、600〜1800）."""
    return max(600.0, min(1800.0, 0.6 * (float(depth_mm) + float(row_mm) + 450.0)))


def overhang_depth_mm(big_mm, main_mm) -> float:
    """張り出した上の階の外形が本体の外形から外へ出ているいちばん大きい奥行き mm（張り出した面と、その下の本体の面の距離）."""
    from .geometry import build_outline

    big = build_outline([tuple(map(float, p)) for p in big_mm])
    main = build_outline([tuple(map(float, p)) for p in main_mm])
    best = 0.0
    for e in big.edges:
        for me in main.edges:
            if e.direction[0] * me.direction[0] + e.direction[1] * me.direction[1] < 0.99:
                continue
            d = (e.start[0] - me.start[0]) * me.outward[0] + (e.start[1] - me.start[1]) * me.outward[1]
            if 1.0 < d <= OVERHANG_MAX_MM:
                best = max(best, d)
    return best
OVERHANG_MAX_MM = 4500.0     # これより外へ広がる外形は張り出した上の階とみなさない（敷地・別棟）
HANE_DEPTH_MM = 600.0        # 跳ね出しブラケットの吊り材の上の取付プレートの高さ（床の天端からこれだけ上の壁）
HANE_BELOW_MM = 450.0        # ブラケットの床の天端から下へ出る寸法（横に流す H形鋼 150＋取付プレート 240＋あき。張り出しの下の本体の足場はこれより下）
HANE_GUARD_MM = 1100.0       # 本体の足場の天端（手すり分込み）をブラケットの下端からこれだけ下に収める
MIN_RISE_MM = 1000.0         # 途中の屋根から上段の天端までこれ以上
SAME_POLY_MM = 50.0          # 同じ外形とみなす頂点のずれ

# 上段の組に引き継がない条件（位置が本体の面からなので、上段では意味が変わる）
_DROP = ("outline_mm", "slabs", "face_forms", "form_standoff", "faces", "openings", "loading_stages", "hoists",
         "bracket_sections", "span_overrides", "face_eaves_mm", "base_height_mm", "eaves_height_mm",
         "building_height_mm", "scaffold_height_mm", "setbacks", "obstacles", "ground_points_mm", "member_edits",
         "corner_steps", "site_boundary_mm", "road_edges", "wall_ties_manual", "_overhang_faces", "_face_range")


def _area(poly) -> float:
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def _key(poly) -> tuple:
    return tuple(sorted((round(x / SAME_POLY_MM), round(y / SAME_POLY_MM)) for x, y in poly))


def _within(poly, outer, tol: float = 300.0) -> bool:
    """poly の頂点がすべて outer の中（縁から tol までの外れは許す）."""
    for x, y in poly:
        if _inside((x, y), outer):
            continue
        if not any(_inside((x + dx, y + dy), outer) for dx in (-tol, 0, tol) for dy in (-tol, 0, tol)):
            return False
    return True


def setback_tiers(outline_mm, slabs: list[dict], min_depth: float = SETBACK_MAX_MM) -> list[dict]:
    """本体の外形・スラブ → 上段 [{"outline_mm", "top_mm", "faces": [(辺番号, 立つ高さ)]}]（下から順）."""
    from .geometry import build_outline

    main = [tuple(map(float, p)) for p in outline_mm]
    a_main = abs(_area(main))
    groups: dict[tuple, tuple[list, list[float]]] = {}
    for s in slabs or []:
        poly = [tuple(map(float, p)) for p in s.get("polygon_mm") or []]
        if len(poly) < 3:
            continue
        k = _key(poly)
        groups.setdefault(k, (poly, []))[1].append(float(s.get("top_mm", 0.0)))
    polys = [([tuple(map(float, p)) for p in s["polygon_mm"]], float(s.get("top_mm", 0.0)))
             for s in slabs or [] if len(s.get("polygon_mm") or []) >= 3]
    out = []
    for poly, tops in groups.values():
        # 本体より小さい上の階の外形（一部が本体の外へ張り出していてもよい: 西へ張り出し東へ下がる階。実機 2026-10-25）。
        # 本体の中に1点も無い外形（別の建物）は除く
        if abs(_area(poly)) >= 0.97 * a_main or not any(_inside(p, main) for p in _probe_points(poly)):
            continue
        top = max(tops)
        try:
            ol = build_outline(poly)
        except Exception:
            continue
        faces: list[tuple[int, float]] = []
        for e in ol.edges:
            mx, my = (e.start[0] + e.end[0]) / 2.0, (e.start[1] + e.end[1]) / 2.0
            ox, oy = e.outward
            if not _inside((mx + ox * (min_depth + 200.0), my + oy * (min_depth + 200.0)), main):
                continue                      # 本体の面に近い（本体の足場が上まで上がる・内ブラケットでかわす）
            p = (mx + ox * PROBE_OUT_MM, my + oy * PROBE_OUT_MM)
            under = [t for q, t in polys if t < top - MIN_RISE_MM and _inside(p, q)]
            if under:
                faces.append((e.index, max(under)))
        if faces:
            out.append({"outline_mm": [list(v) for v in ol.vertices], "top_mm": top, "faces": faces})
    return sorted(out, key=lambda t: t["top_mm"])


def _probe_points(poly) -> list:
    """外形の中の点（重心と、頂点と重心の中点）."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return [(cx, cy)] + [((p[0] + cx) / 2.0, (p[1] + cy) / 2.0) for p in poly]


def _contains(outer, inner, tol: float = 300.0) -> bool:
    return _within(inner, outer, tol)


def overhang_tiers(outline_mm, slabs: list[dict], min_depth: float = SETBACK_MAX_MM) -> list[dict]:
    """張り出した上の階 [{"outline_mm", "top_mm", "base_mm"}]（base は張り出しのいちばん下の床の天端）."""
    from .geometry import build_outline

    main = [tuple(map(float, p)) for p in outline_mm]
    groups: dict[tuple, tuple[list, list[float]]] = {}
    for s in slabs or []:
        poly = [tuple(map(float, p)) for p in s.get("polygon_mm") or []]
        if len(poly) >= 3:
            groups.setdefault(_key(poly), (poly, []))[1].append(float(s.get("top_mm", 0.0)))
    floor0 = min((t for _p, ts in groups.values() for t in ts), default=0.0)
    xs, ys = [p[0] for p in main], [p[1] for p in main]
    out = []
    for poly, tops in groups.values():
        # 本体の外形の中に収まる外形（セットバックだけの階）は張り出しではない。本体を含まなくてもよい（一部の面だけ外へ
        # 張り出す階。実機 2026-10-25: 1000mm はねだしている うまくいってない）
        if _within(poly, main, tol=0.0) or not any(_inside(p, main) for p in _probe_points(poly)):
            continue
        # 地盤・敷地のスラブ（いちばん低い床と同じ高さ）や、本体から大きく外へ広がる外形（別の建物・敷地）は張り出しではない
        if min(tops) < floor0 + MIN_RISE_MM:
            continue
        if any(x < min(xs) - OVERHANG_MAX_MM or x > max(xs) + OVERHANG_MAX_MM
               or y < min(ys) - OVERHANG_MAX_MM or y > max(ys) + OVERHANG_MAX_MM for x, y in poly):
            continue
        try:
            ol = build_outline(poly)
        except Exception:
            continue
        far = False
        for e in ol.edges:
            ox, oy = e.outward
            for k in range(1, 8):
                t = k / 8.0
                x = e.start[0] + (e.end[0] - e.start[0]) * t - ox * (min_depth + 1.0)
                y = e.start[1] + (e.end[1] - e.start[1]) * t - oy * (min_depth + 1.0)
                if not _inside((x, y), main):
                    far = True
        if far:
            out.append({"outline_mm": [list(v) for v in ol.vertices], "top_mm": max(tops), "base_mm": min(tops)})
    return sorted(out, key=lambda t: t["base_mm"])


def overhang_faces(big_mm, main_mm, min_depth: float = SETBACK_MAX_MM) -> dict[int, tuple[str, float]]:
    """張り出した上の階の外形の面のうち、本体の外形より外へ出ている面 → {辺番号: (範囲, 長さ)}.

    範囲 "all"＝面全体が外（張り出した面）。"s"・"e"＝面の始点側・終点側だけが外（張り出しの横の短い面。外の部分の
    長さ mm。その先は本体の面と同じ線で、本体の足場が地上から上まで通る）。外へ出ていない面は入れない。
    """
    from .geometry import build_outline

    main = [tuple(map(float, p)) for p in main_mm]
    ol = build_outline([tuple(map(float, p)) for p in big_mm])
    off = min_depth + 1.0          # 奥行きの上限（900）を超えて外へ出ている面（1000 の張り出しも）

    def outside(e, d: float) -> bool:
        ux, uy = e.direction
        ox, oy = e.outward
        x = e.start[0] + ux * d - ox * off
        y = e.start[1] + uy * d - oy * off
        return not _inside((x, y), main)

    out: dict[int, tuple[str, float]] = {}
    for e in ol.edges:
        L = e.length
        n = 48
        flags = [outside(e, L * (k + 0.5) / n) for k in range(n)]
        if not any(flags):
            continue
        if all(flags):
            out[e.index] = ("all", L)
            continue
        if flags[0] and not flags[-1]:
            lo, hi = 0.0, L
            for _ in range(30):
                mid = (lo + hi) / 2.0
                lo, hi = (mid, hi) if outside(e, mid) else (lo, mid)
            out[e.index] = ("s", lo)
        elif flags[-1] and not flags[0]:
            lo, hi = 0.0, L
            for _ in range(30):
                mid = (lo + hi) / 2.0
                lo, hi = (lo, mid) if outside(e, mid) else (mid, hi)
            out[e.index] = ("e", L - hi)
        else:
            out[e.index] = ("all", L)
    return out


HANE_END_CLEAR_MM = 150.0    # 張り出しの横の面の上段の端と、本体の隅の升目（外側の建地の列）のあき（半分までは詰めてよい）


def hane_face_ranges(sub: dict, main_model, names_of) -> dict:
    """跳ね出しの上段の入力に、張り出しの横の短い面の区間（_face_range）を入れて返す.

    横の面は張り出した部分だけ建て、本体の隅の升目（本体の面の離れ＋建地列間隔）の手前で止める（端は開放端）。区間は
    上段の面の始点の支柱から mm（終点側は負＝終点から）。"""
    parts = sub.get("_overhang_faces") or {}
    if not parts:
        return sub
    from .geometry import build_outline

    names = names_of(sub["outline_mm"])
    ol = build_outline([tuple(map(float, p)) for p in sub["outline_mm"]])
    row = float(main_model.post_row_spacing_mm)
    target = float((sub.get("standoff") or {}).get("target", 300.0))
    rng = {}
    for ei_s, (kind, length) in parts.items():
        ei = int(ei_s)
        if kind == "all":
            continue
        e = ol.edges[ei]
        # 張り出しの外の部分が終わる点（本体の隅）で、この面と直交する本体の面の離れ
        d = length if kind == "s" else e.length - length
        px, py = e.start[0] + e.direction[0] * d, e.start[1] + e.direction[1] * d
        so_perp = target
        best = None
        for me in main_model.plan.edges:
            mo = main_model.plan.outline.edges[me.edge_index]
            if abs(mo.direction[0] * e.direction[0] + mo.direction[1] * e.direction[1]) > 0.5:
                continue
            dist = abs((px - mo.start[0]) * mo.direction[1] - (py - mo.start[1]) * mo.direction[0])
            if best is None or dist < best:
                best, so_perp = dist, float(me.standoff)
        # 上段の面の始点の支柱は、前の面（張り出した面）の離れだけ外の位置から
        limit = length - so_perp - row - HANE_END_CLEAR_MM + target
        if limit < 500.0:
            rng[names[ei]] = None
            continue
        rng[names[ei]] = [0.0, limit, "fit"] if kind == "s" else [-limit, -1.0, "fit"]
    faces = [f for f in (sub.get("faces") or []) if rng.get(f, 1) is not None]
    out = {**sub, "faces": faces}
    # 建てない面（張り出していない面）のうち本体の面と同じ線の面は、本体の離れ（上段の面の端の支柱を本体の内側の建地の
    # 列にそろえる。目標の離れのまま解くと上段の面の離れがインチの割付で 350 を超え、内ブラケットが出ていた）
    nb = dict(sub.get("_neighbor_standoffs") or {})
    for e in ol.edges:
        if names[e.index] in faces:
            continue
        for me in main_model.plan.edges:
            mo = main_model.plan.outline.edges[me.edge_index]
            if abs(mo.direction[0] * e.direction[0] + mo.direction[1] * e.direction[1]) < 0.99:
                continue
            dist = abs((e.start[0] - mo.start[0]) * mo.direction[1] - (e.start[1] - mo.start[1]) * mo.direction[0])
            if dist < 5.0:
                nb[e.index] = float(me.standoff)
                break
    # 小さな張り出し（300 など）: 普通の離れで建てると跳ね出しの上段の建地列が本体の隅の升目の列と重なる。張り出した面の
    # 内側建地の列を、その下の本体の面の外側建地の列にそろえる（離れ＝本体の離れ＋建地列間隔−張り出し。躯体との隙間は
    # 内ブラケットで詰める）。端は本体の隅の升目の外側の支柱を共有し、張出ブラケットで隅の外へ床を持ち出して繋ぐ
    # （hane_bridges。利用者の指定 2026-10-25: 300出してるのにできてない拡張に）
    so_min = float((sub.get("standoff") or {}).get("min", 250.0))
    for ei_s, (kind, _length) in parts.items():
        if kind != "all":
            continue
        e = ol.edges[int(ei_s)]
        for me in main_model.plan.edges:
            mo = main_model.plan.outline.edges[me.edge_index]
            if mo.direction[0] * e.direction[0] + mo.direction[1] * e.direction[1] < 0.99:
                continue
            d = ((e.start[0] - mo.start[0]) * mo.outward[0] + (e.start[1] - mo.start[1]) * mo.outward[1])
            if not (1.0 < d < float(me.standoff) + row):
                continue
            s_al = float(me.standoff) + row - d
            if s_al >= so_min:
                al = dict(out.get("_aligned_standoff") or {})
                al[str(e.index)] = round(s_al, 1)
                out["_aligned_standoff"] = al
            break
    if nb:
        out["_neighbor_standoffs"] = nb
    rr = {f: r for f, r in rng.items() if r is not None}
    if rr:
        out["_face_range"] = rr
    return out


def overhang_caps(spec: dict) -> dict[int, float]:
    """張り出した上の階があれば、本体の面ごとの足場の天端の上限（GL から mm。跳ね出しブラケットの下端−手すり分）."""
    if spec.get("_tier") or not spec.get("slabs") or not spec.get("height_from_slabs", True) \
            or spec.get("setback_tiers") is False:
        return {}
    from .geometry import build_outline

    if hane_type(spec) == "なし":
        return {}
    tiers = overhang_tiers(spec["outline_mm"], spec["slabs"], float(spec.get("overhang_min_mm", OVERHANG_MIN_MM)))
    if not tiers:
        return {}
    # 張り出しの下になる本体の面だけ、ブラケットの下で止める（面の外 600 の点が張り出した上の階の外形の中）。張り出して
    # いない面は地上から上まで通す（利用者の指定 2026-10-25: 拡張は張り出す面だけ跳ね出しにして）
    out: dict[int, float] = {}
    # 面の外の点は、拡張とみなす奥行きの半分（小さな張り出し 300 でも外形の中に入る）
    probe = 0.5 * float(spec.get("overhang_min_mm", OVERHANG_MIN_MM))
    for e in build_outline([tuple(map(float, p)) for p in spec["outline_mm"]]).edges:
        for t in tiers:
            big = [tuple(map(float, p)) for p in t["outline_mm"]]
            hits = 0
            for k in range(1, 8):
                x = e.start[0] + (e.end[0] - e.start[0]) * k / 8.0 + e.outward[0] * probe
                y = e.start[1] + (e.end[1] - e.start[1]) * k / 8.0 + e.outward[1] * probe
                hits += int(_inside((x, y), big))
            if hits >= 4:
                cap = float(t["base_mm"]) - HANE_BELOW_MM
                if hane_type(spec) == "方杖":
                    # 方杖の下端（下の階の壁の取付プレート）より下で止める
                    drop = brace_drop_mm(overhang_depth_mm(big, spec["outline_mm"]),
                                         float(spec.get("scaffold_width_mm") or 610))
                    cap = float(t["base_mm"]) - drop - 100.0
                out[e.index] = min(out.get(e.index, cap), cap)
    return out


def tier_specs(spec: dict, names_of) -> list[tuple[str, dict]]:
    """入力 → 上段の組 [(組の名前, 入力)]。names_of(outline_mm) は外形の辺の面の名前（辺の順）.

    スラブが無い・高さをスラブから決めない・かわさない（avoid_obstacles false）・上段の組そのもの（_tier）なら []。
    """
    if spec.get("_tier") or not spec.get("slabs") or not spec.get("height_from_slabs", True) \
            or not spec.get("avoid_obstacles", True) or spec.get("setback_tiers") is False:
        return []
    depth = float(spec.get("setback_bracket_max_mm", SETBACK_MAX_MM))
    tiers = setback_tiers(spec["outline_mm"], spec["slabs"], depth)
    out = []
    odepth = float(spec.get("overhang_min_mm", OVERHANG_MIN_MM))
    # 跳ね出さない（本体の足場を上まで通して庇としてかわす）ときは張り出しの上段を作らない
    over = [] if hane_type(spec) == "なし" else overhang_tiers(spec["outline_mm"], spec["slabs"], odepth)
    for k, t in enumerate(over):
        names = names_of(t["outline_mm"])
        parts = overhang_faces(t["outline_mm"], spec["outline_mm"], odepth)
        if not parts:
            continue
        sub = {kk: v for kk, v in spec.items() if kk not in _DROP}
        st = sub.get("stairs")
        if isinstance(st, dict) and "positions" in st:
            sub["stairs"] = {kk: v for kk, v in st.items() if kk != "positions"}
        label = "上段（張り出し）" if k == 0 else f"上段（張り出し{k + 1}）"
        sub.update({
            "outline_mm": t["outline_mm"],
            "base_height_mm": t["base_mm"],
            "eaves_height_mm": int(round(t["top_mm"] - t["base_mm"])),
            "height_from_slabs": False,
            "project_name": f"{spec.get('project_name') or '足場'} {label}",
            "_tier": True,
            "_hane": True,
            "_hane_type": hane_type(spec),
            "_hane_drop_mm": brace_drop_mm(overhang_depth_mm(t["outline_mm"], spec["outline_mm"]),
                                           float(spec.get("scaffold_width_mm") or 610)),
            "_hane_wall_mm": overhang_depth_mm(t["outline_mm"], spec["outline_mm"]),
            # 屋根の上・ブラケットの上には仮囲いが無い。シートは足場の立つ面まで下ろす（利用者の指定 2026-10-25:
            # シートの高さも揃えて）
            "hoarding_height_mm": 0,
            # 張り出した面と、張り出しの横の短い面の張り出した部分だけ（区間は本体を解いてから hane_face_ranges）
            "faces": [names[i] for i in sorted(parts)],
            "_overhang_faces": {str(i): list(v) for i, v in parts.items()},
        })
        out.append((label, sub))
    for k, t in enumerate(tiers):
        names = names_of(t["outline_mm"])
        chosen = {i for i, _b in t["faces"]}
        base = min(b for _i, b in t["faces"])
        n = len(names)
        joined = []
        for i in sorted(chosen):
            if (i - 1) % n not in chosen:
                joined.append([i, "s"])
            if (i + 1) % n not in chosen:
                joined.append([i, "e"])
        sub = {kk: v for kk, v in spec.items() if kk not in _DROP}
        st = sub.get("stairs")
        if isinstance(st, dict) and "positions" in st:
            sub["stairs"] = {kk: v for kk, v in st.items() if kk != "positions"}
        label = "上段" if k == 0 else f"上段（{k + 1}）"
        sub.update({
            "outline_mm": t["outline_mm"],
            "faces": [names[i] for i in sorted(chosen)],
            "base_height_mm": base,
            "eaves_height_mm": int(round(t["top_mm"] - base)),
            "height_from_slabs": False,
            "project_name": f"{spec.get('project_name') or '足場'} {label}",
            "_tier": True,
            "_joined_ends": joined,
            # 屋根の上・ブラケットの上には仮囲いが無い。シートは足場の立つ面まで下ろす（利用者の指定 2026-10-25:
            # シートの高さも揃えて）
            "hoarding_height_mm": 0,
        })
        out.append((label, sub))
    return out


def tier_note(label: str, sub: dict) -> Optional[str]:
    if not sub.get("_tier"):
        return None
    if sub.get("_hane"):
        return (f"{label}: 張り出した上の階（GL+{sub['base_height_mm']:.0f} から上）の {'・'.join(sub.get('faces') or [])} は、"
                f"床スラブの縁から出す跳ね出しブラケットの上に足場を建てます（軒高 {sub['eaves_height_mm']}）。張り出しの下の"
                "本体の面はブラケットの下で止め、ほかの本体の面は地上から上まで通します")
    ends = ("端は本体の足場の手前で止めて妻側を塞ぎます" if "_joined_ends" in sub and not sub["_joined_ends"]
            else "端は本体の足場に繋ぎます")
    return (f"{label}: セットバックした上の階の {'・'.join(sub['faces'])} は、途中の屋根（GL+{sub['base_height_mm']:.0f}）の"
            f"上から足場を建て、{ends}（軒高 {sub['eaves_height_mm']}）")


# ---- 上段の端と本体の足場の納まり（利用者の指定 2026-10-25: セットバックの時は この左右のセットバックより先の足場は
# 不要です。セットバックから支柱が繋がるように配置して割り付けしてください セットバックの両端のジャッキベースなしにして）----

TIER_STANDOFF_MIN_MM = 200.0    # 上段の離れの最小の既定（setback_standoff_min）
FREE_TIER_CLEAR_MM = 150.0      # 本体に繋げない上段の端と本体の内側の建地の列のあき


def _line_hit(p, d, q, e) -> Optional[tuple[float, float]]:
    """直線 p+t·d と q+s·e の交点."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return p[0] + d[0] * t, p[1] + d[1] * t


def _best_spans(coins: list[int], length: float, slack: float = 150.0,
                window: Optional[tuple[float, float]] = None) -> list[int]:
    """長さにいちばん近い（以下を先に）スパンの並び（本数の少ないもの）. 長さが 0 以下なら [].

    window=(下, 上) を渡すと、合計と長さの差がその範囲に入るものだけ（上段の離れを 250〜350 に収める）。"""
    from .plan_solver import achievable_sums

    lo_d, hi_d = window if window is not None else (-slack, slack)
    if length + hi_d < min(coins) - 1.0:
        return []
    table = achievable_sums(coins, max(min(coins), int(math.floor(length + lo_d))), int(math.ceil(length + hi_d)))
    if not table:
        return []
    # 1829（いちばん長いスパン）を基本に、端数のスパンの少ないもの → 本数の少ないもの → 近いもの（実機 2026-10-25:
    # 近さだけで選んで 1829×3 より 3mm 近い 610×9 を選んでいた）
    main = max(coins)
    near = [v for v in table if lo_d - 0.5 <= v - length <= hi_d + 0.5]
    if not near:
        return []
    best = min(near, key=lambda v: (sum(1 for x in table[v] if x != main), len(table[v]), abs(v - length)))
    return sorted(table[best], reverse=True)


def _main_first_table(coins: list[int], max_total: int) -> dict[int, list[int]]:
    """合計 → スパンの並び（1829 を基本に端数のスパンがいちばん少なく、次に本数の少ないもの。長い順）."""
    main = max(coins)
    best: dict[int, tuple[int, int, list[int]]] = {0: (0, 0, [])}
    for total in range(1, max_total + 1):
        cand = None
        for c in coins:
            prev = best.get(total - c)
            if prev is None:
                continue
            key = (prev[0] + (c != main), prev[1] + 1)
            if cand is None or key < cand[:2]:
                cand = (key[0], key[1], prev[2] + [c])
        if cand is not None:
            best[total] = cand
    return {v: sorted(c[2], reverse=True) for v, c in best.items() if v > 0}


def _exact(coins: list[int], length: int) -> Optional[list[int]]:
    from .plan_solver import achievable_sums

    if length <= 0:
        return [] if length == 0 else None
    t = achievable_sums(coins, length, length)
    return sorted(t[length], reverse=True) if length in t else None


def setback_junctions(spec: dict, tiers: list[tuple[str, dict]], solve, names_of) -> tuple[dict, list[tuple[str, dict]], list[str]]:
    """セットバックの上段の端（本体の足場に繋ぐ端）の納まりを決める → (本体の入力, 上段の入力, 案内).

    - 上段の端が当たる本体の面（上まで上がる面）に、上段の内側・外側の建地の列の位置に支柱が来るスパンを固定する
      （span_overrides）。上段の線はその支柱に合わせる（上段の離れを固定。_neighbor_standoffs）
    - その面の、上段の線より外（セットバックの先。途中の屋根の上）の区間は「下段」として途中の屋根の高さで止める
      （_low_ranges。face_forms と同じ面の区間の組）。上段の端は本体の支柱に乗るので、支柱・ジャッキを描かない（_skip_end_posts）
    solve(spec) は本体だけを解く関数、names_of(outline) は面の名前。
    """
    from .geometry import build_outline
    from .plan_solver import achievable_sums

    notes: list[str] = []
    setback = [(lb, t) for lb, t in tiers if not t.get("_hane") and t.get("_joined_ends")]
    if not setback or spec.get("setback_join") is False:
        return spec, tiers, notes
    r0 = solve(spec)
    m0 = r0.model
    coins = sorted({int(s) for s in m0.master.span_lengths()})
    w = float(m0.post_row_spacing_mm)
    main_edges = {e.edge_index: e for e in m0.plan.edges}
    main_ol = m0.plan.outline
    names = m0.plan.face_names()
    name_of = dict(zip([e.edge_index for e in m0.plan.edges], names))
    target = float((spec.get("standoff") or {}).get("target", 300.0))
    so_min = float((spec.get("standoff") or {}).get("min", 250.0))
    # 上段の離れの最小（既定 200）。上段は改修・塗装程度の作業で 200 前後でも足りる。本体を最小まで詰めて上段を少し狭く
    # する方が、本体の面の離れを広げて内ブラケットを付けるより部材が少ない（利用者の指定 2026-10-25: 本体250・上段236で）
    tier_min = float(spec.get("setback_standoff_min", TIER_STANDOFF_MIN_MM))
    so_max = float((spec.get("standoff") or {}).get("max", 350.0))
    overrides: dict[str, list[int]] = {}
    span_so_max = 0.0                       # 上段の離れを合わせるために広げた本体の面の離れ（内ブラケット）
    free_tiers: set[int] = set()            # 本体に繋げない上段（id(入力)）
    prev_so: dict[int, float] = {}          # 上段の離れを合わせるために決めた本体の面の離れ（隅の前の面）
    low: dict[str, list[float]] = {}
    passage: list[list[float]] = []
    low_top = None
    plan_t: list[dict] = []
    heads: dict[int, tuple] = {}
    for lb, t in setback:
        tol = build_outline([tuple(map(float, p)) for p in t["outline_mm"]])
        tnames = names_of(t["outline_mm"])
        idx = {n: i for i, n in enumerate(tnames)}
        juncs = []
        for ei, end in t["_joined_ends"]:
            te = tol.edges[int(ei)]
            pc = te.start if end == "s" else te.end
            # 上段の端の点が載る本体の外形の辺（上段の面と平行でない）
            hit = None
            for oe in main_ol.edges:
                if abs(oe.direction[0] * te.direction[0] + oe.direction[1] * te.direction[1]) > 0.5:
                    continue
                ax, ay = oe.start
                ux, uy = oe.direction
                tt = (pc[0] - ax) * ux + (pc[1] - ay) * uy
                dist = abs((pc[0] - ax) * uy - (pc[1] - ay) * ux)
                if dist < 5.0 and -1.0 <= tt <= oe.length + 1.0 and oe.index in main_edges:
                    hit = oe
            if hit is None:
                continue
            ep = main_edges[hit.index]
            sp = ep.start_post
            u = ((ep.end_post[0] - sp[0]) / max(1e-9, float(sum(ep.spans))),
                 (ep.end_post[1] - sp[1]) / max(1e-9, float(sum(ep.spans))))
            a = (pc[0] + te.outward[0] * target, pc[1] + te.outward[1] * target)
            x = _line_hit(a, te.direction, sp, u)
            if x is None:
                continue
            p_in = (x[0] - sp[0]) * u[0] + (x[1] - sp[1]) * u[1]
            sgn = 1.0 if te.outward[0] * u[0] + te.outward[1] * u[1] > 0 else -1.0
            juncs.append((ei, end, ep, p_in, sgn))
        for ei, end, ep, p_in, sgn in juncs:
            if int(round(w)) not in coins:
                notes.append(f"{lb}: 建地列の間隔 {w:.0f} の布材が系列に無いので、上段の端の支柱を本体の支柱に揃えられません")
                continue
            lo = min(p_in, p_in + sgn * w)
            prev = (ep.edge_index - 1) % len(main_ol.edges)
            so_prev = float(main_edges[prev].standoff) if prev in main_edges else target
            heads[ep.edge_index] = (lo, float(sum(ep.spans)), sgn, t, so_prev, lb, prev)
        plan_t.append({"label": lb, "sub": t, "juncs": juncs, "idx": idx, "names": tnames})
    # 向かい合う（平行な）面の合計の長さは同じでないと割付が解けない。平行な面の組ごとに、元の長さに近く、
    # どの面も残りがちょうど組める合計 T を探す
    def axis(ei):
        ep = main_edges[ei]
        dx, dy = ep.end_post[0] - ep.start_post[0], ep.end_post[1] - ep.start_post[1]
        return 0 if abs(dx) >= abs(dy) else 1
    for ax in (0, 1):
        group = [ei for ei in heads if axis(ei) == ax]
        if not group:
            continue
        L0 = max(h[1] for ei, h in heads.items() if ei in group)
        best_T = None
        main_span = max(coins)
        # 合計 T と、各面の上段の内側の列までのスパン S を一緒に選ぶ。T を変えると本体の両端の面（隅の前・後の面）の離れが
        # (T−L0)/2 ずつ動き、上段の離れ s＝目標＋(S−lo−(T−L0)/2)×向き も動く。上段の離れを 250〜350 に収めるのを先に、
        # 本体の離れは 250〜350 を外れてもよい（外れた面は内ブラケット。利用者の指定 2026-10-25: 上段の隙間 153 は狭い・
        # 本体は全部同じ離れでなくていいよ）
        lo_T, hi_T = int(L0) - 2 * 300, int(L0) + 2 * 400
        span_tab = _main_first_table(coins, hi_T)
        totals = {v: c for v, c in span_tab.items() if lo_T <= v <= hi_T}

        def outside(v: float, lo_v: float, hi_v: float) -> float:
            return max(0.0, lo_v - v, v - hi_v)

        import bisect

        keys_sorted = sorted(span_tab)
        # 上段の端が当たる面の始点の隅の前の面（その離れで面の始めの支柱が動く）。2つの面が向かい合う隅の面（例: 南面は
        # 西面、北面は東面）なら、両方の離れの和が T−L0 だけ変わり、配分は自由（本体は全部同じ離れでなくていい）
        prevs = sorted({heads[ei][6] for ei in group})
        base_so = {pv: next(heads[ei][4] for ei in group if heads[ei][6] == pv) for pv in prevs}

        def pick_for(ei, lo_s, T, s_ref):
            lo, _L, sgn, _t, _so, _lb, _pv = heads[ei]
            best = None
            i0 = bisect.bisect_left(keys_sorted, lo_s - 700)
            i1 = bisect.bisect_right(keys_sorted, lo_s + 700)
            for S in keys_sorted[i0:i1]:
                sp = span_tab[S]
                st = target + (S - lo_s) * sgn
                if s_ref is not None and abs(st - s_ref) > 5.0:
                    continue
                # 向かい合う面の合計はちょうど T（割付の式は真物で厳密に成り立つ必要がある）
                r_len = T - S - int(round(w))
                rest = [] if r_len == 0 else span_tab.get(r_len) if r_len > 0 else None
                if rest is None:
                    continue
                key = (outside(st, tier_min, so_max), sum(1 for x in sp + rest if x != main_span), abs(st - target))
                if best is None or key < best[0]:
                    best = (key, st, sorted(sp, reverse=True), rest)
            return best

        for T in sorted(totals, key=lambda v: abs(v - L0)):
            extra = T - L0
            # 隅の前の面の離れの配分（2面なら A を動かし B は残り、1面なら半分ずつ）
            if len(prevs) == 2:
                a, b = prevs
                splits = []
                for va in range(int(math.ceil(so_min)), int(so_max + 300) + 1, 2):
                    vb = base_so[a] + base_so[b] + extra - va
                    if so_min - 0.5 <= vb <= so_max + 300:
                        splits.append({a: va - base_so[a], b: vb - base_so[b]})
            else:
                splits = [{pv: extra / 2.0 for pv in prevs}]
            for dl in splits:
                so_new = [base_so[pv] + dl[pv] for pv in prevs]
                if min(so_new) < so_min - 0.5:
                    continue
                main_out = max(outside(v, so_min, so_max) for v in so_new)
                picks = {}
                s_ref = None
                for ei in sorted(group, key=lambda e: heads[e][0]):
                    b_ = pick_for(ei, heads[ei][0] + dl[heads[ei][6]], T, s_ref)
                    if b_ is None:
                        break
                    picks[ei] = b_
                    s_ref = b_[1] if s_ref is None else s_ref
                else:
                    tier_out = max(b_[0][0] for b_ in picks.values())
                    # 上段の離れ → 本体の離れの広げ幅（50 刻み。範囲の内なら 0）→ 端数のスパンの少なさ → 元の長さとの差
                    # → 本体の離れの偏り
                    st_any = next(iter(picks.values()))[1]
                    key = (tier_out, round(main_out / 50.0), sum(b_[0][1] for b_ in picks.values()), abs(T - L0),
                           round(abs(st_any - target) / 10.0), abs(so_new[0] - so_new[-1]))
                    if best_T is None or key < best_T[0]:
                        best_T = (key, T, picks, {pv: base_so[pv] + dl[pv] for pv in prevs})
        if best_T is None:
            notes.append("上段の端の支柱を本体の支柱に揃える割付が見つかりません（面の長さと布材の規格）。揃えずに置きます")
            continue
        key, T, picks, so_set = best_T
        if key[0] > 0.5 or max(so_set.values()) > so_max + 0.5:
            # 上段の端を本体の支柱に乗せると、上段の離れが範囲を外れるか本体の面の離れを最大より広げる（内ブラケットが出る）。
            # 無理に繋げず、上段は自前の支柱で目標の離れに建て、端は本体の内側の建地の列の手前で止めて妻側を塞ぐ
            # （利用者の指定 2026-10-25: ブラケット出てるところがある 無理に繋げなくてもいいよ）
            for ei in group:
                lo, L, sgn, t, so_prev, lbl, _pv = heads[ei]
                ep = main_edges[ei]
                posts = [0.0]
                for v in ep.spans:
                    posts.append(posts[-1] + float(v))
                fname = name_of[ei]
                if sgn > 0:
                    cut = next((x for x in posts if x >= lo + w - 1.0), posts[-1])
                    low[fname] = [cut, 1.0e9]
                else:
                    cut = max((x for x in posts if x <= lo + 1.0), default=0.0)
                    low[fname] = [0.0, cut]
                low_top = float(t["base_height_mm"]) if low_top is None else min(low_top, float(t["base_height_mm"]))
                free_tiers.add(id(t))
            notes.append(f"{heads[group[0]][5]}: 上段の端を本体の支柱に揃えると上段の離れか本体の離れが範囲を外れるので、上段は"
                         "本体に繋げず自前の支柱で建て、端は本体の内側の建地の列の手前で止めて妻側を塞ぎます")
            continue
        rests = {ei: picks[ei][3] for ei in group}
        so_wide = max(so_set.values())
        if so_wide > so_max + 0.5:
            span_so_max = max(span_so_max, so_wide + 5.0)
        if len(so_set) == 2 or any(abs(v - base_so[pv]) > 0.5 for pv, v in so_set.items()):
            prev_so.update({pv: round(v, 1) for pv, v in so_set.items()})
        for ei in group:
            lo, L, sgn, t, so_prev, lbl, _pv = heads[ei]
            heads[ei] = (picks[ei][2], L, sgn, t)
        st_any = next(iter(picks.values()))[1]
        if key[0] > 0.5:
            notes.append(f"上段の離れを {tier_min:.0f}〜{so_max:.0f} に収める割付がありません。いちばん近い {st_any:.0f} で置きます")
        if key[1] > 0.5:
            notes.append(f"上段の離れを {st_any:.0f} にするため、本体の上段の両脇の面の離れを広げています（{so_min:.0f}〜"
                         f"{so_max:.0f} を外れた面は内ブラケットで床と躯体の隙間を詰めます）")
        for ei in group:
            first, _L, sgn, t = heads[ei]
            a2 = float(sum(first))
            spans = first + [int(round(w))] + rests[ei]
            fname = name_of[ei]
            overrides[fname] = spans
            # セットバックの先: 上段の外側の列より外（上段の外向きの側）
            low[fname] = [0.0, a2] if sgn < 0 else [a2 + w, 1.0e9]     # 1e9＝面の終点まで（face_forms.FACE_END_MM 以上）
            # 上段の内外の建地の列の間のスパン（上段の床から本体の床へ歩いて渡る升目）
            passage.append([ei, a2, a2 + w])
            low_top = float(t["base_height_mm"]) if low_top is None else min(low_top, float(t["base_height_mm"]))
    if not overrides and not low:
        return spec, tiers, notes
    if span_so_max or prev_so:
        # 本体の面の離れを広げる・配分を変えるのは上段の端が当たる面の隅の前後の面だけ。そのほかの面のスパンは元のまま（広げた
        # 面の長さの方向の離れを変えない）
        for ei, ep in main_edges.items():
            fn = name_of[ei]
            if fn not in overrides and not any(axis(ei) == axis(j) for j in heads):
                overrides[fn] = [int(v) for v in ep.spans]
    base = float(spec.get("base_height_mm", 0) or 0)
    idx_of = {n: ei for ei, n in name_of.items()}
    # 切れ目: 下段の側は本体に続く（妻側を塞がない）、本体の側は途中の屋根より上だけ塞ぐ
    low_join = [[idx_of[f], "e" if a < 0.5 else "s"] for f, (a, _b) in low.items()]
    open_above = [[idx_of[f], "s" if a < 0.5 else "e", low_top - base] for f, (a, _b) in low.items()]
    main = {**spec, "span_overrides": list(spec.get("span_overrides") or [])
            + [{"face": f, "spans_mm": sp} for f, sp in overrides.items()],
            "_low_ranges": low, "_open_above": open_above,
            **({"_span_standoff_max": round(span_so_max, 1)} if span_so_max else {}),
            **({"_span_standoffs": {int(k): v for k, v in prev_so.items()}} if prev_so else {}),
            # 上段の床から本体の床へ渡る升目は、途中の屋根より上の層で本体の内側の手すり（布材）を付けない
            # （利用者の指摘 2026-10-25: セットバックの足場が本体と回らないようになっている布材を配置しないようにして）
            "_tier_passage": [[ei, a, b, low_top - base] for ei, a, b in passage],
            # 下段は本体と同じ立面を途中の屋根で切る（床の高さが本体とそろう。別に解くとジャッキ・段がずれた）
            # 下段の本体側の端の支柱は本体の支柱（全高）と同じ位置。下段は描かず数えない（二重に立っていた）
            "_low_spec": {"height_from_slabs": False, "roof_bridge": False, "_joined_ends": low_join,
                          "_skip_end_posts": low_join,
                          "scaffold_height_mm": "__MAIN__",
                          "face_eaves_mm": {f: int(round(low_top - base)) for f in low}}}
    # 揃えたスパンで解き直した本体の支柱の位置に、上段の線を合わせる
    r1 = solve({k: v for k, v in main.items() if k not in ("_low_ranges", "_low_spec", "_open_above")})
    m1 = r1.model
    # 下段は本体と同じ足場高さで解いて途中の屋根で切る（面ごとの軒高を入れると全体の軒高まで低くなって段がずれた）
    main["_low_spec"]["scaffold_height_mm"] = int(m1.elevation.total_height)
    main["_low_spec"]["eaves_height_mm"] = int(round(max((m1.eaves_by_face or {}).values(),
                                                         default=float(spec.get("eaves_height_mm") or 0))))
    # 本体の切れ目の妻側は、下段の足場の天端より上だけ塞ぐ（下段の床の層は下段に続く。シートも下段の足場の天端から上。
    # 利用者の指定 2026-10-25: セットバックのメッシュは低いところの足場までにして）
    from .elevation_solver import truncate_elevation

    from .attachments import sheet_top_of

    low_ev = truncate_elevation(m1.elevation, low_top - base, m1.master)
    low_top_rel = float(low_ev.total_height)
    main["_open_above"] = [[ei, end, low_top_rel] for ei, end, _z in main["_open_above"]]
    # 妻側のシート・上段のシートは下段のシート（低い所のメッシュ）の天端から上（利用者の指定 2026-10-25: セットバック
    # 部分もメッシュシートは低いところのメッシュの高さまででいいよ）
    low_sheet_rel = float(sheet_top_of(m1, low_ev))
    main["_open_sheet_above"] = [[ei, end, low_sheet_rel] for ei, end, _z in main["_open_above"]]
    e1 = {e.edge_index: e for e in m1.plan.edges}
    out_tiers = []
    done = {id(p["sub"]) for p in plan_t}
    for lb, t in tiers:
        if id(t) not in done:
            out_tiers.append((lb, t))
            continue
        pt = next(p for p in plan_t if p["sub"] is t)
        tol = build_outline([tuple(map(float, p)) for p in t["outline_mm"]])
        lv_abs = [float(h) + float(m1.base_height_mm or 0) for h in m1.elevation.level_heights]
        top_abs = float(m1.elevation.total_height) + float(m1.base_height_mm or 0)
        if id(t) in free_tiers:
            # 本体に繋げない上段: 端の面（本体の面と同じ線）の離れを本体の離れ − あき にして、本体の内側の建地の列の手前で
            # 止める。端は開放端（妻側の手すり・シート）。床・天端・シートの下端は本体にそろえる
            fixed_f: dict[int, float] = {}
            gap_ends = []
            for ei, end, ep0, p_in, sgn in pt["juncs"]:
                ep = e1.get(ep0.edge_index)
                if ep is None:
                    continue
                nb = (int(ei) - 1) % len(tol.edges) if end == "s" else (int(ei) + 1) % len(tol.edges)
                fixed_f[nb] = max(0.0, float(ep.standoff) - FREE_TIER_CLEAR_MM)
                # 端は開けて本体の床へ渡る（利用者の指摘 2026-10-25: セットバックのコーナー部分ができてない）。あき 150 は
                # すき間板で塞ぎ、本体の躯体側の手すり・中桟は上段の床が当たるスパンで外す
                gap_ends.append([int(ei), end])
                lo_x, hi_x = sorted((p_in - sgn * 100.0, p_in + sgn * (w + 100.0)))
                main.setdefault("_free_passage", []).append(
                    [ep0.edge_index, lo_x, hi_x, float(t["base_height_mm"]) - base])
            t2 = {**t, "_neighbor_standoffs": fixed_f, "_joined_ends": gap_ends, "_free_gap_ends": gap_ends,
                  "_free_gap_mm": FREE_TIER_CLEAR_MM, "_align_levels_mm": lv_abs,
                  "_align_top_mm": top_abs, "_sheet_bottom_mm": base + low_sheet_rel - float(t["base_height_mm"])}
            out_tiers.append((lb, t2))
            continue
        fixed: dict[int, float] = {}
        skip = []
        so_t = None
        for ei, end, ep0, p_in, sgn in pt["juncs"]:
            ep = e1.get(ep0.edge_index)
            if ep is None:
                continue
            te = tol.edges[int(ei)]
            # 上段の内側の列が通る本体の支柱（固定したスパンの w の両端のうち、上段の躯体側）
            posts = [0.0]
            for s_ in ep.spans:
                posts.append(posts[-1] + float(s_))
            lo = float(low[name_of[ep.edge_index]][1]) if sgn < 0 else float(low[name_of[ep.edge_index]][0]) - w
            x_in = lo + w if sgn < 0 else lo
            u = ((ep.end_post[0] - ep.start_post[0]) / max(1e-9, posts[-1]),
                 (ep.end_post[1] - ep.start_post[1]) / max(1e-9, posts[-1]))
            X = (ep.start_post[0] + u[0] * x_in, ep.start_post[1] + u[1] * x_in)
            pc = te.start if end == "s" else te.end
            s_need = (X[0] - pc[0]) * te.outward[0] + (X[1] - pc[1]) * te.outward[1]
            so_t = s_need if so_t is None else so_t
            if abs(s_need - so_t) > 30.0:
                notes.append(f"{lb}: 両端で本体の支柱の位置が {abs(s_need - so_t):.0f}mm ずれます（上段の離れ {so_t:.0f}）")
            # 上段の端の面（本体の面と同じ線）の離れは本体と同じ
            nb = (int(ei) - 1) % len(tol.edges) if end == "s" else (int(ei) + 1) % len(tol.edges)
            fixed[nb] = float(ep.standoff)
            skip.append([int(ei), end])
        if so_t is None:
            out_tiers.append((lb, t))
            continue
        for ei, _e in skip:
            fixed[int(ei)] = round(so_t, 1)
        # 床の高さ（lv_abs）・足場の天端（top_abs）は本体にそろえる（利用者の指定 2026-10-25: 床の高さは揃えるようにして・
        # シートの高さも揃えて）
        # 上段のシートは下段の足場（低い所のメッシュ）の天端から上だけ（利用者の指定 2026-10-25: セットバック部分も
        # メッシュシートは低いところのメッシュの高さまででいいよ。屋根の上は下段のシートの内側）
        t2 = {**t, "_neighbor_standoffs": fixed, "_skip_end_posts": skip, "_align_levels_mm": lv_abs,
              "_align_top_mm": top_abs,
              "_sheet_bottom_mm": base + low_sheet_rel - float(t["base_height_mm"])}
        out_tiers.append((lb, t2))
        notes.append(f"{lb}: 上段の端の支柱は本体の支柱に乗せる（ジャッキベースなし）。上段の離れ {so_t:.0f}、"
                     f"セットバックの先（{'・'.join(low)}）の本体の足場は途中の屋根（GL+{low_top:.0f}）で止める")
    return main, out_tiers, notes


# 拡幅ブラケット・張出ブラケット（reports/くさび式足場の拡幅ブラケット.md。利用者の指定 2026-10-25: 拡張ブラケット
# リサーチして修正して）。拡幅ブラケットは先端に上の層の外側の支柱を立てて足場の幅を広げる部材（全高で1回だけ）、
# 張出ブラケットは床だけを持ち出す部材（先端のホゾに手すり柱）。日建 ND1800: 拡幅 NDBK03H 305（方杖は1コマ下・先端から
# 下の層の支柱へ補強単管）、張出 NDBK06H 610（方杖は2コマ下）
WIDEN_DEFAULT_MM = (305.0,)  # 系列のマスタに拡幅ブラケットが無いときの幅
WIDEN_POST_CLEAR_MM = 45.0   # 本体の隅の拡幅ブラケットの先（先端の支柱の芯）と、跳ね出しの上段の内側建地（芯）とのあき
DECK_GAP_MAX_MM = 30.0       # 床材と床材のすき間（安衛則563条1項2号ロ: 3cm 以下）
MIN_TRANSFER_MM = 400.0      # 2つの床が並ぶ長さ（渡り。作業床の幅 40cm 以上と同じ）
BRIDGE_REACH_MM = 50.0       # 跳ね出しの上段の端の支柱が本体の隅の線を越えてよい分


def widen_widths(master) -> list[float]:
    """系列の拡幅ブラケットの幅（大きい順）. マスタに無ければ 305."""
    ws = sorted({float(p.nominal_dim) for p in master.by_category("ブラケット") if "拡幅ブラケット" in p.note},
                reverse=True)
    return ws or list(WIDEN_DEFAULT_MM)


def overhang_bracket_width(master, row: float) -> float:
    """跳ね出しの上段の端の先へ床を持ち出す張出ブラケットの幅: 本体の建地列間隔（隅の升目の外側の列まで届く）以下で
    いちばん大きい張出ブラケット. マスタに無ければ建地列間隔."""
    ws = [float(p.nominal_dim) for p in master.by_category("ブラケット")
          if "張出ブラケット" in p.note and float(p.nominal_dim) <= row + 1.0]
    return max(ws) if ws else row


def hane_bridges(out: list) -> list[str]:
    """跳ね出しの上段の端を、張り出しの横の面の本体の足場（隅の升目）へ繋ぐ（利用者の指定 2026-10-25: 張り出しの横の面も
    足場入れて ブラケットで繋がるようにしてみて／拡張ブラケットリサーチして修正して）. 決めたことを組のモデルに書き、注記を返す.

    張り出しの下の本体の面（overhang_caps_rel）は張り出しの下で止まるが、その面と張り出しの横の面（上まで通る）の出隅の
    升目は高い方の面の高さまで立つ（gdl_params.corner_tower_params）。その升目の外側（張り出しの側）の2本の建地に、
    跳ね出しの上段のいちばん下の床の高さで拡幅ブラケット（跳ね出しの上段の内側建地の手前 45 までに入る幅。日建 NDBK03H 305）を
    1回だけ付け、先端に支柱を天端まで立てて升目を広げる（各層に 305 の布材・床・手すり）。跳ね出しの上段の端の内外の支柱
    からは、各層で端の先へ張出ブラケット（本体の建地列間隔まで。日建 NDBK06H 610）を出して床を持ち出す。2つの床は
    並び、あき（50 程度）は 3cm を超えるのですき間板でふさぐ.

    また跳ね出しの上段の面の端の支柱が床スラブの外（躯体の角の先）にあれば、その支柱はブラケットを壁に留められないので、
    床スラブの端の手前（角から HANE_END_CLEAR_MM）にブラケットを足し、そこから渡し梁で受ける（model.hane_slab_range）.
    """
    if not out:
        return []
    main = out[0][1].model
    caps = getattr(main, "overhang_caps_rel", None) or {}
    notes: list[str] = []
    widths = widen_widths(main.master)
    for label, r in out[1:]:
        m = r.model
        if not getattr(m, "hane_bracket", False):
            continue
        m.hane_slab_range = {}
        m.hane_end_ext = {}
        m.hane_shared_ends = set()
        ol = m.plan.outline
        ext_w = overhang_bracket_width(m.master, float(main.post_row_spacing_mm))
        for ep in m.plan.edges:
            ei = ep.edge_index
            e = ol.edges[ei]
            d = e.direction
            total = float(sum(ep.spans))
            sx, sy = ep.start_post
            x_e0 = (e.start[0] - sx) * d[0] + (e.start[1] - sy) * d[1]
            x0, x1 = x_e0 + HANE_END_CLEAR_MM, x_e0 + e.length - HANE_END_CLEAR_MM
            if x0 > 1.0 or x1 < total - 1.0:
                m.hane_slab_range[ei] = (max(0.0, x0), min(total, x1))
            for end in ("s", "e"):
                if not (m.open_start(ei) if end == "s" else m.open_end(ei)):
                    continue
                px, py = (sx, sy) if end == "s" else (sx + d[0] * total, sy + d[1] * total)
                hit = _bridge_corner(main, caps, e, ep, (px, py), end)
                if hit is None:
                    continue
                owner, side, gap = hit
                wm = next((w for w in widths if w + WIDEN_POST_CLEAR_MM <= gap + 0.5), 0.0)
                base_m = float(main.base_height_mm or 0)
                base_t = float(m.base_height_mm or 0)
                # 隅の升目の最上の作業床（隅を挟む2つの面の高い方）
                prev = (owner - 1) % len(main.plan.outline.edges)
                faces = [owner] + ([prev] if prev in {x.edge_index for x in main.plan.edges} else [])
                top_floor = max(float(main.elevation_of(f).level_heights[-1]) for f in faces)
                lv = [h + base_t - base_m for h in m.elevation_of(ei).level_heights]
                lv = [h for h in lv if h <= top_floor + 1.0]
                if not lv:
                    continue
                m.hane_end_ext[(ei, end)] = ext_w
                rest = gap - wm
                if wm > 0:
                    cb = getattr(main, "corner_bridges", None) or {}
                    cb[owner] = (wm, side, lv, rest)
                    main.corner_bridges = cb
                elif abs(gap) <= 5.0:
                    # 建地列をそろえた小さな張り出し（hane_face_ranges の _aligned_standoff）: 跳ね出しの上段の端の内側の
                    # 支柱は本体の隅の升目の外側の支柱と同じ1本（跳ね出し側は描かない）。張出ブラケットは外側の支柱だけに
                    # 付け、床の内側は隅の升目の布材に掛ける。隅の升目のその辺は手すり・中桟を外して渡る
                    m.hane_shared_ends = set(getattr(m, "hane_shared_ends", set()) or set()) | {(ei, end)}
                    co = getattr(main, "corner_open", None) or {}
                    co[owner] = (side, lv)
                    main.corner_open = co
                fill = (f"。2つの床のあき {int(round(rest))}mm は 3cm を超えるので、各層ですき間板を敷いてふさぎます"
                        if rest > DECK_GAP_MAX_MM else "")
                if wm <= 0 and abs(gap) <= 5.0:
                    notes.append(
                        f"{label}: {m.face_name(ei)}の{'始点' if end == 's' else '終点'}の端は、建地列を本体の外側の列に"
                        f"そろえたので内側の支柱を本体の隅の升目と共有し、外側の支柱から各層で張出ブラケット{int(ext_w)}を"
                        "端の先へ出して床を隅の升目の布材に掛け、隅の升目の脇へ並べます")
                    continue
                notes.append(
                    f"{label}: {m.face_name(ei)}の{'始点' if end == 's' else '終点'}の端は、端の内外の支柱から各層で張出ブラケット"
                    f"{int(ext_w)}を端の先へ出して床を持ち出し"
                    + (f"、張り出しの横の本体の足場の隅の升目（上の階まで立てる）の外側の2本に、GL+{int(round(lv[0] + base_m))}"
                       f" の床の高さで拡幅ブラケット{int(wm)}を1回だけ付けて先端に支柱を立て、升目を張り出しの側へ広げて"
                       f"2つの床を並べます{fill}。拡幅した層の上下は前踏み側の全スパンに壁つなぎを付け、拡幅部の支柱の許容荷重を"
                       "確かめてください" if wm > 0 else
                       f"て本体の足場の隅の升目の脇へ床を伸ばします（あき {int(round(gap))}mm）"))
        if m.hane_slab_range:
            notes.append(f"{label}: 床スラブの外（躯体の角の先）に出る端の支柱は、床スラブの端の手前（角から "
                         f"{int(HANE_END_CLEAR_MM)}）に足した跳ね出しブラケットから渡し梁（溝形鋼）で受けます")
    return notes


def _bridge_corner(main, caps: dict, e, ep, post: tuple, end: str) -> Optional[tuple]:
    """跳ね出しの上段の面の端（post＝端の内側建地）に向き合う、本体の張り出しの下の面の出隅 → (隅の升目を描く面, 辺, あき).

    辺は 0＝張り出しの下の面が隅の升目を描く（その面の始点の隅。外側の列から外へ）、1＝次の面が描く（前の面の外側の
    列の延長から始点の先へ）。あきは本体の外側の建地列から跳ね出しの上段の内側建地列まで（mm）."""
    n_out = e.outward
    d = e.direction
    built = {x.edge_index for x in main.plan.edges}
    n = len(main.plan.outline.edges)
    row = float(main.post_row_spacing_mm)
    for mep in main.plan.edges:
        mi = mep.edge_index
        if mi not in caps:
            continue
        me = main.plan.outline.edges[mi]
        if me.direction[0] * d[0] + me.direction[1] * d[1] < 0.99:
            continue
        # 本体の面の外側の建地列と、跳ね出しの上段の内側建地列の、外向きの位置
        m_outer = me.start[0] * n_out[0] + me.start[1] * n_out[1] + float(mep.standoff) + row
        t_inner = e.start[0] * n_out[0] + e.start[1] * n_out[1] + float(ep.standoff)
        gap = t_inner - m_outer
        if gap < -5.0 or gap > 1500.0:
            continue
        mx, my = mep.start_post if end == "s" else mep.end_post
        # 跳ね出しの上段の端の支柱が本体の隅の升目の内側の列の線のどこにあるか（スパンの割付で数百手前で止まることがある）。
        # 端の先へ出す張出ブラケットの床が、本体の隅の升目（建地列間隔 row）と 400 以上並ぶ範囲なら繋ぐ
        along = (post[0] - mx) * d[0] + (post[1] - my) * d[1]
        if (along if end == "s" else -along) < -BRIDGE_REACH_MM or abs(along) > row - MIN_TRANSFER_MM:
            continue
        if end == "s":
            prev = (mi - 1) % n
            if (main.corner_kind_start(mi) != "出隅" or prev not in built
                    or main.own_height(prev) <= main.own_height(mi) + 1.0):
                continue
            return mi, 0, gap
        nxt = (mi + 1) % n
        if (nxt not in built or main.corner_kind_start(nxt) != "出隅"
                or main.own_height(nxt) <= main.own_height(mi) + 1.0):
            continue
        return nxt, 1, gap
    return None
