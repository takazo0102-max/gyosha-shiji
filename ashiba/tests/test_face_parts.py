"""選んだ部品（面の区間）だけ足場の種類を切り替える（利用者の指定 2026-10-24: 面の切り替えはやめて選択した足場の変更に）."""

import sys
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import solve_groups
from ashiba.face_forms import face_groups, face_segments, parse_face_forms, split_key, updated_face_forms, RESET

ROOT = Path(__file__).resolve().parents[1]
RECT = [[0, 0], [24000, 0], [24000, 12000], [0, 12000]]
FACES = ["南面", "東面", "北面", "西面"]


class TestRanges(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(split_key("南面[10974-16461]"), ("南面", 10974.0, 16461.0))
        self.assertEqual(split_key("南[16461〜10974]"), ("南面", 10974.0, 16461.0))
        self.assertEqual(split_key("東面"), ("東面", None, None))
        ff = parse_face_forms("南面[9145-16461]=ブラケット足場(支柱);東面=単管抱き足場")
        self.assertEqual(ff, {"南面[9145-16461]": "ブラケット足場（支柱）", "東面": "単管抱き足場"})

    def test_segments_and_groups(self):
        ff = parse_face_forms("南面[9145-16461]=ブラケット足場（支柱）")
        self.assertEqual(face_segments(ff, "南面"), [(0.0, 9145.0, ""), (9145.0, 16461.0, "ブラケット足場（支柱）"),
                                                   (16461.0, None, "")])
        spec = {"face_forms": "南面[9145-16461]=ブラケット足場（支柱）",
                "openings": [{"face": "南面", "start_mm": 10974, "beam_span_mm": 3658}]}
        g = dict(face_groups(spec, FACES))
        self.assertEqual(set(g), {"", "元の足場（2）", "ブラケット足場（支柱）"})
        self.assertEqual(g[""]["_face_range"], {"南面": [0.0, 9145.0]})
        self.assertEqual(g["元の足場（2）"]["_face_range"], {"南面": [16461.0, -1.0]})
        # 開口は区間の始点からの位置に直り、区間の外の組からは外れる
        self.assertEqual(g["ブラケット足場（支柱）"]["openings"][0]["start_mm"], 10974 - 9145)
        self.assertEqual(g[""]["openings"], [])

    def test_update_replaces_overlapping_ranges_and_resets(self):
        ff = updated_face_forms("南面[9145-16461]=ブラケット足場（支柱）", ["南面[12803-16461]"], "一側足場")
        self.assertEqual(ff, {"南面[12803-16461]": "一側足場"})
        self.assertEqual(updated_face_forms(ff, ["南面[12803-16461]"], RESET), {})
        self.assertEqual(updated_face_forms("南面[0-3658]=一側足場;東面=単管抱き足場", ["南面"], RESET),
                         {"東面": "単管抱き足場"})


class TestSolveParts(unittest.TestCase):
    def test_pieces_line_up_and_ends_are_open(self):
        from ashiba.gdl_params import line_params

        runs = solve_groups({"outline_mm": RECT, "eaves_height_mm": 9000, "series_id": "nikken_nd1800",
                             "face_forms": "南面[9145-16461]=ブラケット足場（支柱）"})
        pieces = []
        for label, r in runs:
            m = r.model
            for e in m.plan.edges:
                if e.edge_index == 0:
                    p = line_params(m, e, stair_plan=r.stair_plan)
                    pieces.append((e.start_post, e.end_post, e.standoff, p["endOpenS"], p["endOpenE"], p["faceOff"]))
        pieces.sort(key=lambda t: t[0][0])
        self.assertEqual(len(pieces), 3)
        for (s0, e0, so0, *_r0), (s1, e1, so1, *_r1) in zip(pieces, pieces[1:]):
            self.assertAlmostEqual(e0[0], s1[0], places=3)          # 切れ目の支柱がそろう
            self.assertAlmostEqual(so0, so1)                       # 離れもそろう
        self.assertEqual([(p[3], p[4]) for p in pieces], [(0, 1), (1, 1), (1, 0)])   # 切れ目は開放端
        self.assertEqual([round(p[5] * 1000) for p in pieces], [0, 9145, 16461])

    def test_piece_key_from_the_selected_part(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import switch_face_form as S

        p = {"spanList": "1829,1829,1829,1829", "levelList": "945,2745", "faceOff": 9.145, "faceLen": 24.691,
             "segSpanA": 3, "segSpanB": 4}
        self.assertEqual(S.piece_key("南面", p), "南面[12803-16461]")
        whole = {"spanList": "1829,1829", "levelList": "945,2745", "faceOff": 0.0, "faceLen": 3.658}
        self.assertEqual(S.piece_key("南面", whole), "南面")


if __name__ == "__main__":
    unittest.main()
