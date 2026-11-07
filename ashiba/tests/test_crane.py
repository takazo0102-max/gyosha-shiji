"""移動式クレーン（利用者の指定 2026-11-01: クレーン リサーチして追加して）."""

from __future__ import annotations

import math
import re
import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.crane import (MODELS, PLATE_AREA, Lift, boom_angle, boom_axis, crane_plan, hook_height, judge, part_params,
                          plan_lift, rated, rated_strings, report, seg_box_distance)

M25, M50, M70 = MODELS["25t"], MODELS["50t"], MODELS["70t"]


class TestRatedTables(unittest.TestCase):
    def test_values_from_the_spec_sheets(self):
        """タダノの定格総荷重表の値（GR-250N（Ⅴ）6.6m・3.6m、GR-500N（Ⅰ）7.4m、GR-700N-3 7.8m）."""
        self.assertEqual(rated(M25, 6.6, 23.45, 10.0), 7.6)
        self.assertEqual(rated(M25, 6.6, 9.35, 3.5), 25.0)
        self.assertEqual(rated(M25, 3.6, 16.4, 10.0), 2.9)
        self.assertEqual(rated(M50, 7.4, 41.2, 10.0), 7.0)
        self.assertEqual(rated(M50, 7.4, 38.05, 10.0), 8.5)
        self.assertEqual(rated(M70, 7.8, 30.3, 20.0), 4.1)                     # モードの違う2列は大きい方
        self.assertIsNone(rated(M70, 7.8, 9.8, 2.1))                       # 70t は重荷重装置付き（※）の値なので入れない
        self.assertEqual(rated(M70, 7.8, 9.8, 6.0), 32.4)

    def test_between_rows_and_out_of_reach(self):
        self.assertEqual(rated(M25, 6.6, 23.45, 10.3), 6.65)                   # 間は外側の行（安全側）
        self.assertIsNone(rated(M25, 6.6, 9.35, 7.0))                          # 9.35m のブームは 6.5m まで
        self.assertIsNone(rated(M25, 6.6, 30.5, 3.0))                          # 長いブームは近くに下ろせない
        self.assertEqual(rated(M25, 5.5, 16.4, 10.0), 4.95)                    # 張出 5.5m は 5.0m の表で


class TestGeometry(unittest.TestCase):
    def test_hook_height_matches_max_lift_height(self):
        """30.5m のブームを最大の 84° に立てたときのフックの掛け位置 ≒ 仕様書の最大地上揚程 31.3m（ブームの先からの距離はその逆算）."""
        import math
        self.assertAlmostEqual(hook_height(M25, 30.5, 30500.0 * math.cos(math.radians(84.0)) - M25.piv_b), 31300.0, delta=50.0)
        self.assertEqual(hook_height(M25, 9.35, 9000.0), -1.0)
        self.assertAlmostEqual(boom_angle(M25, 23.45, 12000.0), 51.5, places=1)   # フートピンは旋回中心の 2.6m 後ろ（寸法図）
        self.assertEqual(max(M25.spreads) * 1000.0 + M25.float_ab[0], 6900.0)  # フロート外端（寸法図。フロートの横 300）
        self.assertEqual(max(M70.spreads) * 1000.0 + M70.float_d, 8200.0)


class TestPlan(unittest.TestCase):
    def test_shortest_boom_that_reaches_and_lifts(self):
        x = plan_lift(M25, 6.6, Lift("柱", 12000.0, 2.5, 15000.0))
        self.assertEqual((x.boom, x.rated_t, x.status), (23.45, 5.8, "OK"))     # 16.4m はフックが 15m に届かない
        y = plan_lift(M25, 6.6, Lift("重い", 8000.0, 9.0, 8000.0))
        self.assertEqual((y.boom, y.status), (16.4, "OK"))                      # 11.4t の 82%
        z = plan_lift(M25, 6.6, Lift("過負荷", 20000.0, 3.0, 5000.0))
        self.assertEqual(z.status, "NG")
        w = plan_lift(M25, 6.6, Lift("ぎりぎり", 10000.0, 6.8, 5000.0))
        self.assertEqual(w.status, "WARN")                                      # 定格 7.6t の 93%（計画は 90% まで）

    def test_auto_model_and_plates(self):
        p = crane_plan("a", [Lift("鉄骨", 8000.0, 15.0, 10000.0)])
        self.assertEqual(p.model.key, "k50t")                                   # 25t・35t では足りず、満たす一番小さい 50t（加藤 SL-500RfⅢ）
        self.assertEqual(crane_plan("a", [Lift("鉄骨", 8000.0, 15.0, 10000.0)], "50t").model.key, "50t")   # 機種を決めればその機種
        self.assertTrue(p.ok)
        q = crane_plan("b", [Lift("柱", 12000.0, 2.5, 15000.0)])
        self.assertEqual((q.model.key, q.plates), ("25t", 1))
        self.assertAlmostEqual(q.reaction_t, 0.8 * (25.495 + 2.5 + 0.22 + 0.05), places=2)   # 25t のフックは公表 0.22t
        self.assertLessEqual(q.pressure, 100.0)
        soft = crane_plan("c", [Lift("柱", 12000.0, 2.5, 15000.0)], soil_q=60.0)
        self.assertEqual(soft.plates, 2)                                        # 十字に2枚
        self.assertAlmostEqual(soft.pressure, soft.reaction_t * 9.80665 / PLATE_AREA[2])
        mud = crane_plan("d", [Lift("柱", 12000.0, 2.5, 15000.0)], soil_q=30.0)
        self.assertFalse(mud.ok)

    def test_checks_quantity_report_and_params(self):
        p = crane_plan("a", [Lift("柱", 12000.0, 2.5, 15000.0), Lift("資材", 18000.0, 1.0, 12000.0)], model="25t", spread=5.0)
        st = {c.item: c.status for c in p.checks}
        self.assertEqual(st["アウトリガの張出"], "WARN")                            # 最大限に張り出していない（70条の5）
        for k in ("立入禁止", "強風", "作業計画"):
            self.assertIn(k, st)
        self.assertIn("厚板鋼板 NT22×5×10（1524×3048×22・802kg）", {a for a, _n, _c in p.quantity})
        prm = part_params(p, 30.0)
        self.assertEqual((prm["crType"], prm["outW"], prm["wrR"], prm["slew"]), (4, 5.0, "12000,18000", 30.0))   # 機種の並びの 4 番
        self.assertEqual(prm["boomL"], p.governing.boom)
        md = report([p])
        for w in ("# 移動式クレーン", "クレーン則", "タダノ", "定格総荷重"):
            self.assertIn(w, md)


class TestPartTable(unittest.TestCase):
    def test_rated_strings_fit_255(self):
        """部品へ渡す定格総荷重表: 文字のパラメータは 255 字で切れるので張出幅の段とブームの列ごとに分け、どれも 255 字以内.
        全部の張出幅の表を渡す（アウトリガを引くと部品が段を選び直す。利用者の指定 2026-11-01: 性能表とリンクさせてね）."""
        for m in MODELS.values():
            s = rated_strings(m)
            self.assertTrue(all(len(v) <= 255 for v in s.values()), (m.key, {k: len(v) for k, v in s.items()}))
        s = rated_strings(M25)
        self.assertEqual(s["rtS"], "6600,6100,5000,3600,2300")
        radii = [float(v) / 1000 for v in s["rr1"].split(",")]
        col = [int(v) for v in s["rs1c3"].split(",")]                      # 張出 6.6m・3番目のブーム 23.45m（10kg 単位）
        self.assertEqual(col[radii.index(10.0)], 760)
        self.assertEqual(len(s["rs4c2"].split(",")), len(s["rr4"].split(",")))   # 段ごとの半径の並びで
        big = rated_strings(MODELS["100t"])                                 # 100t は 12 列・36 行でも 255 字以内
        self.assertEqual(len(big["rtB"].split(",")), 12)

    def test_effective_spread(self):
        """定格を読む張出幅は4脚の一番小さい張出の 2 倍（古い部品は outW）."""
        from ashiba.crane import effective_spread
        self.assertEqual(effective_spread({"oFL": 3.3, "oFR": 2.5, "oRL": 3.3, "oRR": 3.3}), 5.0)
        self.assertEqual(effective_spread({"outW": 6.1}), 6.1)


class TestModels(unittest.TestCase):
    """ラフタークレーン 12 機種（利用者の指定 2026-11-01: ラフタークレーンも追加して種類も増やして）."""

    def test_twelve_models_and_tables(self):
        import re
        from pathlib import Path
        self.assertEqual(len(MODELS), 12)
        self.assertEqual(sorted(m.kind for m in MODELS.values()), list(range(1, 13)))
        caps = [m.capacity_t for m in MODELS.values()]
        self.assertEqual(caps, sorted(caps))                                # 小さい順（自動で選ぶとき一番小さい機種から）
        names = set(re.findall(r'Name="([^"]+)"', (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_crane"
                                                    / "paramlist.xml").read_text(encoding="utf-8")))
        for m in MODELS.values():
            sp = m.spreads
            self.assertLessEqual(len(sp), 8, m.key)
            self.assertLessEqual(len(m.booms), 12, m.key)
            # 張出が小さいと定格が大きくならない・半径が大きいと定格が大きくならない（調べで確かめた性質）
            for a, b in zip(sp, sp[1:]):
                for r, row in m.tables[b].items():
                    for bm, t in row.items():
                        big = m.tables[a].get(r, {}).get(bm)
                        if big is not None:
                            self.assertLessEqual(t, big + 1e-9, (m.key, a, b, r, bm))
            p = crane_plan("x", [Lift("A", 6000.0, 1.0, 8000.0)], m.key)
            self.assertEqual(set(part_params(p, 0.0)) - names, set(), m.key)

    def test_catalog_values(self):
        """仕様書の値: 加藤 SR-250RfⅡ の左右の脚のずれ 278（左の前 +3,339・右の前 +3,061）、タダノ 100t は 12 列."""
        k = MODELS["k25t"]
        self.assertEqual((k.out_front, k.out_front - k.out_shift), (3339.0, 3061.0))
        self.assertEqual(rated(MODELS["k25t"], 6.6, 9.35, 2.5), 25.0)
        self.assertEqual(len(MODELS["100t"].booms), 12)
        self.assertEqual(MODELS["70t"].spreads, [7.8, 7.6, 7.2, 6.4, 5.38, 4.18, 2.36])


class TestSmartconChecks(unittest.TestCase):
    """smartCON Planner を手本にした揚重判定・ブームの干渉（利用者の指定 2026-11-01）."""

    def test_judge_four_results(self):
        """2026-11-01 実機の試験の壁4枚と同じ値: 揚重可能・遠すぎ・高すぎ・重すぎ."""
        self.assertEqual(judge(M25, 6.6, 12000.0, 8000.0, 1.15)[0], "揚重可能")
        self.assertEqual(judge(M25, 6.6, 32000.0, 8000.0, 1.15)[0], "遠すぎ")          # どのブームも 32m に届かない
        self.assertEqual(judge(M25, 6.6, 8300.0, 42000.0, 7.68)[0], "高すぎ")          # 最大地上揚程 31.3m を超える
        self.assertEqual(judge(M25, 6.6, 10600.0, 8000.0, 21.6)[0], "重すぎ")

    def test_reach_for(self):
        """重すぎ・遠すぎのとき、吊れるいちばん大きい作業半径（0.5m 刻み）. そこでは揚重可能、0.5m 先では吊れない."""
        from ashiba.crane import reach_for
        r = reach_for(M25, 6.6, 8000.0, 4.0)
        self.assertIsNotNone(r)
        self.assertEqual(r % 500.0, 0.0)
        self.assertEqual(judge(M25, 6.6, r, 8000.0, 4.0)[0], "揚重可能")
        self.assertNotEqual(judge(M25, 6.6, r + 500.0, 8000.0, 4.0)[0], "揚重可能")
        self.assertIsNone(reach_for(M25, 6.6, 8000.0, 40.0))             # 25t 吊りで 40t はどこでも無理

    def test_segment_to_box_distance(self):
        self.assertEqual(seg_box_distance((0, 0, 0), (10, 0, 0), (4, -1, -1), (6, 1, 1)), 0.0)    # 箱の中を通る
        self.assertAlmostEqual(seg_box_distance((0, 0, 0), (10, 0, 0), (4, 3, -1), (6, 5, 1)), 3.0)
        self.assertAlmostEqual(seg_box_distance((0, 0, 0), (10, 0, 0), (12, 0, 0), (13, 1, 1)), 2.0)  # 先の向こう

    def test_boom_axis_and_travel(self):
        """車体 90°・旋回 −90° で +X へ。走行姿勢は最短ブームを車体の前へ水平に."""
        p0, p1 = boom_axis({"slew": -90.0, "boomL": 16.4, "boomA": 31.388}, (0.0, 0.0, 0.0), 90.0)
        self.assertEqual([round(v) for v in p0 + p1], [-1000, 0, 2300, 13000, 0, 10842])
        q0, q1 = boom_axis({"slew": -90.0, "boomL": 16.4, "boomA": 31.388, "bMin": 9.35, "travel": True}, (0.0, 0.0, 0.0), 90.0)
        self.assertEqual([round(v) for v in q0 + q1], [0, -1000, 2300, 0, 8350, 2300])


class TestRunScript(unittest.TestCase):
    def test_points_to_lifts(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from crane_run import lifts_from_points

        c, ls = lifts_from_points([(0.0, 0.0), (12000.0, 0.0), (0.0, 18000.0)], "2.5", "15000,12000")
        self.assertEqual(c, (0.0, 0.0))
        self.assertEqual([(x.radius, x.load_t, x.need_z) for x in ls], [(12000.0, 2.5, 15000.0), (18000.0, 2.5, 12000.0)])

    def test_form_takes_load_and_height(self):
        import argparse
        import json
        import os
        from unittest import mock

        sys.path.insert(0, str(SRC.parent / "scripts"))
        import crane_run as C

        a = argparse.Namespace(model=None, load=None, lift_z=None, boom=0.0, jib=0.0, jib_off=5.0, ratio=0.9)
        ans = json.dumps({"button": "place", "values": {"load": "2.8", "liftz": "16000", "ratio": "0.8"}})
        with mock.patch.dict(os.environ, {"ASHIBA_FORM_ANSWER": ans}):
            self.assertTrue(C.ask(a))
        self.assertEqual((a.load, a.lift_z, a.ratio), ("2.8", "16000", 0.8))


class TestClickPlacement(unittest.TestCase):
    """線でなくクリックで置く（利用者の指定 2026-11-06「クレーンも線でなくクリックで配置するようにして」）."""

    def _main(self, window, picked=None, lines=()):
        from unittest import mock

        sys.path.insert(0, str(SRC.parent / "scripts"))
        import crane_run as C

        class Client:
            def tapir(self, name, params=None, **kw):
                return {"currentWindowType": window}

        pick = mock.Mock(return_value=picked)
        with mock.patch("ashiba.tapir_adapter.ArchicadClient", Client), \
                mock.patch("ashiba.naming.prune_gone", lambda c, rec: rec), \
                mock.patch("guide_lines.selected_guides", lambda c: []), \
                mock.patch("kakoi_run.chains", lambda g: list(lines)), \
                mock.patch("machine_run.front_archicad"), mock.patch("machine_run.pick_line", pick), \
                mock.patch("run_from_archicad.ensure_parts", side_effect=SystemExit("置く所まで来た")):
            return C.main(["--load", "2.5"]), pick

    def test_no_line_asks_for_two_clicks(self):
        rc, pick = self._main("FloorPlan")
        self.assertEqual(rc, 0)                          # Esc はやめる
        self.assertEqual(pick.call_args.args[1:], ("Click the crane center", "Click the load position"))
        self.assertTrue(all(ord(ch) < 128 for t in pick.call_args.args[1:] for ch in t))    # Tapir の案内は 1バイトのみ

    def test_click_goes_on_to_placing(self):
        with self.assertRaises(SystemExit):
            self._main("FloorPlan", [(0.0, 0.0), (12000.0, 0.0)])

    def test_needs_the_floor_plan(self):
        rc, pick = self._main("3DModel")
        self.assertEqual(rc, 1)
        pick.assert_not_called()

    def test_selected_line_is_kept(self):
        with self.assertRaises(SystemExit):
            rc, pick = self._main("3DModel", None, [("k", [(0.0, 0.0), (12000.0, 0.0)], False)])


class TestLiftTool(unittest.TestCase):
    """SCP の手引の揚重判定（利用者の指定 2026-11-06「SCPに入っているクレーンの機能全て入れて揚重検討が楽になるように」）."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SRC.parent / "scripts"))

    def test_unreadable_weight_is_not_a_pass(self):
        from crane_check import weigh

        self.assertIsNone(weigh("density", None, None, "Object", None, None, {}))
        self.assertIsNone(weigh("density", 0.0, None, "Object", None, None, {}))
        self.assertIsNone(weigh("bm", 1.0, None, "Slab", None, None, {}))

    def test_weight_modes_and_factor(self):
        from crane_check import weigh

        self.assertAlmostEqual(weigh("density", 2.0, None, "Beam", None, None, {}), 15.7)
        self.assertAlmostEqual(weigh("density", 2.0, None, "Slab", None, None, {"Slab": 1.1}), 5.28)
        self.assertAlmostEqual(weigh("density", 2.0, None, "Slab", 3.0, None, {}), 6.0)
        self.assertEqual(weigh("direct", 2.0, None, "Slab", None, 4.5, {"Slab": 2.0}), 4.5)    # 直接は補正しない
        self.assertAlmostEqual(weigh("bm", 2.0, 4.8, "Slab", None, None, {"Slab": 0.5}), 2.4)

    def test_density_from_material(self):
        from crane_check import _density_of

        self.assertEqual(_density_of({"properties": {"thermalConductivity": 1.6, "density": 2400}}), 2400.0)
        self.assertIsNone(_density_of({"error": {"code": 1}}))

    def test_crawler_judge(self):
        from ashiba.machine import MACHINES, crawler_judge, crawler_reach

        m = MACHINES["cc50"]
        ps = dict(m.params)
        r = crawler_judge(m, ps, 12.0, 10.0, 5.0, 0.9)
        self.assertEqual((r["判定"], r["ブーム"], r["定格"]), ("揚重可能", 21.3, 9.0))
        self.assertEqual(crawler_judge(m, ps, 12.0, 10.0, 20.0, 0.9)["判定"], "重すぎ")
        self.assertEqual(crawler_judge(m, ps, 60.0, 10.0, 1.0, 0.9)["判定"], "遠すぎ")
        self.assertEqual(crawler_judge(m, ps, 12.0, 200.0, 1.0, 0.9)["判定"], "高すぎ")
        self.assertEqual(crawler_reach(m, ps, 10.0, 7.0, 0.9), 12.0)      # 14m は 7.5×0.9 で足りず、12m の 9.2×0.9 で足りる

    def test_crawler_with_jib_reads_its_column(self):
        from ashiba.machine import MACHINES, crawler_judge

        m = MACHINES["cc50"]
        r = crawler_judge(m, {**m.params, "lbL": 30.5, "jbL": 12.2, "jbO": 10.0}, 16.0, 10.0, 2.0, 0.9)
        self.assertEqual((r["判定"], r["ブーム"], r["ジブ"]), ("揚重可能", 30.5, 12.2))

    def test_axes_include_the_jib(self):
        from ashiba.crane import crane_axes
        from ashiba.machine import MACHINES, crawler_axes

        ps = {"boomL": 20.0, "boomA": 60.0, "pivB": 1.0, "pivH": 2.0, "jbL": 8.0, "jbO": 5.0, "slew": 0.0}
        self.assertEqual(len(crane_axes({**ps, "jbL": 0.0}, (0, 0, 0), 0.0)), 1)
        segs = crane_axes(ps, (0, 0, 0), 0.0)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0][1], segs[1][0])
        m = MACHINES["cc50"]
        self.assertEqual(len(crawler_axes({**m.params, "jbL": 12.2}, (0, 0, 0), 0.0)), 2)

    def test_copy_goes_under_the_hook(self):
        from crane_check import hook_point

        h = hook_point({"hkR": 10.0, "slew": 90.0, "boomL": 20.0, "boomA": 60.0, "hkZ": 7.0}, (1000.0, 0.0, 500.0), 0.0, "rough")
        self.assertAlmostEqual(h[0], 1000.0)
        self.assertAlmostEqual(h[1], 10000.0)
        self.assertAlmostEqual(h[2], 7500.0)

    def test_erase_finds_columns_not_only_objects(self):
        from crane_check import erase_copies

        class Client:
            gone = []

            def tapir(self, name, params):
                return {"elements": [{"elementId": {"guid": "a"}}] if params["elementType"] == "Column" else []}

            def delete_elements(self, els):
                self.gone += els

        k = Client()
        self.assertEqual(erase_copies(k, ["a", "消えた"]), 1)
        self.assertEqual(k.gone, [{"elementId": {"guid": "a"}}])

    def test_form_fills_the_options(self):
        import argparse
        import json
        import os
        from unittest import mock

        import crane_check as K

        a = argparse.Namespace(all=False, draw=False, sling=6000.0, mode="density", density=None, weight=None, hook=None, rig=None, factors={})
        ans = json.dumps({"button": "go", "values": {"scope": "表示中の全部（一括）", "sling": "3000", "mode": "重量直接指定", "weight": "2.5",
                                                     "hook": "0.3", "rig": "0.1", "fColumn": "1.2", "draw": "1"}})
        with mock.patch.dict(os.environ, {"ASHIBA_FORM_ANSWER": ans}):
            self.assertTrue(K.ask_lift(a, {}, 0.25, 0.05))
        self.assertEqual((a.all, a.sling, a.mode, a.weight, a.hook, a.rig, a.draw), (True, 3000.0, "direct", 2.5, 0.3, 0.1, True))
        self.assertEqual(a.factors["Column"], 1.2)


class TestCraneMove(unittest.TestCase):
    """車両・フックの移動（SCP の手引 p.5）."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SRC.parent / "scripts"))

    def test_hook_moves_in_plan_directions(self):
        from crane_move import move_hook

        r, s = move_hook(10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        self.assertAlmostEqual(r, math.hypot(10, 10))
        self.assertAlmostEqual(s, 45.0)
        r, s = move_hook(10.0, 0.0, 90.0, 0.0, 10.0, 0.0, 0.0)      # 車体が 90° 向いていれば、図面の +Y は部品の +X
        self.assertAlmostEqual(r, 20.0)
        self.assertAlmostEqual(s, 0.0)

    def test_radius_and_slew_steps(self):
        from crane_move import move_hook

        r, s = move_hook(10.0, 350.0, 0.0, 0.0, 0.0, 1.0, 15.0)
        self.assertAlmostEqual(r, 11.0)
        self.assertAlmostEqual(s, 5.0)

    def test_ground_is_the_highest_top_below(self):
        from crane_move import ground_z

        bs = [((0, 0, 0), (10, 10, 3000)), ((0, 0, 0), (10, 10, 5000)), ((0, 0, 0), (10, 10, 9000)), ((50, 50, 0), (60, 60, 7000)), None]
        self.assertEqual(ground_z(bs, 5, 5, 6000), 5000)
        self.assertIsNone(ground_z(bs, 100, 100, 6000))

    def test_group_moves_the_plates_too(self):
        from crane_move import group_of

        self.assertEqual(group_of({"k": ["a", "b"]}, "a"), ["a", "b"])
        self.assertEqual(group_of({"k": ["a", "b"]}, "z"), ["z"])

    @unittest.skipUnless(__import__("shutil").which("swiftc"), "swiftc が無い")
    def test_panel_builds(self):
        import os
        import subprocess

        import crane_panel

        r = subprocess.run([str(crane_panel.binary()), "/tmp", "/usr/bin/true"], capture_output=True, text=True,
                           env={**os.environ, "ASHIBA_PALETTE_SELFTEST": "1"}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("接地", r.stdout)
        self.assertEqual(r.stdout.count("↑"), 2)


class TestCraneLod(unittest.TestCase):
    """全部のクレーンを LOD500 に（利用者の指定 2026-11-06「クレーンがすごいことになっている 全てのクレーンのLOD500程度にして」）."""

    def test_every_model_has_the_shape(self):
        from ashiba.crane import CARRIER_REAR, LOD_MODEL, lod_params

        self.assertEqual(set(MODELS), set(LOD_MODEL))
        self.assertEqual(set(MODELS), set(CARRIER_REAR))
        for m in MODELS.values():
            p = lod_params(m)
            self.assertGreater(m.piv_h / 1000.0 - p["ftZ"], 0.8, m.key)            # 上部原点は地面の上
            self.assertLess(p["cyT"], p["cyUa"], m.key)                             # チューブはピン間より短い

    def test_cylinder_pins_do_not_follow_the_boom_length(self):
        """起伏シリンダの上ピンは基本ブームに固定（ブームを伸ばしても動かない）."""
        hsf = SRC.parent / "gdl" / "hsf" / "ashiba_crane" / "scripts" / "3d.gdl"
        g = hsf.read_text(encoding="utf-8")
        self.assertIn("xU = -pivB + cyUa * cos(bB) + cyUb * sin(bB)", g)
        self.assertNotIn("0.35 * bL", g)

    def test_carrier_stops_at_the_rear_end(self):
        """全長はブームの先まで。車体の後端は carB（前は 25t の全長で 7.9m 後ろまで描いていた）."""
        from ashiba.crane import lod_params

        self.assertEqual(lod_params(MODELS["25t"])["carB"], 4.155)
        g = (SRC.parent / "gdl" / "hsf" / "ashiba_crane" / "scripts" / "1d.gdl").read_text(encoding="utf-8")
        self.assertIn("carRr = carB", g)

    def test_colors_follow_the_maker(self):
        from ashiba.crane import lod_params

        self.assertEqual(lod_params(MODELS["k25t"])["clr"], 2)
        self.assertEqual(lod_params(MODELS["25t"])["clr"], 1)

    def test_scp_switches_exist(self):
        crane = (SRC.parent / "gdl" / "hsf" / "ashiba_crane" / "paramlist.xml").read_text(encoding="utf-8")
        for n in ("bmStep", "infoOn", "wrOn", "wrShow", "wrFlip", "ldW", "ldS", "clr"):
            self.assertIn(f'Name="{n}"', crane)
        machine = (SRC.parent / "gdl" / "hsf" / "ashiba_machine" / "paramlist.xml").read_text(encoding="utf-8")
        for n in ("lbGnd", "lbRW", "lbFat", "infoOn"):
            self.assertIn(f'Name="{n}"', machine)
        tower = (SRC.parent / "gdl" / "hsf" / "ashiba_tower" / "paramlist.xml").read_text(encoding="utf-8")
        for n in ("tcBase", "msStep", "hkLim", "hkMax", "hfX", "rtT", "tcClr"):
            self.assertIn(f'Name="{n}"', tower)

    def test_tower_part_gets_its_rating(self):
        from ashiba.tower import TOWERS, Placed, check, part_params as tower_params

        p = Placed("c", TOWERS["jcl730"])
        check(p)
        q = tower_params(p)
        self.assertEqual(len(q["rtR"].split(",")), len(q["rtT"].split(",")))
        self.assertLessEqual(len(q["rtR"]), 255)
        self.assertEqual(tower_params(TOWERS["v600"])["tcClr"], 2)                 # JCC は赤白（IHI 技報）


class TestBulkLift(unittest.TestCase):
    """一括揚重判定で吊荷作図にチェックを入れたら部材が増えた（利用者の報告 2026-11-07）."""

    def test_notes_are_limited(self):
        from crane_check import reach_notes

        rows = [("C1", "Column", 0.1, 5.0, 20000.0, 3000.0, "重すぎ", None, 9000.0)] * 92 + [("C2", "Column", 0.1, 1.0, 5000.0, 3000.0, "揚重可能", None, None)]
        got = reach_notes(rows)
        self.assertEqual(len(got), 6)
        self.assertIn("ほか 87個", got[-1])
        self.assertIn("作業半径 9.0m 以内", got[0])
        self.assertEqual(reach_notes(rows[-1:]), [])

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SRC.parent / "scripts"))

    @staticmethod
    def row(guid, kind="Column", name=""):
        return ({"elementId": {"guid": guid}}, {"type": kind, "details": {"libPart": {"name": name}}})

    def test_copies_and_marks_are_not_members(self):
        from crane_check import lift_targets

        pool = [self.row("a"), self.row("copy"), self.row("crane", "Object", "ashiba_crane_1"), self.row("s", "Object", "ashiba_plate_1"),
                self.row("g", "Object", "標準通り芯マーカー"), self.row("o", "Object", "仮置きの箱"), self.row("m", "Mesh")]
        got = [e["elementId"]["guid"] for e, _d in lift_targets(pool, "crane", {"copy"})]
        self.assertEqual(got, ["a", "o"])

    def test_bulk_never_draws(self):
        g = (SRC.parent / "scripts" / "crane_check.py").read_text(encoding="utf-8")
        self.assertIn("a.draw = a.draw and not a.all", g)
        self.assertLess(g.index("a.draw = a.draw and not a.all"), g.index("made = copy_loads("))


class TestHookMark(unittest.TestCase):
    """吊り点の丸十字と Max（利用者の指定 2026-11-07）."""

    PARTS = ("ashiba_crane", "ashiba_machine", "ashiba_tower")

    def hsf(self, part, name):
        return (SRC.parent / "gdl" / "hsf" / part / name).read_text(encoding="utf-8")

    def test_mark_moves_freely_in_3d(self):
        for part in self.PARTS:
            g = self.hsf(part, "scripts/3d.gdl")
            for ref, flags in (("hfX", ("1 + 128", "2", "3")), ("hfY", ("1 + 128", "2", "3")), ("mkZ", ("1 + 128", "2", "3"))):
                for f in flags:
                    self.assertRegex(g, rf"hotspot .*, {ref}, {re.escape(f)}\n", part)
            self.assertIn("mkQ = mkH - slgH", g)
            self.assertIn('"Max "', g)
            self.assertIn("mkV = capT", g)

    def test_mark_lies_flat_and_only_the_text_faces_the_view(self):
        for part in self.PARTS:
            g = self.hsf(part, "scripts/3d.gdl")
            a = g.index("add mkX, mkY, mkQ")
            self.assertLess(g.index("prism_ nsp / 3", a), g.index("rotx 90", a))
            self.assertLess(g.index("rotx 90", a), g.index('style "mkI"', a))

    def test_plan_draws_the_mark(self):
        for part in self.PARTS:
            self.assertIn("circle2 xF, yF, mkR", self.hsf(part, "scripts/2d.gdl"))

    def test_mark_height_moves_the_hook(self):
        self.assertIn("parameters hkZ = mkZ + slgH", self.hsf("ashiba_crane", "scripts/vl.gdl"))
        self.assertIn("parameters hkD = max(0.5, tpZ - mkZ - slgH)", self.hsf("ashiba_machine", "scripts/vl.gdl"))
        self.assertIn("parameters hkD = max(0.5, jZ - mkZ - slgH)", self.hsf("ashiba_tower", "scripts/vl.gdl"))

    def test_info_text_does_not_repeat_max(self):
        for part in self.PARTS[:2]:
            self.assertIn("if slgOn = 0 then", self.hsf(part, "scripts/3d.gdl"))

    def test_check_uses_the_part_sling(self):
        g = (SRC.parent / "scripts" / "crane_check.py").read_text(encoding="utf-8")
        self.assertIn('a.sling = float(ps["slgH"]) * 1000.0', g)


class TestRadiiDisplay(unittest.TestCase):
    """平面の作業半径の表示（SCP の「クレーン設定」。利用者の指定 2026-11-07「これも機能追加して」）."""

    PARTS = ("ashiba_crane", "ashiba_machine", "ashiba_tower")

    def hsf(self, part, name):
        return (SRC.parent / "gdl" / "hsf" / part / name).read_text(encoding="utf-8")

    def test_all_cranes_have_the_items(self):
        for part in self.PARTS:
            pl = self.hsf(part, "paramlist.xml")
            for n in ("wiNum", "wiPen", *(f"wi{k}{i}" for k in "RABMF" for i in range(1, 6))):
                self.assertIn(f'Name="{n}"', pl, part)

    def test_each_item_has_radius_range_and_turn_hotspots(self):
        for part in self.PARTS:
            g = self.hsf(part, "scripts/2d.gdl")
            for i in range(1, 6):
                for n, flags in ((f"wiR{i}", (r"1 \+ 128", "2", "3")), (f"wiA{i}", ("6", "4", "5")), (f"wiB{i}", ("6", "4", "5")), (f"wiM{i}", ("6", "4", "5"))):
                    for f in flags:
                        self.assertRegex(g, rf"hotspot2 .*, {n}, {f}\n", part)
            ids = re.findall(r"hotspot2 [^\n]*?, (\d+), (?!hid\b)[a-zA-Z]\w*, ", g)      # hid は番号の変数（前の数は座標）
            self.assertEqual(len(ids), len(set(ids)), part)

    def test_turning_the_middle_moves_both_ends(self):
        for part in self.PARTS:
            g = self.hsf(part, "scripts/vl.gdl")
            self.assertIn("parameters wiA1 = wiM1 - wiSq[1] / 2, wiB1 = wiM1 + wiSq[1] / 2", g)
            self.assertIn('hideparameter "wiR5", "wiA5", "wiB5", "wiF5"', g)

    def test_rated_load_uses_each_radius(self):
        self.assertIn("if rr[k] >= wiRq[wq] - 0.001 then iQ = k", self.hsf("ashiba_crane", "scripts/1d.gdl"))
        self.assertIn("if mtR[k] >= wiRq[wq] - 0.001 then iQ = k", self.hsf("ashiba_machine", "scripts/1d.gdl"))
        self.assertIn("if qR[k] >= wiRq[wq] - 0.001 and k <= nQt then vq = qT[k] / 100", self.hsf("ashiba_tower", "scripts/1d.gdl"))

    def test_settings_page_follows_the_count(self):
        for part in self.PARTS:
            g = self.hsf(part, "scripts/ui.gdl")
            self.assertIn('ui_infield "wiNum"', g)
            self.assertIn("if nWi >= 5 then", g)
            self.assertIn('ui_infield "wiPen"', g)
            self.assertIn("<Script_UI", self.hsf(part, "libpartdata.xml"))

    def test_placing_shows_the_lift_radii_at_the_boom(self):
        from ashiba.crane import radii_values

        v = radii_values([14.0, 9.0, 14.0], 30.0)
        self.assertEqual(v["wiNum"], 2)
        self.assertEqual((v["wiR1"], v["wiR2"]), (9.0, 14.0))
        self.assertEqual((v["wiA1"], v["wiB1"], v["wiM1"]), (20.0, 40.0, 30.0))
        self.assertEqual(radii_values([float(r) for r in range(5, 12)], 0.0)["wiNum"], 5)

    def test_angles_go_to_tapir_in_radians(self):
        from ashiba.tapir_adapter import to_tapir_values

        self.assertAlmostEqual(to_tapir_values({"wiA1": 180.0})["wiA1"], math.pi)
        self.assertEqual(to_tapir_values({"wiR1": 10.0})["wiR1"], 10.0)


class TestParamRoundtrip(unittest.TestCase):
    def test_mismatches(self):
        """実機の値の比べ方: 角度は Tapir がラジアンで返す、文字は 255 字で切れる。吸い付きで脚が変われば食い違い（2026-11-02）."""
        import math
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from dev_param_roundtrip import mismatches
        sent = {"slew": 30.0, "oSnap": True, "rtS": "x" * 300, "oFL": 3.8}
        self.assertEqual(mismatches(sent, {"slew": math.radians(30.0), "oSnap": 1, "rtS": "x" * 255, "oFL": 3.8}), [])
        self.assertEqual(mismatches(sent, {"slew": math.radians(30.0), "oSnap": True, "rtS": "x" * 255, "oFL": 3.3}),
                         [("oFL", 3.8, 3.3)])
        # 度のまま残った角度は食い違い（ラジアンに直さずに送った。2026-11-03 実機）
        self.assertEqual(mismatches({"slew": 30.0}, {"slew": 30.0}), [("slew", 30.0, 30.0)])



class TestBoomAndJib(unittest.TestCase):
    """ブーム・ジブの設定と起伏角のホットスポット（利用者の指定 2026-11-06）."""

    def test_pose_with_jib_reaches_the_radius(self):
        import math

        from ashiba.crane import MODELS, pose_angle

        m = MODELS["25t"]
        a = pose_angle(m, 23.45, 14000.0, 8.2, 5.0)
        r = -m.piv_b / 1000.0 + 23.45 * math.cos(math.radians(a)) + 8.2 * math.cos(math.radians(a - 5.0))
        self.assertAlmostEqual(r, 14.0, places=4)

    def test_part_takes_boom_and_jib(self):
        from ashiba.crane import Lift, crane_plan, part_params

        p = crane_plan("c", [Lift("a", 14000.0, 2.5, 10000.0)], "25t")
        q = part_params(p, 30.0, boom_m=23.45, jib=8.2, jib_off=5.0)
        self.assertEqual((q["boomL"], q["jbL"], q["jbO"]), (23.45, 8.2, 5.0))
        self.assertEqual(part_params(p, 30.0)["jbL"], 0.0)

    def test_no_hanging_load_by_default(self):
        """吊り荷は描かない（利用者の指定 2026-11-06「クレーンについている吊りに消して」）. 描くときは部品の ldOn."""
        from ashiba.crane import Lift, crane_plan, part_params

        self.assertFalse(part_params(crane_plan("c", [Lift("a", 14000.0, 2.5, 10000.0)], "25t"), 30.0)["ldOn"])

    def test_every_model_lists_its_jibs(self):
        from ashiba.crane import JIBS, MODELS

        self.assertEqual(set(JIBS), set(MODELS))

    def test_gdl_has_tip_hotspot_and_min_radius(self):
        from pathlib import Path

        hsf = Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_crane" / "scripts"
        self.assertIn("23, boomA, 5", (hsf / "3d.gdl").read_text(encoding="utf-8"))
        self.assertIn('"最小 R"', (hsf / "2d.gdl").read_text(encoding="utf-8"))
        vl = (hsf / "vl.gdl").read_text(encoding="utf-8")
        self.assertIn('GLOB_MODPAR_NAME = "boomA"', vl)
        self.assertIn("parameters hkR = sqr(hfX * hfX + hfY * hfY), slew = aF", vl)
        d2 = (hsf / "2d.gdl").read_text(encoding="utf-8")
        self.assertIn("xF, yF, 2, hfX, 2", d2)
        self.assertIn("xF, yF, 32, hfY, 2", d2)


if __name__ == "__main__":
    unittest.main()
