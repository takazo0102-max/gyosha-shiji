"""Tapir パレットの入口（Phase 10-3）: 「足場_パレット」1つ。押すと仮設足場のパレット（浮いた小窓）が開く.

利用者の指定（2026-10-22）「Tapirの足場を一つにパレットとしてまとめて、使いやすいように工夫して」。Tapir の一覧には
入口を1つだけ置き、すべての操作はパレットの窓のボタンに並べる（組: 建てる・直す・見る／出す）。窓は Archicad の前に
浮いたまま残り、押しても Archicad の選択は外れない。選んでいるもの（躯体スラブ・足場・分解した支柱・足場条件の部品）
を数秒ごとに見て、合う操作のボタンに★を付ける。結果の要点は窓の下に出す（ダイアログを出さない）。
窓は tapir/palette_panel.swift（AppKit。tkinter は使えない Python で、osascript の JavaScript は窓の
ボタンを受ける仕組みが止まった）。初めて開くときに swiftc で作る。

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
    when: tuple = ()   # メニューで上に出す選択の種類（slab・line・member・spec・none）
    quiet: bool = False   # 入口が終わりのダイアログを出さない（パレットの窓を開くだけの入口）


# パレットのすべての操作。利用者の指定（2026-10-21）「タピアーコマンドをまとめて使いやすいものに」: パレットには
# 「メニュー」と、よく使う3つ（配置・解き直し・3D表示）だけを並べ、ほかはメニューから選ぶ。メニューは選んでいる
# もの（躯体スラブ・足場ライン・分解した支柱・足場条件の部品・何も無し）に合う操作を上に出す（scripts/ashiba_menu.py）
ACTIONS: tuple[Entry, ...] = (
    Entry("足場_配置.py", "run_from_archicad.py", (), "配置",
          "躯体スラブを選んでから押す。条件の窓で足場の種類・系列・幅・手すり・階段などを選んで「配置」", ("slab",)),
    Entry("足場_解き直し.py", "read_back_spans.py", ("--apply",), "解き直し",
          "スパン・階段室・ステージ・昇降機を平面で、足場の高さを3Dで引いたあと、"
          "壁つなぎの部品を動かした・消した・コピーしたあとに押す", ("line",)),
    Entry("足場_区切る.py", "split_line.py", (), "区切る",
          "3Dで足場を選び、上端の縦のつまみ（次の支柱で区切る）か始点の横のつまみ（次の作業床で区切る）を"
          "引いてから押す。そこから先を別の部品にする", ("line",)),
    Entry("足場_区切りを戻す.py", "split_line.py", ("--undo",), "区切りを戻す",
          "区切った足場の部品を選んでから押す。その面の部品を1つに戻す", ("line",)),
    Entry("足場_面の切替.py", "switch_face_form.py", (), "面の切替",
          "足場ライン（区切った部品・複数の面でもよい）を選んでから押す。選んだ面を別の種類の足場"
          "（本足場・一側・ブラケット（支柱・単管）・単管抱き・単管本足場・枠組）に切り替えて置き直す", ("line",)),
    Entry("足場_朝顔の面.py", "asagao_faces.py", (), "朝顔の面",
          "朝顔の要る面（道路・隣地・人の通る側）の足場ラインを選んでから押す。選んだ面に朝顔を付ける・外す"
          "（全部の面に戻すこともできる）して置き直す", ("line",)),
    Entry("足場_支柱だけ分解.py", "explode_line.py", (), "支柱だけ分解",
          "足場ライン（区切った部品でもよい）を選んでから押す。支柱（枠組は建枠）を1本ずつの部品にする", ("line",)),
    Entry("足場_分解を戻す.py", "explode_line.py", ("--undo",), "分解を戻す",
          "分解した足場ライン（または支柱）を選んでから押す。支柱を消して足場ラインで描く", ("line", "member")),
    Entry("足場_3D表示.py", "toggle_3d.py", (), "3D表示",
          "押すたびに足場の3Dを 自動→軽量→線→ブロック→精細 と切り替える（重いときは軽量か線、取り合いはブロック）",
          ("line", "none")),
    Entry("足場_平面表示.py", "toggle_plan.py", (), "平面表示",
          "押すたびに足場の平面を 詳細→精細（実寸）→単線 と切り替える（精細は支柱・布材・踏板・幅木を太さ・幅どおり）",
          ("line", "none")),
    Entry("足場_条件.py", "spec_form_run.py", (), "条件",
          "条件の窓を開く（足場の種類・系列・幅・手すり・階段・朝顔・養生・高さ・立面断面）。「保存して配置」で置き直す。"
          "細かい条件（離れ・ネット・部材編集）は足場条件の部品を選んで ⌘T", ("slab", "none")),
    Entry("足場_条件の登録.py", "spec_preset.py", ("save",), "条件の登録",
          "足場条件の部品の「登録名」に名前を書いてから押す。条件（建物ごとの値を除く）を控える", ("spec",)),
    Entry("足場_条件の呼び出し.py", "spec_preset.py", ("load",), "条件の呼び出し",
          "別の建物の足場条件の部品の「登録名」に登録した名前を書いてから押し、「配置」で置き直す", ("spec",)),
    Entry("足場_帳票.py", "open_outputs.py", (), "帳票",
          "帳票の出力先を開き、最新の割付レポートを開く", ("none", "slab")),
    Entry("足場_撤去.py", "remove_from_archicad.py", (), "撤去",
          "躯体スラブを選んでから押す。足場部品と立面・平面・詳細図のレイアウトを消す", ("slab",)),
)


def _action(title: str) -> Entry:
    return next(a for a in ACTIONS if a.title == title)


# パレットの窓の組（ACTIONS のすべてをどれか1つの組に）
PANEL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("建てる", ("配置", "条件", "条件の登録", "条件の呼び出し")),
    ("直す", ("解き直し", "区切る", "区切りを戻す", "面の切替", "朝顔の面", "支柱だけ分解", "分解を戻す")),
    ("見る・出す", ("3D表示", "平面表示", "帳票", "撤去")),
)


def panel_layout() -> list[dict]:
    """パレットの窓に渡す並び [{group, actions: [{title, hint, when}]}]."""
    return [{"group": g, "actions": [{"title": a.title, "hint": a.hint, "when": list(a.when)}
                                     for a in (_action(t) for t in titles)]}
            for g, titles in PANEL_GROUPS]


# Tapir の一覧に置く入口は1つ（パレットの窓を開く）。以前はメニュー＋よく使う3つの4つだった
ENTRIES: tuple[Entry, ...] = (
    Entry("足場_パレット.py", "ashiba_palette.py", (), "パレット",
          "仮設足場のパレットの窓を開く。窓のボタンで配置・解き直し・区切る・3D表示などを実行する"
          "（★は今の選択に合う操作）", quiet=True),
)


def menu_items(kinds: set) -> list[Entry]:
    """メニューの並び: 選んでいるものに合う操作を先に、残りはその後（並びは ACTIONS の順）."""
    kinds = set(kinds) or {"none"}
    hit = [a for a in ACTIONS if set(a.when) & kinds]
    return hit + [a for a in ACTIONS if a not in hit]


def summary(output: str, limit: int = 14) -> str:
    """実行の出力から、ダイアログに出す要点の行（keys で始まる行）。無ければ最後の数行."""
    keys = ("足場ライン", "総合判定", "  是正", "  要確認", "  表題欄", "  詳細図:", "  平面図:", "  立面:", "  PDF:",
            "書き込み", "配置時と同じ", "撤去", "足場部品", "立面図（断面", "注意:", "エラー", "[ashiba]",
            "足場条件", "帳票", "建物が分かりません", "この建物の", "配置:", "条件:", "朝顔の面",
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
QUIET = {quiet}
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
    if QUIET:                                            # 窓を開くだけ（結果は窓に出る）
        return subprocess.run([py, SCRIPT] + list(ARGS), env=env, cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
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
                                 quiet=bool(e.quiet),
                                 summary_src=inspect.getsource(summary))
