"""部品 ashiba_wform（壁の型枠: せき板・桟木・外端太・フォームタイ）の HSF を書き出す.

利用者の指定（2026-10-31）「型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置するようにして」。
割付と計算は src/ashiba/wall_form.py、置くのは scripts/form_run.py。

原点＝壁の右の面（壁の向きに見て）の始めの下。+X＝壁の向き、壁は +Y の側（0〜wT）、+Z＝上。
両面に、せき板（合板 12mm）、その外に桟木（45×60 縦。sgX の位置）、その外に外端太（単管 φ48.6 の2本組 横。tbZ の高さ、
フォームタイを上下にはさむ）、フォームタイ（tiX×tbZ の位置で壁を貫く。内側の両端に Pコン、外は座金とナット）.
  python3 scripts/gen_wform_gdl.py     # gdl/hsf/ashiba_wform を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_wform"
MAIN_GUID = "6E2A9C41-3F7B-4D18-A5C2-8B1E0D4F7A93"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "壁の長さ", 6.0, True),
        _param("Length", "B", "Dimension 2", 0.2, True),
        _param("Length", "ZZYZX", "壁の高さ", 3.0, True),
        _param("Length", "wT", "壁の厚さ", 0.2),
        _param("String", "sgX", "右の面（−Y の側）の桟木の位置（壁の始めから mm、カンマ区切り）", "150,400,650"),
        _param("String", "sgX2", "左の面（壁の向こう +Y の側）の桟木の位置（同）", "150,400,650"),
        _param("String", "p1Seg", "右の面のせき板の区間（壁の始めから mm、始め,終わり の組をカンマ区切り。角で延ばす・縮める、T 字で分ける）",
               "0,6000"),
        _param("String", "p2Seg", "左の面のせき板の区間（同）", "0,6000"),
        _param("String", "tbZ", "外端太の高さ（壁の下から mm）", "150,600,1050"),
        _param("String", "tiX", "フォームタイの位置（壁の始めから mm）", "150,900"),
        _param("Length", "plyT", "せき板の厚さ", 0.012),
        _param("Length", "sgB", "桟木の幅", 0.045),
        _param("Length", "sgH", "桟木のせい（合板に直角）", 0.06),
        _param("Length", "tbOut", "止め型枠の押さえの単管の出（壁の厚さの外へ）", 0.1),
        _param("String", "t1Seg", "右の面の外端太の区間（同。角・T 字では相手の外端太の線まで）", "-150,6150"),
        _param("String", "t2Seg", "左の面の外端太の区間（同）", "-150,6150"),
        _param("Boolean", "endS", "始めの端に止め型枠（ほかの壁につながらない端）", 0),
        _param("Boolean", "endE", "終わりの端に止め型枠", 0),
        _param("String", "cName", "名前（平面の注記）", "壁型枠"),
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


SCRIPT_1D = ("﻿! 壁の型枠: 桟木・外端太・フォームタイの位置を読む（m）\n"
             + _parse_all("sgX", "sx", "nS") + _parse_all("sgX2", "sx2", "nS2") + _parse_all("tbZ", "tz", "nT")
             + _parse_all("tiX", "tx", "nX") + _parse_all("p1Seg", "pa", "nPa") + _parse_all("p2Seg", "pb", "nPb")
             + _parse_all("t1Seg", "ta", "nTa") + _parse_all("t2Seg", "tb", "nTb")
             + """! 外端太の外の面の位置（せき板の面から）
r = 0.0243
yS = plyT + sgH
yT = yS + r
"""
             )

SCRIPT_2D = """﻿! 壁の型枠 2D: せき板（両面）、桟木、外端太、フォームタイ、名前
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "wfT" "ＭＳ Ｐゴシック", texSiz, 1, 0
! せき板（面ごとの区間。角で延ばす・縮める、T 字で分ける）
for i = 1 to int(nPa / 2)
	rect2 pa[2 * i - 1], -plyT, pa[2 * i], 0
next i
for i = 1 to int(nPb / 2)
	rect2 pb[2 * i - 1], wT, pb[2 * i], wT + plyT
next i
! 桟木
for i = 1 to nS
	rect2 sx[i] - sgB / 2, -yS, sx[i] + sgB / 2, -plyT
next i
for i = 1 to nS2
	rect2 sx2[i] - sgB / 2, wT + plyT, sx2[i] + sgB / 2, wT + yS
next i
! 外端太（単管）
line_type "DASHED"
for i = 1 to int(nTa / 2)
	line2 ta[2 * i - 1], -yT, ta[2 * i], -yT
next i
for i = 1 to int(nTb / 2)
	line2 tb[2 * i - 1], wT + yT, tb[2 * i], wT + yT
next i
line_type 1
! 止め型枠
if endS then
	rect2 -plyT, -plyT, 0, wT + plyT
	line2 -plyT - sgH - r, -yT - tbOut, -plyT - sgH - r, wT + yT + tbOut
endif
if endE then
	rect2 A, -plyT, A + plyT, wT + plyT
	line2 A + plyT + sgH + r, -yT - tbOut, A + plyT + sgH + r, wT + yT + tbOut
endif
! フォームタイ
for i = 1 to nX
	line2 tx[i], -yT - 0.06, tx[i], wT + yT + 0.06
	rect2 tx[i] - 0.03, -yT - 0.03, tx[i] + 0.03, -yT - 0.024
	rect2 tx[i] - 0.03, wT + yT + 0.024, tx[i] + 0.03, wT + yT + 0.03
next i
style "wfT"
text2 A / 2, -yT - 0.12, cName + "  " + cNote
"""

SCRIPT_3D = """﻿! ============================================================
! 壁の型枠 3D（利用者の指定 2026-10-31: さんぎ そとばた フォームタイ）
! - せき板（合板 12mm）: 壁の両面
! - 桟木（45×60）: せき板の外に縦
! - 外端太（単管 φ48.6 の2本組）: 桟木の外に横。2本でフォームタイを上下にはさむ
! - フォームタイ: 壁を貫く。内側の両端に Pコン（せき板の内面）、外は座金とナット
! ============================================================
resol 12
define material "wf_ply" 2, 0.86, 0.66, 0.38
define material "wf_wood" 2, 0.74, 0.56, 0.36
define material "wf_steel" 2, 0.62, 0.62, 0.66
define material "wf_tie" 2, 0.35, 0.35, 0.38
define material "wf_pcon" 2, 0.85, 0.85, 0.80
H = ZZYZX
gap = 0.006
for side = 1 to 2
	if side = 1 then
		y0 = 0
		sg = -1
		nn = nS
	else
		y0 = wT
		sg = 1
		nn = nS2
	endif
	! ---- せき板 ----
	material "wf_ply"
	if sg < 0 then
		nq = int(nPa / 2)
	else
		nq = int(nPb / 2)
	endif
	for q = 1 to nq
		if sg < 0 then
			fS = pa[2 * q - 1]
			fE = pa[2 * q]
			add fS, -plyT, 0
		else
			fS = pb[2 * q - 1]
			fE = pb[2 * q]
			add fS, wT, 0
		endif
		block fE - fS, plyT, H
		del 1
	next q
	! ---- 桟木 ----
	material "wf_wood"
	for i = 1 to nn
		if sg < 0 then
			add sx[i] - sgB / 2, -yS, 0
		else
			add sx2[i] - sgB / 2, wT + plyT, 0
		endif
		block sgB, sgH, H
		del 1
	next i
	! ---- 外端太（2本組） ----
	material "wf_steel"
	if sg < 0 then
		nq = int(nTa / 2)
	else
		nq = int(nTb / 2)
	endif
	for q = 1 to nq
		if sg < 0 then
			tS = ta[2 * q - 1]
			tE = ta[2 * q]
		else
			tS = tb[2 * q - 1]
			tE = tb[2 * q]
		endif
		for j = 1 to nT
			for k = -1 to 1 step 2
				add tS, y0 + sg * yT, tz[j] + k * (r + gap)
				roty 90
				cylind tE - tS, r
				del 2
			next k
		next j
	next q
next side
! ---- 止め型枠（ほかの壁につながらない端）: 合板・縦の桟木2本・段ごとに押さえの単管（両面の外端太の出に直交クランプ） ----
for ee = 1 to 2
	if (ee = 1 and endS) or (ee = 2 and endE) then
		if ee = 1 then
			xe = 0
			dx = -1
		else
			xe = A
			dx = 1
		endif
		material "wf_ply"
		add xe + (dx - 1) / 2 * plyT, -plyT, 0
		block plyT, wT + 2 * plyT, H
		del 1
		material "wf_wood"
		for q = 1 to 2
			add xe + dx * plyT + (dx - 1) / 2 * sgH, wT * q / 3 - sgB / 2, 0
			block sgH, sgB, H
			del 1
		next q
		material "wf_steel"
		for j = 1 to nT
			add xe + dx * (plyT + sgH + r), -yT - tbOut, tz[j]
			rotx -90
			cylind wT + 2 * yT + 2 * tbOut, r
			del 2
		next j
	endif
next ee
! ---- フォームタイ ----
for j = 1 to nT
	for i = 1 to nX
		add tx[i], 0, tz[j]
		! 棒（外の座金の先まで）
		material "wf_tie"
		add 0, -yT - r - 0.05, 0
		rotx -90
		cylind wT + 2 * (yT + r + 0.05), 0.00395
		del 2
		! Pコン（せき板の内面に。壁の中へ 25）
		material "wf_pcon"
		add 0, 0, 0
		rotx -90
		cone 0.025, 0.012, 0.0175, 90, 90
		del 2
		add 0, wT, 0
		rotx 90
		cone 0.025, 0.012, 0.0175, 90, 90
		del 2
		! 座金（2本の外端太にまたがる）とナット
		material "wf_tie"
		for sd = 1 to 2
			if sd = 1 then
				yy = -yT - r
				dd = -1
				yb = yy - 0.006
			else
				yy = wT + yT + r
				dd = 1
				yb = yy
			endif
			add -0.035, yb, -(2 * r + gap)
			block 0.07, 0.006, 2 * (2 * r + gap)
			del 1
			add 0, yy + dd * 0.006, 0
			if dd < 0 then
				rotx 90
			else
				rotx -90
			endif
			cylind 0.03, 0.012
			del 2
		next sd
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
    print(f"ashiba_wform: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
