"""面ごと・面の組（ブロック）ごとの足場の切り替え（利用者の指定 2026-10-22）."""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, run, solve_all, solve_groups
from ashiba.face_forms import (
    FACE_FORMS, RESET, face_groups, faces_of_lines, format_face_forms, parse_face_forms, updated_face_forms,
)

BASE = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 6000,
        "clearance_space_mm": 1500, "ladders": 2}


class TestParse(unittest.TestCase):
    def test_string_and_dict(self):
        self.assertEqual(parse_face_forms("南面=ブラケット足場(単管); 東=単管抱き足場"),
                         {"南面": "ブラケット足場（単管）", "東面": "単管抱き足場"})
        self.assertEqual(parse_face_forms({"北面": "枠組足場"}), {"北面": "枠組足場"})
        self.assertEqual(parse_face_forms(""), {})
        with self.assertRaises(ValueError):
            parse_face_forms("南面=丸太足場")
        with self.assertRaises(ValueError):
            parse_face_forms("南面")
        self.assertEqual(format_face_forms({"南面": "単管本足場", "東面": "一側足場"}), "南面=単管本足場;東面=一側足場")

    def test_update_and_reset(self):
        ff = updated_face_forms("南面=単管抱き足場", ["東面", "西面"], "ブラケット足場（単管）")
        self.assertEqual(ff, {"南面": "単管抱き足場", "東面": "ブラケット足場（単管）", "西面": "ブラケット足場（単管）"})
        self.assertEqual(updated_face_forms(ff, ["南面", "東面"], RESET), {"西面": "ブラケット足場（単管）"})
        with self.assertRaises(ValueError):
            updated_face_forms({}, ["南面"], "なにか")


class TestGroups(unittest.TestCase):
    def test_groups_split_faces(self):
        spec = {**BASE, "module": "metric", "face_forms": "南面=ブラケット足場（単管）;東面=枠組足場;西面=枠組足場"}
        gs = face_groups(spec, ["南面", "東面", "北面", "西面"])
        self.assertEqual([g[0] for g in gs], ["", "ブラケット足場（単管）", "枠組足場"])
        self.assertEqual(gs[0][1]["faces"], ["北面"])
        self.assertEqual(gs[2][1]["faces"], ["東面", "西面"])           # 同じ種類の面は1つの組（ブロック）
        self.assertEqual(gs[2][1]["series_id"], "waku")
        self.assertNotIn("module", gs[2][1])                              # 系列を替える組はモジュールを外す
        self.assertNotIn("face_forms", gs[1][1])
        with self.assertRaises(ValueError):
            face_groups({**BASE, "face_forms": "南西面=本足場"}, ["南面", "東面", "北面", "西面"])

    def test_solve_groups(self):
        groups = solve_groups({**BASE, "face_forms": "南面=ブラケット足場（単管）;東面=単管抱き足場"})
        self.assertEqual([lb for lb, _ in groups], ["", "ブラケット足場（単管）", "単管抱き足場"])
        base, brk, hug = (r.model for _, r in groups)
        self.assertEqual(sorted(base.plan.face_names()), ["北面", "西面"])
        self.assertEqual(brk.plan.face_names(), ["南面"])
        self.assertEqual(brk.config.form_label, "ブラケット足場（単管）")
        self.assertTrue(brk.master.is_tube and hug.config.is_hug)
        self.assertEqual(base.master.series_id, "nikken_nd1800")             # 既定の系列（フィート寸法）
        # 隣の面を建てない端は開放端（妻側の手すり・幅木）
        e = brk.plan.edges[0].edge_index
        self.assertTrue(brk.open_end(e) or brk.open_start(e))
        # 全部の面を切り替えれば、切り替えていない組は無い
        all_sw = solve_groups({**BASE, "face_forms": "南=単管本足場;東=単管本足場;北=単管本足場;西=単管本足場"})
        self.assertEqual([lb for lb, _ in all_sw], ["単管本足場"])
        self.assertEqual(len(all_sw[0][1].model.plan.edges), 4)

    def test_solve_all_refuses_and_run_writes_groups(self):
        with self.assertRaises(InputError):
            solve_all({**BASE, "face_forms": "南面=単管抱き足場"})
        with tempfile.TemporaryDirectory() as d:
            inp = Path(d) / "in.json"
            inp.write_text(json.dumps({**BASE, "project_name": "切替", "face_forms": "南面=単管抱き足場"},
                                      ensure_ascii=False), encoding="utf-8")
            res = run(inp, Path(d) / "out")
            self.assertEqual([g["form"] for g in res["face_groups"]], ["（切り替えなし）", "単管抱き足場"])
            self.assertTrue(list((Path(d) / "out" / "切替_単管抱き足場").glob("*_plan.json")))

    def test_forms_are_all_solvable(self):
        for form in FACE_FORMS:
            with self.subTest(form):
                gs = solve_groups({**BASE, "face_forms": {"南面": form}})
                self.assertEqual(gs[-1][0], form)
                self.assertEqual(gs[-1][1].model.plan.face_names(), ["南面"])


class TestFacesOfLines(unittest.TestCase):
    def test_match_origins(self):
        plan_a = {"outline_mm": [[0, 0], [1, 0]], "edges": [
            {"face": "南面", "placement": {"x_mm": 0.0, "y_mm": -300.0}},
            {"face": "東面", "placement": {"x_mm": 12300.0, "y_mm": 0.0}}]}
        plan_b = {"outline_mm": [[0, 0], [1, 0]], "edges": [
            {"face": "北面", "placement": {"x_mm": 12000.0, "y_mm": 8300.0}}]}
        other = {"outline_mm": [[5, 5]], "edges": [{"face": "西面", "placement": {"x_mm": 0.0, "y_mm": -300.0}}]}
        plan, faces = faces_of_lines([plan_a, plan_b, other], [(0.0, -300.0), (12000.0, 8300.0), (0.0, -300.0)])
        self.assertIs(plan, plan_a)
        self.assertEqual(faces, ["南面", "北面"])                          # 区切った部品（同じ原点）は1つの面
        self.assertEqual(faces_of_lines([plan_a], [(99.0, 99.0)]), (None, []))


class TestSpecObject(unittest.TestCase):
    def test_round_trip(self):
        from ashiba.spec_object import params_from_spec, spec_from_params

        p = params_from_spec({**BASE, "face_forms": "南面=単管抱き足場"})
        self.assertEqual(p["faceForms"], "南面=単管抱き足場")
        self.assertEqual(spec_from_params(p)["face_forms"], "南面=単管抱き足場")

    def test_palette_entry(self):
        from ashiba.palette import ACTIONS

        a = next(a for a in ACTIONS if a.title == "面の切替")
        self.assertEqual(a.script, "switch_face_form.py")
        self.assertIn("line", a.when)
        self.assertTrue((Path(__file__).resolve().parents[1] / "scripts" / a.script).exists())


if __name__ == "__main__":
    unittest.main()
