"""タワークレーン（利用者の指定 2026-11-01: タワークレーンも追加してちょ）."""

from __future__ import annotations

import re
import unittest

from _path import SRC  # noqa: F401

from ashiba.oversail import inside, oversail, seg_dist
from ashiba.tower import (TOWERS, Placed, aviation, check, jib_axis, jib_length, judge_lift, light_count, overlaps, part_params,
                          procedures, rated_at, report, tie_checks, tower_from_params)

ROOT = SRC.parent


class TestOversail(unittest.TestCase):
    SITE = [(0.0, 0.0), (30000.0, 0.0), (30000.0, 20000.0), (0.0, 20000.0)]

    def test_geometry(self):
        self.assertAlmostEqual(seg_dist((5.0, 5.0), (0.0, 0.0), (10.0, 0.0)), 5.0)
        self.assertAlmostEqual(seg_dist((15.0, 0.0), (0.0, 0.0), (10.0, 0.0)), 5.0)
        self.assertTrue(inside((10.0, 10.0), self.SITE))
        self.assertFalse(inside((-1.0, 10.0), self.SITE))

    def test_edges_crossed(self):
        """マストが (8m, 10m) で半径 15m なら、下の辺（道路）・左の辺・上の辺の外へ出る。右の辺（22m 先）は出ない."""
        over = oversail((8000.0, 10000.0), 15000.0, self.SITE, {0})
        self.assertEqual([(o.edge, o.road, round(o.over)) for o in over], [(0, True, 5000), (2, False, 5000), (3, False, 7000)])
        self.assertEqual(oversail((8000.0, 10000.0), 5000.0, self.SITE), [])
        self.assertEqual(len(oversail((-1000.0, 10000.0), 5000.0, self.SITE)), 4)     # マストが敷地の外
        self.assertEqual(oversail((8000.0, 10000.0), 15000.0, []), [])                 # 敷地境界が無ければ判定しない


class TestTowers(unittest.TestCase):
    def test_catalog_values(self):
        """北川の図面・産業リーシングの仕様書の値."""
        t = TOWERS["jcl730"]
        self.assertEqual((t.mast_w, t.free_h, t.tail_r, t.max_t), (1.9, 51.455, 6.6, 27.5))   # 980＋1000＋48000＋1475＝51455
        self.assertEqual((TOWERS["v600"].tail_r, TOWERS["jcl080"].mast_w), (8.1, 1.17))
        names = set(re.findall(r'Name="([^"]+)"', (ROOT / "gdl" / "hsf" / "ashiba_tower" / "paramlist.xml").read_text(encoding="utf-8")))
        for t in TOWERS.values():
            self.assertEqual(set(part_params(t)) - names, set(), t.key)

    def test_dxf_measured(self):
        """北川の DXF と産業リーシングの側面図から測った値: JCL280GK のジブの根元は旋回中心から 0.30m 前・ベル受面から 1.706m 上（R95 のピンの円）、
        JCL080SKA は 0.80m・1.046m（1:300 の図。マスト 7,000×5 の寸法線で縮尺を確かめた）."""
        from ashiba.tower import pivot
        self.assertEqual(pivot(TOWERS["jcl280"]), (0.30, 1.706))
        self.assertEqual(pivot(TOWERS["jcl080"]), (0.80, 1.046))
        self.assertEqual(pivot(TOWERS["v600"]), (-3.1, 0.1))                    # 側面図の先端から解いたピン（旋回中心の後ろ）
        # カタログの側面図のジブの長さ（ピン〜先端）: V600S の 32m ジブは 41.6m で最大半径では約 33°、730NKD は 15°（公表）
        from ashiba.tower import luff_angle
        self.assertEqual(jib_length(32.0, TOWERS["v600"]), 41.6)
        self.assertAlmostEqual(luff_angle(32.0, 41.6, TOWERS["v600"]), 32.5, places=0)
        self.assertAlmostEqual(luff_angle(53.0, jib_length(53.0, TOWERS["jcl730"]), TOWERS["jcl730"]), 15.0, places=0)
        ps = part_params(TOWERS["jcl280"])
        self.assertEqual((ps["cwW"], ps["cwL"], ps["cwH"], ps["dkY"]), (4.57, 0.79, 1.49, -0.56))
        self.assertAlmostEqual(jib_length(24.0, TOWERS["jcl280"]), (24.0 - 0.30) / 0.9659258, places=2)

    def test_rated(self):
        """表の点の間は両側の小さい方。JCC-V600S の 0〜3.5m は 10t（ジブを立てた所）なので 2m は 10t."""
        self.assertEqual(rated_at(TOWERS["jcl730"], 32.0, 30.0), 23.5)
        self.assertEqual(rated_at(TOWERS["jcl730"], 37.0, 33.0), 17.3)    # 37m の表は無く 45m の表で、30m と 35m の点の小さい方
        self.assertEqual(rated_at(TOWERS["v600"], 32.0, 2.0), 10.0)
        self.assertEqual(rated_at(TOWERS["jcl080"], 42.0, 25.0), 1.8)      # 階段状 2.8t〜20m・1.8t〜31m
        self.assertIsNone(rated_at(TOWERS["ots90"], 20.0, 25.0))           # 20m ジブで 25m は届かない

    def test_ties(self):
        """北川の目安: 支えの上の自立高さ ≦ 最大自立高さ×2/3、間隔は 1/5 以上・最大自立高さ以下."""
        t = TOWERS["jcl280"]
        self.assertEqual([c.status for c in tie_checks(t, 40.0, [])], ["OK"])
        self.assertEqual([c.status for c in tie_checks(t, 80.0, [])], ["NG"])
        st = {c.item: c.status for c in tie_checks(t, 80.0, [30.0, 60.0])}
        self.assertEqual(st, {"支えの上の自立高さ": "OK", "支えの間隔": "OK"})
        st = {c.item: c.status for c in tie_checks(t, 80.0, [30.0, 35.0])}
        self.assertEqual(st["支えの上の自立高さ"], "NG")                  # 45m ＞ 46.755×2/3
        self.assertEqual(st["支えの間隔"], "NG")                          # 5m ＜ 46.755/5

    def test_checks_and_report(self):
        p = check(Placed("T1", TOWERS["jcl730"], mast=80, radius=30, load_t=25, ties_mm=[30000, 60000], origin=(8000.0, 10000.0)),
                  [(0.0, 0.0), (30000.0, 0.0), (30000.0, 20000.0), (0.0, 20000.0)], {0})
        st = {c.item: c.status for c in p.checks}
        self.assertEqual(st["定格荷重"], "NG")                             # 25t ＞ 23.5t
        self.assertEqual(st["航空障害灯"], "注意")
        self.assertEqual(st["敷地の外へ"], "要確認")
        self.assertAlmostEqual(jib_length(32.0), (32.0 - 1.0) / 0.9659258, places=2)
        self.assertIn("JCL730NKD", report([p]))


class TestLiftCheck(unittest.TestCase):
    def test_judge_lift(self):
        """据え付けたジブのまま: 吊り荷＋玉掛け用具 0.05t ≦ 定格荷重（ク則23条）、ジブの呼びより遠ければ遠すぎ."""
        t = TOWERS["jcl280"]
        self.assertEqual(judge_lift(t, 24.0, 46.755, 20.0, 30.0, 8.0), ("揚重可能", 14.0))
        self.assertEqual(judge_lift(t, 24.0, 46.755, 20.0, 30.0, 14.0)[0], "重すぎ")       # 14＋0.05 ＞ 14
        self.assertEqual(judge_lift(t, 24.0, 46.755, 30.0, 30.0, 3.0), ("遠すぎ", None))
        self.assertEqual(judge_lift(t, 24.0, 46.755, 20.0, 80.0, 3.0)[0], "高すぎ")

    def test_jib_axis_and_model(self):
        p0, p1 = jib_axis({"msH": 40.0, "pvX": 1.0, "pvH": 2.0, "jbL": 30.0, "jbA": 0.0, "slew": 90.0}, (1000.0, 2000.0, 0.0), 0.0)
        self.assertEqual([round(v) for v in p0], [1000, 3000, 42000])
        self.assertEqual([round(v) for v in p1], [1000, 33000, 42000])                   # 旋回 90° でジブは +Y
        self.assertIs(tower_from_params({"tcModel": 4}), TOWERS["jcl280"])


class TestErection(unittest.TestCase):
    def test_erect_plan(self):
        """最大分割重量（北川の図面）をマストの上（最小クライミング寸法）に据える: JCL280GK 4.4t は 25t で足り、
        JCL730NKD 12.8t は 70t。公開されていない機種は None."""
        from ashiba.tower import erect_height, erect_plan
        self.assertAlmostEqual(erect_height(TOWERS["jcl280"]), 6.57 + 2.06 + 2.0)
        ep = erect_plan(TOWERS["jcl280"])
        self.assertEqual((ep.model.key, ep.lifts[0].status), ("25t", "OK"))
        big = erect_plan(TOWERS["jcl730"])                                   # 12.8t を 10m・13.5m へは 70t（35t フック 0.34t）
        self.assertEqual((big.model.key, big.lifts[0].status), ("70t", "OK"))
        self.assertIsNone(erect_plan(TOWERS["v600"]))
        self.assertIn("組立て・解体の移動式クレーン", report([check(Placed("T", TOWERS["jcl280"]))]))


class TestLaws(unittest.TestCase):
    def test_procedures(self):
        """3t 以上は設置届（30 日前）・落成検査、0.5〜3t は設置報告。5t 以上は運転士免許、1t 以上の玉掛けは技能講習."""
        big = dict(procedures(TOWERS["jcl730"]))
        self.assertIn("30 日前", big["設置届"])
        self.assertIn("1.25 倍", big["落成検査"])
        self.assertIn("クレーン・デリック運転士免許", big["運転"])
        small = dict(procedures(TOWERS["jcl080"]))
        self.assertNotIn("設置届", small)
        self.assertIn("ク則11条", small["設置報告"])
        self.assertIn("特別教育", small["運転"])
        self.assertIn("技能講習", small["玉掛け"])                           # 2.8t は 1t 以上

    def test_aviation(self):
        """実施要領 第6章(10): 90m 未満は塔頂とジブ先端に低光度、90m 以上はジブ先端に中光度赤色、ジブ 45m 超は途中に足す."""
        self.assertEqual(aviation(55.0, 40.0), [])
        low = aviation(70.0, 40.0)
        self.assertTrue(low[0].endswith("低光度（32cd）") and low[1].endswith("低光度（32cd）"))
        high = aviation(120.0, 55.0)
        self.assertEqual((high[0], high[1]), ("Aフレーム頂部（塔頂）: 中光度赤色", "ジブ先端: 中光度赤色"))
        self.assertIn("1 個", high[2])
        p = check(Placed("T", TOWERS["jcl730"], mast=80.0, jib=53.0, radius=30.0))
        self.assertEqual(light_count(p), 2)                                   # 55m のジブ → 途中に 1 個
        self.assertEqual(light_count(check(Placed("T", TOWERS["ots90"], mast=20.0))), 0)

    def test_overlaps(self):
        a = check(Placed("A", TOWERS["jcl280"], origin=(0.0, 0.0)))
        b = check(Placed("B", TOWERS["jcl280"], origin=(40000.0, 0.0)))
        c = check(Placed("C", TOWERS["jcl280"], origin=(85000.0, 0.0)))   # ジブ 24m 同士で芯々 45m ＜ 48m
        self.assertEqual([x.detail.split("（")[0] for x in overlaps([a, b, c])], ["A と B", "B と C"])


if __name__ == "__main__":
    unittest.main()
