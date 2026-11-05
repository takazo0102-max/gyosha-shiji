"""敷鉄板（利用者の指定 2026-11-01: 敷鉄板はホットスポットで広げれるようにして 別オブジェクトにして）."""

from __future__ import annotations

import sys
import unittest

from _path import SRC  # noqa: F401

from ashiba.crane import Lift, crane_plan, outrigger_plates
from ashiba.steel_plate import layout, part_params, quantity


class TestLayout(unittest.TestCase):
    def test_round_up_to_whole_plates(self):
        """広さは1枚の倍数に切り上げる（部品のパラメータスクリプトと同じ）。5×10 は 1,524×3,048・802kg."""
        lay = layout(7000.0, 4000.0)
        self.assertEqual((lay.nx, lay.ny, lay.lx, lay.ly, lay.count), (3, 3, 9144.0, 4572.0, 9))
        self.assertEqual(lay.kg, 9 * 802.0)
        self.assertEqual(lay.joints, 2 * 3 + 3 * 2)
        self.assertEqual(layout(3048.0, 1524.0).count, 1)                    # ちょうどなら1枚
        self.assertEqual(layout(3080.0, 1524.0).count, 1)                    # 2% までの はみ出しは切り上げない

    def test_direction_types_and_layers(self):
        y = layout(3048.0, 6096.0, "NT22×5×20", along_y=True)
        self.assertEqual((y.nx, y.ny, y.px, y.py), (2, 1, 1524.0, 6096.0))
        two = layout(3048.0, 3048.0, layers=2)                               # 下 2枚・上に十字 2枚
        self.assertEqual(two.count, 4)
        prm = part_params(two)
        self.assertEqual((prm["lenX"], prm["lenY"], prm["plType"], prm["plDir"], prm["plLay"]), (3.048, 3.048, 2, 0, 2))
        self.assertEqual(part_params(y)["plDir"], 1)
        self.assertEqual(list(part_params(y))[:4], ["plType", "plDir", "plLay", "lenX"])      # 向きを広さより先に

    def test_quantity(self):
        q = {a: n for a, n, _c in quantity([layout(7000.0, 4000.0), layout(3048.0, 1524.0)])}
        self.assertEqual(q["厚板鋼板 NT22×5×10（1524×3048×22）"], 10)
        self.assertEqual(q["敷鉄板固定金具 小判君 NTK"], 12)


class TestCranePlates(unittest.TestCase):
    def test_one_or_two_plates_under_each_outrigger(self):
        """クレーンのアウトリガの下に敷鉄板の部品: 1枚は車体に沿わせて真ん中に、2枚は上にもう1枚を十字に."""
        p = crane_plan("a", [Lift("柱", 12000.0, 2.5, 15000.0)])
        ps = outrigger_plates(p)
        self.assertEqual(len(ps), 4)
        (x, y), along_y, dz = ps[0]
        self.assertEqual((x + 1524.0, y + 762.0, along_y, dz), (3265.0, 3300.0, False, 0.0))   # 板の真ん中にフロート
        soft = crane_plan("b", [Lift("柱", 12000.0, 2.5, 15000.0)], soil_q=60.0)
        ps2 = outrigger_plates(soft)
        self.assertEqual(len(ps2), 8)
        self.assertEqual((ps2[1][1], ps2[1][2]), (True, 22.0))


class TestRunScript(unittest.TestCase):
    def test_extent_and_codes(self):
        sys.path.insert(0, str(SRC.parent / "scripts"))
        from plate_run import extent, plate_code

        c, lx, ly, ang = extent([(0.0, 0.0), (6000.0, 0.0), (6000.0, 3000.0), (0.0, 3000.0)])
        self.assertEqual((c, lx, ly, ang), ((0.0, 0.0), 6000.0, 3000.0, 0.0))
        c2, lx2, ly2, _a = extent([(0.0, 0.0), (5000.0, 0.0)], 1524.0)                       # 線1本は幅を左へ
        self.assertEqual((lx2, ly2), (5000.0, 1524.0))
        self.assertEqual(plate_code("5x20"), "NT22×5×20")
        with self.assertRaises(SystemExit):
            plate_code("6x20")


if __name__ == "__main__":
    unittest.main()
