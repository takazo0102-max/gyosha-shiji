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
from ashiba.tapir_adapter import _line_params

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
                p = _line_params(m, m.plan.edges[0])
                self.assertEqual(
                    p["levelList"],
                    ",".join(str(h) for h in m.elevation.level_heights),
                )

    def test_rail_heights_are_nonzero_for_frames(self):
        """枠組は komaPitch=0。手すり高さを komaPitch から作ると作業床に重なって消える."""
        m = build("waku")
        p = _line_params(m, m.plan.edges[0])
        self.assertEqual(p["komaPitch"], 0.0)
        self.assertGreater(p["railH"], 0)
        self.assertGreater(p["midH"], 0)
        self.assertGreater(p["railH"], p["midH"])

    def test_row_width_and_deck_widths_follow_the_series(self):
        """既定値のままだと系列に関係なくA系列の幅で描かれる."""
        widths = {
            sid: _line_params(build(sid), build(sid).plan.edges[0])
            for sid in ("shinwa_A", "shinwa_B", "waku")
        }
        self.assertNotEqual(widths["shinwa_A"]["deckW1"], widths["waku"]["deckW1"])
        for sid, p in widths.items():
            m = build(sid)
            with self.subTest(sid):
                self.assertAlmostEqual(p["rowW"], m.deck_width_total / 1000.0)
                self.assertAlmostEqual(
                    p["deckW1"], m.config.deck_widths[0] / 1000.0
                )

    def test_plan_and_elevation_share_the_same_geometry(self):
        """平面と立面で別々に組み立てると片方だけ渡し漏れる."""
        m = build("shinwa_A")
        p = _line_params(m, m.plan.edges[0])
        for key in ("rowW", "deckW1", "levelList", "railH", "negaH"):
            self.assertIn(key, p)


if __name__ == "__main__":
    unittest.main()
