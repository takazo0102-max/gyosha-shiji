"""手動配置（利用者の指定 2026-10-30: スパンを自分で決める超簡易モード。スパンと高さを決めて配置ボタンで置く）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.manual import (SIDE_LEFT, SIDE_RIGHT, axis_direction, parse_spans, solve_manual, solve_manual_loop,
                           span_changes, span_text, suggest_spans)


class TestSpanText(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(parse_spans("1829×4, 914"), [1829] * 4 + [914])
        self.assertEqual(parse_spans("1800x2+900 600"), [1800, 1800, 900, 600])
        self.assertEqual(parse_spans("1829*2、610"), [1829, 1829, 610])
        self.assertEqual(span_text([1829, 1829, 1829, 914, 914]), "1829×3, 914×2")
        for bad in ("", "abc", "1829×0"):
            with self.assertRaises(ValueError):
                parse_spans(bad)

    def test_suggest_from_the_line_length(self):
        self.assertEqual(suggest_spans(8230, [1829, 1524, 1219, 914, 610]), [1829] * 4 + [914])
        self.assertEqual(suggest_spans(7200, [1800, 1500, 1200, 900, 600]), [1800] * 4)


class TestManualPlacement(unittest.TestCase):
    def test_first_post_on_the_line_start_with_the_given_spans(self):
        # 縦・横どちら向きでも、右側・左側どちらでも、1本目の支柱（内側）が線の始点に来て、スパン・離れは入れたとおり
        sp = [1829, 1829, 1829, 914]
        for a, b in (((1000, 2000), (9000, 2000)), ((0, 0), (0, 8000)), ((5000, 5000), (-1000, 5100)),
                     ((0, 0), (0, -4000))):
            for side in (SIDE_RIGHT, SIDE_LEFT):
                with self.subTest(a=a, b=b, side=side):
                    _w, spec, _l = solve_manual(a, b, sp, 300, side, 6000, {"series_id": "nikken_nd1800"})
                    r = solve_all(spec)
                    ei = spec["faces"][0]
                    e = next(x for x in r.model.plan.edges if x.edge_index == ei)
                    p = e.end_post if side == SIDE_LEFT else e.start_post
                    self.assertAlmostEqual(p[0], a[0], delta=1)
                    self.assertAlmostEqual(p[1], a[1], delta=1)
                    self.assertEqual(e.spans, sp if side == SIDE_RIGHT else list(reversed(sp)))
                    self.assertAlmostEqual(e.standoff, 300, delta=1)
                    self.assertTrue(r.verdict["ok"], r.verdict)
                    self.assertEqual(len(r.model.plan.edges if r.model.edge_subset is None else r.model.edge_subset), 1)

    def test_every_series_and_standoff(self):
        for sid, big, odd in (("nikken_nd1800", 1829, 914), ("shinwa_A", 1800, 900), ("albatross", 1829, 610)):
            for so in (250, 300, 350):
                with self.subTest(sid=sid, so=so):
                    _w, spec, _l = solve_manual((0, 0), (8000, 0), [big] * 3 + [odd], so, SIDE_RIGHT, 9000,
                                                {"series_id": sid})
                    r = solve_all(spec)
                    self.assertAlmostEqual(r.model.plan.edges[0].standoff, so, delta=1)

    def test_only_general_conditions_are_carried_over(self):
        # 見本の建物の「階段 0か所」「幅の変更（西面）」を持ち込んで昇降設備 NG になっていた（実機 2026-10-30）
        from ashiba.manual import general_conditions

        base = {"module": "inch", "pens": "post=8", "stairs": {"positions": [], "count": 0},
                "width_change": {"from_mm": 610, "to_mm": 914, "level": 3, "faces": ["西面[3658-5487]"]},
                "asagao": {"stages": 1, "faces": ["北面"]}, "openings": [{"edge_index": 2}]}
        g = general_conditions(base)
        self.assertEqual(g, {"module": "inch", "pens": "post=8", "asagao": {"stages": 1}})
        _w, spec, _l = solve_manual((0, 0), (8000, 0), [1829] * 4 + [914], 300, SIDE_RIGHT, 6000,
                                    {**g, "series_id": "albatross"})
        r = solve_all(spec)
        self.assertTrue(r.verdict["ok"], r.verdict)
        self.assertTrue(r.stair_plan.towers)

    def test_slanted_line_is_refused(self):
        self.assertEqual(axis_direction((0, 0), (1000, 20)), (1.0, 0.0))     # 2° 以内はそろえる
        with self.assertRaises(ValueError):
            solve_manual((0, 0), (5000, 3000), [1829] * 3, 300, SIDE_RIGHT, 6000)

    def test_height_is_kept_and_slabs_are_not_read(self):
        _w, spec, _l = solve_manual((0, 0), (8000, 0), [1829] * 4, 300, SIDE_RIGHT, 12000, {"series_id": "albatross"})
        self.assertEqual((spec["height_from_slabs"], spec["avoid_obstacles"]), (False, False))
        top = solve_all(spec).model.elevation.level_heights[-1]
        self.assertGreaterEqual(top, 12000)                    # 最上段の作業床は軒高まで（1層 1800 の刻みで上へ）
        self.assertLess(top, 12000 + 1800)



class TestLastInputs(unittest.TestCase):
    def test_remember_and_default_spans(self):
        import tempfile
        from pathlib import Path

        from ashiba.manual import default_spans, load_last, save_last

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "前回.json"
            self.assertEqual(load_last(p), {})
            save_last(p, {"height": "9000", "spans": "1829×4, 914", "junk": 1})
            self.assertEqual(load_last(p), {"height": "9000", "spans": "1829×4, 914"})
            p.write_text("壊れた", encoding="utf-8")
            self.assertEqual(load_last(p), {})
        coins = [1829, 1524, 1219, 914, 610]
        self.assertEqual(default_spans(8200, coins, "1829×4, 914"), "1829×4, 914")       # 合計 8230 は ±300 以内
        self.assertEqual(default_spans(5500, coins, "1829×4, 914"), "1829×3")            # 遠ければ線の長さから


class TestManualLoop(unittest.TestCase):
    """一周（閉じたポリライン）: 辺ごとのスパンで一周を置く."""

    RECT = [(0, 0), (8230, 0), (8230, 5487), (0, 5487)]
    SIDES = [[1829] * 4 + [914], [1829] * 3, [1829] * 4 + [914], [1829] * 3]

    def test_rectangle_both_directions(self):
        for pts, sides in ((self.RECT, self.SIDES),
                           (self.RECT[::-1], [self.SIDES[2], self.SIDES[1], self.SIDES[0], self.SIDES[3]])):
            with self.subTest(ccw=pts == self.RECT):
                out, spec, r = solve_manual_loop(pts, sides, 300, 6000, {"series_id": "nikken_nd1800"})
                self.assertTrue(r.verdict["ok"], r.verdict)
                corners = {tuple(round(v) for v in e.start_post) for e in r.model.plan.edges}
                self.assertEqual(corners, {(0, 0), (8230, 0), (8230, 5487), (0, 5487)})   # 四隅の支柱が描いた所
                self.assertTrue(all(abs(e.standoff - 300) < 1 for e in r.model.plan.edges))
                self.assertEqual(span_changes(spec, r), [])

    def test_not_closing_is_refused(self):
        with self.assertRaisesRegex(ValueError, "右向きの辺の合計 8230mm と左向きの辺の合計 7316mm が 914mm 違う"):
            solve_manual_loop(self.RECT, [[1829] * 4 + [914], [1829] * 3, [1829] * 4, [1829] * 3], 300, 6000)

    def test_concave_corner_changes_are_reported(self):
        # 入隅は2つの面を 610 などの升目でつなぐのでスパンが変わる（置いたあとに知らせる）
        pts = [(0, 0), (14632, 0), (14632, 5487), (7316, 5487), (7316, 10974), (0, 10974)]
        sides = [[1829] * 8, [1829] * 3, [1829] * 4, [1829] * 3, [1829] * 4, [1829] * 6]
        out, spec, r = solve_manual_loop(pts, sides, 300, 6000, {"series_id": "nikken_nd1800"})
        self.assertTrue(r.verdict["ok"], r.verdict)
        ch = span_changes(spec, r)
        self.assertEqual(len(ch), 2)
        self.assertTrue(all("入隅のつなぎ" in c for c in ch))


class TestManualOpenPath(unittest.TestCase):
    """開いたポリライン（2辺の角・3辺のコの字）: 向かい合う辺を同じスパンで仮に足して解き、描いた辺だけに置く."""

    def _solve(self, pts, sides):
        from ashiba.manual import close_open_path

        lp, all_sides, keep = close_open_path(pts, sides)
        return solve_manual_loop(lp, all_sides, 300, 6000, {"series_id": "nikken_nd1800"}, keep_sides=keep)

    def test_corner_both_directions(self):
        for pts, sides, corner in (
                ([(0, 0), (8000, 0), (8000, 5000)], [[1829] * 4 + [914], [1829] * 3], (8230, 0)),
                ([(8000, 5000), (8000, 0), (0, 0)], [[1829] * 3, [914] + [1829] * 4], (8000, -487))):
            with self.subTest(pts=pts):
                _o, spec, r = self._solve(pts, sides)
                self.assertTrue(r.verdict["ok"], r.verdict)
                self.assertEqual(len(r.model.faces_only), 2)
                posts = {tuple(round(v) for v in e.start_post) for e in r.model.plan.edges
                         if e.edge_index in r.model.faces_only}
                self.assertIn(corner, posts)
                self.assertEqual(span_changes(spec, r), [])

    def test_u_shape_and_mismatch(self):
        _o, spec, r = self._solve([(0, 5487), (0, 0), (8230, 0), (8230, 5487)],
                                  [[1829] * 3, [1829] * 4 + [914], [1829] * 3])
        self.assertTrue(r.verdict["ok"], r.verdict)
        self.assertEqual(len(r.model.faces_only), 3)
        with self.assertRaisesRegex(ValueError, "閉じません"):
            self._solve([(0, 5487), (0, 0), (8230, 0), (8230, 5487)], [[1829] * 3, [1829] * 4 + [914], [1829] * 2])


if __name__ == "__main__":
    unittest.main()
