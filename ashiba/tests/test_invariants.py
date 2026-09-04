"""全サンプルに対する横断的な不変条件（図面・数量・判定が互いに矛盾しない）.

個別のテストは機能ごとに書いてある。ここでは「同梱サンプルを全部解いたとき、
どのサンプルでも必ず成り立つべき関係」を1箇所にまとめ、機能を足したときの
回帰を止める。
"""

import glob
import re
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import load_spec, solve_all

ROOT = Path(__file__).resolve().parents[1]


def _runs():
    for ex in sorted(glob.glob(str(ROOT / "examples" / "*.json"))):
        yield Path(ex).stem, solve_all(load_spec(Path(ex)))


class TestCrossCuttingInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = list(_runs())

    def test_wall_tie_quantity_equals_the_drawing_list(self):
        for name, r in self.runs:
            with self.subTest(name):
                self.assertEqual(r.quantity.qty_of("壁つなぎ"), len(r.model.wall_ties))

    def test_warnings_are_not_duplicated(self):
        for name, r in self.runs:
            with self.subTest(name):
                texts = [w[2] for w in r.warnings]
                self.assertEqual(len(texts), len(set(texts)), texts)

    def test_every_ng_issue_is_a_blocker(self):
        for name, r in self.runs:
            with self.subTest(name):
                ng = [i for i in r.openings.issues + r.platforms.issues + r.bracket_issues
                      + list(r.conflicts) if i.severity == "NG"]
                ng_checks = [c for c in r.checks if c.status == "NG"]
                if ng or ng_checks or not r.structural.all_ok:
                    self.assertFalse(r.verdict["ok"], (name, r.verdict))
                    self.assertTrue(r.verdict["blockers"])
                else:
                    self.assertTrue(r.verdict["ok"], (name, r.verdict))

    def test_deck_note_matches_the_lines(self):
        for name, r in self.runs:
            with self.subTest(name):
                cat = r.model.master.deck_category
                note = next(n for n in r.quantity.notes if n.startswith(f"{cat}はスパン"))
                final = int(re.search(r"(\d+)セルで計上", note).group(1))
                per_width = {}
                for l in r.quantity.lines:
                    if l.part.category == cat:
                        w = next((t for t in l.part.note.split() if t.startswith("幅")), "?")
                        per_width[w] = per_width.get(w, 0) + l.qty
                # 標準幅（ステージ等の追加が無い幅）はセル数と一致する
                self.assertIn(final, per_width.values(), (name, per_width, final))

    def test_jacks_equal_the_feet_on_the_ground(self):
        for name, r in self.runs:
            with self.subTest(name):
                m = r.model
                rows = 1 if m.config.scaffold_form == "一側足場" else 2
                feet = m.plan.total_posts * rows - r.openings.removed_posts
                jacks = sum(l.qty for l in r.quantity.lines
                            if l.part.category == "ジャッキ" and "アンダーベース" not in l.part.note)
                self.assertEqual(jacks, feet, name)

    def test_plan_json_gdl_params_fit_the_gdl(self):
        from ashiba.gdl_params import GDL_STR_MAX, line_params

        for name, r in self.runs:
            with self.subTest(name):
                for ep in r.model.plan.edges:
                    p = line_params(r.model, ep, stair_plan=r.stair_plan, openings=r.openings,
                                    platforms=r.platforms, bracket_sections=r.brackets,
                                    terrain=r.terrain)
                    for k, v in p.items():
                        if isinstance(v, str):
                            self.assertLessEqual(len(v), GDL_STR_MAX, (name, k))


if __name__ == "__main__":
    unittest.main()
