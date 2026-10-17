"""立面図を断面図ビューポイント（立面ツール相当）で作ってレイアウトに置く（elevation_sections）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_sections import (
    CLEARANCE_MM,
    END_EXT_MM,
    SUBSET_NAME,
    arrange_on_one_sheet,
    drawing_plan,
    ensure_subset,
    find_items,
    pick_master_layout,
    remove_elevations,
    section_specs,
    walk_tree,
)
from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan

RECT = [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]


def build():
    master = load_master("shinwa_A")
    return ScaffoldModel(master=master, plan=solve_plan(RECT, master),
                         elevation=solve_elevation(16300, master=master), config=ScaffoldConfig())


class TestSectionGeometry(unittest.TestCase):
    def setUp(self):
        self.m = build()
        self.specs = {s.face_name: s for s in section_specs(self.m, "試験")}

    def test_one_section_per_face_named_by_face(self):
        self.assertEqual(set(self.specs), {"南面", "東面", "北面", "西面"})
        self.assertEqual(self.specs["南面"].name, "試験 南面 足場立面")

    def test_cut_line_is_outside_the_outer_post_row_and_looks_at_the_building(self):
        s = self.specs["南面"]
        row_w = self.m.post_row_spacing_mm
        ep = next(e for e in self.m.plan.edges if self.m.face_name(e.edge_index) == "南面")
        # 南面: 足場ラインは y=start_post.y、外側建地列はその -rowW、切断線はさらに clearance 外
        self.assertAlmostEqual(s.start_mm[1], ep.start_post[1] - row_w - CLEARANCE_MM, places=3)
        self.assertAlmostEqual(s.end_mm[1], s.start_mm[1], places=3)
        # 始点→終点は +x（左手＝+y＝躯体側を見る。Tapir の CreateSections と同じ向き）
        self.assertGreater(s.end_mm[0], s.start_mm[0])
        # 両端を延長
        self.assertAlmostEqual(s.start_mm[0], ep.start_post[0] - END_EXT_MM, places=3)
        self.assertAlmostEqual(s.end_mm[0], ep.end_post[0] + END_EXT_MM, places=3)
        # 奥行きは躯体の最遠点（y=320000）を越え、向こう側の足場（320000+離れ+rowW）には届かない
        far_wall = 320000 - s.start_mm[1]
        self.assertGreater(s.depth_mm, far_wall)
        self.assertLess(s.depth_mm, far_wall + ep.standoff + row_w)

    def test_every_face_looks_toward_the_building(self):
        cx, cy = 315000.0, 310000.0
        for s in self.specs.values():
            dx, dy = s.end_mm[0] - s.start_mm[0], s.end_mm[1] - s.start_mm[1]
            # 左手法線 (-dy, dx) が建物中心を向く
            self.assertGreater((-dy) * (cx - s.start_mm[0]) + dx * (cy - s.start_mm[1]), 0, s.face_name)


class TestDrawingPlan(unittest.TestCase):
    def test_scale_fits_the_paper(self):
        a1 = (841.0, 594.0)
        self.assertEqual(drawing_plan(34600, 16300, a1).scale, 100)      # 346mm ≤ 791mm
        self.assertEqual(drawing_plan(90000, 16300, a1).scale, 200)      # 900mm は入らない → 1/200
        self.assertEqual(drawing_plan(34600, 45000, a1).scale, 100)      # 高さ 47m/100=470 ≤ 494
        self.assertEqual(drawing_plan(34600, 55000, a1).scale, 200)      # 高さが入らない → 1/200
        a3 = (420.0, 297.0)
        self.assertEqual(drawing_plan(34600, 16300, a3).scale, 100)      # 346 ≤ 370
        self.assertEqual(drawing_plan(40000, 16300, a3).scale, 200)

    def test_position_clears_the_margin_and_title_band(self):
        p = drawing_plan(34600, 16300, (841.0, 594.0), margins_mm=(15.0, 10.0, 10.0, 10.0))
        self.assertEqual(p.position_mm, (25.0, 70.0))


FAKE_TREE = {
    "type": "UndefinedItem", "name": "ROOT", "navigatorItemId": {"guid": "root"},
    "children": [
        {"navigatorItem": {"type": "BookItem", "name": "名称未設定", "navigatorItemId": {"guid": "book"}, "children": [
            {"navigatorItem": {"type": "SubSetItem", "name": "レイアウト", "navigatorItemId": {"guid": "sub1"}, "children": [
                {"navigatorItem": {"type": "LayoutItem", "name": "試験 足場立面図 南面", "navigatorItemId": {"guid": "lay1"}}}]}},
            {"navigatorItem": {"type": "MasterFolderItem", "name": "マスタ", "navigatorItemId": {"guid": "mf"}, "children": [
                {"navigatorItem": {"type": "MasterLayoutItem", "name": "A3テンプレート", "navigatorItemId": {"guid": "a3"}}},
                {"navigatorItem": {"type": "MasterLayoutItem", "name": "A1テンプレート", "navigatorItemId": {"guid": "a1"}}}]}},
        ]}},
    ],
}


class TestNavigatorHelpers(unittest.TestCase):
    def test_walk_and_find(self):
        items = list(walk_tree(FAKE_TREE))
        self.assertEqual(len(items), 7)
        self.assertEqual(find_items(FAKE_TREE, "LayoutItem", name="試験 足場立面図 南面")[0]["guid"], "lay1")
        self.assertEqual([i["guid"] for i in find_items(FAKE_TREE, "MasterLayoutItem")], ["a3", "a1"])

    def test_master_prefers_a1_and_skips_the_folder(self):
        masters = [i for i in walk_tree(FAKE_TREE) if "Master" in (i["type"] or "")]
        self.assertEqual(pick_master_layout(masters)["guid"], "a1")
        self.assertEqual(pick_master_layout(masters, prefer="A3")["guid"], "a3")


class _Client:
    """ツリーを返し、削除・作成を記録する疑似クライアント."""

    def __init__(self, project_map, layout_book):
        self.pm, self.lb = project_map, layout_book
        self.calls = []

    def tapir(self, command, params):
        self.calls.append((command, params))
        if command == "GetNavigatorItemTree":
            return {"navigatorItemTree": self.pm if params["navigatorMapId"] == "ProjectMap" else self.lb}
        if command == "CreateLayoutSubset":
            # 実機と同じく ID を返せない。ツリーに足しておく
            self.lb["children"][0]["navigatorItem"]["children"].append(
                {"navigatorItem": {"type": "SubSetItem", "name": params["subsetsData"][0]["name"], "navigatorItemId": {"guid": "newsub"}}})
            return {"navigatorItems": [{"error": {"message": "could not resolve"}}]}
        return {"executionResults": []}


class TestRemoveAndSubset(unittest.TestCase):
    def test_remove_deletes_only_matching_names(self):
        pm = {"type": "ProjectItem", "name": "p", "navigatorItemId": {"guid": "p"}, "children": [
            {"navigatorItem": {"type": "SectionItem", "name": "試験 南面 足場立面", "navigatorItemId": {"guid": "s1"}}},
            {"navigatorItem": {"type": "SectionItem", "name": "別物件 南面 足場立面", "navigatorItemId": {"guid": "s2"}}}]}
        import copy
        c = _Client(pm, copy.deepcopy(FAKE_TREE))
        n_s, n_l, left = remove_elevations(c, ["試験 南面 足場立面"], ["試験 足場立面図 南面"], section_guids=["cut-1", ""])
        self.assertEqual((n_s, n_l), (1, 1))
        # 断面は要素（CutPlane）として消す。ナビゲータ項目の削除は実機で失敗する
        self.assertEqual([p["elements"][0]["elementId"]["guid"] for cmd, p in c.calls if cmd == "DeleteElements"], ["cut-1"])
        self.assertEqual([p["navigatorItemIds"][0]["navigatorItemId"]["guid"] for cmd, p in c.calls if cmd == "DeleteNavigatorItems"], ["lay1"])
        self.assertEqual(left, ["試験 南面 足場立面"])        # 疑似ツリーでは残る（控えが無い断面の注意に使う）

    def test_subset_is_created_once_and_found_by_name(self):
        import copy
        c = _Client({"type": "ProjectItem", "name": "p", "navigatorItemId": {"guid": "p"}}, copy.deepcopy(FAKE_TREE))
        self.assertEqual(ensure_subset(c), "newsub")
        self.assertEqual(sum(1 for cmd, _ in c.calls if cmd == "CreateLayoutSubset"), 1)
        self.assertEqual(ensure_subset(c), "newsub")                      # 2回目は作らない
        self.assertEqual(sum(1 for cmd, _ in c.calls if cmd == "CreateLayoutSubset"), 1)
        self.assertEqual(SUBSET_NAME, "仮設足場")


class TestRecord(unittest.TestCase):
    def test_round_trip_keeps_other_buildings(self):
        import tempfile
        from ashiba.elevation_sections import ElevationPlacement, load_record, save_record

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_record(d), {})
            rec = save_record(d, [ElevationPlacement("南面", "A 南面 足場立面", section_guid="g1")], {"B 南面 足場立面": "g0"})
            self.assertEqual(rec, {"B 南面 足場立面": "g0", "A 南面 足場立面": "g1"})
            self.assertEqual(load_record(d), rec)


if __name__ == "__main__":
    unittest.main()


class TestOneSheet(unittest.TestCase):
    """全面が収まるときは1枚のレイアウトに並べる（30×20m・A1 なら 1/100 で2行）."""

    def test_rect_fits_on_a1_at_1_100(self):
        plan = arrange_on_one_sheet([34600, 24600, 34600, 24600], 16300, (841.0, 594.0))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.scale, 100)
        xs = [p[0] for p in plan.positions_mm]
        ys = [p[1] for p in plan.positions_mm]
        self.assertEqual(len(set(ys)), 2)                      # 2行
        self.assertLess(xs[0], xs[1])                           # 南→東は右へ
        self.assertEqual(ys[0], ys[1]); self.assertEqual(ys[2], ys[3])
        self.assertGreater(ys[0], ys[2])                        # 1行目が上
        # 右端・上端が用紙に収まる（図面幅 = 長さ/100、高さ = (H+2000)/100）
        for (x, y), length in zip(plan.positions_mm, [34600, 24600, 34600, 24600]):
            self.assertLessEqual(x + length / 100, 841 - 20)
            self.assertLessEqual(y + 18300 / 100, 594 - 20)
            self.assertGreaterEqual(y, 20 + 60)

    def test_falls_back_when_too_big(self):
        self.assertIsNone(arrange_on_one_sheet([34600, 24600, 34600, 24600], 16300, (420.0, 297.0)))   # A3 では無理
        plan = arrange_on_one_sheet([34600, 24600, 34600, 24600], 50000, (841.0, 594.0))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.scale, 200)                       # 高さ 52m は 1/100 では2行にならない → 1/200


class TestActivateFloorPlan(unittest.TestCase):
    def test_switches_to_the_active_story_when_a_layout_is_in_front(self):
        from ashiba.elevation_sections import activate_floor_plan

        class C:
            def __init__(self):
                self.calls = []
                self.win = "Layout"

            def current_window_type(self):
                return self.win

            def tapir(self, command, params):
                self.calls.append((command, params))
                if command == "GetStories":
                    return {"actStory": 1}
                if command == "GetNavigatorItemTree":
                    return {"navigatorItemTree": {"type": "ProjectItem", "name": "p", "navigatorItemId": {"guid": "p"}, "children": [
                        {"navigatorItem": {"type": "StoryItem", "prefix": "0", "name": "1FL", "navigatorItemId": {"guid": "s0"}}},
                        {"navigatorItem": {"type": "StoryItem", "prefix": "1", "name": "2FL", "navigatorItemId": {"guid": "s1"}}}]}}
                if command == "ChangeWindow":
                    self.win = "FloorPlan"
                    return {"success": True}
                return {}

        c = C()
        self.assertTrue(activate_floor_plan(c))
        self.assertEqual([p for cmd, p in c.calls if cmd == "ChangeWindow"], [{"navigatorItemId": {"guid": "s1"}}])
        n = len(c.calls)
        self.assertTrue(activate_floor_plan(c))          # 既に平面図なら何もしない
        self.assertEqual(len(c.calls), n)
