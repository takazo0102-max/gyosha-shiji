"""構造計算書の下書き表示と確認欄（Phase 12-2）."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, write_outputs


def _sheets(r):
    with tempfile.TemporaryDirectory() as d:
        write_outputs(r, Path(d))
        z = zipfile.ZipFile(next(Path(d).glob("*_設置届一式.xlsx")))
        wbx = z.read("xl/workbook.xml").decode("utf-8")
        names = [n.split('"')[0] for n in wbx.split('<sheet name="')[1:]]
        return {n: z.read(f"xl/worksheets/sheet{i}.xml").decode("utf-8") for i, n in enumerate(names, start=1)}


class TestCalcSheetsAreDrafts(unittest.TestCase):
    def test_every_calc_sheet_has_banner_and_confirm_block(self):
        r = solve_all({"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                       "eaves_height_mm": 15400, "building_height_mm": 16000,
                       "openings": [{"face": "南面", "start_mm": 3600, "beam_span_mm": 3600, "level": 2}]})
        sheets = _sheets(r)
        calc = [n for n in sheets if n.startswith("計算書")]
        self.assertGreaterEqual(len(calc), 4)                      # 風・壁つなぎ・建地・梁枠
        for n in calc:
            x = sheets[n]
            self.assertIn("下書き（有資格者の確認前提）", x, n)
            self.assertIn("確認（有資格者が記入。ツールは記入しない）", x, n)
            self.assertIn("確認者 氏名", x, n)
            self.assertIn("【記入】", x, n)

    def test_unverified_capacities_are_named_in_the_confirm_block(self):
        r = solve_all({"series_id": "shinwa_A", "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                       "eaves_height_mm": 15400, "building_height_mm": 16000})
        from ashiba.notification import _unverified_labels

        labels = _unverified_labels(r.structural)
        if not labels:
            self.skipTest("未確認の耐力値を使っていない")
        x = _sheets(r)["計算書3_建地圧縮"]
        self.assertIn("未確認の耐力値を使っています", x)


if __name__ == "__main__":
    unittest.main()


class TestFormDescribesAutoBrackets(unittest.TestCase):
    def test_auto_inner_brackets_are_explained(self):
        r = solve_all({"module": "inch", "corner_steps": False, "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                       "eaves_height_mm": 15400, "building_height_mm": 16000})
        x = _sheets(r)["様式第20号(下書き)"]
        self.assertIn("うち4区間は離れ350超の面に躯体側へ踏板を足して隙間を詰めるもの（自動）", x)
