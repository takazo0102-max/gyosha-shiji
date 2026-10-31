"""根切りの山留めまわり（利用者の指定 2026-10-31: 切張り上の足場を追加して 山留め上の手すり リサーチして追加して）."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.excavation import (BRACKET_PITCH_MAX_MM, kiribari_plan, part_params, rail_plan, report, stations)


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
