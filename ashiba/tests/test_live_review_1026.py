"""2026-10-26 の実機の指摘（利用者: リサーチして しっかり確認してよ・・ 単管足場の位置も屋上の渡りも適当だな）で直したところ."""

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, solve_groups

SQ = [[0, 0], [10000, 0], [10000, 10000], [0, 10000]]
# 利用者の建物の形（南面だけ本足場、東面は下屋の単管抱き足場、北・西は一側足場。屋根は東の下屋 3.0m）
USER = {"outline_mm": SQ, "module": "inch", "scaffold_width_mm": 610, "eaves_height_mm": 15400,
        "face_eaves_mm": {"東面": 3000}, "face_forms": "東面=単管抱き足場;北面=一側足場;西面=一側足場"}


class TestHugMeetsItsNeighbours(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = solve_groups(USER)
        cls.hug = next(r for lb, r in cls.g if "抱き" in lb).model
        cls.rigid = [r.model for lb, r in cls.g if "抱き" not in lb]

    def test_corner_posts_are_the_neighbours_posts(self):
        # 単管の始点・終点の建地は、隣の組（本足場・一側足場）の端の建地と同じ位置（70 ずれて2本立っていた）
        (ep,) = self.hug.plan.edges
        ends = [p for m in self.rigid for e in m.plan.edges for p in (e.start_post, e.end_post)]
        for pt in (ep.start_post, ep.end_post):
            self.assertLess(min(math.dist(pt, q) for q in ends), 1.0, pt)

    def test_shared_corner_posts_are_drawn_once(self):
        self.assertEqual(self.hug.skip_end_posts, {(1, "s"), (1, "e")})

    def test_shared_ends_are_not_open_ends(self):
        # 単管と建地を共有して繋いだ端は開放端ではない（妻側の手すり「布材0」・幅0 のシート・一側の布材350 を出していた）
        for lb, r in self.g:
            ws = [w[2] for w in r.warnings]
            self.assertFalse([w for w in ws if "開放端" in w or "幅0" in w or "布材0" in w], (lb, ws))
        self.assertEqual(self.hug.joined_ends, {(1, "s"), (1, "e")})

    def test_group_warnings_name_only_its_own_faces(self):
        # 本体（南面だけ）の要確認に「南面・東面・北面・西面: 離れ…」とほかの組の面まで並び、同じ文が組の数だけ重なった
        for lb, r in self.g:
            own = set(r.model.plan.face_names())
            for w in r.model.plan.warnings:
                head, sep, _rest = w.partition(": ")
                if sep and "離れ" in _rest[:4]:
                    self.assertTrue(set(head.split("・")) <= own, (lb, w))

    def test_aligned_face_says_it_follows_the_neighbour(self):
        # 単管の面の離れは隣の組の線にそろえた値。「この形状で組める離れは他に 250mm」は当てはまらない
        ws = [w for w in self.hug.plan.warnings if "離れ" in w]
        self.assertTrue(ws)
        self.assertFalse([w for w in ws if "他に" in w], ws)

    def test_tube_spans_stay_within_the_law(self):
        (ep,) = self.hug.plan.edges
        self.assertTrue(all(300 <= s <= 1800 for s in ep.spans), ep.spans)       # 安衛則571条一号 1.85m 以下
        self.assertAlmostEqual(sum(ep.spans), ep.scaffold_length, delta=1.0)

    def test_hug_decks_match_the_main_scaffold(self):
        main = next(m for m in self.rigid if m.config.scaffold_form == "本足場")
        lv = self.hug.elevation_of(1).level_heights
        self.assertTrue(set(lv) <= set(main.elevation.level_heights), (lv, main.elevation.level_heights))

    def test_lean_to_hug_stops_under_the_eaves_with_eave_rails(self):
        # 下屋 3.0m の面: 最上段の床は軒の下、軒先から 450・900 に手すり、建地はその上まで（床が 4.63m に出ていた）
        e = self.hug.elevation_of(1)
        self.assertLessEqual(max(e.level_heights), 3000 + 300)
        self.assertEqual(e.eave_rails_mm, [3450, 3900])
        self.assertGreaterEqual(e.total_height, 3900 + 100)
        self.assertLess(e.total_height, 5000)                       # 建物全体の高さ（11m）で拾わない


class TestTierFollowsTheGroups(unittest.TestCase):
    def test_setback_junction_runs_with_switched_faces(self):
        # 面を切り替えた建物は上段の繋ぎ（setback_junctions）を通さず、南面の本足場が下屋（3.0m）の上まで 11.7m で建ち
        # （壁つなぎの取れない自立部分）、上段の端の建地が本体の建地と 152 ずれて宙に立った（実機の複製で見つけた）
        g = solve_groups({**USER, "face_eaves_mm": {"東面": 3000}, "eaves_height_mm": 9700,
                          "slabs": [{"polygon_mm": [[0, 0], [10000, 0], [10000, 10000], [0, 10000]], "top_mm": 3000},
                                    {"polygon_mm": [[0, 0], [5000, 0], [5000, 10000], [0, 10000]], "top_mm": 9700}]})
        labels = [lb for lb, _r in g]
        self.assertIn("下段", labels)                                     # 南面の下屋の上は途中の屋根で止める
        self.assertIn("一側足場（下段）", labels)                         # 切り替えた北面も、その種類のまま止める
        for lb, r in g:
            if "下段" in lb:
                self.assertLess(r.model.elevation_of(r.model.plan.edges[0].edge_index).total_height, 6000)
            # 下段の壁つなぎの垂直間隔を全体の高さで測って NG（8155mm）にしていた
            self.assertFalse([c for c in r.checks if c.status == "NG" and "壁つなぎ" in c.name], lb)
        main = next(r.model for lb, r in g if lb == "")
        tier = next(r.model for lb, r in g if lb.startswith("上段"))
        # 上段は本体の内側の建地の列の手前で止める（本体の建地に乗せられない形）か、本体の線にそろう
        y0 = tier.plan.edges[0].start_post[1]
        self.assertGreaterEqual(y0, main.plan.edges[0].start_post[1] - 0.5)


class TestOneSpanSectionTies(unittest.TestCase):
    def test_one_span_section_is_a_warning_not_a_spacing_ng(self):
        # 1スパンだけの面（面の区間の切れ端）は格子の壁つなぎが入らない前提。朝顔の取付部の1本だけで垂直間隔を測って
        # 6355mm の NG にしていた（セットバックの東面を一側足場にした下段）
        from ashiba.law_check import check_wall_ties
        from ashiba.model import WallTie

        r = solve_all({"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
                       "module": "inch"})
        m = r.model
        import dataclasses

        one = dataclasses.replace(m.plan.edges[0], spans=[1829], scaffold_length=1829.0)
        m.plan = dataclasses.replace(m.plan, edges=[one])
        m.wall_ties = [WallTie(one.edge_index, 0.0, 3600, "asagao")]
        c = check_wall_ties(m)
        self.assertEqual(c.status, "WARN")
        self.assertIn("1スパンの面", c.message)


class TestSwitchedFaceLowSection(unittest.TestCase):
    def test_low_section_of_a_switched_face_continues_its_line(self):
        # セットバックの西面を一側足場にすると「一側足場（下段）」が面の無い組になって壁つなぎの NG、直すと上の区間と
        # 建地の線が 96 ずれた（2026-10-26 のループ）
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from dev_cases import floors

        fl = floors("setback", 0, 0)
        slabs = [{"polygon_mm": [list(p) for p in poly], "top_mm": top} for poly, top in fl]
        g = dict(solve_groups({"outline_mm": [list(p) for p in fl[0][0]], "eaves_height_mm": 18000, "module": "inch",
                               "slabs": slabs, "face_forms": "西面=一側足場"}))
        up, low = g["一側足場"].model, g["一側足場（下段）"].model
        self.assertTrue(low.plan.edges)
        self.assertAlmostEqual(up.plan.edges[0].end_post[0], low.plan.edges[0].start_post[0], delta=0.5)
        self.assertAlmostEqual(up.plan.edges[0].end_post[1], low.plan.edges[0].start_post[1], delta=0.5)


class TestTubeRunStopsShortOfTheWall(unittest.TestCase):
    def test_end_room_moves_the_overrun_to_the_other_end(self):
        # L 字の入隅で、単管の通しが端の建地から 470 出て、離れ 350 の先の壁を 120 突き抜けていた
        from ashiba.tube_runs import plan_run

        spans = [1800, 1800, 1800, 1616, 914]
        free = plan_run(spans)
        self.assertEqual(free.start_mm, -100)
        held = plan_run(spans, end_room=300)
        self.assertLessEqual(held.end_mm - sum(spans), 300)
        self.assertGreaterEqual(held.end_mm - sum(spans), 100)
        self.assertEqual(sorted(held.pieces), sorted(free.pieces))

    def test_inner_corner_ends_of_a_tankan_ell_stay_off_the_walls(self):
        from ashiba.cli import solve_all
        from ashiba.tube_runs import board_limits, face_boards, face_runs, run_rooms

        r = solve_all({"outline_mm": [[0, 0], [16000, 0], [16000, 6000], [8000, 6000], [8000, 12000], [0, 12000]],
                       "eaves_height_mm": 9000, "series_id": "tankan", "module": "metric"})
        m = r.model
        hit = 0
        for ep in m.plan.edges:
            s_room, e_room = run_rooms(m, ep)
            a, _b = face_runs(list(ep.spans), s_room, e_room)
            if e_room is not None:
                hit += 1
                self.assertLessEqual(a.end_mm - sum(ep.spans), e_room + 1e-6)
                self.assertLessEqual(face_boards(list(ep.spans), **board_limits(m, ep))[0].end_mm - sum(ep.spans),
                                     e_room + 1e-6)
            if s_room is not None:
                self.assertLessEqual(-a.start_mm, s_room + 1e-6)
        self.assertGreater(hit, 0)


class TestTubeSharesPostsOnItsLine(unittest.TestCase):
    def test_tube_spans_put_a_post_at_the_mark(self):
        from ashiba.plan_solver import tube_spans_through

        sp = tube_spans_through([1800, 1800, 1800, 1800, 730], [7320.0], 1800)
        xs = [sum(sp[:i]) for i in range(len(sp) + 1)]
        self.assertIn(7320, xs)
        self.assertEqual(sum(sp), 7930)
        self.assertTrue(all(300 <= v <= 1800 for v in sp), sp)
        self.assertEqual(tube_spans_through([1800, 1800], [1800.0], 1800), [1800, 1800])

    def test_hug_at_an_inner_corner_shares_the_main_outer_post(self):
        # L 字の入隅で、単管抱き足場の建地が本足場の外側の建地から 120 ずれて立っていた
        import math
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from dev_cases import floors

        from ashiba.cli import solve_groups

        fl = floors("ell", 0, 0)
        slabs = [{"polygon_mm": [list(p) for p in poly], "top_mm": top} for poly, top in fl]
        g = dict(solve_groups({"outline_mm": [list(p) for p in fl[0][0]], "eaves_height_mm": 9000, "module": "inch",
                               "series_id": "nikken_nd1800", "slabs": slabs,
                               "face_forms": "北面(辺2)=単管抱き足場"}))
        hug = g["単管抱き足場"].model.plan.edges[0]
        main = g[""].model
        e3 = next(e for e in main.plan.edges if e.edge_index == 3)
        oe = main.plan.outline.edges[3]
        row = main.row_spacing_of(3)
        outer = (e3.start_post[0] + oe.outward[0] * row, e3.start_post[1] + oe.outward[1] * row)
        d = g["単管抱き足場"].model.plan.outline.edges[hug.edge_index].direction
        xs = [sum(hug.spans[:i]) for i in range(len(hug.spans) + 1)]
        pts = [(hug.start_post[0] + d[0] * x, hug.start_post[1] + d[1] * x) for x in xs]
        self.assertLess(min(math.dist(p, outer) for p in pts), 2.0)


class TestWedgeCornerClosesOrSteps(unittest.TestCase):
    def test_feet_corners_close_within_the_wedge_play_or_take_a_corner_step(self):
        # 隙間 30 以下を「閉じた」とみなしていて、12m×8m のインチで面の最後の建地が隅の建地から 30 手前に立ち、
        # 2本が重なっていた（布材も 30 足りない）。閉じるのはくさびの遊び 10 まで、それ以外はコーナーステップ
        import math

        from ashiba.cli import solve_all
        from ashiba.plan_solver import WEDGE_GAP_CLOSED_MM, WEDGE_STEP_MIN_MM

        for W, D in ((12000, 8000), (9000, 6000), (20000, 10000), (15000, 7000)):
            r = solve_all({"outline_mm": [[0, 0], [W, 0], [W, D], [0, D]], "eaves_height_mm": 9000,
                           "series_id": "nikken_nd1800", "module": "inch"})
            for e in r.model.plan.edges:
                gap = math.dist(e.start_post, e.end_post) - sum(e.spans)
                with self.subTest(W=W, D=D, face=e.edge_index):
                    self.assertTrue(-0.5 <= gap <= WEDGE_GAP_CLOSED_MM or gap >= WEDGE_STEP_MIN_MM, gap)
        r = solve_all({"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
                       "series_id": "nikken_nd1800", "module": "inch"})
        self.assertLessEqual(max(math.dist(e.start_post, e.end_post) - sum(e.spans) for e in r.model.plan.edges
                                 if e.edge_index in (1, 3)), 5.0)


class TestBridgeDeckFitsTheGap(unittest.TestCase):
    def test_bracket_bridge_picks_the_anti_that_fits_the_standoff(self):
        # 信和A（アンチ 500・400・250）で、離れ 300 に大きい2種の 400 を選び「床材 400 が入りきりません」だった
        from ashiba.cli import solve_all

        r = solve_all({"outline_mm": [[0, 0], [9000, 0], [9000, 6000], [0, 6000]], "eaves_height_mm": 9000,
                       "building_height_mm": 9000, "series_id": "shinwa_A", "module": "metric"})
        b = r.model.roof_bridges[0]
        self.assertEqual(b.kind, "ブラケット")
        self.assertEqual(b.deck, [250])
        self.assertFalse([w for w in r.warnings if "入りきりません" in w[2]])


class TestTubeStandoffFollowsTheTarget(unittest.TestCase):
    def test_tube_face_keeps_300_by_trimming_a_non_standard_span(self):
        # 単管は建地の間隔が自由なのに、規格スパンの和だけで解いて「離れ350mm > 300mm（スパン構成では動かせません）」だった
        from ashiba.cli import solve_all

        r = solve_all({"outline_mm": [[0, 0], [6300, 0], [6300, 5000], [0, 5000]], "eaves_height_mm": 9000,
                       "building_height_mm": 9000, "series_id": "tankan", "module": "metric"})
        self.assertTrue(all(d <= 300 + 1e-6 for d in r.model.plan.standoffs), r.model.plan.standoffs)
        self.assertFalse([w for w in r.warnings if "離れ350" in w[2]])
        # 縮めるのは 1800 でないスパン（規格の 1800 は斜材・シートの升目のまま）
        east = r.model.plan.edges[1].spans
        self.assertEqual(east.count(1800), 2, east)


class TestTubeBoardsLongLap(unittest.TestCase):
    def test_boards_that_cannot_lap_300_on_a_bracket_lap_longer(self):
        # スパン 1800・1800・1500・600 は規定の長さの板の 300 重ねがブラケットに乗らず「足場板を割り付けられません」で止まった
        from ashiba.tube_runs import BOARD_BEAR_MM, face_boards, post_positions

        spans = [1800, 1800, 1500, 600]
        a, _b = face_boards(spans)
        posts = post_positions(spans)
        sp = a.spans_mm()
        for (s0, e0), (s1, _e1) in zip(sp, sp[1:]):
            self.assertGreaterEqual(e0 - s1, 300)
            self.assertTrue(any(p - s1 >= BOARD_BEAR_MM and e0 - p >= BOARD_BEAR_MM for p in posts[1:-1]))
        self.assertTrue(posts[-1] + 100 <= sp[-1][1] <= posts[-1] + 300)
        # GDL へは 300 以外の重ねを負の数で渡す
        self.assertTrue(any(v < 0 for v in a.items()))

    def test_ordinary_faces_keep_the_300_lap(self):
        from ashiba.tube_runs import face_boards

        a, _b = face_boards([1800] * 5)
        self.assertIsNone(a.laps)
        self.assertTrue(all(v > 0 for v in a.items()))


class TestTubeRunOddLength(unittest.TestCase):
    def test_odd_tube_face_still_gets_runs(self):
        # 隣の組に合わせた半端なスパン（1669）の単管抱き足場で「単管の通しを割り付けられません（9069mm）」と止まった
        from ashiba.tube_runs import plan_run

        run = plan_run([1800, 1800, 1800, 1800, 1669])
        self.assertGreaterEqual(sum(run.pieces), 8869 + 200)


class TestConvergedStandoffs(unittest.TestCase):
    def test_groups_agree_on_every_corner(self):
        g = solve_groups(USER)
        own = {e.edge_index: e.standoff for _l, r in g if "上段" not in _l for e in r.model.plan.edges}
        for lb, r in g:
            if "上段" in lb:
                continue
            for e in r.model.plan.edges:
                for adj in ((e.edge_index - 1) % 4, (e.edge_index + 1) % 4):
                    self.assertAlmostEqual(r.model.plan.standoffs[adj], own[adj], delta=0.5, msg=(lb, adj))


class TestCornersAgreeAcrossGroups(unittest.TestCase):
    """面の組をまたぐ隅で、どの組も隣の面の離れを同じ値で見る（建地の位置が組ごとにずれない）.
    メートルの一側足場の東面で本体が 300 と見込み 50 ずれた、インチで 27.5 ずれた（2026-10-26 のループ）."""

    def test_every_group_sees_the_same_standoff(self):
        R = [[0, 0], [12000, 0], [12000, 8000], [0, 8000]]
        for mod in ("inch", "metric"):
            for ff in ("東面=一側足場", "北面=一側足場;西面=一側足場", "東面=単管抱き足場;北面=一側足場;西面=一側足場"):
                with self.subTest(mod=mod, ff=ff):
                    g = solve_groups({"outline_mm": R, "eaves_height_mm": 9000, "module": mod, "face_forms": ff})
                    own = {e.edge_index: (lb, e.standoff) for lb, r in g for e in r.model.plan.edges}
                    for lb, r in g:
                        so = r.model.plan.standoffs
                        self.assertTrue(all(240 <= x <= 360 for x in so), (lb, so))
                        for e in r.model.plan.edges:
                            for adj in ((e.edge_index - 1) % 4, (e.edge_index + 1) % 4):
                                if adj in own and own[adj][0] != lb:
                                    self.assertAlmostEqual(so[adj], own[adj][1], delta=1.0, msg=(lb, adj))


    def test_hug_follows_an_l_shape_metric_main(self):
        # L 字のメートルは本体の離れが 400 になる面がある。単管抱き足場は 350 で止めず本体の線にそろえる（50 ずれた）
        L = [[0, 0], [16000, 0], [16000, 6000], [8000, 6000], [8000, 12000], [0, 12000]]
        g = solve_groups({"outline_mm": L, "eaves_height_mm": 9000, "module": "metric",
                          "face_forms": "東面(辺1)=単管抱き足場;西面=単管抱き足場"})
        main = next(r.model for lb, r in g if lb == "")
        hug = next(r.model for lb, r in g if "抱き" in lb)
        for e in hug.plan.edges:
            self.assertAlmostEqual(e.standoff, main.plan.standoffs[e.edge_index], delta=0.5)


class TestOneSidedCornerGaps(unittest.TestCase):
    def test_inch_one_sided_l_shape_keeps_the_standoff(self):
        # インチの一側足場は隅を閉じようとして離れが 403〜435 になった。隅に隙間（コーナーステップ）を残して 350 以下に
        L = [[0, 0], [16000, 0], [16000, 6000], [8000, 6000], [8000, 12000], [0, 12000]]
        r = solve_all({"outline_mm": L, "eaves_height_mm": 9000, "module": "inch", "scaffold_form": "一側足場"})
        self.assertTrue(all(250 <= x <= 350 for x in r.model.plan.standoffs), r.model.plan.standoffs)
        self.assertTrue(r.model.plan.corner_steps)
        # 出隅の升目（350 角）は日建に 350 の布材・幅木が無い。汎用の「該当部材がありません」ではなく単管とクランプで手配
        ws = r.quantity.warnings
        self.assertFalse(any("該当部材がありません" in w and "350" in w for w in ws), ws)
        self.assertTrue(any("単管（1.0m）" in w and "直交クランプ" in w for w in ws))


class TestBracketEndRails(unittest.TestCase):
    def test_frame_bracket_end_rails_use_the_610_ledger(self):
        # 枠組の張出し 600 の妻側の手すり・中桟・幅木は系列の 610（ちょうど 600 が無く「該当部材がありません」だった）
        from pathlib import Path

        from ashiba.cli import load_spec

        r = solve_all(load_spec(Path(__file__).resolve().parents[1] / "examples" / "waku_composite.json"))
        self.assertFalse([w for w in r.quantity.warnings if "該当部材がありません" in w and "張出し妻側" in w])


class TestPostsByLevel(unittest.TestCase):
    def test_every_post_lands_in_its_level(self):
        # 層ごとの数量で、支柱を全部の脚が同じ積み方として割り振り、差を「1層目に入れています」としていた
        # （敷地の高低差・開口部の梁枠上・荷受けステージの先端の支柱・屋上の渡りの支柱）
        from pathlib import Path

        from ashiba.cli import load_spec
        from ashiba.level_quantity import take_off_by_level

        root = Path(__file__).resolve().parents[1] / "examples"
        for name in ("sloped_site", "combo_nd1800", "opening_beam", "loading_stage", "nikken_nd1900_rect"):
            with self.subTest(name):
                r = solve_all(load_spec(root / f"{name}.json"))
                lt = take_off_by_level(r.model, r.quantity, bracket_sections=r.brackets, stair_plan=r.stair_plan,
                                       platforms=r.platforms, openings=r.openings, terrain=r.terrain)
                self.assertFalse([n for n in lt.notes if "1層目に入れています" in n], lt.notes)


class TestFaceTakeoffAddsUp(unittest.TestCase):
    def test_faces_sum_to_the_whole(self):
        # 面ごとの数量の合計が全体と合う（開口部の抜いた支柱を全部の面で引いてジャッキが 18 本少なかった、面の終点の
        # 脚がずれて継ぎ足し部の根がらみが抜けていた）
        from pathlib import Path

        from ashiba.cli import load_spec
        from ashiba.level_quantity import take_off_by_face

        root = Path(__file__).resolve().parents[1] / "examples"
        for name in ("opening_beam", "sloped_site", "combo_nd1800", "waku_composite"):
            with self.subTest(name):
                r = solve_all(load_spec(root / f"{name}.json"))
                ft = take_off_by_face(r.model, r.quantity, bracket_sections=r.brackets, stair_plan=r.stair_plan,
                                      platforms=r.platforms, openings=r.openings, terrain=r.terrain)
                bad = [(p.model_no, sum(v), ft.totals.get((p.model_no, p.category), 0)) for p, v in ft.rows
                       if sum(v) != ft.totals.get((p.model_no, p.category), 0)]
                self.assertEqual(bad, [])


class TestRoofBridgeFromScaffoldMembers(unittest.TestCase):
    """屋上への渡りは足場の部材で組む（利用者の指定 2026-10-26: 布材かブラケット出して支柱で足元つくかブラケットで
    浮かせる、アンチ引いて手すりも布材、枠の場合は単管と足場板、パラペットは避ける）."""

    B = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]

    def _bridge(self, **kw):
        r = solve_all({"outline_mm": self.B, "eaves_height_mm": 9000, "module": "inch", **kw})
        (b,) = r.model.roof_bridges
        return r, b

    def _delta(self, r, **kw):
        r0 = solve_all({"outline_mm": self.B, "eaves_height_mm": 9000, "module": "inch", "roof_bridge": False, **kw})
        q0 = {ln.part.model_no: ln.qty for ln in r0.quantity.lines}
        return {ln.part.model_no: ln.qty - q0.get(ln.part.model_no, 0) for ln in r.quantity.lines
                if ln.qty != q0.get(ln.part.model_no, 0)}

    def test_flush_with_the_roof_closes_the_gap_with_brackets(self):
        r, b = self._bridge()
        self.assertEqual(b.kind, "ブラケット")
        self.assertEqual(b.z_deck_mm, b.z_from_mm)                          # 足場の床のまま
        self.assertLessEqual(b.length_mm, b.standoff_mm + 10)                # 躯体の外面まで（屋上スラブに食い込まない）
        self.assertEqual(b.width_mm, 1829)                                   # 掛けるスパンの幅
        d = self._delta(r)
        self.assertEqual(d.get("NDBK03H"), 2)                               # 拡幅ブラケット 305 を両脇に
        self.assertEqual(d.get("NDN624"), 1)                                 # アンチ 240×1829

    def test_deck_above_the_roof_stands_posts_on_the_roof(self):
        r, b = self._bridge(eaves_height_mm=8700)
        self.assertEqual(b.kind, "支柱")
        self.assertGreater(b.z_deck_mm, b.z_to_mm)
        self.assertGreaterEqual(b.length_mm, b.standoff_mm + 150)           # 屋上の支柱は躯体の外面から内側
        koma = r.model.master.koma_pitch
        # 床・中桟・手すりが屋上の支柱のコマに来る（支柱の天端 − 上端の下がり − 2コマ ＝ 床）
        top = b.z_to_mm + b.jack_mm + b.post_mm - r.model.master.koma_top_gap
        self.assertEqual((top - b.z_deck_mm) % koma, 0)
        d = self._delta(r, eaves_height_mm=8700)
        self.assertEqual(d.get(r.model.master.find("支柱", int(b.post_mm)).model_no), 2)
        self.assertGreaterEqual(d.get("NDT06", 0), 6)                         # 布材の腕木・中桟・手すり
        self.assertEqual(b.steps(b.drop_mm), 2)                               # 屋上へ踏段

    def test_parapet_is_cleared(self):
        _r, b = self._bridge(roof_parapet_mm=300)
        self.assertEqual(b.kind, "支柱")
        self.assertGreaterEqual(b.z_deck_mm, b.z_to_mm + 300 + 50)           # パラペットの天端の 50 上より上
        self.assertGreaterEqual(b.length_mm, b.standoff_mm + b.parapet_t_mm + 150)

    def test_frame_scaffold_uses_tubes_and_planks(self):
        r, b = self._bridge(series_id="waku")
        self.assertTrue(b.tube)
        self.assertIn(b.kind, ("単管支柱", "単管跳ね出し"))
        d = self._delta(r, series_id="waku")
        self.assertTrue(any(k.startswith("足場板") for k in d), d)
        self.assertGreater(d.get("ARC1", 0), 0)
        self.assertTrue(any(k.startswith("単管") for k in d), d)

    def test_inner_posts_are_extended_for_the_rails(self):
        # 渡りの手すりが足場の内側の支柱の天端より上になるとき、掛けるスパンの内側の支柱2本を継ぎ足す（案内だけだった）
        r, b = self._bridge(roof_parapet_mm=300)
        koma = r.model.master.koma_pitch
        self.assertGreater(b.ext_mm, 0)
        self.assertEqual(b.ext_mm % koma, 0)                                # コマの並びを崩さない
        self.assertGreaterEqual(b.post_top_mm + b.ext_mm, b.z_deck_mm + 900)
        d = self._delta(r, roof_parapet_mm=300)
        ext = r.model.master.find("支柱", int(b.ext_mm)).model_no
        self.assertGreaterEqual(d.get(ext, 0), 2)

    def test_anti_fill_the_depth(self):
        # 横引きのアンチが奥行きにすき間なく並ぶ長さを選ぶ（914 に 500＋240 だと 134 残った）
        from ashiba.roof_bridges import deck_gap_mm

        _r, b = self._bridge(roof_parapet_mm=300)
        self.assertLessEqual(deck_gap_mm(b.length_mm, b.deck), 90)

    def test_anti_widths_come_from_the_series(self):
        # 信和 A はアンチ 240 が無い（500・400）。渡りの床も系列にある幅で（凹み形状の見本で「該当部材がありません」）
        for sid in ("shinwa_A", "shinwa_B", "nikken_nd1800"):
            with self.subTest(sid):
                r = solve_all({"outline_mm": self.B, "eaves_height_mm": 9000, "series_id": sid, "roof_parapet_mm": 300})
                self.assertFalse([w for w in r.quantity.warnings if "該当部材がありません" in w and "渡り" in w])

    def test_part_gets_the_members(self):
        from ashiba.attachments import bridge_placements

        r, b = self._bridge(eaves_height_mm=8700)
        (p,) = bridge_placements(r.model)
        self.assertEqual(p.params["brKind"], 0)
        self.assertEqual(p.params["deckList"], ",".join(str(w) for w in b.deck))
        self.assertAlmostEqual(p.params["postL"] * 1000, b.post_mm)


class TestAttachmentsGoToTheirGroup(unittest.TestCase):
    def test_hoist_only_in_the_group_with_its_face(self):
        # 昇降機（辺0＝南面）は南面を建てる組にだけ渡す（ほかの組で「辺0は存在しません」と止まった。2026-10-26 実機）
        g = solve_groups({"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
                          "module": "inch", "face_forms": "東面=単管抱き足場;北面=一側足場;西面=一側足場",
                          "hoists": [{"edge_index": 0, "position_mm": 6000}]})
        with_hoist = [lb for lb, r in g if r.platforms.hoists]
        self.assertEqual(with_hoist, [""])


if __name__ == "__main__":
    unittest.main()
