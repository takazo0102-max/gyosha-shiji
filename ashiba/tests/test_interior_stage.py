"""内部ステージ足場（利用者の指定 2026-10-24: 内部足場の内部ステージ足場の機能追加して検証して）."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.interior_stage import solve_stage, stage_params, stage_report
from ashiba.master import load_master
from ashiba.structural import load_capacities

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
RECT = [[0, 0], [12000, 0], [12000, 8000], [0, 8000]]


def solve(**kw):
    m = load_master("nikken_nd1800")
    item = {"name": "吹抜け", "corners_mm": RECT, "deck_mm": 6000, **kw}
    return solve_stage(item, m, load_capacities("nikken_nd1800"))


class TestInteriorStage(unittest.TestCase):
    def test_grid_fits_inside_with_long_spans(self):
        r = solve()
        self.assertEqual(r.spans_u, [1829] * 6)
        self.assertEqual(r.spans_v, [1829] * 4)
        self.assertLessEqual(r.length_u, 12000 - 300)
        self.assertEqual(r.deck_mm, 6000)
        self.assertEqual(r.levels[-1], 6000)
        # 中央に寄せる
        self.assertAlmostEqual(r.origin[0], (12000 - r.length_u) / 2, delta=1)

    def test_checks(self):
        r = solve()
        st = {c.item: c.status for c in r.checks}
        self.assertEqual(st["支柱の軸力"], "OK")
        self.assertEqual(st["作業床の積載"], "WARN")              # 1.5kN/m² × 1829² は 250kg/スパンを超える
        self.assertEqual(st["高さと短辺の比"], "OK")
        light = solve(live_kn_m2=0.6)
        self.assertEqual({c.item: c.status for c in light.checks}["作業床の積載"], "OK")
        tall = solve(corners_mm=[[0, 0], [12000, 0], [12000, 2500], [0, 2500]], deck_mm=12000)
        self.assertEqual({c.item: c.status for c in tall.checks}["高さと短辺の比"], "WARN")
        heavy = solve(live_kn_m2=6.0)
        self.assertEqual({c.item: c.status for c in heavy.checks}["支柱の軸力"], "NG")
        self.assertFalse(heavy.ok)

    def test_quantity_and_report(self):
        r = solve()
        q = {(c, d, why): n for c, d, n, why in r.quantity}
        self.assertEqual(q[("ジャッキ", 0, "内部ステージのジャッキベース")], 7 * 5)
        decks = sum(n for c, d, n, why in r.quantity if c == "踏板")
        self.assertEqual(decks, 6 * 4 * 4)                     # 1829 を 500×3＋240×1 で埋める
        txt = stage_report(r)
        self.assertIn("## 検証", txt)
        self.assertIn("支柱の軸力", txt)
        p = stage_params(r)
        self.assertEqual(p["spanU"], "1829,1829,1829,1829,1829,1829")
        self.assertAlmostEqual(p["deckH"], 6.0)

    def test_deck_is_the_nearest_level(self):
        r = solve(deck_mm=4000)
        self.assertLessEqual(abs(r.deck_mm - 4000), 300)
        self.assertEqual(r.levels[-1], r.deck_mm)

    def test_too_small(self):
        with self.assertRaises(ValueError):
            solve(corners_mm=[[0, 0], [500, 0], [500, 500], [0, 500]])

    def test_guides_to_corners_and_part(self):
        from interior_stage_run import corners_of

        self.assertEqual(corners_of([(None, [((0.0, 0.0), (5.0, 3.0))])]), [[0.0, 0.0], [5.0, 0.0], [5.0, 3.0], [0.0, 3.0]])
        poly = [(None, [((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (4.0, 2.0)), ((4.0, 2.0), (0.0, 2.0)), ((0.0, 2.0), (0.0, 0.0))])]
        self.assertEqual(len(corners_of(poly)), 4)
        self.assertTrue((ROOT / "gdl" / "ashiba_stage.gsm").exists())
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_stage" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("最上段の全面の作業床", d3)
        self.assertNotIn(" LV ", d3)                          # 配列 lv と大文字小文字で衝突しない名前


if __name__ == "__main__":
    unittest.main()
