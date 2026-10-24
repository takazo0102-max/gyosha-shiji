"""仮設足場のパレットの窓（tapir/palette_panel.js）から呼ぶ実行役.

  python3 scripts/palette_run.py --kinds      選んでいるものの種類を JSON で出す（窓が★を付けるのに使う）
  python3 scripts/palette_run.py 配置         操作を実行し、1行目に「完了」か「止まりました…」、続けて要点を出す

全文は ~/Desktop/ashiba_out/パレット実行.log に残す。Archicad の番号（ポート）は窓が ASHIBA_PORT で渡す。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.palette import ACTIONS, summary  # noqa: E402

OUT = Path.home() / "Desktop" / "ashiba_out"


def kinds_json() -> str:
    from ashiba_menu import selection_kinds

    kinds, desc = selection_kinds()
    return json.dumps({"kinds": sorted(kinds), "desc": desc}, ensure_ascii=False)


def run_action(title: str) -> tuple[int, str]:
    """操作を実行 → (終了コード, 窓に出す文: 1行目が結果、続けて要点)."""
    # パレットの窓（Swift の Process）は引数を NFD に分解して渡す（「ペ」→「ヘ」＋半濁点）。合成して比べる
    # （利用者の指摘 2026-10-24: ペンのところができない。「条件の呼び出し」の「び」も同じ）
    title = unicodedata.normalize("NFC", title)
    act = next((a for a in ACTIONS if a.title == title), None)
    if act is None:
        return 2, f"止まりました\n「{title}」という操作はありません"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / act.script)] + list(act.args),
                          capture_output=True, text=True, env=env, cwd=ROOT)
    out = (proc.stdout or "") + (proc.stderr or "")
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "パレット実行.log").write_text(f"仮設足場 {title}\n{out}", encoding="utf-8")
    except OSError:
        pass
    head = "完了" if proc.returncode == 0 else f"止まりました（終了コード {proc.returncode}）"
    return proc.returncode, f"{head}\n{summary(out)}"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--kinds":
        print(kinds_json())
        return 0
    code, text = run_action(argv[0])
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
