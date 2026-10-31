"""仮囲い（利用者の指定 2026-11-01: 仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ）."""

from __future__ import annotations

import math
import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.hoarding import (PANEL_OFF_MM, Segment, hoarding_plan, inset_polygon, outside_is_right, part_params,
                             polyline_layout, rail_heights, PANELS, report, split_gates)

PENTAGON = [(-3000.0, -500.0), (12000.0, -500.0), (15000.0, 4000.0), (11000.0, 10000.0), (-3000.0, 10000.0)]


def q(p):
    return {n: k for n, k, _x in p.quantity}


def st(p):
    return {c.item: c.status for c in p.checks}


class TestStraight(unittest.TestCase):
    def test_three_metre_on_tankan(self):
        """3m の安全鋼板: 支柱 1.8m ごと・横地3段（パネルの上端・下端から 150）・有効幅 540・フックボルト 6・控えは支柱ごと."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (10800.0, 0.0)))
        self.assertEqual(p.posts, [0.0, 1800.0, 3600.0, 5400.0, 7200.0, 9000.0, 10800.0])
        self.assertEqual(p.rails, [350.0, 1700.0, 3050.0])
        self.assertEqual(p.top, 3200.0)
        self.assertEqual(q(p)["安全鋼板 t1.2 H3000"], 20)                    # 10800 / 540
        self.assertEqual(q(p)["フックボルト"], 120)
        self.assertEqual(q(p)["単管 5.0m（横地）"], 9)
        self.assertEqual(q(p)["直交クランプ（支柱・横地）"], 21)
        self.assertEqual(q(p)["単管 2.5m（控え）"], 7)                         # 1900 の高さから後ろ 1300（約 55°）
        self.assertEqual(q(p)["単管 1.5m（控えの杭）"], 14)
        self.assertEqual((st(p)["仮囲いの高さ"], st(p)["支柱の間隔"], st(p)["控えと風"]), ("OK", "OK", "OK"))

    def test_two_metre_two_rails(self):
        self.assertEqual(rail_heights(PANELS["安全鋼板"], 2000.0), [350.0, 2050.0])
        p = hoarding_plan("a", Segment((0.0, 0.0), (5000.0, 0.0)), height=2000.0)
        self.assertEqual(q(p)["フックボルト"], 4 * q(p)["安全鋼板 t1.2 H2000"])

    def test_flat_panel_adjust_and_low_fence(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (5230.0, 0.0)), panel="フラットパネル")
        self.assertEqual((q(p)["フラットパネル H3000"], q(p)["幅調整パネル（50〜480）"]), (10, 1))
        low = hoarding_plan("a", Segment((0.0, 0.0), (5000.0, 0.0)), height=1500.0)
        self.assertEqual(st(low)["仮囲いの高さ"], "NG")                         # 1.8m 以上（施行令 136条の2の20）

    def test_wind_and_brace_pitch(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (10800.0, 0.0)), brace_every=2)
        self.assertEqual(st(p)["控えと風"], "WARN")                             # @3600 は 15m/s まで
        self.assertEqual(len(p.braces), 4)

    def test_foundations(self):
        s = Segment((0.0, 0.0), (7200.0, 0.0))
        self.assertIn("根巻きコンクリート 150×150×500", q(hoarding_plan("a", s, foundation="根巻き")))
        h = hoarding_plan("a", s, foundation="H形鋼")
        self.assertEqual(h.brace_back, 1700.0)                                  # 後ろの列の H形鋼に落とす
        self.assertEqual(q(h)["キャッチクランプ（H形鋼用）"], (5 + 5) * 2)
        self.assertEqual(part_params(h)["kkFound"], 3)


class TestDiagonal(unittest.TestCase):
    def test_layout_shares_corner_posts_and_mitres(self):
        """斜めの辺: 区間ごとに向きを持ち、角の支柱は前の辺と共有、パネルは角の二等分線まで延ばす."""
        segs = polyline_layout(PENTAGON, closed=True, outside_right=outside_is_right(PENTAGON, (5000.0, 4000.0)))
        self.assertEqual(len(segs), 5)
        self.assertAlmostEqual(segs[1].angle, math.degrees(math.atan2(4500, 3000)))
        self.assertFalse(any(s.post0 for s in segs))                            # 閉じた形は角の支柱を前の辺が立てる
        self.assertAlmostEqual(segs[0].ext1, PANEL_OFF_MM * math.tan(math.radians(segs[0].turn1) / 2))
        self.assertAlmostEqual(segs[0].ext1, segs[1].ext0)
        p = hoarding_plan("b", segs[1])
        self.assertNotIn(0.0, p.posts)
        self.assertEqual(p.runs[0][0], -segs[1].ext0)
        self.assertIn("自在クランプ（斜めの角の横地）", q(p))

    def test_open_line_and_sharp_corner(self):
        segs = polyline_layout([(0.0, 0.0), (10000.0, 0.0), (2000.0, 3000.0)])
        self.assertTrue(segs[0].post0)
        self.assertFalse(segs[1].post0)
        self.assertEqual(st(hoarding_plan("a", segs[0]))["終わりの角"], "WARN")    # 内角 20° は自在コーナーで受けられない

    def test_outside_side(self):
        """敷地の中の点が左なら外（パネル）は右。逆なら点列を逆に回す."""
        self.assertTrue(outside_is_right([(0.0, 0.0), (10000.0, 0.0)], (5000.0, 3000.0)))
        self.assertFalse(outside_is_right([(0.0, 0.0), (10000.0, 0.0)], (5000.0, -3000.0)))
        segs = polyline_layout([(0.0, 0.0), (10000.0, 0.0)], outside_right=False)
        self.assertEqual(segs[0].p0, (10000.0, 0.0))

    def test_inset_boundary(self):
        out = inset_polygon([(0.0, 0.0), (10000.0, 0.0), (10000.0, 8000.0), (0.0, 8000.0)], 150.0)
        self.assertEqual([tuple(round(v) for v in p) for p in out], [(150, 150), (9850, 150), (9850, 7850), (150, 7850)])
        tri = inset_polygon([(0.0, 0.0), (10000.0, 0.0), (0.0, 10000.0)], 100.0)
        self.assertAlmostEqual(tri[0][0], 100.0)
        self.assertAlmostEqual(tri[1][0] + tri[1][1], 10000.0 - 100.0 * math.sqrt(2), places=3)   # 斜めの辺も平行に寄せる


class TestSlopeAndGates(unittest.TestCase):
    def test_ground_per_post(self):
        """敷地の高低差: 支柱ごとに地盤を読む（部品の postZ）、10% を超えれば WARN."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (9000.0, 0.0)), ground=lambda x, y: -0.07 * x)
        self.assertEqual(p.post_z[-1], -630.0)
        self.assertEqual(st(p)["地盤の高低差"], "OK")
        self.assertEqual(part_params(p)["postZ"].split(",")[-1], "-630")
        steep = hoarding_plan("a", Segment((0.0, 0.0), (9000.0, 0.0)), ground=lambda x, y: -0.15 * x)
        self.assertEqual(st(steep)["地盤の高低差"], "WARN")

    def test_gate_cuts_panels(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (15000.0, 0.0)), gates=[(4000.0, 3600.0, "キャスター")])
        self.assertEqual(p.runs, [(0.0, 4000.0), (7600.0, 15000.0)])
        self.assertIn(4000.0, p.posts)
        self.assertIn(7600.0, p.posts)
        self.assertFalse(any(4000.0 < x < 7600.0 for x in p.posts))
        self.assertEqual(st(p)["支柱の間隔"], "OK")                               # ゲートの間口は数えない
        self.assertEqual(st(p)["出入口"], "OK")
        prm = part_params(p)
        self.assertEqual((prm["gateX"], prm["gateK"]), ("4000,7600", "1"))
        self.assertNotIn("5800", prm["brX"].split(","))

    def test_split_gates_along_polyline(self):
        segs = polyline_layout([(0.0, 0.0), (10000.0, 0.0), (10000.0, 8000.0)])
        self.assertEqual(split_gates(segs, [(12000.0, 900.0, "ドア")]), [[], [(2000.0, 900.0, "ドア")]])

    def test_report(self):
        md = report([hoarding_plan("a", Segment((0.0, 0.0), (5000.0, 0.0))), hoarding_plan("b", Segment((0.0, 0.0), (3000.0, 0.0)))])
        for w in ("# 仮囲い", "136条の2の20", "合計", "ミルックス"):
            self.assertIn(w, md)


class TestRunScript(unittest.TestCase):
    def test_chains_join_loose_lines(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from kakoi_run import _gate, chains

        g = [({"elementId": {"guid": "a"}}, [((0.0, 0.0), (5000.0, 0.0))]),
             ({"elementId": {"guid": "b"}}, [((5000.0, 0.0), (8000.0, 4000.0))])]       # 斜めの線をつなぐ
        out = chains(g)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], [(0.0, 0.0), (5000.0, 0.0), (8000.0, 4000.0)])
        self.assertEqual(_gate("4000:3600:ジャバラ"), (4000.0, 3600.0, "ジャバラ"))


if __name__ == "__main__":
    unittest.main()
