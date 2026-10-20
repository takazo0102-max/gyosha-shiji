"""足場ラインGDLへ渡すパラメータのテスト.

GDL側で komaPitch から作業床高さや手すり高さを再計算すると、コマの概念が
無い枠組（komaPitch=0）で破綻し、ソルバの結果と図面がずれる。
Python側の解をそのまま渡していることを検査する。
"""

import unittest
from pathlib import Path

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
        # 本足場は出隅の外側コーナー支柱（ジャッキ＋アンダーベース）が加わる
        self.assertEqual(jacks_double - 2 * double.outer_corner_posts(),
                         2 * (jacks_single - 2 * single.outer_corner_posts()))
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


class TestBeamFramesReachTheDrawing(unittest.TestCase):
    """梁枠の内側は支柱を抜く。図面が抜いた支柱を描いたままだと嘘になる."""

    def _setup(self):
        from ashiba.openings import Opening, validate_openings

        m = build("shinwa_A")
        return m, validate_openings(m, [Opening(0, 3600, 3600)])

    def test_only_the_owning_edge_gets_the_beam(self):
        m, op = self._setup()
        got = {
            ep.edge_index: line_params(m, ep, openings=op)["beamList"]
            for ep in m.plan.edges
        }
        self.assertTrue(got[0])
        self.assertEqual([v for k, v in got.items() if k != 0], ["", "", ""])

    def test_triple_is_start_span_and_beam_height(self):
        m, op = self._setup()
        vals = line_params(m, m.plan.edges[0], openings=op)["beamList"].split(",")
        self.assertEqual(len(vals), 3)
        self.assertEqual(int(vals[0]), 3600)
        self.assertEqual(int(vals[1]), 3600)
        self.assertEqual(int(vals[2]), m.elevation.level_heights[0])

    def test_level_selects_the_beam_height(self):
        from ashiba.openings import Opening, validate_openings

        m = build("shinwa_A")
        op = validate_openings(m, [Opening(0, 3600, 3600, level=3)])
        vals = line_params(m, m.plan.edges[0], openings=op)["beamList"].split(",")
        self.assertEqual(int(vals[2]), m.elevation.level_heights[2])

    def test_empty_without_openings(self):
        m = build("shinwa_A")
        self.assertEqual(line_params(m, m.plan.edges[0])["beamList"], "")


class TestLoadingStagesReachTheDrawing(unittest.TestCase):
    """出1.5mの張り出し床。構造計算では見ているのに図面に無かった."""

    def _setup(self, levels=(3,)):
        from ashiba.platforms import LoadingStage, validate_platforms

        m = build("shinwa_A")
        pf = validate_platforms(m, [LoadingStage(
            edge_index=0, start_mm=12600, span_count=2, levels=list(levels))])
        return m, pf

    def test_group_is_start_length_projection_height_hozue(self):
        m, pf = self._setup()
        vals = line_params(m, m.plan.edges[0], platforms=pf)["stageList"].split(",")
        self.assertEqual(len(vals), 5)
        self.assertEqual(int(vals[0]), 12600)
        self.assertEqual(int(vals[2]), int(pf.stages[0].projection_mm))
        self.assertEqual(int(vals[3]), m.elevation.level_heights[2])
        # 方杖は数量拾いと同じ指定を渡す（図だけ勝手に方杖を付けない）
        self.assertEqual(vals[4], "1" if pf.stages[0].has_hozue else "0")

    def test_hozue_flag_follows_the_input(self):
        from ashiba.platforms import LoadingStage, validate_platforms

        m = build("shinwa_A")
        pf = validate_platforms(m, [LoadingStage(
            edge_index=0, start_mm=12600, span_count=2, levels=[3],
            has_hozue=False)])
        vals = line_params(m, m.plan.edges[0], platforms=pf)["stageList"].split(",")
        self.assertEqual(vals[4], "0")

    def test_hoist_reaches_the_drawing(self):
        """昇降機のマストと乗り込み口が図面に出ること.

        数量（乗り込み口の開閉式手すり）と構造（マストの局所荷重）には
        出ていたのに、図面には昇降機がまったく現れていなかった。
        """
        from ashiba.platforms import Hoist, validate_platforms

        m = build("shinwa_A")
        pf = validate_platforms(m, [], [Hoist(
            edge_index=0, position_mm=9000, landing_levels=[2, 5])])
        p = line_params(m, m.plan.edges[0], platforms=pf)
        ho = p["hoistList"].split(",")
        self.assertEqual(int(ho[0]), 9000)
        self.assertEqual(int(ho[1]), m.elevation.total_height)   # 到達高さ既定
        la = [int(v) for v in p["landingList"].split(",")]
        self.assertEqual(la, [9000, m.elevation.level_heights[1],
                              9000, m.elevation.level_heights[4]])

    def test_hoist_is_drawn_in_every_view(self):
        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        body2 = (gdl / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        body3 = (gdl / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertEqual(body2.count("hoP[ih]"), 3)     # 平面（詳細・単線）と立面
        self.assertIn("乗込口", body2)
        self.assertIn("hoR[ih]", body3)

    def test_one_group_per_level(self):
        m, pf = self._setup(levels=(3, 4))
        vals = line_params(m, m.plan.edges[0], platforms=pf)["stageList"].split(",")
        self.assertEqual(len(vals), 10)
        self.assertEqual(int(vals[8]), m.elevation.level_heights[3])

    def test_length_comes_from_the_real_spans(self):
        m, pf = self._setup()
        vals = line_params(m, m.plan.edges[0], platforms=pf)["stageList"].split(",")
        self.assertEqual(int(vals[1]), int(pf.stages[0].length_mm(m)))

    def test_other_edges_and_no_platform_are_empty(self):
        m, pf = self._setup()
        self.assertEqual(line_params(m, m.plan.edges[1], platforms=pf)["stageList"], "")
        self.assertEqual(line_params(m, m.plan.edges[0])["stageList"], "")


class TestBracketSectionsReachTheDrawing(unittest.TestCase):
    """区間の幅指定は数量に反映している。図面にも出さないと食い違う."""

    def _sec(self, **kw):
        from ashiba.brackets import BracketSection

        base = dict(edge_index=0, start_mm=0, end_mm=5400, width=300)
        base.update(kw)
        return BracketSection(**base)

    def test_sextuple_layout(self):
        """開始,終了,幅,向き,高さ,床幅 の6要素で1区間."""
        m = build("shinwa_A")
        vals = line_params(
            m, m.plan.edges[0],
            bracket_sections=[self._sec(levels=[1], deck_width=500)],
        )["brktList"].split(",")
        self.assertEqual(len(vals), 6)
        self.assertEqual([int(v) for v in vals[:4]], [0, 5400, 300, 1])
        self.assertEqual(int(vals[4]), m.elevation.level_heights[0])
        self.assertEqual(int(vals[5]), 500)

    def test_deck_width_is_zero_when_unchanged(self):
        """床幅を変えない区間は0。図に「床500」と書かせない."""
        m = build("shinwa_A")
        vals = line_params(
            m, m.plan.edges[0], bracket_sections=[self._sec(levels=[1])]
        )["brktList"].split(",")
        self.assertEqual(int(vals[5]), 0)

    def test_outer_direction_is_negative(self):
        from ashiba.brackets import OUTER

        m = build("shinwa_A")
        vals = line_params(
            m, m.plan.edges[0],
            bracket_sections=[self._sec(direction=OUTER, levels=[1])],
        )["brktList"].split(",")
        self.assertEqual(int(vals[3]), -1)

    def test_no_levels_means_every_level(self):
        m = build("shinwa_A")
        vals = line_params(
            m, m.plan.edges[0], bracket_sections=[self._sec()]
        )["brktList"].split(",")
        self.assertEqual(len(vals) // 6, m.elevation.n_levels)

    def test_group_count_is_capped(self):
        from ashiba.gdl_params import MAX_BRACKET_GROUPS

        m = build("shinwa_A")
        secs = [self._sec(start_mm=i * 1800, end_mm=i * 1800 + 1800) for i in range(6)]
        vals = line_params(m, m.plan.edges[0], bracket_sections=secs)["brktList"]
        self.assertLessEqual(len(vals.split(",")) // 6, MAX_BRACKET_GROUPS)

    def test_other_edges_are_empty(self):
        m = build("shinwa_A")
        self.assertEqual(
            line_params(m, m.plan.edges[1], bracket_sections=[self._sec()])["brktList"],
            "",
        )


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


class TestGeometryParamsMatchThePlan(unittest.TestCase):
    """図面に渡す寸法が割付の値と一致すること.

    離れを0で渡しても落ちない状態だった（変異テストで判明）。
    離れは平面図の躯体参照線・壁つなぎの長さ・詳細図の寸法に効くので、
    ここがズレると図面だけ実物と違う。
    """

    def test_standoff_is_per_edge(self):
        m = build("shinwa_A")
        for ep in m.plan.edges:
            with self.subTest(ep.edge_index):
                p = line_params(m, ep)
                self.assertAlmostEqual(p["standoff"] * 1000, ep.standoff, places=3)
                self.assertGreater(p["standoff"], 0)

    def test_standoff_follows_a_changed_spec(self):
        from ashiba.plan_solver import StandoffSpec, solve_plan

        m = build("shinwa_A")
        m.plan = solve_plan(
            [(0, 0), (30000, 0), (30000, 20000), (0, 20000)], m.master,
            StandoffSpec(target=250, min=200, max=300, hard_min=180),
        )
        for ep in m.plan.edges:
            p = line_params(m, ep)
            self.assertAlmostEqual(p["standoff"] * 1000, ep.standoff, places=3)

    def test_detail_sheet_uses_a_real_standoff(self):
        from ashiba.details import required_details

        m = build("shinwa_A")
        for sheet in required_details(m):
            with self.subTest(sheet.key):
                self.assertGreater(sheet.params["standoff"], 0)

    def test_row_spacing_is_not_the_deck_width(self):
        """建地列の芯々と作業床の被覆幅は別物（混同すると図面が狂う）."""
        m = build("shinwa_A")
        p = line_params(m, m.plan.edges[0])
        self.assertAlmostEqual(
            p["rowW"] * 1000, m.post_row_spacing_mm, places=3)
        self.assertNotAlmostEqual(
            p["rowW"] * 1000, m.deck_width_total, places=3)


class TestPartialPlacementIsRolledBack(unittest.TestCase):
    """一括配置の途中で失敗したら、置いた分を残さない."""

    class FakeClient:
        def __init__(self, fail_on):
            self.fail_on = fail_on
            self.created = []
            self.deleted = []
            self.n = 0

        def create_object(self, name, x, y, z=0.0):
            elem = {"elementId": {"guid": f"g{len(self.created)}"}}
            self.created.append(elem)
            return elem

        def rotate_element(self, *a, **kw):
            pass

        def set_gdl_parameters(self, element, params, object_name=""):
            self.n += 1
            if self.n == self.fail_on:
                from ashiba.tapir_adapter import TapirError
                raise TapirError("テスト用の失敗")

        def delete_elements(self, elements):
            self.deleted.extend(elements)

        def find_red_pen(self, default=20):
            return 20

        def find_member_surfaces(self):
            return {"matScaf": 45, "matDeck": 47}

    def test_scaffold_lines_are_removed(self):
        from ashiba.tapir_adapter import TapirError, place_scaffold_lines

        m = build("shinwa_A")
        c = self.FakeClient(fail_on=3)
        with self.assertRaises(TapirError) as cm:
            place_scaffold_lines(m, "obj", c)
        self.assertEqual(len(c.deleted), len(c.created))
        self.assertIn("削除しました", str(cm.exception))

    def test_details_are_removed(self):
        from ashiba.details import required_details
        from ashiba.tapir_adapter import TapirError, place_details

        m = build("shinwa_A")
        c = self.FakeClient(fail_on=2)
        with self.assertRaises(TapirError):
            place_details(m, required_details(m), "obj", client=c)
        self.assertEqual(len(c.deleted), len(c.created))

    def test_success_deletes_nothing(self):
        from ashiba.tapir_adapter import place_scaffold_lines

        m = build("shinwa_A")
        c = self.FakeClient(fail_on=0)
        placed = place_scaffold_lines(m, "obj", c)
        self.assertEqual(len(placed), len(m.plan.edges))
        self.assertEqual(c.deleted, [])


class TestPlanJsonRoundTripCoverage(unittest.TestCase):
    """plan.json からの再配置スクリプトが、送った全パラメータを照合すること.

    照合対象を手で並べていたときは、パラメータを増やすたびに漏れて
    「全パラメータ一致」と出しながら12個が未検証だった。
    """

    def test_no_hardcoded_key_list_in_the_script(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts" / "place_from_plan_json.py").read_text(encoding="utf-8")
        for name in ("NUMERIC_KEYS", "STRING_KEYS", "INT_KEYS"):
            self.assertNotIn(name, src, f"{name} で対象を固定すると漏れる")
        self.assertIn("params.items()", src)

    def test_plan_json_carries_every_parameter(self):
        import json
        import tempfile

        from ashiba.report import write_plan_json

        m = build("shinwa_A")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "plan.json"
            write_plan_json(m, path)
            data = json.loads(path.read_text(encoding="utf-8"))
        sent = set(line_params(m, m.plan.edges[0]))
        for e in data["edges"]:
            self.assertEqual(set(e["gdl_params"]), sent)


if __name__ == "__main__":
    unittest.main()


class TestElevationAnnotationsDoNotCollide(unittest.TestCase):
    """立面図の文字が重ならないこと（実機のプレビューで潰れていた）."""

    def setUp(self):
        self.body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf"
                     / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")

    def test_jack_callout_left_the_height_dimension_column(self):
        # 高さ寸法の列（dx）に jackOut/2 で置くと最下段（GL+100）の寸法と重なる
        self.assertNotIn('jackOut / 2, "ジャッキ', self.body)

    def test_jack_callout_sits_below_the_span_dimension(self):
        line = [ln for ln in self.body.splitlines() if '"ジャッキ繰出' in ln]
        # 平坦／高低差あり（脚ごとに同じ値）／高低差あり（脚ごとの範囲）の3分岐。どれも同じ位置に置く
        self.assertEqual(len(line), 3, "ジャッキ繰出しの記載は平坦・同値・範囲の3分岐")
        for ln in line:
            self.assertIn("dy - txtLine * 3.4", ln)

    def test_height_dimension_text_is_right_aligned(self):
        # 左詰めのままだと桁数が増えたとき寸法線と足場の中へはみ出す
        for want in ("dimTxt = str(lv[il] * 1000, 6, 0)",
                     "stw(dimTxt) * GLOB_SCALE / 1000"):
            self.assertIn(want, self.body)
        self.assertNotIn('text2 dx - txtH, lv[il]', self.body)
        self.assertNotIn('text2 dx - txtH, postTop', self.body)

    def test_centered_labels_use_the_centered_style(self):
        """中点に置く文字は中央揃えのスタイルで書く.

        既定のスタイルは左詰めなので、中点を基準点にすると文字幅の半分だけ
        右にずれて見える（実機で全てのスパン寸法がずれていた）。
        """
        lines = self.body.splitlines()
        offenders = []
        for i, ln in enumerate(lines):
            if "text2 " not in ln:
                continue
            x = ln.split("text2 ", 1)[1].split(",")[0].strip()
            if not x.endswith("/ 2"):
                continue
            if lines[i - 1].strip() != 'set style "annoC"':
                offenders.append(ln.strip())
        self.assertEqual(offenders, [], "中点基準の文字が左詰めのままです")

    def test_centered_style_is_defined(self):
        self.assertIn('define style "annoC" "ＭＳ Ｐゴシック", texSiz, 5, 0', self.body)

    def test_braces_are_drawn_as_a_cross(self):
        """ブレスは1箇所2本（交さ2方向）。数量がそう数えているので図もX.

        片方向だけ描いていたため、部材表の本数と図が合わなかった。
        枠組の交差筋交も同じ（建枠間はX）。
        """
        from ashiba.quantity import QuantityRules

        self.assertEqual(QuantityRules().braces_per_location, 2)
        body2 = self.body
        i = body2.index("! ブレス")
        block = body2[i:i + 700]
        self.assertIn("line2 x, lv[il], x + spans[ip], lv[il + 1]", block)
        self.assertIn("line2 x + spans[ip], lv[il], x, lv[il + 1]", block)
        body3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
                 / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        j = body3.index("! ---- ブレス")
        self.assertEqual(body3[j:j + 900].count("cylind bl, 0.0213 / 2"), 2)

    def test_single_row_scaffold_gets_its_deck_brackets(self):
        """一側足場の床受けブラケットを3Dにも出す.

        数量では拾っているのに3Dには腕木もブラケットも無く、作業床が
        宙に浮いて見えていた（干渉確認にも使えない）。
        """
        body3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
                 / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("800: ! ---- 一側足場の床受けブラケット", body3)
        self.assertEqual(body3.count("gosub 800"), 2)   # 各スパンと終端

    def test_asagao_dimension_does_not_claim_the_limit_is_met(self):
        """朝顔の寸法に法定値を混ぜない.

        「突出 1500≧2000」と描かれていた。違反していても≧と書くので
        図面が嘘をつく。法定値は注記と警告文に出る。
        """
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_detail"
                / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        for bad in ('"≧2000"', '"°≧20°"', '"≦" + str(LIM_JACK'):
            self.assertNotIn(bad, body)
        # 基準は注記と警告文の側に残っていること
        self.assertIn("外周から水平突出2m以上・水平面と20度以上", body)
        self.assertIn('"※朝顔突出 "', body)
        self.assertIn('"ジャッキ繰出しは " + str(LIM_JACK * 1000, 3, 0) + "mm以下"', body)
        self.assertIn('"※ジャッキ繰出し "', body)

    def test_detail_sheets_center_their_labels_too(self):
        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_detail"
        self.assertIn('define style "annoC" "ＭＳ Ｐゴシック", texSiz * dScale / GLOB_SCALE, 5, 0',
                      (gdl / "scripts" / "1d.gdl").read_text(encoding="utf-8"))
        lines = (gdl / "scripts" / "2d.gdl").read_text(encoding="utf-8").splitlines()
        offenders = [
            ln.strip() for i, ln in enumerate(lines)
            if "text2 " in ln
            and ln.split("text2 ", 1)[1].split(",")[0].strip().endswith("/ 2")
            and lines[i - 1].strip() != 'set style "annoC"'
        ]
        self.assertEqual(offenders, [], "詳細図の中点基準の文字が左詰めのままです")

    def test_notes_column_clears_the_height_labels(self):
        # FL参照(+0.35)・朝顔の高さ表示(+0.1)と同じ帯だと行が重なる
        tx = [ln for ln in self.body.splitlines() if ln.startswith("tx = lineLen")]
        self.assertEqual(len(tx), 1)
        self.assertGreaterEqual(float(tx[0].split("+")[1]), 2.5)

    def test_span_total_and_jack_are_on_separate_lines(self):
        # 短い面では L= と横並びになる。行を変えて避ける
        total = [ln for ln in self.body.splitlines()
                 if '"L=" + str(lineLen' in ln and "dy - txtLine * 2.2" in ln]
        self.assertEqual(len(total), 1, "立面の全長寸法は1箇所")


class TestTerrainReachesTheDrawing(unittest.TestCase):
    """敷地高低差は支柱位置ごとの地盤高・ジャッキとして図面に渡る.

    平坦なGLに共通のジャッキで描いていたので、継ぎ足した支柱（数量には入る）が
    立面・3Dに出ず、図面と数量が食い違っていた。
    """

    def _terrain(self, m, drop):
        from ashiba.terrain import GroundModel, solve_post_feet

        return solve_post_feet(m, GroundModel(points=[
            (0, 0, drop), (30000, 0, 0), (30000, 20000, 0), (0, 20000, drop)]))

    def test_flat_site_sends_nothing(self):
        m = build("shinwa_A")
        p = line_params(m, m.plan.edges[0], terrain=self._terrain(m, 0))
        self.assertEqual(p["glList"], "")
        self.assertEqual(p["jackList"], "")
        self.assertEqual(line_params(m, m.plan.edges[0])["glList"], "")

    def test_sloped_site_sends_one_value_per_post(self):
        m = build("shinwa_A")
        t = self._terrain(m, 2000)
        for ep in m.plan.edges:
            p = line_params(m, ep, terrain=t)
            gl = [int(v) for v in p["glList"].split(",")]
            jk = [int(v) for v in p["jackList"].split(",")]
            self.assertEqual(len(gl), ep.span_count + 1, ep.edge_index)
            self.assertEqual(len(jk), ep.span_count + 1)
            self.assertLessEqual(max(gl), 0)            # 基準は最も高い地盤
            self.assertTrue(all(v >= 30 for v in jk))   # ジャッキ最小以上
        # 辺0は x=0 側が高い（drop）→ 地盤高は x=0 で 0、終点で -2000 付近
        p0 = line_params(m, m.plan.edges[0], terrain=t)
        gl0 = [int(v) for v in p0["glList"].split(",")]
        self.assertGreater(gl0[0], gl0[-1])
        self.assertLess(gl0[-1], -1500)

    def test_gdl_reads_the_lists(self):
        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        master = (root / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        elev = (root / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        solid = (root / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        for name in ("glList", "glList2", "jackList", "jackList2"):
            self.assertIn(f"rest = {name}", master)
        self.assertIn("gl[ip]", elev)
        self.assertIn("jk[ip]", elev)
        self.assertIn("gl[ip]", solid)


class TestAsagaoCutList(unittest.TestCase):
    """昇降機が通るスパンは朝顔を切り欠いて描く（asaCutList「開始,終了」）."""

    def _model(self):
        from ashiba.model import AsagaoSpec

        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)),
        )

    def test_hoist_on_a_post_cuts_both_spans_as_one_range(self):
        from ashiba.platforms import Hoist, validate_platforms

        m = self._model()
        pf = validate_platforms(m, [], [Hoist(edge_index=0, position_mm=9000)])
        p = line_params(m, m.plan.edges[0], platforms=pf)
        self.assertEqual(p["asaCutList"], "7200,10800")
        other = line_params(m, m.plan.edges[1], platforms=pf)
        self.assertEqual(other["asaCutList"], "")

    def test_hoist_mid_span_cuts_that_span(self):
        """切り欠きは搬器の幅ぶん。スパンに収まる搬器はそのスパンだけ、はみ出せば隣も."""
        from ashiba.platforms import Hoist, validate_platforms

        m = self._model()
        pf = validate_platforms(m, [], [Hoist(edge_index=0, position_mm=9900, cage_width_mm=1600)])
        p = line_params(m, m.plan.edges[0], platforms=pf)
        self.assertEqual(p["asaCutList"], "9000,10800")
        pf = validate_platforms(m, [], [Hoist(edge_index=0, position_mm=9900, cage_width_mm=2400)])
        p = line_params(m, m.plan.edges[0], platforms=pf)
        self.assertEqual(p["asaCutList"], "7200,12600")     # 幅2.4mは両隣に100mm以上掛かる

    def test_no_asagao_means_no_cut(self):
        from ashiba.platforms import Hoist, validate_platforms

        m = build("shinwa_A")
        pf = validate_platforms(m, [], [Hoist(edge_index=0, position_mm=9000)])
        self.assertEqual(line_params(m, m.plan.edges[0], platforms=pf)["asaCutList"], "")



class TestGuardRailMethodReachesTheDrawing(unittest.TestCase):
    """先行手すり工法は railAdv=1（斜材が中桟を兼ねる）。布材は 0、枠組は建枠一体なので 0."""
    def test_flag(self):
        from ashiba.model import GUARD_RAIL_ADVANCE, GUARD_RAIL_LEDGER
        for sid, rail, want in (("shinwa_A", GUARD_RAIL_ADVANCE, 1), ("shinwa_A", GUARD_RAIL_LEDGER, 0),
                                ("waku", GUARD_RAIL_ADVANCE, 0)):
            with self.subTest((sid, rail)):
                m = build(sid)
                m.config.guard_rail_type = rail
                self.assertEqual(line_params(m, m.plan.edges[0])["railAdv"], want)


class TestInnerGuardRailReachesTheDrawing(unittest.TestCase):
    """躯体側の手すり・中桟（railIn）は既定で 1。外せば 0。枠組は建枠一体なので 0."""
    def test_flag(self):
        m = build("shinwa_A")
        self.assertEqual(line_params(m, m.plan.edges[0])["railIn"], 1)
        m.config.inner_guard_rail = False
        self.assertEqual(line_params(m, m.plan.edges[0])["railIn"], 0)
        w = build("waku")
        self.assertEqual(line_params(w, w.plan.edges[0])["railIn"], 0)


class TestCornerReachesTheDrawing(unittest.TestCase):
    """出隅の外側コーナーは始点側の面が描く（cornerS）。一側足場・枠組は 0."""
    def test_flag(self):
        m = build("shinwa_A")
        self.assertTrue(all(line_params(m, e)["cornerS"] == 1 for e in m.plan.edges))
        m.config.scaffold_form = "一側足場"
        self.assertEqual(line_params(m, m.plan.edges[0])["cornerS"], 1)   # 一側も建地列が躯体コーナーで終わる
        w = build("waku")
        self.assertEqual(line_params(w, w.plan.edges[0])["cornerS"], 0)


class TestShimsReachTheDrawing(unittest.TestCase):
    """敷板で持ち上げた脚は shimList で図に渡す（ジャッキ繰出しの内数）."""
    def test_shim_list(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        m = build("shinwa_A")
        t = solve_post_feet(m, GroundModel(points=[(0, 0, 0), (30000, 0, 700), (30000, 20000, 700), (0, 20000, 0)]))
        self.assertTrue(any(f.base_plate_adjust_mm > 0 for f in t.feet), "敷板が出る斜面の前提")
        p = line_params(m, m.plan.edges[0], terrain=t)
        shims = [int(v) for v in p["shimList"].split(",")]
        jacks = [int(v) for v in p["jackList"].split(",")]
        self.assertEqual(len(shims), len(jacks))
        self.assertTrue(any(v > 0 for v in shims))
        for s_, j in zip(shims, jacks):
            self.assertLessEqual(s_, j)
            self.assertEqual(s_ % 35, 0)
        flat = line_params(m, m.plan.edges[0])
        self.assertEqual(flat["shimList"], "")


class TestHoistMastInModel(unittest.TestCase):
    """昇降機はマスト・搬器・渡し板・マスト控えまで3Dに出す（以前は4隅の柱と床板だけ）."""

    def _params(self, **kw):
        from ashiba.platforms import Hoist, validate_platforms

        m = build("shinwa_A")
        pf = validate_platforms(m, [], [Hoist(edge_index=0, position_mm=9000, landing_levels=[2, 5], **kw)])
        return m, line_params(m, m.plan.edges[0], platforms=pf)

    def test_tie_pitch_is_the_fifth_value(self):
        m, p = self._params()
        ho = p["hoistList"].split(",")
        self.assertEqual(len(ho), 5)
        self.assertEqual(int(ho[4]), 3600)                       # 既定の控えピッチ
        _, p2 = self._params(tie_every_mm=1800, cage_width_mm=2400, cage_depth_mm=1800)
        self.assertEqual([int(v) for v in p2["hoistList"].split(",")[2:]], [2400, 1800, 1800])

    def test_gdl_parses_five_values_and_draws_mast_cage_tie(self):
        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"
        body1 = (gdl / "1d.gdl").read_text(encoding="utf-8")
        self.assertIn("hoM = hoIdx - 5 * int((hoIdx - 1) / 5)", body1)
        self.assertIn("hoTp[nHo] = 3.6", body1)                  # 未指定でも控えを描く
        body3 = (gdl / "3d.gdl").read_text(encoding="utf-8")
        for key in ("マスト控え", "渡し板", "hoTp[ih]", "cylind 2.2, 0.02", "cylind mh, 0.02"):
            self.assertIn(key, body3)
        body2 = (gdl / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("-rowW - 0.40 - hoD[ih]", body2)          # 平面にマストの角
        self.assertIn("hoR[ih] + 1.0", body2)                    # 立面にマスト（到達+1m）と搬器
        self.assertIn("cz2 + 2.2", body2)


class TestPlanDimensionClearsAttachments(unittest.TestCase):
    """平面の寸法線は昇降機の搬器・ステージの外側に置く（面中央の昇降機で文字が重なっていた）."""

    def test_offset_uses_hoist_depth_and_stage_projection(self):
        body2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl"
                 ).read_text(encoding="utf-8")
        self.assertIn("if 0.10 + hoD[ih] + 0.55 > dOff then dOff = 0.10 + hoD[ih] + 0.55", body2)
        self.assertIn("if sgP[ig] + 0.10 > dOff then dOff = sgP[ig] + 0.10", body2)
        self.assertIn("yd = -rowW - dOff - 0.90", body2)          # 寸法線は張り出しの外からさらに離す


class TestLineMode3D(unittest.TestCase):
    """3Dの線表示（lineMode）: 立体を描かず線だけで割付・付帯設備の占有範囲を出す."""

    def test_parameter_and_branch_exist(self):
        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        xml = (root / "paramlist.xml").read_text(encoding="utf-8")
        self.assertIn('<Boolean Name="lineMode">', xml)
        body3 = (root / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("if lineMode then\n\tgosub 900\n\tend\nendif", body3)
        self.assertIn("900:\t! ---- 線表示 ----", body3)
        # 線表示でも開口部の支柱抜き・階段・ステージ・昇降機・壁つなぎは出す
        sub = body3[body3.index("900:"):]
        for key in ("bBase = bmH[ib]", "for it5 = 1 to nSt", "for ig = 1 to nSg", "for ih = 1 to nHo",
                    "for it = 1 to nTieDraw", "cornerS = 1"):
            self.assertIn(key, sub)
        # 線表示の部分に立体（cylind/block/prism）は無い
        for solid in ("cylind", "block ", "prism"):
            self.assertNotIn(solid, sub)


class TestLineModeFromSpec(unittest.TestCase):
    """入力の line_mode_3d が部品の lineMode に bool で届く（int だと Tapir が全パラメータを落とす）."""

    def test_default_off_and_bool_type(self):
        m = build("shinwa_A")
        p = line_params(m, m.plan.edges[0])
        self.assertIs(p["lineMode"], False)
        from ashiba.cli import solve_all
        r = solve_all({"project_name": "線表示", "series_id": "shinwa_A",
                       "outline_mm": [[0, 0], [10800, 0], [10800, 5400], [0, 5400]],
                       "eaves_height_mm": 9000, "building_height_mm": 9000, "line_mode_3d": True})
        self.assertIs(line_params(r.model, r.model.plan.edges[0])["lineMode"], True)


class TestModelViewOptionPart(unittest.TestCase):
    """モデル表示オプション部品 ashiba_mvo と、足場ラインの LIBRARYGLOBAL 読み."""

    def test_mvo_part_is_a_library_global(self):
        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_mvo"
        anc = (root / "ancestry.xml").read_text(encoding="utf-8")
        self.assertIn("709CC5CC-6817-4C56-A74B-BED99DDB5FFA", anc)     # Library Global Settings の系譜
        lpd = (root / "libpartdata.xml").read_text(encoding="utf-8")
        self.assertIn("<Script_UI", lpd)
        self.assertIn("<Script_VL", lpd)
        xml = (root / "paramlist.xml").read_text(encoding="utf-8")
        for name in ("planMode", "planNotes", "mode3d"):
            self.assertIn(f'Name="{name}"', xml)
        vl = (root / "scripts" / "vl.gdl").read_text(encoding="utf-8")
        self.assertIn('"planMode", 1, "詳細", 2, "単線"', vl)

    def test_line_part_reads_the_mvo_and_falls_back_to_its_own_params(self):
        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"
        body2 = (gdl / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn('LIBRARYGLOBAL(mvoName, "planMode", mvPlan)', body2)
        self.assertIn('LIBRARYGLOBAL(mvoName, "planNotes", mvNotes)', body2)
        self.assertIn("950: ! ---- 平面 単線", body2)
        body3 = (gdl / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn('LIBRARYGLOBAL(mvoName, "mode3d", mv3d)', body3)

    def test_mvo_name_is_passed_with_the_dist_version(self):
        import tempfile
        from ashiba.gdl_params import mvo_part_name

        m = build("shinwa_A")
        p = line_params(m, m.plan.edges[0])
        self.assertTrue(p["mvoName"].startswith("ashiba_mvo"))
        self.assertIs(p["planSimple"], False)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(mvo_part_name(d), "ashiba_mvo")
            (Path(d) / "ashiba_mvo.gsm.hash").write_text("0123abcd\n", encoding="utf-8")
            self.assertEqual(mvo_part_name(d), "ashiba_mvo_0123abcd")


class TestFaceDrawnCounts(unittest.TestCase):
    """部品が書き戻す図示本数（qty*）の式は Python にも置き、全面の合計が数量表と合うことを確かめる."""

    def _solve(self, **extra):
        from ashiba.cli import solve_all

        spec = {"project_name": "図示本数", "series_id": "shinwa_A",
                "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 16000, "building_height_mm": 16000}
        spec.update(extra)
        return solve_all(spec)

    def test_gdl_writes_back_every_count(self):
        from ashiba.gdl_params import FACE_COUNT_PARAMS

        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        xml = (root / "paramlist.xml").read_text(encoding="utf-8")
        body1 = (root / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        for name in FACE_COUNT_PARAMS:
            self.assertIn(f'<Integer Name="{name}">', xml)
            self.assertIn(f"{name} = ", body1)
        self.assertIn("parameters qtyPostPos = qPostPos", body1)

    def test_sums_match_the_take_off(self):
        from ashiba.gdl_params import face_drawn_counts
        from ashiba.quantity import QuantityRules

        r = self._solve()
        m, q = r.model, r.quantity
        tot = {}
        for ep in m.plan.edges:
            for k, v in face_drawn_counts(m, ep, stair_plan=r.stair_plan, openings=r.openings).items():
                tot[k] = tot.get(k, 0) + v
        self.assertEqual(tot["qtyPostPos"], m.plan.total_posts * 2 + m.outer_corner_posts())
        self.assertEqual(tot["qtyTie"], len(m.wall_ties))
        self.assertEqual(tot["qtyStair"], r.stair_plan.count * m.elevation.n_levels)
        widths = list(m.deck_widths_in_use)
        # 出隅コーナーの床（長さ＝建地列間隔の踏板）は面の図示本数に入らない（幅木と同じ扱い）
        corner_decks = m.outer_corner_posts() * m.elevation.n_levels * len(widths)
        self.assertEqual(tot["qtyDeck"] * len(widths), q.qty_of(m.master.deck_category) - corner_decks)
        self.assertEqual(tot["qtyToe"], q.qty_of("幅木") - m.outer_corner_posts() * 2 * m.elevation.n_levels)
        # 布材（面に沿う分）: 数量表の1スパンあたりの式と同じ
        rules = QuantityRules()
        per_span = rules.ledgers_negarami + m.elevation.n_levels * (rules.ledgers_per_level_floor + rules.rails_per_level_outer + 2)
        self.assertEqual(tot["qtyNuno"], m.plan.total_spans * per_span)

    def test_opening_and_advance_rail_change_the_counts(self):
        from ashiba.gdl_params import face_drawn_counts

        r = self._solve(openings=[{"face": "南面", "start_mm": 3600, "beam_span_mm": 3600, "level": 2}],
                        guard_rail_type="先行手すり")
        m = r.model
        south = next(e for e in m.plan.edges if m.face_name(e.edge_index) == "南面")
        c = face_drawn_counts(m, south, stair_plan=r.stair_plan, openings=r.openings)
        self.assertEqual(c["qtyToe"], 0)                      # 先行手すりでは幅木なし
        self.assertGreater(c["qtyAdv"], 0)
        plain = self._solve(guard_rail_type="先行手すり")
        ps = next(e for e in plain.model.plan.edges if plain.model.face_name(e.edge_index) == "南面")
        c0 = face_drawn_counts(plain.model, ps, stair_plan=plain.stair_plan, openings=plain.openings)
        self.assertLess(c["qtyAdv"], c0["qtyAdv"])            # 開口部の通路層ぶん減る
        self.assertLess(c["qtyNuno"], c0["qtyNuno"])


class TestRealMemberDimensions3D(unittest.TestCase):
    """3Dの緊結部まわりは実寸（次世代足場.gsm で確認した寸法）で描く."""

    def setUp(self):
        self.body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                     ).read_text(encoding="utf-8")

    def test_flange_is_phi106_t6(self):
        self.assertIn("cylind 0.006, 0.053", self.body)
        self.assertNotIn("cylind 0.01, 0.055", self.body)

    def test_ledgers_end_at_the_claw_not_the_post_centre(self):
        # 床レベル・手すり・中桟・根がらみ（6）＋外付け階段の根がらみ・外周の手すり・中桟・開口の手すり・中桟（5）
        self.assertEqual(self.body.count("gosub 830"), 11)
        self.assertNotIn("cylind spans[ip], r_nuno", self.body)
        sub = self.body[self.body.index("830:"):self.body.index("900:")]
        self.assertIn("cylind nL - 0.156, r_nuno", sub)                   # 両端 78 ずつ
        self.assertEqual(sub.count("block 0.052, 0.020, 0.024"), 2)       # 爪

    def test_decks_clear_the_posts_by_70(self):
        self.assertIn("add x + 0.07, -rowW + 0.05, z", self.body)
        self.assertIn("block spans[ip] - 0.14, deckW1, 0.045", self.body)


class TestNoTextIn3D(unittest.TestCase):
    """3D には文字を出さない（利用者の指定 2026-10-18。スパン寸法は平面・立面の2Dで読む）."""

    def test_no_3d_text(self):
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                ).read_text(encoding="utf-8")
        code = "\n".join(ln.split("!")[0] for ln in body.splitlines())
        self.assertNotIn("txt3d", code)
        self.assertNotRegex(code, r"(?m)^\s*text\s")


class TestWallTieSymbol(unittest.TestCase):
    """壁つなぎの記号は平面が逆三角 ▽、立面が◎（以前は両方○に十字→▽）."""

    def test_plan_triangle_and_elevation_double_circle(self):
        body2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl"
                 ).read_text(encoding="utf-8")
        self.assertIn("960:\t! ---- 壁つなぎの記号（平面）: 逆三角", body2)
        self.assertIn("line2 tx3, ty3 + 0.11, tx3 - 0.11, ty3 - 0.09", body2)  # 平面: 頂点が躯体側
        self.assertIn("circle2 ties[it], tieH[it], 0.12", body2)              # 立面: ◎ の外輪
        self.assertIn("circle2 ties[it], tieH[it], 0.065", body2)             # 立面: ◎ の内輪
        self.assertNotIn("line2 tx3, ty3, tx3 - 0.14, ty3 + 0.22", body2)     # 立面の ▽ は廃止
        self.assertIn("箇所（平面▽・立面◎）", body2)
        body3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                 ).read_text(encoding="utf-8")
        self.assertNotIn("prism_ nsp / 3, 0.01, get(nsp)", body3)            # ◎ は3Dに持たせない（立面の注記で描く）
        self.assertNotIn("prism 3, 0.01, -0.14, 0.22, 0.14, 0.22, 0, 0", body3)
        import re
        self.assertIsNone(re.search(r"\btri\s*=", body3, re.I))   # tri を変数にすると3Dが真っ白（実機）


class TestStandoffDimensionInPlan(unittest.TestCase):
    """平面に躯体面と内側建地列の間の離れ寸法を両端に入れる."""

    def test_dimension_lines_and_value(self):
        body2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl"
                 ).read_text(encoding="utf-8")
        self.assertIn("if kd = 1 then xd = spans[1] / 2 else xd = lineLen - spans[nSpan] / 2", body2)
        self.assertIn("line2 xd, 0, xd, standoff", body2)
        self.assertIn("text2 xd + 0.08, standoff / 2, str(standoff * 1000, 4, 0)", body2)


class TestFarSideScreen(unittest.TestCase):
    """立面（断面）で向こう側の面の足場を描かない: 各面が自分の躯体面の奥に辺の無い幕を立てる（断面・立面だけ）."""

    def test_screen_only_in_sections_without_edges(self):
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                ).read_text(encoding="utf-8")
        i = body.index("! ---- 向こう側の面を隠す幕")
        sub = body[i:i + 1500]
        self.assertIn("if GLOB_VIEW_TYPE = 4 or GLOB_VIEW_TYPE = 5 then", sub)
        self.assertIn("add -rowW - 0.05, standoff + 1.0, -3.0", sub)
        # 状態 8 = 側面あり・辺なし（幕の輪郭を立面に描かない）
        self.assertEqual(sub.count(", 8"), 4)
        # 線表示でも効くよう、線表示の分岐より前
        self.assertLess(i, body.index("if lineMode then"))


class TestPlanDimensions(unittest.TestCase):
    """平面のスパン寸法は足場から離した寸法線で、北・西を向く面でも数字が読める向き."""

    def setUp(self):
        self.body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl"
                     ).read_text(encoding="utf-8")

    def test_dimension_line_stands_off(self):
        self.assertIn("yd = -rowW - dOff - 0.90", self.body)
        self.assertIn("line2 xs, yd, xe, yd", self.body)
        # 両端の出隅コーナー（外側の角の支柱）まで寸法を張る
        self.assertIn("xs = -rowW * cornerS", self.body)
        self.assertIn("xe = lineLen + rowW * cornerE", self.body)
        self.assertIn("if nAsa > 0 and asagaoProj + 0.35 > dOff then dOff = asagaoProj + 0.35", self.body)

    def test_text_turns_to_read_from_below_or_right(self):
        i = self.body.index("985:")
        sub = self.body[i:i + 600]
        self.assertIn("if SYMB_ROTANGLE > 90.001 and SYMB_ROTANGLE < 270.001 then rot2 180 else rot2 0", sub)


class TestLight3D(unittest.TestCase):
    """3Dの細かさ: 自動・精細・軽量・線。軽量はコマ・爪・継手・ハンドルを省き円柱を6角に."""

    def setUp(self):
        self.body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                     ).read_text(encoding="utf-8")

    def test_levels_and_auto(self):
        self.assertIn("if nSpan * (nLv - 1) > 40 then d3 = 2", self.body)
        self.assertIn("if isLite then rN = 6", self.body)
        self.assertNotIn("resol 12", self.body)          # 戻すときも rN（軽量では6のまま）

    def test_light_skips_small_parts(self):
        self.assertEqual(self.body.count("if komaPitch > 0 and isLite = 0 then"), 2)   # コマ（外側コーナー含む）
        self.assertEqual(self.body.count("if j < nPost and isLite = 0 then"), 2)       # 支柱の継手のカラー
        self.assertIn("if isLite = 0 then\n\tadd 0.026, -0.010, -0.012", self.body)    # 布材の爪

    def test_mvo_overrides(self):
        self.assertIn('if LIBRARYGLOBAL(mvoName, "mode3d", mvD) then', self.body)
        vl = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_mvo" / "scripts" / "vl.gdl"
              ).read_text(encoding="utf-8")
        self.assertIn('3, "立体（軽量）"', vl)


class TestStairOpeningGuard3D(unittest.TestCase):
    """階段開口部手摺枠＋幅木を、各層の階段の上がり口の真上に描く（数量の出入口1か所に1組と同じ）."""

    def test_guard_frame_at_low_end_of_flight(self):
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                ).read_text(encoding="utf-8")
        i = body.index("! 階段開口部手摺枠＋開口部幅木")
        sub = body[i:i + 1200]
        self.assertIn("zg = lv[il5 + 1]", sub)
        self.assertIn("add x0 + 0.03, gy0, zg + 0.90", sub)
        self.assertIn("block 0.02, gw, 0.157", sub)


class TestSharedCornerPosts(unittest.TestCase):
    """隅の内側建地は隣の面と同じ1本。両方の面が描いて重なっていた（利用者の指摘 2026-10-20）."""

    def test_each_corner_post_drawn_once(self):
        from ashiba.cli import solve_all
        from ashiba.gdl_params import shared_corner_skips

        r = solve_all({"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000})
        n = len(r.model.plan.edges)
        sk = {e.edge_index: shared_corner_skips(r.model, e.edge_index) for e in r.model.plan.edges}
        for i in range(n):
            # 面 i の終点＝面 i+1 の始点。どちらか一方だけが描く
            drawn = (1 - sk[i]["skipInE"]) + (1 - sk[(i + 1) % n]["skipInS"])
            self.assertEqual(drawn, 1, sk)

    def test_taller_face_draws_the_corner_post(self):
        from ashiba.cli import solve_all
        from ashiba.gdl_params import shared_corner_skips

        r = solve_all({"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 15000,
                       "face_eaves_mm": {"0": 9000, "1": 15000, "2": 15000, "3": 15000}})
        m = r.model
        low = 0
        self.assertLess(m.elevation_of(low).total_height, m.elevation_of(1).total_height)
        self.assertEqual(shared_corner_skips(m, low)["skipInE"], 1)     # 次の面（高い）が描く
        self.assertEqual(shared_corner_skips(m, 1)["skipInS"], 0)
        self.assertEqual(shared_corner_skips(m, 3)["skipInE"], 0)       # 前の面（高い）が自分で描く
        self.assertEqual(shared_corner_skips(m, low)["skipInS"], 1)

    def test_gdl_skips_and_corner_materials(self):
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                ).read_text(encoding="utf-8")
        self.assertIn("if row = 0 and ((ip = 1 and skipInS = 1) or (ip = nSpan + 1 and skipInE = 1)) then skipP = 1",
                      body)
        i = body.index("! コーナー踏板と、外側2辺の幅木")
        self.assertIn("if matDeck > 0 then material matDeck", body[i:i + 400])
