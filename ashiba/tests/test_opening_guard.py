"""床の開口の養生・床の縁の手すり（開発ループ 2026-11-01: 他に必要な仮設材の5番）."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.opening_guard import (TUBES, Guard, classify, drop_below, edge_runs, net_clearance, net_pick, oriented_box,
                                  part_params, plan_guard, plank_pieces, tube_pieces)


class TestClassify(unittest.TestCase):
    def test_sizes(self):
        """短辺 30cm 未満は小開口、長辺 60cm まで 12mm、1.8m まで 24mm（荷揚げ開口 1000×300 は 24mm 矢作）、超えれば手すり."""
        self.assertEqual([classify(w, d) for w, d in ((150, 150), (500, 500), (1000, 300), (1800, 900), (2500, 2000), (2000, 600))],
                         [1, 2, 3, 3, 4, 4])

    def test_net_clearance(self):
        """安全ネット指針: H2＝0.85(L＋3A)/4（L＜A）・0.85L（L≧A）."""
        self.assertAlmostEqual(net_clearance(3000.0, 3000.0), 0.85 * 3000.0)
        self.assertAlmostEqual(net_clearance(4000.0, 2000.0), 0.85 * (2000.0 + 3 * 4000.0) / 4.0)


class TestGuards(unittest.TestCase):
    def test_lid_and_rail(self):
        lid = plan_guard(Guard("開口1", 1000.0, 300.0, 3500.0))
        self.assertEqual(lid.kind, 3)
        self.assertIn("義務", lid.checks[0].message)
        q = {a: n for a, n, _u in lid.quantity}
        self.assertEqual((q["合板 12mm 910×1820（蓋）"], q["桟木 30×40×4000（ずれ止め）"]), (2, 1))   # 1200×500 の蓋を2枚重ね
        ev = plan_guard(Guard("EV", 2500.0, 2000.0, 3500.0))
        self.assertTrue(ev.net)
        self.assertEqual(ev.checks[0].status, "OK")
        q = {a: n for a, n, _u in ev.quantity}
        self.assertEqual(q["NREG スタンション（第1種・締付厚 0〜600）"], 2 * 2 + 2 * 2)   # 2.7×2.2m の囲い・隅は共有
        self.assertEqual((q["単管 3.0M（手すり・中桟）"], q["単管 2.5M（手すり・中桟）"]), (4, 4))   # 2辺×2段ずつ
        self.assertEqual(q["ARC1 兼用直交クランプ"], 4 * 3 * 2)                                 # 辺ごとに柱3本×2段
        self.assertEqual((q["杉足場板 S3530 35×210×3000（幅木）"], q["杉足場板 S3520 35×210×2000（幅木）"]), (2, 2))   # 左右は間に
        self.assertEqual(q["水平ネット 100mm 目 3×6m"], 1)
        big = plan_guard(Guard("吹抜け", 8000.0, 6000.0, 3500.0))
        self.assertEqual(big.checks[0].status, "WARN")                                  # ネットの下の空きが足りない
        low = plan_guard(Guard("ピット", 2500.0, 2000.0, 1500.0))
        self.assertFalse(low.net)
        self.assertIn("推奨", low.checks[0].message)
        edge = plan_guard(Guard("縁1", 12000.0, 0.0, 3500.0, kind=5, side=-1, post="PKB"))
        q = {a: n for a, n, _u in edge.quantity}
        self.assertEqual((q["PKB 固定ベース"], q["単管 1.0M（手すり柱）"], q["あと施工アンカー M10（固定ベース）"]), (8, 8, 16))
        prm = part_params(edge)
        self.assertEqual((prm["edSide"], prm["postK"], prm["rlS"], prm["rlL"]), (-1, 2, "1,1,1", "6000,5500,600"))   # 12.0m＋突き出し 50×2


class TestOrderPieces(unittest.TestCase):
    """発注の規格の長さで割り付ける（利用者の指定 2026-11-01: イメージじゃなく実際の規定の長さで発注できるくらい詳細に）."""

    def test_tubes(self):
        self.assertEqual(tube_pieces(2900.0, 475.0), [3000])                 # 2.2＋0.7 より 3.0M 1本（両端 50 ずつ長く）
        self.assertEqual(tube_pieces(5200.0, 633.0), [5500])
        self.assertEqual(tube_pieces(10200.0, 633.0), [6000, 4500])          # 継ぎ目は直線ジョイント1つ
        self.assertTrue(all(t in TUBES for t in tube_pieces(30200.0, 680.0)))
        self.assertGreaterEqual(sum(tube_pieces(30200.0, 680.0)), 30200.0)
        self.assertEqual(tube_pieces(2900.0, 0.0), [2200, 700])              # 余りを許さなければ突き合わせで

    def test_planks_and_nets(self):
        self.assertEqual(plank_pieces(5200.0), [4000, 2000])
        self.assertEqual(plank_pieces(10000.0), [4000, 4000, 2000])
        self.assertEqual(net_pick(3100.0, 2600.0), [(3000, 6000)])
        self.assertEqual(net_pick(12600.0, 6600.0), [(10000, 10000)] * 2)


class TestGeometry(unittest.TestCase):
    def test_box_drop_and_edges(self):
        self.assertEqual(oriented_box([(0, 0), (0, 4000), (-1000, 4000), (-1000, 0)]), ((0.0, 0.0), 4000.0, 1000.0, 90.0))
        upper = {"outline": [(0, 0), (10000, 0), (10000, 8000), (0, 8000)], "holes": [[(4000, 3000), (6000, 3000), (6000, 5000),
                                                                                      (4000, 5000)]], "top": 3500.0}
        lower = {"outline": [(0, 0), (10000, 0), (10000, 8000), (0, 8000)], "holes": [], "top": 0.0}
        self.assertEqual(drop_below((5000, 4000), 3500.0, [upper, lower], -1500.0), 3500.0)     # 下の床まで
        self.assertEqual(drop_below((5000, 4000), 3500.0, [upper], -1500.0), 5000.0)           # 下に床が無ければ地盤まで
        nxt = {"outline": [(10000, 0), (20000, 0), (20000, 8000), (10000, 8000)], "holes": [], "top": 3500.0}
        runs = edge_runs(upper, [upper, lower, nxt])
        self.assertEqual(len(runs), 3)                                                          # 隣の床に続く辺は外す


class TestRunScript(unittest.TestCase):
    def test_slab_info(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from opening_run import slab_info

        d = {"details": {"polygonOutline": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 8}, {"x": 0, "y": 8}],
                         "holes": [{"polygonOutline": [{"x": 4, "y": 3}, {"x": 6, "y": 3}, {"x": 6, "y": 5}, {"x": 4, "y": 5}]}],
                         "thickness": 0.2, "zCoordinate": 3.5, "referencePlaneLocation": "Top"}}
        s = slab_info(d)
        self.assertEqual((len(s["outline"]), len(s["holes"]), s["top"], s["t"]), (4, 1, 3500.0, 200.0))


if __name__ == "__main__":
    unittest.main()
