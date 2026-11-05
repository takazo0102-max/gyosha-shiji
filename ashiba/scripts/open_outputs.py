"""帳票の出力先（デスクトップの ashiba_out）を Finder で開き、最新の割付レポートを開く（パレットのボタン「帳票」）."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "ashiba_out"))  # 試験は ASHIBA_OUT で別の場所に


RECENT = 8      # 結果の窓に出す新しい帳票の数（全部を1行に並べると 60 個近くになり読めなかった 2026-11-05）


def summary(out_dir: Path, report: Path | None) -> list[str]:
    """結果の窓に出す行: 開いたレポートと、新しい順の帳票 RECENT 個（残りは数だけ）."""
    files = sorted((p for p in out_dir.iterdir() if p.is_file() and not p.name.startswith(".")
                    and p.name.endswith((".csv", ".md", ".xlsx", ".pdf"))), key=lambda p: -p.stat().st_mtime)
    lines = [f"帳票: 出力先 {out_dir} を開きました" + (f"・最新の割付レポート {report.name} を開きました" if report else "")]
    if files:
        rest = len(files) - RECENT
        lines.append("  新しい帳票: " + "・".join(p.name for p in files[:RECENT]) + (f" ほか {rest}個" if rest > 0 else ""))
    return lines


def main() -> int:
    if not OUT_DIR.exists():
        print(f"帳票がまだありません（{OUT_DIR}）。先に「配置」を押してください")
        return 1
    subprocess.run(["open", str(OUT_DIR)], check=False)
    reports = sorted(OUT_DIR.glob("*_割付レポート.md"), key=lambda p: p.stat().st_mtime)
    if reports:
        subprocess.run(["open", "-e", str(reports[-1])], check=False)
    print("\n".join(summary(OUT_DIR, reports[-1] if reports else None)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
