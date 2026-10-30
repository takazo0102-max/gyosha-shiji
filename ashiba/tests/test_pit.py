"""根切り底と地中梁（利用者の指定 2026-10-30: 次足場はメッシュに根切り底と梁を置いてテストして）.

敷地メッシュは三角形分割で高さを補う（近い点の平面当てで根切りの脇の GL±0 が −620 になっていた）、根切りの肩の近くの脚、
地中梁の上に乗る支柱、梁をまたぐ仮設通路のあき。"""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.beams import Beam, beam_from_details, posts_on_beams, walkway_beam_checks
from ashiba.terrain import GroundModel


def pit_points(dy: float = 0.0) -> list:
    """GL±0 の敷地に、法肩 y −1700・法尻 y −2700（深さ 2m）の根切り（dy で南へ遠ざける）."""
    pts = []
    for (x0, y0, x1, y1), z in (((-8000, -20000, 20000, 14000), 0.0), ((-2000, -13700 - dy, 14000, -1700 - dy), 0.0),
                                ((-1000, -12700 - dy, 13000, -2700 - dy), -2000.0)):
        pts += [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    return pts


class TestPitGround(unittest.TestCase):
    def test_tin_heights(self):
        g = GroundModel(points=pit_points())
        self.assertAlmostEqual(g.elevation_at(6000, -7000), -2000.0)      # 根切り底
        self.assertAlmostEqual(g.elevation_at(6000, 1000), 0.0)           # 根切りの外（−620 になっていた）
        self.assertAlmostEqual(g.elevation_at(6000, -2200), -1000.0)      # 法面の中ほど
        self.assertAlmostEqual(g.slope_at(6000, -2200), 2.0)

    def test_edge_warning(self):
        from ashiba.cli import solve_all

        spec = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
                "series_id": "albatross"}
        near = solve_all({**spec, "ground_points_mm": [list(p) for p in pit_points()]})
        self.assertTrue([w for w in near.warnings if "肩の近くに立つ" in str(w)])
        far = solve_all({**spec, "ground_points_mm": [list(p) for p in pit_points(3000.0)]})
        self.assertFalse([w for w in far.warnings if "肩の近くに立つ" in str(w)])


class TestBeams(unittest.TestCase):
    def test_details_use_zcoordinate(self):
        """zCoordinate はプロジェクトの原点からの高さ（level は階からの高さで、足すと二重になる）."""
        bm = beam_from_details({"begCoordinate": {"x": 0, "y": 0}, "endCoordinate": {"x": 0, "y": 10}, "zCoordinate": -1,
                                "level": 1, "width": 0.6, "height": 1, "anchorPoint": "TopCenter", "beamShape": "Straight"})
        self.assertEqual((bm.top_mm, bm.bottom_mm, bm.width), (-1000.0, -2000.0, 600.0))

    def test_posts_and_walkway(self):
        bm = Beam((4000.0, -12700.0), (4000.0, -2700.0), 600.0, -1000.0, -2000.0)
        posts = [(3800.0, -8000.0), (5000.0, -8000.0), (4000.0, -1000.0)]
        hit = posts_on_beams(posts, [bm], -2000.0)
        self.assertEqual([p for p, _b in hit], [(3800.0, -8000.0)])       # 芯から 200（幅 600 の上）だけ
        ok = walkway_beam_checks((3000.0, -7600.0), (5600.0, -7600.0), -200.0, -200.0, [bm])
        ng = walkway_beam_checks((3000.0, -7600.0), (5600.0, -7600.0), -1000.0, -1000.0, [bm])
        self.assertEqual((ok[0][0], ng[0][0]), ("OK", "NG"))
        self.assertIn("あき 680mm", ok[0][1])


if __name__ == "__main__":
    unittest.main()
