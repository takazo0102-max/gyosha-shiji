"""日建 NDシステム ストロング（仮設資材カタログ Vol.10 p042〜046）と、足場の種類の選び方."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.master import SERIES_LABELS, load_master, series_from_label
from ashiba.structural import load_capacities

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 15400}


class TestStrong(unittest.TestCase):
    def test_master_has_its_own_posts_and_shares_the_rest(self):
        m = load_master("nikken_strong")
        posts = {p.model_no: p for p in m.by_category("支柱")}
        self.assertEqual(posts["NSP36"].weight_kg, 13.91)
        self.assertIn(1575, m.post_lengths())                     # S支柱 NSPS15
        self.assertTrue(m.find("布材", 1829))                     # つなぎ材は ND1800 と共通（NDT18）
        self.assertEqual(m.find("布材", 1829).model_no, "NDT18")

    def test_post_capacity_is_higher_than_nd1800(self):
        s = load_capacities("nikken_strong")
        n = load_capacities("nikken_nd1800")
        key = next(k for k in s if "支柱許容圧縮耐力" in str(k))
        self.assertGreater(s[key].value, n[key].value)

    def test_solves_and_counts_joints(self):
        r = solve_all({**RECT, "series_id": "nikken_strong"})
        q = {l.part.model_no: l.qty for l in r.quantity.lines}
        self.assertIn("NSP36", q)
        self.assertIn("NSBC", q)
        n_feet = q["NSBC"]
        self.assertEqual(q["NS30"], n_feet * (len(r.model.elevation.posts) - 1))


class TestScaffoldTypeLabels(unittest.TestCase):
    def test_label_round_trip(self):
        from ashiba.spec_object import params_from_spec, spec_from_params

        self.assertEqual(series_from_label(SERIES_LABELS["nikken_strong"]), "nikken_strong")
        self.assertEqual(series_from_label("nikken_nd1800"), "nikken_nd1800")
        p = params_from_spec({"series_id": "waku"})
        self.assertEqual(p["seriesId"], SERIES_LABELS["waku"])
        self.assertEqual(spec_from_params({"seriesId": SERIES_LABELS["waku"]})["series_id"], "waku")

    def test_label_solves(self):
        r = solve_all({**RECT, "series_id": SERIES_LABELS["nikken_strong"], "module": "inch"})
        self.assertEqual(r.model.master.series_id, "nikken_strong")


if __name__ == "__main__":
    unittest.main()


class TestMillennium(unittest.TestCase):
    """日建 ミレニューム（カタログ Vol.10 p048〜053）."""

    def test_own_posts_ledgers_and_shared_decks(self):
        m = load_master("nikken_millennium")
        self.assertEqual({p.model_no for p in m.by_category("支柱")} >= {"P36G", "P27G", "P18G"}, True)
        self.assertEqual(m.find("布材", 1829).model_no, "SC18G")
        self.assertEqual(m.find("先行手摺", 1829).model_no, "STXC1809G")
        self.assertTrue(any(p.model_no.startswith("NDN") for p in m.by_category("踏板")))   # 布板は ND と共通

    def test_solves_with_advance_rails(self):
        r = solve_all({**RECT, "series_id": "nikken_millennium", "guard_rail_type": "先行手すり"})
        q = {l.part.model_no: l.qty for l in r.quantity.lines}
        self.assertIn("STXC1809G", q)
        self.assertIn("KC1818A", q)
        self.assertTrue(r.verdict["ok"], r.verdict)

    def test_beam_support_allowance_parses_the_smaller_value(self):
        from ashiba.structural import beam_support_allowable_kn

        fc2 = next(p for p in load_master("nikken_millennium").by_category("梁枠") if p.model_no == "FC2G")
        self.assertEqual(beam_support_allowable_kn(fc2), 5.4)


class TestCatalogAttachments(unittest.TestCase):
    """カタログの付属品: ネット専用ブラケット NL500（p109）・スプリングメッシュ MS1851（p111）・枠組の階段開口部幅木（p093）."""

    def test_nikken_counts_net_brackets_and_mesh_sheets(self):
        for sid in ("nikken_nd1800", "nikken_strong", "nikken_millennium", "waku"):
            with self.subTest(sid):
                r = solve_all({**RECT, "series_id": sid, "horizontal_net_levels": [2]})
                q = {l.part.model_no: l.qty for l in r.quantity.lines}
                self.assertGreater(q.get("NL500", 0), 0)
                self.assertGreater(q.get("MS1851", 0), 0)
                self.assertTrue(any(n.startswith("メッシュシート（1.8×5.2m）") for n in r.quantity.notes))

    def test_waku_stair_opening_toe_board(self):
        r = solve_all({**RECT, "series_id": "waku"})
        self.assertIn("NFG918", {l.part.model_no for l in r.quantity.lines})
        self.assertFalse(any("階段開口部幅木" in w for w in r.quantity.warnings))


class TestOneSidedCornerStep(unittest.TestCase):
    def test_corner_step_replaces_the_order_note(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800", "scaffold_form": "一側足場"})
        q = {l.part.model_no: l.qty for l in r.quantity.lines}
        self.assertEqual(q.get("NDCS05"), r.model.outer_corner_posts() * r.model.elevation.n_levels)
        self.assertFalse(any("コーナー踏板" in w for w in r.quantity.warnings))
