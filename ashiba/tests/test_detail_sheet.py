"""詳細図のレイアウト（Phase 9-3）: 詰め直し・切り抜き・比率と、部品の detScale."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.detail_sheet import DETAIL_SCALES, clip_regions, detail_layout_name, drawing_ratio, row_origins
from ashiba.elevation_sections import arrange_boxes, clipped_drawing_geometry

HSF = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_detail"


class TestRespace(unittest.TestCase):
    def test_row_does_not_overlap(self):
        # 実機の 1/100 の文字のときの外形（原点からの相対 mm）。間隔4mだと重なっていた
        rel = [(-2230, -2470, 5080, 900), (-1030, -2320, 6600, 1850), (-1030, -5090, 8550, 1500)]
        xs = row_origins(rel, 300000 - 2230, gap_mm=1500)
        self.assertEqual(xs[0], 300000)                       # 1枚目は動かさない
        for i in range(1, len(rel)):
            left = xs[i] + rel[i][0]
            right_prev = xs[i - 1] + rel[i - 1][2]
            self.assertAlmostEqual(left - right_prev, 1500)

    def test_clip_regions_are_absolute_with_margin(self):
        r = clip_regions([(300000, 280000)], [(-878, -1138, 1511, 900)], margin_mm=300)
        self.assertEqual(r[0], (300000 - 878 - 300, 280000 - 1138 - 300, 300000 + 1511 + 300, 280000 + 900 + 300))


class TestRatioAndPosition(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual(drawing_ratio(20), 5)
        self.assertEqual(drawing_ratio(100), 1)
        self.assertEqual(DETAIL_SCALES[0], 20)
        self.assertEqual(detail_layout_name("A棟"), "A棟 足場詳細図")

    def test_position_matches_archicad_at_ratio_5(self):
        # 実機の値（2026-10-18）: 1/20・枠の最小角 (0.024, 0.385958)・範囲の最小角 (298821.5, 278562.5) mm を
        # 中身が枠に入る位置にするには、Tapir の pos = position − 枠×比率 が P − Rmin×k になること
        region = (298821.538, 278562.461, 301810.77, 281200.0)
        clip, pos = clipped_drawing_geometry(region, 20, (24.0, 385.958), source_scale=100)
        tapir_pos_x = pos["x"] - clip[0]["x"] * 5
        tapir_pos_y = pos["y"] - clip[0]["y"] * 5
        self.assertAlmostEqual(tapir_pos_x, 0.024 - 298.821538 / 20)
        self.assertAlmostEqual(tapir_pos_y, 0.385958 - 278.562461 / 20)
        self.assertAlmostEqual(clip[2]["x"] - clip[0]["x"], (301810.77 - 298821.538) / 1000 / 20)

    def test_four_details_fit_a1_at_1_20(self):
        boxes = [(2989, 2638), (3309, 3591), (3778, 3881), (5018, 3338)]
        plan = arrange_boxes(boxes, (841.0, 594.0), scales=(20,), max_scale=20)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.scale, 20)


class TestDetailPartScale(unittest.TestCase):
    def test_detscale_parameter_and_text_size(self):
        root = ET.parse(HSF / "paramlist.xml").getroot()
        names = {e.get("Name"): e.tag for e in root.find("Parameters")}
        self.assertEqual(names.get("detScale"), "Integer")
        d1 = (HSF / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        self.assertIn('define style "anno" "ＭＳ Ｐゴシック", texSiz * dScale / GLOB_SCALE, 1, 0', d1)
        self.assertIn("txtH = texSiz * dScale / 1000", d1)
        d2 = (HSF / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn('"　S=1/" + str(detScale, 1, 0)', d2)


class TestToolbarPlacesDetailSheet(unittest.TestCase):
    def test_wired(self):
        root = Path(__file__).resolve().parents[1]
        tb = (root / "scripts" / "run_from_archicad.py").read_text(encoding="utf-8")
        self.assertIn("place_detail_sheet(", tb)
        rm = (root / "scripts" / "remove_from_archicad.py").read_text(encoding="utf-8")
        self.assertIn("scaffold_layout_names(prefix, faces)", rm)
        from ashiba.elevation_sections import scaffold_layout_names

        names = scaffold_layout_names("X", ["南面"])
        for want in ("X 足場詳細図", "X 足場平面図", "X 足場立面図", "X 足場立面図 2", "X 足場立面図 南面",
                     "X 足場断面図", "X 足場断面図 A-A", "X 足場断面図 B-B 1"):
            self.assertIn(want, names)


if __name__ == "__main__":
    unittest.main()
