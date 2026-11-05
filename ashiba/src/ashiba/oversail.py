"""旋回の円と敷地境界（ジブ・カウンタウエイトが敷地の外へ出る辺。タワークレーン・クレーンのオーバースイング）.

敷地境界は mm の多角形（足場条件の site_boundary_mm か Archicad の境界線）、road_edges は道路に面した辺の番号。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Over:
    edge: int                    # 辺の番号（0 から）
    road: bool                   # 道路に面した辺
    dist: float                  # 旋回の中心から辺まで mm
    over: float                  # 辺の外へ出る長さ mm（半径 − 距離）


def seg_dist(p: tuple, a: tuple, b: tuple) -> float:
    """点 p から線分 a-b までの距離."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    L2 = ex * ex + ey * ey
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / L2))
    return math.hypot(p[0] - (a[0] + t * ex), p[1] - (a[1] + t * ey))


def inside(p: tuple, poly: list) -> bool:
    """多角形の内側か（偶奇判定）."""
    x, y = p
    n = len(poly)
    c = False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def oversail(center: tuple, radius_mm: float, boundary: list, roads: set | None = None) -> list[Over]:
    """半径 radius_mm の旋回の円が敷地境界の外へ出る辺（中心が敷地の外なら全部の辺を返す）."""
    if len(boundary) < 3 or radius_mm <= 0:
        return []
    roads = roads or set()
    ins = inside(center, boundary)
    out = []
    for i in range(len(boundary)):
        d = seg_dist(center, boundary[i], boundary[(i + 1) % len(boundary)])
        if not ins or d < radius_mm:
            out.append(Over(i, i in roads, d, radius_mm - d if ins else radius_mm + d))
    return out
