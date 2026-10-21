"""Archicad の中で条件を入力する部品「足場条件」（ashiba_spec）と、入力 JSON との対応.

ツールバーは、スラブの近くに置かれた足場条件部品のパラメータを読み、入力条件に重ねる
（デスクトップの JSON より優先）。部品が無ければ、今の条件を入れた部品を自動で置く。
利用者はその部品の設定ダイアログ（タブ: 基本／高さ・離れ／安全・表示）で条件を変えて、
もう一度ツールバーを実行するだけでよい。条件はプロジェクトに保存される。

開口部・ステージ・昇降機・スパン指定など、一覧で持つ条件は今までどおり JSON（または
平面のホットスポット編集と read_back_spans.py）で持つ。部品が持つのは一つの値で決まる条件だけ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

SPEC_OBJECT = "ashiba_spec"


@dataclass(frozen=True)
class Field:
    gdl: str            # GDL パラメータ名
    kind: str           # "str" / "len" / "int" / "bool" / "intlist"（部品は "2,5" の文字列、入力は [2, 5]）
    path: tuple         # 入力 JSON のキー（入れ子は複数）
    default: Any        # 部品の既定値（GDL の単位: 長さは m）
    zero_is_unset: bool = False   # 0（または空文字）なら入力に入れない


FIELDS: tuple[Field, ...] = (
    Field("projName", "str", ("project_name",), "足場計画"),
    # 条件の登録名（パレットの「登録」「呼び出し」で使う。計画には効かない。"_" で始まるキーは入力の検査で無視される）
    Field("presetName", "str", ("_preset",), "", zero_is_unset=True),
    Field("moduleKind", "str", ("module",), "metric"),
    Field("seriesId", "str", ("series_id",), "", zero_is_unset=True),
    Field("eavesH", "len", ("eaves_height_mm",), 15.4),
    Field("guardExtra", "len", ("guard_extra_mm",), 0.9),
    Field("scaffH", "len", ("scaffold_height_mm",), 0.0, zero_is_unset=True),
    Field("bldgH", "len", ("building_height_mm",), 16.0),
    Field("periodDays", "int", ("period_days",), 90),
    Field("soTarget", "len", ("standoff", "target"), 0.30),
    Field("soMin", "len", ("standoff", "min"), 0.25),
    Field("soMax", "len", ("standoff", "max"), 0.35),
    Field("soHardMin", "len", ("standoff", "hard_min"), 0.25),
    Field("scaffForm", "str", ("scaffold_form",), "本足場"),
    Field("bracketPost", "str", ("bracket_post",), "支柱"),
    Field("scaffW", "int", ("scaffold_width_mm",), 0, zero_is_unset=True),
    Field("railType", "str", ("guard_rail_type",), "布材"),
    Field("innerRail", "bool", ("inner_guard_rail",), True),
    Field("nextGen", "bool", ("next_gen",), False),
    Field("asagaoStages", "int", ("asagao", "stages"), 0, zero_is_unset=True),
    Field("region", "str", ("site", "region"), "関東(内陸)"),
    Field("roughness", "str", ("site", "roughness"), "III"),
    Field("sheetType", "str", ("site", "sheet_type"), "メッシュシート"),
    Field("siteName", "str", ("notification", "site_name"), "", zero_is_unset=True),
    Field("elevMode", "str", ("elevation_mode",), "section"),
    Field("lineMode3d", "bool", ("line_mode_3d",), False),
    Field("autoInBrk", "bool", ("auto_inner_bracket",), True),
    Field("stairLayout", "str", ("stairs", "layout"), "自動"),
    Field("facesOnly", "str", ("faces",), "", zero_is_unset=True),
    Field("netLevels", "intlist", ("horizontal_net_levels",), "", zero_is_unset=True),
    Field("hFromSlab", "bool", ("height_from_slabs",), True),
    # 範囲を指定した部材の編集。1行に「面 スパン 層 部材（→品番）」を ; 区切りで（255文字ずつ4欄）
    Field("memberEdit1", "edits", ("member_edits",), "", zero_is_unset=True),
    Field("memberEdit2", "edits", ("member_edits",), "", zero_is_unset=True),
    Field("memberEdit3", "edits", ("member_edits",), "", zero_is_unset=True),
    Field("memberEdit4", "edits", ("member_edits",), "", zero_is_unset=True),
)
EDIT_FIELDS = tuple(f.gdl for f in FIELDS if f.kind == "edits")
EDIT_FIELD_MAX = 250


def _get(spec: dict, path: tuple) -> Any:
    cur: Any = spec
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(spec: dict, path: tuple, value: Any) -> None:
    cur = spec
    for k in path[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[path[-1]] = value


def spec_from_params(params: dict) -> dict:
    """部品のパラメータ（読み戻し値）→ 入力 JSON の断片（長さは mm）.

    系列が空なら series_id を入れない（モジュールの既定系列になる）。0 を「未指定」とする
    項目（足場高さの直接指定・朝顔の段数・現場名）は 0／空なら入れない。
    """
    out: dict = {}
    for f in FIELDS:
        if f.gdl not in params:
            continue
        v = params[f.gdl]
        if f.kind == "len":
            try:
                v = round(float(v) * 1000.0, 1)
            except (TypeError, ValueError):
                continue
            if f.zero_is_unset and abs(v) < 0.5:
                continue
            v = int(v) if abs(v - round(v)) < 1e-6 else v
        elif f.kind == "int":
            try:
                v = int(round(float(v)))
            except (TypeError, ValueError):
                continue
            if f.zero_is_unset and v == 0:
                continue
        elif f.kind == "bool":
            v = bool(v) if not isinstance(v, str) else v.strip().lower() in ("1", "true", "yes", "on")
        elif f.kind == "intlist":
            v = parse_int_list(v)
            if f.zero_is_unset and not v:
                continue
        elif f.kind == "edits":
            from .member_edits import parse_edit_text

            # 部品に欄があれば部品が正（空にしたら編集を消したということ。JSON の編集を残さない）
            items, errs = parse_edit_text(v)
            for e in errs:
                out.setdefault("_edit_errors", []).append(f"{f.gdl}: {e}")
            out.setdefault("member_edits", []).extend(items)
            continue
        else:
            v = "" if v is None else str(v).strip()
            if f.zero_is_unset and v == "":
                continue
            if f.gdl == "seriesId":
                from .master import series_from_label

                v = series_from_label(v)
        _set(out, f.path, v)
    return out


def params_from_spec(spec: dict) -> dict:
    """入力 JSON（いまの条件）→ 部品のパラメータ（新しく置くときの初期値）.

    Tapir には Boolean を bool、Integer を int、Length を m の float で送る（型が違うと全パラメータが落ちる）。
    """
    out: dict = {}
    edit_lines = _edit_field_values(spec.get("member_edits"))
    for f in FIELDS:
        if f.kind == "edits":
            out[f.gdl] = edit_lines.pop(0) if edit_lines else ""
            continue
        v = _get(spec, f.path)
        if v is None:
            v = f.default
        elif f.kind == "len":
            v = float(v) / 1000.0
        if f.kind == "len":
            out[f.gdl] = float(v)
        elif f.kind == "int":
            out[f.gdl] = int(v)
        elif f.kind == "bool":
            out[f.gdl] = bool(v)
        elif f.kind == "intlist":
            out[f.gdl] = ",".join(str(i) for i in parse_int_list(v))
        elif f.gdl == "seriesId":
            from .master import SERIES_LABELS, series_from_label

            out[f.gdl] = SERIES_LABELS.get(series_from_label(v), str(v))
        else:
            out[f.gdl] = str(v)
    return out


def _edit_field_values(items) -> list[str]:
    """member_edits → 部品の4欄に詰めた文字列（1欄 EDIT_FIELD_MAX 文字まで。入りきらない分は落とさず止める）."""
    from .member_edits import format_edit_items

    fields: list[str] = []
    cur = ""
    for line in format_edit_items(items):
        nxt = f"{cur}; {line}" if cur else line
        if len(nxt) > EDIT_FIELD_MAX and cur:
            fields.append(cur)
            cur = line
        else:
            cur = nxt
    if cur:
        fields.append(cur)
    if len(fields) > len(EDIT_FIELDS):
        raise ValueError(f"部材編集が多すぎて足場条件の部品の{len(EDIT_FIELDS)}欄に入りません。入力 JSON の member_edits で持ってください")
    return fields


def parse_int_list(v) -> list[int]:
    """"2,5"・"2、5"・[2, 5] → [2, 5]（読めない語は飛ばす）."""
    if isinstance(v, (list, tuple)):
        items = v
    else:
        items = str(v or "").replace("、", ",").replace(" ", ",").split(",")
    out = []
    for t in items:
        try:
            out.append(int(round(float(str(t).strip()))))
        except (TypeError, ValueError):
            continue
    return out


def merge_object_into_spec(spec: dict, obj_spec: dict) -> dict:
    """部品の条件を入力に重ねる（部品が優先。入れ子は項目ごとに上書き）.

    部品の系列が空でモジュールだけ決まっているときは、JSON 側の series_id を外す
    （信和Aの既定に引きずられてインチの指定と食い違わないように）。
    """
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in spec.items()}
    for k, v in obj_spec.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    if "module" in obj_spec and "series_id" not in obj_spec:
        out.pop("series_id", None)
    return out


def _bbox(outline_mm) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in outline_mm]
    ys = [float(p[1]) for p in outline_mm]
    return min(xs), min(ys), max(xs), max(ys)


def spec_object_position(outline_mm) -> tuple[float, float]:
    """新しく置く足場条件部品の位置（mm）: 建物の左下から外側へ（断面の切断線より外）."""
    x0, y0, _x1, _y1 = _bbox(outline_mm)
    return x0, y0 - 9000.0


def pick_spec_object(objects: list[tuple[dict, tuple[float, float], dict]], outline_mm,
                     reach_mm: float = 25000.0) -> Optional[tuple[dict, dict]]:
    """(要素, 原点mm, パラメータ) の一覧から、この建物の足場条件部品を選ぶ.

    外形の外接矩形から reach 以内にあるもののうち、いちばん近いもの。隣の建物の部品は拾わない。
    """
    x0, y0, x1, y1 = _bbox(outline_mm)
    best = None
    for el, (ox, oy), params in objects:
        dx = max(x0 - ox, 0.0, ox - x1)
        dy = max(y0 - oy, 0.0, oy - y1)
        d = (dx * dx + dy * dy) ** 0.5
        if d <= reach_mm and (best is None or d < best[0]):
            best = (d, el, params)
    return (best[1], best[2]) if best else None


def upgrade_params(params: dict) -> tuple[dict, list[str]]:
    """古い版の足場条件部品の値 → 今の版に入れる値（無い項目は既定値）と、足した項目名.

    部品に項目を足すと、前に置いた部品（古い版）には新しい項目が無く、設定ダイアログにも出ない
    （2026-10-20: 「幅」「階段の付け方」が実機の部品に無かった）。値を引き継いで今の版に置き換える。
    """
    out: dict = {}
    added: list[str] = []
    for f in FIELDS:
        if f.gdl in params:
            out[f.gdl] = params[f.gdl]
        else:
            out[f.gdl] = f.default
            added.append(f.gdl)
    return out, added
