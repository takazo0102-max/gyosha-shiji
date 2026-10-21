"""単管の通し: 規定の長さの単管を直線ジョイントで継ぐ（利用者の指定 2026-10-22）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tube_runs import (
    BOARD_BEAR_MM, BOARD_LAP_MM, BOARD_MAX_OVER_MM, BOARD_STOCK_MM, END_MM, JOINT_CLEAR_MM, MAX_OVER_MM, STOCK_MM,
    face_boards, face_runs, post_positions,
)

GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"


class TestTubeRuns(unittest.TestCase):
    def test_runs_cover_the_face_with_stock_lengths(self):
        for spans in ([1800] * 7, [1800] * 4 + [1500], [1800] * 20 + [900], [1800, 1800], [1500]):
            a, b = face_runs(spans)
            L = sum(spans)
            self.assertTrue(all(p in STOCK_MM for p in a.pieces))
            self.assertEqual(a.start_mm, -END_MM)
            self.assertGreaterEqual(a.end_mm, L + END_MM)                 # 終点の建地の先まで届く
            self.assertLessEqual(a.end_mm, L + END_MM + MAX_OVER_MM)
            self.assertEqual(sorted(a.pieces), sorted(b.pieces))          # B は同じ単管の並べ替え（数量は同じ）
            posts = post_positions(spans)
            for x in a.joints_mm + b.joints_mm:                           # 継ぎは建地のクランプから離す
                self.assertTrue(all(abs(x - p) >= JOINT_CLEAR_MM for p in posts))

    def test_example_face(self):
        a, b = face_runs([1800] * 7)                                      # 12.6m の面
        self.assertEqual(a.pieces, [6000, 6000, 1000])                    # 本数が少なく、長い単管が先
        self.assertEqual(len(a.joints_mm), 2)
        self.assertNotEqual(a.joints_mm, b.joints_mm)                     # 隣の通しと継ぎをずらす

    def test_short_face_is_one_tube(self):
        a, b = face_runs([1800, 1800])
        self.assertEqual(a.pieces, [4000])
        self.assertEqual(a.joints_mm, [])

    def test_gdl_draws_the_runs(self):
        d3 = (GDL / "3d.gdl").read_text(encoding="utf-8")
        d1 = (GDL / "1d.gdl").read_text(encoding="utf-8")
        self.assertIn("rl[p832][nRl[p832]] = v / 1000", d1)
        self.assertIn("832:", d3)
        self.assertIn("846:", d3)
        # 布・根がらみ・手すり（外・内）・抱き足場の床の布が通しを使う
        self.assertGreaterEqual(d3.count("runX = x"), 4)
        # 識別色は長さ別一覧表の11色
        self.assertEqual(d3.count('define material "ashiba_tc_'), 11)

    def test_params(self):
        from ashiba.cli import solve_all
        from ashiba.gdl_params import line_params

        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}
        m = solve_all({**base, "scaffold_form": "単管抱き足場"}).model
        p = line_params(m, m.plan.edges[0])
        a, b = face_runs(list(m.plan.edges[0].spans))
        self.assertEqual(p["tubeRunA"], ",".join(str(v) for v in a.pieces))
        self.assertEqual(p["tubeRunB"], ",".join(str(v) for v in b.pieces))
        self.assertAlmostEqual(p["tubeRunS"], -0.1)
        w = solve_all(base).model
        self.assertEqual(line_params(w, w.plan.edges[0])["tubeRunA"], "")   # くさびは通さない



class TestBoards(unittest.TestCase):
    """単管のブラケット足場の足場板: 規定の長さ、継ぎは300重ねてブラケットの上（利用者の指定 2026-10-22）."""

    def test_laps_sit_on_brackets(self):
        for spans in ([1800] * 7, [1800] * 4 + [1500], [1800] * 20 + [900], [1800, 1800], [1500], [1800] * 6 + [1500]):
            posts = post_positions(spans)
            for run in face_boards(spans):
                self.assertTrue(all(p in BOARD_STOCK_MM for p in run.pieces))
                seg = run.spans_mm()
                for (s0, e0), (s1, _e1) in zip(seg, seg[1:]):
                    self.assertAlmostEqual(e0 - s1, BOARD_LAP_MM)                  # 300 重ねる
                    # 重ねの中にブラケット（建地）があり、両側に 100 以上ずつ掛かる
                    self.assertTrue(any(p - s1 >= BOARD_BEAR_MM and e0 - p >= BOARD_BEAR_MM for p in posts))
                self.assertLessEqual(-BOARD_MAX_OVER_MM, seg[0][0])
                self.assertLessEqual(seg[0][0], -BOARD_BEAR_MM)                     # 端もブラケットに掛かる
                self.assertGreaterEqual(seg[-1][1], posts[-1] + BOARD_BEAR_MM)
                self.assertLessEqual(seg[-1][1], posts[-1] + BOARD_MAX_OVER_MM)

    def test_bracket_scaffold_counts_boards_by_length(self):
        from ashiba.cli import solve_all
        from ashiba.gdl_params import line_params

        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}
        r = solve_all({**base, "scaffold_form": "ブラケット足場", "bracket_post": "単管"})
        m = r.model
        n = m.elevation.n_levels
        boards = {ln.part.model_no: ln.qty for ln in r.quantity.lines if ln.part and ln.part.category == "踏板"}
        want: dict = {}
        for ep in m.plan.edges:
            for i in range(len(m.deck_widths_in_use)):
                for L in face_boards(list(ep.spans))[i % 2].pieces:
                    k = f"足場板{L / 1000:.1f}M-240"
                    want[k] = want.get(k, 0) + n
        # 出隅ごと・層ごとにコーナーの足場板1.0Mを1枚（利用者の指摘 2026-10-22: コーナー部分）
        want["足場板1.0M-240"] = want.get("足場板1.0M-240", 0) + m.outer_corner_posts() * n
        self.assertEqual(boards, want)
        d3 = (GDL / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn('if showDeck and hugMode = 0 and serType = "T" and nRows < 2 then', d3)
        self.assertIn("if kb = nBd[bw] and cornerE = 1 and nRows < 2 then bRz = 0.056", d3)
        # クランプは金色（利用者の指定 2026-10-22）
        i = d3.index("838:")
        self.assertNotIn("ashiba_clamp_zinc", d3[i:i + 3000])
        self.assertIn('material "ashiba_clamp_gold"', d3[i:i + 3000])
        p = line_params(m, m.plan.edges[0])
        self.assertEqual(p["deckRunA"], ",".join(str(v) for v in face_boards(list(m.plan.edges[0].spans))[0].pieces))

    def test_toe_boards_follow_the_deck_layout(self):
        # 幅木も足場板を立てて規定の長さで通し、継ぎは300重ねる（利用者の指定 2026-10-22）
        from ashiba.cli import solve_all

        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}
        r = solve_all({**base, "scaffold_form": "ブラケット足場", "bracket_post": "単管"})
        m = r.model
        toe = {ln.part.model_no: ln.qty for ln in r.quantity.lines if ln.part and ln.part.category == "幅木"}
        want: dict = {}
        for ep in m.plan.edges:
            for L in face_boards(list(ep.spans))[0].pieces:
                k = f"足場板{L / 1000:.1f}M-240"
                want[k] = want.get(k, 0) + m.elevation.n_levels
        corner = m.outer_corner_posts() * m.elevation.n_levels * 2          # 出隅の外側の升目の幅木（短い板）
        got = dict(toe)
        got["足場板1.0M-240"] = got.get("足場板1.0M-240", 0) - corner
        self.assertEqual({k: v for k, v in got.items() if v}, want)
        d3 = (GDL / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("block bdLen[1][kb], 0.028, 0.24", d3)

    def test_bracket_tip_has_no_clamp_and_ties_start_at_the_post(self):
        d3 = (GDL / "3d.gdl").read_text(encoding="utf-8")
        # 単管のブラケットは C付伸縮ブラケット（812）。クランプは建地側だけ（先端に建地が無い）
        i = d3.index("812:")
        sub = d3[i:d3.index("800: ! ---- 一側足場の床受けブラケット")]
        self.assertEqual(sub.count("gosub 838"), 1)
        self.assertIn("TWL500F", sub)
        self.assertIn("if nRows < 2 then yTie = -rowW", d3)

    def test_tie_from_the_outer_post_on_a_single_row(self):
        from ashiba.attachments import tie_placements
        from ashiba.cli import solve_all
        from ashiba.quantity import wall_tie_required_length_mm

        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}
        brk = solve_all({**base, "scaffold_form": "ブラケット足場", "bracket_post": "単管"}).model
        full = solve_all({**base, "series_id": "tankan"}).model
        self.assertEqual(brk.tie_post_offset_mm, brk.post_row_spacing_mm)
        self.assertEqual(full.tie_post_offset_mm, 0)
        e = brk.plan.edges[0]
        self.assertAlmostEqual(wall_tie_required_length_mm(brk, e.edge_index),
                               e.standoff + brk.post_row_spacing_mm + 48.6 / 2, places=3)
        t = tie_placements(brk)[0]
        self.assertAlmostEqual(t.params["wallD"] * 1000, brk.plan.edges[0].standoff + brk.post_row_spacing_mm, places=3)



class TestMasterArraysDoNotClash(unittest.TestCase):
    def test_arrays_are_not_scalars_in_the_parameter_script(self):
        # マスタースクリプトで dim した名前を、パラメータスクリプトで数として代入すると、パラメータスクリプトが落ちて
        # 部品のパラメータが読めなくなる（実機: 足場板の配列 bd が vl.gdl の bd = 1e9 と衝突し、配置できなかった）
        import re

        d1 = (GDL / "1d.gdl").read_text(encoding="utf-8")
        vl = (GDL / "vl.gdl").read_text(encoding="utf-8")
        arrays = set(re.findall(r"^dim\s+(\w+)\[", d1, flags=re.M))
        scalars = set(re.findall(r"^\s*(\w+)\s*=[^=]", vl, flags=re.M))
        self.assertFalse(arrays & scalars, arrays & scalars)


if __name__ == "__main__":
    unittest.main()
