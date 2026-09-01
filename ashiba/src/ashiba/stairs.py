"""階段（昇降設備）の自動配置.

安衛則526条: 高さ1.5mを超える箇所には昇降設備が必要。
実務指針: 作業場所から昇降設備までの水平移動距離は30m以内が目安。

配置ルール:
- 足場中心線ループ上に均等配置する（閉ループなので、n箇所なら最大移動距離は 周長/(2n)）
- 階段室は所定スパン数（A系列 1800×1800 なら2スパン=3600mm）を占有する
- コーナーから1スパン以上離す（コーナー支柱まわりは納まりが厳しい）
- 階段室の区間には踏板を敷かない → 数量から差し引く（二重計上の防止）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .model import ScaffoldModel

DEFAULT_MAX_TRAVEL_MM = 30000    # 昇降設備までの水平移動距離の目安
MIN_HEIGHT_FOR_STAIRS_MM = 1500  # 安衛則526条
LANDING_EVERY_LEVELS = 2         # 昇降階段は2層以下毎に踊り場を設ける


@dataclass
class StairTower:
    """階段室（1箇所）. 面の区間を占有する."""

    edge_index: int
    start_mm: float          # 辺の始点コーナー支柱からの距離
    span_count: int          # 占有スパン数
    length_mm: float         # 占有長さ
    loop_position_mm: float  # ループ全体での位置（移動距離の計算用）
    reason: str = ""
    manual: bool = False     # 利用者が位置を指定したものか

    @property
    def end_mm(self) -> float:
        return self.start_mm + self.length_mm


@dataclass
class StairPlan:
    towers: list[StairTower] = field(default_factory=list)
    max_travel_mm: float = 0.0     # 実配置での最大水平移動距離
    required_count: int = 0
    landings_per_tower: int = 0    # 1箇所あたりの踊り場数（2層以下毎）
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.towers)

    @property
    def total_landings(self) -> int:
        return self.count * self.landings_per_tower


def auto_place_stairs(
    model: ScaffoldModel,
    max_travel_mm: float = DEFAULT_MAX_TRAVEL_MM,
    tower_spans: int = 2,
    count: Optional[int] = None,
) -> StairPlan:
    """階段室をループ上に均等配置する.

    count を指定するとその箇所数で配置し、指定しなければ
    移動距離が max_travel_mm 以下になる最小箇所数を自動で決める。
    """
    plan = StairPlan()
    plan.landings_per_tower = landings_per_tower(model)
    if model.scaffold_height_mm <= MIN_HEIGHT_FOR_STAIRS_MM:
        plan.warnings.append(
            f"足場高さ{model.scaffold_height_mm}mm ≦ {MIN_HEIGHT_FOR_STAIRS_MM}mm のため"
            "昇降設備は不要です（安衛則526条）"
        )
        return plan

    loop_len = sum(ep.scaffold_length for ep in model.plan.edges)
    if loop_len <= 0:
        return plan

    # 閉ループにn箇所を均等配置すると最大移動距離は loop/(2n)
    need = max(1, math.ceil(loop_len / (2 * max_travel_mm)))
    plan.required_count = need
    n = count if count is not None else need

    targets = [loop_len * i / n for i in range(n)]
    for i, t in enumerate(targets):
        tower = _place_at(model, t, tower_spans)
        if tower is None:
            plan.warnings.append(
                f"階段{i + 1}箇所目を配置できる区間が見つかりません"
                f"（{tower_spans}スパン連続かつコーナーから1スパン以上離れた場所が必要）"
            )
            continue
        tower.reason = (
            f"昇降設備{n}箇所を均等配置（安衛則526条、水平移動{max_travel_mm / 1000:.0f}m以内）"
        )
        plan.towers.append(tower)

    # 最大移動距離は理想配置の式ではなく実配置から求める
    # （スロットへの丸めやコーナー回避で位置がずれるため）
    plan.max_travel_mm = actual_max_travel(plan.towers, loop_len)
    if plan.max_travel_mm > max_travel_mm:
        plan.warnings.append(
            f"階段{len(plan.towers)}箇所では最大水平移動距離が"
            f"{plan.max_travel_mm / 1000:.1f}mとなり"
            f"目安{max_travel_mm / 1000:.0f}mを超えます（{need + 1}箇所以上を検討）"
        )
    return plan


def landings_per_tower(model: ScaffoldModel, every_levels: int = LANDING_EVERY_LEVELS) -> int:
    """1箇所あたりの踊り場数（昇降階段は2層以下毎に踊り場を設ける）."""
    n = model.elevation.n_levels
    if n <= 0 or every_levels <= 0:
        return 0
    # 2層登るごとに踊り場。最上層に着いたところは作業床なので数えない
    return max(0, (n - 1) // every_levels)


def place_stairs_at(
    model: ScaffoldModel,
    positions: list[dict],
    tower_spans: int = 2,
    max_travel_mm: float = DEFAULT_MAX_TRAVEL_MM,
    landing_every_levels: int = LANDING_EVERY_LEVELS,
) -> StairPlan:
    """階段室の位置を指定して配置する.

    positions: [{"edge_index": 0, "start_mm": 3600, "span_count": 2}, ...]
    start_mm は辺の始点コーナー支柱からの距離。スパン境界に丸める
    （階段室は支柱間に納まる必要があるため）。

    自動配置と同じ検証（移動距離・重なり）を通すので、
    指定位置が実務指針を外れていれば警告が出る。
    """
    plan = StairPlan()
    plan.landings_per_tower = landings_per_tower(model, landing_every_levels)
    if model.scaffold_height_mm <= MIN_HEIGHT_FOR_STAIRS_MM:
        plan.warnings.append(
            f"足場高さ{model.scaffold_height_mm}mm ≦ {MIN_HEIGHT_FOR_STAIRS_MM}mm のため"
            "昇降設備は不要です（安衛則526条）"
        )
        return plan

    loop_len = sum(ep.scaffold_length for ep in model.plan.edges)
    plan.required_count = max(1, math.ceil(loop_len / (2 * max_travel_mm)))

    for i, pos in enumerate(positions):
        ei = pos.get("edge_index")
        edge = next((e for e in model.plan.edges if e.edge_index == ei), None)
        if edge is None:
            plan.warnings.append(f"階段{i + 1}: 辺{ei}は存在しません")
            continue
        spans_n = pos.get("span_count", tower_spans)
        snapped = _snap_to_span(edge, float(pos.get("start_mm", 0)), spans_n)
        if snapped is None:
            plan.warnings.append(
                f"階段{i + 1}: 辺{ei}に{spans_n}スパン連続の区間を確保できません"
                f"（面長{edge.scaffold_length:.0f}mm・{edge.span_count}スパン）"
            )
            continue
        start, length = snapped
        requested = float(pos.get("start_mm", 0))
        if abs(start - requested) > 1:
            plan.warnings.append(
                f"階段{i + 1}: 指定位置{requested:.0f}mmを"
                f"スパン境界の{start:.0f}mmに丸めました（支柱間に納めるため）"
            )
        acc = sum(
            e.scaffold_length for e in model.plan.edges if e.edge_index < ei
        )
        plan.towers.append(StairTower(
            edge_index=ei, start_mm=start, span_count=spans_n, length_mm=length,
            loop_position_mm=acc + start, manual=True,
            reason=pos.get("reason", "利用者が位置を指定"),
        ))

    plan.max_travel_mm = actual_max_travel(plan.towers, loop_len)
    if plan.towers and plan.max_travel_mm > max_travel_mm:
        plan.warnings.append(
            f"指定された{len(plan.towers)}箇所では最大水平移動距離が"
            f"{plan.max_travel_mm / 1000:.1f}mとなり"
            f"目安{max_travel_mm / 1000:.0f}mを超えます"
            f"（{plan.required_count}箇所以上を推奨）"
        )
    return plan


def _snap_to_span(edge, start_mm: float, tower_spans: int):
    """指定位置に最も近いスパン境界へ丸め、そこから tower_spans 分の区間を返す."""
    spans = edge.spans
    if len(spans) < tower_spans:
        return None
    starts = [0.0]
    for s in spans:
        starts.append(starts[-1] + s)
    candidates = [
        (starts[i], sum(spans[i:i + tower_spans]))
        for i in range(0, len(spans) - tower_spans + 1)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c[0] - start_mm))


def actual_max_travel(towers: list[StairTower], loop_len_mm: float) -> float:
    """実配置から最大水平移動距離を求める.

    閉ループ上の隣り合う階段の間隔の半分が、その区間での最大移動距離になる。
    """
    if not towers:
        return float("inf")
    pos = sorted(t.loop_position_mm for t in towers)
    if len(pos) == 1:
        return loop_len_mm / 2
    gaps = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
    gaps.append(loop_len_mm - pos[-1] + pos[0])   # 折り返しの区間
    return max(gaps) / 2


def _place_at(
    model: ScaffoldModel, loop_pos_mm: float, tower_spans: int
) -> Optional[StairTower]:
    """ループ上の位置に最も近い、配置可能な区間へ階段室を置く."""
    acc = 0.0
    for ep in model.plan.edges:
        edge_len = ep.scaffold_length
        if loop_pos_mm <= acc + edge_len or ep is model.plan.edges[-1]:
            local = max(0.0, min(loop_pos_mm - acc, edge_len))
            slot = _find_slot(ep, local, tower_spans)
            if slot is not None:
                start, length = slot
                return StairTower(
                    edge_index=ep.edge_index,
                    start_mm=start,
                    span_count=tower_spans,
                    length_mm=length,
                    loop_position_mm=acc + start,
                )
            # この辺に置けなければ次の辺を探す
        acc += edge_len
    # どこにも置けなければ、置ける辺を総当たり
    acc = 0.0
    for ep in model.plan.edges:
        slot = _find_slot(ep, 0.0, tower_spans)
        if slot is not None:
            start, length = slot
            return StairTower(
                edge_index=ep.edge_index, start_mm=start, span_count=tower_spans,
                length_mm=length, loop_position_mm=acc + start,
            )
        acc += ep.scaffold_length
    return None


def _find_slot(edge, prefer_mm: float, tower_spans: int) -> Optional[tuple[float, float]]:
    """辺の中で、コーナーから1スパン以上離れた連続 tower_spans スパンの区間を探す.

    prefer_mm に最も近いものを返す。
    """
    spans = edge.spans
    if len(spans) < tower_spans + 2:  # 両端に1スパンずつ確保できない
        return None
    starts = [0.0]
    for s in spans:
        starts.append(starts[-1] + s)

    candidates = []
    # i=1 から始めてコーナー側1スパンを空ける。終端側も1スパン残す
    for i in range(1, len(spans) - tower_spans):
        length = sum(spans[i:i + tower_spans])
        candidates.append((starts[i], length))
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c[0] - prefer_mm))


def stair_deck_deduction(model: ScaffoldModel, plan: StairPlan) -> dict[int, int]:
    """階段室が占有して踏板を敷かないスパンの本数（呼び寸法→本数）.

    数量の二重計上を防ぐため、踏板の集計からこの分を差し引く。
    """
    out: dict[int, int] = {}
    for tower in plan.towers:
        edge = next(
            (e for e in model.plan.edges if e.edge_index == tower.edge_index), None
        )
        if edge is None:
            continue
        acc = 0.0
        for s in edge.spans:
            if tower.start_mm - 1e-6 <= acc < tower.end_mm - 1e-6:
                out[s] = out.get(s, 0) + 1
            acc += s
    return out


def validate_stairs(
    model: ScaffoldModel, plan: StairPlan, max_travel_mm: float = DEFAULT_MAX_TRAVEL_MM
) -> list[str]:
    """配置済みの階段を検証して警告を返す."""
    issues: list[str] = []
    if model.scaffold_height_mm > MIN_HEIGHT_FOR_STAIRS_MM and not plan.towers:
        issues.append(
            f"足場高さ{model.scaffold_height_mm / 1000:.1f}mに対し昇降設備がありません"
            "（安衛則526条）"
        )
        return issues
    if plan.max_travel_mm > max_travel_mm:
        issues.append(
            f"昇降設備までの最大水平移動距離{plan.max_travel_mm / 1000:.1f}mが"
            f"目安{max_travel_mm / 1000:.0f}mを超えます"
        )
    # 区間の重なり
    for i, a in enumerate(plan.towers):
        for b in plan.towers[i + 1:]:
            if a.edge_index == b.edge_index and a.start_mm < b.end_mm and b.start_mm < a.end_mm:
                issues.append(
                    f"辺{a.edge_index}で階段室の区間が重なっています"
                    f"（{a.start_mm:.0f}-{a.end_mm:.0f} と {b.start_mm:.0f}-{b.end_mm:.0f}）"
                )
    return issues
