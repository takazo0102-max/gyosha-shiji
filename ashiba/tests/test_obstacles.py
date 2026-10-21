"""庇・バルコニー・セットバックをかわす（利用者の指定 2026-10-21「セットバックや庇をかわせるような仕組みを作って」）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.master import load_master
from ashiba.obstacles import EAVE_CLEAR_MM, POST_R_MM, detect_eaves, detect_setbacks
from ashiba.geometry import build_outline
from ashiba.plan_solver import solve_plan

W, D = 12000, 8000
OUT = [[0, 0], [W, 0], [W, D], [0, D]]
BASE = {"outline_mm": OUT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800"}


def _floor(top, poly=None):
    return {"polygon_mm": poly or OUT, "top_mm": top, "thickness_mm": 200}


EAVE = {"polygon_mm": [[3000, -600], [6000, -600], [6000, 100], [3000, 100]], "top_mm": 3000, "thickness_mm": 150}
GROUND = {"polygon_mm": [[-8000, -8000], [W + 8000, -8000], [W + 8000, D + 8000], [-8000, D + 8000]],
          "top_mm": 0, "thickness_mm": 300}


def _south(r):
    return next(e for e in r.model.plan.edges if e.edge_index == 0)


class TestDetect(unittest.TestCase):
    def test_eave_slab_on_the_south_face(self):
        edges = build_outline(OUT).edges
        obs = detect_eaves(edges, [_floor(3000), EAVE])
        self.assertEqual(len(obs), 1)
        o = obs[0]
        self.assertEqual(o.edge_index, 0)
        self.assertAlmostEqual(o.start_mm, 3000, delta=300)
        self.assertAlmostEqual(o.end_mm, 6000, delta=300)
        self.assertAlmostEqual(o.projection_mm, 600, delta=50)
        self.assertAlmostEqual(o.bottom_mm, 2850)

    def test_detached_slab_is_not_an_eave(self):
        edges = build_outline(OUT).edges
        far = {"polygon_mm": [[3000, -3000], [6000, -3000], [6000, -1000], [3000, -1000]], "top_mm": 3000}
        self.assertEqual(detect_eaves(edges, [far]), [])

    def test_small_setback(self):
        edges = build_outline(OUT).edges
        upper = _floor(9000, [[0, 0], [W, 0], [W, D - 500], [0, D - 500]])
        sbs = detect_setbacks(edges, [_floor(3000), _floor(6000), upper], {0: 9000, 1: 9000, 2: 6000, 3: 9000})
        self.assertEqual([(s.edge_index, s.height_mm, s.upper_top_mm) for s in sbs], [(2, 6000, 9000)])
        self.assertAlmostEqual(sbs[0].depth_mm, 500, delta=60)


class TestPlanShift(unittest.TestCase):
    def test_face_min_moves_the_face_out_and_keeps_the_outline(self):
        m = load_master("nikken_nd1800")
        p0 = solve_plan(OUT, m)
        p = solve_plan(OUT, m, face_min={0: 725})
        south = next(e for e in p.edges if e.edge_index == 0)
        self.assertGreaterEqual(south.standoff, 725 - 1)
        self.assertEqual(p.outline.vertices, p0.outline.vertices)          # 躯体の外形は元のまま
        self.assertGreater(p.face_shift[0], 0)
        # 外側の支柱は躯体から離れ＋幅の位置（面の線から測る）
        self.assertAlmostEqual(south.start_post[1], -south.standoff, delta=1.0)


class TestSolveAll(unittest.TestCase):
    def test_eave_from_slabs_pushes_the_face_and_adds_brackets(self):
        r = solve_all({**BASE, "slabs": [GROUND, _floor(3000), _floor(6000), _floor(9000), EAVE]})
        s = _south(r)
        self.assertGreaterEqual(s.standoff, 600 + EAVE_CLEAR_MM + POST_R_MM - 1)
        self.assertEqual(len(r.model.obstacles), 1)                       # 地盤のスラブは張り出しではない
        inner = [b for b in r.brackets if b.edge_index == 0 and b.direction == "内"]
        self.assertTrue(inner)
        self.assertTrue(any("庇・バルコニーの先端をかわす" in w for w in r.model.plan.warnings))
        self.assertFalse(any(w.startswith("南面") and "落下防止材" in w for w in r.model.plan.warnings))

    def test_brackets_skip_the_eave_at_its_level(self):
        # 庇の下端 3300（2層の床 3600 の 300 下）→ 2層だけ庇の区間を外す
        r = solve_all({**BASE, "obstacles": [{"face": "南面", "start_mm": 3000, "end_mm": 6000,
                                              "height_mm": 3300, "top_mm": 3450, "projection_mm": 600}]})
        secs = [b for b in r.brackets if b.edge_index == 0]
        lv2 = sorted((b.start_mm, b.end_mm) for b in secs if 2 in b.levels)
        self.assertEqual(len(lv2), 2)
        self.assertLess(lv2[0][1], 3300)
        self.assertGreater(lv2[1][0], 6000)
        self.assertTrue(any(1 in b.levels and b.end_mm - b.start_mm > 10000 for b in secs))

    def test_small_eave_needs_nothing(self):
        r = solve_all({**BASE, "obstacles": [{"face": "南面", "start_mm": 0, "end_mm": 12000,
                                              "height_mm": 2700, "projection_mm": 100}]})
        self.assertEqual(r.model.plan.face_shift, {})
        self.assertTrue(any("内側に収まります" in w for w in r.model.plan.warnings))

    def test_setback_raises_the_face_and_brackets_above(self):
        upper = _floor(9000, [[0, 0], [W, 0], [W, D - 300], [0, D - 300]])
        r = solve_all({**BASE, "slabs": [GROUND, _floor(3000), _floor(6000), upper]})
        north = next(e for e in r.model.plan.edges if e.edge_index == 2)
        e = r.model.elevation_of(2)
        self.assertGreaterEqual(max(e.level_heights), 8000)               # 下の屋根 6000 で止めず上まで
        above = [b for b in r.brackets if b.edge_index == 2 and any(e.level_heights[k - 1] >= 6000 for k in b.levels)]
        self.assertTrue(above)
        self.assertGreater(above[0].inner_deck_width, 0)
        self.assertTrue(any("セットバック" in w for w in r.model.plan.warnings))
        self.assertTrue(north.standoff < 400)

    def test_can_turn_off(self):
        r = solve_all({**BASE, "avoid_obstacles": False, "obstacles": [
            {"face": "南面", "start_mm": 0, "end_mm": 12000, "height_mm": 2700, "projection_mm": 900}]})
        self.assertEqual(r.model.plan.face_shift, {})


if __name__ == "__main__":
    unittest.main()
