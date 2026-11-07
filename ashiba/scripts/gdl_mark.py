"""クレーンの吊り点の印（利用者の指定 2026-11-07「フックから吊りしろのところに丸十字のマークつけてホットスポットで動かせるようにして自由に あと吊りに総荷重でわかるようにして」）.

ラフター・クローラ・タワーで同じものを使う。フックの下の吊りしろ slgH（既定 6m。SCP の既定）に丸十字を描き、横に「Max 8.21t」（今の半径の定格総荷重×安全率）を書く。
印は平面のどの向きにも（hfX・hfY。丸十字の点）、上下にも（mkZ。丸十字の少し上の点）ホットスポットで引け、フックが一緒に動く。mkZ＝印の高さで、パラメータスクリプトがフックへ書き戻す。
3D の丸十字は水平に寝かせ、文字だけ視点へ向ける（クレーン情報の文字と同じ回し方）。
"""

from __future__ import annotations

HOTSPOT_3D = 960


def params(_param) -> list[str]:
    return [_param("Boolean", "slgOn", "吊り点の印と Max の表示", 1),
            _param("Length", "slgH", "吊りしろ（フックから吊り点）", 6.0),
            _param("Length", "mkZ", "吊り点の高さ（ホットスポット）", 0.0)]


def model(x: str, y: str, z: str, cap: str, tail: str = "", gate: str = "1") -> str:
    """3D: 印と文字とホットスポット. x・y・z はフックの位置の式（部品の原点から）、cap は定格総荷重×安全率の式."""
    h = HOTSPOT_3D
    return f"""! 吊り点の印（丸十字）と Max（scripts/gdl_mark.py）
if slgOn and ({gate}) then
	define material "mk_red" 2, 0.90, 0.10, 0.10
	define style "mkI" "Arial", 900 * texZ, 4, 0
	mkX = {x}
	mkY = {y}
	mkH = {z}
	mkQ = mkH - slgH
	mkR = texZ
	mkV = {cap}
	material "mk_red"
	lin_ mkX, mkY, mkH, mkX, mkY, mkQ
	aV = 0
	dxV = GLOB_EYEPOS_X - SYMB_POS_X
	dyV = GLOB_EYEPOS_Y - SYMB_POS_Y
	if abs(dxV) > 0.01 then aV = atn(dyV / dxV) + 180 * (dxV < 0)
	aV = aV - SYMB_ROTANGLE + 90
	add mkX, mkY, mkQ
	! 丸十字は水平に寝かせる（利用者の指定 2026-11-07）。文字だけ視点へ向ける
	for k = 0 to 24
		put mkR * cos(15 * k), mkR * sin(15 * k), 15 - 16 * (k = 24)
	next k
	for k = 0 to 24
		put mkR * 0.82 * cos(15 * k), mkR * 0.82 * sin(15 * k), 15 - 16 * (k = 24)
	next k
	prism_ nsp / 3, 0.03, get(nsp)
	add -mkR, -mkR * 0.05, 0
	block mkR * 2, mkR * 0.1, 0.03
	del 1
	add -mkR * 0.05, -mkR, 0
	block mkR * 0.1, mkR * 2, 0.03
	del 1
	rotz aV
	rotx 90
	style "mkI"
	add mkR * 1.3, 0, 0
	if mkV > 0 then
		text 0.02, 0, "Max " + str(mkV, 4 + (mkV >= 10) + (mkV >= 100), 2) + "t"{tail}
	else
		text 0.02, 0, "Max -"
	endif
	del 4
	hotspot 0, mkY, mkQ, {h}, hfX, 1 + 128
	hotspot mkX, mkY, mkQ, {h + 1}, hfX, 2
	hotspot -1, mkY, mkQ, {h + 2}, hfX, 3 + 128
	hotspot mkX, 0, mkQ, {h + 3}, hfY, 1 + 128
	hotspot mkX, mkY, mkQ, {h + 4}, hfY, 2
	hotspot mkX, -1, mkQ, {h + 5}, hfY, 3 + 128
	! 上下は丸十字の少し上の点で（同じ点に重ねると X・Y と一緒に編集になり、高さが書き戻された。実機 2026-11-07）
	hotspot mkX, mkY, mkR * 1.5, {h + 6}, mkZ, 1 + 128
	hotspot mkX, mkY, mkQ + mkR * 1.5, {h + 7}, mkZ, 2
	hotspot mkX, mkY, mkR * 1.5 - 1, {h + 8}, mkZ, 3 + 128
endif
"""


def plan(x: str, y: str, pen: str, gate: str = "1") -> str:
    """2D: フックの真下の丸十字（平面のフックのホットスポットがそのまま効く）."""
    return f"""! 吊り点の印（scripts/gdl_mark.py）
if slgOn and ({gate}) then
	pen {pen}
	line_type 1
	mkR = texSiz * GLOB_SCALE / 1000 * 0.7
	circle2 {x}, {y}, mkR
	line2 {x} - mkR, {y}, {x} + mkR, {y}
	line2 {x}, {y} - mkR, {x}, {y} + mkR
endif
"""


def vl(height: str, write: str, gate: str = "1") -> str:
    """パラメータスクリプト: 印を上下に引いたらフックへ（write は mkZ からフックの値を入れる文）、ほかは印の高さを今のフックに合わせる."""
    return f"""! 吊り点の印（scripts/gdl_mark.py）
hideparameter "mkZ"
if {gate} then
	if GLOB_MODPAR_NAME = "mkZ" then
		{write}
	else
		if abs(mkZ - ({height} - slgH)) > 0.001 then parameters mkZ = {height} - slgH
	endif
else
	hideparameter "slgOn", "slgH"
endif
values "slgH" range [0, ]
"""
