"""別の足場を単管でつなぐ（GLOOBE の「別の足場と接続する単管」。2026-11-02 の開発ループ）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.master import load_master
from ashiba.tube_join import (Join, columns_on, corner_angle, part_params, pick_tie, pick_tube, plan_join, report, tie_spots,
                              tube_capacity_kn)


class TestTubeJoin(unittest.TestCase):
    def test_tube_length_and_order(self):
        """支柱の間 2,900 は突き出し 50 ずつ足して 3.0M、3段に単管3本と直交クランプ6個（日建 Vol.10 p372・p378）."""
        self.assertEqual((pick_tube(3000.0), pick_tube(3001.0), pick_tube(6200.0)), (3000, 3500, 0))
        j = plan_join(Join("つなぎ1", (0.0, 0.0), (2900.0, 0.0), [1800.0, 3600.0, 5400.0]))
        self.assertEqual(j.tube, 3000)
        q = {a: n for a, n, _u in j.quantity}
        self.assertEqual((q["単管 3.0M（つなぎ・手すり）"], q["ARC1 兼用直交クランプ"]), (3, 6))
        self.assertEqual(part_params(j)["zList"], "1800,3600,5400")
        self.assertIn("ARC1", report([j]))

    def test_guard_brace_and_limits(self):
        """手すり・中桟で1層3本、層の間の斜めは自在クランプ。6m を超える間は単管が届かない."""
        j = plan_join(Join("つなぎ2", (0.0, 0.0), (1500.0, 0.0), [1800.0, 3600.0], guard=True, brace=True))
        self.assertEqual(j.rows, [1800.0, 2250.0, 2750.0, 3600.0, 4050.0, 4550.0])
        q = {a: n for a, n, _u in j.quantity}
        self.assertEqual((q["単管 1.8M（つなぎ・手すり）"], q["単管 2.5M（斜めの補強）"], q["ARC2 兼用自在クランプ"]), (6, 1, 2))
        far = plan_join(Join("つなぎ3", (0.0, 0.0), (6500.0, 0.0), [1800.0]))
        self.assertEqual(({c.item: c.status for c in far.checks}["長さ"], far.quantity), ("NG", []))


class TestHiuchiAndTubeTie(unittest.TestCase):
    """GLOOBE 2026 の火打ち・壁つなぎの単管配置に当たるもの（利用者の指定 2026-11-02「全部入れて 進めて」）."""

    def test_hiuchi(self):
        """隅の支柱から両側 1800 の支柱を斜めに結ぶ: 2,546 に単管 2.7M・両端 ARC1。一直線の3点は NG."""
        j = plan_join(Join("火打ち1", (1800, 0), (0, 1800), [1800, 3600], kind="火打ち", corner=(0, 0)))
        self.assertAlmostEqual(corner_angle(j), 90.0)
        self.assertEqual(j.tube, 2700)
        self.assertEqual({c.item: c.status for c in j.checks}["火打ち"], "OK")
        self.assertIn(("単管 2.7M（火打ち）", 2, "本（7.61kg）"), j.quantity)
        lop = plan_join(Join("火打ち2", (3600, 0), (0, 900), [1800], kind="火打ち", corner=(0, 0)))
        self.assertEqual({c.item: c.status for c in lop.checks}["火打ち"], "WARN")                    # 片側が4倍
        flat = plan_join(Join("火打ち3", (1800, 0), (-1800, 0), [1800], kind="火打ち", corner=(0, 0)))
        self.assertEqual({c.item: c.status for c in flat.checks}["火打ち"], "NG")

    def test_tube_capacity(self):
        """単純梁の中央: P = 4·fb·Z/L = 4×23,520×3.83/180 ≒ 2.00kN。支柱に寄るほど大きく、2本で倍."""
        self.assertAlmostEqual(tube_capacity_kn(1800, 900), 4 * 23520 * 3.83 / 180 / 1000, places=3)
        self.assertGreater(tube_capacity_kn(1800, 300), tube_capacity_kn(1800, 900))
        self.assertAlmostEqual(tube_capacity_kn(1800, 900, True), 2 * tube_capacity_kn(1800, 900))

    def test_tie_on_tube(self):
        """柱（□300、芯が線から 450 の左）が支柱の間に来れば、柱の面まで 300 の壁つなぎ（日建 KS400: 250〜420）を層ごとに."""
        j = Join("壁つなぎ1", (0, 0), (1800, 0), [1800, 3600], kind="壁つなぎ")
        j.ties = columns_on(j, [((900.0, 450.0), 150.0), ((2500.0, 450.0), 150.0), ((900.0, -4000.0), 150.0)])
        self.assertEqual(j.ties, [(900.0, 1, 300.0)])                               # 支柱の間の外・遠い柱は取らない
        m = load_master("nikken_nd1800")
        j.tie_parts = [pick_tie(m, need) for _x, _s, need in j.ties]
        self.assertEqual(j.tie_parts, ["KS400"])
        plan_join(j)
        st = [c.status for c in j.checks if c.item == "壁つなぎ"]
        self.assertEqual(st, ["WARN"])                                               # 2.00kN ＜ 4.41kN
        self.assertIn(("壁つなぎ KS400（単管から柱へ）", 2, "本"), j.quantity)
        sp = tie_spots(j)[0]
        self.assertEqual((sp["x"], sp["y"], sp["faceAng"], sp["tieL"]), (900.0, 0.0, 0.0, 300.0))   # +Y が柱の側
        right = Join("右", (1800, 0), (0, 0), [1800], kind="壁つなぎ")
        right.ties = columns_on(right, [((900.0, 450.0), 150.0)])
        self.assertEqual(tie_spots(right)[0]["faceAng"] % 360.0, 0.0)               # 線が逆向きなら柱は右 → 180° 回す
        two = plan_join(Join("2本", (0, 0), (1800, 0), [1800], kind="壁つなぎ", double=True, ties=[(400.0, 1, 300.0)]))
        self.assertEqual([c.status for c in two.checks if c.item == "壁つなぎ"], ["OK"])
        self.assertEqual(part_params(two)["zList"], "1800,1900")                    # 2本目は上に
        self.assertIn("# 単管に壁つなぎ", report([j]))


if __name__ == "__main__":
    unittest.main()
