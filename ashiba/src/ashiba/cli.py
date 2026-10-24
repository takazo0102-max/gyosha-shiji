"""ワンクリック実行CLI: 入力JSON → 割付・法規チェック・数量CSV・レポート一式.

使い方:
    python3 -m ashiba.cli examples/rect_30x20.json --out out/

構成:
- solve_all()      入力を解く（割付・壁つなぎ最適化・階段・敷地・検査・数量・構造）
- write_outputs()  帳票一式を書く（CLIもツールバーも実機E2Eも同じものを出す）
- result_dict()    機械可読の実行結果（標準出力・受け入れテストが読む）
判定は build_verdict() の1箇所で決める。法規・構造・付帯設備・数量が別々に
判定を持っていた頃は、どこかがNGでも他は緑のままだった。

要確認の件数は法規チェックのWARNだけでなく、collect_warnings() が集めた
全分類（構造・割付・階段・開口部・敷地・数量・付帯設備）を数える。数えないと
「要確認0件」の裏に離れの措置や未確認耐力値が隠れる。

入力の誤り（綴り違い・型違い・矛盾）は validate_spec() が実行前にまとめて
指摘し、ファイル自体の異常（無い・空・壊れ・文字コード）は load_spec() が
日本語で返す。どちらも終了コード2で止める。

入力JSONスキーマ（examples/参照）:
{
  "project_name": "サンプル",
  "series_id": "nikken_nd1800",
  "module": "inch",                // "inch"（インチ: 1829/1524/1219/914/610）／"metric"（メートル: 1800/1500/1200/900/600）。両方省くと日建ND1800（フィート寸法）
  "outline_mm": [[0,0],[30000,0],[30000,20000],[0,20000]],
  "eaves_height_mm": 15400,        // 軒高
  "guard_extra_mm": 900,           // 軒高に足す手すり分（最上層作業床固定点）
  "building_height_mm": 16000,     // 架け面積用（省略時は足場高さ）
  "period_days": 90,
  "standoff": {"target": 300, "min": 250, "max": 350, "hard_min": 250},   // hard_min 未満の離れは採らない（200まで許す案件は下げる）
  "deck_widths": [400, 250],
  "clearance_space_mm": 2000,
  "scaffold_form": "本足場",
  "next_gen": false,               // 次世代足場（踏板幅が広い規格）
  "guard_rail_type": "布材",        // "布材"（＋中桟）／"先行手すり"
  "inner_guard_rail": true,        // 躯体側（内側建地列）の手すり＋中桟を布材で組む
  "line_mode_3d": false,           // 3Dを線だけで描く（計画初期・大規模向け。干渉確認は false の立体表現で）
  "horizontal_net_levels": [2],    // 水平ネット（躯体と足場の隙間）を張る作業層。ネットブラケットは内側建地ごと（省略＝張らない）
  "auto_inner_bracket": true,      // 離れが目標上限（350）を超える面に内ブラケット＋踏板を自動で付ける
  "pdf": true,                     // 足場のレイアウト（サブセット「仮設足場」）を ashiba_out/PDF に発行（断面図方式のとき）
  "pdf_publisher_set": "2 - レイアウト",  // 発行に使う Archicad の発行セット（レイアウトブックを映したもの）
  "elevation_mode": "section",     // 立面図: "section"=断面図ビューポイントで3Dから投影しレイアウトへ／"object"=平面の下に2Dで並べる／"none"
  "cross_section_mode": "section", // 断面図: "section"=断面図ビューポイントで3Dを切る（既定）／"drafted"=2Dの作図の形の部品を 1/50 で
  "post_reinforcement": "",       // ""／"強力つなぎ材"（腕木を強力つなぎ材にして支柱の許容支持力を上げる。系列に値がある場合のみ）
  // 開口部（省略可）。支柱を抜いて通路にする箇所。梁枠は規格品のみ
  "openings": [
    {"edge_index": 0, "start_mm": 3600, "beam_span_mm": 3600, "reason": "現場出入口"}
  ],
  // 朝顔（省略時は高さから自動。false で明示的に設置しない）
  "asagao": {"stages": 1, "projection_mm": 2000, "angle_deg": 25, "tie_every_spans": 2},
  // 信和のセーフウイング（簡易落下物防止・張出1280mm）は "kind": "セーフウイング"。
  // 防護棚ではないので10m以上の足場では法規#10がNGになる（朝顔が別途要る）
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
  "hoists": [{"edge_index": 2, "position_mm": 14400, "tie_every_mm": 3600,
              "landing_levels": [2, 4]}],   // 乗り込み口の作業層（省略＝全層）
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
    "positions": [{"edge_index": 0, "start_mm": 3600, "span_count": 2,
                   "reason": "現場出入口の近く"}]
  }
}
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from .brackets import BracketSection, validate_bracket_sections
from .elevation_solver import solve_elevation
from .law_check import asagao_height_mm, required_asagao_stages, run_all_checks, summary
from .master import MasterDataError, SeriesLockError, load_master
from .model import (
    ASAGAO_KIND_ASAGAO, ASAGAO_KIND_SAFE_WING, ASAGAO_KINDS, SAFE_WING_ANGLE_DEG, SAFE_WING_PROJECTION_MM,
    GUARD_RAIL_ADVANCE,
    FRAME_GUARD_RAIL_HEIGHT_MM,
    TUBE_GUARD_RAIL_HEIGHT_MM,
    TUBE_POST_ABOVE_RAIL_MM,
    GUARD_RAIL_LEDGER,
    AsagaoSpec,
    ScaffoldConfig,
    ScaffoldModel,
)
from .openings import Opening, opening_detail_specs, opening_ranges, validate_openings
from .conflicts import check_conflicts
from .pens import parse_pens
from .ties import merge_attachment_ties, relocate_ties_off_openings, relocate_unreachable_ties
from .structural import CapacityError
from .gdl_params import GdlCapacityError
from .geometry import ValidationError
from .notification import (
    NotificationInfo,
    notification_required,
    write_notification_xlsx,
)
from .plan_solver import StandoffSpec, solve_plan
from .platforms import Hoist, LoadingStage, platform_ranges, validate_platforms
from .quantity import take_off
from .report import (
    write_jack_table_csv,
    write_plan_json,
    write_quantity_csv,
    write_report_md,
)
from .stairs import (
    DEFAULT_MAX_TRAVEL_MM,
    MIN_HEIGHT_FOR_STAIRS_MM,
    auto_place_stairs,
    place_stairs_at,
    validate_stairs,
)
from .structural import SiteCondition, optimize_wall_ties, run_structural
from .terrain import GroundModel, solve_post_feet


class InputError(ValueError):
    """入力JSONの誤り（綴り違い・型違い・矛盾）をまとめて知らせる."""


# 受け付けるキー。ここに無いキーは綴り違いとして弾く。
# 黙って無視すると「指定したのに効かない」まま図面と計算が進んでしまう
# （loading_stage と書けばステージが消え、計算にも数量にも現れない）
TOP_KEYS = {
    "project_name", "series_id", "module", "outline_mm", "eaves_height_mm", "guard_extra_mm", "scaffold_height_mm",
    "span_overrides",
    "building_height_mm", "period_days", "standoff", "deck_widths", "scaffold_width_mm",
    "clearance_space_mm", "scaffold_form", "next_gen", "site_boundary_mm", "road_edges", "fit_boundary",
    "stairs_elsewhere",
    "guard_rail_type", "inner_guard_rail", "end_guard", "line_mode_3d", "horizontal_net_levels", "slabs", "height_from_slabs",
    "toe_board", "net_brackets", "hoarding_height_mm", "pens",
    "obstacles", "setbacks", "avoid_obstacles", "setback_bracket_max_mm", "bracket_post", "ladders",
    "face_eaves_mm", "base_height_mm", "setback_tiers", "elevation_mode", "cross_section_mode", "auto_inner_bracket", "pdf", "pdf_publisher_set", "post_reinforcement", "openings", "asagao", "bracket_sections",
    "loading_stages",
    "hoists", "ground_points_mm", "site", "notification", "stairs", "wall_ties_manual", "stories", "faces",
    "member_edits", "face_forms", "form_standoff", "corner_steps", "corner_joins",
}
NESTED_KEYS = {
    "standoff": {"target", "min", "max", "hard_min"},
    "asagao": {"stages", "projection_mm", "angle_deg", "tie_every_spans", "kind", "faces"},
    "site": {"region", "v0_ms", "roughness", "sheet_type", "adjacent_factor",
             "region_factor", "gamma", "correction_f",
             "simultaneous_loaded_levels"},
    "notification": {"business_type", "site_name", "site_address", "worker_count",
                     "planner_name", "planner_career", "start_date", "contractor",
                     "labor_office"},
    "stairs": {"count", "tower_spans", "max_travel_mm", "min_per_face",
               "positions", "layout"},
}
LIST_ITEM_KEYS = {
    "openings": ({"edge_index", "face", "start_mm", "beam_span_mm", "level", "reason"},
                 {"edge_index", "start_mm", "beam_span_mm"}),
    "bracket_sections": (
        {"edge_index", "face", "start_mm", "end_mm", "direction", "width", "deck_width",
         "levels", "has_hozue", "is_widening", "on_kessokubu", "reason"},
        {"edge_index", "start_mm", "end_mm"},
    ),
    "loading_stages": (
        {"edge_index", "face", "start_mm", "span_count", "projection_mm", "load_kn",
         "levels", "has_guard_rail", "has_toe_board", "has_load_sign",
         "has_hozue", "has_fence", "note"},
        {"edge_index", "start_mm"},
    ),
    "hoists": ({"edge_index", "face", "position_mm", "reach_height_mm", "tie_every_mm",
                "landing_levels", "note", "cage_width_mm", "cage_depth_mm", "load_kn"},
               {"edge_index", "position_mm"}),
    # 範囲を指定した部材の編集（外す・置換）。spans・levels は "3-5"・[3, 5]・3・"全部"
    "member_edits": ({"edge_index", "face", "spans", "levels", "parts", "part", "action", "to", "reason"},
                     {"edge_index"}),
}
STAIR_POSITION_KEYS = {"edge_index", "face", "start_mm", "span_count", "reason"}


# 型違いを実行前に弾くための、数値であるべきフィールド一覧。
# 文字列やbool・負値を黙って通すと、割付の途中で TypeError や
# invalid literal になり、利用者には直しようがない
NUMERIC_FIELDS = {
    "standoff": ("target", "min", "max", "hard_min"),
    "asagao": ("stages", "projection_mm", "angle_deg", "tie_every_spans"),
    "site": ("v0_ms", "adjacent_factor", "region_factor", "gamma",
             "correction_f", "simultaneous_loaded_levels"),
    "stairs": ("count", "tower_spans", "max_travel_mm", "min_per_face"),
}
# 文字列であるべきフィールド（数値を渡すと後段の照合で分かりにくく落ちる）
STRING_FIELDS = {
    "site": ("region", "roughness", "sheet_type"),
    "asagao": ("kind",),
}
# LIST_ITEM_KEYS の各要素で数値であるべきキー
LIST_NUMERIC_FIELDS = {
    "openings": ("edge_index", "start_mm", "beam_span_mm", "level"),
    "bracket_sections": ("edge_index", "start_mm", "end_mm", "width", "deck_width"),
    "loading_stages": ("edge_index", "start_mm", "span_count",
                       "projection_mm", "load_kn"),
    "hoists": ("edge_index", "position_mm", "reach_height_mm", "tie_every_mm",
               "cage_width_mm", "cage_depth_mm", "load_kn"),
}
# 整数の配列であるべきキー（作業層の指定など）
LIST_INT_LIST_FIELDS = {
    "bracket_sections": ("levels",),
    "loading_stages": ("levels",),
    "hoists": ("landing_levels",),
}


def _check_numbers(errors: list[str], where: str, obj, keys) -> None:
    """obj の指定キーが数値（bool不可）であることを確認する."""
    if not isinstance(obj, dict):
        return
    for k in keys:
        v = obj.get(k)
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            errors.append(f"{where}: \"{k}\" は数値で指定してください（{v!r}）")


def _check_int_lists(errors: list[str], where: str, obj, keys) -> None:
    """obj の指定キーが整数の配列であることを確認する."""
    if not isinstance(obj, dict):
        return
    for k in keys:
        v = obj.get(k)
        if v is None:
            continue
        if not isinstance(v, list) or any(
            not isinstance(x, int) or isinstance(x, bool) for x in v
        ):
            errors.append(f"{where}: \"{k}\" は整数の配列で指定してください（{v!r}）")


def _check_strings(errors: list[str], where: str, obj, keys) -> None:
    """obj の指定キーが文字列であることを確認する."""
    if not isinstance(obj, dict):
        return
    for k in keys:
        v = obj.get(k)
        if v is not None and not isinstance(v, str):
            errors.append(f"{where}: \"{k}\" は文字列で指定してください（{v!r}）")


# 以前あったが実際には効いていなかったキー → 今の書き方
RENAMED = {"n_stairs": "stairs.count（階段の箇所数）"}


def _check_keys(errors: list[str], where: str, obj, allowed: set[str],
                required: set[str] = frozenset()) -> None:
    if not isinstance(obj, dict):
        errors.append(f"{where}: オブジェクトで指定してください（{type(obj).__name__}）")
        return
    # "_" で始まるキーはコメント扱い（JSONにコメントが書けないので、雛形の説明に使う）
    for k in sorted(k for k in set(obj) - allowed if not str(k).startswith("_")):
        if k in RENAMED:
            errors.append(f"{where}: \"{k}\" は廃止しました → {RENAMED[k]} を使ってください")
            continue
        near = [a for a in allowed if a.startswith(k[:4])]
        hint = f"（{'・'.join(sorted(near))} の綴り違い？）" if near else ""
        errors.append(f"{where}: 未知のキー \"{k}\"{hint}")
    # 面は edge_index か face（面名）のどちらかで指定する
    if "face" in obj:
        required = required - {"edge_index"}
        if not isinstance(obj["face"], str) or not obj["face"].strip():
            errors.append(f"{where}: \"face\" は面名の文字列で指定してください（例 \"北面\"）")
    for k in sorted(required - set(obj)):
        errors.append(f"{where}: \"{k}\" が要ります" + ("（または face: \"北面\"）" if k == "edge_index" else ""))


def _check_item_semantics(errors: list[str], key: str, where: str, item) -> None:
    """区間指定の値の意味の誤り（向きの綴り・負の積載・終点が始点より前）を入口で止める.

    これらは検証ではNG（計画不成立）として出ていたが、綴り違いや符号の間違いは
    計画の問題ではなく入力の問題。是正項目に混ぜると読む側が入力ミスに気づきにくい。
    """
    if not isinstance(item, dict):
        return

    def num(name):
        v = item.get(name)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    for name in ("edge_index", "start_mm", "position_mm"):
        v = num(name)
        if v is not None and v < 0:
            errors.append(f"{where}.{name}: 0以上で指定してください（{v}）")
    if key == "bracket_sections":
        d = item.get("direction")
        if d is not None and d not in ("内", "張出"):
            errors.append(f"{where}.direction: 内 か 張出 です（{d!r}）")
        w = num("width")
        if w is not None and w <= 0:
            errors.append(f"{where}.width: 0より大きい値で指定してください（{w}）")
        s0, s1 = num("start_mm"), num("end_mm")
        if s0 is not None and s1 is not None and s1 <= s0:
            errors.append(f"{where}: end_mm（{s1}）は start_mm（{s0}）より大きい値です")
    elif key == "loading_stages":
        for name in ("load_kn", "projection_mm"):
            v = num(name)
            if v is not None and v <= 0:
                errors.append(f"{where}.{name}: 0より大きい値で指定してください（{v}）")
        sc = num("span_count")
        if sc is not None and sc < 1:
            errors.append(f"{where}.span_count: 1以上で指定してください（{sc}）")
    elif key == "hoists":
        t = num("tie_every_mm")
        if t is not None and t <= 0:
            errors.append(f"{where}.tie_every_mm: 0より大きい値で指定してください（{t}）")
    elif key == "openings":
        b = num("beam_span_mm")
        if b is not None and b <= 0:
            errors.append(f"{where}.beam_span_mm: 0より大きい値で指定してください（{b}）")
        lv = num("level")
        if lv is not None and lv < 1:
            errors.append(f"{where}.level: 1以上で指定してください（{lv}）")


MIN_OUTLINE_EXTENT_MM = 1000.0   # これ未満の外形は m 入力の取り違えとみなす
MIN_HEIGHT_MM = 100.0            # 軒高: これ未満は m 入力の取り違え（100mm以上は作業層が取れない検定不能の経路として通す）


def resolve_face_name(name: str, model) -> int:
    """面名（"北面"・"北"・"南面(辺4)"）→ 辺番号。無い・複数あるときは InputError.

    面名は割付レポート・立面図と同じ方位名（plan.face_names()）。同じ方位の面が複数
    ある建物では「南面(辺0)」「南面(辺4)」のように辺番号つきでしか呼べないので、
    「南面」だけでは止めて候補を出す。
    """
    names = model.plan.face_names()
    key = name.strip()
    if key.endswith("面") is False and "(" not in key:
        key += "面"
    exact = [e.edge_index for e, n in zip(model.plan.edges, names) if n == key]
    if len(exact) == 1:
        return exact[0]
    prefix = [n for n in names if n.startswith(key + "(")]
    if prefix:
        raise InputError(
            f"面「{name}」は複数あります（{'・'.join(prefix)}）。辺番号つきで指定してください"
        )
    raise InputError(f"面「{name}」はありません（この外形の面は {'・'.join(names)}）")


def check_edge_indices(spec: dict, model) -> None:
    """辺番号つきの付帯設備が、割付後に存在する辺を指しているか.

    存在しない辺の階段は「辺9は存在しません」の警告だけで落ちて、階段が無い計画が
    黙って出ていた。開口部・ステージ・昇降機・ブラケット区間も同じ入口で止める。
    """
    valid = sorted(e.edge_index for e in model.plan.edges)
    errors: list[str] = []
    items: list[tuple[str, list]] = [
        (key, spec.get(key) or []) for key in ("openings", "loading_stages", "hoists", "bracket_sections",
                                                    "member_edits")
    ]
    items.append(("stairs.positions", (spec.get("stairs") or {}).get("positions") or []))
    for key, lst in items:
        if not isinstance(lst, list):
            continue
        for i, item in enumerate(lst):
            if not isinstance(item, dict):
                continue
            # 面名（"北面"）での指定を辺番号に解く。辺番号は外形の整理（反転・斜辺の
            # 置き換え・共線頂点の除去）で入力の頂点順とずれ、実機の五角形棟では入力順の
            # 辺3（北面）が整理後は西面になり、昇降機が西面に置かれた。面名なら整理の
            # 影響を受けない
            if item.get("face") is not None:
                try:
                    resolved = resolve_face_name(str(item["face"]), model)
                except InputError as e:
                    errors.append(f"{key}[{i}].face: {e}")
                    continue
                ei0 = item.get("edge_index")
                if ei0 is not None and not isinstance(ei0, bool) and int(ei0) != resolved:
                    errors.append(
                        f"{key}[{i}]: face「{item['face']}」は辺{resolved}ですが edge_index は{int(ei0)}です。"
                        "どちらか一方にしてください"
                    )
                    continue
                item["edge_index"] = resolved
            ei = item.get("edge_index")
            if ei is None:
                errors.append(f"{key}[{i}]: 面の指定がありません（face: \"北面\" か edge_index）")
                continue
            if isinstance(ei, bool) or not isinstance(ei, (int, float)):
                continue
            if int(ei) not in valid:
                errors.append(
                    f"{key}[{i}].edge_index: 辺{int(ei)}は存在しません（この外形の辺は "
                    + "・".join(str(v) for v in valid) + "。割付レポートの平面割付表の辺番号）"
                )
    if errors:
        raise InputError("入力JSONに問題があります:\n  - " + "\n  - ".join(errors))


def validate_spec(spec: dict) -> None:
    """入力JSONを読む前に、綴り違い・型違い・矛盾をまとめて指摘する.

    黙って既定値へ落とすと、指定したつもりの朝顔やステージが計画から消えても
    誰も気づかない。安全に関わる指定を無視しないための入口チェック。
    """
    errors: list[str] = []
    _check_keys(errors, "入力", spec, TOP_KEYS, {"outline_mm", "eaves_height_mm"})
    if not isinstance(spec, dict):
        raise InputError("入力JSONはオブジェクトで指定してください")

    outline = spec.get("outline_mm")
    if outline is not None:
        if not isinstance(outline, list) or len(outline) < 3:
            errors.append("outline_mm: 3点以上の[[x,y], ...]で指定してください")
        elif any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in outline):
            errors.append("outline_mm: 各点は[x, y]の2要素で指定してください")
        else:
            # m で入力した外形（30×20）は 30mm×20mm の建物として解けてしまい、
            # 支柱4本・重量1.5t の計画が黙って出る。単位の取り違えは入口で止める
            try:
                xs = [float(p[0]) for p in outline]
                ys = [float(p[1]) for p in outline]
                extent = max(max(xs) - min(xs), max(ys) - min(ys))
                if extent < MIN_OUTLINE_EXTENT_MM:
                    errors.append(
                        f"outline_mm: 外形の大きさが{extent:.0f}mmしかありません。"
                        "単位は mm です（m で入力していませんか。30m なら 30000）"
                    )
            except (TypeError, ValueError):
                errors.append("outline_mm: 座標は数値で指定してください")

    for key in ("eaves_height_mm", "guard_extra_mm", "building_height_mm",
                "period_days", "clearance_space_mm", "scaffold_height_mm"):
        v = spec.get(key)
        if v is not None and (not isinstance(v, (int, float))
                              or isinstance(v, bool) or v < 0):
            errors.append(f"{key}: 0以上の数値で指定してください（{v!r}）")

    def _num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    # 0は型としては通るが、解くと意味の無い計画になる値
    ev, bv = spec.get("eaves_height_mm"), spec.get("building_height_mm")
    if _num(ev) and ev <= 0:
        errors.append("eaves_height_mm: 0より大きい値で指定してください（軒高0では足場を組めません）")
    elif _num(ev) and ev < MIN_HEIGHT_MM:
        errors.append(
            f"eaves_height_mm: 軒高{ev:g}mmは小さすぎます。単位は mm です（m で入力していませんか。16m なら 16000）"
        )
    if _num(ev) and _num(bv) and bv > 0 and ev > bv:
        errors.append(
            f"eaves_height_mm: 軒高{ev:g}mmが建物高さ building_height_mm {bv:g}mmを"
            "超えています（軒高≦建物高さ）")
    pd = spec.get("period_days")
    if _num(pd) and 0 <= pd < 1:
        errors.append("period_days: 1日以上で指定してください（工期0日では風荷重の期間係数を決められません）")
    sw = spec.get("scaffold_width_mm")
    if sw not in (None, 0) and (not _num(sw) or not 300 <= sw <= 1500):
        errors.append(f"scaffold_width_mm: 足場の幅は 600・900 などを mm で指定してください（{sw!r}）")
    dw = spec.get("deck_widths")
    if dw is not None and (
        not isinstance(dw, list) or not (1 <= len(dw) <= 2)
        or any(not _num(w) or w <= 0 for w in dw)
    ):
        errors.append(f"deck_widths: 正の数値を1〜2個の配列で指定してください（{dw!r}）")
    st0 = spec.get("stairs")
    if isinstance(st0, dict):
        for k in ("count", "tower_spans", "min_per_face"):
            v = st0.get(k)
            if _num(v) and v < 0:
                errors.append(f"stairs.{k}: 0以上で指定してください（{v!r}）")
        v = st0.get("max_travel_mm")
        if _num(v) and v <= 0:
            errors.append(f"stairs.max_travel_mm: 0より大きい値で指定してください（{v!r}）")

    for key, allowed in NESTED_KEYS.items():
        if key in spec and spec[key] is not None and spec[key] is not False:
            _check_keys(errors, key, spec[key], allowed)
            if key in NUMERIC_FIELDS:
                _check_numbers(errors, key, spec[key], NUMERIC_FIELDS[key])
            if key in STRING_FIELDS:
                _check_strings(errors, key, spec[key], STRING_FIELDS[key])

    so = spec.get("standoff")
    if isinstance(so, dict):
        _check_numbers(errors, "standoff", so,
                       ("target", "min", "max", "hard_min"))
        hard, mn = so.get("hard_min", 250), so.get("min", 250)
        mx, tgt = so.get("max", 350), so.get("target", 300)
        # 大小比較は数値のときだけ。型違いは上の _check_numbers が指摘済み
        vals = (hard, mn, tgt, mx)
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                      for v in vals)
        if numeric and not (hard <= mn <= tgt <= mx):
            errors.append(
                f"standoff: hard_min≦min≦target≦max の順になっていません"
                f"（hard_min{hard}・min{mn}・target{tgt}・max{mx}）"
            )

    for key, (allowed, required) in LIST_ITEM_KEYS.items():
        items = spec.get(key)
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append(f"{key}: 配列で指定してください")
            continue
        for i, item in enumerate(items):
            where = f"{key}[{i}]"
            _check_keys(errors, where, item, allowed, required)
            _check_numbers(errors, where, item, LIST_NUMERIC_FIELDS.get(key, ()))
            _check_int_lists(errors, where, item, LIST_INT_LIST_FIELDS.get(key, ()))
            _check_item_semantics(errors, key, where, item)

    if spec.get("module") not in (None, ""):
        from .master import normalize_module
        try:
            normalize_module(spec.get("module"))
        except ValueError as e:
            errors.append(f"module: {e}")
    so = spec.get("span_overrides")
    if so is not None:
        if not isinstance(so, list):
            errors.append("span_overrides: 配列で指定してください")
        else:
            for i, item in enumerate(so):
                where = f"span_overrides[{i}]"
                _check_keys(errors, where, item, {"edge_index", "face", "spans_mm"}, {"edge_index", "spans_mm"})
                if isinstance(item, dict):
                    try:
                        vals = expand_span_list(item.get("spans_mm"))
                        if not vals:
                            errors.append(f"{where}.spans_mm: 1本以上のスパンを指定してください")
                    except ValueError as e:
                        errors.append(f"{where}.spans_mm: {e}")

    st = spec.get("stairs")
    if isinstance(st, dict):
        for i, pos in enumerate(st.get("positions") or []):
            where = f"stairs.positions[{i}]"
            _check_keys(errors, where, pos,
                        STAIR_POSITION_KEYS, {"edge_index", "start_mm"})
            _check_numbers(errors, where, pos,
                           ("edge_index", "start_mm", "span_count"))

    for i, p in enumerate(spec.get("ground_points_mm") or []):
        if not isinstance(p, (list, tuple)) or len(p) != 3:
            errors.append(f"ground_points_mm[{i}]: [x, y, z]の3要素で指定してください")

    form = spec.get("scaffold_form")
    if form is not None and form not in SCAFFOLD_FORMS:
        errors.append(f"scaffold_form: {'・'.join(SCAFFOLD_FORMS)} のどれかです（{form!r}）")
    if spec.get("face_forms"):
        from .face_forms import parse_face_forms

        try:
            parse_face_forms(spec.get("face_forms"))
        except ValueError as e:
            errors.append(str(e))
    bpost = spec.get("bracket_post", "支柱")
    if bpost not in ("支柱", "単管"):
        errors.append(f"bracket_post: 支柱 か 単管 です（{bpost!r}）")
    reinf = spec.get("post_reinforcement", "")
    if reinf not in ("", "強力つなぎ材"):
        errors.append(f"post_reinforcement: \"\" か 強力つなぎ材 です（{reinf!r}）")

    # 構造計算の敷地条件。未知の地域区分・粗度区分・養生材は解いている途中で
    # CapacityError（トレースバック）になっていた。入口で候補つきで弾く
    site = spec.get("site")
    if isinstance(site, dict):
        from .structural import ROUGHNESS, SHEET_FILL_RATIO, CapacityError, SiteCondition

        reg = site.get("region")
        if isinstance(reg, str):
            try:
                SiteCondition(region=reg).base_wind_speed()
            except CapacityError as e:
                errors.append(f"site.region: {e}")
        rough = site.get("roughness")
        if isinstance(rough, str) and rough not in ROUGHNESS:
            errors.append(
                f"site.roughness: 未知の地表面粗度区分です: {rough}"
                f"（候補: {'、'.join(ROUGHNESS)}）")
        sheet = site.get("sheet_type")
        if isinstance(sheet, str) and sheet not in SHEET_FILL_RATIO:
            errors.append(
                f"site.sheet_type: 未知の養生材です: {sheet}"
                f"（候補: {'、'.join(SHEET_FILL_RATIO)}）")
        v0 = site.get("v0_ms")
        if _num(v0) and v0 <= 0:
            errors.append(f"site.v0_ms: 基準風速は0より大きい値（m/s）で指定してください（{v0!r}）")
        e_adj = site.get("adjacent_factor")
        if _num(e_adj) and not (1.0 <= e_adj <= 1.3):
            errors.append(
                f"site.adjacent_factor: 近接建物補正Eは1.0〜1.3の範囲で指定してください（{e_adj!r}）")
        for k in ("region_factor", "correction_f"):
            v = site.get(k)
            if _num(v) and v <= 0:
                errors.append(f"site.{k}: 0より大きい値で指定してください（{v!r}）")
        g = site.get("gamma")
        if _num(g) and not (0.0 <= g <= 1.0):
            errors.append(f"site.gamma: 0〜1の範囲で指定してください（{g!r}）")
        sl = site.get("simultaneous_loaded_levels")
        if _num(sl) and sl < 1:
            errors.append(f"site.simultaneous_loaded_levels: 1層以上で指定してください（{sl!r}）")

    if errors:
        raise InputError("入力JSONに問題があります:\n  - " + "\n  - ".join(errors))


def expand_span_list(values) -> list[int]:
    """スパン指定を本数に展開する。[1800, "1800x5", 900] → [1800, 1800, ..., 900]."""
    if not isinstance(values, list):
        raise ValueError("配列で指定してください（例 [1800, \"1800x5\", 900]）")
    out: list[int] = []
    for v in values:
        if isinstance(v, bool):
            raise ValueError(f"数値か \"寸法x本数\" で指定してください（{v!r}）")
        if isinstance(v, (int, float)):
            if v <= 0:
                raise ValueError(f"スパンは0より大きい値で指定してください（{v!r}）")
            out.append(int(v))
            continue
        if isinstance(v, str) and "x" in v.lower():
            a, _, b = v.lower().partition("x")
            try:
                n = int(b)
                d = int(float(a))
            except ValueError:
                raise ValueError(f"\"寸法x本数\" の形で指定してください（{v!r}）")
            if n <= 0 or d <= 0:
                raise ValueError(f"\"寸法x本数\" は正の値で指定してください（{v!r}）")
            out += [d] * n
            continue
        raise ValueError(f"数値か \"寸法x本数\" で指定してください（{v!r}）")
    return out


def _resolve_span_overrides(spec: dict, plan) -> dict[int, list[int]]:
    """span_overrides の面（face か edge_index）を割付後の辺番号に解き、{辺番号: スパン列} を返す."""
    fixed: dict[int, list[int]] = {}
    names = plan.face_names()
    by_name = {n: e.edge_index for e, n in zip(plan.edges, names)}
    valid = {e.edge_index for e in plan.edges}
    errors: list[str] = []
    for i, item in enumerate(spec.get("span_overrides") or []):
        where = f"span_overrides[{i}]"
        ei = None
        if item.get("face") is not None:
            key = str(item["face"]).strip()
            if not key.endswith("面") and "(" not in key:
                key += "面"
            if key in by_name:
                ei = by_name[key]
            else:
                pref = [n for n in names if n.startswith(key + "(")]
                errors.append(
                    f"{where}.face: 面「{item['face']}」は複数あります（{'・'.join(pref)}）。辺番号つきで指定してください"
                    if pref else f"{where}.face: 面「{item['face']}」はありません（この外形の面は {'・'.join(names)}）"
                )
                continue
            ei0 = item.get("edge_index")
            if ei0 is not None and not isinstance(ei0, bool) and int(ei0) != ei:
                errors.append(f"{where}: face「{item['face']}」は辺{ei}ですが edge_index は{int(ei0)}です。どちらか一方にしてください")
                continue
        else:
            ei = int(item["edge_index"])
            if ei not in valid:
                errors.append(f"{where}.edge_index: 辺{ei}は存在しません（この外形の辺は "
                              + "・".join(str(v) for v in sorted(valid)) + "）")
                continue
        if ei in fixed:
            errors.append(f"{where}: 辺{ei}のスパン指定が重複しています")
            continue
        fixed[ei] = expand_span_list(item["spans_mm"])
    if errors:
        raise InputError("入力JSONに問題があります:\n  - " + "\n  - ".join(errors))
    return fixed


# 足場の形式（利用者の指定 2026-10-21: ブラケット足場（単管・支柱）と単管抱き足場）。建地1列の形式は内部では一側足場
SCAFFOLD_FORMS = ("本足場", "一側足場", "ブラケット足場", "抱き足場", "単管抱き足場")


def narrow_width_mm(master):
    """本足場のいちばん細い幅（くさび: 床を載せられる最小の腕木＝布材 500 以上の最小）. 単管・枠組は None（既定のまま）."""
    if master.is_tube or master.is_frame:
        return None
    rows = [p.nominal_dim for p in master.by_category("布材") if p.nominal_dim >= 500]
    return int(min(rows)) if rows else None


def bracket_for_deck(master, deck_w):
    """一側足場の床受けブラケット: 床の幅以上でいちばん短い品（張出用・内ブラケットを除く。数量と同じ選び方）."""
    return next((p for p in sorted(master.by_category("ブラケット"), key=lambda q: q.nominal_dim)
                 if p.nominal_dim >= deck_w and "張出" not in p.note and "内" not in p.note), None)


def _form_from_spec(spec: dict) -> tuple[str, str, str]:
    """入力の scaffold_form・bracket_post → (内部の形式, 建地1列の組み方, ブラケットの建地)."""
    form = str(spec.get("scaffold_form") or "本足場")
    post = str(spec.get("bracket_post") or "支柱")
    if form in ("抱き足場", "単管抱き足場"):
        return "一側足場", "抱き", "単管"
    if form == "ブラケット足場":
        return "一側足場", "ブラケット", post
    if form == "一側足場":
        return "一側足場", "ブラケット", "支柱"
    return form, "", "支柱"


def resolve_series_id(spec: dict) -> str:
    """series_id と module（インチ／メートル）から系列を決める.

    module だけなら既定の系列（メートル=信和A、インチ=日建ND1800）。両方あれば食い違いを止める
    （インチで組む指定に信和Aを当てると、1800の布材で1829の割付を描くことになる）。
    """
    from .master import DEFAULT_SERIES_BY_MODULE, SERIES_CONST, normalize_module, series_ids_for_module, series_module

    from .master import series_from_label

    sid = series_from_label(spec.get("series_id")) or None
    # 単管抱き足場・単管のブラケット足場は単管の系列で組む（くさびの系列を指定していても）
    _f, kind, post = _form_from_spec(spec)
    if kind == "抱き" or (kind == "ブラケット" and post == "単管"):
        return "tankan"
    mod_in = spec.get("module")
    if mod_in is None or str(mod_in).strip() == "":
        return str(sid or "nikken_nd1800")
    module = normalize_module(mod_in)
    if not sid:
        return DEFAULT_SERIES_BY_MODULE[module]
    sid = str(sid)
    if sid in SERIES_CONST and series_module(sid) != module:
        label = "インチ" if module == "inch" else "メートル"
        raise InputError(
            f"module が{label}なのに系列 {sid} は{'メートル' if label == 'インチ' else 'インチ'}系列です。"
            f"{label}の系列は " + "・".join(series_ids_for_module(module)) + "（series_id を省けば既定の "
            f"{DEFAULT_SERIES_BY_MODULE[module]}）"
        )
    return sid


def build_model(spec: dict, master_csv: Path | None = None) -> ScaffoldModel:
    master = load_master(resolve_series_id(spec), master_csv)
    so = spec.get("standoff", {})
    # 単管抱き足場の離れは建地の芯まで（建地列が離れの線の上）。既定の300でも躯体側の布の外は躯体から約210
    standoff = StandoffSpec(
        target=so.get("target", 300),
        min=so.get("min", 250),
        max=so.get("max", 350),
        hard_min=so.get("hard_min", 250),
        # 隅をコーナーステップで納めるのは本足場（建地2列）。一側は出隅の升目をコーナーステップで塞ぐ別の決め
        corner_steps=bool(spec.get("corner_steps", True)) and _form_from_spec(spec)[0] == "本足場",
    )
    # 面の組で、ほかの組が建てる隣の面の離れ（solve_groups が渡す）。隅はその面の線で終わる
    nb_so = {int(k): float(v) for k, v in (spec.get("_neighbor_standoffs") or {}).items()} or None
    plan = solve_plan(spec["outline_mm"], master, standoff, fixed_standoffs=nb_so)
    fixed = None
    # 面ごとのスパン指定（途中に900を入れる等）。面名は割付後の辺に解いてから、
    # その面を固定して離れを解き直す
    if spec.get("span_overrides"):
        fixed = _resolve_span_overrides(spec, plan)
        try:
            plan = solve_plan(spec["outline_mm"], master, standoff, fixed_spans=fixed)
        except ValidationError as e:
            raise InputError(f"span_overrides: {e}")
        for ei, sp in sorted(fixed.items()):
            plan.warnings.append(
                f"{plan.face_names()[[e.edge_index for e in plan.edges].index(ei)]}のスパンは指定どおり"
                f"（{'+'.join(str(s) for s in sp)}＝{sum(sp)}mm・{len(sp)}スパン）に固定し、離れはそれに合わせて解いています"
            )
    # スラブの天端から面ごとの軒高（セットバック）。いちばん高い面を全体の軒高にし、低い面は後で切る
    spec = dict(spec)
    face_eaves = _face_eaves_from_spec(spec, plan)
    # 庇・バルコニーをかわす: 内側建地が先端に当たる面は、離れを広げて割り付け直す（obstacles）
    obstacles = []
    if spec.get("avoid_obstacles", True):
        obstacles, face_min, notes = _obstacles_from_spec(spec, plan, face_eaves)
        if face_min:
            old_w = list(plan.warnings)
            plan = solve_plan(spec["outline_mm"], master, standoff, fixed_spans=fixed, face_min=face_min)
            plan.warnings[:] = old_w + [w for w in plan.warnings if w not in old_w]
            names = dict(zip([e.edge_index for e in plan.edges], plan.face_names()))
            for ei, sh in sorted(plan.face_shift.items()):
                ep = next(e for e in plan.edges if e.edge_index == ei)
                notes.append(f"{names.get(ei, ei)}: 庇・バルコニーの先端をかわすため、離れを{sh:.0f}mm 広げて"
                             f"{ep.standoff:.0f}mm にしました（内側建地と先端の間 {100:.0f}mm 以上）")
        plan.warnings.extend(notes)
    if face_eaves:
        spec["eaves_height_mm"] = int(round(max(face_eaves.values())))
        spec.setdefault("building_height_mm", spec["eaves_height_mm"])
        if float(spec.get("building_height_mm") or 0) < spec["eaves_height_mm"]:
            spec["building_height_mm"] = spec["eaves_height_mm"]
    # 手すり分の既定は系列から。枠組はコマピッチを持たない（0）ので、
    # 2×コマピッチだと軒高そのままになり、最上層に手すりが立たない。単管は手すりの上に建地を100出す
    guard_extra = spec.get("guard_extra_mm")
    if guard_extra is None:
        guard_extra = (
            FRAME_GUARD_RAIL_HEIGHT_MM if master.is_frame
            else TUBE_GUARD_RAIL_HEIGHT_MM + TUBE_POST_ABOVE_RAIL_MM if master.is_tube
            else 2 * master.koma_pitch + master.koma_top_gap
        )
    required = int(spec["eaves_height_mm"]) + int(guard_extra)
    height_note = None
    if spec.get("scaffold_height_mm") is not None:
        # 足場高さの直接指定（軒高＋手すり分の計算値より優先）。実機で高さを
        # 調整したい要望。軒高より低ければ黙って通さず警告する
        required = int(spec["scaffold_height_mm"])
        height_note = (
            f"足場高さは指定値{required}mm（軒高{int(spec['eaves_height_mm'])}＋手すり分{int(guard_extra)}"
            f"＝{int(spec['eaves_height_mm']) + int(guard_extra)}mmの計算値ではなく）を目標に解いています"
        )
        if required < int(spec["eaves_height_mm"]):
            height_note += "。指定高さが軒高より低いので、最上層は軒に届きません"
    try:
        elevation = solve_elevation(required, master=master)
    except ValueError as e:
        if spec.get("scaffold_height_mm") is not None:
            raise InputError(f"scaffold_height_mm: {e}")
        raise
    if height_note:
        # 指定高さで最上層作業床が軒より下に来るなら、その差を書く（足場高さだけ見ると
        # 軒より高いのに、作業床は軒に届いていない、という見落としを防ぐ）
        eaves = int(spec["eaves_height_mm"])
        top_floor = max(elevation.level_heights) if elevation.level_heights else 0
        if top_floor < eaves and required >= eaves:
            height_note += (
                f"。最上層作業床{top_floor}mmは軒高{eaves}mmより{eaves - top_floor}mm低くなります"
                "（軒回りの作業に支障がないか確認）"
            )
        plan.warnings.append(height_note)
    # マスタに無い幅の作業床は、解けてしまって数量表で床が丸ごと欠けるだけになる
    if spec.get("deck_widths"):
        avail = master.deck_widths_available()
        bad = [w for w in spec["deck_widths"] if int(w) not in avail]
        if bad:
            raise InputError(
                f"deck_widths: 幅{'・'.join(str(int(w)) for w in bad)}の{master.deck_category}が"
                f"系列 {master.series_id} の部材マスタにありません"
                f"（使える幅: {'・'.join(str(w) for w in sorted(avail, reverse=True))}）"
            )
    rail_type = spec.get("guard_rail_type", GUARD_RAIL_LEDGER)
    # 先行手すり方式（くさび系）は幅木を付けない（先行手すりは手すり＋X斜材が一体。
    # 落下物防止はメッシュシート・防網等で）。図面・数量・法規チェックを同じ前提にする
    no_toe = rail_type == GUARD_RAIL_ADVANCE and not master.is_frame
    # 幅木・層間ネットのネットブラケットの付け外し（利用者の指定 2026-10-24: 幅木のおんオフ、そうかんネットと
    # ネットブラケットのおんオフ）
    toe_off = spec.get("toe_board", True) is False and not no_toe
    if toe_off:
        plan.warnings.append(
            "幅木は付けない指定です（図面・数量とも）。落下物防止はメッシュシート・防網等で確保してください"
            "（安衛則563条1項六号）")
    if no_toe:
        plan.warnings.append(
            "先行手すり方式のため幅木は付けていません（図面・数量とも）。落下物防止は"
            "メッシュシート・防網等で確保してください（安衛則563条1項六号）"
        )
    # 足場の幅（600・900 など。利用者の指定 2026-10-20）: 腕木＝建地列の間隔と、そこに収まる作業床の組を決める。
    # 作業床を deck_widths で指定していればそちらが優先。枠組は幅に近い建枠（1219・914・610）に載る布板の組にし、
    # 建枠は布板の載る最小の幅（614枠＝610 はアンチ1列、914 は 500＋240、1219 は 500＋500。利用者の指定 2026-10-23）
    deck_ws = tuple(spec["deck_widths"]) if spec.get("deck_widths") else None
    row_mm = None
    width_mm = spec.get("scaffold_width_mm")
    if spec.get("_narrow") and not width_mm:
        width_mm = narrow_width_mm(master)
    if width_mm:
        w_row, auto_ws = master.width_setup(int(width_mm))
        if not master.is_frame:
            row_mm = w_row
        if deck_ws is None and auto_ws:
            deck_ws = auto_ws
    elif deck_ws is None and not master.is_frame and not spec.get("next_gen", False):
        # 幅も作業床も指定が無いとき、系列の既定の作業床（日建 500＋240＝760）が建地列の間隔（610）より
        # 広いと、内側の板が建地の内へ200ほどはみ出す（利用者の指摘 2026-10-20: 内側のアンチ何？）。
        # 建地列の間隔に収まる組に替える（建地列の間隔は既定どおり）
        dflt = master.default_deck_widths(False)
        total = sum(dflt) + 20 * (len(dflt) - 1)
        rows = [p.nominal_dim for p in master.by_category("布材") if 0 < p.nominal_dim <= total]
        if rows and total > max(rows) + 70:
            _row, fit = master.width_setup(max(rows))
            if fit:
                deck_ws = fit
                row_mm = max(rows)
    form, kind, post = _form_from_spec(spec)
    # ブラケット足場（くさびの支柱）はハーフアンチ1枚で狭いところに使う足場（利用者の指定 2026-10-24）。幅・作業床の
    # 指定が無ければ、系列のいちばん細い作業床（日建 240・信和 250）を1枚、その床用のブラケット（日建 NDBK03C 350・
    # 信和 SB-25 400）の長さを建地列の間隔にする（2026-10-24 に一度 300 にしたが、利用者の指定で 350 のまま: 「ごめん
    # ブラケットはば350でいいよ」）。以前は本足場と同じ 500 の板と 610 の腕で、狭いところに入らなかった
    if (form == "一側足場" and kind == "ブラケット" and not master.is_tube and not master.is_frame
            and not spec.get("deck_widths") and not width_mm):
        half = min((w for w in master.deck_widths_available() if w >= 200), default=None)
        brk = bracket_for_deck(master, half) if half else None
        if brk is not None:
            deck_ws = (half,)
            row_mm = int(brk.nominal_dim)
    config = ScaffoldConfig(
        scaffold_form=form,
        single_row_kind=kind,
        bracket_post=post,
        ladders=int(spec.get("ladders", 0) or 0),
        # 単管抱き足場は幅木を付けない（利用者の指定 2026-10-22）
        has_toe_board=not no_toe and not toe_off and kind != "抱き",
        net_brackets=spec.get("net_brackets", True) is not False,
        shita_san=toe_off and kind != "抱き",
        # 未指定なら系列の既定（A:400/250、B:405/240、次世代:500）を使う
        deck_widths=deck_ws,
        post_row_spacing_mm=row_mm,
        next_gen=spec.get("next_gen", False),
        sheet_type=str((spec.get("site") or {}).get("sheet_type", "メッシュシート")),
        pens=parse_pens(spec.get("pens")),
        guard_rail_type=rail_type,
        inner_guard_rail=bool(spec.get("inner_guard_rail", True)),
        end_guard=parse_end_guard(spec.get("end_guard")),
        line_mode_3d=bool(spec.get("line_mode_3d", False)),
        horizontal_net_levels=net_levels_from_spec(spec, elevation.n_levels),
        auto_inner_bracket=bool(spec.get("auto_inner_bracket", True)),
        post_reinforcement=spec.get("post_reinforcement", ""),
        period_days=spec.get("period_days", 60),
        asagao=build_asagao(spec, asagao_height_mm(elevation.total_height, master), master),
    )
    # 足場を掛ける面（一部の面だけ）。隣の面を掛けない端は開放端（妻側の手すり・幅木）
    faces = _faces_from_spec(spec, plan)
    if faces is not None:
        import dataclasses as _dc

        plan = _dc.replace(plan, edges=[e for e in plan.edges if e.edge_index in faces])
    # ブラケット足場と本足場の出隅を繋ぐ割付（面の組を解き直すとき solve_groups が渡す。corner_joins）
    joins = spec.get("_joins")
    if joins:
        from .corner_joins import apply_joins

        plan = apply_joins(plan, joins)
    model = ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elevation,
        config=config,
        building_height_mm=float(spec.get("building_height_mm", 0)),
        clearance_space_mm=float(spec.get("clearance_space_mm", 2000)),
        base_height_mm=float(spec.get("base_height_mm", 0) or 0),
    )
    model.faces_only = faces
    model.joined_ends = set(tuple(j) for j in ((joins or {}).get("joined") or []))
    # セットバックの上段の端（本体の足場に繋ぐ。setback_tiers）
    model.joined_ends |= {(int(j[0]), str(j[1])) for j in (spec.get("_joined_ends") or [])}
    model.group_neighbors = {int(k): dict(v) for k, v in (spec.get("_group_neighbors") or {}).items()}
    # 仮囲いの高さ（外部シートの下端。既定 3000＝仮囲いの鋼板 H3m。0 なら地面から）
    model.hoarding_height_mm = max(0.0, float(spec.get("hoarding_height_mm", 3000) or 0))
    # 入隅の升目の重なりを直す（隅から始まる面を通し、隅で終わる面はその外側建地列で止める。利用者の指摘
    # 2026-10-24: 入りすみが重なっているよ）。建地列間隔が決まってから（ScaffoldModel の後で）
    if not master.is_frame and form == "本足場":
        from .inner_corners import trim_inner_corners
        from .model import generate_wall_ties

        plan2, ic_joins, ic_notes = trim_inner_corners(model.plan, model.post_row_spacing_mm, master.span_lengths())
        if ic_joins:
            model.plan = plan2
            model.wall_ties = generate_wall_ties(plan2, elevation, config)
            model.inner_corner_joins = ic_joins
        model.plan.warnings.extend(ic_notes)
    # 面の区間だけ残す（面の途中で足場の種類を切り替えた組。face_forms の「南面[a-b]」→ _face_range）。区間を切り替えた
    # 面は、先に解いた組の面の形（スパン・始点と終点の支柱・離れ）をそのまま使う（_face_edge。切れ目の支柱と離れがそろう）
    if spec.get("_face_range"):
        _apply_face_range(model, spec["_face_range"], spec.get("_face_edge") or {})
    # 朝顔を付ける面（面名 → 辺番号）。面の組では、この組の面だけ
    asg = model.config.asagao
    if asg is not None and asg.faces:
        from .face_forms import split_key

        names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
        model.asagao_edges = {names[f] for f in asg.faces if f in names}
        # 面の一部だけ（「南面[a-b]」。元の面の始点の支柱から mm）。区間だけ残した面（face_offsets）は区間の始めを引く
        unknown = []
        for f in asg.faces:
            face, a, b = split_key(f)
            if a is None:
                if f not in names and f != "なし":
                    unknown.append(f)
                continue
            if face not in names:
                continue
            ei = names[face]
            x0 = float((model.face_offsets.get(ei) or (0.0, 0.0))[0])
            model.asagao_ranges.setdefault(ei, []).append((a - x0, b - x0))
        model.asagao_ranges = {ei: rs for ei, rs in model.asagao_ranges.items() if model.asagao_parts(ei)}
        if unknown and not spec.get("face_forms") and not spec.get("_group_neighbors") and not spec.get("faces"):
            model.plan.warnings.append(f"朝顔を付ける面「{'・'.join(unknown)}」は足場の面にありません"
                                       f"（面: {'・'.join(names)}）")
    model.obstacles = obstacles
    model.setbacks = spec.get("_setbacks") or []
    if face_eaves:
        _apply_face_eaves(model, face_eaves)
    return model


def _apply_face_range(model: ScaffoldModel, ranges: dict, given: dict | None = None) -> None:
    """面を区間 [始め, 終わり]（元の割付の面の始点の支柱から mm。終わり -1 は面の終点）だけ残す.

    面全体を同じスパンで解いたあとで、区間に入るスパンだけを残し、始点・終点の支柱を区間の端へ動かす。区間の端
    （面の途中）は開放端（range_ends）。区間の端にあった隅の隙間・入隅のつなぎは外し、壁つなぎは区間で作り直す。
    """
    import dataclasses as _dc
    import math as _m

    from .model import generate_wall_ties

    names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
    edges = []
    ends: set = set()
    offsets: dict = {}
    full_edges: dict = {}
    for ep in model.plan.edges:
        name = next((k for k, v in names.items() if v == ep.edge_index), "")
        rng = ranges.get(name)
        if not rng:
            edges.append(ep)
            continue
        g = (given or {}).get(name)
        if g:
            ep = _dc.replace(ep, spans=list(g["spans"]), start_post=tuple(g["start_post"]), end_post=tuple(g["end_post"]),
                             standoff=float(g["standoff"]), scaffold_length=float(sum(g["spans"])),
                             owned_post_count=len(g["spans"]))
        full_edges[name] = {"spans": list(ep.spans), "start_post": list(ep.start_post), "end_post": list(ep.end_post),
                            "standoff": float(ep.standoff)}
        posts = [0.0]
        for sp in ep.spans:
            posts.append(posts[-1] + float(sp))
        a = float(rng[0])
        b = posts[-1] if float(rng[1]) < 0 else float(rng[1])
        i0 = min(range(len(posts)), key=lambda i: abs(posts[i] - a))
        i1 = min(range(len(posts)), key=lambda i: abs(posts[i] - b))
        if i1 <= i0:
            continue
        (sx, sy), (ex, ey) = ep.start_post, ep.end_post
        ln = _m.hypot(ex - sx, ey - sy) or 1.0
        ux, uy = (ex - sx) / ln, (ey - sy) / ln
        spans = list(ep.spans[i0:i1])
        x0, x1 = posts[i0], posts[i1]
        edges.append(_dc.replace(ep, spans=spans, scaffold_length=float(sum(spans)), owned_post_count=len(spans),
                                 start_post=(sx + ux * x0, sy + uy * x0), end_post=(sx + ux * x1, sy + uy * x1)))
        if i0 > 0:
            ends.add((ep.edge_index, "s"))
        if i1 < len(posts) - 1:
            ends.add((ep.edge_index, "e"))
        offsets[ep.edge_index] = (x0, posts[-1])
    steps = [c for c in (model.plan.corner_steps or [])
             if (c.edge_index, "s" if getattr(c, "at_start", False) else "e") not in ends]
    model.plan = _dc.replace(model.plan, edges=edges, corner_steps=steps)
    model.range_ends = ends
    model.face_offsets = offsets
    model.face_full_edges = full_edges
    model.inner_corner_joins = [j for j in (getattr(model, "inner_corner_joins", None) or [])
                                if (j[0], "e") not in ends and (j[1], "s") not in ends]
    model.wall_ties = generate_wall_ties(model.plan, model.elevation, model.config)


def _obstacles_from_spec(spec: dict, plan, face_eaves: dict[int, float]):
    """庇・バルコニー（スラブから・入力から）→ (かわす張り出し, 面ごとの最小の離れ, 案内文).

    足場の立つ面（地盤・下の屋根）と同じ高さのスラブは張り出しとみなさない（足場はその上に立つ）。
    面の足場より上（軒高＋2m）の張り出しも足場に関係しない。
    """
    from .obstacles import detect_eaves, from_spec, plan_avoidance

    names = dict(zip([e.edge_index for e in plan.edges], plan.face_names()))
    base = float(spec.get("base_height_mm", 0) or 0)
    obs, _sb, notes = from_spec(spec, names)
    if spec.get("slabs") and spec.get("height_from_slabs", True):
        limit = {ei: base + v + 2000.0 for ei, v in face_eaves.items()}
        slabs = [s for s in spec["slabs"] if float(s["top_mm"]) > base + 300.0]
        found = detect_eaves(plan.outline.edges, slabs, top_limit=limit or None)
        manual = {o.edge_index for o in obs}
        obs += [o for o in found if o.edge_index not in manual]
    obs = [o for o in obs if o.edge_index in names]
    av = plan_avoidance(plan.outline.edges, plan.standoffs, obs, names,
                        plan.standoff_spec.target if plan.standoff_spec else 300.0)
    return av.obstacles, av.face_min, notes + av.notes


def _faces_from_spec(spec: dict, plan):
    """入力の faces（面名「南面」「南」や辺番号の並び、カンマ区切りの文字列も可）→ 辺番号の集合。無指定・全部なら None."""
    v = spec.get("faces")
    if v in (None, "", []):
        return None
    items = [t.strip() for t in str(v).replace("、", ",").split(",")] if isinstance(v, str) else list(v)
    names = plan.face_names()
    out = set()
    for t in items:
        if isinstance(t, int) or str(t).isdigit():
            out.add(int(t))
            continue
        hit = [e.edge_index for e, n in zip(plan.edges, names)
               if n == t or n.replace("面", "") == str(t).replace("面", "")]
        if not hit:
            raise InputError(f"faces: 面「{t}」がありません（{'・'.join(names)}）")
        out.update(hit)
    if out >= {e.edge_index for e in plan.edges}:
        return None
    return out


def _face_eaves_from_spec(spec: dict, plan) -> dict[int, float]:
    """面ごとの軒高（足場の立つ高さからの mm）。slabs（スラブの外形と天端）か face_eaves_mm（面名・辺番号→軒高）.

    slabs は足場の立つ高さ base_height_mm（下の屋根の上に建てるとき）を引いて、立つ面からの高さにする。
    """
    out: dict[int, float] = {}
    base = float(spec.get("base_height_mm", 0) or 0)
    if spec.get("slabs") and spec.get("height_from_slabs", True):
        from .slab_heights import SlabInfo, face_base_mm, face_eaves_mm

        slabs = [SlabInfo([tuple(p) for p in s["polygon_mm"]], float(s["top_mm"])) for s in spec["slabs"]]
        tops = face_eaves_mm(plan.outline.edges, slabs)
        if spec.get("base_height_mm") is None and tops:
            # 足場の立つ高さ: 面の外側（建地の下）にある、面の軒高より十分低いスラブ（下の屋根）。
            # 上のスラブだけを選んで実行したとき、下の屋根の上に建てる。面ごとに違えば低い方（地盤に立つ面がある）
            out_mm = max(float(s_) for s_ in plan.standoffs) + 300.0 if plan.standoffs else 600.0
            bases = face_base_mm(plan.outline.edges, slabs, tops, out_mm)
            if bases:
                base = min(bases.values())
                if base > 0:
                    spec["base_height_mm"] = base
                    plan.warnings.append(f"足場は下の屋根（天端 GL+{base:.0f}）の上に建てます（スラブから自動）")
                if len({round(v) for v in bases.values()}) > 1:
                    plan.warnings.append("面によって立つ高さが違います（" + "・".join(f"{v:.0f}" for v in bases.values())
                                         + "）。低い方に合わせて建てています。高い屋根の上に立つ面は、その面だけ選び直してください")
        # 小さなセットバック（奥行き setback_bracket_max_mm 以下）は、足場を上の屋根まで上げて内ブラケットでかわす
        if spec.get("avoid_obstacles", True):
            from .obstacles import SETBACK_MAX_MM, detect_setbacks

            sbs = detect_setbacks(plan.outline.edges, spec["slabs"], tops,
                                  float(spec.get("setback_bracket_max_mm", SETBACK_MAX_MM)))
            names0 = dict(zip([e.edge_index for e in plan.edges], plan.face_names()))
            for sb in sbs:
                plan.warnings.append(
                    f"{names0.get(sb.edge_index, sb.edge_index)}: セットバック（GL+{sb.height_mm:.0f} から上が奥へ"
                    f"{sb.depth_mm:.0f}mm）は、足場を上の屋根（GL+{sb.upper_top_mm:.0f}）まで上げ、内ブラケットでかわします")
                tops[sb.edge_index] = sb.upper_top_mm
            spec["_setbacks"] = sbs
        for ei, top in tops.items():
            if top - base > 0:
                out[ei] = top - base
    if spec.get("setbacks") and spec.get("avoid_obstacles", True):
        from .obstacles import from_spec as _sb_spec

        names0 = dict(zip([e.edge_index for e in plan.edges], plan.face_names()))
        _o, sbs2, _n = _sb_spec({"setbacks": spec["setbacks"]}, names0)
        spec["_setbacks"] = [s for s in (spec.get("_setbacks") or []) if s.edge_index not in {x.edge_index for x in sbs2}] + sbs2
        for sb in sbs2:
            if sb.upper_top_mm > 0:
                out[sb.edge_index] = sb.upper_top_mm - base
    names = plan.face_names()
    for k, v in (spec.get("face_eaves_mm") or {}).items():
        ei = None
        if isinstance(k, int) or str(k).isdigit():
            ei = int(k)
        else:
            for e, n in zip(plan.edges, names):
                if n == k or n.replace("面", "") == str(k).replace("面", ""):
                    ei = e.edge_index
        if ei is not None:
            out[ei] = float(v)
    return out


def _apply_face_eaves(model: ScaffoldModel, face_eaves: dict[int, float]) -> None:
    """低い面の立面を全体の立面から切り出し、その面の上の壁つなぎを外す。面ごとの高さを警告に書く."""
    from .elevation_solver import truncate_elevation

    names = model.plan.face_names()
    lines = []
    for e, n in zip(model.plan.edges, names):
        ev = face_eaves.get(e.edge_index)
        if ev is None:
            continue
        fe = truncate_elevation(model.elevation, ev, model.master)
        if fe is not model.elevation:
            model.face_elevations[e.edge_index] = fe
        lines.append(f"{n} 軒高{ev / 1000:.2f}m→{fe.n_levels}層・足場高さ{fe.total_height / 1000:.2f}m")
    model.clip_ties_to_faces()
    if model.face_elevations:
        model.plan.warnings.append("面ごとの高さ（スラブの天端から。大きくセットバックした上の階は、途中の屋根の上から"
                                   "上段の足場を建てて繋ぎます）: " + "／".join(lines))
    elif lines:
        model.plan.warnings.append("軒高はスラブの天端から: " + "／".join(lines))


def build_asagao(spec: dict, height_mm: int, master=None) -> AsagaoSpec | None:
    """朝顔の入力。指定がなければ高さから必要段数を自動設定する（10m以上で1段・20m以上で2段）."""
    a = spec.get("asagao")
    if a is False:  # 明示的に「設置しない」
        return None
    need = required_asagao_stages(height_mm)
    if a is None:
        return AsagaoSpec(stages=need) if need else None
    kind = a.get("kind", ASAGAO_KIND_ASAGAO)
    if kind not in ASAGAO_KINDS:
        raise InputError(f"asagao.kind: {' か '.join(ASAGAO_KINDS)} です（{kind!r}）")
    if kind == ASAGAO_KIND_SAFE_WING:
        # 簡易落下物防止機材。張出・角度は資料値で固定（マスタにあれば系列の実寸）
        wing = next((p for p in master.by_category("朝顔") if p.note.startswith("セーフウイング")), None) \
            if master is not None else None
        return AsagaoSpec(
            stages=a.get("stages", need or 1),
            kind=kind,
            faces=parse_asagao_faces(a.get("faces")),
            projection_mm=a.get("projection_mm", float(wing.nominal_dim) if wing else SAFE_WING_PROJECTION_MM),
            angle_deg=a.get("angle_deg", SAFE_WING_ANGLE_DEG),
            tie_every_spans=a.get("tie_every_spans", 2),
        )
    return AsagaoSpec(
        stages=a.get("stages", need),
        projection_mm=a.get("projection_mm", 2000.0),
        angle_deg=a.get("angle_deg", 25.0),
        tie_every_spans=a.get("tie_every_spans", 2),
        faces=parse_asagao_faces(a.get("faces")),
    )


def parse_end_guard(value) -> str:
    """妻側の墜落防止: "布材"（既定）か "ブレス材"（「ブレス」「先行手すり」も）."""
    v = str(value or "").strip()
    if v in ("ブレス材", "ブレス", "先行手すり", "先行手摺", "brace"):
        return "ブレス材"
    if v in ("", "布材", "手すり", "rail"):
        return "布材"
    raise InputError(f"end_guard: 布材 か ブレス材 です（{value!r}）")


def parse_asagao_faces(value) -> list[str]:
    """朝顔を付ける面: ["南面", "東面"]・"南面・東面"・"全部"・空 → 面名の並び（空は全部の面）.

    面の一部だけなら区間つき「南面[3600-9000]」（元の面の始点の支柱から mm）。"なし" はどの面にも付けない。
    """
    if not value:
        return []
    if isinstance(value, str) and value.strip() == "なし":
        return ["なし"]                                     # どの面にも付けない
    if isinstance(value, str):
        for sep in ("、", ",", ";", "；", " ", "　"):
            value = value.replace(sep, "・")
        items = value.split("・")
    else:
        items = [str(v) for v in value]
    out = []
    for t in items:
        t = t.strip()
        if not t or t in ("全部", "全て", "すべて", "全面", "全部の面"):
            continue
        out.append(t if t.endswith("面") or "(" in t or "[" in t else t + "面")
    return out


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


def _tight_faces_for_outside(model: ScaffoldModel, clearances) -> dict[int, list[tuple[float, float]]]:
    """外付けの階段に足場の外の空き（建地列の間隔＋余裕）が足りない面 → 面全体を避ける区間に.

    空いた面が1つも無ければ避けない（どこかに置いて、空きが足りない注意を出す）。
    """
    from .stairs import OUTSIDE_SPACE_MARGIN_MM

    need = float(model.post_row_spacing_mm) + OUTSIDE_SPACE_MARGIN_MM
    tight = {c.edge_index for c in clearances or [] if c.min_mm < need}
    roomy = {e.edge_index for e in model.plan.edges} - tight
    if not tight or not roomy:
        return {}
    return {e.edge_index: [(0.0, float(e.scaffold_length))] for e in model.plan.edges if e.edge_index in tight}


def _merge_ranges(*maps: dict) -> dict[int, list[tuple[float, float]]]:
    """辺ごとの区間一覧を結合する（階段室の自動配置が避ける区間）."""
    out: dict[int, list[tuple[float, float]]] = {}
    for m in maps:
        for k, v in (m or {}).items():
            out.setdefault(k, []).extend(v)
    return out


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
            has_fence=s.get("has_fence", True),
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
            landing_levels=[int(v) for v in h.get("landing_levels", [])],
            note=h.get("note", ""),
            cage_width_mm=float(h.get("cage_width_mm", 2000)),
            cage_depth_mm=float(h.get("cage_depth_mm", 2000)),
            load_kn=float(h.get("load_kn", 0.0)),
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
    openings, terrain, platforms, checks=None, quantity=None, conflicts=None,
) -> list[tuple[str, str, str]]:
    """是正・確認が要る項目を (分類, 重大度, 本文) で集める.

    総合判定と結果JSONで同じものを数えるための一箇所。別々に組み立てていた
    ときは、判定が法規チェックのWARNしか数えず、離れの措置や未確認耐力値が
    「要確認0件」の裏に隠れていた。
    """
    out: list[tuple[str, str, str]] = []
    # 法規チェックのNGは条文つきの本文を出す。件数だけ（「法規チェックNG 1件」）だと
    # どの条文で落ちたか、割付レポートの表まで探さないと分からない（実機の五角形棟で
    # 昇降設備までの水平移動30m超が理由だったのに、ツールバーの出力に無かった）
    ng_checks = [c for c in (checks or []) if c.status == "NG"]
    # 昇降設備までの移動距離超過は階段の配置側も同じ事象を（何箇所要るかまで書いて）
    # 挙げる。NG の本文に対処として畳み込み、1件にする
    travel_fix = [w for w in stair_plan.warnings if "最大水平移動距離" in w]
    plan_warnings = [w for w in stair_plan.warnings if w not in travel_fix] if any(
        "最大水平移動距離" in c.message for c in ng_checks) else list(stair_plan.warnings)
    for c in ng_checks:
        text = f"法規チェック[NG] #{c.check_id} {c.name}: {c.message}（{c.basis}）"
        if "最大水平移動距離" in c.message and travel_fix:
            text += "／対処: " + "；".join(travel_fix)
        out.append(("法規チェック", "NG", text))
    out += [("構造", "WARN", w) for w in structural.warnings]
    out += [("割付", "WARN", w)
            for w in model.plan.warnings + model.elevation.warnings]
    out += [("ブラケット区間", i.severity,
             f"ブラケット[{i.severity}] {i.message}（{i.basis}）")
            for i in bracket_issues]
    out += [("階段", "WARN", w) for w in plan_warnings]
    # 配置時の警告（何箇所要るかまで書いてある）と検証の警告が同じ移動距離超過を
    # 二重に挙げていた。配置側（または上の法規NG）にあれば検証側は重ねない
    travel_said = any("最大水平移動距離" in w for w in stair_plan.warnings)
    out += [("階段", "WARN", f"階段[WARN] {w}") for w in stair_issues
            if not (travel_said and "最大水平移動距離" in w)]
    # 重大度を本文にも出す。NGと注意が同じ見た目だと、どれが止まる項目か分からない
    out += [("開口部", i.severity, f"開口部[{i.severity}] {i.message}")
            for i in openings.issues]
    # 法規チェックが同じ文面で挙げている事象は、そちらが条文つきで出るので重ねない
    said = {c.message for c in (checks or []) if c.status == "WARN"}
    out += [("敷地", "WARN", f"敷地: {w}")
            for w in terrain.warnings if w not in said]
    # 「マスタに無い」「カタログ品では受けられない」は手配・検討が要る。
    # 数量注記に埋もれると発注漏れになる
    kinds = getattr(quantity, "warning_kinds", {})
    out += [(f"数量・{kinds.get(w, '手配')}", "WARN", w)
            for w in getattr(quantity, "warnings", [])]
    out += [("荷受けステージ・昇降機", i.severity,
             f"{i.kind}[{i.severity}] {i.message}（{i.basis}）")
            for i in platforms.issues]
    # 付帯設備どうし・開口部との衝突。個々の検証は通っても同じ区間には組めない
    out += [("付帯設備の衝突", i.severity,
             f"{i.kind}[{i.severity}] {i.message}（{i.basis}）")
            for i in (conflicts or [])]
    return out


def build_verdict(
    check_summary, structural, platforms, openings, bracket_issues,
    warnings: list[tuple[str, str, str]] | None = None, conflicts=None,
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
        blockers.append(
            f"壁つなぎ 検定比{structural.wall_tie.ratio}"
            if math.isfinite(structural.wall_tie.ratio)
            else "壁つなぎ 0本のため検定不能"
        )
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
    n_cf = len([i for i in (conflicts or []) if i.severity == "NG"])
    if n_cf:
        blockers.append(f"付帯設備の衝突NG {n_cf}件")
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


@dataclass
class PlanRun:
    """1回の計画で解いたものを一式で持つ.

    CLI・Archicadのツールバー・実機E2Eが同じ手順で解くための入れ物。
    以前はスクリプトごとに手順を書いていたので、ツールバーから出る成果物だけ
    構造計算も総合判定も無い薄いものになっていた。
    """

    spec: dict
    model: ScaffoldModel
    site: SiteCondition
    tie_opt: object
    brackets: list
    bracket_issues: list
    stair_plan: object
    stair_issues: list
    platforms: object
    openings: object
    conflicts: list
    terrain: object
    checks: list
    quantity: object
    structural: object
    detail_sheets: list
    warnings: list
    verdict: dict

    @property
    def name(self) -> str:
        return self.spec.get("project_name", "ashiba")

    @property
    def file_stem(self) -> str:
        """帳票のファイル名に使う工事名（使えない文字を落とした形）."""
        return safe_file_stem(self.name)


def net_levels_from_spec(spec: dict, n_levels: int) -> list[int]:
    """horizontal_net_levels（[2, 5] や "2,5"）→ 作業層の番号の列（範囲外・重複は除く）."""
    from .spec_object import parse_int_list

    raw = spec.get("horizontal_net_levels")
    if raw is None:
        return []
    # 1段目（最下段の作業床）は地面に近いので層間ネットは張らない（利用者の指摘 2026-10-24: 1段目はそうかんネット
    # いらないのでは）。「全部」「自動」は第2層から。番号で 1 を書いたときだけ張る
    if isinstance(raw, str) and raw.strip() in ("全部", "全層", "すべて", "全て"):
        return list(range(2, n_levels + 1))
    if isinstance(raw, str) and raw.strip().startswith("自動"):
        # 層間ネットの決まり（利用者の資料 2026-10-24）: 幅木を使うなら2層毎、使わないなら全層（どちらも1段目は除く）
        if spec.get("toe_board", True) is False:
            return list(range(2, n_levels + 1))
        return list(range(2, n_levels + 1, 2))
    return sorted({v for v in parse_int_list(raw) if 1 <= v <= n_levels})


def _manual_ties(spec: dict, model: ScaffoldModel):
    """入力の wall_ties_manual → 壁つなぎの一覧（無ければ None）。面は edge_index か face（面名）."""
    from .model import WallTie

    rows = spec.get("wall_ties_manual")
    if rows is None:
        return None
    names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
    built = {e.edge_index for e in model.plan.edges}
    out = []
    for i, t in enumerate(rows):
        ei = t.get("edge_index")
        if ei is None and t.get("face") in names:
            ei = names[t["face"]]
        if ei is None or int(ei) not in built:
            raise InputError(f"wall_ties_manual[{i}]: 面（edge_index か face）が足場の面に当たりません（{t!r}）")
        out.append(WallTie(int(ei), float(t["position_mm"]), int(t["height_mm"]), t.get("kind", "grid")))
    return out


def all_face_names(spec: dict, master_csv: Path | None = None) -> list[str]:
    """建てる面の名前（外形の辺の方位。入力の faces で絞っていればその面だけ）."""
    master = load_master(resolve_series_id(spec), master_csv)
    plan = solve_plan(spec["outline_mm"], master, StandoffSpec())
    names = plan.face_names()
    faces = _faces_from_spec(spec, plan)
    return [n for e, n in zip(plan.edges, names) if faces is None or e.edge_index in faces]


def corner_owners(out: list) -> tuple[dict[int, int], dict[int, int]]:
    """面の組の結果 → ({辺: 面の始点の隅まで来ている組}, {辺: 面の終点の隅まで来ている組}).

    面の区間を切り替えると同じ面が複数の組に入る。隅で隣と繋ぐのは、その隅まで来ている区間の組（range_ends で
    切れ目の側の端を持たない組）。
    """
    own_s: dict[int, int] = {}
    own_e: dict[int, int] = {}
    for k, (_l, r) in enumerate(out):
        m = r.model
        for e in m.plan.edges:
            if (e.edge_index, "s") not in m.range_ends:
                own_s.setdefault(e.edge_index, k)
            if (e.edge_index, "e") not in m.range_ends:
                own_e.setdefault(e.edge_index, k)
    return own_s, own_e


def _group_neighbors(out: list) -> dict[int, dict]:
    """面の組の結果 → {組の番号: {隣の面の辺番号: {"row", "height"}}}. 本足場どうしの出隅だけ（ブラケットは corner_joins）."""
    from .corner_joins import _kind

    own_s, own_e = corner_owners(out)
    if not own_s and not own_e:
        return {}
    outline = out[0][1].model.plan.outline
    n = len(outline.edges)
    res: dict[int, dict] = {}
    for k, (_l, r) in enumerate(out):
        m = r.model
        if _kind(m) != "main":
            continue
        for e in m.plan.edges:
            ei = e.edge_index
            prev, nxt = (ei - 1) % n, (ei + 1) % n
            for end, adj, corner, ka in (("s", prev, outline.edges[ei].start_corner, own_e.get(prev)),
                                         ("e", nxt, outline.edges[ei].end_corner, own_s.get(nxt))):
                if (ei, end) in m.range_ends:          # 区間の切れ目は隅ではない
                    continue
                if ka is None or ka == k or corner != "出隅" or _kind(out[ka][1].model) != "main":
                    continue
                ma = out[ka][1].model
                res.setdefault(k, {})[adj] = {"row": float(ma.post_row_spacing_mm),
                                              "height": float(ma.elevation_of(adj).total_height)}
    return res


def solve_groups(spec: dict, master_csv: Path | None = None) -> list[tuple[str, PlanRun]]:
    """面ごとの足場の切り替え（face_forms）を含む入力を、面の組ごとに解く → [(組の名前, 結果)].

    切り替えが無ければ [("", solve_all(spec))]。組の名前は "" が切り替えていない面、ほかは種類（face_forms）。
    大きなセットバックの上の階は、途中の屋根の上から建てる「上段」の組を後ろに足す（setback_tiers。
    利用者の指定 2026-10-24: セットバックの時は途中の屋根から足場が繋がるようにする仕組みを作って）。
    """
    from .setback_tiers import tier_note, tier_specs

    out = _solve_face_groups(spec, master_csv)
    for label, sub in tier_specs(spec, lambda ol: all_face_names({**spec, "outline_mm": ol, "faces": None}, master_csv)):
        r = solve_all(sub, master_csv)
        out.append((label, r))
        note = tier_note(label, sub)
        if note:
            out[0][1].model.plan.warnings.append(note)
    return out


def _solve_face_groups(spec: dict, master_csv: Path | None = None) -> list[tuple[str, PlanRun]]:
    from .face_forms import face_groups

    if not spec.get("face_forms"):
        return [("", solve_all(spec, master_csv))]
    validate_spec(spec)
    try:
        groups = face_groups(spec, all_face_names(spec, master_csv))
    except ValueError as e:
        raise InputError(str(e))
    # 面の区間を切り替えた面は、どの組も同じスパン（先に解いた組の、区間で切る前のスパン）で解いてから区間で切る。
    # 区間の切れ目の支柱が組どうしでそろう（利用者の指定 2026-10-24: 選んだ部品だけ足場を変える）
    out = []
    full_edges: dict = {}
    for i, (label, sub) in enumerate(groups):
        rng = sub.get("_face_range") or {}
        given = {f: full_edges[f] for f in rng if f in full_edges}
        if given:
            sub = {**sub, "_face_edge": given}
            groups[i] = (label, sub)
        r = solve_all(sub, master_csv)
        for f, fe in (getattr(r.model, "face_full_edges", None) or {}).items():
            full_edges.setdefault(f, fe)
        out.append((label, r))
    # 隣の面がほかの組なら、その面の離れはその組で解いた値（隅の位置が組ごとにずれないように）
    own = {e.edge_index: float(e.standoff) for _l, r in out for e in r.model.plan.edges}
    n_out = len(out[0][1].model.plan.outline.edges) if out else 0
    again = {}
    for k, (_label, r) in enumerate(out):
        mine = {e.edge_index for e in r.model.plan.edges}
        nb = {}
        for ei in mine:
            for adj in ((ei - 1) % n_out, (ei + 1) % n_out):
                if adj not in mine and adj in own and abs(own[adj] - float(r.model.plan.standoffs[adj])) > 0.5:
                    nb[adj] = own[adj]
        if nb:
            again[k] = nb
    # 本足場どうし（幅の違う本足場など）の出隅は、組をまたいでも同じ組の隅と同じに納める（外側の升目を始点の面が
    # 描き、妻側の手すりは付けず、隅の内側建地は1本）。利用者の指摘 2026-10-24: 端部が重なったり、回れないようになってる
    nbs = _group_neighbors(out)
    if again or nbs:
        groups = [(label, {**sub, **({"_neighbor_standoffs": again[k]} if k in again else {}),
                           **({"_group_neighbors": nbs[k]} if k in nbs else {})})
                  for k, (label, sub) in enumerate(groups)]
        out = [(label, solve_all(sub, master_csv)) if (k in again or k in nbs) else out[k]
               for k, (label, sub) in enumerate(groups)]
    # ブラケット足場と本足場の出隅: 本足場をブラケットの支柱の列まで延ばして解き直す（利用者の指定 2026-10-23）
    from .corner_joins import bracket_corner_joins

    if spec.get("corner_joins", True):
        joins = bracket_corner_joins(out)
        if joins:
            groups = [(label, {**sub, "_joins": joins[k]} if k in joins else sub) for k, (label, sub) in enumerate(groups)]
            out = [(label, solve_all(sub, master_csv)) if k in joins else out[k]
                   for k, (label, sub) in enumerate(groups)]
    # 階段の無い組は、ほかの組の面の階段で昇降する（足場は面の組をまたいでつながっている）
    stair_faces = [r.model.face_name(t.edge_index) for _l, r in out
                   for t in (getattr(r.stair_plan, "towers", None) or [])]
    if stair_faces:
        for k, ((label, sub), (_l, r)) in enumerate(zip(groups, out)):
            if not getattr(r.stair_plan, "towers", None) and (getattr(r.model, "auto_ladders", False) or any(
                    c.check_id == 12 and c.status != "OK" for c in r.checks)):
                out[k] = (label, solve_all({**sub, "stairs_elsewhere": list(dict.fromkeys(stair_faces))}, master_csv))
                continue
            # 切り替えた組（境界に合わせた狭い面など）の階段が敷地境界に当たるなら、ほかの組の階段を使う
            # （2026-10-24: 道路側を本足場（狭い幅）にしたら、その面に外付け階段を置いて道路境界に当たった）
            others = [f for f in stair_faces if f not in {r.model.face_name(t.edge_index)
                                                           for t in (r.stair_plan.towers or [])}]
            hit = [c for c in r.conflicts if c.severity == "NG" and "階段" in c.message]
            if label and others and hit and not (sub.get("stairs") or {}).get("positions"):
                out[k] = (label, solve_all({**sub, "stairs": {**(sub.get("stairs") or {}), "count": 0},
                                            "stairs_elsewhere": list(dict.fromkeys(others))}, master_csv))
    return out


def solve_all(spec: dict, master_csv: Path | None = None) -> PlanRun:
    """入力仕様を解く（ファイル出力・Archicad配置は呼び側の仕事）.

    面ごとの足場の切り替え（face_forms）は solve_groups で面の組に分けてから解く。
    """
    if spec.get("face_forms"):
        raise InputError("face_forms（面ごとの足場の切り替え）は面の組ごとに解きます（solve_groups）")
    validate_spec(spec)
    model = build_model(spec, master_csv)
    check_edge_indices(spec, model)
    model.stairs_elsewhere = [str(f) for f in (spec.get("stairs_elsewhere") or [])]
    site = build_site(spec)
    # 開口部を先に解く（壁つなぎの最適化は抜いた支柱を避けた状態で検定する。
    # 階段の自動配置も梁枠の区間（通路）を避ける）
    openings = validate_openings(model, build_openings(spec))
    # 壁つなぎは風荷重の検定から逆算して確定させる（数量・法規チェックに反映するため先に実行）
    # 取付部（朝顔・ステージ）の壁つなぎも最適化の検定に載せるため、付帯設備を先に解く
    platforms = validate_platforms(model, *build_platforms(spec))
    tie_opt = optimize_wall_ties(model, site, openings=openings, platforms=platforms)
    model.plan.warnings.extend(tie_opt.notes)
    # 手で直した壁つなぎ（Archicad で部品を動かした・消した・足したのを解き直しが読み戻したもの）。
    # 最適化の配置の代わりにこの本数・位置で検定・数量・図を出す
    manual = _manual_ties(spec, model)
    if manual is not None:
        model.wall_ties = manual
        model.plan.warnings.append(
            f"壁つなぎは手で直した配置（{len(manual)}本）で検定・数量を出しています"
            "（自動の配置に戻すには条件ファイルの wall_ties_manual を消す）")
    brackets = build_brackets(spec)
    # 離れが目標上限を超える面には内ブラケットを自動で付ける（入力で切れる）。庇をかわして離れを広げた面・
    # セットバックの面は、層ごとに隙間を詰める（庇に当たる区間は外す。obstacles）
    if model.config.auto_inner_bracket:
        from .brackets import auto_inner_brackets
        from .obstacles import avoidance_brackets

        so_spec = model.plan.standoff_spec
        av_br, av_notes = [], []
        if model.obstacles or model.setbacks or model.plan.face_shift:
            av_br, av_notes = avoidance_brackets(model, brackets, model.obstacles, model.setbacks,
                                                 so_spec.fall_protection_limit if so_spec else 300.0,
                                                 so_spec.max if so_spec else 350.0)
        auto, auto_notes = auto_inner_brackets(
            model, brackets + av_br, so_spec.max if so_spec else 350.0,
            so_spec.fall_protection_limit if so_spec else 300.0)
        auto = av_br + auto
        auto_notes = av_notes + auto_notes
        brackets += auto
        # 内ブラケットで措置した面は、割付が出していた「検討してください」を外す
        # （同じ文面を複数面でまとめた警告は、措置した面だけ名前から抜く）
        resolved: dict[str, set[str]] = {}
        for sec in auto:
            ep = next(e for e in model.plan.edges if e.edge_index == sec.edge_index)
            covered = max((sum(s.end_mm - s.start_mm for s in auto if s.edge_index == ep.edge_index
                               and (not s.levels or lv in s.levels)) for lv in range(1, model.elevation.n_levels + 1)),
                          default=0.0)
            if covered < ep.scaffold_length - 1.0 and ep.edge_index not in model.plan.face_shift:
                continue      # 張出の範囲は詰まっていない。措置の注意は残す
            if ep.remedy:
                resolved.setdefault(ep.remedy, set()).add(model.face_name(ep.edge_index))
            ep.remedy = None
        kept = []
        for w in model.plan.warnings:
            label, sep, rest = w.partition(": ")
            if sep and rest in resolved:
                faces = [f for f in label.split("・") if f not in resolved[rest]]
                if not faces:
                    continue
                w = f"{'・'.join(faces)}: {rest}"
            kept.append(w)
        model.plan.warnings[:] = kept + auto_notes
    bracket_issues = validate_bracket_sections(model, brackets)
    # 枠組の手すりは建枠一体。先行手すり工法の指定は効かないので、黙って無視しない
    if model.master.is_frame and spec.get("guard_rail_type") == GUARD_RAIL_ADVANCE:
        model.plan.warnings.append(
            "枠組足場では先行手すり工法（guard_rail_type）は適用されません。手すりは建枠一体で、"
            "最上層のみ布材で手すり・中桟を組みます。指定は無視しました"
        )
    # 外形を整理した（反転・重複除去・渡し）うえで辺番号つきの付帯設備があるなら、
    # その番号が入力の頂点順と一致しない可能性を先に言う
    def _uses_index(lst) -> bool:
        return any(isinstance(x, dict) and x.get("face") is None for x in (lst or []))

    edge_keys = [k for k in ("openings", "loading_stages", "hoists", "bracket_sections")
                 if _uses_index(spec.get(k))]
    if _uses_index(spec.get("stairs", {}).get("positions")):
        edge_keys.append("stairs.positions")
    if edge_keys and model.plan.outline.notes:
        model.plan.warnings.append(
            "外形を整理したため（" + "／".join(n.split("。")[0] for n in model.plan.outline.notes)
            + "）、辺番号が入力の頂点順とずれている可能性があります。"
            + "・".join(edge_keys) + " の edge_index は、平面割付表の辺・面名・躯体頂点で"
            "指定した面に当たっているか確認してください（辺番号の代わりに face: \"北面\" で"
            "面名指定もできます）"
        )
    st = spec.get("stairs", {})
    # 階段の付け方（足場の中／外付け／自動。自動は幅 900 以上なら中、900 未満なら外付け）。外付けの区間は
    # 上り口＋階段＋降り口（利用者の指摘 2026-10-20: 上り口と降り口に横のスパンが要る）なので2スパン長い
    from .stairs import decide_outside

    # 敷地境界線があれば、面ごとの足場の外の空き（境界までの離れ）を測る。外付け階段の自動はいちばん空いた面で決める
    from .site_boundary import face_clearances, parse_boundary

    bnd, roads = parse_boundary(spec)
    clearances = face_clearances(model, bnd, roads) if bnd else []
    if bnd:
        model.site_boundary_mm = bnd
        model.site_road_edges = roads
    if clearances:
        # 躯体外面から敷地境界までの水平スペース（法規#1 本足場原則・収まり）は、建てる面のうちいちばん狭い面の値
        from .site_boundary import POST_R_MM

        so = {e.edge_index: float(e.standoff) for e in model.plan.edges}
        model.clearance_space_mm = min(c.min_mm + POST_R_MM + float(model.post_row_spacing_mm) + so.get(c.edge_index, 0.0)
                                       for c in clearances)
    space = float(spec.get("clearance_space_mm", 2000))
    if clearances:
        space = min(space, max(c.min_mm for c in clearances))
    outside, why = decide_outside(model, st.get("layout"), space)
    tspans = int(st.get("tower_spans", 2)) + (2 if outside else 0)
    hug_no_stairs = model.no_stair_tower and not st.get("positions") and not st.get("count")
    if hug_no_stairs:
        # 単管抱き足場（布2本の床）・ブラケット足場（一側）に階段は入らない。昇降はほかの面の階段か、はしご等を別に
        # （数量・図に階段を出さない。利用者の指摘 2026-10-22・23: 階段はつけれない寸法）
        stair_plan = auto_place_stairs(model, max_travel_mm=st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM),
                                       tower_spans=tspans, count=0)
        if (not model.config.ladders and not model.stairs_elsewhere
                and model.scaffold_height_mm > MIN_HEIGHT_FOR_STAIRS_MM):
            # ほかの面の階段も、入力のはしごも無い → はしごを外周 60m ごとに1箇所（水平移動 30m 以内）
            per = sum(float(e.scaffold_length) for e in model.plan.edges)
            model.config.ladders = max(1, math.ceil(per / (2.0 * DEFAULT_MAX_TRAVEL_MM)))
            model.auto_ladders = True
            model.plan.warnings.append(
                f"{model.config.form_label}は階段を付けられない寸法（床の幅に階段枠が入らない）なので、昇降は"
                f"はしご {model.config.ladders}箇所（水平移動 30m 以内）にしました。独立の階段（900 枠か 600 枠 2 列）を"
                "別に立てる場合は stairs で位置を指定してください")
    elif st.get("positions"):
        # 位置を指定した場合はそれを使う（自動配置と同じ検証は通す）
        stair_plan = place_stairs_at(
            model,
            st["positions"],
            tower_spans=tspans,
            max_travel_mm=st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM),
        )
    else:
        stair_plan = auto_place_stairs(
            model,
            max_travel_mm=st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM),
            tower_spans=tspans,
            # stairs.count が無ければ n_stairs を使う。どちらも書かなければ
            # 移動距離から自動算出（n_stairs は既定値1なので、明示時だけ効かせる）
            count=st.get("count"),
            min_per_face=st.get("min_per_face", 0),
            avoid=_merge_ranges(opening_ranges(openings), platform_ranges(model, platforms),
                                _tight_faces_for_outside(model, clearances) if outside else {}),
            # 外付けは足場の外に出るので、上り口・降り口のスパンがコーナーに掛かってよい
            corner_gap=0 if outside else 1,
        )
    if stair_plan.towers:
        stair_plan.outside = outside
        if why:
            stair_plan.warnings.append(why)
    elif (not hug_no_stairs and not st.get("positions") and not st.get("count") and "count" not in st
          and not model.config.ladders
          and not model.stairs_elsewhere and model.scaffold_height_mm > MIN_HEIGHT_FOR_STAIRS_MM):
        # 階段室（連続スパン）が入らない小さい足場（2.6×2.4m 等、2026-10-24 実機で昇降設備 NG）。はしごを外周 60m
        # ごとに入れる（ブラケット足場と同じ）
        per = sum(float(e.scaffold_length) for e in model.plan.edges)
        model.config.ladders = max(1, math.ceil(per / (2.0 * DEFAULT_MAX_TRAVEL_MM)))
        model.auto_ladders = True
        # 階段室を置こうとして出た「置けない・昇降設備が無い」の文は、昇降口・はしごに替えたので外す
        stair_plan.warnings = []
        # くさびの本足場は、ハッチ付布板（梯子内蔵。日建 NDN6TA）で昇降口を作る（はしごを別に立てない。現場の定番）
        from .stairs import hatch_part, place_hatch_ladders

        model.hatch_ladders = place_hatch_ladders(model, model.config.ladders)
        if model.hatch_ladders:
            hp, _hw = hatch_part(model)
            model.plan.warnings.append(
                f"足場が小さく階段室（{tspans}スパン連続）が入らないので、昇降口はハッチ付布板（梯子内蔵 {hp.model_no}）"
                f"{len(model.hatch_ladders)}箇所にしました（各層。安衛則526条）。独立の階段を別に立てる場合は stairs で位置を指定してください")
        else:
            model.plan.warnings.append(
                f"足場が小さく階段室（{tspans}スパン連続）が入らないので、昇降ははしご {model.config.ladders}箇所に"
                "しました（安衛則526条）。独立の階段を別に立てる場合は stairs で位置を指定してください")
    stair_issues = [] if (hug_no_stairs or (model.config.ladders and not stair_plan.towers)) else validate_stairs(
        model, stair_plan, st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM)
    )
    if hug_no_stairs:
        model.plan.warnings.append(
            f"{model.config.form_label}の作業床に階段は入らないので、階段は計上していません。"
            "昇降設備（はしご・昇降用の別の足場など）を別に用意し、箇所数を ladders に書いてください（安衛則526条）")
    # 一側足場の床（受けブラケット幅＝建地列間隔）に階段枠（幅420〜450）は収まらない。
    # 区間・数量は計上するが、その区間の組み方は別途要る（実機の一側棟で階段室が幅400の
    # 床の中に描かれていた）
    if model.config.scaffold_form == "一側足場" and getattr(stair_plan, "towers", None):
        stair_plan.warnings.append(
            f"一側足場の作業床（幅{model.post_row_spacing_mm}mm）には階段枠（幅420〜450mm）が収まりません。"
            f"階段室{len(stair_plan.towers)}箇所の区間は本足場（建地2列）で組むか、階段用ブラケットで"
            "受けてください（階段・階段まわりの手すりの数量と区間は計上済み。その区間の支柱・布材の追加は含んでいません）"
        )
    # 取付部・マスト控えの壁つなぎを格子と同じ一覧へ（図面・数量・検定が同じ本数になる。
    # 最適化で既に載っていれば何もしない）
    merge_attachment_ties(model, platforms, openings)
    # 取付部・マスト控えの壁つなぎも、開口部で抜いた支柱には付けられない／届かない位置には置かない
    model.plan.warnings.extend(relocate_ties_off_openings(model, openings))
    model.plan.warnings.extend(relocate_unreachable_ties(model, label="取付部の壁つなぎ"))
    conflicts = check_conflicts(
        model, openings, stair_plan=stair_plan, platforms=platforms, brackets=brackets
    )
    if clearances:
        from .site_boundary import boundary_issues

        conflicts += boundary_issues(model, clearances, stair_plan)
    # 法規チェックは階段配置と敷地の解を使う（昇降設備・ジャッキ繰出し）
    terrain = solve_post_feet(model, build_ground(spec))
    checks = run_all_checks(model, stair_plan=stair_plan, terrain=terrain)
    # 範囲を指定した部材の編集（外す・置換）。割付（スパン数・層数）が決まってから升目を読む
    if spec.get("member_edits"):
        from .member_edits import parse_member_edits

        model.member_edits, edit_errors = parse_member_edits(spec["member_edits"], model, resolve_face_name)
        model.plan.warnings.extend(f"部材編集を効かせられません: {m}" for m in edit_errors)
    if model.inner_corner_joins:
        from .member_edits import inner_corner_edits

        model.member_edits = list(model.member_edits or []) + inner_corner_edits(model)
    quantity = take_off(
        model, bracket_sections=brackets, stair_plan=stair_plan,
        platforms=platforms, openings=openings, terrain=terrain,
    )
    # 詳細図は開口部があれば梁枠の図を足す
    from .details import hoist_detail_specs, required_details

    detail_sheets = required_details(
        model, opening_detail_specs(openings), terrain=terrain,
        hoists=hoist_detail_specs(model, platforms),
    )
    structural = run_structural(
        model, quantity, site, platforms=platforms, terrain=terrain,
        bracket_sections=brackets, openings=openings,
    )

    s = summary(checks)
    warnings = collect_warnings(
        structural, model, bracket_issues, stair_plan, stair_issues,
        openings, terrain, platforms, checks, quantity, conflicts,
    )
    verdict = build_verdict(
        s, structural, platforms, openings, bracket_issues, warnings, conflicts
    )
    return PlanRun(
        spec=spec, model=model, site=site, tie_opt=tie_opt, brackets=brackets,
        bracket_issues=bracket_issues, stair_plan=stair_plan,
        stair_issues=stair_issues, platforms=platforms, openings=openings,
        conflicts=conflicts, terrain=terrain, checks=checks, quantity=quantity, structural=structural,
        detail_sheets=detail_sheets, warnings=warnings, verdict=verdict,
    )


# ファイル名に使えない文字（Windows/macOSの制約の和集合）
_BAD_NAME_CHARS = '/\\:*?"<>|'
MAX_NAME_LEN = 80


def safe_file_stem(name: str) -> str:
    """工事名をファイル名に使える形にする.

    工事名はそのままファイル名の頭に付く。"A/B工区" のような名前が来ると、
    スラッシュがディレクトリ区切りとして扱われて書き出しに失敗する
    （実際 FileNotFoundError で落ちていた）。Windowsで使えない文字や
    前後の空白・ドットも落として、長すぎる名前は切り詰める。
    """
    out = []
    for ch in name.strip():
        out.append("_" if ch in _BAD_NAME_CHARS or ord(ch) < 32 else ch)
    stem = "".join(out).strip(" .")
    while "__" in stem:
        stem = stem.replace("__", "_")
    if len(stem) > MAX_NAME_LEN:
        stem = stem[:MAX_NAME_LEN].rstrip(" ._")
    return stem or "ashiba"


def write_outputs(r: PlanRun, out_dir: Path) -> None:
    """帳票一式を書き出す（CLIもツールバーも同じものを出す）."""
    (model, quantity, checks, structural, terrain, platforms, openings,
     brackets, stair_plan, verdict, warnings, spec) = (
        r.model, r.quantity, r.checks, r.structural, r.terrain, r.platforms,
        r.openings, r.brackets, r.stair_plan, r.verdict, r.warnings, r.spec)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = safe_file_stem(r.name)
    write_quantity_csv(quantity, out_dir / f"{name}_数量表.csv")
    # 層ごとの数量（1フロアごとに拾う。支柱は1本ずつ下端の層に）
    from .level_quantity import take_off_by_level
    from .report import write_level_quantity_csv

    write_level_quantity_csv(
        take_off_by_level(model, quantity, stories=spec.get("stories"), bracket_sections=brackets,
                          stair_plan=stair_plan, platforms=platforms, openings=openings, terrain=terrain),
        out_dir / f"{name}_層別数量.csv",
    )
    # 面ごとの数量（工区・面ごとに手配するとき用。参考: smartCON Planner の領域ごとの部品表）
    from .level_quantity import take_off_by_face
    from .report import write_face_quantity_csv

    write_face_quantity_csv(
        take_off_by_face(model, quantity, bracket_sections=brackets, stair_plan=stair_plan,
                         platforms=platforms, openings=openings, terrain=terrain),
        out_dir / f"{name}_面別数量.csv",
    )
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
        details=r.detail_sheets, terrain=terrain, verdict=verdict,
        warnings=warnings, stair_plan=stair_plan, platforms=platforms,
        openings=openings, bracket_sections=brackets,
    )


def _finite(value):
    """inf/nan を None に落とす（JSONに Infinity を書くと厳密なパーサで読めない）."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def result_dict(r: PlanRun, out_dir: Path) -> dict:
    """機械可読の実行結果（CLIの標準出力・受け入れテストが読む）."""
    (model, quantity, checks, structural, terrain, platforms, openings,
     brackets, stair_plan, verdict, warnings, tie_opt) = (
        r.model, r.quantity, r.checks, r.structural, r.terrain, r.platforms,
        r.openings, r.brackets, r.stair_plan, r.verdict, r.warnings, r.tie_opt)
    name = r.name
    s = summary(checks)
    renamed = []
    if r.file_stem != r.name:
        renamed.append(
            f"工事名にファイル名で使えない文字があるため、帳票のファイル名は"
            f"「{r.file_stem}」にしました"
        )
    return _finite({
        "project": name,
        "file_stem": r.file_stem,
        "posts_per_level": model.plan.total_posts,
        "levels": model.elevation.n_levels,
        "scaffold_height_mm": model.scaffold_height_mm,
        "verdict": verdict,
        "checks": s,
        "notification_required": notification_required(model, r.terrain),
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
             "kind": model.config.asagao.kind,
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
            # 階段0箇所だと inf。JSONに Infinity を書くと厳密なパーサで読めない
            "max_travel_m": (
                round(stair_plan.max_travel_mm / 1000.0, 1)
                if math.isfinite(stair_plan.max_travel_mm) else None
            ),
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
        "notes": (structural.notes + [f"敷地: {n}" for n in terrain.notes]
                  + renamed),
        "warnings": [w for _, _, w in warnings],
        "out_dir": str(out_dir),
    })


def load_spec(path: Path) -> dict:
    """入力JSONを読む。読めない理由は Python の例外ではなく日本語で返す.

    このツールはプログラマ以外も実行する。ファイルが無い・壊れている・
    文字コードが違うといった入口の失敗でトレースバックを出しても、
    何を直せばよいのか分からない。
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise InputError(f"入力ファイルが見つかりません: {path}") from None
    except IsADirectoryError:
        raise InputError(f"入力にディレクトリが指定されています: {path}") from None
    except OSError as e:
        raise InputError(f"入力ファイルを読めません: {path}（{e.strerror}）") from None

    if not raw.strip():
        raise InputError(f"入力ファイルが空です: {path}")
    try:
        # BOM付きUTF-8（Windowsのメモ帳など）もそのまま受ける
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        for enc in ("cp932", "euc_jp"):
            try:
                raw.decode(enc)
            except UnicodeDecodeError:
                continue
            raise InputError(
                f"入力ファイルの文字コードが {enc} のようです: {path}。"
                "UTF-8で保存し直してください"
            ) from None
        raise InputError(
            f"入力ファイルをUTF-8として読めません: {path}。"
            "UTF-8で保存し直してください"
        ) from None

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        line = text.splitlines()[e.lineno - 1] if 0 < e.lineno <= len(
            text.splitlines()) else ""
        raise InputError(
            f"JSONとして読めません: {path} の{e.lineno}行{e.colno}文字目付近"
            f"（{e.msg}）\n  該当行: {line.strip()[:80]}\n"
            "  よくある原因: 末尾の余分なカンマ、閉じ括弧の不足、"
            "コメント（JSONにコメントは書けません）"
        ) from None


def run(input_path: Path, out_dir: Path, master_csv: Path | None = None) -> dict:
    """入力JSON → 解く → 帳票一式 → 実行結果."""
    # 文字列で渡されることがある（スクリプトからの直接呼び出し）。
    # input_path だけ Path() していて out_dir はしていなかった
    out_dir = Path(out_dir)
    spec = load_spec(Path(input_path))
    groups = solve_groups(spec, Path(master_csv) if master_csv is not None else None)
    # 面ごとに足場を切り替えた組は「切替_種類」の下に帳票を出す
    for label, r in groups:
        write_outputs(r, out_dir / f"切替_{label}" if label else out_dir)
    label, r = groups[0]
    res = result_dict(r, out_dir / f"切替_{label}" if label else out_dir)
    if len(groups) > 1:
        res["face_groups"] = [{"form": lb or "（切り替えなし）", "faces": g.model.plan.face_names()} for lb, g in groups]
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="仮設足場 割付・法規チェック・数量拾い")
    ap.add_argument("input", type=Path, help="入力JSON")
    ap.add_argument("--out", type=Path, default=Path("out"), help="出力ディレクトリ")
    ap.add_argument("--master", type=Path, default=None, help="部材マスタCSV（省略時は同梱）")
    args = ap.parse_args(argv)
    try:
        result = run(args.input, args.out, args.master)
    except (InputError, MasterDataError, SeriesLockError, GdlCapacityError,
            ValidationError, CapacityError) as e:
        # 入力やマスタの誤りでスタックトレースを出しても直しようがない
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
