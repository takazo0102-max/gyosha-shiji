"""くさび式: 根がらみ・作業床・手すり・中桟の高さが支柱のコマ（フック）に乗る.

利用者の指摘（2026-10-22）: 支柱のフック位置がずれている、布材とか先行手すりにかかってない。コマは支柱ごとに
上端から koma_pitch で並ぶので、コマピッチの倍数でない支柱（675・1125・1575・225）を積むと上下でコマの並びが
半ピッチずれていた。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all

SERIES = ("shinwa_A", "shinwa_B", "nikken_nd1800", "nikken_nd1900", "nikken_strong", "nikken_millennium")


def _komas(m, e):
    z, out = e.jack_extension, []
    for p in e.posts:
        out += [z + o for o in m.master.post_koma_offsets(p)]
        z += p
    return out


def _off_koma(m, e):
    ks = _komas(m, e)
    rh, mh = m.guard_rail_height_mm, m.midrail_height_mm
    heights = ([e.first_ledger_height] + list(e.level_heights)
               + [h + rh for h in e.level_heights] + [h + mh for h in e.level_heights])
    return [h for h in heights if not any(abs(h - k) <= 1 for k in ks)]


class TestKomaAlignment(unittest.TestCase):
    def test_every_hook_height_is_on_a_koma(self):
        for sid in SERIES:
            for eaves in range(4000, 31000, 2337):
                with self.subTest(sid=sid, eaves=eaves):
                    spec = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "series_id": sid,
                            "eaves_height_mm": eaves, "building_height_mm": eaves + 500,
                            "guard_rail_type": "先行手すり", "asagao": {"stages": 1}}
                    m = solve_all(spec).model
                    e = m.elevation
                    self.assertEqual(_off_koma(m, e), [], e.posts)
                    # 積む支柱はコマピッチの倍数だけ（端数はジャッキ）
                    self.assertTrue(all(p % m.master.koma_pitch == 0 for p in e.posts), e.posts)

    def test_setback_faces_too(self):
        spec = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "series_id": "nikken_strong",
                "eaves_height_mm": 12000, "building_height_mm": 12500, "face_eaves_mm": {"南面": 6700, "東面": 9100}}
        m = solve_all(spec).model
        for ep in m.plan.edges:
            e = m.elevation_of(ep.edge_index)
            self.assertEqual(_off_koma(m, e), [], e.posts)



class TestStairHalfDeck(unittest.TestCase):
    def test_914_stair_moves_outside_and_keeps_the_half_anti(self):
        # 幅914（500＋240）の階段は外側に寄せ、階段が上がってくる層も内側の 240（ハーフアンチ）を敷く
        # （利用者の指摘 2026-10-22: 階段外側に寄せて、上にハーフアンチいるよ）
        from pathlib import Path

        from ashiba.gdl_params import line_params

        base = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "module": "inch", "eaves_height_mm": 6000,
                "roof_bridge": False}                                  # 屋上への渡りのアンチは外して比べる
        r = solve_all({**base, "scaffold_width_mm": 914})
        m = r.model
        self.assertTrue(m.stair_half_deck)
        q = {ln.part.model_no: ln.qty for ln in r.quantity.lines if ln.part and ln.part.category == "踏板"}
        outer = sum(v for k, v in q.items() if not k.endswith("24"))
        inner = sum(v for k, v in q.items() if k.endswith("24"))
        n_open = len(m.elevation.level_heights) * len(r.stair_plan.towers)
        self.assertEqual(inner - outer, n_open)
        self.assertEqual(line_params(m, m.plan.edges[0])["stHalf"], 1)
        narrow = solve_all({**base, "scaffold_width_mm": 610}).model
        self.assertFalse(narrow.stair_half_deck)                       # 1枚敷き（610）は従来どおり全幅を開ける
        d3 = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_line" / "scripts" / "3d.gdl"
              ).read_text(encoding="utf-8")
        self.assertIn("if stHalf = 1 and stOut = 0 then fy0 = -rowW + 0.05 + (deckW1 - 0.01 - fw) / 2", d3)
        self.assertIn("if skipDeck = 1 and stHalf = 1 and stOut = 0 then", d3)


if __name__ == "__main__":
    unittest.main()
