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
        _param("Length", "hoReach", "到達高さ（マストの頂部の目安。配置で足場の天端を入れる）", 10),
        _param("Length", "gapOut", "足場の外側建地の列から荷台までのあき", 0.1),
        _param("String", "landLevels", "乗り込む作業層の番号（カンマ区切り「2,5」。空は全部の層）", ""),
        _param("String", "landList", "乗り込む作業床の高さ m（配置が入れる。フロアーゲートを描く）", ""),
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
        "! マストの位置（ロングスパンは荷台の両端、それ以外は荷台の外側に1本）",
        "yC0 = -gapOut",
        "yC1 = -gapOut - cageD",
        "dim mx[2]",
        "dim my[2]",
        "if nMast = 2 then",
        "\tmx[1] = -postSp / 2",
        "\tmx[2] = postSp / 2",
        "\tmy[1] = (yC0 + yC1) / 2",
        "\tmy[2] = (yC0 + yC1) / 2",
        "else",
        "\tmx[1] = 0",
        "\tmy[1] = yC1 - 0.25",
        "endif",
        "! フロアーゲートの幅（荷台の長さとゲートの有効開口の小さい方）",
        "gW = cageL",
        "if gateOpen > 0.01 then gW = min(cageL, gateOpen)",
        "! 地上の昇降路の囲い（荷台から 0.3 離す。マストの外まで）",
        "fX = cageL / 2 + 0.3",
        "fY = yC1 - 0.3",
        "for im = 1 to nMast",
        "\tfX = max(fX, abs(mx[im]) + 0.4)",
        "\tfY = min(fY, my[im] - 0.4)",
        "next im",
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
line2 -cageL / 2, yC1, cageL / 2, yC0
line2 -cageL / 2, yC0, cageL / 2, yC1
! マスト
for im = 1 to nMast
	rect2 mx[im] - 0.10, my[im] - 0.10, mx[im] + 0.10, my[im] + 0.10
	line2 mx[im] - 0.10, my[im] - 0.10, mx[im] + 0.10, my[im] + 0.10
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

SCRIPT_3D = """﻿! 昇降機 3D: マスト（ベース・壁つなぎ）・荷台（床・手すり・頭上覆い）・各階のフロアーゲート
resol 8
if matCage > 0 then material matCage
rotz faceAng
mastH = max(hoReach + 1.5, 3)
for im = 1 to nMast
	! ベース
	add mx[im] - 0.40, my[im] - 0.40, 0
	block 0.80, 0.80, 0.12
	del 1
	! マスト（ラック付きの角形。150 角）
	add mx[im] - 0.075, my[im] - 0.075, 0.12
	block 0.15, 0.15, mastH - 0.12
	del 1
	! マストの壁つなぎ（足場の外側建地の列まで）。到達高さ（足場の天端）まで tieE ごと。数量（platforms: 到達高さ÷間隔）と
	! 同じ本数（マストの頂部まで描くと足場の天端より上に繋ぐ先の無い壁つなぎが1段出ていた）
	if showTie then
		zt = tieE
		while zt < hoReach + 0.001 do
			add mx[im], my[im] + 0.075, zt
			rotx -90
			cylind max(0.05, -(my[im] + 0.075)), 0.0243
			del 2
			zt = zt + tieE
		endwhile
	endif
next im
! 荷台（いちばん下に止めた形）: 床・外側と両端の手すり（0.75・1.15）・頭上覆い
zF = 0.30
add -cageL / 2, yC1, zF
block cageL, cageD, 0.06
del 1
for hr = 1 to 2
	zr = zF + 0.35 + 0.40 * hr
	add -cageL / 2, yC1 + 0.03, zr
	roty 90
	cylind cageL, 0.0243
	del 2
	for se = 0 to 1
		add -cageL / 2 + se * cageL, yC1, zr
		rotx -90
		cylind cageD, 0.0243
		del 2
	next se
next hr
for cx = 0 to 1
	for cy = 0 to 1
		add -cageL / 2 + cx * cageL, yC1 + cy * cageD, zF
		cylind 2.1, 0.0243
		del 1
	next cy
next cx
add -cageL / 2, yC1, zF + 2.1
block cageL, cageD, 0.03
del 1
! フロアーゲート（各階の乗り込み口。単管 φ48.6 の扉: 手すり 0.9・中桟 0.45・両端の縦）。機種にフロアーゲートが
! 無ければ開閉式手すり（同じ高さの枠）。足場の線の部品は乗り込み口の固定の手すりを外すだけで、ここが防護を描く
if showGate then
	for il = 1 to nLand
		for hr = 1 to 2
			add gA, -0.04, landH[il] + 0.45 * hr
			roty 90
			cylind gB - gA, 0.0243
			del 2
		next hr
		for se = 0 to 1
			add gA + se * (gB - gA), -0.04, landH[il]
			cylind 1.0, 0.0243
			del 1
		next se
	next il
endif
! 地上の昇降路の囲い（足場側を除く3方。支柱・笠木・中桟・下桟。搬器の下への立入禁止）
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
	next ip
endif
! 渡し板（各階の乗り込み口で足場の作業床から荷台までのすき間を塞ぐ。足場の外側建地の列から荷台の足場側の端の先 0.15 まで）
for il = 1 to nLand
	add -gW / 2, yC0 - 0.15, landH[il] + 0.02
	block gW, gapOut + 0.15, 0.03
	del 1
next il
del top
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
