import unittest

from _path import SRC  # noqa: F401

from ashiba.geometry import ValidationError, build_outline
from ashiba.master import load_master
from ashiba.plan_solver import StandoffSpec, solve_plan

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]
# L型: 入隅が(18000,12000)に1つ
LSHAPE = [(0, 0), (30000, 0), (30000, 12000), (18000, 12000), (18000, 20000), (0, 20000)]


class TestGeometry(unittest.TestCase):
    def test_corner_classification(self):
        o = build_outline(LSHAPE)
        kinds = [c.kind for c in o.corners]
        self.assertEqual(kinds.count("出隅"), 5)
        self.assertEqual(kinds.count("入隅"), 1)
        reflex = [c for c in o.corners if c.kind == "入隅"][0]
        self.assertEqual(reflex.point, (18000.0, 12000.0))

    def test_non_orthogonal_rejected(self):
        with self.assertRaises(ValidationError):
            build_outline([(0, 0), (10000, 0), (5000, 8000)])

    def test_cw_input_normalized(self):
        o = build_outline(list(reversed(RECT)))
        self.assertEqual([c.kind for c in o.corners], ["出隅"] * 4)


class TestPlanRect(unittest.TestCase):
    def setUp(self):
        self.master = load_master("shinwa_A")
        self.plan = solve_plan(RECT, self.master)

    def test_standoffs_in_range(self):
        for d in self.plan.standoffs:
            self.assertGreaterEqual(d, 250)
            self.assertLessEqual(d, 350)

    def test_over_300_requires_fall_protection(self):
        """離れ30cm超は法規上、墜落防止措置が要る（許容範囲内でも黙って通さない）.

        外壁施工後の建物と作業床の間隔は30cm以下が原則。
        超える場合は手すり設置または安全帯使用等の措置。
        """
        for ep in self.plan.edges:
            if ep.standoff > 300:
                self.assertIsNotNone(ep.remedy, f"辺{ep.edge_index}が無警告")
                self.assertIn("墜落防止", ep.remedy)
            elif 250 <= ep.standoff <= 300:
                self.assertIsNone(ep.remedy, f"辺{ep.edge_index}に不要な警告")

    def test_max_300_spec_avoids_fall_protection(self):
        """許容上限を300にすれば、墜落防止措置が要る面を出さずに解ける場合がある."""
        plan = solve_plan(RECT, self.master, StandoffSpec(max=300.0, min=200.0))
        for d in plan.standoffs:
            self.assertLessEqual(d, 300)

    def test_span_geometry_consistency(self):
        # 各辺: sum(spans) == 躯体辺長 + 符号付き隣接離れ（真物のみ・切断なし）
        n = len(self.plan.edges)
        for ep, e in zip(self.plan.edges, self.plan.outline.edges):
            d_prev = self.plan.standoffs[(e.index - 1) % n]
            d_next = self.plan.standoffs[(e.index + 1) % n]
            expect = e.length + e.start_sign * d_prev + e.end_sign * d_next
            self.assertAlmostEqual(sum(ep.spans), expect, delta=0.5)
            self.assertAlmostEqual(ep.scaffold_length, sum(ep.spans), delta=0.5)

    def test_long_face_all_main_spans(self):
        # 30m面は1800×17=30600（離れ300/300）で割れる
        e0 = self.plan.edges[0]
        self.assertEqual(e0.spans, [1800] * 17)

    def test_spans_are_stock_lengths(self):
        stock = set(self.master.span_lengths())
        for ep in self.plan.edges:
            for s in ep.spans:
                self.assertIn(s, stock)

    def test_opposite_faces_balanced(self):
        # 全体XYシフトで対面の離れが均等になる
        self.assertAlmostEqual(self.plan.standoffs[0], self.plan.standoffs[2], delta=0.5)
        self.assertAlmostEqual(self.plan.standoffs[1], self.plan.standoffs[3], delta=0.5)

    def test_no_double_counted_posts(self):
        pts = self.plan.post_positions()
        self.assertEqual(len(pts), self.plan.total_posts)
        uniq = {(round(x, 1), round(y, 1)) for x, y in pts}
        self.assertEqual(len(uniq), len(pts))
        self.assertEqual(self.plan.total_posts, self.plan.total_spans)


class TestShortEdges(unittest.TestCase):
    """短い辺（凹み・小さな張り出し）の回帰テスト.

    探索下限を最大スパンで切ると、短い辺で最大スパン1本しか候補が出ず、
    実際には成立する構成を黙って捨ててしまう（過大な離れ、または解なし）。
    実務の玄関ポーチ・小さな張り出し・凹みで普通に起きる。
    """

    def setUp(self):
        self.master = load_master("shinwa_A")

    # 2000幅×800深の凹み
    RECESS = [(0, 0), (12000, 0), (12000, 8000), (7000, 8000),
              (7000, 7200), (5000, 7200), (5000, 8000), (0, 8000)]
    # 2400×1200の張り出し
    BUMP = [(0, 0), (12000, 0), (12000, 8000), (7200, 8000),
            (7200, 9200), (4800, 9200), (4800, 8000), (0, 8000)]
    # 800幅の凹み（狭すぎて足場面を作れない）
    TOO_NARROW = [(0, 0), (12000, 0), (12000, 8000), (6400, 8000),
                  (6400, 7200), (5600, 7200), (5600, 8000), (0, 8000)]

    def test_recess_uses_short_spans_not_max_span(self):
        plan = solve_plan(self.RECESS, self.master)
        short = [ep for ep in plan.edges if ep.scaffold_length < 1800]
        self.assertTrue(short, "短い足場面が1つも出ていない")
        for ep in short:
            # 最大スパン1本に丸められていない
            self.assertNotEqual(ep.spans, [1800])
            for s in ep.spans:
                self.assertIn(s, self.master.span_lengths())

    def test_bump_keeps_standoff_in_range(self):
        plan = solve_plan(self.BUMP, self.master)
        for ep in plan.edges:
            if ep.scaffold_length < 1800:
                self.assertGreaterEqual(ep.standoff, 250)
                self.assertLessEqual(ep.standoff, 350)

    def test_geometry_consistency_with_short_edges(self):
        for name, poly in (("凹み", self.RECESS), ("張出", self.BUMP)):
            with self.subTest(shape=name):
                plan = solve_plan(poly, self.master)
                n = len(plan.edges)
                for ep, e in zip(plan.edges, plan.outline.edges):
                    d_prev = plan.standoffs[(e.index - 1) % n]
                    d_next = plan.standoffs[(e.index + 1) % n]
                    expect = e.length + e.start_sign * d_prev + e.end_sign * d_next
                    self.assertAlmostEqual(sum(ep.spans), expect, delta=0.5)

    def test_too_narrow_recess_rejected_with_reason(self):
        """物理的に足場面を作れない場合は、理由と対処を添えて拒否する."""
        with self.assertRaises(ValidationError) as ctx:
            solve_plan(self.TOO_NARROW, self.master)
        msg = str(ctx.exception)
        self.assertIn("最小スパン", msg)
        self.assertIn("渡す", msg)   # 対処が書いてある

    def test_achievable_sums_respects_requested_window(self):
        """DPテーブルの大きさが返す範囲を広げてしまわない."""
        from ashiba.plan_solver import achievable_sums
        coins = self.master.span_lengths()
        sums = achievable_sums(coins, 600, 1200)
        self.assertTrue(sums)
        for s in sums:
            self.assertGreaterEqual(s, 600)
            self.assertLessEqual(s, 1200)   # max(coins)=1800 に広がらない

    def test_standoff_below_target_min_is_flagged(self):
        """顧客最小値は満たすが目標下限(250)を下回る帯を黙って通さない.

        200〜250mmは「組めるが余裕が小さい」帯で、干渉確認が要る。
        """
        plan = solve_plan(
            [(0, 0), (24000, 0), (24000, 16000), (14000, 16000),
             (14000, 14000), (10000, 14000), (10000, 16000), (0, 16000)],
            self.master,
        )
        below = [ep for ep in plan.edges
                 if 200 <= ep.standoff < 250]
        self.assertTrue(below, "この形状では目標下限を下回る面が出るはず")
        for ep in below:
            self.assertIsNotNone(ep.remedy, f"辺{ep.edge_index}が無警告")
            self.assertIn("干渉", ep.remedy)

    def test_every_out_of_target_standoff_has_remedy(self):
        """目標帯[250,350]を外れた面には必ず対処案が付く."""
        for name, poly in (("凹み", self.RECESS), ("張出", self.BUMP)):
            with self.subTest(shape=name):
                plan = solve_plan(poly, self.master)
                for ep in plan.edges:
                    if 250 <= ep.standoff <= 350:
                        continue
                    where = f"{name} 辺{ep.edge_index} 離れ{ep.standoff:.0f}"
                    # None でないだけでは足りない。空文字でも assertIsNotNone は通る
                    self.assertTrue(ep.remedy, f"{where} が無警告")
                    self.assertGreater(len(ep.remedy.strip()), 10, where)
                    # 実際の離れの値を本文に出す（何mmが問題なのか分かること）
                    self.assertIn(f"{ep.standoff:.0f}mm", ep.remedy, where)

    def test_no_double_counted_posts_with_short_edges(self):
        plan = solve_plan(self.RECESS, self.master)
        pts = plan.post_positions()
        uniq = {(round(x, 1), round(y, 1)) for x, y in pts}
        self.assertEqual(len(uniq), len(pts))
        self.assertEqual(plan.total_posts, plan.total_spans)


class TestPlanLShape(unittest.TestCase):
    def setUp(self):
        self.master = load_master("shinwa_A")
        self.plan = solve_plan(LSHAPE, self.master)

    def test_geometry_consistency(self):
        n = len(self.plan.edges)
        for ep, e in zip(self.plan.edges, self.plan.outline.edges):
            d_prev = self.plan.standoffs[(e.index - 1) % n]
            d_next = self.plan.standoffs[(e.index + 1) % n]
            expect = e.length + e.start_sign * d_prev + e.end_sign * d_next
            self.assertAlmostEqual(sum(ep.spans), expect, delta=0.5)

    def test_no_double_counted_posts(self):
        pts = self.plan.post_positions()
        uniq = {(round(x, 1), round(y, 1)) for x, y in pts}
        self.assertEqual(len(uniq), len(pts))
        self.assertEqual(self.plan.total_posts, self.plan.total_spans)

    def test_standoff_or_remedy(self):
        # 受け入れ基準: 全面250〜350、または350超の面に対処案が提示される
        for ep in self.plan.edges:
            if not (250 <= ep.standoff <= 350):
                self.assertIsNotNone(ep.remedy)
                self.assertTrue(
                    "ブラケット" in ep.remedy or "落下防止" in ep.remedy
                    or "スパン構成" in ep.remedy
                )

    def test_hard_min_respected(self):
        for d in self.plan.standoffs:
            self.assertGreaterEqual(d, 200)


class TestDegenerateOutlines(unittest.TestCase):
    """Archicadのスラブ外形は重複頂点・共線頂点を普通に含む."""

    def setUp(self):
        self.m = load_master("shinwa_A")

    def test_collinear_vertex_does_not_create_a_corner(self):
        """直線の途中の頂点を入隅と見なすと、両側の面が離れの分だけ短くなる."""
        plain = solve_plan(RECT, self.m)
        withmid = solve_plan(
            [(0, 0), (15000, 0), (30000, 0), (30000, 20000), (0, 20000)], self.m
        )
        self.assertEqual(len(withmid.edges), len(plain.edges))
        self.assertEqual(withmid.total_spans, plain.total_spans)
        self.assertAlmostEqual(
            sum(e.scaffold_length for e in withmid.edges),
            sum(e.scaffold_length for e in plain.edges),
        )

    def test_cleanup_is_reported(self):
        plan = solve_plan(
            [(0, 0), (15000, 0), (30000, 0), (30000, 20000), (0, 20000)], self.m
        )
        self.assertTrue(any("共線頂点" in w for w in plan.warnings), plan.warnings)

    def test_duplicate_vertex_is_not_reported_as_non_orthogonal(self):
        """長さ0の辺は「非直交」ではない。誤った原因を出さない."""
        outline = build_outline(
            [(0, 0), (10000, 0), (10000, 0), (10000, 8000), (0, 8000)]
        )
        self.assertEqual(len(outline.edges), 4)
        self.assertTrue(any("重複頂点" in n for n in outline.notes))

    def test_still_rejects_real_non_orthogonal(self):
        with self.assertRaises(ValidationError):
            build_outline([(0, 0), (10000, 500), (10000, 8000), (0, 8000)])

    def test_too_few_vertices_after_cleanup(self):
        with self.assertRaises(ValidationError):
            build_outline([(0, 0), (5000, 0), (10000, 0), (10000, 0)])


class TestWarningsAreGrouped(unittest.TestCase):
    """同じ対処案が面ごとに1行ずつ並ぶと、件数だけ増えて読みにくい."""

    def setUp(self):
        self.master = load_master("shinwa_A")

    def test_same_remedy_is_one_line_naming_every_face(self):
        plan = solve_plan(RECT, self.master)
        hits = [w for w in plan.warnings if "離れ350mm" in w]
        self.assertEqual(len(hits), 1, plan.warnings)
        self.assertIn("辺0", hits[0])
        self.assertIn("辺2", hits[0])

    def test_different_remedies_stay_separate(self):
        """離れの値が違えば別の対処案なので、まとめない."""
        plan = solve_plan(
            [(0, 0), (20000, 0), (20000, 10000), (14000, 10000),
             (14000, 7000), (6000, 7000), (6000, 10000), (0, 10000)],
            self.master,
        )
        texts = {w.split(": ", 1)[1] for w in plan.warnings if ": " in w}
        self.assertGreater(len(texts), 1, plan.warnings)
        self.assertEqual(len(plan.warnings), len(texts))

    def test_per_edge_remedy_is_kept_for_the_table(self):
        """まとめるのは警告一覧だけ。面ごとの表には各辺の対処案が要る."""
        plan = solve_plan(RECT, self.master)
        with_remedy = [e for e in plan.edges if e.remedy]
        self.assertEqual(len(with_remedy), 2)
        for e in with_remedy:
            self.assertIn(f"{e.standoff:.0f}mm", e.remedy)

    def test_warning_count_matches_distinct_remedies(self):
        for poly in (RECT, LSHAPE):
            with self.subTest(poly=poly[1]):
                plan = solve_plan(poly, self.master)
                distinct = {e.remedy for e in plan.edges if e.remedy}
                grouped = [w for w in plan.warnings if "辺" in w]
                self.assertEqual(len(grouped), len(distinct))


class TestFeasibilityHint(unittest.TestCase):
    """対処案に「他にどの離れなら組めたか」を添える.

    350mmしか組めないのか、300mmも組めるが別の理由で選ばなかったのかで、
    計画者の打つ手が変わる（前者は建物側か措置側でしか動かせない）。
    """

    def setUp(self):
        self.master = load_master("shinwa_A")

    def test_hint_is_attached_to_every_remedy(self):
        for poly in (RECT, LSHAPE):
            with self.subTest(poly=poly[1]):
                for e in solve_plan(poly, self.master).edges:
                    if e.remedy:
                        self.assertIn("（", e.remedy, e.remedy)

    def test_listed_alternatives_are_really_buildable(self):
        """挙げた離れが本当に真物で組めること（スパン和＝面長になる）."""
        import re

        plan = solve_plan(RECT, self.master)
        remedy = next(e.remedy for e in plan.edges if e.remedy)
        alts = [int(v) for v in re.findall(r"(\d+)mm＝?目標帯外", remedy)]
        self.assertTrue(alts, remedy)
        for d in alts:
            with self.subTest(d=d):
                spec = StandoffSpec(target=d, min=d, max=d, hard_min=d)
                p2 = solve_plan(RECT, self.master, spec)
                for e in p2.edges:
                    self.assertAlmostEqual(sum(e.spans), e.scaffold_length)

    def test_says_so_when_the_value_is_forced(self):
        """代案が無いときは「この値のみ」と言う."""
        plan = solve_plan(
            [(0, 0), (20000, 0), (20000, 10000), (14000, 10000),
             (14000, 7000), (6000, 7000), (6000, 10000), (0, 10000)],
            self.master,
        )
        forced = [e.remedy for e in plan.edges
                  if e.remedy and "この値のみ" in e.remedy]
        self.assertTrue(forced, [e.remedy for e in plan.edges if e.remedy])

    def test_says_so_when_nothing_in_the_band_works(self):
        plan = solve_plan(LSHAPE, self.master)
        none_fit = [e.remedy for e in plan.edges
                    if e.remedy and "組める離れはありません" in e.remedy]
        self.assertTrue(none_fit, [e.remedy for e in plan.edges if e.remedy])


if __name__ == "__main__":
    unittest.main()
