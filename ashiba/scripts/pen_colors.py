"""図面のペンを区分ごとに選ぶ（パレットのボタン「ペン」）.

利用者の指定（2026-10-24）「ペンカラーを選べるコマンド作って」。押すと窓が前に出て、支柱・足場の線・床・階段・
付帯設備・壁つなぎ・層間ネット・養生・寸法文字のペンを、ペンセットの色見本つきで選べる。「適用」で置いてある足場の
部品（足場ライン・壁つなぎ・層間ネット・ネットブラケット・養生・コーナーステップ）をその場で書き換え（置き直さない）、
足場条件の部品（penList）と条件の上書き（~/Desktop/ashiba_spec.json の pens）に控えて次の配置でも使う。
色はプロジェクトの最初のペンセットの色（ビューのペンセットが違えば色はそちらになる。番号は同じ）。

窓の「カラーの組」「白黒の組」は、区分ごとに決めた色（支柱 赤・足場の線 青・床 緑…。ashiba.pens.COLOR_SCHEME）にいちばん近い
ペンをペンセットから選んで一度で適用する（GLOOBE の「カラー印刷」に当たる。2026-11-02）。窓なしは --preset カラー / 白黒。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.pens import PART_PENS, PEN_KEYS, format_pens, gdl_pens, parse_pens, part_base, preset_pens  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402


def pen_table(c: ArchicadClient) -> tuple[str, list[tuple[int, str, str]]]:
    """(ペンセットの名前, [(番号, "#RRGGBB", 説明)]). 読めなければ番号だけ（色は灰）."""
    try:
        ids = c.post("API.GetAttributesByType", {"attributeType": "PenTable"})["attributeIds"]
        attr = c.post("API.GetPenTableAttributes", {"attributeIds": ids[:1]})["attributes"][0]["penTableAttribute"]
        out = []
        for row in attr.get("pens", []):
            p = row.get("pen") or {}
            col = p.get("color") or {}
            hexc = "#%02X%02X%02X" % tuple(int(round(float(col.get(k, 0.5)) * 255)) for k in ("red", "green", "blue"))
            out.append((int(p.get("index", 0)), hexc, str(p.get("description") or "")))
        return str(attr.get("name") or ""), sorted(out)
    except (TapirError, KeyError, IndexError, ValueError):
        return "", [(i, "#808080", "") for i in range(1, 256)]


def pen_weights(c: ArchicadClient) -> list[tuple[int, str, float]]:
    """[(番号, "#RRGGBB", 太さ mm)]（一番めのペンセット。pen_table と同じ）。読めなければ空."""
    try:
        ids = c.post("API.GetAttributesByType", {"attributeType": "PenTable"})["attributeIds"]
        attr = c.post("API.GetPenTableAttributes", {"attributeIds": ids[:1]})["attributes"][0]["penTableAttribute"]
        out = []
        for row in attr.get("pens", []):
            p = row.get("pen") or {}
            col = p.get("color") or {}
            hexc = "#%02X%02X%02X" % tuple(int(round(float(col.get(k, 0.5)) * 255)) for k in ("red", "green", "blue"))
            out.append((int(p.get("index", 0)), hexc, float(p.get("weight") or 0.0)))
        return sorted(out)
    except (TapirError, KeyError, IndexError, ValueError, TypeError):
        return []


def draft_pens_for(c: ArchicadClient, base: int) -> dict[str, int]:
    """部品の描き方の太線・細線・範囲の線のペン（線のペン base と同じ色の太い・細いもの）."""
    from ashiba.pens import draft_pens

    return draft_pens(pen_weights(c), base)


def title_of(index: int, desc: str) -> str:
    return f"{index}" + (f"  {desc}" if desc else "")


def index_of(title: str) -> int:
    head = str(title).strip().split(" ", 1)[0]
    return int(head) if head.isdigit() else 1


def current_pens(c: ArchicadClient) -> dict[str, int]:
    """足場条件の部品（どれか1つ）の penList、無ければ条件の上書きの pens."""
    import run_from_archicad as R

    for _el, _o, params in R.read_spec_objects(c):
        if params.get("penList"):
            return parse_pens(params["penList"])
    return parse_pens(R.load_spec_override().get("pens"))


def save_pens(c: ArchicadClient, pens: dict[str, int]) -> int:
    """足場条件の部品すべての penList と、条件の上書き（新しい建物の既定）に控える → 書いた部品の数."""
    import run_from_archicad as R

    from ashiba.spec_object import upgrade_params

    text = format_pens(pens)
    n = 0
    for el, _o, params in R.read_spec_objects(c):
        new_params, added = upgrade_params(params)
        new_params["penList"] = text
        try:
            if added or "penList" not in params:
                # 古い版（penList が無い）: 値を引き継いで今の版に置き換えて控える
                R.upgrade_spec_object(c, el, new_params, [a for a in added if a != "penList"])
            else:
                c.set_gdl_parameters(el, {"penList": text})
            n += 1
        except TapirError:
            pass
    try:
        body = json.loads(R.SPEC_OVERRIDE.read_text(encoding="utf-8")) if R.SPEC_OVERRIDE.exists() else {}
        if isinstance(body, dict):
            if text:
                body["pens"] = text
            else:
                body.pop("pens", None)
            R.SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        pass
    return n


def apply_to_parts(c: ArchicadClient, pens: dict[str, int]) -> tuple[int, int]:
    """置いてある足場の部品のペンを書き換える → (書き換えた数, 書けなかった数（古い版の部品）)."""
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    pairs = []
    for e, d in zip(objs, c.get_details(objs) if objs else []):
        lp = (d.get("details", {}).get("libPart") or {})
        base = part_base(lp.get("name", "") if isinstance(lp, dict) else "")
        if base in PART_PENS:
            pairs.append((e, gdl_pens(pens, base)))
    if not pairs:
        return 0, 0
    ok = c.set_gdl_parameters_many(pairs)
    return ok, len(pairs) - ok


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    c = ArchicadClient()
    R.ensure_parts(c)
    name, table = pen_table(c)
    argv = sys.argv[1:]
    preset = argv[argv.index("--preset") + 1] if "--preset" in argv and argv.index("--preset") + 1 < len(argv) else ""
    titles = [title_of(i, desc) for i, _h, desc in table]
    colors = [h for _i, h, _d in table]
    by_index = {i: title_of(i, desc) for i, _h, desc in table}
    cur = current_pens(c)
    fields = [{"key": "_s", "label": "図面のペン（区分ごと）", "kind": "section"}]
    fields += [{"key": k, "label": label, "kind": "pen", "options": titles, "colors": colors, "help": detail,
                "value": by_index.get(int(cur.get(k, 1)), titles[0] if titles else "1")}
               for k, _p, label, detail in PEN_KEYS]
    intro = ("足場の図面のペンを区分ごとに選んでください。「適用」で置いてある足場の部品を書き換え、次の配置でも使います。"
             + (f"色はペンセット「{name}」の色です。" if name else ""))
    if preset:
        res = {"button": "color" if preset == "カラー" else "mono" if preset == "白黒" else "", "values": {}}
    else:
        res = show_form({"title": "仮設足場のペン", "intro": intro + "「カラーの組」「白黒の組」は区分ごとの色を一度で選んで適用します。",
                         "fields": fields,
                         "buttons": [{"id": "apply", "label": "適用"}, {"id": "color", "label": "カラーの組"},
                                     {"id": "mono", "label": "白黒の組"}, {"id": "cancel", "label": "やめる"}]})
    button = (res or {}).get("button")
    if button not in ("apply", "color", "mono"):
        print("ペン: やめました（何も変えていません）")
        return 0
    if button == "apply":
        vals = res.get("values") or {}
        pens = {k: index_of(vals[k]) for k, _p, _l, _d in PEN_KEYS if k in vals}
    else:
        pens = preset_pens(table, "カラー" if button == "color" else "白黒")
    ok, ng = apply_to_parts(c, pens)
    n_spec = save_pens(c, pens)
    picked = "・".join(f"{label} {pens.get(k, 1)}" for k, _p, label, _d in PEN_KEYS)
    print(f"ペン: {picked}")
    print(f"足場の部品 {ok}個のペンを書き換えました" + (f"（足場条件の部品 {n_spec}個に控えました）" if n_spec else ""))
    if ng:
        print(f"注意: {ng}個は古い版の部品でペンを持っていません。「配置」で置き直すと選んだペンで描きます")
    return 0


if __name__ == "__main__":
    sys.exit(main())
