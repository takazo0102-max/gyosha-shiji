"""部品 ashiba_house（仮設建物。ユニットハウスの1棟に1部品）の HSF を書き出す.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の4番。型と判定は src/ashiba/site_house.py（出典はそちら）、置くのは
scripts/house_run.py。原点＝建物の手前の左の隅（地盤）、+X＝長手、+Y＝奥。手前（Y0）の面に出入口と窓。
- 型 hsType（1〜5 スーパーハウス 1・2・3.1・3.8・5坪、6 仮設トイレ、7 快適トイレハウス）、連棟 nUnit（ハウスは奥へ、トイレは横へ）、
  段 nTier（1〜3）、段ごとの用途 use1〜3（1 事務所・2 詰所・3 休憩所・4 更衣室・5 会議室・6 倉庫・7 トイレ・8 シャワー）
- 2段以上は手前に外廊下（幅 corrW・手すり 1,100）と2階への外階段（カナモト ハウス用階段 FE用 900×4,100・KD用 1,150×4,990。
  幅 stairW・長さ stairL、stairSd＝0 で X0 の外・1 で X の外。利用者の指定 2026-11-01: 仮設建物の階段も製品の規格にして）
  python3 scripts/gen_house_gdl.py     # gdl/hsf/ashiba_house を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from ashiba.site_house import HOUSES, USES  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_house"
MAIN_GUID = "2F8B6D41-5A93-4C07-B1E8-6D2A9F0C37E5"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "hsType", "型（一覧で選ぶ）", 4),
        _param("Integer", "nUnit", "連棟の数（ハウスは奥へ、トイレは横へ）", 1),
        _param("Integer", "nTier", "段の数（1〜3）", 1),
        _param("Integer", "use1", "1階の用途", 1),
        _param("Integer", "use2", "2階の用途", 1),
        _param("Integer", "use3", "3階の用途", 1),
        _param("Integer", "stairSd", "外階段の位置（0＝左の端の外・1＝右の端の外）", 0),
        _param("Length", "stairW", "外階段の幅（製品の幅）", 0.9),
        _param("Length", "stairL", "外階段の長さ（製品の長さ。FE用 4.1・KD用 4.99）", 4.1),
        _param("String", "stName", "外階段の品名（注記）", "ハウス用階段 FE用"),
        _param("Length", "corrW", "2階の外廊下の幅", 1.0),
        _param("String", "hsName", "名前（注記）", "仮設建物"),
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
    n = len(HOUSES)
    tab = [f"dim hwT[{n}], hdT[{n}], hhT[{n}], hkT[{n}]"]
    for k, (_nm, w, d, h, _kg, toil) in HOUSES.items():
        tab += [f"hwT[{k}] = {w / 1000:.3f}", f"hdT[{k}] = {d / 1000:.3f}", f"hhT[{k}] = {h / 1000:.3f}", f"hkT[{k}] = {toil}"]
    names = [f"dim usN[{len(USES)}]"] + [f'usN[{k}] = "{v}"' for k, v in USES.items()]
    return "﻿! 仮設建物: 型の寸法（site_house.HOUSES）と並べ方\n" + "\n".join(tab + names) + f"""
kT = max(1, min({n}, hsType))
uw = hwT[kT]
ud = hdT[kT]
uh = hhT[kT]
isT = hkT[kT] > 0
nU = max(1, nUnit)
nT = max(1, min(3, nTier))
if isT then nT = 1
lx = uw
ly = ud * nU
if isT then
	lx = uw * nU
	ly = ud
endif
dim tu[3]
tu[1] = max(1, min({len(USES)}, use1))
tu[2] = max(1, min({len(USES)}, use2))
tu[3] = max(1, min({len(USES)}, use3))
! 2階より上: 手前の外廊下と2階への外階段（製品の長さ stairL を段に分ける。蹴上 0.2 以下）
upOn = nT >= 2
nRs = ceil(uh / 0.2 - 0.0001)
rsH = uh / nRs
stL = max(1, stairL)
gStp = stL / max(1, nRs - 1)
stX = -stL
if stairSd = 1 then stX = lx
"""


SCRIPT_2D = """﻿! 仮設建物 2D: ユニットの外形・出入口・窓・2階の外廊下と外階段・名前と段ごとの用途
pen penEquip
define style "hsT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "hsT"
for u = 1 to nU
	x0 = 0
	y0 = (u - 1) * ud
	if isT then
		x0 = (u - 1) * uw
		y0 = 0
	endif
	rect2 x0, y0, x0 + uw, y0 + ud
	! 出入口（手前の面。トイレは各ユニット、ハウスは手前の1つ）
	if isT or u = 1 then
		dw = min(0.8, uw - 0.1)
		dx = x0 + 0.05
		if isT then dx = x0 + (uw - dw) / 2
		line2 dx, y0, dx, y0 - dw
		arc2 dx, y0, dw, 270, 360
	endif
	! 窓（手前の面、ハウスだけ）
	if isT = 0 and u = 1 and uw > 2.5 then
		nW = max(1, int((uw - 1.0) / 1.8))
		for i = 1 to nW
			wx = 1.0 + (uw - 1.0) * (i - 0.5) / nW - 0.6
			line2 wx, -0.03, wx + 1.2, -0.03
			line2 wx, 0.03, wx + 1.2, 0.03
		next i
	endif
next u
! 2階の外廊下と外階段（上る向きの矢）
if upOn and isT = 0 then
	rect2 0, -corrW, lx, 0
	rect2 stX, -stairW, stX + stL, 0
	for i = 1 to nRs - 2
		line2 stX + i * gStp, -stairW, stX + i * gStp, 0
	next i
	add2 stX + stL / 2, -stairW - 0.4
	rot2 -SYMB_ROTANGLE
	text2 0, 0, stName
	del 2
	ax = stX + 0.2
	bx = stX + stL - 0.2
	if stairSd = 1 then
		ax = stX + stL - 0.2
		bx = stX + 0.2
	endif
	line2 ax, -stairW / 2, bx, -stairW / 2
	line2 bx, -stairW / 2, bx - 0.25 * sgn(bx - ax), -stairW / 2 + 0.15
	line2 bx, -stairW / 2, bx - 0.25 * sgn(bx - ax), -stairW / 2 - 0.15
endif
! 名前と段ごとの用途（図面の向きに関係なく水平）
add2 lx / 2, ly / 2
rot2 -SYMB_ROTANGLE
tx = usN[tu[1]]
if nT >= 2 then tx = "1F " + usN[tu[1]] + " / 2F " + usN[tu[2]]
if nT >= 3 then tx = tx + " / 3F " + usN[tu[3]]
text2 0, 0.25, hsName
text2 0, -0.25, tx
del 2
hotspot2 0, 0
hotspot2 lx, 0
hotspot2 lx, ly
hotspot2 0, ly
"""

SCRIPT_3D = """﻿! 仮設建物 3D: ユニット・出入口・窓・2階の外廊下と手すり・外階段
define material "hs_body" 2, 0.88, 0.89, 0.87
define material "hs_toil" 2, 0.80, 0.88, 0.95
define material "hs_base" 2, 0.30, 0.30, 0.32
define material "hs_glass" 2, 0.35, 0.50, 0.65
define material "hs_door" 2, 0.55, 0.57, 0.60
define material "hs_rail" 2, 0.90, 0.75, 0.10
resol 8
for t = 1 to nT
	for u = 1 to nU
		x0 = 0
		y0 = (u - 1) * ud
		if isT then
			x0 = (u - 1) * uw
			y0 = 0
		endif
		z0 = (t - 1) * uh
		material "hs_base"
		add x0 + 0.005, y0 + 0.005, z0
		block uw - 0.01, ud - 0.01, 0.12
		del 1
		material "hs_body"
		if isT then material "hs_toil"
		add x0 + 0.005, y0 + 0.005, z0 + 0.12
		block uw - 0.01, ud - 0.01, uh - 0.12
		del 1
		if isT or u = 1 then
			material "hs_door"
			dw = min(0.8, uw - 0.1)
			dx = x0 + 0.05
			if isT then dx = x0 + (uw - dw) / 2
			add dx, -0.01, z0 + 0.15
			block dw, 0.02, min(1.9, uh - 0.4)
			del 1
		endif
		if isT = 0 and u = 1 and uw > 2.5 then
			material "hs_glass"
			nW = max(1, int((uw - 1.0) / 1.8))
			for i = 1 to nW
				wx = 1.0 + (uw - 1.0) * (i - 0.5) / nW - 0.6
				add wx, -0.01, z0 + 0.9
				block 1.2, 0.02, 1.0
				del 1
			next i
		endif
	next u
next t
if upOn and isT = 0 then
	for t = 2 to nT
		zf = (t - 1) * uh
		! 外廊下の床と手すり（手すり 1.1・中桟 0.55、柱は 1.8 以内）
		material "hs_base"
		add 0, -corrW, zf - 0.12
		block lx, corrW, 0.12
		del 1
		material "hs_rail"
		nPo = max(1, ceil(lx / 1.8 - 0.0001))
		for i = 0 to nPo
			add lx * i / nPo, -corrW + 0.03, zf
			cylind 1.1, 0.0243
			del 1
		next i
		for r = 1 to 2
			hz = 1.1
			if r = 2 then hz = 0.55
			add 0, -corrW + 0.03, zf + hz
			roty 90
			cylind lx, 0.0243
			del 2
		next r
		! 廊下の階段の無い側の端
		ex = lx
		if stairSd = 1 then ex = 0
		for r = 1 to 2
			hz = 1.1
			if r = 2 then hz = 0.55
			add ex, -corrW + 0.03, zf + hz
			rotx -90
			cylind corrW - 0.03, 0.0243
			del 2
		next r
	next t
	! 2階への外階段（段板と側桁）
	material "hs_base"
	for i = 1 to nRs - 1
		sx = stX + (i - 1) * gStp
		if stairSd = 1 then sx = stX + stL - i * gStp
		add sx, -stairW, i * rsH - 0.04
		block gStp, stairW, 0.04
		del 1
	next i
	material "hs_rail"
	ang = atn(uh / max(0.3, stL))
	sl = sqr(stL * stL + uh * uh)
	for s = 0 to 1
		ys = -stairW + 0.03
		if s = 1 then ys = -0.03
		if stairSd = 0 then
			add stX, ys, 1.1
			roty 90 - ang
		else
			add stX + stL, ys, 1.1
			roty -90 + ang
		endif
		cylind sl, 0.0243
		del 2
	next s
endif
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(_master(), encoding="utf-8")
    vl = ("﻿! 仮設建物: 型・用途の一覧\n"
          + "values{2} \"hsType\" " + ", ".join(f'{k}, "{v[0]}"' for k, v in HOUSES.items()) + "\n"
          + "".join(f"values{{2}} \"use{i}\" " + ", ".join(f'{k}, "{v}"' for k, v in USES.items()) + "\n" for i in (1, 2, 3))
          + "values \"nTier\" 1, 2, 3\nvalues \"stairSd\" 0, 1\nvalues \"nUnit\" range [1, 12]\n")
    (OUT / "scripts" / "vl.gdl").write_text(vl, encoding="utf-8")
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
    print(f"ashiba_house: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
