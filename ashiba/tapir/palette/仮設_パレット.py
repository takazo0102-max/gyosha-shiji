#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
# -*- coding: utf-8 -*-
# ashiba-palette-entry
"""仮設足場 パレット

Tapir パレットから呼ぶ入口（python3 scripts/install_palette.py で作り直す。手で直さない）。
仮設パレットの窓を開く。窓のボタンで配置・解き直し・区切る・3D表示などを実行する（★は今の選択に合う操作）
本体は <ashiba>/scripts/ashiba_palette.py。Tapir が付ける --port は ASHIBA_PORT に移して本体へ渡す。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))           # <ashiba>/tapir/palette（リンクをたどる）
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "ashiba_palette.py")
ARGS = ()
TITLE = "仮設足場 パレット"
QUIET = True
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "ashiba_out")


def summary(output: str, limit: int = 14) -> str:
    """実行の出力から、ダイアログに出す要点の行（keys で始まる行）。無ければ最後の数行."""
    keys = ("足場ライン", "足場の部品", "総合判定", "  是正", "  要確認", "  表題欄", "  詳細図:", "  平面図:", "  立面:", "  PDF:",
            "書き込み", "配置時と同じ", "撤去", "足場部品", "立面図（断面", "注意:", "エラー", "[ashiba]",
            "足場条件", "帳票", "建物が分かりません", "この建物の", "配置:", "条件:", "朝顔の面", "朝顔の範囲", "幅の変更", "階段の位置", "図面を作る", "  図面:", "取り入れ口", "昇降機", "内部足場", "仮設通路", "  検証", "地足場", "手動配置", "箱を置く", "箱を足場に", "型枠", "  面の切替", "  上段（途中の屋根から）", "  置き方",
            "  計算書", "  計画届", "TapirError", "TapirTimeout", "Traceback")
    import re

    # 窓に出しても役に立たない行（条件ファイルの場所・部品の読み込み）は除き、長い道のりはファイル名だけに
    # （1行目が「条件の上書き: /private/…」になり肝心の「重機: 1台」が埋もれた 2026-11-05）
    noise = ("条件の上書き", "配布GSMを埋め込みライブラリへ追加", "条件の上書きファイルは無し")
    lines = [re.sub(r"(/[^\s/（）()]+)+/([^\s/（）()]+)", r"\2", ln.rstrip()) for ln in output.splitlines()
             if ln.strip() and not ln.lstrip().startswith(noise)]
    # 決めた見出しの行に加えて、行頭の「名前: …」の結果の行も（根切り図などで「帳票:」の行だけが出て、肝心の
    # 「根切り図: 根切り1 掘削 150m²…」が出ていなかった 2026-11-05）
    top = re.compile(r"^[^\s:：（(]{1,24}[:：] ")
    picked = [ln for ln in lines if ln.startswith(keys) or ln.lstrip().startswith(keys) or top.match(ln)]
    if not picked:
        picked = lines[-6:]
    elif lines and lines[-1] not in picked:
        # 最後の行はたいてい結びなので足す（区切るで「区切る: …」の行だけになり、「計 1個の部品を足しました。…戻すときは
        # 「区切りを戻す」」が出なくなった 2026-11-05）
        picked.append(lines[-1])
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
    if QUIET:                                            # 窓を開くだけ（結果は窓に出る）
        return subprocess.run([py, SCRIPT] + list(ARGS), env=env, cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
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
