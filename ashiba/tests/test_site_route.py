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


class TestTrailerRoute(unittest.TestCase):
    """搬入トラック・トレーラー連結車の曲がり角（2026-11-04 利用者の指定「場内通路にトレーラーも入れて進めて」）."""

    def test_follow_reaches_steady_turn(self):
        """前軸を円の上で回り続けると、後軸・トレーラーの後軸群の半径は定常円旋回（machine.swept_path）の値に近づく
        （折れ角の大きい 4軸の中低床は刻みの誤差で 0.1m ほど内へ出る）."""
        import math

        from ashiba.machine import MACHINES, swept_path
        from ashiba.swept_sim import rig, simulate

        for k in ("lb4", "fb3", "tr10"):
            r = rig(k)
            R = r.rg_min
            g = [(R * math.sin(i * 0.1 / R), R - R * math.cos(i * 0.1 / R)) for i in range(int(8 * math.pi * R / 0.1))]
            *_, (_f, rear, tax, pts) = simulate(r, g)
            sw = swept_path(MACHINES[k], dict(MACHINES[k].params))
            self.assertAlmostEqual(max(math.dist(q, (0, R)) for q in pts), sw["外側"], delta=0.05, msg=k)
            if r.trailer:
                ps = MACHINES[k].params
                rt = math.dist(tax, (0, R))
                self.assertAlmostEqual(rt - ps["tlT"] / 2, sw["内側"], delta=0.15, msg=k)

    def test_follow_is_narrower_than_steady(self):
        """直角に曲がり終えるときは、定常円旋回の値を同じ角の式（Ro − ri·cos(θ/2) ＋ 余裕×(1＋cos(θ/2))）に入れたより狭く済む
        （トレーラーが内へ入り切らない）。浅い角はもっと狭い."""
        import math

        from ashiba.machine import MACHINES, swept_path
        from ashiba.swept_sim import corner

        c = math.cos(math.radians(45))
        for k in ("lb4", "lb2", "fb3"):
            ps = MACHINES[k].params
            c90 = corner(k, 90.0, 40.0)
            sw = swept_path(MACHINES[k], dict(ps))
            ri = sw["内側"] - (ps["tlW"] - ps["tlT"]) / 2              # 車輪の外の縁 → 車体の辺
            steady = sw["外側"] - ri * c + 0.25 * (1 + c)
            self.assertLess(c90.need, steady, k)
            self.assertLess(corner(k, 45.0, 40.0).need, c90.need, k)
        self.assertLess(corner("tr10", 90.0, 40.0).need, corner("lb4", 90.0, 40.0).need)
        self.assertTrue(8.0 < corner("lb4", 90.0, 40.0).need < 10.5)

    def test_rigid_follow_close_to_formula(self):
        """単車を追従で回すと、場内通路の式（最小回転半径でいきなり回る）より少し狭い（1割以内）."""
        import math

        from ashiba.site_route import VEHICLES
        from ashiba.swept_sim import Rig, _evaluate

        n, L, F, W, T, R = (x / 1000 if isinstance(x, float) else x for x in VEHICLES["10t"])
        rr = math.sqrt(R * R - L * L) - T / 2
        rg = math.hypot(rr, L)
        r = Rig("10t", n, L, F, L / 2 + 1.0, W, rg)
        sim = min(_evaluate(r, math.radians(90), rg + i * 0.5, 0.25).need for i in range(20))
        ana = corner_need("10t", 90.0, 30000.0)[0] / 1000
        self.assertTrue(0.9 * ana < sim <= ana, (sim, ana))

    def test_trailer_route(self):
        p = route_plan("通路1", [(0, 0), (30000, 0), (30000, 25000)], vehicle="lb4")
        st = {c.item: c for c in p.checks}
        self.assertEqual(st["曲がり角 1"].status, "NG")
        self.assertIn("追従の軌跡", st["曲がり角 1"].message)
        self.assertIn("【目安】", st["曲がり角 1"].message)
        self.assertIn("2.99m", st["通路の幅"].message)              # 車幅はトレーラーの 2.99
        self.assertEqual(st["荷下ろしの直線"].status, "OK")
        wide = route_plan("通路2", [(0, 0), (30000, 0), (30000, 25000)], width=9500.0, vehicle="lb4", plates=False)
        self.assertEqual({c.item: c.status for c in wide.checks}["曲がり角 1"], "OK")
        short = route_plan("通路3", [(0, 0), (30000, 0), (30000, 12000)], width=9500.0, vehicle="lb4", plates=False)
        self.assertEqual({c.item: c.status for c in short.checks}["荷下ろしの直線"], "要確認")
        prm = part_params(p)
        self.assertIn("中低床トレーラー", prm["rtVeh"])
        ro, ri = (int(x) for x in prm["aR"].split(","))
        self.assertTrue(ro > 12000 and 3000 < ri < 8000, (ro, ri))

    def test_pole_trailer_uses_catalog(self):
        p = route_plan("通路1", [(0, 0), (30000, 0), (30000, 25000)], vehicle="pt2", plates=False)
        cn = p.corners[0]
        self.assertAlmostEqual(cn.need, 10500.0)
        self.assertAlmostEqual(cn.ro, 16390.0)
        self.assertIn("所要道路幅", next(c.message for c in p.checks if c.item == "曲がり角 1"))

    def test_vehicle_keys(self):
        from ashiba.site_route import vehicle_keys

        ks = vehicle_keys()
        self.assertEqual(ks[:6], ["4t", "10t", "mixer", "mixer_m", "R25", "std"])
        self.assertIn("lb4", ks)
        self.assertIn("sl10", ks)


if __name__ == "__main__":
    unittest.main()
