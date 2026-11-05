"""くさびのフィート寸法の隅（利用者の指定 2026-10-23）: 離れを動かして無理に繋がず、繋がらない隅は
コーナーステップ（GDL 部品 ashiba_cstep）で納める。熟練の所長・足場作業者の目線."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.plan_solver import WEDGE_GAP_CLOSED_MM, WEDGE_STEP_MAX_MM, WEDGE_STEP_MIN_MM

RECT = [[0, 0], [30000, 0], [30000, 20000], [0, 20000]]           # 離れ 270〜350 でも隅が閉じない
CLOSABLE = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]       # 離れ 334・346 で全部の隅が閉じる
L = [[0, 0], [24000, 0], [24000, 8000], [12000, 8000], [12000, 16000], [0, 16000]]
U = [[0, 0], [30000, 0], [30000, 18000], [20000, 18000], [20000, 6000], [10000, 6000], [10000, 18000], [0, 18000]]


def _solve(outline, **extra):
    return solve_all({"outline_mm": outline, "eaves_height_mm": 9000, "series_id": "nikken_nd1800", **extra})


class TestFeetCorners(unittest.TestCase):
    def test_standoff_stays_in_the_band_and_gaps_are_steps(self):
        for name, o in (("長方形", RECT), ("L字", L), ("コの字", U)):
            r = _solve(o)
            with self.subTest(name):
                # 離れは 270〜350 の帯（利用者の指定 2026-10-23: 270〜350 くらいの隙間感でいい）
                self.assertTrue(all(270 - 1e-6 <= e.standoff <= 350 + 1e-6 for e in r.model.plan.edges),
                                [e.standoff for e in r.model.plan.edges])
                self.assertTrue(r.model.plan.corner_steps)
                for cs in r.model.plan.corner_steps:
                    self.assertTrue(WEDGE_STEP_MIN_MM <= cs.gap_mm <= WEDGE_STEP_MAX_MM, cs)
                # 面の長さ＝スパンの合計＋終点の隙間（閉じた隅は 30mm 以下）
                gaps = {c.edge_index: c.gap_mm for c in r.model.plan.corner_steps}
                for e in r.model.plan.edges:
                    (sx, sy), (ex, ey) = e.start_post, e.end_post
                    length = abs(ex - sx) + abs(ey - sy)
                    rest = length - sum(e.spans) - gaps.get(e.edge_index, 0.0)
                    self.assertTrue(-0.5 <= rest <= WEDGE_GAP_CLOSED_MM, (e.edge_index, rest))
                self.assertFalse([e for e in r.model.plan.edges if e.remedy])

    def test_corners_close_when_the_band_allows(self):
        r = _solve(CLOSABLE)
        self.assertEqual(r.model.plan.corner_steps, [])
        self.assertTrue(all(270 <= e.standoff <= 350 for e in r.model.plan.edges))
        for e in r.model.plan.edges:
            (sx, sy), (ex, ey) = e.start_post, e.end_post
            self.assertLessEqual(abs(ex - sx) + abs(ey - sy) - sum(e.spans), WEDGE_GAP_CLOSED_MM)

    def test_metric_and_option_keep_the_old_way(self):
        m = solve_all({"outline_mm": L, "eaves_height_mm": 9000, "series_id": "shinwa_A"})   # メートルは従来どおり
        self.assertEqual(m.model.plan.corner_steps, [])
        old = _solve(CLOSABLE, corner_steps=False)                                 # 入力で従来の解き方
        self.assertEqual(old.model.plan.corner_steps, [])
        self.assertTrue(any(e.standoff > 300 for e in old.model.plan.edges))

    def test_corner_posts_are_not_shared_across_a_gap(self):
        from ashiba.gdl_params import shared_corner_skips

        r = _solve(RECT)
        for e in r.model.plan.edges:
            sk = shared_corner_skips(r.model, e.edge_index)
            self.assertEqual(sk, {"skipInS": 0, "skipInE": 0})     # 隅に隙間 → 両方の面が自分の支柱を描く


class TestCornerStepPart(unittest.TestCase):
    def test_placed_at_the_last_post_with_every_level(self):
        from ashiba.attachments import CSTEP_OBJECT, cstep_placements

        r = _solve(RECT)
        pls = cstep_placements(r.model)
        self.assertEqual(len(pls), len(r.model.plan.corner_steps))
        south = r.model.plan.edges[0]
        p = next(p for p in pls if abs(p.params["faceAng"]) < 1e-6)
        self.assertEqual(p.part, CSTEP_OBJECT)
        self.assertAlmostEqual(p.x_mm, south.start_post[0] + sum(south.spans), delta=0.5)
        self.assertAlmostEqual(p.params["gapL"] * 1000, r.model.plan.corner_steps[0].gap_mm, delta=0.5)
        self.assertEqual(len(p.params["lvList"].split(",")), len(r.model.elevation.level_heights))
        self.assertEqual(p.params["stepName"], "NDCS05")                      # 610 幅は踏板 500
        self.assertAlmostEqual(p.params["deckTop"], 0.0427 / 2 + 0.045)        # 足場ラインの床の上面と同じ高さ

    def test_quantity_counts_steps_per_level(self):
        r = _solve(RECT)
        cs = [l for l in r.quantity.lines if l.part.category == "コーナー踏板"]
        n_lv = len(r.model.elevation.level_heights)
        self.assertEqual(sum(l.qty for l in cs), len(r.model.plan.corner_steps) * n_lv)
        wide = _solve(RECT, scaffold_width_mm=914)                             # 914 幅は踏板 500+240
        self.assertEqual({l.part.model_no for l in wide.quantity.lines if l.part.category == "コーナー踏板"},
                         {"NDCS05", "NDCS02"})

    def test_gdl_part_files(self):
        d = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_cstep"
        p2 = (d / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        p3 = (d / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        # 隙間の×は描かない（利用者の指定 2026-10-23）。カタログの形（爪 65＋縞鋼板 460、t=3.2）で描く
        self.assertNotIn("line2 0, -rowW, gapL, 0", p2)
        self.assertIn("rect2 0, yB, plL, yA", p2)
        self.assertIn("block plL, w, 0.0032", p3)
        # 踏板は床の上面に（利用者の指摘 2026-10-24: コーナー部分が渡れない。布材の高さに置いて床より沈んでいた）
        self.assertIn("add 0, y0 - w, z + deckTop", p3)
        for n in ("gapL", "rowW", "lvList", "stepName", "plW1", "plW2", "plL", "hookL", "flipX", "deckTop"):
            self.assertIn(f'Name="{n}"', (d / "paramlist.xml").read_text(encoding="utf-8"))


class TestGapCorner(unittest.TestCase):
    """隙間の寸法と、隙間のある出隅の建地（利用者の指摘 2026-10-24: 隙間が狭すぎて輪っか部分が干渉している／
    コーナー部分の支柱がない部分がある／コーナーのネットブラケットは斜めにして）."""

    def test_gap_is_wide_enough_for_the_koma(self):
        # 隙間の両側に建地が立つ。コマ φ106 どうしが当たらず、くさびを打つ手が入る 150 以上
        self.assertGreaterEqual(WEDGE_STEP_MIN_MM, 106 + 40)
        for o in (RECT, L, U):
            for cs in _solve(o).model.plan.corner_steps:
                self.assertGreaterEqual(cs.gap_mm, 150, cs)

    def test_gap_corner_gets_its_own_post(self):
        from ashiba.gdl_params import face_drawn_counts, line_params

        r = _solve(RECT)
        m = r.model
        n = len(m.plan.outline.edges)
        nxt = {(c.edge_index + 1) % n for c in m.plan.corner_steps if not c.at_start}
        self.assertTrue(nxt)
        for ep in m.plan.edges:
            want = ep.edge_index in nxt and m.corner_kind_start(ep.edge_index) == "出隅"
            self.assertEqual(m.gap_corner_post_start(ep.edge_index), want, ep.edge_index)
            self.assertEqual(line_params(m, ep, stair_plan=r.stair_plan)["cornerSP"], 1 if want else 0)
        self.assertEqual(m.gap_corner_posts(), len(nxt))
        # 図示の支柱位置数にも1本ずつ足す（数量のジャッキは test_jack_selection）
        drawn = sum(face_drawn_counts(m, ep, r.stair_plan)["qtyPostPos"] for ep in m.plan.edges)
        from ashiba.quantity import standing_post_positions

        self.assertEqual(drawn, standing_post_positions(m, 2))
        # 隙間の手前で止まる面の終点の支柱（内外）も立つ（隅で共有しない）
        self.assertGreater(drawn, m.plan.total_posts * 2 + m.outer_corner_posts() + m.gap_corner_posts())
        self.assertTrue(any("コーナーステップ）のある出隅" in n for n in r.quantity.notes), r.quantity.notes)

    def test_gdl_draws_the_gap_corner_post(self):
        d = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        self.assertIn('Name="cornerSP"', (d / "paramlist.xml").read_text(encoding="utf-8"))
        p3 = (d / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        # 隅の升目の建地の並び（隙間の手前の建地 (-cSW, 0) は cornerSP のとき）
        self.assertIn("if cornerSP = 1 or cnrLowP > 0.001 then", p3)
        self.assertIn("for iq = 1 to nCq", p3)
        self.assertIn("circle2 -cSW, 0, r_sic", (d / "scripts" / "2d.gdl").read_text(encoding="utf-8"))
        self.assertIn("cornerS + cornerSP", (d / "scripts" / "1d.gdl").read_text(encoding="utf-8"))

    def test_corner_net_bracket_points_at_the_building_corner(self):
        import math

        from ashiba.attachments import NETBK_OBJECT, net_placements

        r = _solve(RECT, horizontal_net_levels=[2])
        m = r.model
        corners = {tuple(round(v) for v in e.start) for e in m.plan.outline.edges
                   if m.corner_kind_start(e.index) == "出隅"}
        diag = 0
        for p in net_placements(m):
            if p.part != NETBK_OBJECT:
                continue
            ang = p.params["faceAng"] % 90.0
            if min(ang, 90.0 - ang) < 1.0:
                continue
            diag += 1
            # 腕（部品の +Y）は躯体の角を向く
            a = math.radians(p.params["faceAng"] + 90.0)
            tip = (p.x_mm + math.cos(a) * 1000, p.y_mm + math.sin(a) * 1000)
            near = min(corners, key=lambda c: math.hypot(c[0] - p.x_mm, c[1] - p.y_mm))
            to_c = math.atan2(near[1] - p.y_mm, near[0] - p.x_mm)
            to_t = math.atan2(tip[1] - p.y_mm, tip[0] - p.x_mm)
            self.assertLess(abs(math.remainder(to_c - to_t, 2 * math.pi)), 1e-6)
        self.assertEqual(diag, len(corners) * len(m.config.horizontal_net_levels))


if __name__ == "__main__":
    unittest.main()
