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


if __name__ == "__main__":
    unittest.main()
