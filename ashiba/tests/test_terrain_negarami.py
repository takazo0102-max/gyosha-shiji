"""継ぎ足した脚の区間の根がらみ（敷地高低差）.

基準の根がらみは最も高い地盤に合わせるので、下げた脚では地盤から離れる
（地上第一の布2m以下＝安衛則571条、根がらみ＝570条）。区間ごとに1段追加し、
数量・図面・法規チェックが同じ規則で見る。
"""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.gdl_params import line_params
from ashiba.law_check import run_all_checks
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.terrain import (
    GroundModel, extra_negarami, first_ledger_heights, solve_post_feet,
)

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
ROOT = Path(__file__).resolve().parents[1]


def build(series="shinwa_A"):
    master = load_master(series)
    return ScaffoldModel(
        master=master, plan=solve_plan(RECT, master),
        elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
    )


def terrace(m, drop):
    """x=0 側が drop だけ高い斜面."""
    return solve_post_feet(m, GroundModel(points=[
        (0, 0, drop), (30000, 0, 0), (30000, 20000, 0), (0, 20000, drop)]))


class TestExtraNegarami(unittest.TestCase):
    def test_flat_site_adds_nothing(self):
        m = build()
        self.assertEqual(extra_negarami(m, terrace(m, 0)), {})
        self.assertEqual(extra_negarami(m, None), {})

    def test_rows_sit_on_the_koma_grid_below_the_datum(self):
        m = build()
        t = terrace(m, 6000)
        rows = extra_negarami(m, t)
        self.assertTrue(rows)
        # 基準面は最適化で名目から動く（この敷地では名目ジャッキ100→基準脚35）。
        # 格子は実際の基準面で見る
        from ashiba.terrain import datum_first_ledger_mm

        nega = datum_first_ledger_mm(m, t)
        self.assertNotAlmostEqual(nega, m.elevation.first_ledger_height)
        koma = m.master.koma_pitch
        for edge_index, items in rows.items():
            ep = next(e for e in m.plan.edges if e.edge_index == edge_index)
            for i, level in items:
                self.assertTrue(0 <= i < ep.span_count)
                steps = (nega - level) / koma
                self.assertAlmostEqual(steps, round(steps))     # 緊結部の格子に乗る
                self.assertGreaterEqual(steps, 1)

    def test_first_ledger_stays_within_2m_on_a_gentle_slope(self):
        m = build()
        t = terrace(m, 6000)          # 30mで6m: 1スパン360mm
        hs = first_ledger_heights(m, t)
        self.assertEqual(len(hs), len(t.feet))
        self.assertLessEqual(max(hs), 2000)
        c = [r for r in run_all_checks(m, terrain=t) if r.check_id == 4][0]
        self.assertEqual(c.status, "OK", c.message)
        self.assertIn("継ぎ足し部の根がらみ", c.message)

    def test_steep_slope_still_reaches_every_foot(self):
        """急斜面でも各脚は自分の下げ段数に合う根がらみを持つ（1スパン2.4m下がる例）.

        各脚は隣のスパンで「高い側」になるので、その段数の根がらみが自分の
        緊結部に乗る。地盤からの高さはジャッキ＋1コマ程度に収まる。
        """
        m = build()
        t = terrace(m, 40000)
        hs = first_ledger_heights(m, t)
        self.assertLessEqual(max(hs), m.master.koma_pitch + 450 + 100)
        c = [r for r in run_all_checks(m, terrain=t) if r.check_id == 4][0]
        self.assertEqual(c.status, "OK", c.message)

    def test_quantity_adds_one_ledger_row_per_span(self):
        m = build()
        t = terrace(m, 6000)
        rows = sum(len(v) for v in extra_negarami(m, t).values())
        plain = take_off(m, terrain=terrace(m, 0)).qty_of("布材")
        sloped = take_off(m, terrain=t).qty_of("布材")
        self.assertEqual(sloped - plain, rows * 2)          # 内外2列
        self.assertTrue([n for n in take_off(m, terrain=t).notes if "根がらみ（布材）" in n])

    def test_frame_uses_the_adjust_frame_step(self):
        m = build("waku")
        t = terrace(m, 6000)
        rows = extra_negarami(m, t)
        self.assertTrue(rows)
        q = take_off(m, terrain=t)
        self.assertTrue([n for n in q.notes if "根がらみ（布材）" in n])

    def test_drawing_gets_the_same_step(self):
        m = build()
        p = line_params(m, m.plan.edges[0], terrain=terrace(m, 6000))
        self.assertAlmostEqual(p["footStep"], m.master.koma_pitch / 1000.0)
        self.assertEqual(line_params(m, m.plan.edges[0])["footStep"], 0.0)
        root = ROOT / "gdl" / "hsf" / "ashiba_line"
        self.assertIn('<Length Name="footStep">', (root / "paramlist.xml").read_text(encoding="utf-8"))
        for script in ("2d.gdl", "3d.gdl"):
            body = (root / "scripts" / script).read_text(encoding="utf-8")
            self.assertIn("footStep", body)
            self.assertIn("lv[1] - mlo * footStep", body)


class TestDatumIsNotWastefullyHigh(unittest.TestCase):
    """全脚が同じ段数だけ下がる解は基準面が高すぎるだけ。継ぎ足しを増やさない.

    枠組（刻み900mm）で高低差500mmの敷地に、全58脚へ調整枠を1枚ずつ足していた。
    """

    def test_min_offset_is_zero(self):
        for series, drop in (("waku", 500), ("waku", 5000), ("shinwa_A", 700), ("shinwa_A", 6000)):
            with self.subTest(series=series, drop=drop):
                m = build(series)
                t = terrace(m, drop)
                self.assertEqual(min(f.koma_offset for f in t.feet), 0)
                for f in t.feet:
                    # ジャッキは可動域内（外れる分は敷板・床掘りとして明示）
                    self.assertGreaterEqual(f.jack_mm, 30 - 1e-6)
                    self.assertLessEqual(f.jack_mm, 450 + 1e-6)


class TestFirstLedgerIsMeasuredFromTheBearingSurface(unittest.TestCase):
    def test_no_negative_heights_after_digging(self):
        """床掘りした脚は支持面が下がる。元の地盤で測ると負の高さが出ていた（-300mm）."""
        m = build("waku")
        t = terrace(m, 500)
        hs = first_ledger_heights(m, t)
        self.assertGreaterEqual(min(hs), 0)
        self.assertLessEqual(max(hs), 2000)
        c = [r for r in run_all_checks(m, terrain=t) if r.check_id == 4][0]
        self.assertEqual(c.status, "OK", c.message)
        self.assertNotIn("-", c.message.split("高さ")[1].split("mm")[0])


class TestDrawingFollowsTheDatumShift(unittest.TestCase):
    """基準面が名目から動いても、図の脚の下端は名目のジャッキ天端の格子に乗る.

    GDLは作業床・根がらみを名目の高さに描き、脚は glList＋jackList で描く。
    基準面の最適化でジャッキ量が名目から動いた分（名目100→基準脚35）を
    glList に乗せていなかったので、基準の脚でも緊結部が65mmずれて描かれていた。
    """

    def _feet_in_drawing(self, m, t):
        from ashiba.gdl_params import line_params
        from ashiba.terrain import terrain_step_mm

        step = terrain_step_mm(m)
        nominal_top = m.elevation.jack_extension
        out = []
        for ep in m.plan.edges:
            p = line_params(m, ep, terrain=t)
            if not p["glList"]:
                continue
            gls = [float(v) for v in p["glList"].split(",")]
            jks = [float(v) for v in p["jackList"].split(",")]
            for g, j in zip(gls, jks):
                # 脚の下端（地盤＋ジャッキ）は名目ジャッキ天端から刻みの整数倍だけ下
                out.append((nominal_top - (g + j)) / step)
        return out

    def test_wedge_and_frame_feet_sit_on_the_grid(self):
        for series, drop in (("shinwa_A", 6000), ("waku", 500), ("shinwa_A", 700)):
            with self.subTest(series=series, drop=drop):
                m = build(series)
                t = terrace(m, drop)
                steps = self._feet_in_drawing(m, t)
                self.assertTrue(steps)
                for s_ in steps:
                    self.assertAlmostEqual(s_, round(s_), delta=1.5 / terrain_step(m))

    def test_flat_site_is_unchanged(self):
        from ashiba.gdl_params import line_params

        m = build()
        p = line_params(m, m.plan.edges[0], terrain=terrace(m, 0))
        self.assertEqual((p["glList"], p["jackList"]), ("", ""))


def terrain_step(m):
    from ashiba.terrain import terrain_step_mm

    return terrain_step_mm(m)


if __name__ == "__main__":
    unittest.main()
