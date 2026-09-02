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
import math
from dataclasses import dataclass, field
from typing import Optional

from .geometry import Outline, ValidationError, build_outline, scaffold_loop_vertices
from .master import PartMaster


@dataclass
class StandoffSpec:
    """壁離れの目標と許容範囲.

    fall_protection_limit（300mm）は法規に基づく境界:
    外壁施工後、建築物と足場の作業床との間隔は30cm以下とすること。
    30cm以下が困難な場合は、手すりを設けるか安全帯を使用させる等の
    墜落防止措置を講じる（足場からの墜落防止のための措置／安衛則）。
    幾何学的に組める範囲（min〜max）とは別の基準なので独立に持つ。
    """

    target: float = 300.0
    min: float = 250.0
    max: float = 350.0
    hard_min: float = 200.0  # 顧客最小値（これ未満は組めない）
    fall_protection_limit: float = 300.0  # これを超えると墜落防止措置が必要


# 枠組足場のコーナー処理（仕様4.2の分岐）
# くさび式: 端数は壁離れで吸収する（コーナーで足場板の調整をしない）
# 枠組式  : 離れは固定し、端数はコーナーステップ・足場板で吸収する
FRAME_CORNER_MIN_GAP_MM = 70    # 建枠を90度回して納めるのに要る最小隙間
FRAME_CORNER_MAX_STEP_MM = 250  # コーナーステップで埋められる上限


@dataclass
class CornerStep:
    """枠組のコーナーに生じる隙間（コーナーステップ・足場板で埋める）."""

    corner_index: int        # 足場ループの頂点番号
    gap_mm: float            # 隙間の大きさ
    ok: bool                 # 70〜250mmに納まっているか
    message: str = ""


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


# 外向き法線の向き → 方位。真北はY+（Archicadの既定と同じ扱い）
_COMPASS_8 = ["東", "北東", "北", "北西", "西", "南西", "南", "南東"]


def _compass(outward: tuple[float, float]) -> str:
    ang = math.degrees(math.atan2(outward[1], outward[0])) % 360.0
    return _COMPASS_8[int((ang + 22.5) % 360.0 // 45.0)]


@dataclass
class PlanResult:
    outline: Outline
    edges: list[EdgePlan]
    standoffs: list[float]
    scaffold_vertices: list[tuple[float, float]]
    warnings: list[str] = field(default_factory=list)
    corner_steps: list[CornerStep] = field(default_factory=list)  # 枠組のみ

    def face_names(self) -> list[str]:
        """各面の呼び名（方位）。立面図の面名と帳票の見出しに使う.

        外形はCCWで内側が躯体、Edge.outward が外向き法線なので、そこから
        方位を決める。同じ方位が複数あるときは辺番号を添えて区別する
        （南面が2つある建物で、どちらの図か分からなくなるため）。
        """
        raw = [_compass(e.outward) for e in self.outline.edges]
        dup = {n for n in raw if raw.count(n) > 1}
        return [
            f"{n}面(辺{e.edge_index})" if n in dup else f"{n}面"
            for n, e in zip(raw, self.edges)
        ]

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

    DPテーブルの大きさと「返す範囲」は別物にしてある。テーブルを広げるついでに
    返す上限まで広げてしまうと、呼び出し側が求めた帯の外の解を混ぜてしまう。
    """
    table_hi = max(hi, max(coins))
    best: list[Optional[list[int]]] = [None] * (table_hi + 1)
    best[0] = []
    for s in range(1, table_hi + 1):
        for c in sorted(coins, reverse=True):
            if s - c >= 0 and best[s - c] is not None:
                cand = best[s - c] + [c]
                if best[s] is None or _better(cand, best[s]):
                    best[s] = cand
    return {
        s: sorted(best[s], reverse=True)
        for s in range(max(lo, 1), hi + 1)
        if best[s] is not None
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

    # 枠組は端数の逃がし先が違う（仕様4.2）。離れを固定し、
    # 余りはコーナーステップで吸収する
    if master.is_frame:
        return _solve_plan_frame(outline, master, spec, coins)

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
        # 探索下限は「組める最小のスパン」。最大スパンで下限を切ると、
        # 短い辺（凹み・小さな張り出し）で最大スパン1本しか候補が出ず、
        # 実際には成立する構成を黙って捨ててしまう。
        # 「大きいスパンを優先する」意図は _small_span_count の評価側で満たす。
        min_span = min(coins)
        sums = achievable_sums(coins, max(lo, min_span), hi)
        if not sums:
            raise ValidationError(
                f"辺{e.index}（躯体長{e.length:.0f}mm）に組めるスパンがありません。"
                f"この辺の足場長は{lo}〜{hi}mmになりますが、最小スパンは{min_span}mmです。"
                "凹みや小さな張り出しが狭すぎて足場面を作れないため、"
                "その区間は足場を回り込ませず直線で通す（渡す）計画にしてください"
            )
        target = e.length + (e.start_sign + e.end_sign) * spec.target
        ranked = sorted(
            sums.items(),
            key=lambda kv: (abs(kv[0] - target), _small_span_count(kv[1], main_span)),
        )
        candidates.append(ranked[:6])

    # 軸ごとに独立: x方向に走る辺の式はy面の離れのみを含む（直交ポリゴン）
    best_combo: dict[int, tuple[int, list[int]]] = {}
    standoffs = [spec.target] * n
    # 外形を整理した内容は黙って飲み込まず、割付の警告として残す
    warnings: list[str] = list(outline.notes)
    # 同じ対処案は面ごとに1行ずつ出さず、対象の辺をまとめて1行にする
    # （凹み形状で同じ文が4行並び、件数だけ増えて読みにくかった）
    remedies: dict[str, list[int]] = {}
    # 面ごとに「他にどの離れなら成立したか」。選択の余地があるのか、
    # 形状から一意に決まるのかで打つ手が変わる
    feasible_standoffs: dict[int, set[int]] = {}
    for axis in ("x", "y"):
        grp = [e for e in edges if e.axis == axis]
        if not grp:
            continue
        combo, d_solved, feas = _solve_axis(grp, candidates, edges, spec, main_span)
        best_combo.update(combo)
        feasible_standoffs.update(feas)
        for idx, d in d_solved.items():
            # 最小二乗の解には微小な数値誤差が乗る。丸めずに閾値比較すると
            # 「ちょうど300mm」が300超と判定され、不要な墜落防止措置の警告が出る
            standoffs[idx] = round(d, 3)

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
        elif d > spec.fall_protection_limit:
            # 組める範囲だが法規上の措置が要る帯。黙って通さない
            remedy = (
                f"離れ{d:.0f}mm > {spec.fall_protection_limit:.0f}mm: "
                "外壁施工後の建物と作業床の間隔は30cm以下が原則です。"
                "手すりの設置、または安全帯の使用等の墜落防止措置を講じてください"
            )
        elif d < spec.min:
            # 顧客最小値は満たすが目標下限を下回る帯。躯体との干渉余裕が小さいので
            # 黙って通さず、現場で確認すべき旨を出す
            remedy = (
                f"離れ{d:.0f}mm が目標下限{spec.min:.0f}mmを下回ります"
                f"（顧客最小値{spec.hard_min:.0f}mmは満たす）。"
                "躯体の出入り・断熱材・仕上げ厚との干渉を現場で確認してください"
            )
        start_post = scaffold_verts[e.index]
        end_post = scaffold_verts[(e.index + 1) % n]
        if remedy:
            # 表にも警告にも同じ本文を出す（別々にすると片方だけ情報が欠ける）
            remedy += _feasibility_hint(
                feasible_standoffs.get(e.index), d, spec
            )
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
            remedies.setdefault(remedy, []).append(e.index)

    result = PlanResult(
        outline=outline,
        edges=plan_edges,
        standoffs=standoffs,
        scaffold_vertices=scaffold_verts,
        warnings=warnings,
    )
    # 現場で措置を打つ人に「辺2」では伝わらない。面の呼び名で言う
    faces = result.face_names()
    by_index = {e.edge_index: f for e, f in zip(plan_edges, faces)}
    for remedy, edges in remedies.items():
        label = "・".join(by_index.get(i, f"辺{i}") for i in edges)
        warnings.append(f"{label}: {remedy}")
    return result


def _feasibility_hint(
    feasible: Optional[set[int]], chosen: float, spec: StandoffSpec
) -> str:
    """他にどの離れなら成立したかを添える.

    「350mmしか組めない」のか「300mmも組めるが別の理由で選ばなかった」のかで、
    計画者の打つ手が変わる。前者は建物側か措置側でしか動かせない。
    スパンは真物のみで組むので、成立する離れは形状から離散的に決まる。
    """
    if feasible is None:
        return ""
    if not feasible:
        return (
            f"（目標帯{spec.min:.0f}〜{spec.max:.0f}mmで真物で組める離れは"
            "ありません。建物寸法か措置側での対応になります）"
        )
    others = sorted(v for v in feasible if abs(v - chosen) > 0.5)
    if not others:
        return "（真物で組める離れはこの値のみ。スパン構成では動かせません）"
    parts = []
    for v in others:
        out = "" if spec.min <= v <= spec.max else "＝目標帯外"
        parts.append(f"{v}mm{out}")
    return "（この形状で組める離れは他に " + "・".join(parts) + "）"


def _solve_axis(
    grp: list,
    candidates: list[list[tuple[int, list[int]]]],
    all_edges: list,
    spec: StandoffSpec,
    main_span: int,
) -> tuple[dict[int, tuple[int, list[int]]], dict[int, float], dict[int, set[int]]]:
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
    # 成立した離れの値を集める。「350mmしか組めない」のか「300mmも組めるが
    # 別の理由で選ばなかった」のかで、計画者の打つ手が変わる
    feasible: dict[int, set[int]] = {di: set() for di in d_indices}
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
        for di, x in zip(d_indices, d):
            if spec.hard_min - 0.5 <= x <= spec.max + 0.5:
                feasible[di].add(int(round(x)))
        dev = sum(abs(x - spec.target) for x in d)
        n_over = sum(1 for x in d if x > spec.max or x < spec.min)
        n_hard = sum(1 for x in d if x < spec.hard_min)
        # 墜落防止措置が要る面（離れ30cm超）は少ないほどよい
        n_fall = sum(1 for x in d if x > spec.fall_protection_limit)
        n_small = sum(_small_span_count(spans, main_span) for _s, spans in choice)
        score = (n_hard, n_over, n_fall, n_small, dev)
        if best is None or score < best[0]:
            best = (score, choice, d)

    if best is None:
        raise ValidationError("スパン割の整合解が見つかりません（建物寸法と布材規格を確認してください）")
    _score, choice, d = best
    combo = {e.index: c for e, c in zip(grp, choice)}
    d_map = {di: d[pos[di]] for di in d_indices}
    return combo, d_map, feasible


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


def _solve_plan_frame(
    outline: Outline,
    master: PartMaster,
    spec: StandoffSpec,
    coins: list[int],
) -> PlanResult:
    """枠組足場の平面割付（仕様4.2の分岐）.

    くさび式は端数を壁離れで吸収するが、枠組は建枠が定尺で離れを動かしにくいため
    **離れを固定し、余りをコーナーステップ・足場板で吸収する**。

    さらに枠組はコーナーで建枠を90度回して納めるため、
    直交する建枠どうしが干渉しない隙間（70mm以上）が要る。
    余りが70mm未満になる場合は1スパン落として隙間を開ける。
    """
    edges = outline.edges
    n = len(edges)
    d = spec.target                      # 離れは全面固定
    standoffs = [d] * n
    min_span = min(coins)

    plan_edges: list[EdgePlan] = []
    # 外形を整理した内容は黙って飲み込まず、割付の警告として残す
    warnings: list[str] = list(outline.notes)
    corner_steps: list[CornerStep] = []
    scaffold_verts = scaffold_loop_vertices(outline, standoffs)

    for e in edges:
        # 離れ固定なので面の長さは一意に決まる
        target_len = e.length + (e.start_sign + e.end_sign) * d
        if target_len < min_span:
            raise ValidationError(
                f"辺{e.index}（躯体長{e.length:.0f}mm）は足場長{target_len:.0f}mmとなり、"
                f"最小スパン{min_span}mmを下回ります。"
                "その区間は足場を回り込ませず直線で通す（渡す）計画にしてください"
            )
        spans, gap = _frame_spans_and_gap(coins, target_len)
        plan_edges.append(EdgePlan(
            edge_index=e.index,
            spans=spans,
            scaffold_length=float(sum(spans)),
            standoff=d,
            owned_post_count=len(spans),
            start_post=scaffold_verts[e.index],
            end_post=scaffold_verts[(e.index + 1) % n],
            remedy=None,
        ))
        # 余りは終点側のコーナーに出る
        corner = (e.index + 1) % n
        ok = FRAME_CORNER_MIN_GAP_MM <= gap <= FRAME_CORNER_MAX_STEP_MM
        msg = ""
        if gap < FRAME_CORNER_MIN_GAP_MM:
            msg = (
                f"コーナー{corner}: 隙間{gap:.0f}mm < {FRAME_CORNER_MIN_GAP_MM}mm。"
                "建枠を90度回して納める余地がありません。"
                "離れを広げるか、1スパン落としてコーナーステップで調整してください"
            )
        elif gap > FRAME_CORNER_MAX_STEP_MM:
            msg = (
                f"コーナー{corner}: 隙間{gap:.0f}mm > {FRAME_CORNER_MAX_STEP_MM}mm。"
                "コーナーステップで埋めきれません。役物スパンの追加、"
                "または離れの見直しが必要です"
            )
        corner_steps.append(CornerStep(corner, round(gap, 1), ok, msg))
        if msg:
            warnings.append(msg)

    return PlanResult(
        outline=outline,
        edges=plan_edges,
        standoffs=standoffs,
        scaffold_vertices=scaffold_verts,
        warnings=warnings,
        corner_steps=corner_steps,
    )


def _frame_spans_and_gap(coins: list[int], target_len: float) -> tuple[list[int], float]:
    """建枠のスパン構成と、コーナーに残る隙間を返す.

    隙間は 70mm 以上（建枠の干渉回避）を満たす最小のものを選ぶ。
    満たせる構成が無ければ、隙間が最小の構成を返す（呼び出し側で警告する）。
    """
    limit = int(target_len)
    table = achievable_sums(coins, min(coins), max(limit, min(coins)))
    candidates = [
        (target_len - s, spans) for s, spans in table.items() if s <= target_len
    ]
    if not candidates:
        # 最短構成しか置けない
        return [min(coins)], target_len - min(coins)
    fits = [c for c in candidates if c[0] >= FRAME_CORNER_MIN_GAP_MM]
    if fits:
        # 干渉を避けられる中で隙間が最小＝部材を最大限使う構成
        gap, spans = min(fits, key=lambda c: (c[0], len(c[1])))
    else:
        gap, spans = min(candidates, key=lambda c: (abs(c[0]), len(c[1])))
    return spans, gap
