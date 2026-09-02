import unittest

from _path import SRC  # noqa: F401

from ashiba.master import SeriesLockError, load_master


class TestMaster(unittest.TestCase):
    def setUp(self):
        self.a = load_master("shinwa_A")

    def test_series_constants(self):
        self.assertEqual(self.a.koma_pitch, 450)
        self.assertEqual(self.a.floor_height, 1800)
        b = load_master("shinwa_B")
        self.assertEqual(b.koma_pitch, 475)

    def test_nominal_vs_actual(self):
        # 支柱1800の実長はほぞ+125
        p = self.a.find("支柱", 1800)
        self.assertEqual(p.actual_dim, 1925)
        # ブレスW1800×H1800の実長は2608
        brace = self.a.by_category("筋交")[0]
        self.assertEqual(brace.nominal_dim, 1800)
        self.assertEqual(brace.actual_dim, 2608)

    def test_span_lengths(self):
        self.assertEqual(self.a.span_lengths(), [1800, 1500, 1200, 900, 600])

    def test_post_lengths_exclude_negarami(self):
        self.assertEqual(self.a.post_lengths(), [3600, 2700, 1800, 900, 450])
        self.assertIn(720, self.a.negarami_post_lengths())

    def test_series_lock(self):
        with self.assertRaises(SeriesLockError):
            load_master("unknown_series")
        b = load_master("shinwa_B")
        b_part = b.find("支柱", 1900)
        with self.assertRaises(SeriesLockError):
            self.a.assert_series(b_part)


class TestMasterCompleteness(unittest.TestCase):
    """部材が欠けた系列は読み込み時点で落とす."""

    def test_incomplete_series_is_rejected_with_the_missing_names(self):
        """inch系列は布材しか無い。解いている途中で空のmin()を取る前に落とす."""
        with self.assertRaises(SeriesLockError) as cm:
            load_master("inch")
        msg = str(cm.exception)
        self.assertIn("不完全", msg)
        for cat in ("支柱", "踏板", "ジャッキ", "壁つなぎ"):
            self.assertIn(cat, msg)

    def test_complete_series_load_fine(self):
        for sid in ("shinwa_A", "shinwa_B", "waku"):
            with self.subTest(sid):
                self.assertTrue(load_master(sid).parts)

    def test_deck_category_differs_by_system(self):
        """枠組は「布板」。決め打ちすると部材があるのに拾えない."""
        self.assertEqual(load_master("shinwa_A").deck_category, "踏板")
        self.assertEqual(load_master("waku").deck_category, "布板")
        self.assertIsNotNone(load_master("waku").deck_parts(500, 1829))


class TestSeriesDerivedDimensions(unittest.TestCase):
    """系列から引く寸法。決め打ちすると系列を切り替えたとき静かに壊れる."""

    def test_default_deck_widths_differ_by_series(self):
        a = load_master("shinwa_A")
        b = load_master("shinwa_B")
        self.assertEqual(a.default_deck_widths(False), (400, 250))
        self.assertEqual(b.default_deck_widths(False), (405, 240))
        self.assertNotEqual(
            a.default_deck_widths(False), a.default_deck_widths(True)
        )

    def test_next_gen_widths_are_wider(self):
        for sid in ("shinwa_A", "shinwa_B"):
            with self.subTest(sid):
                m = load_master(sid)
                self.assertGreater(
                    sum(m.default_deck_widths(True)),
                    sum(m.default_deck_widths(False)),
                )

    def test_frame_width_picks_the_smallest_that_fits(self):
        """「近い幅」で選ぶと布板より狭い建枠になり、実際には組めない."""
        m = load_master("waku")
        widths = sorted(m.frame_widths())
        need = widths[0] + 1
        w, fits = m.frame_width_for(need)
        self.assertTrue(fits)
        self.assertGreaterEqual(w, need)
        self.assertEqual(w, min(x for x in widths if x >= need))

    def test_frame_width_reports_when_nothing_fits(self):
        m = load_master("waku")
        w, fits = m.frame_width_for(99999)
        self.assertFalse(fits)
        self.assertEqual(w, max(m.frame_widths()))


if __name__ == "__main__":
    unittest.main()
