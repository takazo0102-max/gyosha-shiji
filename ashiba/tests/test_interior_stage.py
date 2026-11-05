"""内部ステージ足場（利用者の指定 2026-10-24: 内部足場の内部ステージ足場の機能追加して検証して）."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.interior_stage import solve_stage, stage_params, stage_report
from ashiba.master import load_master
from ashiba.structural import load_capacities

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
RECT = [[0, 0], [12000, 0], [12000, 8000], [0, 8000]]


def solve(**kw):
    m = load_master("nikken_nd1800")
    item = {"name": "吹抜け", "corners_mm": RECT, "deck_mm": 6000, **kw}
    return solve_stage(item, m, load_capacities("nikken_nd1800"))


class TestInteriorStage(unittest.TestCase):
    def test_grid_fits_inside_with_long_spans(self):
        r = solve()
        self.assertEqual(r.spans_u, [1829] * 6)
        self.assertEqual(r.spans_v, [1219] * 6)                 # 足場の幅は 1219 まで（利用者の指定 2026-10-29）
        self.assertLessEqual(r.length_u, 12000 - 300)
        self.assertEqual(r.deck_mm, 6000)
        self.assertEqual(r.levels[-1], 6000)
        # 中央に寄せる
        self.assertAlmostEqual(r.origin[0], (12000 - r.length_u) / 2, delta=1)

    def test_checks(self):
        r = solve()
        st = {c.item: c.status for c in r.checks}
        self.assertEqual(st["支柱の軸力"], "OK")
        self.assertEqual(st["作業床の積載"], "WARN")              # 1.5kN/m² × 1829² は 250kg/スパンを超える
        self.assertEqual(st["高さと短辺の比"], "OK")
        light = solve(live_kn_m2=0.6)
        self.assertEqual({c.item: c.status for c in light.checks}["作業床の積載"], "OK")
        tall = solve(corners_mm=[[0, 0], [12000, 0], [12000, 2500], [0, 2500]], deck_mm=12000)
        self.assertEqual({c.item: c.status for c in tall.checks}["高さと短辺の比"], "WARN")
        self.assertIn("転倒安定度", next(c.message for c in tall.checks if c.item == "高さと短辺の比"))
        # 転倒安定度 FS＝(b/2)/(0.025h) が 2.0 を割る細長い形は NG（指針の棚足場）
        slim = solve(corners_mm=[[0, 0], [12000, 0], [12000, 2200], [0, 2200]], deck_mm=20000)
        self.assertEqual({c.item: c.status for c in slim.checks}["高さと短辺の比"], "NG")
        heavy = solve(live_kn_m2=6.0)
        self.assertEqual({c.item: c.status for c in heavy.checks}["支柱の軸力"], "NG")
        self.assertFalse(heavy.ok)

    def test_quantity_and_report(self):
        r = solve()
        q = {(c, d, why): n for c, d, n, why in r.quantity}
        self.assertEqual(q[("ジャッキ", 0, "内部ステージのジャッキベース")], 7 * 7)
        decks = sum(n for c, d, n, why in r.quantity if c == "踏板")
        # 幅 1219 を 500×2 で埋め、残り 189 はすき間板。階段の升目は階段の通る幅（450×2＋100）を抜く（2026-10-29）
        self.assertEqual(decks, 6 * 6 * 2 - 2)
        self.assertTrue(any(c == "すき間板" for c, *_ in r.quantity))
        # 昇降ははしごでなく階段（利用者の指定 2026-10-29: ハシゴじゃなくて階段を使う）
        self.assertNotIn("はしご", {c for c, *_ in r.quantity})
        self.assertEqual(sum(n for c, _d, n, _w in r.quantity if c == "階段"), len(r.stair_flights))
        self.assertTrue(r.stair_flights)
        txt = stage_report(r)
        self.assertIn("## 検証", txt)
        self.assertIn("支柱の軸力", txt)
        p = stage_params(r)
        self.assertEqual(p["spanU"], "1829,1829,1829,1829,1829,1829")
        self.assertAlmostEqual(p["deckH"], 6.0)

    def test_deck_is_the_nearest_level(self):
        r = solve(deck_mm=4000)
        self.assertLessEqual(abs(r.deck_mm - 4000), 300)
        self.assertEqual(r.levels[-1], r.deck_mm)

    def test_not_a_rectangle(self):
        # 台形は長い辺から張った格子が範囲の外へはみ出すので止める（回した長方形は通す）
        with self.assertRaises(ValueError):
            solve(corners_mm=[[0, 0], [12000, 0], [9000, 8000], [3000, 8000]])
        import math
        c, s_ = math.cos(math.radians(30)), math.sin(math.radians(30))
        rot = [[x * c - y * s_, x * s_ + y * c] for x, y in RECT]
        self.assertAlmostEqual(solve(corners_mm=rot).length_u, solve().length_u)

    def test_too_small(self):
        with self.assertRaises(ValueError):
            solve(corners_mm=[[0, 0], [500, 0], [500, 500], [0, 500]])

    def test_guides_to_corners_and_part(self):
        from interior_stage_run import corners_of

        self.assertEqual(corners_of([(None, [((0.0, 0.0), (5.0, 3.0))])]), [[0.0, 0.0], [5.0, 0.0], [5.0, 3.0], [0.0, 3.0]])
        poly = [(None, [((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (4.0, 2.0)), ((4.0, 2.0), (0.0, 2.0)), ((0.0, 2.0), (0.0, 0.0))])]
        self.assertEqual(len(corners_of(poly)), 4)
        self.assertTrue((ROOT / "gdl" / "ashiba_stage.gsm").exists())
        d3 = (ROOT / "gdl" / "hsf" / "ashiba_stage" / "scripts" / "3d.gdl").read_text(encoding="utf-8")
        self.assertIn("最上段の全面の作業床", d3)
        self.assertNotIn(" LV ", d3)                          # 配列 lv と大文字小文字で衝突しない名前


if __name__ == "__main__":
    unittest.main()


class TestShoringStage(unittest.TestCase):
    """型枠支保工として使う内部ステージ（利用者の指定 2026-10-28: 型枠支保工で使う、内部足場はステージ）."""

    def shore(self, **kw):
        return solve(**{"deck_mm": 2800, "use": "支保工", "slab_mm": 200, "ceiling_mm": 4400, **kw})

    def test_design_load_is_rc_plus_form_plus_live(self):
        r = self.shore()
        self.assertEqual(r.use, "支保工")
        # 23.5×0.2＋0.39＋1.47（手引: 2400kg/m³・型枠 40kg/m²・積載 150kg/m²）
        self.assertAlmostEqual(r.design_kn_m2, 6.56, places=2)
        items = [c.item for c in r.checks]
        self.assertNotIn("支柱の軸力", items)          # 足場の軸力は支保工の軸力に置き換える
        self.assertIn("支保工の支柱の軸力", items)

    def test_spans_from_the_formwork_calc(self):
        # 支柱の間隔は型枠の計算（せき板・根太・大引）と支柱の軸力で決める（利用者の指定 2026-10-29: 型枠の計算を
        # しないとスパン決めれないよ、1800飛ばせないと思う）。スラブ 200 は大引 □100×50 が 1829 を飛ばせない
        st = lambda r: {c.item: c.status for c in r.checks}
        r = self.shore()
        self.assertLess(max(r.spans_u), 1829)
        self.assertEqual(r.form["spans"], (1524, 1219))
        self.assertEqual(st(r)["型枠（せき板・根太・大引）"], "OK")
        self.assertEqual(st(r)["支保工の支柱の軸力"], "OK")
        msg = next(c.message for c in r.checks if c.item == "型枠（せき板・根太・大引）")
        for part in ("せき板", "根太", "大引"):
            self.assertIn(part, msg)
        # 厚いスラブは間隔を詰める（スラブ 300 で短手 914）
        thick = self.shore(slab_mm=300, tie="両方向つなぎ材")
        self.assertLessEqual(max(thick.spans_v), 914)
        self.assertEqual(st(thick)["支保工の支柱の軸力"], "OK")
        # 強い大引（単管2本は弱い）を選ぶと間隔が変わる
        weak = self.shore(form={"obiki": "単管2本"})
        self.assertLess(weak.form["spans"][0] * weak.form["spans"][1], 1524 * 1219)
        q = {c: why for c, _d, _n, why in weak.quantity}
        self.assertIn("単管 φ48.6×2.4 2本", q["大引"])
        self.assertIn("根太", q)
        # 型枠の計算に通る定尺が無い（極端に厚いスラブ）ときは NG と案内
        none = self.shore(slab_mm=3000, tie="ブレース")
        if none.form["spans"] is None:
            self.assertEqual(st(none)["型枠（せき板・根太・大引）"], "NG")

    def test_deck_snaps_to_the_nearest_koma(self):
        # 天井から積み方を選び直しても、作業床は指定にいちばん近いコマの段（1800 の指定が 2465 になっていた）
        for d, c in ((1800, 3800), (1800, 4400), (2500, 5200)):
            r = self.shore(deck_mm=d, ceiling_mm=c)
            self.assertLessEqual(abs(r.deck_mm - d), 225, (d, c, r.deck_mm))
            lv = sorted(r.levels[1:] + r.upper_levels)
            self.assertTrue(all((x - r.deck_mm) % 450 == 0 for x in lv), lv)

    def test_uhead_jack_and_notification(self):
        r = self.shore()
        self.assertEqual(r.uhead_ext_mm, 4400 - 175 - r.top_mm)
        st = {c.item: c.status for c in r.checks}
        self.assertEqual(st["大引受けジャッキ"], "OK")
        self.assertEqual(st["設置届"], "WARN")             # 支柱高さ 3.5m 以上
        self.assertEqual(st["水平つなぎ"], "OK")
        self.assertNotIn("天井との取り合い", st)                 # 支保工は頭上の空きを見ない
        # 作業床は支柱の天端より下の段から選ぶので、手すり（＋900）が大引に当たる形は出ない
        for d in (2800, 3600, 4500):
            hi = self.shore(deck_mm=d)
            self.assertLessEqual(hi.deck_mm + 900, 4400 - 175 - 50)
        # 支柱の積み方を天井に合わせて選ぶ（繰出し 0〜350）
        # 4200 は大引受けジャッキだけでは届かず、足元のジャッキも繰り出す（270 以下）
        for ceil in (2900, 3500, 4200, 4250, 5200, 6100):
            r2 = self.shore(ceiling_mm=ceil)
            self.assertTrue(0 <= r2.uhead_ext_mm <= 350, (ceil, r2.uhead_ext_mm))
            self.assertLessEqual(r2.jack_mm, 270)
            self.assertEqual(r2.top_mm + r2.uhead_ext_mm, ceil - 175)
            lv = sorted(r2.levels + r2.upper_levels + [r2.top_mm])
            self.assertLessEqual(max(b - a for a, b in zip(lv, lv[1:])), 2000)    # 水平つなぎは 2m 以内ごと
        low = self.shore(ceiling_mm=1500)                  # 作業床より低い天井: どの積み方でも支柱が大引に当たる
        self.assertEqual({c.item: c.status for c in low.checks}["大引受けジャッキ"], "NG")

    def test_quantity_and_horizontal_load(self):
        r = self.shore()
        q = {name: n for name, _, n, _ in r.quantity}
        posts = (len(r.spans_u) + 1) * (len(r.spans_v) + 1)
        self.assertEqual(q["大引受けジャッキ"], posts)
        self.assertEqual(q["大引"], len(r.spans_v) + 1)
        h = next(c for c in r.checks if c.item == "支保工の水平荷重")
        self.assertIn("5.0%", h.message)
        # 足りない筋かいは数量にも（各層・各方向・交さ）
        self.assertEqual(h.status, "WARN")
        inner = [(d, n, why) for c, d, n, why in r.quantity if c == "筋交" and "内側の交さ筋かい" in why]
        self.assertEqual(len(inner), 2)
        self.assertTrue(all(n > 0 and n % 2 == 0 for _, n, _ in inner))
        # 部品にも同じ組数を渡して描く（数量だけで 3D に無かった。2026-10-29）
        self.assertEqual(stage_params(r)["inBrN"], r.inner_braces)
        self.assertGreater(r.inner_braces, 0)
        # 升目が足りないと組数を満たせない（幅 1スパンの細長い 40m・スラブ 1000）
        tight = solve(corners_mm=[[0, 0], [40000, 0], [40000, 2200], [0, 2200]], deck_mm=2800, use="支保工",
                      slab_mm=1000, ceiling_mm=4400)
        self.assertEqual({c.item: c.status for c in tight.checks}.get("支保工の筋かいの入る升目"), "NG")
        self.assertTrue(any("2段以上" in n for n in r.notes))
        self.assertTrue(any("型枠支保工の組立て等作業主任者" in n for n in r.notes))
        self.assertTrue(any("下の階のスラブ" in n and "kN" in n for n in r.notes))
        self.assertIn("型枠支保工", stage_report(r))
        # 支柱の高さ 3.5m 以上は設置届の下書き（ND1800 は承認第88-164号）
        rep = stage_report(r)
        self.assertIn("設置届（様式第20号）の記入の下書き", rep)
        self.assertIn("承認第88-164号", rep)
        self.assertIn("設計荷重の 5%", rep)
        self.assertNotIn("設置届（様式第20号）", stage_report(self.shore(ceiling_mm=3000)))   # 3.5m 未満
        # 部品: 支柱は大引の下まで、頂部に大引受けジャッキ
        p = stage_params(r)
        self.assertAlmostEqual(p["postTop"], r.top_mm / 1000.0)
        self.assertAlmostEqual(p["uheadExt"], r.uhead_ext_mm / 1000.0)
        self.assertEqual(stage_params(solve())["postTop"], 0.0)


class TestStairStage(unittest.TestCase):
    """階段の上に組む内部足場（利用者の指定 2026-10-28: 内部足場は階段でよく使う）."""

    def stair(self, **st):
        m = load_master("nikken_nd1800")
        item = {"name": "階段室", "corners_mm": [[0, 0], [6000, 0], [6000, 2800], [0, 2800]], "deck_mm": 3000,
                "stair": {"axis": "u", "from_mm": 800, "tread_mm": 250, "riser_mm": 180, "steps": 16, **st}}
        return solve_stage(item, m, load_capacities("nikken_nd1800"))

    def test_posts_shorten_by_the_step_and_jacks_take_the_rest(self):
        r = self.stair()
        koma = 450
        for f in r.stair_feet:
            # 支柱の下端（段＋敷板＋ジャッキ）が平らな床の支柱とコマでそろう
            bottom = f["z_mm"] + f["shim"] * 35 + f["jack_mm"]
            self.assertEqual((bottom - r.jack_mm) % koma, 0, f)
            self.assertEqual(bottom + sum(f["posts"]), r.top_mm)
            self.assertLessEqual(f["shim"], 2)
        flat = r.stair_feet[0]
        self.assertEqual(flat["z_mm"], 0)
        self.assertEqual(flat["posts"], r.posts)

    def test_quantity_counts_stair_posts_and_shims(self):
        r = self.stair()
        q = r.quantity
        n_posts = (len(r.spans_u) + 1) * (len(r.spans_v) + 1)
        posts = [(d, n) for c, d, n, _ in q if c == "支柱"]
        per_row = len(r.spans_v) + 1
        want = sum(len(f["posts"]) for f in r.stair_feet) * per_row
        self.assertEqual(sum(n for _, n in posts), want)
        self.assertEqual(sum(n for c, _, n, _ in q if c == "ジャッキ"), n_posts)
        shims = sum(f["shim"] for f in r.stair_feet) * per_row
        self.assertEqual(sum(n for c, _, n, _ in q if c == "敷板"), shims)

    def test_checks_flag_nosing_and_shims(self):
        r = self.stair()
        st = {c.item: c.status for c in r.checks}
        self.assertIn(st["階段の上の支柱"], ("OK", "WARN"))
        self.assertEqual(st.get("踏面の端"), "WARN")          # 2列目の支柱が蹴上げから 36mm
        self.assertTrue(any("根がらみは段ごと" in n for n in r.notes))
        self.assertIn("階段の上の支柱（列ごと）", stage_report(r))
        moved = self.stair(from_mm=750)
        self.assertNotIn("踏面の端", {c.item for c in moved.checks})
        # 作業床 3000→3125 は踊り場（2880）の列の支柱の下端より低く、布材が掛からない
        self.assertEqual(st["作業床と踊り場"], "NG")

    def test_base_ties_per_step_and_part_params(self):
        m = load_master("nikken_nd1800")
        item = {"name": "階段室", "corners_mm": [[0, 0], [6000, 0], [6000, 2800], [0, 2800]], "deck_mm": 4500,
                "stair": {"axis": "u", "from_mm": 750, "tread_mm": 250, "riser_mm": 180, "steps": 16}}
        r = solve_stage(item, m, load_capacities("nikken_nd1800"))
        self.assertNotIn("作業床と踊り場", {c.item for c in r.checks})
        koma = 450
        for f in r.stair_feet:
            bottom = f["z_mm"] + f["shim"] * 35 + f["jack_mm"]
            first = f["negarami_mm"] or min(h for h in r.levels if h > bottom + 100)
            self.assertLessEqual(first - bottom, 600, f)               # 下端から 600 以内に根がらみ
            if f["negarami_mm"]:
                self.assertEqual((f["negarami_mm"] - r.levels[0]) % koma, 0)   # コマの位置
        self.assertTrue(any(why == "階段の上の段ごとの根がらみ" for _, _, _, why in r.quantity))
        # 昇降は建物の階段から（足元が建物の段で階段枠が据わらない）。上の踊り場 2880 と作業床 4500 の段差が大きい
        self.assertEqual(r.access, "建物の階段")
        self.assertFalse(r.stair_flights)
        self.assertEqual({c.item: c.status for c in r.checks}["昇降（建物の階段）"], "WARN")
        p = stage_params(r)
        self.assertEqual(len(p["footZ"].split(",")), len(r.stair_feet))
        self.assertEqual(len(p["footNeg"].split(",")), len(r.stair_feet))


class TestShaftStage(unittest.TestCase):
    """EVシャフトの中に組む内部足場（利用者の指定 2026-10-28: 内部足場はステージとEV部分）."""

    def shaft(self, **kw):
        m = load_master("nikken_nd1800")
        item = {"name": "EV1", "corners_mm": [[0, 0], [2400, 0], [2400, 2200], [0, 2200]], "deck_mm": 16000,
                "use": "EVシャフト", "floors_mm": [1500, 5000, 8500, 12000, 15500], **kw}
        return solve_stage(item, m, load_capacities("nikken_nd1800"))

    def test_decks_at_each_layer_and_no_perimeter_guard(self):
        r = self.shaft()
        self.assertEqual(r.use, "EVシャフト")
        # 作業床は各層（層の高さごと。利用者の指定 2026-10-29: 各層に作業床＋ハッチ）。各階の床は壁つなぎの段に使う
        lv = sorted(r.deck_levels + [r.deck_mm])
        self.assertTrue(all(h in r.levels for h in lv))             # 布材の段にもある
        self.assertTrue(all(b - a == 1800 for a, b in zip(lv[1:], lv[2:])))
        self.assertFalse(r.guard)                                   # 壁との隙間 30cm 以下
        q = {(c, why) for c, _, _, why in r.quantity}
        self.assertFalse(any(c == "幅木" for c, _ in q))
        n = {c: sum(k for cc, _, k, _ in r.quantity if cc == c) for c in ("壁つなぎ", "はしご", "階段")}
        self.assertEqual(n["壁つなぎ"], 4 * 5)
        self.assertEqual(n["はしご"], 0)
        self.assertEqual(n["階段"], 0)                              # 昇降はハッチ付布板
        p = stage_params(r)
        self.assertFalse(p["guardOn"])
        self.assertEqual(len(p["deckList"].split(",")), len(r.deck_levels))

    def test_hatch_access_every_layer(self):
        # 昇降はハッチ付布板（梯子内蔵）、作業床は各層（利用者の指定 2026-10-29: 階段ではなくハッチつきアンチ／各層に作業床＋ハッチ）
        r = self.shaft()
        self.assertEqual(r.access, "ハッチ")
        self.assertFalse(r.stair_flights)
        q = {c: sum(n for cc, _d, n, _w in r.quantity if cc == c) for c in ("踊り場", "階段", "はしご")}
        self.assertEqual(q["階段"], 0)
        self.assertEqual(q["はしご"], 0)
        self.assertEqual(q["踊り場"], len([h for h in r.hatch_levels if h > 650]))
        lv = [h for h in r.hatch_levels if h > 650]
        self.assertTrue(all(b - a == 1800 for a, b in zip(lv, lv[1:])))       # 層ごと
        self.assertEqual(set(r.deck_levels + [r.deck_mm]), set(r.hatch_levels))  # 各層に作業床
        p = stage_params(r)
        self.assertEqual(p["stFl"], "")
        self.assertFalse(p["ladOn"])
        self.assertEqual(len(p["hatchZ"].split(",")), len(r.hatch_levels))

    def test_checks_and_notes(self):
        r = self.shaft()
        st = {c.item: c.status for c in r.checks}
        self.assertNotIn("高さと短辺の比", st)
        self.assertEqual(st["壁つなぎ"], "OK")
        self.assertTrue(any("519条" in n for n in r.notes))
        # 最初の段が階段枠に合わないとき、シャフトは作業床でなく最下段で調整する
        acc = next((c for c in r.checks if c.item == "昇降の階段"), None)
        if acc is not None and acc.status == "WARN":
            self.assertIn("ピットの床", acc.message)
            self.assertNotIn("作業床を", acc.message)
        self.assertTrue(any("足場の組立て等作業主任者" in n for n in r.notes))      # 高さ 5m 以上
        sparse = self.shaft(floors_mm=[1500, 9000])                # 階の間が 5m を超える
        self.assertEqual({c.item: c.status for c in sparse.checks}["壁つなぎ"], "WARN")
        wide = self.shaft(corners_mm=[[0, 0], [2700, 0], [2700, 2200], [0, 2200]])
        self.assertLessEqual(wide.wall_gap_mm, 300)                 # シャフトは壁とのすき間 30cm 以下に割る
        self.assertFalse(wide.guard)
        self.assertIn("EVシャフト", stage_report(r))


class TestStairAccess(unittest.TestCase):
    """内部ステージの昇降は階段（利用者の指定 2026-10-29: ハシゴじゃなくて階段を使う）."""

    def test_first_flight_from_the_ground(self):
        ok = solve(deck_mm=3800)                    # 地面から 2000 の段・3800 の作業床で 2台
        st = {c.item: c.status for c in ok.checks}
        self.assertEqual(st["昇降の階段"], "OK")
        self.assertEqual(ok.stair_flights[0][0], 0)
        self.assertEqual(len(ok.stair_flights), 2)
        off = solve(deck_mm=3000)                   # 最初の段 1325 は階段枠 1800 に合わない
        msg = next(c for c in off.checks if c.item == "昇降の階段")
        self.assertEqual(msg.status, "WARN")
        self.assertIn("1800", msg.message)
        lad = solve(deck_mm=3800, access="はしご")    # はしごを選んだときだけはしご
        self.assertFalse(lad.stair_flights)
        self.assertIn("はしご", {c for c, *_ in lad.quantity})
        p = stage_params(ok)
        self.assertEqual(p["stFl"], "0,2000,2000,3800")


class TestFrameStage(unittest.TestCase):
    def test_frame_series_uses_frame_widths_and_frames(self):
        # 枠組は短手を建枠の幅で割り、建枠・交差筋かいで数える（短手 1829・「支柱」で数えていた。2026-10-29）
        m = load_master("waku")
        r = solve_stage({"name": "枠", "corners_mm": RECT, "deck_mm": 3500}, m)
        self.assertTrue(set(r.spans_v) <= set(m.frame_widths()))
        cats = {c for c, *_ in r.quantity}
        self.assertIn("建枠", cats)
        self.assertNotIn("支柱", cats)
        nu, nv = len(r.spans_u), len(r.spans_v)
        self.assertEqual(sum(n for c, _d, n, _w in r.quantity if c == "建枠"), len(r.posts) * (nu + 1) * nv)


class TestStageGdlNames(unittest.TestCase):
    def test_arrays_do_not_clash_with_scalars(self):
        # GDL は名前の大文字小文字を区別しない。配列 hdL[] と布材の緊結部の長さ hdL が同じ名前で 3D が真っ白になった
        # （2026-10-29 ハッチ付布板）
        import re

        for f in ("3d.gdl", "2d.gdl"):
            body = (ROOT / "gdl" / "hsf" / "ashiba_stage" / "scripts" / f).read_text(encoding="utf-8")
            arrays = {n.lower() for d in re.findall(r"^\s*dim\s+(.+)$", body, re.M) for n in re.findall(r"(\w+)\[", d)}
            scalars = {n.lower() for n in re.findall(r"^\s*(\w+)\s*=", body, re.M)}
            with self.subTest(script=f):
                self.assertFalse(arrays & scalars, arrays & scalars)


class TestStagePartParams(unittest.TestCase):
    """配置の時に渡すパラメータが部品 ashiba_stage にあって型が合う（実機で型が違うと設定が弾かれる。2026-10-28 guardOn）."""

    def test_every_param_exists_with_the_right_type(self):
        import re

        xml = (ROOT / "gdl" / "hsf" / "ashiba_stage" / "paramlist.xml").read_text(encoding="utf-8")
        kinds = dict((n, k) for k, n in re.findall(r'<(\w+) Name="(\w+)">', xml))
        m = load_master("nikken_nd1800")
        cases = [solve(), solve(deck_mm=2800, use="支保工", slab_mm=200, ceiling_mm=4400),
                 solve_stage({"name": "EV", "corners_mm": [[0, 0], [2400, 0], [2400, 2200], [0, 2200]], "deck_mm": 9000,
                              "use": "EVシャフト", "floors_mm": [1500, 5000]}, m),
                 solve_stage({"name": "階段", "corners_mm": [[0, 0], [6000, 0], [6000, 2800], [0, 2800]], "deck_mm": 4500,
                              "stair": {"axis": "u", "from_mm": 750, "tread_mm": 250, "riser_mm": 180, "steps": 16}}, m)]
        want = {"Boolean": bool, "Integer": int, "Length": float, "RealNum": float, "Angle": float, "String": str}
        for r in cases:
            # master を渡すと本体の足場と同じ部材の作り（支柱の径・コマ・足場の種類・布板の幅。2026-10-29）
            p = stage_params(r, master=m)
            for key in ("postDia", "komaP", "sysKind", "jackExt", "dkWs"):
                self.assertIn(key, p)
            for k, v in p.items():
                with self.subTest(use=r.use, param=k):
                    self.assertIn(k, kinds)
                    t = want.get(kinds[k])
                    if t is bool:
                        self.assertIsInstance(v, bool)
                    elif t is int:
                        self.assertTrue(isinstance(v, int) and not isinstance(v, bool))
                    elif t is float:
                        self.assertIsInstance(v, (int, float))
                    elif t is str:
                        self.assertIsInstance(v, str)


class TestAllSeries(unittest.TestCase):
    """全系列（くさび・枠組・単管）× 足場・支保工・EVシャフト・階段で解ける（2026-10-29 の総当たりで見つけた3件）."""

    CASES = {
        "足場": {"corners_mm": RECT, "deck_mm": 4000},
        "支保工": {"corners_mm": RECT, "deck_mm": 1800, "use": "支保工", "slab_mm": 200, "ceiling_mm": 4400},
        "EV": {"corners_mm": [[0, 0], [2400, 0], [2400, 2200], [0, 2200]], "deck_mm": 12000, "use": "EVシャフト",
               "floors_mm": [1500, 5000, 8500]},
        "階段": {"corners_mm": [[0, 0], [6000, 0], [6000, 2800], [0, 2800]], "deck_mm": 4500,
                 "stair": {"axis": "u", "from_mm": 750, "tread_mm": 250, "riser_mm": 180, "steps": 16}},
    }

    def test_every_series_and_use(self):
        from ashiba.master import SERIES_CONST

        for sid in SERIES_CONST:
            m, caps = load_master(sid), load_capacities(sid)
            for name, it in self.CASES.items():
                with self.subTest(series=sid, case=name):
                    r = solve_stage({"name": name, **it}, m, caps)       # 単管の支保工で例外になっていた
                    stage_params(r)
                    st = {c.item: c.status for c in r.checks}
                    if name == "EV":
                        # シャフトは外周の支柱だけ（内側の支柱の受け持ちで数えて NG になっていた）。各層に作業床を張る
                        # ので、許容の小さい系列（信和 A 6.86kN）は NG になってよい
                        msg = next(c.message for c in r.checks if c.item == "支柱の軸力")
                        self.assertRegex(msg, "角の支柱|端の支柱")
                        if sid == "nikken_nd1800":
                            self.assertEqual(st["支柱の軸力"], "OK")
                    if name == "階段":
                        # 枠組・単管でも段ごとの積み方が見つかる（コマ 450 を仮定して NG になっていた）
                        # アルバトロスの中空ジャッキは調節長 255 だけ（スギコ カタログvol.7 p043）。調整カラー 60・150・300 で
                        # 合わせる（入れる前は1列が受けきれず NG だった）
                        self.assertNotEqual(st["階段の上の支柱"], "NG")
                        self.assertTrue(all(f["posts"] for f in r.stair_feet))


class TestFormworkCalc(unittest.TestCase):
    def test_matches_the_kkl_worked_example(self):
        # KKL 型枠支保工強度計算書の例（スラブ 400・合板 12・根太 角パイプ 60 @300・大引 @1219）: せき板 σ0.70kN/cm²・
        # δ0.14cm、根太 σ8.9kN/cm²（単純梁）
        from ashiba.formwork import check

        sk, nd, _ob = check(15.0, 10.3, 1829, 1219, neda="角パイプ60")
        self.assertAlmostEqual(sk.sigma / 10.0, 0.70, places=2)
        self.assertAlmostEqual(sk.deflection_mm / 10.0, 0.14, places=2)
        self.assertAlmostEqual(nd.sigma / 10.0, 8.9, delta=0.5)
