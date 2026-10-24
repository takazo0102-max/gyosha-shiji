"""ジャッキベースの詳細と、その下の敷板（利用者の指定 2026-10-25: ジャッキベースの詳細どあげて ジャッキベースの下に敷板規格の
長さかジャッキベースを配置して）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import SILL_LENGTHS_MM, line_params, sill_pieces

SPEC = {"project_name": "a", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "series_id": "nikken_nd1800"}
D3 = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"


class TestJackDetail(unittest.TestCase):
    def test_gdl_draws_the_catalog_shape(self):
        src = D3.read_text(encoding="utf-8")
        blk = src[src.index("820: ! ---- ジャッキベース"):]
        blk = blk[:blk.index("return\n")]
        self.assertIn("prism_ 41, 0.006", blk)              # ベース板 140角 t6・穴 4-φ14
        self.assertIn("cylind jsL + 0.12 - 0.006, 0.035 / 2", blk)   # ねじ棒 φ35、支柱の中へ 120
        self.assertIn("ashiba_jack_blue", blk)              # ND752P の底面の青
        self.assertIn("for hw = 0 to 1", blk)               # ハンドルの羽根2枚

    def test_blue_for_nd_only(self):
        r = solve_all(SPEC)
        self.assertEqual(line_params(r.model, r.model.plan.edges[0])["jkBlue"], 1)
        r2 = solve_all({**SPEC, "series_id": "shinwa_A"})
        self.assertEqual(line_params(r2.model, r2.model.plan.edges[0])["jkBlue"], 0)


class TestSillBoards(unittest.TestCase):
    def test_pieces_use_standard_lengths(self):
        self.assertEqual(sill_pieces(10000), [4000, 4000, 3000])     # 10300 = 4+4、残り2300 は足りる最短の 3m
        for ln in sill_pieces(24690):
            self.assertIn(ln, SILL_LENGTHS_MM)
        self.assertGreaterEqual(sum(sill_pieces(24690)), 24690 + 300)

    def test_drawn_and_counted(self):
        r = solve_all(SPEC)
        p = line_params(r.model, r.model.plan.edges[0])
        self.assertAlmostEqual(p["sillT"], 0.035)
        self.assertEqual(p["sillLens"], "4000,3000,2000,1500,1000")
        self.assertTrue(any("ジャッキベースの下の敷板" in w for w in r.quantity.warnings))
        off = solve_all({**SPEC, "sill_boards": False})
        self.assertEqual(line_params(off.model, off.model.plan.edges[0])["sillT"], 0.0)
        self.assertFalse(any("ジャッキベースの下の敷板" in w for w in off.quantity.warnings))
        src = D3.read_text(encoding="utf-8")
        self.assertIn("! ---- 敷板（支柱の列に沿って", src)


if __name__ == "__main__":
    unittest.main()
