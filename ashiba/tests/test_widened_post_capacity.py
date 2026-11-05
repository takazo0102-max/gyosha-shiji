"""張出ブラケットの区間がある計画は、拡幅部の支柱許容支持力で検定する.

日建カタログ p025/p040: 拡幅部（張出・拡幅ブラケットを付けた支柱）の許容支持力は
通常より低い（ND1800 11.0→8.8kN/本、強力つなぎ材でも17.0→12.5）。区間があるのに
通常値で検定すると危険側。値の無い系列は通常値で検定して、その旨を警告する。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all

ROOT = Path(__file__).resolve().parents[1]
OUT = [{"edge_index": 0, "start_mm": 0, "end_mm": 5487, "width": 610, "direction": "張出", "levels": [1]}]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


def base(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class TestWidenedPostCapacity(unittest.TestCase):
    def test_nd1800_uses_the_widened_row(self):
        r = solve(dict(base("nikken_nd1800_rect.json"), bracket_sections=OUT))
        post = r.structural.post
        self.assertTrue(post.widened)
        self.assertEqual(post.allowable_kn, 8.8)
        self.assertIn("拡幅部", post.governing)
        self.assertEqual(post.widened_note, "")

    def test_nd1800_widened_with_strong_ties(self):
        r = solve(dict(base("nikken_nd1800_rect.json"), bracket_sections=OUT,
                       post_reinforcement="強力つなぎ材"))
        self.assertEqual(r.structural.post.allowable_kn, 12.5)

    def test_inner_sections_do_not_trigger_it(self):
        inner = [dict(OUT[0], direction="内", width=350, deck_width=240)]
        r = solve(dict(base("nikken_nd1800_rect.json"), bracket_sections=inner))
        self.assertFalse(r.structural.post.widened)
        self.assertEqual(r.structural.post.allowable_kn, 12.0)

    def test_series_without_the_row_warns_and_uses_the_normal_value(self):
        spec = dict(base("rect_30x20.json"), bracket_sections=[dict(OUT[0], width=600)])
        r = solve(spec)
        post = r.structural.post
        self.assertTrue(post.widened)
        self.assertTrue(post.widened_note)
        self.assertTrue([w for w in r.structural.warnings if "拡幅部" in w and "通常値" in w],
                        r.structural.warnings)
        self.assertTrue([w for w in r.warnings if "拡幅部" in w[2]], r.warnings)


    def test_opening_end_posts_use_the_same_row(self):
        """開口部の両端支柱の許容も、張出区間があれば拡幅部の値."""
        spec = dict(base("nikken_nd1800_rect.json"), bracket_sections=OUT,
                    openings=[{"edge_index": 2, "start_mm": 9145, "beam_span_mm": 3658, "level": 2}])
        r = solve(spec)
        self.assertEqual(r.structural.openings[0].end_post_allow_kn, 8.8)


if __name__ == "__main__":
    unittest.main()
