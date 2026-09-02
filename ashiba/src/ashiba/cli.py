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
  "n_stairs": 1,
  "next_gen": false,               // 次世代足場（踏板幅が広い規格）
  "guard_rail_type": "布材",        // "布材"（＋中桟）／"先行手すり"
  // 開口部（省略可）。支柱を抜いて通路にする箇所。梁枠は規格品のみ
  "openings": [
    {"edge_index": 0, "start_mm": 3600, "beam_span_mm": 3600, "reason": "現場出入口"}
  ],
  // 朝顔（省略時は高さから自動。false で明示的に設置しない）
  "asagao": {"stages": 1, "projection_mm": 2000, "angle_deg": 25, "tie_every_spans": 2},
  // ブラケット区間（面の区間属性。支柱ラインは動かさない）
  "bracket_sections": [
    {"edge_index": 0, "start_mm": 0, "end_mm": 5400, "direction": "内",
     "width": 300, "deck_width": 500, "levels": [1], "has_hozue": false,
     "is_widening": false, "on_kessokubu": false}
  ],
  // 荷受けステージ・昇降機
  "loading_stages": [
    {"edge_index": 0, "start_mm": 12600, "span_count": 2, "projection_mm": 1500,
     "load_kn": 9.8, "levels": [3]}
  ],
  "hoists": [{"edge_index": 2, "position_mm": 14400, "tie_every_mm": 3600}],
  // 敷地の標高サンプル [[x,y,z], ...]（Archicad連携時は敷地メッシュから自動）
  "ground_points_mm": [[0, 0, 0], [30000, 0, 400]],
  // 構造計算の追加入力（省略時は既定値。地域区分だけでも入れる）
  "site": {"region": "関東(沿岸)", "roughness": "III", "sheet_type": "メッシュシート",
           "adjacent_factor": 1.0, "region_factor": 1.0,
           "simultaneous_loaded_levels": 2},
  // 様式第20号の人が書く欄（分かる範囲で事前入力できる）
  "notification": {"business_type": "", "site_name": "", "start_date": "2026-11-01",
                   "planner_name": "", "labor_office": ""},
  // 階段（省略可）。positions を書けば手動配置、書かなければ自動配置
  "stairs": {
    "count": 2,              // 箇所数。省略時は移動距離30m以内から自動算出
    "tower_spans": 2,        // 階段室が占有するスパン数
    "max_travel_mm": 30000,  // 昇降設備までの水平移動距離の目安
    "min_per_face": 1,       // 各面に最低1箇所（法規ではなく実務上の配慮）
    "positions": [{"edge_index": 0, "start_mm": 3600, "span_count": 2}]
  }
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
from .model import (
    GUARD_RAIL_LEDGER,
    AsagaoSpec,
    ScaffoldConfig,
    ScaffoldModel,
)
from .openings import Opening, opening_detail_specs, validate_openings
from .notification import (
    NotificationInfo,
    notification_required,
    write_notification_xlsx,
)
from .plan_solver import StandoffSpec, solve_plan
from .platforms import Hoist, LoadingStage, platform_quantities, validate_platforms
from .quantity import take_off
from .report import (
    write_jack_table_csv,
    write_plan_json,
    write_quantity_csv,
    write_report_md,
)
from .stairs import (
    DEFAULT_MAX_TRAVEL_MM,
    auto_place_stairs,
    place_stairs_at,
    validate_stairs,
)
from .structural import SiteCondition, optimize_wall_ties, run_structural
from .terrain import GroundModel, solve_post_feet


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
        guard_rail_type=spec.get("guard_rail_type", GUARD_RAIL_LEDGER),
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


def build_openings(spec: dict) -> list:
    """開口部（梁枠）の入力を組み立てる."""
    return [
        Opening(
            edge_index=int(o["edge_index"]),
            start_mm=float(o["start_mm"]),
            beam_span_mm=int(o["beam_span_mm"]),
            level=int(o.get("level", 1)),
            reason=o.get("reason", ""),
        )
        for o in spec.get("openings", [])
    ]


def build_platforms(spec: dict) -> tuple[list, list]:
    """荷受けステージと昇降機の入力."""
    stages = [
        LoadingStage(
            edge_index=s["edge_index"],
            start_mm=float(s["start_mm"]),
            span_count=s.get("span_count", 2),
            projection_mm=s.get("projection_mm", 1500),
            load_kn=s.get("load_kn", 9.8),
            levels=s.get("levels", []),
            has_guard_rail=s.get("has_guard_rail", True),
            has_toe_board=s.get("has_toe_board", True),
            has_load_sign=s.get("has_load_sign", True),
            has_hozue=s.get("has_hozue", True),
            note=s.get("note", ""),
        )
        for s in spec.get("loading_stages", [])
    ]
    hoists = [
        Hoist(
            edge_index=h["edge_index"],
            position_mm=float(h["position_mm"]),
            reach_height_mm=h.get("reach_height_mm", 0.0),
            tie_every_mm=h.get("tie_every_mm", 3600),
            note=h.get("note", ""),
        )
        for h in spec.get("hoists", [])
    ]
    return stages, hoists


def build_ground(spec: dict) -> GroundModel:
    """敷地の標高サンプル点。Archicadから使う場合は read_ground_model() で読む."""
    pts = spec.get("ground_points_mm", [])
    return GroundModel(points=[tuple(p) for p in pts])


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


def collect_warnings(
    structural, model, bracket_issues, stair_plan, stair_issues,
    openings, terrain, platforms, checks=None,
) -> list[tuple[str, str, str]]:
    """是正・確認が要る項目を (分類, 重大度, 本文) で集める.

    総合判定と結果JSONで同じものを数えるための一箇所。別々に組み立てていた
    ときは、判定が法規チェックのWARNしか数えず、離れの措置や未確認耐力値が
    「要確認0件」の裏に隠れていた。
    """
    out: list[tuple[str, str, str]] = []
    out += [("構造", "WARN", w) for w in structural.warnings]
    out += [("割付", "WARN", w)
            for w in model.plan.warnings + model.elevation.warnings]
    out += [("ブラケット区間", i.severity,
             f"ブラケット[{i.severity}] {i.message}（{i.basis}）")
            for i in bracket_issues]
    out += [("階段", "WARN", w) for w in stair_plan.warnings]
    out += [("階段", "WARN", f"階段[WARN] {w}") for w in stair_issues]
    # 重大度を本文にも出す。NGと注意が同じ見た目だと、どれが止まる項目か分からない
    out += [("開口部", i.severity, f"開口部[{i.severity}] {i.message}")
            for i in openings.issues]
    # 法規チェックが同じ文面で挙げている事象は、そちらが条文つきで出るので重ねない
    said = {c.message for c in (checks or []) if c.status == "WARN"}
    out += [("敷地", "WARN", f"敷地: {w}")
            for w in terrain.warnings if w not in said]
    out += [("荷受けステージ・昇降機", i.severity,
             f"{i.kind}[{i.severity}] {i.message}（{i.basis}）")
            for i in platforms.issues]
    return out


def build_verdict(
    check_summary, structural, platforms, openings, bracket_issues,
    warnings: list[tuple[str, str, str]] | None = None,
) -> dict:
    """計画が成立しているかの総合判定.

    これまでは法規チェック・構造計算・荷受けステージ・開口部・ブラケット区間が
    それぞれ別々に判定を持ち、どこかがNGでも他は緑のままだった。読む側が
    4〜5箇所を突き合わせないと成立しているか分からない。1箇所にまとめる。
    """
    blockers = []
    if check_summary["ng"]:
        blockers.append(f"法規チェックNG {check_summary['ng']}件")
    if not structural.wall_tie.ok:
        blockers.append(f"壁つなぎ 検定比{structural.wall_tie.ratio}")
    if not structural.post.ok:
        blockers.append(f"建地圧縮 検定比{structural.post.ratio}")
    n_pf = len([i for i in platforms.issues if i.severity == "NG"])
    if n_pf:
        blockers.append(f"荷受けステージ・昇降機NG {n_pf}件")
    n_op = len([i for i in openings.issues if i.severity == "NG"])
    if n_op:
        blockers.append(f"開口部NG {n_op}件")
    n_bk = len([i for i in bracket_issues if i.severity == "NG"])
    if n_bk:
        blockers.append(f"ブラケット区間NG {n_bk}件")
    # 要確認の件数は法規チェックのWARNだけではない。離れの措置・未確認耐力値・
    # 階段の注意なども「読んで手を打つ」対象なので、まとめて数えて内訳を出す
    counts: dict[str, int] = {}
    if check_summary["warn"]:
        counts["法規チェック"] = check_summary["warn"]
    for kind, severity, _ in warnings or []:
        # NG は blockers に出ている。要確認の件数に混ぜると二重に数える
        if severity != "NG":
            counts[kind] = counts.get(kind, 0) + 1
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warn": sum(counts.values()),
        "warn_breakdown": [f"{k} {v}件" for k, v in counts.items()],
    }


def run(input_path: Path, out_dir: Path, master_csv: Path | None = None) -> dict:
    # 文字列で渡されることがある（スクリプトからの直接呼び出し）。
    # input_path だけ Path() していて out_dir はしていなかった
    out_dir = Path(out_dir)
    if master_csv is not None:
        master_csv = Path(master_csv)
    spec = json.loads(Path(input_path).read_text(encoding="utf-8"))
    model = build_model(spec, master_csv)
    site = build_site(spec)
    # 壁つなぎは風荷重の検定から逆算して確定させる（数量・法規チェックに反映するため先に実行）
    tie_opt = optimize_wall_ties(model, site)
    brackets = build_brackets(spec)
    bracket_issues = validate_bracket_sections(model, brackets)
    st = spec.get("stairs", {})
    if st.get("positions"):
        # 位置を指定した場合はそれを使う（自動配置と同じ検証は通す）
        stair_plan = place_stairs_at(
            model,
            st["positions"],
            tower_spans=st.get("tower_spans", 2),
            max_travel_mm=st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM),
        )
    else:
        stair_plan = auto_place_stairs(
            model,
            max_travel_mm=st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM),
            tower_spans=st.get("tower_spans", 2),
            count=st.get("count"),
            min_per_face=st.get("min_per_face", 0),
        )
    stair_issues = validate_stairs(
        model, stair_plan, st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM)
    )
    platforms = validate_platforms(model, *build_platforms(spec))
    openings = validate_openings(model, build_openings(spec))
    # 法規チェックは階段配置と敷地の解を使う（昇降設備・ジャッキ繰出し）
    terrain = solve_post_feet(model, build_ground(spec))
    checks = run_all_checks(model, stair_plan=stair_plan, terrain=terrain)
    quantity = take_off(
        model, bracket_sections=brackets, stair_plan=stair_plan,
        platforms=platforms, openings=openings,
    )
    # 詳細図は開口部があれば梁枠の図を足す
    from .details import required_details

    detail_sheets = required_details(model, opening_detail_specs(openings))
    structural = run_structural(
        model, quantity, site, platforms=platforms, terrain=terrain
    )

    s = summary(checks)
    warnings = collect_warnings(
        structural, model, bracket_issues, stair_plan, stair_issues,
        openings, terrain, platforms, checks,
    )
    verdict = build_verdict(
        s, structural, platforms, openings, bracket_issues, warnings
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    name = spec.get("project_name", "ashiba")
    write_quantity_csv(quantity, out_dir / f"{name}_数量表.csv")
    write_report_md(
        model, quantity, checks, out_dir / f"{name}_割付レポート.md", name,
        stair_plan=stair_plan, verdict=verdict, structural=structural, terrain=terrain,
        platforms=platforms, openings=openings, bracket_sections=brackets,
        warnings=warnings,
    )
    write_plan_json(
        model, out_dir / f"{name}_plan.json",
        stair_plan=stair_plan, terrain=terrain, platforms=platforms,
        openings=openings, bracket_sections=brackets,
    )
    write_jack_table_csv(terrain, out_dir / f"{name}_ジャッキ量一覧.csv")
    write_notification_xlsx(
        model, quantity, checks, structural,
        out_dir / f"{name}_設置届一式.xlsx", name, build_notification_info(spec),
        details=detail_sheets, terrain=terrain,
    )

    return {
        "project": name,
        "posts_per_level": model.plan.total_posts,
        "levels": model.elevation.n_levels,
        "scaffold_height_mm": model.scaffold_height_mm,
        "verdict": verdict,
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
            # 差し替えるべき capacity.csv の行（series_id,item,key）
            "unverified_capacity_rows": [
                r for c in structural.unverified_rows for r in c.rows
            ],
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
        "openings": {
            "count": len(openings.openings),
            "removed_posts": openings.removed_posts,
            "ok": openings.ok,
        },
        "platforms": {
            "loading_stages": len(platforms.stages),
            "hoists": len(platforms.hoists),
            "extra_wall_ties": platforms.extra_wall_ties,
            "max_post_load_kn": round(platforms.max_post_load_kn, 2),
            "governing": platforms.governing,
            "ok": platforms.ok,
        },
        "terrain": {
            "gl_difference_mm": round(terrain.gl_difference_mm, 1),
            "jack_range_mm": [round(terrain.jack_min_mm, 1),
                              round(terrain.jack_max_mm, 1)],
            "foot_variants": len({f.koma_offset for f in terrain.feet}),
            "posts_over_recommended": len(terrain.over_recommended()),
            "all_ok": terrain.all_ok,
        },
        "stairs": {
            "count": stair_plan.count,
            "required_count": stair_plan.required_count,
            "max_travel_m": round(stair_plan.max_travel_mm / 1000.0, 1),
            "landings": stair_plan.total_landings,
            "manual": any(t.manual for t in stair_plan.towers),
            "positions": [
                {"edge_index": t.edge_index, "start_mm": round(t.start_mm),
                 "spans": t.span_count, "manual": t.manual}
                for t in stair_plan.towers
            ],
        },
        # 参考情報（何をどう解いたかの説明）は warnings と分ける。
        # 混ぜると、読む側がどれに手を打てばよいのか分からなくなる
        "notes": structural.notes + [f"敷地: {n}" for n in terrain.notes],
        "warnings": [w for _, _, w in warnings],
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
