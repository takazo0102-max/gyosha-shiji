"""日建リース NDシステム1800: カタログの実品番・確定耐力値で計画が解ける.

以前の inch 系列は型番仮・暫定耐力値（A系列流用）だった。仮設資材カタログVol.10
（data/NIKKEN_CATALOG_NOTES.md）で全行を実品番に置き換え、耐力値は p025 の
許容荷重表に差し替えた。ここでは「型番仮が残っていない」「未確認の耐力値が
出ない」「幅別の支柱耐力が効く」ことを止める。
"""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all
from ashiba.master import load_master
from ashiba.structural import load_capacities

ROOT = Path(__file__).resolve().parents[1]


def qty_of_model(q, model_no):
    return sum(l.qty for l in q.lines if l.part.model_no == model_no)


class TestNikkenNd1800Master(unittest.TestCase):
    def test_master_is_complete_and_from_catalog(self):
        m = load_master("nikken_nd1800")
        cats = {p.category for p in m.parts}
        for need in ("支柱", "布材", "踏板", "ジャッキ", "壁つなぎ", "筋交", "幅木",
                     "階段", "梁枠", "先行手摺", "朝顔", "踊り場", "ブラケット", "方杖"):
            self.assertIn(need, cats)
        self.assertEqual(m.span_lengths(), [1829, 1524, 1219, 914, 610])
        self.assertEqual(m.post_lengths(), [3600, 2700, 1800, 1350, 1125, 900, 675, 450])
        self.assertEqual(m.deck_widths_available(), {500, 240})
        self.assertEqual((m.koma_pitch, m.floor_height), (450, 1800))
        # 型番仮は1行も残っていない。全行にカタログページが書いてある
        self.assertFalse([p for p in m.parts if "型番仮" in p.note])
        # 出典はカタログのページ、カタログに無い品は利用者の資料（層間ネット KSK-HV。2026-10-24）か、ほかのメーカーの資料
        # （防音パネル・BG は日本セイフティーの製品ページ。2026-10-24）
        src = [p for p in m.parts if "カタログVol.10p" not in p.note and "利用者の資料" not in p.note
               and "メーカーの資料" not in p.note]
        self.assertFalse(src, src)

    def test_catalog_weights_are_the_real_ones(self):
        m = load_master("nikken_nd1800")
        by_no = {p.model_no: p for p in m.parts}
        self.assertEqual(by_no["NDP36N"].weight_kg, 11.07)       # p003
        self.assertEqual(by_no["NDT18"].weight_kg, 5.03)         # p005
        self.assertEqual(by_no["NDN6"].weight_kg, 15.40)         # p007
        self.assertEqual(by_no["NDH36"].weight_kg, 24.50)        # p011
        self.assertEqual(by_no["A752"].weight_kg, 3.96)        # p078（ジャッキベース。利用者の指定 2026-10-25）
        self.assertEqual(by_no["KS700"].weight_kg, 1.61)         # p100
        self.assertEqual(by_no["NDBS15"].weight_kg, 20.0)        # p018
        # アルミ軽量アサガオ直線部1スパン（受金具ALA7Nを除く）: 10.80×2+4.60+5.00+1.70+2.00×2+5.97×6
        self.assertAlmostEqual(by_no["ALA-1829"].weight_kg, 72.72)
        self.assertAlmostEqual(by_no["ALAC-SET"].weight_kg, 98.28)

    def test_capacity_rows_are_verified_with_catalog_page(self):
        caps = load_capacities("nikken_nd1800")
        self.assertTrue(caps)
        for (item, key), c in caps.items():
            with self.subTest(item=item, key=key):
                self.assertTrue(c.verified, (item, key))
                # 支保工の承認値は Vol.10 に無く、足場カタログ（ダーウィン 2024 の抜粋）から
                self.assertTrue("カタログVol.10 p" in c.source or "ダーウィン 2024" in c.source, c.source)
        self.assertEqual(caps[("支柱許容圧縮耐力", "0")].value, 11.0)
        self.assertEqual(caps[("支柱許容圧縮耐力[幅610]", "0")].value, 12.0)
        self.assertEqual(caps[("支柱許容圧縮耐力[幅914]", "0")].value, 12.0)
        self.assertEqual(caps[("ジャッキ許容支持力", "200")].value, 24.5)
        self.assertEqual(caps[("壁つなぎ許容耐力", "引張")].value, 4.41)


class TestNikkenNd1800Plan(unittest.TestCase):
    def test_example_solves_without_unverified_capacity_notice(self):
        r = solve_all(load_spec(ROOT / "examples" / "nikken_nd1800_rect.json"))
        self.assertEqual(r.model.master.series_id, "nikken_nd1800")
        self.assertTrue(all(s in (1829, 1524, 1219, 914, 610)
                            for e in r.model.plan.edges for s in e.spans))
        self.assertGreater(r.quantity.total_weight_kg, 0)
        # 確定値なので「未確認の耐力値」の要確認は出ない
        self.assertFalse([w for w in r.warnings if "未確認" in w[2]], r.warnings)
        self.assertFalse([n for n in r.quantity.notes if "マスタに該当部材がありません" in n],
                         r.quantity.notes)

    def test_post_capacity_uses_the_width_row(self):
        """内外の建地間隔610（NDT06）は W610 の 12.0kN/本 が効く."""
        r = solve_all(load_spec(ROOT / "examples" / "nikken_nd1800_rect.json"))
        self.assertEqual(r.model.post_row_spacing_mm, 610)
        post = r.structural.post
        self.assertEqual(post.allowable_kn, 12.0)
        self.assertIn("支柱", post.governing)
        self.assertTrue(post.verified)

    def test_jack_and_bottom_collar_follow_the_feet(self):
        r = solve_all(load_spec(ROOT / "examples" / "nikken_nd1800_rect.json"))
        q = r.quantity
        self.assertEqual(qty_of_model(q, "A752"), qty_of_model(q, "ECOPS"))
        self.assertEqual(qty_of_model(q, "NDBCN"), qty_of_model(q, "A752"))
        self.assertGreater(qty_of_model(q, "A752"), 0)

    def test_asagao_set_counts_two_hangers_per_post_and_no_hozue(self):
        import json
        import tempfile

        base = json.loads((ROOT / "examples" / "nikken_nd1800_rect.json").read_text(encoding="utf-8"))
        base["asagao"] = {"stages": 1}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        q = r.quantity
        self.assertGreater(qty_of_model(q, "ALA-1829"), 0)
        self.assertEqual(qty_of_model(q, "ALA7N"), 2 * r.model.plan.total_posts)
        self.assertFalse([n for n in q.notes if "朝顔方杖" in n], q.notes)
        # 「方杖不要」の本体行が方杖として拾われて本数が足されていた
        self.assertFalse([l for l in q.lines if "朝顔方杖" in l.note], [l.note for l in q.lines])
        # 出隅4箇所ぶんのコーナーセット
        self.assertEqual(qty_of_model(q, "ALAC-SET"), 4)
        # 端数スパン（1524/1219/610）にも専用セットがあるので「切り詰め」の注記は出ない
        self.assertFalse([w for w in r.warnings if "切り詰め" in w[2]], r.warnings)
        for sp in (1524, 1219, 610):
            self.assertGreater(qty_of_model(q, f"ALA-{sp}"), 0, sp)

    def test_long_face_is_not_filled_with_short_spans(self):
        from ashiba.plan_solver import solve_plan

        m = load_master("nikken_nd1800")
        plan = solve_plan([(0, 0), (30000, 0), (30000, 20000), (0, 20000)], m)
        for e in plan.edges:
            small = sum(1 for s in e.spans if s < 1829)
            self.assertLessEqual(small, 2, (e.edge_index, e.spans))
            self.assertGreaterEqual(e.standoff, 200)


if __name__ == "__main__":
    unittest.main()
