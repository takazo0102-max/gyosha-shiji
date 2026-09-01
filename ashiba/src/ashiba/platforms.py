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

    @property
    def end_mm(self) -> float:
        return self.start_mm + self.span_count * 1800   # 概算（検証で厳密化）


@dataclass
class Hoist:
    """昇降機（工事用エレベータ・ホイスト）1基."""

    edge_index: int
    position_mm: float              # 辺の始点コーナー支柱からの距離
    reach_height_mm: float = 0.0    # 到達高さ（0なら足場高さ）
    tie_every_mm: float = 3600      # マスト控えの壁つなぎ間隔
    note: str = ""


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
    return stage.load_kn * n_levels * CANTILEVER_AMPLIFICATION / n_posts


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
        reach = h.reach_height_mm or model.scaffold_height_mm
        if reach > model.scaffold_height_mm:
            result.issues.append(PlatformIssue(
                "昇降機", i, "WARN",
                f"到達高さ{reach:.0f}mmが足場高さ{model.scaffold_height_mm}mmを超えます。"
                "マスト頂部の控えを別途検討してください",
                "工事用エレベータ構造規格"))
        # マスト控えの壁つなぎ
        n_ties = max(1, int(reach // max(h.tie_every_mm, 1)))
        result.extra_wall_ties += n_ties
        result.issues.append(PlatformIssue(
            "昇降機", i, "WARN",
            f"昇降機本体の基礎・構造は本ツールの対象外です。"
            f"マスト控えの壁つなぎ{n_ties}箇所を計上しました",
            "メーカーの構造計算による"))

    return result


def platform_quantities(
    model: ScaffoldModel, result: PlatformResult
) -> dict[str, int]:
    """荷受けステージの部材数（分類名→数量）.

    張出ブラケット・方杖・踏板・幅木・手すり用布材を、間口のスパン数から算出する。
    """
    counts: dict[str, int] = {}

    def add(key: str, n: int) -> None:
        if n > 0:
            counts[key] = counts.get(key, 0) + n

    for s in result.stages:
        n_levels = max(1, len(s.levels) or 1)
        n_posts = s.span_count + 1
        add("張出ブラケット", n_posts * n_levels)
        if s.has_hozue:
            add("方杖", n_posts * n_levels)
        add("踏板", s.span_count * n_levels)
        if s.has_toe_board:
            add("幅木", s.span_count * n_levels)
        if s.has_guard_rail:
            add("布材", s.span_count * 2 * n_levels)   # 手すり＋中桟
    add("壁つなぎ", result.extra_wall_ties)
    return counts
