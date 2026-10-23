"""くさびのフィート寸法の隅（利用者の指定 2026-10-23）: 離れを動かして無理に繋がず、繋がらない隅は
コーナーステップ（GDL 部品 ashiba_cstep）で納める。熟練の所長・足場作業者の目線."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.plan_solver import WEDGE_GAP_CLOSED_MM, WEDGE_STEP_MAX_MM, WEDGE_STEP_MIN_MM

RECT = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]
L = [[0, 0], [24000, 0], [24000, 8000], [12000, 8000], [12000, 16000], [0, 16000]]
U = [[0, 0], [30000, 0], [30000, 18000], [20000, 18000], [20000, 6000], [10000, 6000], [10000, 18000], [0, 18000]]


def _solve(outline, **extra):
    return solve_all({"outline_mm": outline, "eaves_height_mm": 9000, "series_id": "nikken_nd1800", **extra})


class TestFeetCorners(unittest.TestCase):
    def test_standoff_stays_at_300_and_gaps_are_steps(self):
        for name, o in (("長方形", RECT), ("L字", L), ("コの字", U)):
            r = _solve(o)
            with self.subTest(name):
                # 離れは顧客最小値〜300（隅を閉じるために 300 を超えない）
                self.assertTrue(all(250 - 3 <= e.standoff <= 300 + 1e-6 for e in r.model.plan.edges),
                                [e.standoff for e in r.model.plan.edges])
                self.assertTrue(r.model.plan.corner_steps)
                for cs in r.model.plan.corner_steps:
                    self.assertTrue(WEDGE_STEP_MIN_MM <= cs.gap_mm <= WEDGE_STEP_MAX_MM, cs)
                # 面の長さ＝スパンの合計＋終点の隙間（閉じた隅は 30mm 以下）
                gaps = {c.edge_index: c.gap_mm for c in r.model.plan.corner_steps}
                for e in r.model.plan.edges:
                    (sx, sy), (ex, ey) = e.start_post, e.end_post
                    length = abs(ex - sx) + abs(ey - sy)
                    rest = length - sum(e.spans) - gaps.get(e.edge_index, 0.0)
                    self.assertTrue(-0.5 <= rest <= WEDGE_GAP_CLOSED_MM, (e.edge_index, rest))
                self.assertFalse([e for e in r.model.plan.edges if e.remedy])

    def test_metric_and_option_keep_the_old_way(self):
        m = solve_all({"outline_mm": L, "eaves_height_mm": 9000})            # メートルは従来どおり
        self.assertEqual(m.model.plan.corner_steps, [])
        old = _solve(RECT, corner_steps=False)                                 # 入力で従来の解き方
        self.assertEqual(old.model.plan.corner_steps, [])
        self.assertTrue(any(e.standoff > 300 for e in old.model.plan.edges))

    def test_corner_posts_are_not_shared_across_a_gap(self):
        from ashiba.gdl_params import shared_corner_skips

        r = _solve(RECT)
        for e in r.model.plan.edges:
            sk = shared_corner_skips(r.model, e.edge_index)
            self.assertEqual(sk, {"skipInS": 0, "skipInE": 0})     # 隅に隙間 → 両方の面が自分の支柱を描く


class TestCornerStepPart(unittest.TestCase):
    def test_placed_at_the_last_post_with_every_level(self):
        from ashiba.attachments import CSTEP_OBJECT, cstep_placements

        r = _solve(RECT)
        pls = cstep_placements(r.model)
        self.assertEqual(len(pls), len(r.model.plan.corner_steps))
        south = r.model.plan.edges[0]
        p = next(p for p in pls if abs(p.params["faceAng"]) < 1e-6)
        self.assertEqual(p.part, CSTEP_OBJECT)
        self.assertAlmostEqual(p.x_mm, south.start_post[0] + sum(south.spans), delta=0.5)
        self.assertAlmostEqual(p.params["gapL"] * 1000, r.model.plan.corner_steps[0].gap_mm, delta=0.5)
        self.assertEqual(len(p.params["lvList"].split(",")), len(r.model.elevation.level_heights))
        self.assertEqual(p.params["stepName"], "NDCS05")                      # 610 幅は踏板 500

    def test_quantity_counts_steps_per_level(self):
        r = _solve(RECT)
        cs = [l for l in r.quantity.lines if l.part.category == "コーナー踏板"]
        n_lv = len(r.model.elevation.level_heights)
        self.assertEqual(sum(l.qty for l in cs), len(r.model.plan.corner_steps) * n_lv)
        wide = _solve(RECT, scaffold_width_mm=914)                             # 914 幅は踏板 500+240
        self.assertEqual({l.part.model_no for l in wide.quantity.lines if l.part.category == "コーナー踏板"},
                         {"NDCS05", "NDCS02"})

    def test_gdl_part_files(self):
        d = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_cstep"
        p2 = (d / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        p3 = (d / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn('"CS " + str(gapL * 1000, 3, 0)', p2)
        self.assertIn("block gapL, rowW - 0.04, 0.04", p3)
        for n in ("gapL", "rowW", "lvList", "stepName"):
            self.assertIn(f'Name="{n}"', (d / "paramlist.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
