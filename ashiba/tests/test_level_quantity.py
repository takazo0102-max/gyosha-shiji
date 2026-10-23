"""層ごとの数量（利用者の指定 2026-10-20: 1フロアごとに数量を拾う、支柱は分解して）."""

import csv
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all, write_outputs
from ashiba.level_quantity import take_off_by_level

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]], "eaves_height_mm": 15400}


def _lt(r):
    return take_off_by_level(r.model, r.quantity, bracket_sections=r.brackets, stair_plan=r.stair_plan,
                             platforms=r.platforms, openings=r.openings, terrain=r.terrain)


class TestLevelQuantity(unittest.TestCase):
    def test_levels_add_up_to_the_quantity_table(self):
        for sp in (RECT, {**RECT, "series_id": "nikken_nd1800"},
                   {**RECT, "face_eaves_mm": {"0": 9000, "1": 15400, "2": 15400, "3": 15400}}):
            with self.subTest(sp=sp):
                r = solve_all(dict(sp))
                lt = _lt(r)
                self.assertEqual(len(lt.bands), r.model.elevation.n_levels)
                want = {}
                for line in r.quantity.lines:
                    key = (line.part.model_no, line.part.category)
                    want[key] = want.get(key, 0) + line.qty
                got = {(row.part.model_no, row.part.category): row.total for row in lt.rows}
                self.assertEqual(got, want)

    def test_posts_are_split_piece_by_piece(self):
        """1段目の 2700 は1層目、その上の 3600 はそれぞれ下端の層に."""
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        lt = _lt(r)
        posts = {row.part.nominal_dim: row.per_level for row in lt.rows if row.part.category == "支柱"}
        from ashiba.quantity import outside_stair_counts

        # 外付けの階段室（幅 610 の足場の階段は 600 枠 2 列）の 3 列目の支柱も
        positions = (r.model.plan.total_posts * 2 + r.model.outer_corner_posts()
                     + outside_stair_counts(r.model, r.stair_plan)[0])
        self.assertEqual(posts[2700][0], positions)
        self.assertEqual(sum(posts[3600]), positions * r.model.elevation.posts.count(3600))
        self.assertEqual(posts[3600][0], 0)

    def test_foot_parts_and_ledgers(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800"})
        lt = _lt(r)
        jack = next(row for row in lt.rows if row.part.category == "ジャッキ" and "繰出し" in row.part.note)
        self.assertEqual(jack.per_level[1:], [0] * (len(lt.bands) - 1))
        deck = [row for row in lt.rows if row.part.category == "踏板"]
        self.assertTrue(all(row.per_level[1] > 0 for row in deck))

    def test_csv_written(self):
        r = solve_all(dict(RECT))
        with tempfile.TemporaryDirectory() as d:
            write_outputs(r, Path(d))
            with open(Path(d) / f"{r.name}_層別数量.csv", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows[0][:3], ["型番", "分類", "呼び寸法"])
        self.assertTrue(rows[0][3].startswith("1層"))


if __name__ == "__main__":
    unittest.main()


class TestFloors(unittest.TestCase):
    def test_levels_map_to_building_floors(self):
        stories = [{"name": "1FL", "level_mm": 0}, {"name": "2FL", "level_mm": 3000},
                   {"name": "3FL", "level_mm": 6000}, {"name": "RFL", "level_mm": 9000}]
        r = solve_all({**RECT, "eaves_height_mm": 9000, "stories": stories})
        lt = take_off_by_level(r.model, r.quantity, stories=stories, bracket_sections=r.brackets,
                               stair_plan=r.stair_plan, platforms=r.platforms, openings=r.openings,
                               terrain=r.terrain)
        self.assertEqual(len(lt.floors), len(lt.bands))
        for b, f in zip(lt.bands, lt.floors):
            want = [s["name"] for s in stories if s["level_mm"] <= b.z_hi + 1][-1]
            self.assertEqual(f, want)
        names, rows = lt.by_floor()
        self.assertEqual(names, list(dict.fromkeys(lt.floors)))
        for (part, vals), row in zip(rows, lt.rows):
            self.assertEqual(sum(vals), row.total)

    def test_csv_has_floor_section(self):
        stories = [{"name": "1FL", "level_mm": 0}, {"name": "2FL", "level_mm": 3000}]
        r = solve_all({**RECT, "stories": stories})
        with tempfile.TemporaryDirectory() as d:
            write_outputs(r, Path(d))
            with open(Path(d) / f"{r.name}_層別数量.csv", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        self.assertTrue(any(row and row[0] == "■フロア別" for row in rows))


class TestOutsideStairPosts(unittest.TestCase):
    def test_tower_posts_are_split_too(self):
        r = solve_all({**RECT, "series_id": "nikken_nd1800", "stairs": {"layout": "outside"}})
        lt = _lt(r)
        self.assertFalse(any("位置ごとに違う分" in n for n in lt.notes), lt.notes)


class TestCsvSafe(unittest.TestCase):
    def test_formula_like_names_are_quoted(self):
        from ashiba.report import _csv_safe

        self.assertEqual(_csv_safe("=1+1"), "'=1+1")
        self.assertEqual(_csv_safe("-1.基礎下端"), "'-1.基礎下端")
        self.assertEqual(_csv_safe("2FL"), "2FL")


class TestFaceQuantity(unittest.TestCase):
    """面ごとの数量（参考: smartCON Planner の領域ごとの部品表）。面の合計は全体の数量表と一致する."""

    def test_faces_add_up(self):
        for sp in ({"series_id": "nikken_nd1800"}, {"series_id": "waku"},
                   {"series_id": "nikken_nd1800", "stairs": {"layout": "outside"}},
                   {"face_eaves_mm": {"0": 9000, "1": 15400, "2": 15400, "3": 15400}}):
            with self.subTest(sp=sp):
                r = solve_all({**RECT, **sp})
                from ashiba.level_quantity import take_off_by_face

                ft = take_off_by_face(r.model, r.quantity, bracket_sections=r.brackets, stair_plan=r.stair_plan,
                                      platforms=r.platforms, openings=r.openings, terrain=r.terrain)
                self.assertEqual(len(ft.faces), len(r.model.plan.edges))
                for p, vals in ft.rows:
                    self.assertEqual(sum(vals), ft.totals.get((p.model_no, p.category), 0), (p.model_no, vals))
