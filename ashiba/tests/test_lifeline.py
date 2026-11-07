"""親綱と親綱支柱（利用者の指定 2026-11-01: 親綱と親綱支柱も追加して）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.lifeline import Run, part_params, plan_run, report, span_limit


class TestSpan(unittest.TestCase):
    def test_limits(self):
        """別表6: L＝40(H−4)/11（L=10m なら H≧6.75m）、矢作: H ≧ X/3＋3、上限 10m。厳しい方."""
        self.assertEqual(span_limit(3500.0), 0.0)
        self.assertAlmostEqual(span_limit(5000.0), 40.0 * 1.0 / 11.0 * 1000.0)
        self.assertAlmostEqual(span_limit(6750.0), 10000.0)
        self.assertEqual(span_limit(12000.0), 10000.0)


class TestDropZones(unittest.TestCase):
    """H の区分（reports/デッキプレートの敷設時期.md）."""

    def test_zones(self):
        from ashiba.lifeline import judge_drop

        self.assertEqual([judge_drop(h)[0] for h in (4000.0, 4200.0, 4800.0, 4900.0, 6700.0, 6750.0, 9000.0)],
                         ["適用外", "警告", "警告", "注意", "注意", "OK", "OK"])

    def test_short_span_is_not_placed(self):
        r = plan_run(Run("親綱", (0, 0), (7200, 0), 4200.0, 4200.0))
        self.assertEqual(({c.item: c.status for c in r.checks}["スパン"], r.spans, r.quantity), ("警告", [], []))

    def test_harness_uses_the_upper_h(self):
        r = plan_run(Run("親綱", (0, 0), (7200, 0), 5000.0, 5000.0, drop_max=9000.0))
        self.assertIn("落差 9.0m", {c.item: c.message for c in r.checks}["墜落制止用器具"])

    def test_note_for_the_finished_floors(self):
        r = plan_run(Run("親綱", (0, 0), (7200, 0), 8000.0, 8000.0, note="完成時"))
        self.assertEqual({c.item: c.status for c in r.checks}["落差"], "注意")

    def test_low_post_does_not_force_type_2(self):
        r = plan_run(Run("親綱", (0, 0), (7200, 0), 8000.0, 8000.0))
        self.assertIn("第一種も可", {c.item: c.message for c in r.checks}["親綱の高さ"])


class TestRun(unittest.TestCase):
    def test_posts_ropes_and_checks(self):
        r = plan_run(Run("親綱1", (0, 0), (24000, 0), 8000.0, 8000.0))
        self.assertEqual(r.spans, [7800.0] * 3)                              # 両端 300 入れて 23.4m を3つに
        q = {a: n for a, n, _u in r.quantity}
        self.assertEqual((q["親綱支柱（H鋼取付用）NTP"], q["NSPR20 親綱（20m・販売品）"], q["NSPJK 親綱緊張用自在滑車"]), (4, 3, 3))
        st = {c.item: c.status for c in r.checks}
        self.assertEqual((st["スパン"], st["親綱の高さ"]), ("OK", "WARN"))    # 支柱 1,045 は D環 1.45m より低い
        low = plan_run(Run("親綱2", (0, 0), (7000, 0), 3500.0, 3500.0))
        self.assertEqual(({c.item: c.status for c in low.checks}["スパン"], low.quantity), ("適用外", []))
        alu = plan_run(Run("親綱3", (0, 0), (9000, 0), 8000.0, 8000.0, "ALPA12", flange_t=60.0))
        self.assertEqual({c.item: c.status for c in alu.checks}["つかみ厚"], "NG")
        self.assertEqual(part_params(alu)["postK"], 2)
        self.assertIn("NSPR20", report([r]))


if __name__ == "__main__":
    unittest.main()
