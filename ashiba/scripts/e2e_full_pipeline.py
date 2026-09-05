"""実機E2E（全機能通し）: Archicadの躯体スラブから設置届一式まで.

Phase 1〜4の全機能を1本で通す最終検証:
  スラブ作成 → 外形取得 → 平面/立面割付 → 壁つなぎ最適化 → 階段自動配置
  → 敷地高低差(ジャッキ量) → 荷受けステージ → 法規12項目 → 構造計算
  → 足場ライン配置 → 詳細図配置 → 帳票一式出力 → プレビュー保存

使い方: python3 scripts/e2e_full_pipeline.py [--keep] [--series=shinwa_A|nikken_nd1800|...]
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.cli import build_verdict, collect_warnings  # noqa: E402
from ashiba.details import required_details  # noqa: E402
from ashiba.elevation_solver import solve_elevation  # noqa: E402
from ashiba.law_check import run_all_checks, summary  # noqa: E402
from ashiba.master import load_master  # noqa: E402
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel  # noqa: E402
from ashiba.openings import validate_openings  # noqa: E402
from ashiba.notification import (  # noqa: E402
    NotificationInfo,
    notification_required,
    write_notification_xlsx,
)
from ashiba.plan_solver import solve_plan  # noqa: E402
from ashiba.platforms import LoadingStage, validate_platforms  # noqa: E402
from ashiba.quantity import take_off  # noqa: E402
from ashiba.report import (  # noqa: E402
    write_jack_table_csv,
    write_plan_json,
    write_quantity_csv,
    write_report_md,
)
from ashiba.stairs import auto_place_stairs  # noqa: E402
from ashiba.structural import SiteCondition, optimize_wall_ties, run_structural  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    ArchicadClient,
    TapirError,
    _extract_polygon,
    place_details,
    place_elevations,
    place_scaffold_lines,
    read_ground_model,
)
from ashiba.terrain import GroundModel, solve_post_feet  # noqa: E402

# 検証する部品は毎回HSFからコンパイルして注入する。部品名を固定で埋め込むと、
# 更新を忘れたまま古いGSMを検証し続ける（実際そうなっていた）。
SLAB_POLY_MM = [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]


def main() -> None:
    keep = "--keep" in sys.argv
    series = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--series=")), "shinwa_A")
    out = ROOT / "out" / ("e2e_full" if series == "shinwa_A" else f"e2e_full_{series}")
    out.mkdir(parents=True, exist_ok=True)
    placed: list[dict] = []

    c = ArchicadClient()
    assert c.is_alive(), "Archicadが応答しません"
    print(f"Tapir {c.tapir_version()} 接続OK")

    # --- 0. 現在のHSFをコンパイルして埋め込みライブラリへ ---
    sys.path.insert(0, str(ROOT / "scripts"))
    from dev_gsm_iterate import build_current_gsm

    work = ROOT / "out" / "gsm_dev"
    work.mkdir(parents=True, exist_ok=True)
    objects = {}
    for part in ("ashiba_line", "ashiba_detail"):
        name, gsm = build_current_gsm(part, work)
        try:
            c.add_file_to_embedded_library(str(gsm), gsm.name)
        except TapirError:
            pass   # 同じ内容なら既に入っている（部品名は内容ハッシュ）
        objects[part] = name
    LINE_OBJECT = objects["ashiba_line"]
    DETAIL_OBJECT = objects["ashiba_detail"]
    print(f"0. 現行GDLを注入: {LINE_OBJECT} / {DETAIL_OBJECT}")

    # --- 1. 躯体スラブ ---
    slab = c.create_slab(SLAB_POLY_MM)
    placed.append(slab)
    det = c.get_details([slab])[0]
    poly = _extract_polygon(det)
    assert poly, "外形が取れません"
    outline_mm = [(x * 1000.0, y * 1000.0) for (x, y) in poly]
    print(f"1. 躯体スラブ作成・外形取得: {len(outline_mm)}点")

    # --- 2. 割付 ---
    master = load_master(series)
    plan = solve_plan(outline_mm, master)
    print(f"   系列 {series}（コマ{master.koma_pitch}・階高{master.floor_height}・スパン{master.span_lengths()}）")
    elevation = solve_elevation(16300, master=master)
    model = ScaffoldModel(
        master=master, plan=plan, elevation=elevation,
        config=ScaffoldConfig(period_days=90, asagao=AsagaoSpec(stages=1)),
        building_height_mm=16000,
    )
    print(f"2. 割付: 支柱{plan.total_posts}位置/層・{elevation.n_levels}層・"
          f"H{model.scaffold_height_mm}mm")

    # --- 3. 壁つなぎ最適化 → 階段 → 地形 → ステージ ---
    site = SiteCondition(region="関東(沿岸)", sheet_type="メッシュシート")
    tie_opt = optimize_wall_ties(model, site)
    print(f"3. 壁つなぎ: {tie_opt.tie_count}箇所 検定比{tie_opt.wall_tie.ratio}")

    stair_plan = auto_place_stairs(model)
    print(f"4. 階段: {stair_plan.count}箇所 最大移動{stair_plan.max_travel_mm / 1000:.1f}m")

    ground = read_ground_model(c)
    if ground.is_flat:
        ground = GroundModel(points=[
            (x, y, -(x - 300000) * 0.02)
            for x in (300000, 315000, 331000) for y in (300000, 321000)
        ])
        print("5. 敷地: メッシュ無し → 検証用の斜面(高低差約0.6m)を仮定")
    terrain = solve_post_feet(model, ground)
    print(f"   高低差{terrain.gl_difference_mm:.0f}mm ジャッキ"
          f"{terrain.jack_min_mm:.0f}〜{terrain.jack_max_mm:.0f}mm "
          f"脚部{len({f.koma_offset for f in terrain.feet})}種")

    # ステージの始点は辺0の4本目の支柱（系列でスパンが違うので位置から出す）
    stage_start = float(sum(plan.edges[0].spans[:4]))
    stages = [LoadingStage(edge_index=0, start_mm=stage_start, span_count=2, levels=[3])]
    platforms = validate_platforms(model, stages)
    from ashiba.ties import merge_attachment_ties
    merge_attachment_ties(model, platforms)
    print(f"6. 荷受けステージ: {len(stages)}基 直下建地+{platforms.max_post_load_kn:.2f}kN")

    # --- 4. 検査と数量 ---
    checks = run_all_checks(model, stair_plan=stair_plan, terrain=terrain)
    quantity = take_off(model, stair_plan=stair_plan, platforms=platforms, terrain=terrain)
    structural = run_structural(
        model, quantity, site, platforms=platforms, terrain=terrain
    )
    s = summary(checks)
    why = ""
    if not structural.all_ok and not structural.post.ok and not structural.post.verified:
        # 一般値で不足しているだけなら、それが理由だと行の中で言う（末尾の1行だけだと見落とす）
        why = "（建地の許容支持力が未確認の一般値。認定値を capacity.csv に入れて再判定）"
    print(f"7. 法規: OK{s['ok']} WARN{s['warn']} NG{s['ng']} / "
          f"構造: 壁つなぎ{structural.wall_tie.ratio} 建地{structural.post.ratio} "
          f"→ {'成立' if structural.all_ok else '不成立' + why}")
    print(f"8. 数量: {len(quantity.lines)}品目 {quantity.total_weight_kg}kg "
          f"4t車{quantity.truck_count}台 架け面積{quantity.kake_menseki_m2}m²")

    # --- 5. Archicadへ配置 ---
    lines = place_scaffold_lines(
        model, LINE_OBJECT, c, stair_plan=stair_plan, platforms=platforms,
        terrain=terrain,
    )
    placed += lines
    print(f"9. 足場ライン配置: {len(lines)}本")

    elevs = place_elevations(
        model, LINE_OBJECT, origin_mm=(300000, 250000),
        floor_levels_mm=[3000, 6000, 9000, 12000, 15000],
        face_names=["南面", "東面", "北面", "西面"], client=c,
        stair_plan=stair_plan, platforms=platforms, terrain=terrain,
    )
    placed += elevs
    print(f"10. 立面図配置: {len(elevs)}面")

    sheets = required_details(model, terrain=terrain)
    details = place_details(
        model, sheets, DETAIL_OBJECT, origin_mm=(300000, 280000), client=c
    )
    placed += details
    print(f"11. 詳細図配置: {len(details)}枚 "
          f"({', '.join(d.key for d in sheets)})")

    # --- 6. 帳票 ---
    name = "E2E全機能"
    write_quantity_csv(quantity, out / f"{name}_数量表.csv")
    openings = validate_openings(model, [])
    warnings = collect_warnings(
        structural, model, [], stair_plan, [], openings, terrain, platforms,
        checks, quantity,
    )
    verdict = build_verdict(s, structural, platforms, openings, [], warnings)
    write_report_md(
        model, quantity, checks, out / f"{name}_割付レポート.md", name,
        stair_plan=stair_plan, structural=structural, terrain=terrain,
        platforms=platforms, verdict=verdict, warnings=warnings,
    )
    write_plan_json(
        model, out / f"{name}_plan.json",
        stair_plan=stair_plan, terrain=terrain, platforms=platforms,
    )
    write_jack_table_csv(terrain, out / f"{name}_ジャッキ量一覧.csv")
    write_notification_xlsx(
        model, quantity, checks, structural, out / f"{name}_設置届一式.xlsx",
        name, NotificationInfo(site_name="E2E検証"), sheets, terrain,
        verdict=verdict, warnings=warnings,
        stair_plan=stair_plan, platforms=platforms,
    )
    files = sorted(p.name for p in out.glob(f"{name}_*"))
    print(f"12. 帳票出力: {len(files)}件 {files}")
    print(f"    設置届: {'要' if notification_required(model, terrain) else '不要'}")
    print(f"    総合判定: {'成立' if verdict['ok'] else '是正が必要'}"
          f" 要確認{verdict['warn']}件 {verdict['warn_breakdown']}")

    # --- 7. プレビュー ---
    for label, elem in (("足場ライン", lines[0]), ("立面図", elevs[0]),
                        ("詳細図(脚部)", details[0])):
        for img in ("3D", "2D") if label == "足場ライン" else ("2D",):
            resp = c.tapir(
                "GetElementPreviewImage",
                {"elementId": elem["elementId"], "imageType": img,
                 "width": 900, "height": 900},
            )
            p = out / f"{label}_{img}.png"
            p.write_bytes(base64.b64decode(resp["previewImage"]))
            print(f"13. プレビュー保存: {p.name}")

    if not keep:
        c.delete_elements(placed)
        print(f"テスト要素 {len(placed)}個を削除（--keep で残せます）")

    # このシナリオは斜面（ジャッキ約400mm）＋1tの荷受けステージをくさび支柱に載せる。
    # くさび支柱は一般値6.86kN（信和の認定値はカタログ非公開）なので建地圧縮は是正になる。
    # それはツールの正しい判定なので、是正の理由が建地圧縮だけなら通し検証は成功とする
    blockers = verdict["blockers"]
    ok = verdict["ok"] or all("建地圧縮" in b for b in blockers)
    if not verdict["ok"] and ok:
        print("    （是正の理由は建地圧縮のみ: くさび支柱の一般値による。"
              "信和の認定値を capacity.csv に入れて再判定する）")
    print("\nE2E全機能 " + ("成功" if ok else "失敗"))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
