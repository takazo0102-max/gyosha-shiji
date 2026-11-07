"""部品 ashiba_steel（鉄骨の建て方のピース。柱の節にブラケット・継手の添え板・ベースプレートが一体、または梁の真ん中）の HSF を書き出す.

利用者の指定（2026-11-07）。割り方と重量は src/ashiba/steel_erection.py、置くのは scripts/steel_run.py。
原点: 柱のピースはピースの下端の芯、梁のピースは梁の始めの中心。spK 1 柱・2 梁、断面 spT 0 外形・1 H・2 角形・3 丸（中実で描く。重量は pcW）。
  python3 scripts/gen_steel_gdl.py     # gdl/hsf/ashiba_steel を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402
from gen_ywall_gdl import _list  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_steel"
MAIN_GUID = "6D2A9F47-1E3B-4C58-8A07-5B9E4C1F7A26"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "spK", "ピース（1 柱・2 梁）", 1),
        _param("Integer", "spT", "断面（0 外形・1 H・2 角形・3 丸）", 2),
        _param("Length", "spH", "せい", 0.5),
        _param("Length", "spB", "幅", 0.5),
        _param("Length", "spW", "ウェブの厚さ", 0.022),
        _param("Length", "spF", "フランジの厚さ", 0.022),
        _param("Length", "spL", "長さ", 4.0),
        _param("Angle", "spAng", "向き", 0.0),
        _param("Boolean", "bpOn", "ベースプレート", 0),
        _param("Length", "bpO", "ベースプレートのはみ出し", 0.1),
        _param("Length", "bpT", "ベースプレートの厚さ", 0.036),
        _param("String", "brA", "ブラケットの向き（度。カンマ区切り）", ""),
        _param("String", "brZ", "ブラケットの高さ（mm。ピースの下端から）", ""),
        _param("String", "brS", "柱の中心から根元（mm）", ""),
        _param("String", "brE", "柱の中心から先（mm）", ""),
        _param("String", "brT", "ブラケットの断面の種類", ""),
        _param("String", "brH", "ブラケットのせい（mm）", ""),
        _param("String", "brB", "ブラケットの幅（mm）", ""),
        _param("String", "brW", "ブラケットのウェブ（mm）", ""),
        _param("String", "brF", "ブラケットのフランジ（mm）", ""),
        _param("String", "spoT", "フランジ外添板の厚さ（mm）", ""),
        _param("String", "spoL", "フランジ添板の長さ（mm）", ""),
        _param("String", "spoW", "フランジ外添板の幅（mm）", ""),
        _param("String", "spiT", "フランジ内添板の厚さ（mm）", ""),
        _param("String", "spiW", "フランジ内添板の幅（mm）", ""),
        _param("String", "spwT", "ウェブ添板の厚さ（mm）", ""),
        _param("String", "spwH", "ウェブ添板の高さ（mm）", ""),
        _param("String", "spwW", "ウェブ添板の幅（mm）", ""),
        _param("RealNum", "pcW", "ピースの重量（t）", 0.0),
        _param("String", "pcName", "ピースの名前（注記）", ""),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
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


SCRIPT_1D = ("﻿! 鉄骨のピース: ブラケットの並び（m・度）\n" + _list("brA", "qA", "nB", "1") + _list("brZ", "qZ", "nZ") + _list("brS", "qS", "nS")
             + _list("brE", "qE", "nE") + _list("brT", "qT", "nT", "1") + _list("brH", "qH", "nH") + _list("brB", "qB", "nW")
             + _list("brW", "qW", "nX") + _list("brF", "qF", "nF") + _list("spoT", "uT", "n1") + _list("spoL", "uL", "n2") + _list("spoW", "uW", "n3")
             + _list("spiT", "vT", "n4") + _list("spiW", "vW", "n5") + _list("spwT", "wT", "n6") + _list("spwH", "wH", "n7") + _list("spwW", "wW", "n8")
             + "nB = min(nB, min(nZ, min(nS, min(nE, min(nT, min(nH, min(nW, min(nX, nF))))))))\n"
             + "nB = min(nB, min(n1, min(n2, min(n3, min(n4, min(n5, min(n6, min(n7, n8))))))))\n")

SCRIPT_2D = """﻿! 鉄骨のピース 2D: 断面の外形、ブラケットと継手の添え板、名前
pen penEquip
define style "spT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "spT"
if spK = 1 then
	rot2 spAng
	if spT = 3 then
		circle2 0, 0, spH / 2
	else
		rect2 -spH / 2, -spB / 2, spH / 2, spB / 2
	endif
	if bpOn then rect2 -spH / 2 - bpO, -spB / 2 - bpO, spH / 2 + bpO, spB / 2 + bpO
	del 1
	for i = 1 to nB
		rot2 qA[i]
		rect2 qS[i], -qB[i] / 2, qE[i], qB[i] / 2
		if uL[i] > 0 then rect2 qE[i] - uL[i] / 2, -uW[i] / 2, qE[i] + uL[i] / 2, uW[i] / 2
		del 1
	next i
	add2 -spH / 2, spB / 2 + bpO * bpOn + 0.3
	rot2 -SYMB_ROTANGLE
	text2 0, 0, pcName
	del 2
else
	rot2 spAng
	rect2 0, -spB / 2, spL, spB / 2
	add2 spL / 2, spB / 2 + 0.05
	text2 0, 0, pcName
	del 2
endif
hotspot2 0, 0
"""

SCRIPT_3D = """﻿! 鉄骨のピース 3D: 柱の節にブラケット・継手の添え板・ベースプレートが一体。梁は真ん中のピース
define material "sp_steel" 2, 0.62, 0.30, 0.16
define material "sp_plate" 2, 0.30, 0.55, 0.75
resol 16
sT = spT
sH = spH
sB = spB
sW = spW
sF = spF
rL = spL
material "sp_steel"
if spK = 1 then
	rotz spAng
	if bpOn then
		material "sp_plate"
		add -spH / 2 - bpO, -spB / 2 - bpO, -bpT
		block spH + 2 * bpO, spB + 2 * bpO, bpT
		del 1
		material "sp_steel"
	endif
	roty -90
	gosub "run"
	del 2
	for i = 1 to nB
		add 0, 0, qZ[i]
		rotz qA[i]
		add qS[i], 0, 0
		sT = qT[i]
		sH = qH[i]
		sB = qB[i]
		sW = qW[i]
		sF = qF[i]
		rL = qE[i] - qS[i]
		material "sp_steel"
		gosub "run"
		if uL[i] > 0 then
			! 継手の添え板（ウェブ両面、フランジの外と内。ブラケットの先をまたぐ）
			material "sp_plate"
			for s = -1 to 1 step 2
				add rL - wW[i] / 2, s * (sW + wT[i]) / 2 - wT[i] / 2, -wH[i] / 2
				block wW[i], wT[i], wH[i]
				del 1
				add rL - uL[i] / 2, -uW[i] / 2, s * (sH + uT[i]) / 2 - uT[i] / 2
				block uL[i], uW[i], uT[i]
				del 1
				for y = -1 to 1 step 2
					add rL - uL[i] / 2, y * (sW / 2 + 0.005 + vW[i] / 2) - vW[i] / 2, s * (sH / 2 - sF - vT[i] / 2) - vT[i] / 2
					block uL[i], vW[i], vT[i]
					del 1
				next y
			next s
		endif
		del 3
	next i
else
	rotz spAng
	gosub "run"
	del 1
endif
end

"run":
	! 断面 sT を +X へ長さ rL 押し出す（z＝せい、y＝幅）
	if sT = 1 then
		add 0, -sB / 2, sH / 2 - sF
		block rL, sB, sF
		del 1
		add 0, -sB / 2, -sH / 2
		block rL, sB, sF
		del 1
		add 0, -sW / 2, -sH / 2 + sF
		block rL, sW, sH - 2 * sF
		del 1
	endif
	if sT = 2 then
		add 0, -sB / 2, sH / 2 - sF
		block rL, sB, sF
		del 1
		add 0, -sB / 2, -sH / 2
		block rL, sB, sF
		del 1
		add 0, -sB / 2, -sH / 2 + sF
		block rL, sW, sH - 2 * sF
		del 1
		add 0, sB / 2 - sW, -sH / 2 + sF
		block rL, sW, sH - 2 * sF
		del 1
	endif
	if sT = 3 then
		roty 90
		cylind rL, sH / 2
		del 1
	endif
	if sT = 0 then
		add 0, -sB / 2, -sH / 2
		block rL, sB, sH
		del 1
	endif
return
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text("﻿! 鉄骨のピース: 値の一覧は無い\n", encoding="utf-8")
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
    print(f"ashiba_steel: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
