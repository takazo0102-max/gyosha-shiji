"""帳票出力: 数量表CSV（発注書としてそのまま使える型番ベース）＋割付レポート.

設置届（様式第20号）要否の自動判定もここで行う:
高さ10m以上かつ設置期間60日以上 → 工事開始30日前までに所轄労基署へ（安衛法88条）。
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .law_check import CheckResult
from .model import ScaffoldModel
from .notification import notification_required  # 判定はnotificationに一元化
from .quantity import QuantityResult

__all__ = [
    "notification_required",
    "write_quantity_csv",
    "write_report_md",
    "write_plan_json",
    "write_jack_table_csv",
]


def write_quantity_csv(result: QuantityResult, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["型番", "分類", "呼び寸法", "実寸法", "単位重量kg", "数量", "小計重量kg", "備考"])
        for line in result.lines:
            p = line.part
            w.writerow(
                [p.model_no, p.category, p.nominal_dim, p.actual_dim,
                 p.weight_kg, line.qty, round(line.subtotal_weight, 1), p.note]
            )
        w.writerow([])
        w.writerow(["総重量kg", round(result.total_weight_kg, 1)])
        w.writerow(["トラック台数概算(4t)", result.truck_count])
        w.writerow(["架け面積m2", result.kake_menseki_m2])
        for n in result.notes:
            w.writerow(["注記", n])


def write_report_md(
    model: ScaffoldModel,
    quantity: QuantityResult,
    checks: list[CheckResult],
    path: Path,
    project_name: str = "",
    stair_plan=None,
    structural=None,
    terrain=None,
    platforms=None,
    openings=None,
    bracket_sections=None,
) -> None:
    """割付レポート（人が読む成果物）.

    構造計算の検定比・壁つなぎの配置・敷地の高低差・付帯設備は、以前は
    plan.json と設置届Excelにしか出ておらず、この本文には無かった。
    計画の可否を左右する数字なので本文に出す。
    """
    e = model.elevation
    lines: list[str] = []
    a = lines.append
    a(f"# 足場割付レポート {project_name}".rstrip())
    a("")
    a(f"- 系列: {model.master.series_id}（コマピッチ{model.master.koma_pitch}mm）")
    a(f"- 足場高さ: {model.scaffold_height_mm}mm / 作業層数: {e.n_levels}")
    a(f"- 支柱構成（下から）: ジャッキ{e.jack_extension} + "
      + " + ".join(str(p) for p in e.posts)
      + f" = {e.total_height}mm")
    a(f"- 千鳥用代替構成: " + " + ".join(str(p) for p in e.posts_alt)
      + ("（千鳥成立）" if e.is_staggered() else "（要確認）"))
    a(f"- 1層あたり支柱位置数: {model.plan.total_posts}（二重計上なし）")
    a(f"- 手すり方式: {model.config.guard_rail_type}")
    a("- 設置届: " + ("**要**（高さ10m以上かつ60日以上 → 開始30日前までに労基署へ）"
                    if notification_required(model) else "不要"))
    a("")
    a("## 平面割付")
    a("")
    a("| 辺 | 足場長 | スパン構成 | 離れ | 対処案 |")
    a("|---|---|---|---|---|")
    for ep in model.plan.edges:
        spans = "+".join(str(s) for s in ep.spans)
        a(f"| {ep.edge_index} | {ep.scaffold_length:.0f} | {spans} "
          f"| {ep.standoff:.0f} | {ep.remedy or '—'} |")
    if model.plan.corner_steps:
        a("")
        a("## コーナーステップ（枠組: 離れ固定で余りをコーナーで吸収）")
        a("")
        a("| コーナー | 隙間 | 判定 | 備考 |")
        a("|---|---|---|---|")
        for cs in model.plan.corner_steps:
            a(f"| {cs.corner_index} | {cs.gap_mm:.0f}mm | "
              f"{'OK' if cs.ok else 'NG'} | {cs.message or '建枠70mm以上・ステップ250mm以内'} |")
    if stair_plan is not None and stair_plan.towers:
        a("")
        a("## 昇降設備（階段室）")
        a("")
        a(f"- 箇所数: {stair_plan.count}（移動距離30m以内に必要な数: "
          f"{stair_plan.required_count}）")
        a(f"- 最大水平移動距離: {stair_plan.max_travel_mm / 1000:.1f}m")
        a(f"- 踊り場: 1箇所あたり{stair_plan.landings_per_tower}段 "
          f"／ 計{stair_plan.total_landings}段（2層以下毎）")
        a("")
        a("| # | 辺 | 始点からの位置 | 占有 | 選定理由 |")
        a("|---|---|---|---|---|")
        for i, t in enumerate(stair_plan.towers, 1):
            a(f"| {i} | {t.edge_index} | {t.start_mm:.0f}mm | "
              f"{t.span_count}スパン({t.length_mm:.0f}mm) | "
              f"{t.reason or ('位置指定' if t.manual else '自動配置')} |")
        # 必要数を大きく超える配置は費用に効くので、そうと分かるように書く
        if stair_plan.count > stair_plan.required_count:
            a("")
            a(f"> 移動距離の目安を満たすだけなら{stair_plan.required_count}箇所で足ります"
              f"（現在{stair_plan.count}箇所）。各面配置などの方針で増えている分です。")
        for w in stair_plan.warnings:
            a(f"- ⚠️ {w}")
    a("")
    a("## 法規チェック")
    a("")
    a("| # | 項目 | 判定 | 内容 | 根拠 |")
    a("|---|---|---|---|---|")
    for c in checks:
        mark = {"OK": "✅", "WARN": "⚠️", "NG": "❌"}.get(c.status, c.status)
        a(f"| {c.check_id} | {c.name} | {mark} {c.status} | {c.message} | {c.basis} |")
    a("")
    a("## 壁つなぎ")
    a("")
    v_lim, h_lim, tie_basis = model.wall_tie_limits()
    v_max, h_max = model.wall_tie_max_spacing()
    a(f"- 本数: {len(model.wall_ties)}箇所")
    a(f"- 実配置の最大間隔: 垂直{v_max:.0f}mm × 水平{h_max:.0f}mm "
      f"（法定 垂直{v_lim:.0f} × 水平{h_lim:.0f}以下）")
    a(f"- 根拠: {tie_basis}")
    untied = model.edges_without_wall_ties()
    if untied:
        a("- ⚠️ 壁つなぎが入らない面: "
          + "、".join(f"辺{i}" for i in untied)
          + "（両隣の面にコーナー経由で支持される前提。単管等での別途拘束を検討）")

    if structural is not None:
        w, t, ps = structural.wind, structural.wall_tie, structural.post
        a("")
        a("## 構造計算（有資格者の確認前提の下書き）")
        a("")
        a(f"- 設計風速 V = {w.v_design_ms}m/s（V0={w.v0_ms} × K={w.k_height} "
          f"× E={w.e_adjacent} × S={w.s_region}）／速度圧 q = {w.q_n_m2}N/m²")
        a(f"- 風力係数 C = {w.c_force}（養生材 {structural.site.sheet_type}・充実率{w.fill_ratio}）")
        a("")
        a("| 検定 | 作用 | 許容 | 検定比 | 判定 |")
        a("|---|---|---|---|---|")
        a(f"| 壁つなぎ | {t.force_kn}kN | {t.allowable_increased_kn}kN（×1.3） "
          f"| {t.ratio} | {'✅ OK' if t.ok else '❌ NG'} |")
        a(f"| 建地圧縮 | {ps.total_kn}kN | {ps.allowable_kn}kN "
          f"| {ps.ratio} | {'✅ OK' if ps.ok else '❌ NG'} |")
        a("")
        a(f"- 支配的な壁つなぎ: {t.governing or '—'}（支配面積{t.tributary_area_m2}m²）")
        a(f"- 建地の支配検定: {ps.governing}")
        a(f"- 建地1本の内訳: 自重{ps.dead_load_kn}kN ＋ 積載{ps.live_load_kn}kN"
          + (f" ＋ 局所{ps.extra_load_kn}kN" if ps.extra_load_kn > 0 else ""))
        for wmsg in structural.warnings:
            a(f"- ⚠️ {wmsg}")

    if terrain is not None and terrain.gl_difference_mm > 0:
        a("")
        a("## 敷地の高低差")
        a("")
        a(f"- 高低差: {terrain.gl_difference_mm:.0f}mm "
          f"／ 脚部構成 {len({f.koma_offset for f in terrain.feet})}種類")
        a(f"- ジャッキ繰出し: {terrain.jack_min_mm:.0f}〜{terrain.jack_max_mm:.0f}mm")
        need_plate = [f for f in terrain.feet if abs(f.base_plate_adjust_mm) > 1e-6]
        if need_plate:
            a(f"- 敷板・床掘りでの調整が要る支柱: {len(need_plate)}本"
              "（支柱ごとの量はジャッキ量一覧CSV）")
        a("- 作業床レベルは全周で通し、高低差は支柱ごとのジャッキと支柱長で吸収しています")

    extras = []
    if bracket_sections:
        extras.append(f"ブラケット区間 {len(bracket_sections)}箇所")
    if platforms is not None and platforms.stages:
        extras.append(f"荷受けステージ {len(platforms.stages)}基")
    if platforms is not None and platforms.hoists:
        extras.append(f"昇降機 {len(platforms.hoists)}基")
    if openings is not None and openings.openings:
        extras.append(f"開口部（梁枠）{len(openings.openings)}箇所")
    if extras:
        a("")
        a("## 付帯設備")
        a("")
        a("- " + "／".join(extras))
        if platforms is not None and platforms.max_post_load_kn > 0:
            a(f"- ステージ直下の建地に加わる軸力: {platforms.max_post_load_kn:.2f}kN"
              f"（{platforms.governing}）")
        if openings is not None and openings.removed_posts:
            a(f"- 開口部で抜いた支柱: {openings.removed_posts}本"
              "（両端支柱の補強・梁枠上の積載荷重低減が必要）")

    a("")
    a("## 数量サマリ")
    a("")
    a(f"- 総重量: {quantity.total_weight_kg}kg / トラック概算: 4t車{quantity.truck_count}台")
    a(f"- 架け面積: {quantity.kake_menseki_m2}m²（(外周+4m)×(高さ+0.5m)）")
    for n in quantity.notes:
        a(f"- 注記: {n}")
    a("")
    a("> 本レポートは計画作成参画者（有資格者）が確認する前提の下書きです。")
    a("> 部材形状はカタログ寸法からの再現であり、単位重量は概算値を含みます。")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_jack_table_csv(terrain, path: Path) -> None:
    """支柱ごとのジャッキ量一覧（敷地高低差対応・本ツールの差別化機能）."""
    from .terrain import jack_table_rows

    rows = jack_table_rows(terrain)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)
        w.writerow([])
        w.writerow(["基準GL(mm)", round(terrain.reference_gl_mm, 1)])
        w.writerow(["GL範囲(mm)", round(terrain.gl_range_mm[0], 1),
                    round(terrain.gl_range_mm[1], 1)])
        w.writerow(["高低差(mm)", round(terrain.gl_difference_mm, 1)])
        w.writerow(["ジャッキ繰出し範囲(mm)", round(terrain.jack_min_mm, 1),
                    round(terrain.jack_max_mm, 1)])
        for note in terrain.warnings:
            w.writerow(["注記", note])


def write_plan_json(model: ScaffoldModel, path: Path) -> None:
    """GDL配置・再編集用の機械可読データ."""
    data = {
        "series_id": model.master.series_id,
        "koma_pitch": model.master.koma_pitch,
        "scaffold_height_mm": model.scaffold_height_mm,
        "elevation": {
            "jack_extension": model.elevation.jack_extension,
            "posts": model.elevation.posts,
            "posts_alt": model.elevation.posts_alt,
            "level_heights": model.elevation.level_heights,
            "first_ledger_height": model.elevation.first_ledger_height,
        },
        "edges": [
            {
                "edge_index": ep.edge_index,
                "spans": ep.spans,
                "scaffold_length": ep.scaffold_length,
                "standoff": ep.standoff,
                "start_post": list(ep.start_post),
                "end_post": list(ep.end_post),
                "remedy": ep.remedy,
            }
            for ep in model.plan.edges
        ],
        "scaffold_vertices": [list(v) for v in model.plan.scaffold_vertices],
        "wall_ties": [asdict(t) for t in model.wall_ties],
        "warnings": model.plan.warnings + model.elevation.warnings,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
