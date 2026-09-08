"""選択したスラブに対して置いた足場ライン・立面図・詳細図を撤去する（ツールバー割当用）.

条件を変えて何度も試すとき、run_from_archicad.py は同じ位置の前回分を置き換えるが、
外形や離れが変わると位置がずれて残る。スラブを選択してこれを実行すると、その建物の
ぶんだけ消す（他の建物の配置や他ツールの部品には触らない）。

使い方:
  スラブを選択 → python3 scripts/remove_from_archicad.py
  python3 scripts/remove_from_archicad.py --all     # プロジェクト内の足場部品を全部消す
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.tapir_adapter import ArchicadClient, TapirError, get_selected_outline_mm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_from_archicad import DETAIL_OBJECT, DETAIL_OFFSET_MM, ELEVATION_OFFSET_MM, LINE_OBJECT  # noqa: E402


def main() -> int:
    client = ArchicadClient()
    names = (LINE_OBJECT, DETAIL_OBJECT)
    if "--all" in sys.argv:
        els = client.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        targets = [
            e for e, d in zip(els, client.get_details(els) if els else [])
            if ((d.get("details", {}).get("libPart") or {}).get("name") or "") in names
        ]
    else:
        outline = get_selected_outline_mm(client)
        targets = client.objects_for_slab(
            outline, names, elevation_offset_mm=ELEVATION_OFFSET_MM, detail_offset_mm=DETAIL_OFFSET_MM,
        )
    if not targets:
        print("撤去する足場部品はありません")
        return 0
    client.delete_elements(targets)
    print(f"足場部品 {len(targets)}個を撤去しました")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TapirError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)
