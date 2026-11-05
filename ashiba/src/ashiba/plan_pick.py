"""平面に引いた線から面と位置を読む（配置の控え plan.json の面で。利用者の指定 2026-10-24: 階段の位置・区切る・面の切替も
平面に線を引いて決められるように）.

- 面に沿った線（along）: 面と、面の始点から線の両端までの位置。階段の位置・面の切替に使う
- 面を横切る線（across）: 面と、線が足場の帯を横切る位置。区切るに使う
面の座標は plan.json の start_post・end_post（内側建地列の始点・終点）、帯は内側建地列 0〜外側建地列 −rowW。
"""

from __future__ import annotations

import math
from typing import Optional

NEAR_MM = 1500.0          # 帯の外へ拾う幅（躯体側・外側）


def frame(e: dict) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], float]:
    """面の (始点, 向き u, 躯体側の法線 n, 長さ)."""
    (sx, sy), (ex, ey) = e["start_post"], e["end_post"]
    ln = math.hypot(ex - sx, ey - sy) or 1.0
    ux, uy = (ex - sx) / ln, (ey - sy) / ln
    return (sx, sy), (ux, uy), (-uy, ux), ln


def spans_of(e: dict) -> list[float]:
    """面のスパン（gdl_params の spanList・spanList2。無ければ spans）."""
    g = e.get("gdl_params") or {}
    out = []
    for key in ("spanList", "spanList2"):
        for t in str(g.get(key) or "").split(","):
            t = t.strip()
            if t:
                out.append(float(t))
    return out or [float(s) for s in e.get("spans") or []]


def row_of(e: dict) -> float:
    return float((e.get("gdl_params") or {}).get("rowW") or 0.914) * 1000.0


def posts_of(e: dict) -> list[float]:
    out = [0.0]
    for s in spans_of(e):
        out.append(out[-1] + s)
    return out


def _local(e: dict, p) -> tuple[float, float]:
    o, u, n, _ln = frame(e)
    dx, dy = p[0] - o[0], p[1] - o[1]
    return dx * u[0] + dy * u[1], dx * n[0] + dy * n[1]


def along(edges: list[dict], p1, p2) -> Optional[tuple[dict, float, float]]:
    """面に沿った線 → (面, 線の始まり, 線の終わり mm。面の始点から、面の中に丸める)。無ければ None."""
    if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 100.0:
        return None
    best = None
    for e in edges:
        (t1, n1), (t2, n2) = _local(e, p1), _local(e, p2)
        length = frame(e)[3]
        if abs(t2 - t1) < 0.9 * math.hypot(t2 - t1, n2 - n1):       # 面と平行（±25°）
            continue
        lo, hi = sorted((t1, t2))
        if hi < 0 or lo > length:
            continue
        d = abs((n1 + n2) / 2.0 + row_of(e) / 2.0)
        if d > row_of(e) / 2.0 + NEAR_MM:
            continue
        if best is None or d < best[0]:
            best = (d, e, max(0.0, lo), min(length, hi))
    return None if best is None else best[1:]


def across(edges: list[dict], p1, p2) -> Optional[tuple[dict, float]]:
    """面を横切る線 → (面, 線が帯の中ほどを横切る位置 mm)。無ければ None."""
    best = None
    for e in edges:
        (t1, n1), (t2, n2) = _local(e, p1), _local(e, p2)
        length = frame(e)[3]
        mid = -row_of(e) / 2.0
        if (n1 - mid) * (n2 - mid) > 0 or abs(n2 - n1) < 1.0:     # 帯の中ほどの線をまたがない
            continue
        if abs(n2 - n1) < 0.5 * math.hypot(t2 - t1, n2 - n1):     # 面に直交に近い（±60°）
            continue
        t = t1 + (t2 - t1) * (mid - n1) / (n2 - n1)
        if not (0.0 <= t <= length):
            continue
        reach = max(abs(n1 - mid), abs(n2 - mid))
        if best is None or reach < best[0]:
            best = (reach, e, t)
    return None if best is None else best[1:]


def nearest_post(e: dict, t: float, inner_only: bool = True) -> float:
    """位置 t にいちばん近い支柱（inner_only なら面の両端の支柱を除く）."""
    posts = posts_of(e)
    if inner_only and len(posts) > 2:
        posts = posts[1:-1]
    return min(posts, key=lambda p: abs(p - t))


def spans_covered(e: dict, t0: float, t1: float) -> tuple[float, int]:
    """線の区間 [t0, t1] が半分以上かかるスパン → (始めの支柱の位置, スパン数)。かからなければいちばん近い1スパン."""
    posts = posts_of(e)
    hit = [i for i in range(len(posts) - 1)
           if min(t1, posts[i + 1]) - max(t0, posts[i]) >= 0.5 * (posts[i + 1] - posts[i])]
    if not hit:
        mid = (t0 + t1) / 2.0
        i = min(range(len(posts) - 1), key=lambda k: abs((posts[k] + posts[k + 1]) / 2.0 - mid))
        return posts[i], 1
    return posts[hit[0]], hit[-1] - hit[0] + 1
