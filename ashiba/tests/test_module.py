"""スパンのモジュール（メートル／インチ）の指定."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, resolve_series_id, solve_all, validate_spec
from ashiba.master import DEFAULT_SERIES_BY_MODULE, normalize_module, series_ids_for_module, series_module

BASE = {"project_name": "モジュール", "outline_mm": [[0, 0], [10800, 0], [10800, 5400], [0, 5400]],
        "eaves_height_mm": 9000, "building_height_mm": 9000}


class TestModule(unittest.TestCase):
    def test_series_have_a_module(self):
        self.assertEqual(series_module("shinwa_A"), "metric")
        self.assertEqual(series_module("nikken_nd1800"), "inch")
        self.assertEqual(series_module("waku"), "inch")
        self.assertEqual(set(series_ids_for_module("inch")), {"nikken_nd1800", "nikken_nd1900", "waku"})

    def test_aliases(self):
        for v in ("inch", "インチ", "IN", "Inch"):
            self.assertEqual(normalize_module(v), "inch")
        for v in ("metric", "メートル", "mm"):
            self.assertEqual(normalize_module(v), "metric")
        with self.assertRaises(ValueError):
            normalize_module("feet")

    def test_module_alone_picks_the_default_series(self):
        self.assertEqual(resolve_series_id({"module": "インチ"}), DEFAULT_SERIES_BY_MODULE["inch"])
        self.assertEqual(resolve_series_id({"module": "metric"}), "shinwa_A")
        self.assertEqual(resolve_series_id({}), "shinwa_A")
        self.assertEqual(resolve_series_id({"series_id": "nikken_nd1900", "module": "inch"}), "nikken_nd1900")

    def test_mismatch_is_an_input_error(self):
        with self.assertRaises(InputError) as cm:
            resolve_series_id({"series_id": "shinwa_A", "module": "inch"})
        self.assertIn("nikken_nd1800", str(cm.exception))
        with self.assertRaises(InputError):
            resolve_series_id({"series_id": "nikken_nd1800", "module": "メートル"})

    def test_solve_all_in_inch_uses_inch_spans_and_snap_sizes(self):
        from ashiba.gdl_params import line_params

        r = solve_all({**BASE, "module": "inch"})
        m = r.model
        self.assertEqual(m.master.series_id, "nikken_nd1800")
        self.assertTrue(all(s in (1829, 1524, 1219, 914, 610) for e in m.plan.edges for s in e.spans))
        self.assertEqual(line_params(m, m.plan.edges[0])["sizeList"], "1829,1524,1219,914,610")

    def test_bad_module_value_is_caught_by_validation(self):
        with self.assertRaises(InputError) as cm:
            validate_spec({**BASE, "series_id": "shinwa_A", "module": "feet"})
        self.assertIn("module", str(cm.exception))


class TestInchSnap(unittest.TestCase):
    """ホットスポット吸着はインチの規格でも面の長さを保つ."""

    def test_inch_sizes(self):
        from ashiba.span_readback import snap_boundary

        inch = (1829, 1524, 1219, 914, 610)
        self.assertEqual(snap_boundary([1829, 1829, 1829], 2, 1524, inch), [1524, 1524, 610, 1829])
        self.assertEqual(snap_boundary([1829, 914], 2, 1250, inch), [1219, 1524])
        self.assertEqual(snap_boundary([914, 914, 1829], 2, 50, inch), [914, 914, 1829])   # 1828≠1829 なので結合しない
        self.assertEqual(snap_boundary([1219, 610, 1829], 2, 50, inch), [1829, 1829])


if __name__ == "__main__":
    unittest.main()
