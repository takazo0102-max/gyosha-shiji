"""仮設建物（現場事務所・詰所・休憩所・更衣室・トイレ・倉庫）（開発ループ 2026-11-01: 他に必要な仮設材の4番。部品 ashiba_house）.

ユニットハウス（連棟・1〜2段積み、2段なら外階段と2階の外廊下）を1棟1部品で置き、建物の用途と人数から便所の数・事務所の面積・
休憩所・消火器・転倒などを判定する。

出典（調べた資料）:
- ナガワ スーパーハウス（ジェコス・アクティオのカタログ）: 1坪 SH-H1 1,850×1,850×2,603・460kg、2坪 SH-H2 3,650×1,850・720kg、
  3.1坪 SH-H3 4,550×2,300・1,000kg、3.8坪 SH-H4 5,450×2,300・1,110kg、5坪 SH-H6 7,250×2,300・1,400kg。三協フロンテア CT-J は
  床耐荷重 295kg/㎡、「1階が単体なら2階建て不可」（1階を連棟に）
- 仮設トイレ: ハマネツ TU 系 W850×D1,550×H2,470・140kg、快適トイレハウス（カナテック KⅢ）2,600×2,200×2,650・900kg（カナモト
  カタログ p511〜519）。国交省 快適トイレ（R8.2.27 国技建管第10号）: 洋式・水洗・施錠・照明・男女表示・鏡と手洗器 ほか 11項目
- 労働安全衛生規則 628条（便所: 男性の大便所 60人・小便所 30人・女性 20人ごとに1つ）・628条の2（独立個室型は1つ×10人を差し引く。
  常時10人以内は独立個室型1つでよい。令和3年12月1日施行）・618条（休養室: 常時50人以上か女性30人以上で男女別）・613条
  （休憩設備）・612条の2（熱中症: WBGT 28度以上か気温 31度以上の作業に報告の体制と手順。令和7年6月1日施行）
- 事務所衛生基準規則（気積 10㎥/人・照度 300lx・開口 床の 1/20）、日本建築学会 仮設構造物計画の手引き（竹中工務店。事務所は施工者
  8〜10㎡/人・監理者 10〜12㎡/人、出入口の近く・現場が見渡せる所）
- 建築基準法 85条2項（工事現場の事務所・下小屋・材料置場は確認申請不要、第3章も外れる。20条は残る、防火・準防火地域で延べ
  50㎡超は 62条）・令147条、令23条（屋外階段 直通 90cm・その他 60cm、蹴上 22cm 以下・踏面 21cm 以上）、消防法施行令10条
  （消火器は事務所 延べ 300㎡・倉庫 150㎡以上で義務）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.80665
WIND_MS = 30.0                         # 転倒を見る風速（仮囲いの検討と同じ 30m/s。目安）
CF = 1.2                               # 風力係数（箱形の目安）
FLOOR_LOAD = 295.0                     # 床の積載 kg/㎡（三協 CT-J）
OFFICE_M2 = 9.0                        # 事務所 1人あたり（施工者 8〜10㎡）
REST_M2 = 1.2                          # 詰所・休憩所 同時に休む1人あたり（法令の基準は無く 1.0〜1.5 の目安）
STAIR_W_MIN, CORR_W_MIN, RAIL_H = 900.0, 900.0, 1100.0   # 屋外階段（直通）・2階の外廊下・手すり（目安）

# 番号 → (名前, 長手 W mm, 奥行 D mm, 高さ H mm, kg, 個室の便器)
HOUSES = {
    1: ("スーパーハウス 1坪（SH-H1）", 1850.0, 1850.0, 2603.0, 460.0, 0),
    2: ("スーパーハウス 2坪（SH-H2）", 3650.0, 1850.0, 2603.0, 720.0, 0),
    3: ("スーパーハウス 3.1坪（SH-H3）", 4550.0, 2300.0, 2603.0, 1000.0, 0),
    4: ("スーパーハウス 3.8坪（SH-H4）", 5450.0, 2300.0, 2603.0, 1110.0, 0),
    5: ("スーパーハウス 5坪（SH-H6）", 7250.0, 2300.0, 2603.0, 1400.0, 0),
    6: ("仮設トイレ（ハマネツ TU・洋式1）", 850.0, 1550.0, 2470.0, 140.0, 1),
    7: ("快適トイレハウス（カナテック KⅢ）", 2600.0, 2200.0, 2650.0, 900.0, 2),
    # アクティオ レンタル総合カタログ【ハウス・備品】vol.40 p86（利用者の指定 2026-11-01: https://www.aktio.co.jp/products/pdf/Vol.40_p04.pdf）
    8: ("ユニバーサルハウス 2.0坪（アクティオ NA6 02000）", 3740.0, 1800.0, 2575.0, 600.0, 0),
    9: ("ユニバーサルハウス 2.9坪（アクティオ NA6 02900）", 4590.0, 1900.0, 2575.0, 750.0, 0),
    10: ("ユニバーサルハウス 3.8坪（アクティオ NA6 03800）", 5540.0, 2200.0, 2575.0, 1050.0, 0),
    11: ("連棟型パネルユニットハウス 4.0坪（アクティオ NAN 40100・大町 NOIA-410）", 5700.0, 2300.0, 2650.0, 1370.0, 0),
    12: ("プロハウス 4.0坪（アクティオ NNA 40000・エスアールエス P4N）", 5632.0, 2285.0, 2700.0, 1130.0, 0),
}
STACKABLE = (3, 4, 5, 10, 11, 12)      # 2段積みにする型（奥行 2,200 以上。メーカーに確かめる）
# ハウス用の外階段（カナモト レンタル。カナテック）: 型 → (品名, 幅 D mm, 長さ W mm, 高さ H mm, kg)。1階の高さで選ぶ
# （FE用は 2.7m までの低い型、KD用は高い型。階段の幅は屋外の直通階段 90cm 以上を満たす）
STAIRS = {"FE": ("ハウス用階段 FE用（カナテック）", 900.0, 4100.0, 3350.0, 250.0),
          "KD": ("ハウス用階段 KD用（カナテック）", 1150.0, 4990.0, 3900.0, 430.0)}
STAIR_FE_MAX_H = 2700.0


def stair_for(unit_h: float) -> str:
    """1階の高さ mm → ハウス用階段の型."""
    return "FE" if unit_h <= STAIR_FE_MAX_H else "KD"


USES = {1: "事務所", 2: "詰所", 3: "休憩所", 4: "更衣室", 5: "会議室", 6: "倉庫", 7: "トイレ", 8: "シャワー"}


@dataclass
class House:
    name: str
    kind: int = 4                      # HOUSES の番号
    units: int = 1                     # 連棟の数（ハウスは奥行の向き、トイレは横に並べる）
    tiers: int = 1                     # 段数（1〜2。3 は専用の架台）
    uses: tuple = (1,)                 # 段ごとの用途（USES の番号）
    stair: int = 0                     # 外階段（0＝X0 の端・1＝X の端）
    stair_w: float = 0.0               # 外階段の幅（0＝製品の幅）
    corr_w: float = 1000.0

    @property
    def stair_kind(self) -> str:
        return stair_for(HOUSES[self.kind][3])

    @property
    def stair_width(self) -> float:
        return self.stair_w or STAIRS[self.stair_kind][1]

    @property
    def size(self) -> tuple[float, float, float]:
        _n, w, d, h, _kg, _t = HOUSES[self.kind]
        if self.is_toilet:
            return w * self.units, d, h
        return w, d * self.units, h

    @property
    def is_toilet(self) -> bool:
        return HOUSES[self.kind][5] > 0

    def area(self, use: int | None = None) -> float:
        """床面積 ㎡（use を渡すとその用途の段だけ）."""
        w, d, _h = self.size
        tiers = [u for u in list(self.uses)[: self.tiers] + [self.uses[-1]] * (self.tiers - len(self.uses))]
        return sum(w * d / 1e6 for u in tiers if use is None or u == use)

    @property
    def mass(self) -> float:
        return HOUSES[self.kind][4] * self.units * self.tiers

    @property
    def toilets(self) -> int:
        return HOUSES[self.kind][5] * self.units * self.tiers

    def wind_speed(self) -> float:
        """固定しないときに長手の面に風を受けて転倒する風速 m/s（重さ×奥行/2 ＝ 0.6V²·Cf·面積·高さ/2）."""
        w, d, h = self.size
        mass = self.mass
        if self.is_toilet:                                   # トイレは1基ずつ別に立つ
            w, mass = HOUSES[self.kind][1], HOUSES[self.kind][4]
        hh = h * self.tiers / 1000.0
        m_r = mass * G * d / 1000.0 / 2.0
        return math.sqrt(m_r / (0.6 * CF * w / 1000.0 * hh * hh / 2.0))


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Site:
    houses: list[House] = field(default_factory=list)
    staff: int = 0                     # 職員（事務所。便所は男性として数える。女性の職員は women へ）
    men: int = 0                       # 作業員 男性
    women: int = 0                     # 作業員・職員 女性
    fire_zone: bool = False            # 防火・準防火地域
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)


def toilet_need(men: int, women: int, independent: int = 0) -> tuple[int, int, int, int]:
    """安衛則 628条・628条の2: (男性 大便所, 男性 小便所, 女性 便所, 差し引いた人数)。独立個室型は1つ×10人を男女から差し引く."""
    if men + women <= 10 and independent >= 1:
        return 0, 0, 0, men + women
    cut = 10 * independent
    m, w = max(0, men - cut), max(0, women - cut)
    return math.ceil(m / 60.0), math.ceil(m / 30.0), math.ceil(w / 20.0), cut


def check(site: Site) -> Site:
    c = site.checks = []
    total = site.staff + site.men + site.women
    # 建物ごと
    for h in site.houses:
        w, d, ht = h.size
        nm = f"{h.name}（{HOUSES[h.kind][0]}・{h.units}連棟×{h.tiers}段）"
        if h.tiers >= 2:
            ok = h.units >= 2 and h.tiers <= 2 and h.kind in STACKABLE
            c.append(Check(f"{h.name} 段積み", "OK" if ok else "WARN",
                           f"{nm}: 2段積みは1階を連棟に（三協 CT-J「1階が単体なら2階建て不可」）、3段は専用の架台。奥行 2,300 の型で"
                           + ("" if ok else "。メーカーに確かめる")))
            sk = STAIRS[h.stair_kind]
            st_ok = h.stair_width >= STAIR_W_MIN and h.corr_w >= CORR_W_MIN
            c.append(Check(f"{h.name} 階段・廊下", "OK" if st_ok else "NG",
                           f"外階段 {sk[0]}（幅 {sk[1]:.0f}×長さ {sk[2]:.0f}×高さ {sk[3]:.0f}・{sk[4]:.0f}kg"
                           + (f"、{h.tiers - 1}階分を踊り場でつなぐ" if h.tiers > 2 else "") + "。屋外の直通階段 90cm 以上・"
                           f"蹴上 22cm 以下・踏面 21cm 以上 令23条）、2階の外廊下 幅 "
                           f"{h.corr_w:.0f}・手すり {RAIL_H:.0f}（目安）。2階の床 {ht:.0f} は 4m 以下で踊場は要らない（令24条）"))
        v = h.wind_speed()
        mass, ww = (HOUSES[h.kind][4], HOUSES[h.kind][1]) if h.is_toilet else (h.mass, w)
        c.append(Check(f"{h.name} 転倒", "OK" if v >= WIND_MS else "WARN",
                       f"固定しないで転倒する風速 約 {v:.0f}m/s（{'1基 ' if h.is_toilet else ''}{mass:.0f}kg・長手 {ww / 1000:.2f}×高さ "
                       f"{ht * h.tiers / 1000:.2f}m・"
                       f"奥行 {d / 1000:.2f}m・Cf {CF:g}）" + ("" if v >= WIND_MS else f" < {WIND_MS:.0f}m/s → アンカーかワイヤ＋ターンバックル・"
                                                                                        "ハウス用ウエイトで固定（目安）")))
    # 現場全体
    office = sum(h.area(1) for h in site.houses)
    rest = sum(h.area(2) + h.area(3) for h in site.houses)
    if site.staff:
        need = site.staff * OFFICE_M2
        c.append(Check("事務所の広さ", "OK" if office >= need else "WARN",
                       f"事務所 {office:.1f}㎡ ≧ 職員 {site.staff}人×{OFFICE_M2:g}㎡＝{need:.0f}㎡（施工者 8〜10㎡/人。仮設構造物計画の手引き）・"
                       "気積 10㎥/人・照度 300lx（事務所衛生基準規則）"))
    if site.men + site.women:
        need = (site.men + site.women) * REST_M2
        c.append(Check("詰所・休憩所", "OK" if rest >= need else "WARN",
                       f"詰所・休憩所 {rest:.1f}㎡ ≧ 作業員 {site.men + site.women}人×{REST_M2:g}㎡＝{need:.0f}㎡（法令の基準は無く目安。"
                       "休憩設備は安衛則 613条）"))
        ind = sum(h.toilets for h in site.houses)
        big, small, fem, cut = toilet_need(site.men + site.staff, site.women, ind)
        c.append(Check("便所の数", "OK" if ind >= big + small + fem else "WARN",
                       f"男性 {site.men + site.staff}人・女性 {site.women}人 → 男性の大便所 {big}・小便所 {small}・女性 {fem}（安衛則 628条。"
                       f"独立個室型 {ind}つで {cut}人を差し引いた 628条の2）。置いた個室 {ind}"
                       + ("" if ind >= big + small + fem else "。小便所・男女別の便所を足す")
                       + "。差し引いても男女別が原則（女性がいれば女性用を1つ以上）。洋式・施錠・男女表示・手洗い（国交省 快適トイレ）、"
                         "女性用は男性用・喫煙所と離して入口を分ける"))
        if total >= 50 or site.women >= 30:
            c.append(Check("休養室", "WARN", f"常時 {total}人（女性 {site.women}人）: 50人以上か女性 30人以上は男女別に臥床できる休養室"
                                             "（安衛則 618条）"))
    c.append(Check("熱中症", "OK", "WBGT 28度以上か気温 31度以上で1時間以上・1日4時間を超える作業は、報告の体制と手順を作り周知"
                                  "（安衛則 612条の2）。休憩所に冷房・飲料・WBGT 計"))
    area = sum(h.area() for h in site.houses)
    store = sum(h.area(6) for h in site.houses)
    c.append(Check("消火器", "OK" if office < 300 and store < 150 else "WARN",
                   f"事務所 {office:.0f}㎡・倉庫 {store:.0f}㎡（事務所 300㎡・倉庫 150㎡以上は消火器が義務 消防法施行令10条。それ未満も置く）"))
    c.append(Check("建築基準法", "OK" if not (site.fire_zone and area > 50.0) else "WARN",
                   f"工事現場の事務所・下小屋・材料置場は 85条2項（確認申請は不要、構造 20条は残る）。延べ {area:.0f}㎡"
                   + ("。防火・準防火地域で 50㎡を超えるので屋根は 62条" if site.fire_zone and area > 50.0 else "")
                   + "。床の積載 295kg/㎡（書庫・資材は分散）"))
    _quantity(site)
    return site


def _quantity(site: Site) -> None:
    q = site.quantity = []
    cnt: dict[int, int] = {}
    for h in site.houses:
        cnt[h.kind] = cnt.get(h.kind, 0) + h.units * h.tiers
    for k, n in sorted(cnt.items()):
        q.append((HOUSES[k][0], n, f"{HOUSES[k][1]:.0f}×{HOUSES[k][2]:.0f}・1基 {HOUSES[k][4]:.0f}kg"))
    st = sum(1 for h in site.houses if h.tiers >= 2)
    if st:
        for k in sorted({h.stair_kind for h in site.houses if h.tiers >= 2}):
            n_st = sum(h.tiers - 1 for h in site.houses if h.tiers >= 2 and h.stair_kind == k)
            nm, w, ln, hh, kg = STAIRS[k]
            q.append((f"{nm} {w:.0f}×{ln:.0f}×{hh:.0f}", n_st, f"基（{kg:.0f}kg）"))
        n_land = sum(h.tiers - 2 for h in site.houses if h.tiers >= 3)
        if n_land:
            q.append(("踊り場 SC（カナテック。3階への折り返し）", n_land, "基"))
        q.append(("2階の外廊下（手すり 1,100）", round(sum(h.size[0] for h in site.houses if h.tiers >= 2) / 1000.0, 1), "m"))
    q.append(("消火器", max(1, len(site.houses)), "本（1棟に1本の目安）"))


def part_params(h: House) -> dict:
    """部品 ashiba_house のパラメータ."""
    uses = list(h.uses) + [h.uses[-1]] * 3
    return {"hsType": h.kind, "nUnit": h.units, "nTier": h.tiers, "use1": uses[0], "use2": uses[1], "use3": uses[2],
            "stairSd": h.stair, "stairW": h.stair_width / 1000.0, "stairL": STAIRS[h.stair_kind][2] / 1000.0,
            "stName": STAIRS[h.stair_kind][0].split("（")[0], "corrW": h.corr_w / 1000.0, "hsName": h.name}


def house_from_params(ps: dict, name: str = "") -> House:
    uses = tuple(int(ps.get(f"use{i}") or 1) for i in (1, 2, 3))
    return House(name or str(ps.get("hsName") or "仮設建物"), int(ps.get("hsType") or 4), int(ps.get("nUnit") or 1),
                 int(ps.get("nTier") or 1), uses, int(ps.get("stairSd") or 0), float(ps.get("stairW") or 0.0) * 1000.0,
                 float(ps.get("corrW") or 1.0) * 1000.0)


def report(site: Site) -> str:
    out = ["# 仮設建物", "",
           "出典: ナガワ スーパーハウス・三協フロンテア CT-J・カナモト（仮設トイレ・快適トイレハウス）・国交省 快適トイレ・安衛則 613・618・"
           "628・628条の2・612条の2・事務所衛生基準規則・建築基準法 85条2項・令23・24・147条・消防法施行令10条・仮設構造物計画の手引き。"
           "広さ・転倒の風速は目安", "",
           f"- 人数: 職員 {site.staff}人・作業員 男性 {site.men}人・女性 {site.women}人", "",
           "| 建物 | 型 | 連棟×段 | 用途 | 床面積 |", "|---|---|---|---|---|"]
    for h in site.houses:
        us = "・".join(USES.get(u, "?") for u in list(h.uses)[: h.tiers])
        out.append(f"| {h.name} | {HOUSES[h.kind][0]} | {h.units}×{h.tiers} | {us} | {h.area():.1f}㎡ |")
    out += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"] + [f"| {x.item} | {x.status} | {x.message} |" for x in site.checks]
    out += ["", "| 品名 | 数 | 注 |", "|---|---|---|"] + [f"| {a} | {b:g} | {c} |" for a, b, c in site.quantity] + [""]
    return "\n".join(out)
