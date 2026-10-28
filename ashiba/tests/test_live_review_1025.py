"""2026-10-25 の実機の見直し（利用者の指定: 次の項目を実機で試しておかしなところは修正して ベテラン監督がチェックするように
厳しく）で直したところ."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, solve_groups

RECT = [[0, 0], [12000, 0], [12000, 8000], [0, 8000]]


class TestHugIgnoresTheWidth(unittest.TestCase):
    def test_hug_face_stays_on_the_line(self):
        # 本体の幅 610 を指定した建物で、面の切替の単管抱き足場が 600 の建地列の間隔になり、3D の建地が平面とずれた
        g = solve_groups({"outline_mm": RECT, "eaves_height_mm": 6000, "module": "inch", "scaffold_width_mm": 610,
                          "face_forms": "東面=単管抱き足場"})
        hug = next(r for lb, r in g if "抱き" in lb)
        self.assertEqual(hug.model.post_row_spacing_mm, 0)


class TestRoofBridgeOpening(unittest.TestCase):
    def test_inner_rails_open_at_the_bridge(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800"})
        self.assertTrue(r.model.roof_bridges)
        b = r.model.roof_bridges[0]
        eds = [e for e in r.model.member_edits if e.reason == "屋上への渡りの出入口"]
        self.assertEqual(len(eds), 1)
        lv = list(r.model.elevation_of(b.edge_index).level_heights)
        self.assertEqual(eds[0].level_from, lv.index(int(b.z_from_mm)) + 1)
        self.assertEqual(eds[0].parts, ("内側手すり",))


class TestBracesAtBothEnds(unittest.TestCase):
    def test_brace_starts(self):
        from ashiba.quantity import brace_starts

        self.assertEqual(brace_starts(6, 6), [1, 5])
        self.assertEqual(brace_starts(7, 6), [1, 7])
        self.assertEqual(brace_starts(12, 6), [1, 7, 11])
        self.assertEqual(brace_starts(1, 6), [1])


class TestLongSpanHoist(unittest.TestCase):
    def test_two_masts_and_gates_over_the_platform(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                       "hoists": [{"edge_index": 0, "position_mm": 6000, "landing_levels": [1, 2]}]})
        h = r.platforms.hoists[0]
        self.assertEqual((h.cage_width_mm, h.cage_depth_mm), (4600.0, 1300.0))
        self.assertGreaterEqual(len(h.gate_spans(r.model)), 3)            # 4.6m の荷台は 3 スパンに掛かる
        xs = sorted({t.position_mm for t in r.model.wall_ties if t.kind == "hoist"})
        self.assertEqual(len(xs), 2)                                        # マスト2本の控え
        # 控えは荷台の両端の外（±2500）にいちばん近い足場の建地に取る（2026-10-27: 建地の間の布材には取らない）
        ep = r.model.plan.edges[0]
        posts = [sum(ep.spans[:k]) for k in range(len(ep.spans) + 1)]
        self.assertTrue(all(any(abs(x - p) < 0.5 for p in posts) for x in xs))
        self.assertGreaterEqual(xs[1] - xs[0], 4600)


class TestSteelTiesAtBeams(unittest.TestCase):
    def test_attachment_ties_snap_to_the_beams(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800", "tie_source": "鉄骨",
                       "steel_beam_heights_mm": [2850, 5850, 8850],
                       "hoists": [{"edge_index": 0, "position_mm": 6000}]})
        beams = {3150, 6150, 9150}
        self.assertTrue(all(t.height_mm in beams for t in r.model.wall_ties), sorted({t.height_mm for t in r.model.wall_ties}))


class TestInteriorStageUnderTheCeiling(unittest.TestCase):
    def test_rails_through_the_ceiling_is_ng(self):
        from ashiba.interior_stage import solve_stage
        from ashiba.master import load_master

        m = load_master("nikken_nd1800")
        corners = [[0, 0], [6000, 0], [6000, 4000], [0, 4000]]
        bad = solve_stage({"name": "x", "corners_mm": corners, "deck_mm": 2500, "ceiling_mm": 2800}, m)
        self.assertFalse(bad.ok)
        self.assertTrue(any(c.item == "天井との取り合い" and c.status == "NG" for c in bad.checks))
        ok = solve_stage({"name": "x", "corners_mm": corners, "deck_mm": 1000, "ceiling_mm": 2800}, m)
        self.assertTrue(any(c.item == "天井との取り合い" and c.status == "OK" for c in ok.checks))


class TestGroundScaffoldStairs(unittest.TestCase):
    def test_stairs_not_ladders(self):
        # 2026-10-25 は 2層以下ははしごで階段を数えなかったが、利用者の指定 2026-10-29「ハシゴじゃなくて階段を使う」で
        # 地足場も階段室にした。階段は層の数×階段室の数だけ数え、はしごは数えない
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                       "ground_scaffold": {"levels": 2}})
        self.assertEqual(r.quantity.qty_of("階段"), 2 * len(r.stair_plan.towers))
        self.assertEqual(r.model.config.ladders, 0)


class TestSpecObjectModule(unittest.TestCase):
    def test_module_follows_the_series(self):
        from ashiba.spec_object import params_from_spec

        self.assertEqual(params_from_spec({"series_id": "nikken_nd1800"})["moduleKind"], "inch")


class TestElevationLines(unittest.TestCase):
    def test_line_outside_a_face_sets_its_elevation(self):
        from ashiba.elevation_sections import assign_elevation_line, crosses_outline, section_specs

        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                       "elevation_lines_mm": [[[11000, -5000], [2000, -5000]]]})
        m = r.model
        self.assertFalse(crosses_outline(RECT, (11000, -5000), (2000, -5000)))
        self.assertTrue(crosses_outline(RECT, (6000, -3000), (6000, 11000)))
        self.assertEqual(assign_elevation_line(m, (11000, -5000), (2000, -5000))[0], 0)
        south = next(s for s in section_specs(m) if s.edge_index == 0)
        self.assertEqual((south.start_mm, south.end_mm), ((2000.0, -5000.0), (11000.0, -5000.0)))
        # 外側建地列より内側の線は立面にしない（図面を作るで断面にまわす）
        self.assertIsNone(assign_elevation_line(m, (2000, -400), (9000, -400)))


if __name__ == "__main__":
    unittest.main()
