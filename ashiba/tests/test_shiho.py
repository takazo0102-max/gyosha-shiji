"""山留め支保工（src/ashiba/shiho.py・scripts/shiho_run.py。利用者の指定 2026-11-06「縦横の切梁と中間杭も足して 切張り・腹起こしは
手動でできるようにして LOD高く」）."""

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba import retaining as RT  # noqa: E402
from ashiba import shiho as SH  # noqa: E402


def _pit(w=20000.0, d=12000.0, depth=7000.0, support="auto"):
    return RT.plan(RT.Wall("試し", "oyagui", pts=[(0, 0), (w, 0), (w, d), (0, d)], closed=True, depth=depth, support=support))


class TestCompose(unittest.TestCase):
    def test_strut_is_main_aux_and_jack(self):
        """切梁は主材（0.5m 刻みの定尺）＋補助ピース＋キリンジャッキ（450〜600）で長さちょうど（ヒロセ p.09・p.15）."""
        for L in (3000.0, 4980.0, 10900.0, 10949.0, 18900.0, 23456.0):
            seq = SH.compose(L)
            self.assertAlmostEqual(sum(v for _t, v in seq), L, places=6)
            j = [v for t, v in seq if t == "jack"]
            self.assertEqual(len(j), 1)
            self.assertTrue(SH.JACK_RANGE[0] - 1e-6 <= j[0] <= SH.JACK_RANGE[1] + 1e-6, (L, seq))
            for t, v in seq:
                if t == "main":
                    self.assertIn(v, SH.MAIN_MM)
                if t == "aux":
                    self.assertIn(v, SH.AUX_MM)

    def test_main_pieces_prefer_long(self):
        self.assertEqual(SH.split_main(15000.0), [7000.0, 7000.0, 1000.0])
        self.assertEqual(SH.split_main(14500.0), [7000.0, 6500.0, 1000.0])
        self.assertEqual(SH.split_main(500.0), [])

    def test_wale_has_no_jack(self):
        seq = SH.compose(4980.0, jack=False)
        self.assertNotIn("jack", [t for t, _v in seq])
        self.assertLess(4980.0 - sum(v for _t, v in seq), 100.0)

    def test_jack_side_reverses(self):
        m = SH.Member("strut", (0, 0), (10900, 0), jack=2)
        self.assertEqual(SH.segments(m)[-1][0], "jack")
        m.jack = 1
        self.assertEqual(SH.segments(m)[0][0], "jack")


class TestGrid(unittest.TestCase):
    def test_wide_pit_gets_grid(self):
        """広い根切りの「自動」は縦横の切梁（短い向きの腹起しが隅火打ちの間で 5m を超える）. 狭いものは1方向のまま."""
        self.assertTrue(RT.use_grid(_pit()))
        self.assertFalse(RT.use_grid(_pit(4500.0, 3000.0, 5000.0)))
        self.assertFalse(RT.use_grid(_pit(support="wale")))
        self.assertTrue(RT.use_grid(_pit(8000.0, 6000.0, 5000.0, support="grid")))

    def test_wales_in_two_tiers(self):
        """腹起しは長い辺が下段・短い辺が上段、角は通して隅部ピース（ヒロセ p.06・p.15）. 一方向の切梁は出さない."""
        w = _pit()
        self.assertEqual([e.tier for e in w.edges], [0, 1, 0, 1])
        self.assertTrue(all(e.corner_piece for e in w.edges))
        f = RT.face_offset(w) + RT.WALE_GAP_MM
        self.assertAlmostEqual(w.edges[0].wale_x[0], f)
        self.assertFalse(any(e.strut_x for e in w.edges))
        p = RT.part_params(w, w.edges[1])
        self.assertEqual(p["wlTier"], 1)
        self.assertTrue(p["cnOn"])
        self.assertEqual(p["sbX"], "")

    def test_struts_cross_and_piles(self):
        w = _pit()
        ms = SH.grid(w)
        st = [m for m in ms if m.kind == "strut"]
        lo = [m for m in st if m.tier == 0 and m.level == 0]
        up = [m for m in st if m.tier == 1 and m.level == 0]
        self.assertEqual((len(lo), len(up)), (4, 3))
        # 間隔は 5m 以下、上段は H 1本分上
        xs = sorted(m.a[0] for m in lo)
        self.assertTrue(all(b - a <= RT.STRUT_PITCH_MM + 1e-6 for a, b in zip(xs, xs[1:])))
        self.assertAlmostEqual(lo[0].z - up[0].z, 300.0)
        # 下段の切梁は腹起しの前の面から前の面まで
        front = RT.face_offset(w) + RT.WALE_GAP_MM + 300.0
        self.assertAlmostEqual(lo[0].length, 12000.0 - 2 * front)
        # 交点は上段の部材に控え、交点ごとに中間杭（段をまとめて1本）
        self.assertEqual(sum(len(m.crossings) for m in st), 4 * 3 * len(w.wales))
        piles = [m for m in ms if m.kind == "pile"]
        self.assertEqual(len(piles), 12)
        self.assertEqual(len(piles[0].brackets), len(w.wales))
        self.assertAlmostEqual(piles[0].bottom, w.depth + w.embed_mm)
        # 杭は切梁にぶつからない（両方の切梁の芯から フランジの半分＋すき間＋杭の半分）
        for p in piles:
            for m in st:
                if m.level:
                    continue
                u = ((m.b[0] - m.a[0]) / m.length, (m.b[1] - m.a[1]) / m.length)
                dist = abs((p.a[0] - m.a[0]) * u[1] - (p.a[1] - m.a[1]) * u[0])
                self.assertGreaterEqual(dist, 150.0 + 150.0 - 1e-6)
        # ジャッキは千鳥（隣の切梁で反対の端）
        self.assertNotEqual(lo[0].jack, lo[1].jack)

    def test_strut_hiuchi(self):
        """切梁火打ち（利用者の指定 2026-11-06「火打も入れて」）: 切梁の両端の左右に対称に 45°、主材 1.0m＋火打受ピース2個で、腹起しに
        当たる点は切梁の芯から約 1.5m（火打ブロック 30HB: ヒロセ p.17）. 隅火打ち・隣の火打ちと当たる端は左右とも入れない."""
        w = _pit()
        ms = SH.grid(w)
        hs = [m for m in ms if m.kind == "hiuchi"]
        self.assertEqual(len(hs), 2 * 2 * 2 * 2)              # 下段の真ん中2本 × 両端 × 左右 × 2段
        self.assertEqual(w.hi_skipped, 10)
        self.assertIn("切梁火打ち", [c.item for c in w.checks])
        self.assertEqual({m.tier for m in hs}, {0})
        h = hs[0]
        self.assertAlmostEqual(h.length, 2000.0)
        self.assertEqual(SH.segments(h), [("piece", 500.0), ("main", 1000.0), ("piece", 500.0)])
        self.assertAlmostEqual(abs(h.b[0] - h.a[0]), abs(h.b[1] - h.a[1]))     # 45°
        # 始めは腹起しの前の面、終わりは切梁の脇
        front = RT.face_offset(w) + RT.WALE_GAP_MM + 300.0
        self.assertAlmostEqual(h.a[1], front)
        strut = next(m for m in ms if m.kind == "strut" and m.tier == 0 and abs(m.a[0] - h.b[0]) <= 150.0 + 1e-6)
        self.assertAlmostEqual(abs(h.a[0] - strut.a[0]), 150.0 + SH.HIUCHI_S_LEG_MM)
        self.assertEqual(sorted(m.side for m in hs[:2]), [-1, 1])
        self.assertEqual(SH.part_params(h)["sgT"], "4.0,1.0,4.0")

    def test_strut_hiuchi_off_and_one_way(self):
        w = RT.Wall("試し", "oyagui", pts=[(0, 0), (20000, 0), (20000, 12000), (0, 12000)], closed=True, depth=7000, strut_hiuchi=False)
        self.assertFalse([m for m in SH.grid(RT.plan(w)) if m.kind == "hiuchi"])
        one = _pit(24000.0, 8000.0, 5000.0, support="wale")
        hs = SH.members(one)
        self.assertTrue(hs)
        self.assertEqual({m.kind for m in hs}, {"hiuchi"})
        self.assertIn("火打ち", [q.item for q in RT.quantities(one)])

    def test_quantities_and_report(self):
        w = _pit()
        items = [q.item for q in RT.quantities(w)]
        for it in ("  隅部ピース", "切梁", "  主材 30HA", "  キリンジャッキ", "交差部", "  アングルピース", "  交叉部直ボルト", "中間杭",
                   "  切梁受けブラケット", "  締付用 U ボルト", "副部材（照合）", "隅火打ち", "  隅火打ちの受け材"):
            self.assertIn(it, items)
        st = [c.item for c in w.checks]
        self.assertIn("中間杭", st)
        self.assertIn("腹起しの上下段", st)
        md = RT.report([w])
        self.assertIn("中間杭", md)

    def test_part_params(self):
        w = _pit()
        ms = SH.grid(w)
        up = next(m for m in ms if m.kind == "strut" and m.tier == 1)
        p = SH.part_params(up)
        self.assertEqual(p["shKind"], 1)
        self.assertEqual(len(p["xcX"].split(",")), 4)
        self.assertAlmostEqual(sum(float(v) for v in p["sgL"].split(",")) / 1000.0, p["shL"], places=3)
        pile = next(m for m in ms if m.kind == "pile")
        pp = SH.part_params(pile)
        self.assertEqual(pp["shKind"], 4)
        self.assertAlmostEqual(pp["shL"], (pile.bottom - pile.z) / 1000.0)
        self.assertEqual(len(pp["pkZ"].split(",")), 2)

    def test_struts_for_walkways(self):
        """切梁上の足場は縦横の切梁も読む（山留め壁の部品か、切梁の部品を選ぶ）."""
        import ywall_run as Y

        w = _pit()
        with tempfile.TemporaryDirectory() as d:
            ms = SH.grid(w)
            sg = [f"G{i:04d}" for i in range(len(ms))]
            rec = {"k": {"name": "試し", "kind": "oyagui", "pts": [list(p) for p in w.pts], "closed": True, "depth": 7000.0,
                         "guids": ["W1", "W2", "W3", "W4"], "shiho_guids": sg}}
            (Path(d) / Y.RECORD).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            alls = Y.struts_for(Path(d), ["W1"])
            self.assertEqual(len(alls), sum(1 for m in ms if m.kind == "strut"))
            one = Y.struts_for(Path(d), [sg[0]])
            self.assertEqual(len(one), 1)
            info = Y.sheet_info(Path(d), "試し")
            self.assertTrue(info["grid"])
            self.assertEqual(info["piles"], 12)
            self.assertEqual(len(info["strut_lens"]), 2)


class TestManual(unittest.TestCase):
    def test_tiers_by_direction_and_crossings(self):
        lines = [{"kind": "strut", "a": (0, 0), "b": (0, 12000), "depths": [1000.0, 4000.0], "tier": None},
                 {"kind": "strut", "a": (5000, 0), "b": (5000, 12000), "depths": [1000.0, 4000.0], "tier": None},
                 {"kind": "strut", "a": (-2000, 6000), "b": (8000, 6000), "depths": [1000.0, 4000.0], "tier": None},
                 {"kind": "wale", "a": (-2000, 0), "b": (8000, 0), "depths": [1000.0], "shape": "H-350"}]
        ms = SH.manual(lines)
        st = [m for m in ms if m.kind == "strut"]
        self.assertEqual([m.tier for m in st if m.level == 0], [0, 0, 1])
        up = next(m for m in st if m.tier == 1 and m.level == 0)
        self.assertAlmostEqual(up.z, 700.0)
        cross = SH.crossings(ms)
        self.assertEqual(len(cross), 4)
        self.assertEqual([round(x) for x, _h in up.crossings], [2000, 7000])
        piles = SH.make_piles(ms, cross, 0.0, 9000.0)
        self.assertEqual(len(piles), 2)
        wale = next(m for m in ms if m.kind == "wale")
        self.assertEqual(wale.shape, "H-350")
        self.assertGreaterEqual(len(wale.wale_brackets), 2)
        self.assertNotIn("jack", [t for t, _v in SH.segments(wale)])

    def test_hand_drawn_hiuchi_follows_the_wale(self):
        """手で引いた火打ちの受ピースの底は、始めの近くの腹起しに沿う（線をどちらに引いても）."""
        for b, side in (((1414.0, 1414.0), 1), ((-1414.0, 1414.0), -1)):
            ms = SH.manual([{"kind": "wale", "a": (-5000, 0), "b": (5000, 0), "depths": [1000.0]},
                            {"kind": "hiuchi", "a": (0, 0), "b": b, "depths": [1000.0]}])
            SH.hiuchi_sides(ms)
            self.assertEqual(ms[1].side, side)

    def test_report_lists_members(self):
        ms = SH.manual([{"kind": "hiuchi", "a": (0, 0), "b": (2121, 2121), "depths": [1000.0]}])
        md = SH.report(ms)
        self.assertIn("火打受ピース", md)
        self.assertIn("## 部材", md)

    def test_build_from_record(self):
        import shiho_run as S

        rec = {"lines": {"a:0": {"kind": "strut", "a": [0, 0], "b": [0, 10000], "depths": [1000.0], "tier": None, "jack": True},
                         "b:0": {"kind": "strut", "a": [-3000, 5000], "b": [3000, 5000], "depths": [1000.0], "tier": None, "jack": False},
                         "c:0": {"kind": "pile", "a": [9000, 0], "b": [9000, 3000], "depths": [1000.0]}},
               "cross_piles": True, "pile_bottom": 8000.0}
        ms = S.build(rec)
        kinds = [m.kind for m in ms]
        self.assertEqual(kinds.count("strut"), 2)
        self.assertEqual(kinds.count("pile"), 3)             # 交点 1・線の両端 2
        nojack = next(m for m in ms if m.kind == "strut" and m.tier == 1)
        self.assertEqual(nojack.jack, 0)
        rec["cross_piles"] = False
        self.assertEqual([m.kind for m in S.build(rec)].count("pile"), 2)
        self.assertEqual(S._depths("GL-1000, 4000"), [1000.0, 4000.0])

    def test_struts_for_reads_manual_record(self):
        import shiho_run as S
        import ywall_run as Y

        rec = {"lines": {"a:0": {"kind": "strut", "a": [0, 0], "b": [0, 10000], "depths": [1000.0, 4000.0], "tier": None, "jack": True}},
               "cross_piles": True, "pile_bottom": 8000.0, "gl": 0.0}
        n = len(S.build(rec))
        rec["guids"] = [f"M{i}" for i in range(n)]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / S.RECORD).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            got = Y.struts_for(Path(d), ["M1"])
            self.assertEqual(len(got), 1)
            beam = next(iter(got.values()))
            self.assertAlmostEqual(beam["top"], -4000.0 + 150.0)
            self.assertEqual(len(Y.struts_for(Path(d))), 2)


class TestGdl(unittest.TestCase):
    def test_part_is_registered(self):
        from ashiba.library_versions import BASES
        from ashiba.pens import DRAFT_PARTS
        from ashiba.tapir_adapter import is_ashiba_part

        import build_dist_gsm
        import run_from_archicad as R

        self.assertIn("ashiba_shiho", BASES)
        self.assertIn("ashiba_shiho", DRAFT_PARTS)
        self.assertIn("ashiba_shiho", build_dist_gsm.PARTS)
        self.assertIn("ashiba_shiho", R.SEPARATE_OBJECTS)
        self.assertTrue(is_ashiba_part("ashiba_shiho"))

    def test_generated_scripts_match(self):
        import gen_shiho_gdl as G

        hsf = ROOT / "gdl" / "hsf" / "ashiba_shiho"
        self.assertEqual((hsf / "scripts" / "3d.gdl").read_text(encoding="utf-8"), G.SCRIPT_3D)
        self.assertEqual((hsf / "scripts" / "2d.gdl").read_text(encoding="utf-8"), G.SCRIPT_2D)
        self.assertEqual((hsf / "paramlist.xml").read_text(encoding="utf-8"), G.paramlist())
        # 配列の名前とパラメータの名前は大文字小文字を除いて重ならない（GDL は区別しない）
        import re

        params = {m.lower() for m in re.findall(r'Name="(\w+)"', G.paramlist())}
        arrays = {m.lower() for m in re.findall(r"dim (\w+)\[\]", G.SCRIPT_1D)}
        self.assertFalse(params & arrays, params & arrays)


if __name__ == "__main__":
    unittest.main()
