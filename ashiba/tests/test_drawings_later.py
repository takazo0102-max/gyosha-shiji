"""立面図・断面図は最後に調整してから作る・断面は線で好きなところ（利用者の指定 2026-10-24）."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.cross_sections import cross_section_specs, split_cross_specs
from ashiba.tapir_features import choose_elevation_mode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = {"project_name": "a", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "module": "inch"}


class TestDrawingsLater(unittest.TestCase):
    def test_later_is_a_mode(self):
        self.assertEqual(choose_elevation_mode("later", "1.7.0")[0], "later")

    def test_placement_defers_the_drawings(self):
        src = (ROOT / "scripts" / "run_from_archicad.py").read_text(encoding="utf-8")
        self.assertIn("def make_drawings(", src)
        self.assertIn('req = "later"', src)
        self.assertIn('if req == "each":', src)

    def test_palette_button(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("図面を作る", [a.title for a in ACTIONS])
        self.assertIn("図面を作る", dict(PANEL_GROUPS)["見る・出す（足場用）"])
        self.assertTrue((ROOT / "scripts" / "drawings_run.py").exists())


class TestSectionByLine(unittest.TestCase):
    def test_drawn_lines_become_the_cuts(self):
        cuts = [[[5000, -5000], [5000, 15000]], [[-5000, 4000], [30000, 4000]], [[12000, -4000], [12000, -100]]]
        r = solve_all({**SPEC, "cross_cuts_mm": cuts})
        specs = cross_section_specs(r.model, "a")
        self.assertEqual([s.face_name for s in specs], ["A-A", "B-B", "C-C"])
        self.assertEqual(specs[0].start_mm, (5000.0, -5000.0))           # 引いた向きのまま
        faces = [s.face_name for s in split_cross_specs(r.model, specs)]
        self.assertIn("A-A 南面", faces)
        self.assertIn("A-A 北面", faces)
        self.assertIn("B-B 西面", faces)
        self.assertEqual([f for f in faces if f.startswith("C-C")], ["C-C 南面"])   # 南の足場だけ横切る短い線

    def test_without_lines_it_is_automatic(self):
        r = solve_all(SPEC)
        self.assertEqual([s.face_name for s in cross_section_specs(r.model, "a")], ["A-A", "B-B"])

    def test_cuts_from_guides(self):
        from drawings_run import cuts_of

        g = [(None, [((0.0, 0.0), (1.0, 2.0)), ((1.0, 2.0), (3.0, 4.0))])]
        self.assertEqual(cuts_of(g), [[[0.0, 0.0], [1.0, 2.0]], [[1.0, 2.0], [3.0, 4.0]]])


if __name__ == "__main__":
    unittest.main()
