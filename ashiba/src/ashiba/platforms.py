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

import re

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
    # 侵入落下防止柵（利用者の指定 2026-10-24。GLOOBE の「荷受けステージと侵入落下防止柵」）: ステージの先端・妻側に
    # 金網の落下防止柵（荷が手すりの間から落ちない）、足場側の間口に開閉式の侵入防止柵（荷の取り込み中に人が出ない）
    has_fence: bool = True
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


HOIST_FENCE_GAP_MM = 300.0  # 地上の昇降路の囲いと荷台のあき
HOIST_FENCE_H_MM = 1800.0    # 地上の昇降路の囲いの高さ
HOIST_CAGE_W_MM = 4600.0     # ロングスパン建設用リフトの荷台の長さ（面に沿って。既定）
GATE_MIN_OVERLAP_MM = 150.0  # 荷台がこれ以下しか掛からないスパンは乗り込み口にしない
HOIST_CAGE_D_MM = 1300.0     # 荷台の奥行（既定）


def spans_under_cage(spans, center_mm: float, cage_len_mm: float) -> list[int]:
    """荷台（中心 center_mm・長さ cage_len_mm）が掛かるスパン（0 始まり）＝乗り込み口で手すりを外すスパン.

    荷台の端がスパンに少し掛かるだけ（搬器の枠の厚み程度）なら、そのスパンの手すりは外さない。乗り込む扉は荷台の
    端より内側にある。1850 の搬器が 1829 のスパンの両隣に 10 ずつ掛かって 3 スパン（5.5m）も開けていた
    """
    posts = [0.0]
    for sp in spans:
        posts.append(posts[-1] + float(sp))
    lo, hi = center_mm - cage_len_mm / 2.0, center_mm + cage_len_mm / 2.0
    return [k for k in range(len(spans)) if min(posts[k + 1], hi) - max(posts[k], lo) > GATE_MIN_OVERLAP_MM]


def fewest_gate_spans_center(spans, center_mm: float, cage_len_mm: float, reach_mm: float) -> float:
    """center_mm から reach_mm 以内の建地の芯・スパンの中央のうち、乗り込み口のスパンがいちばん少ない位置（同数なら近い方）.
    荷台が面からはみ出す位置は採らない。候補が無ければ center_mm のまま."""
    posts = [0.0]
    for sp in spans:
        posts.append(posts[-1] + float(sp))
    half = cage_len_mm / 2.0
    cands = [c for c in sorted(set(posts) | {(a + b) / 2.0 for a, b in zip(posts, posts[1:])})
             if abs(c - center_mm) <= reach_mm and c - half >= 0.0 and c + half <= posts[-1]]
    if not cands:
        return center_mm
    return min(cands, key=lambda c: (len(spans_under_cage(spans, c, cage_len_mm)), abs(c - center_mm)))


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
    # 荷台の見付け（面に沿った長さ×奥行。ロングスパン建設用リフトの荷台は 3〜10m と長く、両端にマスト。機種で違うので
    # 既定は図示用の 4.6×1.3m。日本建設機械施工協会「建設用リフト」図2.4.8・2.4.9）と積載荷重
    cage_width_mm: float = HOIST_CAGE_W_MM
    cage_depth_mm: float = HOIST_CAGE_D_MM
    load_kn: float = 0.0            # 積載荷重（0=未指定。設置届/設置報告の要否判定に使う）
    # 機種（data/hoist_models.csv の model_id。指定すれば荷台・積載・壁つなぎ間隔・マスト間隔・揚程・フロアーゲートが入る）
    model_id: str = ""

    def gate_spans(self, model: ScaffoldModel) -> list[int]:
        """乗り込み口の開閉式手すりを付けるスパン（0 始まり）: 荷台の長さ（位置を中心に）に掛かるスパン（3D と同じ）."""
        edge = _edge(model, self.edge_index)
        if edge is None or not edge.spans:
            return []
        return spans_under_cage(edge.spans, self.position_mm, float(self.cage_width_mm or HOIST_CAGE_W_MM))

    @property
    def spec(self):
        """機種（hoist_models.HoistModel）. 機種の指定が無ければ None."""
        from .hoist_models import hoist_model

        return hoist_model(self.model_id)

    def reach_mm(self, model: ScaffoldModel) -> float:
        """到達高さ（足場の立つ面から mm）. 指定が無ければ昇降機の立つ面の足場の高さ（面ごとに高さが違えばその面の）."""
        return float(self.reach_height_mm or model.elevation_of(self.edge_index).total_height)

    def level_heights(self, model: ScaffoldModel) -> list:
        """昇降機の立つ面の作業層の床の高さ（面ごとの高さ。部品の配置・壁つなぎと同じ）."""
        return model.elevation_of(self.edge_index).level_heights

    def landings(self, model: ScaffoldModel) -> list[int]:
        n = model.elevation_of(self.edge_index).n_levels
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


# 荷取りステージ（スギコ アルバロングスパンEV荷取用金具 50500 のカタログ: 許容荷重 500kg/個、ステージ上の全積載 800kg 以下、
# 梁枠は 2・3 スパン、布材は上部フランジに 1829 ピッチ。利用者が渡した PDF 2026-10-27）
LANDING_FITTING_KG = 500.0
LANDING_FITTINGS_PER_STAGE = 4
LANDING_STAGE_MAX_KG = 800.0
LANDING_BEAM_SPANS = (2, 3)
LANDING_LEDGER_PITCH_MM = 1829.0
FRAME_TOL_MM = 60.0     # ロングスパンの枠組間隔と足場のスパンの続きの合計の許容差（インチ 3×1829＝5487 と 5490 は同じ）


def frame_runs(spans, frame_mm: float) -> list[tuple[int, int, float]]:
    """足場のスパンの続き（i〜j）で、合計がロングスパンの枠組間隔に合うもの → [(i, j, 区間の中心 mm)].

    ロングスパンは足場の建枠（建地）の間に組む（枠組間隔 3600・5400・7200＝1800 の 2・3・4 スパン。インチの足場では
    3660・5490・7320＝1829 の 2・3・4 スパン）。機種表の枠組間隔はメートルの値なので、インチ換算（×1829/1800）でも見る。
    """
    posts = [0.0]
    for sp in spans:
        posts.append(posts[-1] + float(sp))
    targets = (float(frame_mm), float(frame_mm) * 1829.0 / 1800.0)
    out = []
    for i in range(len(spans)):
        for j in range(i, len(spans)):
            ln = posts[j + 1] - posts[i]
            if any(abs(ln - t) <= FRAME_TOL_MM for t in targets):
                out.append((i, j, (posts[i] + posts[j + 1]) / 2.0))
            if ln > max(targets) + FRAME_TOL_MM:
                break
    return out


def frame_center(model: ScaffoldModel, h) -> Optional[float]:
    """ロングスパンの昇降機の、枠組の両端が足場の建地に乗る位置（いちばん近い区間の中心 mm）. 合う区間が無い・
    ロングスパンでなければ None."""
    hm = h.spec
    edge = _edge(model, h.edge_index)
    if hm is None or hm.kind != "ロングスパン" or hm.frame_span_mm <= 0 or edge is None:
        return None
    runs = frame_runs(edge.spans, hm.frame_span_mm)
    if not runs:
        return None
    return min((c for _i, _j, c in runs), key=lambda c: abs(c - h.position_mm))


def _gate_fit_position(model: ScaffoldModel, h, limit_mm: float) -> Optional[tuple[float, int, float]]:
    """乗り込み口の開口（手すりを外すスパンの合計）が limit_mm 以下になる位置 → (位置, スパン数, 開口). いちばん近いもの.

    候補は建地の芯とスパンの中央（荷台の中心をそこに合わせる）。荷台が面からはみ出す位置は採らない。ロングスパンで
    枠組を建地に乗せる位置が決まっている機種は、その位置しか取れないので探さない（frame_center の指摘に任せる）。
    """
    from dataclasses import replace

    edge = _edge(model, h.edge_index)
    hm = h.spec
    if edge is None or not edge.spans or (hm is not None and hm.kind == "ロングスパン" and hm.frame_span_mm > 0):
        return None
    posts = [0.0]
    for sp in edge.spans:
        posts.append(posts[-1] + float(sp))
    half = float(h.cage_width_mm or HOIST_CAGE_W_MM) / 2.0
    cands = sorted(set(posts) | {(a + b) / 2.0 for a, b in zip(posts, posts[1:])}, key=lambda c: abs(c - h.position_mm))
    for c in cands:
        if c - half < 0 or c + half > posts[-1]:
            continue
        gs = replace(h, position_mm=c).gate_spans(model)
        opening = sum(float(edge.spans[k]) for k in gs)
        if gs and opening <= limit_mm:
            return c, len(gs), opening
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
                f"{model.face_name(s.edge_index)}: 位置{s.start_mm:.0f}mmから"
                f"{s.span_count}スパンは面（{edge.scaffold_length:.0f}mm・"
                f"{edge.span_count}スパン）に収まりません", "入力エラー"))

        uplift = stage_inner_uplift_kn(s, model)
        if uplift > result.max_inner_uplift_kn:
            result.max_inner_uplift_kn = uplift
            result.uplift_governing = (
                f"{model.face_name(s.edge_index)} 始点から{s.start_mm:.0f}mm（出{s.projection_mm:.0f}mm）"
            )
        load = stage_post_load_kn(s, model)
        if load > result.max_post_load_kn:
            result.max_post_load_kn = load
            result.governing = (
                f"{model.face_name(s.edge_index)} 始点から{s.start_mm:.0f}mm "
                f"（間口{s.span_count}スパン・出{s.projection_mm:.0f}mm・"
                f"積載{s.load_kn:.1f}kN）"
            )
        # 受けブラケット1本の荷重 ≦ ブラケットの許容荷重。出で選んだ部材が
        # 積載に耐えるかは別の話で、枠組の伸縮ブラケット（許容1.96kN）に
        # 1tのステージを受けさせても、ここで見なければ通ってしまう
        n_brk = s.span_count + 1
        per_bracket = s.load_kn / n_brk
        brk = stage_bracket_part(model, s.projection_mm)
        if brk is not None:
            allow = bracket_allowable_kn(brk)
            if allow is None:
                result.issues.append(PlatformIssue(
                    "ステージ", i, "WARN",
                    f"受けブラケット {brk.model_no} の許容荷重がマスタに無く、"
                    f"1本あたり{per_bracket:.2f}kN（積載{s.load_kn:.1f}kN÷{n_brk}本）の検定ができません。"
                    "メーカー値で確認してください", "仮設工業会 設計指針"))
            elif per_bracket > allow + 1e-9:
                result.issues.append(PlatformIssue(
                    "ステージ", i, "NG",
                    f"受けブラケット {brk.model_no} の許容荷重{allow:.2f}kN/本に対し"
                    f"1本あたり{per_bracket:.2f}kN（積載{s.load_kn:.1f}kN÷{n_brk}本）で超過します。"
                    "荷取り用のブラケットに替えるか、積載を下げるか、間口を広げてください",
                    "仮設工業会 設計指針（部材の許容荷重）"))
            # 1本あたりが通っても、スパン当たりの上限（日建 荷取りブラケット 6.86kN/スパン）を
            # 超えることがある（間口1スパンに1t → 4.9kN/本は可、9.8kN/スパンは不可）
            span_allow = bracket_span_allowable_kn(brk)
            per_span = s.load_kn / max(1, s.span_count)
            if span_allow is not None and per_span > span_allow + 1e-9:
                result.issues.append(PlatformIssue(
                    "ステージ", i, "NG",
                    f"受けブラケット {brk.model_no} のスパン当たり許容荷重{span_allow:.2f}kNに対し"
                    f"1スパンあたり{per_span:.2f}kN（積載{s.load_kn:.1f}kN÷間口{s.span_count}スパン）で"
                    "超過します。間口を広げるか、積載を下げてください",
                    "メーカー使用基準（荷取りブラケット スパン当たり許容荷重）"))
        # ステージ取付部は壁つなぎを増設する（間口の両端）
        # 間口の各支柱（スパン数+1）に、ブラケットの上下で2箇所（ties._platform_ties と同じ数え方）
        result.extra_wall_ties += 2 * (s.span_count + 1) * max(1, len(s.levels) or 1)

    # 同じ区間に2基は取り付かない。重なりを黙って通すと部材も軸力も二重になる
    for i, a in enumerate(stages):
        for j, b in list(enumerate(stages))[i + 1:]:
            if a.edge_index != b.edge_index:
                continue
            if a.start_mm < b.end_mm(model) and b.start_mm < a.end_mm(model):
                result.issues.append(PlatformIssue(
                    "ステージ", j, "NG",
                    f"{model.face_name(a.edge_index)}でステージ{i + 1}と{j + 1}の間口が重なっています"
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
        # 層数・足場高さは昇降機の立つ面のもの（面ごとに高さが違う建物で、高い面の層を低い面に許していた）
        face_ev = model.elevation_of(h.edge_index)
        bad_levels = [lv for lv in h.landing_levels if not (1 <= lv <= face_ev.n_levels)]
        if bad_levels:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG",
                f"乗り込み口の作業層{bad_levels}は存在しません（1〜{face_ev.n_levels}）。"
                "指定した層の乗り込み口は計上されません", "入力エラー"))
        reach = h.reach_mm(model)
        if reach > face_ev.total_height:
            result.issues.append(PlatformIssue(
                "昇降機", i, "WARN",
                f"到達高さ{reach:.0f}mmが足場高さ{face_ev.total_height}mmを超えます。"
                "マスト頂部の控えを別途検討してください",
                "工事用エレベータ構造規格"))
        hm = h.spec
        # 機種の揚程（最大）を超える高さは、その機種では昇れない（マストを継ぎ足しても届かない）
        if hm is not None and hm.max_lift_m > 0 and reach > hm.max_lift_m * 1000.0 + 1e-6:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG",
                f"到達高さ{reach:.0f}mmが機種 {hm.name} の最大揚程{hm.max_lift_m:.0f}mを超えます。"
                "揚程の高い機種に替えてください", "メーカーの仕様"))
        # 到達高さより上の作業層は、搬器が届かないので乗り込めない（到達高さを下げて入力したとき、乗り込み口だけ残っていた）
        levels = h.level_heights(model)
        above = [lv for lv in h.landings(model) if float(levels[lv - 1]) > reach + 1e-6]
        if above:
            result.issues.append(PlatformIssue(
                "昇降機", i, "NG",
                f"乗り込み口の作業層{above}（床の高さ{float(levels[above[0] - 1]):.0f}mm〜）が到達高さ{reach:.0f}mmより上で、"
                "搬器が届きません。到達高さを上げるか、乗り込む層から外してください", "入力エラー"))
        # フロアーゲートの大きさで塞げる開口か。乗り込み口は荷台の長さに掛かるスパン全部で足場の手すりを外すので、
        # 開口がゲートのスパンより広いと両端が開いたままになる
        if hm is not None and hm.gate:
            from .hoist_models import FLOOR_GATES

            fg = FLOOR_GATES.get(hm.gate)
            gs = h.gate_spans(model)
            opening = sum(float(edge.spans[k]) for k in gs)
            # 片側 100 までは単管クランプの掛かり（建地への留め位置）で納まる。インチの 4 スパン 7316 に 7.2 スパンは片側 58
            if fg and opening > fg["span_mm"] + 200.0:
                # ずらせばゲートの幅に収まる位置（建地の芯か、スパンの中央）を探して示す
                better = _gate_fit_position(model, h, fg["span_mm"] + 200.0)
                move = (f"昇降機の位置を{h.position_mm:.0f}mm から {better[0]:.0f}mm にずらせば{better[1]}スパン"
                        f"（{better[2]:.0f}mm）に収まります。" if better is not None
                        else "枠組を建地に乗せる位置は動かせません。" if hm.kind == "ロングスパン" and hm.frame_span_mm > 0
                        else "昇降機の位置をずらしてもスパンは減りません。")
                result.issues.append(PlatformIssue(
                    "昇降機", i, "WARN",
                    f"乗り込み口の開口{opening:.0f}mm（{len(gs)}スパン）が{fg['name']}の幅{fg['span_mm']:.0f}mmより"
                    f"広く、両端に{(opening - fg['span_mm']) / 2:.0f}mmずつ手すりの無いすき間が残ります。"
                    + move + "ずらせなければ残りを単管の手すりで塞いでください",
                    "安衛則第519条（開口部の囲い）"))
        # ロングスパンは足場の建枠の間に組む。枠組の両端が建地に乗る位置でないと、ガーダ（荷台の受け）が掛からない
        if hm is not None and hm.kind == "ロングスパン" and hm.frame_span_mm > 0:
            fc = frame_center(model, h)
            if fc is None:
                result.issues.append(PlatformIssue(
                    "昇降機", i, "WARN",
                    f"{model.face_name(h.edge_index)}のスパン割りに、機種 {hm.name} の枠組間隔{hm.frame_span_mm:.0f}mm に"
                    "合う続きのスパンがありません。枠組の両端が足場の建地に乗らないので、スパン割りか機種を見直してください",
                    "メーカーの組立要領"))
            elif abs(fc - h.position_mm) > 50.0:
                result.issues.append(PlatformIssue(
                    "昇降機", i, "WARN",
                    f"機種 {hm.name} の枠組（{hm.frame_span_mm:.0f}mm）の両端が足場の建地に乗りません。位置を"
                    f"{h.position_mm:.0f}mm から {fc:.0f}mm にしてください", "メーカーの組立要領"))
        # 荷取りステージ（荷取用金具＋梁枠）の決め: 梁枠は 2・3 スパン、ステージ上の全積載 800kg 以下
        # （スギコ アルバロングスパンEV荷取用金具 50500 の使用上の注意）
        if hm is not None and hm.kind == "ロングスパン" and h.landings(model):
            gs = h.gate_spans(model)
            if len(gs) not in LANDING_BEAM_SPANS:
                result.issues.append(PlatformIssue(
                    "昇降機", i, "WARN",
                    f"乗り込み口が{len(gs)}スパンに掛かり、荷取りステージの梁枠（2・3スパン）が掛けられません。"
                    "昇降機の位置か機種を見直すか、荷取りステージを別に計画してください",
                    "荷取用金具の使用上の注意（梁枠は2・3スパン）"))
            if hm.load_kg > LANDING_STAGE_MAX_KG:
                result.issues.append(PlatformIssue(
                    "昇降機", i, "WARN",
                    f"機種 {hm.name} の積載{hm.load_kg:.0f}kgは、荷取りステージ上の全積載{LANDING_STAGE_MAX_KG:.0f}kgを"
                    "超えます。満載の荷を一度にステージへ降ろさず、ステージに最大積載荷重を表示してください",
                    "荷取用金具の使用上の注意・安衛則第655条（最大積載荷重の表示）"))
        # 荷揚げ専用の機種は人が乗れない。乗り込み口は荷の受け取り口で、人は階段で上がる
        if hm is not None and hm.persons == 0:
            result.issues.append(PlatformIssue(
                "昇降機", i, "WARN",
                f"機種 {hm.name} は荷揚げ専用で人は乗れません。乗り込み口は荷の受け取り口として、"
                "開口部は開閉式手すりで塞ぎ、搬器への立入りを禁止する表示をしてください",
                "メーカーの仕様・安衛則第519条（開口部の囲い）"))
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
                    f"{model.face_name(h.edge_index)}で昇降機{j + 1}と{i + 1}が同じ位置"
                    f"（{other.position_mm:.0f}mmと{h.position_mm:.0f}mm）に重なっています",
                    "入力エラー"))
        # マスト控えの壁つなぎ
        # マスト控えの壁つなぎ（マストごと。機種が無ければ荷台の両端の2本。ties._attachment_ties と同じ）
        n_masts = hm.masts if hm is not None else 2
        n_ties = max(1, int(reach // h.tie_every_mm)) * n_masts
        result.extra_wall_ties += n_ties
        result.issues.append(PlatformIssue(
            "昇降機", i, "WARN",
            f"昇降機本体の基礎・構造は本ツールの対象外です。"
            f"マスト控えの壁つなぎ{n_ties}箇所（マスト{n_masts}本）を計上しました",
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
        if s.has_guard_rail:
            # 先端の手すり・中桟を受ける支柱（張出ブラケット先端の建地受けに立てる短い支柱）。
            # 3Dで手すりが宙に浮いていて、数量にも無かった（実機の小型面で確認）
            post = _rail_post_nominal(model)
            out.append(PartDemand(
                "荷受けステージ 先端手すり支柱", "支柱", post, n_posts * n_levels,
                detail="張出ブラケット先端に立て、先端の手すり・中桟を受ける",
            ))
        if s.has_fence:
            # 侵入落下防止柵: 先端・妻側は金網の柵（1枚の幅 FENCE_PANEL_MAX_MM 以下で割る）、足場側の間口はスパンごとの
            # 開閉式の柵。3D・平面と同じ枚数
            n_front, n_side, n_gate = stage_fence_panels(model, s)
            out.append(PartDemand(
                "荷受けステージ 落下防止柵（金網）", "落下防止柵", None, (n_front + n_side) * n_levels,
                detail=f"先端{n_front}枚・妻側{n_side}枚×{n_levels}層、高さ{FENCE_HEIGHT_MM:.0f}（荷が手すりの間から落ちない）",
            ))
            out.append(PartDemand(
                "荷受けステージ 侵入防止柵（開閉式）", "侵入防止柵", None, n_gate * n_levels,
                detail=f"足場側の間口の扉{n_gate}枚（足場の床の中へ開く幅に割る）×{n_levels}層、高さ{FENCE_HEIGHT_MM:.0f}"
                       "（荷の取り込み中は閉めて人をステージへ出さない）",
            ))
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
        hm = h.spec
        # 地上の昇降路の囲い: 搬器が下りてくる荷台の外周（足場側を除く3方）を囲い、出入口は施錠できる扉。
        # 搬器の下への立入りを防ぐ（部品 ashiba_hoist の 3D と同じ: 荷台から 0.3 離して高さ 1.8m）
        fl = float(h.cage_width_mm or HOIST_CAGE_W_MM) + 2 * HOIST_FENCE_GAP_MM
        fd = float(h.cage_depth_mm or 1300.0) + HOIST_FENCE_GAP_MM + 100.0
        out.append(PartDemand(
            "昇降機 地上の昇降路の囲い", "昇降路の囲い", None, 1,
            detail=f"荷台の外周 3方 延長{(fl + 2 * fd) / 1000:.1f}m・高さ{HOIST_FENCE_H_MM / 1000:.1f}m・施錠できる出入口の扉 1"
                   "（搬器の下への立入禁止。クレーン等安全規則の建設用リフト・メーカーの組立要領）",
        ))
        if hm is not None:
            # 機種を選んだ昇降機: 本体（レンタル1台）と、乗り込み口のフロアーゲート（乗り込む階ごとに1枚。単管 φ48.6 を
            # クランプで建地に留める。建機サービス Floor-gate。利用者の指定 2026-10-27）
            out.append(PartDemand(
                f"昇降機 本体 {hm.name}", "昇降機", None, 1,
                detail=f"{hm.maker or 'メーカー未記載'}・積載{hm.load_kg:.0f}kg"
                       + (f"・定員{hm.persons}名" if hm.persons else "")
                       + (f"・揚程{hm.max_lift_m:.0f}m" if hm.max_lift_m else "")
                       + f"（{hm.source}）",
            ))
            if landings and hm.kind == "ロングスパン":
                # 荷取りステージ: 乗り込み口の両端の建地に荷取用金具を付け、そのフランジに梁枠を2本（搬器側・足場側）掛け、
                # 布材・ころばし・足場板で床を組む（スギコ アルバロングスパンEV荷取用金具 50500 の設置手順）。床先は搬器の
                # 床先とのすき間 40mm 以内（利用者の指定 2026-10-27: ステージとロングスパンの離れは40mm以内の規定がある）
                gs = h.gate_spans(model)
                edge = _edge(model, h.edge_index)
                opening = sum(float(edge.spans[k]) for k in gs) if edge is not None else 0.0
                lv_txt = "作業層" + "・".join(str(lv) for lv in landings)
                out.append(PartDemand(
                    "昇降機 荷取りステージの荷取用金具", "荷取用金具", None, LANDING_FITTINGS_PER_STAGE * len(landings),
                    detail=f"{lv_txt}×{LANDING_FITTINGS_PER_STAGE}（梁枠2本の両端の建地。許容{LANDING_FITTING_KG:.0f}kg/個、"
                           f"例 スギコ 50500）。ステージの床先と搬器の床先のすき間は 40mm 以内（床は搬器の通り道に入れない）",
                ))
                if len(gs) in LANDING_BEAM_SPANS:
                    n_fab = int(opening // LANDING_LEDGER_PITCH_MM) + 1
                    out.append(PartDemand(
                        "昇降機 荷取りステージの梁枠", "梁枠", int(round(opening)), 2 * len(landings),
                        detail=f"{lv_txt}×2本（{len(gs)}スパン {opening:.0f}）。梁枠の間に布材を上部フランジ"
                               f"{LANDING_LEDGER_PITCH_MM:.0f} ごとに{n_fab}本、ころばし・足場板で床。梁枠の上に足場は組めない。"
                               "梁枠を受ける支柱に壁つなぎ",
                    ))
            elif landings:
                # 工事用エレベーター・荷揚げ機: 乗り込み口の両端の外側建地から腕を出して荷取り床を受ける（部品 ashiba_hoist の
                # 3D と同じ）。床先は搬器の床先とのすき間 40mm 以内
                out.append(PartDemand(
                    "昇降機 荷取り床の受け金物", "荷取用金具", None, 2 * len(landings),
                    detail="作業層" + "・".join(str(lv) for lv in landings)
                           + "×2（乗り込み口の両端の外側建地）。足場の作業床を搬器の側へ出し、搬器の床先とのすき間を "
                             "40mm 以内に（床は搬器の通り道に入れない）",
                ))
            if hm.gate and landings:
                from .hoist_models import FLOOR_GATES

                fg = FLOOR_GATES.get(hm.gate)
                out.append(PartDemand(
                    f"昇降機 乗り込み口の{fg['name'] if fg else 'フロアーゲート'}", "フロアーゲート", None, len(landings),
                    detail="作業層" + "・".join(str(lv) for lv in landings)
                           + "（単管 φ48.6 をクランプで建地に留める・リミット付ロック装置）",
                ))
                continue
        if landings:
            n_sp = len(h.gate_spans(model)) or 1
            out.append(PartDemand(
                "昇降機 乗り込み口の開閉式手すり", "開閉式手すり", None,
                len(landings) * n_sp,
                detail="作業層" + "・".join(str(lv) for lv in landings)
                       + f"×荷台の長さに掛かる{n_sp}スパン。乗り込み口は足場側の開口で、防護しないと"
                         "各層に開放端ができます（安衛則563条）",
            ))
    # 取付部・マスト控えの壁つなぎは ties.merge_attachment_ties で格子と同じ一覧に
    # 入れて数える（図面にも出る）。ここで別に足すと二重計上になる
    return out


FENCE_HEIGHT_MM = 1800.0        # 侵入落下防止柵の高さ（床から。金網のフェンスパネル H1800）
FENCE_PANEL_MAX_MM = 1800.0     # 落下防止柵1枚の最大幅


def stage_fence_panels(model: ScaffoldModel, stage: "LoadingStage") -> tuple[int, int, int]:
    """侵入落下防止柵の1層あたりの枚数 (先端, 妻側2面の計, 足場側の開閉式). GDL の 3D・平面と同じ割り方."""
    length = stage.length_mm(model)
    n_front = max(1, math.ceil(length / FENCE_PANEL_MAX_MM - 1e-6)) if length > 0 else 0
    n_side = 2 * max(1, math.ceil(float(stage.projection_mm) / FENCE_PANEL_MAX_MM - 1e-6))
    # 足場側の扉は足場の床の中へ開くので、1枚の幅は建地列の間隔−120 以下に割る（610 幅で 1829 のスパンは4枚）
    leaf = max(1.0, float(model.post_row_spacing_mm) - 120.0)
    n_gate = sum(max(1, math.ceil((float(sp) - 100.0) / leaf - 1e-6)) for sp in stage.spans(model))
    return n_front, n_side, n_gate


def _rail_post_nominal(model: ScaffoldModel) -> Optional[int]:
    """先端の手すり支柱の呼び寸法。手すり高さ以上で最小の支柱（根がらみ用は除く）."""
    need = model.guard_rail_height_mm
    sizes = sorted(p.nominal_dim for p in model.master.by_category("支柱")
                   if "根がらみ" not in p.note and p.nominal_dim > 0)
    for v in sizes:
        if v >= need - 1e-6:
            return v
    return sizes[-1] if sizes else None


def _side_nominal(model: ScaffoldModel, projection_mm: float) -> Optional[int]:
    """張出しの妻側（左右）に渡す材の呼び寸法。出以上で最小のもの."""
    sizes = sorted(p.nominal_dim for p in model.master.by_category("布材"))
    for v in sizes:
        if v >= projection_mm - 1e-6:
            return v
    return None


def stage_bracket_part(model: ScaffoldModel, projection_mm: float):
    """出を受けられる最小の張出ブラケット（部材）。無ければ None."""
    cands = sorted(
        (p for p in model.master.by_category("ブラケット") if "張出" in p.note),
        key=lambda p: p.nominal_dim,
    )
    for p in cands:
        if p.nominal_dim >= projection_mm - 1e-6:
            return p
    return None


def _bracket_nominal(model: ScaffoldModel, projection_mm: float) -> Optional[int]:
    """出を受けられる最小の張出ブラケット呼び寸法。無ければ None."""
    p = stage_bracket_part(model, projection_mm)
    return p.nominal_dim if p is not None else None


def bracket_span_allowable_kn(part) -> Optional[float]:
    """ブラケットのスパン当たり許容荷重（note の「かつ6.86kN/スパン」）。無ければ None."""
    m = re.search(r"([\d.]+)\s*kN\s*/\s*スパン", part.note)
    return float(m.group(1)) if m else None


def bracket_allowable_kn(part) -> Optional[float]:
    """ブラケットの許容荷重（kN/本）。マスタの note の「許容支持力6.86kN」「許容荷重1.96kN」から読む.

    書いていない部材は None（検定できないので要確認に回す）。
    """
    m = re.search(r"許容(?:支持力|荷重)\s*([\d.]+)\s*kN", part.note)
    return float(m.group(1)) if m else None


def platform_quantities(
    model: ScaffoldModel, result: PlatformResult
) -> dict[str, int]:
    """荷受けステージの部材数（分類名→数量）の要約."""
    counts: dict[str, int] = {}
    for d in platform_part_demands(model, result):
        if d.qty > 0:
            counts[d.label] = counts.get(d.label, 0) + d.qty
    return counts


def hoist_cut_ranges(model: ScaffoldModel, edge_index: int, hoists) -> list[tuple[float, float]]:
    """昇降機のマスト・搬器が通るスパン（辺の始点からの区間、重なりは結合）.

    朝顔はこの区間を切り欠く。支柱の真上に立つ昇降機は両隣のスパンを占める。
    衝突検査の文面と図面（asaCutList）で同じ区間を使う。
    """
    ep = next((e for e in model.plan.edges if e.edge_index == edge_index), None)
    if ep is None:
        return []
    posts = [0.0]
    for sp in ep.spans:
        posts.append(posts[-1] + sp)
    raw: list[tuple[float, float]] = []
    for h in hoists or []:
        if h.edge_index != edge_index:
            continue
        x = h.position_mm
        # 搬器の幅ぶん（位置を中心に）掛かるスパンを取る。点だけで見ると、幅2.4mの
        # 搬器がスパン境界の近くに立つとき隣のスパンの朝顔が切り欠かれない
        half = float(getattr(h, "cage_width_mm", HOIST_CAGE_W_MM) or HOIST_CAGE_W_MM) / 2.0
        raw += [(posts[k], posts[k + 1]) for k in range(len(ep.spans))
                if posts[k] < x + half - 1e-6 and posts[k + 1] > x - half + 1e-6]
    out: list[tuple[float, float]] = []
    for s0, e0 in sorted(raw):
        if out and s0 <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], e0))
        else:
            out.append((s0, e0))
    return out



def platform_ranges(model: ScaffoldModel, platforms) -> dict[int, list[tuple[float, float]]]:
    """荷受けステージと昇降機（搬器の幅が掛かるスパン）が占める区間（辺 → [(始点, 終点)]）.

    階段室の自動配置が避けるために使う。実機の小型面で、自動配置の階段室が
    昇降機の乗り込み口のスパンに重なって、踊り場と搬器が同じ床を取り合っていた。
    """
    out: dict[int, list[tuple[float, float]]] = {}
    if platforms is None:
        return out
    for st in getattr(platforms, "stages", None) or []:
        out.setdefault(st.edge_index, []).append((st.start_mm, st.end_mm(model)))
    hoists = getattr(platforms, "hoists", None) or []
    for ep in model.plan.edges:
        for rng in hoist_cut_ranges(model, ep.edge_index, hoists):
            out.setdefault(ep.edge_index, []).append(rng)
    return out
