"""鉄骨の建て方（節と重量表）のテスト."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.steel_erection import (Beam, Column, Options, column_params, cut_heights, grid_names, make_steps, parse_section, piece_width, plan_pieces,
                                   schedule_tasks, splice_of, table_rows, zone_lines, zone_of)


def frame(mark="C1"):
    cols = [Column(mark, x, 0.0, z, z + 3000.0, 500.0, 500.0) for x in (0.0, 6000.0) for z in (0.0, 3000.0, 6000.0, 9000.0)]
    beams = [Beam("G1", (0.0, 0.0), (6000.0, 0.0), z - 250.0, 200.0, 500.0) for z in (3000.0, 6000.0, 9000.0, 12000.0)]
    return cols, beams


SECS = {"C1": parse_section("□-500×500×22"), "G1": parse_section("H-500×200×10×16")}
LEVELS = [0.0, 3000.0, 6000.0, 9000.0]


class TestSection(unittest.TestCase):
    def test_area(self):
        self.assertAlmostEqual(parse_section("H-500×200×10×16").area, 2 * 200 * 16 + 468 * 10 + 0.858 * 13 ** 2)
        self.assertAlmostEqual(parse_section("H-400×200×8×13").area / 100, 83.37, 1)             # 日本製鉄のカタログの値
        self.assertAlmostEqual(parse_section("BH-500×200×10×16").area, 2 * 200 * 16 + 468 * 10)  # 溶接組立はフィレットなし
        self.assertAlmostEqual(parse_section("□-500×500×22").area, 2 * 22 * 956)
        self.assertEqual(parse_section("□-400×19").b, 400)
        self.assertEqual(parse_section("BH-600x250x12x25").kind, "H")
        self.assertEqual(parse_section("P-318.5×10").kind, "PIPE")

    def test_unreadable(self):
        self.assertIsNone(parse_section(""))
        self.assertIsNone(parse_section("H-500×200"))


class TestPieces(unittest.TestCase):
    def test_cut_at_floor_plus_1m(self):
        self.assertEqual(cut_heights(LEVELS, 0.0, 12000.0, Options()), [7000.0])                 # 既定は 2 階で 1 節
        self.assertEqual(cut_heights(LEVELS, 0.0, 12000.0, Options(every=1)), [4000.0, 7000.0, 10000.0])
        self.assertEqual(cut_heights(LEVELS, 0.0, 10300.0, Options(every=1)), [4000.0, 7000.0])  # 上端のすぐ下は切らない
        self.assertEqual(cut_heights([0.0, 3000.0, 6000.0, 9000.0, 9700.0], 0.0, 12000.0, Options(every=1)), [4000.0, 7000.0, 10000.0])   # 短い階では切らない

    def test_beam_is_cut_from_the_column_center(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options(every=1))
        self.assertEqual(len(p.columns), 8)
        self.assertEqual({b.length for b in p.beams}, {4000.0})
        self.assertEqual(p.beams[0].x, 1000.0)
        br = next(c for c in p.columns if c.node == 1 and c.x == 0.0).brackets
        self.assertEqual([(b.ang, b.start, b.end) for b in br], [(0.0, 250.0, 1000.0)])        # 3m の梁は 4m の切り目より下の 1 節に

    def test_weight_has_bracket_splice_and_base_plate(self):
        cols, beams = frame()
        o = Options(every=1, extra=0.0)
        p = plan_pieces(cols, beams, LEVELS, SECS, o)
        c = next(c for c in p.columns if c.node == 1 and c.x == 0.0)
        col = SECS["C1"].weight(4000.0)
        br = SECS["G1"].weight(750.0)
        sp = splice_of(SECS["G1"]).weight
        bp = 700 * 700 * 36 * 7.85e-9
        self.assertAlmostEqual(c.weight, col + br + sp + bp)

    def test_missing_section_gives_no_weight(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, {"G1": SECS["G1"]}, Options())
        self.assertTrue(all(c.weight is None for c in p.columns))
        self.assertIn("C1", p.warnings[-1])

    def test_table_has_the_four_columns(self):
        cols, beams = frame()
        rows = table_rows(plan_pieces(cols, beams, LEVELS, SECS, Options(every=1), [("A", 0.0), ("B", 6000.0)], [("1", 0.0)]))
        self.assertEqual(rows[0][:3], ("1節", "A-1", "C1"))
        self.assertEqual(rows[-1][:3], ("4節", "B-1", "C1"))

    def test_grid_falls_back_to_order(self):
        self.assertEqual(grid_names([(0.0, 0.0), (6000.0, 0.0)], [], []), {(0.0, 0.0): "X1-Y1", (6000.0, 0.0): "X2-Y1"})

    def test_part_gets_the_brackets(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options(every=1))
        c = next(c for c in p.columns if c.node == 1 and c.x == 6000.0)
        q = column_params(c, SECS, Options())
        self.assertEqual(q["brA"], "180.0")
        self.assertEqual(q["brZ"], "2750")
        self.assertTrue(q["bpOn"])
        self.assertEqual((q["spwT"], q["spwH"], q["spwW"], q["spoL"]), ("9", "350", "165", "405"))


class TestSplice(unittest.TestCase):
    """継手の添え板一式（reports/ガセットプレートの実務と標準値.md）."""

    def test_table_value_and_weight(self):
        sp = splice_of(parse_section("H-400×200×8×13"))
        self.assertTrue(sp.listed)
        self.assertEqual((sp.web_t, sp.web_h, sp.web_w), (9, 260, 165))
        self.assertAlmostEqual(sp.weight * 1000, 27.9, 1)                                         # 1 か所 27.9kg

    def test_unlisted_section_is_marked(self):
        cols, _b = frame()
        beams = [Beam("G9", (0.0, 0.0), (6000.0, 0.0), 2750.0, 200.0, 500.0)]
        sec = {**SECS, "G9": parse_section("H-488×300×11×18")}
        self.assertFalse(splice_of(sec["G9"]).listed)
        p = plan_pieces(cols, beams, LEVELS, sec, Options())
        self.assertTrue(any("継手表に無い" in w for w in p.warnings))

    def test_box_beam_has_no_splice(self):
        self.assertIsNone(splice_of(parse_section("□-300×12")))


class TestWarnings(unittest.TestCase):
    def test_long_node_and_wide_bracket(self):
        cols = [Column("C1", 0.0, 0.0, 0.0, 20000.0, 500.0, 500.0)]
        beams = [Beam("G1", (-6000.0, 0.0), (6000.0, 0.0), 2750.0, 200.0, 500.0)]
        p = plan_pieces(cols, beams, [0.0, 3000.0, 15000.0], SECS, Options(bracket=1300.0))
        self.assertTrue(any("12m を超え" in w for w in p.warnings))
        self.assertTrue(any("全幅" in w for w in p.warnings))
        self.assertEqual(piece_width(p.columns[0]), 2600.0)


class TestSteps(unittest.TestCase):
    """工区ごと・節ごとのステップとピース数・工程表（利用者の指定 2026-11-07）."""

    def plan(self, every=1):
        cols = [Column("C1", x, 0.0, z, z + 3000.0, 500.0, 500.0) for x in (0.0, 6000.0, 12000.0) for z in (0.0, 3000.0, 6000.0, 9000.0)]
        beams = [Beam("G1", (x, 0.0), (x + 6000.0, 0.0), z - 250.0, 200.0, 500.0) for x in (0.0, 6000.0) for z in (3000.0, 6000.0, 9000.0, 12000.0)]
        return plan_pieces(cols, beams, LEVELS, SECS, Options(every=every))

    def test_zone_boundary(self):
        self.assertEqual([zone_of(x, 0.0, [6000.0], []) for x in (0.0, 6000.0, 12000.0)], [1, 1, 2])
        self.assertEqual(zone_of(9000.0, 9000.0, [6000.0], [4500.0]), 4)

    def test_zone_lines_by_name(self):
        pts = [(0.0, 0.0), (6000.0, 0.0), (6000.0, 4500.0)]
        self.assertEqual(zone_lines("X2", pts), ([6000.0], [], []))
        self.assertEqual(zone_lines("Y1, Z9", pts), ([], [0.0], ["Z9"]))
        self.assertEqual(zone_lines("B", pts, [("A", 0.0), ("B", 6000.0)], []), ([6000.0], [], []))

    def test_order_by_zone_and_by_node(self):
        p = self.plan()
        by_zone = make_steps(p, [6000.0], [], "工区")
        self.assertEqual([(s.zone, s.node) for s in by_zone[:5]], [(1, 1), (1, 2), (1, 3), (1, 4), (2, 1)])
        by_node = make_steps(p, [6000.0], [], "節")
        self.assertEqual([(s.zone, s.node) for s in by_node[:3]], [(1, 1), (2, 1), (1, 2)])

    def test_every_piece_is_in_one_step(self):
        p = self.plan()
        steps = make_steps(p, [6000.0], [])
        self.assertEqual(sum(s.pieces for s in steps), len(p.columns) + len(p.beams))
        self.assertEqual(steps[0].name, "1工区 1節")
        self.assertEqual((len(steps[0].columns), len(steps[0].beams)), (2, 1))

    def test_beam_goes_to_the_node_of_its_column(self):
        p = self.plan(every=2)
        steps = make_steps(p, [], [])
        self.assertEqual({b.node for b in steps[0].beams}, {1})
        self.assertEqual(sum(len(s.beams) for s in steps), 8)

    def test_schedule_days_and_order(self):
        steps = make_steps(self.plan(), [6000.0], [])
        tasks = schedule_tasks(steps, 2.0, 1)
        self.assertEqual(tasks[0].days, 2)                                          # 3 ピース ÷ 2
        self.assertEqual(tasks[1].deps[0].key, "steel1")
        self.assertEqual(schedule_tasks(steps, 2.0, 2)[0].days, 1)

    def test_step_layers_show_up_to_the_step(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from steel_run import visible_at

        steps = [{"no": 1, "layer": "a"}, {"no": 2, "layer": "b"}, {"no": 3, "layer": "c"}]
        self.assertEqual(visible_at(steps, 2), {"a": False, "b": False, "c": True})
        self.assertEqual(visible_at(steps, 0), {"a": False, "b": False, "c": False})


class TestSheet(unittest.TestCase):
    def test_lift_check_reads_the_piece(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from crane_check import lift_targets

        pool = [({"elementId": {"guid": "p"}}, {"type": "Object", "details": {"libPart": {"name": "ashiba_steel_1"}}})]
        self.assertEqual(len(lift_targets(pool, "", set())), 1)


if __name__ == "__main__":
    unittest.main()
