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

    def test_b_series_nextgen_with_brackets(self):
        """B系列＋次世代足場＋ブラケット区間でも一式が出る."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "b_series_nextgen.json", out)
            self.assertEqual(result["checks"]["total"], 10)
            self.assertEqual(result["checks"]["ng"], 0)
            self.assertEqual(result["bracket_sections"], 1)
            # ブラケットの検証で問題が出ていない
            self.assertEqual(
                [w for w in result["warnings"] if w.startswith("ブラケット[NG]")], []
            )
            # 高さ10m以上なので朝顔が自動で1段入る
            self.assertEqual(result["asagao"]["stages"], 1)
            csv_text = (out / f"{result['project']}_数量表.csv").read_text(
                encoding="utf-8-sig"
            )
            self.assertNotIn("該当部材がありません", csv_text)  # 系列の欠品なし
            self.assertIn("B-", csv_text)                       # B系列の型番

    def test_frame_scaffold_one_click(self):
        """枠組足場（建枠方式）でも一式が出る."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "waku_frame.json", out)
            self.assertEqual(result["checks"]["total"], 10)
            self.assertEqual(result["checks"]["ng"], 0)
            self.assertGreaterEqual(result["stairs"]["count"], 1)
            csv_text = (out / f"{result['project']}_数量表.csv").read_text(
                encoding="utf-8-sig"
            )
            self.assertNotIn("該当部材がありません", csv_text)
            self.assertIn("建枠", csv_text)
            self.assertIn("アームロック", csv_text)
            self.assertNotIn("支柱", csv_text)   # くさび式の部材は出ない

    def test_sloped_site_jack_table(self):
        """傾斜地でも支柱ごとのジャッキ量一覧まで出る（Phase 4の差別化機能）."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "sloped_site.json", out)
            self.assertEqual(result["checks"]["ng"], 0)
            t = result["terrain"]
            self.assertGreater(t["gl_difference_mm"], 1000)
            self.assertGreater(t["foot_variants"], 1)   # 脚部構成が複数種になる
            csv_path = out / f"{result['project']}_ジャッキ量一覧.csv"
            self.assertTrue(csv_path.exists())
            text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("ジャッキ繰出し(mm)", text)
            self.assertIn("下げコマ数", text)
            # 上限超過は黙って丸めず対処まで書く
            self.assertIn("敷板", text + "".join(result["warnings"]))

    def test_loading_stage_and_hoist(self):
        """荷受けステージ・昇降機がある計画でも一式が出て、建地検定に反映される."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "loading_stage.json", out)
            p = result["platforms"]
            self.assertEqual(p["loading_stages"], 1)
            self.assertEqual(p["hoists"], 1)
            self.assertTrue(p["ok"])
            self.assertGreater(p["max_post_load_kn"], 0)
            self.assertGreater(p["extra_wall_ties"], 0)
            self.assertIsNotNone(p["governing"])
            # 昇降機本体が対象外であることは黙らない
            self.assertTrue(any("対象外" in w for w in result["warnings"]))
            self.assertEqual(result["checks"]["ng"], 0)

    def test_stairs_auto_placed(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = run(EXAMPLES / "rect_30x20.json", out)
            stairs = result["stairs"]
            self.assertGreaterEqual(stairs["count"], stairs["required_count"])
            self.assertLessEqual(stairs["max_travel_m"], 30.0)


if __name__ == "__main__":
    unittest.main()
