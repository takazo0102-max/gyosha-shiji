"""平面割付ソルバ.

実務手順の自動化（仕様4.1〜4.3）:
- コーナー頂点は固定点。各辺は両端固定でスパン割（真物のみ・切断調整なし）
- 端数は壁離れ（既定250〜350）で吸収。全体XYシフトで対面の離れバランスを最適化
- 離れが350を超える面には対処案（落下防止材／ブラケット）を提示
- 支柱の帰属は「各辺は始点支柱を所有し終点支柱は所有しない」（二重計上防止）

目的関数: 離れの300からの偏差最小 ＋ 小スパン本数最小 ＋ 離れ350超の面数最小
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

from .geometry import Outline, ValidationError, build_outline, scaffold_loop_vertices
from .master import PartMaster


@dataclass
class StandoffSpec:
    target: float = 300.0
    min: float = 250.0
    max: float = 350.0
    hard_min: float = 200.0  # 顧客最小値（これ未満は組めない）


@dataclass
class EdgePlan:
    edge_index: int
    spans: list[int]              # 呼び寸法の並び（始点→終点）
    scaffold_length: float        # コーナー支柱間距離 = sum(spans)
    standoff: float               # この面の壁離れ
    owned_post_count: int         # 始点支柱＋中間支柱（終点は所有しない）
    start_post: tuple[float, float] = (0.0, 0.0)
    end_post: tuple[float, float] = (0.0, 0.0)
    remedy: Optional[str] = None  # 離れ超過時の対処案

    @property
    def span_count(self) -> int:
        return len(self.spans)


@dataclass
class PlanResult:
    outline: Outline
    edges: list[EdgePlan]
    standoffs: list[float]
    scaffold_vertices: list[tuple[float, float]]
    warnings: list[str] = field(default_factory=list)

    @property
    def total_posts(self) -> int:
        """1層あたりの支柱本数（帰属ルールにより二重計上なし）."""
        return sum(e.owned_post_count for e in self.edges)

    @property
    def total_spans(self) -> int:
        return sum(e.span_count for e in self.edges)

    def post_positions(self) -> list[tuple[float, float]]:
        """全支柱位置（帰属ルール順: 各辺の始点＋中間支柱）。
        閉ループなので終点支柱は次辺の始点として一度だけ現れる."""
        pts: list[tuple[float, float]] = []
        for ep, edge in zip(self.edges, self.outline.edges):
            x, y = ep.start_post
            dx, dy = edge.direction
            acc = 0.0
            pts.append((x, y))
            for s in ep.spans[:-1]:
                acc += s
                pts.append((x + dx * acc, y + dy * acc))
        return pts


# ---------------------------------------------------------------- span DP

def achievable_sums(coins: list[int], lo: int, hi: int) -> dict[int, list[int]]:
    """[lo,hi]で構成可能な合計→最良構成（本数最小、次に大部材優先）を返すDP.

    コイン問題。切断調整は存在しないため真物の組合せのみ。
    """
    if hi < max(coins):
        hi = max(coins)
    best: list[Optional[list[int]]] = [None] * (hi + 1)
    best[0] = []
    for s in range(1, hi + 1):
        for c in sorted(coins, reverse=True):
            if s - c >= 0 and best[s - c] is not None:
                cand = best[s - c] + [c]
                if best[s] is None or _better(cand, best[s]):
                    best[s] = cand
    return {
        s: sorted(best[s], reverse=True)
        for s in range(lo, hi + 1)
        if best[s] is not None and s >= lo
    }


def _better(a: list[int], b: list[int]) -> bool:
    if len(a) != len(b):
        return len(a) < len(b)
    return sorted(a, reverse=True) > sorted(b, reverse=True)


def _small_span_count(spans: list[int], main_span: int) -> int:
    return sum(1 for s in spans if s < main_span)


# ---------------------------------------------------------------- solver

def solve_plan(
    vertices: list[tuple[float, float]],
    master: PartMaster,
    standoff: Optional[StandoffSpec] = None,
) -> PlanResult:
    spec = standoff or StandoffSpec()
    outline = build_outline(vertices)
    edges = outline.edges
    n = len(edges)
    coins = master.span_lengths()
    if not coins:
        raise ValidationError(f"系列 {master.series_id} にスパン用布材がありません")
    main_span = max(coins)

    # 各辺の候補スパン合計: 離れが[min,max]のときに実現される長さ帯
    #   S_i = L_i + start_sign*d_prev + end_sign*d_next
    lo_d, hi_d = spec.min, spec.max
    slack = 150.0  # 帯の外側にも候補を持ち（離れ超過→対処案の提示に使う）
    candidates: list[list[tuple[int, list[int]]]] = []
    for e in edges:
        bounds = []
        for dp in (lo_d, hi_d):
            for dn in (lo_d, hi_d):
                bounds.append(e.length + e.start_sign * dp + e.end_sign * dn)
        lo = int(min(bounds) - slack)
        hi = int(max(bounds) + slack)
        sums = achievable_sums(coins, max(lo, main_span), hi)
        if not sums:
            raise ValidationError(f"辺{e.index}(長さ{e.length:.0f})に組めるスパンがありません")
        target = e.length + (e.start_sign + e.end_sign) * spec.target
        ranked = sorted(
            sums.items(),
            key=lambda kv: (abs(kv[0] - target), _small_span_count(kv[1], main_span)),
        )
        candidates.append(ranked[:6])

    # 軸ごとに独立: x方向に走る辺の式はy面の離れのみを含む（直交ポリゴン）
    best_combo: dict[int, tuple[int, list[int]]] = {}
    standoffs = [spec.target] * n
    warnings: list[str] = []
    for axis in ("x", "y"):
        grp = [e for e in edges if e.axis == axis]
        if not grp:
            continue
        combo, d_solved = _solve_axis(grp, candidates, edges, spec, main_span)
        best_combo.update(combo)
        for idx, d in d_solved.items():
            standoffs[idx] = d

    # 結果組み立て
    scaffold_verts = scaffold_loop_vertices(outline, standoffs)
    plan_edges: list[EdgePlan] = []
    for e in edges:
        s_sum, spans = best_combo[e.index]
        d = standoffs[e.index]
        remedy = None
        if d > spec.max:
            remedy = (
                f"離れ{d:.0f}mm > {spec.max:.0f}mm: 落下防止材（層間ネット等）の設置、"
                "または内ブラケットによる床の拡幅を検討してください"
            )
        elif d < spec.hard_min:
            remedy = f"離れ{d:.0f}mm < 顧客最小値{spec.hard_min:.0f}mm: スパン構成の見直しが必要です"
        start_post = scaffold_verts[e.index]
        end_post = scaffold_verts[(e.index + 1) % n]
        plan_edges.append(
            EdgePlan(
                edge_index=e.index,
                spans=spans,
                scaffold_length=float(s_sum),
                standoff=d,
                owned_post_count=len(spans),  # 始点＋中間。終点は次辺が所有
                start_post=start_post,
                end_post=end_post,
                remedy=remedy,
            )
        )
        if remedy:
            warnings.append(f"辺{e.index}: {remedy}")

    return PlanResult(
        outline=outline,
        edges=plan_edges,
        standoffs=standoffs,
        scaffold_vertices=scaffold_verts,
        warnings=warnings,
    )


def _solve_axis(
    grp: list,
    candidates: list[list[tuple[int, list[int]]]],
    all_edges: list,
    spec: StandoffSpec,
    main_span: int,
) -> tuple[dict[int, tuple[int, list[int]]], dict[int, float]]:
    """1軸分の辺グループについて、スパン合計の組合せと離れを同時に解く.

    未知数: グループの辺に隣接する直交面の離れ d
    式:     S_i = L_i + start_sign*d_prev + end_sign*d_next
    ランク落ち分（全体シフト）は離れの300からの最大偏差を最小化するよう決める。
    """
    n_all = len(all_edges)
    # このグループの式に現れる離れ（直交面）のインデックス
    d_indices = sorted(
        {(e.index - 1) % n_all for e in grp} | {(e.index + 1) % n_all for e in grp}
    )
    pos = {di: k for k, di in enumerate(d_indices)}

    best = None  # (score, combo, d_map)
    for choice in itertools.product(*[candidates[e.index] for e in grp]):
        # 連立: A d = b を最小二乗で解き、シフト自由度で偏差を最小化
        rows = []
        rhs = []
        for e, (s_sum, _spans) in zip(grp, choice):
            row = [0.0] * len(d_indices)
            row[pos[(e.index - 1) % n_all]] += e.start_sign
            row[pos[(e.index + 1) % n_all]] += e.end_sign
            rows.append(row)
            rhs.append(s_sum - e.length)
        d = _lstsq_with_target(rows, rhs, len(d_indices), spec.target)
        if d is None:
            continue
        # 整合チェック（真物のみ→式は厳密に成立する必要がある）
        ok = True
        for row, b in zip(rows, rhs):
            if abs(sum(r * x for r, x in zip(row, d)) - b) > 0.5:
                ok = False
                break
        if not ok:
            continue
        dev = sum(abs(x - spec.target) for x in d)
        n_over = sum(1 for x in d if x > spec.max or x < spec.min)
        n_hard = sum(1 for x in d if x < spec.hard_min)
        n_small = sum(_small_span_count(spans, main_span) for _s, spans in choice)
        score = (n_hard, n_over, n_small, dev)
        if best is None or score < best[0]:
            best = (score, choice, d)

    if best is None:
        raise ValidationError("スパン割の整合解が見つかりません（建物寸法と布材規格を確認してください）")
    _score, choice, d = best
    combo = {e.index: c for e, c in zip(grp, choice)}
    d_map = {di: d[pos[di]] for di in d_indices}
    return combo, d_map


def _lstsq_with_target(
    rows: list[list[float]], rhs: list[float], nvar: int, target: float
) -> Optional[list[float]]:
    """小規模な最小二乗（正規方程式＋対角正則化で目標値300へ引き寄せる）.

    係数は±1の疎行列・変数は高々辺数個なのでガウス消去で十分。
    正則化項 eps*(d - target)^2 がランク落ち（全体シフト自由度）を
    「離れの偏差最小」の意味で一意に解決する。
    """
    eps = 1e-6
    a = [[eps if i == j else 0.0 for j in range(nvar)] for i in range(nvar)]
    b = [eps * target] * nvar
    for row, r in zip(rows, rhs):
        for i in range(nvar):
            if row[i] == 0.0:
                continue
            b[i] += row[i] * r
            for j in range(nvar):
                if row[j] != 0.0:
                    a[i][j] += row[i] * row[j]
    # ガウス消去（部分ピボット）
    m = [a[i] + [b[i]] for i in range(nvar)]
    for col in range(nvar):
        piv = max(range(col, nvar), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        m[col] = [v / pv for v in m[col]]
        for r in range(nvar):
            if r != col and m[r][col] != 0.0:
                f = m[r][col]
                m[r] = [v - f * w for v, w in zip(m[r], m[col])]
    return [m[i][nvar] for i in range(nvar)]
