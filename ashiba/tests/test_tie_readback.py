"""壁つなぎの部品を動かした・消した・足したのを読み戻す（利用者の指定 2026-10-20: 修正機能を充実させて）."""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import tie_placements
from ashiba.cli import solve_all, write_outputs
from ashiba.span_readback import ties_from_readback

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000}


def _plan(r):
    with tempfile.TemporaryDirectory() as d:
        write_outputs(r, Path(d))
        return json.loads((Path(d) / f"{r.name}_plan.json").read_text(encoding="utf-8"))


def _points(r):
    return [(p.x_mm, p.y_mm, p.params["zH"] * 1000.0) for p in tie_placements(r.model)]


class TestTieReadback(unittest.TestCase):
    def setUp(self):
        self.r = solve_all(dict(RECT))
        self.plan = _plan(self.r)

    def test_unchanged(self):
        ties, _notes = ties_from_readback(self.plan["edges"], _points(self.r), self.plan["wall_ties"])
        self.assertIsNone(ties)

    def test_deleted_and_moved(self):
        pts = _points(self.r)
        del pts[0]
        x, y, z = pts[0]
        pts[0] = (x + 1829.0 if abs(self.r.model.plan.edges[0].start_post[1] - y) < 1 else x, y, z)
        ties, notes = ties_from_readback(self.plan["edges"], pts, self.plan["wall_ties"])
        self.assertEqual(len(ties), len(self.r.model.wall_ties) - 1)
        self.assertTrue(any("壁つなぎ" in n for n in notes))
        # 高さは作業床の高さに戻る（部品は床の 300 下に付く）
        levels = set(self.r.model.elevation.level_heights)
        self.assertTrue(all(t["height_mm"] in levels for t in ties))

    def test_stray_part_is_ignored(self):
        # 足場の近く（支柱の範囲＋3m）の乗っていない部品は知らせ、別の建物の壁つなぎ（遠い）は数えない
        pts = _points(self.r) + [(15000.0, 10000.0, 3000.0)]
        ties, notes = ties_from_readback(self.plan["edges"], pts, self.plan["wall_ties"])
        self.assertIsNone(ties)
        self.assertTrue(any("乗っていない" in n and "1本" in n for n in notes))
        ties, notes = ties_from_readback(self.plan["edges"], _points(self.r) + [(999999.0, 999999.0, 3000.0)],
                                         self.plan["wall_ties"])
        self.assertIsNone(ties)
        self.assertFalse(any("乗っていない" in n for n in notes))

    def test_manual_ties_drive_the_solve(self):
        pts = _points(self.r)[:-3]
        ties, _ = ties_from_readback(self.plan["edges"], pts, self.plan["wall_ties"])
        r2 = solve_all({**RECT, "wall_ties_manual": ties})
        self.assertEqual(len(r2.model.wall_ties), len(ties))
        self.assertTrue(any("手で直した配置" in w for w in r2.model.plan.warnings))
        q1 = sum(l.qty for l in self.r.quantity.lines if l.part.category == "壁つなぎ")
        q2 = sum(l.qty for l in r2.quantity.lines if l.part.category == "壁つなぎ")
        self.assertEqual(q1 - q2, 3)


if __name__ == "__main__":
    unittest.main()
