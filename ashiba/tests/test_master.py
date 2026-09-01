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


if __name__ == "__main__":
    unittest.main()
