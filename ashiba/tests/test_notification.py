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
        wb = Workbook()
        wb.sheet("s").add(["<&>\"危険"])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.xlsx"
            wb.save(p)
            z = zipfile.ZipFile(p)
            assert_wellformed(z.read("xl/worksheets/sheet1.xml"))


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
            self.assertIn("P = C × q × lh × lw", tie)  # 式が転記されている

    def test_unverified_marked_in_sheet(self):
        m = make_model()
        q = take_off(m)
        st = run_structural(m, q)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "n.xlsx"
            write_notification_xlsx(m, q, run_all_checks(m), st, p)
            z = zipfile.ZipFile(p)
            tie = z.read("xl/worksheets/sheet4.xml").decode()
            self.assertIn("未確認値", tie)


if __name__ == "__main__":
    unittest.main()
