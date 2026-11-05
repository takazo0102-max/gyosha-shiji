"""足場ラインの支柱だけを部材（ashiba_member）に分解する（利用者の指定 2026-10-21「分解はやめて…支柱だけ分解できるように」）."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.explode import KIND, koma_offsets, line_members, member_counts, to_world
from ashiba.gdl_params import line_params

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000}


def _count(ms, kind, name_has=""):
    return sum(1 for m in ms if m.kind == kind and name_has in m.name)


def _key(m):
    return (m.kind, round(m.x, 3), round(m.y, 3), round(m.z, 3), round(m.L, 3))


class TestPostsOnly(unittest.TestCase):
    def test_only_posts_with_the_line_count(self):
        """くさび式: 支柱だけ（ジャッキ・布材・踏板などは足場ラインのまま）。足場ラインは面の両端の支柱を描く."""
        for sid in ("nikken_nd1800", "nikken_strong", "shinwa_A"):
            r = solve_all({**RECT, "series_id": sid})
            for ep in r.model.plan.edges:
                p = line_params(r.model, ep)
                ms = line_members(p)
                n_post = len(r.model.elevation_of(ep.edge_index).posts)
                with self.subTest(series=sid, edge=ep.edge_index):
                    self.assertEqual({m.kind for m in ms}, {KIND["支柱"]})
                    pos = (len(ep.spans) + 1) * 2 - p["skipInS"] - p["skipInE"] + p["cornerS"]
                    self.assertEqual(len(ms), pos * n_post)

    def test_posts_carry_catalog_komas(self):
        self.assertEqual(koma_offsets(2.7, 0.45, 0.055, 0.17, [2700, 1125, 900]),
                         [170, 395, 845, 1295, 1745, 2195, 2645])
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        ms = line_members(line_params(r.model, r.model.plan.edges[0]))
        first = next(m for m in ms if "出隅" not in m.name)
        self.assertAlmostEqual(first.z, r.model.elevation.jack_extension / 1000)
        self.assertEqual(first.koma[0], 170)

    def test_outer_corner_post(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        ms = line_members(line_params(r.model, r.model.plan.edges[0]))
        corner = [m for m in ms if "出隅" in m.name]
        self.assertEqual(len(corner), len(r.model.elevation.posts))
        self.assertTrue(all(abs(m.x + 0.61) < 0.01 and abs(m.y + 0.61) < 0.01 for m in corner))

    def test_posts_on_the_beam(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800",
                       "openings": [{"edge_index": 0, "start_mm": 3658, "beam_span_mm": 3658, "level": 2}]})
        ms = line_members(line_params(r.model, r.model.plan.edges[0], openings=r.openings))
        self.assertEqual(_count(ms, KIND["支柱"], "梁枠上"), 2)        # 梁の中の支柱位置1つ × 内外

    def test_world_placement_follows_the_line(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        ep = r.model.plan.edges[1]                      # 東面（+Y 向き）
        ms = line_members(line_params(r.model, ep))
        w = to_world(ms, (30.0, 0.0), math.radians(90), base_z_m=0.0)
        outer = next(o for o, m in zip(w, ms) if abs(m.x) < 0.001 and abs(m.y + 0.61) < 0.01)
        self.assertAlmostEqual(outer["x"], 30.0 + 0.61, places=3)   # 外側（-Y 局所）は +X 側
        self.assertAlmostEqual(outer["params"]["faceAng"], 90.0)

    def test_frame_becomes_frames(self):
        r = solve_all({**RECT, "series_id": "waku"})
        for ep in r.model.plan.edges:
            p = line_params(r.model, ep)
            ms = line_members(p)
            n_pos, n_stage = len(ep.spans) + 1, len(r.model.elevation_of(ep.edge_index).posts)
            with self.subTest(edge=ep.edge_index):
                self.assertEqual({m.kind for m in ms}, {KIND["建枠"]})
                self.assertEqual(len(ms), n_pos * n_stage)
                # 継ぎ目は2段目から、隅で共有する躯体側の脚は描かない
                self.assertEqual(sum(1 for m in ms if m.flags & 1), n_pos * (n_stage - 1))
                self.assertEqual(sum(1 for m in ms if m.flags & 2), (p["skipInS"] + p["skipInE"]) * n_stage)

    def test_counts_by_name(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        c = member_counts(line_members(line_params(r.model, r.model.plan.edges[0])))
        self.assertTrue(any(k.startswith("支柱 ") for k in c))
        self.assertTrue(any(k.startswith("支柱（出隅）") for k in c))


class TestPiecesShareThePosts(unittest.TestCase):
    """区切った部品ごとに分解しても、支柱は面全体と同じ（重ならず、抜けない）."""

    def _pieces(self, p, ranges):
        out = []
        for sa, sb, la, lb in ranges:
            out += line_members({**p, "segSpanA": sa, "segSpanB": sb, "segLevA": la, "segLevB": lb})
        return out

    def test_vertical_and_horizontal(self):
        for sid in ("nikken_nd1800", "waku"):
            r = solve_all({**RECT, "series_id": sid,
                           "openings": [{"edge_index": 0, "start_mm": 3658, "beam_span_mm": 3658, "level": 2}]
                           if sid != "waku" else []})
            p = line_params(r.model, r.model.plan.edges[0], openings=r.openings)
            whole = sorted(map(_key, line_members(p)))
            n, nl = len(r.model.plan.edges[0].spans), r.model.elevation.n_levels
            k, m = n // 2, max(2, nl // 2)
            parts = self._pieces(p, [(1, k, 1, m - 1), (k + 1, n, 1, m - 1), (1, k, m, nl), (k + 1, n, m, nl)])
            with self.subTest(series=sid):
                self.assertEqual(sorted(map(_key, parts)), whole)
                # 区切り目の支柱は右の部品が持つ（どの部品も自分の始点の支柱を持ち、終点の支柱は隣が持つ）
                left = line_members({**p, "segSpanA": 1, "segSpanB": k})
                x_cut = sum(r.model.plan.edges[0].spans[:k]) / 1000
                self.assertFalse(any(abs(mm.x - x_cut) < 0.001 for mm in left))


if __name__ == "__main__":
    unittest.main()
