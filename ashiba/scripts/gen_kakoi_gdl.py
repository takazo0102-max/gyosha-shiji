"""部品 ashiba_kakoi（仮囲い。線・ポリラインの1区間に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「仮囲いを追加して リサーチして詳細度上げてモデル作成できるようにして 斜めにも対応できるようにしてちょ」、
同日「ゲート 仮囲いに必要な部材リサーチして」→「全部入れて 3Dも詳細度上げて」（日建リース工業 仮設資材カタログ Vol.10 の寸法）。

原点＝区間の始めの支柱の芯の地盤、+X＝区間の向き、−Y＝外（道路の側。パネル）、+Y＝敷地の中（控え）。斜めの辺は部品を回して置く。
支柱（単管 φ48.6・天端にキャップ）は postX、足元の地盤は postZ（原点の地盤から。高低差はここ）、横地（単管）は railZ の高さで
支柱の外に直交クランプ ARC1、パネルは runX の範囲に有効幅 pnW ずつ（1枚ずつ足元の地盤に合わせて上下）。安全鋼板（kkType 1・
パンチング 5）は端から 40 の山（R12.5）とフックボルト SSKFB（横地の上を通って裏を半円で回る）、フラットパネル（2）・防音パネル（3）は
縁の折り返し 28 が横地に当たり、継ぎ目に C型金具、角（kkCor）は自在コーナーパネル 240 と蝶番。控えは brX の支柱に（高さ brH から
後ろ brB・高さ brRt へ。上と足は自在クランプ ARC2）、根がらみ（高さ brRt・両端は直交クランプ）。基礎 kkFound＝1 打込み（打込み
パイプ くい丸1.5M）・2 根巻き（□300×400）・3 H形鋼（H-300 の2列・キャッチクランプ）・4 アンカー（支柱は固定ベース PKB、控えの足は
ベースアンカー NBAK）・5 親杭支柱（親杭 H形鋼 pileW を天端 pileZ から継ぎ足して支柱に、添え板、横地は外のフランジにキャッチ
クランプ、控えなし）・6 山留め控え（支柱は単管の打込み、控え・根がらみの足は親杭の根切りの側のフランジにキャッチクランプ2個1組で
留めた単管の立て。親杭の芯は brB−pileW/2−φ48.6/2）。H形鋼の基礎のウェイトは wtN（1スパンに 前の列,後ろの列）。ゲートは gateX（始め,終わり の組）、gateK（1 パネルキャスター・2 キャスター（ジャバラ）・3 ドアパネル W500・
4 ローキャスター・5 ワイドドアパネル W1000）、gateN（始めの側・終わりの側のユニットの数の組。片開きは 0,n）。割付と数量・検定は
src/ashiba/hoarding.py、置くのは scripts/kakoi_run.py。
  python3 scripts/gen_kakoi_gdl.py     # gdl/hsf/ashiba_kakoi を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gen_cfill_gdl import _parse_all  # noqa: E402
import gdl_draft  # noqa: E402
from gen_hoist_gdl import _param  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_kakoi"
MAIN_GUID = "8C3F2A61-4D7E-4B19-A5C2-7E9D0F3B6A48"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "kkType", "パネル（6＝単管シート・1＝安全鋼板・2＝フラットパネル・3＝防音パネル・4＝メッシュフェンス・5＝安全鋼板パンチング）", 1),
        _param("Length", "kkL", "区間の長さ", 10.8),
        _param("Length", "pnH", "パネルの高さ", 3.0),
        _param("Length", "pnW", "パネルの有効幅", 0.54),
        _param("Length", "lift", "パネルの下端（地盤から。負は根入れ）", 0.0),
        _param("String", "postX", "支柱の位置（mm。始めから、カンマ区切り）", "0,1800,3600,5400,7200,9000,10800"),
        _param("String", "postZ", "支柱の足元の地盤（mm。原点の地盤から）", "0,0,0,0,0,0,0"),
        _param("String", "railZ", "横地の高さ（mm。地盤から）", "150,1500,2850"),
        _param("String", "runX", "パネルを張る範囲（mm。始め,終わり の組。角で延ばす・ゲートで切る）", "0,10800"),
        _param("String", "gateX", "ゲート（mm。始め,終わり の組）", ""),
        _param("String", "gateK", "ゲートの種類（1＝パネルキャスター・2＝キャスター・3＝ドア・4＝ローキャスター・5＝ワイドドア）", ""),
        _param("String", "gateN", "ゲートのユニットの数（始めの側,終わりの側 の組）", ""),
        _param("String", "brX", "控えを掛ける支柱の位置（mm）", "0,1800,3600,5400,7200,9000,10800"),
        _param("Length", "brH", "控えを掛ける支柱の高さ（地盤から）", 2.1),
        _param("Length", "brB", "控えの足の後ろ（支柱の芯から敷地の側へ）", 1.55),
        _param("Length", "brRt", "控えの足・根がらみの高さ（地盤から）", 0.15),
        _param("String", "kkCor", "自在コーナーパネル（始め,終わり。1＝あり）", "0,0"),
        _param("String", "hbX", "H形鋼の後ろの列の始め,終わり（mm。角の二等分線で止める）", ""),
        _param("Integer", "kkFound", "基礎（1＝単管の打込み・2＝根巻きコンクリート・3＝H形鋼・4＝アンカー・5＝親杭支柱・6＝山留め控え）", 1),
        _param("String", "wtN", "H形鋼の基礎のウェイト □600（1スパンに 前の列,後ろの列）", "0,0"),
        _param("Length", "pileW", "山留めの親杭（H形鋼）の幅・せい", 0.3),
        _param("Length", "pileZ", "親杭の天端（地盤から。継ぎ足しはここから）", 0.0),
        _param("Length", "embed", "打込みの根入れ", 1.0),
        _param("String", "kkName", "名前（平面の注記）", "仮囲い"),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        *gdl_draft.params(),
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


SCRIPT_1D = ("﻿! 仮囲い: 支柱・地盤・横地・パネルの範囲・ゲート・控え・角を読む（m）\n"
             + _parse_all("postX", "px", "nP") + _parse_all("postZ", "pz", "nZ") + _parse_all("railZ", "rz", "nR")
             + _parse_all("runX", "ru", "nRu") + _parse_all("gateX", "gx", "nGx") + _parse_all("gateK", "gk", "nGk")
             + _parse_all("gateN", "gn", "nGn") + _parse_all("brX", "bq", "nBq") + _parse_all("kkCor", "kc", "nKc") + _parse_all("hbX", "hb", "nHb") + _parse_all("wtN", "wt", "nWt")
             + """for i = nZ + 1 to nP
	pz[i] = 0
next i
for i = 1 to nGk
	gk[i] = round_int(gk[i] * 1000)
next i
for i = 1 to nGn
	gn[i] = round_int(gn[i] * 1000)
next i
cS = 0
cE = 0
if nKc >= 2 then
	cS = round_int(kc[1] * 1000)
	cE = round_int(kc[2] * 1000)
endif
r = 0.0243
ro = 0.0486
! パネルの裏（支柱の芯から外へ）: 安全鋼板は横地の外面＋フック、フラット・防音は縁の折り返し 28
po = 0.0749
if kkType = 2 or kkType = 3 then po = 0.1009
pt = 0.0012
if kkType = 3 then pt = 0.025
if kkType = 6 then pt = 0.0006
! 山留めから取るときは横地が親杭の外のフランジに付く
if kkFound = 5 then
	po = po + pileW / 2 + r - ro
	ro = pileW / 2 + r
endif
wtF = 0
wtR = 0
if nWt >= 2 then
	wtF = round_int(wt[1] * 1000)
	wtR = round_int(wt[2] * 1000)
endif
kkTop = lift + pnH
""")

SCRIPT_2D_T = """﻿! 仮囲い 2D（CAD の平面図の描き方: scripts/gdl_draft.py）: パネル（外）は太線、横地・支柱・控え（中）・ゲートは細線、地中の基礎
! （親杭・根巻き・H形鋼の根入れ）は隠れ線。縮尺で 詳細（1/100: パネルの厚み・横地・支柱・控え・基礎）・標準（1/200: パネルの1本と
! 支柱・控えの1本）・簡略（パネルの線とゲートの開口だけ）
@HEAD@
define style "kkT" "ＭＳ Ｐゴシック", texSiz, 2, 0
define style "kkB" "ＭＳ Ｐゴシック", texSiz, 8, 0
define style "kkL" "ＭＳ Ｐゴシック", texSiz, 4, 0
define style "kkR" "ＭＳ Ｐゴシック", texSiz, 6, 0
style "kkT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
! パネル（外の面。太線）と横地（細線）
for k = 1 to nRu - 1 step 2
	pen pO
	line2 ru[k], -po, ru[k + 1], -po
	if drLv = 1 then
		pen pT
		line2 ru[k], -po - max(pt, 0.004), ru[k + 1], -po - max(pt, 0.004)
		line2 ru[k], -ro, ru[k + 1], -ro
	endif
next k
if drLv < 3 then
	pen pT
	! 支柱
	for i = 1 to nP
		circle2 px[i], 0, r
	next i
	! 控え（中）。標準は芯の1本
	for i = 1 to nBq
		if drLv = 1 then
			line2 bq[i] - ro - r, 0, bq[i] - ro - r, brB
			line2 bq[i] - ro + r, 0, bq[i] - ro + r, brB
			if kkFound <= 2 or kkFound = 6 then
				line2 bq[i] + ro - r, 0, bq[i] + ro - r, brB
				line2 bq[i] + ro + r, 0, bq[i] + ro + r, brB
			endif
		else
			line2 bq[i], 0, bq[i], brB
		endif
		circle2 bq[i], brB, r
	next i
endif
! 基礎（地中は隠れ線。詳細だけ）
if drLv = 1 then
	pen pT
	line_type ltH
	for i = 1 to nP
		if kkFound = 2 then rect2 px[i] - 0.15, -0.15, px[i] + 0.15, 0.15
		if kkFound = 4 then rect2 px[i] - 0.06, -0.06, px[i] + 0.06, 0.06
		if kkFound = 5 then
			rect2 px[i] - pileW / 2, -pileW / 2, px[i] + pileW / 2, -pileW / 2 + 0.015
			rect2 px[i] - pileW / 2, pileW / 2 - 0.015, px[i] + pileW / 2, pileW / 2
			rect2 px[i] - 0.005, -pileW / 2 + 0.015, px[i] + 0.005, pileW / 2 - 0.015
		endif
	next i
	for i = 1 to nBq
		if kkFound = 2 then rect2 bq[i] - 0.15, brB - 0.15, bq[i] + 0.15, brB + 0.15
		if kkFound = 4 then rect2 bq[i] - 0.07, brB - 0.07, bq[i] + 0.07, brB + 0.07
		if kkFound = 6 then rect2 bq[i] - pileW / 2, brB - pileW - r, bq[i] + pileW / 2, brB - r
	next i
	if kkFound = 3 then
		line2 0, -0.15, kkL, -0.15
		line2 0, 0.15, kkL, 0.15
		line2 0, brB - 0.15, kkL, brB - 0.15
		line2 0, brB + 0.15, kkL, brB + 0.15
	endif
	line_type ltS
endif
! ゲート（細線）
pen pT
for k = 1 to nGx - 1 step 2
	j = (k + 1) / 2
	g0 = gx[k]
	g1 = gx[k + 1]
	gw = g1 - g0
	kd = 2
	if j <= nGk then kd = gk[j]
	nL = 0
	nRt = 1
	if 2 * j <= nGn then
		nL = gn[2 * j - 1]
		nRt = gn[2 * j]
	endif
	! 開口の両端の印（簡略でも）
	line2 g0, -po - 0.15, g0, 0.15
	line2 g1, -po - 0.15, g1, 0.15
	if drLv < 3 then
		if kd = 3 or kd = 5 then
			! 内開きのドア（扉 413・910）
			lw = 0.413
			if kd = 5 then lw = 0.91
			dx0 = g0 + (gw - lw) / 2
			line2 g0, -0.1009, g1, -0.1009
			line2 dx0, -0.1009, dx0, -0.1009 + lw
			arc2 dx0, -0.1009, lw, 0, 90
		else
			! キャスターゲート（閉めた線）と畳んだときの置き場（ユニット 260＋支柱 90×2）
			line2 g0, 0.03, g1, 0.03
			line2 g0, -0.03, g1, -0.03
			if drLv = 1 then
				if nL > 0 then rect2 g0, -0.04, g0 + nL * 0.26 + 0.18, 0.04
				if nRt > 0 then rect2 g1 - nRt * 0.26 - 0.18, -0.04, g1, 0.04
			endif
		endif
	endif
next k
! 名前（外の側に。図面の向きに関係なく水平。外の向きが画面で横なら左・右寄せ、縦なら上・下寄せで線から離す）
pen penEquip
sx = sin(SYMB_ROTANGLE)
sy = -cos(SYMB_ROTANGLE)
if SYMB_MIRRORED then sx = -sx
add2 kkL / 2, -po - 0.25
rot2 -SYMB_ROTANGLE
if abs(sx) > abs(sy) then
	if sx > 0 then
		style "kkL"
	else
		style "kkR"
	endif
else
	if sy < 0 then
		style "kkT"
	else
		style "kkB"
	endif
endif
text2 0, 0, kkName
del 2
hotspot2 0, 0
hotspot2 kkL, 0
! 控えのホットスポット（1本めの控えの足。区間の控えがそろって動く）
if nBq > 0 and kkFound <> 6 then
	hotspot2 bq[1], 0, 11, brB, 1 + 128
	hotspot2 bq[1], brB, 12, brB, 2
	hotspot2 bq[1], -1, 13, brB, 3
endif
"""

# 範囲の線（pZ）は使わない。マスタースクリプトの配列 pz と GDL では同じ名前になるので外す
# 描き方の決めの pO・pT（太線・細線のペン）は GDL では大文字小文字を区別しないので、マスタースクリプトのパネルの位置 po・
# 厚み pt と同じ変数になる（パネルが 21m 先に描かれた 2026-11-04）→ 仮囲いでは pnO・pnT に。範囲の線 pZ（配列 pz とぶつかる）は使わない
_HEAD = re.sub(r"\bpO\b", "pnO", re.sub(r"\bpT\b", "pnT", gdl_draft.head().replace("pZ = penZone\nif pZ < 1 then pZ = pT\n", "")))
SCRIPT_2D = SCRIPT_2D_T.replace("@HEAD@", _HEAD.rstrip("\n")).replace("pen pO\n", "pen pnO\n").replace("pen pT\n", "pen pnT\n")


SCRIPT_3D = """﻿! 仮囲い 3D（日建リース工業 仮設資材カタログ Vol.10 の寸法: 単管 φ48.6×2.4、兼用直交クランプ ARC1・自在クランプ ARC2 の口
! 幅40・帯4.5、安全鋼板 有効幅540 t1.2 端から40 の山、フックボルト SSKFB φ9、VIC フラットパネル 有効幅500 縁の折り返し 28・C型金具、
! 自在コーナーパネル 240、控え 高さ 2100→後ろ 1550、根がらみ、打込みパイプ くい丸1.5M、根巻き □300×400、H-300×300×10×15、
! 固定ベース PKB □120・ベースアンカー NBAK □140 t9 φ48.6×3.2 H309、キャスターゲート 単スパン 900・H1800・キャスター 130、
! ドアパネル VICD200 W500（扉 413）・VICDW200 W1000（扉 910）、上に VIC100）
define material "kk_steel" 2, 0.62, 0.64, 0.68
define material "kk_panel" 2, 0.90, 0.91, 0.90
define material "kk_flat" 2, 0.95, 0.95, 0.94
define material "kk_sound" 2, 0.78, 0.80, 0.78
define material "kk_clamp" 2, 0.85, 0.70, 0.30
define material "kk_conc" 2, 0.70, 0.70, 0.68
define material "kk_sheet" 0, 0.46, 0.62, 0.50, 0.6, 0.6, 0.1, 0, 5, 0, 1, 1, 1, 0, 0, 0, 0
define material "kk_mesh" 0, 0.55, 0.58, 0.60, 0.6, 0.6, 0.1, 0.8, 5, 0, 1, 1, 1, 0, 0, 0, 0
define material "kk_punch" 0, 0.40, 0.42, 0.45, 0.6, 0.6, 0.1, 0.5, 5, 0, 1, 1, 1, 0, 0, 0, 0
define material "kk_alum" 2, 0.80, 0.82, 0.84
define material "kk_cap" 2, 0.95, 0.80, 0.10
define material "kk_wheel" 2, 0.15, 0.15, 0.15
define material "kk_pile" 2, 0.45, 0.33, 0.25
rN = 12
resol rN
clW = 0.040
clT = 0.0045
hkR = r + 0.0055
material "kk_steel"
! ---- 支柱（打込みは根入れ、根巻きはコンクリートの中、H形鋼は上のフランジから、アンカーは固定ベースの上）と天端のキャップ ----
for i = 1 to nP
	z0 = pz[i]
	if kkFound = 5 then
		! 親杭（H形鋼）を天端から継ぎ足す: 下に親杭の頭（800）、継手の添え板（フランジの外 2・ウェブの両側 2）とボルト
		material "kk_pile"
		xh = px[i]
		yh = 0
		zq = z0 + pileZ - 0.8
		hq = 0.8
		gosub "hsec"
		material "kk_steel"
		zq = z0 + pileZ
		hq = kkTop - pileZ
		gosub "hsec"
		material "kk_clamp"
		for e = -1 to 1 step 2
			add px[i] - pileW / 2 + 0.02, e * (pileW / 2 + 0.006) - 0.006, z0 + pileZ - 0.3
			block pileW - 0.04, 0.012, 0.6
			del 1
			add px[i] + e * 0.011 - 0.005, -pileW / 2 + 0.05, z0 + pileZ - 0.25
			block 0.01, pileW - 0.1, 0.5
			del 1
		next e
		material "kk_steel"
		for e = -1 to 1 step 2
			for c = 0 to 3
				add px[i] - pileW / 2 + 0.06 + (c mod 2) * (pileW - 0.12), e * (pileW / 2 + 0.012), z0 + pileZ - 0.2 + int(c / 2) * 0.4
				rotx -90 * e
				resol 6
				cylind 0.012, 0.011
				resol rN
				del 2
			next c
		next e
	else
	zb = z0
	if kkFound = 1 or kkFound = 6 then zb = z0 - embed
	if kkFound = 2 then zb = z0 - 0.35
	if kkFound = 3 then zb = z0 + 0.3
	if kkFound = 4 then zb = z0 + 0.006
	zt = z0 + kkTop
	add px[i], 0, zb
	cylind zt - zb, r
	del 1
	if kkFound = 2 then
		material "kk_conc"
		add px[i] - 0.15, -0.15, z0 - 0.4
		block 0.3, 0.3, 0.42
		del 1
		material "kk_steel"
	endif
	if kkFound = 4 then
		! 固定ベース PKB（□120・4-φ11）とあと施工アンカー
		add px[i] - 0.06, -0.06, z0
		block 0.12, 0.12, 0.006
		del 1
		add px[i], 0, z0 + 0.006
		cylind 0.1, 0.0209
		del 1
		for e = 0 to 3
			add px[i] + 0.0425 * (2 * (e mod 2) - 1), 0.0425 * (2 * int(e / 2) - 1), z0 + 0.006
			resol 6
			cylind 0.008, 0.009
			resol rN
			del 1
		next e
	endif
	endif
next i
! ---- 横地（支柱の外。地盤に沿って流す）と直交クランプ ARC1 ----
for k = 1 to nRu - 1 step 2
	a0 = ru[k]
	a1 = ru[k + 1]
	for j = 1 to nR
		xq = a0
		gosub "gz"
		x0q = a0
		z0q = zq + rz[j]
		for i = 1 to nP + 1
			xn = a1
			if i <= nP then xn = px[i]
			if xn > x0q + 0.001 and xn <= a1 + 0.001 then
				xq = xn
				gosub "gz"
				x1q = xn
				z1q = zq + rz[j]
				yq = -ro
				rq = r
				gosub "tube"
				x0q = x1q
				z0q = z1q
			endif
		next i
	next j
	for i = 1 to nP
		if px[i] >= a0 - 0.001 and px[i] <= a1 + 0.001 then
			for j = 1 to nR
				if kkFound = 5 then
					! キャッチクランプ（H形鋼用）: 横地を親杭の外のフランジに
					add px[i], -ro, pz[i] + rz[j]
					rotz 180
					jR = r
					gosub "jaw"
					del 2
					material "kk_clamp"
					add px[i] - 0.03, -pileW / 2 - 0.006, pz[i] + rz[j] - 0.035
					block 0.06, 0.03, 0.07
					del 1
					material "kk_steel"
				else
					add px[i], 0, pz[i] + rz[j]
					clDy = ro
					gosub "orth"
					del 1
				endif
			next j
		endif
	next i
next k
! ---- パネル（1枚ずつ足元の地盤に合わせる）・角の自在コーナーパネル・取付金具 ----
for k = 1 to nRu - 1 step 2
	a0 = ru[k]
	a1 = ru[k + 1]
	xa = a0
	xb = a1
	if kkType = 2 or kkType = 3 then
		if k = 1 and cS = 1 then xa = a0 + 0.24
		if k = nRu - 1 and cE = 1 then xb = a1 - 0.24
	endif
	! 角の自在コーナーパネル（240。角の側に蝶番）
	for e = 0 to 1
		cx0 = a0
		cx1 = xa
		cxh = a0
		if e = 1 then
			cx0 = xb
			cx1 = a1
			cxh = a1
		endif
		if cx1 - cx0 > 0.01 then
			x0 = cx0
			x1 = cx1
			gosub "pnl"
			material "kk_steel"
			xq = cxh
			gosub "gz"
			for c = 0 to 4
				add cxh, -po - pt - 0.006, zq + lift + 0.1 + c * (pnH - 0.3) / 4
				cylind 0.1, 0.008
				del 1
			next c
			add cxh, -po - pt - 0.006, zq + lift
			cylind pnH, 0.003
			del 1
		endif
	next e
	x0 = xa
	while x0 < xb - 0.005 do
		x1 = min(xb, x0 + pnW)
		gosub "pnl"
		x0 = x1
	endwhile
	! フラットパネルの継ぎ目の C型金具（VIC-Cカナグ）: 横地ごと、継ぎ目と端に
	if kkType = 2 or kkType = 3 then
		xj = xa
		while xj <= xb + 0.001 do
			xq = xj
			gosub "gz"
			for j = 1 to nR
				add min(max(xj, a0 + 0.015), a1 - 0.015), -ro, zq + rz[j]
				gosub "cfit"
				del 1
			next j
			if xj >= xb - 0.001 then
				xj = xb + 1
			else
				xj = min(xb, xj + pnW)
			endif
		endwhile
	endif
next k
! ---- 控え（自在クランプ ARC2）・根がらみ（直交クランプ ARC1）・控えの足 ----
! 控えの足は根がらみの直交クランプの上に掛ける（同じ高さだとクランプが当たる: 利用者の指摘 2026-11-06）
brFt = brRt
if kkFound <= 2 or kkFound = 6 then brFt = brRt + 0.13
dzB = brH - brFt
bL = sqr(dzB ^ 2 + brB ^ 2)
brA = atn(dzB / max(brB, 0.01))
! 控えのホットスポット（1本めの控えに。区間の控えがそろって動く）: 足の後ろ brB・支柱に掛ける高さ brH。山留め控えは親杭で決まる
if nBq > 0 and kkFound <> 6 then
	xq = bq[1]
	gosub "gz"
	hotspot bq[1], 0, zq, 301, brH, 1 + 128
	hotspot bq[1], 0, zq + brH, 302, brH, 2
	hotspot bq[1], 0, zq - 1, 303, brH, 3
	hotspot bq[1], 0, zq + brFt, 304, brB, 1 + 128
	hotspot bq[1], brB, zq + brFt, 305, brB, 2
	hotspot bq[1], -1, zq + brFt, 306, brB, 3
endif
for i = 1 to nBq
	xq = bq[i]
	gosub "gz"
	zg = zq
	add bq[i] - ro, 0, zg + brH
	rotx -(90 + brA)
	cylind bL, r
	del 2
	add bq[i], 0, zg + brH
	clDy = ro
	clA = brA
	gosub "swiv"
	del 1
	if kkFound <= 2 or kkFound = 6 then
		! 根がらみ（支柱から控えの足へ水平）
		add bq[i] + ro, -0.06, zg + brRt
		rotx -90
		cylind brB + 0.12, r
		del 2
		for e = 0 to 1
			add bq[i], e * brB, zg + brRt
			rotz 90
			clDy = ro
			gosub "orth"
			del 2
		next e
	endif
	! 控えの足
	zs0 = zg - 0.9
	zs1 = zg + 0.6
	if kkFound = 2 then
		zs0 = zg - 0.35
		zs1 = zg + 0.65
		material "kk_conc"
		add bq[i] - 0.15, brB - 0.15, zg - 0.4
		block 0.3, 0.3, 0.42
		del 1
		material "kk_steel"
	endif
	if kkFound = 3 then
		zs0 = zg + 0.3
		zs1 = zg + 0.8
	endif
	if kkFound = 6 then
		! 山留めの親杭の頭（根切りの側のフランジに単管の立てをキャッチクランプ2個1組）
		zs0 = zg + pileZ - 0.4
		zs1 = zg + pileZ + 0.6
		material "kk_pile"
		xh = bq[i]
		yh = brB - pileW / 2 - r
		zq = zg + pileZ - 0.8
		hq = 0.8
		gosub "hsec"
		material "kk_clamp"
		for e = 0 to 1
			add bq[i] - 0.03, yh + pileW / 2 - 0.004, zg + pileZ - 0.33 + e * 0.2
			block 0.06, 0.035, 0.06
			del 1
		next e
		material "kk_steel"
	endif
	if kkFound = 4 then
		! ベースアンカー NBAK（□140 t9・φ48.6×3.2 H309）
		zs0 = zg + 0.009
		zs1 = zg + 0.309
		add bq[i] - 0.07, brB - 0.07, zg
		block 0.14, 0.14, 0.009
		del 1
		for e = 0 to 3
			add bq[i] + 0.04 * (2 * (e mod 2) - 1), brB + 0.04 * (2 * int(e / 2) - 1), zg + 0.009
			resol 6
			cylind 0.009, 0.009
			resol rN
			del 1
		next e
	endif
	add bq[i], brB, zs0
	cylind zs1 - zs0, r
	del 1
	xq = bq[i]
	yq = brB
	zq = zs1
	if kkFound <> 4 then gosub "cap"
	add bq[i], brB, zg + brFt
	clDy = ro
	clA = brA
	gosub "swiv"
	del 1
next i
! ---- H形鋼の基礎（2列。支柱の下と控えの足の下）とキャッチクランプ ----
if kkFound = 3 then
	for e = 0 to 1
		yh = e * brB
		! 前の列は区間の始め〜終わり、後ろの列は hbX（角の二等分線で止める）
		lo = 0
		hi = kkL
		if e = 1 and nHb >= 2 then
			lo = hb[1]
			hi = hb[2]
		endif
		for i = 0 to nP
			x0q = lo
			if i > 0 then x0q = max(lo, px[i])
			x1q = hi
			if i < nP then x1q = min(hi, px[i + 1])
			xq = x0q
			gosub "gz"
			z0q = zq
			xq = x1q
			gosub "gz"
			z1q = zq
			dxq = x1q - x0q
			if dxq > 0.001 then
				add x0q, yh, z0q
				roty -atn((z1q - z0q) / dxq)
				lq = sqr(dxq ^ 2 + (z1q - z0q) ^ 2)
				add 0, -0.15, 0
				block lq, 0.3, 0.015
				addz 0.285
				block lq, 0.3, 0.015
				del 1
				add 0, 0.145, 0.015
				block lq, 0.01, 0.27
				del 4
			endif
		next i
	next e
	material "kk_clamp"
	for i = 1 to nP
		for e = -1 to 1 step 2
			add px[i] + e * 0.06 - 0.025, -0.03, pz[i] + 0.3
			block 0.05, 0.06, 0.05
			del 1
		next e
	next i
	for i = 1 to nBq
		xq = bq[i]
		gosub "gz"
		for e = -1 to 1 step 2
			add bq[i] + e * 0.06 - 0.025, brB - 0.03, zq + 0.3
			block 0.05, 0.06, 0.05
			del 1
		next e
	next i
	! コンクリートウェイト □600（スパンの中に 前の列の内・後ろの列の手前）とチェーン
	for i = 1 to nP - 1
		for e = 0 to 1
			nW = wtF
			yw = 0.16
			if e = 1 then
				nW = wtR
				yw = brB - 0.76
			endif
			for c = 1 to nW
				xw = (px[i] + px[i + 1]) / 2 + (c - (nW + 1) / 2) * 0.65 - 0.3
				xq = xw + 0.3
				gosub "gz"
				material "kk_conc"
				add xw, yw, zq
				block 0.6, 0.6, 0.6
				del 1
				material "kk_steel"
				yc = yw - 0.02
				if e = 1 then yc = yw + 0.62
				add xw + 0.3, yc, zq + 0.3
				roty 90
				cylind 0.03, 0.01
				del 2
			next c
		next e
	next i
	material "kk_steel"
endif
! ---- ゲート ----
for k = 1 to nGx - 1 step 2
	j = (k + 1) / 2
	g0 = gx[k]
	g1 = gx[k + 1]
	gw = g1 - g0
	kd = 2
	if j <= nGk then kd = gk[j]
	nL = 0
	nRt = max(1, round_int(gw / 0.9))
	if 2 * j <= nGn then
		nL = gn[2 * j - 1]
		nRt = gn[2 * j]
	endif
	xq = (g0 + g1) / 2
	gosub "gz"
	zg = zq
	if kd = 3 or kd = 5 then
		gosub "door"
	else
		gB = 1.8
		if kd = 4 then gB = 1.25
		! 片開きは終わりの側に固定（右固定）、両開きは大きい方が終わりの側
		lL = gw * nL / max(1, nL + nRt)
		if nL > 0 then
			lx0 = g0
			lx1 = g0 + lL
			nU = nL
			sd = -1
			gosub "jab"
		endif
		if nRt > 0 then
			lx0 = g0 + lL
			lx1 = g1
			nU = nRt
			sd = 1
			gosub "jab"
		endif
	endif
	material "kk_steel"
next k
end

"gz":
	! xq の地盤（支柱の足元の間を直線で）
	zq = 0
	if nP > 0 then
		zq = pz[1]
		if xq >= px[nP] then zq = pz[nP]
		for jj = 1 to nP - 1
			if xq >= px[jj] and xq <= px[jj + 1] then zq = pz[jj] + (pz[jj + 1] - pz[jj]) * (xq - px[jj]) / max(0.001, px[jj + 1] - px[jj])
		next jj
	endif
	return

"tube":
	! (x0q, yq, z0q) から (x1q, yq, z1q) の管（x1q > x0q）
	dxq = x1q - x0q
	lq = sqr(dxq ^ 2 + (z1q - z0q) ^ 2)
	if lq > 0.001 then
		add x0q, yq, z0q
		roty 90 - atn((z1q - z0q) / max(0.0001, dxq))
		cylind lq, rq
		del 2
	endif
	return

"hsec":
	! H形鋼（pileW 角・フランジ 15・ウェブ 10）: 芯 (xh, yh)、zq から hq の高さ。フランジは区間の向きに沿う（山留めの面）
	add xh - pileW / 2, yh - pileW / 2, zq
	block pileW, 0.015, hq
	addy pileW - 0.015
	block pileW, 0.015, hq
	del 2
	add xh - 0.005, yh - pileW / 2 + 0.015, zq
	block 0.01, pileW - 0.03, hq
	del 1
	return

"cap":
	! 単管キャップ（キャッピカ。黄）: (xq, yq, zq) は管の天端
	material "kk_cap"
	add xq, yq, zq - 0.02
	cylind 0.035, r + 0.002
	del 1
	material "kk_steel"
	return

"pnl":
	! パネル1枚（x0〜x1）。足元の地盤に合わせる
	xq = (x0 + x1) / 2
	gosub "gz"
	zp = zq + lift
	if kkType = 4 then
		! メッシュフェンス: φ32 の枠と金網
		material "kk_steel"
		add x0 + 0.016, -po - 0.016, zp
		cylind pnH, 0.016
		del 1
		add x1 - 0.016, -po - 0.016, zp
		cylind pnH, 0.016
		del 1
		for e2 = 0 to 1
			add x0, -po - 0.016, zp + 0.016 + e2 * (pnH - 0.032)
			roty 90
			cylind x1 - x0, 0.016
			del 2
		next e2
		material "kk_mesh"
		add x0 + 0.03, -po - 0.018, zp + 0.03
		block x1 - x0 - 0.06, 0.004, pnH - 0.06
		del 1
		return
	endif
	if kkType = 6 then
		! 防炎シート（ハトメ 45cm ごとを上下の縁に）
		material "kk_sheet"
		add x0 + 0.001, -po - pt, zp
		block x1 - x0 - 0.002, pt, pnH
		del 1
		material "kk_steel"
		for e2 = 0 to 1
			xr = x0 + 0.075
			while xr < x1 - 0.02 do
				add xr, -po - pt, zp + 0.03 + e2 * (pnH - 0.06)
				rotx 90
				cylind 0.001, 0.012
				del 2
				xr = xr + 0.45
			endwhile
		next e2
		return
	endif
	material "kk_panel"
	if kkType = 2 then material "kk_flat"
	if kkType = 3 then material "kk_sound"
	add x0 + 0.001, -po - pt, zp
	block x1 - x0 - 0.002, pt, pnH
	del 1
	if kkType = 1 or kkType = 5 then
		! 安全鋼板の山（端から 40・R12.5。外へ）
		for e2 = 0 to 1
			xr = x0 + 0.04
			if e2 = 1 then xr = x1 - 0.04
			if xr > x0 + 0.015 and xr < x1 - 0.015 then
				for c = 0 to 6
					put xr + 0.0125 * cos(180 + 30 * c), -po - pt + 0.0125 * sin(180 + 30 * c)
				next c
				add 0, 0, zp
				prism nsp / 2, pnH, get(nsp)
				del 1
			endif
		next e2
		if kkType = 5 then
			! パンチングの範囲（横地の間の真ん中の帯）
			material "kk_punch"
			for j = 1 to nR - 1
				zp0 = zq + rz[j] + 0.12
				zp1 = zq + rz[j + 1] - 0.12
				if zp1 > zp0 + 0.05 and x1 - x0 > 0.3 then
					add (x0 + x1) / 2 - 0.1, -po - pt - 0.0008, zp0
					block 0.2, 0.0006, zp1 - zp0
					del 1
				endif
			next j
		endif
		! フックボルト SSKFB（φ9）: 横地ごとに2本
		for j = 1 to nR
			for e2 = 0 to 1
				xb2 = x0 + 0.1 + e2 * (x1 - x0 - 0.2)
				if x1 - x0 < 0.25 then xb2 = (x0 + x1) / 2
				xq = xb2
				gosub "gz"
				add xb2, -ro, zq + rz[j]
				gosub "hook"
				del 1
			next e2
		next j
	else
		! フラットパネル（VIC）の縁の折り返し 28（横地に当たる）
		material "kk_flat"
		if kkType = 3 then material "kk_sound"
		for e2 = 0 to 1
			add x0 + 0.001 + e2 * (x1 - x0 - 0.0032), -po, zp
			block 0.0012, 0.028, pnH
			del 1
		next e2
	endif
	material "kk_steel"
	return

"hook":
	! フックボルト SSKFB: 原点＝横地の芯。パネルの外のナット・横地の上を通る軸・横地の裏を回る半円（φ9）
	material "kk_steel"
	add 0, -(po + pt + 0.012 - ro), hkR
	rotx -90
	cylind po + pt + 0.012 - ro, 0.0045
	resol 6
	addz -0.008
	cylind 0.008, 0.0085
	resol rN
	del 3
	rotx -90
	revolve 9, 180, 63,
		0.0045, hkR, 0,
		0.0032, hkR + 0.0032, 0,
		0, hkR + 0.0045, 0,
		-0.0032, hkR + 0.0032, 0,
		-0.0045, hkR, 0,
		-0.0032, hkR - 0.0032, 0,
		0, hkR - 0.0045, 0,
		0.0032, hkR - 0.0032, 0,
		0.0045, hkR, 0
	del 1
	return

"cfit":
	! C型金具（VIC-Cカナグ）: 原点＝横地の芯。横地の裏を回る帯と、上下の腕・パネルの折り返しを締めるボルト
	material "kk_clamp"
	rotx -90
	revolve 5, 180, 63,
		-0.012, r + 0.001, 0,
		0.012, r + 0.001, 0,
		0.012, r + 0.004, 0,
		-0.012, r + 0.004, 0,
		-0.012, r + 0.001, 0
	del 1
	for e3 = -1 to 1 step 2
		add -0.012, -(po - ro - 0.002), e3 * (r + 0.0025) - 0.0015
		block 0.024, po - ro - 0.002, 0.003
		del 1
	next e3
	material "kk_steel"
	add 0, -(po - ro - 0.014), -(r + 0.012)
	cylind 2 * (r + 0.012), 0.004
	addz 2 * (r + 0.012)
	resol 6
	cylind 0.006, 0.0085
	resol rN
	del 2
	return

"jaw":
	! クランプの口1つ（日建 ARC1 の形・規格の寸法。管は X 向きで芯が原点、半径 jR。相手の口は −Y 側）
	material "kk_clamp"
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
	material "kk_steel"
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

"swiv":
	! 自在クランプ（日建 兼用自在クランプ ARC2）: 原点＝柱の芯（Z 向き）、相手の管は柱から −X に clDy、
	! YZ 面で +Y へ水平から clA 度下がる向き（控え）
	rotz -90
	roty -90
	jR = r
	gosub "jaw"
	del 1
	add 0, -clDy, 0
	rotz 180
	roty clA
	jR = r
	gosub "jaw"
	del 4
	return

"jab":
	! キャスターゲートの片側（lx0〜lx1、ユニット nU、sd＝−1 は始めの側に固定・+1 は終わりの側に固定）: 側支柱・中央支柱（取手・
	! 落とし棒）・単スパン（ジャバラの交差する平鋼）・キャスター（130）・パネルキャスターはアルミパネル
	zc = zg + 0.13
	xfix = lx1 - 0.09
	xfre = lx0
	if sd < 0 then
		xfix = lx0
		xfre = lx1 - 0.09
	endif
	material "kk_alum"
	add xfix, -0.03, zc
	block 0.09, 0.06, gB
	del 1
	add xfre, -0.03, zc
	block 0.09, 0.06, gB
	del 1
	material "kk_steel"
	add xfre + 0.045 - sd * 0.02, -0.07, zc + gB * 0.55
	block 0.02, 0.04, 0.12
	del 1
	add xfre + 0.045, 0.04, zg - 0.05
	cylind 0.6, 0.008
	del 1
	uw = (lx1 - lx0 - 0.18) / max(1, nU)
	ux0 = lx0 + 0.09
	nr2 = 5
	if gB < 1.5 then nr2 = 4
	hc = gB / nr2
	for u = 1 to nU
		xa2 = ux0 + (u - 1) * uw
		material "kk_alum"
		if u > 1 then
			add xa2 - 0.01, -0.02, zc
			block 0.02, 0.04, gB
			del 1
		endif
		cw = uw / 2
		for c = 0 to 1
			xc = xa2 + c * cw
			for rr = 0 to nr2 - 1
				zl = zc + rr * hc
				for e3 = 0 to 1
					x0q = xc
					x1q = xc + cw
					z0q = zl
					z1q = zl + hc
					if (rr + e3) mod 2 = 1 then
						z0q = zl + hc
						z1q = zl
					endif
					yq = -0.012 + 0.024 * e3
					rq = 0.006
					gosub "tube"
				next e3
			next rr
		next c
		if kd = 1 then
			! パネルキャスターゲートのアルミパネル（ユニットごと。外の面）
			add xa2 + 0.02, -0.04, zc + 0.05
			block uw - 0.04, 0.003, gB - 0.1
			del 1
		endif
		! キャスター（ユニットの継ぎ目ごと。車 φ100・幅 30・金具 130）
		if u mod 2 = 1 or u = nU then
			xw = xa2 + uw
			if u = 1 and nU > 1 then xw = xa2
			material "kk_steel"
			add xw - 0.03, -0.03, zg + 0.08
			block 0.06, 0.06, 0.05
			del 1
			material "kk_wheel"
			add xw, -0.015, zg + 0.05
			rotx -90
			cylind 0.03, 0.05
			del 2
		endif
	next u
	material "kk_steel"
	for e3 = 0 to 1
		xw = xfix + 0.045
		if e3 = 1 then xw = xfre + 0.045
		material "kk_wheel"
		add xw, -0.015, zg + 0.05
		rotx -90
		cylind 0.03, 0.05
		del 2
	next e3
	material "kk_steel"
	return

"door":
	! ドアパネル VICD200（W500・扉 413）・ワイドドアパネル VICDW200（W1000・扉 910）。上に VIC100、両脇は単管の支柱
	lw = 0.413
	if kd = 5 then lw = 0.91
	pd = 0.1009
	dx0 = g0 + (gw - lw) / 2
	material "kk_steel"
	add g0, -pd - 0.03, zg
	block 0.03, 0.03, 2.0
	del 1
	add g1 - 0.03, -pd - 0.03, zg
	block 0.03, 0.03, 2.0
	del 1
	add g0, -pd - 0.03, zg + 1.97
	block gw, 0.03, 0.03
	del 1
	add g0, -pd - 0.03, zg
	block gw, 0.03, 0.02
	del 1
	if dx0 - g0 > 0.035 then
		material "kk_flat"
		add g0 + 0.03, -pd - 0.003, zg + 0.02
		block dx0 - g0 - 0.03, 0.003, 1.95
		del 1
		add dx0 + lw, -pd - 0.003, zg + 0.02
		block g1 - 0.03 - dx0 - lw, 0.003, 1.95
		del 1
	endif
	material "kk_flat"
	add dx0, -pd - 0.03, zg + 0.03
	block lw, 0.03, 1.93
	del 1
	material "kk_steel"
	for c = 0 to 2
		add dx0 + 0.005, -pd - 0.035, zg + 0.25 + c * 0.7
		cylind 0.1, 0.007
		del 1
	next c
	add dx0 + lw - 0.07, -pd - 0.03, zg + 1.0
	rotx 90
	cylind 0.04, 0.01
	addz 0.04
	sphere 0.02
	del 3
	! 上の調整パネル VIC100（パネルの上端まで）
	if kkTop - 2.0 > 0.05 then
		nA = max(1, round_int(gw / 0.5))
		for c = 0 to nA - 1
			material "kk_flat"
			add g0 + c * gw / nA + 0.001, -pd - 0.0012, zg + 2.0
			block gw / nA - 0.002, 0.0012, kkTop - 2.0
			del 1
			for e3 = 0 to 1
				add g0 + c * gw / nA + 0.001 + e3 * (gw / nA - 0.0032), -pd, zg + 2.0
				block 0.0012, 0.028, kkTop - 2.0
				del 1
			next e3
		next c
	endif
	material "kk_steel"
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
    print(f"ashiba_kakoi: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
