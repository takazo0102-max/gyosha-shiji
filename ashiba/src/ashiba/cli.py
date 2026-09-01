"""ワンクリック実行CLI: 入力JSON → 割付・法規チェック・数量CSV・レポート一式.

使い方:
    python3 -m ashiba.cli examples/rect_30x20.json --out out/

入力JSONスキーマ（examples/参照）:
{
  "project_name": "サンプル",
  "series_id": "shinwa_A",
  "outline_mm": [[0,0],[30000,0],[30000,20000],[0,20000]],
  "eaves_height_mm": 15400,        // 軒高
  "guard_extra_mm": 900,           // 軒高に足す手すり分（最上層作業床固定点）
  "building_height_mm": 16000,     // 架け面積用（省略時は足場高さ）
  "period_days": 90,
  "standoff": {"target": 300, "min": 250, "max": 350, "hard_min": 200},
  "deck_widths": [400, 250],
  "clearance_space_mm": 2000,
  "scaffold_form": "本足場",
  "n_stairs": 1
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .elevation_solver import solve_elevation
from .law_check import run_all_checks, summary
from .master import load_master
from .model import ScaffoldConfig, ScaffoldModel
from .plan_solver import StandoffSpec, solve_plan
from .quantity import take_off
from .report import (
    notification_required,
    write_plan_json,
    write_quantity_csv,
    write_report_md,
)


def build_model(spec: dict, master_csv: Path | None = None) -> ScaffoldModel:
    master = load_master(spec.get("series_id", "shinwa_A"), master_csv)
    so = spec.get("standoff", {})
    standoff = StandoffSpec(
        target=so.get("target", 300),
        min=so.get("min", 250),
        max=so.get("max", 350),
        hard_min=so.get("hard_min", 200),
    )
    plan = solve_plan(spec["outline_mm"], master, standoff)
    required = int(spec["eaves_height_mm"]) + int(spec.get("guard_extra_mm", 2 * master.koma_pitch))
    elevation = solve_elevation(required, master=master)
    config = ScaffoldConfig(
        scaffold_form=spec.get("scaffold_form", "本足場"),
        deck_widths=tuple(spec.get("deck_widths", (400, 250))),
        n_stairs=spec.get("n_stairs", 1),
        period_days=spec.get("period_days", 60),
    )
    return ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elevation,
        config=config,
        building_height_mm=float(spec.get("building_height_mm", 0)),
        clearance_space_mm=float(spec.get("clearance_space_mm", 2000)),
    )


def run(input_path: Path, out_dir: Path, master_csv: Path | None = None) -> dict:
    spec = json.loads(Path(input_path).read_text(encoding="utf-8"))
    model = build_model(spec, master_csv)
    checks = run_all_checks(model)
    quantity = take_off(model)

    out_dir.mkdir(parents=True, exist_ok=True)
    name = spec.get("project_name", "ashiba")
    write_quantity_csv(quantity, out_dir / f"{name}_数量表.csv")
    write_report_md(model, quantity, checks, out_dir / f"{name}_割付レポート.md", name)
    write_plan_json(model, out_dir / f"{name}_plan.json")

    s = summary(checks)
    return {
        "project": name,
        "posts_per_level": model.plan.total_posts,
        "levels": model.elevation.n_levels,
        "scaffold_height_mm": model.scaffold_height_mm,
        "checks": s,
        "notification_required": notification_required(model),
        "total_weight_kg": quantity.total_weight_kg,
        "kake_menseki_m2": quantity.kake_menseki_m2,
        "out_dir": str(out_dir),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="仮設足場 割付・法規チェック・数量拾い")
    ap.add_argument("input", type=Path, help="入力JSON")
    ap.add_argument("--out", type=Path, default=Path("out"), help="出力ディレクトリ")
    ap.add_argument("--master", type=Path, default=None, help="部材マスタCSV（省略時は同梱）")
    args = ap.parse_args(argv)
    result = run(args.input, args.out, args.master)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
