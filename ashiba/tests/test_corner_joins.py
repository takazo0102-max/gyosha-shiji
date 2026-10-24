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
        # ブラケットはハーフアンチ 240 で幅 300（利用者の指定 2026-10-24: ハーフアンチだけなので幅300として）。支柱の列は
        # 壁から約 600 で、本足場の端からの隙間はスパンにならないのでコーナーステップで支柱の列まで渡す
        self.assertEqual(brk.model.deck_widths_in_use, (240,))
        self.assertEqual(brk.model.post_row_spacing_mm, 300)
        gaps = {(c.edge_index, c.at_start): c.gap_mm for c in main.model.plan.corner_steps}
        self.assertAlmostEqual(east.start_post[1] - gaps[(1, True)], post_y)    # 東面の始点の手前の隙間
        self.assertAlmostEqual(west.end_post[1], post_y)                # 西面の端も支柱の列まで（隙間はコーナーステップ）
        # ブラケットの面は本足場の内側建地列の線から線まで
        self.assertAlmostEqual(south.start_post[0], west.start_post[0])
        self.assertAlmostEqual(south.end_post[0], east.start_post[0])
        self.assertEqual(brk.model.joined_ends, {(0, "s"), (0, "e")})
        self.assertFalse(brk.model.open_start(0) or brk.model.open_end(0))   # 本足場の床に続くので妻側の手すりなし
        self.assertTrue(main.model.open_start(1))                        # 本足場の延長の端は開放端のまま
        self.assertTrue(any("ブラケットの支柱の列" in w for w in brk.model.plan.warnings))

    def test_standoff_dimension_skips_the_extension_span(self):
        """離れ寸法は躯体に面したスパンに（延長の 610 は隅の外で躯体が無い。2026-10-23 実機）."""
        from ashiba.plan_labels import standoff_dim_positions

        import dataclasses

        main, _brk = _solve("ブラケット足場（支柱）")
        east = _edge(main, 1)
        # 始点に 610 の延長がある形（本足場の端をブラケットの支柱の列まで延ばした面）を作って確かめる
        ext = dataclasses.replace(east, spans=[610] + list(east.spans),
                                  start_post=(east.start_post[0], east.start_post[1] - 610))
        x1, x2 = standoff_dim_positions(main.model, ext)
        self.assertAlmostEqual(x1, 610 + east.spans[0] / 2)
        self.assertAlmostEqual(x2, sum(ext.spans) - ext.spans[-1] / 2)

    def test_tube_bracket_is_clamped_past_the_post_line(self):
        main, brk = _solve("ブラケット足場（単管）")
        east, south = _edge(main, 1), _edge(brk, 0)
        post_y = -(south.standoff + brk.model.post_row_spacing_mm)
        # 単管はクランプで留めるので、くさびは支柱の列を越えて定尺で止める（隙間・コーナーステップなし）
        self.assertLessEqual(east.start_post[1], post_y + 0.5)
        self.assertLess(post_y - east.start_post[1], 610)
        self.assertFalse([c for c in main.model.plan.corner_steps if c.at_start])
        self.assertFalse([c for c in brk.model.plan.corner_steps if c.edge_index == 0])

    def test_step_at_the_start_hooks_on_the_start_post(self):
        import dataclasses

        from ashiba.attachments import cstep_placements
        from ashiba.plan_solver import CornerStep

        main, _brk = _solve("ブラケット足場（支柱）")
        m = main.model
        east = _edge(main, 1)
        m.plan = dataclasses.replace(m.plan, corner_steps=[CornerStep(1, 200.0, True, "", 1, at_start=True)])
        p = cstep_placements(m)[0]
        self.assertAlmostEqual(p.y_mm, east.start_post[1] - 200.0)       # 隙間は始点の手前
        self.assertTrue(p.params["flipX"])                                 # 爪は始点の支柱（+X の端）に掛ける

    def test_can_be_turned_off(self):
        main, brk = _solve("ブラケット足場（支柱）", corner_joins=False)
        self.assertGreater(_edge(main, 1).start_post[1], -400.0)          # 隅のまま（ブラケットの支柱の列まで延ばさない）
        self.assertFalse(brk.model.joined_ends)
        self.assertTrue(brk.model.open_start(0))


if __name__ == "__main__":
    unittest.main()
