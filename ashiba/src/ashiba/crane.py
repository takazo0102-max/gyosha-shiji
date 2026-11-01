"""移動式クレーン（ラフテレーンクレーン）の揚重計画（利用者の指定 2026-11-01: クレーン リサーチして追加して）.
部品 ashiba_crane（1台に1つ）、置くのは scripts/crane_run.py。

- 機種: 25t タダノ GR-250N（Ⅴ）・50t GR-500N（Ⅰ）・70t GR-700N-3（性能表と寸法は crane_data.py。各社の公開資料）
- 吊り荷ごとに作業半径（旋回中心からフック）を測り、ブーム長さを短い方から試して「定格総荷重 × 計画の率（既定 90%）≧ 吊り荷＋
  フック＋玉掛け用具」かつ「フックの高さ ≧ 要る高さ」になる最短のブームを選ぶ（定格総荷重はフック・つり具を含む。表に無い
  半径は外側の行で読む）。機種を省くと、全部の吊り荷を満たす一番小さい機種
- フックの高さ: ブームの根元（旋回中心から後ろ pivB・高さ pivH）からブームの先までの高さ − 先端からフックまで
- アウトリガの反力: 1脚の最大は機体と吊り荷の和の 80%（労働安全衛生総合研究所 JNIOSH-TD の概算）とし、仕様書の作業時最大路面
  荷重を超えない。敷鉄板（日建リース 厚板鋼板 NT22×5×10＝1,524×3,048×22・802kg）を脚ごとに1枚か2枚（十字に重ねる）。1枚は
  幅 1,524 の正方形、2枚は 1,524×3,048 で受けるとして接地圧を出し、地盤の許容支持力（短期・既定 100kN/m²）と比べる
- 法令: クレーン等安全規則 69条（過負荷の制限＝定格荷重を超えない）・70条の3（軟弱地盤・地下工作物の上で使わない）・70条の4
  （鉄板等を敷き、その中央にアウトリガ）・70条の5（アウトリガは最大限張り出す）・74条（上部旋回体との接触の立入禁止＝後端
  旋回半径の中）・74条の2（つり荷の下の立入禁止）・74条の3（強風。10分間平均風速 10m/s 以上で中止）・66条の2（作業の方法・
  転倒を防ぐ方法・労働者の配置と指揮の系統を定めて周知）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ashiba.crane_data import GR250N, GR500N_74, GR700N_78

G = 9.80665
PLATE = ("厚板鋼板 NT22×5×10", 1524.0, 3048.0, 22.0, 802.0)      # 日建リース 仮設資材カタログ Vol.10 p394
PLATE_AREA = {1: 1.524 * 1.524, 2: 1.524 * 3.048}                  # 敷鉄板で受ける面積 m²（1枚・十字に2枚）
SOIL_Q = 100.0                     # 地盤の許容支持力（短期）kN/m²（既定。地盤調査の値を --soil-q で）
LOAD_RATIO = 0.90                  # 計画の率: 吊り荷＋つり具 ≦ 定格総荷重 × これ
RIGGING_T = 0.05                   # 玉掛け用具（ワイヤ・シャックル）t
REACTION_RATE = 0.80               # アウトリガ1脚の最大反力 ≒（機体＋吊り荷）× これ（JNIOSH の概算）
WIND_STOP_MS = 10.0                # 強風で作業を止める 10分間平均風速
SOURCES = ("タダノ GR-250N（Ⅴ）・GR-500N（Ⅰ）・GR-700N-3 の主要諸元・定格総荷重表・寸法図（米原商事 機種表 2023・タダノ データ"
           "シート）、労働安全衛生総合研究所 移動式クレーンの安定設置に必要な地盤の支持力要件（JNIOSH-TD）、日建連 ホイールクレーンの"
           "BIM 属性、日建リース 仮設資材カタログ Vol.10 p394（敷鉄板）、クレーン等安全規則 66条の2・69条・70条の3〜5・74条〜74条の3")


@dataclass(frozen=True)
class CraneModel:
    key: str
    kind: int                      # 部品の crType
    name: str
    capacity_t: float
    mass_t: float                  # 車両総重量
    max_jack_t: float              # 作業時最大路面荷重（最大ジャッキ反力）
    length: float                  # 全長 mm
    width: float                   # 全幅 mm
    height: float                  # 全高 mm
    front: float                   # 旋回中心から前端 mm（目安）
    out_front: float               # 旋回中心から前のアウトリガ mm
    out_rear: float                # 旋回中心から後ろのアウトリガ mm
    tail_r: float                  # 後端旋回半径 mm
    float_d: float                 # フロートの径 mm（フロート外端 − 張出幅。25t は 6,900−6,600、70t は 8,200−7,800）
    piv_h: float                   # ブームの根元の高さ mm（目安）
    piv_b: float                   # ブームの根元の旋回中心から後ろ mm（目安）
    tip_hook: float                # ブームの先からフックの上まで mm（目安）
    hook_t: float                  # 主巻フックの質量 t（目安）
    tables: dict                   # 張出幅 m → 作業半径 m → ブーム長さ m → 定格総荷重 t
    note: str = ""

    @property
    def spreads(self) -> list[float]:
        return sorted(self.tables, reverse=True)

    @property
    def booms(self) -> list[float]:
        return sorted({b for t in self.tables.values() for row in t.values() for b in row})


MODELS = {
    "25t": CraneModel("25t", 1, "タダノ GR-250N（Ⅴ）25t ラフテレーンクレーン", 25.0, 25.495, 26.9, 11530.0, 2620.0, 3475.0,
                      5400.0, 3265.0, 3415.0, 3100.0, 300.0, 2300.0, 1000.0, 1300.0, 0.25, GR250N),
    "50t": CraneModel("50t", 2, "タダノ GR-500N（Ⅰ）50t ラフテレーンクレーン", 51.0, 38.895, 38.3, 11870.0, 2960.0, 3760.0,
                      5600.0, 3600.0, 3600.0, 3550.0, 450.0, 2600.0, 1300.0, 1500.0, 0.45, {7.4: GR500N_74},
                      "アウトリガの前後の間隔は目安（寸法図に無い）。性能表は最大張出 7.4m だけ"),
    "70t": CraneModel("70t", 3, "タダノ GR-700N-3 70t ラフテレーンクレーン", 70.0, 41.295, 43.2, 12765.0, 2780.0, 3750.0,
                      6000.0, 4820.0, 4527.0, 3640.0, 400.0, 2800.0, 1500.0, 1800.0, 0.6, {7.8: GR700N_78},
                      "性能表は最大張出 7.8m だけ（モードの違う2列は大きい方）。2.1m の 70t は重荷重装置付き"),
}


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Lift:
    name: str
    radius: float                  # 作業半径 mm
    load_t: float                  # 吊り荷 t
    need_z: float                  # 要るフックの高さ（地盤から）mm
    boom: Optional[float] = None   # 選んだブーム長さ m
    rated_t: Optional[float] = None
    hook_z: float = 0.0
    status: str = "NG"
    note: str = ""

    def total_t(self, m: CraneModel) -> float:
        return self.load_t + m.hook_t + RIGGING_T


@dataclass
class CranePlan:
    name: str
    model: CraneModel
    spread: float                  # アウトリガの張出幅 m（表の張出幅）
    lifts: list[Lift]
    soil_q: float = SOIL_Q
    plates: int = 1
    reaction_t: float = 0.0
    pressure: float = 0.0          # 敷鉄板の下の接地圧 kN/m²
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)

    @property
    def governing(self) -> Optional[Lift]:
        """ブームを向けて描く吊り荷: いちばん厳しい（定格に対する比が大きい）もの."""
        ok = [x for x in self.lifts if x.rated_t]
        if not ok:
            return self.lifts[0] if self.lifts else None
        return max(ok, key=lambda x: x.total_t(self.model) / x.rated_t)

    @property
    def boom(self) -> float:
        b = [x.boom for x in self.lifts if x.boom]
        return max(b) if b else self.model.booms[0]


def table_for(m: CraneModel, spread: float) -> tuple[float, dict]:
    """張出幅 spread m で使う表: その幅以下でいちばん大きい表（安全側）。足りなければいちばん小さい表."""
    cand = [s for s in m.spreads if s <= spread + 1e-6]
    s = max(cand) if cand else min(m.spreads)
    return s, m.tables[s]


def rated(m: CraneModel, spread: float, boom: float, radius_m: float) -> Optional[float]:
    """定格総荷重 t。表の半径はその半径以上の行で読む（間は外側の行＝安全側）。届かない・近すぎれば None."""
    _s, t = table_for(m, spread)
    rows = sorted(r for r in t if boom in t[r])
    if not rows or radius_m > rows[-1] + 1e-6:
        return None
    if radius_m < rows[0] - 1e-6:                                      # 近すぎる（起伏角の上限・最小の作業半径）
        return None
    r = next(r for r in rows if r >= radius_m - 1e-6)
    return t[r][boom]


def hook_height(m: CraneModel, boom: float, radius_mm: float) -> float:
    """ブーム長さ boom（m）で作業半径 radius のときのフックの上の高さ（地盤から mm）。届かなければ −1."""
    L = boom * 1000.0
    h = radius_mm + m.piv_b
    if h >= L:
        return -1.0
    return m.piv_h + math.sqrt(L * L - h * h) - m.tip_hook


def boom_angle(m: CraneModel, boom: float, radius_mm: float) -> float:
    """ブームの起伏角（度）."""
    c = min(1.0, (radius_mm + m.piv_b) / (boom * 1000.0))
    return math.degrees(math.acos(c))


def plan_lift(m: CraneModel, spread: float, lift: Lift, ratio: float = LOAD_RATIO) -> Lift:
    """短いブームから試し、定格総荷重 × ratio ≧ 吊り荷＋フック＋玉掛け、フックの高さ ≧ 要る高さ になる最短のブームを選ぶ."""
    need = lift.total_t(m)
    best = None
    for b in m.booms:
        rt = rated(m, spread, b, lift.radius / 1000.0)
        hz = hook_height(m, b, lift.radius)
        if rt is None or hz < 0:
            continue
        if rt * ratio >= need and hz >= lift.need_z:
            lift.boom, lift.rated_t, lift.hook_z, lift.status = b, rt, hz, "OK"
            lift.note = f"{need / rt * 100:.0f}%"
            return lift
        score = (hz >= lift.need_z, rt)
        if best is None or score > best[0]:
            best = (score, b, rt, hz)
    if best:
        _sc, b, rt, hz = best
        lift.boom, lift.rated_t, lift.hook_z = b, rt, hz
        if hz < lift.need_z:
            lift.status, lift.note = "NG", f"フックが {lift.need_z - hz:.0f} 足りない（最長のブームでも）"
        elif rt >= need:
            lift.status, lift.note = "WARN", f"定格の {need / rt * 100:.0f}%（計画の {ratio * 100:.0f}% を超える）"
        else:
            lift.status, lift.note = "NG", f"定格総荷重 {rt:.2f}t < {need:.2f}t（過負荷）"
    else:
        lift.status, lift.note = "NG", "作業半径に届かない"
    return lift


JUDGE = ("揚重可能", "重すぎ", "遠すぎ", "高すぎ")
CLASH_WARN_MM, CLASH_CONTACT_MM = 4000.0, 1000.0   # ブームの中心軸からの警告・接触の距離（smartCON Planner の既定と同じ）


def judge(m: CraneModel, spread: float, radius_mm: float, need_z: float, load_t: float, ratio: float = LOAD_RATIO,
          name: str = "") -> tuple[str, Lift]:
    """揚重判定（利用者の指定 2026-11-01: smartCON Planner の揚重判定）: 揚重可能・重すぎ・遠すぎ・高すぎ.
    遠すぎ＝どのブームでもその半径に届かない、高すぎ＝届くブームでもフックが要る高さに届かない、重すぎ＝届くが
    吊荷＋フック＋玉掛けが定格総荷重 × 安全率を超える."""
    x = plan_lift(m, spread, Lift(name, radius_mm, load_t, need_z), ratio)
    if x.status == "OK":
        return JUDGE[0], x
    reach = [b for b in m.booms if rated(m, spread, b, radius_mm / 1000.0) is not None and hook_height(m, b, radius_mm) >= 0]
    if not reach:
        return JUDGE[2], x
    if all(hook_height(m, b, radius_mm) < need_z for b in reach):
        return JUDGE[3], x
    return JUDGE[1], x


def seg_box_distance(a: tuple, b: tuple, lo: tuple, hi: tuple) -> float:
    """線分 a–b と軸に沿った箱（lo〜hi）の最短距離 mm（箱の中を通れば 0）。距離は t について凸なので三分探索."""
    def d(t):
        q = [a[i] + (b[i] - a[i]) * t for i in range(3)]
        return math.sqrt(sum(max(lo[i] - q[i], 0.0, q[i] - hi[i]) ** 2 for i in range(3)))
    t0, t1 = 0.0, 1.0
    for _ in range(60):
        m1, m2 = t0 + (t1 - t0) / 3.0, t1 - (t1 - t0) / 3.0
        if d(m1) <= d(m2):
            t1 = m2
        else:
            t0 = m1
    return min(d(0.0), d(1.0), d((t0 + t1) / 2.0))


def boom_axis(params: dict, origin: tuple, carrier_deg: float) -> tuple[tuple, tuple]:
    """置いた部品のパラメータ（m・度）→ ブームの中心軸（根元・先）の図面の座標 mm."""
    slew = params.get("slew", 0.0)
    bl, ba = params.get("boomL", 10.0), params.get("boomA", 45.0)
    if params.get("travel"):
        bl, ba, slew = params.get("bMin", bl), 0.0, 0.0
    a = math.radians(carrier_deg + slew)
    pb, ph = params.get("pivB", 1.0), params.get("pivH", 2.3)
    r0, r1 = -pb, -pb + bl * math.cos(math.radians(ba))
    z1 = ph + bl * math.sin(math.radians(ba))
    p0 = (origin[0] + r0 * 1000.0 * math.cos(a), origin[1] + r0 * 1000.0 * math.sin(a), origin[2] + ph * 1000.0)
    p1 = (origin[0] + r1 * 1000.0 * math.cos(a), origin[1] + r1 * 1000.0 * math.sin(a), origin[2] + z1 * 1000.0)
    return p0, p1


def crane_plan(name: str, lifts: list[Lift], model: Optional[str] = None, spread: Optional[float] = None,
               soil_q: float = SOIL_Q, ratio: float = LOAD_RATIO) -> CranePlan:
    """吊り荷の並び → 機種・ブーム・アウトリガ・敷鉄板・検定。model を省くと全部を満たす一番小さい機種."""
    keys = [model] if model else list(MODELS)
    plan = None
    for k in keys:
        m = MODELS[k]
        sp = spread if spread else max(m.spreads)
        ls = [plan_lift(m, sp, Lift(x.name, x.radius, x.load_t, x.need_z), ratio) for x in lifts]
        plan = CranePlan(name, m, table_for(m, sp)[0], ls, soil_q)
        if all(x.status == "OK" for x in ls):
            break
    assert plan is not None
    _foundation(plan)
    _quantity(plan)
    _checks(plan, ratio, spread)
    return plan


def _foundation(p: CranePlan) -> None:
    m = p.model
    q_max = max((x.total_t(m) for x in p.lifts), default=0.0)
    p.reaction_t = min(m.max_jack_t, REACTION_RATE * (m.mass_t + q_max))
    for n in (1, 2):
        p.plates = n
        p.pressure = p.reaction_t * G / PLATE_AREA[n]
        if p.pressure <= p.soil_q:
            break


def _quantity(p: CranePlan) -> None:
    m = p.model
    q = p.quantity
    q.append((m.name, 1, f"アウトリガ張出 {p.spread:g}m・ブーム {p.boom:g}m"))
    name, w, l, t, kg = PLATE
    q.append((f"{name}（{w:.0f}×{l:.0f}×{t:.0f}・{kg:.0f}kg）", 4 * p.plates,
              f"アウトリガ4脚に {p.plates}枚ずつ" + ("（十字に重ねる）" if p.plates == 2 else "")))
    q.append(("玉掛け用具（ワイヤロープ・シャックル）", len(p.lifts), f"吊り荷ごと（{RIGGING_T * 1000:.0f}kg で見込む）"))
    q.append(("カラーコーン・バー（立入禁止の区画）", math.ceil(2 * math.pi * (m.tail_r + 1000.0) / 2000.0),
              f"後端旋回半径 {m.tail_r:.0f}＋1,000 の円に 2m ごと"))


def _checks(p: CranePlan, ratio: float, spread: Optional[float]) -> None:
    m, c = p.model, p.checks
    for x in p.lifts:
        need = x.total_t(m)
        c.append(Check(f"吊り荷 {x.name}", x.status,
                       f"作業半径 {x.radius / 1000:.1f}m・吊り荷 {x.load_t:g}t＋フック {m.hook_t:g}t＋玉掛け {RIGGING_T:g}t＝{need:.2f}t"
                       + (f"・ブーム {x.boom:g}m（起伏角 {boom_angle(m, x.boom, x.radius):.0f}°）定格総荷重 {x.rated_t:.2f}t・"
                          f"フックの高さ {x.hook_z / 1000:.1f}m（要る {x.need_z / 1000:.1f}m）" if x.boom else "")
                       + f"。{x.note}（クレーン則 69条 過負荷の制限・計画は定格の {ratio * 100:.0f}% 以内）"))
    c.append(Check("アウトリガの張出", "OK" if spread is None or spread >= max(m.spreads) - 1e-6 else "WARN",
                   f"張出幅 {p.spread:g}m の性能表で計画（最大 {max(m.spreads):g}m。クレーン則 70条の5: 最大限に張り出す。"
                   "張り出せない側は張出幅に応じた性能で）" + (f"。{m.note}" if m.note else "")))
    name, w, l, t, _kg = PLATE
    c.append(Check("アウトリガの反力と敷鉄板", "OK" if p.pressure <= p.soil_q else "NG",
                   f"1脚の最大反力 約 {p.reaction_t:.1f}t（機体 {m.mass_t:g}t と吊り荷の和の {REACTION_RATE * 100:.0f}%・作業時最大路面荷重 "
                   f"{m.max_jack_t:g}t 以下）を {name} {p.plates}枚（{PLATE_AREA[p.plates]:.2f}m² で受ける）で接地圧 "
                   f"{p.pressure:.0f}kN/m² ≦ 地盤の許容支持力 {p.soil_q:.0f}kN/m²"
                   + ("" if p.pressure <= p.soil_q else "。地盤改良・敷鉄板を増やす・機種を下げる")
                   + "（クレーン則 70条の3・70条の4: 鉄板の中央にアウトリガ。JNIOSH: 支持力の安全率は 2 以上が望ましい）"))
    c.append(Check("立入禁止", "OK", f"後端旋回半径 R{m.tail_r:.0f} の中（上部旋回体との接触。クレーン則 74条）と、つり荷の下"
                                    "（74条の2）は立入禁止。カラーコーン・バーで区画"))
    c.append(Check("強風", "OK", f"10分間平均風速 {WIND_STOP_MS:.0f}m/s 以上は作業を中止し、ブームを下げる（クレーン則 74条の3・74条の4）"))
    c.append(Check("作業計画", "OK", "作業の方法・転倒を防ぐ方法・労働者の配置と指揮の系統を定めて周知（クレーン則 66条の2）。"
                                    "合図者を決める（71条）"))


def rated_strings(m: CraneModel, spread: float = 0.0) -> dict:
    """部品が姿勢から定格総荷重を読む表: 張出幅 mm（rtS。大きい順、最大 6 段）・ブーム長さ mm（rtB）・作業半径 mm（rtR。全部の
    張出幅の行を合わせた並び）と、張出幅の段 i・ブームの列 k ごとの定格 kg（rs{i}c{k}。半径の行の順、無い所は 0）.
    その張出幅の表に無い半径の行は、その半径以上で一番近い行の値（表の読み方と同じで安全側）。Archicad の文字のパラメータは
    255 字で切れる（2026-11-01、表を1つの文字にして 25t でも途中で切れ、定格が 0 と出た）ので段と列ごとに."""
    spreads = m.spreads[:6]
    booms = m.booms[:8]
    radii = sorted({r for sp in spreads for r in m.tables[sp]})
    out = {"rtS": ",".join(f"{sp * 1000:.0f}" for sp in spreads), "rtB": ",".join(f"{b * 1000:.0f}" for b in booms),
           "rtR": ",".join(f"{r * 1000:.0f}" for r in radii)}
    for i in range(1, 7):
        for k in range(1, 9):
            key = f"rs{i}c{k}"
            if i > len(spreads) or k > len(booms):
                out[key] = ""
                continue
            t, b = m.tables[spreads[i - 1]], booms[k - 1]
            vals = []
            for r in radii:
                rows = [rr for rr in sorted(t) if rr >= r - 1e-9 and b in t[rr]]
                vals.append(str(int(round(t[rows[0]][b] * 1000))) if rows and rows[0] == min(rr for rr in sorted(t) if rr >= r - 1e-9) else "0")
            out[key] = ",".join(vals)
            assert len(out[key]) <= 255, (m.key, key)
    return out


def part_params(p: CranePlan, slew_deg: float, ground_dz: float = 0.0, ratio: float = LOAD_RATIO) -> dict:
    """部品 ashiba_crane のパラメータ（m・度）。slew_deg は車体の向きからのブームの向き。いちばん厳しい吊荷の姿勢（作業半径・
    ブーム長さ）で置き、平面・3D のホットスポットで動かすと部品が性能表から定格総荷重を読み直す."""
    m = p.model
    g = p.governing
    radius = g.radius if g else 6000.0
    boom = g.boom if g and g.boom else p.boom
    return {"crType": m.kind, "crName": m.name.split(" ")[1],
            "carL": m.length / 1000.0, "carW": m.width / 1000.0, "carH": m.height / 1000.0, "carF": m.front / 1000.0,
            "outF": m.out_front / 1000.0, "outR": m.out_rear / 1000.0, "outW": p.spread, "fltD": m.float_d / 1000.0,
            "oFL": p.spread / 2, "oFR": p.spread / 2, "oRL": p.spread / 2, "oRR": p.spread / 2,
            "tailR": m.tail_r / 1000.0, "pivH": m.piv_h / 1000.0, "pivB": m.piv_b / 1000.0, "tipHk": m.tip_hook / 1000.0,
            "hkR": radius / 1000.0, "slew": slew_deg, "prio": 0, "boomL": boom, "boomA": boom_angle(m, boom, radius),
            "bMin": min(m.booms), "bMax": max(m.booms), "hkZ": 0.0,
            "loadT": g.load_t if g else 0.0, "hookT": m.hook_t, "rigT": RIGGING_T, "sfRate": ratio,
            **rated_strings(m),
            "plN": p.plates, "plDraw": False, "wrR": ",".join(f"{x.radius:.0f}" for x in p.lifts),
            "wrDir": 0.0, "wrSpan": 360.0, "travel": False, "ldOn": bool(g and g.load_t > 0)}


def effective_spread(ps: dict) -> float:
    """置いた部品のパラメータ（m）→ 定格を読む張出幅 m（4脚の一番小さい張出の 2 倍。脚のパラメータが無い古い部品は outW）."""
    legs = [float(ps[k]) for k in ("oFL", "oFR", "oRL", "oRR") if isinstance(ps.get(k), (int, float))]
    return 2 * min(legs) if len(legs) == 4 else float(ps.get("outW", 0.0) or 0.0)


def outrigger_plates(p: CranePlan) -> list[tuple[tuple[float, float], bool, float]]:
    """アウトリガの下の敷鉄板（部品 ashiba_plate）: [(車体の座標での板の隅 mm, 長い辺が Y か, 高さ mm)]。1枚は長い辺を車体に
    沿わせ、2枚は上にもう1枚を十字に（利用者の指定 2026-11-01: 敷鉄板は別オブジェクトにして）."""
    m = p.model
    _name, s, lg, t, _kg = PLATE
    out = []
    for x in (m.out_front, -m.out_rear):
        for y in (p.spread * 500.0, -p.spread * 500.0):
            out.append(((x - lg / 2.0, y - s / 2.0), False, 0.0))
            if p.plates >= 2:
                out.append(((x - s / 2.0, y - lg / 2.0), True, t))
    return out


def report(plans: list[CranePlan]) -> str:
    out = ["# 移動式クレーン", "", f"出典: {SOURCES}", ""]
    for p in plans:
        m = p.model
        out += [f"## {p.name}: {m.name}（張出 {p.spread:g}m・ブーム最長 {p.boom:g}m）", "",
                "| 吊り荷 | 作業半径 | 重さ（＋フック・玉掛け） | ブーム | 定格総荷重 | 比 | フックの高さ／要る | 判定 |",
                "|---|---|---|---|---|---|---|---|"]
        for x in p.lifts:
            need = x.total_t(m)
            out.append(f"| {x.name} | {x.radius / 1000:.1f}m | {x.load_t:g}t（{need:.2f}t） | {x.boom or '-'}m | "
                       f"{x.rated_t or 0:.2f}t | {need / x.rated_t * 100 if x.rated_t else 0:.0f}% | "
                       f"{x.hook_z / 1000:.1f}／{x.need_z / 1000:.1f}m | {x.status} |")
        out += ["", "| 品名 | 数 | 注 |", "|---|---|---|"] + [f"| {a} | {b:g} | {c} |" for a, b, c in p.quantity]
        out += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"] + [f"| {c.item} | {c.status} | {c.message} |" for c in p.checks]
        out.append("")
    return "\n".join(out)
