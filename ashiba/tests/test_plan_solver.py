import unittest

from _path import SRC  # noqa: F401

from ashiba.geometry import ValidationError, build_outline
from ashiba.master import load_master
from ashiba.plan_solver import StandoffSpec, solve_plan

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
# L型: 入隅が(18000,12000)に1つ
LSHAPE = [(0, 0), (30000, 0), (30000, 12000), (18000, 12000), (18000, 20000), (0, 20000)]


class TestGeometry(unittest.TestCase):
    def test_corner_classification(self):
        o = build_outline(LSHAPE)
        kinds = [c.kind for c in o.corners]
        self.assertEqual(kinds.count("出隅"), 5)
        self.assertEqual(kinds.count("入隅"), 1)
        reflex = [c for c in o.corners if c.kind == "入隅"][0]
        self.assertEqual(reflex.point, (18000.0, 12000.0))

    def test_non_orthogonal_rejected(self):
        with self.assertRaises(ValidationError):
            build_outline([(0, 0), (10000, 0), (5000, 8000)])

    def test_cw_input_normalized(self):
        o = build_outline(list(reversed(RECT)))
        self.assertEqual([c.kind for c in o.corners], ["出隅"] * 4)


class TestPlanRect(unittest.TestCase):
    def setUp(self):
        self.master = load_master("shinwa_A")
        self.plan = solve_plan(RECT, self.master)

    def test_standoffs_in_range(self):
        for d in self.plan.standoffs:
            self.assertGreaterEqual(d, 250)
            self.assertLessEqual(d, 350)
        self.assertEqual(self.plan.warnings, [])

    def test_span_geometry_consistency(self):
        # 各辺: sum(spans) == 躯体辺長 + 符号付き隣接離れ（真物のみ・切断なし）
        n = len(self.plan.edges)
        for ep, e in zip(self.plan.edges, self.plan.outline.edges):
            d_prev = self.plan.standoffs[(e.index - 1) % n]
            d_next = self.plan.standoffs[(e.index + 1) % n]
            expect = e.length + e.start_sign * d_prev + e.end_sign * d_next
            self.assertAlmostEqual(sum(ep.spans), expect, delta=0.5)
            self.assertAlmostEqual(ep.scaffold_length, sum(ep.spans), delta=0.5)

    def test_long_face_all_main_spans(self):
        # 30m面は1800×17=30600（離れ300/300）で割れる
        e0 = self.plan.edges[0]
        self.assertEqual(e0.spans, [1800] * 17)

    def test_spans_are_stock_lengths(self):
        stock = set(self.master.span_lengths())
        for ep in self.plan.edges:
            for s in ep.spans:
                self.assertIn(s, stock)

    def test_opposite_faces_balanced(self):
        # 全体XYシフトで対面の離れが均等になる
        self.assertAlmostEqual(self.plan.standoffs[0], self.plan.standoffs[2], delta=0.5)
        self.assertAlmostEqual(self.plan.standoffs[1], self.plan.standoffs[3], delta=0.5)

    def test_no_double_counted_posts(self):
        pts = self.plan.post_positions()
        self.assertEqual(len(pts), self.plan.total_posts)
        uniq = {(round(x, 1), round(y, 1)) for x, y in pts}
        self.assertEqual(len(uniq), len(pts))
        self.assertEqual(self.plan.total_posts, self.plan.total_spans)


class TestPlanLShape(unittest.TestCase):
    def setUp(self):
        self.master = load_master("shinwa_A")
        self.plan = solve_plan(LSHAPE, self.master)

    def test_geometry_consistency(self):
        n = len(self.plan.edges)
        for ep, e in zip(self.plan.edges, self.plan.outline.edges):
            d_prev = self.plan.standoffs[(e.index - 1) % n]
            d_next = self.plan.standoffs[(e.index + 1) % n]
            expect = e.length + e.start_sign * d_prev + e.end_sign * d_next
            self.assertAlmostEqual(sum(ep.spans), expect, delta=0.5)

    def test_no_double_counted_posts(self):
        pts = self.plan.post_positions()
        uniq = {(round(x, 1), round(y, 1)) for x, y in pts}
        self.assertEqual(len(uniq), len(pts))
        self.assertEqual(self.plan.total_posts, self.plan.total_spans)

    def test_standoff_or_remedy(self):
        # 受け入れ基準: 全面250〜350、または350超の面に対処案が提示される
        for ep in self.plan.edges:
            if not (250 <= ep.standoff <= 350):
                self.assertIsNotNone(ep.remedy)
                self.assertTrue(
                    "ブラケット" in ep.remedy or "落下防止" in ep.remedy
                    or "スパン構成" in ep.remedy
                )

    def test_hard_min_respected(self):
        for d in self.plan.standoffs:
            self.assertGreaterEqual(d, 200)


if __name__ == "__main__":
    unittest.main()
