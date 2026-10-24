"""日建リース NDシステム1900（コマ475・階高1900）: ND1800と同じ根拠で解ける.

支柱・先行手すり・階段・張出ブラケットが専用品番（NHP/NHX/NHAL/NHBK）、
つなぎ材・布板・梁枠はND1800と共通。支柱の許容支持力は p040 の 9.8kN/本
（幅によらない）。
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


class TestNikkenNd1900(unittest.TestCase):
    def test_master_is_complete_and_from_catalog(self):
        m = load_master("nikken_nd1900")
        self.assertEqual((m.koma_pitch, m.floor_height), (475, 1900))
        self.assertEqual(m.span_lengths(), [1829, 1524, 1219, 914, 610])
        self.assertEqual(m.post_lengths(), [3800, 2850, 1900, 1425, 950, 475])
        self.assertEqual(m.deck_widths_available(), {500, 240})
        self.assertFalse([p for p in m.parts if "型番仮" in p.note])
        self.assertFalse([p for p in m.parts if "カタログVol.10p" not in p.note and "利用者の資料" not in p.note
                              and "メーカーの資料" not in p.note])
        by_no = {p.model_no: p for p in m.parts}
        self.assertEqual(by_no["NHP38N"].weight_kg, 11.60)      # p026
        self.assertEqual(by_no["NHX18"].weight_kg, 6.50)        # p029
        self.assertEqual(by_no["NHAL4519K"].weight_kg, 13.40)   # p032
        self.assertEqual(by_no["NHBK06H"].weight_kg, 8.26)      # p037
        # 階高1.9mの朝顔はSW型主材（+0.1kg×2）
        self.assertAlmostEqual(by_no["ALA-1829W"].weight_kg, 72.92)

    def test_capacity_is_verified_and_width_independent(self):
        caps = load_capacities("nikken_nd1900")
        self.assertTrue(all(c.verified for c in caps.values()))
        self.assertEqual(caps[("支柱許容圧縮耐力", "0")].value, 9.8)
        self.assertNotIn(("支柱許容圧縮耐力[幅610]", "0"), caps)

    def test_example_solves_with_the_1900_grid(self):
        r = solve_all(load_spec(ROOT / "examples" / "nikken_nd1900_rect.json"))
        self.assertEqual(r.model.master.series_id, "nikken_nd1900")
        self.assertEqual(r.model.master.floor_height, 1900)
        self.assertFalse([w for w in r.warnings if "未確認" in w[2]], r.warnings)
        self.assertFalse([n for n in r.quantity.notes if "マスタに該当部材がありません" in n],
                         r.quantity.notes)
        post = r.structural.post
        self.assertEqual(post.allowable_kn, 9.8)
        self.assertTrue(post.ok)
        q = r.quantity
        self.assertGreater(qty_of_model(q, "NHP38N"), 0)
        self.assertEqual(qty_of_model(q, "ND752P"), qty_of_model(q, "NDBCN"))
        self.assertEqual(qty_of_model(q, "ALA7N"), 2 * r.model.plan.total_posts)   # 朝顔受けはコーナー支柱に無い
        self.assertEqual(qty_of_model(q, "ALAC-SETW"), 4)

    def test_1800_and_1900_parts_cannot_be_mixed(self):
        from ashiba.master import SeriesLockError

        m18 = load_master("nikken_nd1800")
        m19 = load_master("nikken_nd1900")
        with self.assertRaises(SeriesLockError):
            m18.assert_series(m19.by_category("支柱")[0])


if __name__ == "__main__":
    unittest.main()
