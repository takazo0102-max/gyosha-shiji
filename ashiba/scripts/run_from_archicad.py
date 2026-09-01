"""Archicadツールバー割当用スクリプト（Tapirのスクリプト割当機能でボタン化する）.

操作モデル（GLOOBE踏襲）:
  躯体スラブを選択 → このスクリプトを実行 → 足場ライン一括生成＋帳票出力

⚠️ Archicad実機での動作検証は未実施。tapir_adapter.py の注意書きを参照。
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.elevation_solver import solve_elevation  # noqa: E402
from ashiba.law_check import run_all_checks, summary  # noqa: E402
from ashiba.master import load_master  # noqa: E402
from ashiba.model import ScaffoldConfig, ScaffoldModel  # noqa: E402
from ashiba.plan_solver import solve_plan  # noqa: E402
from ashiba.quantity import take_off  # noqa: E402
from ashiba.report import write_plan_json, write_quantity_csv, write_report_md  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    get_selected_outline_mm,
    place_scaffold_lines,
)

# ---- 条件入力（Phase 2でUIダイアログ化。当面はここを編集する） ----
SERIES_ID = "shinwa_A"
EAVES_HEIGHT_MM = 15400     # 軒高
GUARD_EXTRA_MM = 900        # 最上層作業床固定点 = 軒高 + 手すり分
PERIOD_DAYS = 90
OUT_DIR = Path.home() / "Desktop" / "ashiba_out"


def main() -> None:
    master = load_master(SERIES_ID)
    outline = get_selected_outline_mm()
    plan = solve_plan(outline, master)
    elevation = solve_elevation(EAVES_HEIGHT_MM + GUARD_EXTRA_MM, master=master)
    model = ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elevation,
        config=ScaffoldConfig(period_days=PERIOD_DAYS),
        building_height_mm=EAVES_HEIGHT_MM,
    )

    ids = place_scaffold_lines(model)
    checks = run_all_checks(model)
    quantity = take_off(model)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_quantity_csv(quantity, OUT_DIR / "数量表.csv")
    write_report_md(model, quantity, checks, OUT_DIR / "割付レポート.md")
    write_plan_json(model, OUT_DIR / "plan.json")

    s = summary(checks)
    print(f"足場ライン {len(ids)}本を配置しました")
    print(f"法規チェック: OK {s['ok']} / WARN {s['warn']} / NG {s['ng']}")
    print(f"帳票出力先: {OUT_DIR}")


if __name__ == "__main__":
    main()
