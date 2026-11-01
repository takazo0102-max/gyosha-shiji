"""部品 ashiba_kodai（乗入れ構台・荷取り構台。1つの構台に1部品）の HSF を書き出す.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の2番。割付と検定は src/ashiba/kodai.py（出典はそちら）、置くのは
scripts/kodai_run.py。原点＝構台の床の隅の地盤（GL）、+X＝進行方向、+Y＝幅。床の上端は zTop。
- 覆工板（高さ 208）を X に 1m・Y に 2m の列で並べ、幅の端数に 3m を混ぜる（dk3＝3m の列の数・−1 は自動で奇数 m なら1列、
  dk3At＝手前から何列目。利用者の指定 2026-11-01: 全部が 3m じゃないよ 1列だけだよね）。根太（secJ）は列の境目ごとに X へ通す
- 大引（secG）は支柱の列ごとに Y へ、支柱（secP）は縁から ovh の内側を spMax 以内で等分した格子、根切り底（−dig）から根入れ emb。
  H形鋼は H-200〜H-594 の10種類を一覧で（kodai.H_SECTIONS。利用者の指定 2026-11-01: H鋼の種類も）
- 支柱の列（gX1〜16）・行（gY1〜8）は平面の外の丸い印のホットスポットで、水平つなぎの段（lvD1〜8）は 3D の隅の支柱の外の
  ホットスポットで動かせる（利用者の指定 2026-11-01: こうだいくいと腹起こし 大引きのホットスポットで位置変更できるように）。
  動かすとパラメータスクリプトが gAuto・lAuto（自動で等分）を外す
- 水平つなぎ（[-200×90）は大引のすぐ下から tieP 以内で等分し根切り底の 300 上まで、垂直ブレース（L-75）は外周の構面に X 形
- 手すり 950・中さん 450・幅木 150 を railS・railN・railE・railW の辺に、入口（X0）にスロープ 1/slopeN（zTop が 50 を超えるとき）
- 広さ lenX・lenY は平面のホットスポットで引き、パラメータスクリプトが X は 1m、Y は覆工板の列の組み合わせに切り上げる
  python3 scripts/gen_kodai_gdl.py     # gdl/hsf/ashiba_kodai を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from ashiba.kodai import H_SECTIONS, MAX_GX, MAX_GY, MAX_LV  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_kodai"
MAIN_GUID = "4B7D2E19-8C3A-4F61-9E05-A2D6C8B1F374"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "dk3", "3m の覆工板の列の数（−1＝自動: 幅が奇数 m なら1列。残りは 2m）", -1),
        _param("Integer", "dk3At", "3m の列の位置（手前から何列目）", 1),
        _param("Length", "spMax", "支柱の間隔の上限", 6.0),
        _param("Length", "ovh", "張出し（縁から支柱まで）", 1.0),
        _param("Length", "lenX", "長さ X（進行方向。ホットスポットで引く。1m の倍数に切り上げる）", 30.0),
        _param("Length", "lenY", "幅 Y（同上。覆工板の長さの倍数に）", 8.0),
        _param("Length", "zTop", "床の上端（地盤から）", 0.5),
        _param("Length", "dig", "根切り底（地盤から下へ）", 6.3),
        _param("Length", "emb", "支柱の根入れ（根切り底から下へ）", 4.7),
        _param("Integer", "secJ", "根太の H形鋼（一覧で選ぶ）", 5),
        _param("Integer", "secG", "大引の H形鋼（一覧で選ぶ）", 5),
        _param("Integer", "secP", "支柱（構台杭）の H形鋼（一覧で選ぶ）", 4),
        _param("Length", "tieP", "水平つなぎの段の間隔の上限", 3.0),
        _param("RealNum", "slopeN", "スロープの勾配 1/n（0＝なし。入口 X0 の側）", 8.0),
        _param("Boolean", "railS", "手すり 手前（Y0）", 1),
        _param("Boolean", "railN", "手すり 奥（Y 最大）", 1),
        _param("Boolean", "railE", "手すり 先（X 最大）", 1),
        _param("Boolean", "railW", "手すり 入口（X0）", 0),
        _param("Boolean", "showDeck", "覆工板を 3D に描く", 1),
        _param("Boolean", "gAuto", "支柱の列・行を自動で等分（ホットスポットで動かすと外れる）", 1),
        _param("Integer", "nGX", "支柱の列の数（X。2〜16）", 4),
        *[_param("Length", f"gX{i}", f"支柱の列 {i} の X（大引も）", 0.0) for i in range(1, MAX_GX + 1)],
        _param("Integer", "nGY", "支柱の行の数（Y。2〜8）", 2),
        *[_param("Length", f"gY{j}", f"支柱の行 {j} の Y", 0.0) for j in range(1, MAX_GY + 1)],
        _param("Boolean", "lAuto", "水平つなぎの段を自動で（3D のホットスポットで動かすと外れる）", 1),
        _param("Integer", "nLvP", "水平つなぎの段の数（1〜8）", 3),
        *[_param("Length", f"lvD{k}", f"水平つなぎ {k} 段目（床の上端から下へ）", 0.0) for k in range(1, MAX_LV + 1)],
        _param("String", "kdVeh", "重機（検定用。T25・R20・R25・R40・R65・C50）", "R25"),
        _param("RealNum", "kdLoad", "吊荷 t（検定用）", 3.0),
        _param("RealNum", "kdN", "支柱の先の N 値（検定用）", 20.0),
        _param("String", "kdName", "名前（注記）", "構台"),
        _param("String", "maxLd", "最大積載荷重の注記", "最大積載荷重 28.6t"),
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


def _master() -> str:
    n = len(H_SECTIONS)
    sec = [f"dim secH[{n}], secB[{n}], secW[{n}], secF[{n}]"]
    for i, (h, b, tw, tf, *_r) in enumerate(H_SECTIONS.values(), 1):
        sec += [f"secH[{i}] = {h / 1000:.3f}", f"secB[{i}] = {b / 1000:.3f}", f"secW[{i}] = {tw / 1000:.3f}",
                f"secF[{i}] = {tf / 1000:.4f}"]
    gx = [f"px0[{i}] = gX{i}" for i in range(1, MAX_GX + 1)]
    gy = [f"py0[{j}] = gY{j}" for j in range(1, MAX_GY + 1)]
    lz = [f"lz0[{k}] = lvD{k}" for k in range(1, MAX_LV + 1)]
    return ("﻿! 乗入れ構台: 割付（src/ashiba/kodai.py の layout と同じ）。H形鋼は kodai.H_SECTIONS の並び\n" + "\n".join(sec) + f"""
kJ = max(1, min({n}, secJ))
kG = max(1, min({n}, secG))
kP = max(1, min({n}, secP))
dkH = 0.208
! 広さ（X は 1m、Y は覆工板の長さの倍数）
nDX = max(1, ceil(lenX - 0.02))
lx = nDX
! 覆工板の列（Y の手前から。2m が基本、幅の端数に 3m。kodai.deck_rows と同じ）
if dk3 < 0 then
	wm = max(2, ceil(lenY - 0.02))
	n3 = wm - 2 * int(wm / 2)
	n2 = (wm - 3 * n3) / 2
else
	n3 = dk3
	n2 = max(0, ceil((lenY - 3 * n3) / 2 - 0.01))
	if n2 + n3 = 0 then n2 = 1
endif
nDY = n2 + n3
k3 = max(1, min(dk3At, n2 + 1))
dim rw[], ry[]
ry[1] = 0
for j = 1 to nDY
	rw[j] = 2
	if j >= k3 and j < k3 + n3 then rw[j] = 3
	ry[j + 1] = ry[j] + rw[j]
next j
ly = ry[nDY + 1]
! 支柱の格子の自動（縁から ovh の内側を spMax 以内で等分）
spM = max(1, spMax)
inX = max(lx - 2 * ovh, 0)
inY = max(ly - 2 * ovh, 0)
nBX = min({MAX_GX - 1}, max(1, ceil(inX / spM - 0.000001)))
nBY = min({MAX_GY - 1}, max(1, ceil(inY / spM - 0.000001)))
nAX = nBX + 1
nAY = nBY + 1
dim axp[{MAX_GX}], ayp[{MAX_GY}]
for i = 1 to nAX
	axp[i] = ovh + inX * (i - 1) / nBX
next i
for j = 1 to nAY
	ayp[j] = ovh + inY * (j - 1) / nBY
next j
! 使う列・行（自動か、ホットスポットで動かした gX・gY）。並べ替えて gx・gy に
dim px0[{MAX_GX}], py0[{MAX_GY}]
""" + "\n".join(gx + gy) + f"""
dim gx[], gy[]
if gAuto then
	nPX = nAX
	nPY = nAY
	for i = 1 to nPX
		gx[i] = axp[i]
	next i
	for j = 1 to nPY
		gy[j] = ayp[j]
	next j
else
	nPX = max(2, min({MAX_GX}, nGX))
	nPY = max(2, min({MAX_GY}, nGY))
	for i = 1 to nPX
		gx[i] = max(0, min(lx, px0[i]))
	next i
	for j = 1 to nPY
		gy[j] = max(0, min(ly, py0[j]))
	next j
endif
for i = 2 to nPX
	for m = i to 2 step -1
		if gx[m] < gx[m - 1] then
			tq = gx[m]
			gx[m] = gx[m - 1]
			gx[m - 1] = tq
		endif
	next m
next i
for j = 2 to nPY
	for m = j to 2 step -1
		if gy[m] < gy[m - 1] then
			tq = gy[m]
			gy[m] = gy[m - 1]
			gy[m - 1] = tq
		endif
	next m
next j
nBX = nPX - 1
nBY = nPY - 1
! 高さ: 床の上端 zTop → 覆工板 → 根太 → 大引 → 支柱の天端
zJt = zTop - dkH
zGt = zJt - secH[kJ]
zPt = zGt - secH[kG]
zPb = -dig - emb
! 水平つなぎの段の自動（大引のすぐ下から tieP 以内で等分、一番下は根切り底の 300 上。床の上端から下へ m）
dim alp[{MAX_LV}]
zLast = -dig + 0.3
nAL = 1
alp[1] = zTop - zPt
if zPt - zLast > 0.3 then
	nTier = min({MAX_LV - 1}, max(1, ceil((zPt - zLast) / max(0.5, tieP) - 0.000001)))
	for k = 1 to nTier + 1
		alp[k] = zTop - (zPt - (zPt - zLast) * (k - 1) / nTier)
	next k
	nAL = nTier + 1
endif
dim lz0[{MAX_LV}]
""" + "\n".join(lz) + f"""
dim lv[]
nLv = nAL
if lAuto = 0 then nLv = max(1, min({MAX_LV}, nLvP))
for k = 1 to nLv
	if lAuto then
		lv[k] = zTop - alp[k]
	else
		lv[k] = zTop - max(0, lz0[k])
	endif
next k
for k = 2 to nLv
	for m = k to 2 step -1
		if lv[m] > lv[m - 1] then
			tq = lv[m]
			lv[m] = lv[m - 1]
			lv[m - 1] = tq
		endif
	next m
next k
! スロープ（入口 X0 の側）
slL = 0
if slopeN > 0.5 and zTop > 0.05 then slL = zTop * slopeN
""")


def _vl() -> str:
    names = ", ".join(f'{i}, "{k}×{v[1]:.0f}"' for i, (k, v) in enumerate(H_SECTIONS.items(), 1))
    wx = ", ".join(f"gX{i} = axp[{i}]" for i in range(1, MAX_GX + 1))
    wy = ", ".join(f"gY{j} = ayp[{j}]" for j in range(1, MAX_GY + 1))
    wl = ", ".join(f"lvD{k} = alp[{k}]" for k in range(1, MAX_LV + 1))
    return f"""﻿! 乗入れ構台: ホットスポットで引いた広さを切り上げ、自動の支柱の列・行と水平つなぎの段を書き込む。
! 支柱・水平つなぎのホットスポットを動かすと（GLOB_MODPAR_NAME）自動を外し、動かした位置のままにする
if abs(lenX - lx) > 0.0005 then parameters lenX = lx
if abs(lenY - ly) > 0.0005 then parameters lenY = ly
mp = GLOB_MODPAR_NAME
gA = gAuto
if strstr(mp, "gX") = 1 or strstr(mp, "gY") = 1 or mp = "nGX" or mp = "nGY" then
	gA = 0
	parameters gAuto = 0
endif
if gA then
	parameters nGX = nAX, nGY = nAY
	parameters {wx}
	parameters {wy}
endif
lA = lAuto
if strstr(mp, "lvD") = 1 or mp = "nLvP" then
	lA = 0
	parameters lAuto = 0
endif
if lA then
	parameters nLvP = nAL
	parameters {wl}
endif
values{{2}} "dk3" -1, "自動（幅が奇数 m なら 3m を1列）", 0, "2m だけ", 1, "3m を1列", 2, "3m を2列"
values "dk3At" range [1, 20]
values{{2}} "secJ" {names}
values{{2}} "secG" {names}
values{{2}} "secP" {names}
values "nGX" range [2, {MAX_GX}]
values "nGY" range [2, {MAX_GY}]
values "nLvP" range [1, {MAX_LV}]
values "kdVeh" "T25", "R20", "R25", "R40", "R65", "C50"
values "spMax" range [1.0, 12.0]
values "slopeN" 0, range [6, 20]
"""


SCRIPT_2D = """﻿! 乗入れ構台 2D: 床の外形・覆工板の目地・支柱・手すり・スロープ・注記・広げるホットスポット
pen penEquip
define style "kdT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "kdT"
! 覆工板の目地（X に 1m・Y に覆工板の長さ）
for i = 1 to nDX - 1
	line2 i, 0, i, ly
next i
for j = 1 to nDY - 1
	line2 0, ry[j + 1], lx, ry[j + 1]
next j
rect2 0, 0, lx, ly
! 支柱（H 形。フランジは X の両側に、幅は Y に。3D と同じ）
hp = secH[kP] / 2
bp = secB[kP] / 2
fp = secF[kP]
wp = secW[kP] / 2
for i = 1 to nPX
	for j = 1 to nPY
		rect2 gx[i] + hp - fp, gy[j] - bp, gx[i] + hp, gy[j] + bp
		rect2 gx[i] - hp, gy[j] - bp, gx[i] - hp + fp, gy[j] + bp
		rect2 gx[i] - hp + fp, gy[j] - wp, gx[i] + hp - fp, gy[j] + wp
	next j
next i
! 手すり（縁の内側 50）
if railS then line2 0, 0.05, lx, 0.05
if railN then line2 0, ly - 0.05, lx, ly - 0.05
if railE then line2 lx - 0.05, 0, lx - 0.05, ly
if railW then line2 0.05, 0, 0.05, ly
! スロープ（入口の側）と上る向きの矢
if slL > 0 then
	rect2 -slL, 0, 0, ly
	line2 -slL * 0.8, ly / 2, -slL * 0.2, ly / 2
	line2 -slL * 0.2, ly / 2, -slL * 0.2 - 0.4, ly / 2 + 0.25
	line2 -slL * 0.2, ly / 2, -slL * 0.2 - 0.4, ly / 2 - 0.25
	add2 -slL / 2, ly / 2 + 0.6
	rot2 -SYMB_ROTANGLE
	text2 0, 0, "スロープ 1/" + str(slopeN, 1, 0)
	del 2
endif
! 注記（名前・広さ・最大積載荷重。図面の向きに関係なく水平に）
add2 lx / 2, ly / 2
rot2 -SYMB_ROTANGLE
text2 0, 0.6, kdName + " " + str(lx, 1, 0) + "×" + str(ly, 1, 0) + "m"
t3 = ""
if n3 > 0 then t3 = "・1×3m " + str(nDX * n3, 1, 0) + "枚"
text2 0, 0, "覆工板 1×2m " + str(nDX * n2, 1, 0) + "枚" + t3
text2 0, -0.6, maxLd
del 2
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

SCRIPT_3D = """﻿! 乗入れ構台 3D
define material "kd_deck" 2, 0.36, 0.37, 0.38
define material "kd_steel" 2, 0.55, 0.42, 0.30
define material "kd_brace" 2, 0.45, 0.47, 0.50
define material "kd_rail" 2, 0.90, 0.75, 0.10
define material "kd_toe" 2, 0.85, 0.85, 0.85
define material "kd_slope" 2, 0.62, 0.60, 0.56
resol 8
! ---- 覆工板 ----
if showDeck then
	material "kd_deck"
	for i = 1 to nDX
		for j = 1 to nDY
			add (i - 1) + 0.003, ry[j] + 0.003, zJt
			block 1 - 0.006, rw[j] - 0.006, dkH
			del 1
		next j
	next i
endif
material "kd_steel"
! ---- 根太（X に通す。覆工板の長さごと）----
hh = secH[kJ]
hb = secB[kJ]
htw = secW[kJ]
htf = secF[kJ]
for j = 1 to nDY + 1
	yj = max(hb / 2, min(ly - hb / 2, ry[j]))
	add 0, yj, zGt
	hL = lx
	gosub "hbeam"
	del 1
next j
! ---- 大引（支柱の列ごとに Y へ）----
hh = secH[kG]
hb = secB[kG]
htw = secW[kG]
htf = secF[kG]
for i = 1 to nPX
	add gx[i], 0, zPt
	rotz 90
	hL = ly
	gosub "hbeam"
	del 2
next i
! ---- 支柱 ----
hh = secH[kP]
hb = secB[kP]
htw = secW[kP]
htf = secF[kP]
for i = 1 to nPX
	for j = 1 to nPY
		add gx[i], gy[j], zPb
		roty -90
		add 0, 0, -hh / 2
		hL = zPt - zPb
		gosub "hbeam"
		del 3
	next j
next i
! ---- 水平つなぎ（[-200×90。支柱の外の面に）----
material "kd_brace"
pY = secB[kP] / 2
pX = secH[kP] / 2
for k = 1 to nLv
	for j = 1 to nPY
		add gx[1], gy[j] + pY, lv[k] - 0.2
		block gx[nPX] - gx[1], 0.09, 0.2
		del 1
	next j
	for i = 1 to nPX
		add gx[i] + pX, gy[1], lv[k] - 0.2
		block 0.09, gy[nPY] - gy[1], 0.2
		del 1
	next i
next k
! ---- 垂直ブレース（L-75。外周の構面に X 形）----
if nLv > 1 then
	for k = 1 to nLv - 1
		zH = lv[k] - 0.2
		zL = lv[k + 1]
		dz = max(0.05, zH - zL)
		for i = 1 to nBX
			dx = max(0.05, gx[i + 1] - gx[i])
			bl = sqr(dx * dx + dz * dz)
			ang = atn(dz / dx)
			for s = 0 to 1
				yb = gy[1] - pY - 0.08
				if s = 1 then yb = gy[nPY] + pY + 0.09
				add gx[i], yb, zL
				roty -ang
				block bl, 0.075, 0.075
				del 2
				add gx[i], yb, zH
				roty ang
				block bl, 0.075, 0.075
				del 2
			next s
		next i
		for j = 1 to nBY
			dy = max(0.05, gy[j + 1] - gy[j])
			bl = sqr(dy * dy + dz * dz)
			ang = atn(dz / dy)
			for s = 0 to 1
				xb = gx[1] - pX - 0.08
				if s = 1 then xb = gx[nPX] + pX + 0.09
				add xb, gy[j], zL
				rotz 90
				roty -ang
				block bl, 0.075, 0.075
				del 3
				add xb, gy[j], zH
				rotz 90
				roty ang
				block bl, 0.075, 0.075
				del 3
			next s
		next j
	next k
endif
! ---- 手すり・中さん・幅木（縁の内側 50）----
for e = 1 to 4
	onE = 0
	if e = 1 and railS then onE = 1
	if e = 2 and railN then onE = 1
	if e = 3 and railE then onE = 1
	if e = 4 and railW then onE = 1
	if onE then
		eL = lx
		ex = 0
		ey = 0.05
		er = 0
		if e = 2 then ey = ly - 0.05
		if e > 2 then
			eL = ly
			ey = 0
			er = 90
			ex = 0.05
			if e = 3 then ex = lx - 0.05
		endif
		add ex, ey, zTop
		rotz er
		nRp = max(1, ceil(eL / 1.8 - 0.000001))
		material "kd_rail"
		for r = 0 to nRp
			add eL * r / nRp, 0, 0
			cylind 1.0, 0.0243
			del 1
		next r
		for t = 1 to 2
			hz = 0.95
			if t = 2 then hz = 0.45
			add 0, 0, hz
			roty 90
			cylind eL, 0.0243
			del 2
		next t
		material "kd_toe"
		add 0, -0.0125, 0
		block eL, 0.025, 0.15
		del 1
		del 2
	endif
next e
! ---- スロープ（入口 X0 の側。下は盛土かコンクリート）----
if slL > 0 then
	material "kd_slope"
	add -slL, ly, 0
	rotx 90
	prism 3, ly, 0, 0, slL, zTop, slL, 0
	del 2
endif
end

! H 形鋼: 今の座標で +X に長さ hL、Y の真ん中、下端 z＝0（hh・hb・htw・htf）
"hbeam":
	add 0, -hb / 2, 0
	block hL, hb, htf
	add 0, (hb - htw) / 2, htf
	block hL, htw, hh - 2 * htf
	del 1
	add 0, 0, hh - htf
	block hL, hb, htf
	del 2
return
"""


def _hot2d() -> str:
    """支柱の列（X）は床の手前の外 0.6 に、行（Y）は先の外 0.6 に丸い印とホットスポット。引くとその列・行の支柱と大引が動く."""
    out = ["! 支柱の列・行を動かすホットスポット（列は手前の外、行は先の外の丸い印）"]
    for i in range(1, MAX_GX + 1):
        b = 200 + 3 * i
        out += [f"if nPX >= {i} then", f"\tcircle2 max(0, min(lx, gX{i})), -0.6, 0.12",
                f"\tline2 max(0, min(lx, gX{i})), -0.48, max(0, min(lx, gX{i})), 0",
                f"\thotspot2 0, -0.6, {b}, gX{i}, 1 + 128", f"\thotspot2 gX{i}, -0.6, {b + 1}, gX{i}, 2",
                f"\thotspot2 -1, -0.6, {b + 2}, gX{i}, 3", "endif"]
    for j in range(1, MAX_GY + 1):
        b = 300 + 3 * j
        out += [f"if nPY >= {j} then", f"\tcircle2 lx + 0.6, max(0, min(ly, gY{j})), 0.12",
                f"\tline2 lx + 0.48, max(0, min(ly, gY{j})), lx, max(0, min(ly, gY{j}))",
                f"\thotspot2 lx + 0.6, 0, {b}, gY{j}, 1 + 128", f"\thotspot2 lx + 0.6, gY{j}, {b + 1}, gY{j}, 2",
                f"\thotspot2 lx + 0.6, -1, {b + 2}, gY{j}, 3", "endif"]
    return "\n".join(out) + "\n"


def _hot3d() -> str:
    """水平つなぎの段を上下に動かす 3D のホットスポット（手前の隅の支柱の外。床の上端から下へ lvD）."""
    out = ["! 水平つなぎの段を上下に動かすホットスポット（手前の隅の支柱の外）", "hx = gx[1]", "hy = gy[1] - secB[kP] / 2 - 0.3"]
    for k in range(1, MAX_LV + 1):
        b = 400 + 3 * k
        out += [f"if nLv >= {k} then", f"\thotspot hx, hy, zTop, {b}, lvD{k}, 1 + 128",
                f"\thotspot hx, hy, zTop - lvD{k}, {b + 1}, lvD{k}, 2", f"\thotspot hx, hy, zTop + 1, {b + 2}, lvD{k}, 3",
                "endif"]
    return "\n".join(out) + "\n"


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(_master(), encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(_vl(), encoding="utf-8")
    (OUT / "scripts" / "2d.gdl").write_text(SCRIPT_2D + _hot2d(), encoding="utf-8")
    (OUT / "scripts" / "3d.gdl").write_text(SCRIPT_3D.replace("\nend\n", "\n" + _hot3d() + "end\n", 1), encoding="utf-8")
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
    print(f"ashiba_kodai: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
