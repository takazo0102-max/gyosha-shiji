"""足場の条件の窓（配置・条件のボタン）の項目と、選んだ値を入力に入れる決め.

利用者の指定（2026-10-24）「配置の時 足場の種類選べるようにして。条件の部分がどうやるのかわからない」。
足場条件の部品の設定ダイアログ（⌘T）を探さなくても、配置・条件のボタンで窓が前に出て、足場の種類・系列・幅・
手すり・階段・朝顔・養生・高さ・立面断面を選べる。選んだ値は足場条件の部品に書く（次からはその値が出る）。
窓は tapir/spec_form.swift（scripts/form_dialog.py が開く）。ここは窓に依らない部分（試験できる）。
"""

from __future__ import annotations

from typing import Optional

from .face_forms import FACE_FORM_SPECS
from .widths import WIDTH_CHOICES, WidthChoice, _module_of

# 足場の種類（面の切替と同じ名前。「本足場（狭い幅）」は敷地境界に合わせるときにツールが選ぶので出さない）
KINDS = ("本足場", "ブラケット足場（支柱）", "ブラケット足場（単管）", "一側足場", "単管抱き足場", "単管本足場", "枠組足場")
SERIES_AUTO = "自動（幅に合わせる）"
WIDTH_DEFAULT = "系列の既定"
RAILS = {"布材（手すり＋中桟＋幅木）": "布材", "先行手すり": "先行手すり"}
STAIRS = {"自動（幅900以上は足場の中）": "自動", "足場の中": "中", "外付け": "外付け"}
ASAGAO = ("自動（高さで決める）", "1段", "2段", "3段")
SHEETS = ("メッシュシート", "防音シート", "密閉シート")
ELEV = {"作る": "section", "作らない（平面・3Dだけ・速い）": "none"}

# 窓で変える足場条件の部品の項目（ここに無い項目は部品のまま）
FORM_GDL_KEYS = ("projName", "moduleKind", "seriesId", "scaffForm", "bracketPost", "scaffW", "railType",
                 "stairLayout", "asagaoStages", "sheetType", "eavesH", "hFromSlab", "elevMode")


def _series_labels() -> dict[str, str]:
    from .master import SERIES_LABELS

    return {sid: lab for sid, lab in SERIES_LABELS.items() if sid not in ("waku", "tankan")}


def current_kind(spec: dict) -> str:
    sid = str(spec.get("series_id") or "")
    form = str(spec.get("scaffold_form") or "本足場")
    if sid == "waku":
        return "枠組足場"
    if form == "ブラケット足場":
        return f"ブラケット足場（{spec.get('bracket_post') or '支柱'}）"
    if form in ("単管抱き足場", "抱き足場"):
        return "単管抱き足場"
    if form == "一側足場":
        return "一側足場"
    if sid == "tankan":
        return "単管本足場"
    return "本足場"


def _key(d: dict, value, default: str) -> str:
    return next((k for k, v in d.items() if v == value), default)


def current_width(spec: dict) -> str:
    w = spec.get("scaffold_width_mm")
    if not w:
        return WIDTH_DEFAULT
    mod = _module_of(spec)
    cands = [c for c in WIDTH_CHOICES if c.module == mod] or list(WIDTH_CHOICES)
    return min(cands, key=lambda c: abs(c.width_mm - float(w))).label


def form_fields(spec: dict) -> list[dict]:
    """窓の項目（いまの条件の値を入れて）."""
    labels = _series_labels()
    sid = str(spec.get("series_id") or "")
    stages = int(((spec.get("asagao") or {}).get("stages")) or 0)
    eaves = spec.get("eaves_height_mm")
    return [
        {"key": "", "label": "足場", "kind": "section"},
        {"key": "project_name", "label": "工事名", "kind": "text", "value": str(spec.get("project_name") or "")},
        {"key": "kind", "label": "足場の種類", "kind": "choice", "options": list(KINDS), "value": current_kind(spec),
         "help": "本足場（建地2列）・ブラケット足場（狭いところ）・一側足場・単管抱き足場・単管本足場・枠組足場"},
        {"key": "series", "label": "メーカー・系列", "kind": "choice", "options": [SERIES_AUTO] + list(labels.values()),
         "value": labels.get(sid, SERIES_AUTO),
         "help": "単管・枠組は足場の種類で決まります。自動は幅（センチ／インチ）に合う既定の系列"},
        {"key": "width", "label": "足場の幅", "kind": "choice", "options": [WIDTH_DEFAULT] + [c.label for c in WIDTH_CHOICES],
         "value": current_width(spec), "help": "建地列の間隔。階段を足場の中に入れるなら 900 以上"},
        {"key": "", "label": "安全・設備", "kind": "section"},
        {"key": "rail", "label": "手すり", "kind": "choice", "options": list(RAILS),
         "value": _key(RAILS, spec.get("guard_rail_type") or "布材", "布材（手すり＋中桟＋幅木）")},
        {"key": "stairs", "label": "階段の付け方", "kind": "choice", "options": list(STAIRS),
         "value": _key(STAIRS, (spec.get("stairs") or {}).get("layout") or "自動", "自動（幅900以上は足場の中）")},
        {"key": "asagao", "label": "朝顔", "kind": "choice", "options": list(ASAGAO),
         "value": f"{stages}段" if stages in (1, 2, 3) else ASAGAO[0]},
        {"key": "sheet", "label": "養生", "kind": "choice", "options": list(SHEETS),
         "value": str((spec.get("site") or {}).get("sheet_type") or "メッシュシート")},
        {"key": "", "label": "高さ・図面", "kind": "section"},
        {"key": "eaves", "label": "軒高", "kind": "number", "value": "" if eaves is None else f"{float(eaves):.0f}",
         "help": "mm（スラブから決めるときは使わない）"},
        {"key": "from_slabs", "label": "高さ", "kind": "check", "value": "1" if spec.get("height_from_slabs", True) else "0",
         "help": "建物のスラブの天端から面ごとに決める"},
        {"key": "elev", "label": "立面・断面", "kind": "choice", "options": list(ELEV),
         "value": _key(ELEV, spec.get("elevation_mode") or "section", "作る")},
    ]


def _width_in(choice: WidthChoice, module: str) -> WidthChoice:
    if choice.module == module:
        return choice
    same = [c for c in WIDTH_CHOICES if c.module == module]
    return min(same, key=lambda c: abs(c.width_mm - choice.width_mm)) if same else choice


def apply_form(spec: dict, values: dict) -> tuple[dict, list[str]]:
    """窓で選んだ値 → (新しい入力, 変えたことの説明)."""
    from .master import series_module
    from .widths import apply_width_choice

    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in spec.items()}
    notes: list[str] = []
    name = str(values.get("project_name") or "").strip()
    if name:
        out["project_name"] = name
    kind = values.get("kind") or current_kind(spec)
    if kind in FACE_FORM_SPECS:
        k = FACE_FORM_SPECS[kind]
        out["scaffold_form"] = k["scaffold_form"]
        if "bracket_post" in k:
            out["bracket_post"] = k["bracket_post"]
        if "series_id" in k:
            out["series_id"] = k["series_id"]
        elif str(out.get("series_id") or "") in ("waku", "tankan"):
            out.pop("series_id", None)
    fixed = str(out.get("series_id") or "") in ("waku", "tankan")
    series = values.get("series") or SERIES_AUTO
    if not fixed:
        sid = next((s for s, lab in _series_labels().items() if lab == series), None)
        if sid:
            out["series_id"] = sid
            out["module"] = series_module(sid)
        else:
            out.pop("series_id", None)
    width = values.get("width") or WIDTH_DEFAULT
    choice: Optional[WidthChoice] = next((c for c in WIDTH_CHOICES if c.label == width), None)
    if choice is None:
        out.pop("scaffold_width_mm", None)
    else:
        if out.get("series_id") and not fixed:
            mod = series_module(str(out["series_id"]))
            fit = _width_in(choice, mod)
            if fit is not choice:
                notes.append(f"幅 {choice.label} は系列に無いので {fit.label} にします")
                choice = fit
        out, wn = apply_width_choice(out, choice)
        notes += wn
    out["guard_rail_type"] = RAILS.get(values.get("rail") or "", out.get("guard_rail_type") or "布材")
    out["stairs"] = {**(out.get("stairs") or {}), "layout": STAIRS.get(values.get("stairs") or "", "自動")}
    st = values.get("asagao") or ASAGAO[0]
    asg = dict(out.get("asagao") or {})
    if st in ASAGAO[1:]:
        asg["stages"] = int(st[0])
    else:
        asg.pop("stages", None)
    if asg:
        out["asagao"] = asg
    else:
        out.pop("asagao", None)
    if values.get("sheet") in SHEETS:
        out["site"] = {**(out.get("site") or {}), "sheet_type": values["sheet"]}
    try:
        e = float(str(values.get("eaves") or "").replace(",", ""))
        if e > 0:
            out["eaves_height_mm"] = int(round(e))
    except ValueError:
        notes.append(f"軒高「{values.get('eaves')}」は数字ではないので前のままにします")
    if "from_slabs" in values:
        out["height_from_slabs"] = str(values["from_slabs"]) in ("1", "true")
    out["elevation_mode"] = ELEV.get(values.get("elev") or "", out.get("elevation_mode") or "section")
    notes.insert(0, f"足場の種類 {kind}")
    return out, notes


def object_params(spec: dict) -> dict:
    """足場条件の部品に書く値（窓で変える項目だけ）."""
    from .spec_object import params_from_spec

    p = params_from_spec(spec)
    return {k: p[k] for k in FORM_GDL_KEYS if k in p}


def form_spec(spec: dict, title: str, intro: str, buttons: list[tuple[str, str]]) -> dict:
    """窓に渡す JSON（tapir/spec_form.swift の Form）."""
    return {"title": title, "intro": intro, "fields": form_fields(spec),
            "buttons": [{"id": i, "label": lab} for i, lab in buttons]}
