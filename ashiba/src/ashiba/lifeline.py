"""親綱と親綱支柱（鉄骨梁の上の水平親綱）（利用者の指定 2026-11-01: 親綱と親綱支柱も追加して。部品 ashiba_lifeline）.

鉄骨梁（か梁に沿って引いた線）ごとに、梁の上フランジに親綱支柱を立て、スパンごとに親綱を張る。規格品で発注できる詳細さで
（利用者の指定 2026-11-01: イメージじゃなく実際の規定の長さで発注できるくらい詳細に）。

出典（調べた資料）:
- 日建リース工業 仮設資材カタログ Vol.10 p196: 親綱支柱（H鋼取付用）NTP 9.50kg・高さ 1,045、アルミ製親綱支柱 ALPA12 7.75kg・高さ
  1,081・つかみ厚 最大 50mm、親綱緊張用自在滑車 NSPJK 0.70kg、横移動用安全滑車 NSPAK 0.53kg、親綱 NSPR20（20m・販売品）2.00kg
- 手すり先行工法等に関するガイドライン（令和5年改正）別表6: 支柱のスパンは 10m 以下、かつ L＝40(H−4)/11 [m] 以下（H は支柱を置いた
  作業床から下の床面・機械設備までの垂直距離）、1スパン1人、コーナーの支柱に平行・直交の2本の親綱を同時に付けない、緊張器で
  たるまない程度に張る、設置直後・盛替え直後・作業開始前に点検。別表5: 第1種の支柱はフランジ（厚さ 16mm の鋼板で試験）用
- 墜落制止用器具の安全な使用に関するガイドライン（平成30年 基発0622第2号）: 6.75m を超える所はフルハーネス型（一般的な建設作業は
  5m を超える所）、水平親綱は D環（1.45m）より高く張る。低くしか張れないときはフルハーネス＋第二種ショックアブソーバ・短いランヤード
- H の区分（reports/デッキプレートの敷設時期.md の提案）: 6.75m 以上は式のとおり、それ未満は注意、スパン 3m 未満は実用外（3m は目安で出典の値でない）、
  4m 以下は別表6 の適用外。通達の値なので「法令違反」とは読まない。矢作の 3(H−3) は 10m 以内で別表6 より常に緩く効かないので外した
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .opening_guard import order_table

POSTS = {"NTP": ("親綱支柱（H鋼取付用）NTP", 9.50, 1045.0, 0.0), "ALPA12": ("アルミ製親綱支柱 ALPA12", 7.75, 1081.0, 50.0)}
ROPE = ("NSPR20 親綱（20m・販売品）", 20000.0, 2.00)
TENSIONER = ("NSPJK 親綱緊張用自在滑車", 0.70)
SPAN_MAX = 10000.0                     # 別表6 の上限
END_MM = 300.0                         # 梁の端（柱）から支柱まで。角の支柱を2方向で共有しない
ROPE_EXTRA = 2000.0                    # 結び・緊張器の余長（目安）
D_RING = 1450.0                        # D環の高さ
HARNESS_MUST, HARNESS_BUILD = 6750.0, 5000.0
MIN_SPAN = 3000.0                      # これより短いスパンは実用外【目安】（H＝4.825m に当たる）


def span_limit(drop: float) -> float:
    """落差 drop mm で張れる支柱の間隔の上限 mm: 別表6 の 40(H−4)/11 と 10m の小さい方（0 以下は張れない）."""
    h = drop / 1000.0
    return max(0.0, min(SPAN_MAX, 40.0 * (h - 4.0) / 11.0 * 1000.0))


def judge_drop(drop: float) -> tuple:
    """H の区分の判定 (状態, 内容). 状態は OK・注意・警告・適用外. 通達の値なので法令違反の判定ではない."""
    h = drop / 1000.0
    lim = span_limit(drop)
    if lim <= 0.0:
        return "適用外", f"H {h:.2f}m は別表6 の式の外（4m 以下）→ 手すり・巻取り式・安全ブロックのどれで守るかを計画に書く"
    if lim < MIN_SPAN:
        return "警告", f"H {h:.2f}m はスパン {lim / 1000:.2f}m で実用外（3m は目安）→ 作業床と手すりへ。親綱は補助"
    if drop < HARNESS_MUST:
        return "注意", f"H {h:.2f}m はスパン {lim / 1000:.2f}m まで。短いランヤードか巻取り式で、製品の落下距離＋たわみと H を比べる"
    return "OK", f"H {h:.2f}m は別表6 の式でスパン {lim / 1000:.2f}m まで"


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Run:
    name: str
    a: tuple[float, float]
    b: tuple[float, float]
    top: float                         # 梁の上端（支柱を置く面）mm
    drop: float                        # 下の面までの落差 mm（段階があるときは下限）
    post: str = "NTP"
    flange_t: float = 0.0              # 上フランジの厚さ mm（分かれば。ALPA12 は 50 まで）
    spans: list[float] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)
    drop_max: float = 0.0              # 落差の上限 mm（器具の判定。0 は drop と同じ）
    note: str = ""                     # 落差の出どころの注意

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)


def plan_run(r: Run) -> Run:
    L = max(r.length - 2.0 * END_MM, 0.0)
    lim = span_limit(r.drop)
    c = r.checks = []
    state, text = judge_drop(r.drop)
    if lim < MIN_SPAN or L <= 0.0:
        r.spans = []
        c.append(Check("スパン", state, text))
    else:
        n = max(1, math.ceil(L / lim - 1e-6))
        r.spans = [L / n] * n
        c.append(Check("スパン", state, f"{n}スパン×{L / n / 1000:.2f}m ≦ {lim / 1000:.2f}m（別表6 の 40(H−4)/11 と 10m の小さい方）。"
                                       f"{text}。1スパン1人・スパンごとに親綱を分ける"))
    if r.note:
        c.append(Check("落差", "注意", r.note))
    name, _kg, ph, grip = POSTS[r.post]
    high = max(r.drop, r.drop_max)
    if high > HARNESS_MUST:
        c.append(Check("墜落制止用器具", "OK", f"落差 {high / 1000:.1f}m（6.75m 超）はフルハーネス型（墜落制止用器具ガイドライン）"))
    else:
        c.append(Check("墜落制止用器具", "OK", f"落差 {high / 1000:.1f}m: " + ("一般的な建設作業は 5m 超でフルハーネス型" if high > HARNESS_BUILD
                                                                              else "6.75m 以下（胴ベルト型も可。フルハーネス推奨）")))
    if ph < D_RING:
        c.append(Check("親綱の高さ", "WARN", f"{name} は梁の上から約 {ph:.0f}mm で D環（1.45m）より低い → フルハーネス＋第二種ショック"
                                          "アブソーバか、腰の高さ以上なら第一種も可。短いランヤードか巻取り式を検討し、製品の最大自由落下距離を確かめる（ランヤード 1.7m 以内）"))
    if grip and r.flange_t and r.flange_t > grip:
        c.append(Check("つかみ厚", "NG", f"上フランジ {r.flange_t:.0f}mm は {name} のつかみ厚 {grip:.0f}mm を超える → NTP に"))
    c.append(Check("点検", "OK", "設置直後・盛替え直後・作業開始前に支柱の取付部・親綱の張り（緊張器でたるまない程度）を点検（別表6）。"
                                "支柱に直接フックを掛けない・コーナーの支柱に2方向の親綱を付けない"))
    _quantity(r)
    return r


def _quantity(r: Run) -> None:
    q = r.quantity = []
    if not r.spans:
        return
    name, kg, _h, _g = POSTS[r.post]
    q.append((name, len(r.spans) + 1, f"本（{kg:g}kg）"))
    ropes = sum(1 if s + ROPE_EXTRA <= ROPE[1] else math.ceil((s + ROPE_EXTRA) / ROPE[1]) for s in r.spans)
    q.append((ROPE[0], ropes, f"本（{ROPE[2]:g}kg。スパンごとに1本）"))
    q.append((TENSIONER[0], ropes, f"個（{TENSIONER[1]:g}kg。親綱1本に1個）"))
    q.append(("表示「1スパン1人」", len(r.spans), "枚"))


def part_params(r: Run) -> dict:
    return {"llL": r.length / 1000.0, "nSpan": len(r.spans), "llEnd": END_MM / 1000.0, "postK": 2 if r.post == "ALPA12" else 1,
            "llName": r.name, "llDrop": f"落差 {r.drop / 1000:.1f}m"}


def report(runs: list[Run]) -> str:
    out = ["# 親綱・親綱支柱", "",
           "出典: 日建リース工業 仮設資材カタログ Vol.10 p196、手すり先行工法等に関するガイドライン 別表5・6（令和5年改正）、墜落制止用"
           "器具の安全な使用に関するガイドライン（平成30年）、H の区分は reports/デッキプレートの敷設時期.md の提案", "",
           "| 親綱 | 長さ | 判定 | 内容 |", "|---|---|---|---|"]
    tot: dict[str, list] = {}
    for r in runs:
        for x in r.checks:
            out.append(f"| {r.name} | {r.length / 1000:.1f}m | {x.status} | {x.item}: {x.message} |")
        for a, n, u in r.quantity:
            row = tot.setdefault(a, [0.0, u])
            row[0] += n
    out += order_table(tot, ("親綱支柱", "アルミ製親綱支柱", "NSPR20", "NSPJK", "表示")) + [""]
    return "\n".join(out)
