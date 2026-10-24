"""大きなセットバック: 上の階の面の足場を途中の屋根の上から建てて本体の足場に繋ぐ（利用者の指定 2026-10-24: セットバックの
時は途中の屋根から足場が繋がるようにする仕組みを作って）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_groups
from ashiba.gdl_params import line_params
from ashiba.setback_tiers import setback_tiers

LOW = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]
UP = [[0, 3000], [24000, 3000], [24000, 10000], [0, 10000]]          # 南を 3000 下げた 4〜6階
SLABS = ([{"polygon_mm": LOW, "top_mm": t} for t in (3000, 6000, 9000)]
         + [{"polygon_mm": UP, "top_mm": t} for t in (12000, 15000, 18000)])
SPEC = {"project_name": "S", "outline_mm": LOW, "slabs": SLABS, "module": "inch", "eaves_height_mm": 18000}


class TestSetbackTiers(unittest.TestCase):
    def test_finds_the_upper_face_and_the_middle_roof(self):
        t = setback_tiers(LOW, SLABS)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["top_mm"], 18000)
        self.assertEqual([b for _i, b in t[0]["faces"]], [9000.0])        # 南の面だけ、途中の屋根 GL+9000 から

    def test_small_setback_is_left_to_inner_brackets(self):
        up = [[0, 600], [24000, 600], [24000, 10000], [0, 10000]]
        slabs = SLABS[:3] + [{"polygon_mm": up, "top_mm": 18000}]
        self.assertEqual(setback_tiers(LOW, slabs), [])

    def test_upper_tier_is_a_group_standing_on_the_roof(self):
        g = solve_groups(SPEC)
        self.assertEqual([lb for lb, _r in g], ["", "上段"])
        main, tier = g[0][1].model, g[1][1].model
        self.assertLess(main.elevation_of(0).total_height, main.elevation.total_height)   # 本体の南は途中の屋根まで
        self.assertEqual(tier.base_height_mm, 9000.0)
        self.assertEqual(tier.plan.face_names(), ["南面"])
        self.assertAlmostEqual(tier.elevation.total_height, main.elevation_of(0).total_height, delta=200)
        # 端は本体の足場（東・西）に繋ぐ。妻側の手すりは付けない
        p = line_params(tier, tier.plan.edges[0])
        self.assertEqual((p["endOpenS"], p["endOpenE"]), (0, 0))
        # 上段の端は本体の東西の足場の内側建地列の線まで
        xs = sorted(x for e in main.plan.edges for x, _y in (e.start_post, e.end_post))
        self.assertAlmostEqual(tier.plan.edges[0].start_post[0], xs[0], delta=1.0)
        self.assertAlmostEqual(tier.plan.edges[0].end_post[0], xs[-1], delta=1.0)
        self.assertTrue(any("途中の屋根（GL+9000）" in w for w in main.plan.warnings))

    def test_can_be_turned_off(self):
        self.assertEqual(len(solve_groups({**SPEC, "setback_tiers": False})), 1)


BIG = [[0, -2000], [24000, -2000], [24000, 10000], [0, 10000]]    # 2階から上が南へ 2000 張り出す
SL_OVER = ([{"polygon_mm": LOW, "top_mm": 0}]
           + [{"polygon_mm": BIG, "top_mm": t} for t in (3000, 6000, 9000, 12000)])


class TestOverhangTier(unittest.TestCase):
    """上の階が外へ張り出す（拡張。利用者の指定 2026-10-24: 上階で拡張する仕組みと拡小する仕組みを作って）."""

    SP = {"project_name": "H", "outline_mm": LOW, "slabs": SL_OVER, "module": "inch", "eaves_height_mm": 12000}

    def test_upper_tier_stands_on_brackets(self):
        g = solve_groups(self.SP)
        self.assertEqual([lb for lb, _r in g], ["", "上段（張り出し）"])
        main, tier = g[0][1].model, g[1][1].model
        self.assertTrue(tier.hane_bracket)
        self.assertEqual(tier.base_height_mm, 3000.0)
        self.assertEqual(len(tier.plan.edges), 4)                                      # 全周
        self.assertAlmostEqual(line_params(tier, tier.plan.edges[0])["haneD"], 0.6)
        self.assertEqual(line_params(main, main.plan.edges[0])["haneD"], 0.0)
        # 本体の足場はブラケットの下端（3000−600）より下で止まる。張り出しを庇としてかわさない（離れはそのまま）
        for e in main.plan.edges:
            self.assertLessEqual(main.elevation_of(e.edge_index).total_height, 2400)
        self.assertLess(max(e.standoff for e in main.plan.edges), 600)
        self.assertTrue(any("跳ね出しブラケット" in w for w in g[1][1].quantity.warnings))
        self.assertTrue(any("張り出した上の階" in w for w in main.plan.warnings))

    def test_gdl_draws_the_brackets(self):
        from pathlib import Path

        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"
        self.assertIn("if haneD > 0.001 then", (gdl / "3d.gdl").read_text(encoding="utf-8"))
        self.assertIn("跳ね出しブラケットの上に建てる", (gdl / "2d.gdl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
