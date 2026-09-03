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

    def test_quadruple_is_start_length_projection_height(self):
        m, pf = self._setup()
        vals = line_params(m, m.plan.edges[0], platforms=pf)["stageList"].split(",")
        self.assertEqual(len(vals), 4)
        self.assertEqual(int(vals[0]), 12600)
        self.assertEqual(int(vals[2]), int(pf.stages[0].projection_mm))
        self.assertEqual(int(vals[3]), m.elevation.level_heights[2])

    def test_one_group_per_level(self):
        m, pf = self._setup(levels=(3, 4))
        vals = line_params(m, m.plan.edges[0], platforms=pf)["stageList"].split(",")
        self.assertEqual(len(vals), 8)
        self.assertEqual(int(vals[7]), m.elevation.level_heights[3])

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

        def create_object(self, name, x, y):
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
        self.assertEqual(len(line), 1, "ジャッキ繰出しの記載は1箇所")
        self.assertIn("dy - txtLine * 3.4", line[0])

    def test_span_total_and_jack_are_on_separate_lines(self):
        # 短い面では L= と横並びになる。行を変えて避ける
        total = [ln for ln in self.body.splitlines()
                 if '"L=" + str(lineLen' in ln and "dy - txtLine * 2.2" in ln]
        self.assertEqual(len(total), 1, "立面の全長寸法は1箇所")
