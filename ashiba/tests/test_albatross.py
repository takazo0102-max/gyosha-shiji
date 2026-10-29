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
        self.assertEqual(sorted(p.weight_kg for p in deck), [7.0, 8.5, 15.8])        # 500・240・150（狭小地）
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


class TestAlbatrossGapBoards(unittest.TestCase):
    def test_stage_gap_is_closed_by_the_hooked_gap_board(self):
        # 幅1219 に布板 500×2 で残る 189 は、フック付すきま埋め板（幅175、p045）で残り 14mm（3cm 以下）
        from ashiba.interior_stage import solve_stage

        r = solve_stage({"name": "s", "corners_mm": [[0, 0], [6000, 0], [6000, 4000], [0, 4000]], "deck_mm": 4000},
                        load_master("albatross"), load_capacities("albatross"))
        why = next(q[3] for q in r.quantity if q[0] == "すき間板")
        self.assertIn("34818（幅175）を入れて残り 14mm", why)


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

    def test_mesh_sheets_and_net_brackets_are_sugiko_parts(self):
        # ライトネス（p357）は足場のスパンの幅どおり。ネットブラケット 27300（p356）は腕の寸法が資料に無いので NL500 で仮に判定
        r = solve_all({**RECT, "horizontal_net_levels": [2], "site": {"sheet_type": "メッシュシート"}})
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        self.assertGreater(q.get("81418", 0), 0)
        self.assertGreater(q.get("27300", 0), 0)
        self.assertFalse(any("マスタに無い幅" in n for n in r.quantity.notes))
        self.assertTrue(any("27300 の腕の届きは資料に無い" in n for n in r.quantity.notes))

    def test_bottom_post_has_a_negarami_plate(self):
        # 最下層の支柱は根がらみプレート付き（2700・1350・900・675・225。スギコ カタログ p062・p083）。1800・3600 は使えない
        for h in (4000, 6500, 9000, 12000, 15400, 20000, 31000):
            with self.subTest(h=h):
                e = solve_all({**RECT, "eaves_height_mm": h}).model.elevation
                self.assertIn(e.posts[0], (2700, 1350, 900, 675, 225), e.posts)

    def test_negarami_on_the_bottom_plate(self):
        # 根がらみプレート付支柱（2700 等）の下端から約130 のプレートに根がらみを掛ける（入れる前は 450 の高さだった。
        # p027 の図・p147「根がらみは最下端の根がらみフランジに」）
        e = solve_all({**RECT, "eaves_height_mm": 9000}).model.elevation
        self.assertEqual(e.posts[0], 2700)
        self.assertEqual(e.first_ledger_height, e.jack_extension + 130)
        m = load_master("albatross")
        self.assertEqual(m.post_koma_offsets(2700)[:2], [130, 400])
        self.assertEqual(m.post_koma_offsets(1800)[0], 400)            # 1800・3600 は根がらみプレート無し

    def test_no_under_base_but_sill_boards(self):
        # アンダーベースの品は無い（カタログ p083: ジャッキベースは敷板に釘等で固定）。「マスタに無い」と出さない
        r = solve_all(RECT)
        self.assertFalse(any("アンダーベース（数量" in n for n in r.quantity.notes))
        self.assertTrue(any("敷板（敷角）の中心に置いて釘等で固定" in n for n in r.quantity.notes))

    def test_narrow_boards_only_for_tight_spots(self):
        # 150幅鋼製板（狭小地システム p043）は本体の床の組に入れない（p025: 幅610は500幅の布板）。屋上への渡りで
        # 240 のアンチだとブラケット 305 が離れ 270 より長くなるので、150 の板と 153 のブラケットに選び直す
        m = load_master("albatross")
        self.assertNotIn(150, m.deck_widths_available())
        self.assertEqual(m.width_setup(610)[1], (500,))
        r = solve_all({**RECT, "guard_rail_type": "先行手すり"})
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        self.assertNotIn("34669", q)                                 # 本体の床に 150 を敷かない
        b = r.model.roof_bridges[0]
        self.assertEqual((b.deck, b.bracket.split()[0]), ([150], "50353"))
        self.assertFalse(any("より長いので" in str(w) for w in r.warnings))

    def test_ledger_rails_become_advance_braces(self):
        # 外側の面の全層・全スパンに先行手摺ブレス（筋かいを兼ねる。p084）。布材だと筋かいが1本も無い足場になっていた
        r = solve_all({**RECT, "guard_rail_type": "布材"})
        self.assertEqual(r.model.config.guard_rail_type, "先行手すり")
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        self.assertGreater(q.get("50118", 0), 0)
        self.assertTrue(any("先行手摺ブレス（筋かいを兼ねる）" in str(w) for w in r.warnings))
        nd = solve_all({**RECT, "series_id": "nikken_nd1800", "guard_rail_type": "布材"})
        self.assertEqual(nd.model.config.guard_rail_type, "布材")       # 日建は布材のまま（筋交 NDBR を数える）

    def test_open_ends_use_end_side_braces(self):
        # 端の面（妻側）は妻側ブレス（認定品 p029）。入れる前は通常の先行手摺ブレス 50106 を当てていた
        r = solve_all({**RECT, "end_guard": "ブレス材", "faces": ["南面"]})
        q = {l.part.model_no: l.qty for l in r.quantity.lines if l.part}
        self.assertEqual(q.get("50840"), 10)                      # 610・端2か所×5層
        self.assertNotIn("50106", q)

    def test_spec_object_lists_the_series(self):
        from pathlib import Path

        vl = (Path(__file__).resolve().parents[1] / "gdl" / "hsf" / "ashiba_spec" / "scripts" / "vl.gdl").read_text(
            encoding="utf-8")
        self.assertIn(SERIES_LABELS["albatross"], vl)


if __name__ == "__main__":
    unittest.main()
