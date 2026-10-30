"""足場の箱（超簡易モード。利用者の指定 2026-10-30: 箱を作って自分で伸び縮み・一周の箱・ボタンで本体にする）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.box import (box_coins, box_loop, box_params, box_sides, chain_sides, contains, parse_box_params,
                        parse_side_params, plan_side_chain, side_axis, side_params, snap_spans, solve_side_job,
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
        self.assertEqual(got["一側足場"][0], "一側足場")


def _sides(over=None):
    """7316×5487 の箱の4辺（左回り: 南・東・北・西）。over={番号: {属性}} で辺ごとに変える."""
    out = []
    for k, (a, ang, sp) in enumerate(box_sides((0.0, 0.0), 0.0, [1829] * 4, [1829] * 3)):
        s = {"a": a, "dir": side_axis(ang), "spans": sp, "base_mm": 0.0, "series_id": "albatross", "thick_mm": 900,
             "levels": 4, "standoff": 300.0, "floor_mm": 1800.0}
        s.update((over or {}).get(k, {}))
        out.append(s)
    return out


def _extra(job):
    return {"series_id": "albatross", **thickness_conditions(job["main_t"], 300.0)[1]}


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


if __name__ == "__main__":
    unittest.main()
