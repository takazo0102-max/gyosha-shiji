"""足場の条件の窓（配置・条件のボタン）の項目と、選んだ値を入力に入れる決め.

利用者の指定（2026-10-24）「配置の時 足場の種類選べるようにして。条件の部分がどうやるのかわからない」。
足場条件の部品の設定ダイアログ（⌘T）を探さなくても、配置・条件のボタンで窓が前に出て、足場の種類・系列・幅・
手すり・幅木・層間ネット・階段・養生・高さ・立面断面を選べる。選んだ値は足場条件の部品に書く（次からはその値が出る）。
朝顔は窓に出さない（利用者の指定 2026-10-24: 条件のところに朝顔入れないで）。段数は高さで自動、付ける面はパレットの「朝顔の面」。
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
INNER = {"付ける（手すり＋中桟）": True, "付けない": False}
ONOFF = {"付ける": True, "付けない": False}
NET = {"張らない": False, "張る": True}
NET_AUTO = "自動（幅木ありは2層毎・なしは全層）"
STAIRS = {"自動（幅900以上は足場の中）": "自動", "足場の中": "足場の中", "外付け": "外付け"}
SHEETS = ("メッシュシート", "防音シート", "密閉シート", "防音パネル")
ELEV = {"作る": "section", "作らない（平面・3Dだけ・速い）": "none"}

# 窓で変える足場条件の部品の項目（ここに無い項目は部品のまま）
FORM_GDL_KEYS = ("projName", "moduleKind", "seriesId", "scaffForm", "bracketPost", "scaffW", "railType", "innerRail",
                 "toeBoard", "netLevels", "netBrackets",
                 "stairLayout", "sheetType", "hoardH", "eavesH", "hFromSlab", "elevMode")


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


def _net_levels_text(spec: dict) -> str:
    v = spec.get("horizontal_net_levels")
    if not v:
        return NET_AUTO
    if isinstance(v, str):
        return NET_AUTO if v.startswith("自動") else v
    return ",".join(str(i) for i in v)


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
        {"key": "rail", "label": "外側の手すり", "kind": "choice", "options": list(RAILS),
         "value": _key(RAILS, spec.get("guard_rail_type") or "布材", "布材（手すり＋中桟＋幅木）")},
        {"key": "inner", "label": "内側（躯体側）の手すり", "kind": "choice", "options": list(INNER),
         "value": _key(INNER, bool(spec.get("inner_guard_rail", True)), "付ける（手すり＋中桟）"),
         "help": "躯体と作業床の間が 300 を超えるところの墜落防止。躯体に近く要らなければ付けない"},
        {"key": "toe", "label": "幅木", "kind": "choice", "options": list(ONOFF),
         "value": _key(ONOFF, spec.get("toe_board", True) is not False, "付ける"),
         "help": "作業床の外側の幅木（先行手すりのときは付けない）。付けないときは落下物防止をメッシュシート等で"},
        {"key": "net", "label": "層間ネット", "kind": "choice", "options": list(NET),
         "value": "張る" if spec.get("horizontal_net_levels") else "張らない",
         "help": "躯体と足場の隙間に張る水平ネット"},
        {"key": "net_levels", "label": "ネットを張る層", "kind": "text", "value": _net_levels_text(spec),
         "help": "自動（幅木ありは2層毎・なしは全層）・全部・2,4,6 のように作業層の番号（1＝最下段。自動・全部は1段目を除く）"},
        {"key": "net_bk", "label": "ネットブラケット", "kind": "choice", "options": list(ONOFF),
         "value": _key(ONOFF, spec.get("net_brackets", True) is not False, "付ける"),
         "help": "層間ネットを内側建地ごとのネットブラケット（NL500）で受ける。付けないときは取付け金具を別途"},
        {"key": "stairs", "label": "階段の付け方", "kind": "choice", "options": list(STAIRS),
         "value": _key(STAIRS, (spec.get("stairs") or {}).get("layout") or "自動", "自動（幅900以上は足場の中）")},
        {"key": "sheet", "label": "養生", "kind": "choice", "options": list(SHEETS),
         "value": str((spec.get("site") or {}).get("sheet_type") or "メッシュシート")},
        {"key": "hoarding", "label": "仮囲いの高さ", "kind": "number",
         "value": f"{float(spec.get('hoarding_height_mm', 3000) or 0):.0f}",
         "help": "mm（外部シートはこの上から。0＝地面から）"},
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
    if str(values.get("hoarding") or "").strip():
        try:
            out["hoarding_height_mm"] = max(0, int(round(float(str(values["hoarding"]).replace(",", "")))))
        except ValueError:
            notes.append(f"仮囲いの高さ「{values.get('hoarding')}」は数字ではないので前のままにします")
    if values.get("toe") in ONOFF:
        out["toe_board"] = ONOFF[values["toe"]]
    if values.get("net") in NET:
        if NET[values["net"]]:
            lv = str(values.get("net_levels") or "").strip() or NET_AUTO
            out["horizontal_net_levels"] = ("全部" if lv in ("全部", "全層", "すべて", "全て")
                                            else "自動" if lv.startswith("自動") else lv)
        else:
            out.pop("horizontal_net_levels", None)
    if values.get("net_bk") in ONOFF:
        out["net_brackets"] = ONOFF[values["net_bk"]]
    if values.get("inner") in INNER:
        out["inner_guard_rail"] = INNER[values["inner"]]
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


ASAGAO_MODES = ("朝顔を付ける", "朝顔を外す", "全部の面に付ける")
ASAGAO_ALL = "全部"


def asagao_on_map(current: str, all_faces: list[str], lengths: dict | None = None) -> dict[str, list]:
    """朝顔を付ける面（asagaoFaces の文字）→ {面: [(始め, 終わり)]}（面全体は [(0, 面の長さ)]）.

    Archicad の配置では空＝付けない（配置で勝手に付けない。利用者の指定 2026-10-24）。「全部」で全部の面。
    lengths は面の長さ mm（無い面は ∞ とみなす）。
    """
    from .cli import parse_asagao_faces
    from .face_forms import split_key

    lengths = lengths or {}
    full = lambda f: (0.0, float(lengths.get(f) or float("inf")))
    if str(current or "").strip() in ("全部", "全て", "すべて", "全面", "全部の面"):
        return {f: [full(f)] for f in all_faces}
    on: dict[str, list] = {}
    for t in parse_asagao_faces(current):
        f, a, b = split_key(t)
        if f not in all_faces:
            continue
        on.setdefault(f, []).append(full(f) if a is None else (a, b))
    return {f: _merge_ranges(rs) for f, rs in on.items()}


def _merge_ranges(rs: list) -> list:
    out: list = []
    for a, b in sorted(rs):
        if out and a <= out[-1][1] + 1.0:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        elif b > a + 1.0:
            out.append((a, b))
    return out


def _minus(rs: list, a: float, b: float) -> list:
    out = []
    for x, y in rs:
        if y <= a + 1.0 or x >= b - 1.0:
            out.append((x, y))
            continue
        if x < a - 1.0:
            out.append((x, a))
        if y > b + 1.0:
            out.append((b, y))
    return out


def asagao_faces_text(on: dict[str, list], all_faces: list[str], lengths: dict | None = None) -> str:
    """{面: 区間} → asagaoFaces の文字（全部の面に全長なら「全部」、どこにも無ければ「なし」）."""
    from .face_forms import range_key

    lengths = lengths or {}
    toks = []
    whole = 0
    for f in all_faces:
        rs = _merge_ranges(on.get(f) or [])
        if not rs:
            continue
        ln = float(lengths.get(f) or float("inf"))
        if len(rs) == 1 and rs[0][0] < 1.0 and rs[0][1] >= ln - 1.0:
            toks.append(f)
            whole += 1
        else:
            toks += [range_key(f, a, min(b, ln) if min(b, ln) < float("inf") else 9999999.0) for a, b in rs]
    if whole == len(all_faces) and len(toks) == whole:
        return ASAGAO_ALL
    return "・".join(toks) if toks else "なし"


def updated_asagao_faces(current: str, all_faces: list[str], picked: list[str], mode: str,
                         lengths: dict | None = None) -> str:
    """朝顔を付ける面（足場条件の部品の asagaoFaces）に、選んだ面・区間（「南面[a-b]」）を付ける・外した結果.

    利用者の指定（2026-10-24）「朝顔あとで必要箇所を選べるようにしたい」「配置で朝顔が勝手に配置される。なしして線で
    朝顔の範囲追加できるようにして」。空＝付けない、「全部」＝全部の面、どこにも無ければ「なし」。lengths（面の長さ mm）が
    あれば、面全体に付いた面から区間を外せる・区間が面の全長になれば面の名前にまとめる。
    """
    from .face_forms import split_key

    lengths = lengths or {}
    on = asagao_on_map(current, all_faces, lengths)
    if mode == ASAGAO_MODES[2]:
        return ASAGAO_ALL
    for key in picked:
        f, a, b = split_key(key)
        if f not in all_faces:
            continue
        if a is None:
            a, b = 0.0, float(lengths.get(f) or float("inf"))
        if mode == ASAGAO_MODES[1]:
            rs = _minus(on.get(f) or [], a, b)
            if rs:
                on[f] = rs
            else:
                on.pop(f, None)
        else:
            on[f] = _merge_ranges((on.get(f) or []) + [(a, b)])
    return asagao_faces_text(on, all_faces, lengths)
