"""仮設通路（日工セック ライトブリッジ。利用者の指定 2026-10-29: 次足場はこういうのにも対応できるようにしたい）."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.interior_stage import stage_params  # noqa: E402
from ashiba.master import load_master  # noqa: E402
from ashiba.walkways import choose_model, load_walkway_models, solve_walkway, walkway_params, walkway_report  # noqa: E402

M = load_master("nikken_nd1800")


def walk(end, **kw):
    return solve_walkway({"name": "地中梁通路", "start_mm": [0, 0], "end_mm": end, "deck_mm": 1800, **kw}, M)


class TestModels(unittest.TestCase):
    def test_catalog_rows(self):
        ms = {m.model: m for m in load_walkway_models()}
        self.assertEqual(set(ms), {"LB-2439", "LB-3849", "LB-4556", "LB-4572"})
        self.assertEqual((ms["LB-4572"].min_mm, ms["LB-4572"].max_mm), (4500, 7200))
        self.assertTrue(all(m.deck_w_mm == 660 and m.overall_w_mm == 915 for m in ms.values()))

    def test_lightest_model_in_range(self):
        self.assertEqual(choose_model(3000).model, "LB-2439")
        self.assertEqual(choose_model(5000).model, "LB-4556")   # LB-4572 も入るが重い
        self.assertEqual(choose_model(6500).model, "LB-4572")
        self.assertIsNone(choose_model(8000))
        self.assertIsNone(choose_model(3000, name="LB-4572"))


class TestWalkway(unittest.TestCase):
    def test_islands_stair_at_the_far_bay(self):
        """始めの島は2スパンで階段は奥の升目（通路の付く升目は床）、終わりの島は1スパンで昇降なし."""
        for end in ([5000, 0], [3000, 4000], [-2000, -4000], [0, 5000]):
            r = walk(end)
            a, b = r.islands
            self.assertEqual((a.spans_u, a.spans_v, a.access), ([1829, 1829], [1219], "階段"), end)
            self.assertEqual((b.spans_u, b.spans_v, b.access), ([1829], [1219], "なし"), end)
            self.assertFalse(stage_params(b, master=M)["ladOn"])
            # 島の始めの角（階段の升目）は通路から遠い側、u は通路へ向かう
            L = math.dist((0, 0), end)
            d = (end[0] / L, end[1] / L)
            far = -(a.origin[0] * d[0] + a.origin[1] * d[1])
            self.assertAlmostEqual(far, 3658, delta=2, msg=end)
            self.assertAlmostEqual(a.u[0] * d[0] + a.u[1] * d[1], 1.0, places=6)

    def test_end_island_has_no_stair_or_ladder(self):
        r = walk([5000, 0])
        cats = {q[0] for q in r.islands[1].quantity}
        self.assertNotIn("階段", cats)
        self.assertNotIn("はしご", cats)
        self.assertTrue(any("通路から渡る" in c.message for c in r.islands[1].checks))

    def test_checks_and_quantity(self):
        r = walk([5000, 0])
        self.assertTrue(r.ok)
        self.assertEqual(r.model.model, "LB-4556")
        st = {c.item: c.status for c in r.checks}
        self.assertEqual((st["通路の長さ"], st["積載"], st["勾配"]), ("OK", "OK", "OK"))
        q = [x for x in r.quantity if x[0].startswith("仮設通路")]
        self.assertEqual([x[0] for x in q][:2], ["仮設通路", "仮設通路の手すり"])
        self.assertEqual(q[1][2], 2)
        self.assertIn("250kg", next(c.message for c in r.checks if c.item == "積載"))

    def test_walkway_edge_rails_are_removed(self):
        """通路の取り付く辺は出入口: 島の短手の外周の手すり・中桟は1辺分（2本）、幅木 1枚。部品にも開ける指定を渡す
        （実機 2026-10-29: 3D で島の手すりが通路の入口をふさいでいた）."""
        r = walk([5000, 0])
        for st in r.islands:
            self.assertTrue(st.open_end)
            self.assertTrue(stage_params(st, master=M)["gOpenE"])
            rails = sum(n for c, d, n, why in st.quantity if c == "布材" and d == 1219 and "外周の手すり" in why)
            toes = sum(n for c, d, n, why in st.quantity if c == "幅木" and d == 1219)
            self.assertEqual((rails, toes), (2, 1), st.name)
        self.assertTrue(any("出入口で除く" in q[3] for q in r.quantity))
        xml = (ROOT / "gdl" / "hsf" / "ashiba_stage" / "paramlist.xml").read_text(encoding="utf-8")
        self.assertIn('Name="gOpenE"', xml)

    def test_too_long_and_too_short(self):
        r = walk([9000, 0])
        self.assertFalse(r.ok)
        msg = next(c.message for c in r.checks if c.item == "通路の長さ")
        self.assertIn("2本に分ける", msg)
        self.assertNotIn("仮設通路", [x[0] for x in r.quantity])
        short = walk([2000, 0])
        self.assertIn("足場板", next(c.message for c in short.checks if c.item == "通路の長さ"))

    def test_slope(self):
        r = walk([5000, 0], end_deck_mm=2400)
        c = next(c for c in r.checks if c.item == "勾配")
        self.assertEqual(c.status, "WARN")            # 600/5000 = 12%
        self.assertIn("日工セック", c.message)
        self.assertEqual(r.islands[1].deck_mm, 2400)
        self.assertEqual(next(c for c in walk([5000, 0], end_deck_mm=1900).checks if c.item == "勾配").status, "OK")

    def test_ends_follow_the_island_floors(self):
        """島の床はコマの段に合う（2100 → 2015）。通路の両端はその高さに掛ける（実機 2026-10-29: 端が 85mm 浮いていた）."""
        r = walk([5000, 0], end_deck_mm=2100)
        self.assertEqual(r.islands[1].deck_mm, 2015)
        self.assertEqual(r.end_deck_mm, 2015)
        self.assertAlmostEqual(walkway_params(r)["zEnd"], 2.015)
        self.assertTrue(any("2100 → 2015" in n for n in r.notes))
        self.assertFalse(any("始めの島の床" in n for n in r.notes))

    def test_params_and_report(self):
        r = walk([0, 5000], base_mm=-1500)
        p = walkway_params(r)
        self.assertAlmostEqual(p["faceAng"], 90.0)
        self.assertAlmostEqual(p["wkL"], 5.0)
        self.assertAlmostEqual(p["zDeck"], 0.3)
        self.assertEqual(p["wkModel"], "LB-4556")
        rep = walkway_report(r)
        self.assertIn("## 数量", rep)
        self.assertIn("4点吊り", rep)
        self.assertIn("出入口", rep)


class TestWalkwayPart(unittest.TestCase):
    def test_part_params_match(self):
        xml = (ROOT / "gdl" / "hsf" / "ashiba_walkway" / "paramlist.xml").read_text(encoding="utf-8")
        for k in walkway_params(walk([5000, 0])):
            self.assertIn(f'Name="{k}"', xml, k)
        self.assertIn('<PenColor Name="penEquip">', xml)

    def test_registered_everywhere(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS
        from ashiba.tapir_adapter import is_ashiba_part

        self.assertTrue(is_ashiba_part("ashiba_walkway_12345678"))
        self.assertIn("仮設通路", dict(PANEL_GROUPS)["直す"])
        self.assertTrue(any(a.script == "walkway_run.py" for a in ACTIONS))
        self.assertIn('"ashiba_walkway"', (ROOT / "scripts" / "build_dist_gsm.py").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "gdl" / "ashiba_walkway.gsm").exists())


if __name__ == "__main__":
    unittest.main()
