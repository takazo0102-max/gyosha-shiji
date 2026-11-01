"""部品 ashiba_machine（重機 1台に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。機種と寸法は src/ashiba/machine.py（出典はそちら）、置くのは
scripts/machine_run.py。mcKind 1 バックホウ・2 クローラクレーン・3 コンクリートポンプ車・4 生コン車（トラックミキサ）・5 ダンプ・
6 高所作業車（トラック式）・7 垂直昇降（自走式シザース）。原点＝旋回中心の地盤（ミキサ・ダンプ・垂直昇降は車体の真ん中）、+X＝車体の前。旋回 slew で上部（バックホウ・
クローラクレーンの上部旋回体、ポンプ車・高所作業車のブーム）を回す。

クローラ（履帯の全長 trkL・全幅 trkW・シュー幅 shoeW・高さ trkH）は履帯の板（グローサ）・遊動輪・起動輪・下転輪まで、上部旋回体は後端
旋回半径 tailR の円弧の後ろ（カウンタウエイト）・エンジンカバー・運転室の窓、バックホウはくの字のブーム・アーム・バケット（爪）と
3本のシリンダ、クローラクレーンはラチスブーム（主材4本・斜材）・ガントリ・ペンダント・フック。トラックは運転室（傾いた前窓）・
フレーム・前輪と後ろの2軸・フェンダー・サイドガード・燃料タンク、ポンプ車は旋回台と折り曲げのブーム（段ごとの角度 pA1〜pA5）と
輸送管・先端ホース・アウトリガ4本・ホッパ、生コン車は傾いたドラム（前後の円錐）・ホッパ・シュート・水タンク、ダンプは荷台
（あおり・鳥居）と上げ角 bedA・ホイストシリンダ、高所作業車は伸縮ブームとバスケット（手すり）、アウトリガは3組まで
（o1〜o3 の位置と張出スパン）、垂直昇降は車台・X 字の腕3段・作業床（高さ pfH）と手すり。
平面は外形・上部の外形（旋回で回す）・後端旋回半径（立入禁止）・作業半径（maxR）・アウトリガの位置・注記。
  python3 scripts/gen_machine_gdl.py     # gdl/hsf/ashiba_machine を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_machine"
MAIN_GUID = "5C2E8A71-3D96-4B1F-A7E4-9F6B2D8C1A35"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "mcKind", "種類（1 バックホウ・2 クローラクレーン・3 ポンプ車・4 生コン車・5 ダンプ・6 高所作業車・7 垂直昇降）", 1),
        _param("Integer", "mcModel", "機種（選ぶと寸法を書き込む。0＝手入力）", 3),
        _param("String", "mcName", "機種の名前（平面の注記）", "バックホウ 0.45m³"),
        _param("String", "mcNote", "諸元の注記", ""),
        _param("Angle", "slew", "旋回角（車体の前から左回り）", 0.0),
        _param("Integer", "cbS", "運転室の側（1＝左・-1＝右）", 1),
        # クローラ
        _param("Length", "trkL", "履帯の全長", 4.45),
        _param("Length", "trkW", "履帯の全幅", 2.8),
        _param("Length", "shoeW", "シュー幅", 0.6),
        _param("Length", "trkH", "履帯の高さ", 0.85),
        # 上部旋回体
        _param("Length", "upF", "上部旋回体の前端（旋回中心から）", 1.6),
        _param("Length", "upW", "上部旋回体の幅", 2.7),
        _param("Length", "tailR", "後端旋回半径", 2.75),
        _param("Length", "upZ", "上部旋回体の下端の高さ", 1.0),
        _param("Length", "upH", "運転室の上の高さ（全高）", 2.95),
        _param("Length", "cabW", "運転室の幅", 0.95),
        _param("Length", "cabL", "運転室の長さ", 1.6),
        # バックホウ
        _param("Length", "pvX", "ブームの根元（旋回中心から前）", 0.15),
        _param("Length", "pvH", "ブームの根元の高さ", 1.75),
        _param("Length", "boomL", "ブームの長さ（根元から先の弦）", 5.7),
        _param("Length", "armL", "アームの長さ", 2.9),
        _param("Length", "bkL", "バケットの長さ（ピンから爪）", 1.45),
        _param("Length", "bkW", "バケットの幅", 1.05),
        _param("Angle", "bmA", "ブームの角度（弦）", 35.0),
        _param("Angle", "amA", "アームの角度（水平から）", -70.0),
        _param("Angle", "bkA", "バケットの角度（水平から）", -150.0),
        _param("Length", "maxR", "最大作業半径（平面の円）", 9.9),
        _param("Length", "maxD", "最大掘削深さ", 6.6),
        _param("Length", "bldW", "排土板の幅（0＝無し）", 0.0),
        _param("Length", "bldH", "排土板の高さ", 0.45),
        # クローラクレーン
        _param("Length", "lbL", "ラチスブームの長さ", 30.0),
        _param("Angle", "lbA", "ブームの起伏角", 70.0),
        _param("Length", "lbW", "ブームの幅", 1.2),
        _param("Length", "hkD", "ブームの先からフックまで", 6.0),
        _param("Length", "hkH", "フックの全高", 1.47),
        _param("Length", "hkW", "フックの幅", 0.59),
        _param("Length", "hkT", "フックの厚み", 0.435),
        _param("Length", "gnX", "ガントリ頂部（旋回中心から後ろ）", 3.16),
        _param("Length", "gnH", "ガントリ頂部の高さ", 6.145),
        _param("Length", "cwW", "カウンタウエイトの幅（0＝上部旋回体と同じ）", 0.0),
        _param("Length", "cwH", "カウンタウエイトの高さ（0＝上に載る薄い形）", 0.0),
        # トラック
        _param("Length", "carL", "全長", 8.0),
        _param("Length", "carW", "全幅", 2.49),
        _param("Length", "carF", "原点から前端", 4.0),
        _param("Length", "cabH", "運転室の上の高さ", 3.0),
        _param("Length", "frOv", "前端から前の車軸", 1.3),
        _param("Length", "wb", "前の車軸から後ろの車軸（1軸め）", 4.0),
        _param("Integer", "nFr", "前の車軸の数", 1),
        _param("Length", "frSp", "前の車軸の間", 1.7),
        _param("Integer", "nRear", "後ろの車軸の数", 2),
        _param("Length", "rearSp", "後ろの車軸の間", 1.3),
        _param("Length", "whR", "タイヤの半径", 0.5),
        _param("Length", "frZ", "フレームの上の高さ", 1.0),
        # ポンプ車・高所作業車のブームとアウトリガ
        _param("Integer", "nSec", "ブームの段の数", 4),
        _param("Length", "sL1", "ブーム1段の長さ", 7.5),
        _param("Length", "sL2", "ブーム2段の長さ", 6.5),
        _param("Length", "sL3", "ブーム3段の長さ", 6.5),
        _param("Length", "sL4", "ブーム4段の長さ", 6.0),
        _param("Length", "sL5", "ブーム5段の長さ", 0.0),
        _param("Angle", "pA1", "ブーム1段の角度", 70.0),
        _param("Angle", "pA2", "ブーム2段の角度", 25.0),
        _param("Angle", "pA3", "ブーム3段の角度", -10.0),
        _param("Angle", "pA4", "ブーム4段の角度", -60.0),
        _param("Angle", "pA5", "ブーム5段の角度", -80.0),
        _param("Length", "tuH", "ブームの根元の高さ", 3.2),
        _param("Length", "o1x", "アウトリガ1組め（原点から前が +）", 1.4),
        _param("Length", "o1y", "アウトリガ1組めの張出スパン", 5.43),
        _param("Length", "o2x", "アウトリガ2組め", -2.0),
        _param("Length", "o2y", "アウトリガ2組めの張出スパン", 5.43),
        _param("Length", "o3x", "アウトリガ3組め", -4.6),
        _param("Length", "o3y", "アウトリガ3組めの張出スパン（0＝無し）", 2.3),
        _param("Boolean", "otOn", "アウトリガを張る", 1),
        # 生コン車・ダンプ・高所作業車
        _param("Length", "drL", "ドラムの長さ", 4.3),
        _param("Length", "drD", "ドラムの径", 2.1),
        _param("Angle", "drA", "ドラムの傾き", 14.0),
        _param("Length", "bedL", "荷台の長さ", 5.1),
        _param("Length", "bedW", "荷台の幅", 2.25),
        _param("Length", "bedH", "あおりの高さ", 0.6),
        _param("Angle", "bedA", "荷台の上げ角", 0.0),
        _param("Length", "abL", "伸縮ブームの長さ（今）", 9.0),
        _param("Angle", "abA", "伸縮ブームの起伏角", 55.0),
        _param("Length", "pfL", "バスケットの長さ", 1.2),
        _param("Length", "pfW", "バスケットの幅", 0.7),
        _param("Length", "pfH", "作業床の高さ（垂直昇降）", 3.0),
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


SCRIPT_1D = """﻿! 重機: 種類ごとの形（m・度）
isCr = (mcKind = 1 or mcKind = 2)
isTk = (mcKind >= 3)
! 上部旋回体の後ろの円弧（後端旋回半径）と幅の合う所
w2 = min(upW / 2, tailR * 0.995)
xs = -sqr(tailR ^ 2 - w2 ^ 2)
aS = asn(w2 / tailR)
! カウンタウエイトの幅（クレーンは上部旋回体より広い）
w2c = min(max(cwW, upW) / 2, tailR * 0.995)
xsc = -sqr(tailR ^ 2 - w2c ^ 2)
aSc = asn(w2c / tailR)
! トラック: 前端・後端・車軸（後ろの車軸は1軸めから rearSp ずつ後ろ）
xF = carF
xR = carF - carL
axF = xF - frOv
axR1 = axF - wb
axR2 = axR1 - rearSp * (nRear >= 2)
! 車軸の位置（前 nFr 本・後ろ nRear 本）
dim axs[4]
nAx = 0
for i = 1 to max(1, min(2, nFr))
	nAx = nAx + 1
	axs[nAx] = axF - (i - 1) * frSp
next i
for i = 1 to max(1, min(2, nRear))
	nAx = nAx + 1
	axs[nAx] = axR1 - (i - 1) * rearSp
next i
! アウトリガの組（x と片側の張出）
dim ox[3], oy[3]
ox[1] = o1x
ox[2] = o2x
ox[3] = o3x
oy[1] = o1y / 2
oy[2] = o2y / 2
oy[3] = o3y / 2
nJk = 2 + (o3y > 0.01)
whW = 0.32 + 0.12 * (carW > 2.2)
! バックホウ: ブームの先（弦）・くの字の折れ・アームの先・バケットのピン
bmX1 = pvX + boomL * cos(bmA)
bmZ1 = pvH + boomL * sin(bmA)
knX = pvX + 0.55 * boomL * cos(bmA) - 0.13 * boomL * sin(bmA)
knZ = pvH + 0.55 * boomL * sin(bmA) + 0.13 * boomL * cos(bmA)
amX1 = bmX1 + armL * cos(amA)
amZ1 = bmZ1 + armL * sin(amA)
amX0 = bmX1 - 0.2 * armL * cos(amA)
amZ0 = bmZ1 - 0.2 * armL * sin(amA)
! ポンプ車のブームの段（長さと角度）
dim sl[5], sa[5]
sl[1] = sL1
sl[2] = sL2
sl[3] = sL3
sl[4] = sL4
sl[5] = sL5
sa[1] = pA1
sa[2] = pA2
sa[3] = pA3
sa[4] = pA4
sa[5] = pA5
nSc = max(1, min(5, nSec))
pmX = 0
pmZ = tuH
for i = 1 to nSc
	pmX = pmX + sl[i] * cos(sa[i])
	pmZ = pmZ + sl[i] * sin(sa[i])
next i
! 高所作業車のブームの先
abX = -0.4 + abL * cos(abA)
abZ = tuH + abL * sin(abA)
! クローラクレーンのブームの先
lbX = pvX + lbL * cos(lbA)
lbZ = pvH + lbL * sin(lbA)
"""

SCRIPT_VL = """﻿! 重機: 種類の一覧
values{2} "mcKind" 1, "バックホウ", 2, "クローラクレーン", 3, "コンクリートポンプ車", 4, "生コン車", 5, "ダンプ", 6, "高所作業車", 7, "垂直昇降"
values "nFr" 1, 2
values{2} "cbS" 1, "左", -1, "右"
values "nRear" 1, 2
values "nSec" 3, 4, 5
"""

SCRIPT_2D = """﻿! 重機 2D: 外形・上部の外形（旋回）・後端旋回半径（立入禁止）・作業半径・アウトリガ・注記
pen penEquip
define style "mcT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "mcT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
if isCr then
	! 履帯（2本）と上部旋回体（旋回で回す）
	for s = -1 to 1 step 2
		yc = s * (trkW / 2 - shoeW / 2)
		rect2 -trkL / 2, yc - shoeW / 2, trkL / 2, yc + shoeW / 2
	next s
	circle2 0, 0, tailR
	rot2 slew
	! 外形は円弧と線で（put と poly2 の多角形は平面を止めた）
	arc2 0, 0, tailR, 180 - aS, 180 + aS
	line2 xs, w2, upF, w2
	line2 upF, w2, upF, -w2
	line2 upF, -w2, xs, -w2
	if mcKind = 1 and bldW > 0.1 then
		del 1
		rect2 trkL / 2 + 0.25, -bldW / 2, trkL / 2 + 0.25 + 0.12, bldW / 2
		rot2 slew
	endif
	if mcKind = 1 then
		line2 pvX, -0.25, amX1, -0.15
		line2 pvX, 0.25, amX1, 0.15
		rect2 amX1 - 0.1, -bkW / 2, amX1 + 0.35, bkW / 2
	else
		line2 pvX, -lbW / 2, lbX, -lbW / 2
		line2 pvX, lbW / 2, lbX, lbW / 2
		circle2 lbX, 0, 0.4
	endif
	del 1
endif
if isTk then
	! 車体・運転室・タイヤ
	rect2 xR, -carW / 2, xF, carW / 2
	if mcKind < 7 then line2 xF - min(2.3, carL * 0.28), -carW / 2, xF - min(2.3, carL * 0.28), carW / 2
	for i = 1 to nAx
		for s = -1 to 1 step 2
			rect2 axs[i] - whR, s * carW / 2 - s * 0.05, axs[i] + whR, s * carW / 2 - s * (0.05 + whW)
		next s
	next i
	if (mcKind = 3 or mcKind = 6) and otOn then
		for j = 1 to 3
			if oy[j] > 0.01 then
				for s = -1 to 1 step 2
					line2 ox[j], s * 0.3, ox[j], s * oy[j]
					rect2 ox[j] - 0.3, s * oy[j] - 0.3, ox[j] + 0.3, s * oy[j] + 0.3
				next s
			endif
		next j
	endif
	if mcKind = 7 then rect2 -pfL / 2, -pfW / 2, pfL / 2, pfW / 2
	if mcKind = 3 then
		circle2 0, 0, 0.6
		rot2 slew
		line2 0, -0.2, pmX, -0.15
		line2 0, 0.2, pmX, 0.15
		circle2 pmX, 0, 0.15
		del 1
	endif
	if mcKind = 6 then
		circle2 0, 0, 0.5
		rot2 slew
		line2 -0.4, -0.2, abX, -0.2
		line2 -0.4, 0.2, abX, 0.2
		rect2 abX, -pfL / 2, abX + pfW, pfL / 2
		del 1
	endif
	if mcKind = 4 then
		rect2 xF - 2.2 - drL * cos(drA), -drD / 2, xF - 2.2, drD / 2
	endif
	if mcKind = 5 then
		rect2 xR + 0.1, -bedW / 2, xR + 0.1 + bedL * cos(bedA), bedW / 2
	endif
endif
! 作業半径（バックホウは最大掘削半径、クレーン・ポンプ車・高所作業車は最大作業半径）
rW = maxR
if mcKind = 2 then rW = lbX + 0.4
if rW > 0.1 and (mcKind <= 3 or mcKind = 6) then circle2 0, 0, rW
! 注記（機種・諸元）
xN = -tailR - 0.6
if isTk then xN = xR - 0.6
add2 xN, 0
rot2 -SYMB_ROTANGLE
text2 0, 0, mcName
if strlen(mcNote) > 0 then text2 0, -dT, mcNote
del 2
if rW > 0.1 and (mcKind <= 3 or mcKind = 6) then
	add2 rW * cos(45), rW * sin(45)
	rot2 -SYMB_ROTANGLE
	text2 0, 0, "R" + str(round_int(rW * 1000), 1, 0)
	del 2
endif
! 旋回角のホットスポット
rH = max(2.0, tailR)
hotspot2 0, 0, 1, slew, 6
hotspot2 rH, 0, 2, slew, 4
hotspot2 rH * cos(slew), rH * sin(slew), 3, slew, 5
hotspot2 0, 0
"""

SCRIPT_3D = """﻿! 重機 3D
! 車体の色（バックホウは黄、ほかは白。同じ名前の define material を2回書くと 3D が止まる）
cR = 0.95
cG = 0.72
cB = 0.08
if mcKind >= 2 then
	cR = 0.93
	cG = 0.94
	cB = 0.95
endif
define material "mc_body" 2, cR, cG, cB
define material "mc_dark" 2, 0.18, 0.18, 0.20
define material "mc_steel" 2, 0.55, 0.56, 0.58
define material "mc_cw" 2, 0.35, 0.36, 0.38
define material "mc_tire" 2, 0.10, 0.10, 0.10
define material "mc_rim" 2, 0.80, 0.80, 0.78
define material "mc_glass" 2, 0.30, 0.45, 0.60
define material "mc_rod" 2, 0.85, 0.86, 0.88
define material "mc_drum" 2, 0.92, 0.40, 0.12
define material "mc_bed" 2, 0.30, 0.52, 0.35
resol 12
if isCr then gosub "crawler"
if mcKind = 1 and bldW > 0.1 then gosub "blade"
if isTk and mcKind < 7 then gosub "truck"
if mcKind = 1 then
	rotz slew
	gosub "upper"
	gosub "backhoe"
	del 1
endif
if mcKind = 2 then
	rotz slew
	gosub "upper"
	gosub "lattice"
	del 1
endif
if mcKind = 3 then
	gosub "outrig"
	gosub "pumpbody"
	rotz slew
	gosub "pumpboom"
	del 1
endif
if mcKind = 4 then gosub "mixer"
if mcKind = 5 then gosub "dump"
if mcKind = 6 then
	gosub "outrig"
	rotz slew
	gosub "aerial"
	del 1
endif
if mcKind = 7 then gosub "scissor"
end

"crawler":
	! 履帯（帯・両端の輪・グローサ・横のフレームと下転輪・遊動輪と起動輪）と下部の枠・旋回輪
	rT = trkH / 2
	for s = -1 to 1 step 2
		yc = s * (trkW / 2 - shoeW / 2)
		material "mc_dark"
		add -trkL / 2 + rT, yc - shoeW / 2, 0
		block trkL - 2 * rT, shoeW, trkH
		del 1
		for e = -1 to 1 step 2
			add e * (trkL / 2 - rT), yc + shoeW / 2, rT
			rotx 90
			cylind shoeW, rT
			del 2
		next e
		nG = int((trkL - 2 * rT) / 0.2)
		for k = 0 to nG
			add -trkL / 2 + rT + k * 0.2, yc - shoeW / 2, trkH
			block 0.05, shoeW, 0.03
			del 1
		next k
		! 外の面: 履帯のフレーム（板 0.02）と、その外に下転輪・遊動輪・起動輪（円柱は rotx 90 で -y へ伸びる）
		yP = yc + s * shoeW / 2 - (s < 0) * 0.02
		material "mc_body"
		add -trkL / 2 + rT, yP, trkH * 0.3
		block trkL - 2 * rT, 0.02, trkH * 0.4
		del 1
		yR = yP + (s > 0) * 0.05
		material "mc_steel"
		nRl = max(2, int((trkL - 2 * rT) / 0.45))
		for k = 0 to nRl
			add -trkL / 2 + rT + k * (trkL - 2 * rT) / nRl, yR, 0.13
			rotx 90
			cylind 0.03, 0.09
			del 2
		next k
		for e = -1 to 1 step 2
			add e * (trkL / 2 - rT), yR, rT
			rotx 90
			cylind 0.03, rT * 0.72
			del 2
		next e
	next s
	material "mc_body"
	add -0.9, -(trkW / 2 - shoeW), trkH * 0.35
	block 1.8, trkW - 2 * shoeW, trkH * 0.45
	del 1
	material "mc_steel"
	add 0, 0, trkH * 0.8
	cylind upZ - trkH * 0.8, min(0.85, upW * 0.3)
	del 1
	return

"blade":
	! 排土板（履帯の前。腕2本とシリンダ）
	material "mc_body"
	add trkL / 2 + 0.25, -bldW / 2, 0.02
	block 0.12, bldW, bldH
	del 1
	for s = -1 to 1 step 2
		x0q = trkL / 2 - 0.4
		z0q = trkH * 0.45
		x1q = trkL / 2 + 0.3
		z1q = bldH * 0.5
		bwq = 0.1
		bhq = 0.12
		add 0, s * bldW * 0.3, 0
		gosub "bar"
		del 1
	next s
	crq = 0.04
	cx0 = trkL / 2 - 0.25
	cy0 = 0
	cz0 = trkH * 0.7
	cx1 = trkL / 2 + 0.25
	cy1 = 0
	cz1 = bldH * 0.85
	gosub "cyl2"
	return

"upper":
	! 上部旋回体（後ろは後端旋回半径の円弧）・カウンタウエイト・エンジンカバー・運転室と窓・手すり
	hB = 0.12 * (upH - upZ) + 0.45
	material "mc_body"
	for i = 0 to 8
		aa = 180 + aS - i * aS / 4
		put tailR * cos(aa), tailR * sin(aa)
	next i
	put upF, w2, upF, -w2
	add 0, 0, upZ
	prism nsp / 2, hB, get(nsp)
	del 1
	! カウンタウエイト（cwH があれば下面 upZ から高さ cwH・幅 cwW、無ければ上に載る薄い形）
	xC = xsc + min(0.9, tailR * 0.35)
	zC0 = upZ + hB
	hC = 0.35
	if cwH > 0.01 then
		xC = xsc + 1.0
		zC0 = upZ
		hC = cwH
	endif
	material "mc_cw"
	for i = 0 to 8
		aa = 180 + aSc - i * aSc / 4
		put tailR * cos(aa), tailR * sin(aa)
	next i
	put xC, w2c, xC, -w2c
	add 0, 0, zC0
	prism nsp / 2, hC, get(nsp)
	del 1
	material "mc_body"
	yE0 = -w2 + 0.05
	yE1 = w2 - cabW - 0.1
	if cbS < 0 then
		yE0 = -w2 + cabW + 0.1
		yE1 = w2 - 0.05
	endif
	add xC, yE0, upZ + hB
	block max(0.2, upF - cabL - xC - 0.05), yE1 - yE0, 0.4
	del 1
	material "mc_dark"
	for i = 0 to 4
		add xC + 0.1 + i * 0.18, yE0 + 0.1, upZ + hB + 0.4
		block 0.09, max(0.1, yE1 - yE0 - 0.2), 0.01
		del 1
	next i
	! 運転室（cbS の側の前）
	yC0 = w2 - cabW
	if cbS < 0 then yC0 = -w2
	material "mc_body"
	add upF - cabL, yC0, upZ + hB
	block cabL, cabW, upH - upZ - hB
	del 1
	material "mc_glass"
	hW = (upH - upZ - hB) * 0.62
	add upF + 0.005, yC0 + 0.08, upH - hW - 0.08
	block 0.006, cabW - 0.16, hW
	del 1
	yG = yC0 + cabW + 0.002
	if cbS < 0 then yG = yC0 - 0.008
	add upF - cabL + 0.12, yG, upH - hW - 0.08
	block cabL - 0.24, 0.006, hW
	del 1
	material "mc_steel"
	add upF - cabL - 0.05, yE0, upZ + hB + 0.4
	block 0.04, yE1 - yE0, 0.03
	del 1
	return

"bar":
	! (x0q, z0q) から (x1q, z1q) の箱（幅 bwq・せい bhq。y は 0 を中心）
	dxq = x1q - x0q
	dzq = z1q - z0q
	lq = sqr(dxq ^ 2 + dzq ^ 2)
	anq = 90
	if dzq < 0 then anq = -90
	if abs(dxq) > 0.000001 then anq = atn(dzq / dxq)
	if dxq < 0 then anq = anq + 180
	add x0q, 0, z0q
	roty -anq
	add 0, -bwq / 2, -bhq / 2
	block lq, bwq, bhq
	del 3
	return

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

"cyl2":
	! 油圧シリンダ（太い筒 6 割と細いロッド）: (cx0, cy0, cz0) から (cx1, cy1, cz1)
	material "mc_dark"
	x0q = cx0
	y0q = cy0
	z0q = cz0
	x1q = cx0 + 0.6 * (cx1 - cx0)
	y1q = cy0 + 0.6 * (cy1 - cy0)
	z1q = cz0 + 0.6 * (cz1 - cz0)
	rq = crq
	gosub "seg3"
	material "mc_rod"
	x0q = x1q
	y0q = y1q
	z0q = z1q
	x1q = cx1
	y1q = cy1
	z1q = cz1
	rq = crq * 0.55
	gosub "seg3"
	return

"backhoe":
	! ブーム（くの字の2本の箱）・アーム・バケット（側板の形と爪）・シリンダ3本
	bwq = 0.075 * boomL
	material "mc_body"
	add pvX - 0.2, -bwq / 2 - 0.08, upZ
	block 0.5, bwq + 0.16, pvH - upZ + 0.15
	del 1
	x0q = pvX
	z0q = pvH
	x1q = knX
	z1q = knZ
	bhq = 0.1 * boomL
	gosub "bar"
	x0q = knX
	z0q = knZ
	x1q = bmX1
	z1q = bmZ1
	bhq = 0.075 * boomL
	gosub "bar"
	bwq = 0.06 * boomL
	bhq = 0.06 * boomL
	x0q = amX0
	z0q = amZ0
	x1q = amX1
	z1q = amZ1
	gosub "bar"
	material "mc_steel"
	add bmX1, bwq / 2 + 0.03, bmZ1
	rotx 90
	cylind bwq + 0.06, 0.07
	del 2
	! バケット（ピンから爪へ bkA の向き。側板の形を幅 bkW で押し出す）
	material "mc_dark"
	add amX1, bkW / 2, amZ1
	rotx 90
	rotz bkA
	prism 6, bkW, 0, 0.1 * bkL, 0.3 * bkL, 0.42 * bkL, 0.8 * bkL, 0.38 * bkL, bkL, 0, 0.85 * bkL, -0.06 * bkL, 0.12 * bkL, -0.1 * bkL
	nTh = max(3, int(bkW / 0.22))
	for k = 0 to nTh - 1
		add bkL - 0.02, -0.03, 0.06 + k * (bkW - 0.12) / max(1, nTh - 1) - 0.04
		block 0.14, 0.06, 0.08
		del 1
	next k
	del 3
	! シリンダ（ブーム2本・アーム・バケット）
	crq = 0.045 * boomL / 3.5
	for s = -1 to 1 step 2
		cx0 = pvX + 0.35
		cy0 = s * (0.075 * boomL / 2 + 0.06)
		cz0 = upZ + 0.25
		cx1 = pvX + 0.42 * boomL * cos(bmA) + 0.04 * boomL * sin(bmA)
		cy1 = cy0
		cz1 = pvH + 0.42 * boomL * sin(bmA) - 0.04 * boomL * cos(bmA)
		gosub "cyl2"
	next s
	cx0 = knX - 0.06 * boomL * sin(bmA)
	cy0 = 0
	cz0 = knZ + 0.07 * boomL
	cx1 = amX0
	cy1 = 0
	cz1 = amZ0
	gosub "cyl2"
	crq = crq * 0.8
	cx0 = bmX1 + 0.2 * armL * cos(amA) - 0.08 * sin(amA)
	cy0 = 0
	cz0 = bmZ1 + 0.2 * armL * sin(amA) + 0.08 * cos(amA)
	cx1 = amX1 - 0.12 * armL * cos(amA) - 0.12 * sin(amA)
	cy1 = 0
	cz1 = amZ1 - 0.12 * armL * sin(amA) + 0.12 * cos(amA)
	gosub "cyl2"
	return

"lattice":
	! ラチスブーム（主材4本・斜材は4面）・根元と先・ガントリとペンダント・ワイヤとフック
	material "mc_steel"
	add pvX - 0.4, -lbW / 2 - 0.1, upZ
	block 0.8, lbW + 0.2, pvH - upZ
	del 1
	material "mc_body"
	add pvX, 0, pvH
	roty -lbA
	resol 6
	rcq = 0.035 + 0.02 * lbW
	for sy = -1 to 1 step 2
		for sz = -1 to 1 step 2
			add 0, sy * lbW / 2, sz * lbW / 2
			roty 90
			cylind lbL, rcq
			del 2
		next sz
	next sy
	nP = max(2, int(lbL / lbW))
	pP = lbL / nP
	for i = 0 to nP - 1
		sg = 1 - 2 * (i mod 2)
		rq = rcq * 0.5
		x0q = i * pP
		x1q = x0q + pP
		y0q = -sg * lbW / 2
		y1q = sg * lbW / 2
		z0q = lbW / 2
		z1q = lbW / 2
		gosub "seg3"
		z0q = -lbW / 2
		z1q = -lbW / 2
		gosub "seg3"
		y0q = lbW / 2
		y1q = lbW / 2
		z0q = -sg * lbW / 2
		z1q = sg * lbW / 2
		gosub "seg3"
		y0q = -lbW / 2
		y1q = -lbW / 2
		gosub "seg3"
	next i
	resol 12
	material "mc_steel"
	add lbL - 0.2, -lbW / 2, -lbW / 2
	block 0.6, lbW, lbW
	del 1
	for k = -1 to 1
		add lbL + 0.4, k * 0.2 - 0.04, 0
		rotx -90
		cylind 0.08, 0.45
		del 2
	next k
	del 2
	! ガントリ（上部の後ろ）とペンダント（ガントリの頭からブームの先）
	gX = -gnX
	gZ = gnH
	material "mc_steel"
	for s = -1 to 1 step 2
		x0q = gX - 0.6
		y0q = s * 0.8
		z0q = upZ + 0.9
		x1q = gX
		y1q = s * 0.5
		z1q = gZ
		rq = 0.08
		gosub "seg3"
		x0q = gX + 1.4
		y0q = s * 0.8
		z0q = upZ + 0.9
		gosub "seg3"
		x0q = gX
		y0q = s * 0.5
		z0q = gZ
		x1q = lbX
		y1q = s * lbW / 2 * 0.6
		z1q = lbZ
		rq = 0.02
		gosub "seg3"
	next s
	! ワイヤとフック
	material "mc_steel"
	for s = -1 to 1 step 2
		add lbX + 0.4 + s * 0.12, 0, lbZ - hkD + 0.8
		cylind hkD - 0.8, 0.015
		del 1
	next s
	! フック（仕様書の全高 hkH・幅 hkW・厚み hkT。上の 7 割がブロック、下がフック）
	material "mc_drum"
	add lbX + 0.4 - hkW / 2, -hkT / 2, lbZ - hkD
	block hkW, hkT, hkH * 0.7
	del 1
	material "mc_steel"
	add lbX + 0.4, 0, lbZ - hkD - hkH * 0.3
	cone hkH * 0.3, 0.05, hkT * 0.25, 90, 90
	del 1
	return

"truck":
	! トラックの車体: フレーム・運転室（前窓は傾ける）・タイヤとホイール・フェンダー・バンパー・サイドガード・燃料タンク・ミラー
	material "mc_dark"
	for s = -1 to 1 step 2
		add xR + 0.15, s * 0.45 - 0.05, frZ - 0.28
		block carL - 0.45, 0.1, 0.28
		del 1
	next s
	cZ0 = whR * 2 - 0.1
	cL = min(2.3, carL * 0.28)
	material "mc_body"
	add xF - cL, carW / 2, cZ0
	rotx 90
	prism 5, carW, 0, 0, cL, 0, cL, (cabH - cZ0) * 0.45, cL - 0.3, cabH - cZ0, 0, cabH - cZ0
	del 2
	material "mc_glass"
	x0q = xF + 0.012
	z0q = cZ0 + (cabH - cZ0) * 0.47
	x1q = xF - 0.3 + 0.012
	z1q = cabH - 0.06
	bwq = carW - 0.25
	bhq = 0.01
	gosub "bar"
	for s = -1 to 1 step 2
		add xF - cL + 0.25, s * (carW / 2 + 0.003) - 0.003, cZ0 + (cabH - cZ0) * 0.48
		block cL - 0.75, 0.006, (cabH - cZ0) * 0.4
		del 1
	next s
	! バンパー（運転室の下端に付ける）
	material "mc_dark"
	add xF - 0.12, -carW / 2 + 0.05, cZ0 - 0.3
	block 0.16, carW - 0.1, 0.35
	del 1
	for s = -1 to 1 step 2
		add xF - 0.2, s * (carW / 2 + 0.12) - 0.04, cabH - 0.7
		block 0.04, 0.08, 0.35
		del 1
	next s
	! タイヤ（前は1本・後ろはダブル）
	for i = 1 to nAx
		axX = axs[i]
		for s = -1 to 1 step 2
			! 円柱は rotx 90 で -y へ伸びる。ホイールは外の面に 0.015 出す
			yT = s * (carW / 2 - 0.03) + (s < 0) * whW
			material "mc_tire"
			add axX, yT, whR
			rotx 90
			cylind whW, whR
			del 2
			material "mc_rim"
			add axX, yT + (s > 0) * 0.015, whR
			rotx 90
			cylind whW + 0.015, whR * 0.55
			del 2
			material "mc_body"
			add axX - whR - 0.08, s * (carW / 2 - 0.02) - (s + 1) / 2 * (whW + 0.04), 2 * whR + 0.04
			block 2 * whR + 0.16, whW + 0.04, 0.05
			del 1
		next s
	next i
	! サイドガード（前の車軸と後ろの車軸の間）と燃料タンク
	material "mc_steel"
	for s = -1 to 1 step 2
		for k = 0 to 1
			add axR1 + whR + 0.15, s * (carW / 2 - 0.12) - 0.02, 0.45 + k * 0.25
			block max(0.2, axs[max(1, min(2, nFr))] - axR1 - 2 * whR - 0.3), 0.04, 0.06
			del 1
		next k
	next s
	add axF - whR - 0.25, carW / 2 - 0.35, 0.7
	rotx 90
	cylind 0.6, 0.25
	del 2
	return

"outrig":
	! アウトリガ（組ごとに両側。横の箱・ジャッキ・敷板。3組めは張出スパン 0 なら無し）
	if otOn then
		for s = -1 to 1 step 2
			for e = 1 to nJk
				jX = ox[e]
				jY = max(0.35, oy[e])
				material "mc_body"
				add jX - 0.15, min(s * 0.3, s * jY), frZ - 0.45
				block 0.3, abs(jY - 0.3), 0.25
				del 1
				material "mc_dark"
				add jX, s * jY, 0.08
				cylind frZ - 0.4, 0.09
				del 1
				material "mc_steel"
				add jX - 0.3, s * jY - 0.3, 0
				block 0.6, 0.6, 0.08
				del 1
			next e
		next s
	endif
	return

"pumpbody":
	! ポンプ車: 荷台の機器箱・ホッパ（後ろ）・旋回台
	material "mc_body"
	add xR + 1.2, -carW / 2 + 0.15, frZ
	block max(0.5, -0.8 - xR - 1.2), carW - 0.3, 0.9
	del 1
	material "mc_dark"
	add xR, -0.6, frZ - 0.2
	block 1.0, 1.2, 0.75
	del 1
	material "mc_steel"
	add 0, 0, frZ
	cylind tuH - frZ - 0.3, 0.55
	del 1
	return

"pumpboom":
	! 折り曲げのブーム（段ごとに細く）・関節・輸送管・先端ホース
	material "mc_body"
	add -0.5, -0.45, tuH - 0.6
	block 1.0, 0.9, 0.6
	del 1
	px = 0
	pz = tuH
	for i = 1 to nSc
		qx = px + sl[i] * cos(sa[i])
		qz = pz + sl[i] * sin(sa[i])
		material "mc_body"
		x0q = px
		z0q = pz
		x1q = qx
		z1q = qz
		bwq = 0.38 - 0.05 * i
		bhq = 0.5 - 0.06 * i
		gosub "bar"
		material "mc_steel"
		add qx, bwq / 2 + 0.04, qz
		rotx 90
		cylind bwq + 0.08, bhq * 0.45
		del 2
		material "mc_rod"
		rq = 0.06
		x0q = px - (bhq / 2 + 0.1) * sin(sa[i])
		y0q = -bwq / 2 - 0.1
		z0q = pz + (bhq / 2 + 0.1) * cos(sa[i])
		x1q = qx - (bhq / 2 + 0.1) * sin(sa[i])
		y1q = y0q
		z1q = qz + (bhq / 2 + 0.1) * cos(sa[i])
		gosub "seg3"
		px = qx
		pz = qz
	next i
	material "mc_dark"
	add pmX, 0, max(0.3, pmZ - 3.0)
	cylind min(3.0, pmZ - 0.3), 0.065
	del 1
	return

"mixer":
	! 生コン車: ドラム（前の短い円錐・後ろの長い円錐）・帯・ホッパ・シュート・水タンク・後ろの足場
	zD = frZ + drD / 2 + 0.1
	dX0 = xF - min(2.3, carL * 0.28) - 0.35
	material "mc_drum"
	add dX0, 0, zD
	roty drA - 90
	cone drL * 0.3, drD * 0.3, drD / 2, 90, 90
	addz drL * 0.3
	cone drL * 0.7, drD / 2, drD * 0.22, 90, 90
	material "mc_body"
	for k = 1 to 3
		zk = k * drL * 0.2
		addz zk - 0.04
		cylind 0.08, drD / 2 + (drD * 0.22 - drD / 2) * zk / (drL * 0.7) + 0.02
		del 1
	next k
	del 3
	dX1 = dX0 - drL * cos(drA)
	dZ1 = zD + drL * sin(drA)
	material "mc_steel"
	add dX1 - 0.3, 0, dZ1 + 0.1
	cone 0.6, 0.15, 0.45, 90, 90
	del 1
	x0q = dX1 - 0.2
	z0q = dZ1 - 0.4
	x1q = xR - 0.5
	z1q = frZ + 0.2
	bwq = 0.4
	bhq = 0.05
	gosub "bar"
	add dX0 + 0.1, -0.35, frZ
	cylind 0.7, 0.3
	del 1
	add xR, -0.4, frZ
	block 0.3, 0.8, 0.05
	del 1
	return

"dump":
	! ダンプ: 荷台（床・あおり・鳥居）を後ろのヒンジで bedA だけ上げる・ホイストシリンダ
	hX = xR + 0.1
	hZ = frZ + 0.05
	add hX, 0, hZ
	roty -bedA
	material "mc_bed"
	add 0, -bedW / 2, 0
	block bedL, bedW, 0.12
	block bedL, 0.05, bedH + 0.12
	addy bedW - 0.05
	block bedL, 0.05, bedH + 0.12
	del 2
	add bedL - 0.08, -bedW / 2, 0
	block 0.08, bedW, bedH + 0.35
	addz bedH + 0.3
	block 0.45, bedW, 0.05
	del 2
	add 0, -bedW / 2, 0
	block 0.06, bedW, bedH + 0.12
	del 1
	material "mc_dark"
	for k = 1 to 4
		add k * bedL / 5, -bedW / 2 - 0.04, 0.12
		block 0.06, 0.04, bedH
		addy bedW + 0.04
		block 0.06, 0.04, bedH
		del 2
	next k
	del 2
	if bedA > 0.5 then
		crq = 0.09
		cx0 = hX + bedL * 0.6
		cy0 = 0
		cz0 = frZ - 0.2
		cx1 = hX + bedL * 0.62 * cos(bedA)
		cy1 = 0
		cz1 = hZ + bedL * 0.62 * sin(bedA)
		gosub "cyl2"
	endif
	return

"aerial":
	! 高所作業車: 旋回台・伸縮ブーム（段ごとに細く）・起伏シリンダ・バスケット（床・手すり）
	material "mc_steel"
	add 0, 0, frZ
	cylind tuH - frZ - 0.4, 0.45
	del 1
	material "mc_body"
	add -0.8, -0.5, tuH - 0.45
	block 1.3, 1.0, 0.5
	del 1
	nAb = max(2, min(5, nSec))
	for i = 1 to nAb
		x0q = -0.4 + (i - 1) * abL / nAb * 0.9 * cos(abA)
		z0q = tuH + (i - 1) * abL / nAb * 0.9 * sin(abA)
		x1q = -0.4 + min(abL, i * abL / nAb + 0.3) * cos(abA)
		z1q = tuH + min(abL, i * abL / nAb + 0.3) * sin(abA)
		bwq = 0.36 - 0.05 * i
		bhq = 0.42 - 0.05 * i
		gosub "bar"
	next i
	crq = 0.08
	cx0 = 0.4
	cy0 = 0
	cz0 = tuH - 0.3
	cx1 = -0.4 + abL * 0.35 * cos(abA) + 0.15 * sin(abA)
	cy1 = 0
	cz1 = tuH + abL * 0.35 * sin(abA) - 0.15 * cos(abA)
	gosub "cyl2"
	material "mc_body"
	add abX, -pfL / 2, abZ - 1.2
	block pfW, pfL, 0.1
	del 1
	rx0 = abX
	ry0 = -pfL / 2
	rlx = pfW
	rly = pfL
	rz0 = abZ - 1.1
	gosub "rail"
	return

"rail":
	! 作業床の手すり（rx0, ry0 から rlx × rly、床 rz0 から上桟 1.0・中桟 0.5・隅の柱）
	material "mc_steel"
	for k = 1 to 2
		add rx0, ry0, rz0 + k * 0.5 - 0.04
		block rlx, 0.04, 0.04
		addy rly - 0.04
		block rlx, 0.04, 0.04
		del 1
		block 0.04, rly, 0.04
		addx rlx - 0.04
		block 0.04, rly, 0.04
		del 2
	next k
	for e = 0 to 1
		for s = 0 to 1
			add rx0 + e * (rlx - 0.04), ry0 + s * (rly - 0.04), rz0
			block 0.04, 0.04, 1.0
			del 1
		next s
	next e
	return

"scissor":
	! 自走式の垂直昇降（シザース）: 車台・車輪・X 字の腕（3段）・作業床と手すり
	material "mc_body"
	add xR, -carW / 2, 0.08
	block carL, carW, 0.42
	del 1
	material "mc_tire"
	for e = -1 to 1 step 2
		for s = -1 to 1 step 2
			add e * (carL / 2 - 0.3), s * (carW / 2 - 0.02) + (s < 0) * 0.12, 0.15
			rotx 90
			cylind 0.12, 0.15
			del 2
		next s
	next e
	zA = 0.5
	zB = max(zA + 0.3, pfH - 0.15)
	hS = (zB - zA) / 3
	xa = -carL / 2 + 0.2
	xb = carL / 2 - 0.2
	material "mc_cw"
	bwq = 0.06
	bhq = 0.08
	for s = -1 to 1 step 2
		for k = 0 to 2
			add 0, s * (carW / 2 - 0.08), 0
			x0q = xa
			z0q = zA + k * hS
			x1q = xb
			z1q = zA + (k + 1) * hS
			gosub "bar"
			x0q = xb
			x1q = xa
			gosub "bar"
			del 1
		next k
	next s
	material "mc_body"
	add -pfL / 2, -pfW / 2, zB
	block pfL, pfW, 0.15
	del 1
	rx0 = -pfL / 2
	ry0 = -pfW / 2
	rlx = pfL
	rly = pfW
	rz0 = zB + 0.15
	gosub "rail"
	return
"""


def model_vl() -> str:
    """機種の一覧（mcModel）と、選んだときに寸法・種類・注記を書き込む（GLOB_MODPAR_NAME。1行は 522 バイトまで）."""
    from ashiba.machine import MACHINES, Placed, model_code, part_params

    out = ["! 機種を選ぶと、src/ashiba/machine.py の寸法を書き込む（gen_machine_gdl.py が書き出す）"]
    # 一覧は配列で渡す（1行に全部並べると 408 バイトで部品が止まった。218 バイトは通った）
    out += ["dim mdV[], mdS[]", "mdV[1] = 0", 'mdS[1] = "手入力"']
    for i, (k, m) in enumerate(MACHINES.items(), 2):
        out += [f"mdV[{i}] = {model_code(k)}", f'mdS[{i}] = "{m.name}"']
    out.append('values{2} "mcModel" mdV, mdS')
    out.append('if GLOB_MODPAR_NAME = "mcModel" then')
    for k, m in MACHINES.items():
        ps = {a: b for a, b in part_params(Placed("", m)).items() if a not in ("mcName", "mcNote", "slew", "mcModel")}
        out.append(f"\tif mcModel = {model_code(k)} then")
        out.append(f'\t\tparameters mcName = "{m.name}", mcNote = "{part_params(Placed("", m))["mcNote"]}"')
        pairs = [f"{a} = {b:g}" for a, b in ps.items()]
        for i in range(0, len(pairs), 8):
            out.append("\t\tparameters " + ", ".join(pairs[i:i + 8]))
        out.append("\tendif")
    out.append("endif")
    return "\n".join(out) + "\n"


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(SCRIPT_VL + model_vl(), encoding="utf-8")
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
    print(f"ashiba_machine: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
