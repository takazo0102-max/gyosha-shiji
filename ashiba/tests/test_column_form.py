"""柱の型枠（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置する
ようにして）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.column_form import COL_OUT_MM, column_from_details, plan_column
from ashiba.wall_form import BAND_MM, W0_KN_M3, pressure_kn_m2


class TestColumnForm(unittest.TestCase):
    def test_column_pressure(self):
        w = W0_KN_M3
        self.assertAlmostEqual(pressure_kn_m2(3000, column=True), 1.5 * w + 0.6 * w * 1.5)

    def test_small_column_has_no_through_tie(self):
        f = plan_column(600, 600, 3000)
        self.assertTrue(f.ok)
        edge = 300 + BAND_MM + COL_OUT_MM
        self.assertEqual([round(x, 1) for x in f.tie_x], [round(-edge, 1), round(edge, 1)])    # 角の外だけ
        q = {n: k for n, k, _x in f.quantities()}
        self.assertNotIn("フォームタイ（柱を貫く）", q)
        self.assertEqual(q["フォームタイ（柱の角の外）"], 4 * len(f.tate_z))

    def test_large_column_adds_through_ties(self):
        f = plan_column(800, 800, 3000)
        self.assertTrue(f.ok)
        self.assertEqual(len(f.tie_x), 3)                                   # 柱を貫くフォームタイが1本
        self.assertAlmostEqual(f.tie_x[1], 0.0)
        q = {n: k for n, k, _x in f.quantities()}
        self.assertEqual(q["フォームタイ（柱を貫く）"], 2 * len(f.tate_z))
        self.assertEqual(q["Pコン"], 4 * len(f.tate_z))
        for xs, half in ((f.sangi_x, 400), (f.sangi_y, 400)):
            self.assertTrue(all(-half < x < half for x in xs))
            self.assertTrue(all(b - a <= f.calc_x.sangi_pitch + 1e-6 for a, b in zip(xs, xs[1:])))

    def test_column_details(self):
        det = {"type": "Column", "details": {"origin": {"x": 1, "y": 2}, "width": 0.6, "depth": 0.9, "height": 3.5,
                                             "zCoordinate": 0, "bottomOffset": 0, "circleBased": False, "isSlanted": False,
                                             "axisRotationAngle": 0},
               "floorPlanPolygons": [{"coordinates": [{"x": 0.7, "y": 1.55}, {"x": 1.3, "y": 1.55}, {"x": 1.3, "y": 2.45},
                                                      {"x": 0.7, "y": 2.45}, {"x": 0.7, "y": 1.55}]}]}
        c = column_from_details(det)
        self.assertEqual((round(c["c"][0]), round(c["c"][1])), (1000, 2000))
        self.assertEqual((c["width"], c["depth"], c["height"]), (600.0, 900.0, 3500.0))
        det["details"]["circleBased"] = True
        self.assertIsNone(column_from_details(det))                        # 丸い柱は飛ばす


if __name__ == "__main__":
    unittest.main()
