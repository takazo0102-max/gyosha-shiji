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

# 枠組足場の建枠が兼ねる手すりの高さ（作業床から。安衛則563条の85cm以上を満たす）
FRAME_GUARD_RAIL_HEIGHT_MM = 900

# 手すり方式
GUARD_RAIL_ADVANCE = "先行手すり"   # 先行手摺部材（手すり＋斜材が一体）
GUARD_RAIL_LEDGER = "布材"          # 布材で手すり＋中桟を組む


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
    post_row_spacing_mm: Optional[int] = None  # 内外建地列の芯々間隔（Noneで自動）
    deck_to_post_gap_mm: int = 100         # 床材と建地の隙間
    # 手すり方式: 先行手すり工法か、布材（手すり＋中桟）か
    # ビル工事用は原則として手すり先行工法（特別教育テキスト）
    guard_rail_type: str = GUARD_RAIL_LEDGER
    guard_rail_koma: int = 2               # 手すり高さ（コマ数。A:900 / B:950）
    guard_rail_height_mm: Optional[int] = None  # 直接指定する場合（枠組等）
    has_midrail: bool = True               # 中桟
    midrail_height_mm: int = 450           # 中桟高さ（作業床から。基準35〜50cm）
    has_toe_board: bool = True             # 幅木
    toe_board_height_mm: int = 157         # 幅木高さ（落下物防止は10cm以上）
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
    def post_row_spacing_mm(self) -> int:
        """内外の建地列の芯々間隔.

        作業床の被覆幅（deck_width_total）とは別物。くさび式は内外を繋ぐ
        腕木（布材）の呼び寸法が、そのまま建地列の間隔になる。枠組は建枠幅。

        以前は建地列の間隔として deck_width_total を使っていたため、
        部材表は腕木600を発注するのに図面は670で描く、という食い違いが
        出ていた。発注する部材の寸法を正とする。
        """
        if self.config.post_row_spacing_mm is not None:
            return self.config.post_row_spacing_mm
        if self.master.is_frame:
            return self.master.frame_width_for(self.deck_width_total)[0]
        # 作業床を載せられる範囲で最大の腕木（布材）
        cands = [
            p.nominal_dim for p in self.master.by_category("布材")
            if p.nominal_dim <= self.deck_width_total
        ]
        return max(cands) if cands else self.deck_width_total

    @property
    def deck_width_total(self) -> int:
        gaps = self.config.deck_gap_mm * (len(self.config.deck_widths) - 1)
        return sum(self.config.deck_widths) + gaps

    @property
    def guard_rail_height_mm(self) -> int:
        """作業床からの手すり高さ.

        枠組式は建枠自体が手すりを兼ねるため、コマピッチ（枠組には無い概念）ではなく
        建枠の手すり高さを使う。
        """
        if self.config.guard_rail_height_mm is not None:
            return self.config.guard_rail_height_mm
        if self.master.is_frame:
            return FRAME_GUARD_RAIL_HEIGHT_MM
        return self.config.guard_rail_koma * self.master.koma_pitch

    def wall_tie_limits(self) -> tuple[float, float, str]:
        """壁つなぎ間隔の法定上限（垂直, 水平, 根拠）.

        安衛則570条1項五号は足場の種類で上限が違う:
          イ わく組足場（高さ5m未満を除く）: 垂直9m・水平8m
          ハ 単管足場: 垂直5m・水平5.5m（くさび緊結式はこれに準じる）

        枠組に単管の値を当てると法規上不要な壁つなぎを拾うことになり、
        逆に緩い方を全系列に当てると法規違反を見逃す。系列で分ける。
        """
        if self.master.is_frame and self.scaffold_height_mm >= 5000:
            return (9000.0, 8000.0,
                    "安衛則570条1項五号イ（わく組足場: 垂直9m×水平8m以下）")
        return (5000.0, 5500.0,
                "安衛則570条1項五号ハ（単管足場に準じる: 垂直5m×水平5.5m以下）")

    def edges_without_wall_ties(self) -> list[int]:
        """壁つなぎが1本も無い辺の番号.

        短い面は支柱が足りず壁つなぎを入れられないことがある。その面は
        両隣の面の壁つなぎにコーナー経由で支持される前提になるが、
        構造計算はその面の風荷重を誰にも負担させていない。黙って通さない
        ために取り出せるようにしておく。
        """
        has = {t.edge_index for t in self.wall_ties}
        return [e.edge_index for e in self.plan.edges if e.edge_index not in has]

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
        interior = acc[1:-1]  # コーナー支柱そのものは除外
        candidates = [
            x
            for x in interior
            if x >= max(1800, e.spans[0]) and (e.scaffold_length - x) >= max(1800, e.spans[-1])
        ]
        if not candidates:
            # コーナーから1スパン空ける取り合いの都合を満たせない短い面。
            # ここで諦めるとその面が壁つなぎ0本になり、法規チェックも
            # 構造計算もその面を見なくなる（黙って未拘束の面ができる）。
            # 取り合いの都合より面を拘束する方が優先なので、中央寄りの
            # 支柱に1本入れる。
            if not interior:
                continue
            mid = e.scaffold_length / 2
            picked = [min(interior, key=lambda x: abs(x - mid))]
            for h in tie_levels:
                for x in picked:
                    ties.append(
                        WallTie(edge_index=e.edge_index, position_mm=x, height_mm=h)
                    )
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
