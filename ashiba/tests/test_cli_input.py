"""入力JSONの読み取り（cli.py の build_* 関数）のテスト.

どの build_* にも直接のテストが無く、例題が使っていない入力項目は
「受け取っているのに効いていない」状態でも気づけなかった。実際、
ブラケット区間の deck_width と開口部がその状態だった。
"""

import datetime as dt
import unittest

from _path import SRC  # noqa: F401

from ashiba.brackets import INNER, OUTER
from ashiba.cli import (
    build_asagao,
    build_brackets,
    build_ground,
    build_model,
    build_notification_info,
    build_openings,
    build_platforms,
    build_site,
)
from ashiba.model import GUARD_RAIL_ADVANCE, GUARD_RAIL_LEDGER

RECT = [[0, 0], [30000, 0], [30000, 20000], [0, 20000]]
BASE = {"series_id": "shinwa_A", "outline_mm": RECT, "eaves_height_mm": 15400}


class TestBuildModel(unittest.TestCase):
    def test_defaults(self):
        m = build_model(dict(BASE), None)
        self.assertEqual(m.master.series_id, "shinwa_A")
        self.assertEqual(m.config.scaffold_form, "本足場")
        self.assertEqual(m.config.guard_rail_type, GUARD_RAIL_LEDGER)
        self.assertFalse(m.config.next_gen)
        self.assertEqual(m.clearance_space_mm, 2000)

    def test_explicit_values_win(self):
        m = build_model(dict(
            BASE, scaffold_form="一側足場", guard_rail_type=GUARD_RAIL_ADVANCE,
            next_gen=True, clearance_space_mm=500, building_height_mm=16000,
            period_days=90, deck_widths=[500, 240],
        ), None)
        self.assertEqual(m.config.scaffold_form, "一側足場")
        self.assertEqual(m.config.guard_rail_type, GUARD_RAIL_ADVANCE)
        self.assertTrue(m.config.next_gen)
        self.assertEqual(m.clearance_space_mm, 500)
        self.assertEqual(m.building_height_mm, 16000)
        self.assertEqual(m.config.period_days, 90)
        self.assertEqual(list(m.config.deck_widths), [500, 240])

    def test_guard_extra_is_added_to_the_eaves_height(self):
        low = build_model(dict(BASE, guard_extra_mm=0), None)
        high = build_model(dict(BASE, guard_extra_mm=900), None)
        self.assertGreater(high.scaffold_height_mm, low.scaffold_height_mm)

    def test_standoff_spec_is_read(self):
        m = build_model(dict(BASE, standoff={
            "target": 250, "min": 200, "max": 300, "hard_min": 180}), None)
        for e in m.plan.edges:
            self.assertLessEqual(e.standoff, 300)


class TestBuildAsagao(unittest.TestCase):
    def test_auto_from_height(self):
        self.assertEqual(build_asagao({}, 16300).stages, 1)
        self.assertEqual(build_asagao({}, 25000).stages, 2)
        self.assertIsNone(build_asagao({}, 8000))

    def test_false_means_do_not_install(self):
        """高さ的には要るが、明示的に設置しない指定."""
        self.assertIsNone(build_asagao({"asagao": False}, 16300))

    def test_explicit_spec(self):
        a = build_asagao({"asagao": {
            "stages": 2, "projection_mm": 2500, "angle_deg": 30,
            "tie_every_spans": 3}}, 16300)
        self.assertEqual((a.stages, a.projection_mm, a.angle_deg), (2, 2500, 30))
        self.assertEqual(a.tie_every_spans, 3)

    def test_partial_spec_falls_back_to_the_required_count(self):
        a = build_asagao({"asagao": {"projection_mm": 2500}}, 25000)
        self.assertEqual(a.stages, 2)


class TestBuildBrackets(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_brackets({}), [])

    def test_all_fields_are_read(self):
        s = build_brackets({"bracket_sections": [{
            "edge_index": 1, "start_mm": 100, "end_mm": 5500, "direction": "張出",
            "width": 400, "deck_width": 500, "levels": [1, 2],
            "has_hozue": True, "is_widening": True, "on_kessokubu": True,
            "reason": "下屋",
        }]})[0]
        self.assertEqual(s.edge_index, 1)
        self.assertEqual((s.start_mm, s.end_mm), (100.0, 5500.0))
        self.assertEqual(s.direction, OUTER)
        self.assertEqual((s.width, s.deck_width), (400, 500))
        self.assertEqual(s.levels, [1, 2])
        self.assertTrue(s.has_hozue and s.is_widening and s.on_kessokubu)
        self.assertEqual(s.reason, "下屋")

    def test_direction_defaults_to_inner(self):
        s = build_brackets({"bracket_sections": [
            {"edge_index": 0, "start_mm": 0, "end_mm": 1800}]})[0]
        self.assertEqual(s.direction, INNER)


class TestBuildPlatformsAndOpenings(unittest.TestCase):
    def test_stages_and_hoists(self):
        stages, hoists = build_platforms({
            "loading_stages": [{
                "edge_index": 2, "start_mm": 3600, "span_count": 3,
                "projection_mm": 1800, "load_kn": 14.7, "levels": [2]}],
            "hoists": [{"edge_index": 1, "position_mm": 9000,
                        "reach_height_mm": 20000, "tie_every_mm": 3000}],
        })
        self.assertEqual(stages[0].span_count, 3)
        self.assertEqual(stages[0].projection_mm, 1800)
        self.assertEqual(stages[0].load_kn, 14.7)
        self.assertEqual(stages[0].levels, [2])
        self.assertEqual(hoists[0].reach_height_mm, 20000)
        self.assertEqual(hoists[0].tie_every_mm, 3000)

    def test_empty(self):
        self.assertEqual(build_platforms({}), ([], []))
        self.assertEqual(build_openings({}), [])

    def test_openings(self):
        o = build_openings({"openings": [{
            "edge_index": 3, "start_mm": 5400, "beam_span_mm": 5400,
            "level": 2, "reason": "搬入路"}]})[0]
        self.assertEqual((o.edge_index, o.start_mm), (3, 5400.0))
        self.assertEqual((o.beam_span_mm, o.level), (5400, 2))
        self.assertEqual(o.reason, "搬入路")

    def test_opening_level_defaults_to_one(self):
        o = build_openings({"openings": [
            {"edge_index": 0, "start_mm": 0, "beam_span_mm": 3600}]})[0]
        self.assertEqual(o.level, 1)


class TestBuildGroundAndSite(unittest.TestCase):
    def test_ground_points(self):
        g = build_ground({"ground_points_mm": [[0, 0, 0], [1000, 0, 500]]})
        self.assertFalse(g.is_flat)
        self.assertEqual(g.range_mm(), (0, 500))

    def test_flat_when_absent(self):
        self.assertTrue(build_ground({}).is_flat)

    def test_site_defaults(self):
        s = build_site({})
        self.assertEqual(s.region, "関東(内陸)")
        self.assertEqual(s.roughness, "III")
        self.assertEqual(s.sheet_type, "メッシュシート")
        self.assertEqual(s.simultaneous_loaded_levels, 2)
        self.assertEqual(s.period_days, 60)

    def test_site_explicit(self):
        s = build_site({"period_days": 90, "site": {
            "region": "沖縄", "v0_ms": 46.0, "roughness": "II",
            "sheet_type": "防音シート", "adjacent_factor": 1.2,
            "region_factor": 1.1, "gamma": 0.3, "correction_f": 1.05,
            "simultaneous_loaded_levels": 1}})
        self.assertEqual(s.region, "沖縄")
        self.assertEqual(s.v0_ms, 46.0)
        self.assertEqual(s.adjacent_factor, 1.2)
        self.assertEqual(s.gamma, 0.3)
        self.assertEqual(s.correction_f, 1.05)
        self.assertEqual(s.simultaneous_loaded_levels, 1)
        self.assertEqual(s.period_days, 90)


class TestBuildNotificationInfo(unittest.TestCase):
    def test_start_date_is_parsed_and_deadline_derived(self):
        info = build_notification_info({"notification": {
            "start_date": "2026-11-01", "site_name": "現場"}})
        self.assertEqual(info.start_date, dt.date(2026, 11, 1))
        self.assertEqual(info.submission_deadline(), dt.date(2026, 10, 2))
        self.assertEqual(info.site_name, "現場")

    def test_absent_date_leaves_none(self):
        info = build_notification_info({})
        self.assertIsNone(info.start_date)
        self.assertIsNone(info.submission_deadline())

    def test_worker_count_is_stringified(self):
        info = build_notification_info({"notification": {"worker_count": 30}})
        self.assertEqual(info.worker_count, "30")


class TestDocumentedSchemaIsRead(unittest.TestCase):
    """docstringに書いた入力項目が、実際にコードから読まれていること.

    書いてあるのに読んでいない項目は、指定しても効かない（実際に
    ブラケットの deck_width と開口部がその状態だった）。
    """

    def test_every_documented_key_appears_in_the_code(self):
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1]
               / "src" / "ashiba" / "cli.py").read_text(encoding="utf-8")
        schema = src.split("入力JSONスキーマ")[1].split('"""')[0]
        keys = set(re.findall(r'"([a-z_]+)":', schema))
        body = src.split('"""', 2)[2]
        missing = sorted(k for k in keys if f'"{k}"' not in body)
        self.assertEqual(missing, [], f"docstringにあるがコードが読んでいない: {missing}")


if __name__ == "__main__":
    unittest.main()
