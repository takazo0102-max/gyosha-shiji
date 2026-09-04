"""荷受けステージ・昇降機（仕様8 Phase 3の残タスク）.

どちらも「足場に取り付く付帯設備」で、共通するのは
**局所的に大きな荷重・反力が入るので、その直下の建地と壁つなぎを個別に見る必要がある**こと。
全体平均の建地圧縮検定だけでは、ステージ直下の建地が抜ける。

荷受けステージ:
- 資材荷揚げ用の張出し床。積載荷重は通常の作業床の数倍（1t/箇所が実務の目安）
- 張出しなので偏心があり、直下の建地に割増した軸力が入る
- 手すり・幅木が必須で、最大積載荷重の表示義務がある（安衛則655条）

昇降機（工事用エレベータ・ホイスト）:
- マストを足場に控えるため、取付部の壁つなぎを増設する
- 昇降機自体の基礎・構造は本ツールの対象外（別途専門メーカーの計算による）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .model import ScaffoldModel

# 張出しの偏心による建地軸力の割増係数（工学的仮定。要有資格者確認）
CANTILEVER_AMPLIFICATION = 1.5
DEFAULT_STAGE_LOAD_KN = 9.8       # 1000kgf/箇所（実務の目安）
DEFAULT_STAGE_PROJECTION_MM = 1500
GRAVITY = 9.80665


@dataclass
class LoadingStage:
    """荷受けステージ1基."""

    edge_index: int
    start_mm: float                 # 辺の始点コーナー支柱からの距離
    span_count: int = 2             # 間口（スパン数）
    projection_mm: float = DEFAULT_STAGE_PROJECTION_MM   # 出（張出し長さ）
    load_kn: float = DEFAULT_STAGE_LOAD_KN               # 最大積載荷重
    levels: list[int] = field(default_factory=list)      # 設置する作業層（空=最下層）
    has_guard_rail: bool = True
    has_toe_board: bool = True
    has_load_sign: bool = True      # 最大積載荷重の表示
    has_hozue: bool = True          # 方杖
    note: str = ""

    def length_mm(self, model: ScaffoldModel) -> float:
        edge = _edge(model, self.edge_index)
        if edge is None:
            return 0.0
        acc = 0.0
        start_i = _span_index(edge, self.start_mm)
        for s in edge.spans[start_i:start_i + self.span_count]:
            acc += s
        return acc

    def end_mm(self, model: ScaffoldModel) -> float:
        """間口の終端。スパンは1800とは限らない（B系列・枠組・端数スパン）."""
        return self.start_mm + self.length_mm(model)

    def spans(self, model: ScaffoldModel) -> list[int]:
        """間口が占有するスパンの呼び寸法。面の端を越える分は含まれない."""
        edge = _edge(model, self.edge_index)
        if edge is None:
            return []
        i = _span_index(edge, self.start_mm)
        return list(edge.spans[i:i + self.span_count])


@dataclass
class Hoist:
    """昇降機（工事用エレベータ・ホイスト）1基."""

    edge_index: int
    position_mm: float              # 辺の始点コーナー支柱からの距離
    reach_height_mm: float = 0.0    # 到達高さ（0なら足場高さ）
    tie_every_mm: float = 3600      # マスト控えの壁つなぎ間隔
    # 乗り込み口を設ける作業層（空なら全層）。足場側の開口なので本ツールの範囲
    landing_levels: list[int] = field(default_factory=list)
    note: str = ""

    def landings(self, model: ScaffoldModel) -> list[int]:
        n = model.elevation.n_levels
        if self.landing_levels:
            return [lv for lv in self.landing_levels if 1 <= lv <= n]
        return list(range(1, n + 1))


@dataclass
class PlatformIssue:
    kind: str          # "ステージ" / "昇降機"
    index: int
    severity: str      # "NG" / "WARN"
    message: str
    basis: str


@dataclass
class PlatformResult:
    stages: list[LoadingStage] = field(default_factory=list)
    hoists: list[Hoist] = field(default_factory=list)
    issues: list[PlatformIssue] = field(default_factory=list)
    extra_wall_ties: int = 0
    max_post_load_kn: float = 0.0      # ステージ直下の建地1本あたり最大軸力
    governing: Optional[str] = None    # どのステージが支配的か
    # 偏心の裏の内側建地の引抜き（1本あたり）。自重と比べて浮きを判定する
    max_inner_uplift_kn: float = 0.0
    uplift_governing: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not [i for i in self.issues if i.severity == "NG"]


def _edge(model: ScaffoldModel, edge_index: int):
    for ep in model.plan.edges:
        if ep.edge_index == edge_index:
            return ep
    return None


def _span_index(edge, position_mm: float) -> int:
    acc = 0.0
    for i, s in enumerate(edge.spans):
        if position_mm < acc + s - 1e-6:
            return i
        acc += s
    return max(0, len(edge.spans) - 1)


def stage_post_load_kn(stage: LoadingStage, model: ScaffoldModel) -> float:
    """ステージ直下の建地1本あたりの追加軸力.

    張出しの偏心を割増係数で見込む（工学的仮定）。支持する建地は
    間口の両端＋中間の支柱（＝スパン数+1本）。
    """
    n_posts = stage.span_count + 1
    n_levels = max(1, len(stage.levels) or 1)
    return stage.load_kn * n_levels * cantilever_amplification(stage, model) / n_posts


def stage_inner_uplift_kn(stage: LoadingStage, model: ScaffoldModel) -> float:
    """ステージの偏心で内側建地1本に生じる引抜き力 P×a/b ÷ 建地数.

    外側建地の反力 P(1+a/b) の裏で、内側建地には P×a/b の引抜きが出る。
    自重で抑えられなければジャッキベースが浮く（方杖で外側へ流すか浮き止めが要る）。
    """
    b = float(model.post_row_spacing_mm or 0)
    if b <= 0:
        return 0.0
    n_posts = stage.span_count + 1
    n_levels = max(1, len(stage.levels) or 1)
    a = stage.projection_mm / 2.0
    return stage.load_kn * n_levels * (a / b) / n_posts


def cantilever_amplification(stage: LoadingStage, model: ScaffoldModel) -> float:
    """張出しの偏心による外側建地の割増係数 1 + a/b（下限 CANTILEVER_AMPLIFICATION）.

    荷重は張出し床の中央（外側建地から a = 出/2）に載るとみなす。内外の建地間隔 b で
    受ける片持ちの反力は外側建地で P(1 + a/b)、内側は引抜き。定数1.5だけだと
    出1500mm・建地間隔600mmの2.25倍を過小に見ていた（出を変えても軸力が動かなかった）。
    """
    b = float(model.post_row_spacing_mm or 0)
    if b <= 0:
        return CANTILEVER_AMPLIFICATION
    a = stage.projection_mm / 2.0
    return max(CANTILEVER_AMPLIFICATION, 1.0 + a / b)


def validate_platforms(
    model: ScaffoldModel,
    stages: Optional[list[LoadingStage]] = None,
    hoists: Optional[list[Hoist]] = None,
) -> PlatformResult:
    """荷受けステージ・昇降機の妥当性を検証し、追加壁つなぎと建地軸力を返す."""
    stages = stages or []
    hoists = hoists or []
    result = PlatformResult(stages=stages, hoists=hoists)
    n_levels = model.elevation.n_levels

    for i, s in enumerate(stages):
        edge = _edge(model, s.edge_index)
        basis = "安衛則563条・655条（作業床の手すり・幅木、最大積載荷重の表示）"
        if edge is None:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG", f"辺{s.edge_index}は存在しません", "入力エラー"))
            continue
        if s.start_mm < 0 or s.start_mm >= edge.scaffold_length:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                f"辺{s.edge_index}: 位置{s.start_mm:.0f}mmが面長"
                f"{edge.scaffold_length:.0f}mmの範囲外です", "入力エラー"))
        if s.span_count < 1:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG", "間口は1スパン以上必要です", "入力エラー"))
        if model.config.scaffold_form == "一側足場":
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                "一側足場（建地1列）には荷受けステージを取り付けられません。張出しの偏心を"
                "内外2列の建地で受ける前提なので、本足場で計画してください",
                "仮設工業会 足場・型枠支保工設計指針（荷受け構台は本足場に設置）"))
        if s.projection_mm <= 0:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                f"出{s.projection_mm:.0f}mmでは張出し床になりません（0より大きい値）",
                "入力エラー"))
        if s.load_kn <= 0:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                f"最大積載荷重{s.load_kn:.1f}kNは0より大きい値で指定してください"
                "（荷受けステージは積載が前提。0以下では検定にならない）",
                "入力エラー"))
        for lv in s.levels:
            if not (1 <= lv <= n_levels):
                result.issues.append(PlatformIssue(
                    "ステージ", i, "NG",
                    f"作業層{lv}は存在しません（1〜{n_levels}）", "入力エラー"))
        if not s.has_guard_rail:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG", "荷受けステージには手すりが必要です", basis))
        if not s.has_toe_board:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG", "荷受けステージには幅木が必要です", basis))
        if not s.has_load_sign:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                f"最大積載荷重（{s.load_kn:.1f}kN）の表示が必要です", basis))
        if not s.has_hozue:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                "張出し部には方杖が必要です（偏心荷重を建地へ伝えるため）",
                "仮設工業会 足場・型枠支保工設計指針"))
        if s.projection_mm > 1800:
            result.issues.append(PlatformIssue(
                "ステージ", i, "WARN",
                f"出{s.projection_mm:.0f}mmが大きく、偏心モーメントが増えます。"
                "支持方法を個別に検討してください",
                "仮設工業会 設計指針"))

        # 間口が面に収まるか。スライスで黙って短くなると、実際には
        # 取り付かない構成のまま軸力だけ計算してしまう
        got = s.spans(model)
        if len(got) < s.span_count:
            result.issues.append(PlatformIssue(
                "ステージ", i, "NG",
                f"辺{s.edge_index}: 位置{s.start_mm:.0f}mmから"
                f"{s.span_count}スパンは面（{edge.scaffold_length:.0f}mm・"
                f"{edge.span_count}スパン）に収まりません", "入力エラー"))

        uplift = stage_inner_uplift_kn(s, model)
        if uplift > result.max_inner_uplift_kn:
            result.max_inner_uplift_kn = uplift
            result.uplift_governing = (
                f"辺{s.edge_index} 始点から{s.start_mm:.0f}mm（出{s.projection_mm:.0f}mm）"
            )
        load = stage_post_load_kn(s, model)
        if load > result.max_post_load_kn:
            result.max_post_load_kn = load
            result.governing = (
                f"辺{s.edge_index} 始点から{s.start_mm:.0f}mm "
                f"（間口{s.span_count}スパン・出{s.projection_mm:.0f}mm・"
                f"積載{s.load_kn:.1f}kN）"
            )
        # ステージ取付部は壁つなぎを増設する（間口の両端）
        result.extra_wall_ties += 2 * max(1, len(s.levels) or 1)

    # 同じ区間に2基は取り付かない。重なりを黙って通すと部材も軸力も二重になる
    for i, a in enumerate(stages):
        for j, b in list(enumerate(stages))[i + 1:]:
            if a.edge_index != b.edge_index:
                continue
            if a.start_mm < b.end_mm(model) and b.start_mm < a.end_mm(model):
                result.issues.append(PlatformIssue(
                    "ステージ", j, "NG",
                    f"辺{a.edge_index}でステージ{i + 1}と{j + 1}の間口が重なっています"
                    f"（{a.start_mm:.0f}-{a.end_mm(model):.0f} と "
                    f"{b.start_mm:.0f}-{b.end_mm(model):.0f}）", "入力エラー"))

    for i, h in enumerate(hoists):
        edge = _edge(model, h.edge_index)
        if edge is None:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG", f"辺{h.edge_index}は存在しません", "入力エラー"))
            continue
        if h.position_mm < 0 or h.position_mm > edge.scaffold_length:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG",
                f"辺{h.edge_index}: 位置{h.position_mm:.0f}mmが面長の範囲外です",
                "入力エラー"))
        # landings() は範囲外の層を黙って読み飛ばす（層数が変わっても落ちないように）。
        # ここで指摘しないと「指定した層に乗り込み口が無い」まま数量・図面から
        # 静かに消える
        bad_levels = [lv for lv in h.landing_levels if not (1 <= lv <= n_levels)]
        if bad_levels:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG",
                f"乗り込み口の作業層{bad_levels}は存在しません（1〜{n_levels}）。"
                "指定した層の乗り込み口は計上されません", "入力エラー"))
        reach = h.reach_height_mm or model.scaffold_height_mm
        if reach > model.scaffold_height_mm:
            result.issues.append(PlatformIssue(
                "昇降機", i, "WARN",
                f"到達高さ{reach:.0f}mmが足場高さ{model.scaffold_height_mm}mmを超えます。"
                "マスト頂部の控えを別途検討してください",
                "工事用エレベータ構造規格"))
        if h.tie_every_mm <= 0:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG",
                f"マスト控えの間隔{h.tie_every_mm:.0f}mmは0より大きい値で指定してください"
                "（0だと控えが無限に必要になる）", "入力エラー"))
            continue
        # 同じ面の同じ位置（1スパン未満）に2基は建たない。黙って通すと控えと
        # 乗り込み口が二重に計上される
        for j, other in enumerate(hoists[:i]):
            if other.edge_index == h.edge_index and \
                    abs(other.position_mm - h.position_mm) < min(edge.spans or [1800]):
                result.issues.append(PlatformIssue(
                    "昇降機", i, "NG",
                    f"辺{h.edge_index}で昇降機{j + 1}と{i + 1}が同じ位置"
                    f"（{other.position_mm:.0f}mmと{h.position_mm:.0f}mm）に重なっています",
                    "入力エラー"))
        # マスト控えの壁つなぎ
        n_ties = max(1, int(reach // h.tie_every_mm))
        result.extra_wall_ties += n_ties
        result.issues.append(PlatformIssue(
            "昇降機", i, "WARN",
            f"昇降機本体の基礎・構造は本ツールの対象外です。"
            f"マスト控えの壁つなぎ{n_ties}箇所を計上しました",
            "メーカーの構造計算による"))

    return result


@dataclass
class PartDemand:
    """ステージが必要とする部材1件。数量拾いがマスタに引き当てるための指定."""

    label: str            # 数量表の分類名
    category: str         # マスタの分類
    nominal_dim: Optional[int]   # 呼び寸法。Noneなら分類内の唯一品
    qty: int
    note_contains: str = ""      # マスタ検索の絞り込み（例 "張出"）
    # 手配が要るときに添える補足（場所・条文）。検証側と数量側で
    # 同じ話を2行に分けないため、部材の説明はここに集約する
    detail: str = ""


def platform_part_demands(
    model: ScaffoldModel, result: PlatformResult
) -> list[PartDemand]:
    """ステージの必要部材。数量拾いと platform_quantities の唯一の出所.

    分類名だけ返して数量表に載せないと、ステージの部材（張出ブラケット・
    踏板・幅木・手すり）が発注リストから丸ごと抜ける。間口の呼び寸法は
    1800決め打ちにせず、実際のスパン構成から拾う。
    """
    out: list[PartDemand] = []
    for s in result.stages:
        n_levels = max(1, len(s.levels) or 1)
        n_posts = s.span_count + 1
        bracket = _bracket_nominal(model, s.projection_mm)
        out.append(PartDemand(
            "荷受けステージ 張出ブラケット", "ブラケット", bracket, n_posts * n_levels, "張出"
        ))
        if s.has_hozue:
            out.append(PartDemand("荷受けステージ 方杖", "方杖", None, n_posts * n_levels))
        spans = s.spans(model)
        # 張出し床は「出」を踏板で覆う。1スパンあたり1枚で数えると、
        # 出1500mmのステージに幅400の踏板1枚しか拾わないことになる
        deck_w = max(model.config.deck_widths or [400])
        per_span = math.ceil(s.projection_mm / deck_w) if deck_w else 0
        for nominal in set(spans):
            n = spans.count(nominal)
            deck_cat = model.master.deck_category
            out.append(PartDemand(
                "荷受けステージ " + deck_cat, deck_cat, nominal,
                n * n_levels * per_span, f"幅{deck_w}"
            ))
            if s.has_toe_board:
                out.append(PartDemand("荷受けステージ 幅木", "幅木", nominal, n * n_levels))
            if s.has_guard_rail:
                # 手すり＋中桟
                out.append(PartDemand("荷受けステージ 手すり・中桟", "布材", nominal, n * 2 * n_levels))
        # 妻側（張出しの左右）も開放端。前面だけ手すりを立てても横から落ちる
        side = _side_nominal(model, s.projection_mm)
        if side is not None:
            if s.has_guard_rail:
                out.append(PartDemand(
                    "荷受けステージ 妻側手すり・中桟", "布材", side, 2 * 2 * n_levels))
            if s.has_toe_board:
                out.append(PartDemand("荷受けステージ 妻側幅木", "幅木", side, 2 * n_levels))
    for h in result.hoists:
        landings = h.landings(model)
        if landings:
            out.append(PartDemand(
                "昇降機 乗り込み口の開閉式手すり", "開閉式手すり", None,
                len(landings),
                detail="作業層" + "・".join(str(lv) for lv in landings)
                       + "。乗り込み口は足場側の開口で、防護しないと"
                         "各層に開放端ができます（安衛則563条）",
            ))
    if result.extra_wall_ties > 0:
        out.append(PartDemand("付帯設備の増設壁つなぎ", "壁つなぎ", None, result.extra_wall_ties))
    return out


def _side_nominal(model: ScaffoldModel, projection_mm: float) -> Optional[int]:
    """張出しの妻側（左右）に渡す材の呼び寸法。出以上で最小のもの."""
    sizes = sorted(p.nominal_dim for p in model.master.by_category("布材"))
    for v in sizes:
        if v >= projection_mm - 1e-6:
            return v
    return None


def _bracket_nominal(model: ScaffoldModel, projection_mm: float) -> Optional[int]:
    """出を受けられる最小の張出ブラケット呼び寸法。無ければ None."""
    sizes = sorted(
        p.nominal_dim for p in model.master.by_category("ブラケット")
        if "張出" in p.note
    )
    for n in sizes:
        if n >= projection_mm - 1e-6:
            return n
    return None


def platform_quantities(
    model: ScaffoldModel, result: PlatformResult
) -> dict[str, int]:
    """荷受けステージの部材数（分類名→数量）の要約."""
    counts: dict[str, int] = {}
    for d in platform_part_demands(model, result):
        if d.qty > 0:
            counts[d.label] = counts.get(d.label, 0) + d.qty
    return counts
