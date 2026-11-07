"""足場条件の登録と呼び出し（パレットのボタン「登録」「呼び出し」）.

参考: smartCON Planner の足場条件の登録。会社・現場の定番の条件（足場の種類・幅・手すり・養生材・
階段の付け方・ネットの層など）に名前を付けて控え、別の建物の足場条件の部品へ呼び出す。

使い方（躯体スラブを選んで。選んでいなければ最後に配置した建物）:
  1. 「登録」を押し、窓で登録名を入れる（初期値は足場条件の部品の「登録名」）→ ashiba_out/条件の登録/<登録名>.json に控える
  2. 別の建物で「呼び出し」を押し、窓の一覧から選ぶ →「配置」

  python3 scripts/spec_preset.py save|load|list [登録名]
  （登録名を引数で渡すと部品の登録名より優先。load は工事名・軒高・掛ける面・部材編集などの建物ごとの値は変えない）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.presets import apply_preset, list_presets, load_preset, preset_dir, save_preset  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient  # noqa: E402

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "ashiba_out"))  # 試験は ASHIBA_OUT で別の場所に


def _spec_part(c):
    from ashiba.elevation_sections import activate_floor_plan
    from ashiba.spec_object import pick_spec_object
    from run_from_archicad import read_spec_objects
    from select_spec import _outline

    activate_floor_plan(c)
    outline = _outline(c)
    if not outline:
        return None
    return pick_spec_object(read_spec_objects(c), outline)


def labels() -> dict[str, str]:
    """足場条件の部品のパラメータ名 → 設定ダイアログの名前（呼び出しで変わった項目を toeBoard でなく「幅木を付ける」と出す）."""
    import re

    try:
        xml = (ROOT / "gdl" / "hsf" / "ashiba_spec" / "paramlist.xml").read_text(encoding="utf-8")
    except OSError:
        return {}
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r'Name="([^"]+)">\s*<Description><!\[CDATA\["(.*?)"\]\]>', xml)}


def ask_name(mode: str, now: str) -> str | None:
    """登録名を窓で. save は名前を入れる（今の登録名が初期値）、load は登録済みから選ぶ. やめたら None・登録が無ければ ""."""
    from form_dialog import show_form

    have = list_presets(OUT_DIR)
    if mode == "load":
        if not have:
            return ""
        field = {"key": "name", "label": "呼び出す条件", "kind": "choice", "options": have, "value": now if now in have else have[0]}
        intro = "登録した条件を、この建物の足場条件の部品へ呼び出します（工事名・軒高・掛ける面などの建物ごとの値は変えません）。"
    else:
        field = {"key": "name", "label": "登録名", "kind": "text", "value": now}
        intro = ("この建物の足場条件に名前を付けて控えます。同じ名前があれば上書きします。"
                 + (f"登録済み: {'・'.join(have)}" if have else ""))
    res = show_form({"title": "条件の登録" if mode == "save" else "条件の呼び出し", "intro": intro, "fields": [field],
                     "buttons": [{"id": "go", "label": "登録" if mode == "save" else "呼び出す"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "go":
        return None
    return str((res.get("values") or {}).get("name") or "").strip()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "list"
    name_arg = argv[1] if len(argv) > 1 else ""
    if mode == "list":
        have = list_presets(OUT_DIR)
        print("登録済みの条件: " + ("・".join(have) if have else "なし") + f"（{preset_dir(OUT_DIR)}）")
        return 0
    c = ArchicadClient()
    hit = _spec_part(c)
    if hit is None:
        print("この建物の足場条件の部品がありません。躯体スラブを選ぶか、先に「配置」してください")
        return 1
    el, params = hit
    name = name_arg or str(params.get("presetName") or "").strip()
    if not name_arg and mode in ("save", "load"):
        # 登録名を部品の設定（⌘T）に書かないと使えなかった → 窓で名前を入れる・一覧から選ぶ（2026-11-07 ループの試験）
        name = ask_name(mode, name)
        if name is None:
            print(f"{'条件の登録' if mode == 'save' else '条件の呼び出し'}: やめました")
            return 0
        if not name:
            print("条件の呼び出し: 登録済みの条件がありません。先に「条件の登録」で登録してください" if mode == "load"
                  else "条件の登録: 登録名を入れてください")
            return 1
        if mode == "save" and name != str(params.get("presetName") or "").strip():
            c.set_gdl_parameters(el, {"presetName": name})          # 部品の登録名にも控える
    try:
        if mode == "save":
            path = save_preset(name, params, OUT_DIR)
            print(f"条件の登録: 「{name}」を登録しました（{path}）。別の建物で「条件の呼び出し」を押し、一覧から「{name}」を選ぶ")
            print("登録済みの条件: " + "・".join(list_presets(OUT_DIR)))
            return 0
        if mode == "load":
            preset = load_preset(name, OUT_DIR)
            new, changed = apply_preset(params, preset)
            if not changed:
                print(f"条件の呼び出し: 「{name}」は今の足場条件と同じです")
                return 0
            c.set_gdl_parameters(el, {k: new[k] for k in changed})
            lb = labels()
            print(f"条件の呼び出し: 「{name}」を呼び出しました（{len(changed)}項目: {'・'.join(lb.get(k, k).split('（')[0].strip() for k in changed)}）。"
                  "「配置」で置き直してください")
            return 0
    except (ValueError, FileNotFoundError) as e:
        print(str(e))
        return 1
    print(f"使い方: spec_preset.py save|load|list [登録名]（{mode} は分かりません）")
    return 2


if __name__ == "__main__":
    sys.exit(main())
