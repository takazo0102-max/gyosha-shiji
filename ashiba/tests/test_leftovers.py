"""足場の断面・レイアウトの残骸の点検."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.leftovers import group, lines, prefix_of_layout, prefix_of_section


class TestNames(unittest.TestCase):
    def test_prefixes(self):
        self.assertEqual(prefix_of_section("実機 内ブラケット 南面 足場立面"), "実機 内ブラケット")
        self.assertEqual(prefix_of_section("スモーク lshape 東面(辺0) 足場立面"), "スモーク lshape")
        self.assertIsNone(prefix_of_section("断面 A"))
        self.assertEqual(prefix_of_layout("A棟 足場立面図"), "A棟")
        self.assertEqual(prefix_of_layout("A棟 足場立面図 南面"), "A棟")
        self.assertEqual(prefix_of_layout("B棟 足場詳細図"), "B棟")
        self.assertIsNone(prefix_of_layout("各階平面図"))

    def test_group_marks_in_use(self):
        uses = group(["A棟 南面 足場立面", "旧名 北面 足場立面"],
                     ["A棟 足場立面図", "A棟 足場平面図", "旧名 足場詳細図", "面積表"], ["A棟"])
        self.assertEqual([(u.prefix, u.in_use, len(u.sections), len(u.layouts)) for u in uses],
                         [("A棟", True, 1, 2), ("旧名", False, 1, 1)])
        text = "\n".join(lines(uses))
        self.assertIn("残骸の候補: 「旧名」", text)
        self.assertIn("--remove", text)
        self.assertEqual(lines([]), ["足場の断面・レイアウトはありません"])


if __name__ == "__main__":
    unittest.main()
