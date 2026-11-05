"""山留め支保工の部材（切梁・腹起し・火打ち・中間杭）. 利用者の指定（2026-11-06）「縦横の切梁と中間杭も足して 切張り・腹起こしは
手動でできるようにして LOD高く」.

部品 ashiba_shiho（部材1本・中間杭1本に1つ）。縦横の切梁は 山留め壁（retaining.py の support "grid"）が割り付けて scripts/ywall_run.py が
置き、手で引いた線からは scripts/shiho_run.py が置く。調べた値と出典は research_notes/山留めの種類/支保工の付属部材.md.

決め（出典）
- 主材はリース材 30HA・35HA・40HA（100・150・200 kg/m）。長さ 1.0〜2.5m と 3.0〜7.0m の 0.5m 刻み、端板 16mm、継手は END 部の
  ボルト締めと両フランジのカバープレート 30P（600×300 t12・17kg）（ヒロセ 鋼製山留総合カタログ p.15〜16・p.05）
- 切梁の 50cm 以下の不足は補助ピース（100・200・300）とキリンジャッキ（450〜600）で補う（ヒロセ p.09）。ジャッキは切梁1本に1台・
  千鳥に（藤田金屬 p.15）、ジャッキカバー 30JS-N（1,500・51kg: ヒロセ p.16）
- 2方向の切梁は上下に重ねて交差させ、下段・上段の順に組む（ヒロセ p.09・藤田 p.16）。交差部ごとにアングルピース FLP（L-75 550・5.5kg）
  と交叉部直ボルト SB-750（M22×750・2.4kg）で上下を留める（ヒロセ p.09・p.16・p.26）。ボルトは4本・アングルは上下に2本ずつ【読み取り:
  ジェコス p.23 の写真】
- 腹起しも上下段に分け、角は隅部ピース 30CN（445×400×260・50kg）で上下をつなぐ（ヒロセ p.06・p.15）
- 中間杭は H-300×300 以上を切梁の交点に（中部地整 3-1-62・旧 公衆災害防止対策要綱 土木 第51）。切梁受けブラケットは杭1本に1個
  （ヒロセ p.06）で BL40N（650×450 L-75×75×9・17kg: ジェコス p.31）、締付用 U ボルト DU 30B（340×350 M22・4kg: ジェコス p.24）
- 杭は交点の斜めの隅（2本の切梁の脇）に置く・杭頭は GL・根入れは山留め壁と同じ【目安。長さは支持力と座屈の計算で】
- 切梁火打ち（利用者の指定 2026-11-06「火打も入れて」）: 切梁の両端の左右に対称に 45°（九州 共2-29・中部 3-1-64）。主材 1.0m＋火打受ピース
  0.5m×2（数量要領 R8 1-11-4）で、腹起しに当たる点は切梁の芯から約 1.5m（火打ブロック 30HB と同じ大きさ: ヒロセ p.17）【主材の長さは目安】。
  隣の切梁の火打ち・隅火打ち・中間杭と当たる端は、片側だけだと偏心するので左右とも入れない

座標（mm）: 平面は プロジェクトの x・y、深さ z は GL から下を正（部材の芯）。中間杭の z は杭頭、bottom は先端.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ashiba import retaining as RT

LEASE = {"H-300": ("30HA", 100.0), "H-350": ("35HA", 150.0), "H-400": ("40HA", 200.0)}     # ヒロセ p.15〜23
SHAPES = tuple(LEASE)
MAIN_MM = tuple(float(v) for v in list(range(1000, 2501, 500)) + list(range(3000, 7001, 500)))
AUX_MM = {100.0: 32.0, 200.0: 45.0, 300.0: 55.0}       # 補助ピース 30D-1〜3 の長さ: kg（ヒロセ p.15）
AUX_SETS = ((), (100.0,), (200.0,), (300.0,), (300.0, 100.0), (300.0, 200.0), (300.0, 300.0))
JACK_RANGE = (450.0, 600.0)                            # キリンジャッキ KJ-150 の伸縮（ヒロセ p.09）
JACK_MID = 525.0
END_T_MM = 16.0                                        # 主材の端板（ヒロセ p.15 の図）
COVER = {"H-300": ("30P", 600.0, 12.0, 17.0), "H-350": ("35P", 600.0, 12.0, 20.0), "H-400": ("40P", 600.0, 12.0, 22.6)}
# 30P・35P はヒロセ p.16・p.20。40P の質量は 600×400×12 の鋼の重さ【目安】
JACK_COVER = ("30JS-N", 1500.0, 476.0, 51.0)           # ジャッキカバー（ヒロセ p.16）
CROSS_ANGLE = ("FLP", 550.0, 75.0, 9.0, 5.5)           # アングルピース（ヒロセ p.16。L-75×75 の厚さは図から【読み取り】）
CROSS_BOLT = ("SB-750", 750.0, 22.0, 2.4)              # 交叉部直ボルト（ヒロセ p.26）
CROSS_HOLE_MM = 340.0                                  # アングルピースの孔の間（ヒロセ p.16 の 550 の図: 55＋50＋340＋50＋55）
BRACKET = ("BL40N", 650.0, 450.0, 670.0, 17.0)         # 切梁受けブラケット（ジェコス p.31「切梁用」）
UBOLT = ("DU 30B", 340.0, 350.0, 4.0)                  # 締付用 U ボルト（ジェコス p.24）
CORNER_PIECE = ("30CN", 445.0, 400.0, 260.0, 50.0)     # 隅部ピース（ヒロセ p.15）
PILE_SHAPE = "H-300"                                   # 中間杭（H-300×300 以上: 中部地整 3-1-62）
PILE_GAP_MM = 50.0                                     # 切梁の脇と中間杭のすき間【目安】
WALE_BRACKET_KG = 7.0                                  # 腹起しのブラケット BL30N（ジェコス p.31）
HIUCHI_S_MAIN_MM = 1000.0                              # 切梁火打ちの主材【目安】
HIUCHI_S_LEG_MM = (HIUCHI_S_MAIN_MM + 2 * RT.PIECE_DEDUCT_MM) / math.sqrt(2.0)   # 切梁の脇からの脚
SUB_RATIO = (0.22, 0.04)                               # 副部材の比率 (A) リース・(B) 全損（国総研 数量要領 R8 1-11-4）
KINDS = {"strut": "切梁", "wale": "腹起し", "hiuchi": "火打ち", "pile": "中間杭"}
KIND_NO = {"strut": 1, "wale": 2, "hiuchi": 3, "pile": 4}

SOURCES = {
    "hirose": "ヒロセ 鋼製山留総合カタログ（2024-11）p.05〜29 https://www.hirose-net.com/technique/pdf/kousei-yamadome.pdf",
    "gecoss": "ジェコス 鋼製山留製品（2025-03）p.23〜31 https://www.gecoss.co.jp/products_service/pdf/yamadome.pdf",
    "fujita": "藤田金屬 鋼製山留 主材・部材 p.15〜17 https://www.fujita-kz.com/pdf/items/jyukasetsu/kousei-yamadomeshuzai.pdf",
    "chubu": "中部地方整備局 河川構造物設計要領 第3編 第1章 仮設工 3-1-62 https://www.cbr.mlit.go.jp/kawatomizu/kouzou/pdf/20_01kasetsukou.pdf",
    "youkou": "旧 建設工事公衆災害防止対策要綱 土木工事編（H5）第51 https://www.mlit.go.jp/common/001221757.pdf",
    "nilim": "国総研 土木工事数量算出要領 第1編 11章 仮設工（R8.4）1-11-4 https://www.nilim.go.jp/lab/pbg/theme/theme2/sr/yoryo0804/s-0804-1-11.pdf",
}


@dataclass
class Member:
    """支保工の部材1本（中間杭は1本の杭）."""
    kind: str                                          # strut・wale・hiuchi・pile
    a: tuple                                           # 始め（平面 mm）。中間杭は杭の芯
    b: tuple = (0.0, 0.0)                              # 終わり（中間杭は向き: 杭からブラケットの先の向きの点）
    z: float = 1000.0                                  # GL からの深さ mm（部材の芯。中間杭は杭頭）
    shape: str = "H-300"
    tier: int = 0                                      # 0 下段・1 上段（2方向の切梁は上下に重ねる）
    level: int = 0                                     # 支保工の段（0 が1段目）
    name: str = ""
    jack: int = 0                                      # キリンジャッキ 0 無し・1 始めの側・2 終わりの側
    crossings: list = field(default_factory=list)      # 上段の切梁: 下段と交わる所（始めから mm）と下段の形 [(x, 下段の H)]
    bottom: float = 0.0                                # 中間杭の先端（GL から mm）
    brackets: list = field(default_factory=list)       # 中間杭: 切梁受けブラケットの天端の深さ mm（段ごと）
    reach: float = 0.0                                 # 中間杭: 杭の芯から下段の切梁の芯まで mm
    wale_brackets: list = field(default_factory=list)  # 手で置いた腹起し: ブラケットの位置（始めから mm）
    side: int = 1                                      # 火打ち: 受ピースの底の向き（始めから見て 1 左へ開く・-1 右へ開く）

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b) if self.kind != "pile" else self.bottom - self.z

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.b[1] - self.a[1], self.b[0] - self.a[0]))


# ---- 主材の割付 ----

def split_main(total: float) -> list[float]:
    """主材の長さの合計（0.5m の倍数）→ 定尺の並び（長いものから。7.0m を多く、端数は 1.0m 以上に）."""
    if total < MAIN_MM[0] - 1e-6:
        return []
    n = math.ceil(total / MAIN_MM[-1] - 1e-9)
    out = [MAIN_MM[-1]] * (n - 1)
    rest = total - MAIN_MM[-1] * (n - 1)
    if rest < MAIN_MM[0] - 1e-6 and out:
        out[-1] -= MAIN_MM[0] - rest
        rest = MAIN_MM[0]
    out.append(rest)
    return sorted(out, reverse=True)


def compose(length: float, jack: bool = True) -> list[tuple[str, float]]:
    """部材の長さ → 端からの並び [("jack" | "aux" | "main", 長さ mm)].

    切梁（jack）: 主材＋補助ピース＋キリンジャッキ（450〜600）で長さに合わせる。補助ピースの少ない組、次にジャッキが中ほどの組.
    腹起し・火打ち: 主材を 0.5m 刻みで長さ以下に、残りを補助ピースで（100 未満の残りはすき間・裏込め）."""
    if jack:
        best = None
        for aux in AUX_SETS:
            room = length - sum(aux)
            lo, hi = room - JACK_RANGE[1], room - JACK_RANGE[0]
            m = math.floor(hi / 500.0 + 1e-9) * 500.0
            if m < lo - 1e-6 or (0 < m < MAIN_MM[0]):
                continue
            j = room - m
            key = (len(aux), abs(j - JACK_MID))
            if best is None or key < best[0]:
                best = (key, aux, m, j)
        if best is None:
            return [("jack", length)]
        _k, aux, m, j = best
        return [("jack", j)] + [("aux", v) for v in aux] + [("main", v) for v in split_main(m)]
    m = math.floor(length / 500.0 + 1e-9) * 500.0
    if m < MAIN_MM[0]:
        m = 0.0
    rest = length - m
    aux = []
    for v in (300.0, 200.0, 100.0):
        while rest >= v - 1e-6:
            aux.append(v)
            rest -= v
    return [("main", v) for v in split_main(m)] + [("aux", v) for v in aux]


def segments(m: Member) -> list[tuple[str, float]]:
    """部材の始めからの並び（ジャッキが終わりの側なら逆に）."""
    if m.kind == "pile":
        return []
    if m.kind == "hiuchi":                             # 主材の長さは受ピース 0.5m ずつを控除（数量要領 R8 1-11-4）
        p = RT.PIECE_DEDUCT_MM
        return [("piece", p)] + compose(max(0.0, m.length - 2 * p), jack=False) + [("piece", p)]
    seq = compose(m.length, jack=(m.kind == "strut" and m.jack > 0))
    return list(reversed(seq)) if m.jack == 2 else seq


# ---- 縦横の切梁（山留め壁から） ----

def _rot(p, c, s):
    return (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)


def _unrot(p, c, s):
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _cuts(poly, axis: int, v: float) -> list[tuple[float, float]]:
    """多角形を 軸 axis の値 v の直線で切った中の区間 [(t0, t1)]（もう一方の軸の値）."""
    ts = []
    o = 1 - axis
    for p, q in zip(poly, poly[1:] + poly[:1]):
        if (p[axis] - v) * (q[axis] - v) < 0 or (abs(p[axis] - v) < 1e-9 and q[axis] != v):
            if abs(q[axis] - p[axis]) < 1e-9:
                continue
            t = (v - p[axis]) / (q[axis] - p[axis])
            if 0.0 <= t < 1.0:
                ts.append(p[o] + (q[o] - p[o]) * t)
    ts.sort()
    return [(ts[i], ts[i + 1]) for i in range(0, len(ts) - 1, 2)]


def offset_polygon(pts: list, d: float) -> list:
    """時計回りの多角形を中（右）へ d だけずらす（辺どうしを交わらせる）."""
    lines = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        L = math.dist(a, b) or 1.0
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        lines.append(((a[0] + u[1] * d, a[1] - u[0] * d), u))
    out = []
    for k in range(len(lines)):
        (p1, u1), (p2, u2) = lines[k - 1], lines[k]
        den = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(den) < 1e-9:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / den
        out.append((p1[0] + u1[0] * t, p1[1] + u1[1] * t))
    return out


def frame_angle(w) -> float:
    """縦横の向き（いちばん長い辺の向き、度）."""
    e = max(w.edges, key=lambda x: x.length)
    return math.degrees(math.atan2(e.b[1] - e.a[1], e.b[0] - e.a[0]))


def wale_front(w) -> list:
    """腹起しの前の面（根切りの側）の多角形 mm."""
    H = RT.H_SHAPES[RT.wale_shape(w)[0]][0]
    return offset_polygon(RT.orient(w.pts, True), RT.face_offset(w) + RT.WALE_GAP_MM + H)


def _stations(lo: float, hi: float, clear: float) -> list[float]:
    """切梁の位置: 両端から clear（隅火打ちをよける）の間を 5m 以下に等分して両端を含む. 狭ければ真ん中に1本."""
    a, b = lo + clear, hi - clear
    if b - a < 1.0:
        return [(lo + hi) / 2.0]
    k = max(1, math.ceil((b - a) / RT.STRUT_PITCH_MM - 1e-6))
    return [a + (b - a) * j / k for j in range(k + 1)]


def hiuchi_pair(E, u, B: float, z: float, shape: str, tier: int, level: int, name: str) -> list[Member]:
    """切梁の端（腹起しの前の面の点 E、切梁の向き u）の左右の切梁火打ち. 始めが腹起し、終わりが切梁の脇."""
    out = []
    L = HIUCHI_S_LEG_MM
    for s in (1, -1):
        n = (-u[1] * s, u[0] * s)
        a = (E[0] + n[0] * (B / 2.0 + L), E[1] + n[1] * (B / 2.0 + L))
        b = (E[0] + u[0] * L + n[0] * B / 2.0, E[1] + u[1] * L + n[1] * B / 2.0)
        out.append(Member("hiuchi", a, b, z=z, shape=shape, tier=tier, level=level, name=name, side=s))
    return out


def _room(st: list, i: int, lo: float, hi: float, reach: float, need: float) -> bool:
    """切梁 i の左右に火打ちが入るか（隣の切梁の火打ちと、隅火打ちの当たる所 reach に当たらない）."""
    below = st[i - 1] + need if i else lo + reach
    above = st[i + 1] - need if i + 1 < len(st) else hi - reach
    return st[i] - need >= below - 1e-6 and st[i] + need <= above + 1e-6


def grid(w) -> list[Member]:
    """閉じた山留め壁の縦横の切梁（段ごと・下段は長い辺に直角の向き）と、切梁火打ち、交点の中間杭."""
    if not (w.closed and w.wales):
        return []
    shape = RT.wale_shape(w)[0]
    H, B, *_ = RT.H_SHAPES[shape]
    th = math.radians(frame_angle(w))
    c, s = math.cos(th), math.sin(th)
    poly = [_rot(p, c, s) for p in wale_front(w)]
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    hi = any(e.hiuchi for e in w.edges)
    clear = RT.HIUCHI_LEG_MM + RT.HIUCHI_PIECE[0] / 2.0 + B / 2.0 + 100.0 if hi else 0.0
    lines = []                                         # (tier, axis, 位置, t0, t1)
    st = (_stations(min(xs), max(xs), clear), _stations(min(ys), max(ys), clear))
    for x in st[0]:                                    # 下段: 長い辺に直角（局所 y の向き）
        for t0, t1 in _cuts(poly, 0, x):
            if t1 - t0 > 1000.0:
                lines.append((0, 0, x, t0, t1))
    for y in st[1]:                                    # 上段: 長い辺に平行
        for t0, t1 in _cuts(poly, 1, y):
            if t1 - t0 > 1000.0:
                lines.append((1, 1, y, t0, t1))
    need = B / 2.0 + HIUCHI_S_LEG_MM + RT.HIUCHI_PIECE[0] / 2.0          # 切梁の芯から腹起しの上の受ピースの先まで
    reach = RT.HIUCHI_LEG_MM + RT.HIUCHI_PIECE[0] / 2.0 if hi else 0.0   # 角から隅火打ちの受ピースの先まで
    pile_off = B / 2.0 + PILE_GAP_MM + RT.H_SHAPES[PILE_SHAPE][0]        # 交点から中間杭の手前の面まで
    ends = []                                          # 切梁火打ちの入る端 (線の番号, 端の値, 向き)
    w.hi_skipped = 0
    if w.strut_hiuchi:
        for j, (_tier, axis, v, t0, t1) in enumerate(lines):
            lim = (xs, ys)[axis]
            room = _room(st[axis], st[axis].index(v), min(lim), max(lim), reach, need)
            for t, sg in ((t0, 1.0), (t1, -1.0)):
                flat = all(any(abs(e - t) < 1.0 for c in _cuts(poly, axis, v + d) for e in c) for d in (-need, need))
                clear_x = all(abs(q - t) >= HIUCHI_S_LEG_MM + RT.HIUCHI_PIECE[0] / 2.0 + pile_off for q in st[1 - axis])
                if room and flat and clear_x:
                    ends.append((j, t, sg))
                else:
                    w.hi_skipped += 1
    out: list[Member] = []
    for lv, z in enumerate(w.wales):
        for j, (tier, axis, v, t0, t1) in enumerate(lines):
            if axis == 0:
                pa, pb = (v, t0), (v, t1)
            else:
                pa, pb = (t0, v), (t1, v)
            out.append(Member("strut", _unrot(pa, c, s), _unrot(pb, c, s), z=z - tier * H, shape=shape, tier=tier, level=lv,
                              name=f"{w.name} 切梁{lv + 1}段-{'下' if tier == 0 else '上'}{j + 1}", jack=1 + (j + lv) % 2))
    braces = []
    for lv, z in enumerate(w.wales):
        for j, t, sg in ends:
            tier, axis, v = lines[j][:3]
            E = _unrot((v, t) if axis == 0 else (t, v), c, s)
            d = _unrot((0.0, sg) if axis == 0 else (sg, 0.0), c, s)
            braces += hiuchi_pair(E, d, B, z - tier * H, shape, tier, lv, f"{w.name} 切梁火打ち{lv + 1}段")
    piles = crossings(out)
    embed = w.embed_mm
    return out + braces + make_piles(out, piles, top=0.0, bottom=w.depth + embed, name=w.name)


def oneway_hiuchi(w) -> list[Member]:
    """1方向の切梁（山留め壁の部品が描く）の切梁火打ち."""
    if not (w.wales and w.strut_hiuchi):
        return []
    shape = RT.wale_shape(w)[0]
    H, B, *_ = RT.H_SHAPES[shape]
    f = RT.face_offset(w) + RT.WALE_GAP_MM + H
    need = B / 2.0 + HIUCHI_S_LEG_MM + RT.HIUCHI_PIECE[0] / 2.0
    reach = RT.HIUCHI_LEG_MM + RT.HIUCHI_PIECE[0] / 2.0
    out = []
    w.hi_skipped = 0
    for e in w.edges:
        ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
        n = (uy, -ux)
        for i, x in enumerate(e.strut_x):
            if not _room(e.strut_x, i, f, e.length - f, reach, need):
                w.hi_skipped += 1
                continue
            E = (e.a[0] + ux * x + n[0] * f, e.a[1] + uy * x + n[1] * f)
            for lv, z in enumerate(w.wales):
                out += hiuchi_pair(E, n, B, z, shape, 0, lv, f"{e.name} 切梁火打ち{lv + 1}段")
    return out


def members(w) -> list[Member]:
    """山留め壁に付けて部品 ashiba_shiho で置く部材（縦横の切梁一式か、1方向の切梁の火打ち）."""
    return grid(w) if RT.use_grid(w) else oneway_hiuchi(w)


def crossings(members: list[Member]) -> list[tuple]:
    """同じ段の下段と上段の切梁の交点を上段の部材に控え、交点の一覧 [(点, 下段, 上段)] を返す."""
    out = []
    struts = [m for m in members if m.kind == "strut"]
    for up in struts:
        if up.tier != 1:
            continue
        up.crossings = []
        for lo in struts:
            if lo.tier != 0 or lo.level != up.level:
                continue
            p = _seg_x(lo.a, lo.b, up.a, up.b)
            if p is None:
                continue
            up.crossings.append((math.dist(up.a, p), RT.H_SHAPES[lo.shape][0]))
            out.append((p, lo, up))
        up.crossings.sort()
    return out


def _seg_x(a, b, c, d, tol: float = 1.0):
    """線分 ab と cd の交点（端から tol の内。交わらなければ None）."""
    r = (b[0] - a[0], b[1] - a[1])
    q = (d[0] - c[0], d[1] - c[1])
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    La, Lc = math.hypot(*r) or 1.0, math.hypot(*q) or 1.0
    if -tol / La <= t <= 1 + tol / La and -tol / Lc <= u <= 1 + tol / Lc:
        return (a[0] + r[0] * t, a[1] + r[1] * t)
    return None


def make_piles(members: list[Member], cross: list[tuple], top: float, bottom: float, name: str = "",
               shape: str = PILE_SHAPE) -> list[Member]:
    """交点（平面の同じ所は段をまとめて1本）に中間杭. 杭は2本の切梁の脇の斜めの隅、ブラケットは下段の切梁の下（段ごと）."""
    Hp, Bp, *_ = RT.H_SHAPES[shape]
    by_pt: dict = {}
    for p, lo, up in cross:
        k = (round(p[0] / 10.0), round(p[1] / 10.0))
        by_pt.setdefault(k, []).append((p, lo, up))
    out = []
    for i, k in enumerate(sorted(by_pt), 1):
        rows = by_pt[k]
        p, lo, up = rows[0]
        Blo = RT.H_SHAPES[lo.shape][1]
        Bup = RT.H_SHAPES[up.shape][1]
        ul = _unit(lo.a, lo.b)
        uu = _unit(up.a, up.b)
        dl = Blo / 2.0 + PILE_GAP_MM + Hp / 2.0          # 下段の切梁の芯から杭の芯（下段に直角）
        du = Bup / 2.0 + PILE_GAP_MM + Bp / 2.0          # 上段の切梁の芯から（上段に直角）
        n_lo = (-ul[1], ul[0])                           # 下段に直角（上段の向きに近い）
        if n_lo[0] * uu[0] + n_lo[1] * uu[1] < 0:
            n_lo = (-n_lo[0], -n_lo[1])
        n_up = (-uu[1], uu[0])
        if n_up[0] * ul[0] + n_up[1] * ul[1] < 0:
            n_up = (-n_up[0], -n_up[1])
        ctr = (p[0] + n_lo[0] * dl + n_up[0] * du, p[1] + n_lo[1] * dl + n_up[1] * du)
        toward = (ctr[0] - n_lo[0] * 1000.0, ctr[1] - n_lo[1] * 1000.0)
        brs = sorted({round(lo2.z + RT.H_SHAPES[lo2.shape][0] / 2.0, 1) for _p, lo2, _u in rows})
        out.append(Member("pile", ctr, toward, z=top, shape=shape, name=f"{name} 中間杭{i}".strip(), bottom=bottom,
                          brackets=list(brs), reach=dl))
    return out


def _unit(a, b):
    L = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


# ---- 手で引いた線から ----

def manual(lines: list[dict]) -> list[Member]:
    """手で引いた線（{kind, a, b, depths, shape, tier, jack, name}）→ 部材. tier が None の切梁は向きで決める（最初に出た向きが下段・
    それと 45°を超えて違う向きが上段）."""
    out = []
    first_dir = None
    for ln in lines:
        if ln["kind"] == "strut" and first_dir is None:
            first_dir = _unit(ln["a"], ln["b"])
    for i, ln in enumerate(lines):
        kind = ln["kind"]
        shape = ln.get("shape") or "H-300"
        H = RT.H_SHAPES[shape][0]
        tier = ln.get("tier")
        if kind == "strut" and tier is None:
            u = _unit(ln["a"], ln["b"])
            tier = 0 if first_dir is None or abs(u[0] * first_dir[0] + u[1] * first_dir[1]) > math.cos(math.radians(45)) else 1
        tier = int(tier or 0)
        for lv, z in enumerate(ln["depths"]):
            m = Member(kind, tuple(ln["a"]), tuple(ln["b"]), z=float(z) - (tier * H if kind == "strut" else 0.0), shape=shape,
                       tier=tier, level=lv, name=f"{ln.get('name') or KINDS[kind]}-{lv + 1}段")
            if kind == "strut" and ln.get("jack", True):
                m.jack = 1 + (i + lv) % 2
            if kind == "hiuchi":
                m.side = ln.get("side") or 1
            if kind == "wale":
                L = m.length
                k = max(1, math.ceil((L - 2 * RT.BRACKET_END_MM) / RT.BRACKET_PITCH_MM - 1e-6))
                m.wale_brackets = [RT.BRACKET_END_MM + (L - 2 * RT.BRACKET_END_MM) * j / k for j in range(k + 1)]
            out.append(m)
    return out


def hiuchi_sides(members: list[Member], tol: float = 400.0) -> None:
    """手で引いた火打ちの受ピースの向き: 始めの近くの腹起し・切梁に底を沿わせる（無ければそのまま）."""
    bars = [m for m in members if m.kind in ("wale", "strut")]
    for h in (m for m in members if m.kind == "hiuchi"):
        ax = _unit(h.a, h.b)
        for m in bars:
            if m.level != h.level:
                continue
            d = _unit(m.a, m.b)
            t = (h.a[0] - m.a[0]) * d[0] + (h.a[1] - m.a[1]) * d[1]
            off = abs((h.a[0] - m.a[0]) * d[1] - (h.a[1] - m.a[1]) * d[0])
            if off > tol or not -tol <= t <= m.length + tol:
                continue
            if d[0] * ax[0] + d[1] * ax[1] > 0:
                d = (-d[0], -d[1])
            cr = ax[0] * d[1] - ax[1] * d[0]
            if abs(cr) > 0.1:
                h.side = 1 if cr > 0 else -1
                break


def manual_piles(lines: list[dict], top: float, bottom: float, shape: str = PILE_SHAPE) -> list[Member]:
    """手で中間杭を指す線の点ごとに杭（ブラケットの向きは線の向き、段は depths）."""
    out = []
    Hp = RT.H_SHAPES[shape][0]
    for ln in lines:
        u = _unit(ln["a"], ln["b"])
        for k, p in enumerate((ln["a"], ln["b"])):
            out.append(Member("pile", tuple(p), (p[0] + u[0] * 1000.0, p[1] + u[1] * 1000.0), z=top, shape=shape,
                              name=f"{ln.get('name') or '中間杭'}-{k + 1}", bottom=bottom,
                              brackets=[float(z) + 150.0 for z in ln["depths"]], reach=Hp / 2.0 + PILE_GAP_MM + 150.0))
    return out


# ---- 数量 ----

def quantities(members: list[Member]) -> list:
    """支保工の数量（主材は定尺ごとの本数と t、付属部品は1個ずつ。比率の照合も）."""
    Qty = RT.Qty
    out = []
    main_t = 0.0
    for kind in ("strut", "wale", "hiuchi"):
        ms = [m for m in members if m.kind == kind]
        if not ms:
            continue
        by_shape: dict = {}
        for m in ms:
            by_shape.setdefault(m.shape, []).append(m)
        for shape, group in by_shape.items():
            code, kg = LEASE.get(shape, (shape, RT.H_SHAPES[shape][4]))
            pieces: dict = {}
            aux: dict = {}
            jacks = 0
            for m in group:
                for t, L in segments(m):
                    if t == "main":
                        pieces[L] = pieces.get(L, 0) + 1
                    elif t == "aux":
                        aux[L] = aux.get(L, 0) + 1
                    elif t == "jack":
                        jacks += 1
            Lsum = sum(m.length for m in group)
            t = sum(L * n for L, n in pieces.items()) / 1000.0 * kg / 1000.0
            main_t += t
            levels = sorted({m.level for m in group})
            out.append(Qty(KINDS[kind], f"{shape}（{code} {kg:g}kg/m）・{len(levels)}段", len(group), "本",
                           f"芯の延べ {Lsum / 1000:.1f}m・主材 {t:.2f}t"))
            for L in sorted(pieces, reverse=True):
                out.append(Qty(f"  主材 {code}", f"L={L / 1000:g}m", pieces[L], "本",
                               f"{pieces[L] * L / 1000 * kg / 1000:.2f}t（定尺 1.0〜2.5・3.0〜7.0m の 0.5m 刻み: ヒロセ p.15）"))
            nj = sum(pieces.values()) - len(group)
            if nj > 0:
                cv = COVER.get(shape, COVER["H-300"])
                out.append(Qty("  カバープレート", f"{cv[0]} {cv[1]:.0f}×{RT.H_SHAPES[shape][1]:.0f} t{cv[2]:g}", nj * 2, "枚",
                               f"継手 {nj}か所×両フランジ（{cv[3]:g}kg: ヒロセ p.05・p.16）"))
            for L in sorted(aux):
                out.append(Qty("  補助ピース", f"30D L={L:.0f}", aux[L], "個", f"{aux[L] * AUX_MM[L]:.0f}kg（ヒロセ p.15）"))
            if jacks:
                out.append(Qty("  キリンジャッキ", f"KJ-150 {JACK_RANGE[0]:.0f}〜{JACK_RANGE[1]:.0f}・端板 {RT.JACK[1]:.0f}□", jacks, "台",
                               f"{jacks * RT.JACK[2] / 1000:.2f}t。切梁1本に1台・千鳥に（ヒロセ p.09・p.29・藤田 p.15）"))
                out.append(Qty("  ジャッキカバー", f"{JACK_COVER[0]} {JACK_COVER[1]:.0f}", jacks, "組", f"{JACK_COVER[3]:g}kg（ヒロセ p.16）"))
            if kind == "hiuchi":
                out.append(Qty("  火打受ピース", f"45° 底 {RT.HIUCHI_PIECE[0]:.0f}×幅 {RT.HIUCHI_PIECE[1]:.0f}", len(group) * 2, "個",
                               f"{len(group) * 2 * RT.HIUCHI_PIECE[3] / 1000:.2f}t（ヒロセ p.16）"))
            if kind == "wale":
                nb = sum(len(m.wale_brackets) for m in group)
                out.append(Qty("  腹起しのブラケット", f"BL30N {RT.BRACKET_PITCH_MM / 1000:g}m ピッチ・両端に", nb, "個",
                               f"{nb * WALE_BRACKET_KG:.0f}kg（ジェコス p.31）"))
    nx = sum(len(m.crossings) for m in members if m.kind == "strut")
    if nx:
        out.append(Qty("交差部", "上段と下段の切梁の交点", nx, "か所", "下段・上段の順に組む（ヒロセ p.09）"))
        out.append(Qty("  アングルピース", f"{CROSS_ANGLE[0]} L-{CROSS_ANGLE[2]:.0f} {CROSS_ANGLE[1]:.0f}", nx * 4, "本",
                       f"{nx * 4 * CROSS_ANGLE[4]:.0f}kg。上下に2本ずつ【数は読み取り: ジェコス p.23】（ヒロセ p.16）"))
        out.append(Qty("  交叉部直ボルト", f"{CROSS_BOLT[0]} M{CROSS_BOLT[2]:.0f}×{CROSS_BOLT[1]:.0f}", nx * 4, "本",
                       f"{nx * 4 * CROSS_BOLT[3]:.1f}kg（ヒロセ p.26）"))
    piles = [m for m in members if m.kind == "pile"]
    if piles:
        H, B, t1, t2, kg = RT.H_SHAPES[piles[0].shape]
        L = max(m.length for m in piles)
        out.append(Qty("中間杭", f"{piles[0].shape}×{B:.0f}×{t1:g}×{t2:g} L={L / 1000:.1f}m（杭用・生材）", len(piles), "本",
                       f"{sum(m.length for m in piles) / 1000 * kg / 1000:.2f}t。切梁の交点に（中部地整 3-1-62・旧要綱 第51）。"
                       "長さは支持力と座屈の計算で"))
        nb = sum(len(m.brackets) for m in piles)
        out.append(Qty("  切梁受けブラケット", f"{BRACKET[0]} {BRACKET[1]:.0f}×{BRACKET[2]:.0f} L-75×75×9", nb, "個",
                       f"{nb * BRACKET[4]:.0f}kg。杭1本に1個・段ごと（ヒロセ p.06・ジェコス p.31）"))
        out.append(Qty("  締付用 U ボルト", f"{UBOLT[0]} {UBOLT[1]:.0f}×{UBOLT[2]:.0f} M22", nb, "本", f"{nb * UBOLT[3]:.0f}kg（ジェコス p.24）"))
    if main_t > 0:
        out.append(Qty("副部材（照合）", f"主部材 {main_t:.2f}t × {SUB_RATIO[0]}（リース）・× {SUB_RATIO[1]}（全損）", main_t * SUB_RATIO[0], "t",
                       f"全損 {main_t * SUB_RATIO[1]:.2f}t。公共積算の比率（数量要領 R8 1-11-4）。上の1個ずつと見比べる"))
    return out


def checks(members: list[Member]) -> list:
    """支保工の検定（出典のある決めだけ）."""
    Check = RT.Check
    out = []
    struts = [m for m in members if m.kind == "strut"]
    for m in struts:
        if m.length > 0 and all(t != "main" for t, _L in segments(m)) and m.length > JACK_RANGE[1] + 900.0:
            out.append(Check("切梁の割付", "WARN", f"{m.name}: {m.length:.0f}mm を主材で割り付けられません"))
    if struts:
        lv = sorted({m.level for m in struts})
        out.append(Check("切梁", "注意", f"{len(struts)}本・{len(lv)}段。水平 5m 以下・継材は 4m 以内（九州 共2-24・共2-28）・"
                                         "プレロードと軸力は山留めの計算で"))
    nh = sum(1 for m in members if m.kind == "hiuchi")
    if nh:
        out.append(Check("火打ち", "注意", f"{nh}本。45°・切梁に付けるものは左右に対称（九州 共2-29・中部 3-1-64）。軸力は N＝R／cosθ を山留めの計算で"))
    if any(m.tier == 1 for m in struts) and any(m.tier == 0 for m in struts):
        piles = [m for m in members if m.kind == "pile"]
        nx = sum(len(m.crossings) for m in struts)
        out.append(Check("中間杭", "OK" if piles else "注意",
                         f"交点 {nx}か所・中間杭 {len(piles)}本（2方向の切梁は交点に中間杭: 旧要綱 第51。座屈を抑える荷重は切梁の全軸力の 2%: "
                         "中部 3-1-62）"))
    return out


# ---- 部品のパラメータ ----

def part_params(m: Member) -> dict:
    """部品 ashiba_shiho のパラメータ（m。並びは mm の文字列）."""
    H, B, t1, t2, _kg = RT.H_SHAPES[m.shape]
    p = {"shKind": KIND_NO[m.kind], "shL": m.length / 1000.0, "shZ": m.z / 1000.0, "sH": H / 1000.0, "sB": B / 1000.0,
         "sT1": t1 / 1000.0, "sT2": t2 / 1000.0, "shName": m.name, "shInfo": info(m)}
    if m.kind == "pile":
        p.update({"shBot": m.bottom / 1000.0, "pkZ": RT._mm(m.brackets), "pkR": m.reach / 1000.0,
                  "bkL": BRACKET[1] / 1000.0, "bkH": BRACKET[2] / 1000.0, "ubW": UBOLT[1] / 1000.0, "ubH": UBOLT[2] / 1000.0})
        return p
    seq = segments(m)
    p.update({"sgL": RT._mm(L for _t, L in seq), "sgT": RT._mm({"main": 1.0, "aux": 2.0, "jack": 3.0, "piece": 4.0}[t] for t, _L in seq),
              "hpS": m.side,
              "cvL": COVER["H-300"][1] / 1000.0, "cvT": COVER["H-300"][2] / 1000.0, "endT": END_T_MM / 1000.0,
              "jkW": RT.JACK[1] / 1000.0, "jcL": JACK_COVER[1] / 1000.0,
              "xcX": RT._mm(x for x, _h in m.crossings), "xcH": RT._mm(h for _x, h in m.crossings),
              "xaL": CROSS_ANGLE[1] / 1000.0, "xbO": CROSS_HOLE_MM / 2000.0,
              "brX": RT._mm(m.wale_brackets), "hpA": RT.HIUCHI_PIECE[0] / 1000.0})
    return p


def info(m: Member) -> str:
    """平面の注記."""
    if m.kind == "pile":
        return f"中間杭 {m.shape} L={m.length / 1000:.1f}m"
    code = LEASE.get(m.shape, (m.shape,))[0]
    return f"{KINDS[m.kind]} {m.shape}（{code}）GL-{m.z:,.0f}" + (" 上段" if m.kind == "strut" and m.tier else "")


def report(members: list[Member], title: str = "山留め支保工") -> str:
    lines = [f"# {title}", "", "| 項目 | 仕様 | 数量 | 単位 | 備考 |", "|---|---|---:|---|---|"]
    for q in quantities(members):
        v = f"{q.qty:.2f}" if q.unit in ("m²", "m³", "t", "m") else f"{q.qty:g}"
        lines.append(f"| {q.item} | {q.spec} | {v} | {q.unit} | {q.note} |")
    cs = checks(members)
    if cs:
        lines += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"] + [f"| {c.item} | {c.status} | {c.message} |" for c in cs]
    lines += ["", "## 部材", "", "| 名前 | 種類 | 形 | 深さ | 長さ | 割付（始めから） |", "|---|---|---|---:|---:|---|"]
    names = {"main": "主材", "aux": "補助", "jack": "ジャッキ", "piece": "受ピース"}
    for m in members:
        seq = "・".join(f"{names[t]}{L:.0f}" for t, L in segments(m))
        lines.append(f"| {m.name} | {KINDS[m.kind]}{'（上段）' if m.kind == 'strut' and m.tier else ''} | {m.shape} | "
                     f"GL-{m.z:,.0f} | {m.length:,.0f} | {seq} |")
    lines += ["", "## 出典", ""] + [f"- {v}" for v in SOURCES.values()] + [""]
    return "\n".join(lines)
