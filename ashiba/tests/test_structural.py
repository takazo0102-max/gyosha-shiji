import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel, generate_wall_ties
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.structural import (
    CO_BASE,
    CapacityError,
    SiteCondition,
    height_factor,
    load_capacities,
    optimize_wall_ties,
    run_structural,
    tie_tributaries,
    wind_force_coefficient,
)

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def make_model():
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(16300, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(period_days=90), building_height_mm=16000,
    )


class TestWindFormula(unittest.TestCase):
    def test_force_coefficient_matches_spec(self):
        # C = (0.11 + 0.09γ + 0.945×Co×R) × F、メッシュ R=0.7・Co=1.57
        c = wind_force_coefficient(fill_ratio=0.7, gamma=0.0, f=1.0)
        self.assertAlmostEqual(c, 0.11 + 0.945 * CO_BASE * 0.7, places=6)
        # 養生なしなら 0.11 のみ
        self.assertAlmostEqual(wind_force_coefficient(0.0), 0.11, places=6)
        # γとFが効く
        self.assertGreater(wind_force_coefficient(0.7, gamma=1.0), c)
        self.assertAlmostEqual(wind_force_coefficient(0.7, f=2.0), c * 2, places=6)

    def test_height_factor_increases_with_height(self):
        self.assertLess(height_factor(5, "III"), height_factor(30, "III"))
        # 粗度区分が粗いほど地表付近の係数は小さい
        self.assertGreater(height_factor(20, "I"), height_factor(20, "IV"))

    def test_unknown_roughness_and_region_rejected(self):
        with self.assertRaises(CapacityError):
            height_factor(10, "V")
        with self.assertRaises(CapacityError):
            SiteCondition(region="火星").base_wind_speed()
        with self.assertRaises(CapacityError):
            SiteCondition(sheet_type="ビニール").fill_ratio()

    def test_design_wind_speed_chain(self):
        m = make_model()
        site = SiteCondition(region="関東(内陸)", adjacent_factor=1.2, region_factor=1.1)
        r = run_structural(m, take_off(m), site)
        expect = r.wind.v0_ms * r.wind.k_height * 1.2 * 1.1
        self.assertAlmostEqual(r.wind.v_design_ms, expect, places=2)
        self.assertAlmostEqual(r.wind.q_n_m2, 0.6 * expect**2, places=0)


class TestCapacityGate(unittest.TestCase):
    def test_unverified_values_are_flagged(self):
        m = make_model()
        r = run_structural(m, take_off(m))
        # 同梱の暫定耐力値は verified=no。黙って使わず必ず警告する
        self.assertTrue(r.unverified_used)
        self.assertTrue(any("未確認" in w for w in r.warnings))
        self.assertFalse(r.wall_tie.verified)

    def test_jack_capacity_interpolated_and_decreasing(self):
        caps = load_capacities("shinwa_A")
        from ashiba.structural import _interpolate_capacity
        v0, _ = _interpolate_capacity(caps, "ジャッキ許容支持力", 0)
        v150, _ = _interpolate_capacity(caps, "ジャッキ許容支持力", 150)
        v270, _ = _interpolate_capacity(caps, "ジャッキ許容支持力", 270)
        # 繰出しが長いほど許容支持力は下がる
        self.assertGreater(v0.value, v150.value)
        self.assertGreater(v150.value, v270.value)
        # 100(22.5)と200(19.6)の中間
        self.assertAlmostEqual(v150.value, (22.5 + 19.6) / 2, places=2)

    def test_exact_key_is_not_reported_as_interpolated(self):
        """表にある繰出し量は補間しない（補間と書くと出典が誤りになる）."""
        from ashiba.structural import _interpolate_capacity
        caps = load_capacities("shinwa_A")
        v, key = _interpolate_capacity(caps, "ジャッキ許容支持力", 200)
        self.assertEqual(key, "200")
        self.assertNotIn("補間", v.source)
        self.assertEqual(v.rows, ["shinwa_A,ジャッキ許容支持力,200"])

    def test_interpolated_value_names_both_source_rows(self):
        from ashiba.structural import _interpolate_capacity
        caps = load_capacities("shinwa_A")
        v, _ = _interpolate_capacity(caps, "ジャッキ許容支持力", 150)
        self.assertEqual(
            v.rows,
            ["shinwa_A,ジャッキ許容支持力,100", "shinwa_A,ジャッキ許容支持力,200"],
        )


class TestTallScaffoldNote(unittest.TestCase):
    """31m超は2本組が要る。どちらで検定したのかを書かないと検定比が読めない."""

    def _model(self, height):
        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(height, master=master),
            config=ScaffoldConfig(), building_height_mm=height - 300,
        )

    def test_note_says_single_post(self):
        m = self._model(35000)
        r = run_structural(m, take_off(m))
        self.assertTrue(any("1本組" in n for n in r.notes), r.notes)

    def test_no_note_below_31m(self):
        m = self._model(16300)
        r = run_structural(m, take_off(m))
        self.assertFalse([n for n in r.notes if "1本組" in n])


class TestUnverifiedRowsAreNamed(unittest.TestCase):
    """「未確認値です」だけでは直せない。どの行を差し替えるかまで出す."""

    def setUp(self):
        m = make_model()
        self.r = run_structural(m, take_off(m))
        self.warn = next(w for w in self.r.warnings if "未確認" in w)

    def test_warning_names_the_csv_rows(self):
        for item in ("壁つなぎ許容耐力", "ジャッキ許容支持力"):
            self.assertIn(item, self.warn)
        self.assertIn("capacity.csv", self.warn)
        self.assertIn("verified=yes", self.warn)

    def test_rows_point_at_real_lines_in_the_csv(self):
        import csv as _csv
        from ashiba.structural import DATA_DIR
        with open(DATA_DIR / "capacity.csv", encoding="utf-8") as f:
            actual = {
                (r["series_id"], r["item"], r["key"])
                for r in _csv.DictReader(f)
                if r["verified"].strip().lower() not in ("yes", "true", "1")
            }
        reported = {
            tuple(row.split(",")) for c in self.r.unverified_rows for row in c.rows
        }
        self.assertTrue(reported)
        self.assertTrue(reported <= actual, reported - actual)

    def test_verified_master_data_produces_no_warning(self):
        import csv as _csv
        import tempfile
        from ashiba.structural import DATA_DIR
        with open(DATA_DIR / "capacity.csv", encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
            names = list(rows[0])
        for r in rows:
            r["verified"] = "yes"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "capacity.csv"
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, names)
                w.writeheader()
                w.writerows(rows)
            m = make_model()
            r = run_structural(m, take_off(m), capacity_path=path)
        self.assertEqual(r.unverified_rows, [])
        self.assertFalse([w for w in r.warnings if "未確認" in w])


class TestChecks(unittest.TestCase):
    def test_wall_tie_formula(self):
        m = make_model()
        r = run_structural(m, take_off(m))
        t, w = r.wall_tie, r.wind
        # P = C·q·lh·lw （kN換算）
        expect = w.c_force * w.q_n_m2 * t.lh_m * t.lw_m / 1000.0
        self.assertAlmostEqual(t.force_kn, expect, places=2)
        # 許容は風荷重時30%割増
        self.assertAlmostEqual(t.allowable_increased_kn, t.allowable_kn * 1.3, places=3)

    def test_post_check_uses_governing_capacity(self):
        m = make_model()
        r = run_structural(m, take_off(m))
        p = r.post
        self.assertAlmostEqual(p.total_kn, p.dead_load_kn + p.live_load_kn, places=3)
        self.assertEqual(p.jack_extension_mm, m.elevation.jack_extension)
        self.assertAlmostEqual(p.ratio, p.total_kn / p.allowable_kn, places=3)

    def test_severe_site_fails_and_warns(self):
        m = make_model()
        # 沖縄・密閉シート・粗度区分I（海岸の開けた地形）・近接建物補正最大
        severe = SiteCondition(region="沖縄", sheet_type="密閉シート",
                               roughness="I", adjacent_factor=1.3)
        r = run_structural(m, take_off(m), severe)
        self.assertFalse(r.wall_tie.ok)
        self.assertTrue(any("壁つなぎ" in w for w in r.warnings))


class TestTieTributary(unittest.TestCase):
    """壁つなぎごとの支配面積（Phase 4）.

    境界の扱い: 下端は脚部が支点なので半分、上端は自由端なので全長、
    面の端はコーナー支柱（支点）なので半分。
    """

    def setUp(self):
        self.m = make_model()
        self.tribs = tie_tributaries(self.m)

    def test_one_entry_per_tie(self):
        self.assertEqual(len(self.tribs), len(self.m.wall_ties))

    def test_no_tie_no_tributary(self):
        m = make_model()
        m.wall_ties = []
        self.assertEqual(tie_tributaries(m), [])

    def test_top_tie_covers_full_overhang(self):
        """最上段は上の張り出しを全部負担する（自由端）."""
        top_h = max(t.height_mm for t in self.m.wall_ties)
        heights = sorted({t.height_mm for t in self.m.wall_ties})
        below_half = (top_h - heights[-2]) / 2
        overhang = self.m.scaffold_height_mm - top_h
        for t in self.tribs:
            if t.height_mm == top_h:
                self.assertAlmostEqual(
                    t.lw_m * 1000, below_half + overhang, delta=1
                )

    def test_bottom_tie_takes_half_to_ground(self):
        """最下段は脚部が支点なので、地盤までの半分だけ負担する."""
        heights = sorted({t.height_mm for t in self.m.wall_ties})
        bottom = heights[0]
        expect = bottom / 2 + (heights[1] - bottom) / 2
        for t in self.tribs:
            if t.height_mm == bottom:
                self.assertAlmostEqual(t.lw_m * 1000, expect, delta=1)

    def test_total_area_below_full_face(self):
        """支配面積の合計は足場外面より小さい（脚部とコーナーが分担するため）."""
        total = sum(t.area_m2 for t in self.tribs)
        loop_m = sum(e.scaffold_length for e in self.m.plan.edges) / 1000
        face = loop_m * self.m.scaffold_height_mm / 1000
        self.assertLess(total, face)
        self.assertGreater(total, face * 0.5)   # 極端に小さくもない

    def test_check_uses_worst_tie_and_names_it(self):
        r = run_structural(self.m, take_off(self.m))
        worst = max(self.tribs, key=lambda t: t.area_m2)
        self.assertAlmostEqual(r.wall_tie.tributary_area_m2, worst.area_m2, places=2)
        self.assertIsNotNone(r.wall_tie.governing)
        self.assertIn(f"辺{worst.edge_index}", r.wall_tie.governing)

    def test_tighter_layout_reduces_tributary(self):
        m = make_model()
        loose = max(t.area_m2 for t in tie_tributaries(m))
        m.config.wall_tie_span_step = 1
        m.config.wall_tie_level_step = 1
        m.wall_ties = generate_wall_ties(m.plan, m.elevation, m.config)
        tight = max(t.area_m2 for t in tie_tributaries(m))
        self.assertLess(tight, loose)


class TestWallTieOptimization(unittest.TestCase):
    def test_tightens_until_structurally_ok(self):
        m = make_model()
        before = len(m.wall_ties)
        site = SiteCondition(region="関東(沿岸)", sheet_type="メッシュシート")
        opt = optimize_wall_ties(m, site)
        self.assertTrue(opt.feasible)
        self.assertLessEqual(opt.wall_tie.ratio, 1.0)
        # 法規上限は「間隔」の制限（支配面積 lh/lw とは別物）
        v_max, h_max = m.wall_tie_max_spacing()
        self.assertLessEqual(v_max, 5000)
        self.assertLessEqual(h_max, 5500)
        # 詰めた場合は本数が増え、モデルに反映される
        self.assertEqual(len(m.wall_ties), opt.tie_count)
        if opt.tightened:
            self.assertGreater(opt.tie_count, before)
            self.assertIn("詰めました", opt.message)

    def test_apply_false_leaves_model_untouched(self):
        m = make_model()
        before = list(m.wall_ties)
        before_cfg = (m.config.wall_tie_span_step, m.config.wall_tie_level_step)
        optimize_wall_ties(m, SiteCondition(region="関東(沿岸)"), apply=False)
        self.assertEqual(len(m.wall_ties), len(before))
        self.assertEqual(
            (m.config.wall_tie_span_step, m.config.wall_tie_level_step), before_cfg
        )

    def test_infeasible_case_reports_remedy(self):
        m = make_model()
        # 沖縄・密閉シート・粗度区分I（海岸の開けた地形）・近接建物補正最大
        severe = SiteCondition(region="沖縄", sheet_type="密閉シート",
                               roughness="I", adjacent_factor=1.3)
        opt = optimize_wall_ties(m, severe)
        self.assertFalse(opt.feasible)
        self.assertIn("最密", opt.message)
        self.assertTrue("高耐力" in opt.message or "養生材" in opt.message)


class TestJackExtensionGovernsPostCapacity(unittest.TestCase):
    """ジャッキ許容支持力は繰出し長で落ちる（100mm:22.5kN → 450mm:11.8kN）.

    傾斜地で平坦時の繰出し量のまま検定すると2倍近く危険側になる。
    """

    def setUp(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        self.m = make_model()
        # 30m×20mの敷地に約1.2mの高低差
        self.ground = GroundModel(points=[
            (0, 0, 0), (30000, 0, 400), (30000, 20000, 1200), (0, 20000, 800),
        ])
        self.terrain = solve_post_feet(self.m, self.ground)

    def test_terrain_produces_larger_jack_extensions(self):
        self.assertGreater(
            self.terrain.jack_max_mm, self.m.elevation.jack_extension
        )

    def test_check_uses_the_worst_post(self):
        q = take_off(self.m)
        flat = run_structural(self.m, q, SiteCondition())
        slope = run_structural(self.m, q, SiteCondition(), terrain=self.terrain)
        self.assertEqual(flat.post.jack_extension_mm, self.m.elevation.jack_extension)
        self.assertEqual(
            slope.post.jack_extension_mm, int(round(self.terrain.jack_max_mm))
        )
        self.assertLess(slope.post.allowable_kn, flat.post.allowable_kn)
        self.assertGreater(slope.post.ratio, flat.post.ratio)

    def test_the_governing_post_is_named(self):
        """どの支柱で検定したかは「説明」なので notes 側に出す."""
        res = run_structural(
            self.m, take_off(self.m), SiteCondition(), terrain=self.terrain
        )
        self.assertTrue(any("最大繰出し" in n for n in res.notes), res.notes)

    def test_flat_site_is_unchanged(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        flat_terrain = solve_post_feet(self.m, GroundModel())
        q = take_off(self.m)
        a = run_structural(self.m, q, SiteCondition())
        b = run_structural(self.m, q, SiteCondition(), terrain=flat_terrain)
        self.assertEqual(a.post.jack_extension_mm, b.post.jack_extension_mm)
        self.assertEqual(a.post.ratio, b.post.ratio)


class TestUntiedFaces(unittest.TestCase):
    """壁つなぎが入らない面を黙って通さないこと."""

    @staticmethod
    def _model(outline):
        master = load_master("shinwa_A")
        plan = solve_plan(outline, master)
        return ScaffoldModel(
            master=master, plan=plan,
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(period_days=90),
        )

    def test_short_face_still_gets_a_tie(self):
        """コーナーから1スパン空ける取り合いより、面を拘束する方が優先."""
        m = self._model([
            (0, 0), (20000, 0), (20000, 10000), (14000, 10000),
            (14000, 7000), (6000, 7000), (6000, 10000), (0, 10000),
        ])
        self.assertEqual(m.edges_without_wall_ties(), [])

    def test_single_span_face_is_reported(self):
        """支柱が無く物理的に入らない面は、警告として必ず出す."""
        from ashiba.law_check import check_wall_ties

        m = self._model([(0, 0), (30000, 0), (30000, 900), (0, 900)])
        self.assertTrue(m.edges_without_wall_ties())
        check = check_wall_ties(m)
        self.assertEqual(check.status, "WARN")
        self.assertIn("壁つなぎが入らない面", check.message)

    def test_structural_states_the_face_is_not_carried(self):
        m = self._model([(0, 0), (30000, 0), (30000, 900), (0, 900)])
        res = run_structural(m, take_off(m), SiteCondition())
        self.assertTrue(
            any("壁つなぎが1本も入らない面" in w for w in res.warnings),
            res.warnings,
        )

    def test_tributaries_skip_untied_faces(self):
        """支配面積に出てこない面がある＝その面の風荷重は検定外、という前提の確認."""
        m = self._model([(0, 0), (30000, 0), (30000, 900), (0, 900)])
        covered = {t.edge_index for t in tie_tributaries(m)}
        self.assertTrue(set(m.edges_without_wall_ties()).isdisjoint(covered))


if __name__ == "__main__":
    unittest.main()
