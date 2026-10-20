"""Tapir パレットのボタン（Phase 10-3）: 「配置」「解き直し」「撤去」「3D表示」「条件」「帳票」「条件の登録」「条件の呼び出し」.

Tapir のパレットは ~/Documents/Tapir の下のフォルダにある .py を一覧に出し、
`uv run --script ファイル --port 番号` で起動する（配筋ツールで確かめた仕組み。Tapir は
~/Documents/Tapir の下のフォルダを全部読む）。配筋ツールは custom-scripts を使っているので、
足場は別のフォルダ「仮設足場」にリンクして並べ、配筋ツールのファイルには触らない。

入口は小さな .py で、本体（scripts/*.py）は写さない（写すと直したときに2つの版ができる）。
パレットは標準出力を見せないので、終わったら要点（配置の本数・総合判定・是正・要確認・エラー）を
ダイアログで出し、割付レポートを開けるようにする。全文は ashiba_out/パレット実行.log に残す。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

FOLDER_NAME = "仮設足場"          # ~/Documents/Tapir/仮設足場 → <ashiba>/tapir/palette
MARK = "# ashiba-palette-entry"   # install が作った入口の印（印の無いファイルには触らない）


@dataclass(frozen=True)
class Entry:
    file: str          # パレットに出る名前（.py）
    script: str        # scripts/ の下の本体
    args: tuple = ()
    title: str = ""
    hint: str = ""     # ダイアログの先頭に出す一言


ENTRIES: tuple[Entry, ...] = (
    Entry("足場1_配置.py", "run_from_archicad.py", (), "配置",
          "躯体スラブを選んでから押す。条件は「足場条件」部品の設定で変える"),
    Entry("足場2_解き直し.py", "read_back_spans.py", ("--apply",), "解き直し",
          "スパン・階段室・ステージ・昇降機を平面で、足場の高さを3Dで引いたあと、"
          "壁つなぎの部品を動かした・消した・コピーしたあとに押す"),
    Entry("足場3_撤去.py", "remove_from_archicad.py", (), "撤去",
          "躯体スラブを選んでから押す。足場部品と立面・平面・詳細図のレイアウトを消す"),
    Entry("足場4_3D表示.py", "toggle_3d.py", (), "3D表示",
          "押すたびに足場の3Dを 自動→軽量→線→精細 と切り替える（重いときは軽量か線）"),
    Entry("足場5_条件.py", "select_spec.py", (), "条件",
          "この建物の足場条件の部品を選ぶ。⌘T で幅・手すり・階段・ネット・養生材を変えて「配置」"),
    Entry("足場6_帳票.py", "open_outputs.py", (), "帳票",
          "帳票の出力先を開き、最新の割付レポートを開く"),
    Entry("足場7_条件の登録.py", "spec_preset.py", ("save",), "条件の登録",
          "足場条件の部品の「登録名」に名前を書いてから押す。条件（建物ごとの値を除く）を控える"),
    Entry("足場8_条件の呼び出し.py", "spec_preset.py", ("load",), "条件の呼び出し",
          "別の建物の足場条件の部品の「登録名」に登録した名前を書いてから押し、「配置」で置き直す"),
)

def summary(output: str, limit: int = 14) -> str:
    """実行の出力から、ダイアログに出す要点の行（keys で始まる行）。無ければ最後の数行."""
    keys = ("足場ライン", "総合判定", "  是正", "  要確認", "  表題欄", "  詳細図:", "  平面図:", "  立面:", "  PDF:",
            "書き込み", "配置時と同じ", "撤去", "足場部品", "立面図（断面", "注意:", "エラー", "[ashiba]",
            "足場条件", "帳票", "建物が分かりません", "この建物の",
            "TapirError", "TapirTimeout", "Traceback")
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    picked = [ln for ln in lines if ln.startswith(keys) or ln.lstrip().startswith(keys)]
    if not picked:
        picked = lines[-6:]
    if len(picked) > limit:
        picked = picked[:limit - 1] + [f"…ほか {len(picked) - limit + 1} 行（ashiba_out/パレット実行.log）"]
    return "\n".join(picked)


ENTRY_TEMPLATE = '''#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
# -*- coding: utf-8 -*-
{mark}
"""仮設足場 {title}

Tapir パレットから呼ぶ入口（python3 scripts/install_palette.py で作り直す。手で直さない）。
{hint}
本体は <ashiba>/scripts/{script}。Tapir が付ける --port は ASHIBA_PORT に移して本体へ渡す。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))           # <ashiba>/tapir/palette（リンクをたどる）
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "{script}")
ARGS = {args!r}
TITLE = "仮設足場 {title}"
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "ashiba_out")


{summary_src}

def _port():
    a = sys.argv[1:]
    for i, v in enumerate(a):
        if v == "--port" and i + 1 < len(a):
            return a[i + 1]
        if v.startswith("--port="):
            return v.split("=", 1)[1]
    return ""


def _dialog(text, with_report):
    text = text.replace("\\\\", "\\\\\\\\").replace('"', '\\\\"')
    buttons = '{{"割付レポートを開く", "OK"}}' if with_report else '{{"OK"}}'
    script = 'display dialog "' + text + '" with title "' + TITLE + '" buttons ' + buttons + ' default button "OK"'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        # 画面を持たないプロセスからは出せないことがある。理由をログに足す
        try:
            with open(os.path.join(OUT, "パレット実行.log"), "a", encoding="utf-8") as f:
                f.write("\\n[ダイアログを出せませんでした] " + (r.stderr or "").strip() + "\\n")
        except OSError:
            pass
    return "割付レポートを開く" in (r.stdout or "")


DESKTOP_HELP = ("Archicad からデスクトップの ashiba_out を読めません（macOS の許可待ち）。\\n\\n"
                "システム設定 → プライバシーとセキュリティ → ファイルとフォルダ → Archicad で\\n"
                "「デスクトップフォルダ」をオンにしてから、もう一度押してください。\\n"
                "（項目が無ければ Archicad を再起動すると許可を求める窓が出ます）")


def _desktop_ok():
    """デスクトップを読めるか（許可待ちだと黙って止まるので、別プロセスで5秒だけ試す）."""
    try:
        subprocess.run(["/bin/ls", os.path.dirname(OUT)], capture_output=True, timeout=5)
        return True
    except subprocess.TimeoutExpired:
        return False


def main():
    if not _desktop_ok():
        if os.environ.get("ASHIBA_PALETTE_NODIALOG"):
            print(DESKTOP_HELP)
        else:
            _dialog(DESKTOP_HELP, False)
        return 3
    py = "/usr/local/bin/python3.13" if os.path.exists("/usr/local/bin/python3.13") else sys.executable
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    port = _port()
    if port:
        env["ASHIBA_PORT"] = port
    proc = subprocess.run([py, SCRIPT] + list(ARGS), capture_output=True, text=True, env=env, cwd=ROOT)
    out = (proc.stdout or "") + (proc.stderr or "")
    try:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "パレット実行.log"), "w", encoding="utf-8") as f:
            f.write(TITLE + "\\n" + out)
    except OSError:
        pass
    head = "完了" if proc.returncode == 0 else "止まりました（終了コード " + str(proc.returncode) + "）"
    reports = sorted((os.path.join(OUT, n) for n in os.listdir(OUT) if n.endswith("_割付レポート.md")),
                     key=os.path.getmtime) if os.path.isdir(OUT) else []
    text = head + "\\n\\n" + summary(out)
    if os.environ.get("ASHIBA_PALETTE_NODIALOG"):        # 試験用: ダイアログを出さずに要点を出す
        print(text)
        return proc.returncode
    if _dialog(text, bool(reports)) and reports:
        subprocess.run(["open", reports[-1]])
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
'''


def entry_source(e: Entry) -> str:
    """入口ファイルの中身（要点の関数は summary をそのまま埋め込む）."""
    return ENTRY_TEMPLATE.format(mark=MARK, title=e.title, hint=e.hint, script=e.script, args=tuple(e.args),
                                 summary_src=inspect.getsource(summary))
