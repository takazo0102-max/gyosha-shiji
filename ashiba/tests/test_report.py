"""割付レポート（人が読む成果物）の内容テスト."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import run_all_checks
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.report import write_report_md
from ashiba.stairs import auto_place_stairs

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build():
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(16300, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev, config=ScaffoldConfig(),
        building_height_mm=16000,
    )


def render(model, stair_plan=None, **kw) -> str:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "r.md"
        write_report_md(
            model, take_off(model), run_all_checks(model), path,
            "テスト", stair_plan=stair_plan, **kw,
        )
        return path.read_text(encoding="utf-8")


class TestReport(unittest.TestCase):
    def test_stairs_section_lists_every_tower(self):
        m = build()
        plan = auto_place_stairs(m, count=3)
        text = render(m, plan)
        self.assertIn("## 昇降設備（階段室）", text)
        for t in plan.towers:
            self.assertIn(f"| {t.edge_index} | {t.start_mm:.0f}mm |", text)

    def test_extra_stairs_beyond_requirement_are_flagged(self):
        """必要数を超える箇所数は費用に効くので、そうと分かるようにする."""
        m = build()
        plan = auto_place_stairs(m, min_per_face=1)
        self.assertGreater(plan.count, plan.required_count)
        self.assertIn(f"{plan.required_count}箇所で足ります", render(m, plan))

    def test_section_is_omitted_without_stairs(self):
        self.assertNotIn("## 昇降設備", render(build()))

    def test_disclaimer_is_always_present(self):
        """有資格者確認前提の下書きである旨（指示書9）を落とさない."""
        self.assertIn("計画作成参画者（有資格者）が確認する前提の下書き", render(build()))


class TestReportCoversTheWholePlan(unittest.TestCase):
    """計画の可否を左右する数字が本文に出ること.

    構造計算の検定比・壁つなぎ・敷地の高低差は、以前は plan.json と
    設置届Excelにしかなく、人が読む割付レポートには無かった。
    """

    def setUp(self):
        self.m = build()

    def test_wall_tie_section_always_present(self):
        text = render(self.m)
        self.assertIn("## 壁つなぎ", text)
        self.assertIn(f"本数: {len(self.m.wall_ties)}箇所", text)

    def test_structural_ratios_are_shown(self):
        from ashiba.structural import SiteCondition, run_structural

        res = run_structural(self.m, take_off(self.m), SiteCondition())
        text = render(self.m, structural=res)
        self.assertIn("## 構造計算", text)
        self.assertIn(str(res.wall_tie.ratio), text)
        self.assertIn(str(res.post.ratio), text)

    def test_structural_warnings_are_shown(self):
        from ashiba.structural import SiteCondition, run_structural

        res = run_structural(self.m, take_off(self.m), SiteCondition())
        text = render(self.m, structural=res)
        for w in res.warnings:
            self.assertIn(w, text)

    def test_terrain_section_only_when_sloped(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        flat = solve_post_feet(self.m, GroundModel())
        self.assertNotIn("## 敷地の高低差", render(self.m, terrain=flat))
        slope = solve_post_feet(self.m, GroundModel(points=[
            (0, 0, 0), (30000, 0, 400), (30000, 20000, 1200), (0, 20000, 800),
        ]))
        text = render(self.m, terrain=slope)
        self.assertIn("## 敷地の高低差", text)
        self.assertIn("脚部構成", text)

    def test_extras_section_only_when_present(self):
        from ashiba.platforms import LoadingStage, validate_platforms

        self.assertNotIn("## 付帯設備", render(self.m))
        pf = validate_platforms(self.m, [LoadingStage(
            edge_index=0, start_mm=12600, span_count=2, levels=[3])])
        text = render(self.m, platforms=pf)
        self.assertIn("## 付帯設備", text)
        self.assertIn("荷受けステージ 1基", text)


class TestPlanJsonIsSelfSufficient(unittest.TestCase):
    """「配置用」と謳う以上、これだけで再配置できること."""

    def _json(self, **kw):
        import json

        from ashiba.report import write_plan_json

        m = build()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"
            write_plan_json(m, path, **kw)
            return m, json.loads(path.read_text(encoding="utf-8"))

    def test_every_edge_carries_placement_and_gdl_params(self):
        from ashiba.gdl_params import line_params

        m, d = self._json()
        self.assertEqual(len(d["edges"]), len(m.plan.edges))
        for ep, e in zip(m.plan.edges, d["edges"]):
            self.assertEqual(e["gdl_params"], line_params(m, ep))
            self.assertAlmostEqual(e["placement"]["x_mm"], ep.start_post[0])

    def test_config_is_recorded(self):
        m, d = self._json()
        self.assertEqual(d["config"]["post_row_spacing_mm"], m.post_row_spacing_mm)
        self.assertEqual(d["config"]["scaffold_form"], m.config.scaffold_form)

    def test_optional_sections_appear_only_when_given(self):
        from ashiba.stairs import auto_place_stairs

        _m, plain = self._json()
        self.assertNotIn("stairs", plain)
        m, with_stairs = self._json(stair_plan=auto_place_stairs(build()))
        self.assertIn("stairs", with_stairs)
        self.assertEqual(
            len(with_stairs["stairs"]["towers"]), with_stairs["stairs"]["count"]
        )


class TestWarningsAreSeparatedFromNotes(unittest.TestCase):
    """対応が要るものと、何をどう解いたかの説明を混ぜない."""

    def setUp(self):
        from ashiba.structural import SiteCondition, run_structural
        from ashiba.terrain import GroundModel, solve_post_feet

        self.m = build()
        self.terrain = solve_post_feet(self.m, GroundModel(points=[
            (0, 0, 0), (30000, 0, 400), (30000, 20000, 1200), (0, 20000, 800),
        ]))
        self.res = run_structural(
            self.m, take_off(self.m), SiteCondition(), terrain=self.terrain
        )

    def test_condition_explanation_is_a_note_not_a_warning(self):
        """どのジャッキ量で検定したかは説明であって是正項目ではない."""
        self.assertTrue(
            any("最大繰出し" in n for n in self.res.notes), self.res.notes
        )
        self.assertFalse(any("最大繰出し" in w for w in self.res.warnings))

    def test_unverified_capacity_stays_a_warning(self):
        """未確認の耐力値は提出前に必ず解消するので警告のまま."""
        self.assertTrue(
            any("未確認の耐力値" in w for w in self.res.warnings), self.res.warnings
        )

    def test_terrain_absorption_is_a_note_and_over_limit_is_a_warning(self):
        self.assertTrue(
            any("吸収しました" in n for n in self.terrain.notes), self.terrain.notes
        )
        self.assertFalse(any("吸収しました" in w for w in self.terrain.warnings))
        self.assertTrue(
            any("実務上限" in w for w in self.terrain.warnings), self.terrain.warnings
        )

    def test_report_marks_them_differently(self):
        text = render(self.m, structural=self.res, terrain=self.terrain)
        for n in self.res.notes:
            self.assertIn(f"ℹ️ {n}", text)
        for w in self.res.warnings:
            self.assertIn(f"⚠️ {w}", text)


if __name__ == "__main__":
    unittest.main()
