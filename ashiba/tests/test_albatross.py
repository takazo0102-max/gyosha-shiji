"""スギコ アルバトロス（利用者の指定 2026-10-29: アルバロスの材料も対応できるようにして。スギコ カタログ vol.7 p025〜051）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.master import SERIES_CONST, SERIES_LABELS, load_master, series_from_label
from ashiba.structural import load_capacities

RECT = {"outline_mm": [[0, 0], [12000, 0], [12000, 8000], [0, 8000]], "eaves_height_mm": 9000,
        "series_id": "albatross"}


class TestAlbatrossMaster(unittest.TestCase):
    def test_series_constants(self):
        c = SERIES_CONST["albatross"]
        self.assertEqual((c["koma_pitch"], c["floor_height"], c["hozo"], c["module"]), (450, 1800, 130, "inch"))
        self.assertEqual(series_from_label(SERIES_LABELS["albatross"]), "albatross")

    def test_catalog_parts(self):
        m = load_master("albatross")
        self.assertEqual(m.span_lengths(), [1829, 1524, 1219, 914, 610])
        post = {p.nominal_dim: p for p in m.by_category("支柱")}
        self.assertEqual((post[3600].model_no, post[3600].weight_kg, post[3600].actual_dim), ("50036", 12.6, 3730))
        self.assertEqual(m.find("布材", 1829).model_no, "50218")
        self.assertEqual(m.find("先行手摺", 1829).weight_kg, 6.9)
        self.assertEqual(m.find("幅木", 1219).model_no, "34852")
        deck = [p for p in m.by_category("踏板") if p.nominal_dim == 1829]
        self.assertEqual(sorted(p.weight_kg for p in deck), [8.5, 15.8])
        jack = m.by_category("ジャッキ")[0]
        self.assertEqual((jack.model_no, jack.max_extension_mm()), ("37751", 255))
        tie = [p for p in m.by_category("壁つなぎ") if p.covers(600)]
        self.assertTrue(any(p.model_no == "28226" for p in tie))          # 自在4型 550〜740

    def test_capacities(self):
        caps = load_capacities("albatross")
        self.assertEqual(caps[("支柱許容圧縮耐力", "0")].value, 12.5)
        self.assertTrue(caps[("支柱許容圧縮耐力", "0")].verified)
        self.assertFalse(caps[("ジャッキ許容支持力", "250")].verified)  # ジャッキは資料に無い（暫定）
        self.assertEqual(caps[("作業床許容積載荷重", "スパン")].value, 2.45)


class TestAlbatrossCollars(unittest.TestCase):
    def test_stair_feet_use_adjusting_collars(self):
        """階段の上は調整カラーを支柱の下に継いで合わせる（ジャッキ 255 と敷板だけでは1列が受けきれず NG だった）."""
        from ashiba.interior_stage import solve_stage, stage_report

        r = solve_stage({"name": "階段室", "corners_mm": [[0, 0], [6000, 0], [6000, 2800], [0, 2800]], "deck_mm": 4500,
                         "stair": {"axis": "u", "from_mm": 750, "tread_mm": 250, "riser_mm": 180, "steps": 16}},
                        load_master("albatross"), load_capacities("albatross"))
        c = next(c for c in r.checks if c.item == "階段の上の支柱")
        self.assertEqual(c.status, "OK", c.message)
        self.assertIn("頭つなぎ", c.message)
        for f in r.stair_feet:
            self.assertLessEqual(f["jack_mm"], 255)
            self.assertEqual(f["shim"], 0)
            # 段＋ジャッキ＋調整カラー＋支柱 ＝ 支柱の天端（コマは天端からそろう）
            self.assertEqual(f["z_mm"] + f["jack_mm"] + f["collar_mm"] + sum(f["posts"]), r.top_mm)
        self.assertTrue(any(q[0] == "調整カラー" for q in r.quantity))
        self.assertIn("調整カラー", stage_report(r))

    def test_no_collars_for_other_series(self):
        self.assertEqual(load_master("nikken_nd1800").by_category("調整カラー"), [])


class TestAlbatrossStruts(unittest.TestCase):
    """強化方杖（スギコ カタログ p035・p059）: 支柱の許容 12.5 → 23.5kN/本、腕木の下に足す（腕木は布材のまま）."""

    def test_struts_raise_the_post_allowance(self):
        base = {**RECT, "eaves_height_mm": 40000, "guard_rail_type": "先行手すり", "site": {"sheet_type": "防音シート"}}
        plain = solve_all(base)
        strut = solve_all({**base, "post_reinforcement": "強化方杖"})
        self.assertEqual(plain.structural.post.allowable_kn, 12.5)
        self.assertEqual(strut.structural.post.allowable_kn, 23.5)   # ジャッキの暫定値（23.5）に頭を押さえられない
        q = {l.part.model_no: l.qty for l in strut.quantity.lines if l.part}
        n_levels = strut.model.elevation.n_levels
        self.assertGreater(q["50810"], 0)
        self.assertEqual(q["50810"] % n_levels, 0)
        self.assertEqual(q.get("50212", 0), {l.part.model_no: l.qty for l in plain.quantity.lines if l.part}.get("50212", 0))
        self.assertTrue(any("強化方杖を使うときは壁つなぎが必要" in n for n in strut.quantity.notes))

    def test_struts_are_only_for_series_that_have_them(self):
        from ashiba.structural import CapacityError

        with self.assertRaises(CapacityError):
            solve_all({**RECT, "series_id": "shinwa_A", "post_reinforcement": "強化方杖"})


class TestAlbatrossSolve(unittest.TestCase):
    def test_solves_with_its_own_parts(self):
        r = solve_all({**RECT, "guard_rail_type": "先行手すり", "asagao": {"stages": 1}})
        self.assertTrue(r.verdict["ok"], r.verdict)
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        for code in ("50036", "50218", "50118", "N6", "35585", "37751", "ALA-1829", "39063+39064"):
            self.assertIn(code, q)
        self.assertFalse(any(k.startswith(("ND", "NDP", "SC")) for k in q), q)   # 日建の品が混ざらない

    def test_asagao_corners_are_counted(self):
        # 朝顔コーナー（スギコ カタログ p052〜053）: 出隅4か所×2段。入れる前は「マスタに無いので計上していない」だった
        r = solve_all({**RECT, "asagao": {"stages": 2}})
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        self.assertEqual(q.get("ALAC-SET"), 8)
        self.assertFalse(any("朝顔コーナーがマスタに無い" in n for n in r.quantity.notes))

    def test_spec_object_lists_the_series(self):
        from pathlib import Path

        vl = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_spec" / "scripts" / "vl.gdl").read_text(
            encoding="utf-8")
        self.assertIn(SERIES_LABELS["albatross"], vl)


if __name__ == "__main__":
    unittest.main()
