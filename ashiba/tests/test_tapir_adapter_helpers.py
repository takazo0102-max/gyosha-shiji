"""Tapir アダプタの補助（実機不要で確認できるもの）."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tapir_adapter import ArchicadClient, TapirError


class _Stub(ArchicadClient):
    """tapir() を記録するだけの疑似クライアント."""

    def __init__(self, fail_names=()):
        self.calls = []
        self.fail_names = set(fail_names)

    def tapir(self, command, params):
        self.calls.append((command, params))
        if command == "AddFilesToEmbeddedLibrary":
            out = params["files"][0]["outputPath"]
            ok = not any(n in out for n in self.fail_names)
            return {"executionResults": [{"success": ok, "error": None if ok else {"message": "not a valid relative path"}}]}
        return {}


class TestEnsureEmbeddedParts(unittest.TestCase):
    def test_adds_missing_and_tolerates_existing(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "ashiba_line.gsm"; a.write_bytes(b"x")
            b = Path(d) / "ashiba_detail.gsm"; b.write_bytes(b"x")
            c = _Stub(fail_names=["ashiba_detail"])       # 既にある想定
            added = c.ensure_embedded_parts([a, b, Path(d) / "missing.gsm"])
        self.assertEqual(added, ["ashiba_line.gsm"])
        adds = [p for cmd, p in c.calls if cmd == "AddFilesToEmbeddedLibrary"]
        self.assertEqual(len(adds), 2)                        # 無いファイルは送らない
        self.assertTrue(all(p["files"][0]["outputPath"].startswith("ashiba/") for p in adds))
        self.assertTrue(any(cmd == "ReloadLibraries" for cmd, _ in c.calls))


if __name__ == "__main__":
    unittest.main()
