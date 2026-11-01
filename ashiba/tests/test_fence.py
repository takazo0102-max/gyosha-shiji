"""歩行者の安全（開発ループ 2026-11-01: 他に必要な仮設材の6番）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.fence import FenceRun, part_params, plan_run, report


class TestFence(unittest.TestCase):
    def test_units_and_order(self):
        """日建 Vol.10 の規格で1基ずつ: PPフェンス 1.5m、スタンドは 1.8m 以内に詰める、防護柵は切れない."""
        pts = [(0, 0), (20000, 0), (20000, 6000)]
        pp = plan_run(FenceRun("柵1", pts, 1))
        self.assertEqual(pp.units, [14, 4])
        q = {a: n for a, n, _u in pp.quantity}
        self.assertEqual((q["PP1512G PPフェンス"], q["PPJ PPジョイント"], q["PPW PPウェイト"]), (18, 17, 20))
        st = plan_run(FenceRun("柵2", pts, 2))
        self.assertEqual((st.units, st.over), ([12, 4], [0.0, 0.0]))
        q = {a: n for a, n, _u in st.quantity}
        self.assertEqual((q["BS020 スタンドバリケード C型"], q["単管 2.0M（横桟 上下2段）"]), (18, 32))
        gr = plan_run(FenceRun("柵3", pts, 4))
        self.assertEqual({c.item: c.status for c in gr.checks}["割付"], "WARN")       # 6m の区間に 5m を2基で 4m 余る

    def test_checks(self):
        r = plan_run(FenceRun("柵1", [(0, 0), (20000, 0)], 1, walk_w=1200.0, busy=True, road_side=True))
        st = {c.item: c.status for c in r.checks}
        self.assertEqual((st["歩行者通路の幅"], st["車両との区分"]), ("NG", "WARN"))
        ok = plan_run(FenceRun("柵2", [(0, 0), (20000, 0)], 3, walk_w=1500.0, busy=True, road_side=True))
        st = {c.item: c.status for c in ok.checks}
        self.assertEqual((st["歩行者通路の幅"], st["車両との区分"]), ("OK", "OK"))
        self.assertIn("BBJW4", report([ok]))
        self.assertEqual(part_params(ok)["cX"], "0,20000")


if __name__ == "__main__":
    unittest.main()
