"""足場条件の登録と呼び出し（パレットのボタン「登録」「呼び出し」）.

参考: smartCON Planner の足場条件の登録。会社・現場の定番の条件（足場の種類・幅・手すり・養生材・
階段の付け方・ネットの層など）に名前を付けて控え、別の建物の足場条件の部品へ呼び出す。

使い方（躯体スラブを選んで。選んでいなければ最後に配置した建物）:
  1. 足場条件の部品の「登録名」に名前を書く（⌘T、基本のページ）
  2. 「登録」を押す → ashiba_out/条件の登録/<登録名>.json に控える
  3. 別の建物の足場条件の部品の「登録名」に同じ名前を書いて「呼び出し」→「配置」

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
    try:
        if mode == "save":
            path = save_preset(name, params, OUT_DIR)
            print(f"条件の登録: 「{name}」を登録しました（{path}）。別の建物の足場条件の登録名に「{name}」と書いて「条件の呼び出し」")
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
