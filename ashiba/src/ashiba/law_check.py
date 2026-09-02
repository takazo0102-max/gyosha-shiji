"""法規チェック.

仕様5の自動判定リスト10項目に、建地間隔（#11）と昇降設備（#12）を加えた12項目。
判定は OK / WARN / NG の3値。根拠条文を basis に必ず持つ。
"""

from __future__ import annotations

from dataclasses import dataclass

from .elevation_solver import JACK_MAX_EXTENSION
from .master import SeriesLockError
from .model import GUARD_RAIL_ADVANCE, ScaffoldModel

OK = "OK"
WARN = "WARN"
NG = "NG"


@dataclass
class CheckResult:
    check_id: int
    name: str
    status: str
    message: str
    basis: str


def run_all_checks(
    model: ScaffoldModel, stair_plan=None, terrain=None
) -> list[CheckResult]:
    """法規チェック12項目.

    stair_plan / terrain を渡すと、その結果を使って判定する:
    - 昇降設備(#12)は階段の配置が無いと判定できない
    - ジャッキ(#6)は敷地高低差で支柱ごとに繰出し量が違う。平坦時の値だけ
      見ていると、実際には上限超過の支柱があるのにOKと出る
    """
    checks = [
        check_full_scaffold_principle,
        check_working_deck,
        check_guard_rail,
        check_first_ledger,
        check_negarami,
        check_wall_ties,
        check_height_reinforcement,
        check_series_lock,
        check_asagao,
        check_post_spacing,
    ]
    results = [fn(model) for fn in checks]
    results.append(check_jack_extension(model, terrain))
    results.append(check_stairs(model, stair_plan))
    return sorted(results, key=lambda r: r.check_id)


def required_asagao_stages(height_mm: float) -> int:
    """必要な朝顔の段数: 10m以上で1段、20m以上で2段."""
    if height_mm >= 20000:
        return 2
    if height_mm >= 10000:
        return 1
    return 0


def summary(results: list[CheckResult]) -> dict:
    return {
        "total": len(results),
        "ok": sum(1 for r in results if r.status == OK),
        "warn": sum(1 for r in results if r.status == WARN),
        "ng": sum(1 for r in results if r.status == NG),
    }


# ---- #1 本足場原則 -------------------------------------------------------

def check_full_scaffold_principle(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則561条の2（2024/4施行）"
    if m.clearance_space_mm >= 1000 and m.config.scaffold_form == "一側足場":
        return CheckResult(
            1, "本足場原則", NG,
            f"躯体外面から水平{m.clearance_space_mm:.0f}mm≧1mのスペースがあるため"
            "一側足場は使用できません。本足場としてください", basis,
        )
    return CheckResult(1, "本足場原則", OK, f"足場形式: {m.config.scaffold_form}", basis)


# ---- #2 作業床 -----------------------------------------------------------

def check_working_deck(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則563条"
    problems = []
    width = sum(m.deck_widths_in_use)
    if width < 400:
        problems.append(f"作業床幅{width}mm < 400mm")
    if m.config.deck_gap_mm > 30:
        problems.append(f"床材隙間{m.config.deck_gap_mm}mm > 30mm")
    if m.config.deck_to_post_gap_mm >= 120:
        problems.append(f"床材と建地の隙間{m.config.deck_to_post_gap_mm}mm ≧ 120mm")
    # 作業床の垂直間隔は2m以下（くさび緊結式足場の基準）
    levels = m.elevation.level_heights
    if len(levels) >= 2:
        v_pitch = max(b - a for a, b in zip(levels, levels[1:]))
        if v_pitch > 2000:
            problems.append(f"作業床の垂直間隔{v_pitch}mm > 2000mm")
    if problems:
        return CheckResult(2, "作業床", NG, "、".join(problems), basis)
    return CheckResult(
        2, "作業床", OK,
        f"幅{width}mm・床材隙間{m.config.deck_gap_mm}mm・建地との隙間{m.config.deck_to_post_gap_mm}mm",
        basis,
    )


# ---- #3 手すり -----------------------------------------------------------

def check_guard_rail(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則563条"
    h = m.guard_rail_height_mm
    if h < 850:
        return CheckResult(3, "手すり", NG, f"手すり高さ{h}mm < 850mm", basis)
    # 先行手摺は手すりと斜材が一体で、中桟の機能を兼ねる
    advance = m.config.guard_rail_type == GUARD_RAIL_ADVANCE
    if not advance and not m.config.has_midrail:
        return CheckResult(3, "手すり", NG, f"手すり高さ{h}mmだが中桟がありません", basis)
    problems = []
    mh = m.config.midrail_height_mm
    if not advance and not (350 <= mh <= 500):
        problems.append(f"中桟高さ{mh}mm が35〜50cmの範囲外")
    if m.config.has_toe_board and m.config.toe_board_height_mm < 100:
        problems.append(
            f"幅木高さ{m.config.toe_board_height_mm}mm < 100mm（落下物防止）"
        )
    if problems:
        return CheckResult(3, "手すり", NG, "、".join(problems), basis)
    detail = f"手すり高さ{h}mm＋" + ("先行手摺（斜材が中桟を兼ねる）" if advance
                                    else f"中桟{mh}mm")
    if m.config.has_toe_board:
        detail += f"＋幅木{m.config.toe_board_height_mm}mm"
    return CheckResult(3, "手すり", OK, detail, basis)


# ---- #4 第一の布 ---------------------------------------------------------

def check_first_ledger(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則571条"
    h = m.elevation.first_ledger_height
    if h > 2000:
        return CheckResult(4, "第一の布", NG, f"第一の布高さ{h}mm > 2000mm", basis)
    return CheckResult(4, "第一の布", OK, f"第一の布高さ{h}mm ≦ 2000mm", basis)


# ---- #5 根がらみ ---------------------------------------------------------

def check_negarami(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則570条・仮設工業会技術基準（できる限り低く）"
    if not m.elevation.has_negarami:
        return CheckResult(5, "根がらみ", NG, "最下コマに根がらみがありません", basis)
    return CheckResult(
        5, "根がらみ", OK,
        f"最下コマ（高さ{m.elevation.first_ledger_height}mm）に設置", basis,
    )


# ---- #6 ジャッキ ---------------------------------------------------------

def check_jack_extension(m: ScaffoldModel, terrain=None) -> CheckResult:
    """ジャッキ繰出し量。傾斜地では支柱ごとに違うので最大の1本で見る.

    平坦時の値だけ見ていると、敷地の警告では「上限超過が16本」と出ている
    のに法規チェックはOK、という食い違いが起きる。
    """
    basis = f"実務基準（繰り出し{JACK_MAX_EXTENSION}mm以下）"
    j = m.elevation.jack_extension
    over = []
    if terrain is not None and getattr(terrain, "feet", None):
        over = [f for f in terrain.feet if f.jack_mm > JACK_MAX_EXTENSION]
        j = max(j, max((f.jack_mm for f in terrain.feet), default=0))
    if over:
        # 地形ソルバは「なぜ超えるのか・どれだけ床均しすれば収まるのか」まで
        # 出している。同じ事象を別文面で二度言わず、その本文をそのまま使う
        msg = getattr(terrain, "over_jack_warning", "") or (
            f"敷地高低差により繰り出しが{JACK_MAX_EXTENSION}mmを超える支柱が"
            f"{len(over)}本あります（最大{j:.0f}mm）。"
            "該当支柱は敷板調整または部分的な床均しで対応してください"
        )
        return CheckResult(6, "ジャッキ", WARN, msg, basis)
    if j > JACK_MAX_EXTENSION:
        return CheckResult(
            6, "ジャッキ", WARN, f"繰り出し{j:.0f}mm > {JACK_MAX_EXTENSION}mm", basis
        )
    return CheckResult(
        6, "ジャッキ", OK, f"繰り出し{j:.0f}mm ≦ {JACK_MAX_EXTENSION}mm", basis
    )


# ---- #12 昇降設備 --------------------------------------------------------

def check_stairs(m: ScaffoldModel, stair_plan=None) -> CheckResult:
    """昇降設備の有無と、昇降設備までの水平移動距離.

    ツールは階段を自動配置しているのに、法規チェックの一覧には入って
    いなかった。設置届の法規チェック表に昇降設備の行が無いのはまずい。
    """
    from .stairs import (
        DEFAULT_MAX_TRAVEL_MM,
        MIN_HEIGHT_FOR_STAIRS_MM,
        validate_stairs,
    )

    basis = "安衛則526条（高さ1.5m超は昇降設備）／実務指針（水平移動30m以内）"
    h = m.scaffold_height_mm
    if h <= MIN_HEIGHT_FOR_STAIRS_MM:
        return CheckResult(
            12, "昇降設備", OK,
            f"足場高さ{h}mm ≦ {MIN_HEIGHT_FOR_STAIRS_MM}mm のため昇降設備は不要",
            basis,
        )
    if stair_plan is None:
        return CheckResult(
            12, "昇降設備", WARN,
            f"足場高さ{h / 1000:.1f}mには昇降設備が必要ですが、"
            "階段の配置が未指定のため判定できません",
            basis,
        )
    issues = validate_stairs(m, stair_plan)
    if issues:
        return CheckResult(12, "昇降設備", NG, "、".join(issues), basis)
    return CheckResult(
        12, "昇降設備", OK,
        f"階段{stair_plan.count}箇所（最大水平移動"
        f"{stair_plan.max_travel_mm / 1000:.1f}m ≦ "
        f"{DEFAULT_MAX_TRAVEL_MM / 1000:.0f}m）"
        f"／踊り場計{stair_plan.total_landings}段",
        basis,
    )


# ---- #7 壁つなぎ ---------------------------------------------------------

def check_wall_ties(m: ScaffoldModel) -> CheckResult:
    v_lim, h_lim, basis = m.wall_tie_limits()
    if not m.wall_ties:
        return CheckResult(7, "壁つなぎ", NG, "壁つなぎが配置されていません", basis)
    v_max, h_max = m.wall_tie_max_spacing()
    problems = []
    if v_max > v_lim:
        problems.append(f"垂直間隔{v_max:.0f}mm > {v_lim:.0f}mm")
    if h_max > h_lim:
        problems.append(f"水平間隔{h_max:.0f}mm > {h_lim:.0f}mm")
    if problems:
        return CheckResult(7, "壁つなぎ", NG, "、".join(problems), basis)
    # 間隔が法規内でも、壁つなぎが1本も入らない面は別に挙げる。
    # 間隔の最大値だけ見ていると、その面の存在が結果に出てこない
    untied = m.edges_without_wall_ties()
    if untied:
        lengths = {
            e.edge_index: e.scaffold_length for e in m.plan.edges
        }
        detail = "、".join(
            f"{m.face_name(i)} {lengths.get(i, 0):.0f}mm" for i in untied
        )
        return CheckResult(
            7, "壁つなぎ", WARN,
            f"最大 垂直{v_max:.0f}mm×水平{h_max:.0f}mm（{len(m.wall_ties)}箇所）"
            f"／壁つなぎが入らない面: {detail}。"
            "両隣の面にコーナー経由で支持される前提です。単管等での別途拘束を検討してください",
            basis,
        )
    return CheckResult(
        7, "壁つなぎ", OK,
        f"最大 垂直{v_max:.0f}mm×水平{h_max:.0f}mm（{len(m.wall_ties)}箇所）", basis,
    )


# ---- #8 高さ31m超の補強 --------------------------------------------------

def check_height_reinforcement(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則571条（高さ31m超は建地2本組等の補強）"
    h = m.scaffold_height_mm
    if h > 45000:
        return CheckResult(
            8, "高さ", NG,
            f"足場高さ{h / 1000:.2f}m > 45m: 本ツールの適用範囲外です（個別設計が必要）", basis,
        )
    if h > 31000:
        return CheckResult(
            8, "高さ", WARN,
            f"足場高さ{h / 1000:.2f}m > 31m: 31mを超える部分より下の支柱は2本組等の補強が必要です",
            basis,
        )
    return CheckResult(8, "高さ", OK, f"足場高さ{h / 1000:.2f}m ≦ 31m", basis)


# ---- #9 規格混在 ---------------------------------------------------------

def check_series_lock(m: ScaffoldModel) -> CheckResult:
    basis = "本ツール運用規則（系列ロック。インチ/センチ混在は組めない）"
    series = {p.series_id for p in m.master.parts}
    if len(series) > 1 or (series and m.master.series_id not in series):
        return CheckResult(
            9, "規格混在", NG,
            f"複数系列の部材が混在しています: {sorted(series)}", basis,
        )
    try:
        for p in m.master.parts:
            m.master.assert_series(p)
    except SeriesLockError as exc:
        return CheckResult(9, "規格混在", NG, str(exc), basis)
    return CheckResult(9, "規格混在", OK, f"全部材が {m.master.series_id} に統一", basis)


# ---- #10 朝顔（防護棚） --------------------------------------------------

def check_asagao(m: ScaffoldModel) -> CheckResult:
    basis = (
        "安衛則563条・537条（落下物防護）: 高さ10m以上で1段・20m以上で2段、"
        "突出2m以上・傾斜20度以上、取付部は2スパン毎に壁つなぎ"
    )
    need = required_asagao_stages(m.scaffold_height_mm)
    spec = m.config.asagao
    h_m = m.scaffold_height_mm / 1000.0

    if need == 0:
        if spec is None or spec.stages == 0:
            return CheckResult(
                10, "朝顔", OK, f"足場高さ{h_m:.2f}m < 10m のため朝顔は不要", basis
            )
        return CheckResult(
            10, "朝顔", OK,
            f"足場高さ{h_m:.2f}m（不要だが{spec.stages}段を設置）", basis,
        )

    if spec is None or spec.stages == 0:
        return CheckResult(
            10, "朝顔", NG,
            f"足場高さ{h_m:.2f}m には朝顔{need}段が必要ですが設置されていません",
            basis,
        )

    problems = []
    if spec.stages < need:
        problems.append(f"段数{spec.stages} < 必要{need}段")
    if spec.projection_mm < 2000:
        problems.append(f"突出{spec.projection_mm:.0f}mm < 2000mm")
    if spec.angle_deg < 20:
        problems.append(f"傾斜{spec.angle_deg:.0f}度 < 20度")
    if spec.tie_every_spans > 2:
        problems.append(f"取付部の壁つなぎが{spec.tie_every_spans}スパン毎 > 2スパン毎")
    if problems:
        return CheckResult(10, "朝顔", NG, "、".join(problems), basis)
    return CheckResult(
        10, "朝顔", OK,
        f"{spec.stages}段（必要{need}段）・突出{spec.projection_mm:.0f}mm・"
        f"傾斜{spec.angle_deg:.0f}度・取付部{spec.tie_every_spans}スパン毎に壁つなぎ",
        basis,
    )


# ---- #11 建地間隔 --------------------------------------------------------

# くさび緊結式足場の建地間隔（安衛則571条 わく組足場以外の支柱式足場に準じる）
MAX_SPAN_ALONG_MM = 1850    # 桁行方向（スパン方向）
MAX_SPAN_ACROSS_MM = 1500   # 梁間方向（内外建地間隔）


MAX_FRAME_HEIGHT_MM = 2000   # わく組足場の主わく高さ（571条1項一号）


def check_post_spacing(m: ScaffoldModel) -> CheckResult:
    """建地（枠組は主わく）の間隔.

    571条は足場の種類で条文が違う:
      一号 わく組足場: 主わく高さ2m以下・主わく間隔1.85m以下
      二号 それ以外の支柱式: 桁行1.85m以下・梁間1.5m以下

    梁間1.5mの制限はわく組には無い（建枠の幅で決まる）ので当てない。
    スパン割は真物の呼び寸法から決まるので通常は満たすが、
    系列やマスタを差し替えたときに黙って超えないよう検査する。
    """
    spans = [s for ep in m.plan.edges for s in ep.spans]
    longest = max(spans) if spans else 0
    problems = []

    if m.master.is_frame:
        basis = "安衛則571条1項一号（わく組足場: 主わく高さ2m以下・主わく間隔1.85m以下）"
        if longest > MAX_SPAN_ALONG_MM:
            problems.append(f"主わくの間隔{longest}mm > {MAX_SPAN_ALONG_MM}mm")
        frame_h = max(m.elevation.posts) if m.elevation.posts else 0
        if frame_h > MAX_FRAME_HEIGHT_MM:
            problems.append(f"主わくの高さ{frame_h}mm > {MAX_FRAME_HEIGHT_MM}mm")
        if problems:
            return CheckResult(11, "建地間隔", NG, "、".join(problems), basis)
        return CheckResult(
            11, "建地間隔", OK, f"主わく間隔{longest}mm・主わく高さ{frame_h}mm", basis
        )

    basis = "安衛則571条1項二号（支柱式足場の建地間隔: 桁行方向1.85m以下・梁間方向1.5m以下）"
    if longest > MAX_SPAN_ALONG_MM:
        problems.append(f"桁行方向の建地間隔{longest}mm > {MAX_SPAN_ALONG_MM}mm")
    # 梁間方向の建地間隔は建地列の芯々。作業床の被覆幅ではない
    across = m.post_row_spacing_mm
    if m.config.scaffold_form != "一側足場" and across > MAX_SPAN_ACROSS_MM:
        problems.append(f"梁間方向の建地間隔{across}mm > {MAX_SPAN_ACROSS_MM}mm")
    if problems:
        return CheckResult(11, "建地間隔", NG, "、".join(problems), basis)
    detail = f"桁行{longest}mm"
    if m.config.scaffold_form != "一側足場":
        detail += f"・梁間{across}mm"
    return CheckResult(11, "建地間隔", OK, detail, basis)
