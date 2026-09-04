"""取付部・マスト控えの壁つなぎを格子と同じ一覧に統合する（図面・数量・検定の一致）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.gdl_params import line_params
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.platforms import Hoist, LoadingStage, validate_platforms
from ashiba.quantity import take_off
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


if __name__ == "__main__":
    unittest.main()
