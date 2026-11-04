"""部品 ashiba_hstage（昇降機の荷取りステージ。乗り込む所1か所に1部品）の HSF を書き出す.

利用者の指定（2026-10-28）「ブラケットも詳細にして　ステージは高さの調整があるので別オブジェクトにして」。荷取りステージは
スラブの高さに合わせて上下に調整する（荷取用金具・ブラケットはクランプで留めるので足場のコマに縛られない）ので、
昇降機の部品から分けて、乗り込む所ごとに1部品で置く。部品の設定の「床の高さ」（zSt）を変えれば、そのステージだけ
上下する（次の配置でもその高さを残す。attachments.hoist_stage_placements）。

取付け（stMode）:
  0＝外付け: 乗り込み口の両端の建地（内外）に荷取用金具（クランプ＋フランジ管）、梁枠（トラス）2本、ころばし、足場板
     （スギコ アルバロングスパンEV荷取用金具の設置手順）
  1＝足場の幅の中: 両横の足場の端の建地（躯体側の列）からクランプ式の内側ブラケット（腕は溝形・方杖・建地に留める
     クランプ2つ・先端の止めとホゾ・板止め）、荷台の側の縁に敷板、その奥に足場板
フロアーゲート（アコーディオン式）はステージの荷台側の縁に立てる。

原点＝足場の外側建地の列の上の昇降機の中心（昇降機の部品と同じ）。+X＝面に沿う向き、+Y＝躯体側。faceAng で面の向き。
  python3 scripts/gen_hstage_gdl.py     # gdl/hsf/ashiba_hstage を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gdl_step  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_hstage"
MAIN_GUID = "E3C8CB0B-FA2E-4CB9-BC62-0881BF83982D"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param(*gdl_step.PARAM),
        _param("Angle", "faceAng", "面の向き（度。+X＝面に沿う向き、+Y＝躯体側）", 0),
        _param("Length", "zH", "足場の立つ面の高さ（階の高さから。配置が入れる）", 0),
        _param("Length", "zSt", "ステージの床の高さ（足場の立つ面から。上下に調整できる。次の配置でも残す）", 3),
        _param("String", "landName", "乗り込む所（フロア名か作業層）", "2FL"),
        _param("Integer", "stMode", "取付け（0＝外付け: 荷取用金具＋梁枠、1＝足場の幅の中: ブラケット＋敷板）", 0),
        _param("Length", "stA", "ステージの始点（昇降機の中心から面に沿って。乗り込み口の端の建地）", -2.7435),
        _param("Length", "stB", "ステージの終点（同上）", 2.7435),
        _param("Length", "rowSp", "足場の内外の建地の間隔", 0.914),
        _param("Length", "yF", "ステージの床先（荷台の側の縁。外側建地の列から +Y＝躯体側）", -0.07),
        _param("Length", "railX", "1本構のガイドレールを避ける幅の半分（0＝無し）", 0),
        _param("Boolean", "showGate", "フロアーゲートを描く", 1),
        _param("Boolean", "showText", "平面に乗り込む所の名前を書く", 1),
        "\t\t<Material Name=\"matSt\">\n\t\t\t<Description><![CDATA[\"金物の材質（0＝亜鉛めっきの色）\"]]></Description>\n"
        "\t\t\t<Value>0</Value>\n\t\t</Material>\n",
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


SCRIPT_1D = """﻿! 荷取りステージ: 床の幅（外付けは外側建地の列から内側の建地の手前まで、足場の幅の中は敷板 240＋足場板 240）
if stMode = 1 then
	yB = yF + 0.48
else
	yB = rowSp - 0.10
endif
"""

SCRIPT_2D = """﻿! 荷取りステージ 2D（平面）: 床の外形・板の継ぎ目・ゲートの線・乗り込む所の名前
define style "hsTx" "ＭＳ Ｐゴシック", texSiz, 5, 0
pE = penEquip
if pE < 1 then pE = 1
pen pE
rot2 faceAng
line_type 1
rect2 stA, yF, stB, yB
nL = max(1, int((stB - stA) / 4.0 + 0.99))
for k = 1 to nL - 1
	line2 stA + k * (stB - stA) / nL, yF, stA + k * (stB - stA) / nL, yB
next k
if stMode = 1 then line2 stA, yF + 0.24, stB, yF + 0.24
if showGate then
	line2 stA, yF + 0.05, stB, yF + 0.05
	line2 stA, yF + 0.07, stB, yF + 0.07
endif
if showText then
	style "hsTx"
	text2 (stA + stB) / 2, yB + 0.15, "荷取りステージ " + landName
endif
"""

SCRIPT_3D = """﻿! ============================================================
! 昇降機の荷取りステージ 3D（乗り込む所1か所）。利用者の指定 2026-10-28: ブラケットも詳細にして／ステージは高さの
! 調整があるので別オブジェクトにして。床先は荷台の縁の手前 30（規定 40mm 以内）
! ============================================================
resol 10
define material "hstage_zinc" 2, 0.72, 0.74, 0.76
define material "hstage_wood" 2, 0.74, 0.56, 0.36
define material "hstage_gold" 2, 0.86, 0.68, 0.22
mSt = IND(MATERIAL, "hstage_zinc")
if matSt > 0 then mSt = matSt
mWd = IND(MATERIAL, "hstage_wood")
mAu = IND(MATERIAL, "hstage_gold")
add 0, 0, zH + zSt
rotz faceAng
rP = 0.0243
if stMode = 1 then
	! ---- 足場の幅の中: 両横の足場の端の建地（躯体側の列 y＝rowSp）からクランプ式の内側ブラケット ----
	brW = yB - rowSp
	brD = 0.45
	for se = 0 to 1
		xS = stA + se * (stB - stA)
		sx = 1 - 2 * se
		! 建地に留めるクランプ（腕の高さと方杖の下）: 建地を巻く2つ割りの金物とボルト
		for cz = 0 to 1
			zc = -0.09 - cz * brD
			material mAu
			add xS, rowSp, zc - 0.035
			cylind 0.07, rP + 0.008
			del 1
			add xS - 0.012, rowSp + rP, zc - 0.03
			block 0.024, 0.035, 0.06
			del 1
			for bo = 0 to 1
				add xS - 0.03 + bo * 0.06, rowSp + rP + 0.02, zc - 0.02 + bo * 0.04
				rotx -90
				cylind 0.04, 0.006
				del 2
			next bo
		next cz
		material mSt
		! 背の縦材（2つのクランプをつなぐ角形 40）
		add xS - 0.02, rowSp + rP + 0.035, -0.09 - brD
		block 0.04, 0.04, brD
		del 1
		! 腕（溝形 75×40: ウェブと上下のフランジ。足場板・敷板はこの上に載る）
		add xS - 0.02, rowSp + rP + 0.035, -0.08
		block 0.004, brW - rP - 0.035, 0.075
		del 1
		add xS - 0.02, rowSp + rP + 0.035, -0.008
		block 0.04, brW - rP - 0.035, 0.008
		del 1
		add xS - 0.02, rowSp + rP + 0.035, -0.08
		block 0.04, brW - rP - 0.035, 0.008
		del 1
		! 方杖（φ27.2。下のクランプから腕の先の手前へ。両端に取付けの平鋼）
		bLy = brW - rP - 0.12
		add xS, rowSp + rP + 0.075, -0.09 - brD + 0.02
		rotx -atn(bLy / (brD - 0.07))
		cylind sqr(bLy ^ 2 + (brD - 0.07) ^ 2), 0.0136
		del 2
		add xS - 0.025, rowSp + rP + 0.06, -0.09 - brD
		block 0.05, 0.03, 0.04
		del 1
		add xS - 0.025, yB - 0.10, -0.12
		block 0.05, 0.04, 0.04
		del 1
		! 先端の止め（腕の先の立ち上がり）と、手すりを受けるホゾ（φ36.4）
		add xS - 0.02, yB - 0.006, -0.08
		block 0.04, 0.006, 0.13
		del 1
		add xS, yB - 0.03, 0.05
		cylind 0.10, 0.0182
		del 1
		! 板止め（建地側の端。板が建地の側へずれないように）
		add xS - 0.02, rowSp + rP + 0.035, 0
		block 0.04, 0.006, 0.05
		del 1
	next se
	! 敷板（荷台の側の縁。幅 240・厚 50。上にフロアーゲートが立つ）
	material mWd
	add stA + 0.005, yF, 0
	block stB - stA - 0.01, 0.24, 0.05
	del 1
	! 足場板（幅 240・厚 40・4m まで）
	bxA = stA + 0.03
	bxB = stB - 0.03
	byA = yF + 0.24
	byB = yB
	bzT = 0.04
	gosub "boards"
else
	! ---- 外付け: 荷取用金具（建地の内外）＋梁枠2本＋ころばし＋足場板 ----
	zS = -0.025
	yF0 = -0.206
	if railX > 0.01 or yF > -0.23 then yF0 = 0.206
	for sy = 0 to 1
		yS = yF0 + sy * (rowSp - 0.206 - yF0)
		for se = 0 to 1
			xS = stA + se * (stB - stA)
			! 荷取用金具: 建地を巻くクランプ（金色）と、梁枠を受けるフランジ管（長さ 200）
			material mAu
			add xS, sy * rowSp, zS - 0.12
			cylind 0.07, rP + 0.008
			del 1
			material mSt
			add xS - 0.03, min(sy * rowSp, yS), zS - 0.10
			block 0.06, 0.206, 0.04
			del 1
			add xS, yS, zS - 0.20
			cylind 0.20, 0.03
			del 1
			add xS - 0.06, yS - 0.06, zS - 0.012
			block 0.12, 0.12, 0.012
			del 1
		next se
		! 梁枠（トラス。上弦材・下弦材・束・斜材）
		material mSt
		add stA, yS - 0.025, zS - 0.05
		block stB - stA, 0.05, 0.05
		del 1
		add stA, yS - 0.025, zS - 0.40
		block stB - stA, 0.05, 0.05
		del 1
		nT = max(2, int((stB - stA) / 0.6 + 0.5))
		wT = (stB - stA) / nT
		tAng = atn(wT / 0.35)
		for k = 0 to nT - 1
			if k - 2 * int(k / 2) = 0 then
				add stA + k * wT, yS, zS - 0.375
				roty tAng
			else
				add stA + (k + 1) * wT, yS, zS - 0.375
				roty -tAng
			endif
			cylind sqr(wT ^ 2 + 0.35 ^ 2) - 0.05, 0.017
			del 2
		next k
	next sy
	! ころばし（梁枠に直交。床先から内側の梁枠まで）
	nK = max(2, int((stB - stA) / 0.9 + 0.5))
	for k = 0 to nK
		add stA + 0.05 + k * (stB - stA - 0.10) / nK, yF + 0.05, zS + 0.024
		rotx -90
		cylind rowSp - 0.206 + 0.05 - yF - 0.05, 0.024
		del 2
	next k
	! 足場板（1本構はガイドレールを避けて左右に分ける）
	bzT = 0.06
	byA = yF
	byB = yB
	if railX > 0.01 then
		bxA = stA + 0.03
		bxB = -railX
		gosub "boards"
		bxA = railX
		bxB = stB - 0.03
		gosub "boards"
	else
		bxA = stA + 0.03
		bxB = stB - 0.03
		gosub "boards"
	endif
endif
! ---- フロアーゲート（アコーディオン式。ステージの荷台側の縁に立てる） ----
if showGate then
	yG = yF + 0.06
	zg0 = 0.18
	hG = 1.06
	material mSt
	nV = max(1, int((stB - stA) / 2.0 + 0.5))
	for se = 0 to nV
		xv = stA + se * (stB - stA) / nV
		add xv, yG, 0.10
		cylind 1.17, 0.02
		del 1
	next se
	nJ = max(2, int((stB - stA) / 0.27 + 0.5))
	wJ = (stB - stA) / nJ
	hJ = hG / 2
	jA = atn(wJ / hJ)
	jL = sqr(wJ ^ 2 + hJ ^ 2)
	for k = 0 to nJ - 1
		for rr = 0 to 1
			add stA + k * wJ, yG, zg0 + rr * hJ
			roty jA
			cylind jL, 0.008
			del 2
			add stA + (k + 1) * wJ, yG, zg0 + rr * hJ
			roty -jA
			cylind jL, 0.008
			del 2
		next rr
	next k
	material mAu
	add stB - 0.10, yG - 0.05, 0.82
	block 0.08, 0.06, 0.12
	del 1
endif
end

! ==== 足場板（幅 240・厚 40・長さ 4m まで。面に沿って並べ、継ぎは 10 あける）: bxA〜bxB × byA〜byB、上端 bzT ====
"boards":
	material mWd
	nB = max(1, int((byB - byA) / 0.24 + 0.99))
	wB = (byB - byA) / nB
	nL = max(1, int((bxB - bxA) / 4.0 + 0.99))
	lB = (bxB - bxA) / nL
	for jb = 0 to nB - 1
		for kb = 0 to nL - 1
			add bxA + kb * lB + 0.005, byA + jb * wB + 0.005, bzT - 0.04
			block lB - 0.01, wB - 0.01, 0.04
			del 1
		next kb
	next jb
return
"""


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "2d.gdl").write_text(SCRIPT_2D, encoding="utf-8")
    (OUT / "scripts" / "3d.gdl").write_text(gdl_step.wrap(SCRIPT_3D), encoding="utf-8")
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
    print(f"ashiba_hstage: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
