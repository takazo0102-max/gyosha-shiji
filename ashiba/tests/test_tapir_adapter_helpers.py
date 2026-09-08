"""Tapir アダプタの補助（実機不要で確認できるもの）."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tapir_adapter import ArchicadClient, TapirError


class _Stub(ArchicadClient):
    """tapir() を記録するだけの疑似クライアント."""

    def __init__(self, fail_names=()):
        self.calls = []
        self.fail_names = set(fail_names)

    def tapir(self, command, params):
        self.calls.append((command, params))
        if command == "AddFilesToEmbeddedLibrary":
            out = params["files"][0]["outputPath"]
            ok = not any(n in out for n in self.fail_names)
            return {"executionResults": [{"success": ok, "error": None if ok else {"message": "not a valid relative path"}}]}
        return {}


class TestEnsureEmbeddedParts(unittest.TestCase):
    def test_adds_missing_and_tolerates_existing(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "ashiba_line.gsm"; a.write_bytes(b"x")
            b = Path(d) / "ashiba_detail.gsm"; b.write_bytes(b"x")
            c = _Stub(fail_names=["ashiba_detail"])       # 既にある想定
            added = c.ensure_embedded_parts([a, b, Path(d) / "missing.gsm"])
        self.assertEqual(added, ["ashiba_line.gsm"])
        adds = [p for cmd, p in c.calls if cmd == "AddFilesToEmbeddedLibrary"]
        self.assertEqual(len(adds), 2)                        # 無いファイルは送らない
        self.assertTrue(all(p["files"][0]["outputPath"].startswith("ashiba/") for p in adds))
        self.assertTrue(any(cmd == "ReloadLibraries" for cmd, _ in c.calls))


class _DupStub(ArchicadClient):
    """オブジェクト一覧と詳細を持つ疑似クライアント."""

    def __init__(self, objects):
        self.objects = objects      # guid -> (name, x_m, y_m, angle)
        self.deleted = []

    def tapir(self, command, params):
        if command == "GetElementsByType":
            return {"elements": [{"elementId": {"guid": g}} for g in self.objects]}
        if command == "GetDetailsOfElements":
            out = []
            for e in params["elements"]:
                name, x, y, a = self.objects[e["elementId"]["guid"]]
                out.append({"details": {"libPart": {"name": name}, "origin": {"x": x, "y": y, "z": 0}, "angle": a}})
            return {"detailsOfElements": out}
        if command == "DeleteElements":
            self.deleted += [e["elementId"]["guid"] for e in params["elements"]]
            return {}
        return {}


class TestDeleteStaleDuplicates(unittest.TestCase):
    def test_only_same_part_same_spot_goes(self):
        objs = {
            "new1": ("ashiba_line", 299.7, 299.65, 0.0),
            "old1": ("ashiba_line", 299.7, 299.65, 0.0),        # 同じ位置の前回分 → 消す
            "old_far": ("ashiba_line", 399.7, 299.65, 0.0),     # 別の建物 → 残す
            "old_rot": ("ashiba_line", 299.7, 299.65, 1.5708),  # 向きが違う → 残す
            "other": ("FR_Column", 299.7, 299.65, 0.0),          # 他ツールの部品 → 残す
            "old_close": ("ashiba_line", 299.7004, 299.65, 0.0),  # 0.4mm 違い → 同じ位置とみなす
        }
        c = _DupStub(objs)
        n = c.delete_stale_duplicates([{"elementId": {"guid": "new1"}}])
        self.assertEqual(n, 2)
        self.assertEqual(sorted(c.deleted), ["old1", "old_close"])

    def test_nothing_placed_nothing_deleted(self):
        c = _DupStub({"a": ("ashiba_line", 0, 0, 0)})
        self.assertEqual(c.delete_stale_duplicates([]), 0)
        self.assertEqual(c.deleted, [])


class TestObjectsForSlab(unittest.TestCase):
    def test_picks_lines_elevations_and_details_of_that_slab_only(self):
        objs = {
            "line": ("ashiba_line", 299.7, 299.65, 0.0),        # 外形の範囲
            "elev": ("ashiba_line", 334.6, 255.0, 0.0),         # 立面図の行（y0-45m）
            "det": ("ashiba_detail", 300.0, 280.0, 0.0),        # 詳細図の行（y0-20m）
            "other_bldg": ("ashiba_line", 399.7, 299.65, 0.0),  # 別の建物（x が外）
            "other_row": ("ashiba_line", 300.0, 270.0, 0.0),    # どの行でもない
            "east_bldg_elev": ("ashiba_line", 460.0, 255.0, 0.0),  # 同じ行の東隣の建物の立面図 → 拾わない
            "fr": ("FR_Column", 300.0, 300.0, 0.0),             # 他ツール
        }
        c = _DupStub(objs)
        got = sorted(e["elementId"]["guid"] for e in c.objects_for_slab(
            [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]))
        self.assertEqual(got, ["det", "elev", "line"])


if __name__ == "__main__":
    unittest.main()

