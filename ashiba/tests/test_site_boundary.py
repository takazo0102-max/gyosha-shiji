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
        r = solve_all({"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(west=700),
                       "series_id": "shinwa_A"})
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

    def test_tighten_the_standoff_when_the_smallest_form_still_crosses(self):
        """単管抱き足場でも越える面は、その形式の離れを詰める（境界まで −床の外側 100、下限 200）."""
        spec = {"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(west=300), "road_edges": [0]}
        sp, notes = plan_within_boundary(spec)
        self.assertEqual(sp["face_forms"], "西面=単管抱き足場")
        self.assertEqual(sp["form_standoff"]["単管抱き足場"]["target"], 200.0)
        self.assertIn("離れを 200mm に詰めました", notes[-1])
        for _label, r in solve_groups(sp):
            self.assertFalse([c for c in r.conflicts if c.kind == "足場×敷地境界" and c.severity == "NG"])
        # 下限まで詰めても越えるなら、そう書いて止める。南面・北面は角の支柱だけが西の境界を越える（角の位置は
        # 西面の離れで決まる）ので、南面・北面の形式は替えない（替えていた）
        sp2, notes2 = plan_within_boundary({**spec, "site_boundary_mm": bnd(west=250)})
        self.assertTrue(any("200mm まで詰めても敷地境界を越えます" in n for n in notes2), notes2)
        self.assertEqual(sp2["face_forms"], "西面=単管抱き足場")
        self.assertIn("南面: 角の支柱だけが敷地境界を越えます（角の位置は西面の離れで決まるので、西面で直します）", notes2)
        self.assertEqual(len(notes2), len(set(notes2)))

    def test_ladders_when_no_face_can_take_a_stair(self):
        """四方とも単管抱き足場になって階段が入らないときは、はしご（外周 60m ごとに1箇所）."""
        spec = {"outline_mm": B, "eaves_height_mm": 9000, "road_edges": [0],
                "site_boundary_mm": [[-500, -500], [24500, -500], [24500, 10500], [-500, 10500]]}
        sp, notes = plan_within_boundary(spec)
        self.assertEqual(sp["ladders"], 2)                                   # 外周 68m
        self.assertIn("はしご 2箇所", notes[-1])
        (_label, r), = solve_groups(sp)
        self.assertEqual(r.verdict["blockers"], [])

    def test_overlay_dimension_is_outside_the_scaffold(self):
        """境界までの寸法線は外側建地と境界の間（躯体側に書いて GDL のラベルに重なっていた）."""
        from ashiba.elevation_sections import plan_region_mm
        from ashiba.sheet_panel import boundary_overlay

        r = solve_all({"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(), "road_edges": [0]})
        region = plan_region_mm(r.model)
        ov = boundary_overlay(r.model, region, 100, (0.0, 0.0))
        to_mm = lambda q: (q[0] * 100 + region[0], q[1] * 100 + region[1])
        texts = {t["text"]: to_mm((t["x"], t["y"])) for t in ov["texts"] if t["text"].startswith("境界まで")}
        self.assertEqual(len(texts), 4)
        for (x, y) in texts.values():
            self.assertFalse(0 < x < 24000 and 0 < y < 10000, (x, y))      # 建物の外
        south = next(v for k, v in texts.items() if v[1] < 0)
        self.assertGreater(south[1], -1200 - 400)                          # 道路境界の内
        north = next(v for k, v in texts.items() if v[1] > 10000)
        self.assertGreater(north[1], 10000 + 2000)                         # 境界の側（足場の外の寸法線から離す）
        self.assertLess(north[1], 10000 + 4000)

    def test_asagao_does_not_depend_on_the_face_form(self):
        """同じ建物で単管抱き足場の面だけ朝顔が付いていた（単管は手すりの上に建地を100出して 10.03m）."""
        gs = solve_groups({"outline_mm": B, "eaves_height_mm": 9000, "face_forms": "西面=単管抱き足場"})
        self.assertEqual([r.model.asagao_heights() for _l, r in gs], [[], []])
        self.assertEqual(gs[-1][1].model.scaffold_height_mm, 10030)

    def test_overlay_writes_the_faces_of_the_other_groups(self):
        """面の組のほかの組（西面だけ単管抱き足場）の面にも「境界まで」を書く（先頭の組の面だけだった）."""
        from ashiba.elevation_sections import plan_region_mm
        from ashiba.sheet_panel import boundary_overlay

        sp, _ = plan_within_boundary({"outline_mm": B, "eaves_height_mm": 9000, "site_boundary_mm": bnd(west=300)})
        gs = solve_groups(sp)
        m0 = gs[0][1].model
        region = plan_region_mm(m0)
        count = lambda ov: sum(1 for t in ov["texts"] if t["text"].startswith("境界まで"))
        self.assertEqual(count(boundary_overlay(m0, region, 100, (0.0, 0.0))), 3)
        self.assertEqual(count(boundary_overlay(m0, region, 100, (0.0, 0.0), [r.model for _l, r in gs[1:]])), 4)


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
