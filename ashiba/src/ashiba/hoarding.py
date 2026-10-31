"""仮囲い（利用者の指定 2026-11-01: 仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ）.
部品 ashiba_kakoi（線・ポリラインの1区間に1つ）。

組み方（ミルックスの 3m 仮囲い計画図・藤田の安全鋼板の拾い方・鈴東の数量計算・ゲート工業／HSK のカタログ）:
- 単管 φ48.6 の支柱を 1,800 ごとに立て（打込みは根入れ 1,000 以上。粘性土 N値4以上）、外側に横地（布単管）を直交クランプで
  3段（3m。パネルの上端・下端から 150 と中）か2段（2m）。パネルは横地にフックボルト（安全鋼板）・Jフック（フラットパネル）で掛ける
- パネルの下端は地面から 200 浮かす。安全鋼板は有効幅 540（t1.2、2m 12.0kg・3m 18.0kg）、フラットパネルは有効幅 500
  （2m 約12kg・3m 18.9kg）、防音パネル（アドフラット防音）W500×H3,000 18.8kg。メッシュフェンス（ガードフェンス）H1,800×W1,800
- 控え（単管）は支柱ごとに内側へ。3m は 2.5m の単管を支柱の高さ約 1,900 に掛けて後ろ約 1,300 の杭へ（約 55°）、地上約 300 に
  コロバシ（水平つなぎ）。控えの間隔の目安の許容風速は 3.6m で 15m/s、1.8m で 25m/s、0.9m で 35m/s（ミルックス）
- 基礎: 単管の打込み・根巻きコンクリート（150×150×500）・H形鋼（H-300 を2列 1,700 幅で敷き、キャッチクランプで留める）
- 斜めの角は蝶番式の自在コーナー（鈴東: 出隅 70〜180°・入隅 60〜180°）、直交しない単管は自在クランプ。半端は幅調整パネル
  （50〜480）か安全鋼板の重ね代（10〜30）で吸収する
法令: 建築基準法施行令 136条の2の20（木造で高さ 13m・軒の高さ 9m を超える、または木造以外で2階以上の工事は高さ 1.8m 以上の
仮囲い）、建設工事公衆災害防止対策要綱 建築工事等編 第21（1.8m 以上、特に必要なら 3m。強風で倒れない構造。出入口は普段閉めて
引戸か内開き）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

POST_PITCH_MM = 1800.0             # 支柱の間隔
LIFT_MM = 200.0                    # パネルの下端を地面から浮かす
RAIL_EDGE_MM = 150.0               # 横地はパネルの上端・下端からこれだけ内
POST_TOP_MM = 50.0                 # 支柱の天端はパネルの上端からこれだけ上
EMBED_MM = 1000.0                  # 打込みの根入れ
RAIL_OFF_MM = 48.6                 # 横地の芯は支柱の芯から外へ（φ48.6 どうし）
PANEL_OFF_MM = 48.6 + 24.3 + 2.0   # パネルの裏は支柱の芯から外へ（横地の外面＋フック）
KOROBASHI_Z_MM = 300.0             # コロバシ（水平つなぎ）の高さ
H_BEAM_GAP_MM = 1700.0             # H形鋼の基礎の2列の幅
GATE_POST_MM = 100.0               # ゲートの柱（□100）
CORNER_MIN_OUT, CORNER_MIN_IN = 70.0, 60.0   # 自在コーナー（鈴東）が受けられる角（内角。出隅・入隅）
DESIGN_WIND_MS = 25.0              # 既定の設計風速（国交省 雪寒仮囲い要領の最大 25m/s）
# 控えの間隔ごとの許容風速の目安（3m の仮囲い。ミルックスの計画図）
WIND_BY_BRACE = ((900.0, 35.0), (1800.0, 25.0), (3600.0, 15.0))


@dataclass(frozen=True)
class Panel:
    kind: int                      # 部品の kkType
    name: str
    eff: float                     # 有効幅（働き幅）mm
    kg: dict                       # 高さ mm → 1枚の重さ kg
    fixers: dict                   # 高さ mm → 1枚の取付金具の数
    fixer: str
    lift: float = LIFT_MM


PANELS = {
    "安全鋼板": Panel(1, "安全鋼板 t1.2", 540.0, {2000: 12.0, 3000: 18.0}, {2000: 4, 3000: 6}, "フックボルト"),
    "フラットパネル": Panel(2, "フラットパネル", 500.0, {2000: 12.0, 3000: 18.9}, {2000: 4, 3000: 6}, "Jフック"),
    "防音パネル": Panel(3, "防音パネル（アドフラット防音）", 500.0, {3000: 18.8}, {3000: 6}, "Jフック"),
    "メッシュフェンス": Panel(4, "メッシュフェンス（ガードフェンス）", 1800.0, {1800: 12.0}, {1800: 4}, "番線", 50.0),
}
FOUNDATIONS = {"打込み": 1, "根巻き": 2, "H形鋼": 3}
GATES = {   # 種類 → (部品の番号, 高さ mm, 説明)
    "キャスター": (1, 2000.0, "パネルキャスターゲート（引戸。たたみ代 370×2）"),
    "ジャバラ": (2, 1800.0, "クロスゲート（ジャバラ。引戸）"),
    "ドア": (3, 2000.0, "パネルドア W810（内開き）"),
}
SOURCES = ("ミルックス 3m 仮囲い計画図・藤田 安全鋼板の拾い方・鈴東 数量計算（自在コーナー 出隅 70〜180°・入隅 60〜180°）・"
           "ゲート工業／HSK カタログ（フラットパネル・ゲート）、建築基準法施行令 136条の2の20、建設工事公衆災害防止対策要綱 "
           "建築工事等編 第21")


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Segment:
    """仮囲いの1区間（線・ポリラインの1辺）。外（道路の側）は進む向きの右（部品の −Y）."""
    p0: tuple
    p1: tuple
    ext0: float = 0.0              # パネル・横地を始めの角で延ばす長さ（出隅＋、入隅−）
    ext1: float = 0.0
    post0: bool = True             # 始めの角に支柱を立てる（前の辺と共有するなら False）
    turn0: float = 0.0             # 始めの角の折れ（度。左へ＋）。角が無ければ 0
    turn1: float = 0.0

    @property
    def length(self) -> float:
        return math.dist(self.p0, self.p1)

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.p1[1] - self.p0[1], self.p1[0] - self.p0[0]))


def _turn(a, b, c) -> float:
    """a→b→c の折れ（度。左へ曲がると＋）."""
    t1 = math.atan2(b[1] - a[1], b[0] - a[0])
    t2 = math.atan2(c[1] - b[1], c[0] - b[0])
    d = math.degrees(t2 - t1)
    return (d + 180.0) % 360.0 - 180.0


def _ext(turn_deg: float, off: float) -> float:
    """角で外の面（芯から off 外）を延ばす長さ。左へ曲がる角は外が出隅（＋）、右は入隅（−）."""
    return off * math.tan(math.radians(abs(turn_deg)) / 2.0) * (1.0 if turn_deg > 0 else -1.0)


def polyline_layout(pts: list, closed: bool = False, outside_right: bool = True) -> list[Segment]:
    """点列 → 区間。斜めの辺も同じ（区間ごとに向きを持つ）。外は進む向きの右（outside_right=False なら左にそろえるため
    点列を逆に回す）。角の支柱は前の辺と共有し、パネル・横地は角の二等分線まで延ばす・縮める."""
    p = [tuple(map(float, q)) for q in pts]
    if closed and len(p) > 2 and math.dist(p[0], p[-1]) < 1.0:
        p = p[:-1]
    if not outside_right:
        p = p[::-1]
    p = [q for i, q in enumerate(p) if i == 0 or math.dist(q, p[i - 1]) > 1.0]
    n = len(p)
    if n < 2:
        return []
    m = n if closed and n > 2 else n - 1
    segs = []
    for i in range(m):
        a, b = p[i], p[(i + 1) % n]
        s = Segment(a, b)
        if closed and n > 2 or i > 0:
            s.turn0 = _turn(p[(i - 1) % n], a, b)
            s.post0 = False
        if closed and n > 2 or i < m - 1:
            s.turn1 = _turn(a, b, p[(i + 2) % n])
        s.ext0, s.ext1 = _ext(s.turn0, PANEL_OFF_MM), _ext(s.turn1, PANEL_OFF_MM)
        segs.append(s)
    return segs


def outside_is_right(pts: list, inside_pt: Optional[tuple]) -> bool:
    """敷地の中の点（建物の重心など）が進む向きの左にあれば、外（道路の側）は右."""
    if inside_pt is None or len(pts) < 2:
        if len(pts) > 2:          # 閉じた形は反時計回りなら中が左
            a = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
            return a > 0
        return True
    best, side = None, 0.0
    for a, b in zip(pts, pts[1:]):
        L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 or 1.0
        t = max(0.0, min(1.0, ((inside_pt[0] - a[0]) * (b[0] - a[0]) + (inside_pt[1] - a[1]) * (b[1] - a[1])) / L2))
        d = math.dist(inside_pt, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if best is None or d < best:
            best = d
            side = (b[0] - a[0]) * (inside_pt[1] - a[1]) - (b[1] - a[1]) * (inside_pt[0] - a[0])
    return side > 0


@dataclass
class HoardPlan:
    name: str
    seg: Segment
    height: float                  # パネルの高さ
    panel: Panel
    posts: list[float]             # 支柱の位置（始めから mm）
    post_z: list[float]            # 支柱の足元の地盤（区間の始めの地盤から mm）
    rails: list[float]             # 横地の高さ（地盤から）
    runs: list[tuple[float, float]]            # パネルを張る範囲（ゲートで切る）
    gates: list[tuple[float, float, str]]      # ゲート（始め・終わり・種類）
    brace_every: int
    foundation: str
    quantity: list[tuple[str, float, str]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)

    @property
    def top(self) -> float:
        return self.panel.lift + self.height

    @property
    def braces(self) -> list[int]:
        """控えを掛ける支柱の番号（ゲートの柱・ゲートの中は除く）."""
        out = []
        for k, x in enumerate(self.posts):
            if any(g0 - 1.0 <= x <= g1 + 1.0 for g0, g1, _k in self.gates):
                continue
            if k % self.brace_every == 0 or k == len(self.posts) - 1:
                out.append(k)
        return out

    @property
    def brace_h(self) -> float:
        return round(min(1900.0, self.top * 0.6) / 50.0) * 50.0

    @property
    def brace_back(self) -> float:
        if self.foundation == "H形鋼":
            return H_BEAM_GAP_MM                                 # 後ろの列の H形鋼に落とす
        return round(self.brace_h * 0.68 / 50.0) * 50.0          # 約 55°


def _ceil_tube(mm: float) -> float:
    return math.ceil(mm / 500.0) * 500.0


def rail_heights(panel: Panel, height: float) -> list[float]:
    lo, hi = panel.lift + RAIL_EDGE_MM, panel.lift + height - RAIL_EDGE_MM
    if height >= 2500.0:
        return [lo, (lo + hi) / 2.0, hi]
    return [lo, hi]


def hoarding_plan(name: str, seg: Segment, height: float = 3000.0, panel: str = "安全鋼板", foundation: str = "打込み",
                  gates: Optional[list] = None, brace_every: int = 1, wind_ms: float = DESIGN_WIND_MS,
                  ground: Optional[Callable[[float, float], float]] = None, pitch: float = POST_PITCH_MM) -> HoardPlan:
    """1区間の割付・数量・検定。gates は [(始め mm, 幅 mm, 種類)]（区間の始めから）。ground(x, y) は地盤の高さ（mm）."""
    pn = PANELS[panel]
    if pn.kind == 4:
        height, pitch = 1800.0, 1800.0
    L = seg.length
    gl = sorted((max(0.0, g0), min(L, g0 + w), k) for g0, w, k in (gates or []) if w > 0 and g0 < L)
    # 支柱: 端と、ゲートの両脇の柱の間を pitch 以下で等分
    marks = [0.0] + [v for g0, g1, _k in gl for v in (g0, g1)] + [L]
    posts: list[float] = []
    for a, b in zip(marks[::2], marks[1::2]):
        if b - a < 1.0:
            continue
        n = max(1, math.ceil((b - a) / pitch - 1e-9))
        posts += [a + (b - a) * k / n for k in range(n + 1)]
    posts = sorted({round(x, 1) for x in posts})
    if not seg.post0 and posts and posts[0] < 1.0 and not any(g0 < 1.0 for g0, _g1, _k in gl):
        posts = posts[1:]
    ux, uy = (seg.p1[0] - seg.p0[0]) / (L or 1.0), (seg.p1[1] - seg.p0[1]) / (L or 1.0)
    z0 = ground(*seg.p0) if ground else 0.0
    post_z = [round(ground(seg.p0[0] + ux * x, seg.p0[1] + uy * x) - z0, 1) if ground else 0.0 for x in posts]
    runs, x = [], -seg.ext0
    for g0, g1, _k in gl:
        if g0 - x > 1.0:
            runs.append((x, g0))
        x = g1
    if L + seg.ext1 - x > 1.0:
        runs.append((x, L + seg.ext1))
    p = HoardPlan(name, seg, height, pn, posts, post_z, rail_heights(pn, height), runs, gl, max(1, brace_every),
                  foundation)
    _quantity(p)
    _checks(p, wind_ms, pitch)
    return p


def _quantity(p: HoardPlan) -> None:
    q, pn, H = p.quantity, p.panel, p.height
    nb = len(p.posts)
    run_len = sum(b - a for a, b in p.runs)
    n_panel = 0
    adj = 0
    for a, b in p.runs:
        full, rest = divmod(b - a, pn.eff)
        if pn.kind in (2, 3) and rest > 10.0:
            n_panel += int(full)
            adj += 1
        else:
            n_panel += int(full) + (1 if rest > 10.0 else 0)
    kg = pn.kg.get(int(H), max(pn.kg.values()) * H / max(pn.kg))
    q.append((f"{pn.name} H{H:.0f}", n_panel, f"有効幅 {pn.eff:.0f}・延べ {run_len / 1000:.1f}m・1枚 {kg:.1f}kg"))
    if adj:
        q.append(("幅調整パネル（50〜480）", adj, "半端の幅"))
    fix = pn.fixers.get(int(H), 2 * len(p.rails))
    q.append((pn.fixer, (n_panel + adj) * fix, f"1枚に {fix}"))
    tube_post = _ceil_tube(p.top + POST_TOP_MM + (EMBED_MM if p.foundation == "打込み" else 0.0))
    q.append((f"単管 {tube_post / 1000:.1f}m（支柱）", nb, f"@{POST_PITCH_MM:.0f} 以内" +
              ("・根入れ 1,000 以上（粘性土 N値4以上）" if p.foundation == "打込み" else "")))
    n5 = sum(math.ceil((b - a) / 5000.0) for a, b in p.runs)
    q.append(("単管 5.0m（横地）", n5 * len(p.rails), f"{len(p.rails)}段"))
    q.append(("単管ジョイント", max(0, n5 - len(p.runs)) * len(p.rails), "横地の継ぎ"))
    q.append(("直交クランプ（支柱・横地）", nb * len(p.rails), ""))
    corner = sum(1 for t in (p.seg.turn0, p.seg.turn1) if abs(t) > 1.0)
    skew = sum(1 for t in (p.seg.turn0, p.seg.turn1) if 1.0 < abs(t) and abs(abs(t) - 90.0) > 1.0)
    if skew:
        q.append(("自在クランプ（斜めの角の横地）", skew * len(p.rails), "直交しない角は自在クランプ"))
    if p.seg.turn1 and abs(p.seg.turn1) > 1.0:   # 角の役物は終わりの角で数える（始めの角は前の辺）
        q.append(("コーナーパネル（自在・蝶番）" if pn.kind in (2, 3) else "角のパネル（重ね）", 1,
                  f"内角 {180.0 - abs(p.seg.turn1):.0f}°・{'出隅' if p.seg.turn1 > 0 else '入隅'}"))
    nbr = len(p.braces)
    bl = _ceil_tube(math.hypot(p.brace_h, p.brace_back) + 100.0)
    q.append((f"単管 {bl / 1000:.1f}m（控え）", nbr, f"支柱の高さ {p.brace_h:.0f} から後ろ {p.brace_back:.0f}（約 55°）"))
    q.append(("単管 1.5m（コロバシ）", nbr, f"地上 {KOROBASHI_Z_MM:.0f}"))
    q.append(("自在クランプ（控え・コロバシ）", nbr * 4, "控え1本に 4"))
    if p.foundation == "打込み":
        q.append(("単管 1.5m（控えの杭）", nbr * 2, "控え・コロバシの足元に打込み"))
    elif p.foundation == "根巻き":
        q.append(("根巻きコンクリート 150×150×500", nb + nbr, "支柱と控えの足元"))
    else:
        hl = _ceil_tube(p.seg.length + 300.0)
        q.append((f"H形鋼 H-300×300（{hl / 1000:.1f}m）", 2, f"2列（幅 {H_BEAM_GAP_MM:.0f}）を敷く"))
        q.append(("キャッチクランプ（H形鋼用）", (nb + nbr) * 2, "支柱・控えを H形鋼のフランジに 2個1組"))
    for g0, g1, k in p.gates:
        q.append((GATES[k][2], 1, f"間口 {g1 - g0:.0f}"))


def _checks(p: HoardPlan, wind_ms: float, pitch: float) -> None:
    c = p.checks
    top = p.top
    c.append(Check("仮囲いの高さ", "OK" if top >= 1800.0 else "NG",
                   f"地盤から {top:.0f}（1.8m 以上。施行令 136条の2の20・公衆災害防止対策要綱 建築 第21。特に必要なら 3m）"))
    gaps = [b - a for a, b in zip(p.posts, p.posts[1:])
            if not any(g0 - 1.0 <= a and b <= g1 + 1.0 for g0, g1, _k in p.gates)]
    pm = max(gaps, default=0.0)
    c.append(Check("支柱の間隔", "OK" if pm <= pitch + 1.0 else "NG", f"最大 {pm:.0f}（{pitch:.0f} 以内）"))
    sp = pitch * p.brace_every
    allow = next((w for s, w in WIND_BY_BRACE if sp <= s + 1.0), 0.0)
    if p.panel.kind == 4:
        c.append(Check("風", "OK", "メッシュは風を通す（風力係数 0.9。板は 1.3）"))
    else:
        c.append(Check("控えと風", "OK" if allow >= wind_ms else "WARN",
                       f"控え @{sp:.0f} の許容風速の目安 {allow:.0f}m/s（3m の仮囲い。ミルックス）／設計風速 {wind_ms:.0f}m/s"
                       + ("" if allow >= wind_ms else "。控えを支柱ごとに・強風の前にパネルを外す")))
    for t, where in ((p.seg.turn0, "始め"), (p.seg.turn1, "終わり")):
        if abs(t) <= 1.0:
            continue
        inner = 180.0 - abs(t)
        lim = CORNER_MIN_OUT if t > 0 else CORNER_MIN_IN
        c.append(Check(f"{where}の角", "OK" if inner >= lim else "WARN",
                       f"内角 {inner:.0f}°（{'出隅' if t > 0 else '入隅'}。自在コーナーは {lim:.0f}〜180°）"
                       + ("" if inner >= lim else "。鋭すぎる。角を2つの折れに分ける")))
    if p.post_z and max(p.post_z) - min(p.post_z) > 1.0:
        dz = max(p.post_z) - min(p.post_z)
        slope = dz / max(1.0, p.seg.length)
        c.append(Check("地盤の高低差", "OK" if slope <= 0.10 else "WARN",
                       f"区間の中で {dz:.0f}（勾配 {slope * 100:.1f}%）。パネルは1枚ずつ地盤に合わせて上下にずらし、横地は地盤に沿って"
                       "流す（自在クランプ）" + ("" if slope <= 0.10 else "。10% を超えるので段切りか、パネルの下のすき間をふさぐ")))
    for g0, g1, k in p.gates:
        c.append(Check("出入口", "OK", f"{GATES[k][2]}・間口 {g1 - g0:.0f}。普段は閉め、引戸か内開き。車両の出入りが多ければ誘導員"
                                       "（公衆災害防止対策要綱 建築 第21）"))


def part_params(p: HoardPlan) -> dict:
    """部品 ashiba_kakoi のパラメータ（m）."""
    gk = {k: v[0] for k, v in GATES.items()}
    return {"kkType": p.panel.kind, "kkL": p.seg.length / 1000.0, "pnH": p.height / 1000.0, "pnW": p.panel.eff / 1000.0,
            "lift": p.panel.lift / 1000.0, "postX": ",".join(f"{x:.0f}" for x in p.posts),
            "postZ": ",".join(f"{z:.0f}" for z in p.post_z), "railZ": ",".join(f"{z:.0f}" for z in p.rails),
            "runX": ",".join(f"{a:.0f},{b:.0f}" for a, b in p.runs),
            "gateX": ",".join(f"{a:.0f},{b:.0f}" for a, b, _k in p.gates),
            "gateK": ",".join(str(gk[k]) for _a, _b, k in p.gates),
            "brX": ",".join(f"{p.posts[k]:.0f}" for k in p.braces), "brH": p.brace_h / 1000.0,
            "brB": p.brace_back / 1000.0,
            "kkFound": FOUNDATIONS[p.foundation], "embed": EMBED_MM / 1000.0, "kkName": f"仮囲い {p.name}"}


def report(plans: list[HoardPlan]) -> str:
    out = ["# 仮囲い", "", f"出典: {SOURCES}", ""]
    total: dict[str, float] = {}
    for p in plans:
        out += [f"## {p.name}（長さ {p.seg.length:.0f}mm・向き {p.seg.angle:.1f}°・パネルの上端 {p.top:.0f}）", "",
                "| 品名 | 数 | 注 |", "|---|---|---|"]
        out += [f"| {a} | {b:g} | {c} |" for a, b, c in p.quantity]
        out += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        out += [f"| {c.item} | {c.status} | {c.message} |" for c in p.checks]
        out.append("")
        for a, b, _c in p.quantity:
            total[a] = total.get(a, 0) + b
    if len(plans) > 1:
        out += ["## 合計", "", "| 品名 | 数 |", "|---|---|"] + [f"| {a} | {b:g} |" for a, b in total.items()]
    return "\n".join(out)


def inset_polygon(pts: list, d: float) -> list:
    """閉じた多角形を中へ d だけ寄せる（辺を平行に寄せて隣の辺と交わる点。斜めの辺も同じ）。敷地境界から仮囲いの芯へ."""
    p = [tuple(map(float, q)) for q in pts]
    if len(p) > 2 and math.dist(p[0], p[-1]) < 1.0:
        p = p[:-1]
    n = len(p)
    if n < 3:
        return p
    area = sum(p[i][0] * p[(i + 1) % n][1] - p[(i + 1) % n][0] * p[i][1] for i in range(n))
    s = 1.0 if area > 0 else -1.0                 # 反時計回りなら中は左
    lines = []
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        L = math.dist(a, b) or 1.0
        nx, ny = -(b[1] - a[1]) / L * s, (b[0] - a[0]) / L * s     # 中への法線
        lines.append(((a[0] + nx * d, a[1] + ny * d), (b[0] + nx * d, b[1] + ny * d)))
    out = []
    for i in range(n):
        (a1, b1), (a2, b2) = lines[i - 1], lines[i]
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        d2 = (b2[0] - a2[0], b2[1] - a2[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(a2)
            continue
        t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
        out.append((a1[0] + d1[0] * t, a1[1] + d1[1] * t))
    return out


def split_gates(segs: list[Segment], gates: list) -> list[list]:
    """ポリラインの始めからの位置で指定したゲート [(位置, 幅, 種類)] を区間ごとの [(区間の始めから, 幅, 種類)] に分ける."""
    out: list[list] = [[] for _ in segs]
    acc = 0.0
    for i, s in enumerate(segs):
        L = s.length
        for g0, w, k in gates:
            if acc - 1.0 <= g0 < acc + L - 1.0:
                out[i].append((g0 - acc, min(w, acc + L - g0), k))
        acc += L
    return out
