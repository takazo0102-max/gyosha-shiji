"""部品 ashiba_side（足場の辺。足場の箱を1辺ずつに分けたもの）の HSF を書き出す.

利用者の指定（2026-10-31）「箱は1辺ずつ別々にしてちょ」。足場の箱（ashiba_box）は一周が1つの部品で、辺ごとに厚み（足場の
種類）・段数を変えたり、1辺だけ消してコの字・L字にしたりできなかった。「箱を置く」は四角の4辺をこの部品で別々に置く。

原点＝内側の建地の列の始点。+X＝辺の向き（長さ lenX）、建物は +Y の側（左回りの一周の内側）、足場は −Y の側へ厚み thick の
壁の形で描く。終わりの端のつまみで長さを伸び縮み（定尺の組み合わせに吸着してスパン spanX を書き直す）、辺の中ほどのつまみで
厚み（300＝一側足場・600／900／1200＝幅610／914／1219の本足場。一側の組み方 oneKind＝ブラケット（支柱）・ブラケット（単管）・
単管抱き。単管の2つは灰色）、3D の天端のつまみで作業床の段数、始めの端の上のつまみで
立つ高さ。cornerE＝終わりの出隅の升目もこの辺で描く（左回りの四角では各辺が終わりの角を受け持つ）。
  python3 scripts/gen_side_gdl.py     # gdl/hsf/ashiba_side を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_box_gdl import SCRIPT_VL as BOX_VL  # noqa: E402
from gen_box_gdl import _parse  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_side"
MAIN_GUID = "FFCA7064-7C08-400A-B977-7A2B8B42BA0E"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Length", "lenX", "長さ（内側の建地の列。つまみで引くと定尺の組み合わせに吸着）", 7.316),
        _param("String", "spanX", "スパン（mm、カンマ区切り。始めから）", "1829,1829,1829,1829"),
        _param("String", "szList", "使える定尺（mm、カンマ区切り。大きい順。置くときに系列から入れる）", "1829,1524,1219,914,610"),
        _param("Length", "thick", "厚み（足場の種類: 300＝一側足場・600／900／1200＝幅610／914／1219の本足場。つまみで吸着）", 0.9),
        _param("Integer", "nLev", "作業床の段数（3D の天端のつまみで増減）", 4),
        _param("Length", "lev1", "1段目の作業床の高さ", 1.78),
        _param("Length", "floorH", "作業床の段の間隔", 1.8),
        _param("Length", "topEdit", "最上段の作業床（立つ高さから。3D のつまみ。引くと段数が変わる）", 7.18),
        _param("Length", "zBase", "立つ高さ（足場の立つ面から。セットバックの上の階は下の屋根の天端。3D のつまみ）", 0),
        _param("Boolean", "cornerE", "終わりの出隅の升目もこの辺で描く", 1),
        _param("Integer", "oneKind", "一側の組み方（厚み 300 のとき: 1＝ブラケット（支柱）・2＝ブラケット（単管）・3＝単管抱き）", 1),
        _param("String", "seriesId", "足場の種類（系列の ID。本体にするときに使う）", ""),
        _param("Length", "standoff", "離れ（躯体から内側の建地まで。本体にするときに使う）", 0.3),
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


SCRIPT_1D = ("﻿! 足場の辺: スパンの並びと定尺を読む（m）\n"
             + _parse("spanX", "sx", "nX", "/ 1000") + _parse("szList", "sz", "nSz", "/ 1000") + """if nX = 0 then
	nX = 1
	sx[1] = max(0.6, lenX)
endif
lx = 0
for i = 1 to nX
	lx = lx + sx[i]
next i
nL = max(1, nLev)
deckTop = lev1 + (nL - 1) * floorH
postH = deckTop + 1.0
tk = max(0.3, min(1.2, round_int(thick / 0.3) * 0.3))
oK = oneKind
if oK < 1 or oK > 3 then oK = 1
if tk < 0.45 then
	if oK = 2 then
		kind = "ブラケット足場（単管）"
	else
		if oK = 3 then
			kind = "単管抱き足場"
		else
			kind = "ブラケット足場（支柱）"
		endif
	endif
else
	kind = "本足場 幅" + str(round_int(tk / 0.3) * 300, 1, 0)
endif
ex = 0
if cornerE then ex = tk
""")


def _vl() -> str:
    """箱のパラメータスクリプトから短手（lenY・spanY）を除いたもの（長さの吸着・厚み・段数・立つ高さは同じ決め方）＋一側の組み方の選択肢."""
    a = BOX_VL.index('if GLOB_MODPAR_NAME = "spanY" then')
    b = BOX_VL.index("if zBase < 0 then")
    kinds = ('! 一側の組み方（利用者の指定 2026-10-31: ブラケット足場と単管抱き足場を選べるように）。厚み 300 のときに使う\n'
             'values{2} "oneKind" 1, "ブラケット（支柱）", 2, "ブラケット（単管）", 3, "単管抱き"\n')
    return BOX_VL[:a].replace("足場の箱", "足場の辺").replace("lenX・lenY", "lenX") + kinds + BOX_VL[b:]


SCRIPT_2D = """﻿! 足場の辺 2D（壁の形）: 内側の建地の列（y＝0）から外（−y）へ厚み tk の帯、スパンの区切り・寸法、種類と見出し、つまみ
! （終わりの端＝長さ、中ほど＝厚み）
pE = penEquip
if pE < 1 then pE = 1
pen pE
define style "sdT" "ＭＳ Ｐゴシック", texSiz, 2, 0
define style "sdB" "ＭＳ Ｐゴシック", texSiz, 8, 0
gap = texSiz * GLOB_SCALE / 1000 * 0.6
rect2 0, 0, lx, -tk
xx = 0
for i = 1 to nX + 1
	line2 xx, 0, xx, -tk
	if i <= nX then
		style "sdT"
		text2 xx + sx[i] / 2, -tk - gap, str(sx[i] * 1000, 1, 0)
		xx = xx + sx[i]
	endif
next i
! 終わりの出隅の升目（×）
if cornerE then
	rect2 lx, 0, lx + tk, -tk
	line2 lx, 0, lx + tk, -tk
	line2 lx, -tk, lx + tk, 0
endif
! 向き（始め→終わり）の矢印
line2 lx / 2 - 0.3, -tk / 2, lx / 2 + 0.3, -tk / 2
line2 lx / 2 + 0.3, -tk / 2, lx / 2 + 0.15, -tk / 2 + 0.08
line2 lx / 2 + 0.3, -tk / 2, lx / 2 + 0.15, -tk / 2 - 0.08
style "sdB"
zTx = ""
if zBase > 0.001 then zTx = "・立つ高さ " + str(zBase * 1000, 1, 0)
text2 lx / 2, gap, "足場の辺 " + str(lx * 1000, 1, 0) + "・" + kind + "・作業床 " + str(nL, 1, 0) + "段（最上段 " + str((zBase + deckTop) * 1000, 1, 0) + "）" + zTx
hotspot2 0, 0
hotspot2 lx, 0
hotspot2 0, -tk
hotspot2 lx + ex, -tk
hotspot2 lx + ex, 0
! 伸び縮みのつまみ（終わりの端で長さ、中ほどで厚み）
hotspot2 0, -tk / 2, 101, lenX, 1 + 128
hotspot2 lenX, -tk / 2, 102, lenX, 2
hotspot2 -1, -tk / 2, 103, lenX, 3
hotspot2 lx / 4, 0, 107, thick, 1 + 128
hotspot2 lx / 4, -thick, 108, thick, 2
hotspot2 lx / 4, 1, 109, thick, 3
"""

SCRIPT_3D = """﻿! ============================================================
! 足場の辺 3D（壁の形）: 内側の建地の列から外へ厚み tk・高さ 最上段＋手すりの壁。色は種類（一側足場・幅610・914・1219）、
! 作業床の段の高さに線
! ============================================================
resol 8
! ---- 立つ高さのつまみ（始めの端の外。セットバックの上の階は下の屋根の天端へ上げる） ----
hotspot 0, -tk, 0, 1010, zBase, 1 + 128
hotspot 0, -tk, zBase, 1011, zBase, 2
hotspot 0, -tk, -1, 1012, zBase, 3
add 0, 0, zBase
define material "sd_1" 2, 0.95, 0.62, 0.25
define material "sd_6" 2, 0.45, 0.70, 0.95
define material "sd_9" 2, 0.45, 0.80, 0.45
define material "sd_12" 2, 0.70, 0.55, 0.90
define material "sd_t" 2, 0.62, 0.62, 0.66
if tk < 0.45 then
	if oK > 1 then
		material "sd_t"
	else
		material "sd_1"
	endif
else
	if tk < 0.75 then
		material "sd_6"
	else
		if tk < 1.05 then
			material "sd_9"
		else
			material "sd_12"
		endif
	endif
endif
H = postH
add 0, -tk, 0
block lx + ex, tk, H
del 1
for lv = 1 to nL
	zl = lev1 + (lv - 1) * floorH
	lin_ 0, -tk - 0.003, zl, lx + ex, -tk - 0.003, zl
	lin_ 0, 0.003, zl, lx, 0.003, zl
next lv
! ---- 段数のつまみ（終わりの端の上。引くと段の間隔に丸めて段数が変わる） ----
hotspot lx, -tk, 0, 1000, topEdit, 1 + 128
hotspot lx, -tk, topEdit, 1001, topEdit, 2
hotspot lx, -tk, -1, 1002, topEdit, 3
del 1
end
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(_vl(), encoding="utf-8")
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
    print(f"ashiba_side: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
