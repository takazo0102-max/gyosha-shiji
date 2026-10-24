"""足場モデル: 平面割付＋立面割付＋構成条件を束ねた検査・拾い対象.

壁つなぎの自動配置もここで行う（仕様4.2:
コーナーから1.8m以上離れた左右均等の支柱に配置、コーナーから1スパン除外）。
条件を満たす支柱が無い短い面は、取り合いの都合より面を拘束する方を優先して
中央寄りの支柱に1本入れる。それでも入らない面は edges_without_wall_ties() で
取り出せるようにし、黙って未拘束の面を作らない。

検査・拾い・作図が共有する寸法をここに集約している:
- post_row_spacing_mm: 内外建地列の芯々間隔（作業床の被覆幅とは別物）
- wall_tie_limits(): 壁つなぎ間隔の法定上限（足場の種類で違う）
- guard_rail_height_mm / midrail_height_mm: 手すり・中桟の高さ。くさびは緊結部
  （コマ）にしか付かないのでコマピッチの倍数、枠組は建枠の値
- deck_widths_in_use: 実際に敷く作業床の幅。一側足場は1枚敷き（本足場の
  内外2枚敷きで数えると、床が倍・受けブラケットが0本になる）
- face_name(): 面の呼び名（南面など）。図面・帳票で人に見せる側は辺番号で呼ばない
- asagao_heights(): 朝顔の設置高さ（法は段数しか定めないので実務の目安から）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .elevation_solver import ElevationResult
from .master import PartMaster
from .plan_solver import PlanResult

# 枠組足場の建枠が兼ねる手すりの高さ（作業床から。安衛則563条の85cm以上を満たす）
FRAME_GUARD_RAIL_HEIGHT_MM = 900
# 単管の手すり・中桟（安衛則563条: 手すり85cm以上、中桟35〜50cm。立面ソルバが最上層の床を決めるのに使う）
from .elevation_solver import (  # noqa: E402,F401
    TUBE_GUARD_RAIL_HEIGHT_MM, TUBE_MIDRAIL_HEIGHT_MM, TUBE_POST_ABOVE_RAIL_MM,
)
# アルミ階段枠の外幅（日建 NDAL4518K・信和 AL3055SW）
STAIR_FRAME_WIDTH_MM = 481
FRAME_MIDRAIL_HEIGHT_MM = 450       # 建枠の中桟（建枠と一体）

# 手すり方式
GUARD_RAIL_ADVANCE = "先行手すり"   # 先行手摺部材（手すり＋斜材が一体）
GUARD_RAIL_LEDGER = "布材"          # 布材で手すり＋中桟を組む


# 朝顔の設置高さの実務目安（法は段数と突出・傾斜のみを定める）
ASAGAO_FIRST_MIN_MM = 4000
ASAGAO_FIRST_MAX_MM = 5000
ASAGAO_STAGE_PITCH_MM = 10000


ASAGAO_KIND_ASAGAO = "朝顔"
ASAGAO_KIND_SAFE_WING = "セーフウイング"
ASAGAO_KINDS = (ASAGAO_KIND_ASAGAO, ASAGAO_KIND_SAFE_WING)
SAFE_WING_PROJECTION_MM = 1280.0   # 信和セーフウイング資料（swg.pdf）: 張出1,280mm・25°
SAFE_WING_ANGLE_DEG = 25.0


@dataclass
class AsagaoSpec:
    """朝顔（防護棚）の仕様（仕様5-#10）.

    高さ10m以上で1段・20m以上で2段、突出2m以上・傾斜20度以上、
    取付部は2スパン毎に壁つなぎ。
    """

    stages: int = 0                  # 設置段数（0=未設置）
    # 種別: "朝顔"（防護棚・突出2m以上）か "セーフウイング"（信和の簡易落下物防止機材、
    # 張出1,280mm・25°）。セーフウイングは防護棚の要件を満たさないので、10m以上の
    # 足場では法規#10がNGになる（別途朝顔が要る）。低い足場の落下物対策として使う
    kind: str = ASAGAO_KIND_ASAGAO
    projection_mm: float = 2000.0    # 水平突出
    angle_deg: float = 25.0          # 水平面からの傾斜
    tie_every_spans: int = 2         # 取付部の壁つなぎ間隔（スパン数）
    heights_mm: list[int] = field(default_factory=list)  # 設置高さ（空なら自動）
    # 付ける面の名前（空なら全部の面。利用者の指定 2026-10-24: 朝顔あとで必要箇所を選べるようにしたい）。
    # 割付の面の番号へは build_model が直して ScaffoldModel.asagao_edges に入れる
    faces: list[str] = field(default_factory=list)


@dataclass
class ScaffoldConfig:
    scaffold_form: str = "本足場"          # 本足場 / 一側足場（建地1列。ブラケット足場・抱き足場もこれ）
    # 建地1列の足場の組み方（利用者の指定 2026-10-21「ブラケット足場、単管抱き足場、ブラケットは単管と支柱のタイプ」）:
    #   "ブラケット" … 建地に床受けブラケットを付けて床を載せる（従来の一側足場）
    #   "抱き"       … 単管の建地を両側から2本の布で抱き、その上に足場板（単管抱き足場）
    single_row_kind: str = ""
    # ブラケット足場の建地: "支柱"（くさび等の系列の支柱）／"単管"（単管＋クランプ式ブラケット。系列は単管）
    bracket_post: str = "支柱"
    # 階段の代わりの昇降設備（はしご等）の箇所数。単管抱き足場など階段の入らない足場で使う（数量は別途手配）
    ladders: int = 0
    # 踏板幅は系列で実寸が違う（A:400/250、B:405/240、次世代:500）。
    # Noneならマスタの系列既定を使う（決め打ちにするとマスタ引き当てが静かに失敗する）
    deck_widths: Optional[tuple[int, ...]] = None
    next_gen: bool = False                 # 次世代足場（くさび派生・踏板幅500）
    # 養生材（メッシュシート・防音シート・密閉シート・防音パネル。空・なしは張らない）。風荷重の充実率と同じ指定
    sheet_type: str = ""
    # 図面のペン {"post": 3, ...}（ashiba.pens。パレットの「ペン」で選ぶ。無ければ 1）
    pens: dict = field(default_factory=dict)
    deck_gap_mm: int = 20                  # 床材間の隙間
    post_row_spacing_mm: Optional[int] = None  # 内外建地列の芯々間隔（Noneで自動）
    deck_to_post_gap_mm: int = 100         # 床材と建地の隙間
    # 手すり方式: 先行手すり工法か、布材（手すり＋中桟）か
    # ビル工事用は原則として手すり先行工法（特別教育テキスト）
    guard_rail_type: str = GUARD_RAIL_LEDGER
    guard_rail_koma: int = 2               # 手すり高さ（コマ数。A:900 / B:950）
    # 躯体側（内側建地列）の手すり＋中桟を布材で組む。実機の模型で外側だけ手すりが
    # あり内側が素通しだったので、既定で入れる（一側足場・枠組には内側列が無い）
    inner_guard_rail: bool = True
    # 妻側（足場の端の開放端）の墜落防止: "布材"（手すり＋中桟）か "ブレス材"（先行手すり。くさび式だけ）
    # （利用者の指定 2026-10-24: 妻側を布材かブレス材か選択する仕組み作成して）
    end_guard: str = "布材"
    # 支柱の補強仕様。"強力つなぎ材" を指定すると腕木を強力つなぎ材（方杖付き）に替え、
    # capacity.csv の「支柱許容圧縮耐力[強力つなぎ材]」で検定する（日建ND: 11.0→17.0kN/本）。
    # 該当行が無い系列では検定で止まる（黙って通常値で通さない）
    post_reinforcement: str = ""
    guard_rail_height_mm: Optional[int] = None  # 直接指定する場合（枠組等）
    has_midrail: bool = True               # 中桟
    # 中桟高さ（作業床から。基準35〜50cm）。Noneなら系列から求める
    # （くさびは緊結部＝コマ位置にしか付かないので、450決め打ちだとB系列で25mmずれる）
    midrail_height_mm: Optional[int] = None
    has_toe_board: bool = True             # 幅木
    # 3Dを線だけで描く（計画初期・40m級の建物一周で軽くする。干渉確認は立体表現で）
    line_mode_3d: bool = False
    # 水平ネット（躯体と足場の隙間）を張る作業層。ネットブラケットは内側建地ごと（利用者の指定 2026-10-20）
    horizontal_net_levels: list = field(default_factory=list)
    # 層間ネットをネットブラケット（NL500）で受けるか。False なら建地・布材に直に結ぶ等、ブラケットを置かず数えない
    net_brackets: bool = True
    # 幅木を付けない指定のとき、作業床の外側に下さん（高さ15〜40cmの桟）を入れる（利用者の資料 2026-10-24: 幅木を
    # 使用しない場合、下さんは必要・層間ネットは全層に必要）
    shita_san: bool = False
    # 離れが目標上限を超える面に内ブラケット（躯体側に踏板）を自動で付ける
    auto_inner_bracket: bool = True
    toe_board_height_mm: int = 157         # 幅木高さ（落下物防止は10cm以上）
    n_stairs: int = 1                      # 階段設置箇所数
    wall_tie_span_step: int = 3            # 壁つなぎ水平間隔（スパン数、実務推奨3以内）
    wall_tie_level_step: int = 2           # 壁つなぎ垂直間隔（作業層数、実務推奨2以内）
    # 角から1.8m未満の支柱にも壁つなぎを入れるか（最密でも風荷重を満たせないときだけ最適化が使う。
    # 端のスパンが短いと角の手前の支柱が外れ、端の領域を1本で受ける形になった）
    wall_tie_near_corner: bool = False
    period_days: int = 60                  # 設置期間（届出要否判定）
    asagao: Optional["AsagaoSpec"] = None  # 朝顔（Noneなら未設置）

    @property
    def is_hug(self) -> bool:
        """単管抱き足場（建地1列を2本の布で抱き、その上に足場板）."""
        return self.scaffold_form == "一側足場" and self.single_row_kind == "抱き"

    @property
    def form_label(self) -> str:
        """帳票に書く足場の形式（一側足場はブラケット足場・抱き足場を呼び分ける）."""
        if self.scaffold_form != "一側足場":
            return self.scaffold_form
        if self.is_hug:
            return "単管抱き足場"
        if self.single_row_kind == "ブラケット":
            return f"ブラケット足場（{self.bracket_post}）"
        return "一側足場"


@dataclass
class WallTie:
    edge_index: int
    position_mm: float   # 辺の始点コーナー支柱からの距離
    height_mm: int       # GLからの高さ
    # 由来: grid（風荷重から決めた格子）／asagao（朝顔取付部）／stage（荷受け
    # ステージ取付部）／hoist（昇降機マストの控え）。数量・図面・検定で同じ一覧を使う
    kind: str = "grid"


@dataclass
class ScaffoldModel:
    master: PartMaster
    plan: PlanResult
    elevation: ElevationResult
    config: ScaffoldConfig = field(default_factory=ScaffoldConfig)
    building_height_mm: float = 0.0        # 建物高さ（架け面積・届出判定用）
    clearance_space_mm: float = 2000.0     # 躯体外面から確保できる水平スペース
    wall_ties: list[WallTie] = field(default_factory=list)
    # 面ごとの立面（セットバックで低い面。辺番号 → 全体の立面を軒高で切ったもの）。無い面は全体の立面
    face_elevations: dict = field(default_factory=dict)
    # 足場の立つ高さ（下の屋根の上に建てるとき。GL＝0 からの mm。図面・部品はこの高さに置く）
    base_height_mm: float = 0.0
    # 数量を面の組ごとに出すときの対象の面（None＝全部）。出隅の外側コーナーをこの面だけで数える
    edge_subset: Optional[set] = None
    # 足場を掛ける面（None＝全周）。一部の面だけのときは、隣の面が無い端が開放端になる
    faces_only: Optional[set] = None
    # ハッチ付布板（梯子内蔵）の昇降口 [(辺番号, スパンの番号 0〜)]。階段室が入らない小さい足場（stairs.place_hatch_ladders）
    hatch_ladders: list = field(default_factory=list)
    # ほかの組の本足場に繋いだ端（(辺, "s"|"e")。corner_joins）。開放端の妻側の手すりを付けない
    joined_ends: set = field(default_factory=set)
    # 面の区間だけ残した端（(辺, "s"|"e")。面の途中で足場の種類を切り替えた切れ目。face_forms の「南面[a-b]」）。開放端
    range_ends: set = field(default_factory=set)
    # 区間だけ残した面の、元の面の始点からの区間の始め・元の面の長さ mm（{辺: (始め, 長さ)}。部品を選んで切り替えるとき使う）
    face_offsets: dict = field(default_factory=dict)
    # ほかの組の本足場の隣の面で、出隅を同じ組の隅と同じに納める面（辺番号 → {"row": 建地列間隔 mm, "height": 高さ mm}）。
    # 南面だけ本足場（狭い幅）にした組で、隅の外側の升目が抜け、両方の面の端に妻側の手すりが付いて回れず、隅の内側
    # 建地が2本重なっていた（利用者の指摘 2026-10-24: 端部が重なったり、回れないようになってる）。cli.solve_groups が渡す
    group_neighbors: dict = field(default_factory=dict)
    # 仮囲いの高さ mm（足場の立つ面から）。外部シートはその天端から上に張る（利用者の指定 2026-10-24: 仮囲いまでにする）
    hoarding_height_mm: float = 3000.0
    # 入隅でつないだ面 [(隅で終わる面 A, 隅から始まる面 B, A の終点の隙間 mm)]。B を通し A は B の外側建地列で止める
    # （inner_corners）。隙間が無ければ A の終点の内側建地は B の始点の外側建地と同じ1本、B の最初のスパンは外側の
    # 手すり・幅木を付けない
    inner_corner_joins: list = field(default_factory=list)
    # 朝顔を付ける面（辺番号の集合。None＝全部の面）。AsagaoSpec.faces の面名から build_model が決める
    asagao_edges: Optional[set] = None
    # 面の一部だけに付ける朝顔（{辺番号: [(始め, 終わり), …]}。辺の始点の支柱から mm）。AsagaoSpec.faces の「南面[a-b]」から
    # build_model が決める（利用者の指定 2026-10-24: 線で朝顔の範囲追加できるようにして）
    asagao_ranges: dict = field(default_factory=dict)
    # 範囲を指定した部材の編集（外す・置換）。member_edits.MemberEdit の並び
    member_edits: list = field(default_factory=list)
    # かわした庇・バルコニーとセットバック（obstacles.Obstacle・Setback の並び）
    obstacles: list = field(default_factory=list)
    setbacks: list = field(default_factory=list)

    def _n_outline(self) -> int:
        return len(self.plan.outline.edges)

    def _no_prev(self, edge_index: int) -> bool:
        prev = (edge_index - 1) % self._n_outline()
        if (edge_index, "s") in self.range_ends:                 # 区間の切れ目は隅ではない
            return True
        if prev in self.group_neighbors:
            return False
        if (prev, "e") in self.range_ends:                       # 前の面はこの組では隅まで来ない
            return True
        return self.faces_only is not None and prev not in self.faces_only

    def _no_next(self, edge_index: int) -> bool:
        nxt = (edge_index + 1) % self._n_outline()
        if (edge_index, "e") in self.range_ends:
            return True
        if nxt in self.group_neighbors:
            return False
        if (nxt, "s") in self.range_ends:
            return True
        return self.faces_only is not None and nxt not in self.faces_only

    def row_spacing_of(self, edge_index: int) -> float:
        """その面の建地列間隔 mm（ほかの組の隣の面はその組の値。出隅の外側の升目の辺の長さ）."""
        nb = self.group_neighbors.get(edge_index)
        return float(nb["row"]) if nb else float(self.post_row_spacing_mm)

    def height_of(self, edge_index: int) -> float:
        """その面の足場の高さ mm（ほかの組の隣の面はその組の値）."""
        nb = self.group_neighbors.get(edge_index)
        return float(nb["height"]) if nb else float(self.elevation_of(edge_index).total_height)

    def open_start(self, edge_index: int) -> bool:
        """その面の始点が開放端か（一部の面だけの足場で、前の面を掛けない）.

        ほかの組の本足場に繋いだブラケットの面の端（corner_joins）は開放端ではない（本足場の床に続く）。
        """
        return self._no_prev(edge_index) and (edge_index, "s") not in self.joined_ends

    def open_end(self, edge_index: int) -> bool:
        """その面の終点が開放端か（次の面を掛けない）."""
        return self._no_next(edge_index) and (edge_index, "e") not in self.joined_ends

    def inner_join_start(self, edge_index: int) -> bool:
        """入隅でつないだ隅から始まる面か（inner_corners）. その始点の升目は躯体側に開くので妻側の手すり・幅木を付ける."""
        return any(b == edge_index for _a, b, _g in self.inner_corner_joins)

    def corner_kind_start(self, edge_index: int) -> str:
        """始点の隅の種類（出隅／入隅／空）。開放端・ほかの組に繋いだ端は隅として扱わない."""
        return "" if self._no_prev(edge_index) else self.plan.outline.edges[edge_index].start_corner

    def frame_gap_end_mm(self, edge_index: int) -> float:
        """枠組の面の終点の出隅で、建枠どうしの隙間 mm（単管で繋ぐ。0 は隙間なし・枠組でない・出隅でない）.

        枠組は離れを固定して余りを各面の終点の隅に出す（plan_solver._solve_plan_frame。70mm 以上）。建枠は隣の面の
        建枠と繋がらないので、隙間を単管（直交クランプ）で繋ぐ（利用者の指定 2026-10-24）。
        """
        if not self.master.is_frame or self.corner_kind_end(edge_index) != "出隅":
            return 0.0
        n = len(self.plan.outline.edges)
        for c in getattr(self.plan, "corner_steps", None) or []:
            if c.edge_index < 0 and c.corner_index == (edge_index + 1) % n:
                return float(c.gap_mm)
        return 0.0

    def corner_kind_end(self, edge_index: int) -> str:
        return "" if self._no_next(edge_index) else self.plan.outline.edges[edge_index].end_corner

    def elevation_of(self, edge_index: int) -> ElevationResult:
        """その面の立面（面ごとの高さが無ければ全体）."""
        return self.face_elevations.get(edge_index, self.elevation)

    def clip_ties_to_faces(self) -> int:
        """面ごとの高さより上の壁つなぎを外す（低い面に、高い面の層の壁つなぎを残さない）。外した数を返す."""
        if not self.face_elevations:
            return 0
        keep = []
        for t in self.wall_ties:
            lv = self.elevation_of(t.edge_index).level_heights
            if not lv or t.height_mm <= lv[-1] + 1:
                keep.append(t)
        n = len(self.wall_ties) - len(keep)
        self.wall_ties = keep
        return n

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

    def asagao_on(self, edge_index: int) -> bool:
        """その面に朝顔を付けるか（段数があり、付ける面に入っている）."""
        a = self.config.asagao
        return bool(a is not None and a.stages > 0
                    and (self.asagao_edges is None or edge_index in self.asagao_edges
                         or bool(self.asagao_ranges.get(edge_index))))

    def asagao_parts(self, edge_index: int) -> Optional[list]:
        """その面の朝顔を付ける区間 [(始め, 終わり)]（辺の始点の支柱から mm、昇順・重なりなし）。面全体なら None、付けなければ []."""
        if not self.asagao_on(edge_index):
            return []
        if self.asagao_edges is None or edge_index in self.asagao_edges:
            return None
        ep = next((e for e in self.plan.edges if e.edge_index == edge_index), None)
        length = float(sum(ep.spans)) if ep is not None else float("inf")
        out: list = []
        for a, b in sorted(self.asagao_ranges.get(edge_index) or []):
            a, b = max(0.0, float(a)), min(length, float(b))
            if b <= a + 1.0:
                continue
            if out and a <= out[-1][1] + 1.0:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        return out

    def asagao_at(self, edge_index: int, x_mm: float) -> bool:
        """面の始点から x_mm の位置に朝顔が付くか（区間の端も含む）."""
        parts = self.asagao_parts(edge_index)
        return parts is None or any(a - 1.0 <= x_mm <= b + 1.0 for a, b in parts)

    def asagao_reaches(self, edge_index: int, at_end: bool) -> bool:
        """その面の朝顔が隅（始点か終点）まで来ているか（出隅のコーナー部を付けるか）."""
        parts = self.asagao_parts(edge_index)
        if parts is None:
            return True
        if not parts:
            return False
        if not at_end:
            return parts[0][0] < 1.0
        ep = next((e for e in self.plan.edges if e.edge_index == edge_index), None)
        return ep is not None and parts[-1][1] > float(sum(ep.spans)) - 1.0

    def asagao_heights_of(self, edge_index: int) -> list[int]:
        """その面の朝顔の高さ（付けない面は空）."""
        return self.asagao_heights() if self.asagao_on(edge_index) else []

    def asagao_heights(self) -> list[int]:
        """朝顔の設置高さ（GLから、下から昇順）.

        法は段数（10m以上1段・20m以上2段）と突出・傾斜を定めるが、高さは
        定めていない。実務では「1段目は地上4〜5m、2段目以降は1段目から
        10m以内ごと」に取るので、その範囲に最も近い作業床の高さを選ぶ。
        AsagaoSpec.heights_mm を指定すればそちらを優先する。
        """
        spec = self.config.asagao
        if spec is None or spec.stages <= 0:
            return []
        if spec.heights_mm:
            return sorted(int(h) for h in spec.heights_mm)
        levels = self.elevation.level_heights
        if not levels:
            return []
        out: list[int] = []
        target = (ASAGAO_FIRST_MIN_MM + ASAGAO_FIRST_MAX_MM) / 2
        for _ in range(spec.stages):
            cands = [h for h in levels if h not in out]
            if not cands:
                break
            out.append(min(cands, key=lambda h: abs(h - target)))
            target = out[-1] + ASAGAO_STAGE_PITCH_MM
        return sorted(out)

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
        if self.config.is_hug:
            # 単管抱き足場は建地を両側から布2本（単管）で抱き、その布が床になる（利用者の指定 2026-10-22: 布板不要）。
            # 建地列は離れの線の上（列間隔 0）。以前は線から 100 外に立て、出隅で隣の面の端の建地・コーナー支柱と
            # 3本並んでいた（利用者の指定 2026-10-22: 出隅の建地は1本にまとめて）。線の上なら隣の面と同じ1本
            return 0
        if self.master.is_frame:
            return self.master.frame_width_for(self.deck_width_total)[0]
        if self.master.is_tube and self.config.scaffold_form == "一側足場":
            # 単管のブラケット足場の腕は単管ブラケット。足場板の幅以上でいちばん短いブラケット（数量と同じ品）
            brk = [p.nominal_dim for p in self.master.by_category("ブラケット") if p.nominal_dim >= self.deck_width_total]
            if brk:
                return min(brk)
        if self.master.is_tube:
            # 単管の腕木は建地に外からクランプで留めるので、作業床の幅以上でいちばん短い単管
            wide = [p.nominal_dim for p in self.master.by_category("布材") if p.nominal_dim >= self.deck_width_total]
            if wide:
                return min(wide)
        # 作業床を載せられる範囲で最大の腕木（布材）
        cands = [
            p.nominal_dim for p in self.master.by_category("布材")
            if p.nominal_dim <= self.deck_width_total
        ]
        return max(cands) if cands else self.deck_width_total

    @property
    def deck_widths_in_use(self) -> tuple[int, ...]:
        """実際に敷く作業床の幅.

        一側足場は建地1列でブラケット受けの1枚敷きになる。マスタ既定の
        内外2枚（400+250など）をそのまま使うと、数量も図面も法規チェックの
        床幅も本足場のものになってしまう。
        """
        ws = tuple(self.config.deck_widths or ())
        # 単管抱き足場は布板を敷かない（抱き合わせた単管2本が床。利用者の指定 2026-10-22）
        if self.config.is_hug:
            return ()
        # 枠組は建枠が内外2列を成すので一側にはできない（法規チェック1でNG）。
        # ここで幅を1枚に落とすと、建枠幅まで細くなって矛盾が広がる
        if (self.config.scaffold_form == "一側足場"
                and not self.master.is_frame and len(ws) > 1):
            # 単管のブラケット足場も足場板（幅240）1列（利用者の指定 2026-10-22: 足場板は2列じゃなく1列）
            return (max(ws),)
        return ws

    @property
    def deck_width_total(self) -> int:
        ws = self.deck_widths_in_use
        return sum(ws) + self.config.deck_gap_mm * (len(ws) - 1)

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
        if self.master.is_tube:
            return TUBE_GUARD_RAIL_HEIGHT_MM      # 単管の手すりはどの高さにもクランプで付く
        return self.config.guard_rail_koma * self.master.koma_pitch

    @property
    def guard_rail_method(self) -> str:
        """帳票に書く手すり方式の説明.

        枠組は中間層の手すりを建枠自体が兼ね、最上層だけ布材で組む。
        guard_rail_type（布材／先行手すり）はくさび式の選択肢なので、
        枠組でそのまま書くと「布材で全層手すり」と誤読される。
        """
        if self.master.is_frame:
            return "建枠一体（最上層のみ布材で手すり・中桟）"
        return self.config.guard_rail_type

    @property
    def midrail_height_mm(self) -> int:
        """作業床からの中桟高さ.

        くさび式の中桟は緊結部（コマ）にしか取り付かないので、コマピッチの
        整数倍になる（A:450＝1コマ、B:475＝1コマ）。450決め打ちにすると、
        B系列で図面も帳票も実際と25mmずれる。
        """
        if self.config.midrail_height_mm is not None:
            return self.config.midrail_height_mm
        if self.master.is_frame:
            return FRAME_MIDRAIL_HEIGHT_MM
        if self.master.is_tube:
            return TUBE_MIDRAIL_HEIGHT_MM
        return self.master.koma_pitch

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

    def face_name(self, edge_index: int) -> str:
        """辺番号 → 面の呼び名（南面など）。図面・帳票で人に見せる側に使う."""
        names = self.plan.face_names()
        for e, n in zip(self.plan.edges, names):
            if e.edge_index == edge_index:
                return n
        return f"辺{edge_index}"

    @property
    def stair_half_deck(self) -> bool:
        """階段を外側に寄せ、内側の床（ハーフアンチ）を残すか.

        利用者の指摘（2026-10-22: 914幅の階段、階段外側に寄せて、上にハーフアンチいるよ）。くさびの本足場で床が
        2枚（外側の広い板＋内側の細い板。日建914幅は 500＋240）のとき、階段枠（外幅 481）は外側の板の幅に収まる
        ので外側に寄せ、階段が上がってくる層でも内側の板（ハーフアンチ）は敷いて通れるようにする。
        """
        ws = self.deck_widths_in_use
        return (not self.master.is_frame and not self.master.is_tube and self.config.scaffold_form == "本足場"
                and len(ws) == 2 and ws[0] >= STAIR_FRAME_WIDTH_MM)

    @property
    def no_stair_tower(self) -> bool:
        """階段が入らない足場の形式. 単管抱き足場（布2本の床）と、ブラケット足場（一側。床は 1 列）.

        利用者の指摘（2026-10-22）: 単管のブラケット足場に階段はつけれない。2026-10-23: くさびのブラケットの足場にも
        階段はつけれない寸法（床 400 に階段枠 450 は入らない）。昇降はほかの面の階段か、はしご等を別に（入力 ladders）
        """
        return self.config.is_hug or self.config.scaffold_form == "一側足場"

    @property
    def tie_post_offset_mm(self) -> float:
        """壁つなぎを取る建地の、離れの線から外への距離. 建地1列（一側・ブラケット足場）は外側の列（列間隔）、
        本足場は内側の列（0）。利用者の指摘（2026-10-22）: 壁繋ぎは単管支柱から取るように（線の上から描いて浮いていた）
        """
        if self.config.scaffold_form != "一側足場" or self.master.is_frame:     # 建枠は一側にできない（2列のまま）
            return 0.0
        return float(self.post_row_spacing_mm)

    def outer_corner_posts(self) -> int:
        """出隅の外側コーナー支柱の本数.

        内側建地列は隣の面とコーナー支柱を共有するが、外側建地列は面ごとに躯体コーナーで
        終わるので、四隅の外側に1本ずつ立つ。3D・数量・構造（立っている本数）で同じ値を使う。
        一側足場も建地列が躯体コーナーで終わるのは同じなので付く。枠組（建枠を回して
        納める）には無い。単管抱き足場も無い（建地列が離れの線の上で、出隅の建地は隣の面と同じ1本）。
        """
        if self.master.is_frame or self.config.is_hug:
            return 0
        return len([e for e in self.plan.outline.edges if self.corner_kind_start(e.index) == "出隅"
                    and (self.edge_subset is None or e.index in self.edge_subset)
                    and (self.faces_only is None or e.index in self.faces_only)])

    def gap_corner_post_start(self, edge_index: int) -> bool:
        """始点の出隅で、前の面が隅の隙間（コーナーステップ）の手前で止まるか.

        そのときは出隅の外側の升目の前の面の側（前の面の外側列の延長の根元）に建地が要る（前の面の終点の建地は隙間の
        向こう）。升目は4本の建地と、その側の布材（根がらみ＋各層の床）で独り立ちする。利用者の指摘 2026-10-24:
        コーナー部分の支柱がない部分がある。3D・平面・数量で同じ規則を使う。
        """
        if self.master.is_frame or self.config.is_hug or self.corner_kind_start(edge_index) != "出隅":
            return False
        prev = (edge_index - 1) % self._n_outline()
        return any(c.edge_index == prev and not getattr(c, "at_start", False)
                   for c in getattr(self.plan, "corner_steps", None) or [])

    def gap_corner_posts(self) -> int:
        """隙間のある出隅に足す建地の本数（gap_corner_post_start の面の数。面を絞った数量ではその面だけ）."""
        return len([e for e in self.plan.outline.edges if self.gap_corner_post_start(e.index)
                    and (self.edge_subset is None or e.index in self.edge_subset)
                    and (self.faces_only is None or e.index in self.faces_only)])

    def outer_corner_prev_widths(self) -> list[float]:
        """出隅の外側コーナーごとの、前の面の建地列間隔 mm（outer_corner_posts と同じ隅の並び）.

        同じ組の隅はこの組の建地列間隔。ほかの組の幅の違う本足場と出会う隅は、升目がその幅×この面の幅の長方形になる。
        """
        if self.master.is_frame or self.config.is_hug:
            return []
        n = self._n_outline()
        return [self.row_spacing_of((e.index - 1) % n) for e in self.plan.outline.edges
                if self.corner_kind_start(e.index) == "出隅"
                and (self.edge_subset is None or e.index in self.edge_subset)
                and (self.faces_only is None or e.index in self.faces_only)]

    def edges_without_wall_ties(self) -> list[int]:
        """壁つなぎが1本も無い辺の番号.

        短い面は支柱が足りず壁つなぎを入れられないことがある。その面は
        両隣の面の壁つなぎにコーナー経由で支持される前提になるが、
        構造計算はその面の風荷重を誰にも負担させていない。黙って通さない
        ために取り出せるようにしておく。
        """
        has = {t.edge_index for t in self.wall_ties}
        return [e.edge_index for e in self.plan.edges if e.edge_index not in has]

    def wall_tie_max_spacing(self, exclude_unreachable: bool = True) -> tuple[float, float]:
        """壁つなぎの実配置から(垂直最大, 水平最大)間隔[mm]を返す.

        exclude_unreachable: 渡した区間（凹み・斜辺）の深い所は最長の壁つなぎでも
        躯体に届かず、単管等の別途の控えで固定する帯。その帯は控えで拘束される前提で
        水平間隔の計算から除く（帯の両端を拘束点として数える）。
        """
        if not self.wall_ties:
            return (float("inf"), float("inf"))
        bands: dict[int, list[tuple[float, float]]] = {}
        if exclude_unreachable:
            try:
                from .ties import unreachable_bands

                bands = unreachable_bands(self)
            except Exception:
                bands = {}
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
                # 壁つなぎが1本も無い面は、その面全体が1つの間隔になる。
                # 1スパン以下の面（回し・小さな張り出し）は両隣で拘束される
                if e.spans and e.scaffold_length > max(e.spans):
                    h_max = max(h_max, e.scaffold_length)
                continue
            # 届かない帯の両端は控えの拘束点。帯の内側（a〜b）は間隔として数えない
            edge_bands = bands.get(e.edge_index, [])
            points = sorted(set(xs) | {a for a, _b in edge_bands} | {b for _a, b in edge_bands})
            prev_x = 0.0
            for x in points:
                inside = any(a - 1e-6 <= prev_x and x <= b + 1e-6 for a, b in edge_bands)
                if not inside:
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
        if config.wall_tie_near_corner:
            candidates = list(interior)
        else:
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
        # 最後の壁つなぎから面の端までが step スパンより空くなら1本足す。
        # 1800決め打ちにすると、B系列(1829)や枠組(1829)で判定がずれる
        span_ref = max(e.spans) if e.spans else 1800
        # （最後の候補が既に選ばれているときは足さない。1スパン毎のとき同じ支柱に2本入り、
        # 数量が二重になり、検定でも受け持ちが割れていた）
        if picked and (e.scaffold_length - picked[-1]) > step * span_ref and acc[idxs[-1]] not in picked:
            picked.append(acc[idxs[-1]])
        for h in tie_levels:
            for x in picked:
                ties.append(WallTie(edge_index=e.edge_index, position_mm=x, height_mm=h))
    return ties
