"""辺番号は正規化後の頂点順。外形を整理したときは黙らずに言う."""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all
from ashiba.geometry import build_outline

ROOT = Path(__file__).resolve().parents[1]
RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


class TestEdgeNumbering(unittest.TestCase):
    def test_clockwise_input_is_noted(self):
        o = build_outline(list(reversed(RECT)))
        self.assertTrue([n for n in o.notes if "時計回り" in n and "辺番号" in n], o.notes)
        self.assertEqual(build_outline(RECT).notes, [])

    def test_features_on_a_normalised_outline_get_a_warning(self):
        base = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        spec = dict(base, outline_mm=[list(v) for v in reversed(RECT)],
                    openings=[{"edge_index": 0, "start_mm": 9000, "beam_span_mm": 3600, "level": 2}])
        r = solve(spec)
        hit = [w for w in r.model.plan.warnings if "辺番号" in w and "openings" in w]
        self.assertTrue(hit, r.model.plan.warnings)
        # 整理していない外形・辺指定なしなら出ない
        plain = solve(dict(base, outline_mm=[list(v) for v in RECT]))
        self.assertFalse([w for w in plain.model.plan.warnings if "辺番号" in w])

    def test_report_table_shows_the_building_vertex(self):
        from ashiba.report import write_report_md

        base = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        r = solve(base)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.md"
            write_report_md(r.model, r.quantity, r.checks, path, "t", stair_plan=r.stair_plan)
            text = path.read_text(encoding="utf-8")
        self.assertIn("躯体頂点(始点)", text)
        self.assertIn("| 0 | 南面 | (0, 0) |", text)


if __name__ == "__main__":
    unittest.main()
