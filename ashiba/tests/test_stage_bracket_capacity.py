"""荷受けステージの受けブラケットは、出だけでなく許容荷重でも検定する.

出で選ぶだけだと、枠組の伸縮ブラケット（TWL1000・許容1.96kN）に1tのステージを
受けさせても通っていた。マスタの note の許容荷重で1本あたりの荷重を検定し、
書いていない部材は要確認に回す。
"""

import unittest

from _path import SRC  # noqa: F401

from ashiba.elevation_solver import solve_elevation
from ashiba.master import Part, load_master
from ashiba.model import ScaffoldConfig, ScaffoldModel
from ashiba.plan_solver import solve_plan
from ashiba.platforms import LoadingStage, bracket_allowable_kn, validate_platforms

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def build(series):
    master = load_master(series)
    return ScaffoldModel(master=master, plan=solve_plan(RECT, master),
                         elevation=solve_elevation(16300, master=master),
                         config=ScaffoldConfig(), building_height_mm=16000)


def stage(**kw):
    base = dict(edge_index=0, start_mm=5400, span_count=2, levels=[3])
    base.update(kw)
    return LoadingStage(**base)


class TestBracketAllowable(unittest.TestCase):
    def test_parses_both_wordings(self):
        a = Part("x", "ブラケット", "A", 1524, 1524, 0, 20.0, "張出用 荷取りブラケット 許容支持力6.86kN/枚かつ6.86kN/スパン")
        b = Part("x", "ブラケット", "B", 1000, 1000, 0, 6.45, "張出用 伸縮ブラケット750〜1000 許容荷重1.96kN")
        c = Part("x", "ブラケット", "C", 600, 600, 0, 3.3, "張出用")
        self.assertEqual(bracket_allowable_kn(a), 6.86)
        self.assertEqual(bracket_allowable_kn(b), 1.96)
        self.assertIsNone(bracket_allowable_kn(c))


class TestStageBracketCheck(unittest.TestCase):
    def test_nd1800_default_stage_fits_the_loading_bracket(self):
        """1t÷3本＝3.27kN ≦ 荷取りブラケット NDBS15 の 6.86kN."""
        m = build("nikken_nd1800")
        r = validate_platforms(m, [stage(projection_mm=1500)])
        self.assertFalse([i for i in r.issues if "受けブラケット" in i.message], [i.message for i in r.issues])

    def test_nd1800_overload_is_ng(self):
        """1スパン（2本）で 20kN → 10kN/本 > 6.86kN."""
        m = build("nikken_nd1800")
        r = validate_platforms(m, [stage(projection_mm=1500, span_count=1, load_kn=20.0)])
        ng = [i for i in r.issues if i.severity == "NG" and "受けブラケット" in i.message]
        self.assertTrue(ng, [i.message for i in r.issues])
        self.assertIn("NDBS15", ng[0].message)
        self.assertIn("6.86", ng[0].message)
        self.assertIn("10.00kN", ng[0].message)

    def test_frame_adjustable_bracket_cannot_carry_a_stage(self):
        """枠組の TWL1000（許容1.96kN）に出900のステージ1tは載せられない."""
        m = build("waku")
        r = validate_platforms(m, [stage(projection_mm=900)])
        ng = [i for i in r.issues if i.severity == "NG" and "TWL1000" in i.message]
        self.assertTrue(ng, [i.message for i in r.issues])
        self.assertIn("1.96", ng[0].message)

    def test_bracket_without_a_rating_is_flagged_for_confirmation(self):
        """信和の張出ブラケット（許容荷重の記載なし）は要確認（WARN）で通す."""
        m = build("shinwa_A")
        r = validate_platforms(m, [stage(projection_mm=600)])
        warn = [i for i in r.issues if i.severity == "WARN" and "許容荷重がマスタに無く" in i.message]
        self.assertTrue(warn, [i.message for i in r.issues])
        self.assertFalse([i for i in r.issues if i.severity == "NG" and "受けブラケット" in i.message])


class TestUpliftWordingDoesNotContradictTheHozue(unittest.TestCase):
    """方杖付きのステージに「方杖を付けろ」と言わない.

    引抜きはてこモデル（方杖の効果を見込まない）で出しているので、方杖が既に
    ある計画には「安全側の値・有資格者確認」と言う。
    """

    def test_warning_and_sheets(self):
        import tempfile
        import zipfile
        from pathlib import Path

        from ashiba.cli import load_spec, solve_all
        from ashiba.notification import write_notification_xlsx

        root = Path(__file__).resolve().parents[1]
        r = solve_all(load_spec(root / "examples" / "combo_nd1800.json"))
        self.assertTrue(all(s.has_hozue for s in r.platforms.stages))
        w = [x for x in r.structural.warnings if "引抜き" in x]
        self.assertTrue(w, r.structural.warnings)
        self.assertIn("方杖の効果を見込まない", w[0])
        self.assertNotIn("方杖で外側建地へ流す構成にし", w[0])
        with tempfile.TemporaryDirectory() as d:
            xl = Path(d) / "n.xlsx"
            write_notification_xlsx(r.model, r.quantity, r.checks, r.structural, xl, "t")
            import re

            z = zipfile.ZipFile(xl)
            names = re.findall(r'name="([^"]+)"', z.read("xl/workbook.xml").decode())
            calc3 = z.read(f"xl/worksheets/sheet{names.index('計算書3_建地圧縮') + 1}.xml").decode()
            row = next(m.group(1) for m in re.finditer(r"<row[^>]*>(.*?)</row>", calc3, re.S)
                       if "引抜きの判定" in m.group(1))
            self.assertIn("要確認", row)
            self.assertNotIn(">NG<", row)


if __name__ == "__main__":
    unittest.main()
