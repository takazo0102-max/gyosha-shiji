"""幅の違う本足場の組と出会う出隅（利用者の指摘 2026-10-24: 端部が重なったり、回れないようになってる）.

南面だけ本足場（狭い幅 610）にすると、面の組ごとに解くので南東・南西の隅が開放端になり、
外側の升目が抜け、両方の面の端に妻側の手すりが付き、隅の内側建地が2本重なっていた。
"""

import unittest

from ashiba.cli import solve_groups
from ashiba.gdl_params import line_params

B = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]
NARROW = "本足場（狭い幅）"


def _runs():
    spec = {"project_name": "隅", "outline_mm": B, "eaves_height_mm": 9000, "scaffold_width_mm": 914,
            "face_forms": {"南面": NARROW}}
    runs = solve_groups(spec)
    return next(r for lb, r in runs if lb == ""), next(r for lb, r in runs if lb == NARROW)


def _params(r, ei):
    ep = next(e for e in r.model.plan.edges if e.edge_index == ei)
    return line_params(r.model, ep, stair_plan=r.stair_plan)


class TestCornersAcrossGroups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main, cls.narrow = _runs()
        cls.east, cls.west = _params(cls.main, 1), _params(cls.main, 3)
        cls.south = _params(cls.narrow, 0)

    def test_no_end_rails_at_the_corners(self):
        # 妻側の手すりで塞がない（回れる）
        self.assertEqual((self.south["endOpenS"], self.south["endOpenE"]), (0, 0))
        self.assertEqual(self.east["endOpenS"], 0)
        self.assertEqual(self.west["endOpenE"], 0)

    def test_outer_cell_is_drawn_once_with_both_widths(self):
        # 南東は東面（914）の始点、南西は南面（610）の始点が描く。升目は 610×914 の長方形
        self.assertEqual(self.east["cornerS"], 1)
        self.assertAlmostEqual(self.east["cornerSW"], 0.610)
        self.assertEqual(self.south["cornerS"], 1)
        self.assertAlmostEqual(self.south["cornerSW"], 0.914)
        # 寸法の外側の角: 西面の終点は南面の幅、南面の終点は東面の幅の先
        self.assertAlmostEqual(self.west["cornerEW"], 0.610)
        self.assertAlmostEqual(self.south["cornerEW"], 0.914)
        self.assertEqual(self.main.model.outer_corner_posts() + self.narrow.model.outer_corner_posts(), 4)

    def test_inner_corner_post_is_drawn_by_one_face(self):
        self.assertEqual(self.south["skipInE"] + self.east["skipInS"], 1)       # 南東
        self.assertEqual(self.west["skipInE"] + self.south["skipInS"], 1)       # 南西

    def test_faces_meet_on_the_inner_post_lines(self):
        south = next(e for e in self.narrow.model.plan.edges if e.edge_index == 0)
        east = next(e for e in self.main.model.plan.edges if e.edge_index == 1)
        # 東面の始点は南面の内側建地列の上、南面の終点は東面の内側建地列の上
        self.assertAlmostEqual(east.start_post[1], -south.standoff, delta=0.6)
        self.assertAlmostEqual(south.start_post[0] + sum(south.spans), east.start_post[0], delta=0.6)

    def test_corner_deck_and_ledgers_use_the_neighbour_width(self):
        q = self.narrow.quantity
        notes = " ".join(q.notes)
        self.assertIn("914×610", notes)
        deck = [l for l in q.lines if l.part.category == "踏板" and l.part.nominal_dim == 914]
        self.assertTrue(deck, "南西の隅の踏板（長さ914）")


if __name__ == "__main__":
    unittest.main()
