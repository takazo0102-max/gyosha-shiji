"""部品 ashiba_yamadome（根切りの山留めまわり: 切梁上の足場・山留め上の手すり。1本の切梁・1辺の山留めに1部品）の HSF を書き出す.

利用者の指定（2026-10-31）「https://www.seinankizai.jp/product/b_b/136/ 切張り上の足場を追加して 山留め上の手すり リサーチして追加して」。

ymKind＝1 切梁上の足場（西南機材 切梁ブラケット＋嵩上金具＋伸縮手摺柱）: 切梁（H形鋼 250〜400）の上のフランジに切梁ブラケットを
  brPitch（2m 以内）ごとに挟み、両端の φ42.7 に嵩上金具（W900・φ48.6）を差して床（鋼製布板 deckW）を受け、伸縮手摺柱
  （H875〜1275）で手すり・中桟、幅木クランプで幅木。原点＝切梁の始めの上のフランジの上面の芯、+X＝切梁の向き。
ymKind＝2 山留め上の手すり: 親杭（H形鋼）の天端に単管の手すり柱を pitch ごとにキャッチクランプ（2個1組）で留め、手すり・中桟
  （単管）と幅木。原点＝山留めの始めの天端の芯、+X＝山留めの向き、+Y＝地山の側。
  python3 scripts/gen_yamadome_gdl.py     # gdl/hsf/ashiba_yamadome を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_yamadome"
MAIN_GUID = "5B0E9C47-6A1D-4E2B-9C38-2F7D41A8E613"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "ymKind", "種類（1＝切梁上の足場・2＝山留め上の手すり）", 1),
        _param("Length", "ymL", "長さ（切梁・山留めの向き）", 6),
        _param("Length", "flgW", "切梁の H形鋼のフランジの幅", 0.3),
        _param("String", "brX", "ブラケット・手すり柱の位置（mm。始めから、カンマ区切り）", "150,1950,3750,5550"),
        _param("Length", "postSp", "切梁上: 嵩上金具・手すり柱の間（芯々。W900）", 0.9),
        _param("Length", "deckZ", "切梁上: 床の上端の高さ（フランジの上から。嵩上金具）", 0.3),
        _param("Length", "deckW", "切梁上: 床幅（鋼製布板）", 0.5),
        _param("Length", "railH", "手すりの高さ（床・天端から）", 0.95),
        _param("Length", "midH", "中桟の高さ（床・天端から）", 0.45),
        _param("Length", "toeH", "幅木の高さ", 0.15),
        _param("Length", "postDn", "山留め上: 手すり柱を親杭に留める深さ（天端から下へ）", 0.35),
        _param("String", "ymName", "名前（平面の注記）", "切梁上の足場"),
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


SCRIPT_1D = ("﻿! 根切りの山留めまわり: ブラケット・手すり柱の位置を読む（m）\n" + _parse_all("brX", "bx", "nB") + """hp = postSp / 2
r = 0.0243
""")

SCRIPT_2D = """﻿! 根切りの山留めまわり 2D
pen penEquip
define style "ymT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "ymT"
if ymKind = 1 then
	! 切梁上の足場: 床の外形・手すり柱・ブラケット
	rect2 0, -deckW / 2, ymL, deckW / 2
	line2 0, -hp, ymL, -hp
	line2 0, hp, ymL, hp
	for i = 1 to nB
		line2 bx[i], -hp - 0.05, bx[i], hp + 0.05
		circle2 bx[i], -hp, r
		circle2 bx[i], hp, r
	next i
	text2 ymL / 2, hp + 0.25, ymName
else
	! 山留め上の手すり: 手すりの線と柱
	line2 0, 0.06, ymL, 0.06
	for i = 1 to nB
		circle2 bx[i], 0, r
	next i
	text2 ymL / 2, 0.35, ymName
endif
hotspot2 0, 0
hotspot2 ymL, 0
"""

SCRIPT_3D = """﻿! 根切りの山留めまわり 3D
define material "ym_steel" 2, 0.62, 0.64, 0.68
define material "ym_deck" 2, 0.55, 0.57, 0.6
define material "ym_toe" 2, 0.85, 0.75, 0.2
material "ym_steel"
resol 12
if ymKind = 1 then
	! ---- 切梁上の足場（切梁ブラケット＋嵩上金具＋伸縮手摺柱） ----
	for i = 1 to nB
		x = bx[i]
		! 切梁ブラケット: フランジを両側から挟む受けと、両端の φ42.7 まで渡る腕
		for sd = -1 to 1 step 2
			add x - 0.04, sd * (flgW / 2 + 0.02) - 0.02, -0.03
			block 0.08, 0.04, 0.06
			del 1
		next sd
		add x - 0.03, -hp - 0.03, 0.03
		block 0.06, postSp + 0.06, 0.05
		del 1
		! 嵩上金具の柱（φ48.6）と伸縮手摺柱（φ42.7）。床の下に床受けの横材
		for sd = -1 to 1 step 2
			add x, sd * hp, 0.03
			cylind deckZ + railH - 0.03, r
			del 1
		next sd
		add x, -hp, deckZ - 0.06
		rotx -90
		cylind postSp, 0.0214
		del 2
	next i
	! 床（鋼製布板）
	material "ym_deck"
	add 0, -deckW / 2, deckZ - 0.04
	block ymL, deckW, 0.04
	del 1
	material "ym_steel"
	! 手すり・中桟（両側）
	for sd = -1 to 1 step 2
		for hh = 1 to 2
			zr = railH
			if hh = 2 then zr = midH
			add 0, sd * (hp + 0.05), deckZ + zr
			roty 90
			cylind ymL, r
			del 2
		next hh
		! 幅木（幅木クランプで柱に）
		material "ym_toe"
		add 0, sd * (hp - 0.03) - 0.005, deckZ
		block ymL, 0.01, toeH
		del 1
		material "ym_steel"
	next sd
else
	! ---- 山留め上の手すり（親杭の天端に単管の手すり柱をキャッチクランプで） ----
	for i = 1 to nB
		add bx[i], 0, -postDn
		cylind postDn + railH + 0.05, r
		del 1
		! キャッチクランプ（2個1組）
		for k = 1 to 2
			add bx[i] - 0.04, -0.06, -postDn * k / 3 - 0.02
			block 0.08, 0.12, 0.04
			del 1
		next k
	next i
	for hh = 1 to 2
		zr = railH
		if hh = 2 then zr = midH
		add 0, 0.05, zr
		roty 90
		cylind ymL, r
		del 2
	next hh
	material "ym_toe"
	add 0, 0.03, 0
	block ymL, 0.01, toeH
	del 1
endif
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
    print(f"ashiba_yamadome: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
