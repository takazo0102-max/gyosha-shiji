"""部品 ashiba_fence（歩行者通路の柵・バリケード・車両防護柵。1本の線に1部品）の HSF を書き出す.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の6番。割付と判定は src/ashiba/fence.py（出典はそちら）、置くのは
scripts/fence_run.py。原点＝線の始め、座標は文字のパラメータ cX・cY（mm）。種類 fcKind: 1 PPフェンス（1,500×1,214 の板と支柱・
ウエイト）、2 スタンドバリケード C型（1.8m 以内の間に単管の横桟 上下2段）、3 バルカンバリア JW4型（4,115×560×814）、
4 仮設ガードレール GR50（5.0m・H-300 の台・支柱 φ114.3）。区間ごとに規格の1基ずつ描く
  python3 scripts/gen_fence_gdl.py     # gdl/hsf/ashiba_fence を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_fence"
MAIN_GUID = "5B9E2C74-3A61-4D8F-92C0-1E7F6A4B8D23"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "fcKind", "種類（1 PPフェンス・2 スタンドバリケード・3 バルカンバリア・4 仮設ガードレール）", 1),
        _param("String", "cX", "線の X（mm。始めの点から）", "0,20000,20000"),
        _param("String", "cY", "線の Y", "0,0,6000"),
        _param("String", "fcName", "名前（注記）", "柵1"),
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
    out = ["﻿! 柵: 線（mm）を読む・種類ごとの1基の長さ・高さ・奥行"]
    for prm, arr, cnt in (("cX", "qcx", "kC"), ("cY", "qcy", "kCy")):
        out += [f"dim {arr}[]", f"{cnt} = 0", f"rest = {prm}", "while strlen(rest) > 0 do", '\tpc = strstr(rest, ",")',
                "\tif pc > 0 then", "\t\titem = strsub(rest, 1, pc - 1)", "\t\trest = strsub(rest, pc + 1, strlen(rest) - pc)",
                "\telse", "\t\titem = rest", '\t\trest = ""', "\tendif", '\tk = split(item, "%n", v)', "\tif k > 0 then",
                f"\t\t{cnt} = {cnt} + 1", f"\t\t{arr}[{cnt}] = v / 1000", "\tendif", "endwhile"]
    out += ["kC = min(kC, kCy)", "kd = max(1, min(4, fcKind))", "uL = 1.5", "uH = 1.214", "uD = 0.3",
            "if kd = 2 then", "\tuL = 1.8", "\tuH = 0.935", "\tuD = 0.46", "endif",
            "if kd = 3 then", "\tuL = 4.115", "\tuH = 0.814", "\tuD = 0.56", "endif",
            "if kd = 4 then", "\tuL = 5.0", "\tuH = 0.775", "\tuD = 0.3", "endif"]
    return "\n".join(out) + "\n"


SCRIPT_2D = """﻿! 柵 2D: 区間ごとに1基ずつの外形と名前
pen penEquip
define style "fcT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "fcT"
for s = 1 to kC - 1
	dx = qcx[s + 1] - qcx[s]
	dy = qcy[s + 1] - qcy[s]
	sL = sqr(dx * dx + dy * dy)
	sA = 90 * sgn(dy)
	if abs(dx) > 0.000001 then sA = atn(dy / dx)
	if dx < 0 then sA = sA + 180
	if sL > 0.01 then
		nU = max(1, ceil(sL / uL - 0.02))
		stp = uL
		if kd = 2 then stp = sL / nU
		add2 qcx[s], qcy[s]
		rot2 sA
		for u = 1 to nU
			rect2 (u - 1) * stp, -uD / 2, (u - 1) * stp + uL, uD / 2
			if kd = 2 then rect2 (u - 1) * stp - 0.02, -uD / 2, (u - 1) * stp + 0.02, uD / 2
		next u
		if kd = 2 then rect2 sL - 0.02, -uD / 2, sL + 0.02, uD / 2
		del 2
	endif
next s
if kC > 1 then
	add2 (qcx[1] + qcx[2]) / 2, (qcy[1] + qcy[2]) / 2
	rot2 -SYMB_ROTANGLE
	text2 0, 0.6, fcName
	del 2
endif
for i = 1 to kC
	hotspot2 qcx[i], qcy[i]
next i
"""

SCRIPT_3D = """﻿! 柵 3D: 区間ごとに規格の1基ずつ
define material "fc_pp" 2, 0.20, 0.55, 0.30
define material "fc_wt" 2, 0.25, 0.25, 0.27
define material "fc_galv" 2, 0.72, 0.74, 0.76
define material "fc_yel" 2, 0.95, 0.80, 0.10
define material "fc_red" 2, 0.75, 0.15, 0.15
define material "fc_white" 2, 0.92, 0.92, 0.90
resol 8
for s = 1 to kC - 1
	dx = qcx[s + 1] - qcx[s]
	dy = qcy[s + 1] - qcy[s]
	sL = sqr(dx * dx + dy * dy)
	sA = 90 * sgn(dy)
	if abs(dx) > 0.000001 then sA = atn(dy / dx)
	if dx < 0 then sA = sA + 180
	if sL > 0.01 then
		nU = max(1, ceil(sL / uL - 0.02))
		stp = uL
		if kd = 2 then stp = sL / nU
		add qcx[s], qcy[s], 0
		rotz sA
		for u = 1 to nU
			add (u - 1) * stp, 0, 0
			gosub "unit"
			del 1
		next u
		if kd = 2 then
			add sL, 0, 0
			gosub "stand"
			del 1
		endif
		del 2
	endif
next s
end

! 1基（今の座標で +X に長さ uL）
"unit":
	if kd = 1 then
		! PPフェンス: 支柱 φ32×2・板・ウエイト（支柱の下）
		material "fc_wt"
		add -0.15, -0.15, 0
		block 0.3, 0.3, 0.114
		del 1
		material "fc_pp"
		add 0.0, 0, 0.114
		cylind 1.1, 0.016
		del 1
		add 0.052, -0.01, 0.214
		block 1.395, 0.02, 1.0
		del 1
	endif
	if kd = 2 then
		gosub "stand"
		material "fc_galv"
		for r = 1 to 2
			hz = 0.85
			if r = 2 then hz = 0.45
			add -0.1, 0.05, hz
			roty 90
			cylind stp + 0.2, 0.0243
			del 2
		next r
	endif
	if kd = 3 then
		! バルカンバリア: 鋼製の台形の断面を3段に、上に黄色の帯
		material "fc_galv"
		add 0.005, -0.28, 0
		block 4.105, 0.56, 0.25
		del 1
		add 0.005, -0.2, 0.25
		block 4.105, 0.4, 0.3
		del 1
		add 0.005, -0.125, 0.55
		block 4.105, 0.25, 0.264
		del 1
		material "fc_yel"
		add 0.005, -0.126, 0.72
		block 4.105, 0.002, 0.06
		del 1
	endif
	if kd = 4 then
		! 仮設ガードレール: H-300 の台（赤）・支柱 φ114.3 を 2m ごと・ガードレールのビーム
		material "fc_red"
		add 0.005, -0.15, 0
		block 4.99, 0.3, 0.3
		del 1
		material "fc_galv"
		for i = 0 to 2
			add 0.5 + 2 * i, 0, 0.3
			cylind 0.4, 0.057
			del 1
		next i
		material "fc_white"
		add 0.005, -0.15, 0.425
		block 4.99, 0.08, 0.35
		del 1
	endif
return

! スタンドバリケード C型: A 形の脚（幅 460・高さ 935）
"stand":
	material "fc_yel"
	for lg = -1 to 1 step 2
		add 0, lg * 0.23, 0
		rotx lg * 14
		cylind 0.95, 0.016
		del 2
	next lg
	add -0.016, -0.23, 0.2
	block 0.032, 0.46, 0.03
	del 1
return
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(_master(), encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(
        "﻿! 柵: 種類の一覧\nvalues{2} \"fcKind\" 1, \"PPフェンス PP1512G\", 2, \"スタンドバリケード C型 BS020＋単管\", "
        "3, \"バルカンバリア JW4型 BBJW4\", 4, \"仮設ガードレール GR50\"\n", encoding="utf-8")
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
    print(f"ashiba_fence: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
