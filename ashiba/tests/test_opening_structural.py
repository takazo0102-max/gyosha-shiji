"""開口部（梁枠）の構造検定: 梁枠上の積載制限・支点の軸力・両端支柱の反力.

これまで capacity.csv の「開口部上方許容積載荷重」は読むだけで使っておらず、
梁枠の支点許容（日建 NDH36 16.0kN/支点）も検定していなかった。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all

ROOT = Path(__file__).resolve().parents[1]
OPEN = [{"edge_index": 0, "start_mm": 9145, "beam_span_mm": 3658, "level": 2}]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


def base(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class TestBeamAllowableParsing(unittest.TestCase):
    def test_takes_the_unconditional_value(self):
        from ashiba.master import Part
        from ashiba.structural import beam_support_allowable_kn

        nd = Part("x", "梁枠", "NDH36", 3658, 3658, 0, 24.5,
                  "トラス梁枠 2スパン 許容支持力18.5kN/支点(実大試験)・16.0kN(それ以外) 梁渡しNDHW併用")
        self.assertEqual(beam_support_allowable_kn(nd), 16.0)
        sh = Part("x", "梁枠", "SG-36N", 3600, 3600, 0, 23.3, "トラス梁枠 2スパン")
        self.assertIsNone(beam_support_allowable_kn(sh))


class TestOpeningCheck(unittest.TestCase):
    def test_nd1800_opening_is_checked(self):
        r = solve(dict(base("nikken_nd1800_rect.json"), openings=OPEN))
        self.assertEqual(len(r.structural.openings), 1)
        oc = r.structural.openings[0]
        post = r.structural.post
        self.assertEqual(oc.beam_model, "NDH36")
        self.assertEqual(oc.n_inner_posts, 1)
        # 梁枠上の積載 2.45×2スパン×2層＝9.8kN > 上限7.84 → 制限（1スパン1.96kN）
        self.assertAlmostEqual(oc.live_above_kn, 9.8)
        self.assertEqual(oc.live_limit_kn, 7.84)
        self.assertFalse(oc.live_ok)
        self.assertAlmostEqual(oc.live_per_span_limit_kn, 1.96)
        # 支点: 梁枠より上の自重＋制限後の1スパン積載 ≦ 16.0
        self.assertEqual(oc.support_allow_kn, 16.0)
        self.assertLess(oc.support_kn, post.dead_load_kn + 7.84 / 2 + 1e-6)
        self.assertTrue(oc.support_ok)
        # 両端支柱: 通常＋反力
        self.assertAlmostEqual(oc.end_post_kn, post.dead_load_kn + post.live_load_kn + oc.reaction_kn, places=2)
        self.assertEqual(oc.end_post_allow_kn, 12.0)
        self.assertTrue(oc.end_post_ok)
        # 積載制限は成立条件であって不成立ではない
        self.assertTrue(oc.ok)
        self.assertIn("1.96kN", oc.condition)
        self.assertTrue([n for n in r.structural.notes if "制限してください" in n], r.structural.notes)
        self.assertTrue([n for n in r.structural.notes if "両端支柱の軸力" in n], r.structural.notes)

    def test_series_without_beam_rating_asks_for_confirmation(self):
        r = solve(dict(base("rect_30x20.json"), openings=[dict(OPEN[0], start_mm=9000, beam_span_mm=3600)]))
        oc = r.structural.openings[0]
        self.assertIsNone(oc.support_allow_kn)
        self.assertTrue([w for w in r.structural.warnings if "支点当たり許容支持力がマスタに無く" in w],
                        r.structural.warnings)
        self.assertTrue([w for w in r.warnings if "支点当たり" in w[2]], r.warnings)

    def test_no_opening_no_check(self):
        r = solve(base("nikken_nd1800_rect.json"))
        self.assertEqual(r.structural.openings, [])

    def test_workbook_gets_the_beam_sheet_and_report_the_line(self):
        import re
        import zipfile

        from ashiba.notification import write_notification_xlsx
        from ashiba.report import write_report_md

        r = solve(dict(base("nikken_nd1800_rect.json"), openings=OPEN))
        with tempfile.TemporaryDirectory() as d:
            xl = Path(d) / "n.xlsx"
            write_notification_xlsx(r.model, r.quantity, r.checks, r.structural, xl, "t")
            z = zipfile.ZipFile(xl)
            names = re.findall(r'name="([^"]+)"', z.read("xl/workbook.xml").decode())
            self.assertIn("計算書4_開口部梁枠", names)
            sheet = z.read(f"xl/worksheets/sheet{names.index('計算書4_開口部梁枠') + 1}.xml").decode()
            self.assertIn("NDH36", sheet)
            self.assertIn("反力", sheet)
            md = Path(d) / "r.md"
            write_report_md(r.model, r.quantity, r.checks, md, "t", stair_plan=r.stair_plan,
                            structural=r.structural)
            self.assertIn("開口部 辺0 梁枠NDH36", md.read_text(encoding="utf-8"))


class TestDeadLoadUsesTheStandingPosts(unittest.TestCase):
    """開口部で抜いた建地は総重量を分担しない（数量のジャッキ数と同じ本数で割る）."""

    def test_post_count_excludes_removed_posts(self):
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "opening_beam.json"))
        self.assertGreater(r.openings.removed_posts, 0)
        expect = r.model.plan.total_posts * 2 - r.openings.removed_posts
        self.assertEqual(r.structural.post.n_posts, expect)
        jacks = sum(l.qty for l in r.quantity.lines
                    if l.part.category == "ジャッキ" and "アンダーベース" not in l.part.note)
        self.assertEqual(r.structural.post.n_posts, jacks)


if __name__ == "__main__":
    unittest.main()

