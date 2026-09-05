"""区間指定の意味の誤りは入口（入力検証）で止める.

向きの綴り違い・負の積載・終点が始点より前は、計画のNGではなく入力ミス。
是正項目に混ぜず、終了コード2の入力エラーにする。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, load_spec, solve_all

ROOT = Path(__file__).resolve().parents[1]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


def base():
    return json.loads((ROOT / "examples" / "nikken_nd1800_rect.json").read_text(encoding="utf-8"))


class TestSpecSemantics(unittest.TestCase):
    def _rejects(self, spec, needle):
        with self.assertRaises(InputError) as cm:
            solve(spec)
        self.assertIn(needle, str(cm.exception))

    def test_bracket_direction_typo(self):
        self._rejects(dict(base(), bracket_sections=[
            {"edge_index": 0, "start_mm": 0, "end_mm": 3658, "width": 610, "direction": "外", "levels": [1]}]),
            "direction: 内 か 張出")

    def test_bracket_end_before_start(self):
        self._rejects(dict(base(), bracket_sections=[
            {"edge_index": 0, "start_mm": 3658, "end_mm": 1829, "width": 610, "direction": "張出", "levels": [1]}]),
            "end_mm")

    def test_negative_stage_load(self):
        self._rejects(dict(base(), loading_stages=[
            {"edge_index": 0, "start_mm": 9145, "span_count": 2, "load_kn": -1, "levels": [3]}]),
            "load_kn")

    def test_zero_span_stage(self):
        self._rejects(dict(base(), loading_stages=[
            {"edge_index": 0, "start_mm": 9145, "span_count": 0, "levels": [3]}]),
            "span_count")

    def test_negative_edge_index(self):
        self._rejects(dict(base(), openings=[
            {"edge_index": -1, "start_mm": 9145, "beam_span_mm": 3658, "level": 2}]),
            "edge_index")

    def test_valid_sections_still_pass(self):
        r = solve(dict(base(), bracket_sections=[
            {"edge_index": 0, "start_mm": 0, "end_mm": 3658, "width": 610, "direction": "張出", "levels": [1]}]))
        self.assertTrue(r.verdict["ok"] or r.verdict["blockers"], r.verdict)


if __name__ == "__main__":
    unittest.main()
