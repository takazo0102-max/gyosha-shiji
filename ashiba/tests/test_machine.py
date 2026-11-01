"""重機（利用者の指定 2026-11-01: 重機の詳細度もっとあげて　種類も増やして）."""

from __future__ import annotations

import re
import unittest

from _path import SRC  # noqa: F401

from ashiba.machine import KINDS, MACHINES, Placed, check, find, license_for, part_params, plates_for, rated_at, report

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

    def test_licenses(self):
        self.assertIn("技能講習", license_for(MACHINES["bh01"]))                       # 3.6t は 3t 以上
        self.assertIn("移動式クレーン運転士免許", license_for(MACHINES["cc50"]))
        self.assertIn("技能講習", license_for(MACHINES["aw12"]))                       # 作業床 12.1m
        self.assertIn("特別教育", license_for(MACHINES["sv06"]))                       # 5.72m
        self.assertEqual(license_for(MACHINES["dump4"]), "中型免許")


class TestChecks(unittest.TestCase):
    def test_ground_and_jacks(self):
        cc = check(Placed("c", MACHINES["cc90"]), soil_q=80.0)
        st = {c.item: c.status for c in cc.checks}
        self.assertEqual(st["接地圧"], "要確認")                                       # 95 kPa ＞ 80
        self.assertEqual(plates_for(200.0, 100.0), (2.0, 1))                           # 2.0m² → 敷鉄板1枚（4.6m²）
        self.assertEqual(plates_for(30.0, 100.0)[1], 0)                                # 敷板 600 角で可
        pump = check(Placed("p", MACHINES["pump36"]))
        self.assertEqual([c.status for c in pump.checks if c.item.startswith("ジャッキ")], ["要敷鉄板"] * 3)

    def test_crane_rated(self):
        """表の列はその長さ以上・行はその半径以上（安全側）."""
        m = MACHINES["cc50"]
        self.assertEqual(rated_at(m, 30.5, 15.0), 5.8)
        self.assertEqual(rated_at(m, 25.0, 10.0), 11.4)
        self.assertIsNone(rated_at(m, 40.0, 10.0))
        self.assertEqual(rated_at(MACHINES["cc70"], 30.5, 15.0), 11.0)               # 7070G-2 p.8 の 30.5m・16m の欄
        c = check(Placed("c", m))
        self.assertIn("定格総荷重", [x.item for x in c.checks])
        self.assertIn("7050G-2", report([c]))


if __name__ == "__main__":
    unittest.main()
