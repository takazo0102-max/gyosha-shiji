"""ツールバー割当スクリプトの条件上書きファイルの扱い（実機不要）."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("run_from_archicad", ROOT / "scripts" / "run_from_archicad.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSpecOverride(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ashiba_spec.json"
        self.mod.SPEC_OVERRIDE = self.path

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_means_no_override(self):
        self.assertEqual(self.mod.load_spec_override(), {})

    def test_bom_file_is_read_and_outline_is_ignored(self):
        self.path.write_bytes("﻿".encode("utf-8") + b'{"series_id": "waku", "outline_mm": [[0,0]]}')
        self.assertEqual(self.mod.load_spec_override(), {"series_id": "waku"})

    def test_broken_file_stops_instead_of_falling_back(self):
        """読めない上書きファイルで既定条件の足場を黙って置かない（waku のつもりが信和Aになった）."""
        from ashiba.cli import InputError

        self.path.write_text('{"series_id": "waku",}', encoding="utf-8")
        with self.assertRaises(InputError) as cm:
            self.mod.load_spec_override()
        self.assertIn("読めません", str(cm.exception))

    def test_macos_refusal_is_not_called_a_json_mistake(self):
        """macOS がデスクトップを読ませないときは JSON の綴りでなく許可を案内する（2026-11-06 パレットで Errno 1）."""
        from unittest import mock

        from ashiba.cli import InputError

        self.path.write_text("{}", encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError(1, "Operation not permitted")):
            with self.assertRaises(InputError) as cm:
                self.mod.load_spec_override()
        self.assertIn("macOS", str(cm.exception))
        self.assertIn("ファイルとフォルダ", str(cm.exception))
        self.assertNotIn("綴り", str(cm.exception))

    def test_non_object_file_stops(self):
        from ashiba.cli import InputError

        self.path.write_text('["waku"]', encoding="utf-8")
        with self.assertRaises(InputError):
            self.mod.load_spec_override()


class TestVersionedPartName(unittest.TestCase):
    """配布GSMの版（.gsm.hash）を部品名に付ける。GSM更新で古い埋め込み部品が居座り
    「railAdv is not a GDL parameter」で止まった対策."""

    def test_uses_hash_stamp_and_falls_back_to_base(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as d:
            g = Path(d)
            (g / "ashiba_line.gsm.hash").write_text("a146589c\n", encoding="utf-8")
            (g / "ashiba_detail.gsm.hash").write_text("not a hash", encoding="utf-8")
            self.assertEqual(mod.versioned_part_name("ashiba_line", g), "ashiba_line_a146589c")
            self.assertEqual(mod.versioned_part_name("ashiba_detail", g), "ashiba_detail")
            self.assertEqual(mod.versioned_part_name("ashiba_other", g), "ashiba_other")

    def test_shipped_stamps_give_recognised_names(self):
        from ashiba.tapir_adapter import is_ashiba_part
        mod = _load_module()
        for base in ("ashiba_line", "ashiba_detail"):
            n = mod.versioned_part_name(base)
            self.assertNotEqual(n, base, "配布GSMの .gsm.hash が無い")
            self.assertTrue(is_ashiba_part(n), n)


class TestSampleSpec(unittest.TestCase):
    """出力先に書く雛形は、そのまま（外形を足せば）入力として通る."""

    def test_sample_is_valid_input(self):
        from ashiba.cli import validate_spec

        mod = _load_module()
        with tempfile.TemporaryDirectory() as d:
            p = mod.write_sample_spec(Path(d))
            import json
            data = json.loads(p.read_text(encoding="utf-8"))
        self.assertTrue(any(k.startswith("_") for k in data))       # コメント入り
        data["outline_mm"] = [[0, 0], [30000, 0], [30000, 20000], [0, 20000]]
        validate_spec(data)                                          # コメントは無視される
        self.assertIn("_scaffold_height_mm", data)
        self.assertIn("_span_overrides_example", data)

    def test_missing_override_prints_where_to_put_it(self):
        import io
        from contextlib import redirect_stdout

        mod = _load_module()
        with tempfile.TemporaryDirectory() as d:
            mod.SPEC_OVERRIDE = Path(d) / "ashiba_spec.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(mod.load_spec_override(), {})
        self.assertIn("雛形", buf.getvalue())
        self.assertIn(mod.SAMPLE_NAME, buf.getvalue())


class TestElevationTitles(unittest.TestCase):
    def test_project_name_is_appended(self):
        mod = _load_module()
        self.assertEqual(mod.elevation_face_titles(["南面", "東面(辺1)"], "A棟"), ["南面　A棟", "東面(辺1)　A棟"])
        self.assertEqual(mod.elevation_face_titles(["南面"], ""), ["南面"])
        self.assertEqual(mod.elevation_face_titles(["南面"], None), ["南面"])


class TestStaleBeforeDrawings(unittest.TestCase):
    def test_previous_parts_go_before_the_drawings_and_pdf(self):
        """前回の部品は図面・PDF より先に消す（後で消していたので古い版のラベルが PDF に重なった）."""
        src = (ROOT / "scripts" / "run_from_archicad.py").read_text(encoding="utf-8")
        gone = src.index("client.delete_elements(stale)")
        self.assertLess(gone, src.rindex("place_plan_annotations(client"))
        # 図面・PDF は make_drawings（配置の最後、またはパレットの「図面を作る」。利用者の指定 2026-10-24）
        self.assertLess(gone, src.index("    dw = make_drawings("))
        body = src[src.index("def make_drawings("):src.index("def main(")]
        for later in ("place_section_elevations(", "place_plan_sheet(", "place_details(", "publish_scaffold_pdf("):
            self.assertIn(later, body)


if __name__ == "__main__":
    unittest.main()
