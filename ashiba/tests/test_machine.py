"""重機（利用者の指定 2026-11-01: 重機の詳細度もっとあげて　種類も増やして）."""

from __future__ import annotations

import re
import unittest

from _path import SRC  # noqa: F401

from ashiba.machine import (KINDS, MACHINES, Placed, check, crawler_plates, find, keep_out, license_for, outrigger_pad, part_params,
                            rated_at, report, road_license)

ROOT = SRC.parent


class TestMachines(unittest.TestCase):
    def test_every_kind_and_part_parameter(self):
        """7種類すべてに機種があり、渡すパラメータは部品に全部ある."""
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


if __name__ == "__main__":
    unittest.main()
