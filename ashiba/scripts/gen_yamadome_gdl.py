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
        _param("Integer", "ymKind", "種類（1＝切梁上の足場・2＝山留め上の手すり・3＝外周の腹起し上の足場）", 1),
        _param("Length", "armL", "腹起し上: 腹起ブラケットの腕（山留めの面から根切りの側へ）", 0.9),
        # 角の重なりと切梁との取り合い（利用者の指定 2026-10-31: 角の重なりと切梁との取り合いも直して）
        _param("Length", "railX0", "手すり・幅木の始め（切梁上は床も。始めから）", 0),
        _param("Length", "railX1", "手すり・幅木の終わり（切梁上は床も）", 6),
        _param("String", "railGap", "手すり・幅木を切る所（mm。始め,終わり の組。切梁上の足場の取り合い）", ""),
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
        # 山留め上の手すりのネット（利用者の指定 2026-10-31: 山留め上の手すりはネットいるよ）: ラッセルネット（無結節・目合 15）
        _param("Boolean", "netOn", "山留め上: 手すりにネット（ラッセルネット 目合15）を張る", 1),
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


SCRIPT_1D = ("﻿! 根切りの山留めまわり: ブラケット・手すり柱の位置を読む（m）\n" + _parse_all("brX", "bx", "nB")
             + _parse_all("railGap", "gp", "nG") + """hp = postSp / 2
rx0 = railX0
rx1 = railX1
if rx1 <= rx0 then rx1 = ymL
r = 0.0243
""")

SCRIPT_2D = """﻿! 根切りの山留めまわり 2D
pen penEquip
define style "ymT" "ＭＳ Ｐゴシック", texSiz, 1, 0
style "ymT"
if ymKind = 1 then
	! 切梁上の足場: 床の外形・手すり柱・ブラケット
	rect2 rx0, -deckW / 2, rx1, deckW / 2
	line2 rx0, -hp, rx1, -hp
	line2 rx0, hp, rx1, hp
	for i = 1 to nB
		line2 bx[i], -hp - 0.05, bx[i], hp + 0.05
		circle2 bx[i], -hp, r
		circle2 bx[i], hp, r
	next i
	text2 ymL / 2, hp + 0.25, ymName
endif
if ymKind = 3 then
	! 外周の腹起し上の足場: 山留めの面（y＝0）から根切りの側（−y）へ armL。手すりは根切りの側だけ
	rect2 0, 0, ymL, -armL
	line2 0, -armL + 0.03, ymL, -armL + 0.03
	for i = 1 to nB
		line2 bx[i], 0, bx[i], -armL
		circle2 bx[i], -armL, r
	next i
	text2 ymL / 2, -armL - 0.3, ymName
endif
if ymKind = 2 then
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

SCRIPT_3D = """﻿! 根切りの山留めまわり 3D（規格の寸法: 単管 φ48.6×2.4・φ42.7、直交クランプ 日建 ARC1 の口 幅40・帯4.5、足場板 240×28、
! 鋼製布板 幅500・高さ45、鋼製幅木 H150×1.6、キャッチクランプ（H形鋼のフランジに単管を留める）。利用者の指定 2026-10-31: 詳細度上げて
! クランプや規格の寸法で）
define material "ym_steel" 2, 0.62, 0.64, 0.68
define material "ym_deck" 2, 0.55, 0.57, 0.6
define material "ym_board" 2, 0.80, 0.66, 0.42
define material "ym_toe" 2, 0.56, 0.58, 0.62
define material "ym_clamp" 2, 0.85, 0.70, 0.30
define material "ym_net" 0, 0.10, 0.45, 0.22, 0.6, 0.6, 0.1, 0.55, 5, 0, 1, 1, 1, 0, 0, 0, 0
rN = 12
resol rN
clW = 0.040
clT = 0.0045
r42 = 0.02135
r60 = 0.03025
material "ym_steel"
if ymKind = 1 then
	! ---- 切梁上の足場（西南機材 切梁ブラケット＋嵩上金具 W900＋伸縮手摺柱） ----
	for i = 1 to nB
		x = bx[i]
		! 切梁ブラケット: フランジの両端を下から掴む爪（片方はスライドしてボルトで締める）と、両端の受け口まで渡る腕（□60×40）
		for sd = -1 to 1 step 2
			add x - 0.03, sd * (flgW / 2 + 0.006) - 0.006, -0.032
			block 0.06, 0.012, 0.072
			del 1
			add x - 0.03, sd * (flgW / 2 - 0.02) - 0.02 + sd * 0.02, -0.032
			block 0.06, 0.04, 0.010
			del 1
		next sd
		add x, flgW / 2 + 0.012, 0.0
		rotx -90
		cylind 0.06, 0.006
		del 2
		add x - 0.03, -hp - 0.03, 0.04
		block 0.06, postSp + 0.06, 0.04
		del 1
		for sd = -1 to 1 step 2
			! 受け口 φ42.7・嵩上金具の脚 φ48.6（受け口にかぶせる）
			add x, sd * hp, 0.08
			cylind 0.12, r42
			cylind deckZ + 0.12 - 0.08, r
			del 1
			! 伸縮手摺柱: 外管 φ48.6（嵩上の上 450）、内管 φ42.7（手すりの上まで）、留めピン
			add x, sd * hp, deckZ + 0.04
			cylind 0.45, r
			addz 0.45
			cylind railH - 0.45 + 0.04, r42
			del 2
			add x - 0.03, sd * hp, deckZ + 0.43
			roty 90
			cylind 0.06, 0.004
			del 2
			! 手すり・中桟の直交クランプ（柱の外側に管）
			for hh = 1 to 2
				zr = railH
				if hh = 2 then zr = midH
				add x, sd * hp, deckZ + zr
				if sd < 0 then mul 1, -1, 1
				clDy = -0.0486
				gosub "orth"
				if sd < 0 then del 1
				del 1
			next hh
			! 幅木クランプ
			material "ym_clamp"
			add x - 0.02, sd * (hp - 0.035) - 0.008, deckZ + toeH - 0.04
			block 0.04, 0.016, 0.05
			del 1
			material "ym_steel"
		next sd
		! 嵩上金具の床受け（φ42.7）
		add x, -hp, deckZ - 0.045 - r42
		rotx -90
		cylind postSp, r42
		del 2
	next i
	! 鋼製布板（幅 deckW・高さ45）: ブラケットの間ごと。両端のつかみ金具を床受けに掛ける
	for i = 0 to nB
		a0 = rx0
		if i > 0 then a0 = max(rx0, bx[i])
		a1 = rx1
		if i < nB then a1 = min(rx1, bx[i + 1])
		if a1 - a0 > 0.1 then
			material "ym_deck"
			add a0 + 0.005, -deckW / 2, deckZ - 0.0016
			block a1 - a0 - 0.01, deckW, 0.0016
			del 1
			for sd = -1 to 1 step 2
				add a0 + 0.005, sd * (deckW / 2 - 0.0016) - 0.0008 - sd * 0.0008, deckZ - 0.045
				block a1 - a0 - 0.01, 0.0016, 0.045
				del 1
			next sd
			material "ym_steel"
		endif
	next i
	! 手すり・中桟（単管 φ48.6。柱の外）と鋼製幅木（両側）
	for sd = -1 to 1 step 2
		for hh = 1 to 2
			zr = railH
			if hh = 2 then zr = midH
			add rx0, sd * (hp + 0.0486), deckZ + zr
			roty 90
			cylind rx1 - rx0, r
			del 2
		next hh
		material "ym_toe"
		add rx0, sd * (hp - 0.03) - 0.0008, deckZ
		block rx1 - rx0, 0.0016, toeH
		add 0, -sd * 0.015 + 0.0008 - 0.0008, toeH - 0.0016
		block rx1 - rx0, 0.015, 0.0016
		del 2
		material "ym_steel"
	next sd
endif
if ymKind = 3 then
	! ---- 外周の腹起し上の足場（腹起ブラケット＋足場板 240×28 を3枚＋単管の手すり柱。山留めの面 y＝0 から −y へ） ----
	for i = 1 to nB
		x = bx[i]
		! 腹起しの上のフランジに掛ける爪（逆 L）と締めボルト
		add x - 0.03, -0.012, -0.10
		block 0.06, 0.012, 0.13
		del 1
		add x - 0.03, -0.012, 0.018
		block 0.06, 0.07, 0.012
		del 1
		add x, -0.05, -0.06
		rotx -90
		cylind 0.06, 0.006
		del 2
		! 腕（φ42.7・スライド）と方杖（φ34）
		add x, -0.012, 0.024
		rotx 90
		cylind armL - 0.012, r42
		del 2
		! 方杖: 腕の途中から腹起しの前のフランジへ斜め下に
		dyB = armL * 0.55
		dzB = 0.25
		add x, -dyB, 0.01
		rotx -(90 + atn(dzB / dyB))
		cylind sqr(dyB ^ 2 + dzB ^ 2), 0.017
		del 2
		! 先のサヤ管 φ60.5（高さ 200）に単管の手すり柱 φ48.6
		add x, -armL, -0.15
		cylind 0.20, r60
		del 1
		add x, -armL, -0.15
		cylind railH + 0.073 + 0.20, r
		del 1
		! 幅木クランプ
		material "ym_clamp"
		add x - 0.02, -armL + 0.04, 0.073 + toeH - 0.04
		block 0.04, 0.016, 0.05
		del 1
		material "ym_steel"
	next i
	! 足場板 240×28 を3枚。長さ 4m 以内で、継ぎはブラケットの上（突き合わせ）。番線で腕に留める
	material "ym_board"
	xs0 = 0
	while xs0 < ymL - 0.01 do
		xe0 = ymL
		if ymL - xs0 > 4.0 then
			xe0 = min(ymL, xs0 + 1.8)
			for i = 1 to nB
				if bx[i] > xs0 + 0.3 and bx[i] <= xs0 + 3.9 then xe0 = bx[i]
			next i
		endif
		for k = 0 to 2
			add xs0 + 0.002, -0.04 - k * 0.27 - 0.24, 0.045
			block xe0 - xs0 - 0.004, 0.24, 0.028
			del 1
		next k
		xs0 = xe0
	endwhile
	material "ym_steel"
	for i = 1 to nB
		for k = 0 to 2
			add bx[i] - 0.002, -0.04 - k * 0.27 - 0.24, 0.0
			block 0.004, 0.24, 0.075
			del 1
		next k
	next i
	! 手すり・中桟・幅木（根切りの側）: rx0〜rx1 から切梁上の足場の取り合い（gp の組）を除いた区間ごと
	sx = rx0
	for g = 1 to nG - 1 step 2
		s0 = sx
		s1 = min(gp[g], rx1)
		if s1 > s0 + 0.05 then gosub "wrail"
		sx = max(sx, gp[g + 1])
	next g
	s0 = sx
	s1 = rx1
	if s1 > s0 + 0.05 then gosub "wrail"
endif
if ymKind = 2 then
	! ---- 山留め上の手すり（親杭の天端に単管の手すり柱をキャッチクランプ2個1組で、手すり・中桟は直交クランプ、
	! ラッセルネットと鋼製幅木は根切りの側） ----
	for i = 1 to nB
		add bx[i], 0.06, -postDn
		cylind postDn + railH + 0.05, r
		del 1
		! キャッチクランプ（H形鋼のフランジを掴む爪＋単管の口）
		for k = 1 to 2
			zc = -0.06
			if k = 2 then zc = -postDn + 0.06
			material "ym_clamp"
			add bx[i] - 0.035, -0.02, zc - 0.03
			block 0.07, 0.03, 0.06
			del 1
			add bx[i] - 0.035, -0.02, zc + 0.03
			block 0.07, 0.06, 0.008
			del 1
			add bx[i], -0.02, zc
			rotx 90
			cylind 0.02, 0.008
			del 2
			add bx[i], 0.06, zc
			roty -90
			jR = r
			gosub "jaw"
			del 2
			material "ym_steel"
		next k
		for hh = 1 to 2
			zr = railH
			if hh = 2 then zr = midH
			add bx[i], 0.06, zr
			mul 1, -1, 1
			clDy = 0.0486
			gosub "orth"
			del 2
		next hh
	next i
	for hh = 1 to 2
		zr = railH
		if hh = 2 then zr = midH
		add 0, 0.06 - 0.0486, zr
		roty 90
		cylind ymL, r
		del 2
	next hh
	material "ym_toe"
	add 0, 0.06 - 0.0486 - r - 0.002, 0
	block ymL, 0.0016, toeH
	del 1
	if netOn then
		! ラッセルネット（無結節・目合 15）: 地盤から手すりの上まで、手すり・中桟・幅木の根切りの側に結束して張る
		material "ym_net"
		add 0, 0.06 - 0.0486 - r - 0.008, 0
		block ymL, 0.003, railH + r
		del 1
		material "ym_steel"
	endif
endif
end

"jaw":
	! クランプの口1つ（日建 ARC1 の形・規格の寸法。管は X 向きで芯が原点、半径 jR。相手の口は −Y 側）
	material "ym_clamp"
	rotx 90
	revolve 4, 180, 63, -clW / 2, jR, 0, clW / 2, jR, 0, clW / 2, jR + clT, 0, -clW / 2, jR + clT, 0
	del 1
	add -clW / 2, -(jR + clT + 0.004), -clW / 2
	block clW, 0.004, clW
	del 1
	add -clW / 2, 0, jR + clT + 0.0035
	roty 90
	cylind clW, 0.0045
	del 2
	rotx -90
	revolve 4, 180, 63, -clW / 2, jR, 0, clW / 2, jR, 0, clW / 2, jR + clT, 0, -clW / 2, jR + clT, 0
	del 1
	add 0, -0.012, -(jR + clT + 0.008)
	rotx -90
	cylind 0.044, 0.005
	addz 0.019
	resol 6
	cylind 0.010, 0.0095
	resol rN
	del 3
	material "ym_steel"
	return

"orth":
	! 直交クランプ（日建 兼用直交クランプ ARC1）: 原点＝柱の芯（Z 向き）、管は +X 向きで芯は y = −clDy
	roty -90
	jR = r
	gosub "jaw"
	del 1
	add 0, -clDy, 0
	rotz 180
	jR = r
	gosub "jaw"
	del 2
	return

"wrail":
	for hh = 1 to 2
		zr = railH
		if hh = 2 then zr = midH
		add s0, -armL - 0.0486, 0.073 + zr
		roty 90
		cylind s1 - s0, r
		del 2
	next hh
	! 区間の中の手すり柱に直交クランプ
	for i = 1 to nB
		if bx[i] >= s0 - 0.001 and bx[i] <= s1 + 0.001 then
			for hh = 1 to 2
				zr = railH
				if hh = 2 then zr = midH
				add bx[i], -armL, 0.073 + zr
				clDy = 0.0486
				gosub "orth"
				del 1
			next hh
		endif
	next i
	material "ym_toe"
	add s0, -armL + 0.03, 0.073
	block s1 - s0, 0.0016, toeH
	del 1
	material "ym_steel"
	return
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
