"""平面図の部材名ラベル（引出線つき）: 部材を指し、文字は足場の外（寸法の外）に並ぶ."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.plan_labels import (
    load_label_record,
    plan_label_items,
    plan_labels,
    remove_plan_labels,
    save_label_record,
)

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
        "eaves_height_mm": 15400, "building_height_mm": 16000}


class TestPlanLabels(unittest.TestCase):
    def setUp(self):
        self.r = solve_all(dict(RECT))

    def test_items(self):
        texts = [t for _x, _y, t in plan_label_items(self.r.model, self.r.stair_plan)]
        self.assertFalse(any(t.startswith("壁つなぎ") for t in texts), texts)   # GDL のラベル（tieTxt）が描く
        self.assertIn("建地（支柱）", texts)
        # 作業床は足場ラインの GDL のラベルが面ごとに描く（Python のラベルでは二重にしない）
        self.assertFalse(any(t.startswith("作業床") for t in texts), texts)
        g2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl").read_text(
            encoding="utf-8")
        self.assertIn("if lblOn and strlen(typeTxt) > 0 and pxB - pxA > 3.0 then", g2)
        from ashiba.gdl_params import label_texts
        lt = label_texts(self.r.model)
        self.assertEqual(lt["deckTxt"].split(" ")[0], "踏板")
        self.assertTrue(lt["tieTxt"].startswith("壁つなぎ "), lt)
        # 北・西を向く面では棚を逆に出し、文字を 180° 回す（上下逆に読めていた）
        self.assertIn("lbF = (SYMB_ROTANGLE > 90.001 and SYMB_ROTANGLE < 270.001)", g2)
        self.assertIn("986:", g2)
        self.assertEqual(sum(1 for t in texts if "階段" in t), self.r.stair_plan.count)

    def test_text_rows_are_outside_the_scaffold_and_dimensions(self):
        from ashiba.plan_labels import outward_extra_m

        labels = plan_labels(self.r.model, self.r.stair_plan)
        self.assertTrue(labels)
        out = 0.3 + 0.6 + outward_extra_m(self.r.model) + 1.9      # 離れ＋建地＋張り出し＋寸法
        for lb in labels:
            y = lb["end"][1]
            self.assertTrue(y < -out or y > 20.0 + out, lb)
            self.assertTrue(-1.0 - outward_extra_m(self.r.model) <= lb["beg"][1] <= 21.0, lb)    # 矢先は足場の上

    def test_labels_in_one_row_do_not_overlap(self):
        from ashiba.elevation_sections import label_text_width_m

        labels = plan_labels(self.r.model, self.r.stair_plan)
        rows = {}
        for lb in labels:
            rows.setdefault(round(lb["mid"][1], 3), []).append(lb)
        for row in rows.values():
            row.sort(key=lambda lb: lb["mid"][0])
            for a, b in zip(row, row[1:]):
                self.assertLess(a["mid"][0] + label_text_width_m(a["text"], 0.25), b["mid"][0])


class TestLabelRecord(unittest.TestCase):
    """平面のラベルは建物ごとに GUID を控え、次の配置・撤去で消す."""

    def test_save_load_remove(self):
        class Client:
            deleted = []

            def delete_elements(self, els):
                Client.deleted.extend(e["elementId"]["guid"] for e in els)

        with tempfile.TemporaryDirectory() as d:
            save_label_record(d, "A", ["g1", "g2"])
            save_label_record(d, "B", ["g3"])
            self.assertEqual(load_label_record(d), {"A": ["g1", "g2"], "B": ["g3"]})
            self.assertEqual(remove_plan_labels(Client(), d, "A"), 2)
            self.assertEqual(Client.deleted, ["g1", "g2"])
            self.assertEqual(load_label_record(d), {"B": ["g3"]})
            self.assertEqual(remove_plan_labels(Client(), d), 1)
            self.assertEqual(load_label_record(d), {})


class TestPlanDimensions(unittest.TestCase):
    """平面のスパン寸法は寸法ツール（関連寸法）で、足場ラインの支柱のホットスポット（1〜nSpan+1）を指す."""

    def test_two_dimensions_per_face(self):
        from ashiba.plan_labels import SPAN_DIM_OUT_M, plan_dimension_data

        r = solve_all(dict(RECT))
        lines = [{"elementId": {"guid": f"G{i}"}} for i in range(len(r.model.plan.edges))]
        data = plan_dimension_data(r.model, lines)
        # スパン・全長が面ごとに2本、その後ろに離れ寸法（躯体〜内側建地列）が面ごとに2本
        self.assertEqual(len(data), 4 * len(lines))
        nl = len(lines)
        for k, ep in enumerate(r.model.plan.edges):
            n = len(ep.spans) + 1
            a, b = data[2 * nl + 2 * k], data[2 * nl + 2 * k + 1]
            self.assertEqual([w["inIndex"] for w in a["witnessPoints"]], [n + 3, n + 4])
            self.assertEqual([w["inIndex"] for w in b["witnessPoints"]], [n + 5, n + 6])
        self.assertAlmostEqual(data[2 * nl]["direction"]["y"], 1.0)        # 南面の離れ寸法は面に直交（躯体側 +y）

        for k, ep in enumerate(r.model.plan.edges):
            spans, total = data[2 * k], data[2 * k + 1]
            # 長方形は四隅とも出隅: 始点の角の支柱（nSpan+2）→ 支柱 1〜nSpan+1 → 終点の角の支柱（nSpan+3）
            n = len(ep.spans) + 1
            # 隅の隙間（コーナーステップ）がある面は、隙間の端（nSpan+8・nSpan+9）も並びに入る（2026-10-24）
            from ashiba.gdl_params import corner_gaps_m

            gp = corner_gaps_m(r.model, ep.edge_index)
            exp = ([n + 1] + ([n + 8] if gp["gapS"] > 0 else []) + list(range(1, n + 1))
                   + ([n + 7] if gp["gapE"] > 0 else []) + [n + 2])
            self.assertEqual([w["inIndex"] for w in spans["witnessPoints"]], exp)
            self.assertEqual([w["inIndex"] for w in total["witnessPoints"]], [n + 1, n + 2])
            self.assertTrue(all(w["elementId"]["guid"] == f"G{k}" for w in spans["witnessPoints"]))
        # 南面（辺0, +x 方向）: 寸法線は外側（-y）へ、建地列＋朝顔の出＋0.9m
        south = data[0]
        self.assertAlmostEqual(south["direction"]["x"], 1.0)
        self.assertLess(south["referencePoint"]["y"], r.model.plan.edges[0].start_post[1] / 1000.0 - SPAN_DIM_OUT_M)

    def test_corner_gap_is_in_the_span_chain(self):
        """隙間部分も寸法に（利用者の指定 2026-10-24）: くさびの隅の隙間がある面は、最後の支柱→隙間の先→隅の外側の支柱."""
        from ashiba.plan_labels import plan_dimension_data

        r = solve_all({"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 9000})
        self.assertTrue(r.model.plan.corner_steps)
        lines = [{"elementId": {"guid": f"G{i}"}} for i in range(len(r.model.plan.edges))]
        data = plan_dimension_data(r.model, lines)
        ep = r.model.plan.edges[0]
        n = len(ep.spans) + 1
        idx = [w["inIndex"] for w in data[0]["witnessPoints"]]
        self.assertEqual(idx[-3:], [n, n + 7, n + 2])
        g2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("hotspot2 xh + gapE + rowW * cornerE, -rowW", g2)
        c2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_cstep" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("line2 0, -rowW, gapL, -rowW", c2)                     # 隙間の区間にも建地列の線


class TestTypeLabelOnShortFaces(unittest.TestCase):
    """小さい建物で種類の名前が隅で重なる（7×5m、2026-10-24 実機）→ 空きの無い面は書かず、1つは必ず書く."""

    def test_small_building_has_one_type_label(self):
        from ashiba.gdl_params import label_positions

        r = solve_all({"outline_mm": [[0, 0], [7000, 0], [7000, 5000], [0, 5000]], "eaves_height_mm": 6000})
        at = [label_positions(r.model, e, r.stair_plan, r.openings, r.platforms)["lblAt"] for e in r.model.plan.edges]
        self.assertEqual(sum(1 for a in at if a >= 0), 1)
        self.assertTrue(all(a >= 0 or a == -2.0 for a in at))
        g2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("if lblAt > -1.5 then", g2)


class TestLabelPositions(unittest.TestCase):
    def test_labels_keep_off_section_markers_and_corners(self):
        """平面の GDL ラベルは断面図の切断線（とその端のマーカー）と面の両端を避けて置く."""
        from ashiba.elevation_sections import label_text_width_m
        from ashiba.gdl_params import (LABEL_AVOID_CUT_MM, LABEL_CORNER_MM, LABEL_TEXT_H_M, _cut_crossings,
                                       label_positions, label_texts)

        r = solve_all({"outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]], "eaves_height_mm": 9000})
        south = r.model.plan.edges[0]
        L = sum(south.spans)
        cuts = _cut_crossings(r.model, south, r.stair_plan, r.openings, r.platforms)
        self.assertTrue(cuts)
        pos = label_positions(r.model, south, r.stair_plan, r.openings, r.platforms)
        tx = label_texts(r.model)
        w = (0.4 + max(label_text_width_m(tx["typeTxt"], LABEL_TEXT_H_M),
                       label_text_width_m(tx["deckTxt"], LABEL_TEXT_H_M)) + 0.2) * 1000.0
        a, b = pos["lblAt"], pos["lblAt"] + w                       # 南面は 180° 回さない（棚は終点の側へ）
        self.assertGreaterEqual(a, LABEL_CORNER_MM)
        self.assertLessEqual(b, L - LABEL_CORNER_MM)
        for c in cuts:
            self.assertFalse(a < c + LABEL_AVOID_CUT_MM and b > c - LABEL_AVOID_CUT_MM, (a, b, c))
        g2 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "2d.gdl").read_text(
            encoding="utf-8")
        self.assertIn("if lblAt >= 0 and lblAt / 1000 >= pxA and lblAt / 1000 <= pxB then lbAx = lblAt / 1000", g2)


class TestInnerFaceRow(unittest.TestCase):
    def test_stair_on_an_inner_face_is_labelled_outside_that_face(self):
        """L 字の入隅の北面の階段は、その面の外の列にラベル（建物の上の段まで引出線を引いていた）."""
        from ashiba.plan_labels import plan_labels

        L = [[0, 0], [24000, 0], [24000, 8000], [12000, 8000], [12000, 16000], [0, 16000]]
        r = solve_all({"outline_mm": L, "eaves_height_mm": 9000})
        labels = plan_labels(r.model, r.stair_plan)
        inner = [lb for lb in labels if 7.5 < lb["beg"][1] < 9.5]
        self.assertTrue(inner, labels)
        for lb in inner:
            self.assertLess(lb["mid"][1], 16.0)                      # 建物の北端より下（その面の外の列）
            self.assertLess(abs(lb["mid"][1] - lb["beg"][1]), 6.0)
