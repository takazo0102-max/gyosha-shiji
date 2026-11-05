"""入隅で2つの面の升目が重ならないように納める（利用者の指摘 2026-10-24: 入りすみが重なっているよ）.

割付は面を内側建地列から内側建地列まで解くので、入隅では隅で終わる面（A）と隅から始まる面（B）が、
隅の 建地列間隔×建地列間隔 の升目を両方とも持ち、支柱・床・手すりが二重になっていた。

熟練の作業者の組み方に合わせて:
- B（隅から始まる面）を通す。最初のスパンを建地列間隔（914 など）にして、A の外側建地列の位置に支柱を立てる
- A（隅で終わる面）は B の外側建地列で止める。割り切れない分はコーナーステップで B の外側の布材へ渡す
- B の最初のスパンは外側の手すり・幅木を付けない（A の床から B の床へ歩いて渡る。auto の部材編集）
- 隙間が無いときは A の終点の内側建地は B の始点の外側建地と同じ1本（A は描かない）

割付（離れ・スパン）は解いたあとで直す。B の最初に入れたスパンの分は B の終点の隙間で受ける（隙間が
コーナーステップの範囲に収まらなければ、その隅は直さずに注記する）。
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .plan_solver import (WEDGE_GAP_CLOSED_MM, WEDGE_STEP_MAX_MM, WEDGE_STEP_MIN_MM, CornerStep,
                          _small_span_count, achievable_sums)


def _gap_ok(gap: float) -> bool:
    return -0.5 <= gap <= WEDGE_GAP_CLOSED_MM or WEDGE_STEP_MIN_MM <= gap <= WEDGE_STEP_MAX_MM


def _pick(coins: list[int], target: float, main: int, prefer_exact: bool = True) -> Optional[tuple[list[int], float]]:
    """合計が target 以下で隙間が 0〜30 か 150〜400 のスパン列（隙間の小さい・端数の少ない順）."""
    lo = max(min(coins), int(target - WEDGE_STEP_MAX_MM) - 1)
    table = achievable_sums(coins, lo, int(target) + 1)
    cands = []
    for s, sp in table.items():
        gap = target - s
        if not _gap_ok(gap):
            continue
        closed = 0 if gap <= WEDGE_GAP_CLOSED_MM else 1
        cands.append(((closed if prefer_exact else 0, _small_span_count(sp, main), len(sp), gap), sp, gap))
    if not cands:
        return None
    _k, sp, gap = min(cands, key=lambda c: c[0])
    return list(sp), float(gap)


def _first_span_w(spans: list[int], w: int, coins: list[int], main: int) -> Optional[tuple[list[int], float]]:
    """最初のスパンを w にしたスパン列と、合計の差（元 − 新。終点の隙間に足す）."""
    if spans and spans[0] == w:
        return list(spans), 0.0
    if w in spans:
        rest = list(spans)
        rest.remove(w)
        return [w] + rest, 0.0
    got = _pick(coins, sum(spans) - w, main)
    if got is None:
        return None
    sp, d = got
    return [w] + sp, d


def _run(ep, oe) -> float:
    """面の始点の支柱から隅（終点）までの長さ（終点の隙間を含む）."""
    return ((ep.end_post[0] - ep.start_post[0]) * oe.direction[0]
            + (ep.end_post[1] - ep.start_post[1]) * oe.direction[1])


def trim_inner_corners(plan, row_mm: float, coins: list[int]):
    """入隅の重なりを直した plan と、つないだ隅 [(A, B, 隙間 mm)] と注記を返す."""
    w = int(round(row_mm))
    if w not in coins or not plan.edges:
        return plan, [], []
    main = max(coins)
    n = len(plan.outline.edges)
    eps = {e.edge_index: e for e in plan.edges}
    steps = list(plan.corner_steps or [])
    joins: list[tuple[int, int, float]] = []
    first_fixed: set[int] = set()
    notes: list[str] = []
    names = dict(zip([e.edge_index for e in plan.edges], plan.face_names()))
    for b, ob in enumerate(plan.outline.edges):
        a = (b - 1) % n
        if ob.start_corner != "入隅" or a not in eps or b not in eps:
            continue
        if any(c.edge_index == b and c.at_start for c in steps):
            continue
        ea, eb = eps[a], eps[b]
        oa = plan.outline.edges[a]
        # B: 最初のスパンを建地列間隔に。差は終点の隙間で受ける
        gb0 = _run(eb, ob) - sum(eb.spans)
        got_b = _first_span_w(eb.spans, w, coins, main)
        if got_b is None or not _gap_ok(gb0 + got_b[1]):
            notes.append(f"{names.get(a, a)}と{names.get(b, b)}の入隅は、{names.get(b, b)}の最初のスパンを{w}に"
                         "できないので升目が重なったままです（スパンを指定して直してください）")
            continue
        spans_b, d_b = got_b
        # A: B の外側建地列で止める（隅までの長さ − 建地列間隔）。割り切れない分は終点の隙間（コーナーステップ）
        # A が別の入隅を通す面（最初のスパンを w にした）なら、その w は残す
        head = [w] if a in first_fixed and ea.spans and ea.spans[0] == w else []
        got_a = _pick(coins, _run(ea, oa) - w - sum(head), main)
        if got_a is None:
            notes.append(f"{names.get(a, a)}を{names.get(b, b)}の外側建地列で止めるスパンの組合せが無いので、"
                         "入隅の升目が重なったままです")
            continue
        spans_a, ga = got_a
        spans_a = head + spans_a
        da = oa.direction
        eps[a] = dataclasses.replace(
            ea, spans=spans_a, scaffold_length=float(sum(spans_a)), owned_post_count=len(spans_a),
            end_post=(ea.end_post[0] - da[0] * w, ea.end_post[1] - da[1] * w))
        eps[b] = dataclasses.replace(eb, spans=spans_b, scaffold_length=float(sum(spans_b)),
                                     owned_post_count=len(spans_b))
        steps = [c for c in steps if not (c.edge_index == a and not c.at_start)
                 and not (c.edge_index == b and not c.at_start)]
        if ga > WEDGE_GAP_CLOSED_MM:
            steps.append(CornerStep((a + 1) % n, round(ga, 1), True, "", a))
        gb = gb0 + d_b
        if gb > WEDGE_GAP_CLOSED_MM:
            steps.append(CornerStep((b + 1) % n, round(gb, 1), True, "", b))
        joins.append((a, b, round(ga, 1)))
        first_fixed.add(b)
        notes.append(
            f"{names.get(a, a)}と{names.get(b, b)}の入隅: {names.get(b, b)}を通し（最初のスパン {w}）、"
            f"{names.get(a, a)}は{names.get(b, b)}の外側建地列で止めます"
            + (f"（隙間 {ga:.0f}mm はコーナーステップ）" if ga > WEDGE_GAP_CLOSED_MM else "")
            + f"。{names.get(b, b)}の最初のスパンは外側の手すり・幅木を付けず、床を渡ります（利用者の指摘 2026-10-24: "
            "入りすみが重なっている）")
    if not joins:
        return plan, [], notes
    plan = dataclasses.replace(plan, edges=[eps[e.edge_index] for e in plan.edges], corner_steps=steps)
    return plan, joins, notes
