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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .terrain import actual_max_height_mm
from .model import ScaffoldModel
from .quantity import QuantityResult

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 風力係数の定数（仮設工業会 風荷重指針）
CO_BASE = 1.57          # 基本風力係数
WIND_INCREASE = 1.3     # 風荷重時の部材許容耐力の割増（30%）
AIR_Q_COEF = 0.6        # 速度圧 q = 0.6 V^2 [N/m2]

# 養生材の充実率 R
SHEET_FILL_RATIO = {
    "なし": 0.0,
    "メッシュシート": 0.7,
    "防音シート": 1.0,
    "密閉シート": 1.0,
}

# 地表面粗度区分ごとの高さ補正係数 K の算定用（Zb, ZG, α）
# 建築基準法告示1454号 Er の考え方に準拠した簡易実装
ROUGHNESS = {
    "I": (5.0, 250.0, 0.10),
    "II": (5.0, 350.0, 0.15),
    "III": (5.0, 450.0, 0.20),
    "IV": (10.0, 550.0, 0.27),
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

    region: str = "関東(内陸)"          # 建設地（地域区分）
    v0_ms: Optional[float] = None       # 基準風速。Noneならregionから引く
    roughness: str = "III"              # 地表面粗度区分
    sheet_type: str = "メッシュシート"   # 養生材仕様
    adjacent_factor: float = 1.0        # 近接建物による補正 E（1.0〜1.3）
    region_factor: float = 1.0          # 地域区分係数 S
    gamma: float = 0.0                  # 風力係数式のγ（躯体側の充実率パラメータ）
    correction_f: float = 1.0           # 風力係数の補正係数 F
    period_days: int = 90               # 設置期間
    simultaneous_loaded_levels: int = 2  # 同時に積載する作業層数（実務: 2層以内）

    def base_wind_speed(self) -> tuple[float, str]:
        if self.v0_ms is not None:
            return self.v0_ms, "利用者指定値"
        regions = load_wind_regions()
        if self.region not in regions:
            raise CapacityError(
                f"未知の地域区分です: {self.region}（候補: {', '.join(regions)}）"
            )
        return regions[self.region]

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
    k_height: float
    e_adjacent: float
    s_region: float
    v_design_ms: float
    q_n_m2: float
    fill_ratio: float
    c_force: float


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

    @property
    def uplift_ok(self) -> bool:
        return self.inner_uplift_kn <= self.dead_load_kn + 1e-9

    @property
    def unverified_items(self) -> list[str]:
        return [c.label for c in self.unverified_caps]


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

    @property
    def all_ok(self) -> bool:
        return self.wall_tie.ok and self.post.ok


# ---- 計算本体 -------------------------------------------------------------


def height_factor(height_m: float, roughness: str = "III") -> float:
    """高さ補正係数 K（告示1454号 Er に準拠した簡易式）."""
    if roughness not in ROUGHNESS:
        raise CapacityError(f"未知の地表面粗度区分です: {roughness}")
    zb, zg, alpha = ROUGHNESS[roughness]
    h = max(height_m, 1.0)
    if h <= zb:
        return 1.7 * (zb / zg) ** alpha
    return 1.7 * (h / zg) ** alpha


def wind_force_coefficient(fill_ratio: float, gamma: float = 0.0, f: float = 1.0) -> float:
    """風力係数 C = (0.11 + 0.09γ + 0.945×Co×R) × F."""
    return (0.11 + 0.09 * gamma + 0.945 * CO_BASE * fill_ratio) * f


def compute_wind(model: ScaffoldModel, site: SiteCondition, height_mm: Optional[float] = None) -> WindResult:
    v0, v0_src = site.base_wind_speed()
    # 高さ補正は最も高い部分で見る。敷地の低い側で継ぎ足した分は名目より高い
    h_m = (height_mm if height_mm else model.scaffold_height_mm) / 1000.0
    k = height_factor(h_m, site.roughness)
    v = v0 * k * site.adjacent_factor * site.region_factor
    q = AIR_Q_COEF * v**2
    r = site.fill_ratio()
    c = wind_force_coefficient(r, site.gamma, site.correction_f)
    return WindResult(
        v0_ms=v0,
        v0_source=v0_src,
        height_m=round(h_m, 3),
        k_height=round(k, 4),
        e_adjacent=site.adjacent_factor,
        s_region=site.region_factor,
        v_design_ms=round(v, 3),
        q_n_m2=round(q, 1),
        fill_ratio=r,
        c_force=round(c, 4),
    )


@dataclass
class TieTributary:
    """壁つなぎ1本が受け持つ支配面積."""

    edge_index: int
    position_mm: float
    height_mm: int
    lh_m: float          # 水平方向の支配幅
    lw_m: float          # 垂直方向の支配高さ

    @property
    def area_m2(self) -> float:
        return self.lh_m * self.lw_m


def tie_tributaries(model: ScaffoldModel) -> list[TieTributary]:
    """壁つなぎごとの支配面積を求める（Phase 4）.

    各壁つなぎは「隣の壁つなぎとの中間まで」の風荷重を受け持つ。境界の扱いは
    そこが構造的な支点かどうかで決まる:

    - 最下段の下側: 足場脚部（ジャッキ・根がらみ）は支点なので **半分**を負担
    - 最上段の上側: 自由端の張り出しなので **全長**を負担
    - 面の端（コーナー）: コーナー支柱は両面共有で直交面に支持される支点なので **半分**

    「最大垂直間隔×最大水平間隔」で一律に評価すると、その2つが別々の壁つなぎで
    起きている場合に過大評価になり、逆に最下段のように片側が長い壁つなぎは
    過小評価になる。支配面積で見ると、どの1本が支配的かも分かる。

    ⚠️ 境界の支点扱いは工学的仮定。提出図書に使う際は有資格者の確認を受けること。
    """
    out: list[TieTributary] = []
    if not model.wall_ties:
        return out
    top = float(model.scaffold_height_mm)
    heights = sorted({t.height_mm for t in model.wall_ties})

    for edge in model.plan.edges:
        edge_ties = [t for t in model.wall_ties if t.edge_index == edge.edge_index]
        if not edge_ties:
            continue
        by_height: dict[int, list[float]] = {}
        for t in edge_ties:
            by_height.setdefault(t.height_mm, []).append(t.position_mm)
        for h in by_height:
            by_height[h].sort()

        for t in edge_ties:
            xs = by_height[t.height_mm]
            i = xs.index(t.position_mm)
            # 水平: 端はコーナー支柱（直交面に支持される支点）なので半分
            left = (t.position_mm - xs[i - 1]) / 2 if i > 0 else t.position_mm / 2
            right = (
                (xs[i + 1] - t.position_mm) / 2 if i < len(xs) - 1
                else (edge.scaffold_length - t.position_mm) / 2
            )

            # 垂直: 下端は脚部（支点）なので半分、上端は自由端なので全長
            j = heights.index(t.height_mm)
            below = (t.height_mm - heights[j - 1]) / 2 if j > 0 else t.height_mm / 2
            above = (
                (heights[j + 1] - t.height_mm) / 2 if j < len(heights) - 1
                else top - t.height_mm
            )

            out.append(TieTributary(
                edge_index=edge.edge_index,
                position_mm=t.position_mm,
                height_mm=t.height_mm,
                lh_m=(left + right) / 1000.0,
                lw_m=(below + above) / 1000.0,
            ))
    return out


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
            f"辺{worst.edge_index} 始点から{worst.position_mm:.0f}mm "
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
    return WallTieResult(
        lh_m=round(lh, 3),
        lw_m=round(lw, 3),
        tributary_area_m2=round(area, 3),
        force_kn=round(p_kn, 3),
        allowable_kn=cap,
        allowable_increased_kn=round(allow_inc, 3),
        ratio=round(ratio, 3),
        ok=ratio <= 1.0,
        source=cap_t.source,
        verified=verified,
        governing=governing,
        unverified_caps=unverified_caps,
    )


def check_post(
    model: ScaffoldModel,
    quantity: QuantityResult,
    site: SiteCondition,
    caps: dict,
    extra_post_load_kn: float = 0.0,
    extra_load_source: str = "",
    jack_extension_mm: Optional[int] = None,
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
    n_posts = model.plan.total_posts * (1 if single_row else 2)
    dead_kn = (quantity.total_weight_kg * 9.80665 / 1000.0) / max(n_posts, 1)

    deck_item = _width_item(caps, "作業床許容積載荷重", model)
    cap_deck = caps.get((deck_item, "スパン"))
    if cap_deck is None:
        raise CapacityError("作業床許容積載荷重が capacity.csv にありません")
    # 1構面(スパン)の積載を両端2本の建地で分担。同時載荷は所定層数まで
    live_kn = cap_deck.value * site.simultaneous_loaded_levels / 2.0
    total = dead_kn + live_kn + extra_post_load_kn

    jack = max(model.elevation.jack_extension, jack_extension_mm or 0)
    cap_jack, jack_key = _interpolate_capacity(
        caps, _width_item(caps, "ジャッキ許容支持力", model), jack)
    cap_post = caps.get((_width_item(caps, "支柱許容圧縮耐力", model), "0"))
    candidates = [("ジャッキ(繰出し%dmm)" % jack, cap_jack)]
    if cap_post is not None:
        candidates.append(("支柱", cap_post))
    governing_name, governing_cap = min(candidates, key=lambda kv: kv[1].value)

    ratio = total / governing_cap.value if governing_cap.value else float("inf")
    cap_label = f"{governing_name}の許容支持力"
    if extra_post_load_kn > 0 and extra_load_source:
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
        total_kn=round(total, 3),
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
    )


def _width_item(caps: dict, item: str, model: ScaffoldModel) -> str:
    """枠組は建枠の幅で許容値が違う。幅付きの行があればその項目名を返す.

    例: 610枠なら「ジャッキ許容支持力[幅610]」。くさびや、幅付きの行が無い
    場合は元の項目名のまま（標準枠の値）。
    """
    if not model.master.is_frame:
        return item
    variant = f"{item}[幅{model.post_row_spacing_mm}]"
    if any(i == variant for (i, _k) in caps):
        return variant
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


def optimize_wall_ties(
    model: ScaffoldModel,
    site: Optional[SiteCondition] = None,
    capacity_path: Optional[Path] = None,
    apply: bool = True,
) -> TieOptimizeResult:
    """壁つなぎ間隔を構造計算から逆算して決める.

    法規上限（垂直5m×水平5.5m）を満たしていても風荷重で耐力不足になることがあるため、
    「法規に適合し、かつ P ≦ 許容耐力×1.3 を満たす最も緩い配置」を探索する。
    緩い順（部材数が少ない順）に試し、最初に成立した構成を採用する。

    apply=True のとき model.wall_ties を最適解で置き換える（数量・図面に反映される）。
    """
    from .model import generate_wall_ties  # 循環インポート回避のため関数内で解決

    site = site or SiteCondition(period_days=model.config.period_days)
    caps = load_capacities(model.master.series_id, capacity_path)
    wind = compute_wind(model, site)

    original = list(model.wall_ties)
    base_span, base_level = (
        model.config.wall_tie_span_step,
        model.config.wall_tie_level_step,
    )
    # 部材数が少ない（緩い）順に試す
    candidates = sorted(
        [(s, lv) for s in (3, 2, 1) for lv in (2, 1)],
        key=lambda c: (-(c[0] * c[1]), -c[0]),
    )

    best: Optional[TieOptimizeResult] = None
    tightest: Optional[TieOptimizeResult] = None
    try:
        for span_step, level_step in candidates:
            model.config.wall_tie_span_step = span_step
            model.config.wall_tie_level_step = level_step
            ties = generate_wall_ties(model.plan, model.elevation, model.config)
            model.wall_ties = ties
            res = check_wall_tie(model, wind, caps)
            cand = TieOptimizeResult(
                span_step=span_step,
                level_step=level_step,
                tie_count=len(ties),
                wall_tie=res,
                tightened=(span_step, level_step) != (base_span, base_level),
                feasible=res.ok,
                message="",
            )
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
    elif chosen.tightened:
        chosen.message = (
            f"風荷重の検定を満たすため壁つなぎを "
            f"{base_span}スパン×{base_level}層毎 → "
            f"{chosen.span_step}スパン×{chosen.level_step}層毎 に詰めました"
            f"（{chosen.tie_count}箇所、検定比{chosen.wall_tie.ratio:.2f}）"
        )
    else:
        chosen.message = (
            f"既定配置で耐力を満たします"
            f"（{chosen.tie_count}箇所、検定比{chosen.wall_tie.ratio:.2f}）"
        )

    if apply:
        model.config.wall_tie_span_step = chosen.span_step
        model.config.wall_tie_level_step = chosen.level_step
        model.wall_ties = generate_wall_ties(
            model.plan, model.elevation, model.config
        )
    else:
        model.wall_ties = original
        model.config.wall_tie_span_step = base_span
        model.config.wall_tie_level_step = base_level
    return chosen


def run_structural(
    model: ScaffoldModel,
    quantity: QuantityResult,
    site: Optional[SiteCondition] = None,
    capacity_path: Optional[Path] = None,
    platforms=None,
    terrain=None,
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
        worst = max(terrain.feet, key=lambda f: f.jack_mm)
        max_jack = int(round(worst.jack_mm))
        if max_jack > model.elevation.jack_extension:
            governing_foot = worst
    post = check_post(model, quantity, site, caps, extra, source, max_jack)
    if platforms is not None and platforms.max_inner_uplift_kn > 0:
        post.inner_uplift_kn = round(platforms.max_inner_uplift_kn, 3)
        post.uplift_source = platforms.uplift_governing or ""

    warnings: list[str] = []
    notes: list[str] = []
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
                f"自重{post.dead_load_kn}kNを超えます（{post.uplift_source}）。ジャッキベースが"
                "浮くので、方杖で外側建地へ流す構成にし、内側建地の浮き止め（根がらみへの緊結・"
                "壁つなぎの増設）か出の縮小・積載の低減を検討してください"
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
    if not tie.ok:
        if not model.wall_ties:
            # 0本だと支配面積が定まらず検定比が発散する。数字を出す場面ではない
            warnings.append(
                "壁つなぎが1本もないため風荷重を検定できません。"
                "作業層が取れない高さになっていないか、外形と軒高を確認してください"
            )
        else:
            warnings.append(
                f"壁つなぎが耐力不足です（検定比{tie.ratio:.2f}）。"
                "壁つなぎ間隔を詰める、または高耐力品への変更を検討してください"
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
    return StructuralResult(
        site=site, wind=wind, wall_tie=tie, post=post,
        warnings=warnings, notes=notes, unverified_used=unverified,
        unverified_rows=list(by_row.values()),
    )
