"""足場条件の部品（ashiba_spec）と入力 JSON の対応."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, validate_spec
from ashiba.spec_object import (
    FIELDS,
    merge_object_into_spec,
    params_from_spec,
    pick_spec_object,
    spec_from_params,
    spec_object_position,
)

HSF = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_spec"
RECT = [[300000, 300000], [330000, 300000], [330000, 320000], [300000, 320000]]


class TestParamlistMatchesFields(unittest.TestCase):
    """GDL のパラメータは FIELDS と一対一（型も）。足したのに片方を忘れる、を止める."""

    def test_names_and_types(self):
        root = ET.parse(HSF / "paramlist.xml").getroot()
        declared = {e.get("Name"): e.tag for e in root.find("Parameters") if e.find("Fix") is None}
        kind_to_tag = {"str": "String", "len": "Length", "int": "Integer", "bool": "Boolean"}
        self.assertEqual(set(declared), {f.gdl for f in FIELDS})
        for f in FIELDS:
            self.assertEqual(declared[f.gdl], kind_to_tag[f.kind], f.gdl)

    def test_ui_shows_every_field(self):
        ui = (HSF / "scripts" / "ui.gdl").read_text(encoding="utf-8")
        for f in FIELDS:
            self.assertIn(f'"{f.gdl}"', ui, f.gdl)
        for title in ("基本", "高さ・離れ", "安全・表示"):
            self.assertIn(f'-1, "{title}"', ui)        # ページ名（無いと見出しが「…」になる）


class TestRoundTrip(unittest.TestCase):
    def test_params_to_spec_and_back(self):
        spec = {"project_name": "A棟", "module": "inch", "eaves_height_mm": 12000, "guard_extra_mm": 900,
                "period_days": 120, "standoff": {"target": 300, "min": 250, "max": 350, "hard_min": 250},
                "guard_rail_type": "先行手すり", "inner_guard_rail": False, "site": {"region": "九州(南部)"},
                "asagao": {"stages": 1}, "elevation_mode": "section"}
        p = params_from_spec(spec)
        self.assertIs(p["innerRail"], False)                 # Boolean は bool で送る
        self.assertIsInstance(p["periodDays"], int)
        self.assertAlmostEqual(p["eavesH"], 12.0)            # 長さは m
        self.assertEqual(p["seriesId"], "")                  # 系列なし＝モジュールの既定
        back = spec_from_params(p)
        self.assertEqual(back["eaves_height_mm"], 12000)
        self.assertEqual(back["standoff"]["hard_min"], 250)
        self.assertEqual(back["site"]["region"], "九州(南部)")
        self.assertEqual(back["asagao"]["stages"], 1)
        self.assertNotIn("series_id", back)
        self.assertNotIn("scaffold_height_mm", back)         # 0 は未指定

    def test_object_wins_and_drops_conflicting_series(self):
        base = {"series_id": "shinwa_A", "site": {"region": "関東(内陸)", "sheet_type": "メッシュシート"},
                "span_overrides": [{"edge_index": 0, "spans_mm": [1800]}]}
        obj = spec_from_params({"moduleKind": "inch", "seriesId": "", "region": "沖縄"})
        out = merge_object_into_spec(base, obj)
        self.assertNotIn("series_id", out)                   # インチの既定（ND1800）になる
        self.assertEqual(out["site"], {"region": "沖縄", "sheet_type": "メッシュシート"})
        self.assertEqual(out["span_overrides"], base["span_overrides"])   # 一覧の条件は JSON のまま
        self.assertEqual(base["site"]["region"], "関東(内陸)")              # 元は変えない

    def test_object_spec_is_valid_input(self):
        """部品の既定値だけで組んだ入力が検証を通り、解ける."""
        defaults = {f.gdl: f.default for f in FIELDS}
        spec = merge_object_into_spec({"outline_mm": RECT}, spec_from_params(defaults))
        validate_spec(spec)
        r = solve_all(spec)
        self.assertEqual(r.model.master.series_id, "shinwa_A")


class TestPick(unittest.TestCase):
    def test_nearest_within_reach(self):
        near = ({"id": "near"}, (299000.0, 291000.0), {"projName": "A"})
        far = ({"id": "far"}, (400000.0, 291000.0), {"projName": "B"})
        self.assertEqual(pick_spec_object([far, near], RECT)[0]["id"], "near")
        self.assertIsNone(pick_spec_object([far], RECT))

    def test_default_position_is_outside_the_section_lines(self):
        x, y = spec_object_position(RECT)
        self.assertEqual(x, 300000)
        self.assertLess(y, 300000 - 8000)
        self.assertIsNotNone(pick_spec_object([({}, (x, y), {})], RECT))   # 置いた場所は次回拾える


if __name__ == "__main__":
    unittest.main()
