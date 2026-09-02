"""階段（昇降設備）の自動配置.

安衛則526条: 高さ1.5mを超える箇所には昇降設備が必要。
実務指針: 作業場所から昇降設備までの水平移動距離は30m以内が目安。

配置ルール:
- 足場中心線ループ上に均等配置する（閉ループなので、n箇所なら最大移動距離は 周長/(2n)）
- 階段室は所定スパン数（A系列 1800×1800 なら2スパン=3600mm）を占有する
- コーナーから1スパン以上離す（コーナー支柱まわりは納まりが厳しい）
- 階段室の区間には踏板を敷かない → 数量から差し引く（二重計上の防止）
- 同じ区間に2箇所置かない。重ねると物理的に成立しないうえ、踏板の差引が
  二重にかかって数量が狂う
- min_per_face を指定すると各面に1箇所以上置く（法規ではなく実務上の配慮。
  1面だけに集中すると、その面が塞がったとき降りられない）
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
    min_per_face: int = 0,
) -> StairPlan:
    """階段室をループ上に配置する.

    count を指定するとその箇所数で配置し、指定しなければ
    移動距離が max_travel_mm 以下になる最小箇所数を自動で決める。

    min_per_face を指定すると、まず各面にその数だけ置いてから
    移動距離が足りるまで空いた区間を埋める。
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

    # 置いた区間は occupied に積んで、次の階段が重ならないようにする。
    # 重ねると物理的に成立しないうえ、踏板の差引が二重にかかる。
    occupied: dict[int, list[tuple[float, float]]] = {}

    def _add(tower: Optional[StairTower], reason: str) -> bool:
        if tower is None:
            return False
        tower.reason = reason
        occupied.setdefault(tower.edge_index, []).append(
            (tower.start_mm, tower.end_mm)
        )
        plan.towers.append(tower)
        return True

    if min_per_face > 0:
        for ep in model.plan.edges:
            placed = 0
            for _ in range(min_per_face):
                slot = _find_slot(ep, ep.scaffold_length / 2, tower_spans,
                                  occupied.get(ep.edge_index, []))
                if slot is None:
                    break
                start, length = slot
                acc = sum(
                    e.scaffold_length for e in model.plan.edges
                    if e.edge_index < ep.edge_index
                )
                _add(
                    StairTower(
                        edge_index=ep.edge_index, start_mm=start,
                        span_count=tower_spans, length_mm=length,
                        loop_position_mm=acc + start,
                    ),
                    "各面に昇降設備を確保（1面が塞がっても降りられるようにする）",
                )
                placed += 1
            if placed < min_per_face:
                plan.warnings.append(
                    f"辺{ep.edge_index}に階段室を{min_per_face}箇所置けません"
                    f"（置けたのは{placed}箇所。{tower_spans}スパン連続かつ"
                    "コーナーから1スパン以上離れた空き区間が必要）"
                )
        # 各面に置いたうえで移動距離が足りなければ、一番広く空いた所から埋める。
        # 箇所数だけを条件にすると、必要数を満たしていても配置が偏って
        # 移動距離を超えたままになる（各面の中央に置くので均等にならない）。
        # 実際の移動距離が収まるまで埋める
        while True:
            if (len(plan.towers) >= n
                    and actual_max_travel(plan.towers, loop_len) <= max_travel_mm):
                break
            pos = _largest_gap_center(plan.towers, loop_len)
            if not _add(
                _place_at(model, pos, tower_spans, occupied),
                f"移動距離{max_travel_mm / 1000:.0f}m以内にするための追加",
            ):
                plan.warnings.append(
                    f"階段を{max(n, len(plan.towers) + 1)}箇所置きたいところ"
                    f"{len(plan.towers)}箇所しか置けません"
                    f"（{tower_spans}スパン連続の空き区間が足りない）"
                )
                break
    else:
        targets = [loop_len * i / n for i in range(n)]
        failed = 0
        for t in targets:
            if not _add(
                _place_at(model, t, tower_spans, occupied),
                f"昇降設備{n}箇所を均等配置"
                f"（安衛則526条、水平移動{max_travel_mm / 1000:.0f}m以内）",
            ):
                failed += 1
        if failed:
            # 1箇所ごとに同じ文を並べると、指定箇所数が多いほど警告で埋まる
            # （99箇所の指定で75行出ていた）。何箇所置けたのかを1行で言う
            plan.warnings.append(
                f"指定の{n}箇所のうち{len(plan.towers)}箇所しか配置できません"
                f"（残り{failed}箇所ぶんの空き区間がありません。"
                f"{tower_spans}スパン連続かつコーナーから1スパン以上離れた"
                "区間が必要）"
            )

    # 最大移動距離は理想配置の式ではなく実配置から求める
    # （スロットへの丸めやコーナー回避で位置がずれるため）
    plan.max_travel_mm = actual_max_travel(plan.towers, loop_len)
    if not plan.towers:
        # 階段室が1つも入らない規模。距離を「inf m」と書いても読めないので、
        # 何で代替するのかを書く（526条は階段に限らず昇降設備を求めている）
        plan.warnings.append(
            f"階段室（{tower_spans}スパン連続）が入る区間が無い規模です"
            f"（足場長の合計{loop_len / 1000:.1f}m）。はしご・移動式昇降設備等での"
            "昇降を別途計画してください（安衛則526条は階段に限定していません）"
        )
    elif plan.max_travel_mm > max_travel_mm:
        plan.warnings.append(
            f"階段{len(plan.towers)}箇所では最大水平移動距離が"
            f"{plan.max_travel_mm / 1000:.1f}mとなり"
            f"目安{max_travel_mm / 1000:.0f}mを超えます（{need + 1}箇所以上を検討）"
        )
    # 自前の検証も通しておく。成立しない配置を黙って返すのが一番まずい
    for issue in validate_stairs(model, plan, max_travel_mm):
        if issue not in plan.warnings:
            plan.warnings.append(issue)
    return plan


def _largest_gap_center(towers: list[StairTower], loop_len_mm: float) -> float:
    """一番広く空いているループ区間の中央を返す（次の階段を置きたい位置）."""
    if not towers:
        return 0.0
    pos = sorted(t.loop_position_mm for t in towers)
    best_gap, best_center = -1.0, 0.0
    for i, a in enumerate(pos):
        b = pos[i + 1] if i + 1 < len(pos) else pos[0] + loop_len_mm
        if b - a > best_gap:
            best_gap, best_center = b - a, (a + b) / 2
    return best_center % loop_len_mm


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
    model: ScaffoldModel,
    loop_pos_mm: float,
    tower_spans: int,
    occupied: Optional[dict[int, list[tuple[float, float]]]] = None,
) -> Optional[StairTower]:
    """ループ上の位置に最も近い、配置可能な区間へ階段室を置く.

    occupied に入っている区間は既に別の階段が使っているので避ける。
    """
    occ = occupied or {}

    def _try(ep, prefer: float, acc: float) -> Optional[StairTower]:
        slot = _find_slot(ep, prefer, tower_spans, occ.get(ep.edge_index, []))
        if slot is None:
            return None
        start, length = slot
        return StairTower(
            edge_index=ep.edge_index, start_mm=start, span_count=tower_spans,
            length_mm=length, loop_position_mm=acc + start,
        )

    acc = 0.0
    for ep in model.plan.edges:
        edge_len = ep.scaffold_length
        if loop_pos_mm <= acc + edge_len or ep is model.plan.edges[-1]:
            local = max(0.0, min(loop_pos_mm - acc, edge_len))
            tower = _try(ep, local, acc)
            if tower is not None:
                return tower
            # この辺に置けなければ次の辺を探す
        acc += edge_len
    # どこにも置けなければ、置ける辺を総当たり
    acc = 0.0
    for ep in model.plan.edges:
        tower = _try(ep, 0.0, acc)
        if tower is not None:
            return tower
        acc += ep.scaffold_length
    return None


def _find_slot(
    edge,
    prefer_mm: float,
    tower_spans: int,
    occupied: Optional[list[tuple[float, float]]] = None,
) -> Optional[tuple[float, float]]:
    """辺の中で、コーナーから1スパン以上離れた連続 tower_spans スパンの区間を探す.

    occupied と重なる区間は候補から外す。prefer_mm に最も近いものを返す。
    """
    spans = edge.spans
    if len(spans) < tower_spans + 2:  # 両端に1スパンずつ確保できない
        return None
    starts = [0.0]
    for s in spans:
        starts.append(starts[-1] + s)

    taken = occupied or []
    candidates = []
    # i=1 から始めてコーナー側1スパンを空ける。終端側も1スパン残す
    for i in range(1, len(spans) - tower_spans):
        start = starts[i]
        length = sum(spans[i:i + tower_spans])
        if any(start < b and a < start + length for a, b in taken):
            continue
        candidates.append((start, length))
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
    if plan.towers and plan.max_travel_mm > max_travel_mm:
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
