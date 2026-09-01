"""階段（昇降設備）自動配置のテスト.

安衛則526条: 高さ1.5m超は昇降設備が必要。
実務指針: 昇降設備までの水平移動距離は30m以内が目安。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.stairs import (
    DEFAULT_MAX_TRAVEL_MM,
    actual_max_travel,
    auto_place_stairs,
    stair_deck_deduction,
    validate_stairs,
)

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
SMALL = [(0, 0), (12000, 0), (12000, 8000), (0, 8000)]


def build(height=16300, outline=RECT):
    master = load_master("shinwa_A")
    plan = solve_plan(outline, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)), building_height_mm=16000,
    )


def loop_length(model):
    return sum(e.scaffold_length for e in model.plan.edges)


class TestAutoPlacement(unittest.TestCase):
    def test_count_meets_travel_limit(self):
        m = build()
        plan = auto_place_stairs(m)
        self.assertGreaterEqual(plan.count, 1)
        self.assertLessEqual(plan.max_travel_mm, DEFAULT_MAX_TRAVEL_MM)
        self.assertEqual(plan.warnings, [])

    def test_max_travel_computed_from_actual_positions(self):
        """理想配置の式ではなく実位置から計算する（丸めで位置がずれるため）."""
        m = build()
        plan = auto_place_stairs(m)
        expect = actual_max_travel(plan.towers, loop_length(m))
        self.assertAlmostEqual(plan.max_travel_mm, expect, places=3)
        # 均等配置の理想値と実配置は一致しないことが普通
        ideal = loop_length(m) / (2 * plan.count)
        self.assertGreaterEqual(plan.max_travel_mm, ideal - 1e-6)

    def test_single_stair_on_long_loop_warns(self):
        m = build()
        plan = auto_place_stairs(m, count=1)
        self.assertEqual(plan.count, 1)
        self.assertGreater(plan.max_travel_mm, DEFAULT_MAX_TRAVEL_MM)
        self.assertTrue(any("超えます" in w for w in plan.warnings))

    def test_more_stairs_shorten_travel(self):
        m = build()
        d2 = auto_place_stairs(m, count=2).max_travel_mm
        d4 = auto_place_stairs(m, count=4).max_travel_mm
        self.assertLess(d4, d2)

    def test_towers_avoid_corners(self):
        """コーナーから1スパン以上離す."""
        m = build()
        for t in auto_place_stairs(m, count=4).towers:
            edge = [e for e in m.plan.edges if e.edge_index == t.edge_index][0]
            self.assertGreaterEqual(t.start_mm, edge.spans[0] - 1e-6)
            self.assertLessEqual(t.end_mm, edge.scaffold_length - edge.spans[-1] + 1e-6)

    def test_towers_do_not_overlap(self):
        m = build()
        plan = auto_place_stairs(m, count=4)
        self.assertEqual(validate_stairs(m, plan), [])

    def test_low_scaffold_needs_no_stairs(self):
        m = build(height=1400)
        plan = auto_place_stairs(m)
        self.assertEqual(plan.count, 0)
        self.assertTrue(any("不要" in w for w in plan.warnings))

    def test_small_building_gets_one_stair(self):
        m = build(outline=SMALL)
        plan = auto_place_stairs(m)
        self.assertEqual(plan.required_count, 1)
        self.assertEqual(plan.count, 1)


class TestValidation(unittest.TestCase):
    def test_missing_stairs_flagged(self):
        m = build()
        empty = auto_place_stairs(m, count=0)
        issues = validate_stairs(m, empty)
        self.assertTrue(any("昇降設備がありません" in i for i in issues))

    def test_travel_limit_flagged(self):
        m = build()
        issues = validate_stairs(m, auto_place_stairs(m, count=1))
        self.assertTrue(any("水平移動距離" in i for i in issues))


class TestQuantityIntegration(unittest.TestCase):
    def test_stair_spans_deducted_from_decks(self):
        """階段室の区間には踏板を敷かない（二重計上の防止）."""
        m = build()
        plan = auto_place_stairs(m)
        base = take_off(m)
        with_stairs = take_off(m, stair_plan=plan)
        deduction = stair_deck_deduction(m, plan)
        expected_drop = (
            sum(deduction.values()) * m.elevation.n_levels * len(m.config.deck_widths)
        )
        self.assertEqual(
            base.qty_of("踏板") - with_stairs.qty_of("踏板"), expected_drop
        )
        self.assertGreater(expected_drop, 0)

    def test_deduction_matches_tower_spans(self):
        m = build()
        plan = auto_place_stairs(m, count=2)
        self.assertEqual(
            sum(stair_deck_deduction(m, plan).values()),
            sum(t.span_count for t in plan.towers),
        )

    def test_stair_count_follows_plan(self):
        m = build()
        plan = auto_place_stairs(m, count=3)
        q = take_off(m, stair_plan=plan)
        self.assertEqual(q.qty_of("階段"), 3 * m.elevation.n_levels)

    def test_no_plan_falls_back_to_config(self):
        m = build()
        m.config.n_stairs = 1
        self.assertEqual(take_off(m).qty_of("階段"), m.elevation.n_levels)


if __name__ == "__main__":
    unittest.main()
