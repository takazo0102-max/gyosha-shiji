"""面の高さの組ごとに拾った手配の行（敷板・シート・クランプ）を品目ごとに足して1行にする（2026-10-27 のループ: 張り出しの
検証で敷板が3行・特殊シートが3行並び合計がどこにも無く、要確認一覧の敷板は割り付け直す前の枚数のままだった）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.cli import solve_groups
from ashiba.quantity import SILL_NOTE_HEAD, merge_counted_warnings

SILL = "ジャッキベースの下の敷板（杉の足場板 幅240・厚35）{}枚を手配してください（建地の列に沿って通す）"


class TestMergeCounted(unittest.TestCase):
    def test_sums_each_item(self):
        ws = [SILL.format("4m×4・3m×2"), SILL.format("4m×11・3m×1・2m×2"), SILL.format("4m×5・3m×1"),
              "シート: 幅914×3枚・幅1524×3枚（無い幅）", "シート: 幅914×3枚（無い幅）",
              "養生クランプ コーナー用 4個（出隅）", "養生クランプ コーナー用 8個（出隅）",
              "メッシュシート（1.8×5.2m）は外側の構面", "昇降機 本体 KSE-990 型がマスタにありません（1）"]
        out, mapping = merge_counted_warnings(ws)
        self.assertEqual(out, [SILL.format("4m×20・3m×4・2m×2"), "シート: 幅914×6枚・幅1524×3枚（無い幅）",
                               "養生クランプ コーナー用 12個（出隅）", "メッシュシート（1.8×5.2m）は外側の構面",
                               "昇降機 本体 KSE-990 型がマスタにありません（1）"])
        self.assertEqual(mapping[ws[1]], out[0])

    def test_different_lines_stay_apart(self):
        ws = ["支柱 A×2本を足す", "布材 B×3本を足す"]
        self.assertEqual(merge_counted_warnings(ws)[0], ws)


class TestReportMatchesQuantity(unittest.TestCase):
    def test_checklist_uses_the_final_order_lines(self):
        low = [[0, 0], [24000, 0], [24000, 10000], [0, 10000]]
        up = [[0, 3000], [24000, 3000], [24000, 10000], [0, 10000]]
        slabs = ([{"polygon_mm": low, "top_mm": t} for t in (3000, 6000, 9000)]
                 + [{"polygon_mm": up, "top_mm": t} for t in (12000, 15000, 18000)])
        for _lb, r in solve_groups({"project_name": "S", "outline_mm": low, "slabs": slabs, "module": "inch",
                                    "eaves_height_mm": 18000}):
            listed = [t for k, _s, t in r.warnings if k.startswith("数量")]
            self.assertEqual(listed, list(r.quantity.warnings))
            self.assertLessEqual(sum(1 for w in r.quantity.warnings if w.startswith(SILL_NOTE_HEAD)), 1)


class TestWideGapWithInnerRails(unittest.TestCase):
    """離れ 300 超の面: 躯体側の手すり・中桟を付ける足場では「付けている」と書き、付けない足場だけ措置を求める."""

    SPEC = {"project_name": "x", "outline_mm": [[0, 0], [10000, 0], [10000, 8000], [0, 8000]], "eaves_height_mm": 6000,
            "series_id": "nikken_nd1800", "module": "inch"}

    def test_rails_are_said_to_be_there(self):
        from ashiba.cli import FALL_REMEDY_ASK, FALL_REMEDY_DONE, solve_all

        r = solve_all(self.SPEC)
        wide = [e for e in r.model.plan.edges if e.standoff > 300]
        self.assertTrue(wide)
        self.assertTrue(all(FALL_REMEDY_DONE in e.remedy for e in wide))
        self.assertFalse([w for _k, _s, w in r.warnings if FALL_REMEDY_ASK in w])
        r2 = solve_all({**self.SPEC, "inner_guard_rail": False})
        self.assertTrue([w for _k, _s, w in r2.warnings if FALL_REMEDY_ASK in w])


if __name__ == "__main__":
    unittest.main()
