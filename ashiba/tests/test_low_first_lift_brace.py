"""根がらみ〜1段目の床が低い層にはブレスを掛けず、1つ上の層へ入れる（利用者の指摘 2026-10-24: 前も言ったけど1段目に変な
ブレス）。3D・平面（斜材の本数）・立面が同じ層の印 brOn を使う."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

GDL = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"


class TestLowFirstLiftBrace(unittest.TestCase):
    def test_brace_layers_skip_a_low_lift(self):
        d1 = (GDL / "1d.gdl").read_text(encoding="utf-8")
        blk = d1[d1.index("! 斜材を入れる層 brOn[il]"):]
        blk = blk[:blk.index("next il\n", blk.index("brOn[il + 1] = 1")) + 8]
        self.assertIn("if lv[il + 1] - lv[il] > 0.999 then", blk)
        self.assertIn("if il + 1 <= nLv - 1 then brOn[il + 1] = 1", blk)

    def test_every_view_uses_the_same_layers(self):
        for name in ("1d.gdl", "2d.gdl", "3d.gdl"):
            src = (GDL / name).read_text(encoding="utf-8")
            self.assertIn("brOn[il] = 1", src, name)
            self.assertNotIn("il - 1 - bEvL * int((il - 1) / bEvL) = 0 and", src, name)


if __name__ == "__main__":
    unittest.main()
