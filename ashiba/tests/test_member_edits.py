"""範囲を指定した部材の編集（参考: smartCON Planner の「一般部材編集」。升目・列・行で部材を外す・置き換える）."""

import re
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import GDL_ARRAY_CAP, face_drawn_counts, line_params
from ashiba.member_edits import cell_parts

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
        "series_id": "nikken_nd1800", "scaffold_width_mm": 914,
        "stairs": {"count": 1, "positions": [{"face": "北面", "start_mm": 3600}]}}
ROOT = Path(__file__).resolve().parents[1]


def _qty(r, model_no):
    return sum(l.qty for l in r.quantity.lines if l.part.model_no == model_no)


class TestRemove(unittest.TestCase):
    def setUp(self):
        self.base = solve_all(dict(RECT))

    def test_removing_decks_takes_them_off_the_quantity(self):
        r = solve_all({**RECT, "member_edits": [
            {"face": "南面", "spans": "2-3", "levels": "2-3", "parts": ["踏板"], "reason": "設備の搬入口"}]})
        south = r.model.plan.edges[0]
        per_cell = cell_parts(r.model, south, 1, 2, "踏板")
        self.assertTrue(per_cell)
        for part, n in per_cell:
            self.assertEqual(_qty(self.base, part.model_no) - _qty(r, part.model_no), 4 * n)
        self.assertTrue(any("部材編集" in n and "設備の搬入口" in n for n in r.quantity.notes))
        self.assertLess(r.quantity.total_weight_kg, self.base.quantity.total_weight_kg)

    def test_drawing_skips_the_same_cells(self):
        r = solve_all({**RECT, "member_edits": [
            {"face": "南面", "spans": "2-3", "levels": "2-3", "parts": ["踏板", "幅木"]}]})
        south = r.model.plan.edges[0]
        p = line_params(r.model, south)
        self.assertEqual(p["editList"], "2,3,2,3,5")
        c = face_drawn_counts(r.model, south, stair_plan=r.stair_plan, openings=r.openings)
        c0 = face_drawn_counts(self.base.model, self.base.model.plan.edges[0],
                               stair_plan=self.base.stair_plan, openings=self.base.openings)
        self.assertEqual(c0["qtyDeck"] - c["qtyDeck"], 4)
        self.assertEqual(c0["qtyToe"] - c["qtyToe"], 4)
        # 他の面は変わらない
        east = r.model.plan.edges[1]
        self.assertEqual(line_params(r.model, east)["editList"], "")

    def test_removing_rails_is_flagged_for_the_site(self):
        r = solve_all({**RECT, "member_edits": [{"face": "東面", "spans": 1, "parts": "手すり"}]})
        self.assertTrue(any("墜落" in w for w in r.quantity.warnings))

    def test_overlapping_edits_do_not_double_count(self):
        one = solve_all({**RECT, "member_edits": [{"face": "南面", "spans": "2-3", "levels": 2, "parts": "踏板"}]})
        two = solve_all({**RECT, "member_edits": [
            {"face": "南面", "spans": "2-3", "levels": 2, "parts": "踏板"},
            {"face": "南面", "spans": "3", "levels": 2, "parts": "床"}]})
        self.assertEqual([(l.part.model_no, l.qty) for l in one.quantity.lines],
                         [(l.part.model_no, l.qty) for l in two.quantity.lines])

    def test_stair_tower_decks_are_left_alone(self):
        north = next(e for e in self.base.model.plan.edges if e.edge_index == 2)
        t = self.base.stair_plan.towers[0]
        xs, x = [], 0
        for s in north.spans:
            xs.append(x)
            x += s
        i = next(k for k, v in enumerate(xs) if abs(v - t.start_mm) < 1) + 1
        r = solve_all({**RECT, "member_edits": [{"face": "北面", "spans": i, "levels": "全部", "parts": "踏板"}]})
        self.assertEqual([(l.part.model_no, l.qty) for l in r.quantity.lines],
                         [(l.part.model_no, l.qty) for l in self.base.quantity.lines])
        self.assertTrue(any("階段室の升目" in n for n in r.quantity.notes))

    def test_level_and_face_tables_still_add_up(self):
        from ashiba.level_quantity import take_off_by_face, take_off_by_level

        r = solve_all({**RECT, "member_edits": [{"face": "南面", "spans": "1-4", "levels": "1-2",
                                                 "parts": ["踏板", "幅木"]}]})
        kw = dict(stair_plan=r.stair_plan, openings=r.openings, platforms=r.platforms, terrain=r.terrain,
                  bracket_sections=r.brackets)
        lv = take_off_by_level(r.model, r.quantity, **kw)
        for row in lv.rows:
            total = sum(l.qty for l in r.quantity.lines
                        if (l.part.model_no, l.part.category) == (row.part.model_no, row.part.category))
            self.assertEqual(row.total, total, row.part.model_no)
        ft = take_off_by_face(r.model, r.quantity, **kw)
        deck = next(p for p, _ in cell_parts(r.model, r.model.plan.edges[0], 0, 1, "踏板"))
        f0 = next(v for p, v in ft.rows if p.model_no == deck.model_no and p.category == deck.category)
        f0b = next(v for p, v in take_off_by_face(self.base.model, self.base.quantity,
                                                   stair_plan=self.base.stair_plan).rows
                   if p.model_no == deck.model_no and p.category == deck.category)
        self.assertEqual(f0b[0] - f0[0], 8)
        self.assertEqual(f0b[1:], f0[1:])


class TestReplace(unittest.TestCase):
    def test_replace_moves_the_count_to_the_other_part(self):
        base = solve_all(dict(RECT))
        m = base.model.master
        east = base.model.plan.edges[1]
        src = m.find("布材", east.spans[0])
        dst = next(p for p in m.by_category("布材") if p.model_no != src.model_no)
        r = solve_all({**RECT, "member_edits": [
            {"face": "東面", "spans": 1, "levels": "全部", "parts": "外側手すり", "action": "置換",
             "to": dst.model_no}]})
        moved = _qty(base, src.model_no) - _qty(r, src.model_no)
        self.assertEqual(moved, 2 * r.model.elevation.n_levels)
        self.assertEqual(_qty(r, dst.model_no) - _qty(base, dst.model_no), moved)
        # 置換は図を変えない
        self.assertEqual(line_params(r.model, r.model.plan.edges[1])["editList"], "")


class TestInput(unittest.TestCase):
    def test_bad_items_become_warnings(self):
        r = solve_all({**RECT, "member_edits": [
            {"face": "南面", "spans": "99", "parts": "踏板"},
            {"face": "南面", "spans": 1, "parts": "屋根"},
            {"face": "南面", "spans": 1, "parts": "踏板", "action": "置換"}]})
        w = [x for x in r.model.plan.warnings if "部材編集" in x]
        self.assertEqual(len(w), 3)
        self.assertEqual([e for e in r.model.member_edits if not e.auto], [])   # ツールが入れる編集（渡りの出入口）は除く

    def test_unknown_key_is_rejected(self):
        from ashiba.cli import InputError

        with self.assertRaises(InputError):
            solve_all({**RECT, "member_edits": [{"face": "南面", "span": 1, "parts": "踏板"}]})


class TestFrame(unittest.TestCase):
    def test_frame_braces_both_faces(self):
        spec = {**RECT, "series_id": "waku"}
        spec.pop("stairs")
        base = solve_all(spec)
        r = solve_all({**spec, "member_edits": [{"face": "南面", "spans": 1, "levels": 1, "parts": "筋かい"}]})
        s = base.model.plan.edges[0].spans[0]
        brace = next(p for p in base.model.master.by_category("筋交") if p.nominal_dim == s)
        self.assertEqual(_qty(base, brace.model_no) - _qty(r, brace.model_no), 2)


class TestGdlSide(unittest.TestCase):
    def test_gdl_reads_as_many_records_as_python_sends(self):
        gdl = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        dims = {m.group(1): int(m.group(2)) for m in re.finditer(r"dim (\w+)\[(\d+)\]", gdl)}
        self.assertEqual(dims["edA"] * 5, GDL_ARRAY_CAP["editList"])
        self.assertIn(f"nEd < {dims['edA']} do", gdl)

    def test_every_bit_is_used_in_3d(self):
        gdl = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        for b in range(7):
            self.assertIn(f"bittest(edE[ie], {b})", gdl)


class TestSpecPart(unittest.TestCase):
    """足場条件の部品の「部材編集」ページ（1行に 面 スパン 層 部材）."""

    def test_text_round_trip(self):
        from ashiba.member_edits import format_edit_items, parse_edit_text

        items, errs = parse_edit_text("南面 2-3 2-3 踏板・幅木 #搬入口; 東面 1 手すり→NDT09S；辺2 全部 4 筋かい")
        self.assertEqual(errs, [])
        self.assertEqual(items[0], {"face": "南面", "spans": "2-3", "levels": "2-3", "parts": ["踏板", "幅木"],
                                    "reason": "搬入口"})
        self.assertEqual(items[1]["action"], "置換")
        self.assertEqual(items[1]["to"], "NDT09S")
        self.assertEqual(items[1]["levels"], "全部")
        self.assertEqual(items[2]["edge_index"], 2)
        again, _ = parse_edit_text("; ".join(format_edit_items(items)))
        self.assertEqual(again, items)

    def test_bad_line(self):
        from ashiba.member_edits import parse_edit_text

        items, errs = parse_edit_text("南面 踏板")
        self.assertEqual(items, [])
        self.assertEqual(len(errs), 1)

    def test_part_fields_drive_the_plan(self):
        from ashiba.spec_object import merge_object_into_spec, params_from_spec, spec_from_params

        spec = {**RECT, "member_edits": [{"face": "南面", "spans": "2-3", "levels": "2-3", "parts": ["踏板"]}]}
        params = params_from_spec(spec)
        self.assertEqual(params["memberEdit1"], "南面 2-3 2-3 踏板")
        self.assertEqual(params["memberEdit2"], "")
        obj = spec_from_params(params)
        self.assertEqual(len(obj["member_edits"]), 1)
        r = solve_all({**spec, "member_edits": obj["member_edits"]})
        self.assertEqual(len([e for e in r.model.member_edits if not e.auto]), 1)
        # 部品の欄を空にしたら、JSON の編集も効かない（部品が正）
        params["memberEdit1"] = ""
        merged = merge_object_into_spec(spec, spec_from_params(params))
        self.assertEqual(merged["member_edits"], [])

    def test_long_edits_spill_into_the_next_field(self):
        from ashiba.spec_object import params_from_spec

        items = [{"face": "南面", "spans": i, "levels": "全部", "parts": ["踏板", "幅木", "外側手すり"],
                  "reason": "設備の搬入口の仮設"} for i in range(1, 15)]
        p = params_from_spec({**RECT, "member_edits": items})
        self.assertTrue(p["memberEdit2"])
        self.assertTrue(all(len(p[f"memberEdit{i}"]) <= 250 for i in range(1, 5)))


class TestNarrowUpperLevels(unittest.TestCase):
    """上の層だけ床を狭める（内側の踏板を外す）。候補3「層ごとの幅の変更」."""

    def setUp(self):
        self.spec = {**RECT, "series_id": "shinwa_A"}
        self.base = solve_all(self.spec)
        self.widths = list(self.base.model.deck_widths_in_use)

    def test_inner_deck_only(self):
        if len(self.widths) < 2:
            self.skipTest("1枚敷きの系列")
        r = solve_all({**self.spec, "member_edits": [
            {"face": "南面", "spans": "全部", "levels": "3-全部".replace("全部", str(self.base.model.elevation.n_levels)),
             "parts": "内側踏板"}]})
        south = r.model.plan.edges[0]
        inner = cell_parts(r.model, south, 0, 3, "内側踏板")
        outer = cell_parts(r.model, south, 0, 3, "外側踏板")
        self.assertEqual(len(inner), 1)
        self.assertEqual(inner[0][0].nominal_dim, south.spans[0])
        self.assertIn(f"幅{self.widths[1]}", inner[0][0].note)
        removed = _qty(self.base, inner[0][0].model_no) - _qty(r, inner[0][0].model_no)
        self.assertGreater(removed, 0)
        if outer[0][0].model_no != inner[0][0].model_no:
            self.assertEqual(_qty(self.base, outer[0][0].model_no), _qty(r, outer[0][0].model_no))
        # 床はまだある（外側の踏板）ので図示本数の床は変わらない
        c = face_drawn_counts(r.model, south, stair_plan=r.stair_plan, openings=r.openings)
        c0 = face_drawn_counts(self.base.model, self.base.model.plan.edges[0],
                               stair_plan=self.base.stair_plan, openings=self.base.openings)
        self.assertEqual(c["qtyDeck"], c0["qtyDeck"])
        self.assertEqual(line_params(r.model, south)["editList"].split(",")[-1], "64")

    def test_both_sides_equal_the_whole_deck(self):
        whole = solve_all({**self.spec, "member_edits": [{"face": "南面", "spans": 2, "levels": 2, "parts": "踏板"}]})
        sides = solve_all({**self.spec, "member_edits": [
            {"face": "南面", "spans": 2, "levels": 2, "parts": "外側踏板"},
            {"face": "南面", "spans": 2, "levels": 2, "parts": ["内側の床", "踏板"]}]})
        self.assertEqual([(l.part.model_no, l.qty) for l in whole.quantity.lines],
                         [(l.part.model_no, l.qty) for l in sides.quantity.lines])
        south = whole.model.plan.edges[0]
        c1 = face_drawn_counts(whole.model, south, stair_plan=whole.stair_plan)
        c2 = face_drawn_counts(sides.model, sides.model.plan.edges[0], stair_plan=sides.stair_plan)
        self.assertEqual(c1["qtyDeck"], c2["qtyDeck"])


if __name__ == "__main__":
    unittest.main()
