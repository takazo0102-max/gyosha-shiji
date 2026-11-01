"""重機（バックホウ・クローラクレーン・コンクリートポンプ車・生コン車・ダンプ・高所作業車・垂直昇降）（部品 ashiba_machine）.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。寸法はメーカーの仕様書・カタログの値（m・t・kN）、
【目安】は仕様書に無く、外形図や同じクラスの機種から決めた値（部品のパラメータで直せる）。出典は SOURCES。

判定は3つ: 地盤の許容支持力（短期 kN/m²）に対し、クローラ機は仕様書の接地圧、ポンプ車・高所作業車はジャッキ1本の反力を
敷板の面積で割った値（足りなければ要る面積と敷鉄板の枚数）。立入禁止は後端旋回半径（＋0.5m の余裕。目安）と作業半径。
運転の資格と作業計画の条文は、機種の区分（質量・作業床の高さ・つり上げ荷重）から引く。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

SOIL_Q = 100.0              # 地盤の許容支持力（短期）kN/m²（既定。地盤調査の値を --soil-q で）
JACK_PAD = 0.6 * 0.6        # ジャッキの下の敷板（樹脂の敷板 600 角。目安）m²
PLATE = ("厚板鋼板 NT22×5×10", 1.524, 3.048)   # 日建リース Vol.10 p394（crane.py と同じ）
KEEP_OUT = 0.5              # 立入禁止の余裕 m（後端旋回半径に足す。目安）

SOURCES = {
    "K1": "コマツ PC30UU/30UUC/38UU-6 カタログ p.23（kcsj.komatsu）",
    "K2": "コマツ PC78US-11 カタログ p.19（kcsj.komatsu）",
    "K3": "コマツ PC128US/138US-12 カタログ p.31（kcsj.komatsu）",
    "K4": "コマツ PC200/210-11 カタログ p.19（kcsj.komatsu）、ブーム長はコベルコ SK200-14 p.12",
    "C1": "コベルコ 7050G-2 仕様書 p.2・3・10・20・21（kobelco-kenki.co.jp）",
    "C2": "コベルコ 7090G-2 仕様書 p.2・3・8・28・29（kobelco-kenki.co.jp）",
    "C3": "コベルコ 7070G-2 仕様書 p.2（主要諸元）・p.3（全体図）・p.8（主ブーム定格総荷重表 25.4t ウエイト）（kobelco-kenki.co.jp）",
    "P1": "極東開発 PY120B-26D カタログ No.1559 p.1（kyokuto.com）",
    "P2": "極東開発 PY140-36A カタログ No.1478 p.1（kyokuto.com）",
    "M1": "三菱ふそう スーパーグレート ダンプ・ミキサ カタログ p.17・19",
    "M2": "三菱ふそう ファイター ダンプ・ミキサ 2022 p.19・22・23",
    "D1": "いすゞ ギガ ダンプ 6×4 主要諸元・外観図",
    "A1": "アイチ SH12C1RN カタログ p.14・車両寸法図（aichi-corp.co.jp）",
    "A3": "アイチ SV-E シリーズ カタログ p.12・14（aichi-corp.co.jp）",
}

KINDS = {1: "バックホウ", 2: "クローラクレーン", 3: "コンクリートポンプ車", 4: "生コン車", 5: "ダンプ", 6: "高所作業車",
         7: "垂直昇降（自走式）"}


@dataclass(frozen=True)
class Machine:
    key: str
    kind: int
    name: str                       # 平面の注記・帳票の名前
    model: str                      # メーカーと型式
    mass_t: float                   # 運転質量（トラックは車両総重量）
    params: dict                    # 部品のパラメータ（m・度）
    source: str                     # SOURCES のキー
    ground_kpa: Optional[float] = None          # クローラの接地圧（仕様書）
    jacks_kn: tuple = ()                        # ジャッキ1本の最大反力（組ごと）kN
    platform_m: float = 0.0                     # 作業床の最大の高さ（高所作業車・垂直昇降）
    lift_t: float = 0.0                         # つり上げ荷重（クレーン）
    turn_r: float = 0.0                         # 最小回転半径 m（トラック）
    rated: dict = field(default_factory=dict)   # クレーンの定格総荷重 {ブーム長: {半径: t}}
    guesses: str = ""                           # 【目安】の値


def _bh(trkL, gauge, shoe, trkH, upW, tailR, upZ, upH, cab, pvH, boomL, armL, bkL, bkW, maxR, maxD, pvX=0.15, upF=None):
    """バックホウのパラメータ（クローラ全幅＝ゲージ＋シュー幅）."""
    return {"trkL": trkL, "trkW": gauge + shoe, "shoeW": shoe, "trkH": trkH, "upW": upW, "tailR": tailR, "upZ": upZ, "upH": upH,
            "cabW": cab[0], "cabL": cab[1], "upF": upF if upF is not None else max(cab[1] - 0.2, upW * 0.55),
            "pvX": pvX, "pvH": pvH, "boomL": boomL, "armL": armL, "bkL": bkL, "bkW": bkW, "maxR": maxR, "maxD": maxD,
            "bmA": 35.0, "amA": -70.0, "bkA": -150.0, "cbS": 1}


def _truck(carL, carW, cabH, frOv, wb, nRear, rearSp, whR, frZ, carF=None, nFr=1, frSp=1.7):
    return {"carL": carL, "carW": carW, "cabH": cabH, "frOv": frOv, "wb": wb, "nRear": nRear, "rearSp": rearSp, "whR": whR,
            "frZ": frZ, "carF": carL / 2 if carF is None else carF, "nFr": nFr, "frSp": frSp}


MACHINES = {
    # バックホウ（コマツ。ブーム長・履帯の高さ・ブームの根元・バケットの寸法は【目安】）
    "bh01": Machine("bh01", 1, "バックホウ 0.1m³", "コマツ PC38UU-6（0.11m³・後方超小旋回）", 3.6,
                    _bh(2.105, 1.44, 0.30, 0.45, 1.70, 0.87, 0.55, 2.49, (0.85, 1.25), 0.85, 2.5, 1.3, 0.65, 0.55, 4.855, 3.23,
                        pvX=0.35),
                    "K1", ground_kpa=33.0, guesses="ブーム長 2.5・アーム長 1.3・履帯の高さ・ブームの根元・バケット"),
    "bh025": Machine("bh025", 1, "バックホウ 0.25m³", "コマツ PC78US-11（0.28m³・後方超小旋回）", 7.71,
                     _bh(2.84, 1.87, 0.45, 0.62, 2.32, 1.39, 0.75, 2.71, (0.95, 1.5), 1.25, 3.6, 1.65, 0.85, 0.7, 6.38, 4.10,
                         pvX=0.3),
                     "K2", ground_kpa=34.1, guesses="ブーム長 3.6・履帯の高さ・ブームの根元・バケット"),
    "bh045": Machine("bh045", 1, "バックホウ 0.45m³", "コマツ PC138US-12（0.53m³・後方超小旋回）", 13.8,
                     _bh(3.61, 1.99, 0.50, 0.75, 2.49, 1.49, 0.85, 2.85, (0.95, 1.6), 1.55, 4.6, 2.5, 1.05, 0.9, 8.30, 5.48,
                         pvX=0.3),
                     "K3", ground_kpa=42.7, guesses="ブーム長 4.6（同クラスの SK135SR-7 は 4.68）・履帯の高さ・ブームの根元・バケット"),
    "bh08": Machine("bh08", 1, "バックホウ 0.8m³", "コマツ PC200-11（0.8m³・標準）", 20.2,
                    _bh(4.07, 2.20, 0.60, 0.90, 2.71, 2.83, 1.07, 3.135, (1.0, 1.75), 1.9, 5.7, 2.9, 1.45, 1.05, 9.875, 6.62,
                        pvX=0.15, upF=1.6),
                    "K4", ground_kpa=46.2, guesses="ブーム長 5.7（SK200-14 は 5.65）・履帯の高さ・ブームの根元・バケット"),
    # クローラクレーン（コベルコ。ブームの幅とガントリの形は【目安】）
    "cc50": Machine("cc50", 2, "クローラクレーン 50t", "コベルコ 7050G-2（50t×3.8m）", 48.0,
                    {"trkL": 5.57, "trkW": 4.36, "shoeW": 0.76, "trkH": 0.985, "upW": 3.5, "tailR": 4.0, "upZ": 1.1,
                     "upH": 3.3, "cabW": 1.0, "cabL": 1.9, "upF": 2.0, "pvX": 1.1, "pvH": 1.75, "lbL": 30.5, "lbA": 70.0,
                     "lbW": 1.22, "hkD": 6.0, "cbS": -1, "maxR": 0.0},
                    "C1", ground_kpa=65.0, lift_t=50.0,
                    rated={21.3: {10: 11.6, 14: 7.3, 16: 6.1, 20: 4.4}, 30.5: {10: 11.4, 14: 7.1, 16: 5.8, 20: 4.1}},
                    guesses="ブームの幅 1.22・ガントリの形・上部旋回体の前端"),
    "cc70": Machine("cc70", 2, "クローラクレーン 70t", "コベルコ 7070G-2（70t×4.0m）", 76.0,
                    {"trkL": 5.975, "trkW": 4.83, "shoeW": 0.8, "trkH": 1.0, "upW": 3.5, "tailR": 4.3, "upZ": 1.1,
                     "upH": 3.31, "cabW": 1.0, "cabL": 1.9, "upF": 2.1, "pvX": 1.1, "pvH": 1.75, "lbL": 30.5, "lbA": 70.0,
                     "lbW": 1.37, "hkD": 6.0, "cbS": -1, "maxR": 0.0},
                    "C3", ground_kpa=91.0, lift_t=70.0,
                    rated={21.3: {10: 21.3, 14: 13.6, 16: 11.3, 20: 8.4}, 30.5: {10: 21.1, 14: 13.3, 16: 11.0, 20: 7.9}},
                    guesses="シュー幅 0.8・履帯の高さ・ブームの幅 1.37・ガントリの形・上部旋回体の前端"),
    "cc90": Machine("cc90", 2, "クローラクレーン 90t", "コベルコ 7090G-2（90t×4.3m）", 93.0,
                    {"trkL": 6.315, "trkW": 4.9, "shoeW": 0.9, "trkH": 1.05, "upW": 4.2, "tailR": 4.4, "upZ": 1.275,
                     "upH": 3.485, "cabW": 1.0, "cabL": 1.9, "upF": 2.2, "pvX": 1.1, "pvH": 2.2, "lbL": 29.1, "lbA": 70.0,
                     "lbW": 1.52, "hkD": 6.0, "cbS": -1, "maxR": 0.0},
                    "C2", ground_kpa=95.0, lift_t=90.0,
                    rated={23.0: {10: 26.5, 14: 16.9, 16: 14.1, 20: 10.5}, 29.1: {10: 26.3, 14: 16.6, 16: 13.9, 20: 10.3}},
                    guesses="履帯の高さ・ブームの幅 1.52・ガントリの形・上部旋回体の前端"),
    # コンクリートポンプ車（極東開発。軸距・旋回台の位置・ブームの根元の高さは【目安】）
    "pump26": Machine("pump26", 3, "ポンプ車 26m", "極東開発 PY120B-26D（4段屈折・最大地上高 25.7m）", 16.95,
                      {**_truck(9.46, 2.49, 3.0, 1.4, 5.0, 1, 1.3, 0.52, 1.05, carF=2.6),
                       "nSec": 4, "sL1": 6.2, "sL2": 5.4, "sL3": 5.4, "sL4": 4.7, "sL5": 0.0,
                       "pA1": 70.0, "pA2": 30.0, "pA3": -5.0, "pA4": -60.0, "pA5": -80.0, "tuH": 3.4,
                       "o1x": 2.6 - 1.51, "o1y": 5.43, "o2x": 2.6 - 4.86, "o2y": 5.43, "o3x": 2.6 - 7.46, "o3y": 2.3,
                       "maxR": 21.7},
                      "P1", jacks_kn=(127.0, 157.0, 78.0),
                      guesses="軸距 5.0・旋回台は前端から 2.6・ブームの根元の高さ"),
    "pump36": Machine("pump36", 3, "ポンプ車 36m", "極東開発 PY140-36A（4段屈折・最大地上高 35.6m）", 24.99,
                      {**_truck(11.94, 2.49, 3.0, 1.3, 5.6, 2, 1.3, 0.52, 1.05, carF=3.0, nFr=2, frSp=1.75),
                       "nSec": 4, "sL1": 8.8, "sL2": 7.35, "sL3": 7.35, "sL4": 8.6, "sL5": 0.0,
                       "pA1": 70.0, "pA2": 30.0, "pA3": -5.0, "pA4": -60.0, "pA5": -80.0, "tuH": 3.5,
                       "o1x": 3.0 - 0.74, "o1y": 7.6, "o2x": 3.0 - 8.54, "o2y": 7.8, "o3x": 3.0 - 11.61, "o3y": 1.3,
                       "maxR": 32.1},
                      "P2", jacks_kn=(200.0, 200.0, 78.0),
                      guesses="軸距・旋回台は前端から 3.0・ジャッキの前後の位置（設置図の並び）"),
    # 生コン車（三菱ふそう。前端から前の車軸・ドラムの外形は【目安】）
    "mix45": Machine("mix45", 4, "生コン車 4.5m³", "三菱ふそう スーパーグレート FV ミキサ（4.4/4.5m³・6×4）", 19.945,
                     {**_truck(7.925, 2.49, 3.1, 1.3, 3.26, 2, 1.31, 0.53, 1.05),
                      "drL": 4.2, "drD": 2.25, "drA": 16.0},
                     "M1", turn_r=6.8, guesses="前端から前の車軸・ドラムの外形（内法 φ2,100×3,530 から）"),
    "mix32": Machine("mix32", 4, "生コン車 3.2m³", "三菱ふそう ファイター FK7-Z ミキサ（3.2m³）", 14.0,
                     {**_truck(6.33, 2.30, 2.75, 1.2, 3.19, 1, 1.3, 0.47, 1.0),
                      "drL": 3.6, "drD": 2.0, "drA": 16.0},
                     "M2", turn_r=5.8, guesses="前端から前の車軸・ドラムの寸法（φ1,900×3,000 前後）"),
    # ダンプ（荷台の床の高さから frZ を決める）
    "dump10": Machine("dump10", 5, "ダンプ 10t", "いすゞ ギガ 6×4（強化角底一方開・最大積載 9,100kg）", 19.96,
                      {**_truck(7.64, 2.49, 3.05, 1.3, 3.225, 2, 1.31, 0.53, 1.45),
                       "bedL": 5.1, "bedW": 2.2, "bedH": 0.52, "bedA": 0.0},
                      "D1", turn_r=6.6, guesses="前端から前の車軸・運転室の高さ"),
    "dump4": Machine("dump4", 5, "ダンプ 4t", "三菱ふそう ファイター FK7（強化一方開・最大積載 3,750kg）", 7.965,
                     {**_truck(5.395, 2.19, 2.5, 1.15, 2.91, 1, 1.3, 0.42, 0.95),
                      "bedL": 3.4, "bedW": 2.06, "bedH": 0.34, "bedA": 0.0},
                     "M2", turn_r=4.8, guesses="前端から前の車軸・運転室の高さ"),
    # 高所作業車（アイチ。旋回台・ジャッキの前後の位置・ブームの根元の高さは【目安】）
    "aw12": Machine("aw12", 6, "高所作業車 12m", "アイチ SH12C1RN（作業床 12.1m・後方格納の伸縮ブーム）", 4.5,
                    {**_truck(5.14, 1.91, 2.2, 1.035, 2.475, 1, 1.3, 0.36, 0.85, carF=4.24),
                     "nSec": 3, "abL": 9.4, "abA": 60.0, "tuH": 2.3, "pfL": 1.0, "pfW": 0.7,
                     "o1x": 4.24 - 1.9, "o1y": 1.9, "o2x": -0.5, "o2y": 1.7, "o3x": 0.0, "o3y": 0.0, "maxR": 9.9},
                    "A1", jacks_kn=(44.1, 44.1), platform_m=12.1,
                    guesses="車両総重量（2t 車級の目安 4.5t）・旋回台とジャッキの前後の位置・ブームの根元の高さ"),
    "sv06": Machine("sv06", 7, "垂直昇降 5.7m", "アイチ SV06E1NS（自走式シザース・作業床 5.72m）", 1.2,
                    {"carL": 1.87, "carW": 0.76, "carF": 0.935, "whR": 0.15, "pfL": 1.77, "pfW": 0.68, "pfH": 3.0,
                     "maxR": 0.0},
                    "A3", platform_m=5.72),
}


@dataclass
class Check:
    item: str
    status: str
    detail: str


@dataclass
class Placed:
    name: str
    machine: Machine
    slew: float = 0.0
    params: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)


def find(key: str) -> Machine:
    """機種のキー（bh045 など）か名前の一部 → 機種."""
    if key in MACHINES:
        return MACHINES[key]
    hits = [m for m in MACHINES.values() if key and (key in m.name or key in m.model)]
    if len(hits) == 1:
        return hits[0]
    raise KeyError(f"機種は {'・'.join(MACHINES)} のどれか（{key}）")


def model_code(key: str) -> int:
    """部品の mcModel の番号（MACHINES の並び順の 1 から）."""
    return list(MACHINES).index(key) + 1


def license_for(m: Machine) -> str:
    """運転・操作に要る資格（安衛令・安衛則・クレーン則）."""
    if m.kind == 1:
        if m.mass_t >= 3.0:
            return "車両系建設機械（整地・運搬・積込み用及び掘削用）運転技能講習（安衛則41条）"
        return "車両系建設機械（整地等）の特別教育（安衛則36条9号）"
    if m.kind == 2:
        lic = "移動式クレーン運転士免許（クレーン則68条）" if m.lift_t >= 5 else "小型移動式クレーン運転技能講習（クレーン則68条）"
        return lic + "・玉掛け技能講習（クレーン則221条）"
    if m.kind == 3:
        return "コンクリート打設用機械の作業装置の操作の特別教育（安衛則36条10号の2）・大型免許"
    if m.kind in (4, 5):
        return "大型免許" if m.mass_t > 11.0 else "中型免許"
    if m.kind in (6, 7):
        return ("高所作業車運転技能講習（安衛令20条15号）" if m.platform_m >= 10 else "高所作業車の特別教育（安衛則36条10号の5）")
    return ""


def plan_rule(m: Machine) -> str:
    """作業計画の条文."""
    return {1: "車両系建設機械の作業計画（安衛則155条）", 2: "移動式クレーンの作業の方法等（クレーン則66条の2）",
            3: "車両系建設機械の作業計画（安衛則155条）", 4: "車両系荷役運搬機械等の作業計画（安衛則151条の3）",
            5: "車両系荷役運搬機械等の作業計画（安衛則151条の3）", 6: "高所作業車の作業計画（安衛則194条の9）",
            7: "高所作業車の作業計画（安衛則194条の9）"}[m.kind]


def rated_at(m: Machine, boom: float, radius: float) -> Optional[float]:
    """クレーンの定格総荷重 t（ブームはその長さ以上の列・半径はその半径以上の行。表の外は None）."""
    booms = sorted(b for b in m.rated if b >= boom - 1e-6)
    if not booms:
        return None
    rows = m.rated[booms[0]]
    rs = sorted(r for r in rows if r >= radius - 1e-6)
    return rows[rs[0]] if rs else None


def plates_for(reaction_kn: float, soil_q: float) -> tuple[float, int]:
    """ジャッキ1本の反力 → 要る面積 m² と、敷鉄板 1.524×3.048 を何枚（0＝敷板 600 角で足りる）."""
    need = reaction_kn / soil_q
    if need <= JACK_PAD:
        return need, 0
    return need, 1 if need <= PLATE[1] * PLATE[2] else 2


def check(p: Placed, soil_q: float = SOIL_Q) -> Placed:
    m = p.machine
    p.checks = []
    if m.ground_kpa:
        ok = m.ground_kpa <= soil_q
        p.checks.append(Check("接地圧", "OK" if ok else "要確認",
                              f"接地圧 {m.ground_kpa:.1f} kPa ／ 地盤 {soil_q:.0f} kN/m²" + ("" if ok else "（敷鉄板・地盤改良）")))
    for i, r in enumerate(m.jacks_kn, 1):
        need, n = plates_for(r, soil_q)
        p.checks.append(Check(f"ジャッキ{i}の下", "OK" if n == 0 else "要敷鉄板",
                              f"反力 {r:.0f} kN ÷ {soil_q:.0f} ＝ {need:.2f} m²" + ("（敷板 600 角で可）" if n == 0
                                                                              else f"→ {PLATE[0]} {n}枚")))
    if m.kind == 2:
        ps = {**m.params, **p.params}
        boom, ang = float(ps["lbL"]), float(ps["lbA"])
        rad = float(ps["pvX"]) + boom * math.cos(math.radians(ang)) + 0.4
        t = rated_at(m, boom, rad)
        p.checks.append(Check("定格総荷重", "OK" if t is not None else "要確認",
                              f"ブーム {boom:.1f}m・半径 {rad:.1f}m → " + (f"{t:.1f}t（フック・玉掛具込み）" if t is not None
                                                                         else "表の外（仕様書の定格総荷重表で確認）")))
    tail = float({**m.params, **p.params}.get("tailR", 0) or 0)
    if tail > 0:
        p.checks.append(Check("立入禁止", "注意", f"後端旋回半径 {tail:.2f}m ＋{KEEP_OUT}m（R{tail + KEEP_OUT:.2f}m）"))
    return p


def part_params(p: Placed) -> dict:
    """部品 ashiba_machine のパラメータ."""
    m = p.machine
    ps = {**m.params, **p.params}
    note = f"{m.model.split('（')[0]} {m.mass_t:g}t"
    if m.platform_m:
        note += f"・作業床 {m.platform_m:g}m"
    name = f"{p.name} {m.name}" if p.name else m.name
    return {"mcKind": m.kind, "mcModel": model_code(m.key), "mcName": name, "mcNote": note, "slew": p.slew, **ps}


def report(placed: list[Placed], soil_q: float = SOIL_Q) -> str:
    lines = ["# 重機の手配と判定", "", f"地盤の許容支持力（短期）{soil_q:.0f} kN/m²。", "",
             "| 名前 | 機種 | 型式 | 質量 t | 運転の資格 | 作業計画 |", "|---|---|---|---|---|---|"]
    for p in placed:
        m = p.machine
        lines.append(f"| {p.name} | {m.name} | {m.model} | {m.mass_t:g} | {license_for(m)} | {plan_rule(m)} |")
    lines += ["", "## 判定", "", "| 名前 | 項目 | 結果 | 内容 |", "|---|---|---|---|"]
    for p in placed:
        for c in p.checks:
            lines.append(f"| {p.name} | {c.item} | {c.status} | {c.detail} |")
    lines += ["", "## 出典と目安", ""]
    for p in placed:
        m = p.machine
        lines.append(f"- {m.name}（{m.model}）: {SOURCES[m.source]}" + (f"。【目安】{m.guesses}" if m.guesses else ""))
    return "\n".join(lines) + "\n"
