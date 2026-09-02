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


if __name__ == "__main__":
    unittest.main()
