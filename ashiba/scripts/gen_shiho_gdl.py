"""部品 ashiba_shiho（山留め支保工の部材1本: 切梁・腹起し・火打ち・中間杭）の HSF を書き出す.

利用者の指定（2026-11-06）「縦横の切梁と中間杭も足して 切張り・腹起こしは手動でできるようにして LOD高く」。

shKind: 1 切梁（H形鋼のフランジが上下。主材・補助ピース・キリンジャッキとジャッキカバー・継手のカバープレート、上段の切梁は下段との
交差部のアングルピースと交叉部直ボルト）、2 腹起し（フランジが縦。主材・補助ピース・カバープレート・ブラケット）、3 火打ち（両端に
火打受ピース）、4 中間杭（H形鋼・段ごとの切梁受けブラケット・締付用 U ボルト）。
原点＝部材の始めの芯の平面（GL の高さに置く）、+X＝部材の向き、高さは shZ（GL から下の深さ）。中間杭は原点＝杭の芯、+X＝下段の切梁の側。
割付は src/ashiba/shiho.py、置くのは scripts/ywall_run.py（縦横の切梁）と scripts/shiho_run.py（手で引いた線から）.
  python3 scripts/gen_shiho_gdl.py     # gdl/hsf/ashiba_shiho を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gdl_draft  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402
from gen_ywall_gdl import _list  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_shiho"
MAIN_GUID = "3B7D2E91-5C4A-4F08-9E6B-A21C8D47F530"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "shKind", "種類（1 切梁・2 腹起し・3 火打ち・4 中間杭）", 1),
        _param("Length", "shL", "部材の長さ（芯。中間杭は杭頭から先端まで）", 10),
        _param("Length", "shZ", "部材の芯の深さ（GL から下。正）。中間杭は杭頭", 1),
        _param("Length", "sH", "H形鋼の高さ H", 0.3),
        _param("Length", "sB", "H形鋼のフランジ幅 B", 0.3),
        _param("Length", "sT1", "H形鋼のウェブの厚さ t1", 0.01),
        _param("Length", "sT2", "H形鋼のフランジの厚さ t2", 0.015),
        _param("String", "shName", "名前", "切梁1"),
        _param("String", "shInfo", "平面の注記（種類・形・深さ）", "切梁 H-300（30HA）GL-1,000"),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        _param("String", "sgL", "始めからの並びの長さ（mm）", "525,300,7000,2000"),
        _param("String", "sgT", "並びの種類（1 主材・2 補助ピース・3 キリンジャッキ・4 火打受ピース）", "3,2,1,1"),
        _param("Length", "cvL", "カバープレートの長さ", 0.6),
        _param("Length", "cvT", "カバープレートの厚さ", 0.012),
        _param("Length", "endT", "主材の端板の厚さ", 0.016),
        _param("Length", "jkW", "キリンジャッキの端板の角", 0.298),
        _param("Length", "jcL", "ジャッキカバーの長さ", 1.5),
        _param("String", "xcX", "上段の切梁: 下段と交わる所（始めから mm）", ""),
        _param("String", "xcH", "交わる下段の切梁の高さ（mm）", ""),
        _param("Length", "xaL", "交差部のアングルピースの長さ", 0.55),
        _param("Length", "xbO", "交叉部直ボルトの芯から（孔の間の半分）", 0.17),
        _param("String", "brX", "腹起しのブラケットの位置（mm）", ""),
        _param("Length", "hpA", "火打受ピースの底の長さ", 0.45),
        _param("Integer", "hpS", "火打受ピースの底の向き（始めから見て 1 左へ開く・-1 右へ開く）", 1),
        _param("Length", "shBot", "中間杭の先端の深さ（GL から下）", 9),
        _param("String", "pkZ", "中間杭: 切梁受けブラケットの天端の深さ（mm。段ごと）", "1150,4150"),
        _param("Length", "pkR", "中間杭の芯から下段の切梁の芯まで", 0.35),
        _param("Length", "bkL", "切梁受けブラケットの腕の長さ", 0.65),
        _param("Length", "bkH", "切梁受けブラケットの高さ", 0.45),
        _param("Length", "ubW", "締付用 U ボルトの幅", 0.34),
        _param("Length", "ubH", "締付用 U ボルトの高さ", 0.35),
        *gdl_draft.params(),
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


SCRIPT_1D = ("﻿! 山留め支保工: 並びを読む（m）\n"
             + _list("sgL", "sgv", "nSg") + _list("sgT", "sgk", "nSgT", "1") + _list("xcX", "xcv", "nXc") + _list("xcH", "xchv", "nXh")
             + _list("brX", "brv", "nBr") + _list("pkZ", "pkv", "nPk") + """if nSgT < nSg then nSg = nSgT
if nXh < nXc then nXc = nXh
zc = -shZ
""")

# H形鋼の断面（原点＝芯）. W: フランジが X に沿う（寝かせると縦のフランジ＝腹起し）、S: フランジが Y に沿う（寝かせると上下のフランジ＝切梁・
# 立てると +X を向くフランジ＝中間杭）
W_PTS = ["-sB / 2, -sH / 2", "sB / 2, -sH / 2", "sB / 2, -sH / 2 + sT2", "sT1 / 2, -sH / 2 + sT2", "sT1 / 2, sH / 2 - sT2",
         "sB / 2, sH / 2 - sT2", "sB / 2, sH / 2", "-sB / 2, sH / 2", "-sB / 2, sH / 2 - sT2", "-sT1 / 2, sH / 2 - sT2",
         "-sT1 / 2, -sH / 2 + sT2", "-sB / 2, -sH / 2 + sT2"]
S_PTS = ["-sH / 2, -sB / 2", "-sH / 2 + sT2, -sB / 2", "-sH / 2 + sT2, -sT1 / 2", "sH / 2 - sT2, -sT1 / 2", "sH / 2 - sT2, -sB / 2",
         "sH / 2, -sB / 2", "sH / 2, sB / 2", "sH / 2 - sT2, sB / 2", "sH / 2 - sT2, sT1 / 2", "-sH / 2 + sT2, sT1 / 2",
         "-sH / 2 + sT2, sB / 2", "-sH / 2, sB / 2"]


def _prism(indent: str, height: str, pts) -> str:
    body = ",\n".join(f"{indent}\t{p}, 15" for p in pts)
    return f"{indent}prism_ {len(pts)}, {height},\n{body}\n"


def _poly(indent: str, pts) -> str:
    rows = list(pts) + [pts[0]]
    body = ",\n".join(f"{indent}\t{p}, {-1 if i == len(rows) - 1 else 1}" for i, p in enumerate(rows))
    return f"{indent}fill fiS\n{indent}poly2_b {len(rows)}, 7, pO, pO,\n{body}\n"


SCRIPT_2D_T = """﻿! 山留め支保工 2D（GL の下なので部材は隠れ線。中間杭は GL で切った断面を塗り）。詳細（1/100 まで）は芯・継手・ジャッキと伸縮の範囲
! （二点鎖線）・交叉部直ボルト・ブラケット、簡略（1/250 より小さい縮尺）は外形だけ（scripts/gdl_draft.py）
@HEAD@
define style "shT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "shT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
! 重なり: 30 杭の断面（塗り）、40 隠れ線と細部、50 文字
if shKind = 4 then
	drawindex 30
	pen pO
	if drLv < 3 then
@P2D@	else
		rect2 -sH / 2, -sB / 2, sH / 2, sB / 2
	endif
	if drLv = 1 then
		drawindex 40
		pen pT
		line_type ltH
		rect2 sH / 2, -0.0375, sH / 2 + bkL, 0.0375
		line_type ltC
		line2 pkR, -0.6, pkR, 0.6
		line_type ltS
	endif
	drawindex 50
	pen penEquip
	if drLv < 3 then text2 0, sB / 2 + 0.1 + dT / 2, shInfo
	hotspot2 0, 0
	end
endif
hw = sH / 2
if shKind = 1 then hw = sB / 2
drawindex 40
pen pO
line_type ltH
line2 0, -hw, shL, -hw
line2 0, hw, shL, hw
line2 0, -hw, 0, hw
line2 shL, -hw, shL, hw
pen pT
if drLv = 1 then
	line_type ltC
	line2 -0.2, 0, shL + 0.2, 0
	line_type ltH
	x = 0
	for i = 1 to nSg
		if i > 1 then line2 x, -hw, x, hw
		if sgk[i] = 3 then
			rect2 x, -jkW / 2, x + sgv[i], jkW / 2
			line2 x, -jkW / 2, x + sgv[i], jkW / 2
			line2 x, jkW / 2, x + sgv[i], -jkW / 2
			line_type ltZ
			rect2 x + sgv[i] / 2 - 0.3, -jkW / 2 - 0.02, x + sgv[i] / 2 + 0.3, jkW / 2 + 0.02
			line_type ltH
		endif
		x = x + sgv[i]
	next i
	for k = 1 to nXc
		for sx = -1 to 1 step 2
			for sy = -1 to 1 step 2
				circle2 xcv[k] + sx * xbO, sy * xbO, 0.011
			next sy
		next sx
	next k
	for k = 1 to nBr
		rect2 brv[k] - 0.075, -hw, brv[k] + 0.075, hw
	next k
	if shKind = 3 then
		hb = hpA / 2 * 0.7071
		line2 hb, -hpS * hb, -hb, hpS * hb
		line2 shL - hb, -hpS * hb, shL + hb, hpS * hb
	endif
endif
line_type ltS
drawindex 50
pen penEquip
if drLv < 3 then text2 shL / 2, hw + 0.1 + dT / 2, shInfo
if drLv = 1 then text2 shL / 2, -hw - 0.1 - dT / 2, shName
hotspot2 0, 0
hotspot2 shL, 0
"""

SCRIPT_2D = (SCRIPT_2D_T.replace("@HEAD@", gdl_draft.head().rstrip("\n")).replace("@P2D@", _poly("\t\t", S_PTS)))

SCRIPT_3D_T = """﻿! 山留め支保工 3D（リース材 30HA・35HA・40HA の主材と端板、継手のカバープレート、補助ピース、キリンジャッキとジャッキカバー、交差部の
! アングルピースと交叉部直ボルト、中間杭の切梁受けブラケットと締付用 U ボルト。寸法は src/ashiba/shiho.py の出典）
define material "sh_main" 2, 0.72, 0.16, 0.12
define material "sh_aux" 2, 0.85, 0.45, 0.15
define material "sh_plate" 2, 0.52, 0.12, 0.10
define material "sh_jack" 2, 0.20, 0.38, 0.72
define material "sh_steel" 2, 0.48, 0.30, 0.22
define material "sh_bolt" 2, 0.78, 0.78, 0.74
resol 12
if shKind = 4 then
	! ---- 中間杭（フランジが +X を向く H形鋼）・段ごとの切梁受けブラケット・締付用 U ボルト ----
	material "sh_steel"
	add 0, 0, -shBot
@P3D@	del 1
	dg = sqr(bkL * bkL + bkH * bkH)
	for k = 1 to nPk
		zb = -pkv[k]
		material "sh_steel"
		add sH / 2, -0.0375, zb - 0.009
		block bkL, 0.075, 0.009
		del 1
		add sH / 2, -0.0045, zb - 0.075
		block bkL, 0.009, 0.066
		del 1
		add sH / 2, -0.0375, zb - bkH
		block 0.009, 0.075, bkH
		del 1
		add sH / 2, -0.0045, zb - bkH
		roty -atn(bkH / bkL)
		block dg, 0.009, 0.06
		del 2
		material "sh_bolt"
		for sd = -1 to 1 step 2
			add pkR + sd * ubW / 2, 0, zb - 0.04
			cylind ubH + 0.04, 0.011
			del 1
		next sd
		add pkR - ubW / 2, 0, zb + ubH
		roty 90
		cylind ubW, 0.011
		del 2
	next k
	end
endif
if nSg = 0 then
	material "sh_main"
	add 0, 0, zc
	roty 90
	if shKind = 1 then
@S3DL@	else
@W3DL@	endif
	del 2
endif
x = 0
for i = 1 to nSg
	L = sgv[i]
	if sgk[i] = 3 then
		! ---- キリンジャッキ（端板 2枚・ねじ・ナット）とジャッキカバー（両側） ----
		material "sh_jack"
		add x, -jkW / 2, zc - jkW / 2
		block 0.028, jkW, jkW
		addx L - 0.028
		block 0.028, jkW, jkW
		del 2
		add x + 0.028, 0, zc
		roty 90
		cylind L - 0.056, 0.07
		del 2
		add x + L / 2 - 0.04, 0, zc
		roty 90
		cylind 0.08, 0.11
		del 2
		material "sh_steel"
		for sd = -1 to 1 step 2
			add x + L / 2 - jcL / 2, sd * (jkW / 2 + 0.026) - 0.006, zc - 0.1
			block jcL, 0.012, 0.2
			del 1
		next sd
	endif
	if sgk[i] < 3 then
		! ---- 主材・補助ピース（H形鋼）と主材の端板 ----
		if sgk[i] = 1 then
			material "sh_main"
		else
			material "sh_aux"
		endif
		add x, 0, zc
		roty 90
		if shKind = 1 then
@S3D@		else
@W3D@		endif
		del 2
		if sgk[i] = 1 then
			material "sh_plate"
			if shKind = 1 then
				add x, -sB / 2 - 0.005, zc - sH / 2 - 0.005
				block endT, sB + 0.01, sH + 0.01
				addx L - endT
				block endT, sB + 0.01, sH + 0.01
				del 2
			else
				add x, -sH / 2 - 0.005, zc - sB / 2 - 0.005
				block endT, sH + 0.01, sB + 0.01
				addx L - endT
				block endT, sH + 0.01, sB + 0.01
				del 2
			endif
		endif
		! 前の主材・補助ピースとの継手に両フランジのカバープレート
		if i > 1 then
			if sgk[i - 1] < 3 then
				material "sh_plate"
				if shKind = 1 then
					add x - cvL / 2, -sB / 2, zc + sH / 2
					block cvL, sB, cvT
					addz -sH - cvT
					block cvL, sB, cvT
					del 2
				else
					add x - cvL / 2, sH / 2, zc - sB / 2
					block cvL, cvT, sB
					addy -sH - cvT
					block cvL, cvT, sB
					del 2
				endif
			endif
		endif
	endif
	x = x + L
next i
if shKind = 1 then
	! ---- 交差部（上段の切梁）: 上のフランジにアングル2本（切梁に直角）・下段の下のフランジの下にアングル2本・交叉部直ボルト4本 ----
	for k = 1 to nXc
		xq = xcv[k]
		zt = zc + sH / 2
		zb = zc - sH / 2 - xchv[k]
		material "sh_steel"
		for sd = -1 to 1 step 2
			add xq + sd * xbO - 0.0375, -xaL / 2, zt
			block 0.075, xaL, 0.009
			addx 0.033
			block 0.009, xaL, 0.075
			del 2
			add xq - xaL / 2, sd * xbO - 0.0375, zb - 0.009
			block xaL, 0.075, 0.009
			addy 0.033
			addz -0.066
			block xaL, 0.009, 0.075
			del 3
		next sd
		material "sh_bolt"
		for sx = -1 to 1 step 2
			for sy = -1 to 1 step 2
				add xq + sx * xbO, sy * xbO, zb - 0.06
				cylind zt - zb + 0.12, 0.011
				del 1
			next sy
		next sx
	next k
endif
if shKind = 2 then
	! ---- 腹起しのブラケット（下のフランジの下に受けの板と縦のリブ） ----
	material "sh_steel"
	for k = 1 to nBr
		add brv[k] - 0.075, -sH / 2, zc - sB / 2 - 0.016
		block 0.15, sH, 0.016
		del 1
		add brv[k] - 0.006, -sH / 2, zc - sB / 2 - 0.2
		block 0.012, sH * 0.6, 0.184
		del 1
	next k
endif
if shKind = 3 then
	! ---- 火打受ピース（両端。底は腹起し・切梁の面に沿い 45°、当たり面は火打ちに直角。幅 260） ----
	material "sh_steel"
	hb = hpA / 2 * 0.7071
	for sd = 0 to 1
		add sd * shL, 0, zc - 0.13
		if sd = 1 then mul -1, 1, 1
		prism_ 4, 0.26,
			hb, -hpS * hb, 15,
			0.5, -hpS * sH / 2, 15,
			0.5, hpS * sH / 2, 15,
			-hb, hpS * hb, 15
		if sd = 1 then del 1
		del 1
	next sd
endif
end
"""

SCRIPT_3D = (SCRIPT_3D_T.replace("@P3D@", _prism("\t", "shBot - shZ", S_PTS))
             .replace("@S3D@", _prism("\t\t\t", "L", S_PTS)).replace("@W3D@", _prism("\t\t\t", "L", W_PTS))
             .replace("@S3DL@", _prism("\t\t", "shL", S_PTS)).replace("@W3DL@", _prism("\t\t", "shL", W_PTS)))


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
    print(f"ashiba_shiho: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
