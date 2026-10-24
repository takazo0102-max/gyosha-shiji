"""条件の窓（配置・条件のボタン。利用者の指定 2026-10-24: 配置の時 足場の種類選べるようにして。条件の部分がどうやるのか
わからない）."""

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from ashiba.cli import solve_all
from ashiba.spec_form import (ASAGAO, KINDS, SERIES_AUTO, WIDTH_DEFAULT, apply_form, current_kind, form_fields,
                              object_params)

BASE = {"project_name": "足場計画", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "module": "inch", "scaffold_width_mm": 900, "stairs": {"layout": "自動"}}


def _vals(spec):
    return {f["key"]: f.get("value") for f in form_fields(spec) if f["key"]}


class TestFormFields(unittest.TestCase):
    def test_current_values_are_shown(self):
        v = _vals(BASE)
        self.assertEqual(v["kind"], "本足場")
        self.assertEqual(v["series"], SERIES_AUTO)
        self.assertEqual(v["width"], "3フィート＝36インチ（914mm）")      # インチ系の 900 → 914
        self.assertEqual(v["stairs"], "自動（幅900以上は足場の中）")
        self.assertEqual(v["asagao"], ASAGAO[0])
        self.assertEqual(v["elev"], "作る")

    def test_kinds_round_trip(self):
        for kind in KINDS:
            new, _n = apply_form(BASE, {**_vals(BASE), "kind": kind})
            self.assertEqual(current_kind(new), kind, kind)


class TestApplyForm(unittest.TestCase):
    def test_choose_bracket_scaffold_and_solve(self):
        new, notes = apply_form(BASE, {**_vals(BASE), "kind": "ブラケット足場（支柱）", "width": WIDTH_DEFAULT})
        self.assertEqual((new["scaffold_form"], new["bracket_post"]), ("ブラケット足場", "支柱"))
        self.assertNotIn("scaffold_width_mm", new)
        self.assertIn("足場の種類 ブラケット足場（支柱）", notes)
        r = solve_all(new)
        self.assertEqual(r.model.config.scaffold_form, "一側足場")

    def test_series_and_width_of_another_module(self):
        # 日建 ND1800（インチ）に 90cm を選んだら、系列にある 914 にする
        lab = "日建 NDシステム1800（くさび）"
        new, notes = apply_form(BASE, {**_vals(BASE), "series": lab, "width": "90cm（900mm）"})
        self.assertEqual(new["series_id"], "nikken_nd1800")
        self.assertEqual(new["scaffold_width_mm"], 914)
        self.assertTrue(any("914" in n for n in notes))

    def test_frame_and_tube_fix_the_series(self):
        new, _n = apply_form(BASE, {**_vals(BASE), "kind": "枠組足場"})
        self.assertEqual(new["series_id"], "waku")
        back, _n = apply_form(new, {**_vals(new), "kind": "本足場"})
        self.assertNotIn("series_id", back)                               # 枠組の系列を引きずらない

    def test_options_reach_the_spec_and_the_object(self):
        new, _n = apply_form(BASE, {**_vals(BASE), "rail": "先行手すり", "stairs": "外付け", "asagao": "2段",
                                    "sheet": "防音シート", "eaves": "12000", "from_slabs": "0",
                                    "elev": "作らない（平面・3Dだけ・速い）"})
        self.assertEqual(new["guard_rail_type"], "先行手すり")
        self.assertEqual(new["stairs"]["layout"], "外付け")
        self.assertEqual(new["asagao"]["stages"], 2)
        self.assertEqual(new["site"]["sheet_type"], "防音シート")
        self.assertEqual(new["eaves_height_mm"], 12000)
        self.assertFalse(new["height_from_slabs"])
        self.assertEqual(new["elevation_mode"], "none")
        p = object_params(new)
        self.assertEqual((p["railType"], p["stairLayout"], p["asagaoStages"], p["elevMode"]),
                         ("先行手すり", "外付け", 2, "none"))
        self.assertAlmostEqual(p["eavesH"], 12.0)


class TestDialogAnswer(unittest.TestCase):
    def test_canned_answer_skips_the_window(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from form_dialog import show_form

        ans = {"button": "place", "values": {"kind": "一側足場"}}
        with mock.patch.dict(os.environ, {"ASHIBA_FORM_ANSWER": json.dumps(ans, ensure_ascii=False)}):
            self.assertEqual(show_form({"title": "x", "fields": [], "buttons": []}), ans)


if __name__ == "__main__":
    unittest.main()
