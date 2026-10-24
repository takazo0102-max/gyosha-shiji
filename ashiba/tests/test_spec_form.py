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


class TestInnerRailAndAsagaoFaces(unittest.TestCase):
    """手すりは外と内で選べる・朝顔は付ける面を選べる（利用者の指定 2026-10-24）."""

    def test_inner_rail_choice(self):
        v = _vals(BASE)
        self.assertEqual(v["inner"], "付ける（手すり＋中桟）")
        new, _n = apply_form(BASE, {**v, "inner": "付けない"})
        self.assertFalse(new["inner_guard_rail"])
        self.assertFalse(object_params(new)["innerRail"])
        self.assertFalse(solve_all(new).model.config.inner_guard_rail)

    def test_asagao_on_chosen_faces_only(self):
        from ashiba.gdl_params import line_params

        tall = {**BASE, "eaves_height_mm": 15000, "height_from_slabs": False}
        v = _vals(tall)
        self.assertEqual(v["asagao_faces"], "全部の面")
        new, _n = apply_form(tall, {**v, "asagao_faces": "南面・東面"})
        self.assertEqual(new["asagao"]["faces"], ["南面", "東面"])
        self.assertEqual(object_params(new)["asagaoFaces"], "南面・東面")
        r = solve_all(new)
        m = r.model
        on = {m.face_name(e.edge_index): bool(line_params(m, e, stair_plan=r.stair_plan)["asagaoList"])
              for e in m.plan.edges}
        self.assertEqual(on, {"南面": True, "東面": True, "北面": False, "西面": False})
        self.assertFalse(any(t.kind == "asagao" and m.face_name(t.edge_index) in ("北面", "西面") for t in m.wall_ties))
        full = solve_all(tall)
        self.assertLess(r.quantity.qty_of("朝顔"), full.quantity.qty_of("朝顔"))
        law = next(c for c in r.checks if c.check_id == 10)
        self.assertEqual(law.status, "WARN")
        self.assertIn("北面・西面には付けていません", law.message)

    def test_toggle_faces_later(self):
        from ashiba.spec_form import ASAGAO_MODES, updated_asagao_faces

        every = ["南面", "東面", "北面", "西面"]
        self.assertEqual(updated_asagao_faces("", every, ["北面"], ASAGAO_MODES[1]), "南面・東面・西面")
        self.assertEqual(updated_asagao_faces("南面", every, ["東面"], ASAGAO_MODES[0]), "南面・東面")
        self.assertEqual(updated_asagao_faces("南面・東面", every, ["北面", "西面"], ASAGAO_MODES[0]), "")
        self.assertEqual(updated_asagao_faces("南面", every, ["南面"], ASAGAO_MODES[1]), "なし")
        self.assertEqual(updated_asagao_faces("南面", every, [], ASAGAO_MODES[2]), "")
        r = solve_all({**BASE, "eaves_height_mm": 15000, "height_from_slabs": False, "asagao": {"faces": "なし"}})
        self.assertEqual(r.model.asagao_edges, set())


class TestToeBoardAndNets(unittest.TestCase):
    """幅木のオンオフ・層間ネットとネットブラケットのオンオフ（利用者の指定 2026-10-24）."""

    def test_toe_board_off(self):
        from ashiba.gdl_params import line_params

        new, _n = apply_form(BASE, {**_vals(BASE), "toe": "付けない"})
        self.assertIs(new["toe_board"], False)
        self.assertFalse(object_params(new)["toeBoard"])
        r = solve_all(new)
        self.assertFalse(r.model.config.has_toe_board)
        self.assertEqual(r.quantity.qty_of("幅木"), 0)
        from ashiba.gdl_params import face_drawn_counts

        ep = r.model.plan.edges[0]
        self.assertEqual(line_params(r.model, ep, stair_plan=r.stair_plan)["toeOn"], 0)
        self.assertEqual(face_drawn_counts(r.model, ep, stair_plan=r.stair_plan)["qtyToe"], 0)
        self.assertTrue(any("幅木は付けない" in w for w in r.model.plan.warnings))
        self.assertGreater(solve_all(BASE).quantity.qty_of("幅木"), 0)

    def test_nets_on_all_levels_without_brackets(self):
        from ashiba.attachments import NETBK_OBJECT, NET_OBJECT, net_placements

        v = _vals(BASE)
        self.assertEqual((v["net"], v["net_bk"]), ("張らない", "付ける"))
        new, _n = apply_form(BASE, {**v, "net": "張る", "net_levels": "全部", "net_bk": "付けない"})
        self.assertEqual(new["horizontal_net_levels"], "全部")
        self.assertEqual(object_params(new)["netLevels"], "全部")
        r = solve_all(new)
        self.assertEqual(r.model.config.horizontal_net_levels, list(range(1, r.model.elevation.n_levels + 1)))
        kinds = {p.part for p in net_placements(r.model)}
        self.assertIn(NET_OBJECT, kinds)
        self.assertNotIn(NETBK_OBJECT, kinds)
        self.assertEqual(r.quantity.qty_of("ネットブラケット"), 0)
        with_bk = solve_all({**new, "net_brackets": True})
        self.assertGreater(with_bk.quantity.qty_of("ネットブラケット"), 0)

    def test_net_levels_from_the_object(self):
        from ashiba.spec_object import spec_from_params

        self.assertEqual(spec_from_params({"netLevels": "全部"})["horizontal_net_levels"], "全部")
        self.assertEqual(spec_from_params({"netLevels": "2,5"})["horizontal_net_levels"], [2, 5])


class TestNetRules(unittest.TestCase):
    """層間ネット: 幅木ありは2層毎・幅木なしは全層（＋下さん）。ネットは KSK-HV 0.5×6m（利用者の資料 2026-10-24）."""

    def test_auto_levels_follow_the_toe_board(self):
        r = solve_all({**BASE, "horizontal_net_levels": "自動"})
        n = r.model.elevation.n_levels
        self.assertEqual(r.model.config.horizontal_net_levels, list(range(2, n + 1, 2)))
        off = solve_all({**BASE, "horizontal_net_levels": "自動", "toe_board": False})
        self.assertEqual(off.model.config.horizontal_net_levels, list(range(1, n + 1)))

    def test_net_pieces_are_counted_by_the_sheet(self):
        import math

        from ashiba.attachments import net_heights_mm, net_width_mm

        r = solve_all({**BASE, "horizontal_net_levels": [2]})
        m = r.model
        want = sum(math.ceil(sum(e.spans) / 6000) * max(1, math.ceil(net_width_mm(e.standoff) / 500 - 1e-6))
                   * len(net_heights_mm(m, e.edge_index)) for e in m.plan.edges if net_width_mm(e.standoff) > 0)
        line = next(l for l in r.quantity.lines if l.part.model_no == "KSK-HV")
        self.assertEqual(line.qty, want)

    def test_no_toe_board_needs_shita_san_and_nets_on_every_level(self):
        from ashiba.gdl_params import line_params

        r = solve_all({**BASE, "toe_board": False, "horizontal_net_levels": [2]})
        self.assertTrue(r.model.config.shita_san)
        self.assertEqual(line_params(r.model, r.model.plan.edges[0], stair_plan=r.stair_plan)["shitaSan"], 1)
        self.assertTrue(any("下さん" in n for n in r.quantity.notes))
        self.assertTrue(any("層間ネットは全層に要ります" in w for w in r.quantity.warnings))
        ok = solve_all({**BASE, "horizontal_net_levels": "自動"})
        self.assertFalse(any("層間ネット" in w for w in ok.quantity.warnings))
        sparse = solve_all({**BASE, "horizontal_net_levels": [1]})
        self.assertTrue(any("2層毎に要ります" in w for w in sparse.quantity.warnings))
