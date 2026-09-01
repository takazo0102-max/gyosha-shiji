"""参照版 .gdl がHSFソースとズレていないことを検査する.

参照版は以前は手書きで、立面モードも壁つなぎ表示も入らないまま放置されて
いた。実物と違う内容を「参照実装」として読むのが一番まずいので、
生成物にしたうえでここでズレを落とす。
"""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_flat_gdl import PARTS, build_flat_gdl  # noqa: E402


class TestFlatGdlSync(unittest.TestCase):
    def test_reference_files_match_hsf(self):
        for part in PARTS:
            with self.subTest(part=part):
                path = ROOT / "gdl" / f"{part}.gdl"
                self.assertTrue(path.exists(), f"{path} がありません")
                self.assertEqual(
                    path.read_text(encoding="utf-8-sig"),
                    build_flat_gdl(part),
                    f"{path.name} がHSFとズレています。"
                    " python3 scripts/build_flat_gdl.py で再生成してください",
                )

    def test_reference_includes_every_hsf_script(self):
        """スクリプトを1本まるごと落とさないこと（旧参照版は3Dも立面も欠けていた）."""
        for part in PARTS:
            with self.subTest(part=part):
                text = build_flat_gdl(part)
                for src in sorted((ROOT / "gdl" / "hsf" / part / "scripts").iterdir()):
                    body = src.read_text(encoding="utf-8-sig").rstrip("\n")
                    self.assertIn(body, text, f"{part}/{src.name} が参照版に無い")


if __name__ == "__main__":
    unittest.main()
