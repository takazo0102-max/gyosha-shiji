"""部品 ashiba_cform（柱の型枠: せき板・桟木・外端太・フォームタイ）の HSF を書き出す.

利用者の指定（2026-10-31）「型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置するようにして」。
割付と計算は src/ashiba/column_form.py、置くのは scripts/form_run.py。

原点＝柱の芯の下。+X＝柱の幅 A の向き、+Y＝奥行き B の向き。4面にせき板（±Y の面は ±X の面の小口を覆って A＋2×12）、
桟木（縦。±Y の面は sgX、±X の面は sgY の位置）、外端太（単管2本組。±Y の面は X の向きに tbZ の高さ、±X の面は Y の向きに
dzB 上げた高さ）、フォームタイ（tiX の位置で Y の向きに、tiY の位置で X の向きに。両端は角の外、間は柱を貫いて Pコン）.
  python3 scripts/gen_cform_gdl.py     # gdl/hsf/ashiba_cform を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_cform"
MAIN_GUID = "2C8E5B17-9A4F-4E63-B0D2-7F1A3C6E9D58"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "柱の幅（X）", 0.6, True),
        _param("Length", "B", "柱の奥行き（Y）", 0.6, True),
        _param("Length", "ZZYZX", "柱の高さ", 3.0, True),
        _param("String", "sgX", "±Y の面の桟木の位置（芯から X mm、カンマ区切り）", "-250,0,250"),
        _param("String", "sgY", "±X の面の桟木の位置（芯から Y mm）", "-250,0,250"),
        _param("String", "tbZ", "外端太の高さ（柱の下から mm。±X の面は dzB 上）", "150,450,750"),
        _param("String", "tiX", "Y の向きに締めるフォームタイの X の位置（芯から mm。両端は角の外）", "-451,451"),
        _param("String", "tiY", "X の向きに締めるフォームタイの Y の位置（芯から mm）", "-451,451"),
        _param("Length", "dzB", "±X の面の外端太を上げる高さ", 0.12),
        _param("Length", "plyT", "せき板の厚さ", 0.012),
        _param("Length", "sgB", "桟木の幅", 0.045),
        _param("Length", "sgH", "桟木のせい（合板に直角）", 0.06),
        _param("Length", "tbOver", "外端太の、角の外のフォームタイからの出", 0.1),
        _param("String", "cName", "名前（平面の注記）", "柱型枠"),
        _param("String", "cNote", "間隔の注記", ""),
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


SCRIPT_1D = ("﻿! 柱の型枠: 桟木・外端太・フォームタイの位置を読む（m）\n"
             + _parse_all("sgX", "sx", "nSx") + _parse_all("sgY", "sy", "nSy") + _parse_all("tbZ", "tz", "nT")
             + _parse_all("tiX", "tx", "nX") + _parse_all("tiY", "ty", "nY")
             + """r = 0.0243
hA = A / 2
hB = B / 2
! 外端太の芯（面から）
yT = hB + plyT + sgH + r
xT = hA + plyT + sgH + r
"""
             )

SCRIPT_2D = """﻿! 柱の型枠 2D
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "cfT" "ＭＳ Ｐゴシック", texSiz, 1, 0
! せき板
rect2 -hA - plyT, hB, hA + plyT, hB + plyT
rect2 -hA - plyT, -hB - plyT, hA + plyT, -hB
rect2 hA, -hB, hA + plyT, hB
rect2 -hA - plyT, -hB, -hA, hB
! 桟木
for i = 1 to nSx
	rect2 sx[i] - sgB / 2, hB + plyT, sx[i] + sgB / 2, hB + plyT + sgH
	rect2 sx[i] - sgB / 2, -hB - plyT - sgH, sx[i] + sgB / 2, -hB - plyT
next i
for i = 1 to nSy
	rect2 hA + plyT, sy[i] - sgB / 2, hA + plyT + sgH, sy[i] + sgB / 2
	rect2 -hA - plyT - sgH, sy[i] - sgB / 2, -hA - plyT, sy[i] + sgB / 2
next i
! 外端太
line_type "DASHED"
line2 tx[1] - tbOver, yT, tx[nX] + tbOver, yT
line2 tx[1] - tbOver, -yT, tx[nX] + tbOver, -yT
line2 xT, ty[1] - tbOver, xT, ty[nY] + tbOver
line2 -xT, ty[1] - tbOver, -xT, ty[nY] + tbOver
line_type 1
! フォームタイ
for i = 1 to nX
	line2 tx[i], -yT - 0.05, tx[i], yT + 0.05
next i
for i = 1 to nY
	line2 -xT - 0.05, ty[i], xT + 0.05, ty[i]
next i
style "cfT"
text2 0, -yT - 0.15, cName + "  " + cNote
"""

SCRIPT_3D = """﻿! ============================================================
! 柱の型枠 3D（利用者の指定 2026-10-31: さんぎ そとばた フォームタイ）
! ============================================================
resol 12
define material "cf_ply" 2, 0.86, 0.66, 0.38
define material "cf_wood" 2, 0.74, 0.56, 0.36
define material "cf_steel" 2, 0.62, 0.62, 0.66
define material "cf_tie" 2, 0.35, 0.35, 0.38
define material "cf_pcon" 2, 0.85, 0.85, 0.80
H = ZZYZX
gap = 0.006
! ---- せき板 ----
material "cf_ply"
add -hA - plyT, hB, 0
block A + 2 * plyT, plyT, H
del 1
add -hA - plyT, -hB - plyT, 0
block A + 2 * plyT, plyT, H
del 1
add hA, -hB, 0
block plyT, B, H
del 1
add -hA - plyT, -hB, 0
block plyT, B, H
del 1
! ---- 桟木 ----
material "cf_wood"
for i = 1 to nSx
	add sx[i] - sgB / 2, hB + plyT, 0
	block sgB, sgH, H
	del 1
	add sx[i] - sgB / 2, -hB - plyT - sgH, 0
	block sgB, sgH, H
	del 1
next i
for i = 1 to nSy
	add hA + plyT, sy[i] - sgB / 2, 0
	block sgH, sgB, H
	del 1
	add -hA - plyT - sgH, sy[i] - sgB / 2, 0
	block sgH, sgB, H
	del 1
next i
! ---- 外端太（2本組） ----
material "cf_steel"
Lx = tx[nX] - tx[1] + 2 * tbOver
Ly = ty[nY] - ty[1] + 2 * tbOver
for j = 1 to nT
	for k = -1 to 1 step 2
		for sd = -1 to 1 step 2
			add tx[1] - tbOver, sd * yT, tz[j] + k * (r + gap)
			roty 90
			cylind Lx, r
			del 2
			add sd * xT, ty[1] - tbOver, tz[j] + dzB + k * (r + gap)
			rotx -90
			cylind Ly, r
			del 2
		next sd
	next k
next j
! ---- フォームタイ ----
for j = 1 to nT
	! Y の向き（±Y の面の外端太を締める）
	for i = 1 to nX
		add tx[i], 0, tz[j]
		material "cf_tie"
		add 0, -yT - r - 0.05, 0
		rotx -90
		cylind 2 * (yT + r + 0.05), 0.00395
		del 2
		for sd = -1 to 1 step 2
			add -0.035, sd * (yT + r) + (sd - 1) / 2 * 0.006, -(2 * r + gap)
			block 0.07, 0.006, 2 * (2 * r + gap)
			del 1
		next sd
		if i > 1 and i < nX then
			material "cf_pcon"
			add 0, -hB, 0
			rotx -90
			cone 0.025, 0.012, 0.0175, 90, 90
			del 2
			add 0, hB, 0
			rotx 90
			cone 0.025, 0.012, 0.0175, 90, 90
			del 2
		endif
		del 1
	next i
	! X の向き（±X の面の外端太を締める）
	for i = 1 to nY
		add 0, ty[i], tz[j] + dzB
		material "cf_tie"
		add -xT - r - 0.05, 0, 0
		roty 90
		cylind 2 * (xT + r + 0.05), 0.00395
		del 2
		for sd = -1 to 1 step 2
			add sd * (xT + r) + (sd - 1) / 2 * 0.006, -0.035, -(2 * r + gap)
			block 0.006, 0.07, 2 * (2 * r + gap)
			del 1
		next sd
		if i > 1 and i < nY then
			material "cf_pcon"
			add -hA, 0, 0
			roty 90
			cone 0.025, 0.012, 0.0175, 90, 90
			del 2
			add hA, 0, 0
			roty -90
			cone 0.025, 0.012, 0.0175, 90, 90
			del 2
		endif
		del 1
	next i
next j
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text("﻿\n", encoding="utf-8")
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
    print(f"ashiba_cform: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
