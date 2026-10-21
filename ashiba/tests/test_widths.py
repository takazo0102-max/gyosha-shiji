"""足場の幅を始めに選ぶ（センチとインチ。利用者の指定 2026-10-22）."""

import os
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.widths import WIDTH_CHOICES, apply_width_choice, find_choice, needs_width_choice, ordered_choices

BASE = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}


class TestWidths(unittest.TestCase):
    def test_choices_in_cm_and_inch(self):
        self.assertEqual([c.width_mm for c in WIDTH_CHOICES], [600, 900, 1200, 610, 914, 1219])
        self.assertTrue(all("cm" in c.label for c in WIDTH_CHOICES if c.module == "metric"))
        self.assertTrue(all("インチ" in c.label for c in WIDTH_CHOICES if c.module == "inch"))
        for text, mm in (("90cm", 900), ("914", 914), ("36in", 914), ("3ft", 914), ("36インチ", 914),
                         ("2フィート", 610), ("1200mm", 1200), ("60cm（600mm）", 600)):
            self.assertEqual(find_choice(text).width_mm, mm, text)
        self.assertIsNone(find_choice(""))
        self.assertIsNone(find_choice("幅広"))

    def test_order_follows_current_module(self):
        self.assertEqual(ordered_choices({"module": "inch"})[0].module, "inch")
        self.assertEqual(ordered_choices({"series_id": "shinwa_A"})[0].module, "metric")

    def test_which_buildings_ask(self):
        self.assertTrue(needs_width_choice(BASE))
        self.assertFalse(needs_width_choice({**BASE, "scaffold_width_mm": 900}))
        self.assertFalse(needs_width_choice({**BASE, "deck_widths": [400, 250]}))
        self.assertFalse(needs_width_choice({**BASE, "scaffold_form": "単管抱き足場"}))
        self.assertFalse(needs_width_choice({**BASE, "scaffold_form": "ブラケット足場", "bracket_post": "単管"}))
        self.assertFalse(needs_width_choice({**BASE, "series_id": "waku"}))

    def test_inch_choice_switches_module_and_series(self):
        spec, notes = apply_width_choice({**BASE, "series_id": "shinwa_A", "module": "metric"}, find_choice("3ft"))
        self.assertEqual(spec["module"], "inch")
        self.assertNotIn("series_id", spec)                              # インチ系の既定の系列にする
        self.assertEqual(spec["scaffold_width_mm"], 914)
        m = solve_all(spec).model
        self.assertEqual(m.master.series_id, "nikken_nd1800")
        self.assertEqual(m.post_row_spacing_mm, 914)
        self.assertTrue(any("インチ" in n for n in notes))
        # 同じ系なら系列はそのまま
        spec2, _ = apply_width_choice({**BASE, "series_id": "shinwa_A"}, find_choice("120cm"))
        self.assertEqual(spec2["series_id"], "shinwa_A")
        self.assertEqual(solve_all(spec2).model.post_row_spacing_mm, 1200)

    def test_run_from_archicad_hook_without_dialog(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import run_from_archicad as tb

        os.environ["ASHIBA_WIDTH"] = "36in"
        try:
            out = tb.choose_width_at_start(None, {**BASE, "module": "metric"}, interactive=False, persist=False)
        finally:
            del os.environ["ASHIBA_WIDTH"]
        self.assertEqual((out["scaffold_width_mm"], out["module"]), (914, "inch"))
        # 幅が決まっている建物は聞かない（そのまま）
        same = tb.choose_width_at_start(None, {**BASE, "scaffold_width_mm": 600}, interactive=True, persist=False)
        self.assertEqual(same["scaffold_width_mm"], 600)


if __name__ == "__main__":
    unittest.main()
