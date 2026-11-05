"""足場ラインを垂直・水平に区切る（利用者の指定 2026-10-21「垂直と水平で区切れるように」「クリックした次のところから区切る、3Dで」）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params
from ashiba.segments import CUT_BELOW_FLOOR, horizontal_cut, levels_m, piece_of, spans_m, split_ranges, vertical_cut

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
        "series_id": "nikken_nd1800"}
LINE = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"


def _params():
    r = solve_all(dict(RECT))
    return line_params(r.model, r.model.plan.edges[0])


class TestPiece(unittest.TestCase):
    def test_whole_face_by_default(self):
        p = _params()
        pc = piece_of(p)
        self.assertFalse(pc.split)
        self.assertTrue(pc.base)
        self.assertEqual((pc.sA, pc.sB, pc.lA), (1, len(spans_m(p)), 1))
        self.assertTrue(pc.own_x(-0.61) and pc.own_x(sum(spans_m(p))))   # 出隅・面の終点の支柱も持つ
        self.assertTrue(pc.own_z(0.0) and pc.own_z(99.0))

    def test_range_bounds_are_post_centres_and_below_floors(self):
        p = _params()
        sp, lv = spans_m(p), levels_m(p)
        pc = piece_of({**p, "segSpanA": 3, "segSpanB": 5, "segLevA": 2, "segLevB": 3})
        self.assertAlmostEqual(pc.gxA, sum(sp[:2]))
        self.assertAlmostEqual(pc.gxB, sum(sp[:5]))
        self.assertAlmostEqual(pc.gzA, lv[2] - CUT_BELOW_FLOOR)       # 2層の床の 100 下
        self.assertAlmostEqual(pc.gzB, lv[4] - CUT_BELOW_FLOOR)       # 4層の床の 100 下
        self.assertTrue(pc.own_x(sum(sp[:2])))                        # 始点の支柱は自分
        self.assertFalse(pc.own_x(sum(sp[:5])))                       # 終点の支柱は隣
        self.assertFalse(pc.base)


class TestCutHandles(unittest.TestCase):
    def test_vertical_cut_snaps_to_the_next_post(self):
        p = _params()
        sp = spans_m(p)
        self.assertIsNone(vertical_cut(p))
        self.assertEqual(vertical_cut({**p, "cutAtX": sp[0] + 0.3}), 2)       # 2本目の支柱を過ぎた → 3本目で
        self.assertEqual(vertical_cut({**p, "cutAtX": sp[0]}), 1)             # ちょうど支柱 → そこで
        self.assertIsNone(vertical_cut({**p, "cutAtX": sum(sp) + 1}))         # 終点の先 → 区切らない
        # 区切った部品では部品の始点から測る
        q = {**p, "segSpanA": 4, "cutAtX": 0.1}
        self.assertEqual(vertical_cut(q), 4)

    def test_horizontal_cut_snaps_to_the_next_floor(self):
        p = _params()
        lv = levels_m(p)
        self.assertEqual(horizontal_cut({**p, "cutAtZ": 0.5}), 2)             # 1層の床は根元。次は2層の床
        self.assertEqual(horizontal_cut({**p, "cutAtZ": lv[3] - CUT_BELOW_FLOOR}), 3)
        self.assertIsNone(horizontal_cut({**p, "cutAtZ": 99.0}))

    def test_split_ranges(self):
        p = _params()
        n, nl = len(spans_m(p)), len(levels_m(p)) - 1
        sp = spans_m(p)
        got = split_ranges({**p, "cutAtX": sum(sp[:4]), "cutAtZ": 0.5})
        self.assertEqual([(g["segSpanA"], g["segSpanB"], g["segLevA"], g["segLevB"]) for g in got],
                         [(1, 4, 1, 1), (5, n, 1, 1), (1, 4, 2, nl), (5, n, 2, nl)])
        self.assertTrue(all(g["cutAtX"] == 0 and g["cutAtZ"] == 0 for g in got))
        self.assertEqual(split_ranges(p), [])


class TestGdlUsesTheSameRule(unittest.TestCase):
    def test_master_and_parameter_script(self):
        master = (LINE / "scripts" / "1d.gdl").read_text(encoding="utf-8-sig")
        for line in ("if sA > 1 then gxA = pxA", "if sB < nSpan then gxB = pxB",
                     "if lA > 1 then gzA = lv[lA + 1] - 0.1", "if lB < nLevels then gzB = lv[lB + 2] - 0.1"):
            self.assertIn(line, master)
        vl = (LINE / "scripts" / "vl.gdl").read_text(encoding="utf-8-sig")
        self.assertIn("zc = lv[k + 1] - 0.1", vl)
        self.assertIn("if i >= sA and cxSnap = 0 and xq >= pxA + cutAtX - 0.001 then cxSnap = xq - pxA", vl)
        xml = (LINE / "paramlist.xml").read_text(encoding="utf-8")
        for name in ("segSpanA", "segSpanB", "segLevA", "segLevB"):
            self.assertIn(f'<Integer Name="{name}">', xml)
        for name in ("cutAtX", "cutAtZ"):
            self.assertIn(f'<Length Name="{name}">', xml)

    def test_3d_clips_to_the_piece(self):
        body = (LINE / "scripts" / "3d.gdl").read_text(encoding="utf-8-sig")
        self.assertIn("cutpoly 4, -1000, -1000, gxA, -1000, gxA, 1000, -1000, 1000", body)
        # 切り取りは描き終わり（end の前）で必ず閉じる
        main = body[:body.index("990:")]
        self.assertEqual(main.count("\nend\n") + main.count("\tend\n"), main.count("next ic9\n"))


if __name__ == "__main__":
    unittest.main()
