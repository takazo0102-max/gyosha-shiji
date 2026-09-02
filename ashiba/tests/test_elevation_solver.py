import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master


class TestElevation(unittest.TestCase):
    def test_reproduce_documented_example(self):
        """受け入れ基準: G(ジャッキ270)+3800×4+900=16370 の実例再現."""
        r = solve_elevation(
            16370,
            post_lengths=[3800, 2850, 1900, 950, 900, 475],
            floor_height=1900,
            koma_pitch=475,
        )
        self.assertEqual(r.jack_extension, 270)
        self.assertEqual(r.posts, [3800, 3800, 3800, 3800, 900])
        self.assertEqual(r.total_height, 16370)

    def test_shinwa_a_composition(self):
        master = load_master("shinwa_A")
        r = solve_elevation(16300, master=master)
        self.assertEqual(r.total_height, 16300)  # 偏差0の解がある
        self.assertLessEqual(r.jack_extension, 270)
        # 全支柱がA系列規格
        for p in r.posts:
            self.assertIn(p, master.post_lengths())
        # 端数（短支柱）は最上部
        self.assertEqual(r.posts, sorted(r.posts, reverse=True))

    def test_staggered_joints(self):
        master = load_master("shinwa_A")
        r = solve_elevation(16300, master=master)
        self.assertTrue(r.is_staggered(), f"千鳥不成立: {r.posts} / {r.posts_alt}")
        # 代替構成も同じ合計高さ
        self.assertEqual(sum(r.posts), sum(r.posts_alt))

    def test_first_ledger_low(self):
        master = load_master("shinwa_A")
        r = solve_elevation(10000, master=master)
        self.assertLessEqual(r.first_ledger_height, 2000)

    def test_top_floor_is_fixed_point(self):
        """最上層作業床＝支柱天端から手すり2コマ下."""
        master = load_master("shinwa_A")
        r = solve_elevation(16300, master=master)
        self.assertTrue(r.level_heights)
        self.assertEqual(max(r.level_heights), r.total_height - 2 * 450)

    def test_unsolvable_raises(self):
        with self.assertRaises(ValueError):
            solve_elevation(100, post_lengths=[3600], koma_pitch=450, floor_height=1800)


class TestDegenerateHeights(unittest.TestCase):
    """作業床が1層も取れない解を黙って返さない."""

    def test_zero_levels_is_warned(self):
        m = load_master("shinwa_A")
        e = solve_elevation(2000, master=m)
        self.assertEqual(e.n_levels, 0)
        self.assertTrue(
            any("作業床が1層も取れません" in w for w in e.warnings), e.warnings
        )

    def test_normal_heights_have_no_such_warning(self):
        m = load_master("shinwa_A")
        e = solve_elevation(16300, master=m)
        self.assertGreater(e.n_levels, 0)
        self.assertFalse(any("作業床が1層も取れません" in w for w in e.warnings))

    def test_every_series_solves_across_the_usable_range(self):
        """高さを振っても例外・過大偏差・2m超の層間が出ないこと."""
        for sid in ("shinwa_A", "shinwa_B", "waku"):
            m = load_master(sid)
            for h in range(4000, 45001, 1000):
                with self.subTest(sid=sid, h=h):
                    e = solve_elevation(h, master=m)
                    self.assertGreater(e.n_levels, 0)
                    self.assertGreaterEqual(e.total_height - h, -150)
                    gaps = [
                        b - a for a, b in zip(e.level_heights, e.level_heights[1:])
                    ]
                    self.assertTrue(all(g <= 2000 for g in gaps), gaps)


if __name__ == "__main__":
    unittest.main()
