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

from typing import Optional

from .obstacles import SETBACK_MAX_MM, _inside

PROBE_OUT_MM = 600.0         # 上段の面の外側（足場の下）の点
OVERHANG_MAX_MM = 4500.0     # これより外へ広がる外形は張り出した上の階とみなさない（敷地・別棟）
HANE_DEPTH_MM = 600.0        # 跳ね出しブラケットの方杖の下がり（ブラケットの下端は床の天端からこれだけ下）
HANE_GUARD_MM = 1100.0       # 本体の足場の天端（手すり分込み）をブラケットの下端からこれだけ下に収める
MIN_RISE_MM = 1000.0         # 途中の屋根から上段の天端までこれ以上
SAME_POLY_MM = 50.0          # 同じ外形とみなす頂点のずれ

# 上段の組に引き継がない条件（位置が本体の面からなので、上段では意味が変わる）
_DROP = ("outline_mm", "slabs", "face_forms", "form_standoff", "faces", "openings", "loading_stages", "hoists",
         "bracket_sections", "span_overrides", "face_eaves_mm", "base_height_mm", "eaves_height_mm",
         "building_height_mm", "scaffold_height_mm", "setbacks", "obstacles", "ground_points_mm", "member_edits",
         "corner_steps", "site_boundary_mm", "road_edges", "wall_ties_manual")


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
        if abs(_area(poly)) >= 0.97 * a_main or not _within(poly, main):
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
        if _within(poly, main) or not _contains(poly, main):
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
                x = e.start[0] + (e.end[0] - e.start[0]) * t - ox * (min_depth + 200.0)
                y = e.start[1] + (e.end[1] - e.start[1]) * t - oy * (min_depth + 200.0)
                if not _inside((x, y), main):
                    far = True
        if far:
            out.append({"outline_mm": [list(v) for v in ol.vertices], "top_mm": max(tops), "base_mm": min(tops)})
    return sorted(out, key=lambda t: t["base_mm"])


def overhang_caps(spec: dict) -> dict[int, float]:
    """張り出した上の階があれば、本体の面ごとの足場の天端の上限（GL から mm。跳ね出しブラケットの下端−手すり分）."""
    if spec.get("_tier") or not spec.get("slabs") or not spec.get("height_from_slabs", True) \
            or spec.get("setback_tiers") is False:
        return {}
    from .geometry import build_outline

    tiers = overhang_tiers(spec["outline_mm"], spec["slabs"], float(spec.get("setback_bracket_max_mm", SETBACK_MAX_MM)))
    if not tiers:
        return {}
    cap = min(t["base_mm"] for t in tiers) - HANE_DEPTH_MM
    return {e.index: cap for e in build_outline([tuple(map(float, p)) for p in spec["outline_mm"]]).edges}


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
    for k, t in enumerate(overhang_tiers(spec["outline_mm"], spec["slabs"], depth)):
        names = names_of(t["outline_mm"])
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
            "faces": list(names),
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
        })
        out.append((label, sub))
    return out


def tier_note(label: str, sub: dict) -> Optional[str]:
    if not sub.get("_tier"):
        return None
    if sub.get("_hane"):
        return (f"{label}: 張り出した上の階（GL+{sub['base_height_mm']:.0f} から上）は、床スラブの縁から出す跳ね出しブラケットの"
                f"上に全周の足場を建てます（軒高 {sub['eaves_height_mm']}）。本体の足場はブラケットの下で止めます")
    return (f"{label}: セットバックした上の階の {'・'.join(sub['faces'])} は、途中の屋根（GL+{sub['base_height_mm']:.0f}）の"
            f"上から足場を建て、端は本体の足場に繋ぎます（軒高 {sub['eaves_height_mm']}）")
