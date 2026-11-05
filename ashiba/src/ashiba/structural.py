"""構造計算（仮設工業会「足場・型枠支保工設計指針」「風荷重に対する足場の安全技術指針」準拠）.

⚠️ 設計方針（開発指示書§6・§9）:
本モジュールは「計算エンジンの自作」ではなく **実績フォーマットへ転記するための値を算出する下書き**。
最終判断は計画作成参画者（有資格者）が行う前提。

耐力値（ジャッキ許容支持力・壁つなぎ許容耐力・作業床許容積載）は data/capacity.csv に
外出しし、各行に verified 列と source 列を持つ。verified=no の値が計算に使われた場合は
必ず警告を出し、帳票にも「未確認値」と明記する。安全に関わる数値を黙って使わないための仕組み。
警告には**差し替える行（series_id,item,key）**まで書く。「未確認値です」だけでは、
どこを直せば消えるのか分からない（補間値なら補間元の2行とも挙げる）。

検定の元になった数（建地本数・総重量・作業床許容積載・同時載荷層数）は PostResult に
持たせて計算書に出す。式だけ書いて元の数が無いと、確認する人が値を追えない。

計算式（指示書§6の指定どおり）:
  設計風速   V  = V0 × K(高さ) × E(近接建物 1.0〜1.3) × S(地域区分)
  速度圧     q  = 0.6 × V^2                    [N/m2]
  風力係数   C  = (0.11 + 0.09γ + 0.945×Co×R) × F   （Co=1.57、メッシュ R=0.7）
  壁つなぎ   P  = C × q × lh × lw ≦ 許容耐力 × 1.3  （風荷重時30%割増）
  建地圧縮   N  = 自重 + 積載 ≦ 許容支持力（ジャッキ繰出し長で変動）
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .terrain import actual_max_height_mm
from .model import ScaffoldModel
from .quantity import QuantityResult

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 仮設工業会「風荷重に対する足場の安全技術指針」（建災防東京支部「計画届作成の手引（第6版）」p227〜239 に転載）
WIND_INCREASE = 1.3     # 風荷重時の部材許容耐力の割増（30%）
AIR_Q_COEF = 5.0 / 8.0  # 設計用速度圧 qz = 5/8 Vz² [N/m²]（式1・2）
PEAK_FACTOR = 3.2       # ピークファクター g（瞬間風速の評価時間 2〜3 秒）
V0_DEFAULT = 14.0       # 表1-5 に無い地域の基準風速（再現期間12ヶ月）
TOP_LAYERS_M = 3.6      # 上層2層部分（F=1.0 の範囲。図1-18）
# 表1-6 台風時割増係数 Ke（台風接近時に強風対策を行わない場合）
TYPHOON_KE = {"山口県": 1.1, "福岡県": 1.1, "佐賀県": 1.1, "長崎県": 1.1, "熊本県": 1.1, "大分県": 1.1,
              "宮崎県": 1.1, "鹿児島県": 1.2, "沖縄県": 1.2}
PREFECTURES = ("北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
               "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
               "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
               "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
               "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県")
# 所在地を入れていない計画の基準風速（旧来の地方の区分から表1-5 の代表値。所在地 site.location で引き直す）
REGION_V0 = {"北海道(内陸)": 16.0, "北海道(沿岸)": 18.0, "東北(内陸)": 18.0, "東北(沿岸)": 18.0,
             "関東(内陸)": 16.0, "関東(沿岸)": 18.0, "中部(内陸)": 16.0, "中部(沿岸)": 18.0,
             "近畿(内陸)": 16.0, "近畿(沿岸)": 18.0, "中国": 16.0, "四国": 16.0, "九州(北部)": 16.0,
             "九州(南部)": 18.0, "沖縄": 18.0}

# 養生材の充実率 φ（表1-9。メッシュシートは T-5001・♯1004 の 0.700）
SHEET_FILL_RATIO = {
    "なし": 0.0,
    "メッシュシート": 0.7,
    "防音シート": 1.0,
    "密閉シート": 1.0,
    "防音パネル": 1.0,     # 板（日本セイフティー 防音パネル・BG）。風を通さない
}

# 表1-7 地域区分（地表面粗度）ごとの (Zb, Zg, α, κ)
ROUGHNESS = {
    "I": (5.0, 250.0, 0.10, 0.0023),     # 海岸・海上
    "II": (5.0, 350.0, 0.15, 0.0053),    # 草原・田園
    "III": (5.0, 450.0, 0.20, 0.010),    # 郊外・森
    "IV": (10.0, 550.0, 0.27, 0.018),    # 一般市街地
    "V": (20.0, 650.0, 0.35, 0.034),     # 大都市市街地
}


class CapacityError(Exception):
    pass


@dataclass
class CapacityValue:
    value: float
    unit: str
    verified: bool
    source: str
    # 由来した capacity.csv の行。未確認値をどの行で差し替えればよいかを
    # 帳票側に伝えるために持つ（補間値なら元の2行ぶん入る）
    series_id: str = ""
    item: str = ""
    keys: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.value}{self.unit}" + ("" if self.verified else "（未確認値）")

    @property
    def rows(self) -> list[str]:
        """capacity.csv の該当行を series_id,item,key 形式で返す."""
        return [f"{self.series_id},{self.item},{k}" for k in self.keys]

    def unverified(self, label: str) -> Optional["UnverifiedCapacity"]:
        if self.verified:
            return None
        return UnverifiedCapacity(
            label=label, value=self.value, unit=self.unit,
            series_id=self.series_id, item=self.item, keys=self.keys,
            source=self.source,
        )


@dataclass
class UnverifiedCapacity:
    """未確認のまま計算に使われた耐力値と、その差し替え先の行."""

    label: str          # 何に使われた値か（例: ジャッキ(繰出し450mm)許容支持力）
    value: float
    unit: str
    series_id: str
    item: str
    keys: tuple[str, ...]
    source: str

    @property
    def rows(self) -> list[str]:
        return [f"{self.series_id},{self.item},{k}" for k in self.keys]

    @property
    def where(self) -> str:
        """差し替える行の指示（key が複数なら補間元の両方）."""
        return f"{self.item}（key={('・'.join(self.keys)) or '—'}）"

    def describe(self) -> str:
        return f"{self.where} {self.value}{self.unit} ← {self.label}"


def load_capacities(series_id: str, path: Optional[Path] = None) -> dict[tuple[str, str], CapacityValue]:
    p = Path(path) if path else DATA_DIR / "capacity.csv"
    out: dict[tuple[str, str], CapacityValue] = {}
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["series_id"] != series_id:
                continue
            out[(row["item"], row["key"])] = CapacityValue(
                value=float(row["value"]),
                unit=row["unit"],
                verified=row["verified"].strip().lower() in ("yes", "true", "1"),
                source=row["source"],
                series_id=row["series_id"],
                item=row["item"],
                keys=(row["key"],),
            )
    if not out:
        raise CapacityError(f"系列 {series_id} の耐力値が {p} にありません")
    return out


def load_wind_regions(path: Optional[Path] = None) -> dict[str, tuple[float, str]]:
    p = Path(path) if path else DATA_DIR / "wind_region.csv"
    out = {}
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["region"]] = (float(row["v0_ms"]), row["source"])
    return out


# ---- 追加入力4項目（指示書§6） -------------------------------------------


@dataclass
class SiteCondition:
    """構造計算に必要な追加入力4項目."""

    region: str = "関東(内陸)"          # 建設地の地方（所在地 location が無いときの代表値）
    v0_ms: Optional[float] = None       # 基準風速。None なら location（無ければ region）から表1-5 で引く
    roughness: str = "III"              # 地域区分 I〜V（表1-7）
    sheet_type: str = "メッシュシート"   # 養生材仕様
    adjacent_factor: float = 1.0        # 近接高層建築物による割増係数 EB（1.0〜1.3）
    region_factor: float = 1.0          # 小地形による影響係数 Eg（崖上・傾斜地。ほかは 1.0）
    gamma: Optional[float] = None       # 第2構面風力低減係数 γ。None なら 1−φ（式1・6-1）
    correction_f: Optional[float] = None  # 設置位置による補正係数 F。None なら建物外壁に沿う足場 1+0.31φ（表1-10 B）
    period_days: int = 90               # 設置期間
    simultaneous_loaded_levels: int = 2  # 同時に積載する作業層数（実務: 2層以内）
    # 地盤の許容支持力度（kN/m²）。None なら建災防東京支部「計画届作成の手引（第6版）」p124 の例（密実砂 中期
    # 3kgf/cm²＝29N/cm²＝290kN/m²）で検定し、地盤調査の値を入れるよう書き添える
    ground_bearing_kn_m2: Optional[float] = None
    location: str = ""                  # 所在地（都道府県＋市区町村。例「千葉県千葉市」）。表1-5・表1-6 を引く
    typhoon_measures: bool = False      # 台風接近時に強風対策をする（する計画なら Ke=1.0）

    def prefecture(self) -> str:
        loc = self.location or ""
        if "23区" in loc or "特別区" in loc:
            return "東京都"
        return next((p for p in PREFECTURES if p in loc or p[:-1] == loc[:len(p) - 1]), "")

    def base_wind_speed(self) -> tuple[float, str]:
        if self.v0_ms is not None:
            return self.v0_ms, "利用者指定値"
        if self.location:
            return kasetsu_v0(self.location)
        if self.region not in REGION_V0:
            raise CapacityError(
                f"未知の地域区分です: {self.region}（候補: {', '.join(REGION_V0)}）"
            )
        return REGION_V0[self.region], (f"{self.region}の代表値（表1-5）。所在地 site.location を入れると"
                                        "市区町村で引き直す")

    def typhoon_factor(self) -> tuple[float, str]:
        if self.typhoon_measures:
            return 1.0, "台風接近時に強風対策を行う"
        pref = self.prefecture()
        ke = TYPHOON_KE.get(pref, 1.0)
        return ke, (f"表1-6（{pref}）" if ke > 1.0 else "表1-6 の地域外")

    def fill_ratio(self) -> float:
        if self.sheet_type not in SHEET_FILL_RATIO:
            raise CapacityError(
                f"未知の養生材です: {self.sheet_type}"
                f"（候補: {', '.join(SHEET_FILL_RATIO)}）"
            )
        return SHEET_FILL_RATIO[self.sheet_type]


# ---- 計算結果 -------------------------------------------------------------


@dataclass
class WindResult:
    v0_ms: float
    v0_source: str
    height_m: float
    k_height: float          # 瞬間風速分布係数 S＝G×E（式1・4）
    e_adjacent: float        # 近接高層建築物による割増係数 EB
    s_region: float          # 小地形による影響係数 Eg
    v_design_ms: float       # Vz＝V0・Ke・S・EB・Eg
    q_n_m2: float            # qz＝5/8 Vz²
    fill_ratio: float        # φ
    c_force: float           # その他の部分の風力係数（F＝1+0.31φ）
    ke: float = 1.0
    ke_source: str = ""
    roughness: str = "III"
    g_factor: float = 0.0    # ガストファクター G
    e_factor: float = 0.0    # 鉛直分布係数 E
    gamma: float = 0.0
    k_resist: float = 0.0    # 抵抗係数 K＝1.2φ/(1−φ)²
    c0: float = 0.0          # 基本風力係数 C0
    aspect: float = 0.0      # 縦横比 2H/B
    b_m: float = 0.0
    r_shape: float = 0.0     # 形状補正係数 R
    f_main: float = 1.0      # その他の部分の F
    f_top: float = 1.0       # 上層2層部分の F
    c_top: float = 0.0       # 上層2層部分の風力係数


@dataclass
class WallTieResult:
    lh_m: float                 # 水平間隔
    lw_m: float                 # 垂直間隔
    tributary_area_m2: float
    force_kn: float             # P = C·q·lh·lw
    allowable_kn: float         # 許容耐力
    allowable_increased_kn: float  # ×1.3
    ratio: float                # 検定比 P / (許容×1.3)
    ok: bool
    source: str
    verified: bool
    governing: Optional[str] = None   # 支配的な壁つなぎの位置（どの1本が効いているか）
    unverified_caps: list["UnverifiedCapacity"] = field(default_factory=list)
    # 建地が座屈するときに壁つなぎへ掛かる水平荷重（計画届作成の手引 p130: 1スパンの鉛直荷重×5%×受け持つスパン数）
    buckle_kn: float = 0.0
    buckle_spans: float = 0.0
    # 上端の壁つなぎ（上層2層部分。足場の天端までのはね出しを張出梁、その下を単純梁とみた支点反力。手引 p244 図1-22a・
    # 計算例「壁つなぎ上部2層部分の検討」R = (½W1·b²)/a + W1·b + ½W2·a、W1 = qz·C1·b2、W2 = qz·C2·b2）
    top_kn: float = 0.0
    top_where: str = ""

    @property
    def top_ratio(self) -> float:
        return self.top_kn / self.allowable_increased_kn if self.allowable_increased_kn else 0.0

    @property
    def buckle_ratio(self) -> float:
        return self.buckle_kn / self.allowable_increased_kn if self.allowable_increased_kn else 0.0


def tie_remedy(tie: "WallTieResult") -> str:
    """壁つなぎ NG のとき、どれだけ詰めればよいか（作用力は支配面積に比例するので面積を割る）."""
    if tie.ratio <= 0:
        return "壁つなぎ間隔を詰める、または高耐力品への変更を検討してください"
    a_req = tie.tributary_area_m2 / tie.ratio
    cut = (1 - 1 / tie.ratio) * 100
    lw_req = tie.lw_m / tie.ratio
    p_req = tie.force_kn / 1.3
    return (f"支配面積を{a_req:.2f}m²以下に（いま{tie.tributary_area_m2:.2f}m²、{cut:.0f}%減）。"
            f"例: 縦の受け持ち{tie.lw_m:.2f}m を{lw_req:.2f}m 以下に（壁つなぎの段を増やす）、"
            f"または許容耐力{p_req:.2f}kN 以上の壁つなぎに替える（いま{tie.allowable_kn:.2f}kN）")


@dataclass
class PostResult:
    # 検定値の元になった数（計算書を追えるようにするため持つ）
    n_posts: int
    total_weight_kg: float
    deck_capacity_kn: float
    loaded_levels: int
    dead_load_kn: float
    live_load_kn: float
    extra_load_kn: float          # 荷受けステージ等の局所荷重
    total_kn: float
    jack_extension_mm: int
    allowable_kn: float
    ratio: float
    ok: bool
    governing: str              # 支配する検定（ジャッキ / 支柱）
    source: str
    verified: bool
    # 未確認だった耐力値。警告文に実際の項目と差し替え先の行を挙げるために持つ
    unverified_caps: list["UnverifiedCapacity"] = field(default_factory=list)
    # 作業床許容積載の出典（計算書に「capacity.csv」とだけ書いても確認できない）
    deck_source: str = ""
    # 帳票の呼び名（枠組は建枠）
    vertical_member_name: str = "支柱"
    # 荷受けステージの偏心で内側建地に生じる引抜き（1本あたり）と、その出どころ。
    # 自重 dead_load_kn で抑えられなければジャッキベースが浮く
    inner_uplift_kn: float = 0.0
    uplift_source: str = ""
    # 張出ブラケットの区間がある計画か。拡幅部の行で検定したか／無くて通常値だったか
    widened: bool = False
    widened_note: str = ""
    # 支配した検定の軸力に局所荷重（ステージ）が入っているか。荷取り部の行がある
    # 系列では一般部（局所荷重なし）と荷取り部を別々に検定するので、計算書の式が変わる
    includes_extra: bool = True
    # 支配しなかった側の検定（一般部／荷取り部／ジャッキ）。計算書の参考行
    other_checks: list[str] = field(default_factory=list)

    @property
    def uplift_ok(self) -> bool:
        return self.inner_uplift_kn <= self.dead_load_kn + 1e-9

    @property
    def unverified_items(self) -> list[str]:
        return [c.label for c in self.unverified_caps]


@dataclass
class OpeningCheck:
    """開口部（梁枠）1箇所の構造検定.

    - 梁枠上の積載: 作業床許容積載×梁枠スパン数×同時載荷層 ≦ 開口部上方許容積載荷重
    - 支点: 梁枠に乗る支柱1本の軸力（梁枠より上の自重＋積載）≦ 梁枠の支点許容支持力
    - 両端支柱: 通常の軸力＋梁枠の反力 ≦ 支柱の許容支持力
    """

    index: int
    edge_index: int
    beam_span_mm: int
    beam_model: str
    n_inner_posts: int
    live_above_kn: float
    live_limit_kn: Optional[float]
    live_ok: bool
    live_per_span_limit_kn: Optional[float]
    support_kn: float
    support_allow_kn: Optional[float]
    support_source: str
    support_ok: bool
    reaction_kn: float
    end_post_kn: float
    end_post_allow_kn: float
    end_post_ok: bool

    @property
    def ok(self) -> bool:
        """成立か。梁枠上の積載制限は「制限を表示して運用する」条件であって不成立ではない."""
        return self.support_ok and self.end_post_ok

    @property
    def condition(self) -> str:
        """成立条件（積載制限）。無ければ空."""
        if self.live_ok or self.live_per_span_limit_kn is None:
            return ""
        return f"梁枠上の積載を1スパン{self.live_per_span_limit_kn}kN以下に制限"


@dataclass
class StructuralResult:
    site: SiteCondition
    wind: WindResult
    wall_tie: WallTieResult
    post: PostResult
    # warnings は「対応が要るもの」だけ。検定条件の説明は notes へ分ける
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # 未確認のまま使われた耐力値。文字列（項目名）と差し替え先の行の両方を持つ
    unverified_used: list[str] = field(default_factory=list)
    unverified_rows: list[UnverifiedCapacity] = field(default_factory=list)
    # 開口部（梁枠）ごとの検定。無ければ空
    openings: list[OpeningCheck] = field(default_factory=list)
    # 拡幅・張出ブラケット1基ごとの検定（check_widen_brackets）。無ければ空
    brackets: list["BracketCheck"] = field(default_factory=list)
    # 脚部の地盤支持力（check_ground_bearing）
    ground: Optional["GroundBearing"] = None

    @property
    def all_ok(self) -> bool:
        return (self.wall_tie.ok and self.post.ok and all(b.ok for b in self.brackets)
                and all(o.ok for o in self.openings) and (self.ground is None or self.ground.ok))


@dataclass
class BracketCheck:
    """拡幅・張出ブラケット1基の検定（作用 N ≦ ブラケットの許容支持力）."""

    name: str
    load_kn: float
    allowable_kn: float
    detail: str
    source: str = ""

    @property
    def ratio(self) -> float:
        return self.load_kn / self.allowable_kn if self.allowable_kn else float("inf")

    @property
    def ok(self) -> bool:
        return self.ratio <= 1.0

    def describe(self) -> str:
        return (f"{self.name}: N={self.load_kn:.2f}kN（{self.detail}）≦ 許容{self.allowable_kn}kN"
                f"（検定比{self.ratio:.2f}）{'OK' if self.ok else 'NG'}")


def widened_by_bridges(model: ScaffoldModel) -> bool:
    """張り出しの横の本体の足場の隅を拡幅ブラケットで広げたか、跳ね出しの上段の端に張出ブラケットを出したか
    （setback_tiers.hane_bridges）. そのブラケットを付けた支柱は拡幅部の許容支持力で検定する（日建 ND1800 11.0→8.8kN/本）."""
    return bool(getattr(model, "corner_bridges", None) or getattr(model, "hane_end_ext", None)
                or getattr(model, "width_change", None))


def check_widen_brackets(model: ScaffoldModel, caps: dict, site: SiteCondition) -> tuple[list[BracketCheck], list[str]]:
    """拡幅・張出ブラケット1基の検定（reports/くさび式足場の拡幅ブラケット.md。3D の gosub 758／759・数量と同じ組み方）.

    拡幅（隅の升目の外、全高で1回）: ブラケットに先端の支柱が載る。先端の支柱1本の軸力 = 先端の支柱の自重 ＋ 各層の
    布材（先端側の半分）・床（1/4） ＋ 積載（作業床許容積載荷重 1スパン分を拡幅した升目の4本で分担、同時載荷の層数まで）。
    張出（跳ね出しの上段の端、各層）: 床をブラケット2基で受ける。1基 = 床・先端の手すり柱・手すりの自重（半分）＋
    積載（作業床許容積載荷重 1スパン分の半分）。どちらも1スパン分の許容積載を小さな床に載せる安全側の見方.
    返り値は（検定, 注記）。ブラケットの許容支持力の行が無い系列は検定せず、注記で知らせる."""
    m = model.master
    g = 9.80665 / 1000.0
    row = int(model.post_row_spacing_mm)
    cap_deck = caps.get(("作業床許容積載荷重", "スパン"))
    live_span = cap_deck.value if cap_deck else 0.0
    out: list[BracketCheck] = []
    notes: list[str] = []

    def kg(part) -> float:
        return float(part.weight_kg) if part is not None else 0.0

    def post_kg(nominal: int) -> float:
        p = next((p for p in m.by_category("支柱") if p.nominal_dim == nominal and "根がらみ" not in p.note), None)
        return kg(p)

    n_out = len(model.plan.outline.edges)
    lengths = sorted({p.nominal_dim for p in m.by_category("支柱")
                      if "根がらみ" not in p.note and "屋根" not in p.note and p.nominal_dim > 0}, reverse=True)
    for ei, cb in (getattr(model, "corner_bridges", None) or {}).items():
        if model.edge_subset is not None and ei not in model.edge_subset:
            continue
        w, side, lv = int(cb[0]), cb[1], list(cb[2])
        cap = caps.get(("ブラケット許容支持力", "拡幅"))
        if cap is None:
            notes.append(f"拡幅ブラケット{w}の許容支持力が capacity.csv に無いため、ブラケット単体は検定していません"
                         f"（系列 {m.series_id}。メーカー値を確認してください）")
            continue
        cl = row if side == 1 else int(model.row_spacing_of((ei - 1) % n_out))
        k = len(lv)
        top = max(model.own_height(ei), model.own_height((ei - 1) % n_out))
        rest, tip_kg = top - lv[0], 0.0
        while rest > 10 and lengths:
            pick = next((L for L in lengths if L <= rest + 10), lengths[-1])
            tip_kg += post_kg(pick)
            rest -= pick
        rail_w, rail_c = m.find("布材", w), m.find("布材", cl)
        deck = m.deck_parts(240, cl)
        per_level = 3 * kg(rail_w) / 2 + kg(rail_c) / 2 + kg(deck) / 4
        dead = (tip_kg + k * per_level) * g
        live = live_span * min(k, site.simultaneous_loaded_levels) / 4.0
        out.append(BracketCheck(
            f"拡幅ブラケット{w}（{model.face_name(ei)}の隅の升目の先端の支柱）", round(dead + live, 3), cap.value,
            f"自重{dead:.2f}＋積載{live:.2f}（{min(k, site.simultaneous_loaded_levels)}層×{live_span}kN÷4本）",
            cap.source))
    for (ei, end), w in (getattr(model, "hane_end_ext", None) or {}).items():
        if model.edge_subset is not None and ei not in model.edge_subset:
            continue
        w = int(w)
        cap = caps.get(("ブラケット許容支持力", "張出"))
        if cap is None:
            notes.append(f"張出ブラケット{w}の許容支持力が capacity.csv に無いため、ブラケット単体は検定していません"
                         f"（系列 {m.series_id}。メーカー値を確認してください）")
            continue
        deck = m.deck_parts(500 if w > 540 else 240, row)
        dead = (kg(deck) / 2 + post_kg(1350) + 2 * kg(m.find("布材", row)) / 2 + 2 * kg(m.find("布材", w)) / 2) * g
        live = live_span / 2.0
        out.append(BracketCheck(
            f"張出ブラケット{w}（{model.face_name(ei)}の{'始点' if end == 's' else '終点'}の先）", round(dead + live, 3),
            cap.value, f"自重{dead:.2f}＋積載{live:.2f}（{live_span}kN÷2基）", cap.source))
    # 拡幅・縮幅（width_change）: 幅を変える床の拡幅ブラケット1基に、先端の支柱（新しい外側の支柱）1本が載る。
    # 先端の支柱の軸力 = 支柱の自重 ＋ 各層の外側の布材（床・手すり・中桟。両隣のスパンの半分ずつ＝1スパン分）・腕木の半分・
    # 床の外側の半分 ＋ 積載（作業床許容積載荷重 1スパン分の半分を外側の支柱が受ける、同時載荷の層数まで）
    from .width_change import change_height_mm, faces, upper_levels

    wc = getattr(model, "width_change", None)
    for ep in (faces(model) if wc is not None else []):
        if model.edge_subset is not None and ep.edge_index not in model.edge_subset:
            continue
        cap = caps.get(("ブラケット許容支持力", "拡幅"))
        if cap is None:
            notes.append(f"{wc.label}の拡幅ブラケットの許容支持力が capacity.csv に無いため、ブラケット単体は検定していません"
                         f"（系列 {m.series_id}。メーカー値を確認してください）")
            break
        k = upper_levels(model, ep.edge_index)
        sp = int(max(ep.spans))
        rest, tip_kg = model.own_height(ep.edge_index) - change_height_mm(model, ep.edge_index), 0.0
        while rest > 10 and lengths:
            pick = next((L for L in lengths if L <= rest + 10), lengths[-1])
            tip_kg += post_kg(pick)
            rest -= pick
        per_level = (3 * kg(m.find("布材", sp)) + kg(m.find("布材", wc.to_mm)) / 2
                     + sum(kg(m.deck_parts(w, sp)) for w in wc.to_decks) / 2)
        dead = (tip_kg + k * per_level) * g
        live = live_span * min(k, site.simultaneous_loaded_levels) / 2.0
        out.append(BracketCheck(
            f"拡幅ブラケット305（{wc.label}・{model.face_name(ep.edge_index)}の先端の支柱 スパン{sp}）", round(dead + live, 3),
            cap.value, f"自重{dead:.2f}＋積載{live:.2f}（{min(k, site.simultaneous_loaded_levels)}層×{live_span}kN÷2）",
            cap.source))
    if out:
        worst = max(out, key=lambda b: b.ratio)
        notes.append("ブラケットの検定（1基あたり）: " + worst.describe()
                     + ("" if len(out) == 1 else f"（ほか{len(out) - 1}基は検定比がこれ以下）"))
    return out, notes


# ---- 計算本体 -------------------------------------------------------------


def kasetsu_v0(location: str) -> tuple[float, str]:
    """所在地から表1-5 の基準風速 V0（m/s）. 表に無い地域は 14m/s。市町村は表の名前（合併前の名前を含む）で探す."""
    pref = SiteCondition(location=location).prefecture()
    best = None
    with open(DATA_DIR / "kasetsu_wind_v0.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["pref"] != pref:
                continue
            areas = [a for a in row["areas"].split("|") if a]
            excepts = [a for a in row["except"].split("|") if a]
            if any(e in location for e in excepts):
                continue
            hit = [a for a in areas if a in location]
            if areas and not hit:
                continue
            rank = max((len(a) for a in hit), default=0)
            if best is None or rank > best[0]:
                best = (rank, float(row["v0_ms"]), row["note"])
    if best is None:
        return V0_DEFAULT, f"表1-5 に無い地域（{pref or location}）は 14m/s"
    return best[1], f"{best[2]}（{location}）"


def gust_and_profile(height_m: float, roughness: str = "III") -> tuple[float, float]:
    """(G, E): 変動風速のガストファクターと平均風速の鉛直分布係数（式1・4-2・1・4-3. Z<Zb は Zb で見る）."""
    if roughness not in ROUGHNESS:
        raise CapacityError(f"未知の地域区分です: {roughness}（I〜V）")
    zb, zg, alpha, kappa = ROUGHNESS[roughness]
    z = max(height_m, zb)
    g = 1.0 + PEAK_FACTOR * math.sqrt(6.0 * kappa) * (10.0 / z) ** alpha
    e = 1.7 * (z / zg) ** alpha
    return g, e


def height_factor(height_m: float, roughness: str = "III") -> float:
    """瞬間風速分布係数 S＝G×E（式1・4-4）."""
    g, e = gust_and_profile(height_m, roughness)
    return g * e


def basic_force_coefficient(phi: float) -> tuple[float, float]:
    """(K, C0): 抵抗係数と基本風力係数（式1・7-1〜3。log は常用対数。φ=1 は C0=2.0）."""
    if phi <= 0:
        return 0.0, 0.0
    if phi >= 1.0:
        return float("inf"), 2.0
    k = 1.2 * phi / (1.0 - phi) ** 2
    if k <= 0.73:
        return k, k / (1.0 + k / 4.0) ** 2
    c0 = 2.8 * math.log10(k + 0.6 - math.sqrt(1.2 * k + 0.36)) - 2.8 * math.log10(k) + 2.0
    return k, c0


def shape_factor(aspect: float) -> float:
    """形状補正係数 R（式1・8-2: 地上から建つ。2H/B ≦1.5 は 0.6、≧59 は 1.0）."""
    if aspect <= 1.5:
        return 0.6
    if aspect >= 59:
        return 1.0
    return 0.5813 + 0.013 * aspect - 0.0001 * aspect ** 2


def wind_force_coefficient(fill_ratio: float, gamma: Optional[float] = None, f: Optional[float] = None,
                           r: float = 0.6) -> float:
    """風力係数 C = (0.11 + 0.09γ + 0.945×C0×R) × F（式1・6-1）."""
    g = (1.0 - fill_ratio) if gamma is None else gamma
    ff = (1.0 + 0.31 * fill_ratio) if f is None else f
    return (0.11 + 0.09 * g + 0.945 * basic_force_coefficient(fill_ratio)[1] * r) * ff


def compute_wind(model: ScaffoldModel, site: SiteCondition, height_mm: Optional[float] = None) -> WindResult:
    v0, v0_src = site.base_wind_speed()
    ke, ke_src = site.typhoon_factor()
    # 速度圧は最も高い部分（地上高さ Z＝足場の天端）で見る。敷地の低い側で継ぎ足した分は名目より高い
    h_m = (height_mm if height_mm else model.scaffold_height_mm) / 1000.0
    g, e = gust_and_profile(h_m, site.roughness)
    sz = g * e
    v = v0 * ke * sz * site.adjacent_factor * site.region_factor
    q = AIR_Q_COEF * v**2
    phi = site.fill_ratio()
    gamma = (1.0 - phi) if site.gamma is None else site.gamma
    k_res, c0 = basic_force_coefficient(phi)
    # 縦横比は地上から建つシートの 2H/B。B は面の長さの短い方（R が大きく出る安全側）
    lengths = [e_.scaffold_length for e_ in model.plan.edges if e_.scaffold_length > 0]
    b_m = (min(lengths) if lengths else 1000.0) / 1000.0
    aspect = 2.0 * h_m / b_m
    r = shape_factor(aspect)
    f_main = (1.0 + 0.31 * phi) if site.correction_f is None else site.correction_f
    f_top = 1.0
    c = (0.11 + 0.09 * gamma + 0.945 * c0 * r) * f_main
    c_top = (0.11 + 0.09 * gamma + 0.945 * c0 * r) * f_top
    return WindResult(
        v0_ms=v0,
        v0_source=v0_src,
        height_m=round(h_m, 3),
        k_height=round(sz, 4),
        e_adjacent=site.adjacent_factor,
        s_region=site.region_factor,
        v_design_ms=round(v, 3),
        q_n_m2=round(q, 1),
        fill_ratio=phi,
        c_force=round(c, 4),
        ke=ke, ke_source=ke_src, roughness=site.roughness,
        g_factor=round(g, 4), e_factor=round(e, 4), gamma=round(gamma, 4),
        k_resist=round(k_res, 3) if k_res != float("inf") else k_res, c0=round(c0, 4),
        aspect=round(aspect, 3), b_m=round(b_m, 3), r_shape=round(r, 4),
        f_main=round(f_main, 4), f_top=f_top, c_top=round(c_top, 4),
    )


@dataclass
class TieTributary:
    """壁つなぎ1本が受け持つ支配面積."""

    edge_index: int
    position_mm: float
    height_mm: int
    lh_m: float          # 水平方向の支配幅（受け持ち領域の横の広がり）
    lw_m: float          # 垂直方向の支配高さ（同じく縦の広がり）
    area_m2: float = 0.0  # 受け持ち領域の面積（格子なら lh×lw、取付部の壁つなぎが混じると多角形）


def _clip(poly: list[tuple[float, float]], a: float, b: float, c: float) -> list[tuple[float, float]]:
    """半平面 a·x + b·z ≤ c で凸多角形を切る（Sutherland–Hodgman）."""
    out: list[tuple[float, float]] = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp = a * p[0] + b * p[1] - c
        fq = a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _poly_area(poly: list[tuple[float, float]]) -> float:
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                   - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2.0 if len(poly) >= 3 else 0.0


def tie_tributaries(model: ScaffoldModel) -> list[TieTributary]:
    """壁つなぎごとの支配面積を求める（Phase 4）.

    面（足場長×足場高さの長方形）を「最も近い壁つなぎ」で分割し（ボロノイ分割）、
    各壁つなぎの受け持ち領域とする。境界の扱いはそこが構造的な支点かどうかで決まる:

    - 最下段の下側: 足場脚部（ジャッキ・根がらみ）は支点なので **半分**（高さの中点まで）
    - 最上段の上側: 自由端の張り出しなので **全長**
    - 面の端（コーナー）: コーナー支柱は両面共有で直交面に支持される支点なので **半分**

    格子状の配置では従来の「隣との中間まで」の長方形と一致する。以前は同じ高さの
    列の中だけで隣を探していたため、荷受けステージ取付部のように格子と違う高さに
    1本だけ足された壁つなぎが、右隣を「面の端まで」と数えて14.6m²の支配的な1本に
    なっていた（壁つなぎを足したのに検定が悪化する）。近い壁つなぎで分ければ、
    足した壁つなぎは周りの領域を分担するだけで、どの1本の面積も増えない。

    ⚠️ 境界の支点扱いは工学的仮定。提出図書に使う際は有資格者の確認を受けること。
    """
    out: list[TieTributary] = []
    # 昇降機マストの控えはマストを支えるもので、足場の風荷重は負担しない
    ties = [t for t in model.wall_ties if getattr(t, "kind", "grid") != "hoist"]
    if not ties:
        return out
    top = float(model.scaffold_height_mm)
    from .ties import unreachable_bands

    bands = unreachable_bands(model)

    for edge in model.plan.edges:
        edge_ties = [t for t in ties if t.edge_index == edge.edge_index]
        if not edge_ties:
            continue
        length = float(edge.scaffold_length)
        # 面ごとの高さ（セットバックで低い面）。全体の天端で受け持ちを取ると、低い面の上の壁つなぎが
        # 実際には無い高さの風まで受けることになる
        top = float(model.elevation_of(edge.edge_index).total_height)
        pts = [(float(t.position_mm), float(t.height_mm)) for t in edge_ties]
        for t, (x0, z0) in zip(edge_ties, pts):
            poly = [(0.0, 0.0), (length, 0.0), (length, top), (0.0, top)]
            # 支点との境界: 地盤（下）とコーナー（左右）は中点まで。上端は自由端
            poly = _clip(poly, 0.0, -1.0, -z0 / 2.0)             # z ≥ z0/2
            poly = _clip(poly, -1.0, 0.0, -x0 / 2.0)             # x ≥ x0/2
            poly = _clip(poly, 1.0, 0.0, (length + x0) / 2.0)    # x ≤ (L+x0)/2
            # 壁つなぎが届かない帯（渡した区間の深い所）はこの検定の外。帯の風荷重は
            # 別途の控えが受ける前提で、帯の手前までを受け持ち領域にする
            for a, b in bands.get(edge.edge_index, []):
                if x0 <= a + 1e-6:
                    poly = _clip(poly, 1.0, 0.0, a)              # x ≤ a
                elif x0 >= b - 1e-6:
                    poly = _clip(poly, -1.0, 0.0, -b)            # x ≥ b
            for (x1, z1) in pts:
                if abs(x1 - x0) < 1e-9 and abs(z1 - z0) < 1e-9:
                    continue
                # 垂直二等分線: t に近い側を残す
                poly = _clip(poly, 2.0 * (x1 - x0), 2.0 * (z1 - z0),
                             x1 * x1 + z1 * z1 - x0 * x0 - z0 * z0)
                if not poly:
                    break
            if poly:
                xs = [p[0] for p in poly]
                zs = [p[1] for p in poly]
                lh = (max(xs) - min(xs)) / 1000.0
                lw = (max(zs) - min(zs)) / 1000.0
                area = _poly_area(poly) / 1e6
            else:
                lh = lw = area = 0.0
            out.append(TieTributary(
                edge_index=edge.edge_index,
                position_mm=t.position_mm,
                height_mm=t.height_mm,
                lh_m=lh, lw_m=lw, area_m2=area,
            ))
    return out


def top_tie_reaction(q_kn_m2: float, c1: float, c2: float, b2: float, b: float, a: float) -> float:
    """上端の壁つなぎの反力 R = (½W1·b²)/a + W1·b + ½W2·a（W1 = q·C1·b2、W2 = q·C2·b2）. b は天端までのはね出し、a は下の段まで."""
    w1 = q_kn_m2 * c1 * b2
    w2 = q_kn_m2 * c2 * b2
    return (0.5 * w1 * b ** 2) / a + w1 * b + 0.5 * w2 * a


def top_tie_force(model: ScaffoldModel, wind: WindResult) -> tuple[float, str]:
    """上端の壁つなぎの反力（kN）と、その位置. 面ごとに、いちばん上の段の壁つなぎの水平間隔 b2（最大）、天端までの
    はね出し b、その下の段までの間隔 a から R = (½W1·b²)/a + W1·b + ½W2·a."""
    worst = (0.0, "")
    by_face: dict[int, list] = {}
    for t in model.wall_ties:
        by_face.setdefault(t.edge_index, []).append(t)
    q = wind.q_n_m2 / 1000.0
    from .ties import unreachable_bands

    bands = unreachable_bands(model)
    for ei, ts in by_face.items():
        hs = sorted({t.height_mm for t in ts})
        if len(hs) < 2:
            continue
        top, below = hs[-1], hs[-2]
        xs = sorted(t.position_mm for t in ts if t.height_mm == top)
        ep = next((e for e in model.plan.edges if e.edge_index == ei), None)
        if ep is None or not xs:
            continue
        # 受け持ち幅は両隣の壁つなぎとの中間まで。面の端は角（隣の面の足場）が支点になるので、角までの半分
        # （全体の検定 tie_tributaries と同じ受け持ちの取り方）
        # 壁つなぎが躯体に届かない帯（渡した区間の深い所）は検定の外（別途の控え。run_structural の警告）
        lo, hi = 0.0, float(ep.scaffold_length)
        for a0, b0 in bands.get(ei, []):
            if a0 <= lo + 1.0 and b0 <= xs[0] + 1.0:
                lo = max(lo, b0)
            if b0 >= hi - 1.0 and a0 >= xs[-1] - 1.0:
                hi = min(hi, a0)
        pts = [min(lo, xs[0])] + xs + [max(hi, xs[-1])]
        b2 = max((pts[i + 1] - pts[i - 1]) / 2.0 for i in range(1, len(pts) - 1)) / 1000.0
        b = max(0.0, model.elevation_of(ei).total_height - top) / 1000.0
        a = (top - below) / 1000.0
        r = top_tie_reaction(q, wind.c_top, wind.c_force, b2, b, a)
        if r > worst[0]:
            worst = (round(r, 3), f"{model.face_name(ei)} 高さ{top}mm（はね出し{b:.2f}m・下の段まで{a:.2f}m・水平間隔{b2:.2f}m）")
    return worst


def check_wall_tie(
    model: ScaffoldModel, wind: WindResult, caps: dict
) -> WallTieResult:
    """壁つなぎ1箇所あたり P = C·q·lh·lw ≦ 許容耐力×1.3.

    支配面積は壁つなぎごとに求め、最大のもの（支配的な1本）で検定する。
    """
    tribs = tie_tributaries(model)
    governing = None
    if tribs:
        worst = max(tribs, key=lambda t: t.area_m2)
        lh, lw, area = worst.lh_m, worst.lw_m, worst.area_m2
        governing = (
            f"{model.face_name(worst.edge_index)} 始点から{worst.position_mm:.0f}mm "
            f"高さ{worst.height_mm}mm"
        )
    else:
        v_max_mm, h_max_mm = model.wall_tie_max_spacing()
        lw = v_max_mm / 1000.0
        lh = h_max_mm / 1000.0
        area = lh * lw
    p_kn = wind.c_force * wind.q_n_m2 * area / 1000.0  # N → kN

    cap_t = caps.get(("壁つなぎ許容耐力", "引張"))
    cap_c = caps.get(("壁つなぎ許容耐力", "圧縮"))
    if cap_t is None or cap_c is None:
        raise CapacityError("壁つなぎ許容耐力が capacity.csv にありません")
    cap = min(cap_t.value, cap_c.value)
    verified = cap_t.verified and cap_c.verified
    unverified_caps = [
        c for c in (
            cap_t.unverified("壁つなぎ許容耐力(引張)"),
            cap_c.unverified("壁つなぎ許容耐力(圧縮)"),
        ) if c is not None
    ]
    allow_inc = cap * WIND_INCREASE
    ratio = p_kn / allow_inc if allow_inc else float("inf")
    top_kn, top_where = top_tie_force(model, wind)
    return WallTieResult(
        lh_m=round(lh, 3),
        lw_m=round(lw, 3),
        tributary_area_m2=round(area, 3),
        force_kn=round(p_kn, 3),
        allowable_kn=cap,
        allowable_increased_kn=round(allow_inc, 3),
        ratio=round(ratio, 3),
        ok=ratio <= 1.0 and (top_kn / allow_inc if allow_inc else 0.0) <= 1.0,
        source=cap_t.source,
        verified=verified,
        governing=governing,
        unverified_caps=unverified_caps,
        top_kn=top_kn,
        top_where=top_where,
    )


def check_post(
    model: ScaffoldModel,
    quantity: QuantityResult,
    site: SiteCondition,
    caps: dict,
    extra_post_load_kn: float = 0.0,
    extra_load_source: str = "",
    jack_extension_mm: Optional[int] = None,
    widened: bool = False,
    removed_posts: int = 0,
) -> PostResult:
    """建地1本あたり N = 自重 + 積載 ≦ 許容支持力（ジャッキ繰出し長で変動）.

    荷受けステージのような局所荷重がある場合は extra_post_load_kn で加算する。
    平均で見ると直下の建地が抜けるため、最も厳しい1本で検定する。

    jack_extension_mm には敷地高低差を解いた結果の最大繰出し量を渡す。
    ジャッキの許容支持力は繰出し長で落ちる（仮設工業会の建枠の表では
    200mm以下→350mmで約13%減）ので、傾斜地で平坦時の繰出し量のまま
    検定すると危険側になる。

    枠組は建枠の幅で許容値が変わる（900mm未満は簡易枠で約2割低い）。
    capacity.csv に「項目[幅610]」のような幅付きの行があればそれを使い、
    無ければ幅なしの行に落ちる。
    """
    # 枠組は建枠1枚が2脚なので、一側指定でも脚は2列ぶん（その組合せ自体は
    # 法規チェック1でNGになる）
    single_row = (
        model.config.scaffold_form == "一側足場" and not model.master.is_frame
    )
    # 開口部で抜いた建地は地盤に立たない（梁枠より上の分は梁枠両端の建地が受ける＝
    # 計算書4）。総重量を割る本数は実際に立っている本数にする。数量のジャッキ数と同じ
    from .quantity import standing_post_positions

    n_posts = standing_post_positions(model, 1 if single_row else 2) - max(0, removed_posts)
    dead_kn = (quantity.total_weight_kg * 9.80665 / 1000.0) / max(n_posts, 1)

    deck_item = _width_item(caps, "作業床許容積載荷重", model)
    cap_deck = caps.get((deck_item, "スパン"))
    if cap_deck is None:
        raise CapacityError("作業床許容積載荷重が capacity.csv にありません")
    # 1構面(スパン)の積載を両端2本の建地で分担。同時載荷は所定層数まで
    live_kn = cap_deck.value * site.simultaneous_loaded_levels / 2.0
    total = dead_kn + live_kn + extra_post_load_kn

    jack = max(model.elevation.jack_extension, jack_extension_mm or 0)
    cap_jack, _jack_key = _interpolate_capacity(
        caps, _width_item(caps, "ジャッキ許容支持力", model), jack)
    post_item, widened_note = _post_item(caps, model, widened)
    cap_post = caps.get((post_item, "0"))
    # 候補ごとに (名前, 許容, 作用軸力)。荷取りブラケットを付けた支柱は日建では別の
    # 許容値（ND1800 補剛材あり15kN/本）なので、その行があればステージ直下は
    # その値で、一般部の支柱は局所荷重抜きの軸力で、それぞれ検定して厳しい方を採る
    candidates = [("ジャッキ(繰出し%dmm)" % jack, cap_jack, total)]
    stage_row = caps.get(("支柱許容圧縮耐力[荷取り]", "0")) if extra_post_load_kn > 0 else None
    other_checks: list[str] = []
    if cap_post is not None:
        post_name = "支柱（拡幅部）" if "[拡幅部]" in post_item else "支柱"
        if stage_row is not None:
            candidates.append((post_name + "（一般部）", cap_post, dead_kn + live_kn))
            candidates.append(("支柱（荷取り部）", stage_row, total))
        else:
            candidates.append((post_name, cap_post, total))
    def _ratio(c):
        return c[2] / c[1].value if c[1].value else float("inf")
    governing_name, governing_cap, governing_n = max(candidates, key=_ratio)
    for name, cap, n in candidates:
        if name != governing_name:
            other_checks.append(f"{name}: {n:.3f}kN / {cap.value}kN = {_ratio((name, cap, n)):.3f}")

    ratio = governing_n / governing_cap.value if governing_cap.value else float("inf")
    includes_extra = governing_n >= total - 1e-9
    cap_label = f"{governing_name}の許容支持力"
    if extra_post_load_kn > 0 and extra_load_source and includes_extra:
        governing_name += f" ＋{extra_load_source}"

    unverified_caps = [
        c for c in (
            governing_cap.unverified(cap_label),
            cap_deck.unverified("作業床許容積載荷重"),
        ) if c is not None
    ]

    return PostResult(
        n_posts=n_posts,
        total_weight_kg=quantity.total_weight_kg,
        deck_capacity_kn=cap_deck.value,
        loaded_levels=site.simultaneous_loaded_levels,
        dead_load_kn=round(dead_kn, 3),
        live_load_kn=round(live_kn, 3),
        extra_load_kn=round(extra_post_load_kn, 3),
        total_kn=round(governing_n, 3),
        includes_extra=includes_extra,
        other_checks=other_checks,
        jack_extension_mm=jack,
        allowable_kn=governing_cap.value,
        ratio=round(ratio, 3),
        ok=ratio <= 1.0,
        governing=governing_name,
        source=governing_cap.source,
        deck_source=cap_deck.source,
        vertical_member_name=model.master.vertical_member_name,
        verified=governing_cap.verified and cap_deck.verified,
        unverified_caps=unverified_caps,
        widened=widened,
        widened_note=widened_note,
    )


BUCKLE_RATIO = 0.05                    # 建地が座屈するときの水平荷重＝鉛直荷重の5%（手引 p130）
GROUND_BEARING_EXAMPLE_KN_M2 = 290.0   # 手引 p124 の例: 密実砂 中期 3kgf/cm²（29N/cm²）
SILL_BOARD_WIDTH_M = 0.24              # 建地の列に沿って通す敷板（杉の足場板）の幅
JACK_PLATE_DEFAULT_MM = 140.0          # ベースジャッキの底板（手引 p124 の図 140 角）


@dataclass
class GroundBearing:
    """脚部の地盤支持力（手引 p125・p132: ベースジャッキ直下と敷板の下）."""

    foot_kn: float          # 脚1箇所の鉛直荷重（建地の検定の軸力）
    plate_mm: float         # ベースジャッキの底板の一辺
    board_w_m: float        # 敷板の幅
    board_len_m: float      # 敷板の1脚あたりの負担長さ（スパン）
    qa_kn_m2: float         # 地盤の許容支持力度
    qa_source: str
    plate_kn_m2: float
    board_kn_m2: float

    @property
    def plate_ratio(self) -> float:
        return self.plate_kn_m2 / self.qa_kn_m2

    @property
    def board_ratio(self) -> float:
        return self.board_kn_m2 / self.qa_kn_m2

    @property
    def ok(self) -> bool:
        # ジャッキの底板だけでは受けられないのが普通。敷板で面積を増やして受ければよい（手引 p133 の対策）
        return self.board_ratio <= 1.0


def check_ground_bearing(model: ScaffoldModel, post: "PostResult", site: SiteCondition) -> GroundBearing:
    """建地1本の軸力を、ベースジャッキの底板と敷板（幅240をスパンの長さ）で地盤に伝えたときの接地圧."""
    plate = JACK_PLATE_DEFAULT_MM
    for p in list(model.master.by_category("ジャッキ")) + list(model.master.by_category("支柱附属")):
        m = re.search(r"(\d{2,3})\s*角", p.note)
        if m:
            plate = float(m.group(1))
            break
    spans = [s for e in model.plan.edges for s in e.spans]
    span = (max(set(spans), key=spans.count) if spans else 1800) / 1000.0
    qa = site.ground_bearing_kn_m2
    src = "利用者指定（site.ground_bearing_kn_m2）"
    if qa is None:
        qa, src = GROUND_BEARING_EXAMPLE_KN_M2, "計画届作成の手引 p124 の例（密実砂 中期 29N/cm²）"
    n = post.total_kn
    return GroundBearing(
        foot_kn=n, plate_mm=plate, board_w_m=SILL_BOARD_WIDTH_M, board_len_m=span, qa_kn_m2=qa, qa_source=src,
        plate_kn_m2=round(n / (plate / 1000.0) ** 2, 1),
        board_kn_m2=round(n / (SILL_BOARD_WIDTH_M * span), 1))


def beam_support_allowable_kn(part) -> Optional[float]:
    """梁枠の支点当たり許容支持力（note の「許容支持力18.5kN/支点(実大試験)・16.0kN(それ以外)」）.

    条件付きの実大試験値ではなく、並んだ値のうち最小（それ以外の値）を採る。
    """
    m = re.search(r"許容支持力(.*)", part.note)
    if not m:
        return None
    vals = [float(v) for v in re.findall(r"([\d.]+)\s*kN", m.group(1))]
    return min(vals) if vals else None


def check_openings(
    model: ScaffoldModel, openings, post: PostResult, caps: dict
) -> tuple[list[OpeningCheck], list[str], list[str]]:
    """開口部（梁枠）の構造検定。戻り値は (検定, 警告, 注記)."""
    out: list[OpeningCheck] = []
    warnings: list[str] = []
    notes: list[str] = []
    if openings is None or not getattr(openings, "openings", None):
        return out, warnings, notes
    limit = caps.get(("開口部上方許容積載荷重", "合計"))
    cap_deck = caps.get((_width_item(caps, "作業床許容積載荷重", model), "スパン"))
    # 両端支柱の許容は建地圧縮と同じ行（張出区間があれば拡幅部の値）
    post_item, _ = _post_item(caps, model, post.widened)
    cap_post = caps.get((post_item, "0"))
    height = float(model.scaffold_height_mm) or 1.0
    vm = model.master.vertical_member_name
    for i, o in enumerate(openings.openings):
        if o.void:
            continue     # 昇降路（全高で抜く）は梁枠が無い
        beam = model.master.find("梁枠", o.beam_span_mm)
        if beam is None:
            continue
        inner = openings.inner_posts.get(i, [])
        beam_h = float(openings.beam_heights.get(i, 0.0))
        n_spans = max(1, len(inner) + 1)
        loaded = post.loaded_levels
        live_above = (cap_deck.value if cap_deck else 0.0) * n_spans * loaded
        live_limit = limit.value if limit else None
        live_ok = live_limit is None or live_above <= live_limit + 1e-9
        per_span_limit = (live_limit / (n_spans * loaded)) if live_limit else None
        live_design = min(live_above, live_limit) if live_limit else live_above
        # 梁枠に乗る支柱1本: 梁枠より上の自重＋その支柱が受け持つ1スパン分の積載
        frac = max(0.0, (height - beam_h) / height)
        support = post.dead_load_kn * frac + live_design / n_spans
        from .openings import beam_rules

        rules = beam_rules(model)
        allow = rules.get("support_kn", {}).get(int(o.beam_span_mm)) or beam_support_allowable_kn(beam)
        allow_src = rules["source"] if rules.get("support_kn", {}).get(int(o.beam_span_mm)) else beam.note
        support_ok = allow is None or support <= allow + 1e-9
        # 両端支柱: 通常の軸力に梁枠の反力（内側支柱の軸力と梁枠自重の半分）
        beam_kn = beam.weight_kg * 9.80665 / 1000.0
        reaction = (support * len(inner) + beam_kn) / 2.0
        end_post = post.dead_load_kn + post.live_load_kn + reaction
        end_allow = cap_post.value if cap_post else post.allowable_kn
        end_ok = end_post <= end_allow + 1e-9
        chk = OpeningCheck(
            index=i, edge_index=o.edge_index, beam_span_mm=o.beam_span_mm, beam_model=beam.model_no,
            n_inner_posts=len(inner), live_above_kn=round(live_above, 3), live_limit_kn=live_limit,
            live_ok=live_ok, live_per_span_limit_kn=(round(per_span_limit, 3) if per_span_limit else None),
            support_kn=round(support, 3), support_allow_kn=allow, support_source=allow_src,
            support_ok=support_ok, reaction_kn=round(reaction, 3), end_post_kn=round(end_post, 3),
            end_post_allow_kn=end_allow, end_post_ok=end_ok,
        )
        out.append(chk)
        where = f"{model.face_name(o.edge_index)}の開口部（梁枠{beam.model_no} {o.beam_span_mm}mm）"
        if not live_ok:
            notes.append(
                f"{where}: 梁枠上の積載は{live_limit:.2f}kN以下に制限してください"
                f"（作業床の通常積載{live_above:.2f}kN＝{cap_deck.value if cap_deck else 0}kN×{n_spans}スパン×{loaded}層に対し、"
                f"1スパン{per_span_limit:.2f}kN＝約{per_span_limit * 1000 / 9.80665:.0f}kgまで）"
            )
        if allow is None:
            warnings.append(
                f"{where}: 梁枠の支点当たり許容支持力がマスタに無く、梁枠に乗る{vm}の軸力"
                f"{support:.2f}kN/本の検定ができません。メーカー値で確認してください"
            )
        elif not support_ok:
            warnings.append(
                f"{where}: 梁枠に乗る{vm}の軸力{support:.2f}kN/本が梁枠の支点許容{allow:.2f}kNを超えます。"
                "梁枠上の積載の低減か、支点の多い梁枠への変更が必要です"
            )
        if not end_ok:
            # 系列に補強の決めがあれば、足りるいちばん軽い補強を出す（ミレニューム Q16）
            opts = [(n, kn, src) for n, kn, src in rules.get("end_post_options", ()) if end_post <= kn + 1e-9]
            fix = (f"両端{vm}を{opts[0][0]}（許容{opts[0][1]:.1f}kN・{opts[0][2]}）で補強してください"
                   if opts else (f"系列の補強（" + "・".join(f"{n} {kn:.1f}kN" for n, kn, _s in rules["end_post_options"])
                                 + "）でも足りません。梁枠を短くするか積載を下げてください"
                                 if rules.get("end_post_options") else f"両端{vm}の2本組等の補強が必要です"))
            warnings.append(
                f"{where}: 両端{vm}の軸力{end_post:.2f}kN（通常{post.dead_load_kn + post.live_load_kn:.2f}"
                f"＋反力{reaction:.2f}）が許容{end_allow:.2f}kNを超えます。{fix}"
            )
        else:
            notes.append(
                f"{where}: 両端{vm}の軸力{end_post:.2f}kN（反力{reaction:.2f}kN込み）≦ 許容{end_allow:.2f}kN"
            )
    return out, warnings, notes


def _post_item(caps: dict, model: ScaffoldModel, widened: bool) -> tuple[str, str]:
    """支柱許容圧縮耐力の行名と、拡幅部の行が無いときの注意.

    張出・拡幅ブラケットを付けた区間の支柱は、日建NDでは許容支持力が下がる
    （ND1800 通常11.0→拡幅部8.8kN/本、強力つなぎ材でも17.0→12.5）。区間があるのに
    通常値で検定すると危険側。拡幅部の行が無い系列は通常値で検定し、その旨を返す。
    """
    item = "支柱許容圧縮耐力"
    if not widened:
        return _width_item(caps, item, model), ""
    reinf = getattr(model.config, "post_reinforcement", "") or ""
    present = {i for (i, _k) in caps}
    tries = []
    if reinf:
        tries.append(f"{item}[拡幅部][{reinf}]")
    tries.append(f"{item}[拡幅部]")
    for t in tries:
        if t in present:
            if reinf and f"[{reinf}]" not in t:
                raise CapacityError(
                    f"系列 {model.master.series_id} には拡幅部で「{reinf}」使用時の支柱許容圧縮耐力が"
                    " capacity.csv にありません（post_reinforcement を外すか、認定値を追加してください）"
                )
            return t, ""
    return _width_item(caps, item, model), (
        f"張出ブラケットの区間がありますが、系列 {model.master.series_id} には拡幅部の"
        "支柱許容圧縮耐力が capacity.csv に無いため通常値で検定しています。"
        "拡幅部は許容支持力が下がる系列があります（日建ND: 11.0→8.8kN/本）。メーカー値を確認してください"
    )


def _width_item(caps: dict, item: str, model: ScaffoldModel) -> str:
    """建地列の間隔（枠組は建枠幅）で許容値が違う系列は、幅付きの行を使う.

    例: 610枠なら「ジャッキ許容支持力[幅610]」。くさびでも日建NDは
    W914・W610 で支柱の許容支持力が1.0kN大きい（幅の広い方が基準値）。
    幅付きの行が無い場合は元の項目名のまま（標準枠／基準幅の値）。
    """
    width = f"[幅{model.post_row_spacing_mm}]"
    reinf = getattr(model.config, "post_reinforcement", "") or ""
    tries = []
    if reinf and item == "支柱許容圧縮耐力":
        tries += [f"{item}{width}[{reinf}]", f"{item}[{reinf}]"]
    tries += [f"{item}{width}", item]
    present = {i for (i, _k) in caps}
    for t in tries:
        if t in present:
            if reinf and item == "支柱許容圧縮耐力" and f"[{reinf}]" not in t:
                # 補強を指定したのに値が無い系列。通常値で黙って通すと、補強を
                # 前提にした計画が通常仕様の耐力で成立したように見える
                raise CapacityError(
                    f"系列 {model.master.series_id} には「{reinf}」使用時の支柱許容圧縮耐力が"
                    f" capacity.csv にありません（post_reinforcement を外すか、認定値を追加してください）"
                )
            return t
    return item


def _interpolate_capacity(
    caps: dict, item: str, key_mm: int
) -> tuple[CapacityValue, str]:
    """繰出し長に対する許容支持力を線形補間（安全側に切り下げ）."""
    rows = sorted(
        ((int(k), v) for (i, k), v in caps.items() if i == item),
        key=lambda kv: kv[0],
    )
    if not rows:
        raise CapacityError(f"{item} が capacity.csv にありません")
    if key_mm <= rows[0][0]:
        return rows[0][1], str(rows[0][0])
    if key_mm >= rows[-1][0]:
        return rows[-1][1], str(rows[-1][0])
    for x, v in rows:
        if x == key_mm:
            return v, str(x)
    for (x0, v0), (x1, v1) in zip(rows, rows[1:]):
        if x0 <= key_mm <= x1:
            t = (key_mm - x0) / (x1 - x0)
            val = v0.value + t * (v1.value - v0.value)
            return (
                CapacityValue(
                    value=round(val, 3),
                    unit=v0.unit,
                    verified=v0.verified and v1.verified,
                    source=f"{v0.source}（{x0}〜{x1}mmを線形補間）",
                    series_id=v0.series_id,
                    item=item,
                    # 補間値は2行から作られる。片方だけ直しても未確認は消えない
                    keys=tuple(
                        k for v in (v0, v1) for k in v.keys if not v.verified
                    ) or (str(x0), str(x1)),
                ),
                f"{x0}-{x1}",
            )
    raise CapacityError(f"{item} の補間に失敗しました: {key_mm}")


@dataclass
class TieOptimizeResult:
    span_step: int
    level_step: int
    tie_count: int
    wall_tie: WallTieResult
    tightened: bool          # 既定配置から詰めたか
    feasible: bool           # 最密でも耐力を満たせない場合 False
    message: str
    # 開口部で抜いた支柱から両端へ寄せた壁つなぎの説明（openings を渡したとき）
    notes: list = field(default_factory=list)
    near_corner: bool = False    # 角から1.8m未満の支柱にも入れたか


def optimize_wall_ties(
    model: ScaffoldModel,
    site: Optional[SiteCondition] = None,
    capacity_path: Optional[Path] = None,
    apply: bool = True,
    openings=None,
    platforms=None,
    height_mm: Optional[float] = None,
) -> TieOptimizeResult:
    """壁つなぎ間隔を構造計算から逆算して決める.

    height_mm: 風の高さ補正に使う足場高さ（敷地の低い側で伸びた実高さ。run_structural と同じ高さで選ぶ。名目の高さで
    選ぶと、高低差 2m の敷地で後の検定が 1.02〜1.07 で落ちた。2026-10-26 のループ）。

    法規上限（垂直5m×水平5.5m）を満たしていても風荷重で耐力不足になることがあるため、
    「法規に適合し、かつ P ≦ 許容耐力×1.3 を満たす最も緩い配置」を探索する。
    緩い順（部材数が少ない順）に試し、最初に成立した構成を採用する。

    apply=True のとき model.wall_ties を最適解で置き換える（数量・図面に反映される）。
    openings を渡すと、開口部で抜いた支柱に当たる壁つなぎを両端へ寄せた状態で検定する
    （寄せると支配面積が偏るので、寄せた後で成立する間隔を選ぶ。寄せる前に選んだ間隔では
    opening_beam サンプルが寄せた後に検定比1.10で落ちた）。
    """
    from .model import generate_wall_ties  # 循環インポート回避のため関数内で解決
    from .ties import merge_attachment_ties, relocate_ties_off_openings, relocate_unreachable_ties

    def layout() -> list[str]:
        """候補の格子に、開口部の寄せと取付部（朝顔・ステージ）の壁つなぎを載せる.

        検定は最終的な一覧で行う。格子だけで検定して後から取付部を足すと、
        取付部の壁つなぎが格子の粗い所（コーナー寄り）の風荷重を受け持つ形になり、
        「壁つなぎを足したのに検定が悪化」して総合判定で落ちた（L形サンプル）。
        """
        notes = relocate_ties_off_openings(model, openings)
        merge_attachment_ties(model, platforms, openings)
        notes += relocate_ties_off_openings(model, openings)
        # 渡した区間の深い所（最長品でも届かない）の壁つなぎは、届く支柱へ寄せる
        notes += relocate_unreachable_ties(model)
        # 格子と取付部で同じ寄せ方の注意が2回出る（同じ文）。1つにまとめる
        return list(dict.fromkeys(notes))

    site = site or SiteCondition(period_days=model.config.period_days)
    caps = load_capacities(model.master.series_id, capacity_path)
    wind = compute_wind(model, site, height_mm=height_mm) if height_mm else compute_wind(model, site)

    original = list(model.wall_ties)
    base_span, base_level = (
        model.config.wall_tie_span_step,
        model.config.wall_tie_level_step,
    )
    # 部材数が少ない（緩い）順に試す。最後に、最密のまま角の手前の支柱にも入れる案
    candidates = sorted(
        [(s, lv) for s in (3, 2, 1) for lv in (2, 1)],
        key=lambda c: (-(c[0] * c[1]), -c[0]),
    )
    base_near = model.config.wall_tie_near_corner

    best: Optional[TieOptimizeResult] = None
    tightest: Optional[TieOptimizeResult] = None
    try:
        for span_step, level_step, near in [(s, lv, base_near) for s, lv in candidates] + (
                [] if base_near else [(1, 1, True)]):
            model.config.wall_tie_span_step = span_step
            model.config.wall_tie_level_step = level_step
            model.config.wall_tie_near_corner = near
            ties = generate_wall_ties(model.plan, model.elevation, model.config)
            model.wall_ties = ties
            model.clip_ties_to_faces()
            layout()
            res = check_wall_tie(model, wind, caps)
            cand = TieOptimizeResult(
                span_step=span_step,
                level_step=level_step,
                tie_count=len(model.wall_ties),
                wall_tie=res,
                tightened=(span_step, level_step) != (base_span, base_level),
                feasible=res.ok,
                message="",
            )
            cand.near_corner = near
            if tightest is None or cand.tie_count > tightest.tie_count:
                tightest = cand
            # 法規上限は「間隔」の制限。支配面積とは別物なので実間隔で見る。
            # 上限は足場の種類で違う（枠組は垂直9m×水平8m）ので model から引く
            v_lim, h_lim, _ = model.wall_tie_limits()
            v_max, h_max = model.wall_tie_max_spacing()
            if res.ok and v_max <= v_lim and h_max <= h_lim:
                best = cand
                break
    except Exception:
        model.wall_ties = original
        model.config.wall_tie_span_step = base_span
        model.config.wall_tie_level_step = base_level
        model.config.wall_tie_near_corner = base_near
        raise

    chosen = best or tightest
    assert chosen is not None, "壁つなぎ候補の評価に失敗しました"
    if best is None:
        chosen.feasible = False
        chosen.message = (
            f"壁つなぎを最密（{chosen.span_step}スパン毎×{chosen.level_step}層毎）にしても"
            f"検定比{chosen.wall_tie.ratio:.2f}で耐力を満たせません。"
            "高耐力の壁つなぎ、養生材の変更（メッシュ→なし等）、"
            "または壁つなぎ以外の補強を検討してください"
        )
    elif chosen.tightened or chosen.near_corner != base_near:
        chosen.message = (
            f"風荷重の検定を満たすため壁つなぎを "
            f"{base_span}スパン×{base_level}層毎 → "
            f"{chosen.span_step}スパン×{chosen.level_step}層毎"
            + ("（角から1.8m未満の支柱にも入れる）" if chosen.near_corner and not base_near else "")
            + f" に詰めました（{chosen.tie_count}箇所、検定比{chosen.wall_tie.ratio:.2f}）"
        )
    else:
        chosen.message = (
            f"既定配置で耐力を満たします"
            f"（{chosen.tie_count}箇所、検定比{chosen.wall_tie.ratio:.2f}）"
        )

    if apply:
        model.config.wall_tie_span_step = chosen.span_step
        model.config.wall_tie_level_step = chosen.level_step
        model.config.wall_tie_near_corner = chosen.near_corner
        model.wall_ties = generate_wall_ties(
            model.plan, model.elevation, model.config
        )
        model.clip_ties_to_faces()
        chosen.notes = layout()
    else:
        model.wall_ties = original
        model.config.wall_tie_span_step = base_span
        model.config.wall_tie_level_step = base_level
        model.config.wall_tie_near_corner = base_near
    return chosen


def run_structural(
    model: ScaffoldModel,
    quantity: QuantityResult,
    site: Optional[SiteCondition] = None,
    capacity_path: Optional[Path] = None,
    platforms=None,
    terrain=None,
    bracket_sections=None,
    openings=None,
) -> StructuralResult:
    site = site or SiteCondition(period_days=model.config.period_days)
    caps = load_capacities(model.master.series_id, capacity_path)

    wind = compute_wind(model, site, height_mm=actual_max_height_mm(model, terrain)[0])
    tie = check_wall_tie(model, wind, caps)

    # 荷受けステージがあれば、その直下の建地（最も厳しい1本）で検定する
    extra = platforms.max_post_load_kn if platforms else 0.0
    source = (
        f"荷受けステージ {platforms.governing}"
        if platforms and platforms.governing else ""
    )
    # 傾斜地では支柱ごとにジャッキ繰出し量が違う。許容支持力は繰出し長で
    # 落ちるので、最も繰り出している1本で検定する
    max_jack = None
    governing_foot = None
    if terrain is not None and getattr(terrain, "feet", None):
        worst = max(terrain.all_feet, key=lambda f: f.jack_mm)
        max_jack = int(round(worst.jack_mm))
        if max_jack > model.elevation.jack_extension:
            governing_foot = worst
    # 張出ブラケットの区間、または隅の拡幅・跳ね出しの端の張出ブラケット（hane_bridges）があれば、支柱は拡幅部の値で
    widened = (any(getattr(b, "direction", "") == "張出" for b in (bracket_sections or []))
               or widened_by_bridges(model))
    post = check_post(model, quantity, site, caps, extra, source, max_jack, widened=widened,
                      removed_posts=(openings.removed_posts if openings is not None else 0))
    if platforms is not None and platforms.max_inner_uplift_kn > 0:
        post.inner_uplift_kn = round(platforms.max_inner_uplift_kn, 3)
        post.uplift_source = platforms.uplift_governing or ""

    warnings: list[str] = []
    # 壁つなぎが届かない帯（渡した区間の深い所）は検定の外。面積を出して別途の控えを求める
    from .ties import unreachable_bands
    _bands = unreachable_bands(model)
    if _bands:
        _top = float(model.scaffold_height_mm)
        _txt = "・".join(
            f"{model.face_name(e)} {a:.0f}〜{b:.0f}mm（{(b - a) * _top / 1e6:.1f}m²）"
            for e, bs in sorted(_bands.items()) for a, b in bs
        )
        warnings.append(
            f"渡した区間の深い所は最長の壁つなぎでも躯体に届かず、壁つなぎの検定から除いています: {_txt}。"
            "この帯の風荷重は単管等で躯体まで控えを取って受けてください（控えの設計は本ツールの対象外）"
        )
    notes: list[str] = []
    if post.widened_note:
        warnings.append(post.widened_note)
    opening_checks, op_warn, op_notes = check_openings(model, openings, post, caps)
    warnings += op_warn
    notes += op_notes
    if post.inner_uplift_kn > 0:
        vm = model.master.vertical_member_name
        if post.uplift_ok:
            notes.append(
                f"荷受けステージの偏心による内側{vm}の引抜き{post.inner_uplift_kn}kN"
                f"（{post.uplift_source}）は自重{post.dead_load_kn}kNで抑えられます"
            )
        else:
            warnings.append(
                f"荷受けステージの偏心で内側{vm}に引抜き{post.inner_uplift_kn}kNが生じ、"
                f"自重{post.dead_load_kn}kNを超えます（{post.uplift_source}）。この値は方杖の効果を"
                "見込まないてこモデルの安全側の値です。方杖の効きを含めた検討と、内側建地の浮き止め"
                "（根がらみへの緊結・壁つなぎの増設）または出の縮小・積載の低減の要否を、有資格者が"
                "確認してください"
            )
    unverified_caps: list[UnverifiedCapacity] = []
    if governing_foot is not None:
        vm = model.master.vertical_member_name
        notes.append(
            f"敷地高低差により最大繰出し{post.jack_extension_mm}mmの{vm}"
            f"（{vm}{governing_foot.index}）で建地を検定しています"
            f"（平坦時の{model.elevation.jack_extension}mmではなく）。"
            "ジャッキ許容支持力は繰出し長で低下します"
        )
    # 建地2本組は単管足場（571条）の話。枠組は対象外なのでこの注記は出さない
    if model.scaffold_height_mm > 31000 and not model.master.is_frame:
        # 2本組にすれば許容は増えるが、そう組むかは計画者の判断。
        # どちらで検定したのかを書かないと検定比の意味が変わる
        notes.append(
            f"足場高さ{model.scaffold_height_mm / 1000:.2f}mですが、建地の検定は"
            "1本組で行っています（安衛則571条の2本組にすれば許容支持力は増えます）"
        )
    unverified_caps.extend(tie.unverified_caps)
    unverified_caps.extend(post.unverified_caps)
    # 同じCSV行が複数の検定に効いていることがある（引張/圧縮など）。
    # 差し替える側は行が知りたいので、行単位でまとめて挙げる
    by_row: dict[tuple[str, ...], UnverifiedCapacity] = {}
    used_for: dict[tuple[str, ...], list[str]] = {}
    for c in unverified_caps:
        by_row.setdefault(c.keys, c)
        used_for.setdefault(c.keys, []).append(c.label)
    unverified = [c.label for c in unverified_caps]
    if unverified_caps:
        series = unverified_caps[0].series_id
        lines = []
        for k, labels in used_for.items():
            c = by_row[k]
            line = f"{c.item}(key={'・'.join(k)}) {c.value}{c.unit}"
            # 項目名だけで用途が分かる行に用途を書き足しても読みにくいだけ
            extra = [t for t in labels if not t.startswith(c.item)]
            if extra:
                line += f"＝{'／'.join(dict.fromkeys(extra))}"
            lines.append(line)
        warnings.append(
            f"未確認の耐力値が計算に使われています。data/capacity.csv の系列 {series} の"
            "次の行を、メーカー認定値・仮設工業会認定値に差し替えて verified=yes に"
            "してから提出図書に使用してください: " + "、".join(lines)
        )
    if tie.top_ratio > 1.0:
        warnings.append(
            f"上端の壁つなぎが耐力不足です（{tie.top_where}: 反力{tie.top_kn:.2f}kN ＞ 許容{tie.allowable_increased_kn:.2f}kN、"
            f"検定比{tie.top_ratio:.2f}）。最上段の壁つなぎの水平間隔を詰めるか、天端までのはね出しを短くしてください"
            "（手引 p130・計算例「壁つなぎ上部2層部分の検討」）")
    if not tie.ok and tie.ratio > 1.0:
        if not model.wall_ties:
            # 0本だと支配面積が定まらず検定比が発散する。数字を出す場面ではない
            warnings.append(
                "壁つなぎが1本もないため風荷重を検定できません。"
                "作業層が取れない高さになっていないか、外形と軒高を確認してください"
            )
        else:
            warnings.append(
                f"壁つなぎが耐力不足です（検定比{tie.ratio:.2f}）。" + tie_remedy(tie)
            )
    # 壁つなぎ0本の面の風荷重は、この検定では誰も負担していない。
    # 両隣の面へコーナー経由で伝わる前提になるので、そうと書いておく
    untied = model.edges_without_wall_ties()
    if untied:
        warnings.append(
            "壁つなぎが1本も入らない面があります（"
            + "、".join(model.face_name(i) for i in untied)
            + "）。この面の風荷重は本検定に含まれておらず、両隣の面の壁つなぎに"
            "コーナー経由で伝わる前提です。単管等での別途拘束を検討してください"
        )
    if not post.ok:
        remedy = "ジャッキ繰出し量の低減、支柱2本組、またはスパン短縮を検討してください"
        if post.extra_load_kn > 0:
            remedy = (
                "荷受けステージ直下の建地が支配的です。積載荷重の低減、間口の拡大"
                "（支持する建地を増やす）、または支柱2本組を検討してください"
            )
        if not post.verified:
            # 一般値（単管建地6.86kN等）で不足しただけなら、部材を変える前に
            # メーカーの認定値を入れて判定し直すのが先。認定値は一般値より大きい
            remedy = (
                "許容支持力が未確認の一般値です。まずメーカー認定値を capacity.csv に"
                "入れて再判定してください。認定値でも不足なら、" + remedy
            )
        warnings.append(
            f"建地圧縮が耐力不足です（検定比{post.ratio:.2f}、支配: {post.governing}）。"
            + remedy
        )
    # 建地の座屈止めとしての壁つなぎ（手引 p130）: 1スパンの鉛直荷重（内外の建地2本）の5%を、壁つなぎ1本が受け持つ
    # スパン数ぶん受ける。風の検定とは別に、許容×1.3 と比べる
    spans = [s_ for e in model.plan.edges for s_ in e.spans]
    span_m = (max(set(spans), key=spans.count) if spans else 1800) / 1000.0
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    tie.buckle_spans = round(max(1.0, tie.lh_m / span_m), 2)
    tie.buckle_kn = round(post.total_kn * rows * BUCKLE_RATIO * tie.buckle_spans, 3)
    if tie.buckle_ratio > 1.0:
        tie.ok = False
        warnings.append(
            f"壁つなぎが建地の座屈止めとして耐力不足です（水平荷重{tie.buckle_kn:.2f}kN＝1スパンの鉛直荷重×5%×"
            f"{tie.buckle_spans:g}スパン ＞ 許容{tie.allowable_increased_kn:.2f}kN、検定比{tie.buckle_ratio:.2f}）。"
            "壁つなぎの水平間隔を詰めるか、高耐力の壁つなぎにしてください（計画届作成の手引 p130）")
    ground = check_ground_bearing(model, post, site)
    if not ground.ok:
        warnings.append(
            f"敷板の下の地盤が支持力不足です（接地圧{ground.board_kn_m2:.0f}kN/m²＞許容{ground.qa_kn_m2:.0f}kN/m²、"
            f"検定比{ground.board_ratio:.2f}。{ground.qa_source}）。敷角で受ける幅を広げる、地盤を改良する、"
            "または土間コンクリートで受けてください")
    else:
        notes.append(
            f"脚部の地盤支持力: ベースジャッキの底板（{ground.plate_mm:.0f}角）直下は{ground.plate_kn_m2:.0f}kN/m²で"
            f"許容{ground.qa_kn_m2:.0f}kN/m²を" + ("超えるので" if ground.plate_ratio > 1 else "下回るが")
            + f"、敷板（幅{ground.board_w_m * 1000:.0f}）を建地の列に沿って通して受ける（{ground.board_kn_m2:.0f}kN/m²、"
            f"検定比{ground.board_ratio:.2f}）")
    if site.ground_bearing_kn_m2 is None:
        notes.append("地盤の許容支持力度は計画届作成の手引の例（密実砂 29N/cm²）で検定しています。地盤調査の値を "
                     "site.ground_bearing_kn_m2（kN/m²）に入れて検定し直してください")
    brackets, b_notes = check_widen_brackets(model, caps, site)
    notes += b_notes
    if widened_by_bridges(model) and post.widened and not post.widened_note:
        notes.append("拡幅ブラケット・張出ブラケットで足場を広げた（隅の升目の拡幅・跳ね出しの上段の端・途中の床からの拡幅／縮幅）ので、"
                     f"{model.master.vertical_member_name}は拡幅部の許容支持力で検定しています")
    for b in brackets:
        if not b.ok:
            warnings.append(f"ブラケットが耐力不足です: {b.describe()}。ブラケットの出を小さくする、強力型（日建 NDBK03HS・"
                            "06HS）にする、または積載を下げてください")
    return StructuralResult(
        site=site, wind=wind, wall_tie=tie, post=post,
        warnings=warnings, notes=notes, unverified_used=unverified,
        unverified_rows=list(by_row.values()),
        openings=opening_checks, brackets=brackets, ground=ground,
    )
