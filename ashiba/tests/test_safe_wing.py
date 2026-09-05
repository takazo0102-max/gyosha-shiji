"""信和セーフウイング（簡易落下物防止機材）を朝顔の種別として扱う.

資料 swg.pdf: 張出1,280mm・25°、支柱ごとに1本、張出部にSD-4018踏板3枚。
防護棚（突出2m以上）ではないので、10m以上の足場では法規#10が「朝顔が別途必要」のNG。
B用も踏板はキャッチャー用（A系列）を使う指示なので、B系列では踏板が手配項目に出る。
"""

import json
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.cli import InputError, load_spec, solve_all
from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import check_asagao
from ashiba.master import load_master
from ashiba.model import (
    ASAGAO_KIND_SAFE_WING, AsagaoSpec, ScaffoldConfig, ScaffoldModel,
)
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off

ROOT = Path(__file__).resolve().parents[1]
RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(series="shinwa_A", height=16300, wing=True, stages=1):
    master = load_master(series)
    spec = AsagaoSpec(stages=stages, kind=ASAGAO_KIND_SAFE_WING,
                      projection_mm=1280, angle_deg=25) if wing else None
    return ScaffoldModel(
        master=master, plan=solve_plan(RECT, master),
        elevation=solve_elevation(height, master=master),
        config=ScaffoldConfig(asagao=spec), building_height_mm=height - 300,
    )


def wing_part(master):
    return next((p for p in master.by_category("朝顔") if p.note.startswith("セーフウイング")), None)


class TestMasterRows(unittest.TestCase):
    def test_both_shinwa_series_have_the_wing(self):
        for sid in ("shinwa_A", "shinwa_B"):
            with self.subTest(sid):
                p = wing_part(load_master(sid))
                self.assertIsNotNone(p)
                self.assertGreater(p.weight_kg, 5.0)
                # 朝顔の集計が本体・受けブラケット・方杖・コーナーとして拾わないこと
                for word in ("防護棚", "受けブラケット", "方杖", "コーナー"):
                    self.assertNotIn(word, p.note)

    def test_wing_is_never_used_as_asagao_panel(self):
        """通常の朝顔指定でセーフウイングが朝顔本体として計上されないこと."""
        master = load_master("shinwa_A")
        m = ScaffoldModel(
            master=master, plan=solve_plan(RECT, master),
            elevation=solve_elevation(16300, master=master),
            config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)), building_height_mm=16000,
        )
        q = take_off(m)
        self.assertFalse([l for l in q.lines if l.part.note.startswith("セーフウイング")])


class TestQuantity(unittest.TestCase):
    def test_one_arm_per_post_and_three_decks_per_span(self):
        m = build()
        base = take_off(build(wing=False))
        q = take_off(m)
        wing = [l for l in q.lines if l.part.note.startswith("セーフウイング")]
        self.assertEqual(len(wing), 1)
        self.assertEqual(wing[0].qty, m.plan.total_posts)
        spans = sum(len(ep.spans) for ep in m.plan.edges)
        self.assertEqual(q.qty_of("踏板") - base.qty_of("踏板"), 3 * spans)
        # 通常の朝顔部材（本体・受けブラケット・方杖）は出ない
        self.assertFalse([l for l in q.lines if l.part.category == "朝顔"
                          and not l.part.note.startswith("セーフウイング")])
        self.assertFalse([n for n in q.notes if "マスタに該当部材がありません" in n], q.notes)

    def test_two_stages_double_it(self):
        one, two = take_off(build(stages=1)), take_off(build(stages=2))
        w1 = next(l.qty for l in one.lines if l.part.note.startswith("セーフウイング"))
        w2 = next(l.qty for l in two.lines if l.part.note.startswith("セーフウイング"))
        self.assertEqual(w2, 2 * w1)

    def test_b_series_orders_catcher_decks_instead_of_counting_b_decks(self):
        m = build("shinwa_B")
        base = take_off(build("shinwa_B", wing=False))
        q = take_off(m)
        self.assertTrue([l for l in q.lines if l.part.note.startswith("セーフウイング")])
        self.assertEqual(q.qty_of("踏板"), base.qty_of("踏板"))   # B用踏板は使わない
        hit = [w for w in q.warnings if "キャッチャー用踏板" in w and "手配" in w]
        self.assertTrue(hit, q.warnings)
        spans = sum(len(ep.spans) for ep in m.plan.edges)
        total = sum(int(t.split("×")[1].rstrip("枚")) for t in
                    hit[0].split(": ")[1].split("。")[0].split("、"))
        self.assertEqual(total, 3 * spans)

    def test_series_without_the_wing_reports_not_silent(self):
        q = take_off(build("nikken_nd1800"))
        self.assertTrue([w for w in q.warnings
                         if "セーフウイング" in w and "マスタに該当部材がありません" in w], q.warnings)

    def test_provisional_notice_names_the_wing(self):
        q = take_off(build())
        self.assertTrue([w for w in q.warnings if "型番仮" in w and "SW-A" in w])


class TestLawCheck(unittest.TestCase):
    def test_tall_scaffold_needs_a_real_asagao(self):
        r = check_asagao(build(height=16300))
        self.assertEqual(r.status, "NG")
        self.assertIn("朝顔1段が別途必要", r.message)
        self.assertIn("セーフウイング", r.message)

    def test_low_scaffold_is_ok_with_the_wing(self):
        r = check_asagao(build(height=8000))
        self.assertEqual(r.status, "OK")
        self.assertIn("セーフウイング", r.message)


class TestCli(unittest.TestCase):
    def _solve(self, asagao):
        spec = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
        spec["asagao"] = asagao
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return solve_all(load_spec(p))

    def test_kind_flows_from_the_input(self):
        r = self._solve({"kind": "セーフウイング", "stages": 1})
        a = r.model.config.asagao
        self.assertEqual(a.kind, ASAGAO_KIND_SAFE_WING)
        self.assertEqual(a.projection_mm, 1280)   # マスタの実寸（張出）
        self.assertEqual(a.angle_deg, 25)
        c = next(c for c in r.checks if c.check_id == 10)
        self.assertEqual(c.status, "NG")
        self.assertFalse(r.verdict["ok"])

    def test_unknown_kind_is_an_input_error(self):
        with self.assertRaises(InputError) as cm:
            self._solve({"kind": "セイフウイング", "stages": 1})
        self.assertIn("asagao.kind", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
