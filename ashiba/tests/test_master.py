import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.master import MasterDataError, SeriesLockError, load_master


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
        """布材しか無い系列は、解いている途中で空のmin()を取る前に落とす."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "m.csv"
            csv_path.write_text(
                "series_id,category,model_no,nominal_dim,actual_dim,diameter,weight_kg,note\n"
                "nikken_nd1800,布材,NDT18,1829,1829,42.7,5.03,\n", encoding="utf-8")
            with self.assertRaises(SeriesLockError) as cm:
                load_master("nikken_nd1800", csv_path)
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


class TestSeriesDerivedDimensions(unittest.TestCase):
    """系列から引く寸法。決め打ちすると系列を切り替えたとき静かに壊れる."""

    def test_default_deck_widths_differ_by_series(self):
        a = load_master("shinwa_A")
        b = load_master("shinwa_B")
        self.assertEqual(a.default_deck_widths(False), (400, 250))
        self.assertEqual(b.default_deck_widths(False), (405, 240))
        self.assertNotEqual(
            a.default_deck_widths(False), a.default_deck_widths(True)
        )

    def test_next_gen_widths_are_wider(self):
        for sid in ("shinwa_A", "shinwa_B"):
            with self.subTest(sid):
                m = load_master(sid)
                self.assertGreater(
                    sum(m.default_deck_widths(True)),
                    sum(m.default_deck_widths(False)),
                )

    def test_frame_width_picks_the_smallest_that_fits(self):
        """「近い幅」で選ぶと布板より狭い建枠になり、実際には組めない."""
        m = load_master("waku")
        widths = sorted(m.frame_widths())
        need = widths[0] + 1
        w, fits = m.frame_width_for(need)
        self.assertTrue(fits)
        self.assertGreaterEqual(w, need)
        self.assertEqual(w, min(x for x in widths if x >= need))

    def test_frame_width_reports_when_nothing_fits(self):
        m = load_master("waku")
        w, fits = m.frame_width_for(99999)
        self.assertFalse(fits)
        self.assertEqual(w, max(m.frame_widths()))


class TestMasterCsvErrors(unittest.TestCase):
    """マスタは利用者が差し替える外部データ。読めない理由を日本語で返す."""

    HEAD = ("series_id,category,model_no,nominal_dim,actual_dim,"
            "diameter,weight_kg,note\n")
    ROW = "shinwa_A,支柱,A-3609,3600,3725,48.6,13.1,ほぞ+125\n"

    def _load(self, body, encoding="utf-8"):
        import tempfile

        td = tempfile.mkdtemp()
        path = Path(td) / "m.csv"
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding=encoding)
        return load_master("shinwa_A", path)

    def _err(self, *a, **kw):
        with self.assertRaises(MasterDataError) as cm:
            self._load(*a, **kw)
        return str(cm.exception)

    def test_missing_file(self):
        with self.assertRaises(MasterDataError) as cm:
            load_master("shinwa_A", Path("/nonexistent/master.csv"))
        self.assertIn("見つかりません", str(cm.exception))

    def test_empty_file(self):
        self.assertIn("空です", self._err(""))

    def test_missing_columns_are_named(self):
        msg = self._err("series_id,category,model_no\nshinwa_A,支柱,A-1\n")
        self.assertIn("必要な列がありません", msg)
        self.assertIn("nominal_dim", msg)

    def test_non_numeric_names_the_row(self):
        msg = self._err(self.HEAD + "shinwa_A,支柱,A-3609,さんぜん,3725,48.6,13.1,x\n")
        self.assertIn("2行目", msg)
        self.assertIn("nominal_dim", msg)
        self.assertIn("A-3609", msg)

    def test_empty_cell_names_the_row(self):
        msg = self._err(self.HEAD + "shinwa_A,支柱,A-3609,,3725,48.6,13.1,x\n")
        self.assertIn("空です", msg)
        self.assertIn("nominal_dim", msg)

    def test_excel_encodings_are_accepted(self):
        """ExcelのCSVはBOM付きUTF-8かShift_JIS。どちらも読めること."""
        full = Path(__file__).resolve().parents[1] / "data" / "part_master.csv"
        text = full.read_text(encoding="utf-8")
        for body in (text.encode("utf-8-sig"), text.encode("cp932")):
            with self.subTest(len(body)):
                m = self._load(body)
                self.assertGreater(len(m.parts), 10)
                self.assertEqual(m.series_id, "shinwa_A")


if __name__ == "__main__":
    unittest.main()
