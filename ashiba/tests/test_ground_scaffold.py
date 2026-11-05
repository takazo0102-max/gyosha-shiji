"""地足場（利用者の指定 2026-10-24: 地足場機能も追加して）."""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, solve_all, solve_groups

ROOT = Path(__file__).resolve().parents[1]
SPEC = {"project_name": "g", "outline_mm": [[0, 0], [24000, 0], [24000, 10000], [0, 10000]],
        "eaves_height_mm": 9000, "module": "inch"}


class TestGroundScaffold(unittest.TestCase):
    def test_one_level_with_stairs(self):
        # 昇降ははしごでなく階段室（利用者の指定 2026-10-29: ハシゴじゃなくて階段を使う）
        r = solve_all({**SPEC, "ground_scaffold": True})
        self.assertEqual(r.model.elevation.level_heights, [1800])
        self.assertGreaterEqual(len(r.stair_plan.towers), 1)
        self.assertIsNone(r.model.config.asagao)
        self.assertEqual(r.model.roof_bridges, [])
        self.assertTrue(any("地足場（1層" in w for w in r.model.plan.warnings))
        # 実機 2026-10-24: 「階段室が入る区間が無い規模」「昇降設備がありません」と出た（はしごで昇降する）
        self.assertFalse(any("入る区間が無い規模" in w or "昇降設備がありません" in w for w in r.stair_plan.warnings))

    def test_three_levels_keep_stairs(self):
        r = solve_all({**SPEC, "ground_scaffold": {"levels": 3}})
        self.assertEqual(len(r.model.elevation.level_heights), 3)
        self.assertTrue(r.stair_plan.towers)

    def test_groups_and_bad_levels(self):
        g = solve_groups({**SPEC, "ground_scaffold": {"levels": 2}})
        self.assertEqual(len(g[0][1].model.elevation.level_heights), 2)
        with self.assertRaises(InputError):
            solve_all({**SPEC, "ground_scaffold": {"levels": 5}})

    def test_standoff_clears_the_formwork(self):
        # 躯体の面から 500 以上離す（型枠・端太・セパを収める。報告 地足場と内部足場 2026-10-28）
        r = solve_all({**SPEC, "ground_scaffold": True})
        # 離れはスパンの割付で数 mm 動く（インチの割付で 498）
        self.assertTrue(all(v >= 490 for v in r.model.plan.standoffs), r.model.plan.standoffs)
        note = next(w for w in r.model.plan.warnings if "地足場（1層" in w)
        self.assertIn("控え", note)
        self.assertIn("500mm 離して", note)
        wide = solve_all({**SPEC, "ground_scaffold": {"levels": 1, "standoff_mm": 700}})
        self.assertTrue(all(v >= 690 for v in wide.model.plan.standoffs), wide.model.plan.standoffs)
        normal = solve_all(SPEC)
        self.assertTrue(any(v < 450 for v in normal.model.plan.standoffs))

    def test_deck_height_against_the_ground_beam(self):
        # 作業床は地中梁の天端（ふかし筋）＋500〜800 が目安（報告 地足場と内部足場 2026-10-28）
        ok = solve_all({**SPEC, "ground_scaffold": {"levels": 1, "beam_top_mm": 1150}})
        note = next(w for w in ok.model.plan.warnings if "地足場（1層" in w)
        self.assertIn("天端 1150 から +650", note)
        low = solve_all({**SPEC, "ground_scaffold": {"levels": 1, "beam_top_mm": 1600}})
        note = next(w for w in low.model.plan.warnings if "地足場（1層" in w)
        self.assertIn("目安 +500〜800 を外れる", note)
        # 2層は下の段（1800）が目安に入れば OK（最上段 3600 だけ見て外れると出ていた。実機 2026-10-29）
        two = solve_all({**SPEC, "ground_scaffold": {"levels": 2, "beam_top_mm": 1150}})
        note = next(w for w in two.model.plan.warnings if "地足場（2層" in w)
        self.assertIn("1800 の作業床が地中梁の天端 1150 から +650", note)

    def test_standoff_kept_for_tube_and_frame(self):
        # 単管は離れを 300 に引き戻していた。枠組は躯体側の手すりが割付・数量に入らないので注記で
        from ashiba.master import series_module

        for sid in ("tankan", "waku"):
            r = solve_all({**SPEC, "series_id": sid, "module": series_module(sid), "ground_scaffold": {"levels": 2}})
            self.assertTrue(all(v >= 470 for v in r.model.plan.standoffs), (sid, r.model.plan.standoffs))
            note = next(w for w in r.model.plan.warnings if "地足場（2層" in w)
            self.assertEqual("手すり枠" in note, sid == "waku")
        # 離れの注意は型枠の言い方（外壁の言い方のままだった。実機 2026-10-29）
        r2 = solve_all({**SPEC, "ground_scaffold": {"levels": 2}})
        txt = "\n".join(r2.model.plan.warnings) + "\n".join(e.remedy or "" for e in r2.model.plan.edges)
        self.assertNotIn("外壁施工後の建物", txt)
        self.assertIn("型枠を収めるため", txt)
        # 割付で数 mm 下回っても「顧客最小値を下回る」とは言わない
        r = solve_all({**SPEC, "ground_scaffold": {"levels": 2}})
        self.assertFalse(any("顧客最小値" in w for w in r.model.plan.warnings))

    def test_ties_become_braces_until_the_structure_rises(self):
        # 根切り底では壁つなぎを取る躯体がまだ無いので、控え（単管＋自在クランプ）を手配に出す（2026-10-29）
        r = solve_all({**SPEC, "ground_scaffold": {"levels": 2}})
        n = len(r.model.wall_ties)
        self.assertGreater(n, 0)
        w = next(x for x in r.quantity.warnings if "控えで代える" in x)
        self.assertIn(f"{n}本＋自在クランプ {2 * n}個", w)
        self.assertFalse(any("控えで代える" in x for x in solve_all(SPEC).quantity.warnings))

    def test_palette(self):
        from ashiba.palette import ACTIONS, PANEL_GROUPS

        self.assertIn("地足場", dict(PANEL_GROUPS)["足場を建てる"])
        self.assertIn("地足場", [a.title for a in ACTIONS])
        self.assertTrue((ROOT / "scripts" / "ground_scaffold_run.py").exists())


if __name__ == "__main__":
    unittest.main()
