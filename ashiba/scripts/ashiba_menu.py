"""仮設足場のメニュー（パレットのボタン「メニュー」）.

利用者の指定（2026-10-21）「タピアーコマンドをまとめて使いやすいものにして」。パレットのボタンが12個に増え、
どれをいつ押すのか分かりにくかった。メニューは選んでいるものを見て、合う操作を上に（★）並べた一覧を出し、
選んだ操作を実行する:
  躯体スラブ        → 配置・条件・帳票・撤去
  足場ライン        → 解き直し・区切る・区切りを戻す・支柱だけ分解・分解を戻す・3D表示
  分解した支柱      → 分解を戻す
  足場条件の部品    → 条件の登録・条件の呼び出し
  何も選んでいない  → 3D表示・条件・帳票
残りの操作も一覧の下にある。選んだ操作の出力はそのまま出す（パレットの入口が要点をダイアログにする）。

使い方: python3 scripts/ashiba_menu.py            # 一覧を出して選ぶ
        ASHIBA_MENU_CHOICE=区切る python3 scripts/ashiba_menu.py   # 一覧を出さずに実行（試験用）
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.palette import ACTIONS, menu_items  # noqa: E402

KIND_LABEL = {"slab": "躯体スラブ", "line": "足場", "member": "分解した支柱", "spec": "足場条件の部品"}


def selection_kinds() -> tuple[set, str]:
    """選んでいるものの種類（slab・line・member・spec）と、一覧の上に出す説明."""
    from ashiba.tapir_adapter import ArchicadClient, TapirError, is_ashiba_part

    try:
        c = ArchicadClient(timeout=20)
        sel = c.get_selected_elements()
        if not sel:
            return set(), "何も選んでいません"
        kinds: dict[str, int] = {}
        for e, d in zip(sel, c.get_details(sel)):
            typ = str(d.get("type") or "")
            dd = d.get("details") or {}
            name = (dd.get("libPart") or {}).get("name", "")
            if is_ashiba_part(name, ("ashiba_line",)):
                k = "line"
            elif is_ashiba_part(name, ("ashiba_member",)):
                k = "member"
            elif is_ashiba_part(name, ("ashiba_spec",)):
                k = "spec"
            elif typ == "Slab":
                k = "slab"
            else:
                continue
            kinds[k] = kinds.get(k, 0) + 1
        if not kinds:
            return set(), f"選んでいるもの {len(sel)}個（足場の操作に関係しないもの）"
        return set(kinds), "選んでいるもの: " + "・".join(f"{KIND_LABEL[k]}{n}個" for k, n in kinds.items())
    except (TapirError, OSError) as e:
        return set(), f"Archicad の選択を読めませんでした（{e}）"


def choose(items, prompt: str) -> str | None:
    """一覧から1つ選ぶ（osascript の choose from list）。取り消しなら None."""
    labels = [("★ " if star else "　 ") + a.title + "　― " + a.hint.split("。")[0] for a, star in items]
    q = lambda t: '"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = ("choose from list {" + ", ".join(q(t) for t in labels) + "} with title " + q("仮設足場 メニュー")
              + " with prompt " + q(prompt + "\n★ は今の選択に合う操作") + " default items {" + q(labels[0]) + "}"
              + " OK button name " + q("実行") + " cancel button name " + q("やめる"))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out or out == "false":
        return None
    for (a, _), lab in zip(items, labels):
        if out == lab:
            return a.title
    return None


def main(argv=None) -> int:
    kinds, desc = selection_kinds()
    ordered = menu_items(kinds)
    items = [(a, bool(set(a.when) & (kinds or {"none"}))) for a in ordered]
    title = os.environ.get("ASHIBA_MENU_CHOICE") or choose(items, desc)
    if not title:
        print("メニュー: やめました")
        return 0
    act = next((a for a in ACTIONS if a.title == title), None)
    if act is None:
        print(f"エラー: メニューに「{title}」はありません（" + "・".join(a.title for a in ACTIONS) + "）")
        return 2
    print(f"メニュー: {act.title}（{desc}）")
    py = sys.executable
    proc = subprocess.run([py, str(ROOT / "scripts" / act.script)] + list(act.args), cwd=ROOT,
                          capture_output=True, text=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    sys.stdout.write(proc.stdout or "")
    sys.stdout.write(proc.stderr or "")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
