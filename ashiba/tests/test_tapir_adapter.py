"""Tapirアダプタの失敗の伝え方（実機で踏んだもの）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tapir_adapter import ANGLE_PARAMS, ArchicadClient, TapirError, angle_values, to_tapir_values


class _Canned(ArchicadClient):
    """tapir() を差し替えて、送った内容と決めた応答を確認する."""

    def __init__(self, response):
        super().__init__()
        self.response = response
        self.calls = []

    def tapir(self, command, parameters=None):
        self.calls.append((command, parameters))
        return self.response


class TestCreateObjectFailure(unittest.TestCase):
    def test_missing_library_part_is_a_clear_error(self):
        """CreateObjects は要素ごとに error を返す。KeyError 'elementId' で落とさない."""
        c = _Canned({"elements": [{"error": {
            "code": -2130313113,
            "message": "Not found library part with name 'ashiba_line_55a0a1fb'"}}]})
        with self.assertRaises(TapirError) as cm:
            c.create_object("ashiba_line_55a0a1fb", 0, 0)
        msg = str(cm.exception)
        self.assertIn("ashiba_line_55a0a1fb", msg)
        self.assertIn("Not found library part", msg)
        self.assertIn("読み込まれていない", msg)


class TestAngleParameters(unittest.TestCase):
    """Tapir は Angle 型をラジアンで受け取り・返す（2026-11-03 実機: 度の 90 を送ると 90 ラジアン≒116.6° になった）."""

    def test_angle_names_match_the_parts(self):
        import re
        names = set()
        for f in (SRC.parent / "gdl" / "hsf").glob("*/paramlist.xml"):
            names |= set(re.findall(r'<Angle Name="([^"]+)"', f.read_text(encoding="utf-8")))
        self.assertEqual(set(ANGLE_PARAMS), names)

    def test_degrees_are_sent_as_radians(self):
        out = to_tapir_values({"faceAng": 90.0, "bmA": -30, "zH": 1.5, "kind": 2, "slew": True})
        self.assertAlmostEqual(out["faceAng"], 1.5707963, places=6)
        self.assertAlmostEqual(out["bmA"], -0.5235988, places=6)
        self.assertEqual((out["zH"], out["kind"], out["slew"]), (1.5, 2, True))      # 長さ・整数・真偽はそのまま
        c = _Canned({"executionResults": [{"success": True}]})
        c.set_gdl_parameters({"elementId": {"guid": "g"}}, {"faceAng": 180.0})
        self.assertAlmostEqual(c.calls[0][1]["elementsWithGDLParameters"][0]["gdlParameters"][0]["value"], 3.1415927, places=6)
        c.set_gdl_parameters_many([({"elementId": {"guid": "g"}}, {"slew": 45.0})])
        self.assertAlmostEqual(c.calls[1][1]["elementsWithGDLParameters"][0]["gdlParameters"][0]["value"], 0.7853982, places=6)

    def test_read_back_in_degrees(self):
        rows = [{"name": "bmA", "type": "Angle", "value": 0.610865238}, {"name": "boomL", "type": "Length", "value": 5.7}]
        self.assertEqual({k: round(v, 3) for k, v in angle_values(rows).items()}, {"bmA": 35.0, "boomL": 5.7})


class TestEmbeddedLibraryPath(unittest.TestCase):
    def test_relative_path_is_sent_absolute(self):
        """Archicad は相対パスを解決できない（Failed to read file になった）."""
        c = _Canned({"executionResults": [{"success": True}]})
        c.add_file_to_embedded_library("out/gsm_dev/x.gsm", "x.gsm")
        sent = c.calls[0][1]["files"][0]["inputPath"]
        self.assertTrue(Path(sent).is_absolute(), sent)
        self.assertTrue(sent.endswith("out/gsm_dev/x.gsm"))


if __name__ == "__main__":
    unittest.main()
