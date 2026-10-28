import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import ElevationResult, solve_elevation
from ashiba.law_check import NG, OK, WARN, run_all_checks
from ashiba.master import Part, load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def make_good_model():
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(16300, master=master)
    return ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elev,
        # 高さ16.3m ≧ 10m なので朝顔1段が要る
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)),
        building_height_mm=16000,
        clearance_space_mm=2000,
    )


def make_violation_model():
    """意図的な違反モデル: 全項目が検出されること（受け入れ基準）."""
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    # 立面を手作りで違反させる
    elev = ElevationResult(
        required_height=32000,
        jack_extension=300,            # #6 ジャッキ>270
        posts=[3600] * 8 + [2700, 450],  # 高さ 300+31950=32250 > 31m (#8)
        posts_alt=[3600] * 8 + [2700, 450],
        has_negarami=False,            # #5
        first_ledger_height=2100,      # #4 >2000
        n_levels=17,
        level_heights=[2100 + 1800 * i for i in range(17)],
    )
    config = ScaffoldConfig(
        scaffold_form="一側足場",      # #1 (スペース1m以上あるのに一側)
        deck_widths=(300,),            # #2 幅<400
        deck_gap_mm=40,                # #2 隙間>30
        deck_to_post_gap_mm=130,       # #2 建地との隙間>=120
        guard_rail_koma=1,             # #3 450mm<850mm
        has_midrail=False,             # #3
    )
    # #11 建地間隔: 桁行方向に規格外スパンが混入した状態
    # （マスタや系列を差し替えたときに起こりうる）
    plan.edges[0].spans = [2000] + plan.edges[0].spans[1:]
    model = ScaffoldModel(
        master=master,
        plan=plan,
        elevation=elev,
        config=config,
        building_height_mm=31500,
        clearance_space_mm=1500,
    )
    model.wall_ties = []               # #7 壁つなぎなし
    # #9 系列混在: B系列部材を混入
    b_part = load_master("shinwa_B").find("支柱", 1900)
    model.master.parts.append(b_part)
    return model


class TestLawChecks(unittest.TestCase):
    def test_good_model_passes(self):
        results = run_all_checks(make_good_model())
        self.assertEqual(len(results), 12)
        bad = [r for r in results if r.status == NG]
        self.assertEqual(bad, [], f"NG: {[(r.name, r.message) for r in bad]}")

    def test_all_violations_detected(self):
        results = run_all_checks(make_violation_model())
        self.assertEqual(len(results), 12)
        by_id = {r.check_id: r for r in results}
        # 全項目 OK 以外（NG または WARN）で検出される
        for cid in range(1, 13):
            self.assertNotEqual(
                by_id[cid].status, OK,
                f"チェック#{cid} {by_id[cid].name} が違反を検出できていない",
            )
        # 明確なNG項目
        for cid in (1, 2, 3, 4, 5, 7, 9, 10, 11):
            self.assertEqual(by_id[cid].status, NG, f"#{cid}")
        # ジャッキ超過と高さ31m超は警告
        self.assertEqual(by_id[6].status, WARN)
        self.assertIn(by_id[8].status, (WARN, NG))

    def test_basis_present(self):
        for r in run_all_checks(make_good_model()):
            self.assertTrue(r.basis)


class TestStairCheck(unittest.TestCase):
    """#12 昇降設備。階段を自動配置しているのにチェック一覧に無かった."""

    def test_unspecified_plan_is_warned_not_ok(self):
        r = [c for c in run_all_checks(make_good_model()) if c.check_id == 12][0]
        self.assertEqual(r.status, WARN)
        self.assertIn("判定できません", r.message)

    def test_valid_plan_passes(self):
        from ashiba.stairs import auto_place_stairs

        m = make_good_model()
        plan = auto_place_stairs(m)
        r = [
            c for c in run_all_checks(m, stair_plan=plan) if c.check_id == 12
        ][0]
        self.assertEqual(r.status, OK)
        self.assertIn("階段", r.message)

    def test_missing_stairs_is_ng(self):
        from ashiba.stairs import StairPlan

        m = make_good_model()
        r = [
            c for c in run_all_checks(m, stair_plan=StairPlan())
            if c.check_id == 12
        ][0]
        self.assertEqual(r.status, NG)

    def test_low_scaffold_needs_none(self):
        from ashiba.elevation_solver import solve_elevation

        m = make_good_model()
        m.elevation = solve_elevation(1400, post_lengths=[900, 450], koma_pitch=450)
        r = [c for c in run_all_checks(m) if c.check_id == 12][0]
        self.assertEqual(r.status, OK)
        self.assertIn("不要", r.message)


class TestJackCheckUsesTerrain(unittest.TestCase):
    """傾斜地では支柱ごとに繰出し量が違う。平坦時の値だけ見ない."""

    def _terrain(self, m):
        from ashiba.terrain import GroundModel, solve_post_feet

        return solve_post_feet(m, GroundModel(points=[
            (0, 0, 0), (30000, 0, 400), (30000, 20000, 1200), (0, 20000, 800),
        ]))

    def test_flat_site_is_ok(self):
        r = [c for c in run_all_checks(make_good_model()) if c.check_id == 6][0]
        self.assertEqual(r.status, OK)

    def test_slope_with_over_extended_posts_is_shimmed(self):
        """上限超えの支柱は敷板で持ち上げて上限内に収める。判定はOKだが、その旨を本文に残す."""
        m = make_good_model()
        t = self._terrain(m)
        r = [
            c for c in run_all_checks(m, terrain=t) if c.check_id == 6
        ][0]
        self.assertEqual(r.status, OK)
        self.assertIn("敷板", r.message)
        self.assertIn("支柱", r.message)
        self.assertIn("本", r.message)


class TestFirstLedgerBasisBySystem(unittest.TestCase):
    """第一の布（2m以下）は単管足場の規定。方式で根拠を出し分ける."""

    def _model(self, series):
        master = load_master(series)
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def test_wedge_cites_tanken_provision(self):
        c = [r for r in run_all_checks(self._model("shinwa_A")) if r.check_id == 4][0]
        self.assertIn("571条1項二号", c.basis)
        self.assertIn("単管足場に準じる", c.basis)

    def test_frame_does_not_cite_tanken_571(self):
        c = [r for r in run_all_checks(self._model("waku")) if r.check_id == 4][0]
        self.assertIn("建枠脚部", c.message)
        self.assertNotIn("571条", c.basis)
        self.assertIn("570条", c.basis)


class TestTallScaffoldReachesTheQuantity(unittest.TestCase):
    """31m超の2本組は、警告だけ出して数量が単管1本組のままでは部材が足りない."""

    def _model(self, height, series="shinwa_A"):
        master = load_master(series)
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(height, master=master),
            config=ScaffoldConfig(), building_height_mm=height - 300,
        )

    def test_wedge_quantity_states_what_is_missing(self):
        """くさびは単管に準じて31m超の建地2本組を警告し、不足本数を出す."""
        from ashiba.quantity import take_off

        q = take_off(self._model(35000, "shinwa_A"))
        hit = [w for w in q.warnings if "2本組" in w]
        self.assertTrue(hit, q.warnings)
        self.assertIn("数量に含んでいません", hit[0])
        self.assertIn("本ぶん", hit[0])

    def test_frame_does_not_use_single_pipe_double_post_rule(self):
        """枠組は単管足場の「建地2本組」（571条）の対象外。誤ってその文面を出さない."""
        from ashiba.quantity import take_off

        m = self._model(35000, "waku")
        q = take_off(m)
        self.assertFalse([w for w in q.warnings if "2本組" in w], q.warnings)
        self.assertFalse([n for n in q.notes if "2本組" in n], q.notes)
        # 高さチェックは枠組用の文面（最下段建枠の強度検討）を出す
        c = [r for r in run_all_checks(m) if r.check_id == 8][0]
        self.assertEqual(c.status, "WARN")
        self.assertIn("最下段", c.message)
        self.assertNotIn("2本組が必要", c.message)

    def test_check_names_the_range(self):
        c = [r for r in run_all_checks(self._model(35000)) if r.check_id == 8][0]
        self.assertEqual(c.status, "WARN")
        self.assertIn("GL〜", c.message)

    def test_short_scaffold_says_nothing(self):
        from ashiba.quantity import take_off

        q = take_off(self._model(16300))
        self.assertFalse([w for w in q.warnings if "2本組" in w])


if __name__ == "__main__":
    unittest.main()


class TestPostSpacing(unittest.TestCase):
    """#11 建地間隔: 桁行1.85m以下・梁間1.5m以下.

    スパン割は真物から決まるので通常は満たすが、系列やマスタを
    差し替えたときに黙って超えないよう検査する。
    """

    def test_normal_model_passes(self):
        r = [c for c in run_all_checks(make_good_model()) if c.check_id == 11][0]
        self.assertEqual(r.status, OK)
        self.assertIn("桁行", r.message)

    def test_oversized_span_rejected(self):
        m = make_good_model()
        m.plan.edges[0].spans = [1900] + m.plan.edges[0].spans[1:]
        r = [c for c in run_all_checks(m) if c.check_id == 11][0]
        self.assertEqual(r.status, NG)
        self.assertIn("桁行", r.message)

    def test_oversized_cross_spacing_rejected(self):
        """梁間は建地列の芯々。作業床の被覆幅ではない."""
        m = make_good_model()
        m.config.post_row_spacing_mm = 1620
        r = [c for c in run_all_checks(m) if c.check_id == 11][0]
        self.assertEqual(r.status, NG)
        self.assertIn("梁間", r.message)

    def test_cross_spacing_comes_from_the_ledger_not_the_deck(self):
        """作業床を広げただけでは建地間隔は変わらない（腕木の寸法で決まる）."""
        m = make_good_model()
        m.config.deck_widths = (800, 800)
        self.assertGreater(m.deck_width_total, m.post_row_spacing_mm)
        r = [c for c in run_all_checks(m) if c.check_id == 11][0]
        self.assertEqual(r.status, OK)

    def test_single_row_has_no_cross_spacing(self):
        """一側足場は内外2列でないので梁間方向の制限は対象外."""
        m = make_good_model()
        m.config.scaffold_form = "一側足場"
        m.config.deck_widths = (800, 800)
        r = [c for c in run_all_checks(m) if c.check_id == 11][0]
        self.assertEqual(r.status, OK)


class TestSeriesLockCheck(unittest.TestCase):
    """系列ロック（法規チェック9）。このツールの根幹の不変条件.

    読込側（assert_series）はテストしていたが、モデル側のチェック9は
    無効化してもテストが落ちなかった（変異テストで判明）。
    """

    def _model_with(self, part):
        m = make_good_model()
        m.master.parts.append(part)
        return m

    def test_foreign_part_is_ng(self):
        foreign = Part(series_id="waku", category="支柱", model_no="W-X",
                       nominal_dim=1829, actual_dim=1829, diameter=48.6,
                       weight_kg=10.0, note="")
        r = [c for c in run_all_checks(self._model_with(foreign))
             if c.check_id == 9][0]
        self.assertEqual(r.status, NG)
        self.assertIn("混在", r.message)

    def test_clean_model_is_ok(self):
        m = make_good_model()
        r = [c for c in run_all_checks(m) if c.check_id == 9][0]
        self.assertEqual(r.status, OK)
        self.assertIn(m.master.series_id, r.message)

    def test_inch_and_metric_cannot_be_mixed(self):
        """インチ規格（1829）とセンチ規格（1800）の混在を通さない."""
        inch = Part(series_id="inch", category="布材", model_no="I-N18",
                    nominal_dim=1829, actual_dim=1829, diameter=42.7,
                    weight_kg=5.5, note="")
        r = [c for c in run_all_checks(self._model_with(inch))
             if c.check_id == 9][0]
        self.assertEqual(r.status, NG)


class TestDeckAndRailDetails(unittest.TestCase):
    """テキストの基準を追加検査した分（作業床の垂直間隔・中桟・幅木）."""

    def test_narrow_deck_rejected(self):
        """幅40cm未満は563条違反。下限判定を消してもテストが落ちなかった箇所."""
        m = make_good_model()
        m.config.deck_widths = (300,)
        r = [c for c in run_all_checks(m) if c.check_id == 2][0]
        self.assertEqual(r.status, NG)
        self.assertIn("400mm", r.message)

    def test_deck_width_is_the_sum_of_boards(self):
        """隙間は床ではない。合計で判定する（被覆幅と混同しない）."""
        m = make_good_model()
        m.config.deck_widths = (250, 200)     # 合計450mm＝OK
        r = [c for c in run_all_checks(m) if c.check_id == 2][0]
        self.assertEqual(r.status, OK)
        self.assertIn("幅450mm", r.message)

    def test_deck_vertical_pitch_over_2m_rejected(self):
        m = make_good_model()
        m.elevation.level_heights = [1000, 3500, 6000]   # 2500mm ピッチ
        r = [c for c in run_all_checks(m) if c.check_id == 2][0]
        self.assertEqual(r.status, NG)
        self.assertIn("垂直間隔", r.message)

    def test_midrail_height_out_of_range_rejected(self):
        for bad in (300, 600):
            with self.subTest(height=bad):
                m = make_good_model()
                m.config.midrail_height_mm = bad
                r = [c for c in run_all_checks(m) if c.check_id == 3][0]
                self.assertEqual(r.status, NG)
                self.assertIn("中桟", r.message)

    def test_toe_board_under_100mm_rejected(self):
        m = make_good_model()
        m.config.toe_board_height_mm = 80
        r = [c for c in run_all_checks(m) if c.check_id == 3][0]
        self.assertEqual(r.status, NG)
        self.assertIn("幅木", r.message)

    def test_defaults_satisfy_standards(self):
        m = make_good_model()
        by = {c.check_id: c for c in run_all_checks(m)}
        self.assertEqual(by[2].status, OK)
        self.assertEqual(by[3].status, OK)
        self.assertIn("中桟450", by[3].message)


class TestHeightUsesTheTallestLeg(unittest.TestCase):
    """高さ(#8)は敷地の低い側で継ぎ足した実高さで判定する（名目だけ見ない）."""

    def _model(self):
        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(28000, master=master),
            config=ScaffoldConfig(), building_height_mm=27700,
        )

    def test_flat_site_uses_nominal_height(self):
        c = [r for r in run_all_checks(self._model()) if r.check_id == 8][0]
        self.assertEqual(c.status, "OK")
        self.assertNotIn("継ぎ足した", c.message)

    def test_terrace_pushes_the_low_side_over_31m(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        m = self._model()          # 名目28.1m。低い側で5m継ぎ足すと33m超
        ground = GroundModel(points=[(0, 0, 5000), (30000, 0, 0),
                                     (30000, 20000, 0), (0, 20000, 5000)])
        terrain = solve_post_feet(m, ground)
        c = [r for r in run_all_checks(m, terrain=terrain) if r.check_id == 8][0]
        self.assertEqual(c.status, "WARN", c.message)
        self.assertIn("脚の伸び", c.message)
        self.assertIn("2本組", c.message)


class TestSingleRowFootprint(unittest.TestCase):
    """一側足場の収まりは離れ＋床受けブラケット長で見る（離れだけでは過小）."""

    def _model(self, clearance):
        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(9000, master=master),
            config=ScaffoldConfig(scaffold_form="一側足場"),
            clearance_space_mm=clearance,
        )

    def test_footprint_includes_the_bracket_deck(self):
        m = self._model(900)
        need = max(e.standoff for e in m.plan.edges) + m.post_row_spacing_mm
        tight = self._model(need - 50)
        c = [r for r in run_all_checks(tight) if r.check_id == 1][0]
        self.assertEqual(c.status, "NG", c.message)
        self.assertIn("床受けブラケット長", c.message)
        wide = self._model(need + 50)
        c2 = [r for r in run_all_checks(wide) if r.check_id == 1][0]
        self.assertEqual(c2.status, "OK", c2.message)



class TestSheetedTieSpacing(unittest.TestCase):
    """シート張りの足場の壁つなぎは原則 2層2スパン以内（計画届作成の手引 チェックリスト No.17）."""

    def _check(self, sheet, span_step):
        from ashiba.law_check import check_wall_ties
        from ashiba.model import generate_wall_ties

        m = make_good_model()
        m.config.sheet_type = sheet
        m.config.wall_tie_span_step = span_step
        m.wall_ties = generate_wall_ties(m.plan, m.elevation, m.config)
        return check_wall_ties(m)

    def test_three_spans_with_mesh_is_warned(self):
        r = self._check("メッシュシート", 3)
        self.assertEqual(r.status, WARN)
        self.assertIn("2層2スパン以内", r.message)

    def test_two_spans_or_no_sheet_is_ok(self):
        self.assertEqual(self._check("メッシュシート", 2).status, OK)
        self.assertEqual(self._check("", 3).status, OK)
