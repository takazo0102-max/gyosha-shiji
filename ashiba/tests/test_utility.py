"""仮設電気・給排水（利用者の指定 2026-11-02「各図面を参考にして、図面かボタンを追加してちょ」の続き。施工図の手引き p.23〜24）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.utility import KINDS, LINE_KINDS, Item, check, drawing, report, separation, slope_of


class TestUtility(unittest.TestCase):
    def test_drain_fall(self):
        """排水の標準の勾配（SHASE-S206-2009）: 65 以下 1/50・75 と 100 は 1/100・125 以上 1/200。20m の φ100 は落差 200."""
        self.assertEqual((slope_of(50), slope_of(100), slope_of(150)), (50.0, 100.0, 200.0))
        it = check(Item("排水管1", "排水管", [(0, 0), (12000, 0), (12000, 8000)], 100.0))
        self.assertIn("落差 200mm", it.checks[0].message)
        self.assertEqual(it.checks[1].item, "沈砂槽")

    def test_overhead_line_and_crane(self):
        """送配電線からの離隔の目安: 低圧 1m・高圧 1.2m・特別高圧 2m（6万V 以上は 1万V ごとに 20cm）. 近いクレーンは要確認."""
        self.assertEqual((separation("低圧"), separation("高圧"), separation("特別高圧"), separation("特別高圧", 77)),
                         (1000.0, 1200.0, 2000.0, 2400.0))
        near = check(Item("架空1", "架空電線", [(0, 0), (20000, 0)], volt="高圧"), [("クレーン1", (1000, 1000, 5000, 6000))])
        self.assertEqual(near.checks[0].status, "WARN")
        far = check(Item("架空2", "架空電線", [(0, 0), (20000, 0)], volt="高圧"), [("クレーン1", (1000, 1300, 5000, 6000))])
        self.assertEqual(far.checks[0].status, "OK")

    def test_symbols(self):
        """どの種類も記号が描ける。管・電線は線のとおり、機器は線の始め＝芯で、向きに回る."""
        for k in KINDS:
            d = drawing(Item("x", k, [(0, 0), (1000, 0)]))
            self.assertTrue(d["lines"] and d["texts"], k)
        d = drawing(Item("x", "キュービクル", [(5000, 5000), (5000, 6000)]))          # 向き 90°
        xs = [p[0] for p in d["lines"][0][0]]
        self.assertAlmostEqual(max(xs) - min(xs), 1200.0)                            # 2000×1200 が回る
        self.assertEqual(drawing(Item("x", "地中埋設電線", [(0, 0), (1000, 0)]))["lines"][0][1], "chain")
        self.assertIn("| 給水管 φ25 | 3.0m |", report([check(Item("給水1", "給水管", [(0, 0), (3000, 0)], 25.0))]))
        self.assertEqual(LINE_KINDS[0], "給水管")


if __name__ == "__main__":
    unittest.main()
