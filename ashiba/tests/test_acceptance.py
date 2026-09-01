"""受け入れ基準（仕様10）のエンドツーエンドテスト."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import run

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class TestAcceptance(unittest.TestCase):
    def test_rect_one_click(self):
        """矩形建物で割付〜数量CSVまでワンクリック生成."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "rect_30x20.json", out)
            name = result["project"]
            self.assertTrue((out / f"{name}_数量表.csv").exists())
            self.assertTrue((out / f"{name}_割付レポート.md").exists())
            self.assertTrue((out / f"{name}_plan.json").exists())
            self.assertEqual(result["checks"]["ng"], 0)
            # 高さ10m以上・60日以上 → 設置届 要
            self.assertTrue(result["notification_required"])
            csv_text = (out / f"{name}_数量表.csv").read_text(encoding="utf-8-sig")
            self.assertIn("架け面積", csv_text)
            self.assertIn("A-3609", csv_text)  # 型番ベース

            # Phase 2: 設置届一式（様式20号＋構造計算書＋明細）が出る
            xlsx = out / f"{name}_設置届一式.xlsx"
            self.assertTrue(xlsx.exists())
            import zipfile
            z = zipfile.ZipFile(xlsx)
            self.assertIsNone(z.testzip())
            # 壁つなぎは構造計算から逆算され、検定を満たす
            self.assertTrue(result["structural"]["all_ok"])
            self.assertLessEqual(result["structural"]["wall_tie_ratio"], 1.0)
            self.assertGreater(result["wall_ties"]["count"], 0)
            # 暫定耐力値を使っていることは必ず申告される
            self.assertTrue(result["structural"]["unverified_capacity_used"])

    def test_l_shape_one_click(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "l_shape.json", out)
            self.assertEqual(result["checks"]["ng"], 0)
            self.assertGreater(result["posts_per_level"], 0)


if __name__ == "__main__":
    unittest.main()
