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


class TestFeetOnTheSlope(unittest.TestCase):
    def test_feet_on_the_excavation_slope_are_ng(self):
        """根切りの法面（勾配 200%）に立つ脚は総合判定を止める（段切りか自在ジャッキの注意で済ませていた）."""
        from ashiba.box import box_loop
        from ashiba.manual import solve_manual_loop

        ground = {"series_id": "albatross", "ground_points_mm": [list(p) for p in pit_points()]}
        pts, sides = box_loop((1500.0, -4500.0), 0.0, [1829] * 4, [1829] * 2)      # 北側が法面にかかる
        _w, _s, r = solve_manual_loop(pts, sides, 300.0, 6000.0, ground)
        self.assertIn("敷地NG 1件", r.verdict["blockers"])
        pts, sides = box_loop((1500.0, -10000.0), 0.0, [1829] * 4, [1829] * 2)     # 根切り底の中
        _w, _s, r = solve_manual_loop(pts, sides, 300.0, 6000.0, ground)
        self.assertTrue(r.verdict["ok"], r.verdict)


class TestGroundSpread(unittest.TestCase):
    def test_slope_under_the_stage(self):
        """範囲が法面にかかると脚ごとの地盤の高さが違う（中央の1点で建てていた）。根切り底の平らな所は何も出ない."""
        from ashiba.beams import ground_spread, ground_spread_message

        g = GroundModel(points=pit_points())
        flat = [(x, y) for x in (4600, 6000, 7400) for y in (-10000, -7000, -5200)]
        self.assertIsNone(ground_spread_message(ground_spread(flat, g, -2000.0)))
        edge = [(x, y) for x in (4600, 6000, 7400) for y in (-3500, -2500, -1500)]
        st, msg = ground_spread_message(ground_spread(edge, g, g.elevation_at(6000, -2500)))
        self.assertEqual(st, "NG")
        self.assertIn("2000mm 違う", msg)
        small = [(6000, -2650), (6000, -2700)]                            # 法尻の 50mm の差はジャッキで合わせる
        self.assertEqual(ground_spread_message(ground_spread(small, g, -2000.0))[0], "WARN")


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

    def test_walkway_footprint(self):
        """芯どうしが交わらなくても、通路の幅が梁の端にかかる所・梁に沿って通る所を拾う。勾配はいちばん低い所で見る."""
        bm = Beam((4000.0, -12700.0), (4000.0, -2700.0), 600.0, -1000.0, -2000.0)
        graze = ((3000.0, -2300.0), (5600.0, -2300.0))        # 芯は梁の端の 400 先、幅 900 の縁が梁にかかる
        self.assertEqual(walkway_beam_checks(*graze, -1000.0, -1000.0, [bm]), [])
        self.assertEqual(walkway_beam_checks(*graze, -1000.0, -1000.0, [bm], width_mm=900.0)[0][0], "NG")
        along = walkway_beam_checks((4000.0, -12000.0), (4000.0, -4000.0), -900.0, -500.0, [bm], width_mm=900.0)
        self.assertEqual(len(along), 1)
        self.assertEqual(along[0][0], "NG")                     # 低い始めの側: −900−120 は梁の上端 −1000 より下
        self.assertIn("〜", along[0][1])
        slope = walkway_beam_checks((3000.0, -7600.0), (5000.0, -7600.0), -1000.0, 0.0, [bm], width_mm=900.0)
        self.assertIn("あき 230mm", slope[0][1])                # 梁の幅の手前の縁（始めから 700）の床 −650


if __name__ == "__main__":
    unittest.main()
