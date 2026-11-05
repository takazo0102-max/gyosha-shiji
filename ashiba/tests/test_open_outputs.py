"""「帳票」の結果の窓の行（scripts/open_outputs.py）."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import open_outputs  # noqa: E402


class TestSummary(unittest.TestCase):
    def test_recent_only(self):
        """帳票が多くても、新しい順に RECENT 個と残りの数だけ（60 個近くを1行に並べて読めなかった 2026-11-05）."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            now = time.time()
            for i in range(20):
                f = d / f"帳票{i:02d}.md"
                f.write_text("x", encoding="utf-8")
                os.utime(f, (now + i, now + i))
            (d / "控え.json").write_text("{}", encoding="utf-8")
            lines = open_outputs.summary(d, d / "帳票19.md")
            self.assertIn("帳票19.md を開きました", lines[0])
            self.assertTrue(lines[1].startswith("  新しい帳票: 帳票19.md・帳票18.md"))
            self.assertIn(f"ほか {20 - open_outputs.RECENT}個", lines[1])
            self.assertNotIn("控え.json", lines[1])
            self.assertNotIn("帳票00.md", lines[1])


if __name__ == "__main__":
    unittest.main()
