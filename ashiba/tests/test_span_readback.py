"""ホットスポット編集したスパンの読み戻し（span_readback）と部品側の吸着."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.span_readback import match_edge, merge_overrides, overrides_from_readback, spans_from_params

PLAN = [
    {"edge_index": 0, "face": "南面", "spans": [1800, 1800, 1800, 600], "placement": {"x_mm": 100.0, "y_mm": -300.0}},
    {"edge_index": 1, "face": "東面", "spans": [1800, 1800], "placement": {"x_mm": 6400.0, "y_mm": -300.0}},
]


class TestSpansFromParams(unittest.TestCase):
    def test_joins_both_chunks_and_tolerates_spaces(self):
        self.assertEqual(spans_from_params({"spanList": "1800, 1500", "spanList2": "900"}), [1800, 1500, 900])
        self.assertEqual(spans_from_params({"spanList": ""}), [])


class TestOverrides(unittest.TestCase):
    def test_only_changed_faces_become_overrides(self):
        rb = [((100.0, -300.0), {"spanList": "1800,1500,1800,900"}),       # 南面: 境界を1つ動かした
              ((6400.0, -300.0), {"spanList": "1800,1800"})]                # 東面: そのまま
        ov, warns = overrides_from_readback(PLAN, rb, allowed={1800, 1500, 1200, 900, 600})
        self.assertEqual(ov, [{"edge_index": 0, "face": "南面", "spans_mm": [1800, 1500, 1800, 900]}])
        self.assertEqual(warns, [])

    def test_length_change_is_rejected_and_odd_size_is_flagged(self):
        rb = [((100.0, -300.0), {"spanList": "1800,1800,1800"}),            # 合計が面の長さと違う
              ((6400.0, -300.0), {"spanList": "1800,1700,100"})]            # 規格外を含む（合計は同じ）
        ov, warns = overrides_from_readback(PLAN, rb, allowed={1800, 1500, 1200, 900, 600})
        self.assertEqual([o["edge_index"] for o in ov], [1])
        self.assertEqual(len(warns), 2)
        self.assertIn("採用しません", warns[0])
        self.assertIn("規格外", warns[1])

    def test_unmatched_origin_is_ignored(self):
        self.assertIsNone(match_edge(PLAN, (999.0, 999.0)))

    def test_merge_replaces_same_edge_and_keeps_others(self):
        spec = {"series_id": "shinwa_A", "span_overrides": [{"edge_index": 0, "spans_mm": [1800, 1800, 1800, 600]},
                                                            {"edge_index": 2, "spans_mm": [1800]}]}
        out = merge_overrides(spec, [{"edge_index": 0, "spans_mm": [1800, 1500, 1800, 900]}])
        self.assertEqual(out["span_overrides"], [{"edge_index": 0, "spans_mm": [1800, 1500, 1800, 900]},
                                                 {"edge_index": 2, "spans_mm": [1800]}])
        self.assertEqual(spec["span_overrides"][0]["spans_mm"], [1800, 1800, 1800, 600])   # 元は変えない


class TestGdlSideOfTheEdit(unittest.TestCase):
    """部品側: xEdit を引いたら規格寸法に吸着して spanList を書き戻し、平面に編集ホットスポットを出す."""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"

    def test_parameters_and_snap_logic(self):
        xml = (self.root / "paramlist.xml").read_text(encoding="utf-8")
        for name in ("editSpan", "sizeList", "xEdit"):
            self.assertIn(f'Name="{name}"', xml)
        body1 = (self.root / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        self.assertIn('GLOB_MODPAR_NAME = "xEdit"', body1)
        self.assertIn("if abs(pair - szL[k] - szL[k2]) < 0.0005 then okRest = 1", body1)   # 前後とも規格になる位置だけ
        self.assertIn("parameters spanList = sl1, spanList2 = sl2", body1)
        self.assertIn("parameters xEdit = xe", body1)               # Python から置いたときは spanList が正

    def test_plan_has_editable_hotspots_between_the_ends(self):
        body2 = (self.root / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("for i = 2 to nSpan", body2)
        self.assertIn("hotspot2 xEdit[i], -rowW / 2, 501 + 3 * i, xEdit[i], 2", body2)

    def test_python_sends_the_series_sizes(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_gdl_params import build
        from ashiba.gdl_params import line_params

        m = build("shinwa_A")
        p = line_params(m, m.plan.edges[0])
        self.assertIs(p["editSpan"], True)
        self.assertEqual(p["sizeList"].split(",")[0], "1800")
        self.assertIn("600", p["sizeList"].split(","))


if __name__ == "__main__":
    unittest.main()
