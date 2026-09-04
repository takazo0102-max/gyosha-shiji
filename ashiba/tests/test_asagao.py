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


class TestAsagaoGaps(unittest.TestCase):
    """朝顔は「落下物を受ける」設備。隙間が残る箇所を黙らない."""

    def _model(self, outline=None, stages=1):
        master = load_master("shinwa_A")
        poly = outline or RECT
        return ScaffoldModel(
            master=master, plan=solve_plan(poly, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=AsagaoSpec(stages=stages)),
            building_height_mm=16000,
        )

    def test_outside_corners_are_reported(self):
        m = self._model()
        q = take_off(m)
        # 出隅の隅部はコーナー材で計上し、その旨を注記に出す（現場対応の警告ではない）
        hit = [n for n in q.notes if "出隅" in n and "朝顔コーナー" in n]
        self.assertTrue(hit, q.notes)
        corners = [c for c in m.plan.outline.corners if c.kind == "出隅"]
        self.assertIn(f"出隅{len(corners)}箇所", hit[0])
        self.assertFalse([w for w in q.warnings if "出隅" in w])

    def test_odd_span_is_reported(self):
        """900スパンに1800の板を当てていることを書く."""
        q = take_off(self._model())
        hit = [w for w in q.warnings if "呼び寸法が合わない" in w]
        self.assertTrue(hit, q.warnings)
        self.assertIn("900mm", hit[0])

    def test_panel_count_still_matches_spans(self):
        m = self._model()
        q = take_off(m)
        self.assertEqual(q.qty_of("朝顔", 1800), m.plan.total_spans)

    def test_frame_system_gets_the_same_notes(self):
        """枠組の経路にだけ注記が無い、という状態を作らない."""
        master = load_master("waku")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)),
            building_height_mm=16000,
        )
        q = take_off(m)
        self.assertTrue([n for n in q.notes if "出隅" in n and "朝顔コーナー" in n], q.notes)
        self.assertTrue([w for w in q.warnings if "呼び寸法が合わない" in w])
        self.assertGreater(q.qty_of("朝顔"), 0)

    def test_no_asagao_no_notes(self):
        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=None), building_height_mm=16000,
        )
        q = take_off(m)
        self.assertFalse([w for w in q.warnings if "朝顔" in w or "出隅" in w])


if __name__ == "__main__":
    unittest.main()


class TestAsagaoCorners(unittest.TestCase):
    """出隅の隅部は朝顔コーナー（型番仮）で計上する（以前は現場対応の注記だけだった）."""

    def test_corner_pieces_counted_per_convex_corner_and_stage(self):
        from ashiba.elevation_solver import solve_elevation
        from ashiba.master import load_master
        from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
        from ashiba.plan_solver import solve_plan
        from ashiba.quantity import take_off

        for series in ("shinwa_A", "waku"):
            with self.subTest(series):
                master = load_master(series)
                m = ScaffoldModel(
                    master=master,
                    plan=solve_plan([(0, 0), (30000, 0), (30000, 20000), (0, 20000)], master),
                    elevation=solve_elevation(25000, master=master),
                    config=ScaffoldConfig(asagao=AsagaoSpec(stages=2)),
                )
                q = take_off(m)
                corner = [l for l in q.lines if l.part.category == "朝顔" and "コーナー" in l.part.note]
                self.assertEqual(len(corner), 1)
                self.assertEqual(corner[0].qty, 4 * 2)
                self.assertTrue([n for n in q.notes if "朝顔コーナー" in n and "計上" in n])
                self.assertFalse([w for w in q.warnings if "隅角部の板" in w])

