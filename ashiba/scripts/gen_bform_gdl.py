"""部品 ashiba_bform（梁の型枠: 側板・底板・桟木・外端太・フォームタイ・底の受けの単管）の HSF を書き出す.

利用者の指定（2026-10-31）「型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置するようにして」。
割付と計算は src/ashiba/beam_form.py、置くのは scripts/form_run.py。

原点＝梁の芯の始めの下端。+X＝梁の向き、梁は Y の −wB/2〜+wB/2、+Z＝上。型枠の範囲は x0〜x1（柱の面で止める）。底板（合板）
と下の桟木（botY）、受けの単管（ukeX。梁に直角）、両側の側板（底板の下面から sideH）と桟木（縦。sgX）、外端太（単管2本組。tbZ の
高さ、tb0〜tb1）、フォームタイ（tiX×tbZ。梁を貫いて Pコン）、止め型枠（endS・endE）.
  python3 scripts/gen_bform_gdl.py     # gdl/hsf/ashiba_bform を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_bform"
MAIN_GUID = "9D4B2E71-6C3A-4F85-A1E9-5B7C0F2D8E46"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "梁の長さ（芯）", 6.0, True),
        _param("Length", "B", "Dimension 2", 0.4, True),
        _param("Length", "ZZYZX", "梁せい", 0.7, True),
        _param("Length", "wB", "梁の幅", 0.4),
        _param("Length", "sideH", "−Y の側板の高さ（底板の下面から。上にスラブがあればスラブの下端まで）", 0.562),
        _param("Length", "sideH2", "+Y の側板の高さ（外周の梁で片側だけスラブがあるときは違う）", 0.562),
        _param("RealNum", "nTie", "フォームタイを入れる外端太の段の数（下から。両側の側板がある段）", 2),
        _param("Length", "x0", "型枠の始め（梁の始めから）", 0),
        _param("Length", "x1", "型枠の終わり", 6.0),
        _param("Length", "tb0", "外端太の始め", -0.15),
        _param("Length", "tb1", "外端太の終わり", 6.15),
        _param("String", "sgX", "側板の桟木の位置（梁の始めから mm）", "150,450,750"),
        _param("String", "tbZ", "外端太の高さ（底板の下面から mm）", "140,422"),
        _param("String", "tiX", "フォームタイの位置（梁の始めから mm）", "150,1050"),
        _param("String", "botY", "底板の下の桟木の位置（梁の芯から mm）", "-178,0,178"),
        _param("String", "ukeX", "底の受けの単管の位置（梁の始めから mm）", "150,900"),
        _param("Length", "ukeOut", "受けの単管の、外端太の外への出", 0.15),
        _param("Length", "psH", "受けの単管を受けるパイプサポートの長さ（床から受けの単管の下まで。0 なら描かない）", 0),
        _param("Length", "psY", "パイプサポートの位置（梁の芯から両側へ）", 0.3),
        _param("Length", "sillH", "パイプサポートの下の敷き桟木の高さ（45×60 を寝かせる）", 0.045),
        _param("Boolean", "sillCross", "敷き桟木を梁に直角に（受けの単管ごとに両側の支柱の下へ）。切ると梁の向きに2列", 0),
        _param("Boolean", "endS", "始めの端に止め型枠", 0),
        _param("Boolean", "endE", "終わりの端に止め型枠", 0),
        _param("Length", "plyT", "せき板の厚さ", 0.012),
        _param("Length", "sgB", "桟木の幅", 0.045),
        _param("Length", "sgH", "桟木のせい", 0.06),
        _param("String", "cName", "名前（平面の注記）", "梁型枠"),
        _param("String", "cNote", "間隔の注記", ""),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        "\t\t<PenColor Name=\"penEquip\">\n\t\t\t<Description><![CDATA[\"線のペン\"]]></Description>\n"
        "\t\t\t<Value>1</Value>\n\t\t</PenColor>\n",
    ]
    return ("\ufeff<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ParamSection>\n\t<ParamSectHeader>\n"
            "\t\t<AutoHotspots>false</AutoHotspots>\n\t\t<StatBits>\n\t\t\t<STBit_UIDefault/>\n\t\t</StatBits>\n"
            "\t\t<WDLeftFrame>0</WDLeftFrame>\n\t\t<WDRightFrame>0</WDRightFrame>\n\t\t<WDTopFrame>0</WDTopFrame>\n"
            "\t\t<WDBotFrame>0</WDBotFrame>\n\t\t<LayFlags>65535</LayFlags>\n\t\t<WDMirrorThickness>0</WDMirrorThickness>\n"
            "\t\t<WDWallInset>0</WDWallInset>\n\t</ParamSectHeader>\n"
            "\t<Parameters SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\">\n" + "".join(ps)
            + "\t</Parameters>\n</ParamSection>\n")


SCRIPT_1D = ("\ufeff! 梁の型枠: 位置を読む（m）\n"
             + _parse_all("sgX", "sx", "nS") + _parse_all("tbZ", "tz", "nT") + _parse_all("tiX", "tx", "nX")
             + _parse_all("botY", "by", "nB") + _parse_all("ukeX", "ux", "nU")
             + """r = 0.0243
hw = wB / 2
yS = hw + plyT + sgH
yT = yS + r
zb = -plyT
! 底の根太（角パイプ □50×50）・大引（杉 90×90）
nH = 0.05
oH = 0.09
"""
             )

SCRIPT_2D = """\ufeff! 梁の型枠 2D
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "bfT" "ＭＳ Ｐゴシック", texSiz, 1, 0
! 側板
rect2 x0, hw, x1, hw + plyT
rect2 x0, -hw - plyT, x1, -hw
! 桟木
for i = 1 to nS
	rect2 sx[i] - sgB / 2, hw + plyT, sx[i] + sgB / 2, yS
	rect2 sx[i] - sgB / 2, -yS, sx[i] + sgB / 2, -hw - plyT
next i
! 外端太・受けの単管
line_type "DASHED"
line2 tb0, yT, tb1, yT
line2 tb0, -yT, tb1, -yT
for i = 1 to nU
	line2 ux[i], -yT - r - ukeOut, ux[i], yT + r + ukeOut
next i
line_type 1
! フォームタイ
for i = 1 to nX
	line2 tx[i], -yT - 0.06, tx[i], yT + 0.06
next i
! 止め型枠
if endS then rect2 x0 - plyT, -hw - plyT, x0, hw + plyT
if endE then rect2 x1, -hw - plyT, x1 + plyT, hw + plyT
style "bfT"
text2 (x0 + x1) / 2, -yT - 0.12, cName + "  " + cNote
"""

SCRIPT_3D = """\ufeff! ============================================================
! 梁の型枠 3D（利用者の指定 2026-10-31: さんぎ そとばた フォームタイ）
! 原点＝梁の芯の始めの下端（底板の上面）
! ============================================================
resol 12
define material "bf_ply" 2, 0.86, 0.66, 0.38
define material "bf_wood" 2, 0.74, 0.56, 0.36
define material "bf_steel" 2, 0.62, 0.62, 0.66
define material "bf_tie" 2, 0.35, 0.35, 0.38
define material "bf_pcon" 2, 0.85, 0.85, 0.80
define material "bf_ps" 2, 0.42, 0.44, 0.48
gap = 0.006
L = x1 - x0
! ---- 底板と下の根太（角パイプ □50×50・梁の向き）（スラブ・梁下の詳細図。利用者の指定 2026-10-31） ----
material "bf_ply"
add x0, -hw, zb
block L, wB, plyT
del 1
material "bf_steel"
for i = 1 to nB
	add x0, by[i] - nH / 2, zb - nH
	block L, nH, nH
	del 1
next i
! ---- 大引（杉 90×90・梁に直角） ----
material "bf_wood"
for i = 1 to nU
	add ux[i] - oH / 2, -yT - r - ukeOut, zb - nH - oH
	block oH, 2 * (yT + r + ukeOut), oH
	del 1
next i
! ---- パイプサポート（受けの単管の両端の下） ----
if psH > 0.1 then
	for i = 1 to nU
		for sd = -1 to 1 step 2
			add ux[i], sd * psY, zb - nH - oH - psH
			material "bf_steel"
			add -0.07, -0.07, 0
			block 0.14, 0.14, 0.006
			del 1
			material "bf_ps"
			cylind psH * 0.6, 0.03025
			add 0, 0, psH * 0.6
			material "bf_steel"
			cylind psH * 0.4 - 0.006, 0.0243
			del 1
			add -0.06, -0.06, psH - 0.006
			block 0.12, 0.12, 0.006
			del 1
			material "bf_tie"
			for kk = -1 to 1 step 2
				add kk * 0.04, 0, psH
				cylind 0.04, 0.002
				del 1
			next kk
			del 1
		next sd
	next i
endif
! ---- 敷き桟木（上のスラブの敷き桟木と向きを揃える。利用者の指定 2026-10-31: さんぎの向き揃えて） ----
if psH > 0.1 and nU > 0 then
	material "bf_wood"
	if sillCross then
		for i = 1 to nU
			add ux[i] - 0.03, -psY - 0.15, zb - nH - oH - psH - sillH
			block 0.06, 2 * psY + 0.3, sillH
			del 1
		next i
	else
		for sd = -1 to 1 step 2
			add ux[1] - 0.15, sd * psY - 0.03, zb - nH - oH - psH - sillH
			block ux[nU] - ux[1] + 0.3, 0.06, sillH
			del 1
		next sd
	endif
endif
! ---- 側板・桟木・外端太 ----
for sd = -1 to 1 step 2
	if sd > 0 then
		hS = sideH2
	else
		hS = sideH
	endif
	material "bf_ply"
	if sd > 0 then
		add x0, hw, zb
	else
		add x0, -hw - plyT, zb
	endif
	block L, plyT, hS
	del 1
	material "bf_wood"
	for i = 1 to nS
		if sd > 0 then
			add sx[i] - sgB / 2, hw + plyT, zb
		else
			add sx[i] - sgB / 2, -yS, zb
		endif
		block sgB, sgH, hS
		del 1
	next i
	material "bf_steel"
	for j = 1 to nT
		if tz[j] < hS - 0.03 then
		for k = -1 to 1 step 2
			add tb0, sd * yT, zb + tz[j] + k * (r + gap)
			roty 90
			cylind tb1 - tb0, r
			del 2
		next k
		endif
	next j
next sd
! ---- フォームタイ（両側の側板がある段だけ） ----
for j = 1 to min(nT, nTie)
	for i = 1 to nX
		add tx[i], 0, zb + tz[j]
		material "bf_tie"
		add 0, -yT - r - 0.05, 0
		rotx -90
		cylind 2 * (yT + r + 0.05), 0.00395
		del 2
		for sd = -1 to 1 step 2
			add -0.035, sd * (yT + r) + (sd - 1) / 2 * 0.006, -(2 * r + gap)
			block 0.07, 0.006, 2 * (2 * r + gap)
			del 1
		next sd
		material "bf_pcon"
		add 0, -hw, 0
		rotx -90
		cone 0.025, 0.012, 0.0175, 90, 90
		del 2
		add 0, hw, 0
		rotx 90
		cone 0.025, 0.012, 0.0175, 90, 90
		del 2
		del 1
	next i
next j
! ---- 止め型枠 ----
material "bf_ply"
if endS then
	add x0 - plyT, -hw - plyT, zb
	block plyT, wB + 2 * plyT, max(sideH, sideH2)
	del 1
endif
if endE then
	add x1, -hw - plyT, zb
	block plyT, wB + 2 * plyT, max(sideH, sideH2)
	del 1
endif
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
    print(f"ashiba_bform: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
