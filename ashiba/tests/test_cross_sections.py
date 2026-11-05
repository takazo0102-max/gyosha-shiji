"""足場断面図（建物を横切る A-A・B-B。利用者の指定 2026-10-21「断面図も必要」）."""

import unittest
from pathlib import Path

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
        # 高さは寸法の3本（段・支柱・足場）を両側の面に。層の高さの文字は書かない（利用者の指定 2026-10-23）
        self.assertFalse(any("層 +" in x for x in texts))
        for title in ("段の高さ", "支柱の高さ", "足場の高さ"):
            self.assertEqual(texts.count(title), 2)
        totals = [d for d in notes.dims if d["chain"] == "足場の高さ"]
        self.assertEqual([d["values"] for d in totals], [[e.total_height]] * 2)
        self.assertIn("南面", texts)
        self.assertIn("北面", texts)
        self.assertTrue(any(t.startswith("離れ") for t in texts))
        self.assertTrue(any(x.endswith(f"幅 {r.model.post_row_spacing_mm:.0f}") for x in texts))
        # 単管抱き足場（建地1列）は幅を書かない（「幅 0」と寸法の「0」が出ていた）
        h = solve_all({**RECT, "scaffold_form": "単管抱き足場"})
        ht = [t["text"] for t in cross_section_annotations(h.model, cross_section_specs(h.model, "X")[0]).texts]
        self.assertFalse(any("幅 0" in x for x in ht), ht)
        self.assertNotIn("0", ht)
        self.assertTrue(any("A-A 足場断面図" in t for t in texts))
        # 左側の面の文字は寸法線の左に置く（足場に重ならない）
        south = next(f for f in cut_faces(r.model, spec) if f.face_name == "南面")
        lvl = [t for t in notes.texts if t.get("chain_title") and t["text"] == "段の高さ"]
        left_one = min(lvl, key=lambda t: t["x"])
        self.assertLess(left_one["x"], south.x_out)

    def test_setback_faces_use_their_own_height(self):
        r = solve_all({**RECT, "face_eaves_mm": {"南面": 9000, "東面": 9000, "西面": 9000, "北面": 6000}})
        spec = cross_section_specs(r.model, "X")[0]
        tops = sorted(d["values"][0] for d in cross_section_annotations(r.model, spec).dims if d["chain"] == "足場の高さ")
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
            return max(abs(t_["x"] - f.x_out) for t_ in n.texts if t_.get("chain_title") and t_["text"] == "足場の高さ"
                       and (t_["x"] - f.x_in) * (f.x_out - f.x_in) > 0)
        self.assertAlmostEqual(far(with_st) - far(plain), r.model.post_row_spacing_mm / 1000.0, delta=0.01)



class TestSplitAt50(unittest.TestCase):
    """断面図は面ごとに切って 1/50（利用者の指定 2026-10-23: 詳細もわかるように1/50でおさまるように）."""

    def test_each_face_gets_a_short_section(self):
        from ashiba.cross_sections import CLEAR_MM, INSIDE_MM, cross_sheet_name, split_cross_specs
        # 断面は足場ラインの幕（躯体面の 1m 奥、3d.gdl の standoff + 1.0）の手前で止める
        g3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(
            encoding="utf-8")
        self.assertIn("add -rowW - 0.05, standoff + 1.0, -3.0", g3)
        self.assertLess(INSIDE_MM, 1000.0)

        r = solve_all(dict(RECT))
        full = cross_section_specs(r.model, "X")
        parts = split_cross_specs(r.model, full)
        self.assertEqual([p.face_name for p in parts], ["A-A 南面", "A-A 北面", "B-B 東面", "B-B 西面"])
        self.assertEqual(parts[0].name, cross_section_name("X", "A") + " 南面")
        row = r.model.post_row_spacing_mm
        for p in parts:
            faces = cut_faces(r.model, p)
            self.assertEqual(len(faces), 1)                                    # 1面だけを切る
            f = faces[0]
            self.assertIn(f.face_name, p.face_name)
            # 足場の外 CLEAR_MM から躯体の内側 INSIDE_MM まで（30×20m の建物でも 1/50 で十数 m）
            self.assertAlmostEqual(p.length_mm, CLEAR_MM + row + f.standoff_mm + INSIDE_MM, delta=2.0)
            # 向きは元の断面と同じ（見る向きがそろう）
            src = next(s for s in full if p.face_name.startswith(s.face_name))
            d0 = (src.end_mm[0] - src.start_mm[0], src.end_mm[1] - src.start_mm[1])
            d1 = (p.end_mm[0] - p.start_mm[0], p.end_mm[1] - p.start_mm[1])
            self.assertGreater(d0[0] * d1[0] + d0[1] * d1[1], 0)
            self.assertEqual(len(cross_section_annotations(r.model, p).dims), 3)   # 段・支柱・足場の高さ
        self.assertEqual(cross_sheet_name("X", "A-A"), "X 足場断面図 A-A")


if __name__ == "__main__":
    unittest.main()


class TestGroupCrossSections(unittest.TestCase):
    def test_switched_faces_get_their_half_of_the_cut(self):
        """面ごとに足場を替えた建物でも、切断線が横切る替えた面の断面図を出す（先頭の組の面だけだった）."""
        from ashiba.cli import solve_groups
        from ashiba.cross_sections import cross_section_specs, split_cross_specs_with_owner

        gs = solve_groups({**RECT, "face_forms": "北面=一側足場"})
        (_l0, r0), (_l1, r1) = gs
        full = cross_section_specs(r0.model, "X", r0.stair_plan, r0.openings, r0.platforms)
        owned = split_cross_specs_with_owner([(r.model, r.stair_plan, r.terrain) for _l, r in gs], full)
        names = [s.face_name for s, _own in owned]
        north = [(s, own) for s, own in owned if s.face_name.endswith("北面")]
        self.assertEqual(len(north), 1, names)
        self.assertIs(north[0][1][0], r1.model)                     # 北面の注記は一側足場の組の模型で
        self.assertEqual(len(names), 4)


class TestCutAwayFromParallelFaces(unittest.TestCase):
    def test_cut_does_not_run_along_an_inner_face(self):
        """L 字で切断線が入隅の面の足場に沿って通らない（B-B が入隅の北面の足場の上を通っていた）."""
        from ashiba.cross_sections import PARALLEL_CLEAR_MM, cross_section_specs

        L = [[0, 0], [24000, 0], [24000, 8000], [12000, 8000], [12000, 16000], [0, 16000]]
        r = solve_all({"outline_mm": L, "eaves_height_mm": 9000})
        specs = {s.face_name: s for s in cross_section_specs(r.model, "X", r.stair_plan, r.openings, r.platforms)}
        bb_y = specs["B-B"].start_mm[1]
        aa_x = specs["A-A"].start_mm[0]
        self.assertGreater(abs(bb_y - 8000), PARALLEL_CLEAR_MM)            # 入隅の北面(辺2)
        self.assertGreater(abs(aa_x - 12000), PARALLEL_CLEAR_MM)           # 入隅の東面(辺3)
