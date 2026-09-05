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
  "next_gen": false,               // 次世代足場（踏板幅が広い規格）
  "guard_rail_type": "布材",        // "布材"（＋中桟）／"先行手すり"
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
from .law_check import required_asagao_stages, run_all_checks, summary
from .master import MasterDataError, SeriesLockError, load_master
from .model import (
    ASAGAO_KIND_ASAGAO, ASAGAO_KIND_SAFE_WING, ASAGAO_KINDS, SAFE_WING_ANGLE_DEG, SAFE_WING_PROJECTION_MM,
    GUARD_RAIL_ADVANCE,
    FRAME_GUARD_RAIL_HEIGHT_MM,
    GUARD_RAIL_LEDGER,
    AsagaoSpec,
    ScaffoldConfig,
    ScaffoldModel,
)
from .openings import Opening, opening_detail_specs, opening_ranges, validate_openings
from .conflicts import check_conflicts
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
from .platforms import Hoist, LoadingStage, validate_platforms
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


class InputError(ValueError):
    """入力JSONの誤り（綴り違い・型違い・矛盾）をまとめて知らせる."""


# 受け付けるキー。ここに無いキーは綴り違いとして弾く。
# 黙って無視すると「指定したのに効かない」まま図面と計算が進んでしまう
# （loading_stage と書けばステージが消え、計算にも数量にも現れない）
TOP_KEYS = {
    "project_name", "series_id", "outline_mm", "eaves_height_mm", "guard_extra_mm",
    "building_height_mm", "period_days", "standoff", "deck_widths",
    "clearance_space_mm", "scaffold_form", "next_gen",
    "guard_rail_type", "post_reinforcement", "openings", "asagao", "bracket_sections", "loading_stages",
    "hoists", "ground_points_mm", "site", "notification", "stairs",
}
NESTED_KEYS = {
    "standoff": {"target", "min", "max", "hard_min"},
    "asagao": {"stages", "projection_mm", "angle_deg", "tie_every_spans", "kind"},
    "site": {"region", "v0_ms", "roughness", "sheet_type", "adjacent_factor",
             "region_factor", "gamma", "correction_f",
             "simultaneous_loaded_levels"},
    "notification": {"business_type", "site_name", "site_address", "worker_count",
                     "planner_name", "planner_career", "start_date", "contractor",
                     "labor_office"},
    "stairs": {"count", "tower_spans", "max_travel_mm", "min_per_face",
               "positions"},
}
LIST_ITEM_KEYS = {
    "openings": ({"edge_index", "start_mm", "beam_span_mm", "level", "reason"},
                 {"edge_index", "start_mm", "beam_span_mm"}),
    "bracket_sections": (
        {"edge_index", "start_mm", "end_mm", "direction", "width", "deck_width",
         "levels", "has_hozue", "is_widening", "on_kessokubu", "reason"},
        {"edge_index", "start_mm", "end_mm"},
    ),
    "loading_stages": (
        {"edge_index", "start_mm", "span_count", "projection_mm", "load_kn",
         "levels", "has_guard_rail", "has_toe_board", "has_load_sign",
         "has_hozue", "note"},
        {"edge_index", "start_mm"},
    ),
    "hoists": ({"edge_index", "position_mm", "reach_height_mm", "tie_every_mm",
                "landing_levels", "note"},
               {"edge_index", "position_mm"}),
}
STAIR_POSITION_KEYS = {"edge_index", "start_mm", "span_count", "reason"}


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
    "hoists": ("edge_index", "position_mm", "reach_height_mm", "tie_every_mm"),
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
    for k in sorted(set(obj) - allowed):
        if k in RENAMED:
            errors.append(f"{where}: \"{k}\" は廃止しました → {RENAMED[k]} を使ってください")
            continue
        near = [a for a in allowed if a.startswith(k[:4])]
        hint = f"（{'・'.join(sorted(near))} の綴り違い？）" if near else ""
        errors.append(f"{where}: 未知のキー \"{k}\"{hint}")
    for k in sorted(required - set(obj)):
        errors.append(f"{where}: \"{k}\" が要ります")


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


def check_edge_indices(spec: dict, model) -> None:
    """辺番号つきの付帯設備が、割付後に存在する辺を指しているか.

    存在しない辺の階段は「辺9は存在しません」の警告だけで落ちて、階段が無い計画が
    黙って出ていた。開口部・ステージ・昇降機・ブラケット区間も同じ入口で止める。
    """
    valid = sorted(e.edge_index for e in model.plan.edges)
    errors: list[str] = []
    items: list[tuple[str, list]] = [
        (key, spec.get(key) or []) for key in ("openings", "loading_stages", "hoists", "bracket_sections")
    ]
    items.append(("stairs.positions", (spec.get("stairs") or {}).get("positions") or []))
    for key, lst in items:
        if not isinstance(lst, list):
            continue
        for i, item in enumerate(lst):
            if not isinstance(item, dict):
                continue
            ei = item.get("edge_index")
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
                "period_days", "clearance_space_mm"):
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
        hard, mn = so.get("hard_min", 200), so.get("min", 250)
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
    if form is not None and form not in ("本足場", "一側足場"):
        errors.append(f"scaffold_form: 本足場 か 一側足場 です（{form!r}）")
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
    # 手すり分の既定は系列から。枠組はコマピッチを持たない（0）ので、
    # 2×コマピッチだと軒高そのままになり、最上層に手すりが立たない
    guard_extra = spec.get("guard_extra_mm")
    if guard_extra is None:
        guard_extra = (
            FRAME_GUARD_RAIL_HEIGHT_MM if master.is_frame
            else 2 * master.koma_pitch
        )
    required = int(spec["eaves_height_mm"]) + int(guard_extra)
    elevation = solve_elevation(required, master=master)
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
    config = ScaffoldConfig(
        scaffold_form=spec.get("scaffold_form", "本足場"),
        # 未指定なら系列の既定（A:400/250、B:405/240、次世代:500）を使う
        deck_widths=(tuple(spec["deck_widths"]) if spec.get("deck_widths") else None),
        next_gen=spec.get("next_gen", False),
        guard_rail_type=spec.get("guard_rail_type", GUARD_RAIL_LEDGER),
        post_reinforcement=spec.get("post_reinforcement", ""),
        period_days=spec.get("period_days", 60),
        asagao=build_asagao(spec, elevation.total_height, master),
    )
    return ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elevation,
        config=config,
        building_height_mm=float(spec.get("building_height_mm", 0)),
        clearance_space_mm=float(spec.get("clearance_space_mm", 2000)),
    )


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
            projection_mm=a.get("projection_mm", float(wing.nominal_dim) if wing else SAFE_WING_PROJECTION_MM),
            angle_deg=a.get("angle_deg", SAFE_WING_ANGLE_DEG),
            tie_every_spans=a.get("tie_every_spans", 2),
        )
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
            landing_levels=[int(v) for v in h.get("landing_levels", [])],
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
    openings, terrain, platforms, checks=None, quantity=None, conflicts=None,
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
    # 配置時の警告（何箇所要るかまで書いてある）と検証の警告が同じ移動距離超過を
    # 二重に挙げていた。配置側にあれば検証側は重ねない
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


def solve_all(spec: dict, master_csv: Path | None = None) -> PlanRun:
    """入力仕様を解く（ファイル出力・Archicad配置は呼び側の仕事）."""
    validate_spec(spec)
    model = build_model(spec, master_csv)
    check_edge_indices(spec, model)
    site = build_site(spec)
    # 開口部を先に解く（壁つなぎの最適化は抜いた支柱を避けた状態で検定する。
    # 階段の自動配置も梁枠の区間（通路）を避ける）
    openings = validate_openings(model, build_openings(spec))
    # 壁つなぎは風荷重の検定から逆算して確定させる（数量・法規チェックに反映するため先に実行）
    # 取付部（朝顔・ステージ）の壁つなぎも最適化の検定に載せるため、付帯設備を先に解く
    platforms = validate_platforms(model, *build_platforms(spec))
    tie_opt = optimize_wall_ties(model, site, openings=openings, platforms=platforms)
    model.plan.warnings.extend(tie_opt.notes)
    brackets = build_brackets(spec)
    bracket_issues = validate_bracket_sections(model, brackets)
    # 枠組の手すりは建枠一体。先行手すり工法の指定は効かないので、黙って無視しない
    if model.master.is_frame and spec.get("guard_rail_type") == GUARD_RAIL_ADVANCE:
        model.plan.warnings.append(
            "枠組足場では先行手すり工法（guard_rail_type）は適用されません。手すりは建枠一体で、"
            "最上層のみ布材で手すり・中桟を組みます。指定は無視しました"
        )
    # 外形を整理した（反転・重複除去・渡し）うえで辺番号つきの付帯設備があるなら、
    # その番号が入力の頂点順と一致しない可能性を先に言う
    edge_keys = [k for k in ("openings", "loading_stages", "hoists", "bracket_sections")
                 if spec.get(k)]
    if spec.get("stairs", {}).get("positions"):
        edge_keys.append("stairs.positions")
    if edge_keys and model.plan.outline.notes:
        model.plan.warnings.append(
            "外形を整理したため（" + "／".join(n.split("。")[0] for n in model.plan.outline.notes)
            + "）、辺番号が入力の頂点順とずれている可能性があります。"
            + "・".join(edge_keys) + " の edge_index は、平面割付表の辺・面名・躯体頂点で"
            "指定した面に当たっているか確認してください"
        )
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
            # stairs.count が無ければ n_stairs を使う。どちらも書かなければ
            # 移動距離から自動算出（n_stairs は既定値1なので、明示時だけ効かせる）
            count=st.get("count"),
            min_per_face=st.get("min_per_face", 0),
            avoid=opening_ranges(openings),
        )
    stair_issues = validate_stairs(
        model, stair_plan, st.get("max_travel_mm", DEFAULT_MAX_TRAVEL_MM)
    )
    # 取付部・マスト控えの壁つなぎを格子と同じ一覧へ（図面・数量・検定が同じ本数になる。
    # 最適化で既に載っていれば何もしない）
    merge_attachment_ties(model, platforms)
    # 取付部・マスト控えの壁つなぎも、開口部で抜いた支柱には付けられない／届かない位置には置かない
    model.plan.warnings.extend(relocate_ties_off_openings(model, openings))
    model.plan.warnings.extend(relocate_unreachable_ties(model, label="取付部の壁つなぎ"))
    conflicts = check_conflicts(
        model, openings, stair_plan=stair_plan, platforms=platforms, brackets=brackets
    )
    # 法規チェックは階段配置と敷地の解を使う（昇降設備・ジャッキ繰出し）
    terrain = solve_post_feet(model, build_ground(spec))
    checks = run_all_checks(model, stair_plan=stair_plan, terrain=terrain)
    quantity = take_off(
        model, bracket_sections=brackets, stair_plan=stair_plan,
        platforms=platforms, openings=openings, terrain=terrain,
    )
    # 詳細図は開口部があれば梁枠の図を足す
    from .details import required_details

    detail_sheets = required_details(
        model, opening_detail_specs(openings), terrain=terrain
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
    r = solve_all(spec, Path(master_csv) if master_csv is not None else None)
    write_outputs(r, out_dir)
    return result_dict(r, out_dir)


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
