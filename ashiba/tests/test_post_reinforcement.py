"""支柱の補強仕様（強力つなぎ材）: 耐力の切替と部材の差し替えが一緒に動く.

日建カタログ p025/p040 は腕木を強力つなぎ材（方杖付き）にすると支柱の許容支持力が
上がる（ND1800 11.0→17.0kN/本）。耐力だけ上げて部材が通常のつなぎ材のままなら
計算書と発注が食い違うので、両方を同じ設定から引く。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, load_spec, solve_all
from ashiba.structural import CapacityError

ROOT = Path(__file__).resolve().parents[1]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


def base(series="nikken_nd1800"):
    name = "nikken_nd1800_rect.json" if series == "nikken_nd1800" else f"{series}_rect.json"
    spec = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
    spec["series_id"] = series
    return spec


def qty_of_model(q, model_no):
    return sum(l.qty for l in q.lines if l.part.model_no == model_no)


class TestPostReinforcement(unittest.TestCase):
    def test_default_is_the_normal_capacity(self):
        r = solve(base())
        self.assertEqual(r.structural.post.allowable_kn, 12.0)     # W610 通常使用
        self.assertGreater(qty_of_model(r.quantity, "NDT06"), 0)
        self.assertEqual(qty_of_model(r.quantity, "NDT06S"), 0)

    def test_strong_ties_raise_the_capacity_and_swap_the_part(self):
        spec = dict(base(), post_reinforcement="強力つなぎ材")
        r = solve(spec)
        post = r.structural.post
        self.assertEqual(post.allowable_kn, 17.0)
        self.assertTrue(post.verified)
        self.assertIn("強力つなぎ材", post.source)
        q = r.quantity
        n_udegi = r.model.plan.total_posts * (r.model.elevation.n_levels + 1)
        self.assertEqual(qty_of_model(q, "NDT06S"), n_udegi)
        # 通常のつなぎ材610は腕木ぶんが消える（手すり・布材としての610は残り得る）
        self.assertLess(qty_of_model(q, "NDT06"), n_udegi)
        self.assertFalse([n for n in q.notes if "強力つなぎ材" in n and "ありません" in n], q.notes)
        # plan.json に往復する
        from ashiba.report import write_plan_json

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"
            write_plan_json(r.model, path)
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["config"]["post_reinforcement"], "強力つなぎ材")

    def test_nd1900_uses_the_single_sided_value(self):
        spec = dict(base("nikken_nd1900"), post_reinforcement="強力つなぎ材")
        r = solve(spec)
        self.assertEqual(r.structural.post.allowable_kn, 14.4)
        self.assertGreater(qty_of_model(r.quantity, "NHT06S"), 0)

    def test_series_without_the_value_refuses_instead_of_using_the_normal_one(self):
        spec = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        spec["post_reinforcement"] = "強力つなぎ材"
        with self.assertRaises(CapacityError) as cm:
            solve(spec)
        self.assertIn("強力つなぎ材", str(cm.exception))

    def test_unknown_value_is_rejected_by_validation(self):
        spec = dict(base(), post_reinforcement="補剛材")
        with self.assertRaises(InputError) as cm:
            solve(spec)
        self.assertIn("post_reinforcement", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
