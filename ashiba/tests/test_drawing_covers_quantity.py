"""数量に出る部材は図面にも出す、という不変条件のテスト.

この方針を決めるまでに、朝顔・階段室・壁つなぎ・梁枠・荷受けステージ・
ブラケット区間の6件が「数量表や法規チェックには出るのに図面には現れない」
状態だった。原因はいずれも平面と立面でGDLパラメータを別々に組み立てて
いたことで、片方だけ渡し漏れていた。line_params への集約後も、新しい
部材を足したときに同じことが起きないようここで止める。
"""

import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba.brackets import BracketSection
from ashiba.elevation_solver import solve_elevation
from ashiba.gdl_params import line_params
from ashiba.master import load_master
from ashiba.model import AsagaoSpec, ScaffoldConfig, ScaffoldModel
from ashiba.openings import Opening, validate_openings
from ashiba.plan_solver import solve_plan
from ashiba.platforms import LoadingStage, validate_platforms
from ashiba.quantity import take_off
from ashiba.stairs import auto_place_stairs

RECT = [(0, 0), (30000, 0), (30000, 20000), (0, 20000)]


def full_model():
    """付帯設備をひととおり載せたモデル."""
    master = load_master("shinwa_A")
    plan = solve_plan(RECT, master)
    return ScaffoldModel(
        master=master, plan=plan,
        elevation=solve_elevation(16300, master=master),
        config=ScaffoldConfig(asagao=AsagaoSpec(stages=1)),
        building_height_mm=16000,
    )


class TestDrawingCoversQuantity(unittest.TestCase):
    def setUp(self):
        self.m = full_model()
        self.stairs = auto_place_stairs(self.m)
        self.openings = validate_openings(self.m, [Opening(0, 3600, 3600)])
        self.platforms = validate_platforms(self.m, [LoadingStage(
            edge_index=0, start_mm=12600, span_count=2, levels=[3])])
        self.brackets = [BracketSection(
            edge_index=0, start_mm=0, end_mm=5400, width=300, levels=[1])]
        self.params = [
            line_params(
                self.m, ep, stair_plan=self.stairs, openings=self.openings,
                platforms=self.platforms, bracket_sections=self.brackets,
            )
            for ep in self.m.plan.edges
        ]

    def _any(self, key):
        return any(p[key] for p in self.params)

    def test_every_optional_feature_reaches_the_drawing(self):
        for key, what in (
            ("stairList", "階段室"),
            ("asagaoList", "朝顔"),
            ("tieList", "壁つなぎ"),
            ("beamList", "梁枠"),
            ("stageList", "荷受けステージ"),
            ("brktList", "ブラケット区間"),
        ):
            with self.subTest(what):
                self.assertTrue(self._any(key), f"{what}が図面パラメータに出ていない")

    def test_quantity_has_the_same_features(self):
        """図面に出したものが数量表にも出ていること（逆向きの確認）."""
        q = take_off(
            self.m, stair_plan=self.stairs, platforms=self.platforms,
            openings=self.openings, bracket_sections=self.brackets,
        )
        self.assertGreater(q.qty_of("階段"), 0)
        self.assertGreater(q.qty_of("朝顔"), 0)
        self.assertGreater(q.qty_of("壁つなぎ"), 0)
        self.assertGreater(q.qty_of("梁枠"), 0)

    def test_geometry_params_are_never_zero(self):
        """既定値のまま描かれると系列違いに気づけない."""
        for p in self.params:
            for key in ("rowW", "deckW1", "railH", "midH", "floorH"):
                self.assertGreater(p[key], 0, key)
            self.assertTrue(p["levelList"], "作業床高さが空")
            self.assertTrue(p["postList"], "支柱構成が空")

    def test_no_feature_leaks_to_other_edges(self):
        """辺ごとのリストは、その辺のぶんだけ."""
        own = self.params[0]
        others = self.params[1:]
        for key in ("beamList", "stageList", "brktList"):
            with self.subTest(key):
                self.assertTrue(own[key])
                self.assertEqual([p[key] for p in others], ["", "", ""])


class TestEveryGdlParamIsWired(unittest.TestCase):
    """GDLにパラメータを足したのにPythonから渡し忘れる、を止める.

    「コードはあるのにデータが来ない」で描かれなかった部材が6件あった。
    表示切替と立面専用を除く全パラメータは line_params が渡すこと。
    """

    # 立面図の配置でだけ設定するもの／GDL既定で足りる表示切替
    VIEW_ONLY = {"viewMode", "faceName", "flList"}
    DISPLAY_ONLY = {"showBrace", "showDeck", "showDim", "texSiz", "warnPen"}
    # 部品の1Dスクリプトが図示本数を計算して書き戻す出力専用（Python からは渡さない）
    OUTPUT_ONLY = {"qtyPostPos", "qtyPost", "qtyNuno", "qtyDeck", "qtyToe", "qtyAdv", "qtyTie", "qtyBrace", "qtyStair"}

    def test_no_unwired_parameter(self):
        import xml.etree.ElementTree as ET
        from pathlib import Path as P

        root = ET.parse(
            P(__file__).resolve().parents[1]
            / "gdl" / "hsf" / "ashiba_line" / "paramlist.xml"
        ).getroot()
        declared = {
            e.get("Name") for e in root.find("Parameters") if e.find("Fix") is None
        }
        m = full_model()
        sent = set(line_params(m, m.plan.edges[0]))
        unwired = declared - sent - self.VIEW_ONLY - self.DISPLAY_ONLY - self.OUTPUT_ONLY
        self.assertEqual(
            unwired, set(),
            f"GDLにあるのに line_params が渡していない: {sorted(unwired)}",
        )

    def test_no_parameter_that_gdl_does_not_know(self):
        """存在しないパラメータを送ると、その要素の全パラメータが無視される."""
        import xml.etree.ElementTree as ET
        from pathlib import Path as P

        root = ET.parse(
            P(__file__).resolve().parents[1]
            / "gdl" / "hsf" / "ashiba_line" / "paramlist.xml"
        ).getroot()
        declared = {e.get("Name") for e in root.find("Parameters")}
        m = full_model()
        sent = set(line_params(m, m.plan.edges[0]))
        self.assertEqual(sent - declared, set())


class TestThreeViewsUseTheSameExclusions(unittest.TestCase):
    """平面・立面・3Dが同じ区間で床を抜くこと（3Dだけ敷いたままだった）."""

    def _script(self, name):
        return (Path(__file__).resolve().parents[1] / "gdl" / "hsf"
                / "ashiba_line" / "scripts" / name).read_text(encoding="utf-8")

    def test_3d_skips_stair_and_opening_bays(self):
        body = self._script("3d.gdl")
        self.assertIn("stS[it4]", body)      # 階段室の判定
        self.assertIn("bmH[ib4]", body)      # 梁枠より下の判定

    def test_3d_omits_posts_inside_an_opening(self):
        self.assertIn("bBase", self._script("3d.gdl"))

    def test_3d_draws_beams_and_stairs(self):
        body = self._script("3d.gdl")
        self.assertIn("梁枠", body)
        self.assertIn("階段室", body)

    def test_advance_rail_draws_an_x_and_no_toe_board(self):
        """先行手すりは手すり＋X斜材2本。幅木は先行手すり方式では描かない（数量も0）."""
        body3 = self._script("3d.gdl")
        i = body3.index("if railAdv = 1 then")
        blk = body3[i:body3.index("else", i)]
        self.assertEqual(blk.count("cylind advL"), 2)
        self.assertLess(body3.index("if railAdv = 0 then"), body3.index("block spans[ip], 0.02, 0.157"))
        body2 = self._script("2d.gdl")
        self.assertIn("if railAdv = 0 and inSg = 0 then rect2 xs, z + 0.05, xe, z + 0.05 + 0.157", body2)
        self.assertIn("line2 xe, z + railTop, xs, z + 0.02", body2)

    def test_stair_bays_keep_their_toe_board(self):
        """階段室は床を敷かないが幅木は残る（数量もそう拾っている）.

        3Dも立面も床と幅木を同じ条件で消していたため、階段室のスパンだけ
        図面から幅木が消え、部材表の枚数と合わなかった。
        """
        body3 = self._script("3d.gdl")
        # 床は階段室＋開口部で消す、幅木は開口部だけで消す
        self.assertIn("if skipAll = 0 then", body3)
        self.assertIn("if skipDeck = 0 then", body3)
        i = body3.index("! 幅木（外側）")
        self.assertLess(body3.index("if skipDeck = 0 then"), i)
        self.assertIn("skipDeck", body3[:i])
        body2 = self._script("2d.gdl")
        self.assertIn("if noDeck = 0 then rect2 xs, z, xe, z + 0.05", body2)
        self.assertIn("幅木は階段室にも残る", body2)

    def test_opening_bays_have_no_ledgers_in_any_view(self):
        """開口部（梁枠より下）は通路。布材・手すり・根がらみが入らない.

        立面だけがその区間を空けていて、3Dは根がらみが足元を横切り、
        数量は全スパンぶん布材を数えていた。
        """
        body3 = self._script("3d.gdl")
        self.assertIn("skipH", body3)          # 布材・手すりを開口部で止める
        self.assertIn("noPost", body3)         # 抜いた支柱には腕木も付かない
        body2 = self._script("2d.gdl")
        self.assertIn("inOpen", body2)         # 根がらみも開口部を避ける
        self.assertNotIn("line2 0, lv[1], lineLen, lv[1]", body2)

    def test_quantity_deducts_the_opening_ledgers(self):
        model = full_model()
        base = take_off(model)
        op = validate_openings(model, [Opening(0, 3600, 3600, level=3)])
        cut = take_off(model, openings=op)
        self.assertLess(cut.qty_of("布材"), base.qty_of("布材"))
        # 2スパン×2層×(床2+外側の手すり2+躯体側の手すり2) ＋ 2スパン×根がらみ2 ＝ 28本
        # ＋ 抜いた支柱1本×3段（根がらみ＋梁枠より下2層）の腕木 ＝ 31本
        self.assertEqual(base.qty_of("布材") - cut.qty_of("布材"), 31)

    def test_quantity_drops_the_jacks_of_removed_posts(self):
        """抜いた支柱は地面に達しない。ジャッキもアンダーベースも要らない."""
        model = full_model()
        base = take_off(model)
        op = validate_openings(model, [Opening(0, 3600, 3600, level=3)])
        cut = take_off(model, openings=op)
        self.assertEqual(op.removed_posts, 2)      # 内側支柱1本×内外2列
        # 分類「ジャッキ」にはアンダーベースも含むので 2本×2品目
        self.assertEqual(base.qty_of("ジャッキ") - cut.qty_of("ジャッキ"), 4)
        # 抜いた支柱は梁枠上（作業床〜天端）だけの短い構成に置き換わる（本数は減るか同じ）
        self.assertLessEqual(cut.qty_of("支柱"), base.qty_of("支柱"))
        self.assertTrue(any("梁枠上（作業床〜天端）の構成で計上" in n for n in cut.notes), cut.notes)
        self.assertFalse(any("拾い直して" in w for w in cut.warnings))

    def test_2d_has_the_same_checks(self):
        body = self._script("2d.gdl")
        for token in ("stS[it2]", "bmS[ib3]", "stS[it3]", "bmH[ib2]"):
            self.assertIn(token, body)


class TestDetailParametersAreWired(unittest.TestCase):
    """詳細図GDLのパラメータと required_details の受け渡しが食い違わないこと.

    足場ライン側だけ担保していたので、詳細図は綴り違いを実機まで気づけなかった
    （存在しないパラメータを1つ送ると、その要素の全パラメータが無視される）。
    """

    # 図面ごとに使うもの／GDL既定で足りる表示切替
    SHEET_ONLY = {"detailType", "tieV", "tieH", "asagaoProj", "asagaoAngle",
                  "beamSpan", "beamPosts", "openH", "floorH", "koma", "negaLv"}
    DISPLAY_ONLY = {"showDim", "texSiz", "warnPen"}

    def _declared(self, fixed_only=False):
        import xml.etree.ElementTree as ET
        from pathlib import Path as P

        root = ET.parse(
            P(__file__).resolve().parents[1]
            / "gdl" / "hsf" / "ashiba_detail" / "paramlist.xml"
        ).getroot()
        return {
            e.get("Name") for e in root.find("Parameters")
            if fixed_only or e.find("Fix") is None
        }

    def _sent(self):
        from ashiba.details import required_details

        m = full_model()
        out = set()
        for sheet in required_details(
            m, [{"beam_span_mm": 3600, "inner_posts_mm": [1800.0],
                 "beam_height_mm": 4600}], force_all=True
        ):
            out |= set(sheet.params)
        return out

    def test_no_parameter_that_gdl_does_not_know(self):
        self.assertEqual(self._sent() - self._declared(fixed_only=True), set())

    def test_no_unwired_parameter(self):
        unwired = (
            self._declared() - self._sent() - self.SHEET_ONLY - self.DISPLAY_ONLY
        )
        self.assertEqual(
            unwired, set(),
            f"GDLにあるのに required_details が渡していない: {sorted(unwired)}",
        )


if __name__ == "__main__":
    unittest.main()
