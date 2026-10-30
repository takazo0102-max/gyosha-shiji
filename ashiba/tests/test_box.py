"""足場の箱（超簡易モード。利用者の指定 2026-10-30: 箱を作って自分で伸び縮み・一周の箱・ボタンで本体にする）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.box import box_coins, box_loop, box_params, contains, parse_box_params, snap_spans, thickness_conditions
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

if __name__ == "__main__":
    unittest.main()
