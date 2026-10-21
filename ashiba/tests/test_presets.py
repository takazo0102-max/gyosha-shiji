"""足場条件の登録と呼び出し（参考: smartCON Planner の足場条件の登録）."""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.presets import BUILDING_FIELDS, PRESET_FIELDS, apply_preset, list_presets, load_preset, save_preset
from ashiba.spec_object import FIELDS, params_from_spec


def _params(**kw):
    spec = {"project_name": "A棟", "series_id": "nikken_strong", "eaves_height_mm": 12000,
            "guard_rail_type": "先行手すり", "scaffold_width_mm": 900, "stairs": {"layout": "外付け"},
            "horizontal_net_levels": [2, 5], "faces": "南面,東面", "_preset": "日建ストロング標準",
            "member_edits": [{"face": "南面", "spans": 1, "parts": "踏板"}]}
    spec.update(kw)
    return params_from_spec(spec)


class TestPresets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_keeps_only_the_shared_conditions(self):
        p = _params()
        path = save_preset(p["presetName"], p, self.out)
        body = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(body["name"], "日建ストロング標準")
        self.assertEqual(body["params"]["railType"], "先行手すり")
        self.assertEqual(body["params"]["scaffW"], 900)
        for k in ("projName", "eavesH", "facesOnly", "memberEdit1", "presetName"):
            self.assertNotIn(k, body["params"])
        self.assertEqual(body["spec"]["horizontal_net_levels"], [2, 5])
        self.assertNotIn("member_edits", body["spec"])
        self.assertEqual(list_presets(self.out), ["日建ストロング標準"])

    def test_load_onto_another_building_keeps_its_own_values(self):
        src = _params()
        save_preset("標準", src, self.out)
        other = params_from_spec({"project_name": "B棟", "eaves_height_mm": 6000, "faces": "北面"})
        new, changed = apply_preset(other, load_preset("標準", self.out))
        self.assertEqual(new["railType"], "先行手すり")
        self.assertEqual(new["seriesId"], src["seriesId"])
        self.assertEqual(new["stairLayout"], "外付け")
        self.assertEqual(new["projName"], "B棟")
        self.assertAlmostEqual(new["eavesH"], 6.0)
        self.assertEqual(new["facesOnly"], "北面")
        self.assertIn("railType", changed)
        self.assertNotIn("projName", changed)

    def test_missing_name(self):
        with self.assertRaises(ValueError):
            save_preset("  ", _params(), self.out)
        save_preset("A", _params(), self.out)
        with self.assertRaises(FileNotFoundError) as cm:
            load_preset("B", self.out)
        self.assertIn("A", str(cm.exception))

    def test_name_is_a_safe_file_name(self):
        path = save_preset("A/B工区", _params(), self.out)
        self.assertEqual(path.parent.name, "条件の登録")
        self.assertEqual(load_preset("A/B工区", self.out)["railType"], "先行手すり")

    def test_fields_are_split_cleanly(self):
        names = {f.gdl for f in FIELDS}
        self.assertTrue(BUILDING_FIELDS <= names)
        self.assertEqual(set(PRESET_FIELDS) | BUILDING_FIELDS, names)

    def test_preset_name_does_not_reach_the_plan(self):
        from ashiba.cli import solve_all
        from ashiba.spec_object import spec_from_params

        frag = spec_from_params(_params())
        self.assertEqual(frag["_preset"], "日建ストロング標準")
        spec = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000,
                "_preset": "x"}
        self.assertTrue(solve_all(spec).model.plan.edges)


class TestPalette(unittest.TestCase):
    def test_buttons(self):
        from ashiba.palette import ACTIONS

        # 条件の登録・呼び出しはパレットのメニューから選ぶ
        by = {e.title: e for e in ACTIONS}
        self.assertEqual(by["条件の登録"].args, ("save",))
        self.assertEqual(by["条件の呼び出し"].args, ("load",))
        self.assertIn("spec", by["条件の登録"].when)
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "scripts" / "spec_preset.py").exists())


if __name__ == "__main__":
    unittest.main()
