"""部品 ashiba_crane（移動式クレーン 1台に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「クレーン リサーチして追加して」。寸法はタダノ GR-250N（Ⅴ）・GR-500N（Ⅰ）・GR-700N-3 の仕様書
（src/ashiba/crane_data.py・crane.py）。原点＝旋回中心の地盤、+X＝車体の前。車体（シャシ・タイヤ）、アウトリガ（前 outF・後ろ outR、
張出幅 outW、ジャッキとフロート fltD）、敷鉄板（厚板鋼板 1,524×3,048×22 を plN 枚。2枚は十字）、上部旋回体（旋回 slew 度・
カウンタウエイトの後端は後端旋回半径 tailR）、ブーム（根元 pivB 後ろ・pivH 高さから boomL を起伏角 boomA で、段ごとに細く）、
起伏シリンダ、フック（ブームの先から tipHk 下）・ワイヤ・吊り荷。平面は車体・アウトリガ・敷鉄板・後端旋回半径の円（立入禁止）・
作業半径の円（wrR）・ブームとフック。割付と検定は src/ashiba/crane.py、置くのは scripts/crane_run.py。
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
        _param("Integer", "crType", "機種（1＝25t GR-250N・2＝50t GR-500N・3＝70t GR-700N）", 1),
        _param("String", "crName", "機種の名前（平面の注記）", "GR-250N（Ⅴ）25t"),
        _param("Length", "carL", "全長", 11.53),
        _param("Length", "carW", "全幅", 2.62),
        _param("Length", "carH", "全高", 3.475),
        _param("Length", "carF", "旋回中心から前端", 5.4),
        _param("Length", "outF", "旋回中心から前のアウトリガ", 3.265),
        _param("Length", "outR", "旋回中心から後ろのアウトリガ", 3.415),
        _param("Length", "outW", "アウトリガの張出幅（ジャッキの芯々）", 6.6),
        _param("Length", "fltD", "フロートの径", 0.4),
        _param("Length", "tailR", "後端旋回半径", 3.1),
        _param("Length", "pivH", "ブームの根元の高さ", 2.3),
        _param("Length", "pivB", "ブームの根元の旋回中心から後ろ", 1.0),
        _param("Length", "tipHk", "ブームの先からフックの上まで", 1.3),
        _param("Length", "boomL", "ブーム長さ", 23.45),
        _param("Angle", "boomA", "ブームの起伏角", 56.0),
        _param("Angle", "slew", "旋回角（車体の前から左回り）", 30.0),
        _param("Length", "hookZ", "フックの高さ（地盤から。注記）", 20.0),
        _param("Integer", "plN", "敷鉄板の枚数（アウトリガ1脚に。2＝十字）", 1),
        _param("String", "wrR", "作業半径の円（mm。カンマ区切り）", "12000,18000"),
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


SCRIPT_1D = ("﻿! 移動式クレーン: 作業半径の円・車軸・ブームの先とフック（m）\n" + _parse_all("wrR", "wr", "nWr") + """carRr = carL - carF
nAx = 2
dim ax[4]
ax[1] = 1.94
ax[2] = -1.94
whR = 0.68
whW = 0.39
if crType = 2 then
	ax[1] = 2.52
	ax[2] = -2.53
	whR = 0.78
	whW = 0.5
endif
if crType = 3 then
	nAx = 4
	ax[1] = 3.0
	ax[2] = 1.45
	ax[3] = -1.55
	ax[4] = -3.1
endif
! ブームの先（上部旋回体の座標）とフック
tipX = -pivB + boomL * cos(boomA)
tipZ = pivH + boomL * sin(boomA)
hkZ = max(0.6, tipZ - tipHk)
plT = 0.022
plA = 1.524
plB = 3.048
""")

SCRIPT_2D = """﻿! 移動式クレーン 2D: 車体・アウトリガ・敷鉄板・後端旋回半径（立入禁止）・作業半径・ブームとフック
! 文字の数は str(数, 1, 0)（小数の桁を付けた str(x, 1, 1) は平面図でこの部品の 2D を丸ごと消した。プレビューでは描けていた）
pen penEquip
define style "crT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "crT"
! 車体
rect2 -carRr, -carW / 2, carF, carW / 2
for e = -1 to 1 step 2
	xo = outF
	if e < 0 then xo = -outR
	line2 xo, -outW / 2, xo, outW / 2
	for s = -1 to 1 step 2
		circle2 xo, s * outW / 2, fltD / 2
		rect2 xo - plB / 2, s * outW / 2 - plA / 2, xo + plB / 2, s * outW / 2 + plA / 2
		if plN >= 2 then rect2 xo - plA / 2, s * outW / 2 - plB / 2, xo + plA / 2, s * outW / 2 + plB / 2
	next s
next e
! 立入禁止（上部旋回体の後端旋回半径）と作業半径の円
circle2 0, 0, tailR
for i = 1 to nWr
	circle2 0, 0, wr[i]
	text2 wr[i] * 0.7071, wr[i] * 0.7071, "R" + str(round_int(wr[i] * 1000), 1, 0)
next i
! 上部旋回体とブーム（旋回角で回す）
rot2 slew
rect2 -tailR, -1.1, 1.2, 1.1
line2 -pivB, -0.35, tipX, -0.2
line2 -pivB, 0.35, tipX, 0.2
circle2 tipX, 0, 0.3
if ldOn then rect2 tipX - 0.75, -0.75, tipX + 0.75, 0.75
del 1
text2 0, -outW / 2 - 1.2, crName
text2 0, -outW / 2 - 1.2 - texSiz * GLOB_SCALE / 1000 * 1.6, "ブーム " + str(round_int(boomL * 1000), 1, 0) + "・作業半径 " + str(round_int(tipX * 1000), 1, 0)
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
resol 16
plH = plT * plN
! ---- 敷鉄板（アウトリガ1脚に plN 枚。2枚は十字）とフロート・ジャッキ・アウトリガのビーム ----
for e = -1 to 1 step 2
	xo = outF
	if e < 0 then xo = -outR
	material "cr_steel"
	add xo - 0.15, -outW / 2, 1.0
	block 0.3, outW, 0.25
	del 1
	for s = -1 to 1 step 2
		yo = s * outW / 2
		material "cr_plate"
		add xo - plB / 2, yo - plA / 2, 0
		block plB, plA, plT
		del 1
		if plN >= 2 then
			add xo - plA / 2, yo - plB / 2, plT
			block plA, plB, plT
			del 1
		endif
		material "cr_steel"
		add xo, yo, plH
		cylind 0.06, fltD / 2
		addz 0.06
		cylind 1.0 - plH - 0.06, 0.09
		del 2
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
material "cr_tire"
for i = 1 to nAx
	for s = -1 to 1 step 2
		add ax[i], s * (carW / 2 - whW / 2 - 0.02), whR + 0.05
		rotx 90
		addz -whW / 2
		cylind whW, whR
		del 3
	next s
next i
! ---- 上部旋回体（旋回角 slew で回す）----
rotz slew
material "cr_steel"
add 0, 0, 1.5
cylind 0.2, 1.0
del 1
material "cr_body"
add -tailR + 0.7, -1.1, 1.7
block tailR - 0.7 + 1.0, 2.2, 0.9
del 1
material "cr_cw"
add -tailR, -1.1, 1.7
block 0.7, 2.2, 1.0
del 1
! 運転室（右前）
material "cr_body"
add 0.2, -1.25, 1.7
block 1.9, 0.85, 1.65
del 1
material "cr_cw"
add 1.0, -1.255, 2.4
block 1.05, 0.005, 0.8
del 1
! 起伏シリンダ（旋回体からブームの 0.35 の所）
material "cr_steel"
x0q = 0.9
y0q = 0
z0q = 1.9
x1q = -pivB + 0.35 * boomL * cos(boomA)
y1q = 0
z1q = pivH + 0.35 * boomL * sin(boomA)
rq = 0.11
gosub "seg3"
! ブーム（根元から段ごとに細く）
add -pivB, 0, pivH
roty -boomA
nS = 4
if crType >= 2 then nS = 6
sL = boomL / nS
for k = 1 to nS
	bw = 0.78 - (k - 1) * 0.06
	if crType = 1 then bw = 0.62 - (k - 1) * 0.06
	ov = 0
	if k > 1 then ov = 0.05
	material "cr_boom"
	add (k - 1) * sL - ov, -bw / 2, -bw * 0.55
	block sL + ov, bw, bw * 1.1
	del 1
next k
! ブームの先（シーブ）
material "cr_steel"
add boomL, 0, 0
rotx 90
addz -0.2
cylind 0.4, 0.35
del 3
del 2
! ワイヤ・フック・吊り荷（旋回体の座標でブームの先の真下）
material "cr_steel"
add tipX, 0, hkZ + 0.6
cylind tipZ - hkZ - 0.6, 0.012
del 1
material "cr_hook"
add tipX - 0.25, -0.18, hkZ
block 0.5, 0.36, 0.6
del 1
material "cr_steel"
add tipX, 0, hkZ - 0.35
cylind 0.35, 0.05
del 1
if ldOn then
	zl = max(0.0, hkZ - 2.6)
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
		z1q = hkZ - 0.35
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
    print(f"ashiba_crane: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
