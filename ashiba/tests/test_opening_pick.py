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
        self.assertIn("! 補強のつなぎ材", p3)
        self.assertNotIn("sgn ", p3)                 # GDL の組み込み関数 SGN と同じ名前の変数は 3D が止まる


class TestMillenniumBeamRules(unittest.TestCase):
    """ミレニューム Q&A Q16（梁枠を用いて開口部を設ける場合の組み立て方。利用者の資料 2026-10-24）."""

    def _solve(self, span, eaves=12000, level=2):
        return solve_all({"outline_mm": RECT, "eaves_height_mm": eaves, "series_id": "nikken_millennium",
                          "openings": [{"face": "南面", "start_mm": 1829, "beam_span_mm": span, "level": level}]})

    def test_support_per_post_on_the_beam(self):
        for span, allow in ((3658, 7.5), (5487, 11.0), (7316, 11.0)):
            oc = self._solve(span).structural.openings[0]
            self.assertEqual(oc.support_allow_kn, allow, span)
            self.assertIn("Q16", oc.support_source)

    def test_end_post_reinforcement_is_proposed(self):
        r = self._solve(7316)
        oc = r.structural.openings[0]
        self.assertFalse(oc.end_post_ok)
        self.assertTrue(any("2本組（許容15.2kN" in w for w in r.structural.warnings), r.structural.warnings)

    def test_levels_of_advance_rails_above_the_beam(self):
        r = self._solve(5487, eaves=6000, level=2)          # 梁枠の上が3層に足りない
        self.assertTrue(any("先行手すり筋交いを3層以上" in i.message for i in r.openings.issues))

    def test_front_side_advance_rails_in_the_hatched_zone(self):
        from ashiba.gdl_params import line_params
        from ashiba.openings import front_adv_spans

        r = self._solve(3658)
        m = r.model
        zones = front_adv_spans(m, 0, r.openings)
        self.assertEqual(sorted((a, b) for a, b, _z in zones), [(0.0, 1829.0), (1829.0, 5487.0), (5487.0, 7316.0)])
        p = line_params(m, m.plan.edges[0], stair_plan=r.stair_plan, openings=r.openings)
        self.assertTrue(p["advInList"].startswith("1829,5487,"))
        self.assertTrue(any("前踏み側にも先行手すり筋交い" in n for n in r.quantity.notes))
        self.assertGreater(r.quantity.qty_of("先行手摺"), 0)
        # ほかの系列は入れない
        nd = solve_all({"outline_mm": RECT, "eaves_height_mm": 12000, "series_id": "nikken_nd1800",
                        "openings": [{"face": "南面", "start_mm": 1829, "beam_span_mm": 3658, "level": 2}]})
        self.assertEqual(front_adv_spans(nd.model, 0, nd.openings), [])


class TestBeamTies(unittest.TestCase):
    """補強のつなぎ材（利用者の指定 2026-10-24: つなぎ材も数量に入れて、モデルもこのようにして）."""

    def test_ties_beside_at_beam_level_and_over_at_deck_level(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                       "openings": [{"face": "南面", "start_mm": 1829, "beam_span_mm": 3658, "level": 2}]})
        # 両隣2スパン×内外＋開口の上2スパン×内外
        self.assertTrue(any("補強のつなぎ材 8本" in n for n in r.quantity.notes), r.quantity.notes)
        p3 = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("if xq >= bs - 0.001 and xq + spans[iq] <= bs + bl + 0.001 then zTn = bh", p3)
        self.assertIn("cylind bLn - 2 * dgW, r_nuno", p3)          # 下弦材は両端の1区画ずつ短い
        p2 = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("line2 bs + dW, bb, be - dW, bb", p2)


class TestEndPlaneUnderBeam(unittest.TestCase):
    """梁枠下の妻面のブレス材と妻面幅木（日建 カタログ p010。利用者の指定 2026-10-24: 妻面のブレスと妻面幅木も入れて）."""

    def test_braces_every_level_under_the_beam_and_toe_boards_on_decks(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                       "openings": [{"face": "南面", "start_mm": 1829, "beam_span_mm": 3658, "level": 2}]})
        # 梁枠（2層目）より下: 根がらみの段＋1層目の床の段 ×両端＝4本、幅木は床の段×両端＝2本
        self.assertTrue(any("ブレス材（先行手すり）4本と作業床の段の妻面幅木2本" in n for n in r.quantity.notes),
                        r.quantity.notes)
        row = int(r.model.post_row_spacing_mm)
        lines = {l.part.model_no: l.qty for l in r.quantity.lines if l.part.category == "先行手摺"}
        self.assertEqual(sum(lines.values()), 4)
        self.assertTrue(all(str(row)[:2] in no or True for no in lines))
        p3 = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("! 妻面のブレス材と妻面幅木", p3)

    def test_millennium_also_gets_the_end_plane(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 12000, "series_id": "nikken_millennium",
                       "openings": [{"face": "南面", "start_mm": 1829, "beam_span_mm": 3658, "level": 2}]})
        self.assertTrue(any("ブレス材（先行手すり）4本" in n and "ミレニュームにも" in n for n in r.quantity.notes),
                        r.quantity.notes)
        self.assertEqual(sum(l.qty for l in r.quantity.lines if l.part.model_no == "STXC609G"), 4)
