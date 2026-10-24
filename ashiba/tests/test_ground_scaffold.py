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

    def test_three_levels_keep_stairs(self):
        r = solve_all({**SPEC, "ground_scaffold": {"levels": 3}})
        self.assertEqual(len(r.model.elevation.level_heights), 3)
        self.assertTrue(r.stair_plan.towers)

    def test_groups_and_bad_levels(self):
        g = solve_groups({**SPEC, "ground_scaffold": {"levels": 2}})
        self.assertEqual(len(g[0][1].model.elevation.level_heights), 2)
        with self.assertRaises(InputError):
            solve_all({**SPEC, "ground_scaffold": {"levels": 5}})

    def test_palette(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("地足場", dict(PANEL_GROUPS)["建てる"])
        self.assertIn("地足場", [a.title for a in ACTIONS])
        self.assertTrue((ROOT / "scripts" / "ground_scaffold_run.py").exists())


if __name__ == "__main__":
    unittest.main()
