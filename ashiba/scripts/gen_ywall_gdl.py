"""部品 ashiba_ywall（山留め壁。山留めの線の1辺に1部品）の HSF を書き出す.

利用者の指定（2026-11-05）「山留めの種類も増やして シートパイルや簡易山留めなど 他にもあったら増やして LOD高めて Hこう横やいたは
矢板の平米拾えるようにしてかかりしろは厚みの分だけにして１次ねぎりと2次ねぎりで分けれるようにあと矢板を止めるさんぎも」。

ywKind: 1 親杭横矢板（H形鋼・横矢板1枚ずつ・くさび・矢板止めの桟木。根切りの段ごとに矢板の色を変える）、2 U形鋼矢板・3 ハット形・
4 軽量鋼矢板・5 アルミ矢板（1枚ずつの断面を押し出し、U形は1枚おきに裏返す。継手の爪）、6 たて込み簡易土留め（スライドレール・
パネルの積み・切梁）、7 SMW（削孔の円柱と芯材の H形鋼）、8 鋼管矢板（管と P-P 継手）。
原点＝辺の始めの山留めの線の GL、+X＝辺の向き、−Y＝根切りの側。並び（pX など）は辺の始めからの mm、割付は src/ashiba/retaining.py、
置くのは scripts/ywall_run.py.
  python3 scripts/gen_ywall_gdl.py     # gdl/hsf/ashiba_ywall を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gdl_draft  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_ywall"
MAIN_GUID = "8E3C51A2-74D9-4B6E-A1F0-3C9D27E5B814"


def _list(src: str, arr: str, cnt: str, div: str = "1000") -> str:
    """カンマ区切りの数の並び src → 配列 arr[1..cnt]（÷div）."""
    return f"""dim {arr}[]
{cnt} = 0
rest = {src}
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
		{cnt} = {cnt} + 1
		{arr}[{cnt}] = v / {div}
	endif
endwhile
"""


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "ywKind", "種類（1 親杭横矢板・2 U形鋼矢板・3 ハット形・4 軽量鋼矢板・5 アルミ矢板・6 たて込み簡易土留め・7 SMW・8 鋼管矢板）", 1),
        _param("Length", "ywL", "辺の長さ", 6),
        _param("Length", "zTop", "天端（GL から上。たて込みはレールの頭）", 0),
        _param("Length", "zBot", "先端（GL から。負。根入れを含む）", -5.5),
        _param("Length", "digD", "根切りの深さ（GL から下。正）", 4),
        _param("String", "stD", "根切りの段の底の深さ（mm。1次,2次…。最後は根切りの深さ）", "2000,4000"),
        _param("String", "pX", "親杭・鋼矢板・SMW の孔・鋼管・レールの位置（mm。辺の始めから）", "0,1500,3000,4500"),
        _param("String", "ywName", "名前", "山留め1-1"),
        _param("String", "ywInfo", "平面の注記（種類・型式・ピッチ・長さ）", "親杭 H-300 @1500 L=5.5m・横矢板 t40"),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        # H形鋼（親杭・SMW の芯材）
        _param("Length", "hH", "H形鋼の高さ H（山留めの線に直角）", 0.3),
        _param("Length", "hB", "H形鋼のフランジ幅 B（山留めの線に沿う）", 0.3),
        _param("Length", "hT1", "H形鋼のウェブの厚さ t1", 0.01),
        _param("Length", "hT2", "H形鋼のフランジの厚さ t2", 0.015),
        # 親杭横矢板
        _param("Length", "lagT", "横矢板の厚さ", 0.04),
        _param("Length", "lagW", "横矢板の幅（高さの向き）", 0.2),
        _param("Length", "kak", "掛かり代（矢板の厚さ）", 0.04),
        _param("Length", "lagGap", "フランジと矢板のすき間（くさび）", 0.015),
        _param("String", "lgA", "バイごとの矢板の始め（mm）", "110,1610,3110"),
        _param("String", "lgB", "バイごとの矢板の終わり（mm）", "1390,2890,4390"),
        _param("String", "lgN", "根切りの段ごとの矢板の枚数（1次,2次…）", "10,10"),
        _param("Length", "skW", "矢板止めの桟木の幅", 0.04),
        _param("Length", "skT", "矢板止めの桟木の厚さ", 0.016),
        # 鋼矢板・軽量鋼矢板・アルミ矢板
        _param("Length", "spW", "鋼矢板の有効幅", 0.4),
        _param("Length", "spT", "鋼矢板の板厚", 0.013),
        _param("Length", "spH", "鋼矢板の有効高さ", 0.125),
        _param("Integer", "nU", "鋼矢板の枚数", 15),
        _param("Boolean", "spAlt", "1枚おきに裏返す（U形）", 1),
        _param("String", "prX", "鋼矢板1枚の断面の外形 x（mm）", "0,112,288,400,400,288,112,0"),
        _param("String", "prY", "鋼矢板1枚の断面の外形 y（mm）", "6,62,62,6,-6,50,50,-6"),
        # SMW・鋼管矢板
        _param("Length", "smD", "SMW の削孔径", 0.55),
        _param("String", "coreX", "SMW の芯材の位置（mm）", "0,450,900"),
        _param("Length", "tbD", "鋼管矢板の外径", 0.8),
        _param("Length", "tbT", "鋼管矢板の板厚", 0.012),
        _param("Length", "jD", "鋼管矢板の継手の管の外径（P-P）", 0.1652),
        # たて込み簡易土留め
        _param("Length", "pnT", "パネルの厚さ", 0.104),
        _param("String", "pnH", "パネルの積み（下から高さ mm）", "2000,1000"),
        _param("Length", "rlW", "スライドレールの幅（線に沿う）", 0.191),
        _param("Length", "rlD", "スライドレールの奥行き（根切りの側へ）", 0.204),
        _param("String", "stY", "レールごとの切梁の長さ（根切りの中心まで。mm。0＝無し）", "1192,1192"),
        _param("String", "stZ", "切梁の段の高さ（底から mm）", "700,2300"),
        _param("Length", "stDia", "切梁の太さ", 0.1143),
        _param("Boolean", "stgCol", "3D で根切りの段ごとに矢板の色を変える", 1),
        # 腹起し・ブラケット・切梁（山留め支保工）
        _param("Boolean", "wlOn", "腹起し・切梁を描く", 0),
        _param("String", "wlZ", "腹起しの段（GL からの深さ mm。腹起しの芯）", "1000"),
        _param("Length", "wlH", "腹起し・切梁の H形鋼の高さ", 0.3),
        _param("Length", "wlB", "腹起し・切梁の H形鋼のフランジ幅", 0.3),
        _param("Length", "wlT1", "腹起し・切梁の H形鋼のウェブの厚さ", 0.01),
        _param("Length", "wlT2", "腹起し・切梁の H形鋼のフランジの厚さ", 0.015),
        _param("Length", "wlGap", "山留め壁と腹起しのすき間（裏込め）", 0.1),
        _param("Length", "wlX0", "腹起しの始め（辺の始めから）", 0.55),
        _param("Length", "wlX1", "腹起しの終わり", 4),
        _param("String", "brX", "腹起しのブラケットの位置（mm）", "700,2500"),
        _param("String", "sbX", "切梁の位置（mm）", ""),
        _param("String", "sbL", "切梁の長さ（腹起しの前の面から根切りの中心まで mm）", ""),
        _param("Length", "faceY", "根切りの側の面（山留めの線から。平面に根切りの縁を二点鎖線で）", 0.15),
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


SCRIPT_1D = ("﻿! 山留め壁: 並びを読む（m）\n"
             + _list("pX", "pileX", "nPile") + _list("stD", "stgD", "nStg")
             + _list("lgA", "bdA", "nBay") + _list("lgB", "bdB", "nBayB") + _list("lgN", "bdN", "nBn", "1")
             + _list("prX", "pfX", "nPf") + _list("prY", "pfY", "nPfY") + _list("coreX", "coreP", "nCore")
             + _list("pnH", "pnHs", "nPn") + _list("stY", "strL", "nStr") + _list("stZ", "strZ", "nStz")
             + _list("wlZ", "wlv", "nWl") + _list("brX", "brP", "nBr") + _list("sbX", "sbP", "nSb") + _list("sbL", "sbLs", "nSbL") + """if nSbL < nSb then nSb = nSbL
if not(wlOn) then nWl = 0
yW = -faceY - wlGap
if nBayB < nBay then nBay = nBayB
if nPfY < nPf then nPf = nPfY
nBoard = 0
for i = 1 to nBn
	nBoard = nBoard + bdN[i]
next i
yF = -hH / 2 + hT2 + lagGap
hgt = zTop - zBot
""")

# H形鋼の断面（原点＝芯、フランジが X に沿う）. 2D は塗り（fiS）の poly2_b、3D は prism_
H_PTS = ["-hB / 2, -hH / 2", "hB / 2, -hH / 2", "hB / 2, -hH / 2 + hT2", "hT1 / 2, -hH / 2 + hT2", "hT1 / 2, hH / 2 - hT2",
         "hB / 2, hH / 2 - hT2", "hB / 2, hH / 2", "-hB / 2, hH / 2", "-hB / 2, hH / 2 - hT2", "-hT1 / 2, hH / 2 - hT2",
         "-hT1 / 2, -hH / 2 + hT2", "-hB / 2, -hH / 2 + hT2"]


W_PTS = [q.replace("hB", "wlB").replace("hH", "wlH").replace("hT1", "wlT1").replace("hT2", "wlT2") for q in H_PTS]


def _h2d(indent: str) -> str:
    rows = H_PTS + [H_PTS[0]]
    body = ",\n".join(f"{indent}\t{p}, {-1 if i == len(rows) - 1 else 1}" for i, p in enumerate(rows))
    return (f"{indent}fill fiS\n{indent}poly2_b {len(rows)}, 7, pO, pO,\n" + body + "\n")


def _h3d(indent: str, height: str, pts=None) -> str:
    pts = pts or H_PTS
    body = ",\n".join(f"{indent}\t{p}, 15" for p in pts)
    return f"{indent}prism_ {len(pts)}, {height},\n{body}\n"


SCRIPT_2D_T = """﻿! 山留め壁 2D（GL で切った平面。CAD の平面図の描き方: scripts/gdl_draft.py）: 鋼材の断面は塗り、矢板・パネルは外形、根切りの中の
! 切梁は隠れ線。詳細（1/100 まで）は桟木・継手の爪・管の厚さ、簡略（1/250 より小さい縮尺）は線と注記だけ
@HEAD@
define style "ywT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "ywT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
! 重なり: 10 矢板・パネル、30 鋼材の断面（塗り）、40 桟木・爪・線、50 文字
if drLv = 1 then
	drawindex 40
	pen pT
	if ywKind = 1 or ywKind >= 7 then
		line_type ltC
		line2 0, 0, ywL, 0
	endif
	line_type ltZ
	line2 0, -faceY, ywL, -faceY
	line_type ltS
endif
pen pO
if ywKind = 1 then
	! 親杭（H形鋼）と横矢板（掘削側のフランジの裏）・矢板止めの桟木
	drawindex 30
	if drLv < 3 then
		for i = 1 to nPile
			add2 pileX[i], 0
@H2D@			del 1
		next i
	else
		for i = 1 to nPile
			line2 pileX[i] - hB / 2, 0, pileX[i] + hB / 2, 0
		next i
	endif
	pen pT
	for i = 1 to nBay
		drawindex 10
		rect2 bdA[i], yF, bdB[i], yF + lagT
		drawindex 40
		if drLv = 1 then
			rect2 bdA[i] + kak + 0.005, yF - skT, bdA[i] + kak + 0.005 + skW, yF
			rect2 bdB[i] - kak - 0.005 - skW, yF - skT, bdB[i] - kak - 0.005, yF
		endif
	next i
	yTx = hH / 2
endif
if ywKind >= 2 and ywKind <= 5 then
	! 鋼矢板: 1枚ずつの断面（U形は1枚おきに裏返す）。継手の爪は詳細だけ
	drawindex 30
	yB = 0
	if ywKind = 3 then yB = -(spH / 2 - spT / 2)
	for i = 1 to nU
		sgy = 1
		if spAlt and (i - 2 * int(i / 2)) = 0 then sgy = -1
		add2 (i - 1) * spW, 0
		mul2 1, sgy
		if drLv < 3 then
			for k = 1 to nPf
				k2 = k + 1
				if k2 > nPf then k2 = 1
				line2 pfX[k], pfY[k], pfX[k2], pfY[k2]
			next k
		else
			line2 0, 0, spW, 0
		endif
		del 2
		if drLv = 1 then circle2 (i - 1) * spW, yB, spT * 1.1
	next i
	yTx = spH / 2
endif
if ywKind = 6 then
	! たて込み簡易土留め: パネル（線の根切りの側）・スライドレール・切梁（隠れ線）
	drawindex 10
	for i = 1 to nPile - 1
		rect2 pileX[i], -pnT, pileX[i + 1], 0
	next i
	drawindex 30
	for i = 1 to nPile
		if drLv < 3 then
			fill fiS
			poly2_b 5, 7, pO, pO,
				pileX[i] - rlW / 2, -rlD, 1,
				pileX[i] + rlW / 2, -rlD, 1,
				pileX[i] + rlW / 2, 0, 1,
				pileX[i] - rlW / 2, 0, 1,
				pileX[i] - rlW / 2, -rlD, -1
		endif
	next i
	drawindex 40
	pen pT
	line_type ltH
	for i = 1 to min(nPile, nStr)
		if strL[i] > 0.01 then
			line2 pileX[i] - stDia / 2, -rlD, pileX[i] - stDia / 2, -rlD - strL[i]
			line2 pileX[i] + stDia / 2, -rlD, pileX[i] + stDia / 2, -rlD - strL[i]
		endif
	next i
	line_type ltS
	yTx = 0.05
endif
if ywKind = 7 then
	! SMW: 削孔の円（重なり）と芯材
	drawindex 10
	pen pT
	for i = 1 to nPile
		circle2 pileX[i], 0, smD / 2
	next i
	drawindex 30
	pen pO
	for i = 1 to nCore
		add2 coreP[i], 0
		if drLv < 3 then
@H2D2@		endif
		del 1
	next i
	yTx = smD / 2
endif
if ywKind = 8 then
	! 鋼管矢板と P-P 継手
	drawindex 30
	for i = 1 to nPile
		circle2 pileX[i], 0, tbD / 2
		if drLv = 1 then circle2 pileX[i], 0, tbD / 2 - tbT
		if i < nPile then circle2 (pileX[i] + pileX[i + 1]) / 2, 0, jD / 2
	next i
	yTx = tbD / 2
endif
if nWl > 0 and drLv < 3 then
	! 腹起し・切梁（GL の下なので隠れ線）
	drawindex 40
	pen pT
	line_type ltH
	line2 wlX0, yW, wlX1, yW
	line2 wlX0, yW - wlH, wlX1, yW - wlH
	for j = 1 to nSb
		line2 sbP[j] - wlB / 2, yW - wlH, sbP[j] - wlB / 2, yW - wlH - sbLs[j]
		line2 sbP[j] + wlB / 2, yW - wlH, sbP[j] + wlB / 2, yW - wlH - sbLs[j]
	next j
	line_type ltS
endif
drawindex 50
pen penEquip
text2 ywL / 2, yTx + 0.15 + dT / 2, ywInfo
if drLv = 1 then text2 ywL / 2, yTx + 0.15 + dT * 1.5, ywName
hotspot2 0, 0
hotspot2 ywL, 0
"""

SCRIPT_2D = (SCRIPT_2D_T.replace("@HEAD@", gdl_draft.head().rstrip("\n"))
             .replace("@H2D@", _h2d("\t\t\t")).replace("@H2D2@", _h2d("\t\t\t")))

SCRIPT_3D_T = """﻿! 山留め壁 3D（規格の寸法。親杭 JIS G 3192・鋼矢板 日本製鉄 1-1・1-2・軽量鋼矢板 1-12・アルミ矢板 ホーシン・たて込み TSパネル・
! 鋼管矢板 JIS A 5530。横矢板は 1枚ずつ・くさび・矢板止めの桟木。根切りの段ごとに矢板の色を変える（stgCol））
define material "yw_steel" 2, 0.48, 0.30, 0.22
define material "yw_sheet" 2, 0.42, 0.40, 0.38
define material "yw_alu" 2, 0.80, 0.82, 0.85
define material "yw_lag1" 2, 0.82, 0.66, 0.42
define material "yw_lag2" 2, 0.66, 0.50, 0.30
define material "yw_lag3" 2, 0.74, 0.58, 0.36
define material "yw_sanki" 2, 0.90, 0.80, 0.58
define material "yw_wedge" 2, 0.55, 0.40, 0.22
define material "yw_smw" 2, 0.66, 0.66, 0.62
define material "yw_panel" 2, 0.30, 0.45, 0.62
define material "yw_rail" 2, 0.90, 0.62, 0.12
define material "yw_strut" 2, 0.20, 0.38, 0.72
define material "yw_wale" 2, 0.72, 0.16, 0.12
resol 16
if ywKind = 1 then
	! ---- 親杭（H形鋼。フランジが山留めの線に平行） ----
	material "yw_steel"
	for i = 1 to nPile
		add pileX[i], 0, zBot
@H3D@		del 1
	next i
	! ---- 横矢板（掘削側のフランジの裏。上から1枚ずつ、根切りの段ごとに色）・くさび ----
	kb = 0
	for s = 1 to nBn
		mt = 1
		if stgCol then mt = s - 3 * int((s - 1) / 3)
		for j = 1 to bdN[s]
			kb = kb + 1
			zb = -kb * lagW
			for i = 1 to nBay
				if mt = 1 then material "yw_lag1"
				if mt = 2 then material "yw_lag2"
				if mt = 3 then material "yw_lag3"
				add bdA[i], yF, zb
				block bdB[i] - bdA[i], lagT, lagW - 0.003
				del 1
				material "yw_wedge"
				for sd = 1 to 2
					xw = bdA[i] + kak / 2 - 0.02
					if sd = 2 then xw = bdB[i] - kak / 2 - 0.02
					add xw, yF - lagGap, zb + lagW * 0.1
					block 0.04, lagGap, lagW * 0.35
					addz lagW * 0.45
					block 0.04, lagGap, lagW * 0.35
					del 2
				next sd
			next i
		next j
	next s
	! ---- 矢板止めの桟木（バイの両端・フランジの脇に縦に。根切りの段ごと） ----
	material "yw_sanki"
	kb = 0
	for s = 1 to nBn
		z1 = -kb * lagW
		kb = kb + bdN[s]
		z2 = -kb * lagW
		if z1 - z2 > 0.01 then
			for i = 1 to nBay
				add bdA[i] + kak + 0.005, yF - skT, z2 + 0.005
				block skW, skT, z1 - z2 - 0.01
				del 1
				add bdB[i] - kak - 0.005 - skW, yF - skT, z2 + 0.005
				block skW, skT, z1 - z2 - 0.01
				del 1
			next i
		endif
	next s
endif
if ywKind >= 2 and ywKind <= 5 then
	! ---- 鋼矢板: 1枚ずつ断面を押し出す（U形は1枚おきに裏返す）・継手の爪 ----
	material "yw_sheet"
	if ywKind = 5 then material "yw_alu"
	yB = 0
	if ywKind = 3 then yB = -(spH / 2 - spT / 2)
	for i = 1 to nU
		sgy = 1
		if spAlt and (i - 2 * int(i / 2)) = 0 then sgy = -1
		add (i - 1) * spW, 0, zBot
		mul 1, sgy, 1
		for k = 1 to nPf
			put pfX[k], pfY[k]
		next k
		prism nPf, hgt, get(nsp)
		del 2
		add (i - 1) * spW, yB, zBot
		cylind hgt, spT * 1.1
		del 1
	next i
endif
if ywKind = 6 then
	! ---- たて込み簡易土留め: スライドレール（頭は GL の上）・パネルの積み（リブ付き）・切梁（サポートジャッキ） ----
	material "yw_rail"
	for i = 1 to nPile
		add pileX[i] - rlW / 2, -rlD, zBot
		block rlW, rlD, hgt
		del 1
	next i
	material "yw_panel"
	for i = 1 to nPile - 1
		zp = zBot
		for k = 1 to nPn
			add pileX[i] + rlW / 2, -pnT, zp
			block pileX[i + 1] - pileX[i] - rlW, pnT, pnHs[k] - 0.005
			addz pnHs[k] * 0.33
			addy -0.03
			block pileX[i + 1] - pileX[i] - rlW, 0.03, 0.012
			addz pnHs[k] * 0.33
			block pileX[i + 1] - pileX[i] - rlW, 0.03, 0.012
			del 4
			zp = zp + pnHs[k]
		next k
	next i
	material "yw_strut"
	for i = 1 to min(nPile, nStr)
		if strL[i] > 0.01 then
			for k = 1 to nStz
				add pileX[i], -rlD, zBot + strZ[k]
				rotx 90
				cylind strL[i], stDia / 2
				cylind 0.35, stDia * 0.75
				del 2
			next k
		endif
	next i
endif
if ywKind = 7 then
	! ---- SMW: 削孔の円柱（重なり）と芯材（H形鋼） ----
	material "yw_smw"
	for i = 1 to nPile
		add pileX[i], 0, zBot
		cylind hgt, smD / 2
		del 1
	next i
	material "yw_steel"
	for i = 1 to nCore
		add coreP[i], 0, zBot
@H3D@		del 1
	next i
endif
if ywKind = 8 then
	! ---- 鋼管矢板（管の厚さ）と P-P 継手 ----
	material "yw_steel"
	for i = 1 to nPile
		add pileX[i], 0, zBot
		roty -90
		revolve 4, 360, 0, 0, tbD / 2 - tbT, 0, hgt, tbD / 2 - tbT, 0, hgt, tbD / 2, 0, 0, tbD / 2, 0
		del 2
		if i < nPile then
			add (pileX[i] + pileX[i + 1]) / 2, 0, zBot
			cylind hgt, jD / 2
			del 1
		endif
	next i
endif
! ---- 腹起し（H形鋼を寝かせて壁から wlGap 離す）・ブラケット・切梁（向かいの辺の部品と合わせて1本） ----
for k = 1 to nWl
	zc = -wlv[k]
	material "yw_wale"
	add wlX0, yW - wlH / 2, zc
	roty 90
@W3DX@	del 2
	material "yw_steel"
	for i = 1 to nBr
		add brP[i] - 0.075, yW - wlH, zc - wlB / 2 - 0.016
		block 0.15, wlH + wlGap, 0.016
		del 1
		add brP[i] - 0.006, yW - wlH * 0.6, zc - wlB / 2 - 0.2
		block 0.012, wlH * 0.6 + wlGap, 0.184
		del 1
	next i
	material "yw_wale"
	for j = 1 to nSb
		if sbLs[j] > 0.01 then
			add sbP[j], yW - wlH, zc
			rotx 90
@W3DY@			del 2
		endif
	next j
next k
end
"""

SCRIPT_3D = (SCRIPT_3D_T.replace("@H3D@", _h3d("\t\t", "hgt"))
             .replace("@W3DX@", _h3d("\t", "wlX1 - wlX0", W_PTS)).replace("@W3DY@", _h3d("\t\t\t", "sbLs[j]", W_PTS)))


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
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
        "\t<ParamSection SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\"/>\n</LibpartData>\n", encoding="utf-8")
    (OUT / "ancestry.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Ancestry>\n"
        "\t<MainGUID>F938E33A-329D-4A36-BE3E-85E126820996</MainGUID>\n"
        "\t<MainGUID>103E8D2C-8230-42E1-9597-46F84CCE28C0</MainGUID>\n</Ancestry>\n", encoding="utf-8")
    (OUT / "calledmacros.xml").write_text("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<CalledMacros>\n</CalledMacros>\n",
                                         encoding="utf-8")
    print(f"ashiba_ywall: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
