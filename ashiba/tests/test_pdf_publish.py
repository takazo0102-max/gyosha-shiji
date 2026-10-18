"""足場のレイアウトの PDF 発行（Phase 9-5）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.pdf_publish import find_layout_items, find_subset_item, publish_params

TREE = {"type": "FolderItem", "name": "???", "navigatorItemId": {"guid": "R"}, "children": [
    {"navigatorItem": {"type": "UndefinedItem", "name": "仮設足場", "navigatorItemId": {"guid": "SUB"}, "children": [
        {"navigatorItem": {"type": "LayoutItem", "name": "A棟 足場立面図", "navigatorItemId": {"guid": "A1"}}},
        {"navigatorItem": {"type": "LayoutItem", "name": "A棟 足場平面図", "navigatorItemId": {"guid": "A2"}}},
        {"navigatorItem": {"type": "LayoutItem", "name": "B棟 足場立面図", "navigatorItemId": {"guid": "B1"}}},
    ]}},
    {"navigatorItem": {"type": "LayoutItem", "name": "各階平面図", "navigatorItemId": {"guid": "X"}}},
]}


class TestSelect(unittest.TestCase):
    def test_only_this_project_layouts(self):
        self.assertEqual(find_layout_items(TREE, "A棟"), ["A1", "A2"])
        self.assertEqual(find_subset_item(TREE), "SUB")
        self.assertEqual(find_layout_items(TREE, "C棟"), [])

    def test_params_use_navigator_item_id_wrapper(self):
        # 実機: {"guid": …} だけだと "selectedNavigatorItemId is corrupt or missing"
        p = publish_params("2 - レイアウト", ["A1", "A2"], Path("/tmp/x"))
        self.assertEqual(p["selectedNavigatorItemIds"][0], {"navigatorItemId": {"guid": "A1"}})
        self.assertEqual(p["outputPath"], "/tmp/x")
        self.assertEqual(publish_params("s", "SUB", Path("/o"))["selectedNavigatorItemIds"],
                         [{"navigatorItemId": {"guid": "SUB"}}])

    def test_toolbar_publishes_by_default_in_section_mode(self):
        src = (Path(__file__).resolve().parents[1] / "scripts" / "run_from_archicad.py").read_text(encoding="utf-8")
        self.assertIn('if elevation_mode == "section" and spec.get("pdf", True):', src)


if __name__ == "__main__":
    unittest.main()
