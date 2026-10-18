"""埋め込みライブラリの版付き部品の整理（Phase 13-3）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.library_versions import CLEANUP_STEPS, count_versions, current_versions, split_name

ROOT = Path(__file__).resolve().parents[1]


class TestVersions(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_name("ashiba_line_67740d9e"), ("ashiba_line", "67740d9e"))
        self.assertEqual(split_name("ashiba_detail"), ("ashiba_detail", ""))
        self.assertIsNone(split_name("柱脚_fr"))
        self.assertIsNone(split_name("ashiba_other_12345678"))

    def test_current_from_hash_files(self):
        cur = current_versions(ROOT / "gdl")
        for base in ("ashiba_line", "ashiba_detail", "ashiba_mvo", "ashiba_spec"):
            self.assertEqual(len(cur[base]), 8, base)

    def test_report_separates_old_parts_and_the_spec_object(self):
        cur = {"ashiba_line": "aaaaaaaa", "ashiba_spec": "cccccccc"}
        rep = count_versions(["ashiba_line_aaaaaaaa"] * 3 + ["ashiba_line_bbbbbbbb", "ashiba_spec_dddddddd", "壁"], cur)
        self.assertEqual(rep.in_use["ashiba_line"], {"aaaaaaaa": 3, "bbbbbbbb": 1})
        text = "\n".join(rep.lines())
        self.assertIn("ashiba_line_bbbbbbbb 1個", text)
        self.assertIn("足場条件の部品は古い版のまま", text)          # 条件部品は置き換わらない
        self.assertNotIn("ashiba_spec_dddddddd 1個", text.split("足場条件")[0])
        self.assertTrue(any("置いてある版は消さない" in s for s in CLEANUP_STEPS))


if __name__ == "__main__":
    unittest.main()
