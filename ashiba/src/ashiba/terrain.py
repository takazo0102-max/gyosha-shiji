"""敷地の高低差対応と支柱ごとのジャッキ量算出（仕様4.4・Phase 4）.

⚠️ ここが本ツール最大の差別化点:
敷地メッシュから各支柱位置のGL標高を取り、支柱1本ごとのジャッキ繰出し量を自動で出す。

原理（仕様4.4）:
- **布材・作業床レベルは全周で通す**。だから作業床の絶対標高は全支柱で共通
- くさび式はコマ位置が支柱下端から固定ピッチなので、作業床を揃えるには
  **各支柱の下端（ジャッキ天端）が基準からコマピッチの整数倍だけ下がっている**必要がある
- GLとその「あるべき下端」の差をジャッキ繰出しで吸収する

つまり支柱ごとに解くのは「何コマ下げるか(m_i)」で、残差がジャッキ量になる。
ジャッキの可動域(30〜450mm)はコマピッチ(450mm)よりわずかに狭いので、
どうしても収まらない位置が出る。その場合は敷板での調整量を明示する（黙って丸めない）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .elevation_solver import JACK_MAX_EXTENSION, JACK_MIN_EXTENSION, _compose_table
from .model import ScaffoldModel

JACK_HARD_MAX_EXTENSION = 450   # ジャッキの機械的な最大繰出し（270は実務上限）


@dataclass
class GroundModel:
    """敷地の標高サンプル点群. 任意座標の標高を逆距離加重(IDW)で補間する.

    Archicadの敷地メッシュ頂点をそのまま入れる想定。
    ⚠️ 三角形分割による厳密な内挿ではなく近傍点の加重平均。
    急変する地形では実測値の確認が必要。
    """

    points: list[tuple[float, float, float]] = field(default_factory=list)  # (x,y,z) mm
    k_nearest: int = 4
    power: float = 2.0

    @property
    def is_flat(self) -> bool:
        return not self.points

    def elevation_at(self, x: float, y: float, default: float = 0.0) -> float:
        if not self.points:
            return default
        dists = []
        for px, py, pz in self.points:
            d2 = (px - x) ** 2 + (py - y) ** 2
            if d2 < 1e-6:          # サンプル点に一致
                return pz
            dists.append((d2, pz))
        dists.sort(key=lambda t: t[0])
        near = dists[: max(1, self.k_nearest)]
        wsum = 0.0
        zsum = 0.0
        for d2, pz in near:
            w = 1.0 / (math.sqrt(d2) ** self.power)
            wsum += w
            zsum += w * pz
        return zsum / wsum

    def range_mm(self) -> tuple[float, float]:
        if not self.points:
            return (0.0, 0.0)
        zs = [p[2] for p in self.points]
        return (min(zs), max(zs))


@dataclass
class PostFoot:
    """支柱1本の脚部（ジャッキ量と支柱構成）."""

    index: int
    x: float
    y: float
    gl_mm: float
    koma_offset: int          # 基準から何コマ下げるか
    jack_mm: float            # ジャッキ繰出し量
    posts: list[int]          # この位置の支柱構成（下から）
    base_plate_adjust_mm: float = 0.0   # 敷板で追加調整が必要な量
    warnings: list[str] = field(default_factory=list)

    @property
    def jack_top_mm(self) -> float:
        return self.gl_mm + self.jack_mm + self.base_plate_adjust_mm

    @property
    def ok(self) -> bool:
        return not self.warnings


@dataclass
class TerrainResult:
    feet: list[PostFoot]
    reference_gl_mm: float
    gl_range_mm: tuple[float, float]
    deck_levels_abs_mm: list[float]    # 作業床の絶対標高（全周共通）
    # warnings は「対応が要るもの」だけ。何をどう解いたかの説明は notes へ分ける
    # （混ぜると、読む側がどれに手を打てばよいのか分からなくなる）
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # ジャッキ繰出しが実務上限を超えたときの本文。法規チェック6と同じ事象なので、
    # 向こうにも同じ文面を使わせて、要確認一覧に二重で並ばないようにする
    over_jack_warning: str = ""
    # 帳票の呼び名（枠組は建枠）。ジャッキ量一覧の列名などに使う
    vertical_member_name: str = "支柱"

    @property
    def jack_min_mm(self) -> float:
        return min((f.jack_mm for f in self.feet), default=0.0)

    @property
    def jack_max_mm(self) -> float:
        return max((f.jack_mm for f in self.feet), default=0.0)

    @property
    def gl_difference_mm(self) -> float:
        return self.gl_range_mm[1] - self.gl_range_mm[0]

    @property
    def all_ok(self) -> bool:
        return all(f.ok for f in self.feet)

    def over_recommended(self) -> list[PostFoot]:
        return [f for f in self.feet if f.jack_mm > JACK_MAX_EXTENSION]


def solve_post_feet(
    model: ScaffoldModel,
    ground: Optional[GroundModel] = None,
    jack_min: int = JACK_MIN_EXTENSION,
    jack_recommended_max: int = JACK_MAX_EXTENSION,
    jack_hard_max: int = JACK_HARD_MAX_EXTENSION,
) -> TerrainResult:
    """各支柱位置のGL標高から、支柱ごとのジャッキ量と支柱構成を解く.

    作業床レベルを全周で通すため、各支柱の下端は基準からコマピッチの整数倍だけ下げる。
    残差をジャッキで吸収し、吸収しきれない分は敷板調整として明示する。
    """
    ground = ground or GroundModel()
    positions = model.plan.post_positions()
    koma = model.master.koma_pitch
    # 枠組にコマは無い。段差の刻みは最小の建枠（調整枠）の高さになる
    step_name = "コマピッチ"
    if koma <= 0:
        # 枠組はコマの概念がないので、建枠高さの最小値を刻みとする
        koma = min(model.master.frame_heights() or [model.master.floor_height])
        step_name = "調整枠の高さ"

    gls = [ground.elevation_at(x, y) for (x, y) in positions]
    gl_max = max(gls) if gls else 0.0
    gl_min = min(gls) if gls else 0.0

    # 基準面（全支柱の下端が乗る面）を全体シフトして、実務上限を超える支柱を最小化する。
    # 平面割付の「全体XYシフトで離れを最適化」と同じ考え方の垂直版。
    # ジャッキの可動域(30〜270)はコマピッチ(450)より狭いため、
    # 連続的な斜面では必ず収まらない支柱が出る。せめてその本数を最小にする。
    ref_jack = model.elevation.jack_extension
    ref_jack_top = _optimize_datum(
        gls, gl_max, ref_jack, koma, jack_min, jack_hard_max, jack_recommended_max
    )

    base_posts = list(model.elevation.posts)
    base_total = sum(base_posts)
    lengths = (
        model.master.frame_heights() if model.master.is_frame
        else model.master.post_lengths(include_negarami=True)
    )
    # 何コマ下げれば、ジャッキ量が可動域に収まるか（脚ごと）
    offsets = [
        _choose_koma_offset(
            ref_jack_top, gl, koma, jack_min, jack_hard_max, jack_recommended_max
        )
        for gl in gls
    ]
    # 継ぎ足しの構成表は、実際に必要な最大コマ数まで作る。8コマ（3.6m）で
    # 打ち切っていたときは、それを超える段差の脚が名目構成に戻され、数量の
    # 支柱が不足し、高さ判定も名目のままだった（脚ごとの備考にしか出なかった）
    max_offset = max(offsets) if offsets else 0
    table = _compose_table(
        base_total + int(koma) * max(8, max_offset), sorted(set(lengths), reverse=True)
    )

    feet: list[PostFoot] = []
    warnings: list[str] = []
    for i, ((x, y), gl), m in zip(range(len(gls)), zip(positions, gls), offsets):
        # 支柱下端の目標位置は gl + jack_ideal。ジャッキで届かない分は地盤側で調整する。
        # 調整量は必ず adjust = jack_ideal - 実ジャッキ量 とする（符号を逆にすると
        # 支柱下端が目標からずれ、作業床が全周で通らなくなる）
        jack_ideal = ref_jack_top - m * koma - gl
        jack = jack_ideal
        foot_warnings: list[str] = []
        adjust = 0.0

        if jack_ideal < jack_min:
            jack = jack_min
            adjust = jack_ideal - jack_min          # 負＝床掘りで下げる
            foot_warnings.append(
                f"ジャッキ最小{jack_min}mmでも下端が高すぎます。"
                f"床掘り等で{-adjust:.0f}mm下げる必要があります"
            )
        elif jack_ideal > jack_hard_max:
            jack = jack_hard_max
            adjust = jack_ideal - jack_hard_max     # 正＝敷板で持ち上げる
            foot_warnings.append(
                f"ジャッキ最大{jack_hard_max}mmでも下端に届きません。"
                f"敷板で{adjust:.0f}mm持ち上げる必要があります"
            )
        elif jack > jack_recommended_max:
            foot_warnings.append(
                f"ジャッキ繰出し{jack:.0f}mmが実務上限{jack_recommended_max}mmを超えます"
            )

        # コマを下げた分だけ支柱を長くする
        posts = base_posts
        if m > 0:
            extra = table.get(base_total + int(m * koma))
            posts = sorted(extra, reverse=True) if extra else base_posts
            if extra is None:
                foot_warnings.append(
                    f"{m}コマ分（{m * koma:.0f}mm）延長した支柱構成を組めません"
                )

        feet.append(PostFoot(
            index=i, x=x, y=y, gl_mm=gl, koma_offset=m, jack_mm=jack,
            posts=posts, base_plate_adjust_mm=adjust, warnings=foot_warnings,
        ))

    notes: list[str] = []
    diff = gl_max - gl_min
    if diff > 0:
        notes.append(
            f"敷地の高低差{diff:.0f}mmを支柱ごとのジャッキ・支柱長で吸収しました"
            f"（{len({f.koma_offset for f in feet})}種類の脚部構成）"
        )
    vm = model.master.vertical_member_name    # 支柱／建枠
    over_jack_warning = ""
    over = [f for f in feet if f.jack_mm > jack_recommended_max]
    if over:
        window = jack_recommended_max - jack_min
        msg = (
            f"ジャッキ繰出しが実務上限{jack_recommended_max}mmを超える{vm}が"
            f"{len(over)}本あります（最大{max(f.jack_mm for f in over):.0f}mm）。"
        )
        if diff <= koma:
            # 高低差がコマピッチ以内なら、床均しで全数を上限内に収められる
            need = max(0.0, diff - window)
            msg += (
                f"高低差が{step_name}{koma:.0f}mm以内なので、"
                f"床均しで高低差を{need:.0f}mm縮めれば全{vm}が上限内に収まります"
            )
        else:
            msg += (
                f"ジャッキの可動域（{jack_min}〜{jack_recommended_max}mm＝{window}mm）は"
                f"{step_name}{koma:.0f}mmより狭いため、高低差が1段を超える敷地では"
                f"一定数が上限を超えます。該当{vm}の敷板調整または部分的な床均しで対応してください"
            )
        warnings.append(msg)
        over_jack_warning = msg
    cannot = [f for f in feet if any("組めません" in w for w in f.warnings)]
    if cannot:
        # 脚ごとの備考にしか出ないと、総合判定が成立のまま部材が足りない計画になる
        warnings.append(
            f"継ぎ足した{vm}構成を組めない脚が{len(cannot)}本あります"
            f"（最大{max(f.koma_offset for f in cannot)}{step_name}分）。"
            "マスタの支柱長で構成できない段差です。床均しか支柱規格の追加を検討してください"
        )
    need_plate = [f for f in feet if abs(f.base_plate_adjust_mm) > 1e-6]
    if need_plate:
        warnings.append(
            f"ジャッキの可動域で吸収しきれない{vm}が{len(need_plate)}本あります"
            "（敷板または床掘りでの調整量を一覧に明示しています）"
        )

    deck_levels_abs = [
        ref_jack_top - ref_jack + lvl for lvl in model.elevation.level_heights
    ]
    return TerrainResult(
        feet=feet,
        reference_gl_mm=gl_max,
        gl_range_mm=(gl_min, gl_max),
        deck_levels_abs_mm=deck_levels_abs,
        warnings=warnings,
        notes=notes,
        over_jack_warning=over_jack_warning,
        vertical_member_name=vm,
    )


def _optimize_datum(
    gls: list[float],
    gl_max: float,
    ref_jack: int,
    koma: float,
    jack_min: int,
    jack_hard_max: int,
    jack_recommended_max: int,
) -> float:
    """基準面（ジャッキ天端の基準標高）を決める.

    基準面をδずらすと全支柱のジャッキ量が一様にδ動く。δはコマピッチ周期なので
    [0, koma) を走査すれば十分。実務上限超過本数 → 敷板調整本数 → 逸脱量合計 の順に最小化する。
    """
    if not gls:
        return gl_max + ref_jack
    best = None
    step = 5
    for delta in range(0, int(koma), step):
        top = gl_max + jack_min + delta
        n_over = 0
        n_plate = 0
        total_dev = 0.0
        for gl in gls:
            m = _choose_koma_offset(
                top, gl, koma, jack_min, jack_hard_max, jack_recommended_max
            )
            jack = top - m * koma - gl
            if jack < jack_min:
                n_plate += 1
                total_dev += jack_min - jack
            elif jack > jack_hard_max:
                n_plate += 1
                total_dev += jack - jack_hard_max
            elif jack > jack_recommended_max:
                n_over += 1
                total_dev += jack - jack_recommended_max
        score = (n_plate, n_over, total_dev)
        if best is None or score < best[0]:
            best = (score, top)
    return best[1]


def _choose_koma_offset(
    ref_jack_top: float,
    gl: float,
    koma: float,
    jack_min: int,
    jack_hard_max: int,
    jack_recommended_max: int,
) -> int:
    """ジャッキ量が可動域に収まる下げコマ数を選ぶ（実務上限内を優先）."""
    raw = (ref_jack_top - gl - jack_recommended_max) / koma
    best = None
    for m in range(max(0, math.floor(raw) - 1), math.ceil(raw) + 3):
        if m < 0:
            continue
        jack = ref_jack_top - m * koma - gl
        within_hard = jack_min <= jack <= jack_hard_max
        within_rec = jack_min <= jack <= jack_recommended_max
        # 実務上限内 → 可動域内 → 逸脱量最小 の順で選ぶ
        deviation = 0.0
        if jack < jack_min:
            deviation = jack_min - jack
        elif jack > jack_hard_max:
            deviation = jack - jack_hard_max
        score = (not within_rec, not within_hard, deviation, m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1] if best else 0


def jack_table_rows(result: TerrainResult) -> list[list]:
    """ジャッキ量一覧（帳票用の行データ）."""
    vm = result.vertical_member_name
    rows = [[
        "No", "X(mm)", "Y(mm)", "GL標高(mm)", "下げ段数",
        "ジャッキ繰出し(mm)", "敷板調整(mm)", f"{vm}構成", "備考",
    ]]
    for f in result.feet:
        rows.append([
            f.index + 1, round(f.x), round(f.y), round(f.gl_mm, 1), f.koma_offset,
            round(f.jack_mm, 1), round(f.base_plate_adjust_mm, 1),
            "+".join(str(p) for p in f.posts),
            " / ".join(f.warnings) if f.warnings else "",
        ])
    return rows
