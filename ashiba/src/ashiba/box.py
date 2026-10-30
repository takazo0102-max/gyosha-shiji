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
DEFAULT_LEVELS = 4
AXIS_TOL_DEG = 2.0


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
            "row_mm": float(params.get("rowW") or 0.914) * 1000.0,
            "standoff": float(params.get("standoff") or 0.3) * 1000.0,
            "floor_mm": float(params.get("floorH") or 1.8) * 1000.0,
            "series_id": str(params.get("seriesId") or "")}


def width_nominal(row_mm: float) -> int:
    """箱の足場の幅（内外の建地の間 610・914・1219）→ 条件の足場の幅（600・900・1200）."""
    return min((600, 900, 1200), key=lambda w: abs(w - row_mm * 900.0 / 914.0))


def box_params(sx: list[int], sy: list[int], coins: list[int], row_mm: float, levels: int, lev1_mm: float,
               floor_mm: float, series_id: str, standoff: float, pens: Optional[dict] = None) -> dict:
    """部品 ashiba_box に入れるパラメータ（m）."""
    out = {"spanX": ",".join(str(int(v)) for v in sx), "spanY": ",".join(str(int(v)) for v in sy),
           "szList": ",".join(str(int(c)) for c in sorted({int(c) for c in coins}, reverse=True)),
           "lenX": sum(sx) / 1000.0, "lenY": sum(sy) / 1000.0, "rowW": row_mm / 1000.0, "nLev": int(levels),
           "lev1": lev1_mm / 1000.0, "floorH": floor_mm / 1000.0,
           "topEdit": (lev1_mm + (levels - 1) * floor_mm) / 1000.0, "seriesId": series_id, "standoff": standoff / 1000.0}
    out.update(pens or {})
    return out
