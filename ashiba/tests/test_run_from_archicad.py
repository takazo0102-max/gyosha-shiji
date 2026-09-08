"""ツールバー割当スクリプトの条件上書きファイルの扱い（実機不要）."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("run_from_archicad", ROOT / "scripts" / "run_from_archicad.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSpecOverride(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ashiba_spec.json"
        self.mod.SPEC_OVERRIDE = self.path

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_means_no_override(self):
        self.assertEqual(self.mod.load_spec_override(), {})

    def test_bom_file_is_read_and_outline_is_ignored(self):
        self.path.write_bytes("﻿".encode("utf-8") + b'{"series_id": "waku", "outline_mm": [[0,0]]}')
        self.assertEqual(self.mod.load_spec_override(), {"series_id": "waku"})

    def test_broken_file_stops_instead_of_falling_back(self):
        """読めない上書きファイルで既定条件の足場を黙って置かない（waku のつもりが信和Aになった）."""
        from ashiba.cli import InputError

        self.path.write_text('{"series_id": "waku",}', encoding="utf-8")
        with self.assertRaises(InputError) as cm:
            self.mod.load_spec_override()
        self.assertIn("読めません", str(cm.exception))

    def test_non_object_file_stops(self):
        from ashiba.cli import InputError

        self.path.write_text('["waku"]', encoding="utf-8")
        with self.assertRaises(InputError):
            self.mod.load_spec_override()


if __name__ == "__main__":
    unittest.main()
