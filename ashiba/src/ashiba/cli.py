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
import datetime as _dt
import json
import sys
from pathlib import Path

from .brackets import BracketSection, validate_bracket_sections
from .elevation_solver import solve_elevation
from .law_check import required_asagao_stages, run_all_checks, summary
from .master import load_master
from .model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from .notification import (
    NotificationInfo,
    notification_required,
    write_notification_xlsx,
)
from .plan_solver import StandoffSpec, solve_plan
from .quantity import take_off
from .report import write_plan_json, write_quantity_csv, write_report_md
from .stairs import DEFAULT_MAX_TRAVEL_MM, auto_place_stairs, validate_stairs
from .structural import SiteCondition, optimize_wall_ties, run_structural


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
        # 未指定なら系列の既定（A:400/250、B:405/240、次世代:500）を使う
        deck_widths=(tuple(spec["deck_widths"]) if spec.get("deck_widths") else None),
        next_gen=spec.get("next_gen", False),
        n_stairs=spec.get("n_stairs", 1),
        period_days=spec.get("period_days", 60),
        asagao=build_asagao(spec, elevation.total_height),
    )
    return ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elevation,
        config=config,
        building_height_mm=float(spec.get("building_height_mm", 0)),
        clearance_space_mm=float(spec.get("clearance_space_mm", 2000)),
    )


def build_asagao(spec: dict, height_mm: int) -> AsagaoSpec | None:
    """朝顔の入力。指定がなければ高さから必要段数を自動設定する（10m以上で1段・20m以上で2段）."""
    a = spec.get("asagao")
    if a is False:  # 明示的に「設置しない」
        return None
    need = required_asagao_stages(height_mm)
    if a is None:
        return AsagaoSpec(stages=need) if need else None
    return AsagaoSpec(
        stages=a.get("stages", need),
        projection_mm=a.get("projection_mm", 2000.0),
        angle_deg=a.get("angle_deg", 25.0),
        tie_every_spans=a.get("tie_every_spans", 2),
    )


def build_brackets(spec: dict) -> list[BracketSection]:
    """ブラケット区間の入力（面の区間属性。支柱ラインは動かさない）."""
    out = []
    for b in spec.get("bracket_sections", []):
        out.append(BracketSection(
            edge_index=b["edge_index"],
            start_mm=float(b["start_mm"]),
            end_mm=float(b["end_mm"]),
            direction=b.get("direction", "内"),
            width=b.get("width", 600),
            deck_width=b.get("deck_width"),
            levels=b.get("levels", []),
            has_hozue=b.get("has_hozue", False),
            is_widening=b.get("is_widening", False),
            on_kessokubu=b.get("on_kessokubu", False),
            reason=b.get("reason", ""),
        ))
    return out


def build_site(spec: dict) -> SiteCondition:
    """入力JSONの site ブロック → 構造計算の追加入力4項目."""
    s = spec.get("site", {})
    return SiteCondition(
        region=s.get("region", "関東(内陸)"),
        v0_ms=s.get("v0_ms"),
        roughness=s.get("roughness", "III"),
        sheet_type=s.get("sheet_type", "メッシュシート"),
        adjacent_factor=s.get("adjacent_factor", 1.0),
        region_factor=s.get("region_factor", 1.0),
        gamma=s.get("gamma", 0.0),
        correction_f=s.get("correction_f", 1.0),
        period_days=spec.get("period_days", 60),
        simultaneous_loaded_levels=s.get("simultaneous_loaded_levels", 2),
    )


def build_notification_info(spec: dict) -> NotificationInfo:
    n = spec.get("notification", {})
    start = n.get("start_date")
    return NotificationInfo(
        business_type=n.get("business_type", ""),
        site_name=n.get("site_name", ""),
        site_address=n.get("site_address", ""),
        worker_count=str(n.get("worker_count", "")),
        planner_name=n.get("planner_name", ""),
        planner_career=n.get("planner_career", ""),
        start_date=_dt.date.fromisoformat(start) if start else None,
        contractor=n.get("contractor", ""),
        labor_office=n.get("labor_office", ""),
    )


def run(input_path: Path, out_dir: Path, master_csv: Path | None = None) -> dict:
    spec = json.loads(Path(input_path).read_text(encoding="utf-8"))
    model = build_model(spec, master_csv)
    site = build_site(spec)
    # 壁つなぎは風荷重の検定から逆算して確定させる（数量・法規チェックに反映するため先に実行）
    tie_opt = optimize_wall_ties(model, site)
    brackets = build_brackets(spec)
    bracket_issues = validate_bracket_sections(model, brackets)
    st = spec.get("stairs", {})
    stair_plan = auto_place_stairs(
        model,
        max_travel_mm=st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM),
        tower_spans=st.get("tower_spans", 2),
        count=st.get("count"),
    )
    stair_issues = validate_stairs(
        model, stair_plan, st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM)
    )
    checks = run_all_checks(model)
    quantity = take_off(model, bracket_sections=brackets, stair_plan=stair_plan)
    structural = run_structural(model, quantity, site)

    out_dir.mkdir(parents=True, exist_ok=True)
    name = spec.get("project_name", "ashiba")
    write_quantity_csv(quantity, out_dir / f"{name}_数量表.csv")
    write_report_md(model, quantity, checks, out_dir / f"{name}_割付レポート.md", name)
    write_plan_json(model, out_dir / f"{name}_plan.json")
    write_notification_xlsx(
        model, quantity, checks, structural,
        out_dir / f"{name}_設置届一式.xlsx", name, build_notification_info(spec),
    )

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
        "structural": {
            "design_wind_speed_ms": structural.wind.v_design_ms,
            "wind_pressure_n_m2": structural.wind.q_n_m2,
            "wall_tie_ratio": structural.wall_tie.ratio,
            "post_ratio": structural.post.ratio,
            "all_ok": structural.all_ok,
            "unverified_capacity_used": structural.unverified_used,
        },
        "wall_ties": {
            "count": len(model.wall_ties),
            "span_step": tie_opt.span_step,
            "level_step": tie_opt.level_step,
            "message": tie_opt.message,
        },
        "asagao": (
            {"stages": model.config.asagao.stages,
             "projection_mm": model.config.asagao.projection_mm,
             "angle_deg": model.config.asagao.angle_deg}
            if model.config.asagao else None
        ),
        "bracket_sections": len(brackets),
        "stairs": {
            "count": stair_plan.count,
            "required_count": stair_plan.required_count,
            "max_travel_m": round(stair_plan.max_travel_mm / 1000.0, 1),
            "positions": [
                {"edge_index": t.edge_index, "start_mm": round(t.start_mm),
                 "spans": t.span_count}
                for t in stair_plan.towers
            ],
        },
        "warnings": (
            structural.warnings + model.plan.warnings + model.elevation.warnings
            + [f"ブラケット[{i.severity}] {i.message}（{i.basis}）" for i in bracket_issues]
            + stair_plan.warnings + [f"階段: {w}" for w in stair_issues]
        ),
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
