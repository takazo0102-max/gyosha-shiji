"""Tapir パレットに「仮設足場」のボタン（配置・解き直し・撤去）を並べる（Phase 10-3）.

<ashiba>/tapir/palette に入口の .py を作り、Tapir が読むフォルダ ~/Documents/Tapir/custom-scripts に
入口ごとのリンク（足場1_配置.py など）を置く。Tapir のパレットはこのフォルダの直下しか読まない
（~/Documents/Tapir の別フォルダは一覧に出ず、サブフォルダは展開されずに1項目になった。実機 2026-10-18）。

custom-scripts は配筋ツールのフォルダ（へのリンク）なので、配筋ツールのファイルには触らない。
置くのはこのツールの入口へのリンクだけで、片付けるのも「リンク先がこのツールの入口」のものだけ。
置いたあと、パレットの一覧の「Reload scripts...」で読み直すと出る。

使い方: python3 scripts/install_palette.py [--dry-run] [--remove]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.palette import ENTRIES, FOLDER_NAME, MARK, entry_source  # noqa: E402

PALETTE_DIR = ROOT / "tapir" / "palette"
TAPIR_DIR = Path.home() / "Documents" / "Tapir"
SCRIPTS_DIR = TAPIR_DIR / "custom-scripts"


def _ours(link: Path) -> bool:
    """このツールの入口を指すリンクか（別の作業ツリーに作った古いものも含む）."""
    if not link.is_symlink():
        return False
    try:
        target = Path(os.path.realpath(link))
        return target.suffix == ".py" and MARK in target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "tapir/palette" in os.readlink(link)       # 先が消えたリンク


def main() -> int:
    dry = "--dry-run" in sys.argv
    remove = "--remove" in sys.argv
    if not remove:
        PALETTE_DIR.mkdir(parents=True, exist_ok=True)
        keep = {e.file for e in ENTRIES}
        for old in sorted(PALETTE_DIR.glob("*.py")):
            if old.name not in keep and MARK in old.read_text(encoding="utf-8", errors="replace"):
                print(f"片付け（古い入口）: {old}")
                if not dry:
                    old.unlink()
        for e in ENTRIES:
            path = PALETTE_DIR / e.file
            print(f"入口: {path}")
            if not dry:
                path.write_text(entry_source(e), encoding="utf-8")
                os.chmod(path, 0o755)
    # 前に試した置き方（~/Documents/Tapir/仮設足場、custom-scripts/仮設足場）は一覧に出ないので片付ける
    for stale in (TAPIR_DIR / FOLDER_NAME, SCRIPTS_DIR / FOLDER_NAME):
        if stale.is_symlink() and "tapir/palette" in os.readlink(stale):
            print(f"片付け（前の置き方のリンク）: {stale}")
            if not dry:
                stale.unlink()
    if not SCRIPTS_DIR.exists():
        print(f"{SCRIPTS_DIR} がありません（Tapir を入れて Archicad を一度起動してください）")
        return 1
    for link in sorted(SCRIPTS_DIR.iterdir()):
        if _ours(link) and (remove or link.name not in {e.file for e in ENTRIES}
                            or os.path.realpath(link) != str((PALETTE_DIR / link.name).resolve())):
            print(f"リンクを外す: {link}")
            if not dry:
                link.unlink()
    if remove:
        return 0
    for e in ENTRIES:
        link = SCRIPTS_DIR / e.file
        if link.is_symlink() and os.path.realpath(link) == str((PALETTE_DIR / e.file).resolve()):
            continue
        if link.exists() or link.is_symlink():
            print(f"{link} は別のファイルなので触りません")
            continue
        print(f"リンク: {link} → {PALETTE_DIR / e.file}")
        if not dry:
            link.symlink_to(PALETTE_DIR / e.file)
    print("Tapir パレットの一覧の「Reload scripts...」で読み直すと「足場1_配置」などが出ます")
    return 0


if __name__ == "__main__":
    sys.exit(main())
