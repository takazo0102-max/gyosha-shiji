"""昇降機の機種表・部品 ashiba_hoist（利用者の指定 2026-10-27: 建機サービスの図面から機種表にする・フロアーゲートを描いて
数える・機種ごとの形を3Dで描く・昇降機は別オブジェクトで配置できるように）."""

import json
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import HOIST_OBJECT, hoist_placements
from ashiba.cli import solve_all
from ashiba.hoist_models import FLOOR_GATES, hoist_model, load_hoist_models
from ashiba.hoist_objects import hoists_from_objects

ROOT = Path(__file__).resolve().parents[1]
BOX = {"project_name": "昇降機", "outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]],
       "eaves_height_mm": 9000, "series_id": "nikken_nd1800", "module": "inch"}


class TestCatalog(unittest.TestCase):
    def test_every_drawing_is_in_the_table(self):
        ms = load_hoist_models()
        for mid in ("KSE600C", "KSE900-5.4", "KSE-990", "HSL-900C2-7.2", "HSL-900B-5.4", "HSL950L2", "KRD800-5.4",
                    "KRD950-7.2", "NSE800", "HCE990GL", "SL-240B"):
            self.assertIn(mid, ms)
            self.assertTrue(ms[mid].source)
        self.assertEqual(hoist_model("kse900-5.4").cage_len_mm, 4800)
        self.assertEqual(hoist_model("KSE900-5.4").masts, 2)
        self.assertEqual(hoist_model("KSE600C").masts, 1)
        self.assertIsNone(hoist_model("なし"))

    def test_gate_opens_the_cage(self):
        # フロアーゲートは荷台の長さより広い有効開口のものを選んである（7.2 スパンは長い荷台）
        for m in load_hoist_models().values():
            if m.gate:
                self.assertIn(m.gate, FLOOR_GATES)
                if m.gate == "4.5":
                    self.assertLessEqual(m.cage_len_mm, FLOOR_GATES["7.2"]["opening_mm"])

    def test_generated_part_matches_the_table(self):
        vl = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "vl.gdl").read_text(encoding="utf-8")
        d1 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        for mid in load_hoist_models():
            self.assertIn(f'"{mid}"', vl)
            self.assertIn(f'if hoModel = "{mid}" then', d1)
        # 値の一覧の1行が長いと Tapir がパラメータを読み書きできない（6機種ごとに改行）
        self.assertTrue(all(len(line) < 160 for line in vl.splitlines()))


class TestHoistInput(unittest.TestCase):
    def test_model_fills_the_cage_load_and_ties(self):
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE900-5.4",
                                          "landing_levels": [2, 4]}]})
        h = r.platforms.hoists[0]
        self.assertEqual((h.cage_width_mm, h.cage_depth_mm), (4800, 1030))
        self.assertAlmostEqual(h.load_kn, 900 * 9.80665 / 1000)
        notes = [str(n) for n in r.quantity.notes]
        self.assertTrue([n for n in notes if "昇降機 本体 KSE-900 5.4m" in n])
        self.assertTrue([n for n in notes if "フロアーゲート 7.2スパン" in n and "（2）" in n])
        self.assertFalse([n for n in notes if "開閉式手すり" in n and "マスタにありません" in n])

    def test_unknown_model_is_an_input_error(self):
        from ashiba.cli import InputError

        with self.assertRaises(InputError):
            solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "XYZ"}]})

    def test_placement_sits_on_the_outer_row(self):
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE-990",
                                          "landing_levels": [3]}]})
        pls = hoist_placements(r.model, r.platforms)
        self.assertEqual(len(pls), 1)
        p = pls[0]
        self.assertEqual(p.part, HOIST_OBJECT)
        ep = r.model.plan.edges[0]
        row = r.model.row_spacing_of(0)
        self.assertAlmostEqual(p.y_mm, ep.start_post[1] - row, delta=1)
        self.assertEqual(p.params["hoModel"], "KSE-990")
        self.assertEqual(p.params["landLevels"], "3")
        self.assertEqual(len(p.params["landList"].split(",")), 1)


class TestModelChecks(unittest.TestCase):
    def _issues(self, spec):
        r = solve_all(spec)
        return [i.message for i in r.platforms.issues if i.kind == "昇降機"]

    def test_lift_over_the_model_is_ng(self):
        # SL-240B は揚程 60m。到達 65m（足場の上の控えの検討は別）は機種では届かない
        msgs = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "SL-240B",
                                                "reach_height_mm": 65000}]})
        self.assertTrue([m for m in msgs if "最大揚程60m" in m])
        ok = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE900-5.4"}]})
        self.assertFalse([m for m in ok if "最大揚程" in m])

    def test_goods_only_hoist_says_no_riders(self):
        msgs = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "SL-240B"}]})
        self.assertTrue([m for m in msgs if "荷揚げ専用で人は乗れません" in m])
        ok = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE-990"}]})
        self.assertFalse([m for m in ok if "荷揚げ専用" in m])


class TestReadPlacedObjects(unittest.TestCase):
    def test_object_snaps_to_the_nearest_face(self):
        from ashiba.cli import solve_groups

        g = solve_groups(BOX)
        m = g[0][1].model
        e1 = next(e for e in m.plan.edges if e.edge_index == 1)       # 東面
        x = e1.start_post[0] + m.row_spacing_of(1) + 900            # 外側の列から 900 外
        y = e1.start_post[1] + 3000
        hs, notes = hoists_from_objects([(None, (x, y), {"hoModel": "KSE600L", "landLevels": "2,4"})], g)
        self.assertEqual(hs, [{"edge_index": 1, "position_mm": 3000.0, "model": "KSE600L", "landing_levels": [2, 4]}])
        far, n2 = hoists_from_objects([(None, (x + 20000, y), {"hoModel": "KSE600L"})], g)
        self.assertEqual(far, [])
        self.assertTrue(n2)


if __name__ == "__main__":
    unittest.main()
