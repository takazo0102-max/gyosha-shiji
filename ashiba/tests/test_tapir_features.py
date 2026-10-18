"""Tapir・Archicad の版と機能の対応（古い Tapir で断面方式を試して途中で止まらない）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tapir_features import choose_elevation_mode, environment_notes, parse_version


class TestParseVersion(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_version("1.7.0"), (1, 7, 0))
        self.assertEqual(parse_version("1.7"), (1, 7, 0))
        self.assertEqual(parse_version("v1.10.2"), (1, 10, 2))
        self.assertIsNone(parse_version(""))
        self.assertIsNone(parse_version(None))
        self.assertGreater(parse_version("1.10.0"), parse_version("1.7.0"))   # 文字列比較ではない


class TestChooseElevationMode(unittest.TestCase):
    def test_section_needs_tapir_170(self):
        self.assertEqual(choose_elevation_mode("section", "1.7.0"), ("section", []))
        self.assertEqual(choose_elevation_mode("section", "1.8.1")[0], "section")
        mode, notes = choose_elevation_mode("section", "1.5.8")
        self.assertEqual(mode, "object")
        self.assertIn("1.7.0 以上", notes[0])

    def test_unreadable_version_falls_back(self):
        # GetAddOnVersion が無いほど古い Tapir は版を読めない
        self.assertEqual(choose_elevation_mode("section", "")[0], "object")

    def test_object_is_kept_and_unknown_means_section(self):
        self.assertEqual(choose_elevation_mode("object", ""), ("object", []))
        self.assertEqual(choose_elevation_mode("", "1.7.0")[0], "section")


class TestEnvironmentNotes(unittest.TestCase):
    def test_verified_pairs_are_quiet(self):
        self.assertEqual(environment_notes("1.7.0", 30), [])
        self.assertEqual(environment_notes("1.5.8", 28), [])
        self.assertEqual(environment_notes("1.8.0", 30), [])        # 確認済みより新しい Tapir は黙る

    def test_unverified_pairs_say_so(self):
        n = environment_notes("1.7.0", 29)
        self.assertEqual(len(n), 1)
        self.assertIn("未確認", n[0])
        self.assertIn("Archicad 30 ＋ Tapir 1.7.0", n[0])
        self.assertTrue(environment_notes("1.6.0", 30))
        self.assertEqual(environment_notes("", 30), [])              # 版不明は立面の案内に任せる


class TestToolbarUsesTheGate(unittest.TestCase):
    def test_run_from_archicad_chooses_mode_by_version(self):
        src = (Path(__file__).resolve().parents[1] / "scripts" / "run_from_archicad.py").read_text(encoding="utf-8")
        self.assertIn("choose_elevation_mode(", src)
        self.assertIn("client.versions()", src)


if __name__ == "__main__":
    unittest.main()


class TestSlowCommandsWaitLonger(unittest.TestCase):
    def test_create_drawings_gets_a_longer_timeout_once(self):
        from ashiba.tapir_adapter import ArchicadClient

        c = ArchicadClient(timeout=60.0)
        seen = []

        def fake_post(command, parameters=None):
            seen.append(c.timeout)
            return {"addOnCommandResponse": {}}
        c.post = fake_post
        c.tapir("CreateDrawings", {})
        c.tapir("GetStories", {})
        self.assertEqual(seen, [300.0, 60.0])        # 終われば元に戻す
        self.assertEqual(c.timeout, 60.0)
