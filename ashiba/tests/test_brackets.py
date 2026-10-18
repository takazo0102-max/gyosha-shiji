import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.brackets import (
    INNER,
    OUTER,
    BracketSection,
    bracket_quantities,
    validate_bracket_sections,
)
from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def make_model(height=16300):
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)),
        building_height_mm=16000,
    )


def ng(issues):
    return [i for i in issues if i.severity == "NG"]


class TestBracketValidation(unittest.TestCase):
    def setUp(self):
        self.m = make_model()

    def test_valid_section_passes(self):
        s = BracketSection(edge_index=0, start_mm=12000, end_mm=18000,
                           direction=INNER, width=300, reason="躯体凹凸への床追従")
        self.assertEqual(ng(validate_bracket_sections(self.m, [s])), [])

    def test_section_beyond_edge_rejected(self):
        edge_len = self.m.plan.edges[0].scaffold_length
        s = BracketSection(edge_index=0, start_mm=0, end_mm=edge_len + 1000)
        issues = ng(validate_bracket_sections(self.m, [s]))
        self.assertTrue(any("面長" in i.message for i in issues))

    def test_unknown_edge_rejected(self):
        s = BracketSection(edge_index=99, start_mm=0, end_mm=1800)
        self.assertTrue(ng(validate_bracket_sections(self.m, [s])))

    def test_opposite_directions_overlapping_rejected(self):
        a = BracketSection(edge_index=0, start_mm=0, end_mm=5400, direction=INNER)
        b = BracketSection(edge_index=0, start_mm=3600, end_mm=9000, direction=OUTER)
        issues = ng(validate_bracket_sections(self.m, [a, b]))
        self.assertTrue(any("逆向き" in i.message for i in issues))

    def test_same_direction_overlapping_allowed(self):
        a = BracketSection(edge_index=0, start_mm=0, end_mm=5400, direction=INNER)
        b = BracketSection(edge_index=0, start_mm=3600, end_mm=9000, direction=INNER)
        self.assertEqual(ng(validate_bracket_sections(self.m, [a, b])), [])

    def test_different_levels_do_not_conflict(self):
        a = BracketSection(edge_index=0, start_mm=0, end_mm=5400,
                           direction=INNER, levels=[1])
        b = BracketSection(edge_index=0, start_mm=0, end_mm=5400,
                           direction=OUTER, levels=[2])
        self.assertEqual(ng(validate_bracket_sections(self.m, [a, b])), [])

    def test_widening_twice_rejected(self):
        a = BracketSection(edge_index=0, start_mm=0, end_mm=3600, is_widening=True)
        b = BracketSection(edge_index=1, start_mm=0, end_mm=3600, is_widening=True)
        issues = ng(validate_bracket_sections(self.m, [a, b]))
        self.assertTrue(any("1回まで" in i.message for i in issues))

    def test_kessokubu_widening_requires_hozue(self):
        s = BracketSection(edge_index=0, start_mm=0, end_mm=3600, width=400,
                           is_widening=True, on_kessokubu=True, has_hozue=False)
        issues = ng(validate_bracket_sections(self.m, [s]))
        self.assertTrue(any("方杖" in i.message for i in issues))
        s.has_hozue = True
        self.assertEqual(
            [i for i in ng(validate_bracket_sections(self.m, [s])) if "方杖" in i.message],
            [],
        )

    def test_widening_ratio_rule(self):
        """拡幅は下層建地間隔が上層の60%以上（仕様4.3）.

        この足場の建地間隔は670mm。幅400なら 670/1070=63% で可、
        幅600だと 670/1270=53% で不可。
        """
        s = BracketSection(edge_index=0, start_mm=0, end_mm=3600, width=400,
                           is_widening=True)
        self.assertEqual(
            [i for i in ng(validate_bracket_sections(self.m, [s])) if "60%" in i.message],
            [],
        )
        s.width = 600
        self.assertTrue(any("60%" in i.message
                            for i in ng(validate_bracket_sections(self.m, [s]))))

    def test_invalid_level_rejected(self):
        s = BracketSection(edge_index=0, start_mm=0, end_mm=1800, levels=[99])
        self.assertTrue(ng(validate_bracket_sections(self.m, [s])))


class TestBracketQuantity(unittest.TestCase):
    def setUp(self):
        self.m = make_model()

    def test_counts_posts_times_levels(self):
        # 1800×3スパン分＝支柱4本、全層(8層)
        s = BracketSection(edge_index=0, start_mm=0, end_mm=5400,
                           direction=INNER, width=400)
        q = bracket_quantities(self.m, [s])
        self.assertEqual(q[(400, INNER)], 4 * self.m.elevation.n_levels)

    def test_levels_limit_quantity(self):
        s = BracketSection(edge_index=0, start_mm=0, end_mm=5400,
                           direction=INNER, width=400, levels=[1, 2])
        self.assertEqual(bracket_quantities(self.m, [s])[(400, INNER)], 4 * 2)

    def test_hozue_counted(self):
        s = BracketSection(edge_index=0, start_mm=0, end_mm=1800, width=400,
                           has_hozue=True, levels=[1])
        q = bracket_quantities(self.m, [s])
        self.assertEqual(q[(400, "方杖")], 2)

    def test_flows_into_takeoff(self):
        s = BracketSection(edge_index=0, start_mm=0, end_mm=5400,
                           direction=INNER, width=400, levels=[1])
        base = take_off(self.m)
        with_bracket = take_off(self.m, bracket_sections=[s])
        self.assertGreater(
            with_bracket.qty_of("ブラケット"), base.qty_of("ブラケット")
        )
        # 重量はブラケット分が増え、外した躯体側手すり分が減る（単純増ではない）
        self.assertNotEqual(with_bracket.total_weight_kg, base.total_weight_kg)

    def test_post_positions_unchanged_by_brackets(self):
        """ブラケットは面の区間属性であり、支柱ラインを動かさない（仕様4.3）."""
        before = self.m.plan.post_positions()
        s = BracketSection(edge_index=0, start_mm=0, end_mm=5400, width=600)
        validate_bracket_sections(self.m, [s])
        bracket_quantities(self.m, [s])
        self.assertEqual(self.m.plan.post_positions(), before)


class TestBracketDeckWidth(unittest.TestCase):
    """区間の踏板幅指定が数量に反映されること（受け取るだけで無視していた）."""

    def setUp(self):
        from ashiba.brackets import bracket_deck_changes

        self.changes = bracket_deck_changes
        self.m = make_model()

    def _qty(self, model_no, result, category="踏板"):
        # 信和の踊り場は踏板 SD-4018T で構成するので、同じ品番の行が踊り場にもある。
        # 踏板の行だけ見る
        return next((l.qty for l in result.lines
                     if l.part.model_no == model_no and l.part.category == category), 0)

    def test_only_spans_fully_inside_are_changed(self):
        """区間をまたぐスパンは敷き替えられない."""
        sec = BracketSection(
            edge_index=0, start_mm=0, end_mm=5400, width=400,
            deck_width=500, levels=[1],
        )
        got = self.changes(self.m, [sec])
        self.assertEqual(len(got), 3)          # 1800×3スパンが収まる
        self.assertTrue(all(sum(c[:1]) == 1800 for c in got))

    def test_take_off_swaps_the_deck_part(self):
        sec = BracketSection(
            edge_index=0, start_mm=0, end_mm=5400, width=400,
            deck_width=500, levels=[1, 2],
        )
        base = take_off(self.m)
        with_sec = take_off(self.m, bracket_sections=[sec])
        self.assertEqual(
            self._qty("SD-4018T", base) - self._qty("SD-4018T", with_sec), 6
        )
        self.assertEqual(self._qty("SD-5018T", with_sec), 6)
        # 踊り場（同じ品番 SD-4018T）の行は踏板の行と別に残り、敷き替えで減らない
        self.assertEqual(self._qty("SD-4018T", base, "踊り場"),
                         self._qty("SD-4018T", with_sec, "踊り場"))

    def test_missing_width_is_reported_not_dropped(self):
        sec = BracketSection(
            edge_index=0, start_mm=0, end_mm=5400, width=400,
            deck_width=9999, levels=[1],
        )
        q = take_off(self.m, bracket_sections=[sec])
        self.assertTrue(
            any("マスタにありません" in n and "9999" in n for n in q.notes), q.notes
        )

    def test_no_width_given_changes_nothing(self):
        sec = BracketSection(edge_index=0, start_mm=0, end_mm=5400, width=400)
        self.assertEqual(self.changes(self.m, [sec]), [])


class TestOuterBracketEdge(unittest.TestCase):
    """張出すと作業床の外縁が建地より外に出る。その縁の手すり・幅木が要る."""

    def setUp(self):
        master = load_master("shinwa_A")
        self.m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        self.base = take_off(self.m)

    def _sec(self, direction):
        return [BracketSection(edge_index=0, start_mm=0, end_mm=5400,
                               direction=direction, width=600, levels=[1, 2])]

    def test_outer_section_adds_rails_and_toe_boards(self):
        q = take_off(self.m, bracket_sections=self._sec("張出"))
        # 3スパン×2層＝6セル。新しい縁に手すり＋中桟2本・幅木1本を足し、建地位置の
        # 外側手すり・中桟2本・幅木1本（床の途中に立つことになる）を外すので差は0
        # 妻側（両端）: 手すり・中桟 2箇所×2本×2層＝8本、幅木 2箇所×2層＝4本
        self.assertEqual(q.qty_of("布材") - self.base.qty_of("布材"), 12 - 12 + 8)
        self.assertEqual(q.qty_of("幅木") - self.base.qty_of("幅木"), 6 - 6 + 4)
        self.assertEqual(q.qty_of("布材", 600) - self.base.qty_of("布材", 600), 8)
        # 縁の部材が別行で入っていること
        edge_rails = sum(qty for what, qty in q.breakdown_for("布材") if "張出し外縁" in what) \
            if hasattr(q, "breakdown_for") else None
        if edge_rails is not None:
            self.assertEqual(edge_rails, 12)

    def test_inner_section_does_not(self):
        """内側は躯体に面する。開放端にならないので手すり・幅木は足さない。
        むしろ拡幅で隙間が小さくなるので、躯体側の手すり・中桟（2本×3スパン×2層）を外す."""
        q = take_off(self.m, bracket_sections=self._sec("内"))
        self.assertEqual(q.qty_of("布材"), self.base.qty_of("布材") - 6 * 2)
        self.assertEqual(q.qty_of("幅木"), self.base.qty_of("幅木"))

    def test_open_edge_is_flagged(self):
        issues = validate_bracket_sections(self.m, self._sec("張出"))
        hit = [i for i in issues if "開放端" in i.message]
        self.assertTrue(hit, issues)
        self.assertIn("563", hit[0].basis)

    def test_drawing_shows_the_edge_rails(self):
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf"
                / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("bkLen", body)
        self.assertIn("開放端", body)


class TestFrameSystemAlsoCounts(unittest.TestCase):
    """枠組式でも区間指定が数量に届くこと（届かず黙って消えていた）."""

    def _model(self, series_id):
        master = load_master(series_id)
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def _section(self, model):
        edge = model.plan.edges[0]
        return [BracketSection(
            edge_index=0, start_mm=0, end_mm=sum(edge.spans[:3]),
            direction="内", width=400, levels=[1, 2],
        )]

    def test_missing_master_part_is_reported_not_ignored(self):
        m = self._model("waku")
        q = take_off(m, bracket_sections=self._section(m))
        self.assertTrue(
            any("ブラケット" in w and "手配" in w for w in q.warnings), q.warnings
        )

    def test_width_without_a_catalog_part_is_ordered_not_dropped(self):
        """信和の内ブラケット300は型番仮を外した（カタログ p41 の伸縮品は320〜505）。
        マスタに無い幅は0本で黙らず、手配項目に幅と本数を出す."""
        m = self._model("shinwa_A")
        sec = self._section(m)
        sec[0].width = 300
        q = take_off(m, bracket_sections=sec)
        hit = [w for w in q.warnings if "ブラケット300mm" in w and "手配" in w]
        self.assertTrue(hit, q.warnings)
        self.assertIn(f"（{2 * 4}本）", hit[0])

    def test_wedge_system_still_counts_parts(self):
        m = self._model("shinwa_A")
        base = take_off(m)
        q = take_off(m, bracket_sections=self._section(m))
        self.assertGreater(q.qty_of("ブラケット"), 0)
        self.assertNotEqual(q.total_weight_kg, base.total_weight_kg)




class TestZeroWidthBracketIsRejected(unittest.TestCase):
    def test_width_zero_is_ng(self):
        from ashiba.brackets import BracketSection, validate_bracket_sections
        from ashiba.elevation_solver import solve_elevation
        from ashiba.master import load_master
        from ashiba.model import ScaffoldConfig, ScaffoldModel
        from ashiba.plan_solver import solve_plan

        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master,
            plan=solve_plan([(0, 0), (30000, 0), (30000, 20000), (0, 20000)], master),
            elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
        )
        issues = validate_bracket_sections(m, [BracketSection(
            edge_index=0, start_mm=5400, end_mm=9000, direction="張出", width=0)])
        self.assertTrue([i for i in issues if i.severity == "NG" and "ブラケット幅" in i.message],
                        [i.message for i in issues])



class TestAdjustableBracketsAreFound(unittest.TestCase):
    """伸縮ブラケットは呼び幅が範囲に入れば当てる（完全一致だけだと「マスタに無い」）."""

    def test_part_covers(self):
        from ashiba.master import Part

        adj = Part("x", "ブラケット", "T", 750, 750, 0, 5.5, "張出用 伸縮ブラケット500〜750")
        fixed = Part("x", "ブラケット", "F", 600, 580, 0, 2.5, "踏板500用")
        self.assertEqual(adj.adjustable_range(), (500, 750))
        self.assertTrue(adj.covers(600))
        self.assertFalse(adj.covers(400))
        self.assertIsNone(fixed.adjustable_range())
        self.assertTrue(fixed.covers(600))
        self.assertFalse(fixed.covers(610))

    def test_exact_part_wins_over_adjustable(self):
        from ashiba.master import load_master

        m = load_master("nikken_nd1800")
        self.assertEqual(m.bracket_for(600, outward=False).model_no, "NDBK06C")
        # 400 は定尺が無いので伸縮 360〜475 の NDBK3647C
        self.assertEqual(m.bracket_for(400, outward=False).model_no, "NDBK3647C")
        self.assertIsNone(m.bracket_for(200, outward=False))

    def test_frame_outward_section_uses_twl(self):
        from ashiba.brackets import BracketSection
        from ashiba.elevation_solver import solve_elevation
        from ashiba.master import load_master
        from ashiba.model import ScaffoldConfig, ScaffoldModel
        from ashiba.plan_solver import solve_plan
        from ashiba.quantity import take_off

        master = load_master("waku")
        rect = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
        m = ScaffoldModel(master=master, plan=solve_plan(rect, master),
                          elevation=solve_elevation(16300, master=master),
                          config=ScaffoldConfig(), building_height_mm=16000)
        sec = [BracketSection(edge_index=0, start_mm=0, end_mm=5487, width=600,
                              direction="張出", levels=[1])]
        q = take_off(m, bracket_sections=sec)
        self.assertGreater(sum(l.qty for l in q.lines if l.part.model_no == "TWL750"), 0)
        self.assertFalse([w for w in q.warnings if "ブラケット600mm" in w and "ありません" in w], q.warnings)
        self.assertTrue([n for n in q.notes if "TWL750" in n and "合わせて使う" in n], q.notes)


if __name__ == "__main__":
    unittest.main()



class TestAutoInnerBracket(unittest.TestCase):
    """離れ350超の面に内ブラケット＋踏板を自動で付ける（インチ30×20mで離れ364/394になる）."""

    def _solve(self, **extra):
        from ashiba.cli import solve_all

        spec = {"project_name": "内ブラ", "module": "inch",
                "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 16000, "building_height_mm": 16000}
        spec.update(extra)
        return solve_all(spec)

    def test_wide_standoff_faces_get_inner_brackets(self):
        r = self._solve()
        auto = [b for b in r.brackets if getattr(b, "auto", False)]
        wide = [e for e in r.model.plan.edges if e.standoff > 350]
        self.assertTrue(wide)
        self.assertEqual({b.edge_index for b in auto}, {e.edge_index for e in wide})
        for b in auto:
            ep = next(e for e in r.model.plan.edges if e.edge_index == b.edge_index)
            gap = ep.standoff - b.inner_deck_width - 25
            self.assertTrue(50 <= gap <= 300, gap)
            self.assertIsNone(ep.remedy)
            self.assertEqual(b.end_mm, ep.scaffold_length)
        ws = r.model.plan.warnings
        self.assertEqual(sum("付けました" in w for w in ws), len(auto))
        self.assertFalse(any("検討してください" in w for w in ws))         # 措置前の注意は消える
        self.assertFalse(any("躯体側手すり材は数量に含んでいません" in str(n) for n in r.quantity.notes))

    def test_quantity_has_the_brackets_and_the_planks(self):
        r = self._solve()
        q = r.quantity
        auto = [b for b in r.brackets if getattr(b, "auto", False)]
        deck_w = auto[0].inner_deck_width
        notes = [ln.note for ln in q.lines]
        part = r.model.master.bracket_for(auto[0].width, outward=False)
        self.assertGreater(q.qty_of("ブラケット", part.nominal_dim), 0)
        self.assertTrue(any(f"内ブラケットの踏板 幅{deck_w}" in (n or "") for n in notes)
                        or q.qty_of(r.model.master.deck_category) > 0)

    def test_drawing_reach_is_the_plank_not_the_arm(self):
        from ashiba.gdl_params import line_params

        r = self._solve()
        b = next(b for b in r.brackets if getattr(b, "auto", False))
        ep = next(e for e in r.model.plan.edges if e.edge_index == b.edge_index)
        p = line_params(r.model, ep, bracket_sections=r.brackets)
        vals = p["brktList"].split(",")
        self.assertEqual(int(vals[2]), b.inner_deck_width + 25)        # 腕の呼び（400）ではなく踏板＋支柱半径
        self.assertLess(int(vals[2]), ep.standoff)                      # 躯体に当たらない

    def test_can_be_turned_off_and_does_not_touch_input_brackets(self):
        r = self._solve(auto_inner_bracket=False)
        self.assertFalse(any(getattr(b, "auto", False) for b in r.brackets))
        r2 = self._solve(bracket_sections=[{"face": "南面", "start_mm": 0, "end_mm": 3658, "width": 350, "direction": "内"}])
        south = next(e for e in r2.model.plan.edges if r2.model.face_name(e.edge_index) == "南面")
        self.assertFalse(any(getattr(b, "auto", False) and b.edge_index == south.edge_index for b in r2.brackets))

    def test_metric_rect_within_band_gets_none(self):
        r = self._solve(module="metric")
        self.assertFalse(any(getattr(b, "auto", False) for b in r.brackets))


class TestAutoInnerAvoidsOuterBrackets(unittest.TestCase):
    """入力の張出区間とは重ねない（逆向き取付禁止）。残りの範囲にだけ付け、措置の注意は残す."""

    def test_carves_around_the_outer_section(self):
        from ashiba.cli import solve_all

        spec = {"project_name": "張出と内", "series_id": "nikken_nd1800",
                "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 16000, "building_height_mm": 16000,
                "bracket_sections": [{"edge_index": 0, "start_mm": 0, "end_mm": 7316, "width": 350,
                                      "direction": "張出", "levels": [2, 3]}]}
        r = solve_all(spec)
        auto0 = [b for b in r.brackets if b.auto and b.edge_index == 0]
        self.assertEqual([(b.start_mm, b.end_mm) for b in auto0],
                         [(7316, r.model.plan.edges[0].scaffold_length)])
        self.assertFalse(any("逆向き" in i.message for i in r.bracket_issues))
        self.assertIsNotNone(r.model.plan.edges[0].remedy)            # 張出の範囲は詰まっていない
        self.assertTrue(any("張出ブラケットの範囲は除く" in w for w in r.model.plan.warnings))
