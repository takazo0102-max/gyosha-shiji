"""最小スパン未満の凹み・張り出しは直線で渡す（エラーで止めない）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.geometry import ValidationError, build_outline
from ashiba.master import load_master
from ashiba.plan_solver import solve_plan

MASTER = load_master("shinwa_A")
MIN_SPAN = min(MASTER.span_lengths())      # 600

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def with_notch(depth, width, at=12000, bump=False):
    """南面(y=0)に幅 width・奥行/出 depth の出入りを付けた外形（CCW）."""
    d = -depth if bump else depth
    return [(0, 0), (at, 0), (at, d), (at + width, d), (at + width, 0),
            (30000, 0), (30000, 20000), (0, 20000)]


class TestBridge(unittest.TestCase):
    def test_shallow_recess_is_bridged_with_a_note(self):
        o = build_outline(with_notch(300, 3600), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 4)
        self.assertTrue([n for n in o.notes if "凹み" in n and "直線で渡します" in n
                         and "300mm増えます" in n], o.notes)

    def test_narrow_deep_slot_is_bridged(self):
        o = build_outline(with_notch(3600, 300), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 4)
        self.assertTrue([n for n in o.notes if "3600mm増えます" in n], o.notes)

    def test_deep_wide_recess_is_routed(self):
        o = build_outline(with_notch(900, 1800), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 8)
        self.assertFalse([n for n in o.notes if "渡します" in n])

    def test_shallow_bump_moves_the_neighbours_out(self):
        o = build_outline(with_notch(300, 3600, bump=True), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 4)
        # 南面全体が張り出しの線 y=-300 に移る
        self.assertTrue(all(abs(v[1] + 300) < 1e-6 for v in o.vertices if v[1] < 10000))
        self.assertTrue([n for n in o.notes if "張り出し" in n and "両隣" in n], o.notes)

    def test_tall_narrow_bump_is_still_routed(self):
        o = build_outline(with_notch(3600, 300, bump=True), bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 8)

    def test_off_by_default(self):
        o = build_outline(with_notch(300, 3600))
        self.assertEqual(len(o.vertices), 8)

    def test_solver_no_longer_rejects_shallow_notches(self):
        for shape in (with_notch(300, 3600), with_notch(3600, 300),
                      with_notch(300, 3600, bump=True)):
            with self.subTest(shape):
                plan = solve_plan(shape, MASTER)
                self.assertEqual(len(plan.edges), 4)
                self.assertTrue([w for w in plan.warnings if "渡します" in w], plan.warnings)

    def test_step_is_not_flattened(self):
        """段差（入って戻らない）は出入りではないので対象外."""
        step = [(0, 0), (12000, 0), (12000, 300), (30000, 300), (30000, 20000), (0, 20000)]
        o = build_outline(step, bridge_below_mm=MIN_SPAN)
        self.assertEqual(len(o.vertices), 6)


class TestBridgedZoneReachesQuantityAndReport(unittest.TestCase):
    def test_zone_is_located_on_the_face_with_span_count(self):
        plan = solve_plan(with_notch(300, 3600), MASTER)
        self.assertEqual(len(plan.bridged_zones), 1)
        z = plan.bridged_zones[0]
        self.assertEqual((z.kind, z.edge_index), ("凹み", 0))
        # 始点コーナー支柱から: 離れ + 12000mm
        self.assertGreater(z.start_mm, 12000)
        self.assertAlmostEqual(z.end_mm - z.start_mm, 3600, delta=1e-6)
        self.assertIn(z.span_count, (2, 3))
        self.assertAlmostEqual(z.depth_mm, 300)

    def test_bump_zone_too(self):
        plan = solve_plan(with_notch(300, 3600, bump=True), MASTER)
        self.assertEqual([z.kind for z in plan.bridged_zones], ["張り出し"])
        self.assertAlmostEqual(plan.bridged_zones[0].depth_mm, 300)

    def test_quantity_note_gives_counts(self):
        from ashiba.elevation_solver import solve_elevation
        from ashiba.model import ScaffoldConfig, ScaffoldModel
        from ashiba.quantity import take_off

        plan = solve_plan(with_notch(300, 3600), MASTER)
        m = ScaffoldModel(master=MASTER, plan=plan,
                          elevation=solve_elevation(16300, master=MASTER), config=ScaffoldConfig())
        q = take_off(m)
        note = [n for n in q.warnings + q.notes if "渡した区間" in n]
        self.assertTrue(note, q.warnings)
        z = plan.bridged_zones[0]
        lv = m.elevation.n_levels
        self.assertIn(f"内ブラケット{(z.span_count + 1) * lv}本", note[0])
        self.assertIn(f"布材{z.span_count * lv * 2}本", note[0])

    def test_frame_path_locates_zones_as_well(self):
        waku = load_master("waku")
        plan = solve_plan(with_notch(300, 3658), waku)
        self.assertEqual(len(plan.bridged_zones), 1)
        self.assertGreater(plan.bridged_zones[0].span_count, 0)


class TestBridgedZoneReachesTheDrawing(unittest.TestCase):
    def test_bridge_list_is_sent_for_the_face(self):
        from ashiba.elevation_solver import solve_elevation
        from ashiba.gdl_params import line_params
        from ashiba.model import ScaffoldConfig, ScaffoldModel

        plan = solve_plan(with_notch(300, 3600), MASTER)
        m = ScaffoldModel(master=MASTER, plan=plan,
                          elevation=solve_elevation(16300, master=MASTER), config=ScaffoldConfig())
        z = plan.bridged_zones[0]
        p0 = line_params(m, plan.edges[0])
        self.assertEqual(p0["bridgeList"], f"{z.start_mm:.0f},3600,300,0")
        self.assertEqual(line_params(m, plan.edges[1])["bridgeList"], "")
        bump = solve_plan(with_notch(300, 3600, bump=True), MASTER)
        mb = ScaffoldModel(master=MASTER, plan=bump,
                           elevation=solve_elevation(16300, master=MASTER), config=ScaffoldConfig())
        self.assertTrue(line_params(mb, bump.edges[0])["bridgeList"].endswith(",300,1"))

    def test_gdl_reads_and_draws_it(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        self.assertIn('<String Name="bridgeList">', (root / "paramlist.xml").read_text(encoding="utf-8"))
        self.assertIn("rest = bridgeList", (root / "scripts" / "1d.gdl").read_text(encoding="utf-8"))
        body = (root / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("standoff + brD[ibr]", body)
        self.assertIn("渡し", body)


class TestBridgedZoneInPlanJson(unittest.TestCase):
    def test_plan_json_lists_the_zones(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.elevation_solver import solve_elevation
        from ashiba.model import ScaffoldConfig, ScaffoldModel
        from ashiba.report import write_plan_json

        plan = solve_plan(with_notch(300, 3600), MASTER)
        m = ScaffoldModel(master=MASTER, plan=plan,
                          elevation=solve_elevation(16300, master=MASTER), config=ScaffoldConfig())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"
            write_plan_json(m, path)
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["bridged_zones"]), 1)
        z = data["bridged_zones"][0]
        self.assertEqual((z["kind"], z["edge_index"], z["depth_mm"]), ("凹み", 0, 300.0))
        # 渡していない外形では省略する
        plain = solve_plan(RECT, MASTER)
        mp = ScaffoldModel(master=MASTER, plan=plain,
                           elevation=solve_elevation(16300, master=MASTER), config=ScaffoldConfig())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"
            write_plan_json(mp, path)
            self.assertNotIn("bridged_zones", json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
