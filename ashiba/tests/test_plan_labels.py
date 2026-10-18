"""平面図の部材名ラベル（引出線つき）: 部材を指し、文字は足場の外（寸法の外）に並ぶ."""

import tempfile
import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_all
from ashiba.plan_labels import (
    load_label_record,
    plan_label_items,
    plan_labels,
    remove_plan_labels,
    save_label_record,
)

RECT = {"outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
        "eaves_height_mm": 15400, "building_height_mm": 16000}


class TestPlanLabels(unittest.TestCase):
    def setUp(self):
        self.r = solve_all(dict(RECT))

    def test_items(self):
        texts = [t for _x, _y, t in plan_label_items(self.r.model, self.r.stair_plan)]
        self.assertTrue(any(t.startswith("壁つなぎ") for t in texts), texts)
        self.assertIn("建地（支柱）", texts)
        self.assertTrue(any(t.startswith("作業床（踏板") for t in texts), texts)
        self.assertEqual(sum(1 for t in texts if "階段" in t), self.r.stair_plan.count)

    def test_text_rows_are_outside_the_scaffold_and_dimensions(self):
        from ashiba.plan_labels import outward_extra_m

        labels = plan_labels(self.r.model, self.r.stair_plan)
        self.assertTrue(labels)
        out = 0.3 + 0.6 + outward_extra_m(self.r.model) + 1.9      # 離れ＋建地＋張り出し＋寸法
        for lb in labels:
            y = lb["end"][1]
            self.assertTrue(y < -out or y > 20.0 + out, lb)
            self.assertTrue(-1.0 - outward_extra_m(self.r.model) <= lb["beg"][1] <= 21.0, lb)    # 矢先は足場の上

    def test_labels_in_one_row_do_not_overlap(self):
        from ashiba.elevation_sections import label_text_width_m

        labels = plan_labels(self.r.model, self.r.stair_plan)
        rows = {}
        for lb in labels:
            rows.setdefault(round(lb["mid"][1], 3), []).append(lb)
        for row in rows.values():
            row.sort(key=lambda lb: lb["mid"][0])
            for a, b in zip(row, row[1:]):
                self.assertLess(a["mid"][0] + label_text_width_m(a["text"], 0.25), b["mid"][0])


class TestLabelRecord(unittest.TestCase):
    """平面のラベルは建物ごとに GUID を控え、次の配置・撤去で消す."""

    def test_save_load_remove(self):
        class Client:
            deleted = []

            def delete_elements(self, els):
                Client.deleted.extend(e["elementId"]["guid"] for e in els)

        with tempfile.TemporaryDirectory() as d:
            save_label_record(d, "A", ["g1", "g2"])
            save_label_record(d, "B", ["g3"])
            self.assertEqual(load_label_record(d), {"A": ["g1", "g2"], "B": ["g3"]})
            self.assertEqual(remove_plan_labels(Client(), d, "A"), 2)
            self.assertEqual(Client.deleted, ["g1", "g2"])
            self.assertEqual(load_label_record(d), {"B": ["g3"]})
            self.assertEqual(remove_plan_labels(Client(), d), 1)
            self.assertEqual(load_label_record(d), {})
