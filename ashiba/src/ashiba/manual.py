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
