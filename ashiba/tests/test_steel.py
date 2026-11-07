"""鉄骨の建て方（節と重量表）のテスト."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.steel_erection import Beam, Column, Options, column_params, cut_heights, grid_names, parse_section, plan_pieces, table_rows


def frame(mark="C1"):
    cols = [Column(mark, x, 0.0, z, z + 3000.0, 500.0, 500.0) for x in (0.0, 6000.0) for z in (0.0, 3000.0, 6000.0, 9000.0)]
    beams = [Beam("G1", (0.0, 0.0), (6000.0, 0.0), z - 250.0, 200.0, 500.0) for z in (3000.0, 6000.0, 9000.0, 12000.0)]
    return cols, beams


SECS = {"C1": parse_section("□-500×500×22"), "G1": parse_section("H-500×200×10×16")}
LEVELS = [0.0, 3000.0, 6000.0, 9000.0]


class TestSection(unittest.TestCase):
    def test_area(self):
        self.assertAlmostEqual(parse_section("H-500×200×10×16").area, 2 * 200 * 16 + 468 * 10)
        self.assertAlmostEqual(parse_section("□-500×500×22").area, 2 * 22 * 956)
        self.assertEqual(parse_section("□-400×19").b, 400)
        self.assertEqual(parse_section("BH-600x250x12x25").kind, "H")
        self.assertEqual(parse_section("P-318.5×10").kind, "PIPE")

    def test_unreadable(self):
        self.assertIsNone(parse_section(""))
        self.assertIsNone(parse_section("H-500×200"))


class TestPieces(unittest.TestCase):
    def test_cut_at_floor_plus_1m(self):
        self.assertEqual(cut_heights(LEVELS, 0.0, 12000.0, Options()), [4000.0, 7000.0, 10000.0])
        self.assertEqual(cut_heights(LEVELS, 0.0, 12000.0, Options(every=2)), [7000.0])
        self.assertEqual(cut_heights(LEVELS, 0.0, 10300.0, Options()), [4000.0, 7000.0])         # 上端のすぐ下は切らない
        self.assertEqual(cut_heights([0.0, 3000.0, 6000.0, 9000.0, 9700.0], 0.0, 12000.0, Options()), [4000.0, 7000.0, 10000.0])   # 短い階では切らない

    def test_beam_is_cut_from_the_column_center(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        self.assertEqual(len(p.columns), 8)
        self.assertEqual({b.length for b in p.beams}, {4000.0})
        self.assertEqual(p.beams[0].x, 1000.0)
        br = next(c for c in p.columns if c.node == 1 and c.x == 0.0).brackets
        self.assertEqual([(b.ang, b.start, b.end) for b in br], [(0.0, 250.0, 1000.0)])        # 3m の梁は 4m の切り目より下の 1 節に

    def test_weight_has_bracket_gusset_and_base_plate(self):
        cols, beams = frame()
        o = Options(extra=0.0)
        p = plan_pieces(cols, beams, LEVELS, SECS, o)
        c = next(c for c in p.columns if c.node == 1 and c.x == 0.0)
        col = SECS["C1"].weight(4000.0)
        br = SECS["G1"].weight(750.0)
        gp = (500 - 32 - 40) * 300 * 12 * 7.85e-9
        bp = 700 * 700 * 36 * 7.85e-9
        self.assertAlmostEqual(c.weight, col + br + gp + bp)

    def test_missing_section_gives_no_weight(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, {"G1": SECS["G1"]}, Options())
        self.assertTrue(all(c.weight is None for c in p.columns))
        self.assertIn("C1", p.warnings[-1])

    def test_table_has_the_four_columns(self):
        cols, beams = frame()
        rows = table_rows(plan_pieces(cols, beams, LEVELS, SECS, Options(), [("A", 0.0), ("B", 6000.0)], [("1", 0.0)]))
        self.assertEqual(rows[0][:3], ("1節", "A-1", "C1"))
        self.assertEqual(rows[-1][:3], ("4節", "B-1", "C1"))

    def test_grid_falls_back_to_order(self):
        self.assertEqual(grid_names([(0.0, 0.0), (6000.0, 0.0)], [], []), {(0.0, 0.0): "X1-Y1", (6000.0, 0.0): "X2-Y1"})

    def test_part_gets_the_brackets(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        c = next(c for c in p.columns if c.node == 1 and c.x == 6000.0)
        q = column_params(c, SECS, Options())
        self.assertEqual(q["brA"], "180.0")
        self.assertEqual(q["brZ"], "2750")
        self.assertTrue(q["bpOn"])


class TestSheet(unittest.TestCase):
    def test_lift_check_reads_the_piece(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from crane_check import lift_targets

        pool = [({"elementId": {"guid": "p"}}, {"type": "Object", "details": {"libPart": {"name": "ashiba_steel_1"}}})]
        self.assertEqual(len(lift_targets(pool, "", set())), 1)


if __name__ == "__main__":
    unittest.main()
