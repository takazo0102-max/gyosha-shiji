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


def plan_run(spans: list[int], stock=STOCK_MM, max_over: int = MAX_OVER_MM) -> TubeRun:
    """面のスパン列から、通しの単管の割付（A）を決める.

    面の長さが規格管（500 刻み）の和に端の出 max_over 以内で収まらないとき（隣の組に合わせた半端なスパンの単管抱き
    足場など）は、端の出を 500 まで広げて解き直す（割り付けられずに止まっていた。2026-10-26 のループ）。
    """
    try:
        return _plan_run(spans, stock, max_over)
    except ValueError:
        if max_over >= MAX_OVER_MM + 500:
            raise
        return _plan_run(spans, stock, MAX_OVER_MM + 500)


def _plan_run(spans: list[int], stock, max_over: int) -> TubeRun:
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
            if q > need + max_over:
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


# ---- 足場板（単管のブラケット足場の床）----
# 利用者の指定（2026-10-22）「足場板にして規定の長さで足場板と足場板は300mmラップするように」。
# 足場板は規定の長さ（杉 厚28×幅240。4.0・3.0・2.0・1.5・1.0M）を面に沿って敷き、継ぎは 300 重ねる。
# 重ねはブラケット（建地の位置）の上で、ブラケットの両側に 100 以上ずつ掛ける（支点の上で重ねる）。
# 面の両端はブラケットから 100〜BOARD_MAX_OVER_MM 出す
BOARD_STOCK_MM = (4000, 3000, 2000, 1500, 1000)
BOARD_LAP_MM = 300
BOARD_BEAR_MM = 100          # 重ね・端がブラケットに掛かる長さの下限
BOARD_MAX_OVER_MM = 300      # 端のブラケットから先へ出す上限
BOARD_LAP_MAX_MM = 600       # 300 重ねで割り付けられない面だけ、重ねをここまで伸ばす（ブラケットの上で重ねるのは同じ）


@dataclass
class BoardRun:
    """足場板の1列の割付. start_mm は面の始点の建地から（負＝手前に出す）。継ぎは BOARD_LAP_MM 重ねる."""

    start_mm: float
    pieces: list[int]
    lap_mm: int = BOARD_LAP_MM
    # 継ぎごとの重ね（len(pieces)−1。None なら全部 lap_mm）。300 重ねで割り付けられない面だけ長く重ねる
    laps: list[int] | None = None

    def lap_after(self, i: int) -> int:
        return self.laps[i] if self.laps else self.lap_mm

    def spans_mm(self) -> list[tuple[float, float]]:
        """各板の（始め, 終わり）."""
        out, s = [], self.start_mm
        for i, p in enumerate(self.pieces):
            out.append((s, s + p))
            if i < len(self.pieces) - 1:
                s = s + p - self.lap_after(i)
        return out

    def items(self) -> list[int]:
        """GDL へ渡す並び（板の長さ。300 以外の重ねは、その継ぎの前の板の後ろに負の数で入れる）."""
        out = []
        for i, p in enumerate(self.pieces):
            out.append(p)
            if i < len(self.pieces) - 1 and self.lap_after(i) != BOARD_LAP_MM:
                out.append(-self.lap_after(i))
        return out

    @property
    def end_mm(self) -> float:
        return self.spans_mm()[-1][1]


def _lap_on_post(end: float, posts: list[float]) -> bool:
    """板の終わり end の重ね [end−300, end] が建地（ブラケット）を両側 100 以上ずつ含むか."""
    return any(p - (end - BOARD_LAP_MM) >= BOARD_BEAR_MM and end - p >= BOARD_BEAR_MM for p in posts[1:-1])


def plan_boards(spans: list[int], stock=BOARD_STOCK_MM, starts=None, end_window=None) -> BoardRun:
    """面の足場板1列の割付. 枚数が少なく、長い板が先.

    starts: 敷き始めの候補（面の始点の建地から mm。既定はブラケットから 100〜300 手前）。
    end_window: 終わりの、終点の建地からの出（下限, 上限）mm。既定は (100, 300)。
    出隅の割付（コーナーを通す・手前で止める）は face_boards_for が渡す。

    300 重ねで割り付けられない面（スパン 1800・1800・1500・600 など。規定の長さの板の継ぎがブラケットに
    乗らない）は、重ねを BOARD_LAP_MAX_MM まで伸ばして割り付け直す（止まっていた。2026-10-26 のループ）。
    """
    try:
        return _plan_boards(spans, stock, starts, end_window)
    except ValueError:
        return _plan_boards_long_laps(spans, stock, starts, end_window)


def _plan_boards(spans, stock, starts, end_window) -> BoardRun:
    posts = post_positions(spans)
    L = int(round(posts[-1]))
    stock = sorted(set(int(s) for s in stock), reverse=True)
    default = starts is None
    if default:
        starts = (-BOARD_BEAR_MM, -150, -200, -250, -BOARD_MAX_OVER_MM)
    lo, hi = end_window or (BOARD_BEAR_MM, BOARD_MAX_OVER_MM)
    best = None
    for start in starts:
        # 板の終わりの位置 → そこまでの最良の並び
        reach: dict[int, tuple] = {}
        frontier = [(int(start), ())]
        while frontier:
            nxt = []
            for pos, seq in frontier:
                for Lb in stock:
                    e = pos + Lb
                    cand = seq + (Lb,)
                    if L + lo <= e <= L + hi:
                        key = (len(cand), e - L, tuple(-v for v in cand))
                        if best is None or key < best[0]:
                            best = (key, start, cand)
                        continue
                    if e >= L or not _lap_on_post(e, posts):
                        continue
                    old = reach.get(e)
                    if old is None or (len(cand), tuple(-v for v in cand)) < (len(old), tuple(-v for v in old)):
                        reach[e] = cand
                        nxt.append((e - BOARD_LAP_MM, cand))
            frontier = nxt
        if default and best is not None and best[0][0] <= max(1, (L + 2 * BOARD_BEAR_MM) // max(stock) + 1):
            break
    if best is None:
        raise ValueError(f"足場板を割り付けられません（面の長さ{L}mm）")
    return BoardRun(start_mm=float(best[1]), pieces=list(best[2]))


def _plan_boards_long_laps(spans, stock, starts, end_window) -> BoardRun:
    """重ねを 300〜BOARD_LAP_MAX_MM（100 刻み）で選べる割付. 重ねはブラケットの両側に 100 以上ずつ掛ける."""
    posts = post_positions(spans)
    L = int(round(posts[-1]))
    stock = sorted(set(int(s) for s in stock), reverse=True)
    if starts is None:
        starts = (-BOARD_BEAR_MM, -150, -200, -250, -BOARD_MAX_OVER_MM)
    lo, hi = end_window or (BOARD_BEAR_MM, BOARD_MAX_OVER_MM)
    best = None
    for start in starts:
        # 次の板の始め → (板の並び, 重ねの並び)。少ない枚数・短い重ね・長い板が先
        reach: dict[int, tuple] = {int(start): ((), ())}
        frontier = [int(start)]
        while frontier:
            nxt = []
            for pos in frontier:
                seq, laps = reach[pos]
                for Lb in stock:
                    e = pos + Lb
                    cand = seq + (Lb,)
                    if L + lo <= e <= L + hi:
                        key = (len(cand), sum(laps), e - L, tuple(-v for v in cand))
                        if best is None or key < best[0]:
                            best = (key, start, cand, laps)
                        continue
                    if e >= L:
                        continue
                    for lap in range(BOARD_LAP_MM, BOARD_LAP_MAX_MM + 1, 100):
                        s2 = e - lap
                        if not any(p - s2 >= BOARD_BEAR_MM and e - p >= BOARD_BEAR_MM for p in posts[1:-1]):
                            continue
                        if s2 <= pos:
                            continue
                        val = (cand, laps + (lap,))
                        old = reach.get(s2)
                        if old is None or (len(val[0]), sum(val[1])) < (len(old[0]), sum(old[1])):
                            reach[s2] = val
                            nxt.append(s2)
            frontier = nxt
    if best is None:
        raise ValueError(f"足場板を割り付けられません（面の長さ{L}mm）")
    return BoardRun(start_mm=float(best[1]), pieces=list(best[2]), laps=list(best[3]))


def staggered_boards(run: BoardRun, spans: list[int], end_window=None) -> BoardRun:
    """隣の列（2枚敷きのもう1枚）: 同じ板を並べ替え、重ねの位置をずらす。成り立たなければ同じ."""
    if len(run.pieces) < 2 or run.laps:
        return run
    posts = post_positions(spans)
    L = posts[-1]
    lo, hi = end_window or (BOARD_BEAR_MM, BOARD_MAX_OVER_MM)
    a_ends = [e for _s, e in run.spans_mm()[:-1]]
    best, best_key = run, None
    seen = set()
    for perm in permutations(run.pieces):
        if perm in seen:
            continue
        seen.add(perm)
        if len(seen) > 5040:
            break
        cand = BoardRun(run.start_mm, list(perm), run.lap_mm)
        ends = [e for _s, e in cand.spans_mm()]
        if not all(_lap_on_post(e, posts) for e in ends[:-1]):
            continue
        if not (L + lo <= ends[-1] <= L + hi):
            continue
        gap = min((abs(x - y) for x in ends[:-1] for y in a_ends), default=0.0)
        key = (gap, tuple(perm))
        if best_key is None or key > best_key:
            best, best_key = cand, key
    return best


def face_boards(spans: list[int], starts=None, end_window=None) -> tuple[BoardRun, BoardRun]:
    a = plan_boards(spans, starts=starts, end_window=end_window)
    return a, staggered_boards(a, spans, end_window)



# 出隅の板（単管の足場。3D の GDL と同じ規則）: コーナーの単管（建地列の外、管の芯々 TUBE_OFF_MM 外）から
# 始点側の面の最初の建地の先まで届く、いちばん短い足場板（1.0M→1.5M→2.0M）。幅木も同じ長さ
TUBE_OFF_MM = 48.6 + 17.0


def corner_board_mm(row_spacing_mm: float) -> int:
    need = float(row_spacing_mm) + TUBE_OFF_MM + 200.0
    return next((L for L in (1000, 1500, 2000) if L >= need), 2000)
