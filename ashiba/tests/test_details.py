import unittest

from _path import SRC  # noqa: F401

from ashiba.details import DETAIL_NAMES, required_details
from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
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


if __name__ == "__main__":
    unittest.main()
