"""部品の平面図を CAD の平面図の描き方にそろえる共通の決め（利用者の指定 2026-11-04「今まで作ったものを平面図は CAD の平面図
レベルにできる？」→ 1/100 と 1/200 の両方、重機・搬入車両・クレーンから）.

決め（建築製図の線の使い分け。JIS Z 8114・A 0150 の線の種類と太さの考え方に、仮設計画図の習いを当てた）:
- 線の太さはペンで分ける: 外形（太線）＝penBold、細部（細線）＝penThin、範囲の線（作業半径・後端旋回半径・立入禁止・旋回軌跡）＝penZone。
  置くときは選んだペン（penEquip の色）と同じ色のペンからペンセットの太い・細いものを選ぶ（scripts/pen_colors.py の pen_weights）
- 線の種類はプロジェクトの線種の名前で選ぶ（無ければ実線）: 下に隠れるもの（車体の下のタイヤ・第5輪）＝破線、中心線・回転の中心＝
  一点鎖線、作業半径＝一点鎖線、後端旋回半径・旋回軌跡・立入禁止＝二点鎖線
- 縮尺で描き分ける（drMode 0 は自動）: 詳細 1/100 まで（タイヤ・履帯の板・運転室・窓・ミラー・ラチスの斜材）、標準 1/200 まで
  （外形と主な部材・タイヤは1本の箱）、簡略 それより小さい縮尺（外形・中心・範囲の線だけ）
- 上に載るもの（上部旋回体・荷台・積荷・トレーラー）は背景の色で塗って、下の線（履帯・別の要素）を隠す（penMask、0 は隠さない）。
  部品の中の重なりは drawindex（10 下・20 隠す塗り・30 上の外形・40 隠れ線と細部・50 文字）
- 文字は紙の上の mm（texSiz）。縮尺で大きさは変わらない
"""

from __future__ import annotations

from gen_hoist_gdl import _param

# 線種の名前（日本語のテンプレート・英語のテンプレート）
LINE_NAMES = {"ltH": ("破線", "Dashed"), "ltC": ("一点鎖線", "Dash-dotted", "Dash-dot"),
              "ltZ": ("二点鎖線", "Dash-double-dotted", "Dash-dot-dot")}


def params() -> list[str]:
    """部品の paramlist に足す描き方のパラメータ."""
    return [
        _param("PenColor", "penBold", "外形の線（太線。置くときに線のペンと同じ色の太いペン）", 21),
        _param("PenColor", "penThin", "細部の線（細線。同じ色の細いペン）", 1),
        _param("PenColor", "penZone", "範囲の線（作業半径・後端旋回半径・立入禁止・旋回軌跡）", 20),
        _param("PenColor", "penMask", "上に載るものの背景の塗り（下の線を隠す。0＝隠さない）", 19),
        _param("Integer", "drMode", "平面の描き分け（0 縮尺で自動・1 詳細 1/100・2 標準 1/200・3 簡略）", 0),
    ]


def values() -> str:
    """パラメータスクリプトに足す値の一覧."""
    return 'values{2} "drMode" 0, "縮尺で自動", 1, "詳細（1/100）", 2, "標準（1/200）", 3, "簡略"\n'


def head() -> str:
    """2D スクリプトの先頭: 描き分けの段（drLv）・ペン（pO 太・pT 細・pZ 範囲・pM 隠す塗り）・線種（ltS・ltH・ltC・ltZ）・塗り（fiS）."""
    out = ["! 描き方の決め（scripts/gdl_draft.py）",
           "drLv = drMode",
           "if drLv < 1 or drLv > 3 then",
           "\tdrLv = 1",
           "\tif GLOB_SCALE > 150 then drLv = 2",
           "\tif GLOB_SCALE > 250 then drLv = 3",
           "endif",
           "pO = penBold",
           "if pO < 1 then pO = penEquip",
           "pT = penThin",
           "if pT < 1 then pT = penEquip",
           "pZ = penZone",
           "if pZ < 1 then pZ = pT",
           "pM = penMask",
           "ltS = 1"]
    for var, names in LINE_NAMES.items():
        out.append(f"{var} = IND(LINE_TYPE, \"{names[0]}\")")
        for n in names[1:]:
            out.append(f"if {var} < 1 then {var} = IND(LINE_TYPE, \"{n}\")")
        out.append(f"if {var} < 1 then {var} = 1")
    out += ["fiS = IND(FILL, \"100 %\")",
            "if fiS < 1 then fiS = IND(FILL, \"Solid Fill\")",
            "mk = (pM > 0 and fiS > 0)"]
    return "\n".join(out) + "\n"


def mask(pts: list[tuple[str, str]], indent: str = "\t") -> str:
    """点（GDL の式の組）で囲んだ所を背景の色で塗る（輪郭は描かない）. 呼ぶ側で drawindex 20 と if mk then … endif."""
    rows = list(pts) + [pts[0]]
    lines = [f"{indent}fill fiS", f"{indent}poly2_b {len(rows)}, 6, pM, pM,"]
    for i, (x, y) in enumerate(rows):
        last = i == len(rows) - 1
        lines.append(f"{indent}\t{x}, {y}, {-1 if last else 1}" + ("" if last else ","))
    return "\n".join(lines) + "\n"


def rect_mask(x1: str, y1: str, x2: str, y2: str, indent: str = "\t") -> str:
    return mask([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], indent)


def arc_pts(r: str, a0: str, a1: str, n: int = 9) -> list[tuple[str, str]]:
    """半径 r の円弧（角度 a0 → a1。式）を n 点で."""
    return [(f"{r} * cos({a0} + ({a1} - ({a0})) * {k} / {n - 1})", f"{r} * sin({a0} + ({a1} - ({a0})) * {k} / {n - 1})")
            for k in range(n)]
