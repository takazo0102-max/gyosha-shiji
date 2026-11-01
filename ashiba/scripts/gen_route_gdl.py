"""部品 ashiba_route（場内の車両動線。1本の通路に1部品）の HSF を書き出す.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の3番。割付と検定は src/ashiba/site_route.py（出典はそちら）、置くのは
scripts/route_run.py（敷鉄板は別の部品 ashiba_plate を区間ごとに）。原点＝通路の始め（ゲートの側）、座標は文字のパラメータ（mm）。
- 平面: 通路の帯（eX・eY）・中心線と進む向きの矢（cX・cY）・曲がり角の掃引（回転中心 aX・aY、外側前端角と内側後輪の円 aR、
  角度 aA）・拡幅の注記（aW＝拡幅 ×0.1m）・名前と車両
- 3D: 通路の面（敷鉄板の下に薄く）
  python3 scripts/gen_route_gdl.py     # gdl/hsf/ashiba_route を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_route"
MAIN_GUID = "9C1E5A37-2D84-4B6F-8E13-7A0F4C92D6B5"
LISTS = (("cX", "qcx", "kC", "/ 1000"), ("cY", "qcy", "kCy", "/ 1000"), ("eX", "qex", "kE", "/ 1000"),
         ("eY", "qey", "kEy", "/ 1000"), ("aX", "qox", "kO", "/ 1000"), ("aY", "qoy", "kOy", "/ 1000"),
         ("aR", "qr", "kR", "/ 1000"), ("aA", "qa", "kA", ""), ("aW", "qw", "kW", "/ 10"))


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("String", "cX", "中心線の X（mm。始めの点から）", "0,30000,30000"),
        _param("String", "cY", "中心線の Y", "0,0,25000"),
        _param("String", "eX", "通路の帯の X", "0,28000,28000,32000,32000,0"),
        _param("String", "eY", "通路の帯の Y", "2000,2000,25000,25000,-2000,-2000"),
        _param("String", "aX", "曲がり角の回転中心の X", "25059"),
        _param("String", "aY", "曲がり角の回転中心の Y", "4941"),
        _param("String", "aR", "曲がり角ごとの外側前端角・内側後輪の半径", "7643,3064"),
        _param("String", "aA", "曲がり角ごとの円弧の始めと終わりの角度（度）", "-90,0"),
        _param("String", "aW", "曲がり角ごとの拡幅（0.1m 単位。0＝不要）", "19"),
        _param("Length", "rtW", "通路の幅", 4.0),
        _param("String", "rtName", "名前（注記）", "通路1"),
        _param("String", "rtVeh", "車両と通行（注記）", "一方通行 幅4.0m 10t ダンプ"),
        _param("Boolean", "showSw", "曲がり角の掃引（車両の通る範囲）を描く", 1),
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


def _master() -> str:
    out = ["﻿! 場内通路: 文字のパラメータ（mm・度）を配列に読む"]
    for prm, arr, cnt, scale in LISTS:
        out += [f"dim {arr}[]", f"{cnt} = 0", f"rest = {prm}", "while strlen(rest) > 0 do", '\tpc = strstr(rest, ",")',
                "\tif pc > 0 then", "\t\titem = strsub(rest, 1, pc - 1)", "\t\trest = strsub(rest, pc + 1, strlen(rest) - pc)",
                "\telse", "\t\titem = rest", '\t\trest = ""', "\tendif", '\tk = split(item, "%n", v)', "\tif k > 0 then",
                f"\t\t{cnt} = {cnt} + 1", f"\t\t{arr}[{cnt}] = v {scale}", "\tendif", "endwhile"]
    out += ["kC = min(kC, kCy)", "kE = min(kE, kEy)", "kO = min(kO, kOy)"]
    return "\n".join(out) + "\n"


SCRIPT_2D = """﻿! 場内通路 2D: 通路の帯・中心線と矢・曲がり角の掃引・拡幅の注記・名前
pen penEquip
define style "rtT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "rtT"
! 通路の帯
if kE > 2 then
	for i = 1 to kE
		j = i + 1
		if j > kE then j = 1
		line2 qex[i], qey[i], qex[j], qey[j]
	next i
endif
! 中心線と進む向きの矢（区間の真ん中）
for i = 1 to kC - 1
	line2 qcx[i], qcy[i], qcx[i + 1], qcy[i + 1]
	sl = sqr((qcx[i + 1] - qcx[i]) ^ 2 + (qcy[i + 1] - qcy[i]) ^ 2)
	if sl > 0.01 then
		ux = (qcx[i + 1] - qcx[i]) / sl
		uy = (qcy[i + 1] - qcy[i]) / sl
		mx = (qcx[i] + qcx[i + 1]) / 2
		my = (qcy[i] + qcy[i + 1]) / 2
		line2 mx, my, mx - 0.8 * ux + 0.4 * uy, my - 0.8 * uy - 0.4 * ux
		line2 mx, my, mx - 0.8 * ux - 0.4 * uy, my - 0.8 * uy + 0.4 * ux
	endif
next i
! 曲がり角の掃引（外側前端角 Ro と内側後輪 ri の円弧）と拡幅の注記
if showSw then
	for k = 1 to kO
		if 2 * k <= kR and 2 * k <= kA then
			arc2 qox[k], qoy[k], qr[2 * k - 1], qa[2 * k - 1], qa[2 * k]
			arc2 qox[k], qoy[k], qr[2 * k], qa[2 * k - 1], qa[2 * k]
			line2 qox[k] - 0.2, qoy[k], qox[k] + 0.2, qoy[k]
			line2 qox[k], qoy[k] - 0.2, qox[k], qoy[k] + 0.2
		endif
		if k <= kW then
			if qw[k] > 0 then
				add2 qox[k], qoy[k]
				rot2 -SYMB_ROTANGLE
				text2 0, -0.6, "角" + str(k, 1, 0) + " 拡幅 +" + str(qw[k], 3, 1) + "m"
				del 2
			endif
		endif
	next k
endif
! 名前と車両（始めの区間の真ん中の左に。図面の向きに関係なく水平）
if kC > 1 then
	add2 (qcx[1] + qcx[2]) / 2, (qcy[1] + qcy[2]) / 2
	rot2 -SYMB_ROTANGLE
	text2 0, rtW / 2 + 1.2, rtName
	text2 0, rtW / 2 + 0.6, rtVeh
	del 2
endif
for i = 1 to kC
	hotspot2 qcx[i], qcy[i]
next i
"""

SCRIPT_3D = """﻿! 場内通路 3D: 通路の面（敷鉄板の下に薄く）
define material "rt_road" 2, 0.55, 0.53, 0.50
material "rt_road"
if kE > 2 then
	for i = 1 to kE
		put qex[i], qey[i]
	next i
	add 0, 0, -0.006
	prism kE, 0.004, get(kE * 2)
	del 1
endif
for i = 1 to kC
	hotspot qcx[i], qcy[i], 0
next i
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(_master(), encoding="utf-8")
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
    print(f"ashiba_route: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
