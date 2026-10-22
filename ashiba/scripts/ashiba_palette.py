"""仮設足場のパレットの窓を開く（Tapir の入口「足場_パレット」から呼ぶ）.

窓は tapir/palette_panel.swift（AppKit の浮いた小窓）。初めて開くときと直したあとは swiftc で作る（十数秒。
作ったものは tapir/build/AshibaPalette-<中身の印>）。前に開いた窓があれば閉じて
開き直す（Archicad の番号＝ポートが変わっても窓が古い番号を使わないように）。窓は別のプロセスで動き続け、
この入口はすぐ終わる（Tapir を待たせない）。窓の出力は ~/Desktop/ashiba_out/パレット窓.log。

使い方: python3 scripts/ashiba_palette.py [--close]
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.palette import panel_layout  # noqa: E402

OUT = Path.home() / "Desktop" / "ashiba_out"
PANEL = ROOT / "tapir" / "palette_panel.swift"
BUILD = ROOT / "tapir" / "build"
PID = OUT / ".palette.pid"


def close_old() -> bool:
    """前に開いた窓（記録したプロセス）を閉じる. 閉じたら True."""
    try:
        pid = int(PID.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
        if "AshibaPalette" not in cmd:
            return False
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False
    finally:
        try:
            PID.unlink()
        except OSError:
            pass


def binary() -> Path:
    """窓のプログラム（中身が変わったら作り直す）. 作れなければ RuntimeError."""
    tag = hashlib.sha1(PANEL.read_bytes()).hexdigest()[:8]
    exe = BUILD / f"AshibaPalette-{tag}"
    if exe.exists():
        return exe
    BUILD.mkdir(parents=True, exist_ok=True)
    for old in BUILD.glob("AshibaPalette-*"):
        old.unlink()
    r = subprocess.run(["swiftc", "-O", str(PANEL), "-o", str(exe)], capture_output=True, text=True)
    if r.returncode != 0 or not exe.exists():
        raise RuntimeError("パレットの窓を作れませんでした（swiftc）: " + (r.stderr or r.stdout or "").strip()[-400:])
    return exe


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    OUT.mkdir(parents=True, exist_ok=True)
    closed = close_old()
    if "--close" in argv:
        print("パレットの窓を閉じました" if closed else "開いている窓はありません")
        return 0
    try:
        exe = binary()
    except (RuntimeError, OSError) as e:
        print(f"エラー: {e}")
        return 1
    layout = OUT / ".palette_layout.json"
    layout.write_text(json.dumps(panel_layout(), ensure_ascii=False), encoding="utf-8")
    port = os.environ.get("ASHIBA_PORT", "")
    with open(OUT / "パレット窓.log", "w", encoding="utf-8") as log:
        proc = subprocess.Popen([str(exe), str(ROOT), sys.executable, str(layout), str(OUT), port],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    PID.write_text(str(proc.pid))
    print("仮設足場のパレットの窓を開きました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
