"""足場ラインGDLへ渡すパラメータのテスト.

GDL側で komaPitch から作業床高さや手すり高さを再計算すると、コマの概念が
無い枠組（komaPitch=0）で破綻し、ソルバの結果と図面がずれる。
Python側の解をそのまま渡していることを検査する。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.gdl_params import line_params, placement_of

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(series_id):
    master = load_master(series_id)
    plan = solve_plan(RECT, master)
    return ScaffoldModel(
        master=master, plan=plan,
        elevation=solve_elevation(16300, master=master),
        config=ScaffoldConfig(),
    )


class TestLineParams(unittest.TestCase):
    def test_levels_come_from_the_solver(self):
        for sid in ("shinwa_A", "shinwa_B", "waku"):
            with self.subTest(sid):
                m = build(sid)
                p = line_params(m, m.plan.edges[0])
                self.assertEqual(
                    p["levelList"],
                    ",".join(str(h) for h in m.elevation.level_heights),
                )

    def test_rail_heights_are_nonzero_for_frames(self):
        """枠組は komaPitch=0。手すり高さを komaPitch から作ると作業床に重なって消える."""
        m = build("waku")
        p = line_params(m, m.plan.edges[0])
        self.assertEqual(p["komaPitch"], 0.0)
        self.assertGreater(p["railH"], 0)
        self.assertGreater(p["midH"], 0)
        self.assertGreater(p["railH"], p["midH"])

    def test_row_width_and_deck_widths_follow_the_series(self):
        """既定値のままだと系列に関係なくA系列の幅で描かれる."""
        widths = {
            sid: line_params(build(sid), build(sid).plan.edges[0])
            for sid in ("shinwa_A", "shinwa_B", "waku")
        }
        self.assertNotEqual(widths["shinwa_A"]["deckW1"], widths["waku"]["deckW1"])
        for sid, p in widths.items():
            m = build(sid)
            with self.subTest(sid):
                # 建地列の間隔は発注する腕木（枠組は建枠幅）の寸法と一致させる。
                # 作業床の被覆幅で描くと、部材表と図面が食い違う
                self.assertAlmostEqual(p["rowW"], m.post_row_spacing_mm / 1000.0)
                self.assertAlmostEqual(
                    p["deckW1"], m.config.deck_widths[0] / 1000.0
                )

    def test_drawing_row_width_matches_the_ordered_ledger(self):
        from ashiba.quantity import take_off

        m = build("shinwa_A")
        rowW_mm = round(line_params(m, m.plan.edges[0])["rowW"] * 1000)
        udegi = [
            l for l in take_off(m).lines
            if l.part.category == "布材" and l.part.nominal_dim == rowW_mm
        ]
        self.assertTrue(udegi, f"腕木{rowW_mm}が数量表に無い")

    def test_plan_and_elevation_share_the_same_geometry(self):
        """平面と立面で別々に組み立てると片方だけ渡し漏れる."""
        m = build("shinwa_A")
        p = line_params(m, m.plan.edges[0])
        for key in ("rowW", "deckW1", "levelList", "railH", "negaH"):
            self.assertIn(key, p)


class TestSingleRowScaffold(unittest.TestCase):
    """一側足場は建地1列。渡さないと図面は本足場（2列）で描かれる."""

    def _model(self, form):
        master = load_master("shinwa_A")
        plan = solve_plan(RECT, master)
        return ScaffoldModel(
            master=master, plan=plan,
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(scaffold_form=form),
        )

    def test_row_count_follows_the_form(self):
        for form, want in (("本足場", 2), ("一側足場", 1)):
            with self.subTest(form):
                m = self._model(form)
                self.assertEqual(line_params(m, m.plan.edges[0])["nRows"], want)

    def test_quantity_and_drawing_agree_on_the_row_count(self):
        """数量は1列で拾うのに図面が2列、という食い違いを防ぐ."""
        from ashiba.quantity import take_off

        single = self._model("一側足場")
        double = self._model("本足場")
        jacks_single = take_off(single).qty_of("ジャッキ")
        jacks_double = take_off(double).qty_of("ジャッキ")
        self.assertEqual(jacks_double, jacks_single * 2)
        self.assertEqual(
            line_params(double, double.plan.edges[0])["nRows"],
            2 * line_params(single, single.plan.edges[0])["nRows"],
        )


class TestBraceSpacingMatchesTakeOff(unittest.TestCase):
    """図面のブレス本数が部材表と食い違わないこと."""

    def test_wedge_uses_the_take_off_interval(self):
        from ashiba.quantity import QuantityRules

        r = QuantityRules()
        p = line_params(build("shinwa_A"), build("shinwa_A").plan.edges[0])
        self.assertEqual(p["braceEveryS"], r.brace_every_spans)
        self.assertEqual(p["braceEveryL"], r.brace_every_levels)
        self.assertGreater(p["braceEveryS"], 1)

    def test_frame_draws_every_bay(self):
        """枠組の交差筋交は建枠と一体で全構面に入る."""
        m = build("waku")
        p = line_params(m, m.plan.edges[0])
        self.assertEqual((p["braceEveryS"], p["braceEveryL"]), (1, 1))

    def test_custom_rules_are_reflected(self):
        from ashiba.quantity import QuantityRules

        m = build("shinwa_A")
        p = line_params(
            m, m.plan.edges[0],
            rules=QuantityRules(brace_every_spans=1, brace_every_levels=1),
        )
        self.assertEqual((p["braceEveryS"], p["braceEveryL"]), (1, 1))


class TestAsagaoReachesTheDrawing(unittest.TestCase):
    """朝顔は数量にも法規チェックにも出るのに、図面・3Dに現れていなかった."""

    def _model(self, stages, height=16300):
        from ashiba.model import AsagaoSpec

        master = load_master("shinwa_A")
        plan = solve_plan(RECT, master)
        return ScaffoldModel(
            master=master, plan=plan,
            elevation=solve_elevation(height, master=master),
            config=ScaffoldConfig(
                asagao=AsagaoSpec(stages=stages) if stages else None
            ),
        )

    def test_heights_are_work_deck_levels(self):
        m = self._model(2, height=25000)
        hs = m.asagao_heights()
        self.assertEqual(len(hs), 2)
        for h in hs:
            self.assertIn(h, m.elevation.level_heights)

    def test_first_stage_is_around_4_to_5m(self):
        m = self._model(1)
        self.assertTrue(3000 <= m.asagao_heights()[0] <= 6000, m.asagao_heights())

    def test_explicit_heights_win(self):
        m = self._model(1)
        m.config.asagao.heights_mm = [8200]
        self.assertEqual(m.asagao_heights(), [8200])

    def test_params_carry_the_heights(self):
        m = self._model(1)
        p = line_params(m, m.plan.edges[0])
        self.assertEqual(
            p["asagaoList"], ",".join(str(h) for h in m.asagao_heights())
        )
        self.assertGreater(p["asagaoProj"], 0)

    def test_no_asagao_means_empty_list(self):
        m = self._model(0)
        self.assertEqual(m.asagao_heights(), [])
        self.assertEqual(line_params(m, m.plan.edges[0])["asagaoList"], "")


class TestStairsReachTheDrawing(unittest.TestCase):
    """階段室の位置は計画図の主要情報。図面に出ていなかった."""

    def setUp(self):
        from ashiba.stairs import auto_place_stairs

        self.m = build("shinwa_A")
        self.plan = auto_place_stairs(self.m)

    def test_each_edge_gets_only_its_own_towers(self):
        for ep in self.m.plan.edges:
            p = line_params(self.m, ep, stair_plan=self.plan)
            mine = [t for t in self.plan.towers if t.edge_index == ep.edge_index]
            got = [v for v in p["stairList"].split(",") if v]
            self.assertEqual(len(got), len(mine) * 2, ep.edge_index)

    def test_pairs_are_start_and_length(self):
        ep = next(
            e for e in self.m.plan.edges
            if any(t.edge_index == e.edge_index for t in self.plan.towers)
        )
        t = next(t for t in self.plan.towers if t.edge_index == ep.edge_index)
        vals = line_params(self.m, ep, stair_plan=self.plan)["stairList"].split(",")
        self.assertEqual(int(vals[0]), int(t.start_mm))
        self.assertEqual(int(vals[1]), int(t.length_mm))

    def test_empty_without_a_plan(self):
        p = line_params(self.m, self.m.plan.edges[0])
        self.assertEqual(p["stairList"], "")


class TestWallTiesReachTheDrawing(unittest.TestCase):
    """平面にも描画コードがあるのに、立面でしか渡していなかった."""

    def setUp(self):
        self.m = build("shinwa_A")

    def test_each_edge_gets_only_its_own_ties(self):
        for ep in self.m.plan.edges:
            p = line_params(self.m, ep)
            mine = [t for t in self.m.wall_ties if t.edge_index == ep.edge_index]
            got = [v for v in p["tieList"].split(",") if v]
            self.assertEqual(len(got), len(mine), ep.edge_index)

    def test_positions_and_heights_pair_up(self):
        ep = self.m.plan.edges[0]
        p = line_params(self.m, ep)
        pos = p["tieList"].split(",")
        hei = p["tieHeightList"].split(",")
        self.assertEqual(len(pos), len(hei))
        mine = [t for t in self.m.wall_ties if t.edge_index == ep.edge_index]
        self.assertEqual([int(v) for v in pos], [int(t.position_mm) for t in mine])
        self.assertEqual([int(v) for v in hei], [int(t.height_mm) for t in mine])

    def test_all_ties_are_covered_across_edges(self):
        total = sum(
            len([v for v in line_params(self.m, ep)["tieList"].split(",") if v])
            for ep in self.m.plan.edges
        )
        self.assertEqual(total, len(self.m.wall_ties))


class TestPlacement(unittest.TestCase):
    """配置座標と回転角。plan.json だけで再配置できるようにする."""

    def test_origin_is_the_start_corner_post(self):
        m = build("shinwa_A")
        for ep in m.plan.edges:
            with self.subTest(edge=ep.edge_index):
                pl = placement_of(m, ep.edge_index)
                self.assertAlmostEqual(pl["x_mm"], ep.start_post[0])
                self.assertAlmostEqual(pl["y_mm"], ep.start_post[1])

    def test_angles_follow_the_edge_directions(self):
        m = build("shinwa_A")
        angles = [placement_of(m, e.edge_index)["angle_deg"] for e in m.plan.edges]
        self.assertEqual(sorted(angles), [-90.0, 0.0, 90.0, 180.0])


if __name__ == "__main__":
    unittest.main()
