import unittest

from _path import SRC  # noqa: F401

from ashiba.details import DETAIL_NAMES, required_details
from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
LSHAPE = [(0, 0), (30000, 0), (30000, 12000), (18000, 12000), (18000, 20000), (0, 20000)]


def make_model(height=16300, outline=RECT, series="shinwa_A"):
    master = load_master(series)
    plan = solve_plan(outline, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(period_days=90), building_height_mm=16000,
    )


class TestRequiredDetails(unittest.TestCase):
    def test_always_required_three(self):
        sheets = required_details(make_model(height=8000))
        keys = [s.key for s in sheets]
        self.assertEqual(keys, ["base", "tie", "corner"])
        # 高さ8mなら朝顔は不要
        self.assertNotIn("asagao", keys)
        # 開口指定がなければ梁枠も不要
        self.assertNotIn("beam", keys)

    def test_asagao_required_over_10m(self):
        keys = [s.key for s in required_details(make_model(height=16300))]
        self.assertIn("asagao", keys)
        sheet = [s for s in required_details(make_model(height=16300))
                 if s.key == "asagao"][0]
        self.assertIn("1段", sheet.reason)

    def test_asagao_two_stages_over_20m(self):
        sheet = [s for s in required_details(make_model(height=25000))
                 if s.key == "asagao"][0]
        self.assertIn("2段", sheet.reason)

    def test_beam_only_with_openings(self):
        m = make_model()
        self.assertNotIn("beam", [s.key for s in required_details(m)])
        sheets = required_details(m, openings=[{"beam_span_mm": 5400}])
        beams = [s for s in sheets if s.key == "beam"]
        self.assertEqual(len(beams), 1)
        self.assertAlmostEqual(beams[0].params["beamSpan"], 5.4)

    def test_multiple_openings_numbered(self):
        sheets = required_details(
            make_model(), openings=[{"beam_span_mm": 3600}, {"beam_span_mm": 5400}]
        )
        beams = [s for s in sheets if s.key == "beam"]
        self.assertEqual(len(beams), 2)
        self.assertIn("開口1", beams[0].title)
        self.assertIn("開口2", beams[1].title)

    def test_force_all_gives_five(self):
        sheets = required_details(make_model(height=8000), force_all=True)
        self.assertEqual({s.key for s in sheets}, set(DETAIL_NAMES))

    def test_keys_are_ascii(self):
        # 日本語キーを外部からGDLに渡すと比較が一致しない（実機で確認済み）
        for s in required_details(make_model(), force_all=True):
            self.assertTrue(s.key.isascii(), s.key)
            self.assertEqual(s.params["serType"], "A")

    def test_series_b_switches_dimensions(self):
        m = make_model(height=16150, series="shinwa_B")
        for s in required_details(m):
            self.assertEqual(s.params["serType"], "B")

    def test_params_derived_from_model(self):
        m = make_model()
        by_key = {s.key: s for s in required_details(m)}
        # 脚部: ジャッキ繰出しは立面ソルバの解
        self.assertAlmostEqual(
            by_key["base"].params["jackOut"], m.elevation.jack_extension / 1000.0
        )
        # 壁つなぎ: 実配置の最大間隔
        v_max, h_max = m.wall_tie_max_spacing()
        self.assertAlmostEqual(by_key["tie"].params["tieV"], v_max / 1000.0)
        self.assertAlmostEqual(by_key["tie"].params["tieH"], h_max / 1000.0)
        # 代表スパンは最頻値
        self.assertAlmostEqual(by_key["base"].params["spanW"], 1.8)

    def test_corner_reason_counts_lshape(self):
        sheet = [s for s in required_details(make_model(outline=LSHAPE))
                 if s.key == "corner"][0]
        self.assertIn("出隅5", sheet.reason)
        self.assertIn("入隅1", sheet.reason)


class TestFrameSeriesDetails(unittest.TestCase):
    """詳細図はくさびの納まり。枠組で使うことを図面に出す."""

    def test_frame_uses_its_own_series_type(self):
        frame = required_details(make_model(series="waku"))[0]
        wedge = required_details(make_model(series="shinwa_A"))[0]
        self.assertEqual(frame.params["serType"], "W")
        self.assertEqual(wedge.params["serType"], "A")

    def test_negarami_height_comes_from_the_solver(self):
        """コマピッチで決め打ちすると、コマの概念が無い枠組で0になる."""
        m = make_model(series="shinwa_A")
        base = required_details(m)[0]
        self.assertAlmostEqual(
            base.params["negaLv"],
            (m.elevation.first_ledger_height - m.elevation.jack_extension) / 1000.0,
        )

    def test_tie_limits_follow_the_series(self):
        """図面に埋め込む法規しきい値も系列で変わる（570条1項五号）."""
        frame = required_details(make_model(series="waku"))[0]
        wedge = required_details(make_model(series="shinwa_A"))[0]
        self.assertEqual((frame.params["tieVLim"], frame.params["tieHLim"]), (9.0, 8.0))
        self.assertEqual((wedge.params["tieVLim"], wedge.params["tieHLim"]), (5.0, 5.5))


class TestSheetsMatchThePlan(unittest.TestCase):
    """添付図書が計画と食い違わないこと（既定値で描いていた）."""

    def _model(self, **kw):
        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            building_height_mm=16000, **kw,
        )

    def test_asagao_uses_the_planned_projection_and_angle(self):
        m = self._model(config=ScaffoldConfig(
            asagao=AsagaoSpec(stages=2, projection_mm=2500, angle_deg=30)))
        sheet = {s.key: s for s in required_details(m)}["asagao"]
        self.assertEqual(sheet.params["asagaoProj"], 2.5)
        self.assertEqual(sheet.params["asagaoAngle"], 30)

    def test_planned_stage_count_is_stated_when_it_differs(self):
        m = self._model(config=ScaffoldConfig(asagao=AsagaoSpec(stages=2)))
        sheet = {s.key: s for s in required_details(m)}["asagao"]
        self.assertIn("計画は2段", sheet.reason)

    def test_base_sheet_draws_the_worst_jack(self):
        """平坦時の繰出しで描くと、法規チェックの警告と図面が食い違う."""
        from ashiba.terrain import GroundModel, solve_post_feet

        m = self._model(config=ScaffoldConfig())
        ground = GroundModel(points=[
            (x, y, -x * 0.02) for x in (0, 15000, 30000) for y in (0, 20000)
        ])
        terrain = solve_post_feet(m, ground)
        flat = {s.key: s for s in required_details(m)}["base"]
        slope = {s.key: s for s in required_details(m, terrain=terrain)}["base"]
        worst = max(f.jack_mm for f in terrain.feet)
        self.assertGreater(worst, m.elevation.jack_extension)
        self.assertAlmostEqual(slope.params["jackOut"], round(worst) / 1000.0, 3)
        self.assertGreater(slope.params["jackOut"], flat.params["jackOut"])
        self.assertIn("敷地高低差", slope.reason)


if __name__ == "__main__":
    unittest.main()
