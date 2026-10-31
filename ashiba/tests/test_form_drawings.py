"""型枠支保工計画図（利用者の指定 2026-10-31: 型枠しほこう計画図作成できる？ → 伏図・断面図と詳細図・構造計算書・計画届）."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.form_drawings import NOTICE_H_MM, build_html, build_xlsx, calc_lines, notice_info


def _plan(floor=0.0, bottom=2820.0):
    return {"project": "試し", "slabs": [{
        "name": "S0", "origin": [0.0, 0.0], "ang": 0.0, "outer": [[0, 0], [6000, 0], [6000, 5600], [0, 5600]],
        "holes": [[[2650, -50], [3350, -50], [3350, 5650], [2650, 5650]]], "thick": 180.0, "top": bottom + 180.0,
        "bottom": bottom, "floor": floor, "floor_found": True, "su": 1200.0, "sv": 900.0,
        "posts": [[150.0, 150.0], [1350.0, 150.0], [150.0, 1050.0]], "obiki": [[50.0, 2600.0, 150.0]], "neda_n": 10,
        "sills": [[0.0, 1500.0, 150.0]], "ties": [], "post_h": 2623.0, "post_kn": 6.7, "q": 6.22,
        "lines": ["荷重 6.22 kN/m²", "パイプサポート 1本 6.7／15.0 kN（目安） 可"]}],
        "beams": [], "columns": [], "walls": [], "rows": [["S0", "パイプサポート", 3, ""]]}


class TestFormDrawings(unittest.TestCase):
    def test_pages_and_calc(self):
        html = build_html(_plan())
        self.assertEqual(html.count('class="page"'), 4)                     # 伏図・断面詳細・計算書・計画届
        for word in ("型枠支保工 伏図", "断面図・詳細図", "構造計算書", "計画届の要否", "様式第20号", "安衛則 242条"):
            self.assertIn(word, html)
        heads = [h for h, _b in calc_lines(_plan())]
        self.assertEqual(heads[:2], ["前提", "スラブ S0（厚さ 180）"])

    def test_notice_needed_from_3500(self):
        """支柱の高さ 3.5m 以上は計画届（安衛則 88条・別表第7）."""
        self.assertFalse(notice_info(_plan())["required"])
        ni = notice_info(_plan(bottom=NOTICE_H_MM))
        self.assertTrue(ni["required"])
        self.assertEqual(ni["where"], "スラブ S0")
        self.assertIn("計画届が要る", build_html(_plan(bottom=4000.0)))

    def test_xlsx(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.xlsx"
            build_xlsx(_plan(), p)
            names = zipfile.ZipFile(p).namelist()
            self.assertIn("xl/worksheets/sheet4.xml", names)               # 計算書・材料・支柱・計画届の要否


if __name__ == "__main__":
    unittest.main()
