"""拡幅・縮幅（途中の作業床から足場の幅を 305 変える。利用者の指定 2026-10-25: 両方作って 610→914と914→1219）."""

import json
import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import kbrk_placements, sheet_placements
from ashiba.cli import InputError, solve_all, validate_spec
from ashiba.gdl_params import line_params
from ashiba.spec_form import form_fields
from ashiba.spec_object import params_from_spec
from ashiba.width_change import bracket_specs, labels_for, line_pieces, span_range, start_corner, upper_params

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from width_range_run import merged_faces, updated_width_change  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "nikken_nd1800_rect.json"


def _spec(w1: int, w2: int, level: int = 4, **kw) -> dict:
    s = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    s["scaffold_width_mm"] = w1
    s["width_change"] = {"to_mm": w2, "level": level, **kw}
    s["stairs"] = {**(s.get("stairs") or {}), "layout": "足場の中"}
    return s


def _qty(r, model_no: str) -> int:
    return sum(l.qty for l in r.quantity.lines if l.part.model_no == model_no)


class TestWidthChange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wide = solve_all(_spec(610, 914))
        cls.narrow = solve_all(_spec(1219, 914, 5))
        base = _spec(610, 914)
        base.pop("width_change")
        cls.base = solve_all(base)

    def test_model_holds_the_change(self):
        wc = self.wide.model.width_change
        self.assertEqual((wc.mode, wc.from_mm, wc.to_mm, wc.level), ("拡幅", 610, 914, 4))
        self.assertEqual(wc.to_decks, (500, 240))
        self.assertEqual(self.narrow.model.width_change.mode, "縮幅")

    def test_lower_line_stops_below_the_changed_floor_and_upper_line_is_wider(self):
        m = self.wide.model
        ep = m.plan.edges[0]
        p = line_params(m, ep)
        self.assertEqual((p["segLevA"], p["segLevB"]), (0, 3))
        self.assertAlmostEqual(p["rowW"], 0.61)
        u = upper_params(m, ep)
        self.assertEqual((u["segLevA"], u["segLevB"]), (4, 0))
        self.assertAlmostEqual(u["rowW"], 0.914)
        self.assertAlmostEqual(u["deckW2"], 0.24)
        self.assertAlmostEqual(u["cornerSW"], 0.914)
        self.assertEqual(u["sillList"], "")

    def test_brackets_on_every_outer_post_at_the_changed_floor(self):
        m = self.wide.model
        ks = kbrk_placements(m)
        brk = [k for k in ks if k.params["cnrMode"] == 0]
        n_posts = sum(len(e.spans) + 1 for e in m.plan.edges)
        self.assertEqual(len(brk), n_posts)
        lv4 = m.elevation.level_heights[3] / 1000.0
        self.assertTrue(all(abs(k.params["zArm"] - lv4) < 1e-6 for k in brk))
        self.assertTrue(all(k.params["extUp"] == 0.9 and k.params["tieZ"] > 0 for k in brk))
        # 南面（+X 向き）の拡幅は外（−Y）へ、縮幅は躯体側（+Y）へ
        self.assertAlmostEqual(brk[0].params["faceAng"], -90.0)
        nb = [k for k in kbrk_placements(self.narrow.model) if k.params["cnrMode"] == 0]
        self.assertAlmostEqual(nb[0].params["faceAng"], 90.0)
        # 先端の管の芯は新しい建地列（芯々 305）
        self.assertAlmostEqual(brk[0].params["brW"] - 0.0427 / 2, 0.305)

    def test_corner_posts(self):
        wide = [k for k in kbrk_placements(self.wide.model) if k.params["cnrMode"]]
        self.assertEqual(len(wide), 4)
        self.assertTrue(all(k.params["cnrMode"] == 1 and k.params["tieList"] for k in wide))
        narrow = [k for k in kbrk_placements(self.narrow.model) if k.params["cnrMode"]]
        self.assertEqual(len(narrow), 4)
        self.assertTrue(all(k.params["cnrMode"] == 2 and k.params["cnrAt"] < k.params["cnrL"] for k in narrow))

    def test_quantity_swaps_transoms_and_adds_brackets(self):
        n_posts = sum(len(e.spans) + 1 for e in self.wide.model.plan.edges)
        self.assertEqual(_qty(self.wide, "NDBK03H"), n_posts)
        self.assertEqual(_qty(self.wide, "NDP09N") - _qty(self.base, "NDP09N"), n_posts)
        self.assertEqual(_qty(self.wide, "NDT03") - _qty(self.base, "NDT03"), n_posts)
        self.assertGreater(_qty(self.wide, "NDT09"), _qty(self.base, "NDT09"))
        self.assertLess(_qty(self.wide, "NDT06"), _qty(self.base, "NDT06"))
        self.assertTrue(any("拡幅 610→914" in n for n in self.wide.quantity.notes))

    def test_structural_uses_widened_capacity_and_checks_brackets(self):
        st = self.wide.structural
        self.assertTrue(st.post.widened)
        self.assertTrue(any("拡幅 610→914" in b.name for b in st.brackets))
        self.assertTrue(all(b.ok for b in st.brackets))

    def test_sheets_split_at_the_changed_floor(self):
        m = self.wide.model
        zk = m.elevation.level_heights[3] / 1000.0
        sh = [p.params for p in sheet_placements(m, False, self.wide.stair_plan) if p.params["faceAng"] == 0.0]
        low = [q for q in sh if abs(q["zT"] - zk) < 1e-6]
        up = [q for q in sh if abs(q["zB"] - zk) < 1e-6]
        self.assertTrue(low and up)
        self.assertAlmostEqual(up[0]["offY"] - low[0]["offY"], 0.304)

    def test_bad_pairs_are_refused_with_a_note(self):
        r = solve_all(_spec(610, 1219))
        self.assertIsNone(r.model.width_change)
        self.assertTrue(any("305 の1回分" in w for w in r.model.plan.warnings))
        with self.assertRaises(InputError):
            validate_spec(_spec(610, 914, 1))

    def test_lines_and_window_do_not_offer_whole_building_change(self):
        # 利用者の指摘 2026-10-25: 拡張が全ての足場になってしまう → 条件の窓・足場条件の部品からは外し、パレットの
        # 「幅の変更」で線を引いた範囲だけにする
        keys = {x["key"] for x in form_fields(_spec(610, 914))}
        self.assertNotIn("widen", keys)
        self.assertNotIn("widthChg", params_from_spec(_spec(610, 914)))


class TestWidthChangeRange(unittest.TestCase):
    def test_range_in_the_middle_of_a_face(self):
        r = solve_all(_spec(610, 914, 3, faces=["南面[3658-9145]"]))
        m = r.model
        ep = m.plan.edges[0]
        self.assertEqual(span_range(m, ep), (3, 5))
        pcs = line_pieces(m, ep)
        self.assertEqual([(p["segSpanA"], p["segSpanB"], p["segLevA"], p["segLevB"]) for p in pcs],
                         [(0, 2, 0, 0), (3, 5, 0, 2), (3, 5, 3, 0), (6, 0, 0, 0)])
        self.assertAlmostEqual(pcs[2]["rowW"], 0.914)
        self.assertNotIn("rowW", pcs[1])
        # 範囲の外の面は変えない
        self.assertEqual(line_pieces(m, m.plan.edges[1]), [])
        br = bracket_specs(m, ep)
        self.assertEqual(len(br), 4)
        s_end = next(b for b in br if b["end"] == "s")
        e_end = next(b for b in br if b["end"] == "e")
        # 始まりの端は元の支柱を天端まで、終わりの端は先端の支柱を天端まで。どちらも各層の手すり・中桟で塞ぐ
        self.assertGreater(s_end["ext"], 5000)
        self.assertGreater(e_end["tip"], 5000)
        self.assertEqual(len(s_end["ties"]), len(e_end["ties"]))
        self.assertGreater(len(s_end["ties"]), 4)
        self.assertTrue(e_end["ud"])
        self.assertEqual(len([k for k in kbrk_placements(m)]), 4)
        self.assertEqual(_qty(r, "NDBK03H"), 4)
        # 範囲の端の妻側のシート
        ends = [p for p in sheet_placements(m, False, r.stair_plan) if p.params.get("panelList", "").endswith(",1")
                and abs(p.params["x1"] - p.params["x0"] - 0.304) < 1e-6]
        self.assertEqual(len(ends), 2)

    def test_corner_where_only_one_face_changes(self):
        m = solve_all(_spec(610, 914, 3, faces=["南面[25000-40000]"])).model
        south, east = m.plan.edges[0], m.plan.edges[1]
        self.assertIsNone(start_corner(m, south))
        self.assertEqual(start_corner(m, east), "prev")
        pcs = line_pieces(m, east)
        self.assertEqual(len(pcs), 2)
        self.assertAlmostEqual(pcs[1]["cornerSW"], 0.914)
        self.assertNotIn("rowW", pcs[1])
        b = bracket_specs(m, east)
        self.assertEqual([(x["x"], x["y"], x["dir"]) for x in b], [(-610.0, -610.0, "prev")])
        m2 = solve_all(_spec(914, 610, 3, faces=["東面[0-3658]"])).model
        self.assertEqual(start_corner(m2, m2.plan.edges[1]), "self")

    def test_palette_range_merge(self):
        self.assertEqual(merged_faces(["南面[0-3658]"], ["東面"], True), ["南面[0-3658]", "東面"])
        self.assertEqual(merged_faces(["南面[0-3658]", "東面"], ["南面[1829-5487]"], False), ["東面"])
        wc = updated_width_change(None, "拡幅 610→914", 3, ["南面[0-3658]"], "add")
        self.assertEqual(wc, {"label": "拡幅 610→914", "from_mm": 610, "to_mm": 914, "level": 3, "faces": ["南面[0-3658]"]})
        self.assertIsNone(updated_width_change(wc, "拡幅 610→914", 3, ["南面[0-3658]"], "remove"))
        self.assertIsNone(updated_width_change(wc, "拡幅 610→914", 3, [], "clear"))
        self.assertEqual(labels_for(914), ["拡幅 914→1219", "縮幅 914→610"])


if __name__ == "__main__":
    unittest.main()
