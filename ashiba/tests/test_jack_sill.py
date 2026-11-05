"""ジャッキベースの詳細と、その下の敷板（利用者の指定 2026-10-25: ジャッキベースの詳細どあげて ジャッキベースの下に敷板規格の
長さかジャッキベースを配置して）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, solve_groups
from ashiba.gdl_params import SILL_LENGTHS_MM, line_params
from ashiba.sill_boards import SILL_END_MM, piece_lengths, runs_of

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
        self.assertIn("if jkSill = 1 and sillT > 0.001 and nGl >= 2 then", blk)   # 高低差のある地盤で列の無い脚は 1m
        self.assertIn("for hw = 0 to 1", blk)               # ハンドルの羽根2枚

    def test_post_joints_have_their_own_colour(self):
        # 利用者の指定 2026-10-25: 支柱の継ぎ目は色変えてわかるようにして
        src = D3.read_text(encoding="utf-8")
        blk = src[src.index("840:\t! ---- 支柱の継ぎ目"):]
        blk = blk[:blk.index("847:")]
        self.assertIn('define material "ashiba_post_joint"', src)
        # 長さごとの色（利用者の指定 2026-10-25: 支柱の繋ぎの色は長さごとに変えて）。下の帯は下の支柱、上の帯は上の支柱
        self.assertIn("jLen = jLo", blk)
        self.assertIn("jLen = jUp", blk)
        sub = src[src.index("847:\t! 支柱の長さ jLen"):]
        sub = sub[:sub.index("return\n")]
        for mat in ("ashiba_pj_36", "ashiba_pj_27", "ashiba_pj_18", "ashiba_pj_09", "ashiba_pj_045"):
            self.assertIn(f'material "{mat}"', sub)
        self.assertEqual(src.count("jUp = "), 3)                      # 支柱を積む3か所とも

    def test_standard_jack_is_a752_and_long_nd752sp(self):
        # 利用者の指定 2026-10-25: ジャッキベースはジャッキベースかロングジャッキを基本に
        r = solve_all(SPEC)
        self.assertEqual(line_params(r.model, r.model.plan.edges[0])["jkBlue"], 0)
        nos = {l.part.model_no for l in r.quantity.lines if l.part.category == "ジャッキ"}
        self.assertIn("A752", nos)
        self.assertNotIn("ND752P", nos)


class TestSillBoards(unittest.TestCase):
    def test_pieces_use_standard_lengths_and_cut_the_last(self):
        # 利用者の指摘 2026-10-25: 敷板が飛び出ている 規格の大きさを基本でカット必要な箇所はカットして飛び出ないように
        self.assertEqual(piece_lengths(10300), [(4000, 4000.0), (4000, 4000.0), (3000, 2300.0)])
        self.assertEqual(piece_lengths(4600), [(3000, 3000.0), (2000, 1600.0)])     # 残りを 1m 以上に
        for std, ln in piece_lengths(24690):
            self.assertIn(std, SILL_LENGTHS_MM)
            self.assertLessEqual(ln, std)
        self.assertAlmostEqual(sum(ln for _s, ln in piece_lengths(24690)), 24690)

    def test_rows_end_just_past_the_end_feet(self):
        r = solve_all(SPEC)
        for ei, runs in runs_of(r.model, r.stair_plan).items():
            for run in runs:
                self.assertLessEqual(run.x1_mm, run.feet[-1] + SILL_END_MM + 0.5)
                self.assertGreaterEqual(run.x0_mm, run.feet[0] - SILL_END_MM - 0.5)

    def test_outer_corner_post_sits_on_the_extended_outer_row(self):
        r = solve_all(SPEC)
        runs = runs_of(r.model, r.stair_plan)[0]
        outer = next(x for x in runs if x.y_mm < 0)
        w = r.model.row_spacing_of(len(r.model.plan.outline.edges) - 1)
        self.assertEqual(outer.feet[0], -w)                           # 出隅の外側の角の支柱
        self.assertAlmostEqual(outer.x0_mm, -w - SILL_END_MM)

    def test_boards_do_not_overlap_at_corners(self):
        from ashiba import sill_boards as SB

        for spec in (SPEC, {**SPEC, "outline_mm": [[0, 0], [24000, 0], [24000, 8000], [12000, 8000], [12000, 16000],
                                                   [0, 16000]]}, {**SPEC, "stairs": {"layout": "外付け"}}):
            r = solve_all(spec)
            items = [(run, SB._world(r.model, run)) for runs in runs_of(r.model, r.stair_plan).values() for run in runs]
            for i, (a, _wa) in enumerate(items):
                for b, _wb in items[i + 1:]:
                    c = SB._cross(r.model, a, r.model, b)
                    if c is None:
                        continue
                    self.assertEqual(c[0], "x", (a, b))
                    # 直交して重なるのは、通る板の上で終わる板が無いとき（交差の内側に端が無い）
                    self.assertFalse(SB._end_at(a, c[1], c[2]) and SB._end_at(b, *SB._cross(r.model, b, r.model, a)[1:]),
                                     (a, b))
            # どの脚もどれかの板に載る
            for run, (p, u, _n) in items:
                for x in run.feet:
                    q = SB._pt(p, u, x)
                    self.assertTrue(any(SB._covered(r.model, o, q) for o, _w in items), (run, x))

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
