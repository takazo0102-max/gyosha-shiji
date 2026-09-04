"""インチ系列: 型番仮のマスタで計画が解け、暫定耐力値は要確認に出る."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all
from ashiba.master import load_master

ROOT = Path(__file__).resolve().parents[1]


class TestInchSeries(unittest.TestCase):
    def test_master_is_complete_and_flagged_provisional(self):
        m = load_master("inch")
        cats = {p.category for p in m.parts}
        for need in ("支柱", "布材", "踏板", "ジャッキ", "壁つなぎ", "筋交", "幅木", "階段", "梁枠"):
            self.assertIn(need, cats)
        self.assertEqual(m.span_lengths(), [1829, 1524, 1219, 914, 610])
        self.assertEqual(m.post_lengths(), [3658, 2743, 1829, 914, 457])
        self.assertEqual(m.deck_widths_available(), {500, 240})
        # 型番仮であることは全行に書いてある（本物と混ざらない）
        self.assertTrue(all("型番仮" in p.note for p in m.parts if p.category != "布材"))

    def test_example_solves_with_unverified_capacity_notice(self):
        r = solve_all(load_spec(ROOT / "examples" / "inch_rect.json"))
        self.assertEqual(r.model.master.series_id, "inch")
        self.assertTrue(all(s in (1829, 1524, 1219, 914, 610)
                            for e in r.model.plan.edges for s in e.spans))
        self.assertGreater(r.quantity.total_weight_kg, 0)
        # 暫定耐力値は「未確認」として要確認に出る（黙って通さない）
        self.assertTrue([w for w in r.warnings if "未確認" in w[2]], r.warnings)

    def test_long_face_is_not_filled_with_short_spans(self):
        """候補を「目標長に近い6件」に絞っていたとき、30m面が610×50本になっていた."""
        from ashiba.plan_solver import solve_plan

        m = load_master("inch")
        plan = solve_plan([(0, 0), (30000, 0), (30000, 20000), (0, 20000)], m)
        for e in plan.edges:
            small = sum(1 for s in e.spans if s < 1829)
            self.assertLessEqual(small, 2, (e.edge_index, e.spans))
            self.assertGreaterEqual(e.standoff, 200)


if __name__ == "__main__":
    unittest.main()
