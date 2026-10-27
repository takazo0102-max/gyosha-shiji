"""昇降機の機種表・部品 ashiba_hoist（利用者の指定 2026-10-27: 建機サービスの図面から機種表にする・フロアーゲートを描いて
数える・機種ごとの形を3Dで描く・昇降機は別オブジェクトで配置できるように）."""

import json
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import HOIST_OBJECT, hoist_placements
from ashiba.cli import solve_all
from ashiba.hoist_models import FLOOR_GATES, hoist_model, load_hoist_models
from ashiba.hoist_objects import hoists_from_objects

ROOT = Path(__file__).resolve().parents[1]
BOX = {"project_name": "昇降機", "outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]],
       "eaves_height_mm": 9000, "series_id": "nikken_nd1800", "module": "inch"}


class TestCatalog(unittest.TestCase):
    def test_every_drawing_is_in_the_table(self):
        ms = load_hoist_models()
        for mid in ("KSE600C", "KSE900-5.4", "KSE-990", "HSL-900C2-7.2", "HSL-900B-5.4", "HSL950L2", "KRD800-5.4",
                    "KRD950-7.2", "NSE800", "HCE990GL", "SL-240B"):
            self.assertIn(mid, ms)
            self.assertTrue(ms[mid].source)
        self.assertEqual(hoist_model("kse900-5.4").cage_len_mm, 4800)
        self.assertEqual(hoist_model("KSE900-5.4").masts, 2)
        self.assertEqual(hoist_model("KSE600C").masts, 1)
        self.assertIsNone(hoist_model("なし"))
        # 図面の寸法線・寸法の文字から（2026-10-27 読み直し）: KSE900-7.2 の荷台は 6600（仕様表は 5.4 型の流用）、
        # HSL の荷台は枠組の両側 315 ずつ内（有効長＝枠組−1130 は内のり）
        self.assertEqual(hoist_model("KSE900-7.2").cage_len_mm, 6600)
        self.assertEqual((hoist_model("HSL-900B-7.2").cage_len_mm, hoist_model("HSL-900B-7.2").cage_in_len_mm), (6570, 6070))
        self.assertEqual((hoist_model("HSL-900C2-7.2").cage_len_mm, hoist_model("HSL-900C2-7.2").post_spacing_mm),
                         (6570, 6690))

    def test_gate_opens_the_cage(self):
        # フロアーゲートは荷台の長さより広い有効開口のものを選んである（7.2 スパンは長い荷台）
        for m in load_hoist_models().values():
            if m.gate:
                self.assertIn(m.gate, FLOOR_GATES)
                if m.gate == "4.5":
                    self.assertLessEqual(m.cage_len_mm, FLOOR_GATES["7.2"]["opening_mm"])

    def test_generated_part_matches_the_table(self):
        vl = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "vl.gdl").read_text(encoding="utf-8")
        d1 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        for mid in load_hoist_models():
            self.assertIn(f'"{mid}"', vl)
            self.assertIn(f'if hoModel = "{mid}" then', d1)
        # 値の一覧の1行が長いと Tapir がパラメータを読み書きできない（6機種ごとに改行）
        self.assertTrue(all(len(line) < 160 for line in vl.splitlines()))


class TestHoistInput(unittest.TestCase):
    def test_model_fills_the_cage_load_and_ties(self):
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE900-5.4",
                                          "landing_levels": [2, 4]}]})
        h = r.platforms.hoists[0]
        self.assertEqual((h.cage_width_mm, h.cage_depth_mm), (4800, 1030))
        self.assertAlmostEqual(h.load_kn, 900 * 9.80665 / 1000)
        notes = [str(n) for n in r.quantity.notes]
        self.assertTrue([n for n in notes if "昇降機 本体 KSE-900 5.4m" in n])
        self.assertTrue([n for n in notes if "フロアーゲート 7.2スパン" in n and "（2）" in n])
        self.assertFalse([n for n in notes if "開閉式手すり" in n and "マスタにありません" in n])
        # 詳細図の説明に機種と乗り込み口の防護（フロアーゲート）を出す
        reason = next(sheet.reason for sheet in r.detail_sheets if getattr(sheet, "key") == "hoist")
        self.assertIn("KSE-900 5.4m", reason)
        self.assertIn("フロアーゲート 7.2スパン", reason)
        # 地上の昇降路の囲い（搬器の下への立入禁止）も手配に出す
        self.assertTrue([n for n in notes if "昇降路の囲い" in n and "立入禁止" in n])

    def test_part_draws_the_ground_fence(self):
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        d2 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("if showFence then", d3)
        self.assertIn("cylind 1.8, 0.0243", d3)
        self.assertIn("line2 -fX, fY, fX, fY", d2)
        self.assertNotIn("atn2", d3)                 # GDL に atn2 は無い
        # マストの壁つなぎは到達高さ（足場の天端）まで。数量の本数（到達高さ÷間隔）と同じ
        self.assertIn("while zt < hoReach + 0.001 do", d3)
        # GDL は大文字小文字を区別しない: マスターの配列（dim）と同じ名前を平面・3D で値に使うと、その画が止まって白紙になる
        # （tieList の配列 tX が平面の文字 tx とぶつかって平面が白紙だった）
        import re

        d1 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        for name in re.findall(r"^dim (\w+)\[", d1, re.M):
            for body in (d2, d3):
                self.assertIsNone(re.search(rf"^\s*{name}\s*=", body, re.M | re.I), name)
        self.assertNotIn("while zt < mastH - 0.5 do", d3)

    def test_sheet_is_left_off_the_hoist_spans(self):
        # 乗り込み口のスパン（荷台の長さに掛かるスパン）は外部シートを張らない。数量の注記にも出す
        from ashiba.attachments import sheet_panels, sheet_segments
        from ashiba.platforms import hoist_cut_ranges

        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 5487, "model": "KSE900-5.4"}]})
        ep = r.model.plan.edges[0]
        (c0, c1), = hoist_cut_ranges(r.model, 0, r.platforms.hoists)
        segs = sheet_segments(r.model, ep, r.stair_plan)
        self.assertFalse([s for s in segs if s[0] < c1 - 1 and s[1] > c0 + 1])
        self.assertFalse([p for ps in sheet_panels(r.model, ep, r.stair_plan) for p in ps if p[0] < c1 - 1 and p[1] > c0 + 1])
        self.assertTrue([n for n in r.quantity.notes if "乗り込み口のスパン" in n and f"{c0:.0f}〜{c1:.0f}" in n])
        plain = solve_all(BOX)
        covered = sum(min(s[1], c1) - max(s[0], c0) for s in sheet_segments(plain.model, plain.model.plan.edges[0],
                                                                          plain.stair_plan) if s[0] < c1 and s[1] > c0)
        self.assertAlmostEqual(covered, c1 - c0, delta=1)            # 昇降機が無ければ同じ区間に張る

    def test_unknown_model_is_an_input_error(self):
        from ashiba.cli import InputError

        with self.assertRaises(InputError):
            solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "XYZ"}]})

    def test_placement_sits_on_the_outer_row(self):
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE-990",
                                          "landing_levels": [3]}]})
        pls = hoist_placements(r.model, r.platforms)
        self.assertEqual(len(pls), 1)
        p = pls[0]
        self.assertEqual(p.part, HOIST_OBJECT)
        ep = r.model.plan.edges[0]
        row = r.model.row_spacing_of(0)
        self.assertAlmostEqual(p.y_mm, ep.start_post[1] - row, delta=1)
        self.assertEqual(p.params["hoModel"], "KSE-990")
        self.assertEqual(p.params["landLevels"], "3")
        self.assertEqual(len(p.params["landList"].split(",")), 1)
        # 乗り込み口は足場の手すりを外したスパンの端から端（荷台の長さより広い）
        h = r.platforms.hoists[0]
        gs = h.gate_spans(r.model)
        width = sum(ep.spans[k] for k in gs) / 1000.0
        self.assertAlmostEqual(p.params["gateB"] - p.params["gateA"], width, places=3)
        self.assertLess(p.params["gateA"], -h.cage_width_mm / 2000.0 + 1e-6)
        self.assertGreater(p.params["gateB"], h.cage_width_mm / 2000.0 - 1e-6)

    def test_line_part_leaves_the_hoist_to_its_own_part(self):
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertNotIn("ロングスパンエレベーター（マスト2本", d3)
        self.assertNotIn("開閉式手すり（枠", d3)
        h3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("cylind gB - gA, 0.0243", h3)
        self.assertIn("渡し板", h3)


class TestModelChecks(unittest.TestCase):
    def _issues(self, spec):
        r = solve_all(spec)
        return [i.message for i in r.platforms.issues if i.kind == "昇降機"]

    def test_lift_over_the_model_is_ng(self):
        # SL-240B は揚程 60m。到達 65m（足場の上の控えの検討は別）は機種では届かない
        msgs = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "SL-240B",
                                                "reach_height_mm": 65000}]})
        self.assertTrue([m for m in msgs if "最大揚程60m" in m])
        ok = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE900-5.4"}]})
        self.assertFalse([m for m in ok if "最大揚程" in m])

    def test_opening_wider_than_the_gate_warns(self):
        # KSE600C は 4.5 スパンのフロアーゲート。荷台 2.4m 前後でも支柱の上に立てると 2スパン（3.6m）で収まる。
        # 位置をスパンの途中にずらし、荷台の長さを伸ばした入力で 3スパン（5.4m）にかかると 4.5 では塞げない
        ok = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 5400, "model": "KSE600C"}]})
        self.assertFalse([m for m in ok if "すき間が残ります" in m])
        ng = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6300, "model": "KSE600C",
                                              "cage_width_mm": 4000}]})
        self.assertTrue([m for m in ng if "すき間が残ります" in m and "4.5スパン" in m])

    def test_long_span_frame_sits_on_the_posts(self):
        # ロングスパンは足場の建枠の間に組む: 5400（インチ 5490）＝3 スパン。枠組の両端が建地に乗る位置だけ黙って通す
        from ashiba.platforms import frame_runs

        self.assertEqual(frame_runs([1800, 1800, 1800, 1800], 5400), [(0, 2, 2700.0), (1, 3, 4500.0)])
        self.assertEqual([r[:2] for r in frame_runs([1829, 1829, 1829], 5400)], [(0, 2)])      # インチ 5487
        self.assertEqual(frame_runs([1829, 1219, 1829], 5400), [])
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE900-5.4"}]})
        ep = r.model.plan.edges[0]
        runs = frame_runs(ep.spans, 5400)
        msgs = [i.message for i in r.platforms.issues if i.kind == "昇降機"]
        on = min((c for _i, _j, c in runs), key=lambda c: abs(c - 6000))
        if abs(on - 6000) > 50:
            self.assertTrue([m for m in msgs if f"から {on:.0f}mm に" in m])
        ok = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": on, "model": "KSE900-5.4"}]})
        self.assertFalse([m for m in ok if "建地に乗りません" in m or "合う続きのスパン" in m])
        # 荷台（枠組−600）は 3 スパンにちょうど収まり、乗り込み口の開口も 3 スパン
        r2 = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": on, "model": "KSE900-5.4"}]})
        self.assertEqual(len(r2.platforms.hoists[0].gate_spans(r2.model)), 3)

    def test_long_span_ties_go_to_the_frame_posts(self):
        # ロングスパンの控えは枠組の両端の足場の建地に取る（ポスト芯々の 2400 は建地の間の布材の上になる）
        from ashiba.platforms import frame_runs
        from ashiba.ties import _platform_ties

        r0 = solve_all(BOX)
        ep = r0.model.plan.edges[0]
        i, j, c = min(frame_runs(ep.spans, 5400), key=lambda t: abs(t[2] - 6000))
        posts = [0.0]
        for sp in ep.spans:
            posts.append(posts[-1] + float(sp))
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": c, "model": "KSE900-5.4"}]})
        xs = {t.position_mm for t in _platform_ties(r.model, r.platforms) if t.kind == "hoist"}
        self.assertEqual(xs, {posts[i], posts[j + 1]})

    def test_goods_only_hoist_says_no_riders(self):
        msgs = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "SL-240B"}]})
        self.assertTrue([m for m in msgs if "荷揚げ専用で人は乗れません" in m])
        ok = self._issues({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "KSE-990"}]})
        self.assertFalse([m for m in ok if "荷揚げ専用" in m])


class TestReadPlacedObjects(unittest.TestCase):
    def test_object_snaps_to_the_nearest_face(self):
        from ashiba.cli import solve_groups

        g = solve_groups(BOX)
        m = g[0][1].model
        e1 = next(e for e in m.plan.edges if e.edge_index == 1)       # 東面
        x = e1.start_post[0] + m.row_spacing_of(1) + 900            # 外側の列から 900 外
        y = e1.start_post[1] + 3000
        hs, notes = hoists_from_objects([(None, (x, y), {"hoModel": "KSE600L", "landLevels": "2,4"})], g)
        self.assertEqual(hs, [{"edge_index": 1, "position_mm": 3000.0, "model": "KSE600L", "landing_levels": [2, 4]}])
        # ロングスパンの部品は枠組の両端が建地に乗る位置へ寄せる
        from ashiba.platforms import frame_runs

        e0 = next(e for e in m.plan.edges if e.edge_index == 0)
        c = min((c for _i, _j, c in frame_runs(e0.spans, 5400)), key=lambda c: abs(c - 5000))
        x0 = e0.start_post[0] + 5000
        y0 = e0.start_post[1] - m.row_spacing_of(0) - 900
        ls, _ = hoists_from_objects([(None, (x0, y0), {"hoModel": "KSE900-5.4"})], g)
        self.assertEqual(ls[0]["edge_index"], 0)
        self.assertAlmostEqual(ls[0]["position_mm"], c, delta=0.1)
        far, n2 = hoists_from_objects([(None, (x + 20000, y), {"hoModel": "KSE600L"})], g)
        self.assertEqual(far, [])
        self.assertTrue(n2)


if __name__ == "__main__":
    unittest.main()
