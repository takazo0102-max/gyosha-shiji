"""内部ステージ足場（利用者の指定 2026-10-24: 内部足場の内部ステージ足場の機能追加して検証して）."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.interior_stage import solve_stage, stage_params, stage_report
from ashiba.master import load_master
from ashiba.structural import load_capacities

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
RECT = [[0, 0], [12000, 0], [12000, 8000], [0, 8000]]


def solve(**kw):
    m = load_master("nikken_nd1800")
    item = {"name": "吹抜け", "corners_mm": RECT, "deck_mm": 6000, **kw}
    return solve_stage(item, m, load_capacities("nikken_nd1800"))


class TestInteriorStage(unittest.TestCase):
    def test_grid_fits_inside_with_long_spans(self):
        r = solve()
        self.assertEqual(r.spans_u, [1829] * 6)
        self.assertEqual(r.spans_v, [1829] * 4)
        self.assertLessEqual(r.length_u, 12000 - 300)
        self.assertEqual(r.deck_mm, 6000)
        self.assertEqual(r.levels[-1], 6000)
        # 中央に寄せる
        self.assertAlmostEqual(r.origin[0], (12000 - r.length_u) / 2, delta=1)

    def test_checks(self):
        r = solve()
        st = {c.item: c.status for c in r.checks}
        self.assertEqual(st["支柱の軸力"], "OK")
        self.assertEqual(st["作業床の積載"], "WARN")              # 1.5kN/m² × 1829² は 250kg/スパンを超える
        self.assertEqual(st["高さと短辺の比"], "OK")
        light = solve(live_kn_m2=0.6)
        self.assertEqual({c.item: c.status for c in light.checks}["作業床の積載"], "OK")
        tall = solve(corners_mm=[[0, 0], [12000, 0], [12000, 2500], [0, 2500]], deck_mm=12000)
        self.assertEqual({c.item: c.status for c in tall.checks}["高さと短辺の比"], "WARN")
        heavy = solve(live_kn_m2=6.0)
        self.assertEqual({c.item: c.status for c in heavy.checks}["支柱の軸力"], "NG")
        self.assertFalse(heavy.ok)

    def test_quantity_and_report(self):
        r = solve()
        q = {(c, d, why): n for c, d, n, why in r.quantity}
        self.assertEqual(q[("ジャッキ", 0, "内部ステージのジャッキベース")], 7 * 5)
        decks = sum(n for c, d, n, why in r.quantity if c == "踏板")
        self.assertEqual(decks, 6 * 4 * 4)                     # 1829 を 500×3＋240×1 で埋める
        txt = stage_report(r)
        self.assertIn("## 検証", txt)
        self.assertIn("支柱の軸力", txt)
        p = stage_params(r)
        self.assertEqual(p["spanU"], "1829,1829,1829,1829,1829,1829")
        self.assertAlmostEqual(p["deckH"], 6.0)

    def test_deck_is_the_nearest_level(self):
        r = solve(deck_mm=4000)
        self.assertLessEqual(abs(r.deck_mm - 4000), 300)
        self.assertEqual(r.levels[-1], r.deck_mm)

    def test_too_small(self):
        with self.assertRaises(ValueError):
            solve(corners_mm=[[0, 0], [500, 0], [500, 500], [0, 500]])

    def test_guides_to_corners_and_part(self):
        from interior_stage_run import corners_of

        self.assertEqual(corners_of([(None, [((0.0, 0.0), (5.0, 3.0))])]), [[0.0, 0.0], [5.0, 0.0], [5.0, 3.0], [0.0, 3.0]])
        poly = [(None, [((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (4.0, 2.0)), ((4.0, 2.0), (0.0, 2.0)), ((0.0, 2.0), (0.0, 0.0))])]
        self.assertEqual(len(corners_of(poly)), 4)
        self.assertTrue((ROOT / "gdl" / "ashiba_stage.gsm").exists())
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_stage" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("最上段の全面の作業床", d3)
        self.assertNotIn(" LV ", d3)                          # 配列 lv と大文字小文字で衝突しない名前


if __name__ == "__main__":
    unittest.main()


class TestShoringStage(unittest.TestCase):
    """型枠支保工として使う内部ステージ（利用者の指定 2026-10-28: 型枠支保工で使う、内部足場はステージ）."""

    def shore(self, **kw):
        return solve(**{"deck_mm": 2800, "use": "支保工", "slab_mm": 200, "ceiling_mm": 4400, **kw})

    def test_design_load_is_rc_plus_form_plus_live(self):
        r = self.shore()
        self.assertEqual(r.use, "支保工")
        # 23.5×0.2＋0.39＋1.47（手引: 2400kg/m³・型枠 40kg/m²・積載 150kg/m²）
        self.assertAlmostEqual(r.design_kn_m2, 6.56, places=2)
        items = [c.item for c in r.checks]
        self.assertNotIn("支柱の軸力", items)          # 足場の軸力は支保工の軸力に置き換える
        self.assertIn("支保工の支柱の軸力", items)

    def test_post_load_against_the_approval_by_tie_method(self):
        st = lambda r: {c.item: c.status for c in r.checks}["支保工の支柱の軸力"]
        # 1829×1829 で 6.56kN/m² → 22.6kN/本。ND1800 は片方向つなぎ材 18kN・両方向 25kN
        self.assertEqual(st(self.shore()), "NG")
        self.assertEqual(st(self.shore(tie="両方向つなぎ材")), "OK")
        self.assertEqual(st(self.shore(slab_mm=120)), "OK")

    def test_uhead_jack_and_notification(self):
        r = self.shore()
        self.assertEqual(r.uhead_ext_mm, 4400 - 175 - r.top_mm)
        st = {c.item: c.status for c in r.checks}
        self.assertEqual(st["大引受けジャッキ"], "OK")
        self.assertEqual(st["設置届"], "WARN")             # 支柱高さ 3.5m 以上
        self.assertEqual(st["水平つなぎ"], "OK")
        # 支柱の積み方を天井に合わせて選ぶ（繰出し 0〜350）
        for ceil in (3500, 5200, 6100):
            r2 = self.shore(ceiling_mm=ceil)
            self.assertTrue(0 <= r2.uhead_ext_mm <= 350, (ceil, r2.uhead_ext_mm))
            lv = sorted(r2.levels + r2.upper_levels + [r2.top_mm])
            self.assertLessEqual(max(b - a for a, b in zip(lv, lv[1:])), 2000)    # 水平つなぎは 2m 以内ごと
        low = self.shore(ceiling_mm=2900)                  # どの積み方でも支柱が大引に当たる
        self.assertEqual({c.item: c.status for c in low.checks}["大引受けジャッキ"], "NG")

    def test_quantity_and_horizontal_load(self):
        r = self.shore()
        q = {name: n for name, _, n, _ in r.quantity}
        posts = (len(r.spans_u) + 1) * (len(r.spans_v) + 1)
        self.assertEqual(q["大引受けジャッキ"], posts)
        self.assertEqual(q["大引"], len(r.spans_v) + 1)
        h = next(c for c in r.checks if c.item == "支保工の水平荷重")
        self.assertIn("5.0%", h.message)
        self.assertTrue(any("2段以上" in n for n in r.notes))
        self.assertIn("型枠支保工", stage_report(r))


class TestStairStage(unittest.TestCase):
    """階段の上に組む内部足場（利用者の指定 2026-10-28: 内部足場は階段でよく使う）."""

    def stair(self, **st):
        m = load_master("nikken_nd1800")
        item = {"name": "階段室", "corners_mm": [[0, 0], [6000, 0], [6000, 2800], [0, 2800]], "deck_mm": 3000,
                "stair": {"axis": "u", "from_mm": 800, "tread_mm": 250, "riser_mm": 180, "steps": 16, **st}}
        return solve_stage(item, m, load_capacities("nikken_nd1800"))

    def test_posts_shorten_by_the_step_and_jacks_take_the_rest(self):
        r = self.stair()
        koma = 450
        for f in r.stair_feet:
            # 支柱の下端（段＋敷板＋ジャッキ）が平らな床の支柱とコマでそろう
            bottom = f["z_mm"] + f["shim"] * 35 + f["jack_mm"]
            self.assertEqual((bottom - r.jack_mm) % koma, 0, f)
            self.assertEqual(bottom + sum(f["posts"]), r.top_mm)
            self.assertLessEqual(f["shim"], 2)
        flat = r.stair_feet[0]
        self.assertEqual(flat["z_mm"], 0)
        self.assertEqual(flat["posts"], r.posts)

    def test_quantity_counts_stair_posts_and_shims(self):
        r = self.stair()
        q = r.quantity
        n_posts = (len(r.spans_u) + 1) * (len(r.spans_v) + 1)
        posts = [(d, n) for c, d, n, _ in q if c == "支柱"]
        per_row = len(r.spans_v) + 1
        want = sum(len(f["posts"]) for f in r.stair_feet) * per_row
        self.assertEqual(sum(n for _, n in posts), want)
        self.assertEqual(sum(n for c, _, n, _ in q if c == "ジャッキ"), n_posts)
        shims = sum(f["shim"] for f in r.stair_feet) * per_row
        self.assertEqual(sum(n for c, _, n, _ in q if c == "敷板"), shims)

    def test_checks_flag_nosing_and_shims(self):
        r = self.stair()
        st = {c.item: c.status for c in r.checks}
        self.assertIn(st["階段の上の支柱"], ("OK", "WARN"))
        self.assertEqual(st.get("踏面の端"), "WARN")          # 2列目の支柱が蹴上げから 36mm
        self.assertTrue(any("根がらみは段ごと" in n for n in r.notes))
        self.assertIn("階段の上の支柱（列ごと）", stage_report(r))
        moved = self.stair(from_mm=750)
        self.assertNotIn("踏面の端", {c.item for c in moved.checks})
