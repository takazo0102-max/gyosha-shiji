"""根切りの山留めまわり（利用者の指定 2026-10-31: 切張り上の足場を追加して 山留め上の手すり リサーチして追加して）."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.excavation import (BRACKET_PITCH_MAX_MM, haraokoshi_plan, kiribari_plan, part_params, perimeter_layout,
                                rail_plan, report, stations, strut_insets)


class TestKiribari(unittest.TestCase):
    def test_brackets_within_2m(self):
        """切梁ブラケット（西南機材）: 取付間隔 2m 以内、端は 150."""
        p = kiribari_plan("切梁1", 6700.0, 300.0)
        self.assertEqual(p.xs[0], 150.0)
        self.assertAlmostEqual(p.xs[-1], 6550.0)
        self.assertTrue(all(b - a <= BRACKET_PITCH_MAX_MM for a, b in zip(p.xs, p.xs[1:])))
        st = {c.item: c.status for c in p.checks}
        self.assertEqual((st["切梁のフランジ"], st["作業床"], st["手すり・中桟"], st["幅木"]), ("OK", "OK", "OK", "OK"))
        self.assertEqual(st["切梁の荷重"], "WARN")                          # 山留めの設計者に確かめる
        q = {n: k for n, k, _x in p.quantity}
        self.assertEqual(q["切梁ブラケット"], len(p.xs))
        self.assertEqual(q["伸縮手摺柱 H875〜1275"], 2 * len(p.xs))

    def test_flange_out_of_range(self):
        """H形鋼 250〜400 の外は製品の対応外."""
        self.assertEqual({c.item: c.status for c in kiribari_plan("切梁", 6000.0, 200.0).checks}["切梁のフランジ"], "NG")
        self.assertFalse(kiribari_plan("切梁", 6000.0, 450.0).ok)

    def test_params(self):
        p = kiribari_plan("切梁1", 6700.0, 300.0)
        prm = part_params(p, 300.0)
        self.assertEqual((prm["ymKind"], prm["flgW"], prm["postSp"]), (1, 0.3, 0.9))
        self.assertEqual(prm["brX"].split(",")[0], "150")


class TestHaraokoshi(unittest.TestCase):
    def test_wale_walkway(self):
        """外周の腹起し上の足場（利用者の指定 2026-10-31: 外周の切張の足場も作って 組み方はリサーチしてね）: 西南機材 腹起ブラケット
        （H形鋼 250〜500・2m 以内・腕 900）に足場板3枚、根切りの側だけ手すり。通路まで 1.5m を超えれば昇降設備."""
        p = haraokoshi_plan("山留め1", 10000.0, 300.0, depth_mm=1500.0 + 1.0)
        self.assertTrue(all(b - a <= BRACKET_PITCH_MAX_MM for a, b in zip(p.xs, p.xs[1:])))
        st = {c.item: c.status for c in p.checks}
        self.assertEqual((st["腹起し"], st["作業床"], st["手すり・中桟"], st["ブラケットの数"]), ("OK", "OK", "OK", "OK"))
        self.assertEqual(st["昇降設備"], "WARN")
        self.assertEqual(st["腹起しの荷重"], "WARN")
        q = {n: k for n, k, _x in p.quantity}
        self.assertEqual(q["腹起ブラケット"], len(p.xs))
        self.assertEqual(q["足場板 240×4000"] % 3, 0)                      # 3枚並べ
        self.assertEqual(part_params(p, 300.0)["ymKind"], 3)
        self.assertEqual({c.item: c.status for c in haraokoshi_plan("山留め", 6000.0, 600.0).checks}["腹起し"], "NG")


class TestJunctions(unittest.TestCase):
    """角の重なりと切梁との取り合い（利用者の指定 2026-10-31: 角の重なりと切梁との取り合いも直して）."""

    def setUp(self):
        pts = [(0.0, 7000.0), (10000.0, 7000.0), (10000.0, 0.0), (0.0, 0.0)]          # 根切りの中が右（時計回り）
        self.lines = list(zip(pts, pts[1:] + pts[:1]))
        self.ends = [(3500.0, 150.0), (3500.0, 6850.0)]

    def test_corners_do_not_overlap(self):
        lay = perimeter_layout(self.lines, [300.0] * 4, self.ends)
        top = lay[0]
        self.assertEqual(top["origin"], (1050.0, 6850.0))                 # 前の辺の床（面から 900）の縁から
        self.assertEqual(top["length"], 8800.0)                           # 次の辺の山留めの面まで（角はこの辺）
        self.assertEqual(top["rail"], (0.0, 7900.0))                      # 手すりは内側の角で止めて折る
        right = lay[1]
        self.assertEqual(right["origin"], (9850.0, 5950.0))               # 上の辺の床の縁から始まる
        # 隣どうしの床が重ならない: 上の辺の床は y 5950〜6850、右の辺の床は y 5950 から下
        self.assertLessEqual(right["origin"][1], top["origin"][1] - 900.0)

    def test_rail_opens_for_strut_walkway(self):
        lay = perimeter_layout(self.lines, [300.0] * 4, self.ends)
        self.assertEqual(lay[0]["gaps"], [(1950.0, 2950.0)])             # 切梁の芯 3500 の ±500
        self.assertEqual(lay[1]["gaps"], [])
        p = haraokoshi_plan("山留め1", lay[0]["length"], 300.0)
        p.rail, p.gaps = lay[0]["rail"], lay[0]["gaps"]
        prm = part_params(p, 300.0)
        self.assertEqual((prm["railX1"], prm["railGap"]), (7.9, "1950,2950"))

    def test_strut_walkway_stops_at_perimeter_edge(self):
        d0, d1 = strut_insets((3500.0, 150.0), (3500.0, 6850.0), self.lines, [300.0] * 4)
        self.assertEqual((d0, d1), (900.0, 900.0))
        p = kiribari_plan("切梁1", 6700.0, 300.0, deck0=d0, deck1=d1, step_mm=227.0)
        self.assertEqual(p.rail, (900.0, 5800.0))
        self.assertGreaterEqual(p.xs[0], 1000.0)
        self.assertEqual({c.item: c.status for c in p.checks}["外周の足場との取り合い"], "WARN")   # 段差 227


class TestRail(unittest.TestCase):
    def test_posts_and_checks(self):
        """山留め上の手すり: 柱 1.8m 以内、手すり 85cm 以上・中桟・幅木、根切り 2m 以上は安衛則 519条."""
        p = rail_plan("山留め1", 10000.0, depth_mm=6000.0)
        self.assertEqual(len(p.xs), 7)
        self.assertTrue(all(b - a <= 1800.0 + 1e-6 for a, b in zip(p.xs, p.xs[1:])))
        st = {c.item: (c.status, c.message) for c in p.checks}
        self.assertIn("519条", st["根切りの縁"][1])
        q = {n: k for n, k, _x in p.quantity}
        self.assertEqual(q["キャッチクランプ（H形鋼用）"], 2 * len(p.xs))       # 2個1組
        self.assertEqual(part_params(p)["ymKind"], 2)

    def test_net(self):
        """山留め上の手すりはネット（利用者の指定 2026-10-31: 山留め上の手すりはネットいるよ）: ラッセルネット 目合15 を
        地盤から手すりの上まで、手すり・中桟・幅木に結束."""
        p = rail_plan("山留め1", 10000.0, depth_mm=6000.0)
        q = {n: (k, x) for n, k, x in p.quantity}
        net = next(n for n in q if n.startswith("ラッセルネット"))
        self.assertEqual(q[net][0], 10)                                        # 10m × 0.95m → 10m²
        self.assertEqual(q["結束バンド（ネット）"][0], 3 * (23 + 1))           # 3段 × @450
        self.assertEqual({c.item: c.status for c in p.checks}["ネット"], "OK")
        self.assertIs(part_params(p)["netOn"], True)                          # 部品の Boolean には真偽値で渡す
        off = rail_plan("山留め1", 10000.0, net=False)
        self.assertEqual({c.item: c.status for c in off.checks}["ネット"], "WARN")
        self.assertFalse(any(n.startswith("ラッセルネット") for n, _k, _x in off.quantity))

    def test_stations(self):
        self.assertEqual(stations(3600.0, 1800.0, 0.0), [0.0, 1800.0, 3600.0])
        self.assertEqual(len(stations(3700.0, 1800.0, 0.0)), 4)

    def test_report(self):
        md = report([kiribari_plan("切梁1", 6700.0, 300.0), rail_plan("山留め1", 7000.0)])
        for w in ("切梁上の足場 切梁1", "山留め上の手すり 山留め1", "seinankizai", "519条"):
            self.assertIn(w, md)


class TestRailLines(unittest.TestCase):
    def test_ground_side_on_the_left(self):
        """手すりの線は地山（根切りの外）が左になる向き."""
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from excav_run import rail_lines

        def wall(a, b):
            ux, uy = b[0] - a[0], b[1] - a[1]
            L = (ux * ux + uy * uy) ** 0.5
            return {"ca": a, "cb": b, "n": (-uy / L, ux / L), "lo": -150.0, "hi": 150.0, "z0": -6000.0, "height": 6000.0}

        pts = [(0.0, 0.0), (10000.0, 0.0), (10000.0, 7000.0), (0.0, 7000.0)]
        lines = rail_lines([wall(a, b) for a, b in zip(pts, pts[1:] + pts[:1])])
        for a, b, z, _n in lines:
            side = (b[0] - a[0]) * (3500.0 - a[1]) - (b[1] - a[1]) * (5000.0 - a[0])
            self.assertLess(side, 0)                                        # 根切りの中は右
            self.assertEqual(z, 0.0)                                        # 天端


if __name__ == "__main__":
    unittest.main()
