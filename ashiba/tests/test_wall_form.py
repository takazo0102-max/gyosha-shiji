"""壁の型枠（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置する
ようにして）."""

from __future__ import annotations

import math
import unittest

from _path import SRC  # noqa: F401

from ashiba.wall_form import (EDGE_MM, TIE_ALLOW_KN, W0_KN_M3, check, choose, face_extents, face_layout, free_ends, plan_wall, pressure_kn_m2,
                              tube_pieces, wall_from_details, _stations)


class TestPressure(unittest.TestCase):
    def test_jass5_table(self):
        w = W0_KN_M3
        self.assertAlmostEqual(pressure_kn_m2(1200), w * 1.2)                          # 1.5m 以下は液圧
        self.assertAlmostEqual(pressure_kn_m2(3000, 6000), 1.5 * w)                    # 長い壁
        self.assertAlmostEqual(pressure_kn_m2(3000, 2500), 1.5 * w + 0.2 * w * 1.5)    # 3m 以下の壁
        self.assertAlmostEqual(pressure_kn_m2(3000, column=True), 1.5 * w + 0.6 * w * 1.5)
        self.assertAlmostEqual(pressure_kn_m2(3000, 6000, rate=15.0), 2.0 * w)
        self.assertAlmostEqual(pressure_kn_m2(3000, 6000, rate=25.0), 3.0 * w)         # 速いと液圧

    def test_choose_passes_and_prefers_wide_battens(self):
        c = choose(3000, 6000)
        self.assertTrue(c.ok)
        self.assertTrue(all(b.ok for b in c.beams))
        self.assertLessEqual(c.tie_kn, TIE_ALLOW_KN)
        self.assertEqual((c.sangi_pitch, c.tate_pitch, c.tie_pitch), (250.0, 450.0, 750.0))
        self.assertFalse(check(3000, 300.0, 750.0, 900.0, 6000).ok)                    # 粗すぎる組は通らない
        self.assertEqual(len(c.lines()), 5)


class TestLayout(unittest.TestCase):
    def test_stations(self):
        xs = _stations(6000, 750, EDGE_MM)
        self.assertAlmostEqual(xs[0], EDGE_MM)
        self.assertAlmostEqual(xs[-1], 6000 - EDGE_MM)
        self.assertTrue(all(b - a <= 750 + 1e-6 for a, b in zip(xs, xs[1:])))
        self.assertEqual(_stations(200, 750, EDGE_MM), [100.0])

    def test_plan_wall(self):
        f = plan_wall(6000, 3000, 200)
        self.assertEqual(len(f.tie_x), 9)
        self.assertEqual(len(f.tate_z), 7)
        for xs in f.sangi_x:
            self.assertTrue(all(b - a <= f.calc.sangi_pitch + 1e-6 for a, b in zip(xs, xs[1:])))
        area = sum(w * h for _x, _z, w, h in f.panels[0])
        self.assertAlmostEqual(area, 6000 * 3000)                                     # 片面を合板で覆う
        q = {n: k for n, k, _note in f.quantities()}
        self.assertEqual(q["フォームタイ（壁厚 200）"], 9 * 7)
        self.assertEqual(q["Pコン"], 2 * 9 * 7)
        self.assertEqual(q["型枠用合板 12mm 900×1800"], 2 * 6)                      # 900×1800 が 6枚×1段（両面）
        self.assertEqual(q["単管 6.0m（外端太）"], 2 * 2 * 7)
        self.assertEqual(q["単管 1.0m（外端太）"], 2 * 2 * 7)                       # 6300 は 6m＋1m を継ぐ
        self.assertEqual(q["単管ジョイント（外端太の継ぎ）"], 2 * 2 * 7)

    def test_tube_pieces(self):
        self.assertEqual(tube_pieces(2300), [2500])
        self.assertEqual(tube_pieces(6300), [6000, 1000])
        self.assertEqual(tube_pieces(12500), [6000, 6000, 1000])


def _wall(a, b, t=200.0):
    L = math.dist(a, b)
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    return {"ca": a, "cb": b, "u": u, "n": (-u[1], u[0]), "lo": -t / 2, "hi": t / 2, "thick": t, "length": L}


class TestCorners(unittest.TestCase):
    """壁どうしの角: 出隅の面は向こうの面まで延ばし、入隅の面・T字は手前の面まで."""

    def test_l_corner(self):
        (a1, a2), (b1, b2) = face_extents([_wall((0, 0), (6000, 0)), _wall((6000, 0), (6000, 5000))])
        self.assertEqual((a1, a2), ((0.0, 6100.0), (0.0, 5900.0)))                  # 右（外）は延ばし、左（内）は縮める
        self.assertEqual((b1, b2), ((-100.0, 5000.0), (100.0, 5000.0)))

    def test_t_and_free_ends(self):
        ext = face_extents([_wall((0, 0), (6000, 0)), _wall((6000, -3000), (6000, 3000))])
        self.assertEqual(ext[0], [(0.0, 5900.0), (0.0, 5900.0)])                    # T 字は両面とも手前まで
        self.assertEqual(ext[1], [(0.0, 6000.0), (0.0, 6000.0)])                    # 通る壁はそのまま
        f = plan_wall(6000, 3000, 200, [(0.0, 6100.0), (0.0, 5900.0)])
        self.assertLessEqual(f.tie_x[-1], 5900.0 - EDGE_MM + 1e-6)                  # フォームタイは両面がある所だけ
        self.assertAlmostEqual(f.sangi_x[0][-1] - f.sangi_x[1][-1], 200.0, delta=60.0)


class TestNoProtrusion(unittest.TestCase):
    """両方延長から飛び出さないようにしてちょ（利用者の指定 2026-10-31）: 角では外端太は相手の外端太の線まで、桟木は相手の型枠の外."""

    def test_l_corner_tubes_meet(self):
        a, b = face_layout([_wall((0, 0), (6000, 0)), _wall((6000, 0), (6000, 5000))])
        off = 12.0 + 60.0 + 48.6 / 2.0                                              # 面から外端太の芯
        self.assertAlmostEqual(a["tubes"][0][1], 6100.0 + off)                       # 出隅: B の外の外端太の線（x）まで
        self.assertAlmostEqual(b["tubes"][0][0], -100.0 - off)                       # B も A の外の外端太の線（y）まで
        self.assertAlmostEqual(a["tubes"][1][1], 5900.0 - off)                       # 入隅: B の内の外端太の線まで
        self.assertAlmostEqual(b["tubes"][1][0], 100.0 + off)
        band = 12.0 + 60.0 + 48.6
        self.assertAlmostEqual(a["sangi"][1][1], 5900.0 - band)                      # 入隅の桟木は B の型枠の外
        self.assertAlmostEqual(b["sangi"][1][0], 100.0 + band)
        f = plan_wall(6000, 3000, 200, a["faces"], (True, False), a["tubes"], a["sangi"])
        self.assertLessEqual(max(f.sangi_x[1]) + 22.5, 5900.0 - band + 1e-6)
        self.assertAlmostEqual(f.tubes[0][0], -150.0)                                # つながらない端は 150 出す

    def test_t_junction_stops_outside_the_through_wall_form(self):
        a, b = face_layout([_wall((0, 0), (6000, 0)), _wall((6000, -3000), (6000, 3000))])
        for k in (0, 1):
            self.assertAlmostEqual(a["tubes"][k][1], 5900.0 - (12.0 + 60.0 + 48.6 / 2.0))
        self.assertEqual(b["tubes"], [(-150.0, 6150.0), (-150.0, 6150.0)])


class TestTJunctionSplit(unittest.TestCase):
    def test_through_wall_face_is_split(self):
        """T 字で通る壁の、突き当たる壁の側の面は、その所でせき板・外端太・桟木・フォームタイを分ける."""
        ws = [_wall((0, 0), (6000, 0)), _wall((6000, -3000), (6000, 3000))]
        lay = face_layout(ws)
        b = lay[1]
        f = plan_wall(6000, 3000, 200, b["faces"], (True, True), b["tubes"], b["sangi"], b["cuts"])
        self.assertEqual(f.ply_segs[0], [(0.0, 6000.0)])                             # 向こうの面は1枚
        self.assertEqual(f.ply_segs[1], [(0.0, 2900.0), (3100.0, 6000.0)])           # 突き当たる壁の厚さだけ分ける
        off = 12.0 + 60.0 + 48.6 / 2.0
        self.assertEqual([tuple(round(v, 1) for v in t) for t in f.tube_segs[1]],
                         [(-150.0, round(3000.0 - 100.0 - off, 1)), (round(3000.0 + 100.0 + off, 1), 6150.0)])
        band = 12.0 + 60.0 + 48.6
        self.assertFalse(any(3000.0 - 100.0 - band < x + 22.5 and x - 22.5 < 3000.0 + 100.0 + band for x in f.sangi_x[1]))
        self.assertFalse(any(2900.0 - EDGE_MM + 1.0 < x < 3100.0 + EDGE_MM - 1.0 for x in f.tie_x))   # 突き当たる壁を貫かない
        self.assertEqual([len(p) for p in f.panels], [7 * 2, 4 * 2 + 4 * 2])        # 6000 は 900 幅で7枚×2段、分けた所は 2900 ずつ


class TestStopEnds(unittest.TestCase):
    def test_free_ends_need_stop_forms(self):
        ws = [_wall((0, 0), (6000, 0)), _wall((6000, 0), (6000, 5000)),
              _wall((10000, 0), (14000, 0)), _wall((14000, 0), (16000, 0))]        # L 字と、1枚を2つに分けた壁
        self.assertEqual(free_ends(ws), [(True, False), (False, True), (True, False), (False, True)])
        q = {n: k for n, k, _x in plan_wall(6000, 3000, 200, ends=(True, False)).quantities()}
        self.assertEqual(q["型枠用合板 12mm（止め型枠）"], 2)                       # 高さ 3000 は 1800 の2枚
        self.assertEqual(q["単管 1.0m（止め型枠の押さえ）"], 7)                     # 外端太の段ごと
        self.assertNotIn("型枠用合板 12mm（止め型枠）", {n for n, _k, _x in plan_wall(6000, 3000, 200).quantities()})


class TestWallDetails(unittest.TestCase):
    def _det(self, polys, ref="Center", flipped=False):
        return {"type": "Wall", "details": {"geometryType": "Straight", "begCoordinate": {"x": 0, "y": 0},
                                            "endCoordinate": {"x": 6, "y": 0}, "height": 3, "bottomOffset": 0.1,
                                            "zCoordinate": 1.0, "begThickness": 0.2, "referenceLineLocation": ref,
                                            "flipped": flipped, "offset": 0, "slantAlpha": 1.570796327,
                                            "slantBeta": 1.570796327},
                "floorPlanPolygons": polys}

    def test_center_wall(self):
        w = wall_from_details(self._det([{"coordinates": [{"x": 0, "y": -0.1}, {"x": 6, "y": -0.1}, {"x": 6, "y": 0.1},
                                                           {"x": 0, "y": 0.1}]}]))
        self.assertEqual((round(w["a"][0]), round(w["a"][1])), (0, -100))             # 右の面の始め
        self.assertAlmostEqual(w["thick"], 200.0)
        self.assertAlmostEqual(w["length"], 6000.0)
        self.assertAlmostEqual(w["z0"], 1000.0)                             # zCoordinate は絶対の下端（bottomOffset は足さない）
        self.assertAlmostEqual(w["ang"], 0.0)

    def test_joined_wall_falls_back_to_reference_line(self):
        """壁がつながると外形が角の切れ端だけになる（実機 2026-10-31）. 厚さと合わなければ基準線の位置から."""
        w = wall_from_details(self._det([{"coordinates": [{"x": 6.1, "y": 0.1}, {"x": 5.9, "y": 0.1}]}]))
        self.assertAlmostEqual(w["length"], 6000.0)
        self.assertAlmostEqual(w["a"][1], -100.0)
        w = wall_from_details(self._det([], ref="Outside"))
        self.assertAlmostEqual(w["a"][1], 0.0)                                        # 壁は基準線の左

    def test_curved_wall_is_skipped(self):
        d = self._det([])
        d["details"]["geometryType"] = "Arc"
        self.assertIsNone(wall_from_details(d))


if __name__ == "__main__":
    unittest.main()
