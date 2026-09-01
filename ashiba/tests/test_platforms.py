"""荷受けステージ・昇降機のテスト.

どちらも局所的に大きな荷重・反力が入るので、
全体平均ではなく「直下の建地」を個別に見る必要がある。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.platforms import (
    CANTILEVER_AMPLIFICATION,
    Hoist,
    LoadingStage,
    platform_quantities,
    stage_post_load_kn,
    validate_platforms,
)
from ashiba.quantity import take_off
from ashiba.structural import run_structural

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build():
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(16300, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)), building_height_mm=16000,
    )


def stage(**kw):
    base = dict(edge_index=0, start_mm=12600, span_count=2,
                projection_mm=1500, load_kn=9.8, levels=[3])
    base.update(kw)
    return LoadingStage(**base)


def ngs(result):
    return [i for i in result.issues if i.severity == "NG"]


class TestStageValidation(unittest.TestCase):
    def setUp(self):
        self.m = build()

    def test_valid_stage_passes(self):
        self.assertEqual(ngs(validate_platforms(self.m, [stage()])), [])

    def test_guard_rail_required(self):
        r = validate_platforms(self.m, [stage(has_guard_rail=False)])
        self.assertTrue(any("手すり" in i.message for i in ngs(r)))

    def test_toe_board_required(self):
        r = validate_platforms(self.m, [stage(has_toe_board=False)])
        self.assertTrue(any("幅木" in i.message for i in ngs(r)))

    def test_load_sign_required(self):
        """最大積載荷重の表示義務（安衛則655条）."""
        r = validate_platforms(self.m, [stage(has_load_sign=False)])
        issues = ngs(r)
        self.assertTrue(any("最大積載荷重" in i.message for i in issues))
        self.assertTrue(any("655" in i.basis for i in issues))

    def test_hozue_required_for_cantilever(self):
        r = validate_platforms(self.m, [stage(has_hozue=False)])
        self.assertTrue(any("方杖" in i.message for i in ngs(r)))

    def test_large_projection_warns(self):
        r = validate_platforms(self.m, [stage(projection_mm=2400)])
        self.assertTrue(any(i.severity == "WARN" and "出" in i.message
                            for i in r.issues))

    def test_out_of_range_rejected(self):
        r = validate_platforms(self.m, [stage(start_mm=999999)])
        self.assertTrue(ngs(r))
        r = validate_platforms(self.m, [stage(edge_index=99)])
        self.assertTrue(ngs(r))

    def test_invalid_level_rejected(self):
        r = validate_platforms(self.m, [stage(levels=[99])])
        self.assertTrue(any("作業層" in i.message for i in ngs(r)))


class TestStageLoad(unittest.TestCase):
    def setUp(self):
        self.m = build()

    def test_load_distributed_to_supporting_posts(self):
        s = stage(span_count=2, load_kn=9.8, levels=[3])
        # 支持する建地は間口のスパン数+1本、張出しの偏心を割増係数で見込む
        expect = 9.8 * 1 * CANTILEVER_AMPLIFICATION / 3
        self.assertAlmostEqual(stage_post_load_kn(s, self.m), expect, places=3)

    def test_wider_stage_lowers_per_post_load(self):
        narrow = stage_post_load_kn(stage(span_count=2), self.m)
        wide = stage_post_load_kn(stage(span_count=4), self.m)
        self.assertLess(wide, narrow)

    def test_more_levels_raises_load(self):
        one = stage_post_load_kn(stage(levels=[3]), self.m)
        two = stage_post_load_kn(stage(levels=[3, 4]), self.m)
        self.assertAlmostEqual(two, one * 2, places=3)

    def test_governing_stage_reported(self):
        r = validate_platforms(self.m, [stage(load_kn=4.9), stage(start_mm=3600, load_kn=19.6)])
        self.assertIn("19.6", r.governing)
        self.assertAlmostEqual(
            r.max_post_load_kn, stage_post_load_kn(stage(load_kn=19.6), self.m), places=3
        )


class TestStructuralIntegration(unittest.TestCase):
    def test_stage_raises_post_ratio(self):
        """ステージ直下の建地は平均より厳しくなる（平均で見ると抜ける）."""
        m = build()
        q = take_off(m)
        base = run_structural(m, q)
        p = validate_platforms(m, [stage()])
        with_stage = run_structural(m, q, platforms=p)
        self.assertGreater(with_stage.post.ratio, base.post.ratio)
        self.assertAlmostEqual(
            with_stage.post.extra_load_kn, p.max_post_load_kn, places=3
        )
        self.assertIn("荷受けステージ", with_stage.post.governing)

    def test_total_includes_extra(self):
        m = build()
        p = validate_platforms(m, [stage()])
        r = run_structural(m, take_off(m), platforms=p)
        self.assertAlmostEqual(
            r.post.total_kn,
            r.post.dead_load_kn + r.post.live_load_kn + r.post.extra_load_kn,
            places=3,
        )

    def test_overloaded_stage_gets_specific_remedy(self):
        m = build()
        p = validate_platforms(m, [stage(load_kn=400.0, span_count=1)])
        r = run_structural(m, take_off(m), platforms=p)
        self.assertFalse(r.post.ok)
        msgs = [w for w in r.warnings if "建地圧縮" in w]
        self.assertTrue(msgs)
        self.assertIn("荷受けステージ直下", msgs[0])

    def test_no_platforms_no_extra_load(self):
        m = build()
        r = run_structural(m, take_off(m))
        self.assertEqual(r.post.extra_load_kn, 0.0)


class TestHoist(unittest.TestCase):
    def setUp(self):
        self.m = build()

    def test_adds_mast_wall_ties(self):
        r = validate_platforms(self.m, hoists=[Hoist(edge_index=2, position_mm=14400)])
        self.assertEqual(r.hoists and r.extra_wall_ties, 4)  # 16300 // 3600

    def test_tighter_tie_interval_adds_more(self):
        loose = validate_platforms(
            self.m, hoists=[Hoist(edge_index=2, position_mm=0, tie_every_mm=3600)]
        ).extra_wall_ties
        tight = validate_platforms(
            self.m, hoists=[Hoist(edge_index=2, position_mm=0, tie_every_mm=1800)]
        ).extra_wall_ties
        self.assertGreater(tight, loose)

    def test_scope_limit_is_stated(self):
        """昇降機本体の構造は対象外であることを黙らない."""
        r = validate_platforms(self.m, hoists=[Hoist(edge_index=2, position_mm=0)])
        self.assertTrue(any("対象外" in i.message for i in r.issues))

    def test_reach_over_scaffold_warns(self):
        r = validate_platforms(
            self.m, hoists=[Hoist(edge_index=2, position_mm=0, reach_height_mm=25000)]
        )
        self.assertTrue(any("到達高さ" in i.message for i in r.issues))

    def test_bad_position_rejected(self):
        r = validate_platforms(self.m, hoists=[Hoist(edge_index=99, position_mm=0)])
        self.assertTrue(ngs(r))


class TestPlatformQuantities(unittest.TestCase):
    def test_parts_scale_with_span_and_levels(self):
        m = build()
        r = validate_platforms(m, [stage(span_count=2, levels=[3])])
        q = platform_quantities(m, r)
        self.assertEqual(q["張出ブラケット"], 3)   # スパン数+1
        self.assertEqual(q["方杖"], 3)
        self.assertEqual(q["踏板"], 2)
        self.assertEqual(q["幅木"], 2)
        self.assertEqual(q["布材"], 4)             # 手すり＋中桟
        self.assertEqual(q["壁つなぎ"], r.extra_wall_ties)

    def test_no_hozue_no_count(self):
        m = build()
        r = validate_platforms(m, [stage(has_hozue=False)])
        self.assertNotIn("方杖", platform_quantities(m, r))


if __name__ == "__main__":
    unittest.main()
