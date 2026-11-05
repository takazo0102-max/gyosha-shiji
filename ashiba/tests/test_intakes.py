"""取り入れ口（利用者の指定 2026-10-24: 取り入れ口を作る仕組みを考えて作成して）."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = {"project_name": "a", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "module": "inch"}


class TestIntakes(unittest.TestCase):
    def setUp(self):
        self.r0 = solve_all(SPEC)
        ep = self.r0.model.plan.edges[0]
        self.x = sum(ep.spans[:2])                                   # 3スパン目の始め
        self.r = solve_all({**SPEC, "intakes": [{"face": "南面", "start_mm": self.x, "span_count": 1, "levels": "3-4"}]})

    def test_cells_drop_fixed_rails_and_toe_boards(self):
        (t,) = self.r.model.intakes
        self.assertEqual((t.span_from, t.span_to, t.level_from, t.level_to), (3, 3, 3, 4))
        e = next(x for x in self.r.model.member_edits if x.reason == "取り入れ口")
        self.assertEqual(set(e.parts), {"外側手すり", "幅木"})
        self.assertLess(self.r.quantity.qty_of("幅木"), self.r0.quantity.qty_of("幅木"))
        self.assertTrue(any("取り入れ口" in w and "可動手すり" in w for w in self.r.quantity.warnings))

    def test_line_gets_the_list_and_edits(self):
        p = line_params(self.r.model, self.r.model.plan.edges[0])
        a, b, l1, l2 = p["intkList"].split(",")
        self.assertEqual((float(a), int(l1), int(l2)), (self.x, 3, 4))
        self.assertTrue(p["editList"])
        self.assertEqual(line_params(self.r.model, self.r.model.plan.edges[1])["intkList"], "")

    def test_gdl_draws_the_gate_and_plan_note(self):
        gdl = ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts"
        self.assertIn("取り入れ口の可動手すり", (gdl / "3d.gdl").read_text(encoding="utf-8"))
        self.assertIn('"取り入れ口（"', (gdl / "2d.gdl").read_text(encoding="utf-8"))

    def test_command_updates_the_list(self):
        from intake_run import updated_intakes

        posts = [0.0, 1829.0, 3658.0, 5487.0, 7316.0]
        items = [{"face": "南面", "start_mm": 1829, "span_count": 2, "levels": "全部"}]
        self.assertEqual(updated_intakes(items, "南面", 3658.0, 1, "2-3", True, posts),
                         [{"face": "南面", "start_mm": 3658, "span_count": 1, "levels": "2-3"}])     # 重なる前の指定は外す
        self.assertEqual(updated_intakes(items, "南面", 3658.0, 1, "", False, posts), [])
        self.assertEqual(len(updated_intakes(items, "東面", 0.0, 1, "", True, posts)), 2)


if __name__ == "__main__":
    unittest.main()
