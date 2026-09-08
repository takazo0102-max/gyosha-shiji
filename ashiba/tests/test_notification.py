import datetime as dt
import re
import tempfile
import unittest
import xml.dom.minidom as minidom
import zipfile
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import run_all_checks
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.notification import (
    NotificationInfo,
    notification_required,
    scaffold_total_length_m,
    write_notification_xlsx,
)
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.structural import run_structural
from ashiba.xlsx_writer import Workbook, _col_name

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def assert_wellformed(data: bytes) -> None:
    """自作ライタが出力したXMLの妥当性を確認する.

    xlsx_writer は DTD も外部実体も出力しない。それを不変条件として先に検査してから
    パースするので、XXE・billion laughs の入口を作らない（外部依存を足さずに済む）。
    """
    head = data[:512].lstrip()
    assert b"<!DOCTYPE" not in head and b"<!ENTITY" not in data, "DTD/実体宣言が混入している"
    minidom.parseString(data)


def make_model(period_days=90, height=16300):
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(period_days=period_days), building_height_mm=16000,
    )


class TestXlsxWriter(unittest.TestCase):
    def test_column_names(self):
        self.assertEqual(_col_name(0), "A")
        self.assertEqual(_col_name(25), "Z")
        self.assertEqual(_col_name(26), "AA")
        self.assertEqual(_col_name(27), "AB")

    def test_writes_valid_xlsx(self):
        wb = Workbook()
        s = wb.sheet("テスト")
        s.add_title("タイトル")
        s.add_header(["A列", "B列"])
        s.add(["文字", 123])
        s.add(["小数", 1.5])
        s.set_width(0, 20)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.xlsx"
            wb.save(p)
            z = zipfile.ZipFile(p)
            self.assertIsNone(z.testzip())
            for n in z.namelist():
                if n.endswith((".xml", ".rels")):
                    assert_wellformed(z.read(n))
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("<v>123</v>", sheet)
            self.assertIn("タイトル", sheet)

    def test_escapes_xml_special_chars(self):
        """整形式なだけでは足りない。値が落ちても整形式にはなる."""
        text = "<&>\"危険' 100 > 50"
        wb = Workbook()
        wb.sheet("s").add([text])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.xlsx"
            wb.save(p)
            z = zipfile.ZipFile(p)
            raw = z.read("xl/worksheets/sheet1.xml")
        assert_wellformed(raw)
        # 生のXMLに未エスケープの記号が残っていないこと
        body = raw.decode().split("<sheetData>")[1]
        self.assertNotIn("<&", body)
        self.assertIn("&lt;", body)
        self.assertIn("&amp;", body)
        # パースし直して元の文字列に戻ること（落ちていない・壊れていない）
        doc = minidom.parseString(raw)
        cells = doc.getElementsByTagName("t")
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0].firstChild.nodeValue, text)


class TestNotification(unittest.TestCase):
    def test_required_only_when_both_conditions(self):
        self.assertTrue(notification_required(make_model(90, 16300)))
        self.assertFalse(notification_required(make_model(30, 16300)))   # 期間不足
        self.assertFalse(notification_required(make_model(90, 9000)))    # 高さ不足

    def test_submission_deadline_is_30_days_before(self):
        info = NotificationInfo(start_date=dt.date(2026, 11, 1))
        self.assertEqual(info.submission_deadline(), dt.date(2026, 10, 2))
        self.assertIsNone(NotificationInfo().submission_deadline())

    def test_total_length_is_scaffold_loop(self):
        m = make_model()
        expect = sum(e.scaffold_length for e in m.plan.edges) / 1000.0
        self.assertAlmostEqual(scaffold_total_length_m(m), expect, places=3)

    def test_workbook_contents(self):
        m = make_model()
        q = take_off(m)
        checks = run_all_checks(m)
        st = run_structural(m, q)
        info = NotificationInfo(site_name="テスト工事", start_date=dt.date(2026, 11, 1))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "設置届.xlsx"
            write_notification_xlsx(m, q, checks, st, p, "テスト", info)
            z = zipfile.ZipFile(p)
            self.assertIsNone(z.testzip())
            names = re.findall(r'name="([^"]+)"', z.read("xl/workbook.xml").decode())
            for expected in ["様式第20号(下書き)", "計算書1_風荷重", "計算書2_壁つなぎ",
                             "計算書3_建地圧縮", "部材等明細書", "法規チェック",
                             "添付図書チェック"]:
                self.assertIn(expected, names)

            form = z.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("くさび緊結式足場", form)
            self.assertIn("2026-10-02", form)      # 着手30日前が自動算出される
            self.assertIn("【記入】", form)          # 人が書く欄は空欄マーカー
            self.assertIn("有資格者", form)          # 免責が入る

            tie = z.read("xl/worksheets/sheet4.xml").decode()
            self.assertIn("P = C × q × A", tie)  # 式が転記されている（A＝支配面積）

    def test_unverified_marked_in_sheet(self):
        m = make_model()
        q = take_off(m)
        st = run_structural(m, q)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "n.xlsx"
            write_notification_xlsx(m, q, run_all_checks(m), st, p)
            z = zipfile.ZipFile(p)
            # 壁つなぎ(sheet4)は認定基準値で確認済み。くさびの建地(sheet5)は
            # ジャッキ・支柱が一般値のままなので、そちらに未確認の印が出る
            tie = z.read("xl/worksheets/sheet4.xml").decode()
            post = z.read("xl/worksheets/sheet5.xml").decode()
            self.assertNotIn("未確認値", tie)
            self.assertIn("未確認値", post)


class TestPostSheetNamesTheDeckSource(unittest.TestCase):
    def test_deck_capacity_row_shows_the_real_source(self):
        m = make_model()
        q = take_off(m)
        st = run_structural(m, q)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "n.xlsx"
            write_notification_xlsx(m, q, run_all_checks(m), st, p)
            post = zipfile.ZipFile(p).read("xl/worksheets/sheet5.xml").decode()
        self.assertIn("信和総合カタログ", post)
        self.assertNotIn("kN/スパン  capacity.csv", post)


class TestPostSheetIsReproducible(unittest.TestCase):
    """計算書は値だけでなく、その値を出した数まで載せる（確認できないと意味がない）."""

    def test_inputs_of_each_formula_are_on_the_sheet(self):
        m = make_model()
        q = take_off(m)
        st = run_structural(m, q)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "n.xlsx"
            write_notification_xlsx(m, q, run_all_checks(m), st, p)
            z = zipfile.ZipFile(p)
            names = re.findall(
                r'name="([^"]+)"', z.read("xl/workbook.xml").decode())
            sheet = z.read(
                f"xl/worksheets/sheet{names.index('計算書3_建地圧縮') + 1}.xml"
            ).decode()
        for label in ("足場総重量", "建地本数", "作業床許容積載", "同時載荷層数"):
            self.assertIn(label, sheet)
        self.assertIn(f"<v>{st.post.n_posts}</v>", sheet)
        self.assertIn(f"<v>{q.total_weight_kg}</v>", sheet)

    def test_dead_load_matches_the_stated_numbers(self):
        m = make_model()
        q = take_off(m)
        p = run_structural(m, q).post
        self.assertAlmostEqual(
            p.dead_load_kn, p.total_weight_kg * 9.80665 / 1000.0 / p.n_posts,
            places=2,
        )
        self.assertAlmostEqual(
            p.live_load_kn, p.deck_capacity_kn * p.loaded_levels / 2.0, places=3
        )


class TestForm20StructureSummary(unittest.TestCase):
    """様式第20号の「構造の概要」が計画に追随すること."""

    def _form(self, **cfg):
        m = make_model(**cfg) if cfg else make_model()
        q = take_off(m)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "n.xlsx"
            write_notification_xlsx(m, q, run_all_checks(m), run_structural(m, q), p)
            z = zipfile.ZipFile(p)
            return z.read("xl/worksheets/sheet1.xml").decode()

    def test_deck_and_rail_and_ties_are_stated(self):
        form = self._form()
        for token in ("作業床", "手すり", "壁つなぎ", "朝顔"):
            self.assertIn(token, form)

    def test_attached_equipment_reaches_the_form(self):
        """付帯設備が様式に出る。計画にあるのに届に無いと、審査側は
        「無い」ものとして読む（図面と食い違う届になる）."""
        from ashiba.openings import Opening, validate_openings
        from ashiba.platforms import Hoist, LoadingStage, validate_platforms
        from ashiba.stairs import auto_place_stairs

        m = make_model()
        q = take_off(m)
        stair = auto_place_stairs(m)
        pf = validate_platforms(
            m,
            [LoadingStage(edge_index=0, start_mm=12600, span_count=2, levels=[3])],
            [Hoist(edge_index=2, position_mm=9000)],
        )
        op = validate_openings(m, [Opening(0, 3600, 3600)])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "n.xlsx"
            write_notification_xlsx(
                m, q, run_all_checks(m), run_structural(m, q), path,
                stair_plan=stair, platforms=pf, openings=op,
                bracket_sections=[object()],
            )
            form = zipfile.ZipFile(path).read("xl/worksheets/sheet1.xml").decode()
        for token in ("昇降設備（階段）", "荷受けステージ", "出1500mm 第3層",
                      "昇降機", "開閉式手すり", "開口部（梁枠）", "梁枠3600mm",
                      "ブラケット区間"):
            self.assertIn(token, form)

    def test_no_equipment_rows_when_none_planned(self):
        # 付帯設備なしの計画に空の行を出さない（「0基」は誤読のもと）
        form = self._form()
        for token in ("荷受けステージ", "開口部（梁枠）", "ブラケット区間"):
            self.assertNotIn(token, form)

    def test_deck_width_matches_the_law_check(self):
        """様式の作業床幅と法規チェックの幅が食い違わない（670と650）."""
        m = make_model()
        width = sum(m.deck_widths_in_use)
        self.assertIn(f"幅{width}mm", self._form())
        deck = [c for c in run_all_checks(m) if c.check_id == 2][0]
        self.assertIn(f"幅{width}mm", deck.message)


class TestTodoSheet(unittest.TestCase):
    """提出書類にも「着手前に何を確認するか」を載せる."""

    def _book(self, **kw):
        m = make_model()
        q = take_off(m)
        checks = run_all_checks(m)
        st = run_structural(m, q)
        td = tempfile.mkdtemp()
        p = Path(td) / "n.xlsx"
        write_notification_xlsx(m, q, checks, st, p, **kw)
        z = zipfile.ZipFile(p)
        names = z.read("xl/workbook.xml").decode()
        return z, names

    def test_sheet_absent_without_verdict(self):
        _, names = self._book()
        self.assertNotIn("要確認事項", names)

    def test_sheet_lists_items_and_counts(self):
        z, names = self._book(
            verdict={"ok": True, "blockers": [], "warn": 1,
                     "warn_breakdown": ["構造 1件"]},
            warnings=[("構造", "WARN", "未確認の耐力値が計算に使われています")],
        )
        self.assertIn("要確認事項", names)
        # 様式第20号の次（確認する人が最初に見る位置）
        sheet = z.read("xl/worksheets/sheet2.xml").decode()
        self.assertIn("計画は成立しています", sheet)
        self.assertIn("未確認の耐力値", sheet)
        self.assertIn("構造 1件", sheet)

    def test_blockers_are_listed(self):
        z, _ = self._book(
            verdict={"ok": False, "blockers": ["開口部NG 1件"], "warn": 0,
                     "warn_breakdown": []},
            warnings=[],
        )
        sheet = z.read("xl/worksheets/sheet2.xml").decode()
        self.assertIn("是正が必要です", sheet)
        self.assertIn("開口部NG 1件", sheet)

    def test_ng_warnings_are_listed_once_as_a_blocker_not_as_checklist(self):
        """NG の本文は「是正」の行に1回だけ出す。番号付きの着手前チェックリストには混ぜない.

        以前は本文を出していなかったので「ブラケット区間NG 1件」だけで理由が分からなかった。
        """
        z, _ = self._book(
            verdict={"ok": False, "blockers": ["開口部NG 1件"], "warn": 0,
                     "warn_breakdown": []},
            warnings=[("開口部", "NG", "梁枠3600mmは規格外です")],
        )
        sheet = z.read("xl/worksheets/sheet2.xml").decode()
        self.assertEqual(sheet.count("規格外"), 1)
        self.assertIn("開口部: 梁枠3600mmは規格外です", sheet)
        import re
        numbered = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S)
        self.assertFalse([r for r in numbered if "<v>1</v>" in r and "規格外" in r])


class TestNonFiniteValues(unittest.TestCase):
    """inf / nan を数値セルに書くとブックが開けなくなる."""

    def test_infinite_ratio_does_not_corrupt_the_book(self):
        from ashiba.xlsx_writer import Cell

        wb = Workbook()
        sh = wb.sheet("t")
        sh.add_cells([Cell(float("inf")), Cell(float("nan")), Cell(2.5)])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.xlsx"
            wb.save(path)
            z = zipfile.ZipFile(path)
            name = [n for n in z.namelist() if n.endswith("sheet1.xml")][0]
            xml = z.read(name).decode()
        assert_wellformed(xml.encode())
        self.assertIn("計算不能", xml)
        self.assertIn("<v>2.5</v>", xml)


class TestSheetsStateTheRightBasis(unittest.TestCase):
    """届出書に載る基準値は足場の種類で変わる（570条1項五号）."""

    def _sheet_text(self, series_id):
        master = load_master(series_id)
        plan = solve_plan(RECT, master)
        elev = solve_elevation(16300, master=master)
        model = ScaffoldModel(
            master=master, plan=plan, elevation=elev,
            config=ScaffoldConfig(period_days=90), building_height_mm=16000,
        )
        q = take_off(model)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "n.xlsx"
            write_notification_xlsx(
                model, q, run_all_checks(model), run_structural(model, q),
                path, "テスト", NotificationInfo(),
            )
            z = zipfile.ZipFile(path)
            return "".join(
                z.read(n).decode() for n in z.namelist() if n.endswith(".xml")
            )

    def test_wedge_states_the_tube_scaffold_limits(self):
        text = self._sheet_text("shinwa_A")
        self.assertIn("垂直5000以下", text)
        self.assertIn("くさび緊結式足場", text)

    def test_frame_states_the_frame_scaffold_limits(self):
        text = self._sheet_text("waku")
        self.assertIn("垂直9000以下", text)
        self.assertIn("枠組足場", text)
        self.assertNotIn("垂直5000以下", text)


class TestFormListsWhatSitsOnEachFace(unittest.TestCase):
    """様式第20号の下書きに面ごとの構成（壁つなぎ本数・梁枠…）が入る."""

    def test_opening_example_row(self):
        import re
        import tempfile
        import zipfile

        from ashiba.cli import load_spec, solve_all, write_outputs

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "opening_beam.json"))
        with tempfile.TemporaryDirectory() as d:
            write_outputs(r, Path(d))
            x = next(Path(d).glob("*_設置届一式.xlsx"))
            z = zipfile.ZipFile(x)
            sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        cells = re.findall(r"<t[^>]*>([^<]*)</t>", sheet)
        self.assertIn("面ごとの構成", cells)
        row = next(c for c in cells if c.startswith("南面: "))
        self.assertIn("梁枠1", row)
        self.assertIn("壁つなぎ", row)
        self.assertIn("北面", row)


if __name__ == "__main__":
    unittest.main()

