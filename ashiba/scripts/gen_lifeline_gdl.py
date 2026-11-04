"""部品 ashiba_lifeline（鉄骨梁の上の親綱と親綱支柱。1本の梁（線）に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「親綱と親綱支柱も追加して」。割付と判定は src/ashiba/lifeline.py（出典はそちら）、置くのは
scripts/lifeline_run.py。原点＝梁の芯の始め（上フランジの上）、+X＝梁の向き。支柱は両端から llEnd 入れて nSpan スパンに等分、
postK 1 NTP（H鋼取付用・高さ 1,045）・2 ALPA12（アルミ・1,081）。親綱はスパンごとに1本、片側に緊張器
  python3 scripts/gen_lifeline_gdl.py     # gdl/hsf/ashiba_lifeline を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gdl_draft  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_lifeline"
MAIN_GUID = "8E4D1B63-7C2A-4F95-B0E8-3A9C5D7F1E26"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Length", "llL", "梁（線）の長さ", 24.0),
        _param("Integer", "nSpan", "スパンの数（0＝張れない）", 3),
        _param("Length", "llEnd", "梁の端から支柱まで", 0.3),
        _param("Integer", "postK", "親綱支柱（1 NTP H鋼取付用・2 ALPA12 アルミ）", 1),
        _param("String", "llName", "名前（注記）", "親綱1"),
        _param("String", "llDrop", "落差の注記", "落差 8.0m"),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        *gdl_draft.params(),
        "\t\t<PenColor Name=\"penEquip\">\n\t\t\t<Description><![CDATA[\"線のペン\"]]></Description>\n"
        "\t\t\t<Value>1</Value>\n\t\t</PenColor>\n",
    ]
    return ("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ParamSection>\n\t<ParamSectHeader>\n"
            "\t\t<AutoHotspots>false</AutoHotspots>\n\t\t<StatBits>\n\t\t\t<STBit_UIDefault/>\n\t\t</StatBits>\n"
            "\t\t<WDLeftFrame>0</WDLeftFrame>\n\t\t<WDRightFrame>0</WDRightFrame>\n\t\t<WDTopFrame>0</WDTopFrame>\n"
            "\t\t<WDBotFrame>0</WDBotFrame>\n\t\t<LayFlags>65535</LayFlags>\n\t\t<WDMirrorThickness>0</WDMirrorThickness>\n"
            "\t\t<WDWallInset>0</WDWallInset>\n\t</ParamSectHeader>\n"
            "\t<Parameters SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\">\n" + "".join(ps)
            + "\t</Parameters>\n</ParamSection>\n")


SCRIPT_1D = """﻿! 親綱: 支柱の位置（両端から llEnd、nSpan に等分）と支柱の高さ
nS = max(0, nSpan)
spL = 0
if nS > 0 then spL = max(0, llL - 2 * llEnd) / nS
pH = 1.045
if postK = 2 then pH = 1.081
rpZ = pH - 0.06
"""

SCRIPT_2D_T = """﻿! 親綱 2D（CAD の平面図の描き方: scripts/gdl_draft.py）: 梁の芯は一点鎖線（細線）、親綱支柱は太線、親綱は破線の太線。
! 縮尺で 詳細（支柱の H 形のベース）・標準（支柱は小さな箱）・簡略（親綱の線と名前だけ）。注記の行送りは縮尺に合わせる
@HEAD@
define style "llT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "llT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
if drLv < 3 then
	pen pT
	line_type ltC
	line2 0, 0, llL, 0
	line_type ltS
endif
if nS > 0 then
	if drLv < 3 then
		pen pO
		for i = 0 to nS
			px = llEnd + i * spL
			rect2 px - 0.065, -0.0975, px + 0.065, 0.0975
			if drLv = 1 then line2 px - 0.065, -0.0975, px + 0.065, 0.0975
		next i
	endif
	pen pO
	line_type ltH
	for i = 1 to nS
		line2 llEnd + (i - 1) * spL + 0.07, 0.03, llEnd + i * spL - 0.07, 0.03
	next i
	line_type ltS
endif
pen penEquip
add2 llL / 2, 0
rot2 -SYMB_ROTANGLE
tx = llName + " 親綱 " + str(nS, 1, 0) + "スパン（1スパン1人）"
if nS = 0 then tx = llName + " 親綱は張れない（水平ネット等）"
text2 0, 0.3 + 1.5 * dT, tx
if drLv < 3 then text2 0, 0.3 + 0.5 * dT, llDrop
del 2
hotspot2 0, 0
hotspot2 llL, 0
"""

SCRIPT_2D = SCRIPT_2D_T.replace("@HEAD@", gdl_draft.head().rstrip("\n"))


SCRIPT_3D = """﻿! 親綱 3D: 親綱支柱（フランジをくわえる金具・角パイプの柱・頭の受け）、スパンごとの親綱と緊張器
define material "ll_post" 2, 0.85, 0.65, 0.10
define material "ll_alu" 2, 0.80, 0.82, 0.85
define material "ll_clamp" 2, 0.35, 0.36, 0.38
define material "ll_rope" 2, 0.80, 0.62, 0.30
resol 8
if nS > 0 then
	for i = 0 to nS
		px = llEnd + i * spL
		material "ll_clamp"
		add px - 0.065, -0.0975, -0.03
		block 0.13, 0.195, 0.22
		del 1
		material "ll_post"
		if postK = 2 then material "ll_alu"
		add px - 0.0225, -0.0375, 0.19
		block 0.045, 0.075, pH - 0.19
		del 1
		add px - 0.025, -0.115, pH - 0.012
		block 0.05, 0.23, 0.012
		del 1
	next i
	for i = 1 to nS
		x0 = llEnd + (i - 1) * spL
		material "ll_rope"
		add x0 + 0.03, 0, rpZ
		roty 90
		cylind spL - 0.06, 0.006
		del 2
		material "ll_clamp"
		add x0 + spL - 0.45, -0.03, rpZ - 0.05
		block 0.12, 0.06, 0.1
		del 1
	next i
endif
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(
        "﻿! 親綱: 支柱の一覧\nvalues{2} \"postK\" 1, \"親綱支柱（H鋼取付用）NTP\", 2, \"アルミ製親綱支柱 ALPA12\"\n", encoding="utf-8")
    (OUT / "scripts" / "2d.gdl").write_text(SCRIPT_2D, encoding="utf-8")
    (OUT / "scripts" / "3d.gdl").write_text(SCRIPT_3D, encoding="utf-8")
    (OUT / "libpartdata.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<LibpartData Owner=\"1196638531\" Signature=\"1196644685\" Version=\"44\">\n"
        f"\t<Identification>\n\t\t<MainGUID>{MAIN_GUID}</MainGUID>\n\t\t<IsPlaceable>true</IsPlaceable>\n"
        "\t\t<IsArchivable>false</IsArchivable>\n\t\t<MigrationValue>Normal</MigrationValue>\n\t\t<IsTemplate>false</IsTemplate>\n"
        "\t</Identification>\n\t<Ancestry SectVersion=\"1\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<CalledMacros SectVersion=\"2\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_3D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_2D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_1D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_VL SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<ParamSection SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\"/>\n</LibpartData>\n", encoding="utf-8")
    (OUT / "ancestry.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Ancestry>\n"
        "\t<MainGUID>F938E33A-329D-4A36-BE3E-85E126820996</MainGUID>\n"
        "\t<MainGUID>103E8D2C-8230-42E1-9597-46F84CCE28C0</MainGUID>\n</Ancestry>\n", encoding="utf-8")
    (OUT / "calledmacros.xml").write_text("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<CalledMacros>\n</CalledMacros>\n",
                                         encoding="utf-8")
    print(f"ashiba_lifeline: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
