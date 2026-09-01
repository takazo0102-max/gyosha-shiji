"""枠組足場（建枠方式）のテスト.

くさび式（支柱＋布材）と枠組式（建枠）は構造が根本的に違うので、
立面の解き方も数量ルールも分岐する。従属部材（アームロック・連結ピン）は
建枠数から自動算出する（仕様3.1）。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation, solve_elevation_frame
from ashiba.law_check import run_all_checks, summary
from ashiba.master import FRAME, WEDGE, load_master
from ashiba.model import FRAME_GUARD_RAIL_HEIGHT_MM, AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.stairs import auto_place_stairs

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build_frame(height=16300):
    master = load_master("waku")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)), building_height_mm=16000,
    )


class TestSystemType(unittest.TestCase):
    def test_series_declare_system(self):
        self.assertEqual(load_master("shinwa_A").system_type, WEDGE)
        self.assertEqual(load_master("waku").system_type, FRAME)
        self.assertFalse(load_master("shinwa_A").is_frame)
        self.assertTrue(load_master("waku").is_frame)

    def test_frame_catalog(self):
        m = load_master("waku")
        self.assertEqual(m.frame_heights(), [1700, 1200, 900])
        self.assertEqual(m.frame_widths(), [1219, 914, 610])
        # 建枠間隔はインチ規格
        self.assertIn(1829, m.span_lengths())


class TestFrameElevation(unittest.TestCase):
    def test_stacks_frames_not_posts(self):
        m = load_master("waku")
        r = solve_elevation_frame(16300, m)
        self.assertEqual(r.total_height, 16300)
        for h in r.posts:
            self.assertIn(h, m.frame_heights())
        # 標準枠が下、調整枠が上
        self.assertEqual(r.posts, sorted(r.posts, reverse=True))

    def test_solve_elevation_dispatches_by_system(self):
        m = load_master("waku")
        direct = solve_elevation_frame(16300, m)
        dispatched = solve_elevation(16300, master=m)
        self.assertEqual(dispatched.posts, direct.posts)

    def test_levels_equal_frame_stages(self):
        m = load_master("waku")
        r = solve_elevation_frame(16300, m)
        # 最上段は手すり分なので作業層は段数-1
        self.assertEqual(r.n_levels, len(r.posts) - 1)

    def test_unsolvable_raises(self):
        m = load_master("waku")
        with self.assertRaises(ValueError):
            solve_elevation_frame(100, m)


class TestFrameQuantity(unittest.TestCase):
    def setUp(self):
        self.m = build_frame()
        self.q = take_off(self.m, stair_plan=auto_place_stairs(self.m))

    def test_no_missing_parts(self):
        self.assertEqual(
            [n for n in self.q.notes if "該当部材がありません" in n], []
        )

    def test_frame_width_fits_deck(self):
        """建枠幅は「近い幅」ではなく「布板が載る最小幅」を選ぶ."""
        frames = [l for l in self.q.lines if l.part.category == "建枠"]
        self.assertTrue(frames)
        need = self.m.deck_width_total
        for line in frames:
            width = int(line.part.note.split("幅")[1].split()[0])
            self.assertGreaterEqual(width, need)

    def test_armlock_from_frame_count(self):
        """アームロックは構面数×段数（建枠2枚に1個）."""
        n_bays = self.m.plan.total_spans
        n_stages = len(self.m.elevation.posts)
        self.assertEqual(self.q.qty_of("アームロック"), n_bays * n_stages)

    def test_joint_pin_from_stacking(self):
        """連結ピンは縦継ぎ1箇所に1本＝(段数-1)×建枠列数."""
        n_stages = len(self.m.elevation.posts)
        self.assertEqual(
            self.q.qty_of("連結ピン"),
            (n_stages - 1) * self.m.plan.total_posts,
        )

    def test_no_wedge_only_parts(self):
        """枠組では支柱・踏板（くさび式の部材）を使わない."""
        cats = {l.part.category for l in self.q.lines}
        self.assertNotIn("支柱", cats)
        self.assertNotIn("踏板", cats)
        self.assertIn("建枠", cats)
        self.assertIn("布板", cats)

    def test_all_parts_from_frame_series(self):
        for line in self.q.lines:
            self.assertEqual(line.part.series_id, "waku", line.part.model_no)

    def test_cross_braces_cover_all_spans(self):
        n_bays = self.m.plan.total_spans
        n_stages = len(self.m.elevation.posts)
        self.assertEqual(self.q.qty_of("筋交"), n_bays * n_stages)


class TestFrameLawChecks(unittest.TestCase):
    def test_guard_rail_from_frame_not_koma(self):
        """枠組はコマピッチの概念がないので、建枠の手すり高さを使う."""
        m = build_frame()
        self.assertEqual(m.master.koma_pitch, 0)
        self.assertEqual(m.guard_rail_height_mm, FRAME_GUARD_RAIL_HEIGHT_MM)
        self.assertGreaterEqual(m.guard_rail_height_mm, 850)

    def test_all_checks_pass(self):
        m = build_frame()
        s = summary(run_all_checks(m))
        self.assertEqual(s["total"], 11)
        ngs = [c for c in run_all_checks(m) if c.status == "NG"]
        self.assertEqual(ngs, [], [(c.name, c.message) for c in ngs])

    def test_explicit_guard_rail_overrides(self):
        m = build_frame()
        m.config.guard_rail_height_mm = 1000
        self.assertEqual(m.guard_rail_height_mm, 1000)


if __name__ == "__main__":
    unittest.main()
