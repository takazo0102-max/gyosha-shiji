"""壁つなぎ・水平ネット・ネットブラケットを足場ラインとは別の部品で置く（利用者の指定 2026-10-20）."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.attachments import (
    NET_OBJECT,
    NETBK_OBJECT,
    TIE_OBJECT,
    net_heights_mm,
    net_placements,
    net_quantities,
    net_width_mm,
    netbk_arm_mm,
    netbk_clash_faces,
    tie_placements,
)
from ashiba.cli import solve_all

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "series_id": "shinwa_A",
        "eaves_height_mm": 15400, "building_height_mm": 16000}


class TestTies(unittest.TestCase):
    def test_one_part_per_wall_tie_toward_the_building(self):
        r = solve_all(dict(RECT))
        pls = tie_placements(r.model)
        self.assertEqual(len(pls), len(r.model.wall_ties))
        self.assertTrue(all(p.part == TIE_OBJECT for p in pls))
        south = next(e for e in r.model.plan.edges if r.model.face_name(e.edge_index) == "南面")
        t = next(t for t in r.model.wall_ties if t.edge_index == south.edge_index)
        # 取付は作業床の 300 下（床の高さのコマは腕木・ネットブラケットが使う）
        p = next(p for p in pls if abs(p.params["zH"] - (t.height_mm - 300) / 1000) < 1e-9
                 and abs(p.x_mm - (south.start_post[0] + t.position_mm)) < 1e-6)
        self.assertAlmostEqual(p.params["faceAng"], 0.0)                 # 南面は +x へ
        self.assertAlmostEqual(p.y_mm, south.start_post[1])              # 内側建地列の上
        self.assertGreater(p.params["tieL"], south.standoff / 1000)       # 躯体面まで（離れ＋支柱半径）
        self.assertTrue(p.params["tieName"])
        self.assertAlmostEqual(p.params["wallD"], south.standoff / 1000)   # 躯体面で止める（突き抜けない）


class TestNet(unittest.TestCase):
    def test_none_without_levels(self):
        r = solve_all(dict(RECT))
        self.assertEqual(net_placements(r.model), [])
        self.assertEqual(net_quantities(r.model), (0.0, 0))

    def test_nets_and_brackets_per_face_and_level(self):
        r = solve_all({**RECT, "horizontal_net_levels": [2, 5, 99]})
        self.assertEqual(r.model.config.horizontal_net_levels, [2, 5])     # 範囲外は捨てる
        pls = net_placements(r.model)
        nets = [p for p in pls if p.part == NET_OBJECT]
        bks = [p for p in pls if p.part == NETBK_OBJECT]
        faces = len(r.model.plan.edges)
        self.assertEqual(len(nets), 2 * faces)
        self.assertEqual(len(bks), 2 * sum(len(e.spans) for e in r.model.plan.edges))
        lv = r.model.elevation.level_heights
        self.assertEqual(net_heights_mm(r.model), [lv[1] - 50.0, lv[4] - 50.0])   # 床の少し下
        area, n_bk = net_quantities(r.model)
        self.assertEqual(n_bk, len(bks))
        want = sum(p.params["netL"] * p.params["netW"] for p in nets)
        self.assertTrue(math.isclose(area, want, rel_tol=1e-9))

    def test_nl500_reach(self):
        """NL500: 受け板（建地芯から42）から 300〜470mm の伸縮。先端は躯体面の 50mm 手前を狙う."""
        self.assertEqual(netbk_arm_mm(500), (450.0, True))
        self.assertEqual(netbk_arm_mm(392), (342.0, True))
        self.assertEqual(netbk_arm_mm(300), (342.0, False))      # 最短でも躯体に当たる
        self.assertEqual(netbk_arm_mm(900), (512.0, True))       # 全伸で止まる
        self.assertAlmostEqual(net_width_mm(500), 450 - 20 - 120)
        self.assertAlmostEqual(net_width_mm(300), 250 - 20 - 120)  # 当たる面は躯体面のあきまで

    def test_clash_warning_when_standoff_is_small(self):
        r = solve_all({**RECT, "horizontal_net_levels": [2]})
        self.assertTrue(netbk_clash_faces(r.model))                # 既定の離れ 300 では届きすぎる
        self.assertTrue(any("NL500" in w and "躯体に当たります" in w for w in r.quantity.warnings), r.quantity.warnings)
        bk = next(p for p in net_placements(r.model) if p.part == NETBK_OBJECT)
        self.assertAlmostEqual(bk.params["armL"], 0.342)

    def test_quantity_note_and_order(self):
        r = solve_all({**RECT, "horizontal_net_levels": [2]})
        q = r.quantity
        self.assertTrue(any("水平ネットは第2層" in n for n in q.notes), q.notes)
        self.assertTrue(any("水平ネットの部材" in w for w in q.warnings), q.warnings)

    def test_spec_object_round_trip(self):
        from ashiba.spec_object import params_from_spec, spec_from_params

        p = params_from_spec({"horizontal_net_levels": [2, 5]})
        self.assertEqual(p["netLevels"], "2,5")
        self.assertEqual(spec_from_params({"netLevels": "2、5"})["horizontal_net_levels"], [2, 5])
        self.assertNotIn("horizontal_net_levels", spec_from_params({"netLevels": ""}))


class TestNetLabels(unittest.TestCase):
    def test_elevation_and_plan_labels(self):
        from ashiba.elevation_sections import section_annotations, section_specs
        from ashiba.plan_labels import plan_label_items

        r = solve_all({**RECT, "horizontal_net_levels": [2]})
        spec = section_specs(r.model, "T")[0]
        texts = [lb["text"] for lb in section_annotations(r.model, spec, stair_plan=r.stair_plan).labels]
        self.assertIn("水平ネット・ネットブラケット", texts)
        self.assertTrue(any(t.startswith("水平ネット（第2層）") for _x, _y, t in plan_label_items(r.model, r.stair_plan)))


class TestSheets(unittest.TestCase):
    """養生シート（メッシュシート）を足場の外側の構面に張る部品."""

    def test_one_sheet_part_per_face_around_the_corners(self):
        from ashiba.attachments import SHEET_OBJECT, sheet_placements

        r = solve_all(dict(RECT))
        pls = sheet_placements(r.model)
        self.assertEqual(len(pls), len(r.model.plan.edges))
        self.assertTrue(all(p.part == SHEET_OBJECT for p in pls))
        p = pls[0]
        ep = r.model.plan.edges[0]
        d = (r.model.post_row_spacing_mm + 60) / 1000.0
        self.assertAlmostEqual(p.params["x0"], -d)                      # 出隅は角の外まで回す
        self.assertAlmostEqual(p.params["x1"], sum(ep.spans) / 1000.0 + d)
        self.assertAlmostEqual(p.params["zT"], r.model.elevation.total_height / 1000.0)

    def test_none_when_no_sheet(self):
        from ashiba.attachments import sheet_placements, sheet_quantities

        r = solve_all({**RECT, "site": {"sheet_type": "なし"}})
        self.assertEqual(sheet_placements(r.model), [])
        self.assertEqual(sheet_quantities(r.model), (0.0, 0))

    def test_quantity_note(self):
        r = solve_all(dict(RECT))
        self.assertTrue(any(n.startswith("メッシュシート（1.8×5.1m）") for n in r.quantity.notes), r.quantity.notes)


class TestSheetsAroundOutsideStairs(unittest.TestCase):
    def test_sheet_moves_to_the_outside_of_the_stair_bay(self):
        from ashiba.attachments import sheet_segments

        r = solve_all({**RECT, "series_id": "nikken_nd1800", "stairs": {"layout": "outside"}})
        t = r.stair_plan.towers[0]
        ep = next(e for e in r.model.plan.edges if e.edge_index == t.edge_index)
        segs = sheet_segments(r.model, ep, r.stair_plan)
        tower = [s for s in segs if abs(s[0] - t.start_mm) < 1e-6 and abs(s[1] - t.end_mm) < 1e-6]
        self.assertEqual(len(tower), 1)
        self.assertAlmostEqual(tower[0][2], 2 * r.model.post_row_spacing_mm + 60)   # 階段の升目の外
        self.assertEqual(len(segs), 3)


class TestSheetEndsOfOutsideStairs(unittest.TestCase):
    def test_two_end_pieces_per_tower(self):
        from ashiba.attachments import sheet_placements

        r = solve_all({**RECT, "series_id": "nikken_nd1800", "stairs": {"layout": "outside"}})
        pls = sheet_placements(r.model, stair_plan=r.stair_plan)
        faces = len(r.model.plan.edges)
        towers = len(r.stair_plan.towers)
        self.assertEqual(len(pls), faces + 2 * towers + 2 * towers)   # 区間3つ（＋2）と妻側2枚（＋2）
        ends = [p for p in pls if abs(p.params["x1"] - p.params["x0"] - r.model.post_row_spacing_mm / 1000) < 1e-9]
        self.assertEqual(len(ends), 2 * towers)


class TestSheetPanelsFollowTheScaffold(unittest.TestCase):
    """外部シートの割付は足場と同じ（継ぎ目は支柱）。間が開いている部分は特殊シートとして伸ばす（利用者の指定 2026-10-24）."""

    def test_seams_on_posts_and_special_sheets(self):
        from ashiba.attachments import sheet_panels, sheet_placements, special_sheets
        from ashiba.cli import solve_all

        r = solve_all({"outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]], "eaves_height_mm": 9000,
                       "series_id": "nikken_nd1800", "scaffold_width_mm": 914})
        m = r.model
        for ep in m.plan.edges:
            posts = [0.0]
            for sp in ep.spans:
                posts.append(posts[-1] + sp)
            panels = [p for seg in sheet_panels(m, ep, r.stair_plan) for p in seg]
            inner = [a for a, _b, _s in panels[1:]]
            self.assertTrue(all(any(abs(a - p) < 0.5 for p in posts) for a in inner), m.face_name(ep.edge_index))
            # 足場のスパンと同じ幅（インチの 610〜1829 はどれも普通にある）は標準、スパンに無い幅（角・隙間）だけ特殊
            # （利用者の指摘 2026-10-24: インチも普通にあるから特殊シートじゃない）
            for a, b, sp in panels:
                self.assertEqual(sp, not any(abs((b - a) - c) <= 1.0 for c in (610, 914, 1219, 1524, 1829)))
            self.assertFalse(any(sp for a, b, sp in panels[1:-1]))      # 中のスパンは全部標準
        gaps = [c for c in m.plan.corner_steps if c.edge_index >= 0]
        for c in gaps:                                   # 隙間（コーナーステップ）も覆う
            ep = next(e for e in m.plan.edges if e.edge_index == c.edge_index)
            last = [p for seg in sheet_panels(m, ep, r.stair_plan) for p in seg][-1]
            self.assertGreater(last[1], sum(ep.spans) + c.gap_mm)
        self.assertTrue(special_sheets(m, r.stair_plan))
        self.assertTrue(all(p.params.get("panelList") for p in sheet_placements(m, stair_plan=r.stair_plan)))
        self.assertTrue(any("特殊シート" in w for w in r.quantity.warnings))


class TestSheetClamps(unittest.TestCase):
    """シートクランプ（利用者の指定 2026-10-24: シートクランプGDLも作成してつけて）."""

    def test_clamps_on_seams_and_ends(self):
        from ashiba.attachments import (sheet_clamp_count, sheet_clamp_heights, sheet_clamp_positions,
                                        sheet_placements, standard_sheets)
        from ashiba.cli import solve_all

        r = solve_all({"outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]], "eaves_height_mm": 9000,
                       "series_id": "nikken_nd1800", "scaffold_width_mm": 914})
        m = r.model
        ep = m.plan.edges[0]
        hs = sheet_clamp_heights(m, ep.edge_index)
        ev = m.elevation_of(ep.edge_index)
        top = ev.total_height
        # 上から割り付ける（天端から 5160 ずつ下へ）。下端は仮囲いの天端 3000（利用者の指定 2026-10-24）
        self.assertEqual(hs[-1], round(top - 100))
        self.assertEqual(hs[0], 3150)
        self.assertIn(round(top - 5160), hs)
        xs = sheet_clamp_positions(m, ep, r.stair_plan)
        # 継ぎ目（支柱）だけ。出隅の角は両端とも養生クランプ コーナー用（始点はこの面、終点は次の面）
        self.assertEqual(len(xs), len(ep.spans) + 1)
        from ashiba.attachments import sheet_corner_clamp_count

        self.assertEqual(sheet_corner_clamp_count(m, r.stair_plan),
                         sum(len(sheet_clamp_heights(m, e.edge_index)) for e in m.plan.edges))
        self.assertEqual(sheet_clamp_count(m, r.stair_plan),
                         sum(len(sheet_clamp_positions(m, e, r.stair_plan)) * len(sheet_clamp_heights(m, e.edge_index))
                             for e in m.plan.edges))
        pl = next(p for p in sheet_placements(m, stair_plan=r.stair_plan) if p.params.get("panelList"))
        self.assertEqual(pl.params["clampList"], ",".join(f"{h:.0f}" for h in hs))
        self.assertIn(914, standard_sheets(m, r.stair_plan))              # インチの幅も標準のシート
        q = {l.part.model_no: l.qty for l in r.quantity.lines}
        self.assertEqual(q.get("次世代シートクランプ"), sheet_clamp_count(m, r.stair_plan))

    def test_soundproof_sheet_uses_the_maker_sizes(self):
        # 協和 防音シート ♯1000（1.8/1.5/1.2/0.9/0.6×3.4）。インチのスパンには近い幅の品を当てる
        from ashiba.attachments import sheet_size
        from ashiba.cli import solve_all

        r = solve_all({"outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]], "eaves_height_mm": 9000,
                       "series_id": "nikken_nd1800", "scaffold_width_mm": 914, "site": {"sheet_type": "防音シート"}})
        self.assertEqual(sheet_size(r.model), (1800.0, 3400.0))
        q = {l.part.model_no: l.qty for l in r.quantity.lines}
        self.assertGreater(q.get("♯1000 1.8×3.4", 0), 0)
        self.assertGreater(q.get("♯1000 0.9×3.4", 0), 0)
