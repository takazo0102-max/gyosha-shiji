"""大きなセットバック: 上の階の面の足場を途中の屋根の上から建てて本体の足場に繋ぐ（利用者の指定 2026-10-24: セットバックの
時は途中の屋根から足場が繋がるようにする仕組みを作って）."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_groups
from ashiba.gdl_params import line_params
from ashiba.setback_tiers import setback_tiers

LOW = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]
UP = [[0, 3000], [24000, 3000], [24000, 10000], [0, 10000]]          # 南を 3000 下げた 4〜6階
SLABS = ([{"polygon_mm": LOW, "top_mm": t} for t in (3000, 6000, 9000)]
         + [{"polygon_mm": UP, "top_mm": t} for t in (12000, 15000, 18000)])
SPEC = {"project_name": "S", "outline_mm": LOW, "slabs": SLABS, "module": "inch", "eaves_height_mm": 18000}


class TestSetbackTiers(unittest.TestCase):
    def test_finds_the_upper_face_and_the_middle_roof(self):
        t = setback_tiers(LOW, SLABS)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["top_mm"], 18000)
        self.assertEqual([b for _i, b in t[0]["faces"]], [9000.0])        # 南の面だけ、途中の屋根 GL+9000 から

    def test_small_setback_is_left_to_inner_brackets(self):
        up = [[0, 600], [24000, 600], [24000, 10000], [0, 10000]]
        slabs = SLABS[:3] + [{"polygon_mm": up, "top_mm": 18000}]
        self.assertEqual(setback_tiers(LOW, slabs), [])

    def test_upper_tier_is_a_group_standing_on_the_roof(self):
        g = solve_groups(SPEC)
        self.assertEqual([lb for lb, _r in g], ["", "下段", "上段"])
        main, low, tier = g[0][1].model, g[1][1].model, g[2][1].model
        self.assertLess(main.elevation_of(0).total_height, main.elevation.total_height)   # 本体の南は途中の屋根まで
        self.assertEqual(tier.base_height_mm, 9000.0)
        self.assertEqual(tier.plan.face_names(), ["南面"])
        self.assertAlmostEqual(tier.elevation.total_height, main.elevation_of(0).total_height, delta=200)
        # 端は本体の足場（東・西）に繋ぐ。妻側の手すりは付けない
        p = line_params(tier, tier.plan.edges[0])
        self.assertEqual((p["endOpenS"], p["endOpenE"]), (0, 0))
        self.assertTrue(any("途中の屋根（GL+9000）" in w for w in main.plan.warnings))

    def test_tier_ends_sit_on_main_posts_and_the_far_side_is_low(self):
        # 利用者の指定 2026-10-25: セットバックより先の足場は不要・セットバックから支柱が繋がるように割り付け・両端のジャッキなし
        g = solve_groups(SPEC)
        main, low, tier = g[0][1].model, g[1][1].model, g[2][1].model
        te = tier.plan.edges[0]
        y_in = te.start_post[1]                                   # 上段の内側の建地の列
        y_out = y_in - main.post_row_spacing_mm                   # 外側の列（南へ）
        for face in ("東面", "西面"):
            ep = next(e for e in main.plan.edges if main.face_name(e.edge_index) == face)
            ys = {round(ep.start_post[1] + (ep.end_post[1] - ep.start_post[1]) * t / sum(ep.spans))
                  for t in [sum(ep.spans[:k]) for k in range(len(ep.spans) + 1)]}
            # 本体の面の支柱が上段の内側・外側の列の両方に来る（本体は上段の外側の列から北だけ、上まで上がる）
            self.assertTrue(any(abs(y - y_in) <= 2 for y in ys), (face, y_in, sorted(ys)))
            self.assertTrue(any(abs(y - y_out) <= 2 for y in ys), (face, y_out, sorted(ys)))
            self.assertGreaterEqual(min(ys), y_out - 2)
        # セットバックの先（上段の外側の列より南）は下段: 途中の屋根の高さで止まる
        self.assertEqual(sorted(low.plan.face_names()), ["東面", "西面"])
        for e in low.plan.edges:
            self.assertLessEqual(max(e.start_post[1], e.end_post[1]), y_out + 2)
        # 下段は本体と同じ立面を途中の屋根で切る（面ごとの立面が低い）
        for e in low.plan.edges:
            self.assertLess(low.elevation_of(e.edge_index).total_height, main.elevation.total_height)
        # 上段の両端は本体の支柱に乗る: 支柱・ジャッキベースを描かない
        p = line_params(tier, te)
        self.assertEqual((p["skipPS"], p["skipPE"]), (1, 1))
        # 本体の切れ目は下段の足場の天端より上の層だけ妻側を塞ぎ（下段の床の層は下段に続く）、下段の切れ目は塞がない
        z_low = max(low.elevation_of(e.edge_index).total_height for e in low.plan.edges) / 1000.0
        opens = [line_params(main, e) for e in main.plan.edges]
        self.assertTrue(any(abs(q["endOpenZS"] - z_low) < 1e-6 or abs(q["endOpenZE"] - z_low) < 1e-6 for q in opens))
        self.assertTrue(all(not (line_params(low, e)["endOpenS"] and line_params(low, e)["endOpenE"]) for e in low.plan.edges))
        # 上段の端の支柱は数量でも数えない
        import re

        jl = next(l for l in g[2][1].quantity.lines if l.part.model_no == "A752")
        n_main = int(re.search(r"ジャッキ (\d+)本", jl.note).group(1)) if "内訳" in jl.note else jl.qty
        self.assertEqual(n_main, 2 * tier.plan.total_posts - 4)       # 両端の内外 2本ずつを引く

    def test_floors_line_up_and_spans_are_mostly_1829(self):
        # 利用者の指摘 2026-10-25: 610使いすぎ・床の高さは揃えるようにして
        g = solve_groups(SPEC)
        main, low, tier = (r.model for _lb, r in g)
        main_lv = {round(h + main.base_height_mm) for h in main.elevation.level_heights}
        for m in (low, tier):
            for h in m.elevation.level_heights:
                self.assertIn(round(h + m.base_height_mm), main_lv)
        for m in (main, low):
            for e in m.plan.edges:
                # 端数のスパンは、上段の端の建地列の間隔（1本）と調整の2本まで
                self.assertLessEqual(sum(1 for v in e.spans if v != 1829), 3, (m.face_name(e.edge_index), e.spans))

    def test_sheet_clamps_sit_on_posts(self):
        # 利用者の指摘 2026-10-25: シートクランプが浮いてる箇所がある（範囲の端・上段の端でシートの端の 60 先に付けていた）
        from ashiba.attachments import sheet_clamp_positions

        for _lb, r in solve_groups(SPEC):
            m = r.model
            for e in m.plan.edges:
                posts = [0.0]
                for v in e.spans:
                    posts.append(posts[-1] + v)
                for x in sheet_clamp_positions(m, e, r.stair_plan):
                    self.assertTrue(any(abs(x - p) < 1.0 for p in posts), (m.face_name(e.edge_index), x))

    def test_main_inner_rail_is_open_where_the_tier_joins(self):
        # 利用者の指摘 2026-10-25: セットバックの足場が本体と回らないようになっている布材を配置しないようにして
        g = solve_groups(SPEC)
        main, tier = g[0][1].model, g[2][1].model
        eds = [e for e in main.member_edits if e.reason.startswith("上段への通り")]
        self.assertEqual(len(eds), 2)                                    # 東・西の面の、上段の内外の建地の列の間
        for e in eds:
            ep = next(x for x in main.plan.edges if x.edge_index == e.edge_index)
            self.assertEqual(ep.spans[e.span_from - 1], round(main.post_row_spacing_mm))
            self.assertEqual(e.parts, ("内側手すり",))
            z = main.elevation_of(e.edge_index).level_heights[e.level_from - 1] + main.base_height_mm
            self.assertGreaterEqual(z, tier.base_height_mm)              # 途中の屋根より上の層だけ
            self.assertIn(f",{e.level_from},", line_params(main, ep)["editList"])

    def test_tier_top_and_sheet_rows_match_the_main(self):
        # 利用者の指定 2026-10-25: シートの高さも揃えて（上段の天端が本体より 450 高く、シートは屋根の上 3m から下が無かった）
        from ashiba.attachments import sheet_bottom_mm, sheet_rows, sheet_top_mm

        g = solve_groups(SPEC)
        main, low, tier = (r.model for _lb, r in g)
        top = main.elevation.total_height + main.base_height_mm
        self.assertEqual(tier.elevation.total_height + tier.base_height_mm, top)
        ei = tier.plan.edges[0].edge_index
        main_joints = {round(hi + main.base_height_mm) for e in main.plan.edges
                       for _lo, hi in sheet_rows(main, e.edge_index)}
        for _lo, hi in sheet_rows(tier, ei):
            self.assertIn(round(hi + tier.base_height_mm), main_joints)
        # 上段のシートは下段のシート（低い所のメッシュ）の天端から上だけ（利用者の指定 2026-10-25: セットバック部分も
        # メッシュシートは低いところのメッシュの高さまででいいよ）
        low_top = max(sheet_top_mm(low, e.edge_index) for e in low.plan.edges) + low.base_height_mm
        self.assertAlmostEqual(sheet_bottom_mm(tier, ei) + tier.base_height_mm, low_top, delta=1)

    def test_open_ends_above_the_roof_get_end_sheets(self):
        # 利用者の指摘 2026-10-25: 妻側にもシートいるよ
        from ashiba.attachments import SHEET_OBJECT, open_end_sheets, sheet_placements

        from ashiba.attachments import sheet_clamp_heights_from

        g = solve_groups(SPEC)
        main, low = g[0][1].model, g[1][1].model
        from ashiba.attachments import sheet_top_mm

        ends = {(e.edge_index, end): z for e in main.plan.edges for end, z in open_end_sheets(main, e)}
        self.assertEqual(len(ends), 2)                                   # 東・西の面の、セットバックの先の端
        for (ei, _end), z in ends.items():
            # 妻側を塞ぐのは下段の足場の天端より上の層、シートは下段のシートの天端から上（利用者の指定 2026-10-25:
            # セットバックのメッシュは低いところの足場までにして・低いところのメッシュの高さまで）
            self.assertAlmostEqual(z, sheet_top_mm(low, ei), delta=1)
            self.assertAlmostEqual(line_params(main, next(e for e in main.plan.edges if e.edge_index == ei))[
                "endOpenZS" if _end == "s" else "endOpenZE"] * 1000, low.elevation_of(ei).total_height, delta=1)
            # クランプはシートの上と下のハトメ（利用者の指定 2026-10-25: メッシュクランプは上と下につけて）
            hs = sheet_clamp_heights_from(main, ei, z)
            self.assertTrue(z + 20 <= hs[0] < z + 20 + 450, hs)
            self.assertAlmostEqual(hs[-1], sheet_top_mm(main, ei) - 20, delta=1)
        pls = [p for p in sheet_placements(main) if p.part == SHEET_OBJECT
               and any(abs(p.params["zB"] * 1000 - z) < 1 for z in ends.values()) and p.params.get("clampEnd")]
        self.assertEqual(len(pls), 2)
        # 面のシートとの角（外側の建地）はコーナー用（利用者の指定 2026-10-25: コーナー部分はコーナー用にして）
        self.assertEqual(sorted(p.params["clampCS"] + p.params["clampCE"] for p in pls), [1, 1])
        faces = [p for p in sheet_placements(main) if p.part == SHEET_OBJECT and p.params.get("rowList")
                 and (p.params.get("clampSZ") or p.params.get("clampEZ"))]
        self.assertEqual(len(faces), 2)

    def test_nets_stay_out_from_under_the_tier(self):
        # 利用者の指摘 2026-10-25: ネットクランプが足場の下まで入っている
        from ashiba.attachments import NET_OBJECT, net_placements

        g = solve_groups({**SPEC, "horizontal_net_levels": [4, 5, 6]})
        main = g[0][1].model
        self.assertEqual(len(main.tier_passages), 2)
        for ei, x0, x1, zp in main.tier_passages:
            ep = next(e for e in main.plan.edges if e.edge_index == ei)
            o = ep.start_post
            L = float(sum(ep.spans))
            u = ((ep.end_post[0] - o[0]) / L, (ep.end_post[1] - o[1]) / L)
            for p in net_placements(main):
                if p.part != NET_OBJECT or abs(p.params["faceAng"] - math.degrees(math.atan2(u[1], u[0]))) > 0.1:
                    continue
                a = (p.x_mm - o[0]) * u[0] + (p.y_mm - o[1]) * u[1]
                b = a + p.params["netL"] * 1000
                if p.params["zH"] * 1000 >= zp - 500:
                    self.assertTrue(b <= x0 + 1 or a >= x1 - 1, (ei, a, b, x0, x1))

    def test_tier_lines_go_on_the_main_floor(self):
        # 利用者の指定 2026-10-25: セットバックで上に配置した足場等は1階に表示するようにして（z だけで置くと屋根の高さの
        # 階に入る）
        from ashiba.tapir_adapter import place_scaffold_lines

        class Fake:
            def __init__(self):
                self.calls = []

            def create_object(self, name, x, y, z=0.0, floor_index=None):
                self.calls.append((z, floor_index))
                return {"elementId": {"guid": f"g{len(self.calls)}"}}

            def rotate_element(self, *a, **kw):
                pass

            def set_gdl_parameters(self, *a, **kw):
                pass

            def delete_elements(self, *a):
                pass

            def find_member_surfaces(self):
                return {}

        g = solve_groups(SPEC)
        c = Fake()
        place_scaffold_lines(g[2][1].model, "ashiba_line", c, floor_index=0)
        self.assertTrue(c.calls)
        self.assertTrue(all(z == 9000.0 and f == 0 for z, f in c.calls), c.calls)

    def test_section_names_stay_unique(self):
        # 実機 2026-10-24: 断面 A-A が本体の南面と上段の南面を横切り、同じ名前「A-A 南面」が2つになった
        from ashiba.cross_sections import cross_section_specs, split_cross_specs_with_owner

        g = solve_groups({**SPEC, "cross_cuts_mm": [[[12000, -6000], [12000, 15000]]]})
        owners = [(r.model, r.stair_plan, r.terrain) for _lb, r in g]
        specs = [s for s, _o in split_cross_specs_with_owner(owners, cross_section_specs(g[0][1].model, "x"))]
        names = [s.face_name for s in specs]
        self.assertEqual(len(names), len(set(names)), names)
        self.assertIn("A-A 南面（上段）", names)

    def test_can_be_turned_off(self):
        self.assertEqual(len(solve_groups({**SPEC, "setback_tiers": False})), 1)


BIG = [[0, -2000], [24000, -2000], [24000, 10000], [0, 10000]]    # 2階から上が南へ 2000 張り出す
SL_OVER = ([{"polygon_mm": LOW, "top_mm": 0}]
           + [{"polygon_mm": BIG, "top_mm": t} for t in (3000, 6000, 9000, 12000)])


class TestOverhangTier(unittest.TestCase):
    """上の階が外へ張り出す（拡張。利用者の指定 2026-10-24: 上階で拡張する仕組みと拡小する仕組みを作って）."""

    SP = {"project_name": "H", "outline_mm": LOW, "slabs": SL_OVER, "module": "inch", "eaves_height_mm": 12000}

    def test_upper_tier_stands_on_brackets(self):
        g = solve_groups(self.SP)
        self.assertEqual([lb for lb, _r in g], ["", "上段（張り出し）"])
        main, tier = g[0][1].model, g[1][1].model
        self.assertTrue(tier.hane_bracket)
        self.assertEqual(tier.base_height_mm, 3000.0)
        self.assertEqual(len(tier.plan.edges), 4)                                      # 全周
        self.assertAlmostEqual(line_params(tier, tier.plan.edges[0])["haneD"], 0.6)
        self.assertEqual(line_params(main, main.plan.edges[0])["haneD"], 0.0)
        # 本体の足場はブラケットの下端（3000−600）より下で止まる。張り出しを庇としてかわさない（離れはそのまま）
        for e in main.plan.edges:
            self.assertLessEqual(main.elevation_of(e.edge_index).total_height, 2400)
        self.assertLess(max(e.standoff for e in main.plan.edges), 600)
        self.assertTrue(any("跳ね出しブラケット" in w for w in g[1][1].quantity.warnings))
        self.assertTrue(any("張り出した上の階" in w for w in main.plan.warnings))

    def test_gdl_draws_the_brackets(self):
        from pathlib import Path

        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"
        self.assertIn("if haneD > 0.001 then", (gdl / "3d.gdl").read_text(encoding="utf-8"))
        self.assertIn("跳ね出しブラケットの上に建てる", (gdl / "2d.gdl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
