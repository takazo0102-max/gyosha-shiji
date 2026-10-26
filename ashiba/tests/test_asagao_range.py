"""朝顔は配置では付けず、平面の線で範囲を足す（利用者の指定 2026-10-24: 配置で朝顔が勝手に配置される。なしして線で朝顔の
範囲追加できるようにして）・階段の位置で階段なし."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params
from ashiba.spec_form import ASAGAO_MODES, asagao_on_map, updated_asagao_faces

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

TALL = {"project_name": "足場計画", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 15000, "height_from_slabs": False, "module": "inch", "scaffold_width_mm": 900,
        "stairs": {"layout": "自動"}}
EVERY = ["南面", "東面", "北面", "西面"]


def _south(m):
    return next(e for e in m.plan.edges if m.face_name(e.edge_index) == "南面")


def _posts(ep):
    out = [0.0]
    for sp in ep.spans:
        out.append(out[-1] + sp)
    return out


class TestAsagaoOffByDefault(unittest.TestCase):
    def test_placement_puts_no_asagao_unless_asked(self):
        from run_from_archicad import asagao_off_by_default

        spec = asagao_off_by_default(dict(TALL))
        self.assertEqual(spec["asagao"], {"faces": "なし"})
        r = solve_all(spec)
        self.assertEqual(r.quantity.qty_of("朝顔"), 0)
        self.assertFalse(any(t.kind == "asagao" for t in r.model.wall_ties))
        self.assertFalse(any(line_params(r.model, e, stair_plan=r.stair_plan)["asagaoList"] for e in r.model.plan.edges))
        # 法規チェック#10 は付けていないことを知らせる
        law = next(c for c in r.checks if c.check_id == 10)
        # 付ける面が無いときは「どの面にもに設置。…には付けていません」と食い違わず、付けていないことだけを言う
        self.assertNotIn("に設置", law.message)
        self.assertIn("どの面", law.message)
        self.assertNotEqual(law.status, "OK")
        # 付ける面を書いたもの・「全部」・付けない指定（False）はそのまま
        self.assertEqual(asagao_off_by_default({**TALL, "asagao": {"faces": "南面"}})["asagao"], {"faces": "南面"})
        self.assertIs(asagao_off_by_default({**TALL, "asagao": False})["asagao"], False)
        self.assertEqual(asagao_off_by_default({**TALL, "asagao": {"stages": 2}})["asagao"], {"stages": 2, "faces": "なし"})
        full = solve_all({**TALL, "asagao": {"faces": "全部"}})
        self.assertIsNone(full.model.asagao_edges)
        self.assertGreater(full.quantity.qty_of("朝顔"), 0)


class TestAsagaoRange(unittest.TestCase):
    def setUp(self):
        self.full = solve_all({**TALL, "asagao": {"faces": "南面"}})
        ep = _south(self.full.model)
        self.posts = _posts(ep)
        self.a, self.b = self.posts[3], self.posts[7]
        self.r = solve_all({**TALL, "asagao": {"faces": f"南面[{self.a:.0f}-{self.b:.0f}]"}})

    def test_range_is_read_into_the_model(self):
        m = self.r.model
        ep = _south(m)
        self.assertEqual(m.asagao_edges, set())
        self.assertTrue(m.asagao_on(ep.edge_index))
        parts = m.asagao_parts(ep.edge_index)
        self.assertEqual(len(parts), 1)
        self.assertAlmostEqual(parts[0][0], self.a, delta=1.0)
        self.assertAlmostEqual(parts[0][1], self.b, delta=1.0)
        self.assertFalse(m.asagao_reaches(ep.edge_index, at_end=False))
        self.assertFalse(m.asagao_on(next(e.edge_index for e in m.plan.edges if m.face_name(e.edge_index) == "東面")))

    def test_drawing_cuts_outside_the_range(self):
        m = self.r.model
        ep = _south(m)
        p = line_params(m, ep, stair_plan=self.r.stair_plan, platforms=self.r.platforms)
        self.assertTrue(p["asagaoList"])
        cuts = [float(v) for v in p["asaCutList"].split(",")]
        self.assertEqual(cuts[:2], [0.0, round(self.a)])
        self.assertEqual(cuts[2], round(self.b))
        self.assertAlmostEqual(cuts[3], self.posts[-1], delta=1.0)
        # 面全体の朝顔は切り欠かない（前の面に朝顔が無い隅だけ、コーナー部を付けない印「0,0」）
        pf = line_params(self.full.model, _south(self.full.model), stair_plan=self.full.stair_plan,
                         platforms=self.full.platforms)
        self.assertEqual(pf["asaCutList"], "0,0")

    def test_quantity_and_ties_only_in_the_range(self):
        q_full = self.full.quantity.qty_of("朝顔")
        q_part = self.r.quantity.qty_of("朝顔")
        self.assertGreater(q_part, 0)
        self.assertLess(q_part, q_full)
        from ashiba.ties import _asagao_ties

        m = self.r.model
        ties = _asagao_ties(m)            # 取付部の壁つなぎ（格子の金具と同じ位置なら兼ねる）
        self.assertTrue(ties)
        for t in ties:
            self.assertEqual(m.face_name(t.edge_index), "南面")
            self.assertTrue(self.a - 1.0 <= t.position_mm <= self.b + 1.0, t)

    def test_whole_face_wins_over_a_range(self):
        r = solve_all({**TALL, "asagao": {"faces": f"南面・南面[{self.a:.0f}-{self.b:.0f}]"}})
        self.assertIsNone(r.model.asagao_parts(_south(r.model).edge_index))


class TestAsagaoOnThePlan(unittest.TestCase):
    """朝顔の平面の表記（利用者の指定 2026-10-24: 朝顔の平面図に表記して）: 張り出しに斜線、範囲ごとに文字、ラベルは範囲の中."""

    def test_plan_script_draws_hatch_and_a_label_per_range(self):
        src = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        blk = src[src.index("! 朝顔の突出範囲"):src.index("pen penLine", src.index("! 朝顔の突出範囲"))]
        self.assertIn("45° の斜線", blk)
        self.assertIn("line2 ahX0, ahY0, ahX1, ahY1", blk)
        self.assertIn('tdt = "朝顔 突出"', blk)
        self.assertIn("（範囲 ", blk)
        self.assertIn("next isg", blk[blk.index('tdt = "朝顔 突出"'):])            # 範囲（連続区間）ごと
        self.assertIn("hoIn = 1", blk)                                                # 「朝顔切欠」は昇降機の所だけ

    def test_label_points_into_the_range(self):
        from ashiba.plan_labels import plan_label_items

        full = solve_all({**TALL, "asagao": {"faces": "南面"}})
        ep = _south(full.model)
        posts = _posts(ep)
        a, b = posts[-4], posts[-2]
        r = solve_all({**TALL, "asagao": {"faces": f"南面[{a:.0f}-{b:.0f}]"}})
        x, _y = next((x, y) for x, y, t in plan_label_items(r.model, r.stair_plan) if t.startswith("朝顔"))
        x0 = float(_south(r.model).start_post[0])
        self.assertTrue(x0 + a - 1.0 <= x * 1000.0 <= x0 + b + 1.0, (x, x0 + a, x0 + b))     # ラベルの点は m


class TestUpdatedFacesWithRanges(unittest.TestCase):
    L = {"南面": 24000.0, "東面": 10000.0, "北面": 24000.0, "西面": 10000.0}

    def test_add_and_remove_ranges(self):
        add, rem = ASAGAO_MODES[0], ASAGAO_MODES[1]
        self.assertEqual(updated_asagao_faces("", EVERY, ["南面[3600-9000]"], add, self.L), "南面[3600-9000]")
        # 続く範囲はまとめる・面の全長になれば面の名前
        self.assertEqual(updated_asagao_faces("南面[3600-9000]", EVERY, ["南面[9000-12000]"], add, self.L),
                         "南面[3600-12000]")
        self.assertEqual(updated_asagao_faces("南面[3600-9000]", EVERY, ["南面[0-3600]", "南面[9000-24000]"], add, self.L),
                         "南面")
        # 面全体から一部を外す
        self.assertEqual(updated_asagao_faces("南面", EVERY, ["南面[3600-9000]"], rem, self.L),
                         "南面[0-3600]・南面[9000-24000]")
        self.assertEqual(updated_asagao_faces("全部", EVERY, ["東面"], rem, self.L), "南面・北面・西面")
        self.assertEqual(updated_asagao_faces("南面[3600-9000]", EVERY, ["南面"], rem, self.L), "なし")
        self.assertEqual(updated_asagao_faces("南面[3600-9000]・東面", EVERY, [], ASAGAO_MODES[2], self.L), "全部")
        self.assertEqual(asagao_on_map("南面[3600-9000]・東面", EVERY, self.L),
                         {"南面": [(3600.0, 9000.0)], "東面": [(0.0, 10000.0)]})


class TestPickRangeByLine(unittest.TestCase):
    """線 → 面と、線がかかるスパンの区間（元の面の始点から。面の途中で切り替えた区間の部品は faceOff を足す）."""

    SOUTH = {"edge_index": 0, "face": "南面", "start_post": [0.0, 0.0], "end_post": [9145.0, 0.0],
             "gdl_params": {"spanList": "1829,1829,1829,1829,1829", "rowW": 0.914}}

    def test_line_snaps_to_spans(self):
        from asagao_range_run import picked_ranges

        keys, lengths, missed = picked_ranges([self.SOUTH], [(None, [((1900.0, -400.0), (5400.0, -400.0))])])
        self.assertEqual(keys, ["南面[1829-5487]"])
        self.assertEqual(lengths, {"南面": 9145.0})
        self.assertEqual(missed, [])
        keys, _l, _m = picked_ranges([self.SOUTH], [(None, [((-200.0, -400.0), (9300.0, -400.0))])])
        self.assertEqual(keys, ["南面"])
        piece = {**self.SOUTH, "gdl_params": {**self.SOUTH["gdl_params"], "faceOff": 3.658, "faceLen": 20.0}}
        keys, lengths, _m = picked_ranges([piece], [(None, [((1900.0, -400.0), (5400.0, -400.0))])])
        self.assertEqual(keys, ["南面[5487-9145]"])
        self.assertEqual(lengths, {"南面": 20000.0})
        _k, _l, missed = picked_ranges([self.SOUTH], [(None, [((1900.0, 5000.0), (5400.0, 5000.0))])])
        self.assertEqual(len(missed), 1)

    def test_palette_has_the_button(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("朝顔の範囲", [a.title for a in ACTIONS])
        self.assertIn("朝顔の範囲", dict(PANEL_GROUPS)["直す"])
        self.assertTrue((ROOT / "scripts" / "asagao_range_run.py").exists())


class TestStairNone(unittest.TestCase):
    """階段の位置で階段なし（stairs の count 0。はしごも自動で足さない）."""

    def test_remove_one_or_all(self):
        from stair_move_run import ALL, positions_without

        towers = [{"edge_index": 0, "start_mm": 1829.0, "span_count": 2},
                  {"edge_index": 2, "start_mm": 3658.0, "span_count": 2}]
        faces = {0: "南面", 2: "北面"}
        labels = ["a", "b"]
        self.assertEqual(positions_without(towers, faces, labels, "a"),
                         [{"face": "北面", "start_mm": 3658.0, "span_count": 2}])
        self.assertEqual(positions_without(towers, faces, labels, ALL), [])

    def test_no_stairs_solves_without_towers(self):
        r = solve_all({**TALL, "stairs": {"positions": [], "count": 0}})
        self.assertEqual(len(r.stair_plan.towers), 0)


if __name__ == "__main__":
    unittest.main()
