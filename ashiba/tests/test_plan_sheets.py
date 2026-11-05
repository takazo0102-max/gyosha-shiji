"""根切り・山留計画図と総合仮設計画図（利用者の指定 2026-11-02: 各図面を参考にして、図面かボタンを追加してちょ。
施工図の手引き 建築施工図研究会 平成16年の第1章 仮設計画図にならう）."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.form_layout import svg_shapes
from ashiba.negiri_sheets import build_html, crossings, default_cuts, negiri_of, page_list, profile, spans_inside
from ashiba.sogo_sheet import panel_svg, road_limit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

FIG = {"name": "試験", "gl": 0.0, "slope": None,
       "zones": [{"name": "耐圧盤", "pts": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "bottom": -1200, "top": -800},
                 {"name": "基礎F1", "pts": [[5000, 3000], [7000, 3000], [7000, 5000], [5000, 5000]], "bottom": -2000, "top": -800}],
       "yamadome": [[-1500, -1500], [13500, -1500], [13500, 9500], [-1500, 9500]]}


class TestNegiriSheets(unittest.TestCase):
    def test_pages(self):
        """平面図・断面図・数量と判定と確認の3枚。レイアウトの変換（svg_shapes）で読める."""
        n = negiri_of(FIG)
        pages = page_list(n)
        self.assertEqual([p[0] for p in pages], ["根切り 平面図", "根切り 断面図", "根切り 数量・判定・確認"])
        self.assertEqual(pages[0][1], "1/100")
        for _name, _sc, body in pages:
            self.assertTrue(svg_shapes(body))
        texts = " ".join(s.text for s in svg_shapes(pages[0][2]) if s.kind == "text")
        self.assertIn("床付け GL-2,110", texts)
        self.assertIn("山留め", texts)
        html = build_html(n, "試験工事")
        self.assertIn("根切り 3/3", html)                                   # 表題欄の図番
        self.assertIn("事前に確かめる項目", html)

    def test_cuts_and_profile(self):
        """既定の断面は深い基礎の真ん中を通る横・縦。断面の掘削面は山留めの所で GL から一般の床付け、基礎で深い床付けへ."""
        n = negiri_of(FIG)
        (la, a, b), (lb, c, d) = default_cuts(n)
        self.assertEqual((la, lb), ("A", "B"))
        self.assertAlmostEqual(a[1], 4000.0)
        self.assertAlmostEqual(c[0], 6000.0)
        zs = [z for _t, z in profile(n, a, b)]
        self.assertEqual((max(zs), min(zs)), (0.0, -2110.0))
        self.assertIn(-1310.0, zs)
        self.assertEqual(len(crossings(a, b, n.yamadome)), 2)
        (t0, t1), = spans_inside(a, b, FIG["zones"][1]["pts"])
        self.assertAlmostEqual(t1 - t0, 2000.0)

    def test_road_on_sheets(self):
        """道路境界線があれば、平面に道路境界線と沿道区域、横切る断面に道路境界と 45° の影響斜線、条件の欄に沿道掘削."""
        n = negiri_of({**FIG, "yamadome": [], "road": [[[-5000, -1000], [20000, -1000]]], "road_width": 8000})
        pages = page_list(n)
        plan = " ".join(s.text for s in svg_shapes(pages[0][2]) if s.kind == "text")
        sec = " ".join(s.text for s in svg_shapes(pages[1][2]) if s.kind == "text")
        self.assertIn("沿道区域 3m", plan)
        self.assertIn("道路境界線", plan)
        self.assertIn("45° 影響斜線", sec)                                     # B－B（縦）が道路を横切る
        self.assertIn("沿道掘削", plan)
        self.assertIn("バックホウ 0.1m³（最大掘削深さ 3.23m）", sec)          # 最初の断面に最終段階の掘削機とダンプ
        self.assertIn("ダンプ 4t", sec)

    def test_sheet_from_record(self):
        """根切り図の控え（根切り_<名前>_図.json）から計画図を作る（Archicad が無くても PDF の元の HTML は書く）."""
        import negiri_run as N

        tmp = Path(tempfile.mkdtemp())
        (tmp / "根切り_試験_図.json").write_text(json.dumps(FIG, ensure_ascii=False), encoding="utf-8")

        class R:
            OUT_DIR = tmp
            SPEC = {"project_name": "試験工事"}

            @staticmethod
            def load_spec_override():
                return {}

        class C:
            def get_selected_elements(self):
                return []

            def get_details(self, sel):
                return []

            def tapir(self, *a, **k):
                raise RuntimeError("Archicad なし")

        self.assertEqual(N.sheet(C(), R, "試験"), 0)
        self.assertTrue((tmp / "根切り・山留計画図_試験.html").exists())


class TestSogoSheet(unittest.TestCase):
    def test_road_limit(self):
        """東京都北多摩北部建設事務所の許可基準: 歩道は 1m 以下かつ有効幅員の 1/3、残り 1.5m。車道は 1m 以下かつ 1/8."""
        self.assertEqual(road_limit(3000).max_out_mm, 1000.0)
        self.assertEqual(road_limit(2000).max_out_mm, 500.0)                  # 1/3 だと残りが 1.33m → 1.5m 残す
        self.assertEqual(road_limit(6000, sidewalk=False).max_out_mm, 750.0)
        self.assertEqual(road_limit(12000, sidewalk=False).max_out_mm, 1000.0)
        self.assertEqual(road_limit(4000, guard_inner_mm=2400).max_out_mm, 800.0)
        self.assertIn("4.5m", road_limit(6000, sidewalk=False).notes[0])

    def test_panel(self):
        body, y = panel_svg(0.0, 0.0, 175.0, road_limit(3000), "歩道 3.0m")
        texts = " ".join(s.text for s in svg_shapes(body) if s.kind == "text")
        for word in ("凡例（線種）", "道路占用の許可基準", "主な届出", "事前に確かめる項目", "出幅の上限 1,000mm"):
            self.assertIn(word, texts)
        self.assertLess(y, 250.0)                                           # A3 の高さに収まる

    def test_panel_scale(self):
        """右の欄は A3 で組み、A1 なら 2 倍に（文字 2.1mm×0.8 が小さかった）。欄が用紙の高さに収まるまで小さくする."""
        import sogo_run as S

        self.assertEqual(S.panel_scale((420, 297), (10, 10, 10, 10)), 1.0)
        k = S.panel_scale((841, 594), (10, 10, 10, 10))
        self.assertAlmostEqual(k, 2.0, delta=0.01)
        self.assertLessEqual(panel_svg(0.0, 0.0, 175.0 / k)[1] * k, 594 - 20 - 40)

    def test_record_guids_and_region(self):
        import sogo_run as S

        tmp = Path(tempfile.mkdtemp())
        g1, g2 = "744095DB-EBC6-FD4D-A13A-A9790EB6AEBE", "CA4817F1-9A3E-A74A-9862-23462D78440D"
        (tmp / "構台.json").write_text(json.dumps({g1: g2}), encoding="utf-8")
        (tmp / "仮囲い.json").write_text(json.dumps({"線": {"guids": [g1, "x"]}}), encoding="utf-8")
        self.assertEqual(S.record_guids(tmp), [g1, g2])                     # 値の GUID だけ（構台の鍵は線。控えの順・重ねない）
        self.assertEqual(S.region_of([(0, 0), (10000, 5000)], [(-2000, 0, 1000, 8000)], 1000.0), (-3000, -1000, 11000, 9000))
        self.assertIsNone(S.region_of([], []))


if __name__ == "__main__":
    unittest.main()
