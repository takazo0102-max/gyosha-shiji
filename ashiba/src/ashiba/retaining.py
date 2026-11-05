"""山留め壁（利用者の指定 2026-11-05「山留めの種類も増やして シートパイルや簡易山留めなど 他にもあったら増やして LOD高めて
Hこう横やいたは矢板の平米拾えるようにしてかかりしろは厚みの分だけにして１次ねぎりと2次ねぎりで分けれるようにあと矢板を止める
さんぎも」）. 部品 ashiba_ywall（山留めの線の1辺に1つ）、置くのは scripts/ywall_run.py.

調べた値と出典は research_notes/山留めの種類/（親杭横矢板.md・鋼矢板と簡易山留め.md）。建築の今の決め（標仕 R7・公衆災害防止
対策要綱 建築工事等編 R1）には数値が無く、数値は土木の設計要領（九州地方整備局 土木工事設計要領 共通編 第2章。道路土工 仮設構造物工
指針に沿う）・旧要綱（H5。R1 で削除）・メーカーのカタログにある。出典の無いものは【目安】.

種類（kind）: oyagui 親杭横矢板・sp_u U形鋼矢板・sp_hat ハット形鋼矢板・lsp 軽量鋼矢板・alu アルミ矢板・tatekomi たて込み簡易土留め・
smw ソイルセメント柱列壁・koukan 鋼管矢板。木矢板は寸法と使える深さの出典が見つからないので入れていない.

座標（辺ごと・mm）: 原点＝辺の始めの山留めの線の GL、+X＝辺の向き、−Y＝根切りの側、+Y＝地山の側。閉じた線は根切り（中）が右（−Y）に
なる向き（時計回り）にそろえる。線は 親杭・SMW・鋼管矢板は芯、鋼矢板は壁の中心線（農水 土地改良工事数量算出要領 R6 2-13）、たて込み
簡易土留めは土留め板の外面（同 2-14）.

親杭横矢板（H鋼横矢板）
- 親杭 H形鋼は JIS G 3192 の広幅（日本製鉄 建築製品ハンドブック 3-28）。芯々 1.5m を標準・1.0〜2.0m（九州 共2-22）。掘削 3m 以深は
  H-300 以上（九州 共2-32）。フランジを山留めの線に平行に
- 根入れ: つり合い深さ×1.2、1.5m 未満なら 1.5m、50cm 単位に切り上げ（九州 共2-21）。入れた根入れを 50cm に切り上げ、1.5m 未満は WARN
- 横矢板: 杉・松の幅 200mm、厚さ 25〜60mm・長さ 1〜4m の定尺（wood.co.jp の在庫表）。最小厚 30mm（九州 共2-23）、既定 40mm【目安】。
  掘削側のフランジの裏（地山側）に当てて掛ける（土木学会 年次講演 Ⅵ-212 2009 p.423〜424）
- 掛かり代は矢板の厚さ（利用者の指定。旧要綱 建築 H5 第48「両端が矢板の厚み以上」）。土木の要領は 40mm 以上かつ板厚以上（九州 共2-23）
  なので、40mm 未満は「注意」
- 矢板の長さ ＝ フランジの先どうしの内法（芯々 − B）＋ 掛かり代×2【目安。式は出典に無く形から】。入る上限 芯々 − t1 − 2×20
- くさび: 矢板1枚の左右に各2個（作業手順書）。寸法は見つからない → 150×40・厚 5〜25【目安】
- 矢板止めの桟木: バイの両端・親杭のフランジの脇に縦1本ずつ、矢板の各段に釘止め（標準作業シート №3「さん木で各横矢板を釘止めし、
  ズレ落ち防止」）。40×16【目安。木材店の胴縁・ズレ止 16×40】。根切りの段ごとに入れる
- 1次根切り・2次根切り: 段ごとに掘って矢板を入れる。1回の素掘りは矢板1枚分（200mm）、先行掘りはしない（作業手順書）。腹起しの第1段は
  杭頭から 1m 以内、その下は 3m 程度ごと（九州 共2-24）
- 数量: 横矢板は 根切り深さ × 山留め壁の周長（m²。根入れ部は含まない。公共建築数量積算基準 R5 p.8）。周長は親杭の芯線【目安】
鋼矢板（U形・ハット形）: 日本製鉄 建設用資材ハンドブック 1-1・1-2（JFE カタログ d1j-501 印刷 p.6〜8 と同じ値）。枚数＝中心線の長さ ÷
  有効幅（切り上げ）、質量＝長さ×単位質量×枚数（農水 数量算出要領 16-27）。U形の継手は壁の中立軸、ハット形は外縁（JFE-FAQ Q7）。
  ハット形と U形はかみ合わない。根入れの最小 3.0m（旧 土木要綱・道路土工 仮設指針）。長さは 0.5m 刻み【目安】
軽量鋼矢板: 日鉄建材 1-12・軽量鋼矢板Q&A p.4〜6（リース材の長さ p.42）。計算すれば掘削 4m 程度まで（横浜市 下水道設計指針 8-5）
アルミ矢板: ホーシン HAY-3833N（333×38、長さ 1.5〜4.0m）。根入れ 0.2m 以上・掘削 3.8m まで（静岡市 土留工標準構造図）
たて込み簡易土留め: 日本スピードショア TSパネル（TSⅠ 3.5m まで・TSⅡ 6.0m まで）。根入れは無い、掘削幅 4.7m 以下（同 製品頁）
SMW: 削孔径・平均壁厚・軸間は SMW 協会・三和機工の資料（既存の調査 重機 杭山留解体/山留め.md）。芯材は全孔か1本おき
鋼管矢板: JIS A 5530（外径 500〜2,000、6m 以上で 0.5m 刻み）、継手 P-P φ165.2×9（鋼管杭・鋼矢板技術協会 標準製作仕様 p.3）
"""

from __future__ import annotations

import math
from itertools import combinations_with_replacement
from dataclasses import dataclass, field

# ---- H形鋼（H×B×t1×t2 mm・kg/m。JIS G 3192。広幅は日本製鉄 建築製品ハンドブック 3-28・K004 p.48、中幅・細幅は SMW の芯材） ----
H_SHAPES = {
    "H-200": (200.0, 200.0, 8.0, 12.0, 49.9),
    "H-250": (250.0, 250.0, 9.0, 14.0, 71.8),
    "H-300": (300.0, 300.0, 10.0, 15.0, 93.0),
    "H-350": (350.0, 350.0, 12.0, 19.0, 135.0),
    "H-400": (400.0, 400.0, 13.0, 21.0, 172.0),
    "H-350×175": (350.0, 175.0, 7.0, 11.0, 49.6),
    "H-400×200": (400.0, 200.0, 8.0, 13.0, 66.0),
    "H-450×200": (450.0, 200.0, 9.0, 14.0, 76.0),
    "H-500×200": (500.0, 200.0, 10.0, 16.0, 89.6),
    "H-588×300": (588.0, 300.0, 12.0, 20.0, 151.0),
}
PILE_SHAPES = ("H-200", "H-250", "H-300", "H-350", "H-400")
PILE_PITCH_MM = 1500.0               # 芯々の標準（九州 共2-22）
PILE_PITCH_RANGE = (1000.0, 2000.0)
EMBED_MIN_MM = 1500.0                # 根入れの下限（九州 共2-21）
EMBED_STEP_MM = 500.0                # 根入れは 50cm 単位に切り上げ（同）
H300_DEPTH_MM = 3000.0               # 掘削 3m 以深は H-300 以上（九州 共2-32）
LAG_W_MM = 200.0                     # 横矢板の幅（木材店の標準）
LAG_T_MM = 40.0                      # 横矢板の厚さ【目安。最小 30（九州 共2-23）】
LAG_T_MIN_MM = 30.0
LAG_T_OPTIONS = (25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 60.0)
LAG_STOCK_M = (1.0, 1.2, 2.0, 3.0, 4.0)   # 定尺（wood.co.jp）
KAKARI_SOIL_MIN_MM = 40.0            # 土木の要領の掛かり代の下限（九州 共2-23）。ここでは掛かり代＝板厚（利用者の指定）
INSERT_PLAY_MM = 20.0                # 差し込みのあそび【目安】
WEDGE_GAP_MM = 15.0                  # フランジと矢板のすき間（くさびを打つ。掛かり付近は矢板厚＋くさび分の空隙: JR論文 p.424）【目安】
SIGMA_SUGI = 10.3                    # すぎ系の許容曲げ応力度 N/mm²（学会 山留め設計指針 第4版 p.87）
WEDGE = (150.0, 40.0, 25.0)          # くさびの長さ・幅・厚い方【目安】
SANKI = (40.0, 16.0)                 # 矢板止めの桟木 幅×厚【目安】
SANKI_STOCK_M = (2.0, 4.0)
# 腹起し・切梁（山留め支保工）: リース材 30HA（H-300）100kg/m・40HA 200kg/m（ヒロセ 鋼製山留総合カタログ p.15〜23・国総研 数量要領
# R8 1-11-5）。山留め壁と腹起しの間隙 10cm（裏込め。ヒロセ p.6）、ブラケットは腹起し1本に2個以上・2m ピッチ目安・両端に必ず（施工計画書例）、
# 切梁は水平 5m 以下・垂直 3m 程度（九州 共2-24）、切梁を入れるときの余掘り 1.0m（道路土工 仮設指針 p.65）
WALE_SHAPE = {"heavy": ("H-300", 100.0), "light": ("H-200", 55.0)}     # (形, kg/m。加工材の単位質量)
WALE_GAP_MM = 100.0
BRACKET_PITCH_MM = 2000.0
BRACKET_END_MM = 150.0               # 腹起しの端からブラケットまで【目安】
STRUT_PITCH_MM = 5000.0
STRUT_OVERDIG_MM = 1000.0            # 切梁の下の余掘り（1次根切りの底＝腹起しの下端＋1.0m）
AUTO_SUPPORT_DEPTH_MM = 3000.0       # 「自動」はこれより深いと腹起し・切梁を描く【目安。自立にできるかは山留めの計算で】
CORNER_GAP_MM = 5.0                  # 角の杭のフランジと矢板の端のすき間【目安】
WALE_FIRST_MM = 1000.0               # 腹起しの第1段は杭頭から 1m 以内（九州 共2-24）
WALE_STEP_MM = 3000.0                # その下は 3m 程度ごと
LEN_STEP_MM = 500.0                  # 鋼矢板・鋼管矢板の長さの刻み【目安】

# ---- 鋼矢板（有効幅 W・有効高さ h・板厚 t mm、1枚 kg/m、壁1m の Z cm³/m・kg/m²） ----
SP_U = {
    "II": ("Ⅱ型", 400.0, 100.0, 10.5, 48.0, 874.0, 120.0),
    "III": ("Ⅲ型", 400.0, 125.0, 13.0, 60.0, 1340.0, 150.0),
    "IV": ("Ⅳ型", 400.0, 170.0, 15.5, 76.1, 2270.0, 190.0),
    "VL": ("ⅤL型", 500.0, 200.0, 24.3, 105.0, 3150.0, 210.0),
    "VIL": ("ⅥL型", 500.0, 225.0, 27.6, 120.0, 3820.0, 240.0),
    "IIw": ("Ⅱw型", 600.0, 130.0, 10.3, 61.8, 1000.0, 103.0),
    "IIIw": ("Ⅲw型", 600.0, 180.0, 13.4, 81.6, 1800.0, 136.0),
    "IVw": ("Ⅳw型", 600.0, 210.0, 18.0, 106.0, 2700.0, 177.0),
}
SP_HAT = {
    "10H": ("10H", 900.0, 230.0, 10.8, 86.4, 902.0, 96.0),
    "25H": ("25H", 900.0, 300.0, 13.2, 113.0, 1610.0, 126.0),
    "45H": ("45H", 900.0, 368.0, 15.0, 147.0, 2450.0, 163.0),
    "50H": ("50H", 900.0, 370.0, 17.0, 167.0, 2760.0, 186.0),
}
# 軽量鋼矢板（リースの板厚。日鉄建材 1-12・軽量鋼矢板Q&A p.4〜6）。最後はリース材の長さの範囲 m（同 p.42。無いものは None）
LSP = {
    "LSP-1": ("LSP-1（A1）", 250.0, 36.0, 5.0, 12.9, 33.3, 51.6, (2.0, 4.0)),
    "LSP-2": ("LSP-2（A）", 250.0, 36.0, 5.0, 14.8, 59.7, 59.2, (2.0, 5.0)),
    "LSP-2N": ("LSP-2N", 250.0, 43.0, 5.0, 14.8, 96.5, 59.2, None),
    "LSP-3A": ("LSP-3A（B）", 333.0, 51.0, 5.0, 17.9, 144.0, 53.7, None),
    "LSP-3B": ("LSP-3B（D）", 333.0, 75.0, 6.0, 25.9, 204.0, 77.7, (3.0, 5.5)),
    "LSP-3D": ("LSP-3D（C）", 333.0, 87.0, 6.0, 23.3, 330.0, 69.9, None),
    "LSP-5": ("LSP-5（E）", 500.0, 161.0, 6.0, 40.4, 540.0, 80.8, None),
}
LSP_DEPTH_MM = 4000.0                # 計算すれば掘削 4m 程度まで（横浜市 下水道設計指針 8-5）
# アルミ矢板（ホーシン HAY-3833N: 1枚 20.2kg/4m）
ALU = {"HAY-3833N": ("HAY-3833N", 333.0, 38.0, 4.0, 20.2 / 4.0, 20.6 * 3.0, 20.2 / 4.0 * 3.0, (1.5, 4.0))}
ALU_DEPTH_MM = 3800.0                # 支保工 3段で 3.8m まで（静岡市）
ALU_EMBED_MM = 200.0                 # 根入れ 0.2m 以上（静岡市）
SP_EMBED_MIN_MM = 3000.0             # 鋼矢板の根入れの最小（旧 土木要綱・道路土工 仮設指針）
SP_ROTATE_DEG = {"sp_u": 6.0, "sp_hat": 4.0, "lsp": 10.0, "alu": 10.0}   # 継手の標準回転角（JFE カタログ 印刷 p.11、LSP-QA p.10）
# たて込み簡易土留め（日本スピードショア TSパネル）: 深さの上限・パネルの長さと厚さ・下部パネル {高さ: kg}・上部 {高さ: kg}・
# スライドレール（幅×奥行 mm・{長さ: kg}）・掘削幅（外幅）の範囲
TATEKOMI = {
    "TS1": ("TSⅠ（3.5m まで）", 3500.0, 2500.0, 66.4, {1000.0: 228.0, 1500.0: 364.0, 2000.0: 404.0},
            {500.0: 136.0, 1000.0: 224.0, 1500.0: 312.0}, (141.0, 161.0), {2000.0: 119.0, 2500.0: 140.0, 3000.0: 187.0, 3500.0: 216.0},
            (954.0, 4356.0)),
    "TS2": ("TSⅡ（6.0m まで）", 6000.0, 3000.0, 104.0, {2000.0: 663.0, 2200.0: 779.0},
            {500.0: 223.0, 1000.0: 366.0, 2000.0: 624.0}, (191.0, 204.0), {4000.0: 356.0, 4500.0: 443.0, 5000.0: 498.0},
            (1306.0, 4456.0)),
}
TATEKOMI_WIDTH_MAX_MM = 4700.0
STRUT_DIA_MM = 114.3                 # 切梁（サポートジャッキ）の太さ【目安】
STRUT_FROM_BOTTOM_MM = 700.0         # 切梁の段: 下は底から、上は GL から【目安】
# SMW（削孔径: 平均壁厚・軸間）
SMW = {550.0: (480.0, 450.0), 600.0: (538.0, 450.0), 650.0: (593.0, 450.0), 850.0: (773.0, 600.0), 900.0: (828.0, 600.0)}
SMW_CORE = {550.0: "H-400×200", 600.0: "H-400×200", 650.0: "H-450×200", 850.0: "H-588×300", 900.0: "H-588×300"}   # 既定の芯材【目安】
# 鋼管矢板（外径・板厚の既定と継手）
TUBE_D_MM, TUBE_T_MM = 800.0, 12.0   # 【目安。外径 500〜2,000】
JOINT_D_MM, JOINT_T_MM = 165.2, 9.0  # P-P 継手（鋼管杭・鋼矢板技術協会 標準製作仕様 p.3）

KIND_LABELS = {"oyagui": "親杭横矢板（H鋼横矢板）", "sp_u": "鋼矢板（U形シートパイル）", "sp_hat": "鋼矢板（ハット形）",
               "lsp": "軽量鋼矢板", "alu": "アルミ矢板", "tatekomi": "たて込み簡易土留め", "smw": "ソイルセメント柱列壁（SMW）",
               "koukan": "鋼管矢板"}
KIND_NO = {k: i for i, k in enumerate(KIND_LABELS, 1)}
SHEET_KINDS = ("sp_u", "sp_hat", "lsp", "alu")

SOURCES = {
    "pile": "日本製鉄 建築製品ハンドブック 3-28 https://www.nipponsteel.com/product/construction/handbook/pdf/3-28.pdf",
    "design": "九州地方整備局 土木工事設計要領 共通編 第2章 仮設構造物 共2-21〜32 http://www.qsr.mlit.go.jp/s_top/h22doboku/common/1-03.pdf",
    "kakari": "旧 建設工事公衆災害防止対策要綱 建築工事編（H5）第48（R1 で削除） https://www.mlit.go.jp/common/001221756.pdf",
    "qty": "公共建築数量積算基準（令和5年改定）p.8 https://www.mlit.go.jp/common/001178206.pdf",
    "lagging": "木の情報発信基地 土木用材の在庫表 https://wood.co.jp/doboku/zaiko.html",
    "method": "大塚ほか 親杭式掘削土留め工の施工法に関する一考察 土木学会年次学術講演会 Ⅵ-212（2009）p.423〜424",
    "sp": "日本製鉄 建設用資材ハンドブック 1-1・1-2 https://www.nipponsteel.com/product/construction/handbook/pdf/1-2.pdf",
    "lsp": "日本製鉄 建設用資材ハンドブック 1-12（軽量鋼矢板）・軽量鋼矢板Q&A https://www.nipponsteel.com/product/construction/handbook/pdf/1-12.pdf",
    "alu": "ホーシン アルミ矢板 HAY-3833N https://hoshin.co.jp/dcms_media/other/alyaita_catalog.pdf・静岡市 土留工標準構造図",
    "ts": "日本スピードショア TSパネル https://speedshore.co.jp/product/tspanel/",
    "nousui": "農林水産省 土地改良工事数量算出要領（案）R6 2-13・2-14・16-27",
    "tube": "鋼管杭・鋼矢板技術協会 鋼管矢板 標準製作仕様（JIS A 5530）",
}


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Stage:
    """根切りの段（1次・2次…）. top・bottom は GL からの深さ mm（正）."""
    name: str
    top: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass
class Edge:
    """山留めの1辺の割付（mm、辺の始めから）."""
    name: str
    a: tuple
    b: tuple
    length: float = 0.0
    piles: list = field(default_factory=list)          # 親杭・SMW の孔・鋼管・レールの位置（始めの角を含み、終わりの角は次の辺）
    bays: list = field(default_factory=list)           # 親杭横矢板 [(始めの杭 x, 終わりの杭 x)]
    lag_len: list = field(default_factory=list)        # バイごとの矢板の長さ
    lag_ab: list = field(default_factory=list)         # バイごとの矢板の始めと終わり（辺の始めから）
    units: int = 0                                     # 鋼矢板の枚数
    cores: list = field(default_factory=list)          # SMW の芯材の位置
    struts: list = field(default_factory=list)         # たて込み: レールごとの切梁の長さ（根切りの中心まで。0＝無し）
    wale_x: tuple = (0.0, 0.0)                         # 腹起しの始めと終わり（角は次の腹起しまで通し、始めは前の腹起しに突き当てる）
    brackets: list = field(default_factory=list)       # 腹起しのブラケットの位置
    strut_x: list = field(default_factory=list)        # 切梁の位置（狭い向きの辺だけ）
    strut_len: list = field(default_factory=list)      # 切梁の長さ（腹起しの前の面から根切りの中心まで。向かいの辺の部品と合わせて1本）
    width: float = 0.0                                 # たて込み: 掘削幅（向かいの土留めまで。0＝分からない）


@dataclass
class Wall:
    """山留め（線1本分）."""
    name: str
    kind: str = "oyagui"
    pts: list = field(default_factory=list)            # 線の点（mm。閉じた線は始めを繰り返さない）
    closed: bool = False
    gl: float = 0.0                                    # GL の高さ（mm。プロジェクトの 0 から）
    depth: float = 3000.0                              # 根切り（掘削）の深さ（GL から mm、正）
    stages_mm: list = field(default_factory=list)      # 段の底の深さ（GL から mm、正。最後は depth）。空＝1段
    top_up: float = 0.0                                # 天端（杭頭）の GL からの高さ mm
    embed: float | None = None                         # 根入れ mm（None＝種類の既定）
    model: str = ""                                    # 型式（H形鋼・鋼矢板・軽量鋼矢板・アルミ矢板・たて込みの型、SMW は削孔径）
    pitch: float = PILE_PITCH_MM                       # 親杭の芯々
    lag_t: float = LAG_T_MM
    lag_w: float = LAG_W_MM
    kakari: float | None = None                        # 掛かり代（None＝板厚）
    core: str = ""                                     # SMW の芯材（H形鋼のキー。空＝削孔径の既定）
    core_every: int = 1                                # SMW の芯材 1＝全孔・2＝1本おき
    tube_d: float = TUBE_D_MM
    tube_t: float = TUBE_T_MM
    support: str = "auto"                              # 腹起し・切梁: auto（深さ 3m を超えたら）・wale（描く）・none（自立）
    wales: list = field(default_factory=list)          # 腹起しの段（GL からの深さ mm。腹起しの芯）
    edges: list = field(default_factory=list)
    stages: list = field(default_factory=list)
    checks: list = field(default_factory=list)

    @property
    def kakari_mm(self) -> float:
        return self.lag_t if self.kakari is None else self.kakari

    @property
    def embed_mm(self) -> float:
        e = default_embed(self.kind, self.depth) if self.embed is None else float(self.embed)
        if self.kind == "oyagui":
            return math.ceil(e / EMBED_STEP_MM - 1e-9) * EMBED_STEP_MM
        return max(0.0, e)

    @property
    def wall_len(self) -> float:
        """杭・矢板の長さ（天端から先まで）。鋼矢板・鋼管矢板は 0.5m 刻みに切り上げ."""
        L = self.top_up + self.depth + self.embed_mm
        if self.kind in SHEET_KINDS or self.kind == "koukan":
            L = math.ceil(L / LEN_STEP_MM - 1e-9) * LEN_STEP_MM
        if self.kind == "tatekomi":
            L = tatekomi_rail(self)[0]
        return L

    @property
    def perimeter(self) -> float:
        return sum(e.length for e in self.edges)


def default_model(kind: str) -> str:
    return {"oyagui": "H-300", "sp_u": "III", "sp_hat": "10H", "lsp": "LSP-2", "alu": "HAY-3833N", "tatekomi": "TS2",
            "smw": "550", "koukan": f"{TUBE_D_MM:.0f}"}[kind]


def default_embed(kind: str, depth: float) -> float:
    """種類の既定の根入れ mm."""
    if kind == "oyagui":
        return EMBED_MIN_MM
    if kind in ("sp_u", "sp_hat"):
        return SP_EMBED_MIN_MM
    if kind == "lsp":
        return max(ALU_EMBED_MM, depth / 2.0)          # 打込み・圧入は H/2（横浜市 下水道設計指針 8-10）
    if kind == "alu":
        return ALU_EMBED_MM
    if kind == "tatekomi":
        return 0.0                                     # パネルの根入れは無い（TSパネル）
    return 3000.0                                      # SMW・鋼管矢板【目安。山留めの計算で】


def sheet_spec(kind: str, model: str):
    """鋼矢板の (名前, W, h, t, kg/m, Z cm³/m, kg/m², 長さの範囲)."""
    if kind == "sp_u":
        n, W, h, t, kg, Z, kgm2 = SP_U[model]
        return n, W, h, t, kg, Z, kgm2, None
    if kind == "sp_hat":
        n, W, h, t, kg, Z, kgm2 = SP_HAT[model]
        return n, W, h, t, kg, Z, kgm2, None
    if kind == "lsp":
        return LSP[model]
    return ALU[model]


def orient(pts: list, closed: bool) -> list:
    """閉じた線は時計回り（根切りの中が辺の右＝−Y）にそろえる。開いた線はそのまま（左＝+Y が地山）."""
    if not closed or len(pts) < 3:
        return list(pts)
    area = sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts))) / 2.0
    return list(pts) if area < 0 else list(reversed(pts))


def make_stages(depth: float, stages_mm) -> list[Stage]:
    """段の底の深さ（例 [2000, 4000]）→ [Stage]。最後の段は根切りの深さまで。浅すぎ・重なりは捨てる."""
    cuts = sorted({round(float(s), 1) for s in (stages_mm or []) if 0.0 < float(s) < depth - 1.0})
    tops = [0.0] + cuts
    bots = cuts + [float(depth)]
    return [Stage(f"{i + 1}次根切り", t, b) for i, (t, b) in enumerate(zip(tops, bots))]


def stations(length: float, pitch: float) -> list[float]:
    """辺の長さを pitch 以下の等間隔に割った位置（始めを含み、終わり（次の辺の始め）は含まない）."""
    n = max(1, math.ceil(length / pitch - 1e-6))
    return [length * i / n for i in range(n)]


def boards_per_stage(stages: list[Stage], w: float) -> list[int]:
    """段ごとの矢板の枚数（1バイ）. 段の底まで入れた累計の枚数の差（最後の段は根切り底まで切り上げ）."""
    out, prev = [], 0
    for i, s in enumerate(stages):
        last = i == len(stages) - 1
        cum = math.ceil(s.bottom / w - 1e-6) if last else int(math.floor(s.bottom / w + 1e-6))
        out.append(max(0, cum - prev))
        prev = max(prev, cum)
    return out


def stock_len(L_mm: float, stock=LAG_STOCK_M) -> float:
    """切る前の定尺（m）. 足りなければいちばん長いもの."""
    for s in stock:
        if s * 1000.0 >= L_mm - 1e-6:
            return s
    return stock[-1]


def corners(w: Wall, min_deg: float = 20.0) -> int:
    """折れる角の数（閉じた線は全部の頂点、開いた線は途中の頂点）."""
    pts = w.pts
    idx = range(len(pts)) if w.closed else range(1, len(pts) - 1)
    n = 0
    for i in idx:
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        ang = abs(math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])))
        n += ang >= min_deg
    return n


def _ray_hit(p, d, segs) -> float:
    """点 p から向き d（単位）に進んで線分に当たる距離（当たらなければ 0）."""
    best = 0.0
    for a, b in segs:
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-9:
            continue
        t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den
        s = ((a[0] - p[0]) * d[1] - (a[1] - p[1]) * d[0]) / den
        if t > 1.0 and -1e-6 <= s <= 1.0 + 1e-6 and (best == 0.0 or t < best):
            best = t
    return best


def _edges(w: Wall, pitch: float) -> list[Edge]:
    pts = w.pts
    segs = list(zip(pts, pts[1:] + ([pts[0]] if w.closed else [])))
    out = []
    for i, (a, b) in enumerate(segs, 1):
        L = math.dist(a, b)
        e = Edge(f"{w.name}-{i}", a, b, length=L)
        e.piles = stations(L, pitch)
        out.append(e)
    if not w.closed and out:
        out[-1].piles.append(out[-1].length)            # 開いた線は終わりにも
    return out


def plan(w: Wall) -> Wall:
    """種類ごとの割付と検定."""
    if not w.model:
        w.model = default_model(w.kind)
    w.pts = orient(w.pts, w.closed)
    w.wales = support_levels(w)
    if w.wales and not w.stages_mm:
        # 根切りの段を入れていなければ、腹起しの段ごとに「腹起しの下端＋余掘り 1.0m」までを1次・2次…根切りに
        wb = H_SHAPES[wale_shape(w)[0]][1]
        w.stages_mm = [z + wb / 2.0 + STRUT_OVERDIG_MM for z in w.wales if z + wb / 2.0 + STRUT_OVERDIG_MM < w.depth - 1.0]
    w.stages = make_stages(w.depth, w.stages_mm)
    if w.kind == "oyagui":
        H, B, t1, t2, kg = H_SHAPES[w.model]
        w.edges = _edges(w, w.pitch)
        k = w.kakari_mm
        for i, e in enumerate(w.edges):
            ends = e.piles + ([] if e.piles and abs(e.piles[-1] - e.length) < 1e-6 else [e.length])
            e.bays = list(zip(ends, ends[1:]))
            e.lag_ab = [(x0 + B / 2.0 - k, x1 - B / 2.0 + k) for x0, x1 in e.bays]
            if e.lag_ab and (w.closed or i < len(w.edges) - 1):
                # 角の杭は次の辺の向き（フランジが次の辺に平行）に立つので、この辺の最後の矢板は角の杭のフランジの面
                # （芯から H/2 手前）に突き当てて止める
                a0, _b0 = e.lag_ab[-1]
                e.lag_ab[-1] = (a0, e.length - H / 2.0 - CORNER_GAP_MM)
            e.lag_len = [b - a for a, b in e.lag_ab]
    elif w.kind in SHEET_KINDS:
        _n, W, *_ = sheet_spec(w.kind, w.model)
        w.edges = _edges(w, W)
        for e in w.edges:
            e.units = max(1, math.ceil(e.length / W - 1e-6))
            e.piles = [W * i for i in range(e.units)]
    elif w.kind == "smw":
        D = float(w.model)
        _tm, p = SMW[D]
        w.edges = _edges(w, p)
        for e in w.edges:
            e.piles = [p * i for i in range(max(1, math.ceil(e.length / p - 1e-6)))] + (
                [e.length] if (not w.closed and e is w.edges[-1]) else [])
        k = 0
        for e in w.edges:
            for x in e.piles:
                if k % max(1, w.core_every) == 0:
                    e.cores.append(x)
                k += 1
    elif w.kind == "koukan":
        pitch = w.tube_d + JOINT_D_MM
        w.edges = _edges(w, pitch)
        for e in w.edges:
            e.piles = [pitch * i for i in range(max(1, math.ceil(e.length / pitch - 1e-6)))] + (
                [e.length] if (not w.closed and e is w.edges[-1]) else [])
    elif w.kind == "tatekomi":
        sysd = TATEKOMI[w.model]
        w.edges = _edges(w, sysd[2])
        rail_d = sysd[6][1]
        segs = list(zip(w.pts, w.pts[1:] + ([w.pts[0]] if w.closed else [])))
        for i, e in enumerate(w.edges):
            if not (e.piles and abs(e.piles[-1] - e.length) < 1e-6):
                e.piles = e.piles + [e.length]          # 両端にレール（角は両方の辺に）
            ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
            inward = (uy, -ux)                            # −Y（右）が根切りの中
            others = [s for j, s in enumerate(segs) if j != i]
            ws = []
            for x in e.piles:
                p = (e.a[0] + ux * x, e.a[1] + uy * x)
                ws.append(_ray_hit(p, inward, others))
            e.width = max(ws) if ws and all(v > 0 for v in ws) else 0.0
            e.struts = list(ws)
        # 切梁は根切りの狭い向き（掘削幅）だけ。長い向きの向かい（妻の側）には渡さない（溝の両端は妻のパネル）
        trench = min((e.width for e in w.edges if e.width > 0), default=0.0)
        for e in w.edges:
            narrow = e.width > 0 and e.width <= trench * 1.2 + 1.0
            e.struts = [max(0.0, v / 2.0 - rail_d - sysd[3]) if (narrow and v > 0) else 0.0 for v in e.struts]
            if not narrow:
                e.width = 0.0 if e.width > trench * 1.2 + 1.0 else e.width
    else:
        raise KeyError(f"山留めの種類が分かりません: {w.kind}")
    if w.wales:
        plan_supports(w)
    w.checks = check(w)
    return w


def wale_shape(w: Wall) -> tuple:
    """腹起し・切梁の形と kg/m（軽量鋼矢板・アルミ矢板は H-200【目安】）."""
    return WALE_SHAPE["light" if w.kind in ("lsp", "alu") else "heavy"]


def support_levels(w: Wall) -> list[float]:
    """腹起し・切梁の段（GL からの深さ mm）. 自立・たて込みは無し."""
    if w.kind == "tatekomi" or w.support == "none":
        return []
    if w.support == "auto" and w.depth <= AUTO_SUPPORT_DEPTH_MM + 1e-6:
        return []
    if w.kind in ("lsp", "alu"):
        n = 1 if w.depth <= 2000.0 else 2 if w.depth <= 3500.0 else 3      # 軽量鋼矢板Q&A p.36・静岡市
        return [round(w.depth * i / (n + 1), 0) for i in range(1, n + 1)]   # 段の高さは【目安】（等分）
    return wale_levels(w)


def plan_supports(w: Wall) -> None:
    """腹起しの範囲・ブラケット・切梁（狭い向きの辺に水平 5m 以下で等分、長さは根切りの中心まで）."""
    H = H_SHAPES[wale_shape(w)[0]][0]
    f = face_offset(w) + WALE_GAP_MM
    n = len(w.edges)
    for i, e in enumerate(w.edges):
        x0 = 0.0 if (not w.closed and i == 0) else f + H
        x1 = e.length if (not w.closed and i == n - 1) else e.length - f
        e.wale_x = (x0, max(x0, x1))
        span = e.wale_x[1] - e.wale_x[0]
        k = max(1, math.ceil((span - 2 * BRACKET_END_MM) / BRACKET_PITCH_MM - 1e-6))
        e.brackets = [x0 + BRACKET_END_MM + (span - 2 * BRACKET_END_MM) * j / k for j in range(k + 1)]
    if not w.closed:
        return
    segs = list(zip(w.pts, w.pts[1:] + w.pts[:1]))
    widths = []
    for i, e in enumerate(w.edges):
        ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
        mid = (e.a[0] + ux * e.length / 2.0, e.a[1] + uy * e.length / 2.0)
        widths.append(_ray_hit(mid, (uy, -ux), [s for j, s in enumerate(segs) if j != i]))
    known = [v for v in widths if v > 0]
    if not known:
        return
    narrow = min(known)
    for i, e in enumerate(w.edges):
        if not (0 < widths[i] <= narrow * 1.2 + 1.0):
            continue
        x0, x1 = e.wale_x
        k = max(1, math.ceil((x1 - x0) / STRUT_PITCH_MM - 1e-6))
        e.strut_x = [x0 + (x1 - x0) * (j + 0.5) / k for j in range(k)]
        ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
        others = [s for j, s in enumerate(segs) if j != i]
        e.strut_len = []
        for x in e.strut_x:
            v = _ray_hit((e.a[0] + ux * x, e.a[1] + uy * x), (uy, -ux), others)
            e.strut_len.append(max(0.0, v / 2.0 - f - H) if v > 0 else 0.0)


def tatekomi_stack(w: Wall) -> tuple[list[float], float]:
    """パネルの積み方（下から高さ mm の並び）と重さ kg（1枚の長さぶん）. 深さ以上で、はみ出しが少なく枚数の少ないもの."""
    _n, _hmax, _pl, _t, lower, upper, _rail, _rlen, _rng = TATEKOMI[w.model]
    best = None
    ups = sorted(upper)
    combos = [c for r in range(4) for c in combinations_with_replacement(ups, r)]
    for lo in sorted(lower):
        for c in combos:
            tot = lo + sum(c)
            if tot < w.depth - 1e-6:
                continue
            key = (tot - w.depth, len(c))
            if best is None or key < best[0]:
                best = (key, [lo] + sorted(c, reverse=True), lower[lo] + sum(upper[u] for u in c))
    if best is None:
        lo = max(lower)
        return [lo] + [max(ups)] * 4, lower[lo] + upper[max(ups)] * 4
    return best[1], best[2]


def tatekomi_rail(w: Wall) -> tuple[float, float]:
    """スライドレールの長さ mm と重さ kg（深さ以上でいちばん短いもの）."""
    rl = TATEKOMI[w.model][7]
    for L in sorted(rl):
        if L >= w.depth - 1e-6:
            return L, rl[L]
    L = max(rl)
    return L, rl[L]


def strut_levels(w: Wall) -> list[float]:
    """たて込みの切梁の段（GL からの深さ mm）【目安】."""
    if w.depth <= 2.0 * STRUT_FROM_BOTTOM_MM + 600.0:
        return [w.depth / 2.0]
    return [STRUT_FROM_BOTTOM_MM, w.depth - STRUT_FROM_BOTTOM_MM]


def wale_levels(w: Wall) -> list[float]:
    """腹起しの段の目安（GL からの深さ mm）. 杭頭から 1m 以内・その下 3m 程度ごと、根切り底の 1m 上まで."""
    out = []
    z = max(0.0, WALE_FIRST_MM - w.top_up)
    while z <= w.depth - 1000.0 + 1e-6:
        out.append(z)
        z += WALE_STEP_MM
    return out


def check(w: Wall) -> list[Check]:
    out: list[Check] = []
    if w.kind == "oyagui":
        out += _check_oyagui(w)
    elif w.kind in SHEET_KINDS:
        name, W, h, t, kg, Z, kgm2, rng = sheet_spec(w.kind, w.model)
        em = w.embed_mm
        if w.kind in ("sp_u", "sp_hat"):
            ok = em >= SP_EMBED_MIN_MM - 1e-6 or (w.depth <= 3000.0 and em >= w.depth / 2.0 - 1e-6)
            out.append(Check("根入れ", "OK" if ok else "WARN", f"{em:.0f}mm（最小 3.0m・小規模は掘削深の 1/2: 旧 土木要綱・道路土工 "
                                                             "仮設指針。つり合いは山留めの計算で）"))
            if w.kind == "sp_hat" and corners(w):
                out.append(Check("角", "注意", f"角 {corners(w)}か所: ハット形にコーナー矢板は無い → 異形鋼矢板か NSコネクター"
                                               "（JFE-FAQ Q3・日本製鉄 1-10）"))
            if w.kind == "sp_u" and corners(w):
                cn = "CⅢ" if w.model in ("II", "III", "IIIw") else "CⅣ" if w.model in ("IV", "IVw") else "異形鋼矢板"
                out.append(Check("角", "OK" if cn != "異形鋼矢板" else "注意", f"角 {corners(w)}か所: コーナー矢板 {cn}"
                                                                                f"（日本製鉄 1-3・JFE カタログ 印刷 p.12）"))
        if w.kind == "lsp":
            out.append(Check("掘削の深さ", "OK" if w.depth <= LSP_DEPTH_MM + 1e-6 else "WARN",
                             f"{w.depth / 1000:.1f}m（軽量鋼矢板は計算すれば 4m 程度まで: 横浜市 下水道設計指針 8-5）"))
        if w.kind == "alu":
            out.append(Check("掘削の深さ", "OK" if w.depth <= ALU_DEPTH_MM + 1e-6 else "WARN",
                             f"{w.depth / 1000:.1f}m（アルミ矢板は支保工 3段で 3.8m まで: 静岡市 土留工標準構造図）"))
            out.append(Check("根入れ", "OK" if em >= ALU_EMBED_MM - 1e-6 else "WARN", f"{em:.0f}mm（0.2m 以上: 静岡市）"))
        if rng:
            L = w.wall_len / 1000.0
            out.append(Check("長さ", "OK" if rng[0] - 1e-6 <= L <= rng[1] + 1e-6 else "WARN",
                             f"{L:.1f}m（{name} の長さ {rng[0]:g}〜{rng[1]:g}m: 軽量鋼矢板Q&A p.42・ホーシン）"))
        if w.kind in ("lsp", "alu"):
            out.append(Check("地下水", "注意", "止水性が無いので、掘削底より地下水位が高いと使わない（函館市 下水道の設計資料 p.36）"))
        out += [] if w.wales else [Check("支保工の段", "注意", _support_note(w))]
    elif w.kind == "tatekomi":
        n, hmax, *_rest = TATEKOMI[w.model]
        rng = TATEKOMI[w.model][8]
        out.append(Check("掘削の深さ", "OK" if w.depth <= hmax + 1e-6 else "NG", f"{w.depth / 1000:.1f}m（{n}: 日本スピードショア）"))
        widths = [e.width for e in w.edges if e.width > 0]
        if widths:
            wmax = max(widths)              # 狭い向き（切梁を渡す向き）の掘削幅
            ok = rng[0] - 1e-6 <= wmax <= min(rng[1], TATEKOMI_WIDTH_MAX_MM) + 1e-6
            out.append(Check("掘削幅", "OK" if ok else "NG", f"最大 {wmax:.0f}mm（{n} の外幅 {rng[0]:.0f}〜{rng[1]:.0f}・原則 4.7m 以下）"))
        else:
            out.append(Check("掘削幅", "注意", "向かいの土留めが無い（開いた線）ので切梁を描いていません。閉じた線か、向かいの線も選ぶ"))
        out.append(Check("地盤", "注意", "パネルの根入れが無いので、ボイリング（砂質土）・ヒービング（粘性土）の恐れのない地盤で。"
                                         "押込み前の先掘りは 50cm 以下（日本スピードショア）"))
    elif w.kind == "smw":
        out.append(Check("根入れ", "注意", f"{w.embed_mm:.0f}mm【目安】。根入れ・芯材は山留めの計算で"))
        out.append(Check("隣地", "注意", "壁芯から隣地まで 475〜610mm 以上（モテックの資料・原本未確認）"))
    elif w.kind == "koukan":
        out.append(Check("根入れ", "注意", f"{w.embed_mm:.0f}mm【目安】。根入れ・外径・板厚は山留めの計算で"))
    if w.wales:
        shape, _kg = wale_shape(w)
        gaps = [b - a for a, b in zip([0.0] + w.wales, w.wales)]
        out.append(Check("腹起しの段", "OK" if w.wales[0] <= WALE_FIRST_MM + w.top_up + 1e-6 and max(gaps[1:] or [0.0]) <= WALE_STEP_MM + 1e-6
                         else "注意", "・".join(f"GL-{z:.0f}" for z in w.wales) + f"（{shape}。第1段は頭から 1m 以内・その下 3m 程度: 九州 共2-24）"))
        sl = [v for e in w.edges for v in e.strut_len]
        if sl:
            out.append(Check("切梁", "注意", f"水平 {STRUT_PITCH_MM / 1000:g}m 以下に等分・長さ 最大 {2 * max(sl) / 1000:.1f}m（向かいまで）。継材は 4m 以内"
                             "（九州 共2-28）・中間杭・火打ち（45°）・プレロードは山留めの計算で"))
        elif w.closed:
            out.append(Check("切梁", "注意", "向かいの山留めまでの幅が分からないので切梁を描いていません"))
        else:
            out.append(Check("切梁", "注意", "開いた線なので切梁を描いていません（腹起しだけ）。切梁の受けは山留めの計算で"))
    if w.depth >= 1500.0 - 1e-6:
        out.append(Check("山留め", "OK", "深さ 1.5m 以上の根切りは山留めを設ける（建築基準法施行令 136条の3 第4項）"))
    if w.depth >= 2000.0 - 1e-6 and w.kind != "tatekomi":
        out.append(Check("作業主任者", "注意", "土止め支保工の切梁・腹起しの取付け・取外しは土止め支保工作業主任者（安衛法施行令 6条10号）。"
                                               "組立図（安衛則 370条）・7日以内ごとの点検（373条）"))
    return out


def _support_note(w: Wall) -> str:
    if w.kind in ("lsp", "alu"):
        d = w.depth
        n = 1 if d <= 2000.0 else 2 if d <= 3500.0 else 3
        return f"腹起し・切梁 {n}段の目安（2.0m 以下 1段・3.5m 以下 2段・それより深く 3段: 軽量鋼矢板Q&A p.36・静岡市）"
    z = wale_levels(w)
    return ("腹起し・切梁の段の目安 " + "・".join(f"GL-{v:.0f}" for v in z) + "（第1段は頭から 1m 以内・その下 3m 程度: 九州 共2-24）"
            if z else "自立の山留め（腹起し・切梁なし）にするかは山留めの計算で")


def _check_oyagui(w: Wall) -> list[Check]:
    H, B, t1, t2, kg = H_SHAPES[w.model]
    out = []
    pitches = [x1 - x0 for e in w.edges for x0, x1 in e.bays]
    pmax = max(pitches) if pitches else 0.0
    lo, hi = PILE_PITCH_RANGE
    out.append(Check("親杭の間隔", "OK" if lo - 1 <= pmax <= hi + 1 else "WARN",
                     f"芯々 最大 {pmax:.0f}mm（標準 1500・1000〜2000: 九州 共2-22）"))
    if w.depth >= H300_DEPTH_MM - 1e-6 and H < 300.0:
        out.append(Check("親杭の大きさ", "WARN", f"掘削 {w.depth / 1000:.1f}m は H-300 以上（九州 共2-32）。いまは {w.model}"))
    else:
        out.append(Check("親杭の大きさ", "OK", f"{w.model}（掘削 3m 以深は H-300 以上: 九州 共2-32）"))
    out.append(Check("根入れ", "OK" if w.embed_mm >= EMBED_MIN_MM - 1e-6 else "WARN",
                     f"{w.embed_mm:.0f}mm（50cm 単位に切り上げ。1.5m 以上・つり合い深さ×1.2 以上を山留めの計算で: 九州 共2-21）"))
    out.append(Check("横矢板の厚さ", "OK" if w.lag_t >= LAG_T_MIN_MM - 1e-6 else "NG",
                     f"{w.lag_t:.0f}mm（最小 30mm: 九州 共2-23・旧要綱 土木 第48）"))
    k = w.kakari_mm
    out.append(Check("掛かり代", "OK" if k >= KAKARI_SOIL_MIN_MM - 1e-6 else "注意",
                     f"{k:.0f}mm＝矢板の厚さ（旧要綱 建築 H5 第48「矢板の厚み以上」）"
                     + ("" if k >= KAKARI_SOIL_MIN_MM - 1e-6 else "。土木の要領は 40mm 以上かつ板厚以上（九州 共2-23）")))
    fit_max = pmax - t1 - 2 * INSERT_PLAY_MM
    Lmax = max((x for e in w.edges for x in e.lag_len), default=0.0)
    out.append(Check("矢板の入り", "OK" if Lmax <= fit_max + 1e-6 else "NG",
                     f"矢板 {Lmax:.0f}mm ≦ 芯々 − ウェブ − あそび 2×20 ＝ {fit_max:.0f}mm【目安】"))
    # 板厚の照査（九州 共2-23: t = √(6M / (b σa))、M = w ℓ² / 8、ℓ＝フランジ間の内法）。土圧は令136条の3 の深さ 3m 以内の簡便な値
    span = pmax - B
    if w.depth <= 3000.0 + 1e-6:
        p = 0.5 * 9.81 * w.depth / 1000.0                     # kN/m²（水圧の 50%）
        M = p * (span / 1000.0) ** 2 / 8.0 * 1e6               # N·mm（幅 1m）
        need = math.sqrt(6.0 * M / (1000.0 * SIGMA_SUGI))
        out.append(Check("横矢板の曲げ", "OK" if w.lag_t >= need - 1e-6 else "NG",
                         f"根切り底の土圧 {p:.1f}kN/m²（深さ 3m 以内の水圧の 50%: 令136条の3）・内法 {span:.0f}mm → 要る厚さ "
                         f"{need:.1f}mm（すぎ σa 10.3: 学会 山留め設計指針）"))
    else:
        out.append(Check("横矢板の曲げ", "注意", f"根切り {w.depth / 1000:.1f}m は 3m を超えるので、土圧と板厚は山留めの計算で（令136条の3）"))
    if len(w.stages) > 1:
        out.append(Check("根切りの段", "OK", "・".join(f"{s.name} GL-{s.bottom:.0f}" for s in w.stages)
                         + "。各段は矢板1枚分（200mm）ずつ掘って入れる（先行掘りしない: 作業手順書）"))
    out += [] if w.wales else [Check("支保工の段", "注意", _support_note(w))]
    out.append(Check("排水", "注意", "親杭横矢板は止水しない工法。背面に水がたまらないよう排水孔を（土木学会 年次講演 Ⅵ-212 p.424）"))
    return out


@dataclass
class Qty:
    item: str
    spec: str
    qty: float
    unit: str
    note: str = ""


def quantities(w: Wall) -> list[Qty]:
    """数量（積算の拾いと、手配の実数）."""
    out: list[Qty] = []
    perim = w.perimeter
    L = w.wall_len
    area_dig = perim * w.depth / 1e6
    if w.kind == "oyagui":
        H, B, t1, t2, kg = H_SHAPES[w.model]
        npile = sum(len(e.piles) for e in w.edges)
        out.append(Qty("親杭", f"{w.model}×{B:.0f}×{t1:g}×{t2:g} L={L / 1000:.1f}m", npile, "本",
                       f"延べ {npile * L / 1000:.1f}m・{npile * L / 1000 * kg / 1000:.2f}t（根入れ {w.embed_mm / 1000:.1f}m を含む）"))
        out.append(Qty("横矢板（積算）", f"根切り深さ {w.depth / 1000:.2f}m × 周長 {perim / 1000:.2f}m", area_dig, "m²",
                       "根入れ部は含まない（公共建築数量積算基準 R5 p.8）"))
        for s in w.stages:
            out.append(Qty(f"  横矢板 {s.name}", f"GL-{s.top:.0f}〜GL-{s.bottom:.0f}（{s.height / 1000:.2f}m）", perim * s.height / 1e6,
                           "m²", ""))
        nb = boards_per_stage(w.stages, w.lag_w)
        by_len: dict = {}
        for e in w.edges:
            for Lb in e.lag_len:
                for s, n in zip(w.stages, nb):
                    k = (s.name, round(Lb))
                    by_len[k] = by_len.get(k, 0) + n
        vol = 0.0
        for (sname, Lb), n in sorted(by_len.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
            vol += n * Lb * w.lag_w * w.lag_t / 1e9
            out.append(Qty(f"  横矢板の手配 {sname}", f"杉 {w.lag_t:.0f}×{w.lag_w:.0f} 切断 {Lb:.0f}mm（定尺 {stock_len(Lb):g}m から）", n,
                           "枚", f"掛かり代 {w.kakari_mm:.0f}mm×2"))
        out.append(Qty("  横矢板の材積", f"厚 {w.lag_t:.0f}×幅 {w.lag_w:.0f}", vol, "m³", "切断した長さで"))
        nbays = sum(len(e.bays) for e in w.edges)
        nboard = nbays * sum(nb)
        out.append(Qty("くさび", f"{WEDGE[0]:.0f}×{WEDGE[1]:.0f}×{WEDGE[2]:.0f}【目安】", nboard * 4, "個", "矢板1枚の左右に各2個（作業手順書）"))
        for s, n in zip(w.stages, nb):
            h = n * w.lag_w
            if h <= 0:
                continue
            st = next((x for x in SANKI_STOCK_M if x * 1000.0 >= h - 1e-6), SANKI_STOCK_M[-1])
            pieces = nbays * 2 * max(1, math.ceil(h / (st * 1000.0) - 1e-6))
            out.append(Qty(f"矢板止めの桟木 {s.name}", f"{SANKI[0]:.0f}×{SANKI[1]:.0f}【目安】 L={h / 1000:.2f}m（定尺 {st:g}m）", pieces, "本",
                           f"バイ {nbays}・両端に縦に釘止め（標準作業シート №3）"))
    elif w.kind in SHEET_KINDS:
        name, W, h, t, kg, Z, kgm2, rng = sheet_spec(w.kind, w.model)
        n = sum(e.units for e in w.edges)
        out.append(Qty(KIND_LABELS[w.kind], f"{name}（{W:.0f}×{h:.0f}×{t:g}） L={L / 1000:.1f}m", n, "枚",
                       f"{n * L / 1000 * kg / 1000:.2f}t（{kg:g}kg/m。枚数＝中心線 ÷ 有効幅の切り上げ: 農水 16-27）"))
        out.append(Qty("  壁の面積（根切り）", f"根切り深さ {w.depth / 1000:.2f}m × 延長 {perim / 1000:.2f}m", area_dig, "m²", ""))
        out.append(Qty("  延面積（矢板の長さ）", f"L {L / 1000:.1f}m × 延長 {perim / 1000:.2f}m", perim * L / 1e6, "m²",
                       "公共建築工事見積標準書式の見積条件"))
        out.append(Qty("  打込み・引抜き", f"L {L / 1000:.1f}m × {n}枚", n * L / 1000.0, "m", "見積標準書式（打込み費・引抜き費は m）"))
        nc = corners(w)
        if nc and w.kind == "sp_u":
            cn = "CⅢ" if w.model in ("II", "III", "IIIw") else "CⅣ" if w.model in ("IV", "IVw") else "異形鋼矢板"
            out.append(Qty("  コーナー矢板", f"{cn} L={L / 1000:.1f}m", nc, "枚", "角ごと（日本製鉄 1-3）"))
        elif nc and w.kind == "sp_hat":
            out.append(Qty("  角の継手", f"NSコネクター（非溶接 26.0kg/m）か異形鋼矢板 L={L / 1000:.1f}m", nc, "か所", "日本製鉄 1-10"))
    elif w.kind == "tatekomi":
        n, hmax, pl, pt, lower, upper, (rw, rd), rlen, rng = TATEKOMI[w.model]
        stack, kgp = tatekomi_stack(w)
        npan = sum(len(e.piles) - 1 for e in w.edges)
        nrail = sum(len(e.piles) for e in w.edges) - (len(w.edges) if w.closed else max(0, len(w.edges) - 1))
        RL, rkg = tatekomi_rail(w)
        out.append(Qty("たて込み簡易土留め", f"{n} 延長 {perim / 1000:.2f}m・掘削深 {w.depth / 1000:.2f}m", perim / 1000.0, "m",
                       "延長 m・掘削深・掘削幅ごと（農水 16-8）"))
        out.append(Qty("  土留めの面積", f"延長 × 掘削深", area_dig, "m²", "賃料は ㎡・供用日（農水 16-32）"))
        out.append(Qty("  パネル", f"長さ {pl:.0f}・厚 {pt:g}・積み " + "＋".join(f"{v:.0f}" for v in stack), npan, "組",
                       f"1組 {kgp:.0f}kg・計 {npan * kgp / 1000:.2f}t"))
        out.append(Qty("  スライドレール", f"{rw:.0f}×{rd:.0f} L={RL / 1000:.1f}m", nrail, "本", f"{nrail * rkg / 1000:.2f}t"))
        ns = sum(1 for e in w.edges for v in e.struts if v > 0) * len(strut_levels(w))
        if ns:
            out.append(Qty("  切梁（サポートジャッキ）", "・".join(f"GL-{z:.0f}" for z in strut_levels(w)) + "【段は目安】", ns / 2.0, "本",
                           "向かい合うレールの間（両側の部品で 1本）"))
    elif w.kind == "smw":
        D = float(w.model)
        tm, p = SMW[D]
        core = w.core or SMW_CORE[D]
        H, B, t1, t2, kg = H_SHAPES[core]
        nh = sum(len(e.piles) for e in w.edges)
        nc = sum(len(e.cores) for e in w.edges)
        out.append(Qty("ソイルセメント柱列壁", f"φ{D:.0f}@{p:.0f}・壁の長さ {L / 1000:.1f}m", perim * L / 1e6, "m²",
                       "柱列壁の延面積（見積標準書式）"))
        out.append(Qty("  削孔", f"φ{D:.0f} L={L / 1000:.1f}m", nh, "本", f"延べ {nh * L / 1000:.1f}m"))
        out.append(Qty("  削孔混練土量", f"平均壁厚 {tm:.0f} × 延長 × 長さ", tm / 1000.0 * perim / 1000.0 * L / 1000.0, "m³", "SMW 協会の平均壁厚"))
        out.append(Qty("  芯材", f"{core} L={L / 1000:.1f}m（{'全孔' if w.core_every == 1 else '1本おき'}）", nc, "本",
                       f"{nc * L / 1000 * kg / 1000:.2f}t"))
    elif w.kind == "koukan":
        D, t = w.tube_d, w.tube_t
        kgm = math.pi * (D - t) * t * 7.85e-3
        jk = math.pi * (JOINT_D_MM - JOINT_T_MM) * JOINT_T_MM * 7.85e-3
        n = sum(len(e.piles) for e in w.edges)
        out.append(Qty("鋼管矢板", f"φ{D:.0f}×{t:g} L={L / 1000:.1f}m", n, "本", f"{n * L / 1000 * kgm / 1000:.2f}t（{kgm:.1f}kg/m）"))
        out.append(Qty("  継手 P-P", f"φ{JOINT_D_MM:g}×{JOINT_T_MM:g}（{jk:.1f}kg/m）", n * 2, "本", "1本の両側に（標準製作仕様 p.3）"))
    if w.wales:
        out += support_quantities(w)
    return out


def support_quantities(w: Wall) -> list[Qty]:
    """腹起し・ブラケット・裏込め・切梁の数量（主部材は積上げ t: 国総研 数量要領 R8 1-11-4、切梁の積算は各段の根切り面積: 公共建築数量
    積算基準 R5 p.8）."""
    shape, kg = wale_shape(w)
    H, B, *_ = H_SHAPES[shape]
    nl = len(w.wales)
    L = sum(e.wale_x[1] - e.wale_x[0] for e in w.edges)
    out = [Qty("腹起し", f"{shape}（{kg:g}kg/m）・" + "・".join(f"GL-{z:.0f}" for z in w.wales), L * nl / 1000.0, "m",
               f"{L * nl / 1000.0 * kg / 1000.0:.2f}t（{nl}段。壁とのすき間 {WALE_GAP_MM:.0f}: ヒロセ p.6）"),
           Qty("  腹起しのブラケット", f"{BRACKET_PITCH_MM / 1000:g}m ピッチ・両端に", sum(len(e.brackets) for e in w.edges) * nl, "個",
               "腹起し1本に2個以上（施工計画書例・ヒロセ p.5）"),
           Qty("  裏込め", f"すき間 {WALE_GAP_MM:.0f} × 腹起しの高さ {B:.0f}", WALE_GAP_MM / 1000.0 * B / 1000.0 * L / 1000.0 * nl, "m³",
               "コンクリート・既製の裏込め材（ヒロセ p.6）")]
    pairs = sum(len(e.strut_x) for e in w.edges) / 2.0
    if pairs:
        slen = sum(sum(e.strut_len) for e in w.edges)
        out.append(Qty("切梁", f"{shape} 水平 {STRUT_PITCH_MM / 1000:g}m 以下・{nl}段", pairs * nl, "本",
                       f"延べ {slen * nl / 1000.0:.1f}m・{slen * nl / 1000.0 * kg / 1000.0:.2f}t（ジャッキ・火打ちは別）"))
        area = abs(_area(inner_polygon(w))) / 1e6 if w.closed else 0.0
        if area:
            out.append(Qty("  切梁（積算）", f"根切り面積 {area:.1f}m² × {nl}段", area * nl, "m²", "各段ごとの根切り面積（公共建築数量積算基準 R5 p.8）"))
    return out


def _area(pts) -> float:
    return sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts))) / 2.0 if pts else 0.0


def report(walls: list[Wall]) -> str:
    lines = ["# 山留め壁", ""]
    for w in walls:
        lines += [f"## {w.name}（{KIND_LABELS.get(w.kind, w.kind)}）", "",
                  f"- 根切り GL-{w.depth:.0f}・天端 GL+{w.top_up:.0f}・根入れ {w.embed_mm:.0f}・長さ {w.wall_len / 1000:.1f}m・辺 {len(w.edges)}・"
                  f"周長 {w.perimeter / 1000:.2f}m", ""]
        if len(w.stages) > 1:
            lines += ["- 根切りの段: " + "・".join(f"{s.name} GL-{s.top:.0f}〜GL-{s.bottom:.0f}" for s in w.stages), ""]
        lines += ["| 項目 | 仕様 | 数量 | 単位 | 備考 |", "|---|---|---:|---|---|"]
        for q in quantities(w):
            v = f"{q.qty:.2f}" if q.unit in ("m²", "m³", "t", "m") else f"{q.qty:g}"
            lines.append(f"| {q.item} | {q.spec} | {v} | {q.unit} | {q.note} |")
        lines += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        lines += [f"| {c.item} | {c.status} | {c.message} |" for c in w.checks]
        lines.append("")
    lines += ["## 出典", ""] + [f"- {v}" for v in SOURCES.values()] + [""]
    return "\n".join(lines)


# ---- 部品のパラメータ ----

def _mm(vals) -> str:
    return ",".join(f"{v:.1f}" for v in vals)


def _offset(pts: list, d: float) -> list:
    """折れ線を左へ d だけずらす（角は留め継ぎ）."""
    out = []
    n = len(pts)
    for i in range(n):
        segs = []
        if i > 0:
            segs.append((pts[i - 1], pts[i]))
        if i < n - 1:
            segs.append((pts[i], pts[i + 1]))
        nx = ny = 0.0
        for a, b in segs:
            L = math.dist(a, b) or 1.0
            nx += -(b[1] - a[1]) / L
            ny += (b[0] - a[0]) / L
        L = math.hypot(nx, ny) or 1.0
        nx, ny = nx / L, ny / L
        if len(segs) == 2:
            a, b = segs[0]
            L0 = math.dist(a, b) or 1.0
            cosh = nx * (-(b[1] - a[1]) / L0) + ny * ((b[0] - a[0]) / L0)
            k = d / max(cosh, 0.3)
        else:
            k = d
        out.append((pts[i][0] + nx * k, pts[i][1] + ny * k))
    return out


def sheet_profile(kind: str, model: str) -> list:
    """鋼矢板1枚の断面の外形（mm。x＝0〜W、継手は x＝0 と W）. 寸法は有効幅・高さ・板厚から【形の割合は目安】."""
    _n, W, h, t, *_ = sheet_spec(kind, model)
    hc = h / 2.0 - t / 2.0
    if kind == "sp_hat":
        a, wb = 0.11 * W, 0.13 * W
        cl = [(0.0, -hc), (a, -hc), (a + wb, hc), (W - a - wb, hc), (W - a, -hc), (W, -hc)]
    else:
        wb = 0.28 * W
        cl = [(0.0, 0.0), (wb, hc), (W - wb, hc), (W, 0.0)]
    left, right = _offset(cl, t / 2.0), _offset(cl, -t / 2.0)
    return left + list(reversed(right))


def part_params(w: Wall, e: Edge) -> dict:
    """部品 ashiba_ywall のパラメータ（m。並びは mm の文字列）."""
    p = {"ywKind": KIND_NO[w.kind], "ywL": e.length / 1000.0, "zTop": w.top_up / 1000.0,
         "zBot": -(w.depth + w.embed_mm) / 1000.0, "digD": w.depth / 1000.0,
         "stD": _mm(s.bottom for s in w.stages), "pX": _mm(e.piles), "ywName": e.name,
         "ywInfo": label(w), "faceY": face_offset(w) / 1000.0}
    p["wlOn"] = bool(w.wales)
    if w.wales:
        H, B, t1, t2, _kg = H_SHAPES[wale_shape(w)[0]]
        p.update({"wlZ": _mm(w.wales), "wlH": H / 1000.0, "wlB": B / 1000.0, "wlT1": t1 / 1000.0, "wlT2": t2 / 1000.0,
                  "wlGap": WALE_GAP_MM / 1000.0, "wlX0": e.wale_x[0] / 1000.0, "wlX1": e.wale_x[1] / 1000.0,
                  "brX": _mm(e.brackets), "sbX": _mm(e.strut_x), "sbL": _mm(e.strut_len)})
    if w.kind == "tatekomi":
        p["zBot"] = -w.depth / 1000.0
        p["zTop"] = (tatekomi_rail(w)[0] - w.depth) / 1000.0
    if w.kind in ("oyagui", "smw"):
        key = w.model if w.kind == "oyagui" else (w.core or SMW_CORE[float(w.model)])
        H, B, t1, t2, _kg = H_SHAPES[key]
        p.update({"hH": H / 1000.0, "hB": B / 1000.0, "hT1": t1 / 1000.0, "hT2": t2 / 1000.0})
    if w.kind == "oyagui":
        H, B, *_ = H_SHAPES[w.model]
        k = w.kakari_mm
        p.update({"lagT": w.lag_t / 1000.0, "lagW": w.lag_w / 1000.0, "kak": k / 1000.0, "lagGap": WEDGE_GAP_MM / 1000.0,
                  "lgA": _mm(a for a, _b in e.lag_ab), "lgB": _mm(b for _a, b in e.lag_ab),
                  "lgN": _mm(float(n) for n in boards_per_stage(w.stages, w.lag_w)),
                  "skW": SANKI[0] / 1000.0, "skT": SANKI[1] / 1000.0})
    elif w.kind in SHEET_KINDS:
        _n, W, h, t, *_ = sheet_spec(w.kind, w.model)
        prof = sheet_profile(w.kind, w.model)
        p.update({"spW": W / 1000.0, "spT": t / 1000.0, "spH": h / 1000.0, "nU": e.units, "spAlt": w.kind != "sp_hat",
                  "prX": _mm(q[0] for q in prof), "prY": _mm(q[1] for q in prof)})
    elif w.kind == "smw":
        D = float(w.model)
        p.update({"smD": D / 1000.0, "coreX": _mm(e.cores)})
    elif w.kind == "koukan":
        p.update({"tbD": w.tube_d / 1000.0, "tbT": w.tube_t / 1000.0, "jD": JOINT_D_MM / 1000.0})
    elif w.kind == "tatekomi":
        _n, _hm, pl, pt, *_r = TATEKOMI[w.model]
        rw, rd = TATEKOMI[w.model][6]
        stack, _kg = tatekomi_stack(w)
        p.update({"pnT": pt / 1000.0, "pnH": _mm(stack), "rlW": rw / 1000.0, "rlD": rd / 1000.0,
                  "stY": _mm(e.struts), "stZ": _mm(w.depth - z for z in strut_levels(w)), "stDia": STRUT_DIA_MM / 1000.0})
    return p


def label(w: Wall) -> str:
    """平面の注記（施工図の本 p.38〜39 の書き方: 種類・型式・ピッチ・長さ）."""
    L = w.wall_len / 1000.0
    if w.kind == "oyagui":
        return f"親杭 {w.model} @{w.pitch:.0f} L={L:.1f}m・横矢板 t{w.lag_t:.0f}"
    if w.kind in SHEET_KINDS:
        return f"{KIND_LABELS[w.kind]} {sheet_spec(w.kind, w.model)[0]} L={L:.1f}m"
    if w.kind == "smw":
        D = float(w.model)
        return f"SMW φ{D:.0f}@{SMW[D][1]:.0f} L={L:.1f}m・芯材 {w.core or SMW_CORE[D]}" + ("" if w.core_every == 1 else " 1本おき")
    if w.kind == "koukan":
        return f"鋼管矢板 φ{w.tube_d:.0f}×{w.tube_t:g} L={L:.1f}m"
    return f"たて込み簡易土留め {TATEKOMI[w.model][0]} H={w.depth / 1000:.1f}m"


def face_offset(w: Wall) -> float:
    """山留めの線から根切りの側の面までの距離 mm（根切り図が掘る範囲）."""
    if w.kind == "oyagui":
        return H_SHAPES[w.model or default_model(w.kind)][0] / 2.0
    if w.kind in SHEET_KINDS:
        return sheet_spec(w.kind, w.model or default_model(w.kind))[2] / 2.0
    if w.kind == "smw":
        return float(w.model or default_model(w.kind)) / 2.0
    if w.kind == "koukan":
        return w.tube_d / 2.0
    return TATEKOMI[w.model or default_model(w.kind)][3]


def inner_polygon(w: Wall) -> list:
    """閉じた山留めの根切りの側の面の多角形（mm）. 時計回りの線を右（中）へ face_offset だけずらし、隣の辺どうしを交わらせる."""
    if not w.closed or len(w.pts) < 3:
        return []
    pts = orient(w.pts, True)
    d = face_offset(w)
    lines = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        L = math.dist(a, b) or 1.0
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        nrm = (u[1], -u[0])                                # 右（根切りの中）
        lines.append(((a[0] + nrm[0] * d, a[1] + nrm[1] * d), u))
    out = []
    for k in range(len(lines)):
        (p1, u1), (p2, u2) = lines[k - 1], lines[k]
        den = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(den) < 1e-9:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / den
        out.append((p1[0] + u1[0] * t, p1[1] + u1[1] * t))
    return out
