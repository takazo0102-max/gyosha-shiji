"""部品 ashiba_cfill（斜めの角の隅のつなぎ）の HSF を書き出す.

利用者の指定（2026-10-31）「斜めの角もつながるようにしてちょ 無理な場合はかど合わせてアンチをし単管手すり作成か足場板と単管手すりに
するか」。割付は縦・横しか解けないので、直角でない角の2本の足場はそれぞれ1本で解き、そのあいだのすき間をこの部品でふさぐ。

原点＝線の角（2本の足場の内側の列の交点）。polyX・polyY＝床の形（原点からの mm、左回り）、railE＝手すり・幅木を付ける辺の番号
（辺 k は点 k→k+1。0 から）、levList＝作業床の段の高さ（原点の高さから mm）。各段に、外の辺に直角な単管の受け2本（間＝アンチの長さ）に
アンチ（antiL×antiW。外の辺に平行に並べる）を掛け、手すりの辺に単管の上桟（床から 950）・中桟（450）と幅木（150）。
  python3 scripts/gen_cfill_gdl.py     # gdl/hsf/ashiba_cfill を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_box_gdl import _parse  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_cfill"
MAIN_GUID = "3B7E2C19-6A4D-4F0B-8E51-2C9D7A1F4B63"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("String", "polyX", "床の形の x（原点からの mm、カンマ区切り。左回り）", "0,0,800,0"),
        _param("String", "polyY", "床の形の y（同上）", "0,-914,-457,0"),
        _param("String", "railE", "手すり・幅木を付ける辺の番号（辺 k は点 k→k+1。0 から。カンマ区切り）", "1"),
        _param("String", "levList", "作業床の段の高さ（原点の高さから mm、カンマ区切り）", "1780,3580,5380,7180"),
        _param("Integer", "deckKind", "作業床（1＝アンチ・2＝足場板）", 1),
        _param("Length", "deckT", "作業床の厚み", 0.045),
        _param("Length", "antiL", "アンチの長さ（受けの単管の間。インチの系列は 914、メートルは 900）", 0.914),
        _param("Length", "antiW", "アンチの幅", 0.24),
        _param("String", "plkX", "アンチの外の辺側の始めの角の x（原点から mm。空なら外の辺の中点から並べる）", ""),
        _param("String", "plkY", "同 y", ""),
        _param("RealNum", "plkAng", "アンチの向き（度。外の辺の向き）", 0),
        _param("String", "plkL", "アンチの長さ（列ごと mm。空なら antiL）", ""),
        _param("String", "fbX", "残りのすき間をふさぐ足場板（列ごと）の始めの角の x（原点から mm）", ""),
        _param("String", "fbY", "同 y", ""),
        _param("String", "fbL", "同 長さ（mm）", ""),
        _param("String", "supX0", "受けの単管の始めの x（原点から mm）", ""),
        _param("String", "supY0", "同 y", ""),
        _param("String", "supX1", "受けの単管の終わりの x", ""),
        _param("String", "supY1", "同 y", ""),
        _param("Length", "deckTop", "本足場の布板の上面（段の高さから。アンチはこの上に載る）", 0.0664),
        _param("Length", "railH1", "上桟の高さ（床から）", 0.95),
        _param("Length", "railH2", "中桟の高さ（床から）", 0.45),
        _param("Length", "toeH", "幅木の高さ", 0.15),
        _param("String", "cName", "名前（平面の注記）", "隅のつなぎ"),
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


def _parse_all(src: str, arr: str, cnt: str) -> str:
    """カンマ区切りの mm の並び（負の値・0 も）を配列 arr[1..cnt]（m）に."""
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
		{arr}[{cnt}] = v / 1000
	endif
endwhile
"""


SCRIPT_1D = ("﻿! 隅のつなぎ: 床の形・手すりの辺・段の高さを読む（m）\n"
             + _parse_all("polyX", "px", "nP") + _parse_all("polyY", "py", "nPy")
             + _parse_all("railE", "re", "nR") + _parse("levList", "lv", "nL", "/ 1000") + """if nPy < nP then nP = nPy
dim rl[]
for k = 1 to nP
	rl[k] = 0
next k
for k = 1 to nR
	ix = round_int(re[k] * 1000) + 1
	if ix >= 1 and ix <= nP then rl[ix] = 1
next k
if deckKind = 2 then
	dName = "足場板"
else
	dName = "アンチ"
endif
cx = 0
cy = 0
for k = 1 to nP
	cx = cx + px[k] / nP
	cy = cy + py[k] / nP
next k
! アンチを並べる基準: 最初の手すりの辺（外の辺）。辺の向き u・内向き（左）nI・中点・床の奥行き（辺から最も遠い点まで）
kR = 1
for k = nP to 1 step -1
	if rl[k] then kR = k
next k
kR2 = kR + 1
if kR2 > nP then kR2 = 1
eDx = px[kR2] - px[kR]
eDy = py[kR2] - py[kR]
eL = sqr(eDx * eDx + eDy * eDy)
if eL < 0.001 then eL = 0.001
ux = eDx / eL
uy = eDy / eL
mx = px[kR] + eDx / 2
my = py[kR] + eDy / 2
dep = 0
for k = 1 to nP
	dd = (px[k] - px[kR]) * (-uy) + (py[k] - py[kR]) * ux
	if dd > dep then dep = dd
next k
nPl = 1
if antiW > 0.01 then nPl = max(1, int(dep / antiW + 0.999))
if nPl > 8 then nPl = 8
if abs(eDx) < 0.000001 then
	eAng = 90 * sgn(eDy)
else
	eAng = atn(eDy / eDx)
	if eDx < 0 then eAng = eAng + 180
endif
pAng = eAng
"""
             + _parse_all("plkX", "qx", "nQx") + _parse_all("plkY", "qy", "nQy")
             + _parse_all("supX0", "s0x", "nS") + _parse_all("supY0", "s0y", "nS2")
             + _parse_all("supX1", "s1x", "nS3") + _parse_all("supY1", "s1y", "nS4")
             + _parse_all("plkL", "qL", "nQL") + _parse_all("fbX", "fx", "nF") + _parse_all("fbY", "fy", "nF2")
             + _parse_all("fbL", "fL", "nF3") + """nF = min(nF, min(nF2, nF3))
for i = 1 to nPl
	if i > nQL then qL[i] = antiL
next i
if nQy < nQx then nQx = nQy
if nQx > 0 then
	nPl = nQx
	pAng = plkAng
	for i = 1 to nPl
		if i > nQL then qL[i] = antiL
	next i
else
	for i = 1 to nPl
		qx[i] = mx - ux * antiL / 2 + (-uy) * antiW * (i - 1)
		qy[i] = my - uy * antiL / 2 + ux * antiW * (i - 1)
	next i
endif
nS = min(nS, min(nS2, min(nS3, nS4)))
""")

SCRIPT_2D = """﻿! 隅のつなぎ 2D: 床の形、手すりの辺（二重線）、床の向きの斜線、名前
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "cfT" "ＭＳ Ｐゴシック", texSiz, 5, 0
for k = 1 to nP
	k2 = k + 1
	if k2 > nP then k2 = 1
	line2 px[k], py[k], px[k2], py[k2]
	if rl[k] then
		dx = px[k2] - px[k]
		dy = py[k2] - py[k]
		L = sqr(dx * dx + dy * dy)
		if L > 0.001 then
			ox = dy / L * 0.05
			oy = -dx / L * 0.05
			line2 px[k] + ox, py[k] + oy, px[k2] + ox, py[k2] + oy
		endif
	endif
	hotspot2 px[k], py[k]
next k
! 床の範囲の目印（重心から各点へ短い線）
for k = 1 to nP
	line2 cx, cy, cx + (px[k] - cx) * 0.3, cy + (py[k] - cy) * 0.3
next k
! アンチ（外の辺に平行に、辺の中点から両側へ antiL/2）
for i = 1 to nPl
	add2 qx[i], qy[i]
	rot2 pAng
	rect2 0, 0, qL[i], antiW
	del 2
next i
! 受けの単管（破線）
for i = 1 to nS
	line_type "DASHED"
	line2 s0x[i], s0y[i], s1x[i], s1y[i]
	line_type 1
next i
style "cfT"
text2 cx, cy, cName + "（" + dName + str(antiL * 1000, 1, 0) + "×" + str(nPl, 1, 0) + "枚＋単管手すり）"
"""

SCRIPT_3D = """﻿! ============================================================
! 隅のつなぎ 3D（利用者の指定 2026-10-31: 三角の板じゃなく 900アンチを乗せる クランプもつけてね／高さがずれている 本足場の
! アンチの上に乗せるようにして クランプの詳細どあげて）
! - アンチ（antiL×antiW×deckT）: 下面＝段の高さ＋deckTop（本足場の布板の上面）。両側の本足場のアンチの上に重ねて載る
! - 受けの単管: 上面をアンチの下面にそろえ、隅のすき間の中だけに渡す。両端は本足場の端の布材に自在クランプ（交差）
! - 外の辺: 単管の上桟・中桟（支柱の外に 支柱半径＋単管半径 offR だけ出して添わせる。off は GDL の予約語で 3D が止まった）と幅木。両端の支柱に自在クランプ
! - 自在クランプ: 2つの抱き金具（単管を巻く帯・耳・T ボルトとナット）を回転軸のリベットでつないだ形
! ============================================================
resol 12
define material "cf_deck" 2, 0.72, 0.74, 0.78
define material "cf_steel" 2, 0.62, 0.62, 0.66
define material "cf_toe" 2, 0.55, 0.55, 0.58
define material "cf_clamp" 2, 0.50, 0.55, 0.66
define material "cf_bolt" 2, 0.30, 0.30, 0.32
define material "cf_wood" 2, 0.76, 0.60, 0.40
r = 0.0243
rP = 0.0243
offR = rP + r
zD = deckTop
for i = 1 to nL
	z = lv[i]
	! ---- アンチ（本足場のアンチの上に載る） ----
	material "cf_deck"
	for j = 1 to nPl
		add qx[j], qy[j], z + zD
		rotz pAng
		block qL[j], antiW - 0.005, deckT
		! 両端のつめ（受けの布材・単管に掛かる）
		add 0, 0.02, -0.02
		block 0.01, antiW - 0.045, 0.02
		del 1
		add qL[j] - 0.01, 0.02, -0.02
		block 0.01, antiW - 0.045, 0.02
		del 1
		del 2
	next j
	! ---- 残りのすき間をふさぐ足場板（斜めの受けとアンチの先の三角。アンチの先に 100 重ねて載せる） ----
	material "cf_wood"
	for j = 1 to nF
		add fx[j], fy[j], z + zD + deckT
		rotz pAng
		block fL[j], antiW - 0.01, 0.028
		del 2
	next j
	! ---- 受けの単管（すき間の中だけ）と、両端の自在クランプ（本足場の端の布材と交差） ----
	for j = 1 to nS
		dx = s1x[j] - s0x[j]
		dy = s1y[j] - s0y[j]
		L = sqr(dx * dx + dy * dy)
		if L > 0.05 then
			gosub "ang"
			material "cf_steel"
			add s0x[j], s0y[j], z + zD - r
			rotz ang
			roty 90
			addz -0.05
			cylind L + 0.1, r
			del 4
			for e = 0 to 1
				cX = s0x[j] + dx * e
				cY = s0y[j] + dy * e
				cZ = z + zD - r
				cA = ang
				cT = 2
				gosub "clamp"
			next e
		endif
	next j
	! ---- 外の辺: 単管の上桟・中桟（支柱に添わせて外へ offR）・幅木・両端の支柱に自在クランプ ----
	for k = 1 to nP
		if rl[k] then
			k2 = k + 1
			if k2 > nP then k2 = 1
			dx = px[k2] - px[k]
			dy = py[k2] - py[k]
			L = sqr(dx * dx + dy * dy)
			if L > 0.001 then
				gosub "ang"
				oX = dy / L * offR
				oY = -dx / L * offR
				for h = 1 to 2
					if h = 1 then
						zh = z + zD + deckT + railH1
					else
						zh = z + zD + deckT + railH2
					endif
					material "cf_steel"
					add px[k] + oX, py[k] + oY, zh
					rotz ang
					roty 90
					addz -0.3
					cylind L + 0.6, r
					del 4
					for e = 0 to 1
						cX = px[k] + dx * e + oX
						cY = py[k] + dy * e + oY
						cZ = zh
						cA = ang
						cT = 1
						gosub "clamp"
					next e
				next h
				material "cf_toe"
				add px[k], py[k], z + zD + deckT
				rotz ang
				addy -0.025
				block L, 0.025, toeH
				del 3
			endif
		endif
	next k
next i
end

"ang":
	if abs(dx) < 0.000001 then
		ang = 90 * sgn(dy)
	else
		ang = atn(dy / dx)
		if dx < 0 then ang = ang + 180
	endif
return

"clamp":
	! 自在クランプ: (cX, cY, cZ) を芯とする単管（向き cA）の抱き金具と、相手の抱き金具（cT=1: 支柱＝鉛直、内側 offR の所。
	! cT=2: 本足場の布材＝水平で下に offR、向きは単管に直角）を回転軸のリベットでつなぐ
	material "cf_clamp"
	add cX, cY, cZ
	rotz cA
	! 単管の抱き金具（帯 幅 50・耳・T ボルト＋ナット）
	roty 90
	addz -0.025
	cylind 0.05, r + 0.004
	del 2
	add -0.02, -0.004, r
	block 0.04, 0.008, 0.022
	del 1
	material "cf_bolt"
	add 0, 0.012, r + 0.014
	rotx 90
	cylind 0.03, 0.006
	resol 6
	addz 0.024
	cylind 0.01, 0.0105
	del 1
	resol 12
	del 2
	material "cf_clamp"
	if cT = 1 then
		! 支柱の抱き金具（鉛直の帯）と、2つをつなぐリベット
		add 0, offR, -0.025
		cylind 0.05, rP + 0.004
		del 1
		! リベット（2つの帯が接する所の回転軸。長さ 0 の円柱は描けないので、接点に短い軸を置く）
		add 0, r - 0.006, 0
		rotx -90
		cylind 0.012, 0.010
		del 2
		add 0.006, offR + rP, -0.02
		block 0.022, 0.008, 0.04
		del 1
		material "cf_bolt"
		add 0.017, offR + rP + 0.004, 0
		roty 90
		cylind 0.03, 0.006
		resol 6
		addz 0.024
		cylind 0.01, 0.0105
		del 1
		resol 12
		del 2
	else
		! 下の布材（単管に直角）の抱き金具と、2つをつなぐリベット
		add 0, -0.025, -offR
		rotx -90
		cylind 0.05, r + 0.004
		del 2
		add 0, 0, -r + 0.006
		rotx 180
		cylind 0.012, 0.010
		del 2
		material "cf_bolt"
		add 0.012, 0, -offR - r - 0.014
		roty 90
		cylind 0.03, 0.006
		del 2
	endif
	del 2
return
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text("﻿values{2} \"deckKind\" 1, \"アンチ\", 2, \"足場板\"\n", encoding="utf-8")
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
    print(f"ashiba_cfill: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
