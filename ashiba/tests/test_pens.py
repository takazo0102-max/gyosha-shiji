"""図面のペン（利用者の指定 2026-10-24: 壁繋ぎの逆三角を塗りつぶして／ペンカラーを選べるコマンド作って）."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.attachments import net_placements, sheet_placements, tie_placements
from ashiba.cli import solve_all
from ashiba.gdl_params import line_params
from ashiba.pens import PART_PENS, PEN_KEYS, format_pens, gdl_pens, parse_pens, part_base

ROOT = Path(__file__).resolve().parents[1]
GDL = ROOT / "gdl" / "hsf"
RECT = [[0, 0], [24000, 0], [24000, 12000], [0, 12000]]


class TestPenValues(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(parse_pens("post=3, tie=20、dim=5"), {"post": 3, "tie": 20, "dim": 5})
        self.assertEqual(parse_pens({"post": "3", "nope": 2, "deck": 0, "net": 300}), {"post": 3})
        self.assertEqual(parse_pens(""), {})
        self.assertEqual(format_pens({"dim": 5, "post": 3, "line": 1}), "post=3,dim=5")   # 区分の順、1 は書かない

    def test_part_names(self):
        self.assertEqual(part_base("ashiba_netbk_558a68ff"), "ashiba_netbk")
        self.assertEqual(part_base("ashiba_net_b029e3ba"), "ashiba_net")
        self.assertEqual(part_base("ashiba_line"), "ashiba_line")
        self.assertEqual(part_base("ashiba_spec_1"), "")
        self.assertEqual(gdl_pens({"tie": 20}, "ashiba_tie"), {"penTie": 20})
        self.assertEqual(gdl_pens(None, "ashiba_sheet"), {"penSheet": 1})

    def test_every_pen_param_is_in_the_parts(self):
        for part, keys in PART_PENS.items():
            xml = (GDL / part / "paramlist.xml").read_text(encoding="utf-8")
            for k in keys:
                param = next(p for kk, p, _l, _d in PEN_KEYS if kk == k)
                self.assertIn(f'<PenColor Name="{param}">', xml, (part, param))


class TestPensReachThePlacements(unittest.TestCase):
    def test_spec_pens_go_to_every_part(self):
        r = solve_all({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                       "horizontal_net_levels": [2], "pens": "post=3,tie=20,net=4,sheet=6,dim=5"})
        m = r.model
        p = line_params(m, m.plan.edges[0], stair_plan=r.stair_plan)
        self.assertEqual((p["penPost"], p["penTie"], p["penDim"], p["penLine"]), (3, 20, 5, 1))
        self.assertTrue(all(pl.params["penTie"] == 20 for pl in tie_placements(m)))
        self.assertTrue(all(pl.params["penNet"] == 4 for pl in net_placements(m)))
        self.assertTrue(all(pl.params["penSheet"] == 6 for pl in sheet_placements(m, stair_plan=r.stair_plan)))

    def test_spec_object_keeps_the_pens(self):
        from ashiba.spec_object import params_from_spec, spec_from_params

        self.assertEqual(params_from_spec({"pens": "post=3"})["penList"], "post=3")
        self.assertEqual(spec_from_params({"penList": "tie=20"})["pens"], "tie=20")
        self.assertIn('<String Name="penList">', (GDL / "ashiba_spec" / "paramlist.xml").read_text(encoding="utf-8"))


class TestTieSymbolIsFilled(unittest.TestCase):
    def test_tie_triangle_is_a_filled_polygon(self):
        for p in (GDL / "ashiba_tie" / "scripts" / "2d.gdl", GDL / "ashiba_line" / "scripts" / "2d.gdl"):
            src = p.read_text(encoding="utf-8")
            self.assertIn('fiTie = IND(FILL, "100 %")', src, p)
            self.assertIn("poly2_b 4, 7,", src, p)


class TestDraftPens(unittest.TestCase):
    """CAD の平面図の描き方（scripts/gdl_draft.py）の太線・細線・範囲の線・隠す塗り（利用者の指定 2026-11-04）."""

    ROWS = [(1, "#000000", 0.05), (4, "#029E21", 0.05), (19, "#FFFFFF", 0.05), (20, "#FF0000", 0.05),
            (21, "#000000", 0.15), (24, "#029E21", 0.15), (41, "#000000", 0.1), (60, "#FF0080", 0.05)]

    def test_same_colour_thick_and_thin(self):
        from ashiba.pens import draft_pens

        self.assertEqual(draft_pens(self.ROWS, 1), {"penBold": 21, "penThin": 1, "penZone": 20, "penMask": 19})
        self.assertEqual(draft_pens(self.ROWS, 24)["penBold"], 24)
        self.assertEqual(draft_pens(self.ROWS, 24)["penThin"], 4)
        self.assertEqual(draft_pens([], 7), {"penBold": 7, "penThin": 7, "penZone": 7})
        self.assertEqual(draft_pens([(1, "#000000", 0.1), (2, "#FF0000", 0.1)], 1)["penMask"], 0)

    def test_draft_params_in_the_parts(self):
        """描き方のパラメータは部品の paramlist にあり、2D は縮尺の段・線種・隠す塗りを使う."""
        from pathlib import Path

        from ashiba.pens import DRAFT_PARTS

        hsf = Path(__file__).resolve().parents[1] / "gdl" / "hsf"
        for part in sorted(DRAFT_PARTS):
            pl = (hsf / part / "paramlist.xml").read_text(encoding="utf-8")
            for name in ("penBold", "penThin", "penZone", "penMask", "drMode"):
                self.assertIn(f'Name="{name}"', pl, (part, name))
            sc = (hsf / part / "scripts" / "2d.gdl").read_text(encoding="utf-8")
            for word in ("drLv", "ltZ", "ltC", "poly2_b", "drawindex"):
                self.assertIn(word, sc, (part, word))


class TestPenCommand(unittest.TestCase):
    def test_palette_has_the_button(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("ペン", [a.title for a in ACTIONS])
        self.assertIn("ペン", dict(PANEL_GROUPS)["足場を見る・出す"])
        self.assertTrue((ROOT / "scripts" / "pen_colors.py").exists())

    def test_form_window_draws_pen_swatches(self):
        src = (ROOT / "tapir" / "spec_form.swift").read_text(encoding="utf-8")
        self.assertIn('case "pen":', src)
        self.assertIn("item.image = swatch(", src)

    def test_presets_pick_the_nearest_colors(self):
        """カラーの組は区分ごとの色にいちばん近いペン、白黒の組は全部を黒に近いペン（ペンセットごとに番号が違う。2026-11-02）."""
        from ashiba.pens import preset_pens

        table = [(1, "#000000", ""), (3, "#E01818", "赤"), (5, "#1848D8", "青"), (6, "#20A030", "緑"), (12, "#808080", "灰"),
                 (20, "#F08C00", "橙"), (30, "#B020B0", "紫"), (40, "#00A8C0", "水色"), (50, "#8C5828", "茶")]
        p = preset_pens(table, "カラー")
        self.assertEqual((p["post"], p["line"], p["deck"], p["equip"], p["tie"], p["net"], p["sheet"], p["dim"]),
                         (3, 5, 6, 20, 40, 50, 12, 1))
        self.assertEqual(set(preset_pens(table, "白黒").values()), {1})
        self.assertEqual(preset_pens([], "カラー"), {})

    def test_titles_round_trip(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import pen_colors as P

        self.assertEqual(P.index_of(P.title_of(20, "シンボル - 一般")), 20)
        self.assertEqual(P.index_of("7"), 7)
        self.assertEqual(P.index_of(""), 1)


class TestDraftHeadNames(unittest.TestCase):
    def test_no_case_clash_with_the_part(self):
        """描き方の決め（gdl_draft.head）の変数は、部品のマスター・2D の別の変数と大文字小文字だけ違う名前にしない.

        GDL は大文字小文字を区別しない。仮囲いの po（パネルの位置）・pt（厚み）が pO（太線のペン 21）・pT（細線のペン）に
        なり、パネルが 21m 先に描かれた（2026-11-04 実機）."""
        import re
        from pathlib import Path

        hsf = Path(__file__).resolve().parents[1] / "gdl" / "hsf"
        assign = re.compile(r"(?:^|[\s:,(])([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*=(?!=)", re.M)
        for d in sorted(hsf.iterdir()):
            s2 = d / "scripts" / "2d.gdl"
            if not s2.exists():
                continue
            t2 = s2.read_text(encoding="utf-8-sig")
            if "描き方の決め（scripts/gdl_draft.py）" not in t2:
                continue
            head, _, body = t2.partition("mk = (")
            hv = {n for n in assign.findall(head)}
            hl = {n.lower(): n for n in hv}
            t1 = (d / "scripts" / "1d.gdl").read_text(encoding="utf-8-sig") if (d / "scripts" / "1d.gdl").exists() else ""
            for n in set(assign.findall(t1 + "\n" + body)) | set(re.findall(r"dim\s+([A-Za-z_][A-Za-z0-9_]*)", t1, re.I)):
                if n.lower() in hl:
                    self.assertEqual(n, hl[n.lower()], (d.name, n, hl[n.lower()]))


if __name__ == "__main__":
    unittest.main()
