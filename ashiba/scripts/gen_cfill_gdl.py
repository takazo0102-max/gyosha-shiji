"""部品 ashiba_cfill（斜めの角の隅のつなぎ）の HSF を書き出す.

利用者の指定（2026-10-31）「斜めの角もつながるようにしてちょ 無理な場合はかど合わせてアンチをし単管手すり作成か足場板と単管手すりに
するか」。割付は縦・横しか解けないので、直角でない角の2本の足場はそれぞれ1本で解き、そのあいだのすき間をこの部品でふさぐ。

原点＝線の角（2本の足場の内側の列の交点）。polyX・polyY＝床の形（原点からの mm、左回り）、railE＝手すり・幅木を付ける辺の番号
（辺 k は点 k→k+1。0 から）、levList＝作業床の段の高さ（原点の高さから mm）。各段に作業床（deckKind 1＝アンチ・2＝足場板）、
床の下に単管の受け（外の辺に直角に2本。床の板は外の辺に平行）、手すりの辺に単管の上桟（床から 950）・中桟（450）と幅木（150）。
  python3 scripts/gen_cfill_gdl.py     # gdl/hsf/ashiba_cfill を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_box_gdl import _parse  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_cfill"
MAIN_GUID = "3B7E2C19-6A4D-4F0B-8E51-2C9D7A1F4B63"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("String", "polyX", "床の形の x（原点からの mm、カンマ区切り。左回り）", "0,0,800,0"),
        _param("String", "polyY", "床の形の y（同上）", "0,-914,-457,0"),
        _param("String", "railE", "手すり・幅木を付ける辺の番号（辺 k は点 k→k+1。0 から。カンマ区切り）", "1"),
        _param("String", "levList", "作業床の段の高さ（原点の高さから mm、カンマ区切り）", "1780,3580,5380,7180"),
        _param("Integer", "deckKind", "作業床（1＝アンチ・2＝足場板）", 1),
        _param("Length", "deckT", "作業床の厚み", 0.04),
        _param("Length", "railH1", "上桟の高さ（床から）", 0.95),
        _param("Length", "railH2", "中桟の高さ（床から）", 0.45),
        _param("Length", "toeH", "幅木の高さ", 0.15),
        _param("String", "cName", "名前（平面の注記）", "隅のつなぎ"),
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


def _parse_all(src: str, arr: str, cnt: str) -> str:
    """カンマ区切りの mm の並び（負の値・0 も）を配列 arr[1..cnt]（m）に."""
    return f"""dim {arr}[]
{cnt} = 0
rest = {src}
while strlen(rest) > 0 do
	pc = strstr(rest, ",")
	if pc > 0 then
		item = strsub(rest, 1, pc - 1)
		rest = strsub(rest, pc + 1, strlen(rest) - pc)
	else
		item = rest
		rest = ""
	endif
	k = split(item, "%n", v)
	if k > 0 then
		{cnt} = {cnt} + 1
		{arr}[{cnt}] = v / 1000
	endif
endwhile
"""


SCRIPT_1D = ("﻿! 隅のつなぎ: 床の形・手すりの辺・段の高さを読む（m）\n"
             + _parse_all("polyX", "px", "nP") + _parse_all("polyY", "py", "nPy")
             + _parse_all("railE", "re", "nR") + _parse("levList", "lv", "nL", "/ 1000") + """if nPy < nP then nP = nPy
dim rl[]
for k = 1 to nP
	rl[k] = 0
next k
for k = 1 to nR
	ix = round_int(re[k] * 1000) + 1
	if ix >= 1 and ix <= nP then rl[ix] = 1
next k
if deckKind = 2 then
	dName = "足場板"
else
	dName = "アンチ"
endif
cx = 0
cy = 0
for k = 1 to nP
	cx = cx + px[k] / nP
	cy = cy + py[k] / nP
next k
""")

SCRIPT_2D = """﻿! 隅のつなぎ 2D: 床の形、手すりの辺（二重線）、床の向きの斜線、名前
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "cfT" "ＭＳ Ｐゴシック", texSiz, 5, 0
for k = 1 to nP
	k2 = k + 1
	if k2 > nP then k2 = 1
	line2 px[k], py[k], px[k2], py[k2]
	if rl[k] then
		dx = px[k2] - px[k]
		dy = py[k2] - py[k]
		L = sqr(dx * dx + dy * dy)
		if L > 0.001 then
			ox = dy / L * 0.05
			oy = -dx / L * 0.05
			line2 px[k] + ox, py[k] + oy, px[k2] + ox, py[k2] + oy
		endif
	endif
	hotspot2 px[k], py[k]
next k
! 床の範囲の目印（重心から各点へ短い線）
for k = 1 to nP
	line2 cx, cy, cx + (px[k] - cx) * 0.3, cy + (py[k] - cy) * 0.3
next k
style "cfT"
text2 cx, cy, cName + "（" + dName + "＋単管手すり）"
"""

SCRIPT_3D = """﻿! ============================================================
! 隅のつなぎ 3D: 各段に作業床（多角形の板）、手すりの辺に単管の上桟・中桟（φ48.6）と幅木、床の下に単管の受け
! ============================================================
resol 8
define material "cf_deck" 2, 0.80, 0.72, 0.45
define material "cf_steel" 2, 0.62, 0.62, 0.66
define material "cf_toe" 2, 0.55, 0.55, 0.58
r = 0.0243
for i = 1 to nL
	z = lv[i]
	! 作業床
	material "cf_deck"
	addz z - deckT
	put px[1], py[1], 15
	for k = 2 to nP
		put px[k], py[k], 15
	next k
	prism_ nP, deckT, get(nsp)
	del 1
	material "cf_steel"
	for k = 1 to nP
		if rl[k] then
			k2 = k + 1
			if k2 > nP then k2 = 1
			dx = px[k2] - px[k]
			dy = py[k2] - py[k]
			L = sqr(dx * dx + dy * dy)
			if L > 0.001 then
				if abs(dx) < 0.000001 then
					ang = 90 * sgn(dy)
				else
					ang = atn(dy / dx)
					if dx < 0 then ang = ang + 180
				endif
				! 上桟・中桟（両側の足場の支柱にかけるので 300 ずつ延ばす）
				for h = 1 to 2
					if h = 1 then
						zh = z + railH1
					else
						zh = z + railH2
					endif
					add px[k], py[k], zh
					rotz ang
					roty 90
					addz -0.3
					cylind L + 0.6, r
					del 4
				next h
				! 幅木
				material "cf_toe"
				add px[k], py[k], z
				rotz ang
				addy -0.025
				block L, 0.025, toeH
				del 3
				material "cf_steel"
				! 床の受け: 外の辺に直角に2本（辺の両端の近く。床の板は外の辺に平行に並べて、この2本に掛ける。アンチは平行な
				! 受けにしか掛からないので、斜めの角でも受けは平行に渡す）。長さは床の奥行き＋300
				dep = 0
				for m = 1 to nP
					dd = ((px[m] - px[k]) * (-dy) + (py[m] - py[k]) * dx) / L
					if abs(dd) > dep then dep = abs(dd)
				next m
				for h = 1 to 2
					if h = 1 then
						s = 0.1
					else
						s = L - 0.1
					endif
					add px[k] + dx / L * s, py[k] + dy / L * s, z - deckT - r
					rotz ang + 90
					roty 90
					addz -0.15
					cylind dep + 0.3, r
					del 4
				next h
			endif
		endif
	next k
next i
end
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text("﻿values{2} \"deckKind\" 1, \"アンチ\", 2, \"足場板\"\n", encoding="utf-8")
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
    print(f"ashiba_cfill: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
