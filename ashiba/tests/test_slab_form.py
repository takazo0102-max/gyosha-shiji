"""スラブの型枠と支保工（利用者の指定 2026-10-31: スラブの型枠も進めて しほこうも）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.beam_form import plan_beam
from ashiba.slab_form import (NEDA_D_MM, OBIKI_H_MM, PS_ALLOW_KN, PS_MAX_MM, SILL_H_MM, SILL_OUT_MM, TIE_PITCH_MM, _in_poly, choose_spacing, loads,
                              plan_slab, rect)


class TestSlabSpacing(unittest.TestCase):
    def test_detail_drawing_members(self):
        """スラブ・梁下の詳細図（利用者の指定 2026-10-31）: 根太 □50×50×2.3 @300・杉大引 90×90 @900."""
        s = choose_spacing(180)
        self.assertEqual(s.sv, 900.0)
        self.assertEqual([b.member for b in s.beams][1:], ["角パイプ □50×50×2.3", "杉大引 90×90"])
        self.assertEqual((NEDA_D_MM, OBIKI_H_MM), (50.0, 90.0))

    def test_loads_and_spacing(self):
        q, qd = loads(200)
        self.assertAlmostEqual(q, 24 * 0.2 + 0.4 + 1.5)
        self.assertAlmostEqual(qd, 24 * 0.2 + 0.4)
        for t in (150, 200, 250, 300):
            s = choose_spacing(t)
            self.assertTrue(s.ok, t)
            self.assertLessEqual(s.post_kn, PS_ALLOW_KN)
            self.assertTrue(all(b.ok for b in s.beams))
        self.assertGreaterEqual(choose_spacing(150).su * choose_spacing(150).sv,
                                choose_spacing(300).su * choose_spacing(300).sv)   # 厚いほど密


class TestSlabLayout(unittest.TestCase):
    def setUp(self):
        self.outline = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]
        self.beam = rect((4000.0, 3000.0), (1.0, 0.0), 4000.0, 200.0, 12.0)

    def test_posts_avoid_beams_and_stay_inside(self):
        f = plan_slab(self.outline, 180, 2820, 0, [self.beam])
        self.assertAlmostEqual(f.post_h, 2820 - 12 - NEDA_D_MM - OBIKI_H_MM - SILL_H_MM)   # 敷き桟木の上から
        self.assertTrue(f.posts)
        for u, v in f.posts:
            self.assertTrue(_in_poly((u, v), f.outer))
            self.assertFalse(abs(v - 3000.0) < 212.0 + 150.0)                  # 梁の下（とまわり 150）に立てない
        for v0, v1, u in f.neda:                                                # 根太は梁の所で切る
            self.assertFalse(v0 < 3000.0 < v1)
        self.assertEqual(f.ties, [])                                            # 3.5m 以下は水平つなぎなし
        self.assertAlmostEqual(f.area_m2(), 48.0 - 8.0 * 0.424, delta=0.5)

    def test_sills_under_each_post_row(self):
        """サポートしたはさんぎいる（利用者の指定 2026-10-31）: 支柱の列ごとに敷き桟木を通す."""
        f = plan_slab(self.outline, 180, 2820, 0, [self.beam])
        sills = f.sills()
        self.assertEqual(len(sills), len({round(v) for _u, v in f.posts}))
        for u0, u1, v in sills:
            us = [u for u, vv in f.posts if round(vv) == round(v)]
            self.assertAlmostEqual(u0, min(us) - SILL_OUT_MM)
            self.assertAlmostEqual(u1, max(us) + SILL_OUT_MM)

    def test_sills_split_where_posts_skip_a_beam(self):
        """さんぎの向き揃えて（利用者の指定 2026-10-31）: 梁で支柱が飛ぶ列は敷き桟木を分け、梁の下を通さない."""
        beam_v = rect((4000.0, 3000.0), (0.0, 1.0), 3000.0, 350.0, 12.0)        # 大引に直角な梁（x＝4000）
        f = plan_slab(self.outline, 180, 2820, 0, [beam_v])
        for u0, u1, _v in f.sills():
            self.assertFalse(u0 < 4000.0 < u1)
        self.assertGreater(len(f.sills()), len({round(v) for _u, v in f.posts}))
        self.assertIn("桟木 45×60（敷き桟木・4m）", {n for n, _k, _x in f.quantities()})

    def test_tall_shoring_gets_horizontal_ties(self):
        f = plan_slab(self.outline, 180, 5000, 0)
        self.assertGreater(f.post_h, PS_MAX_MM)
        self.assertEqual(f.ties, [TIE_PITCH_MM, 2 * TIE_PITCH_MM])              # 2m 以内ごと
        q = {n: k for n, k, _x in f.quantities()}
        self.assertEqual(q["パイプサポート"], len(f.posts))
        self.assertIn("単管（水平つなぎ・2方向）", q)

    def test_beam_supports(self):
        f = plan_beam(6000, 400, 700, 150)
        f.post_h = 2000.0
        q = {n: k for n, k, _x in f.quantities()}
        self.assertEqual(q["パイプサポート"], 2 * len(f.uke_x))
        f.sill_cross = True                                                      # スラブの敷き桟木と向きを揃える
        notes = {n: x for n, _k, x in f.quantities()}
        self.assertIn("梁に直角", notes["桟木 45×60（敷き桟木・4m）"])
        self.assertLessEqual(f.post_kn, PS_ALLOW_KN)


if __name__ == "__main__":
    unittest.main()
