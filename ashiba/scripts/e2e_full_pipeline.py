"""実機E2E（全機能通し）: Archicadの躯体スラブから設置届一式まで.

Phase 1〜4の全機能を1本で通す最終検証:
  スラブ作成 → 外形取得 → 平面/立面割付 → 壁つなぎ最適化 → 階段自動配置
  → 敷地高低差(ジャッキ量) → 荷受けステージ → 法規12項目 → 構造計算
  → 足場ライン配置 → 詳細図配置 → 帳票一式出力 → プレビュー保存

使い方: python3 scripts/e2e_full_pipeline.py [--keep] [--series=shinwa_A|nikken_nd1800|...] [--poly=rect|diagonal]
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.cli import solve_all, write_outputs  # noqa: E402
from ashiba.details import required_details  # noqa: E402
from ashiba.notification import notification_required  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    ArchicadClient,
    TapirError,
    _extract_polygon,
    place_details,
    place_elevations,
    place_scaffold_lines,
    read_ground_model,
)
from ashiba.terrain import GroundModel  # noqa: E402

# 検証する部品は毎回HSFからコンパイルして注入する。部品名を固定で埋め込むと、
# 更新を忘れたまま古いGSMを検証し続ける（実際そうなっていた）。
SLAB_POLY_MM = [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]


def main() -> None:
    keep = "--keep" in sys.argv
    series = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--series=")), "shinwa_A")
    # --poly=diagonal: 北東を斜めに切った五角形（斜辺の置き換え・届かない帯の経路を実機で通す）
    poly_kind = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--poly=")), "rect")
    slab_poly = SLAB_POLY_MM
    if poly_kind == "diagonal":
        slab_poly = [(300000, 300000), (330000, 300000), (330000, 312000), (320000, 320000), (300000, 320000)]
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
    slab = c.create_slab(slab_poly)
    placed.append(slab)
    det = c.get_details([slab])[0]
    poly = _extract_polygon(det)
    assert poly, "外形が取れません"
    outline_mm = [(x * 1000.0, y * 1000.0) for (x, y) in poly]
    print(f"1. 躯体スラブ作成・外形取得: {len(outline_mm)}点")

    # --- 2〜8. 計画（CLI・ツールバーと同じ solve_all で解く） ---
    # 以前はここに手順を書き下していて、最適化に載せる取付部の壁つなぎや開口部・
    # 渡した区間の寄せなど solve_all に足した処理が抜け、同じ形でCLIと違う検定比が
    # 出ていた（斜辺のスラブで壁つなぎ3.67 vs 0.57）。手順は1箇所に置く
    base_spec = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
    ground = read_ground_model(c)
    if ground.is_flat:
        ground = GroundModel(points=[
            (x, y, -(x - 300000) * 0.02)
            for x in (300000, 315000, 331000) for y in (300000, 321000)
        ])
        print("5. 敷地: メッシュ無し → 検証用の斜面(高低差約0.6m)を仮定")

    def spec_for(stages):
        sp = dict(base_spec)
        sp.update({
            "project_name": "E2E全機能", "series_id": series,
            "outline_mm": [[x, y] for (x, y) in outline_mm],
            "period_days": 90, "asagao": {"stages": 1},
            "site": {"region": "関東(沿岸)", "sheet_type": "メッシュシート"},
            "ground_points_mm": [list(pt) for pt in ground.points],
            "notification": {"site_name": "E2E検証"},
        })
        if stages:
            sp["loading_stages"] = stages
        return sp

    # ステージの始点は辺0の4本目の支柱（系列でスパンが違うので、一度解いて位置を取る）
    r0 = solve_all(spec_for(None))
    stage_start = float(sum(r0.model.plan.edges[0].spans[:4]))
    r = solve_all(spec_for([{"edge_index": 0, "start_mm": stage_start, "span_count": 2,
                             "levels": [3], "note": "E2E"}]))
    model, plan = r.model, r.model.plan
    master, elevation = model.master, model.elevation
    stair_plan, platforms, terrain = r.stair_plan, r.platforms, r.terrain
    quantity, structural, verdict = r.quantity, r.structural, r.verdict
    print(f"   系列 {series}（コマ{master.koma_pitch}・階高{master.floor_height}・スパン{master.span_lengths()}）")
    print(f"2. 割付: 支柱{plan.total_posts}位置/層・{elevation.n_levels}層・"
          f"H{model.scaffold_height_mm}mm")
    print(f"3. 壁つなぎ: {r.tie_opt.tie_count}箇所 検定比{r.tie_opt.wall_tie.ratio}")
    print(f"4. 階段: {stair_plan.count}箇所 最大移動{stair_plan.max_travel_mm / 1000:.1f}m")
    print(f"   高低差{terrain.gl_difference_mm:.0f}mm ジャッキ"
          f"{terrain.jack_min_mm:.0f}〜{terrain.jack_max_mm:.0f}mm "
          f"脚部{len({f.koma_offset for f in terrain.feet})}種")
    print(f"6. 荷受けステージ: {len(platforms.stages)}基 直下建地+{platforms.max_post_load_kn:.2f}kN")
    n_ok = sum(1 for k in r.checks if k.status == "OK")
    n_warn = sum(1 for k in r.checks if k.status == "WARN")
    n_ng = sum(1 for k in r.checks if k.status == "NG")
    why = ""
    if not structural.all_ok and not structural.post.ok and not structural.post.verified:
        # 一般値で不足しているだけなら、それが理由だと行の中で言う（末尾の1行だけだと見落とす）
        why = "（建地の許容支持力が未確認の一般値。認定値を capacity.csv に入れて再判定）"
    print(f"7. 法規: OK{n_ok} WARN{n_warn} NG{n_ng} / "
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

    # --- 6. 帳票（CLIと同じ write_outputs） ---
    name = "E2E全機能"
    write_outputs(r, out)
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
    else:
        # --keep の繰り返しで同じ位置に溜まらないよう、前回の残りは置き換える
        replaced = c.delete_stale_duplicates(placed)
        if replaced:
            print(f"前回の残り {replaced}個を置き換え")

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
