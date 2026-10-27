"""受け入れ基準（仕様10）のエンドツーエンドテスト."""

import json
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
            self.assertIn("SA-36", csv_text)  # 型番ベース（信和の実品番）

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
            self.assertEqual(result["checks"]["total"], 12)
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
            self.assertEqual(result["checks"]["total"], 12)
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
            self.assertIn("下げ段数", text)
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


class TestOverallVerdict(unittest.TestCase):
    """成立しているかを1箇所で言えること.

    法規・構造・荷受けステージ・開口部・ブラケット区間がそれぞれ別々に
    判定を持っていて、どこかがNGでも他は緑のままだった。
    """

    BASE = {
        "series_id": "shinwa_A",
        "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
        "eaves_height_mm": 15400, "guard_extra_mm": 900, "period_days": 90,
    }

    def _run(self, name, **extra):
        spec = dict(self.BASE, project_name=name, **extra)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            f = out / "s.json"
            f.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            result = run(f, out / "o")
            report = (out / "o" / f"{name}_割付レポート.md").read_text(encoding="utf-8")
        return result, report

    def test_clean_plan_is_ok(self):
        r, report = self._run("正常")
        self.assertTrue(r["verdict"]["ok"])
        self.assertEqual(r["verdict"]["blockers"], [])
        self.assertIn("計画は成立しています", report)

    def test_opening_ng_blocks_even_when_law_checks_pass(self):
        """法規12/12 OKでも、開口部が規格外なら成立していない."""
        r, report = self._run(
            "梁枠規格外", series_id="shinwa_B",
            openings=[{"edge_index": 2, "start_mm": 3600, "beam_span_mm": 7200}],
        )
        self.assertEqual(r["checks"]["ng"], 0)
        self.assertFalse(r["verdict"]["ok"])
        self.assertTrue(any("開口部" in b for b in r["verdict"]["blockers"]))
        self.assertIn("是正が必要です", report)

    def test_law_check_ng_blocks(self):
        """法規チェックのNGが総合判定に入ること（入れなくても落ちなかった箇所）."""
        r, report = self._run(
            "本足場原則NG", scaffold_form="一側足場", clearance_space_mm=2000)
        self.assertGreater(r["checks"]["ng"], 0)
        self.assertFalse(r["verdict"]["ok"])
        self.assertTrue(
            any("法規チェックNG" in b for b in r["verdict"]["blockers"]),
            r["verdict"],
        )
        self.assertIn("是正が必要です", report)
        # 件数だけでなく、どの条文で落ちたかを判定の直下に出す
        ng_texts = [w for w in r["warnings"] if w.startswith("法規チェック[NG] #")]
        self.assertEqual(len(ng_texts), r["checks"]["ng"], r["warnings"])
        for t in ng_texts:
            self.assertIn(f"- 是正: 法規チェック: {t}", report)

    def test_terrain_warnings_reach_the_checklist(self):
        """敷地の警告が要確認一覧に載ること（落としても落ちなかった箇所）.

        法規チェック6と同じ文面のものは重ねないので、敷地固有の警告
        （敷板・床掘りの調整）を直接与えて配線だけを見る。
        """
        from types import SimpleNamespace

        from ashiba.cli import collect_warnings

        terrain = SimpleNamespace(
            warnings=["ジャッキの可動域で吸収しきれない支柱が3本あります"],
            notes=[], feet=[],
        )
        got = collect_warnings(
            SimpleNamespace(warnings=[], notes=[]),
            SimpleNamespace(plan=SimpleNamespace(warnings=[]),
                            elevation=SimpleNamespace(warnings=[])),
            [], SimpleNamespace(warnings=[]), [],
            SimpleNamespace(issues=[]), terrain, SimpleNamespace(issues=[]),
        )
        self.assertEqual(
            [(kind, text) for kind, _sev, text in got],
            [("敷地", "敷地: ジャッキの可動域で吸収しきれない支柱が3本あります")],
        )

    def test_platform_ng_blocks(self):
        r, _ = self._run("ステージ重なり", loading_stages=[
            {"edge_index": 0, "start_mm": 3600, "span_count": 2},
            {"edge_index": 0, "start_mm": 5400, "span_count": 2},
        ])
        self.assertFalse(r["verdict"]["ok"])
        self.assertTrue(
            any("ステージ" in b for b in r["verdict"]["blockers"]),
            r["verdict"],
        )

    def test_blockers_name_the_reason(self):
        """判定だけでなく、どこが引っかかったかを言う."""
        r, _ = self._run(
            "梁枠規格外2", series_id="shinwa_B",
            openings=[{"edge_index": 2, "start_mm": 3600, "beam_span_mm": 7200}],
        )
        for b in r["verdict"]["blockers"]:
            self.assertGreater(len(b), 5, b)

    def test_warn_count_covers_every_warning(self):
        """「要確認0件」の裏に離れの措置や未確認耐力値が隠れないこと."""
        r, report = self._run("要確認の数")
        # NG は blockers 側に出るので、要確認の件数からは除く
        non_ng = [w for w in r["warnings"] if "[NG]" not in w]
        self.assertEqual(r["verdict"]["warn"], r["checks"]["warn"] + len(non_ng))
        self.assertGreater(r["verdict"]["warn"], 0)
        self.assertIn(f"要確認 {r['verdict']['warn']}件", report)

    def test_warn_breakdown_names_the_source(self):
        r, _ = self._run("要確認の内訳")
        self.assertTrue(r["verdict"]["warn_breakdown"])
        # 内訳の合計と総数が食い違わない
        total = sum(int(x.split()[-1].rstrip("件"))
                    for x in r["verdict"]["warn_breakdown"])
        self.assertEqual(total, r["verdict"]["warn"])

    def test_ng_is_not_counted_twice(self):
        r, _ = self._run(
            "梁枠規格外3", series_id="shinwa_B",
            openings=[{"edge_index": 2, "start_mm": 3600, "beam_span_mm": 7200}],
        )
        self.assertFalse(r["verdict"]["ok"])
        # 開口部はNG1件＋常時の注意1件。要確認に数えるのは後者だけ
        ng = [w for w in r["warnings"] if w.startswith("開口部") and "NG" in w]
        self.assertTrue(ng)
        self.assertIn("開口部 1件", r["verdict"]["warn_breakdown"])

    def test_report_lists_every_warning_once(self):
        """冒頭の「要確認N件」が本文の一覧と一致すること."""
        r, report = self._run("要確認一覧", ground_points_mm=[
            [0, 0, 0], [30000, 0, 900], [30000, 20000, 900], [0, 20000, 0],
        ])
        body = report.split("## 要確認一覧")[1]
        rows = [ln for ln in body.splitlines() if ln.startswith("| ") and
                not ln.startswith("| # ") and not ln.startswith("|---")]
        self.assertEqual(len(rows), r["verdict"]["warn"])

    def test_terrain_and_law_check_do_not_repeat_each_other(self):
        """同じジャッキ超過を敷地と法規で二度言わない."""
        r, report = self._run("重複しない", ground_points_mm=[
            [0, 0, 0], [30000, 0, 900], [30000, 20000, 900], [0, 20000, 0],
        ])
        body = report.split("## 要確認一覧")[1]
        self.assertEqual(body.count("実務上限270mmを超える支柱"), 1, body)

    # 是正になる例題と、その理由。くさび支柱の一般値6.86kN（信和の認定値は非公開）に
    # 1tの荷受けステージは載らない。ツールが正しく止める例として残している
    # opening_beam: 梁枠の両端の支柱が許容（信和A の一般値 6.86kN）を超える（2026-10-27 から総合判定に入れた。それまでは
    # 構造の注意に「2本組等の補強が必要」と出ても「計画は成立」だった）
    EXPECTED_BLOCKERS = {"loading_stage.json": "建地圧縮", "opening_beam.json": "開口部の梁枠の検定NG"}

    def test_every_example_has_the_expected_verdict(self):
        for f in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(f.name), tempfile.TemporaryDirectory() as td:
                r = run(f, Path(td))
                want = self.EXPECTED_BLOCKERS.get(f.name)
                if want is None:
                    self.assertTrue(r["verdict"]["ok"], f"{f.name}: {r['verdict']}")
                else:
                    self.assertFalse(r["verdict"]["ok"], f"{f.name}: 是正のはず")
                    self.assertTrue(
                        any(want in b for b in r["verdict"]["blockers"]),
                        f"{f.name}: {r['verdict']['blockers']}")


if __name__ == "__main__":
    unittest.main()
