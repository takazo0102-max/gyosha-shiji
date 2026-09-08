"""Archicadツールバー割当用スクリプト（Tapirのスクリプト割当機能でボタン化する）.

操作モデル（GLOOBE踏襲）:
  躯体スラブを選択 → このスクリプトを実行 → 足場ライン一括生成＋帳票一式出力

CLI（python3 -m ashiba.cli）と同じ solve_all/write_outputs を通すので、
ボタンから出る成果物もCLIと同じ（壁つなぎ最適化・階段・敷地・構造計算・
総合判定・設置届まで）。以前はこのスクリプトだけ手順を書き下しており、
構造計算も総合判定も無い薄いレポートしか出ていなかった。

条件（系列・軒高・開口部など）はデスクトップの ashiba_spec.json（入力JSONと同じキー）で
上書きできる。無ければ下の SPEC の既定値。系列だけなら --series=nikken_nd1800 でも指定できる。

部品（gdl/ashiba_line.gsm・ashiba_detail.gsm）は無ければ自動で埋め込みライブラリへ入れる
（配置パイプライン自体は Archicad 28 + Tapir 1.5.8 でE2E検証済み:
 scripts/e2e_archicad_test.py）。
"""

import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.cli import result_dict, solve_all, write_outputs  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    ArchicadClient,
    get_selected_outline_mm,
    place_details,
    place_elevations,
    place_scaffold_lines,
    read_ground_model,
)

# ---- 条件入力（Phase 2でUIダイアログ化。当面はここを編集する） ----
# キー名と既定値は入力JSONと同じ（ashiba/cli.py のスキーマ参照）
SPEC = {
    "project_name": "足場計画",
    "series_id": "shinwa_A",
    "eaves_height_mm": 15400,      # 軒高
    "guard_extra_mm": 900,         # 最上層作業床固定点 = 軒高 + 手すり分
    "period_days": 90,
    "site": {"region": "関東(内陸)", "sheet_type": "メッシュシート"},
}
LINE_OBJECT = "ashiba_line"
DETAIL_OBJECT = "ashiba_detail"
PLACE_DETAILS = True               # 詳細図も並べるか
PLACE_ELEVATIONS = True            # 各面の立面図も並べるか
FLOOR_LEVELS_MM: list[float] = []  # 立面に描く各階レベル（空なら描かない）
# 図面の並べ先。躯体外形の左下から下方向へ、立面→詳細図の順に置く
ELEVATION_OFFSET_MM = -45000.0
DETAIL_OFFSET_MM = -20000.0
OUT_DIR = Path.home() / "Desktop" / "ashiba_out"
# 条件をスクリプトを編集せずに変えるための上書きファイル（存在すれば SPEC に重ねる）。
# 中身は入力JSONと同じキー（series_id・eaves_height_mm・site・openings 等。outline_mm は
# 選択したスラブから取るので無視）。環境変数 ASHIBA_SPEC でパスを差し替えられる
SPEC_OVERRIDE = Path(os.environ.get("ASHIBA_SPEC", str(Path.home() / "Desktop" / "ashiba_spec.json")))


def load_spec_override() -> dict:
    """上書きファイルを読む。無ければ空、壊れていれば理由を出して空."""
    if not SPEC_OVERRIDE.exists():
        return {}
    try:
        data = json.loads(SPEC_OVERRIDE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"条件の上書きファイル {SPEC_OVERRIDE} を読めません（{e}）。既定の条件で続けます")
        return {}
    if not isinstance(data, dict):
        print(f"条件の上書きファイル {SPEC_OVERRIDE} はオブジェクトではありません。既定の条件で続けます")
        return {}
    data.pop("outline_mm", None)
    print(f"条件の上書き: {SPEC_OVERRIDE}（{', '.join(sorted(data))}）")
    return data


def main() -> None:
    client = ArchicadClient()
    spec = dict(SPEC)
    spec.update(load_spec_override())
    for a in sys.argv[1:]:
        if a.startswith("--series="):
            spec["series_id"] = a.split("=", 1)[1]
    spec["outline_mm"] = [list(p) for p in get_selected_outline_mm(client)]
    # 同梱の配布GSM（足場ライン・詳細図）を埋め込みライブラリに入れる。手で読み込んで
    # いなくても止まらないように（既に入っていれば何もしない）
    GDL_DIR = Path(__file__).resolve().parents[1] / "gdl"
    added = client.ensure_embedded_parts([GDL_DIR / f"{LINE_OBJECT}.gsm", GDL_DIR / f"{DETAIL_OBJECT}.gsm"])
    if added:
        print(f"配布GSMを埋め込みライブラリへ追加: {', '.join(added)}")
    # 敷地メッシュがあれば高低差を拾う（無ければ平坦として解く）
    ground = read_ground_model(client)
    if not ground.is_flat:
        spec["ground_points_mm"] = [list(p) for p in ground.points]

    r = solve_all(spec)
    write_outputs(r, OUT_DIR)
    result = result_dict(r, OUT_DIR)

    lines = place_scaffold_lines(
        r.model, LINE_OBJECT, client, stair_plan=r.stair_plan,
        openings=r.openings, platforms=r.platforms, bracket_sections=r.brackets,
        terrain=r.terrain,
    )
    x0 = min(v[0] for v in r.model.plan.outline.vertices)
    y0 = min(v[1] for v in r.model.plan.outline.vertices)
    elevs = []
    if PLACE_ELEVATIONS:
        # 面名は指定しなければ方位（南面・東面…）が入る
        elevs = place_elevations(
            r.model, LINE_OBJECT, stair_plan=r.stair_plan, openings=r.openings,
            platforms=r.platforms, bracket_sections=r.brackets, terrain=r.terrain,
            origin_mm=(x0, y0 + ELEVATION_OFFSET_MM),
            floor_levels_mm=FLOOR_LEVELS_MM or None, client=client,
        )
    details = []
    if PLACE_DETAILS:
        details = place_details(
            r.model, r.detail_sheets, DETAIL_OBJECT,
            origin_mm=(x0, y0 + DETAIL_OFFSET_MM), client=client,
        )

    # 同じスラブでの再実行は、前回の配置（同じ部品・同じ位置）を置き換える
    replaced = client.delete_stale_duplicates(lines + elevs + details)
    v = result["verdict"]
    print(f"足場ライン {len(lines)}本・立面図 {len(elevs)}面・"
          f"詳細図 {len(details)}枚を配置しました"
          + (f"（前回の配置{replaced}個を置き換え）" if replaced else ""))
    print("総合判定: " + ("成立" if v["ok"] else "是正が必要"))
    for b in v["blockers"]:
        print(f"  是正: {b}")
    if v["warn"]:
        print(f"  要確認 {v['warn']}件: " + "／".join(v["warn_breakdown"])
              + "（割付レポートの要確認一覧を参照）")
    print(f"帳票出力先: {OUT_DIR}")


if __name__ == "__main__":
    # CLI と同じく、入力・マスタ・耐力値・Archicad接続の失敗はトレースバックではなく
    # 原因と直し方を出して終了コード2で止める（上書きファイルの綴り違いもここに来る）
    from ashiba.cli import InputError
    from ashiba.geometry import ValidationError
    from ashiba.master import MasterDataError, SeriesLockError
    from ashiba.structural import CapacityError
    from ashiba.tapir_adapter import TapirError

    try:
        main()
    except (InputError, ValidationError, MasterDataError, SeriesLockError,
            CapacityError, TapirError) as e:
        print(f"[ashiba] {type(e).__name__}: {e}")
        raise SystemExit(2)
