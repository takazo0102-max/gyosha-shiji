"""防音パネルと荷受けステージの侵入落下防止柵（利用者の指定 2026-10-24: 防音パネルと侵入落下防止柵どっちも追加して。
GLOOBE Construction の仮設計画にあってこのツールに無かった2つ）."""

import math
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import (PANEL_H_MM, is_panel, panel_corner_pieces, sheet_clamp_count,
                                sheet_corner_clamp_count, sheet_panels, sheet_placements, sheet_rows)
from ashiba.cli import solve_all
from ashiba.platforms import FENCE_PANEL_MAX_MM, stage_fence_panels

RECT = [[0, 0], [24000, 0], [24000, 12000], [0, 12000]]
GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf"


def _solve(**extra):
    return solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800", **extra})


class TestSoundPanel(unittest.TestCase):
    def setUp(self):
        self.r = _solve(site={"sheet_type": "防音パネル"})
        self.m = self.r.model

    def test_rows_are_whole_panels_from_the_top_lapping_the_hoarding(self):
        self.assertTrue(is_panel(self.m))
        for ep in self.m.plan.edges:
            rows = sheet_rows(self.m, ep.edge_index)
            top = self.m.elevation_of(ep.edge_index).total_height
            self.assertAlmostEqual(rows[-1][1], top)
            for lo, hi in rows:
                self.assertAlmostEqual(hi - lo, PANEL_H_MM["inch"])        # 板は切れない
            # いちばん下の段は仮囲いの天端に重なる（隙間を残さない）が、1枚以上は下がらない
            self.assertLessEqual(rows[0][0], self.m.hoarding_height_mm)
            self.assertGreater(rows[0][0], self.m.hoarding_height_mm - PANEL_H_MM["inch"])

    def test_metric_series_uses_the_850_panel(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "shinwa_A",
                       "site": {"sheet_type": "防音パネル"}})
        rows = sheet_rows(r.model, 0)
        self.assertAlmostEqual(rows[0][1] - rows[0][0], PANEL_H_MM["metric"])
        self.assertTrue(any(l.part.model_no == "防音パネル・BG メーター規格18" for l in r.quantity.lines))

    def test_panels_follow_the_spans_and_stop_at_the_corner_post(self):
        ep = self.m.plan.edges[0]
        panels = [p for seg in sheet_panels(self.m, ep) for p in seg]
        row = self.m.post_row_spacing_mm
        self.assertAlmostEqual(panels[0][0], -row)          # 出隅の角の建地で止める（コーナーパネルで塞ぐ）
        coins = self.m.master.span_lengths()
        for a, b, sp in panels:
            self.assertEqual(sp, not any(abs((b - a) - c) <= 1 for c in coins))

    def test_quantities(self):
        q = self.r.quantity
        by = {l.part.model_no: l.qty for l in q.lines if l.part.category == "防音パネル"}
        self.assertIn("防音パネル・BG インチ規格18", by)
        self.assertEqual(by.get("防音パネル・BG インチ規格コーナー"), panel_corner_pieces(self.m, self.r.stair_plan))
        # 三つ爪クランプ＝コーナーパネルの数＋コーナーの箇所数（日本セイフティーのよくある質問）
        n_corners = sum(1 for e in self.m.plan.edges if self.m.corner_kind_start(e.edge_index) == "出隅")
        self.assertEqual(sheet_corner_clamp_count(self.m, self.r.stair_plan), panel_corner_pieces(self.m, self.r.stair_plan) + n_corners)
        self.assertTrue(any(f"三つ爪クランプ {sheet_corner_clamp_count(self.m, self.r.stair_plan)}個" in n for n in q.notes))
        self.assertTrue(any(f"専用クランプ {sheet_clamp_count(self.m, self.r.stair_plan)}個" in n for n in q.notes))
        # 隅の隙間はパネルの無い幅（防音シートか合板で塞ぐ）
        if self.m.plan.corner_steps:
            self.assertTrue(any("防音パネルの隙間" in n for n in q.notes))

    def test_placement_and_gdl(self):
        p = next(p for p in sheet_placements(self.m) if p.params["clampCS"])
        self.assertEqual(p.params["sheetKind"], "防音パネル")
        self.assertAlmostEqual(p.params["sheetH"], 0.862)
        self.assertAlmostEqual(p.params["zB"] * 1000, sheet_rows(self.m, 0)[0][0])
        p3 = (GDL / "ashiba_sheet" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn('isPnl = sheetKind = "防音パネル"', p3)
        self.assertIn("三つ爪クランプ", p3)
        self.assertIn('"防音パネル"', (GDL / "ashiba_spec" / "scripts" / "vl.gdl").read_text(encoding="utf-8"))

    def test_wind_treats_panels_as_solid(self):
        self.assertEqual(self.r.structural.wind.fill_ratio, 1.0)


class TestStageFence(unittest.TestCase):
    def setUp(self):
        # 柵は既定では付けない（利用者の指定 2026-10-28: 手すりの後ろのフェンスいらない）。付けるときは has_fence: true
        self.r = _solve(loading_stages=[{"edge_index": 0, "start_mm": 1829, "span_count": 2, "levels": [2, 3],
                                         "has_fence": True}])
        self.m = self.r.model
        self.st = self.r.platforms.stages[0]

    def test_panel_counts(self):
        n_front, n_side, n_gate = stage_fence_panels(self.m, self.st)
        self.assertEqual(n_front, math.ceil(self.st.length_mm(self.m) / FENCE_PANEL_MAX_MM))
        self.assertEqual(n_side, 2)
        # 扉は足場の床の中へ開く幅（建地列の間隔−120 以下）に割る
        leaf = self.m.post_row_spacing_mm - 120
        self.assertEqual(n_gate, sum(math.ceil((sp - 100) / leaf) for sp in self.st.spans(self.m)))
        notes = "\n".join(self.r.quantity.notes)
        # levels [2, 3] は1フロアずつ盛り替えるので、柵も1組
        self.assertIn(f"落下防止柵（金網）がマスタにありません（{n_front + n_side}）", notes)
        self.assertIn(f"侵入防止柵（開閉式）がマスタにありません（{n_gate}）", notes)

    def test_can_be_turned_off(self):
        # 既定（指定なし）は柵なし
        r = _solve(loading_stages=[{"edge_index": 0, "start_mm": 1829, "span_count": 2}])
        self.assertFalse(any("防止柵" in n for n in r.quantity.notes))

    def test_gdl_gets_the_fence_bit(self):
        from ashiba.gdl_params import line_params

        p = line_params(self.m, self.m.plan.edges[0], stair_plan=self.r.stair_plan, platforms=self.r.platforms)
        self.assertEqual(p["stageList"].split(",")[4], "3")              # 方杖1＋柵2
        d = GDL / "ashiba_line" / "scripts"
        self.assertIn("sgF[nSg] = int(v / 2)", (d / "1d.gdl").read_text(encoding="utf-8"))
        self.assertIn("str(sgZ[ig] + 2 * sgF[ig] + 4 * sgK[ig], 1, 0)", (d / "vl.gdl").read_text(encoding="utf-8"))
        self.assertIn("865:", (d / "3d.gdl").read_text(encoding="utf-8"))
        self.assertIn("arc2 xa, -rowW + 0.06, fWq, 0, 90", (d / "2d.gdl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
