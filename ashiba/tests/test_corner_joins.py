"""ブラケット足場とくさびの本足場の出隅（利用者の指定 2026-10-23: くさび式がブラケットの支柱のところまで必要）."""

import unittest

from ashiba.cli import solve_groups

B = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]


def _solve(form, **extra):
    spec = {"project_name": "隅", "outline_mm": B, "eaves_height_mm": 9000, "face_forms": {"南面": form}}
    spec.update(extra)
    runs = solve_groups(spec)
    main = next(r for lb, r in runs if lb == "")
    brk = next(r for lb, r in runs if lb == form)
    return main, brk


def _edge(r, ei):
    return next(e for e in r.model.plan.edges if e.edge_index == ei)


class TestWedgeReachesTheBracketPosts(unittest.TestCase):
    def test_main_faces_run_to_the_bracket_post_line(self):
        main, brk = _solve("ブラケット足場（支柱）")
        south = _edge(brk, 0)
        post_y = -(south.standoff + brk.model.post_row_spacing_mm)     # ブラケットの支柱の列
        east, west = _edge(main, 1), _edge(main, 3)
        self.assertEqual(east.spans[0], 610)                            # 東面は始点に 610 を足して支柱の列まで
        self.assertAlmostEqual(east.start_post[1], post_y)
        self.assertAlmostEqual(west.end_post[1], post_y)                # 西面の端も支柱の列まで（隙間はコーナーステップ）
        # ブラケットの面は本足場の内側建地列の線から線まで
        self.assertAlmostEqual(south.start_post[0], west.start_post[0])
        self.assertAlmostEqual(south.end_post[0], east.start_post[0])
        self.assertEqual(brk.model.joined_ends, {(0, "s"), (0, "e")})
        self.assertFalse(brk.model.open_start(0) or brk.model.open_end(0))   # 本足場の床に続くので妻側の手すりなし
        self.assertTrue(main.model.open_start(1))                        # 本足場の延長の端は開放端のまま
        self.assertTrue(any("ブラケットの支柱の列" in w for w in brk.model.plan.warnings))

    def test_gap_at_the_start_of_a_main_face_gets_a_corner_step(self):
        from ashiba.attachments import cstep_placements

        main, brk = _solve("ブラケット足場（単管）")
        east = _edge(main, 1)
        cs = [c for c in main.model.plan.corner_steps if c.edge_index == 1 and c.at_start]
        self.assertEqual(len(cs), 1)
        south = _edge(brk, 0)
        self.assertAlmostEqual(east.start_post[1] - cs[0].gap_mm, -(south.standoff + brk.model.post_row_spacing_mm))
        pl = [p for p in cstep_placements(main.model) if abs(p.x_mm - east.start_post[0]) < 1]
        self.assertTrue(any(abs(p.y_mm - (east.start_post[1] - cs[0].gap_mm)) < 1 for p in pl))

    def test_can_be_turned_off(self):
        main, brk = _solve("ブラケット足場（支柱）", corner_joins=False)
        self.assertAlmostEqual(_edge(main, 1).start_post[1], -300.0)
        self.assertFalse(brk.model.joined_ends)
        self.assertTrue(brk.model.open_start(0))


if __name__ == "__main__":
    unittest.main()
