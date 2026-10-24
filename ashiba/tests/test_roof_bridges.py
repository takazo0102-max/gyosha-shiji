"""屋上への渡り（利用者の指定 2026-10-24: 屋上への渡りもGDL作成して 平面に表記するようにして）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import BRIDGE_OBJECT, bridge_placements
from ashiba.cli import solve_all

SPEC = {"project_name": "a", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "module": "inch"}
HSF = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_bridge"


class TestRoofBridges(unittest.TestCase):
    def test_one_bridge_next_to_the_stair(self):
        r = solve_all(SPEC)
        (b,) = r.model.roof_bridges
        t = r.stair_plan.towers[0]
        self.assertEqual(b.edge_index, t.edge_index)
        self.assertAlmostEqual(b.x_mm, t.end_mm)                      # 階段室の降り口の先のスパン
        self.assertEqual(b.z_from_mm, r.model.elevation.level_heights[-1])
        self.assertTrue(any("屋上への渡り" in w for w in r.quantity.warnings))
        (p,) = bridge_placements(r.model)
        self.assertEqual(p.part, BRIDGE_OBJECT)
        self.assertAlmostEqual(p.params["brL"] * 1000, b.length_mm)

    def test_manual_position_and_parapet(self):
        r = solve_all({**SPEC, "roof_bridges": [{"face": "北面", "position_mm": 3000, "parapet_mm": 600}]})
        (b,) = r.model.roof_bridges
        self.assertEqual(r.model.face_name(b.edge_index), "北面")
        self.assertEqual((b.x_mm, b.parapet_mm), (3000.0, 600.0))
        self.assertAlmostEqual(bridge_placements(r.model)[0].params["paraH"], 0.6)

    def test_bridge_starts_at_the_level_nearest_the_roof(self):
        # 実機 2026-10-24: セットバックの低い面で最上段が屋根より 1775 上になり「下り1775」の渡りになった
        from test_setback_tiers import SPEC as SB

        from ashiba.cli import solve_groups

        g = solve_groups({**SB, "stairs": {"layout": "自動"}})
        main = g[0][1]
        for b in main.model.roof_bridges:
            self.assertLessEqual(abs(b.z_to_mm - b.z_from_mm), 900)
        # 面の組ごとの数量で二重に手配しない
        notes = [w for w in main.quantity.warnings if "屋上への渡り" in w]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("辺0", notes[0])

    def test_off(self):
        self.assertEqual(solve_all({**SPEC, "roof_bridge": False}).model.roof_bridges, [])

    def test_part_draws_plan_and_3d(self):
        d2 = (HSF / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        d3 = (HSF / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("text2 0, 0, tx", d2)                  # 平面に「屋上への渡り 幅600 …」
        self.assertIn("rect2 0, yS, brW, brL", d2)
        self.assertIn("cylind 0.95, 0.0243", d3)             # 手すりの支柱
        self.assertIn("パラペット", d3)
        self.assertTrue((HSF.parents[1] / "ashiba_bridge.gsm").exists())


if __name__ == "__main__":
    unittest.main()
