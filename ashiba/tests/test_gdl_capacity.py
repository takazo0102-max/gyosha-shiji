"""足場ラインGDLの上限（文字列255文字・配列）に対する分割と検査.

実機で、枠組9層×6列の壁つなぎで tieList が255文字で切れ、上層の壁つなぎが
図から黙って消えていた。長いリストは続きパラメータに分けて渡し、収まらない
ときは止める。
"""

import re
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.gdl_params import (
    GDL_ARRAY_CAP, GDL_STR_MAX, LIST_CHUNKS, GdlCapacityError, fit_gdl_lists,
)

ROOT = Path(__file__).resolve().parents[1]
MASTER_GDL = ROOT / "gdl" / "hsf" / "ashiba_line" / "scripts" / "1d.gdl"
PARAMLIST = ROOT / "gdl" / "hsf" / "ashiba_line" / "paramlist.xml"


class TestChunking(unittest.TestCase):
    def test_long_tie_list_is_split_at_commas(self):
        items = [str(1800 * (i % 30) + 12000) for i in range(100)]   # 5〜6桁×100
        full = ",".join(items)
        self.assertGreater(len(full), GDL_STR_MAX * 2)
        out = fit_gdl_lists({"tieList": full}, 0)
        chunks = [out["tieList"]] + [out[f"tieList{k}"] for k in range(2, 6)]
        for c in chunks:
            self.assertLessEqual(len(c), GDL_STR_MAX)
            self.assertFalse(c.startswith(",") or c.endswith(","))
        self.assertEqual(",".join(c for c in chunks if c), full)
        self.assertEqual(out["tieList5"], "")     # 使わない続きは空で上書き

    def test_short_list_leaves_continuations_empty(self):
        out = fit_gdl_lists({"tieList": "1800,5400", "spanList": "1800"}, 0)
        self.assertEqual(out["tieList"], "1800,5400")
        self.assertEqual([out[f"tieList{k}"] for k in range(2, 6)], [""] * 4)
        self.assertEqual(out["spanList2"], "")

    def test_bracket_records_are_not_split_mid_record(self):
        rec = "10800,14400,600,1,2800,900"      # 6項目=1レコード
        full = ",".join([rec] * 14)             # 約380文字
        out = fit_gdl_lists({"brktList": full}, 1)
        for c in (out["brktList"], out["brktList2"]):
            self.assertLessEqual(len(c), GDL_STR_MAX)
            self.assertEqual(len(c.split(",")) % 6, 0, c)
        self.assertEqual(out["brktList"] + "," + out["brktList2"], full)


class TestCapacityIsNeverSilent(unittest.TestCase):
    def test_too_many_chunks_raises(self):
        full = ",".join(["123456"] * 200)       # 1400文字 > 255×5
        with self.assertRaises(GdlCapacityError) as cm:
            fit_gdl_lists({"tieList": full}, 2)
        self.assertIn("辺2", str(cm.exception))
        self.assertIn("面を分割", str(cm.exception))

    def test_array_cap_raises(self):
        with self.assertRaises(GdlCapacityError) as cm:
            fit_gdl_lists({"spanList": ",".join(["1800"] * (GDL_ARRAY_CAP["spanList"] + 1))}, 0)
        self.assertIn("スパン", str(cm.exception))

    def test_unchunked_long_string_raises(self):
        with self.assertRaises(GdlCapacityError):
            fit_gdl_lists({"levelList": ",".join(["12345"] * 60)}, 0)

    def test_shipped_examples_fit(self):
        import glob

        from ashiba.cli import load_spec, solve_all
        from ashiba.gdl_params import line_params

        for ex in sorted(glob.glob(str(ROOT / "examples" / "*.json"))):
            r = solve_all(load_spec(Path(ex)))
            for ep in r.model.plan.edges:
                params = line_params(
                    r.model, ep, stair_plan=r.stair_plan, openings=r.openings,
                    platforms=r.platforms, bracket_sections=r.brackets)
                for k, v in params.items():
                    if isinstance(v, str):
                        self.assertLessEqual(len(v), GDL_STR_MAX, f"{ex} {k}")


class TestGdlSideMatches(unittest.TestCase):
    """GDL側が続きパラメータを全部読み、配列上限がPython側と一致する."""

    def test_continuation_params_exist_and_are_read(self):
        gdl = MASTER_GDL.read_text(encoding="utf-8")
        xml = PARAMLIST.read_text(encoding="utf-8")
        for key, n in LIST_CHUNKS.items():
            for k in range(2, n + 1):
                self.assertIn(f'<String Name="{key}{k}">', xml)
                self.assertIn(f"rest = {key}{k}", gdl)

    def test_array_dims_match_python_caps(self):
        gdl = MASTER_GDL.read_text(encoding="utf-8")
        dims = {m.group(1): int(m.group(2)) for m in re.finditer(r"dim (\w+)\[(\d+)\]", gdl)}
        self.assertEqual(dims["spans"], GDL_ARRAY_CAP["spanList"])
        self.assertEqual(dims["posts"], GDL_ARRAY_CAP["postList"])
        self.assertEqual(dims["ties"], GDL_ARRAY_CAP["tieList"])
        self.assertEqual(dims["tieH"], GDL_ARRAY_CAP["tieHeightList"])
        self.assertEqual(dims["bkS"] * 6, GDL_ARRAY_CAP["brktList"])
        # while の上限も dim と同じ（dim だけ上げても読む数が増えない）
        self.assertIn(f"nTie < {GDL_ARRAY_CAP['tieList']} do", gdl)
        self.assertIn(f"nSpan < {GDL_ARRAY_CAP['spanList']} do", gdl)


if __name__ == "__main__":
    unittest.main()
