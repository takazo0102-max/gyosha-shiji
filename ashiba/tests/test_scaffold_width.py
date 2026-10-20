"""足場の幅を 600・900 から選ぶ（利用者の指定 2026-10-20）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.master import load_master

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000}


class TestWidthSetup(unittest.TestCase):
    def test_nikken(self):
        m = load_master("nikken_nd1800")
        self.assertEqual(m.width_setup(600), (610, (500,)))
        self.assertEqual(m.width_setup(900), (914, (500, 240)))

    def test_shinwa_keeps_the_usual_pair_for_600(self):
        m = load_master("shinwa_A")
        self.assertEqual(m.width_setup(600), (600, (400, 250)))
        self.assertEqual(m.width_setup(900)[0], 900)

    def test_model_uses_the_width(self):
        for w, row in ((600, 610), (900, 914)):
            with self.subTest(w=w):
                r = solve_all({**RECT, "series_id": "nikken_nd1800", "scaffold_width_mm": w})
                self.assertEqual(r.model.post_row_spacing_mm, row)
                self.assertLessEqual(r.model.deck_width_total, row + 70)

    def test_deck_widths_win(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800", "scaffold_width_mm": 900, "deck_widths": [500]})
        self.assertEqual(r.model.post_row_spacing_mm, 914)
        self.assertEqual(r.model.deck_widths_in_use, (500,))

    def test_spec_object_round_trip(self):
        from ashiba.spec_object import params_from_spec, spec_from_params

        self.assertEqual(params_from_spec({"scaffold_width_mm": 900})["scaffW"], 900)
        self.assertEqual(spec_from_params({"scaffW": 600})["scaffold_width_mm"], 600)
        self.assertNotIn("scaffold_width_mm", spec_from_params({"scaffW": 0}))


if __name__ == "__main__":
    unittest.main()


class TestDefaultDecksFitTheRows(unittest.TestCase):
    def test_nikken_default_deck_does_not_stick_out(self):
        """日建の既定 500＋240（760）は建地列の間隔 610 に収まらず、内側の板がはみ出していた（利用者の指摘 2026-10-20）."""
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        self.assertEqual(r.model.post_row_spacing_mm, 610)
        self.assertEqual(r.model.deck_widths_in_use, (500,))
        self.assertLessEqual(r.model.deck_width_total, r.model.post_row_spacing_mm + 70)
