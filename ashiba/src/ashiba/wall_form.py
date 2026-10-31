"""壁の型枠: せき板（合板）・桟木・外端太（単管2本）・フォームタイの割付と計算（利用者の指定 2026-10-31: 型枠を作る仕組みを
作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置するようにして）.

組み方（在来の壁型枠）:
- せき板は型枠用合板 12mm（900×1800 を縦使い）を壁の両面に
- 桟木は合板の外に縦に SANGI_PITCH の間隔（合板のスパン）
- 外端太は単管 φ48.6 を2本組で横に、下から間隔 TATE_PITCH（桟木のスパン）
- フォームタイは外端太の2本の間を通し、横に間隔 TIE_PITCH（外端太のスパン）。両面の外端太を座金とナットで締める

計算（formwork.py と同じ単純梁、たわみの上限 3mm）:
- 側圧は JASS 5 の型枠設計用コンクリートの側圧（打込みの速さ RATE_M_H 以下、W0＝23.5kN/m³、H はヘッド m）:
  10m/h 以下: H≦1.5 は W0·H、1.5＜H は 柱 1.5W0＋0.6W0(H−1.5)・壁（長さ 3m 以下）1.5W0＋0.2W0(H−1.5)・壁（3m 超え）1.5W0
  10〜20m/h: H≦2.0 は W0·H、2.0＜H は 柱 2.0W0＋0.8W0(H−2.0)・壁（3m 以下）2.0W0＋0.4W0(H−2.0)・壁（3m 超え）2.0W0
  20m/h 超え: W0·H。どれも液圧 W0·H を上限とする
- せき板: 1m 幅・スパン＝桟木の間隔・荷重＝側圧
- 桟木: スパン＝外端太の間隔・荷重＝側圧×桟木の間隔
- 外端太（単管2本）: スパン＝フォームタイの間隔・荷重＝側圧×外端太の間隔
- フォームタイ: 引張＝側圧×外端太の間隔×フォームタイの間隔 ≦ 許容引張（W5/16 の目安 13.7kN。メーカーの値で確かめる）
間隔は候補の中から、みな通る組のうち桟木の間隔がいちばん広く、次にフォームタイの本数がいちばん少ない組を選ぶ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ashiba.formwork import DEFLECTION_MAX_MM, NEDA, PLY_E, PLY_FB, PLY_T_MM, Member, _beam

W0_KN_M3 = 23.5                       # コンクリートの単位体積重量（側圧の計算用）
PANEL_W_MM, PANEL_H_MM = 900.0, 1800.0
SANGI_B_MM, SANGI_H_MM = 45.0, 60.0   # 桟木の断面（幅×せい。せいを合板に直角）
WOOD_E, WOOD_FB = 7000.0, 10.3        # 桟木（米松の目安）N/mm²
TUBE_D_MM = 48.6
TIE_ALLOW_KN = 13.7                   # フォームタイ W5/16 の許容引張の目安
TIE_D_MM = 7.9                        # W5/16 の径
EDGE_MM = 150.0                       # 壁の端・上下からいちばん近い外端太・フォームタイまで

SANGI_PITCHES = (300.0, 250.0, 200.0, 150.0)
TATE_PITCHES = (750.0, 600.0, 450.0, 300.0)       # 外端太の上下の間隔
TIE_PITCHES = (900.0, 750.0, 600.0, 450.0)        # フォームタイの横の間隔

SANGI = Member(f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}", WOOD_E, WOOD_FB,
               SANGI_B_MM * SANGI_H_MM ** 2 / 6.0, SANGI_B_MM * SANGI_H_MM ** 3 / 12.0)
SOTOBATA = Member("外端太 単管 φ48.6×2.4 2本", NEDA["単管"].E, NEDA["単管"].fb, 2 * NEDA["単管"].Z, 2 * NEDA["単管"].I)


RATE_M_H = 10.0                       # 打込みの速さの想定（m/h）


def pressure_kn_m2(height_mm: float, length_mm: float = 1e9, column: bool = False, rate: float = RATE_M_H) -> float:
    """いちばん下の側圧 kN/m²（JASS 5 の表。液圧を上限）."""
    w, h = W0_KN_M3, height_mm / 1000.0
    liquid = w * h
    if rate > 20.0:
        return liquid
    h0, kc, kw = (1.5, 0.6, 0.2) if rate <= 10.0 else (2.0, 0.8, 0.4)
    if h <= h0:
        return liquid
    if column:
        p = h0 * w + kc * w * (h - h0)
    elif length_mm <= 3000.0:
        p = h0 * w + kw * w * (h - h0)
    else:
        p = h0 * w
    return min(p, liquid)


@dataclass
class FormCheck:
    sangi_pitch: float
    tate_pitch: float
    tie_pitch: float
    pressure: float                       # kN/m²
    beams: list                           # [BeamCheck]（せき板・桟木・外端太）
    tie_kn: float
    ok: bool

    def lines(self) -> list[str]:
        out = [f"側圧 {self.pressure:.1f} kN/m²（JASS 5・打込みの速さ {RATE_M_H:.0f}m/h 以下）"]
        for b in self.beams:
            out.append(f"{b.part}（{b.member}）スパン {b.span_mm:.0f}: σ {b.sigma:.1f}／{b.fb:.1f} N/mm²・"
                       f"たわみ {b.deflection_mm:.2f}／{DEFLECTION_MAX_MM:.0f} mm {'可' if b.ok else '不可'}")
        out.append(f"フォームタイ 引張 {self.tie_kn:.1f}／{TIE_ALLOW_KN:.1f} kN {'可' if self.tie_kn <= TIE_ALLOW_KN else '不可'}")
        return out


def check(height_mm: float, sangi_pitch: float, tate_pitch: float, tie_pitch: float, length_mm: float = 1e9) -> FormCheck:
    p = pressure_kn_m2(height_mm, length_mm)
    q = p * 1e-3                                          # N/mm²
    ply = Member(f"合板 {PLY_T_MM:.0f}mm", PLY_E, PLY_FB, 1000.0 * PLY_T_MM ** 2 / 6.0, 1000.0 * PLY_T_MM ** 3 / 12.0)
    beams = [_beam("せき板", ply, sangi_pitch, q * 1000.0, q * 1000.0),
             _beam("桟木", SANGI, tate_pitch, q * sangi_pitch, q * sangi_pitch),
             _beam("外端太", SOTOBATA, tie_pitch, q * tate_pitch, q * tate_pitch)]
    tie = p * tate_pitch * tie_pitch / 1e6
    return FormCheck(sangi_pitch, tate_pitch, tie_pitch, p, beams, tie,
                     all(b.ok for b in beams) and tie <= TIE_ALLOW_KN + 1e-9)


def choose(height_mm: float, length_mm: float = 1e9) -> FormCheck:
    """みな通る間隔の組のうち、桟木の間隔がいちばん広く（在来の @300 を先に）、次にフォームタイの受け持つ面積がいちばん広い
    （本数が少ない）組。通る組が無ければ
    いちばん密な組（不可のまま）."""
    best = None
    for tie in TIE_PITCHES:
        for tate in TATE_PITCHES:
            for sg in SANGI_PITCHES:
                c = check(height_mm, sg, tate, tie, length_mm)
                if c.ok:
                    key = (sg, tie * tate, tie)
                    if best is None or key > best[0]:
                        best = (key, c)
    return best[1] if best else check(height_mm, SANGI_PITCHES[-1], TATE_PITCHES[-1], TIE_PITCHES[-1], length_mm)


def _stations(length: float, pitch: float, edge: float) -> list[float]:
    """0〜length に、端から edge の所を両端として、間隔 pitch 以下で等しく割った位置."""
    if length <= 2 * edge:
        return [length / 2.0]
    span = length - 2 * edge
    n = max(1, math.ceil(span / pitch - 1e-9))
    return [edge + span * k / n for k in range(n + 1)]


TUBE_LENGTHS = (1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000)
def tube_pieces(length_mm: float) -> list[int]:
    """長さ length の外端太1本を定尺の単管で（長ければ 6m を単管ジョイントで突き付けて継ぐ）."""
    out, rest = [], length_mm
    while rest > TUBE_LENGTHS[-1]:
        out.append(TUBE_LENGTHS[-1])
        rest -= TUBE_LENGTHS[-1]
    out.append(next(v for v in TUBE_LENGTHS if v >= rest))
    return out


@dataclass
class WallForm:
    length: float
    height: float
    thick: float
    calc: FormCheck
    faces: list[tuple[float, float]]  # 右の面・左の面の型枠の範囲（壁の始めから。角で延ばす・縮める）
    sangi_x: list[list[float]]        # 面ごとの桟木の位置（壁の始めから）
    tate_z: list[float]               # 外端太の高さ（壁の下から）
    tie_x: list[float]                # フォームタイの位置（壁の始めから。両面の型枠がある所）
    panels: list[list[tuple[float, float, float, float]]] = field(default_factory=list)   # 面ごとの合板 (x, z, 幅, 高さ)
    ends: tuple[bool, bool] = (False, False)    # 始め・終わりの止め型枠（ほかの壁につながらない端）
    tubes: list[tuple[float, float]] = field(default_factory=list)   # 面ごとの外端太の範囲（壁の始めから）
    ply_segs: list[list[tuple[float, float]]] = field(default_factory=list)    # 面ごとのせき板の区間（T字で分ける）
    tube_segs: list[list[tuple[float, float]]] = field(default_factory=list)   # 面ごとの外端太の区間

    def quantities(self) -> list[tuple[str, int, str]]:
        """両面の材料の目安."""
        from collections import Counter

        allp = [p for ps in self.panels for p in ps]
        full = sum(1 for _x, _z, w, h in allp if w >= PANEL_W_MM - 1 and h >= PANEL_H_MM - 1)
        cut = len(allp) - full
        sangi_len = self.height
        per = max(1, math.floor(4000.0 / sangi_len)) if sangi_len <= 4000.0 else 0
        n_sangi = sum(len(xs) for xs in self.sangi_x)
        sangi_pcs = math.ceil(n_sangi / per) if per else n_sangi * math.ceil(sangi_len / 4000.0)
        tubes = Counter()
        for s, e in (t for ts in self.tube_segs for t in ts):
            for v in tube_pieces(e - s):
                tubes[v] += 2 * len(self.tate_z)
        n_tie = len(self.tie_x) * len(self.tate_z)
        out = [("型枠用合板 12mm 900×1800", full, "両面・縦使い"),
               ("型枠用合板 12mm（切り物）", cut, "両面・端と上の残り")]
        out = [r for r in out if r[1] > 0]
        out.append((f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}（4m）", sangi_pcs,
                    f"縦 @{self.calc.sangi_pitch:.0f}・長さ {sangi_len:.0f}×{n_sangi}本"))
        for v, n in sorted(tubes.items(), reverse=True):
            out.append((f"単管 {v / 1000:.1f}m（外端太）", n, f"2本組・@{self.calc.tate_pitch:.0f}・両面"))
        k = sum(len(tube_pieces(e - s)) - 1 for ts in self.tube_segs for s, e in ts) * 2 * len(self.tate_z)
        if k:
            out.append(("単管ジョイント（外端太の継ぎ）", k, "長い外端太を突き付けて継ぐ。継ぎ目は上下でずらす"))
        n_end = sum(1 for e in self.ends if e)
        if n_end:
            out.append(("型枠用合板 12mm（止め型枠）", n_end * math.ceil(self.height / PANEL_H_MM),
                        f"壁の端の止め（幅 {self.thick + 2 * PLY_T_MM:.0f}）"))
            out.append((f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}（止め型枠・4m）", n_end * 2 * math.ceil(self.height / 4000.0),
                        "止めの合板の外に縦2本"))
            press = next(v for v in TUBE_LENGTHS if v >= self.thick + 2 * 200.0)
            out.append((f"単管 {press / 1000:.1f}m（止め型枠の押さえ）", n_end * len(self.tate_z),
                        "外端太の段ごとに壁の厚さの向きに1本。止めの桟木を押さえる"))
            out.append(("直交クランプ（止め型枠）", n_end * 2 * len(self.tate_z), "押さえの単管を両面の外端太の出に"))
        out.append((f"フォームタイ（壁厚 {self.thick:.0f}）", n_tie, f"@{self.calc.tie_pitch:.0f}・座金・ナット 両側"))
        out.append(("Pコン", 2 * n_tie, "セパレータの両端"))
        return out


def _panels(s: float, e: float, height: float) -> list[tuple[float, float, float, float]]:
    out = []
    z = 0.0
    while z < height - 1.0:
        h = min(PANEL_H_MM, height - z)
        x = s
        while x < e - 1.0:
            w = min(PANEL_W_MM, e - x)
            out.append((x, z, w, h))
            x += w
        z += h
    return out


def _subtract(rng: tuple[float, float], gaps: list[tuple[float, float]], keep: float = 50.0) -> list[tuple[float, float]]:
    """区間 rng から gaps を除いた区間（keep 未満は捨てる）."""
    segs = [tuple(rng)]
    for a, b in sorted(gaps):
        nxt = []
        for s, e in segs:
            if b <= s or a >= e:
                nxt.append((s, e))
                continue
            if a > s:
                nxt.append((s, a))
            if b < e:
                nxt.append((b, e))
        segs = nxt
    return [(s, e) for s, e in segs if e - s >= keep]


def plan_wall(length_mm: float, height_mm: float, thick_mm: float, faces=None, ends=(False, False), tubes=None,
              sangi_rng=None, cuts=None) -> WallForm:
    """1枚の壁の型枠の割付. faces＝右の面・左の面の型枠の範囲（壁の始めから。無ければ 0〜長さ）、ends＝止め型枠の端、
    tubes＝外端太の範囲（無ければ面の端から TUBE_FREE_MM 出す）、sangi_rng＝桟木を置ける範囲（無ければ面の範囲）、
    cuts＝面ごとに T 字で突き当たる壁の所 [{"ply", "tube", "sangi": (始め, 終わり)}]（その面の型枠をそこで分ける）."""
    faces = [tuple(f) for f in (faces or [(0.0, length_mm), (0.0, length_mm)])]
    tubes = [tuple(t) for t in (tubes or [(s - TUBE_FREE_MM, e + TUBE_FREE_MM) for s, e in faces])]
    rng = [tuple(r) for r in (sangi_rng or faces)]
    cuts = cuts or [[], []]
    c = choose(height_mm, length_mm)
    ply = [_subtract(faces[k], [g["ply"] for g in cuts[k]]) for k in (0, 1)]
    tub = [_subtract(tubes[k], [g["tube"] for g in cuts[k]]) for k in (0, 1)]
    sangi = []
    for k in (0, 1):
        xs = []
        for s, e in _subtract(rng[k], [g["sangi"] for g in cuts[k]]):
            xs += [s + x for x in _stations(e - s, c.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
        sangi.append(xs)
    tate = _stations(height_mm, c.tate_pitch, EDGE_MM)
    # フォームタイは両面のせき板がある所（T 字で突き当たる壁の所は除く）
    s0, e0 = max(0.0, max(f[0] for f in faces)), min(length_mm, min(f[1] for f in faces))
    ties = []
    for s, e in _subtract((s0, e0), [g["ply"] for k in (0, 1) for g in cuts[k]], keep=2 * EDGE_MM):
        ties += [s + x for x in _stations(e - s, c.tie_pitch, EDGE_MM)]
    if not ties:
        ties = [(s0 + e0) / 2.0]
    return WallForm(length_mm, height_mm, thick_mm, c, faces, sangi, tate, ties,
                    [p for k in (0, 1) for p in [[q for s, e in ply[k] for q in _panels(s, e, height_mm)]]],
                    tuple(ends), tubes, ply, tub)


def _line_t(p, u, q, v) -> float | None:
    """直線 p+u·t と q+v·s の交点の t."""
    den = u[0] * v[1] - u[1] * v[0]
    if abs(den) < 1e-9:
        return None
    return ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / den


def _meets(A: dict, P, B: dict) -> bool:
    """壁 A の端 P が、向きの違う壁 B の中（厚さの半分＋5 以内）にあるか."""
    u = A["u"]
    if abs(u[0] * B["u"][1] - u[1] * B["u"][0]) < 0.05:
        return False
    d = (P[0] - B["ca"][0], P[1] - B["ca"][1])
    tb = d[0] * B["u"][0] + d[1] * B["u"][1]
    off = d[0] * B["n"][0] + d[1] * B["n"][1]
    return -B["thick"] / 2.0 - 5.0 <= tb <= B["length"] + B["thick"] / 2.0 + 5.0 and \
        B["lo"] - A["thick"] / 2.0 - 5.0 <= off <= B["hi"] + A["thick"] / 2.0 + 5.0


def free_ends(walls: list[dict]) -> list[tuple[bool, bool]]:
    """壁ごとに (始めの端, 終わりの端) が、ほかの壁につながらない（止め型枠が要る）か. 同じ線の上で端どうしが
    重なる壁（1枚の壁を分けたもの）もつながっているとみる."""
    out = []
    for i, A in enumerate(walls):
        fr = []
        for P in (A["ca"], A["cb"]):
            joined = False
            for j, B in enumerate(walls):
                if j == i:
                    continue
                if _meets(A, P, B):
                    joined = True
                elif abs(A["u"][0] * B["u"][1] - A["u"][1] * B["u"][0]) < 0.05 and \
                        min(math.dist(P, B["ca"]), math.dist(P, B["cb"])) <= 5.0:
                    joined = True
            fr.append(not joined)
        out.append(tuple(fr))
    return out


TUBE_OFF_MM = PLY_T_MM + SANGI_H_MM + TUBE_D_MM / 2.0   # 面から外端太の芯まで
BAND_MM = PLY_T_MM + SANGI_H_MM + TUBE_D_MM             # 面から型枠の外（外端太の外）まで
TUBE_FREE_MM = 150.0                                     # つながらない端の外端太の出（止め型枠の押さえを留める）


def face_layout(walls: list[dict]) -> list[dict]:
    """壁どうしのつながり（L字・T字・十字）で、壁ごとの面の型枠の範囲（壁の始めから）を決める
    → [{"faces": [(始め, 終わり)]×2（右の面・左の面）, "tubes": 外端太の範囲×2, "sangi": 桟木を置ける範囲×2}].

    せき板: 壁の端が別の壁の中（厚さの半分＋5 以内）にあれば、その壁の面の線まで。相手の壁が続いている側の面（入隅の面・T字）は
    手前の面まで縮め、続いていない側の面（出隅の面）は向こうの面まで延ばす.
    外端太・桟木（利用者の指定 2026-10-31: 両方延長から飛び出さないようにしてちょ）: 外端太は相手の壁の同じ側の外端太の線まで
    （出隅はたがいの外端太の線の交点で止め、入隅は相手の型枠の外で止める。角から先へ出さない）。桟木は相手の壁の型枠
    （面から BAND_MM）の中に入れない。つながらない端は外端太を TUBE_FREE_MM 出す."""
    out = []
    for i, A in enumerate(walls):
        u, n, L = A["u"], A["n"], A["length"]
        ext = [[0.0, L], [0.0, L]]                                 # [右の面, 左の面]
        tub = [[-TUBE_FREE_MM, L + TUBE_FREE_MM], [-TUBE_FREE_MM, L + TUBE_FREE_MM]]
        sng = [[0.0, L], [0.0, L]]
        for end in (0, 1):
            P = A["ca"] if end == 0 else A["cb"]
            for j, B in enumerate(walls):
                if j == i or not _meets(A, P, B):
                    continue
                # 相手の壁が続く側（A の左 +1・右 −1）
                sides = set()
                for Q in (B["ca"], B["cb"]):
                    h = (Q[0] - P[0]) * n[0] + (Q[1] - P[1]) * n[1]
                    if abs(h) > A["thick"] / 2.0 + 5.0:
                        sides.add(1 if h > 0 else -1)
                for k, (aoff, sg) in enumerate(((A["lo"], -1), (A["hi"], 1))):
                    at = lambda off: (A["ca"][0] + n[0] * off, A["ca"][1] + n[1] * off)
                    cand = []                                     # (t, B の面のずれ, B の面の外の向き)
                    for boff, sb in ((B["lo"], -1), (B["hi"], 1)):
                        q = (B["ca"][0] + B["n"][0] * boff, B["ca"][1] + B["n"][1] * boff)
                        t = _line_t(at(aoff), u, q, B["u"])
                        if t is not None:
                            cand.append((t, boff, sb))
                    if len(cand) < 2:
                        continue
                    cand.sort()
                    near = cand[0] if end == 1 else cand[-1]
                    far = cand[-1] if end == 1 else cand[0]
                    t, boff, sb = near if sg in sides else far
                    ext[k][end] = t

                    def cross(a_off, b_off):
                        q = (B["ca"][0] + B["n"][0] * b_off, B["ca"][1] + B["n"][1] * b_off)
                        return _line_t(at(a_off), u, q, B["u"])
                    tt = cross(aoff + sg * TUBE_OFF_MM, boff + sb * TUBE_OFF_MM)
                    if tt is not None:
                        tub[k][end] = tt
                    if sg in sides:                               # 入隅・T字: 相手の型枠の外まで桟木を寄せない
                        ts = cross(aoff + sg * BAND_MM, boff + sb * BAND_MM)
                        if ts is not None:
                            sng[k][end] = ts
                    else:
                        sng[k][end] = t
        out.append({"faces": [tuple(e) for e in ext], "tubes": [tuple(e) for e in tub], "sangi": [tuple(e) for e in sng],
                    "cuts": [[], []]})
    # T 字: 端が別の壁 B の中ほどに突き当たる壁 A の所で、B の A の側の面の型枠を分ける（せき板は A の面の線まで、外端太は A の
    # 外端太の線まで、桟木は A の型枠の外。入隅と同じ納まり）
    for i, A in enumerate(walls):
        for P, Q in ((A["ca"], A["cb"]), (A["cb"], A["ca"])):
            for j, B in enumerate(walls):
                if j == i or not _meets(A, P, B):
                    continue
                h = (Q[0] - P[0]) * B["n"][0] + (Q[1] - P[1]) * B["n"][1]
                k, boff, sb = (1, B["hi"], 1) if h > 0 else (0, B["lo"], -1)

                def span(b_off, a_add):
                    q = (B["ca"][0] + B["n"][0] * b_off, B["ca"][1] + B["n"][1] * b_off)
                    ts = []
                    for aoff, sa in ((A["lo"], -1), (A["hi"], 1)):
                        p = (A["ca"][0] + A["n"][0] * (aoff + sa * a_add), A["ca"][1] + A["n"][1] * (aoff + sa * a_add))
                        t = _line_t(q, B["u"], p, A["u"])
                        if t is not None:
                            ts.append(t)
                    return (min(ts), max(ts)) if len(ts) == 2 else None
                ply, tube, sangi = span(boff, 0.0), span(boff + sb * TUBE_OFF_MM, TUBE_OFF_MM), span(boff, BAND_MM)
                if ply and tube and sangi:
                    out[j]["cuts"][k].append({"ply": ply, "tube": tube, "sangi": sangi})
    return out


def face_extents(walls: list[dict]) -> list[list[tuple[float, float]]]:
    """壁ごとの右の面・左の面のせき板の範囲（face_layout の faces）."""
    return [f["faces"] for f in face_layout(walls)]


def wall_from_details(det: dict) -> dict | None:
    """Tapir の壁の詳細 → {"a", "b"（外形の長い辺の片方の面の始めと終わり, mm）, "n"（その面から壁の中への向き）,
    "thick", "z0", "height"}. 直線の壁だけ（曲がった壁・傾いた壁は None）."""
    d = det.get("details") or {}
    if d.get("geometryType") not in (None, "Straight") or abs(float(d.get("slantAlpha", math.pi / 2)) - math.pi / 2) > 1e-3 \
            or abs(float(d.get("slantBeta", math.pi / 2)) - math.pi / 2) > 1e-3:
        return None
    b0, e0 = d.get("begCoordinate"), d.get("endCoordinate")
    if not b0 or not e0:
        return None
    a = (float(b0["x"]) * 1000.0, float(b0["y"]) * 1000.0)
    b = (float(e0["x"]) * 1000.0, float(e0["y"]) * 1000.0)
    L = math.dist(a, b)
    if L < 100.0:
        return None
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])                                      # 左
    # 長さは基準線の始めから終わり。面の位置（基準線からのずれ）は平面の外形の点から（基準線の位置・ずれに関わらず）。
    # 壁どうしがつながると外形は角の切れ端だけになることがあるので、厚さと合わなければ基準線の位置から
    t = float(d.get("begThickness", 0.2)) * 1000.0
    pts = [(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for poly in (det.get("floorPlanPolygons") or [])
           for p in poly.get("coordinates", [])]
    offs = [(p[0] - a[0]) * n[0] + (p[1] - a[1]) * n[1] for p in pts]
    if offs and abs((max(offs) - min(offs)) - t) <= 2.0:
        lo, hi = min(offs), max(offs)
    else:
        ref = d.get("referenceLineLocation", "Center")
        off = float(d.get("offset", 0.0)) * 1000.0
        if ref == "Center":
            lo, hi = -t / 2.0, t / 2.0
        else:
            # 外側・内側の面が基準線（反転していなければ壁は左に）
            lo, hi = (0.0, t) if not d.get("flipped") else (-t, 0.0)
        lo, hi = lo + off, hi + off
    t0, t1 = 0.0, L
    thick = hi - lo
    # 右の面（lo）の始めから、壁の向きに
    p0 = (a[0] + u[0] * t0 + n[0] * lo, a[1] + u[1] * t0 + n[1] * lo)
    p1 = (a[0] + u[0] * t1 + n[0] * lo, a[1] + u[1] * t1 + n[1] * lo)
    z0 = (float(d.get("zCoordinate", 0.0)) + float(d.get("bottomOffset", 0.0))) * 1000.0
    return {"a": p0, "b": p1, "n": n, "u": u, "ca": a, "cb": b, "lo": lo, "hi": hi, "thick": thick, "z0": z0,
            "height": float(d.get("height", 0.0)) * 1000.0, "length": t1 - t0, "ang": math.degrees(math.atan2(u[1], u[0]))}
