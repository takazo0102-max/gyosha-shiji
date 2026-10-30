"""足場の箱（超簡易モード。利用者の指定 2026-10-30: 箱を作って自分で伸び縮み・一周の箱・ボタンで本体にする）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.box import box_coins, box_loop, box_params, parse_box_params, snap_spans, thickness_conditions
from ashiba.manual import solve_manual_loop

INCH = [1829, 1524, 1219, 914, 610]


class TestSnap(unittest.TestCase):
    def test_snaps_to_standard_lengths(self):
        """つまみで引いた長さ → 定尺の最大を並べて端数を定尺で埋める（部品のパラメータスクリプトと同じ決め方）."""
        self.assertEqual(snap_spans(7316, INCH), [1829] * 4)
        self.assertEqual(snap_spans(8000, INCH), [1829] * 4 + [610])      # 7926（8000 に一番近い）
        self.assertEqual(snap_spans(8230, INCH), [1829] * 4 + [914])
        self.assertEqual(snap_spans(300, INCH), [610])                     # 短すぎても1本は残る
        self.assertEqual(snap_spans(9000, [1800, 1500, 1200, 900, 600]), [1800] * 5)

    def test_no_adjusting_457(self):
        """アルバトロスの 457 は端数の調整用（先行手摺・シートが合わない）。箱の吸着には使わない（利用者が引いて 1524＋457 になった）."""
        from ashiba.master import load_master

        coins = box_coins(load_master("albatross").span_lengths())
        self.assertNotIn(457, coins)
        self.assertNotIn(457, snap_spans(11126, coins))


class TestBoxLoop(unittest.TestCase):
    def test_rotations(self):
        pts, sides = box_loop((1000.0, 2000.0), 0.0, [1829, 1829], [914])
        self.assertEqual(pts, [(1000.0, 2000.0), (4658.0, 2000.0), (4658.0, 2914.0), (1000.0, 2914.0)])
        self.assertEqual(sides, [[1829, 1829], [914], [1829, 1829], [914]])
        pts, _ = box_loop((0.0, 0.0), math.pi / 2, [1829], [914])
        self.assertEqual([tuple(round(v) for v in p) for p in pts], [(0, 0), (0, 1829), (-914, 1829), (-914, 0)])
        with self.assertRaisesRegex(ValueError, "斜め"):
            box_loop((0.0, 0.0), math.radians(30), [1829], [914])

    def test_params_round_trip_and_solve(self):
        p = box_params([1829] * 4, [1829] * 3, INCH, 900.0, 4, 1780.0, 1800.0, "albatross", 300.0)
        self.assertEqual((p["spanX"], p["lenX"], p["topEdit"], p["thick"]), ("1829,1829,1829,1829", 7.316, 7.18, 0.9))
        b = parse_box_params({**p, "nLev": 4})
        self.assertEqual((b["sx"], b["sy"], b["levels"], b["thick_mm"]), ([1829] * 4, [1829] * 3, 4, 900))
        pts, sides = box_loop((0.0, 0.0), 0.0, b["sx"], b["sy"])
        _w, _spec, r = solve_manual_loop(pts, sides, b["standoff"], 7000.0, {"series_id": "albatross"})
        self.assertTrue(r.verdict["ok"], r.verdict)
        self.assertEqual([list(e.spans) for e in r.model.plan.edges],
                         [[1829] * 4, [1829] * 3, [1829] * 4, [1829] * 3])

    def test_thickness_picks_the_scaffold(self):
        """厚みで足場の種類も変える（利用者の指定 2026-10-30）: 300＝一側足場、600／900／1200＝幅 610／914／1219 の本足場."""
        pts, sides = box_loop((0.0, 0.0), 0.0, [1829] * 4, [1829] * 3)
        got = {}
        for t in (280, 600, 950, 1200):
            kind, cond = thickness_conditions(t, 300.0)
            _w, _spec, r = solve_manual_loop(pts, sides, 300.0, 6000.0, {"series_id": "albatross", **cond})
            self.assertTrue(r.verdict["ok"], (kind, r.verdict))
            got[kind] = (r.model.config.scaffold_form, round(r.model.post_row_spacing_mm))
        self.assertEqual(got["本足場 幅600"], ("本足場", 610))
        self.assertEqual(got["本足場 幅900"], ("本足場", 914))
        self.assertEqual(got["本足場 幅1200"], ("本足場", 1219))
        self.assertEqual(got["一側足場"][0], "一側足場")

if __name__ == "__main__":
    unittest.main()
