"""開口（梁枠）を線で指す（利用者の指定 2026-10-24: 開口のコマンド作って、開口に梁枠つける。線を引いて押す形）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.opening_pick import (_frame, fit_beam, format_openings, parse_openings, pick_opening, same_place)

ROOT = Path(__file__).resolve().parents[1]
RECT = [[0, 0], [24000, 0], [24000, 12000], [0, 12000]]


def _model(**extra):
    return solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800", **extra}).model


def _pt(ep, t, n):
    o, u, nrm = _frame(ep)
    return (o[0] + u[0] * t + nrm[0] * n, o[1] + u[1] * t + nrm[1] * n)


class TestPick(unittest.TestCase):
    def setUp(self):
        self.m = _model()

    def test_line_over_two_spans_gets_the_two_span_beam(self):
        ep = self.m.plan.edges[0]
        pick, why = pick_opening(self.m, _pt(ep, 2000, -300), _pt(ep, 5400, -300))
        self.assertEqual(why, "")
        self.assertEqual((pick.face, pick.start_mm, pick.beam_span_mm, pick.model_no), ("南面", 1829.0, 3658, "NDH36"))
        self.assertEqual(pick.spans, [1829.0, 1829.0])
        self.assertTrue(pick.others)                          # ほかの大きさも選べる

    def test_line_on_another_face_and_reversed(self):
        ep = self.m.plan.edges[1]
        pick, _ = pick_opening(self.m, _pt(ep, 5400, -200), _pt(ep, 1900, -200))
        self.assertEqual(pick.edge_index, ep.edge_index)

    def test_far_or_crossing_line_is_rejected(self):
        ep = self.m.plan.edges[0]
        self.assertIsNone(pick_opening(self.m, _pt(ep, 2000, 5000), _pt(ep, 5400, 5000))[0])     # 躯体の中
        self.assertIsNone(pick_opening(self.m, _pt(ep, 2000, 500), _pt(ep, 2100, -3000))[0])     # 面に直交

    def test_beam_must_land_on_posts(self):
        ep = self.m.plan.edges[0]
        fits, _why = fit_beam(self.m, ep, 1900, 5500)
        posts = [0.0]
        for s in ep.spans:
            posts.append(posts[-1] + s)
        for p, s in fits:
            self.assertTrue(any(abs(q - p) < 1 for q in posts) and any(abs(q - p - s) < 1 for q in posts))


class TestStoreAndPlace(unittest.TestCase):
    def test_text_round_trip(self):
        items = [{"face": "南面", "start_mm": 1829, "beam_span_mm": 3658, "level": 1, "reason": "搬入口"},
                 {"edge_index": 2, "start_mm": 0, "beam_span_mm": 5487, "level": 2}]
        text = format_openings(items)
        self.assertEqual(text, "南面 1829 3658 1 搬入口; 辺2 0 5487 2")
        back, errs = parse_openings(text)
        self.assertEqual(errs, [])
        self.assertEqual(back[0]["face"], "南面")
        self.assertEqual(back[1]["edge_index"], 2)
        self.assertEqual(parse_openings("南面 x")[1], ["南面 x"])

    def test_same_place(self):
        a = {"face": "南面", "start_mm": 1829, "beam_span_mm": 3658}
        self.assertTrue(same_place(a, {"face": "南面", "start_mm": 3658, "beam_span_mm": 3658}))
        self.assertFalse(same_place(a, {"face": "南面", "start_mm": 5487, "beam_span_mm": 3658}))
        self.assertFalse(same_place(a, {"face": "東面", "start_mm": 1829, "beam_span_mm": 3658}))

    def test_spec_object_keeps_openings_and_solve_uses_them(self):
        from ashiba.spec_object import params_from_spec, spec_from_params

        spec = spec_from_params({"openList": "南面 1829 3658 1 搬入口"})
        self.assertEqual(params_from_spec(spec)["openList"], "南面 1829 3658 1 搬入口")
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800", **spec})
        self.assertEqual(r.openings.openings[0].edge_index, 0)
        self.assertEqual(r.openings.removed_posts, 2)
        self.assertEqual(r.quantity.qty_of("梁枠"), 2)
        xml = (ROOT / "gdl" / "hsf" / "ashiba_spec" / "paramlist.xml").read_text(encoding="utf-8")
        self.assertIn('<String Name="openList">', xml)

    def test_palette_button(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("開口", [a.title for a in ACTIONS])
        self.assertIn("開口", dict(PANEL_GROUPS)["直す"])
        self.assertTrue((ROOT / "scripts" / "opening_run.py").exists())


if __name__ == "__main__":
    unittest.main()


class TestBeamDetailAndBraces(unittest.TestCase):
    """梁枠の詳細と、開口の通路に掛かる筋かい（利用者の指摘 2026-10-24: 梁枠の詳細上げて／1層目の両サイドに謎のブレス）."""

    def test_braces_over_the_passage_are_not_drawn(self):
        from ashiba.gdl_params import face_drawn_counts

        base = {"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800"}
        plain = solve_all(base)
        r = solve_all({**base, "openings": [{"face": "南面", "start_mm": 1829, "beam_span_mm": 3658, "level": 2}]})
        ep = r.model.plan.edges[0]
        n_open = face_drawn_counts(r.model, ep, r.stair_plan, r.openings)["qtyBrace"]
        n_plain = face_drawn_counts(plain.model, plain.model.plan.edges[0], plain.stair_plan, plain.openings)["qtyBrace"]
        self.assertLess(n_open, n_plain)
        # 数量は隣の構面へ移す扱いで同じ
        self.assertEqual(r.quantity.qty_of("筋交"), plain.quantity.qty_of("筋交"))
        self.assertTrue(any("隣の構面へ移して" in n for n in r.quantity.notes))
        d = ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts"
        for f in ("3d.gdl", "2d.gdl", "1d.gdl"):
            self.assertIn("bmH[ib9]", (d / f).read_text(encoding="utf-8"), f)

    def test_beam_hangs_one_koma_below_the_deck_with_saddles(self):
        p3 = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("if komaPitch > 0.001 then bmDrop = komaPitch", p3)
        self.assertIn("! 梁渡し（NDHW）", p3)
        self.assertIn("! 両隣のスパンのつなぎ材", p3)
        self.assertNotIn("sgn ", p3)                 # GDL の組み込み関数 SGN と同じ名前の変数は 3D が止まる
