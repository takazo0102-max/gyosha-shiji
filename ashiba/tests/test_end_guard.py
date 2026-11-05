"""妻側（足場の端の開放端）を布材かブレス材（先行手すり）か選ぶ（利用者の指定 2026-10-24: 妻側を布材かブレス材か選択する
仕組み作成して）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, solve_all
from ashiba.gdl_params import line_params

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
        "series_id": "nikken_nd1800", "faces": ["南面", "東面"]}
GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"


class TestEndGuard(unittest.TestCase):
    def test_default_is_rails(self):
        r = solve_all(RECT)
        self.assertEqual(r.model.config.end_guard, "布材")
        self.assertEqual(line_params(r.model, r.model.plan.edges[0])["endBrace"], 0)
        self.assertEqual(r.quantity.qty_of("先行手摺"), 0)

    def test_brace_replaces_the_rails(self):
        r0 = solve_all(RECT)
        r = solve_all({**RECT, "end_guard": "ブレス材"})
        self.assertEqual(line_params(r.model, r.model.plan.edges[0])["endBrace"], 1)
        # 1層1箇所に1枚（布材は手すり＋中桟の2本）。開放端2箇所×5層
        n = r.quantity.qty_of("先行手摺", 610)
        self.assertEqual(n, 10)
        self.assertEqual(r0.quantity.qty_of("布材", 610) - r.quantity.qty_of("布材", 610), 2 * n)
        self.assertTrue(any("ブレス材（先行手すり）" in n for n in r.quantity.notes))

    def test_tube_and_frame_keep_rails(self):
        r = solve_all({**RECT, "end_guard": "ブレス", "series_id": "waku"})
        self.assertEqual(line_params(r.model, r.model.plan.edges[0])["endBrace"], 0)

    def test_bad_value(self):
        with self.assertRaises(InputError):
            solve_all({**RECT, "end_guard": "ネット"})

    def test_3d_draws_the_advance_rail_at_open_ends(self):
        src = GDL.read_text(encoding="utf-8")
        blk = src[src.index("! ---- 開放端（一部の面だけの足場"):src.index("! ---- 枠組の出隅コーナー")]
        self.assertIn("if endBrace = 1 then", blk)
        self.assertIn("gosub 850", blk)

    def test_form_and_object(self):
        from ashiba.spec_form import apply_form, form_fields
        from ashiba.spec_object import params_from_spec

        v = {f["key"]: f.get("value") for f in form_fields(RECT) if f["key"]}
        self.assertEqual(v["end"], "布材（手すり＋中桟）")
        new, _n = apply_form(RECT, {**v, "end": "ブレス材（先行手すり）"})
        self.assertEqual(new["end_guard"], "ブレス材")
        self.assertEqual(params_from_spec(new)["endGuard"], "ブレス材")


if __name__ == "__main__":
    unittest.main()
