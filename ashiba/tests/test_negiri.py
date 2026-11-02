"""根切り図（利用者の指定 2026-11-02: 根切り図も作れるようにして 掘削のオブジェクト躯体選択して 掘削底深さと法面を選べるようにして
山留めまでの中途半ば部分は掘削するようにして）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.negiri import Footprint, Negiri, level_color, max_angle, mesh_data, report, solve

SLAB = Footprint("耐圧盤", [(0, 0), (12000, 0), (12000, 8000), (0, 8000)], -1200.0)
FOOT = Footprint("基礎F1", [(5000, 3000), (7000, 3000), (7000, 5000), (5000, 5000)], -2000.0)


class TestNegiri(unittest.TestCase):
    def test_slope_shape_and_volume(self):
        """耐圧盤（下端 −1200）と深い基礎（−2000）: 床付けは地業 110 を引いた 2段、法尻は余掘り 500、法肩は 1:0.5 で GL まで.
        土量は角錐台の手計算（≒ 182m³）と升目の誤差の内で合う."""
        n = solve(Negiri("試験", [SLAB, FOOT], slope=0.5))
        self.assertEqual(n.levels, [-1310.0, -2110.0])
        xs = [p[0] for p in n.top_rings[0]]
        self.assertAlmostEqual(min(xs), -500.0 - 655.0, delta=n.step)          # 余掘り 500＋深さ 1,310×0.5
        self.assertEqual(len(n.top_rings[0]), 4)                               # 角は尖る（凸の躯体は辺ごとの距離）
        self.assertAlmostEqual(n.volume, 182.0, delta=4.0)
        self.assertEqual(len(n.edge_rings[-1310.0]), 1)                        # 基礎の掘り込みの縁（下の段の法肩）
        self.assertIn("床付け GL", report(n).replace("| 床付け |", "床付け GL"))

    def test_fixed_depth_and_vertical_needs_yamadome(self):
        """掘削底を指定すると平ら。垂直で 1.5m を超えて山留めが無ければ NG（安衛則361条）."""
        n = solve(Negiri("試験", [SLAB, FOOT], slope=0.0, depth=-2000.0))
        self.assertEqual(n.levels, [-2000.0])
        st = {c.item: c.status for c in n.checks}
        self.assertEqual(st["山留め"], "NG")

    def test_yamadome_digs_the_leftover(self):
        """山留めの内側は山留めの面まで掘る（躯体の掘削と山留めの間の中途半端な所も一般の根切り底まで）。外は掘らない."""
        y = [(-1500, -1500), (13500, -1500), (13500, 9500), (-1500, 9500)]
        n = solve(Negiri("試験", [SLAB, FOOT], slope=0.0, yamadome=y))
        xs = [p[0] for p in n.top_rings[0]]
        self.assertAlmostEqual(min(xs), -1500.0, delta=n.step)                 # 山留めの面まで
        self.assertAlmostEqual(n.volume, 15.0 * 11.0 * 1.31 + 3.0 * 3.0 * 0.8, delta=6.0)
        m = mesh_data(n)
        self.assertEqual(len(m), 1)
        self.assertGreaterEqual(len(m[0]["sublines"]), 2)                      # 一般の根切り底と基礎の床付け

    def test_auto_slope_by_depth(self):
        """勾配の自動は積算基準（令和5年）の法の係数: 1.5m 未満は垂直、1.5〜5m は 1:0.3。砂は 1:1.5."""
        n = solve(Negiri("試験", [SLAB, FOOT]))
        self.assertEqual(sorted(n.slopes), [(1310.0, 0.0), (2110.0, 0.3)])
        st = {c.item: c.status for c in n.checks}
        self.assertNotIn("山留め", st)                                          # 1.5m 未満の垂直は山留め無しで可
        self.assertEqual((st["法面のこう配"], st["作業主任者"]), ("OK", "OK"))   # 2.11m は作業主任者（安衛法施行令6条9号）
        sand = solve(Negiri("試験", [SLAB, FOOT], soil="砂"))
        self.assertIn((2110.0, 1.5), sand.slopes)

    def test_narrow_strip_is_dug(self):
        """根切りと根切りの間に残る幅 1.1m 以下の地山は掘る（隣の浅い方の床付けまで）."""
        a = Footprint("基礎A", [(0, 0), (2000, 0), (2000, 2000), (0, 2000)], -1200.0)
        b = Footprint("基礎B", [(4000, 0), (6000, 0), (6000, 2000), (4000, 2000)], -1200.0)
        n = solve(Negiri("試験", [a, b], slope=0.0))                          # 余掘り 500 ずつで間 1,000 が残る
        self.assertGreater(n.strips, 0)
        self.assertEqual(len(n.top_rings), 1)                                  # 2つの根切りが1つにつながる
        far = solve(Negiri("試験", [a, Footprint("基礎C", [(5000, 0), (7000, 0), (7000, 2000), (5000, 2000)], -1200.0)],
                           slope=0.0))                                        # 間 2,000 は残す
        self.assertEqual((far.strips, len(far.top_rings)), (0, 2))

    def test_law_angles(self):
        """安衛則356条・357条の掘削面のこう配の上限."""
        self.assertEqual((max_angle("その他", 1500), max_angle("その他", 3000), max_angle("その他", 6000)), (90.0, 75.0, 60.0))
        self.assertEqual((max_angle("岩盤・堅い粘土", 4000), max_angle("岩盤・堅い粘土", 6000)), (90.0, 75.0))
        self.assertEqual((max_angle("砂", 4000), max_angle("砂", 6000)), (90.0, 35.0))
        n = solve(Negiri("試験", [SLAB, FOOT], slope=0.3, soil="その他"))       # 1:0.3 は 73°、2.1m は 75° まで
        self.assertEqual({c.item: c.status for c in n.checks}["法面のこう配"], "OK")
        n = solve(Negiri("試験", [SLAB, FOOT], slope=0.5, soil="砂"))           # 63° ＞ 35°（高さ 5m 未満は可）
        self.assertEqual({c.item: c.status for c in n.checks}["法面のこう配"], "OK")

    def test_gravel_and_lean_are_separate(self):
        """床付け＝下端−砕石−捨てコン（標仕 4.6.3・4.6.4 の 60・50 が既定）。地業の数量は出幅 0.1m の面積×厚さ（積算基準）."""
        n = solve(Negiri("試験", [SLAB], gravel=100.0, lean=50.0))
        self.assertEqual(n.levels, [-1350.0])
        a, v = n.ground["砕石"]
        self.assertAlmostEqual(a, 12.2 * 8.2, delta=1.5)                       # 出幅 0.1m（升目 50 の誤差の内）
        self.assertAlmostEqual(v, 12.2 * 8.2 * 0.10, delta=0.2)
        self.assertAlmostEqual(n.ground["捨てコン"][1], 12.2 * 8.2 * 0.05, delta=0.1)
        self.assertIn("| 砕石 |", report(n))
        self.assertEqual(solve(Negiri("試験", [SLAB])).levels, [-1310.0])     # 既定 60＋50

    def test_doma_margin_and_layers(self):
        """土間・犬走り等は余掘り 0.1m（積算基準）・捨てコン無し（既定）."""
        doma = Footprint("土間", [(0, 0), (6000, 0), (6000, 4000), (0, 4000)], -200.0, "土間")
        n = solve(Negiri("試験", [doma]))
        self.assertEqual(n.levels, [-260.0])                                   # 砕石 60 だけ
        xs = [p[0] for p in n.top_rings[0]]
        self.assertAlmostEqual(min(xs), -100.0, delta=n.step)
        self.assertNotIn("捨てコン", n.ground)
        self.assertIn("土間 100", {c.item: c.message for c in n.checks}["床付け"])

    def test_yamadome_gap(self):
        """山留め壁と躯体の間が 1.0m（積算基準の標準）より狭ければ知らせる。はみ出せば NG."""
        near = [(-500, -500), (12500, -500), (12500, 8500), (-500, 8500)]
        n = solve(Negiri("試験", [SLAB], slope=0.0, yamadome=near))
        gap = [c for c in n.checks if c.item == "山留めとの間"]
        self.assertEqual([c.status for c in gap], ["WARN"])
        self.assertIn("500mm", gap[0].message)
        far = [(-1000, -1000), (13000, -1000), (13000, 9000), (-1000, 9000)]
        self.assertFalse([c for c in solve(Negiri("試験", [SLAB], slope=0.0, yamadome=far)).checks if c.item == "山留めとの間"])
        cut = [(1000, -1000), (13000, -1000), (13000, 9000), (1000, 9000)]
        self.assertEqual([c.status for c in solve(Negiri("試験", [SLAB], slope=0.0, yamadome=cut)).checks
                          if c.item == "山留めとの間"], ["NG"])

    def test_level_colors(self):
        """床付けの高さごとに色を分ける（浅い順。白黒は灰の濃さで、深いほど濃い）."""
        n = solve(Negiri("試験", [SLAB, FOOT], slope=0.5))
        c0, c1 = (level_color(n, L) for L in n.levels)
        self.assertNotEqual(c0, c1)
        g0, g1 = (level_color(n, L, gray=True) for L in n.levels)
        self.assertGreater(g0[0], g1[0])


if __name__ == "__main__":
    unittest.main()
