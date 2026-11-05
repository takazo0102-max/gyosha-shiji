"""くさび1点で部材を足す（GLOOBE 2026 のくさび受け参照入力。利用者の指定 2026-11-03「進めて」）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.master import SERIES_CONST, load_master
from ashiba.wedge_point import from_line, member_params, order_rows, plan, report, snap_z


class TestWedgePoint(unittest.TestCase):
    def setUp(self):
        self.m = load_master("nikken_nd1800")
        self.pitch = SERIES_CONST["nikken_nd1800"]["koma_pitch"]

    def test_length_and_height_snap(self):
        """線の長さはいちばん近い規格（日建 ND の 1829/1524/1219/914/610）、高さはコマ 450 にそろえる。向きは線のとおり（梁間の腕木も）."""
        pc = plan([from_line("a", "布材・腕木", (0, 0), (0, 930), 1750)], self.m, self.pitch)[0]
        self.assertEqual((pc.part.model_no, pc.z_mm, pc.ang), ("NDT09", 1800.0, 90.0))
        self.assertEqual(snap_z(2000, 450), 1800.0)
        far = plan([from_line("b", "布材・腕木", (0, 0), (2400, 0), 1800)], self.m, self.pitch)[0]
        self.assertTrue(far.notes)                                         # 規格の長さと 571 違う
        self.assertFalse([p for p in self.m.by_category("布材") if p.model_no.endswith("S") and p is far.part])

    def test_params_and_order(self):
        rail = plan([from_line("c", "先行手すり", (0, 0), (1829, 0), 1800)], self.m, self.pitch)[0]
        deck = plan([from_line("d", "踏板", (0, 0), (1524, 0), 1800)], self.m, self.pitch)[0]
        self.assertEqual(member_params(rail)["kind"], 5)
        self.assertAlmostEqual(member_params(rail)["memH"], 0.9)
        self.assertEqual((member_params(deck)["kind"], deck.part.model_no), (3, "NDN5"))   # 幅 500 の品
        rows = order_rows([rail, deck, rail])
        self.assertIn(("先行手摺 NDX18（1829）", 2, 6.25), rows)
        self.assertIn("## 発注表", report([rail, deck], "nikken_nd1800"))


if __name__ == "__main__":
    unittest.main()
