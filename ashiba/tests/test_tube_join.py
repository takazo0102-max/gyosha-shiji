"""別の足場を単管でつなぐ（GLOOBE の「別の足場と接続する単管」。2026-11-02 の開発ループ）."""

from __future__ import annotations

import unittest

from _path import SRC  # noqa: F401

from ashiba.tube_join import Join, part_params, pick_tube, plan_join, report


class TestTubeJoin(unittest.TestCase):
    def test_tube_length_and_order(self):
        """支柱の間 2,900 は突き出し 50 ずつ足して 3.0M、3段に単管3本と直交クランプ6個（日建 Vol.10 p372・p378）."""
        self.assertEqual((pick_tube(3000.0), pick_tube(3001.0), pick_tube(6200.0)), (3000, 3500, 0))
        j = plan_join(Join("つなぎ1", (0.0, 0.0), (2900.0, 0.0), [1800.0, 3600.0, 5400.0]))
        self.assertEqual(j.tube, 3000)
        q = {a: n for a, n, _u in j.quantity}
        self.assertEqual((q["単管 3.0M（つなぎ・手すり）"], q["ARC1 兼用直交クランプ"]), (3, 6))
        self.assertEqual(part_params(j)["zList"], "1800,3600,5400")
        self.assertIn("ARC1", report([j]))

    def test_guard_brace_and_limits(self):
        """手すり・中桟で1層3本、層の間の斜めは自在クランプ。6m を超える間は単管が届かない."""
        j = plan_join(Join("つなぎ2", (0.0, 0.0), (1500.0, 0.0), [1800.0, 3600.0], guard=True, brace=True))
        self.assertEqual(j.rows, [1800.0, 2250.0, 2750.0, 3600.0, 4050.0, 4550.0])
        q = {a: n for a, n, _u in j.quantity}
        self.assertEqual((q["単管 1.8M（つなぎ・手すり）"], q["単管 2.5M（斜めの補強）"], q["ARC2 兼用自在クランプ"]), (6, 1, 2))
        far = plan_join(Join("つなぎ3", (0.0, 0.0), (6500.0, 0.0), [1800.0]))
        self.assertEqual(({c.item: c.status for c in far.checks}["長さ"], far.quantity), ("NG", []))


if __name__ == "__main__":
    unittest.main()
