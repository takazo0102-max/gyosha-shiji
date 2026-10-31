"""梁の型枠（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置する
ようにして）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.beam_form import beam_extents, beam_from_details, plan_beam, slab_over
from ashiba.column_form import column_rect
from ashiba.slab_heights import SlabInfo
from ashiba.wall_form import BAND_MM, TUBE_OFF_MM


def _beam(L=6000.0, w=400.0, h=700.0):
    return {"ca": (0.0, 0.0), "cb": (L, 0.0), "u": (1.0, 0.0), "length": L, "width": w, "depth": h, "top": 3000.0,
            "bottom": 3000.0 - h, "ang": 0.0}


class TestBeamForm(unittest.TestCase):
    def test_plan_passes(self):
        for w, h in ((300, 600), (400, 700), (700, 700), (500, 1200)):
            with self.subTest(w=w, h=h):
                f = plan_beam(6000, w, h, 150)
                self.assertTrue(f.ok)
                self.assertTrue(all(b - a <= f.uke_pitch + 1e-6 for a, b in zip(f.uke_x, f.uke_x[1:])))
                self.assertAlmostEqual(f.side_hs[0], h - 150 + 12)                  # 底板の下面からスラブの下端まで

    def test_wide_beam_gets_more_bottom_battens(self):
        self.assertEqual(len(plan_beam(6000, 400, 700).bot_y), 3)
        self.assertEqual(len(plan_beam(6000, 700, 700).bot_y), 4)               # 合板が通るまで増やす

    def test_edge_beam_sides_differ(self):
        f = plan_beam(6000, 400, 700, (0.0, 150.0))
        self.assertEqual(f.side_hs, (712.0, 562.0))
        self.assertTrue(all(z < 562.0 - 30.0 for z in f.tie_z))                 # フォームタイは両側の側板がある段だけ
        q = {n: k for n, k, _x in f.quantities()}
        self.assertEqual(q["フォームタイ（梁幅 400）"], len(f.tie_x) * len(f.tie_z))

    def test_slab_over_and_column_end(self):
        bm = _beam()
        slab = SlabInfo([(-1000.0, 0.0), (7000.0, 0.0), (7000.0, 5000.0), (-1000.0, 5000.0)], 3000.0, 150.0)
        self.assertEqual(slab_over(bm, [slab]), (0.0, 150.0))                    # +Y の側だけスラブ（外周の梁）
        col = column_rect({"c": (6000.0, 0.0), "width": 800.0, "depth": 800.0, "ang": 0.0})
        ex = beam_extents(bm, [col])
        self.assertEqual(ex["ext"], (0.0, 5600.0))                               # 柱の面まで
        self.assertAlmostEqual(ex["tubes"][1], 5600.0 - TUBE_OFF_MM)
        self.assertAlmostEqual(ex["sangi"][1], 5600.0 - BAND_MM)
        self.assertEqual(ex["ends"], (True, False))                              # 柱の側は止め型枠なし

    def test_details(self):
        d = {"details": {"begCoordinate": {"x": 0, "y": 0}, "endCoordinate": {"x": 0, "y": 6}, "width": 0.4, "height": 0.7,
                         "zCoordinate": 3.0, "anchorPoint": "TopCenter", "beamShape": "Straight"}}
        bm = beam_from_details(d)
        self.assertEqual((bm["width"], bm["depth"], bm["bottom"], round(bm["ang"])), (400.0, 700.0, 2300.0, 90))


if __name__ == "__main__":
    unittest.main()
