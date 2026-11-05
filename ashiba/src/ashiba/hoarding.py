"""仮囲い（利用者の指定 2026-11-01: 仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ。
同日: ゲート 仮囲いに必要な部材リサーチして → 全部入れて 3Dも詳細度上げて）.
部品 ashiba_kakoi（線・ポリラインの1区間に1つ）。

組み方の主な出典は日建リース工業 仮設資材カタログ Vol.10（安全鋼板 p398〜399・VICパネル p400〜403・キャスターゲート p404〜410・
仮囲安全鋼板の検討 p453〜456・単管 p372・ベースアンカー p377・兼用クランプ p378）。ほかにミルックスの 3m 仮囲い計画図・藤田の
安全鋼板の拾い方・鈴東の数量計算。
- 単管 φ48.6×2.4（STK500）の支柱を 1,800 ごとに立て（打込みは根入れ 1,000）、天端はパネルの上端から 150 上。外に横地（布単管）を
  直交クランプ（ARC1）でパネルの取付穴の高さに: 安全鋼板 SSK300 は下から 150・1,500・2,850、SSK400 は 150・1,350・2,650・3,850、
  SSK230 は 150・1,150・2,150、SSK200 は 150・1,850。パネルの下端は地盤（日建の標準施工図。浮かす・根入れも選べる）
- 安全鋼板は有効幅 540・t1.2（2,000 12.1kg・2,300 14.2kg・3,000 18.1kg・4,000 24.1kg。パンチングもある）をフックボルト SSKFB
  （φ9）で。フラットパネル（VIC。有効幅 500・3,000 16.5kg）は C型金具（VIC-Cカナグ）で1枚に 6（3m）・4（2m）、半端は調整Nパネル
  （40〜440）、角は自在コーナーパネル（240＋240。出隅 70〜180°・入隅 60〜180°）、開き止め金具は 40スパンに 3
- 控え柱（単管）は支柱ごとに中へ: 上段の横地から 750 下（3m で高さ 2,100）に自在クランプ（ARC2）で掛け、後ろ 1,550・地上 150 の
  根がらみ（単管）と打込みパイプ（くい丸 1.5M）へ（約 51°）。高さが変われば同じ勾配で後ろを伸ばす
- 風: 日建の「仮囲安全鋼板の検討」の通りに q＝5V²/8・風力係数 1.3 で、パネル・横地・支柱（片持ちと両端支持）・控え（座屈）・
  控えの自在クランプ（3.43kN×1.3）・基礎（打込みは Meyerhof、N値 20 の砂。根巻きは □300×400、地耐力 147kN/m²）を確かめ、
  この組で持つ風速を出す。H形鋼は転倒（安全率 1.5）、ベースアンカーは要る引抜き耐力を出す
- ゲート: キャスターゲート（CG。ジャバラ・本体 H1,800・キャスター込み 1,930）・パネルキャスターゲート（PCG。アルミパネル付き）・
  ローキャスターゲート（H1,250）は 900 のユニットを並べ、片開き 0.9〜8.1m・両開き 3.6〜16.2m。部材はカタログの部材数量表どおり。
  畳むとユニット1つで厚さ 260＋支柱 90×2 が間口に残るので、通れる幅を出す。ドアはドアパネル VICD200（W500・扉 413）と
  ワイドドアパネル VICDW200（W1,000・扉 910）、上に調整パネル VIC100
- 基礎: 打込み・根巻きコンクリート（□300×400）・H形鋼（H-300 を2列 1,700 幅で敷き、キャッチクランプ。パネルの下端は H形鋼の
  上）・ベースアンカー（NBAK。
  コンクリートの上。□140 t9・φ48.6×3.2 H309）
- H形鋼の基礎は転倒（安全率 1.5）が足りなければコンクリートウェイト（□600・約 500kg。H形鋼にチェーンで縛る）を、外からの風には
  前の列の内側、中からの風には後ろの列の手前にスパンごとに足す（利用者の指定 2026-11-01: H形鋼の転倒はウェイトを足して直して）
- 山留めから取る（利用者の指定 同日: 山留めからとるパターンあるよね → 控えだけ 山留めで取るってこと Hこうで仮囲いとるのもあるね）:
  ・山留め控え: 仮囲いは道路の側に単管の打込みで立て、控え・根がらみの足だけを山留めの親杭に取る。足は親杭の根切りの側のフランジに
    単管 1.0m の立てをキャッチクランプ（H形鋼用）2個1組で留め、控えは自在・根がらみは直交で。支柱は親杭の真正面（親杭の間隔の
    倍数で 1,800 以内）にそろえ、控えは山留めへまっすぐ。控えの後ろ＝仮囲いから親杭の芯まで＋親杭の半分＋単管の半径
  ・親杭支柱: 根切りの際で控えを下ろす所もないとき、親杭（H形鋼）を地上へ継ぎ足して支柱にする（鈴東の H形鋼支柱杭式＝控えなしで
    H形鋼の曲げで持つ、カワモリ産業の杭の打てない所は山留材の例）。横地は親杭の外のフランジにキャッチクランプ
  どちらも親杭に風の力が加わるので山留めの設計者に確かめる（WARN）
- 斜めの角は自在コーナー、直交しない単管は自在クランプ
- 単管シート仮囲い（利用者の指定 2026-11-06「単管シート仮囲いH1.8mも追加して」）: 単管の支柱と横地に防炎シート 1.8×5.4m（ハトメ 45cm・32個:
  販売品の規格 ユタカメイク・ミスミ）を結束バンドで。組み方の基準は見つからず、支柱 1.8m・横地 3段（150・900・1,650）・シートの重さは【目安】
法令: 建築基準法施行令 136条の2の20（木造で高さ 13m・軒の高さ 9m を超える、または木造以外で2階以上の工事は高さ 1.8m 以上の
仮囲い）、建設工事公衆災害防止対策要綱 建築工事等編 第21（1.8m 以上、特に必要なら 3m。強風で倒れない構造。出入口は普段閉めて
引戸か内開き）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

POST_PITCH_MM = 1800.0             # 支柱の間隔
LIFT_MM = 0.0                      # パネルの下端（地盤から。日建の標準施工図は地盤）
RAIL_EDGE_MM = 150.0               # 横地はパネルの上端・下端からこれだけ内（取付穴の表に無い高さ）
POST_TOP_MM = 0.0                  # 支柱の天端はパネルの上端にそろえる（日建の図は上 150。利用者の指摘 2026-11-06「仮囲いから単管はみ出ている」）
EMBED_MM = 1000.0                  # 打込みの根入れ
RAIL_OFF_MM = 48.6                 # 横地の芯は支柱の芯から外へ（φ48.6 どうし）
PANEL_OFF_MM = 48.6 + 24.3 + 2.0   # 安全鋼板の裏は支柱の芯から外へ（横地の外面＋フック）
FLAT_OFF_MM = 48.6 + 24.3 + 28.0   # フラットパネル（VIC）は縁の折り返し 28 が横地に当たる（C型金具の取付方）
BRACE_DROP_MM = 750.0              # 控えは上段の横地からこれだけ下に掛ける
BRACE_SLOPE = 1550.0 / 1950.0      # 控えの後ろ ÷ 控えの高さ（根がらみから。日建 3m: 高さ 2,100−150 に後ろ 1,550）
ROOT_Z = {"打込み": 150.0, "根巻き": 150.0, "H形鋼": 450.0, "アンカー": 200.0, "親杭支柱": 150.0, "山留め控え": 150.0}   # 控えの足（根がらみ・H形鋼の上・アンカーの筒）
H_BEAM_GAP_MM = 1700.0             # H形鋼の基礎の2列の幅
H_BEAM_KG_M = 94.0                 # H-300×300×10×15
WEIGHT_KG, WEIGHT_MM = 500.0, 600.0   # コンクリートウェイト □600（0.216m³×2.3t）
WEIGHT_Y_MM = 160.0 + 300.0        # ウェイトの芯は H形鋼の芯から 460 内（フランジの縁から 10 あけて □600）
# 山留めの親杭（H形鋼）: 名前 → (幅・せい mm, 断面係数 Zx cm³, kg/m)
PILES = {"H-200": (200.0, 472.0, 49.9), "H-250": (250.0, 720.0, 72.4), "H-300": (300.0, 1360.0, 94.0),
         "H-350": (350.0, 2280.0, 137.0)}
PILE_PITCH_MM = 1200.0             # 親杭の間隔（既定。山留めの図面の値を --pile-pitch で）
CORNER_MIN_OUT, CORNER_MIN_IN = 70.0, 60.0   # 自在コーナー（日建 VICC・鈴東）が受けられる角（内角。出隅・入隅）
CORNER_LEAF_MM = 240.0             # 自在コーナーパネルの片側
DESIGN_WIND_MS = 25.0              # 既定の設計風速（国交省 雪寒仮囲い要領の最大 25m/s）
SOIL_N = 20.0                      # 打込みの杭の地盤（N値。日建の検討は砂・中位〜密の 20）
# 単管 φ48.6×2.4 STK500・安全鋼板 SS400（日建 p453）
TUBE_Z, TUBE_A, TUBE_I = 3.83, 3.483, 1.64          # cm³・cm²・cm（断面二次半径）
FB_TUBE, F_TUBE, FB_PANEL = 23520.0, 35280.0, 15680.0   # N/cm²
E_STEEL = 2.05e7
CLAMP_SWIVEL_N = 3430.0            # 自在クランプ ARC2 のすべり耐力（短期は 3割増し）
CLAMP_SUPER_N = 8820.0             # スーパー自在クランプ S2C
PILE_D_M, PILE_H_M = 0.0486, 0.9   # 打込みパイプの径・地中の長さ
CONC_B_M, CONC_D_M = 0.3, 0.4      # 根巻きコンクリート □300×400
SOIL_BEARING = 147.0               # 地耐力 kN/m²（日建の検討）
G = 9.80665

SSK_ROWS = {2000: (150.0, 1850.0), 2300: (150.0, 1150.0, 2150.0), 3000: (150.0, 1500.0, 2850.0),
            4000: (150.0, 1350.0, 2650.0, 3850.0)}   # 安全鋼板の取付穴の高さ（下から。日建 p398）


SHEET_KIND = 6                     # 単管シート仮囲いの kkType
SHEET_EYELETS = 32                 # 防炎シート 1.8×5.4m のハトメの数（45cm ごと: ユタカメイク・ミスミ）


@dataclass(frozen=True)
class Panel:
    kind: int                      # 部品の kkType
    name: str
    eff: float                     # 有効幅（働き幅）mm
    kg: dict                       # 高さ mm → 1枚の重さ kg
    rows: Optional[dict]           # 高さ mm → 取付穴（横地）の高さ（下から）。無ければ上下 150 と中
    fixer: str
    code: dict = field(default_factory=dict)        # 高さ mm → 品番
    off: float = PANEL_OFF_MM      # パネルの裏は支柱の芯から外へ
    z_cm3: float = 0.0             # 1枚の断面係数（風の検討）
    lift: float = LIFT_MM

    def label(self, height: float) -> str:
        c = self.code.get(int(height), "")
        return f"{self.name}{' ' + c if c else ''} H{height:.0f}"


PANELS = {
    "安全鋼板": Panel(1, "安全鋼板", 540.0, {2000: 12.1, 2300: 14.2, 3000: 18.1, 4000: 24.1}, SSK_ROWS,
                  "フックボルト SSKFB", {2000: "SSK200", 2300: "SSK230", 3000: "SSK300", 4000: "SSK400"}, z_cm3=2.25),
    "安全鋼板（パンチング）": Panel(5, "安全鋼板（パンチング）", 540.0, {2000: 9.7, 2300: 11.3, 3000: 14.2, 4000: 18.7}, SSK_ROWS,
                           "フックボルト SSKFB", {2000: "SSKP200", 2300: "SSKP230", 3000: "SSKP300", 4000: "SSKP400"},
                           z_cm3=2.25),
    "フラットパネル": Panel(2, "フラットパネル", 500.0, {1000: 5.5, 2000: 11.1, 3000: 16.5}, None, "C型金具（VIC-Cカナグ）",
                     {1000: "VIC100", 2000: "VIC200", 3000: "VIC300"}, FLAT_OFF_MM, 2.98),
    "防音パネル": Panel(3, "防音パネル（アドフラット防音）", 500.0, {3000: 18.8}, None, "Jフック", {}, FLAT_OFF_MM, 2.98),
    "メッシュフェンス": Panel(4, "メッシュフェンス（ガードフェンス）", 1800.0, {1800: 12.0}, None, "番線", lift=50.0),
    "単管シート": Panel(SHEET_KIND, "防炎シート 1.8×5.4m", 5400.0, {1800: 2.0}, {1800: (150.0, 900.0, 1650.0)}, "結束バンド"),
}
FOUNDATIONS = {"打込み": 1, "根巻き": 2, "H形鋼": 3, "アンカー": 4, "親杭支柱": 5, "山留め控え": 6}
FOUNDATION_ALIAS = {"山留め": "山留め控え", "H鋼": "親杭支柱", "H鋼支柱": "親杭支柱"}
PILE_GRID = ("親杭支柱", "山留め控え")      # 支柱を親杭の位置にそろえる基礎
WALL_DIST_MM = 1000.0              # 山留め控え: 仮囲いの芯から親杭の芯まで（既定。山留め（壁）を選べばそこから測る）


@dataclass(frozen=True)
class Gate:
    kind: int                      # 部品の gateK
    name: str
    code: str                      # 品番の頭（キャスターは CG・PCG。ドアは品番）
    body_h: float                  # 本体の高さ
    all_h: float                   # キャスター込みの高さ
    unit_kg: float = 0.0           # 単スパン（900）1つ
    post_kg: float = 0.0           # 中央支柱・側支柱 1本
    panel_kg: float = 0.0          # アルミパネル 1枚（パネルキャスター）
    door_w: float = 0.0            # ドアの幅（ドアのみ）
    leaf_w: float = 0.0            # 扉の幅
    door_kg: float = 0.0
    low: bool = False

    @property
    def is_door(self) -> bool:
        return self.door_w > 0


GATES = {
    "パネルキャスター": Gate(1, "パネルキャスターゲート", "PCG", 1800.0, 1930.0, 26.0, 4.0, 8.2),
    "キャスター": Gate(2, "キャスターゲート", "CG", 1800.0, 1930.0, 26.0, 4.0),
    "ドア": Gate(3, "ドアパネル", "VICD200", 2000.0, 2000.0, door_w=500.0, leaf_w=413.0, door_kg=23.0),
    "ローキャスター": Gate(4, "ローキャスターゲート", "CG", 1250.0, 1380.0, 20.0, 3.0, low=True),
    "ワイドドア": Gate(5, "ワイドドアパネル", "VICDW200", 2000.0, 2000.0, door_w=1000.0, leaf_w=910.0, door_kg=44.0),
}
GATE_ALIAS = {"ジャバラ": "キャスター", "クロス": "キャスター"}
CASTER_UNIT_MM = 900.0             # 単スパンの幅
FOLD_UNIT_MM, FOLD_POST_MM = 260.0, 90.0   # 畳んだ単スパンの厚さ・中央支柱／側支柱（30＋60）
# キャスターゲートの部材数量表（日建 p405・407・409）: ユニットの数 → (ダブルキャスター, シングルキャスター, 落とし棒)
CASTER_SINGLE = {1: (0, 1, 0), 2: (0, 1, 0), 3: (1, 2, 0), 4: (1, 2, 0), 5: (2, 2, 1), 6: (2, 2, 1), 7: (3, 2, 2),
                 8: (3, 2, 2), 9: (4, 2, 3)}
CASTER_DOUBLE = {4: (0, 2, 0), 5: (1, 3, 0), 6: (2, 4, 0), 7: (2, 4, 0), 8: (2, 4, 1), 9: (3, 4, 1), 10: (4, 4, 2),
                 11: (4, 4, 2), 12: (4, 4, 2), 13: (5, 4, 3), 14: (6, 4, 4), 15: (6, 4, 4), 16: (6, 4, 4), 17: (7, 4, 5),
                 18: (8, 4, 6)}
SOURCES = ("日建リース工業 仮設資材カタログ Vol.10（安全鋼板 p398〜399・VICパネル p400〜403・キャスターゲート p404〜410・"
           "仮囲安全鋼板の検討 p453〜456）・ミルックス 3m 仮囲い計画図・藤田 安全鋼板の拾い方・鈴東 数量計算、"
           "建築基準法施行令 136条の2の20、建設工事公衆災害防止対策要綱 建築工事等編 第21")


def gate_kind(text: str) -> tuple[str, Optional[bool]]:
    """ゲートの種類の文字 → (GATES の鍵, 両開きか。指定なしは None)。「キャスター両開き」「ジャバラ」も."""
    t = text.strip()
    dbl: Optional[bool] = None
    for w, v in (("両開き", True), ("片開き", False)):
        if t.endswith(w):
            t, dbl = t[: -len(w)].rstrip(":："), v
    t = GATE_ALIAS.get(t, t) or "キャスター"
    if t not in GATES:
        raise ValueError(f"ゲートの種類は {'・'.join(GATES)} のどれか（{text}）")
    return t, dbl


@dataclass
class GateLayout:
    gate: Gate
    width: float                   # 間口（ドアは扉の枠の幅）
    units: int = 0                 # 単スパンの数
    leaves: tuple = (0, 0)         # 始めの側・終わりの側のユニットの数（片開きは終わりの側に固定＝右固定）
    clear: float = 0.0             # 畳んだ（開けた）ときに通れる幅
    parts: list = field(default_factory=list)       # [(品名, 数, 1つの重さ kg)]

    @property
    def double(self) -> bool:
        return self.leaves[0] > 0 and self.leaves[1] > 0

    @property
    def kg(self) -> float:
        return sum(n * w for _a, n, w in self.parts)

    @property
    def set_code(self) -> str:
        g = self.gate
        if g.is_door:
            return g.code
        return f"{g.code}{round(self.units * 9):02d}{'S' if g.low else 'N'}{'W' if self.double else 'N'}"


def gate_layout(width: float, kind: str, top: float = 3000.0) -> GateLayout:
    """ゲート1つの割付と部材（日建の部材数量表）。width は指定の間口、top は仮囲いのパネルの上端."""
    key, dbl = gate_kind(kind)
    g = GATES[key]
    if g.is_door:
        if key == "ドア" and width >= 900.0:
            g = GATES["ワイドドア"]
        lay = GateLayout(g, g.door_w, clear=g.leaf_w)
        lay.parts.append((f"{g.name} {g.code}（W{g.door_w:.0f}・扉 {g.leaf_w:.0f}×H2000）", 1, g.door_kg))
        n_adj = max(0, round((top - 2000.0) / 1000.0)) * (2 if g.door_w > 500.0 else 1)
        if n_adj:
            lay.parts.append(("ドアパネル用調整パネル VIC100", n_adj, 5.5))
        if g.door_w > 500.0:
            lay.parts.append(("C型金具（VIC-Cカナグ）", 8 if n_adj else 4, 0.0))
        else:
            lay.parts.append(("VICドアパネル連結金具", 4, 0.0))
            if n_adj:
                lay.parts.append(("C型金具（VIC-Cカナグ）", 4 * n_adj, 0.0))
        lay.parts.append(("ドアパネル用支柱パイプ（単管）", 2, 0.0))
        return lay
    n = max(1, math.ceil(width / CASTER_UNIT_MM - 1e-6))
    double = dbl if dbl is not None else n > 9
    if double and n < 4:
        double = False
    if not double and n > 9:
        double = True
    n_tab = min(n, 18 if double else 9)
    leaves = (n // 2, n - n // 2) if double else (0, n)
    clear = width - sum(k * FOLD_UNIT_MM + 2 * FOLD_POST_MM for k in leaves if k > 0)
    dw, sw, drop = (CASTER_DOUBLE if double else CASTER_SINGLE)[n_tab]
    s = "S" if g.low else ""
    lay = GateLayout(g, width, n, leaves, clear)
    lay.parts += [(f"単スパン CG09A{s}", n, g.unit_kg), (f"中央支柱 CG09C{s}", 2 if double else 1, g.post_kg),
                  (f"側支柱 CG09G{s}", 2 if double else 1, g.post_kg), ("ダブルキャスター CG09W", dw, 5.0),
                  ("シングルキャスター CG09S", sw, 3.0), ("落とし棒 CG09B", drop, 2.0)]
    if not double:
        lay.parts.append(("片開き用鍵受け CG09K", 1, 0.5))
    if g.panel_kg:
        lay.parts.append(("アルミパネル NCGAPF", n, g.panel_kg))
    lay.parts = [x for x in lay.parts if x[1] > 0]
    return lay


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Segment:
    """仮囲いの1区間（線・ポリラインの1辺）。外（道路の側）は進む向きの右（部品の −Y）."""
    p0: tuple
    p1: tuple
    ext0: float = 0.0              # パネル・横地を始めの角で延ばす長さ（出隅＋、入隅−）
    ext1: float = 0.0
    post0: bool = True             # 始めの角に支柱を立てる（前の辺と共有するなら False）
    turn0: float = 0.0             # 始めの角の折れ（度。左へ＋）。角が無ければ 0
    turn1: float = 0.0

    @property
    def length(self) -> float:
        return math.dist(self.p0, self.p1)

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.p1[1] - self.p0[1], self.p1[0] - self.p0[0]))


def _turn(a, b, c) -> float:
    """a→b→c の折れ（度。左へ曲がると＋）."""
    t1 = math.atan2(b[1] - a[1], b[0] - a[0])
    t2 = math.atan2(c[1] - b[1], c[0] - b[0])
    d = math.degrees(t2 - t1)
    return (d + 180.0) % 360.0 - 180.0


def _ext(turn_deg: float, off: float) -> float:
    """角で外の面（芯から off 外）を延ばす長さ。左へ曲がる角は外が出隅（＋）、右は入隅（−）."""
    return off * math.tan(math.radians(abs(turn_deg)) / 2.0) * (1.0 if turn_deg > 0 else -1.0)


def polyline_layout(pts: list, closed: bool = False, outside_right: bool = True, off: float = PANEL_OFF_MM) -> list[Segment]:
    """点列 → 区間。斜めの辺も同じ（区間ごとに向きを持つ）。外は進む向きの右（outside_right=False なら左にそろえるため
    点列を逆に回す）。角の支柱は前の辺と共有し、パネル・横地は角の二等分線まで延ばす・縮める."""
    p = [tuple(map(float, q)) for q in pts]
    if closed and len(p) > 2 and math.dist(p[0], p[-1]) < 1.0:
        p = p[:-1]
    if not outside_right:
        p = p[::-1]
    p = [q for i, q in enumerate(p) if i == 0 or math.dist(q, p[i - 1]) > 1.0]
    n = len(p)
    if n < 2:
        return []
    m = n if closed and n > 2 else n - 1
    segs = []
    for i in range(m):
        a, b = p[i], p[(i + 1) % n]
        s = Segment(a, b)
        if closed and n > 2 or i > 0:
            s.turn0 = _turn(p[(i - 1) % n], a, b)
            s.post0 = False
        if closed and n > 2 or i < m - 1:
            s.turn1 = _turn(a, b, p[(i + 2) % n])
        s.ext0, s.ext1 = _ext(s.turn0, off), _ext(s.turn1, off)
        segs.append(s)
    return segs


def outside_is_right(pts: list, inside_pt: Optional[tuple]) -> bool:
    """敷地の中の点（建物の重心など）が進む向きの左にあれば、外（道路の側）は右."""
    if inside_pt is None or len(pts) < 2:
        if len(pts) > 2:          # 閉じた形は反時計回りなら中が左
            a = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
            return a > 0
        return True
    best, side = None, 0.0
    for a, b in zip(pts, pts[1:]):
        L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 or 1.0
        t = max(0.0, min(1.0, ((inside_pt[0] - a[0]) * (b[0] - a[0]) + (inside_pt[1] - a[1]) * (b[1] - a[1])) / L2))
        d = math.dist(inside_pt, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if best is None or d < best:
            best = d
            side = (b[0] - a[0]) * (inside_pt[1] - a[1]) - (b[1] - a[1]) * (inside_pt[0] - a[0])
    return side > 0


@dataclass
class WindItem:
    item: str
    value: float
    allow: float
    unit: str
    note: str
    severity: str = "NG"           # 超えたときの判定（基礎の地盤は仮定なので WARN）

    @property
    def ratio(self) -> float:
        return self.value / self.allow if self.allow > 0 else 0.0


@dataclass
class HoardPlan:
    name: str
    seg: Segment
    height: float                  # パネルの高さ
    panel: Panel
    posts: list[float]             # 支柱の位置（始めから mm）
    post_z: list[float]            # 支柱の足元の地盤（区間の始めの地盤から mm）
    rails: list[float]             # 横地の高さ（地盤から）
    runs: list[tuple[float, float]]            # パネルを張る範囲（ゲートで切る）
    gates: list[tuple[float, float, str]]      # ゲート（始め・終わり・種類）
    brace_every: int
    foundation: str
    lift: float = LIFT_MM          # パネルの下端（地盤から。負は根入れ）
    soil_n: float = SOIL_N
    gate_info: list[GateLayout] = field(default_factory=list)
    wind: list[WindItem] = field(default_factory=list)
    wind_ms: float = DESIGN_WIND_MS
    pile: str = "H-300"            # 山留めから取るときの親杭
    pile_pitch: float = PILE_PITCH_MM
    pile_top: float = 0.0          # 親杭の天端（地盤から。継ぎ足しはここから）
    wall_dist: float = WALL_DIST_MM    # 山留め控え: 仮囲いの芯から親杭の芯まで
    pile_x0: float = 0.0           # 親杭の位置（区間の始めから。間隔の倍数で並ぶ）
    weights: tuple = (0, 0)        # H形鋼の基礎のウェイト（1スパンに 前の列・後ろの列）
    quantity: list[tuple[str, float, str]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)

    @property
    def top(self) -> float:
        return self.lift + self.height

    @property
    def root(self) -> float:
        return ROOT_Z.get(self.foundation, 150.0)

    @property
    def braces(self) -> list[int]:
        """控えを掛ける支柱の番号（ゲートの柱・ゲートの中は除く。山留めから取るときは控えなし）."""
        if self.foundation == "親杭支柱":
            return []
        out = []
        on_pile = 0
        for k, x in enumerate(self.posts):
            if any(g0 - 1.0 <= x <= g1 + 1.0 for g0, g1, _k in self.gates):
                continue
            if self.foundation == "山留め控え":                  # 親杭の真正面の支柱だけ（控えを親杭へまっすぐ）
                r = (x - self.pile_x0) % self.pile_pitch
                if min(r, self.pile_pitch - r) > 1.0:
                    continue
                if on_pile % self.brace_every == 0:
                    out.append(k)
                on_pile += 1
                continue
            if k % self.brace_every == 0 or k == len(self.posts) - 1:
                out.append(k)
        return out

    @property
    def brace_h(self) -> float:
        """控えを掛ける高さ: 上段の横地から 750 下（日建 3m で 2,100）."""
        h = max(self.rails) - BRACE_DROP_MM if self.rails else self.top * 0.7
        return round(max(self.root + 600.0, h) / 50.0) * 50.0

    @property
    def brace_back(self) -> float:
        if self.foundation == "H形鋼":
            return H_BEAM_GAP_MM                                 # 後ろの列の H形鋼に落とす
        if self.foundation == "山留め控え":                      # 親杭の根切りの側のフランジに留めた単管の立て
            return round(self.wall_dist + PILES[self.pile][0] / 2.0 + 24.3)
        return round((self.brace_h - self.root) * BRACE_SLOPE / 50.0) * 50.0

    @property
    def brace_len(self) -> float:
        return math.hypot(self.brace_back, self.brace_h - self.root)

    @property
    def post_step(self) -> float:
        """山留めから取るときの支柱の間隔: 親杭の間隔の倍数で 1,800 以内."""
        return self.pile_pitch * max(1, int(POST_PITCH_MM // self.pile_pitch + 1e-9))

    @property
    def corners(self) -> tuple[bool, bool]:
        """区間の始め・終わりに自在コーナーパネル（フラットパネル・防音パネルの角）."""
        if self.panel.kind not in (2, 3):
            return False, False
        return abs(self.seg.turn0) > 1.0, abs(self.seg.turn1) > 1.0


def _ceil_tube(mm: float) -> float:
    return math.ceil(mm / 500.0 - 1e-6) * 500.0


def rail_heights(panel: Panel, height: float, lift: Optional[float] = None) -> list[float]:
    """横地の高さ（地盤から）: 安全鋼板は取付穴の高さ（日建）、ほかはパネルの上端・下端から 150 と中."""
    lift = panel.lift if lift is None else lift
    rows = (panel.rows or {}).get(int(height))
    if rows is None:
        lo, hi = RAIL_EDGE_MM, height - RAIL_EDGE_MM
        rows = (lo, (lo + hi) / 2.0, hi) if height >= 2500.0 else (lo, hi)
    return [lift + r for r in rows]


def hoarding_plan(name: str, seg: Segment, height: float = 3000.0, panel: str = "安全鋼板", foundation: str = "打込み",
                  gates: Optional[list] = None, brace_every: int = 1, wind_ms: float = DESIGN_WIND_MS,
                  ground: Optional[Callable[[float, float], float]] = None, pitch: float = POST_PITCH_MM,
                  bottom: Optional[float] = None, soil_n: float = SOIL_N, pile: str = "H-300",
                  pile_pitch: float = PILE_PITCH_MM, pile_top: float = 0.0, wall_dist: float = WALL_DIST_MM,
                  pile_x0: float = 0.0) -> HoardPlan:
    """1区間の割付・数量・検定。gates は [(始め mm, 幅 mm, 種類)]（区間の始めから。種類は「キャスター両開き」なども）。
    ground(x, y) は地盤の高さ（mm）。bottom はパネルの下端（地盤から。省くと日建の標準＝地盤、負は根入れ）。
    foundation="親杭支柱" は親杭（pile・pile_pitch・天端 pile_top）を継ぎ足して支柱にする（控えなし）。"山留め控え" は控えの足だけ
    親杭に取る（仮囲いから親杭の芯まで wall_dist）。どちらも支柱を親杭の位置（区間の始めから pile_x0＋間隔の倍数）にそろえる."""
    foundation = FOUNDATION_ALIAS.get(foundation, foundation)
    pn = PANELS[panel]
    if pn.kind in (4, SHEET_KIND):
        height, pitch = 1800.0, 1800.0
    lift = pn.lift if bottom is None or pn.kind == 4 else float(bottom)
    if foundation == "H形鋼" and bottom is None:
        lift = max(lift, 300.0)                          # パネルの下端は H形鋼（H-300）の上
    L = seg.length
    infos: list[GateLayout] = []
    gl = []
    for g0, w, k in sorted(gates or [], key=lambda t: t[0]):
        if w <= 0 or g0 >= L:
            continue
        lay = gate_layout(w, k, lift + height)
        a = max(0.0, g0)
        gl.append((a, min(L, a + lay.width), k))
        infos.append(lay)
    # 支柱: 端と、ゲートの両脇の柱の間を pitch 以下で等分
    marks = [0.0] + [v for g0, g1, _k in gl for v in (g0, g1)] + [L]
    posts: list[float] = []
    step = pile_pitch * max(1, int(POST_PITCH_MM // pile_pitch + 1e-9))
    for a, b in zip(marks[::2], marks[1::2]):
        if b - a < 1.0:
            continue
        if foundation in PILE_GRID:                      # 親杭の位置（pile_x0＋間隔の倍数）。両端（角・ゲート）にも支柱
            k0 = math.ceil((a - pile_x0) / step - 1e-9)
            grid = [pile_x0 + step * k for k in range(k0, k0 + int((b - a) / step) + 2) if a - 1.0 <= pile_x0 + step * k <= b + 1.0]
            posts += [a] + [x for x in grid if x - a > 300.0 and b - x > 300.0] + [b]
            continue
        n = max(1, math.ceil((b - a) / pitch - 1e-9))
        posts += [a + (b - a) * k / n for k in range(n + 1)]
    posts = sorted({round(x, 1) for x in posts})
    if not seg.post0 and posts and posts[0] < 1.0 and not any(g0 < 1.0 for g0, _g1, _k in gl):
        posts = posts[1:]
    ux, uy = (seg.p1[0] - seg.p0[0]) / (L or 1.0), (seg.p1[1] - seg.p0[1]) / (L or 1.0)
    z0 = ground(*seg.p0) if ground else 0.0
    post_z = [round(ground(seg.p0[0] + ux * x, seg.p0[1] + uy * x) - z0, 1) if ground else 0.0 for x in posts]
    runs, x = [], -seg.ext0
    for g0, g1, _k in gl:
        if g0 - x > 1.0:
            runs.append((x, g0))
        x = g1
    if L + seg.ext1 - x > 1.0:
        runs.append((x, L + seg.ext1))
    p = HoardPlan(name, seg, height, pn, posts, post_z, rail_heights(pn, height, lift), runs, gl, max(1, brace_every),
                  foundation, lift, soil_n, infos, wind_ms=wind_ms, pile=pile, pile_pitch=pile_pitch, pile_top=pile_top,
                  wall_dist=wall_dist, pile_x0=pile_x0)
    p.wind = wind_calc(p, wind_ms, pitch)
    _quantity(p)
    _checks(p, pitch)
    return p


def _max_gap(p: HoardPlan, pitch: float) -> float:
    gaps = [b - a for a, b in zip(p.posts, p.posts[1:])
            if not any(g0 - 1.0 <= a and b <= g1 + 1.0 for g0, g1, _k in p.gates)]
    return max(gaps, default=pitch)


def wind_calc(p: HoardPlan, v: float, pitch: float = POST_PITCH_MM) -> list[WindItem]:
    """風の検討（日建 仮囲安全鋼板の検討 p453〜456 と同じ手順）。メッシュは風を通すので行わない."""
    if p.panel.kind == 4 or not p.rails:
        return []
    q = 5.0 * v * v / 8.0                                # 速度圧 N/m²
    P = 1.3 * q                                          # 風圧力（風力係数 1.3）
    zs = sorted(p.rails)
    lo, hi = max(0.0, p.lift), p.top
    trib = []                                            # 横地ごとに受け持つパネルの高さ（地上の分）
    for j, z in enumerate(zs):
        a = lo if j == 0 else (zs[j - 1] + z) / 2.0
        b = hi if j == len(zs) - 1 else (z + zs[j + 1]) / 2.0
        trib.append(max(0.0, b - max(a, 0.0)) / 1000.0)
    L = _max_gap(p, pitch) / 1000.0
    k = p.brace_every
    out: list[WindItem] = []
    s = max((b - a for a, b in zip(zs, zs[1:])), default=p.height) / 1000.0
    if p.panel.z_cm3:
        M = P * p.panel.eff / 1000.0 * s * s / 8.0 * 100.0
        out.append(WindItem("パネル", M / p.panel.z_cm3, FB_PANEL, "N/cm²",
                            f"横地の間 {s * 1000:.0f} の単純梁・1枚 Z={p.panel.z_cm3}cm³"))
    w = P * max(trib)
    out.append(WindItem("横地", w * L * L / 8.0 * 100.0 / TUBE_Z, FB_TUBE, "N/cm²", f"支柱の間 {L * 1000:.0f} の単純梁"))
    if p.foundation == "親杭支柱":                         # 親杭の継ぎ足し（H形鋼）の片持ち。控えなし
        bw, zx, _kg = PILES[p.pile]
        f1 = [P * t * L for t in trib]
        m = sum(f * (z - p.pile_top) / 1000.0 for f, z in zip(f1, zs) if z > p.pile_top) * 100.0
        out.append(WindItem("親杭の継ぎ足し", m / zx, FB_TUBE, "N/cm²",
                            f"{p.pile}（Zx={zx:g}cm³）の片持ち・親杭の天端（地上 {p.pile_top:.0f}）で {m / 100:.0f}N·m"))
        return out
    F = [P * t * L * k for t in trib]                    # 控えのある支柱1本に横地から掛かる力 N
    zb, zr = p.brace_h, p.root
    Ls = (zb - zr) / 1000.0
    mc = sum(f * (z - zb) / 1000.0 for f, z in zip(F, zs) if z > zb) * 100.0
    ms = sum(f * (z - zr) / 1000.0 * (zb - z) / 1000.0 / Ls for f, z in zip(F, zs) if zr < z < zb) * 100.0
    out.append(WindItem("支柱", max(mc, ms) / TUBE_Z, FB_TUBE, "N/cm²",
                        f"控えから上の片持ち {mc / 100:.0f}N·m・控えと根がらみの間 {ms / 100:.0f}N·m"
                        + (f"（控えは {k}本の支柱ごと）" if k > 1 else "")))
    ra = sum(f * (z - zr) for f, z in zip(F, zs) if z > zr) / (zb - zr)
    back = p.brace_back / 1000.0
    lk = math.hypot(back, Ls)
    nb = ra * lk / back
    lam = lk * 100.0 / TUBE_I
    lam0 = math.sqrt(math.pi ** 2 * E_STEEL / (0.6 * F_TUBE))
    r = lam / lam0
    sc = 0.29 * F_TUBE / r ** 2 if r > 1.0 else (1 - 0.4 * r * r) * F_TUBE / (1.5 + 2.0 / 3.0 * r * r) * (0.29 / 0.277)
    out.append(WindItem("控えの座屈", nb / TUBE_A, sc, "N/cm²", f"控えの軸力 {nb:.0f}N・座屈長さ {lk * 1000:.0f}・λ={lam:.0f}"))
    out.append(WindItem("控えのクランプ", nb, CLAMP_SWIVEL_N * 1.3, "N",
                        "自在クランプ ARC2 のすべり耐力 3.43kN の3割増し", "WARN"))
    n0 = ra * Ls / back                                  # 控えの足の押し・引抜き
    if p.foundation == "打込み":
        n = p.soil_n
        qd = (40.0 * n * math.pi * PILE_D_M ** 2 / 4.0 + math.pi * PILE_D_M * PILE_H_M * n / 5.0) / 1.5 * G * 1000.0
        qt = math.pi * PILE_D_M * PILE_H_M * n / 5.0 / 1.5 * G * 1000.0
        out.append(WindItem("杭の押し", n0, qd, "N", f"打込みパイプ φ48.6・地中 {PILE_H_M * 1000:.0f}・N値 {n:g}（Meyerhof）",
                            "WARN"))
        out.append(WindItem("杭の引抜き", n0, qt, "N", f"周面の摩擦だけ・N値 {n:g}", "WARN"))
    elif p.foundation == "山留め控え":
        out.append(WindItem("控えの足のキャッチクランプ", n0, 2.0 * CLAMP_SWIVEL_N * 1.3, "N",
                            "単管の立てを親杭の根切りの側のフランジに 2個1組（耐力は自在クランプのすべり耐力 3.43kN の3割増しで仮に。"
                            "使うキャッチクランプの値で確かめる）", "WARN"))
    elif p.foundation == "根巻き":
        a1 = CONC_B_M * CONC_B_M
        out.append(WindItem("根巻きの地耐力", n0 / 1000.0 / a1, SOIL_BEARING, "kN/m²", "□300×400", "WARN"))
        qt = SOIL_BEARING / 10.0 * 4.0 * CONC_B_M * CONC_D_M / 1.5 * 1000.0
        out.append(WindItem("根巻きの引抜き", n0, qt, "N", "側面の摩擦（地耐力の 1/10）", "WARN"))
    elif p.foundation == "H形鋼":
        mo = sum(P * t * L * z / 1000.0 for t, z in zip(trib, zs))       # 1スパンの転倒モーメント N·m
        nf, nr, mr = h_beam_weights(p, mo, L)
        p.weights = (nf, nr)
        out.append(WindItem("H形鋼の転倒", mo * 1.5, mr, "N·m",
                            f"1スパン {L * 1000:.0f}・H-300 {H_BEAM_KG_M:g}kg/m の2列（幅 {H_BEAM_GAP_MM:.0f}）を外からの風は後ろの列、"
                            f"中からの風は前の列のまわりに起こす（安全率 1.5）"
                            + (f"・ウェイト □600（{WEIGHT_KG:.0f}kg）を1スパンに 前 {nf}・後ろ {nr}" if nf or nr else ""),
                            "WARN"))
    return out


def h_beam_weights(p: HoardPlan, mo: float, span_m: float) -> tuple[int, int, float]:
    """H形鋼の基礎の転倒に要るウェイト（1スパンの個数 前の列・後ろの列）と、足したあとの抵抗モーメント（2方向の小さい方）.
    外からの風（敷地へ押す）は後ろの列のまわり: 前の列の H形鋼・パネル・前のウェイト（後ろの列から 1,700−460）が抵抗。
    中からの風は前の列のまわり: 後ろの列の H形鋼（1,700）・後ろのウェイト（1,700−460）・前のウェイト（460）が抵抗."""
    gap = H_BEAM_GAP_MM / 1000.0
    arm = (H_BEAM_GAP_MM - WEIGHT_Y_MM) / 1000.0
    w1 = WEIGHT_KG * G
    beam = H_BEAM_KG_M * span_m * G
    wp = p.panel.kg.get(int(p.height), 15.0) * span_m * 1000.0 / p.panel.eff * G
    need = 1.5 * mo
    nf = max(0, math.ceil((need - (beam + wp) * gap) / (w1 * arm) - 1e-9))
    nr = max(0, math.ceil((need - beam * gap - nf * w1 * WEIGHT_Y_MM / 1000.0) / (w1 * arm) - 1e-9))
    m_out = (beam + wp) * gap + nf * w1 * arm
    m_in = beam * gap + nr * w1 * arm + nf * w1 * WEIGHT_Y_MM / 1000.0
    return nf, nr, min(m_out, m_in)


def wind_limit(p: HoardPlan) -> float:
    """この組で持つ風速（m/s）。応力・力は風速の2乗に比べる."""
    worst = max((w.ratio for w in p.wind), default=0.0)
    return p.wind_ms / math.sqrt(worst) if worst > 0 else 0.0


def _panel_count(p: HoardPlan) -> tuple[int, int, int]:
    """(パネル, 調整パネル, 重ねで吸収した半端)。フラットパネルは角の自在コーナーパネル 240 を除く."""
    pn = p.panel
    c0, c1 = p.corners
    n_panel = adj = absorb = 0
    for i, (a, b) in enumerate(p.runs):
        length = b - a
        if c0 and i == 0 and a <= -p.seg.ext0 + 1.0:
            length -= CORNER_LEAF_MM
        if c1 and i == len(p.runs) - 1 and b >= p.seg.length + p.seg.ext1 - 1.0:
            length -= CORNER_LEAF_MM
        full, rest = divmod(max(0.0, length), pn.eff)
        n_panel += int(full)
        if rest <= 10.0:
            continue
        if pn.kind in (2, 3):
            if rest < 40.0:
                absorb += 1
            elif rest <= 440.0:
                adj += 1
            else:
                n_panel += 1
        else:
            n_panel += 1
    return n_panel, adj, absorb


def _quantity(p: HoardPlan) -> None:
    q, pn, H = p.quantity, p.panel, p.height
    nb = len(p.posts)
    nr = len(p.rails)
    run_len = sum(b - a for a, b in p.runs)
    n_panel, adj, absorb = _panel_count(p)
    kg = pn.kg.get(int(H), max(pn.kg.values()) * H / max(pn.kg))
    q.append((pn.label(H), n_panel, f"有効幅 {pn.eff:.0f}・延べ {run_len / 1000:.1f}m・1枚 {kg:.1f}kg"))
    if adj:
        q.append((f"調整Nパネル VICN{int(H / 10)}（有効幅 40〜440）", adj, "半端の幅・VIC留め金具 2"))
        q.append(("VIC留め金具", adj * 2, "調整Nパネル1枚に 2"))
    if absorb:
        q.append(("（半端 40 未満は重ねで吸収）", absorb, ""))
    if pn.kind == SHEET_KIND:
        q.append((pn.fixer, n_panel * SHEET_EYELETS, f"ハトメごと（1枚 {SHEET_EYELETS}・45cm ピッチ）"))
    else:
        q.append((pn.fixer, (n_panel + adj) * 2 * nr, f"1枚に {2 * nr}（横地 {nr}段に 2 ずつ）"))
    if pn.kind == 2:
        q.append(("VIC開き止め金具", math.ceil(n_panel * 0.075), "40スパンに 3"))
    c0, c1 = p.corners
    if c1:                                               # 角の役物は終わりの角で数える（始めの角は前の辺）
        q.append((f"自在コーナーパネル VICC{int(H / 10)}（240＋240）", 1,
                  f"内角 {180.0 - abs(p.seg.turn1):.0f}°・{'出隅' if p.seg.turn1 > 0 else '入隅'}・C型金具 {2 * nr}"))
        q.append(("C型金具（自在コーナーパネル）", 2 * nr, ""))
    elif p.seg.turn1 and abs(p.seg.turn1) > 1.0:
        q.append(("角のパネル（重ね）", 1, f"内角 {180.0 - abs(p.seg.turn1):.0f}°・{'出隅' if p.seg.turn1 > 0 else '入隅'}"))
    if p.foundation == "親杭支柱":
        bw, _zx, kgm = PILES[p.pile]
        ext = p.top + POST_TOP_MM - p.pile_top
        q.append((f"H形鋼 {p.pile}（親杭の継ぎ足し L={ext:.0f}）", nb,
                  f"親杭 @{p.pile_pitch:.0f} の {int(round(p.post_step / p.pile_pitch))}本ごと・{kgm * ext / 1000:.0f}kg・"
                  "天端はパネルの上端"))
        q.append(("継手の添え板・高力ボルト（フランジ2・ウェブ2）", nb, "親杭の天端で継ぐ（溶接でも）"))
        q.append(("キャッチクランプ（H形鋼用・横地）", nb * nr, "横地を親杭の外のフランジに"))
    else:
        under = {"打込み": EMBED_MM, "根巻き": CONC_D_M * 1000.0 - 50.0, "H形鋼": -300.0, "アンカー": -9.0,
                 "山留め控え": EMBED_MM}[p.foundation]
        tube_post = _ceil_tube(p.top + POST_TOP_MM + under)
        q.append((f"単管 {tube_post / 1000:.1f}m（支柱）", nb, f"@{POST_PITCH_MM:.0f} 以内・天端はパネルの上端" +
                  ("・根入れ 1,000 以上" if p.foundation in ("打込み", "山留め控え") else "")))
    n5 = sum(math.ceil((b - a) / 5000.0) for a, b in p.runs)
    q.append(("単管 5.0m（横地）", n5 * nr, f"{nr}段（下から {'・'.join(f'{z:.0f}' for z in p.rails)}）"))
    q.append(("直線ジョイント PCJ", max(0, n5 - len(p.runs)) * nr, "横地の継ぎ"))
    nbr = len(p.braces)
    ground_tie = p.foundation in ("打込み", "根巻き", "山留め控え")
    if p.foundation != "親杭支柱":
        q.append(("直交クランプ ARC1", nb * nr + (2 * nbr if ground_tie else 0),
                  "支柱と横地" + ("・根がらみの両端" if ground_tie else "")))
    skew = sum(1 for t in (p.seg.turn0, p.seg.turn1) if 1.0 < abs(t) and abs(abs(t) - 90.0) > 1.0)
    if nbr or skew:
        q.append(("自在クランプ ARC2", nbr * 2 + skew * nr, "控えの上と足" + ("・直交しない角の横地" if skew else "")))
    if nbr:
        bl = _ceil_tube(p.brace_len)
        q.append((f"単管 {bl / 1000:.1f}m（控え）", nbr,
                  f"支柱の高さ {p.brace_h:.0f} から後ろ {p.brace_back:.0f}・高さ {p.root:.0f} へ"
                  f"（{math.degrees(math.atan2(p.brace_h - p.root, p.brace_back)):.0f}°）"))
    if ground_tie and nbr:
        q.append((f"単管 {_ceil_tube(p.brace_back + 100.0) / 1000:.1f}m（根がらみ）", nbr, f"地上 {p.root:.0f}"))
    if p.foundation == "打込み":
        q.append(("打込みパイプ くい丸1.5M（控えの足）", nbr, f"地中 {PILE_H_M * 1000:.0f}"))
    elif p.foundation == "山留め控え":
        q.append(("単管 1.0m（控えの足。親杭の根切りの側のフランジに立てる）", nbr, f"親杭 {p.pile} の天端から 400 下〜600 上"))
        q.append(("キャッチクランプ（H形鋼用・控えの足を親杭に）", 2 * nbr, "2個1組"))
    elif p.foundation == "根巻き":
        q.append(("根巻きコンクリート □300×400", nb + nbr, "支柱と控えの足"))
        q.append(("単管 1.0m（控えの足。根巻き）", nbr, ""))
    elif p.foundation == "アンカー":
        q.append(("固定ベース PKB（□120・4-φ11）", nb, "支柱をコンクリートの上に"))
        q.append(("ベースアンカー NBAK（□140 t9・φ48.6×3.2 H309）", nbr, "控えの足"))
        q.append(("あと施工アンカー", (nb + nbr) * 4, "固定ベース・ベースアンカー 1台に 4"))
    elif p.foundation == "H形鋼":
        hl = _ceil_tube(p.seg.length + 300.0)
        q.append((f"H形鋼 H-300×300×10×15（{hl / 1000:.1f}m）", 2, f"2列（幅 {H_BEAM_GAP_MM:.0f}）を敷く"))
        q.append(("キャッチクランプ（H形鋼用）", (nb + nbr) * 2, "支柱・控えを H形鋼のフランジに 2個1組"))
        q.append(("単管 0.5m（控えの足。H形鋼の上）", nbr, ""))
        nf, nr_w = p.weights
        if nf or nr_w:
            spans = max(1, len(p.posts) - 1)
            q.append((f"コンクリートウェイト □600（約 {WEIGHT_KG:.0f}kg）", (nf + nr_w) * spans,
                      f"1スパンに 前の列の内 {nf}・後ろの列の手前 {nr_w}（転倒の安全率 1.5）"))
            q.append(("ウェイトを H形鋼に縛るチェーン・シャックル", (nf + nr_w) * spans, ""))
    if p.foundation != "親杭支柱":
        q.append(("単管キャップ（キャッピカ）", nb + (nbr if p.foundation != "アンカー" else 0), "支柱・杭の天端"))
    for (g0, g1, _k), lay in zip(p.gates, p.gate_info):
        g = lay.gate
        if g.is_door:
            q.append((f"{g.name} {g.code}", 1, f"間口 {lay.width:.0f}・扉 {g.leaf_w:.0f}"))
        else:
            q.append((f"{g.name} {lay.width / 1000:.1f}M {'両' if lay.double else '片'}開き（{lay.set_code}）", 1,
                      f"{lay.units}ユニット・{lay.kg:.1f}kg・畳むと {' と '.join(f'{k * FOLD_UNIT_MM + 2 * FOLD_POST_MM:.0f}' for k in lay.leaves if k)}"
                      f"・通れる幅 {lay.clear:.0f}"))
        for a, n, _w in lay.parts:
            if g.is_door and a.startswith(g.name):
                continue
            q.append((f"  {a}", n, g.name))


def _checks(p: HoardPlan, pitch: float) -> None:
    c = p.checks
    top = p.top
    c.append(Check("仮囲いの高さ", "OK" if top >= 1800.0 else "NG",
                   f"地盤から {top:.0f}（1.8m 以上。施行令 136条の2の20・公衆災害防止対策要綱 建築 第21。特に必要なら 3m）"))
    if p.lift > 1.0:
        c.append(Check("パネルの下端", "OK", f"地盤から {p.lift:.0f} 浮かす（すき間は幅木・土のうでふさぐ）"))
    elif p.lift < -1.0:
        c.append(Check("パネルの下端", "OK", f"地盤に {-p.lift:.0f} 入れる（根入れ）"))
    pm = _max_gap(p, pitch)
    c.append(Check("支柱の間隔", "OK" if pm <= pitch + 1.0 else "NG", f"最大 {pm:.0f}（{pitch:.0f} 以内）"))
    if p.panel.kind == 4:
        c.append(Check("風", "OK", "メッシュは風を通す（風力係数 0.9。板は 1.3）"))
    if p.panel.kind == SHEET_KIND:
        c.append(Check("シート", "注意", "単管シートの組み方の基準は見つからず、支柱・横地の段は【目安】。風は板と同じ風力係数 1.3 で見ている。"
                                         "シートの破れ・結束の緩みを点検し、強風の前は対策を"))
    for w in p.wind:
        ok = w.value <= w.allow
        hint = ""
        if not ok:
            hint = {"控えのクランプ": "。スーパー自在クランプ S2C（8.82kN）か2個掛けに",
                    "杭の引抜き": "。杭を長く・控えを増やすか根巻きに",
                    "杭の押し": "。杭を長く",
                    "H形鋼の転倒": "。ウェイト・アンカーを足すか控えを足元で地盤に留める"}.get(w.item, "。控えを支柱ごとに・間隔を詰める")
        c.append(Check(f"風: {w.item}", "OK" if ok else w.severity,
                       f"{w.value:.0f} ≦ {w.allow:.0f} {w.unit}（{w.note}）" if ok else
                       f"{w.value:.0f} > {w.allow:.0f} {w.unit}（{w.note}）{hint}"))
    if p.wind:
        vl = wind_limit(p)
        c.append(Check("風: この組で持つ風速", "OK" if vl >= p.wind_ms - 0.05 else "WARN",
                       f"約 {vl:.0f}m/s（設計風速 {p.wind_ms:.0f}m/s。q＝5V²/8・風力係数 1.3。日建 仮囲安全鋼板の検討の手順）"
                       + ("" if vl >= p.wind_ms - 0.05 else "。強風の前にパネルを外すか控えを足す")))
    if p.foundation == "親杭支柱":
        bw, zx, _kg = PILES[p.pile]
        P = 1.3 * 5.0 * p.wind_ms ** 2 / 8.0
        mg = P * max(0.0, p.top - max(0.0, p.lift)) / 1000.0 * p.post_step / 1000.0 * (p.top + max(0.0, p.lift)) / 2000.0
        c.append(Check("親杭の位置", "OK", f"支柱は親杭 {p.pile} @{p.pile_pitch:.0f} の {int(round(p.post_step / p.pile_pitch))}本"
                                         f"ごと（@{p.post_step:.0f}）を継ぎ足す。根切りの側に控えは下ろさない"))
        c.append(Check("親杭への風の曲げ", "WARN", f"継ぎ足した親杭1本に地盤で約 {mg / 1000:.1f}kN·m（風 {p.wind_ms:.0f}m/s）が"
                                               "加わる。山留めの設計者に確かめる（根切りの深さ・腹起し・切梁の段と合わせて）"))
    if p.foundation == "山留め控え":
        ang = math.degrees(math.atan2(p.brace_h - p.root, p.brace_back))
        c.append(Check("控えの足（山留め）", "WARN" if ang > 70.0 or p.wall_dist < 500.0 else "OK",
                       f"仮囲いから親杭の芯まで {p.wall_dist:.0f}・控えの後ろ {p.brace_back:.0f}（{ang:.0f}°）。支柱は親杭 {p.pile} "
                       f"@{p.pile_pitch:.0f} の真正面にそろえ、控えは親杭の数だけ"
                       + ("。控えが立ちすぎる（70° を超える）。山留めが近いときは控えを1スパンずらすか親杭支柱に" if ang > 70.0
                          or p.wall_dist < 500.0 else "")))
        ax = next((w for w in p.wind if w.item == "控えのクランプ"), None)
        if ax:
            v = ax.value * (p.brace_h - p.root) / p.brace_len
            hz = ax.value * p.brace_back / p.brace_len
            c.append(Check("親杭への控えの力", "WARN", f"控え1本で親杭の頭に 鉛直 {v / 1000:.1f}kN・水平 {hz / 1000:.1f}kN"
                           f"（風 {p.wind_ms:.0f}m/s）。山留めの設計者に確かめる（根切りの深さ・腹起し・切梁の段と合わせて）"))
    if p.foundation == "アンカー" and p.wind:
        ra_like = next((w for w in p.wind if w.item == "控えのクランプ"), None)
        if ra_like:
            c.append(Check("アンカーの引抜き", "OK", f"控えの足 1台に {ra_like.value * (p.brace_h - p.root) / p.brace_len / 1000:.2f}kN "
                           "の引抜き（使うあと施工アンカーの許容引抜き力で確かめる）"))
    for t, where in ((p.seg.turn0, "始め"), (p.seg.turn1, "終わり")):
        if abs(t) <= 1.0:
            continue
        inner = 180.0 - abs(t)
        lim = CORNER_MIN_OUT if t > 0 else CORNER_MIN_IN
        c.append(Check(f"{where}の角", "OK" if inner >= lim else "WARN",
                       f"内角 {inner:.0f}°（{'出隅' if t > 0 else '入隅'}。自在コーナーは {lim:.0f}〜180°）"
                       + ("" if inner >= lim else "。鋭すぎる。角を2つの折れに分ける")))
    if p.post_z and max(p.post_z) - min(p.post_z) > 1.0:
        dz = max(p.post_z) - min(p.post_z)
        slope = dz / max(1.0, p.seg.length)
        c.append(Check("地盤の高低差", "OK" if slope <= 0.10 else "WARN",
                       f"区間の中で {dz:.0f}（勾配 {slope * 100:.1f}%）。パネルは1枚ずつ地盤に合わせて上下にずらし、横地は地盤に沿って"
                       "流す（自在クランプ）" + ("" if slope <= 0.10 else "。10% を超えるので段切りか、パネルの下のすき間をふさぐ")))
    for (g0, g1, k), lay in zip(p.gates, p.gate_info):
        g = lay.gate
        if g.is_door:
            c.append(Check("出入口", "OK", f"{g.name} {g.code}（W{g.door_w:.0f}・扉 {g.leaf_w:.0f}）。内開き・普段は閉める"
                                           "（公衆災害防止対策要綱 建築 第21）"))
            continue
        over = lay.units > (18 if lay.double else 9)
        c.append(Check("出入口", "NG" if over else "OK",
                       f"{g.name} {lay.width / 1000:.1f}M {'両' if lay.double else '片'}開き・{lay.units}ユニット（900）"
                       + ("。両開き 16.2m を超える。ゲートを2つに分ける" if over else "")
                       + "。普段は閉め、車両の出入りが多ければ誘導員（公衆災害防止対策要綱 建築 第21）"))
        vehicle = lay.width >= 3600.0
        c.append(Check("ゲートの通れる幅", "WARN" if vehicle and lay.clear < 3000.0 else "OK",
                       f"開けると {lay.clear:.0f}（間口 {lay.width:.0f} から畳んだゲート {lay.width - lay.clear:.0f} を引く。"
                       f"ユニット1つ 260＋支柱 90×2）" + ("。車両には狭い。両開きか間口を広げる" if vehicle and lay.clear < 3000.0
                                                       else "")))
        if g.panel_kg:
            c.append(Check("パネルキャスターゲートと風", "OK", "強風のときはアルミパネルを外すか、ゲートを畳む（日建 p406）"))


def part_params(p: HoardPlan) -> dict:
    """部品 ashiba_kakoi のパラメータ（m）."""
    c0, c1 = p.corners
    return {"kkType": p.panel.kind, "kkL": p.seg.length / 1000.0, "pnH": p.height / 1000.0, "pnW": p.panel.eff / 1000.0,
            "lift": p.lift / 1000.0, "postX": ",".join(f"{x:.0f}" for x in p.posts),
            "postZ": ",".join(f"{z:.0f}" for z in p.post_z), "railZ": ",".join(f"{z:.0f}" for z in p.rails),
            "runX": ",".join(f"{a:.0f},{b:.0f}" for a, b in p.runs),
            "gateX": ",".join(f"{a:.0f},{b:.0f}" for a, b, _k in p.gates),
            "gateK": ",".join(str(lay.gate.kind) for lay in p.gate_info),
            "gateN": ",".join(f"{lay.leaves[0]},{lay.leaves[1]}" for lay in p.gate_info),
            "brX": ",".join(f"{p.posts[k]:.0f}" for k in p.braces), "brH": p.brace_h / 1000.0,
            "brB": p.brace_back / 1000.0, "brRt": p.root / 1000.0, "kkCor": f"{int(c0)},{int(c1)}",
            "hbX": _h_beam_rear(p), "wtN": f"{p.weights[0]},{p.weights[1]}",
            "pileW": PILES.get(p.pile, PILES["H-300"])[0] / 1000.0, "pileZ": p.pile_top / 1000.0, "kkFound": FOUNDATIONS[p.foundation], "embed": EMBED_MM / 1000.0,
            "kkName": f"仮囲い {p.name}"}


def panel_off(panel: str, foundation: str = "打込み", pile: str = "H-300") -> float:
    """パネルの裏の支柱の芯からの距離（角の延ばし）。山留めから取るときは横地が親杭の外のフランジに付く."""
    off = PANELS[panel].off
    if foundation == "親杭支柱":
        off += PILES[pile][0] / 2.0 + 24.3 - RAIL_OFF_MM
    return off


def _h_beam_rear(p: HoardPlan) -> str:
    """H形鋼の後ろの列（控えの側 brB）の始め・終わり。角では二等分線で止める（左へ曲がる角は縮め、右は延ばす）."""
    if p.foundation != "H形鋼":
        return ""
    d = p.brace_back
    a = d * math.tan(math.radians(p.seg.turn0) / 2.0)
    b = p.seg.length - d * math.tan(math.radians(p.seg.turn1) / 2.0)
    return f"{a:.0f},{b:.0f}"


def report(plans: list[HoardPlan]) -> str:
    out = ["# 仮囲い", "", f"出典: {SOURCES}", ""]
    total: dict[str, float] = {}
    for p in plans:
        out += [f"## {p.name}（長さ {p.seg.length:.0f}mm・向き {p.seg.angle:.1f}°・パネルの上端 {p.top:.0f}）", "",
                "| 品名 | 数 | 注 |", "|---|---|---|"]
        out += [f"| {a} | {b:g} | {c} |" for a, b, c in p.quantity]
        if p.wind:
            out += ["", f"風の検討（設計風速 {p.wind_ms:.0f}m/s・q＝5V²/8＝{5 * p.wind_ms ** 2 / 8:.1f}N/m²・風力係数 1.3）", "",
                    "| 部位 | 値 | 許容 | 比 | 内容 |", "|---|---|---|---|---|"]
            out += [f"| {w.item} | {w.value:.0f} {w.unit} | {w.allow:.0f} | {w.ratio:.2f} | {w.note} |" for w in p.wind]
        out += ["", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        out += [f"| {c.item} | {c.status} | {c.message} |" for c in p.checks]
        out.append("")
        for a, b, _c in p.quantity:
            total[a] = total.get(a, 0) + b
    if len(plans) > 1:
        out += ["## 合計", "", "| 品名 | 数 |", "|---|---|"] + [f"| {a} | {b:g} |" for a, b in total.items()]
    return "\n".join(out)


def inset_polygon(pts: list, d: float) -> list:
    """閉じた多角形を中へ d だけ寄せる（辺を平行に寄せて隣の辺と交わる点。斜めの辺も同じ）。敷地境界から仮囲いの芯へ."""
    p = [tuple(map(float, q)) for q in pts]
    if len(p) > 2 and math.dist(p[0], p[-1]) < 1.0:
        p = p[:-1]
    n = len(p)
    if n < 3:
        return p
    area = sum(p[i][0] * p[(i + 1) % n][1] - p[(i + 1) % n][0] * p[i][1] for i in range(n))
    s = 1.0 if area > 0 else -1.0                 # 反時計回りなら中は左
    lines = []
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        L = math.dist(a, b) or 1.0
        nx, ny = -(b[1] - a[1]) / L * s, (b[0] - a[0]) / L * s     # 中への法線
        lines.append(((a[0] + nx * d, a[1] + ny * d), (b[0] + nx * d, b[1] + ny * d)))
    out = []
    for i in range(n):
        (a1, b1), (a2, b2) = lines[i - 1], lines[i]
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        d2 = (b2[0] - a2[0], b2[1] - a2[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(a2)
            continue
        t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
        out.append((a1[0] + d1[0] * t, a1[1] + d1[1] * t))
    return out


def offset_polyline(pts: list, d: float, closed: bool = False) -> list:
    """点列を進む向きの右へ d 寄せる（辺を平行に寄せて隣の辺と交わる点。開いた線の両端は寄せるだけ）。山留め（壁）から仮囲いの線へ."""
    p = [tuple(map(float, q)) for q in pts]
    if closed and len(p) > 2 and math.dist(p[0], p[-1]) < 1.0:
        p = p[:-1]
    n = len(p)
    m = n if closed else n - 1
    lines = []
    for i in range(m):
        a, b = p[i], p[(i + 1) % n]
        L = math.dist(a, b) or 1.0
        nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L          # 右
        lines.append(((a[0] + nx * d, a[1] + ny * d), (b[0] + nx * d, b[1] + ny * d)))
    out = []
    for i in range(n):
        if not closed and i == 0:
            out.append(lines[0][0])
            continue
        if not closed and i == n - 1:
            out.append(lines[-1][1])
            continue
        (a1, b1), (a2, b2) = lines[i - 1], lines[i % m]
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        d2 = (b2[0] - a2[0], b2[1] - a2[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(a2)
            continue
        s = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
        out.append((a1[0] + d1[0] * s, a1[1] + d1[1] * s))
    return out


def pile_ref(seg: Segment, wall_lines: list, pitch: float = PILE_PITCH_MM) -> tuple[float, float]:
    """山留め控え: 区間に向き合う山留め（壁の芯の線）までの距離（区間の真ん中から）と、親杭の位置の始め（区間の始めから、
    壁の始めを区間の向きに映して間隔で割った余り）。壁が無ければ (WALL_DIST_MM, 0)."""
    if not wall_lines:
        return WALL_DIST_MM, 0.0
    L = seg.length or 1.0
    u = ((seg.p1[0] - seg.p0[0]) / L, (seg.p1[1] - seg.p0[1]) / L)
    mid = ((seg.p0[0] + seg.p1[0]) / 2.0, (seg.p0[1] + seg.p1[1]) / 2.0)
    best = None
    for a, b in wall_lines:
        wl = math.dist(a, b) or 1.0
        w = ((b[0] - a[0]) / wl, (b[1] - a[1]) / wl)
        if abs(u[0] * w[0] + u[1] * w[1]) < 0.95:             # 平行でない壁は向き合わない
            continue
        tt = max(0.0, min(wl, (mid[0] - a[0]) * w[0] + (mid[1] - a[1]) * w[1]))
        dd = math.dist(mid, (a[0] + w[0] * tt, a[1] + w[1] * tt))
        if best is None or dd < best[0]:
            best = (dd, a)
    if best is None:
        return WALL_DIST_MM, 0.0
    dd, a = best
    s0 = (a[0] - seg.p0[0]) * u[0] + (a[1] - seg.p0[1]) * u[1]
    return round(dd, 1), round(s0 % pitch, 1)


def split_gates(segs: list[Segment], gates: list) -> list[list]:
    """ポリラインの始めからの位置で指定したゲート [(位置, 幅, 種類)] を区間ごとの [(区間の始めから, 幅, 種類)] に分ける."""
    out: list[list] = [[] for _ in segs]
    acc = 0.0
    for i, s in enumerate(segs):
        L = s.length
        for g0, w, k in gates:
            if acc - 1.0 <= g0 < acc + L - 1.0:
                out[i].append((g0 - acc, min(w, acc + L - g0), k))
        acc += L
    return out
