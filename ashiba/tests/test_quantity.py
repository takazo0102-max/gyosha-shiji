import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import QuantityRules, take_off

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


class TestQuantity(unittest.TestCase):
    def setUp(self):
        self.master = load_master("shinwa_A")
        self.plan = solve_plan(RECT, self.master)
        self.elev = solve_elevation(16300, master=self.master)
        self.model = ScaffoldModel(
            master=self.master,
            plan=self.plan,
            elevation=self.elev,
            config=ScaffoldConfig(),
            building_height_mm=16000,
        )
        self.q = take_off(self.model)

    def test_dependent_parts_rules(self):
        # アンダーベース数 = ジャッキ数 = 支柱位置数×2列（本足場）
        n_jack = self.q.qty_of("ジャッキ")  # ジャッキ+アンダーベース両方このカテゴリ
        jacks = [l for l in self.q.lines if l.part.category == "ジャッキ"]
        by_note = {("アンダーベース" in l.part.note): l.qty for l in jacks}
        self.assertEqual(by_note[True], by_note[False])
        # ＋出隅の外側コーナー支柱（四隅）
        # 各面の両端を含む支柱の位置（隅の内側建地は共有）。外側の列の終点の支柱も（利用者の指摘 2026-10-25: 支柱の
        # 本数の数え漏れも直して）
        from ashiba.quantity import standing_post_positions

        self.assertEqual(by_note[False], standing_post_positions(self.model, 2))
        self.assertEqual(by_note[False], self.plan.total_posts * 2 + 4 + 4)
        self.assertEqual(self.model.outer_corner_posts(), 4)

    def test_posts_match_what_the_line_draws(self):
        # 3d.gdl と同じ描き分け（面ごとに両端を含む位置 × 内外、隅の内側建地は共有、出隅の外側の角）で数えた本数と
        # 数量の脚の数が一致する（利用者の指摘 2026-10-25: 支柱の本数の数え漏れも直して）
        from ashiba.gdl_params import line_params

        drawn = 0
        for ep in self.model.plan.edges:
            p = line_params(self.model, ep)
            for row in (0, 1):
                for i in range(len(ep.spans) + 1):
                    first, last = i == 0, i == len(ep.spans)
                    if row == 0 and ((first and p["skipInS"]) or (last and p["skipInE"])):
                        continue
                    if (first and p["skipPS"]) or (last and p["skipPE"]):
                        continue
                    drawn += 1
            drawn += p["cornerS"] + p["cornerSP"]
        jacks = [l for l in self.q.lines if l.part.category == "ジャッキ" and "アンダー" not in l.part.note]
        self.assertEqual(sum(l.qty for l in jacks), drawn)

    def test_post_counts(self):
        per_line = len(self.elev.posts)
        total = self.q.qty_of("支柱")
        self.assertEqual(total, (self.plan.total_posts * 2 + 4 + 4) * per_line)

    def test_corner_ledgers_and_toe_boards(self):
        """出隅の外側コーナー升目: 布材（腕木寸法）2辺×(根がらみ1＋各層3)、幅木2辺×層."""
        nl = self.elev.n_levels
        udegi = self.model.post_row_spacing_mm
        self.assertEqual(self.q.qty_of("布材", udegi) - self.plan.total_posts * (nl + 1),
                         4 * 2 * (1 + nl * 3))
        self.assertEqual(self.q.qty_of("幅木", udegi), 4 * nl * 2)
        # コーナーの床は長さ＝建地列間隔の踏板で計上（以前は「別途手配」の注意だった）
        self.assertTrue(any(n.startswith("出隅コーナーの床は長さ") for n in self.q.notes), self.q.notes)
        self.assertFalse(any("コーナー踏板" in n for n in self.q.notes), self.q.notes)

    def test_deck_counts(self):
        # 踏板: スパン数×層数×幅構成2枚 ＋ 出隅コーナー4箇所×層数×2枚（長さ＝建地列間隔）
        n_deck = self.q.qty_of("踏板")
        self.assertEqual(
            n_deck, self.plan.total_spans * self.elev.n_levels * 2 + 4 * self.elev.n_levels * 2
        )
        udegi = self.model.post_row_spacing_mm
        self.assertEqual(self.q.qty_of("踏板", udegi) - 0, sum(
            l.qty for l in self.q.lines if l.part.category == "踏板" and l.part.nominal_dim == udegi))

    def test_braces_use_standard_spacing(self):
        """斜材は全構面ではなく設置間隔から算出する.

        くさび式足場用斜材は「6層6スパン以下毎に交さ2方向」が基準。
        全スパン×全層で拾うと1桁多く発注してしまう。
        """
        import math
        rules = QuantityRules()
        level_groups = math.ceil(self.elev.n_levels / rules.brace_every_levels)
        expect = 0
        for e in self.plan.edges:
            fit = sum(1 for s in e.spans if s == 1800)
            want = math.ceil(e.span_count / rules.brace_every_spans)
            expect += min(want, fit) * level_groups
        self.assertEqual(
            self.q.qty_of("筋交"), expect * rules.braces_per_location
        )

    def test_brace_rule_is_stated_in_notes(self):
        """どの間隔で拾ったかを数量表に残す（発注数量が大きく変わるため）."""
        self.assertTrue(any("斜材は" in n and "交さ2方向" in n for n in self.q.notes))

    def test_denser_bracing_is_configurable(self):
        base = self.q.qty_of("筋交")
        dense = take_off(
            self.model,
            rules=QuantityRules(brace_every_spans=1, brace_every_levels=1),
        ).qty_of("筋交")
        self.assertGreater(dense, base)

    def test_stair_rails_counted_without_a_stair_plan(self):
        """階段の配置が無くても、階段の箇所数から階段側の階段手摺を数える（踊り場の床は使わない）."""
        self.model.config.n_stairs = 2
        q = take_off(self.model)
        self.assertGreater(q.qty_of("階段"), 0)
        self.assertEqual(q.qty_of("踊り場"), 0)
        self.assertEqual(q.qty_of("階段手摺"), 2 * self.model.elevation.n_levels * 2)     # 2段

    def test_wide_standoff_notes_the_missing_inner_rail(self):
        """離れ300mm超は躯体側にも墜落防止措置が要る。躯体側手すりを外した計画では数量に無いことを書く."""
        wide = [e for e in self.plan.edges if e.standoff > 300]
        self.assertTrue(wide, "この例題は離れ350mmの面を含む前提")
        self.model.config.inner_guard_rail = False
        q = take_off(self.model)
        self.assertTrue(
            any("手すり材は数量に含んでいません" in n for n in q.notes),
            q.notes,
        )
        # 既定（躯体側の手すり・中桟を布材で組む）では計上済みなので、その注記は出ない
        self.assertFalse(any("手すり材は数量に含んでいません" in n for n in self.q.notes), self.q.notes)

    def test_inner_guard_rail_is_counted_by_default(self):
        """躯体側の手すり＋中桟（布材）は3Dに描くのと同じ条件で数える."""
        nl = self.elev.n_levels
        spans = self.plan.total_spans
        udegi = self.plan.total_posts * (nl + 1)      # 腕木も布材の区分
        corners = 4 * 2 * (1 + nl * 3)                 # 出隅コーナーの升目
        # 根がらみ2＋各層（外側の手すり・中桟2＋躯体側の手すり・中桟2）。作業床の高さの布材は付けない
        self.assertEqual(self.q.qty_of("布材"), spans * (2 + nl * 4) + udegi + corners)
        note = next(n for n in self.q.notes if n.startswith("布材は1スパンあたり"))
        self.assertIn("躯体側の手すり・中桟2本", note)
        self.model.config.inner_guard_rail = False
        q = take_off(self.model)
        self.assertEqual(q.qty_of("布材"), spans * (2 + nl * 2) + udegi + corners)
        self.assertNotIn("躯体側", next(n for n in q.notes if n.startswith("布材は1スパンあたり")))

    def test_no_such_note_when_all_within_300(self):
        for e in self.plan.edges:
            e.standoff = 300.0
        q = take_off(self.model)
        self.assertFalse(any("離れが300mmを超える" in n for n in q.notes))

    def test_kake_menseki(self):
        # (外周100m+4m)×(高さ16m+0.5m)
        self.assertAlmostEqual(self.q.kake_menseki_m2, 104 * 16.5, delta=0.1)

    def test_weight_and_trucks(self):
        self.assertGreater(self.q.total_weight_kg, 0)
        self.assertGreaterEqual(self.q.truck_count, 1)
        calc = sum(l.part.weight_kg * l.qty for l in self.q.lines)
        self.assertAlmostEqual(self.q.total_weight_kg, calc, delta=0.5)

    def test_wall_ties_generated_and_counted(self):
        self.assertTrue(self.model.wall_ties)
        self.assertEqual(self.q.qty_of("壁つなぎ"), len(self.model.wall_ties))
        v_max, h_max = self.model.wall_tie_max_spacing()
        self.assertLessEqual(v_max, 5000)
        self.assertLessEqual(h_max, 5500)

    def test_single_row_scaffold(self):
        cfg = ScaffoldConfig(scaffold_form="一側足場")
        model = ScaffoldModel(
            master=self.master, plan=self.plan, elevation=self.elev, config=cfg
        )
        q = take_off(model)
        jacks = [l for l in q.lines if l.part.category == "ジャッキ" and "アンダー" not in l.part.note]
        # 建地1列＋出隅の外側コーナー支柱（一側でも付く）
        # 建地1列（各面の両端を含む）＋出隅の外側コーナー支柱（一側でも付く）
        self.assertEqual(jacks[0].qty, self.plan.total_posts + len(self.plan.edges) + model.outer_corner_posts())


class TestBreakdownReconcilesWithTheDrawing(unittest.TestCase):
    """同じ型番が複数の用途で足された行は、備考に用途別の内訳を出す.

    壁つなぎは躯体ぶん（図面に○で出る）＋朝顔取付＋ステージ取付が1行に潰れる。
    発注担当が図面の本数と照合できないと、どれが構造で何本かが分からない。
    """

    def _model(self, **cfg):
        from ashiba.model import AsagaoSpec

        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=AsagaoSpec(stages=1), **cfg),
            building_height_mm=16000,
        )

    def test_wall_tie_row_splits_body_and_asagao(self):
        m = self._model()
        q = take_off(m)
        from ashiba.ties import tie_counts

        # 壁つなぎは面の離れごとに品番が分かれる（NK-1925II／NK-2434II…）ので行は複数。
        # 全行の合計は図面の本数、朝顔取付部を含む行には用途別の内訳が付く
        ties = [l for l in q.lines if l.part.category == "壁つなぎ"]
        self.assertEqual(sum(l.qty for l in ties), sum(tie_counts(m).values()))
        asagao = [l for l in ties if "朝顔取付部の壁つなぎ" in l.note]
        self.assertTrue(asagao, [l.note for l in ties])
        import re
        for tie in asagao:
            self.assertIn("内訳:", tie.note)
            nums = [int(x) for x in re.findall(r" (\d+)本", tie.note.split("内訳:")[1])]
            self.assertEqual(sum(nums), tie.qty)   # 内訳の合計は行の数量に一致する

    def test_single_use_part_has_no_breakdown(self):
        # 支柱は1用途しかない。内訳を付けない（ノイズになる）
        m = self._model()
        q = take_off(m)
        post = next(l for l in q.lines if l.part.category == "支柱"
                    and l.qty == max(x.qty for x in q.lines
                                     if x.part.category == "支柱"))
        self.assertEqual(post.note, "")


class TestCategoryTotals(unittest.TestCase):
    def test_totals_match_lines_and_grand_total(self):
        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        q = take_off(m)
        cats = q.category_totals()
        # 分類ごとの数量・重量が明細と一致
        for c, qty, wt in cats:
            self.assertEqual(qty, q.qty_of(c))
        # 重量合計は総重量に一致
        self.assertAlmostEqual(sum(w for _c, _q, w in cats),
                               q.total_weight_kg, delta=0.2)
        # 出現順を保つ（明細の最初の分類がテーブルの先頭）
        self.assertEqual(cats[0][0], q.lines[0].part.category)


class TestWeightPlausibility(unittest.TestCase):
    """架け面積あたりの重量が実務の相場（おおむね15〜22kg/m2）から外れないこと.

    拾いルールを1つ間違えると桁で狂う。合計で歯止めをかけておく。
    """

    def test_wedge_and_frame_are_in_range(self):
        from ashiba.elevation_solver import solve_elevation

        for sid in ("shinwa_A", "shinwa_B", "waku"):
            with self.subTest(sid):
                master = load_master(sid)
                model = ScaffoldModel(
                    master=master, plan=solve_plan(RECT, master),
                    elevation=solve_elevation(16300, master=master),
                    config=ScaffoldConfig(), building_height_mm=16000,
                )
                q = take_off(model)
                per_m2 = q.total_weight_kg / q.kake_menseki_m2
                self.assertGreater(per_m2, 12.0, f"{sid} {per_m2:.1f}kg/m2 は軽すぎる")
                self.assertLess(per_m2, 25.0, f"{sid} {per_m2:.1f}kg/m2 は重すぎる")


class TestCountsAreCheckable(unittest.TestCase):
    """数だけ出しても検算できない。内訳を注記に書く."""

    def setUp(self):
        master = load_master("shinwa_A")
        self.m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )
        self.q = take_off(self.m)

    def test_ledger_breakdown_adds_up(self):
        spans = self.m.plan.total_spans
        posts = self.m.plan.total_posts
        levels = self.m.elevation.n_levels
        per_span = 2 + levels * (2 + 2)          # 根がらみ＋各層(外側の手すり中桟＋躯体側の手すり中桟)。床の高さの布材は無い
        udegi = posts * (levels + 1)
        corners = self.m.outer_corner_posts() * 2 * (1 + levels * 3)
        self.assertEqual(self.q.qty_of("布材"), spans * per_span + udegi + corners)
        notes = " ".join(self.q.notes)
        self.assertIn(f"＝ {per_span}本で計上", notes)
        self.assertIn(f"＝{udegi}本で計上", notes)

    def test_truck_note_states_the_payload(self):
        import math

        from ashiba.quantity import QuantityRules

        payload = QuantityRules().truck_payload_kg
        self.assertEqual(
            self.q.truck_count, math.ceil(self.q.total_weight_kg / payload)
        )
        self.assertTrue(
            any(f"{payload:.0f}kg" in n for n in self.q.notes), self.q.notes
        )


class TestActionableNotes(unittest.TestCase):
    """手配・検討が要る注記は、計上ルールの説明と混ぜない."""

    def setUp(self):
        self.master = load_master("shinwa_A")
        self.model = ScaffoldModel(
            master=self.master, plan=solve_plan(RECT, self.master),
            elevation=solve_elevation(16300, master=self.master),
            config=ScaffoldConfig(), building_height_mm=16000,
        )

    def test_warnings_are_a_subset_of_notes(self):
        q = take_off(self.model)
        for w in q.warnings:
            self.assertIn(w, q.notes)

    def test_counting_rules_are_not_warnings(self):
        q = take_off(self.model)
        self.assertTrue(any("斜材は" in n for n in q.notes))
        self.assertFalse(any("斜材は" in w for w in q.warnings))

    def test_order_and_site_actions_are_separated(self):
        """発注に足すものと現場で対応するものを、同じ分類に放り込まない."""
        from ashiba.model import AsagaoSpec
        from ashiba.platforms import LoadingStage, validate_platforms
        from ashiba.quantity import Notes

        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)),
            building_height_mm=16000,
        )
        pf = validate_platforms(m, [LoadingStage(
            edge_index=0, start_mm=3600, span_count=2,
            projection_mm=1500, load_kn=9.8, levels=[3])])
        q = take_off(m, platforms=pf)
        kinds = {q.warning_kinds[w] for w in q.warnings}
        self.assertEqual(kinds, {Notes.ORDER, Notes.SITE})
        # マスタに無い部材は手配、隙間を塞ぐ話は現場対応
        order = [w for w in q.warnings if q.warning_kinds[w] == Notes.ORDER]
        site = [w for w in q.warnings if q.warning_kinds[w] == Notes.SITE]
        self.assertTrue(any("マスタにありません" in w for w in order), order)
        # 出隅はコーナー材で計上するようになったので、現場対応の例は端数スパンの板
        self.assertTrue(any("呼び寸法が合わない" in w for w in site), site)

    def test_missing_master_part_is_a_warning(self):
        """マスタに無い＝現場で足りない。説明ではなく手配の話."""
        from ashiba.platforms import LoadingStage, validate_platforms

        pf = validate_platforms(self.model, [LoadingStage(
            edge_index=0, start_mm=3600, span_count=2,
            projection_mm=1500, load_kn=9.8, levels=[3],
        )])
        q = take_off(self.model, platforms=pf)
        self.assertTrue(
            any("別途手配" in w for w in q.warnings), q.warnings
        )
        self.assertTrue(
            any("張出ブラケットでは受けられません" in w for w in q.warnings),
            q.warnings,
        )


class TestSingleRowScaffold(unittest.TestCase):
    """一側足場は建地1列・床は1枚敷き。本足場の構成をそのまま数えない."""

    def _model(self, form):
        master = load_master("shinwa_A")
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(scaffold_form=form),
            building_height_mm=16000, clearance_space_mm=500,
        )

    def setUp(self):
        self.both_model = self._model("本足場")
        self.both = take_off(self.both_model)
        self.one = take_off(self._model("一側足場"))

    def test_decks_are_halved(self):
        # 本足場の出隅コーナーの床（長さ＝建地列間隔の踏板2枚×出隅×層）は一側には無い（別途手配の注意）
        m = self.both_model
        corner = m.outer_corner_posts() * m.elevation.n_levels * 2
        self.assertEqual(self.one.qty_of("踏板"), (self.both.qty_of("踏板") - corner) // 2)
        self.assertTrue(any("一側足場のコーナー" in n for n in self.one.notes), self.one.notes)

    def test_only_the_widest_board_is_used(self):
        widths = {
            l.part.note for l in self.one.lines if l.part.category == "踏板"
        }
        self.assertEqual(widths, {"幅400"}, widths)

    def test_deck_brackets_are_counted(self):
        """床が片持ちになるので受けのブラケットが要る（本足場には無い部材）."""
        self.assertEqual(self.both.qty_of("ブラケット"), 0)
        self.assertGreater(self.one.qty_of("ブラケット"), 0)

    def test_substitution_is_stated(self):
        self.assertTrue(any("1枚敷き" in n for n in self.one.notes), self.one.notes)

    def test_law_check_uses_the_same_width(self):
        from ashiba.law_check import run_all_checks

        m = self._model("一側足場")
        deck = [c for c in run_all_checks(m) if c.check_id == 2][0]
        self.assertIn(f"幅{sum(m.deck_widths_in_use)}mm", deck.message)

    def test_drawing_uses_the_same_width(self):
        from ashiba.gdl_params import line_params

        m = self._model("一側足場")
        p = line_params(m, m.plan.edges[0])
        self.assertEqual(p["nRows"], 1)
        self.assertEqual(p["deckW2"], 0.0)


if __name__ == "__main__":
    unittest.main()


class TestDeckCellsReconcile(unittest.TestCase):
    """作業床は「スパン×層」から階段室・開口部を引いた枚数で、注記で検算できる."""

    def _model(self, series):
        master = load_master(series)
        return ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
        )

    @staticmethod
    def _cells(q, category):
        return sum(l.qty for l in q.lines if l.part.category == category)

    def test_frame_opening_removes_deck_and_toe_board_cells(self):
        """枠組の布板も（くさびの踏板と同じく）開口部の梁枠より下は敷かない."""
        from ashiba.openings import Opening, opening_deck_deduction, validate_openings

        m = self._model("waku")
        op = validate_openings(m, [Opening(0, 3658, 3658, level=2)])
        cut = sum(opening_deck_deduction(m, op).values())
        self.assertGreater(cut, 0)
        base, with_op = take_off(m), take_off(m, openings=op)
        n_widths = len(m.config.deck_widths)
        self.assertEqual(
            self._cells(base, "布板") - self._cells(with_op, "布板"), cut * n_widths)
        if m.config.has_toe_board:
            self.assertEqual(
                self._cells(base, "幅木") - self._cells(with_op, "幅木"), cut)
        note = next(n for n in with_op.notes if n.startswith("布板はスパン"))
        self.assertIn(f"開口部（梁枠より下）の{cut}セル", note)

    def test_wedge_note_reconciles_with_the_lines(self):
        import re

        m = self._model("shinwa_A")
        q = take_off(m)
        note = next(n for n in q.notes if n.startswith("踏板はスパン"))
        n_spans, nl = m.plan.total_spans, m.elevation.n_levels
        self.assertIn(f"スパン{n_spans}×作業層{nl}層＝{n_spans * nl}セル", note)
        final = int(re.search(r"(\d+)セルで計上", note).group(1))
        corner = m.outer_corner_posts() * nl * len(m.config.deck_widths)   # 出隅コーナーの床
        per_width = (self._cells(q, "踏板") - corner) / len(m.config.deck_widths)
        self.assertEqual(final, per_width)

    def test_stair_towers_are_named_in_the_note(self):
        from ashiba.stairs import auto_place_stairs

        m = self._model("shinwa_A")
        sp = auto_place_stairs(m)
        q = take_off(m, stair_plan=sp)
        note = next(n for n in q.notes if n.startswith("踏板はスパン"))
        self.assertIn(f"階段室{len(sp.towers)}箇所", note)


class TestTerrainExtensionPostsAreCounted(unittest.TestCase):
    """高低差で継ぎ足した支柱は数量に入る（ジャッキ量一覧にだけ出ていた）."""

    def test_posts_follow_the_feet(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
        )
        ground = GroundModel(points=[(0, 0, 6000), (30000, 0, 0),
                                     (30000, 20000, 0), (0, 20000, 6000)])
        t = solve_post_feet(m, ground)
        flat = take_off(m)
        sloped = take_off(m, terrain=t)

        def posts(q):
            return {l.part.nominal_dim: l.qty for l in q.lines if l.part.category == "支柱"}

        rows = 2
        expect = {}
        for f in t.feet:
            for n in f.posts:
                expect[n] = expect.get(n, 0) + rows
        for n in m.elevation.posts:              # 出隅の外側コーナー支柱（脚一覧に無い）
            expect[n] = expect.get(n, 0) + m.outer_corner_posts()
        self.assertEqual(posts(sloped), expect)
        self.assertGreater(sum(posts(sloped).values()), sum(posts(flat).values()))
        self.assertTrue([n for n in sloped.notes if "継ぎ足し分" in n], sloped.notes)
        self.assertFalse([n for n in flat.notes if "継ぎ足し分" in n])

    def test_frame_stacks_follow_the_feet(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        master = load_master("waku")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
        )
        ground = GroundModel(points=[(0, 0, 6000), (30000, 0, 0),
                                     (30000, 20000, 0), (0, 20000, 6000)])
        t = solve_post_feet(m, ground)
        sloped = take_off(m, terrain=t)
        got = {}
        for l in sloped.lines:
            if l.part.category == "建枠":
                got[l.part.nominal_dim] = got.get(l.part.nominal_dim, 0) + l.qty
        expect = {}
        for f in t.feet:
            for h in f.posts:
                expect[h] = expect.get(h, 0) + 1
        self.assertEqual(got, expect)
        pins = sum(l.qty for l in sloped.lines if l.part.category == "連結ピン")
        self.assertEqual(pins, sum(len(f.posts) - 1 for f in t.feet))
        self.assertTrue([n for n in sloped.notes if "継ぎ足し分として建枠" in n], sloped.notes)


class TestSingleRowLedgers(unittest.TestCase):
    """一側足場（建地1列）の根がらみ・床レベル布材は1本ずつ（2列前提で数えていた）."""

    def test_ledgers_per_span_follow_the_row_count(self):
        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(scaffold_form="一側足場"),
        )
        q = take_off(m)
        nl = m.elevation.n_levels
        spans = m.plan.total_spans
        # 根がらみ1＋各層（手すり・中桟2）。床の高さの布材・腕木は無し。継ぎ足し無し。
        # 出隅の外側コーナー升目（布材 2辺×〈根がらみ1＋各層3〉）は一側でも付く
        expect = spans * (1 + nl * 2) + m.outer_corner_posts() * 2 * (1 + nl * 3)
        self.assertEqual(q.qty_of("布材"), expect)
        note = next(n for n in q.notes if n.startswith("布材は1スパンあたり"))
        self.assertIn("根がらみ1本", note)
        self.assertNotIn("床レベル", note)



class TestCornerDeckPlanks(unittest.TestCase):
    """出隅コーナーの床（Phase 11-2）: マスタの長さ＝建地列間隔の踏板で拾い、無い幅だけ手配に出す."""

    def _q(self, **extra):
        from ashiba.cli import solve_all

        spec = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 15400, "building_height_mm": 16000}
        spec.update(extra)
        return solve_all(spec)

    def test_real_parts_by_series(self):
        # 日建の既定は幅610に収まる 500 の1枚敷き（500＋240 だと内側の板が建地の内へはみ出す）
        for sid, no in (("shinwa_A", "SD-2506"), ("nikken_nd1800", "NDN2")):
            r = self._q(series_id=sid)
            nl = r.model.elevation.n_levels
            line = next(l for l in r.quantity.lines if l.part.model_no == no)
            self.assertTrue(any(str(n).startswith("出隅コーナーの床は長さ") for n in r.quantity.notes), sid)
            self.assertGreaterEqual(line.qty, 4 * nl, sid)

    def test_missing_width_goes_to_order_notes(self):
        r = self._q(series_id="shinwa_A", next_gen=True)        # 幅500 の長さ600 はマスタに無い
        if 500 not in r.model.deck_widths_in_use:
            self.skipTest("次世代の床幅が500でない")
        acts = [str(n) for n in r.quantity.notes if "長さ600の踏板" in str(n)]
        self.assertTrue(any("幅500" in a and "マスタにありません" in a for a in acts), acts)


class TestLedgerCutNotesNameTheirReason(unittest.TestCase):
    """差し引いた布材は理由ごとに注記する（開口部の無い計画に「開口部の布材」と出ていた）."""

    def _q(self, **extra):
        from ashiba.cli import solve_all

        spec = {"module": "inch", "corner_steps": False, "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 15400, "building_height_mm": 16000}
        spec.update(extra)
        return solve_all(spec).quantity

    def test_inner_bracket_cut_is_not_called_an_opening(self):
        notes = [str(n) for n in self._q().notes]
        self.assertFalse(any(n.startswith("開口部（梁枠より下）は通路") for n in notes), notes)
        inner = next(n for n in notes if n.startswith("内ブラケットで床を拡幅した区間"))
        # 522スパン×層 × 躯体側の手すり・中桟2本（根がらみがカタログどおり下端から170のコマになり、
        # 作業層が1層増えた。以前は464スパン×層・928本）
        self.assertIn("布材1044本", inner)

    def test_opening_note_counts_only_the_opening(self):
        notes = [str(n) for n in self._q(auto_inner_bracket=False, openings=[
            {"face": "南面", "start_mm": 3658, "beam_span_mm": 3658, "level": 2}]).notes]
        op = next(n for n in notes if n.startswith("開口部（梁枠より下）は通路"))
        self.assertNotIn("928", op)
