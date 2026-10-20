"""足場断面図（建物を横切る A-A・B-B。利用者の指定 2026-10-21「断面図も必要」）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.cross_sections import (
    choose_cuts, cross_layout_name, cross_section_annotations, cross_section_name, cross_section_specs, cut_faces,
)

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
        "series_id": "nikken_strong"}


def _span_starts(ep):
    out, x = [], 0.0
    for s in ep.spans:
        out.append(x)
        x += s
    return out + [x]


class TestCuts(unittest.TestCase):
    def setUp(self):
        self.r = solve_all(dict(RECT))
        self.m = self.r.model

    def test_two_perpendicular_cuts_across_the_building(self):
        specs = cross_section_specs(self.m, "X", self.r.stair_plan, self.r.openings, self.r.platforms)
        self.assertEqual([s.face_name for s in specs], ["A-A", "B-B"])
        self.assertEqual(specs[0].name, cross_section_name("X", "A"))
        self.assertEqual(cross_layout_name("X"), "X 足場断面図")
        (ax, ay), (bx, by) = [((s.end_mm[0] - s.start_mm[0]), (s.end_mm[1] - s.start_mm[1])) for s in specs]
        self.assertAlmostEqual(ax * bx + ay * by, 0.0, delta=1.0)
        # どちらも向かい合う2面を横切る
        self.assertEqual(sorted(f.face_name for f in cut_faces(self.m, specs[0])), ["北面", "南面"])
        self.assertEqual(sorted(f.face_name for f in cut_faces(self.m, specs[1])), ["東面", "西面"])

    def test_cut_is_mid_span_not_at_a_post(self):
        for c in choose_cuts(self.m, self.r.stair_plan):
            ep = next(e for e in self.m.plan.edges if e.edge_index == c.edge_index)
            (sx, sy) = ep.start_post
            d = abs(c.point_mm[0] - sx) + abs(c.point_mm[1] - sy)
            self.assertGreater(min(abs(d - x) for x in _span_starts(ep)), 200.0)

    def test_stair_tower_spans_are_avoided(self):
        r = solve_all({**RECT, "stairs": {"count": 1, "positions": [{"face": "南面", "start_mm": 13000}]}})
        t = r.stair_plan.towers[0]
        a = next(c for c in choose_cuts(r.model, r.stair_plan) if c.edge_index == t.edge_index)
        ep = next(e for e in r.model.plan.edges if e.edge_index == t.edge_index)
        d = abs(a.point_mm[0] - ep.start_post[0]) + abs(a.point_mm[1] - ep.start_post[1])
        self.assertFalse(t.start_mm < d < t.start_mm + t.length_mm)

    def test_standoff_and_width(self):
        spec = cross_section_specs(self.m, "X")[0]
        for f in cut_faces(self.m, spec):
            ep = next(e for e in self.m.plan.edges if e.edge_index == f.edge_index)
            self.assertAlmostEqual(abs(f.x_in - f.x_wall) * 1000.0, ep.standoff, delta=1.0)
            self.assertAlmostEqual(abs(f.x_out - f.x_in) * 1000.0, self.m.post_row_spacing_mm, delta=1.0)
            # 外側建地は躯体から離れる向き
            self.assertGreater(abs(f.x_out - f.x_wall), abs(f.x_in - f.x_wall))


class TestNotes(unittest.TestCase):
    def test_levels_heights_and_faces(self):
        r = solve_all(dict(RECT))
        spec = cross_section_specs(r.model, "X")[0]
        notes = cross_section_annotations(r.model, spec)
        texts = [t["text"] for t in notes.texts]
        e = r.model.elevation
        for i, h in enumerate(e.level_heights, start=1):
            self.assertEqual(texts.count(f"{i}層 +{h:.0f}"), 2)          # 両側の面
        self.assertEqual(sum(1 for t in texts if t.startswith("足場高さ")), 2)
        self.assertIn("南面", texts)
        self.assertIn("北面", texts)
        self.assertTrue(any(t.startswith("離れ") for t in texts))
        self.assertTrue(any("A-A 足場断面図" in t for t in texts))
        # 左側の面の文字は寸法線の左に置く（足場に重ならない）
        south = next(f for f in cut_faces(r.model, spec) if f.face_name == "南面")
        lvl = [t for t in notes.texts if t["text"] == "1層 +%.0f" % e.level_heights[0]]
        left_one = min(lvl, key=lambda t: t["x"])
        self.assertLess(left_one["x"], south.x_out)

    def test_setback_faces_use_their_own_height(self):
        r = solve_all({**RECT, "face_eaves_mm": {"南面": 9000, "東面": 9000, "西面": 9000, "北面": 6000}})
        spec = cross_section_specs(r.model, "X")[0]
        tops = sorted(t["text"] for t in cross_section_annotations(r.model, spec).texts if t["text"].startswith("足場高さ"))
        self.assertEqual(len(set(tops)), 2)

    def test_raised_base_moves_notes_up(self):
        r = solve_all(dict(RECT))
        spec = cross_section_specs(r.model, "X")[0]
        n0 = cross_section_annotations(r.model, spec)
        r.model.base_height_mm = 3000.0
        n1 = cross_section_annotations(r.model, spec)
        self.assertAlmostEqual(n1.lines[0][0][1] - n0.lines[0][0][1], 3.0)


class TestOutsideStair(unittest.TestCase):
    def test_dims_clear_the_outside_stair_tower(self):
        spec0 = {**RECT, "stairs": {"layout": "outside", "count": 1}}
        r = solve_all(spec0)
        self.assertTrue(r.stair_plan.outside)
        t = r.stair_plan.towers[0]
        spec = next(s for s in cross_section_specs(r.model, "X") if any(
            f.edge_index == t.edge_index for f in cut_faces(r.model, s)))
        f = next(f for f in cut_faces(r.model, spec) if f.edge_index == t.edge_index)
        plain = cross_section_annotations(r.model, spec)
        with_st = cross_section_annotations(r.model, spec, stair_plan=r.stair_plan)
        def far(n):
            return max(abs(t_["x"] - f.x_out) for t_ in n.texts if t_["text"].startswith("足場高さ")
                       and (t_["x"] - f.x_in) * (f.x_out - f.x_in) > 0)
        self.assertAlmostEqual(far(with_st) - far(plain), r.model.post_row_spacing_mm / 1000.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
