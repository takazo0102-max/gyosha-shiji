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
        self.assertIn('material "ashiba_jack_steel"', blk)   # 支柱と見分ける色（利用者の指定 2026-10-25）
        self.assertIn("if jkSill = 1 and sillT > 0.001 then", blk)   # 通しの敷板の無い脚は 1m の敷板
        self.assertIn("for hw = 0 to 1", blk)               # ハンドルの羽根2枚

    def test_standard_jack_is_a752_and_long_nd752sp(self):
        # 利用者の指定 2026-10-25: ジャッキベースはジャッキベースかロングジャッキを基本に
        r = solve_all(SPEC)
        self.assertEqual(line_params(r.model, r.model.plan.edges[0])["jkBlue"], 0)
        nos = {l.part.model_no for l in r.quantity.lines if l.part.category == "ジャッキ"}
        self.assertIn("A752", nos)
        self.assertNotIn("ND752P", nos)


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
