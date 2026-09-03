"""立面図の特記（文字）が足場の形式に合っているか（GDLソースの検査）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
GDL_2D = ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl"


class TestElevationNotesFollowScaffoldForm(unittest.TestCase):
    def test_single_row_scaffold_does_not_describe_two_rows(self):
        """一側足場（nRows=1）に本足場の「内側／外側」の注記を出さない.

        実機の立面で、建地1列なのに「内側: ブレース＋幅木」と書かれていた。
        """
        body = GDL_2D.read_text(encoding="utf-8")
        i = body.index('"内側: ブレース＋幅木"')
        # 内側の注記は nRows の分岐の中にある
        head = body[max(0, i - 400):i]
        self.assertIn("if nRows = 1 then", head)
        self.assertIn("一側足場: 建地1列", head)
        self.assertIn("ブラケット受け", head)


if __name__ == "__main__":
    unittest.main()
