"""系列切替（A / B / 次世代足場）の通し検証.

系列を切り替えたときに数量拾いが静かに失敗しない（マスタ引き当ての欠品が出ない）
ことを担保する。踏板幅はA:400/250、B:405/240と実寸が違うため、
既定値を決め打ちにすると欠品に気づけない。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import run_all_checks, summary
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(series: str, height: int, next_gen: bool = False):
    master = load_master(series)
    plan = solve_plan(RECT, master)
    elev = solve_elevation(height, master=master)
    model = ScaffoldModel(
        master=master, plan=plan, elevation=elev,
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1), next_gen=next_gen),
        building_height_mm=16000,
    )
    return model, take_off(model)


def missing_notes(q):
    return [n for n in q.notes if "該当部材がありません" in n]


class TestSeriesSwitching(unittest.TestCase):
    def test_deck_widths_come_from_series(self):
        a, _ = build("shinwa_A", 16300)
        b, _ = build("shinwa_B", 16150)
        self.assertEqual(a.config.deck_widths, (400, 250))
        self.assertEqual(b.config.deck_widths, (405, 240))

    def test_next_gen_is_kusabi_variant(self):
        """次世代足場は専用系列を作らず、踏板幅500のくさび派生（仕様3.1）."""
        for series, h in (("shinwa_A", 16300), ("shinwa_B", 16150)):
            model, q = build(series, h, next_gen=True)
            self.assertEqual(model.config.deck_widths[0], 500)
            # 系列の階高・コマピッチは元のまま
            self.assertEqual(model.master.koma_pitch,
                             450 if series == "shinwa_A" else 475)
            self.assertEqual(missing_notes(q), [])

    def test_explicit_deck_widths_win(self):
        master = load_master("shinwa_B")
        plan = solve_plan(RECT, master)
        elev = solve_elevation(16150, master=master)
        model = ScaffoldModel(
            master=master, plan=plan, elevation=elev,
            config=ScaffoldConfig(deck_widths=(240,)),
        )
        self.assertEqual(model.config.deck_widths, (240,))

    def test_no_missing_parts_in_any_series(self):
        for series, h, ng in (("shinwa_A", 16300, False),
                              ("shinwa_B", 16150, False),
                              ("shinwa_A", 16300, True),
                              ("shinwa_B", 16150, True)):
            with self.subTest(series=series, next_gen=ng):
                _model, q = build(series, h, ng)
                self.assertEqual(missing_notes(q), [])
                self.assertGreater(q.total_weight_kg, 0)

    def test_law_checks_pass_in_all_series(self):
        for series, h in (("shinwa_A", 16300), ("shinwa_B", 16150)):
            with self.subTest(series=series):
                model, _q = build(series, h)
                s = summary(run_all_checks(model))
                self.assertEqual(s["total"], 11)
                self.assertEqual(s["ng"], 0)

    def test_series_b_uses_b_parts_only(self):
        _model, q = build("shinwa_B", 16150)
        for line in q.lines:
            self.assertEqual(line.part.series_id, "shinwa_B", line.part.model_no)

    def test_b_series_elevation_uses_b_pitch(self):
        model, _q = build("shinwa_B", 16150)
        # B系列は階高1900・コマピッチ475
        self.assertEqual(model.master.floor_height, 1900)
        heights = model.elevation.level_heights
        if len(heights) >= 2:
            self.assertEqual(heights[1] - heights[0], 1900)


if __name__ == "__main__":
    unittest.main()
