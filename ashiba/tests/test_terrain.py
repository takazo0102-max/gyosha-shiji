"""敷地高低差対応と支柱ごとのジャッキ量算出のテスト（仕様4.4・Phase 4）.

中核の不変条件: **作業床レベルは全周で通る**。
各支柱の下端は基準からコマピッチの整数倍だけ下がり、残差をジャッキが吸収する。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.terrain import (
    JACK_HARD_MAX_EXTENSION,
    GroundModel,
    jack_table_rows,
    solve_post_feet,
)

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
JACK_RECOMMENDED = 270


def build(series="shinwa_A", height=16300):
    master = load_master(series)
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)), building_height_mm=16000,
    )


def slope(gradient=0.04):
    return GroundModel(points=[
        (x, y, -x * gradient)
        for x in (0, 10000, 20000, 31000) for y in (0, 10000, 21000)
    ])


class TestGroundModel(unittest.TestCase):
    def test_flat_when_no_samples(self):
        g = GroundModel()
        self.assertTrue(g.is_flat)
        self.assertEqual(g.elevation_at(1234, 5678), 0.0)

    def test_returns_exact_sample_value(self):
        g = GroundModel(points=[(0, 0, 100), (1000, 0, 200)])
        self.assertAlmostEqual(g.elevation_at(0, 0), 100)
        self.assertAlmostEqual(g.elevation_at(1000, 0), 200)

    def test_interpolates_between_samples(self):
        g = GroundModel(points=[(0, 0, 0), (1000, 0, 1000)])
        mid = g.elevation_at(500, 0)
        self.assertGreater(mid, 0)
        self.assertLess(mid, 1000)

    def test_range(self):
        self.assertEqual(GroundModel(points=[(0, 0, -50), (1, 1, 250)]).range_mm(),
                         (-50, 250))


class TestFlatGround(unittest.TestCase):
    def test_all_posts_identical(self):
        m = build()
        r = solve_post_feet(m)
        self.assertEqual(len({f.jack_mm for f in r.feet}), 1)
        self.assertEqual({f.koma_offset for f in r.feet}, {0})
        self.assertEqual(r.gl_difference_mm, 0)
        self.assertTrue(r.all_ok)

    def test_no_warnings_on_flat(self):
        self.assertEqual(solve_post_feet(build()).warnings, [])


class TestSlopedGround(unittest.TestCase):
    def setUp(self):
        self.m = build()
        self.r = solve_post_feet(self.m, slope())

    def test_deck_levels_stay_level_across_all_posts(self):
        """核心の不変条件: 支柱下端＋下げコマ分が全支柱で一致する.

        これが成り立つとき、布材・作業床レベルが全周で通る（仕様4.4）。
        """
        koma = self.m.master.koma_pitch
        datums = {
            round(f.jack_top_mm + f.koma_offset * koma, 3) for f in self.r.feet
        }
        self.assertEqual(len(datums), 1, f"基準面が揃っていない: {sorted(datums)[:5]}")

    def test_post_stack_grows_by_koma_offset(self):
        koma = self.m.master.koma_pitch
        base_total = sum(self.m.elevation.posts)
        for f in self.r.feet:
            self.assertAlmostEqual(
                sum(f.posts), base_total + f.koma_offset * koma, delta=0.5
            )

    def test_jacks_within_mechanical_range(self):
        for f in self.r.feet:
            self.assertGreaterEqual(f.jack_mm, 30)
            self.assertLessEqual(f.jack_mm, JACK_HARD_MAX_EXTENSION)

    def test_gl_difference_reported(self):
        self.assertGreater(self.r.gl_difference_mm, 1000)
        self.assertTrue(any("高低差" in w for w in self.r.warnings))

    def test_over_recommended_posts_are_flagged(self):
        over = self.r.over_recommended()
        for f in over:
            self.assertGreater(f.jack_mm, JACK_RECOMMENDED)
            self.assertTrue(f.warnings)
        if over:
            self.assertTrue(any("実務上限" in w for w in self.r.warnings))

    def test_remedy_is_actionable(self):
        """対処が「要検討」で終わらず、具体的な手段まで書かれている."""
        msgs = [w for w in self.r.warnings if "実務上限" in w]
        self.assertTrue(msgs)
        self.assertTrue(any("敷板" in m or "床均し" in m for m in msgs))


class TestDatumOptimization(unittest.TestCase):
    def test_datum_shift_minimises_violations(self):
        """基準面の全体シフトで上限超過本数を最小化する.

        既定のジャッキ量をそのまま基準にした場合より悪くならない。
        """
        m = build()
        g = slope(0.01)   # 高低差約0.3m
        r = solve_post_feet(m, g)
        koma = m.master.koma_pitch
        # 最適化された基準面では、可動域外（敷板調整が要る）支柱が出ない
        self.assertEqual([f for f in r.feet if abs(f.base_plate_adjust_mm) > 1e-6], [])
        # 基準面はコマピッチの範囲内で選ばれている
        self.assertLessEqual(r.reference_gl_mm - r.gl_range_mm[1], koma)

    def test_gentle_slope_suggests_leveling(self):
        """高低差がコマピッチ以内なら床均し量を具体的に示す."""
        m = build()
        r = solve_post_feet(m, slope(0.01))
        if r.over_recommended():
            self.assertTrue(any("床均し" in w for w in r.warnings))


class TestDatumInvariantHolds(unittest.TestCase):
    """支柱下端＋下げコマ分＝基準面 は、地盤調整が要る場合でも必ず成り立つ.

    ここが崩れると作業床が全周で通らなくなる。敷板・床掘りの調整量は
    「目標下端 − 実ジャッキ量」でなければならない（符号を逆にすると下端がずれる）。
    """

    def _check(self, model, ground):
        r = solve_post_feet(model, ground)
        koma = model.master.koma_pitch or min(model.master.frame_heights())
        datums = {round(f.jack_top_mm + f.koma_offset * koma, 3) for f in r.feet}
        self.assertEqual(len(datums), 1, f"基準面がずれた: {sorted(datums)[:5]}")
        return r

    def test_various_terrains(self):
        m = build()
        for name, g in (
            ("平坦", GroundModel()),
            ("緩斜面", slope(0.005)),
            ("斜面", slope(0.04)),
            ("急斜面", slope(0.12)),
            ("段差", GroundModel(points=[
                (x, y, 0 if x < 15000 else -1500)
                for x in (0, 14000, 16000, 31000) for y in (0, 21000)])),
            ("起伏", GroundModel(points=[
                (x, y, 300 * ((x // 7000) % 2) - 200 * ((y // 7000) % 2))
                for x in range(0, 32000, 7000) for y in range(0, 22000, 7000)])),
        ):
            with self.subTest(terrain=name):
                self._check(m, g)

    def test_holds_for_frame_series(self):
        self._check(build("waku", 16300), slope(0.04))

    def test_holds_for_b_series(self):
        self._check(build("shinwa_B", 16150), slope(0.04))

    def test_adjust_sign_means_direction(self):
        """調整量の符号: 正＝敷板で持ち上げ、負＝床掘りで下げ."""
        m = build()
        r = solve_post_feet(m, slope(0.20))   # 可動域外が出る急斜面
        for f in r.feet:
            if f.base_plate_adjust_mm > 0:
                self.assertTrue(any("敷板" in w for w in f.warnings))
            elif f.base_plate_adjust_mm < 0:
                self.assertTrue(any("床掘り" in w for w in f.warnings))


class TestJackTable(unittest.TestCase):
    def test_rows_cover_every_post(self):
        m = build()
        r = solve_post_feet(m, slope())
        rows = jack_table_rows(r)
        self.assertEqual(len(rows), len(r.feet) + 1)   # ヘッダ込み
        self.assertIn("ジャッキ繰出し(mm)", rows[0])
        self.assertIn("敷板調整(mm)", rows[0])

    def test_row_matches_foot(self):
        m = build()
        r = solve_post_feet(m, slope())
        rows = jack_table_rows(r)
        f = r.feet[3]
        row = rows[4]
        self.assertEqual(row[0], f.index + 1)
        self.assertAlmostEqual(row[5], round(f.jack_mm, 1))


class TestFrameSeriesTerrain(unittest.TestCase):
    def test_frame_system_uses_frame_pitch(self):
        """枠組はコマの概念がないので建枠の最小高さを刻みに使う."""
        m = build("waku", 16300)
        r = solve_post_feet(m, slope())
        self.assertTrue(r.feet)
        smallest = min(m.master.frame_heights())
        datums = {
            round(f.jack_top_mm + f.koma_offset * smallest, 3) for f in r.feet
        }
        self.assertEqual(len(datums), 1)


if __name__ == "__main__":
    unittest.main()
