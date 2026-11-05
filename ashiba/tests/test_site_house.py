"""仮設建物（開発ループ 2026-11-01: 他に必要な仮設材の4番）."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.site_house import House, Site, check, house_from_params, part_params, stair_for, toilet_need


class TestToilets(unittest.TestCase):
    def test_article_628(self):
        """安衛則 628条: 男性の大便所 60人・小便所 30人・女性 20人ごとに1つ。628条の2: 独立個室型は1つ×10人を差し引く."""
        self.assertEqual(toilet_need(45, 5)[:3], (1, 2, 1))
        self.assertEqual(toilet_need(61, 21)[:3], (2, 3, 2))
        self.assertEqual(toilet_need(45, 5, 2)[:3], (1, 1, 0))          # 20人を差し引く
        self.assertEqual(toilet_need(8, 1, 1)[:3], (0, 0, 0))           # 常時10人以内は独立個室型1つでよい


class TestHouses(unittest.TestCase):
    def test_size_area_and_wind(self):
        office = House("事務所棟", 4, 3, 2, (1, 1))
        self.assertEqual(office.size, (5450.0, 6900.0, 2603.0))         # 3.8坪（SH-H4）を奥へ3連棟
        self.assertAlmostEqual(office.area(1), 2 * 5.45 * 6.9, places=3)
        self.assertEqual(House("t", 6, 4).size, (3400.0, 1550.0, 2470.0))  # トイレは横に並べる
        self.assertLess(House("t", 6, 4).wind_speed(), 30.0)             # 仮設トイレは固定が要る
        self.assertGreater(office.wind_speed(), 30.0)
        self.assertAlmostEqual(House("a", 4).wind_speed(), 30.7, delta=0.5)   # 調べたメモの概算（約 29m/s）に近い

    def test_site_checks(self):
        s = check(Site([House("事務所棟", 4, 3, 2, (1, 1)), House("詰所", 5, 2, 1, (2,)), House("トイレ", 6, 4, 1, (7,))],
                       staff=8, men=40, women=5))
        st = {c.item: c.status for c in s.checks}
        self.assertEqual(st["事務所の広さ"], "OK")                       # 75.2㎡ ≧ 8人×9㎡
        self.assertEqual(st["詰所・休憩所"], "WARN")                     # 33.4㎡ < 45人×1.2㎡
        self.assertEqual(st["休養室"], "WARN")                           # 53人 ≧ 50
        self.assertEqual(st["トイレ 転倒"], "WARN")
        single = check(Site([House("a", 4, 1, 2, (1, 1))]))
        self.assertEqual({c.item: c.status for c in single.checks}["a 段積み"], "WARN")   # 1階が単体の2段は不可
        q = {a: n for a, n, _c in s.quantity}
        self.assertEqual(q["スーパーハウス 3.8坪（SH-H4）"], 6)

    def test_params_round_trip(self):
        h = House("事務所棟", 4, 3, 2, (1, 3), 1, 1200.0, 1100.0)
        ps = part_params(h)
        self.assertEqual((ps["hsType"], ps["nUnit"], ps["nTier"], ps["use1"], ps["use2"], ps["stairSd"]), (4, 3, 2, 1, 3, 1))
        back = house_from_params(ps)
        self.assertEqual((back.kind, back.units, back.tiers, back.uses[:2], back.stair, back.stair_w), (4, 3, 2, (1, 3), 1, 1200.0))

    def test_stair_products(self):
        """外階段はカナモトのハウス用階段（利用者の指定 2026-11-01: 仮設建物の階段も製品の規格にして）: 低い型は FE用 900×4,100、
        3段積みは2階分と踊り場."""
        h = House("事務所棟", 4, 3, 2, (1, 1))
        self.assertEqual((h.stair_kind, h.stair_width), ("FE", 900.0))
        self.assertEqual(stair_for(2900.0), "KD")
        prm = part_params(h)
        self.assertEqual((prm["stairW"], prm["stairL"], prm["stName"]), (0.9, 4.1, "ハウス用階段 FE用"))
        s = check(Site([h, House("3階", 5, 3, 3, (1, 1, 2))]))
        q = {a: n for a, n, _u in s.quantity}
        self.assertEqual((q["ハウス用階段 FE用（カナテック） 900×4100×3350"], q["踊り場 SC（カナテック。3階への折り返し）"]), (3, 1))

    def test_use_names(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from house_run import parse_uses

        self.assertEqual(parse_uses("事務所,詰所"), (1, 2))
        self.assertEqual(parse_uses("7"), (7,))
        with self.assertRaises(SystemExit):
            parse_uses("食堂")


if __name__ == "__main__":
    unittest.main()
