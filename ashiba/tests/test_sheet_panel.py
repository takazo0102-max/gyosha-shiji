"""図面の右の帯（凡例・最大積載荷重・共通事項・注意・方位・キープラン）。利用者の指定 2026-10-23（例の仮設計画図に倣う）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.sheet_panel import (
    PANEL_W_MM, common_notes, max_load_rows, panel_content, scaffold_type_label, write_panel,
)

BASE = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000}


class TestContent(unittest.TestCase):
    def test_load_table_from_capacity(self):
        r = solve_all({**BASE, "module": "inch", "scaffold_width_mm": 914})
        self.assertEqual(max_load_rows(r.model),
                         [(scaffold_type_label(r.model), "250 kg", "370 kg")])      # 日建 914幅
        self.assertIn("W=914", scaffold_type_label(r.model))
        self.assertIn("500+240", scaffold_type_label(r.model))
        hug = solve_all({**BASE, "scaffold_form": "単管抱き足場"})
        self.assertNotIn("W=0", scaffold_type_label(hug.model))
        self.assertNotIn("W=-", scaffold_type_label(hug.model))
        a = solve_all({**BASE, "series_id": "shinwa_A"})
        self.assertEqual(max_load_rows(a.model)[0][1:], ("250 kg", "400 kg"))

    def test_common_notes_follow_the_plan(self):
        r = solve_all(dict(BASE))
        ns = common_notes(r.model, r.stair_plan)
        self.assertTrue(any("敷板" in n for n in ns))
        self.assertTrue(any("フルハーネス" in n for n in ns))
        self.assertTrue(any("垂直5m・水平5.5m" in n for n in ns))
        w = solve_all({**BASE, "series_id": "waku"})
        self.assertTrue(any("垂直9m・水平8m" in n for n in common_notes(w.model)))      # 枠組の壁つなぎ間隔
        h = solve_all({**BASE, "scaffold_form": "単管抱き足場", "ladders": 2})
        self.assertTrue(any("昇降用はしご 2箇所" in n for n in common_notes(h.model, h.stair_plan)))

    def test_kinds(self):
        r = solve_all(dict(BASE))
        texts = lambda k, **kw: [t["text"] for t in panel_content(k, r.model, r.stair_plan, **kw)["texts"]]
        plan = texts("plan")
        for want in ("安全帯を使用", "N", "凡例", "共通事項", "最大積載荷重（1層1スパン）"):
            self.assertIn(want, plan)
        self.assertNotIn("上下作業は禁止する", plan)
        cross = texts("cross", cuts=[{"label": "A", "start": (6000, -3000), "end": (6000, 11000)}])
        self.assertIn("上下作業は禁止する", cross)
        self.assertIn("Key Plan", cross)
        self.assertEqual(cross.count("A"), 2)                                    # 切断線の両端
        red = [t for t in panel_content("cross", r.model, cuts=[])["texts"] if t["red"]]
        self.assertTrue(red)
        # 帯の幅に収まる（線の x は 0〜帯の幅）
        xs = [x for pts in panel_content("plan", r.model, r.stair_plan)["lines"] for x, _ in pts]
        self.assertTrue(all(-0.1 <= x <= PANEL_W_MM + 0.1 for x in xs))

    def test_title_red_notes_and_level_numbers(self):
        from ashiba.elevation_sections import section_annotations, section_specs

        r = solve_all(dict(BASE))
        el = [t["text"] for t in panel_content("elev", r.model, r.stair_plan, title="南面・東面 足場立面図")["texts"]]
        self.assertEqual(el[0], "南面・東面 足場立面図")                         # 見出しが帯のいちばん上
        self.assertIn("・足場上下層において、上下作業禁止。", el)
        # 段の番号（1・2・3…）を段の高さの寸法の外に
        n = section_annotations(r.model, section_specs(r.model, "x")[0])
        nums = [t["text"] for t in n.texts if t.get("level_no")]
        self.assertEqual(nums, [str(i) for i in range(1, len(r.model.elevation.level_heights) + 1)])

    def test_sheet_with_faces_of_two_groups_lists_both_scaffolds(self):
        """面ごとに足場を替えた建物の立面図の帯は、図にある面の組ぶんの種類・荷重・注意を書く."""
        from ashiba.cli import solve_groups

        gs = solve_groups({**BASE, "face_forms": "東面=一側足場"})
        (m0, s0), (m1, s1) = [(r.model, r.stair_plan) for _l, r in gs]
        texts = [t["text"] for t in panel_content("elev", m0, s0, title="x", extra=[(m1, s1)])["texts"]]
        self.assertIn(scaffold_type_label(m0), texts)
        self.assertIn(scaffold_type_label(m1), texts)
        self.assertTrue(any("一側足場部分" in x for x in texts), texts)
        alone = [t["text"] for t in panel_content("elev", m0, s0, title="x")["texts"]]
        self.assertNotIn(scaffold_type_label(m1), alone)


class TestWrite(unittest.TestCase):
    def test_writes_to_the_layout_with_red_pen(self):
        r = solve_all(dict(BASE))

        class Client:
            def __init__(self):
                self.calls = []

            def find_red_pen(self):
                return 33

            def tapir(self, cmd, params):
                self.calls.append((cmd, params))
                key = next(iter(params))
                if cmd == "ChangeWindow":
                    return {}
                return {"elements": [{"elementId": {"guid": "x"}} for _ in params[key]]}

        c = Client()
        n = write_panel(c, "LAY", (841.0, 594.0), (20.0, 20.0, 20.0, 20.0), panel_content("plan", r.model, r.stair_plan))
        self.assertGreater(n, 10)
        self.assertEqual(c.calls[0][0], "ChangeWindow")
        texts = [t for cmd, p in c.calls if cmd == "CreateTexts" for t in p["textsData"]]
        warn = next(t for t in texts if t["text"] == "安全帯を使用")
        self.assertEqual(warn["pen"], 33)
        # 用紙の右上（右の余白の内）
        self.assertGreater(warn["coordinate"]["x"], (841.0 - 20.0 - PANEL_W_MM - 5.0) / 1000.0)
        self.assertLess(warn["coordinate"]["y"], (594.0 - 20.0) / 1000.0)



class TestSpot(unittest.TestCase):
    def test_top_right_then_below_then_none(self):
        from ashiba.elevation_sections import SheetPlan, panel_spot

        paper, margins = (841.0, 594.0), (20.0, 20.0, 20.0, 20.0)
        # 左に小さい図面1枚 → 右上
        small = SheetPlan(scale=100, positions_mm=[(30.0, 400.0)], paper_mm=paper)
        self.assertAlmostEqual(panel_spot(small, [(20000.0, 15000.0)], paper, margins, 150.0), 594.0 - 24.0)
        # 横いっぱいの図面が上に → 図面の下の右（表題欄の上）
        wide = SheetPlan(scale=100, positions_mm=[(30.0, 380.0), (420.0, 380.0)], paper_mm=paper)
        top = panel_spot(wide, [(38000.0, 18000.0), (38000.0, 18000.0)], paper, margins, 150.0)
        self.assertIsNotNone(top)
        self.assertLess(top, 380.0 - 15.0)
        # 高い図面で下も空いていない → None（右の余白を広げて並べ直す）
        tall = SheetPlan(scale=100, positions_mm=[(30.0, 100.0), (420.0, 100.0)], paper_mm=paper)
        self.assertIsNone(panel_spot(tall, [(38000.0, 46000.0), (38000.0, 46000.0)], paper, margins, 150.0))


if __name__ == "__main__":
    unittest.main()
