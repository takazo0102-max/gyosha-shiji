"""スラブの型枠と支保工: せき板・根太・大引・パイプサポート・水平つなぎ（利用者の指定 2026-10-31: スラブの型枠も進めて しほこうも）.

組み方（在来のスラブ型枠）:
- せき板は型枠用合板 12mm（900×1800）をスラブの下面に。梁・壁・柱の所は抜く（梁の側板・壁の型枠が受ける）
- 根太は角パイプ □50×50×2.3 を NEDA_PITCH_MM ごと、大引に直角に（スラブ・梁下の詳細図。利用者 2026-10-31）
- 大引は杉 90×90 を SV_CANDS（@900）ごと、パイプサポートの列ごとに。パイプサポートの上端は大引に釘止め
- パイプサポートは大引の下に、大引の向きに su、大引どうしの間 sv の格子。梁・壁・柱の下（とまわり CLEAR_MM）には立てない。
  下には大引の列ごとに敷き桟木（45×60 を寝かせて通す）を敷き、その上に立てる（利用者の指定 2026-10-31: サポートしたはさんぎいる）
- 高さ 3.5m を超えるパイプサポートは、高さ 2m 以内ごとに水平つなぎを2方向（安衛則 242条）

計算（formwork.py: せき板・根太・大引の単純梁、たわみ 3mm）:
- 荷重はコンクリート（鉄筋とも）RC_KN_M3×厚さ＋型枠 FORM_KN＋作業 WORK_KN（安衛則 240条の作業荷重 1.5kN/m²）。たわみは固定荷重だけ
- パイプサポート1本の軸力＝荷重×su×sv ≦ PS_ALLOW_KN（目安。使う長さのメーカーの許容荷重で確かめる）
- 間隔は候補の中から、みな通る組のうち大引の間隔が広い（詳細図の @900）組、次に支柱の本数が少ない組
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ashiba.formwork import NEDA_PITCH_MM, PLY_T_MM, check

# スラブ・梁下の詳細図（利用者の指定 2026-10-31）: せき板 合板 12 → 根太 角パイプ □50×50×2.3 @300 → 杉大引 90×90 @900 →
# パイプサポート（上端を大引に釘止め）
SLAB_NEDA = "角パイプ50"
SLAB_OBIKI = "杉90"

RC_KN_M3 = 24.0
FORM_KN = 0.4
WORK_KN = 1.5
PS_ALLOW_KN = 15.0                    # パイプサポート1本の許容荷重の目安（kN）
PS_MAX_MM = 3500.0                    # これを超えると水平つなぎ（2方向・2m 以内ごと）
TIE_PITCH_MM = 2000.0
OBIKI_H_MM = 90.0                     # 大引（杉 90×90）のせい
NEDA_D_MM = 50.0                      # 根太（角パイプ □50×50）のせい
CLEAR_MM = 150.0                      # 梁・壁・柱のまわりに支柱を立てない幅
SILL_H_MM = 45.0                      # パイプサポートの下の敷き桟木（45×60 を寝かせる）の高さ（利用者の指定 2026-10-31: サポートしたはさんぎいる）
SILL_OUT_MM = 150.0                   # 敷き桟木の、列の端の支柱からの出
SU_CANDS = (1500.0, 1200.0, 1000.0, 900.0, 750.0, 600.0)   # 大引の向きの支柱の間隔
SV_CANDS = (900.0, 750.0, 600.0)     # 大引どうしの間隔（詳細図は @900）
EDGE_MM = 150.0                       # スラブの縁・穴からいちばん近い根太・大引まで


def loads(thick_mm: float) -> tuple[float, float]:
    """(設計荷重, 固定荷重) kN/m²."""
    dead = RC_KN_M3 * thick_mm / 1000.0 + FORM_KN
    return dead + WORK_KN, dead


@dataclass
class SlabSpacing:
    su: float
    sv: float
    beams: list            # [BeamCheck] せき板・根太・大引
    post_kn: float
    ok: bool

    def lines(self, q: float) -> list[str]:
        out = [f"荷重 {q:.2f} kN/m²（コンクリート {RC_KN_M3:.0f}kN/m³・型枠 {FORM_KN}・作業 {WORK_KN}）"]
        for b in self.beams:
            out.append(f"{b.part}（{b.member}）スパン {b.span_mm:.0f}: σ {b.sigma:.1f}／{b.fb:.1f} N/mm²・"
                       f"たわみ {b.deflection_mm:.2f} mm {'可' if b.ok else '不可'}")
        out.append(f"パイプサポート 1本 {self.post_kn:.1f}／{PS_ALLOW_KN:.1f} kN（目安） "
                   f"{'可' if self.post_kn <= PS_ALLOW_KN + 1e-9 else '不可'}")
        return out


def choose_spacing(thick_mm: float) -> SlabSpacing:
    q, qd = loads(thick_mm)
    best = None
    for su in SU_CANDS:
        for sv in SV_CANDS:
            bc = check(q, qd, su, sv, SLAB_NEDA, SLAB_OBIKI, NEDA_PITCH_MM)
            pk = q * su * sv / 1e6
            ok = all(b.ok for b in bc) and pk <= PS_ALLOW_KN + 1e-9
            if ok:
                key = (sv, su * sv)            # 大引は詳細図の @900 を先に、次に支柱の本数が少ない組
                if best is None or key > best[0]:
                    best = (key, SlabSpacing(su, sv, bc, pk, True))
    if best:
        return best[1]
    su, sv = SU_CANDS[-1], SV_CANDS[-1]
    bc = check(q, qd, su, sv, SLAB_NEDA, SLAB_OBIKI, NEDA_PITCH_MM)
    return SlabSpacing(su, sv, bc, q * su * sv / 1e6, False)


# ---- 平面の形 ----
def _in_poly(p, poly) -> bool:
    inside = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _line_intervals(a: float, axis: int, outer: list, holes: list, edge: float) -> list[tuple[float, float]]:
    """座標 axis（0＝x 一定の線 x=a、1＝y 一定の線 y=a）の線が、外形の中で穴の外にある区間（両端を edge 縮める）."""
    def cuts(poly):
        ts = []
        n = len(poly)
        for k in range(n):
            p, q = poly[k], poly[(k + 1) % n]
            c0, c1 = p[axis], q[axis]
            if (c0 > a) != (c1 > a):
                f = (a - c0) / (c1 - c0)
                ts.append(p[1 - axis] + (q[1 - axis] - p[1 - axis]) * f)
        ts.sort()
        return list(zip(ts[0::2], ts[1::2]))
    segs = cuts(outer)
    for h in holes:
        for h0, h1 in cuts(h):
            nxt = []
            for s, e in segs:
                if h1 <= s or h0 >= e:
                    nxt.append((s, e))
                    continue
                if h0 > s:
                    nxt.append((s, h0))
                if h1 < e:
                    nxt.append((h1, e))
            segs = nxt
    return [(s + edge, e - edge) for s, e in segs if e - s > 2 * edge + 100.0]


def _grid(lo: float, hi: float, pitch: float, edge: float) -> list[float]:
    span = hi - lo - 2 * edge
    if span <= 0:
        return [(lo + hi) / 2.0]
    n = max(1, math.ceil(span / pitch - 1e-9))
    return [lo + edge + span * k / n for k in range(n + 1)]


def rect(c, u, half_len: float, half_w: float, grow: float = 0.0) -> list:
    """芯 c・向き u の長方形（左回り）."""
    n = (-u[1], u[0])
    L, W = half_len + grow, half_w + grow
    return [(c[0] - u[0] * L - n[0] * W, c[1] - u[1] * L - n[1] * W), (c[0] + u[0] * L - n[0] * W, c[1] + u[1] * L - n[1] * W),
            (c[0] + u[0] * L + n[0] * W, c[1] + u[1] * L + n[1] * W), (c[0] - u[0] * L + n[0] * W, c[1] - u[1] * L + n[1] * W)]


@dataclass
class SlabForm:
    ang: float                 # 大引の向き（度。世界座標）
    origin: tuple              # 局所座標の原点（世界 mm）
    outer: list                # 局所座標のスラブの外形
    holes: list                # 局所座標の穴（梁・壁・柱）
    thick: float
    spacing: SlabSpacing
    post_h: float              # パイプサポートの長さ（敷き桟木の上から大引の下まで）
    neda: list = field(default_factory=list)    # 根太 [(v0, v1, u)]（v の向きの線分。u 一定）
    obiki: list = field(default_factory=list)   # 大引 [(u0, u1, v)]（u の向きの線分。v 一定）
    posts: list = field(default_factory=list)   # パイプサポート [(u, v)]
    ties: list = field(default_factory=list)    # 水平つなぎの高さ（床から mm）

    @property
    def q(self) -> float:
        return loads(self.thick)[0]

    def area_m2(self, step: float = 100.0) -> float:
        """せき板の面積（外形の中で穴の外。step の格子で数える）."""
        us, vs = [p[0] for p in self.outer], [p[1] for p in self.outer]
        n = 0
        x = min(us) + step / 2.0
        while x < max(us):
            y = min(vs) + step / 2.0
            while y < max(vs):
                if _in_poly((x, y), self.outer) and not any(_in_poly((x, y), h) for h in self.holes):
                    n += 1
                y += step
            x += step
        return n * step * step / 1e6

    def sills(self) -> list[tuple[float, float, float]]:
        """敷き桟木 [(u0, u1, v)]: 同じ大引の列（v）の支柱の下に、端の支柱から SILL_OUT_MM 出して通す. 梁・壁・柱で支柱が飛ぶ所
        （間が su の 1.2倍を超える）は分ける（梁の下の敷き桟木と交わらない。利用者の指定 2026-10-31: さんぎの向き揃えて）."""
        rows: dict = {}
        for u, v in self.posts:
            rows.setdefault(round(v), []).append(u)
        out = []
        for v, us in sorted(rows.items()):
            us = sorted(us)
            start = us[0]
            for a, b in zip(us, us[1:]):
                if b - a > self.spacing.su * 1.2:
                    out.append((start - SILL_OUT_MM, a + SILL_OUT_MM, float(v)))
                    start = b
            out.append((start - SILL_OUT_MM, us[-1] + SILL_OUT_MM, float(v)))
        return out

    def lines(self) -> list[str]:
        out = self.spacing.lines(self.q)
        out.append(f"パイプサポートの長さ {self.post_h:.0f}" + (f"（{PS_MAX_MM:.0f} を超えるので水平つなぎ {len(self.ties)}段・2方向）"
                                                         if self.ties else ""))
        return out

    def quantities(self) -> list[tuple[str, int, str]]:
        from ashiba.wall_form import tube_pieces
        from collections import Counter

        a = self.area_m2()
        out = [("型枠用合板 12mm 900×1800（スラブ）", math.ceil(a / 1.62 * 1.05), f"面積 {a:.1f}m²（切り物・ロス 5%）")]
        tubes = Counter()
        for v0, v1, _u in self.neda:
            for p in tube_pieces(v1 - v0):
                tubes[p] += 1
        for L, n in sorted(tubes.items(), reverse=True):
            out.append((f"角パイプ □50×50×2.3 {L / 1000:.1f}m（根太）", n, f"@{NEDA_PITCH_MM:.0f}"))
        ob = sum(u1 - u0 for u0, u1, _v in self.obiki)
        out.append(("杉大引 90×90（4m）", math.ceil(ob / 4000.0 * 1.05), f"延べ {ob / 1000:.1f}m・@{self.spacing.sv:.0f}"))
        out.append(("釘（パイプサポートの上端を大引に）", 2 * len(self.posts), "受け板の穴から2本ずつ"))
        out.append(("パイプサポート", len(self.posts), f"長さ {self.post_h:.0f}・@{self.spacing.su:.0f}×{self.spacing.sv:.0f}"))
        sill = sum(e - s for s, e, _v in self.sills())
        out.append(("桟木 45×60（敷き桟木・4m）", math.ceil(sill / 4000.0 * 1.05), f"パイプサポートの下に寝かせて列ごとに通す・延べ {sill / 1000:.1f}m"))
        if self.ties:
            n_u = len({round(v) for _u, v in self.posts})
            n_v = len({round(u) for u, _v in self.posts})
            out.append(("単管（水平つなぎ・2方向）", len(self.ties) * (n_u + n_v), f"{len(self.ties)}段。延べは格子の長さ"))
            out.append(("直交クランプ（水平つなぎ）", 2 * len(self.ties) * len(self.posts), "支柱と水平つなぎ"))
        return out


def obiki_angle(outline_mm: list) -> float:
    """大引（と敷き桟木）の向き＝スラブの外形のいちばん長い辺の向き（度）."""
    pts = list(outline_mm)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    k = max(range(len(pts)), key=lambda i: math.dist(pts[i], pts[(i + 1) % len(pts)]))
    p, q = pts[k], pts[(k + 1) % len(pts)]
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))


def plan_slab(outline_mm: list, thick_mm: float, bottom_mm: float, floor_mm: float, holes_mm=(),
              ang_deg: float | None = None) -> SlabForm:
    """スラブ1枚の型枠と支保工. outline・holes は世界座標 mm、bottom＝スラブの下端、floor＝支柱の立つ床の高さ."""
    pts = list(outline_mm)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if ang_deg is None:                    # 大引はいちばん長い辺の向き
        ang_deg = obiki_angle(pts)
    a = math.radians(ang_deg)
    u, v = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    o = pts[0]
    loc = lambda p: ((p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1], (p[0] - o[0]) * v[0] + (p[1] - o[1]) * v[1])
    outer = [loc(p) for p in pts]
    holes = [[loc(p) for p in h] for h in holes_mm]
    sp = choose_spacing(thick_mm)
    post_h = bottom_mm - PLY_T_MM - NEDA_D_MM - OBIKI_H_MM - SILL_H_MM - floor_mm
    us = [p[0] for p in outer]
    vs = [p[1] for p in outer]
    # 根太（v の向き。u ごと NEDA_PITCH_MM）、大引（u の向き。v ごと sv）、支柱（大引の上 su ごと）
    neda = [(s, e, x) for x in _grid(min(us), max(us), NEDA_PITCH_MM, 50.0)
            for s, e in _line_intervals(x, 0, outer, holes, 20.0)]
    obiki, posts = [], []
    clear = [[(p[0], p[1]) for p in _grow(h, CLEAR_MM)] for h in holes]
    for y in _grid(min(vs), max(vs), sp.sv, EDGE_MM):
        for s, e in _line_intervals(y, 1, outer, holes, 50.0):
            obiki.append((s, e, y))
            for x in _grid(s, e, sp.su, EDGE_MM - 50.0):
                if _in_poly((x, y), outer) and not any(_in_poly((x, y), c) for c in clear):
                    posts.append((x, y))
    ties = []
    if post_h > PS_MAX_MM:
        z = TIE_PITCH_MM
        while z < post_h - 300.0:
            ties.append(z)
            z += TIE_PITCH_MM
    return SlabForm(ang_deg, o, outer, holes, thick_mm, sp, post_h, neda, obiki, posts, ties)


def _grow(poly: list, d: float) -> list:
    """凸の多角形を外へ d 広げた形（辺を平行に動かして角を結ぶ）."""
    n = len(poly)
    area = sum(poly[k][0] * poly[(k + 1) % n][1] - poly[(k + 1) % n][0] * poly[k][1] for k in range(n))
    sgn = 1.0 if area > 0 else -1.0
    lines = []
    for k in range(n):
        p, q = poly[k], poly[(k + 1) % n]
        L = math.dist(p, q) or 1.0
        nx, ny = (q[1] - p[1]) / L * sgn, -(q[0] - p[0]) / L * sgn     # 外向き
        lines.append(((p[0] + nx * d, p[1] + ny * d), (q[0] - p[0], q[1] - p[1])))
    out = []
    for k in range(n):
        (p1, d1), (p2, d2) = lines[k - 1], lines[k]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out
