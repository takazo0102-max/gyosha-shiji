"""プロジェクトに置いた足場部品の版を数え、埋め込みライブラリの古い版の消し方を案内する（Phase 13-3）.

使い方: python3 scripts/library_report.py
読むだけで、何も消さない（埋め込んだ部品は API で消せない。消すのはライブラリマネージャで手で）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.elevation_sections import activate_floor_plan  # noqa: E402
from ashiba.library_versions import CLEANUP_STEPS, count_versions, current_versions  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient  # noqa: E402


def main() -> int:
    c = ArchicadClient()
    activate_floor_plan(c)            # 部品は平面図のデータベースにある
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    names = []
    for d in (c.get_details(objs) if objs else []):
        lp = (d.get("details") or {}).get("libPart") or {}
        names.append(lp.get("name", "") if isinstance(lp, dict) else "")
    rep = count_versions(names, current_versions(ROOT / "gdl"))
    for line in rep.lines():
        print(line)
    print()
    for line in CLEANUP_STEPS:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
