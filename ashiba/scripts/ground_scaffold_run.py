"""地足場を置く（パレットのボタン「地足場」）.

利用者の指定（2026-10-24）「地足場機能も追加して」。躯体スラブを選んで押し、窓で層数（1〜3）を選ぶと、地上に低く組む
足場（基礎・1階まわりの作業用。作業床をその層数だけ、2層以下は階段室を置かずはしご）を置く。条件（系列・幅・手すり
など）は足場条件の部品と条件の上書きのまま。上の階の足場に組み上げるときは「配置」で建て直す。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LEVELS = {"1層（作業床 1.8m 前後）": 1, "2層": 2, "3層": 3}


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    res = show_form({"title": "地足場", "intro": "躯体スラブを選んでから押してください。地上に低く組む足場（基礎・1階まわりの"
                     "作業用）を置きます。2層以下は階段室を置かず、はしごで昇降します。",
                     "fields": [{"key": "levels", "label": "層数", "kind": "choice", "options": list(LEVELS),
                                 "value": next(iter(LEVELS))}],
                     "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        print("地足場: やめました（何も置いていません）")
        return 0
    n = LEVELS.get(str((res.get("values") or {}).get("levels") or ""), 1)
    print(f"地足場: {n}層で置きます")
    R.main(spec_override={**R.load_spec_override(), "ground_scaffold": {"levels": n}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
