"""スラブの型枠と支保工（利用者の指定 2026-10-31: スラブの型枠も進めて しほこうも）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.beam_form import plan_beam
from ashiba.slab_form import (NEDA_D_MM, OBIKI_H_MM, PS_FREE_MAX_MM, PS_MAX_MM, PS_TIED_KN, SILL_H_MM, SILL_OUT_MM, TIE_PITCH_MM, _in_poly, choose_spacing, loads,
                              plan_slab, ps_allow_kn, ps_condition, ps_model, rect)


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
            self.assertLessEqual(s.post_kn, PS_TIED_KN)
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
        self.assertLessEqual(f.post_kn, PS_TIED_KN)

    def test_beam_pitch_fits_the_maker_allowance(self):
        """梁下の大引の間隔は、支柱1本がメーカーの許容支持力（使用高さ 3〜3.4m・連係なしは 9.8kN）に入るまで詰める."""
        for w, d in ((400, 700), (600, 900), (800, 1000), (1000, 1200)):
            f = plan_beam(6000, w, d, 150, post_h_mm=3300.0)
            self.assertEqual(f.ps_allow, 9.8)
            self.assertLessEqual(f.post_kn, 9.8, (w, d))
            self.assertLessEqual(f.uke_pitch, plan_beam(6000, w, d, 150).uke_pitch)
        self.assertIn("連係なし・使用高さ 3〜3.4m", "\n".join(f.lines()))
        self.assertEqual(plan_beam(6000, 600, 900, 150, post_h_mm=3600.0).ps_allow, 19.6)   # 3.4m 超は水平つなぎで連係あり


class TestBraces(unittest.TestCase):
    """大筋かい（利用者の指定 2026-10-31: 筋かいも足して）: 水平荷重 5% を自在クランプ 3.43kN×cosθ の単管で受ける."""

    def test_enough_braces_each_way(self):
        outline = [(0.0, 0.0), (6000.0, 0.0), (6000.0, 5600.0), (0.0, 5600.0)]
        f = plan_slab(outline, 180, 2820, 0)
        for d in ("u", "v"):
            bi = f.brace_info[d]
            self.assertAlmostEqual(bi["H"], 0.05 * f.q * bi["area"])
            self.assertGreaterEqual(bi["have"], bi["need"])
            self.assertEqual(bi["have"] % 2, 0)                              # X（2本）で入れる
        self.assertTrue(any("大筋かい（大引の向き）" in ln and "可" in ln for ln in f.lines()))
        names = {n for n, _k, _x in f.quantities()}
        self.assertIn("自在クランプ（大筋かい）", names)
        self.assertTrue(any(n.startswith("単管") and "大筋かい" in n for n in names))
        u0, v0, z0, u1, v1, z1 = f.braces[0]
        self.assertEqual(z0, 200.0)                                          # 根がらみの高さから
        self.assertAlmostEqual(max(z0, z1), 45.0 + f.post_h - 150.0)         # 支柱の天端の 150 下まで

    def test_heavier_slab_needs_more(self):
        outline = [(0.0, 0.0), (9000.0, 0.0), (9000.0, 7200.0), (0.0, 7200.0)]
        thin, thick = plan_slab(outline, 150, 2820, 0), plan_slab(outline, 400, 2820, 0)
        self.assertGreater(thick.brace_info["u"]["need"], thin.brace_info["u"]["need"])


class TestMakerTable(unittest.TestCase):
    """パイプサポートの許容支持力（利用者の指定 2026-10-31: パイプサポートの許容荷重はメーカー表に合わせて）.
    岡部 フラワーサポート／パイプサポート（仮設工業会認定品）のカタログの表."""

    def test_allowance_by_height(self):
        self.assertEqual([ps_allow_kn(h) for h in (1900, 2000, 2400, 2900, 3300)], [19.6, 19.6, 17.6, 13.7, 9.8])
        self.assertEqual(ps_allow_kn(2900, lower="concrete"), 16.6)          # 下端 仕上げコンクリート
        self.assertEqual(ps_allow_kn(3450), 0.0)                             # 連係なしの表は 3.4m まで
        self.assertEqual(ps_allow_kn(4500, tied=True), 19.6)                 # 連係ありは高さに関係なく
        self.assertEqual(ps_condition(2623, False), "連係なし・使用高さ 2.5〜3m・上下端 木材")

    def test_model_by_length(self):
        self.assertEqual(ps_model(2103), "50S")
        self.assertEqual(ps_model(2623), "60S")
        self.assertEqual(ps_model(3300), "75S")
        self.assertEqual(ps_model(3800), "90S")
        self.assertEqual(ps_model(4800), "90S＋補助サポート 4S")    # 継ぐのは2本まで

    def test_spacing_uses_the_allowance(self):
        """長い支柱ほど許容支持力が下がり、支柱の間隔が詰まる. 3.4m を超えると水平つなぎを設けて 19.6kN."""
        outline = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]
        low = plan_slab(outline, 450, 2300, 0)                               # 支柱 2103（17.6kN）
        mid = plan_slab(outline, 450, 3400, 0)                               # 支柱 3203（9.8kN）
        self.assertEqual((low.spacing.allow_kn, mid.spacing.allow_kn), (17.6, 9.8))
        self.assertLessEqual(mid.spacing.post_kn, 9.8)
        self.assertLess(mid.spacing.su * mid.spacing.sv, low.spacing.su * low.spacing.sv)
        tall = plan_slab(outline, 250, 3650, 0)                              # 支柱 3453（3.4m 超）
        self.assertGreater(tall.post_h, PS_FREE_MAX_MM)
        self.assertTrue(tall.ties)
        self.assertEqual(tall.spacing.allow_kn, PS_TIED_KN)


if __name__ == "__main__":
    unittest.main()
