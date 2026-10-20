"""帳票の出力先（デスクトップの ashiba_out）を Finder で開き、最新の割付レポートを開く（パレットのボタン「帳票」）."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

OUT_DIR = Path.home() / "Desktop" / "ashiba_out"


def main() -> int:
    if not OUT_DIR.exists():
        print(f"帳票がまだありません（{OUT_DIR}）。先に「配置」を押してください")
        return 1
    subprocess.run(["open", str(OUT_DIR)], check=False)
    reports = sorted(OUT_DIR.glob("*_割付レポート.md"), key=lambda p: p.stat().st_mtime)
    if reports:
        subprocess.run(["open", "-e", str(reports[-1])], check=False)
    names = sorted(p.name for p in OUT_DIR.iterdir() if p.is_file() and not p.name.startswith("."))
    print("帳票: " + "・".join(n for n in names if n.endswith((".csv", ".md", ".xlsx"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
