"""法規チェック（仕様5の自動判定リスト、MVPは#1〜#9）.

判定は OK / WARN / NG の3値。根拠条文を basis に必ず持つ。
#10 朝顔はPhase 3（朝顔機能実装時に追加）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .elevation_solver import JACK_MAX_EXTENSION
from .master import SeriesLockError
from .model import ScaffoldModel

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


def run_all_checks(model: ScaffoldModel) -> list[CheckResult]:
    checks = [
        check_full_scaffold_principle,
        check_working_deck,
        check_guard_rail,
        check_first_ledger,
        check_negarami,
        check_jack_extension,
        check_wall_ties,
        check_height_reinforcement,
        check_series_lock,
        check_asagao,
    ]
    return [fn(model) for fn in checks]


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
    width = sum(m.config.deck_widths)
    if width < 400:
        problems.append(f"作業床幅{width}mm < 400mm")
    if m.config.deck_gap_mm > 30:
        problems.append(f"床材隙間{m.config.deck_gap_mm}mm > 30mm")
    if m.config.deck_to_post_gap_mm >= 120:
        problems.append(f"床材と建地の隙間{m.config.deck_to_post_gap_mm}mm ≧ 120mm")
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
    if not m.config.has_midrail:
        return CheckResult(3, "手すり", NG, f"手すり高さ{h}mmだが中桟がありません", basis)
    return CheckResult(3, "手すり", OK, f"手すり高さ{h}mm＋中桟あり", basis)


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

def check_jack_extension(m: ScaffoldModel) -> CheckResult:
    basis = f"実務基準（繰り出し{JACK_MAX_EXTENSION}mm以下）"
    j = m.elevation.jack_extension
    if j > JACK_MAX_EXTENSION:
        return CheckResult(6, "ジャッキ", WARN, f"繰り出し{j}mm > {JACK_MAX_EXTENSION}mm", basis)
    return CheckResult(6, "ジャッキ", OK, f"繰り出し{j}mm ≦ {JACK_MAX_EXTENSION}mm", basis)


# ---- #7 壁つなぎ ---------------------------------------------------------

def check_wall_ties(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則570条（くさび緊結式: 垂直5m×水平5.5m以下）"
    if not m.wall_ties:
        return CheckResult(7, "壁つなぎ", NG, "壁つなぎが配置されていません", basis)
    v_max, h_max = m.wall_tie_max_spacing()
    problems = []
    if v_max > 5000:
        problems.append(f"垂直間隔{v_max:.0f}mm > 5000mm")
    if h_max > 5500:
        problems.append(f"水平間隔{h_max:.0f}mm > 5500mm")
    if problems:
        return CheckResult(7, "壁つなぎ", NG, "、".join(problems), basis)
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
