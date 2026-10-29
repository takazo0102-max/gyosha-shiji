"""部品 ashiba_hoist（昇降機。工事用エレベーター・ロングスパン・荷揚げ機）の HSF を機種表から書き出す.

利用者の指定（2026-10-27）: 昇降機の機種表にする・フロアーゲートを描いて数える・機種ごとの形を3Dで描く・昇降機は
別オブジェクトで配置できるように。部品の設定で機種（hoModel）を選ぶと、data/hoist_models.csv の荷台・マスト・
壁つなぎ間隔で平面と3Dを描く。機種の寸法表は CSV からこのスクリプトで 1d.gdl に書き出す（手で直さない）。

原点＝足場の外側建地の列の上の、昇降機の中心。+X＝面に沿う向き、+Y＝躯体側（荷台は −Y へ出る）。faceAng で面の向き。
  python3 scripts/gen_hoist_gdl.py     # gdl/hsf/ashiba_hoist を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.hoist_models import FLOOR_GATES, load_hoist_models  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_hoist"
KIND_NO = {"ロングスパン": 1, "工事用エレベーター": 2, "荷揚げ機": 3}
FULL_ROOF = ("KRD", "NSE")     # 片方の端の搭乗席だけ囲いとヘッドガード（KRD800/950 の図「ヘッドガード 1910」「搭乗席（2人）」・コシハラの写真）
MAIN_GUID = "6B0E2F41-7C3A-4E58-9A1D-3F2B5C8E7A10"


def _param(kind: str, name: str, desc: str, value, fix: bool = False) -> str:
    v = f"<![CDATA[\"{value}\"]]>" if kind == "String" else str(value)
    return (f"\t\t<{kind} Name=\"{name}\">\n\t\t\t<Description><![CDATA[\"{desc}\"]]></Description>\n"
            + ("\t\t\t<Fix/>\n" if fix else "") + f"\t\t\t<Value>{v}</Value>\n\t\t</{kind}>\n")


def paramlist(first: str) -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Angle", "faceAng", "面の向き（度。+X＝面に沿う向き、+Y＝躯体側）", 0),
        _param("String", "hoModel", "機種（data/hoist_models.csv）", first),
        _param("Length", "zH", "足場の立つ面の高さ（階の高さから。配置が入れる。高さはすべてここから）", 0),
        _param("Length", "hoReach", "到達高さ（マストの頂部の目安。配置で足場の天端を入れる）", 10),
        _param("Length", "gapOut", "足場の外側建地の列から荷台までのあき", 0.1),
        _param("Length", "rowSp", "足場の内外の建地の間隔（配置が入れる。荷取りステージの内側の梁枠の位置）", 0.9),
        _param("Boolean", "hoInside", "足場の幅の中に据える（914。昇降路の足場を抜いた中。外す＝外付け）", 0),
        _param("String", "landLevels", "乗り込む所の番号（カンマ区切り「2,5」。ロングスパンの昇降路は建物のフロアの番号＝下から1,2,…、ほかは足場の作業層。空は全部）", ""),
        _param("String", "landList", "乗り込む作業床の高さ m（配置が入れる。フロアーゲートを描く）", ""),
        _param("String", "tieList", "マスト控えを取る足場の建地（中心から面に沿って m、カンマ区切り。配置が入れる。空はマストの正面）", ""),
        _param("Length", "gateA", "乗り込み口の始点（中心から面に沿って。配置が足場の手すりを外したスパンの端を入れる）", 0),
        _param("Length", "gateB", "乗り込み口の終点（同上。gateA と同じなら荷台の長さで描く）", 0),
        _param("Boolean", "showGate", "乗り込み口のフロアーゲート（機種に無ければ開閉式手すり）を描く", 1),
        _param("Boolean", "stObj", "荷取りステージとフロアーゲートは別の部品（ashiba_hstage）が描く（配置が入れる）", 0),
        _param("Boolean", "showTie", "マストの壁つなぎを描く", 1),
        _param("Boolean", "showFence", "地上の昇降路の囲い（高さ 1.8m・荷台から 0.3 離す）を描く", 1),
        _param("Boolean", "showGuard", "ロングスパンの昇降路の前養生（地上の囲いの上から到達高さまで、単管の枠とメッシュシート）を描く", 1),
        _param("Length", "sideSpan", "外付けの前養生の両横の足場1スパンの奥行（足場の幅。0＝置かない。配置が入れる）", 0),
        _param("Length", "sbL0", "左の横の足場の始め（昇降機の中心から。昇降路の隣のスパン）", -4.6),
        _param("Length", "sbL1", "左の横の足場の終わり", -2.7),
        _param("Length", "sbR0", "右の横の足場の始め", 2.7),
        _param("Length", "sbR1", "右の横の足場の終わり", 4.6),
        _param("Length", "sideLvP", "両横の足場の層の高さ", 1.8),
        "\t\t<Material Name=\"matCage\">\n\t\t\t<Description><![CDATA[\"荷台・マストの材質\"]]></Description>\n"
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


def master(models) -> str:
    lines = [
        "! 昇降機（工事用エレベーター・ロングスパン・荷揚げ機）. 機種の寸法表は scripts/gen_hoist_gdl.py が",
        "! data/hoist_models.csv から書き出す（手で直さない）",
        "cageL = 4.6",
        "cageD = 1.3",
        "postSp = 0",
        "nMast = 1",
        "gateOpen = 0",
        "tieE = 3.6",
        "loadKg = 0",
        "hoName = hoModel",
        "! 種類（1＝ロングスパン・2＝工事用エレベーター・3＝荷揚げ機）と端の囲い（1＝両端の駆動部を金網で囲い頭上覆い（両屋根）・",
        "! 2＝片方の端だけ搭乗席を金網で囲いヘッドガード（コシハラ KRD・NSE。実物の写真: 中央と他方の端は手すりだけ））",
        "hoKind = 1",
        "roofMode = 1",
        "! 荷台の内のりの高さ（三成研機の仕様表）。あれば荷台全体を囲う形（全高のジャバラ扉・外側の金網・屋根枠・三角格子のポスト）",
        "cageH = 0",
    ]
    for m in models.values():
        gate = FLOOR_GATES.get(m.gate)
        lines.append(f'if hoModel = "{m.model_id}" then')
        lines.append(f"\tcageL = {m.cage_len_mm / 1000:.4f}")
        lines.append(f"\tcageD = {m.cage_depth_mm / 1000:.4f}")
        lines.append(f"\tpostSp = {m.post_spacing_mm / 1000:.4f}")
        lines.append(f"\tnMast = {m.masts}")
        lines.append(f"\tgateOpen = {(gate['opening_mm'] / 1000.0) if gate else 0:.4f}")
        lines.append(f"\ttieE = {m.tie_every_mm / 1000:.4f}")
        lines.append(f"\tloadKg = {m.load_kg:.0f}")
        lines.append(f'\thoName = "{m.name}"')
        lines.append(f"\thoKind = {KIND_NO.get(m.kind, 1)}")
        lines.append(f"\troofMode = {2 if m.model_id.startswith(FULL_ROOF) else 1}")
        if m.cage_h_mm > 0:
            lines.append(f"\tcageH = {m.cage_h_mm / 1000:.4f}")
        lines.append("endif")
    lines += [
        "if tieE < 1 then tieE = 3.6",
        "! 乗り込む作業床の高さ（m）",
        "dim landH[40]",
        "nLand = 0",
        "rest = landList",
        "while strlen(rest) > 0 and nLand < 40 do",
        "\tpc = strstr(rest, \",\")",
        "\tif pc > 0 then",
        "\t\titem = strsub(rest, 1, pc - 1)",
        "\t\trest = strsub(rest, pc + 1, strlen(rest) - pc)",
        "\telse",
        "\t\titem = rest",
        "\t\trest = \"\"",
        "\tendif",
        "\tk = split(item, \"%n\", v)",
        "\tif k > 0 then",
        "\t\tnLand = nLand + 1",
        "\t\tlandH[nLand] = v",
        "\tendif",
        "endwhile",
        "! マスト控えを取る足場の建地（中心から m）",
        "dim tieX[8]",
        "nTX = 0",
        "rest = tieList",
        "while strlen(rest) > 0 and nTX < 8 do",
        "\tpc = strstr(rest, \",\")",
        "\tif pc > 0 then",
        "\t\titem = strsub(rest, 1, pc - 1)",
        "\t\trest = strsub(rest, pc + 1, strlen(rest) - pc)",
        "\telse",
        "\t\titem = rest",
        "\t\trest = \"\"",
        "\tendif",
        "\tk = split(item, \"%n\", v)",
        "\tif k > 0 then",
        "\t\tnTX = nTX + 1",
        "\t\ttieX[nTX] = v",
        "\tendif",
        "endwhile",
        "! マストの位置と太さ（ロングスパンは荷台の両端のラック付きポスト 150 角、工事用エレベーターは荷台の外側の格子マスト",
        "! 450 角、荷揚げ機は荷台の外側のガイドレール 120 角）",
        "yC0 = -gapOut",
        "yC1 = -gapOut - cageD",
        "mastW = 0.15",
        "if cageH > 0 then mastW = 0.20",
        "if hoKind = 2 and nMast = 1 then mastW = 0.45",
        "! ロングスパンの1本構（三成研機 DECK・WO-7）: はしご形のガイドレールが足場と荷台の間に立ち、荷台はその外へ出る",
        "if hoKind = 1 and nMast = 1 then",
        "\tmastW = 0.30",
        "\tyC0 = -gapOut - 0.25",
        "\tyC1 = yC0 - cageD",
        "endif",
        "if hoKind = 3 then mastW = 0.12",
        "dim mx[2]",
        "dim my[2]",
        "if nMast = 2 then",
        "\t! ポストは荷台の端の外に立つ（芯々が荷台の長さと同じ機種もポストの半分＋50 は外へ）",
        "\tmx[2] = max(postSp / 2, cageL / 2 + mastW / 2 + 0.05)",
        "\t! 三成研機は図面のガイドレール芯どおり（低床型はレールが荷台の端の内側に入る）",
        "\tif cageH > 0 then mx[2] = postSp / 2",
        "\tmx[1] = -mx[2]",
        "\tmy[1] = (yC0 + yC1) / 2",
        "\tmy[2] = (yC0 + yC1) / 2",
        "else",
        "\tmx[1] = 0",
        "\tmy[1] = yC1 - mastW / 2 - 0.05",
        "\tif hoKind = 1 then my[1] = -gapOut - 0.125",
        "endif",
        "! フロアーゲートの幅（荷台の長さとゲートの有効開口の小さい方）",
        "gW = cageL",
        "if gateOpen > 0.01 then gW = min(cageL, gateOpen)",
        "! 地上の昇降路の囲い（荷台から 0.3 離す。マストの外まで）",
        "fX = cageL / 2 + 0.3",
        "fY = yC1 - 0.3",
        "for im = 1 to nMast",
        "\tfX = max(fX, abs(mx[im]) + 0.4)",
        "\tfY = min(fY, my[im] - mastW / 2 - 0.3)",
        "next im",
        "! 荷揚げ機は巻上げ機がマストの外側に出るので、囲いもその外まで",
        "if hoKind = 3 then fY = fY - 0.6",
        "! 乗り込み口（足場の手すりを外したスパン）。フロアーゲート・開閉式手すりはこの幅いっぱいに付けて開口を残さない",
        "gA = -gW / 2",
        "gB = gW / 2",
        "if gateB - gateA > 0.1 then",
        "\tgA = gateA",
        "\tgB = gateB",
        "endif",
        "! フロアーゲートの面（外付けは足場の外側建地の列）",
        "yG = -0.05",
        "! 足場の幅の中に据える（利用者の指定 2026-10-28: 中に914幅で入れる）: 荷台を足場の幅の中央へ寄せ、ロングスパンの",
        "! マストは昇降路の両横の足場の端の建地のすぐ内に立てる（枠組間隔の中）。乗り込み口は荷台の躯体側",
        "if hoInside then",
        "\tdyI = rowSp / 2 + cageD / 2 - yC0",
        "\tyC0 = yC0 + dyI",
        "\tyC1 = yC1 + dyI",
        "\tfor im = 1 to nMast",
        "\t\tmy[im] = my[im] + dyI",
        "\tnext im",
        "\tif hoKind = 1 and nMast = 2 then",
        "\t\tmx[1] = gA + mastW / 2 + 0.10",
        "\t\tmx[2] = gB - mastW / 2 - 0.10",
        "\t\tmy[1] = rowSp / 2",
        "\t\tmy[2] = rowSp / 2",
        "\tendif",
        "\tyG = yC0 + 0.03 + 0.05",
        "\tfY = min(yC1, 0) - 0.3",
        "endif",
    ]
    return "﻿" + "\n".join(lines) + "\n"


SCRIPT_2D = """﻿! 昇降機 2D（平面）: マスト・荷台の外形・頭上覆い（×）・フロアーゲート（太線）・機種名
define style "hoTx" "ＭＳ Ｐゴシック", texSiz, 5, 0
pE = penEquip
if pE < 1 then pE = 1
pen pE
rot2 faceAng
! 荷台
rect2 -cageL / 2, yC1, cageL / 2, yC0
if hoKind = 1 then
	! ロングスパン: 両端の駆動部（×）と足場側のジャバラ扉（ジグザグ）
	eU = min(0.80, cageL * 0.16)
	for se = -1 to 1 step 2
		x0 = -cageL / 2
		if se > 0 then x0 = cageL / 2 - eU
		rect2 x0, yC1, x0 + eU, yC0
		line2 x0, yC1, x0 + eU, yC0
		line2 x0, yC0, x0 + eU, yC1
	next se
	xa = -cageL / 2 + eU
	xb = cageL / 2 - eU
	nJ = max(2, int((xb - xa) / 0.32 + 0.5))
	wJ = (xb - xa) / nJ
	for k = 0 to nJ - 1
		line2 xa + k * wJ, yC0, xa + (k + 0.5) * wJ, yC0 - 0.06
		line2 xa + (k + 0.5) * wJ, yC0 - 0.06, xa + (k + 1) * wJ, yC0
	next k
else
	! 工事用エレベーター・荷揚げ機: 荷台に×、工事用エレベーターは足場側の扉（太線）
	line2 -cageL / 2, yC1, cageL / 2, yC0
	line2 -cageL / 2, yC0, cageL / 2, yC1
	if hoKind = 2 then rect2 -cageL / 2 + 0.06, yC0 - 0.05, cageL / 2 - 0.06, yC0 - 0.01
endif
! マスト（工事用エレベーターは格子マスト: 外形と内側の枠と×）
for im = 1 to nMast
	hw = mastW / 2
	rect2 mx[im] - hw, my[im] - hw, mx[im] + hw, my[im] + hw
	line2 mx[im] - hw, my[im] - hw, mx[im] + hw, my[im] + hw
	if hoKind = 2 and nMast = 1 then
		rect2 mx[im] - hw + 0.03, my[im] - hw + 0.03, mx[im] + hw - 0.03, my[im] + hw - 0.03
		line2 mx[im] - hw, my[im] + hw, mx[im] + hw, my[im] - hw
	endif
next im
! フロアーゲート（機種に無ければ開閉式手すり）。足場の外側建地の列の外、乗り込み口の幅いっぱい
if showGate and nLand > 0 and stObj = 0 then
	rect2 gA, -0.06, gB, -0.02
endif
! 地上の昇降路の囲い（破線。足場側を除く3方）
if showFence then
	line_type "Dashed"
	if hoInside = 0 then line2 -fX, yC0, -fX, fY
	line2 -fX, fY, fX, fY
	if hoInside = 0 then line2 fX, fY, fX, yC0
	line_type 1
endif
! 外付けのロングスパンの前養生（利用者の指定 2026-10-29: 妻側は足場1スパン、正面に補強）: 両横の足場1スパン（支柱の
! 小円と外形）、前養生の面（正面の太線と両横の足場の外面）
if showGuard and hoKind = 1 and hoInside = 0 and sideSpan > 0 then
	! 外付けのロングスパンの前養生（利用者の指定 2026-10-29: ロングスパンの横はこういう向き）: 昇降路の隣のスパンの前の
	! 足場1スパン（外形・前の建地）と前養生の面
	yF = -sideSpan
	for sb = 0 to 1
		bx0 = sbL0
		bx1 = sbL1
		if sb = 1 then
			bx0 = sbR0
			bx1 = sbR1
		endif
		rect2 bx0, yF, bx1, 0
		line2 bx0, yF, bx1, 0
		circle2 bx0, yF, 0.024
		circle2 bx1, yF, 0.024
	next sb
	pen penEquip
	line2 sbL0, yF - 0.20, sbR1, yF - 0.20
	line2 sbL0, yF - 0.21, sbR1, yF - 0.21
	line2 sbL0 - 0.03, yF, sbL0 - 0.03, 0
	line2 sbR1 + 0.03, yF, sbR1 + 0.03, 0
endif
hotspot2 0, 0
hotspot2 -cageL / 2, yC1
hotspot2 cageL / 2, yC1
set style "hoTx"
tx = hoName
if loadKg > 0 then tx = tx + "（" + str(loadKg, 4, 0) + "kg）"
add2 0, yC1 - 0.45
aTx = SYMB_ROTANGLE + faceAng
aTx = aTx - 360 * int(aTx / 360)
if aTx < 0 then aTx = aTx + 360
if aTx > 90.001 and aTx < 270.001 then rot2 180
text2 0, 0, tx
del top
"""

SCRIPT_3D = """﻿! 昇降機 3D（機種ごと。建機サービスの図面の形）: ロングスパン＝両端のラック付きポスト・桁の付いた長い荷台・足場側のジャバラ扉・
! 両端の駆動部（駆動装置・ガイドローラ・金網・頭上覆い）。工事用エレベーター＝格子マスト・金網で囲った搬器・扉・屋根の上の
! 駆動装置。荷揚げ機＝ガイドレール・昇降フレームの荷台・地上の巻上げ機とワイヤ。共通: マストの壁つなぎ・各階のフロアーゲート・
! 渡し板・地上の昇降路の囲い
resol 8
define material "hoist_steel" 2, 0.62, 0.64, 0.67
define material "hoist_mach" 2, 0.93, 0.72, 0.10
define material "hoist_deck" 2, 0.38, 0.40, 0.43
define material "hoist_mesh" 0, 0.55, 0.58, 0.60, 0.6, 0.6, 0.1, 0.75, 5, 0, 1, 1, 1, 0, 0, 0, 0
define material "hoist_wood" 2, 0.74, 0.56, 0.36
define material "hoist_guard" 0, 0.16, 0.55, 0.26, 0.6, 0.6, 0.1, 0.55, 5, 0, 1, 1, 1, 0, 0, 0, 0
mSt = IND(MATERIAL, "hoist_steel")
if matCage > 0 then mSt = matCage
mMc = IND(MATERIAL, "hoist_mach")
mDk = IND(MATERIAL, "hoist_deck")
mMs = IND(MATERIAL, "hoist_mesh")
mWd = IND(MATERIAL, "hoist_wood")
mGd = IND(MATERIAL, "hoist_guard")
add 0, 0, zH
rotz faceAng
mastH = max(hoReach + 1.5, 3)
zF = 0.30
xL = -cageL / 2
xR = cageL / 2

! ---- マスト ----
for im = 1 to nMast
	material mSt
	! 基礎（コンクリート台）と台板
	add mx[im] - mastW / 2 - 0.30, my[im] - mastW / 2 - 0.30, -0.15
	block mastW + 0.60, mastW + 0.60, 0.15
	del 1
	add mx[im] - mastW / 2 - 0.15, my[im] - mastW / 2 - 0.15, 0
	block mastW + 0.30, mastW + 0.30, 0.02
	del 1
	sd = 1
	if mx[im] > 0.001 then sd = -1
	if hoKind = 2 and nMast = 1 then
		gosub "latticeMast"
	else
		gosub "postMast"
	endif
	! マストの壁つなぎ（足場の外側建地の列まで）。到達高さ（足場の天端）まで tieE ごと。数量（platforms: 到達高さ÷間隔）と同じ本数。
	! 控えの先はいちばん近い足場の建地（tieList。壁つなぎの一覧と同じ建地）。無ければマストの正面
	if showTie then
		material mSt
		txm = mx[im]
		for it = 1 to nTX
			if it = 1 or abs(tieX[it] - mx[im]) < abs(txm - mx[im]) then txm = tieX[it]
		next it
		tdx = txm - mx[im]
		tdy = -(my[im] + mastW / 2)
		tLen = max(0.05, sqr(tdx ^ 2 + tdy ^ 2))
		if abs(tdx) < 0.0001 then
			tAng = 90
		else
			tAng = atn(tdy / tdx)
			if tdx < 0 then tAng = tAng + 180
		endif
		if hoKind = 1 and nMast = 2 and hoInside then
			! 足場の幅の中に据えたとき: マストは昇降路の横の足場の端の建地のすぐ内。足場の内外の列の外に単管を横引き2段
			! （端の建地からマストの先まで）、縦の単管2列（内外の列の線）を横引きに留め、マストを縦の単管の間に渡した
			! 金具で固定する（利用者の図: 内外の列の間にマストの取付け材）
			sg = 1
			if txm < mx[im] then sg = -1
			xA = txm + sg * 0.05
			xB = mx[im] - sg * (mastW / 2 + 0.08)
			for rw = 0 to 1
				yr = -0.06 + rw * (rowSp + 0.12)
				add mx[im], yr + (1 - 2 * rw) * 0.049, 0.10
				cylind mastH - 0.10, 0.0243
				del 1
			next rw
			zt = tieE
			while zt < hoReach + 0.001 do
				for t2 = 0 to 1
					zh = zt - 0.25 + t2 * 0.50
					for rw = 0 to 1
						yr = -0.06 + rw * (rowSp + 0.12)
						add min(xA, xB), yr, zh
						roty 90
						cylind abs(xB - xA), 0.0243
						del 2
						add txm - 0.04, yr - 0.04, zh - 0.04
						block 0.08, 0.08, 0.08
						del 1
						add mx[im] - 0.04, yr - 0.04, zh - 0.04
						block 0.08, 0.08, 0.08
						del 1
					next rw
					add mx[im] - 0.03, -0.01, zh - 0.05
					block 0.06, rowSp + 0.02, 0.10
					del 1
				next t2
				zt = zt + tieE
			endwhile
		endif
		if hoKind = 1 and nMast = 2 and hoInside = 0 then
			! ロングスパンのマストの固定（利用者の指定 2026-10-28: マストは支柱の外に単管を横引き2段、縦の単管を2列配置して
			! マストと固定する）: 昇降路の横の足場の端の建地（内外）に単管を直交クランプで留めて外（マストの側）へ横に引き、
			! 上下2段。その先にマストを挟む縦の単管を2列（マストの前後）立てて横引きに留め、マストを縦の単管に固定する
			sg = 1
			if txm < mx[im] then sg = -1
			xh = txm - sg * 0.06
			xv = xh - sg * 0.049
			yA = rowSp + 0.10
			yB = my[im] - mastW / 2 - 0.15
			for cv = 0 to 1
				yv = my[im] + (2 * cv - 1) * (mastW / 2 + 0.03)
				add xv, yv, 0.10
				cylind mastH - 0.10, 0.0243
				del 1
			next cv
			zt = tieE
			while zt < hoReach + 0.001 do
				for t2 = 0 to 1
					zh = zt - 0.25 + t2 * 0.50
					add xh, yA, zh
					rotx 90
					cylind yA - yB, 0.0243
					del 2
					! 直交クランプ（横引き×足場の内外の建地、横引き×縦の単管2列）
					for cp = 0 to 3
						yc = 0
						if cp = 1 then yc = rowSp
						if cp >= 2 then yc = my[im] + (2 * (cp - 2) - 1) * (mastW / 2 + 0.03)
						add xh - 0.04, yc - 0.04, zh - 0.04
						block 0.08, 0.08, 0.08
						del 1
					next cp
					! マストを縦の単管に固定する金具
					add min(xv, mx[im] + sg * mastW / 2), my[im] - mastW / 2 - 0.03, zh - 0.05
					block abs(xv - mx[im] - sg * mastW / 2) + 0.02, mastW + 0.06, 0.10
					del 1
				next t2
				zt = zt + tieE
			endwhile
		endif
		if not(hoKind = 1 and nMast = 2) then
			zt = tieE
			while zt < hoReach + 0.001 do
				add mx[im], my[im] + mastW / 2, zt
				rotz tAng
				roty 90
				cylind tLen, 0.0243
				del 3
				! 控えの取付金具（マスト側）
				add mx[im] - 0.08, my[im] + mastW / 2, zt - 0.06
				block 0.16, 0.02, 0.12
				del 1
				zt = zt + tieE
			endwhile
		endif
	endif
next im

! ---- 搬器（いちばん下に止めた形） ----
if hoKind = 1 then gosub "longSpanCage"
if hoKind = 2 then gosub "elevatorCage"
if hoKind = 3 then gosub "liftCage"

! ---- フロアーゲート（各階の乗り込み口）: アコーディオン式（ひし形の格子2段・高さ 1250・縦材のキャスター）。片端を足場の
! 建地にクランプで留め、反対の端にリミット付ロック装置（建機サービス Floor-gate の図・イーステック ステージガード C型と同じ形）。
! 機種にフロアーゲートが無ければ開閉式手すり（同じ形で描く）。足場の線の部品は乗り込み口の固定の手すりを外すだけ
if showGate and stObj = 0 then
	for il = 1 to nLand
		zg0 = landH[il] + 0.14
		hG = 1.06
		material mSt
		! 縦材（両端と 2m ごと。下にキャスター）
		nV = max(1, int((gB - gA) / 2.0 + 0.5))
		for se = 0 to nV
			xv = gA + se * (gB - gA) / nV
			add xv, yG, landH[il] + 0.08
			cylind 1.17, 0.02
			del 1
			add xv, yG - 0.03, landH[il] + 0.04
			rotx -90
			cylind 0.06, 0.035
			del 2
		next se
		! ひし形の格子（2段）
		nJ = max(2, int((gB - gA) / 0.27 + 0.5))
		wJ = (gB - gA) / nJ
		hJ = hG / 2
		jA = atn(wJ / hJ)
		jL = sqr(wJ ^ 2 + hJ ^ 2)
		for k = 0 to nJ - 1
			for rr = 0 to 1
				add gA + k * wJ, yG, zg0 + rr * hJ
				roty jA
				cylind jL, 0.008
				del 2
				add gA + (k + 1) * wJ, yG, zg0 + rr * hJ
				roty -jA
				cylind jL, 0.008
				del 2
			next rr
		next k
		! 固定側の縦材を足場の建地に留めるクランプ（上下）
		for zz = 0 to 1
			add gA - 0.06, yG - 0.03, landH[il] + 0.35 + zz * 0.65
			block 0.12, 0.06, 0.08
			del 1
		next zz
		! リミット付ロック装置（扉の端）
		material mMc
		add gB - 0.10, yG - 0.05, landH[il] + 0.80
		block 0.08, 0.06, 0.12
		del 1
		material mSt
	next il
endif
! 荷取り床（各階の乗り込み口）: 搬器の床先とのすき間を 30（規定 40mm 以内）にして、搬器の通り道には入れない（以前は
! 渡し板を搬器の上まで 150 張り出していて、通るたびに当たる形だった）。1本構はガイドレールを避けて左右に分ける。
! ロングスパンは荷取りステージ: 乗り込み口の両端の建地（外側・内側）に荷取用金具、そのフランジに梁枠を2本（外側の建地の
! 外 0.206・内側の建地の内 0.206）、梁枠の上にころばし、その上に足場板（スギコ アルバロングスパンEV荷取用金具の設置手順）
gapL = 0.03
for il = 1 to nLand * (1 - stObj)
	if hoInside then
		! 足場の幅の中に据えたとき（利用者の指定 2026-10-28: 900枠の中に入れる時はステージはブラケット出して敷板を引く・
		! ブラケットは両横の足場の端から）: 昇降路の両横の足場の端の建地（躯体側の列）から内側ブラケットを出し、敷板を
		! 引く。床先は荷台の躯体側の縁の手前 30（規定 40mm 以内）
		! 床の組み方（利用者の指定 2026-10-28: 詳細にして 足場板と敷板も）: 荷台の側の縁に敷板（幅 240・厚 50 の板。上に
		! フロアーゲートが立つ）、その奥に足場板（幅 240・厚 40・4m）。ブラケットは腕（溝形）・方杖・建地に留める金具2つ・
		! 先端の止め
		ySt0 = yC0 + gapL
		brW = ySt0 - rowSp + 0.48
		material mSt
		for se = 0 to 1
			xS = gA + se * (gB - gA)
			add xS - 0.025, rowSp, landH[il] - 0.11
			block 0.05, brW, 0.06
			del 1
			add xS - 0.025, rowSp + brW - 0.03, landH[il] - 0.05
			block 0.05, 0.03, 0.08
			del 1
			bA = atn(brW / 0.45)
			add xS, rowSp, landH[il] - 0.56
			rotx -bA
			cylind sqr(brW ^ 2 + 0.45 ^ 2), 0.0243
			del 2
			for cz = 0 to 1
				add xS - 0.045, rowSp - 0.045, landH[il] - 0.13 - cz * 0.45
				block 0.09, 0.09, 0.08
				del 1
			next cz
		next se
		! 敷板（荷台の側の縁）
		material mWd
		add gA + 0.005, ySt0, landH[il] - 0.05
		block gB - gA - 0.01, 0.24, 0.05
		del 1
		! 足場板
		bxA = gA + 0.03
		bxB = gB - 0.03
		byA = ySt0 + 0.24
		byB = ySt0 + 0.48
		bzT = landH[il] - 0.01
		gosub "boards"
	endif
	if hoKind = 1 and hoInside = 0 then
		zS = landH[il] - 0.025
		! 外側の金具は建地の外へ出すのが基本。搬器（1本構はガイドレール）が建地に近く外へ出せなければ内側へ付ける
		yF0 = -0.206
		if nMast = 1 or yC0 + gapL > -0.26 then yF0 = 0.206
		material mSt
		for sy = 0 to 1
			yS = yF0 + sy * (rowSp - 0.206 - yF0)
			for se = 0 to 1
				xS = gA + se * (gB - gA)
				! 荷取用金具（クランプ＋受けのフランジ管）
				add xS - 0.04, min(sy * rowSp, yS), zS - 0.20
				block 0.08, 0.206, 0.20
				del 1
			next se
			! 梁枠（トラス。深さ 0.40: 上弦材・下弦材・斜材）
			add gA, yS - 0.025, zS - 0.05
			block gB - gA, 0.05, 0.05
			del 1
			add gA, yS - 0.025, zS - 0.40
			block gB - gA, 0.05, 0.05
			del 1
			nT = max(2, int((gB - gA) / 0.6 + 0.5))
			wT = (gB - gA) / nT
			tAng = atn(wT / 0.35)
			for k = 0 to nT - 1
				if k - 2 * int(k / 2) = 0 then
					add gA + k * wT, yS, zS - 0.375
					roty tAng
				else
					add gA + (k + 1) * wT, yS, zS - 0.375
					roty -tAng
				endif
				cylind sqr(wT ^ 2 + 0.35 ^ 2) - 0.05, 0.017
				del 2
			next k
		next sy
		! ころばし（梁枠に直交。床先から内側の梁枠まで）
		nK = max(2, int((gB - gA) / 0.9 + 0.5))
		for k = 0 to nK
			add gA + 0.05 + k * (gB - gA - 0.10) / nK, yC0 + gapL + 0.05, zS + 0.024
			rotx -90
			cylind rowSp - 0.206 + 0.05 - yC0 - gapL - 0.05, 0.024
			del 2
		next k
		! ステージの足場板（外側の建地の列から内側の建地の手前まで。本体の床の代わり＝足場の線の部品はこの升目の踏板を
		! 描かない。利用者の指定 2026-10-28）
		bxA = gA + 0.03
		bxB = gB - 0.03
		byA = 0.10
		byB = rowSp - 0.10
		bzT = landH[il] + 0.06
		gosub "boards"
	endif
	for pc = 1 to 2 - 2 * hoInside
		xa2 = -gW / 2
		xb2 = gW / 2
		if hoKind = 1 and nMast = 1 then
			if pc = 1 then xb2 = mx[1] - mastW / 2 - 0.05
			if pc = 2 then xa2 = mx[1] + mastW / 2 + 0.05
		else
			if pc = 2 then xb2 = xa2
		endif
		if xb2 - xa2 > 0.05 then
			bxA = xa2
			bxB = xb2
			byA = yC0 + gapL
			byB = 0.10
			bzT = landH[il] + 0.06
			gosub "boards"
			if hoKind <> 1 then
				! 荷取用の金具（床を受ける腕。足場の外側建地の列から出す）
				material mSt
				for se = 0 to 1
					add xa2 + se * (xb2 - xa2 - 0.06), yC0 + gapL, landH[il] - 0.10
					block 0.06, -yC0 - gapL + 0.10, 0.12
					del 1
				next se
			endif
		endif
	next pc
next il
! 地上の昇降路の囲い（足場側を除く3方。支柱・笠木・中桟・下桟・金網。搬器の下への立入禁止）
if showFence then
	! 足場の幅の中に据えたときは両横が足場なので、外側の1方だけ
	for ip = 1 + hoInside to 3 - hoInside
		if ip = 1 then
			px0 = -fX
			py0 = yC0
			px1 = -fX
			py1 = fY
			fA = -90
		endif
		if ip = 2 then
			px0 = -fX
			py0 = fY
			px1 = fX
			py1 = fY
			fA = 0
		endif
		if ip = 3 then
			px0 = fX
			py0 = fY
			px1 = fX
			py1 = yC0
			fA = 90
		endif
		fLen = sqr((px1 - px0) ^ 2 + (py1 - py0) ^ 2)
		nP = max(1, int(fLen / 1.8 + 0.99))
		material mSt
		for k = 0 to nP
			add px0 + (px1 - px0) * k / nP, py0 + (py1 - py0) * k / nP, 0
			cylind 1.8, 0.0243
			del 1
		next k
		for hr = 1 to 3
			add px0, py0, 0.1 + 0.85 * (hr - 1)
			rotz fA
			roty 90
			cylind fLen, 0.0243
			del 3
		next hr
		material mMs
		add px0, py0, 0.1
		rotz fA
		block fLen, 0.005, 1.7
		del 2
	next ip
endif
! ロングスパンの昇降路の前養生（利用者の現場写真 2026-10-28・reports/ロングスパンEV昇降路の養生.md）: 地上の囲いと同じ
! 平面を、囲いの天端 1.8m から到達高さまで単管の枠とメッシュシートで塞ぐ。横引きは 1.8m ごと、足場の外側の建地から腕を
! 出して受ける。外付けは両横も返す。乗り込み口の階も外面は開けない（荷は躯体側で取る）
if showGuard and hoKind = 1 and hoReach > 1.85 and hoInside = 0 and sideSpan > 0 then
	! 外付け（利用者の指定 2026-10-29: 妻側は足場1スパン、正面に補強、ロングスパンの横はこういう向き）: 昇降路の隣の
	! スパンの前に足場1スパン（長手は外壁に沿い、奥行＝足場の幅。後ろの建地は本体の足場と兼ね、前の建地2本を立てる）。
	! 正面は横の足場の外端まで横引き、昇降路の前に縦の単管2本と段ごとの斜め（＼　／）。単管は重ねない
	gH = hoReach - 1.8
	nR = int(gH / 1.8 - 0.001) + 1
	yF = -sideSpan
	material mSt
	for sb = 0 to 1
		bx0 = sbL0
		bx1 = sbL1
		if sb = 1 then
			bx0 = sbR0
			bx1 = sbR1
		endif
		! 前の建地とジャッキ
		for kx = 0 to 1
			px = bx0 + kx * (bx1 - bx0)
			add px, yF, 0
			cylind hoReach, 0.0243
			del 1
			add px - 0.07, yF - 0.07, 0
			block 0.14, 0.14, 0.01
			del 1
		next kx
		zl = 0.2
		while zl < hoReach + 0.001 do
			! 前の通りの布材と奥行の布材（後ろは本体の足場の建地へ）
			add bx0, yF, zl
			roty 90
			cylind bx1 - bx0, 0.0214
			del 2
			for kx = 0 to 1
				add bx0 + kx * (bx1 - bx0), 0, zl
				rotx 90
				cylind sideSpan, 0.0214
				del 2
			next kx
			if zl > 0.5 then
				material mDk
				add bx0 + 0.02, yF + 0.01, zl + 0.02
				block bx1 - bx0 - 0.04, sideSpan - 0.02, 0.04
				del 1
				material mSt
			endif
			if zl = 0.2 then
				zl = sideLvP
			else
				zl = zl + sideLvP
			endif
		endwhile
		! 前の面の筋かい（各層）
		zl = 0.2
		while zl + sideLvP < hoReach + 0.001 do
			add bx0, yF, zl
			roty 90 - atn(sideLvP / (bx1 - bx0))
			cylind sqr((bx1 - bx0) ^ 2 + sideLvP ^ 2), 0.0214
			del 2
			if zl = 0.2 then
				zl = sideLvP
			else
				zl = zl + sideLvP
			endif
		endwhile
	next sb
	! 正面の横引き（前の建地の外。左の足場の外端から右の足場の外端まで）
	for kr = 0 to nR
		zr = min(1.8 + kr * 1.8, hoReach)
		add sbL0 - 0.15, yF - 0.05, zr
		roty 90
		cylind sbR1 - sbL0 + 0.3, 0.0243
		del 2
	next kr
	! 昇降路の前の縦の単管2本（両側の足場の内側の前の建地の間の 1/3・2/3。横引きの外）と直交クランプ
	oW = sbR0 - sbL1
	for sg = 1 to 2
		xv = sbL1 + oW * sg / 3
		add xv, yF - 0.10, 1.8
		cylind gH, 0.0243
		del 1
		for kr = 0 to nR
			add xv - 0.04, yF - 0.14, min(1.8 + kr * 1.8, hoReach) - 0.04
			block 0.08, 0.08, 0.08
			del 1
		next kr
	next sg
	! 斜めの単管（段ごとに左右2本、両側の足場の内側の前の建地の上の角から内側へ下がる「＼　／」）
	dRun = oW / 3 - 0.15
	for kr = 1 to nR
		zt = min(1.8 + kr * 1.8, hoReach)
		zb = 1.8 + (kr - 1) * 1.8
		dH = zt - zb
		if dH > 0.3 then
			dL = sqr(dRun ^ 2 + dH ^ 2)
			dA = atn(dH / dRun)
			add sbL1, yF - 0.10, zt
			roty 90 + dA
			cylind dL, 0.0243
			del 2
			add sbR0, yF - 0.10, zt
			roty 270 - dA
			cylind dL, 0.0243
			del 2
		endif
	next kr
	! メッシュシート（正面と両横の足場の外の面）
	material mGd
	add sbL0, yF - 0.20, 1.8
	block sbR1 - sbL0, 0.004, gH
	del 1
	add sbL0 - 0.03, yF, 1.8
	block 0.004, sideSpan, gH
	del 1
	add sbR1 + 0.03, yF, 1.8
	block 0.004, sideSpan, gH
	del 1
endif
if showGuard and hoKind = 1 and hoReach > 1.85 and not(hoInside = 0 and sideSpan > 0) then
	gH = hoReach - 1.8
	gY0 = 0.05
	nR = int(gH / 1.8 - 0.001) + 1
	material mSt
	for kr = 0 to nR
		zr = min(1.8 + kr * 1.8, hoReach)
		! 前面の横引き
		add -fX - 0.15, fY, zr
		roty 90
		cylind 2 * fX + 0.3, 0.0243
		del 2
		! 腕（足場の外側の建地から前面へ。外付けは両横の返しの横引きを兼ねる）
		for sg = -1 to 1 step 2
			add sg * fX, gY0, zr
			rotx 90
			cylind gY0 - fY + 0.15, 0.0243
			del 2
		next sg
	next kr
	if hoInside = 0 then
		! 前面の両端の縦の単管（前面の横引きの内側に沿わせ、重ねない）
		for sg = -1 to 1 step 2
			add sg * fX, fY + 0.05, 1.8
			cylind gH, 0.0243
			del 1
		next sg
		! 両横の返しは足場が無いので単管の枠（利用者の指定 2026-10-28: 縦2本、斜めの単管で補強、クランプ。単管が
		! 重ならないように）: 縦の単管2本（奥行の 1/3・2/3、腕の横引きの外に管1本ずらす）、2段ごとに斜めの単管（その外）
		rD = gY0 - fY
		nB = max(1, int(gH / 3.6 + 0.999))
		bH = gH / nB
		dL = sqr(rD ^ 2 + bH ^ 2)
		dA = atn(rD / bH)
		for sg = -1 to 1 step 2
			for kv = 1 to 2
				yv = gY0 - kv * rD / 3
				add sg * (fX + 0.05), yv, 1.8
				cylind gH, 0.0243
				del 1
				for kr = 0 to nR
					add sg * (fX + 0.05) - 0.04, yv - 0.04, min(1.8 + kr * 1.8, hoReach) - 0.04
					block 0.08, 0.08, 0.08
					del 1
				next kr
			next kv
			for kb = 1 to nB
				z0 = 1.8 + (kb - 1) * bH
				add sg * (fX + 0.10), gY0, z0
				if kb mod 2 = 0 then
					add 0, -rD, 0
					rotx -dA
				else
					rotx dA
				endif
				cylind dL, 0.0243
				del 2 + (kb mod 2 = 0)
			next kb
		next sg
	endif
	material mGd
	add -fX, fY - 0.03, 1.8
	block 2 * fX, 0.004, gH
	del 1
	if hoInside = 0 then
		for sg = -1 to 1 step 2
			add sg * fX - 0.002, fY, 1.8
			block 0.004, gY0 - fY, gH
			del 1
		next sg
	endif
endif
del top
end

! ==== ロングスパンのラック付きポスト・荷揚げ機のガイドレール ====
"postMast":
	if hoKind = 1 and nMast = 1 then
		gosub "railMast"
		return
	endif
	if cageH > 0 then
		gosub "trussPost"
		return
	endif
	material mSt
	add mx[im] - mastW / 2, my[im] - mastW / 2, 0.02
	block mastW, mastW, mastH - 0.02
	del 1
	! 継手のフランジ（1.5m ごと）
	zj = 1.5
	while zj < mastH - 0.1 do
		add mx[im] - mastW / 2 - 0.03, my[im] - mastW / 2 - 0.03, zj - 0.006
		block mastW + 0.06, mastW + 0.06, 0.012
		del 1
		zj = zj + 1.5
	endwhile
	if hoKind = 1 or (hoKind = 2 and im = 1) then
		! ラック（荷台の側の面。歯は 0.1 ごと。HCE990GL は片方がラック無しのポスト）
		rx = mx[im] + sd * mastW / 2
		add rx + (sd - 1) / 2 * 0.02, my[im] - 0.03, 0.02
		block 0.02, 0.06, mastH - 0.02
		del 1
		zr = 0.1
		while zr < mastH - 0.05 do
			add rx + sd * 0.02 + (sd - 1) / 2 * 0.015, my[im] - 0.03, zr
			block 0.015, 0.06, 0.03
			del 1
			zr = zr + 0.1
		endwhile
	else
		! 荷揚げ機: 頂部のシーブ（ワイヤの滑車）
		material mMc
		add mx[im] + 0.10, my[im] - 0.15, mastH - 0.20
		rotx -90
		cylind 0.30, 0.15
		del 2
	endif
return

! ==== 工事用エレベーターの格子マスト（450 角・主材4本・1508 ごとの横材と斜材・ラック） ====
"latticeMast":
	material mSt
	hw = mastW / 2 - 0.03
	for cx = -1 to 1 step 2
		for cy = -1 to 1 step 2
			add mx[im] + cx * hw, my[im] + cy * hw, 0.02
			cylind mastH - 0.02, 0.03
			del 1
		next cy
	next cx
	nS = int(mastH / 1.508)
	for is = 0 to nS
		z0 = 0.02 + is * 1.508
		for cy = -1 to 1 step 2
			add mx[im] - hw, my[im] + cy * hw, z0
			roty 90
			cylind 2 * hw, 0.015
			del 2
		next cy
		for cx = -1 to 1 step 2
			add mx[im] + cx * hw, my[im] - hw, z0
			rotx -90
			cylind 2 * hw, 0.015
			del 2
		next cx
		if is < nS then
			dAng = atn(2 * hw / 1.508)
			dLen = sqr((2 * hw) ^ 2 + 1.508 ^ 2)
			for cy = -1 to 1 step 2
				add mx[im] - hw, my[im] + cy * hw, z0
				roty dAng
				cylind dLen, 0.012
				del 2
			next cy
			for cx = -1 to 1 step 2
				add mx[im] + cx * hw, my[im] - hw, z0
				rotx -dAng
				cylind dLen, 0.012
				del 2
			next cx
		endif
	next is
	! ラック（搬器の側の面）
	add mx[im] - 0.03, my[im] + hw + 0.03, 0.02
	block 0.06, 0.02, mastH - 0.02
	del 1
	zr = 0.1
	while zr < mastH - 0.05 do
		add mx[im] - 0.03, my[im] + hw + 0.05, zr
		block 0.06, 0.015, 0.03
		del 1
		zr = zr + 0.1
	endwhile
return

! ==== ロングスパンの搬器: 床（縞鋼板）・両側の桁・横桁・両端の駆動部・足場側のジャバラ扉・外側の手すり ====
"longSpanCage":
	material mDk
	add xL, yC1, zF
	block cageL, cageD, 0.04
	del 1
	! 両側の桁（ワーレントラス。深さ 0.45: 上弦材＝床の縁・下弦材・端の束・斜材）
	material mSt
	tD = 0.45
	nT = max(2, int(cageL / 0.6 + 0.5))
	wT = cageL / nT
	tAng = atn(wT / tD)
	tLen = sqr(wT ^ 2 + tD ^ 2)
	for sy = 0 to 1
		yT = yC1 + sy * (cageD - 0.06)
		add xL, yT, zF - 0.06
		block cageL, 0.06, 0.06
		del 1
		add xL, yT, zF - tD
		block cageL, 0.06, 0.06
		del 1
		for se = 0 to 1
			add xL + se * (cageL - 0.06), yT, zF - tD
			block 0.06, 0.06, tD
			del 1
		next se
		for k = 0 to nT - 1
			if k - 2 * int(k / 2) = 0 then
				add xL + k * wT, yT + 0.03, zF - tD + 0.03
				roty tAng
			else
				add xL + (k + 1) * wT, yT + 0.03, zF - tD + 0.03
				roty -tAng
			endif
			cylind tLen - 0.06, 0.02
			del 2
		next k
	next sy
	nb = max(2, int(cageL / 0.9))
	for ib = 0 to nb
		add xL + (cageL - 0.06) * ib / nb, yC1 + 0.075, zF - 0.12
		block 0.06, cageD - 0.15, 0.12
		del 1
	next ib
	! 端の駆動部の高さ（三成研機は荷台の内のりの高さまで囲う）
	hU = 1.96
	if cageH > 0 then hU = cageH
	eU = min(0.80, cageL * 0.16)
	if nMast = 1 then eU = 0
	if nMast = 1 then
		! 1本構: 床下の駆動装置（ガイドレールの前）とレールを抱くガイドローラ
		material mMc
		add mx[1] - 0.30, my[1] - 0.10, zF - 0.55
		block 0.60, my[1] - 0.10 - yC0 + 0.10, 0.45
		del 1
		add mx[1] - 0.25, yC0 + 0.05, zF - 0.35
		roty 90
		cylind 0.50, 0.13
		del 2
		material mSt
		for zz = 0 to 1
			add mx[1] - 0.20, my[1] - 0.12, zF - 0.50 + zz * (hU + 0.40)
			block 0.40, 0.04, 0.08
			del 1
		next zz
	endif
	for se = -1 to 1 step 2
		if nMast = 1 then goto "noEndUnit"
		x0 = xL
		if se > 0 then x0 = xR - eU
		xo = xL
		if se > 0 then xo = xR
		! 駆動部の枠（4本の柱 2.0・上枠・金網・頭上覆い）。KRD 形は +x の端の搭乗席だけ（他方の端は手すりだけ）
		cab = 1
		if roofMode = 2 and se < 0 then cab = 0
		material mSt
		if cab = 0 then
			for hr = 1 to 2
				add x0, yC1 + 0.03, zF + 0.55 * hr
				roty 90
				cylind eU, 0.0243
				del 2
				add xo, yC1, zF + 0.55 * hr
				rotx -90
				cylind cageD, 0.0243
				del 2
			next hr
			for cy = 0 to 1
				add xo, yC1 + cy * cageD, zF
				cylind 1.10, 0.0243
				del 1
			next cy
		endif
		if cab = 1 then
		for cx = 0 to 1
			for cy = 0 to 1
				add x0 + cx * (eU - 0.05), yC1 + cy * (cageD - 0.05), zF + 0.04
				block 0.05, 0.05, hU
				del 1
			next cy
		next cx
		for cy = 0 to 1
			add x0, yC1 + cy * (cageD - 0.05), zF + hU - 0.01
			block eU, 0.05, 0.05
			del 1
		next cy
		for cx = 0 to 1
			add x0 + cx * (eU - 0.05), yC1, zF + hU - 0.01
			block 0.05, cageD, 0.05
			del 1
		next cx
		! 金網（外側の面と端の面）
		material mMs
		add x0 + 0.05, yC1 + 0.02, zF + 0.10
		block eU - 0.10, 0.005, hU - 0.16
		del 1
		add xo - (se + 1) / 2 * 0.025 + (1 - se) / 2 * 0.02, yC1 + 0.05, zF + 0.10
		block 0.005, cageD - 0.10, hU - 0.16
		del 1
		! 頭上覆い（ヘッドガード。三成研機は荷台全体の屋根枠を別に描く）
		if cageH = 0 then
			material mSt
			add x0 - 0.05, yC1 - 0.05, zF + 2.00
			block eU + 0.10, cageD + 0.10, 0.04
			del 1
		endif
		endif
		! 駆動装置（電動機・減速機。マストの側）
		mxd = xo
		for im2 = 1 to nMast
			if abs(mx[im2] - xo) < abs(mxd - xo) + 0.001 then mxd = mx[im2]
		next im2
		material mMc
		add mxd - se * (mastW / 2 + 0.32), yC1 + 0.15, zF + 0.55
		rotx -90
		cylind 0.45, 0.13
		del 2
		add mxd - se * (mastW / 2 + 0.32) - 0.15, yC1 + 0.60, zF + 0.40
		block 0.30, 0.30, 0.35
		del 1
		! ガイドローラ（マストを挟む。上下2段）
		material mSt
		for zz = 1 to 2
			zg = zF + 0.15
			if zz = 2 then zg = zF + 1.65
			add mxd - mastW / 2 - 0.08, my[1] - mastW / 2 - 0.08, zg
			block mastW + 0.16, 0.04, 0.08
			del 1
			add mxd - mastW / 2 - 0.08, my[1] + mastW / 2 + 0.04, zg
			block mastW + 0.16, 0.04, 0.08
			del 1
			for cx = -1 to 1 step 2
				for cy = -1 to 1 step 2
					add mxd + cx * (mastW / 2 + 0.035), my[1] + cy * (mastW / 2 - 0.03), zg - 0.02
					cylind 0.12, 0.035
					del 1
				next cy
			next cx
			! ローラの腕（マストから駆動部の枠まで）
			ra = min(mxd - se * (mastW / 2 + 0.08), x0 + eU / 2)
			rb = max(mxd - se * (mastW / 2 + 0.08), x0 + eU / 2)
			if rb - ra > 0.01 then
				add ra, my[1] - 0.04, zg
				block rb - ra, 0.08, 0.08
				del 1
			endif
		next zz
"noEndUnit":
	next se
	! 足場側のジャバラ扉（駆動部の間。上下のレール・中の縦桟・菱形の格子）
	material mSt
	xa = xL + eU
	xb = xR - eU
	yJ = yC0 - 0.03
	! ジャバラ扉の高さ（三成研機は荷台の内のりの高さいっぱい・4段）
	hJb = 1.35
	nRr = 3
	if cageH > 0 then
		hJb = cageH - 0.15
		nRr = 4
	endif
	for hr = 0 to 1
		add xa, yJ, zF + 0.10 + hr * hJb
		roty 90
		cylind xb - xa, 0.02
		del 2
	next hr
	nV = max(1, int((xb - xa) / 1.5 + 0.5))
	for k = 0 to nV
		add xa + (xb - xa) * k / nV, yJ, zF + 0.04
		cylind hJb + 0.10, 0.02
		del 1
	next k
	nJ = max(2, int((xb - xa) / 0.32 + 0.5))
	wJ = (xb - xa) / nJ
	hJ = hJb / nRr
	jAng = atn(wJ / hJ)
	jLen = sqr(wJ ^ 2 + hJ ^ 2)
	for k = 0 to nJ - 1
		for rr = 0 to nRr - 1
			add xa + k * wJ, yJ, zF + 0.10 + rr * hJ
			roty jAng
			cylind jLen, 0.007
			del 2
			add xa + (k + 1) * wJ, yJ, zF + 0.10 + rr * hJ
			roty -jAng
			cylind jLen, 0.007
			del 2
		next rr
	next k
	! 外側の手すり（1.10・中桟 0.55・幅木 0.15。駆動部の間）
	yO = yC1 + 0.03
	for hr = 1 to 2
		add xa, yO, zF + 0.55 * hr
		roty 90
		cylind xb - xa, 0.0243
		del 2
	next hr
	for k = 0 to nV
		add xa + (xb - xa) * k / nV, yO, zF + 0.04
		cylind 1.10, 0.0243
		del 1
	next k
	add xa, yC1, zF + 0.04
	block xb - xa, 0.02, 0.15
	del 1
	if cageH > 0 then
		! 三成研機: 外側の金網（全高）・両端の金網（1本構）・屋根枠（両側の縁と 1.0 ごとの横桟）
		material mMs
		add xa, yC1 + 0.01, zF + 0.10
		block xb - xa, 0.005, cageH - 0.10
		del 1
		if nMast = 1 then
			for se = 0 to 1
				add xL + se * (cageL - 0.01), yC1 + 0.05, zF + 0.10
				block 0.005, cageD - 0.10, cageH - 0.10
				del 1
			next se
		endif
		material mSt
		for k = 0 to nV
			add xa + (xb - xa) * k / nV, yC1 + 0.03, zF + 0.04
			cylind cageH, 0.0243
			del 1
		next k
		for sy = 0 to 1
			add xL, yC1 + 0.03 + sy * (cageD - 0.06), zF + cageH + 0.04
			roty 90
			cylind cageL, 0.0243
			del 2
		next sy
		nR = max(2, int(cageL / 1.0 + 0.5))
		for k = 0 to nR
			add xL + cageL * k / nR, yC1, zF + cageH + 0.04
			rotx -90
			cylind cageD, 0.02
			del 2
		next k
	endif
return

! ==== 工事用エレベーターの搬器: 床・四隅の柱・金網の壁（外側・両端）・足場側の扉・屋根・屋根の上の駆動装置 ====
"elevatorCage":
	material mDk
	add xL, yC1, zF
	block cageL, cageD, 0.05
	del 1
	material mSt
	add xL, yC1, zF - 0.18
	block cageL, cageD, 0.18
	del 1
	! 搬器の高さ（三成研機は仕様表の内のりの高さ。ハイサッシは 2.5m）
	hE = 2.20
	if cageH > 0 then hE = cageH + 0.10
	for cx = 0 to 1
		for cy = 0 to 1
			add xL + cx * (cageL - 0.06), yC1 + cy * (cageD - 0.06), zF + 0.05
			block 0.06, 0.06, hE
			del 1
		next cy
	next cx
	! 屋根（天井の救出口つき）
	add xL, yC1, zF + hE + 0.05
	block cageL, cageD, 0.04
	del 1
	material mMs
	add xL + 0.06, yC1 + 0.01, zF + 0.10
	block cageL - 0.12, 0.005, hE - 0.10
	del 1
	for se = 0 to 1
		add xL + se * (cageL - 0.01), yC1 + 0.06, zF + 0.10
		block 0.005, cageD - 0.12, hE - 0.10
		del 1
	next se
	! 足場側の扉（2枚引き戸の枠と金網・取っ手）
	material mSt
	for k = 0 to 2
		add xL + 0.06 + k * (cageL - 0.12) / 2 - 0.02, yC0 - 0.05, zF + 0.05
		block 0.04, 0.04, hE - 0.10
		del 1
	next k
	for hr = 0 to 1
		add xL + 0.06, yC0 - 0.05, zF + 0.05 + hr * (hE - 0.14)
		block cageL - 0.12, 0.04, 0.04
		del 1
	next hr
	material mMs
	add xL + 0.08, yC0 - 0.035, zF + 0.10
	block cageL - 0.16, 0.005, hE - 0.20
	del 1
	material mMc
	add -0.06, yC0 - 0.08, zF + 1.00
	block 0.12, 0.03, 0.20
	del 1
	! 搬器とマストをつなぐ駆動枠（ピニオンでラックをかむ。マスト1本の機種）と屋根の上の駆動装置
	xd = mx[1]
	if nMast = 1 then
		material mSt
		add mx[1] - 0.35, my[1] + mastW / 2, zF - 0.18
		block 0.70, yC1 - my[1] - mastW / 2, 0.10
		del 1
		add mx[1] - 0.35, my[1] + mastW / 2, zF + hE - 0.05
		block 0.70, yC1 - my[1] - mastW / 2, 0.10
		del 1
	else
		! 両端のポストを抱くガイドローラの腕（上下）
		material mSt
		xd = 0
		for im2 = 1 to 2
			ra = min(mx[im2], xL + (im2 - 1) * cageL)
			rb = max(mx[im2], xL + (im2 - 1) * cageL)
			for zz = 0 to 1
				add ra, my[im2] - 0.05, zF + 0.15 + zz * (hE - 0.30)
				block rb - ra, 0.10, 0.10
				del 1
			next zz
		next im2
	endif
	material mMc
	for k = -1 to 1 step 2
		add xd + k * 0.22, yC1 + 0.10, zF + hE + 0.09
		rotx -90
		cylind 0.40, 0.12
		del 2
	next k
	add xd - 0.30, yC1 + 0.50, zF + hE + 0.09
	block 0.60, 0.30, 0.30
	del 1
	! 制御盤（搬器の中）
	add xR - 0.40, yC1 + 0.05, zF + 0.90
	block 0.30, 0.15, 0.50
	del 1
return

! ==== 荷揚げ機の荷台: 昇降フレーム・荷台（床・3方の手すり）・地上の巻上げ機とワイヤ ====
"liftCage":
	material mDk
	add xL, yC1, zF
	block cageL, cageD, 0.04
	del 1
	material mSt
	! 荷台の手すり（外側・両端。足場側は荷の出し入れで開ける）
	for hr = 1 to 2
		add xL, yC1 + 0.02, zF + 0.45 * hr
		roty 90
		cylind cageL, 0.02
		del 2
		for se = 0 to 1
			add xL + se * cageL, yC1, zF + 0.45 * hr
			rotx -90
			cylind cageD, 0.02
			del 2
		next se
	next hr
	for cx = 0 to 1
		for cy = 0 to 1
			add xL + cx * cageL, yC1 + cy * cageD, zF
			cylind 0.92, 0.02
			del 1
		next cy
	next cx
	! 昇降フレーム（ガイドレールを抱く縦枠）
	for k = -1 to 1 step 2
		add mx[1] + k * 0.25 - 0.03, my[1] + mastW / 2, zF - 0.10
		block 0.06, yC1 - my[1] - mastW / 2, 1.30
		del 1
	next k
	add mx[1] - 0.28, my[1] + mastW / 2, zF + 1.14
	block 0.56, 0.06, 0.06
	del 1
	for k = -1 to 1 step 2
		add mx[1] + k * (mastW / 2 + 0.03), my[1], zF
		cylind 1.20, 0.025
		del 1
	next k
	! 巻上げ機（地上。マストの外側）・ドラム・ワイヤ（巻上げ機から頂部のシーブへ上がり、昇降フレームへ下りる）
	material mMc
	add mx[1] - 0.35, my[1] - mastW / 2 - 0.65, 0
	block 0.70, 0.50, 0.50
	del 1
	add mx[1] - 0.30, my[1] - mastW / 2 - 0.15, 0.25
	roty 90
	cylind 0.60, 0.18
	del 2
	material mSt
	add mx[1] + 0.10, my[1] - mastW / 2 - 0.12, 0.40
	cylind mastH - 0.60, 0.006
	del 1
	add mx[1] + 0.10, my[1] + 0.02, zF + 1.20
	cylind mastH - zF - 1.40, 0.006
	del 1
return

! ==== 三成研機 2本構のガイドレール（三角格子のポスト 200 角・主材4本・ジグザグの斜材・ラック） ====
"trussPost":
	material mSt
	hx = 0.07
	hy = 0.09
	for cx = -1 to 1 step 2
		for cy = -1 to 1 step 2
			add mx[im] + cx * hx, my[im] + cy * hy, 0.02
			cylind mastH - 0.02, 0.022
			del 1
		next cy
	next cx
	zp = 0.02
	dz = 0.30
	dA = atn(2 * hx / dz)
	dL = sqr((2 * hx) ^ 2 + dz ^ 2)
	k = 0
	while zp < mastH - dz do
		for cy = -1 to 1 step 2
			if k - 2 * int(k / 2) = 0 then
				add mx[im] - hx, my[im] + cy * hy, zp
				roty dA
			else
				add mx[im] + hx, my[im] + cy * hy, zp
				roty -dA
			endif
			cylind dL, 0.010
			del 2
		next cy
		zp = zp + dz
		k = k + 1
	endwhile
	zj = 0.02
	while zj < mastH do
		for cx = -1 to 1 step 2
			add mx[im] + cx * hx, my[im] - hy, zj
			rotx -90
			cylind 2 * hy, 0.012
			del 2
		next cx
		zj = zj + 1.508
	endwhile
	! ラック（荷台の側）
	add mx[im] + sd * hx - 0.015, my[im] - 0.03, 0.02
	block 0.03, 0.06, mastH - 0.02
	del 1
return

! ==== 三成研機 1本構のガイドレール（はしご形: 両側の溝形鋼・0.3 ごとの横桟・中央のラック） ====
"railMast":
	material mSt
	for cx = -1 to 1 step 2
		add mx[im] + cx * 0.12 - 0.03, my[im] - 0.06, 0.02
		block 0.06, 0.12, mastH - 0.02
		del 1
	next cx
	zr = 0.30
	while zr < mastH do
		add mx[im] - 0.09, my[im], zr
		roty 90
		cylind 0.18, 0.015
		del 2
		zr = zr + 0.30
	endwhile
	add mx[im] - 0.03, my[im] - 0.09, 0.02
	block 0.06, 0.03, mastH - 0.02
	del 1
	zr = 0.1
	while zr < mastH - 0.05 do
		add mx[im] - 0.03, my[im] - 0.105, zr
		block 0.06, 0.015, 0.03
		del 1
		zr = zr + 0.1
	endwhile
return

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
    models = load_hoist_models()
    ids = list(models)
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(ids[0]), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(master(models), encoding="utf-8")
    (OUT / "scripts" / "2d.gdl").write_text(SCRIPT_2D, encoding="utf-8")
    (OUT / "scripts" / "3d.gdl").write_text(SCRIPT_3D, encoding="utf-8")
    # 値の一覧は1行を短く（6機種ごとに改行）。1行が長い（26機種・約430字）と Tapir の Get/SetGDLParametersOfElements が
    # この部品だけ失敗し、機種を書き込めなかった（2026-10-27）
    parts = [f'"{i}"' for i in ids]
    rows = [", ".join(parts[k:k + 6]) for k in range(0, len(parts), 6)]
    (OUT / "scripts" / "vl.gdl").write_text(
        "﻿values \"hoModel\" " + ",\n\t".join(rows) + "\n", encoding="utf-8")
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
    print(f"ashiba_hoist: {len(ids)} 機種を書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
