"""Tapirアダプタの失敗の伝え方（実機で踏んだもの）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tapir_adapter import ArchicadClient, TapirError


class _Canned(ArchicadClient):
    """tapir() を差し替えて、送った内容と決めた応答を確認する."""

    def __init__(self, response):
        super().__init__()
        self.response = response
        self.calls = []

    def tapir(self, command, parameters=None):
        self.calls.append((command, parameters))
        return self.response


class TestCreateObjectFailure(unittest.TestCase):
    def test_missing_library_part_is_a_clear_error(self):
        """CreateObjects は要素ごとに error を返す。KeyError 'elementId' で落とさない."""
        c = _Canned({"elements": [{"error": {
            "code": -2130313113,
            "message": "Not found library part with name 'ashiba_line_55a0a1fb'"}}]})
        with self.assertRaises(TapirError) as cm:
            c.create_object("ashiba_line_55a0a1fb", 0, 0)
        msg = str(cm.exception)
        self.assertIn("ashiba_line_55a0a1fb", msg)
        self.assertIn("Not found library part", msg)
        self.assertIn("読み込まれていない", msg)


class TestEmbeddedLibraryPath(unittest.TestCase):
    def test_relative_path_is_sent_absolute(self):
        """Archicad は相対パスを解決できない（Failed to read file になった）."""
        c = _Canned({"executionResults": [{"success": True}]})
        c.add_file_to_embedded_library("out/gsm_dev/x.gsm", "x.gsm")
        sent = c.calls[0][1]["files"][0]["inputPath"]
        self.assertTrue(Path(sent).is_absolute(), sent)
        self.assertTrue(sent.endswith("out/gsm_dev/x.gsm"))


if __name__ == "__main__":
    unittest.main()
