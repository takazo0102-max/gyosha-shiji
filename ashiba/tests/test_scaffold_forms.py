"""ブラケット足場（単管・支柱）と単管抱き足場（利用者の指定 2026-10-21）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all

BASE = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000,
        "clearance_space_mm": 900}


def _qty(r, cat):
    return {ln.part.model_no: ln.qty for ln in r.quantity.lines if ln.part and ln.part.category == cat}


def _check(r, cid):
    return next(c for c in r.checks if c.check_id == cid)


class TestTubeSeries(unittest.TestCase):
    def test_tube_full_scaffold_counts_clamps_and_joints(self):
        r = solve_all({**BASE, "series_id": "tankan", "roof_bridge": False})   # 屋上への渡りの単管・クランプは別
        m = r.model
        self.assertTrue(m.master.is_tube)
        self.assertEqual(m.master.system_name, "単管足場")
        self.assertTrue(all(s <= 1800 for e in m.plan.edges for s in e.spans))   # 建地間隔 1.85m 以下
        from ashiba.tube_runs import face_runs

        short = sum(_qty(r, "布材").values())          # 腕木・出隅の短い管（両端をクランプ）
        braces = sum(_qty(r, "筋交").values())
        runs = [face_runs(list(e.spans))[0] for e in m.plan.edges]
        n_rows = sum(_qty(r, "単管").values()) // sum(len(a.pieces) for a in runs)
        clamps = _qty(r, "クランプ")
        # 布・手すりの通しは建地ごとに1個（スパンごとの両端ではない）
        self.assertEqual(clamps["ARC1"], 2 * short + n_rows * sum(len(e.spans) + 1 for e in m.plan.edges))
        self.assertEqual(clamps["ARC2"], 2 * braces)
        self.assertGreaterEqual(_qty(r, "ジョイント")["PCJ"], n_rows * sum(len(a.pieces) - 1 for a in runs))
        self.assertEqual(m.guard_rail_height_mm, 900)
        self.assertEqual(m.midrail_height_mm, 450)
        self.assertEqual(_check(r, 3).status, "OK")
        # 天端は手すり分の上（単管は1m刻みなので要求より高くてよい）
        e = m.elevation
        self.assertGreaterEqual(e.jack_extension + sum(e.posts), 6000 + 900)


    def test_handrail_stays_under_the_post_top(self):
        # 単管は手すりを床から900にクランプで付ける。くさびの「天端から2コマ下」を最上層にすると、手すり・中桟が
        # 建地の天端より上に浮いた（実機の3Dでクランプだけ宙に浮いていた）
        from ashiba.model import TUBE_GUARD_RAIL_HEIGHT_MM, TUBE_POST_ABOVE_RAIL_MM

        for form in ({"series_id": "tankan"}, {"scaffold_form": "単管抱き足場"}):
            e = solve_all({**BASE, **form}).model.elevation
            # 建地の天端は手すりより100上（手すりのクランプが管の端に掛からない）
            self.assertLessEqual(e.level_heights[-1] + TUBE_GUARD_RAIL_HEIGHT_MM + TUBE_POST_ABOVE_RAIL_MM,
                                 e.total_height)
            self.assertGreaterEqual(e.level_heights[-1], 6000)              # 最上層は軒高に届く
            self.assertEqual(sum(e.posts), sum(e.posts_alt))                 # 千鳥でも天端は揃う


class TestBracketScaffold(unittest.TestCase):
    def test_tube_bracket_uses_the_tube_series_with_one_plank(self):
        r = solve_all({**BASE, "series_id": "nikken_nd1800", "scaffold_form": "ブラケット足場", "bracket_post": "単管"})
        m = r.model
        self.assertEqual(m.master.series_id, "tankan")                  # 単管の系列で組む
        self.assertEqual(m.config.form_label, "ブラケット足場（単管）")
        # 足場板は1列（利用者の指定 2026-10-22）。腕はそれを受ける単管ブラケット（数量と同じ長さ）
        self.assertEqual(m.deck_widths_in_use, (240,))
        # カタログの C付伸縮ブラケット フリー（日建 p108、φ48.6・42.7兼用）。足場板1列は TWL500F を縮めて 430
        self.assertIn("TWL500F", _qty(r, "ブラケット"))
        self.assertEqual(m.post_row_spacing_mm, 430)
        # 一側足場は563条の作業床の規定の適用外。40cm未満は注意（NG にしない）
        self.assertEqual(_check(r, 2).status, "WARN")

    def test_tube_bracket_has_no_stairs(self):
        # 足場板1列の単管のブラケット足場に階段はつけれない（利用者の指摘 2026-10-22）。昇降ははしご等（ladders）
        r = solve_all({**BASE, "scaffold_form": "ブラケット足場", "bracket_post": "単管", "ladders": 2})
        self.assertTrue(r.model.no_stair_tower)
        self.assertFalse(r.stair_plan.towers)
        self.assertFalse([ln for ln in r.quantity.lines if ln.part and "階段" in ln.part.category])
        self.assertTrue(any("階段は入らない" in w for w in r.model.plan.warnings))
        self.assertEqual(_check(r, 12).status, "OK")                    # はしご等で昇降設備あり
        # 支柱のブラケット足場（くさび）も階段を付けられない寸法（利用者の指摘 2026-10-23）。はしごを外周から入れる
        k = solve_all({**BASE, "series_id": "shinwa_A", "scaffold_form": "ブラケット足場", "bracket_post": "支柱"})
        self.assertTrue(k.model.no_stair_tower)
        self.assertFalse(k.stair_plan.towers)
        self.assertGreater(k.model.config.ladders, 0)
        self.assertEqual(_check(k, 12).status, "OK")

    def test_post_bracket_keeps_the_series(self):
        r = solve_all({**BASE, "series_id": "shinwa_A", "scaffold_form": "ブラケット足場", "bracket_post": "支柱"})
        m = r.model
        self.assertEqual(m.master.series_id, "shinwa_A")
        self.assertEqual(m.config.scaffold_form, "一側足場")
        self.assertEqual(m.config.form_label, "ブラケット足場（支柱）")
        self.assertTrue(_qty(r, "ブラケット"))


class TestHugScaffold(unittest.TestCase):
    def test_hug_has_two_ledgers_per_level_and_no_brackets(self):
        r = solve_all({**BASE, "scaffold_form": "単管抱き足場"})
        m = r.model
        self.assertEqual(m.master.series_id, "tankan")
        self.assertTrue(m.config.is_hug)
        self.assertEqual(m.config.form_label, "単管抱き足場")
        # 布板・幅木は無い（抱き合わせた単管2本が床。利用者の指定 2026-10-22）
        self.assertEqual(m.deck_widths_in_use, ())
        self.assertFalse(m.config.has_toe_board)
        self.assertFalse(_qty(r, "踏板"))
        self.assertFalse(_qty(r, "幅木"))
        self.assertFalse(_qty(r, "ブラケット"))
        # 抱いているところは3連クランプ（建地ごと・層ごと）、直交するところは直交クランプ
        n_pos = m.plan.total_posts + m.outer_corner_posts()
        self.assertEqual(_qty(r, "クランプ")["P3CR"], n_pos * m.elevation.n_levels)
        # 建地は千鳥（偶数番目の建地は継ぎ目の高さが違う）
        self.assertNotEqual(m.elevation.posts, m.elevation.posts_alt)
        self.assertEqual(sorted(m.elevation.posts), sorted(m.elevation.posts_alt))
        c2 = _check(r, 2)
        self.assertEqual(c2.status, "WARN")                            # 一側足場は563条の適用外。40cm未満は注意
        self.assertIn("単管2本", c2.message)

    def test_hug_ledgers_more_than_bracket(self):
        hug = solve_all({**BASE, "scaffold_form": "単管抱き足場"})
        brk = solve_all({**BASE, "scaffold_form": "ブラケット足場", "bracket_post": "単管"})
        span = sum(len(e.spans) for e in hug.model.plan.edges)
        n = hug.model.elevation.n_levels
        # 抱き足場は各層の床の高さに建地を両側から抱く布が2本の通し（ブラケット足場は床の高さに布が無い）。
        # 出隅の建地は隣の面と同じ1本なので、ブラケット足場の出隅の外側の升目（0.8m の管）が無い
        from ashiba.tube_runs import face_runs

        self.assertEqual([e.spans for e in hug.model.plan.edges], [e.spans for e in brk.model.plan.edges])
        self.assertFalse(_qty(hug, "布材"))
        per_run = sum(len(face_runs(list(e.spans))[0].pieces) for e in hug.model.plan.edges)
        self.assertEqual(sum(_qty(hug, "単管").values()) - sum(_qty(brk, "単管").values()), 2 * n * per_run)
        self.assertGreater(span, 0)

    def test_hug_corner_post_is_shared(self):
        # 出隅の建地は1本（利用者の指定 2026-10-22）。建地列は離れの線の上で、隣の面の端の建地・外側コーナー支柱は無い
        from ashiba.gdl_params import line_params

        m = solve_all({**BASE, "scaffold_form": "単管抱き足場"}).model
        self.assertEqual(m.post_row_spacing_mm, 0)
        self.assertEqual(m.outer_corner_posts(), 0)
        ps = [line_params(m, ep) for ep in m.plan.edges]
        self.assertTrue(all(p["cornerS"] == 0 and p["cornerE"] == 0 for p in ps))
        # 隅の建地は片方の面だけが描く（各隅でちょうど1面が終点を飛ばす）
        self.assertEqual(sum(p["skipInS"] + p["skipInE"] for p in ps), 4)
        # 直交する面は布の高さをずらす（隅の建地で管が交わらない）
        self.assertEqual(sorted(p["hugDz"] for p in ps), [0.0, 0.0, 0.06, 0.06])

    def test_unknown_form_is_rejected(self):
        from ashiba.cli import InputError
        with self.assertRaises(Exception):
            solve_all({**BASE, "scaffold_form": "吊り足場"})
        with self.assertRaises(Exception):
            solve_all({**BASE, "scaffold_form": "ブラケット足場", "bracket_post": "枠"})
        self.assertTrue(InputError)


if __name__ == "__main__":
    unittest.main()
