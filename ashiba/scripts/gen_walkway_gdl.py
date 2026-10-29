"""部品 ashiba_walkway（仮設通路。アルミ製の伸縮通路 日工セック ライトブリッジ。1本に1部品）の HSF を書き出す.

利用者の指定（2026-10-29）「https://www.nikkosec.co.jp/page-73/ 次足場はこういうのにも対応できるようにしたい」。
両端の島（足場の塔。部品 ashiba_stage）の布材に本体のフックを掛けて渡す。形はカタログの寸法: 床幅 660（縞板）・
外枠 766・全幅 915、手すりの間 854・高さ 966・中桟 484、幅木 H125。本体は2段の伸縮（外の枠の中を内の枠が滑る）。

原点＝始めの島の布材の上の通路の芯（フックの掛かる所）。+X＝通路の向き（終わりの島へ）、faceAng で向き。
床の上端は始め zDeck・終わり zEnd（差があれば傾けて渡す）。
  python3 scripts/gen_walkway_gdl.py     # gdl/hsf/ashiba_walkway を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_walkway"
MAIN_GUID = "9FB2AD7A-3276-410F-90D0-6BDB2F59072D"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Angle", "faceAng", "通路の向き（度。+X＝始めの島から終わりの島へ）", 0),
        _param("Length", "wkL", "長さ（島の布材の間・平面）", 5),
        _param("Length", "zDeck", "始めの床の高さ（階の高さから）", 1.8),
        _param("Length", "zEnd", "終わりの床の高さ（同上。差があれば傾けて渡す）", 1.8),
        _param("String", "wkModel", "機種（data/walkway_models.csv）", "LB-4556"),
        _param("Length", "deckW", "床幅（縞板）", 0.66),
        _param("Length", "frW", "外枠の幅", 0.766),
        _param("Length", "ovW", "全幅（手すりの外まで）", 0.915),
        _param("Length", "railSp", "手すりの間（芯々）", 0.854),
        _param("Length", "railH", "手すりの高さ（床から）", 0.966),
        _param("Length", "midH", "中桟の高さ（床から）", 0.484),
        _param("Length", "toeH", "幅木の高さ", 0.125),
        _param("String", "stName", "通路の名前", "仮設通路"),
        _param("Boolean", "showText", "平面に機種と長さを書く", 1),
        "\t\t<Material Name=\"matAl\">\n\t\t\t<Description><![CDATA[\"アルミの材質（0＝アルミの色）\"]]></Description>\n"
        "\t\t\t<Value>0</Value>\n\t\t</Material>\n",
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


SCRIPT_1D = """﻿! 仮設通路: 伸縮の継ぎ目（外の枠の終わり・内の枠の始め。長さの比で描く）
L = max(0.5, wkL)
xJ0 = L * 0.45
xJ1 = L * 0.55
"""

SCRIPT_2D = """﻿! 仮設通路 2D（平面）: 全幅の外形・床幅・手すり・伸縮の継ぎ目・両端のフック・機種と長さ
define style "wkTx" "ＭＳ Ｐゴシック", texSiz, 5, 0
pE = penEquip
if pE < 1 then pE = 1
pen pE
rot2 faceAng
hotspot2 0, 0
hotspot2 L, 0
line_type 1
rect2 0, -ovW / 2, L, ovW / 2
line2 0, -deckW / 2, L, -deckW / 2
line2 0, deckW / 2, L, deckW / 2
line2 0, -railSp / 2, L, -railSp / 2
line2 0, railSp / 2, L, railSp / 2
line2 xJ0, -frW / 2, xJ0, frW / 2
line2 xJ1, -frW / 2, xJ1, frW / 2
! 両端のフック（布材に掛ける所）
for sd = -1 to 1 step 2
	rect2 -0.08, sd * frW / 2 - 0.05, 0, sd * frW / 2 - 0.03
	rect2 L, sd * frW / 2 - 0.05, L + 0.08, sd * frW / 2 - 0.03
next sd
! 向き（始め→終わり）
line2 L / 2 - 0.25, 0, L / 2 + 0.25, 0
line2 L / 2 + 0.25, 0, L / 2 + 0.15, 0.06
line2 L / 2 + 0.25, 0, L / 2 + 0.15, -0.06
if showText then
	style "wkTx"
	text2 L / 2, ovW / 2 + 0.15, "仮設通路 " + wkModel + " L=" + str(L * 1000, 4, 0)
endif
"""

SCRIPT_3D = """﻿! ============================================================
! 仮設通路 3D（日工セック ライトブリッジ）。利用者の指定 2026-10-29: 次足場はこういうのにも対応できるようにしたい
! 外の枠（始め側）の中を内の枠（終わり側）が滑る2段の伸縮。両端のフックを島の布材に掛ける
! ============================================================
resol 10
define material "wk_al" 2, 0.80, 0.82, 0.85
define material "wk_toe" 2, 0.95, 0.80, 0.15
mAl = IND(MATERIAL, "wk_al")
if matAl > 0 then mAl = matAl
mTo = IND(MATERIAL, "wk_toe")
dz = zEnd - zDeck
Ls = sqr(L * L + dz * dz)
sl = atn(dz / L)
x0 = Ls * 0.45
x1 = Ls * 0.55
gW = 0.05            ! 桁の幅
gH = 0.12            ! 桁の高さ（床の上端から下へ）
hw = frW / 2
rotz faceAng
add 0, 0, zDeck
roty -sl
material mAl
! ---- 桁（外の枠は 0〜x1、内の枠は x0〜Ls で外の枠の内側） ----
for sd = -1 to 1 step 2
	add 0, sd * (hw - gW / 2) - gW / 2, -gH
	block x1, gW, gH
	del 1
	add x0, sd * (hw - gW * 1.5) - gW / 2, -gH + 0.01
	block Ls - x0, gW, gH - 0.02
	del 1
next sd
! ---- 床（縞板）と横の桟 ----
add 0, -deckW / 2, -0.004
block x1, deckW, 0.004
del 1
add x1, -deckW / 2 + gW, -0.010
block Ls - x1, deckW - 2 * gW, 0.006
del 1
nC = max(2, int(Ls / 0.6) + 1)
for k = 0 to nC
	xc = min(Ls - 0.03, k * Ls / nC)
	add xc, -hw + gW, -gH + 0.02
	block 0.03, frW - 2 * gW, 0.04
	del 1
next k
! ---- フック（両端。布材の上に掛けて下へ曲がる） ----
for sd = -1 to 1 step 2
	for en = 0 to 1
		if en = 0 then
			xh = -0.08
		else
			xh = Ls
		endif
		add xh, sd * (hw - 0.04) - 0.006, -0.012
		block 0.08, 0.012, 0.012
		del 1
		if en = 0 then
			add xh, sd * (hw - 0.04) - 0.006, -0.10
		else
			add xh + 0.068, sd * (hw - 0.04) - 0.006, -0.10
		endif
		block 0.012, 0.012, 0.09
		del 1
	next en
next sd
! ---- 手すり（両側。支柱は 1.2m 以内ごと、手すり・中桟・幅木） ----
nP = max(1, int(Ls / 1.2 + 0.99))
for sd = -1 to 1 step 2
	yR = sd * railSp / 2
	for k = 0 to nP
		add min(Ls - 0.02, max(0.02, k * Ls / nP)), yR, 0
		cylind railH, 0.017
		del 1
	next k
	for hh = 1 to 2
		if hh = 1 then
			zr = railH
		else
			zr = midH
		endif
		add 0.02, yR, zr
		roty 90
		cylind Ls - 0.04, 0.0175
		del 2
	next hh
	material mTo
	add 0.02, yR - sd * 0.03 - 0.014, 0
	block Ls - 0.04, 0.028, toeH
	del 1
	material mAl
next sd
del 3
end
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
    print(f"ashiba_walkway: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
