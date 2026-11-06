"""クレーンの平面の「作業半径の表示」（SCP の「クレーン設定」の平面の表示。利用者の指定 2026-11-07「これも機能追加して」）.

ラフター（ashiba_crane）・クローラ（ashiba_machine の mcKind 2）・タワー（ashiba_tower）で同じものを使う。
1 項目は 半径 wiR・角度範囲 wiA〜wiB（0°＝部品の +X＝車体の前。ブームを旋回しても動かない）・文字反転 wiF。
弧と中心からの線を描き、線に沿って「作業半径 10.0m × 1.30ton」と書く（ton は今のブームの定格総荷重×安全率）。
ホットスポットは弧の中央で半径、弧の両端で範囲の端、線の途中（wiM）で範囲ごと回す。パラメータスクリプトが wiM を両端に書き戻す。
文字は読める向きに自動で向け、wiF でさらに 180° 返す。文字色は wiPen（0＝線のペン）。
"""

from __future__ import annotations

MAX_ITEMS = 5
HOTSPOT_BASE = 900
RADII = (10.0, 15.0, 20.0, 25.0, 30.0)
HALF = (10.0, 10.0, 30.0, 30.0, 30.0)
ITEM_PARAMS = ("wiR", "wiA", "wiB", "wiF")


def params(_param) -> list[str]:
    """パラメータ（既定は表示数 1。SCP の見本の ±10°・±10°・±30° にならう）."""
    out = [_param("Integer", "wiNum", "作業半径の表示数（0〜5）", 1),
           _param("PenColor", "wiPen", "作業半径の文字色（0＝線のペン）", 0)]
    for i in range(1, MAX_ITEMS + 1):
        h = HALF[i - 1]
        out += [_param("Length", f"wiR{i}", f"{i}. 作業半径", RADII[i - 1]),
                _param("Angle", f"wiA{i}", f"{i}. 角度範囲の始め（0°＝車体の前）", -h),
                _param("Angle", f"wiB{i}", f"{i}. 角度範囲の終わり", h),
                _param("Angle", f"wiM{i}", f"{i}. 範囲の中央（ホットスポット）", 0.0),
                _param("Boolean", f"wiF{i}", f"{i}. 文字反転", 0)]
    return out


def master(gate: str = "1") -> str:
    """マスタースクリプト: 項目を配列に（wiSq＝範囲の幅、wiMq＝中央）. gate が偽なら表示しない."""
    n = MAX_ITEMS
    rows = [f"! 作業半径の表示（scripts/gdl_radii.py）", f"nWi = max(0, min({n}, wiNum)) * ({gate})",
            f"dim wiRq[{n}], wiAq[{n}], wiBq[{n}], wiSq[{n}], wiMq[{n}], wiFq[{n}], wiTq[{n}]"]
    for i in range(1, n + 1):
        rows += [f"wiRq[{i}] = wiR{i}", f"wiAq[{i}] = wiA{i}", f"wiBq[{i}] = wiB{i}", f"wiFq[{i}] = wiF{i}"]
    rows += [f"for wq = 1 to {n}", "\twS0 = wiBq[wq] - wiAq[wq] + 720", "\twS0 = wS0 - int(wS0 / 360) * 360",
             "\tif wS0 < 0.01 then wS0 = 360", "\twiSq[wq] = wS0", "\twiMq[wq] = wiAq[wq] + wS0 / 2", "next wq"]
    return "\n".join(rows) + "\n"


def rated_loop(body: str) -> str:
    """項目ごとの定格（wiRq[wq] の半径の値を vq に入れる body を回す）."""
    return "for wq = 1 to nWi\n\tvq = 0\n" + body + "\twiTq[wq] = vq\nnext wq\n"


LABEL = """wVr = wiRq[{i}]
wVt = wiTq[{i}]
wTx = "作業半径 " + str(wVr, 3 + (wVr >= 10) + (wVr >= 100), 1) + "m × 定格なし"
if wVt > 0 then wTx = "作業半径 " + str(wVr, 3 + (wVr >= 10) + (wVr >= 100), 1) + "m × " + str(wVt, 4 + (wVt >= 10) + (wVt >= 100), 2) + "ton"
"""


def plan(line_pen: str, solid: str, text_pen: str, back_style: str) -> str:
    """2D: 弧・線・文字とホットスポット. 線はペン line_pen・線種 solid、文字色の既定は text_pen、終わったら style back_style に戻す."""
    rows = ['! 作業半径の表示（弧と線と文字。scripts/gdl_radii.py）', "if nWi > 0 then",
            '\tdefine style "wiS" "ＭＳ Ｐゴシック", texSiz, 8, 0',
            "\tdrawindex 50", "\tline_type " + solid, "endif",
            "for wq = 1 to nWi", "\twRr = wiRq[wq]", "\twAm = wiMq[wq]", "\tpen " + line_pen,
            "\tif wiSq[wq] >= 359.9 then", "\t\tcircle2 0, 0, wRr", "\telse",
            "\t\tarc2 0, 0, wRr, wiAq[wq], wiAq[wq] + wiSq[wq]", "\tendif",
            "\tline2 0, 0, wRr * cos(wAm), wRr * sin(wAm)",
            "\twVr = wRr", "\twVt = wiTq[wq]",
            '\twTx = "作業半径 " + str(wVr, 3 + (wVr >= 10) + (wVr >= 100), 1) + "m × 定格なし"',
            '\tif wVt > 0 then wTx = "作業半径 " + str(wVr, 3 + (wVr >= 10) + (wVr >= 100), 1) + "m × " '
            '+ str(wVt, 4 + (wVt >= 10) + (wVt >= 100), 2) + "ton"',
            "\t! 読める向き（図面の上で左へ倒れない）に向け、文字反転でさらに 180°",
            "\twAt = wAm + SYMB_ROTANGLE + 1080", "\twAt = wAt - int(wAt / 360) * 360",
            "\twFl = (wAt > 90 and wAt <= 270)", "\tif wiFq[wq] then wFl = 1 - wFl",
            "\tpen " + text_pen, "\tif wiPen > 0 then pen wiPen", '\tstyle "wiS"',
            "\tadd2 wRr * 0.5 * cos(wAm), wRr * 0.5 * sin(wAm)", "\trot2 wAm + 180 * wFl",
            "\ttext2 0, texSiz * GLOB_SCALE / 1000 * 0.3, wTx", "\tdel 2", "next wq",
            "if nWi > 0 then", '\tstyle "' + back_style + '"', "\tpen " + line_pen, "endif"]
    for i in range(1, MAX_ITEMS + 1):
        b = HOTSPOT_BASE + (i - 1) * 12
        rows += [f"if nWi >= {i} then", f"\twRr = wiRq[{i}]", f"\twAm = wiMq[{i}]",
                 f"\thotspot2 0, 0, {b}, wiR{i}, 1 + 128",
                 f"\thotspot2 wRr * cos(wAm), wRr * sin(wAm), {b + 1}, wiR{i}, 2",
                 f"\thotspot2 -cos(wAm), -sin(wAm), {b + 2}, wiR{i}, 3",
                 f"\thotspot2 0, 0, {b + 3}, wiA{i}, 6", f"\thotspot2 wRr, 0, {b + 4}, wiA{i}, 4",
                 f"\thotspot2 wRr * cos(wiA{i}), wRr * sin(wiA{i}), {b + 5}, wiA{i}, 5",
                 f"\thotspot2 0, 0, {b + 6}, wiB{i}, 6", f"\thotspot2 wRr, 0, {b + 7}, wiB{i}, 4",
                 f"\thotspot2 wRr * cos(wiB{i}), wRr * sin(wiB{i}), {b + 8}, wiB{i}, 5",
                 f"\thotspot2 0, 0, {b + 9}, wiM{i}, 6", f"\thotspot2 wRr * 0.75, 0, {b + 10}, wiM{i}, 4",
                 f"\thotspot2 wRr * 0.75 * cos(wAm), wRr * 0.75 * sin(wAm), {b + 11}, wiM{i}, 5", "endif"]
    return "\n".join(rows) + "\n"


def vl(gate: str = "1") -> str:
    """パラメータスクリプト: 範囲の中央を引いたら両端へ書き戻す。表示数より後ろの項目は隠す."""
    n = MAX_ITEMS
    rows = ["! 作業半径の表示（scripts/gdl_radii.py）", f'values "wiNum" range [0, {n}]', "wMp = GLOB_MODPAR_NAME"]
    for i in range(1, n + 1):
        rows += [f'values "wiR{i}" range [0.5, ]', f'if wMp = "wiM{i}" then',
                 f"\tparameters wiA{i} = wiM{i} - wiSq[{i}] / 2, wiB{i} = wiM{i} + wiSq[{i}] / 2", "else",
                 f"\tif abs(wiM{i} - wiMq[{i}]) > 0.001 then parameters wiM{i} = wiMq[{i}]", "endif",
                 f'hideparameter "wiM{i}"', f"if nWi < {i} then",
                 f'\thideparameter "wiR{i}", "wiA{i}", "wiB{i}", "wiF{i}"', "endif"]
    rows += [f"if ({gate}) = 0 then", '\thideparameter "wiNum", "wiPen"', "endif"]
    return "\n".join(rows) + "\n"


def ui(gate: str = "1") -> str:
    """設定の窓のページ（SCP の「クレーン設定」にならう。表示数の分だけ行を出す）."""
    rows = ["﻿! クレーン設定: 作業半径の表示（scripts/gdl_radii.py）", 'ui_dialog "クレーン設定", 444, 266', f"if ({gate}) then",
            'ui_outfield "平面の作業半径の表示", 12, 8, 300, 18', 'ui_outfield "表示数", 12, 32, 60, 18',
            'ui_infield "wiNum", 76, 30, 50, 20', 'ui_outfield "半径", 186, 32, 60, 18',
            'ui_outfield "角度範囲", 250, 32, 120, 18', 'ui_outfield "文字反転", 376, 32, 60, 18']
    for i in range(1, MAX_ITEMS + 1):
        y = 30 + i * 28
        rows += [f"if nWi >= {i} then", LABEL.format(i=i).rstrip("\n"), f'ui_outfield "{i}. " + strsub(wTx, 6, 40), 12, {y + 2}, 170, 18',
                 f'ui_infield "wiR{i}", 186, {y}, 60, 20', f'ui_infield "wiA{i}", 250, {y}, 60, 20',
                 f'ui_infield "wiB{i}", 314, {y}, 60, 20', f'ui_infield "wiF{i}", 392, {y}, 20, 20', "endif"]
    rows += ['ui_outfield "文字色", 12, 206, 60, 18', 'ui_infield "wiPen", 76, 204, 60, 20',
             'ui_outfield "吊りしろ", 186, 206, 60, 18', 'ui_infield "slgH", 250, 204, 60, 20',
             'ui_outfield "吊り点の印と Max", 318, 206, 100, 18', 'ui_infield "slgOn", 420, 204, 20, 20',
             'ui_outfield "0°は車体の前。平面の弧の中央で半径、両端で範囲、線の途中で範囲ごと回せます", 12, 234, 420, 18',
             "else", 'ui_outfield "クローラクレーンのときに使います", 12, 8, 300, 18', "endif"]
    return "\n".join(rows) + "\n"
