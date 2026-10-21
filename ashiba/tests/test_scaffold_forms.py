"""ブラケット足場（単管・支柱）と単管抱き足場（利用者の指定 2026-10-21）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all

BASE = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000,
        "clearance_space_mm": 900}


def _qty(r, cat):
    return {ln.part.model_no: ln.qty for ln in r.quantity.lines if ln.part and ln.part.category == cat}


def _check(r, cid):
    return next(c for c in r.checks if c.check_id == cid)


class TestTubeSeries(unittest.TestCase):
    def test_tube_full_scaffold_counts_clamps_and_joints(self):
        r = solve_all({**BASE, "series_id": "tankan"})
        m = r.model
        self.assertTrue(m.master.is_tube)
        self.assertEqual(m.master.system_name, "単管足場")
        self.assertTrue(all(s <= 1800 for e in m.plan.edges for s in e.spans))   # 建地間隔 1.85m 以下
        ledgers = sum(_qty(r, "布材").values())
        braces = sum(_qty(r, "筋交").values())
        clamps = _qty(r, "クランプ")
        self.assertEqual(clamps["ARC1"], 2 * ledgers)
        self.assertEqual(clamps["ARC2"], 2 * braces)
        self.assertGreater(_qty(r, "ジョイント").get("PCJ", 0), 0)
        self.assertEqual(m.guard_rail_height_mm, 900)
        self.assertEqual(m.midrail_height_mm, 450)
        self.assertEqual(_check(r, 3).status, "OK")
        # 天端は手すり分の上（単管は1m刻みなので要求より高くてよい）
        e = m.elevation
        self.assertGreaterEqual(e.jack_extension + sum(e.posts), 6000 + 900)


class TestBracketScaffold(unittest.TestCase):
    def test_tube_bracket_uses_the_tube_series_with_two_planks(self):
        r = solve_all({**BASE, "series_id": "nikken_nd1800", "scaffold_form": "ブラケット足場", "bracket_post": "単管"})
        m = r.model
        self.assertEqual(m.master.series_id, "tankan")                  # 単管の系列で組む
        self.assertEqual(m.config.form_label, "ブラケット足場（単管）")
        self.assertEqual(m.deck_widths_in_use, (240, 240))               # 足場板2枚で床幅40cm以上
        self.assertIn("TB-60", _qty(r, "ブラケット"))
        self.assertEqual(_check(r, 2).status, "OK")

    def test_post_bracket_keeps_the_series(self):
        r = solve_all({**BASE, "series_id": "shinwa_A", "scaffold_form": "ブラケット足場", "bracket_post": "支柱"})
        m = r.model
        self.assertEqual(m.master.series_id, "shinwa_A")
        self.assertEqual(m.config.scaffold_form, "一側足場")
        self.assertEqual(m.config.form_label, "ブラケット足場（支柱）")
        self.assertTrue(_qty(r, "ブラケット"))


class TestHugScaffold(unittest.TestCase):
    def test_hug_has_two_ledgers_per_level_and_no_brackets(self):
        r = solve_all({**BASE, "scaffold_form": "単管抱き足場"})
        m = r.model
        self.assertEqual(m.master.series_id, "tankan")
        self.assertTrue(m.config.is_hug)
        self.assertEqual(m.config.form_label, "単管抱き足場")
        self.assertEqual(m.deck_widths_in_use, (240,))
        self.assertFalse(_qty(r, "ブラケット"))
        c2 = _check(r, 2)
        self.assertEqual(c2.status, "WARN")                            # 一側足場は563条の適用外。40cm未満は注意
        self.assertIn("40cm未満", c2.message)

    def test_hug_ledgers_more_than_bracket(self):
        hug = solve_all({**BASE, "scaffold_form": "単管抱き足場"})
        brk = solve_all({**BASE, "scaffold_form": "ブラケット足場", "bracket_post": "単管"})
        span = sum(len(e.spans) for e in hug.model.plan.edges)
        n = hug.model.elevation.n_levels
        # 抱き足場は各層の床の高さに建地を両側から抱く布が2本（ブラケット足場は床の高さに布が無い）
        self.assertEqual(sum(_qty(hug, "布材").values()) - sum(_qty(brk, "布材").values()), 2 * span * n)

    def test_unknown_form_is_rejected(self):
        from ashiba.cli import InputError
        with self.assertRaises(Exception):
            solve_all({**BASE, "scaffold_form": "吊り足場"})
        with self.assertRaises(Exception):
            solve_all({**BASE, "scaffold_form": "ブラケット足場", "bracket_post": "枠"})
        self.assertTrue(InputError)


if __name__ == "__main__":
    unittest.main()
