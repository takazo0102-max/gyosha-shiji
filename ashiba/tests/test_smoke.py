"""実機スモークの純粋な部分（入力の一覧・置き場所・照合）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, validate_spec
from ashiba.smoke import (
    ORIGIN_MM,
    PITCH_MM,
    CaseReport,
    all_zero,
    cases,
    count_mismatches,
    placed_spec,
    select,
    summary_lines,
)

DEV = Path(__file__).resolve().parents[1] / "examples" / "dev"


class TestCases(unittest.TestCase):
    def test_dev_inputs_and_both_modules(self):
        names = [c.name for c in cases(DEV)]
        self.assertIn("small_stage", names)
        self.assertEqual(names[-7:], ["rect_metric", "rect_inch", "pentagon", "lshape", "forms_bridge", "waku_bridge",
                                      "tube_lap"])
        with self.assertRaises(SystemExit):
            select(cases(DEV), ["nope"])
        self.assertEqual([c.name for c in select(cases(DEV), ["rect_inch"])], ["rect_inch"])

    def test_every_case_is_a_valid_input_far_from_the_user_model(self):
        for i, c in enumerate(cases(DEV)):
            spec, outline = placed_spec(c, i)
            validate_spec(spec)
            self.assertTrue(spec["project_name"].startswith("スモーク "))
            self.assertGreaterEqual(min(p[0] for p in outline), ORIGIN_MM[0] + PITCH_MM * i)
            self.assertNotIn("project_name", c.spec if c.name.startswith("rect") else {})
        # 置き場所が違っても割付は同じ（平行移動しただけ）
        c = select(cases(DEV), ["small_stage"])[0]
        a = solve_all(c.spec)
        b = solve_all(placed_spec(c, 3)[0])
        self.assertEqual([e.standoff for e in a.model.plan.edges], [e.standoff for e in b.model.plan.edges])


class TestCompare(unittest.TestCase):
    def test_count_mismatches(self):
        want = {"qtyPost": 10, "qtyDeck": 4, "qtyStair": 0}
        self.assertEqual(count_mismatches(want, {"qtyPost": 10.0, "qtyDeck": 4}), [])   # 無い名前は飛ばす
        self.assertEqual(count_mismatches(want, {"qtyPost": 9}), ["qtyPost 部品9≠式10"])
        self.assertEqual(count_mismatches(want, {"qtyDeck": "x"}), ["qtyDeck=?"])

    def test_all_zero_means_1d_did_not_run(self):
        self.assertTrue(all_zero({"qtyPost": 0, "qtyDeck": 0.0}, ("qtyPost", "qtyDeck")))
        self.assertFalse(all_zero({"qtyPost": 0, "qtyDeck": 3}, ("qtyPost", "qtyDeck")))
        self.assertFalse(all_zero({}, ("qtyPost",)))      # パラメータが無いのは別の判定

    def test_summary(self):
        ok = CaseReport("a")
        ok.add("x", True)
        ng = CaseReport("b")
        ng.add("y", False, "だめ")
        lines = summary_lines([ok, ng])
        self.assertIn("    × y: だめ", lines)
        self.assertEqual(lines[-1], "2件中 1件 OK・1件 NG")
        self.assertIn("    ○ x", summary_lines([ok], verbose=True))


if __name__ == "__main__":
    unittest.main()
