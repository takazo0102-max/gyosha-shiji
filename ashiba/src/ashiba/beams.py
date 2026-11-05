"""根切り底の地中梁（Archicad の梁）と、内部足場の支柱・仮設通路の取り合い.

利用者の指定（2026-10-30）「次足場はメッシュに根切り底と梁を置いてテストして」→ 根切り底に内部足場、梁を渡る仮設通路。
- 内部足場: 支柱が地中梁の上に乗ると、根切り底との段差（梁せい）で支柱の高さが合わない。乗る支柱を知らせ、割付をずらすか
  梁の上の支柱を短くする（ジャッキ・調整）
- 仮設通路: 梁をまたぐ所で、通路の下端（桁の下 120）と梁の上端のあき
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

WALKWAY_UNDER_MM = 120.0    # 通路の床の上端から桁の下端まで（ライトブリッジの桁。部品 ashiba_walkway の gH）
CLEAR_MIN_MM = 100.0        # 通路の下端と梁の上端のあき（これ未満は確かめる）


@dataclass
class Beam:
    a: tuple[float, float]       # 芯の始点（mm）
    b: tuple[float, float]       # 芯の終点
    width: float                 # 幅 mm
    top_mm: float                # 上端（プロジェクトの高さ mm）
    bottom_mm: float             # 下端


def beam_from_details(d: dict) -> Optional[Beam]:
    """Archicad の梁の詳細（GetDetailsOfElements の details）→ Beam。直線の梁だけ."""
    try:
        a, b = d["begCoordinate"], d["endCoordinate"]
        w = float(d.get("width") or 0.0) * 1000.0
        h = float(d.get("height") or 0.0) * 1000.0
        # zCoordinate はプロジェクトの原点からの基準線（上端合わせなら上端）の高さ。level は梁の属する階からの高さで、足すと
        # 二重になる（実機 2026-10-30: 基礎下端 −2000 の階の梁で上端 −1000 が 0 になった）
        z = float(d.get("zCoordinate") or 0.0) * 1000.0
    except (KeyError, TypeError, ValueError):
        return None
    if str(d.get("beamShape", "Straight")) != "Straight" or d.get("isSlanted"):
        return None
    anchor = str(d.get("anchorPoint") or "TopCenter")
    top = z if anchor.startswith("Top") else (z + h if anchor.startswith("Bottom") else z + h / 2.0)
    return Beam((float(a["x"]) * 1000.0, float(a["y"]) * 1000.0), (float(b["x"]) * 1000.0, float(b["y"]) * 1000.0),
                w, top, top - h)


def read_beams(client, near_mm: list, margin_mm: float = 3000.0) -> list[Beam]:
    """範囲（点の並び）の外接矩形＋margin に掛かる梁."""
    try:
        els = client.tapir("GetElementsByType", {"elementType": "Beam"}).get("elements", [])
    except Exception:
        return []
    if not els:
        return []
    xs, ys = [p[0] for p in near_mm], [p[1] for p in near_mm]
    x0, x1, y0, y1 = min(xs) - margin_mm, max(xs) + margin_mm, min(ys) - margin_mm, max(ys) + margin_mm
    out = []
    for d in client.get_details(els):
        bm = beam_from_details(d.get("details") or {})
        if bm is None:
            continue
        if max(bm.a[0], bm.b[0]) < x0 or min(bm.a[0], bm.b[0]) > x1 or max(bm.a[1], bm.b[1]) < y0 \
                or min(bm.a[1], bm.b[1]) > y1:
            continue
        out.append(bm)
    return out


def _dist_to_axis(p, bm: Beam) -> tuple[float, float]:
    """点 p の梁の芯からの距離と、芯に沿った位置（0〜長さ）."""
    dx, dy = bm.b[0] - bm.a[0], bm.b[1] - bm.a[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    t = (p[0] - bm.a[0]) * ux + (p[1] - bm.a[1]) * uy
    return abs((p[0] - bm.a[0]) * uy - (p[1] - bm.a[1]) * ux), t


def posts_on_beams(posts: list, beams: list[Beam], floor_mm: float, base_r_mm: float = 70.0) -> list[tuple]:
    """支柱（ジャッキの底板 140 角）が梁の上に掛かるもの → [(支柱, 梁)]. 床より 50 以上高い梁だけ."""
    out = []
    for p in posts:
        for bm in beams:
            if bm.top_mm <= floor_mm + 50.0:
                continue
            d, t = _dist_to_axis(p, bm)
            L = math.dist(bm.a, bm.b)
            if d <= bm.width / 2.0 + base_r_mm and -base_r_mm <= t <= L + base_r_mm:
                out.append((p, bm))
                break
    return out


def _inside(p, bm: Beam) -> bool:
    d, t = _dist_to_axis(p, bm)
    return d <= bm.width / 2.0 and 0.0 <= t <= math.dist(bm.a, bm.b)


def walkway_beam_checks(start, end, deck_abs_mm: float, end_deck_abs_mm: float, beams: list[Beam],
                        width_mm: float = 0.0, step_mm: float = 25.0) -> list[tuple[str, str]]:
    """仮設通路が梁の上を通る所の、通路の下端（床の上端−WALKWAY_UNDER_MM）と梁の上端のあき → [(状態, 文)].
    通路の幅（width_mm）の帯と梁の幅の帯の重なりで見る: 芯どうしの交点だけでは、梁の端を通路の縁がかすめる所・梁に沿って
    通る所を見落とし、勾配のある通路では梁の幅の中のいちばん低い所が交点とずれる."""
    L = math.dist(start, end)
    if L <= 0:
        return []
    ux, uy = (end[0] - start[0]) / L, (end[1] - start[1]) / L
    offs = (0.0,) if width_mm <= 0 else (-width_mm / 2.0, 0.0, width_mm / 2.0)
    n = max(1, int(math.ceil(L / step_mm)))
    out = []
    for bm in beams:
        hit = []
        for i in range(n + 1):
            s = L * i / n
            if any(_inside((start[0] + ux * s - uy * o, start[1] + uy * s + ux * o), bm) for o in offs):
                hit.append(s)
        if not hit:
            continue
        s0, s1 = hit[0], hit[-1]
        deck = min(deck_abs_mm + (end_deck_abs_mm - deck_abs_mm) * s / L for s in (s0, s1))
        gap = deck - WALKWAY_UNDER_MM - bm.top_mm
        st = "NG" if gap <= 0 else ("WARN" if gap < CLEAR_MIN_MM else "OK")
        where = f"始めから {s0:.0f}mm" if s1 - s0 < 1.0 else f"始めから {s0:.0f}〜{s1:.0f}mm"
        out.append((s0, st, f"{where} で梁（上端 {bm.top_mm:.0f}・幅 {bm.width:.0f}）の上を通る: 通路の下端 "
                            f"{deck - WALKWAY_UNDER_MM:.0f} と梁の上端のあき {gap:.0f}mm"
                        + ("" if st == "OK" else "（床を上げるか、通路の位置をずらす）")))
    return [(st, msg) for _s, st, msg in sorted(out, key=lambda x: x[0])]


LEDGER_HALF_MM = 24.3       # 布材・根がらみ（φ48.6）の半径


def grid_ledgers(origin, u, v, spans_u: list, spans_v: list) -> list[tuple[tuple, tuple]]:
    """升目の支柱の間の布材（両方向）の平面の線 → [(始め, 終わり)]."""
    cu, cv = [0.0], [0.0]
    for s in spans_u:
        cu.append(cu[-1] + s)
    for s in spans_v:
        cv.append(cv[-1] + s)
    pt = lambda a, b: (origin[0] + u[0] * a + v[0] * b, origin[1] + u[1] * a + v[1] * b)
    out = [(pt(cu[i], b), pt(cu[i + 1], b)) for b in cv for i in range(len(cu) - 1)]
    out += [(pt(a, cv[j]), pt(a, cv[j + 1])) for a in cu for j in range(len(cv) - 1)]
    return out


def _segment_hits(p, q, bm: Beam, step_mm: float = 25.0) -> bool:
    L = math.dist(p, q)
    n = max(1, int(math.ceil(L / step_mm)))
    return any(_inside((p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n), bm) for i in range(n + 1))


def ledgers_through_beams(ledgers: list, levels: list, beams: list[Beam], floor_mm: float) -> list[tuple[int, int, Beam]]:
    """梁の上端より低い段の布材（根がらみ）で、梁を横切るもの → [(段の高さ（足場の立つ面から）, 本数, 梁)].
    根切り底の地中梁は根がらみ・下の段の布材と当たる。その升目は梁の上の段で取るか、梁の手前で止めて単管でつなぐ."""
    out = []
    for bm in beams:
        top = bm.top_mm - floor_mm
        if top <= 50.0:
            continue
        low = [h for h in sorted(set(levels)) if h - LEDGER_HALF_MM < top and h + LEDGER_HALF_MM > bm.bottom_mm - floor_mm]
        if not low:
            continue
        n = sum(1 for p, q in ledgers if _segment_hits(p, q, bm))
        if n:
            out += [(int(h), n, bm) for h in low]
    return out


def ledger_clash_message(hits: list) -> Optional[tuple[str, str]]:
    """(状態, 文)。当たる布材が無ければ None."""
    if not hits:
        return None
    hs = sorted({h for h, _n, _b in hits})
    n = max(n for _h, n, _b in hits)
    top = max(b.top_mm for _h, _n, b in hits)
    return "WARN", (f"高さ {'・'.join(str(h) for h in hs)}mm の段の布材（根がらみ）が地中梁を横切る（各段 {n}本・梁の上端は"
                    f"プロジェクトの {top:.0f}）。その升目の布材は梁の上端より上のコマで取るか、梁の手前で止めて単管とクランプで"
                    "つなぐ（根がらみは梁の両側の支柱で2方向に取る）")


GROUND_STEP_WARN_MM = 30.0  # 支柱の足元の地盤の高さの差がこれを超えたら、ジャッキ・敷板で合わせる量を知らせる
GROUND_STEP_NG_MM = 250.0   # これを超える差はジャッキの繰出しの幅（30〜270 前後）で合わせきれない


def ground_spread(posts: list, ground, floor_mm: float) -> Optional[tuple[float, float]]:
    """支柱の足元の敷地メッシュの高さの、床（範囲の中央の高さ）からの (いちばん低い, いちばん高い) 差 mm.
    メッシュが無ければ None（根切り底の法面にかかる内部足場・仮設通路の島）."""
    if ground is None or getattr(ground, "is_flat", True):
        return None
    zs = [float(ground.elevation_at(p[0], p[1], floor_mm)) - floor_mm for p in posts]
    return (min(zs), max(zs)) if zs else None


def ground_spread_message(spread: Optional[tuple[float, float]]) -> Optional[tuple[str, str]]:
    """(状態, 文)。差が GROUND_STEP_WARN_MM 以下なら None."""
    if spread is None:
        return None
    lo, hi = spread
    if hi - lo <= GROUND_STEP_WARN_MM:
        return None
    st = "NG" if hi - lo > GROUND_STEP_NG_MM else "WARN"
    return st, (f"範囲の中で地盤の高さが {hi - lo:.0f}mm 違う（中央から {lo:+.0f}〜{hi:+.0f}）。法面・段差にかかっている。"
                + ("ジャッキで合わせきれない脚・地面にめり込む脚がある。範囲を平らな所（根切り底）へずらすか、"
                   "脚ごとに支柱を継ぎ足して合わせる" if st == "NG" else "低い脚はジャッキ・敷板で高さを合わせる"))
