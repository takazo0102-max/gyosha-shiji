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
