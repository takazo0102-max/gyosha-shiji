"""枠組の出隅は建枠どうしが繋がらないので 70mm 以上離し、単管（直交クランプ）で繋ぐ（利用者の指定 2026-10-24: 枠足場は
繋がらないから70mm離して単管で繋げけるようにして）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params
from ashiba.plan_solver import FRAME_CORNER_MAX_STEP_MM, FRAME_CORNER_MIN_GAP_MM

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000, "series_id": "waku"}
GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"


class TestFrameCornerTube(unittest.TestCase):
    def setUp(self):
        self.r = solve_all({**RECT, "roof_bridge": False})      # 屋上への渡りの単管・クランプは外して数える
        self.m = self.r.model

    def test_gaps_are_near_70(self):
        gaps = [self.m.frame_gap_end_mm(e.edge_index) for e in self.m.plan.edges]
        # 70mm 以上（建枠を離す）で、離れを固定したまま寄せられるだけ寄せる。単管は 250 まで繋げる
        self.assertTrue(all(FRAME_CORNER_MIN_GAP_MM <= g <= FRAME_CORNER_MAX_STEP_MM for g in gaps), gaps)
        self.assertEqual([round(line_params(self.m, e)["frGapE"] * 1000) for e in self.m.plan.edges], gaps)

    def test_tubes_and_clamps_are_counted(self):
        n_lv = self.m.elevation.n_levels
        self.assertEqual(self.r.quantity.qty_of("単管"), 4 * 2 * (n_lv + 1))
        self.assertEqual(self.r.quantity.qty_of("クランプ"), 2 * 4 * 2 * (n_lv + 1))
        self.assertTrue(any("建枠どうしが繋がらない" in n for n in self.r.quantity.notes))

    def test_wedge_has_no_frame_gap(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        self.assertTrue(all(r.model.frame_gap_end_mm(e.edge_index) == 0 for e in r.model.plan.edges))
        self.assertEqual(r.quantity.qty_of("単管"), 0)

    def test_drawn_in_3d_and_plan(self):
        d3 = (GDL / "3d.gdl").read_text(encoding="utf-8")
        d2 = (GDL / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn('if frGapE > 0.001 and serType = "W" then', d3)
        self.assertIn("cylind frGapE + 0.20, 0.0243", d3)
        self.assertIn('"単管連結 隙間"', d2)


if __name__ == "__main__":
    unittest.main()
