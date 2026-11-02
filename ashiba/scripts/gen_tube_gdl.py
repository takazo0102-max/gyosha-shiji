"""部品 ashiba_tube（別の足場を単管でつなぐ。支柱から支柱への線1本に1部品）の HSF を書き出す.

GLOOBE の「別の足場と接続する単管」に当たる（2026-11-02 の開発ループ）。割付と判定は src/ashiba/tube_join.py（出典はそちら）、
置くのは scripts/tube_run.py。原点＝始めの足場の支柱の芯（足場の立つ面）、+X＝終わりの支柱へ。高さ zList（mm、カンマ区切り）ごとに
長さ tbLen の単管を両端が同じだけ突き出すように掛け、両端の支柱に直交クランプ。gdOn で各層の上に中桟・手すり、brOn で層の間に
斜めの単管（自在クランプ）
  python3 scripts/gen_tube_gdl.py     # gdl/hsf/ashiba_tube を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_tube"
MAIN_GUID = "3B7E5A19-C2D4-4F81-9A6E-0D58F2B7C341"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Length", "tbL", "支柱の芯から芯まで", 3.0),
        _param("Length", "tbLen", "単管の長さ（規格）", 3.5),
        _param("String", "zList", "つなぐ高さ mm（カンマ区切り。足場の立つ面から）", "1800,3600,5400"),
        _param("Boolean", "gdOn", "各層の上に中桟・手すり（450・950）", 0),
        _param("Boolean", "brOn", "層の間に斜めの補強", 0),
        _param("String", "tbName", "名前（注記）", "つなぎ1"),
        _param("String", "tbNote", "注記", "単管 3.5M×3本"),
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


SCRIPT_1D = ("﻿! 単管のつなぎ: 高さの並び（m）と両端の突き出し\n" + _parse_all("zList", "zz", "nZ")
             + "ov = max(0, (tbLen - tbL) / 2)\nrT = 0.0243\n")

SCRIPT_2D = """﻿! 単管のつなぎ 2D: 単管（突き出しまで）・両端の直交クランプ・注記
pen penEquip
define style "tbT" "ＭＳ Ｐゴシック", texSiz, 5, 0
style "tbT"
line2 -ov, rT, tbL + ov, rT
line2 -ov, -rT, tbL + ov, -rT
for e = 0 to 1
	xe = e * tbL
	rect2 xe - 0.05, -0.07, xe + 0.05, 0.07
	circle2 xe, 0, 0.0243
next e
add2 tbL / 2, 0
rot2 -SYMB_ROTANGLE
text2 0, 0.35, tbName + " " + tbNote
del 2
hotspot2 0, 0
hotspot2 tbL, 0
"""

SCRIPT_3D = """﻿! 単管のつなぎ 3D: 高さごとの単管（中桟・手すり）・直交クランプ、層の間の斜めの単管と自在クランプ
define material "tb_pipe" 2, 0.72, 0.74, 0.76
define material "tb_clamp" 2, 0.35, 0.36, 0.38
resol 8
for i = 1 to nZ
	nR = 1
	if gdOn then nR = 3
	for k = 1 to nR
		zr = zz[i]
		if k = 2 then zr = zz[i] + 0.45
		if k = 3 then zr = zz[i] + 0.95
		material "tb_pipe"
		add -ov, -0.07, zr
		roty 90
		cylind tbLen, rT
		del 2
		material "tb_clamp"
		for e = 0 to 1
			add e * tbL - 0.045, -0.115, zr - 0.04
			block 0.09, 0.09, 0.08
			del 1
		next e
	next k
next i
if brOn and nZ > 1 then
	for i = 1 to nZ - 1
		! 斜めの両端は自在クランプの所（層の 0.1 上から次の層の 0.1 下）
		dz = zz[i + 1] - zz[i] - 0.2
		bl = sqr(tbL ^ 2 + dz ^ 2)
		ab = atn(dz / tbL)
		material "tb_pipe"
		if i mod 2 = 1 then
			add 0, 0.07, zz[i] + 0.1
			roty 90 - ab
		else
			add tbL, 0.07, zz[i] + 0.1
			roty -90 + ab
		endif
		add 0, 0, -ov
		cylind bl + 2 * ov, rT
		del 3
		material "tb_clamp"
		xb = 0
		if i mod 2 = 0 then xb = tbL
		add xb - 0.045, 0.025, zz[i] + 0.06
		block 0.09, 0.09, 0.08
		del 1
		add tbL - xb - 0.045, 0.025, zz[i + 1] - 0.14
		block 0.09, 0.09, 0.08
		del 1
	next i
endif
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text("﻿! 単管のつなぎ: 値の一覧は無い\n", encoding="utf-8")
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
    print(f"ashiba_tube: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
