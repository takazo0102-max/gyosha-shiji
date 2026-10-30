"""部品 ashiba_box（足場の箱。超簡易モード）の HSF を書き出す.

利用者の指定（2026-10-30）「超簡易モードになってない いきなり足場が現れた」「なんか違う 箱を作って自分で伸び縮みするような
感じ」→ 一周の箱（四角）・ボタンで本体にする。

四角い足場の箱を置き、平面で右の辺・上の辺の中ほどのつまみを引くと長手・短手が伸び縮みする。長さは定尺（szList）の組み合わせに
吸着し、スパンの並び（spanX・spanY）を書き直す（定尺の最大を並べ、端数を定尺1〜2本で埋める）。3D の天端のつまみを引くと作業床の
段数（nLev）が増減する。形が決まったらパレットの「箱を足場に」で、そのスパンと段数の足場一式に置き直す（scripts/box_run.py）。

原点＝内側の建地の列の角（箱の左下の支柱）。+X＝長手、+Y＝短手、建物は箱の内側、足場（外側の列）は外へ rowW。
  python3 scripts/gen_box_gdl.py     # gdl/hsf/ashiba_box を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_box"
MAIN_GUID = "5C1E7A42-8B3D-4F6A-9E21-7D4B2A9C6E10"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Length", "lenX", "長手（内側の建地の列。つまみで引くと定尺の組み合わせに吸着）", 7.316),
        _param("Length", "lenY", "短手（同上）", 5.487),
        _param("String", "spanX", "長手のスパン（mm、カンマ区切り。原点から）", "1829,1829,1829,1829"),
        _param("String", "spanY", "短手のスパン（同上）", "1829,1829,1829"),
        _param("String", "szList", "使える定尺（mm、カンマ区切り。大きい順。置くときに系列から入れる）", "1829,1524,1219,914,610"),
        _param("Length", "rowW", "足場の幅（内外の建地の間）", 0.914),
        _param("Integer", "nLev", "作業床の段数（3D の天端のつまみで増減）", 4),
        _param("Length", "lev1", "1段目の作業床の高さ", 1.78),
        _param("Length", "floorH", "作業床の段の間隔", 1.8),
        _param("Length", "jackH", "ジャッキの繰出し（図の目安）", 0.1),
        _param("Length", "topEdit", "最上段の作業床（3D のつまみ。引くと段数が変わる）", 7.18),
        _param("String", "seriesId", "足場の種類（系列の ID。本体にするときに使う）", ""),
        _param("Length", "standoff", "離れ（躯体から内側の建地まで。本体にするときに使う）", 0.3),
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


def _parse(src: str, arr: str, cnt: str, scale: str) -> str:
    """カンマ区切りの mm の並び src を配列 arr[1..cnt] に（m）."""
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
		if v > 100 then
			{cnt} = {cnt} + 1
			{arr}[{cnt}] = v {scale}
		endif
	endif
endwhile
"""


SCRIPT_1D = ("﻿! 足場の箱: スパンの並びと定尺を読む（m）\n"
             + _parse("spanX", "sx", "nX", "/ 1000") + _parse("spanY", "sy", "nY", "/ 1000")
             + _parse("szList", "sz", "nSz", "/ 1000") + """if nX = 0 then
	nX = 1
	sx[1] = max(0.6, lenX)
endif
if nY = 0 then
	nY = 1
	sy[1] = max(0.6, lenY)
endif
lx = 0
for i = 1 to nX
	lx = lx + sx[i]
next i
ly = 0
for j = 1 to nY
	ly = ly + sy[j]
next j
nL = max(1, nLev)
deckTop = lev1 + (nL - 1) * floorH
postH = deckTop + 1.0
""")

SCRIPT_VL = """﻿! ============================================================
! 足場の箱 パラメータスクリプト: つまみで引いた長さ（lenX・lenY）を定尺の組み合わせに吸着してスパンの並びを書き直す。
! 定尺の最大を n 本並べ、端数を定尺 0〜2 本で埋める組のうち、引いた長さにいちばん近いもの（同じ近さなら本数の少ない方）。
! 3D の天端のつまみ（topEdit）は段の間隔に丸めて作業床の段数（nLev）にする
! ============================================================
! どのパラメータを変えたかは GLOB_MODPAR_NAME に頼らず、値の食い違いで決める（つまみで引いても名前が来ないことがあり、
! 名前で決めていたときは引いた長さをスパンの合計に戻してしまい、つまみが動かなかった。利用者 2026-10-30: つまみが動かない）
if GLOB_MODPAR_NAME = "spanX" then
	parameters lenX = lx
else
	if abs(lenX - lx) > 0.0005 and nSz > 0 then
		want = lenX
		gosub "snap"
		parameters spanX = sOut, lenX = tBest
	endif
endif
if GLOB_MODPAR_NAME = "spanY" then
	parameters lenY = ly
else
	if abs(lenY - ly) > 0.0005 and nSz > 0 then
		want = lenY
		gosub "snap"
		parameters spanY = sOut, lenY = tBest
	endif
endif
if GLOB_MODPAR_NAME = "nLev" or GLOB_MODPAR_NAME = "lev1" or GLOB_MODPAR_NAME = "floorH" then
	parameters topEdit = deckTop
else
	if abs(topEdit - deckTop) > 0.0005 then
		nNew = round_int((topEdit - lev1) / floorH) + 1
		if nNew < 1 then nNew = 1
		if nNew > 30 then nNew = 30
		parameters nLev = nNew, topEdit = lev1 + (nNew - 1) * floorH
	endif
endif
end

"snap":
	mx = sz[1]
	tBest = 0
	bd = 1e9
	bn = 0
	bi = 0
	bj = 0
	nTop = int(want / mx) + 1
	for n = 0 to nTop
		for i = 0 to nSz
			for j = i to nSz
				s = 0
				if i > 0 then s = sz[i]
				t = 0
				if j > 0 then t = sz[j]
				tt = n * mx + s + t
				if tt > 0.1 then
					d = abs(tt - want) + 0.0001 * (n + (i > 0) + (j > 0))
					if d < bd then
						bd = d
						tBest = tt
						bn = n
						bi = i
						bj = j
					endif
				endif
			next j
		next i
	next n
	sOut = ""
	for k = 1 to bn
		if sOut = "" then
			sOut = str(mx * 1000, 1, 0)
		else
			sOut = sOut + "," + str(mx * 1000, 1, 0)
		endif
	next k
	if bi > 0 then
		if sOut = "" then
			sOut = str(sz[bi] * 1000, 1, 0)
		else
			sOut = sOut + "," + str(sz[bi] * 1000, 1, 0)
		endif
	endif
	if bj > 0 then
		if sOut = "" then
			sOut = str(sz[bj] * 1000, 1, 0)
		else
			sOut = sOut + "," + str(sz[bj] * 1000, 1, 0)
		endif
	endif
return
"""

SCRIPT_2D = """﻿! 足場の箱 2D: 内外の建地の列・支柱・スパン寸法・見出しと、伸び縮みのつまみ（右の辺＝長手、上の辺＝短手）
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "bxT" "ＭＳ Ｐゴシック", texSiz, 2, 0
define style "bxB" "ＭＳ Ｐゴシック", texSiz, 8, 0
define style "bxR" "ＭＳ Ｐゴシック", texSiz, 6, 0
define style "bxL" "ＭＳ Ｐゴシック", texSiz, 4, 0
gap = texSiz * GLOB_SCALE / 1000 * 0.6
rP = 0.03
rect2 0, 0, lx, ly
rect2 -rowW, -rowW, lx + rowW, ly + rowW
xx = 0
for i = 1 to nX + 1
	line2 xx, 0, xx, -rowW
	line2 xx, ly, xx, ly + rowW
	circle2 xx, 0, rP
	circle2 xx, -rowW, rP
	circle2 xx, ly, rP
	circle2 xx, ly + rowW, rP
	if i <= nX then
		style "bxT"
		text2 xx + sx[i] / 2, -rowW - gap, str(sx[i] * 1000, 1, 0)
		style "bxB"
		text2 xx + sx[i] / 2, ly + rowW + gap, str(sx[i] * 1000, 1, 0)
		xx = xx + sx[i]
	endif
next i
yy = 0
for j = 1 to nY + 1
	line2 0, yy, -rowW, yy
	line2 lx, yy, lx + rowW, yy
	circle2 -rowW, yy, rP
	circle2 lx + rowW, yy, rP
	if j > 1 and j <= nY then
		circle2 0, yy, rP
		circle2 lx, yy, rP
	endif
	if j <= nY then
		style "bxR"
		text2 -rowW - gap, yy + sy[j] / 2, str(sy[j] * 1000, 1, 0)
		style "bxL"
		text2 lx + rowW + gap, yy + sy[j] / 2, str(sy[j] * 1000, 1, 0)
		yy = yy + sy[j]
	endif
next j
circle2 -rowW, -rowW, rP
circle2 lx + rowW, -rowW, rP
circle2 -rowW, ly + rowW, rP
circle2 lx + rowW, ly + rowW, rP
style "bxT"
text2 lx / 2, -rowW - 4 * gap, "足場の箱 " + str(lx * 1000, 1, 0) + "×" + str(ly * 1000, 1, 0) + "・作業床 " + str(nL, 1, 0) + "段（最上段 " + str(deckTop * 1000, 1, 0) + "）"
hotspot2 0, 0
hotspot2 lx, 0
hotspot2 lx, ly
hotspot2 0, ly
hotspot2 -rowW, -rowW
hotspot2 lx + rowW, ly + rowW
! 伸び縮みのつまみ（右の辺の中ほどで長手、上の辺の中ほどで短手）
hotspot2 0, ly / 2, 101, lenX, 1 + 128
hotspot2 lenX, ly / 2, 102, lenX, 2
hotspot2 -1, ly / 2, 103, lenX, 3
hotspot2 lx / 2, 0, 104, lenY, 1 + 128
hotspot2 lx / 2, lenY, 105, lenY, 2
hotspot2 lx / 2, -1, 106, lenY, 3
"""

SCRIPT_3D = """﻿! ============================================================
! 足場の箱 3D（超簡易モードの形の確かめ）: 外周の支柱（内外の列と出隅の支柱）・各段の作業床・腕木・布材、外側の手すり・
! 中桟（一周）。階段・壁つなぎ・シートは本体にしたときに付く。天端のつまみで作業床の段数を増減
! ============================================================
resol 8
define material "bx_post" 2, 0.62, 0.64, 0.68
define material "bx_deck" 2, 0.42, 0.45, 0.50
define material "bx_jack" 2, 0.35, 0.35, 0.38
mPo = IND(MATERIAL, "bx_post")
mDe = IND(MATERIAL, "bx_deck")
mJa = IND(MATERIAL, "bx_jack")
rP = 0.0243
rL = 0.0214
! ---- 支柱の位置 ----
dim px[], py[]
nP = 0
xx = 0
for i = 1 to nX + 1
	nP = nP + 1
	px[nP] = xx
	py[nP] = 0
	nP = nP + 1
	px[nP] = xx
	py[nP] = -rowW
	nP = nP + 1
	px[nP] = xx
	py[nP] = ly
	nP = nP + 1
	px[nP] = xx
	py[nP] = ly + rowW
	if i <= nX then xx = xx + sx[i]
next i
yy = 0
for j = 1 to nY - 1
	yy = yy + sy[j]
	nP = nP + 1
	px[nP] = 0
	py[nP] = yy
	nP = nP + 1
	px[nP] = -rowW
	py[nP] = yy
	nP = nP + 1
	px[nP] = lx
	py[nP] = yy
	nP = nP + 1
	px[nP] = lx + rowW
	py[nP] = yy
next j
for cx = 0 to 1
	for cy = 0 to 1
		nP = nP + 1
		px[nP] = -rowW + cx * (lx + 2 * rowW)
		py[nP] = -rowW + cy * (ly + 2 * rowW)
	next cy
next cx
for k = 1 to nP
	add px[k], py[k], 0
	material mJa
	add -0.07, -0.07, 0
	block 0.14, 0.14, 0.008
	del 1
	cylind jackH, 0.017
	material mPo
	add 0, 0, jackH
	cylind postH - jackH, rP
	del 2
next k
! ---- 根がらみ（内外の列を一周） ----
material mPo
z = jackH + 0.15
o = 0
gosub "ring"
o = rowW
gosub "ring"
! ---- 各段: 作業床・布材（内外）・腕木・外側の手すり・中桟 ----
for lv = 1 to nL
	zl = lev1 + (lv - 1) * floorH
	material mPo
	z = zl
	o = 0
	gosub "ring"
	o = rowW
	gosub "ring"
	z = zl + 0.9
	gosub "ring"
	z = zl + 0.45
	gosub "ring"
	! 腕木（内外の列を結ぶ）
	xx = 0
	for i = 1 to nX + 1
		add xx, 0, zl
		rotx 90
		cylind rowW, rL
		del 2
		add xx, ly, zl
		rotx -90
		cylind rowW, rL
		del 2
		if i <= nX then xx = xx + sx[i]
	next i
	yy = 0
	for j = 1 to nY - 1
		yy = yy + sy[j]
		add 0, yy, zl
		roty -90
		cylind rowW, rL
		del 2
		add lx, yy, zl
		roty 90
		cylind rowW, rL
		del 2
	next j
	! 作業床（スパンごと＋出隅の升目）
	material mDe
	xx = 0
	for i = 1 to nX
		add xx + 0.01, -rowW + 0.02, zl - 0.045
		block sx[i] - 0.02, rowW - 0.04, 0.045
		del 1
		add xx + 0.01, ly + 0.02, zl - 0.045
		block sx[i] - 0.02, rowW - 0.04, 0.045
		del 1
		xx = xx + sx[i]
	next i
	yy = 0
	for j = 1 to nY
		add -rowW + 0.02, yy + 0.01, zl - 0.045
		block rowW - 0.04, sy[j] - 0.02, 0.045
		del 1
		add lx + 0.02, yy + 0.01, zl - 0.045
		block rowW - 0.04, sy[j] - 0.02, 0.045
		del 1
		yy = yy + sy[j]
	next j
	for cx = 0 to 1
		for cy = 0 to 1
			add -rowW + 0.02 + cx * (lx + rowW), -rowW + 0.02 + cy * (ly + rowW), zl - 0.045
			block rowW - 0.04, rowW - 0.04, 0.045
			del 1
		next cy
	next cx
next lv
! ---- 段数のつまみ（出隅の支柱の上。引くと段の間隔に丸めて段数が変わる） ----
hotspot -rowW, -rowW, 0, 1000, topEdit, 1 + 128
hotspot -rowW, -rowW, topEdit, 1001, topEdit, 2
hotspot -rowW, -rowW, -1, 1002, topEdit, 3
end

"ring":
	! 内側の列（o = 0）か外側の列（o = rowW）を高さ z で一周
	add -o, -o, z
	roty 90
	cylind lx + 2 * o, rL
	del 2
	add -o, ly + o, z
	roty 90
	cylind lx + 2 * o, rL
	del 2
	add -o, -o, z
	rotx -90
	cylind ly + 2 * o, rL
	del 2
	add lx + o, -o, z
	rotx -90
	cylind ly + 2 * o, rL
	del 2
return
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
    print(f"ashiba_box: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
