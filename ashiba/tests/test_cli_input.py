"""入力JSONの読み取り（cli.py の build_* 関数）のテスト.

どの build_* にも直接のテストが無く、例題が使っていない入力項目は
「受け取っているのに効いていない」状態でも気づけなかった。実際、
ブラケット区間の deck_width と開口部がその状態だった。
"""

import datetime as dt
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.brackets import INNER, OUTER
from ashiba.cli import (
    InputError,
    build_asagao,
    build_brackets,
    build_ground,
    build_model,
    build_notification_info,
    build_openings,
    build_platforms,
    build_site,
    STAIR_POSITION_KEYS,
    validate_spec,
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
            period_days=90, deck_widths=[500, 250],
        ), None)
        self.assertEqual(m.config.scaffold_form, "一側足場")
        self.assertEqual(m.config.guard_rail_type, GUARD_RAIL_ADVANCE)
        self.assertTrue(m.config.next_gen)
        self.assertEqual(m.clearance_space_mm, 500)
        self.assertEqual(m.building_height_mm, 16000)
        self.assertEqual(m.config.period_days, 90)
        self.assertEqual(list(m.config.deck_widths), [500, 250])

    def test_guard_extra_default_follows_the_series(self):
        """既定は手すり分。枠組はコマピッチ0なので、2×コマだと0になってしまう."""
        for series, extra in (("shinwa_A", 900), ("shinwa_B", 950), ("waku", 900)):
            with self.subTest(series):
                m = build_model(dict(BASE, series_id=series), None)
                self.assertGreaterEqual(
                    m.scaffold_height_mm, BASE["eaves_height_mm"] + extra)

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


class TestValidateSpec(unittest.TestCase):
    """綴り違い・型違い・矛盾は、黙って既定値に落とさず入口で弾く."""

    def ng(self, spec):
        with self.assertRaises(InputError) as cm:
            validate_spec(spec)
        return str(cm.exception)

    def test_valid_spec_passes(self):
        validate_spec(dict(BASE))

    def test_unknown_top_level_key_is_rejected(self):
        msg = self.ng(dict(BASE, loading_stage=[]))
        self.assertIn("loading_stage", msg)
        self.assertIn("loading_stages", msg)   # 綴り違いの候補を出す

    def test_unknown_nested_key_is_rejected(self):
        self.assertIn("stage", self.ng(dict(BASE, asagao={"stage": 2})))
        self.assertIn("regionn", self.ng(dict(BASE, site={"regionn": "沖縄"})))

    def test_unknown_list_item_key_is_rejected(self):
        msg = self.ng(dict(BASE, loading_stages=[
            {"edge_index": 0, "start_mm": 0, "span": 2}]))
        self.assertIn("loading_stages[0]", msg)
        self.assertIn("span", msg)

    def test_required_keys_are_named(self):
        msg = self.ng({"outline_mm": RECT})
        self.assertIn("eaves_height_mm", msg)
        msg = self.ng(dict(BASE, openings=[{"edge_index": 0}]))
        self.assertIn("start_mm", msg)
        self.assertIn("beam_span_mm", msg)

    def test_outline_shape_is_checked(self):
        self.assertIn("3点以上", self.ng(dict(BASE, outline_mm=[[0, 0], [1, 1]])))
        self.assertIn("2要素", self.ng(dict(BASE, outline_mm=[[0, 0, 0]] * 3)))

    def test_standoff_order_is_checked(self):
        msg = self.ng(dict(BASE, standoff={"target": 400, "min": 250, "max": 350}))
        self.assertIn("hard_min≦min≦target≦max", msg)

    def test_negative_numbers_are_rejected(self):
        self.assertIn("eaves_height_mm", self.ng(dict(BASE, eaves_height_mm=-1)))

    def test_scaffold_form_is_checked(self):
        self.assertIn("scaffold_form", self.ng(dict(BASE, scaffold_form="本足")))

    def test_ground_points_need_three_values(self):
        self.assertIn("3要素", self.ng(dict(BASE, ground_points_mm=[[0, 0]])))

    def test_all_problems_are_reported_at_once(self):
        msg = self.ng(dict(BASE, foo=1, bar=2, scaffold_form="x"))
        for token in ("foo", "bar", "scaffold_form"):
            self.assertIn(token, msg)

    def test_numeric_field_type_is_checked(self):
        """数値であるべきフィールドに文字列を渡したら実行前に弾く.

        以前は割付の途中で TypeError（'<' not supported）や
        invalid literal になり、利用者には直しようがなかった。
        """
        msg = self.ng(dict(BASE, loading_stages=[
            {"edge_index": 0, "start_mm": 0, "span_count": "two"}]))
        self.assertIn("span_count", msg)
        self.assertIn("数値", msg)
        msg = self.ng(dict(BASE, openings=[
            {"edge_index": 0, "start_mm": 0, "beam_span_mm": 3600, "level": "x"}]))
        self.assertIn("level", msg)
        self.assertIn("数値", msg)
        self.assertIn("stages", self.ng(dict(BASE, asagao={"stages": "one"})))

    def test_int_list_field_type_is_checked(self):
        msg = self.ng(dict(BASE, hoists=[
            {"edge_index": 0, "position_mm": 0, "landing_levels": ["a"]}]))
        self.assertIn("landing_levels", msg)
        self.assertIn("整数の配列", msg)

    def test_string_field_type_is_checked(self):
        msg = self.ng(dict(BASE, site={"region": 123}))
        self.assertIn("region", msg)
        self.assertIn("文字列", msg)

    def test_asagao_false_is_allowed(self):
        validate_spec(dict(BASE, asagao=False))

    def test_examples_all_validate(self):
        import json
        
        ex = Path(__file__).resolve().parents[1] / "examples"
        for f in sorted(ex.glob("*.json")):
            with self.subTest(f.name):
                validate_spec(json.loads(f.read_text(encoding="utf-8")))


class TestDegenerateValuesAreRejected(unittest.TestCase):
    """型は合っているが解くと意味の無い値（0・逆転）を入口で弾く."""

    def ng(self, **over):
        with self.assertRaises(InputError) as cm:
            validate_spec(dict(BASE, **over))
        return str(cm.exception)

    def test_zero_eaves_height(self):
        self.assertIn("eaves_height_mm", self.ng(eaves_height_mm=0))

    def test_outline_in_metres_is_caught(self):
        """m で入力した外形は 30mm の建物として解けてしまう。単位の取り違えを止める."""
        msg = self.ng(outline_mm=[[0, 0], [30, 0], [30, 20], [0, 20]])
        self.assertIn("単位は mm", msg)
        self.assertIn("30000", msg)

    def test_eaves_height_in_metres_is_caught(self):
        msg = self.ng(eaves_height_mm=16)
        self.assertIn("単位は mm", msg)

    def test_stairs_on_a_missing_edge_is_an_input_error(self):
        """存在しない辺の階段は警告だけで落ちて階段の無い計画が出ていた."""
        import json
        import tempfile

        from ashiba.cli import load_spec, solve_all

        spec = dict(BASE, stairs={"positions": [{"edge_index": 9, "start_mm": 0}]})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(InputError) as cm:
                solve_all(load_spec(p))
        self.assertIn("stairs.positions[0].edge_index: 辺9は存在しません", str(cm.exception))
        self.assertIn("0・1・2・3", str(cm.exception))

    def test_eaves_above_building(self):
        msg = self.ng(eaves_height_mm=20000, building_height_mm=15000)
        self.assertIn("軒高", msg)
        self.assertIn("建物高さ", msg)

    def test_zero_period(self):
        self.assertIn("period_days", self.ng(period_days=0))

    def test_deck_widths_shape(self):
        for bad in ([], [400, 250, 200], [-400, 250], [0, 250], "400"):
            with self.subTest(bad):
                self.assertIn("deck_widths", self.ng(deck_widths=bad))

    def test_deck_width_missing_from_master(self):
        from ashiba.cli import build_model

        with self.assertRaises(InputError) as cm:
            build_model(dict(BASE, deck_widths=[999, 250]))
        self.assertIn("999", str(cm.exception))
        self.assertIn("使える幅", str(cm.exception))

    def test_negative_stairs_count(self):
        self.assertIn("stairs.count", self.ng(stairs={"count": -1}))
        self.assertIn("max_travel_mm", self.ng(stairs={"max_travel_mm": 0}))

    def test_unknown_site_region_lists_candidates(self):
        msg = self.ng(site={"region": "火星"})
        self.assertIn("site.region", msg)
        self.assertIn("沖縄", msg)

    def test_unknown_roughness_and_sheet(self):
        self.assertIn("粗度", self.ng(site={"roughness": "X"}))
        msg = self.ng(site={"sheet_type": "紙"})
        self.assertIn("養生材", msg)
        self.assertIn("メッシュシート", msg)

    def test_zero_wind_speed_is_rejected(self):
        self.assertIn("v0_ms", self.ng(site={"v0_ms": 0}))

    def test_adjacent_factor_range(self):
        self.assertIn("1.0〜1.3", self.ng(site={"adjacent_factor": 5.0}))
        self.assertIn("adjacent_factor", self.ng(site={"adjacent_factor": 0.5}))
        validate_spec(dict(BASE, site={"adjacent_factor": 1.3}))

    def test_other_site_factors(self):
        self.assertIn("gamma", self.ng(site={"gamma": 2}))
        self.assertIn("correction_f", self.ng(site={"correction_f": 0}))
        self.assertIn("simultaneous_loaded_levels", self.ng(site={"simultaneous_loaded_levels": 0}))

    def test_degenerate_outline_is_a_clean_error(self):
        """外形の検証エラーは生のトレースバックではなく入力エラーとして出る.

        斜めの辺は直交外形に置き換えて通すようになったので、3点の外形で確認する。
        """
        import io
        import json
        import tempfile
        from contextlib import redirect_stderr

        from ashiba.cli import main

        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(dict(
                BASE, outline_mm=[[0, 0], [30000, 0], [30000, 20000]])),
                encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                code = main([str(src), "--out", d])
        self.assertEqual(code, 2)
        self.assertIn("4点以上", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class TestInputsActuallyTakeEffect(unittest.TestCase):
    """受け取っているのに何も変えない入力は、指定しても効かないのと同じ."""

    def test_retired_key_points_at_the_new_one(self):
        """n_stairs は受け取るだけで効いていなかった。黙って無視しない."""
        from ashiba.cli import InputError, validate_spec

        with self.assertRaises(InputError) as cm:
            validate_spec(dict(BASE, n_stairs=3))
        self.assertIn("stairs.count", str(cm.exception))

    def test_clearance_space_blocks_a_scaffold_that_does_not_fit(self):
        """離れ＋建地間隔が確保できる幅を超えたらNG（素通りしていた）."""
        from ashiba.law_check import run_all_checks

        wide = build_model(dict(BASE, clearance_space_mm=2000), None)
        narrow = build_model(dict(BASE, clearance_space_mm=800), None)
        self.assertEqual(
            [c.status for c in run_all_checks(wide) if c.check_id == 1], ["OK"])
        ng = [c for c in run_all_checks(narrow) if c.check_id == 1][0]
        self.assertEqual(ng.status, "NG")
        self.assertIn("収まりません", ng.message)


class TestBrokenInputFiles(unittest.TestCase):
    """入口の失敗でトレースバックを出さない（何を直すか書く）."""

    OK = ('{"outline_mm": [[0,0],[30000,0],[30000,20000],[0,20000]],'
          ' "eaves_height_mm": 15400}')

    def _load(self, body, name="s.json", encoding="utf-8"):
        import tempfile

        from ashiba.cli import load_spec

        td = tempfile.mkdtemp()
        path = Path(td) / name
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding=encoding)
        return load_spec(path)

    def _err(self, *a, **kw):
        with self.assertRaises(InputError) as cm:
            self._load(*a, **kw)
        return str(cm.exception)

    def test_missing_file(self):
        from ashiba.cli import load_spec

        with self.assertRaises(InputError) as cm:
            load_spec(Path("/nonexistent/なにか.json"))
        self.assertIn("見つかりません", str(cm.exception))

    def test_empty_file(self):
        self.assertIn("空です", self._err(""))

    def test_broken_json_points_at_the_line(self):
        msg = self._err('{"outline_mm": [[0,0],')
        self.assertIn("JSONとして読めません", msg)
        self.assertIn("1行", msg)
        self.assertIn("該当行", msg)

    def test_trailing_comma_hint(self):
        msg = self._err(self.OK[:-1] + ",}")
        self.assertIn("末尾の余分なカンマ", msg)

    def test_bom_is_accepted(self):
        """Windowsのメモ帳で保存するとBOMが付く。実用上そのまま受ける."""
        spec = self._load("\ufeff" + self.OK)
        self.assertEqual(spec["eaves_height_mm"], 15400)

    def test_shift_jis_is_named(self):
        # 日本語が入って初めてUTF-8として壊れる（ASCIIだけなら同じバイト列）
        body = '{"project_name": "現場", ' + self.OK[1:]
        msg = self._err(body.encode("cp932"))
        self.assertIn("cp932", msg)
        self.assertIn("UTF-8で保存", msg)

    def test_cli_exits_with_code_2(self):
        import tempfile

        from ashiba.cli import main

        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "s.json"
            f.write_text("", encoding="utf-8")
            self.assertEqual(main([str(f), "--out", str(Path(td) / "o")]), 2)


class TestProjectNameBecomesAFileName(unittest.TestCase):
    """工事名はそのままファイル名になる。使えない文字で落ちない."""

    def _run(self, name):
        import json
        import tempfile

        from ashiba.cli import run

        spec = dict(BASE, project_name=name)
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "s.json"
            f.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = run(f, Path(td) / "o")
            files = sorted(p.name for p in (Path(td) / "o").rglob("*") if p.is_file())
        return r, files

    def test_slash_does_not_crash(self):
        """"A/B工区" は FileNotFoundError で落ちていた."""
        r, files = self._run("A/B工区")
        self.assertEqual(len(files), 6)   # 数量表・層別数量・割付レポート・plan・ジャッキ量一覧・設置届一式
        self.assertEqual(r["file_stem"], "A_B工区")
        self.assertTrue(all(f.startswith("A_B工区_") for f in files), files)

    def test_reserved_characters_are_replaced(self):
        from ashiba.cli import safe_file_stem

        for bad in ':*?"<>|\\':
            with self.subTest(bad):
                self.assertNotIn(bad, safe_file_stem(f"現場{bad}1期"))

    def test_empty_or_dots_fall_back(self):
        from ashiba.cli import safe_file_stem

        for name in ("", "   ", "..", ". ."):
            with self.subTest(name):
                self.assertEqual(safe_file_stem(name), "ashiba")

    def test_long_name_is_truncated(self):
        from ashiba.cli import MAX_NAME_LEN, safe_file_stem

        self.assertLessEqual(len(safe_file_stem("あ" * 200)), MAX_NAME_LEN)

    def test_change_is_not_silent(self):
        r, _files = self._run("A/B工区")
        self.assertTrue(
            any("ファイル名" in n for n in r["notes"]), r["notes"]
        )

    def test_normal_name_is_untouched(self):
        from ashiba.cli import safe_file_stem

        self.assertEqual(safe_file_stem("サンプル矩形30x20"), "サンプル矩形30x20")


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

    def test_accepted_keys_and_the_documented_schema_agree(self):
        """受け付けるキーと説明が食い違うと、正しい入力が弾かれる（逆も）."""
        import re
        from pathlib import Path

        from ashiba.cli import LIST_ITEM_KEYS, NESTED_KEYS, TOP_KEYS

        src = (Path(__file__).resolve().parents[1]
               / "src" / "ashiba" / "cli.py").read_text(encoding="utf-8")
        schema = src.split("入力JSONスキーマ")[1].split('"""')[0]
        documented = set(re.findall(r'"([a-z_0-9]+)":', schema))
        accepted = set(TOP_KEYS)
        for v in NESTED_KEYS.values():
            accepted |= v
        for allowed, _ in LIST_ITEM_KEYS.values():
            accepted |= allowed
        accepted |= STAIR_POSITION_KEYS
        self.assertEqual(
            sorted(documented - accepted), [],
            "説明にあるのに受け付けないキー（正しい入力が弾かれる）",
        )


class TestFaceNamesInsteadOfEdgeIndex(unittest.TestCase):
    """付帯設備の面は face: "北面" でも指定できる。辺番号は外形の整理でずれる."""

    def _solve(self, **extra):
        import json
        import tempfile

        from ashiba.cli import load_spec, solve_all

        spec = dict(BASE, **extra)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return solve_all(load_spec(p))

    def test_face_name_resolves_to_the_edge(self):
        r = self._solve(hoists=[{"face": "北面", "position_mm": 9000}])
        h = r.platforms.hoists[0]
        self.assertEqual(r.model.face_name(h.edge_index), "北面")

    def test_face_survives_outline_normalisation(self):
        """実機の五角形棟: 入力順の辺3は北面だが、斜辺の置き換えで整理後は西面になった."""
        pent = [[0, 0], [30000, 0], [30000, 12000], [20000, 20000], [0, 20000]]
        r = self._solve(outline_mm=pent, hoists=[{"face": "北面", "position_mm": 9000}])
        self.assertEqual(r.model.face_name(r.platforms.hoists[0].edge_index), "北面")
        r2 = self._solve(outline_mm=pent, hoists=[{"edge_index": 3, "position_mm": 9000}])
        self.assertEqual(r2.model.face_name(r2.platforms.hoists[0].edge_index), "西面")
        # 面名で指定した項目には「辺番号がずれている可能性」の警告を出さない
        self.assertFalse(any("辺番号が入力の頂点順とずれている" in w[2] for w in r.warnings), r.warnings)
        self.assertTrue(any("辺番号が入力の頂点順とずれている" in w[2] for w in r2.warnings))

    def test_short_form_and_stairs(self):
        r = self._solve(stairs={"positions": [{"face": "南", "start_mm": 9000}, {"face": "北面", "start_mm": 9000}]})
        faces = sorted(r.model.face_name(t.edge_index) for t in r.stair_plan.towers)
        self.assertEqual(faces, ["北面", "南面"])

    def test_unknown_face_lists_the_faces(self):
        with self.assertRaises(InputError) as cm:
            self._solve(openings=[{"face": "北西面", "start_mm": 3600, "beam_span_mm": 3600}])
        self.assertIn("openings[0].face: 面「北西面」はありません", str(cm.exception))
        self.assertIn("南面・東面・北面・西面", str(cm.exception))

    def test_duplicate_direction_needs_the_edge_number(self):
        l_shape = [[0, 0], [30000, 0], [30000, 10000], [15000, 10000], [15000, 20000], [0, 20000]]
        with self.assertRaises(InputError) as cm:
            self._solve(outline_mm=l_shape, hoists=[{"face": "北面", "position_mm": 3600}])
        self.assertIn("複数あります", str(cm.exception))
        self.assertIn("北面(辺", str(cm.exception))
        r = self._solve(outline_mm=l_shape, hoists=[{"face": "北面(辺2)", "position_mm": 3600}])
        self.assertEqual(r.platforms.hoists[0].edge_index, 2)

    def test_face_and_edge_index_must_agree(self):
        with self.assertRaises(InputError) as cm:
            self._solve(hoists=[{"face": "北面", "edge_index": 0, "position_mm": 3600}])
        self.assertIn("どちらか一方", str(cm.exception))

    def test_neither_is_an_error(self):
        with self.assertRaises(InputError) as cm:
            self._solve(hoists=[{"position_mm": 3600}])
        self.assertIn('"edge_index" が要ります（または face: "北面"）', str(cm.exception))


class TestHeightAndSpanOverrides(unittest.TestCase):
    """足場高さの直接指定と、面ごとのスパン指定."""

    def _solve(self, **extra):
        import json
        import tempfile

        from ashiba.cli import load_spec, solve_all

        spec = dict(BASE, **extra)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return solve_all(load_spec(p))

    def test_scaffold_height_overrides_the_eaves_rule(self):
        base = self._solve()
        r = self._solve(scaffold_height_mm=12000)
        self.assertNotEqual(r.model.scaffold_height_mm, base.model.scaffold_height_mm)
        self.assertLess(abs(r.model.scaffold_height_mm - 12000), 700)
        notes = [w[2] for w in r.warnings if "足場高さは指定値12000mm" in w[2]]
        self.assertEqual(len(notes), 1, r.warnings)
        self.assertIn("軒高より低い", notes[0])

    def test_top_floor_below_the_eaves_is_named(self):
        """足場高さは軒より高いが、最上層作業床が軒に届かないときはその差を書く."""
        r = self._solve(scaffold_height_mm=15900)            # 軒高15400、手すり分900 → 計算値16300
        notes = [w[2] for w in r.warnings if "足場高さは指定値15900mm" in w[2]]
        self.assertEqual(len(notes), 1, r.warnings)
        self.assertIn("軒高15400mmより", notes[0])
        self.assertIn("低くなります", notes[0])
        self.assertNotIn("軒に届きません", notes[0])

    def test_scaffold_height_too_low_is_an_input_error(self):
        with self.assertRaises(InputError) as cm:
            self._solve(scaffold_height_mm=100)
        self.assertIn("scaffold_height_mm", str(cm.exception))

    def test_span_override_by_face(self):
        r = self._solve(span_overrides=[{"face": "南面", "spans_mm": ["1800x5", 900, 900, "1800x11"]}])
        south = [e for e in r.model.plan.edges if r.model.face_name(e.edge_index) == "南面"][0]
        self.assertEqual(list(south.spans), [1800] * 5 + [900, 900] + [1800] * 11)
        self.assertTrue(any("南面のスパンは指定どおり" in w[2] for w in r.warnings), r.warnings)

    def test_span_override_errors(self):
        with self.assertRaises(InputError) as cm:
            self._solve(span_overrides=[{"face": "北西面", "spans_mm": [1800]}])
        self.assertIn("面「北西面」はありません", str(cm.exception))
        with self.assertRaises(InputError) as cm:
            self._solve(span_overrides=[{"face": "南面", "spans_mm": ["1800x5"]}])
        self.assertIn("span_overrides", str(cm.exception))
        self.assertIn("足場長", str(cm.exception))
        with self.assertRaises(InputError) as cm:
            self._solve(span_overrides=[{"face": "南面", "spans_mm": ["abc"]}])
        self.assertIn("spans_mm", str(cm.exception))


class TestAdvanceRailHasNoToeBoard(unittest.TestCase):
    """先行手すり方式は幅木なし（図面・数量・法規チェック）。布材方式は幅木あり."""

    def _solve(self, **extra):
        import json
        import tempfile

        from ashiba.cli import load_spec, solve_all

        spec = dict(BASE, **extra)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return solve_all(load_spec(p))

    def test_advance(self):
        r = self._solve(guard_rail_type=GUARD_RAIL_ADVANCE)
        self.assertFalse(r.model.config.has_toe_board)
        self.assertEqual(r.quantity.qty_of("幅木"), 0)
        self.assertTrue(any("幅木は付けていません" in w[2] for w in r.warnings), r.warnings)
        c3 = [c for c in r.checks if c.check_id == 3][0]
        self.assertEqual(c3.status, "OK")
        self.assertIn("幅木なし（先行手すり方式", c3.message)

    def test_ledger_keeps_toe_boards(self):
        r = self._solve(guard_rail_type=GUARD_RAIL_LEDGER)
        self.assertTrue(r.model.config.has_toe_board)
        self.assertGreater(r.quantity.qty_of("幅木"), 0)
        self.assertFalse(any("幅木は付けていません" in w[2] for w in r.warnings))

    def test_frame_ignores_advance_and_keeps_toe_boards(self):
        r = self._solve(series_id="waku", guard_rail_type=GUARD_RAIL_ADVANCE)
        self.assertTrue(r.model.config.has_toe_board)


class TestUnderscoreKeysAreComments(unittest.TestCase):
    def test_top_level_and_items(self):
        spec = dict(BASE, _memo="コメント", hoists=[{"_memo": "北面の昇降機", "face": "北面", "position_mm": 9000}])
        validate_spec(spec)      # 例外にならない
        with self.assertRaises(InputError):
            validate_spec(dict(BASE, memo="コメント"))


if __name__ == "__main__":
    unittest.main()
