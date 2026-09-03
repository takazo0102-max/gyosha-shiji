"""付帯設備どうし・開口部との衝突検査."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.brackets import BracketSection
from ashiba.conflicts import check_conflicts
from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.openings import Opening, validate_openings
from ashiba.plan_solver import solve_plan
from ashiba.platforms import Hoist, LoadingStage, validate_platforms
from ashiba.stairs import place_stairs_at

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build():
    master = load_master("shinwa_A")
    return ScaffoldModel(
        master=master, plan=solve_plan(RECT, master),
        elevation=solve_elevation(16300, master=master),
        config=ScaffoldConfig(),
    )


class TestConflictsWithOpenings(unittest.TestCase):
    """開口部（梁枠より下は支柱を抜いた通路）と同じ区間の付帯設備."""

    def setUp(self):
        self.m = build()
        # 辺0の 9000〜12600 に梁枠、第2層。第1層は通路
        self.op = validate_openings(self.m, [Opening(0, 9000, 3600, level=2)])

    @staticmethod
    def kinds(issues):
        return [(i.kind, i.severity) for i in issues]

    def test_stair_tower_in_opening_is_ng(self):
        sp = place_stairs_at(self.m, [{"edge_index": 0, "start_mm": 9000}])
        got = check_conflicts(self.m, self.op, stair_plan=sp)
        self.assertIn(("階段室×開口部", "NG"), self.kinds(got))
        self.assertIn("通路", got[0].message)
        self.assertIn("支柱", got[0].message)

    def test_stair_tower_elsewhere_is_fine(self):
        sp = place_stairs_at(self.m, [{"edge_index": 0, "start_mm": 1800}])
        self.assertEqual(check_conflicts(self.m, self.op, stair_plan=sp), [])

    def test_loading_stage_on_beam_is_ng(self):
        pf = validate_platforms(self.m, [LoadingStage(edge_index=0, start_mm=9000)], [])
        got = check_conflicts(self.m, self.op, platforms=pf)
        self.assertIn(("ステージ×開口部", "NG"), self.kinds(got))
        self.assertIn("梁枠上", got[0].message)

    def test_bracket_below_beam_is_ng_and_on_beam_is_warn(self):
        below = BracketSection(edge_index=0, start_mm=9000, end_mm=12600,
                               direction="張出", width=600, levels=[1])
        above = BracketSection(edge_index=0, start_mm=9000, end_mm=12600,
                               direction="張出", width=600, levels=[3])
        got = check_conflicts(self.m, self.op, brackets=[below, above])
        self.assertEqual(self.kinds(got),
                         [("ブラケット区間×開口部", "NG"), ("ブラケット区間×開口部", "WARN")])
        self.assertIn("第1層", got[0].message)
        self.assertIn("偏心", got[1].message)

    def test_bracket_on_another_face_is_fine(self):
        b = BracketSection(edge_index=1, start_mm=9000, end_mm=12600,
                           direction="張出", width=600)
        self.assertEqual(check_conflicts(self.m, self.op, brackets=[b]), [])

    def test_hoist_in_opening_is_warn_and_names_landings_on_beam(self):
        pf = validate_platforms(
            self.m, [], [Hoist(edge_index=0, position_mm=10800, landing_levels=[1, 2, 4])])
        got = check_conflicts(self.m, self.op, platforms=pf)
        self.assertIn(("昇降機×開口部", "WARN"), self.kinds(got))
        self.assertIn("第2・4層", got[0].message)


class TestStageVersusBracketSection(unittest.TestCase):
    """ステージの張出ブラケットとブラケット区間が同じ区間で二重張出しになる."""

    def setUp(self):
        self.m = build()

    def test_same_span_same_level_is_ng(self):
        pf = validate_platforms(
            self.m, [LoadingStage(edge_index=0, start_mm=5400, levels=[1])], [])
        b = BracketSection(edge_index=0, start_mm=5400, end_mm=9000,
                           direction="張出", width=600)
        got = check_conflicts(self.m, None, platforms=pf, brackets=[b])
        self.assertEqual([(i.kind, i.severity) for i in got],
                         [("ステージ×ブラケット区間", "NG")])
        self.assertIn("二重", got[0].message)

    def test_different_level_is_fine(self):
        pf = validate_platforms(
            self.m, [LoadingStage(edge_index=0, start_mm=5400, levels=[1])], [])
        b = BracketSection(edge_index=0, start_mm=5400, end_mm=9000,
                           direction="張出", width=600, levels=[3])
        self.assertEqual(check_conflicts(self.m, None, platforms=pf, brackets=[b]), [])


class TestAutoStairsAvoidOpenings(unittest.TestCase):
    """自動配置の階段室は開口部の区間を避ける（サンプル2件で重なっていた）."""

    def test_auto_placement_skips_opening_range(self):
        from ashiba.openings import opening_ranges
        from ashiba.stairs import auto_place_stairs

        m = build()
        plain = auto_place_stairs(m)
        t = plain.towers[0]
        # 自動配置が選んだ区間にそのまま開口部を置くと衝突する
        op = validate_openings(m, [Opening(t.edge_index, t.start_mm, 3600, level=2)])
        self.assertTrue(check_conflicts(m, op, stair_plan=plain))
        # 避ける区間を渡せば衝突せず、移動距離の目安も守る
        sp = auto_place_stairs(m, avoid=opening_ranges(op))
        self.assertEqual(check_conflicts(m, op, stair_plan=sp), [])
        self.assertLessEqual(sp.max_travel_mm, 30000)

    def test_shipped_examples_with_openings_have_no_conflict(self):
        import json
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1] / "examples"
        for name in ("opening_beam.json", "waku_composite.json"):
            with self.subTest(name):
                r = solve_all(load_spec(root / name))
                self.assertEqual([i.message for i in r.conflicts], [])


class TestConflictsReachTheVerdict(unittest.TestCase):
    """衝突NGは総合判定の是正理由に出る（個別検証が緑でも止まる）."""

    def test_stair_in_opening_blocks_the_plan(self):
        import json
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        spec = json.loads(
            Path(__file__).resolve().parents[1].joinpath("examples", "rect_30x20.json")
            .read_text(encoding="utf-8"))
        spec["stairs"] = {"positions": [{"edge_index": 0, "start_mm": 9000},
                                        {"edge_index": 2, "start_mm": 9000}]}
        spec["openings"] = [{"edge_index": 0, "start_mm": 9000,
                             "beam_span_mm": 3600, "level": 2}]
        r = solve_all(spec)
        self.assertTrue(
            [b for b in r.verdict["blockers"] if b.startswith("付帯設備の衝突NG")],
            r.verdict)
        self.assertTrue([w for w in r.warnings if w[0] == "付帯設備の衝突"])


if __name__ == "__main__":
    unittest.main()
