"""Tapir パレットのボタン（Phase 10-3）: 入口の中身・要点の抜き出し・置き方."""

import ast
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.palette import ENTRIES, MARK, entry_source, summary

ROOT = Path(__file__).resolve().parents[1]


class TestEntries(unittest.TestCase):
    def test_three_buttons_call_existing_scripts(self):
        self.assertEqual([e.title for e in ENTRIES], ["配置", "解き直し", "撤去", "3D表示", "条件", "帳票"])
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


if __name__ == "__main__":
    unittest.main()


class TestToggle3D(unittest.TestCase):
    def test_cycle(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from toggle_3d import next_step

        self.assertEqual(next_step(0), (2, "軽量"))
        self.assertEqual(next_step(2), (3, "線"))
        self.assertEqual(next_step(3), (1, "精細"))
        self.assertEqual(next_step(1), (0, "自動"))
