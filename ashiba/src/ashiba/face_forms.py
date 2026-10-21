"""面ごと・面の組（ブロック）ごとに足場の種類を切り替える（利用者の指定 2026-10-22: 面ごとやブロックを違う足場に
切り替えれるようコマンド作って）.

入力の face_forms（{面名: 種類}、または「南面=ブラケット足場（単管）;東面=単管抱き足場」の文字列）で、指定した面だけ
別の種類で解く。配置（run_from_archicad）は面の組ごとに解いて足場ラインを置き、前回の配置の片付けは1回にまとめる。
隣の面を建てない端は開放端（妻側の手すり・幅木）になる（faces で一部の面だけ建てるときと同じ）。

面名は外形の辺の方位（南面・東面…。同じ方位が2つあれば「南面(辺2)」）で、系列に依らない。
"""

from __future__ import annotations

from typing import Optional

# 切り替えられる足場の種類 → 入力に重ねる値。series_id を持つ種類は系列も替える（module は外す）
FACE_FORM_SPECS: dict[str, dict] = {
    "本足場": {"scaffold_form": "本足場"},
    "一側足場": {"scaffold_form": "一側足場"},
    "ブラケット足場（支柱）": {"scaffold_form": "ブラケット足場", "bracket_post": "支柱"},
    "ブラケット足場（単管）": {"scaffold_form": "ブラケット足場", "bracket_post": "単管"},
    "単管抱き足場": {"scaffold_form": "単管抱き足場"},
    "単管本足場": {"scaffold_form": "本足場", "series_id": "tankan"},
    "枠組足場": {"scaffold_form": "本足場", "series_id": "waku"},
}
FACE_FORMS = tuple(FACE_FORM_SPECS)
# 切り替えた組では使わない入力（スパン・部材の指定は元の種類の割付に対するもの）
_GROUP_DROP_KEYS = ("span_overrides", "member_edits", "face_forms")


def parse_face_forms(value) -> dict[str, str]:
    """face_forms の値 → {面名: 種類}. 空なら {}。種類の綴りの違い（括弧の全角・半角）は揃える."""
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
        out[face if face.endswith("面") or "(" in face else face + "面"] = form
    return out


def normalize_form(text: str) -> Optional[str]:
    t = text.strip().replace("(", "（").replace(")", "）").replace(" ", "")
    return t if t in FACE_FORM_SPECS else None


def format_face_forms(ff: dict[str, str]) -> str:
    """{面名: 種類} → 足場条件の部品に書く文字列（面の並びは入力のまま）."""
    return ";".join(f"{k}={v}" for k, v in ff.items())


def face_groups(spec: dict, all_faces: list[str]) -> list[tuple[str, dict]]:
    """入力 → [(組の名前, その組の入力)]. 切り替えが無ければ [("", spec)]。

    先頭は切り替えていない面の組（名前 ""。全部の面を切り替えたときは無い）、続いて種類ごとの組（名前＝種類）。
    all_faces は建てる面の名前（入力の faces で絞っていればその面だけ）。
    """
    ff = parse_face_forms(spec.get("face_forms"))
    if not ff:
        return [("", spec)]
    unknown = [f for f in ff if f not in all_faces]
    if unknown:
        raise ValueError(f"face_forms: 面「{'・'.join(unknown)}」がありません（{'・'.join(all_faces)}）")
    groups: list[tuple[str, dict]] = []
    rest = [f for f in all_faces if f not in ff]
    if rest:
        base = {k: v for k, v in spec.items() if k not in ("face_forms",)}
        base["faces"] = rest
        groups.append(("", base))
    by_form: dict[str, list[str]] = {}
    for face in all_faces:
        if face in ff:
            by_form.setdefault(ff[face], []).append(face)
    for form, faces in by_form.items():
        sub = {k: v for k, v in spec.items() if k not in _GROUP_DROP_KEYS}
        over = FACE_FORM_SPECS[form]
        if "series_id" in over:
            # 系列を替える組はモジュール（インチ／メートル）の指定も外す（枠組・単管はメートル）
            sub.pop("module", None)
        sub.update(over)
        sub["faces"] = faces
        sub["project_name"] = f"{spec.get('project_name') or '足場'} {form}"
        groups.append((form, sub))
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
    """今の切り替え（文字列か dict）に、選んだ面を form にした結果. form が RESET なら選んだ面の切り替えを外す."""
    ff = parse_face_forms(current)
    for f in faces:
        if form == RESET:
            ff.pop(f, None)
        else:
            nf = normalize_form(form)
            if nf is None:
                raise ValueError(f"種類「{form}」は {'・'.join(FACE_FORMS)} のどれかです")
            ff[f] = nf
    return ff
