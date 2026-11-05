"""重機（利用者の指定 2026-11-01: 重機の詳細度もっとあげて　種類も増やして）."""

from __future__ import annotations

import math
import re
import unittest

from _path import SRC  # noqa: F401

from ashiba.machine import (ATTACHMENTS, KINDS, MACHINES, Placed, att_params, check, crawler_plates, find, keep_out, license_for,
                            outrigger_pad, part_params, plan_rule, rated_at, report, road_license, swept_path, vehicle_size)

ROOT = SRC.parent


class TestMachines(unittest.TestCase):
    def test_every_kind_and_part_parameter(self):
        """12種類すべてに機種があり、渡すパラメータは部品に全部ある."""
        self.assertEqual({m.kind for m in MACHINES.values()}, set(KINDS))
        names = set(re.findall(r'Name="([^"]+)"', (ROOT / "gdl" / "hsf" / "ashiba_machine" / "paramlist.xml")
                               .read_text(encoding="utf-8")))
        for m in MACHINES.values():
            self.assertEqual(set(part_params(Placed("x", m))) - names, set(), m.key)

    def test_model_list_writes_dimensions(self):
        """部品の設定で機種を選ぶと（mcModel）寸法を書き込む。機種ごとに分かれ、番号は part_params と同じ."""
        vl = (ROOT / "gdl" / "hsf" / "ashiba_machine" / "scripts" / "vl.gdl").read_text(encoding="utf-8-sig")
        self.assertIn('values{2} "mcModel" mdV, mdS', vl)
        for k, m in MACHINES.items():
            code = part_params(Placed("", m))["mcModel"]
            self.assertIn(f"if mcModel = {code} then", vl)
            self.assertIn(f'mdS[{code + 1}] = "{m.name}"', vl)

    def test_catalog_values(self):
        """仕様書の値: PC138US-12 の後端旋回半径 1,490・クローラ全幅＝ゲージ 1,990＋シュー 500、7050G-2 の R4,000."""
        bh = MACHINES["bh045"].params
        self.assertEqual((bh["tailR"], bh["trkW"], bh["trkL"]), (1.49, 2.49, 3.61))
        self.assertEqual(MACHINES["cc50"].params["tailR"], 4.0)
        self.assertEqual((MACHINES["bh01"].params["bldW"], MACHINES["bh08"].params["bldW"]), (1.77, 0.0))   # PC200 は排土板なし
        p = MACHINES["pump26"].params
        self.assertAlmostEqual(p["sL1"] + p["sL2"] + p["sL3"] + p["sL4"], 21.7)       # 4段の和＝最大水平到達
        self.assertIs(find("PC78US"), MACHINES["bh025"])

    def test_researched_values(self):
        """しっかり調べ直した値（利用者の指定 2026-11-01: しっかりリサーチしてね）."""
        bh = MACHINES["bh025"].params
        self.assertEqual((bh["boomL"], bh["upZ"], bh["bldH"], bh["bmY"]), (3.71, 0.735, 0.49, -0.12))   # 米国版で作業範囲が一致
        self.assertEqual(MACHINES["bh045"].params["bldW"], 0.0)                     # 国内 -12 の排土板はオプション
        p = MACHINES["pump36"].params
        self.assertAlmostEqual(p["o3x"], 2.8 - 9.63)                                 # アシストはリヤジャッキ 8,540 の 1,090 後ろ
        self.assertEqual((p["nFr"], p["frSp"], p["rearSp"]), (2, 1.74, 1.19))
        self.assertEqual(MACHINES["pump26"].params["tuH"], 4.0)                     # 作業範囲図 10.2m − 1段目 6.2m
        self.assertEqual(MACHINES["dump10"].params["frOv"], 1.37)                   # いすゞ 車両外観図
        self.assertEqual(MACHINES["aw12"].params["carF"], 2.15)                     # 旋回台はキャブのすぐ後ろ
        self.assertIn("準中型", license_for(MACHINES["aw12"]))
        at = MACHINES["at17"].params                                                 # タダノ AT-170TG（前方格納。旋回台は後ろ）
        self.assertEqual((at["carL"], at["wb"], at["frOv"], at["o1y"]), (6.9, 3.4, 1.385, 2.05))   # 公表 6,900・3,400・最大張出 4.1m
        self.assertAlmostEqual(at["carL"] - at["frOv"] - at["wb"], 2.115)          # 後軸〜後端（公表）

    def test_licenses(self):
        """3t は機体重量（作業装置を除いた乾燥質量。安衛令20条12号・安衛則36条9号）で分ける。PC38UU-6 は機体質量 2,680kg."""
        self.assertIn("特別教育（安衛則36条9号", license_for(MACHINES["bh01"]))       # 運転質量 3.6t でも機体質量 2.68t
        self.assertIn("技能講習", license_for(MACHINES["bh025"]))
        self.assertIn("移動式クレーン運転士免許", license_for(MACHINES["cc50"]))
        self.assertIn("技能講習", license_for(MACHINES["aw12"]))                       # 作業床 12.1m
        self.assertIn("特別教育", license_for(MACHINES["sv06"]))                       # 5.72m
        self.assertIn("中型免許（8t 限定中型も可）", license_for(MACHINES["dump4"]))

    def test_road_license(self):
        """道路交通法施行規則2条: 大型は 11,000kg 以上（ちょうども大型）か最大積載量 6,500kg 以上."""
        self.assertEqual(road_license(11.0), "大型免許")
        self.assertEqual(road_license(10.9, 6.5), "大型免許")
        self.assertEqual(road_license(10.9, 3.0), "中型免許")
        self.assertEqual(road_license(4.5), "準中型免許")
        self.assertEqual(road_license(3.0, 1.0), "普通免許")


class TestChecks(unittest.TestCase):
    def test_plate_tables(self):
        """日本クレーン協会 表3・表4（鉄板厚 22mm）. 欄は荷重・接地圧を切り上げて引く."""
        self.assertEqual(outrigger_pad(78.0, 1), "A")         # 柔らかい粘性土 100kN → 1.2×1.2m
        self.assertEqual(outrigger_pad(200.0, 1), "B")        # 200kN → 6.0×1.5m（2枚）
        self.assertEqual(outrigger_pad(450.0, 1), "-")        # 500kN 以上は敷鉄板では対応できない
        self.assertEqual(outrigger_pad(100.0, 2), "B")        # 緩い砂質土は 22mm だと 100kN でも 6.0×1.5m
        self.assertEqual(outrigger_pad(100.0, 3), "S")        # 中位の粘性土 100kN → 厚さ7cmの敷板
        self.assertEqual(outrigger_pad(1200.0, 6), "-")
        self.assertEqual((crawler_plates(65.0, 1), crawler_plates(120.0, 1), crawler_plates(320.0, 1)), ("0", "1", "-"))
        self.assertEqual(crawler_plates(106.0, 3), "0")

    def test_checks(self):
        cc = {c.item: c for c in check(Placed("c", MACHINES["cc90"]), soil_q=80.0).checks}
        self.assertEqual(cc["接地圧"].status, "要確認")                                 # 95 kPa ＞ 80
        self.assertIn("最大接地圧", cc["接地圧"].detail)                                # 平均接地圧なので下限
        self.assertIn("地盤調査", cc)                                                   # 20t 超
        pump = check(Placed("p", MACHINES["pump36"]))
        self.assertEqual([c.status for c in pump.checks if c.item.startswith("ジャッキ")], ["要敷鉄板"] * 3)
        bh = keep_out(MACHINES["bh045"], MACHINES["bh045"].params, 0.5)
        self.assertEqual([(w, round(r, 2), law) for w, r, law in bh],
                         [("後端（上部旋回体）", 1.99, "安衛則158条"), ("作業装置（最大掘削半径）", 8.8, "安衛則158条")])

    def test_crane_rated(self):
        """表の列はその長さ以上・行はその半径以上（安全側）."""
        m = MACHINES["cc50"]
        self.assertEqual(rated_at(m, 30.5, 15.0), 5.9)                               # 7050G-2 p.10 の 30.5m・16m の欄
        self.assertEqual(rated_at(m, 25.0, 10.0), 11.4)
        self.assertIsNone(rated_at(m, 60.0, 10.0))                                   # 最長 51.8m を超える
        self.assertEqual(rated_at(m, 21.3, 19.0), 4.6)                               # 「4.6/19.7」= 最大作業半径 19.7m
        self.assertIsNone(rated_at(m, 21.3, 20.0))
        self.assertIsNone(rated_at(m, 30.5, 6.0))                                    # 「19.8/6.8」= 最小作業半径 6.8m
        self.assertEqual(rated_at(MACHINES["cc70"], 30.5, 15.0), 11.0)               # 7070G-2 p.8
        self.assertEqual(rated_at(MACHINES["cc90h"], 30.0, 12.0), 21.45)             # SCX900-3 p.14
        c = check(Placed("c", m))
        self.assertIn("定格総荷重", [x.item for x in c.checks])
        self.assertIn("7050G-2", report([c]))



class TestPileDemolition(unittest.TestCase):
    """杭・山留め・解体の重機（利用者の指定 2026-11-03: 杭、山留め　解体で使用する重機を徹底的に調べて　GDL作成してちょ）."""

    def test_catalog_values(self):
        """カタログの値: DH558 のリーダ中心 3,000・後端 R4,940、ED6200 の掘削中心 R4,492・ブーム 20.6m、RT-200AⅢ の 8,390×6,980、
        SK400DLC の R3,600、ST400SX の 2,070×1,000×2,320."""
        p = MACHINES["pd558"].params
        self.assertEqual((p["ldX"], p["tailR"], p["trkL"], p["fjX"], p["rjX"]), (3.0, 4.94, 5.52, 3.61, 3.64))
        self.assertAlmostEqual(p["ldZ"] + p["ldL"] + 2.7 * p["ldDia"], 35.423, delta=0.05)     # 全高（33m リーダ）
        q = MACHINES["pd658"].params
        self.assertAlmostEqual(q["ldZ"] + q["ldL"] + 2.7 * q["ldDia"], 38.519, delta=0.1)      # 36m リーダ
        e = MACHINES["ed6200"].params
        self.assertEqual((e["kdR"], e["tbL"], e["tbA"]), (4.492, 20.6, 82.5))
        self.assertAlmostEqual(e["pvX"] + e["tbL"] * math.cos(math.radians(e["tbA"])), e["kdR"], delta=0.05)   # ブームの先が掘削中心
        r = MACHINES["rt200"].params
        self.assertEqual((r["brL"], r["brW"], r["rtD"]), (8.39, 6.98, 1.98))
        self.assertEqual(MACHINES["dm400"].params["tailR"], 3.6)
        d = MACHINES["dm400s"].params                                                   # セパレート: 最大作業高さ 13,680
        self.assertAlmostEqual(d["pvH"] + d["dbL1"] + d["dbL2"] + d["dbL3"], 13.68, delta=0.2)
        g = MACHINES["gk400"].params
        self.assertEqual((g["piL"], g["piW"], g["piH"], g["piC"]), (2.07, 1.0, 2.32, 0.955))
        d5 = MACHINES["dm550"].params                                                   # SK550DLC 8.7m＋3.5m: 27,530・R3,970
        self.assertAlmostEqual(d5["pvH"] + d5["dbL1"] + d5["dbL2"] + d5["dbL3"], 27.53, delta=0.3)
        self.assertEqual((d5["tailR"], d5["trkL"], MACHINES["dm550"].ground_kpa), (3.97, 5.46, 106.0))
        self.assertEqual((MACHINES["dm350"].params["trkW"], MACHINES["dm350"].ground_kpa), (3.19, 81.0))   # 幅の伸縮なし
        self.assertEqual((MACHINES["gk70"].params["piH"], MACHINES["gk70"].params["piC"]), (1.9, 0.525))   # 低空頭
        self.assertEqual((MACHINES["gk112h"].params["piL"], MACHINES["gk112h"].mass_t), (3.37, 10.8))
        s3 = MACHINES["pd658s"].params
        self.assertEqual((s3["auN"], s3["auP"], s3["auD"]), (3, 0.45, 0.55))           # SMW φ550・軸間 450

    def test_licenses(self):
        """基礎工事用は 3t 以上で技能講習、据置の全周回転機は 36条9号の2、解体用は別の講習、PC18MR-5（1.97t）は特別教育."""
        self.assertIn("基礎工事用）運転技能講習", license_for(MACHINES["pd558"]))
        self.assertIn("36条9号の3", license_for(MACHINES["ed6200"]))
        self.assertIn("移動式クレーン運転士免許", license_for(MACHINES["ed6200"]))         # クレーン仕様 17t
        self.assertIn("36条9号の2", license_for(MACHINES["rt200"]))
        self.assertIn("解体用）運転技能講習", license_for(MACHINES["dm400"]))
        self.assertIn("解体用）の特別教育", license_for(MACHINES["dm18"]))
        self.assertIn("解体用", license_for(MACHINES["bh045"], "d135"))                  # バックホウに圧砕機
        self.assertNotIn("解体用", license_for(MACHINES["bh045"]))
        self.assertIn("171条の4", plan_rule(MACHINES["dm400"]))
        self.assertIn("173条", plan_rule(MACHINES["pd558"]))

    def test_checks(self):
        c = {x.item: x for x in check(Placed("p", MACHINES["pd558"])).checks}
        self.assertEqual(c["リーダの自立"].status, "注意")                              # 33m ＞ 27m
        self.assertEqual(c["接地圧"].status, "要確認")                                  # 150kPa ＞ 100
        c = {x.item: x for x in check(Placed("d", MACHINES["dm400"])).checks}
        self.assertEqual(c["アタッチメント"].status, "OK")                              # 2,600kg ≦ 2,600kg
        self.assertIn("特定解体用機械", c)                                               # ブーム＋アーム 23m
        c = {x.item: x for x in check(Placed("d", MACHINES["dm400"], att="d352")).checks}
        self.assertEqual(c["アタッチメント"].status, "要確認")                          # 3,600kg ＞ 2,600kg
        c = {x.item: x for x in check(Placed("b", MACHINES["bh045"], att="d212")).checks}
        self.assertEqual(c["アタッチメント"].status, "要確認")                          # 20〜22t 級を 13.8t に
        c = {x.item: x for x in check(Placed("v", MACHINES["cc50v"])).checks}
        self.assertEqual(c["バイブロの吊り"].status, "OK")                               # 20.2t ≦ 半径 6m の 24.1t
        self.assertIn("20.2t", c["バイブロの吊り"].detail)
        rt = check(Placed("r", MACHINES["rt200"]))
        self.assertEqual(len([x for x in rt.checks if x.item.startswith("ジャッキ")]), 4)
        ko = keep_out(MACHINES["dm400"], {**MACHINES["dm400"].params, **att_params("kr1100")}, 0.5)
        self.assertEqual(round(ko[1][1], 2), 16.1)                                       # 13.0＋2.6＋0.5

    def test_attachment_params(self):
        """爪の開きは先の開きが開口幅になる角度。ブレーカは開かない。バケットは atK 0."""
        a = att_params("d135")
        self.assertEqual(a["atK"], 1)
        jl = 0.55 * a["atL"]
        self.assertAlmostEqual(2 * jl * math.sin(math.radians(a["atO"] / 2)), 1.0, delta=0.01)
        self.assertEqual(att_params("ghd10")["atO"], 0.0)
        self.assertEqual(part_params(Placed("", MACHINES["bh045"]))["atK"], 0)
        self.assertEqual(part_params(Placed("", MACHINES["cc50"]))["vbK"], 0)           # 機種を選び直すとバイブロが消える
        self.assertTrue(all(k in ("d75", "d135", "d212", "d352", "mc212", "dx135", "dx202", "gv122", "gv202", "ghd6", "ghd10",
                                  "jats1100", "kr1100", "kr1350", "ifz15", "lhv025", "lhv04", "lhv07", "lhv09") for k in ATTACHMENTS))

    def test_vibro_on_excavator(self):
        """調和工業 LHV（カタログ p.5 の寸法表）: エクステンションの L・N と本体の B・F・A、取付クラス、資格は基礎工事用."""
        a = att_params("lhv07")
        self.assertEqual((a["atK"], a["atL"], a["atW"], a["vbW"], a["vbT"], a["vbH"], a["vbP"]), (5, 1.4, 1.138, 1.18, 0.757, 1.705, 7.0))
        ps = part_params(Placed("", MACHINES["bh08"], att="lhv07"))
        self.assertEqual((ps["atK"], ps["bkA"]), (5, 0.0))                                 # エクステンションは水平に
        c = {x.item: x for x in check(Placed("b", MACHINES["bh08"], att="lhv07")).checks}
        self.assertEqual(c["アタッチメント"].status, "OK")                                # PC200 20.2t は 20t 級
        self.assertIn("杭長の目安 7m", c["バイブロ"].detail)
        self.assertNotIn("特定解体用機械", c)
        self.assertIn("基礎工事用", license_for(MACHINES["bh08"], "lhv07"))
        gdl = (ROOT / "gdl" / "hsf" / "ashiba_machine" / "scripts" / "3d.gdl").read_text(encoding="utf-8-sig")
        self.assertIn('"lhv":', gdl)

    def test_hotspots_move_parameters(self):
        """3D のホットスポットで動かせる: 杭打機のオーガとリーダ・アースドリルのブームとバケット・解体機の3段と先・全周回転機・圧入機."""
        gdl = (ROOT / "gdl" / "hsf" / "ashiba_machine" / "scripts" / "3d.gdl").read_text(encoding="utf-8-sig")
        for par in ("auZ", "ldL", "tbA", "tbL", "bkD", "dA1", "dA2", "dA3", "bkA", "atO", "rtS", "csH", "piS", "piT", "bmA", "lbA", "pA1",
                    "bedA", "abA", "pfH", "hkD"):
            self.assertRegex(gdl, rf"hotspot [^\n]*, {par}, [1-7]", par)
        ids = [int(x) for x in re.findall(r"hotspot [^\n]*?, (\d{3}), \w+, ", gdl)]
        self.assertEqual(len(ids), len(set(ids)))                                       # 番号が重ならない
        self.assertIn("hid = 351", gdl)                                                  # 爪の開きはバックホウと解体機で別の番号
        self.assertIn("hid = 355", gdl)



class TestDeliveryVehicles(unittest.TestCase):
    """搬入車両（利用者の指定 2026-11-03: 搬入車両も作成して　トレーラーとか含め　詳細平面図になるように）."""

    def test_catalog_values(self):
        """メーカーの諸元: エルフ 4,685・WB 2,490・R4.5、ギガ 8×4 の軸 1,850＋4,275＋1,210、トレクス PMR440BB 11,810（キングピン〜後端）、
        クオン GW の前端〜連結部 5,010 と足して連結全長 16,820."""
        e = MACHINES["tr2"].params
        self.assertEqual((e["carL"], e["wb"], e["tnR"], e["flZ"]), (4.685, 2.49, 4.5, 0.855))
        g = MACHINES["tr10l"].params
        self.assertAlmostEqual(g["wb"], 1.85 + 4.275)
        self.assertEqual((g["nFr"], g["frSp"], g["rearSp"]), (2, 1.85, 1.21))
        lb = MACHINES["lb4"]
        self.assertAlmostEqual(vehicle_size(lb, lb.params)["長さ"], 16.82, places=2)
        self.assertAlmostEqual(vehicle_size(MACHINES["lbl"], MACHINES["lbl"].params)["長さ"], 3.98 + 8.70, places=2)   # GK No.6
        pt = MACHINES["pt2"]
        self.assertAlmostEqual(vehicle_size(pt, pt.params)["長さ"], 5.06 + 18.0, places=2)   # 積載物 20m（前に 2.0）

    def test_road_limits(self):
        """車両制限令3条1項: 幅 2.5・長さ 12・高さ 3.8・総重量 20t。超えれば特殊車両通行許可（道路法47条の2）."""
        c = {x.item: x for x in check(Placed("t", MACHINES["tr4"])).checks}
        self.assertEqual(c["道路の制限"].status, "OK")
        c = {x.item: x for x in check(Placed("t", MACHINES["lb4"])).checks}
        self.assertEqual(c["道路の制限"].status, "要確認")
        self.assertIn("幅 2.99m", c["道路の制限"].detail)
        self.assertIn("特例8車種", c["道路の制限"].detail)
        # 4t 平ボディに高さ 2.8m の積荷を載せると 1.09＋2.8＝3.89m で高さを超える
        c = {x.item: x for x in check(Placed("t", MACHINES["tr4"], params={"cgOn": 1, "cgL": 3, "cgW": 2, "cgH": 2.8, "cgT": 2})).checks}
        self.assertIn("高さ 3.89m", c["道路の制限"].detail)

    def test_swept_path(self):
        """単車は場内通路と同じ式、連結車はキングピンとトレーラー後軸群まで、ポールはカタログの所要道路幅."""
        from ashiba.site_route import VEHICLES, swept
        m = MACHINES["tr4"]
        sw = swept_path(m, m.params)
        self.assertGreater(sw["外側"], m.params["tnR"])
        self.assertLess(sw["内側"], sw["外側"])
        lb = swept_path(MACHINES["lb4"], MACHINES["lb4"].params)
        self.assertGreater(lb["幅"], swept_path(MACHINES["lbl"], MACHINES["lbl"].params)["幅"])   # キングピン〜後軸が長いほど内輪差が大きい
        self.assertEqual(swept_path(MACHINES["pt2"], MACHINES["pt2"].params)["幅"], 10.5)

    def test_licenses(self):
        self.assertIn("けん引免許", license_for(MACHINES["lb4"]))
        self.assertIn("小型移動式クレーン運転技能講習", license_for(MACHINES["uc4"]))
        self.assertIn("移動式クレーン検査証", license_for(MACHINES["uc10"]))              # 4.9t 吊り
        self.assertIn("36条11号", license_for(MACHINES["sl4"]))                          # ウインチ
        self.assertIn("準中型", license_for(MACHINES["tr2"]))
        self.assertIn("151条の70", plan_rule(MACHINES["tr4"]))

    def test_part_has_vehicle_params(self):
        gdl = (ROOT / "gdl" / "hsf" / "ashiba_machine" / "scripts" / "2d.gdl").read_text(encoding="utf-8-sig")
        self.assertIn("arc2 xAxR, yC, rOut", gdl)                                         # 平面の旋回軌跡
        self.assertIn("hotspot2 kpX, 0, 11, trA, 6", gdl)                                  # 連結の折れ角
        names = re.findall(r'Name="([^"]+)"', (ROOT / "gdl" / "hsf" / "ashiba_machine" / "paramlist.xml").read_text(encoding="utf-8"))
        self.assertEqual(len(names), len(set(names)))                                    # 同じ名前のパラメータが無い（GSM が作れない）
        from ashiba.machine import BOOL_PARAMS
        xml = (ROOT / "gdl" / "hsf" / "ashiba_machine" / "paramlist.xml").read_text(encoding="utf-8")
        self.assertEqual(set(BOOL_PARAMS), set(re.findall(r'<Boolean Name="([^"]+)"', xml)))
        ps = part_params(Placed("", MACHINES["uc4"]))
        self.assertIs(ps["ucOn"], True)                                                    # 0・1 は Tapir が受け付けない



class TestPlaceByClick(unittest.TestCase):
    """線を選ばずに押すと平面図で2回クリック、機種は窓で選ぶ（利用者の指定 2026-11-06「クリックして配置するようにしたい あと機種を選択するように」）."""

    @classmethod
    def setUpClass(cls):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

    class Client:
        timeout = 60.0

        def __init__(self, answer):
            self.answer = answer
            self.seen = []

        def tapir(self, cmd, params, retries=2):
            self.seen.append((cmd, retries, self.timeout))
            return self.answer

    def test_two_clicks_give_place_and_front(self):
        import machine_run as M

        c = self.Client({"cancelled": False, "startPoint": {"x": 1.0, "y": 2.0, "z": 0}, "endPoint": {"x": 1.0, "y": 5.0, "z": 0}})
        self.assertEqual(M.pick_line(c), [(1000.0, 2000.0), (1000.0, 5000.0)])
        self.assertEqual(c.seen, [("GetLineFromUser", 0, M.PICK_WAIT_S)])     # 待つ命令は送り直さない
        self.assertEqual(c.timeout, 60.0)

    def test_escape_places_nothing(self):
        import machine_run as M

        self.assertIsNone(M.pick_line(self.Client({"cancelled": True})))

    def test_same_point_faces_plus_x(self):
        import machine_run as M

        c = self.Client({"cancelled": False, "startPoint": {"x": 1.0, "y": 2.0}, "endPoint": {"x": 1.0, "y": 2.0}})
        self.assertEqual(M.pick_line(c)[1], (2000.0, 2000.0))

    def test_model_form_lists_the_same_kind(self):
        import json
        import os
        from unittest import mock

        import machine_run as M

        m = MACHINES["bh045"]
        other = next(x for x in MACHINES.values() if x.kind == m.kind and x is not m)
        ans = json.dumps({"button": "place", "values": {"model": f"{other.name}（{other.model}）"}})
        with mock.patch.dict(os.environ, {"ASHIBA_FORM_ANSWER": ans}):
            self.assertIs(M.choose_model(m, None), other)
        with mock.patch.dict(os.environ, {"ASHIBA_FORM_ANSWER": '{"button": "cancel"}'}):
            self.assertIsNone(M.choose_model(m, None))

    def test_palette_buttons_ask_for_the_model(self):
        from ashiba.palette import ACTIONS

        for a in ACTIONS:
            if a.script == "machine_run.py" and "--remove" not in a.args:
                self.assertIn("--ask", a.args, a.title)


if __name__ == "__main__":
    unittest.main()
