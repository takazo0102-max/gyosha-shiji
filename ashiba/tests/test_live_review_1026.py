"""2026-10-26 の実機の指摘（利用者: リサーチして しっかり確認してよ・・ 単管足場の位置も屋上の渡りも適当だな）で直したところ."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, solve_groups
from ashiba.roof_bridges import RAMP_MAX_DEG, RAMP_PLAIN_DEG, STEP_RISE_MM, bridge_profile

SQ = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
# 利用者の建物の形（南面だけ本足場、東面は下屋の単管抱き足場、北・西は一側足場。屋根は東の下屋 3.0m）
USER = {"outline_mm": SQ, "module": "inch", "scaffold_width_mm": 610, "eaves_height_mm": 15400,
        "face_eaves_mm": {"東面": 3000}, "face_forms": "東面=単管抱き足場;北面=一側足場;西面=一側足場"}


class TestHugMeetsItsNeighbours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = solve_groups(USER)
        cls.hug = next(r for lb, r in cls.g if "抱き" in lb).model
        cls.rigid = [r.model for lb, r in cls.g if "抱き" not in lb]

    def test_corner_posts_are_the_neighbours_posts(self):
        # 単管の始点・終点の建地は、隣の組（本足場・一側足場）の端の建地と同じ位置（70 ずれて2本立っていた）
        (ep,) = self.hug.plan.edges
        ends = [p for m in self.rigid for e in m.plan.edges for p in (e.start_post, e.end_post)]
        for pt in (ep.start_post, ep.end_post):
            self.assertLess(min(math.dist(pt, q) for q in ends), 1.0, pt)

    def test_shared_corner_posts_are_drawn_once(self):
        self.assertEqual(self.hug.skip_end_posts, {(1, "s"), (1, "e")})

    def test_tube_spans_stay_within_the_law(self):
        (ep,) = self.hug.plan.edges
        self.assertTrue(all(300 <= s <= 1800 for s in ep.spans), ep.spans)       # 安衛則571条一号 1.85m 以下
        self.assertAlmostEqual(sum(ep.spans), ep.scaffold_length, delta=1.0)

    def test_hug_decks_match_the_main_scaffold(self):
        main = next(m for m in self.rigid if m.config.scaffold_form == "本足場")
        lv = self.hug.elevation_of(1).level_heights
        self.assertTrue(set(lv) <= set(main.elevation.level_heights), (lv, main.elevation.level_heights))

    def test_lean_to_hug_stops_under_the_eaves_with_eave_rails(self):
        # 下屋 3.0m の面: 最上段の床は軒の下、軒先から 450・900 に手すり、建地はその上まで（床が 4.63m に出ていた）
        e = self.hug.elevation_of(1)
        self.assertLessEqual(max(e.level_heights), 3000 + 300)
        self.assertEqual(e.eave_rails_mm, [3450, 3900])
        self.assertGreaterEqual(e.total_height, 3900 + 100)
        self.assertLess(e.total_height, 5000)                       # 建物全体の高さ（11m）で拾わない


class TestConvergedStandoffs(unittest.TestCase):
    def test_groups_agree_on_every_corner(self):
        g = solve_groups(USER)
        own = {e.edge_index: e.standoff for _l, r in g if "上段" not in _l for e in r.model.plan.edges}
        for lb, r in g:
            if "上段" in lb:
                continue
            for e in r.model.plan.edges:
                for adj in ((e.edge_index - 1) % 4, (e.edge_index + 1) % 4):
                    self.assertAlmostEqual(r.model.plan.standoffs[adj], own[adj], delta=0.5, msg=(lb, adj))


class TestRoofBridgeProfile(unittest.TestCase):
    def _segments(self, prof, kinds):
        return list(zip(prof, prof[1:], kinds))

    def test_roof_higher_rises_before_the_building_face(self):
        # 実機の値: 足場の床 8681・屋上 9000・離れ 310。高低差は躯体の外面（y=310）までに取り、屋上の上は平ら
        prof, kinds, _n = bridge_profile(8681, 9000, 310, 0, 610)
        for (y0, z0), (y1, z1), k in self._segments(prof, kinds):
            if y1 > 310 + 1:
                self.assertEqual((z0, z1, k), (9000, 9000, 0))
            if k in (1, 2):
                ang = math.degrees(math.atan2(abs(z1 - z0), y1 - y0))
                self.assertLessEqual(ang, RAMP_MAX_DEG + 0.01)        # 安衛則552条 30°以下
                self.assertEqual(k, 2 if ang > RAMP_PLAIN_DEG else 1)  # 15°を超えれば踏桟
        self.assertGreaterEqual(prof[-1][0], 310 + 600)

    def test_roof_lower_steps_down_on_the_roof(self):
        prof, kinds, _n = bridge_profile(9000, 8100, 300, 0, 914)
        # 躯体の外面までは床の高さのまま、屋上の上で踏段を下りる（段がスラブより下に出ない）
        self.assertEqual(prof[:2], [(-300.0, 9000), (300, 9000)])
        steps = [s for s in self._segments(prof, kinds) if s[2] == 3]
        self.assertEqual(len(steps), 1)
        (y0, z0), (y1, z1), _k = steps[0]
        self.assertGreaterEqual(y0, 300)
        n = math.ceil(abs(z1 - z0) / STEP_RISE_MM)
        self.assertGreaterEqual((y1 - y0) / (n - 1), 200 - 0.1)       # 踏面 200 以上
        self.assertTrue(all(z >= 8100 for _y, z in prof))

    def test_parapet_is_crossed_above_its_top(self):
        prof, kinds, _n = bridge_profile(9300, 9000, 300, 300, 610)
        top = max(z for _y, z in prof)
        self.assertAlmostEqual(top, 9000 + 300 + 50)
        over = [y for y, z in prof if z == top]
        self.assertLessEqual(min(over), 300 - 50 + 0.1)
        self.assertGreaterEqual(max(over), 300 + 250 - 0.1)
        self.assertEqual(prof[-1][1], 9000)

    def test_bridge_carries_its_profile_to_the_part(self):
        from ashiba.attachments import bridge_placements

        r = solve_all({"outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]], "eaves_height_mm": 9000,
                       "module": "inch"})
        (b,) = r.model.roof_bridges
        (p,) = bridge_placements(r.model)
        self.assertEqual(len(p.params["prfY"].split(",")), len(b.profile))
        self.assertEqual(len(p.params["prfK"].split(",")), len(b.profile) - 1)
        self.assertAlmostEqual(p.params["brL"] * 1000, b.profile[-1][0])


class TestAttachmentsGoToTheirGroup(unittest.TestCase):
    def test_hoist_only_in_the_group_with_its_face(self):
        # 昇降機（辺0＝南面）は南面を建てる組にだけ渡す（ほかの組で「辺0は存在しません」と止まった。2026-10-26 実機）
        g = solve_groups({"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
                          "module": "inch", "face_forms": "東面=単管抱き足場;北面=一側足場;西面=一側足場",
                          "hoists": [{"edge_index": 0, "position_mm": 6000}]})
        with_hoist = [lb for lb, r in g if r.platforms.hoists]
        self.assertEqual(with_hoist, [""])


if __name__ == "__main__":
    unittest.main()
