"""仮設工事の工程表と工程の模型（利用者の指定 2026-11-04「工程表作れる？」「工程表に合わせてモデルを自動作成できるようにして」）."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.schedule import Dep, Task, days_of, display_order, schedule, to_markdown, to_xlsx
from ashiba.schedule_calendar import WorkCalendar, national_holidays
from ashiba.schedule_plan import ScheduleConditions, build
from ashiba.schedule_rates import RATES, scaffold_rate
from ashiba.schedule_sources import Quantities, collect, md_rows
from ashiba.schedule_steps import GROUP_TASKS, layer_state, scaffold_height, steps


class TestCalendar(unittest.TestCase):
    def test_holidays_2026(self):
        """2026年の国民の祝日（内閣府の一覧と同じ。振替 5/6・国民の休日 9/22）."""
        want = ["01-01", "01-12", "02-11", "02-23", "03-20", "04-29", "05-03", "05-04", "05-05", "05-06", "07-20", "08-11",
                "09-21", "09-22", "09-23", "10-12", "11-03", "11-23"]
        self.assertEqual(sorted(f"{d:%m-%d}" for d in national_holidays(2026)), want)

    def test_workdays(self):
        cal = WorkCalendar()
        self.assertFalse(cal.is_work(dt.date(2026, 11, 8)))              # 日曜
        self.assertTrue(cal.is_work(dt.date(2026, 11, 7)))               # 土曜は既定で稼働
        self.assertFalse(WorkCalendar(sat_off=True).is_work(dt.date(2026, 11, 7)))
        self.assertFalse(cal.is_work(dt.date(2026, 12, 30)))             # 年末年始
        self.assertFalse(cal.is_work(dt.date(2026, 8, 14)))              # 夏季
        self.assertEqual(cal.add(dt.date(2026, 11, 2), 1), dt.date(2026, 11, 4))   # 11/3 文化の日を飛ばす
        self.assertEqual(cal.end_of(dt.date(2026, 11, 6), 3), dt.date(2026, 11, 9))  # 金・土・(日)・月
        self.assertEqual(cal.count(dt.date(2026, 11, 2), dt.date(2026, 11, 8)), 5)


class TestEngine(unittest.TestCase):
    def test_days_and_links(self):
        self.assertEqual(days_of(100, 30), 4)
        self.assertEqual(days_of(100, 30, 2), 2)
        self.assertEqual(days_of(0, 30), 0)
        cal = WorkCalendar()
        a = Task("a", "A", "準備", 3)
        b = Task("b", "B", "準備", 2, deps=[Dep("a", "FS")])
        c = Task("c", "C", "準備", 1, deps=[Dep("a", "SS", 1)])
        d = Task("d", "D", "準備", 1, deps=[Dep("a", "SS"), Dep("b", "FF", 2)])
        schedule([a, b, c, d], cal, dt.date(2026, 11, 2))
        self.assertEqual((a.start, a.end), (dt.date(2026, 11, 2), dt.date(2026, 11, 5)))   # 11/3 は休み
        self.assertEqual(b.start, dt.date(2026, 11, 6))
        self.assertEqual(c.start, dt.date(2026, 11, 4))
        self.assertEqual(d.end, cal.add(b.end, 2))                     # 前の終わり＋2 まで延びる
        self.assertEqual(d.days, cal.count(d.start, d.end))


class TestRates(unittest.TestCase):
    def test_from_the_tables(self):
        """K の歩掛り（人／数量）を割り振り（掛け 65・払い 35％）と班の人数で 1班1日の量に."""
        self.assertAlmostEqual(scaffold_rate(10, True).per_day, round(5 / (0.044 * 0.65), 1))
        self.assertAlmostEqual(scaffold_rate(15, False).per_day, round(5 / (0.049 * 0.35), 1))
        self.assertAlmostEqual(scaffold_rate(30, True).per_day, round(5 / (0.054 * 0.65), 1))
        self.assertEqual(RATES["敷鉄板"].per_day, 9.4)
        self.assertEqual(RATES["掘削"].per_day, 180.0)
        for k, r in RATES.items():
            self.assertTrue(r.source, k)                               # 出典か【目安】の理由がある
            self.assertTrue(r.per_day > 0 or r.days > 0, k)


class TestSources(unittest.TestCase):
    def test_collect_from_reports(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "仮囲い.md").write_text("| 品名 | 数 | 注 |\n|---|---|---|\n| 安全鋼板 SSK300 H3000 | 23 | 有効幅 540・延べ 12.4m・1枚 18.1kg |\n"
                                       "| 安全鋼板 SSK300 H3000 | 14 | 有効幅 540・延べ 7.4m |\n", encoding="utf-8")
            (p / "仮設建物.md").write_text("| 建物 | 型 | 連棟×段 | 用途 | 床面積 |\n|---|---|---|---|---|\n"
                                        "| 仮設建物1 | スーパーハウス | 3×2 | 事務所 | 75㎡ |\n| トイレ2 | 仮設トイレ（ハマネツ TU） | 4×1 | トイレ | 5㎡ |\n",
                                        encoding="utf-8")
            (p / "根切り_試.md").write_text("- 山留めあり\n| 項目 | 数量 |\n|---|---|\n| 根切り | 224.1 m³ |\n| 埋戻し | 170.7 m³ |\n",
                                         encoding="utf-8")
            (p / "構台.md").write_text("| 品名・品番・規格 | 数 | 単位・1つの重さ | 重さ計 |\n|---|---|---|---|\n"
                                     "| 覆工板 1×2m（高さ 208） | 72 | 枚（424kg） | 30528.0kg |\n", encoding="utf-8")
            (p / "敷鉄板.md").write_text("| 品名 | 数 | 注 |\n|---|---|---|\n| 厚板鋼板 NT22×5×10（1524×3048×22） | 10 | 計 8.0t |\n",
                                       encoding="utf-8")
            (p / "x_plan.json").write_text(json.dumps({"scaffold_height_mm": 10000, "edges": [{"scaffold_length": 20000}],
                                                       "elevation": {"level_heights": [1800, 3600]}}), encoding="utf-8")
            q = collect(p)
        self.assertAlmostEqual(q.hoarding_m, 19.8)
        self.assertEqual((q.house_units, q.toilet_units), (6, 4))
        self.assertEqual((q.excavation_m3, q.backfill_m3, q.retaining), (224.1, 170.7, True))
        self.assertEqual((q.deck_m2, round(q.deck_t, 2)), (144.0, 30.53))
        self.assertEqual(q.plates, 10)
        self.assertEqual((q.scaffold_m2, q.scaffold_h, q.scaffold_tiers), (200.0, 10.0, 2))
        self.assertEqual(md_rows("| a | b |\n|---|---|\n| 1 | 2 |"), [["a", "b"], ["1", "2"]])


def _plan(**kw) -> tuple[list[Task], WorkCalendar, ScheduleConditions, Quantities]:
    q = Quantities(hoarding_m=40, house_units=6, plates=10, excavation_m3=400, backfill_m3=200, retaining=True, deck_m2=144,
                   deck_t=30, scaffold_m2=1200, scaffold_h=15, form_m2=500, tower="タワークレーン 27.5t", utility=True)
    c = ScheduleConditions(start=dt.date(2027, 4, 1), floors=4, **kw)
    t = build(q, c)
    cal = WorkCalendar()
    schedule(t, cal, c.start)
    return t, cal, c, q


class TestPlan(unittest.TestCase):
    def test_sequence(self):
        t, cal, _c, _q = _plan()
        by = {x.key: x for x in t}
        self.assertLess(by["kakoi"].start, by["yama"].start)
        self.assertLess(by["yama"].end, by["ex1"].start)
        self.assertLess(by["ex1"].end, by["kodai"].start)
        self.assertLess(by["base"].end, by["frame"].start)
        self.assertLessEqual(by["tc_up"].end, by["frame"].start)       # タワークレーンは地上躯体の前に
        self.assertEqual(by["sc_up"].start, by["frame"].start)         # 足場は躯体を追う
        self.assertGreaterEqual(by["sc_up"].end, by["frame"].end)
        self.assertGreater(by["sc_dn"].start, by["facade"].end)        # 外装の後に解体
        self.assertGreaterEqual(by["kakoi_x"].start, by["house_x"].end)
        self.assertEqual(by["frame"].days, 4 * 20)
        self.assertEqual(by["sc_dn"].days, days_of(1200, scaffold_rate(15, False).per_day))
        self.assertEqual([x.group for x in display_order(t)], sorted((x.group for x in t),
                         key=lambda g: ("準備", "山留め・土工", "構台", "揚重", "躯体（参考）", "外部足場", "型枠・支保工", "外装（参考）",
                                        "片付け").index(g)))

    def test_crews_and_override(self):
        t1, *_ = _plan()
        t2, *_ = _plan(crews={"足場組立": 2, "仮囲い": 2})
        k = {x.key: x for x in t1}
        k2 = {x.key: x for x in t2}
        self.assertLess(k2["kakoi"].days, k["kakoi"].days)
        t3, *_ = _plan(override={"retaining_m": 60})
        y = next(x for x in t3 if x.key == "yama")
        self.assertEqual(y.days, days_of(60 / RATES["親杭"].pitch, RATES["親杭"].per_day))

    def test_outputs(self):
        t, cal, _c, _q = _plan()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "工程.xlsx"
            st = steps(t, cal, 4, 20, 15.0, 1.8, set(GROUP_TASKS))
            to_xlsx(t, cal, p, "仮設工事工程表 試験", ["着工 2027-04-01"], [["a", 1, "m", 1, "x", ""]], [("着工日", "2027-04-01")],
                    st)
            with zipfile.ZipFile(p) as z:
                self.assertEqual(sum(n.startswith("xl/worksheets/") for n in z.namelist()), 4)
                s1 = z.read("xl/worksheets/sheet1.xml").decode()
                self.assertIn("外部足場の組立", s1)
                self.assertIn('state="frozen"', s1)
                self.assertIn("施工ステップ", z.read("xl/worksheets/sheet3.xml").decode())
        self.assertIn("| 外部足場 | 外部足場の解体 |", to_markdown(t, "x"))


class TestSteps(unittest.TestCase):
    def test_layers_follow_the_schedule(self):
        t, cal, _c, _q = _plan()
        by = {x.key: x for x in t}
        st = steps(t, cal, 4, 20, 15.0, 1.8, set(GROUP_TASKS))
        names = [s.name for s in st]
        self.assertEqual(names[0], "準備（仮囲い・仮設建物・敷鉄板）")
        self.assertIn("地上躯体 4階", names)
        self.assertEqual(names[-1], "片付け")
        self.assertEqual([s.date for s in st], sorted(s.date for s in st))
        first = st[0].layers
        self.assertEqual((first["仮設工程_仮囲い"], first["仮設工程_外部足場"], first["仮設工程_根切り"]), ("あり", "なし", "なし"))
        f1 = next(s for s in st if s.name == "地上躯体 1階")
        self.assertEqual(f1.layers["仮設工程_構台"], "なし")             # 構台は躯体の前に撤去済み
        self.assertEqual(f1.layers["仮設工程_外部足場"], "作業中")
        self.assertTrue(0 < f1.scaffold_h < 15.0)
        top = next(s for s in st if s.name == "外装")
        self.assertEqual((top.scaffold_h, top.layers["仮設工程_外部足場"]), (15.0, "あり"))
        self.assertEqual(st[-1].layers["仮設工程_外部足場"], "なし")
        # 節目はその日の終わりの姿: 掘削の途中は作業中・終わりの日はあり・埋戻しの終わりの日はなし
        ex = by["ex1"]
        self.assertEqual(layer_state(by, "根切り.json", ex.end), "あり")
        self.assertEqual(layer_state(by, "根切り.json", by["fill"].end), "なし")
        if ex.days > 1:
            self.assertEqual(layer_state(by, "根切り.json", ex.start), "作業中")
        # 足場の組立の終わりは「あり」、解体の終わりは「なし」で高さ 0（高さ 0 を「全部見せる」と読ませない）
        up = next(s for s in st if s.name == "外部足場の組立の終わり")
        self.assertEqual((up.layers["仮設工程_外部足場"], up.scaffold_h), ("あり", 15.0))
        dn = next(s for s in st if s.name == "外部足場の解体")
        self.assertEqual((dn.layers["仮設工程_外部足場"], dn.scaffold_h), ("なし", 0.0))
        for s in st:
            if s.layers["仮設工程_外部足場"] != "なし":
                self.assertGreater(s.scaffold_h, 0, s.name)
        self.assertEqual(scaffold_height(by, by["sc_dn"].end, cal, 15.0, 1.8), 0.0)
        self.assertEqual(scaffold_height(by, by["sc_up"].start, cal, 15.0, 1.8), 1.8)    # 最初の層より低くしない


class TestSourcesFollowTheModel(unittest.TestCase):
    """帳票の拾い方の直し（2026-11-04 のループ: 実際の ashiba_out の写しで工程表を流して見つけたもの）."""

    def test_removed_parts_and_test_plans(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            # タワークレーンは消してある（控えは空・帳票は残る）→ 拾わない
            (p / "タワークレーン.md").write_text("| 名前 | 機種 |\n|---|---|\n| タワー1 | タワークレーン 27.5t |\n", encoding="utf-8")
            (p / "タワークレーン.json").write_text("{}", encoding="utf-8")
            # 試験の建物の計画（検証_）はいちばん新しくても拾わず、工事名の計画を拾う
            (p / "足場計画_plan.json").write_text(json.dumps({"scaffold_height_mm": 10000, "edges": [{"scaffold_length": 30000}]}),
                                              encoding="utf-8")
            (p / "検証_box_plan.json").write_text(json.dumps({"scaffold_height_mm": 9930, "edges": [{"scaffold_length": 12193}]}),
                                               encoding="utf-8")
            (p / "山留め足場.md").write_text("# 根切りの山留めまわり\n\n## 腹起し上の足場 W71（長さ 8800mm）\n\n"
                                         "## 腹起し上の足場 W82（長さ 5800mm）\n\n## 切梁上の足場 切梁1（長さ 6700mm）\n", encoding="utf-8")
            q = collect(p, "足場計画")
            q2 = collect(p)
        self.assertEqual(q.tower, "")
        self.assertEqual(q.scaffold_m2, 300.0)
        self.assertEqual(q2.scaffold_m2, 300.0)                    # 工事名が無くても試験の計画は除く
        self.assertAlmostEqual(q.retaining_m, 14.6)                # 腹起し上の足場だけ（切梁は数えない）
        self.assertTrue(q.retaining)

    def test_second_excavation_after_the_deck(self):
        t, *_ = _plan()
        by = {k.key: k for k in t}
        self.assertGreater(by["ex2"].end, by["kodai"].end)          # 構台から掘るので架設の終わりより後に終える
        self.assertGreater(by["ex2"].start, by["kodai"].start)

    def test_same_day_milestones_are_one_step(self):
        t, cal, _c, _q = _plan()
        by = {k.key: k for k in t}
        prep = [by[k] for k in ("kakoi", "house", "util", "plate")]
        by["yama"].end = max(k.end for k in prep)                   # 準備と山留めが同じ日に終わる
        st = steps(t, cal, 4, 20, 15.0, 1.8, set(GROUP_TASKS))
        self.assertEqual(len({s.date for s in st}), len(st))
        self.assertTrue(st[0].name.endswith("・山留め"))


class TestChecks(unittest.TestCase):
    def test_flags_what_looks_wrong(self):
        """拾った数量の点検: 足場の計画が1面だけ・仮囲いが無い（令 136条の2の20）・仮設建物が無い・山留めの延長が無い."""
        from ashiba.schedule_checks import checks

        q = Quantities(scaffold_m2=29.7, scaffold_h=8.1, scaffold_edges=1, scaffold_len=3.7, retaining=True, excavation_m3=100,
                       backfill_m3=50)
        q.sources["外部足場"] = "足場計画_plan.json"
        c = ScheduleConditions(start=dt.date(2027, 4, 1), floors=3)
        t = build(q, c)
        w = "\n".join(checks(q, t, 3))
        self.assertIn("1面・延べ 3.7m", w)
        self.assertIn("136条の2の20", w)
        self.assertIn("628条", w)
        self.assertIn("retaining_m", w)
        _t, _cal, _c, q2 = _plan()
        q2.scaffold_edges, q2.scaffold_len, q2.retaining_m = 4, 80.0, 36.0
        self.assertEqual(checks(q2, _t, 4), [])                      # そろった計画では何も言わない


class TestStepModel(unittest.TestCase):
    """工程の模型の Archicad の側（scripts/step_run.py・scripts/gdl_step.py）."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

    def test_scaffold_parts_cut_at_step_height(self):
        """外部足場の部品は stepH を持ち、3D で使う（前の版の部品は持たないので step_run は数を知らせる）."""
        from ashiba.schedule_steps import SCAFFOLD_PARTS
        hsf = Path(__file__).resolve().parents[1] / "gdl" / "hsf"
        for part in SCAFFOLD_PARTS:
            if part == "ashiba_kbrk":                    # 切梁の上の足場（山留め）。工程では山留めの控えで扱う
                continue
            self.assertIn('Name="stepH"', (hsf / part / "paramlist.xml").read_text(encoding="utf-8"), part)
            self.assertIn("stepH", (hsf / part / "scripts" / "3d.gdl").read_text(encoding="utf-8"), part)

    def test_wrap(self):
        import gdl_step
        src = "\ufeff! 見出し\n! 2行め\nblock 1, 1, 1\n"
        w = gdl_step.wrap(src)
        self.assertTrue(w.startswith("\ufeff! 見出し\n! 2行め\n" + gdl_step.MARK))
        self.assertTrue(w.endswith("block 1, 1, 1\n" + gdl_step.TAIL))
        self.assertEqual(gdl_step.wrap(w), w)            # 2回目は何もしない

    def test_clusters(self):
        """建物ごとの足場の下端: 原点が 30m 以内でつながる部品をまとめる（離れた建物は別）."""
        from step_run import clusters
        xy = {"a": (0, 0), "b": (12, 0), "c": (12, 25), "d": (-3287, -2080), "e": (-3275, -2072)}
        got = sorted(sorted(g) for g in clusters(xy))
        self.assertEqual(got, [["a", "b", "c"], ["d", "e"]])

    def test_undo_shows_layers_first(self):
        """「戻す」は仮設工程のレイヤーを見せてからレイヤーを戻す（隠したレイヤーの要素は動かせず、2026-11-05 の試験で
        9 個が黙って残った）. 戻せなかったものは控えに残す."""
        import json
        import tempfile
        from unittest import mock

        import step_run
        from ashiba.schedule_steps import LAYERS

        names = {i: n for i, n in enumerate(LAYERS, 100)}

        class Fake:
            def __init__(self):
                self.hidden = {n: True for n in LAYERS}            # ステップの途中で全部を隠した状態
                self.layer = {"G1": 100, "G2": 101, "G3": 102}     # 仮設工程のレイヤーにいる要素
                self.locked = {"G3"}                               # これだけは戻せない（固定など）

            def tapir(self, cmd, params):
                if cmd == "CreateLayers":
                    for d in params["layerDataArray"]:
                        self.hidden[d["name"]] = d["isHidden"]
                    return {}
                if cmd == "SetDetailsOfElements":
                    res = []
                    for d in params["elementsWithDetails"]:
                        g = d["elementId"]["guid"]
                        ok = g not in self.locked and not self.hidden.get(names.get(self.layer[g]), False)
                        if ok:
                            self.layer[g] = d["details"]["layerIndex"]
                        res.append({"success": ok})
                    return {"executionResults": res}
                if cmd == "GetElementsByType":
                    return {"elements": []}
                if cmd == "GetStories":
                    return {"stories": []}
                raise AssertionError(cmd)

            def get_details(self, els):
                return [{"layerIndex": self.layer.get(e["elementId"]["guid"], 0)} for e in els]

        fake = Fake()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / step_run.STEPS).write_text(json.dumps({"steps": []}), encoding="utf-8")
            (out / step_run.MODEL).write_text(json.dumps({"step": 3, "elements": {
                g: {"layer": 1, "group": names[fake.layer[g]]} for g in fake.layer}}), encoding="utf-8")
            with mock.patch("ashiba.tapir_adapter.ArchicadClient", return_value=fake), mock.patch("builtins.print"):
                code = step_run.main(["--undo", "--out", d])
            left = json.loads((out / step_run.MODEL).read_text(encoding="utf-8"))
        self.assertEqual((fake.layer["G1"], fake.layer["G2"]), (1, 1))
        self.assertEqual(code, 2)
        self.assertEqual(list(left["elements"]), ["G3"])
        self.assertFalse(any(fake.hidden.values()))


if __name__ == "__main__":
    unittest.main()
