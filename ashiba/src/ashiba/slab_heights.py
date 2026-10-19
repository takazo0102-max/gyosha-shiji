"""スラブの高さから足場の高さを決める（面ごと。セットバック対応）.

利用者の指定（2026-10-20）: 軒高を手で入れる代わりにスラブの天端を読む。セットバックがあるので面ごとに決め、
引っ込んだ上の部分は「上のスラブを選んでもう一度実行」で下の屋根の上から建てる。高さは天端＋手すり分。

- 面の軒高: 面に沿って内側（躯体側）へ少し入った点を並べ、その点を含むスラブのいちばん高い天端。
  上の階が引っ込んでいれば、その面の点は上のスラブに入らないので下の屋根の高さになる。
- 足場の立つ高さ（base）: 面の外側（建地の下）の点を含むスラブのうち、面の軒高より十分低いものの天端。
  上の部分だけを選んで実行したとき、下の屋根の上に立つ。外側にスラブが無ければ地盤（0）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

INSIDE_MM = 200.0        # 面から躯体側へ入った点（スラブの縁ぴったりを避ける）
SAMPLE_PITCH_MM = 1000.0  # 面に沿って点を並べる間隔
BASE_CLEAR_MM = 1000.0    # 立つ面とみなすスラブは、面の軒高よりこれ以上低いもの


@dataclass
class SlabInfo:
    polygon: list[tuple[float, float]]   # mm
    top_mm: float                        # 天端の高さ（プロジェクトの0から mm）


def slab_top_mm(details: dict) -> Optional[float]:
    """Tapir GetDetailsOfElements のスラブ詳細 → 天端の高さ（mm）。基準面が上端以外なら厚さで直す."""
    d = details.get("details", details)
    z = d.get("zCoordinate")
    if z is None:
        return None
    z = float(z) * 1000.0
    ref = str(d.get("referencePlaneLocation", "Top"))
    t = float(d.get("thickness", 0.0) or 0.0) * 1000.0
    if ref == "Bottom":
        return z + t
    return z


def slabs_from_details(details: Iterable[dict]) -> list[SlabInfo]:
    out = []
    for det in details:
        d = det.get("details", det)
        poly = [(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for p in d.get("polygonOutline") or []]
        top = slab_top_mm(det)
        if len(poly) >= 3 and top is not None:
            if poly[0] == poly[-1]:
                poly = poly[:-1]
            out.append(SlabInfo(poly, top))
    return out


def _inside(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = pt
    n = len(poly)
    c = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            c = not c
        j = i
    return c


def _samples(edge, offset_mm: float) -> list[tuple[float, float]]:
    """面（躯体の辺）に沿った点。offset_mm は外向き法線の向きへのずらし（負なら躯体側）."""
    (sx, sy), (ex, ey) = edge.start, edge.end
    length = abs(ex - sx) + abs(ey - sy)
    if length <= 0:
        return []
    n = max(1, int(length // SAMPLE_PITCH_MM))
    ox, oy = edge.outward
    pts = []
    for k in range(n + 1):
        t = (k + 0.5) / (n + 1)
        pts.append((sx + (ex - sx) * t + ox * offset_mm, sy + (ey - sy) * t + oy * offset_mm))
    return pts


def face_eaves_mm(edges, slabs: list[SlabInfo]) -> dict[int, float]:
    """面ごとの軒高（面の内側の点を含むスラブのいちばん高い天端）。スラブが無い面は入れない."""
    out: dict[int, float] = {}
    for e in edges:
        tops = [s.top_mm for p in _samples(e, -INSIDE_MM) for s in slabs if _inside(p, s.polygon)]
        if tops:
            out[e.index] = max(tops)
    return out


def face_base_mm(edges, slabs: list[SlabInfo], eaves: dict[int, float], out_mm: float) -> dict[int, float]:
    """面ごとの足場の立つ高さ（面の外側 out_mm の点を含む、軒高より十分低いスラブの天端。無ければ0）."""
    out: dict[int, float] = {}
    for e in edges:
        top = eaves.get(e.index)
        if top is None:
            continue
        cands = [s.top_mm for p in _samples(e, out_mm) for s in slabs
                 if _inside(p, s.polygon) and s.top_mm < top - BASE_CLEAR_MM]
        out[e.index] = max(cands) if cands else 0.0
    return out
