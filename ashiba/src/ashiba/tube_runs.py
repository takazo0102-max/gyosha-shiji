"""単管の通し（布・手すり・中桟・根がらみ）を規定の長さの単管と直線ジョイントで割り付ける.

利用者の指定（2026-10-22）「単管種類つけて規定の長さ　単管と単管の間にジョイント」。以前は布・手すりを
スパンごとに1本（スパンより少し長い単管を重ねて留める）で描き・数えていた。実際は面の端から端まで
規定の長さ（日建リース カタログVol.10 p372 の単管パイプ）の単管を直線ジョイント（PCJ、p377）で継いで通し、
建地ごとに直交クランプ（抱き足場の床は3連クランプ）で留める。

- 通しは面の始点の建地から END_MM 手前に出して始め、終点の建地の END_MM 先まで届かせる（はみ出しは
  MAX_OVER_MM まで）。本数が少ない割付を選び、同じ本数なら はみ出しが少ない・長い単管が先の割付
- 継ぎ（PCJ 長さ216）は建地のクランプから JOINT_CLEAR_MM 以上離す
- 継ぎは同じ断面に集めない（安衛則571条の考え方。上下・内外で隣り合う通しの継ぎをずらす）。
  同じ単管の組を並べ替えた2つ目の割付（B）を作り、通しごとに A・B を交互に使う（数量は同じ）
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

# 規定の長さ（mm）。カタログ p372 の単管パイプのうち 0.5m 刻みの品（3.6M・2.7M 等の半端な長さは通しに使わない）
STOCK_MM = (6000, 5500, 5000, 4500, 4000, 3500, 3000, 2500, 2000, 1500, 1000)
END_MM = 100            # 端の建地から外へ出す長さ（クランプを掛ける）
JOINT_CLEAR_MM = 150    # 継ぎを建地のクランプから離す（PCJ 216 の半分＋クランプの口の半分 程度）
MAX_OVER_MM = 400       # 終点の先へのはみ出しの上限
STAGGER_MM = 500        # 隣り合う通しの継ぎをこれ以上ずらしたい

# 識別色（カタログ p372 の長さ別一覧表）。3D で単管の両端に塗る
TUBE_COLORS = {
    6000: "水色", 5500: "赤", 5000: "グレー", 4500: "茶", 4000: "青", 3500: "ピンク", 3000: "黄",
    2500: "黒", 2000: "オレンジ", 1500: "緑", 1000: "紫", 500: "シルバー",
    3600: "緑", 2700: "濃紺", 2200: "若草色", 1800: "ベージュ", 1200: "蛍光青",
}


@dataclass
class TubeRun:
    """1つの通しの割付. start_mm は面の始点の建地から（負＝手前に出す）."""

    start_mm: float
    pieces: list[int]

    @property
    def end_mm(self) -> float:
        return self.start_mm + sum(self.pieces)

    @property
    def joints_mm(self) -> list[float]:
        """継ぎの位置（面の始点の建地から）."""
        out, x = [], self.start_mm
        for p in self.pieces[:-1]:
            x += p
            out.append(x)
        return out


def post_positions(spans: list[int]) -> list[float]:
    xs = [0.0]
    for s in spans:
        xs.append(xs[-1] + s)
    return xs


def _clear_of_posts(x: float, posts: list[float]) -> bool:
    return all(abs(x - p) >= JOINT_CLEAR_MM for p in posts)


def plan_run(spans: list[int], stock=STOCK_MM) -> TubeRun:
    """面のスパン列から、通しの単管の割付（A）を決める."""
    posts = post_positions(spans)
    need = int(round(posts[-1])) + 2 * END_MM
    stock = sorted(set(int(s) for s in stock), reverse=True)
    # 位置（始点から mm）→ そこまでの最良の並び。少ない本数、同じなら長い単管が先（タプルの大きい方）
    best: dict[int, tuple] = {0: ()}
    for pos in sorted(range(0, need, 100)):
        if pos not in best:
            continue
        seq = best[pos]
        for L in stock:
            q = pos + L
            if q < need and not _clear_of_posts(q - END_MM, posts):
                continue
            if q > need + MAX_OVER_MM:
                continue
            cand = seq + (L,)
            old = best.get(q)
            if old is None or (len(cand), tuple(-v for v in cand)) < (len(old), tuple(-v for v in old)):
                best[q] = cand
    ends = [(len(s), q - need, tuple(-v for v in s), q) for q, s in best.items() if q >= need]
    if not ends:
        raise ValueError(f"単管の通しを割り付けられません（長さ{need}mm）")
    _n, _over, _neg, q = min(ends)
    return TubeRun(start_mm=-END_MM, pieces=list(best[q]))


def staggered(run: TubeRun, spans: list[int]) -> TubeRun:
    """同じ単管の組を並べ替え、継ぎが A とずれる割付（B）. 継げない並びしか無ければ A のまま."""
    if len(run.pieces) < 2:
        return run
    posts = post_positions(spans)
    a = run.joints_mm
    best, best_key = run, None
    seen = set()
    for perm in permutations(run.pieces):
        if perm in seen:
            continue
        seen.add(perm)
        if len(seen) > 5040:
            break
        cand = TubeRun(run.start_mm, list(perm))
        js = cand.joints_mm
        if not all(_clear_of_posts(x, posts) for x in js):
            continue
        gap = min((abs(x - y) for x in js for y in a), default=0.0)
        key = (min(gap, STAGGER_MM), gap, tuple(perm))
        if best_key is None or key > best_key:
            best, best_key = cand, key
    return best


def face_runs(spans: list[int]) -> tuple[TubeRun, TubeRun]:
    """面の通しの割付 A と B（同じ単管の組。継ぎをずらす）."""
    a = plan_run(spans)
    return a, staggered(a, spans)
