"""足場の箱（超簡易モード。利用者の指定 2026-10-30: 箱を作って自分で伸び縮み・一周の箱・ボタンで本体にする）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.box import (box_coins, box_loop, box_params, box_sides, chain_frame, chain_sides, contains, orient_path,
                        parse_box_params, rotate_pt, to_local, band, corner_fill, corner_quantities, joined_ends,
                        oblique_corners, trim_for_corner, corner_layout,
                        default_one, parse_side_params, plan_side_chain, side_axis, side_params, sides_from_path, snap_spans,
                        snap_within, solve_side_job,
                        thickness_conditions)
from ashiba.manual import solve_manual_loop

INCH = [1829, 1524, 1219, 914, 610]


class TestSnap(unittest.TestCase):
    def test_snaps_to_standard_lengths(self):
        """つまみで引いた長さ → 定尺の最大を並べて端数を定尺で埋める（部品のパラメータスクリプトと同じ決め方）."""
        self.assertEqual(snap_spans(7316, INCH), [1829] * 4)
        self.assertEqual(snap_spans(8000, INCH), [1829] * 4 + [610])      # 7926（8000 に一番近い）
        self.assertEqual(snap_spans(8230, INCH), [1829] * 4 + [914])
        self.assertEqual(snap_spans(300, INCH), [610])                     # 短すぎても1本は残る
        self.assertEqual(snap_spans(9000, [1800, 1500, 1200, 900, 600]), [1800] * 5)
        self.assertEqual(snap_spans(9100, INCH), [1829] * 5)                # 9144（6本）より 1mm 遠い 9145（5本）

    def test_no_adjusting_457(self):
        """アルバトロスの 457 は端数の調整用（先行手摺・シートが合わない）。箱の吸着には使わない（利用者が引いて 1524＋457 になった）."""
        from ashiba.master import load_master

        coins = box_coins(load_master("albatross").span_lengths())
        self.assertNotIn(457, coins)
        self.assertNotIn(457, snap_spans(11126, coins))


class TestBoxLoop(unittest.TestCase):
    def test_rotations(self):
        pts, sides = box_loop((1000.0, 2000.0), 0.0, [1829, 1829], [914])
        self.assertEqual(pts, [(1000.0, 2000.0), (4658.0, 2000.0), (4658.0, 2914.0), (1000.0, 2914.0)])
        self.assertEqual(sides, [[1829, 1829], [914], [1829, 1829], [914]])
        pts, _ = box_loop((0.0, 0.0), math.pi / 2, [1829], [914])
        self.assertEqual([tuple(round(v) for v in p) for p in pts], [(0, 0), (0, 1829), (-914, 1829), (-914, 0)])
        with self.assertRaisesRegex(ValueError, "斜め"):
            box_loop((0.0, 0.0), math.radians(30), [1829], [914])

    def test_params_round_trip_and_solve(self):
        p = box_params([1829] * 4, [1829] * 3, INCH, 900.0, 4, 1780.0, 1800.0, "albatross", 300.0)
        self.assertEqual((p["spanX"], p["lenX"], p["topEdit"], p["thick"]), ("1829,1829,1829,1829", 7.316, 7.18, 0.9))
        b = parse_box_params({**p, "nLev": 4})
        self.assertEqual((b["sx"], b["sy"], b["levels"], b["thick_mm"]), ([1829] * 4, [1829] * 3, 4, 900))
        pts, sides = box_loop((0.0, 0.0), 0.0, b["sx"], b["sy"])
        _w, _spec, r = solve_manual_loop(pts, sides, b["standoff"], 7000.0, {"series_id": "albatross"})
        self.assertTrue(r.verdict["ok"], r.verdict)
        self.assertEqual([list(e.spans) for e in r.model.plan.edges],
                         [[1829] * 4, [1829] * 3, [1829] * 4, [1829] * 3])

    def test_setback_box_stands_on_the_roof(self):
        """セットバック（利用者の指定 2026-10-30: 高さも変えてセットバックにも対応）: 上の階の箱は立つ高さ zBase から建つ."""
        p = box_params([1829] * 4, [1829] * 2, INCH, 600.0, 3, 1780.0, 1800.0, "albatross", 300.0, base_mm=5400.0)
        b = parse_box_params({**p, "nLev": 3})
        self.assertEqual((p["zBase"], b["base_mm"]), (5.4, 5400.0))
        pts, sides = box_loop((0.0, 0.0), 0.0, b["sx"], b["sy"])
        _w, _spec, r = solve_manual_loop(pts, sides, 300.0, 5200.0,
                                         {"series_id": "albatross", "base_height_mm": b["base_mm"], "scaffold_width_mm": 600})
        self.assertTrue(r.verdict["ok"], r.verdict)
        self.assertEqual(r.model.base_height_mm, 5400.0)

    def test_setback_joins_the_main_scaffold(self):
        """下の足場と上段をつなげる（利用者の指定 2026-10-30）: 南面だけ下がる上の階の箱 → 本体の東・北・西面は上まで、南面は
        途中の屋根で止め、上段の南面の端を本体の支柱に乗せる."""
        from ashiba.box import setback_spec
        from ashiba.cli import solve_groups

        lp, ls = box_loop((0.0, 0.0), 0.0, [1829] * 8, [1829] * 5)
        up, us = box_loop((0.0, 3658.0), 0.0, [1829] * 8, [1829] * 3)
        low = {"pts": lp, "sides": ls, "standoff": 300.0, "base_mm": 0.0, "levels": 3, "floor_mm": 1800.0}
        upper = {"pts": up, "sides": us, "standoff": 300.0, "base_mm": 5400.0, "levels": 3, "floor_mm": 1800.0}
        self.assertTrue(contains(lp, up))
        groups = dict(solve_groups(setback_spec(low, [upper], {"series_id": "albatross"})))
        self.assertEqual(set(groups), {"", "下段", "上段"})
        self.assertTrue(all(g.verdict["ok"] for g in groups.values()), {k: g.verdict for k, g in groups.items()})
        main, tier = groups[""].model, groups["上段"].model
        self.assertEqual(tier.base_height_mm, 5400.0)
        names = dict(zip([e.edge_index for e in main.plan.edges], main.plan.face_names()))
        tops = {names[e.edge_index]: main.elevation_of(e.edge_index).total_height for e in main.plan.edges}
        self.assertLess(tops["南面"], tops["北面"])                       # 南面は途中の屋根で止まる
        self.assertTrue(any("本体の足場に繋ぎます" in str(w) for w in groups[""].warnings))
        self.assertTrue(groups[""].model.roof_bridges)                    # 本体から途中の屋根へ渡る

    def test_inset_tier_reached_by_a_roof_bridge(self):
        """上の箱が下の箱の内側に収まる（面がそろわない）ときも、本体から途中の屋根へ渡って上段へ行ける."""
        from ashiba.box import setback_spec
        from ashiba.cli import solve_groups

        lp, ls = box_loop((0.0, 0.0), 0.0, [1829] * 8, [1829] * 5)
        up, us = box_loop((3658.0, 3658.0), 0.0, [1829] * 4, [1829] * 2)
        low = {"pts": lp, "sides": ls, "standoff": 300.0, "base_mm": 0.0, "levels": 3, "floor_mm": 1800.0}
        upper = {"pts": up, "sides": us, "standoff": 300.0, "base_mm": 5400.0, "levels": 3, "floor_mm": 1800.0}
        groups = dict(solve_groups(setback_spec(low, [upper], {"series_id": "albatross"})))
        self.assertTrue(all(g.verdict["ok"] for g in groups.values()))
        self.assertTrue(any(b.z_to_mm == 5400.0 for b in groups[""].model.roof_bridges))

    def test_thickness_picks_the_scaffold(self):
        """厚みで足場の種類も変える（利用者の指定 2026-10-30）: 300＝一側足場、600／900／1200＝幅 610／914／1219 の本足場."""
        pts, sides = box_loop((0.0, 0.0), 0.0, [1829] * 4, [1829] * 3)
        got = {}
        for t in (280, 600, 950, 1200):
            kind, cond = thickness_conditions(t, 300.0)
            _w, _spec, r = solve_manual_loop(pts, sides, 300.0, 6000.0, {"series_id": "albatross", **cond})
            self.assertTrue(r.verdict["ok"], (kind, r.verdict))
            got[kind] = (r.model.config.scaffold_form, round(r.model.post_row_spacing_mm))
        self.assertEqual(got["本足場 幅600"], ("本足場", 610))
        self.assertEqual(got["本足場 幅900"], ("本足場", 914))
        self.assertEqual(got["本足場 幅1200"], ("本足場", 1219))
        self.assertEqual(got["ブラケット足場（支柱）"][0], "一側足場")


def _sides(over=None):
    """7316×5487 の箱の4辺（左回り: 南・東・北・西）。over={番号: {属性}} で辺ごとに変える."""
    out = []
    for k, (a, ang, sp) in enumerate(box_sides((0.0, 0.0), 0.0, [1829] * 4, [1829] * 3)):
        s = {"a": a, "dir": side_axis(ang), "spans": sp, "base_mm": 0.0, "series_id": "albatross", "thick_mm": 900,
             "levels": 4, "standoff": 300.0, "floor_mm": 1800.0, "one_kind": 1}
        s.update((over or {}).get(k, {}))
        out.append(s)
    return out


def _extra(job):
    return {"series_id": "albatross", **thickness_conditions(job["main_t"], 300.0, job["main"].get("one_kind", 1))[1]}


class TestSides(unittest.TestCase):
    """足場の辺（利用者の指定 2026-10-31: 箱は1辺ずつ別々にしてちょ）."""

    def test_box_is_four_sides_counterclockwise(self):
        sd = box_sides((1000.0, 2000.0), math.pi / 2, [1829, 1829], [914])
        self.assertEqual([tuple(round(v) for v in a) for a, _g, _s in sd], [(1000, 2000), (1000, 5658), (86, 5658), (86, 2000)])
        self.assertEqual([round(math.degrees(g)) % 360 for _a, g, _s in sd], [90, 180, 270, 0])
        p = side_params([1829, 914], INCH, 300.0, 3, 1780.0, 1800.0, "albatross", 300.0, base_mm=5400.0)
        s = parse_side_params({**p, "nLev": 3})
        self.assertEqual((s["spans"], s["thick_mm"], s["levels"], s["base_mm"], p["lenX"]), ([1829, 914], 300, 3, 5400.0, 2.743))

    def test_chains_closed_open_and_single(self):
        sd = _sides()
        self.assertEqual(chain_sides(sd), [([0, 1, 2, 3], True)])
        self.assertEqual(chain_sides([sd[k] for k in (1, 2, 3)]), [([0, 1, 2], False)])     # 南を消すとコの字
        self.assertEqual(chain_sides([sd[0], sd[2]]), [([0], False), ([1], False)])         # 向かい合う2辺は別々
        # 置き直しのずれ（1m 以内）はつながる。立つ高さの違う辺はつながらない
        moved = _sides({1: {"a": (7316.0 + 400.0, 0.0)}})
        self.assertEqual(chain_sides(moved), [([0, 1, 2, 3], True)])
        self.assertEqual(len(chain_sides(_sides({1: {"base_mm": 5400.0}}))), 2)

    def test_shapes(self):
        sd = _sides()
        job = plan_side_chain(sd, [0, 1, 2, 3], True)
        self.assertEqual((job["kind"], job["pts"][2]), ("loop", (7316.0, 5487.0)))
        three = [sd[k] for k in (1, 2, 3)]
        self.assertEqual(plan_side_chain(three, [0, 1, 2], False)["kind"], "open")
        self.assertEqual(plan_side_chain([sd[0]], [0], False)["kind"], "line")
        # まっすぐ続く2本の辺は1つの面
        half = [dict(sd[0], spans=[1829, 1829]), dict(sd[0], a=(3658.0, 0.0), spans=[1829, 1829])] + sd[1:]
        (ch, closed), = chain_sides(half)
        job = plan_side_chain(half, ch, closed)
        self.assertEqual((len(job["group_sides"]), job["sides"][0]), (4, [1829] * 4))

    def test_thickness_and_levels_per_side(self):
        """東の辺を厚み 300（一側足場の狭い所）、北の辺を 6段にすると、面ごとの種類・高さで解いて両方とも成り立つ."""
        sd = _sides({1: {"thick_mm": 300}, 2: {"levels": 6}})
        job = plan_side_chain(sd, [0, 1, 2, 3], True)
        _w, spec, groups = solve_side_job(job, sd, _extra(job))
        self.assertEqual(spec["face_forms"], {"東面": "一側足場（狭い所）"})
        self.assertEqual(spec["face_eaves_mm"], {0: 7000.0, 1: 7000.0, 2: 10600.0, 3: 7000.0})
        self.assertEqual([(lb, sorted(g.model.faces_only)) for lb, g in groups], [("", [0, 2, 3]), ("一側足場（狭い所）", [1])])
        self.assertTrue(all(g.verdict["ok"] for _lb, g in groups), [g.verdict for _lb, g in groups])
        main = groups[0][1].model
        tops = {main.face_name(ei): (main.face_elevations.get(ei) or main.elevation).n_levels for ei in sorted(main.faces_only)}
        self.assertEqual(tops, {"南面": 4, "北面": 6, "西面": 4})
        self.assertEqual(groups[1][1].model.elevation.n_levels, 4)                   # 東面（一側足場）は 4段

    def test_open_and_single_solve(self):
        sd = _sides()
        for keep, faces in (((1, 2, 3), [["東面", "北面", "西面"]]), ((0, 1), [["南面", "東面"]]), ((0,), [["南面"]])):
            with self.subTest(keep=keep):
                ss = [sd[k] for k in keep]
                (ch, closed), = chain_sides(ss)
                job = plan_side_chain(ss, ch, closed)
                _w, _spec, groups = solve_side_job(job, ss, _extra(job))
                r = groups[0][1]
                self.assertTrue(r.verdict["ok"], r.verdict)
                got = [r.model.face_name(i) for i in sorted(r.model.faces_only)] if r.model.faces_only is not None \
                    else r.model.plan.face_names()
                self.assertEqual([got], faces)

    def test_too_many_open_sides(self):
        """西の辺を短くして一周が閉じないと、南から西まで4面の開いた組になる → 一周に閉じるよう知らせる."""
        sd = _sides({3: {"spans": [1829]}})
        (ch, closed), = chain_sides(sd)
        self.assertEqual((ch, closed), ([0, 1, 2, 3], False))
        with self.assertRaisesRegex(ValueError, "一周に閉じて"):
            plan_side_chain(sd, ch, closed)



class TestSidesFromLines(unittest.TestCase):
    """線の範囲だけに辺を置く（利用者の指定 2026-10-31: 線引っ張った範囲だけに配置するようにして 今一線だけで四角につくられてしまう）."""

    def test_length_stays_within_the_line(self):
        self.assertEqual(snap_within(7316, INCH), [1829] * 4)
        self.assertEqual(snap_within(5000, INCH), [1829, 1829, 1219])       # 4877（5000 を超えない）
        self.assertLessEqual(sum(snap_within(9100, INCH)), 9100)
        self.assertEqual(snap_within(400, INCH), [610])                      # 定尺より短い線は1本

    def test_one_line_is_one_side(self):
        segs, how = orient_path([((0.0, 0.0), (5000.0, 0.0))])
        self.assertIn("線の右", how)
        sides = sides_from_path(segs, INCH)
        self.assertEqual(len(sides), 1)
        self.assertEqual((sides[0][0], sides[0][2], sides[0][3]), ((0.0, 0.0), [1829, 1829, 1219], False))
        # 建物（スラブ）が線の右にあれば、逆向きにして足場を建物の反対側に出す
        north = [(0.0, 1000.0), (5000.0, 1000.0), (5000.0, 9000.0), (0.0, 9000.0)]
        south = [(x, -y) for x, y in north]
        self.assertEqual(orient_path([((0.0, 0.0), (5000.0, 0.0))], north)[0], [((0.0, 0.0), (5000.0, 0.0))])
        self.assertEqual(orient_path([((0.0, 0.0), (5000.0, 0.0))], south)[0], [((5000.0, 0.0), (0.0, 0.0))])

    def test_closed_polyline_goes_outside(self):
        """右回りに描いた四角も左回りにそろえて外回りに出す。出隅は各辺が終わりの角を描く."""
        cw = [((0.0, 0.0), (0.0, 5487.0)), ((0.0, 5487.0), (7316.0, 5487.0)), ((7316.0, 5487.0), (7316.0, 0.0)),
              ((7316.0, 0.0), (0.0, 0.0))]
        segs, how = orient_path(cw)
        self.assertEqual(how, "閉じた線の外回り")
        sides = sides_from_path(segs, INCH)
        self.assertEqual([(tuple(a), round(math.degrees(g)) % 360, sum(sp), ce) for a, g, sp, ce in sides],
                         [((0.0, 0.0), 0, 7316, True), ((7316.0, 0.0), 90, 5487, True), ((7316.0, 5487.0), 180, 7316, True),
                          ((0.0, 5487.0), 270, 5487, True)])
        sd = [{"a": a, "dir": side_axis(g), "spans": sp, "base_mm": 0.0, "series_id": ""} for a, g, sp, _ce in sides]
        self.assertEqual(chain_sides(sd), [([0, 1, 2, 3], True)])

    def test_l_shape_inner_corner(self):
        """L字の線（右に曲がる入隅）は終わりの出隅を描かない。最後の辺も描かない."""
        segs, _ = orient_path([((0.0, 0.0), (5487.0, 0.0)), ((5487.0, 0.0), (5487.0, -3658.0))])
        self.assertEqual([ce for *_x, ce in sides_from_path(segs, INCH)], [False, False])
        segs, _ = orient_path([((0.0, 0.0), (5487.0, 0.0)), ((5487.0, 0.0), (5487.0, 3658.0))])
        self.assertEqual([ce for *_x, ce in sides_from_path(segs, INCH)], [True, False])



class TestOneRowKinds(unittest.TestCase):
    """一側の組み方（利用者の指定 2026-10-31: ブラケット足場と単管抱き足場はある？→ 選べるようにして）."""

    def test_kind_to_conditions(self):
        self.assertEqual(thickness_conditions(300, 300.0, 1), ("ブラケット足場（支柱）",
                                                                {"scaffold_form": "一側足場", "one_row_by_choice": True}))
        self.assertEqual(thickness_conditions(300, 300.0, 2)[1]["bracket_post"], "単管")
        self.assertEqual(thickness_conditions(300, 300.0, 3)[0], "単管抱き足場")
        self.assertEqual(thickness_conditions(900, 300.0, 3)[0], "本足場 幅900")          # 本足場の厚みでは使わない
        self.assertEqual(default_one({"scaffold_form": "単管抱き足場"}), (300, 3))
        self.assertEqual(default_one({"scaffold_form": "ブラケット足場", "bracket_post": "単管"}), (300, 2))
        self.assertEqual(default_one({"scaffold_form": "本足場"}), (None, 1))
        p = side_params([1829], INCH, 300.0, 4, 1780.0, 1800.0, "albatross", 300.0, one_kind=3)
        self.assertEqual((p["oneKind"], parse_side_params(p)["one_kind"]), (3, 3))

    def test_tube_hug_loop_uses_tube_spans(self):
        """全部の辺が単管抱き足場なら単管の系列で、スパンを単管の定尺に直して解く（1829 は単管に無い）."""
        sd = _sides({k: {"thick_mm": 300, "one_kind": 3} for k in range(4)})
        job = plan_side_chain(sd, [0, 1, 2, 3], True)
        _w, _spec, groups = solve_side_job(job, sd, _extra(job))
        r = groups[0][1]
        self.assertTrue(r.verdict["ok"], r.verdict)
        self.assertEqual(r.model.config.form_label, "単管抱き足場")
        self.assertEqual([list(e.spans) for e in r.model.plan.edges][:2], [[1800] * 4, [1800] * 3])
        self.assertTrue(any("単管の定尺" in n for n in job["notes"]))
        law = next(c for c in r.checks if c.check_id == 1)
        self.assertEqual(law.status, "WARN")                                    # ただし書き（理由を記録）

    def test_mixed_kinds_switch_faces(self):
        """本足場の一周の東を単管のブラケット足場、北を単管抱き足場にすると、面ごとの切替で解いて全部成り立つ."""
        sd = _sides({1: {"thick_mm": 300, "one_kind": 2}, 2: {"thick_mm": 300, "one_kind": 3}})
        job = plan_side_chain(sd, [0, 1, 2, 3], True)
        _w, spec, groups = solve_side_job(job, sd, _extra(job))
        self.assertEqual(spec["face_forms"], {"東面": "ブラケット足場（単管・狭い所）", "北面": "単管抱き足場（狭い所）"})
        self.assertEqual({lb: g.model.config.form_label for lb, g in groups},
                         {"": "本足場", "ブラケット足場（単管・狭い所）": "ブラケット足場（単管）", "単管抱き足場（狭い所）": "単管抱き足場"})
        self.assertTrue(all(g.verdict["ok"] for _lb, g in groups), [g.verdict for _lb, g in groups])



class TestObliqueSides(unittest.TestCase):
    """斜めの線（利用者の指定 2026-10-31: 斜めの線にも対応できるようにしてちょ）: 組の向きにそろえた座標で縦・横に解く."""

    def _rotated_box(self, deg):
        ang = math.radians(deg)
        out = []
        for a, g, sp, _ce in sides_from_path(orient_path(
                [(rotate_pt(p, ang, (0.0, 0.0)), rotate_pt(q, ang, (0.0, 0.0))) for p, q in
                 (((0.0, 0.0), (7316.0, 0.0)), ((7316.0, 0.0), (7316.0, 5487.0)), ((7316.0, 5487.0), (0.0, 5487.0)),
                  ((0.0, 5487.0), (0.0, 0.0)))])[0], INCH):
            out.append({"a": a, "dir": side_axis(g), "spans": sp, "base_mm": 0.0, "series_id": "albatross", "thick_mm": 900,
                        "levels": 4, "standoff": 300.0, "floor_mm": 1800.0, "one_kind": 1})
        return out

    def test_oblique_line_keeps_its_direction(self):
        (a, g, sp, ce), = sides_from_path(orient_path([((0.0, 0.0), (6000.0 * math.cos(0.5), 6000.0 * math.sin(0.5)))])[0],
                                          INCH)
        self.assertAlmostEqual(g, 0.5)
        self.assertEqual(sum(sp), 5792)                                     # 6000 を超えない 1829×2＋1524＋610
        self.assertAlmostEqual(side_axis(math.radians(1.0))[1], 0.0)          # 2° までは縦・横にそろえる

    def test_rotated_box_chains_and_solves_in_its_frame(self):
        sd = self._rotated_box(30.0)
        (ch, closed), = chain_sides(sd)
        self.assertTrue(closed)
        ang = chain_frame(sd, ch)
        self.assertAlmostEqual(math.degrees(ang), 30.0)
        loc = to_local(sd, ch, ang, sd[ch[0]]["a"])
        self.assertEqual([s["dir"] for s in loc], [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)])
        job = plan_side_chain(loc, list(range(4)), True)
        _w, _spec, groups = solve_side_job(job, loc, _extra(job))
        self.assertTrue(groups[0][1].verdict["ok"], groups[0][1].verdict)
        self.assertEqual([sum(e.spans) for e in groups[0][1].model.plan.edges], [7316, 5487, 7316, 5487])

    def test_oblique_corner_is_not_joined(self):
        """直角でない角（120°）の2辺はつながず、それぞれ1本で解く."""
        p0, p1 = (0.0, 0.0), (5487.0, 0.0)
        p2 = (p1[0] + 3658.0 * math.cos(math.radians(60)), p1[1] + 3658.0 * math.sin(math.radians(60)))
        sd = [{"a": a, "dir": side_axis(g), "spans": sp, "base_mm": 0.0, "series_id": ""}
              for a, g, sp, _ce in sides_from_path([(p0, p1), (p1, p2)], INCH)]
        self.assertEqual(chain_sides(sd), [([0], False), ([1], False)])



def _poly_area(poly):
    n = len(poly)
    return sum(poly[k][0] * poly[(k + 1) % n][1] - poly[(k + 1) % n][0] * poly[k][1] for k in range(n)) / 2.0


def _inside(pt, poly):
    """点が凸多角形（左回り）の内側（辺から 1mm 以上）か."""
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (x2 - x1) * (pt[1] - y1) - (y2 - y1) * (pt[0] - x1) < 1.0 * math.hypot(x2 - x1, y2 - y1):
            return False
    return True


def _in_poly(pt, poly):
    """点が多角形（凹でもよい）の中か（偶奇）."""
    x, y = pt
    inside = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class TestObliqueCorners(unittest.TestCase):
    """斜めの角のつなぎ（利用者の指定 2026-10-31: 斜めの角もつながるようにしてちょ 無理な場合はかど合わせてアンチをし単管手すり
    作成か足場板と単管手すりにするか）."""

    def _two(self, deg):
        out = []
        for a, g, sp, _ce in sides_from_path([((0.0, 0.0), (5500.0, 0.0)),
                                              ((5500.0, 0.0), (5500.0 + 4000.0 * math.cos(math.radians(deg)),
                                                               4000.0 * math.sin(math.radians(deg))))], INCH):
            out.append({"a": a, "dir": side_axis(g), "spans": sp, "base_mm": 0.0, "series_id": "albatross", "thick_mm": 900,
                        "levels": 4, "standoff": 300.0, "floor_mm": 1800.0, "one_kind": 1})
        return out

    def test_convex_corner_fill(self):
        sd = self._two(60.0)
        chains = chain_sides(sd)
        self.assertEqual(chains, [([0], False), ([1], False)])                 # 直角でないのでつながない
        (cn,) = oblique_corners(sd, chains)
        self.assertEqual((cn["i"], cn["j"], cn["convex"]), (0, 1, True))
        self.assertIsNone(trim_for_corner(sd[0], sd[1], INCH))                  # 出隅は重ならない
        end0 = (float(sum(sd[0]["spans"])), 0.0)
        f = corner_fill(end0, sd[0]["dir"], 914.0, sd[1]["a"], sd[1]["dir"], 914.0, cn["c"], True)
        self.assertGreater(_poly_area(f["poly"]), 0)
        k = f["rail"][0]
        self.assertAlmostEqual(math.dist(f["poly"][k], (end0[0], -914.0)), 0.0, places=3)   # 手すりは前の足場の外の角から
        q = dict(corner_quantities(f, 4)[0:1] and [(r[0], r[1]) for r in corner_quantities(f, 4)])
        self.assertTrue(any("アンチ" in n for n in q) and any("自在クランプ" in n for n in q))
        self.assertTrue(any("足場板" in r[0] for r in corner_quantities(f, 4, "足場板")))
        rows = corner_quantities(f, 4, "アンチ", 914)
        self.assertEqual(rows[0][:2], ("アンチ 914×240", 4 * 4))                 # 奥行き 800 → 幅 240 を4枚ずつ
        self.assertTrue(any(r[0] == "自在クランプ" and r[1] == 32 for r in rows))
        # 本足場のアンチの上に重ねて載せる（利用者の指定 2026-10-31）: 出隅の三角は奥が細いので、受けの単管は外の辺の近くの
        # すき間の中だけ（150 未満は要らない）。アンチは外の辺の中点から両側へ 914/2
        lay = corner_layout(f, 914.0, 240.0)
        self.assertEqual(len(lay["planks"]), 4)
        self.assertEqual(lay["supports"], [])
        rows = corner_quantities(f, 4, "アンチ", 914, layout=lay)
        self.assertFalse(any("受け" in r[0] for r in rows))
        self.assertTrue(any(r[0] == "自在クランプ" and r[1] == 16 for r in rows))     # 手すり2本の両端×4段

    def test_concave_corner_trims_and_fills(self):
        for deg in (-30.0, -60.0, -120.0):
            with self.subTest(deg=deg):
                sd = self._two(deg)
                (cn,) = oblique_corners(sd, chain_sides(sd))
                self.assertFalse(cn["convex"])
                tr = trim_for_corner(sd[0], sd[1], INCH)
                self.assertIsNotNone(tr)
                self.assertLess(sum(tr), sum(sd[0]["spans"]))
                bi = band(sd[0]["a"], sd[0]["dir"], float(sum(tr)), 914.0)
                bj = band(sd[1]["a"], sd[1]["dir"], float(sum(sd[1]["spans"])), 914.0)
                f = corner_fill((float(sum(tr)), 0.0), sd[0]["dir"], 914.0, sd[1]["a"], sd[1]["dir"], 914.0, cn["c"], False)
                poly = f["poly"]
                self.assertGreater(_poly_area(poly), 0)
                # 隅のつなぎは2本の足場の帯に食い込まない（形の中の格子点が帯の中に無い。形は凹のこともある）
                xs, ys = [p[0] for p in poly], [p[1] for p in poly]
                pts = [(x, y) for x in range(int(min(xs)), int(max(xs)), 25) for y in range(int(min(ys)), int(max(ys)), 25)
                       if _in_poly((x + 0.5, y + 0.5), poly)]
                self.assertGreater(len(pts), 10)
                bad = [pt for pt in pts if _inside(pt, bi) or _inside(pt, bj)]
                self.assertEqual(bad, [], deg)

    def test_joined_ends_remove_end_guard(self):
        sd = self._two(60.0)
        job = plan_side_chain(sd, [0], False)
        _w, spec, groups = solve_side_job(job, sd, _extra(job), (False, True))
        self.assertEqual(spec["_joined_ends"], [[0, "e"]])
        m = groups[0][1].model
        self.assertEqual((m.open_start(0), m.open_end(0)), (True, False))     # 角の側だけ妻側の手すりを外す
        self.assertEqual(joined_ends(job, spec, (False, False)), [])



class TestGapBoardsAndCorners(unittest.TestCase):
    def test_concave_rail_ends_at_a_post(self):
        """入隅の手すりは近い支柱に留める（利用者の指定 2026-10-31）: 外の線を延ばした点のかわりに、後の足場の外の列の支柱."""
        dj = side_axis(math.radians(-60))
        a = (5500.0, 0.0)
        nj = (dj[1], -dj[0])
        posts, acc = [], 0.0
        for sp in [0, 1829, 1524, 610]:
            acc += sp
            posts.append((a[0] + nj[0] * 914 + dj[0] * acc, a[1] + nj[1] * 914 + dj[1] * acc))
        f = corner_fill((4572.0, 0.0), (1.0, 0.0), 914.0, a, dj, 914.0, a, False, posts_j=posts)
        k = f["rail"][0]
        end = f["poly"][(k + 1) % len(f["poly"])]
        self.assertTrue(any(math.dist(end, q) < 1.0 for q in posts), end)

    def test_gap_boards_for_two_row_decks(self):
        """床の2枚敷き（500＋240）にすき間板（利用者の指定 2026-10-31: 二列並べるには隙間板をつけて）. 日建は 910・606 の組み合わせ."""
        from ashiba.cli import solve_all
        from ashiba.gdl_params import _gap_board_params
        from ashiba.master import load_master
        from ashiba.quantity import gap_board_pieces

        gb = load_master("nikken_nd1800").by_category("すき間板")
        self.assertEqual({s: sorted((p.model_no, k) for p, k in gap_board_pieces(gb, s)) for s in (1829, 1524, 1219, 914)},
                         {1829: [("NDSK09", 2)], 1524: [("NDSK06", 1), ("NDSK09", 1)], 1219: [("NDSK06", 2)],
                          914: [("NDSK09", 1)]})
        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 7000,
                "series_id": "nikken_nd1800"}
        two = solve_all({**base, "scaffold_width_mm": 900})
        self.assertGreater(sum(l.qty for l in two.quantity.lines if l.part.category == "すき間板"), 0)
        self.assertEqual(_gap_board_params(two.model, list(two.model.deck_widths_in_use)),
                         {"gapBd": True, "gapW": 0.44, "gapT": 0.018})
        one = solve_all(base)                                                   # 幅 610 は 500 の1枚敷き
        self.assertEqual(sum(l.qty for l in one.quantity.lines if l.part.category == "すき間板"), 0)
        off = solve_all({**base, "scaffold_width_mm": 900, "gap_boards": False})
        self.assertEqual(sum(l.qty for l in off.quantity.lines if l.part.category == "すき間板"), 0)


if __name__ == "__main__":
    unittest.main()
