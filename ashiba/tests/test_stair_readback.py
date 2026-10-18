"""階段室の位置を平面のホットスポットで引いて読み戻す（Phase 10-2）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params
from ashiba.span_readback import merge_stairs, stair_positions_from_readback, stairs_from_params

HSF = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
EDGES = [{"edge_index": 0, "face": "南面", "placement": {"x_mm": 0, "y_mm": 0}},
         {"edge_index": 1, "face": "東面", "placement": {"x_mm": 30000, "y_mm": 0}}]
TOWERS = [{"edge_index": 0, "start_mm": 1829.0, "span_count": 2, "length_mm": 3658},
          {"edge_index": 1, "start_mm": 16461.0, "span_count": 2, "length_mm": 3658}]


class TestParse(unittest.TestCase):
    def test_pairs(self):
        self.assertEqual(stairs_from_params({"stairList": "1829,3658,9145,3658"}), [(1829, 3658), (9145, 3658)])
        self.assertEqual(stairs_from_params({"stairList": ""}), [])
        self.assertEqual(stairs_from_params({"stairList": "a,b"}), [])


class TestPositions(unittest.TestCase):
    def test_unchanged_gives_none(self):
        rb = [((0, 0), {"stairList": "1829,3658"}), ((30000, 0), {"stairList": "16461,3658"})]
        pos, notes = stair_positions_from_readback(EDGES, TOWERS, rb)
        self.assertIsNone(pos)
        self.assertEqual(notes, [])

    def test_moved_writes_all_towers(self):
        # 実機: 南面の階段室を 6m 引くと部品が 7316 に吸着した
        rb = [((0, 0), {"stairList": "7316,3658"}), ((30000, 0), {"stairList": "16461,3658"})]
        pos, notes = stair_positions_from_readback(EDGES, TOWERS, rb)
        self.assertEqual([(p["edge_index"], p["start_mm"], p["span_count"]) for p in pos],
                         [(0, 7316, 2), (1, 16461, 2)])
        self.assertIn("南面: 階段室 1829 → 7316mm", notes)

    def test_count_mismatch_keeps_planned(self):
        rb = [((0, 0), {"stairList": "1829,3658,9145,3658"})]
        pos, notes = stair_positions_from_readback(EDGES, TOWERS, rb)
        self.assertIsNone(pos)
        self.assertTrue(any("数が配置時と違う" in n for n in notes))

    def test_merge_and_solve_follows(self):
        spec = {"module": "inch", "stairs": {"count": 2, "tower_spans": 2}}
        out = merge_stairs(spec, [{"edge_index": 0, "start_mm": 7316, "span_count": 2}])
        self.assertEqual(out["stairs"], {"tower_spans": 2, "positions": [{"edge_index": 0, "start_mm": 7316, "span_count": 2}]})
        self.assertEqual(spec["stairs"]["count"], 2)                    # 元は変えない
        r = solve_all(dict(out, outline_mm=[[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                           eaves_height_mm=15400, building_height_mm=16000))
        self.assertEqual([t.start_mm for t in r.stair_plan.towers], [7316])
        self.assertTrue(r.stair_plan.towers[0].manual)


class TestPartSendsAndSnaps(unittest.TestCase):
    def test_stedit_sent_with_stairlist(self):
        r = solve_all({"module": "inch", "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                       "eaves_height_mm": 15400, "building_height_mm": 16000})
        for ep in r.model.plan.edges:
            p = line_params(r.model, ep, stair_plan=r.stair_plan)
            starts = [int(v) for v in p["stairList"].split(",")[0::2]] if p["stairList"] else []
            self.assertEqual([round(v * 1000) for v in p["stEdit"]], starts or [0])

    def test_gdl_snaps_by_mismatch_and_has_hotspots(self):
        vl = (HSF / "scripts" / "vl.gdl").read_text(encoding="utf-8")
        self.assertIn('if stDiff and GLOB_MODPAR_NAME <> "stairList" then', vl)   # API でも手でも同じ
        self.assertIn("parameters stairList = sl", vl)
        d2 = (HSF / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("hotspot2 stEdit[it], -rowW / 2, 701 + 3 * it, stEdit[it], 2", d2)
        rb = (Path(__file__).resolve().parents[1] / "scripts" / "read_back_spans.py").read_text(encoding="utf-8")
        self.assertIn("stair_positions_from_readback(", rb)


if __name__ == "__main__":
    unittest.main()


class TestPlatformReadback(unittest.TestCase):
    PLAT = {"stages": [{"edge_index": 0, "start_mm": 3600.0, "span_count": 2}],
            "hoists": [{"edge_index": 1, "position_mm": 5000.0}]}

    def test_stage_levels_move_together_and_hoist_moves(self):
        from ashiba.span_readback import platform_moves_from_readback

        rb = [((0, 0), {"stageList": "7200,3600,1500,4600,1,7200,3600,1500,6400,1"}),
              ((30000, 0), {"hoistList": "6250,16000,2000,2000,3600"})]
        st, ho, notes = platform_moves_from_readback(EDGES, self.PLAT, rb)
        self.assertEqual(st, [(0, 3600.0, 7200)])
        self.assertEqual(ho, [(1, 5000.0, 6250)])
        self.assertIn("南面: 荷受けステージ 3600 → 7200mm", notes)

    def test_unchanged_and_count_mismatch(self):
        from ashiba.span_readback import platform_moves_from_readback

        rb = [((0, 0), {"stageList": "3600,3600,1500,4600,1"}), ((30000, 0), {"hoistList": ""})]
        st, ho, notes = platform_moves_from_readback(EDGES, self.PLAT, rb)
        self.assertEqual((st, ho), ([], []))
        self.assertTrue(any("昇降機の数が配置時と違う" in n for n in notes))

    def test_merge_by_edge_index_or_face(self):
        from ashiba.span_readback import merge_platform_moves

        spec = {"loading_stages": [{"face": "南面", "start_mm": 3600, "span_count": 2}],
                "hoists": [{"edge_index": 1, "position_mm": 5000}, {"edge_index": 1, "position_mm": 9000}]}
        out, notes = merge_platform_moves(spec, EDGES, [(0, 3600.0, 7200)], [(1, 5000.0, 6250), (1, 1234.0, 1)])
        self.assertEqual(out["loading_stages"][0]["start_mm"], 7200)
        self.assertEqual([h["position_mm"] for h in out["hoists"]], [6250, 9000])
        self.assertEqual(spec["loading_stages"][0]["start_mm"], 3600)          # 元は変えない
        self.assertEqual(len(notes), 1)


class TestPartSendsPlatformEdits(unittest.TestCase):
    def test_sgedit_hoedit_match_lists(self):
        import json

        root = Path(__file__).resolve().parents[1]
        for name in ("small_stage", "small_hoist"):
            spec = json.loads((root / "examples" / "dev" / f"{name}.json").read_text(encoding="utf-8"))
            r = solve_all(spec)
            for ep in r.model.plan.edges:
                p = line_params(r.model, ep, stair_plan=r.stair_plan, platforms=r.platforms)
                for lst, ed in (("stageList", "sgEdit"), ("hoistList", "hoEdit")):
                    vals = [int(v) for v in p[lst].split(",") if v] if p[lst] else []
                    firsts = vals[0::5] if vals else [0]
                    self.assertEqual([round(v * 1000) for v in p[ed]], firsts, (name, ed))

    def test_gdl_has_hotspots_and_moves_landings(self):
        vl = (HSF / "scripts" / "vl.gdl").read_text(encoding="utf-8")
        self.assertIn("parameters stageList = sl", vl)
        self.assertIn("parameters hoistList = sl, landingList = sl2", vl)
        self.assertIn("if abs(sgO[jg] - sgO[ig]) < 0.001 then", vl)          # 同じステージの他の層も
        d2 = (HSF / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("801 + 3 * ig", d2)
        self.assertIn("901 + 3 * ih", d2)
