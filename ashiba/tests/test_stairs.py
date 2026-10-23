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
    stair_open_cells,
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
        """階段室は各層で階段が上がってくる1スパンだけ踏板を敷かない（二重計上の防止）."""
        m = build()
        plan = auto_place_stairs(m)
        base = take_off(m)
        with_stairs = take_off(m, stair_plan=plan)
        n = m.elevation.n_levels
        expected_drop = sum(stair_open_cells(m, plan, n).values()) * len(m.config.deck_widths)
        self.assertEqual(
            base.qty_of("踏板") - with_stairs.qty_of("踏板"), expected_drop
        )
        self.assertGreater(expected_drop, 0)

    def test_one_open_span_per_level(self):
        """2スパンの階段室は、各層で1スパン開口・もう1スパンに床（2026-10-18 の決め）."""
        m = build()
        plan = auto_place_stairs(m, count=2)
        n = m.elevation.n_levels
        self.assertTrue(all(t.span_count == 2 for t in plan.towers))
        self.assertEqual(sum(stair_open_cells(m, plan, n).values()), len(plan.towers) * n)

    def test_odd_levels_open_the_start_side_span(self):
        """奇数層へは始点側、偶数層へは終点側のスパン。始点側は (n+1)//2、終点側は n//2 層ぶん開口."""
        from ashiba.stairs import StairPlan

        m = build()
        plan = auto_place_stairs(m, count=1)
        t = plan.towers[0]
        edge = next(e for e in m.plan.edges if e.edge_index == t.edge_index)
        acc, tspans = 0.0, []
        for sp in edge.spans:
            if t.start_mm - 1e-6 <= acc < t.end_mm - 1e-6:
                tspans.append(sp)
            acc += sp
        self.assertEqual(len(tspans), 2)
        one = StairPlan(towers=[t])
        for n in (1, 2, 5, 8):
            got = stair_open_cells(m, one, n)
            if tspans[0] == tspans[1]:
                self.assertEqual(got, {tspans[0]: n})
            else:
                self.assertEqual(got, {tspans[0]: (n + 1) // 2, tspans[1]: n // 2})

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
        n = m.elevation.n_levels
        self.assertEqual(
            sum(stair_open_cells(m, plan, n).values()),
            sum(n for t in plan.towers if t.span_count >= 1),
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


class TestStairGuards(unittest.TestCase):
    """踊り場の床は使わない（2層ごとに外の作業床へ出る）。手すりは両側、開口部手摺・幅木は出入口1か所に1組."""

    def _model(self, series="shinwa_A", height=16300):
        master = load_master(series)
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(height, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def test_no_landing_boards(self):
        m = self._model()
        plan = auto_place_stairs(m)
        q = take_off(m, stair_plan=plan)
        self.assertEqual(q.qty_of("踊り場"), 0)

    def test_handrail_on_the_stair_side_and_one_guard_set_per_entrance(self):
        # 階段手すりは階段側だけ（もう一方は開口部手摺）。利用者の指摘 2026-10-22
        m = self._model("nikken_nd1800")
        plan = auto_place_stairs(m)
        q = take_off(m, stair_plan=plan)
        n = m.elevation.n_levels
        self.assertEqual(q.qty_of("階段手摺"), plan.count * n)
        self.assertEqual(q.qty_of("階段開口部手摺"), plan.count * n)
        self.assertEqual(q.qty_of("階段開口部幅木"), plan.count * n)

    def test_missing_guard_parts_go_to_the_order_list(self):
        """マスタに無い階段まわりの部材は、手配の注記に本数つきで出す."""
        m = self._model("shinwa_A")
        plan = auto_place_stairs(m)
        q = take_off(m, stair_plan=plan)
        hit = [w for w in q.warnings if "階段まわりの部材" in w]
        self.assertTrue(hit, q.warnings)
        self.assertIn("階段開口部手摺", hit[0])

    def test_reported_in_the_law_check(self):
        from ashiba.law_check import run_all_checks

        m = self._model()
        plan = auto_place_stairs(m)
        c = [x for x in run_all_checks(m, stair_plan=plan) if x.check_id == 12][0]
        self.assertIn("作業床が踊り場を兼ねる", c.message)


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


class TestTravelWarningIsNotDuplicated(unittest.TestCase):
    """移動距離超過は配置側と検証側で同じ事象。要確認一覧には1回だけ出す."""

    def test_one_message_for_one_excess(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "examples" / "l_shape.json").read_text(encoding="utf-8"))
        spec["stairs"] = {"positions": [{"edge_index": 0, "start_mm": 9000}]}   # 1箇所では30m超
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        hits = [w[2] for w in r.warnings if "最大水平移動距離" in w[2]]
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("箇所以上を推奨", hits[0])   # 残るのは何箇所要るかまで書いた方


class TestUnevenStairPositionsGetAUsefulHint(unittest.TestCase):
    """数は足りているのに偏りで30mを超えるとき、指定済みの数を「推奨」しない."""

    def _run(self, positions):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        spec["stairs"] = {"positions": positions}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return solve_all(load_spec(p))

    def test_two_towers_side_by_side(self):
        r = self._run([{"edge_index": 0, "start_mm": 1800}, {"edge_index": 0, "start_mm": 7200}])
        hits = [w[2] for w in r.warnings if "最大水平移動距離" in w[2]]
        self.assertEqual(len(hits), 1, hits)
        self.assertNotIn("2箇所以上を推奨", hits[0])
        self.assertIn("位置の見直し", hits[0])
        self.assertIn("3箇所以上", hits[0])
        self.assertIn("2箇所を等間隔に置けば", hits[0])

    def test_too_few_towers_still_says_how_many(self):
        r = self._run([{"edge_index": 0, "start_mm": 1800}])
        hits = [w[2] for w in r.warnings if "最大水平移動距離" in w[2]]
        self.assertTrue(hits and "箇所以上を推奨" in hits[0], hits)


class TestSingleRowStairsNeedADoubleRowSection(unittest.TestCase):
    def test_warning_is_raised(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "examples" / "hitokawa.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        # 一側（ブラケット）足場には階段を付けない（床の幅に階段枠が入らない。利用者の指摘 2026-10-23）。
        # 昇降ははしご（外周 60m ごと）にして、そう書く
        self.assertFalse(r.stair_plan.towers)
        self.assertGreater(r.model.config.ladders, 0)
        self.assertTrue(any("階段を付けられない寸法" in w for w in r.model.plan.warnings), r.model.plan.warnings)


if __name__ == "__main__":
    unittest.main()


class TestLaddersWhenNoStairFits(unittest.TestCase):
    """階段室が入らない小さい足場は、はしごを自動で入れる（2026-10-24 実機: 2.6×2.4m で昇降設備 NG）."""

    def test_tiny_scaffold_gets_a_hatch_ladder(self):
        """くさびの本足場はハッチ付布板（梯子内蔵 NDN6TA）で昇降口を作る。その升目の踏板は差し引く."""
        from ashiba.cli import solve_all
        from ashiba.gdl_params import line_params

        r = solve_all({"outline_mm": [[0, 0], [2600, 0], [2600, 2400], [0, 2400]], "eaves_height_mm": 3000})
        self.assertFalse(r.stair_plan.towers)
        self.assertEqual(r.model.config.ladders, 1)
        self.assertEqual(len(r.model.hatch_ladders), 1)
        self.assertEqual(next(c for c in r.checks if c.check_id == 12).status, "OK")
        self.assertTrue(any("階段室" in w and "ハッチ付布板" in w for w in r.model.plan.warnings))
        self.assertFalse(r.stair_plan.warnings)                          # 階段室を置けなかった文は残さない
        q = {l.part.model_no: l.qty for l in r.quantity.lines}
        n_lv = r.model.elevation.n_levels
        self.assertEqual(q.get("NDN6TA"), n_lv)
        plain = solve_all({"outline_mm": [[0, 0], [2600, 0], [2600, 2400], [0, 2400]], "eaves_height_mm": 3000,
                           "ladders": 1})                                # はしごを入力した足場（ハッチ無し）
        qp = {l.part.model_no: l.qty for l in plain.quantity.lines}
        self.assertEqual(qp.get("NDN6", 0) - q.get("NDN6", 0), n_lv)
        ei, k = r.model.hatch_ladders[0]
        ep = next(e for e in r.model.plan.edges if e.edge_index == ei)
        self.assertEqual(line_params(r.model, ep, stair_plan=r.stair_plan)["hatchList"], str(k + 1))

    def test_bracket_keeps_plain_ladders(self):
        """ブラケット足場（ハーフアンチ）はハッチ付布板が載らないので、はしご（別途手配）のまま."""
        from ashiba.cli import solve_all

        r = solve_all({"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000,
                       "scaffold_form": "ブラケット足場", "bracket_post": "支柱"})
        self.assertFalse(r.model.hatch_ladders)
        self.assertGreater(r.model.config.ladders, 0)
