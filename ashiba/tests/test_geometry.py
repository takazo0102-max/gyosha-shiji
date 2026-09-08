"""外形と足場中心線ループのテスト.

scaffold_loop_vertices はコーナー支柱の位置を決める。オブジェクトの
配置座標がここから来るので、間違うと図面も3Dもまとめてずれる。
"""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.geometry import ValidationError, build_outline, scaffold_loop_vertices

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
LSHAPE = [(0, 0), (30000, 0), (30000, 12000), (18000, 12000), (18000, 20000), (0, 20000)]


class TestOutline(unittest.TestCase):
    def test_ccw_normalisation(self):
        """時計回りで渡しても反時計回りに正規化する."""
        cw = build_outline(list(reversed(RECT)))
        ccw = build_outline(RECT)
        self.assertEqual(len(cw.edges), len(ccw.edges))
        self.assertAlmostEqual(cw.perimeter, ccw.perimeter)
        self.assertEqual([c.kind for c in cw.corners], ["出隅"] * 4)

    def test_outward_normal_points_away_from_the_building(self):
        """CCWで外側は進行方向の右手側."""
        o = build_outline(RECT)
        # 辺0は +X 方向。外向きは -Y（建物の外）
        e0 = o.edges[0]
        self.assertAlmostEqual(e0.direction[0], 1.0)
        self.assertAlmostEqual(e0.outward[0], 0.0)
        self.assertAlmostEqual(e0.outward[1], -1.0)

    def test_lshape_has_one_reflex_corner(self):
        o = build_outline(LSHAPE)
        kinds = [c.kind for c in o.corners]
        self.assertEqual(kinds.count("入隅"), 1)
        self.assertEqual(kinds.count("出隅"), 5)

    def test_reflex_corner_shortens_both_edges(self):
        """入隅は符号 -1（回さずに短縮）、出隅は +1."""
        o = build_outline(LSHAPE)
        reflex = next(c for c in o.corners if c.kind == "入隅")
        incoming = o.edges[(reflex.index - 1) % len(o.edges)]
        outgoing = o.edges[reflex.index]
        self.assertEqual(incoming.end_sign, -1)
        self.assertEqual(outgoing.start_sign, -1)

    def test_perimeter_matches_manhattan_length(self):
        o = build_outline(RECT)
        self.assertAlmostEqual(o.perimeter, 2 * (30000 + 20000))

    def test_axis_of_each_edge(self):
        o = build_outline(RECT)
        self.assertEqual([e.axis for e in o.edges], ["x", "y", "x", "y"])

    def test_closed_polygon_is_not_reported_as_duplicate(self):
        """終点＝始点の閉じた外形（Archicadのスラブはこの形）は注記を出さない."""
        o = build_outline([(0, 0), (30000, 0), (30000, 20000), (0, 20000), (0, 0)])
        self.assertEqual(len(o.vertices), 4)
        self.assertFalse([n for n in o.notes if "重複頂点" in n], o.notes)

    def test_real_duplicate_is_still_reported(self):
        o = build_outline([(0, 0), (30000, 0), (30000, 0), (30000, 20000), (0, 20000), (0, 0)])
        self.assertEqual(len(o.vertices), 4)
        self.assertTrue(any("重複頂点を1点" in n for n in o.notes), o.notes)

    def test_non_orthogonal_is_squared_with_a_note(self):
        """斜めの辺はエラーにせず、外側のコーナーを経由する直交2辺に置き換える."""
        o = build_outline([(0, 0), (10000, 500), (10000, 8000), (0, 8000)])
        self.assertEqual([tuple(map(float, v)) for v in o.vertices],
                         [(0.0, 0.0), (10000.0, 0.0), (10000.0, 8000.0), (0.0, 8000.0)])
        self.assertTrue(any("斜めの辺" in n for n in o.notes))
        self.assertEqual([z.kind for z in o.bridged], ["斜辺", "斜辺"])


class TestScaffoldLoop(unittest.TestCase):
    """離れだけ外へオフセットした線の交点＝コーナー支柱位置."""

    def test_uniform_standoff_expands_the_rectangle(self):
        o = build_outline(RECT)
        d = 300.0
        verts = scaffold_loop_vertices(o, [d] * 4)
        self.assertEqual(len(verts), 4)
        xs = sorted({round(v[0]) for v in verts})
        ys = sorted({round(v[1]) for v in verts})
        self.assertEqual(xs, [-300, 30300])
        self.assertEqual(ys, [-300, 20300])

    def test_loop_length_grows_by_eight_times_the_standoff(self):
        """矩形なら周長は 2(W+H) + 8d になる（4コーナー×2辺ぶん）."""
        o = build_outline(RECT)
        d = 350.0
        verts = scaffold_loop_vertices(o, [d] * 4)
        loop = sum(
            abs(verts[(i + 1) % 4][0] - verts[i][0])
            + abs(verts[(i + 1) % 4][1] - verts[i][1])
            for i in range(4)
        )
        self.assertAlmostEqual(loop, 2 * (30000 + 20000) + 8 * d)

    def test_per_edge_standoff_is_respected(self):
        """面ごとに離れが違っても、各辺はその辺の離れぶんだけ外へ出る."""
        o = build_outline(RECT)
        ds = [250.0, 300.0, 350.0, 320.0]
        verts = scaffold_loop_vertices(o, ds)
        for e, d in zip(o.edges, ds):
            v = verts[e.index]
            # 辺の始点から外向きに d だけ離れた線上に頂点がある
            offset = (
                (v[0] - e.start[0]) * e.outward[0]
                + (v[1] - e.start[1]) * e.outward[1]
            )
            self.assertAlmostEqual(offset, d, msg=f"辺{e.index}")

    def test_reflex_corner_moves_inward(self):
        """入隅のコーナー支柱は躯体の入隅より内側（建物側）へは来ない."""
        o = build_outline(LSHAPE)
        verts = scaffold_loop_vertices(o, [300.0] * len(o.edges))
        self.assertEqual(len(verts), len(o.edges))
        reflex = next(c for c in o.corners if c.kind == "入隅")
        v = verts[reflex.index]
        self.assertAlmostEqual(v[0], reflex.point[0] + 300.0)
        self.assertAlmostEqual(v[1], reflex.point[1] + 300.0)


if __name__ == "__main__":
    unittest.main()
