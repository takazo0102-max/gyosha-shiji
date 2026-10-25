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
        self.assertEqual(n_main, 2 * (tier.plan.total_posts + 1) - 4)  # 両端を含む位置から両端の内外 2本ずつを引く

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

    def test_tier_standoff_is_not_too_narrow(self):
        # 実機 2026-10-25: セットバックの躯体との隙間が153 かなり狭いので250~350の間で調整・本体は全部同じ離れでなくて
        # いい・本体250・上段236で。10m 角で西半分が上の階（壁の段差 5000）。インチの支柱は 304.8 刻みなので、上段の両脇の
        # 本体の面（東・西）の離れの配分を変え、上段を 200〜350（setback_standoff_min）に入れる。本体の面は最小（250）より
        # 狭くせず、最大（350）を超えた面は内ブラケット
        full = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
        west = [[0, 0], [5000, 0], [5000, 10000], [0, 10000]]
        slabs = ([{"polygon_mm": full, "top_mm": t} for t in (0, 3000)]
                 + [{"polygon_mm": west, "top_mm": t} for t in (6000, 9000, 9700)])
        user = {"project_name": "S", "outline_mm": full, "slabs": slabs, "module": "inch",
                "series_id": "nikken_nd1800", "scaffold_width_mm": 914, "eaves_height_mm": 15400}
        for spec in (user, SPEC):
            g = solve_groups(spec)
            tier = g[-1][1].model
            for e in tier.plan.edges:
                self.assertTrue(200 - 1 <= e.standoff <= 350 + 1, (spec["outline_mm"], e.standoff))
        # 上段の端を本体の支柱に揃えると東面の離れが 418（内ブラケット）になる。無理に繋げず、上段は自前の支柱で離れ 300、
        # 端は本体の内側の建地の列の 150 手前で止めて妻側を塞ぐ（利用者の指定 2026-10-25: ブラケット出てるところがある
        # 無理に繋げなくてもいいよ）。本体の離れはどの面も 250〜350 のまま、内ブラケットは出ない
        from ashiba.gdl_params import line_params

        g = solve_groups(user)
        main, tier = g[0][1], g[-1][1].model
        self.assertTrue(all(250 <= e.standoff <= 350 for e in main.model.plan.edges),
                        [e.standoff for e in main.model.plan.edges])
        self.assertFalse([b for b in main.brackets if b.direction == "内"])
        te = tier.plan.edges[0]
        self.assertAlmostEqual(te.standoff, 300, delta=30)
        p = line_params(tier, te)
        self.assertEqual((p["skipPS"], p["skipPE"]), (0, 0))                 # 自前の支柱・ジャッキ
        self.assertEqual((p["endOpenS"], p["endOpenE"]), (1, 1))             # 妻側を塞ぐ
        inner_y = sorted(e.start_post[1] for e in main.model.plan.edges if abs(e.start_post[1] - e.end_post[1]) < 1)
        ys = sorted((te.start_post[1], te.end_post[1]))
        self.assertAlmostEqual(ys[0] - inner_y[0], 150, delta=2)           # 本体の内側の建地の列の 150 手前
        self.assertAlmostEqual(inner_y[-1] - ys[1], 150, delta=2)
        self.assertFalse([e for e in main.model.member_edits if e.reason.startswith("上段への通り")])

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
        # 利用者の指定 2026-10-25: 拡張は張り出す面だけ跳ね出しにして。張り出した南面と、張り出しの横の短い面（東・西の
        # 張り出した部分）だけをブラケットの上に建てる。張り出していない本体の面（東・西・北）は地上から上まで通し、
        # 張り出しの下になる本体の南面だけブラケットの下で止める
        g = solve_groups(self.SP)
        self.assertEqual([lb for lb, _r in g], ["", "上段（張り出し）"])
        main, tier = g[0][1].model, g[1][1].model
        self.assertTrue(tier.hane_bracket)
        self.assertEqual(tier.base_height_mm, 3000.0)
        names = [tier.face_name(e.edge_index) for e in tier.plan.edges]
        self.assertEqual(sorted(names), ["南面", "東面", "西面"])
        south = next(e for e in tier.plan.edges if tier.face_name(e.edge_index) == "南面")
        self.assertAlmostEqual(line_params(tier, south)["haneD"], 0.6)
        self.assertEqual(line_params(main, main.plan.edges[0])["haneD"], 0.0)
        # 横の短い面は張り出した部分だけ（本体の隅の升目の手前で止める。端は開放端）
        row = main.post_row_spacing_mm
        so_s = next(e.standoff for e in main.plan.edges if main.face_name(e.edge_index) == "南面")
        for e in tier.plan.edges:
            if tier.face_name(e.edge_index) == "南面":
                continue
            ys = (e.start_post[1], e.end_post[1])
            self.assertLessEqual(max(ys), -so_s - row - 50)               # 本体の隅の升目（y≧−離れ−建地列間隔）に入らない
            p = line_params(tier, e)
            self.assertEqual(p["endOpenS"] + p["endOpenE"], 1)
        tops = {main.face_name(e.edge_index): main.elevation_of(e.edge_index).total_height for e in main.plan.edges}
        self.assertLessEqual(tops["南面"], 3000 - 300 - 100)                # ブラケットの取付プレートの下端より下
        for f in ("東面", "西面", "北面"):
            self.assertGreater(tops[f], 12000)                             # 地上から上まで
        # 本体の南面にも作業床が1層（1階の壁の作業用）。コマは隣の面とそろう
        self.assertEqual(main.elevation_of(0).n_levels, 1)
        self.assertIn(main.elevation_of(0).level_heights[0], main.elevation.level_heights)
        # 上段の床は本体の床にそろう
        for h in tier.elevation.level_heights:
            self.assertIn(round(h + tier.base_height_mm), {round(v) for v in main.elevation.level_heights})
        self.assertLess(max(e.standoff for e in main.plan.edges), 600)
        w = [x for x in g[1][1].quantity.warnings if "跳ね出しブラケット" in x]
        self.assertTrue(w and "アンカー M16" in w[0] and "渡し梁" in w[0], w)

    def test_one_metre_overhang_with_a_setback(self):
        # 実機 2026-10-25: 1000mm はねだしている うまくいってない。3階から上が西へ 1000 張り出し、東へ 5000 下がる。
        # 張り出しの判定が「上の階の外形が本体を含む」、セットバックの判定が「本体の中に収まる」だったので、どちらにも
        # ならず、西面を庇としてかわして離れ 1150 にしていた
        full = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
        up = [[-1000, 0], [5000, 0], [5000, 10000], [-1000, 10000]]
        slabs = ([{"polygon_mm": full, "top_mm": t} for t in (0, 3000)]
                 + [{"polygon_mm": up, "top_mm": t} for t in (6000, 9000, 9700)])
        g = solve_groups({"project_name": "W", "outline_mm": full, "slabs": slabs, "module": "inch",
                          "series_id": "nikken_nd1800", "scaffold_width_mm": 610, "eaves_height_mm": 15400})
        labels = [lb for lb, _r in g]
        self.assertIn("上段（張り出し）", labels)
        self.assertIn("上段", labels)
        hane = dict(g)["上段（張り出し）"].model
        self.assertTrue(hane.hane_bracket)
        self.assertEqual(hane.base_height_mm, 6000.0)
        self.assertEqual([hane.face_name(e.edge_index) for e in hane.plan.edges], ["西面"])
        self.assertTrue(all(250 <= e.standoff <= 350 for e in hane.plan.edges))
        main = g[0][1].model
        so = {main.face_name(e.edge_index): e.standoff for e in main.plan.edges}
        self.assertLess(so["西面"], 400)                                    # 庇としてかわさない
        west = next(e for e in main.plan.edges if main.face_name(e.edge_index) == "西面")
        self.assertLessEqual(main.elevation_of(west.edge_index).total_height, 6000 - 300)   # ブラケットの下で止める

    def test_side_faces_join_by_widening_brackets(self):
        # 利用者の指定 2026-10-25: 張り出しの横の面も足場入れて ブラケットで繋がるようにしてみて／拡張ブラケットリサーチして
        # 修正して（reports/くさび式足場の拡幅ブラケット.md）。西へ 1000 張り出した上の階: 本体の西面は張り出しの下で止まるが、
        # 北西・南西の隅の升目は北面・南面（上まで通る）の高さまで立つ。その外側の2本に拡幅ブラケット 305（日建 NDBK03H）を
        # 跳ね出しの上段のいちばん下の床で1回だけ付けて先端に支柱を立て、跳ね出しの上段の両端からは各層で張出ブラケット 610
        # （NDBK06H）で床を持ち出す。2つの床のあき（50）は 3cm を超えるのですき間板
        full = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
        up = [[-1000, 0], [5000, 0], [5000, 10000], [-1000, 10000]]
        slabs = ([{"polygon_mm": full, "top_mm": t} for t in (0, 3000)]
                 + [{"polygon_mm": up, "top_mm": t} for t in (6000, 9000, 9700)])
        g = solve_groups({"project_name": "W", "outline_mm": full, "slabs": slabs, "module": "inch",
                          "series_id": "nikken_nd1800", "scaffold_width_mm": 610, "eaves_height_mm": 15400})
        main, hane = g[0][1].model, dict(g)["上段（張り出し）"].model
        name = {main.face_name(e.edge_index): e for e in main.plan.edges}
        pw, ps = line_params(main, name["西面"]), line_params(main, name["南面"])
        # 北西: 西面（低い）が描く隅の升目を北面の積み方で。西面の始点・終点の外側建地は隅の升目の側が立てる
        self.assertTrue(pw["cnrPosts"] and pw["cnrLevels"])
        self.assertEqual((pw["skipOutS"], pw["skipOutE"]), (1, 1))
        self.assertGreater(pw["cnrLowS"], 0)
        # 南西: 南面（高い）が描く隅の升目に、西面の終点の外側建地と、西面の天端より上の層の辺
        self.assertGreater(ps["cnrLowP"], 0)
        self.assertEqual(ps["cnrPosts"], "")
        # 拡幅ブラケット: 本体の隅は 305（跳ね出しの上段の内側建地の手前 45 以上あける）。拡幅する層は跳ね出しの上段の床
        lv_t = [round(h + hane.base_height_mm) for h in hane.elevation.level_heights]
        for p, side in ((pw, 0), (ps, 1)):
            self.assertAlmostEqual(p["cnrBkW"], 0.305)
            self.assertEqual(p["cnrBkP"], side)
            self.assertEqual([int(v) for v in p["cnrBkLv"].split(",")], lv_t)
            self.assertGreater(p["cnrBkG"], 0.03)                          # すき間板が要る
        he = hane.plan.edges[0]
        ph = line_params(hane, he)
        row = main.post_row_spacing_mm
        self.assertAlmostEqual(ph["hbExtS"], row / 1000.0)                  # 張出ブラケット 610（本体の外側の列まで）
        self.assertAlmostEqual(ph["hbExtE"], row / 1000.0)
        self.assertEqual((ph["endOpenS"], ph["endOpenE"]), (0, 0))         # 端の先の床の手すりが塞ぐ
        gap = (1000 + he.standoff) - (name["西面"].standoff + row) - 305
        self.assertGreaterEqual(gap, 45)
        # 上段の端の支柱は床スラブの外（躯体の角の先）: 壁に留められる区間は角から 150 内側まで
        self.assertGreater(ph["haneX0"], 0)
        self.assertLess(ph["haneX1"], sum(he.spans) / 1000.0)
        self.assertAlmostEqual(ph["haneX1"] - ph["haneX0"], (10000 - 300) / 1000.0, places=3)
        # 数量: 拡幅ブラケット 305（日建 NDBK03H）は2隅×2基（全高で1回）、張出ブラケット 610（NDBK06H）は2端×2基×層
        n_lv = len(hane.elevation.level_heights)
        self.assertEqual(g[0][1].quantity.qty_of("ブラケット", 305), 2 * 2)
        self.assertEqual(dict(g)["上段（張り出し）"].quantity.qty_of("ブラケット", 610), 2 * 2 * n_lv)
        w = " ".join(g[0][1].quantity.warnings)
        self.assertIn("すき間板", w)
        self.assertIn("補強単管", w)
        self.assertIn("床スラブの外の端の支柱を受ける渡し梁", " ".join(dict(g)["上段（張り出し）"].quantity.warnings))
        self.assertTrue(any("拡幅ブラケット305を1回だけ" in x for x in main.plan.warnings))
        # 構造検定（利用者の指定 2026-10-25: 構造検定も直して）: ブラケットを付けた組の支柱は拡幅部の許容（日建 ND1800
        # 8.8kN/本）で、ブラケットは1基ずつ許容支持力（6.0kN）で。先端の支柱は隅の升目の天端まで（自重に入る）
        for lb, n_b in (("", 2), ("上段（張り出し）", 2 * 1)):
            st = dict(g)[lb].structural
            self.assertTrue(st.post.widened)
            self.assertAlmostEqual(st.post.allowable_kn, 8.8)
            self.assertEqual(len(st.brackets), n_b)
            self.assertTrue(all(b.ok and b.allowable_kn == 6.0 for b in st.brackets))
        self.assertGreater(min(b.load_kn for b in g[0][1].structural.brackets), 1.3)
        self.assertGreaterEqual(main.own_height(name["北面"].edge_index), 10000)   # 下段の組の値（5650）ではなく

    def test_gdl_draws_the_widening_brackets(self):
        from pathlib import Path

        d = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line"
        d3 = (d / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        wide = d3[d3.index("759:\t! ---- 拡幅ブラケットで升目を広げる"):]
        wide = wide[:wide.index("\treturn\n")]
        for word in ("補強単管", "先端の支柱", "すき間板", "gosub 754", "gosub 870", "gosub 753"):
            self.assertIn(word, wide)
        over = d3[d3.index("758:\t! ---- 張出ブラケットの床1層"):]
        over = over[:over.index("\treturn\n")]
        for word in ("2 * komaPitch", "手すり柱", "dkW = 0.49"):
            self.assertIn(word, over)
        # 隅の升目（cornerS）の外は拡幅（gosub 759）、跳ね出しの上段の端（hbExtS・hbExtE）は張出（gosub 758）
        self.assertIn("if cnrBkW > 0.001 and nCBk > 0 then", d3)
        self.assertIn("gosub 759", d3)
        self.assertIn("xbW = hbExtS", d3)
        # 隅の升目は高い方の面の積み方（gosub 757）、低い面の隅の外側建地は skipOut で描かない
        self.assertIn("gosub 757", d3)
        self.assertIn("skipOutS = 1", d3)
        pl = (d / "paramlist.xml").read_text(encoding="utf-8")
        for n in ("cnrPosts", "cnrLevels", "cnrBkW", "cnrBkG", "hbExtS", "haneX0", "skipOutE"):
            self.assertIn(f'Name="{n}"', pl)
        self.assertIn("cnrBkLv", (d / "scripts" / "1d.gdl").read_text(encoding="utf-8"))
        d2 = (d / "scripts" / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("拡幅ブラケット", d2)
        self.assertIn("張出ブラケット", d2)

    def test_gdl_draws_the_brackets(self):
        from pathlib import Path

        gdl = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts"
        d3 = (gdl / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("if haneD > 0.001 then", d3)
        sub = d3[d3.index("760:\t! ---- 跳ね出しブラケット1基"):]
        sub = sub[:sub.index("return\n")]
        for word in ("溝形鋼", "取付プレート", "アンカーボルト M16×4", "吊り材", "受けプレート"):
            self.assertIn(word, sub)
        self.assertIn("隣の面のブラケットの腕との間に渡し梁", d3)
        self.assertIn("跳ね出しブラケットの上に建てる", (gdl / "2d.gdl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
