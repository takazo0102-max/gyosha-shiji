"""型枠支保工計画図（利用者の指定 2026-10-31: 型枠しほこう計画図作成できる？ → 伏図・断面図と詳細図・構造計算書・計画届）."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.form_drawings import (NOTICE_H_MM, assembly_rows, build_html, build_xlsx, calc_lines, load_rows, member_rows,
                                  notice_info, plan_page, section_cuts, section_page)


def _plan(floor=0.0, bottom=2820.0):
    return {"project": "試し", "slabs": [{
        "name": "S0", "origin": [0.0, 0.0], "ang": 0.0, "outer": [[0, 0], [6000, 0], [6000, 5600], [0, 5600]],
        "holes": [[[2650, -50], [3350, -50], [3350, 5650], [2650, 5650]]], "thick": 180.0, "top": bottom + 180.0,
        "bottom": bottom, "floor": floor, "floor_found": True, "su": 1200.0, "sv": 900.0,
        "posts": [[150.0, 150.0], [1350.0, 150.0], [150.0, 1050.0]], "obiki": [[50.0, 2600.0, 150.0], [50.0, 2600.0, 1050.0]],
        "neda_n": 10, "neda": [[50.0, 5550.0, 300.0], [50.0, 5550.0, 600.0]], "negarami": 200.0,
        "sills": [[0.0, 1500.0, 150.0]], "ties": [], "post_h": 2623.0, "post_kn": 6.7, "q": 6.22,
        "lines": ["荷重 6.22 kN/m²", "パイプサポート 1本 6.7／15.0 kN（目安） 可"]}],
        "beams": [], "columns": [], "walls": [], "rows": [["S0", "パイプサポート", 3, ""]]}


class TestFormDrawings(unittest.TestCase):
    def test_pages_and_calc(self):
        html = build_html(_plan())
        self.assertEqual(html.count('class="page"'), 6)                     # 伏図・断面図・詳細図・計算書・部材等明細書・計画届
        for word in ("型枠支保工 伏図", "型枠支保工 断面図", "型枠支保工 詳細図", "構造計算書", "部材等明細書", "計画届の要否",
                     "様式第20号", "安衛則 242条"):
            self.assertIn(word, html)
        heads = [h for h, _b in calc_lines(_plan())]
        self.assertEqual(heads[:2], ["前提", "スラブ S0（厚さ 180）"])

    def test_plan_detail(self):
        """平面の詳細度（利用者の指定 2026-10-31: 平面の詳細度あげて）: 根太・大引の帯・割付ピッチ・引出し・切る位置."""
        _n, scale, body = plan_page(_plan())
        self.assertEqual(scale, "1/50")
        self.assertEqual(body.count('class="neda"'), 2)                    # 根太（大引に直角）
        self.assertEqual(body.count('class="obk"'), 2)                     # 大引（帯）
        for word in ("スラブ（S0）下 サポート割付ピッチ", "大引割付ピッチ", "根太：角パイプ", "大引：杉 90×90", "敷き桟木",
                     "S0（t180）"):
            self.assertIn(word, body)
        self.assertEqual(body.count('class="mark"'), 4)                    # a・b の記号（両端）
        self.assertIn(">1200<", body)                                     # 支柱の間隔 150→1350

    def test_sections(self):
        """断面も（同日）: a－a は大引の向き、b－b は大引に直角。根がらみ・敷き桟木・寸法・高さ."""
        self.assertEqual(section_cuts(_plan()["slabs"][0]), (1050.0, 1350.0))     # 支柱の行・列のまん中
        name, scale, body = section_page(_plan())
        self.assertEqual(name, "型枠支保工 断面図")
        for word in ("a－a 断面図", "b－b 断面図", "根がらみ：単管", "敷き桟木 45×60", "パイプサポート 60S（長さ 2623）",
                     "▽床 FL+0", ">2820<", ">180<", ">2623<"):
            self.assertIn(word, body)

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
            self.assertIn("xl/worksheets/sheet5.xml", names)               # 計算書・材料・支柱・部材等明細書・計画届の要否

    def test_member_sheet(self):
        """部材等明細書（計画届作成の手引 第6版 p.147 の例の欄）."""
        kinds = [r[0] for r in member_rows(_plan())]
        self.assertEqual(kinds[:4], ["せき板", "角パイプ", "木材（角材）", "パイプサポート"])
        self.assertIn(("水平つなぎ", "無（支柱の高さ 3.4m 以下。メーカーの表の連係なしで受ける）", "―"), member_rows(_plan()))
        self.assertNotIn("フォームタイ", kinds)                             # 壁・柱・梁が無ければ載せない
        (row,) = load_rows(_plan())
        self.assertEqual(row[0], "スラブ S0（厚さ 180）")
        self.assertAlmostEqual(row[2], 24.0 * 180 + 400.0)                  # 固定荷重 N/m²
        self.assertAlmostEqual(row[4], row[2] + 1500.0)
        self.assertAlmostEqual(row[5], 6700.0)                              # 支柱1本当り N
        items = dict((a, c) for a, _b, c in assembly_rows(_plan()))
        self.assertEqual(items["脚部の滑動・沈下防止措置"], "有")
        self.assertEqual(items["水平つなぎ・筋かい・控え等の措置"], "無")
        tall = _plan()
        tall["slabs"][0]["ties"] = [2000.0]
        self.assertEqual(dict((a, c) for a, _b, c in assembly_rows(tall))["水平つなぎ・筋かい・控え等の措置"], "有")
        self.assertIn("水平つなぎ（2方向・2m 以内ごと）", dict((a, c) for a, _b, c in member_rows(tall))["単管"])


if __name__ == "__main__":
    unittest.main()
