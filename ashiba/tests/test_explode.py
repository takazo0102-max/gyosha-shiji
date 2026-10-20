"""足場ラインを部材（ashiba_member）に分解する（利用者の指定 2026-10-21: 部材を分解できるコマンド）."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.explode import KIND, koma_offsets, line_members, member_counts, to_world
from ashiba.gdl_params import face_drawn_counts, line_params

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000}


def _count(ms, kind, name_has=""):
    return sum(1 for m in ms if m.kind == kind and name_has in m.name)


class TestSameAsTheLine(unittest.TestCase):
    """分解した部材の本数は、足場ラインが描いている本数（図示本数 qty*）と同じ."""

    def _check(self, spec):
        r = solve_all(spec)
        for ep in r.model.plan.edges:
            p = line_params(r.model, ep, stair_plan=r.stair_plan, openings=r.openings, platforms=r.platforms,
                            bracket_sections=r.brackets, terrain=r.terrain)
            # 出隅の升目・開放端は別に確かめる（図示本数は面の本体の部材だけ）
            ms = [m for m in line_members(p) if "出隅" not in m.name and "妻側" not in m.name]
            c = face_drawn_counts(r.model, ep, stair_plan=r.stair_plan, openings=r.openings)
            n_post = len(r.model.elevation_of(ep.edge_index).posts)
            with self.subTest(series=spec.get("series_id"), edge=ep.edge_index):
                # 足場ラインは面の両端の支柱を描く（図示本数 qtyPostPos は終点を次の面に数える）。隅の内側は隣の面が描く
                pos = (len(ep.spans) + 1) * 2 - p["skipInS"] - p["skipInE"]
                self.assertEqual(_count(ms, KIND["支柱"]), pos * n_post)
                self.assertEqual(_count(ms, KIND["ジャッキ"]), pos)
                nuno = sum(1 for m in ms if m.kind == KIND["布材"] and "腕木" not in m.name)
                self.assertEqual(nuno, c["qtyNuno"])
                widths = 2 if p["deckW2"] > 0 else 1
                self.assertEqual(_count(ms, KIND["踏板"]), c["qtyDeck"] * widths)
                self.assertEqual(_count(ms, KIND["幅木"]), c["qtyToe"])
                self.assertEqual(_count(ms, KIND["先行手すり"]), c["qtyAdv"])
                self.assertEqual(_count(ms, KIND["ブレース"]), c["qtyBrace"])

    def test_nd1800(self):
        self._check({**RECT, "series_id": "nikken_nd1800"})

    def test_strong_advance_rail_with_inside_stairs(self):
        self._check({**RECT, "series_id": "nikken_strong", "guard_rail_type": "先行手すり",
                     "stairs": {"count": 1, "positions": [{"face": "南面", "start_mm": 3658}]}})

    def test_shinwa_two_decks(self):
        self._check({**RECT, "series_id": "shinwa_A"})

    def test_member_edits_are_respected(self):
        self._check({**RECT, "series_id": "nikken_nd1800", "member_edits": [
            {"face": "南面", "spans": "2-3", "levels": "2-3", "parts": ["踏板", "幅木", "手すり"]}]})


class TestDetails(unittest.TestCase):
    def test_posts_carry_catalog_komas(self):
        self.assertEqual(koma_offsets(2.7, 0.45, 0.055, 0.17, [2700, 1125, 900]),
                         [170, 395, 845, 1295, 1745, 2195, 2645])
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        ms = line_members(line_params(r.model, r.model.plan.edges[0]))
        first = next(m for m in ms if m.kind == KIND["支柱"])
        self.assertAlmostEqual(first.z, r.model.elevation.jack_extension / 1000)
        self.assertEqual(first.koma[0], 170)

    def test_world_placement_follows_the_line(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        ep = r.model.plan.edges[1]                      # 東面（+Y 向き）
        ms = line_members(line_params(r.model, ep))
        w = to_world(ms, (30.0, 0.0), math.radians(90), base_z_m=0.0)
        outer_jack = next(o for o, m in zip(w, ms) if m.kind == KIND["ジャッキ"] and abs(m.y + 0.61) < 0.01)
        self.assertAlmostEqual(outer_jack["x"], 30.0 + 0.61, places=3)   # 外側（-Y 局所）は +X 側
        self.assertAlmostEqual(outer_jack["params"]["faceAng"], 90.0)

    def test_frame_becomes_frames_and_cross_braces(self):
        r = solve_all({**RECT, "series_id": "waku"})
        for ep in r.model.plan.edges:
            p = line_params(r.model, ep)
            ms = line_members(p)
            e = r.model.elevation_of(ep.edge_index)
            n_pos, n_stage = len(ep.spans) + 1, len(e.posts)
            with self.subTest(edge=ep.edge_index):
                frames = [m for m in ms if m.kind == KIND["建枠"]]
                self.assertEqual(len(frames), n_pos * n_stage)
                # 継ぎ目は2段目から、隅で共有する躯体側の脚は描かない
                self.assertEqual(sum(1 for m in frames if m.flags & 1), n_pos * (n_stage - 1))
                shared = p["skipInS"] + p["skipInE"]
                self.assertEqual(sum(1 for m in frames if m.flags & 2), shared * n_stage)
                self.assertEqual(_count(ms, KIND["支柱"]), 0)
                self.assertEqual(_count(ms, KIND["交差筋違"]), 2 * len(ep.spans) * (len(e.level_heights)))
                self.assertEqual(_count(ms, KIND["ブレース"]), 0)
                self.assertEqual(_count(ms, KIND["布材"], "腕木"), 0)
                # 手すり・中桟は最上層だけ
                top = max(e.level_heights) / 1000
                rails = [m for m in ms if m.kind == KIND["布材"] and "手すり" in m.name]
                self.assertTrue(rails)
                self.assertTrue(all(m.z > top for m in rails))
                c = face_drawn_counts(r.model, ep)
                self.assertEqual(_count(ms, KIND["踏板"]), c["qtyDeck"] * (2 if p["deckW2"] > 0 else 1))
                self.assertEqual(_count(ms, KIND["幅木"]), c["qtyToe"])

    def test_counts_by_name(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        c = member_counts(line_members(line_params(r.model, r.model.plan.edges[0])))
        self.assertTrue(any(k.startswith("支柱 ") for k in c))
        self.assertTrue(any(k.startswith("布材（腕木）") for k in c))


class TestCornerAndOpenEnds(unittest.TestCase):
    def test_outer_corner_is_exploded_too(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        ep = r.model.plan.edges[0]
        p = line_params(r.model, ep)
        self.assertEqual(p["cornerS"], 1)
        ms = line_members(p)
        e = r.model.elevation_of(ep.edge_index)
        corner_posts = [m for m in ms if m.kind == KIND["支柱"] and "出隅" in m.name]
        self.assertEqual(len(corner_posts), len(e.posts))
        self.assertTrue(all(abs(m.x + 0.61) < 0.01 and abs(m.y + 0.61) < 0.01 for m in corner_posts))
        self.assertEqual(_count(ms, KIND["踏板"], "出隅"), e.n_levels)
        # 根がらみ1段＋各層の床・手すり・中桟、2方向
        self.assertEqual(_count(ms, KIND["布材"], "出隅"), 2 * (1 + 3 * e.n_levels))

    def test_open_ends_get_end_rails(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800", "faces": "南面,東面"})
        south = line_params(r.model, r.model.plan.edges[0])
        ms = line_members(south)
        n = r.model.elevation.n_levels
        self.assertEqual(_count(ms, KIND["布材"], "妻側"), 2 * n)
        self.assertEqual(_count(ms, KIND["幅木"], "妻側"), n)


if __name__ == "__main__":
    unittest.main()
