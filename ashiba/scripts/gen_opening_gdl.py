"""部品 ashiba_opening（床の開口の養生・床の縁の手すり。1つの開口か1本の縁に1部品）の HSF を書き出す.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の5番。区分と判定は src/ashiba/opening_guard.py（出典はそちら）、置くのは
scripts/opening_run.py。原点＝開口の隅（床の上端）、+X＝開口の長い辺。縁は +X に長さ opW、床は edSide の側（+1＝+Y）。
- 区分 opKind: 1 小開口・2 中開口（合板 12mm の蓋）、3 中開口（合板 24mm）、4 大開口（手すり 950・中桟 450・幅木 150・柱 1.8m 以内、
  netOn で床の上端から 0.3m 下に水平ネット）、5 床の縁（手すり・幅木）
  python3 scripts/gen_opening_gdl.py     # gdl/hsf/ashiba_opening を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_opening"
MAIN_GUID = "7D3A9E52-1C68-4F2B-A947-5E0B8C61D2F9"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Length", "opW", "開口の内法 長い辺（縁は長さ）", 2.5),
        _param("Length", "opD", "開口の内法 短い辺", 2.0),
        _param("Integer", "opKind", "区分（1 小開口・2 中開口 12mm・3 中開口 24mm・4 大開口 手すり・5 床の縁）", 4),
        _param("Boolean", "netOn", "水平ネット（大開口）", 1),
        _param("Length", "slabT", "床の厚さ", 0.2),
        _param("Integer", "edSide", "床の縁の床の側（1＝+Y・−1＝−Y）", 1),
        _param("Integer", "postK", "手すり柱（1＝スタンション NREG・2＝固定ベース PKB＋単管 1.0M）", 1),
        _param("String", "rlS", "手すりの単管の辺（1 手前・2 奥・3 左・4 右）", "1,2,3,4"),
        _param("String", "rlL", "手すりの単管の長さ（mm。辺の始めから並べる）", "3000,3000,2500,2500"),
        _param("String", "tbS", "幅木の杉足場板の辺", "1,2,3,4"),
        _param("String", "tbL", "幅木の杉足場板の長さ（mm）", "3000,3000,3000,3000"),
        _param("String", "opName", "名前（注記）", "開口1"),
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


SCRIPT_1D = """\ufeff! 開口養生: 区分ごとの寸法（opening_guard.py と同じ）と手すりの辺・単管・幅木の板（発注の規格の長さ）
kd = max(1, min(5, opKind))
lap = 0.1
lidT = 0.012
if kd = 3 then lidT = 0.024
rOff = 0.1
pSp = 1.8
! 手すりの囲い（大開口は開口の外 0.1 の長方形、縁は床の側に 0.1 入った1本）
rx0 = -rOff
ry0 = -rOff
rx1 = opW + rOff
ry1 = opD + rOff
eSd = 1
if edSide < 0 then eSd = -1
eY = eSd * rOff
! 辺ごとの始め・向き・長さ・開口（床の縁）の側（辺の +Y を 1）
dim sdX[4], sdY[4], sdA[4], sdL[4], sdI[4]
nSd = 4
sdX[1] = rx0
sdY[1] = ry0
sdA[1] = 0
sdL[1] = rx1 - rx0
sdI[1] = 1
sdX[2] = rx0
sdY[2] = ry1
sdA[2] = 0
sdL[2] = rx1 - rx0
sdI[2] = -1
sdX[3] = rx0
sdY[3] = ry0
sdA[3] = 90
sdL[3] = ry1 - ry0
sdI[3] = -1
sdX[4] = rx1
sdY[4] = ry0
sdA[4] = 90
sdL[4] = ry1 - ry0
sdI[4] = 1
if kd = 5 then
	nSd = 1
	sdX[1] = 0
	sdY[1] = eY
	sdL[1] = opW
	sdI[1] = -eSd
endif
if kd < 4 then nSd = 0
dim qrs[]
kRs = 0
rest = rlS
while strlen(rest) > 0 do
	pc = strstr(rest, ",")
	if pc > 0 then
		item = strsub(rest, 1, pc - 1)
		rest = strsub(rest, pc + 1, strlen(rest) - pc)
	else
		item = rest
		rest = ""
	endif
	k = split(item, "%n", v)
	if k > 0 then
		kRs = kRs + 1
		qrs[kRs] = v
	endif
endwhile
dim qrl[]
kRl = 0
rest = rlL
while strlen(rest) > 0 do
	pc = strstr(rest, ",")
	if pc > 0 then
		item = strsub(rest, 1, pc - 1)
		rest = strsub(rest, pc + 1, strlen(rest) - pc)
	else
		item = rest
		rest = ""
	endif
	k = split(item, "%n", v)
	if k > 0 then
		kRl = kRl + 1
		qrl[kRl] = v / 1000
	endif
endwhile
dim qbs[]
kBs = 0
rest = tbS
while strlen(rest) > 0 do
	pc = strstr(rest, ",")
	if pc > 0 then
		item = strsub(rest, 1, pc - 1)
		rest = strsub(rest, pc + 1, strlen(rest) - pc)
	else
		item = rest
		rest = ""
	endif
	k = split(item, "%n", v)
	if k > 0 then
		kBs = kBs + 1
		qbs[kBs] = v
	endif
endwhile
dim qbl[]
kBl = 0
rest = tbL
while strlen(rest) > 0 do
	pc = strstr(rest, ",")
	if pc > 0 then
		item = strsub(rest, 1, pc - 1)
		rest = strsub(rest, pc + 1, strlen(rest) - pc)
	else
		item = rest
		rest = ""
	endif
	k = split(item, "%n", v)
	if k > 0 then
		kBl = kBl + 1
		qbl[kBl] = v / 1000
	endif
endwhile
"""

SCRIPT_2D = """﻿! 開口養生 2D
pen penEquip
define style "opT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "opT"
if kd <= 3 then
	! 蓋（掛かり 0.1）と開口の内法
	rect2 -lap, -lap, opW + lap, opD + lap
	rect2 0, 0, opW, opD
	line2 0, 0, opW, opD
	line2 0, opD, opW, 0
	tx = "蓋 12mm"
	if kd = 3 then tx = "蓋 24mm"
endif
if kd = 4 then
	rect2 0, 0, opW, opD
	rect2 rx0, ry0, rx1, ry1
	rect2 rx0 + 0.05, ry0 + 0.05, rx1 - 0.05, ry1 - 0.05
	for sd = 1 to 4
		sL = rx1 - rx0
		if sd > 2 then sL = ry1 - ry0
		nP = max(1, ceil(sL / pSp - 0.0001))
		for i = 0 to nP
			px = rx0 + sL * i / nP
			py = ry0
			if sd = 2 then py = ry1
			if sd > 2 then
				px = rx0
				if sd = 4 then px = rx1
				py = ry0 + sL * i / nP
			endif
			circle2 px, py, 0.03
		next i
	next sd
	if netOn then
		line2 0, 0, opW, opD
		line2 0, opD, opW, 0
	endif
	tx = "手すり・幅木"
	if netOn then tx = "手すり・幅木・ネット"
endif
if kd = 5 then
	line2 0, eY, opW, eY
	line2 0, eY + eSd * 0.05, opW, eY + eSd * 0.05
	nP = max(1, ceil(opW / pSp - 0.0001))
	for i = 0 to nP
		circle2 opW * i / nP, eY, 0.03
	next i
	tx = "床の縁 手すり"
endif
add2 opW / 2, opD / 2
if kd = 5 then add2 0, eY + eSd * 0.5
rot2 -SYMB_ROTANGLE
text2 0, 0.2, opName + " " + tx
if kd <= 4 then text2 0, -0.2, "開口注意"
del 2
if kd = 5 then del 1
hotspot2 0, 0
hotspot2 opW, 0
hotspot2 opW, opD
hotspot2 0, opD
"""

SCRIPT_3D = """﻿! 開口養生 3D: 蓋・桟木・手すり・中桟・幅木・水平ネット
define material "op_ply" 2, 0.86, 0.72, 0.48
define material "op_cleat" 2, 0.70, 0.55, 0.35
define material "op_rail" 2, 0.90, 0.75, 0.10
define material "op_toe" 2, 0.80, 0.66, 0.45
define material "op_net" 2, 0.15, 0.40, 0.20
define material "op_post" 2, 0.62, 0.64, 0.66
define material "op_clamp" 2, 0.35, 0.36, 0.38
resol 8
if kd <= 3 then
	material "op_ply"
	add -lap, -lap, 0
	block opW + 2 * lap, opD + 2 * lap, lidT
	del 1
	! 裏のずれ止めの桟木（開口の内法に沿って一周）
	material "op_cleat"
	add 0.005, 0.005, -0.03
	block opW - 0.01, 0.03, 0.03
	del 1
	add 0.005, opD - 0.035, -0.03
	block opW - 0.01, 0.03, 0.03
	del 1
	add 0.005, 0.035, -0.03
	block 0.03, max(0.01, opD - 0.07), 0.03
	del 1
	add opW - 0.035, 0.035, -0.03
	block 0.03, max(0.01, opD - 0.07), 0.03
	del 1
endif
for sd = 1 to nSd
	sL = sdL[sd]
	sdIn = sdI[sd]
	zUp = 0
	if sd > 2 then zUp = 0.06
	add sdX[sd], sdY[sd], 0
	rotz sdA[sd]
	gosub "side"
	del 2
next sd
if kd = 4 and netOn then
	material "op_net"
	add -0.3, -0.3, -slabT - 0.3
	block opW + 0.6, opD + 0.6, 0.005
	del 1
endif
end

! 1辺: 今の座標で +X に長さ sL、開口（床の縁）は sdIn の側（+Y＝1）
"side":
	nP = max(1, ceil(sL / pSp - 0.000001))
	i0 = 0
	i1 = nP
	if sd > 2 then
		i0 = 1
		i1 = nP - 1
	endif
	! 手すり柱（スタンション NREG: 縁をくわえる顎、固定ベース PKB: 120 角の板＋単管 1.0M）
	for i = i0 to i1
		add sL * i / nP, 0, 0
		material "op_post"
		cylind 1.0, 0.0243
		if postK = 2 then
			add -0.06, -0.06, 0
			block 0.12, 0.12, 0.006
			del 1
		else
			jw = rOff + 0.03
			add -0.02, min(0, sdIn * jw), 0
			block 0.04, jw, 0.03
			del 1
			add -0.02, min(sdIn * jw, sdIn * (jw + 0.03)), -slabT - 0.05
			block 0.04, 0.03, slabT + 0.08
			del 1
			add -0.02, min(sdIn * (jw + 0.03), sdIn * (jw - 0.12)), -slabT - 0.05
			block 0.04, 0.15, 0.03
			del 1
		endif
		del 1
	next i
	! 手すり・中桟（単管の定尺を突き合わせ、継ぎ目に直線ジョイント）と直交クランプ
	tot = 0
	for k = 1 to min(kRs, kRl)
		if qrs[k] = sd then tot = tot + qrl[k]
	next k
	for r = 1 to 2
		hz = 0.95 + zUp
		if r = 2 then hz = 0.45 + zUp
		xs = -(tot - sL) / 2
		for k = 1 to min(kRs, kRl)
			if qrs[k] = sd then
				material "op_rail"
				add xs, -sdIn * 0.05, hz
				roty 90
				cylind qrl[k] - 0.003, 0.0243
				del 2
				if xs > -(tot - sL) / 2 + 0.01 then
					material "op_post"
					add xs - 0.05, -sdIn * 0.05, hz
					roty 90
					cylind 0.1, 0.027
					del 2
				endif
				xs = xs + qrl[k]
			endif
		next k
		material "op_clamp"
		for i = 0 to nP
			add sL * i / nP - 0.035, min(-sdIn * 0.06, -sdIn * 0.025), hz - 0.04
			block 0.07, 0.035, 0.08
			del 1
		next i
	next r
	! 幅木（杉足場板 35×210 を開口の側に）
	totB = 0
	for k = 1 to min(kBs, kBl)
		if qbs[k] = sd then totB = totB + qbl[k]
	next k
	material "op_toe"
	xs = -(totB - sL) / 2
	for k = 1 to min(kBs, kBl)
		if qbs[k] = sd then
			add xs + 0.003, min(sdIn * 0.035, sdIn * 0.07), 0.002
			block qbl[k] - 0.006, 0.035, 0.21
			del 1
			xs = xs + qbl[k]
		endif
	next k
return
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(
        "﻿! 開口養生: 区分の一覧\nvalues{2} \"opKind\" 1, \"小開口（蓋 12mm）\", 2, \"中開口（蓋 12mm）\", 3, \"中開口（蓋 24mm・鋼製）\", "
        "4, \"大開口（手すり・幅木・ネット）\", 5, \"床の縁（手すり・幅木）\"\nvalues \"edSide\" -1, 1\n", encoding="utf-8")
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
    print(f"ashiba_opening: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
