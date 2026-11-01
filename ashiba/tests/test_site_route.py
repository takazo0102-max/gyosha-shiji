"""場内の車両動線と敷鉄板（開発ループ 2026-11-01: 他に必要な仮設材の3番）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.site_route import corner_need, part_params, route_plan, swept


class TestSwept(unittest.TestCase):
    def test_matches_the_research_table(self):
        """最小回転半径で回ったときの外側前端角 Ro と内側後輪 ri（調べたメモの計算例: 10t 7.6・3.1、構造令 13.1・7.8）."""
        for v, ro, ri in (("10t", 7.6, 3.1), ("mixer", 7.9, 3.3), ("std", 13.1, 7.8), ("4t", 5.7, 1.8), ("R25", 9.5, 2.3)):
            r = swept(v)
            self.assertAlmostEqual(r[0] / 1000, ro, delta=0.06, msg=v)
            self.assertAlmostEqual(r[1] / 1000, ri, delta=0.06, msg=v)

    def test_corner_width(self):
        """直角に曲がる大型車は 5〜6m 要る（メモ: 大型で 5.0〜5.5m＋余裕）。浅い角ほど狭くて済み、直線が短いと回れない."""
        need90 = corner_need("10t", 90.0, 30000.0, 4000.0)[0]
        self.assertTrue(5000.0 < need90 < 6200.0, need90)
        self.assertLess(corner_need("10t", 30.0, 30000.0, 4000.0)[0], need90)
        self.assertLess(corner_need("4t", 90.0, 30000.0)[0], need90)
        self.assertEqual(corner_need("10t", 90.0, 1000.0, 4000.0)[3], -1.0)
        self.assertEqual(corner_need("10t", 1.0, 30000.0)[0], 0.0)


class TestRoute(unittest.TestCase):
    def test_widening_and_plates(self):
        p = route_plan("通路1", [(0, 0), (30000, 0), (30000, 25000)], vehicle="10t")
        st = {c.item: c.status for c in p.checks}
        self.assertEqual((st["通路の幅"], st["曲がり角 1"]), ("OK", "NG"))
        self.assertIn("拡幅", next(c.message for c in p.checks if c.item == "曲がり角 1"))
        wide = route_plan("通路2", [(0, 0), (30000, 0), (30000, 25000)], width=6500.0, vehicle="10t")
        self.assertEqual({c.item: c.status for c in wide.checks}["曲がり角 1"], "OK")
        # 敷鉄板: 始めの区間はゲートから、余りは 5×10 で埋めて行き過ぎ 3m 未満、終わりの区間は終わりにそろえる
        (c0, a0, l0), (_c1, _a1, l1), (c2, a2, l2), (c3, _a3, l3) = p.plates
        self.assertEqual((c0[0], a0, l0.code, l1.code), (0.0, 0.0, "NT22×5×20", "NT22×5×10"))
        self.assertLess(l0.lx + l1.lx - 32000.0, 3048.0)
        self.assertAlmostEqual(c3[1] + l3.lx, 25000.0, delta=1.0)
        self.assertEqual(round(a2), 90)
        q = {a: n for a, n, _c in p.quantity}
        self.assertEqual(q["厚板鋼板 NT22×5×20（1524×6096×22）"], (l0.count + l2.count))

    def test_two_way_and_params(self):
        p = route_plan("通路3", [(0, 0), (20000, 0)], two_way=True, vehicle="mixer", plates=False)
        self.assertEqual(p.width, 6000.0)
        self.assertEqual({c.item: c.status for c in p.checks}["通路の幅"], "OK")
        self.assertFalse(p.plates)
        narrow = route_plan("通路4", [(0, 0), (20000, 0)], width=5000.0, two_way=True, plates=False)
        self.assertEqual({c.item: c.status for c in narrow.checks}["通路の幅"], "NG")   # 要綱の2車線 5.5m
        prm = part_params(route_plan("通路1", [(1000, 2000), (31000, 2000), (31000, 27000)]))
        self.assertEqual((prm["cX"], prm["cY"], prm["aW"]), ("0,30000,30000", "0,0,25000", "19"))
        self.assertTrue(all(len(v) <= 255 for v in prm.values() if isinstance(v, str)))


if __name__ == "__main__":
    unittest.main()
