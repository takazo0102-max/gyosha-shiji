"""山留め壁（src/ashiba/retaining.py・scripts/ywall_run.py。利用者の指定 2026-11-05「山留めの種類も増やして シートパイルや簡易山留め
など … Hこう横やいたは矢板の平米拾えるようにしてかかりしろは厚みの分だけにして１次ねぎりと2次ねぎりで分けれるようにあと矢板を止める
さんぎも」）."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ashiba import retaining as RT  # noqa: E402

RECT = [(0.0, 0.0), (12000.0, 0.0), (12000.0, 8000.0), (0.0, 8000.0)]


def wall(kind="oyagui", **kw) -> RT.Wall:
    kw.setdefault("depth", 4000.0)
    return RT.plan(RT.Wall("山留め1", kind, pts=list(kw.pop("pts", RECT)), closed=kw.pop("closed", True), **kw))


def qty(w, item):
    return next(q for q in RT.quantities(w) if q.item.strip() == item)


class TestOyagui(unittest.TestCase):
    def test_board_length_uses_thickness_as_kakari(self):
        """矢板の長さ＝フランジの先どうしの内法＋掛かり代×2、掛かり代＝矢板の厚さ（利用者の指定）."""
        w = wall(lag_t=35.0)
        e = w.edges[0]                                   # 12m を 1500 ごとに 8 バイ
        self.assertEqual(len(e.bays), 8)
        self.assertAlmostEqual(e.lag_len[0], 1500.0 - 300.0 + 2 * 35.0)
        self.assertEqual(w.kakari_mm, 35.0)
        self.assertEqual(next(c for c in w.checks if c.item == "掛かり代").status, "注意")   # 土木の要領の 40 未満
        self.assertEqual(wall(lag_t=40.0).checks[4].status, "OK")

    def test_corner_bay(self):
        """角の杭は次の辺の向きに立つので、手前の辺の最後の矢板は角の杭のフランジの面（芯から H/2 手前）で止める."""
        e = wall().edges[0]
        self.assertEqual(e.lag_ab[-1], (10500.0 + 150.0 - 40.0, 12000.0 - 150.0 - 5.0))
        line = wall(pts=[(0.0, 0.0), (3000.0, 0.0), (3000.0, 3000.0)], closed=False)
        self.assertEqual(line.edges[0].lag_ab[-1][1], 3000.0 - 150.0 - 5.0)    # 途中の角
        self.assertEqual(line.edges[-1].lag_ab[-1][1], 3000.0 - 150.0 + 40.0)  # 線の終わりは杭のフランジに掛ける

    def test_area_by_stage(self):
        """横矢板の m² は 根切り深さ × 周長（根入れは含まない）、1次・2次根切りに分ける."""
        w = wall(stages_mm=[2500.0])
        self.assertAlmostEqual(qty(w, "横矢板（積算）").qty, 40.0 * 4.0)
        self.assertAlmostEqual(qty(w, "横矢板 1次根切り").qty, 40.0 * 2.5)
        self.assertAlmostEqual(qty(w, "横矢板 2次根切り").qty, 40.0 * 1.5)
        self.assertEqual([s.name for s in w.stages], ["1次根切り", "2次根切り"])

    def test_boards_per_stage(self):
        """1次根切りの底（2.5m）までに入る枚数（12 枚＝2.4m）、残りは 2次根切りで（4m まで 20 枚）."""
        st = RT.make_stages(4000.0, [2500.0])
        self.assertEqual(RT.boards_per_stage(st, 200.0), [12, 8])
        self.assertEqual(RT.boards_per_stage(RT.make_stages(3100.0, []), 200.0), [16])
        self.assertEqual([s.bottom for s in RT.make_stages(4000.0, [0.0, 2000.0, 5000.0])], [2000.0, 4000.0])

    def test_sanki_and_wedges(self):
        """矢板止めの桟木はバイの両端に段ごと、くさびは矢板1枚の左右に各2個."""
        w = wall(stages_mm=[2000.0])
        nbays = sum(len(e.bays) for e in w.edges)
        self.assertEqual(nbays, 8 + 6 + 8 + 6)
        self.assertEqual(qty(w, "矢板止めの桟木 1次根切り").qty, nbays * 2)
        self.assertEqual(qty(w, "くさび").qty, nbays * 20 * 4)
        piles = qty(w, "親杭")
        self.assertEqual(piles.qty, 28)                   # 閉じた線は角の杭を数え直さない
        self.assertIn("L=5.5m", piles.spec)               # 根切り 4m＋根入れ 1.5m

    def test_embed_and_size_checks(self):
        w = wall(embed=1200.0, model="H-250")
        self.assertEqual(w.embed_mm, 1500.0)              # 50cm に切り上げ
        self.assertEqual(next(c for c in w.checks if c.item == "親杭の大きさ").status, "WARN")   # 3m 以深は H-300
        self.assertEqual(next(c for c in wall(embed=1000.0).checks if c.item == "根入れ").status, "WARN")
        shallow = wall(depth=2500.0)
        self.assertEqual(next(c for c in shallow.checks if c.item == "横矢板の曲げ").status, "OK")

    def test_part_params(self):
        w = wall(stages_mm=[2000.0])
        p = RT.part_params(w, w.edges[0])
        self.assertEqual(p["ywKind"], 1)
        self.assertEqual(len(p["lgA"].split(",")), 8)
        self.assertEqual(p["lgN"], "10.0,10.0")
        self.assertAlmostEqual(p["zBot"], -5.5)
        self.assertAlmostEqual(p["kak"], 0.04)


class TestSheetPiles(unittest.TestCase):
    def test_count_and_weight(self):
        """枚数＝中心線の長さ ÷ 有効幅の切り上げ、質量＝長さ×単位質量×枚数（農水 16-27 の例: 30.8m・Ⅲ型 10m → 77枚・46.2t）."""
        w = wall("sp_u", pts=[(0.0, 0.0), (30800.0, 0.0)], closed=False, depth=6500.0, embed=3500.0, model="III")
        q = RT.quantities(w)[0]
        self.assertEqual(q.qty, 77)
        self.assertIn("46.20t", q.note)

    def test_corners_and_profile(self):
        w = wall("sp_u")
        self.assertEqual(qty(w, "コーナー矢板").qty, 4)
        prof = RT.sheet_profile("sp_u", "III")
        xs = [p[0] for p in prof]
        self.assertAlmostEqual(min(xs), 0.0, delta=10.0)
        self.assertAlmostEqual(max(xs), 400.0, delta=10.0)
        self.assertAlmostEqual(max(p[1] for p in prof), 62.5, delta=0.5)      # 有効高さ 125 の半分
        hat = wall("sp_hat")
        self.assertEqual(next(c for c in hat.checks if c.item == "角").status, "注意")
        self.assertFalse(RT.part_params(hat, hat.edges[0])["spAlt"])

    def test_light_and_alu(self):
        lsp = wall("lsp", depth=4500.0)
        self.assertEqual(next(c for c in lsp.checks if c.item == "掘削の深さ").status, "WARN")
        alu = wall("alu", depth=3000.0)
        self.assertEqual(alu.embed_mm, 200.0)
        self.assertEqual(alu.wall_len, 3500.0)            # 3.2m を 0.5m に切り上げ


class TestSupports(unittest.TestCase):
    def test_wales_and_struts(self):
        """深さ 3m を超えたら腹起し（頭から 1m・その下 3m）・ブラケット（2m 以内・両端）・切梁（狭い向き・水平 5m 以下）."""
        w = wall(depth=5000.0)
        self.assertEqual(w.wales, [1000.0, 4000.0])
        self.assertEqual([s.bottom for s in w.stages], [2150.0, 5000.0])        # 腹起しの下端＋余掘り 1.0m までを1次根切り
        e0, e1 = w.edges[0], w.edges[1]
        self.assertEqual(e0.wale_x, (150.0 + 100.0 + 300.0, 12000.0 - 250.0))
        gaps = [b - a for a, b in zip(e0.brackets, e0.brackets[1:])]
        self.assertTrue(max(gaps) <= 2000.0 and e0.brackets[0] == 700.0)
        self.assertEqual(len(e0.strut_x), 3)                                     # 11.2m を 5m 以下に
        self.assertEqual(e0.strut_len, [8000.0 / 2 - 550.0] * 3)
        self.assertEqual(e1.strut_x, [])                                          # 長い向きには渡さない
        q = {x.item.strip(): x for x in RT.quantities(w)}
        self.assertEqual(q["切梁"].qty, 3 * 2)
        self.assertAlmostEqual(q["切梁（積算）"].qty, 11.7 * 7.7 * 2, places=1)
        self.assertEqual(q["腹起しのブラケット"].qty, (7 + 5) * 2 * 2)

    def test_support_options(self):
        self.assertEqual(wall(depth=3000.0).wales, [])                          # 自動は 3m まで自立
        self.assertEqual(wall(depth=3000.0, support="wale").wales, [1000.0])
        self.assertEqual(wall(depth=6000.0, support="none").wales, [])
        self.assertEqual(wall("tatekomi", depth=5000.0, support="wale").wales, [])
        self.assertEqual(len(wall("lsp", depth=3800.0).wales), 3)               # 軽量鋼矢板は 4.0m 未満 3段
        p = RT.part_params(wall(depth=5000.0), wall(depth=5000.0).edges[0])
        self.assertTrue(p["wlOn"])
        self.assertEqual(p["wlZ"], "1000.0,4000.0")


class TestOthers(unittest.TestCase):
    def test_tatekomi(self):
        """パネルは深さ以上で一番はみ出しの少ない積み、切梁は狭い向き（掘削幅）だけ."""
        w = wall("tatekomi", pts=[(0.0, 0.0), (12000.0, 0.0), (12000.0, 3000.0), (0.0, 3000.0)], depth=3000.0)
        self.assertEqual(RT.tatekomi_stack(w)[0], [2000.0, 1000.0])
        self.assertTrue(all(v > 0 for v in w.edges[0].struts))
        self.assertTrue(all(v == 0 for v in w.edges[1].struts))
        self.assertEqual(next(c for c in w.checks if c.item == "掘削幅").status, "OK")
        self.assertEqual(next(c for c in wall("tatekomi", model="TS1", depth=4000.0).checks if c.item == "掘削の深さ").status, "NG")

    def test_smw_cores(self):
        every = wall("smw", core_every=1)
        other = wall("smw", core_every=2)
        nh = sum(len(e.piles) for e in every.edges)
        self.assertEqual(sum(len(e.cores) for e in every.edges), nh)
        self.assertEqual(sum(len(e.cores) for e in other.edges), (nh + 1) // 2)

    def test_inner_polygon(self):
        """根切り図が掘る山留めの内側の面（親杭は H/2 だけ中へ）."""
        poly = RT.inner_polygon(wall())
        xs, ys = sorted({round(p[0]) for p in poly}), sorted({round(p[1]) for p in poly})
        self.assertEqual((xs, ys), ([150, 11850], [150, 7850]))
        self.assertEqual(RT.inner_polygon(wall(pts=[(0.0, 0.0), (5000.0, 0.0)], closed=False)), [])

    def test_every_kind_plans(self):
        for k in RT.KIND_LABELS:
            with self.subTest(kind=k):
                w = wall(k, depth=3000.0)
                self.assertTrue(RT.quantities(w))
                p = RT.part_params(w, w.edges[0])
                self.assertEqual(p["ywKind"], RT.KIND_NO[k])
                self.assertTrue(RT.label(w))


class TestRecord(unittest.TestCase):
    def test_recorded_polygons(self):
        """控え（山留め壁.json）から、選んだ部品か点を囲む山留めの内側の面."""
        import ywall_run as Y

        with tempfile.TemporaryDirectory() as d:
            rec = {"k": {"name": "山留め1", "kind": "oyagui", "model": "H-300", "pts": [list(p) for p in RECT], "closed": True,
                         "depth": 3000.0, "guids": ["AAAA-1"]}}
            (Path(d) / Y.RECORD).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(len(Y.recorded_polygons(d, ["aaaa-1"])), 1)
            self.assertEqual(Y.recorded_polygons(d, ["BBBB"]), [])
            self.assertEqual([h[2] for h in Y.recorded_polygons(d, point=(6000.0, 4000.0))], [3000.0])
            self.assertEqual(Y.recorded_polygons(d, point=(20000.0, 4000.0)), [])


if __name__ == "__main__":
    unittest.main()
