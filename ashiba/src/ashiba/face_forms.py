"""面ごと・面の組（ブロック）ごとに足場の種類を切り替える（利用者の指定 2026-10-22: 面ごとやブロックを違う足場に
切り替えれるようコマンド作って）.

入力の face_forms（{面名: 種類}、または「南面=ブラケット足場（単管）;東面=単管抱き足場」の文字列）で、指定した面だけ
別の種類で解く。配置（run_from_archicad）は面の組ごとに解いて足場ラインを置き、前回の配置の片付けは1回にまとめる。
隣の面を建てない端は開放端（妻側の手すり・幅木）になる（faces で一部の面だけ建てるときと同じ）。

面名は外形の辺の方位（南面・東面…。同じ方位が2つあれば「南面(辺2)」）で、系列に依らない。

面の一部（区間）だけ切り替えるときは「南面[10974-16461]=ブラケット足場（支柱）」と書く（利用者の指定 2026-10-24: 面の
切り替えはやめて選択した足場の変更に。区切った部品を選んで切り替える）。区間は元の割付の面の始点の支柱からの mm。
面は区間の切れ目で分かれ、それぞれの組が面全体を同じスパンで解いてから自分の区間だけ残す（_face_range）。切れ目は
開放端（妻側の手すり・幅木）。
"""

from __future__ import annotations

import re
from typing import Optional

# 切り替えられる足場の種類 → 入力に重ねる値。series_id を持つ種類は系列も替える（module は外す）
FACE_FORM_SPECS: dict[str, dict] = {
    "本足場": {"scaffold_form": "本足場"},
    # 系列でいちばん細い建地間隔の本足場（くさびは床を載せられる最小の腕木。日建 610・信和 600）。敷地境界に収める
    # とき、一側足場にする前に試す（利用者の指定 2026-10-24 の流れ: 1m 以上空くなら本足場が原則）
    "本足場（狭い幅）": {"scaffold_form": "本足場", "_narrow": True},
    "一側足場": {"scaffold_form": "一側足場"},
    "ブラケット足場（支柱）": {"scaffold_form": "ブラケット足場", "bracket_post": "支柱"},
    "ブラケット足場（単管）": {"scaffold_form": "ブラケット足場", "bracket_post": "単管"},
    "単管抱き足場": {"scaffold_form": "単管抱き足場"},
    "単管本足場": {"scaffold_form": "本足場", "series_id": "tankan"},
    "枠組足場": {"scaffold_form": "本足場", "series_id": "waku"},
}
FACE_FORMS = tuple(FACE_FORM_SPECS)
# 切り替えた組では使わない入力（スパン・部材の指定は元の種類の割付に対するもの）
_GROUP_DROP_KEYS = ("span_overrides", "member_edits", "face_forms", "form_standoff")


_RANGE = re.compile(r"^(.+?)\[\s*(-?\d+(?:\.\d+)?)\s*[-〜~]\s*(-?\d+(?:\.\d+)?)\s*\]$")


def _face_key(face: str) -> str:
    return face if face.endswith("面") or "(" in face else face + "面"


def split_key(key: str) -> tuple[str, Optional[float], Optional[float]]:
    """「南面[10974-16461]」→ ("南面", 10974, 16461)。区間が無ければ (面, None, None)."""
    m = _RANGE.match(str(key).strip())
    if not m:
        return _face_key(str(key).strip()), None, None
    a, b = float(m.group(2)), float(m.group(3))
    return _face_key(m.group(1).strip()), min(a, b), max(a, b)


def range_key(face: str, a: float, b: float) -> str:
    return f"{_face_key(face)}[{a:.0f}-{b:.0f}]"


def parse_face_forms(value) -> dict[str, str]:
    """face_forms の値 → {面名（区間つきなら「南面[a-b]」）: 種類}. 空なら {}。種類の綴りの違い（括弧の全角・半角）は揃える."""
    if not value:
        return {}
    if isinstance(value, dict):
        items = list(value.items())
    else:
        items = []
        for part in str(value).replace("；", ";").replace("\n", ";").split(";"):
            if not part.strip():
                continue
            if "=" not in part:
                raise ValueError(f"face_forms: 「面=種類」の形で書いてください（{part.strip()!r}）")
            k, v = part.split("=", 1)
            items.append((k, v))
    out: dict[str, str] = {}
    for k, v in items:
        face = str(k).strip()
        form = normalize_form(str(v))
        if not face:
            continue
        if form is None:
            raise ValueError(f"face_forms: 「{face}」の種類「{v}」は {'・'.join(FACE_FORMS)} のどれかです")
        f, a, b = split_key(face)
        out[f if a is None else range_key(f, a, b)] = form
    return out


def normalize_form(text: str) -> Optional[str]:
    t = text.strip().replace("(", "（").replace(")", "）").replace(" ", "")
    return t if t in FACE_FORM_SPECS else None


def format_face_forms(ff: dict[str, str]) -> str:
    """{面名: 種類} → 足場条件の部品に書く文字列（面の並びは入力のまま）."""
    return ";".join(f"{k}={v}" for k, v in ff.items())


def face_segments(ff: dict[str, str], face: str) -> list[tuple[float, Optional[float], str]]:
    """面の区間 [(始め, 終わり（None は面の終点）, 種類（"" は入力の種類）)]. 区間の指定が無ければ [(0, None, 面の種類)]."""
    base = ff.get(face, "")
    parts = sorted((a, b, form) for k, form in ff.items()
                   for f, a, b in [split_key(k)] if f == face and a is not None)
    if not parts:
        return [(0.0, None, base)]
    out = []
    cur = 0.0
    for a, b, form in parts:
        if a > cur + 1.0:
            out.append((cur, a, base))
        out.append((max(a, cur), b, form))
        cur = max(cur, b)
    out.append((cur, None, base))
    return [seg for seg in out if seg[1] is None or seg[1] - seg[0] > 1.0]


_SHIFT_ITEMS = (("openings", "start_mm"), ("loading_stages", "start_mm"), ("hoists", "position_mm"))


def _shift_items(sub: dict, face: str, face_names: list[str], a: float, b: Optional[float]) -> None:
    """区間だけ残す面の付帯設備（開口・ステージ・昇降機・階段の位置）を区間の始点からの位置に直し、区間の外は外す."""
    def mine(item) -> bool:
        if item.get("face") is not None:
            return _face_key(str(item["face"]).strip()) == face
        ei = item.get("edge_index")
        return ei is not None and 0 <= int(ei) < len(face_names) and face_names[int(ei)] == face

    def moved(items, key):
        out = []
        for it in items or []:
            if not mine(it):
                out.append(it)
                continue
            x = float(it.get(key, 0.0))
            if x >= a - 1.0 and (b is None or x < b - 1.0):
                out.append({**it, key: x - a})
        return out

    for k, key in _SHIFT_ITEMS:
        if sub.get(k):
            sub[k] = moved(sub[k], key)
    st = sub.get("stairs")
    if isinstance(st, dict) and st.get("positions"):
        sub["stairs"] = {**st, "positions": moved(st["positions"], "start_mm")}


def face_groups(spec: dict, all_faces: list[str]) -> list[tuple[str, dict]]:
    """入力 → [(組の名前, その組の入力)]. 切り替えが無ければ [("", spec)]。

    先頭は切り替えていない面の組（名前 ""。全部の面を切り替えたときは無い）、続いて種類ごとの組（名前＝種類）。
    面の区間を切り替えたときは、同じ面が区間ごとに別の組に入る（同じ種類の区間が1つの面に2つあれば「種類（2）」の組）。
    区間で残す面は _face_range {面: [始め, 終わり（-1 は面の終点）]} を持つ。all_faces は建てる面の名前（辺の順）。
    """
    ff = parse_face_forms(spec.get("face_forms"))
    if not ff:
        return [("", spec)]
    unknown = sorted({split_key(k)[0] for k in ff} - set(all_faces))
    if unknown:
        raise ValueError(f"face_forms: 面「{'・'.join(unknown)}」がありません（{'・'.join(all_faces)}）")
    # 組: (種類, 何番目の区間) → [(面, 始め, 終わり)]
    groups_of: dict[tuple[str, int], list[tuple[str, float, Optional[float]]]] = {}
    for face in all_faces:
        seen: dict[str, int] = {}
        for a, b, form in face_segments(ff, face):
            k = seen.get(form, 0)
            seen[form] = k + 1
            groups_of.setdefault((form, k), []).append((face, a, b))
    groups: list[tuple[str, dict]] = []
    order = sorted(groups_of, key=lambda fk: (fk[0] != "", fk[1], FACE_FORMS.index(fk[0]) if fk[0] in FACE_FORMS else -1))
    for form, k in order:
        items = groups_of[(form, k)]
        if form == "":
            sub = {kk: v for kk, v in spec.items() if kk not in ("face_forms", "form_standoff")}
            label = "" if k == 0 else f"元の足場（{k + 1}）"
        else:
            sub = {kk: v for kk, v in spec.items() if kk not in _GROUP_DROP_KEYS}
            over = FACE_FORM_SPECS[form]
            if "series_id" in over:
                # 系列を替える組はモジュール（インチ／メートル）の指定も外す（枠組・単管はメートル）
                sub.pop("module", None)
            sub.update(over)
            if over.get("_narrow") or (over.get("scaffold_form") in ("ブラケット足場", "一側足場")
                                       and over.get("bracket_post", "支柱") == "支柱" and "series_id" not in over):
                # ブラケット足場はハーフアンチ1枚の狭い足場（利用者の指定 2026-10-24）。本体の幅・作業床の指定は継がない
                sub.pop("scaffold_width_mm", None)
                sub.pop("deck_widths", None)
            # 種類ごとの離れ（form_standoff。敷地境界に収めるため単管抱き足場の離れだけ詰める等）
            fs = (spec.get("form_standoff") or {}).get(form)
            if fs:
                sub["standoff"] = {**(spec.get("standoff") or {}), **fs}
            label = form if k == 0 else f"{form}（{k + 1}）"
            sub["project_name"] = f"{spec.get('project_name') or '足場'} {label}"
        sub["faces"] = [f for f, _a, _b in items]
        ranges = {f: [a, -1.0 if b is None else b] for f, a, b in items if a > 0.5 or b is not None}
        if ranges:
            sub["_face_range"] = ranges
            for f, (a, b) in ranges.items():
                _shift_items(sub, f, all_faces, a, None if b < 0 else b)
        groups.append((label, sub))
    return groups


RESET = "元に戻す"


def faces_of_lines(plans: list[dict], origins: list[tuple[float, float]], tol_mm: float = 5.0) -> tuple[Optional[dict], list[str]]:
    """選んだ足場ラインの原点 → (その建物の plan.json, 面名の並び).

    plans は配置の控え（plan.json。切り替えた組は「切替_種類」の下にもある）。原点が配置位置に一致する面を拾う。
    同じ建物（躯体外形が同じ）の控えをまとめて見る。区切った部品は元の面と同じ原点なので同じ面になる。
    """
    from .span_readback import match_edge

    hit_plan, faces = None, []
    for o in origins:
        for p in plans:
            e = match_edge(p.get("edges") or [], o, tol_mm)
            if e is None:
                continue
            if hit_plan is None:
                hit_plan = p
            elif (p.get("outline_mm") or []) != (hit_plan.get("outline_mm") or []):
                continue
            name = str(e.get("face") or "")
            if name and name not in faces:
                faces.append(name)
            break
    return hit_plan, faces


def updated_face_forms(current, faces: list[str], form: str) -> dict[str, str]:
    """今の切り替え（文字列か dict）に、選んだ面（「南面」か区間つき「南面[a-b]」）を form にした結果. form が RESET なら
    選んだ面・区間の切り替えを外す。区間を指すときは、その区間に重なる前の区間の指定を外してから書く（新しい指定が勝つ）."""
    ff = parse_face_forms(current)
    for key in faces:
        f, a, b = split_key(key)
        if a is not None:
            for k in list(ff):
                kf, ka, kb = split_key(k)
                if kf == f and ka is not None and min(b, kb) - max(a, ka) > 1.0:
                    ff.pop(k)
            k_new = range_key(f, a, b)
        else:
            if form == RESET:
                for k in list(ff):
                    if split_key(k)[0] == f:
                        ff.pop(k)
            k_new = f
        if form == RESET:
            ff.pop(k_new, None)
        else:
            nf = normalize_form(form)
            if nf is None:
                raise ValueError(f"種類「{form}」は {'・'.join(FACE_FORMS)} のどれかです")
            ff[k_new] = nf
    return ff
