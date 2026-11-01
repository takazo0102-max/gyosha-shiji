"""移動式クレーン（利用者の指定 2026-11-01: クレーン リサーチして追加して）."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.crane import (MODELS, PLATE_AREA, Lift, boom_angle, boom_axis, crane_plan, hook_height, judge, part_params,
                          plan_lift, rated, rated_strings, report, seg_box_distance)

M25, M50, M70 = MODELS["25t"], MODELS["50t"], MODELS["70t"]


class TestRatedTables(unittest.TestCase):
    def test_values_from_the_spec_sheets(self):
        """タダノの定格総荷重表の値（GR-250N（Ⅴ）6.6m・3.6m、GR-500N（Ⅰ）7.4m、GR-700N-3 7.8m）."""
        self.assertEqual(rated(M25, 6.6, 23.45, 10.0), 7.6)
        self.assertEqual(rated(M25, 6.6, 9.35, 3.5), 25.0)
        self.assertEqual(rated(M25, 3.6, 16.4, 10.0), 2.9)
        self.assertEqual(rated(M50, 7.4, 41.2, 10.0), 7.0)
        self.assertEqual(rated(M50, 7.4, 38.05, 10.0), 8.5)
        self.assertEqual(rated(M70, 7.8, 30.3, 20.0), 4.1)                     # モードの違う2列は大きい方
        self.assertEqual(rated(M70, 7.8, 9.8, 2.1), 70.0)

    def test_between_rows_and_out_of_reach(self):
        self.assertEqual(rated(M25, 6.6, 23.45, 10.3), 6.65)                   # 間は外側の行（安全側）
        self.assertIsNone(rated(M25, 6.6, 9.35, 7.0))                          # 9.35m のブームは 6.5m まで
        self.assertIsNone(rated(M25, 6.6, 30.5, 3.0))                          # 長いブームは近くに下ろせない
        self.assertEqual(rated(M25, 5.5, 16.4, 10.0), 4.95)                    # 張出 5.5m は 5.0m の表で


class TestGeometry(unittest.TestCase):
    def test_hook_height_matches_max_lift_height(self):
        """30.5m のブームを立てたときのフックの高さ ≒ 仕様書の最大地上揚程 31.3m."""
        self.assertAlmostEqual(hook_height(M25, 30.5, 3500.0), 31300.0, delta=400.0)
        self.assertEqual(hook_height(M25, 9.35, 9000.0), -1.0)
        self.assertAlmostEqual(boom_angle(M25, 23.45, 12000.0), 56.3, places=1)
        self.assertEqual(max(M25.spreads) * 1000.0 + M25.float_d, 6900.0)      # フロート外端（寸法図）
        self.assertEqual(max(M70.spreads) * 1000.0 + M70.float_d, 8200.0)


class TestPlan(unittest.TestCase):
    def test_shortest_boom_that_reaches_and_lifts(self):
        x = plan_lift(M25, 6.6, Lift("柱", 12000.0, 2.5, 15000.0))
        self.assertEqual((x.boom, x.rated_t, x.status), (23.45, 5.8, "OK"))     # 16.4m はフックが 15m に届かない
        y = plan_lift(M25, 6.6, Lift("重い", 8000.0, 9.0, 8000.0))
        self.assertEqual((y.boom, y.status), (16.4, "OK"))                      # 11.4t の 82%
        z = plan_lift(M25, 6.6, Lift("過負荷", 20000.0, 3.0, 5000.0))
        self.assertEqual(z.status, "NG")
        w = plan_lift(M25, 6.6, Lift("ぎりぎり", 10000.0, 6.8, 5000.0))
        self.assertEqual(w.status, "WARN")                                      # 定格 7.6t の 93%（計画は 90% まで）

    def test_auto_model_and_plates(self):
        p = crane_plan("a", [Lift("鉄骨", 8000.0, 15.0, 10000.0)])
        self.assertEqual(p.model.key, "50t")                                    # 25t の 16.4m は 11.4t で足りない
        self.assertTrue(p.ok)
        q = crane_plan("b", [Lift("柱", 12000.0, 2.5, 15000.0)])
        self.assertEqual((q.model.key, q.plates), ("25t", 1))
        self.assertAlmostEqual(q.reaction_t, 0.8 * (25.495 + 2.8), places=2)
        self.assertLessEqual(q.pressure, 100.0)
        soft = crane_plan("c", [Lift("柱", 12000.0, 2.5, 15000.0)], soil_q=60.0)
        self.assertEqual(soft.plates, 2)                                        # 十字に2枚
        self.assertAlmostEqual(soft.pressure, soft.reaction_t * 9.80665 / PLATE_AREA[2])
        mud = crane_plan("d", [Lift("柱", 12000.0, 2.5, 15000.0)], soil_q=30.0)
        self.assertFalse(mud.ok)

    def test_checks_quantity_report_and_params(self):
        p = crane_plan("a", [Lift("柱", 12000.0, 2.5, 15000.0), Lift("資材", 18000.0, 1.0, 12000.0)], model="25t", spread=5.0)
        st = {c.item: c.status for c in p.checks}
        self.assertEqual(st["アウトリガの張出"], "WARN")                            # 最大限に張り出していない（70条の5）
        for k in ("立入禁止", "強風", "作業計画"):
            self.assertIn(k, st)
        self.assertIn("厚板鋼板 NT22×5×10（1524×3048×22・802kg）", {a for a, _n, _c in p.quantity})
        prm = part_params(p, 30.0)
        self.assertEqual((prm["crType"], prm["outW"], prm["wrR"], prm["slew"]), (1, 5.0, "12000,18000", 30.0))
        self.assertEqual(prm["boomL"], p.governing.boom)
        md = report([p])
        for w in ("# 移動式クレーン", "クレーン則", "タダノ", "定格総荷重"):
            self.assertIn(w, md)


class TestPartTable(unittest.TestCase):
    def test_rated_strings_fit_255(self):
        """部品へ渡す定格総荷重表: 文字のパラメータは 255 字で切れるのでブームの列ごとに分け、どれも 255 字以内."""
        for m in MODELS.values():
            for sp in m.spreads:
                s = rated_strings(m, sp)
                self.assertTrue(all(len(v) <= 255 for v in s.values()), (m.key, sp, {k: len(v) for k, v in s.items()}))
        s = rated_strings(M25, 6.6)
        radii = [float(v) / 1000 for v in s["rtR"].split(",")]
        col = [int(v) for v in s["rtT3"].split(",")]                       # 3番目のブーム 23.45m
        self.assertEqual(col[radii.index(10.0)], 7600)


class TestSmartconChecks(unittest.TestCase):
    """smartCON Planner を手本にした揚重判定・ブームの干渉（利用者の指定 2026-11-01）."""

    def test_judge_four_results(self):
        """2026-11-01 実機の試験の壁4枚と同じ値: 揚重可能・遠すぎ・高すぎ・重すぎ."""
        self.assertEqual(judge(M25, 6.6, 12000.0, 8000.0, 1.15)[0], "揚重可能")
        self.assertEqual(judge(M25, 6.6, 32000.0, 8000.0, 1.15)[0], "遠すぎ")          # どのブームも 32m に届かない
        self.assertEqual(judge(M25, 6.6, 8300.0, 42000.0, 7.68)[0], "高すぎ")          # 最大地上揚程 31.3m を超える
        self.assertEqual(judge(M25, 6.6, 10600.0, 8000.0, 21.6)[0], "重すぎ")

    def test_segment_to_box_distance(self):
        self.assertEqual(seg_box_distance((0, 0, 0), (10, 0, 0), (4, -1, -1), (6, 1, 1)), 0.0)    # 箱の中を通る
        self.assertAlmostEqual(seg_box_distance((0, 0, 0), (10, 0, 0), (4, 3, -1), (6, 5, 1)), 3.0)
        self.assertAlmostEqual(seg_box_distance((0, 0, 0), (10, 0, 0), (12, 0, 0), (13, 1, 1)), 2.0)  # 先の向こう

    def test_boom_axis_and_travel(self):
        """車体 90°・旋回 −90° で +X へ。走行姿勢は最短ブームを車体の前へ水平に."""
        p0, p1 = boom_axis({"slew": -90.0, "boomL": 16.4, "boomA": 31.388}, (0.0, 0.0, 0.0), 90.0)
        self.assertEqual([round(v) for v in p0 + p1], [-1000, 0, 2300, 13000, 0, 10842])
        q0, q1 = boom_axis({"slew": -90.0, "boomL": 16.4, "boomA": 31.388, "bMin": 9.35, "travel": True}, (0.0, 0.0, 0.0), 90.0)
        self.assertEqual([round(v) for v in q0 + q1], [0, -1000, 2300, 0, 8350, 2300])


class TestRunScript(unittest.TestCase):
    def test_points_to_lifts(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from crane_run import lifts_from_points

        c, ls = lifts_from_points([(0.0, 0.0), (12000.0, 0.0), (0.0, 18000.0)], "2.5", "15000,12000")
        self.assertEqual(c, (0.0, 0.0))
        self.assertEqual([(x.radius, x.load_t, x.need_z) for x in ls], [(12000.0, 2.5, 15000.0), (18000.0, 2.5, 12000.0)])


if __name__ == "__main__":
    unittest.main()
