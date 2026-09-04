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
        self.assertEqual(by["ND752P"].max_extension_mm(), 292)
        self.assertEqual(by["ND752SP"].max_extension_mm(), 432)
        self.assertIsNone(by["ECOPS"].max_extension_mm())

    def test_flat_site_uses_the_standard_jack_only(self):
        m = build("nikken_nd1800")
        q = take_off(m)
        self.assertEqual(qty(q, "ND752P"), 2 * m.plan.total_posts)
        self.assertEqual(qty(q, "ND752SP"), 0)

    def test_terraced_site_switches_the_long_feet_to_the_long_jack(self):
        m = build("nikken_nd1800")
        t = terrace(m, 1200)
        long_feet = sum(1 for f in t.feet if f.jack_mm > 292)
        self.assertGreater(long_feet, 0)
        q = take_off(m, terrain=t)
        self.assertEqual(qty(q, "ND752SP"), 2 * long_feet)
        self.assertEqual(qty(q, "ND752P") + qty(q, "ND752SP"), 2 * m.plan.total_posts)
        # アンダーベースは脚の数のまま
        self.assertEqual(qty(q, "ECOPS"), 2 * m.plan.total_posts)
        # 届かない脚は無い（432mmまでロングで受ける）ので敷板調整の手配は出ない
        self.assertFalse([n for n in q.warnings if "ジャッキの上限" in n], q.warnings)

    def test_series_without_limits_is_unchanged(self):
        m = build("shinwa_A")
        t = terrace(m, 1200)
        q = take_off(m, terrain=t)
        self.assertEqual(qty(q, "SE-6"), 2 * m.plan.total_posts)


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


if __name__ == "__main__":
    unittest.main()
