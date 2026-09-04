"""最小スパン未満の凹み・張り出しは直線で渡す（エラーで止めない）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.geometry import ValidationError, build_outline
from ashiba.master import load_master
from ashiba.plan_solver import solve_plan

MASTER = load_master("shinwa_A")
MIN_SPAN = min(MASTER.span_lengths())      # 600

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def with_notch(depth, width, at=12000, bump=False):
    """南面(y=0)に幅 width・奥行/出 depth の出入りを付けた外形（CCW）."""
    d = -depth if bump else depth
    return [(0, 0), (at, 0), (at, d), (at + width, d), (at + width, 0),
            (30000, 0), (30000, 20000), (0, 20000)]


class TestBridge(unittest.TestCase):
    def test_shallow_recess_is_bridged_with_a_note(self):
        o = build_outline(with_notch(300, 3600), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 4)
        self.assertTrue([n for n in o.notes if "凹み" in n and "直線で渡します" in n
                         and "300mm増えます" in n], o.notes)

    def test_narrow_deep_slot_is_bridged(self):
        o = build_outline(with_notch(3600, 300), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 4)
        self.assertTrue([n for n in o.notes if "3600mm増えます" in n], o.notes)

    def test_deep_wide_recess_is_routed(self):
        o = build_outline(with_notch(900, 1800), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 8)
        self.assertFalse([n for n in o.notes if "渡します" in n])

    def test_shallow_bump_moves_the_neighbours_out(self):
        o = build_outline(with_notch(300, 3600, bump=True), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 4)
        # 南面全体が張り出しの線 y=-300 に移る
        self.assertTrue(all(abs(v[1] + 300) < 1e-6 for v in o.vertices if v[1] < 10000))
        self.assertTrue([n for n in o.notes if "張り出し" in n and "両隣" in n], o.notes)

    def test_tall_narrow_bump_is_still_routed(self):
        o = build_outline(with_notch(3600, 300, bump=True), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 8)

    def test_off_by_default(self):
        o = build_outline(with_notch(300, 3600))
        self.assertEqual(len(o.vertices), 8)

    def test_solver_no_longer_rejects_shallow_notches(self):
        for shape in (with_notch(300, 3600), with_notch(3600, 300),
                      with_notch(300, 3600, bump=True)):
            with self.subTest(shape):
                plan = solve_plan(shape, MASTER)
                self.assertEqual(len(plan.edges), 4)
                self.assertTrue([w for w in plan.warnings if "渡します" in w], plan.warnings)

    def test_step_is_not_flattened(self):
        """段差（入って戻らない）は出入りではないので対象外."""
        step = [(0, 0), (12000, 0), (12000, 300), (30000, 300), (30000, 20000), (0, 20000)]
        o = build_outline(step, bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 6)


if __name__ == "__main__":
    unittest.main()
