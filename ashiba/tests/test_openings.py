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


def build_frame():
    master = load_master("waku")
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
        # 内外の建地列に1枚ずつ（本足場は2枚）
        self.assertEqual(q.qty_of("梁枠", 3600), 2)
        self.assertTrue(any("支柱2本を抜いています" in n for n in q.notes))

    def test_frame_scaffold_says_kenwaku_not_shichu(self):
        """枠組の開口部は建枠を抜く。届出・数量で「支柱」と書かない."""
        m = build_frame()
        beam = beam_sizes(m)[0]      # waku の梁枠(3658)
        r = validate_openings(m, [Opening(0, 1829, beam, level=2)])
        # WARN メッセージが建枠語彙
        warn = next(i for i in r.issues if "梁枠" in i.message and i.severity == "WARN")
        self.assertIn("建枠", warn.message)
        self.assertNotIn("支柱", warn.message)
        # 数量の注記も建枠
        q = take_off(m, openings=r)
        self.assertTrue(any("建枠" in n and "抜いています" in n for n in q.notes))
        self.assertFalse(any("支柱" in n and "抜いています" in n for n in q.notes))

    def test_wedge_scaffold_still_says_shichu(self):
        m = build()
        r = validate_openings(m, [Opening(0, 3600, 3600)])
        warn = next(i for i in r.issues if "梁枠" in i.message and i.severity == "WARN")
        self.assertIn("支柱", warn.message)
        self.assertNotIn("建枠", warn.message)

    def test_no_openings_changes_nothing(self):
        m = build()
        base = take_off(m)
        with_empty = take_off(m, openings=validate_openings(m))
        self.assertEqual(base.total_weight_kg, with_empty.total_weight_kg)

    def test_floor_below_the_beam_is_not_counted(self):
        """梁枠より下は通路。床も幅木も無いのに数えていた."""
        m = build()
        base = take_off(m)
        r = validate_openings(m, [Opening(0, 3600, 5400, level=3)])
        q = take_off(m, openings=r)
        edge = m.plan.edges[0]
        # 開口が占有するスパン数 × 梁枠より下の層数 × 踏板2枚
        spans = sum(1 for i, s in enumerate(edge.spans)
                    if 3600 - 1e-6 <= sum(edge.spans[:i]) < 3600 + 5400 - 1e-6)
        cells = spans * 2
        self.assertEqual(base.qty_of("踏板") - q.qty_of("踏板"), cells * 2)
        self.assertEqual(base.qty_of("幅木") - q.qty_of("幅木"), cells)

    def test_opening_at_the_lowest_level_removes_nothing(self):
        """1層目に梁枠を置く指定では、下に層が無いので差し引きも無い."""
        m = build()
        base = take_off(m)
        q = take_off(m, openings=validate_openings(
            m, [Opening(0, 3600, 3600, level=1)]))
        self.assertEqual(base.qty_of("踏板"), q.qty_of("踏板"))

    def test_low_headroom_warns(self):
        """通路として使う開口なので頭上高さが要る."""
        from ashiba.openings import MIN_HEADROOM_MM

        m = build()
        m.elevation.level_heights[0] = MIN_HEADROOM_MM - 100
        msgs = [i.message for i in
                validate_openings(m, [Opening(0, 3600, 3600, level=1)]).issues]
        self.assertTrue(any("開口高さ" in x for x in msgs), msgs)

    def test_detail_sheet_gets_the_real_opening_height(self):
        """図が階高2層ぶんと決め打ちすると、実際と違う通路高さを示す."""
        m = build()
        specs = opening_detail_specs(
            validate_openings(m, [Opening(0, 3600, 3600, level=2)])
        )
        self.assertEqual(specs[0]["beam_height_mm"], m.elevation.level_heights[1])

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


class TestBeamSaddle(unittest.TestCase):
    """日建NDは梁枠上の支柱を梁渡し（NDHW）に立てる。梁枠上の支柱1本に1個."""

    def test_nd1800_counts_one_saddle_per_inner_post_and_two_beams(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "examples" / "nikken_nd1800_rect.json").read_text(encoding="utf-8"))
        spec["openings"] = [{"edge_index": 0, "start_mm": 9145, "beam_span_mm": 3658, "level": 2}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        q = r.quantity
        self.assertEqual(q.qty_of("梁枠", 3658), 2)
        self.assertEqual(q.qty_of("梁渡し"), 1)               # 2スパン梁枠に乗る支柱1本
        self.assertEqual(q.qty_of("梁渡し", 610), 1)          # 建地列間隔610 → NDHW06
        self.assertFalse([n for n in q.warnings if "梁渡し" in n], q.warnings)

    def test_series_without_saddles_is_silent(self):
        from ashiba.openings import Opening, validate_openings

        m = build()
        op = validate_openings(m, [Opening(0, 3600, 3600, level=2)])
        q = take_off(m, openings=op)
        self.assertEqual(q.qty_of("梁渡し"), 0)
        self.assertFalse([n for n in q.warnings if "梁渡し" in n])


if __name__ == "__main__":
    unittest.main()


class TestOpeningStacksAreShortened(unittest.TestCase):
    """開口部で抜いた鉛直部材は梁枠上（作業床〜天端）だけの構成で数える."""

    def test_wedge_posts_total_length_drops_by_the_beam_height(self):
        from ashiba.quantity import take_off

        m = build()
        op = validate_openings(m, [Opening(0, 3600, 3600, level=2)])
        base = take_off(m)
        with_op = take_off(m, openings=op)

        def total_mm(q):
            return sum(l.part.nominal_dim * l.qty for l in q.lines
                       if l.part.category == "支柱" and "根がらみ" not in l.part.note)

        beam_h = op.beam_heights[0]
        full = sum(m.elevation.posts)
        above = m.elevation.total_height - beam_h
        expect_drop = op.removed_posts * (full - above)
        self.assertEqual(total_mm(base) - total_mm(with_op), expect_drop)
        self.assertTrue([n for n in with_op.notes if "梁枠上（作業床〜天端）の構成で計上" in n], with_op.notes)
        self.assertFalse([n for n in with_op.warnings if "拾い直して" in n])

    def test_frame_stacks_and_pins_shrink(self):
        from ashiba.quantity import take_off

        m = build_frame()
        op = validate_openings(m, [Opening(0, 3658, 3658, level=2)])
        base = take_off(m)
        with_op = take_off(m, openings=op)
        frames = lambda q: sum(l.part.nominal_dim * l.qty for l in q.lines if l.part.category == "建枠")
        beam_h = op.beam_heights[0]
        above = m.elevation.total_height - beam_h
        self.assertEqual(frames(base) - frames(with_op),
                         op.removed_posts * (sum(m.elevation.posts) - above))
        self.assertLess(with_op.qty_of("連結ピン"), base.qty_of("連結ピン"))

