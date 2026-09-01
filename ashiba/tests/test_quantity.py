import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


class TestQuantity(unittest.TestCase):
    def setUp(self):
        self.master = load_master("shinwa_A")
        self.plan = solve_plan(RECT, self.master)
        self.elev = solve_elevation(16300, master=self.master)
        self.model = ScaffoldModel(
            master=self.master,
            plan=self.plan,
            elevation=self.elev,
            config=ScaffoldConfig(),
            building_height_mm=16000,
        )
        self.q = take_off(self.model)

    def test_dependent_parts_rules(self):
        # アンダーベース数 = ジャッキ数 = 支柱位置数×2列（本足場）
        n_jack = self.q.qty_of("ジャッキ")  # ジャッキ+アンダーベース両方このカテゴリ
        jacks = [l for l in self.q.lines if l.part.category == "ジャッキ"]
        by_note = {("アンダーベース" in l.part.note): l.qty for l in jacks}
        self.assertEqual(by_note[True], by_note[False])
        self.assertEqual(by_note[False], self.plan.total_posts * 2)

    def test_post_counts(self):
        per_line = len(self.elev.posts)
        total = self.q.qty_of("支柱")
        self.assertEqual(total, self.plan.total_posts * 2 * per_line)

    def test_deck_counts(self):
        # 踏板: スパン数×層数×幅構成2枚
        n_deck = self.q.qty_of("踏板")
        self.assertEqual(
            n_deck, self.plan.total_spans * self.elev.n_levels * 2
        )

    def test_braces_from_faces(self):
        # ブレスは1800スパンの構面数から
        n1800 = sum(1 for e in self.plan.edges for s in e.spans if s == 1800)
        self.assertEqual(self.q.qty_of("筋交"), n1800 * self.elev.n_levels)

    def test_kake_menseki(self):
        # (外周100m+4m)×(高さ16m+0.5m)
        self.assertAlmostEqual(self.q.kake_menseki_m2, 104 * 16.5, delta=0.1)

    def test_weight_and_trucks(self):
        self.assertGreater(self.q.total_weight_kg, 0)
        self.assertGreaterEqual(self.q.truck_count, 1)
        calc = sum(l.part.weight_kg * l.qty for l in self.q.lines)
        self.assertAlmostEqual(self.q.total_weight_kg, calc, delta=0.5)

    def test_wall_ties_generated_and_counted(self):
        self.assertTrue(self.model.wall_ties)
        self.assertEqual(self.q.qty_of("壁つなぎ"), len(self.model.wall_ties))
        v_max, h_max = self.model.wall_tie_max_spacing()
        self.assertLessEqual(v_max, 5000)
        self.assertLessEqual(h_max, 5500)

    def test_single_row_scaffold(self):
        cfg = ScaffoldConfig(scaffold_form="一側足場")
        model = ScaffoldModel(
            master=self.master, plan=self.plan, elevation=self.elev, config=cfg
        )
        q = take_off(model)
        jacks = [l for l in q.lines if l.part.category == "ジャッキ" and "アンダー" not in l.part.note]
        self.assertEqual(jacks[0].qty, self.plan.total_posts)


if __name__ == "__main__":
    unittest.main()
