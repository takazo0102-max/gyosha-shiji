"""足場の条件の窓を開いて、押したボタンと選んだ値を受け取る（配置・条件のボタンから）.

窓は tapir/spec_form.swift（AppKit）。初めて開くときと直したあとは swiftc で作る（十数秒。tapir/build/AshibaForm-<中身の印>）。
環境変数 ASHIBA_FORM_ANSWER（{"button": ..., "values": {...}} の JSON）があれば窓を出さずにそれを返す（試験用）。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tapir" / "spec_form.swift"
BUILD = ROOT / "tapir" / "build"


def binary() -> Path:
    """窓のプログラム（中身が変わったら作り直す）. 作れなければ RuntimeError."""
    tag = hashlib.sha1(SRC.read_bytes()).hexdigest()[:8]
    exe = BUILD / f"AshibaForm-{tag}"
    if exe.exists():
        return exe
    BUILD.mkdir(parents=True, exist_ok=True)
    for old in BUILD.glob("AshibaForm-*"):
        old.unlink()
    r = subprocess.run(["swiftc", "-O", str(SRC), "-o", str(exe)], capture_output=True, text=True)
    if r.returncode != 0 or not exe.exists():
        raise RuntimeError("条件の窓を作れませんでした（swiftc）: " + (r.stderr or r.stdout or "").strip()[-400:])
    return exe


def show_form(form: dict) -> Optional[dict]:
    """窓を出して待つ → {"button": id, "values": {...}}。閉じた・作れなければ None（呼び側は窓なしで続けるか止める）."""
    canned = os.environ.get("ASHIBA_FORM_ANSWER")
    if canned:
        return json.loads(canned)
    exe = binary()
    with tempfile.TemporaryDirectory() as td:
        fin, fout = Path(td) / "form.json", Path(td) / "result.json"
        fin.write_text(json.dumps(form, ensure_ascii=False), encoding="utf-8")
        subprocess.run([str(exe), str(fin), str(fout)], capture_output=True, text=True)
        if not fout.exists():
            return None
        return json.loads(fout.read_text(encoding="utf-8"))
