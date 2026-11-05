"""入隅で2つの面の升目が重ならない（利用者の指摘 2026-10-24: 入りすみが重なっているよ）.

L 字の入隅で、隅で終わる面（北面(辺2)）と隅から始まる面（東面(辺3)）が、どちらも相手の内側建地列まで延びて
隅の 914×914 の升目を両方とも持ち、支柱・床が二重になっていた（実機の「足場計画」）。
"""

import unittest

from ashiba.cli import solve_groups
from ashiba.gdl_params import line_params

# 実機の「足場計画」の外形（L 字。頂点3が入隅）を原点へ寄せたもの
L = [[0, 0], [24000, 0], [24000, 8000], [12000, 8000], [12000, 16000], [0, 16000]]


def _solve():
    runs = solve_groups({"project_name": "入隅", "outline_mm": L, "series_id": "nikken_nd1800",
                         "eaves_height_mm": 15000, "scaffold_width_mm": 914})
    return runs[0][1]


class TestInnerCornerDoesNotOverlap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _solve()
        cls.m = cls.r.model
        cls.eps = {e.edge_index: e for e in cls.m.plan.edges}

    def _params(self, ei):
        return line_params(self.m, self.eps[ei], stair_plan=self.r.stair_plan)

    def test_through_face_starts_with_a_row_width_span(self):
        self.assertEqual([(a, b) for a, b, _g in self.m.inner_corner_joins], [(2, 3)])
        self.assertEqual(self.eps[3].spans[0], 914)

    def test_ending_face_stops_at_the_outer_post_line(self):
        a, b = self.eps[2], self.eps[3]
        row = self.m.post_row_spacing_mm
        # 北面(辺2)は西へ。東面(辺3)の外側建地列（内側建地列 + 914）で止まり、残りはコーナーステップ
        outer_x = b.start_post[0] + row
        self.assertAlmostEqual(a.end_post[0], outer_x, delta=0.6)
        last = a.start_post[0] - sum(a.spans)
        gap = next(c.gap_mm for c in self.m.plan.corner_steps if c.edge_index == 2)
        self.assertAlmostEqual(last - gap, outer_x, delta=0.6)
        self.assertGreaterEqual(last, outer_x - 0.6)                 # 隅の升目に入り込まない

    def test_joint_cell_is_walkable_and_closed_on_the_wall_side(self):
        p = self._params(3)
        self.assertEqual(p["endOpenS"], 1)                           # 躯体側（北面(辺2)の壁）に妻側の手すり
        self.assertTrue(p["editList"].startswith("1,1,1,"))          # 最初のスパンの外側の手すり・幅木を外す
        q = self.r.quantity
        self.assertFalse(any("入隅のつなぎ" in w for w in q.warnings))   # ツールが入れた編集は要確認にしない
        self.assertTrue(any("入隅のつなぎ" in n for n in q.notes))

    def test_corner_post_is_drawn_once(self):
        self.assertEqual(self._params(3)["skipInS"], 0)               # 隅の内側建地は通す面が描く


if __name__ == "__main__":
    unittest.main()
