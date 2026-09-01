import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import ElevationResult, solve_elevation
from ashiba.law_check import NG, OK, WARN, run_all_checks
from ashiba.master import Part, load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
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
        config=ScaffoldConfig(),
        building_height_mm=16000,
        clearance_space_mm=2000,
    )


def make_violation_model():
    """意図的な違反モデル: 9項目すべてが検出されること（受け入れ基準）."""
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
        self.assertEqual(len(results), 9)
        bad = [r for r in results if r.status == NG]
        self.assertEqual(bad, [], f"NG: {[(r.name, r.message) for r in bad]}")

    def test_all_violations_detected(self):
        results = run_all_checks(make_violation_model())
        self.assertEqual(len(results), 9)
        by_id = {r.check_id: r for r in results}
        # 9項目すべて OK 以外（NG または WARN）で検出される
        for cid in range(1, 10):
            self.assertNotEqual(
                by_id[cid].status, OK,
                f"チェック#{cid} {by_id[cid].name} が違反を検出できていない",
            )
        # 明確なNG項目
        for cid in (1, 2, 3, 4, 5, 7, 9):
            self.assertEqual(by_id[cid].status, NG, f"#{cid}")
        # ジャッキ超過と高さ31m超は警告
        self.assertEqual(by_id[6].status, WARN)
        self.assertIn(by_id[8].status, (WARN, NG))

    def test_basis_present(self):
        for r in run_all_checks(make_good_model()):
            self.assertTrue(r.basis)


if __name__ == "__main__":
    unittest.main()
