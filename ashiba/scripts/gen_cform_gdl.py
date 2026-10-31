"""部品 ashiba_cform（柱の型枠: せき板・桟木・外端太・フォームタイ）の HSF を書き出す.

利用者の指定（2026-10-31）「型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置するようにして」。
割付と計算は src/ashiba/column_form.py、置くのは scripts/form_run.py。

原点＝柱の芯の下。+X＝柱の幅 A の向き、+Y＝奥行き B の向き。面は 1＝+Y・2＝−X・3＝−Y・4＝+X（芯から 0・90・180・270°
回した +Y の面。面の座標 s は回したあとの X）。面ごとにせき板（ply）・桟木（縦。sg）・外端太（単管2本組。tb。±X の面は dzB
上げる）、壁の取り付く所は区間を分ける。フォームタイ（tiX の位置で Y の向きに、tiY の位置で X の向きに。両端は角の外、間は柱を
貫いて Pコン）.
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
        *[x for k, nm in enumerate(("+Y", "−X", "−Y", "+X"), 1) for x in (
            _param("String", f"ply{k}", f"{nm} の面のせき板の区間（面の座標 s mm、始め,終わり の組。壁の取り付く所で分ける）",
                   "-312,312" if k % 2 else "-300,300"),
            _param("String", f"sg{k}", f"{nm} の面の桟木の位置（面の座標 s mm）", "-250,0,250"),
            _param("String", f"tb{k}", f"{nm} の面の外端太の区間（面の座標 s mm）", "-551,551"))],
        _param("String", "tbZ", "外端太の高さ（柱の下から mm。±X の面は dzB 上）", "150,450,750"),
        _param("String", "tiX", "Y の向きに締めるフォームタイの X の位置（芯から mm。両端は角の外）", "-451,451"),
        _param("String", "tiY", "X の向きに締めるフォームタイの Y の位置（芯から mm）", "-451,451"),
        _param("Length", "dzB", "±X の面の外端太を上げる高さ", 0.12),
        _param("Boolean", "clampOn", "コラムクランプで締める（外端太・フォームタイのかわり。tbZ の高さに4方の腕）", 0),
        _param("Length", "clH", "コラムクランプの腕のせい", 0.075),
        _param("Length", "clT", "コラムクランプの腕の出（合板に直角）", 0.04),
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
             + "".join(_parse_all(f"ply{k}", f"pl{k}", f"nPl{k}") + _parse_all(f"sg{k}", f"sg{k}a", f"nSg{k}")
                       + _parse_all(f"tb{k}", f"tb{k}a", f"nTb{k}") for k in range(1, 5))
             + _parse_all("tbZ", "tz", "nT")
             + _parse_all("tiX", "tx", "nX") + _parse_all("tiY", "ty", "nY")
             + """r = 0.0243
hA = A / 2
hB = B / 2
! 外端太の芯（面から）
yT = hB + plyT + sgH + r
xT = hA + plyT + sgH + r
"""
             )


def _face2d(k: int) -> str:
    """面 k（1＝+Y・2＝−X・3＝−Y・4＝+X）の 2D: 芯から (k−1)×90° 回した +Y の面として描く."""
    h = "hB" if k % 2 else "hA"
    return f"""rot2 {(k - 1) * 90}
for i = 1 to int(nPl{k} / 2)
	rect2 pl{k}[2 * i - 1], {h}, pl{k}[2 * i], {h} + plyT
next i
for i = 1 to nSg{k}
	rect2 sg{k}a[i] - sgB / 2, {h} + plyT, sg{k}a[i] + sgB / 2, {h} + plyT + sgH
next i
if clampOn then
	rect2 -{"hA" if k % 2 else "hB"} - plyT - sgH - 0.12, {h} + plyT + sgH, {"hA" if k % 2 else "hB"} + plyT + sgH + 0.12, {h} + plyT + sgH + clT
endif
line_type "DASHED"
for i = 1 to int(nTb{k} / 2)
	line2 tb{k}a[2 * i - 1], {h} + plyT + sgH + r, tb{k}a[2 * i], {h} + plyT + sgH + r
next i
line_type 1
del 1
"""


def _face3d(k: int) -> str:
    """面 k の 3D（せき板・桟木・外端太の2本組。±X の面の外端太は dzB 上げる）."""
    h = "hB" if k % 2 else "hA"
    dz = "0" if k % 2 else "dzB"
    return f"""rotz {(k - 1) * 90}
material "cf_ply"
for i = 1 to int(nPl{k} / 2)
	add pl{k}[2 * i - 1], {h}, 0
	block pl{k}[2 * i] - pl{k}[2 * i - 1], plyT, H
	del 1
next i
material "cf_wood"
for i = 1 to nSg{k}
	add sg{k}a[i] - sgB / 2, {h} + plyT, 0
	block sgB, sgH, H
	del 1
next i
material "cf_steel"
if clampOn then
	! コラムクランプの腕（角の先まで。角でくさび留め。±X の面の腕は腕のせいだけ上に重ねる）
	for j = 1 to nT
		add -{"hA" if k % 2 else "hB"} - plyT - sgH - 0.12, {h} + plyT + sgH, tz[j] - clH / 2 + {"0" if k % 2 else "clH"}
		block 2 * ({"hA" if k % 2 else "hB"} + plyT + sgH + 0.12), clT, clH
		! くさび（両端）
		material "cf_bolt"
		add 0.03, clT, clH * 0.2
		block 0.02, 0.012, clH * 0.6
		del 1
		add 2 * ({"hA" if k % 2 else "hB"} + plyT + sgH + 0.12) - 0.05, clT, clH * 0.2
		block 0.02, 0.012, clH * 0.6
		del 1
		material "cf_steel"
		del 1
	next j
endif
for i = 1 to int(nTb{k} / 2) * (1 - clampOn)
	for j = 1 to nT
		for kk = -1 to 1 step 2
			add tb{k}a[2 * i - 1], {h} + plyT + sgH + r, tz[j] + {dz} + kk * (r + gap)
			roty 90
			cylind tb{k}a[2 * i] - tb{k}a[2 * i - 1], r
			del 2
		next kk
	next j
next i
del 1
"""


SCRIPT_2D = """﻿! 柱の型枠 2D
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "cfT" "ＭＳ Ｐゴシック", texSiz, 1, 0
! 面ごとのせき板・桟木・外端太
""" + "".join(_face2d(k) for k in range(1, 5)) + """! フォームタイ
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
define material "cf_bolt" 2, 0.30, 0.30, 0.32
H = ZZYZX
gap = 0.006
! ---- 面ごとのせき板・桟木・外端太（2本組） ----
""" + "".join(_face3d(k) for k in range(1, 5)) + """! ---- フォームタイ ----
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
