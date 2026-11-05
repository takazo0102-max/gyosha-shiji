"""一部の面だけの足場と開放端の手すり（参考: smartCON Planner の「墜落の危険箇所に手すり」「エンドストッパー」）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
        "series_id": "nikken_nd1800"}


class TestPartialFaces(unittest.TestCase):
    def test_only_the_named_faces_are_built(self):
        r = solve_all({**RECT, "faces": "南面,東面"})
        self.assertEqual([e.edge_index for e in r.model.plan.edges], [0, 1])
        self.assertEqual(r.model.plan.face_names(), ["南面", "東面"])
        self.assertEqual(r.model.outer_corner_posts(), 1)            # 南東の隅だけ

    def test_open_ends_get_end_rails(self):
        r = solve_all({**RECT, "faces": ["南面", "東面"]})
        south = line_params(r.model, r.model.plan.edges[0])
        east = line_params(r.model, r.model.plan.edges[1])
        self.assertEqual((south["endOpenS"], south["endOpenE"]), (1, 0))
        self.assertEqual((east["endOpenS"], east["endOpenE"]), (0, 1))
        self.assertEqual(south["cornerS"], 0)                         # 開放端に外側コーナーは付けない
        self.assertTrue(any("開放端2箇所" in n for n in r.quantity.notes))

    def test_all_faces_is_the_normal_loop(self):
        r = solve_all({**RECT, "faces": "南,東,北,西"})
        self.assertIsNone(r.model.faces_only)

    def test_unknown_face(self):
        from ashiba.cli import InputError

        with self.assertRaises(InputError):
            solve_all({**RECT, "faces": "上面"})


if __name__ == "__main__":
    unittest.main()
