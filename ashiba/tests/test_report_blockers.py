"""是正が必要なときの割付レポート: 構造の是正（耐力不足・梁枠の両端の支柱）は判定の下に中身を出す（2026-10-27 のループ:
判定には「開口部の梁枠の検定NG 2件」と件数しか無く、何をどう直すかは要確認一覧まで探さないと分からなかった）."""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_groups, write_outputs

ROOT = Path(__file__).resolve().parents[1]


class TestStructuralFixesUnderTheVerdict(unittest.TestCase):
    def test_opening_beam_end_posts_are_listed(self):
        r = solve_groups(json.loads((ROOT / "examples" / "opening_beam.json").read_text(encoding="utf-8")))[0][1]
        self.assertFalse(r.verdict["ok"])
        with tempfile.TemporaryDirectory() as td:
            write_outputs(r, Path(td))
            md = next(Path(td).glob("*_割付レポート.md")).read_text(encoding="utf-8")
        head = md.split("## ")[0]
        self.assertIn("是正: 構造: 南面の開口部", head)
        self.assertIn("2本組", head)


if __name__ == "__main__":
    unittest.main()
