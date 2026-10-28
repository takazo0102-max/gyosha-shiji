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
        # 最適化された基準面では、可動域外（ジャッキ最大でも届かない／最小でも高い）支柱が出ない
        # （実務上限超えの脚を敷板で持ち上げる調整は可動域内の話なので除く）
        self.assertEqual([f for f in r.feet
                          if any("ジャッキ最大" in w or "床掘り" in w for w in f.warnings)], [])
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
        self.assertEqual(len(rows), len(r.all_feet) + 1)   # ヘッダ込み（内外の列）
        self.assertEqual(len(r.feet_outer), len(r.feet))   # 本足場は外側の列も地盤から解く
        self.assertIn("ジャッキ繰出し(mm)", rows[0])
        self.assertIn("敷板調整(mm)", rows[0])

    def test_row_matches_foot(self):
        m = build()
        r = solve_post_feet(m, slope())
        rows = jack_table_rows(r)
        f = r.feet[3]
        row = rows[4]
        self.assertEqual(row[0], f.index + 1)
        self.assertEqual(row[1], "内")
        self.assertAlmostEqual(row[6], round(f.jack_mm, 1))


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


class TestDeckLevelsAreShared(unittest.TestCase):
    """作業床レベルは全周で通す。高低差は脚部だけで吸収する.

    この不変条件は plan.json と設置届に出るのに、絶対標高を空にしても
    テストが落ちなかった（変異テストで判明）。
    """

    def _solve(self, slope=0.04):
        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        ground = GroundModel(points=[
            (x, y, -x * slope) for x in (0, 15000, 30000) for y in (0, 20000)
        ])
        return m, solve_post_feet(m, ground)

    def test_levels_are_reported(self):
        m, t = self._solve()
        self.assertEqual(
            len(t.deck_levels_abs_mm), len(m.elevation.level_heights))

    def test_each_foot_reaches_the_same_levels(self):
        """支柱ごとにジャッキ量も支柱長も違うが、床の標高は揃う."""
        m, t = self._solve()
        first = t.deck_levels_abs_mm[0]
        for f in t.feet:
            with self.subTest(f.index):
                # 脚部下端(GL+敷板調整)＋ジャッキ＝支柱下端。そこから
                # 下げたコマぶん長い支柱を積むので、床は全周で同じ標高になる
                post_bottom = f.gl_mm + f.base_plate_adjust_mm + f.jack_mm
                koma = f.koma_offset * m.master.koma_pitch
                level0 = m.elevation.level_heights[0] - m.elevation.jack_extension
                self.assertAlmostEqual(
                    post_bottom + koma + level0, first, delta=1.0)

    def test_levels_follow_the_elevation(self):
        m, t = self._solve()
        pitches = [b - a for a, b in zip(t.deck_levels_abs_mm,
                                         t.deck_levels_abs_mm[1:])]
        want = [b - a for a, b in zip(m.elevation.level_heights,
                                      m.elevation.level_heights[1:])]
        self.assertEqual([round(p) for p in pitches], want)



class TestFrameTerrainUsesKenwaku(unittest.TestCase):
    """枠組の敷地警告は「支柱」でなく「建枠」で書く."""

    def test_over_jack_warning_says_kenwaku(self):
        m = build(series="waku")
        r = solve_post_feet(m, slope(0.06))
        self.assertTrue(r.over_jack_warning)
        self.assertIn("建枠", r.over_jack_warning)
        self.assertNotIn("超える支柱", r.over_jack_warning)

    def test_wedge_still_says_shichu(self):
        m = build(series="shinwa_A")
        r = solve_post_feet(m, slope(0.06))
        self.assertTrue(r.over_jack_warning)
        self.assertIn("支柱", r.over_jack_warning)


class TestOverRecommendedJackGetsShims(unittest.TestCase):
    """実務上限（270）超〜可動域内の脚は、敷板（厚35）で持ち上げて上限内に収める."""

    def test_shims_bring_the_jack_within_the_limit(self):
        from ashiba.terrain import SHIM_UNIT_MM, JACK_HARD_MAX_EXTENSION

        m = build()
        r = solve_post_feet(m, slope(0.04))
        over = [f for f in r.feet if f.jack_mm > JACK_RECOMMENDED]
        self.assertEqual(over, [])                       # 上限を超える脚は残らない
        shimmed = [f for f in r.feet if f.base_plate_adjust_mm > 1e-6]
        self.assertTrue(shimmed, "この斜面では敷板調整が出る前提")
        for f in shimmed:
            self.assertAlmostEqual(f.base_plate_adjust_mm % SHIM_UNIT_MM, 0.0)
            self.assertGreaterEqual(f.jack_mm, 30)
            self.assertLessEqual(f.jack_mm, JACK_RECOMMENDED)
            self.assertTrue(any("敷板" in w and "実務上限" in w for w in f.warnings), f.warnings)
        self.assertTrue(any("敷板（厚35mm）で持ち上げて上限内" in w for w in r.warnings), r.warnings)

    def test_beyond_hard_max_is_shimmed_with_whole_boards_too(self):
        # 枠組の見本: 可動域（350）も超える脚が繰出し350・端数の敷板（80mm）のまま残り、
        # 注記の「上限内にしています」と一覧が食い違っていた。同じ脚が「吸収しきれない」にも数えられていた
        from ashiba.terrain import SHIM_UNIT_MM

        m = build("waku", 16300)
        r = solve_post_feet(m, slope(0.20))
        beyond = [f for f in r.feet if any("も超える" in w for w in f.warnings)]
        self.assertTrue(beyond, "この斜面では最大繰出しを超える脚が出る前提")
        for f in r.feet:
            if f.base_plate_adjust_mm > 0:
                self.assertAlmostEqual(f.base_plate_adjust_mm % SHIM_UNIT_MM, 0.0)
                self.assertLessEqual(f.jack_mm, JACK_RECOMMENDED)
        n_dig = sum(1 for f in r.all_feet if f.base_plate_adjust_mm < 0)          # 内外の列
        rest = [w for w in r.warnings if "吸収しきれない" in w]
        if n_dig:
            self.assertIn(f"{n_dig}本", rest[0])
        else:
            self.assertEqual(rest, [])
        self.assertTrue(any("枚以上重ねる脚" in w for w in r.warnings), r.warnings)


if __name__ == "__main__":
    unittest.main()


class TestTallTerraceExtendsThePosts(unittest.TestCase):
    """3.6m（8コマ）を超える段差でも、継ぎ足した支柱構成を脚ごとに持つ.

    構成表を8コマで打ち切っていたため、それを超える脚は名目構成に戻され、
    数量の支柱が足りず、高さ判定も名目のままだった。
    """

    def test_every_foot_sums_to_its_offset(self):
        from ashiba.elevation_solver import solve_elevation
        from ashiba.master import load_master
        from ashiba.model import ScaffoldConfig, ScaffoldModel
        from ashiba.plan_solver import solve_plan
        from ashiba.terrain import GroundModel, solve_post_feet

        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master,
            plan=solve_plan([(0, 0), (30000, 0), (30000, 20000), (0, 20000)], master),
            elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
        )
        ground = GroundModel(points=[(0, 0, 6000), (30000, 0, 0),
                                     (30000, 20000, 0), (0, 20000, 6000)])
        t = solve_post_feet(m, ground)
        base_total = sum(m.elevation.posts)
        koma = master.koma_pitch
        self.assertGreater(max(f.koma_offset for f in t.feet), 8)
        for f in t.feet:
            self.assertEqual(sum(f.posts), base_total + f.koma_offset * koma,
                             f"脚{f.index}: offset={f.koma_offset} posts={f.posts}")
            self.assertFalse([w for w in f.warnings if "組めません" in w])
        self.assertFalse([w for w in t.warnings if "組めない脚" in w])



class TestOuterRow(unittest.TestCase):
    """外側の建地列は外側の地盤で解く（利用者の指定 2026-10-21「足元はメッシュで高低差があるときの対応」）."""

    def _cross_slope(self, gradient=0.25):
        # 南面（y=0 の辺）から外へ下がる斜面: 外側の列は内側の列より row×勾配だけ低い
        return GroundModel(points=[(x, y, y * gradient) for x in (-3000, 10000, 20000, 33000)
                                   for y in (-3000, -1000, 0, 10000, 23000)])

    def test_outer_feet_follow_their_own_ground(self):
        m = build()
        r = solve_post_feet(m, self._cross_slope())
        self.assertEqual(len(r.feet_outer), len(r.feet))
        south = [(fi, fo) for fi, fo in zip(r.feet, r.feet_outer) if abs(fi.y - r.feet[0].y) < 1.0]
        self.assertTrue(south)
        fi, fo = south[len(south) // 2]
        self.assertLess(fo.gl_mm, fi.gl_mm - 50)                 # 外側の地盤は低い
        self.assertEqual((fi.row, fo.row), (0, 1))
        # 脚の下端（地盤＋敷板＋ジャッキ）は作業床が通るよう段数ぶんだけ違う
        bottom_i = fi.gl_mm + fi.base_plate_adjust_mm + fi.jack_mm + fi.koma_offset * m.master.koma_pitch
        bottom_o = fo.gl_mm + fo.base_plate_adjust_mm + fo.jack_mm + fo.koma_offset * m.master.koma_pitch
        self.assertAlmostEqual(bottom_i, bottom_o, delta=1.0)

    def test_gdl_gets_outer_lists(self):
        from ashiba.gdl_params import line_params

        m = build()
        r = solve_post_feet(m, self._cross_slope())
        p = line_params(m, m.plan.edges[0], terrain=r)
        self.assertTrue(p["glListO"])
        self.assertNotEqual(p["glListO"], p["glList"])
        self.assertEqual(len(p["glListO"].split(",")), len(p["glList"].split(",")))

    def test_one_side_scaffold_reads_the_outer_row(self):
        m = build()
        m.config.scaffold_form = "一側足場"
        r = solve_post_feet(m, self._cross_slope())
        self.assertEqual(r.feet_outer, [])
        self.assertTrue(all(f.row == 1 for f in r.feet))


class TestMillenniumSlope(unittest.TestCase):
    """日建ミレニュームの斜面（カタログ Q12。利用者の資料 2026-10-25）: 最下段の支柱 P27 を地盤の高い所でそろえ、
    低い所は調整支柱（P2.25・P4.5・P9…）を最下段の下に入れ、ジャッキ 50〜300 で補う（225 刻み）."""

    def test_adjust_posts_go_under_the_base_post(self):
        from ashiba.cli import solve_all
        from ashiba.master import load_master
        from ashiba.terrain import adjust_post_mm

        self.assertEqual(adjust_post_mm(load_master("nikken_millennium")), 225)
        self.assertEqual(adjust_post_mm(load_master("nikken_nd1800")), 0)
        s = {"project_name": "s", "series_id": "nikken_millennium",
             "outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
             "scaffold_width_mm": 610,
             "ground_points_mm": [[-3000, -3000, 0], [15000, -3000, -1500], [15000, 11000, -1500], [-3000, 11000, 0]]}
        feet = solve_all(s).terrain.feet
        self.assertEqual({f.koma_offset for f in feet} >= {1, 2, 3}, True)
        for f in feet:
            adj = f.posts[:len(f.posts) - 3] if f.koma_offset else []
            self.assertEqual(sum(adj), 225 * f.koma_offset)          # 調整支柱は最下段の下に、刻みの合計どおり
            self.assertEqual(f.posts[len(adj)], 2700)                # その上は基準の脚と同じ（P27 から）
            self.assertTrue(50 <= f.jack_mm <= 300, f.jack_mm)       # ジャッキはカタログの 50〜300
