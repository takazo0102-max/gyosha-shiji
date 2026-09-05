"""斜めの辺は外側のコーナーを経由する直交2辺に置き換えて割り付ける（エラーで止めない）."""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all
from ashiba.geometry import build_outline
from ashiba.master import load_master
from ashiba.plan_solver import solve_plan

ROOT = Path(__file__).resolve().parents[1]
PENTA = [(0, 0), (30000, 0), (30000, 12000), (20000, 20000), (0, 20000)]   # 北東を斜めに切った形


class TestOrthogonalize(unittest.TestCase):
    def test_corner_is_inserted_on_the_outer_side(self):
        o = build_outline(PENTA)
        self.assertIn((30000.0, 20000.0), [(float(x), float(y)) for x, y in o.vertices])
        self.assertEqual(len(o.vertices), 4)          # 長方形になる
        for e in o.edges:                             # 全辺が直交
            self.assertTrue(abs(e.direction[0]) < 1e-9 or abs(e.direction[1]) < 1e-9)
        self.assertTrue(any("斜めの辺" in n for n in o.notes), o.notes)

    def test_two_sloped_zones_with_the_deep_end(self):
        o = build_outline(PENTA)
        zones = [z for z in o.bridged if z.kind == "斜辺"]
        self.assertEqual(len(zones), 2)
        z1, z2 = zones
        # p→c（(30000,12000)→(30000,20000)）: c側で |q−c| = 10000 深い
        self.assertEqual((z1.p0, z1.p1), ((30000, 12000), (30000, 20000)))
        self.assertAlmostEqual(z1.depth_mm, 10000)
        self.assertEqual(z1.deep_end, "end")
        # c→q（(30000,20000)→(20000,20000)）: c側で |p−c| = 8000 深い
        self.assertEqual((z2.p0, z2.p1), ((30000, 20000), (20000, 20000)))
        self.assertAlmostEqual(z2.depth_mm, 8000)
        self.assertEqual(z2.deep_end, "start")

    def test_orthogonal_outline_is_untouched(self):
        o = build_outline([(0, 0), (30000, 0), (30000, 20000), (0, 20000)])
        self.assertFalse([z for z in o.bridged if z.kind == "斜辺"])
        self.assertFalse([n for n in o.notes if "斜め" in n])


class TestDiagonalFlowsThroughThePlan(unittest.TestCase):
    def _run(self):
        spec = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        spec["outline_mm"] = [list(p) for p in PENTA]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return solve_all(load_spec(p))

    def test_plan_zones_and_notes(self):
        r = self._run()
        zones = [z for z in r.model.plan.bridged_zones if z.kind == "斜辺"]
        self.assertEqual(len(zones), 2)
        self.assertEqual({z.deep_end for z in zones}, {"start", "end"})
        self.assertTrue(all(z.span_count >= 1 for z in zones))
        hit = [w for w in r.quantity.warnings if "斜辺を渡した区間" in w and "最大" in w]
        self.assertEqual(len(hit), 2, r.quantity.warnings)

    def test_drawing_gets_the_sloped_kind(self):
        from ashiba.gdl_params import line_params

        r = self._run()
        codes = []
        for ep in r.model.plan.edges:
            s = line_params(r.model, ep)["bridgeList"]
            if s:
                codes += [int(v) for v in s.split(",")[3::4]]
        self.assertEqual(sorted(codes), [2, 3])

    def test_solver_accepts_the_shape_directly(self):
        master = load_master("shinwa_A")
        plan = solve_plan(PENTA, master)
        self.assertEqual(len(plan.edges), 4)


class TestShapes(unittest.TestCase):
    def test_tiny_skew_is_rounding_not_a_diagonal(self):
        """5mm の斜めは座標誤差。コーナーを挿入して30mの離れを言わない."""
        o = build_outline([(0, 0), (30000, 0), (30000, 20000), (0, 20005)])
        self.assertEqual([tuple(map(float, v)) for v in o.vertices],
                         [(0.0, 0.0), (30000.0, 0.0), (30000.0, 20000.0), (0.0, 20000.0)])
        self.assertFalse([z for z in o.bridged if z.kind == "斜辺"])
        self.assertTrue(any("座標誤差" in n and "5mm" in n for n in o.notes), o.notes)

    def test_concave_diagonal_bulges_outward(self):
        """入隅を斜めに切った形も外側のコーナーで囲う（内側に食い込まない）."""
        poly = [(0, 0), (30000, 0), (30000, 12000), (18000, 20000), (0, 20000)]
        o = build_outline(poly)
        self.assertEqual(len(o.vertices), 4)
        from ashiba.geometry import _signed_area
        self.assertGreater(_signed_area(o.vertices), _signed_area(poly))   # 置き換えで面積は増える

    def test_two_consecutive_diagonals(self):
        poly = [(0, 0), (26000, 0), (30000, 4000), (30000, 16000), (26000, 20000), (0, 20000)]
        o = build_outline(poly)
        self.assertEqual(len(o.vertices), 4)
        self.assertEqual(len([z for z in o.bridged if z.kind == "斜辺"]), 4)
        plan = solve_plan(poly, load_master("shinwa_A"))
        self.assertEqual(len(plan.bridged_zones), 4)

    def test_v_notch_is_bridged_flat(self):
        """面に食い込むV字の切れ込みは平らに渡し、中央で最大の離れになる2区間になる."""
        poly = [(0, 0), (12000, 0), (15000, 3000), (18000, 0), (30000, 0), (30000, 20000), (0, 20000)]
        plan = solve_plan(poly, load_master("shinwa_A"))
        zones = [z for z in plan.bridged_zones if z.kind == "斜辺"]
        self.assertEqual([(z.edge_index, z.deep_end, round(z.depth_mm)) for z in zones],
                         [(0, "end", 3000), (0, "start", 3000)])


if __name__ == "__main__":
    unittest.main()

