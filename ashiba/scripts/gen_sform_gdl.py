"""部品 ashiba_sform（スラブの型枠と支保工: せき板・根太・大引・パイプサポート・水平つなぎ）の HSF を書き出す.

利用者の指定（2026-10-31）「スラブの型枠も進めて しほこうも」。割付と計算は src/ashiba/slab_form.py、置くのは scripts/form_run.py。

原点＝スラブの外形の1点目の下端（スラブの下面）。+X＝大引の向き（u）、+Y＝v。せき板は外形（ringN の1つ目）から穴（2つ目から。
梁・壁・柱）を抜いた形、根太（単管。v の向きの線分 neU・neV0・neV1）、大引（□100×50。u の向きの線分 obV・obU0・obU1）、
パイプサポート（psU・psV。長さ postH）、水平つなぎ（tieZ の高さに、支柱の列ごとに2方向）.
  python3 scripts/gen_sform_gdl.py     # gdl/hsf/ashiba_sform を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_sform"
MAIN_GUID = "4A7C1E93-2B5D-4F68-9E0A-6D3F8B1C5E27"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("String", "polyU", "せき板の形の u（mm。外形のあとに穴を続ける）", "0,4000,4000,0"),
        _param("String", "polyV", "同 v", "0,0,3000,3000"),
        _param("String", "ringN", "形ごとの点の数（1つ目が外形、2つ目からが穴）", "4"),
        _param("String", "neU", "根太の u（mm）", "150,450"),
        _param("String", "neV0", "根太の始めの v", "20,20"),
        _param("String", "neV1", "根太の終わりの v", "2980,2980"),
        _param("String", "obV", "大引の v（mm）", "150,1500"),
        _param("String", "obU0", "大引の始めの u", "50,50"),
        _param("String", "obU1", "大引の終わりの u", "3950,3950"),
        _param("String", "psU", "パイプサポートの u（mm）", "100,1500"),
        _param("String", "psV", "パイプサポートの v", "150,150"),
        _param("Length", "postH", "パイプサポートの長さ（敷き桟木の上から大引の下まで）", 2.6),
        _param("Length", "sillH", "敷き桟木の高さ（45×60 を寝かせる）", 0.045),
        _param("Length", "sillW", "敷き桟木の幅", 0.06),
        _param("String", "slU0", "敷き桟木の始めの u（mm。支柱の列ごと、梁・壁・柱で分ける）", ""),
        _param("String", "slU1", "敷き桟木の終わりの u", ""),
        _param("String", "slV", "敷き桟木の v", ""),
        _param("String", "tieZ", "水平つなぎの高さ（床から mm）", ""),
        _param("Length", "plyT", "せき板の厚さ", 0.012),
        _param("String", "cName", "名前（平面の注記）", "スラブ型枠"),
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


SCRIPT_1D = ("﻿! スラブの型枠と支保工: 位置を読む（m）\n"
             + _parse_all("polyU", "pu", "nPu") + _parse_all("polyV", "pv", "nPv") + _parse_all("ringN", "rn", "nR")
             + _parse_all("neU", "nu", "nN") + _parse_all("neV0", "nv0", "nN0") + _parse_all("neV1", "nv1", "nN1")
             + _parse_all("obV", "ov", "nO") + _parse_all("obU0", "ou0", "nO0") + _parse_all("obU1", "ou1", "nO1")
             + _parse_all("psU", "su", "nP") + _parse_all("psV", "sv", "nP2") + _parse_all("tieZ", "tz", "nZ")
             + "! 配列の名前はパラメータと大文字・小文字だけ違うものにしない（GDL は大文字・小文字を区別しない。slV と slv で部品が読めなくなった）\n"
             + _parse_all("slU0", "sl0", "nL0") + _parse_all("slU1", "sl1", "nL1") + _parse_all("slV", "slw", "nL")
             + """! ringN は点の数（mm でなく数）。_parse_all が 1000 で割るので戻す
for k = 1 to nR
	rn[k] = round_int(rn[k] * 1000)
next k
r = 0.0243
zN = -plyT - r
zO = -plyT - 2 * r
oH = 0.1
oB = 0.05
zF = zO - oH - postH
zS = zF - sillH
"""
             )

SCRIPT_2D = """﻿! スラブの型枠と支保工 2D: せき板の形（外形と穴）、大引（破線）、パイプサポート（○）、名前
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "sfT" "ＭＳ Ｐゴシック", texSiz, 1, 0
i0 = 1
for k = 1 to nR
	for i = 0 to rn[k] - 1
		j = i + 1
		if j >= rn[k] then j = 0
		line2 pu[i0 + i], pv[i0 + i], pu[i0 + j], pv[i0 + j]
	next i
	i0 = i0 + rn[k]
next k
line_type "DASHED"
for i = 1 to nO
	line2 ou0[i], ov[i], ou1[i], ov[i]
next i
line_type 1
for i = 1 to nP
	circle2 su[i], sv[i], 0.03
next i
style "sfT"
text2 pu[1] + 0.3, pv[1] + 0.3, cName + "  " + cNote
"""

SCRIPT_3D = """﻿! ============================================================
! スラブの型枠と支保工 3D（利用者の指定 2026-10-31: スラブの型枠も進めて しほこうも）
! 原点＝スラブの下面。せき板・根太・大引・パイプサポート・水平つなぎ
! ============================================================
resol 10
define material "sf_ply" 2, 0.86, 0.66, 0.38
define material "sf_steel" 2, 0.62, 0.62, 0.66
define material "sf_obiki" 2, 0.45, 0.52, 0.62
define material "sf_ps" 2, 0.42, 0.44, 0.48
define material "sf_wood" 2, 0.74, 0.56, 0.36
! ---- せき板（外形から穴を抜く） ----
material "sf_ply"
i0 = 1
for k = 1 to nR
	for i = 0 to rn[k] - 1
		put pu[i0 + i], pv[i0 + i], 15
	next i
	put pu[i0], pv[i0], -1
	i0 = i0 + rn[k]
next k
add 0, 0, -plyT
prism_ nsp / 3, plyT, get(nsp)
del 1
! ---- 根太（単管・v の向き） ----
material "sf_steel"
for i = 1 to min(nN, min(nN0, nN1))
	add nu[i], nv0[i], zN
	rotx -90
	cylind nv1[i] - nv0[i], r
	del 2
next i
! ---- 大引（□100×50・u の向き） ----
material "sf_obiki"
for i = 1 to min(nO, min(nO0, nO1))
	add ou0[i], ov[i] - oB / 2, zO - oH
	block ou1[i] - ou0[i], oB, oH
	del 1
next i
! ---- パイプサポート ----
for i = 1 to min(nP, nP2)
	add su[i], sv[i], zF
	material "sf_steel"
	add -0.07, -0.07, 0
	block 0.14, 0.14, 0.006
	del 1
	material "sf_ps"
	cylind postH * 0.6, 0.03025
	add 0, 0, postH * 0.6
	material "sf_steel"
	cylind postH * 0.4 - 0.006, 0.0243
	del 1
	add -0.06, -0.06, postH - 0.006
	block 0.12, 0.12, 0.006
	del 1
	del 1
next i
! ---- 敷き桟木（支柱の列ごと。梁・壁・柱で分ける。利用者の指定 2026-10-31: サポートしたはさんぎいる／さんぎの向き揃えて） ----
material "sf_wood"
for i = 1 to min(nL, min(nL0, nL1))
	add sl0[i], slw[i] - sillW / 2, zS
	block sl1[i] - sl0[i], sillW, sillH
	del 1
next i
! ---- 水平つなぎ（2方向。支柱の列ごと） ----
material "sf_steel"
for k = 1 to nZ
	for i = 1 to nO
		add ou0[i], ov[i] + 0.05, zF + tz[k]
		roty 90
		cylind ou1[i] - ou0[i], r
		del 2
	next i
	! v の向き: 支柱の u ごと（同じ u の支柱の v の最小〜最大）
	for i = 1 to min(nP, nP2)
		first = 1
		for j = 1 to i - 1
			if abs(su[j] - su[i]) < 0.01 then first = 0
		next j
		if first then
			vmin = sv[i]
			vmax = sv[i]
			for j = 1 to min(nP, nP2)
				if abs(su[j] - su[i]) < 0.01 then
					vmin = min(vmin, sv[j])
					vmax = max(vmax, sv[j])
				endif
			next j
			if vmax - vmin > 0.1 then
				add su[i] + 0.05, vmin, zF + tz[k] + 2 * r
				rotx -90
				cylind vmax - vmin, r
				del 2
			endif
		endif
	next i
next k
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
    print(f"ashiba_sform: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
