"""平面に引いた線から面と位置を読む（利用者の指定 2026-10-24: 階段の位置・区切る・面の切替も平面の線で）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.plan_pick import across, along, frame, nearest_post, posts_of, spans_covered

ROOT = Path(__file__).resolve().parents[1]

# 面2つ（南面: x 方向、東面: y 方向）。建地列の間隔 914、スパン 1829×5
SOUTH = {"edge_index": 0, "face": "南面", "start_post": [0.0, 0.0], "end_post": [9145.0, 0.0],
         "gdl_params": {"spanList": "1829,1829,1829,1829,1829", "rowW": 0.914}}
EAST = {"edge_index": 1, "face": "東面", "start_post": [9145.0, 0.0], "end_post": [9145.0, 9145.0],
        "gdl_params": {"spanList": "1829,1829,1829,1829,1829", "rowW": 0.914}}
EDGES = [SOUTH, EAST]


def _pt(e, t, n):
    o, u, nrm, _ln = frame(e)
    return (o[0] + u[0] * t + nrm[0] * n, o[1] + u[1] * t + nrm[1] * n)


class TestPlanPick(unittest.TestCase):
    def test_along_picks_the_face_and_range(self):
        e, t0, t1 = along(EDGES, _pt(SOUTH, 2000, -400), _pt(SOUTH, 5300, -400))
        self.assertEqual(e["face"], "南面")
        self.assertAlmostEqual(t0, 2000)
        self.assertAlmostEqual(t1, 5300)
        self.assertEqual(along(EDGES, _pt(EAST, 1000, -300), _pt(EAST, 4000, -300))[0]["face"], "東面")
        self.assertIsNone(along(EDGES, _pt(SOUTH, 2000, 5000), _pt(SOUTH, 5300, 5000)))     # 躯体の奥

    def test_across_picks_the_crossing_point(self):
        e, t = across(EDGES, _pt(SOUTH, 3700, 300), _pt(SOUTH, 3600, -1300))
        self.assertEqual(e["face"], "南面")
        self.assertTrue(3600 < t < 3700)
        self.assertEqual(nearest_post(e, t), 3658)
        self.assertIsNone(across(EDGES, _pt(SOUTH, 2000, -400), _pt(SOUTH, 5000, -400)))   # 沿っている線

    def test_spans_covered(self):
        self.assertEqual(posts_of(SOUTH)[:3], [0.0, 1829.0, 3658.0])
        self.assertEqual(spans_covered(SOUTH, 1700, 5400), (1829.0, 2))
        self.assertEqual(spans_covered(SOUTH, 3000, 3100), (1829.0, 1))      # 半分かからない短い線はいちばん近い1スパン

    def test_scripts_use_plan_lines(self):
        for f in ("split_line.py", "switch_face_form.py", "stair_move_run.py"):
            self.assertIn("selected_guides", (ROOT / "scripts" / f).read_text(encoding="utf-8"), f)
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("階段の位置", [a.title for a in ACTIONS])
        self.assertIn("階段の位置", dict(PANEL_GROUPS)["直す"])

    def test_stair_positions_after_moving(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import stair_move_run as S

        towers = [{"edge_index": 0, "start_mm": 1829.0, "span_count": 2, "length_mm": 3658},
                  {"edge_index": 2, "start_mm": 5487.0, "span_count": 2, "length_mm": 3658}]
        faces = {0: "南面", 2: "北面"}
        labels = [S.tower_label(faces[t["edge_index"]], t) for t in towers]
        pos = S.positions_after(towers, faces, labels[0], labels, "東面", 3658.0, 2)
        self.assertEqual([(p["face"], p["start_mm"]) for p in pos], [("北面", 5487.0), ("東面", 3658.0)])
        pos = S.positions_after(towers, faces, S.NEW, labels, "東面", 3658.0, 2)
        self.assertEqual(len(pos), 3)


if __name__ == "__main__":
    unittest.main()
