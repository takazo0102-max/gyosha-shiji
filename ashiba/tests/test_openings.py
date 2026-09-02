"""開口部（梁枠）のテスト.

マスタに梁枠はあるのに、CLIから開口部を渡す口が無く、数量にも出て
いなかった。梁枠は規格品でしか飛ばせないので、中間寸法を黙って丸めない。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.openings import (
    Opening,
    beam_sizes,
    opening_detail_specs,
    validate_openings,
)
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build():
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    return ScaffoldModel(
        master=master, plan=plan,
        elevation=solve_elevation(16300, master=master),
        config=ScaffoldConfig(),
    )


def ngs(r):
    return [i for i in r.issues if i.severity == "NG"]


class TestOpeningValidation(unittest.TestCase):
    def setUp(self):
        self.m = build()

    def test_catalog_sizes(self):
        self.assertEqual(beam_sizes(self.m), [3600, 5400])

    def test_standard_opening_is_accepted(self):
        r = validate_openings(self.m, [Opening(0, 3600, 3600)])
        self.assertEqual(ngs(r), [])
        self.assertTrue(r.ok)

    def test_non_catalog_span_is_ng(self):
        """梁枠は現場で切り詰められない."""
        r = validate_openings(self.m, [Opening(0, 3600, 4000)])
        self.assertTrue(any("規格外" in i.message for i in ngs(r)))

    def test_off_post_position_is_ng(self):
        r = validate_openings(self.m, [Opening(0, 900, 3600)])
        self.assertTrue(any("支柱位置に一致しません" in i.message for i in ngs(r)))

    def test_past_the_face_is_ng(self):
        edge = self.m.plan.edges[0]
        r = validate_openings(
            self.m, [Opening(0, edge.scaffold_length - 1800, 3600)]
        )
        self.assertTrue(any("超えています" in i.message for i in ngs(r)))

    def test_overlap_is_ng(self):
        r = validate_openings(
            self.m, [Opening(0, 3600, 5400), Opening(0, 5400, 3600)]
        )
        self.assertTrue(any("重なっています" in i.message for i in ngs(r)))

    def test_removed_posts_counted_for_both_rows(self):
        r = validate_openings(self.m, [Opening(0, 3600, 3600)])
        self.assertEqual(r.removed_posts, 2)      # 中間支柱1本×内外2列
        r5 = validate_openings(self.m, [Opening(0, 3600, 5400)])
        self.assertEqual(r5.removed_posts, 4)

    def test_reinforcement_is_always_warned(self):
        """梁枠の両端支柱は集中荷重を受ける。黙って通さない."""
        r = validate_openings(self.m, [Opening(0, 3600, 3600)])
        self.assertTrue(any("両端支柱の補強" in i.message for i in r.issues))

    def test_missing_nearby_tie_is_warned(self):
        m = build()
        m.wall_ties = []
        r = validate_openings(m, [Opening(0, 3600, 3600)])
        self.assertTrue(any("壁つなぎがありません" in i.message for i in r.issues))


class TestOpeningQuantity(unittest.TestCase):
    def test_beam_appears_in_the_bom(self):
        m = build()
        r = validate_openings(m, [Opening(0, 3600, 3600)])
        q = take_off(m, openings=r)
        self.assertEqual(q.qty_of("梁枠", 3600), 1)
        self.assertTrue(any("支柱2本を抜いています" in n for n in q.notes))

    def test_no_openings_changes_nothing(self):
        m = build()
        base = take_off(m)
        with_empty = take_off(m, openings=validate_openings(m))
        self.assertEqual(base.total_weight_kg, with_empty.total_weight_kg)

    def test_detail_specs_are_derived(self):
        m = build()
        r = validate_openings(m, [Opening(0, 3600, 3600), Opening(1, 3600, 5400)])
        self.assertEqual(
            [s["beam_span_mm"] for s in opening_detail_specs(r)], [3600, 5400]
        )

    def test_detail_specs_carry_the_posts_on_the_beam(self):
        """図がスパン割から推定すると、割付と本数が食い違う."""
        m = build()
        r = validate_openings(m, [Opening(0, 3600, 3600), Opening(1, 3600, 5400)])
        specs = opening_detail_specs(r)
        # 1800割なら 3600 に1本、5400 に2本乗る
        self.assertEqual(len(specs[0]["inner_posts_mm"]), 1)
        self.assertEqual(len(specs[1]["inner_posts_mm"]), 2)
        for s in specs:
            for v in s["inner_posts_mm"]:
                self.assertTrue(0 < v < s["beam_span_mm"], v)


if __name__ == "__main__":
    unittest.main()
