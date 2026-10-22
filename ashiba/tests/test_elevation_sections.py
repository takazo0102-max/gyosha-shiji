"""立面図を断面図ビューポイント（立面ツール相当）で作ってレイアウトに置く（elevation_sections）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_sections import (
    CLEARANCE_MM,
    END_EXT_MM,
    SUBSET_NAME,
    arrange_boxes,
    arrange_on_one_sheet,
    drawing_plan,
    ensure_subset,
    find_items,
    pick_master_layout,
    remove_elevations,
    section_annotations,
    section_specs,
    section_x,
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



class TestTwoFacesPerSheet(unittest.TestCase):
    def test_sheet_names(self):
        # 立面は1枚に2面（利用者の指定 2026-10-23）。4面なら「… 足場立面図 1」「… 2」
        from ashiba.elevation_sections import FACES_PER_SHEET, sheet_layout_name, sheet_layout_names

        self.assertEqual(FACES_PER_SHEET, 2)
        self.assertEqual(sheet_layout_name("X"), "X 足場立面図")
        self.assertEqual(sheet_layout_name("X", 2), "X 足場立面図 2")
        self.assertIn("X 足場立面図 3", sheet_layout_names("X"))
        src = (Path(__file__).resolve().parents[1] / "src" / "ashiba" / "elevation_sections.py").read_text(encoding="utf-8")
        self.assertIn("groups = [idx[g:g + FACES_PER_SHEET] for g in range(0, len(idx), FACES_PER_SHEET)]", src)


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


class TestSectionCoordinates(unittest.TestCase):
    """断面の横軸＝切断線の向きへの射影（実機: 南面は x、北面は -x）."""

    def test_projection_per_face(self):
        m = build()
        specs = {s.face_name: s for s in section_specs(m, "試験")}
        self.assertAlmostEqual(section_x(specs["南面"], (300000.0, 0.0)), 300.0)
        self.assertAlmostEqual(section_x(specs["北面"], (300000.0, 0.0)), -300.0)
        self.assertAlmostEqual(section_x(specs["東面"], (0.0, 310000.0)), 310.0)
        for s in specs.values():
            self.assertLess(section_x(s, s.start_mm), section_x(s, s.end_mm))   # 始点が左


class TestSectionAnnotations(unittest.TestCase):
    def setUp(self):
        self.m = build()
        self.specs = {s.face_name: s for s in section_specs(self.m, "試験")}

    def test_levels_heights_and_summary(self):
        notes = section_annotations(self.m, self.specs["南面"])
        texts = [t["text"] for t in notes.texts]
        e = self.m.elevation
        # 高さは寸法の3本（段の高さ・支柱の高さ・足場の高さ）。層の高さの文字は書かない（利用者の指定 2026-10-23）
        self.assertFalse(any("層 +" in x or x.startswith("根がらみ +") for x in texts))
        for title in ("段の高さ", "支柱の高さ", "足場の高さ"):
            self.assertIn(title, texts)
        # 高さ・スパンは寸法ツールの寸法（測る区間の値）。置けなかったときの線と文字は fallback
        by = {d["chain"]: d for d in notes.dims}
        steps = [0] + list(e.level_heights) + [e.total_height]
        self.assertEqual(by["段の高さ"]["values"], [b - a for a, b in zip(steps, steps[1:])])
        self.assertEqual(by["支柱の高さ"]["values"], [e.jack_extension] + list(e.posts))
        self.assertEqual(by["足場の高さ"]["values"], [self.m.scaffold_height_mm])
        self.assertIn(f"ジャッキ{e.jack_extension:.0f}", texts)                 # 短い区間は名前を添える
        fb = [x["text"] for x in by["段の高さ"]["fallback"]["texts"]]
        self.assertEqual(fb, [f"{b - a:.0f}" for a, b in zip(steps, steps[1:])])
        self.assertTrue(any(t.startswith("南面 足場立面図") for t in texts))
        self.assertTrue(any("壁つなぎ" in t and "◎印" in t for t in texts))
        self.assertIn("GL±0", texts)
        ep = next(x for x in self.m.plan.edges if x.edge_index == self.specs["南面"].edge_index)
        self.assertEqual(by["スパン"]["values"], [float(s) for s in ep.spans])        # スパン寸法
        spans = [t for t in by["スパン"]["fallback"]["texts"]]
        self.assertEqual([t["text"] for t in spans], [f"{s:.0f}" for s in ep.spans])
        self.assertEqual(by["全長"]["values"], [float(sum(ep.spans))])                # 全長

    def test_notes_sit_beside_and_above_the_scaffold(self):
        s = self.specs["南面"]
        ep = next(e for e in self.m.plan.edges if e.edge_index == s.edge_index)
        hi = section_x(s, ep.end_post) + self.m.post_row_spacing_mm / 1000.0
        notes = section_annotations(self.m, s)
        level_texts = [t for t in notes.texts if t.get("chain") or t.get("chain_title")]
        self.assertTrue(level_texts and all(t["x"] > hi for t in level_texts))   # 右側
        summary = [t for t in notes.texts if "足場立面図" in t["text"]][0]
        self.assertGreater(summary["y"], self.m.scaffold_height_mm / 1000.0)   # 上
        self.assertTrue(all(len(pts) >= 2 for pts in notes.lines))

    def test_dimensions_stand_off_from_the_scaffold(self):
        """寸法は足場から離す（スパンは天端から1m以上上、高さの寸法線は外側の建地から1m以上右）."""
        from ashiba.elevation_sections import LEVEL_DIM_OFFSET_M, SPAN_DIM_OFFSET_M

        s = self.specs["南面"]
        top = self.m.scaffold_height_mm / 1000.0
        notes = section_annotations(self.m, s)
        by = {d["chain"]: d for d in notes.dims}
        self.assertGreater(by["スパン"]["ref"][1], top + 1.0)
        self.assertGreaterEqual(SPAN_DIM_OFFSET_M, 1.0)
        self.assertGreaterEqual(LEVEL_DIM_OFFSET_M, 1.0)
        # 高さの寸法: 測る点は外側の建地の線、寸法線はその右に 段の高さ→支柱の高さ→足場の高さ の順
        ep = next(e for e in self.m.plan.edges if e.edge_index == s.edge_index)
        hi = section_x(s, ep.end_post) + self.m.post_row_spacing_mm / 1000.0
        xs = [by[c]["ref"][0] for c in ("段の高さ", "支柱の高さ", "足場の高さ")]
        self.assertEqual(xs, sorted(xs))
        self.assertGreaterEqual(xs[0] - hi, 1.0)
        self.assertTrue(all(abs(x - hi) < 1e-6 for x, _ in by["段の高さ"]["points"]))
        self.assertEqual(len(by["段の高さ"]["points"]), len(self.m.elevation.level_heights) + 2)   # GL→各作業床→天端

    def test_dims_fall_back_to_lines_when_the_tool_fails(self):
        """寸法を置けないとき（古い Tapir など）は、線と文字で描いた寸法になる."""
        from ashiba.elevation_sections import write_section_notes

        notes = section_annotations(self.m, self.specs["南面"])

        class Client:
            def __init__(self, dims_ok):
                self.dims_ok, self.calls = dims_ok, []

            def tapir(self, cmd, params):
                self.calls.append((cmd, params))
                if cmd == "CreateAssociativeDimensions":
                    if not self.dims_ok:
                        raise RuntimeError("no command")
                    return {"elements": [{"elementId": {"guid": "D"}} for _ in params["dimensionsData"]]}
                key = next(iter(params))
                return {"elements": [{"elementId": {"guid": "E"}} for _ in params[key]]}

        def texts(c):
            return [t["text"] for cmd, p in c.calls if cmd == "CreateTexts" for t in p["textsData"]]

        ok = Client(True)
        write_section_notes(ok, notes)
        dims = [p for cmd, p in ok.calls if cmd == "CreateAssociativeDimensions"][0]["dimensionsData"]
        self.assertEqual(len(dims), len(notes.dims))
        self.assertEqual(len(dims[0]["witnessPoints"]), len(notes.dims[0]["points"]))
        self.assertNotIn("1800", texts(ok))                  # 寸法の数は寸法ツールが書く
        ng = Client(False)
        write_section_notes(ng, notes)
        self.assertIn("1800", texts(ng))

    def test_member_labels_point_at_members(self):
        """部材名は引出線つきのラベル。下段は GL の下、上段は寸法の上に並び、矢先は部材の高さ."""
        s = self.specs["南面"]
        top = self.m.scaffold_height_mm / 1000.0
        notes = section_annotations(self.m, s)
        texts = [lb["text"] for lb in notes.labels]
        for want in ("根がらみ", "ジャッキベース", "作業床（踏板）・幅木", "手すり", "中桟"):
            self.assertIn(want, texts)
        self.assertTrue(any(t.startswith("壁つなぎ") for t in texts))
        for lb in notes.labels:
            self.assertTrue(lb["end"][1] < 0 or lb["end"][1] > top + 2.0, lb)
            self.assertTrue(0.0 <= lb["beg"][1] <= top + 1.0, lb)
        e = self.m.elevation
        neg = next(lb for lb in notes.labels if lb["text"] == "根がらみ")
        self.assertAlmostEqual(neg["beg"][1], e.first_ledger_height / 1000.0)


class TestArrangeBoxes(unittest.TestCase):
    def test_measured_boxes_do_not_overlap_and_fit(self):
        boxes = [(41000, 21000), (31000, 21000), (41000, 21000), (31000, 21000)]   # 30×20m＋注記の余白
        plan = arrange_boxes(boxes, (841.0, 594.0))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.scale, 100)
        rects = [(x, y, x + w / 100, y + h / 100) for (x, y), (w, h) in zip(plan.positions_mm, boxes)]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b))
        for x0, y0, x1, y1 in rects:
            self.assertLessEqual(x1, 841 - 20)
            self.assertLessEqual(y1, 594 - 20)

    def test_scale_floor_is_respected(self):
        boxes = [(44000, 21000)] * 4
        plan = arrange_boxes(boxes, (841.0, 594.0), scales=[200, 300])
        self.assertEqual(plan.scale, 200)


class TestDrawingScaleIsARatio(unittest.TestCase):
    """図面の大きさは比率（scale）で決まる。drawingScale は縮尺名だけ（実機で 1/200 指定が 1/100 の大きさで置かれた）."""

    def test_ratio_from_target_scale(self):
        from ashiba.elevation_sections import ElevationPlacement, _create_drawings

        class C:
            def __init__(self):
                self.sent = None

            def tapir(self, command, params):
                if command == "CreateDrawings":
                    self.sent = params["drawingsData"]
                    return {"elements": [{"elementId": {"guid": "d1"}}]}
                return {}

        c = C()
        pl = ElevationPlacement("南面", "x", section_item_guid="s")
        _create_drawings(c, {"guid": "db"}, [pl], [(30.0, 80.0)], 200, 0.01)
        self.assertAlmostEqual(c.sent[0]["scale"], 0.5)
        self.assertEqual(c.sent[0]["drawingScale"], 200.0)
        self.assertEqual(pl.scale, 200)
        self.assertEqual(pl.drawing_guid, "d1")

    def test_boxes_from_measured_bounds(self):
        from ashiba.elevation_sections import _drawing_boxes

        class C:
            def get_details(self, made):
                return [{"details": {"bounds": {"xMin": 0.02, "xMax": 0.439, "yMin": 0.1, "yMax": 0.305},
                                     "drawingScale": 0.01, "ratio": 1}}]

        boxes, src = _drawing_boxes(C(), [{"elementId": {"guid": "d"}}])
        self.assertAlmostEqual(boxes[0][0], 41900.0, places=3)
        self.assertAlmostEqual(boxes[0][1], 20500.0, places=3)
        self.assertEqual(src, 0.01)


class TestPlanSheet(unittest.TestCase):
    """足場平面図: 範囲・縮尺・切り抜きの幾何（実機で確かめた関係）."""

    def test_region_covers_scaffold_and_section_lines(self):
        from ashiba.elevation_sections import plan_region_mm

        m = build()
        x0, y0, x1, y1 = plan_region_mm(m)
        specs = section_specs(m, "試験")
        for s in specs:
            for px, py in (s.start_mm, s.end_mm):
                self.assertTrue(x0 <= px <= x1 and y0 <= py <= y1, (s.face_name, px, py))
        self.assertLess(x0, 300000 - CLEARANCE_MM)

    def test_fit_scale(self):
        from ashiba.elevation_sections import fit_scale

        self.assertEqual(fit_scale((41000, 31000), (841.0, 594.0)), 100)
        self.assertEqual(fit_scale((90000, 60000), (841.0, 594.0)), 200)
        self.assertIsNone(fit_scale((500000, 400000), (841.0, 594.0)))

    def test_clip_and_position(self):
        from ashiba.elevation_sections import clipped_drawing_geometry

        clip, pos = clipped_drawing_geometry((295000, 293000, 335000, 327000), 100, (50.0, 80.0))
        self.assertAlmostEqual(clip[0]["x"], 0.05); self.assertAlmostEqual(clip[0]["y"], 0.08)
        self.assertAlmostEqual(clip[2]["x"], 0.45); self.assertAlmostEqual(clip[2]["y"], 0.42)
        # 実機の値: position = 2P − Rmin×k → Tapir の pos = position − clip最小角 = (-2.9, -2.85)
        self.assertAlmostEqual(pos["x"] - clip[0]["x"], -2.9)
        self.assertAlmostEqual(pos["y"] - clip[0]["y"], -2.85)
        # 1/200（比率 0.5）: Tapir の pos = position − clip最小角×0.5 が P − Rmin×k になる
        clip, pos = clipped_drawing_geometry((295000, 293000, 335000, 327000), 200, (50.0, 80.0))
        self.assertAlmostEqual(pos["x"] - clip[0]["x"] * 0.5, 0.05 - 295.0 / 200)


class TestStalePrefixes(unittest.TestCase):
    """工事名を変えて再実行したら、同じ建物の古い名前の断面・レイアウトを片付ける."""

    def test_record_keeps_building_and_prefix(self):
        import tempfile
        from ashiba.elevation_sections import ElevationPlacement, load_record, load_record_meta, save_record, stale_prefixes

        with tempfile.TemporaryDirectory() as d:
            save_record(d, [ElevationPlacement("南面", "旧 南面 足場立面", section_guid="g1")], {}, "300.0,300.0,330.0,320.0", "旧")
            rec = save_record(d, [ElevationPlacement("南面", "他 南面 足場立面", section_guid="g2")], load_record(d),
                              "400.0,300.0,430.0,320.0", "他")
            meta = load_record_meta(d)
            self.assertEqual(load_record(d), {"旧 南面 足場立面": "g1", "他 南面 足場立面": "g2"})   # _meta は混ざらない
            self.assertEqual(stale_prefixes(rec, meta, "300.0,300.0,330.0,320.0", "新"), {"旧": ["旧 南面 足場立面"]})
            self.assertEqual(stale_prefixes(rec, meta, "300.0,300.0,330.0,320.0", "旧"), {})        # 同じ名前は対象外
            self.assertEqual(stale_prefixes(rec, meta, "500.0,300.0,530.0,320.0", "新"), {})        # 別の建物は触らない

    def test_building_key(self):
        from ashiba.elevation_sections import building_key

        self.assertEqual(building_key([(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]),
                         "300.0,300.0,330.0,320.0")


class TestTieMarksAreSectionAnnotations(unittest.TestCase):
    """立面の壁つなぎ ◎ は断面の注記（2重の円の折れ線）で描く。3D には持たせない."""

    def test_each_tie_gets_two_circles_at_its_height(self):
        from ashiba.cli import solve_all
        from ashiba.elevation_sections import TIE_MARK_RADII_M, section_annotations, section_specs, tie_marks

        r = solve_all({"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                       "eaves_height_mm": 15400, "building_height_mm": 16000})
        spec = section_specs(r.model, "T")[0]
        ep = next(e for e in r.model.plan.edges if e.edge_index == spec.edge_index)
        marks = tie_marks(ep, spec, r.model.wall_ties)
        n = sum(1 for t in r.model.wall_ties if t.edge_index == ep.edge_index)
        self.assertEqual(len(marks), n)
        notes = section_annotations(r.model, spec)
        circles = [ln for ln in notes.lines if len(ln) == 25]
        self.assertEqual(len(circles), n * len(TIE_MARK_RADII_M))
        heights = {round(t.height_mm / 1000, 3) for t in r.model.wall_ties if t.edge_index == ep.edge_index}
        centers = {round(sum(p[1] for p in c[:-1]) / 24, 3) for c in circles}
        self.assertEqual(centers, heights)


class TestNotesOnlyIntoSections(unittest.TestCase):
    """断面図が前面に出ないまま注記を書くと平面図に入る。前面が断面図のときだけ書く."""

    def test_open_section_window_checks_the_front_window(self):
        from ashiba.elevation_sections import open_section_window

        class C:
            def __init__(self, kinds):
                self.kinds = list(kinds)
                self.calls = 0

            def tapir(self, cmd, params=None):
                self.calls += 1
                return {}

            def current_window_type(self):
                return self.kinds.pop(0) if self.kinds else "FloorPlan"

        self.assertTrue(open_section_window(C(["FloorPlan", "Section"]), "g", wait_s=0))
        self.assertFalse(open_section_window(C(["FloorPlan"] * 5), "g", tries=3, wait_s=0))
