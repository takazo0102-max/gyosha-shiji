"""仮囲い（利用者の指定 2026-11-01: 仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ。
同日: ゲート 仮囲いに必要な部材リサーチして → 全部入れて 3Dも詳細度上げて。日建リース工業 仮設資材カタログ Vol.10）."""

from __future__ import annotations

import math
import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.hoarding import (FLAT_OFF_MM, PANEL_OFF_MM, Segment, gate_kind, gate_layout, hoarding_plan, inset_polygon,
                             offset_polyline, outside_is_right, panel_off, part_params, pile_ref, polyline_layout, rail_heights, PANELS, report, split_gates,
                             wind_limit)

PENTAGON = [(-3000.0, -500.0), (12000.0, -500.0), (15000.0, 4000.0), (11000.0, 10000.0), (-3000.0, 10000.0)]


def q(p):
    return {n: k for n, k, _x in p.quantity}


def st(p):
    return {c.item: c.status for c in p.checks}


def wv(p):
    return {w.item: w for w in p.wind}


class TestStraight(unittest.TestCase):
    def test_catalog_standard_three_metre(self):
        """日建の標準施工図（SSK300）: 支柱 1.8m ごと・パネルの下端は地盤・横地は取付穴の 150・1,500・2,850・控えは 2,100 から後ろ 1,550."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (10800.0, 0.0)))
        self.assertEqual(p.posts, [0.0, 1800.0, 3600.0, 5400.0, 7200.0, 9000.0, 10800.0])
        self.assertEqual(p.rails, [150.0, 1500.0, 2850.0])
        self.assertEqual((p.top, p.brace_h, p.brace_back, p.root), (3000.0, 2100.0, 1550.0, 150.0))
        self.assertAlmostEqual(p.brace_len, 2491.0, delta=1.0)                  # 日建の座屈長さ 2.491m
        self.assertEqual(q(p)["安全鋼板 SSK300 H3000"], 20)                       # 10800 / 540
        self.assertEqual(q(p)["フックボルト SSKFB"], 120)
        self.assertEqual(q(p)["単管 5.0m（横地）"], 9)
        self.assertEqual(q(p)["直交クランプ ARC1"], 7 * 3 + 7 * 2)                  # 支柱と横地・根がらみの両端
        self.assertEqual(q(p)["自在クランプ ARC2"], 7 * 2)                          # 控えの上と足
        self.assertEqual(q(p)["単管 2.5m（控え）"], 7)                              # 日建 VIC の部材表も控えパイプ 2.5M
        self.assertEqual(q(p)["単管 2.0m（根がらみ）"], 7)
        self.assertEqual(q(p)["打込みパイプ くい丸1.5M（控えの足）"], 7)
        self.assertEqual((st(p)["仮囲いの高さ"], st(p)["支柱の間隔"], st(p)["風: この組で持つ風速"]), ("OK", "OK", "OK"))

    def test_catalog_wind_example(self):
        """日建 仮囲安全鋼板の検討（p453〜456。V=30m/s・H3m・控え @1.8m・N値 20）の数字を再現する."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (10800.0, 0.0)), wind_ms=30.0)
        w = wv(p)
        for item, val in (("パネル", 4002.5), ("横地", 10459.0), ("支柱", 21286.0), ("控えの座屈", 1263.0),
                          ("控えのクランプ", 4398.2), ("杭の引抜き", 3443.0)):
            self.assertAlmostEqual(w[item].value / val, 1.0, delta=0.005, msg=item)
        self.assertAlmostEqual(w["控えの座屈"].allow / 4248.0, 1.0, delta=0.005)
        self.assertAlmostEqual(w["控えのクランプ"].allow, 4459.0)
        self.assertAlmostEqual(w["杭の引抜き"].allow / 3592.0, 1.0, delta=0.005)
        self.assertTrue(all(c.status == "OK" for c in p.checks if c.item.startswith("風")))
        self.assertAlmostEqual(wind_limit(p), 30.2, delta=0.2)                  # 控えのクランプで決まる

    def test_brace_every_other_post_fails_the_wind(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (10800.0, 0.0)), brace_every=2)
        self.assertEqual(len(p.braces), 4)
        self.assertEqual(st(p)["風: 支柱"], "NG")                                 # 控え1本で2スパン分を持つ
        self.assertEqual(st(p)["風: 控えのクランプ"], "WARN")
        self.assertLess(wind_limit(p), 25.0)
        self.assertEqual(st(hoarding_plan("a", Segment((0.0, 0.0), (10800.0, 0.0)), soil_n=5.0))["風: 杭の引抜き"], "WARN")

    def test_heights_rows_and_bolts(self):
        """安全鋼板の高さ 2,000・2,300・3,000・4,000（取付穴の段）、フックボルトは段ごとに 2."""
        self.assertEqual(rail_heights(PANELS["安全鋼板"], 4000.0, 0.0), [150.0, 1350.0, 2650.0, 3850.0])
        self.assertEqual(rail_heights(PANELS["安全鋼板"], 2300.0, 0.0), [150.0, 1150.0, 2150.0])
        self.assertEqual(rail_heights(PANELS["安全鋼板"], 2000.0, 0.0), [150.0, 1850.0])
        self.assertEqual(rail_heights(PANELS["フラットパネル"], 3000.0, 0.0), [150.0, 1500.0, 2850.0])
        p = hoarding_plan("a", Segment((0.0, 0.0), (5400.0, 0.0)), height=4000.0)
        self.assertEqual(q(p)["フックボルト SSKFB"], 8 * q(p)["安全鋼板 SSK400 H4000"])
        self.assertEqual(p.brace_h, 3100.0)
        self.assertIn("単管 4.0m（控え）", q(p))
        two = hoarding_plan("a", Segment((0.0, 0.0), (5400.0, 0.0)), height=2000.0)
        self.assertEqual(q(two)["フックボルト SSKFB"], 4 * q(two)["安全鋼板 SSK200 H2000"])

    def test_punching_and_bottom(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (5400.0, 0.0)), panel="安全鋼板（パンチング）", bottom=200.0)
        self.assertIn("安全鋼板（パンチング） SSKP300 H3000", q(p))
        self.assertEqual((p.rails, p.top, part_params(p)["kkType"]), ([350.0, 1700.0, 3050.0], 3200.0, 5))
        self.assertEqual(st(p)["パネルの下端"], "OK")
        embed = hoarding_plan("a", Segment((0.0, 0.0), (5400.0, 0.0)), bottom=-100.0)
        self.assertEqual(embed.top, 2900.0)
        self.assertEqual(part_params(embed)["lift"], -0.1)

    def test_flat_panel_adjust_and_fittings(self):
        """フラットパネル（VIC）: 半端は調整Nパネル（40〜440）、C型金具は1枚に 6、開き止め金具は 40スパンに 3."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (5230.0, 0.0)), panel="フラットパネル")
        self.assertEqual((q(p)["フラットパネル VIC300 H3000"], q(p)["調整Nパネル VICN300（有効幅 40〜440）"]), (10, 1))
        self.assertEqual(q(p)["C型金具（VIC-Cカナグ）"], 11 * 6)
        self.assertEqual(q(p)["VIC開き止め金具"], 1)
        self.assertEqual(q(hoarding_plan("a", Segment((0.0, 0.0), (5020.0, 0.0)), panel="フラットパネル"))
                         ["（半端 40 未満は重ねで吸収）"], 1)
        low = hoarding_plan("a", Segment((0.0, 0.0), (5000.0, 0.0)), height=1500.0)
        self.assertEqual(st(low)["仮囲いの高さ"], "NG")                          # 1.8m 以上（施行令 136条の2の20）

    def test_flat_panel_corner(self):
        """フラットパネルの角は自在コーナーパネル（240＋240）。パネルの数から 240 を除く."""
        segs = polyline_layout([(0.0, 0.0), (5400.0, 0.0), (5400.0, 5400.0)], off=FLAT_OFF_MM)
        p = hoarding_plan("a", segs[0], panel="フラットパネル")
        self.assertEqual(p.corners, (False, True))
        self.assertIn("自在コーナーパネル VICC300（240＋240）", q(p))
        self.assertEqual(part_params(p)["kkCor"], "0,1")
        self.assertEqual(part_params(hoarding_plan("b", segs[1], panel="フラットパネル"))["kkCor"], "1,0")
        self.assertAlmostEqual(segs[0].ext1, FLAT_OFF_MM)                       # 直角の出隅は裏の面まで延ばす

    def test_foundations(self):
        s = Segment((0.0, 0.0), (7200.0, 0.0))
        r = hoarding_plan("a", s, foundation="根巻き")
        self.assertEqual(q(r)["根巻きコンクリート □300×400"], 5 + 5)
        self.assertIn("根巻きの引抜き", wv(r))
        h = hoarding_plan("a", s, foundation="H形鋼")
        self.assertEqual((h.brace_back, h.root), (1700.0, 450.0))               # 後ろの列の H形鋼に落とす
        self.assertEqual((h.lift, h.rails[0]), (300.0, 450.0))                 # パネルの下端は H形鋼（H-300）の上
        self.assertEqual(q(h)["キャッチクランプ（H形鋼用）"], (5 + 5) * 2)
        # H-300 の自重だけでは 25m/s で起きるので、ウェイト □600（500kg）を前の列の内・後ろの列の手前に1スパン1つずつ足す
        # （利用者の指定 2026-11-01: H形鋼の転倒はウェイトを足して直して）
        self.assertEqual((h.weights, st(h)["風: H形鋼の転倒"]), ((1, 1), "OK"))
        self.assertEqual(q(h)["コンクリートウェイト □600（約 500kg）"], 2 * 4)
        self.assertEqual(part_params(h)["wtN"], "1,1")
        self.assertGreaterEqual(wind_limit(h), 25.0)
        self.assertEqual(hoarding_plan("a", s, foundation="H形鋼", wind_ms=15.0, height=2000.0).weights, (0, 0))
        self.assertEqual(part_params(h)["kkFound"], 3)
        sq = polyline_layout([(0.0, 0.0), (7200.0, 0.0), (7200.0, 7200.0)], outside_right=False)   # 中が右・外が左回り
        self.assertEqual(part_params(hoarding_plan("a", sq[0], foundation="H形鋼"))["hbX"], "0,8900")   # 入隅の側は延ばす
        sq2 = polyline_layout([(0.0, 0.0), (7200.0, 0.0), (7200.0, 7200.0)])
        self.assertEqual(part_params(hoarding_plan("a", sq2[0], foundation="H形鋼"))["hbX"], "0,5500")  # 中の角は縮める
        a = hoarding_plan("a", s, foundation="アンカー")
        self.assertEqual((q(a)["固定ベース PKB（□120・4-φ11）"], q(a)["ベースアンカー NBAK（□140 t9・φ48.6×3.2 H309）"]), (5, 5))
        self.assertEqual(st(a)["アンカーの引抜き"], "OK")
        self.assertEqual((part_params(a)["kkFound"], part_params(a)["brRt"]), (4, 0.2))
        self.assertNotIn("単管 2.0m（根がらみ）", q(a))


class TestEarthRetaining(unittest.TestCase):
    """山留めから取る（利用者の指定 2026-11-01: 山留めからとるパターンあるよね）: 親杭を継ぎ足して支柱に、控えなし."""

    def test_piles_as_posts(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (10000.0, 0.0)), foundation="親杭支柱")
        self.assertEqual(p.posts, [0.0, 1200.0, 2400.0, 3600.0, 4800.0, 6000.0, 7200.0, 8400.0, 9600.0, 10000.0])
        self.assertEqual(p.braces, [])
        self.assertEqual(q(p)["H形鋼 H-300（親杭の継ぎ足し L=3150）"], 10)
        self.assertEqual(q(p)["キャッチクランプ（H形鋼用・横地）"], 10 * 3)
        self.assertNotIn("単管 2.5m（控え）", q(p))
        self.assertNotIn("直交クランプ ARC1", q(p))
        self.assertEqual(st(p)["風: 親杭の継ぎ足し"], "OK")
        self.assertEqual(st(p)["親杭への風の曲げ"], "WARN")                       # 山留めの設計者に確かめる
        prm = part_params(p)
        self.assertEqual((prm["kkFound"], prm["brX"], prm["pileW"]), (5, "", 0.3))

    def test_pile_pitch_multiple(self):
        """支柱は親杭の間隔の倍数で 1,800 以内（@900 なら2本ごと）。継ぎ足しは親杭の天端から."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (9000.0, 0.0)), foundation="親杭支柱", pile="H-250", pile_pitch=900.0,
                          pile_top=-500.0)
        self.assertEqual((p.post_step, p.posts[:3]), (1800.0, [0.0, 1800.0, 3600.0]))
        self.assertIn("H形鋼 H-250（親杭の継ぎ足し L=3650）", q(p))
        self.assertEqual(part_params(p)["pileZ"], -0.5)

    def test_panel_offset(self):
        self.assertAlmostEqual(panel_off("安全鋼板", "親杭支柱") - panel_off("安全鋼板"), 150.0 + 24.3 - 48.6)


class TestBracesOnEarthRetaining(unittest.TestCase):
    """控えだけ山留めで取る（利用者の指定 2026-11-01: 控えだけ 山留めで取るってこと）: 支柱は単管の打込み、控えの足は親杭に."""

    def test_braces_land_on_piles(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (10000.0, 0.0)), foundation="山留め", wall_dist=1200.0, pile_x0=300.0)
        self.assertEqual(p.foundation, "山留め控え")                              # 「山留め」はこちら
        self.assertEqual(p.posts, [0.0, 1500.0, 2700.0, 3900.0, 5100.0, 6300.0, 7500.0, 8700.0, 10000.0])
        self.assertEqual([p.posts[k] for k in p.braces], [1500.0, 2700.0, 3900.0, 5100.0, 6300.0, 7500.0, 8700.0])
        self.assertEqual(p.brace_back, round(1200.0 + 150.0 + 24.3))             # 親杭の根切りの側のフランジの単管の立て
        self.assertEqual(q(p)["単管 1.0m（控えの足。親杭の根切りの側のフランジに立てる）"], 7)
        self.assertEqual(q(p)["キャッチクランプ（H形鋼用・控えの足を親杭に）"], 14)
        self.assertIn("単管 4.5m（支柱）", q(p))
        self.assertNotIn("打込みパイプ くい丸1.5M（控えの足）", q(p))
        self.assertEqual((st(p)["控えの足（山留め）"], st(p)["親杭への控えの力"]), ("OK", "WARN"))
        self.assertIn("風: 控えの足のキャッチクランプ", st(p))
        self.assertEqual(part_params(p)["kkFound"], 6)
        near = hoarding_plan("a", Segment((0.0, 0.0), (6000.0, 0.0)), foundation="山留め控え", wall_dist=300.0)
        self.assertEqual(st(near)["控えの足（山留め）"], "WARN")                   # 山留めが近すぎて控えが立つ

    def test_wall_distance_and_pile_grid(self):
        """仮囲いの線と山留め（壁の芯の線）を選ぶと、距離と親杭の位置を壁から測る。壁だけなら地山の側へ寄せた線に."""
        walls = [((-200.0, 1500.0), (20000.0, 1500.0))]
        self.assertEqual(pile_ref(Segment((0.0, 0.0), (12000.0, 0.0)), walls, 1200.0), (1500.0, 1000.0))
        self.assertEqual(pile_ref(Segment((0.0, 0.0), (12000.0, 0.0)), []), (1000.0, 0.0))
        sq = [(0.0, 0.0), (12000.0, 0.0), (12000.0, 7000.0), (0.0, 7000.0)]          # 反時計回り＝右が外（地山）
        out = offset_polyline(sq, 1000.0, closed=True)
        self.assertEqual([tuple(round(v) for v in pt) for pt in out], [(-1000, -1000), (13000, -1000), (13000, 8000), (-1000, 8000)])
        self.assertEqual(offset_polyline([(0.0, 0.0), (5000.0, 0.0)], 500.0), [(0.0, -500.0), (5000.0, -500.0)])


class TestGates(unittest.TestCase):
    def test_caster_gate_weights_match_catalog(self):
        """日建 キャスターゲートの部材数量表（p405・407・409）から積んだ重さが、カタログのセットの重さと合う."""
        for width, kind, code, kg in ((900.0, "キャスター", "CG09NN", 37.5), (5400.0, "キャスター", "CG54NN", 182.5),
                                      (8100.0, "キャスター", "CG81NN", 274.5), (7200.0, "キャスター両開き", "CG72NW", 248.0),
                                      (16200.0, "キャスター", "CG162NW", 548.0), (5400.0, "パネルキャスター", "PCG54NN", 231.7),
                                      (12600.0, "パネルキャスター", "PCG126NW", 544.8), (5400.0, "ローキャスター", "CG54SN", 144.5),
                                      (9000.0, "ローキャスター両開き", "CG90SW", 248.0)):
            lay = gate_layout(width, kind)
            self.assertEqual(lay.set_code, code)
            self.assertAlmostEqual(lay.kg, kg, places=1, msg=code)

    def test_folded_gate_leaves_clear_width(self):
        """畳むとユニット1つで 260、側支柱・中央支柱で 90×2 が間口に残る."""
        self.assertEqual(gate_layout(5400.0, "キャスター").clear, 5400.0 - (6 * 260.0 + 180.0))
        dbl = gate_layout(7200.0, "キャスター:両開き")
        self.assertEqual((dbl.leaves, dbl.clear), ((4, 4), 7200.0 - 2 * (4 * 260.0 + 180.0)))
        self.assertEqual(gate_layout(2700.0, "キャスター両開き").leaves, (0, 3))     # 両開きは 3.6m（4ユニット）から
        self.assertEqual(gate_layout(9900.0, "キャスター").leaves, (5, 6))         # 片開きは 8.1m まで。大きい方が終わりの側

    def test_gate_kinds(self):
        self.assertEqual(gate_kind("キャスター両開き"), ("キャスター", True))
        self.assertEqual(gate_kind("ジャバラ"), ("キャスター", None))
        with self.assertRaises(ValueError):
            gate_kind("シャッター")

    def test_gate_cuts_panels(self):
        p = hoarding_plan("a", Segment((0.0, 0.0), (15000.0, 0.0)), gates=[(4000.0, 5400.0, "キャスター")])
        self.assertEqual(p.runs, [(0.0, 4000.0), (9400.0, 15000.0)])
        self.assertIn(4000.0, p.posts)
        self.assertIn(9400.0, p.posts)
        self.assertFalse(any(4000.0 < x < 9400.0 for x in p.posts))
        self.assertEqual((st(p)["支柱の間隔"], st(p)["出入口"], st(p)["ゲートの通れる幅"]), ("OK", "OK", "OK"))
        self.assertEqual(q(p)["  単スパン CG09A"], 6)
        prm = part_params(p)
        self.assertEqual((prm["gateX"], prm["gateK"], prm["gateN"]), ("4000,9400", "2", "0,6"))
        self.assertNotIn("5800", prm["brX"].split(","))
        narrow = hoarding_plan("a", Segment((0.0, 0.0), (15000.0, 0.0)), gates=[(4000.0, 3600.0, "パネルキャスター")])
        self.assertEqual(st(narrow)["ゲートの通れる幅"], "WARN")                   # 開けても 2,380
        self.assertEqual(part_params(narrow)["gateK"], "1")

    def test_doors(self):
        """ドアは VICD200（W500・扉 413）、間口 900 以上はワイドドア VICDW200（W1,000・扉 910）。上に調整パネル VIC100."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (9000.0, 0.0)), gates=[(2000.0, 600.0, "ドア"), (5000.0, 1000.0, "ドア")])
        self.assertEqual([(a, b) for a, b, _k in p.gates], [(2000.0, 2500.0), (5000.0, 6000.0)])
        self.assertEqual(part_params(p)["gateK"], "3,5")
        self.assertEqual(q(p)["ドアパネル VICD200"], 1)
        self.assertEqual(q(p)["ワイドドアパネル VICDW200"], 1)
        door = gate_layout(1000.0, "ワイドドア")
        self.assertEqual({a: n for a, n, _w in door.parts}["ドアパネル用調整パネル VIC100"], 2)
        self.assertNotIn("ドアパネル用調整パネル VIC100", {a for a, _n, _w in gate_layout(500.0, "ドア", top=2000.0).parts})


class TestDiagonal(unittest.TestCase):
    def test_layout_shares_corner_posts_and_mitres(self):
        """斜めの辺: 区間ごとに向きを持ち、角の支柱は前の辺と共有、パネルは角の二等分線まで延ばす."""
        segs = polyline_layout(PENTAGON, closed=True, outside_right=outside_is_right(PENTAGON, (5000.0, 4000.0)))
        self.assertEqual(len(segs), 5)
        self.assertAlmostEqual(segs[1].angle, math.degrees(math.atan2(4500, 3000)))
        self.assertFalse(any(s.post0 for s in segs))                            # 閉じた形は角の支柱を前の辺が立てる
        self.assertAlmostEqual(segs[0].ext1, PANEL_OFF_MM * math.tan(math.radians(segs[0].turn1) / 2))
        self.assertAlmostEqual(segs[0].ext1, segs[1].ext0)
        p = hoarding_plan("b", segs[1])
        self.assertNotIn(0.0, p.posts)
        self.assertEqual(p.runs[0][0], -segs[1].ext0)
        self.assertEqual(q(p)["自在クランプ ARC2"], len(p.braces) * 2 + 2 * 3)     # 直交しない角の横地にも

    def test_open_line_and_sharp_corner(self):
        segs = polyline_layout([(0.0, 0.0), (10000.0, 0.0), (2000.0, 3000.0)])
        self.assertTrue(segs[0].post0)
        self.assertFalse(segs[1].post0)
        self.assertEqual(st(hoarding_plan("a", segs[0]))["終わりの角"], "WARN")    # 内角 20° は自在コーナーで受けられない

    def test_outside_side(self):
        """敷地の中の点が左なら外（パネル）は右。逆なら点列を逆に回す."""
        self.assertTrue(outside_is_right([(0.0, 0.0), (10000.0, 0.0)], (5000.0, 3000.0)))
        self.assertFalse(outside_is_right([(0.0, 0.0), (10000.0, 0.0)], (5000.0, -3000.0)))
        segs = polyline_layout([(0.0, 0.0), (10000.0, 0.0)], outside_right=False)
        self.assertEqual(segs[0].p0, (10000.0, 0.0))

    def test_inset_boundary(self):
        out = inset_polygon([(0.0, 0.0), (10000.0, 0.0), (10000.0, 8000.0), (0.0, 8000.0)], 150.0)
        self.assertEqual([tuple(round(v) for v in p) for p in out], [(150, 150), (9850, 150), (9850, 7850), (150, 7850)])
        tri = inset_polygon([(0.0, 0.0), (10000.0, 0.0), (0.0, 10000.0)], 100.0)
        self.assertAlmostEqual(tri[0][0], 100.0)
        self.assertAlmostEqual(tri[1][0] + tri[1][1], 10000.0 - 100.0 * math.sqrt(2), places=3)   # 斜めの辺も平行に寄せる


class TestSlope(unittest.TestCase):
    def test_ground_per_post(self):
        """敷地の高低差: 支柱ごとに地盤を読む（部品の postZ）、10% を超えれば WARN."""
        p = hoarding_plan("a", Segment((0.0, 0.0), (9000.0, 0.0)), ground=lambda x, y: -0.07 * x)
        self.assertEqual(p.post_z[-1], -630.0)
        self.assertEqual(st(p)["地盤の高低差"], "OK")
        self.assertEqual(part_params(p)["postZ"].split(",")[-1], "-630")
        steep = hoarding_plan("a", Segment((0.0, 0.0), (9000.0, 0.0)), ground=lambda x, y: -0.15 * x)
        self.assertEqual(st(steep)["地盤の高低差"], "WARN")

    def test_split_gates_along_polyline(self):
        segs = polyline_layout([(0.0, 0.0), (10000.0, 0.0), (10000.0, 8000.0)])
        self.assertEqual(split_gates(segs, [(12000.0, 900.0, "ドア")]), [[], [(2000.0, 900.0, "ドア")]])

    def test_report(self):
        md = report([hoarding_plan("a", Segment((0.0, 0.0), (5000.0, 0.0))), hoarding_plan("b", Segment((0.0, 0.0), (3000.0, 0.0)))])
        for w in ("# 仮囲い", "136条の2の20", "合計", "日建リース工業", "風の検討", "控えの座屈"):
            self.assertIn(w, md)


class TestRunScript(unittest.TestCase):
    def test_chains_join_loose_lines(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from kakoi_run import _gate, chains

        g = [({"elementId": {"guid": "a"}}, [((0.0, 0.0), (5000.0, 0.0))]),
             ({"elementId": {"guid": "b"}}, [((5000.0, 0.0), (8000.0, 4000.0))])]       # 斜めの線をつなぐ
        out = chains(g)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], [(0.0, 0.0), (5000.0, 0.0), (8000.0, 4000.0)])
        self.assertEqual(_gate("4000:3600:ジャバラ"), (4000.0, 3600.0, "ジャバラ"))
        self.assertEqual(_gate("12000:7200:パネルキャスター:両開き"), (12000.0, 7200.0, "パネルキャスター両開き"))
        with self.assertRaises(SystemExit):
            _gate("1:2:シャッター")

    def test_wall_chains_put_panels_on_the_ground_side(self):
        """山留め（壁）を選ぶと、角の合う壁をつなぎ、根切りの反対（地山）の側を進む向きの右（パネルの側）にそろえる."""
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from kakoi_run import wall_chains

        sq = [(0.0, 0.0), (12.0, 0.0), (12.0, 7.0), (0.0, 7.0)]

        class Fake:
            def get_selected_elements(self):
                return [{"elementId": {"guid": f"w{i}"}} for i in range(4)]

            def get_details(self, sel):
                return [{"type": "Wall", "details": {"begCoordinate": {"x": sq[i][0], "y": sq[i][1]},
                                                       "endCoordinate": {"x": sq[(i + 1) % 4][0], "y": sq[(i + 1) % 4][1]},
                                                       "begThickness": 0.3, "zCoordinate": -6.0, "height": 6.0}}
                        for i in range(4)]

        lines, top, _w = wall_chains(Fake())
        self.assertEqual((len(lines), top), (1, 0.0))
        _key, pts, closed = lines[0]
        self.assertTrue(closed)
        segs = polyline_layout(pts, closed=True)
        # 根切りの中（6000, 3500）が進む向きの左＝パネルは外（地山）の側
        a, b = segs[0].p0, segs[0].p1
        self.assertGreater((b[0] - a[0]) * (3500.0 - a[1]) - (b[1] - a[1]) * (6000.0 - a[0]), 0.0)


if __name__ == "__main__":
    unittest.main()
