"""高さをスラブの天端から（面ごと・セットバック。利用者の指定 2026-10-20）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.slab_heights import slab_top_mm

FOOT = [[0, 0], [18000, 0], [18000, 14000], [0, 14000]]
UPPER = [[0, 7000], [18000, 7000], [18000, 14000], [0, 14000]]


def slabs():
    return ([{"polygon_mm": FOOT, "top_mm": t} for t in (0, 3000, 6000, 9000)]
            + [{"polygon_mm": UPPER, "top_mm": t} for t in (12000, 15000)])


class TestSlabTop(unittest.TestCase):
    def test_reference_plane(self):
        self.assertEqual(slab_top_mm({"details": {"zCoordinate": 6.0, "referencePlaneLocation": "Top"}}), 6000.0)
        self.assertEqual(slab_top_mm({"details": {"zCoordinate": 5.85, "thickness": 0.15,
                                                  "referencePlaneLocation": "Bottom"}}), 6000.0)


class TestSetback(unittest.TestCase):
    def setUp(self):
        self.r = solve_all({"outline_mm": FOOT, "eaves_height_mm": 1000, "slabs": slabs()})
        self.m = self.r.model
        self.by = {n: e.edge_index for e, n in zip(self.m.plan.edges, self.m.plan.face_names())}

    def test_each_face_gets_its_own_height(self):
        south = self.m.elevation_of(self.by["南面"])
        north = self.m.elevation_of(self.by["北面"])
        # 上の階が面一の面は上の屋根まで（1層目を 1.8m 前後にそろえるので、最上層は屋根から階高の範囲で上に出ることがある）
        self.assertTrue(15000 <= north.level_heights[-1] < 15000 + self.m.master.floor_height, north.level_heights)
        self.assertGreaterEqual(south.level_heights[-1], 9000)         # 引っ込んだ面は下の屋根まで
        self.assertLess(south.n_levels, north.n_levels)
        self.assertEqual(south.level_heights, north.level_heights[:south.n_levels])   # 作業床の高さは共通

    def test_hoist_uses_its_own_face_height(self):
        # 低い面（南）の昇降機は、その面の層数・高さで見る。高い面（北）の最上層を乗り込み口に指定すれば存在しない層、
        # 到達高さを省けば南面の足場の高さまで（マスト控えも南面の高さより上に付けない）
        south = self.by["南面"]
        n_s = self.m.elevation_of(south).n_levels
        n_n = self.m.elevation_of(self.by["北面"]).n_levels
        r = solve_all({"outline_mm": FOOT, "eaves_height_mm": 1000, "slabs": slabs(),
                       "hoists": [{"edge_index": south, "position_mm": 6000, "model": "KSE600L",
                                   "landing_levels": [n_s, n_n]}]})
        h = r.platforms.hoists[0]
        self.assertEqual(h.landings(r.model), [n_s])
        self.assertTrue([x for x in r.platforms.issues if f"[{n_n}]は存在しません" in x.message])
        top_s = r.model.elevation_of(south).total_height
        self.assertEqual(h.reach_mm(r.model), float(top_s))
        self.assertTrue(all(t.height_mm <= top_s for t in r.model.wall_ties if t.kind == "hoist"))

    def test_stage_uses_its_own_face_levels(self):
        # 低い面（南）の荷受けステージに高い面の最上層を指定すれば存在しない層。取付部の壁つなぎも南面の高さを越えない
        south = self.by["南面"]
        n_s = self.m.elevation_of(south).n_levels
        n_n = self.m.elevation_of(self.by["北面"]).n_levels
        r = solve_all({"outline_mm": FOOT, "eaves_height_mm": 1000, "slabs": slabs(),
                       "loading_stages": [{"edge_index": south, "start_mm": 3658, "span_count": 2, "levels": [n_s, n_n]}]})
        self.assertTrue([x for x in r.platforms.issues if f"作業層{n_n}は存在しません（1〜{n_s}）" in x.message])
        top_s = r.model.elevation_of(south).total_height
        self.assertTrue(all(t.height_mm <= top_s for t in r.model.wall_ties
                            if t.kind == "stage" and t.edge_index == south))

    def test_ties_stop_at_each_face_top(self):
        for e in self.m.plan.edges:
            top = self.m.elevation_of(e.edge_index).level_heights[-1]
            self.assertTrue(all(t.height_mm <= top for t in self.m.wall_ties if t.edge_index == e.edge_index))

    def test_passes_and_quantities_merge_groups(self):
        self.assertTrue(self.r.verdict["ok"], self.r.verdict["blockers"])
        self.assertTrue(self.r.quantity.notes[0].startswith("面ごとに高さが違う"))
        full = solve_all({"outline_mm": FOOT, "eaves_height_mm": 15000})
        self.assertLess(self.r.quantity.qty_of("支柱"), full.quantity.qty_of("支柱"))   # 低い面の分だけ少ない
        self.assertGreater(self.r.quantity.qty_of("支柱"), 0)

    def test_drawings_use_the_face_levels(self):
        from ashiba.gdl_params import line_params

        south = next(e for e in self.m.plan.edges if e.edge_index == self.by["南面"])
        p = line_params(self.m, south)
        self.assertEqual(p["levelList"].count(",") + 1, self.m.elevation_of(south.edge_index).n_levels)


class TestUpperPartOnTheLowerRoof(unittest.TestCase):
    def test_base_is_the_lower_roof(self):
        r = solve_all({"outline_mm": [[3000, 9000], [15000, 9000], [15000, 13000], [3000, 13000]],
                       "eaves_height_mm": 1000, "slabs": slabs() + [
                           {"polygon_mm": [[3000, 9000], [15000, 9000], [15000, 13000], [3000, 13000]], "top_mm": 18000}]})
        self.assertEqual(r.model.base_height_mm, 15000)                 # 上の屋根（15m）の上に立つ
        self.assertGreaterEqual(r.model.elevation.level_heights[-1], 2900)   # 立つ面から約 3m（18m の屋上階）
        self.assertLess(r.model.elevation.level_heights[-1], 4000)


class TestNoUsefulSlabs(unittest.TestCase):
    def test_flat_footprint_slab_keeps_the_typed_eaves(self):
        r = solve_all({"outline_mm": FOOT, "eaves_height_mm": 9000, "slabs": [{"polygon_mm": FOOT, "top_mm": 0}]})
        self.assertEqual(r.model.face_elevations, {})
        self.assertEqual(r.model.elevation.level_heights[-1] >= 9000, True)

    def test_switch_off(self):
        r = solve_all({"outline_mm": FOOT, "eaves_height_mm": 9000, "slabs": slabs(), "height_from_slabs": False})
        self.assertEqual(r.model.face_elevations, {})
