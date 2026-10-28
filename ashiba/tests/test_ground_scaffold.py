"""地足場（利用者の指定 2026-10-24: 地足場機能も追加して）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, solve_all, solve_groups

ROOT = Path(__file__).resolve().parents[1]
SPEC = {"project_name": "g", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "module": "inch"}


class TestGroundScaffold(unittest.TestCase):
    def test_one_level_with_a_ladder(self):
        r = solve_all({**SPEC, "ground_scaffold": True})
        self.assertEqual(r.model.elevation.level_heights, [1800])
        self.assertEqual(len(r.stair_plan.towers), 0)
        self.assertGreaterEqual(r.model.config.ladders, 1)
        self.assertIsNone(r.model.config.asagao)
        self.assertEqual(r.model.roof_bridges, [])
        self.assertTrue(any("地足場（1層" in w for w in r.model.plan.warnings))
        # 実機 2026-10-24: 「階段室が入る区間が無い規模」「昇降設備がありません」と出た（はしごで昇降する）
        self.assertFalse(any("入る区間が無い規模" in w or "昇降設備がありません" in w for w in r.stair_plan.warnings))

    def test_three_levels_keep_stairs(self):
        r = solve_all({**SPEC, "ground_scaffold": {"levels": 3}})
        self.assertEqual(len(r.model.elevation.level_heights), 3)
        self.assertTrue(r.stair_plan.towers)

    def test_groups_and_bad_levels(self):
        g = solve_groups({**SPEC, "ground_scaffold": {"levels": 2}})
        self.assertEqual(len(g[0][1].model.elevation.level_heights), 2)
        with self.assertRaises(InputError):
            solve_all({**SPEC, "ground_scaffold": {"levels": 5}})

    def test_standoff_clears_the_formwork(self):
        # 躯体の面から 500 以上離す（型枠・端太・セパを収める。報告 地足場と内部足場 2026-10-28）
        r = solve_all({**SPEC, "ground_scaffold": True})
        # 離れはスパンの割付で数 mm 動く（インチの割付で 498）
        self.assertTrue(all(v >= 490 for v in r.model.plan.standoffs), r.model.plan.standoffs)
        note = next(w for w in r.model.plan.warnings if "地足場（1層" in w)
        self.assertIn("控え", note)
        self.assertIn("500mm 離して", note)
        wide = solve_all({**SPEC, "ground_scaffold": {"levels": 1, "standoff_mm": 700}})
        self.assertTrue(all(v >= 690 for v in wide.model.plan.standoffs), wide.model.plan.standoffs)
        normal = solve_all(SPEC)
        self.assertTrue(any(v < 450 for v in normal.model.plan.standoffs))

    def test_deck_height_against_the_ground_beam(self):
        # 作業床は地中梁の天端（ふかし筋）＋500〜800 が目安（報告 地足場と内部足場 2026-10-28）
        ok = solve_all({**SPEC, "ground_scaffold": {"levels": 1, "beam_top_mm": 1150}})
        note = next(w for w in ok.model.plan.warnings if "地足場（1層" in w)
        self.assertIn("天端 1150 から +650", note)
        low = solve_all({**SPEC, "ground_scaffold": {"levels": 1, "beam_top_mm": 1600}})
        note = next(w for w in low.model.plan.warnings if "地足場（1層" in w)
        self.assertIn("目安 +500〜800 を外れる", note)

    def test_palette(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("地足場", dict(PANEL_GROUPS)["建てる"])
        self.assertIn("地足場", [a.title for a in ACTIONS])
        self.assertTrue((ROOT / "scripts" / "ground_scaffold_run.py").exists())


if __name__ == "__main__":
    unittest.main()
