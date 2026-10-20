"""階段の外付け（3列）（利用者の指摘 2026-10-20: 敷地が広いところは階段を3列で横に付けるパターンが多い）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import face_drawn_counts, line_params

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
        "series_id": "nikken_nd1800"}


def _qty(r):
    out = {}
    for line in r.quantity.lines:
        out[line.part.model_no] = out.get(line.part.model_no, 0) + line.qty
    return out


class TestLayoutChoice(unittest.TestCase):
    def test_inside_is_the_cli_default(self):
        self.assertFalse(solve_all(dict(RECT)).stair_plan.outside)

    def test_auto_uses_the_space_outside(self):
        self.assertTrue(solve_all({**RECT, "stairs": {"layout": "自動"}}).stair_plan.outside)
        narrow = solve_all({**RECT, "stairs": {"layout": "auto"}, "clearance_space_mm": 800})
        self.assertFalse(narrow.stair_plan.outside)

    def test_forced_outside_warns_when_narrow(self):
        r = solve_all({**RECT, "stairs": {"layout": "外付け"}, "clearance_space_mm": 800})
        self.assertTrue(r.stair_plan.outside)
        self.assertTrue(any("外付け" in w for w in r.stair_plan.warnings))

    def test_frame_series_stays_inside(self):
        r = solve_all({**RECT, "series_id": "waku", "stairs": {"layout": "outside"}})
        self.assertFalse(r.stair_plan.outside)


class TestOutsideQuantities(unittest.TestCase):
    def test_main_deck_is_not_cut_and_tower_parts_are_added(self):
        a = solve_all({**RECT, "stairs": {"layout": "inside"}})
        b = solve_all({**RECT, "stairs": {"layout": "outside"}})
        qa, qb = _qty(a), _qty(b)
        n_t = len(b.stair_plan.towers)
        n_lv = b.model.elevation.n_levels
        pos = sum(t.span_count + 1 for t in b.stair_plan.towers)
        self.assertEqual(qb["ND752P"] - qa["ND752P"], pos)                 # 3列目の脚
        self.assertEqual(qb["NDP27N"] - qa["NDP27N"], pos * b.model.elevation.posts.count(2700))
        # 床: 本体は切らない（中の階段の開口ぶん）＋外の升目の踊り場（各層1スパン）
        self.assertEqual(qb["NDN6"] - qa["NDN6"], 2 * n_t * n_lv)
        self.assertEqual(qb["NDAL4518K"], qa["NDAL4518K"])                 # 階段そのものは同じ
        self.assertTrue(any("外付け（3列）" in n for n in b.quantity.notes))

    def test_gdl_params_and_drawn_counts(self):
        b = solve_all({**RECT, "stairs": {"layout": "outside"}})
        t = b.stair_plan.towers[0]
        ep = next(e for e in b.model.plan.edges if e.edge_index == t.edge_index)
        self.assertEqual(line_params(b.model, ep, stair_plan=b.stair_plan)["stOut"], 1)
        c = face_drawn_counts(b.model, ep, stair_plan=b.stair_plan)
        self.assertEqual(c["qtyDeck"], len(ep.spans) * b.model.elevation_of(ep.edge_index).n_levels)
        self.assertEqual(c["qtyStair"], sum(1 for x in b.stair_plan.towers if x.edge_index == ep.edge_index)
                         * b.model.elevation.n_levels)

    def test_3d_draws_the_third_row(self):
        from pathlib import Path

        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                ).read_text(encoding="utf-8")
        self.assertIn("yb = -rowW - stOut * rowW", body)
        self.assertIn("yo = -2 * rowW", body)
        self.assertIn("if stOut = 0 and x >= stS[it4] - 0.001", body)


if __name__ == "__main__":
    unittest.main()


class TestOutsideStairAnnotations(unittest.TestCase):
    def test_dimensions_and_label_clear_the_stair_bay(self):
        from ashiba.plan_labels import face_outward_m, plan_label_items

        b = solve_all({**RECT, "stairs": {"layout": "outside"}})
        a = solve_all({**RECT, "stairs": {"layout": "inside"}})
        t = b.stair_plan.towers[0]
        ep = next(e for e in b.model.plan.edges if e.edge_index == t.edge_index)
        row = b.model.post_row_spacing_mm / 1000.0
        self.assertGreaterEqual(face_outward_m(b.model, ep, b.platforms, b.stair_plan), row)
        self.assertEqual(face_outward_m(a.model, ep, a.platforms, a.stair_plan), 0.0)
        out_lbl = [i for i in plan_label_items(b.model, b.stair_plan) if "階段" in i[2]]
        in_lbl = [i for i in plan_label_items(a.model, a.stair_plan) if "階段" in i[2]]
        # 南面（辺0）は外が -y。外付けは1升ぶん外へ
        self.assertAlmostEqual(in_lbl[0][1] - out_lbl[0][1], b.model.post_row_spacing_mm / 1000.0, places=6)   # 座標は m
