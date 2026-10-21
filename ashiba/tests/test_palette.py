"""Tapir パレットのボタン（Phase 10-3）: 入口の中身・要点の抜き出し・置き方."""

import ast
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.palette import ACTIONS, ENTRIES, MARK, entry_source, menu_items, summary

ROOT = Path(__file__).resolve().parents[1]


class TestEntries(unittest.TestCase):
    def test_three_buttons_call_existing_scripts(self):
        # パレットはメニュー＋よく使う3つ。ほかの操作はメニューから（利用者の指定 2026-10-21: まとめて使いやすく）
        self.assertEqual([e.title for e in ENTRIES], ["メニュー", "配置", "解き直し", "3D表示"])
        self.assertEqual([a.title for a in ACTIONS], ["配置", "解き直し", "区切る", "区切りを戻す", "支柱だけ分解",
                                                     "分解を戻す", "3D表示", "条件", "条件の登録", "条件の呼び出し",
                                                     "帳票", "撤去"])
        for a in ACTIONS:
            self.assertTrue((ROOT / "scripts" / a.script).exists(), a.script)
        for e in ENTRIES:
            self.assertTrue((ROOT / "scripts" / e.script).exists(), e.script)
            self.assertTrue(e.file.startswith("足場") and e.file.endswith(".py"))
        self.assertEqual(next(e for e in ENTRIES if e.title == "解き直し").args, ("--apply",))

    def test_entry_is_valid_python_with_uv_header_and_port(self):
        for e in ENTRIES:
            src = entry_source(e)
            ast.parse(src)
            self.assertTrue(src.startswith("#!/usr/bin/env python3\n# /// script"))    # uv run --script
            self.assertIn(MARK, src)
            self.assertIn('env["ASHIBA_PORT"] = port', src)
            self.assertIn(f'SCRIPT = os.path.join(ROOT, "scripts", "{e.script}")', src)
            self.assertIn("_desktop_ok()", src)          # 許可待ちで黙って止まらない

    def test_port_comes_from_env(self):
        tap = (ROOT / "src" / "ashiba" / "tapir_adapter.py").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_PORT = int(os.environ.get("ASHIBA_PORT", "19723")', tap)


class TestSummary(unittest.TestCase):
    def test_picks_key_lines(self):
        out = ("条件の上書き: x\n配布GSMを埋め込みライブラリへ追加: y\n  平面図: レイアウト「A 足場平面図」に 1/100\n"
               "足場ライン 4本・立面図 4面を配置しました\n総合判定: 是正が必要\n  是正: 壁つなぎ 検定比1.136\n"
               "  要確認 6件: 構造 1件\n帳票出力先: /x\n")
        s = summary(out)
        self.assertIn("足場ライン 4本", s)
        self.assertIn("  是正: 壁つなぎ", s)
        self.assertNotIn("配布GSM", s)

    def test_falls_back_and_limits(self):
        self.assertEqual(summary("a\nb\nc"), "a\nb\nc")
        s = summary("\n".join(f"注意: {i}" for i in range(30)), limit=5)
        self.assertEqual(len(s.splitlines()), 5)
        self.assertIn("ほか 26 行", s)


class TestInstall(unittest.TestCase):
    def test_install_only_touches_its_own_links(self):
        src = (ROOT / "scripts" / "install_palette.py").read_text(encoding="utf-8")
        self.assertIn("def _ours(link: Path) -> bool:", src)
        self.assertIn("は別のファイルなので触りません", src)
        self.assertIn('SCRIPTS_DIR = TAPIR_DIR / "custom-scripts"', src)   # パレットは直下しか読まない



class TestToggle3D(unittest.TestCase):
    def test_cycle(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from toggle_3d import next_step

        self.assertEqual(next_step(0), (2, "軽量"))
        self.assertEqual(next_step(2), (3, "線"))
        self.assertEqual(next_step(3), (4, "ブロック"))
        self.assertEqual(next_step(4), (1, "精細"))
        self.assertEqual(next_step(1), (0, "自動"))


class TestBlockMode(unittest.TestCase):
    """3D の「ブロック」表示（参考: smartCON Planner）: 部材を描かずスパン×層の箱."""

    def test_line_and_mvo_know_block_mode(self):
        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf"
        g3 = (root / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("if d3 = 4 then", g3)
        self.assertIn("if mvD = 4 then d3 = 4", g3)
        # ブロックは線表示・部材の描画より前で終わる
        self.assertLess(g3.index("if d3 = 4 then"), g3.index("if lineMode then"))
        mvo = (root / "ashiba_mvo" / "scripts" / "vl.gdl").read_text(encoding="utf-8")
        self.assertIn('4, "ブロック"', mvo)


class TestKomaInLiteMode(unittest.TestCase):
    """軽量でもフックを掛ける高さのコマは描く（自動で軽量になった長い面だけコマが無かった 2026-10-21）."""

    def test_lite_mode_keeps_hook_komas(self):
        g3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(
            encoding="utf-8")
        i = g3.index("! ---- コマ（緊結部）の高さ kz")
        block = g3[i:g3.index("! ---- 支柱（各スパン境界に内外1対）")]
        self.assertIn("abs(kzAll[ik] - lv[il] - railMid) < 0.005", block)
        self.assertIn("abs(kzAll[ik] - lv[il] - railTop) < 0.005", block)
        # コマを描く3箇所（本体の支柱・出隅の支柱・外付け階段の建地）はどれも kz を使い、軽量で省かない
        self.assertEqual(g3.count("for ik = 1 to nKz\n"), 3)
        self.assertNotIn("komaPitch > 0 and isLite = 0", g3)


if __name__ == "__main__":
    unittest.main()


class TestMenu(unittest.TestCase):
    def test_selection_puts_matching_actions_first(self):
        line = [a.title for a in menu_items({"line"})]
        self.assertEqual(line[:6], ["解き直し", "区切る", "区切りを戻す", "支柱だけ分解", "分解を戻す", "3D表示"])
        slab = [a.title for a in menu_items({"slab"})]
        self.assertEqual(slab[:4], ["配置", "条件", "帳票", "撤去"])
        self.assertEqual([a.title for a in menu_items({"member"})][0], "分解を戻す")
        self.assertEqual([a.title for a in menu_items(set())][:3], ["3D表示", "条件", "帳票"])
        # どの選択でも全部の操作が一覧にある
        for k in ("line", "slab", "member", "spec", "none"):
            self.assertEqual(len(menu_items({k})), len(ACTIONS))
