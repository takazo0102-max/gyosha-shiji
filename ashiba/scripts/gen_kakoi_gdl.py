"""部品 ashiba_kakoi（仮囲い。線・ポリラインの1区間に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ」。

原点＝区間の始めの支柱の芯の地盤、+X＝区間の向き、−Y＝外（道路の側。パネル）、+Y＝敷地の中（控え）。斜めの辺は部品を回して置く。
支柱（単管 φ48.6）は postX、足元の地盤は postZ（原点の地盤から。高低差はここ）、横地（単管）は railZ の高さで支柱の外に
直交クランプ、パネルは runX の範囲に有効幅 pnW ずつ（1枚ずつ足元の地盤に合わせて上下）、横地にフックボルト・Jフック。
控えは brX の支柱に（支柱の高さ brH から後ろ brB の杭へ）、地上 300 にコロバシ。基礎 kkFound＝1 打込み・2 根巻き・3 H形鋼。
ゲートは gateX（始め,終わり の組）と gateK（1 パネルキャスターゲート・2 クロスゲート・3 パネルドア）。割付と数量・検定は
src/ashiba/hoarding.py、置くのは scripts/kakoi_run.py。
  python3 scripts/gen_kakoi_gdl.py     # gdl/hsf/ashiba_kakoi を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_kakoi"
MAIN_GUID = "8C3F2A61-4D7E-4B19-A5C2-7E9D0F3B6A48"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "kkType", "パネル（1＝安全鋼板・2＝フラットパネル・3＝防音パネル・4＝メッシュフェンス）", 1),
        _param("Length", "kkL", "区間の長さ", 10.8),
        _param("Length", "pnH", "パネルの高さ", 3.0),
        _param("Length", "pnW", "パネルの有効幅", 0.54),
        _param("Length", "lift", "パネルの下端（地盤から）", 0.2),
        _param("String", "postX", "支柱の位置（mm。始めから、カンマ区切り）", "0,1800,3600,5400,7200,9000,10800"),
        _param("String", "postZ", "支柱の足元の地盤（mm。原点の地盤から）", "0,0,0,0,0,0,0"),
        _param("String", "railZ", "横地の高さ（mm。地盤から）", "350,1700,3050"),
        _param("String", "runX", "パネルを張る範囲（mm。始め,終わり の組。角で延ばす・ゲートで切る）", "0,10800"),
        _param("String", "gateX", "ゲート（mm。始め,終わり の組）", ""),
        _param("String", "gateK", "ゲートの種類（1＝パネルキャスターゲート・2＝クロスゲート・3＝パネルドア）", ""),
        _param("String", "brX", "控えを掛ける支柱の位置（mm）", "0,1800,3600,5400,7200,9000,10800"),
        _param("Length", "brH", "控えを掛ける支柱の高さ（地盤から）", 1.9),
        _param("Length", "brB", "控えの杭の後ろ（支柱の芯から敷地の側へ）", 1.3),
        _param("Integer", "kkFound", "基礎（1＝単管の打込み・2＝根巻きコンクリート・3＝H形鋼）", 1),
        _param("Length", "embed", "打込みの根入れ", 1.0),
        _param("String", "kkName", "名前（平面の注記）", "仮囲い"),
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


SCRIPT_1D = ("﻿! 仮囲い: 支柱・地盤・横地・パネルの範囲・ゲート・控えを読む（m）\n"
             + _parse_all("postX", "px", "nP") + _parse_all("postZ", "pz", "nZ") + _parse_all("railZ", "rz", "nR")
             + _parse_all("runX", "ru", "nRu") + _parse_all("gateX", "gx", "nGx") + _parse_all("gateK", "gk", "nGk")
             + _parse_all("brX", "bq", "nBq") + """for i = nZ + 1 to nP
	pz[i] = 0
next i
for i = 1 to nGk
	gk[i] = round_int(gk[i] * 1000)
next i
r = 0.0243
ro = 0.0486
po = 0.0749
pt = 0.0012
if kkType = 3 then pt = 0.025
kkTop = lift + pnH
""")

SCRIPT_2D = """﻿! 仮囲い 2D: パネル（外）・横地・支柱・控え（中）・ゲート
pen penEquip
define style "kkT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "kkT"
for k = 1 to nRu - 1 step 2
	line2 ru[k], -po, ru[k + 1], -po
	line2 ru[k], -po - max(pt, 0.004), ru[k + 1], -po - max(pt, 0.004)
	line2 ru[k], -ro, ru[k + 1], -ro
next k
for i = 1 to nP
	circle2 px[i], 0, r
next i
for i = 1 to nBq
	line2 bq[i] - ro, 0, bq[i] - ro, brB
	line2 bq[i] + ro, 0, bq[i] + ro, brB
	circle2 bq[i], brB, r
next i
if kkFound = 3 then
	line2 0, -0.15, kkL, -0.15
	line2 0, 0.15, kkL, 0.15
	line2 0, brB - 0.15, kkL, brB - 0.15
	line2 0, brB + 0.15, kkL, brB + 0.15
endif
for k = 1 to nGx - 1 step 2
	gw = gx[k + 1] - gx[k]
	kd = 1
	if (k + 1) / 2 <= nGk then kd = gk[(k + 1) / 2]
	rect2 gx[k], -0.05, gx[k] + 0.1, 0.05
	rect2 gx[k + 1] - 0.1, -0.05, gx[k + 1], 0.05
	if kd = 3 then
		! 内開きのドア
		line2 gx[k] + 0.1, 0, gx[k] + 0.1, gw - 0.2
		arc2 gx[k] + 0.1, 0, gw - 0.2, 0, 90
	else
		! 引戸（キャスター・ジャバラ）
		line2 gx[k] + 0.1, 0.03, gx[k + 1] - 0.1, 0.03
		line2 gx[k] + 0.1, -0.03, gx[k + 1] - 0.1, -0.03
	endif
next k
text2 kkL / 2, -0.6, kkName
hotspot2 0, 0
hotspot2 kkL, 0
"""

SCRIPT_3D = """﻿! 仮囲い 3D（規格の寸法: 単管 φ48.6、直交クランプ 日建 ARC1 の口 幅40・帯4.5、安全鋼板 有効幅540 t1.2・フラットパネル 有効幅500、
! フックボルト φ8、控え・コロバシ・杭、根巻き 150×150×500、H形鋼 H-300×300×10×15）
define material "kk_steel" 2, 0.62, 0.64, 0.68
define material "kk_panel" 2, 0.90, 0.91, 0.90
define material "kk_flat" 2, 0.95, 0.95, 0.94
define material "kk_sound" 2, 0.78, 0.80, 0.78
define material "kk_clamp" 2, 0.85, 0.70, 0.30
define material "kk_conc" 2, 0.70, 0.70, 0.68
define material "kk_mesh" 0, 0.55, 0.58, 0.60, 0.6, 0.6, 0.1, 0.8, 5, 0, 1, 1, 1, 0, 0, 0, 0
define material "kk_gate" 2, 0.35, 0.55, 0.75
rN = 12
resol rN
clW = 0.040
clT = 0.0045
material "kk_steel"
! ---- 支柱（打込みは根入れ、H形鋼は上のフランジから） ----
for i = 1 to nP
	z0 = pz[i]
	zb = z0
	if kkFound = 1 then zb = z0 - embed
	if kkFound = 3 then zb = z0 + 0.3
	add px[i], 0, zb
	cylind kkTop + 0.05 - (zb - z0), r
	del 1
	if kkFound = 2 then
		material "kk_conc"
		add px[i] - 0.075, -0.075, z0 - 0.45
		block 0.15, 0.15, 0.5
		del 1
		material "kk_steel"
	endif
next i
! ---- 横地（支柱の外。地盤に沿って流す）と直交クランプ ----
for k = 1 to nRu - 1 step 2
	a0 = ru[k]
	a1 = ru[k + 1]
	for j = 1 to nR
		xq = a0
		gosub "gz"
		x0q = a0
		z0q = zq + rz[j]
		for i = 1 to nP + 1
			xn = a1
			if i <= nP then xn = px[i]
			if xn > x0q + 0.001 and xn <= a1 + 0.001 then
				xq = xn
				gosub "gz"
				x1q = xn
				z1q = zq + rz[j]
				yq = -ro
				rq = r
				gosub "tube"
				x0q = x1q
				z0q = z1q
			endif
		next i
	next j
	for i = 1 to nP
		if px[i] >= a0 - 0.001 and px[i] <= a1 + 0.001 then
			for j = 1 to nR
				add px[i], 0, pz[i] + rz[j]
				clDy = ro
				gosub "orth"
				del 1
			next j
		endif
	next i
next k
! ---- パネル（1枚ずつ足元の地盤に合わせる）とフックボルト ----
for k = 1 to nRu - 1 step 2
	a0 = ru[k]
	a1 = ru[k + 1]
	x0 = a0
	while x0 < a1 - 0.005 do
		x1 = min(a1, x0 + pnW)
		xq = (x0 + x1) / 2
		gosub "gz"
		zp = zq + lift
		if kkType = 4 then
			! メッシュフェンス: φ32 の枠と金網
			material "kk_steel"
			add x0 + 0.016, -po - 0.016, zp
			cylind pnH, 0.016
			del 1
			add x1 - 0.016, -po - 0.016, zp
			cylind pnH, 0.016
			del 1
			for e = 0 to 1
				add x0, -po - 0.016, zp + 0.016 + e * (pnH - 0.032)
				roty 90
				cylind x1 - x0, 0.016
				del 2
			next e
			material "kk_mesh"
			add x0 + 0.03, -po - 0.018, zp + 0.03
			block x1 - x0 - 0.06, 0.004, pnH - 0.06
			del 1
		else
			material "kk_panel"
			if kkType = 2 then material "kk_flat"
			if kkType = 3 then material "kk_sound"
			add x0 + 0.001, -po - pt, zp
			block x1 - x0 - 0.002, pt, pnH
			del 1
			if kkType = 1 then
				! 安全鋼板のリブ（外へ 12・幅 30。見た目）
				for e = 1 to 2
					xr = x0 + (x1 - x0) * e / 3
					add xr - 0.015, -po - pt - 0.012, zp
					block 0.03, 0.012, pnH
					del 1
				next e
			else
				! フラットパネルの縁（重ね）
				add x1 - 0.012, -po - pt - 0.008, zp
				block 0.012, 0.008, pnH
				del 1
			endif
			! フックボルト（φ8・横地に掛けてナット）: 横地ごとに2本
			material "kk_steel"
			for j = 1 to nR
				for e = 0 to 1
					xb = x0 + 0.1 + e * (x1 - x0 - 0.2)
					if x1 - x0 < 0.25 then xb = (x0 + x1) / 2
					xq = xb
					gosub "gz"
					add xb, -po - pt - 0.012, zq + rz[j] - 0.03
					rotx -90
					cylind po + pt + 0.012 - ro, 0.004
					resol 6
					cylind 0.008, 0.008
					resol rN
					del 2
				next e
			next j
		endif
		material "kk_steel"
		x0 = x1
	endwhile
next k
! ---- 控え・コロバシ・杭（敷地の側。自在クランプ） ----
bL = sqr(brH ^ 2 + brB ^ 2)
for i = 1 to nBq
	xq = bq[i]
	gosub "gz"
	zg = zq
	add bq[i] - ro, 0, zg + brH
	rotx -(90 + atn(brH / brB))
	cylind bL, r
	del 2
	add bq[i] + ro, 0, zg + 0.3
	rotx -90
	cylind brB + 0.05, r
	del 2
	if kkFound = 1 then
		add bq[i], brB, zg - 1.15
		cylind 1.5, r
		del 1
	endif
	if kkFound = 2 then
		material "kk_conc"
		add bq[i] - 0.075, brB - 0.075, zg - 0.45
		block 0.15, 0.15, 0.5
		del 1
		material "kk_steel"
		add bq[i], brB, zg
		cylind 0.35, r
		del 1
	endif
	if kkFound = 3 then
		add bq[i], brB, zg + 0.3
		cylind 0.35, r
		del 1
	endif
	material "kk_clamp"
	for e = 1 to 4
		yc = 0.03
		zc = zg + brH - 0.04
		if e = 2 then zc = zg + 0.3
		if e > 2 then yc = brB - 0.07
		if e = 3 then zc = zg + 0.07
		if e = 4 then zc = zg + 0.3
		add bq[i] - 0.03, yc, zc - 0.025
		block 0.06, 0.04, 0.05
		del 1
	next e
	material "kk_steel"
next i
! ---- H形鋼の基礎（2列。支柱の下と控えの杭の下）とキャッチクランプ ----
if kkFound = 3 then
	for e = 0 to 1
		yh = e * brB
		for i = 1 to nP - 1
			x0q = px[i]
			x1q = px[i + 1]
			z0q = pz[i]
			z1q = pz[i + 1]
			dxq = x1q - x0q
			if dxq > 0.001 then
				add x0q, yh, z0q
				roty -atn((z1q - z0q) / dxq)
				lq = sqr(dxq ^ 2 + (z1q - z0q) ^ 2)
				add 0, -0.15, 0
				block lq, 0.3, 0.015
				addz 0.285
				block lq, 0.3, 0.015
				del 1
				add 0, 0.145, 0.015
				block lq, 0.01, 0.27
				del 4
			endif
		next i
	next e
	material "kk_clamp"
	for i = 1 to nP
		for e = -1 to 1 step 2
			add px[i] + e * 0.06 - 0.025, -0.03, pz[i] + 0.3
			block 0.05, 0.06, 0.05
			del 1
		next e
	next i
	material "kk_steel"
endif
! ---- ゲート ----
for k = 1 to nGx - 1 step 2
	g0 = gx[k]
	g1 = gx[k + 1]
	gw = g1 - g0
	kd = 1
	if (k + 1) / 2 <= nGk then kd = gk[(k + 1) / 2]
	xq = (g0 + g1) / 2
	gosub "gz"
	zg = zq
	gh = kkTop
	if kd = 2 then gh = 1.8
	if kd = 3 then gh = 2.0
	material "kk_gate"
	! 門柱 □100
	add g0, -0.05, zg
	block 0.1, 0.1, kkTop + 0.05
	del 1
	add g1 - 0.1, -0.05, zg
	block 0.1, 0.1, kkTop + 0.05
	del 1
	if kd = 1 then
		! パネルキャスターゲート（引戸 2枚。枠 □50・パネル・キャスター）
		for e = 0 to 1
			l0 = g0 + 0.1 + e * (gw - 0.2) / 2
			lw = (gw - 0.2) / 2
			add l0, -0.025, zg + 0.1
			block lw, 0.05, 0.05
			addz gh - 0.15
			block lw, 0.05, 0.05
			del 1
			block 0.05, 0.05, gh - 0.1
			addx lw - 0.05
			block 0.05, 0.05, gh - 0.1
			del 2
			material "kk_flat"
			add l0 + 0.05, -0.002, zg + 0.15
			block lw - 0.1, 0.004, gh - 0.2
			del 1
			material "kk_steel"
			for c = 0 to 1
				add l0 + 0.08 + c * (lw - 0.16), -0.04, zg + 0.05
				rotx -90
				cylind 0.08, 0.05
				del 2
			next c
			material "kk_gate"
		next e
	endif
	if kd = 2 then
		! クロスゲート（ジャバラ。上下の枠と X の格子）
		add g0 + 0.1, -0.02, zg + 0.1
		block gw - 0.2, 0.04, 0.04
		addz gh - 0.14
		block gw - 0.2, 0.04, 0.04
		del 2
		nc = max(1, ceil((gw - 0.2) / 0.3))
		cw = (gw - 0.2) / nc
		for c = 1 to nc
			xa = g0 + 0.1 + (c - 1) * cw
			for e = 0 to 1
				x0q = xa
				x1q = xa + cw
				z0q = zg + 0.14 + e * (gh - 0.18)
				z1q = zg + 0.14 + (1 - e) * (gh - 0.18)
				yq = 0
				rq = 0.008
				gosub "tube"
			next e
		next c
	endif
	if kd = 3 then
		! パネルドア（内開き）
		add g0 + 0.1, -0.025, zg + 0.05
		block gw - 0.2, 0.05, 0.05
		addz gh - 0.1
		block gw - 0.2, 0.05, 0.05
		del 1
		block 0.05, 0.05, gh - 0.05
		addx gw - 0.25
		block 0.05, 0.05, gh - 0.05
		del 2
		material "kk_flat"
		add g0 + 0.15, -0.002, zg + 0.1
		block gw - 0.3, 0.004, gh - 0.15
		del 1
		material "kk_steel"
		add g1 - 0.25, -0.06, zg + 1.0
		rotx -90
		cylind 0.12, 0.01
		del 2
	endif
	material "kk_steel"
next k
end

"gz":
	! xq の地盤（支柱の足元の間を直線で）
	zq = 0
	if nP > 0 then
		zq = pz[1]
		if xq >= px[nP] then zq = pz[nP]
		for jj = 1 to nP - 1
			if xq >= px[jj] and xq <= px[jj + 1] then zq = pz[jj] + (pz[jj + 1] - pz[jj]) * (xq - px[jj]) / max(0.001, px[jj + 1] - px[jj])
		next jj
	endif
	return

"tube":
	! (x0q, yq, z0q) から (x1q, yq, z1q) の管（x1q > x0q）
	dxq = x1q - x0q
	lq = sqr(dxq ^ 2 + (z1q - z0q) ^ 2)
	if lq > 0.001 then
		add x0q, yq, z0q
		roty 90 - atn((z1q - z0q) / max(0.0001, dxq))
		cylind lq, rq
		del 2
	endif
	return

"jaw":
	! クランプの口1つ（日建 ARC1 の形・規格の寸法。管は X 向きで芯が原点、半径 jR。相手の口は −Y 側）
	material "kk_clamp"
	rotx 90
	revolve 4, 180, 63, -clW / 2, jR, 0, clW / 2, jR, 0, clW / 2, jR + clT, 0, -clW / 2, jR + clT, 0
	del 1
	add -clW / 2, -(jR + clT + 0.004), -clW / 2
	block clW, 0.004, clW
	del 1
	add -clW / 2, 0, jR + clT + 0.0035
	roty 90
	cylind clW, 0.0045
	del 2
	rotx -90
	revolve 4, 180, 63, -clW / 2, jR, 0, clW / 2, jR, 0, clW / 2, jR + clT, 0, -clW / 2, jR + clT, 0
	del 1
	add 0, -0.012, -(jR + clT + 0.008)
	rotx -90
	cylind 0.044, 0.005
	addz 0.019
	resol 6
	cylind 0.010, 0.0095
	resol rN
	del 3
	material "kk_steel"
	return

"orth":
	! 直交クランプ（日建 兼用直交クランプ ARC1）: 原点＝柱の芯（Z 向き）、管は +X 向きで芯は y = −clDy
	roty -90
	jR = r
	gosub "jaw"
	del 1
	add 0, -clDy, 0
	rotz 180
	jR = r
	gosub "jaw"
	del 2
	return
"""


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
    print(f"ashiba_kakoi: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
