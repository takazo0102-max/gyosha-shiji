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


def render(model, stair_plan=None) -> str:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "r.md"
        write_report_md(
            model, take_off(model), run_all_checks(model), path,
            "テスト", stair_plan=stair_plan,
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


if __name__ == "__main__":
    unittest.main()
