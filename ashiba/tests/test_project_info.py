"""表題欄（プロジェクト情報）の埋め方: 空と前回ツールが書いた値だけ変える（Phase 9-4）."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.project_info import fill_title_block, load_record, plan_updates, wanted_fields


class FakeClient:
    def __init__(self, fields):
        self.fields = dict(fields)
        self.sets = []

    def tapir(self, command, params=None):
        if command == "GetProjectInfoFields":
            return {"fields": [{"projectInfoId": k, "projectInfoValue": v} for k, v in self.fields.items()]}
        if command == "SetProjectInfoField":
            self.sets.append((params["projectInfoId"], params["projectInfoValue"]))
            self.fields[params["projectInfoId"]] = params["projectInfoValue"]
            return {}
        raise AssertionError(command)


class TestWanted(unittest.TestCase):
    def test_site_name_wins_over_project_name(self):
        self.assertEqual(wanted_fields({"project_name": "A棟"}), {"PROJECTNAME": "A棟"})
        w = wanted_fields({"project_name": "A棟", "notification": {"site_name": "○○新築工事", "site_address": "那覇市",
                                                                  "contractor": "△△建設", "planner_name": " "}})
        self.assertEqual(w, {"PROJECTNAME": "○○新築工事", "SITEFULLADDRESS": "那覇市", "CONTACTCOMPANY": "△△建設"})


class TestPlanUpdates(unittest.TestCase):
    def test_only_empty_or_ours(self):
        cur = {"PROJECTNAME": "", "SITEFULLADDRESS": "利用者の住所", "CONTACTCOMPANY": "旧名"}
        want = {"PROJECTNAME": "新", "SITEFULLADDRESS": "那覇市", "CONTACTCOMPANY": "△△建設", "NOPE": "x"}
        up, kept = plan_updates(cur, want, {"CONTACTCOMPANY": "旧名"})
        self.assertEqual(up, {"PROJECTNAME": "新", "CONTACTCOMPANY": "△△建設"})
        self.assertEqual(len(kept), 1)
        self.assertIn("利用者の住所", kept[0])

    def test_same_value_is_quiet(self):
        self.assertEqual(plan_updates({"PROJECTNAME": "A"}, {"PROJECTNAME": "A"}, {}), ({}, []))


class TestFill(unittest.TestCase):
    def test_renaming_the_project_follows_but_user_values_stay(self):
        c = FakeClient({"PROJECTNAME": "", "SITEFULLADDRESS": "手入力"})
        with tempfile.TemporaryDirectory() as d:
            w, notes = fill_title_block(c, {"project_name": "A棟", "notification": {"site_address": "那覇市"}}, d)
            self.assertEqual(w, {"PROJECTNAME": "A棟"})
            self.assertEqual(load_record(d), {"PROJECTNAME": "A棟"})
            self.assertTrue(any("手入力" in n for n in notes))
            # 工事名を変えて再実行 → ツールが書いた値なので追従する
            w2, _ = fill_title_block(c, {"project_name": "B棟"}, d)
            self.assertEqual(w2, {"PROJECTNAME": "B棟"})
            # 利用者が書き換えたら、もう触らない
            c.fields["PROJECTNAME"] = "本当の工事名"
            w3, n3 = fill_title_block(c, {"project_name": "C棟"}, d)
            self.assertEqual(w3, {})
            self.assertIn("本当の工事名", n3[0])

    def test_toolbar_wires_it_and_smoke_does_not_touch_it(self):
        root = Path(__file__).resolve().parents[1]
        tb = (root / "scripts" / "run_from_archicad.py").read_text(encoding="utf-8")
        self.assertIn("fill_title_block(client, spec, OUT_DIR)", tb)
        sm = (root / "scripts" / "smoke_archicad.py").read_text(encoding="utf-8")
        self.assertIn("fill_title=False", sm)


if __name__ == "__main__":
    unittest.main()
