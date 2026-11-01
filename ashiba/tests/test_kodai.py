"""乗入れ構台・荷取り構台（開発ループ 2026-11-01: 他に必要な仮設材の2番）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.kodai import SEC_CODE, _fc, deck_rows, grid, kodai_plan, layout, part_params, plan_from_params, snap, tie_levels


class TestLayout(unittest.TestCase):
    def test_aij_example_grid(self):
        """AIJ の設計例（幅員 8m・支柱 6×6m・張出し 1m）: 幅 8m は支柱2列、根太は覆工板 2m ごとに5通り."""
        p = layout("a", 30000.0, 8000.0, top=500.0, depth=6300.0, embed=4700.0)
        self.assertEqual(p.ys, [1000.0, 7000.0])
        self.assertEqual(len(p.xs), 6)                                   # 28m を 6m 以内で5等分
        self.assertAlmostEqual(p.xs[1] - p.xs[0], 5600.0)
        self.assertEqual(p.joists, [0.0, 2000.0, 4000.0, 6000.0, 8000.0])
        self.assertAlmostEqual(p.post_top, 208.0 + 400.0 + 400.0)        # 覆工板＋根太＋大引の下
        self.assertAlmostEqual(p.post_len, 500.0 + 6300.0 + 4700.0 - 1008.0)

    def test_deck_rows_mix_one_3m(self):
        """覆工板は 2m が基本で、幅を合わせるのに 3m を1列（利用者の指定 2026-11-01: ふっこう板は3mと2mあるので切り替えれる
        ように → 全部が 3m じゃないよ 1列だけだよね）."""
        self.assertEqual(deck_rows(8000.0), [2000.0] * 4)                       # 偶数 m は 2m だけ
        self.assertEqual(deck_rows(7000.0), [3000.0, 2000.0, 2000.0])           # 奇数 m は 3m を1列（手前）
        self.assertEqual(deck_rows(6500.0), [3000.0, 2000.0, 2000.0])           # 1m に切り上げて 7m
        self.assertEqual(deck_rows(8000.0, 1), [3000.0, 2000.0, 2000.0, 2000.0])  # 3m を1列と決めると 9m
        self.assertEqual(deck_rows(7000.0, 1, 3), [2000.0, 2000.0, 3000.0])      # 3m を奥に
        self.assertEqual(deck_rows(8000.0, 0), [2000.0] * 4)
        p = kodai_plan("g", 18000.0, 7000.0)
        self.assertEqual((p.width, p.joists), (7000.0, [0.0, 3000.0, 5000.0, 7000.0]))
        q = {a: (n, c) for a, n, c in p.quantity}
        self.assertEqual((q["覆工板 1×2m（高さ 208）"][0], q["覆工板 1×3m（高さ 208）"][0]), (18 * 2, 18))
        self.assertIn("624kg", q["覆工板 1×3m（高さ 208）"][1])
        self.assertEqual((part_params(p)["dk3"], part_params(p)["dk3At"]), (-1, 1))      # 自動のまま（広げても合わせる）
        self.assertEqual(part_params(kodai_plan("i", 18000.0, 8000.0, n3=1))["dk3"], 1)
        self.assertIn("支間 2.9m", next(c.message for c in p.checks if c.item == "覆工板"))
        self.assertEqual(kodai_plan("h", 18000.0, 8000.0).n3, 0)

    def test_snap_and_levels(self):
        self.assertEqual(snap(7300.0, 2000.0), 8000.0)
        self.assertEqual(snap(8030.0, 2000.0), 8000.0)                   # 1枚の 2% までのはみ出しは切り下げ
        self.assertEqual(grid(8000.0, 1000.0, 6000.0), [1000.0, 7000.0])
        lv = tie_levels(1008.0, 6800.0)                                  # 根切り底の 300 上まで 3m 以内
        self.assertEqual((lv[0], lv[-1], len(lv)), (1008.0, 6500.0, 3))
        self.assertEqual(tie_levels(1008.0, 1200.0), [1008.0])           # 浅いと大引の下だけ

    def test_buckling_formula(self):
        """鋼構造設計規準の fc（SS400・短期＝長期×1.5）: 細長比 0 で F、長いほど小さい."""
        self.assertAlmostEqual(_fc(0.0, 10.0), 235.0)
        self.assertLess(_fc(3000.0, 8.84), 235.0)


class TestChecks(unittest.TestCase):
    def test_25t_rough_terrain_passes(self):
        p = kodai_plan("構台1", 30000.0, 8000.0, "R25", 3.0, top=500.0, depth=6300.0, embed=4700.0)
        st = {c.item: c.status for c in p.checks}
        self.assertTrue(all(v == "OK" for v in st.values()), st)
        self.assertIn("196kN", next(c.message for c in p.checks if c.item == "根太"))   # 0.7×(250＋30)
        self.assertEqual(p.max_load_t, round(280.0 / 9.80665, 1))

    def test_heavy_crane_needs_more(self):
        """65t ラフターは N 値 20・根入れ 4.7m では支持力が足りない、50t クローラは大引も足りない."""
        st = {c.item: c.status for c in kodai_plan("b", 30000.0, 8000.0, "R65", 3.0, depth=6300.0, embed=4700.0).checks}
        self.assertEqual(st["支柱の支持力"], "NG")
        st2 = {c.item: c.status for c in kodai_plan("c", 30000.0, 8000.0, "C50", 5.0, depth=6300.0, embed=4700.0).checks}
        self.assertEqual(st2["大引"], "NG")
        ok = {c.item: c.status for c in kodai_plan("d", 30000.0, 8000.0, "R65", 3.0, depth=6300.0, embed=9000.0,
                                                   n_value=40.0).checks}
        self.assertEqual(ok["支柱の支持力"], "OK")

    def test_slope_and_quantity(self):
        p = kodai_plan("e", 18000.0, 8000.0, top=500.0, slope=5.0)
        self.assertEqual({c.item: c.status for c in p.checks}["スロープ"], "NG")     # 1/6 より急
        q = {a: n for a, n, _c in p.quantity}
        self.assertEqual(q["覆工板 1×2m（高さ 208）"], 18 * 4)
        self.assertEqual(q["大引と支柱の接合 M22 高力ボルト"], 4 * len(p.xs) * len(p.ys))
        flat = kodai_plan("f", 18000.0, 8000.0, top=0.0)
        self.assertNotIn("スロープ", {c.item for c in flat.checks})


class TestPartParams(unittest.TestCase):
    def test_order_and_values(self):
        """覆工板の 3m の列・格子の決めを広さより先に（パラメータスクリプトが広さを切り上げる）."""
        p = kodai_plan("構台1", 30000.0, 8000.0, top=500.0, depth=6300.0, embed=4700.0, rails="SNE")
        prm = part_params(p)
        self.assertEqual(list(prm)[:6], ["dk3", "dk3At", "spMax", "ovh", "lenX", "lenY"])
        self.assertEqual((prm["lenX"], prm["lenY"], prm["secJ"], prm["secP"], prm["railW"]), (30.0, 8.0, 5, 4, False))
        self.assertEqual((prm["gAuto"], prm["lAuto"], prm["kdVeh"]), (True, True, "R25"))
        self.assertEqual(prm["maxLd"], "最大積載荷重 28.6t")


class TestMovedByHotspots(unittest.TestCase):
    """置いたあとホットスポットで支柱（構台杭）・大引・水平つなぎを動かし、H形鋼を選び直したら、部品のパラメータから検定し直す
    （利用者の指定 2026-11-01: こうだいくいと腹起こし 大引きのホットスポットで位置変更できるようにして あとH鋼の種類もね）."""

    def _params(self, **kw):
        ps = part_params(kodai_plan("構台1", 18000.0, 8000.0, top=500.0, depth=6300.0, embed=4700.0))
        ps.update(nGX=4, gX1=1.0, gX2=6.333, gX3=11.667, gX4=17.0, nGY=2, gY1=1.0, gY2=7.0, nLvP=3, lvD1=1.008,
                  lvD2=3.754, lvD3=6.5)
        ps.update(kw)
        return ps

    def test_moved_posts_and_levels(self):
        p = plan_from_params(self._params(gX2=9.0, gX3=12.0, lvD2=4.5))         # 列 2・3 を動かして 1〜9m の間を 8m に
        self.assertEqual(p.xs, [1000.0, 9000.0, 12000.0, 17000.0])
        self.assertEqual(p.levels, [1008.0, 4500.0, 6500.0])
        st = {c.item: c.status for c in p.checks}
        self.assertIn("支間 8.00m", next(c.message for c in p.checks if c.item == "根太"))
        self.assertEqual(st["根太"], "OK")

    def test_section_choice_and_overhang(self):
        weak = plan_from_params(self._params(secJ=1, gX2=9.0, gX3=12.0))           # 根太 H-200 で 8m は持たない
        self.assertEqual((weak.joist, {c.item: c.status for c in weak.checks}["根太"]), ("H-200", "NG"))
        big = plan_from_params(self._params(secP=6))
        self.assertEqual(big.post, "H-414")
        self.assertEqual(SEC_CODE["H-594"], 10)
        far = plan_from_params(self._params(gX1=3.0))                              # 入口の支柱を 3m 奥へ＝張出し 3m
        self.assertEqual({c.item: c.status for c in far.checks}["張出し"], "WARN")


if __name__ == "__main__":
    unittest.main()
