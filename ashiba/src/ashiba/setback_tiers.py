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


# ---- 上段の端と本体の足場の納まり（利用者の指定 2026-10-25: セットバックの時は この左右のセットバックより先の足場は
# 不要です。セットバックから支柱が繋がるように配置して割り付けしてください セットバックの両端のジャッキベースなしにして）----

def _line_hit(p, d, q, e) -> Optional[tuple[float, float]]:
    """直線 p+t·d と q+s·e の交点."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return p[0] + d[0] * t, p[1] + d[1] * t


def _best_spans(coins: list[int], length: float, slack: float = 150.0) -> list[int]:
    """長さにいちばん近い（以下を先に）スパンの並び（本数の少ないもの）. 長さが 0 以下なら []."""
    from .plan_solver import achievable_sums

    if length < min(coins) - 1.0:
        return []
    table = achievable_sums(coins, max(min(coins), int(length - slack)), int(length + slack))
    if not table:
        return []
    # 1829（いちばん長いスパン）を基本に、端数のスパンの少ないもの → 本数の少ないもの → 近いもの（実機 2026-10-25:
    # 近さだけで選んで 1829×3 より 3mm 近い 610×9 を選んでいた。上段の離れが ±slack で合わせる）
    main = max(coins)
    near = [s for s in table if abs(s - length) <= slack]
    best = min(near or table, key=lambda s: (sum(1 for v in table[s] if v != main), len(table[s]), abs(s - length)))
    return sorted(table[best], reverse=True)


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
    overrides: dict[str, list[int]] = {}
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
            first = _best_spans(coins, lo)
            heads[ep.edge_index] = (first, float(sum(ep.spans)), sgn, t)
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
        for dT in sorted(range(-300, 301), key=abs):
            T = int(round(L0)) + dT
            rests = {ei: _exact(coins, T - int(round(sum(heads[ei][0]))) - int(round(w))) for ei in group}
            if all(v is not None for v in rests.values()):
                # 1829 以外のスパンの数がいちばん少ない合計（同じなら元の長さに近い方）
                key = (sum(1 for v in rests.values() for x in v if x != main_span), abs(dT))
                if best_T is None or key < best_T[0]:
                    best_T = (key, T, rests)
        if best_T is None:
            notes.append("上段の端の支柱を本体の支柱に揃える割付が見つかりません（面の長さと布材の規格）。揃えずに置きます")
            continue
        _key, T, rests = best_T
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
    if not overrides:
        return spec, tiers, notes
    base = float(spec.get("base_height_mm", 0) or 0)
    idx_of = {n: ei for ei, n in name_of.items()}
    # 切れ目: 下段の側は本体に続く（妻側を塞がない）、本体の側は途中の屋根より上だけ塞ぐ
    low_join = [[idx_of[f], "e" if a < 0.5 else "s"] for f, (a, _b) in low.items()]
    open_above = [[idx_of[f], "s" if a < 0.5 else "e", low_top - base] for f, (a, _b) in low.items()]
    main = {**spec, "span_overrides": list(spec.get("span_overrides") or [])
            + [{"face": f, "spans_mm": sp} for f, sp in overrides.items()],
            "_low_ranges": low, "_open_above": open_above,
            # 上段の床から本体の床へ渡る升目は、途中の屋根より上の層で本体の内側の手すり（布材）を付けない
            # （利用者の指摘 2026-10-25: セットバックの足場が本体と回らないようになっている布材を配置しないようにして）
            "_tier_passage": [[ei, a, b, low_top - base] for ei, a, b in passage],
            # 下段は本体と同じ立面を途中の屋根で切る（床の高さが本体とそろう。別に解くとジャッキ・段がずれた）
            "_low_spec": {"height_from_slabs": False, "roof_bridge": False, "_joined_ends": low_join,
                          "scaffold_height_mm": "__MAIN__",
                          "face_eaves_mm": {f: int(round(low_top - base)) for f in low}}}
    # 揃えたスパンで解き直した本体の支柱の位置に、上段の線を合わせる
    r1 = solve({k: v for k, v in main.items() if k not in ("_low_ranges", "_low_spec", "_open_above")})
    m1 = r1.model
    # 下段は本体と同じ足場高さで解いて途中の屋根で切る（面ごとの軒高を入れると全体の軒高まで低くなって段がずれた）
    main["_low_spec"]["scaffold_height_mm"] = int(m1.elevation.total_height)
    main["_low_spec"]["eaves_height_mm"] = int(round(max((m1.eaves_by_face or {}).values(),
                                                         default=float(spec.get("eaves_height_mm") or 0))))
    e1 = {e.edge_index: e for e in m1.plan.edges}
    out_tiers = []
    done = {id(p["sub"]) for p in plan_t}
    for lb, t in tiers:
        if id(t) not in done:
            out_tiers.append((lb, t))
            continue
        pt = next(p for p in plan_t if p["sub"] is t)
        tol = build_outline([tuple(map(float, p)) for p in t["outline_mm"]])
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
        # 床の高さを本体の床（GL から）にそろえる（利用者の指定 2026-10-25: 床の高さは揃えるようにして）
        lv_abs = [float(h) + float(m1.base_height_mm or 0) for h in m1.elevation.level_heights]
        t2 = {**t, "_neighbor_standoffs": fixed, "_skip_end_posts": skip, "_align_levels_mm": lv_abs}
        out_tiers.append((lb, t2))
        notes.append(f"{lb}: 上段の端の支柱は本体の支柱に乗せる（ジャッキベースなし）。上段の離れ {so_t:.0f}、"
                     f"セットバックの先（{'・'.join(low)}）の本体の足場は途中の屋根（GL+{low_top:.0f}）で止める")
    return main, out_tiers, notes
