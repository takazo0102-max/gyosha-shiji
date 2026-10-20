"""この建物の足場条件の部品を選ぶ（パレットのボタン「条件」）.

利用者の指定（2026-10-20）: パレット式で使いやすく。条件（幅・手すり・階段の付け方・水平ネットの層・
養生材など）は足場条件の部品の設定ダイアログで変えるが、部品を探して選ぶのが手間。押すと、選んでいる
躯体スラブ（無ければ最後に配置した建物）の足場条件の部品を選ぶので、そのまま設定ダイアログ（⌘T）を開ける。
部品がまだ無ければ、最初の「配置」で建物の左下に置かれる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.spec_object import pick_spec_object  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError, get_selected_outline_mm  # noqa: E402

OUT_DIR = Path.home() / "Desktop" / "ashiba_out"


def _outline(c: ArchicadClient):
    try:
        return [list(p) for p in get_selected_outline_mm(c)]
    except (TapirError, ValueError, KeyError, IndexError):
        pass
    plans = sorted(OUT_DIR.glob("*_plan.json"), key=lambda p: p.stat().st_mtime)
    if plans:
        return json.loads(plans[-1].read_text(encoding="utf-8")).get("outline_mm")
    return None


def main() -> int:
    from ashiba.elevation_sections import activate_floor_plan
    from run_from_archicad import read_spec_objects

    c = ArchicadClient()
    activate_floor_plan(c)
    outline = _outline(c)
    if not outline:
        print("建物が分かりません。躯体スラブを選んでから押すか、先に「配置」してください")
        return 1
    hit = pick_spec_object(read_spec_objects(c), outline)
    if hit is None:
        print("この建物の足場条件の部品がありません。「配置」を押すと建物の左下に置きます")
        return 1
    sel = c.get_selected_elements()
    c.tapir("ChangeSelectionOfElements", {"addElementsToSelection": [hit[0]], "removeElementsFromSelection": sel})
    print("足場条件の部品を選びました。⌘T（オブジェクトの設定）で条件を変え、「配置」で置き直してください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
