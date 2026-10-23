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


class TestStalePdfs(unittest.TestCase):
    def test_old_pdfs_of_this_project_are_removed(self):
        """前回の同じ工事の足場の PDF で今回出なかったもの（「A-A 1」→「A-A」に変わった等）は消す。ほかは触らない."""
        import os
        import tempfile
        import time

        from ashiba.pdf_publish import publish_scaffold_pdf

        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "名称未設定" / "2 仮設足場"
            sub.mkdir(parents=True)
            old = {n: sub / n for n in ("2.6 A棟 足場断面図 A-A 1.pdf", "2.1 B棟 足場平面図.pdf", "メモ.pdf")}
            for q in old.values():
                q.write_bytes(b"%PDF")
                os.utime(q, (time.time() - 3600, time.time() - 3600))

            class Client:
                def tapir(self, cmd, params):
                    if cmd == "GetNavigatorItemTree":
                        return {"navigatorItemTree": TREE}
                    (sub / "2.4 A棟 足場断面図 A-A.pdf").write_bytes(b"%PDF")
                    return {}

            res = publish_scaffold_pdf(Client(), Path(d), prefix="A棟")
            self.assertEqual([f.name for f in res.files], ["2.4 A棟 足場断面図 A-A.pdf"])
            self.assertFalse(old["2.6 A棟 足場断面図 A-A 1.pdf"].exists())
            self.assertTrue(old["2.1 B棟 足場平面図.pdf"].exists())          # 別の工事
            self.assertTrue(old["メモ.pdf"].exists())
            self.assertIn("前回の PDF 1枚", res.notes[-1])


if __name__ == "__main__":
    unittest.main()
