"""2026-10-26 の実機の指摘（利用者: リサーチして しっかり確認してよ・・ 単管足場の位置も屋上の渡りも適当だな）で直したところ."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, solve_groups

SQ = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
# 利用者の建物の形（南面だけ本足場、東面は下屋の単管抱き足場、北・西は一側足場。屋根は東の下屋 3.0m）
USER = {"outline_mm": SQ, "module": "inch", "scaffold_width_mm": 610, "eaves_height_mm": 15400,
        "face_eaves_mm": {"東面": 3000}, "face_forms": "東面=単管抱き足場;北面=一側足場;西面=一側足場"}


class TestHugMeetsItsNeighbours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = solve_groups(USER)
        cls.hug = next(r for lb, r in cls.g if "抱き" in lb).model
        cls.rigid = [r.model for lb, r in cls.g if "抱き" not in lb]

    def test_corner_posts_are_the_neighbours_posts(self):
        # 単管の始点・終点の建地は、隣の組（本足場・一側足場）の端の建地と同じ位置（70 ずれて2本立っていた）
        (ep,) = self.hug.plan.edges
        ends = [p for m in self.rigid for e in m.plan.edges for p in (e.start_post, e.end_post)]
        for pt in (ep.start_post, ep.end_post):
            self.assertLess(min(math.dist(pt, q) for q in ends), 1.0, pt)

    def test_shared_corner_posts_are_drawn_once(self):
        self.assertEqual(self.hug.skip_end_posts, {(1, "s"), (1, "e")})

    def test_tube_spans_stay_within_the_law(self):
        (ep,) = self.hug.plan.edges
        self.assertTrue(all(300 <= s <= 1800 for s in ep.spans), ep.spans)       # 安衛則571条一号 1.85m 以下
        self.assertAlmostEqual(sum(ep.spans), ep.scaffold_length, delta=1.0)

    def test_hug_decks_match_the_main_scaffold(self):
        main = next(m for m in self.rigid if m.config.scaffold_form == "本足場")
        lv = self.hug.elevation_of(1).level_heights
        self.assertTrue(set(lv) <= set(main.elevation.level_heights), (lv, main.elevation.level_heights))

    def test_lean_to_hug_stops_under_the_eaves_with_eave_rails(self):
        # 下屋 3.0m の面: 最上段の床は軒の下、軒先から 450・900 に手すり、建地はその上まで（床が 4.63m に出ていた）
        e = self.hug.elevation_of(1)
        self.assertLessEqual(max(e.level_heights), 3000 + 300)
        self.assertEqual(e.eave_rails_mm, [3450, 3900])
        self.assertGreaterEqual(e.total_height, 3900 + 100)
        self.assertLess(e.total_height, 5000)                       # 建物全体の高さ（11m）で拾わない


class TestConvergedStandoffs(unittest.TestCase):
    def test_groups_agree_on_every_corner(self):
        g = solve_groups(USER)
        own = {e.edge_index: e.standoff for _l, r in g if "上段" not in _l for e in r.model.plan.edges}
        for lb, r in g:
            if "上段" in lb:
                continue
            for e in r.model.plan.edges:
                for adj in ((e.edge_index - 1) % 4, (e.edge_index + 1) % 4):
                    self.assertAlmostEqual(r.model.plan.standoffs[adj], own[adj], delta=0.5, msg=(lb, adj))


class TestRoofBridgeFromScaffoldMembers(unittest.TestCase):
    """屋上への渡りは足場の部材で組む（利用者の指定 2026-10-26: 布材かブラケット出して支柱で足元つくかブラケットで
    浮かせる、アンチ引いて手すりも布材、枠の場合は単管と足場板、パラペットは避ける）."""

    B = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]

    def _bridge(self, **kw):
        r = solve_all({"outline_mm": self.B, "eaves_height_mm": 9000, "module": "inch", **kw})
        (b,) = r.model.roof_bridges
        return r, b

    def _delta(self, r, **kw):
        r0 = solve_all({"outline_mm": self.B, "eaves_height_mm": 9000, "module": "inch", "roof_bridge": False, **kw})
        q0 = {ln.part.model_no: ln.qty for ln in r0.quantity.lines}
        return {ln.part.model_no: ln.qty - q0.get(ln.part.model_no, 0) for ln in r.quantity.lines
                if ln.qty != q0.get(ln.part.model_no, 0)}

    def test_flush_with_the_roof_closes_the_gap_with_brackets(self):
        r, b = self._bridge()
        self.assertEqual(b.kind, "ブラケット")
        self.assertEqual(b.z_deck_mm, b.z_from_mm)                          # 足場の床のまま
        self.assertLessEqual(b.length_mm, b.standoff_mm + 10)                # 躯体の外面まで（屋上スラブに食い込まない）
        self.assertEqual(b.width_mm, 1829)                                   # 掛けるスパンの幅
        d = self._delta(r)
        self.assertEqual(d.get("NDBK03H"), 2)                               # 拡幅ブラケット 305 を両脇に
        self.assertEqual(d.get("NDN624"), 1)                                 # アンチ 240×1829

    def test_deck_above_the_roof_stands_posts_on_the_roof(self):
        r, b = self._bridge(eaves_height_mm=8700)
        self.assertEqual(b.kind, "支柱")
        self.assertGreater(b.z_deck_mm, b.z_to_mm)
        self.assertGreaterEqual(b.length_mm, b.standoff_mm + 150)           # 屋上の支柱は躯体の外面から内側
        koma = r.model.master.koma_pitch
        # 床・中桟・手すりが屋上の支柱のコマに来る（支柱の天端 − 上端の下がり − 2コマ ＝ 床）
        top = b.z_to_mm + b.jack_mm + b.post_mm - r.model.master.koma_top_gap
        self.assertEqual((top - b.z_deck_mm) % koma, 0)
        d = self._delta(r, eaves_height_mm=8700)
        self.assertEqual(d.get(r.model.master.find("支柱", int(b.post_mm)).model_no), 2)
        self.assertGreaterEqual(d.get("NDT06", 0), 6)                         # 布材の腕木・中桟・手すり
        self.assertEqual(b.steps(b.drop_mm), 2)                               # 屋上へ踏段

    def test_parapet_is_cleared(self):
        _r, b = self._bridge(roof_parapet_mm=300)
        self.assertEqual(b.kind, "支柱")
        self.assertGreaterEqual(b.z_deck_mm, b.z_to_mm + 300 + 50)           # パラペットの天端の 50 上より上
        self.assertGreaterEqual(b.length_mm, b.standoff_mm + b.parapet_t_mm + 150)

    def test_frame_scaffold_uses_tubes_and_planks(self):
        r, b = self._bridge(series_id="waku")
        self.assertTrue(b.tube)
        self.assertIn(b.kind, ("単管支柱", "単管跳ね出し"))
        d = self._delta(r, series_id="waku")
        self.assertTrue(any(k.startswith("足場板") for k in d), d)
        self.assertGreater(d.get("ARC1", 0), 0)
        self.assertTrue(any(k.startswith("単管") for k in d), d)

    def test_inner_posts_are_extended_for_the_rails(self):
        # 渡りの手すりが足場の内側の支柱の天端より上になるとき、掛けるスパンの内側の支柱2本を継ぎ足す（案内だけだった）
        r, b = self._bridge(roof_parapet_mm=300)
        koma = r.model.master.koma_pitch
        self.assertGreater(b.ext_mm, 0)
        self.assertEqual(b.ext_mm % koma, 0)                                # コマの並びを崩さない
        self.assertGreaterEqual(b.post_top_mm + b.ext_mm, b.z_deck_mm + 900)
        d = self._delta(r, roof_parapet_mm=300)
        ext = r.model.master.find("支柱", int(b.ext_mm)).model_no
        self.assertGreaterEqual(d.get(ext, 0), 2)

    def test_anti_fill_the_depth(self):
        # 横引きのアンチが奥行きにすき間なく並ぶ長さを選ぶ（914 に 500＋240 だと 134 残った）
        from ashiba.roof_bridges import deck_gap_mm

        _r, b = self._bridge(roof_parapet_mm=300)
        self.assertLessEqual(deck_gap_mm(b.length_mm, b.deck), 90)

    def test_part_gets_the_members(self):
        from ashiba.attachments import bridge_placements

        r, b = self._bridge(eaves_height_mm=8700)
        (p,) = bridge_placements(r.model)
        self.assertEqual(p.params["brKind"], 0)
        self.assertEqual(p.params["deckList"], ",".join(str(w) for w in b.deck))
        self.assertAlmostEqual(p.params["postL"] * 1000, b.post_mm)


class TestAttachmentsGoToTheirGroup(unittest.TestCase):
    def test_hoist_only_in_the_group_with_its_face(self):
        # 昇降機（辺0＝南面）は南面を建てる組にだけ渡す（ほかの組で「辺0は存在しません」と止まった。2026-10-26 実機）
        g = solve_groups({"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
                          "module": "inch", "face_forms": "東面=単管抱き足場;北面=一側足場;西面=一側足場",
                          "hoists": [{"edge_index": 0, "position_mm": 6000}]})
        with_hoist = [lb for lb, r in g if r.platforms.hoists]
        self.assertEqual(with_hoist, [""])


if __name__ == "__main__":
    unittest.main()
