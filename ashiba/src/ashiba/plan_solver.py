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
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Optional

from .dp import better_desc, insert_desc
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
    # 顧客最小値（これ未満は組めない）。既定は目標下限と同じ250: 250未満の離れは躯体の出入り・
    # 仕上げ厚との干渉余裕が無いので採らない（インチ規格で212mmを採っていた）。200まで許す
    # 案件は入力の standoff.hard_min で下げる
    hard_min: float = 250.0
    fall_protection_limit: float = 300.0  # これを超えると墜落防止措置が必要
    # フィート寸法のくさびで隅を閉じるのに離れが 300 を超えるとき、離れを固定して隅をコーナーステップで
    # 納める（False なら従来どおり離れで閉じ、離れ 350 超の面は内ブラケットで詰める）
    corner_steps: bool = True
    # 面ごとの越えない離れの上限 {辺番号: mm}（敷地境界に本足場を収める。site_boundary.plan_within_boundary）。
    # 顧客最小値と同じく絶対の条件として割付を選ぶ（目標・上限を下げても、端数の少ない 400 を選んで越えた）
    face_caps: Optional[dict] = None


# 割付は基本スパン（1800・1829）で組む（利用者の指定 2026-10-22「割り付けは基本を1800 1829で考えて」）。
# 端数スパン1本の重さ。3 だと、インチの12m面で離れ249mm（下限250に1mm足りない）を嫌って 610×6 で埋めていた
SMALL_SPAN_WEIGHT = 8.0
# 離れの下限の許容（インチ寸法の組合せは数mm刻みにしか合わない。下限250に対し249は同じとみなす）
STANDOFF_TOL_MM = 3.0

# 枠組足場のコーナー処理（仕様4.2の分岐）
# くさび式: 端数は壁離れで吸収する（コーナーで足場板の調整をしない）
# 枠組式  : 離れは固定し、端数はコーナーステップ・足場板で吸収する
# くさびの出隅の隙間（コーナーステップで納める）。作業床どうしの隙間は 3cm 以下（仮設工業会 くさび緊結式足場の
# 技術基準）なのでそのまま、コーナーステップの対応は出隅で 70〜400mm（杉孝のコーナーステップの対応寸法）。
# ただし隙間の両側に建地が立つので、下限は 150（コマ φ106 どうしが当たらず、くさびを打つ手が入る）。
# 利用者の指摘 2026-10-24: 隙間が狭すぎて輪っか部分が干渉している（80・109 の隙間でコマが重なっていた）
# 「閉じた」とみなす隙間は、くさびの遊びで吸収できる 10mm まで。30 にしていたら、面の最後の建地が隅の建地から
# 30 手前に立って2本が重なり（φ48.6）、最後の布材も 30 足りなかった（2026-10-26 のループ。12m×8m のインチ）
WEDGE_GAP_CLOSED_MM = 10
WEDGE_STEP_MIN_MM = 150
# 隣の組の離れで閉じられないとき、自由に解いた離れが隣とこれより離れたら隅をコーナーステップで納める（メートル。2026-10-27）
FIXED_MISS_STEP_MM = 100.0
WEDGE_STEP_MAX_MM = 400
# くさびの隅を閉じるのに動かしてよい離れの帯（利用者の指定 2026-10-23: 270〜350 くらいの躯体との隙間感でいい）。
# 300 を超える面は内側に手すり（内ブラケット・内側の手すり）で墜落を防ぐ
WEDGE_STANDOFF_LO_MM = 270
WEDGE_STANDOFF_STEP_MM = 5
FRAME_CORNER_MIN_GAP_MM = 70    # 建枠を90度回して納めるのに要る最小隙間
FRAME_CORNER_MAX_STEP_MM = 250  # コーナーステップで埋められる上限
# 枠組の出隅は建枠どうしが繋がらないので 70mm 離し、単管（直交クランプ）で繋ぐ。隙間はこの値までに寄せる
# （利用者の指定 2026-10-24: 枠足場は繋がらないから70mm離して単管で繋げけるようにして）
FRAME_TUBE_GAP_MAX_MM = 120


@dataclass
class CornerStep:
    """コーナーに生じる隙間（コーナーステップ・足場板で埋める）.

    枠組は離れ固定で余りを各面の終点のコーナーに出す。くさびは離れを動かして隅を閉じるが、閉じるのに
    離れが 300 を超える・範囲を外れるとき（フィート寸法で多い）は、離れを目標に固定して出隅に隙間を残し、
    コーナーステップで納める（利用者の指定 2026-10-23: 繋がらないところは無理に繋がない）。
    """

    corner_index: int        # 足場ループの頂点番号
    gap_mm: float            # 隙間の大きさ
    ok: bool                 # 納まる範囲（枠組 70〜250、くさび 0〜30 か 150〜400）か
    message: str = ""
    edge_index: int = -1     # 隙間を持つ面（その面の終点の側。くさび）
    at_start: bool = False   # 隙間がその面の始点の側（ブラケットの面へ延ばした本足場の始点。corner_joins）


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
class BridgedSpan:
    """渡した区間の、割付後の辺上での位置（始点コーナー支柱から）."""

    kind: str
    edge_index: int
    start_mm: float
    end_mm: float
    span_count: int        # 区間にかかるスパン数
    width_mm: float
    depth_mm: float        # 増える離れ（斜辺は最大値）
    deep_end: str = "uniform"   # 斜辺: "end"＝区間の終点側で最大／"start"＝始点側で最大


def _locate_bridged_zones(outline: Outline, edges: list, standoffs: list[float]) -> list[BridgedSpan]:
    """均した外形上の区間を、割付後の辺・スパンへ落とす."""
    out: list[BridgedSpan] = []
    n = len(outline.vertices)
    for z in outline.bridged:
        for i, e in enumerate(outline.edges):
            x0, y0 = outline.vertices[i]
            dx, dy = e.direction
            a = (z.p0[0] - x0) * dx + (z.p0[1] - y0) * dy
            b = (z.p1[0] - x0) * dx + (z.p1[1] - y0) * dy
            off = max(abs((z.p0[0] - x0) * dy - (z.p0[1] - y0) * dx),
                      abs((z.p1[0] - x0) * dy - (z.p1[1] - y0) * dx))
            if off > 1e-3 or min(a, b) < -1e-3 or max(a, b) > e.length + 1e-3:
                continue
            base = e.start_sign * standoffs[(i - 1) % n]
            s0, s1 = base + min(a, b), base + max(a, b)
            acc = 0.0
            count = 0
            for sp in edges[i].spans:
                if acc < s1 - 1e-6 and acc + sp > s0 + 1e-6:
                    count += 1
                acc += sp
            deep = z.deep_end
            if deep in ("start", "end") and a > b:     # 区間の向きが辺と逆なら深い側も逆
                deep = "start" if deep == "end" else "end"
            out.append(BridgedSpan(z.kind, e.index, s0, s1, count, z.width_mm, z.depth_mm, deep))
            break
    return out


@dataclass
class PlanResult:
    outline: Outline
    edges: list[EdgePlan]
    standoffs: list[float]
    scaffold_vertices: list[tuple[float, float]]
    warnings: list[str] = field(default_factory=list)
    corner_steps: list[CornerStep] = field(default_factory=list)  # 枠組のみ
    # 実際に使った離れの目標帯。図面・帳票に既定値を書かないために持つ
    standoff_spec: Optional["StandoffSpec"] = None
    # 直線で渡した凹み・張り出し（辺上の区間とスパン数）。措置の本数を出すために持つ
    bridged_zones: list["BridgedSpan"] = field(default_factory=list)
    # 庇・バルコニーをかわすために離れを広げた面（辺 → 広げた mm。obstacles）
    face_shift: dict[int, float] = field(default_factory=dict)

    def face_names(self) -> list[str]:
        """各面の呼び名（方位）。立面図の面名と帳票の見出しに使う.

        外形はCCWで内側が躯体、Edge.outward が外向き法線なので、そこから
        方位を決める。同じ方位が複数あるときは辺番号を添えて区別する
        （南面が2つある建物で、どちらの図か分からなくなるため）。
        """
        raw = [_compass(e.outward) for e in self.outline.edges]
        dup = {n for n in raw if raw.count(n) > 1}
        # self.edges と同じ並び（一部の面だけの足場・面の組の数量でも、辺番号で外形の辺の方位を引く）
        return [
            f"{raw[e.edge_index]}面(辺{e.edge_index})" if raw[e.edge_index] in dup else f"{raw[e.edge_index]}面"
            for e in self.edges
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

    結果はキャッシュから複製して返す。呼び出し側は返ったリストを組合せとして
    保持するので、キャッシュの実体をそのまま渡すと後から書き換えられ得る。
    """
    return {
        s: list(v)
        for s, v in _achievable_core(tuple(sorted(set(coins))), lo, hi).items()
    }


@lru_cache(maxsize=64)
def _achievable_core(
    coins: tuple[int, ...], lo: int, hi: int
) -> dict[int, tuple[int, ...]]:
    """DP本体。同じ系列・同じ帯で何度も呼ばれるのでキャッシュする.

    構成は常に降順のタプルで持つ。以前は比較のたびに両辺をソートしており、
    テスト1本の割付で sorted が数百万回走っていた。
    """
    table_hi = max(hi, max(coins))
    coins_desc = sorted(coins, reverse=True)
    best: list[Optional[tuple[int, ...]]] = [None] * (table_hi + 1)
    best[0] = ()
    for s in range(1, table_hi + 1):
        cur: Optional[tuple[int, ...]] = None
        for c in coins_desc:
            prev = best[s - c] if s - c >= 0 else None
            if prev is None:
                continue
            cand = insert_desc(prev, c)
            if cur is None or better_desc(cand, cur):
                cur = cand
        best[s] = cur
    return {
        s: best[s] for s in range(max(lo, 1), hi + 1) if best[s] is not None
    }


def _small_span_count(spans: list[int], main_span: int) -> int:
    return sum(1 for s in spans if s < main_span)


# ---------------------------------------------------------------- solver

def solve_plan(
    vertices: list[tuple[float, float]],
    master: PartMaster,
    standoff: Optional[StandoffSpec] = None,
    fixed_spans: Optional[dict[int, list[int]]] = None,
    face_min: Optional[dict[int, float]] = None,
    fixed_standoffs: Optional[dict[int, float]] = None,
    tube_marks: Optional[dict[int, list[float]]] = None,
) -> PlanResult:
    """fixed_spans: {辺番号: スパン列（始点から）}。その面はこの構成で固定し、離れだけを解く.

    fixed_standoffs: {辺番号: 離れ mm}。面の組（face_forms）で、ほかの組が建てる隣の面の離れ（その組で解いた値）。
    フィート寸法のくさびでは隅の位置をその離れで決める（隣の面の線で終わる）。

    face_min: {辺番号: 最小の離れ mm}（庇・バルコニーの先端をかわす。obstacles）。その面の躯体線を
    （最小 − 目標）だけ外へずらした外形で割り付け、離れにずらした分を足して返す（隣の面はずらした分だけ
    回り込んで長くなる）。辺番号は割付の外形（整理・反時計回り後）の番号。
    """
    spec = standoff or StandoffSpec()
    coins = master.span_lengths()
    if not coins:
        raise ValidationError(f"系列 {master.series_id} にスパン用布材がありません")
    if face_min:
        shifted = _solve_with_face_shift(vertices, master, spec, fixed_spans, face_min, min(coins))
        if shifted is not None:
            return shifted
    # 最小スパン未満の凹み・張り出しは直線で渡す（増える離れは警告に出る）
    outline = build_outline(vertices, bridge_below_mm=min(coins))
    edges = outline.edges
    n = len(edges)
    main_span = max(coins)

    # 枠組は端数の逃がし先が違う（仕様4.2）。離れを固定し、
    # 余りはコーナーステップで吸収する
    if master.is_frame:
        res = _solve_plan_frame(outline, master, spec, coins)
        res.bridged_zones = _locate_bridged_zones(outline, res.edges, res.standoffs)
        return res

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
        # 「目標長に近い6件」だけだと、規格がmm単位で揃わない系列（インチ）では
        # 端数だらけの合計ばかりが近くに並び、端数1本で組める合計（117mm離れる）
        # が候補から落ちていた（30m面が610スパン×50本になった）。
        # 近い順と端数の少ない順の両方から候補を取る
        nearest = sorted(sums.items(), key=lambda kv: abs(kv[0] - target))[:6]
        cleanest = sorted(
            sums.items(),
            key=lambda kv: (_small_span_count(kv[1], main_span), len(kv[1]),
                            abs(kv[0] - target)),
        )[:6]
        ranked: list[tuple[int, list[int]]] = []
        seen: set[int] = set()
        for kv in nearest + cleanest:
            if kv[0] not in seen:
                seen.add(kv[0])
                ranked.append(kv)
        if fixed_spans and e.index in fixed_spans:
            fixed = [int(v) for v in fixed_spans[e.index]]
            bad = sorted({v for v in fixed if v not in coins})
            if bad:
                raise ValidationError(
                    f"辺{e.index}のスパン指定に系列 {master.series_id} に無い寸法があります"
                    f"（{'・'.join(str(b) for b in bad)}。使える寸法: "
                    + "・".join(str(c) for c in coins) + "）"
                )
            total = sum(fixed)
            if not (lo <= total <= hi):
                raise ValidationError(
                    f"辺{e.index}のスパン指定の合計{total}mm（{len(fixed)}スパン）は、この面の足場長"
                    f"{lo}〜{hi}mm（躯体長{e.length:.0f}mm＋両端の離れ{lo_d:.0f}〜{hi_d:.0f}mm）から外れています。"
                    "合計がこの範囲に入るようスパンを足すか減らしてください"
                )
            ranked = [(total, list(fixed))]
        candidates.append(ranked)

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
    extra_small: dict[int, dict[int, int]] = {}   # 面 → {離れ: 端数スパンが増える本数}
    fixed_failed = False                     # 隣の組の離れで閉じる組合せが無かった軸がある
    for axis in ("x", "y"):
        grp = [e for e in edges if e.axis == axis]
        if not grp:
            continue
        # 隣の面がほかの組なら、その組の離れで閉じる組合せを先に探す（無ければ自由に解き、隅は組の間で合わない）
        got = None
        if fixed_standoffs and not fixed_spans and not master.is_tube:
            try:
                got = _solve_axis(grp, candidates, edges, spec, main_span,
                                  {int(k): float(v) for k, v in fixed_standoffs.items()})
            except ValidationError:
                got = None
            if got is None and any(int(k) in {(e.index - 1) % n for e in grp} | {(e.index + 1) % n for e in grp}
                                   for k in fixed_standoffs):
                fixed_failed = True
        combo, d_solved, feas, extra = got or _solve_axis(grp, candidates, edges, spec, main_span)
        best_combo.update(combo)
        feasible_standoffs.update(feas)
        extra_small.update(extra)
        for idx, d in d_solved.items():
            # 最小二乗の解には微小な数値誤差が乗る。丸めずに閾値比較すると
            # 「ちょうど300mm」が300超と判定され、不要な墜落防止措置の警告が出る
            standoffs[idx] = round(d, 3)
    if fixed_spans and fixed_standoffs:
        # スパンを固定した面の両端の離れの配分を指定どおりに（合計はスパンで決まる。セットバックの上段の離れを合わせる
        # ため本体の面ごとに離れを変える。setback_junctions）
        for idx, v in fixed_standoffs.items():
            if 0 <= int(idx) < n:
                standoffs[int(idx)] = round(float(v), 3)
    tube_fix: dict[int, float] = {}
    if master.is_tube and not fixed_spans:
        # 単管は建地の間隔が自由（布は長い管を重ねて留める）。隣の面がほかの組なら、その面の離れの線で終わるよう
        # 端のスパンで合わせる（利用者の指摘 2026-10-26: 単管抱き足場の始点の建地が本足場の端の建地から 70 ずれて2本立った）
        tube_fix = {int(k): float(v) for k, v in (fixed_standoffs or {}).items() if 0 <= int(k) < n}
        # 規格のスパンの和で離れが原則（spec.min〜spec.max）を外れる面も、離れを目標に戻して端のスパンで合わせる
        # （奥行 5m の単管足場が「離れ350mm > 300mm（スパン構成では動かせません）」になっていた。2026-10-26 のループ）
        top = min(spec.max, spec.fall_protection_limit or spec.max)
        for idx, d in enumerate(standoffs):
            if idx not in tube_fix and not (spec.min - STANDOFF_TOL_MM <= d <= top + STANDOFF_TOL_MM):
                tube_fix[idx] = float(min(spec.target, top))
    if tube_fix:
        for idx, v in tube_fix.items():
            standoffs[idx] = round(v, 3)
        for e in edges:
            s_sum, spans = best_combo[e.index]
            dp = e.start_sign * standoffs[(e.index - 1) % n]
            dn = e.end_sign * standoffs[(e.index + 1) % n]
            target = e.length + dp + dn
            if abs(target - s_sum) > 0.5:
                best_combo[e.index] = (round(target), _refit_tube_spans(
                    spans, round(target) - sum(spans), (e.index - 1) % n in tube_fix, max(coins)))

    if master.is_tube and tube_marks and not fixed_spans:
        # 隣の組の建地がこの単管の面の線上に立つ所（L 字の入隅の本足場の外側の建地など）は、そこに単管の建地を
        # 合わせて共有する（120 ずれて2本立っていた。2026-10-26 のループ）
        for e in edges:
            if tube_marks.get(e.index):
                s_sum, spans = best_combo[e.index]
                best_combo[e.index] = (s_sum, tube_spans_through(spans, tube_marks[e.index], max(coins)))

    # フィート寸法のくさびで、隅を閉じるのに離れが 270〜350 の帯を外れるなら、無理に閉じず、帯の中で閉じられる
    # 隅を最も多くし、閉じない隅はコーナーステップで納める（単管は長さが自由なので要らない。メートル寸法は
    # 300mm 刻みで離れ 250〜350 の中で閉じられるので従来どおり）
    lo_band = _wedge_band_lo(spec)
    # メートルでも、隣の組の離れで閉じられない組（一側足場の面が隣の単管抱き足場の離れ 290 で閉じず、本体の 400 で解いて
    # 隅の建地が敷地境界を越えた。2026-10-27 のループ）は、隅を隙間（コーナーステップ）で納める
    # 隣と 100 以内のずれは、単管の組ならクランプで留められるので離れのまま（隅にコーナーステップを増やさない）
    far_off = fixed_failed and bool(fixed_standoffs) and any(
        abs(float(standoffs[int(k)]) - float(v)) > FIXED_MISS_STEP_MM
        for k, v in fixed_standoffs.items() if 0 <= int(k) < n)
    if (spec.corner_steps and not master.is_tube and not fixed_spans
            and ((_is_feet_series(master)
                  and (fixed_standoffs or any(d > spec.max + STANDOFF_TOL_MM or d < lo_band - STANDOFF_TOL_MM
                                              for d in standoffs)))
                 or far_off)):
        stepped = _solve_plan_wedge_steps(outline, spec, coins, main_span, fixed_standoffs,
                                          "フィート寸法" if _is_feet_series(master) else "布材の規格寸法")
        if stepped is not None:
            stepped.bridged_zones = _locate_bridged_zones(outline, stepped.edges, stepped.standoffs)
            return stepped

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
                feasible_standoffs.get(e.index), d, spec, extra_small.get(e.index)
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
        standoff_spec=spec,
    )
    # 現場で措置を打つ人に「辺2」では伝わらない。面の呼び名で言う
    faces = result.face_names()
    by_index = {e.edge_index: f for e, f in zip(plan_edges, faces)}
    for remedy, edges in remedies.items():
        label = "・".join(by_index.get(i, f"辺{i}") for i in edges)
        warnings.append(f"{label}: {remedy}")
    result.bridged_zones = _locate_bridged_zones(outline, plan_edges, standoffs)
    return result


def _solve_with_face_shift(vertices, master, spec, fixed_spans, face_min, bridge_mm) -> Optional[PlanResult]:
    """面の躯体線を外へずらして割り付け、元の外形と実際の離れに直す。ずらす面が無い・辺が変わるなら None."""
    outline0 = build_outline(vertices, bridge_below_mm=bridge_mm)
    edges0 = outline0.edges
    n = len(edges0)
    shifts = {i: round(float(m) - spec.target, 1) for i, m in face_min.items()
              if 0 <= i < n and float(m) - spec.target > 1.0}
    if not shifts:
        return None
    verts = []
    for i, (vx, vy) in enumerate(outline0.vertices):
        dx = dy = 0.0
        for ei in ((i - 1) % n, i):        # 頂点 i は辺 i-1 の終点・辺 i の始点
            sh = shifts.get(ei, 0.0)
            dx += sh * edges0[ei].outward[0]
            dy += sh * edges0[ei].outward[1]
        verts.append((vx + dx, vy + dy))
    res = solve_plan(verts, master, spec, fixed_spans)
    if len(res.edges) != n or len(res.outline.edges) != n:
        return None
    res.outline = outline0
    res.standoffs = [d + shifts.get(i, 0.0) for i, d in enumerate(res.standoffs)]
    for ep in res.edges:
        ep.standoff = round(ep.standoff + shifts.get(ep.edge_index, 0.0), 3)
    res.face_shift = dict(shifts)
    res.bridged_zones = _locate_bridged_zones(outline0, res.edges, res.standoffs)
    return res


def _feasibility_hint(
    feasible: Optional[set[int]], chosen: float, spec: StandoffSpec,
    extra_small: Optional[dict[int, int]] = None,
) -> str:
    """他にどの離れなら成立したかを添える.

    「350mmしか組めない」のか「300mmも組めるが別の理由で選ばなかった」のかで、
    計画者の打つ手が変わる。前者は建物側か措置側でしか動かせない。
    スパンは真物のみで組むので、成立する離れは形状から離散的に決まる。
    """
    if feasible is None:
        return ""
    if not feasible:
        if spec.min <= chosen <= spec.max:
            # この面は帯内。帯外なのは同じ軸の別の面で、真物では全面を
            # 顧客最小〜最大に収める組合せが無い
            return (
                "（この面は目標帯内。全面を顧客最小〜最大に収める真物の組合せが無く、"
                "帯外の面は建物寸法か措置側での対応になります）"
            )
        return (
            f"（目標帯{spec.min:.0f}〜{spec.max:.0f}mmで真物で組める離れは"
            "ありません。建物寸法か措置側での対応になります）"
        )
    others = sorted(v for v in feasible if abs(v - chosen) > 0.5)
    if not others:
        return "（真物で組める離れはこの値のみ。スパン構成では動かせません）"
    inside = [v for v in others if spec.min <= v <= spec.max]
    if not inside:
        # 全部帯外なら1つずつ「＝目標帯外」を付けて並べても読む側の手は増えない。
        # 帯内の代案が無いことを先に言い、帯外の候補は参考として添える
        return ("（目標帯内で組める離れは他にありません。帯外で組めるのは "
                + "・".join(f"{v}mm" for v in others) + "）")
    parts = []
    for v in others:
        out = "" if spec.min <= v <= spec.max else "＝目標帯外"
        parts.append(f"{v}mm{out}")
    text = "（この形状で組める離れは他に " + "・".join(parts)
    # 採用した離れが帯外なのに帯内の代案があるときは、なぜ採らなかったかを言う。
    # 「250mmでも組める」とだけ書くと、ツールの選択ミスに見える
    # （インチ規格で 241.5mm を採り 250mm を案内していた。250mm は端数スパンが増える）
    chosen_in = spec.min <= chosen <= spec.max
    if not chosen_in and extra_small:
        costs = [(v, extra_small.get(v)) for v in inside if extra_small.get(v) is not None]
        worse = [(v, n) for v, n in costs if n > 0]
        if worse:
            text += "。帯内の" + "・".join(f"{v}mm は端数スパンが{n}本増える" for v, n in worse) \
                + f"ため、離れを{abs(chosen - (spec.min if chosen < spec.min else spec.max)):.1f}mm" \
                + ("下げて" if chosen < spec.min else "上げて") + "端数を減らす方を採っています"
    return text + "）"


def tube_spans_through(spans: list[int], marks: list[float], max_span: int) -> list[int]:
    """単管のスパン列を、面の始点から marks（mm）の位置にも建地が立つように組み直す. 印から 300 未満の建地は
    印へ寄せて（外して）、max_span を超える間は等分する。印がどれも建地と重なっていれば元のまま."""
    xs = [0.0]
    for v in spans:
        xs.append(xs[-1] + v)
    total = xs[-1]
    mk = sorted(float(m) for m in marks if 1.0 < float(m) < total - 1.0)
    if not mk or all(any(abs(m - x) < 2.0 for x in xs) for m in mk):
        return list(spans)
    keep = [x for x in xs[1:-1] if all(abs(x - m) >= 300.0 for m in mk)]
    pts = sorted({0.0, total, *keep, *mk})
    out: list[int] = []
    for a, b in zip(pts, pts[1:]):
        k = max(1, -(-int(round(b - a)) // int(max_span)))
        base = [int(round((b - a) / k))] * k
        base[-1] = int(round(b - a)) - sum(base[:-1])
        out += base
    return out


def _refit_tube_spans(spans: list[int], delta: int, at_start: bool, max_span: int) -> list[int]:
    """単管のスパン列の端（隣の組の面の側）で delta を吸収する。建地の間隔は max_span 以下（安衛則571条一号 1.85m）に、
    300 未満の端数は隣のスパンと合わせる."""
    sp = list(spans) or [0]
    if not at_start:
        sp.reverse()
    if delta > 0 and sp[0] + delta > max_span:
        # 端に入らない分は、いちばん短いスパンに足せるならそこへ（本数を増やさない。1500 → 1668 など）
        k = min(range(len(sp)), key=lambda i: sp[i])
        if sp[k] + delta <= max_span:
            sp[k] += int(delta)
            delta = 0
    if delta < 0 and sp[0] >= max_span:
        # 縮める分は規格の 1800（斜材・シートの升目）を崩さず、1800 でないスパンから引く（端に近い方から）
        k = next((i for i, v in enumerate(sp) if v < max_span and v + delta >= 300), None)
        if k is not None:
            sp[k] += int(delta)
            delta = 0
    sp[0] += int(delta)
    while len(sp) > 1 and sp[0] < 300:
        v = sp.pop(0)
        sp[0] += v
    head = sp.pop(0)
    while head > max_span:
        # 長くなった端は規格の間隔を1本ずつ切り出し、最後の端数は半分（900）と残りに分ける
        if head - max_span // 2 <= max_span:
            sp[:0] = [max_span // 2]
            head -= max_span // 2
        else:
            sp[:0] = [max_span]
            head -= max_span
    sp.insert(0, head)
    if not at_start:
        sp.reverse()
    return sp


def _solve_axis(
    grp: list,
    candidates: list[list[tuple[int, list[int]]]],
    all_edges: list,
    spec: StandoffSpec,
    main_span: int,
    fixed: Optional[dict[int, float]] = None,
) -> tuple[dict[int, tuple[int, list[int]]], dict[int, float], dict[int, set[int]]]:
    """1軸分の辺グループについて、スパン合計の組合せと離れを同時に解く.

    fixed: {辺番号: 離れ}。ほかの組が建てる隣の面の離れ（その値で閉じる組合せだけを採る）。

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
    # 離れの値ごとに、それで組んだときの端数スパンの最少本数（軸の全面合計）。
    # 「250mmでも組めるが採らなかった」理由（端数が何本増えるか）を案内に出すため
    small_by: dict[int, dict[int, int]] = {di: {} for di in d_indices}
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
        fx = [(pos[di], float(v)) for di, v in (fixed or {}).items() if di in pos]
        rows_x, rhs_x = list(rows), list(rhs)
        for k, v in fx:
            # 固定する離れは重みの大きい式で押さえ、あとの整合チェックで外れた組合せを捨てる
            rows_x.append([1000.0 if i == k else 0.0 for i in range(len(d_indices))])
            rhs_x.append(1000.0 * v)
        d = _lstsq_with_target(rows_x, rhs_x, len(d_indices), spec.target)
        if d is None or any(abs(d[k] - v) > 0.5 for k, v in fx):
            continue
        if fx and any(not (spec.hard_min - STANDOFF_TOL_MM <= x <= spec.max + STANDOFF_TOL_MM)
                      for i, x in enumerate(d) if i not in {k for k, _v in fx}):
            # 隣の離れで閉じても、自分の面の離れが範囲を外れるなら採らない（西面が 513 になった）
            continue
        # 整合チェック（真物のみ→式は厳密に成立する必要がある）
        ok = True
        for row, b in zip(rows, rhs):
            if abs(sum(r * x for r, x in zip(row, d)) - b) > 0.5:
                ok = False
                break
        if not ok:
            continue
        # 「他にこの離れでも組める」は、その組合せで全面が顧客最小〜最大に
        # 収まるときだけ挙げる。面ごとに拾うと、他面を425mmにする組合せ由来の
        # 275mmを「他に組める」と案内してしまう（凹み形状で実際に出た）
        n_small = sum(_small_span_count(spans, main_span) for _s, spans in choice)
        if all(spec.hard_min - 0.5 - STANDOFF_TOL_MM <= x <= spec.max + 0.5 for x in d):
            for di, x in zip(d_indices, d):
                v = int(round(x))
                feasible[di].add(v)
                small_by[di][v] = min(small_by[di].get(v, n_small), n_small)
        dev = sum(abs(x - spec.target) for x in d)
        n_over = sum(1 for x in d if x > spec.max or x < spec.min - STANDOFF_TOL_MM)
        n_hard = sum(1 for x in d if x < spec.hard_min - STANDOFF_TOL_MM)
        caps = spec.face_caps or {}
        n_cap = sum(1 for di, x in zip(d_indices, d) if di in caps and x > float(caps[di]) + STANDOFF_TOL_MM)
        # 墜落防止措置が要る面（離れ30cm超）は少ないほどよい
        n_fall = sum(1 for x in d if x > spec.fall_protection_limit)
        # 顧客最小値（hard_min）だけは絶対。それ以外は重み付きで足す。
        # 辞書順（n_over → n_fall → n_small）にしていたときは、離れが目標帯を
        # 8.5mm下回るのを避けるために30m面を610スパン×50本にしていた
        # （インチ規格で実際に起きた）。目標帯外（250〜350の外）は帯内で300超
        # （墜落防止措置）より重く、目標帯外1面 ≒ 端数スパン6〜7本の重さにする
        score = (
            n_hard, n_cap,
            20.0 * n_over + 10.0 * n_fall + SMALL_SPAN_WEIGHT * n_small + dev / 50.0,
            n_small, dev,
        )
        if best is None or score < best[0]:
            best = (score, choice, d, n_small)

    if best is None:
        raise ValidationError("スパン割の整合解が見つかりません（建物寸法と布材規格を確認してください）")
    _score, choice, d, chosen_small = best
    combo = {e.index: c for e, c in zip(grp, choice)}
    d_map = {di: d[pos[di]] for di in d_indices}
    # 採用した離れの端数本数を引いた「増える本数」に直して返す
    extra = {di: {v: n - chosen_small for v, n in m.items()} for di, m in small_by.items()}
    return combo, d_map, feasible, extra


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


def _is_feet_series(master: PartMaster) -> bool:
    from .master import MODULE_INCH, series_module

    try:
        return series_module(master.series_id) == MODULE_INCH
    except Exception:
        return False


def _wedge_gap_ok(gap: float) -> bool:
    return -0.5 <= gap <= WEDGE_GAP_CLOSED_MM or WEDGE_STEP_MIN_MM <= gap <= WEDGE_STEP_MAX_MM


def _pick_spans(coins: list[int], target_len: float, main_span: int, need_exact: bool):
    """target_len 以下で組むスパン列と隙間。need_exact なら隙間 0（入隅の面）."""
    lo = max(min(coins), int(target_len - (0 if need_exact else WEDGE_STEP_MAX_MM)) - 1)
    table = achievable_sums(coins, lo, int(target_len) + 1)
    cands = []
    for s, sp in table.items():
        gap = target_len - s
        if need_exact:
            if abs(gap) > 0.5:
                continue
        elif not _wedge_gap_ok(gap):
            continue
        # 端数スパンの少なさ → スパンの少なさ → 隙間の小ささ（閉じる 0〜30 を先に）
        cands.append(((_small_span_count(sp, main_span), len(sp), 0 if gap <= WEDGE_GAP_CLOSED_MM else 1, gap),
                      sp, gap))
    if not cands:
        return None
    _k, sp, gap = min(cands, key=lambda c: c[0])
    return sp, gap


def _wedge_band_lo(spec: StandoffSpec) -> float:
    """離れの帯の下限. 既定（顧客最小値 250 以上）は 270。入力で顧客最小値を下げていればその値."""
    return float(WEDGE_STANDOFF_LO_MM) if spec.hard_min >= 250 - STANDOFF_TOL_MM else float(spec.hard_min)


def _pick_from_table(table: dict[int, list[int]], tl: float, main_span: int):
    """_pick_spans と同じ選び方を、前もって作った合計の表から（離れの組合せを何度も試すので速く）."""
    cands = []
    for s, sp in table.items():
        gap = tl - s
        if not _wedge_gap_ok(gap):
            continue
        cands.append(((_small_span_count(sp, main_span), len(sp), 0 if gap <= WEDGE_GAP_CLOSED_MM else 1, gap),
                      sp, gap))
    if not cands:
        return None
    _k, sp, gap = min(cands, key=lambda c: c[0])
    return sp, gap


def _closing_spans(table: dict[int, list[int]], tl: float, main_span: int) -> Optional[list[int]]:
    """合計が tl−30〜tl（隙間 30 以下は閉じたとみなす）のスパン列。端数スパンの少ないもの."""
    c = [(_small_span_count(sp, main_span), len(sp), tl - s, sp) for s, sp in table.items()
         if -0.5 <= tl - s <= WEDGE_GAP_CLOSED_MM]
    return min(c, key=lambda v: v[:3])[3] if c else None


def _solve_plan_wedge_steps(outline: Outline, spec: StandoffSpec, coins: list[int],
                            main_span: int, fixed: Optional[dict[int, float]] = None,
                            unit_label: str = "フィート寸法") -> Optional[PlanResult]:
    """くさびの割付を、離れを 270〜350 の帯で動かして閉じられる隅を最も多くし、閉じない隅はコーナーステップで
    納めて解く（解けなければ None）.

    面 i の足場長は 辺長＋始点側の符号×前の面の離れ＋終点側の符号×次の面の離れ なので、面 i が閉じるかは
    離れ d[i-1] と d[i+1] で決まる。離れの並びを 2 つ飛びにたどると輪になるので、輪ごとに先頭の値を固定した
    動的計画法で「閉じない面の数」最小（同じなら目標 300 からのずれの合計が最小）の離れを選ぶ。
    隙間は面の終点の側に置く（その面のスパンは隅の手前で終わり、次の面の出隅の升目は隅のまま）。
    """
    edges = outline.edges
    n = len(edges)
    lo = int(_wedge_band_lo(spec))
    hi = int(spec.max)
    if hi < lo:
        return None
    vals = sorted(set(range(lo, hi + 1, WEDGE_STANDOFF_STEP_MM)) | {int(min(max(spec.target, lo), hi))})
    tables = {}
    for e in edges:
        tables[e.index] = achievable_sums(coins, max(1, int(e.length - 2 * hi) - WEDGE_STEP_MAX_MM - 1),
                                          int(e.length + 2 * hi) + 1)

    def tl_of(i: int, a: float, b: float) -> float:
        e = edges[i]
        return e.length + e.start_sign * a + e.end_sign * b

    cost_cache: dict[tuple[int, float], float] = {}

    def open_cost(face: int, a: float, b: float) -> float:
        """面の費用: 隙間（コーナーステップ）1 ＋ 端数スパン 1本 0.1. 端数だらけで閉じるより隙間を残す方を採る."""
        tl = tl_of(face, a, b)
        k = (face, round(tl, 1))                      # 費用は足場長だけで決まる
        if k not in cost_cache:
            sp = _closing_spans(tables[face], tl, main_span)
            # 閉じた面も、隅の残り（くさびの遊びで吸収する分）が小さい方を採る（1mm あたり 1e-3。離れの目標 300
            # からのずれ 1e-4/mm より重い）
            c = (0.1 * _small_span_count(sp, main_span) + 1e-3 * (tl - sum(sp))) if sp is not None else float("inf")
            got = _pick_from_table(tables[face], tl, main_span)
            if got is not None:
                c = min(c, 1.0 + 0.1 * _small_span_count(got[0], main_span))
            cost_cache[k] = c if c < float("inf") else 10.0
        return cost_cache[k]

    def unary(v: int) -> float:
        return abs(v - spec.target) * 1e-4

    standoffs = [float(spec.target)] * n
    seen: set[int] = set()
    for s0 in range(n):
        if s0 in seen:
            continue
        cyc = []
        v = s0
        while v not in cyc:
            cyc.append(v)
            v = (v + 2) % n
        seen.update(cyc)
        m = len(cyc)
        best = None
        fixed = fixed or {}

        def vals_of(var: int):
            return [fixed[var]] if var in fixed else vals

        for first in vals_of(cyc[0]):
            # cost[v] = (費用, 並び) 直前の変数の値ごと
            layer = {first: (unary(first), [first])}
            for k in range(1, m):
                face = (cyc[k - 1] + 1) % n
                nxt = {}
                for b in vals_of(cyc[k]):
                    cand = None
                    for a, (ca, path) in layer.items():
                        c = ca + open_cost(face, a, b) + unary(b)
                        if cand is None or c < cand[0]:
                            cand = (c, path + [b])
                    nxt[b] = cand
                layer = nxt
            face = (cyc[-1] + 1) % n
            for a, (ca, path) in layer.items():
                c = ca + open_cost(face, a, first)
                if best is None or c < best[0] - 1e-9:
                    best = (c, path)
        for var, val in zip(cyc, best[1]):
            standoffs[var] = float(val)
    exact: dict[int, list[int]] = {}
    for e in edges:
        tl = tl_of(e.index, standoffs[(e.index - 1) % n], standoffs[(e.index + 1) % n])
        sp = _closing_spans(tables[e.index], tl, main_span)
        if sp is not None and open_cost(e.index, standoffs[(e.index - 1) % n],
                                        standoffs[(e.index + 1) % n]) < 1.0 - 1e-9:
            exact[e.index] = sp
    scaffold_verts = scaffold_loop_vertices(outline, standoffs)
    plan_edges: list[EdgePlan] = []
    warnings: list[str] = list(outline.notes)
    corner_steps: list[CornerStep] = []
    for e in edges:
        tl = e.length + e.start_sign * standoffs[(e.index - 1) % n] + e.end_sign * standoffs[(e.index + 1) % n]
        if e.index in exact:
            spans = exact[e.index]
            gap = tl - sum(spans)
        else:
            got = _pick_from_table(tables[e.index], tl, main_span)
            if got is None:
                return None
            spans, gap = got
        plan_edges.append(EdgePlan(
            edge_index=e.index,
            spans=spans,
            scaffold_length=float(sum(spans)),
            standoff=standoffs[e.index],
            owned_post_count=len(spans),
            start_post=scaffold_verts[e.index],
            end_post=scaffold_verts[(e.index + 1) % n],
            remedy=None,
        ))
        if gap > WEDGE_GAP_CLOSED_MM:
            corner_steps.append(CornerStep((e.index + 1) % n, round(gap, 1), True, "", e.index))
    result = PlanResult(
        outline=outline,
        edges=plan_edges,
        standoffs=standoffs,
        scaffold_vertices=scaffold_verts,
        warnings=warnings,
        corner_steps=corner_steps,
        standoff_spec=spec,
    )
    if corner_steps:
        faces = dict(zip([e.edge_index for e in plan_edges], result.face_names()))
        lo_s, hi_s = min(standoffs), max(standoffs)
        band = f"{lo_s:.0f}mm" if abs(hi_s - lo_s) < 0.5 else f"{lo_s:.0f}〜{hi_s:.0f}mm"
        warnings.append(
            f"{unit_label}では全部の隅を離れ {lo}〜{hi}mm の中で閉じられないので、離れを {band} にし、閉じない隅の"
            "隙間をコーナーステップで納めます（" + "・".join(f"{faces[c.edge_index]}の終点 {c.gap_mm:.0f}mm"
                                             for c in corner_steps) + "）")
    return result


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
    min_span = min(coins)
    # 離れは全面で同じ値に固定する。目標（300）だけで解くと、インチの建枠間隔では隙間の窓（70〜250）に
    # 入る組合せが 610 の連続しか無い面が出た（8m面が 1524＋610×11）。目標帯（下限〜上限）を10mm刻みで試し、
    # 端数の建枠間隔がいちばん少なく、隙間が窓に入る離れを採る（同じなら目標に近い方）
    main = max(coins)
    best_d, best_key = spec.target, None
    for d_try in sorted({spec.target} | set(range(int(spec.min), int(spec.max) + 1, 10)),
                        key=lambda v: abs(v - spec.target)):
        bad = n_small = n_sp = n_far = 0
        for e in edges:
            tl = e.length + (e.start_sign + e.end_sign) * d_try
            if tl < min_span:
                bad += 1
                continue
            sp, gap = _frame_spans_and_gap(coins, tl)
            if not (FRAME_CORNER_MIN_GAP_MM <= gap <= FRAME_CORNER_MAX_STEP_MM):
                bad += 1
            if gap > FRAME_TUBE_GAP_MAX_MM:
                n_far += 1               # 70mm に寄らない隅（単管で繋ぐ隙間が広い）
            n_small += sum(1 for v in sp if v < main)
            n_sp += len(sp)
        key = (bad, n_small, n_sp, n_far, abs(d_try - spec.target))
        if best_key is None or key < best_key:
            best_d, best_key = d_try, key
    d = float(best_d)                    # 離れは全面固定
    standoffs = [d] * n

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
        standoff_spec=spec,
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
    # 隙間の小ささだけで選ぶと、短い建枠間隔（610）がマスタにあるときに
    # 30m面を610×50スパンで埋めてしまう（隙間は最小になるが建枠・筋違・
    # 布板が3倍になる）。コーナーステップで埋められる隙間の範囲なら、
    # スパン数が最少（＝長尺の建枠間隔を使う）の構成を採り、隙間はその次
    within = [c for c in fits if c[0] <= FRAME_CORNER_MAX_STEP_MM]
    if within:
        gap, spans = min(within, key=lambda c: (len(c[1]), c[0]))
    elif fits:
        gap, spans = min(fits, key=lambda c: (c[0], len(c[1])))
    else:
        gap, spans = min(candidates, key=lambda c: (abs(c[0]), len(c[1])))
    return spans, gap
