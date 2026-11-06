"""部品 ashiba_tower（タワークレーン 1基に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「タワークレーンも追加してちょ」。機種と寸法は src/ashiba/tower.py（出典はそちら）、置くのは
scripts/tower_run.py。原点＝マストの芯の基礎の上面、+X＝旋回の 0°。tcType 1 起伏ジブ（ジブを jbA だけ起こす）・2 水平ジブ
（トロリで作業半径 trR）。

マストは主材4本と各面の斜材・水平材（1本 msSeg ごと）、基礎（baseW 角・厚さ baseD を上面の下に）、壁つなぎ（tieZ の高さごとに
カラーと建物へ2本の控え。向き tieA・長さ tieL）。旋回体は旋回 slew で回し、旋回輪・機械台・カウンタウエイト（後端旋回半径 tailR）・
運転室・Aフレーム（起伏ジブ）か塔頭（水平ジブ）・ジブ（主材と斜材）・ワイヤ・フック。平面はマストと基礎・ジブ・後端旋回半径の円・
今の作業半径の円・最大作業半径の円・壁つなぎ・注記。
  python3 scripts/gen_tower_gdl.py     # gdl/hsf/ashiba_tower を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from gen_hoist_gdl import _param  # noqa: E402
from gen_ywall_gdl import _list  # noqa: E402
import gdl_draft  # noqa: E402
import gdl_radii  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_tower"
MAIN_GUID = "7A3F1C58-9E24-4D6B-8F12-6C4E9B2A7D31"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "tcModel", "機種（選ぶと寸法を書き込む。0＝手入力）", 0),
        _param("Integer", "tcType", "形式（1 起伏ジブ・2 水平ジブ）", 1),
        _param("String", "tcName", "機種の名前（平面の注記）", "タワークレーン"),
        _param("String", "tcNote", "諸元の注記", ""),
        _param("Angle", "slew", "旋回角（+X から左回り）", 30.0),
        # マストと基礎
        _param("Length", "msW", "マストの断面（主材の芯々）", 2.0),
        _param("Length", "msH", "マストの高さ（基礎の上面から旋回輪の下まで）", 40.0),
        _param("Length", "msSeg", "マスト1本の長さ", 4.0),
        _param("Length", "baseW", "基礎の一辺", 7.0),
        _param("Length", "baseD", "基礎の厚さ（上面から下へ）", 1.5),
        # 旋回体
        _param("Length", "tailR", "後端旋回半径（カウンタウエイトの後端）", 8.0),
        _param("Length", "cwW", "カウンタウエイトの幅", 2.5),
        _param("Length", "cwH", "カウンタウエイトの高さ", 2.0),
        _param("Length", "cwL", "カウンタウエイトの奥行", 1.5),
        _param("Length", "dkW", "機械台の幅", 3.0),
        _param("Length", "dkY", "機械台の中心のずれ（左が +）", 0.0),
        _param("Length", "cbL", "運転室の前後", 1.8),
        _param("Length", "cbW", "運転室の幅", 1.1),
        _param("Length", "cbZ", "運転室の上面の高さ（旋回体を受ける面から）", 3.2),
        _param("Length", "cbH", "運転室の高さ", 2.1),
        _param("Length", "frH", "Aフレーム・塔頭の高さ（旋回輪から）", 9.0),
        _param("Length", "frX", "Aフレーム頂部（旋回中心から後ろ）", 3.0),
        _param("Length", "upF", "旋回体の前端（旋回中心から前）", 2.0),
        _param("Length", "pvX", "ジブの根元（旋回中心から前）", 1.0),
        _param("Length", "pvH", "ジブの根元の高さ（旋回輪から）", 2.5),
        # ジブ
        _param("Length", "jbL", "ジブの長さ", 40.0),
        _param("Angle", "jbA", "ジブの起伏角（起伏ジブ）", 45.0),
        _param("Length", "jbW", "ジブの断面", 1.4),
        _param("Length", "trR", "トロリの作業半径（水平ジブ）", 25.0),
        _param("Length", "hkD", "ジブの先（トロリ）からフックまで", 10.0),
        _param("Length", "maxR", "最大作業半径（平面の円）", 40.0),
        # 壁つなぎ
        _param("String", "tieZ", "壁つなぎの高さ（mm・カンマ区切り）", ""),
        _param("Angle", "tieA", "壁つなぎの向き（建物の側）", 180.0),
        _param("Length", "tieL", "壁つなぎの長さ（マストの面から建物まで）", 2.0),
        _param("Length", "hfX", "フックの位置 X（平面のホットスポット）", 30.0),
        _param("Length", "hfY", "フックの位置 Y", 0.0),
        _param("String", "rtR", "定格荷重の作業半径（mm。据え付けたジブの表）", ""),
        _param("String", "rtT", "定格荷重（10kg 単位）", ""),
        _param("RealNum", "loadT", "吊荷 t", 0.0),
        _param("Integer", "tcClr", "色の組（1 黄・2 赤白）", 1),
        _param("Boolean", "tcBase", "ベース（クロスベース）を描く", 1),
        _param("Boolean", "clOn", "クライミング枠を描く", 1),
        _param("Boolean", "msStep", "マストの高さを節の長さに吸い付ける（段階マスト）", 0),
        _param("Boolean", "hkLim", "フックを規定の揚程の範囲に制限する（最大揚程）", 0),
        _param("Length", "hkMax", "最大揚程（地盤からフックの上限）", 0.0),
        *gdl_radii.params(_param),
        _param("Integer", "avN", "航空障害灯（0＝無し・1＝塔頂とジブ先端・2 以上＝ジブの途中に avN−1 個）", 0),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        "\t\t<PenColor Name=\"penEquip\">\n\t\t\t<Description><![CDATA[\"線のペン\"]]></Description>\n"
        "\t\t\t<Value>1</Value>\n\t\t</PenColor>\n",
        *gdl_draft.params(),
    ]
    return ("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ParamSection>\n\t<ParamSectHeader>\n"
            "\t\t<AutoHotspots>false</AutoHotspots>\n\t\t<StatBits>\n\t\t\t<STBit_UIDefault/>\n\t\t</StatBits>\n"
            "\t\t<WDLeftFrame>0</WDLeftFrame>\n\t\t<WDRightFrame>0</WDRightFrame>\n\t\t<WDTopFrame>0</WDTopFrame>\n"
            "\t\t<WDBotFrame>0</WDBotFrame>\n\t\t<LayFlags>65535</LayFlags>\n\t\t<WDMirrorThickness>0</WDMirrorThickness>\n"
            "\t\t<WDWallInset>0</WDWallInset>\n\t</ParamSectHeader>\n"
            "\t<Parameters SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\">\n" + "".join(ps)
            + "\t</Parameters>\n</ParamSection>\n")


SCRIPT_1D = ("""﻿! タワークレーン: マストの本数・ジブの先・フックの位置・壁つなぎの高さ（m・度）
nSg = max(1, int(msH / max(0.5, msSeg) + 0.5))
sgL = msH / nSg
zR = msH
! ジブの先（起伏ジブは起こした先、水平ジブはジブの先）と今の作業半径（フックの位置）
if tcType = 2 then
	jX = pvX + jbL
	jZ = zR + pvH
	hX = max(pvX + 2, min(jX - 0.5, trR))
else
	jX = pvX + jbL * cos(jbA)
	jZ = zR + pvH + jbL * sin(jbA)
	hX = jX
endif
hZ = max(0.5, jZ - hkD)
if hkLim and hkMax > 0.1 then hZ = min(hZ, hkMax)
""" + _list("rtR", "qR", "nQr", 1000) + _list("rtT", "qT", "nQt", 1) + """capT = 0
for i = nQr to 1 step -1
	if qR[i] >= hX - 0.001 and i <= nQt then capT = qT[i] / 100
next i
""" + gdl_radii.master() + gdl_radii.rated_loop('\tfor k = nQr to 1 step -1\n\t\tif qR[k] >= wiRq[wq] - 0.001 and k <= nQt then vq = qT[k] / 100\n\tnext k\n') + """! 壁つなぎの高さ（mm の文字 → m）
dim tz[]
nTz = 0
rest = tieZ
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
		nTz = nTz + 1
		tz[nTz] = v / 1000
	endif
endwhile
""")

SCRIPT_VL = """﻿! タワークレーン: 形式の一覧
values{2} "tcType" 1, "起伏ジブ", 2, "水平ジブ"
mq = GLOB_MODPAR_NAME
if msStep and mq = "msH" then parameters msH = max(1, int(msH / max(0.5, msSeg) + 0.5)) * msSeg
if (mq = "hfX" or mq = "hfY") and abs(hfX) + abs(hfY) > 0.1 then
	! 平面のフックを引いた: 横は旋回、前後は起伏ジブの角度かトロリの半径
	if abs(hfX) < 0.0001 then
		aF = 90 + 180 * (hfY < 0)
	else
		aF = atn(hfY / hfX) + 180 * (hfX < 0)
		if aF < 0 then aF = aF + 360
	endif
	rF = sqr(hfX * hfX + hfY * hfY)
	if tcType = 2 then
		parameters slew = aF, trR = rF
	else
		parameters slew = aF, jbA = acs(max(-1, min(1, (rF - pvX) / jbL)))
	endif
else
	if abs(hfX - hX * cos(slew)) + abs(hfY - hX * sin(slew)) > 0.001 then parameters hfX = hX * cos(slew), hfY = hX * sin(slew)
endif
"""

SCRIPT_2D_T = """﻿! タワークレーン 2D: 基礎・マスト・壁つなぎ・ジブとカウンタウエイト（旋回）・後端旋回半径・作業半径・注記・ホットスポット
! CAD の平面図の描き方（scripts/gdl_draft.py）: 外形は太線・細部は細線、地中の基礎は破線、作業半径は一点鎖線、後端旋回半径は
! 二点鎖線。旋回体（カウンタウエイト・デッキ）は背景の色で塗って下のマストを隠す。縮尺で描き分ける
@HEAD@
pen penEquip
define style "tcT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "tcT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
! 基礎（地中なので破線）・マスト（詳細はラチスの斜材）
drawindex 10
pen pT
if drLv < 3 then
	line_type ltH
	rect2 -baseW / 2, -baseW / 2, baseW / 2, baseW / 2
	line_type ltS
endif
drawindex 12
pen pO
rect2 -msW / 2, -msW / 2, msW / 2, msW / 2
pen pT
if drLv < 3 then
	line2 -msW / 2, -msW / 2, msW / 2, msW / 2
	line2 -msW / 2, msW / 2, msW / 2, -msW / 2
endif
! 壁つなぎ（建物の側へ2本。詳細はつなぎの間の斜材）
if nTz > 0 then
	rot2 tieA
	pen pO
	line2 msW / 2, -msW / 2, msW / 2 + tieL, -msW / 2 - 0.3
	line2 msW / 2, msW / 2, msW / 2 + tieL, msW / 2 + 0.3
	if drLv = 1 then
		pen pT
		line2 msW / 2, -msW / 2, msW / 2 + tieL, msW / 2 + 0.3
	endif
	del 1
endif
! 後端旋回半径（立入禁止の目安。二点鎖線）・今の作業半径・最大作業半径（一点鎖線）
drawindex 45
pen pZ
line_type ltZ
circle2 0, 0, tailR
line_type ltC
circle2 0, 0, hX
if maxR > hX + 0.1 then circle2 0, 0, maxR
line_type ltS
! ジブとカウンタウエイト（旋回で回す）
rot2 slew
if mk then
	drawindex 20
@CWMASK@
@DKMASK@
endif
drawindex 30
pen pO
line2 pvX, -jbW / 2, jX, -jbW / 4
line2 pvX, jbW / 2, jX, jbW / 4
line2 jX, -jbW / 4, jX, jbW / 4
rect2 -tailR, dkY - cwW / 2, -tailR + cwL, dkY + cwW / 2
rect2 -tailR + cwL, dkY - dkW / 2, upF, dkY + dkW / 2
pen pT
if drLv < 3 then rect2 upF - cbL, dkY - dkW / 2, upF, dkY - dkW / 2 + cbW
if drLv = 1 then
	! ジブのラチス（上下の弦材の間に斜材）とカウンタウエイトの目地
	nLc = max(2, int((jX - pvX) / max(jbW, 1.0)))
	for k = 0 to nLc - 1
		xa = pvX + k * (jX - pvX) / nLc
		xb = pvX + (k + 1) * (jX - pvX) / nLc
		wa = jbW / 2 - (jbW / 4) * k / nLc
		wb = jbW / 2 - (jbW / 4) * (k + 1) / nLc
		sg = 1 - 2 * (k mod 2)
		line2 xa, sg * wa, xb, -sg * wb
	next k
	for k = 1 to 3
		line2 -tailR + k * cwL / 4, dkY - cwW / 2, -tailR + k * cwL / 4, dkY + cwW / 2
	next k
endif
if drLv < 3 then
	line_type ltC
	line2 -tailR - 0.5, 0, jX + 0.8, 0
	line_type ltS
endif
circle2 hX, 0, 0.4
del 1
! 旋回の中心（一点鎖線の十字）
drawindex 45
pen pT
line_type ltC
line2 -msW, 0, msW, 0
line2 0, -msW, 0, msW
line_type ltS
! 注記
drawindex 50
pen penEquip
add2 -baseW / 2 - 0.5, -max(baseW, dkW) / 2 - 0.8          ! 基礎と機械台の外（下）に書く（1/200 で台の線に重ならないように）
rot2 -SYMB_ROTANGLE
text2 0, 0, tcName
if strlen(tcNote) > 0 and drLv < 3 then text2 0, -dT, tcNote
text2 0, -2 * dT, "R" + str(round_int(hX * 1000), 1, 0) + "・マスト " + str(round_int(msH * 1000), 1, 0)
del 2
! フックのホットスポット（X と Y の組を同じ点に置いて、どの向きにも引ける）と定格荷重の注記
xF = hX * cos(slew)
yF = hX * sin(slew)
hotspot2 0, yF, 61, hfX, 1 + 128
hotspot2 xF, yF, 62, hfX, 2
hotspot2 -1, yF, 63, hfX, 3
hotspot2 xF, 0, 64, hfY, 1 + 128
hotspot2 xF, yF, 65, hfY, 2
hotspot2 xF, -1, 66, hfY, 3
add2 xF, yF
rot2 -SYMB_ROTANGLE
if capT > 0 then text2 0.6, dT, "定格 " + str(capT, 5, 2) + "t"
text2 0.6, 0, "R" + str(round_int(hX * 1000), 1, 0)
del 2
@RADII@! 旋回角のホットスポット
rH = max(3.0, tailR)
hotspot2 0, 0, 1, slew, 6
hotspot2 rH, 0, 2, slew, 4
hotspot2 rH * cos(slew), rH * sin(slew), 3, slew, 5
hotspot2 0, 0
"""


def _script_2d() -> str:
    """2D スクリプト: 型（SCRIPT_2D_T）に描き方の決めと隠す塗りの多角形を入れる."""
    D = gdl_draft
    t = "\t"
    rep = {
        "@HEAD@": D.head().rstrip("\n"),
        "@CWMASK@": D.rect_mask("-tailR", "dkY - cwW / 2", "-tailR + cwL", "dkY + cwW / 2", t).rstrip("\n"),
        "@DKMASK@": D.rect_mask("-tailR + cwL", "dkY - dkW / 2", "upF", "dkY + dkW / 2", t).rstrip("\n"),
    }
    out = SCRIPT_2D_T.replace("@RADII@", gdl_radii.plan("pT", "ltS", "penEquip", "tcT"))
    for k, v in rep.items():
        assert k in out, k
        out = out.replace(k, v)
    return out


SCRIPT_2D = _script_2d()

SCRIPT_3D = """﻿! タワークレーン 3D
! 色の組（1 黄・2 赤白。航空障害標識の塗り分け。同じ名前の define material は 1回だけ）
cR = 0.95
cG = 0.75
cB = 0.10
wR = cR
wG = cG
wB = cB
if tcClr = 2 then
	cR = 0.80
	cG = 0.12
	cB = 0.10
	wR = 0.94
	wG = 0.94
	wB = 0.94
endif
define material "tc_body" 2, cR, cG, cB
define material "tc_band" 2, wR, wG, wB
define material "tc_steel" 2, 0.55, 0.56, 0.58
define material "tc_dark" 2, 0.20, 0.20, 0.22
define material "tc_cw" 2, 0.62, 0.63, 0.64
define material "tc_conc" 2, 0.75, 0.74, 0.70
define material "tc_glass" 2, 0.30, 0.45, 0.60
define material "tc_hook" 2, 0.92, 0.40, 0.12
define material "tc_light" 2, 0.95, 0.10, 0.08
resol 8
! 基礎
material "tc_conc"
add -baseW * 0.55, -baseW * 0.55, -baseD
block baseW * 1.1, baseW * 1.1, baseD
del 1
if tcBase then
	! ベース（クロスベースの2本の梁）
	material "tc_steel"
	for s = -1 to 1 step 2
		add 0, 0, 0
		rotz 45 * s
		add -baseW * 0.7, -0.25, 0
		block baseW * 1.4, 0.5, 0.5
		del 3
	next s
	add -msW / 2 - 0.3, -msW / 2 - 0.3, 0.5
	block msW + 0.6, msW + 0.6, 0.15
	del 1
endif
gosub "mast"
gosub "ties"
gosub "climb"
add 0, 0, zR
rotz slew
gosub "slewing"
if tcType = 2 then
	gosub "flatjib"
else
	gosub "luffjib"
endif
if avN > 0 then gosub "lights"
del 2
gosub "hook"
end

"seg3":
	! (x0q, y0q, z0q) から (x1q, y1q, z1q) の円柱（半径 rq）
	dxq = x1q - x0q
	dyq = y1q - y0q
	dzq = z1q - z0q
	hq = sqr(dxq ^ 2 + dyq ^ 2)
	lq = sqr(hq ^ 2 + dzq ^ 2)
	if lq > 0.001 then
		az = 0
		if hq > 0.0001 then
			if abs(dxq) < 0.0001 then
				az = 90
				if dyq < 0 then az = -90
			else
				az = atn(dyq / dxq)
				if dxq < 0 then az = az + 180
			endif
		endif
		el = 90
		if dzq < 0 then el = -90
		if hq > 0.0001 then el = atn(dzq / hq)
		add x0q, y0q, z0q
		rotz az
		roty 90 - el
		cylind lq, rq
		del 3
	endif
	return

"mast":
	! マスト: 箱の主材 4 本・節ごとの X の斜材と水平材・継ぎの板・はしごと休憩台
	wC = msW * 0.13
	material "tc_body"
	for sx = -1 to 1 step 2
		for sy = -1 to 1 step 2
			add sx * msW / 2 - wC / 2, sy * msW / 2 - wC / 2, 0
			block wC, wC, msH
			del 1
		next sy
	next sx
	rq = msW * 0.028
	for k = 0 to nSg - 1
		za = k * sgL
		zb = min(msH, za + sgL)
		for f = 1 to 4
			ca = cos(f * 90)
			sa = sin(f * 90)
			cb = cos(f * 90 + 90)
			sb = sin(f * 90 + 90)
			x0q = msW / 2 * (ca - sa)
			y0q = msW / 2 * (sa + ca)
			x1q = msW / 2 * (cb - sb)
			y1q = msW / 2 * (sb + cb)
			z0q = za
			z1q = za
			gosub "seg3"
			z1q = zb
			gosub "seg3"
			xq = x0q
			yq = y0q
			x0q = x1q
			y0q = y1q
			x1q = xq
			y1q = yq
			z0q = za
			gosub "seg3"
			x1q = (x0q + xq) / 2
			y1q = (y0q + yq) / 2
		next f
		! 継ぎの板
		material "tc_dark"
		for sx = -1 to 1 step 2
			for sy = -1 to 1 step 2
				add sx * msW / 2 - wC * 0.7, sy * msW / 2 - wC * 0.7, za - 0.06
				block wC * 1.4, wC * 1.4, 0.12
				del 1
			next sy
		next sx
		! 休憩台
		material "tc_steel"
		add -msW * 0.42, -msW * 0.42, za + 0.04
		block msW * 0.84, msW * 0.84, 0.04
		del 1
		material "tc_body"
	next k
	! はしご（マストの中）
	material "tc_steel"
	rq = 0.02
	for s = -1 to 1 step 2
		add msW * 0.3, s * 0.2, 0
		cylind msH, 0.02
		del 1
	next s
	for k = 0 to int(msH / 0.9)
		add msW * 0.3 - 0.015, -0.2, k * 0.9
		block 0.03, 0.4, 0.03
		del 1
	next k
	return

"climb":
	! クライミング枠（マストを抱く四角の枠。上の 2 段。機種の外形は調査のメモ）
	if clOn then
		for k = 1 to 2
			zK = msH - k * 3.4
			if zK > 1 then
				material "tc_dark"
				hK = msW / 2 + 0.3
				for s = -1 to 1 step 2
					add -hK - 0.5, s * hK - 0.2, zK
					block 2 * hK + 1.0, 0.4, 0.6
					del 1
					add s * hK - 0.2, -hK - 0.5, zK
					block 0.4, 2 * hK + 1.0, 0.6
					del 1
				next s
				! 昇降のシリンダ
				material "tc_steel"
				for s = -1 to 1 step 2
					add s * (msW / 2 + 0.16), 0, zK + 0.6
					cylind 1.6, 0.09
					del 1
				next s
			endif
		next k
	endif
	return

"ties":
	! 壁つなぎ: 高さごとにマストを囲むカラーと、建物の側（tieA）へ2本の控え
	if nTz > 0 then
		for i = 1 to nTz
			material "tc_dark"
			add -msW / 2 - 0.15, -msW / 2 - 0.15, tz[i] - 0.15
			block msW + 0.3, msW + 0.3, 0.3
			del 1
			material "tc_steel"
			rq = 0.08
			for s = -1 to 1 step 2
				x0q = (msW / 2 + 0.15) * cos(tieA) - s * msW / 2 * sin(tieA)
				y0q = (msW / 2 + 0.15) * sin(tieA) + s * msW / 2 * cos(tieA)
				x1q = (msW / 2 + tieL) * cos(tieA) - s * (msW / 2 + 0.3) * sin(tieA)
				y1q = (msW / 2 + tieL) * sin(tieA) + s * (msW / 2 + 0.3) * cos(tieA)
				z0q = tz[i]
				z1q = tz[i]
				gosub "seg3"
			next s
		next i
	endif
	return

"slewing":
	! 旋回体: ポスト・旋回輪・機械台の梁・通路と手すり・機械室のドラム・カウンタウエイト・運転室
	material "tc_dark"
	cylind 0.25, msW * 0.68
	add 0, 0, 0.25
	cylind 0.35, msW * 0.6
	del 1
	xD0 = -tailR + cwL
	lD = tailR - cwL + upF
	material "tc_body"
	for s = -1 to 1 step 2
		add xD0, dkY + s * (dkW / 2 - 0.2) - 0.2, 0.6
		block lD, 0.4, 0.5
		del 1
	next s
	for k = 0 to 4
		add xD0 + k * (lD - 0.3) / 4, dkY - dkW / 2 + 0.2, 0.68
		block 0.3, dkW - 0.4, 0.34
		del 1
	next k
	! 通路の板と手すり
	material "tc_steel"
	add xD0, dkY - dkW / 2, 1.1
	block lD, dkW, 0.03
	del 1
	rq = 0.02
	for s = -1 to 1 step 2
		yH = dkY + s * dkW / 2
		for k = 0 to 4
			x0q = xD0 + k * lD / 4
			y0q = yH
			z0q = 1.13
			x1q = x0q
			y1q = yH
			z1q = 2.2
			gosub "seg3"
		next k
		for k = 0 to 1
			x0q = xD0
			x1q = xD0 + lD
			y0q = yH
			y1q = yH
			z0q = 1.65 + k * 0.55
			z1q = z0q
			gosub "seg3"
		next k
	next s
	! 機械室（箱）と巻上・起伏のドラム
	material "tc_band"
	add xD0 + 0.2, dkY - dkW * 0.3, 1.13
	block min(2.4, lD * 0.35), dkW * 0.6, 1.5
	del 1
	for k = 0 to 1
		xW = xD0 + min(2.4, lD * 0.35) + 0.7 + k * 1.1
		material "tc_dark"
		add xW, dkY - dkW * 0.28, 1.65
		rotx -90
		cylind dkW * 0.56, 0.42
		del 2
		material "tc_steel"
		for s = -1 to 1 step 2
			add xW, dkY + s * dkW * 0.3 - 0.03, 1.65
			rotx -90
			cylind 0.06, 0.55
			del 2
		next s
	next k
	! カウンタウエイト（塊を並べる）
	material "tc_cw"
	nCw = max(2, int(cwW / 0.8))
	for k = 0 to nCw - 1
		add -tailR, dkY - cwW / 2 + k * cwW / nCw + 0.01, 0.6
		block cwL, cwW / nCw - 0.02, cwH
		del 1
	next k
	! 運転室（旋回体の前の右。前面が斜めに傾く。前後 cbL・幅 cbW・上面 cbZ・高さ cbH）
	yR = dkY - dkW / 2
	zC = cbZ - cbH
	material "tc_band"
	add 0, yR + cbW, 0
	rotx 90
	prism 5, cbW, upF - cbL, zC, upF - 0.35, zC, upF, zC + cbH * 0.45, upF - 0.2, cbZ, upF - cbL, cbZ
	del 2
	material "tc_glass"
	add 0, yR + cbW - 0.06, 0
	rotx 90
	prism 4, cbW - 0.12, upF - 0.33, zC + 0.03, upF + 0.01, zC + cbH * 0.45, upF - 0.19, cbZ - 0.06, upF - 0.22, cbZ - 0.08
	del 2
	add 0, yR + 0.004, 0
	rotx 90
	prism 4, 0.008, upF - cbL + 0.12, zC + cbH * 0.35, upF - 0.22, zC + cbH * 0.35, upF - 0.26, cbZ - 0.12, upF - cbL + 0.12, cbZ - 0.12
	del 2
	return

"luffjib":
	! 起伏ジブ: Aフレーム（2 本の柱・後ろの控え・はしご・頂部のシーブ）・ラチスジブ（根元を絞る）・ペンダントと継ぎ金具
	material "tc_body"
	for s = -1 to 1 step 2
		rq = 0.14
		x0q = pvX - 0.6
		y0q = s * dkW * 0.4
		z0q = 1.1
		x1q = -frX
		y1q = s * 0.4
		z1q = frH
		gosub "seg3"
		rq = 0.09
		x0q = -tailR + cwL + 0.3
		gosub "seg3"
	next s
	! はしご
	material "tc_steel"
	nL = int((frH - 1.2) / 0.5)
	for k = 1 to nL
		tL = k / (nL + 1)
		add pvX - 0.6 + (-frX - pvX + 0.6) * tL, -0.3, 1.1 + (frH - 1.1) * tL
		block 0.03, 0.6, 0.03
		del 1
	next k
	add -frX, -0.3, frH
	rotx -90
	cylind 0.6, 0.35
	del 2
	add pvX, 0, pvH
	roty -jbA
	resol 6
	lRt = min(jbL * 0.35, 8.9)
	rcj = jbW * 0.045
	! 主弦材（根元は 2 本の耳へ絞る）
	material "tc_body"
	for sy = -1 to 1 step 2
		for sz = -1 to 1 step 2
			x0q = 0
			y0q = sy * jbW * 0.32
			z0q = sz * jbW * 0.12
			x1q = lRt
			y1q = sy * jbW / 2
			z1q = sz * jbW / 2
			rq = rcj
			gosub "seg3"
			x0q = lRt
			y0q = y1q
			z0q = z1q
			x1q = jbL
			gosub "seg3"
		next sz
	next sy
	nP = max(4, int(jbL / (jbW * 0.95)))
	pP = jbL / nP
	rq = rcj * 0.55
	for i = 0 to nP - 1
		sg = 1 - 2 * (i mod 2)
		! 3 節ごとの塗り分け
		if int(i / 3) mod 2 = 0 then
			material "tc_body"
		else
			material "tc_band"
		endif
		hA = jbW / 2
		zA = jbW / 2
		xq = i * pP
		if xq < lRt then
			hA = jbW * (0.32 + 0.18 * xq / lRt)
			zA = jbW * (0.12 + 0.38 * xq / lRt)
		endif
		hBq = jbW / 2
		zBq = jbW / 2
		xq = (i + 1) * pP
		if xq < lRt then
			hBq = jbW * (0.32 + 0.18 * xq / lRt)
			zBq = jbW * (0.12 + 0.38 * xq / lRt)
		endif
		x0q = i * pP
		x1q = x0q + pP
		y0q = -sg * hA
		y1q = sg * hBq
		z0q = zA
		z1q = zBq
		gosub "seg3"
		z0q = -zA
		z1q = -zBq
		gosub "seg3"
		y0q = hA
		y1q = hBq
		z0q = -sg * zA
		z1q = sg * zBq
		gosub "seg3"
		y0q = -hA
		y1q = -hBq
		gosub "seg3"
	next i
	resol 8
	! ジブの先（側板とシーブ）
	material "tc_steel"
	for s = -1 to 1 step 2
		add jbL - 0.3, s * jbW * 0.4 - 0.03, -jbW / 2
		block 1.0, 0.06, jbW
		del 1
	next s
	add jbL + 0.4, -0.2, 0
	rotx -90
	cylind 0.4, 0.45
	del 2
	del 2
	! ペンダント 2 本と継ぎ金具
	material "tc_steel"
	xM = -frX + (jX + frX) * 0.45
	zM = frH + (jZ - zR - frH) * 0.45
	add xM - 0.3, -0.45, zM - 0.1
	block 0.6, 0.9, 0.2
	del 1
	for s = -1 to 1 step 2
		rq = 0.025
		x0q = -frX
		y0q = s * 0.2
		z0q = frH
		x1q = xM
		y1q = s * 0.4
		z1q = zM
		gosub "seg3"
		x0q = xM
		y0q = s * 0.4
		z0q = zM
		x1q = jX
		y1q = s * jbW / 4
		z1q = jZ - zR
		gosub "seg3"
	next s
	return

"flatjib":
	! 水平ジブ: 塔頭・三角断面のジブ（下弦2本・上弦1本と斜材）・カウンタジブ・タイバー・トロリ
	jbHt = jbW * 0.9
	material "tc_body"
	for s = -1 to 1 step 2
		rq = 0.1
		x0q = s * msW / 2
		y0q = -msW / 2
		z0q = 0.6
		x1q = 0
		y1q = 0
		z1q = frH
		gosub "seg3"
		y0q = msW / 2
		gosub "seg3"
	next s
	resol 6
	rcj = 0.035 + 0.02 * jbW
	rq = rcj
	for s = -1 to 1 step 2
		x0q = pvX
		y0q = s * jbW / 2
		z0q = pvH
		x1q = jX
		y1q = y0q
		z1q = pvH
		gosub "seg3"
		x0q = -tailR + cwL
		x1q = 0
		gosub "seg3"
	next s
	x0q = pvX
	y0q = 0
	z0q = pvH + jbHt
	x1q = jX
	y1q = 0
	z1q = pvH + jbHt
	gosub "seg3"
	nP = max(2, int(jbL / jbW))
	pP = jbL / nP
	rq = rcj * 0.5
	for i = 0 to nP - 1
		for s = -1 to 1 step 2
			x0q = pvX + i * pP
			y0q = s * jbW / 2
			z0q = pvH
			x1q = x0q + pP / 2
			y1q = 0
			z1q = pvH + jbHt
			gosub "seg3"
			x0q = x1q + pP / 2
			gosub "seg3"
		next s
	next i
	resol 8
	material "tc_steel"
	for s = -1 to 1 step 2
		rq = 0.03
		x0q = 0
		y0q = 0
		z0q = frH
		x1q = pvX + jbL * 0.6
		y1q = 0
		z1q = pvH + jbHt
		gosub "seg3"
		x1q = -tailR + cwL + 0.5
		y1q = s * jbW / 2
		z1q = pvH
		gosub "seg3"
	next s
	material "tc_dark"
	add hX - 0.6, -jbW / 2 - 0.1, pvH - 0.5
	block 1.2, jbW + 0.2, 0.4
	del 1
	return

"lights":
	! 航空障害灯（60m 以上。塔頂＝Aフレーム頂部とジブ先端、ジブが長ければ途中にも）
	material "tc_light"
	add -frX, 0, frH + 0.3
	sphere 0.25
	del 1
	add jX, 0, jZ - zR + 0.4
	sphere 0.25
	del 1
	nMid = avN - 1
	for i = 1 to nMid
		fq = i / (nMid + 1)
		add pvX + (jX - pvX) * fq, 0, pvH + (jZ - zR - pvH) * fq + jbW / 2 + 0.25
		sphere 0.2
		del 1
	next i
	return

"hook":
	! ワイヤ（2本）とフック（旋回の向きに作業半径 hX）
	cS = cos(slew)
	sS = sin(slew)
	zT = jZ
	if tcType = 2 then zT = zR + pvH - 0.5
	material "tc_steel"
	for s = -1 to 1 step 2
		add hX * cS - s * 0.12 * sS, hX * sS + s * 0.12 * cS, hZ + 0.8
		cylind max(0.1, zT - hZ - 0.8), 0.015
		del 1
	next s
	add hX * cS, hX * sS, hZ
	rotz slew
	material "tc_hook"
	for s = -1 to 1 step 2
		add 0, s * 0.2 - 0.02, 0.5
		rotx -90
		cylind 0.04, 0.36
		del 2
	next s
	material "tc_steel"
	add 0, -0.18, 0.5
	rotx -90
	cylind 0.36, 0.3
	del 2
	add 0, 0, -0.1
	cylind 0.25, 0.07
	del 1
	material "tc_hook"
	add 0, 0.04, -0.62
	mul 1.2, 1, 1.2
	rotx 90
	prism 15, 0.08, -0.04, 0.45, 0.04, 0.45, 0.05, 0.32, 0.17, 0.2, 0.19, 0.09, 0.12, 0.01, 0, 0, -0.13, 0.05, -0.19, 0.14, -0.13, 0.2, -0.1, 0.13, -0.03, 0.08, 0.07, 0.09, 0.1, 0.15, -0.03, 0.26
	del 3
	del 2
	return
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(SCRIPT_VL + gdl_radii.vl() + model_vl() + gdl_draft.values(), encoding="utf-8")
    (OUT / "scripts" / "2d.gdl").write_text(SCRIPT_2D, encoding="utf-8")
    (OUT / "scripts" / "3d.gdl").write_text(SCRIPT_3D, encoding="utf-8")
    (OUT / "scripts" / "ui.gdl").write_text(gdl_radii.ui(), encoding="utf-8")
    (OUT / "libpartdata.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<LibpartData Owner=\"1196638531\" Signature=\"1196644685\" Version=\"44\">\n"
        f"\t<Identification>\n\t\t<MainGUID>{MAIN_GUID}</MainGUID>\n\t\t<IsPlaceable>true</IsPlaceable>\n"
        "\t\t<IsArchivable>false</IsArchivable>\n\t\t<MigrationValue>Normal</MigrationValue>\n\t\t<IsTemplate>false</IsTemplate>\n"
        "\t</Identification>\n\t<Ancestry SectVersion=\"1\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<CalledMacros SectVersion=\"2\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_3D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_2D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_1D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_UI SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_VL SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<ParamSection SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\"/>\n</LibpartData>\n", encoding="utf-8")
    (OUT / "ancestry.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Ancestry>\n"
        "\t<MainGUID>F938E33A-329D-4A36-BE3E-85E126820996</MainGUID>\n"
        "\t<MainGUID>103E8D2C-8230-42E1-9597-46F84CCE28C0</MainGUID>\n</Ancestry>\n", encoding="utf-8")
    (OUT / "calledmacros.xml").write_text("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<CalledMacros>\n</CalledMacros>\n",
                                         encoding="utf-8")
    print(f"ashiba_tower: 書き出しました（{OUT}）")
    return 0


def model_vl() -> str:
    """機種の一覧（tcModel）と、選んだときに寸法を書き込む（src/ashiba/tower.py から。一覧は配列で渡す）."""
    try:
        from ashiba.tower import TOWERS, model_code, part_params
    except ImportError:
        return ""
    out = ["! 機種を選ぶと、src/ashiba/tower.py の寸法を書き込む（gen_tower_gdl.py が書き出す）",
           "dim mdV[], mdS[]", "mdV[1] = 0", 'mdS[1] = "手入力"']
    for i, (k, t) in enumerate(TOWERS.items(), 2):
        out += [f"mdV[{i}] = {model_code(k)}", f'mdS[{i}] = "{t.name}"']
    out += ['values{2} "tcModel" mdV, mdS', 'if GLOB_MODPAR_NAME = "tcModel" then']
    for k, t in TOWERS.items():
        ps = {a: b for a, b in part_params(t).items() if a not in ("tcName", "tcNote", "slew", "tcModel", "tieZ")}
        out.append(f"\tif tcModel = {model_code(k)} then")
        pp = part_params(t)
        out.append(f'\t\tparameters tcName = "{pp["tcName"]}", tcNote = "{pp["tcNote"]}"')
        out += [f'\t\tparameters {a} = "{b}"' for a, b in ps.items() if isinstance(b, str)]
        pairs = [f"{a} = {b:g}" for a, b in ps.items() if not isinstance(b, str)]
        for i in range(0, len(pairs), 8):
            out.append("\t\tparameters " + ", ".join(pairs[i:i + 8]))
        out.append("\tendif")
    out.append("endif")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
