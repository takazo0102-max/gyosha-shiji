"""部品 ashiba_crane（移動式クレーン 1台に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「クレーン リサーチして追加して」。寸法はタダノ GR-250N（Ⅴ）・GR-500N（Ⅰ）・GR-700N-3 の仕様書
（src/ashiba/crane_data.py・crane.py）。原点＝旋回中心の地盤、+X＝車体の前。車体（シャシ・タイヤ）、アウトリガ（前 outF・後ろ outR、
張出幅 outW、ジャッキとフロート fltD）、敷鉄板（厚板鋼板 1,524×3,048×22 を plN 枚。2枚は十字）、上部旋回体（旋回 slew 度・
カウンタウエイトの後端は後端旋回半径 tailR）、ブーム（根元 pivB 後ろ・pivH 高さから boomL を起伏角 boomA で、段ごとに細く）、
起伏シリンダ、フック（ブームの先から tipHk 下）・ワイヤ・吊り荷。平面は車体・アウトリガ・敷鉄板・後端旋回半径の円（立入禁止）・
作業半径の円（wrR）・ブームとフック。敷鉄板は plDraw を外すと描かず（配置では別の部品 ashiba_plate を
アウトリガの下に置く。利用者の指定 2026-11-01: 敷鉄板はホットスポットで広げれるようにして 別オブジェクトにして）。割付と検定は src/ashiba/crane.py、置くのは scripts/crane_run.py。
smartCON Planner のクレーンを手本に（利用者の指定 2026-11-01: ホットスポットで姿勢・揚重判定・ブームの干渉チェック・半径の扇形・
走行姿勢）: 平面のホットスポットで作業半径 hkR（ブームの向きに引く）・旋回 slew（角度）・扇の向き wrDir、3D でブーム長さ boomL と
フックの高さ hkZ を引く。長さ優先（prio 0）は起伏角が、角度優先（prio 1）はブーム長さが作業半径から決まり、パラメータスクリプトが
書き戻す。定格総荷重は Python が入れる表（rtB・rtR・rtT1〜8＝ブーム長さ・作業半径・ブームの列ごとの定格 kg）から今の姿勢で読み（ブームはその長さ以上
の列・半径はその半径以上の行）、安全率 sfRate を掛けてフックの所に注記（吊荷＋フック＋玉掛けが超えれば「超過」）。作業半径は
向き wrDir・幅 wrSpan の扇形（360 で円）。travel で走行姿勢（ブームを最短で前に倒し、アウトリガを畳む）。
  python3 scripts/gen_crane_gdl.py     # gdl/hsf/ashiba_crane を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_crane"
MAIN_GUID = "3B7D9E15-2C48-4F6A-9D1E-5A2C8B7F4E63"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "crType", "機種の番号（src/ashiba/crane.py の MODELS の並び。1 から）", 3),
        _param("String", "crName", "機種の名前（平面の注記）", "GR-250N（Ⅴ）25t"),
        _param("Length", "carL", "全長", 11.53),
        _param("Length", "carW", "全幅", 2.62),
        _param("Length", "carH", "全高", 3.475),
        _param("Length", "carF", "旋回中心から前端", 5.4),
        _param("Length", "outF", "旋回中心から前のアウトリガ", 3.265),
        _param("Length", "outR", "旋回中心から後ろのアウトリガ", 3.415),
        _param("Length", "outW", "アウトリガの張出幅（計画の値。描くのと定格を読むのは4脚 oFL〜oRR）", 6.6),
        _param("Length", "oFL", "前左のアウトリガ（車体の芯からジャッキまで。平面のホットスポット）", 3.3),
        _param("Length", "oFR", "前右のアウトリガ", 3.3),
        _param("Length", "oRL", "後左のアウトリガ", 3.3),
        _param("Length", "oRR", "後右のアウトリガ", 3.3),
        _param("Boolean", "oSnap", "アウトリガを性能表の張出の段に吸い付ける", 1),
        _param("String", "rtS", "性能表の張出幅（mm。大きい順。最大 8 段）", "6600,6100,5000,3600,2300"),
        _param("Length", "outSh", "右の列のアウトリガの前後のずれ（右の前＝outF−outSh・右の後＝outR＋outSh）", 0.27),
        _param("Length", "fltA", "フロートの横の大きさ（0＝丸 fltD）", 0.3),
        _param("Length", "fltB", "フロートの前後の大きさ", 0.4),
        _param("String", "axS", "車軸の位置（旋回中心から前が +、mm。カンマ区切り）", "1940,-1940"),
        _param("Length", "whR", "タイヤの半径", 0.683),
        _param("Length", "whW", "タイヤの幅", 0.385),
        _param("Length", "cbX0", "運転室の後ろ（旋回中心から前が +）", -0.3),
        _param("Length", "cbX1", "運転室の前", 2.02),
        _param("Length", "cbY0", "運転室のブームに近い側（ブームの右へ）", 0.39),
        _param("Length", "cbY1", "運転室の外側（ブームの右へ）", 1.29),
        _param("Length", "fltD", "フロートの径", 0.4),
        _param("Length", "upW", "上部旋回体の幅", 2.4),
        _param("Length", "bmW", "基本ブームの幅", 0.75),
        _param("Integer", "nBs", "ブームの段の数（基本ブームを含む）", 4),
        _param("Length", "tailR", "後端旋回半径", 3.1),
        _param("Length", "pivH", "ブームの根元の高さ", 2.3),
        _param("Length", "pivB", "ブームの根元の旋回中心から後ろ", 1.0),
        _param("Length", "tipHk", "ブームの先からフックの上まで", 1.3),
        _param("Length", "hkR", "作業半径（旋回中心からフック。平面のホットスポットで引く）", 12.0),
        _param("Angle", "slew", "旋回角（車体の前から左回り。平面のホットスポット）", 30.0),
        _param("Integer", "prio", "姿勢の優先（0＝ブーム長さ優先＝起伏角が決まる・1＝起伏角優先＝ブーム長さが決まる）", 0),
        _param("Length", "boomL", "ブーム長さ（3D のホットスポット。長さ優先で使う）", 23.45),
        _param("Angle", "boomA", "ブームの起伏角（角度優先で使う。長さ優先では書き戻す）", 56.0),
        _param("Length", "bMin", "ブームの最短", 9.35),
        _param("Length", "bMax", "ブームの最長", 30.5),
        _param("Length", "hkZ", "フックの高さ（地盤から。3D のホットスポット。0＝巻上げ限界）", 0.0),
        _param("RealNum", "loadT", "吊荷 t", 2.5),
        _param("RealNum", "hookT", "フック t", 0.25),
        _param("RealNum", "rigT", "玉掛け用具 t", 0.05),
        _param("RealNum", "sfRate", "安全率（定格総荷重に掛ける。0.9＝90%）", 0.9),
        _param("String", "rtB", "定格総荷重表のブーム長さ（mm）", "9350,16400,23450,30500"),
        *[_param("String", f"rr{i}", f"{i}段目の張出幅の表の作業半径（mm）", "") for i in range(1, 9)],
        *[_param("String", f"rs{i}c{k}", f"定格総荷重（10kg 単位。{i}段目の張出幅の表の {k}番目のブーム長さの列を、その段の作業半径の行の順に、"
                 "無い所は 0。文字のパラメータは 255 字で切れるので張出幅と列ごとに分ける）", "")
          for i in range(1, 9) for k in range(1, 13)],
        _param("Integer", "plN", "敷鉄板の枚数（アウトリガ1脚に。2＝十字。フロートの高さに使う）", 1),
        _param("Boolean", "plDraw", "敷鉄板をこの部品で描く（外す＝別の部品 ashiba_plate を下に置く）", 1),
        _param("String", "wrR", "吊荷の作業半径の円（mm。カンマ区切り）", "12000,18000"),
        _param("Angle", "wrDir", "作業半径の扇の向き（平面のホットスポット）", 0.0),
        _param("Angle", "wrSpan", "作業半径の扇の角度の幅（360＝円）", 360.0),
        _param("Boolean", "travel", "走行姿勢（ブームを最短で前に倒し、アウトリガを畳む）", 0),
        _param("Boolean", "ldOn", "吊り荷を描く", 1),
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


# アウトリガ4脚の張出 → 定格を読む張出幅（4脚の一番小さい張出の 2 倍を、表の張出幅で切り下げる）→ その段の列の文字 sc1〜sc8
SPREAD_PICK = """! ---- アウトリガ4脚（前左・前右・後左・後右。車体の芯からジャッキまで）と、定格を読む張出幅 ----
lFL = oFL
lFR = oFR
lRL = oRL
lRR = oRR
if travel then
	lFL = carW / 2 - 0.05
	lFR = lFL
	lRL = lFL
	lRR = lFL
endif
spE = 2 * min(min(lFL, lFR), min(lRL, lRR))
sI = 0
for i = nSs to 1 step -1
	if ss[i] <= spE + 0.001 then sI = i
next i
spT = 0
if sI > 0 then spT = ss[sI]
srr = ""
""" + "".join(f"sc{k} = \"\"\n" for k in range(1, 13)) + "".join(
    f"if sI = {i} then\n\tsrr = rr{i}\n" + "".join(f"\tsc{k} = rs{i}c{k}\n" for k in range(1, 13)) + "endif\n"
    for i in range(1, 9))


SCRIPT_1D = ("﻿! 移動式クレーン: 姿勢（作業半径・ブーム）・定格総荷重表・車軸（m）\n" + _parse_all("wrR", "wr", "nWr")
             + _parse_all("rtB", "rb", "nRb") + _parse_all("rtS", "ss", "nSs") + SPREAD_PICK + _parse_all("srr", "rr", "nRr")
             + "".join(_parse_all(f"sc{k}", f"tc{k}", f"nTc{k}") for k in range(1, 13)) + _parse_all("axS", "ax", "nAx")
             + """carRr = carL - carF
plT = 0.022
plA = 1.524
plB = 3.048
! ---- 姿勢: 長さ優先は起伏角を、角度優先はブーム長さを作業半径から ----
bL = max(bMin, min(bMax, boomL))
hR = max(1.0, hkR)
slD = slew
owD = spE
if prio = 1 then
	bA = max(1, min(84, boomA))
	bL = max(bMin, min(bMax, (hR + pivB) / cos(bA)))
else
	cA = min(1, max(0.1045, (hR + pivB) / bL))
	bA = acs(cA)
endif
if travel then
	! 走行姿勢: ブームを最短で前に倒し、アウトリガを畳む
	bL = bMin
	bA = 0
	slD = 0
	owD = carW - 0.1
endif
tipX = -pivB + bL * cos(bA)
tipZ = pivH + bL * sin(bA)
hkMx = tipZ - tipHk
hkD = hkMx
if hkZ > 0.3 and hkZ < hkMx and travel = 0 then hkD = hkZ
! ---- 定格総荷重（表のブームはその長さ以上の列、半径はその半径以上の行）----
jB = nRb
for k = nRb to 1 step -1
	if rb[k] >= bL - 0.001 then jB = k
next k
rated = 0
iR = 0
for k = nRr to 1 step -1
	if rr[k] >= tipX - 0.001 then iR = k
next k
if iR > 0 then
	if jB = 1 and iR <= nTc1 then rated = tc1[iR] * 10
	if jB = 2 and iR <= nTc2 then rated = tc2[iR] * 10
	if jB = 3 and iR <= nTc3 then rated = tc3[iR] * 10
	if jB = 4 and iR <= nTc4 then rated = tc4[iR] * 10
	if jB = 5 and iR <= nTc5 then rated = tc5[iR] * 10
	if jB = 6 and iR <= nTc6 then rated = tc6[iR] * 10
	if jB = 7 and iR <= nTc7 then rated = tc7[iR] * 10
	if jB = 8 and iR <= nTc8 then rated = tc8[iR] * 10
	if jB = 9 and iR <= nTc9 then rated = tc9[iR] * 10
	if jB = 10 and iR <= nTc10 then rated = tc10[iR] * 10
	if jB = 11 and iR <= nTc11 then rated = tc11[iR] * 10
	if jB = 12 and iR <= nTc12 then rated = tc12[iR] * 10
endif
capT = rated * sfRate
needT = loadT + hookT + rigT
okL = 0
if rated > 0 and needT <= capT then okL = 1
""")

SCRIPT_2D = """﻿! 移動式クレーン 2D: 車体・アウトリガ・敷鉄板・後端旋回半径（立入禁止）・作業半径の扇・ブームとフック・定格の注記・ホットスポット
! 文字の数は str(数, 1, 0)、小数は長さに余裕を（str(x, 1, 1) は平面図でこの部品の 2D を丸ごと消した。プレビューでは描けていた）
pen penEquip
define style "crT" "ＭＳ Ｐゴシック", texSiz, 1, 0
define style "crR" "ＭＳ Ｐゴシック", texSiz, 3, 0
define style "crC" "ＭＳ Ｐゴシック", texSiz, 2, 0
style "crT"
! 車体（キャリヤ）: 外形・前後のバンパー・タイヤ・旋回輪
rect2 -carRr, -carW / 2, carF, carW / 2
rect2 carF - 0.25, -carW / 2 + 0.15, carF, carW / 2 - 0.15
rect2 -carRr, -carW / 2 + 0.15, -carRr + 0.25, carW / 2 - 0.15
for i = 1 to nAx
	for s = -1 to 1 step 2
		rect2 ax[i] - whR, s * (carW / 2 - 0.02), ax[i] + whR, s * (carW / 2 - 0.02 - whW)
	next s
next i
circle2 0, 0, 0.9
for e = -1 to 1 step 2
	xo = outF
	if e < 0 then xo = -outR
	for s = -1 to 1 step 2
		lg = lFL
		if e > 0 and s < 0 then lg = lFR
		if e < 0 and s > 0 then lg = lRL
		if e < 0 and s < 0 then lg = lRR
		xs = xo - (s < 0) * outSh
		! アウトリガのビーム（箱 0.3 幅）・ジャッキ・フロート
		rect2 xs - 0.15, s * (carW / 2 - 0.2), xs + 0.15, s * lg
		circle2 xs, s * lg, 0.12
		if fltA > 0.01 then
			rect2 xs - fltB / 2, s * lg - fltA / 2, xs + fltB / 2, s * lg + fltA / 2
		else
			circle2 xs, s * lg, fltD / 2
		endif
		! 張出の寸法（車体の芯からジャッキまで mm）
		add2 xs + max(fltB, fltD) / 2 + 0.15, s * lg
		rot2 -SYMB_ROTANGLE
		text2 0, 0, str(round_int(lg * 1000), 1, 0)
		del 2
		if plDraw then
			rect2 xs - plB / 2, s * lg - plA / 2, xs + plB / 2, s * lg + plA / 2
			if plN >= 2 then rect2 xs - plA / 2, s * lg - plB / 2, xs + plA / 2, s * lg + plB / 2
		endif
	next s
next e
! 立入禁止（上部旋回体の後端旋回半径）
circle2 0, 0, tailR
! 作業半径の扇（吊荷ごとの半径と、今のフックの半径。wrSpan 360 は円）
nC = nWr + 1
for i = 1 to nC
	rC = tipX
	if i <= nWr then rC = wr[i]
	if wrSpan >= 359.9 then
		circle2 0, 0, rC
	else
		arc2 0, 0, rC, wrDir - wrSpan / 2, wrDir + wrSpan / 2
	endif
	aT = wrDir
	if wrSpan >= 359.9 then aT = wrDir + 45
	! 半径の文字がブームとフックの注記に重ならないよう、ブームの向きから 30° 以内なら 60° 戻す
	dA = aT - slD + 720
	dA = dA - int(dA / 360) * 360
	if dA > 180 then dA = dA - 360
	if abs(dA) < 30 then aT = slD - 60
	if i <= nWr then
		add2 rC * cos(aT), rC * sin(aT)
		rot2 -SYMB_ROTANGLE
		text2 0, 0, "R" + str(round_int(rC * 1000), 1, 0)
		del 2
	endif
next i
if wrSpan < 359.9 then
	rM = tipX
	for i = 1 to nWr
		rM = max(rM, wr[i])
	next i
	line2 0, 0, rM * cos(wrDir - wrSpan / 2), rM * sin(wrDir - wrSpan / 2)
	line2 0, 0, rM * cos(wrDir + wrSpan / 2), rM * sin(wrDir + wrSpan / 2)
endif
! 上部旋回体とブーム（旋回角で回す）
rot2 slD
! 上部旋回体（後ろはカウンタウエイトの円弧＝後端旋回半径）・運転室（右前）
uw = min(upW / 2, tailR * 0.98)
xc = -sqr(tailR ^ 2 - uw ^ 2)
arc2 0, 0, tailR, 180 - asn(uw / tailR), 180 + asn(uw / tailR)
line2 xc, uw, 1.6, uw
line2 xc, -uw, 1.6, -uw
line2 1.6, -uw, 1.6, uw
line2 xc + 0.9, -uw, xc + 0.9, uw
rect2 cbX0, -cbY1, cbX1, -cbY0
line2 cbX1 - 0.25, -cbY1, cbX1 - 0.25, -cbY0
! ブーム（段ごとに細く、全段を重ねて描く）・ブームの先のシーブ・フック。段の根元は平面に写した長さで
! （ブームに沿った長さのままだと、起こしたブームの上の段がフックの先へはみ出した。2026-11-02 実機の平面図）
nb = max(1, min(6, nBs))
for k = 1 to nb
	wk = bmW * (1 - 0.13 * (k - 1)) / 2
	xk = -pivB + (k - 1) * (bL - 1.2) * cos(bA) / nb
	rect2 xk, -wk, tipX, wk
next k
rect2 tipX - 0.35, -bmW / 2, tipX + 0.25, bmW / 2
circle2 tipX, 0, 0.3
circle2 tipX, 0, 0.12
if ldOn and travel = 0 then rect2 tipX - 0.75, -0.75, tipX + 0.75, 0.75
! 作業半径のホットスポット（ブームの向きに引く）
hotspot2 0, 0, 1, hkR, 1 + 128
hotspot2 tipX, 0, 2, hkR, 2
hotspot2 -1, 0, 3, hkR, 3
del 1
! 定格の注記（フックの所）と機種・姿勢の注記（車体の後ろ）
xT = tipX * cos(slD)
yT = tipX * sin(slD)
dT = texSiz * GLOB_SCALE / 1000 * 1.6
if travel = 0 then
	sOk = ""
	if okL = 0 then sOk = " 超過"
	add2 xT, yT
	rot2 -SYMB_ROTANGLE
	text2 0, 0.6 + dT, "定格 " + str(rated, 5, 2) + "t×" + str(sfRate, 4, 2) + "＝" + str(capT, 5, 2) + "t"
	text2 0, 0.6, "吊荷 " + str(needT, 5, 2) + "t" + sOk
	del 2
endif
! 車体の後ろの外に、車体から離れる側へ寄せて書く（車体の向きで文字の寄せと上下を変える。車体の線に重ならない）
add2 -carRr - 1.0, 0
rot2 -SYMB_ROTANGLE
cR = cos(SYMB_ROTANGLE)
yA = 0
if cR > 0.5 then
	style "crR"
else
	if cR > -0.5 then
		style "crC"
		if sin(SYMB_ROTANGLE) < 0 then yA = 3 * dT
	endif
endif
tS = "張出不足（性能表の最小の張出より狭い）"
if sI > 0 then tS = "性能表 張出 " + str(round_int(spT * 1000), 1, 0) + "（4脚の最小 " + str(round_int(spE * 500), 1, 0) + "×2）"
text2 0, yA - 2 * dT, tS
text2 0, yA, crName
text2 0, yA - dT, "ブーム " + str(round_int(bL * 1000), 1, 0) + "・" + str(round_int(bA), 1, 0) + "°・R" + str(round_int(tipX * 1000), 1, 0)
style "crT"
del 2
! 旋回角のホットスポット（ブームの真ん中）と扇の向き
rH = max(2.0, tipX * 0.5)
hotspot2 0, 0, 4, slew, 6
hotspot2 rH, 0, 5, slew, 4
hotspot2 rH * cos(slD), rH * sin(slD), 6, slew, 5
rW = tipX * 1.1
hotspot2 0, 0, 7, wrDir, 6
hotspot2 rW, 0, 8, wrDir, 4
hotspot2 rW * cos(wrDir), rW * sin(wrDir), 9, wrDir, 5
! アウトリガ4脚のホットスポット（ジャッキの所を車体の横へ引く）
if travel = 0 then
	hid = 20
	for e = -1 to 1 step 2
		xo = outF
		if e < 0 then xo = -outR
		for s = -1 to 1 step 2
			hid = hid + 3
			xs = xo - (s < 0) * outSh
			if e > 0 and s > 0 then
				hotspot2 xs, 0, hid, oFL, 1 + 128
				hotspot2 xs, lFL, hid + 1, oFL, 2
				hotspot2 xs, -1, hid + 2, oFL, 3
			endif
			if e > 0 and s < 0 then
				hotspot2 xs, 0, hid, oFR, 1 + 128
				hotspot2 xs, -lFR, hid + 1, oFR, 2
				hotspot2 xs, 1, hid + 2, oFR, 3
			endif
			if e < 0 and s > 0 then
				hotspot2 xs, 0, hid, oRL, 1 + 128
				hotspot2 xs, lRL, hid + 1, oRL, 2
				hotspot2 xs, -1, hid + 2, oRL, 3
			endif
			if e < 0 and s < 0 then
				hotspot2 xs, 0, hid, oRR, 1 + 128
				hotspot2 xs, -lRR, hid + 1, oRR, 2
				hotspot2 xs, 1, hid + 2, oRR, 3
			endif
		next s
	next e
endif
hotspot2 0, 0
"""

SCRIPT_3D = """﻿! 移動式クレーン 3D（タダノ GR-250N・GR-500N・GR-700N の寸法の目安）
define material "cr_body" 2, 0.92, 0.93, 0.94
define material "cr_blue" 2, 0.15, 0.30, 0.60
define material "cr_boom" 2, 0.95, 0.95, 0.92
define material "cr_cw" 2, 0.30, 0.31, 0.33
define material "cr_steel" 2, 0.55, 0.57, 0.60
define material "cr_plate" 2, 0.35, 0.36, 0.38
define material "cr_tire" 2, 0.10, 0.10, 0.10
define material "cr_hook" 2, 0.95, 0.75, 0.10
define material "cr_load" 2, 0.70, 0.50, 0.30
define material "cr_glass" 2, 0.30, 0.45, 0.60
define material "cr_rim" 2, 0.80, 0.80, 0.78
resol 16
plH = plT * plN
! ---- 敷鉄板（アウトリガ1脚に plN 枚。2枚は十字）とフロート・ジャッキ・アウトリガのビーム ----
for e = -1 to 1 step 2
	xo = outF
	if e < 0 then xo = -outR
	for s = -1 to 1 step 2
		lg = lFL
		if e > 0 and s < 0 then lg = lFR
		if e < 0 and s > 0 then lg = lRL
		if e < 0 and s < 0 then lg = lRR
		xs = xo - (s < 0) * outSh
		yo = s * lg
		yp = s * lg
		material "cr_steel"
		add xs - 0.15, min(0, yo), 1.0
		block 0.3, abs(yo), 0.25
		del 1
		if plDraw then
			material "cr_plate"
			add xs - plB / 2, yp - plA / 2, 0
			block plB, plA, plT
			del 1
			if plN >= 2 then
				add xs - plA / 2, yp - plB / 2, plT
				block plA, plB, plT
				del 1
			endif
		endif
		material "cr_steel"
		zf = plH
		if travel then zf = 0.6
		if fltA > 0.01 then
			add xs - fltB / 2, yo - fltA / 2, zf
			block fltB, fltA, 0.06
			del 1
		else
			add xs, yo, zf
			cylind 0.06, fltD / 2
			del 1
		endif
		add xs, yo, zf + 0.06
		cylind 1.0 - zf - 0.06, 0.09
		del 1
	next s
next e
! ---- 車体（シャシ・タイヤ）----
material "cr_body"
add -carRr, -carW / 2 + 0.1, 0.75
block carL, carW - 0.2, 0.75
del 1
material "cr_blue"
add -carRr, -carW / 2 + 0.1, 0.75
block carL, 0.02, 0.3
del 1
add -carRr, carW / 2 - 0.12, 0.75
block carL, 0.02, 0.3
del 1
for i = 1 to nAx
	for s = -1 to 1 step 2
		! タイヤとホイール（リム）
		material "cr_tire"
		add ax[i], s * (carW / 2 - whW / 2 - 0.02), whR + 0.05
		rotx 90
		addz -whW / 2
		cylind whW, whR
		material "cr_rim"
		addz -0.01
		cylind whW + 0.02, whR * 0.55
		del 4
		! フェンダー（タイヤの上）
		material "cr_body"
		add ax[i] - whR - 0.1, s * (carW / 2 - 0.02) - (s + 1) * (whW + 0.06) / 2, 2 * whR + 0.08
		block 2 * whR + 0.2, whW + 0.06, 0.06
		del 1
	next s
next i
! バンパー（前後）
material "cr_cw"
add carL - carRr - 0.05, -carW / 2 + 0.15, 0.6
block 0.15, carW - 0.3, 0.35
del 1
add -carRr - 0.1, -carW / 2 + 0.15, 0.6
block 0.15, carW - 0.3, 0.35
del 1
! ---- 上部旋回体（旋回角 slew で回す）----
rotz slD
material "cr_steel"
add 0, 0, 1.5
cylind 0.2, 1.0
del 1
material "cr_body"
add -tailR + 0.7, -1.1, 1.7
block tailR - 0.7 + 1.0, 2.2, 0.9
del 1
! カウンタウエイト（段付き）とエンジンカバー
material "cr_cw"
add -tailR, -1.1, 1.7
block 0.7, 2.2, 0.75
del 1
add -tailR + 0.1, -1.0, 2.45
block 0.6, 2.0, 0.3
del 1
material "cr_body"
add -tailR + 0.75, 0.15, 2.6
block 1.3, 0.9, 0.35
del 1
material "cr_cw"
for i = 0 to 4
	add -tailR + 0.85 + i * 0.22, 0.16, 2.95
	block 0.12, 0.88, 0.02
	del 1
next i
! 運転室（右前。cbX0〜cbX1・ブームの右 cbY0〜cbY1）と窓
material "cr_body"
add cbX0, -cbY1, 1.7
block cbX1 - cbX0, cbY1 - cbY0, 1.65
del 1
material "cr_glass"
add cbX0 + 0.4 * (cbX1 - cbX0), -cbY1 - 0.005, 2.35
block 0.5 * (cbX1 - cbX0), 0.005, 0.85
del 1
add cbX1, -cbY1 + 0.05, 2.2
block 0.005, cbY1 - cbY0 - 0.1, 1.0
del 1
add cbX0 + 0.1, -cbY0, 2.4
block 0.3 * (cbX1 - cbX0), 0.005, 0.75
del 1
! 起伏シリンダ（旋回体からブームの 0.35 の所。太いシリンダと細いロッド）
material "cr_steel"
xe = -pivB + 0.35 * bL * cos(bA)
ze = pivH + 0.35 * bL * sin(bA)
x0q = 0.9
y0q = 0
z0q = 1.9
x1q = 0.9 + 0.6 * (xe - 0.9)
y1q = 0
z1q = 1.9 + 0.6 * (ze - 1.9)
rq = 0.13
gosub "seg3"
material "cr_rim"
x0q = x1q
z0q = z1q
x1q = xe
z1q = ze
rq = 0.07
gosub "seg3"
material "cr_steel"
! ブーム（根元から段ごとに細く）
add -pivB, 0, pivH
roty -bA
nS = max(1, min(8, nBs))
sL = bL / nS
for k = 1 to nS
	bw = bmW - (k - 1) * 0.06
	ov = 0
	if k > 1 then ov = 0.05
	! 箱形の段（角を落とした八角形の断面）
	material "cr_boom"
	bh = bw * 1.1
	cc = bw * 0.12
	add (k - 1) * sL - ov, 0, 0
	roty 90
	prism 8, sL + ov, \
		-bh / 2, -bw / 2 + cc, -bh / 2 + cc, -bw / 2, bh / 2 - cc, -bw / 2, bh / 2, -bw / 2 + cc, \
		bh / 2, bw / 2 - cc, bh / 2 - cc, bw / 2, -bh / 2 + cc, bw / 2, -bh / 2, bw / 2 - cc
	del 2
	! 段の先の継ぎ目の帯
	if k < nS then
		material "cr_steel"
		add k * sL - 0.08, -bw / 2 - 0.01, -bh / 2 - 0.01
		block 0.08, bw + 0.02, bh + 0.02
		del 1
	endif
next k
! ブームの先（ブームヘッドと3枚のシーブ）
material "cr_steel"
add bL - 0.3, -0.3, -0.35
block 0.45, 0.6, 0.7
del 1
for i = -1 to 1
	add bL + 0.1, i * 0.14 - 0.04, 0
	rotx -90
	cylind 0.08, 0.32
	del 2
next i
! ブーム長さのホットスポット（ブームに沿って引く）
hotspot 0, 0, 0, 11, boomL, 1 + 128
hotspot bL, 0, 0, 12, boomL, 2
hotspot -1, 0, 0, 13, boomL, 3
del 2
! ワイヤ・フック・吊り荷（旋回体の座標でブームの先の真下）
material "cr_steel"
for i = -1 to 1 step 2
	add tipX + i * 0.1, 0, hkD + 0.6
	cylind tipZ - hkD - 0.6, 0.012
	del 1
next i
! フックブロック（側板とシーブ）とフック
material "cr_hook"
add tipX - 0.25, -0.18, hkD
block 0.5, 0.04, 0.6
del 1
add tipX - 0.25, 0.14, hkD
block 0.5, 0.04, 0.6
del 1
material "cr_steel"
add tipX, -0.14, hkD + 0.42
rotx -90
cylind 0.28, 0.2
del 2
add tipX, 0, hkD - 0.2
cylind 0.2, 0.06
del 1
material "cr_hook"
add tipX, 0, hkD - 0.55
cone 0.35, 0.03, 0.08, 90, 90
del 1
! フックの高さのホットスポット
hotspot tipX, 0, 0, 14, hkZ, 1 + 128
hotspot tipX, 0, hkD, 15, hkZ, 2
hotspot tipX, 0, -1, 16, hkZ, 3
if ldOn and travel = 0 then
	zl = max(0.0, hkD - 2.6)
	material "cr_load"
	add tipX - 0.75, -0.75, zl
	block 1.5, 1.5, 1.0
	del 1
	! 玉掛けワイヤ（吊り荷の四隅からフックへ）
	material "cr_steel"
	for c = 0 to 3
		x0q = tipX - 0.7 + 1.4 * (c mod 2)
		y0q = -0.7 + 1.4 * int(c / 2)
		z0q = zl + 1.0
		x1q = tipX
		y1q = 0
		z1q = hkD - 0.35
		rq = 0.008
		gosub "seg3"
	next c
endif
del 1
end

"seg3":
	! (x0q, y0q, z0q) から (x1q, y1q, z1q) の円柱（半径 rq。向きは問わない）
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
"""


SCRIPT_VL = """﻿! 移動式クレーン: ホットスポットで引いた姿勢を書き戻す（長さ優先は起伏角、角度優先はブーム長さ。作業半径は届く所まで）
if travel = 0 then
	if prio = 0 then
		if abs(boomA - bA) > 0.01 then parameters boomA = bA
	else
		if abs(boomL - bL) > 0.001 then parameters boomL = bL
	endif
	if abs(hkR - tipX) > 0.001 then parameters hkR = tipX
endif
values "boomL" range [bMin, bMax]
values "prio" 0, 1
values "boomA" range [1, 84]
! アウトリガ: 引いた脚を性能表の張出の段（張出幅の半分）に吸い付ける。張出は車体の幅の半分から最大の段まで
mp = GLOB_MODPAR_NAME
if oSnap and nSs > 0 and (mp = "oFL" or mp = "oFR" or mp = "oRL" or mp = "oRR") then
	vq = oFL
	if mp = "oFR" then vq = oFR
	if mp = "oRL" then vq = oRL
	if mp = "oRR" then vq = oRR
	bq = ss[1] / 2
	for i = 1 to nSs
		if abs(ss[i] / 2 - vq) < abs(bq - vq) then bq = ss[i] / 2
	next i
	if mp = "oFL" then parameters oFL = bq
	if mp = "oFR" then parameters oFR = bq
	if mp = "oRL" then parameters oRL = bq
	if mp = "oRR" then parameters oRR = bq
endif
! outW から4脚へは書き戻さない（Tapir でまとめて入れると GLOB_MODPAR_NAME が outW のまま古い outW で脚を上書きした。2026-11-01）
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
    print(f"ashiba_crane: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
