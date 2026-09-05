"""付帯設備の取付部・朝顔取付部・昇降機マストの壁つなぎを、格子の壁つなぎと同じ一覧に統合する.

以前は数量だけ「朝顔取付部の壁つなぎ28本」「付帯設備の増設壁つなぎ6本」を別に
足していて、図面（tieList は model.wall_ties）には出ていなかった。格子の壁つなぎと
同じ位置に来る分は同じ金具で兼ねるので二重に数えない。
"""

from __future__ import annotations


from .model import ScaffoldModel, WallTie

KIND_LABEL = {
    "grid": "壁つなぎ",
    "asagao": "朝顔取付部の壁つなぎ",
    "stage": "荷受けステージ取付部の壁つなぎ",
    "hoist": "昇降機マスト控えの壁つなぎ",
}
ATTACHMENT_KINDS = ("asagao", "stage", "hoist")


def kind_labels(model: ScaffoldModel) -> dict[str, str]:
    """用途ラベル。朝顔の種別がセーフウイングなら取付部の名前もそう書く（発注書・内訳で
    「朝顔」と読ませない。届の下書きは「朝顔なし」なので食い違う）."""
    from .model import ASAGAO_KIND_SAFE_WING

    labels = dict(KIND_LABEL)
    a = model.config.asagao
    if a is not None and a.stages > 0 and a.kind == ASAGAO_KIND_SAFE_WING:
        labels["asagao"] = "セーフウイング取付部の壁つなぎ"
    return labels


def _edge(model: ScaffoldModel, idx: int):
    return next((e for e in model.plan.edges if e.edge_index == idx), None)


def _asagao_ties(model: ScaffoldModel) -> list[WallTie]:
    spec = model.config.asagao
    if spec is None or spec.stages <= 0:
        return []
    every = max(1, spec.tie_every_spans)
    out: list[WallTie] = []
    for h in model.asagao_heights():
        for e in model.plan.edges:
            n = max(1, e.span_count // every)
            starts = [0.0]
            for sp in e.spans:
                starts.append(starts[-1] + sp)
            if e.span_count < every:
                xs = [starts[len(e.spans) // 2]]
            else:
                xs = [starts[k * every] for k in range(1, n + 1)]
                # 面長の終端（コーナー支柱）に当たる分は1つ手前に寄せる
                xs = [min(x, starts[-2]) if len(starts) > 2 else x for x in xs]
            for x in xs:
                out.append(WallTie(e.edge_index, x, int(h), "asagao"))
    return out


def _platform_ties(model: ScaffoldModel, platforms) -> list[WallTie]:
    out: list[WallTie] = []
    if platforms is None:
        return out
    levels = model.elevation.level_heights
    n = model.elevation.n_levels
    for st in platforms.stages:
        edge = _edge(model, st.edge_index)
        if edge is None:
            continue
        # 荷取りブラケットの上下付近に必須（日建 p019/p039）。ブラケットは間口の
        # 各支柱に付くので、支柱ごとにブラケットの1つ上と1つ下の作業層に置く
        # （最下層なら根がらみ、最上層なら同じ層）。以前は間口の両端2本だけで、
        # 高さもブラケットと同じ層だった
        posts = [float(st.start_mm)]
        for sp in st.spans(model):
            posts.append(posts[-1] + sp)
        first = int(model.elevation.first_ledger_height)
        for lv in (st.levels or [1]):
            if not (1 <= lv <= n):
                continue
            below = int(levels[lv - 2]) if lv >= 2 else first
            above = int(levels[lv]) if lv < n else int(levels[lv - 1])
            for x in posts:
                for h in sorted({below, above}):
                    out.append(WallTie(st.edge_index, x, h, "stage"))
    for ho in platforms.hoists:
        edge = _edge(model, ho.edge_index)
        if edge is None or ho.tie_every_mm <= 0:
            continue
        reach = ho.reach_height_mm or model.scaffold_height_mm
        n_ties = max(1, int(reach // ho.tie_every_mm))
        for k in range(1, n_ties + 1):
            h = int(min(k * ho.tie_every_mm, reach))
            out.append(WallTie(ho.edge_index, float(ho.position_mm), h, "hoist"))
    return out


def merge_attachment_ties(model: ScaffoldModel, platforms=None) -> dict[str, int]:
    """取付部の壁つなぎを model.wall_ties に足す（同じ位置の金具は兼ねる）.

    何度呼んでも同じ結果（同じ辺・位置・高さが既にあれば足さない）。
    戻り値は由来ごとの本数。
    """
    existing = {
        (t.edge_index, round(t.position_mm), int(t.height_mm)) for t in model.wall_ties
    }
    added: dict[str, int] = {}
    for t in _asagao_ties(model) + _platform_ties(model, platforms):
        key = (t.edge_index, round(t.position_mm), int(t.height_mm))
        if key in existing:
            continue
        existing.add(key)
        model.wall_ties.append(t)
        added[t.kind] = added.get(t.kind, 0) + 1
    return added


def tie_counts(model: ScaffoldModel) -> dict[str, int]:
    """由来ごとの本数（数量・帳票の内訳）."""
    out: dict[str, int] = {}
    for t in model.wall_ties:
        out[t.kind] = out.get(t.kind, 0) + 1
    return out


def has_attachment_ties(model: ScaffoldModel) -> bool:
    return any(t.kind in ATTACHMENT_KINDS for t in model.wall_ties)


def relocate_ties_off_openings(model: ScaffoldModel, openings) -> list[str]:
    """開口部で抜いた支柱（梁枠より下）に当たる壁つなぎを、開口部の両端の支柱へ寄せる.

    格子の壁つなぎは開口部を知らずに決まるので、通路の真ん中（支柱が無い所）に
    金具が描かれ、数量にも入っていた（実機の立面で見つけた）。梁枠より上の支柱は
    梁枠に乗っているので、そこの壁つなぎはそのまま。寄せた先に同じ高さの壁つなぎが
    既にあれば1本にまとめる（同じ位置は同じ金具で兼ねる）。戻り値は寄せた内容の説明。
    """
    if openings is None or not getattr(openings, "openings", None):
        return []
    moved: dict[int, int] = {}
    merged = 0
    for i, o in enumerate(openings.openings):
        beam_h = openings.beam_heights.get(i)
        if beam_h is None or i not in openings.inner_posts:
            continue   # 成立していない開口部（両端が支柱に乗らない等）は触らない
        keep: list[WallTie] = []
        for t in model.wall_ties:
            inside = (t.edge_index == o.edge_index
                      and o.start_mm + 1e-6 < t.position_mm < o.end_mm - 1e-6
                      and t.height_mm < beam_h - 1e-6)
            if not inside:
                keep.append(t)
                continue
            new_x = o.start_mm if (t.position_mm - o.start_mm) <= (o.end_mm - t.position_mm) else o.end_mm
            dup = any(k.edge_index == t.edge_index and abs(k.position_mm - new_x) < 1e-6
                      and k.height_mm == t.height_mm for k in keep)
            if dup:
                merged += 1
            else:
                keep.append(WallTie(t.edge_index, new_x, t.height_mm, t.kind))
            moved[o.edge_index] = moved.get(o.edge_index, 0) + 1
        model.wall_ties = keep
    if not moved:
        return []
    faces = "・".join(f"辺{e} {n}本" for e, n in sorted(moved.items()))
    msg = (f"開口部の通路（支柱を抜いた区間・梁枠より下）に当たる壁つなぎ{faces}を、開口部の両端の"
           "支柱へ寄せました")
    if merged:
        msg += f"（うち{merged}本は寄せた先の壁つなぎと同じ位置なので1本にまとめています）"
    msg += "。寄せた面の水平間隔は法規チェック#4で判定しています"
    return [msg]


def unreachable_bands(model: ScaffoldModel) -> dict[int, list[tuple[float, float]]]:
    """辺ごとに、最長の壁つなぎでも躯体に届かない区間（始点からのmm）.

    渡した区間（凹み・斜辺）で増える離れが（最長品の上限 − 面の必要長さ）を超える所。
    斜辺は線形に増えるので、しきい値を超える側の部分区間になる。
    """
    from .quantity import wall_tie_required_length_mm

    zones = getattr(model.plan, "bridged_zones", None) or []
    cands = [p for p in model.master.by_category("壁つなぎ") if p.adjustable_range()]
    if not zones or not cands:
        return {}
    longest = max(p.adjustable_range()[1] for p in cands)
    out: dict[int, list[tuple[float, float]]] = {}
    for z in zones:
        limit = longest - wall_tie_required_length_mm(model, z.edge_index)
        width = max(z.end_mm - z.start_mm, 1e-9)
        deep = getattr(z, "deep_end", "uniform")
        if z.depth_mm <= limit + 1e-9:
            continue
        if deep == "end":
            band = (z.start_mm + max(limit, 0.0) * width / z.depth_mm, z.end_mm)
        elif deep == "start":
            band = (z.start_mm, z.end_mm - max(limit, 0.0) * width / z.depth_mm)
        else:
            band = (z.start_mm, z.end_mm)
        if band[1] - band[0] > 1e-6:
            out.setdefault(z.edge_index, []).append(band)
    for e, bands in out.items():
        bands.sort()
        merged: list[tuple[float, float]] = []
        for a, b in bands:
            if merged and a <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        out[e] = merged
    return out


def relocate_unreachable_ties(model: ScaffoldModel, label: str = "壁つなぎ") -> list[str]:
    """渡した区間（凹み・斜辺）の中で最長の壁つなぎでも躯体に届かない壁つなぎを、届く位置の支柱へ寄せる.

    開口部の寄せと同じ考え方。同じ辺の支柱位置のうち、その位置で要る長さが最長品の
    範囲に収まる最も近い支柱へ動かす（どちら側でもよい）。届く支柱が無ければ動かさず
    （数量側が名指しで手配に出す）。寄せた先に同じ高さの壁つなぎがあれば1本にまとめる。
    """
    from .quantity import wall_tie_required_length_mm

    zones = getattr(model.plan, "bridged_zones", None) or []
    cands = [p for p in model.master.by_category("壁つなぎ") if p.adjustable_range()]
    if not zones or not cands:
        return []
    longest = max(p.adjustable_range()[1] for p in cands)
    posts_by_edge: dict[int, list[float]] = {}
    for e in model.plan.edges:
        xs = [0.0]
        for sp in e.spans:
            xs.append(xs[-1] + sp)
        posts_by_edge[e.edge_index] = xs
    moved: dict[int, int] = {}
    stuck: dict[int, int] = {}
    merged = 0
    keep: list[WallTie] = []
    for t in model.wall_ties:
        need = wall_tie_required_length_mm(model, t.edge_index, t.position_mm)
        if need <= longest + 1e-6:
            keep.append(t)
            continue
        ok = [x for x in posts_by_edge.get(t.edge_index, [])
              if wall_tie_required_length_mm(model, t.edge_index, x) <= longest + 1e-6]
        if not ok:
            stuck[t.edge_index] = stuck.get(t.edge_index, 0) + 1
            keep.append(t)
            continue
        new_x = min(ok, key=lambda x: (abs(x - t.position_mm), x))
        if any(k.edge_index == t.edge_index and abs(k.position_mm - new_x) < 1e-6
               and k.height_mm == t.height_mm for k in keep):
            merged += 1
        else:
            keep.append(WallTie(t.edge_index, new_x, t.height_mm, t.kind))
        moved[t.edge_index] = moved.get(t.edge_index, 0) + 1
    model.wall_ties = keep
    if not moved:
        return []
    faces = "・".join(f"{model.face_name(e)} {n}本" for e, n in sorted(moved.items()))
    msg = (f"渡した区間（凹み・斜辺）の中で最長の壁つなぎ（〜{longest:.0f}mm）でも躯体に届かない{label}"
           f"{faces}を、届く位置の支柱へ寄せました")
    if merged:
        msg += f"（うち{merged}本は寄せた先の壁つなぎと同じ位置なので1本にまとめています）"
    msg += "。届かない帯の風荷重は壁つなぎの検定から除き、別途の控え（構造の要確認）で受けます"
    return [msg]

