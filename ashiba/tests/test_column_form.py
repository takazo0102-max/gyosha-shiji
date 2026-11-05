"""柱の型枠（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置する
ようにして）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

import math

from ashiba.column_form import COL_OUT_MM, column_from_details, column_rect, plan_column, wall_hits
from ashiba.wall_form import BAND_MM, TUBE_OFF_MM, W0_KN_M3, face_layout, free_ends, pressure_kn_m2


class TestColumnForm(unittest.TestCase):
    def test_column_pressure(self):
        w = W0_KN_M3
        self.assertAlmostEqual(pressure_kn_m2(3000, column=True), 1.5 * w + 0.6 * w * 1.5)

    def test_small_column_has_no_through_tie(self):
        f = plan_column(600, 600, 3000, clamp=False)
        self.assertTrue(f.ok)
        edge = 300 + BAND_MM + COL_OUT_MM
        self.assertEqual([round(x, 1) for x in f.tie_x], [round(-edge, 1), round(edge, 1)])    # 角の外だけ
        q = {n: k for n, k, _x in f.quantities()}
        self.assertNotIn("フォームタイ（柱を貫く）", q)
        self.assertEqual(q["フォームタイ（柱の角の外）"], 4 * len(f.tate_z))

    def test_large_column_adds_through_ties(self):
        f = plan_column(800, 800, 3000, clamp=False)
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


class TestColumnClamp(unittest.TestCase):
    """コラムクランプで締める（利用者の指定 2026-10-31: せぱ飛び出てない？？／コラムクランプで締める）."""

    def test_free_column_uses_clamps_without_ties(self):
        f = plan_column(800, 800, 3000)
        self.assertTrue(f.clamp and f.ok)
        self.assertEqual((f.tie_x, f.tie_y), ([], []))                       # 角の外のフォームタイも貫くセパもなし
        self.assertTrue(all(fc["tube"] == [] for fc in f.faces))
        gaps = [b - a for a, b in zip(f.tate_z, f.tate_z[1:])]
        self.assertGreater(max(gaps), gaps[0])                                # 上ほど広い
        q = {n: k for n, k, _x in f.quantities()}
        self.assertEqual(q["コラムクランプ（800×800 用）"], len(f.tate_z))
        self.assertNotIn("フォームタイ（柱の角の外）", q)
        self.assertIn("コラムクランプの腕", f.calc_x.lines()[3])

    def test_column_with_wall_keeps_walers_and_ties(self):
        wall = {"ca": (0.0, 0.0), "cb": (6000.0, 0.0), "u": (1.0, 0.0), "n": (0.0, 1.0), "lo": -100.0, "hi": 100.0,
                "thick": 200.0, "length": 6000.0}
        col = {"c": (6000.0, 0.0), "width": 800.0, "depth": 800.0, "ang": 0.0, "height": 3000.0}
        f = plan_column(800, 800, 3000, wall_hits(col, [wall]))
        self.assertFalse(f.clamp)                                             # 壁が取り付くとクランプは一周できない
        self.assertTrue(f.tie_x)


class TestWallIntoColumn(unittest.TestCase):
    """壁が柱に取り付く所: 壁の型枠は柱の型枠の外で止め、柱の面は壁の所で分け、壁を貫くフォームタイは外す."""

    def setUp(self):
        L = 6000.0
        self.wall = {"ca": (0.0, 0.0), "cb": (L, 0.0), "u": (1.0, 0.0), "n": (0.0, 1.0), "lo": -100.0, "hi": 100.0,
                     "thick": 200.0, "length": L}
        self.col = {"c": (L, 0.0), "width": 800.0, "depth": 800.0, "ang": 0.0, "height": 3000.0}

    def test_wall_stops_at_column(self):
        (lay,) = face_layout([self.wall], [column_rect(self.col)])
        self.assertEqual(lay["faces"], [(0.0, 5600.0), (0.0, 5600.0)])                 # 柱の面まで
        self.assertAlmostEqual(lay["tubes"][0][1], 5600.0 - TUBE_OFF_MM)              # 柱の外端太の線まで
        self.assertAlmostEqual(lay["sangi"][0][1], 5600.0 - BAND_MM)                  # 柱の型枠の外
        self.assertEqual(free_ends([self.wall], [column_rect(self.col)]), [(True, False)])   # 柱の側は止め型枠なし

    def test_column_face_split_and_ties_dropped(self):
        f = plan_column(800.0, 800.0, 3000.0, wall_hits(self.col, [self.wall]))
        mx = f.faces[1]                                                               # −X の面（壁の取り付く面）
        self.assertEqual([tuple(round(v, 1) for v in seg) for seg in mx["ply"]], [(-400.0, -100.0), (100.0, 400.0)])
        self.assertEqual([tuple(round(v, 1) for v in seg) for seg in mx["tube"]],
                         [(round(-400 - 100 - 150.6, 1), round(-100 - TUBE_OFF_MM, 1)), (round(100 + TUBE_OFF_MM, 1), 650.6)])
        self.assertFalse(any(-100 - BAND_MM < v < 100 + BAND_MM for v in mx["sangi"]))
        self.assertTrue(all(len(fc["ply"]) == 1 for k, fc in enumerate(f.faces) if k != 1))
        self.assertNotIn(-550.6, [round(x, 1) for x in f.tie_x])                      # 壁を貫くフォームタイは外す
        self.assertNotIn(0.0, [round(y, 1) for y in f.tie_y])
        self.assertEqual(f.dropped, 2)
        self.assertTrue(f.notes())


if __name__ == "__main__":
    unittest.main()
