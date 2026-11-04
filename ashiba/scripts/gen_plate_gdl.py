"""部品 ashiba_plate（敷鉄板。ホットスポットで広げる範囲に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「敷鉄板はホットスポットで広げれるようにして 別オブジェクトにして」。寸法と重さは日建リース工業
仮設資材カタログ Vol.10 p394 の厚板鋼板（NT22×5×20＝1,524×6,096・1,604kg、NT22×5×10＝1,524×3,048・802kg、NT22×4×8＝
1,219×2,438・513kg、NT22×3×6＝914×1,829・289kg、厚さ 22。吊り込み用の穴は 5×20 に2か所・ほかは1か所）。
原点＝範囲の隅、+X・+Y に広げる。広さ lenX・lenY は平面のホットスポット（右の辺の真ん中・上の辺の真ん中・右上の隅）で引いて
変え、離すと1枚の倍数に切り上げる（パラメータスクリプト）。長い辺の向き plDir（0＝X・1＝Y）、2段 plLay＝2 は上の段を十字に。
平面は1枚ずつの外形・吊り穴・枚数と重さの注記、3D は1枚ずつの板（段ごとに色を少し変える）。クレーンのアウトリガの下にも置く
（scripts/crane_run.py）。範囲を線で選んで置くのは scripts/plate_run.py。
  python3 scripts/gen_plate_gdl.py     # gdl/hsf/ashiba_plate を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gdl_draft  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_plate"
MAIN_GUID = "6E2A4C91-7B3D-4F58-A1C6-9D0E5B8F2A37"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Length", "lenX", "広さ X（ホットスポットで引く。1枚の倍数に切り上げる）", 3.048),
        _param("Length", "lenY", "広さ Y（同上）", 1.524),
        _param("Integer", "plType", "敷鉄板（1＝NT22×5×20・2＝NT22×5×10・3＝NT22×4×8・4＝NT22×3×6）", 2),
        _param("Integer", "plDir", "長い辺の向き（0＝X・1＝Y）", 0),
        _param("Integer", "plLay", "段数（2＝上の段を十字に）", 1),
        _param("Boolean", "plText", "枚数と重さを注記する", 1),
        _param("String", "plName", "名前（注記）", "敷鉄板"),
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


SCRIPT_1D = """﻿! 敷鉄板: 1枚の寸法（日建 厚板鋼板）と並べる枚数（m）
plS = 1.524
plLg = 3.048
plKg = 802
nHole = 1
if plType = 1 then
	plLg = 6.096
	plKg = 1604
	nHole = 2
endif
if plType = 3 then
	plS = 1.219
	plLg = 2.438
	plKg = 513
endif
if plType = 4 then
	plS = 0.914
	plLg = 1.829
	plKg = 289
endif
plTk = 0.022
! 下の段の1枚の X・Y
pX = plLg
pY = plS
if plDir = 1 then
	pX = plS
	pY = plLg
endif
nX = max(1, ceil(lenX / pX - 0.02))
nY = max(1, ceil(lenY / pY - 0.02))
lx = nX * pX
ly = nY * pY
nTot = nX * nY
! 2段目（十字）: 同じ範囲を向きを変えた板で
qX = pY
qY = pX
mX = max(1, ceil(lx / qX - 0.02))
mY = max(1, ceil(ly / qY - 0.02))
if plLay >= 2 then nTot = nTot + mX * mY
"""

SCRIPT_VL = """﻿! 敷鉄板: ホットスポットで引いた広さを1枚の倍数に切り上げる
if abs(lenX - lx) > 0.0005 then parameters lenX = lx
if abs(lenY - ly) > 0.0005 then parameters lenY = ly
values "plType" 1, 2, 3, 4
values "plDir" 0, 1
values "plLay" 1, 2
"""

SCRIPT_2D_T = """﻿! 敷鉄板 2D（CAD の平面図の描き方: scripts/gdl_draft.py）: 並べた範囲の外形は太線、1枚ずつの継ぎ目は細線、2段敷きは上の段（十字）を
! 実線・下の段を隠れ線。縮尺で 詳細（1/100: 吊り穴まで）・標準（1/200: 継ぎ目まで）・簡略（範囲の外形だけ）
@HEAD@
define style "plT" "ＭＳ Ｐゴシック", texSiz, 2, 0
style "plT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
if drLv < 3 then
	pen pT
	if plLay >= 2 then line_type ltH
	for i = 1 to nX
		for j = 1 to nY
			x0 = (i - 1) * pX
			y0 = (j - 1) * pY
			rect2 x0, y0, x0 + pX, y0 + pY
			! 吊り込み用の穴（長い辺の中ほど。5×20 は2か所。上に段があれば見えない）
			if drLv = 1 and plLay < 2 then
				for h = 1 to nHole
					fh = h / (nHole + 1)
					if plDir = 0 then
						rect2 x0 + pX * fh - 0.05, y0 + pY / 2 - 0.025, x0 + pX * fh + 0.05, y0 + pY / 2 + 0.025
					else
						rect2 x0 + pX / 2 - 0.025, y0 + pY * fh - 0.05, x0 + pX / 2 + 0.025, y0 + pY * fh + 0.05
					endif
				next h
			endif
		next j
	next i
	line_type ltS
	if plLay >= 2 then
		! 上の段（十字）の外形
		for i = 1 to mX
			for j = 1 to mY
				rect2 (i - 1) * qX, (j - 1) * qY, i * qX, j * qY
			next j
		next i
	endif
endif
pen pO
rect2 0, 0, lx, ly
if plText then
	pen penEquip
	add2 lx / 2, -0.2
	rot2 -SYMB_ROTANGLE
	text2 0, 0, plName + " " + str(nTot, 1, 0) + "枚・" + str(round_int(nTot * plKg), 1, 0) + "kg"
	del 2
endif
! 広げるホットスポット（X は右の辺の真ん中、Y は上の辺の真ん中）
hotspot2 0, 0
hotspot2 lx, 0
hotspot2 lx, ly
hotspot2 0, ly
hotspot2 0, ly / 2, 101, lenX, 1 + 128
hotspot2 lenX, ly / 2, 102, lenX, 2
hotspot2 -1, ly / 2, 103, lenX, 3
hotspot2 lx / 2, 0, 104, lenY, 1 + 128
hotspot2 lx / 2, lenY, 105, lenY, 2
hotspot2 lx / 2, -1, 106, lenY, 3
"""
SCRIPT_2D = SCRIPT_2D_T.replace("@HEAD@", gdl_draft.head().rstrip("\n"))


SCRIPT_3D = """﻿! 敷鉄板 3D: 1枚ずつの板（厚さ 22）。2段目は十字に重ねる
define material "pl_steel1" 2, 0.33, 0.34, 0.36
define material "pl_steel2" 2, 0.42, 0.43, 0.45
material "pl_steel1"
for i = 1 to nX
	for j = 1 to nY
		add (i - 1) * pX + 0.002, (j - 1) * pY + 0.002, 0
		block pX - 0.004, pY - 0.004, plTk
		del 1
	next j
next i
if plLay >= 2 then
	material "pl_steel2"
	for i = 1 to mX
		for j = 1 to mY
			add (i - 1) * qX + 0.002, (j - 1) * qY + 0.002, plTk
			block qX - 0.004, qY - 0.004, plTk
			del 1
		next j
	next i
endif
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(SCRIPT_VL, encoding="utf-8")
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
    print(f"ashiba_plate: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
