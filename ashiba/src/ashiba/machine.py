"""重機（バックホウ・クローラクレーン・コンクリートポンプ車・生コン車・ダンプ・高所作業車・垂直昇降）（部品 ashiba_machine）.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。寸法はメーカーの仕様書・カタログの値（m・t・kN）、
【目安】は仕様書に無く、外形図や同じクラスの機種から決めた値（部品のパラメータで直せる）。出典は SOURCES、調べたメモは
docs/調査_重機*.md（バックホウ・クローラクレーン・トラック系・法令と敷鉄板）。

判定（しっかり調べ直した根拠は帳票に）:
- 敷鉄板: 日本クレーン協会「作業現場における移動式クレーンの地盤対策について」の表3（トラッククレーン等のアウトリガー1脚に
  必要な鉄板等の目安。脚荷重 100〜1,000kN×土質）と表4（クローラクレーンに必要な鉄板の枚数。最大接地圧×土質）の鉄板厚 22mm の行
  （出典は日本建設機械化協会「移動式クレーン、杭打機等の支持地盤養生マニュアル」）。ポンプ車・高所作業車のジャッキは表3を準用
  （両者向けの公的な表は見つからない）。クローラは仕様書の平均接地圧（つり荷なし）で引くので下限で、最大接地圧はメーカーに確認。
  20t を超える移動式クレーンは設置地盤の調査（労働安全衛生総合研究所 NIIS-SD-No.22 p.87〜88）。
- 運転の資格: バックホウの 3t は機体重量（作業装置を除いた乾燥質量。安衛令20条12号・安衛則36条9号、厚労省テキスト p.10）で、
  カタログの機体質量で分ける。公道は道路交通法施行規則2条の車両総重量・最大積載量。
- 立入禁止（安衛則158条・クレーン則74条・74条の2・安衛則171条の2・151条の7・537条）。余裕 KEEP_OUT は公的な数値が無いので社内の決め。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

SOIL_Q = 100.0              # 地盤の許容支持力（短期）kN/m²（既定は軟らかい粘性土の下限。地盤調査の値を --soil-q で）
PLATE = ("厚板鋼板 NT22×5×10", 1.524, 3.048)   # 日建リース Vol.10 p394（crane.py と同じ）
KEEP_OUT = 0.5              # 立入禁止の余裕 m（旋回半径に足す。公的な数値は無く社内の決め。--keep-out で変える）

# 土質（日本クレーン協会 表2〜4。短期許容支持力 kN/m²）
SOILS = {1: ("柔らかい粘性土", "2＜N≦6", "100〜300"), 2: ("緩い砂質土", "4＜N≦10", "80〜200"),
         3: ("中位の硬さの粘性土", "6＜N≦8", "300〜400"), 4: ("中位に締まった砂質土", "10＜N≦40", "200〜800"),
         5: ("硬い粘性土", "N＞8", "400〜600"), 6: ("締まった砂質土", "N＞40", "800"),
         7: ("ローム 軟質", "N＜3", "100"), 8: ("ローム 硬質", "N≧3", "150")}
# 表3（鉄板厚 22mm）: 脚荷重 100・200…1,000kN の欄。"S"＝0.6×0.6m（厚さ7cmの敷板）、"A"＝1.2×1.2m 敷鉄板、
# "B"＝6.0×1.5m（敷鉄板2枚）、"-"＝敷鉄板では対応できない（他の支持地盤養生）
OUTRIG_TABLE = {1: "ABBB------", 2: "BBB-------", 3: "SAABBBBBBB", 4: "AABBBBBB--", 5: "SAAABBBBBB",
                6: "SSAAAAAAAA", 7: "ABBB------", 8: "ABBBBB----"}
# 表4（鉄板厚 22mm）: クローラの最大接地圧 100・150…600kN/m² の欄。数＝6.0×1.5m の敷鉄板の枚数、"-"＝対応できない
CRAWLER_TABLE = {1: "0122-------", 2: "1222-------", 3: "00000111122", 4: "0001122222-",
                 5: "00000001111", 6: "00000000000", 7: "0122-------", 8: "0012222----"}
PAD_TEXT = {"S": "0.6×0.6m（厚さ7cmの敷板）", "A": "1.2×1.2m の敷鉄板（NT22 1枚で覆う）",
            "B": "6.0×1.5m（敷鉄板2枚。NT22 2枚を縦に）", "-": "敷鉄板では対応できない（地盤改良など他の養生）"}

SOURCES = {
    "K1": "コマツ PC30UU/30UUC/38UU-6 カタログ p.23（kcsj.komatsu）",
    "K2": "コマツ PC78US-11 カタログ p.19（kcsj.komatsu）、ブーム長 3,710 は Komatsu America PC78US-11 ブローシャ p.16〜18（作業範囲が国内と一致）",
    "K3": "コマツ PC128US/138US-12 カタログ p.31（kcsj.komatsu）、ブーム長 4,600 は Komatsu Australia PC138USLC-11 p.15・16・Komatsu Europe PC138US-11 p.15・16（作業範囲が国内 -12 と一致）",
    "K4": "コマツ PC200/210-11 カタログ p.19（kcsj.komatsu）、ブーム長 5,700 は Komatsu America PC210LCi-11 p.20〜22（作業範囲が国内と一致）",
    "C1": "コベルコ 7050G-2 仕様書 p.2・3・10（主ブーム定格総荷重表）・20〜24（分解寸法・ブーム・フック）（kobelco-kenki.co.jp）",
    "C2": "コベルコ 7090G-2 仕様書 p.2・3・8（主ブーム定格総荷重表）・28〜35（分解寸法・ブーム・フック）（kobelco-kenki.co.jp）",
    "C3": "コベルコ 7070G-2 仕様書 p.2（主要諸元）・p.3（全体図）・p.8（主ブーム定格総荷重表 25.4t ウエイト）・p.33〜39（分解寸法・フック）（kobelco-kenki.co.jp）",
    "H1": "日立住友 SCX550-3 仕様書 JA224-2a p.6・7（仕様・寸法図）・Sp_SCX550-3_2511E p.7（上部旋回体の前端・ガントリを測った寸法図）・p.20（主ブーム定格総荷重表）・p.62〜64（分解寸法）（hsc-cranes.com）",
    "H2": "日立住友 SCX900-3 仕様書 JA262-2a p.6・7（仕様・寸法図）・Sp_SCX900-3C6_2606E p.7（キャブ前面・ガントリを測った寸法図）・p.14（主ブーム定格総荷重表）・p.67〜73（分解寸法・フック）（hsc-cranes.com）",
    "P1": "極東開発 PY120B-26D カタログ No.1559 p.1（主要諸元・外観図・設置寸法・作業範囲図）、ホイールベース 5,000 は同社 2020-11-18 ニュースリリース p.1・2（kyokuto.com）",
    "P2": "極東開発 PY140-36A カタログ No.1478 p.1（主要諸元・外観図・設置寸法・作業範囲図）（kyokuto.com）、シャシはベストカーWeb の記事",
    "U1": "UD トラックス Quon Dump・Mixer 主要諸元表 2025.3（K140D⑥）p.4〜6 ミキサー主要諸元 CW 6×4・寸法図 No.2（udtrucks.co.za/sites/default/files/2025-03/Quon_Dump_Spec.pdf）",
    "M2": "三菱ふそう ファイター ダンプ・ミキサ 2022 p.19・22・23、KYB ミキサ総合カタログ p.1（MR32 外形図）、UD コンドル ダンプ主要諸元表 p.5（参考）",
    "D1": "いすゞ ギガ ダンプ 6×4 主要諸元・車両外観図 p.1（isuzu.co.jp）、運転室の高さはギガ 03shogen.pdf p.1 のカーゴ前二軸・標準ルーフの全高",
    "A1": "アイチ SH12C1RN カタログ p.14・車両寸法図・作業範囲図・主要諸元（画像）・製品頁の必要運転免許（aichi-corp.co.jp）",
    "A3": "アイチ SV-E シリーズ カタログ p.12・14（aichi-corp.co.jp）",
    "T3": "タダノ AT-170TG リーフレット（2026-03、英語・メートル）p.2 主要諸元・作業範囲図・寸法図（mediahub.tadano.com、タダノ アジアの製品一覧から）",
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
    body_t: float = 0.0                         # 機体質量（バックホウ。作業装置を除いた乾燥質量＝資格の 3t の境）
    payload_t: float = 0.0                      # 最大積載量（トラック。公道の免許の区分）
    road: str = ""                              # 公道の免許（質量が分からずメーカーが免許を示すとき）
    turn_r: float = 0.0                         # 最小回転半径 m（トラック）
    rated: dict = field(default_factory=dict)   # クレーンの定格総荷重 {ブーム長: {半径: t}}
    guesses: str = ""                           # 【目安】の値


def _bh(trkL, gauge, shoe, trkH, upW, tailR, upZ, upH, cab, pvH, boomL, armL, bkL, bkW, maxR, maxD, pvX=0.15, upF=None,
        blade=(0.0, 0.45), bmY=0.0):
    """バックホウのパラメータ（クローラ全幅＝ゲージ＋シュー幅。排土板は 幅・高さ、幅 0 は無し）."""
    return {"trkL": trkL, "trkW": round(gauge + shoe, 3), "shoeW": shoe, "trkH": trkH, "upW": upW, "tailR": tailR, "upZ": upZ,
            "upH": upH, "bldW": blade[0], "bldH": blade[1],
            "cabW": cab[0], "cabL": cab[1], "upF": upF if upF is not None else max(cab[1] - 0.2, upW * 0.55),
            "pvX": pvX, "pvH": pvH, "boomL": boomL, "armL": armL, "bkL": bkL, "bkW": bkW, "maxR": maxR, "maxD": maxD,
            "bmA": 35.0, "amA": -70.0, "bkA": -150.0, "cbS": 1, "bmY": bmY}


def _cc(trkL, trkW, shoe, trkH, upW, cwW, tailR, upZ, upH, cabW, pvX, pvH, lbW, lbL, gantry, hook, upF, cwH, cabL=2.0):
    """クローラクレーンのパラメータ（全幅は張出時、upW は上部旋回体・cwW はカウンタウエイトの幅、gantry は頂部の
    （旋回中心から後ろ, 高さ）、hook はフックの（全高, 幅, 厚み））."""
    return {"trkL": trkL, "trkW": trkW, "shoeW": shoe, "trkH": trkH, "upW": upW, "cwW": cwW, "tailR": tailR, "upZ": upZ,
            "upH": upH, "cabW": cabW, "cabL": cabL, "upF": upF, "pvX": pvX, "pvH": pvH, "lbL": lbL, "lbA": 70.0,
            "lbW": lbW, "cwH": cwH, "hkD": 6.0, "gnX": gantry[0], "gnH": gantry[1], "hkH": hook[0], "hkW": hook[1], "hkT": hook[2],
            "cbS": -1, "maxR": 0.0}


def _rt(booms: tuple, text: str) -> dict:
    """定格総荷重表（行「半径: 列ごとの t」、「-」は欄なし、「a/b」は半径 b m が限り（行の半径より小さければ最大、
    大きければ最小の作業半径））→ {ブーム長: {行の半径: t か (t, 限りの半径)}}."""
    out = {b: {} for b in booms}
    for line in text.strip().splitlines():
        r, cells = line.split(":")
        for b, c in zip(booms, cells.split()):
            if c == "-":
                continue
            if "/" in c:
                t, lim = c.split("/")
                out[b][float(r)] = (float(t), float(lim))
            else:
                out[b][float(r)] = float(c)
    return out


def _truck(carL, carW, cabH, frOv, wb, nRear, rearSp, whR, frZ, carF=None, nFr=1, frSp=1.7):
    return {"carL": carL, "carW": carW, "cabH": cabH, "frOv": frOv, "wb": wb, "nRear": nRear, "rearSp": rearSp, "whR": whR,
            "frZ": frZ, "carF": carL / 2 if carF is None else carF, "nFr": nFr, "frSp": frSp}


MACHINES = {
    # バックホウ（コマツ。ブーム長・履帯の高さ・ブームの根元・バケットの寸法は【目安】）
    "bh01": Machine("bh01", 1, "バックホウ 0.1m³", "コマツ PC38UU-6（0.11m³・後方超小旋回・キャノピ）", 3.6,
                    _bh(2.105, 1.44, 0.30, 0.475, 1.54, 0.87, 0.545, 2.49, (0.935, 1.10), 0.85, 2.5, 1.3, 0.65, 0.60, 4.855, 3.23,
                        pvX=0.35, upF=0.58, blade=(1.77, 0.37)),
                    "K1", ground_kpa=33.0, body_t=2.68,
                    guesses="ブーム長 2.5・アーム長 1.3（2ピースのオフセットブームで海外版の資料が無い）・ブームの根元・バケットの長さ"
                            "（どの資料にも無い）、履帯の高さ 0.475・運転室 0.935×1.10・前端 0.58 は外形図を測った値"),
    "bh025": Machine("bh025", 1, "バックホウ 0.25m³", "コマツ PC78US-11（0.28m³・後方超小旋回）", 7.71,
                     _bh(2.84, 1.87, 0.45, 0.63, 2.33, 1.39, 0.735, 2.71, (1.03, 1.47), 1.25, 3.71, 1.65, 0.85, 0.75, 6.38, 4.10,
                         pvX=0.3, upF=0.74, blade=(2.32, 0.49), bmY=-0.12),
                     "K2", ground_kpa=34.1, body_t=5.97,
                     guesses="ブームの根元・バケットの長さ（どの資料にも無い）、履帯の高さ 0.63・運転室 1.03×1.47・前端 0.74 は外形図を測った値"),
    "bh045": Machine("bh045", 1, "バックホウ 0.45m³", "コマツ PC138US-12（0.53m³・後方超小旋回）", 13.8,
                     _bh(3.61, 1.99, 0.50, 0.755, 2.50, 1.49, 0.90, 2.81, (1.07, 1.67), 1.55, 4.6, 2.5, 1.05, 0.979, 8.30, 5.48,
                         pvX=0.3, upF=1.105, blade=(0.0, 0.59), bmY=-0.222),
                     "K3", ground_kpa=42.7, body_t=11.3,
                     guesses="ブームの根元・バケットの長さ（どの資料にも無い）、履帯の高さ 0.755・運転室 1.07×1.67 は外形図を測った値。"
                             "排土板は国内 -12 ではオプション（欧州 -11 は 2,490×590）"),
    "bh08": Machine("bh08", 1, "バックホウ 0.8m³", "コマツ PC200-11（0.8m³・標準）", 20.2,
                    _bh(4.07, 2.20, 0.60, 0.88, 2.705, 2.83, 1.085, 3.045, (1.0, 1.84), 1.9, 5.7, 2.9, 1.45, 1.17, 9.875, 6.62,
                        pvX=0.15, upF=1.2),
                    "K4", ground_kpa=46.2, body_t=15.7,
                    guesses="ブームの根元・バケットの長さ（どの資料にも無い）、履帯の高さ 0.88・運転室 1.0×1.84・前端 1.2 は外形図を測った値"),
    # クローラクレーン（コベルコ。ブームの幅とガントリの形は【目安】）
    # クローラクレーン（コベルコ・日立住友の仕様書。定格表は主ブーム・標準ウエイト・クローラ張出。上部旋回体の前端とキャブの
    # 長さは寸法線が無く全体図の縮尺で測った値）
    "cc50": Machine("cc50", 2, "クローラクレーン 50t", "コベルコ 7050G-2（50t×3.8m）", 48.0,
                    _cc(5.57, 4.36, 0.76, 0.985, 2.99, 3.5, 4.0, 1.1, 3.3, 0.94, 1.1, 1.75, 1.355, 30.5,
                        gantry=(3.16, 6.145), hook=(1.47, 0.59, 0.435), upF=2.45, cwH=2.15),
                    "C1", ground_kpa=65.0, lift_t=50.0,
                    rated=_rt((15.2, 21.3, 30.5, 39.6, 51.8), """
                        6: 24.2 24.1 19.8/6.8 - -
                        8: 16.0 15.8 15.7 14.4/8.4 -
                        10: 11.8 11.6 11.4 11.2 9.2/10.5
                        12: 9.2 9.0 8.9 8.6 8.3
                        14: 7.5 7.3 7.1 6.8 6.5
                        16: 7.2/14.4 6.1 5.9 5.6 5.3
                        20: - 4.6/19.7 4.2 3.9 3.6
                        24: - - 3.2 2.9 2.5
                        28: - - 2.5/27.6 2.1 1.7"""),
                    guesses="上部旋回体の前端 2.45・キャブの長さ（全体図の縮尺で測った値）"),
    "cc70": Machine("cc70", 2, "クローラクレーン 70t", "コベルコ 7070G-2（70t×4.0m）", 76.0,
                    _cc(5.975, 4.83, 0.8, 0.99, 2.99, 3.5, 4.3, 1.1, 3.31, 0.94, 1.1, 1.75, 1.51, 30.5,
                        gantry=(3.16, 6.17), hook=(1.705, 0.6, 0.535), upF=2.4, cwH=1.985, cabL=2.1),
                    "C3", ground_kpa=91.0, lift_t=70.0,
                    rated=_rt((15.2, 21.3, 30.5, 39.6, 54.9), """
                        6: 44.9 44.7 35.0/6.8 - -
                        8: 29.3 29.1 28.9 26.8/8.4 -
                        10: 21.6 21.3 21.1 20.8 14.0/11.0
                        12: 16.9 16.7 16.4 16.1 14.0
                        14: 13.8 13.6 13.3 13.0 12.3
                        16: 13.2/14.5 11.3 11.0 10.7 10.1
                        20: - 8.5/19.8 8.1 7.8 7.1
                        24: - - 6.2 5.9 5.3
                        28: - - 5.0/27.7 4.6 4.0"""),
                    guesses="上部旋回体の前端 2.4・キャブの長さ 2.1（全体図の縮尺で測った値）"),
    "cc90": Machine("cc90", 2, "クローラクレーン 90t", "コベルコ 7090G-2（90t×4.3m）", 93.0,
                    _cc(6.315, 4.9, 0.9, 1.145, 2.99, 4.2, 4.4, 1.275, 3.485, 0.94, 1.1, 2.2, 1.68, 29.1,
                        gantry=(3.36, 6.95), hook=(1.87, 0.7, 0.49), upF=2.4, cwH=2.335),
                    "C2", ground_kpa=95.0, lift_t=90.0,
                    rated=_rt((19.9, 23.0, 29.1, 41.2, 62.6), """
                        6: 55.0 54.9 50.2/6.4 - -
                        8: 36.3 36.2 36.1 32.5/8.5 -
                        10: 26.6 26.5 26.3 26.0 -
                        12: 20.8 20.7 20.5 20.1 18.0/12.2
                        14: 16.9 16.9 16.6 16.2 15.4
                        16: 14.2 14.1 13.9 13.5 12.6
                        20: 11.8/18.5 10.5 10.3 9.8 8.9
                        24: - - 8.0 7.5 6.6
                        28: - - 7.0/26.4 5.9 4.9
                        32: - - - 4.8 3.8"""),
                    guesses="上部旋回体の前端 2.4・キャブの長さ（全体図の縮尺で測った値）"),
    "cc55h": Machine("cc55h", 2, "クローラクレーン 55t（日立住友）", "日立住友 SCX550-3（55t×3.7m）", 53.4,
                     _cc(5.55, 4.36, 0.76, 0.98, 3.2, 3.2, 3.85, 1.11, 3.23, 0.95, 1.0, 1.595, 1.38, 31.0,
                         gantry=(3.0, 5.33), hook=(1.67, 0.62, 0.55), upF=2.2, cwH=1.97),
                     "H1", ground_kpa=73.1, lift_t=55.0,
                     rated=_rt((13.0, 19.0, 31.0, 40.0, 52.0), """
                        4: 51.0 - - - -
                        6: 27.25 27.15 20.5/7.3 - -
                        8: 18.3 18.2 17.95 - -
                        10: 13.7 13.5 13.25 13.0 9.0/11.3
                        12: 10.7 10.65 10.4 10.1 8.85
                        14: 9.9/12.4 8.75 8.45 8.15 7.85
                        16: - 7.35 7.05 6.75 6.45
                        20: - 6.5/17.6 5.15 4.9 4.55
                        24: - - 4.0 3.7 3.35
                        28: - - 3.15 2.85 2.45"""),
                     guesses="上部旋回体の前端 2.2・キャブの幅 0.95・ガントリの前後の位置 3.0 は Sp_SCX550-3_2511E p.7 の寸法図を 5,550・4,710・3,200 の"
                             "寸法線で測った値"),
    "cc90h": Machine("cc90h", 2, "クローラクレーン 90t（日立住友）", "日立住友 SCX900-3（90t×4.0m）", 94.0,
                     _cc(6.295, 4.99, 0.81, 1.11, 2.99, 4.15, 4.3, 1.365, 3.4, 0.95, 1.2, 2.11, 1.66, 30.0,
                         gantry=(3.45, 6.545), hook=(2.12, 0.82, 0.6), upF=2.7, cwH=1.94),
                     "H2", ground_kpa=106.0, lift_t=90.0,
                     rated=_rt((12.0, 18.0, 30.0, 39.0, 60.0), """
                        5: 74.75 74.4 - - -
                        6: 58.85 58.85 44.25/7.2 - -
                        8: 38.25 38.15 37.85 32.8/8.8 -
                        10: 28.1 27.95 27.55 27.3 -
                        12: 22.55/11.8 21.85 21.45 21.15 16.45/12.7
                        14: - 17.8 17.35 17.05 16.0
                        16: - 14.9 14.45 14.15 13.3
                        20: - 13.8/17.0 10.6 10.25 9.35
                        24: - - 8.15 7.8 6.85
                        28: - - 6.75/27.4 6.1 5.15
                        32: - - - 4.9 3.9"""),
                     guesses="上部旋回体（キャブ前面）の前端 2.7・ガントリの前後の位置 3.45・キャブ上面の高さ 3.4 は Sp_SCX900-3C6_2606E p.7 の寸法図を"
                             "5,375・R4300・4,150 の寸法線で測った値（2026-11-02 に測り直した）"),
    # コンクリートポンプ車（極東開発。軸距・旋回台の位置・ブームの根元の高さは【目安】）
    "pump26": Machine("pump26", 3, "ポンプ車 26m", "極東開発 PY120B-26D（4段屈折・最大地上高 25.7m）", 16.95,
                      {**_truck(9.46, 2.49, 3.0, 1.415, 5.0, 1, 1.3, 0.525, 1.05, carF=2.8),
                       "nSec": 4, "sL1": 6.2, "sL2": 5.4, "sL3": 5.4, "sL4": 4.7, "sL5": 0.0,
                       "pA1": 70.0, "pA2": 30.0, "pA3": -5.0, "pA4": -60.0, "pA5": -80.0, "tuH": 4.0,
                       "o1x": 2.8 - 1.51, "o1y": 5.43, "o2x": 2.8 - 4.86, "o2y": 5.43, "o3x": 2.8 - 7.46, "o3y": 2.3,
                       "maxR": 21.7},
                      "P1", jacks_kn=(127.0, 157.0, 78.0),
                      guesses="前端から前の車軸 1.415・旋回中心 2.8・タイヤの半径は外観図を測った値、運転室の高さ（資料に無い）"),
    "pump36": Machine("pump36", 3, "ポンプ車 36m", "極東開発 PY140-36A（日野プロフィア FW1AHG 8×4・4段屈折・最大地上高 35.6m）", 24.99,
                      {**_truck(11.94, 2.49, 3.0, 1.40, 5.86, 2, 1.19, 0.445, 1.05, carF=2.8, nFr=2, frSp=1.74),
                       "nSec": 4, "sL1": 8.8, "sL2": 7.35, "sL3": 7.35, "sL4": 8.6, "sL5": 0.0,
                       "pA1": 70.0, "pA2": 30.0, "pA3": -5.0, "pA4": -60.0, "pA5": -80.0, "tuH": 3.5,
                       "o1x": 2.8 - 0.74, "o1y": 7.6, "o2x": 2.8 - 8.54, "o2y": 7.8, "o3x": 2.8 - 9.63, "o3y": 1.3,
                       "maxR": 32.1},
                      "P2", jacks_kn=(200.0, 200.0, 78.0),
                      guesses="4本の車軸の位置・旋回中心 2.8・タイヤの半径は外観図を測った値（シャシの諸元は日野のカタログが要登録で取れず）、運転室の高さ"),
    # 生コン車（三菱ふそう。前端から前の車軸・ドラムの外形は【目安】）
    # UD トラックス Quon Dump・Mixer 主要諸元表（2025.3）p.4〜6: 前 1,400・軸距 3,200＋1,370・全長 7,975・全高 3,690・傾き 16°・
    # 最小回転半径 6.3m・車両総重量 19,900〜19,970kg（ふそう FV は前後の軸の位置とキャブの高さが公表されていなかった。2026-11-02）
    "mix45": Machine("mix45", 4, "生コン車 4.4m³", "UD クオン CW 6×4 ミキサ（新明和 4.4m³）", 19.97,
                     {**_truck(7.975, 2.49, 3.045, 1.4, 3.2, 2, 1.37, 0.528, 1.05),
                      "drL": 4.2, "drD": 2.25, "drA": 16.0},
                     "U1", turn_r=6.3,
                     guesses="運転室の屋根の高さ 3.045 は寸法図を全高 3,690 の寸法線で測った値、ドラムの外形（公表は内法 φ2,100×3,490。"
                             "外形の線が重なって測れない）・荷台の床の高さ"),
    "mix32": Machine("mix32", 4, "生コン車 3.2m³", "三菱ふそう ファイター FK7-Z ミキサ（3.2m³・KYB MR32）", 14.0,
                     {**_truck(6.33, 2.30, 2.5, 1.145, 3.19, 1, 1.3, 0.433, 1.0),
                      "drL": 3.6, "drD": 2.0, "drA": 17.0},
                     "M2", turn_r=5.8, payload_t=7.88,
                     guesses="前端から前の車軸 1.145・運転室の高さ 2.5・ドラムの外径 2.0・傾き 17° は KYB MR32 の外形図を測った値"
                             "（公表は内法 φ1,900×3,100）、ドラムの外形の長さ"),
    # ダンプ（荷台の床の高さから frZ を決める）
    "dump10": Machine("dump10", 5, "ダンプ 10t", "いすゞ ギガ 6×4（強化角底一方開・最大積載 9,100kg・ダンプ角度 53°）", 19.96,
                      {**_truck(7.64, 2.49, 3.17, 1.37, 3.225, 2, 1.31, 0.528, 1.45),
                       "bedL": 5.1, "bedW": 2.2, "bedH": 0.52, "bedA": 0.0},
                      "D1", turn_r=6.6, payload_t=9.1,
                      guesses="運転室の高さ 3.17 は同じギガのカーゴ（前二軸・標準ルーフ）の全高（いすゞ 03shogen.pdf p.1。ダンプの資料に無い）、"
                              "荷台の外寸（公表は内法）"),
    "dump4": Machine("dump4", 5, "ダンプ 4t", "三菱ふそう ファイター FK7（強化一方開・最大積載 3,750kg）", 7.965,
                     {**_truck(5.395, 2.19, 2.45, 1.17, 2.91, 1, 1.3, 0.40, 0.95),
                      "bedL": 3.4, "bedW": 2.06, "bedH": 0.34, "bedA": 0.0},
                     "M2", turn_r=4.8, payload_t=3.75,
                     guesses="前端から前の車軸 1.17 は UD コンドル 4t、運転室の高さ 2.45 は同じ FK7 の平ボデーの値（ダンプの資料に無い）、"
                             "鳥居の高さ・ダンプ角度（資料に無い）"),
    # 高所作業車（アイチ。旋回台・ジャッキの前後の位置・ブームの根元の高さは【目安】）
    "aw12": Machine("aw12", 6, "高所作業車 12m", "アイチ SH12C1RN（作業床 12.1m・後方格納の伸縮ブーム）", 0.0,
                    {**_truck(5.14, 1.91, 2.2, 1.025, 2.475, 1, 1.3, 0.36, 0.85, carF=2.15),
                     "nSec": 3, "abL": 9.4, "abA": 60.0, "tuH": 2.9, "pfL": 1.0, "pfW": 0.7,
                     "o1x": 2.15 - 1.65, "o1y": 1.9, "o2x": 2.15 - 4.44, "o2y": 1.7, "o3x": 0.0, "o3y": 0.0, "maxR": 9.9},
                    "A1", jacks_kn=(44.1, 44.1), platform_m=12.1, road="準中型免許（アイチの製品頁の必要運転免許）",
                    guesses="旋回中心 2.15・ジャッキの前後の位置・ブームの根元の高さ 2.9（設置時）は寸法図・作業範囲図を測った値、"
                            "車両総重量（資料に無い。免許は準中型＝7.5t 未満）・運転室の高さ・タイヤの半径"),
    # タダノ AT-170TG（17m 級・前方格納・3t 車クラス）。公表: 全長 6,900・全幅 2,150・全高 3,450・軸距 3,400・後軸〜後端 2,115・
    # ブーム 6.20〜15.40m・アウトリガ最大張出 4.1m・バスケット 0.7×1.2m。旋回中心・ジャッキ・ブームの根元は寸法図と作業範囲図を測った値
    "at17": Machine("at17", 6, "高所作業車 17m（タダノ）", "タダノ AT-170TG（作業床 17.2m・前方格納の伸縮ブーム）", 0.0,
                    {**_truck(6.9, 2.15, 2.25, 1.385, 3.4, 1, 1.3, 0.356, 0.91, carF=5.95),
                     "nSec": 3, "abL": 15.4, "abA": 60.0, "tuH": 2.44, "pfL": 1.2, "pfW": 0.7,
                     "o1x": 5.95 - 2.42, "o1y": 2.05, "o2x": 5.95 - 6.55, "o2y": 2.05, "o3x": 0.0, "o3y": 0.0, "maxR": 15.8},
                    "T3", platform_m=17.2, road="車両総重量が公表されていない（3t 車クラスの架装。車検証で免許を確かめる）",
                    guesses="旋回中心（前端から 5.95）・ジャッキの前後の位置（2.42・6.55）・運転室の高さ 2.25・タイヤの半径 0.356・"
                            "荷台の高さ 0.91 は寸法図を全長 6,900・全高 3,450 の寸法線で測った値、ブームの根元の高さ 2.44（設置時）と"
                            "最大作業半径 15.8（100kg）は作業範囲図の 1m 目盛りで測った値。最大ジャッキ反力・車両総重量は資料に無い"),
    "sv06": Machine("sv06", 7, "垂直昇降 5.7m", "アイチ SV06E1NS（自走式シザース・作業床 5.72m）", 1.2,
                    {"carL": 1.87, "carW": 0.76, "carF": 0.935, "whR": 0.185, "pfL": 1.77, "pfW": 0.68, "pfH": 3.0,
                     "maxR": 0.0},
                    "A3", platform_m=5.72, guesses="車輪の半径 0.185 は寸法図を測った値"),
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


def road_license(gvw_t: float, payload_t: float = 0.0) -> str:
    """公道の運転免許（道路交通法施行規則2条: 大型 11,000kg 以上か最大積載量 6,500kg 以上、中型 7,500kg 以上か 4,500kg 以上、
    準中型 3,500kg 以上か 2,000kg 以上）。平成19年6月1日以前の普通免許は 8t 限定中型（8t 未満・5t 未満）."""
    if gvw_t >= 11.0 or payload_t >= 6.5:
        return "大型免許"
    if gvw_t >= 7.5 or payload_t >= 4.5:
        return "中型免許" + ("（8t 限定中型も可）" if gvw_t < 8.0 and payload_t < 5.0 else "")
    if gvw_t >= 3.5 or payload_t >= 2.0:
        return "準中型免許"
    return "普通免許"


def license_for(m: Machine) -> str:
    """運転・操作に要る資格（安衛令・安衛則・クレーン則）と公道の免許."""
    if m.kind == 1:
        body = m.body_t or m.mass_t
        if body >= 3.0:
            return (f"車両系建設機械（整地・運搬・積込み用及び掘削用）運転技能講習（安衛令20条12号・安衛則41条。機体質量 {body:g}t）")
        return f"車両系建設機械（整地等）の特別教育（安衛則36条9号。機体質量 {body:g}t が 3t 未満。キャブ・増量ウエイト付きは機体質量で引き直す）"
    if m.kind == 2:
        lic = "移動式クレーン運転士免許（クレーン則68条）" if m.lift_t >= 5 else "小型移動式クレーン運転技能講習（クレーン則68条）"
        return lic + "・玉掛け技能講習（クレーン則221条）"
    if m.kind == 3:
        return "作業装置の操作はコンクリート打設用機械の特別教育（安衛則36条10号の2）・公道は" + road_license(m.mass_t, m.payload_t)
    if m.kind in (4, 5):
        return "公道は" + road_license(m.mass_t, m.payload_t) + "（安衛法の運転資格の定めは無い）"
    if m.kind in (6, 7):
        lic = ("高所作業車運転技能講習（安衛令20条15号）" if m.platform_m >= 10 else "高所作業車の特別教育（安衛則36条10号の5）")
        return lic + ("・公道は" + (m.road or road_license(m.mass_t, m.payload_t)) if m.kind == 6 else "")
    return ""


def plan_rule(m: Machine) -> str:
    """作業計画の条文（e-Gov の現行版で確かめた）."""
    return {1: "地形・地質の調査と記録（安衛則154条）・車両系建設機械の作業計画（安衛則155条）",
            2: "作業の方法等の決定（クレーン則66条の2）",
            3: "調査と記録（安衛則154条）・作業計画（155条）・輸送管の脱落防止・連絡・吹出し箇所の立入禁止（171条の2）・"
               "輸送管の組立て解体の作業指揮者（171条の3）",
            4: "生コン車が「貨物自動車（専ら荷を運搬する構造）」に当たる場合は作業計画（安衛則151条の3。道路上の走行を除く）・"
               "作業指揮者（151条の4）。当たるかを示した通達は見つからない",
            5: "車両系荷役運搬機械等の作業計画（安衛則151条の3。道路上の走行を除く）・作業指揮者（151条の4）",
            6: "高所作業車の作業計画（安衛則194条の9）・作業指揮者（194条の10）",
            7: "高所作業車の作業計画（安衛則194条の9）・作業指揮者（194条の10）"}[m.kind]


def keep_out(m: Machine, ps: dict, margin: float = KEEP_OUT) -> list[tuple[str, float, str]]:
    """立入禁止の範囲（名前, 半径 m, 条文）。余裕 margin は社内の決め（公的な数値は無い）."""
    out = []
    tail = float(ps.get("tailR", 0) or 0)
    if m.kind == 1:
        out.append(("後端（上部旋回体）", tail + margin, "安衛則158条"))
        out.append(("作業装置（最大掘削半径）", float(ps.get("maxR", 0)) + margin, "安衛則158条"))
    elif m.kind == 2:
        out.append(("上部旋回体", tail + margin, "クレーン則74条"))
        out.append(("つり荷の下", 0.0, "クレーン則74条の2"))
    elif m.kind == 3:
        out.append(("ブームの下・筒先の吹出し", float(ps.get("maxR", 0)) + margin, "安衛則158条・171条の2第3号"))
    elif m.kind in (4, 5):
        out.append(("車体と荷（バック・荷下ろし）", 0.0, "安衛則151条の7"))
    else:
        r = float(ps.get("maxR", 0) or 0)
        out.append(("作業床の下（物の落下）", r + margin if r > 0 else 0.0, "安衛則537条（高所作業車に専用の条は無い）"))
    return out


def rated_at(m: Machine, boom: float, radius: float) -> Optional[float]:
    """クレーンの定格総荷重 t（ブームはその長さ以上の列・半径はその半径以上の行。欄の「a/b」は b を超える半径（最大）か
    b に届かない半径（最小）では使えない。表の外は None）."""
    booms = sorted(b for b in m.rated if b >= boom - 1e-6)
    if not booms:
        return None
    rows = m.rated[booms[0]]
    rs = sorted(r for r in rows if r >= radius - 1e-6)
    if not rs:
        return None
    cell = rows[rs[0]]
    if isinstance(cell, tuple):
        t, lim = cell
        if (lim < rs[0] and radius > lim + 1e-6) or (lim > rs[0] and radius < lim - 1e-6):
            return None
        return t
    return cell


def outrigger_pad(load_kn: float, soil: int) -> str:
    """表3（22mm）: 脚荷重 → "S"・"A"・"B"・"-"（荷重は 100kN ごとの欄に切り上げ、1,000kN を超えれば "-"）."""
    i = max(0, math.ceil(load_kn / 100.0 - 1e-9) - 1)
    return OUTRIG_TABLE[soil][i] if i < 10 else "-"


def crawler_plates(press_kpa: float, soil: int) -> str:
    """表4（22mm）: 最大接地圧 → 敷鉄板（6.0×1.5m）の枚数 "0"〜"2" か "-"（50kN/m² ごとの欄に切り上げ）."""
    i = max(0, math.ceil((press_kpa - 100.0) / 50.0 - 1e-9))
    return CRAWLER_TABLE[soil][i] if i < 11 else "-"


def check(p: Placed, soil_q: float = SOIL_Q, soil: int = 1, margin: float = KEEP_OUT) -> Placed:
    m = p.machine
    ps = {**m.params, **p.params}
    p.checks = []
    sname = f"{SOILS[soil][0]}（{SOILS[soil][1]}・短期 {SOILS[soil][2]}kN/m²）"
    if m.ground_kpa:
        n = crawler_plates(m.ground_kpa, soil)
        st = "要確認" if n == "-" or m.ground_kpa > soil_q else ("要敷鉄板" if n != "0" else "注意")
        p.checks.append(Check("接地圧", st,
                              f"仕様書の平均接地圧 {m.ground_kpa:.1f}kPa（つり荷なし）・地盤 {soil_q:.0f}kN/m²。{sname} で表4 → "
                              + ("敷鉄板では対応できない" if n == "-" else f"敷鉄板 {n}枚") +
                              "（最大接地圧は平均より大きい。メーカーの最大接地圧で引き直す）"))
    for i, r in enumerate(m.jacks_kn, 1):
        k = outrigger_pad(r, soil)
        p.checks.append(Check(f"ジャッキ{i}の下", {"S": "OK", "A": "要敷鉄板", "B": "要敷鉄板", "-": "要確認"}[k],
                              f"反力 {r:.0f}kN・{sname} → {PAD_TEXT[k]}（表3 はトラッククレーン等の表を準用）"))
    if m.kind == 2:
        boom, ang = float(ps["lbL"]), float(ps["lbA"])
        rad = float(ps["pvX"]) + boom * math.cos(math.radians(ang)) + 0.4
        t = rated_at(m, boom, rad)
        p.checks.append(Check("定格総荷重", "OK" if t is not None else "要確認",
                              f"ブーム {boom:.1f}m・半径 {rad:.1f}m → " + (f"{t:g}t（フック・玉掛具込み）" if t is not None
                                                                         else "表の外（仕様書の定格総荷重表で確認）")))
        if m.lift_t > 20:
            p.checks.append(Check("地盤調査", "注意", "つり上げ荷重 20t を超える移動式クレーンは設置地盤の調査を（NIIS-SD-No.22 p.87〜88。"
                                                      "接地圧は極限支持力の 1/3 を推奨）"))
    for what, r, law in keep_out(m, ps, margin):
        p.checks.append(Check("立入禁止", "注意", f"{what}" + (f" R{r:.2f}m（余裕 {margin:g}m は社内の決め）" if r > 0 else "") + f"・{law}"))
    return p


def part_params(p: Placed) -> dict:
    """部品 ashiba_machine のパラメータ."""
    m = p.machine
    ps = {**m.params, **p.params}
    note = m.model.split("（")[0] + (f" {m.mass_t:g}t" if m.mass_t else "")
    if m.platform_m:
        note += f"・作業床 {m.platform_m:g}m"
    name = f"{p.name} {m.name}" if p.name else m.name
    return {"mcKind": m.kind, "mcModel": model_code(m.key), "mcName": name, "mcNote": note, "slew": p.slew, **ps}


def report(placed: list[Placed], soil_q: float = SOIL_Q, soil: int = 1) -> str:
    lines = ["# 重機の手配と判定", "", f"地盤: {SOILS[soil][0]}（{SOILS[soil][1]}・短期許容支持力 {SOILS[soil][2]}kN/m²）、"
             f"判定に使う値 {soil_q:.0f}kN/m²（地盤調査の値で直す）。敷鉄板は日本クレーン協会 表3・表4（鉄板厚 22mm）。", "",
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
