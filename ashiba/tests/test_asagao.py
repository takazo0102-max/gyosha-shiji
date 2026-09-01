"""朝顔（法規チェック#10）のテスト.

高さ10m以上で1段・20m以上で2段、突出2m以上・傾斜20度以上、
取付部は2スパン毎に壁つなぎ。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import NG, OK, check_asagao, required_asagao_stages
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(height: int, asagao=None):
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=asagao), building_height_mm=height,
    )


class TestRequiredStages(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(required_asagao_stages(9999), 0)
        self.assertEqual(required_asagao_stages(10000), 1)
        self.assertEqual(required_asagao_stages(19999), 1)
        self.assertEqual(required_asagao_stages(20000), 2)


class TestAsagaoCheck(unittest.TestCase):
    def test_not_required_under_10m(self):
        r = check_asagao(build(8000))
        self.assertEqual(r.status, OK)
        self.assertIn("不要", r.message)

    def test_missing_over_10m_is_ng(self):
        r = check_asagao(build(16300))
        self.assertEqual(r.status, NG)
        self.assertIn("1段", r.message)

    def test_one_stage_ok_over_10m(self):
        r = check_asagao(build(16300, AsagaoSpec(stages=1)))
        self.assertEqual(r.status, OK)

    def test_two_stages_required_over_20m(self):
        self.assertEqual(check_asagao(build(25000, AsagaoSpec(stages=1))).status, NG)
        self.assertEqual(check_asagao(build(25000, AsagaoSpec(stages=2))).status, OK)

    def test_projection_and_angle(self):
        r = check_asagao(build(16300, AsagaoSpec(stages=1, projection_mm=1500)))
        self.assertEqual(r.status, NG)
        self.assertIn("突出", r.message)
        r = check_asagao(build(16300, AsagaoSpec(stages=1, angle_deg=15)))
        self.assertEqual(r.status, NG)
        self.assertIn("傾斜", r.message)

    def test_tie_spacing_at_mount(self):
        r = check_asagao(build(16300, AsagaoSpec(stages=1, tie_every_spans=3)))
        self.assertEqual(r.status, NG)
        self.assertIn("壁つなぎ", r.message)

    def test_basis_cites_rule(self):
        r = check_asagao(build(16300, AsagaoSpec(stages=1)))
        self.assertIn("10m", r.basis)
        self.assertIn("20度", r.basis)


class TestAsagaoQuantity(unittest.TestCase):
    def test_parts_counted(self):
        model = build(16300, AsagaoSpec(stages=1))
        q = take_off(model)
        self.assertEqual(q.qty_of("朝顔"), sum(
            l.qty for l in q.lines if l.part.category == "朝顔"))
        self.assertGreater(q.qty_of("朝顔"), 0)
        # 本体はスパン数ぶん
        panel = [l for l in q.lines if "防護棚" in l.part.note][0]
        self.assertEqual(panel.qty, model.plan.total_spans)

    def test_two_stages_double_parts(self):
        one = take_off(build(25000, AsagaoSpec(stages=1))).qty_of("朝顔")
        two = take_off(build(25000, AsagaoSpec(stages=2))).qty_of("朝顔")
        self.assertEqual(two, one * 2)

    def test_no_asagao_no_parts(self):
        self.assertEqual(take_off(build(8000)).qty_of("朝顔"), 0)

    def test_mounting_adds_wall_ties(self):
        base = take_off(build(16300)).qty_of("壁つなぎ")
        with_asagao = take_off(build(16300, AsagaoSpec(stages=1))).qty_of("壁つなぎ")
        self.assertGreater(with_asagao, base)


if __name__ == "__main__":
    unittest.main()
