"""支保工足場（利用者の指定 2026-10-31: しほこう足場を内部足場から作成して 図面化までしてちょ）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.form_drawings import member_rows, plan_page, section_page
from ashiba.interior_stage import _frame, solve_stage
from ashiba.master import load_master
from ashiba.shoring_stage import (BEAM_CLEAR_MM, FORM_DEPTH_MM, merge_system, shoring_cells, stage_item,
                                  system_summary)
from ashiba.slab_form import plan_slab, rect
from ashiba.structural import load_capacities
from test_form_drawings import _plan

OUTLINE = [(0.0, 0.0), (6000.0, 0.0), (6000.0, 5600.0), (0.0, 5600.0)]
BEAM = rect((2700.0, 2800.0), (0.0, 1.0), 2900.0, 362.0, 12.0)          # v の向きに横切る梁（幅 700）


class TestCells(unittest.TestCase):
    def test_beam_across_splits_the_slab(self):
        f = plan_slab(OUTLINE, 180, 2820, 0, [BEAM])
        cells, notes = shoring_cells(f.outer, f.holes)
        self.assertEqual(len(cells), 2)
        a, b = cells
        self.assertAlmostEqual(a.u1, 2700.0 - 362.0 - 12.0 - BEAM_CLEAR_MM, delta=1.0)   # 穴（＋せき板 12）の外へ
        self.assertAlmostEqual(b.u0, 2700.0 + 362.0 + 12.0 + BEAM_CLEAR_MM, delta=1.0)
        self.assertEqual((a.v0, a.v1), (0.0, 5600.0))
        self.assertEqual(notes, [])

    def test_column_inside_is_reported(self):
        col = rect((3000.0, 2800.0), (1.0, 0.0), 300.0, 300.0, 12.0)
        f = plan_slab(OUTLINE, 180, 2820, 0, [col])
        cells, notes = shoring_cells(f.outer, f.holes)
        self.assertEqual(len(cells), 1)
        self.assertTrue(any("柱・壁" in n for n in notes))


class TestFrame(unittest.TestCase):
    def test_prefer_u_follows_the_obiki(self):
        """内部足場の長手は長い辺だが、支保工足場は大引の向き（スラブの u）にそろえる."""
        corners = [(0, 0), (1800, 0), (1800, 4800), (0, 4800)]
        self.assertAlmostEqual(_frame(corners)[1][1], 1.0)                 # 長い辺（y）が u
        p0, u, v, la, lb = _frame(corners, (1.0, 0.0))
        self.assertAlmostEqual(u[0], 1.0)
        self.assertEqual((la, lb), (1800.0, 4800.0))


class TestStage(unittest.TestCase):
    def setUp(self):
        self.master = load_master("nikken_nd1800")
        self.caps = load_capacities("nikken_nd1800")
        f = plan_slab(OUTLINE, 180, 2820, 0, [BEAM])
        cells, _n = shoring_cells(f.outer, f.holes)
        W = lambda p: (p[0], p[1])
        self.item = stage_item("S0 支保工1", cells[0], W, (1.0, 0.0), 0.0, 0.0, 2820.0, 180.0, "片方向つなぎ材")
        self.st = solve_stage(self.item, self.master, self.caps)

    def test_shoring_stage_fits_under_the_obiki(self):
        st = self.st
        self.assertEqual(st.use, "支保工")
        self.assertAlmostEqual(st.u[0], 1.0)                                # 大引の向き
        self.assertEqual(st.top_mm + st.uhead_ext_mm, int(2820 - FORM_DEPTH_MM))   # 支柱の天端＋Uジャッキ＝大引の下
        self.assertTrue(st.ok, [(c.item, c.message) for c in st.checks if c.status == "NG"])
        self.assertLessEqual(max(st.spans_v), 1219)

    def test_summary_and_merge(self):
        sy = system_summary(self.st, self.master, self.caps, lambda p: (p[0], p[1]))
        self.assertEqual(len(sy["posts"]), (len(self.st.spans_u) + 1) * (len(self.st.spans_v) + 1))
        self.assertEqual(len(sy["obiki"]), len(self.st.spans_v) + 1)
        self.assertGreater(sy["allow_kn"], sy["post_kn"])
        slab = merge_system(_plan()["slabs"][0], [sy])
        self.assertEqual((slab["sills"], slab["braces"], slab["ties"]), ([], [], []))
        self.assertEqual(slab["posts"], sy["posts"])
        plan = _plan()
        plan["slabs"][0] = slab
        _n, _s, body = plan_page(plan)
        self.assertIn("支保工足場の支柱", body)
        self.assertIn('class="ledger"', body)
        _n, _s, sec = section_page(plan)
        for word in ("ジャッキベース（繰出し", "大引受けジャッキ（繰出し", "布材（根がらみ・水平つなぎ", "作業床（全面"):
            self.assertIn(word, sec)
        rows = dict((a, b) for a, b, _c in member_rows(plan))
        self.assertIn("支保工足場（システム支保工）", rows)
        self.assertIn("つなぎ方 片方向つなぎ材", rows["支保工足場（システム支保工）"])


if __name__ == "__main__":
    unittest.main()
