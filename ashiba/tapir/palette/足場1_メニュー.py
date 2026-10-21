#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
# -*- coding: utf-8 -*-
# ashiba-palette-entry
"""仮設足場 メニュー

Tapir パレットから呼ぶ入口（python3 scripts/install_palette.py で作り直す。手で直さない）。
選んでいるもの（躯体スラブ・足場・分解した支柱・足場条件の部品）に合う操作を上に出す。選んで「実行」
本体は <ashiba>/scripts/ashiba_menu.py。Tapir が付ける --port は ASHIBA_PORT に移して本体へ渡す。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))           # <ashiba>/tapir/palette（リンクをたどる）
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "ashiba_menu.py")
ARGS = ()
TITLE = "仮設足場 メニュー"
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "ashiba_out")


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


def _port():
    a = sys.argv[1:]
    for i, v in enumerate(a):
        if v == "--port" and i + 1 < len(a):
            return a[i + 1]
        if v.startswith("--port="):
            return v.split("=", 1)[1]
    return ""


def _dialog(text, with_report):
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    buttons = '{"割付レポートを開く", "OK"}' if with_report else '{"OK"}'
    script = 'display dialog "' + text + '" with title "' + TITLE + '" buttons ' + buttons + ' default button "OK"'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        # 画面を持たないプロセスからは出せないことがある。理由をログに足す
        try:
            with open(os.path.join(OUT, "パレット実行.log"), "a", encoding="utf-8") as f:
                f.write("\n[ダイアログを出せませんでした] " + (r.stderr or "").strip() + "\n")
        except OSError:
            pass
    return "割付レポートを開く" in (r.stdout or "")


DESKTOP_HELP = ("Archicad からデスクトップの ashiba_out を読めません（macOS の許可待ち）。\n\n"
                "システム設定 → プライバシーとセキュリティ → ファイルとフォルダ → Archicad で\n"
                "「デスクトップフォルダ」をオンにしてから、もう一度押してください。\n"
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
            f.write(TITLE + "\n" + out)
    except OSError:
        pass
    head = "完了" if proc.returncode == 0 else "止まりました（終了コード " + str(proc.returncode) + "）"
    reports = sorted((os.path.join(OUT, n) for n in os.listdir(OUT) if n.endswith("_割付レポート.md")),
                     key=os.path.getmtime) if os.path.isdir(OUT) else []
    text = head + "\n\n" + summary(out)
    if os.environ.get("ASHIBA_PALETTE_NODIALOG"):        # 試験用: ダイアログを出さずに要点を出す
        print(text)
        return proc.returncode
    if _dialog(text, bool(reports)) and reports:
        subprocess.run(["open", reports[-1]])
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
