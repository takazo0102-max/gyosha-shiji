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
        body1 = (self.root / "scripts" / "vl.gdl").read_text(encoding="utf-8")       # 吸着はパラメータスクリプト
        self.assertIn('GLOB_MODPAR_NAME = "xEdit"', body1)
        master = (self.root / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        self.assertNotIn("parameters xEdit", master)      # マスターで配列を書き戻すと 2D・3D が描けなくなる（実機で切り分け）
        self.assertIn("parameters xEdit = xe", body1)
        self.assertIn("<Script_VL", (self.root / "libpartdata.xml").read_text(encoding="utf-8"))
        self.assertIn("if abs(rem - szL[k2] - szL[k3]) < 0.0005 then okRest = 1", body1)   # 残りを規格2本に分けて挿入
        self.assertIn("nSpan = nSpan - 1", body1)                                             # 隣に重ねたら結合
        self.assertIn("nSpan = nSpan + 1", body1)
        self.assertIn("parameters spanList = sl1, spanList2 = sl2", body1)
        self.assertIn("parameters xEdit = xe", body1)               # Python から置いたときは spanList が正

    def test_plan_has_editable_hotspots_between_the_ends(self):
        body2 = (self.root / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("for i = 2 to nSpan", body2)
        self.assertIn("hotspot2 xEdit[i], -rowW, 501 + 3 * i, xEdit[i], 2", body2)

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


class TestSnapRule(unittest.TestCase):
    """吸着規則（部品の1Dと同じ）: 規格寸法だけで面の長さを保つ."""

    A = (1800, 1500, 1200, 900, 600)

    def test_pair_that_can_be_two_sizes(self):
        from ashiba.span_readback import snap_boundary

        self.assertEqual(snap_boundary([1800, 900], 2, 1450, self.A), [1500, 1200])
        self.assertEqual(snap_boundary([1800, 900], 2, 1250, self.A), [1200, 1500])

    def test_1800_1800_boundary_inserts_a_span(self):
        from ashiba.span_readback import snap_boundary

        self.assertEqual(snap_boundary([1800, 1800, 1800], 2, 1500, self.A), [1500, 1500, 600, 1800])
        self.assertEqual(snap_boundary([1800, 1800, 1800], 3, 1250, self.A), [1800, 1200, 1800, 600])
        self.assertEqual(sum(snap_boundary([1800, 1800, 1800], 2, 1500, self.A)), 5400)

    def test_dragging_onto_the_neighbour_merges_only_into_a_size(self):
        from ashiba.span_readback import snap_boundary

        self.assertEqual(snap_boundary([900, 900, 1800], 2, 50, self.A), [1800, 1800])
        self.assertEqual(snap_boundary([1200, 600], 2, 1790, self.A), [1800])
        self.assertEqual(snap_boundary([1800, 900], 2, 2690, self.A), [1800, 900])   # 2700 は規格に無い

    def test_no_change_when_nothing_fits(self):
        from ashiba.span_readback import snap_boundary

        self.assertEqual(snap_boundary([1800, 1800], 2, 1800, self.A), [1800, 1800])
        self.assertEqual(snap_boundary([1800, 1800], 5, 1500, self.A), [1800, 1800])


class TestHeightReadback(unittest.TestCase):
    """3D の天端のホットスポットで引いた足場高さを、全面の目標高さとして読み戻す."""

    PLAN = {
        "scaffold_height_mm": 16300,
        "elevation": {"level_heights": [2800, 4600, 6400, 8200, 10000, 11800, 13600, 15400]},
        "edges": [{"edge_index": 0, "face": "南面", "placement": {"x_mm": 0, "y_mm": 0}},
                  {"edge_index": 1, "face": "東面", "placement": {"x_mm": 30000, "y_mm": 0}}],
    }

    def _rb(self, levels, origin=(0, 0)):
        return (origin, {"levelList": ",".join(str(v) for v in levels)})

    def test_unchanged_is_none(self):
        from ashiba.span_readback import height_from_readback

        lv = self.PLAN["elevation"]["level_heights"]
        self.assertEqual(height_from_readback(self.PLAN, [self._rb(lv)]), (None, []))

    def test_one_level_up(self):
        from ashiba.span_readback import height_from_readback

        lv = self.PLAN["elevation"]["level_heights"] + [17200]
        h, notes = height_from_readback(self.PLAN, [self._rb(lv)])
        self.assertEqual(h, 18100)
        self.assertIn("南面", notes[-1])

    def test_two_levels_down(self):
        from ashiba.span_readback import height_from_readback

        lv = self.PLAN["elevation"]["level_heights"][:-2]
        h, _ = height_from_readback(self.PLAN, [self._rb(lv)])
        self.assertEqual(h, 16300 - 3600)

    def test_lower_face_as_placed_is_not_a_change(self):
        # 実機 2026-10-25: セットバックの低い東面（2層）を全体の立面（5層）と比べて「天端を引き下げた」と読み、足場高さを
        # 5200 に書き換えていた（上まで伸びなくなっている）。比べるのはその面を置いたときの作業床
        from ashiba.span_readback import height_from_readback

        full = [2445, 4245, 6045, 7845, 9645]
        low = [2445, 4245]
        plan = {"scaffold_height_mm": 10600, "elevation": {"level_heights": full},
                "edges": [{"edge_index": 0, "face": "南面", "placement": {"x_mm": 0, "y_mm": 0},
                           "gdl_params": {"levelList": ",".join(str(v) for v in full)}},
                          {"edge_index": 1, "face": "東面", "placement": {"x_mm": 30000, "y_mm": 0},
                           "gdl_params": {"levelList": ",".join(str(v) for v in low)}}]}
        rbs = [self._rb(full), self._rb(low, origin=(30000, 0))]
        self.assertEqual(height_from_readback(plan, rbs), (None, []))
        # 低い面を1層上げたら、その面の差（+1800）を全体に
        h, _ = height_from_readback(plan, [self._rb(full), self._rb(low + [6045], origin=(30000, 0))])
        self.assertEqual(h, 10600 + 1800)

    def test_different_faces_take_the_largest_and_say_so(self):
        from ashiba.span_readback import height_from_readback

        base = self.PLAN["elevation"]["level_heights"]
        h, notes = height_from_readback(
            self.PLAN, [self._rb(base + [17200]), self._rb(base + [17200, 19000], origin=(30000, 0))])
        self.assertEqual(h, 16300 + 3600)
        self.assertTrue(any("面ごとに違う高さ" in n for n in notes), notes)
