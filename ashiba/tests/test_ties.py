"""取付部・マスト控えの壁つなぎを格子と同じ一覧に統合する（図面・数量・検定の一致）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.gdl_params import line_params
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.platforms import Hoist, LoadingStage, validate_platforms
from ashiba.quantity import take_off, wall_tie_required_length_mm
from ashiba.structural import tie_tributaries
from ashiba.ties import merge_attachment_ties, tie_counts

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(asagao=1):
    master = load_master("shinwa_A")
    m = ScaffoldModel(
        master=master, plan=solve_plan(RECT, master),
        elevation=solve_elevation(16300, master=master),
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=asagao) if asagao else None),
        building_height_mm=16000,
    )
    return m


class TestMerge(unittest.TestCase):
    def test_kinds_are_added_once(self):
        m = build()
        pf = validate_platforms(
            m, [LoadingStage(edge_index=0, start_mm=12600, levels=[3])],
            [Hoist(edge_index=2, position_mm=14400, landing_levels=[2, 5])])
        before = len(m.wall_ties)
        added = merge_attachment_ties(m, pf)
        self.assertEqual(set(added) <= {"asagao", "stage", "hoist"}, True)
        self.assertEqual(len(m.wall_ties), before + sum(added.values()))
        # 同じ位置は同じ金具で兼ねる → ステージ両端が格子と重なれば足さない
        counts = tie_counts(m)
        self.assertEqual(counts.get("hoist", 0), 4)          # 16300 // 3600
        # 間口の各支柱（スパン数+1）にブラケットの上下で2箇所
        st = pf.stages[0]
        self.assertLessEqual(counts.get("stage", 0), 2 * (st.span_count + 1))
        # 冪等
        again = merge_attachment_ties(m, pf)
        self.assertEqual(again, {})
        self.assertEqual(len(m.wall_ties), before + sum(added.values()))

    def test_quantity_equals_the_drawing(self):
        m = build()
        pf = validate_platforms(
            m, [LoadingStage(edge_index=0, start_mm=12600, levels=[3])],
            [Hoist(edge_index=2, position_mm=14400)])
        merge_attachment_ties(m, pf)
        q = take_off(m, platforms=pf)
        self.assertEqual(q.qty_of("壁つなぎ"), len(m.wall_ties))
        drawn = sum(
            len([v for v in line_params(m, ep, platforms=pf)["tieList"].split(",") if v])
            + len([v for v in line_params(m, ep, platforms=pf)["tieList2"].split(",") if v])
            for ep in m.plan.edges)
        self.assertEqual(drawn, len(m.wall_ties))

    def test_take_off_merges_on_its_own(self):
        """take_off を単独で呼んでも取付部の壁つなぎが欠けない."""
        m = build()
        pf = validate_platforms(m, [], [Hoist(edge_index=2, position_mm=14400)])
        q = take_off(m, platforms=pf)
        self.assertEqual(q.qty_of("壁つなぎ"), len(m.wall_ties))
        self.assertGreaterEqual(tie_counts(m).get("hoist", 0), 4)
        self.assertTrue(any("朝顔取付部" in l.note or "朝顔取付部" in (l.note or "")
                            for l in q.lines if l.part.category == "壁つなぎ"))

    def test_hoist_ties_do_not_carry_wind(self):
        m = build(asagao=0)
        pf = validate_platforms(m, [], [Hoist(edge_index=2, position_mm=14400)])
        base = len(tie_tributaries(m))
        merge_attachment_ties(m, pf)
        self.assertEqual(len(tie_tributaries(m)), base)      # マスト控えは除外
        self.assertGreater(len(m.wall_ties), base)

    def test_no_attachments_no_change(self):
        m = build(asagao=0)
        n = len(m.wall_ties)
        self.assertEqual(merge_attachment_ties(m, None), {})
        self.assertEqual(len(m.wall_ties), n)


class TestStageTiesBracketTheStage(unittest.TestCase):
    """荷取りブラケットの上下付近に壁つなぎ（日建 p019）: 各支柱に、1つ上と1つ下の作業層."""

    def test_heights_and_posts(self):
        from ashiba.ties import _platform_ties

        m = build()
        st = LoadingStage(edge_index=0, start_mm=12600, span_count=2, levels=[3])
        pf = validate_platforms(m, [st])
        ties = [t for t in _platform_ties(m, pf) if t.kind == "stage"]
        lv = m.elevation.level_heights
        self.assertEqual({t.height_mm for t in ties}, {int(lv[1]), int(lv[3])})
        posts = sorted({t.position_mm for t in ties})
        self.assertEqual(len(posts), 3)
        self.assertEqual(posts[0], 12600.0)
        self.assertEqual(len(ties), 6)
        self.assertEqual(pf.extra_wall_ties, 6)

    def test_bottom_level_uses_the_first_ledger(self):
        from ashiba.ties import _platform_ties

        m = build()
        pf = validate_platforms(m, [LoadingStage(edge_index=0, start_mm=12600, span_count=1, levels=[1])])
        ties = [t for t in _platform_ties(m, pf) if t.kind == "stage"]
        self.assertIn(int(m.elevation.first_ledger_height), {t.height_mm for t in ties})


class TestWallTieLengthSelection(unittest.TestCase):
    """伸縮範囲の違う壁つなぎがある系列は、面ごとの離れ（＋支柱半径）に合う品を選ぶ."""

    def test_nd1800_picks_by_standoff(self):
        from ashiba.quantity import wall_tie_required_length_mm

        master = load_master("nikken_nd1800")
        m = ScaffoldModel(master=master, plan=solve_plan(RECT, master),
                          elevation=solve_elevation(16300, master=master),
                          config=ScaffoldConfig(), building_height_mm=16000)
        q = take_off(m)
        by = {}
        for l in q.lines:
            if l.part.category == "壁つなぎ":
                by[l.part.model_no] = by.get(l.part.model_no, 0) + l.qty
        self.assertEqual(sum(by.values()), len(m.wall_ties))
        # 離れ212の面（＋21）→ KS200、離れ242の面（＋21）→ KS400。KS700 は出ない
        needs = {round(wall_tie_required_length_mm(m, e)) for e in range(4)}
        self.assertTrue(needs <= set(range(160, 421)), needs)
        self.assertNotIn("KS700", by)
        self.assertGreater(by.get("KS200", 0) + by.get("KS400", 0), 0)
        self.assertFalse([w for w in q.warnings if "伸縮範囲に合う品が無い" in w], q.warnings)

    def test_shinwa_ties_are_picked_by_standoff_too(self):
        """信和も NK-1925II〜NK-90112II（p39）を持ったので、面ごとの離れで選ぶ.

        以前は NK-3352II 1品しか無く、範囲外の面は「合う品が無い」と警告するしかなかった。
        """
        from ashiba.quantity import wall_tie_required_length_mm

        m = build()
        q = take_off(m)
        by = {}
        for l in q.lines:
            if l.part.category == "壁つなぎ":
                by[l.part] = by.get(l.part, 0) + l.qty
        self.assertEqual(sum(by.values()), len(m.wall_ties))
        self.assertGreaterEqual(len(by), 2, by)       # 離れの違う面で品番が分かれる
        need = [wall_tie_required_length_mm(m, i) for i in range(len(m.plan.edges))]
        for part in by:
            self.assertTrue(any(part.covers(round(n)) for n in need), (part.model_no, need))
        self.assertFalse([w for w in q.warnings if "伸縮範囲に合う品が無い" in w], q.warnings)


class TestTieRangeGap(unittest.TestCase):
    """伸縮範囲の隙間に落ちた面は、いちばん近い範囲の品で計上して差を書く.

    日建は KS200 160〜240 / KS400 250〜420 で 241〜249mm が隙間。combo_nd1800 の辺1
    （要245mm）は以前 既定品の KS700（380〜760）に落ちていた。
    """

    def test_nearest_range_not_the_longest(self):
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "combo_nd1800.json"))
        q = r.quantity
        need = {e.edge_index: round(wall_tie_required_length_mm(r.model, e.edge_index))
                for e in r.model.plan.edges}
        gap_faces = [e for e, n in need.items()
                     if not any(p.covers(n) for p in r.model.master.by_category("壁つなぎ"))]
        self.assertEqual(gap_faces, [1], need)
        by = {l.part.model_no: l.qty for l in q.lines if l.part.category == "壁つなぎ"}
        self.assertNotIn("KS700", by)          # 380〜760 は 245mm の面に載せない
        self.assertIn("KS400", by)
        hit = [w for w in q.warnings if "伸縮範囲に合う品が無い" in w]
        self.assertEqual(len(hit), 1, q.warnings)
        self.assertIn("辺1（要245mm", hit[0])
        self.assertIn("KS400 250〜420mm まで5mm", hit[0])

    def test_ks1000_is_available_for_wide_standoffs(self):
        for sid in ("nikken_nd1800", "nikken_nd1900", "waku"):
            with self.subTest(sid):
                m = load_master(sid)
                self.assertTrue(any(p.covers(1000) for p in m.by_category("壁つなぎ")))


if __name__ == "__main__":
    unittest.main()
