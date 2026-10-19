import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import load_master


class TestElevation(unittest.TestCase):
    def test_reproduce_documented_example(self):
        """1900 の系列: 1段目は 2850（階高×1.5）、そのあと 3800、端数は最上部（利用者の決め 2026-10-20）.

        以前の受け入れ基準の実例 G(ジャッキ270)+3800×4+900=16370 は、1段目を 2850 にする決めで置き換えた。
        """
        r = solve_elevation(
            16370,
            post_lengths=[3800, 2850, 1900, 950, 900, 475],
            floor_height=1900,
            koma_pitch=475,
        )
        self.assertEqual(r.posts[0], 2850)
        self.assertTrue(all(p == 3800 for p in r.posts[1:-1]), r.posts)
        self.assertLessEqual(abs(r.total_height - 16370), 475)

    def test_shinwa_a_composition(self):
        """1段目 2700、そのあと 3600、端数は最上部（利用者の決め 2026-10-20）."""
        master = load_master("shinwa_A")
        r = solve_elevation(16300, master=master)
        self.assertEqual(r.total_height, 16300)  # 偏差0の解がある
        self.assertLessEqual(r.jack_extension, 270)
        for p in r.posts:
            self.assertIn(p, master.post_lengths())
        self.assertEqual(r.posts[0], 2700)
        self.assertEqual(r.posts[1:], sorted(r.posts[1:], reverse=True))
        self.assertEqual(r.posts[1], 3600)

    def test_first_is_2700_for_low_scaffolds_too(self):
        master = load_master("shinwa_A")
        for h in (6000, 9930, 12000, 20000):
            with self.subTest(h=h):
                self.assertEqual(solve_elevation(h, master=master).posts[0], 2700)

    def test_heights_off_the_5mm_grid(self):
        """スラブの天端から決めた高さ（5928mm など5mmの倍数でない）でも組める（実機で止まった）."""
        master = load_master("shinwa_A")
        for h in (5928, 5927, 9931, 16302, 15999):
            with self.subTest(h=h):
                r = solve_elevation(h, master=master)
                self.assertEqual(r.total_height, h)
                self.assertEqual(r.posts[0], 2700)

    def test_staggered_joints(self):
        """千鳥はしない（利用者の決め）。代替構成は合計高さだけ同じ."""
        master = load_master("shinwa_A")
        r = solve_elevation(16300, master=master)
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


class TestJointStaggering(unittest.TestCase):
    """千鳥（隣接支柱で縦継ぎ位置をずらす）は指示書§4.4の要求."""

    def test_joint_heights_are_cumulative_from_the_jack(self):
        m = load_master("shinwa_A")
        e = solve_elevation(16300, master=m)
        got = e.joint_heights()
        acc, want = e.jack_extension, []
        for p in e.posts[:-1]:
            acc += p
            want.append(acc)
        self.assertEqual(got, want)
        self.assertEqual(len(got), len(e.posts) - 1)

    def test_single_length_cannot_stagger_and_says_so(self):
        e = solve_elevation(7200, post_lengths=[1800], koma_pitch=450)
        self.assertEqual(len(set(e.posts)), 1)
        self.assertFalse(e.is_staggered())
        self.assertTrue(any("千鳥" in w for w in e.warnings), e.warnings)


class TestJackNearTheLimitGetsAnAlternative(unittest.TestCase):
    """繰出しが実務上限に張り付いたら、調整代のある構成を警告で添える（採択は計画者）."""

    def test_alternative_is_offered(self):
        master = load_master("shinwa_A")
        r = solve_elevation(12900, master=master)     # L字棟の条件: 270mm が選ばれる
        self.assertEqual(r.jack_extension, 270)
        hit = [w for w in r.warnings if "調整代" in w]
        self.assertTrue(hit, r.warnings)
        self.assertIn("ジャッキ", hit[0])
        self.assertIn("scaffold_height_mm", hit[0])

    def test_no_note_when_jack_is_comfortable(self):
        master = load_master("shinwa_A")
        r = solve_elevation(16300, master=master)     # ジャッキ100
        self.assertFalse([w for w in r.warnings if "調整代" in w], r.warnings)


if __name__ == "__main__":
    unittest.main()
