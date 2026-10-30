"""足場の箱（超簡易モード。部品 ashiba_box）: 四角い足場を伸び縮みして形を決め、ボタンで本体にする.

利用者の指定（2026-10-30）「超簡易モードになってない いきなり足場が現れた」「なんか違う 箱を作って自分で伸び縮みするような
感じ」→ 一周の箱（四角）・ボタンで本体にする。

- 箱を置く: 平面の線の始点を箱の角（内側の建地の列）に、線の長さを長手の初めの長さにする。部品の右の辺・上の辺の中ほどの
  つまみで伸び縮みし、長さは定尺の組み合わせに吸着する（部品のパラメータスクリプト。snap_spans は同じ決め方）。
- 箱を足場に: 箱の角・向き・スパン・段数を読み、内側の建地の列の一周（manual.solve_manual_loop）として足場一式に置き直す。
"""

from __future__ import annotations

import math
from typing import Optional

BOX_OBJECT = "ashiba_box"
BOX_MIN_SPAN_MM = 600     # 箱の吸着に使う定尺の下限（アルバトロスの 457 は端数の調整用で、先行手摺・シート・朝顔の合う品が無い）
DEFAULT_LEVELS = 4
AXIS_TOL_DEG = 2.0


def box_coins(coins: list[int]) -> list[int]:
    """箱の吸着に使う定尺（大きい順。BOX_MIN_SPAN_MM 未満は使わない。それしか無ければそのまま）."""
    big = sorted({int(c) for c in coins if c >= BOX_MIN_SPAN_MM}, reverse=True)
    return big or sorted({int(c) for c in coins}, reverse=True)


def snap_spans(length_mm: float, coins: list[int]) -> list[int]:
    """長さ → 定尺の最大を n 本並べ、端数を定尺 0〜2 本で埋めた並び（いちばん近い組。同じ近さなら本数の少ない方）.
    部品 ashiba_box のパラメータスクリプト（つまみで引いたとき）と同じ決め方."""
    sz = sorted({int(c) for c in coins if c > 100}, reverse=True)
    if not sz:
        raise ValueError("定尺がありません")
    mx = sz[0]
    best = None
    for n in range(0, int(length_mm // mx) + 2):
        for i in range(0, len(sz) + 1):
            for j in range(i, len(sz) + 1):
                s = sz[i - 1] if i > 0 else 0
                t = sz[j - 1] if j > 0 else 0
                tot = n * mx + s + t
                if tot <= 100:
                    continue
                d = abs(tot - length_mm) + 0.1 * (n + (i > 0) + (j > 0))
                if best is None or d < best[0]:
                    best = (d, [mx] * n + [v for v in (s, t) if v])
    return best[1]


def box_loop(origin_mm: tuple[float, float], angle_rad: float, sx: list[int], sy: list[int]
             ) -> tuple[list[tuple[float, float]], list[list[int]]]:
    """箱の角（内側の建地の列の角）・向き・スパン → 内側の建地の列の一周の点（左回り）と辺ごとのスパン.

    足場は平面の縦・横にしか組まないので、向きは 90° の倍数（±2°）に限る。"""
    deg = math.degrees(angle_rad) % 360.0
    k = round(deg / 90.0) % 4
    if abs(deg - 90.0 * round(deg / 90.0)) > AXIS_TOL_DEG:
        raise ValueError(f"箱が斜め（{deg:.1f}°）です。足場は平面の縦・横に組むので、箱は 0・90・180・270° の向きにしてください")
    u = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)][k]
    v = (-u[1], u[0])
    lx, ly = float(sum(sx)), float(sum(sy))
    x0, y0 = origin_mm
    pts = [(x0, y0), (x0 + u[0] * lx, y0 + u[1] * lx),
           (x0 + u[0] * lx + v[0] * ly, y0 + u[1] * lx + v[1] * ly), (x0 + v[0] * ly, y0 + v[1] * ly)]
    return pts, [list(sx), list(sy), list(reversed(sx)), list(reversed(sy))]


def parse_box_params(params: dict) -> dict:
    """部品のパラメータ（GetGDLParametersOfElements の名前→値）→ スパン（mm）・段数・幅・離れ・系列."""
    from .manual import parse_spans

    sx = parse_spans(str(params.get("spanX") or ""))
    sy = parse_spans(str(params.get("spanY") or ""))
    if not sx or not sy:
        raise ValueError("箱のスパンが読めません（spanX・spanY）")
    return {"sx": sx, "sy": sy, "levels": max(1, int(float(params.get("nLev") or DEFAULT_LEVELS))),
            "thick_mm": snap_thickness(float(params.get("thick") or 0.9) * 1000.0),
            "base_mm": max(0.0, float(params.get("zBase") or 0.0) * 1000.0),
            "standoff": float(params.get("standoff") or 0.3) * 1000.0,
            "floor_mm": float(params.get("floorH") or 1.8) * 1000.0,
            "series_id": str(params.get("seriesId") or "")}


THICKNESSES = (300, 600, 900, 1200)   # 箱の厚み（部品が吸着する値）: 300＝一側足場、600／900／1200＝本足場の幅


def snap_thickness(t_mm: float) -> int:
    return min(THICKNESSES, key=lambda t: abs(t - t_mm))


def thickness_conditions(t_mm: float, standoff: float) -> tuple[str, dict]:
    """箱の厚み → (種類の名前, 解く条件). 利用者の指定 2026-10-30: 厚みで種類も変える.

    300 は一側足場。本足場が入らない狭い所の足場なので、使える幅を「離れ＋厚み＋100」とする（ブラケットの出 360 は収まり、
    本足場の幅 610 は収まらない。安衛則561条の2 の本足場原則のただし書き）。600・900・1200 は幅 610・914・1219 の本足場。"""
    t = snap_thickness(t_mm)
    if t == 300:
        return "一側足場", {"scaffold_form": "一側足場", "clearance_space_mm": standoff + t + 100.0}
    return f"本足場 幅{t}", {"scaffold_form": "本足場", "scaffold_width_mm": t}


def width_nominal(row_mm: float) -> int:
    """足場の幅（内外の建地の間 610・914・1219）→ 条件の足場の幅（600・900・1200）."""
    return min((600, 900, 1200), key=lambda w: abs(w - row_mm * 900.0 / 914.0))


def box_params(sx: list[int], sy: list[int], coins: list[int], thick_mm: float, levels: int, lev1_mm: float,
               floor_mm: float, series_id: str, standoff: float, pens: Optional[dict] = None,
               base_mm: float = 0.0) -> dict:
    """部品 ashiba_box に入れるパラメータ（m）."""
    out = {"spanX": ",".join(str(int(v)) for v in sx), "spanY": ",".join(str(int(v)) for v in sy),
           "szList": ",".join(str(int(c)) for c in sorted({int(c) for c in coins}, reverse=True)),
           "lenX": sum(sx) / 1000.0, "lenY": sum(sy) / 1000.0, "thick": snap_thickness(thick_mm) / 1000.0,
           "nLev": int(levels),
           "lev1": lev1_mm / 1000.0, "floorH": floor_mm / 1000.0,
           "topEdit": (lev1_mm + (levels - 1) * floor_mm) / 1000.0, "seriesId": series_id, "standoff": standoff / 1000.0,
           "zBase": max(0.0, base_mm) / 1000.0}
    out.update(pens or {})
    return out


def contains(outer_pts: list, inner_pts: list, tol: float = 1.0) -> bool:
    """箱の内側の建地の列（四角）inner が outer の中（辺の上も含む）にあるか."""
    xs, ys = [p[0] for p in outer_pts], [p[1] for p in outer_pts]
    return all(min(xs) - tol <= p[0] <= max(xs) + tol and min(ys) - tol <= p[1] <= max(ys) + tol for p in inner_pts)


def setback_spec(low: dict, uppers: list[dict], extra: dict) -> dict:
    """下の箱と、その中に立つ高さを上げて重ねた上の階の箱 → 下の足場と上段をつないで一度に解く条件.

    利用者の指定（2026-10-30）「下の足場と上段をつなげて」。建物の床から解くセットバック（setback_tiers）と同じ形にする:
    下の箱の内側を途中の屋根の床（天端＝上の箱の立つ高さ）、上の箱の内側を上の階の床（天端＝立つ高さ＋その箱の高さ）とし、
    本体は下の箱のスパン・離れで解く。上の階の面が下の箱の面にそろう所は本体の足場がそのまま上まで上がり、下がった面は屋根の
    上から上段の足場を建てて端を本体の支柱に乗せる。本体から途中の屋根へは屋上への渡りを付ける。low・uppers は {"pts", "sides", "standoff", "base_mm", "levels", "floor_mm"}."""
    from .manual import eaves_for_levels, loop_building

    outline, ms = loop_building(low["pts"], low["sides"], low["standoff"])
    roof = min(u["base_mm"] for u in uppers)
    slabs = [{"polygon_mm": outline, "top_mm": roof, "thickness_mm": 200.0}]
    for u in uppers:
        ol, _ = loop_building(u["pts"], u["sides"], u["standoff"])
        slabs.append({"polygon_mm": ol, "top_mm": u["base_mm"] + eaves_for_levels(u["levels"], int(u["floor_mm"])),
                      "thickness_mm": 200.0})
    so = float(low["standoff"])
    return {**extra, "outline_mm": outline, "eaves_height_mm": roof, "slabs": slabs,
            "span_overrides": [{"edge_index": i, "spans_mm": sp} for i, sp in enumerate(ms)],
            "standoff": {"target": so, "min": so, "max": so, "hard_min": so},
            # 屋根は利用者が箱で決めた本物の屋根なので、本体の足場から途中の屋根へ・上段から上の階の屋根へ渡る（上の箱が
            # 下の箱の内側に収まって面がそろわないときも、本体から屋根へ渡って上段へ行ける）
            "height_from_slabs": True, "avoid_obstacles": True, "roof_bridge": True}
