"""乗入れ構台・荷取り構台（開発ループ 2026-11-01: 前に挙げた「他に必要な仮設材」の2番。部品 ashiba_kodai）.

根切りの上に車両・重機を乗り入れる構台（覆工板 → 根太 → 大引 → 支柱。支柱は水平つなぎと垂直ブレースでつなぐ）の割付・数量・検定。

出典（調べた資料。日本建築学会「乗入れ構台設計・施工指針」2014 の本文は有料で読めず、付録の設計例を入力した計算書で値を拾った）:
- FORUM8「乗入れ構台設計例（中小規模）建築学会 H26 のサンプルデータ」（指針 付1 p.97〜）: 衝撃係数 0.2・水平係数 0.2・
  たわみ 支間/300 かつ 2.0cm・短期の割増 1.5、幅員 8m・支柱 6×6m・張出し 1m、根太・大引 H-400×400・支柱 H-350×350・
  水平つなぎ [-200×90・ブレース L-75×75×6、アウトリガ1脚 α=0.70×(W+T)、Ra=(2/3)(qd·Ap+U·Σli·fi)・qd=200N
- 同 操作ガイダンス（重機の登録値: ラフター 20/25/40/65t・クローラ 50t・T-25）、AIJ 講習会資料 鹿島「乗入れ構台計画」
  （幅 6〜8m・スロープ 1/10〜1/7・支柱は基礎杭・柱・梁を避け切梁と合わせる）、ヒロセ 鋼製山留総合カタログ p.33〜34
  （組み方の順・スロープ 1:6〜1:10）、日本製鉄 メトロデッキ（覆工板 1×2m 424kg・1×3m 624kg・高さ 208）
- 労働安全衛生規則 575条の2〜8（作業構台: 材料・最大積載荷重の周知・組立図・根入れ・すき間 3cm 以下・手すり 85cm 以上と
  中さん 35〜50cm・点検）、建設工事公衆災害防止対策要綱 建築工事編 第35（荷受け構台の手すり・幅木）

割付（構台の向き: +X＝進行方向）: 覆工板は X に 1m・Y に 2m の列で並べ、幅の端数に 3m を1列混ぜる（deck_rows）。根太は列の
境目ごとに X へ通す（覆工板の
長手は根太に直交）。大引は支柱の列ごとに Y へ。支柱は縁から張出し ovh の内側を最大 spMax 以内で等分した格子。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.80665
E_STEEL = 205000.0                     # N/mm²
F_SS400 = 235.0                        # N/mm²（短期の許容応力度＝F）
IMPACT = 0.2                           # 衝撃係数（AIJ。覆工板以外も 0.2）
KH = 0.2                               # 水平係数（AIJ）
OUTRIGGER = 0.70                       # アウトリガ1脚の荷重分担率（作業側の最大の1脚）
CRAWLER = 0.80                         # クローラ 側方吊の作業側の分担率
DEFL_RATIO, DEFL_MAX_MM = 300.0, 20.0  # たわみ 支間/300 かつ 2.0cm
DECK_KN_M2 = 2.0                       # 覆工板の固定荷重
DECK_H_MM = 208.0                      # 覆工板の高さ（メトロデッキ）
DECKS = {2.0: 424.0, 3.0: 624.0}       # 覆工板 1m×長さ → kg
SLOPE_MIN = 6.0                        # スロープは 1/6 より緩く（ヒロセ 1:6〜1:10、鹿島 1/10〜1/7）
RAIL_H_MM, MID_H_MM, TOE_H_MM = 950.0, 450.0, 150.0   # 手すり 85cm 以上・中さん 35〜50cm・幅木（公衆災害防止 第35）
RAIL_POST_MM = 1800.0
OVH_MAX_MM = 1500.0                    # 張出し（片持ち）の目安の上限
TIE_PITCH_MM = 3000.0                  # 水平つなぎの段の間隔の目安（設計例 2.8・3.5m）
BOLTS = 4                              # 大引と支柱 M22 を4本

# H形鋼（JIS G 3192 の標準断面。利用者の指定 2026-11-01: H鋼の種類も選べるように）: h, b, tw, tf mm・A cm²・Ix cm⁴・Zx cm³・
# iy cm・kg/m。部品の secJ・secG・secP はこの並びの番号（1〜10）
H_SECTIONS = {
    "H-200": (200.0, 200.0, 8.0, 12.0, 63.53, 4720.0, 472.0, 5.02, 49.9),
    "H-250": (250.0, 250.0, 9.0, 14.0, 91.43, 10700.0, 860.0, 6.29, 71.8),
    "H-300": (300.0, 300.0, 10.0, 15.0, 118.5, 20200.0, 1350.0, 7.51, 94.0),
    "H-350": (350.0, 350.0, 12.0, 19.0, 171.9, 39800.0, 2280.0, 8.84, 135.0),
    "H-400": (400.0, 400.0, 13.0, 21.0, 218.7, 66600.0, 3330.0, 10.1, 172.0),
    "H-414": (414.0, 405.0, 18.0, 28.0, 295.4, 92800.0, 4480.0, 10.2, 232.0),
    "H-428": (428.0, 407.0, 20.0, 35.0, 360.7, 119000.0, 5570.0, 10.4, 283.0),
    "H-488": (488.0, 300.0, 11.0, 18.0, 159.2, 68900.0, 2820.0, 7.04, 125.0),
    "H-588": (588.0, 300.0, 12.0, 20.0, 187.2, 114000.0, 3890.0, 6.90, 147.0),
    "H-594": (594.0, 302.0, 14.0, 23.0, 222.4, 137000.0, 4620.0, 6.85, 175.0),
}
TIE = ("[-200×90×8×13.5", 30.3)                       # 水平つなぎ（溝形鋼）kg/m
BRACE = ("L-75×75×6", 6.85, 8.727, 22.0)              # 垂直ブレース（山形鋼）kg/m・A cm²・ボルト穴 mm（M20）

# 重機・車両（FORUM8 の登録値。AIJ の設計例と同じ）: 名前, 自重 W kN, 吊荷 T kN, 輪荷重（後輪 片側）kN, 種類, 接地長 m
VEHICLES = {
    "T25": ("トラック T-25（生コン車・ダンプ）", 250.0, 0.0, 100.0, "truck", 0.0),
    "R20": ("ラフテレーンクレーン 20t", 200.0, 30.0, 80.0, "rough", 0.0),
    "R25": ("ラフテレーンクレーン 25t", 250.0, 30.0, 100.0, "rough", 0.0),
    "R40": ("ラフテレーンクレーン 40t", 350.0, 30.0, 140.0, "rough", 0.0),
    "R65": ("ラフテレーンクレーン 65t", 395.0, 30.0, 98.75, "rough", 0.0),
    "C50": ("クローラクレーン 50t", 470.0, 50.0, 0.0, "crawler", 4.70),
}


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Plan:
    name: str
    length: float                      # X（進行方向）mm
    width: float                       # Y mm
    rows: list[float]                  # 覆工板の列の長さ mm（Y の手前から。2,000 が基本、幅の端数に 3,000 を1列）
    xs: list[float]                    # 支柱・大引の X mm
    ys: list[float]                    # 支柱の Y mm
    joists: list[float]                # 根太の Y mm
    levels: list[float]                # 水平つなぎの高さ（構台の床の上端から下へ mm・正）
    top: float                         # 床の上端の高さ（地盤から mm）
    depth: float                       # 地盤から根切り底まで mm
    embed: float                       # 根切り底から下の根入れ mm
    joist: str = "H-400"
    girder: str = "H-400"
    post: str = "H-350"
    vehicle: str = "R25"
    load_t: float = 3.0
    slope: float = 8.0                 # スロープ 1/slope（0＝なし）
    rails: str = "SNE"                 # 手すりの辺（S＝Y0・N＝Y 最大・E＝X 最大・W＝X0）
    kind: str = "乗入れ構台"
    sp_max: float = 6000.0             # 支柱の間隔の上限 mm
    ov: float = 1000.0                 # 張出し mm
    n_value: float = 20.0              # 支柱の先の N 値
    n3_req: int = -1                   # 3m の列の数の決め（−1＝自動。部品の dk3 にそのまま）
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)
    max_load_t: float = 0.0

    @property
    def deck_len(self) -> float:
        """一番長い覆工板 m（覆工板の支間・根太の受け持ち幅）."""
        return max(self.rows) / 1000.0

    @property
    def n3(self) -> int:
        return sum(1 for r in self.rows if r > 2500.0)

    @property
    def post_top(self) -> float:
        """支柱の天端（床の上端から下へ mm）."""
        return DECK_H_MM + H_SECTIONS[self.joist][0] + H_SECTIONS[self.girder][0]

    @property
    def post_len(self) -> float:
        return self.top + self.depth + self.embed - self.post_top

    @property
    def slope_len(self) -> float:
        return self.top * self.slope if self.slope > 0 and self.top > 50.0 else 0.0


def grid(length: float, ov: float, sp_max: float) -> list[float]:
    """縁から ov の内側を sp_max 以内で等分した支柱の位置 mm."""
    inner = max(length - 2.0 * ov, 0.0)
    n = max(1, math.ceil(inner / sp_max - 1e-6))
    return [ov + inner * i / n for i in range(n + 1)]


def snap(length: float, unit: float) -> float:
    """長さを unit の倍数に切り上げる（2% までのはみ出しは切り下げ。部品のパラメータスクリプトと同じ）."""
    return max(1, math.ceil(length / unit - 0.02)) * unit


def tie_levels(post_top: float, bottom: float, pitch: float = TIE_PITCH_MM) -> list[float]:
    """水平つなぎの段（床の上端から下へ mm）: 一番上は大引のすぐ下、そこから pitch 以内で等分し、一番下は根切り底の 300 上
    （根がらみ）."""
    last = bottom - 300.0
    if last <= post_top + 300.0:
        return [post_top]
    n = max(1, math.ceil((last - post_top) / pitch - 1e-6))
    return [post_top + (last - post_top) * i / n for i in range(n + 1)]


def deck_rows(width: float, n3: int = -1, at: int = 1) -> list[float]:
    """覆工板の列（Y の手前から mm）。2m が基本で、幅を合わせるのに 3m を混ぜる（利用者の指定 2026-11-01: 全部が 3m じゃないよ
    1列だけだよね）。n3＝−1（自動）は幅を 1m に切り上げ、奇数 m なら 3m を1列（7m＝2＋2＋3）。n3≧0 は 3m をその列数にして残りを
    2m で。at＝3m の列を入れる位置（手前から何列目）。部品のパラメータスクリプトと同じ."""
    if n3 < 0:
        wm = max(2, math.ceil(width / 1000.0 - 0.02))
        n3 = wm % 2
        n2 = (wm - 3 * n3) // 2
    else:
        n2 = max(0, math.ceil((width - 3000.0 * n3) / 2000.0 - 0.01))
        if n2 + n3 == 0:
            n2 = 1
    rows = [2000.0] * n2
    k = max(1, min(at, n2 + 1)) - 1
    return rows[:k] + [3000.0] * n3 + rows[k:]


def layout(name: str, length: float, width: float, n3: int = -1, n3_at: int = 1, sp_max: float = 6000.0,
           ov: float = 1000.0, top: float = 0.0, depth: float = 5000.0, embed: float = 4000.0, **kw) -> Plan:
    L = snap(length, 1000.0)
    rows = deck_rows(width, n3, n3_at)
    W = sum(rows)
    p = Plan(name, L, W, rows, grid(L, ov, sp_max), grid(W, ov, sp_max),
             [sum(rows[:i]) for i in range(len(rows) + 1)], [], top, depth, embed, sp_max=sp_max, ov=ov, n3_req=n3, **kw)
    p.levels = tie_levels(p.post_top, top + depth)
    return p


def _fc(lk_mm: float, i_cm: float) -> float:
    """座屈の短期の許容圧縮応力度 N/mm²（鋼構造設計規準。SS400）."""
    lam = lk_mm / (i_cm * 10.0)
    big = math.sqrt(math.pi ** 2 * E_STEEL / (0.6 * F_SS400))
    r = lam / big
    if r <= 1.0:
        nu = 1.5 + 2.0 / 3.0 * r * r
        f = (1.0 - 0.4 * r * r) * F_SS400 / nu
    else:
        f = 0.277 * F_SS400 / (r * r)
    return 1.5 * f


def _beam(span_mm: float, sec: str, p_kn: float, w_kn_m: float, a_mm: float = 0.0) -> tuple[float, float]:
    """単純梁の中央に P（a＞0 なら長さ a に等分布）＋等分布 w → (曲げ応力度 N/mm², P のたわみ mm)."""
    h = H_SECTIONS[sec]
    L = span_mm
    a = min(a_mm, L)
    m = p_kn * 1000.0 * (L / 4.0 - a / 8.0) + w_kn_m * L * L / 8.0          # N·mm
    sig = m / (h[6] * 1000.0)
    ei = E_STEEL * h[5] * 1e4
    if a > 0:                                                                 # 中央の部分等分布のたわみ（近似: 集中と等分布の間）
        d = p_kn * 1000.0 * L ** 3 / (48.0 * ei) * (1.0 - 0.5 * (a / L) ** 2)
    else:
        d = p_kn * 1000.0 * L ** 3 / (48.0 * ei)
    return sig, d


def check(p: Plan, n_value: float | None = None) -> Plan:
    """部材の検定（AIJ の設計例の考え方。単純梁・軸力は期限付き構造物の扱いで安全側）と安衛則."""
    if n_value is None:
        n_value = p.n_value
    p.n_value = n_value
    name, W, T, wheel, kind, contact = VEHICLES[p.vehicle]
    T = max(T, p.load_t * G)
    c = p.checks = []
    sx = max(b - a for a, b in zip(p.xs, p.xs[1:])) if len(p.xs) > 1 else p.length
    sy = max(b - a for a, b in zip(p.ys, p.ys[1:])) if len(p.ys) > 1 else p.width
    jn, gn, pn = H_SECTIONS[p.joist], H_SECTIONS[p.girder], H_SECTIONS[p.post]
    pitch = p.deck_len * 1000.0
    # 1台の重機の載る荷重: トラックは後輪、ラフターはアウトリガ1脚（α=0.70）と走行の輪の大きい方、クローラは片側の履帯
    a = 0.0
    if kind == "crawler":
        pt, a, how = CRAWLER * (W + T), contact * 1000.0, f"片側の履帯に {CRAWLER:g}×(W＋T) を接地長 {contact:g}m に"
    elif kind == "rough":
        pt = max(wheel, OUTRIGGER * (W + T))
        how = f"アウトリガ1脚 {OUTRIGGER:g}×(W＋T)＝{OUTRIGGER * (W + T):.0f}kN と走行の輪 {wheel:g}kN の大きい方"
    else:
        pt, how = wheel, f"後輪 {wheel:g}kN"
    p.max_load_t = round((W + T) / G, 1)
    c.append(Check("覆工板", "OK" if (kind != "truck" or wheel <= 100.0) else "NG",
                   f"覆工板 1×2m" + (f"と 1×3m を {p.n3}列" if p.n3 else "") + f"（メトロデッキ 高さ {DECK_H_MM:.0f}・"
                   "T-25 相当）。根太に直交に並べ、支間 "
                   f"{p.deck_len - 0.1:.1f}m。ずれ止めは落し込み式" + ("。アウトリガは敷鉄板を根太に渡して中央に（クレーン則 70条の4）"
                                                                       if kind != "truck" else "")))
    # 根太（大引の間 sx の単純梁。荷重は根太で分散させない＝期限付き構造物の扱い）
    wj = DECK_KN_M2 * pitch / 1000.0 + jn[8] * G / 1000.0
    sig, d = _beam(sx, p.joist, pt * (1 + IMPACT), wj, a)
    _sig0, d0 = _beam(sx, p.joist, pt, 0.0, a)
    lim = min(sx / DEFL_RATIO, DEFL_MAX_MM)
    c.append(Check("根太", "OK" if sig <= F_SS400 and d0 <= lim else "NG",
                   f"{p.joist}・支間 {sx / 1000:.2f}m・{how}×衝撃 {1 + IMPACT:g}: 曲げ {sig:.0f} ≦ {F_SS400:.0f}N/mm²、たわみ "
                   f"{d0:.1f} ≦ {lim:.1f}mm（支間/300 かつ 2.0cm。衝撃・死荷重は入れない）"
                   + ("" if sig <= F_SS400 and d0 <= lim else "。支柱の間隔を詰めるか根太を大きく")))
    # 大引（支柱の間 sy）: 根太の反力を中央に1点＋死荷重
    wg = (DECK_KN_M2 + jn[8] * G / 1000.0 / (pitch / 1000.0)) * sx / 1000.0 + gn[8] * G / 1000.0
    pg = pt if kind != "crawler" else CRAWLER * (W + T) * min(1.0, sx / max(a, 1.0))
    sig, _ = _beam(sy, p.girder, pg * (1 + IMPACT), wg)
    _s, d0 = _beam(sy, p.girder, pg, 0.0)
    lim = min(sy / DEFL_RATIO, DEFL_MAX_MM)
    c.append(Check("大引", "OK" if sig <= F_SS400 and d0 <= lim else "NG",
                   f"{p.girder}・支間 {sy / 1000:.2f}m・根太の反力 {pg:.0f}kN を中央に×衝撃: 曲げ {sig:.0f} ≦ {F_SS400:.0f}N/mm²、"
                   f"たわみ {d0:.1f} ≦ {lim:.1f}mm" + ("" if sig <= F_SS400 and d0 <= lim else "。支柱を増やすか大引を H-588 に")))
    # 支柱: 重機の全重量（W＋T）×衝撃＋受け持つ床の固定荷重＋水平力による軸力（ΣH·h/l）
    dead = (DECK_KN_M2 + jn[8] * G / 1000.0 / (pitch / 1000.0) + gn[8] * G / 1000.0 / (sx / 1000.0)) * sx * sy / 1e6 \
        + pn[8] * G / 1000.0 * p.post_len / 1000.0
    h_all = KH * (W + T)
    span_y = (p.ys[-1] - p.ys[0]) or sy
    nh = h_all * (p.top + p.depth) / span_y
    n = (W + T) * (1 + IMPACT) + dead + nh
    segs = [b - a for a, b in zip(p.levels, p.levels[1:])] or [p.top + p.depth - p.post_top]
    lk = max(segs)
    fc = _fc(lk, pn[7])
    sc = n * 1000.0 / (pn[4] * 100.0)
    c.append(Check("支柱", "OK" if sc <= fc else "NG",
                   f"{p.post}・座屈長さ {lk / 1000:.2f}m（水平つなぎの間）: 軸力 {n:.0f}kN（{name} の W＋T＝{W + T:.0f}kN×衝撃＋固定 "
                   f"{dead:.0f}＋水平力 {nh:.0f}）→ {sc:.0f} ≦ fc {fc:.0f}N/mm²（弱軸・短期）" + ("" if sc <= fc else "。水平つなぎの段を増やす")))
    # 根入れの支持力（埋込み、閉塞断面）
    ap = pn[0] * pn[1] / 1e6
    u = 2.0 * (pn[0] + pn[1]) / 1000.0
    ra = 2.0 / 3.0 * (200.0 * min(n_value, 60.0) * ap + u * p.embed / 1000.0 * 10.0 * min(n_value, 30.0) / 3.0)
    c.append(Check("支柱の支持力", "OK" if n <= ra else "NG",
                   f"根入れ {p.embed / 1000:.1f}m・N 値 {n_value:g}（砂質土・埋込み）: Ra＝2/3×(200N·Ap＋U·l·10N/3)＝{ra:.0f} ≧ "
                   f"{n:.0f}kN" + ("" if n <= ra else "。根入れを深く・支柱を増やす") + "（安衛則 575条の6: 地質に応じた根入れ）"))
    # 垂直ブレース: 1構面が ΣH/2、構面の各間に引張のブレース
    bays = max(len(p.xs) - 1, len(p.ys) - 1, 1)
    bay = min(sx, sy)
    lv = max(segs)
    cos = bay / math.hypot(bay, lv)
    f_br = h_all / 2.0 / bays / cos
    an = BRACE[2] - BRACE[3] * 6.0 / 100.0
    c.append(Check("垂直ブレース", "OK" if f_br <= an * 100.0 * F_SS400 / 1000.0 else "NG",
                   f"{BRACE[0]}: 水平力 {KH:g}×(W＋T)＝{h_all:.0f}kN の 1/2 を1構面 {bays} 間で、1本 {f_br:.0f}kN ≦ "
                   f"{an * 100.0 * F_SS400 / 1000.0:.0f}kN（有効断面 {an:.2f}cm²）"))
    ovx, ovy = max(p.xs[0], p.length - p.xs[-1]), max(p.ys[0], p.width - p.ys[-1])
    c.append(Check("張出し", "OK" if max(ovx, ovy) <= OVH_MAX_MM else "WARN",
                   f"縁から支柱まで X {ovx / 1000:.2f}m・Y {ovy / 1000:.2f}m（設計例は 1m。{OVH_MAX_MM / 1000:g}m を超える片持ちは"
                   "根太・大引の先の曲げとたわみを別に確かめる）"))
    if p.slope_len:
        c.append(Check("スロープ", "OK" if p.slope >= SLOPE_MIN else "NG",
                       f"勾配 1/{p.slope:g}・長さ {p.slope_len / 1000:.1f}m（1/{SLOPE_MIN:g} より緩く。一般に 1/10〜1/7。急だと車体の底が"
                       "頂部に当たる）。スロープの下はコンクリートか盛土、根太の下に敷桁"))
    c.append(Check("手すり", "OK", f"{'・'.join({'S': '手前', 'N': '奥', 'E': '先', 'W': '入口'}[k] for k in p.rails) or 'なし'}の辺に"
                                  f"手すり {RAIL_H_MM:.0f}・中さん {MID_H_MM:.0f}・幅木 {TOE_H_MM:.0f}（安衛則 575条の6: 85cm 以上と "
                                  "35〜50cm。幅木は公衆災害防止対策要綱 第35）。床材のすき間 3cm 以下"))
    c.append(Check("最大積載荷重", "OK", f"{p.max_load_t:g}t（{name}＋吊荷）を札で表示し周知（575条の4）。組立図（支柱・床・根太・"
                                     "大引の配置と寸法）で組み立てる（575条の5）。作業前・悪天候・中震以上の地震の後に点検（575条の8）"))
    c.append(Check("山留め・躯体", "OK", "支柱は基礎杭・柱・梁・耐力壁を避け、切梁と位置を合わせる。切梁支柱と兼ねるなら軸力に切梁の"
                                      "自重と切梁軸力/50 を足す。ブレースの段は切梁・腹起しと重ねない"))
    return p


def quantity(p: Plan) -> list[tuple[str, float, str]]:
    q = p.quantity = []
    for ln in (2.0, 3.0):
        nr = sum(1 for r in p.rows if abs(r - ln * 1000.0) < 1.0)
        if nr:
            nd, kg = int(round(p.length / 1000.0)) * nr, DECKS[ln]
            q.append((f"覆工板 1×{ln:g}m（高さ {DECK_H_MM:.0f}）", nd, f"{nr}列・1枚 {kg:g}kg・計 {nd * kg / 1000:.1f}t"))
    for label, sec, ln in (("根太", p.joist, p.length * len(p.joists)), ("大引", p.girder, p.width * len(p.xs)),
                           ("支柱", p.post, p.post_len * len(p.xs) * len(p.ys))):
        h = H_SECTIONS[sec]
        q.append((f"{label} {sec}×{h[1]:.0f}", round(ln / 1000.0, 1), f"m・{h[8]:g}kg/m・計 {ln / 1000.0 * h[8] / 1000:.1f}t"))
    tie = len(p.levels) * ((p.xs[-1] - p.xs[0]) * len(p.ys) + (p.ys[-1] - p.ys[0]) * len(p.xs))
    q.append((f"水平つなぎ {TIE[0]}", round(tie / 1000.0, 1), f"m・{TIE[1]:g}kg/m（{len(p.levels)}段）"))
    nb = (len(p.levels) - 1) * 2 * 2 * ((len(p.xs) - 1) + (len(p.ys) - 1))   # 外周の4構面・水平つなぎの間ごとに X 形に2本
    q.append((f"垂直ブレース {BRACE[0]}", nb, "本（外周の構面・水平つなぎの間ごとに X 形）"))
    q.append(("大引と支柱の接合 M22 高力ボルト", BOLTS * len(p.xs) * len(p.ys), f"本（{BOLTS}本/か所）"))
    edges = {"S": p.length, "N": p.length, "E": p.width, "W": p.width}
    rl = sum(edges[k] for k in p.rails)
    if rl:
        q.append(("手すり・中さん 単管 φ48.6", round(2 * rl / 1000.0, 1), "m"))
        q.append(("手すり柱 単管", sum(math.ceil(edges[k] / RAIL_POST_MM) + 1 for k in p.rails), f"本（{RAIL_POST_MM:.0f} 以内）"))
        q.append(("幅木", round(rl / 1000.0, 1), f"m（高さ {TOE_H_MM:.0f}）"))
    if p.slope_len:
        q.append(("スロープ（覆工板・敷桁）", round(p.slope_len * p.width / 1e6, 1), f"m²（勾配 1/{p.slope:g}）"))
    q.append(("最大積載荷重の表示札", 1, f"{p.max_load_t:g}t"))
    return q


def kodai_plan(name: str, length: float, width: float, vehicle: str = "R25", load_t: float = 3.0, n_value: float = 20.0,
               **kw) -> Plan:
    p = layout(name, length, width, vehicle=vehicle, load_t=load_t, **kw)
    check(p, n_value)
    quantity(p)
    return p


SEC_CODE = {k: i for i, k in enumerate(H_SECTIONS, 1)}
CODE_SEC = {i: k for k, i in SEC_CODE.items()}
MAX_GX, MAX_GY, MAX_LV = 16, 8, 8          # 部品の支柱の列・行・水平つなぎの段の上限（ホットスポットで動かすパラメータの数）


def part_params(p: Plan) -> dict:
    """部品 ashiba_kodai のパラメータ（m）。覆工板の 3m の列・格子の決めを広さより先に（パラメータスクリプトが広さを切り上げる）."""
    return {"dk3": p.n3_req, "dk3At": next((i for i, r in enumerate(p.rows, 1) if r > 2500.0), 1), "spMax": p.sp_max / 1000.0, "ovh": p.ov / 1000.0, "lenX": p.length / 1000.0,
            "lenY": p.width / 1000.0, "zTop": p.top / 1000.0,
            "dig": p.depth / 1000.0, "emb": p.embed / 1000.0, "secJ": SEC_CODE[p.joist], "secG": SEC_CODE[p.girder],
            "secP": SEC_CODE[p.post], "tieP": TIE_PITCH_MM / 1000.0, "slopeN": p.slope if p.slope_len else 0.0,
            "railS": "S" in p.rails, "railN": "N" in p.rails, "railE": "E" in p.rails, "railW": "W" in p.rails,
            "gAuto": True, "lAuto": True, "kdVeh": p.vehicle, "kdLoad": p.load_t, "kdN": p.n_value,
            "kdName": p.name, "maxLd": f"最大積載荷重 {p.max_load_t:g}t"}


def plan_from_params(ps: dict, name: str = "") -> Plan:
    """置いた部品のパラメータ（ホットスポットで動かした支柱の列・行と水平つなぎの段、選んだ H鋼）→ 検定し直した Plan
    （パレットの「構台の検定」）。広さ・位置は m、Tapir の値のまま."""
    m = lambda k, d=0.0: float(ps.get(k) if ps.get(k) is not None else d) * 1000.0  # noqa: E731
    n3 = int(ps.get("dk3") if ps.get("dk3") is not None else -1)
    rows = deck_rows(m("lenY", 8.0), n3, int(ps.get("dk3At") or 1))
    L, W = snap(m("lenX", 18.0), 1000.0), sum(rows)
    n_x, n_y, n_l = int(ps.get("nGX") or 0), int(ps.get("nGY") or 0), int(ps.get("nLvP") or 0)
    xs = sorted(min(max(m(f"gX{i}"), 0.0), L) for i in range(1, min(n_x, MAX_GX) + 1))
    ys = sorted(min(max(m(f"gY{j}"), 0.0), W) for j in range(1, min(n_y, MAX_GY) + 1))
    rails = "".join(k for k in "SNEW" if ps.get(f"rail{k}"))
    p = Plan(name or str(ps.get("kdName") or "構台"), L, W, rows, xs, ys,
             [sum(rows[:i]) for i in range(len(rows) + 1)], [], m("zTop", 0.5), m("dig", 6.0),
             m("emb", 4.7), joist=CODE_SEC.get(int(ps.get("secJ") or 5), "H-400"),
             girder=CODE_SEC.get(int(ps.get("secG") or 5), "H-400"), post=CODE_SEC.get(int(ps.get("secP") or 4), "H-350"),
             vehicle=str(ps.get("kdVeh") or "R25") if str(ps.get("kdVeh") or "R25") in VEHICLES else "R25",
             load_t=float(ps.get("kdLoad") or 3.0), slope=float(ps.get("slopeN") or 0.0), rails=rails,
             sp_max=m("spMax", 6.0), ov=m("ovh", 1.0), n_value=float(ps.get("kdN") or 20.0), n3_req=n3)
    p.levels = sorted(m(f"lvD{k}") for k in range(1, min(n_l, MAX_LV) + 1)) or tie_levels(p.post_top, p.top + p.depth)
    if len(p.xs) < 2 or len(p.ys) < 2:                     # 古い部品（位置のパラメータが無い）は等分で
        p.xs, p.ys = grid(L, p.ov, p.sp_max), grid(W, p.ov, p.sp_max)
    check(p, p.n_value)
    quantity(p)
    return p


def report(plans: list[Plan]) -> str:
    out = ["# 乗入れ構台・荷取り構台", "",
           "出典: 日本建築学会 乗入れ構台設計・施工指針（2014）付1 の設計例（FORUM8 の計算書）・AIJ 講習会資料（鹿島）・ヒロセ "
           "鋼製山留総合カタログ・日本製鉄 メトロデッキ・労働安全衛生規則 575条の2〜8。検定は単純梁・軸力は重機の全重量で"
           "安全側の目安。本設計は構台の設計者の計算で確かめる", ""]
    for p in plans:
        out += [f"## {p.name}（{p.kind}）", "",
                f"- 広さ {p.length / 1000:g}×{p.width / 1000:g}m（覆工板の列 {'＋'.join(f'{r / 1000:g}' for r in p.rows)}m）・床の上端 GL+{p.top:.0f}・根切り底 GL−"
                f"{p.depth:.0f}・根入れ {p.embed:.0f}",
                f"- 支柱 {len(p.xs)}×{len(p.ys)}＝{len(p.xs) * len(p.ys)}本（X {', '.join(f'{x / 1000:.2f}' for x in p.xs)}・Y "
                f"{', '.join(f'{y / 1000:.2f}' for y in p.ys)}m）・長さ {p.post_len / 1000:.2f}m、根太 {len(p.joists)}通り、水平つなぎ "
                f"{len(p.levels)}段（床から {', '.join(f'{z / 1000:.2f}' for z in p.levels)}m 下）",
                f"- 重機: {VEHICLES[p.vehicle][0]}・吊荷 {p.load_t:g}t", "", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        out += [f"| {x.item} | {x.status} | {x.message} |" for x in p.checks]
        out += ["", "| 品名 | 数 | 注 |", "|---|---|---|"] + [f"| {a} | {b:g} | {c} |" for a, b, c in p.quantity] + [""]
    return "\n".join(out)
