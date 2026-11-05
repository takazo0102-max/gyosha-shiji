"""Tapir アダプタの補助（実機不要で確認できるもの）."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.tapir_adapter import ArchicadClient, TapirError, is_ashiba_part


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
        if command == "GetGDLParametersOfElements":
            return {"gdlParametersOfElements": [
                {"gdlParameters": [{"name": "parentId", "value": self.parents.get(e["elementId"]["guid"], "")}]}
                for e in params["elements"]]}
        return {}

    parents: dict = {}


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
            "old_ver": ("ashiba_line_a146589c", 330.3, 299.65, 1.571),  # 版名付きの配布部品も同じ部品
            "old_det": ("ashiba_detail_3f344e7b", 306.0, 280.0, 0.0),
        }
        c = _DupStub(objs)
        got = sorted(e["elementId"]["guid"] for e in c.objects_for_slab(
            [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]))
        self.assertEqual(got, ["det", "elev", "line", "old_det", "old_ver"])

    def test_exploded_members_of_its_lines_far_out(self):
        """分解した部材は外形の外（外側の支柱）にあっても、親の足場ラインごと拾う."""
        objs = {
            "line": ("ashiba_line", 299.7, 299.65, 0.0),
            "m_out": ("ashiba_member_d9eb777d", 298.5, 310.0, 0.0),   # 外形の1.5m外の外側支柱
            "m_in": ("ashiba_member_d9eb777d", 300.5, 310.0, 0.0),    # 範囲内
            "m_other": ("ashiba_member_d9eb777d", 298.5, 312.0, 0.0),  # 別の足場ラインの部材
        }
        c = _DupStub(objs)
        c.parents = {"m_out": "line", "m_in": "line", "m_other": "elsewhere"}
        got = sorted(e["elementId"]["guid"] for e in c.objects_for_slab(
            [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)],
            ("ashiba_line", "ashiba_member")))
        self.assertEqual(got, ["line", "m_in", "m_out"])


class TestPartNameVersions(unittest.TestCase):
    """埋め込み部品は上書きできないので、配布GSMは「基本名_ハッシュ8桁」で埋め込む."""

    def test_base_and_versioned_names_are_ours(self):
        for n in ("ashiba_line", "ashiba_line_a146589c", "ashiba_detail_3f344e7b"):
            self.assertTrue(is_ashiba_part(n), n)
        for n in ("", "FR_Column", "ashiba_line_v2", "ashiba_liner", "ashiba_line_a146589c_x", "ashiba_line_a146-89c"):
            self.assertFalse(is_ashiba_part(n), n)

    def test_ensure_embedded_parts_takes_an_embedded_name(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "ashiba_line.gsm"; a.write_bytes(b"x")
            c = _Stub()
            added = c.ensure_embedded_parts([(a, "ashiba_line_a146589c")])
        self.assertEqual(added, ["ashiba_line_a146589c.gsm"])
        adds = [p for cmd, p in c.calls if cmd == "AddFilesToEmbeddedLibrary"]
        self.assertEqual(adds[0]["files"][0]["outputPath"], "ashiba/ashiba_line_a146589c.gsm")


class _SelStub(ArchicadClient):
    def __init__(self, polys):
        self.polys = polys

    def get_selected_elements(self):
        return [{"elementId": {"guid": f"g{i}"}} for i in range(len(self.polys))]

    def get_details(self, elements):
        return [{"details": {"polygonCoordinates": [{"x": x, "y": y} for x, y in p]}} if p else {"details": {}}
                for p in self.polys]


class TestSelectedOutline(unittest.TestCase):
    RECT = [(0, 0), (30, 0), (30, 20), (0, 20)]

    def test_single_slab(self):
        from ashiba.tapir_adapter import get_selected_outline_mm

        out = get_selected_outline_mm(_SelStub([self.RECT]))
        self.assertEqual(out[1], (30000.0, 0.0))

    def test_two_slabs_selected_is_an_error(self):
        from ashiba.tapir_adapter import get_selected_outline_mm

        with self.assertRaises(TapirError) as cm:
            get_selected_outline_mm(_SelStub([self.RECT, self.RECT]))
        self.assertIn("2個選択", str(cm.exception))

    def test_non_polygon_selection_is_ignored_but_one_slab_ok(self):
        from ashiba.tapir_adapter import get_selected_outline_mm

        out = get_selected_outline_mm(_SelStub([None, self.RECT]))
        self.assertEqual(len(out), 4)


if __name__ == "__main__":
    unittest.main()



class _MeshStub(ArchicadClient):
    """2枚の敷地メッシュ（建物の近くと、300m離れた別棟のもの）."""

    def __init__(self):
        pass

    def tapir(self, command, params):
        if command == "GetElementsByType":
            return {"elements": [{"elementId": {"guid": "near"}}, {"elementId": {"guid": "far"}}]}
        if command == "GetDetailsOfElements":
            return {"detailsOfElements": [
                {"details": {"level": 0.0, "polygonCoordinates": [
                    {"x": 299, "y": 299, "z": 0}, {"x": 331, "y": 299, "z": -0.4},
                    {"x": 331, "y": 321, "z": -0.4}, {"x": 299, "y": 321, "z": 0}]}},
                {"details": {"level": 0.0, "polygonCoordinates": [
                    {"x": 599, "y": 299, "z": -0.3}, {"x": 621, "y": 299, "z": -0.3},
                    {"x": 621, "y": 316, "z": -0.4}, {"x": 599, "y": 316, "z": -0.4}]}},
            ]}
        return {}


class TestGroundModelUsesOnlyNearbyMeshes(unittest.TestCase):
    def test_far_mesh_is_ignored_for_this_building(self):
        from ashiba.tapir_adapter import read_ground_model

        near_bldg = [(300000, 300000), (330000, 300000), (330000, 320000), (300000, 320000)]
        g = read_ground_model(_MeshStub(), outline_mm=near_bldg)
        self.assertEqual(g.ignored_meshes, 1)
        self.assertTrue(all(p[0] < 400000 for p in g.points))
        far_bldg = [(600000, 300000), (620000, 300000), (620000, 315000), (600000, 315000)]
        g2 = read_ground_model(_MeshStub(), outline_mm=far_bldg)
        self.assertEqual(g2.ignored_meshes, 1)
        self.assertTrue(all(p[0] > 500000 for p in g2.points))
        # 外形を渡さなければ従来どおり全メッシュ
        g3 = read_ground_model(_MeshStub())
        self.assertEqual(g3.ignored_meshes, 0)
        self.assertEqual(len(g3.points), 8)


class TestTimeouts(unittest.TestCase):
    """Archicad が操作中で時間切れ: 読むだけの命令は待って再試行、作る命令は再試行しない（重複を作らない）."""

    def _client(self, fail_times):
        from ashiba.tapir_adapter import TapirTimeout

        class C(ArchicadClient):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def post(self, command, parameters=None):
                self.calls += 1
                if self.calls <= fail_times:
                    raise TapirTimeout("timed out")
                return {"addOnCommandResponse": {"ok": True}}

        return C()

    def test_read_only_is_retried(self):
        c = self._client(2)
        self.assertEqual(c.tapir("GetStories", {}, wait_s=0), {"ok": True})
        self.assertEqual(c.calls, 3)

    def test_busy_create_is_retried(self):
        """入力の途中（4001）は実行されずに断られただけなので、作る命令も送り直す."""
        from ashiba.tapir_adapter import TapirBusy

        class C(ArchicadClient):
            calls = 0

            def post(self, command, parameters=None):
                C.calls += 1
                if C.calls == 1:
                    raise TapirBusy("ongoing user input")
                return {"addOnCommandResponse": {"ok": True}}

        c = C()
        self.assertEqual(c.tapir("CreateDrawings", {}, wait_s=0), {"ok": True})
        self.assertEqual(C.calls, 2)

    def test_4001_becomes_busy(self):
        """Archicad の 4001（ongoing user input）は TapirBusy にして、Esc で抜ける案内を付ける."""
        from unittest import mock

        from ashiba.tapir_adapter import TapirBusy

        c = ArchicadClient()
        resp = mock.MagicMock()
        resp.read.return_value = (
            b'{"succeeded": false, "error": {"code": 4001, "message": "Invalid program status (ongoing user input)"}}')
        resp.__enter__.return_value = resp
        with mock.patch("urllib.request.urlopen", return_value=resp):
            with self.assertRaises(TapirBusy) as cm:
                c.post("API.ExecuteAddOnCommand", {})
        self.assertIn("Esc", str(cm.exception))

    def test_no_open_project_is_not_busy(self):
        """4001 でも「プロジェクトが開いていない」は待っても直らないので TapirBusy にせず、開くよう案内する."""
        from unittest import mock

        from ashiba.tapir_adapter import TapirBusy, TapirError

        c = ArchicadClient()
        resp = mock.MagicMock()
        resp.read.return_value = (
            b'{"succeeded": false, "error": {"code": 4001, "message": "Invalid program status (no open project)"}}')
        resp.__enter__.return_value = resp
        with mock.patch("urllib.request.urlopen", return_value=resp):
            with self.assertRaises(TapirError) as cm:
                c.post("API.ExecuteAddOnCommand", {})
        self.assertNotIsInstance(cm.exception, TapirBusy)
        self.assertIn("プロジェクトが開いていません", str(cm.exception))

    def test_create_is_not_retried(self):
        from ashiba.tapir_adapter import TapirTimeout

        c = self._client(1)
        with self.assertRaises(TapirTimeout):
            c.tapir("CreateSections", {}, wait_s=0)
        self.assertEqual(c.calls, 1)


class TestAluminiumSurface(unittest.TestCase):
    """足場の色はアルミ。表面材の番号はプロジェクトごとに違うので名前で探す."""

    def _client(self, names):
        class C(ArchicadClient):
            def tapir(self, command, parameters=None, retries=2, wait_s=5.0):
                return {"attributes": [{"index": i + 1, "name": n} for i, n in enumerate(names)]}

        return C()

    def test_japanese_name(self):
        c = self._client(["金属 - 鉄", "金属 - アルミニウム", "金属 - 亜鉛"])
        self.assertEqual(c.find_aluminium_surface(), 2)

    def test_english_name(self):
        self.assertEqual(self._client(["Metal - Steel", "Metal - Aluminium"]).find_aluminium_surface(), 2)

    def test_partial_name(self):
        self.assertEqual(self._client(["塗装", "アルミ 押出"]).find_aluminium_surface(), 2)

    def test_missing_is_zero(self):
        """無ければ 0（部品は既定の表面材のまま）."""
        self.assertEqual(self._client(["塗装", "木"]).find_aluminium_surface(), 0)


class TestMemberSurfaces(unittest.TestCase):
    """部材ごとの色: 足場＝アルミ、踏板・幅木＝亜鉛（鉄の色。幅木を黄にしない）。名前が無ければ部分一致、それも無ければ入れない."""

    def test_pick(self):
        from ashiba.tapir_adapter import ArchicadClient, pick_member_surfaces

        attrs = [{"index": 45, "name": "金属 - アルミニウム"}, {"index": 47, "name": "金属 - 亜鉛"},
                 {"index": 70, "name": "塗装 - 黄 マット"}]
        got = pick_member_surfaces(attrs, ArchicadClient.MEMBER_SURFACES)
        self.assertEqual(got, {"matScaf": 45, "matDeck": 47, "matToe": 47})
        body = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
                ).read_text(encoding="utf-8")
        # 幅木は黄にせず、踏板と少し違う鋼板色（利用者の指定 2026-10-24）。前に黄で置いた部品もこの色で描く
        self.assertIn('mToe = IND(MATERIAL, "ashiba_toe_steel")', body)

    def test_missing_member_is_left_out(self):
        from ashiba.tapir_adapter import ArchicadClient, pick_member_surfaces

        got = pick_member_surfaces([{"index": 45, "name": "金属 - アルミニウム"}], ArchicadClient.MEMBER_SURFACES)
        self.assertEqual(got, {"matScaf": 45})
