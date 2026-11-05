"""根切りの山留めまわりの足場と手すり（利用者の指定 2026-10-31: https://www.seinankizai.jp/product/b_b/136/ 切張り上の足場を
追加して 山留め上の手すり リサーチして追加して／外周の切張の足場も作って 組み方はリサーチしてね）. 部品 ashiba_yamadome.

外周の腹起し上の足場: 西南機材「腹起ブラケット」（製品ページ・寸法図。土留め工事の腹起し横架材に通路や昇降階段を設置）
- 腹起し（H形鋼 250〜500・板厚 24 まで）に掛け、腕が山留めの面から根切りの側へ 900。腕の上に足場板を3枚並べて番線で留め、
  先のサヤ管 φ60.5 に単管の手すり柱を差して手すり・中桟、幅木は幅木クランプ。取付間隔 2m 以内、自重 5.0kg、単管は別手配
- 山留めの側は山留めの壁なので、手すり・幅木は根切りの側だけ。昇降は腹起ブラケットに昇降階段（ラクラクタラップ）を掛ける

切梁上の足場（切梁上の安全通路）: 西南機材「切梁ブラケット」（製品ページ・寸法図）
- 切梁（H形鋼。フランジ幅 250〜400）の上のフランジに切梁ブラケットを挟み（スライドで幅を合わせる）、取付間隔は 2m 以内
- ブラケットの両端の φ42.7 に嵩上金具（W900・φ48.6）を差し、床（足場板・鋼製布板）を受ける。伸縮手摺柱（H875〜1275）で手すり、
  幅木クランプで幅木。自重: ブラケット 5.8kg（SP-45 は板厚 45 まで 6.0kg）・嵩上金具 2.5kg・伸縮手摺柱 3.5kg
- 法令: 作業床の幅 40cm 以上・すき間 3cm 以下（安衛則 563条）、手すり 85cm 以上と中桟（35〜50cm）・幅木（563条・552条）
- 切梁は山留め支保工の部材なので、通路の荷重（自重＋積載）とブラケットの取付けを山留めの設計者に確かめる

山留め上の手すり（根切りの周囲の囲い）: 根切りの縁は高さ 2m 以上の開口部の端（安衛則 519条: 囲い・手すり・覆い）
- 親杭（H形鋼）の天端に単管の手すり柱をキャッチクランプで留める（H形鋼に留めるクランプは2個1組。杉孝・足場用クランプの解説）。
  柱の間隔 1.8m 以内、手すり 85cm 以上（既定 950）・中桟・幅木（物の落下）
- 公衆に接する所は建設工事公衆災害防止対策要綱の仮囲い・柵も見る（この部品は作業員の墜落防止の手すり）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 切梁ブラケット（西南機材）
FLANGE_MIN_MM, FLANGE_MAX_MM = 250.0, 400.0
BRACKET_PITCH_MAX_MM = 2000.0          # 取付間隔は 2m 以内（製品の注意）
BRACKET_PITCH_MM = 1800.0              # 既定の間隔（足場板 4m の継ぎを支点に載せやすい）
POST_SPACING_MM = 900.0                # 嵩上金具（W900）・手すり柱の芯々
DECK_Z_MM = 300.0                      # 床の上端（フランジの上から。嵩上金具）
DECK_W_MM = 500.0                      # 鋼製布板の幅（作業床 40cm 以上）
RAIL_H_MM = 950.0                      # 手すり（伸縮手摺柱 875〜1275 の中で 85cm 以上）
MID_H_MM = 450.0                       # 中桟（35〜50cm）
TOE_H_MM = 150.0                       # 幅木（10cm 以上）
END_MM = 150.0                         # 切梁の端（腹起し・火打ちの取付け）からブラケットまで
# 外周の腹起し上の足場（西南機材 腹起ブラケット。利用者の指定 2026-10-31: 外周の切張の足場も作って 組み方はリサーチしてね）
WALE_MIN_MM, WALE_MAX_MM = 250.0, 500.0   # 腹起しの H形鋼（板厚 24 まで）
WALE_ARM_MM = 900.0                       # 腹起ブラケットの腕（山留めの面から根切りの側へ）。先のサヤ管 φ60.5 に単管の手すり柱
WALE_BOARDS = 3                           # 足場板（240）を3枚並べて番線で留める
BOARD_W_MM = 240.0
STAIR_DEPTH_MM = 1500.0                   # これを超える深さは昇降設備（安衛則 526条）
# 山留め上の手すり
RAIL_POST_PITCH_MM = 1800.0            # 手すり柱の間隔
RAIL_POST_DOWN_MM = 350.0              # 手すり柱を親杭のフランジに留める深さ（クランプ2個）
NET_TIE_MM = 450.0                     # ネットを手すり・中桟・幅木に結束する間隔（目安）

SOURCES = {"bracket": "西南機材 切梁ブラケット https://www.seinankizai.jp/product/b_b/136/",
           "wale": "西南機材 腹起ブラケット https://www.seinankizai.jp/product/b_b/135/",
           "law": "労働安全衛生規則 519条（開口部の囲い・手すり）・552条（架設通路）・563条（作業床）"}


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Plan:
    kind: str                          # "切梁上の足場" | "山留め上の手すり"
    name: str
    length: float
    xs: list[float]                    # ブラケット・手すり柱の位置（始めから mm）
    quantity: list[tuple[str, int, str]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    rail: tuple = (0.0, -1.0)          # 手すり・幅木（切梁上は床も）の範囲（始めから mm。−1 は終わりまで）
    gaps: list = field(default_factory=list)   # 手すり・幅木を切る所 [(x0, x1)]（切梁上の足場の取り合い）
    net: bool = False                          # 山留め上の手すりにラッセルネット

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)


def stations(length: float, pitch: float, end: float, end2: float | None = None) -> list[float]:
    """始めから end、終わりから end2（省くと end）の間を、pitch 以下で等分した位置（両端を含む）."""
    e2 = end if end2 is None else end2
    span = max(0.0, length - end - e2)
    n = max(1, math.ceil(span / pitch - 1e-9))
    return [end + span * k / n for k in range(n + 1)]


def _tubes(length: float) -> list[int]:
    """手すりの単管の割付（6m までを継ぐ。0.5m 刻みで切り上げ）."""
    out, rest = [], length
    while rest > 1.0:
        piece = min(6000.0, rest + 100.0)
        out.append(int(math.ceil(piece / 500.0) * 500))
        rest -= 6000.0 - 100.0
    return out


def kiribari_plan(name: str, length: float, flange_mm: float, pitch: float = BRACKET_PITCH_MM,
                  deck_w: float = DECK_W_MM, rail_h: float = RAIL_H_MM, mid_h: float = MID_H_MM,
                  toe_h: float = TOE_H_MM, deck0: float = 0.0, deck1: float = 0.0, step_mm: float = 0.0) -> Plan:
    """切梁上の足場（切梁ブラケット＋嵩上金具＋伸縮手摺柱）の割付と数量・検定. deck0・deck1 は始め・終わりで床を止める所（外周の
    腹起し上の足場の縁まで。0 は切梁の端）、step_mm は外周の足場との床の段差."""
    a0, a1 = max(END_MM, deck0 + 100.0), max(END_MM, deck1 + 100.0)
    xs = stations(length, min(pitch, BRACKET_PITCH_MAX_MM), a0, a1)
    n = len(xs)
    p = Plan("切梁上の足場", name, length, xs)
    p.rail = (deck0, length - deck1)
    deck_l = length - deck0 - deck1
    q = p.quantity
    pm = max((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    q.append(("切梁ブラケット", n, f"フランジ {flange_mm:.0f} を挟む・@{pm:.0f}"))
    q.append(("嵩上金具 W900", n, "ブラケットの両端に差す（φ48.6）"))
    q.append(("伸縮手摺柱 H875〜1275", 2 * n, "両側"))
    boards = math.ceil(deck_l / 4000.0)
    q.append((f"鋼製布板 {deck_w:.0f}×4000（床）", boards, f"延べ {deck_l / 1000:.1f}m・継ぎはブラケットの上で"))
    for L in _tubes(length):
        q.append((f"単管 {L / 1000:.1f}m（手すり・中桟）", 4, "両側の手すりと中桟"))
    q.append(("直交クランプ（手すり・中桟）", 4 * n, "伸縮手摺柱と単管"))
    q.append((f"幅木 H{toe_h:.0f}（4m）", 2 * math.ceil(length / 4000.0), "幅木クランプで手すり柱に"))
    q.append(("幅木クランプ", 2 * n, ""))
    c = p.checks
    if FLANGE_MIN_MM <= flange_mm <= FLANGE_MAX_MM:
        c.append(Check("切梁のフランジ", "OK", f"幅 {flange_mm:.0f}（切梁ブラケットは 250〜400。板厚 24 まで、45 までは SP-45）"))
    else:
        c.append(Check("切梁のフランジ", "NG", f"幅 {flange_mm:.0f} は切梁ブラケットの対応（250〜400）の外。単管とキャッチクランプ"
                       "（2個1組）で受けるか、メーカーに確かめる"))
    c.append(Check("ブラケットの間隔", "OK" if pm <= BRACKET_PITCH_MAX_MM else "NG",
                   f"最大 {pm:.0f}mm（2m 以内。製品の取付間隔）"))
    c.append(Check("作業床", "OK" if deck_w >= 400.0 else "NG",
                   f"幅 {deck_w:.0f}mm（40cm 以上）・床のすき間 3cm 以下（安衛則 563条）"))
    c.append(Check("手すり・中桟", "OK" if rail_h >= 850.0 and 350.0 <= mid_h <= 500.0 else "NG",
                   f"手すり {rail_h:.0f}mm（85cm 以上）・中桟 {mid_h:.0f}mm（35〜50cm）（安衛則 552条・563条。伸縮手摺柱 875〜1275）"))
    c.append(Check("幅木", "OK" if toe_h >= 100.0 else "WARN", f"高さ {toe_h:.0f}mm（物の落下を防ぐ 10cm 以上。下は根切りの作業場所）"))
    if deck0 > 0 or deck1 > 0:
        c.append(Check("外周の足場との取り合い", "OK" if step_mm <= 100.0 else "WARN",
                       f"床は外周の腹起し上の足場の縁で止め、そこから外周の足場へ渡る（外周の手すりはこの幅だけ切る）。床の段差 {step_mm:.0f}mm"
                       + ("" if step_mm <= 100.0 else "（つまずき・踏み外しのおそれ。踏台を置くか、嵩上金具を低いものにして床をそろえる）")))
    c.append(Check("切梁の荷重", "WARN", "切梁は山留め支保工の部材。通路の自重（ブラケット 5.8kg・嵩上金具 2.5kg・手摺柱 3.5kg×2 ごと＋床・"
                   "手すり）と積載を山留めの設計者に伝えて確かめる。切梁に溶接・穴あけはしない"))
    return p


def haraokoshi_plan(name: str, length: float, wale_mm: float = 300.0, pitch: float = BRACKET_PITCH_MM,
                    rail_h: float = RAIL_H_MM, mid_h: float = MID_H_MM, toe_h: float = TOE_H_MM, depth_mm: float = 0.0) -> Plan:
    """外周の腹起し上の足場（腹起ブラケット＋足場板3枚＋単管の手すり柱）の割付と数量・検定. 山留めの側は山留めの壁なので、
    手すり・幅木は根切りの側だけ."""
    xs = stations(length, min(pitch, BRACKET_PITCH_MAX_MM), END_MM)
    n = len(xs)
    p = Plan("腹起し上の足場", name, length, xs)
    q = p.quantity
    pm = max((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    q.append(("腹起ブラケット", n, f"腹起し {wale_mm:.0f} に掛ける・@{pm:.0f}"))
    rows = math.ceil((length - 2 * END_MM + 200.0) / 4000.0)
    q.append(("足場板 240×4000", WALE_BOARDS * rows, f"{WALE_BOARDS}枚並べ・番線で留める（継ぎはブラケットの上で重ねる）"))
    q.append(("番線（足場板）", 2 * WALE_BOARDS * n, "ブラケットごとに板の両端"))
    q.append((f"単管 {math.ceil((rail_h + 300.0) / 500.0) * 0.5:.1f}m（手すり柱）", n, "ブラケットの先のサヤ管 φ60.5 に差す"))
    for L in _tubes(length):
        q.append((f"単管 {L / 1000:.1f}m（手すり・中桟）", 2, "根切りの側"))
    q.append(("直交クランプ（手すり・中桟）", 2 * n, "手すり柱と単管"))
    q.append((f"幅木 H{toe_h:.0f}（4m）", math.ceil(length / 4000.0), "根切りの側・幅木クランプで手すり柱に"))
    q.append(("幅木クランプ", n, ""))
    c = p.checks
    if WALE_MIN_MM <= wale_mm <= WALE_MAX_MM:
        c.append(Check("腹起し", "OK", f"H形鋼 {wale_mm:.0f}（腹起ブラケットは 250〜500・板厚 24 まで）"))
    else:
        c.append(Check("腹起し", "NG", f"H形鋼 {wale_mm:.0f} は腹起ブラケットの対応（250〜500）の外。メーカーに確かめる"))
    c.append(Check("ブラケットの間隔", "OK" if pm <= BRACKET_PITCH_MAX_MM else "NG", f"最大 {pm:.0f}mm（2m 以内。製品の取付間隔）"))
    c.append(Check("ブラケットの数", "OK" if n >= 2 else "NG", f"{n}基（腹起し材1本に2基以上。脱落を防ぐ腹起しブラケットとは別）"))
    deck = WALE_BOARDS * BOARD_W_MM
    c.append(Check("作業床", "OK" if deck >= 400.0 else "NG",
                   f"足場板 {WALE_BOARDS}枚で幅 {deck:.0f}mm（40cm 以上）・すき間 3cm 以下・番線で留める（安衛則 563条）"))
    c.append(Check("手すり・中桟", "OK" if rail_h >= 850.0 and 350.0 <= mid_h <= 500.0 else "NG",
                   f"根切りの側に手すり {rail_h:.0f}mm（85cm 以上）・中桟 {mid_h:.0f}mm（安衛則 563条）。山留めの側は山留めの壁"))
    c.append(Check("幅木", "OK" if toe_h >= 100.0 else "WARN", f"高さ {toe_h:.0f}mm（幅木クランプ。根切りの中への物の落下を防ぐ）"))
    if depth_mm > STAIR_DEPTH_MM:
        c.append(Check("昇降設備", "WARN", f"根切りの深さ {depth_mm:.0f}mm（1.5m を超えるので昇降設備。安衛則 526条）。腹起ブラケットに"
                       "昇降階段（ラクラクタラップ等）を掛けるか、根切りの中の階段から上がる"))
    c.append(Check("腹起しの荷重", "WARN", "腹起しは山留め支保工の部材。通路の自重（ブラケット 5.0kg ごと＋足場板・手すり）と積載を山留めの"
                   "設計者に伝えて確かめる。火打ちの所は通路を切らずに渡すか、手すりで囲う"))
    return p


def rail_plan(name: str, length: float, pitch: float = RAIL_POST_PITCH_MM, rail_h: float = RAIL_H_MM,
              mid_h: float = MID_H_MM, toe_h: float = TOE_H_MM, depth_mm: float = 0.0, net: bool = True) -> Plan:
    """山留め上の手すり（親杭の天端に単管の手すり柱をキャッチクランプで）の割付と数量・検定.

    net: 根切りの側にラッセルネット（無結節・目合 15）を地盤から手すりの上まで張る（利用者の指定 2026-10-31:
    山留め上の手すりはネットいるよ）。手すり・中桟・幅木に結束する."""
    xs = stations(length, pitch, 0.0)
    n = len(xs)
    p = Plan("山留め上の手すり", name, length, xs, net=net)
    q = p.quantity
    q.append((f"単管 {math.ceil((RAIL_POST_DOWN_MM + rail_h + 50.0) / 500.0) * 0.5:.1f}m（手すり柱）", n,
              f"@{max((b - a for a, b in zip(xs, xs[1:])), default=0):.0f}・親杭の天端から {RAIL_POST_DOWN_MM:.0f} 下まで"))
    q.append(("キャッチクランプ（H形鋼用）", 2 * n, "手すり柱1本に2個1組で親杭のフランジに"))
    for L in _tubes(length):
        q.append((f"単管 {L / 1000:.1f}m（手すり・中桟）", 2, "手すりと中桟"))
    q.append(("直交クランプ（手すり・中桟）", 2 * n, "手すり柱と単管"))
    q.append((f"幅木 H{toe_h:.0f}（4m）", math.ceil(length / 4000.0), "根切りの側"))
    if net:
        q.append((f"ラッセルネット 目合15（高さ {rail_h / 1000:.2f}m）", math.ceil(length / 1000.0 * rail_h / 1000.0),
                  f"m²・延べ {length / 1000:.1f}m・地盤から手すりの上まで根切りの側に"))
        q.append(("結束バンド（ネット）", 3 * (math.ceil(length / NET_TIE_MM) + 1),
                  f"手すり・中桟・幅木に @{NET_TIE_MM:.0f} 目安"))
    c = p.checks
    pm = max((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    c.append(Check("手すり柱の間隔", "OK" if pm <= RAIL_POST_PITCH_MM + 1.0 else "WARN", f"最大 {pm:.0f}mm（1.8m 以内）"))
    c.append(Check("手すり・中桟", "OK" if rail_h >= 850.0 and 350.0 <= mid_h <= 500.0 else "NG",
                   f"手すり {rail_h:.0f}mm（85cm 以上）・中桟 {mid_h:.0f}mm（35〜50cm）"))
    c.append(Check("幅木", "OK" if toe_h >= 100.0 else "WARN", f"高さ {toe_h:.0f}mm（根切りの中への物の落下を防ぐ）"))
    c.append(Check("ネット", "OK" if net else "WARN",
                   "ラッセルネット（目合 15）を手すり・中桟・幅木に結束（手すりのすき間からの転落と、根切りの中への物・土砂の落下を防ぐ）"
                   if net else "ネットなし。手すりのすき間から物・土砂が根切りの中に落ちる。ラッセルネットを張る"))
    if depth_mm >= 2000.0:
        c.append(Check("根切りの縁", "OK", f"根切りの深さ {depth_mm:.0f}mm（2m 以上の開口部の端なので囲い・手すりが要る。安衛則 519条）"))
    elif depth_mm > 0:
        c.append(Check("根切りの縁", "OK", f"根切りの深さ {depth_mm:.0f}mm（2m 未満でも転落・物の落下を防ぐため設ける）"))
    c.append(Check("手すり柱の取付け", "WARN", "キャッチクランプは2個1組で親杭のフランジに。親杭の天端が地盤より低い・高いときは柱の長さを"
                   "合わせる。人の通る所・公道に面する所は仮囲い・柵（公衆災害防止対策要綱）も見る"))
    return p


def _seg_dist(p, a, b) -> float:
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay or 1.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - a[0] - ax * t, p[1] - a[1] - ay * t)


CORNER_TOL_MM = 1000.0                 # 山留めの線の端どうしがこれより近ければ角でつながる
NEAR_MM = 1500.0                       # 切梁の端がこれより山留めの線に近ければ取り合う


def perimeter_layout(lines: list, thicks: list[float], strut_ends=(), arm: float = WALE_ARM_MM) -> list[dict]:
    """外周の腹起し上の足場の各辺の床・手すりの範囲（利用者の指定 2026-10-31: 角の重なりと切梁との取り合いも直して）.

    lines は山留めの芯の線 [(始め, 終わり)]（根切りの中が右）、thicks は山留めの厚さ。各辺の床は、前の辺がつながっていれば前の辺の
    床（山留めの面から arm）の縁から、次の辺がつながっていれば次の辺の山留めの面まで（角の升目はこの辺が受け持つ）。手すり・幅木は
    角では内側の角（次の辺の床の縁）で止めて次の辺の手すりへ折れる。切梁上の足場の端（strut_ends）が辺に取り合う所は、
    切梁上の足場の幅（手すり柱の間 900＋100）だけ手すり・幅木を切る.
    戻り値は辺ごとに {"origin"（床の始めの山留めの面の点）, "ang", "length"（床の長さ）, "rail": (x0, x1), "gaps": [(x0, x1)]}."""
    out = []
    for i, (p0, p1) in enumerate(lines):
        L = math.dist(p0, p1)
        u = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
        rgt = (u[1], -u[0])
        prev = next((j for j, (a, b) in enumerate(lines) if j != i and min(math.dist(a, p0), math.dist(b, p0)) < CORNER_TOL_MM), None)
        nxt = next((j for j, (a, b) in enumerate(lines) if j != i and min(math.dist(a, p1), math.dist(b, p1)) < CORNER_TOL_MM), None)
        x0 = thicks[prev] / 2.0 + arm if prev is not None else 0.0
        x1 = L - thicks[nxt] / 2.0 if nxt is not None else L
        r1 = x1 - arm if nxt is not None else x1
        t = thicks[i] / 2.0
        origin = (p0[0] + u[0] * x0 + rgt[0] * t, p0[1] + u[1] * x0 + rgt[1] * t)
        gaps = []
        half = POST_SPACING_MM / 2.0 + 50.0
        for e in strut_ends:
            if _seg_dist(e, p0, p1) < NEAR_MM:
                sx = (e[0] - p0[0]) * u[0] + (e[1] - p0[1]) * u[1] - x0
                gaps.append((sx - half, sx + half))
        out.append({"origin": origin, "ang": math.degrees(math.atan2(u[1], u[0])), "length": x1 - x0,
                    "rail": (0.0, r1 - x0), "gaps": sorted(gaps)})
    return out


def strut_insets(ca, cb, lines: list, thicks: list[float], arm: float = WALE_ARM_MM) -> tuple[float, float]:
    """切梁の始め・終わりから、外周の腹起し上の足場の縁までの長さ（その辺に外周の足場が無ければ 0）."""
    out = []
    for e in (ca, cb):
        best = 0.0
        for (p0, p1), t in zip(lines, thicks):
            d = _seg_dist(e, p0, p1)
            if d < NEAR_MM:
                best = max(best, arm - (d - t / 2.0))
        out.append(max(0.0, best))
    return out[0], out[1]


def part_params(p: Plan, flange_mm: float = 300.0) -> dict:
    """部品 ashiba_yamadome のパラメータ（m）."""
    kind = {"切梁上の足場": 1, "山留め上の手すり": 2, "腹起し上の足場": 3}[p.kind]
    return {"ymKind": kind, "ymL": p.length / 1000.0, "flgW": flange_mm / 1000.0,
            "brX": ",".join(f"{x:.0f}" for x in p.xs), "postSp": POST_SPACING_MM / 1000.0, "deckZ": DECK_Z_MM / 1000.0,
            "deckW": DECK_W_MM / 1000.0, "railH": RAIL_H_MM / 1000.0, "midH": MID_H_MM / 1000.0, "toeH": TOE_H_MM / 1000.0,
            "postDn": RAIL_POST_DOWN_MM / 1000.0, "ymName": f"{p.kind} {p.name}",
            "railX0": p.rail[0] / 1000.0, "railX1": (p.rail[1] if p.rail[1] >= 0 else p.length) / 1000.0,
            "railGap": ",".join(f"{a:.0f},{b:.0f}" for a, b in p.gaps), "netOn": bool(p.net)}


def report(plans: list[Plan]) -> str:
    """数量と検定の帳票（Markdown）."""
    out = ["# 根切りの山留めまわり（切梁上の足場・外周の腹起し上の足場・山留め上の手すり）", "",
           f"出典: {SOURCES['bracket']}・{SOURCES['wale']}・{SOURCES['law']}", ""]
    for p in plans:
        out += [f"## {p.kind} {p.name}（長さ {p.length:.0f}mm）", "", "| 品名 | 数 | 注 |", "|---|---|---|"]
        out += [f"| {a} | {b} | {c} |" for a, b, c in p.quantity]
        out += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        out += [f"| {c.item} | {c.status} | {c.message} |" for c in p.checks]
        out.append("")
    return "\n".join(out)
