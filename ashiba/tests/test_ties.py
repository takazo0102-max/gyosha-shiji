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
        # 隅を離れで閉じる解き方（離れ 245mm の面が出る）で、壁つなぎの長さの選び方を見る
        r = solve_all({**load_spec(root / "examples" / "combo_nd1800.json"), "corner_steps": False})
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
        self.assertIn("東面(辺1)（要245mm", hit[0])
        self.assertIn("KS400 250〜420mm まで5mm", hit[0])

    def test_ks1000_is_available_for_wide_standoffs(self):
        for sid in ("nikken_nd1800", "nikken_nd1900", "waku"):
            with self.subTest(sid):
                m = load_master(sid)
                self.assertTrue(any(p.covers(1000) for p in m.by_category("壁つなぎ")))


class TestTiesLeaveTheOpening(unittest.TestCase):
    """開口部で抜いた支柱（梁枠より下）に壁つなぎを付けない.

    格子の壁つなぎは開口部を知らずに決まるので、通路の真ん中に金具が描かれていた
    （複合サンプルの実機立面で発見）。両端の支柱へ寄せ、同じ位置は1本にまとめる。
    """

    def _model_with_opening(self):
        from ashiba.openings import Opening, validate_openings

        m = build(asagao=0)
        op = validate_openings(m, [Opening(0, 3600, 3600, level=2)])
        self.assertTrue(op.ok, [i.message for i in op.issues])
        return m, op

    def test_inner_ties_below_the_beam_move_to_the_end_posts(self):
        from ashiba.model import WallTie
        from ashiba.ties import relocate_ties_off_openings

        m, op = self._model_with_opening()
        beam_h = op.beam_heights[0]
        m.wall_ties = [t for t in m.wall_ties
                       if not (t.edge_index == 0 and 3600 < t.position_mm < 7200)]
        m.wall_ties.append(WallTie(0, 5400, int(beam_h) - 1800, "grid"))   # 通路の真ん中
        m.wall_ties.append(WallTie(0, 5400, int(beam_h) + 1800, "grid"))   # 梁枠上の支柱（残る）
        n0 = len(m.wall_ties)
        notes = relocate_ties_off_openings(m, op)
        self.assertEqual(len(m.wall_ties), n0)
        bad = [t for t in m.wall_ties if t.edge_index == 0 and 3600 < t.position_mm < 7200
               and t.height_mm < beam_h]
        self.assertEqual(bad, [])
        moved = [t for t in m.wall_ties if t.edge_index == 0 and t.height_mm == int(beam_h) - 1800
                 and t.position_mm in (3600.0, 7200.0)]
        self.assertTrue(moved)
        above = [t for t in m.wall_ties if t.position_mm == 5400 and t.height_mm == int(beam_h) + 1800]
        self.assertEqual(len(above), 1)
        self.assertEqual(len(notes), 1)
        self.assertIn("南面 1本", notes[0])

    def test_duplicate_at_the_target_is_merged(self):
        from ashiba.model import WallTie
        from ashiba.ties import relocate_ties_off_openings

        m, op = self._model_with_opening()
        h = int(op.beam_heights[0]) - 1800
        m.wall_ties = [WallTie(0, 3600, h, "grid"), WallTie(0, 4500, h, "grid")]
        notes = relocate_ties_off_openings(m, op)
        self.assertEqual(len(m.wall_ties), 1)
        self.assertIn("1本にまとめて", notes[0])

    def test_optimizer_checks_the_relocated_layout(self):
        """寄せた後の配置で風荷重の検定が成立する間隔を選ぶ（opening_beam は寄せた後に落ちていた）."""
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "opening_beam.json"))
        self.assertTrue(r.structural.wall_tie.ok, r.structural.wall_tie)
        op = r.openings
        for i, o in enumerate(op.openings):
            bad = [t for t in r.model.wall_ties if t.edge_index == o.edge_index
                   and o.start_mm < t.position_mm < o.end_mm and t.height_mm < op.beam_heights[i]]
            self.assertEqual(bad, [], i)
        # 寄せた本数があるときだけ割付の警告に出る（採用した間隔で通路に当たらなければ無し）
        notes = [w[2] for w in r.warnings if "両端の支柱へ寄せました" in w[2]]
        self.assertEqual(len(notes), 1 if r.tie_opt.notes else 0, notes)

    def test_optimizer_checks_with_the_attachment_ties(self):
        """朝顔取付部の壁つなぎを載せた一覧で間隔を選ぶ（L形は後から足すと検定比1.23で落ちた）."""
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "l_shape.json"))
        self.assertTrue(r.structural.wall_tie.ok, r.structural.wall_tie)
        # 最適化時の検定比と最終の検定比は同じ一覧なので一致する
        self.assertAlmostEqual(r.tie_opt.wall_tie.ratio, r.structural.wall_tie.ratio, places=2)

    def test_hoist_mast_ties_leave_the_opening_too(self):
        """マスト控えの壁つなぎは最適化の後で足される。それも抜いた支柱には付けない."""
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "examples" / "opening_beam.json").read_text(encoding="utf-8"))
        spec["hoists"] = [{"edge_index": 0, "position_mm": 5400, "tie_every_mm": 3600}]   # 通路の真ん中
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        beam_h = r.openings.beam_heights[0]
        bad = [t for t in r.model.wall_ties if t.edge_index == 0 and 3600 < t.position_mm < 7200
               and t.height_mm < beam_h]
        self.assertEqual(bad, [])
        hoist_ties = [t for t in r.model.wall_ties if t.kind == "hoist"]
        self.assertTrue(hoist_ties)
        self.assertTrue([t for t in hoist_ties if t.position_mm in (3600.0, 7200.0)])
        self.assertTrue([w for w in r.warnings if "両端の支柱へ寄せました" in w[2]])

    def test_beam_end_ties_are_added_at_the_beam_height(self):
        """梁枠取付部（両端支柱・梁枠高さ）の壁つなぎが一覧に入り、内訳にも出る."""
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "opening_beam.json"))
        op = r.openings
        for i, o in enumerate(op.openings):
            h = int(op.beam_heights[i])
            for x in (o.start_mm, o.end_mm):
                self.assertTrue([t for t in r.model.wall_ties
                                 if t.edge_index == o.edge_index and abs(t.position_mm - x) < 1e-6
                                 and t.height_mm == h], (i, x, h))
        kinds = {t.kind for t in r.model.wall_ties}
        # 格子の金具と重ならない分だけ beam として残る（重なれば grid で兼ねる）
        self.assertTrue("beam" in kinds or all(
            any(t.edge_index == o.edge_index and t.height_mm == int(op.beam_heights[i]) and t.kind == "grid"
                for t in r.model.wall_ties) for i, o in enumerate(op.openings)))
        self.assertEqual(r.quantity.qty_of("壁つなぎ"), len(r.model.wall_ties))

    def test_quantity_notes_list_ties_per_face(self):
        """面ごとの本数と品番が数量の注記に出る（面で品番が変わるので行の合計だけでは足りない）."""
        m = build()
        q = take_off(m)
        note = next(n for n in q.notes if n.startswith("壁つなぎの面別本数"))
        total = 0
        import re
        for face_part in note.split(": ", 1)[1].split("／"):
            n = int(re.search(r" (\d+)本", face_part).group(1))
            inner = sum(int(x) for x in re.findall(r"[A-Z0-9-]+ (\d+)", face_part.split("（")[1]))
            self.assertEqual(n, inner, face_part)
            total += n
        self.assertEqual(total, len(m.wall_ties))
        self.assertIn("南面", note)

    def test_no_opening_changes_nothing(self):
        from ashiba.ties import relocate_ties_off_openings

        m = build(asagao=0)
        before = list(m.wall_ties)
        self.assertEqual(relocate_ties_off_openings(m, None), [])
        self.assertEqual(m.wall_ties, before)


class TestTiesInBridgedZones(unittest.TestCase):
    """渡した区間（凹み・斜辺）の中の壁つなぎは、増えた離れで長さを選ぶ."""

    def test_recess_adds_its_depth_inside_the_zone(self):
        master = load_master("shinwa_A")
        notch = [(0, 0), (12000, 0), (12000, 300), (15600, 300), (15600, 0),
                 (30000, 0), (30000, 20000), (0, 20000)]
        m = ScaffoldModel(master=master, plan=solve_plan(notch, master),
                          elevation=solve_elevation(16300, master=master), config=ScaffoldConfig())
        z = next(z for z in m.plan.bridged_zones if z.kind == "凹み")
        inside = (z.start_mm + z.end_mm) / 2
        base = wall_tie_required_length_mm(m, z.edge_index)
        self.assertAlmostEqual(wall_tie_required_length_mm(m, z.edge_index, inside), base + 300, places=6)
        self.assertAlmostEqual(wall_tie_required_length_mm(m, z.edge_index, z.start_mm - 100), base, places=6)
        q = take_off(m)
        self.assertEqual(sum(l.qty for l in q.lines if l.part.category == "壁つなぎ"), len(m.wall_ties))

    def test_diagonal_zone_reports_unreachable_ties(self):
        import json
        import tempfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all

        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        spec["outline_mm"] = [[0, 0], [30000, 0], [30000, 12000], [20000, 20000], [0, 20000]]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            r = solve_all(load_spec(p))
        # 届かない位置の壁つなぎは届く支柱へ寄せるので、数量側の「届かない」手配は出ない
        self.assertFalse([w for w in r.quantity.warnings if "躯体に届きません" in w], r.quantity.warnings)
        moved = [w[2] for w in r.warnings if "届く位置の支柱へ寄せました" in w[2]]
        self.assertTrue(1 <= len(moved) <= 2, [w[2] for w in r.warnings])   # 格子／取付部で最大2件
        # 届かない帯は検定から除いて別途の控えを求める。壁つなぎの検定はその外で成立する
        self.assertTrue(r.structural.wall_tie.ok, r.structural.wall_tie)
        self.assertTrue([w for w in r.structural.warnings if "検定から除いています" in w], r.structural.warnings)
        # 法規#7: 帯は別途の控えで拘束する前提。NGではなく前提を書いたWARN
        c7 = next(c for c in r.checks if c.check_id == 7)
        self.assertEqual(c7.status, "WARN", c7.message)
        self.assertIn("届かない帯", c7.message)
        self.assertIn("別途の控え", c7.message)
        self.assertTrue(r.verdict["ok"], r.verdict)
        longest = max(p.adjustable_range()[1] for p in r.model.master.by_category("壁つなぎ"))
        for t in r.model.wall_ties:
            self.assertLessEqual(wall_tie_required_length_mm(r.model, t.edge_index, t.position_mm), longest + 1e-6)
        # 区間がコーナーから始まる面: コーナー支柱（位置0）も深い側なので壁つなぎを付けない
        from ashiba.ties import unreachable_bands

        bands = unreachable_bands(r.model)
        z0 = next(z for z in r.model.plan.bridged_zones if z.kind == "斜辺" and z.deep_end == "start")
        self.assertEqual(bands[z0.edge_index][0][0], 0.0)
        self.assertFalse([t for t in r.model.wall_ties if t.edge_index == z0.edge_index and t.position_mm < 1])
        z1 = next(z for z in r.model.plan.bridged_zones if z.kind == "斜辺" and z.deep_end == "end")
        e1 = next(e for e in r.model.plan.edges if e.edge_index == z1.edge_index)
        self.assertAlmostEqual(bands[z1.edge_index][-1][1], e1.scaffold_length)
        # 区間の中でも線形に増える: 浅い端の壁つなぎは通常品で足りる
        z = next(z for z in r.model.plan.bridged_zones if z.kind == "斜辺" and z.deep_end == "end")
        shallow = wall_tie_required_length_mm(r.model, z.edge_index, z.start_mm + 100)
        deep = wall_tie_required_length_mm(r.model, z.edge_index, z.end_mm - 100)
        self.assertLess(shallow, deep)
        self.assertEqual(sum(l.qty for l in r.quantity.lines if l.part.category == "壁つなぎ"),
                         len(r.model.wall_ties))


if __name__ == "__main__":
    unittest.main()

