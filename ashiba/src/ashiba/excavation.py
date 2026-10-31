"""根切りの山留めまわりの足場と手すり（利用者の指定 2026-10-31: https://www.seinankizai.jp/product/b_b/136/ 切張り上の足場を
追加して 山留め上の手すり リサーチして追加して）. 部品 ashiba_yamadome.

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
# 山留め上の手すり
RAIL_POST_PITCH_MM = 1800.0            # 手すり柱の間隔
RAIL_POST_DOWN_MM = 350.0              # 手すり柱を親杭のフランジに留める深さ（クランプ2個）

SOURCES = {"bracket": "西南機材 切梁ブラケット https://www.seinankizai.jp/product/b_b/136/",
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

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)


def stations(length: float, pitch: float, end: float) -> list[float]:
    """端から end の所から、pitch 以下で等分した位置（両端を含む）."""
    span = max(0.0, length - 2 * end)
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
                  toe_h: float = TOE_H_MM) -> Plan:
    """切梁上の足場（切梁ブラケット＋嵩上金具＋伸縮手摺柱）の割付と数量・検定."""
    xs = stations(length, min(pitch, BRACKET_PITCH_MAX_MM), END_MM)
    n = len(xs)
    p = Plan("切梁上の足場", name, length, xs)
    deck_l = length - 2 * END_MM + 200.0
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
    c.append(Check("切梁の荷重", "WARN", "切梁は山留め支保工の部材。通路の自重（ブラケット 5.8kg・嵩上金具 2.5kg・手摺柱 3.5kg×2 ごと＋床・"
                   "手すり）と積載を山留めの設計者に伝えて確かめる。切梁に溶接・穴あけはしない"))
    return p


def rail_plan(name: str, length: float, pitch: float = RAIL_POST_PITCH_MM, rail_h: float = RAIL_H_MM,
              mid_h: float = MID_H_MM, toe_h: float = TOE_H_MM, depth_mm: float = 0.0) -> Plan:
    """山留め上の手すり（親杭の天端に単管の手すり柱をキャッチクランプで）の割付と数量・検定."""
    xs = stations(length, pitch, 0.0)
    n = len(xs)
    p = Plan("山留め上の手すり", name, length, xs)
    q = p.quantity
    q.append((f"単管 {math.ceil((RAIL_POST_DOWN_MM + rail_h + 50.0) / 500.0) * 0.5:.1f}m（手すり柱）", n,
              f"@{max((b - a for a, b in zip(xs, xs[1:])), default=0):.0f}・親杭の天端から {RAIL_POST_DOWN_MM:.0f} 下まで"))
    q.append(("キャッチクランプ（H形鋼用）", 2 * n, "手すり柱1本に2個1組で親杭のフランジに"))
    for L in _tubes(length):
        q.append((f"単管 {L / 1000:.1f}m（手すり・中桟）", 2, "手すりと中桟"))
    q.append(("直交クランプ（手すり・中桟）", 2 * n, "手すり柱と単管"))
    q.append((f"幅木 H{toe_h:.0f}（4m）", math.ceil(length / 4000.0), "根切りの側"))
    c = p.checks
    pm = max((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    c.append(Check("手すり柱の間隔", "OK" if pm <= RAIL_POST_PITCH_MM + 1.0 else "WARN", f"最大 {pm:.0f}mm（1.8m 以内）"))
    c.append(Check("手すり・中桟", "OK" if rail_h >= 850.0 and 350.0 <= mid_h <= 500.0 else "NG",
                   f"手すり {rail_h:.0f}mm（85cm 以上）・中桟 {mid_h:.0f}mm（35〜50cm）"))
    c.append(Check("幅木", "OK" if toe_h >= 100.0 else "WARN", f"高さ {toe_h:.0f}mm（根切りの中への物の落下を防ぐ）"))
    if depth_mm >= 2000.0:
        c.append(Check("根切りの縁", "OK", f"根切りの深さ {depth_mm:.0f}mm（2m 以上の開口部の端なので囲い・手すりが要る。安衛則 519条）"))
    elif depth_mm > 0:
        c.append(Check("根切りの縁", "OK", f"根切りの深さ {depth_mm:.0f}mm（2m 未満でも転落・物の落下を防ぐため設ける）"))
    c.append(Check("手すり柱の取付け", "WARN", "キャッチクランプは2個1組で親杭のフランジに。親杭の天端が地盤より低い・高いときは柱の長さを"
                   "合わせる。人の通る所・公道に面する所は仮囲い・柵（公衆災害防止対策要綱）も見る"))
    return p


def part_params(p: Plan, flange_mm: float = 300.0) -> dict:
    """部品 ashiba_yamadome のパラメータ（m）."""
    kiri = p.kind == "切梁上の足場"
    return {"ymKind": 1 if kiri else 2, "ymL": p.length / 1000.0, "flgW": flange_mm / 1000.0,
            "brX": ",".join(f"{x:.0f}" for x in p.xs), "postSp": POST_SPACING_MM / 1000.0, "deckZ": DECK_Z_MM / 1000.0,
            "deckW": DECK_W_MM / 1000.0, "railH": RAIL_H_MM / 1000.0, "midH": MID_H_MM / 1000.0, "toeH": TOE_H_MM / 1000.0,
            "postDn": RAIL_POST_DOWN_MM / 1000.0, "ymName": f"{p.kind} {p.name}"}


def report(plans: list[Plan]) -> str:
    """数量と検定の帳票（Markdown）."""
    out = ["# 根切りの山留めまわり（切梁上の足場・山留め上の手すり）", "", f"出典: {SOURCES['bracket']}・{SOURCES['law']}", ""]
    for p in plans:
        out += [f"## {p.kind} {p.name}（長さ {p.length:.0f}mm）", "", "| 品名 | 数 | 注 |", "|---|---|---|"]
        out += [f"| {a} | {b} | {c} |" for a, b, c in p.quantity]
        out += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        out += [f"| {c.item} | {c.status} | {c.message} |" for c in p.checks]
        out.append("")
    return "\n".join(out)
