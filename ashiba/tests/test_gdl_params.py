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
