"""荷取りブラケットを付けた支柱は、系列にその許容値があればそれで検定する.

日建 p019: 支柱補剛材あり 15kN/本（ND1800）、p039: 強力つなぎ材あり 14.4kN/本（ND1900）。
一般部の支柱は局所荷重抜きで通常値、荷取り部は局所荷重込みでこの値、厳しい方が支配する。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all

ROOT = Path(__file__).resolve().parents[1]
STAGE = [{"edge_index": 0, "start_mm": 9145, "span_count": 2, "projection_mm": 1500,
          "load_kn": 9.8, "levels": [3]}]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


def base(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class TestStagePostCapacity(unittest.TestCase):
    def test_nd1800_stage_posts_use_the_loading_bracket_row(self):
        r = solve(dict(base("nikken_nd1800_rect.json"), loading_stages=STAGE))
        post = r.structural.post
        self.assertIn("荷取り部", post.governing)
        self.assertEqual(post.allowable_kn, 15.0)
        self.assertTrue(post.includes_extra)
        self.assertAlmostEqual(post.total_kn, post.dead_load_kn + post.live_load_kn + post.extra_load_kn, places=2)
        # 一般部の検定は参考行に出る
        self.assertTrue([c for c in post.other_checks if "一般部" in c], post.other_checks)
        self.assertTrue(post.ok, post)

    def test_without_a_stage_nothing_changes(self):
        r = solve(base("nikken_nd1800_rect.json"))
        post = r.structural.post
        self.assertEqual(post.allowable_kn, 12.0)
        self.assertNotIn("荷取り", post.governing)
        self.assertEqual(post.other_checks, [f"ジャッキ(繰出し{post.jack_extension_mm}mm): "
                                             f"{post.total_kn:.3f}kN / 24.5kN = {post.total_kn / 24.5:.3f}"])

    def test_series_without_the_row_keeps_the_single_check(self):
        r = solve(dict(base("rect_30x20.json"), loading_stages=[dict(STAGE[0], start_mm=9000)]))
        post = r.structural.post
        self.assertNotIn("荷取り部", post.governing)
        self.assertTrue(post.includes_extra)
        self.assertFalse([c for c in post.other_checks if "一般部" in c])

    def test_calc_sheet_prints_the_reference_rows(self):
        import re
        import zipfile

        from ashiba.notification import write_notification_xlsx

        r = solve(dict(base("nikken_nd1800_rect.json"), loading_stages=STAGE))
        with tempfile.TemporaryDirectory() as d:
            xl = Path(d) / "n.xlsx"
            write_notification_xlsx(r.model, r.quantity, r.checks, r.structural, xl, "t")
            z = zipfile.ZipFile(xl)
            names = re.findall(r'name="([^"]+)"', z.read("xl/workbook.xml").decode())
            calc3 = z.read(f"xl/worksheets/sheet{names.index('計算書3_建地圧縮') + 1}.xml").decode()
        self.assertIn("参考: 他の検定", calc3)
        self.assertIn("一般部", calc3)


if __name__ == "__main__":
    unittest.main()
