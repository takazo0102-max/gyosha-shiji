"""枠組足場（建枠方式）のテスト.

くさび式（支柱＋布材）と枠組式（建枠）は構造が根本的に違うので、
立面の解き方も数量ルールも分岐する。従属部材（アームロック・連結ピン）は
建枠数から自動算出する（仕様3.1）。
"""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation, solve_elevation_frame
from ashiba.law_check import run_all_checks, summary
from ashiba.master import FRAME, WEDGE, load_master
from ashiba.model import FRAME_GUARD_RAIL_HEIGHT_MM, AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.stairs import auto_place_stairs

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build_frame(height=16300):
    master = load_master("waku")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)), building_height_mm=16000,
    )


class TestSystemType(unittest.TestCase):
    def test_series_declare_system(self):
        self.assertEqual(load_master("shinwa_A").system_type, WEDGE)
        self.assertEqual(load_master("waku").system_type, FRAME)
        self.assertFalse(load_master("shinwa_A").is_frame)
        self.assertTrue(load_master("waku").is_frame)

    def test_frame_catalog(self):
        m = load_master("waku")
        # 日建カタログの建枠高さ（1700の標準枠に、1524・1219・914の調整枠と490の調節枠）
        self.assertEqual(m.frame_heights(), [1700, 1524, 1219, 914, 490])
        self.assertEqual(m.frame_widths(), [1219, 914, 610])
        # 建枠間隔はインチ規格
        self.assertIn(1829, m.span_lengths())


class TestFrameElevation(unittest.TestCase):
    def test_stacks_frames_not_posts(self):
        m = load_master("waku")
        r = solve_elevation_frame(16300, m)
        self.assertEqual(r.total_height, 16300)
        for h in r.posts:
            self.assertIn(h, m.frame_heights())
        # 標準枠が下、調整枠が上
        self.assertEqual(r.posts, sorted(r.posts, reverse=True))

    def test_solve_elevation_dispatches_by_system(self):
        m = load_master("waku")
        direct = solve_elevation_frame(16300, m)
        dispatched = solve_elevation(16300, master=m)
        self.assertEqual(dispatched.posts, direct.posts)

    def test_levels_equal_frame_stages(self):
        m = load_master("waku")
        r = solve_elevation_frame(16300, m)
        # 最上段は手すり分なので作業層は段数-1
        self.assertEqual(r.n_levels, len(r.posts) - 1)

    def test_unsolvable_raises(self):
        m = load_master("waku")
        with self.assertRaises(ValueError):
            solve_elevation_frame(100, m)


class TestFrameQuantity(unittest.TestCase):
    def setUp(self):
        self.m = build_frame()
        self.q = take_off(self.m, stair_plan=auto_place_stairs(self.m))

    def test_no_missing_parts(self):
        self.assertEqual(
            [n for n in self.q.notes if "該当部材がありません" in n], []
        )

    def test_frame_width_fits_deck(self):
        """建枠幅は「近い幅」ではなく「布板が載る最小幅」を選ぶ."""
        frames = [l for l in self.q.lines if l.part.category == "建枠"]
        self.assertTrue(frames)
        need = self.m.deck_width_total
        for line in frames:
            width = int(line.part.note.split("幅")[1].split()[0])
            self.assertGreaterEqual(width, need)

    def test_armlock_from_frame_count(self):
        """アームロックは構面数×段数（建枠2枚に1個）."""
        n_bays = self.m.plan.total_spans
        n_stages = len(self.m.elevation.posts)
        self.assertEqual(self.q.qty_of("アームロック"), n_bays * n_stages)

    def test_joint_pin_from_stacking(self):
        """連結ピンは縦継ぎ1箇所に1本＝(段数-1)×建枠列数."""
        n_stages = len(self.m.elevation.posts)
        self.assertEqual(
            self.q.qty_of("連結ピン"),
            (n_stages - 1) * self.m.plan.total_posts,
        )

    def test_no_wedge_only_parts(self):
        """枠組では支柱・踏板（くさび式の部材）を使わない."""
        cats = {l.part.category for l in self.q.lines}
        self.assertNotIn("支柱", cats)
        self.assertNotIn("踏板", cats)
        self.assertIn("建枠", cats)
        self.assertIn("布板", cats)

    def test_all_parts_from_frame_series(self):
        for line in self.q.lines:
            self.assertEqual(line.part.series_id, "waku", line.part.model_no)

    def test_cross_braces_cover_all_spans(self):
        n_bays = self.m.plan.total_spans
        n_stages = len(self.m.elevation.posts)
        from ashiba.quantity import QuantityRules

        # 外構面・内構面の両方に入る
        self.assertEqual(
            self.q.qty_of("筋交"),
            n_bays * n_stages * QuantityRules().frame_braces_per_bay,
        )


class TestFrameLawChecks(unittest.TestCase):
    def test_guard_rail_from_frame_not_koma(self):
        """枠組はコマピッチの概念がないので、建枠の手すり高さを使う."""
        m = build_frame()
        self.assertEqual(m.master.koma_pitch, 0)
        self.assertEqual(m.guard_rail_height_mm, FRAME_GUARD_RAIL_HEIGHT_MM)
        self.assertGreaterEqual(m.guard_rail_height_mm, 850)

    def test_all_checks_pass(self):
        m = build_frame()
        s = summary(run_all_checks(m))
        self.assertEqual(s["total"], 12)
        ngs = [c for c in run_all_checks(m) if c.status == "NG"]
        self.assertEqual(ngs, [], [(c.name, c.message) for c in ngs])

    def test_explicit_guard_rail_overrides(self):
        m = build_frame()
        m.config.guard_rail_height_mm = 1000
        self.assertEqual(m.guard_rail_height_mm, 1000)


class TestFrameCornerStepsAreSurfaced(unittest.TestCase):
    """枠組は離れ300固定で端数をコーナーで吸収する。埋めきれない分を黙らせない.

    くさび側の「目標帯を外れた離れには必ず対処案」と対になる不変条件。
    枠組は離れが常に300なので、代わりにコーナーステップで判定する。
    """

    SHAPES = {
        "矩形": RECT,
        "凹み": [(0, 0), (20000, 0), (20000, 10000), (14000, 10000),
                (14000, 7000), (6000, 7000), (6000, 10000), (0, 10000)],
        "L型": [(0, 0), (30000, 0), (30000, 12000), (18000, 12000),
               (18000, 20000), (0, 20000)],
    }

    def _plan(self, poly):
        return solve_plan(poly, load_master("waku"))

    def test_standoff_is_fixed_at_300(self):
        for name, poly in self.SHAPES.items():
            with self.subTest(name):
                for e in self._plan(poly).edges:
                    self.assertEqual(e.standoff, 300.0)

    def test_every_corner_gets_a_step_record(self):
        for name, poly in self.SHAPES.items():
            with self.subTest(name):
                plan = self._plan(poly)
                self.assertEqual(len(plan.corner_steps), len(plan.edges))

    def test_failed_corner_steps_carry_a_message_and_a_warning(self):
        for name, poly in self.SHAPES.items():
            with self.subTest(name):
                plan = self._plan(poly)
                for c in plan.corner_steps:
                    if c.ok:
                        continue
                    where = f"{name} コーナー{c.corner_index} 隙間{c.gap_mm:.0f}"
                    self.assertTrue(c.message, f"{where} が無警告")
                    self.assertIn(f"{c.gap_mm:.0f}mm", c.message, where)
                    self.assertIn(c.message, plan.warnings, where)

    def test_ok_corner_steps_are_within_the_catalog_range(self):
        from ashiba.plan_solver import (
            FRAME_CORNER_MAX_STEP_MM,
            FRAME_CORNER_MIN_GAP_MM,
        )

        for name, poly in self.SHAPES.items():
            with self.subTest(name):
                for c in self._plan(poly).corner_steps:
                    if c.ok:
                        self.assertGreaterEqual(c.gap_mm, FRAME_CORNER_MIN_GAP_MM)
                        self.assertLessEqual(c.gap_mm, FRAME_CORNER_MAX_STEP_MM)


class TestFrameLedgers(unittest.TestCase):
    """枠組でも根がらみと最上層の手すりは布材で組む."""

    def setUp(self):
        self.m = build_frame()
        self.q = take_off(self.m)

    def test_ledgers_are_counted(self):
        """マスタに布材があるのに1本も拾っていなかった."""
        self.assertGreater(self.q.qty_of("布材"), 0)

    def test_count_is_negarami_plus_top_rails(self):
        from ashiba.quantity import QuantityRules

        r = QuantityRules()
        per_span = r.ledgers_negarami + r.rails_per_level_outer
        self.assertEqual(
            self.q.qty_of("布材"), self.m.plan.total_spans * per_span
        )

    def test_rule_is_stated_in_notes(self):
        self.assertTrue(
            any("最上層の手すり" in n for n in self.q.notes), self.q.notes
        )

    def test_intermediate_levels_do_not_add_rails(self):
        """中間層の手すりは1つ上の建枠が兼ねるので、層数に比例しない."""
        low_m, high_m = build_frame(height=8000), build_frame(height=24000)
        self.assertLess(low_m.elevation.n_levels, high_m.elevation.n_levels)
        per_span = [
            take_off(m).qty_of("布材") / m.plan.total_spans
            for m in (low_m, high_m)
        ]
        self.assertEqual(per_span[0], per_span[1])


class TestFrameCrossBraces(unittest.TestCase):
    """交差筋交は外構面・内構面の両方に入る."""

    def test_two_per_bay_by_default(self):
        from ashiba.quantity import QuantityRules

        m = build_frame()
        q = take_off(m)
        n_stages = len(m.elevation.posts)
        self.assertEqual(
            q.qty_of("筋交"),
            m.plan.total_spans * n_stages * QuantityRules().frame_braces_per_bay,
        )

    def test_single_face_is_configurable(self):
        from ashiba.quantity import QuantityRules

        m = build_frame()
        both = take_off(m).qty_of("筋交")
        one = take_off(m, rules=QuantityRules(frame_braces_per_bay=1)).qty_of("筋交")
        self.assertEqual(both, one * 2)

    def test_rule_is_stated_in_notes(self):
        self.assertTrue(
            any("交差筋交は1構面あたり" in n for n in take_off(build_frame()).notes)
        )


class TestFrameSpecificRules(unittest.TestCase):
    """安衛則は足場の種類で条文が違う。枠組に単管の値を当てない."""

    def test_wall_tie_limits_differ_by_system(self):
        frame = build_frame()
        wedge_master = load_master("shinwa_A")
        wedge = ScaffoldModel(
            master=wedge_master, plan=solve_plan(RECT, wedge_master),
            elevation=solve_elevation(16300, master=wedge_master),
            config=ScaffoldConfig(),
        )
        self.assertEqual(frame.wall_tie_limits()[:2], (9000.0, 8000.0))
        self.assertEqual(wedge.wall_tie_limits()[:2], (5000.0, 5500.0))
        self.assertIn("わく組足場", frame.wall_tie_limits()[2])

    def test_low_frame_scaffold_uses_the_stricter_limit(self):
        """わく組の緩和は高さ5m以上のみ（570条1項五号イの括弧書き）."""
        low = build_frame(height=4000)
        self.assertLess(low.scaffold_height_mm, 5000)
        self.assertEqual(low.wall_tie_limits()[:2], (5000.0, 5500.0))

    def test_post_spacing_check_uses_frame_clause(self):
        from ashiba.law_check import check_post_spacing

        c = check_post_spacing(build_frame())
        self.assertEqual(c.status, "OK")
        self.assertIn("わく組足場", c.basis)
        self.assertIn("主わく", c.message)

    def test_submission_form_names_the_right_system(self):
        """届出書に別方式の名前を書かない."""
        self.assertEqual(load_master("waku").system_name, "枠組足場")
        self.assertEqual(load_master("shinwa_A").system_name, "くさび緊結式足場")


class TestFrameDrawingSaysWhatItIs(unittest.TestCase):
    """枠組の図面は建枠を支柱・布材で表現している。そうと書く."""

    def test_series_type_is_w_for_frames(self):
        from ashiba.gdl_params import line_params

        master = load_master("waku")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        self.assertEqual(line_params(m, m.plan.edges[0])["serType"], "W")

    def test_wedge_series_are_a_or_b(self):
        from ashiba.gdl_params import line_params

        for series, want in (("shinwa_A", "A"), ("shinwa_B", "B")):
            with self.subTest(series):
                master = load_master(series)
                m = ScaffoldModel(
                    master=master, plan=solve_plan(RECT, master),
                    elevation=solve_elevation(16300, master=master),
                    config=ScaffoldConfig(), building_height_mm=16000,
                )
                self.assertEqual(line_params(m, m.plan.edges[0])["serType"], want)

    def test_elevation_note_branches_on_the_system(self):
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf"
                / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn('if serType = "W" then', body)
        self.assertIn("建枠の形状は別途", body)
        self.assertIn("根がらみ: 建枠脚部", body)


class TestFrameWordingIsNotWedgeWording(unittest.TestCase):
    """枠組の図書にくさび式の用語（コマ）を書かない."""

    def _model(self, series):
        master = load_master(series)
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def test_negarami_message(self):
        from ashiba.law_check import run_all_checks

        frame = [c for c in run_all_checks(self._model("waku"))
                 if c.check_id == 5][0]
        self.assertIn("建枠脚部", frame.message)
        self.assertNotIn("コマ", frame.message)
        wedge = [c for c in run_all_checks(self._model("shinwa_A"))
                 if c.check_id == 5][0]
        self.assertIn("最下コマ", wedge.message)

    def test_terrain_warning_calls_it_the_adjusting_frame(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        ground = GroundModel(points=[
            (x, y, -x * 0.05) for x in (0, 15000, 30000) for y in (0, 20000)
        ])
        t = solve_post_feet(self._model("waku"), ground)
        over = [w for w in t.warnings if "可動域" in w]
        self.assertTrue(over)
        self.assertIn("調整枠の高さ", over[0])
        self.assertNotIn("コマピッチ", over[0])

    def test_report_header_has_no_koma_pitch_for_frames(self):
        import tempfile

        from ashiba.law_check import run_all_checks
        from ashiba.quantity import take_off
        from ashiba.report import write_report_md

        m = self._model("waku")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "r.md"
            write_report_md(m, take_off(m), run_all_checks(m), path, "枠組")
            head = path.read_text(encoding="utf-8").split("## ")[0]
        self.assertIn("建枠を積む方式", head)
        self.assertNotIn("コマピッチ", head)


class TestSpanIsNotAssumed1800(unittest.TestCase):
    """インチ規格（1829）の系列で、1800決め打ちの判定がずれないこと."""

    RECESS = [(0, 0), (20000, 0), (20000, 10000), (12000, 10000),
              (12000, 8000), (8000, 8000), (8000, 10000), (0, 10000)]

    def test_one_span_face_is_not_counted_as_a_gap(self):
        """1スパンぶんの面は両隣で拘束される。1829>1800で計上すると過大になる."""
        master = load_master("waku")
        m = ScaffoldModel(
            master=master, plan=solve_plan(self.RECESS, master),
            elevation=solve_elevation(9100, master=master),
            config=ScaffoldConfig(), building_height_mm=9000,
        )
        short = [e for e in m.plan.edges
                 if len(e.spans) == 1
                 and not [t for t in m.wall_ties if t.edge_index == e.edge_index]]
        self.assertTrue(short, "1スパンで壁つなぎ0本の面が無い")
        _v, h_max = m.wall_tie_max_spacing()
        for e in short:
            self.assertNotAlmostEqual(h_max, e.scaffold_length, places=1)


class TestFrameLegs(unittest.TestCase):
    """建枠1枚は2脚。脚まわりの部材を建枠の枚数で数えない."""

    def setUp(self):
        master = load_master("waku")
        self.model = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        self.q = take_off(self.model)

    def test_jacks_and_bases_are_two_per_frame_line(self):
        n = self.model.plan.total_posts
        jack = sum(l.qty for l in self.q.lines
                   if l.part.category == "ジャッキ" and "アンダー" not in l.part.note)
        base = sum(l.qty for l in self.q.lines
                   if l.part.category == "ジャッキ" and "アンダーベース" in l.part.note)
        self.assertEqual(jack, n * 2)
        self.assertEqual(base, n * 2)

    def test_same_leg_count_as_the_wedge_system(self):
        """同じ外形なら脚の数は方式によらない（片方だけ半分になっていた）."""
        master = load_master("shinwa_A")
        wedge = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        # くさび式は出隅の外側コーナー支柱（ジャッキ＋アンダーベース）が四隅に加わる
        self.assertEqual(
            take_off(wedge).qty_of("ジャッキ") - 2 * wedge.outer_corner_posts(), self.q.qty_of("ジャッキ")
        )


class TestFrameCannotBeSingleRow(unittest.TestCase):
    """建枠は内外2列を成す。一側足場という指定は成り立たない."""

    def _model(self, form):
        master = load_master("waku")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(scaffold_form=form),
            building_height_mm=16000, clearance_space_mm=500,
        )

    def test_combination_is_ng(self):
        from ashiba.law_check import run_all_checks

        c = [r for r in run_all_checks(self._model("一側足場")) if r.check_id == 1][0]
        self.assertEqual(c.status, "NG")
        self.assertIn("枠組", c.message)

    def test_quantity_and_check_do_not_change(self):
        """NGの組合せで数量・検定だけ静かに変わると、誤りに気づけない."""
        from ashiba.quantity import take_off
        from ashiba.structural import run_structural

        a, b = self._model("本足場"), self._model("一側足場")
        qa, qb = take_off(a), take_off(b)
        self.assertEqual(qa.total_weight_kg, qb.total_weight_kg)
        self.assertEqual(qa.qty_of("建枠"), qb.qty_of("建枠"))
        self.assertEqual(
            run_structural(a, qa).post.ratio, run_structural(b, qb).post.ratio
        )


class TestFrameDrawingsMatchTheTakeOff(unittest.TestCase):
    """枠組の中間層は布材の手すり・中桟を描かない（数量は最上層だけ拾う）."""

    def test_scripts_gate_the_rails_on_the_top_level(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"
        for name in ("3d.gdl", "2d.gdl"):
            body = (root / name).read_text(encoding="utf-8")
            self.assertIn('if serType = "W" and il < nLv then frMid = 1', body, name)
            self.assertIn("frMid = 0", body, name)


if __name__ == "__main__":
    unittest.main()


class TestFrameCorners(unittest.TestCase):
    """枠組のコーナー処理（仕様4.2の分岐）.

    くさび式は端数を壁離れで吸収するが、枠組は建枠が定尺なので
    離れを固定し、余りをコーナーステップで吸収する。
    さらに建枠を90度回して納めるため70mm以上の隙間が要る。
    """

    LSHAPE = [(0, 0), (30000, 0), (30000, 12000),
              (18000, 12000), (18000, 20000), (0, 20000)]

    def test_standoff_is_fixed_not_adjusted(self):
        """枠組は離れを動かさない（くさび式との違い）."""
        from ashiba.plan_solver import StandoffSpec, solve_plan
        m = load_master("waku")
        plan = solve_plan(RECT, m, StandoffSpec(target=300.0))
        self.assertEqual(set(plan.standoffs), {300.0})

    def test_wedge_still_adjusts_standoff(self):
        """くさび式は従来どおり離れで吸収する（分岐が効いていること）."""
        from ashiba.plan_solver import solve_plan
        plan = solve_plan(RECT, load_master("shinwa_A"))
        self.assertGreater(len(set(plan.standoffs)), 1)

    def test_corner_gap_at_least_70mm(self):
        """建枠を90度回して納めるのに要る隙間を確保する."""
        from ashiba.plan_solver import FRAME_CORNER_MIN_GAP_MM, solve_plan
        m = load_master("waku")
        for name, poly in (("矩形", RECT), ("L型", self.LSHAPE)):
            with self.subTest(shape=name):
                plan = solve_plan(poly, m)
                self.assertTrue(plan.corner_steps)
                for cs in plan.corner_steps:
                    self.assertGreaterEqual(cs.gap_mm, FRAME_CORNER_MIN_GAP_MM)

    def test_oversized_gap_is_flagged(self):
        """コーナーステップで埋めきれない隙間は黙って通さない."""
        from ashiba.plan_solver import FRAME_CORNER_MAX_STEP_MM, solve_plan
        plan = solve_plan(self.LSHAPE, load_master("waku"))
        over = [cs for cs in plan.corner_steps
                if cs.gap_mm > FRAME_CORNER_MAX_STEP_MM]
        for cs in over:
            self.assertFalse(cs.ok)
            self.assertIn("コーナーステップ", cs.message)
            self.assertTrue(any(cs.message == w for w in plan.warnings))

    def test_spans_fit_within_target_length(self):
        """スパン合計は離れ固定で決まる面長を超えない（超えると躯体に当たる）."""
        from ashiba.plan_solver import solve_plan
        m = load_master("waku")
        plan = solve_plan(RECT, m)
        for ep, e in zip(plan.edges, plan.outline.edges):
            target = e.length + (e.start_sign + e.end_sign) * ep.standoff
            self.assertLessEqual(sum(ep.spans), target + 1e-6)

    def test_one_corner_step_per_corner(self):
        plan = solve_plan(self.LSHAPE, load_master("waku"))
        self.assertEqual(len(plan.corner_steps), len(plan.edges))
        self.assertEqual(
            sorted(cs.corner_index for cs in plan.corner_steps),
            list(range(len(plan.edges))),
        )


class TestAdvanceRailOnFrameIsNotSilent(unittest.TestCase):
    def test_warning_when_specified(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        spec = json.loads(Path(__file__).resolve().parents[1].joinpath(
            "examples", "waku_frame.json").read_text(encoding="utf-8"))
        spec["guard_rail_type"] = "先行手すり"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        self.assertTrue([w for w in r.model.plan.warnings if "先行手すり工法" in w and "無視" in w])
        self.assertEqual(r.quantity.qty_of("先行手摺"), 0)



class TestFrameSpansPreferLongFrames(unittest.TestCase):
    """建枠間隔610がマスタにあっても、面を610×50で埋めない.

    隙間の小ささだけで構成を選んでいたため、日建カタログの手摺A28（610）を
    足した途端に30m面が610×50スパンになり、建枠・筋違・布板が3倍になった。
    コーナーステップで埋められる隙間なら、スパン数が最少の構成を採る。
    """

    def test_thirty_metre_face_uses_1829_frames(self):
        from ashiba.plan_solver import solve_plan

        m = load_master("waku")
        self.assertIn(610, m.span_lengths())
        plan = solve_plan([(0, 0), (30000, 0), (30000, 20000), (0, 20000)], m)
        for e in plan.edges:
            self.assertLessEqual(len(e.spans), 18, (e.edge_index, e.spans))
            self.assertGreaterEqual(e.spans.count(1829), 10, e.spans)
        for cs in plan.corner_steps:
            self.assertTrue(cs.ok, cs.message)

    def test_gap_is_still_within_the_corner_step(self):
        from ashiba.plan_solver import (FRAME_CORNER_MAX_STEP_MM, FRAME_CORNER_MIN_GAP_MM,
                                        _frame_spans_and_gap)

        spans, gap = _frame_spans_and_gap([1829, 1524, 1219, 914, 610], 30600)
        self.assertGreaterEqual(gap, FRAME_CORNER_MIN_GAP_MM)
        self.assertLessEqual(gap, FRAME_CORNER_MAX_STEP_MM)
        self.assertLess(len(spans), 20)


class TestFrameStackPrefersStandardFrames(unittest.TestCase):
    """同じ枚数なら標準枠（最大高さ）を多く使う.

    刻みの細かい調整枠（1524/1219/914/490）が揃うと、枚数だけの評価では
    1700×5＋1524×5 のような構成が選ばれていた。9×1700＋914 と同じ10枚なら
    調整枠が1枚の方を採る。
    """

    def test_16300_uses_nine_standard_frames(self):
        m = load_master("waku")
        r = solve_elevation_frame(16300, m)
        self.assertEqual(r.total_height, 16300)
        self.assertEqual(r.posts.count(1700), 9, r.posts)
        self.assertLessEqual(sum(1 for p in r.posts if p != 1700), 1, r.posts)
