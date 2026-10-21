"""単管の通し: 規定の長さの単管を直線ジョイントで継ぐ（利用者の指定 2026-10-22）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tube_runs import END_MM, JOINT_CLEAR_MM, MAX_OVER_MM, STOCK_MM, face_runs, post_positions

GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"


class TestTubeRuns(unittest.TestCase):
    def test_runs_cover_the_face_with_stock_lengths(self):
        for spans in ([1800] * 7, [1800] * 4 + [1500], [1800] * 20 + [900], [1800, 1800], [1500]):
            a, b = face_runs(spans)
            L = sum(spans)
            self.assertTrue(all(p in STOCK_MM for p in a.pieces))
            self.assertEqual(a.start_mm, -END_MM)
            self.assertGreaterEqual(a.end_mm, L + END_MM)                 # 終点の建地の先まで届く
            self.assertLessEqual(a.end_mm, L + END_MM + MAX_OVER_MM)
            self.assertEqual(sorted(a.pieces), sorted(b.pieces))          # B は同じ単管の並べ替え（数量は同じ）
            posts = post_positions(spans)
            for x in a.joints_mm + b.joints_mm:                           # 継ぎは建地のクランプから離す
                self.assertTrue(all(abs(x - p) >= JOINT_CLEAR_MM for p in posts))

    def test_example_face(self):
        a, b = face_runs([1800] * 7)                                      # 12.6m の面
        self.assertEqual(a.pieces, [6000, 6000, 1000])                    # 本数が少なく、長い単管が先
        self.assertEqual(len(a.joints_mm), 2)
        self.assertNotEqual(a.joints_mm, b.joints_mm)                     # 隣の通しと継ぎをずらす

    def test_short_face_is_one_tube(self):
        a, b = face_runs([1800, 1800])
        self.assertEqual(a.pieces, [4000])
        self.assertEqual(a.joints_mm, [])

    def test_gdl_draws_the_runs(self):
        d3 = (GDL / "3d.gdl").read_text(encoding="utf-8")
        d1 = (GDL / "1d.gdl").read_text(encoding="utf-8")
        self.assertIn("rl[p832][nRl[p832]] = v / 1000", d1)
        self.assertIn("832:", d3)
        self.assertIn("846:", d3)
        # 布・根がらみ・手すり（外・内）・抱き足場の床の布が通しを使う
        self.assertGreaterEqual(d3.count("runX = x"), 4)
        # 識別色は長さ別一覧表の11色
        self.assertEqual(d3.count('define material "ashiba_tc_'), 11)

    def test_params(self):
        from ashiba.cli import solve_all
        from ashiba.gdl_params import line_params

        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}
        m = solve_all({**base, "scaffold_form": "単管抱き足場"}).model
        p = line_params(m, m.plan.edges[0])
        a, b = face_runs(list(m.plan.edges[0].spans))
        self.assertEqual(p["tubeRunA"], ",".join(str(v) for v in a.pieces))
        self.assertEqual(p["tubeRunB"], ",".join(str(v) for v in b.pieces))
        self.assertAlmostEqual(p["tubeRunS"], -0.1)
        w = solve_all(base).model
        self.assertEqual(line_params(w, w.plan.edges[0])["tubeRunA"], "")   # くさびは通さない


if __name__ == "__main__":
    unittest.main()
