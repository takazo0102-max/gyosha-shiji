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

    def test_each_kind_is_drawn_in_its_own_shape(self):
        # 利用者の指定 2026-10-27: ロングスパンの詳細度上げて何かわからない 全種類作ってね。種類ごとの形で描く
        d1 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        kinds = {"ロングスパン": 1, "工事用エレベーター": 2, "荷揚げ機": 3}
        for mid, m in load_hoist_models().items():
            block = d1.split(f'if hoModel = "{mid}" then', 1)[1].split("endif", 1)[0]
            self.assertIn(f"hoKind = {kinds[m.kind]}", block, mid)
        for sub in ('"longSpanCage":', '"elevatorCage":', '"liftCage":', '"postMast":', '"latticeMast":'):
            self.assertIn(sub, d3)
        for word in ("ジャバラ扉", "駆動装置", "ガイドローラ", "頭上覆い", "格子マスト", "巻上げ機", "ラック"):
            self.assertIn(word, d3)
        self.assertIn("mx[2] = max(postSp / 2, cageL / 2 + mastW / 2 + 0.05)", d1)   # ポストは荷台の端の外

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

    def test_sheet_opens_at_the_stage_level(self):
        # 荷受けステージの間口は、ステージの層の床から手すりの高さに掛かる段だけ外す（床の少し上の継ぎ目の段は残す）
        from ashiba.attachments import sheet_open_rows, sheet_placements, sheet_rows, sheet_segments, standard_sheets

        st = {**BOX, "loading_stages": [{"edge_index": 0, "start_mm": 3658, "span_count": 2, "levels": [3]}]}
        r = solve_all(st)
        ep = r.model.plan.edges[0]
        rows = sheet_rows(r.model, 0)
        segs = sheet_segments(r.model, ep, r.stair_plan)
        gone = [sheet_open_rows(r.model, ep, a, b, rows) for a, b, _o in segs]
        self.assertEqual([len(g) for g in gone].count(1), 1)               # 間口の区間で1段だけ
        a, b, _o = segs[[len(g) for g in gone].index(1)]
        self.assertEqual((round(a), round(b)), (3658, 7316))
        plain = solve_all(BOX)
        self.assertEqual(standard_sheets(plain.model, plain.stair_plan)[1829] - standard_sheets(r.model, r.stair_plan)[1829], 2)
        pl = next(p for p in sheet_placements(r.model, stair_plan=r.stair_plan)
                  if abs(p.params["x0"] - 3.658) < 1e-3 and abs(p.params.get("x1", 0) - 7.316) < 1e-3)
        self.assertLess(pl.params["zT"], max(h for _l, h in rows) / 1000.0)  # 外した段の上まで膜・線を伸ばさない
        self.assertTrue([n for n in r.quantity.notes if "荷受けステージの間口（" in n])

    def test_outer_bracket_on_the_hoist_spans_is_ng(self):
        # 搬器は外側の列のすぐ外を昇り降りする: 同じスパンに外へ張り出すブラケット区間は当たる（別のスパンなら通す）
        ho = {"hoists": [{"edge_index": 0, "position_mm": 5487, "model": "KSE900-5.4"}]}
        on = solve_all({**BOX, **ho, "bracket_sections": [{"edge_index": 0, "start_mm": 3658, "end_mm": 7316,
                                                          "direction": "張出", "width": 610, "levels": [3]}]})
        self.assertTrue([c for c in on.conflicts if c.kind == "昇降機×ブラケット区間" and c.severity == "NG"])
        self.assertFalse(on.verdict["ok"])
        off = solve_all({**BOX, **ho, "bracket_sections": [{"edge_index": 0, "start_mm": 10974, "end_mm": 12803,
                                                           "direction": "張出", "width": 610, "levels": [3]}]})
        self.assertFalse([c for c in off.conflicts if c.kind == "昇降機×ブラケット区間"])

    def test_stage_on_the_hoist_spans_is_ng(self):
        # ステージも外側の列の外へ張り出す: 搬器が通るスパンに重なれば NG、隣のスパンからなら通す
        ho = {"hoists": [{"edge_index": 0, "position_mm": 5487, "model": "KSE900-5.4"}]}
        on = solve_all({**BOX, **ho, "loading_stages": [{"edge_index": 0, "start_mm": 7316, "span_count": 2, "levels": [3]}]})
        self.assertEqual([c.kind for c in on.conflicts], ["昇降機×ステージ"])
        self.assertFalse(on.verdict["ok"])
        off = solve_all({**BOX, **ho, "loading_stages": [{"edge_index": 0, "start_mm": 9145, "span_count": 2, "levels": [3]}]})
        self.assertFalse([c for c in off.conflicts if c.kind == "昇降機×ステージ"])

    def test_hoist_over_the_site_boundary_is_ng(self):
        # 足場は境界に収まっても、搬器・地上の囲い（足場の外へ 1.4m 前後）が越えれば NG。余裕があれば出さない
        def run(south):
            bnd = [[-3000, -south], [15000, -south], [15000, 11000], [-3000, 11000]]
            return solve_all({**BOX, "site_boundary_mm": bnd,
                              "hoists": [{"edge_index": 0, "position_mm": 5487, "model": "KSE900-5.4"}]})

        near = [c for c in run(1500).conflicts if c.kind == "昇降機×敷地境界"]
        self.assertTrue(near and near[0].severity == "NG")
        self.assertFalse([c for c in run(3500).conflicts if c.kind == "昇降機×敷地境界"])

    def test_stage_over_the_site_boundary_is_ng(self):
        # 荷受けステージの張り出し（出 1500）も境界を越えれば NG。足場だけなら収まる敷地
        def run(south):
            bnd = [[-3000, -south], [15000, -south], [15000, 11000], [-3000, 11000]]
            return solve_all({**BOX, "site_boundary_mm": bnd,
                              "loading_stages": [{"edge_index": 0, "start_mm": 3658, "span_count": 2, "levels": [3]}]})

        r = run(2000)
        self.assertFalse([c for c in r.conflicts if c.kind == "足場×敷地境界" and c.severity == "NG"])
        self.assertTrue([c for c in r.conflicts if c.kind == "ステージ×敷地境界"])
        self.assertFalse([c for c in run(4000).conflicts if c.kind == "ステージ×敷地境界"])

    def test_outer_bracket_over_the_site_boundary_is_ng(self):
        # 張出しブラケットの床（外側建地から 610）も境界を越えれば NG。足場だけなら収まる敷地
        def run(south):
            bnd = [[-3000, -south], [15000, -south], [15000, 11000], [-3000, 11000]]
            return solve_all({**BOX, "site_boundary_mm": bnd, "bracket_sections": [
                {"edge_index": 0, "start_mm": 3658, "end_mm": 7316, "direction": "張出", "width": 610, "levels": [3]}]})

        r = run(1300)
        self.assertFalse([c for c in r.conflicts if c.kind == "足場×敷地境界" and c.severity == "NG"])
        self.assertTrue([c for c in r.conflicts if c.kind == "ブラケット区間×敷地境界"])
        self.assertFalse([c for c in run(1800).conflicts if c.kind == "ブラケット区間×敷地境界"])

    def test_asagao_count_leaves_out_the_hoist_spans(self):
        # 昇降機が通るスパンは朝顔を切り欠く（図の asaCutList と同じ）。数量からも引く
        import json

        spec = json.loads((ROOT / "examples" / "combo_nd1800.json").read_text(encoding="utf-8"))
        from ashiba.cli import solve_groups

        def body(sp):
            r = solve_groups(sp)[0][1]
            return sum(l.qty for l in r.quantity.lines if l.part.category == "朝顔" and "防護棚" in l.part.note), r

        with_h, r = body(spec)
        without_h, _ = body({k: v for k, v in spec.items() if k != "hoists"})
        self.assertEqual(without_h - with_h, 4)                 # 西面 5487〜12803 の 4 スパン×1段
        self.assertTrue([n for n in r.quantity.notes if "朝顔を切り欠くので、数量から引いています" in n])
        self.assertTrue([c for c in r.conflicts if "切り欠いたスパンを引いています" in c.message])

    def test_part_stands_on_the_scaffold_base(self):
        # 足場の立つ面が 0 でないとき、部品は zH だけ持ち上げ、到達高さ・乗り込む床は足場の立つ面から（ほかの部品と同じ）
        r = solve_all({**BOX, "base_height_mm": 1200,
                       "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "KSE900-5.4", "landing_levels": [2]}]})
        p = hoist_placements(r.model, r.platforms)[0]
        self.assertAlmostEqual(p.params["zH"], 1.2)
        self.assertAlmostEqual(p.params["hoReach"], r.model.elevation_of(0).total_height / 1000.0)
        self.assertAlmostEqual(float(p.params["landList"]), r.model.elevation_of(0).level_heights[1] / 1000.0, places=3)
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("add 0, 0, zH", d3)

    def test_intake_on_the_hoist_spans_is_ng(self):
        # 取り入れ口（クレーンの吊り荷を入れる口）が搬器の通るスパンに重なれば NG、外なら通す
        ho = {"hoists": [{"edge_index": 0, "position_mm": 4572, "model": "KSE900-5.4"}]}
        on = solve_all({**BOX, **ho, "intakes": [{"face": "南面", "start_mm": 3658, "span_count": 1, "levels": "3-4"}]})
        self.assertEqual([c.kind for c in on.conflicts], ["取り入れ口×昇降機"])
        self.assertFalse(on.verdict["ok"])
        off = solve_all({**BOX, **ho, "intakes": [{"face": "南面", "start_mm": 10974, "span_count": 1, "levels": "3-4"}]})
        self.assertFalse([c for c in off.conflicts if c.kind == "取り入れ口×昇降機"])

    def test_landing_floor_stops_40mm_short_of_the_cage(self):
        # 利用者の指定 2026-10-27: ステージとロングスパンの離れは40mm以内の規定がある。荷取り床は搬器の床先の手前 30 で止め、
        # 搬器の通り道に入れない（渡し板を搬器の上まで張り出すと通るたびに当たる）。荷取用の金具を手配に出す
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("gapL = 0.03", d3)
        self.assertIn("add xa2, yC0 + gapL, landH[il] + 0.02", d3)
        self.assertNotIn("yC0 - 0.15", d3)
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "KSE900-5.4", "landing_levels": [2, 4]}]})
        self.assertTrue([n for n in r.quantity.notes if "荷取用金具" in n and "（8）" in n and "40mm 以内" in n])
        # 工事用エレベーターは乗り込み口の両端の外側建地から腕で床を受ける（3D と同じ 2 か所/層）
        ev = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "SEC-700-F", "landing_levels": [2, 4]}]})
        self.assertTrue([n for n in ev.quantity.notes if "荷取り床の受け金物" in n and "（4）" in n and "40mm 以内" in n])

    def test_landing_stage_follows_the_fitting_catalog(self):
        # 利用者が渡した PDF（スギコ アルバロングスパンEV荷取用金具 50500）: 金具は梁枠2本の両端の建地に4個（許容 500kg/個）、
        # 梁枠は 2・3 スパン、布材は上部フランジに 1829 ピッチ、ステージ上の全積載 800kg 以下
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "KSE900-5.4", "landing_levels": [2, 4]}]})
        beams = [ln for ln in r.quantity.lines if ln.part.category == "梁枠"]
        self.assertEqual([(ln.part.nominal_dim, ln.qty) for ln in beams], [(5487, 4)])
        msgs = [x.message for x in r.platforms.issues]
        self.assertTrue([m for m in msgs if "800kg" in m and "最大積載荷重を表示" in m])
        self.assertFalse([m for m in msgs if "梁枠（2・3スパン）" in m])
        # 7.2m 型は乗り込み口が 4 スパン以上に掛かり、梁枠（2・3 スパン）で荷取りステージが組めない
        wide = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "SEL-950LK-7.2F", "landing_levels": [2]}]})
        self.assertTrue([x for x in wide.platforms.issues if "梁枠（2・3スパン）" in x.message])
        self.assertFalse([ln for ln in wide.quantity.lines if ln.part.category == "梁枠"])
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        for key in ("yS = yF0 + sy * (rowSp - 0.206 - yF0)", "ころばし", "if nMast = 1 or yC0 + gapL > -0.26 then yF0 = 0.206"):
            self.assertIn(key, d3)
        pl = hoist_placements(r.model, r.platforms)[0]
        self.assertAlmostEqual(pl.params["rowSp"], r.model.row_spacing_of(0) / 1000.0)

    def test_landing_stage_posts_get_wall_ties(self):
        # 荷取用金具の使用上の注意「梁枠支持部の支柱に壁つなぎを設置」: 乗り込み口の両端の建地に、乗り込む層ごと
        from ashiba.ties import _platform_ties

        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "KSE900-5.4", "landing_levels": [2, 4]}]})
        lv = r.model.elevation.level_heights
        got = sorted((t.position_mm, t.height_mm) for t in _platform_ties(r.model, r.platforms) if t.kind == "landing")
        self.assertEqual(got, sorted((x, int(lv[k - 1])) for x in (1829.0, 7316.0) for k in (2, 4)))
        # 梁枠が掛からない（4スパン以上）なら荷取りステージは別計画なので、ここでは足さない
        wide = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": "SEL-950LK-7.2F", "landing_levels": [2]}]})
        self.assertFalse([t for t in _platform_ties(wide.model, wide.platforms) if t.kind == "landing"])

    def test_report_says_how_the_landing_floor_is_built(self):
        # 割付レポートの昇降機の行の下に、乗り込み口の床の組み方と決め（梁枠・40mm・800kg）を出す
        import tempfile

        from ashiba.report import write_report_md

        def report(model_id):
            r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572, "model": model_id, "landing_levels": [2]}]})
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "r.md"
                write_report_md(r.model, r.quantity, r.checks, path, "t", platforms=r.platforms)
                return path.read_text(encoding="utf-8")

        ls = report("KSE900-5.4")
        self.assertIn("荷取りステージ: 荷取用金具4個/層＋梁枠3スパン×2本", ls)
        self.assertIn("全積載800kg以下", ls)
        self.assertIn("梁枠（2・3スパン）が掛からず別計画", report("SEL-950LK-7.2F"))
        self.assertIn("荷取り床: 外側建地から腕で受ける", report("SEC-700-F"))

    def test_cage_barely_touching_a_span_does_not_open_it(self):
        # 1850 の搬器がスパン 1829 の両隣に 10 ずつ掛かるだけで 3 スパン（5.5m）の手すりを外していた。扉は荷台の端より
        # 内側なので、150 以下しか掛からないスパンは開けない
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "SEC-980HS", "landing_levels": [2]}]})
        self.assertEqual(r.platforms.hoists[0].gate_spans(r.model), [2])
        self.assertFalse([x for x in r.platforms.issues if "広く、両端" in x.message])

    def test_gate_warning_names_the_position_that_fits(self):
        # 3m の搬器をスパンの中央に置くと 3 スパン開く。建地の芯に置けば 2 スパンでゲートに収まるので、その位置を示す
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "DECK-3.0-F", "landing_levels": [2]}]})
        msg = [x.message for x in r.platforms.issues if "広く、両端" in x.message]
        self.assertTrue(msg and "3658mm にずらせば2スパン" in msg[0], msg)
        ok = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 3658, "model": "DECK-3.0-F", "landing_levels": [2]}]})
        self.assertFalse([x for x in ok.platforms.issues if "広く、両端" in x.message])

    def test_landing_above_the_reach_is_ng(self):
        # 到達高さを下げたのに上の層の乗り込み口が残っていると、搬器が届かない口に扉と金物を手配することになる
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE-990",
                                          "reach_height_mm": 4000, "landing_levels": [2, 4]}]})
        ng = [x.message for x in r.platforms.issues if x.severity == "NG" and "搬器が届きません" in x.message]
        self.assertTrue(ng and "[4]" in ng[0], ng)
        ok = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE-990", "landing_levels": [2, 4]}]})
        self.assertFalse([x for x in ok.platforms.issues if "搬器が届きません" in x.message])

    def test_long_span_bay_has_no_scaffold_above_or_below_the_stage(self):
        # 利用者の指摘 2026-10-28: ステージの上下は足場ないよ（施工写真: ロングスパンの前の足場は全高で抜き、両隣の足場の間に
        # 各階の荷取りステージだけが掛かる）。乗り込み口のスパンを昇降路として全高で抜く（支柱・床・手すり・幅木・壁つなぎ）。
        # 梁枠は入れず、両隣の足場の端は妻面のブレス材・幅木で囲う
        from ashiba.openings import VOID_HEIGHT_MM

        # 比べる相手も昇降機あり（階段室・屋上への渡りは昇降機の面を避けて別の面へ移るので、無しと比べると床がずれる）
        none = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "SEC-700-F", "landing_levels": [2, 4]}]})
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE900-5.4", "landing_levels": [2, 4]}]})
        voids = [o for o in r.openings.openings if o.void]
        self.assertEqual([(o.edge_index, o.start_mm, o.beam_span_mm) for o in voids], [(0, 1829.0, 5487)])
        self.assertTrue(r.verdict["ok"], r.verdict.get("blockers"))

        def qty(res, cat, dim):
            return sum(ln.qty for ln in res.quantity.lines if ln.part.category == cat and ln.part.nominal_dim == dim)

        n_lv = r.model.elevation_of(0).n_levels
        self.assertEqual(qty(none, "踏板", 1829) - qty(r, "踏板", 1829), 3 * n_lv)       # 3スパン×全層の床
        # 幅木: エレベーターの側も乗り込み口（1スパン×2層）は外してあるので、差は 3スパン×全層 − 2
        self.assertEqual(qty(none, "幅木", 1829) - qty(r, "幅木", 1829), 3 * n_lv - 2)
        self.assertEqual(qty(none, "ジャッキ", 400) - qty(r, "ジャッキ", 400), 2 * 2)   # 中の支柱2本×内外
        # 梁枠は荷取りステージの分（2本×乗り込む2層）だけで、昇降路には入れない
        self.assertEqual(qty(r, "梁枠", 5487), 4)
        self.assertFalse([t for t in r.model.wall_ties if t.edge_index == 0 and 1829 + 1 < t.position_mm < 7316 - 1])
        # 足場の線の部品へは 999m の「梁下高さ」で渡す（全高で抜く・梁枠を描かない）
        from ashiba.gdl_params import _beam_list

        ep = next(e for e in r.model.plan.edges if e.edge_index == 0)
        self.assertEqual(_beam_list(r.model, ep, r.openings), f"1829,5487,{int(VOID_HEIGHT_MM)}")
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("if bBase < 900 and not(explodeMask", d3)
        # 梁枠が掛からない乗り込み口（4スパン以上）・エレベーターは抜かない
        for m in ("SEL-950LK-7.2F", "SEC-700-F"):
            w = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": m, "landing_levels": [2]}]})
            self.assertFalse([o for o in w.openings.openings if o.void], m)

    def test_stair_in_the_hoist_bay_is_ng(self):
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE900-5.4", "landing_levels": [2]}],
                       "loading_stages": [{"edge_index": 0, "start_mm": 3658, "span_count": 1, "levels": [3]}]})
        self.assertTrue([c for c in r.conflicts if c.kind == "荷受けステージ×昇降路" and c.severity == "NG"])

    def test_long_span_needs_scaffold_on_both_sides(self):
        # 利用者の指摘 2026-10-28: ロングスパンの横には足場いるよ。昇降フレームは両横の足場の建枠にクランプで上下2か所留め、
        # 壁つなぎも両横の足場から取る（三葉工業 NSE-800 組立手順書）。昇降路が面の端に掛かれば NG
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 2743.5, "model": "KSE900-5.4", "landing_levels": [2]}]})
        self.assertTrue([x for x in r.platforms.issues if x.severity == "NG" and "始点側に足場がありません" in x.message])
        self.assertFalse(r.verdict["ok"])
        ok = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE900-5.4", "landing_levels": [2]}]})
        self.assertFalse([x for x in ok.platforms.issues if "足場がありません" in x.message])
        # 両横の足場の昇降路側の支柱は端部。荷受けステージは1スパン以上離す（杉孝 Q&A）
        st = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE900-5.4", "landing_levels": [2]}],
                        "loading_stages": [{"edge_index": 0, "start_mm": 7316, "span_count": 1, "levels": [3]}]})
        self.assertTrue([c for c in st.conflicts if c.kind == "荷受けステージ×昇降路" and "端部" in c.message])

    def test_long_span_mast_is_fixed_with_tubes_to_the_side_scaffold(self):
        # 利用者の指定 2026-10-28: マストは支柱の外に単管を横引き2段、縦の単管を2列配置してマストと固定する
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_hoist" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        for key in ("for t2 = 0 to 1", "zh = zt - 0.25 + t2 * 0.50", "yv = my[im] + (2 * cv - 1) * (mastW / 2 + 0.03)"):
            self.assertIn(key, d3)
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE900-5.4", "landing_levels": [2]}]})
        notes = [n for n in r.quantity.notes if "マスト固定" in n]
        n_fix = int(r.platforms.hoists[0].reach_mm(r.model) // 3600)
        self.assertTrue([n for n in notes if "横引き単管" in n and f"（{2 * n_fix * 2}）" in n], notes)
        self.assertTrue([n for n in notes if "縦の単管" in n])
        self.assertTrue([n for n in notes if "直交クランプ" in n and f"（{4 * 2 * n_fix * 2}）" in n], notes)
        # エレベーター（マスト1本の格子マスト）は従来の控え
        ev = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "SEC-700-F", "landing_levels": [2]}]})
        self.assertFalse([n for n in ev.quantity.notes if "マスト固定" in n])

    def test_unknown_model_is_an_input_error(self):
        from ashiba.cli import InputError

        with self.assertRaises(InputError):
            solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 6000, "model": "XYZ"}]})

    def test_placement_sits_on_the_outer_row(self):
        # 枠組の両端が建地に乗る位置（3スパン 1829〜7316 の中央）
        r = solve_all({**BOX, "hoists": [{"edge_index": 0, "position_mm": 4572.5, "model": "KSE-990",
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
        self.assertIn("nJ = max(2, int((gB - gA) / 0.27 + 0.5))", h3)   # 乗り込み口いっぱいのアコーディオン式の格子
        self.assertIn("荷取り床", h3)


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
        # 枠組の無い機種は、乗り込み口のスパンがいちばん少ない位置へ寄せる（3000 では 3300 の荷台が 3 スパンに掛かる。
        # 建地の芯 3658 なら 2 スパン）
        self.assertEqual(hs, [{"edge_index": 1, "position_mm": 3658.0, "model": "KSE600L", "landing_levels": [2, 4]}])
        from ashiba.platforms import spans_under_cage

        self.assertEqual(len(spans_under_cage(e1.spans, 3000.0, 3300.0)), 3)
        self.assertEqual(len(spans_under_cage(e1.spans, 3658.0, 3300.0)), 2)
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
