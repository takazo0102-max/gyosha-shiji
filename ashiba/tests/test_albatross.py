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


class TestAlbatrossSolve(unittest.TestCase):
    def test_solves_with_its_own_parts(self):
        r = solve_all({**RECT, "guard_rail_type": "先行手すり", "asagao": {"stages": 1}})
        self.assertTrue(r.verdict["ok"], r.verdict)
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        for code in ("50036", "50218", "50118", "N6", "35585", "37751", "ALA-1829", "39063+39064"):
            self.assertIn(code, q)
        self.assertFalse(any(k.startswith(("ND", "NDP", "SC")) for k in q), q)   # 日建の品が混ざらない

    def test_spec_object_lists_the_series(self):
        from pathlib import Path

        vl = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_spec" / "scripts" / "vl.gdl").read_text(
            encoding="utf-8")
        self.assertIn(SERIES_LABELS["albatross"], vl)


if __name__ == "__main__":
    unittest.main()
