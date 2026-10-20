"""支柱のコマ（フックを掛ける座）の位置（利用者の指摘 2026-10-21: 450ピッチで来るはず、2700は根がらみ用のフック）.

カタログの支柱図（日建 仮設資材カタログ Vol.10）:
- ND1800 p003: NDP36N 395・845…3545（上端から55、450ピッチ）、NDP27N 170・395・845…2645、NDP11N 170・395・620・1070
- ストロング p042: ND1800 と同じ並び
- ミレニューム p050: P36G 420…3570（上端から30）、P27G 120・420…2670
"""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.gdl_params import line_params
from ashiba.master import load_master

RECT = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000}


class TestCatalog(unittest.TestCase):
    def test_nd1800(self):
        m = load_master("nikken_nd1800")
        self.assertEqual(m.post_koma_offsets(3600), [395 + 450 * k for k in range(8)])
        self.assertEqual(m.post_koma_offsets(2700), [170] + [395 + 450 * k for k in range(6)])
        self.assertEqual(m.post_koma_offsets(1800), [395, 845, 1295, 1745])
        self.assertEqual(m.post_koma_offsets(1125), [170, 395, 620, 1070])
        self.assertEqual(m.post_koma_offsets(900), [170, 395, 845])

    def test_strong_and_millennium(self):
        self.assertEqual(load_master("nikken_strong").post_koma_offsets(2700),
                         load_master("nikken_nd1800").post_koma_offsets(2700))
        mi = load_master("nikken_millennium")
        self.assertEqual(mi.post_koma_offsets(3600), [420 + 450 * k for k in range(8)])
        self.assertEqual(mi.post_koma_offsets(2700), [120] + [420 + 450 * k for k in range(6)])

    def test_frame_has_none(self):
        self.assertEqual(load_master("waku").post_koma_offsets(1700), [])


class TestLevelsSitOnKomas(unittest.TestCase):
    """根がらみ・各作業床・中桟・手すりが、積んだ支柱のコマの高さに来る."""

    def _komas(self, model):
        e = model.elevation
        out, zb = set(), e.jack_extension
        for p in e.posts:
            out |= {zb + v for v in model.master.post_koma_offsets(p)}
            zb += p
        return out

    def test_every_hook_height_is_a_koma(self):
        for sid in ("nikken_nd1800", "nikken_strong", "nikken_millennium"):
            r = solve_all({**RECT, "series_id": sid})
            m, e = r.model, r.model.elevation
            komas = self._komas(m)
            self.assertEqual(e.posts[0], 2700, sid)
            self.assertIn(e.first_ledger_height, komas, sid)
            # 根がらみは 2700 の根がらみ用のコマ（下端から 170／120）
            self.assertEqual(e.first_ledger_height - e.jack_extension, min(m.master.post_koma_offsets(2700)), sid)
            for h in e.level_heights:
                for dz in (0, m.midrail_height_mm, m.guard_rail_height_mm):
                    if h + dz < e.total_height:
                        self.assertIn(h + dz, komas, (sid, h, dz))
            # 継ぎ目（支柱の突き合わせ）にはコマが無い
            zb = e.jack_extension
            for p in e.posts[:-1]:
                zb += p
                self.assertNotIn(zb, komas, sid)

    def test_top_floor_still_reaches_the_eaves(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        self.assertGreaterEqual(r.model.elevation.level_heights[-1], 9000 - 150)


class TestGdl(unittest.TestCase):
    def test_params_and_script(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        p = line_params(r.model, r.model.plan.edges[0])
        self.assertAlmostEqual(p["komaGap"], 0.055)
        self.assertAlmostEqual(p["komaNega"], 0.170)
        self.assertEqual(p["negaLens"], "2700,1125,900,675,450")
        g3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl").read_text(
            encoding="utf-8")
        self.assertIn("zz = pl - komaGap", g3)
        self.assertIn("kzAll[nKzA] = zb + komaNega", g3)


if __name__ == "__main__":
    unittest.main()
