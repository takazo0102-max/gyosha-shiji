"""足場モデル: 平面割付＋立面割付＋構成条件を束ねた検査・拾い対象.

壁つなぎの自動配置もここで行う（仕様4.2:
コーナーから1.8m以上離れた左右均等の支柱に配置、コーナーから1スパン除外）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .elevation_solver import ElevationResult
from .master import PartMaster
from .plan_solver import PlanResult


@dataclass
class AsagaoSpec:
    """朝顔（防護棚）の仕様（仕様5-#10）.

    高さ10m以上で1段・20m以上で2段、突出2m以上・傾斜20度以上、
    取付部は2スパン毎に壁つなぎ。
    """

    stages: int = 0                  # 設置段数（0=未設置）
    projection_mm: float = 2000.0    # 水平突出
    angle_deg: float = 25.0          # 水平面からの傾斜
    tie_every_spans: int = 2         # 取付部の壁つなぎ間隔（スパン数）
    heights_mm: list[int] = field(default_factory=list)  # 設置高さ（空なら自動）


@dataclass
class ScaffoldConfig:
    scaffold_form: str = "本足場"          # 本足場 / 一側足場
    # 踏板幅は系列で実寸が違う（A:400/250、B:405/240、次世代:500）。
    # Noneならマスタの系列既定を使う（決め打ちにするとマスタ引き当てが静かに失敗する）
    deck_widths: Optional[tuple[int, ...]] = None
    next_gen: bool = False                 # 次世代足場（くさび派生・踏板幅500）
    deck_gap_mm: int = 20                  # 床材間の隙間
    deck_to_post_gap_mm: int = 100         # 床材と建地の隙間
    guard_rail_koma: int = 2               # 手すり高さ（コマ数。A:900 / B:950）
    has_midrail: bool = True               # 中桟
    has_toe_board: bool = True             # 幅木
    n_stairs: int = 1                      # 階段設置箇所数
    wall_tie_span_step: int = 3            # 壁つなぎ水平間隔（スパン数、実務推奨3以内）
    wall_tie_level_step: int = 2           # 壁つなぎ垂直間隔（作業層数、実務推奨2以内）
    period_days: int = 60                  # 設置期間（届出要否判定）
    asagao: Optional["AsagaoSpec"] = None  # 朝顔（Noneなら未設置）


@dataclass
class WallTie:
    edge_index: int
    position_mm: float   # 辺の始点コーナー支柱からの距離
    height_mm: int       # GLからの高さ


@dataclass
class ScaffoldModel:
    master: PartMaster
    plan: PlanResult
    elevation: ElevationResult
    config: ScaffoldConfig = field(default_factory=ScaffoldConfig)
    building_height_mm: float = 0.0        # 建物高さ（架け面積・届出判定用）
    clearance_space_mm: float = 2000.0     # 躯体外面から確保できる水平スペース
    wall_ties: list[WallTie] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.config.deck_widths is None:
            self.config.deck_widths = self.master.default_deck_widths(
                self.config.next_gen
            )
        if not self.wall_ties:
            self.wall_ties = generate_wall_ties(
                self.plan, self.elevation, self.config
            )

    @property
    def scaffold_height_mm(self) -> int:
        return self.elevation.total_height

    @property
    def deck_width_total(self) -> int:
        gaps = self.config.deck_gap_mm * (len(self.config.deck_widths) - 1)
        return sum(self.config.deck_widths) + gaps

    @property
    def guard_rail_height_mm(self) -> int:
        return self.config.guard_rail_koma * self.master.koma_pitch

    def wall_tie_max_spacing(self) -> tuple[float, float]:
        """壁つなぎの実配置から(垂直最大, 水平最大)間隔[mm]を返す."""
        if not self.wall_ties:
            return (float("inf"), float("inf"))
        v_max = 0.0
        h_max = 0.0
        heights = sorted({t.height_mm for t in self.wall_ties})
        # 最下段の壁つなぎまで・段間
        prev = 0
        for h in heights:
            v_max = max(v_max, h - prev)
            prev = h
        v_max = max(v_max, self.scaffold_height_mm - prev)
        for e in self.plan.edges:
            xs = sorted(
                t.position_mm for t in self.wall_ties if t.edge_index == e.edge_index
            )
            if not xs:
                if e.scaffold_length > 1800:
                    h_max = max(h_max, e.scaffold_length)
                continue
            prev_x = 0.0
            for x in xs:
                h_max = max(h_max, x - prev_x)
                prev_x = x
            h_max = max(h_max, e.scaffold_length - prev_x)
        return (v_max, h_max)


def generate_wall_ties(
    plan: PlanResult, elevation: ElevationResult, config: ScaffoldConfig
) -> list[WallTie]:
    """壁つなぎ自動配置.

    - 水平: コーナーから1スパンを除外し、1.8m以上離れた支柱に config.wall_tie_span_step
      スパン毎に左右均等配置
    - 垂直: 根がらみの2層上から wall_tie_level_step 層毎＋最上層
    """
    ties: list[WallTie] = []
    # 垂直位置: 作業層のうち step 毎（最上層は必ず含める）
    levels = elevation.level_heights
    if not levels:
        return ties
    tie_levels = list(reversed(levels))[:: config.wall_tie_level_step]
    tie_levels = sorted(tie_levels)

    for e in plan.edges:
        # 支柱位置（始点からの累積距離）。両端コーナーから1スパンを除外
        acc = [0.0]
        for s in e.spans:
            acc.append(acc[-1] + s)
        candidates = [
            x
            for x in acc[1:-1]  # コーナー支柱そのものは除外
            if x >= max(1800, e.spans[0]) and (e.scaffold_length - x) >= max(1800, e.spans[-1])
        ]
        if not candidates:
            continue
        # step スパン毎に選ぶ（左右均等: 中央対称になるよう間引く）
        step = config.wall_tie_span_step
        picked: list[float] = []
        idxs = [i for i, x in enumerate(acc) if x in candidates]
        for k, i in enumerate(idxs):
            if k % step == 0:
                picked.append(acc[i])
        if picked and (e.scaffold_length - picked[-1]) > step * 1800:
            picked.append(acc[idxs[-1]])
        for h in tie_levels:
            for x in picked:
                ties.append(WallTie(edge_index=e.edge_index, position_mm=x, height_mm=h))
    return ties
