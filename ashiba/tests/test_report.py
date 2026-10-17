"""割付レポート（人が読む成果物）の内容テスト."""

import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.law_check import run_all_checks
from ashiba.master import load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.quantity import take_off
from ashiba.report import write_plan_json, write_quantity_csv, write_report_md
from ashiba.stairs import auto_place_stairs

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build():
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(16300, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev, config=ScaffoldConfig(),
        building_height_mm=16000,
    )


def build_frame():
    master = load_master("waku")
    plan = solve_plan(RECT, master)
    elev = solve_elevation(16300, master=master)
    return ScaffoldModel(
        master=master, plan=plan, elevation=elev, config=ScaffoldConfig(),
        building_height_mm=16000,
    )


def render(model, stair_plan=None, **kw) -> str:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "r.md"
        write_report_md(
            model, take_off(model), run_all_checks(model), path,
            "テスト", stair_plan=stair_plan, **kw,
        )
        return path.read_text(encoding="utf-8")


class TestReport(unittest.TestCase):
    def test_stairs_section_lists_every_tower(self):
        m = build()
        plan = auto_place_stairs(m, count=3)
        text = render(m, plan)
        self.assertIn("## 昇降設備（階段室）", text)
        for t in plan.towers:
            self.assertIn(f"| {t.edge_index} | {t.start_mm:.0f}mm |", text)

    def test_extra_stairs_beyond_requirement_are_flagged(self):
        """必要数を超える箇所数は費用に効くので、そうと分かるようにする."""
        m = build()
        plan = auto_place_stairs(m, min_per_face=1)
        self.assertGreater(plan.count, plan.required_count)
        self.assertIn(f"{plan.required_count}箇所で足ります", render(m, plan))

    def test_section_is_omitted_without_stairs(self):
        self.assertNotIn("## 昇降設備", render(build()))

    def test_bracket_section_detail_is_shown(self):
        """ブラケット区間は「1箇所」だけでなく、面・範囲・向き・幅を出す."""
        from ashiba.brackets import BracketSection

        m = build()
        secs = [BracketSection(edge_index=0, start_mm=3600, end_mm=9000,
                               direction="張出", width=600, deck_width=500,
                               levels=[2])]
        text = render(m, bracket_sections=secs)
        line = next(l for l in text.splitlines() if l.startswith("- ブラケット区間:"))
        self.assertIn("3600〜9000mm", line)
        self.assertIn("張出", line)
        self.assertIn("ブラケット600", line)
        self.assertIn("床幅500", line)
        self.assertIn("第2層", line)

    def test_hoist_detail_is_shown(self):
        """昇降機は「1基」だけでなく、位置・到達高さ・乗り込み口の層を出す."""
        from ashiba.platforms import Hoist, validate_platforms

        m = build()
        pf = validate_platforms(m, [], [Hoist(
            edge_index=0, position_mm=9000, landing_levels=[2, 4])])
        text = render(m, platforms=pf)
        line = next(l for l in text.splitlines() if l.startswith("- 昇降機:"))
        self.assertIn("9000mm", line)
        self.assertIn("到達高さ", line)
        self.assertIn("第2・4層", line)
        self.assertIn("開閉式手すり", line)

    def test_disclaimer_is_always_present(self):
        """有資格者確認前提の下書きである旨（指示書9）を落とさない."""
        self.assertIn("計画作成参画者（有資格者）が確認する前提の下書き", render(build()))


class TestQuantityCsvCategorySubtotals(unittest.TestCase):
    """数量CSVの分類別集計が、型番別明細の合計と一致すること."""

    def _csv(self, model):
        import csv
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "q.csv"
            write_quantity_csv(take_off(model), path)
            return list(csv.reader(path.open(encoding="utf-8-sig")))

    def test_subtotals_match_the_line_items(self):
        m = build()
        q = take_off(m)
        rows = self._csv(m)
        # 分類別集計ブロックを読む
        i = next(k for k, r in enumerate(rows) if r and r[0] == "■分類別集計")
        sub = {}
        for r in rows[i + 1:]:
            if not r or r[0].startswith("総重量"):
                break
            if len(r) >= 3 and r[1] and r[2]:
                sub[r[0]] = (int(r[1]), float(r[2]))
        # 明細から分類別に集計して照合
        want = {}
        for l in q.lines:
            c = l.part.category
            pq, pw = want.get(c, (0, 0.0))
            want[c] = (pq + l.qty, pw + l.subtotal_weight)
        for c, (wq, ww) in want.items():
            self.assertIn(c, sub)
            self.assertEqual(sub[c][0], wq, c)
            self.assertAlmostEqual(sub[c][1], round(ww, 1), places=1)

    def test_report_md_has_category_table(self):
        """割付レポートにも分類別の規模感（分類テーブル）を出す."""
        text = render(build())
        self.assertIn("| 分類 | 数量計 | 重量計kg |", text)
        # 分類テーブルの合計重量は総重量に一致
        import re
        m = re.search(r"総重量: ([\d.]+)kg", text)
        grand = float(m.group(1))
        rows = re.findall(r"^\| (\S+) \| (\d+) \| ([\d.]+) \|$", text, re.M)
        # 分類テーブルの行だけ（数量計・重量計のヘッダを除く）
        wt = sum(float(w) for _c, _q, w in rows if _c not in ("分類",))
        self.assertAlmostEqual(wt, grand, delta=0.2)

    def test_subtotal_weights_sum_to_grand_total(self):
        rows = self._csv(build())
        i = next(k for k, r in enumerate(rows) if r and r[0] == "■分類別集計")
        total = 0.0
        for r in rows[i + 1:]:
            if not r or r[0].startswith("総重量"):
                break
            if len(r) >= 3 and r[2]:
                total += float(r[2])
        grand = next(float(r[1]) for r in rows if r and r[0] == "総重量kg")
        self.assertAlmostEqual(total, grand, places=1)


class TestFrameReportUsesFrameTerms(unittest.TestCase):
    """枠組の割付レポートはくさび用語（支柱・布材手すり）を出さない."""

    def test_frame_calls_verticals_kenwaku(self):
        text = render(build_frame())
        self.assertIn("建枠構成（下から）", text)
        self.assertIn("建枠位置数", text)
        self.assertNotIn("支柱構成", text)
        self.assertNotIn("支柱位置数", text)

    def test_frame_guard_rail_is_the_frame_itself(self):
        text = render(build_frame())
        self.assertIn("手すり方式: 建枠一体", text)

    def test_deck_config_line_is_shown(self):
        """作業床の幅構成と建地列間隔を計画サマリに出す（レビューできるように）."""
        text = render(build())
        self.assertIn("- 作業床: 踏板 400＋250 ＝ 幅650mm", text)
        self.assertIn("支柱列間隔 600mm", text)

    def test_next_gen_deck_is_labelled(self):
        m = build()
        m.config.next_gen = True
        m.config.deck_widths = None
        m.config.deck_widths = m.master.default_deck_widths(True)
        text = render(m)
        self.assertIn("次世代足場", text)
        self.assertIn("幅750mm", text)

    def test_frame_deck_config_uses_frame_terms(self):
        text = render(build_frame())
        self.assertIn("- 作業床: 布板", text)
        self.assertIn("建枠列間隔", text)

    def test_no_shichu_leaks_into_frame_report(self):
        """枠組の割付レポート全文に「支柱」（建枠と併記でない）が残らない."""
        # 斜面＋開口＋ステージ＋ブラケットを載せて全節を出す
        from ashiba.brackets import BracketSection
        from ashiba.openings import Opening, validate_openings
        from ashiba.terrain import GroundModel, solve_post_feet

        m = build_frame()
        ground = GroundModel(points=[(x, y, -x * 0.02)
                                     for x in (0, 15000, 30000) for y in (0, 20000)])
        terrain = solve_post_feet(m, ground)
        op = validate_openings(m, [Opening(0, 1829, 3658, level=2)])
        secs = [BracketSection(edge_index=1, start_mm=0, end_mm=3658,
                               direction="張出", width=600)]
        text = render(m, terrain=terrain, openings=op, bracket_sections=secs)
        offenders = [ln for ln in text.splitlines()
                     if "支柱" in ln and "建枠" not in ln]
        self.assertEqual(offenders, [], offenders)

    def test_wedge_still_uses_shichu_and_ledger(self):
        text = render(build())
        self.assertIn("支柱構成（下から）", text)
        self.assertIn("支柱位置数", text)
        self.assertIn("手すり方式: 布材", text)


class TestReportCoversTheWholePlan(unittest.TestCase):
    """計画の可否を左右する数字が本文に出ること.

    構造計算の検定比・壁つなぎ・敷地の高低差は、以前は plan.json と
    設置届Excelにしかなく、人が読む割付レポートには無かった。
    """

    def setUp(self):
        self.m = build()

    def test_wall_tie_section_always_present(self):
        text = render(self.m)
        self.assertIn("## 壁つなぎ", text)
        self.assertIn(f"本数: {len(self.m.wall_ties)}箇所", text)

    def test_structural_ratios_are_shown(self):
        from ashiba.structural import SiteCondition, run_structural

        res = run_structural(self.m, take_off(self.m), SiteCondition())
        text = render(self.m, structural=res)
        self.assertIn("## 構造計算", text)
        self.assertIn(str(res.wall_tie.ratio), text)
        self.assertIn(str(res.post.ratio), text)

    def test_structural_warnings_are_shown(self):
        from ashiba.structural import SiteCondition, run_structural

        res = run_structural(self.m, take_off(self.m), SiteCondition())
        text = render(self.m, structural=res)
        for w in res.warnings:
            self.assertIn(w, text)

    def test_terrain_section_only_when_sloped(self):
        from ashiba.terrain import GroundModel, solve_post_feet

        flat = solve_post_feet(self.m, GroundModel())
        self.assertNotIn("## 敷地の高低差", render(self.m, terrain=flat))
        slope = solve_post_feet(self.m, GroundModel(points=[
            (0, 0, 0), (30000, 0, 400), (30000, 20000, 1200), (0, 20000, 800),
        ]))
        text = render(self.m, terrain=slope)
        self.assertIn("## 敷地の高低差", text)
        self.assertIn("脚部構成", text)

    def test_extras_section_only_when_present(self):
        from ashiba.platforms import LoadingStage, validate_platforms

        self.assertNotIn("## 付帯設備", render(self.m))
        pf = validate_platforms(self.m, [LoadingStage(
            edge_index=0, start_mm=12600, span_count=2, levels=[3])])
        text = render(self.m, platforms=pf)
        self.assertIn("## 付帯設備", text)
        self.assertIn("荷受けステージ 1基", text)


class TestPlanJsonIsSelfSufficient(unittest.TestCase):
    """「配置用」と謳う以上、これだけで再配置できること."""

    def _json(self, **kw):
        import json

        from ashiba.report import write_plan_json

        m = build()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.json"
            write_plan_json(m, path, **kw)
            return m, json.loads(path.read_text(encoding="utf-8"))

    def test_every_edge_carries_placement_and_gdl_params(self):
        from ashiba.gdl_params import line_params

        m, d = self._json()
        self.assertEqual(len(d["edges"]), len(m.plan.edges))
        for ep, e in zip(m.plan.edges, d["edges"]):
            self.assertEqual(e["gdl_params"], line_params(m, ep))
            self.assertAlmostEqual(e["placement"]["x_mm"], ep.start_post[0])

    def test_config_is_recorded(self):
        m, d = self._json()
        self.assertEqual(d["config"]["post_row_spacing_mm"], m.post_row_spacing_mm)
        self.assertEqual(d["config"]["scaffold_form"], m.config.scaffold_form)

    def test_optional_sections_appear_only_when_given(self):
        from ashiba.stairs import auto_place_stairs

        _m, plain = self._json()
        self.assertNotIn("stairs", plain)
        m, with_stairs = self._json(stair_plan=auto_place_stairs(build()))
        self.assertIn("stairs", with_stairs)
        self.assertEqual(
            len(with_stairs["stairs"]["towers"]), with_stairs["stairs"]["count"]
        )


class TestWarningsAreSeparatedFromNotes(unittest.TestCase):
    """対応が要るものと、何をどう解いたかの説明を混ぜない."""

    def setUp(self):
        from ashiba.structural import SiteCondition, run_structural
        from ashiba.terrain import GroundModel, solve_post_feet

        self.m = build()
        self.terrain = solve_post_feet(self.m, GroundModel(points=[
            (0, 0, 0), (30000, 0, 400), (30000, 20000, 1200), (0, 20000, 800),
        ]))
        self.res = run_structural(
            self.m, take_off(self.m), SiteCondition(), terrain=self.terrain
        )

    def test_condition_explanation_is_a_note_not_a_warning(self):
        """どのジャッキ量で検定したかは説明であって是正項目ではない."""
        self.assertTrue(
            any("最大繰出し" in n for n in self.res.notes), self.res.notes
        )
        self.assertFalse(any("最大繰出し" in w for w in self.res.warnings))

    def test_unverified_capacity_stays_a_warning(self):
        """未確認の耐力値は提出前に必ず解消するので警告のまま."""
        self.assertTrue(
            any("未確認の耐力値" in w for w in self.res.warnings), self.res.warnings
        )

    def test_terrain_absorption_is_a_note_and_over_limit_is_a_warning(self):
        self.assertTrue(
            any("吸収しました" in n for n in self.terrain.notes), self.terrain.notes
        )
        self.assertFalse(any("吸収しました" in w for w in self.terrain.warnings))
        self.assertTrue(
            any("実務上限" in w for w in self.terrain.warnings), self.terrain.warnings
        )

    def test_report_marks_them_differently(self):
        text = render(self.m, structural=self.res, terrain=self.terrain)
        for n in self.res.notes:
            self.assertIn(f"ℹ️ {n}", text)
        for w in self.res.warnings:
            self.assertIn(f"⚠️ {w}", text)


class TestReadmeMatchesTheCode(unittest.TestCase):
    """READMEの機械的に確かめられる記述が実装とズレないこと.

    数値やファイル名は実装が動くたびに古くなる。読む人はREADMEを信じて
    手を動かすので、ズレはそのまま「動かない手順」になる。
    """

    README = Path(__file__).resolve().parents[1] / "README.md"

    def _text(self) -> str:
        return self.README.read_text(encoding="utf-8")

    def test_referenced_paths_exist(self):
        import re

        root = self.README.parent
        paths = set(re.findall(
            r'`((?:src|scripts|gdl|data|examples|tests)/[^`\s]+)`', self._text()))
        missing = [p for p in sorted(paths) if "*" not in p
                   and not (root / p).exists()]
        self.assertEqual(missing, [])

    def test_test_count_is_current(self):
        import re
        import unittest as ut

        def count(suite):
            return sum(count(x) if isinstance(x, ut.TestSuite) else 1
                       for x in suite)

        n = count(ut.TestLoader().discover(str(self.README.parent / "tests")))
        claimed = int(re.search(r"ユニットテスト(\d+)本", self._text()).group(1))
        self.assertEqual(claimed, n, "READMEのテスト本数を更新してください")

    def test_examples_are_all_listed(self):
        import re

        ex = {p.name for p in (self.README.parent / "examples").glob("*.json")}
        listed = set(re.findall(r'\| `([a-z_0-9]+\.json)` \|', self._text()))
        self.assertEqual(ex, listed)

    def test_law_check_count(self):
        import re

        from ashiba.law_check import run_all_checks

        n = len(run_all_checks(build()))
        for claimed in re.findall(r"法規チェック(?:\s*\|\s*)?(\d+)項目", self._text()):
            self.assertEqual(int(claimed), n)


class TestPlanJsonSchemaIsDocumented(unittest.TestCase):
    """出力スキーマの説明と実際の出力が食い違わないこと.

    plan.json は他ツールが読む前提の機械可読データなので、
    説明に無いキーが出たり、説明にあるキーが出なかったりすると使えない。
    """

    def _doc_keys(self) -> set:
        import re

        src = (Path(__file__).resolve().parents[1] / "src" / "ashiba"
               / "report.py").read_text(encoding="utf-8")
        schema = src.split("出力スキーマ")[1].split('"""')[0]
        return set(re.findall(r'"([a-z_0-9]+)":', schema))

    def _actual_keys(self) -> set:
        import json
        import tempfile

        from ashiba.brackets import BracketSection
        from ashiba.openings import Opening, validate_openings
        from ashiba.platforms import LoadingStage, validate_platforms
        from ashiba.stairs import auto_place_stairs
        from ashiba.terrain import GroundModel, solve_post_feet

        # 浅い凹みを付けて「渡した区間」も出す（文書化したキーは全部実在させる）
        master = load_master("shinwa_A")
        notch = [(0, 0), (12000, 0), (12000, 300), (15600, 300), (15600, 0),
                 (30000, 0), (30000, 20000), (0, 20000)]
        m = ScaffoldModel(
            master=master, plan=solve_plan(notch, master),
            elevation=solve_elevation(16300, master=master), config=ScaffoldConfig(),
            building_height_mm=16000,
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plan.json"
            write_plan_json(
                m, path, stair_plan=auto_place_stairs(m),
                terrain=solve_post_feet(m, GroundModel(points=[])),
                platforms=validate_platforms(m, [LoadingStage(
                    edge_index=0, start_mm=3600, span_count=2, levels=[3])]),
                openings=validate_openings(m, [Opening(0, 7200, 3600, level=2)]),
                bracket_sections=[BracketSection(
                    edge_index=1, start_mm=0, end_mm=3600, width=300)],
            )
            data = json.loads(path.read_text(encoding="utf-8"))
        keys = set(data)
        for section in ("config", "elevation", "stairs", "platforms", "terrain"):
            keys |= set(data.get(section, {}))
        for section in ("openings", "bracket_sections", "bridged_zones"):
            for item in data.get(section, []):
                keys |= set(item)
        keys |= set(data["edges"][0])
        keys |= set(data["edges"][0]["placement"])
        keys |= set(data["wall_ties"][0])
        return keys

    def test_every_output_key_is_documented(self):
        undocumented = self._actual_keys() - self._doc_keys()
        self.assertEqual(sorted(undocumented), [])

    def test_documented_keys_exist(self):
        # gdl_params の中身は gdl_params.py 側で担保しているので除く
        missing = self._doc_keys() - self._actual_keys() - {"gdl_params"}
        self.assertEqual(sorted(missing), [])


class TestNoDoubleReading(unittest.TestCase):
    """同じ長文を1つのレポート内で二度読ませない."""

    def _render(self):
        import tempfile

        from ashiba.cli import build_verdict, collect_warnings
        from ashiba.openings import validate_openings
        from ashiba.platforms import LoadingStage, validate_platforms
        from ashiba.stairs import auto_place_stairs
        from ashiba.structural import run_structural
        from ashiba.terrain import GroundModel, solve_post_feet

        m = build()
        stair = auto_place_stairs(m)
        pf = validate_platforms(m, [LoadingStage(
            edge_index=0, start_mm=3600, span_count=2,
            projection_mm=1500, load_kn=9.8, levels=[3])])
        op = validate_openings(m)
        terrain = solve_post_feet(m, GroundModel(points=[]))
        checks = run_all_checks(m, stair_plan=stair, terrain=terrain)
        q = take_off(m, platforms=pf, stair_plan=stair)
        st = run_structural(m, q, platforms=pf, terrain=terrain)
        warnings = collect_warnings(
            st, m, [], stair, [], op, terrain, pf, checks, q)
        verdict = build_verdict(
            {"ok": 0, "warn": 0, "ng": 0}, st, pf, op, [], warnings)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.md"
            write_report_md(
                m, q, checks, path, "テスト", stair_plan=stair, verdict=verdict,
                structural=st, terrain=terrain, platforms=pf, openings=op,
                warnings=warnings,
            )
            return path.read_text(encoding="utf-8"), q

    def test_quantity_section_points_at_the_checklist(self):
        text, q = self._render()
        self.assertIn("末尾の要確認一覧を参照", text)
        # 長文が数量サマリと一覧の両方に全文で出ていない
        for w in q.warnings:
            self.assertLessEqual(text.count(w), 1, w[:40])

    def test_structural_warning_is_shortened(self):
        text, _q = self._render()
        head = "未確認の耐力値が計算に使われています"
        self.assertIn(f"{head}…（要確認一覧を参照）", text)


class TestOrderableNotesStandOut(unittest.TestCase):
    """発注書として使うCSVで、手配が要る項目が注記に埋もれないこと."""

    def setUp(self):
        from ashiba.platforms import LoadingStage, validate_platforms

        self.m = build()
        pf = validate_platforms(self.m, [LoadingStage(
            edge_index=0, start_mm=3600, span_count=2,
            projection_mm=1500, load_kn=9.8, levels=[3])])
        self.q = take_off(self.m, platforms=pf)

    def test_csv_labels_them_differently(self):
        import tempfile

        self.assertTrue(self.q.warnings)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "q.csv"
            write_quantity_csv(self.q, path)
            text = path.read_text(encoding="utf-8-sig")
        for w in self.q.warnings:
            self.assertIn(f"要手配・要検討,{w}", text)
        # 同じ行が注記としても出ない（二重に見える）
        self.assertEqual(text.count(self.q.warnings[0]), 1)

    def test_report_marks_them_too(self):
        import tempfile

        from ashiba.law_check import run_all_checks

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "r.md"
            write_report_md(self.m, self.q, run_all_checks(self.m), path, "x")
            text = path.read_text(encoding="utf-8")
        self.assertIn("**要手配・要検討**", text)


class TestPlanTableListsWhatSitsOnEachFace(unittest.TestCase):
    """平面割付表に「面に載るもの」列（壁つなぎ本数・階段・梁枠・ステージ・昇降機・渡し）."""

    def _table(self, example):
        import tempfile

        from ashiba.cli import load_spec, solve_all, write_outputs

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / example))
        with tempfile.TemporaryDirectory() as d:
            write_outputs(r, Path(d))
            md = next(Path(d).glob("*_割付レポート.md")).read_text(encoding="utf-8")
        rows = [ln for ln in md.splitlines() if ln.startswith("| ") and ln.count("|") >= 9]
        header = next(ln for ln in md.splitlines() if ln.startswith("| 辺 | 面 |"))
        self.assertIn("面に載るもの", header)
        return {int(ln.split("|")[1]): ln.split("|")[7].strip() for ln in rows if ln.split("|")[1].strip().isdigit()}

    def test_opening_and_stage_examples(self):
        cells = self._table("opening_beam.json")
        self.assertIn("梁枠1", cells[0])
        self.assertIn("梁枠1", cells[2])
        self.assertTrue(cells[0].startswith("壁つなぎ"))
        cells = self._table("loading_stage.json")
        self.assertIn("ステージ1", cells[0])
        self.assertIn("昇降機1", cells[2])
        cells = self._table("diagonal_corner.json")
        self.assertIn("渡し1（斜辺）", cells[1])
        self.assertIn("渡し1（斜辺）", cells[2])


class TestNgReasonsAreWrittenOut(unittest.TestCase):
    """NG の理由の本文がレポートと届の要確認事項に出る（件数だけでは直せない）."""

    def test_widening_ratio_ng_text_reaches_both_outputs(self):
        import re
        import tempfile
        import zipfile

        from ashiba.cli import solve_all, write_outputs

        spec = {"project_name": "拡幅NG", "series_id": "nikken_nd1800",
                "outline_mm": [[0, 0], [30000, 0], [30000, 20000], [0, 20000]],
                "eaves_height_mm": 16000, "building_height_mm": 16000, "guard_extra_mm": 300, "period_days": 90,
                "bracket_sections": [{"edge_index": 0, "start_mm": 0, "end_mm": 7316, "width": 610,
                                      "direction": "張出", "levels": [2, 3], "has_hozue": True, "is_widening": True}]}
        r = solve_all(spec)
        self.assertIn("ブラケット区間NG 1件", r.verdict["blockers"])
        with tempfile.TemporaryDirectory() as d:
            write_outputs(r, Path(d))
            md = next(Path(d).glob("*_割付レポート.md")).read_text(encoding="utf-8")
            z = zipfile.ZipFile(next(Path(d).glob("*_設置届一式.xlsx")))
            sheet2 = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
        self.assertIn("是正: ブラケット区間: ", md)
        self.assertIn("60%", md.split("## ")[0])          # 冒頭の判定ブロックに理由がある
        self.assertTrue(re.search(r"<t[^>]*>ブラケット区間: [^<]*60%", sheet2))


if __name__ == "__main__":
    unittest.main()



class TestPlanJsonHasOutline(unittest.TestCase):
    def test_outline_is_written_for_read_back_apply(self):
        import json
        import tempfile
        from pathlib import Path as P

        from ashiba.cli import solve_all
        from ashiba.report import write_plan_json

        r = solve_all({"project_name": "外形", "series_id": "shinwa_A",
                       "outline_mm": [[0, 0], [10800, 0], [10800, 5400], [0, 5400]],
                       "eaves_height_mm": 9000, "building_height_mm": 9000})
        with tempfile.TemporaryDirectory() as d:
            p = P(d) / "x_plan.json"
            write_plan_json(r.model, p, stair_plan=r.stair_plan, openings=r.openings, platforms=r.platforms,
                            bracket_sections=r.brackets, terrain=r.terrain)
            data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["outline_mm"], [[0, 0], [10800, 0], [10800, 5400], [0, 5400]])
