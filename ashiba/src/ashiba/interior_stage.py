"""内部足場（内部ステージ足場）: 室内の範囲に支柱を格子に立て、上の作業床を全面に張る足場. 部品 ashiba_stage.

利用者の指定（2026-10-24）「内部足場の内部ステージ足場の機能追加して検証して」。吹抜け・高天井の天井・壁上部の作業で、
室内に格子状に支柱を立てて最上段に全面の作業床（ステージ）を張る。
- 範囲: 平面の長方形（4点。向きは自由）。壁から CLEAR_MM 離して、両方向に系列のスパンで割る
- 高さ: 作業床の高さ（床から）を指定。支柱はコマの位置に合わせ、作業床の高さは最寄りの段（以下）にする
- 部材: 支柱（格子）・ジャッキ・根がらみと各段の布材（両方向）・最上段の全面の踏板・外周の手すり・中桟・幅木・
  外周の構面の筋かい（5スパン以下ごと）・昇降のはしご（1箇所）
- 検証: 支柱1本の軸力（自重＋作業床＋積載）と許容耐力、1スパンあたりの積載と作業床の許容積載、高さと短辺の比
  （4 を超えたら控え・壁つなぎ）、作業床の高さ 2m 以上の手すり・幅木・昇降設備

入力: interior_stages: [{"name": "吹抜け", "corners_mm": [[x,y],[x,y],[x,y],[x,y]], "deck_mm": 6000,
       "live_kn_m2": 1.5, "base_mm": 0}]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

CLEAR_MM = 150.0             # 壁から外周の支柱まで
LIVE_DEFAULT_KN_M2 = 1.5     # 作業床の積載（軽作業・仕上げ）
DECK_DEAD_KN_M2 = 0.25       # 踏板の自重
POST_SELF_KN_PER_M = 0.15    # 支柱＋布材・筋かいの自重（支柱1本・高さ1m あたりの目安）
HB_LIMIT = 4.0               # 高さ／短辺がこれを超えたら控え・壁つなぎ
BRACE_EVERY_SPANS = 5
FIT_SLACK_MM = 900.0         # 壁際の余り（片側 CLEAR_MM に足して両側でこれ以内）
GUARD_MM = 900               # 手すりの高さ（作業床から）


@dataclass
class StageCheck:
    item: str
    status: str              # OK / WARN / NG
    message: str


@dataclass
class StageResult:
    name: str
    origin: tuple[float, float]       # 外周の支柱の始めの角（mm）
    u: tuple[float, float]            # 長い方の辺の向き
    v: tuple[float, float]            # もう一方（u から左回り 90°）
    spans_u: list[int]
    spans_v: list[int]
    levels: list[int]                 # 根がらみ＋各段（足場の立つ面から mm）。最後が作業床
    deck_mm: int
    base_mm: float
    posts: list[int]                  # 支柱の構成（下から）
    jack_mm: int
    live_kn_m2: float
    quantity: list[tuple[str, int, int, str]] = field(default_factory=list)   # (分類, 呼び寸法, 数, 用途)
    checks: list[StageCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def length_u(self) -> float:
        return float(sum(self.spans_u))

    @property
    def length_v(self) -> float:
        return float(sum(self.spans_v))

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.u[1], self.u[0]))

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)


def _frame(corners) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], float, float]:
    """4点 → (始めの角, 長い辺の向き u, v（u から左回り）, 長い辺の長さ, 短い辺の長さ)."""
    pts = [tuple(map(float, p)) for p in corners][:4]
    if len(pts) < 4:
        raise ValueError("内部足場の範囲は長方形の4点で指定してください")
    area = sum(pts[i][0] * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4))
    if area < 0:
        pts.reverse()                                   # 左回りにそろえる
    sides = [(i, math.hypot(pts[(i + 1) % 4][0] - pts[i][0], pts[(i + 1) % 4][1] - pts[i][1])) for i in range(4)]
    i0, la = max(sides, key=lambda s: s[1])
    p0, p1 = pts[i0], pts[(i0 + 1) % 4]
    u = ((p1[0] - p0[0]) / la, (p1[1] - p0[1]) / la)
    v = (-u[1], u[0])
    lb = sides[(i0 + 1) % 4][1]
    return p0, u, v, la, lb


def _fit_spans(coins: list[int], length: float) -> list[int]:
    """長さ以下のスパン列: 壁際の余り FIT_SLACK_MM 以内でスパンの本数がいちばん少ない（長いスパン）もの、次に長いもの."""
    from .plan_solver import achievable_sums

    if length < min(coins):
        return []
    lo = max(min(coins), int(length - FIT_SLACK_MM))
    table = achievable_sums(coins, lo, int(length))
    if not table:
        table = achievable_sums(coins, min(coins), int(length))
    best = min(table, key=lambda s: (len(table[s]), -s))
    return sorted(table[best], reverse=True)


def solve_stage(item: dict, master, capacities: Optional[dict] = None) -> StageResult:
    """内部ステージ足場を解いて検証する."""
    from .elevation_solver import solve_elevation

    name = str(item.get("name") or "内部ステージ足場")
    p0, u, v, la, lb = _frame(item["corners_mm"])
    coins = master.span_lengths()
    su = _fit_spans(coins, la - 2 * CLEAR_MM)
    sv = _fit_spans(coins, lb - 2 * CLEAR_MM)
    if not su or not sv:
        raise ValueError(f"{name}: 範囲（{la:.0f}×{lb:.0f}）が狭くて支柱が立ちません")
    # 割り付けた格子を範囲の中央に寄せる
    off_u = (la - sum(su)) / 2.0
    off_v = (lb - sum(sv)) / 2.0
    origin = (p0[0] + u[0] * off_u + v[0] * off_v, p0[1] + u[1] * off_u + v[1] * off_v)
    deck_req = float(item.get("deck_mm", 0.0) or 0.0)
    if deck_req < 1000.0:
        raise ValueError(f"{name}: 作業床の高さ（deck_mm）を 1000 以上で指定してください")
    guard = 2 * int(master.koma_pitch) + int(getattr(master, "koma_top_gap", 0) or 0)
    elev = solve_elevation(int(round(deck_req)) + guard, master=master)
    levels = [int(elev.first_ledger_height)] + [int(h) for h in elev.level_heights if h <= deck_req + 1.0]
    if len(levels) < 2:
        levels = [int(elev.first_ledger_height)] + [int(h) for h in elev.level_heights[:1]]
    deck = levels[-1]
    live = float(item.get("live_kn_m2", LIVE_DEFAULT_KN_M2) or LIVE_DEFAULT_KN_M2)
    res = StageResult(name, origin, u, v, su, sv, levels, deck, float(item.get("base_mm", 0.0) or 0.0),
                      list(elev.posts), int(elev.jack_extension), live)
    _quantity(res, master)
    _checks(res, master, capacities)
    return res


def _quantity(r: StageResult, master) -> None:
    nu, nv = len(r.spans_u), len(r.spans_v)
    n_posts = (nu + 1) * (nv + 1)
    q = r.quantity
    for p in r.posts:
        q.append(("支柱", int(p), n_posts, "内部ステージの支柱"))
    q.append(("ジャッキ", 0, n_posts, "内部ステージのジャッキベース"))
    n_lv = len(r.levels)                       # 根がらみ＋各段
    for s in sorted(set(r.spans_u)):
        k = r.spans_u.count(s) * (nv + 1) * n_lv
        q.append(("布材", int(s), k, "内部ステージの布材（長手）"))
    for s in sorted(set(r.spans_v)):
        k = r.spans_v.count(s) * (nu + 1) * n_lv
        q.append(("布材", int(s), k, "内部ステージの布材（短手）"))
    # 最上段の全面の踏板: 長手のスパンに掛け、短手のスパンを踏板の幅で埋める
    widths = sorted({int(w) for w in getattr(master, "deck_widths", (500, 240)) or (500, 240)}, reverse=True)
    decks: dict[tuple[int, int], int] = {}
    for s_u in r.spans_u:
        for s_v in r.spans_v:
            rest = float(s_v) - 30.0
            for w in widths:
                k = int(rest // w)
                if k:
                    decks[(int(s_u), w)] = decks.get((int(s_u), w), 0) + k
                    rest -= k * w
    for (s_u, w), k in sorted(decks.items()):
        q.append(("踏板", s_u, k, f"内部ステージの全面の作業床（幅{w}）"))
    # 外周の手すり・中桟（2本）と幅木
    per = {}
    for s in r.spans_u:
        per[s] = per.get(s, 0) + 2
    for s in r.spans_v:
        per[s] = per.get(s, 0) + 2
    for s, k in sorted(per.items()):
        q.append(("布材", int(s), 2 * k, "内部ステージの外周の手すり・中桟"))
        q.append(("幅木", int(s), k, "内部ステージの外周の幅木"))
    # 外周の構面の筋かい（各辺 5スパン以下ごと・各段）
    n_br = 0
    for spans in (r.spans_u, r.spans_u, r.spans_v, r.spans_v):
        n_br += math.ceil(len(spans) / BRACE_EVERY_SPANS) * (n_lv - 1)
    q.append(("筋交", int(max(r.spans_u)), n_br * 2, "内部ステージの外周の筋かい（交さ2方向）"))
    q.append(("はしご", 0, 1, "内部ステージの昇降（はしご）"))


def _cap(caps: Optional[dict], item: str, key: str = "0") -> Optional[float]:
    if not caps:
        return None
    cv = caps.get((item, key))
    return float(cv.value) if cv is not None else None


def _checks(r: StageResult, master, caps: Optional[dict]) -> None:
    out = r.checks
    su, sv = max(r.spans_u) / 1000.0, max(r.spans_v) / 1000.0
    h_m = (r.deck_mm + GUARD_MM) / 1000.0
    # 1. 支柱の軸力（内側の支柱。受け持ち＝隣り合うスパンの半分ずつ）
    trib = su * sv
    n_kn = trib * (r.live_kn_m2 + DECK_DEAD_KN_M2) + POST_SELF_KN_PER_M * h_m
    allow = _cap(caps, "支柱許容圧縮耐力")
    if allow is None:
        out.append(StageCheck("支柱の軸力", "WARN", f"内側の支柱1本 {n_kn:.2f}kN（許容耐力が系列の資料に無いので確認）"))
    else:
        st = "OK" if n_kn <= allow else "NG"
        out.append(StageCheck("支柱の軸力", st, f"内側の支柱1本 {n_kn:.2f}kN ≦ 許容 {allow:.1f}kN"
                              if st == "OK" else f"内側の支柱1本 {n_kn:.2f}kN ＞ 許容 {allow:.1f}kN。スパンを詰めるか積載を下げる"))
    # 2. 1スパンあたりの積載と作業床の許容積載
    bay = su * sv * r.live_kn_m2
    deck_allow = _cap(caps, "作業床許容積載荷重", "スパン")
    if deck_allow is None:
        out.append(StageCheck("作業床の積載", "WARN", f"1スパン {bay:.2f}kN（{bay * 102:.0f}kg）。作業床の許容積載を確認"))
    else:
        st = "OK" if bay <= deck_allow else "WARN"
        msg = (f"1スパン {bay:.2f}kN（{bay * 102:.0f}kg）≦ 許容 {deck_allow:.2f}kN" if st == "OK" else
               f"積載 {r.live_kn_m2:.1f}kN/m² だと1スパン {bay:.2f}kN（{bay * 102:.0f}kg）で許容 {deck_allow:.2f}kN"
               f"（{deck_allow * 102:.0f}kg）を超える。1スパン {deck_allow * 102:.0f}kg 以下を掲示し、資材を分散して置く")
        out.append(StageCheck("作業床の積載", st, msg))
    # 3. 高さと短辺の比（転倒・横揺れ）
    short = min(r.length_u, r.length_v) / 1000.0
    ratio = h_m / max(short, 1e-6)
    out.append(StageCheck("高さと短辺の比", "OK" if ratio <= HB_LIMIT else "WARN",
                          f"高さ {h_m:.2f}m／短辺 {short:.2f}m＝{ratio:.1f}" + (
                              "（4 以下）" if ratio <= HB_LIMIT else "。4 を超えるので壁・柱から控え（壁つなぎ）を取る")))
    # 4. 墜落防止・昇降（作業床 2m 以上: 安衛則563条・526条）
    if r.deck_mm >= 2000:
        out.append(StageCheck("墜落防止・昇降", "OK", f"作業床 {r.deck_mm}mm: 外周に手すり H{GUARD_MM}＋中桟＋幅木、昇降のはしご1箇所"
                              "（作業床の隙間 3cm 以下・開口部は手すりで囲う）"))
    else:
        out.append(StageCheck("墜落防止・昇降", "OK", f"作業床 {r.deck_mm}mm（2m 未満）: 外周の手すり・はしごは計上済み"))
    if r.deck_mm < 1800:
        r.notes.append("作業床の高さが低いので、ステージの上の天井作業の姿勢（頭上の空き）を確かめてください")


def stage_report(r: StageResult) -> str:
    lines = [f"# {r.name}（内部ステージ足場）", "",
             f"- 範囲（支柱の芯）: {r.length_u:.0f} × {r.length_v:.0f} mm（スパン 長手 {'+'.join(map(str, r.spans_u))}／"
             f"短手 {'+'.join(map(str, r.spans_v))}）",
             f"- 作業床の高さ: {r.deck_mm} mm（段 {len(r.levels) - 1}・支柱 {'+'.join(map(str, r.posts))}・ジャッキ {r.jack_mm}）",
             f"- 積載: {r.live_kn_m2:.1f} kN/m²", "", "## 検証", ""]
    lines += [f"- {c.item}: {c.status} — {c.message}" for c in r.checks]
    lines += ["", "## 数量", "", "| 分類 | 呼び寸法 | 数 | 用途 |", "|---|---|---|---|"]
    lines += [f"| {c} | {d or ''} | {n} | {why} |" for c, d, n, why in r.quantity]
    if r.notes:
        lines += ["", "## 注意", ""] + [f"- {n}" for n in r.notes]
    return "\n".join(lines) + "\n"


def stage_params(r: StageResult, line_mode: bool = False) -> dict:
    """部品 ashiba_stage のパラメータ（原点は外周の支柱の始めの角、faceAng は長手の向き）."""
    return {"faceAng": r.angle_deg, "spanU": ",".join(map(str, r.spans_u)), "spanV": ",".join(map(str, r.spans_v)),
            "lvList": ",".join(str(int(h + r.base_mm)) for h in r.levels), "deckH": (r.deck_mm + r.base_mm) / 1000.0,
            "zBase": r.base_mm / 1000.0, "stName": r.name, "lineMode": bool(line_mode)}
