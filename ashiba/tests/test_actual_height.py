"""敷地の低い側の実高さで見るべき判定（朝顔・届出・風・様式）.

名目高さで見ると、段差で継ぎ足した分が抜ける（16.3mの計画が低い側で21mでも
「朝顔1段・届出不要（9m）」のまま）。
"""

import re
import unittest
import zipfile
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import run_all_checks
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.notification import notification_required
from ashiba.plan_solver import solve_plan
from ashiba.terrain import GroundModel, actual_max_height_mm, solve_post_feet

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(height=16300, asagao_stages=1, period=90):
    master = load_master("shinwa_A")
    return ScaffoldModel(
        master=master, plan=solve_plan(RECT, master),
        elevation=solve_elevation(height, master=master),
        config=ScaffoldConfig(
            period_days=period,
            asagao=AsagaoSpec(stages=asagao_stages) if asagao_stages else None),
        building_height_mm=height - 300,
    )


def terrace(m, drop):
    return solve_post_feet(m, GroundModel(points=[
        (0, 0, drop), (30000, 0, 0), (30000, 20000, 0), (0, 20000, drop)]))


class TestActualHeight(unittest.TestCase):
    def test_flat_equals_nominal(self):
        m = build()
        self.assertEqual(actual_max_height_mm(m, None), (16300.0, 0.0))
        h, extra = actual_max_height_mm(m, terrace(m, 0))
        self.assertAlmostEqual(h, 16300.0, delta=1)
        self.assertAlmostEqual(extra, 0.0, delta=1)

    def test_terrace_adds_the_extension(self):
        m = build()
        h, extra = actual_max_height_mm(m, terrace(m, 5000))
        self.assertGreater(extra, 4500)
        self.assertAlmostEqual(h, 16300 + extra, delta=1)


class TestAsagaoUsesActualHeight(unittest.TestCase):
    def test_second_stage_required_on_the_low_side(self):
        m = build(16300, asagao_stages=1)
        flat = [r for r in run_all_checks(m, terrain=terrace(m, 0)) if r.check_id == 10][0]
        self.assertEqual(flat.status, "OK", flat.message)
        low = [r for r in run_all_checks(m, terrain=terrace(m, 5000)) if r.check_id == 10][0]
        self.assertEqual(low.status, "NG", low.message)
        self.assertIn("必要2段", low.message)
        self.assertIn("実高さ", low.basis)


class TestNotificationUsesActualHeight(unittest.TestCase):
    def test_nine_metre_plan_on_a_step_needs_the_notice(self):
        m = build(9000)
        self.assertFalse(notification_required(m))
        self.assertFalse(notification_required(m, terrace(m, 0)))
        self.assertTrue(notification_required(m, terrace(m, 2000)))

    def test_form_writes_the_actual_height(self):
        import tempfile

        from ashiba.notification import NotificationInfo, write_notification_xlsx
        from ashiba.quantity import take_off
        from ashiba.structural import run_structural

        m = build()
        t = terrace(m, 5000)
        q = take_off(m, terrain=t)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "n.xlsx"
            write_notification_xlsx(
                m, q, run_all_checks(m, terrain=t), run_structural(m, q, terrain=t),
                path, info=NotificationInfo(), terrain=t)
            z = zipfile.ZipFile(path)
            wb = z.read("xl/workbook.xml").decode()
            names = re.findall(r'<sheet name="([^"]+)"', wb)
            xml = z.read(f"xl/worksheets/sheet{names.index('様式第20号(下書き)') + 1}.xml").decode()
        cells = re.findall(r"<t[^>]*>([^<]*)</t>", xml)
        i = cells.index("足場の高さ")
        self.assertIn("実高さ", cells[i + 1])   # 数値セルは<t>に出ないので次が単位注記
        self.assertIn("脚の伸び", cells[i + 1])
        h, _ = actual_max_height_mm(m, t)
        # 数値セルは <v> に入る（末尾の0は落ちる。21.290 → 21.29）
        self.assertIn(f"<v>{round(h / 1000, 3):g}</v>", xml)


class TestWindUsesActualHeight(unittest.TestCase):
    def test_height_factor_grows_with_the_extension(self):
        from ashiba.structural import SiteCondition, compute_wind

        m = build()
        site = SiteCondition()
        flat = compute_wind(m, site)
        tall = compute_wind(m, site, height_mm=actual_max_height_mm(m, terrace(m, 5000))[0])
        self.assertGreater(tall.height_m, flat.height_m)
        self.assertGreaterEqual(tall.k_height, flat.k_height)


if __name__ == "__main__":
    unittest.main()
