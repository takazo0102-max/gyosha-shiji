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
FULL_ROOF = ("KRD", "NSE")     # 荷台全体にヘッドガード（KRD800/950 の図「ヘッドガード」・搭乗席）
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
        _param("String", "landLevels", "乗り込む作業層の番号（カンマ区切り「2,5」。空は全部の層）", ""),
        _param("String", "landList", "乗り込む作業床の高さ m（配置が入れる。フロアーゲートを描く）", ""),
        _param("String", "tieList", "マスト控えを取る足場の建地（中心から面に沿って m、カンマ区切り。配置が入れる。空はマストの正面）", ""),
        _param("Length", "gateA", "乗り込み口の始点（中心から面に沿って。配置が足場の手すりを外したスパンの端を入れる）", 0),
        _param("Length", "gateB", "乗り込み口の終点（同上。gateA と同じなら荷台の長さで描く）", 0),
        _param("Boolean", "showGate", "乗り込み口のフロアーゲート（機種に無ければ開閉式手すり）を描く", 1),
        _param("Boolean", "showTie", "マストの壁つなぎを描く", 1),
        _param("Boolean", "showFence", "地上の昇降路の囲い（高さ 1.8m・荷台から 0.3 離す）を描く", 1),
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
        "! 種類（1＝ロングスパン・2＝工事用エレベーター・3＝荷揚げ機）と頭上覆い（1＝両端の駆動部だけ・2＝荷台全体のヘッドガード）",
        "hoKind = 1",
        "roofMode = 1",
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
        "if hoKind = 2 then mastW = 0.45",
        "if hoKind = 3 then mastW = 0.12",
        "dim mx[2]",
        "dim my[2]",
        "if nMast = 2 then",
        "\t! ポストは荷台の端の外に立つ（芯々が荷台の長さと同じ機種もポストの半分＋50 は外へ）",
        "\tmx[2] = max(postSp / 2, cageL / 2 + mastW / 2 + 0.05)",
        "\tmx[1] = -mx[2]",
        "\tmy[1] = (yC0 + yC1) / 2",
        "\tmy[2] = (yC0 + yC1) / 2",
        "else",
        "\tmx[1] = 0",
        "\tmy[1] = yC1 - mastW / 2 - 0.05",
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
	if hoKind = 2 then
		rect2 mx[im] - hw + 0.03, my[im] - hw + 0.03, mx[im] + hw - 0.03, my[im] + hw - 0.03
		line2 mx[im] - hw, my[im] + hw, mx[im] + hw, my[im] - hw
	endif
next im
! フロアーゲート（機種に無ければ開閉式手すり）。足場の外側建地の列の外、乗り込み口の幅いっぱい
if showGate and nLand > 0 then
	rect2 gA, -0.06, gB, -0.02
endif
! 地上の昇降路の囲い（破線。足場側を除く3方）
if showFence then
	line_type "Dashed"
	line2 -fX, yC0, -fX, fY
	line2 -fX, fY, fX, fY
	line2 fX, fY, fX, yC0
	line_type 1
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
mSt = IND(MATERIAL, "hoist_steel")
if matCage > 0 then mSt = matCage
mMc = IND(MATERIAL, "hoist_mach")
mDk = IND(MATERIAL, "hoist_deck")
mMs = IND(MATERIAL, "hoist_mesh")
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
	if hoKind = 2 then
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
next im

! ---- 搬器（いちばん下に止めた形） ----
if hoKind = 1 then gosub "longSpanCage"
if hoKind = 2 then gosub "elevatorCage"
if hoKind = 3 then gosub "liftCage"

! ---- フロアーゲート（各階の乗り込み口。単管 φ48.6 の扉: 手すり 0.9・中桟 0.45・両端の縦・中の縦桟）。機種にフロアーゲートが
! 無ければ開閉式手すり（同じ高さの枠）。足場の線の部品は乗り込み口の固定の手すりを外すだけで、ここが防護を描く
material mSt
if showGate then
	for il = 1 to nLand
		for hr = 1 to 2
			add gA, -0.04, landH[il] + 0.45 * hr
			roty 90
			cylind gB - gA, 0.0243
			del 2
		next hr
		nV = max(1, int((gB - gA) / 0.6 + 0.5))
		for se = 0 to nV
			add gA + se * (gB - gA) / nV, -0.04, landH[il]
			if se = 0 or se = nV then
				cylind 1.0, 0.0243
			else
				cylind 0.9, 0.012
			endif
			del 1
		next se
		! リミット付ロック装置（扉の端）
		material mMc
		add gB - 0.10, -0.08, landH[il] + 0.80
		block 0.08, 0.06, 0.12
		del 1
		material mSt
	next il
endif
! 渡し板（各階の乗り込み口で足場の作業床から荷台までのすき間を塞ぐ）
material mDk
for il = 1 to nLand
	add -gW / 2, yC0 - 0.15, landH[il] + 0.02
	block gW, gapOut + 0.15, 0.03
	del 1
next il
! 地上の昇降路の囲い（足場側を除く3方。支柱・笠木・中桟・下桟・金網。搬器の下への立入禁止）
if showFence then
	for ip = 1 to 3
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
del top
end

! ==== ロングスパンのラック付きポスト・荷揚げ機のガイドレール ====
"postMast":
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
	if hoKind = 1 then
		! ラック（荷台の側の面。歯は 0.1 ごと）
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
	material mSt
	for sy = 0 to 1
		add xL, yC1 + sy * (cageD - 0.075), zF - 0.20
		block cageL, 0.075, 0.20
		del 1
	next sy
	nb = max(2, int(cageL / 0.9))
	for ib = 0 to nb
		add xL + (cageL - 0.06) * ib / nb, yC1 + 0.075, zF - 0.12
		block 0.06, cageD - 0.15, 0.12
		del 1
	next ib
	eU = min(0.80, cageL * 0.16)
	for se = -1 to 1 step 2
		x0 = xL
		if se > 0 then x0 = xR - eU
		xo = xL
		if se > 0 then xo = xR
		! 駆動部の枠（4本の柱 2.0・上枠）
		material mSt
		for cx = 0 to 1
			for cy = 0 to 1
				add x0 + cx * (eU - 0.05), yC1 + cy * (cageD - 0.05), zF + 0.04
				block 0.05, 0.05, 1.96
				del 1
			next cy
		next cx
		for cy = 0 to 1
			add x0, yC1 + cy * (cageD - 0.05), zF + 1.95
			block eU, 0.05, 0.05
			del 1
		next cy
		for cx = 0 to 1
			add x0 + cx * (eU - 0.05), yC1, zF + 1.95
			block 0.05, cageD, 0.05
			del 1
		next cx
		! 金網（外側の面と端の面）
		material mMs
		add x0 + 0.05, yC1 + 0.02, zF + 0.10
		block eU - 0.10, 0.005, 1.80
		del 1
		add xo - (se + 1) / 2 * 0.025 + (1 - se) / 2 * 0.02, yC1 + 0.05, zF + 0.10
		block 0.005, cageD - 0.10, 1.80
		del 1
		! 頭上覆い（両端の駆動部の上。KRD 形は荷台全体のヘッドガードを別に描く）
		if roofMode = 1 then
			material mSt
			add x0 - 0.05, yC1 - 0.05, zF + 2.00
			block eU + 0.10, cageD + 0.10, 0.04
			del 1
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
	next se
	if roofMode = 2 then
		! ヘッドガード（荷台全体）と中間の支柱
		material mSt
		add xL - 0.05, yC1 - 0.05, zF + 2.00
		block cageL + 0.10, cageD + 0.10, 0.04
		del 1
		nM = max(1, int((cageL - 2 * eU) / 1.8))
		for k = 1 to nM - 1
			add xL + eU + (cageL - 2 * eU) * k / nM - 0.025, yC1, zF + 0.04
			block 0.05, 0.05, 1.96
			del 1
		next k
	endif
	! 足場側のジャバラ扉（駆動部の間。上下のレール・中の縦桟・菱形の格子）
	material mSt
	xa = xL + eU
	xb = xR - eU
	yJ = yC0 - 0.03
	for hr = 0 to 1
		add xa, yJ, zF + 0.10 + hr * 1.35
		roty 90
		cylind xb - xa, 0.02
		del 2
	next hr
	nV = max(1, int((xb - xa) / 1.5 + 0.5))
	for k = 0 to nV
		add xa + (xb - xa) * k / nV, yJ, zF + 0.04
		cylind 1.45, 0.02
		del 1
	next k
	nJ = max(2, int((xb - xa) / 0.32 + 0.5))
	wJ = (xb - xa) / nJ
	hJ = 1.35 / 3
	jAng = atn(wJ / hJ)
	jLen = sqr(wJ ^ 2 + hJ ^ 2)
	for k = 0 to nJ - 1
		for rr = 0 to 2
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
	for cx = 0 to 1
		for cy = 0 to 1
			add xL + cx * (cageL - 0.06), yC1 + cy * (cageD - 0.06), zF + 0.05
			block 0.06, 0.06, 2.20
			del 1
		next cy
	next cx
	! 屋根（天井の救出口つき）
	add xL, yC1, zF + 2.25
	block cageL, cageD, 0.04
	del 1
	material mMs
	add xL + 0.06, yC1 + 0.01, zF + 0.10
	block cageL - 0.12, 0.005, 2.10
	del 1
	for se = 0 to 1
		add xL + se * (cageL - 0.01), yC1 + 0.06, zF + 0.10
		block 0.005, cageD - 0.12, 2.10
		del 1
	next se
	! 足場側の扉（2枚引き戸の枠と金網・取っ手）
	material mSt
	for k = 0 to 2
		add xL + 0.06 + k * (cageL - 0.12) / 2 - 0.02, yC0 - 0.05, zF + 0.05
		block 0.04, 0.04, 2.10
		del 1
	next k
	for hr = 0 to 1
		add xL + 0.06, yC0 - 0.05, zF + 0.05 + hr * 2.06
		block cageL - 0.12, 0.04, 0.04
		del 1
	next hr
	material mMs
	add xL + 0.08, yC0 - 0.035, zF + 0.10
	block cageL - 0.16, 0.005, 2.00
	del 1
	material mMc
	add -0.06, yC0 - 0.08, zF + 1.00
	block 0.12, 0.03, 0.20
	del 1
	! 搬器とマストをつなぐ駆動枠（ピニオンでラックをかむ）と屋根の上の駆動装置
	material mSt
	add mx[1] - 0.35, my[1] + mastW / 2, zF - 0.18
	block 0.70, yC1 - my[1] - mastW / 2, 0.10
	del 1
	add mx[1] - 0.35, my[1] + mastW / 2, zF + 2.15
	block 0.70, yC1 - my[1] - mastW / 2, 0.10
	del 1
	material mMc
	for k = -1 to 1 step 2
		add mx[1] + k * 0.22, yC1 + 0.10, zF + 2.29
		rotx -90
		cylind 0.40, 0.12
		del 2
	next k
	add mx[1] - 0.30, yC1 + 0.50, zF + 2.29
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
