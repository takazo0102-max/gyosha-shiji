"""ジャッキは脚ごとの繰出し量に合う品で数える（ロングジャッキ）.

日建 ND752P は繰出し最大292mm。高低差の敷地で444mm伸ばす脚があるのに、
数量は平坦時の1品で全脚を数えていた（ジャッキ量一覧と食い違う）。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.terrain import GroundModel, solve_post_feet

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(series):
    master = load_master(series)
    return ScaffoldModel(master=master, plan=solve_plan(RECT, master),
                         elevation=solve_elevation(16300, master=master),
                         config=ScaffoldConfig(), building_height_mm=16000)


def terrace(m, drop):
    return solve_post_feet(m, GroundModel(points=[
        (0, 0, drop), (30000, 0, 0), (30000, 20000, 0), (0, 20000, drop)]))


def qty(q, model_no):
    return sum(l.qty for l in q.lines if l.part.model_no == model_no)


class TestJackSelection(unittest.TestCase):
    def test_master_knows_the_extension_limits(self):
        m = load_master("nikken_nd1800")
        by = {p.model_no: p for p in m.by_category("ジャッキ")}
        # A752 は調節長262（カタログ p078）。ロング ND752SP は調節長432だが、ND1800 の組立・解体マニュアル「繰出し長を
        # 350mmを超えて使用しないこと」に合わせて 350 で止める（2026-10-25 の調査）
        self.assertEqual(by["A752"].max_extension_mm(), 262)
        self.assertEqual(by["ND752SP"].max_extension_mm(), 350)
        self.assertIsNone(by["ECOPS"].max_extension_mm())

    def test_flat_site_uses_the_standard_jack_only(self):
        m = build("nikken_nd1800")
        q = take_off(m)
        self.assertEqual(qty(q, "A752"), 2 * m.plan.total_posts + m.outer_corner_posts() + m.gap_corner_posts())
        self.assertEqual(qty(q, "ND752SP"), 0)

    def test_terraced_site_switches_the_long_feet_to_the_long_jack(self):
        m = build("nikken_nd1800")
        t = terrace(m, 1200)
        long_feet = sum(1 for f in t.feet if f.jack_mm > 262)      # A752 の繰出し最大 262（2026-10-25 から標準）
        self.assertGreater(long_feet, 0)
        q = take_off(m, terrain=t)
        self.assertEqual(qty(q, "ND752SP"), 2 * long_feet)
        feet_total = 2 * m.plan.total_posts + m.outer_corner_posts() + m.gap_corner_posts()
        self.assertEqual(qty(q, "A752") + qty(q, "ND752SP"), feet_total)
        # アンダーベースは脚の数のまま
        self.assertEqual(qty(q, "ECOPS"), feet_total)
        # 届かない脚は無い（350mmまでロングで受け、超える分は敷板で持ち上げる）
        self.assertFalse([n for n in q.warnings if "ジャッキの上限" in n], q.warnings)

    def test_series_without_limits_is_unchanged(self):
        m = build("shinwa_A")
        t = terrace(m, 1200)
        q = take_off(m, terrain=t)
        self.assertEqual(qty(q, "SE-6"), 2 * m.plan.total_posts + m.outer_corner_posts() + m.gap_corner_posts())


class TestOpeningHint(unittest.TestCase):
    def test_misaligned_beam_gets_a_concrete_hint(self):
        from ashiba.openings import Opening, validate_openings

        m = build("nikken_nd1800")
        posts = [0.0]
        for s in m.plan.edges[0].spans:
            posts.append(posts[-1] + s)
        start = posts[3] + 7          # 支柱から7mmずれた指定
        r = validate_openings(m, [Opening(0, start, 3658, level=2)])
        ng = [i for i in r.issues if i.severity == "NG" and "一致しません" in i.message]
        self.assertTrue(ng, [i.message for i in r.issues])
        self.assertIn(f"始点を{posts[3]:.0f}mmにすれば", ng[0].message)


class TestHoistGate(unittest.TestCase):
    """昇降機の乗り込み口の開閉式手すりは、カタログのスイングドア KSSD で拾う."""

    def test_landing_gates_are_counted(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        for name in ("combo_nd1800.json", "waku_composite.json"):
            with self.subTest(name):
                r = solve_all(load_spec(root / "examples" / name))
                n_landings = sum(len(h.landings(r.model)) for h in r.platforms.hoists)
                self.assertGreater(n_landings, 0)
                self.assertEqual(qty(r.quantity, "KSSD"), n_landings)
                self.assertFalse([w for w in r.quantity.warnings if "開閉式手すり" in w and "ありません" in w],
                                 r.quantity.warnings)


class TestStaggerAndShim(unittest.TestCase):
    """2026-10-25 の調査を受けた決め（利用者の指定 2026-10-25: 1〜4直して）."""

    SPEC = {"project_name": "a", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
            "eaves_height_mm": 9000, "series_id": "nikken_nd1800"}

    def test_stagger_is_drawn_and_counted_for_every_other_post(self):
        from ashiba.cli import solve_all
        from ashiba.gdl_params import line_params

        plain = solve_all(self.SPEC)
        st = solve_all({**self.SPEC, "post_stagger": True})
        e = st.model.elevation
        self.assertNotEqual(e.posts, e.posts_alt)
        self.assertEqual(line_params(plain.model, plain.model.plan.edges[0])["postListAlt"], "")
        self.assertEqual(line_params(st.model, st.model.plan.edges[0])["postListAlt"],
                         ",".join(str(v) for v in e.posts_alt))
        self.assertGreater(qty(st.quantity, "NDP09N"), 0)                 # 隣の支柱の1段目 900
        self.assertLess(qty(st.quantity, "NDP27N"), qty(plain.quantity, "NDP27N"))

    def test_setback_tier_lifts_the_jacks_with_sill_shims(self):
        # ロングを 350 で止めると上段の床をそろえる繰出し 400 に届かない。足りない分は全部の脚の下に敷板
        from ashiba.cli import solve_groups
        from ashiba.gdl_params import line_params

        # 実機の「足場計画」（10m 角、東半分が GL+3000 の屋根、西半分が GL+9700 まで）
        full = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
        west = [[0, 0], [5000, 0], [5000, 10000], [0, 10000]]
        slabs = ([{"polygon_mm": full, "top_mm": t} for t in (0, 3000)]
                 + [{"polygon_mm": west, "top_mm": t} for t in (6000, 9000, 9700)])
        g = solve_groups({"project_name": "S", "outline_mm": full, "slabs": slabs, "module": "inch",
                          "series_id": "nikken_nd1800", "scaffold_width_mm": 914, "eaves_height_mm": 15400})
        tier = g[2][1]
        e = tier.model.elevation
        jmax = max(p.max_extension_mm() or 0 for p in tier.model.master.by_category("ジャッキ"))
        self.assertLessEqual(e.jack_extension - e.base_shim, jmax)
        self.assertEqual(e.base_shim % 35, 0)
        self.assertAlmostEqual(line_params(tier.model, tier.model.plan.edges[0])["shimAll"], e.base_shim / 1000.0)
        self.assertGreater(e.base_shim, 0)                                # 実機では繰出し 330 ＋敷板2枚（70）
        self.assertTrue(any("敷板を" in n for n in tier.quantity.notes), tier.quantity.notes)
        # 標準のジャッキベース（262）で届かない繰出しはロングで数える
        self.assertGreater(qty(tier.quantity, "ND752SP"), 0)
        self.assertEqual(qty(tier.quantity, "A752"), 0)


class TestJackHardMaxBySeries(unittest.TestCase):
    """ジャッキの機械的上限は系列で違う: 枠組350（構造規格）、ND 350（ロング。マニュアルの上限）、信和450."""

    def test_limits(self):
        self.assertEqual(load_master("waku").jack_hard_max_mm(), 350)
        self.assertEqual(load_master("nikken_nd1800").jack_hard_max_mm(), 350)
        self.assertEqual(load_master("shinwa_A").jack_hard_max_mm(), 450)

    def test_terrain_respects_the_frame_limit(self):
        m = build("waku")
        t = terrace(m, 1200)
        self.assertLessEqual(max(f.jack_mm for f in t.feet), 350 + 1e-6)
        # 届かない分は敷板調整として明示される
        self.assertTrue(any(f.base_plate_adjust_mm > 0 for f in t.feet)
                        or all(f.jack_mm <= 350 for f in t.feet))

    def test_terrain_respects_the_nd_long_jack(self):
        m = build("nikken_nd1800")
        t = terrace(m, 1200)
        self.assertLessEqual(max(f.jack_mm for f in t.feet), 432 + 1e-6)


class TestShims(unittest.TestCase):
    """敷板調整の脚には敷板（厚35）を枚数換算で計上する."""

    def test_frame_site_beyond_the_jack_gets_shims(self):
        import math

        m = build("waku")
        t = terrace(m, 1200)
        raised = [f for f in t.feet if f.base_plate_adjust_mm > 0]
        self.assertTrue(raised)
        q = take_off(m, terrain=t)
        expect = sum(math.ceil(f.base_plate_adjust_mm / 35 - 1e-9) for f in raised) * 2
        self.assertEqual(qty(q, "S3503B"), expect)
        self.assertTrue([n for n in q.notes if "敷板調整の脚" in n], q.notes)

    def test_flat_site_has_no_shims(self):
        m = build("waku")
        q = take_off(m, terrain=terrace(m, 0))
        self.assertEqual(qty(q, "S3503B"), 0)

    def test_series_without_shims_gets_an_order_note(self):
        m = build("shinwa_A")
        t = terrace(m, 6000)
        raised = [f for f in t.feet if f.base_plate_adjust_mm > 0]
        q = take_off(m, terrain=t)
        if raised:
            self.assertTrue([n for n in q.warnings if "敷板がマスタに無い" in n], q.warnings)
        else:
            self.assertFalse([n for n in q.warnings if "敷板" in n])


if __name__ == "__main__":
    unittest.main()
