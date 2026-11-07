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
        self.assertEqual([(e.file, e.script, e.quiet) for e in ENTRIES], [("仮設_パレット.py", "ashiba_palette.py", True)])
        self.assertEqual([a.title for a in ACTIONS], ["配置", "地足場", "解き直し", "区切る", "区切りを戻す", "面の切替", "朝顔の面", "朝顔の範囲", "幅の変更", "階段の位置", "開口", "昇降機", "手動配置", "箱を置く", "箱を足場に", "山留め壁", "切梁・腹起し", "切梁上の足場", "外周の足場", "山留めの手すり", "根切り図", "根切り図を更新", "根切り・山留計画図", "仮囲い", "クレーン", "タワークレーン", "バックホウ", "クローラクレーン", "ポンプ車", "生コン車", "ダンプ", "高所作業車", "垂直昇降", "杭打機", "アースドリル", "全周回転機", "解体機", "圧入機", "バイブロ", "平ボディ", "クレーン付きトラック", "セルフローダ", "低床トレーラー", "平床トレーラー", "ポールトレーラー", "車両の軌跡", "クレーン操作", "鉄骨建て方", "建て方検討図", "鉄骨の仮設材", "鉄骨の次のステップ", "鉄骨の前のステップ", "鉄骨のステップを戻す", "重機をステップへ", "揚重判定", "一括揚重判定", "吊荷削除", "ブームの干渉", "判定の色を消す", "敷鉄板", "乗入れ構台", "構台 3mを1列", "構台の検定", "場内通路", "場内通路（トレーラー）", "仮設建物", "仮設事務所 2階", "仮設トイレ", "仮設建物の検定", "仮設電気・給排水", "工程表・仮設の金額", "工程の模型を作る", "次の工程", "前の工程", "工程の模型を戻す", "開口養生", "床の縁の手すり", "歩行者通路の柵", "防護柵", "親綱", "単管でつなぐ", "火打ちの単管", "単管に壁つなぎ", "型枠", "支保工足場", "支保工を戻す", "型枠計画図", "型枠の撤去", "取り入れ口", "内部足場", "仮設通路", "くさび1点で部材", "くさび1点の部材を消す", "支柱だけ分解",
                                                     "分解を戻す", "3D表示", "平面表示", "条件", "条件の登録", "条件の呼び出し",
                                                     "図面を作る", "総合仮設計画図", "ペン", "帳票", "撤去"])
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
        self.assertEqual([g["group"] for g in lay], ["足場を建てる", "足場を直す", "足場を見る・出す", "型枠・支保工", "山留め・構台", "鉄骨建て方",
                                                     "揚重・敷鉄板", "重機", "搬入車両", "場内・仮設建物", "工程表・工程の模型", "墜落・落下防止"])
        self.assertLessEqual(max(len(g["actions"]) for g in lay), 14)       # 組ごとに出すので窓が縦に長くならない
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
        self.assertIn("NSPopUpButton", sw)                       # 組を選んでその組のボタンだけ（利用者の指定 2026-11-01: パレットを整理して）
        self.assertIn('"AshibaPaletteGroup"', sw)                # 最後に開いた組を次も
        self.assertIn('if a.title == "撤去" || a.title == "型枠の撤去" {', sw)   # 消す操作は確かめる（型枠の撤去も）
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
            self.assertIn(".returncode == 0", src)       # 断られたときも（ls はすぐ失敗する: 2026-11-06 パレットが黙って開かなかった）

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

    def test_keeps_last_line(self):
        """最後の行（結び）は見出しに合わなくても出す（区切るの「戻すときは「区切りを戻す」」が抜けていた）."""
        out = "区切る: 南面の始点から 5487 の支柱で区切ります\n4BE9FD19: 2つに区切りました\n計 1個の部品を足しました。戻すときは「区切りを戻す」\n"
        self.assertTrue(summary(out).endswith("戻すときは「区切りを戻す」"))
        self.assertEqual(summary("足場ライン 4本\n帳票出力先: x\n").count("帳票出力先"), 1)

    def test_indented_warnings(self):
        """字下げした行でも 要確認・NG は出す（ほかの字下げの行は出さない）."""
        out = "  親綱1: 12.0m・3スパン・落差 4.0m\n  親綱2: 8.0m・2スパン・落差 9.0m・要確認 落差\n親綱: 2本の梁に置きました（発注表: 親綱.md）\n"
        s = summary(out)
        self.assertIn("要確認 落差", s)
        self.assertNotIn("親綱1", s)

    def test_falls_back_and_limits(self):
        self.assertEqual(summary("a\nb\nc"), "a\nb\nc")
        s = summary("\n".join(f"注意: {i}" for i in range(30)), limit=5)
        self.assertEqual(len(s.splitlines()), 5)
        self.assertIn("ほか 26 行", s)


class TestInstall(unittest.TestCase):
    def test_committed_entry_is_current(self):
        """リポジトリの入口（tapir/palette/仮設_パレット.py）は entry_source と同じ（要点の関数を埋め込むので、
        summary を直したら作り直す。古いままで「足場の部品」「最後の行」が窓に出なかった 2026-11-05）."""
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        from ashiba.palette import ENTRIES, entry_source
        for e in ENTRIES:
            self.assertEqual((ROOT / "tapir" / "palette" / e.file).read_text(encoding="utf-8"), entry_source(e), e.file)

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
        self.assertEqual(slab[:8], ["配置", "地足場", "型枠", "支保工足場", "支保工を戻す", "型枠計画図", "条件", "図面を作る"])   # スラブの型枠も（2026-10-31）
        self.assertEqual([a.title for a in menu_items({"member"})][0], "分解を戻す")
        # 何も選んでいないときはペン（図面のペン。2026-10-24）も上に出る
        # 何も選んでいない（平面に目印の線を引いて選んだときも同じ）ときは、線で指す操作が上に出る（2026-10-24）
        self.assertEqual([a.title for a in menu_items(set())][:5], ["区切る", "朝顔の範囲", "幅の変更", "階段の位置", "開口"])
        # どの選択でも全部の操作が一覧にある
        for k in ("line", "slab", "member", "spec", "none"):
            self.assertEqual(len(menu_items({k})), len(ACTIONS))


class TestMachineKind(unittest.TestCase):
    """クレーン・重機を選ぶとパレットが「重機・クレーン」と読む（利用者の指定 2026-11-07「重機が選べなかった」）."""

    def test_crane_is_a_machine(self):
        import sys
        from pathlib import Path
        from unittest import mock

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import ashiba_menu

        sel = [("a", "Object", "ashiba_crane_a38af37f"), ("b", "Object", "ashiba_machine_acb66498"), ("c", "Object", "ashiba_tower"),
               ("d", "Object", "ashiba_sgear_b3af89f2")]

        class C:
            def __init__(self, timeout=20):
                pass

            def get_selected_elements(self):
                return [{"elementId": {"guid": g}} for g, _t, _n in sel]

            def get_details(self, es):
                return [{"type": t, "details": {"libPart": {"name": n}}} for _g, t, n in sel]

        with mock.patch("ashiba.tapir_adapter.ArchicadClient", C):
            kinds, desc = ashiba_menu.selection_kinds()
        self.assertEqual(kinds, {"machine"})
        self.assertIn("重機・クレーン3個", desc)

    def test_machine_buttons_are_marked(self):
        from ashiba.palette import ACTIONS

        hit = {a.title for a in ACTIONS if "machine" in a.when}
        self.assertTrue({"重機をステップへ", "建て方検討図", "揚重判定", "一括揚重判定", "クレーン操作"} <= hit)
