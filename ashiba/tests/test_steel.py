"""鉄骨の建て方（節と重量表）のテスト."""

from __future__ import annotations

import math
import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.steel_erection import (Beam, Bracket, Column, ColumnPiece, Options, Zone, beam_params, cap_plate, column_params, diaphragms, plate_gap_notes, plate_weight, cut_heights, grid_names, make_steps, parse_section, piece_width,
                                   label_point, plan_pieces, schedule_tasks, shape_of, splice_of, table_rows, zone_at, zone_lines, zone_of)


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
        o = Options(every=1, extra=0.0, diaphragm="なし")
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


class TestDeckStage(unittest.TestCase):
    """デッキの状態と建て方の時点の判定（reports/デッキプレートの敷設時期.md）."""

    def rows(self, **kw):
        from ashiba.deck_stage import DeckOptions, floor_rows

        cols = [Column("C1", x, 0.0, z, z + 4000.0, 500.0, 500.0) for x in (0.0, 6000.0) for z in (0.0, 4000.0, 8000.0, 12000.0)]
        beams = [Beam("G1", (0.0, 0.0), (6000.0, 0.0), z - 250.0, 200.0, 500.0) for z in (4000.0, 8000.0, 12000.0, 16000.0)]
        p = plan_pieces(cols, beams, [0.0, 4000.0, 8000.0, 12000.0], SECS, Options(every=2))
        return floor_rows(make_steps(p, [], []), 0.0, DeckOptions(**kw), 6000.0)

    def at(self, rows, step, top):
        return next(r for r in rows if r.step == step and r.top == top)

    def test_undecided_gives_both_bounds(self):
        rows = self.rows()
        r = self.at(rows, 1, 8000.0)                                                # 1 節の上の階: 下の階にデッキがあるか未定
        self.assertEqual((r.h_low, r.h_high, r.stage), (4000.0, 8000.0, "0か1"))
        self.assertEqual(r.rope, "適用外")                                           # 下限で親綱
        self.assertIn("6.75m 超", r.harness)                                        # 上限で器具

    def test_lower_node_counts_after_the_lag(self):
        r = self.at(self.rows(), 2, 12000.0)                                        # 2 節を建てるとき、1 節の階は仮留め済み
        self.assertEqual((r.h_low, r.h_high), (4000.0, 4000.0))
        self.assertEqual(self.at(self.rows(), 2, 8000.0).stage, "2 仮留め済み")

    def test_floor_order(self):
        self.assertEqual(self.at(self.rows(floor_order="上から"), 1, 8000.0).h_low, 8000.0)
        self.assertEqual(self.at(self.rows(floor_order="下から"), 1, 8000.0).h_high, 4000.0)

    def test_work_floor_leaves_the_rope_check(self):
        rows = self.rows(done_node=1)
        self.assertEqual(self.at(rows, 2, 8000.0).rope, "対象外")
        self.assertEqual(self.at(self.rows(work_stage=2), 2, 8000.0).rope, "対象外")   # 仮留めで作業床に数える選択
        self.assertNotEqual(self.at(self.rows(), 2, 8000.0).rope, "対象外")

    def test_net_shows_the_short_side(self):
        from ashiba.deck_stage import net_note

        self.assertIn("空き 3.70m ＜ 5.10m", net_note(4000.0, 6000.0))
        self.assertIn("≧", net_note(8000.0, 6000.0))

    def test_lookup_for_the_lifeline_tool(self):
        from ashiba.deck_stage import lookup, to_records

        t = to_records(self.rows())
        self.assertEqual(lookup(t, 1, 8000.0), (4000.0, 8000.0))
        self.assertIsNone(lookup(t, 1, 5000.0))


class TestLongForm(unittest.TestCase):
    def test_form_scrolls_and_keeps_the_buttons(self):
        g = (SRC.parent / "tapir" / "spec_form.swift").read_text(encoding="utf-8")
        self.assertIn("NSScrollView", g)
        self.assertIn("root.addSubview(btn)", g)


class TestErectionSheet(unittest.TestCase):
    """建て方検討図（節ごと）."""

    def data(self):
        from ashiba.deck_stage import DeckOptions, floor_rows, to_records
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from steel_run import drawing_data, judge_pieces

        cols = [Column("C1", x, 0.0, z, z + 3000.0, 500.0, 500.0) for x in (0.0, 6000.0) for z in (0.0, 3000.0, 6000.0, 9000.0)]
        beams = [Beam("G1", (0.0, 0.0), (6000.0, 0.0), z - 250.0, 200.0, 500.0) for z in (3000.0, 6000.0, 9000.0, 12000.0)]
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        steps = make_steps(p, [], [])
        rows = floor_rows(steps, 0.0, DeckOptions(), 6000.0)
        d = drawing_data(p, steps, [("X1", 0.0), ("X2", 6000.0)], [("Y1", 0.0)], [], [], rows, to_records(rows))
        return d, judge_pieces

    def test_one_page_per_node(self):
        from ashiba.steel_sheets import build_html, page_list

        d, _j = self.data()
        pages = page_list(d)
        self.assertEqual([p[0] for p in pages], ["建て方検討図 1節", "建て方検討図 2節"])
        self.assertIn("工区のピース数", pages[0][2])
        self.assertIn("クレーンを選んで作ると", pages[0][2])
        self.assertEqual(build_html(d, "試験").count('class="page"'), 2)

    def test_crane_and_colors_are_drawn(self):
        from ashiba.steel_sheets import COLORS, page_list

        d, judge = self.data()
        d["crane"] = {"name": "25t", "x": 3000.0, "y": -8000.0}
        judge(d, lambda x, y, top, w, label="": {"res": "重すぎ" if top > 8000 else "揚重可能", "rated": 2.0, "radius": 9000.0})
        pages = page_list(d)
        self.assertIn(COLORS["揚重可能"], pages[0][2])
        self.assertIn(COLORS["重すぎ"], pages[1][2])
        self.assertNotIn("clip-path", pages[0][2])                                  # レイアウトの変換で枠の形に崩れた
        self.assertIn("作業半径 9.0m", pages[0][2])
        self.assertIn("一番重い", pages[0][2])

    def test_lower_node_is_grey(self):
        from ashiba.steel_sheets import page_list

        d, _j = self.data()
        self.assertNotIn("#d5d5d5", page_list(d)[0][2])
        self.assertIn("#d5d5d5", page_list(d)[1][2])


class TestNoColumns(unittest.TestCase):
    def test_no_column_above_the_base_stops_with_a_message(self):
        """基礎の柱だけが見えていると min() で止まった（実機 2026-11-07）."""
        self.assertEqual(plan_pieces([Column("C1", 0.0, 0.0, -3000.0, 0.0, 500.0, 500.0)], [], LEVELS, SECS, Options()).columns, [])
        g = (SRC.parent / "scripts" / "steel_run.py").read_text(encoding="utf-8")
        self.assertLess(g.index("if not plan.columns:"), g.index("zone_lines(a.zones"))


class TestGear(unittest.TestCase):
    """鉄骨建て方の仮設材（利用者の指定 2026-11-07）."""

    def gears(self):
        from ashiba.steel_gear import plan_gear

        cols = [Column("C1", x, y, z, z + 3000.0, 500.0, 500.0) for x in (0.0, 6000.0) for y in (0.0, 6000.0) for z in (0.0, 3000.0, 6000.0, 9000.0)]
        beams = [Beam("G1", (0.0, y), (6000.0, y), z - 250.0, 200.0, 500.0) for y in (0.0, 6000.0) for z in (3000.0, 6000.0, 9000.0, 12000.0)]
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        steps = make_steps(p, [], [])
        return plan_gear(p, steps, SECS, splice_of), steps

    def test_every_kind_has_its_layer(self):
        from ashiba.steel_gear import KINDS

        g, _s = self.gears()
        self.assertEqual({x.kind for x in g}, set(KINDS))
        self.assertEqual({x.layer for x in g if x.kind == 1}, {"鉄骨仮設_溶接足場"})

    def test_stage_only_at_the_joints(self):
        g, _s = self.gears()
        st = [x for x in g if x.kind == 1]
        self.assertEqual(len(st), 4)                                                 # 2 節なので継手は 1 段・柱 4 本
        self.assertEqual({x.z for x in st}, {7000.0 - 750.0})
        self.assertEqual(len([x for x in g if x.kind == 7]), 4)

    def test_lug_on_every_piece(self):
        g, _s = self.gears()
        self.assertEqual(len([x for x in g if x.kind == 6]), 8)

    def test_hanger_both_sides_of_each_joint(self):
        from ashiba.steel_gear import hanger_of

        self.assertEqual(hanger_of(405.0)[1], "NKH0714")
        self.assertEqual(hanger_of(700.0)[1], "NKH1014")
        g, _s = self.gears()
        hs = [x for x in g if x.kind == 2]
        self.assertEqual(len(hs), 2 * 2 * 8)                                         # 梁 8 本 × 端 2 × 両側 2
        self.assertEqual({x.params["sgS"] for x in hs}, {-1, 1})

    def test_ladders_reach_the_piece(self):
        from ashiba.steel_gear import ladders_for

        self.assertEqual([x[1] for x in ladders_for(6.7)], ["NKSTR40", "NKSTR20", "NKSTR10T"])
        self.assertEqual([x[1] for x in ladders_for(3.8)], ["NKSTR40"])

    def test_net_for_each_bay_and_floor(self):
        g, _s = self.gears()
        nets = [x for x in g if x.kind == 4]
        self.assertEqual(len(nets), 4)
        self.assertEqual(nets[0].params, {"sgX": 6.0, "sgY": 6.0})

    def split(self):
        from ashiba.steel_gear import plan_gear

        cols = [Column("C1", x, y, z, z + 3000.0, 500.0, 500.0) for x in (0.0, 6000.0, 12000.0) for y in (0.0, 6000.0) for z in (0.0, 3000.0, 6000.0, 9000.0)]
        beams = [Beam("G1", (a, y), (a + 6000.0, y), z - 250.0, 200.0, 500.0) for a in (0.0, 6000.0) for y in (0.0, 6000.0) for z in (3000.0, 6000.0, 9000.0)]
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        z = [Zone(1, "西工区", [(-1000.0, -1000.0), (3000.0, -1000.0), (3000.0, 7000.0), (-1000.0, 7000.0)]),
             Zone(2, "東工区", [(3000.0, -1000.0), (13000.0, -1000.0), (13000.0, 7000.0), (3000.0, 7000.0)])]
        steps = make_steps(p, [], [], "工区", z)
        return plan_gear(p, steps, SECS, splice_of), steps

    def test_gear_knows_its_zone(self):
        g, steps = self.split()
        by = {s.no: s.zone for s in steps}
        self.assertEqual({x.zone for x in g}, {1, 2})
        self.assertTrue(all(x.zone == by[x.step] for x in g))

    def test_order_is_the_largest_zone(self):
        from ashiba.steel_gear import order_rows

        g, _s = self.split()
        zones, rows = order_rows(g)
        self.assertEqual(zones, [1, 2])
        for _k, _name, n, need, _kg in rows:
            self.assertEqual(need, max(n.values()))
        self.assertLess(sum(r[3] for r in rows), len(g))                             # 延べ数より少ない

    def test_sheet_names_the_zones(self):
        from ashiba.steel_gear import to_sheet

        class Sh:
            rows: list = []

            def add_title(self, *a): pass
            def add_header(self, r): Sh.rows.append(r)
            def add(self, r): Sh.rows.append(r)
            def set_width(self, *a): pass

        class Wb:
            def sheet(self, name): return Sh()

        g, _s = self.split()
        to_sheet(Wb(), g, {1: "西工区", 2: "東工区"})
        self.assertEqual(Sh.rows[0], ["種類", "品名", "西工区", "東工区", "手配数", "手配の重量 kg"])

    def test_step_shows_only_its_zone(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from steel_run import set_gear

        class C:
            def set_gdl_parameters_many(self, pairs):
                self.on = [p[1]["sgOn"] for p in pairs]

        rec = {"steps": [{"no": 1, "zone": 1}, {"no": 2, "zone": 1}, {"no": 3, "zone": 2}],
               "gear": [{"guid": "a", "step": 1, "zone": 1}, {"guid": "b", "step": 2, "zone": 1}, {"guid": "c", "step": 3, "zone": 2}]}
        c = C()
        set_gear(c, rec, 1)
        self.assertEqual(c.on, [True, True, False])                                  # 工区の分は最初から全部
        set_gear(c, rec, 3)
        self.assertEqual(c.on, [False, False, True])                                 # 次の工区へ移した
        set_gear(c, rec, 0)
        self.assertEqual(c.on, [True, True, True])

    def test_old_record_keeps_the_step_rule(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from steel_run import set_gear

        class C:
            def set_gdl_parameters_many(self, pairs):
                self.on = [p[1]["sgOn"] for p in pairs]

        c = C()
        set_gear(c, {"gear": [{"guid": "a", "step": 1}, {"guid": "b", "step": 2}]}, 1)
        self.assertEqual(c.on, [True, False])

    def test_steps_gate_the_gear(self):
        g, steps = self.gears()
        self.assertEqual({x.step for x in g}, {s.no for s in steps})

    def test_part_draws_every_kind(self):
        t = (SRC.parent / "gdl" / "hsf" / "ashiba_sgear" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        for n in ("stage", "hanger", "ladder", "net", "block", "lug", "ep", "wire"):
            self.assertIn(f'"{n}":', t)
        self.assertIn("if sgOn = 0 then end", t)

    def test_angle_goes_to_tapir_in_radians(self):
        from ashiba.tapir_adapter import to_tapir_values

        self.assertAlmostEqual(to_tapir_values({"sgA": 90.0})["sgA"], math.pi / 2)


class TestBlankSection(unittest.TestCase):
    """断面が空でも箱にしない（利用者の報告 2026-11-07「ガセットプレートがでないHこうになってない」）."""

    def test_shape_without_a_section(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, {}, Options(every=1))
        c = next(c for c in p.columns if c.brackets)
        q = column_params(c, {}, Options())
        self.assertEqual(q["spT"], 2)                                                # 角形
        self.assertEqual(q["brT"].split(",")[0], "1")                               # ブラケットは H
        self.assertGreater(float(q["spwH"].split(",")[0]), 0)                       # 添え板が出る
        self.assertEqual(beam_params(p.beams[0], {})["spT"], 1)

    def test_blank_section_gives_no_weight(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, {}, Options())
        self.assertTrue(all(c.weight is None for c in p.columns))
        self.assertIn("仮の形", p.warnings[-1])

    def test_guess_keeps_the_size(self):
        s = shape_of("beam", 300.0, 500.0)
        self.assertEqual((s.kind, s.h, s.b), ("H", 500.0, 300.0))
        self.assertEqual(shape_of("column", 500.0, 500.0).kind, "BOX")


class TestTopPlate(unittest.TestCase):
    """最上節の柱頭の板（利用者の指摘 2026-11-07「最上部にもプレートいるのでは？」）."""

    def top(self, plan):
        return max(plan.columns, key=lambda c: (c.node, bool(c.brackets)))

    def test_only_the_top_node_has_it(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        last = max(c.node for c in p.columns)
        self.assertGreater(last, 1)
        self.assertTrue(all(c.top_plate == (c.node == last) for c in p.columns))
        self.assertTrue(column_params(self.top(p), SECS, Options())["capOn"])
        self.assertFalse(column_params(min(p.columns, key=lambda c: c.node), SECS, Options())["capOn"])

    def test_two_sizes_above_the_flange(self):
        c = parse_section("□-400×400×19")
        self.assertEqual(cap_plate(c, 16.0), (22.0, 25.0))
        self.assertEqual(cap_plate(c, 17.0), (22.0, 25.0))                           # 間の厚さは下の板から数える
        self.assertEqual(cap_plate(c, 13.0), (19.0, 25.0))
        self.assertEqual(cap_plate(parse_section("□-600×600×36"), 16.0), (36.0, 30.0))   # 柱の板厚より薄くしない
        self.assertEqual(cap_plate(parse_section("□-600×600×28"), 28.0), (36.0, 30.0))
        self.assertEqual(cap_plate(c), (25.0, 25.0))                                 # 梁なしは柱の板厚から

    def test_plate_adds_weight(self):
        p = plan_pieces([Column("C1", 0.0, 0.0, 0.0, 3000.0, 500.0, 500.0)], [], LEVELS, SECS, Options(extra=0))
        c = p.columns[0]
        self.assertTrue(c.base_plate and c.top_plate)
        s = SECS["C1"]
        want = s.weight(3000.0) + (700.0 ** 2 * 36.0 + 550.0 ** 2 * 28.0) * 7.85e-9   # 梁なし: 22 の 2 サイズ上は 28
        self.assertAlmostEqual(c.weight, want)

    def test_plate_centers_on_the_top_flange(self):
        s = parse_section("□-400×400×19")
        q = parse_section("H-500×200×10×16")
        c = ColumnPiece(2, "X1-Y1", 0.0, 0.0, 7000.0, 12000.0, ["C1"], 0.0, 400.0, 400.0,
                        [Bracket("G1", 0.0, 11750.0, 200.0, 1000.0, 200.0, 500.0)], top_plate=True)
        v = column_params(c, {"C1": s, "G1": q}, Options())
        self.assertAlmostEqual(v["capZ"], 5.0 - 0.008 + 0.011)                       # 上端 5.000 からフランジの中心へ下げ、板厚の半分を足す
        self.assertAlmostEqual(v["capT"], 0.022)


class TestDiaphragm(unittest.TestCase):
    """ダイアフラム（利用者の指定 2026-11-07「ダイアフラムもリサーチして追加できるようにしてちょ」）."""

    BOX = parse_section("□-400×400×19")
    G5 = parse_section("H-500×200×10×16")

    def piece(self, *beams, top=False):
        br = [Bracket(f"G{i}", 90.0 * i, z, 200.0, 1000.0, 200.0, 500.0) for i, (z, _q) in enumerate(beams)]
        return ColumnPiece(1, "X1-Y1", 0.0, 0.0, 0.0, 5000.0, ["C1"], 0.0, 400.0, 400.0, br, top_plate=top), [(b, q) for b, (_z, q) in zip(br, beams)]

    def test_two_through_plates_at_the_flanges(self):
        p, rows = self.piece((3000.0, self.G5))
        d = diaphragms(p, self.BOX, rows, Options())
        self.assertEqual([(x.z, x.t, x.kind) for x in d], [(2758.0, 22.0, 1), (3242.0, 22.0, 1)])

    def test_same_level_beams_share_one_plate(self):
        p, rows = self.piece((3000.0, self.G5), (3000.0, self.G5))
        self.assertEqual(len(diaphragms(p, self.BOX, rows, Options())), 2)

    def test_top_aligned_deeper_beam_makes_three(self):
        q = parse_section("H-600×200×11×17")
        p, rows = self.piece((3000.0, self.G5), (2950.0, q))
        d = diaphragms(p, self.BOX, rows, Options())
        self.assertEqual(len(d), 3)                                                  # 上は 1 枚、下は 2 枚
        notes = plate_gap_notes(p, self.BOX, rows, d)
        self.assertIn("100mm 未満", notes[0][1])

    def test_gap_of_150_to_200_is_a_soft_note(self):
        q = parse_section("H-700×200×13×24")
        p, rows = self.piece((3000.0, self.G5), (2900.0, q))
        notes = plate_gap_notes(p, self.BOX, rows, diaphragms(p, self.BOX, rows, Options()))
        self.assertEqual(len(notes), 1)
        self.assertIn("150mm 未満" if notes[0][0] < 150.0 else "内法が短い", notes[0][1])

    def test_overlapping_plates_become_one(self):
        q = parse_section("H-588×300×12×20")
        r = parse_section("H-600×200×11×17")
        p, rows = self.piece((3000.0, q), (2994.0, r))                               # 天端を揃えた H-588 と H-600
        d = diaphragms(p, self.BOX, rows, Options())
        self.assertEqual(len(d), 2)
        self.assertGreaterEqual(d[0].t, 28.0)                                        # 下は 32mm 近い帯を 1 枚で受ける
        self.assertEqual(plate_gap_notes(p, self.BOX, rows, d), [])

    def test_stiffener_is_never_thinner_than_the_flange(self):
        col = parse_section("H-400×400×13×21")
        p, rows = self.piece((3000.0, parse_section("H-500×200×10×13")))
        self.assertEqual(diaphragms(p, col, rows, Options())[0].t, 16.0)

    def test_h_column_gets_stiffeners(self):
        col = parse_section("H-400×400×13×21")
        p, rows = self.piece((3000.0, self.G5))
        d = diaphragms(p, col, rows, Options())
        self.assertEqual({(x.t, x.kind) for x in d}, {(16.0, 3)})                    # 梁フランジ厚以上
        self.assertAlmostEqual(plate_weight(d[0], col), (400 - 42) * (400 - 13) * 16 * 7.85e-9)
        self.assertEqual(plate_gap_notes(p, col, rows, d), [])

    def test_inner_and_none(self):
        p, rows = self.piece((3000.0, self.G5))
        d = diaphragms(p, self.BOX, rows, Options(diaphragm="内"))
        self.assertEqual({(x.t, x.kind) for x in d}, {(19.0, 2)})                    # 1 サイズ上
        self.assertEqual(diaphragms(p, self.BOX, rows, Options(diaphragm="なし")), [])
        v = column_params(p, {"C1": self.BOX, "G0": self.G5}, Options(diaphragm="なし"))
        self.assertEqual((v["dpK"], v["dpZ"]), (0, ""))

    def test_pipe_is_through_and_round(self):
        col = parse_section("P-318.5×10")
        p, rows = self.piece((3000.0, self.G5))
        d = diaphragms(p, col, rows, Options())
        self.assertEqual(d[0].kind, 1)
        self.assertAlmostEqual(plate_weight(d[0], col), 3.14159265 * (159.25 + 25) ** 2 * 22 * 7.85e-9, 5)

    def test_top_plate_is_not_doubled(self):
        p, rows = self.piece((4750.0, self.G5), top=True)
        d = diaphragms(p, self.BOX, rows, Options())
        self.assertEqual([x.z for x in d], [4508.0])                                 # 下のフランジだけ

    def test_params_and_weight(self):
        cols = [Column("C1", 0.0, 0.0, 0.0, 6000.0, 400.0, 400.0)]
        beams = [Beam("G1", (0.0, 0.0), (6000.0, 0.0), 3000.0, 200.0, 500.0)]
        secs = {"C1": self.BOX, "G1": self.G5}
        a = plan_pieces(cols, beams, LEVELS, secs, Options()).columns[0]
        b = plan_pieces(cols, beams, LEVELS, secs, Options(diaphragm="なし")).columns[0]
        self.assertEqual(column_params(a, secs, Options())["dpT"], "22,22")
        self.assertAlmostEqual(a.weight - b.weight, 2 * 450.0 ** 2 * 22.0 * 7.85e-9 * 1.05)


class TestZones(unittest.TestCase):
    """ゾーンで工区を分ける（利用者の指定 2026-11-07「ゾーンで工区区切るのはどう？」）."""

    L = [(0.0, 0.0), (20000.0, 0.0), (20000.0, 10000.0), (10000.0, 10000.0), (10000.0, 20000.0), (0.0, 20000.0)]

    def test_inside_l_shape(self):
        z = [Zone(1, "1工区", self.L)]
        self.assertEqual(zone_at((5000.0, 15000.0), z), 1)
        self.assertEqual(zone_at((15000.0, 15000.0), z), 2)                          # 欠けた所は工区なし

    def test_label_stays_inside_an_l_shape(self):
        p = label_point(self.L)
        self.assertEqual(zone_at(p, [Zone(1, "1工区", self.L)], 0.0), 1)
        self.assertNotEqual(p, (10000.0, 10000.0))                                   # 入隅に乗らない

    def test_on_the_line_goes_to_the_smaller_number(self):
        a = Zone(1, "1工区", [(0.0, 0.0), (6000.0, 0.0), (6000.0, 9000.0), (0.0, 9000.0)])
        b = Zone(2, "2工区", [(6000.0, 0.0), (12000.0, 0.0), (12000.0, 9000.0), (6000.0, 9000.0)])
        self.assertEqual(zone_at((6000.0, 4500.0), [a, b]), 1)
        self.assertEqual(zone_at((9000.0, 4500.0), [a, b]), 2)

    def test_steps_follow_the_zones(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        a = Zone(1, "A工区", [(-1000.0, -1000.0), (3000.0, -1000.0), (3000.0, 1000.0), (-1000.0, 1000.0)])
        b = Zone(2, "B工区", [(3000.0, -1000.0), (7000.0, -1000.0), (7000.0, 1000.0), (3000.0, 1000.0)])
        steps = make_steps(p, [], [], "工区", [a, b])
        self.assertEqual(steps[0].name, "A工区 1節")
        self.assertEqual({s.zone_name for s in steps}, {"A工区", "B工区"})

    def test_piece_outside_is_warned(self):
        cols, beams = frame()
        p = plan_pieces(cols, beams, LEVELS, SECS, Options())
        a = Zone(1, "A工区", [(-1000.0, -1000.0), (1000.0, -1000.0), (1000.0, 1000.0), (-1000.0, 1000.0)])
        steps = make_steps(p, [], [], "工区", [a])
        self.assertIn("工区なし", {s.zone_name for s in steps})
        self.assertTrue(any("入らないピース" in w for w in p.warnings))

    def test_only_zones_named_koku_are_used(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from steel_run import zones_of

        class C:
            def tapir(self, cmd, body):
                return {"elements": [1, 2]}

            def get_details(self, es):
                ring = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 0}]
                return [{"details": {"name": "事務室", "numberStr": "1", "polygonOutline": ring}},
                        {"details": {"name": "2工区", "numberStr": "10", "polygonOutline": ring}},
                        {"details": {"name": "西工区", "numberStr": "9", "polygonOutline": ring}}]

        z = zones_of(C())
        self.assertEqual([(x.no, x.name, len(x.outline)) for x in z], [(1, "西工区", 3), (2, "2工区", 3)])   # 番号の順（10 は 9 の後）


class TestSheet(unittest.TestCase):
    def test_lift_check_reads_the_piece(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from crane_check import lift_targets

        pool = [({"elementId": {"guid": "p"}}, {"type": "Object", "details": {"libPart": {"name": "ashiba_steel_1"}}})]
        self.assertEqual(len(lift_targets(pool, "", set())), 1)


if __name__ == "__main__":
    unittest.main()
