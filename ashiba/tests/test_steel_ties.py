"""鉄骨の壁つなぎ: 鉄骨から取る／仕上げから取る（利用者の指定 2026-10-24: 鉄骨の足場の壁繋ぎ機能つけて鉄骨からとる時と
仕上げから取るときの両方が必要）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import tie_placements
from ashiba.cli import InputError, solve_all
from ashiba.quantity import wall_tie_required_length_mm

STORIES = [{"name": f"{k}F", "level_mm": 3500.0 * (k - 1)} for k in range(1, 6)]
SPEC = {"project_name": "S", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 14000, "module": "inch", "stories": STORIES}
TIE_GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_tie" / "scripts" / "3d.gdl"


class TestSteelTies(unittest.TestCase):
    def test_finish_is_the_default(self):
        r = solve_all(SPEC)
        self.assertEqual(r.model.config.tie_source, "仕上げ")
        self.assertEqual(tie_placements(r.model)[0].params["steelD"], 0.0)

    def test_steel_ties_sit_on_the_beams_and_reach_them(self):
        r0 = solve_all(SPEC)
        r = solve_all({**SPEC, "tie_source": "鉄骨"})
        m = r.model
        self.assertEqual(m.config.steel_depth_mm, 150.0)
        # 取付の高さ（作業床の高さ−300）は梁の高さ（各階の床−150）
        beams = {3500.0 * k - 150.0 for k in range(1, 5)}
        grid = [t for t in m.wall_ties if t.kind == "grid"]
        self.assertTrue(grid)
        self.assertTrue({t.height_mm - 300 for t in grid} <= {int(b) for b in beams})
        self.assertAlmostEqual(wall_tie_required_length_mm(m, 0) - wall_tie_required_length_mm(r0.model, 0), 150.0)
        p = tie_placements(m)[0].params
        self.assertAlmostEqual(p["steelD"], 0.15)
        self.assertTrue(any("ビームクランプ" in w for w in r.quantity.warnings))

    def test_beam_heights_can_be_given(self):
        r = solve_all({**SPEC, "tie_source": "鉄骨", "steel_beam_heights_mm": [4000, 8000, 12000]})
        self.assertEqual(sorted({t.height_mm - 300 for t in r.model.wall_ties if t.kind == "grid"}), [4000, 8000, 12000])

    def test_bad_value_and_gdl(self):
        with self.assertRaises(InputError):
            solve_all({**SPEC, "tie_source": "木"})
        src = TIE_GDL.read_text(encoding="utf-8")
        self.assertIn("if steelD > 0.001 then wD = wD + steelD", src)
        self.assertIn("ビームクランプ", src)

    def test_form(self):
        from ashiba.spec_form import apply_form, form_fields
        from ashiba.spec_object import params_from_spec

        v = {f["key"]: f.get("value") for f in form_fields(SPEC) if f["key"]}
        new, _n = apply_form(SPEC, {**v, "tie": "鉄骨から（梁にビームクランプ）"})
        self.assertEqual(new["tie_source"], "鉄骨")
        self.assertEqual(params_from_spec(new)["tieSource"], "鉄骨")


if __name__ == "__main__":
    unittest.main()
