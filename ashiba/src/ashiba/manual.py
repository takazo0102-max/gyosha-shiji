"""手動配置（スパンを先に決める超簡易モード）.

利用者の指定（2026-10-30）「初めにスパンを自分で決める超簡易モードでスパンが決まっているものに合わせやすいような手動モードを
取り入れて スパンと高さ決めたら配置ボタンで足場が配置できるような仕組みを作って」。

平面に足場の内側の建地の列の線を1本引き（始点が1本目の支柱）、スパン（「1829×4, 914」）・高さ（軒高）・離れ・足場を出す側を
入れて配置する。建物（スラブ）は要らない。中では、その線から離れの分だけ建物側に寄せた仮の躯体の面（長さ＝スパンの合計−両端の
離れ）を一辺とする長方形の外形を作り、その面だけ（faces）・スパンを固定（span_overrides）して、いつもの配置で解く。
仮の外形の奥行きは「いちばん長いスパン×2−両端の離れ」（横の面の割り付けに合わせ、離れが指定どおりになる。3000 だと 300 の
指定が 329 になった）。最後に、解いた1本目の支柱が線の始点に来るように外形を動かす。
"""

from __future__ import annotations

import math
import re
from typing import Optional

# 条件の上書きファイル・足場条件から引き継ぐのは建物によらない条件だけ。階段の位置・幅の変更・開口・昇降機・面の指定など
# 建物の面に結び付いた指定を持ち込むと、仮の外形の面に合わずに階段が置けなかった（実機 2026-10-30: 見本の建物の
# 「階段 0か所」で昇降設備 NG）
GENERAL_KEYS = ("series_id", "module", "guard_rail_type", "inner_guard_rail", "end_guard", "deck_widths",
                "scaffold_width_mm", "guard_extra_mm", "period_days", "site", "pens", "toe_board", "scaffold_form",
                "next_gen", "line_mode_3d", "tie_source", "steel_depth_mm", "post_reinforcement", "corner_steps",
                "sill_boards", "elevation_mode", "cross_section_mode", "pdf", "pdf_publisher_set", "project_name",
                "horizontal_net_levels", "asagao")


def general_conditions(spec: Optional[dict]) -> dict:
    """条件から建物によらないものだけ（GENERAL_KEYS）。朝顔は付ける面の指定を外す."""
    out = {k: v for k, v in (spec or {}).items() if k in GENERAL_KEYS}
    if isinstance(out.get("asagao"), dict):
        out["asagao"] = {k: v for k, v in out["asagao"].items() if k != "faces"}
    return out


SIDE_RIGHT = "線の右側（始点から終点を見て）"
SIDE_LEFT = "線の左側"
SIDES = (SIDE_RIGHT, SIDE_LEFT)


def parse_spans(text) -> list[int]:
    """「1829×4, 914」「1829x4+914」「1800*3 900」→ [1829, 1829, 1829, 1829, 914]."""
    if isinstance(text, (list, tuple)):
        text = ",".join(str(t) for t in text)
    out: list[int] = []
    for tok in re.split(r"[,、+＋\s]+", str(text or "").strip()):
        if not tok:
            continue
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:[x×X*＊]\s*(\d+))?", tok)
        if not m:
            raise ValueError(f"スパンは「1829×4, 914」の形で入れてください（「{tok}」が読めません）")
        v, n = int(round(float(m.group(1)))), int(m.group(2) or 1)
        if v <= 0 or n <= 0:
            raise ValueError(f"スパンは0より大きい値で入れてください（「{tok}」）")
        out += [v] * n
    if not out:
        raise ValueError("スパンを1本以上入れてください（例「1829×4, 914」）")
    return out


def span_text(spans: list[int]) -> str:
    """[1829, 1829, 914] → 「1829×2, 914」（同じ寸法が続くところをまとめる）."""
    out, i = [], 0
    while i < len(spans):
        j = i
        while j < len(spans) and spans[j] == spans[i]:
            j += 1
        out.append(f"{spans[i]}×{j - i}" if j - i > 1 else f"{spans[i]}")
        i = j
    return ", ".join(out)


def suggest_spans(length_mm: float, coins: list[int]) -> list[int]:
    """線の長さ（内側の建地の列の長さ）に近いスパンの並び（長いスパンで詰め、残りを入るいちばん長いスパンで）. 窓の初期値."""
    cs = sorted({int(c) for c in coins if c > 0}, reverse=True)
    if not cs:
        return []
    n = int(length_mm // cs[0])
    out = [cs[0]] * n
    rest = length_mm - n * cs[0]
    fit = next((c for c in cs if c <= rest + 1), None)
    if fit is not None and rest >= min(cs) - 1:
        out.append(fit)
    return out or [cs[-1]]


def local_outline(spans: list[int], standoff: float, side: str = SIDE_RIGHT
                  ) -> tuple[list[list[float]], int, list[int]]:
    """仮の外形（足場の向きを +x にした局所座標）・足場を置く辺番号・その辺の始点からのスパン列.

    右側: 建物は +y（線の左）、辺0 が (0,0)→(L,0)。左側: 建物は −y、外形は左回りにそろえて辺2 が (L,0)→(0,0) なので
    スパンは逆順に渡す。
    """
    if not spans:
        raise ValueError("スパンを1本以上入れてください")
    big = max(spans)
    L = float(sum(spans)) - 2.0 * standoff
    D = 2.0 * big - 2.0 * standoff
    if L <= 0 or D <= 0:
        raise ValueError(f"スパンの合計 {sum(spans)}mm が離れ {standoff:.0f}mm の2倍より短い")
    if side == SIDE_LEFT:
        return [[0.0, -D], [L, -D], [L, 0.0], [0.0, 0.0]], 2, list(reversed(spans))
    return [[0.0, 0.0], [L, 0.0], [L, D], [0.0, D]], 0, list(spans)


def manual_spec(spans: list[int], standoff: float, side: str, eaves_mm: float, extra: Optional[dict] = None
                ) -> tuple[dict, int]:
    """局所座標の解く条件（外形・面・スパン固定・離れ固定・高さ）と、足場を置く辺番号."""
    outline, ei, sp = local_outline(spans, standoff, side)
    so = float(standoff)
    spec = {**(extra or {}), "outline_mm": outline, "faces": [ei], "eaves_height_mm": float(eaves_mm),
            "span_overrides": [{"edge_index": ei, "spans_mm": sp}],
            "standoff": {"target": so, "min": so, "max": so, "hard_min": so},
            # 入れた高さ・離れのとおりに置く（近くのスラブの高さ・庇で変えない）
            "height_from_slabs": False, "avoid_obstacles": False}
    return spec, ei


def anchor_of(plan, ei: int, side: str) -> tuple[float, float]:
    """線の始点に合わせる支柱（局所座標）: 右側は辺の始点の支柱、左側（スパン逆順）は辺の終点の支柱."""
    ep = next(e for e in plan.edges if e.edge_index == ei)
    p = ep.end_post if side == SIDE_LEFT else ep.start_post
    return float(p[0]), float(p[1])


AXIS_TOL_DEG = 2.0           # これ以内の傾きの線は縦・横にそろえる


def axis_direction(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """線 a→b の向き（縦・横にそろえた単位ベクトル）. 足場は平面の縦・横にしか組まない（斜めの躯体の辺は割付で直交2辺に
    置き換える。geometry.orthogonalize_diagonals）ので、斜めの線は止める."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if math.hypot(dx, dy) < 1.0:
        raise ValueError("線の始点と終点が同じです")
    ang = math.degrees(math.atan2(dy, dx))
    k = round(ang / 90.0)
    if abs(ang - 90.0 * k) > AXIS_TOL_DEG:
        raise ValueError(f"線が斜め（{ang % 90.0:.1f}°）です。足場は平面の縦・横の向きに組むので、線は縦か横に引いてください")
    return {0: (1.0, 0.0), 1: (0.0, 1.0), 2: (-1.0, 0.0), -2: (-1.0, 0.0), -1: (0.0, -1.0)}[k]


def to_world(outline: list[list[float]], anchor: tuple[float, float], a: tuple[float, float],
             b: tuple[float, float]) -> list[list[float]]:
    """局所座標の外形を、anchor が線の始点 a に、+x が a→b の向き（縦・横）に来るように置く."""
    u = axis_direction(a, b)
    v = (-u[1], u[0])
    out = []
    for x, y in outline:
        lx, ly = x - anchor[0], y - anchor[1]
        out.append([a[0] + lx * u[0] + ly * v[0], a[1] + lx * u[1] + ly * v[1]])
    return out


def solve_manual(a, b, spans: list[int], standoff: float, side: str, eaves_mm: float, extra: Optional[dict] = None):
    """手動配置を解く → (世界座標の外形, 条件, 局所で解いた結果). 条件は外形を世界座標にしたもの（配置に渡す）."""
    from .cli import solve_all

    axis_direction(tuple(a), tuple(b))                       # 斜めの線は解く前に止める
    spec, ei = manual_spec(spans, standoff, side, eaves_mm, extra)
    local = solve_all(spec)
    anchor = anchor_of(local.model.plan, ei, side)
    world = to_world(spec["outline_mm"], anchor, tuple(a), tuple(b))
    return world, {**spec, "outline_mm": world}, local


# ---- 一周（閉じたポリライン）: 内側の建地の列を縦横の閉じたポリラインで描き、辺ごとにスパンを入れる ----
# 向きは描いた線から、長さは入れたスパンの合計から決める（描いた長さは目安）。一周が閉じなければどの向きがいくつ合わないかを
# 出して止める。躯体の外形は、その列を離れの分だけ内側にずらしたもの（scaffold_loop_vertices を内向きに使う）。

def loop_directions(points: list) -> list[tuple[float, float]]:
    """閉じたポリラインの点（最後の点が最初と同じでもよい）→ 辺ごとの向き（縦・横の単位ベクトル）。続けて同じ向きの辺は
    そのまま返す（呼ぶ側でまとめる）."""
    pts = [tuple(map(float, p)) for p in points]
    if len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1.0:
        pts = pts[:-1]
    if len(pts) < 4:
        raise ValueError("一周の足場は、縦横の閉じたポリライン（4点以上）で描いてください")
    return [axis_direction(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


def loop_inner_row(start, dirs: list[tuple[float, float]], spans_by_side: list[list[int]]
                   ) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[list[int]]]:
    """内側の建地の列の頂点（始点から、辺の長さ＝スパンの合計）. 同じ向きが続く辺はまとめる. (頂点, 向き, スパン)."""
    if len(dirs) != len(spans_by_side):
        raise ValueError("辺の数とスパンの組の数が合いません")
    md: list[tuple[float, float]] = []
    ms: list[list[int]] = []
    for d, sp in zip(dirs, spans_by_side):
        if md and md[-1] == d:
            ms[-1] = ms[-1] + list(sp)
        else:
            md.append(d)
            ms.append(list(sp))
    if len(md) > 1 and md[0] == md[-1]:
        md[0], ms[0] = md[-1], ms[-1] + ms[0]
        md, ms = md[:-1], ms[:-1]
    pts = [(float(start[0]), float(start[1]))]
    for d, sp in zip(md, ms):
        L = float(sum(sp))
        pts.append((pts[-1][0] + d[0] * L, pts[-1][1] + d[1] * L))
    gap = (pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    if abs(gap[0]) > 1.0 or abs(gap[1]) > 1.0:
        ex = sum(sum(sp) for d, sp in zip(md, ms) if d[0] > 0.5)
        wx = sum(sum(sp) for d, sp in zip(md, ms) if d[0] < -0.5)
        ny = sum(sum(sp) for d, sp in zip(md, ms) if d[1] > 0.5)
        sy = sum(sum(sp) for d, sp in zip(md, ms) if d[1] < -0.5)
        msgs = []
        if abs(gap[0]) > 1.0:
            msgs.append(f"右向きの辺の合計 {ex}mm と左向きの辺の合計 {wx}mm が {abs(ex - wx)}mm 違う")
        if abs(gap[1]) > 1.0:
            msgs.append(f"上向きの辺の合計 {ny}mm と下向きの辺の合計 {sy}mm が {abs(ny - sy)}mm 違う")
        raise ValueError("スパンで一周が閉じません: " + "・".join(msgs) + "（向かい合う辺の合計をそろえてください）")
    return pts[:-1], md, ms


def loop_outline(inner: list[tuple[float, float]], dirs: list[tuple[float, float]], standoff: float
                 ) -> tuple[list[list[float]], list[list[int]], bool]:
    """内側の建地の列（頂点・向き）→ 躯体の外形（左回り。辺 i が列の辺 i に対応）と、左回りにそろえたかどうか."""
    n = len(inner)
    area = sum(inner[i][0] * inner[(i + 1) % n][1] - inner[(i + 1) % n][0] * inner[i][1] for i in range(n)) / 2.0
    ccw = area > 0
    # 左回りなら躯体（内側）は進む向きの左。外形の辺 i は列の辺 i を内側へ離れの分ずらした線
    lines = []
    for i in range(n):
        d = dirs[i]
        inward = (-d[1], d[0]) if ccw else (d[1], -d[0])
        lines.append(((inner[i][0] + inward[0] * standoff, inner[i][1] + inward[1] * standoff), d))
    verts = []
    for i in range(n):
        (p1, d1), (p2, _d2) = lines[(i - 1) % n], lines[i]
        verts.append([p2[0], p1[1]] if abs(d1[0]) > 0.5 else [p1[0], p2[1]])
    return verts, ccw


def solve_manual_loop(points: list, spans_by_side: list[list[int]], standoff: float, eaves_mm: float,
                      extra: Optional[dict] = None):
    """一周の手動配置を解く → (外形, 条件, 解いた結果). 外形は左回りにそろえ、スパンは左回りの向きに並べ直して渡す."""
    from .cli import solve_all

    pts = [tuple(map(float, p)) for p in points]
    if len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1.0:
        pts = pts[:-1]
    dirs = loop_directions(pts)
    inner, md, ms = loop_inner_row(pts[0], dirs, spans_by_side)
    outline, ccw = loop_outline(inner, md, standoff)
    n = len(outline)
    if not ccw:
        # 右回りに描いたとき: 外形の頂点の順を逆にし、辺 i（頂点 i→i+1）が元のどの辺かを合わせてスパンも逆順に
        outline = [outline[(n - k) % n] for k in range(n)]
        ms = [list(reversed(ms[(n - 1 - k) % n])) for k in range(n)]
    so = float(standoff)
    spec = {**(extra or {}), "outline_mm": outline, "eaves_height_mm": float(eaves_mm),
            "span_overrides": [{"edge_index": i, "spans_mm": sp} for i, sp in enumerate(ms)],
            "standoff": {"target": so, "min": so, "max": so, "hard_min": so},
            "height_from_slabs": False, "avoid_obstacles": False}
    return outline, spec, solve_all(spec)


def span_changes(spec: dict, result) -> list[str]:
    """入れたスパン（span_overrides）と解いたスパンが違う辺（入隅は2つの面を 610 などの升目でつなぐので変わる）."""
    want = {int(o["edge_index"]): list(o["spans_mm"]) for o in spec.get("span_overrides", [])}
    names = dict(zip([e.edge_index for e in result.model.plan.edges], result.model.plan.face_names()))
    out = []
    for e in result.model.plan.edges:
        w = want.get(e.edge_index)
        if w is not None and list(e.spans) != w:
            out.append(f"{names.get(e.edge_index, e.edge_index)}: {span_text(w)} → {span_text(list(e.spans))}（入隅のつなぎ）")
    return out
