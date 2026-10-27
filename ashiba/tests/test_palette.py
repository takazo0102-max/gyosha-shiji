"""Tapir パレットのボタン（Phase 10-3）: 入口の中身・要点の抜き出し・置き方."""

import ast
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.palette import ACTIONS, ENTRIES, MARK, entry_source, menu_items, summary

ROOT = Path(__file__).resolve().parents[1]


class TestEntries(unittest.TestCase):
    def test_one_entry_opens_the_palette(self):
        # Tapir の一覧には入口1つ（パレットの窓を開く）。操作はすべて窓のボタン
        # （利用者の指定 2026-10-22: Tapirの足場を一つにパレットとしてまとめて）
        self.assertEqual([(e.file, e.script, e.quiet) for e in ENTRIES], [("足場_パレット.py", "ashiba_palette.py", True)])
        self.assertEqual([a.title for a in ACTIONS], ["配置", "地足場", "解き直し", "区切る", "区切りを戻す", "面の切替", "朝顔の面", "朝顔の範囲", "幅の変更", "階段の位置", "開口", "昇降機", "取り入れ口", "内部足場", "支柱だけ分解",
                                                     "分解を戻す", "3D表示", "平面表示", "条件", "条件の登録", "条件の呼び出し",
                                                     "図面を作る", "ペン", "帳票", "撤去"])
        for a in ACTIONS:
            self.assertTrue((ROOT / "scripts" / a.script).exists(), a.script)
        for e in ENTRIES:
            self.assertTrue((ROOT / "scripts" / e.script).exists(), e.script)
        self.assertEqual(next(a for a in ACTIONS if a.title == "解き直し").args, ("--apply",))

    def test_panel_groups_cover_every_action_once(self):
        from ashiba.palette import PANEL_GROUPS, panel_layout

        titles = [t for _, ts in PANEL_GROUPS for t in ts]
        self.assertEqual(sorted(titles), sorted(a.title for a in ACTIONS))
        self.assertEqual(len(titles), len(set(titles)))
        lay = panel_layout()
        self.assertEqual([g["group"] for g in lay], ["建てる", "直す", "見る・出す"])
        self.assertEqual(lay[0]["actions"][0]["title"], "配置")
        self.assertIn("slab", lay[0]["actions"][0]["when"])
        self.assertTrue(all(a["hint"] for g in lay for a in g["actions"]))     # 指を置くと出る説明

    def test_quiet_entry_does_not_wait_for_a_dialog(self):
        src = entry_source(ENTRIES[0])
        self.assertIn("QUIET = True", src)
        self.assertIn("stdout=subprocess.DEVNULL", src)        # 窓のプロセスに出力を握らせて入口が待たない

    def test_panel_window(self):
        sw = (ROOT / "tapir" / "palette_panel.swift").read_text(encoding="utf-8")
        self.assertIn(".nonactivatingPanel", sw)                 # 押しても Archicad の選択が外れない
        self.assertIn("panel.isFloatingPanel = true", sw)
        self.assertIn('"--kinds"', sw)                           # 選んでいるものを見て★
        self.assertIn('buttons[i].title = (hit ? "★ " : "") + a.title', sw)
        self.assertIn('if a.title == "撤去" {', sw)              # 消す操作は確かめる
        launcher = (ROOT / "scripts" / "ashiba_palette.py").read_text(encoding="utf-8")
        self.assertIn('["swiftc", "-O", str(PANEL), "-o", str(exe)]', launcher)
        self.assertIn("start_new_session=True", launcher)

    def test_run_action_reports_unknown_and_summary(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import palette_run

        code, text = palette_run.run_action("ない操作")
        self.assertEqual(code, 2)
        self.assertTrue(text.startswith("止まりました"))

    def test_titles_from_the_swift_window_are_composed(self):
        """パレットの窓（Swift の Process）は引数を NFD で渡す（「ペ」→「ヘ」＋半濁点）。合成して操作を探す
        （利用者の指摘 2026-10-24: ペンのところができない）."""
        import sys
        import unicodedata
        from unittest import mock

        sys.path.insert(0, str(ROOT / "scripts"))
        import palette_run

        import tempfile

        seen = []
        with mock.patch.object(palette_run, "OUT", Path(tempfile.mkdtemp())), \
                mock.patch.object(palette_run.subprocess, "run",
                               side_effect=lambda cmd, **kw: seen.append(cmd) or mock.Mock(returncode=0, stdout="", stderr="")):
            for title in ("ペン", "条件の呼び出し"):
                code, text = palette_run.run_action(unicodedata.normalize("NFD", title))
                self.assertNotIn("という操作はありません", text, title)
        self.assertTrue(any("pen_colors.py" in " ".join(map(str, c)) for c in seen), seen)

    def test_entry_is_valid_python_with_uv_header_and_port(self):
        for e in ENTRIES:
            src = entry_source(e)
            ast.parse(src)
            self.assertTrue(src.startswith("#!/usr/bin/env python3\n# /// script"))    # uv run --script
            self.assertIn(MARK, src)
            self.assertIn('env["ASHIBA_PORT"] = port', src)          # 窓は ASHIBA_PORT を受け継いで操作に渡す
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


class TestTogglePlan(unittest.TestCase):
    """平面も詳細モード（利用者の指定 2026-10-23）: 詳細 → 精細（実寸）→ 単線."""

    def test_cycle_and_gdl(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from toggle_plan import current_step, next_step

        self.assertEqual(next_step("詳細"), ("精細", False, True))
        self.assertEqual(next_step("精細"), ("単線", True, False))
        self.assertEqual(next_step("単線"), ("詳細", False, False))
        self.assertEqual(current_step({"planReal": True}), "精細")
        root = ROOT / "gdl" / "hsf"
        g2 = (root / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("if mvOk and mvPlan = 3 then", g2)
        self.assertIn("940: ! ---- 平面 実寸", g2)
        self.assertIn('3, "精細（実寸）"', (root / "ashiba_mvo" / "scripts" / "vl.gdl").read_text(encoding="utf-8"))
        # 表示設定の既定（1）は部品の設定に従う（パレットの切替が効く。2026-10-23 実機: 精細にしても変わらなかった）
        self.assertNotIn("if mvOk and (mvPlan = 1", g2)


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
        # コマの高さは gosub 756（出隅の升目を高い方の面の積み方で描くときも同じ規則で回す）
        i = g3.index("756:\t! ---- コマの高さ kz")
        block = g3[i:g3.index("\treturn\n", i)]
        self.assertIn("abs(kzAll[ik] - lv[il] - railMid) < 0.005", block)
        self.assertIn("abs(kzAll[ik] - lv[il] - railTop) < 0.005", block)
        # コマを描く3箇所（本体の支柱・出隅の支柱・外付け階段の建地）はどれも kz を使い、軽量で省かない
        self.assertEqual(g3.count("for ik = 1 to nKz\n") + g3.count("for ik = 1 to nCKz\n"), 3)
        self.assertNotIn("komaPitch > 0 and isLite = 0", g3)

    def test_drawing_views_use_the_drawing_form(self):
        # 断面図・立面図では図面向き（細部を省き、コマを描かない、円柱は12角）。利用者の指定 2026-10-23（案2）
        g3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(
            encoding="utf-8")
        for want in ("if GLOB_CONTEXT = 4 or GLOB_CONTEXT = 24 then isDwg = 1",
                     "if isDwg = 1 and d3 <> 3 and d3 <> 4 then isLite = 1",
                     "if isLite and isDwg = 0 then rN = 6",
                     "if isDwg = 1 then nKz = 0"):
            self.assertIn(want, g3)
        # コマの高さ（gosub 756）は描く前に求め、その中で図面向きはコマを無しにする
        self.assertLess(g3.index("gosub 756"), g3.index("for ik = 1 to nKz\n"))
        i = g3.index("756:\t! ---- コマの高さ kz")
        self.assertIn("if isDwg = 1 then nKz = 0", g3[i:g3.index("\treturn\n", i)])


if __name__ == "__main__":
    unittest.main()


class TestMenu(unittest.TestCase):
    def test_selection_puts_matching_actions_first(self):
        line = [a.title for a in menu_items({"line"})]
        self.assertEqual(line[:8], ["解き直し", "区切る", "区切りを戻す", "面の切替", "朝顔の面", "支柱だけ分解", "分解を戻す",
                                    "3D表示"])
        slab = [a.title for a in menu_items({"slab"})]
        self.assertEqual(slab[:6], ["配置", "地足場", "条件", "図面を作る", "帳票", "撤去"])
        self.assertEqual([a.title for a in menu_items({"member"})][0], "分解を戻す")
        # 何も選んでいないときはペン（図面のペン。2026-10-24）も上に出る
        # 何も選んでいない（平面に目印の線を引いて選んだときも同じ）ときは、線で指す操作が上に出る（2026-10-24）
        self.assertEqual([a.title for a in menu_items(set())][:5], ["区切る", "朝顔の範囲", "幅の変更", "階段の位置", "開口"])
        # どの選択でも全部の操作が一覧にある
        for k in ("line", "slab", "member", "spec", "none"):
            self.assertEqual(len(menu_items({k})), len(ACTIONS))
