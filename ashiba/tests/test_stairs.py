"""階段（昇降設備）自動配置のテスト.

安衛則526条: 高さ1.5m超は昇降設備が必要。
実務指針: 昇降設備までの水平移動距離は30m以内が目安。
"""

import unittest
from pathlib import Path

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

    def test_towers_never_overlap(self):
        """区間が重なると物理的に成立せず、踏板の差引も二重にかかる."""
        m = build(outline=SMALL)
        for n in (2, 4, 6, 8, 12):
            with self.subTest(count=n):
                plan = auto_place_stairs(m, count=n)
                self.assertEqual(validate_stairs(m, plan), [])
                seen = set()
                for t in plan.towers:
                    self.assertNotIn((t.edge_index, t.start_mm), seen)
                    seen.add((t.edge_index, t.start_mm))

    def test_deduction_counts_each_span_once(self):
        """重なりが起きると差引が二重になり踏板が不足する."""
        m = build(outline=SMALL)
        plan = auto_place_stairs(m, count=8)
        self.assertEqual(
            sum(stair_deck_deduction(m, plan).values()),
            sum(t.span_count for t in plan.towers),
        )

    def test_unplaceable_count_is_reported(self):
        """置けなかった箇所を黙って減らさない（ただし1行にまとめる）."""
        m = build(outline=SMALL)
        plan = auto_place_stairs(m, count=20)
        self.assertLess(plan.count, 20)
        hits = [w for w in plan.warnings if "しか配置できません" in w]
        self.assertEqual(len(hits), 1, plan.warnings)
        self.assertIn(f"{plan.count}箇所", hits[0])
        self.assertIn("20箇所", hits[0])

    def test_min_per_face_puts_one_on_every_face(self):
        m = build()
        plan = auto_place_stairs(m, min_per_face=1)
        faces = {t.edge_index for t in plan.towers}
        self.assertEqual(faces, {e.edge_index for e in m.plan.edges})
        self.assertEqual(validate_stairs(m, plan), [])

    def test_min_per_face_still_meets_travel_distance(self):
        m = build()
        plan = auto_place_stairs(m, min_per_face=1)
        self.assertLessEqual(plan.max_travel_mm, DEFAULT_MAX_TRAVEL_MM)

    def test_min_per_face_tops_up_when_one_per_face_is_not_enough(self):
        """各面1箇所で移動距離が足りない大きな建物は、広く空いた所から埋める."""
        m = build(outline=[(0, 0), (100000, 0), (100000, 60000), (0, 60000)])
        plan = auto_place_stairs(m, min_per_face=1)
        self.assertGreater(plan.required_count, len(m.plan.edges))
        self.assertGreaterEqual(plan.count, plan.required_count)
        self.assertLessEqual(plan.max_travel_mm, DEFAULT_MAX_TRAVEL_MM)
        self.assertEqual(validate_stairs(m, plan), [])

    def test_top_up_fills_the_widest_gap_first(self):
        """埋める位置は一番広く空いた区間。偏って詰めない."""
        m = build(outline=[(0, 0), (100000, 0), (100000, 60000), (0, 60000)])
        plan = auto_place_stairs(m, min_per_face=1)
        loop = sum(e.scaffold_length for e in m.plan.edges)
        pos = sorted(t.loop_position_mm for t in plan.towers)
        gaps = [b - a for a, b in zip(pos, pos[1:])] + [loop - pos[-1] + pos[0]]
        # 最大の間隔が周長の半分を超えるような偏りは無い
        self.assertLess(max(gaps), loop / 2)

    def test_top_up_reports_when_it_runs_out_of_room(self):
        """置けない分を黙って減らさない."""
        m = build(outline=SMALL)
        plan = auto_place_stairs(m, count=20, min_per_face=1)
        self.assertLess(plan.count, 20)
        self.assertTrue(
            any("しか置けません" in w for w in plan.warnings), plan.warnings
        )

    def test_min_per_face_reports_faces_that_cannot_take_one(self):
        """短い面には階段室が入らない。入らなかったことを黙らせない."""
        m = build(outline=[(0, 0), (30000, 0), (30000, 3000), (0, 3000)])
        plan = auto_place_stairs(m, min_per_face=1)
        self.assertTrue(any("階段室を1箇所置けません" in w for w in plan.warnings))

    def test_no_plan_falls_back_to_config(self):
        m = build()
        m.config.n_stairs = 1
        self.assertEqual(take_off(m).qty_of("階段"), m.elevation.n_levels)


class TestWallTieRatioIsNotInfinite(unittest.TestCase):
    """作業層が取れない高さでも、検定比inf を帳票やJSONに出さない."""

    def test_no_infinity_in_the_result(self):
        import json
        import tempfile

        from ashiba.cli import run

        # 軒高0は入口で弾くので、作業層が取れない最小の正の軒高で再現する
        spec = {"series_id": "shinwa_A", "project_name": "軒高ごくわずか",
                "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 100, "period_days": 90}
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "s.json"
            f.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = run(f, Path(td) / "o")
        self.assertNotIn("Infinity", json.dumps(r, ensure_ascii=False))
        self.assertIsNone(r["structural"]["wall_tie_ratio"])
        self.assertTrue(any("検定不能" in b for b in r["verdict"]["blockers"]))
        self.assertTrue(
            any("壁つなぎが1本もないため" in w for w in r["warnings"]), r["warnings"]
        )


class TestLandings(unittest.TestCase):
    """踊り場は2層以下毎（昇降階段の基準）。数を0にしても落ちなかった箇所."""

    def _model(self, height=16300):
        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(height, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def test_every_two_levels(self):
        from ashiba.stairs import LANDING_EVERY_LEVELS, landings_per_tower

        m = self._model()
        n = m.elevation.n_levels
        self.assertEqual(
            landings_per_tower(m), max(0, (n - 1) // LANDING_EVERY_LEVELS))
        self.assertGreater(landings_per_tower(m), 0)

    def test_counted_in_the_quantity(self):
        m = self._model()
        plan = auto_place_stairs(m)
        q = take_off(m, stair_plan=plan)
        self.assertEqual(
            q.qty_of("踊り場"), plan.count * plan.landings_per_tower)
        self.assertGreater(q.qty_of("踊り場"), 0)

    def test_reported_in_the_law_check(self):
        from ashiba.law_check import run_all_checks

        m = self._model()
        plan = auto_place_stairs(m)
        c = [x for x in run_all_checks(m, stair_plan=plan) if x.check_id == 12][0]
        self.assertIn(f"踊り場計{plan.total_landings}段", c.message)


class TestTooSmallForAStairTower(unittest.TestCase):
    """階段室が入らない規模でも、読める形で結果を返すこと."""

    def _model(self, side_mm):
        master = load_master("shinwa_A")
        poly = [(0, 0), (side_mm, 0), (side_mm, side_mm), (0, side_mm)]
        return ScaffoldModel(
            master=master, plan=solve_plan(poly, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def test_warning_offers_an_alternative(self):
        plan = auto_place_stairs(self._model(3000))
        self.assertEqual(plan.count, 0)
        hit = [w for w in plan.warnings if "はしご" in w]
        self.assertTrue(hit, plan.warnings)
        self.assertNotIn("inf", "".join(plan.warnings))

    def test_no_distance_warning_without_towers(self):
        """0箇所のときに「移動距離infm」と言わない."""
        m = self._model(3000)
        plan = auto_place_stairs(m)
        for text in plan.warnings + validate_stairs(m, plan):
            self.assertNotIn("infm", text)

    def test_result_json_has_no_infinity(self):
        import json
        import tempfile

        from ashiba.cli import run

        spec = {"series_id": "shinwa_A", "project_name": "極小",
                "outline_mm": [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                "eaves_height_mm": 15400, "period_days": 90}
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "s.json"
            f.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = run(f, Path(td) / "o")
        text = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("Infinity", text)
        self.assertIsNone(r["stairs"]["max_travel_m"])


if __name__ == "__main__":
    unittest.main()
