"""型枠支保工計画図をレイアウトに描く（利用者の指定 2026-10-31: Archicadのレイアウトにも置いて）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.form_drawings import page_list
from ashiba.form_layout import (fit_area, layout_data, layout_names, line_type_indexes, scale_note, shapes_bbox,
                                solid_fill_id, svg_shapes)
from test_form_drawings import _plan

BLACK = [{"index": 1, "color": {"red": 0, "green": 0, "blue": 0}}, {"index": 5, "color": {"red": 0, "green": 0.3, "blue": 0.7}},
         {"index": 9, "color": {"red": 0.6, "green": 0.6, "blue": 0.6}}]


class TestSvgShapes(unittest.TestCase):
    def test_classes_dash_and_fill(self):
        sh = svg_shapes('<rect x="10" y="20" width="30" height="5" class="struct"/>'
                        '<line x1="0" y1="0" x2="10" y2="0" class="beam"/>')
        rect, line = sh
        self.assertTrue(rect.closed)
        self.assertEqual(rect.pts[2], (40.0, 25.0))
        self.assertAlmostEqual(rect.fill[0], 0xbb / 255.0)                  # .struct の塗り
        self.assertEqual(line.dash, "2 1")                                    # .beam の破線
        self.assertAlmostEqual(line.width, 0.25)

    def test_clip_and_transform(self):
        body = ('<clipPath id="pv"><rect x="0" y="0" width="10" height="10"/></clipPath><g clip-path="url(#pv)">'
                '<line x1="-5" y1="5" x2="20" y2="5" class="thin"/><text x="50" y="5" class="t">外</text></g>'
                '<g transform="translate(100,50) rotate(90)"><line x1="0" y1="0" x2="6" y2="0" class="lead"/></g>')
        sh = svg_shapes(body)
        self.assertEqual(sh[0].pts, [(0.0, 5.0), (10.0, 5.0)])               # 切り抜きの外は切る
        self.assertNotIn("外", [s.text for s in sh])                         # 外の文字は落とす
        a, b = sh[1].pts
        self.assertAlmostEqual(a[0], 100.0)
        self.assertAlmostEqual(b[1], 56.0)                                   # 90° 回して下向き

    def test_rotated_text(self):
        (t,) = svg_shapes('<text x="5" y="5" class="dimt" text-anchor="middle" transform="rotate(-90 5 5)">900</text>')
        self.assertAlmostEqual(t.angle, -90.0)
        self.assertEqual((t.anchor, t.text, t.size), ("middle", "900", 2.1))


class TestLayoutData(unittest.TestCase):
    def test_paper_metres_and_pens(self):
        sh = svg_shapes('<line x1="10" y1="10" x2="110" y2="10" class="dim"/>'
                        '<rect x="10" y="20" width="30" height="5" class="struct"/><text x="10" y="40" class="h2">見出し</text>')
        fit = (1.0, 0.0, 0.0)
        d = layout_data(sh, (420.0, 297.0), fit, BLACK, {}, "SOLID")
        p = d["polylines"][0]
        self.assertEqual(p["coordinates"][0], {"x": 0.01, "y": 0.287})       # 用紙の m（左下が原点・y は上）
        self.assertEqual(p["linePenIndex"], 5)                               # 寸法の青に近いペン
        self.assertEqual(d["hatches"][0]["fillPenIndex"], 9)                 # 壁・柱の灰色
        t = d["texts"][0]
        self.assertEqual((t["height"], t["style"]["anchor"], t["style"]["bold"]), (3.2, "LeftBottom", True))

    def test_white_fill_is_not_hatched(self):
        sh = svg_shapes('<circle cx="10" cy="10" r="1" class="ps"/>')
        d = layout_data(sh, (420.0, 297.0), (1.0, 0.0, 0.0), BLACK, {}, "SOLID")
        self.assertEqual(d["hatches"], [])
        self.assertEqual(len(d["polylines"][0]["coordinates"]), 17)          # 16 角形を閉じる

    def test_text_angle_is_counter_clockwise(self):
        (t,) = svg_shapes('<text x="5" y="5" class="t" transform="rotate(-90 5 5)">上向き</text>')
        d = layout_data([t], (420.0, 297.0), (1.0, 0.0, 0.0), BLACK, {}, None)
        self.assertAlmostEqual(d["texts"][0]["angle"], math.pi / 2)


class TestFit(unittest.TestCase):
    def test_keeps_full_size_when_it_fits(self):
        s, ox, oy = fit_area((420.0, 297.0), (14.0, 14.0, 14.0, 14.0), 28.0, (60.0, 24.0, 402.0, 206.0))
        self.assertEqual(s, 1.0)
        self.assertAlmostEqual(oy + 24.0, 18.0)                             # 上の余白 14＋4 に寄せる

    def test_shrinks_above_title_strip(self):
        s, ox, oy = fit_area((420.0, 297.0), (14.0, 14.0, 14.0, 14.0), 28.0, (15.0, 28.0, 238.0, 278.0))
        self.assertLess(s, 1.0)
        self.assertLessEqual(oy + 278.0 * s, 297.0 - 14.0 - 28.0 - 4.0 + 1e-6)

    def test_scale_note(self):
        self.assertIsNone(scale_note("型枠支保工 構造計算書", "―", 0.9))
        self.assertEqual(scale_note("型枠支保工 伏図", "1/50", 1.0), "型枠支保工 伏図　縮尺 1/50（A3）")
        self.assertIn("93% に縮小", scale_note("型枠支保工 断面図・詳細図", "図示", 0.931))


class TestAttributes(unittest.TestCase):
    def test_line_types_and_fill(self):
        lts = line_type_indexes([{"index": 1, "name": "実線"}, {"index": 4, "name": "破線"}, {"index": 6, "name": "一点鎖線"}])
        self.assertEqual(lts, {"4 1 0.6 1": 6, "2 1": 4, "1.5 0.8": 4})
        fills = [{"name": "50 %", "attributeId": {"guid": "A"}}, {"name": "100 %", "attributeId": {"guid": "B"}}]
        self.assertEqual(solid_fill_id(fills), "B")

    def test_pages_of_the_plan(self):
        pages = page_list(_plan())
        names = layout_names(pages)
        self.assertEqual(names[0], "型枠支保工 1 伏図")
        self.assertEqual(names[-1], f"型枠支保工 {len(pages)} 計画届の要否")
        for _n, _sc, body in pages:
            sh = svg_shapes(body)
            self.assertTrue(sh)
            x0, y0, x1, y1 = shapes_bbox(sh)
            self.assertLess(x0, x1)


if __name__ == "__main__":
    unittest.main()
