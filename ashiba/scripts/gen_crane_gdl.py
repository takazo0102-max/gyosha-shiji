"""部品 ashiba_crane（移動式クレーン 1台に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「クレーン リサーチして追加して」。寸法はタダノ GR-250N（Ⅴ）・GR-500N（Ⅰ）・GR-700N-3 の仕様書
（src/ashiba/crane_data.py・crane.py）。原点＝旋回中心の地盤、+X＝車体の前。車体（シャシ・タイヤ）、アウトリガ（前 outF・後ろ outR、
張出幅 outW、ジャッキとフロート fltD）、敷鉄板（厚板鋼板 1,524×3,048×22 を plN 枚。2枚は十字）、上部旋回体（旋回 slew 度・
カウンタウエイトの後端は後端旋回半径 tailR）、ブーム（根元 pivB 後ろ・pivH 高さから boomL を起伏角 boomA で、段ごとに細く）、
起伏シリンダ、フック（ブームの先から tipHk 下）・ワイヤ・吊り荷。平面は車体・アウトリガ・敷鉄板・後端旋回半径の円（立入禁止）・
作業半径の円（wrR）・ブームとフック。敷鉄板は plDraw を外すと描かず（配置では別の部品 ashiba_plate を
アウトリガの下に置く。利用者の指定 2026-11-01: 敷鉄板はホットスポットで広げれるようにして 別オブジェクトにして）。割付と検定は src/ashiba/crane.py、置くのは scripts/crane_run.py。
smartCON Planner のクレーンを手本に（利用者の指定 2026-11-01: ホットスポットで姿勢・揚重判定・ブームの干渉チェック・半径の扇形・
走行姿勢）: 平面のホットスポットでフックの位置 hfX・hfY（どの向きにも引ける。作業半径 hkR と旋回 slew に書き戻す）・旋回 slew（角度）・扇の向き wrDir、3D でブーム長さ boomL と
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
import gdl_draft  # noqa: E402
import gdl_radii  # noqa: E402

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
        _param("Length", "carB", "旋回中心から車体の後端", 4.155),
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
        _param("Length", "tipHk", "ブームの先からフックの掛け位置まで（いちばん上げた所。仕様書の最大地上揚程に合わせた値）", 1.3),
        _param("Length", "hkR", "作業半径（旋回中心からフック。平面のホットスポットで引く）", 12.0),
        _param("Angle", "slew", "旋回角（車体の前から左回り。平面のホットスポット）", 30.0),
        _param("Length", "hfX", "フックの位置 X（平面のホットスポットで引くと作業半径と旋回が変わる）", 10.4),
        _param("Length", "hfY", "フックの位置 Y", 6.0),
        _param("Integer", "prio", "姿勢の優先（0＝ブーム長さ優先＝起伏角が決まる・1＝起伏角優先＝ブーム長さが決まる）", 0),
        _param("Length", "boomL", "ブーム長さ（3D のホットスポット。長さ優先で使う）", 23.45),
        _param("Angle", "boomA", "ブームの起伏角（角度優先で使う。長さ優先では書き戻す）", 56.0),
        _param("Length", "jbL", "ジブの長さ（0＝ジブなし。機種の段: 帳票に）", 0.0),
        _param("Angle", "jbO", "ジブのオフセット角", 5.0),
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
        _param("Boolean", "ldOn", "吊り荷を描く（既定は描かない）", 0),
        _param("Length", "ldW", "揚重物の幅", 1.5),
        _param("Length", "ldD", "揚重物の奥行き", 1.5),
        _param("Length", "ldH", "揚重物の高さ", 1.0),
        _param("Length", "ldS", "吊りしろ（フックの下端から揚重物の上面）", 1.6),
        _param("Boolean", "wrOn", "作業半径を 3D に描く", 0),
        _param("Boolean", "wrShow", "作業半径を平面に描く", 1),
        _param("Boolean", "wrFlip", "作業半径の文字を反転する", 0),
        _param("Boolean", "bmStep", "ブームの長さを性能表の段に吸い付ける（段階ブーム。長さ優先のとき）", 0),
        _param("Boolean", "infoOn", "クレーン情報を 3D に描く", 0),
        *gdl_radii.params(_param),
        _param("RealNum", "texZ", "クレーン情報の文字の高さ（m）", 0.6),
        _param("Integer", "clr", "色の組（1 タダノ 白と青・2 加藤 黄と濃灰・3 灰）", 1),
        _param("Length", "ftZ", "フートピンの高さ（上部原点から）", 1.71),
        _param("Length", "jkUp", "作業時にキャリヤが上がる量", 0.28),
        _param("Integer", "otKind", "アウトリガの形（1 H 型・2 X 型）", 1),
        _param("Length", "jkR", "ジャッキのロッドの半径", 0.05),
        _param("Integer", "cwN", "カウンタウエイトの段", 2),
        _param("Integer", "cyN", "起伏シリンダの本数", 1),
        _param("Length", "cyLf", "下ピン（フートピンから前）", 1.05),
        _param("Length", "cyLd", "下ピン（フートピンから下）", 0.85),
        _param("Length", "cyUa", "上ピン（ブームの軸方向）", 3.365),
        _param("Length", "cyUb", "上ピン（ブームの軸の下）", 0.725),
        _param("Length", "cyD", "シリンダのチューブの径", 0.268),
        _param("Length", "cyR", "シリンダのロッドの径", 0.18),
        _param("Length", "cyT", "シリンダのチューブの長さ", 2.143),
        _param("Integer", "bmSec", "ブームの断面（1 ラウンド・2 六角・3 箱）", 1),
        _param("Boolean", "jbSt", "格納したジブを描く", 1),
        _param("Integer", "shN", "ブームの先の主シーブの枚数", 4),
        _param("Integer", "fallN", "ワイヤの掛数", 8),
        _param("Length", "hkDm", "フックブロックの径", 0.44),
        _param("Length", "hkHt", "フックの高さ", 1.0),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        "\t\t<PenColor Name=\"penEquip\">\n\t\t\t<Description><![CDATA[\"線のペン\"]]></Description>\n"
        "\t\t\t<Value>1</Value>\n\t\t</PenColor>\n",        *gdl_draft.params(),
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
             + """carRr = carB
carLn = carF + carB
plT = 0.022
plA = 1.524
plB = 3.048
! ---- 姿勢: 長さ優先は起伏角を、角度優先はブーム長さを作業半径から ----
bL = max(bMin, min(bMax, boomL))
hR = max(1.0, hkR)
slD = slew
owD = spE
jL = jbL
if travel then jL = 0
if prio = 1 then
	bA = max(1, min(84, boomA))
	if jL < 0.01 then bL = max(bMin, min(bMax, (hR + pivB) / cos(bA)))
else
	if jL > 0.01 then
		! ジブ付きは作業半径から起伏角を解く（ブームとジブの水平の長さの和）
		aL = 1
		aH = 84
		for k = 1 to 24
			aM = (aL + aH) / 2
			if -pivB + bL * cos(aM) + jL * cos(aM - jbO) > hR then
				aL = aM
			else
				aH = aM
			endif
		next k
		bA = (aL + aH) / 2
	else
		cA = min(1, max(0.1045, (hR + pivB) / bL))
		bA = acs(cA)
	endif
endif
if travel then
	! 走行姿勢: ブームを最短で前に倒し、アウトリガを畳む
	bL = bMin
	bA = 0
	slD = 0
	owD = carW - 0.1
endif
tbX = -pivB + bL * cos(bA)
tbZ = pivH + bL * sin(bA)
tipX = tbX
tipZ = tbZ
if jL > 0.01 then
	tipX = tbX + jL * cos(bA - jbO)
	tipZ = tbZ + jL * sin(bA - jbO)
endif
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
! 作業の最小半径（このブームの列で定格のある一番小さい半径）。ジブの性能表は持っていないので、ジブ付きは定格を出さない
rMin = 0
for k = nRr to 1 step -1
	vq = 0
	if jB = 1 and k <= nTc1 then vq = tc1[k]
	if jB = 2 and k <= nTc2 then vq = tc2[k]
	if jB = 3 and k <= nTc3 then vq = tc3[k]
	if jB = 4 and k <= nTc4 then vq = tc4[k]
	if jB = 5 and k <= nTc5 then vq = tc5[k]
	if jB = 6 and k <= nTc6 then vq = tc6[k]
	if jB = 7 and k <= nTc7 then vq = tc7[k]
	if jB = 8 and k <= nTc8 then vq = tc8[k]
	if jB = 9 and k <= nTc9 then vq = tc9[k]
	if jB = 10 and k <= nTc10 then vq = tc10[k]
	if jB = 11 and k <= nTc11 then vq = tc11[k]
	if jB = 12 and k <= nTc12 then vq = tc12[k]
	if vq > 0 then rMin = rr[k]
next k
if jL > 0.01 then rated = 0
capT = rated * sfRate
needT = loadT + hookT + rigT
okL = 0
if rated > 0 and needT <= capT then okL = 1
""" + gdl_radii.master() + gdl_radii.rated_loop('\tiQ = 0\n\tfor k = nRr to 1 step -1\n\t\tif rr[k] >= wiRq[wq] - 0.001 then iQ = k\n\tnext k\n\tif iQ > 0 then\n\t\tif jB = 1 and iQ <= nTc1 then vq = tc1[iQ] * 10\n\t\tif jB = 2 and iQ <= nTc2 then vq = tc2[iQ] * 10\n\t\tif jB = 3 and iQ <= nTc3 then vq = tc3[iQ] * 10\n\t\tif jB = 4 and iQ <= nTc4 then vq = tc4[iQ] * 10\n\t\tif jB = 5 and iQ <= nTc5 then vq = tc5[iQ] * 10\n\t\tif jB = 6 and iQ <= nTc6 then vq = tc6[iQ] * 10\n\t\tif jB = 7 and iQ <= nTc7 then vq = tc7[iQ] * 10\n\t\tif jB = 8 and iQ <= nTc8 then vq = tc8[iQ] * 10\n\t\tif jB = 9 and iQ <= nTc9 then vq = tc9[iQ] * 10\n\t\tif jB = 10 and iQ <= nTc10 then vq = tc10[iQ] * 10\n\t\tif jB = 11 and iQ <= nTc11 then vq = tc11[iQ] * 10\n\t\tif jB = 12 and iQ <= nTc12 then vq = tc12[iQ] * 10\n\tendif\n\tif jL > 0.01 or wiRq[wq] < rMin - 0.001 then vq = 0\n\tvq = vq * sfRate\n') + """""")

SCRIPT_2D_T = """﻿! 移動式クレーン 2D: 車体・アウトリガ・敷鉄板・後端旋回半径（立入禁止）・作業半径の扇・ブームとフック・定格の注記・ホットスポット
! 文字の数は str(数, 1, 0)、小数は長さに余裕を（str(x, 1, 1) は平面図でこの部品の 2D を丸ごと消した。プレビューでは描けていた）
! CAD の平面図の描き方（scripts/gdl_draft.py）: 外形は太線・細部は細線、車体の下のタイヤと旋回輪は破線、作業半径は一点鎖線、
! 後端旋回半径（立入禁止）は二点鎖線。上部旋回体とブームは背景の色で塗って下の車体の線を隠す。縮尺で描き分ける
@HEAD@
pen penEquip
define style "crT" "ＭＳ Ｐゴシック", texSiz, 1, 0
define style "crR" "ＭＳ Ｐゴシック", texSiz, 3, 0
define style "crC" "ＭＳ Ｐゴシック", texSiz, 2, 0
style "crT"
! 車体（キャリヤ）: 外形・前後のバンパー・タイヤ（車体の下なので破線）・旋回輪（上部の下なので破線）
drawindex 10
if mk then
@CARMASK@
endif
drawindex 12
pen pO
rect2 -carRr, -carW / 2, carF, carW / 2
pen pT
if drLv < 3 then
	rect2 carF - 0.25, -carW / 2 + 0.15, carF, carW / 2 - 0.15
	rect2 -carRr, -carW / 2 + 0.15, -carRr + 0.25, carW / 2 - 0.15
	drawindex 40
	line_type ltH
	for i = 1 to nAx
		for s = -1 to 1 step 2
			rect2 ax[i] - whR, s * (carW / 2 - 0.02), ax[i] + whR, s * (carW / 2 - 0.02 - whW)
		next s
		if drLv = 1 then line2 ax[i], -carW / 2 + 0.1 + whW, ax[i], carW / 2 - 0.1 - whW
	next i
	circle2 0, 0, 0.9
	line_type ltS
	drawindex 12
endif
for e = -1 to 1 step 2
	xo = outF
	if e < 0 then xo = -outR
	for s = -1 to 1 step 2
		lg = lFL
		if e > 0 and s < 0 then lg = lFR
		if e < 0 and s > 0 then lg = lRL
		if e < 0 and s < 0 then lg = lRR
		xs = xo - (s < 0) * outSh
		! アウトリガのビーム（箱 0.3 幅）・ジャッキ・フロート（太線）、敷鉄板（細線）
		drawindex 14
		pen pO
		rect2 xs - 0.15, s * (carW / 2 - 0.2), xs + 0.15, s * lg
		if fltA > 0.01 then
			rect2 xs - fltB / 2, s * lg - fltA / 2, xs + fltB / 2, s * lg + fltA / 2
		else
			circle2 xs, s * lg, fltD / 2
		endif
		pen pT
		if drLv < 3 then circle2 xs, s * lg, 0.12
		! 張出の寸法（車体の芯からジャッキまで mm）
		if drLv < 3 then
			drawindex 50
			pen penEquip
			add2 xs + max(fltB, fltD) / 2 + 0.15, s * lg
			rot2 -SYMB_ROTANGLE
			text2 0, 0, str(round_int(lg * 1000), 1, 0)
			del 2
			pen pT
		endif
		drawindex 8
		if plDraw then
			rect2 xs - plB / 2, s * lg - plA / 2, xs + plB / 2, s * lg + plA / 2
			if plN >= 2 then rect2 xs - plA / 2, s * lg - plB / 2, xs + plA / 2, s * lg + plB / 2
		endif
	next s
next e
! 立入禁止（上部旋回体の後端旋回半径）: 二点鎖線
drawindex 45
pen pZ
line_type ltZ
circle2 0, 0, tailR
line_type ltC
! 作業半径の扇（吊荷ごとの半径と、今のフックの半径。wrSpan 360 は円）
nC = (nWr + 1) * wrShow
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
		pen penEquip
		add2 rC * cos(aT), rC * sin(aT)
		rot2 -SYMB_ROTANGLE + 180 * wrFlip
		text2 0, 0, "R" + str(round_int(rC * 1000), 1, 0)
		del 2
		pen pZ
	endif
next i
! 作業の最小半径
if rMin > 0.1 and travel = 0 then
	line_type ltZ
	circle2 0, 0, rMin
	pen penEquip
	add2 rMin * cos(slD + 40), rMin * sin(slD + 40)
	rot2 -SYMB_ROTANGLE
	text2 0, 0, "最小 R" + str(round_int(rMin * 1000), 1, 0)
	del 2
	pen pZ
endif
line_type ltS
if wrSpan < 359.9 and wrShow then
	line_type ltC
	rM = tipX
	for i = 1 to nWr
		rM = max(rM, wr[i])
	next i
	line2 0, 0, rM * cos(wrDir - wrSpan / 2), rM * sin(wrDir - wrSpan / 2)
	line2 0, 0, rM * cos(wrDir + wrSpan / 2), rM * sin(wrDir + wrSpan / 2)
	line_type ltS
endif
! 上部旋回体とブーム（旋回角で回す）
rot2 slD
! 上部旋回体（後ろはカウンタウエイトの円弧＝後端旋回半径）・運転室（右前）
uw = min(upW / 2, tailR * 0.98)
xc = -sqr(tailR ^ 2 - uw ^ 2)
au = asn(uw / tailR)
if mk then
	drawindex 20
@UPMASK@
endif
drawindex 30
pen pO
arc2 0, 0, tailR, 180 - au, 180 + au
line2 xc, uw, 1.6, uw
line2 xc, -uw, 1.6, -uw
line2 1.6, -uw, 1.6, uw
rect2 cbX0, -cbY1, cbX1, -cbY0
pen pT
if drLv < 3 then line2 xc + 0.9, -uw, xc + 0.9, uw
if drLv = 1 then line2 cbX1 - 0.25, -cbY1, cbX1 - 0.25, -cbY0
! ブーム（段ごとに細く、全段を重ねて描く）・ブームの先のシーブ・フック。段の根元は平面に写した長さで
! （ブームに沿った長さのままだと、起こしたブームの上の段がフックの先へはみ出した。2026-11-02 実機の平面図）
nb = max(1, min(6, nBs))
if mk then
	drawindex 32
@BOOMMASK@
endif
drawindex 34
pen pO
rect2 -pivB, -bmW / 2, tbX, bmW / 2
pen pT
if drLv < 3 then
	for k = 2 to nb
		wk = bmW * (1 - 0.13 * (k - 1)) / 2
		xk = -pivB + (k - 1) * (bL - 1.2) * cos(bA) / nb
		rect2 xk, -wk, tbX, wk
	next k
	line_type ltC
	line2 -pivB - 0.5, 0, tbX + 0.8, 0
	line_type ltS
endif
pen pO
rect2 tbX - 0.35, -bmW / 2, tbX + 0.25, bmW / 2
if jL > 0.01 then
	! ジブ（先へ細くなる）
	line2 tbX, -bmW / 3, tipX, -bmW / 6
	line2 tbX, bmW / 3, tipX, bmW / 6
	line2 tipX, -bmW / 6, tipX, bmW / 6
endif
pen pT
circle2 tipX, 0, 0.3
if drLv = 1 then circle2 tipX, 0, 0.12
pen pO
if ldOn and travel = 0 then
	drawindex 36
	rect2 tipX - 0.75, -0.75, tipX + 0.75, 0.75
	if drLv < 3 then
		pen pT
		line2 tipX - 0.75, -0.75, tipX + 0.75, 0.75
		line2 tipX - 0.75, 0.75, tipX + 0.75, -0.75
	endif
endif
del 1
! フックのホットスポット（X と Y の組を同じ点に置いて、どの向きにも引ける。前後は作業半径、横は旋回）
if travel = 0 then
	xF = tipX * cos(slD)
	yF = tipX * sin(slD)
	hotspot2 0, yF, 1, hfX, 1 + 128
	hotspot2 xF, yF, 2, hfX, 2
	hotspot2 -1, yF, 3, hfX, 3
	hotspot2 xF, 0, 31, hfY, 1 + 128
	hotspot2 xF, yF, 32, hfY, 2
	hotspot2 xF, -1, 33, hfY, 3
endif
! 旋回の中心（一点鎖線の十字）
drawindex 45
pen pT
line_type ltC
line2 -1.2, 0, 1.2, 0
line2 0, -1.2, 0, 1.2
line_type ltS
! 定格の注記（フックの所）と機種・姿勢の注記（車体の後ろ）
drawindex 50
pen penEquip
xT = tipX * cos(slD)
yT = tipX * sin(slD)
dT = texSiz * GLOB_SCALE / 1000 * 1.6
if travel = 0 then
	sOk = ""
	if okL = 0 then sOk = " 超過"
	add2 xT, yT
	rot2 -SYMB_ROTANGLE
	if jL > 0.01 then
		text2 0, 0.6 + dT, "ジブ " + str(round_int(jL * 1000), 1, 0) + " 定格は性能表で"
	else
		text2 0, 0.6 + dT, "定格 " + str(rated, 5, 2) + "t×" + str(sfRate, 4, 2) + "＝" + str(capT, 5, 2) + "t"
	endif
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
if drLv < 3 then text2 0, yA - 2 * dT, tS
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
@RADII@hotspot2 0, 0, 7, wrDir, 6
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


def _script_2d() -> str:
    """2D スクリプト: 型（SCRIPT_2D_T）に描き方の決めと隠す塗りの多角形を入れる."""
    D = gdl_draft
    t = "\t"
    rep = {
        "@HEAD@": D.head().rstrip("\n"),
        "@CARMASK@": D.rect_mask("-carRr", "-carW / 2", "carF", "carW / 2", t).rstrip("\n"),
        "@UPMASK@": D.mask([("1.6", "-uw"), ("1.6", "uw")] + D.arc_pts("tailR", "180 - au", "180 + au"), t).rstrip("\n"),
        "@BOOMMASK@": D.rect_mask("-pivB", "-bmW / 2", "tipX + 0.25", "bmW / 2", t).rstrip("\n"),
    }
    out = SCRIPT_2D_T.replace("@RADII@", gdl_radii.plan("pZ", "ltS", "penEquip", "crT"))
    for k, v in rep.items():
        assert k in out, k
        out = out.replace(k, v)
    return out


SCRIPT_2D = _script_2d()


SCRIPT_3D = """﻿! 移動式クレーン 3D（タダノ GR-250N・GR-500N・GR-700N の寸法の目安）
! ---- 色の組（1 タダノ 白と青・2 加藤 黄と濃灰・3 灰）。同じ名前の define material は 1回だけ ----
bR = 0.94
bG = 0.96
bBl = 0.97
fR = 0.03
fG = 0.34
fBl = 0.66
if clr = 2 then
	bR = 0.97
	bG = 0.78
	bBl = 0.03
	fR = 0.20
	fG = 0.22
	fBl = 0.22
endif
if clr = 3 then
	bR = 0.70
	bG = 0.72
	bBl = 0.74
	fR = 0.30
	fG = 0.31
	fBl = 0.33
endif
define material "cr_body" 2, bR, bG, bBl
define material "cr_blue" 2, fR, fG, fBl
define material "cr_boom" 2, bR, bG, bBl
define material "cr_cw" 2, 0.22, 0.23, 0.24
define material "cr_steel" 2, 0.55, 0.57, 0.60
define material "cr_plate" 2, 0.35, 0.36, 0.38
define material "cr_tire" 2, 0.10, 0.10, 0.10
define material "cr_hook" 2, 0.95, 0.75, 0.10
define material "cr_load" 2, 0.70, 0.50, 0.30
define material "cr_glass" 2, 0.30, 0.45, 0.60
define material "cr_rim" 2, 0.80, 0.80, 0.78
define material "cr_lamp" 2, 0.95, 0.60, 0.10
define material "cr_head" 2, 0.92, 0.93, 0.85
define material "cr_tail" 2, 0.75, 0.10, 0.10
resol 16
plH = plT * plN
! 高さの基準（加藤の DXF の上部原点。作業時はキャリヤが jkUp 上がってタイヤが浮く）
cUp = jkUp * (travel = 0)
cTop = pivH - ftZ - jkUp
uZ = cTop + cUp
sX = pivB / 2.6
sZ = ftZ / 1.71
xT = tailR / sX
hwU = min(carW / 2 - 0.05, 0.477 * carW)
yP = bmW / 2 + 0.05
zB = cTop + cUp - 0.48
! ---- 敷鉄板（アウトリガ1脚に plN 枚。2枚は十字）とフロート・ジャッキ・アウトリガの外箱と内箱 ----
for e = -1 to 1 step 2
	xo = outF
	if e < 0 then xo = -outR
	for s = -1 to 1 step 2
		lg = lFL
		if e > 0 and s < 0 then lg = lFR
		if e < 0 and s > 0 then lg = lRL
		if e < 0 and s < 0 then lg = lRR
		if travel then lg = carW / 2 - 0.05
		xs = xo - (s < 0) * outSh
		yo = s * lg
		if plDraw then
			material "cr_plate"
			add xs - plB / 2, yo - plA / 2, 0
			block plB, plA, plT
			del 1
			if plN >= 2 then
				add xs - plA / 2, yo - plB / 2, plT
				block plA, plB, plT
				del 1
			endif
		endif
		! 箱（H 型は真横、X 型は車体の芯の近くから斜めに出る）
		xb = xs
		if otKind = 2 then xb = xo * 0.62
		dxO = xs - xb
		lO = sqr(dxO * dxO + yo * yo)
		aO = 90 * s
		if abs(dxO) > 0.0001 then aO = atn(yo / dxO) + 180 * (dxO < 0)
		lOut = min(lO, (carW / 2) / max(0.2, abs(sin(aO))))
		add xb, 0, zB
		rotz aO
		material "cr_blue"
		add 0, -0.17, 0
		block lOut, 0.34, 0.44
		del 1
		! 内箱（伸ばした分が見える）と先の縦の箱
		material "cr_body"
		if lO > lOut then
			add lOut - 0.05, -0.12, 0.05
			block lO - lOut + 0.05, 0.24, 0.32
			del 1
		endif
		del 2
		material "cr_blue"
		add xs - 0.19, yo - 0.19, zB - 0.04
		block 0.38, 0.38, 0.54
		del 1
		! ジャッキ（チューブとロッド）とフロート
		zf = plH
		if travel then zf = zB - 0.5
		material "cr_steel"
		if fltA > 0.01 then
			add xs - fltB / 2, yo - fltA / 2, zf
			block fltB, fltA, 0.07
			del 1
		else
			add xs, yo, zf
			cylind 0.07, fltD / 2
			del 1
		endif
		add xs, yo, zf + 0.07
		cone 0.1, jkR * 1.5, jkR, 90, 90
		del 1
		add xs, yo, zf + 0.15
		cylind max(0.05, zB - zf - 0.15), jkR
		del 1
		material "cr_blue"
		zt = max(zf + 0.2, zB - 0.65)
		add xs, yo, zt
		cylind zB - zt, jkR * 1.4
		del 1
	next s
next e
! ---- キャリヤ（作業時は jkUp 上がる）----
add 0, 0, cUp
material "cr_blue"
add -carRr, -carW / 2 + 0.12, 0.62
block carLn, carW - 0.24, cTop - 0.62
del 1
! デッキ（上面の板）と前後の傾き
material "cr_cw"
add -carRr + 0.05, -carW / 2 + 0.1, cTop - 0.02
block carLn - 0.1, carW - 0.2, 0.02
del 1
material "cr_blue"
! 後ろのエンジン室（旋回体の後端より後ろだけ）と煙突・ガラリ
xH = -tailR - 0.12
if xH + carRr > 0.3 then
	material "cr_body"
	add -carRr + 0.03, -carW / 2 + 0.16, cTop
	block xH + carRr - 0.03, carW - 0.32, 0.5
	del 1
	material "cr_cw"
	for i = 0 to 5
		add -carRr + 0.08 + i * (xH + carRr - 0.1) / 6, carW / 2 - 0.5, cTop + 0.5
		block (xH + carRr - 0.1) / 9, 0.32, 0.012
		del 1
	next i
	material "cr_steel"
	add -carRr + 0.25, -carW / 2 + 0.4, cTop + 0.5
	cylind 0.55, 0.06
	del 1
endif
! 前の縞板のデッキの手すり
material "cr_cw"
xFd = max(tailR * 0, cbX1 + 0.35)
if carF - xFd > 0.4 then
	add xFd, -carW / 2 + 0.12, cTop
	block carF - xFd - 0.08, carW - 0.24, 0.18
	del 1
endif
for i = 1 to nAx
	for s = -1 to 1 step 2
		! タイヤ（作業時は地面から上がる）・ホイール・ハブ・ボルト
		material "cr_tire"
		add ax[i], s * (carW / 2 - whW / 2 - 0.02), whR + 0.05 - jkUp * 0
		rotx 90
		addz -whW / 2
		cylind whW, whR
		material "cr_blue"
		addz -0.012
		cylind whW + 0.024, whR * 0.52
		material "cr_rim"
		addz -0.012
		cylind whW + 0.048, whR * 0.22
		del 5
		! フェンダー（タイヤの上）
		material "cr_body"
		add ax[i] - whR - 0.1, s * (carW / 2 - 0.02) - (s + 1) * (whW + 0.06) / 2, 2 * whR + 0.08
		block 2 * whR + 0.2, whW + 0.06, 0.06
		del 1
	next s
next i
! バンパー（前後）・ランプ・ミラー
material "cr_cw"
add carF - 0.1, -carW / 2 + 0.15, 0.6
block 0.15, carW - 0.3, 0.35
del 1
add -carRr - 0.1, -carW / 2 + 0.15, 0.6
block 0.15, carW - 0.3, 0.35
del 1
for s = -1 to 1 step 2
	material "cr_head"
	add carF + 0.05, s * (carW / 2 - 0.4) - 0.1, 0.98
	block 0.01, 0.2, 0.12
	del 1
	material "cr_lamp"
	add carF + 0.05, s * (carW / 2 - 0.65) - 0.05, 0.98
	block 0.01, 0.1, 0.12
	del 1
	material "cr_tail"
	add -carRr - 0.11, s * (carW / 2 - 0.4) - 0.12, 0.98
	block 0.01, 0.24, 0.12
	del 1
	! 前のミラー（棒の先の丸い鏡）
	material "cr_cw"
	x0q = carF - 0.3
	y0q = s * (carW / 2 - 0.15)
	z0q = cTop + 0.05
	x1q = carF - 0.15
	y1q = s * (carW / 2 + 0.2)
	z1q = cTop + 0.75
	rq = 0.015
	gosub "seg3"
	add x1q, y1q, z1q
	roty 90
	cylind 0.03, 0.12
	del 2
next s
! 前のはしごと横の昇降ステップ
material "cr_steel"
for k = 0 to 3
	add carF + 0.03, -carW / 2 + 0.35, 0.55 + k * (cTop - 0.55) / 4
	block 0.04, 0.48, 0.025
	del 1
next k
for s = -1 to 1 step 2
	for k = 0 to 2
		add -0.45, s * (carW / 2 + 0.02) - 0.14, 0.45 + k * (cTop - 0.5) / 3
		block 0.9, 0.14, 0.025
		del 1
	next k
next s
del 1
! ブームの先を平面のどの向きにも引く（平面の 1〜3・31〜33 と同じ組）
if travel = 0 then
	xF = tipX * cos(slD)
	yF = tipX * sin(slD)
	zF = tipZ + 0.3
	hotspot 0, yF, zF, 41, hfX, 1 + 128
	hotspot xF, yF, zF, 42, hfX, 2
	hotspot -1, yF, zF, 43, hfX, 3
	hotspot xF, 0, zF, 44, hfY, 1 + 128
	hotspot xF, yF, zF, 45, hfY, 2
	hotspot xF, -1, zF, 46, hfY, 3
endif
! ---- 上部旋回体（旋回角 slew で回す。Z は上部原点から。外形は加藤 SR-250RfⅡ の DXF を機種の根元の位置で伸ばす）----
rotz slD
add 0, 0, uZ
material "cr_cw"
cylind 0.1 * sZ, 0.7 * sX
add -1.48 * sX, -hwU + 0.1, 0.1 * sZ
block 2.88 * sX, 2 * hwU - 0.2, 0.05 * sZ
del 1
mul sX, 1, sZ
! 運転室の反対の箱と、運転室の下の箱（後ろは斜めに下がる）
material "cr_body"
yA = 0.43 * bmW / 0.53
yB = hwU
put -1.48, 0.15, -1.68, 0.39, -2.34, 0.6, -2.68, 0.6, -2.68, 1.28, -2.24, 1.28, -1.73, 1.155, -1.73, 0.15
gosub "sideP"
yB = -yA
yA = -hwU
put -1.48, 0.15, -1.68, 0.39, -2.34, 0.6, -2.68, 0.6, -2.68, 1.28, -2.24, 1.28, -1.68, 1.155, -0.29, 0.825, -0.29, 0.15
gosub "sideP"
! フートの側板 2 枚（ブームの根元を受ける。上端はピンの上へ出る）
material "cr_blue"
for s = -1 to 1 step 2
	yA = s * yP - 0.05
	yB = s * yP + 0.05
	put -2.77, 1.865, -2.37, 1.865, -0.655, 1.3, -0.255, 1.065, -0.29, 0.15, -1.48, 0.15, -2.455, 1.28, -2.76, 1.64
	gosub "sideP"
next s
del 1
! カウンタウエイト（後ろの丸い面。半径 tailR）と段の目地
material "cr_cw"
aC = asn(min(0.98, hwU / tailR))
xC = 2.68 * sX
for k = 0 to 8
	aq = 180 + aC - k * aC / 4
	put tailR * cos(aq), tailR * sin(aq)
next k
put -xC, -hwU, -xC, hwU
add 0, 0, 0.6 * sZ
prism nsp / 2, 0.68 * sZ, get(nsp)
del 1
material "cr_steel"
for k = 1 to cwN - 1
	add -tailR + 0.01, -hwU - 0.005, 0.6 * sZ + k * 0.68 * sZ / cwN
	block tailR - xC, 2 * hwU + 0.01, 0.012
	del 1
next k
! 吊り金具（目）
material "cr_steel"
for k = -1 to 1 step 2
	add -2.05 * sX, k * yP, 1.56 * sZ
	rotx -90
	cylind 0.03, 0.09
	del 2
next k
! ウインチ（主巻・補巻のドラムとフランジ）
for k = 0 to 1
	xD = -pivB - 0.05 + k * 0.72 * sX
	zD = (1.28 - k * 0.42) * sZ
	material "cr_cw"
	add xD, -yP + 0.06, zD
	rotx -90
	cylind 2 * yP - 0.12, 0.2 * sZ
	del 2
	material "cr_steel"
	for s = -1 to 1 step 2
		add xD, s * (yP - 0.08) - 0.02, zD
		rotx -90
		cylind 0.04, 0.27 * sZ
		del 2
	next s
next k
! 後ろの案内シーブ 2 枚と腕
material "cr_steel"
xG = -2.91 * sX
zG = 1.785 * sZ
for s = -1 to 1 step 2
	add xG, s * 0.26 - 0.03, zG
	rotx -90
	cylind 0.06, 0.165 * sZ
	del 2
	x0q = -3.0 * sX
	y0q = s * 0.26
	z0q = zG
	x1q = -2.845 * sX
	y1q = s * 0.26
	z1q = 1.28 * sZ
	rq = 0.03
	gosub "seg3"
next s
! 運転室（側面の多角形。前は下へとがる）
mul 1, 1, sZ
material "cr_body"
yA = -cbY1
yB = -cbY0
xb = cbX0
xf = cbX1
put xb, 0.15, xb + 0.13, 1.64, xb + 0.2, 1.67, xf - 0.75, 1.67, xf, 0.54, xf - 0.35, 0.15
gosub "sideP"
! 窓: 両側のドアの窓、前の大きい窓、後ろの小窓、屋根のひさし
material "cr_glass"
for s = 0 to 1
	yA = -cbY1 - 0.004 + s * (cbY1 - cbY0)
	yB = yA + 0.008
	put xb + 0.28, 0.78, xb + 0.28, 1.52, xf - 0.72, 1.52, xf - 0.2, 0.78
	gosub "sideP"
next s
yA = -cbY1 + 0.06
yB = -cbY0 - 0.06
put xf - 0.74, 1.62, xf - 0.05, 0.6, xf - 0.02, 0.62, xf - 0.71, 1.65
gosub "sideP"
add xb - 0.004, -cbY1 + 0.15, 0.9
block 0.008, cbY1 - cbY0 - 0.3, 0.55
del 1
material "cr_cw"
add xb + 0.2, -cbY1 - 0.03, 1.67
block xf - xb - 0.9, cbY1 - cbY0 + 0.06, 0.03
del 1
add xb + 0.9 * (xf - xb) * 0.4, -cbY1 - 0.008, 0.78
block 0.05, 0.012, 0.74
del 1
! 運転室の前の足場と手すり（ブームの側）・ミラー・ワイパー
material "cr_steel"
add xf - 0.6, -cbY0 + 0.0, 0.4
block 0.55, cbY0 - 0.04, 0.03
del 1
rq = 0.015
for k = 0 to 1
	x0q = xf - 0.58 + k * 0.5
	y0q = -0.1
	z0q = 0.42
	x1q = x0q
	y1q = y0q
	z1q = 1.25
	gosub "seg3"
next k
x0q = xf - 0.58
x1q = xf - 0.08
y0q = -0.1
y1q = -0.1
z0q = 1.25
z1q = 1.25
gosub "seg3"
material "cr_cw"
add xf + 0.1, -cbY1 - 0.1, 1.05
block 0.03, 0.12, 0.3
del 1
del 1
! 後ろの斜面の階段のステップ
material "cr_steel"
for k = 0 to 3
	add -2.3 * sX + k * 0.17 * sX, hwU - 0.55, (1.27 - k * 0.04) * sZ + 0.012
	block 0.14 * sX, 0.5, 0.02
	del 1
next k
! フートピンのボスと軸・起伏シリンダの下ピンの軸
xL = -pivB + cyLf
zL = ftZ - cyLd
material "cr_steel"
add -pivB, -yP - 0.08, ftZ
rotx -90
cylind 2 * yP + 0.16, 0.06
del 2
for s = -1 to 1 step 2
	add -pivB, s * (yP + 0.05) - 0.035, ftZ
	rotx -90
	cylind 0.07, 0.125
	del 2
next s
add xL, -yP, zL
rotx -90
cylind 2 * yP, 0.05
del 2
! ---- ブーム（基本ブームは長さ一定、先の段が同じ量ずつ出る。主シーブがブーム長さの先に来るよう軸を少し上へ振る）----
h1 = bmW * 1.35
cZ = -0.30 * h1
sD = 0.82 * h1
xBt = sqr(max(1, bL * bL - sD * sD))
bB = bA + atn(sD / xBt)
nS = max(2, min(8, nBs))
Lb = bMin * 0.92
! 起伏シリンダ（下ピンは旋回体、上ピンは基本ブームに固定。ブームを伸ばしても長さは変わらない）
xU = -pivB + cyUa * cos(bB) + cyUb * sin(bB)
zU = ftZ + cyUa * sin(bB) - cyUb * cos(bB)
lC = sqr((xU - xL) ^ 2 + (zU - zL) ^ 2)
tC = min(cyT, lC - 0.15)
for k = 1 to cyN
	yC = 0
	if cyN = 2 then yC = (2 * k - 3) * 0.38 * bmW
	x0q = xL
	y0q = yC
	z0q = zL
	x1q = xL + (xU - xL) * tC / lC
	y1q = yC
	z1q = zL + (zU - zL) * tC / lC
	rq = cyD / 2
	material "cr_blue"
	gosub "seg3"
	x0q = x1q
	z0q = z1q
	x1q = xU
	z1q = zU
	rq = cyR / 2
	material "cr_rim"
	gosub "seg3"
next k
add -pivB, 0, ftZ
roty -bB
! フート（くさび形に絞る）と上面の補強
material "cr_boom"
yA = -bmW / 2 + 0.03
yB = bmW / 2 - 0.03
put -0.12, 0.1, -0.12, -0.1, 0.28, cZ - h1 / 2, 0.28, cZ + h1 / 2
gosub "sideP"
! 上ピンの金具
material "cr_blue"
zb = cZ - h1 / 2
for s = -1 to 1 step 2
	yC = 0
	if cyN = 2 then yC = 0.38 * bmW
	yA = s * (abs(yC) + 0.12) - 0.02
	yB = yA + 0.04
	put cyUa - 0.32, zb + 0.02, cyUa + 0.3, zb + 0.02, cyUa + 0.12, -cyUb - 0.1, cyUa - 0.12, -cyUb - 0.1
	gosub "sideP"
next s
add cyUa, -abs(yC) - 0.14, -cyUb
rotx -90
cylind 2 * abs(yC) + 0.28, 0.05
del 2
! 段
for k = 1 to nS
	wS = bmW * (1 - 0.075 * (k - 1))
	hS = h1 * (1 - 0.085 * (k - 1))
	eK = Lb + (k - 1) * (xBt - 0.25 - Lb) / (nS - 1)
	sK = 0.28
	if k > 1 then sK = Lb + (k - 2) * (xBt - 0.25 - Lb) / (nS - 1) - 0.05
	lS = eK - sK
	material "cr_boom"
	add sK, 0, cZ + 0.0
	roty 90
	gosub "sect"
	del 2
	if k < nS then
		! 段の先の帯
		material "cr_steel"
		wS = wS + 0.03
		hS = hS + 0.03
		lS = 0.07
		add eK - 0.07, 0, cZ
		roty 90
		gosub "sect"
		del 2
	endif
next k
! 上面の長さ検出のケーブル
material "cr_cw"
add 0.4, bmW * 0.25, cZ + h1 / 2 + 0.01
block Lb - 0.6, 0.03, 0.02
del 1
! ケーブルリール（タダノ。基本ブームの左）
if clr = 1 then
	material "cr_steel"
	add pivB * 0 + 0.75 * sX * 2.4, bmW / 2 + 0.01, cZ
	rotx -90
	cylind 0.05, 0.4 * sZ
	material "cr_cw"
	addz 0.05
	cylind 0.02, 0.24 * sZ
	del 3
endif
! 格納したジブ（基本ブームの右の下に抱える）
if jL < 0.01 and jbSt then
	material "cr_body"
	lJ = Lb * 0.78
	yJ = -bmW / 2 - 0.2
	zJ = cZ - h1 * 0.15
	rq = 0.03
	for sy = -1 to 1 step 2
		for sz = -1 to 1 step 2
			x0q = 0.9
			y0q = yJ + sy * 0.1
			z0q = zJ + sz * 0.17
			x1q = 0.9 + lJ
			y1q = y0q
			z1q = z0q
			gosub "seg3"
		next sz
	next sy
	rq = 0.014
	nJ = int(lJ / 0.45)
	for i = 0 to nJ - 1
		sg = 1 - 2 * (i mod 2)
		x0q = 0.9 + i * lJ / nJ
		x1q = x0q + lJ / nJ
		for sy = -1 to 1 step 2
			y0q = yJ + sy * 0.1
			y1q = y0q
			z0q = zJ - sg * 0.17
			z1q = zJ + sg * 0.17
			gosub "seg3"
		next sy
	next i
endif
! ブームの先（側板・主シーブ・シングルトップ・上の案内シーブ。形は加藤 SL-500RfⅢ の DXF）
hC = h1 / 0.89
wE = bmW * (1 - 0.075 * (nS - 1))
add xBt, 0, -sD
material "cr_blue"
mul hC, 1, hC
for s = -1 to 1 step 2
	yA = s * wE / 2 - 0.015
	yB = s * wE / 2 + 0.015
	put -0.19, 1.0, -0.19, 0.75, -0.155, 0.7, -0.155, 0.2, -0.2, -0.05, 0, -0.205, 0.21, -0.22, 0.33, 0, 0.22, 0.3, 0.21, 0.7, 0.35, 1.1, 0.38, 1.2, 0, 1.2
	gosub "sideP"
next s
del 1
material "cr_steel"
nSh = max(1, min(6, shN))
for k = 1 to nSh
	add 0, (k - (nSh + 1) / 2) * 0.07 * hC - 0.0275, 0
	rotx -90
	cylind 0.055, 0.186 * hC
	del 2
next k
add 0.44 * hC, -0.03, -0.185 * hC
rotx -90
cylind 0.06, 0.2 * hC
del 2
add 0, -0.03, 1.09 * hC
rotx -90
cylind 0.06, 0.175 * hC
del 2
for s = -1 to 1 step 2
	x0q = 0.1 * hC
	y0q = s * wE / 4
	z0q = 0
	x1q = 0.44 * hC
	y1q = s * 0.05
	z1q = -0.185 * hC
	rq = 0.025
	gosub "seg3"
next s
del 1
del 2
! ブーム長さのホットスポット（ブームに沿って引く）
add -pivB, 0, ftZ
roty -bA
hotspot 0, 0, 0, 11, boomL, 1 + 128
hotspot bL, 0, 0, 12, boomL, 2
hotspot -1, 0, 0, 13, boomL, 3
del 2
del 1
! ブームの先で起伏角を動かすホットスポット（長さはそのまま）
hotspot -pivB, 0, pivH, 21, boomA, 6
hotspot -pivB + 1, 0, pivH, 22, boomA, 4
hotspot tbX, 0, tbZ + 0.6, 23, boomA, 5
hotspot -pivB, -1, pivH, 24, boomA, 7
if jL > 0.01 then
	! ジブ（箱の弦材とラチス。先へ細くなる）とジブ長さのホットスポット
	add tbX, 0, tbZ
	roty -(bA - jbO)
	material "cr_boom"
	wJ = bmW * 0.6
	rq = 0.03
	for sy = -1 to 1 step 2
		for sz = -1 to 1 step 2
			x0q = 0
			y0q = sy * wJ / 2
			z0q = sz * wJ / 2
			x1q = jL
			y1q = sy * wJ / 4
			z1q = sz * wJ / 4
			gosub "seg3"
		next sz
	next sy
	nJ = max(2, int(jL / max(wJ, 0.5)))
	rq = 0.015
	for i = 0 to nJ - 1
		sg = 1 - 2 * (i mod 2)
		wa = wJ * (1 - 0.5 * i / nJ) / 2
		wb = wJ * (1 - 0.5 * (i + 1) / nJ) / 2
		x0q = i * jL / nJ
		x1q = (i + 1) * jL / nJ
		for sz = -1 to 1 step 2
			y0q = -sg * wa
			y1q = sg * wb
			z0q = sz * wa
			z1q = sz * wb
			gosub "seg3"
		next sz
	next i
	material "cr_steel"
	add jL - 0.1, -0.03, 0
	rotx -90
	add 0, 0, -0.03
	cylind 0.06, 0.18
	del 3
	hotspot 0, 0, 0, 25, jbL, 1 + 128
	hotspot jL, 0, 0, 26, jbL, 2
	hotspot -1, 0, 0, 27, jbL, 3
	del 2
endif
! ワイヤ（掛数の本数）・フックブロック・フック（旋回体の座標でブームの先の真下）
hkB = hkHt - hkDm / 2
material "cr_steel"
nW = max(2, min(12, fallN))
for i = 1 to nW
	add tipX, (i - (nW + 1) / 2) * 0.05, hkD + hkB
	cylind tipZ - hkD - hkB, 0.009
	del 1
next i
! 側板（丸）とシーブ
material "cr_hook"
for s = -1 to 1 step 2
	add tipX, s * (hkDm * 0.32) - 0.02, hkD + hkB
	rotx -90
	cylind 0.04, hkDm / 2
	del 2
next s
material "cr_steel"
add tipX, -hkDm * 0.3, hkD + hkB
rotx -90
cylind hkDm * 0.6, hkDm * 0.4
del 2
add tipX, 0, hkD + hkB - hkDm * 0.62
cylind hkDm * 0.2, hkDm * 0.16
del 1
add tipX, 0, hkD + hkHt * 0.42
cylind hkB - hkDm * 0.62 - hkHt * 0.42 + 0.02, 0.05
del 1
! フック（横から見た C の形）
material "cr_hook"
add tipX, 0, hkD
mul hkHt, 1, hkHt
yA = -0.035
yB = 0.035
put -0.04, 0.45, 0.04, 0.45, 0.05, 0.32, 0.17, 0.2, 0.19, 0.09, 0.12, 0.01, 0.0, 0.0, -0.13, 0.05, -0.19, 0.14, -0.13, 0.2, -0.1, 0.13, -0.03, 0.08, 0.07, 0.09, 0.1, 0.15, -0.03, 0.26
gosub "sideP"
del 2
! フックの高さのホットスポット
hotspot tipX, 0, 0, 14, hkZ, 1 + 128
hotspot tipX, 0, hkD, 15, hkZ, 2
hotspot tipX, 0, -1, 16, hkZ, 3
if ldOn and travel = 0 then
	! 揚重物（大きさ ldW×ldD×ldH。吊りしろ ldS。SCP の手引 p.5）
	zl = hkD - ldS - ldH
	material "cr_load"
	add tipX - ldW / 2, -ldD / 2, zl
	block ldW, ldD, ldH
	del 1
	! 玉掛けワイヤ（吊り荷の四隅からフックへ）
	material "cr_steel"
	for c = 0 to 3
		x0q = tipX - ldW / 2 + 0.05 + (ldW - 0.1) * (c mod 2)
		y0q = -ldD / 2 + 0.05 + (ldD - 0.1) * int(c / 2)
		z0q = zl + ldH
		x1q = tipX
		y1q = 0
		z1q = hkD + 0.05
		rq = 0.008
		gosub "seg3"
	next c
endif
del 1
if wrOn then
	! 作業半径の円（地盤の高さ）
	material "cr_tail"
	rotz slD * 0
	add 0, 0, 0.05
	circle tipX
	del 1
	del 1
endif
if infoOn then
	! クレーン情報（フックと車体の後ろ。視点の向きへ回す）
	define style "crI" "Arial", 900 * texZ, 1, 0
	style "crI"
	aV = 0
	dxV = GLOB_EYEPOS_X - SYMB_POS_X
	dyV = GLOB_EYEPOS_Y - SYMB_POS_Y
	if abs(dxV) > 0.01 then aV = atn(dyV / dxV) + 180 * (dxV < 0)
	aV = aV - SYMB_ROTANGLE + 90
	material "cr_tail"
	add tipX * cos(slD), tipX * sin(slD), hkD + hkHt + 0.6
	rotz aV
	rotx 90
	if rated > 0 then
		text 0.02, 0, "Max " + str(rated * sfRate, 5, 2) + "t (" + str(sfRate * 100, 3, 0) + "%)"
	else
		text 0.02, 0, "Max -"
	endif
	del 3
	add -carRr - 0.5, 0, carH + 0.5
	rotz aV
	rotx 90
	text 0.02, 0, crName
	add 0, -0.9 * texZ, 0
	text 0.02, 0, "Boom=" + str(bL, 4, 1) + "m R=" + str(tipX, 4, 1) + "m"
	del 4
endif
end

"sideP":
	! put 済みの (x, z) の列を Y の yA〜yB に押し出す
	add 0, yB, 0
	rotx 90
	prism nsp / 2, yB - yA, get(nsp)
	del 2
return

"sect":
	! ブームの断面（幅 wS・高さ hS・長さ lS。roty 90 の中で x＝−高さ。1 ラウンド・2 六角・3 箱）
	if bmSec = 1 then
		put -0.5 * hS, -0.34 * wS, -0.5 * hS, 0.34 * wS, -0.38 * hS, 0.5 * wS, 0.02 * hS, 0.5 * wS, 0.22 * hS, 0.45 * wS, 0.4 * hS, 0.33 * wS, 0.5 * hS, 0.15 * wS
		put 0.5 * hS, -0.15 * wS, 0.4 * hS, -0.33 * wS, 0.22 * hS, -0.45 * wS, 0.02 * hS, -0.5 * wS, -0.38 * hS, -0.5 * wS
	endif
	if bmSec = 2 then
		put -0.5 * hS, -0.34 * wS, -0.5 * hS, 0.34 * wS, -0.38 * hS, 0.5 * wS, 0.02 * hS, 0.5 * wS, 0.5 * hS, 0.2 * wS, 0.5 * hS, -0.2 * wS, 0.02 * hS, -0.5 * wS, -0.38 * hS, -0.5 * wS
	endif
	if bmSec = 3 then
		put -0.5 * hS, -0.42 * wS, -0.5 * hS, 0.42 * wS, -0.42 * hS, 0.5 * wS, 0.42 * hS, 0.5 * wS, 0.5 * hS, 0.42 * wS, 0.5 * hS, -0.42 * wS, 0.42 * hS, -0.5 * wS, -0.42 * hS, -0.5 * wS
	endif
	prism nsp / 2, lS, get(nsp)
return

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
mq = GLOB_MODPAR_NAME
if travel = 0 and (mq = "hfX" or mq = "hfY") then
	! 平面のフックを引いた: 前後は作業半径、横は旋回（届かない半径は次の読み直しで最大に戻る）
	if abs(hfX) + abs(hfY) > 0.1 then
		if abs(hfX) < 0.0001 then
			aF = 90 + 180 * (hfY < 0)
		else
			aF = atn(hfY / hfX) + 180 * (hfX < 0)
			if aF < 0 then aF = aF + 360
		endif
		parameters hkR = sqr(hfX * hfX + hfY * hfY), slew = aF
	endif
endif
if bmStep and prio = 0 and mq = "boomL" then
	! 段階ブーム: 性能表のブーム長さのいちばん近い段へ
	bQ = rb[1]
	for k = 1 to nRb
		if abs(rb[k] - boomL) < abs(bQ - boomL) then bQ = rb[k]
	next k
	parameters boomL = bQ
endif
if travel = 0 and mq <> "hfX" and mq <> "hfY" then
	if prio = 0 then
		if GLOB_MODPAR_NAME = "boomA" then
			! ブームの先のホットスポット: 長さはそのままで起伏角を変え、作業半径を合わせる
			aQ = max(1, min(84, boomA))
			parameters hkR = -pivB + bL * cos(aQ) + jL * cos(aQ - jbO) * (jL > 0.01)
		else
			if abs(boomA - bA) > 0.01 then parameters boomA = bA
		endif
	else
		if abs(boomL - bL) > 0.001 then parameters boomL = bL
	endif
	if abs(hkR - tipX) > 0.001 and GLOB_MODPAR_NAME <> "boomA" then parameters hkR = tipX
	if abs(hfX - tipX * cos(slD)) + abs(hfY - tipX * sin(slD)) > 0.001 then parameters hfX = tipX * cos(slD), hfY = tipX * sin(slD)
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
""" + gdl_radii.vl() + gdl_draft.values()


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(SCRIPT_VL, encoding="utf-8")
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
    print(f"ashiba_crane: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
