"""型番仮の部材を含む計画は、手配項目として名指しで出す.

信和の朝顔・踊り場・内ブラケットはカタログに該当が無く仮品番のまま。実品番と同じ顔で
発注書に載ると、そのまま手配されてしまう。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all

ROOT = Path(__file__).resolve().parents[1]


def solve(spec):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return solve_all(load_spec(p))


class TestProvisionalParts(unittest.TestCase):
    def test_shinwa_plan_with_asagao_names_the_provisional_parts(self):
        spec = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        r = solve(spec)                     # 高さ16mなので朝顔1段が自動で付く
        hit = [w for w in r.quantity.warnings if "型番仮の部材" in w]
        self.assertTrue(hit, r.quantity.warnings)
        self.assertIn("A-AS18", hit[0])
        self.assertEqual(r.quantity.warning_kinds.get(hit[0]), "手配")
        # 要確認一覧（数量・手配）に出る
        self.assertTrue([w for w in r.warnings if "型番仮" in w[2] and w[0] == "数量・手配"], r.warnings)

    def test_catalog_series_has_none(self):
        spec = json.loads((ROOT / "examples" / "combo_nd1800.json").read_text(encoding="utf-8"))
        r = solve(spec)
        self.assertFalse([w for w in r.quantity.warnings if "型番仮" in w], r.quantity.warnings)


if __name__ == "__main__":
    unittest.main()
