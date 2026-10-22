"""敷地境界線と足場の離れ・境界に合わせた解き直し（利用者の指定 2026-10-23: 建物と敷地境界線を作成して足場計画を繰り返してみて）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, solve_groups
from ashiba.site_boundary import face_clearances, pick_boundary, plan_within_boundary

B = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]


def bnd(west=1500, road=1200, east=3000, north=4000):
    return [[-west, -road], [24000 + east, -road], [24000 + east, 10000 + north], [-west, 10000 + north]]


class TestClearance(unittest.TestCase):
    def test_per_face_distance_from_outer_posts(self):
        r = solve_all({"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(), "road_edges": [0]})
        c = {x.face: x for x in face_clearances(r.model, r.model.site_boundary_mm, r.model.site_road_edges)}
        ep = {r.model.face_name(e.edge_index): e for e in r.model.plan.edges}
        row = r.model.post_row_spacing_mm
        # 外側建地の外面から: 境界まで − 離れ − 建地列 − 支柱の半径
        self.assertAlmostEqual(c["北面"].min_mm, 4000 - ep["北面"].standoff - row - 25, delta=1)
        self.assertAlmostEqual(c["西面"].min_mm, 1500 - ep["西面"].standoff - row - 25, delta=1)
        self.assertTrue(c["南面"].road and not c["北面"].road)
        # 法規#1 のスペースは躯体からいちばん近い境界まで
        self.assertAlmostEqual(r.model.clearance_space_mm, 1200, delta=1)

    def test_over_the_boundary_is_ng(self):
        r = solve_all({"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(west=700)})
        ng = [c for c in r.conflicts if c.kind == "足場×敷地境界" and c.severity == "NG"]
        self.assertEqual(len(ng), 1)
        self.assertTrue(ng[0].message.startswith("西面:"))
        self.assertIn("225mm 越えます", ng[0].message)

    def test_plan_again_with_smaller_forms(self):
        spec = {"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(west=700), "road_edges": [0]}
        sp, notes = plan_within_boundary(spec)
        self.assertEqual(sp["face_forms"], "西面=単管抱き足場")       # 一側足場でも越える → 単管抱き足場
        self.assertEqual(len(notes), 2)
        for _label, r in solve_groups(sp):
            self.assertFalse([c for c in r.conflicts if c.kind == "足場×敷地境界" and c.severity == "NG"])
            self.assertEqual(r.verdict["blockers"], [])                # 階段はほかの組の面のものを使う
        self.assertEqual(plan_within_boundary({**spec, "fit_boundary": False})[0], {**spec, "fit_boundary": False})


class TestPick(unittest.TestCase):
    def test_closed_polyline_around_the_building_and_road_edge(self):
        out = [(-1500, -1200), (27000, -1200), (27000, 14000), (-1500, 14000), (-1500, -1200)]
        polys = [{"layer": "敷地境界線", "pts": out},
                 {"layer": "敷地境界線", "pts": [(50000, 0), (60000, 0), (60000, 5000), (50000, 0)]},   # 別の敷地
                 {"layer": "道路境界線", "pts": [(-5000, -1200), (30000, -1200)]},
                 {"layer": "壁", "pts": [(-9e5, -9e5), (9e5, -9e5), (9e5, 9e5), (-9e5, 9e5)]}]
        pts, roads = pick_boundary(polys, [tuple(p) for p in B])
        self.assertEqual(len(pts), 4)
        self.assertEqual(roads, {0})



class TestSubsetFaceDirection(unittest.TestCase):
    def test_line_angle_comes_from_its_own_edge(self):
        """面の組（西面だけ）の足場ラインは西面の向き（南向き）に置く。並びで辺を組み合わせて東向きになっていた."""
        import math

        from ashiba.tapir_adapter import place_scaffold_lines

        gs = solve_groups({"outline_mm": B, "eaves_height_mm": 9000, "face_forms": "西面=単管抱き足場"})
        m = gs[-1][1].model

        class Client:
            def __init__(self):
                self.rot = []

            def find_member_surfaces(self):
                return {}

            def create_object(self, name, x, y, z=0.0):
                return {"elementId": {"guid": f"G{len(self.rot)}"}}

            def rotate_element(self, el, angle, x, y):
                self.rot.append(angle)

            def set_gdl_parameters(self, *a, **k):
                pass

            def tapir(self, *a, **k):
                return {}

        c = Client()
        place_scaffold_lines(m, "ashiba_line", c)
        self.assertEqual([round(math.degrees(a)) for a in c.rot], [-90])


if __name__ == "__main__":
    unittest.main()
