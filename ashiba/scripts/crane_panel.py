"""パレットの「クレーン操作」: 車体とフックを動かす小窓（tapir/crane_panel.swift）を開く.

初めて開くときと直したあとは swiftc で作る（十数秒。tapir/build/AshibaCrane-<中身の印>）。窓は押されるたびに
scripts/crane_move.py を呼ぶ。もう開いていれば新しくは開かない。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tapir" / "crane_panel.swift"
BUILD = ROOT / "tapir" / "build"


def binary() -> Path:
    tag = hashlib.sha1(SRC.read_bytes()).hexdigest()[:8]
    exe = BUILD / f"AshibaCrane-{tag}"
    if exe.exists():
        return exe
    BUILD.mkdir(parents=True, exist_ok=True)
    for old in BUILD.glob("AshibaCrane-*"):
        old.unlink()
    r = subprocess.run(["swiftc", "-O", str(SRC), "-o", str(exe)], capture_output=True, text=True)
    if r.returncode != 0 or not exe.exists():
        raise RuntimeError("クレーン操作の窓を作れませんでした（swiftc）: " + (r.stderr or r.stdout or "").strip()[-400:])
    return exe


def main() -> int:
    if subprocess.run(["pgrep", "-f", "AshibaCrane-"], capture_output=True).returncode == 0:
        print("クレーン操作の窓はもう開いています")
        return 0
    exe = binary()
    subprocess.Popen([str(exe), str(ROOT), sys.executable, os.environ.get("ASHIBA_PORT", "")], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print("クレーン操作の窓を開きました（クレーンを選んで押す）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
