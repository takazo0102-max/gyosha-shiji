"""実機検証用の躯体スラブを作る・一覧する・選択する（ツールバー検証の準備）.

実機のプロジェクトは保存されない（デモ版）ので、検証用スラブは毎回作り直す。
以前は一時フォルダの小さなスクリプトでやっていたが、セッションごとに消えていた。

使い方:
  python3 scripts/dev_slab.py list
  python3 scripts/dev_slab.py create 30000x20000 [--at 300000,300000]   # 矩形
  python3 scripts/dev_slab.py create pentagon [--at 400000,300000]       # 北東を斜めに切った五角形
  python3 scripts/dev_slab.py create lshape [--at 600000,300000]         # L字（時計回り入力）
  python3 scripts/dev_slab.py select <GUID先頭>
作成した後はそのスラブを選択状態にするので、続けて run_from_archicad.py を実行できる。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.tapir_adapter import ArchicadClient, _extract_polygon  # noqa: E402


def _poly(kind: str, ox: float, oy: float) -> list[tuple[float, float]]:
    if "x" in kind and kind.replace("x", "").isdigit():
        w, h = (float(v) for v in kind.split("x"))
        return [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
    if kind == "pentagon":
        return [(ox, oy), (ox + 30000, oy), (ox + 30000, oy + 12000), (ox + 20000, oy + 20000), (ox, oy + 20000)]
    if kind == "lshape":
        return [(ox, oy), (ox, oy + 20000), (ox + 12000, oy + 20000), (ox + 12000, oy + 8000),
                (ox + 24000, oy + 8000), (ox + 24000, oy)]
    raise SystemExit(f"形が分かりません: {kind}（WxH / pentagon / lshape）")


def select(c: ArchicadClient, elements: list[dict]) -> None:
    # 選択は前面のウィンドウごと。配置の後はレイアウトが前面に残り、そこで選んでも平面図では選ばれていない
    from ashiba.elevation_sections import activate_floor_plan

    activate_floor_plan(c)
    sel = c.get_selected_elements()
    c.tapir("ChangeSelectionOfElements", {"addElementsToSelection": elements, "removeElementsFromSelection": sel})


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    c = ArchicadClient()
    cmd = args[0]
    if cmd == "list":
        els = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
        for e, d in zip(els, c.get_details(els)):
            poly = _extract_polygon(d) or []
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            if poly:
                print(f"{e['elementId']['guid'][:8]}  {len(poly)}点  x {min(xs):.1f}〜{max(xs):.1f}  y {min(ys):.1f}〜{max(ys):.1f}")
        return 0
    if cmd == "create":
        kind = args[1]
        at = next((a.split("=", 1)[1] if "=" in a else args[i + 1] for i, a in enumerate(args) if a.startswith("--at")), None)
        ox, oy = (float(v) for v in at.split(",")) if at else (300000.0, 300000.0)
        slab = c.create_slab(_poly(kind, ox, oy))
        select(c, [slab])
        print("作成・選択:", slab["elementId"]["guid"])
        return 0
    if cmd == "select":
        pref = args[1].upper()
        els = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
        hit = [e for e in els if e["elementId"]["guid"].upper().startswith(pref)]
        if not hit:
            raise SystemExit(f"GUID {pref}… のスラブがありません")
        select(c, hit[:1])
        print("選択:", hit[0]["elementId"]["guid"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
