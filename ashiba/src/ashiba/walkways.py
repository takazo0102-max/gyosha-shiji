"""仮設通路（アルミ製の伸縮通路。日工セック ライトブリッジ）を、両端の島（足場の塔）の間に渡す. 部品 ashiba_walkway.

利用者の指定（2026-10-29）「https://www.nikkosec.co.jp/page-73/ 次足場はこういうのにも対応できるようにしたい」。
地中梁・鉄骨・法面・水路などを渡る仮設通路。両端に島（足場1スパン×1スパンの塔。本体と同じ部材で interior_stage が
組む）を立て、その布材（単管 φ42.7〜48.6・枠組のパイプ）に本体のフックを掛ける。

- 機種: data/walkway_models.csv（日工セック ライトブリッジ カタログ: 長さ 2400〜7200 を4機種で伸縮、床幅 660・全幅 915、
  安全荷重 2.45kN＝250kgf、本体・手すりの重量、幅木 LBRV21/38 の組合せ）。島の布材の間（フックの掛かる間）の長さが
  伸縮の範囲に入る機種のうち、いちばん軽いもの
- 島: 通路の両端の外に、短手（足場の幅。全幅 915 が載る 1219）の塔。始めの島は長手2スパン（階段＋踊り場）、終わりの島は1スパンで昇降なし。島の床は通路と同じ高さ。
  昇降は始めの島の階段（interior_stage の階段）。島には転倒防止（控え・壁つなぎ）
- 検証: 長さの範囲（7200 を超えれば途中に島を足す、2400 未満なら足場板で渡すか島を寄せる）、積載 250kg の掲示、
  両端の高さの差（カタログは「多少の傾斜」まで。勾配の上限は記載が無いのでメーカーに確かめる）、設置手順（押しボルト・
  4点吊り・介錯ロープ・幅木の専用金具）

入力: walkways: [{"name": "地中梁通路1", "start_mm": [x, y], "end_mm": [x, y], "deck_mm": 1800, "base_mm": 0,
                  "end_deck_mm": 1800（終わりの島の床。無ければ deck_mm）, "model": "LB-4572"（無ければ自動）}]
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DATA = Path(__file__).resolve().parents[2] / "data" / "walkway_models.csv"
ISLAND_W_MM = 1219          # 島の短手（足場の幅。全幅 915 の通路が載る）
G_KN_PER_KG = 9.80665 / 1000.0
SLOPE_WARN = 0.10           # 両端の高さの差／長さ がこれを超えたらメーカーに勾配を確かめる（カタログは「多少の傾斜」）


@dataclass(frozen=True)
class WalkwayModel:
    model: str
    maker: str
    min_mm: int
    max_mm: int
    deck_w_mm: int
    overall_w_mm: int
    rail_h_mm: int
    mid_h_mm: int
    load_kn: float
    body_kg: float
    rail_kg_side: float
    total_kg: float
    toe_2100: int
    toe_3850: int
    source: str


def load_walkway_models(path: Path = DATA) -> list[WalkwayModel]:
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(WalkwayModel(
                row["model"], row["maker"], int(row["min_mm"]), int(row["max_mm"]), int(row["deck_w_mm"]),
                int(row["overall_w_mm"]), int(row["rail_h_mm"]), int(row["mid_h_mm"]), float(row["load_kn"]),
                float(row["body_kg"]), float(row["rail_kg_side"]), float(row["total_kg"]),
                int(row["toe_2100"]), int(row["toe_3850"]), row["source"]))
    return out


def choose_model(length_mm: float, models: Optional[list[WalkwayModel]] = None,
                 name: str = "") -> Optional[WalkwayModel]:
    """長さが伸縮の範囲に入る機種のうちいちばん軽いもの（name を指定すればそれが範囲に入るときだけ）."""
    models = models or load_walkway_models()
    fit = [m for m in models if m.min_mm <= length_mm <= m.max_mm and (not name or m.model == name)]
    return min(fit, key=lambda m: m.total_kg) if fit else None


@dataclass
class WalkwayCheck:
    item: str
    status: str
    message: str


@dataclass
class WalkwayResult:
    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    length_mm: float
    deck_mm: float
    end_deck_mm: float
    base_mm: float
    model: Optional[WalkwayModel]
    islands: list = field(default_factory=list)        # interior_stage.StageResult（始め・終わり）
    checks: list[WalkwayCheck] = field(default_factory=list)
    quantity: list[tuple[str, int, int, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.end[1] - self.start[1], self.end[0] - self.start[0]))

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)


def _island_corners(at: tuple[float, float], u: tuple[float, float], span: float, outward: float) -> list[list[float]]:
    """通路の端 at から外向き（outward＝−1 は始めの側、＋1 は終わりの側）に長手 span・短手 ISLAND_W_MM の島の範囲
    （interior_stage は範囲の内側 150 に支柱を立てるので、その分広げる）. 左回りで、奥（通路と反対）の角から通路へ向かう
    辺を先にする: 内部ステージの始めの角が奥に来て、階段（始めの1スパン）が奥の升目、通路を受けるのは手前の升目になる."""
    from .interior_stage import CLEAR_MM

    a = span + 2 * CLEAR_MM + 1.0       # 1mm は斜めの通路の計算の誤差で 1219 が 914 に落ちないように
    b = ISLAND_W_MM + 2 * CLEAR_MM + 1.0
    # 島の通路側の布材が at に来るよう、範囲を at から外へ CLEAR_MM 戻した所から始める
    n = (at[0] - outward * u[0] * CLEAR_MM, at[1] - outward * u[1] * CLEAR_MM)
    f = (n[0] + outward * u[0] * a, n[1] + outward * u[1] * a)
    d = (-outward * u[0], -outward * u[1])          # 奥 → 通路
    w = (-d[1], d[0])
    pts = [(f[0] - w[0] * b / 2, f[1] - w[1] * b / 2), (n[0] - w[0] * b / 2, n[1] - w[1] * b / 2),
           (n[0] + w[0] * b / 2, n[1] + w[1] * b / 2), (f[0] + w[0] * b / 2, f[1] + w[1] * b / 2)]
    return [[x, y] for x, y in pts]


def solve_walkway(item: dict, master, capacities: Optional[dict] = None) -> WalkwayResult:
    from .interior_stage import solve_stage

    name = str(item.get("name") or "仮設通路")
    s = tuple(map(float, item["start_mm"]))
    e = tuple(map(float, item["end_mm"]))
    length = math.dist(s, e)
    if length < 1.0:
        raise ValueError(f"{name}: 始めと終わりが同じ点です")
    deck = float(item.get("deck_mm", 1800.0) or 1800.0)
    end_deck = float(item.get("end_deck_mm", deck) or deck)
    base = float(item.get("base_mm", 0.0) or 0.0)
    models = load_walkway_models()
    model = choose_model(length, models, str(item.get("model") or ""))
    r = WalkwayResult(name, s, e, length, deck, end_deck, base, model)
    u = ((e[0] - s[0]) / length, (e[1] - s[1]) / length)
    # 島（両端の外に足場の幅の塔）。始めの島は2スパン（階段の升目と通路を受ける踊り場の升目）、終わりの島は1スパンで
    # 通路から渡るだけ（昇降を持たない）
    span = max(v for v in master.span_lengths() if v <= 1829)
    # 通路の片端の反力（本体＋手すり＋安全荷重の半分）を、フックを受ける布材の両端の支柱2本で受ける
    end_kn = ((model.total_kg * G_KN_PER_KG + model.load_kn) / 2.0 / 2.0) if model else 0.0
    for at, out, z, acc, n_sp, tag in ((s, -1.0, deck, "階段", 2, "始め"), (e, 1.0, end_deck, "なし", 1, "終わり")):
        st = solve_stage({"name": f"{name} の{tag}の島", "corners_mm": _island_corners(at, u, n_sp * span, out),
                          "deck_mm": z, "base_mm": base, "access": acc, "open_end": True,
                          "end_post_kn": end_kn}, master, capacities)
        r.islands.append(st)
    # 島の床は支柱のコマの段に合わせて少し上下する（実機 2026-10-29: 2100 の指定が 2015）。通路はフックを島の布材に
    # 掛けるので、両端の高さは島の床の高さにそろえる（指定のままだと通路の端が島の床から浮く）
    asked = (r.deck_mm, r.end_deck_mm)
    r.deck_mm, r.end_deck_mm = float(r.islands[0].deck_mm), float(r.islands[1].deck_mm)
    for tag, want, got in (("始め", asked[0], r.deck_mm), ("終わり", asked[1], r.end_deck_mm)):
        if abs(want - got) >= 1.0:
            r.notes.append(f"{tag}の島の床は支柱のコマの段に合わせて {want:.0f} → {got:.0f}mm。通路の{tag}の端もこの高さに掛ける")
    _checks(r, models)
    _quantity(r)
    return r


def _checks(r: WalkwayResult, models: list[WalkwayModel]) -> None:
    lo, hi = min(m.min_mm for m in models), max(m.max_mm for m in models)
    if r.model is None:
        if r.length_mm > hi:
            n = math.ceil(r.length_mm / hi)
            msg = (f"長さ {r.length_mm:.0f}mm は伸縮の上限 {hi}mm を超える。途中に島を {n - 1}か所足して {n}本に分ける"
                   f"（1本 {r.length_mm / n:.0f}mm）")
        elif r.length_mm < lo:
            msg = f"長さ {r.length_mm:.0f}mm は伸縮の下限 {lo}mm に届かない。足場板・布板で渡すか、島を {lo}mm 以上離す"
        else:
            msg = f"長さ {r.length_mm:.0f}mm に合う機種がない（指定の機種の伸縮の範囲外）"
        r.checks.append(WalkwayCheck("通路の長さ", "NG", msg))
    else:
        m = r.model
        r.checks.append(WalkwayCheck(
            "通路の長さ", "OK",
            f"{m.maker} ライトブリッジ {m.model}（伸縮 {m.min_mm}〜{m.max_mm}mm・床幅 {m.deck_w_mm}・全幅 {m.overall_w_mm}・"
            f"合計 {m.total_kg:.0f}kg）を {r.length_mm:.0f}mm に伸ばして使う。調整後は外枠横の押しボルトで固定"))
        r.checks.append(WalkwayCheck(
            "積載", "OK",
            f"安全荷重 {m.load_kn}kN（{m.load_kn / 9.80665 * 1000:.0f}kg）。通路の入口に「最大積載 {m.load_kn / 9.80665 * 1000:.0f}kg」"
            "を掲示し、資材の仮置きをしない（安衛則562条）"))
        # フックを受ける布材（島の短手）には通路の片端の荷重が布材の中ほど2点で掛かる。布材の許容荷重は系列の資料に
        # 無いので、値を出して確かめる事項にする
        end_kn = m.total_kg * G_KN_PER_KG / 2.0 + m.load_kn / 2.0
        w = r.islands[0].spans_v[0] if r.islands and r.islands[0].spans_v else ISLAND_W_MM
        r.checks.append(WalkwayCheck(
            "フックを受ける布材", "WARN",
            f"島の布材（{w}）1本に通路の片端 {end_kn:.2f}kN（本体＋手すり {m.total_kg * G_KN_PER_KG / 2.0:.2f}・積載 "
            f"{m.load_kn / 2.0:.2f}）がフック2点で掛かる。布材の許容荷重を系列の資料・メーカーに確かめ、足りなければ"
            "布材の下に単管を添えるか受けの支柱を足す"))
    dz = abs(r.end_deck_mm - r.deck_mm)
    slope = dz / r.length_mm if r.length_mm else 0.0
    if dz < 1.0:
        r.checks.append(WalkwayCheck("勾配", "OK", "両端の島の床が同じ高さ"))
    else:
        r.checks.append(WalkwayCheck(
            "勾配", "WARN" if slope > SLOPE_WARN else "OK",
            f"両端の高さの差 {dz:.0f}mm（勾配 {slope * 100:.1f}%）。カタログは「多少の傾斜」まで"
            + ("。上限はメーカー（日工セック）に確かめる" if slope > SLOPE_WARN else "")))
    for st in r.islands:
        bad = [c for c in st.checks if c.status == "NG"]
        if bad:
            r.checks.append(WalkwayCheck("島", "NG", f"{st.name}: " + "／".join(f"{c.item} {c.message}" for c in bad)))
    r.notes.append("島には必ず転倒防止（控え・壁つなぎ、または島どうしをつなぐ）を行う（カタログの設置手順）")
    r.notes.append("島の通路が取り付く辺は出入口（外周の手すり・中桟・幅木なし）。通路の手すりと島の手すりをすき間なくつなぐ")
    r.notes.append("通路は4点吊り（吊り環にワイヤー）で掛け、吊り込みは必ず介錯ロープを付ける。設置後に各所の締付ボルトを確かめ、"
                   "幅木は専用の固定金具（LBRVK）で付ける")


def _quantity(r: WalkwayResult) -> None:
    m = r.model
    q = r.quantity
    if m is not None:
        q.append(("仮設通路", int(m.max_mm), 1, f"{m.maker} ライトブリッジ {m.model} 本体（{m.body_kg:.0f}kg・{r.length_mm:.0f}mm に伸縮）"))
        q.append(("仮設通路の手すり", int(m.max_mm), 2, f"{m.model} 用の手すり（両側・片側 {m.rail_kg_side:.0f}kg）"))
        if m.toe_2100:
            q.append(("仮設通路の幅木", 2100, 2 * m.toe_2100, "アルミ幅木 LBRV21（W28×H125×L2100・両側）"))
        if m.toe_3850:
            q.append(("仮設通路の幅木", 3850, 2 * m.toe_3850, "アルミ幅木 LBRV38（W28×H125×L3850・両側）"))
        n_toe = 2 * (m.toe_2100 + m.toe_3850)
        q.append(("仮設通路の幅木固定金具", 0, 2 * n_toe, "LBRVK（幅木1枚の両端。各手摺柱に設置・数は手摺柱に合わせて確かめる）"))
    # 通路が取り付く辺（島の長手の終わりの短辺）は島の側で出入口にしてある（open_end。手すり・中桟・幅木なし）
    for st in r.islands:
        for cat, dim, n, why in st.quantity:
            q.append((cat, dim, n, f"{st.name}: {why}"))


def walkway_report(r: WalkwayResult) -> str:
    lines = [f"# {r.name}（仮設通路）", "",
             f"- 長さ（島の布材の間）: {r.length_mm:.0f} mm",
             f"- 床の高さ: 始め {r.deck_mm:.0f} mm・終わり {r.end_deck_mm:.0f} mm",
             f"- 機種: {r.model.maker + ' ' + r.model.model if r.model else '合う機種なし'}", "", "## 検証", ""]
    lines += [f"- {c.item}: {c.status} — {c.message}" for c in r.checks]
    lines += ["", "## 数量", "", "| 分類 | 呼び寸法 | 数 | 用途 |", "|---|---|---|---|"]
    lines += [f"| {c} | {d or ''} | {n} | {why} |" for c, d, n, why in r.quantity]
    lines += ["", "## 注意", ""] + [f"- {n}" for n in r.notes]
    return "\n".join(lines) + "\n"


def walkway_params(r: WalkwayResult) -> dict:
    """部品 ashiba_walkway のパラメータ（原点＝始めの島の布材の上の通路の芯、faceAng で通路の向き）."""
    m = r.model
    return {"faceAng": r.angle_deg, "wkL": r.length_mm / 1000.0, "zDeck": (r.deck_mm + r.base_mm) / 1000.0,
            "zEnd": (r.end_deck_mm + r.base_mm) / 1000.0, "wkModel": m.model if m else "",
            "railH": (m.rail_h_mm if m else 966) / 1000.0, "midH": (m.mid_h_mm if m else 484) / 1000.0,
            "stName": r.name}
