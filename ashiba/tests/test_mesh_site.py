"""敷地メッシュを敷地境界線に・足元の勾配に合わせる（利用者の指定 2026-10-24: メッシュの敷地境界線としてと足元の勾配に
合わせるように配置するような機能つけて）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.site_boundary import boundary_from_meshes
from ashiba.terrain import SLOPE_SHIM_LIMIT, GroundModel, jack_table_rows, solve_post_feet

OUT = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]


class TestMeshBoundary(unittest.TestCase):
    def test_smallest_mesh_around_the_building(self):
        big = [(-20000, -20000), (60000, -20000), (60000, 40000), (-20000, 40000)]
        site = [(-3000, -4000), (28000, -4000), (28000, 13000), (-3000, 13000)]
        away = [(100000, 0), (110000, 0), (110000, 10000)]
        self.assertEqual(boundary_from_meshes([big, site, away], OUT), site)
        self.assertEqual(boundary_from_meshes([away], OUT), [])


class TestSlopeFollowsTheMesh(unittest.TestCase):
    def _slope(self, grade):
        pts = [(x, y, x * grade) for x in (-5000, 10000, 30000) for y in (-5000, 5000, 15000)]
        return GroundModel(points=pts)

    def test_uniform_slope_is_exact(self):
        g = self._slope(0.05)
        self.assertAlmostEqual(g.elevation_at(12345, 3000), 12345 * 0.05, delta=0.5)
        self.assertAlmostEqual(g.slope_at(12345, 3000), 0.05, places=4)
        # メッシュの外へ勾配を延ばさない（点の高さの範囲に収める）
        self.assertLessEqual(g.elevation_at(60000, 3000), 30000 * 0.05 + 1e-6)

    def test_steep_feet_are_flagged_and_listed(self):
        r = solve_all({"outline_mm": OUT, "eaves_height_mm": 9000, "module": "inch"})
        steep = solve_post_feet(r.model, self._slope(SLOPE_SHIM_LIMIT * 1.5))
        self.assertTrue(any("足元の勾配" in w for w in steep.warnings))
        self.assertTrue(all(abs(f.slope - SLOPE_SHIM_LIMIT * 1.5) < 1e-3 for f in steep.feet))
        rows = jack_table_rows(steep)
        self.assertIn("勾配(%)", rows[0])
        gentle = solve_post_feet(r.model, self._slope(0.03))
        self.assertFalse(any("足元の勾配" in w for w in gentle.warnings))
        self.assertTrue(any("足元の勾配は最大 3.0%" in n for n in gentle.notes))


if __name__ == "__main__":
    unittest.main()
