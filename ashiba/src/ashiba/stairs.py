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
LANDING_EVERY_LEVELS = 2         # 昇降階段は2層以下毎に踊り場（このツールでは階段室の外の作業床が兼ねる）


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
    landings_per_tower: int = 0    # 1箇所あたり階段室を出て作業床を通る回数（2層ごと。作業床が踊り場を兼ね、踊り場の床材は使わない）
    warnings: list[str] = field(default_factory=list)
    # 外付け: 外側建地列のさらに外に建地を1列立て、その升目に 上り口＋階段2スパン＋降り口 の区間を作る。本体の作業床は
    # 切らない（利用者の指摘 2026-10-20: 敷地が広いところは階段を横に付けるパターンが多い。回れるように4スパン要る、
    # 上り口と降り口に横のスパンが必要）
    outside: bool = False

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
    avoid: Optional[dict[int, list[tuple[float, float]]]] = None,
    corner_gap: int = 1,
) -> StairPlan:
    """階段室をループ上に配置する.

    count を指定するとその箇所数で配置し、指定しなければ
    移動距離が max_travel_mm 以下になる最小箇所数を自動で決める。

    min_per_face を指定すると、まず各面にその数だけ置いてから
    移動距離が足りるまで空いた区間を埋める。

    avoid は置いてはいけない区間（辺 → [(始点, 終点)]）。開口部の梁枠区間など、
    階段室を組めない場所を先に埋めておく。
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
    occupied: dict[int, list[tuple[float, float]]] = {
        k: list(v) for k, v in (avoid or {}).items()
    }

    def _add(tower: Optional[StairTower], reason: str) -> bool:
        if tower is None:
            return False
        tower.reason = reason
        occupied.setdefault(tower.edge_index, []).append(
            (tower.start_mm, tower.end_mm)
        )
        plan.towers.append(tower)
        return True

    def _add_if_shorter(pos: float, reason: str) -> bool:
        """いちばん空いた所の中央に足す。置ける区間が別の面へずれて移動距離が縮まないなら足さない.

        外付けの階段が敷地境界に詰まった面を避けると、空きの中央は置けない面にあり、足した階段は
        置ける面の隣へずれる。縮まないのに足し続けて 30×20m の建物に 7 箇所置いていた（2026-10-23 実機）。
        """
        # 狙った空き（pos を含む隣り合う階段の間）の中に入れば足す。入らなければ移動距離は縮まない
        prev_pos = sorted(tw.loop_position_mm for tw in plan.towers)
        if not _add(_place_at(model, pos, tower_spans, occupied, corner_gap), reason):
            return False
        if not prev_pos:
            return True
        lo = max((q for q in prev_pos if q <= pos), default=prev_pos[-1] - loop_len)
        hi = min((q for q in prev_pos if q > pos), default=prev_pos[0] + loop_len)
        q = plan.towers[-1].loop_position_mm
        if any(lo + 1.0 < x < hi - 1.0 for x in (q, q - loop_len, q + loop_len)):
            return True
        tw = plan.towers.pop()
        occupied[tw.edge_index].remove((tw.start_mm, tw.end_mm))
        return False

    if min_per_face > 0:
        for ep in model.plan.edges:
            placed = 0
            for _ in range(min_per_face):
                slot = _find_slot(ep, ep.scaffold_length / 2, tower_spans,
                                  occupied.get(ep.edge_index, []), corner_gap)
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
                    f"{model.face_name(ep.edge_index)}に階段室を{min_per_face}箇所置けません"
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
            placer = _add_if_shorter if len(plan.towers) >= n else (
                lambda q, why: _add(_place_at(model, q, tower_spans, occupied, corner_gap), why))
            if not placer(pos, f"移動距離{max_travel_mm / 1000:.0f}m以内にするための追加"):
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
                _place_at(model, t, tower_spans, occupied, corner_gap),
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
        # 開口部などを避けて位置がずれると、必要数を置いても移動距離を超える
        # （実際にサンプルで31.5mになった）。箇所数を指定していないときは、
        # 収まるまで一番広い空きから追加する
        if count is None:
            while (plan.towers
                   and actual_max_travel(plan.towers, loop_len) > max_travel_mm):
                pos = _largest_gap_center(plan.towers, loop_len)
                if not _add_if_shorter(pos, f"移動距離{max_travel_mm / 1000:.0f}m以内にするための追加"
                                            "（開口部等を避けて位置がずれた分）"):
                    break

    # 箇所数を指定していないとき、置ける区間が一部の面に限られる（外付けの階段が敷地境界に詰まった面を
    # 避ける等）と、均等配置＋空きの中央への追加では移動距離が縮まないまま数だけ増える。置ける区間の
    # 組合せから、移動距離が収まるいちばん少ない箇所数で、移動距離が最小のものを探して置き換える
    if count is None and min_per_face == 0 and plan.towers and (
            len(plan.towers) > need or actual_max_travel(plan.towers, loop_len) > max_travel_mm):
        best = _best_tower_set(model, tower_spans, avoid or {}, corner_gap, loop_len, need,
                               max_travel_mm, len(plan.towers))
        if best is not None and (len(best) < len(plan.towers) or (
                actual_max_travel(best, loop_len) < actual_max_travel(plan.towers, loop_len) - 1.0
                and len(best) <= len(plan.towers))):
            for tw in best:
                tw.reason = (f"昇降設備{len(best)}箇所（置ける区間の組合せで水平移動"
                             f"{actual_max_travel(best, loop_len) / 1000:.1f}m が最小。安衛則526条）")
            plan.towers = best

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


def _best_tower_set(model: ScaffoldModel, tower_spans: int, avoid: dict, corner_gap: int, loop_len: float,
                    need: int, max_travel_mm: float, upto: int) -> Optional[list[StairTower]]:
    """置ける区間（avoid と重ならない、tower_spans スパン連続）の組合せのうち、移動距離が max_travel_mm 以下になる
    いちばん少ない箇所数で移動距離が最小のもの。need〜upto 箇所を試し、収まらなければ upto 箇所で最小のもの."""
    import itertools

    cands = []
    acc = 0.0
    for ep in model.plan.edges:
        spans = ep.spans
        starts = [0.0]
        for s in spans:
            starts.append(starts[-1] + s)
        taken = avoid.get(ep.edge_index, [])
        for i in range(corner_gap, len(spans) - tower_spans - corner_gap + 1):
            st, ln = starts[i], float(sum(spans[i:i + tower_spans]))
            if any(st < b and a < st + ln for a, b in taken):
                continue
            cands.append((ep.edge_index, st, ln, acc + st, len(spans[:i])))
        acc += ep.scaffold_length
    if not cands:
        return None

    def overlap(sel) -> bool:
        for a, b in itertools.combinations(sel, 2):
            if a[0] == b[0] and a[1] < b[1] + b[2] and b[1] < a[1] + a[2]:
                return True
        return False

    def travel(sel) -> float:
        pos = sorted(c[3] for c in sel)
        if len(pos) == 1:
            return loop_len / 2
        gaps = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)] + [loop_len - pos[-1] + pos[0]]
        return max(gaps) / 2

    best_any = None
    for k in range(max(1, need), max(need, upto) + 1):
        best = None
        combos = itertools.combinations(cands, k)
        for n_try, sel in enumerate(combos):
            if n_try > 60000:
                break
            if overlap(sel):
                continue
            tv = travel(sel)
            if best is None or tv < best[0] - 1e-6:
                best = (tv, sel)
        if best is None:
            continue
        if best_any is None or best[0] < best_any[0]:
            best_any = best
        if best[0] <= max_travel_mm:
            best_any = best
            break
    if best_any is None:
        return None
    return [StairTower(edge_index=c[0], start_mm=c[1], span_count=tower_spans, length_mm=c[2], loop_position_mm=c[3])
            for c in sorted(best_any[1], key=lambda c: c[3])]


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
        n = len(plan.towers)
        if n >= plan.required_count:
            # 数は足りているのに超えるのは偏りのせい。「2箇所以上を推奨」と
            # 指定済みの数を勧めても直せない（実機の五角形棟で2箇所指定→31.9m）
            even = loop_len / (2 * n) / 1000
            hint = (f"（{n}箇所を等間隔に置けば約{even:.1f}m。位置の見直し、"
                    f"または{n + 1}箇所以上）")
        else:
            hint = f"（{plan.required_count}箇所以上を推奨）"
        plan.warnings.append(
            f"指定された{n}箇所では最大水平移動距離が"
            f"{plan.max_travel_mm / 1000:.1f}mとなり"
            f"目安{max_travel_mm / 1000:.0f}mを超えます{hint}"
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
    corner_gap: int = 1,
) -> Optional[StairTower]:
    """ループ上の位置に最も近い、配置可能な区間へ階段室を置く.

    occupied に入っている区間は既に別の階段が使っているので避ける。
    """
    occ = occupied or {}

    def _try(ep, prefer: float, acc: float) -> Optional[StairTower]:
        slot = _find_slot(ep, prefer, tower_spans, occ.get(ep.edge_index, []), corner_gap)
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
    corner_gap: int = 1,
) -> Optional[tuple[float, float]]:
    """辺の中で、コーナーから corner_gap スパン以上離れた連続 tower_spans スパンの区間を探す.

    occupied と重なる区間は候補から外す。prefer_mm に最も近いものを返す。
    外付けの階段室は足場の外に出るので、コーナーまで使ってよい（corner_gap=0）。
    """
    spans = edge.spans
    if len(spans) < tower_spans + 2 * corner_gap:  # 両端に corner_gap スパンずつ確保できない
        return None
    starts = [0.0]
    for s in spans:
        starts.append(starts[-1] + s)

    taken = occupied or []
    candidates = []
    # i=corner_gap から始めてコーナー側を空ける。終端側も corner_gap スパン残す
    for i in range(corner_gap, len(spans) - tower_spans - corner_gap + 1):
        start = starts[i]
        length = sum(spans[i:i + tower_spans])
        if any(start < b and a < start + length for a, b in taken):
            continue
        candidates.append((start, length))
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c[0] - prefer_mm))


STAIR_LAYOUTS = {"inside": "inside", "内": "inside", "中": "inside", "足場の中": "inside",
                 "outside": "outside", "外付け": "outside", "外": "outside", "3列": "outside", "4列": "outside",
                 "auto": "auto", "自動": "auto"}
OUTSIDE_SPACE_MARGIN_MM = 600    # 外付けにするには、足場の外に建地列の間隔＋この余裕が要る
STAIR_INSIDE_MIN_ROW_MM = 900    # 足場の中に階段を組める幅（900 枠）。それより狭いと外付け（600 枠 2 列）


def decide_outside(model: ScaffoldModel, layout: str, clearance_mm: float) -> tuple[bool, str]:
    """階段を外付けにするか。auto は足場の外の空き（clearance_space_mm）で決める."""
    kind = STAIR_LAYOUTS.get(str(layout or "inside").strip(), "inside")
    if model.master.is_frame or model.config.scaffold_form == "一側足場":
        return False, ("枠組・一側足場は階段を足場の中に組みます（外付けの指定は使いません）" if kind == "outside" else "")
    need = model.post_row_spacing_mm + OUTSIDE_SPACE_MARGIN_MM
    # 階段は 900 枠の中か、600 枠 2 列（利用者の指定 2026-10-23）。幅 900 未満の本足場の中に階段枠（幅 450）を
    # 入れると、昇り口の脇を人が通れない → 外付け（外側建地列の外にもう 1 列）にする
    if model.post_row_spacing_mm < STAIR_INSIDE_MIN_ROW_MM:
        if clearance_mm < need:
            return True, (f"幅 {model.post_row_spacing_mm:.0f} の足場の階段は外付け（600 枠 2 列）にしますが、足場の外の空き"
                          f" {clearance_mm:.0f}mm は外付けに要る {need:.0f}mm より狭いです（幅 900 の足場にするか、"
                          "階段の位置を空いた面へ）")
        # 中を明示したときだけ書く（既定のままなら外付けが当たり前なので要確認に入れない）
        return True, ("" if str(layout or "").strip() != "inside" else
                      f"幅 {model.post_row_spacing_mm:.0f} の足場の中に階段は組めないので外付け（600 枠 2 列）にしました")
    if kind == "outside":
        if clearance_mm < need:
            return True, (f"階段を外付けにしましたが、足場の外の空き {clearance_mm:.0f}mm は"
                          f"外付けに要る {need:.0f}mm（建地列の間隔＋{OUTSIDE_SPACE_MARGIN_MM}）より狭いです")
        return True, ""
    if kind == "auto":
        # 決めた結果は数量の注記（外付けの部材）と図に出るので、要確認には入れない
        return clearance_mm >= need, ""
    return False, ""


def tower_spans(model: ScaffoldModel, tower: StairTower) -> list[int]:
    """階段室の区間に入るスパン（始点側から）."""
    edge = next((e for e in model.plan.edges if e.edge_index == tower.edge_index), None)
    if edge is None:
        return []
    acc = 0.0
    out: list[int] = []
    for s in edge.spans:
        if tower.start_mm - 1e-6 <= acc < tower.end_mm - 1e-6:
            out.append(s)
        acc += s
    return out


def flight_spans(model: ScaffoldModel, tower: StairTower, outside: bool) -> tuple[int, list[int]]:
    """階段を掛けるスパン（区間の何番目から, スパンの並び）。外付けは両端（上り口・降り口）を除いた中."""
    ts = tower_spans(model, tower)
    if outside and len(ts) >= 3:
        return 1, ts[1:-1]
    return 0, ts


def flight_span_index(level: int, n_spans: int) -> int:
    """k 層目に下から上がってくる階段のスパン（0＝始点側）。奇数層は始点側、偶数層は終点側."""
    if n_spans <= 1:
        return 0
    return 0 if level % 2 == 1 else 1


def stair_open_cells(model: ScaffoldModel, plan: StairPlan, n_levels: int) -> dict[int, int]:
    """階段室で床を敷かないセル（呼び寸法→スパン×層の数）.

    階段は同じ向きで2層ずつ（奇数層への階段は始点側のスパン、偶数層への階段は終点側のスパン）なので、
    各層で下からの階段が上がってくる1スパンだけが開口になり、もう一方のスパンには床を敷く。
    1スパンの階段室は全層が開口。3スパン目以降は階段が掛からないので床を敷く。
    """
    out: dict[int, int] = {}
    for tower in plan.towers:
        edge = next((e for e in model.plan.edges if e.edge_index == tower.edge_index), None)
        if edge is None:
            continue
        acc = 0.0
        tspans: list[int] = []
        for s in edge.spans:
            if tower.start_mm - 1e-6 <= acc < tower.end_mm - 1e-6:
                tspans.append(s)
            acc += s
        if not tspans:
            continue
        for k in range(1, n_levels + 1):
            if len(tspans) == 1:
                s = tspans[0]
            else:
                s = tspans[0] if k % 2 == 1 else tspans[1]
            out[s] = out.get(s, 0) + 1
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
                    f"{model.face_name(a.edge_index)}で階段室の区間が重なっています"
                    f"（{a.start_mm:.0f}-{a.end_mm:.0f} と {b.start_mm:.0f}-{b.end_mm:.0f}）"
                )
    return issues


def hatch_part(model: ScaffoldModel):
    """ハッチ付布板（梯子内蔵。日建 NDN6TA）と、その幅. 系列に無い・床の幅に合わなければ (None, 0)."""
    m = model.master
    if m.is_tube or m.is_frame or model.config.scaffold_form != "本足場":
        return None, 0
    for p in m.by_category("踊り場"):
        if "梯子" not in p.note:
            continue
        w = next((int(tok[1:]) for tok in p.note.split() if tok.startswith("幅") and tok[1:].isdigit()), 0)
        if w and w in tuple(model.deck_widths_in_use):
            return p, w
    return None, 0


def place_hatch_ladders(model: ScaffoldModel, n: int) -> list[tuple[int, int]]:
    """ハッチ付布板（梯子内蔵）を置くスパン [(辺番号, スパンの番号 0〜)]。布板と同じ長さのスパン（面の中。隅の升目ではない）
    から外周に均等に n 箇所. 置けなければ []."""
    part, _w = hatch_part(model)
    if part is None or n <= 0:
        return []
    cands = []
    acc = 0.0
    for ep in model.plan.edges:
        x = 0.0
        for i, s in enumerate(ep.spans):
            if int(s) == int(part.nominal_dim):
                cands.append((acc + x + s / 2.0, ep.edge_index, i))
            x += s
        acc += ep.scaffold_length
    if not cands:
        return []
    loop = acc
    out: list[tuple[int, int]] = []
    for k in range(n):
        target = loop * (k + 0.25) / n
        free = [c for c in cands if (c[1], c[2]) not in out]
        if not free:
            break
        best = min(free, key=lambda c: min(abs(c[0] - target), loop - abs(c[0] - target)))
        out.append((best[1], best[2]))
    return out
