"""平面に引いた線から開口（梁枠）の場所を決める（パレットの「開口」。利用者の指定 2026-10-24: 開口のコマンド作って、
開口に梁枠つける。線を引いて押す形）.

開けたい幅に足場に沿って線を1本引き、その線を選んで押す。線の両端を面の向きに写し、いちばん近い面の、
両端が支柱に乗る規格の梁枠（日建 2スパン 3658・3スパン 5487・4スパン 7316 など）のうち、線と重なりがいちばん
大きいものを選ぶ。梁枠は規格品しか無いので、支柱に乗らない長さには寄せない（候補が無ければ理由を返す）。
足場条件の部品の openList に「面 始点 梁枠 層 理由」を ; で並べて控える（次の配置でも使う）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

REASONS = ("搬入口", "通路", "車両出入口", "その他")


@dataclass
class OpeningPick:
    edge_index: int
    face: str
    start_mm: float                 # 面の始点の支柱から梁枠の始点まで
    beam_span_mm: int
    model_no: str = ""
    spans: list = field(default_factory=list)       # 梁枠の下のスパン
    others: list = field(default_factory=list)      # ほかに選べる (始点, 梁枠, 品番)


def _frame(ep):
    (sx, sy), (ex, ey) = ep.start_post, ep.end_post
    n = math.hypot(ex - sx, ey - sy) or 1.0
    ux, uy = (ex - sx) / n, (ey - sy) / n
    return (sx, sy), (ux, uy), (-uy, ux)


def _posts(ep) -> list[float]:
    out = [0.0]
    for s in ep.spans:
        out.append(out[-1] + float(s))
    return out


def beam_parts(model) -> dict[int, str]:
    """系列の梁枠 {呼び寸法（飛ばす長さ）: 品番}."""
    return {int(p.nominal_dim): p.model_no for p in model.master.by_category("梁枠")}


def pick_face(model, p1, p2) -> Optional[tuple]:
    """線に沿う面 → (足場の面の計画, 線の始点・終点の面に沿った位置 mm)。足場から離れすぎ・面と平行でなければ None."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ln = math.hypot(dx, dy)
    if ln < 100.0:
        return None
    best = None
    for ep in model.plan.edges:
        o, u, nrm = _frame(ep)
        if abs(dx * u[0] + dy * u[1]) < 0.9 * ln:          # 面と平行（±25°くらい）
            continue
        row = model.row_spacing_of(ep.edge_index)
        t = sorted((p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1] for p in (p1, p2))
        nm = sum((p[0] - o[0]) * nrm[0] + (p[1] - o[1]) * nrm[1] for p in (p1, p2)) / 2.0
        length = float(sum(ep.spans))
        if t[1] < 0 or t[0] > length:
            continue
        # 足場の帯（外側建地列 −row 〜 内側 0）の中ほどからの離れ。躯体側・外側へ 1.5m までは拾う
        d = abs(nm + row / 2.0)
        if d > row / 2.0 + 1500.0:
            continue
        if best is None or d < best[0]:
            best = (d, ep, (max(0.0, t[0]), min(length, t[1])))
    return None if best is None else (best[1], best[2])


def fit_beam(model, ep, t0: float, t1: float) -> tuple[list[tuple[float, int]], str]:
    """線の区間 [t0, t1] に合う梁枠 [(始点, 長さ)]（重なりの大きい順）と、合わないときの理由."""
    posts = _posts(ep)
    sizes = sorted(beam_parts(model))
    if not sizes:
        return [], f"系列 {model.master.series_id} のマスタに梁枠がありません"
    cands = []
    for p in posts:
        for s in sizes:
            if not any(abs(q - (p + s)) <= 1.0 for q in posts):
                continue
            inter = max(0.0, min(t1, p + s) - max(t0, p))
            union = max(t1, p + s) - min(t0, p)
            if inter <= 0:
                continue
            cands.append((inter / union, p, s))
    if not cands:
        spans = "・".join(str(int(s)) for s in ep.spans)
        return [], ("この区間では梁枠（" + "・".join(str(s) for s in sizes) + "）の両端が支柱に乗りません"
                    f"（この面のスパン {spans}）。梁枠の下のスパンを 1829 などにそろえてください")
    cands.sort(key=lambda c: (-c[0], c[2]))
    return [(p, s) for _r, p, s in cands], ""


def pick_opening(model, p1, p2) -> tuple[Optional[OpeningPick], str]:
    """線の両端（mm）→ (開口の候補, 合わないときの理由)."""
    hit = pick_face(model, p1, p2)
    if hit is None:
        return None, "足場に沿った線が見つかりません。開けたい幅に、足場の面に沿って線を1本引いてください"
    ep, (t0, t1) = hit
    fits, why = fit_beam(model, ep, t0, t1)
    if not fits:
        return None, f"{model.face_name(ep.edge_index)}: {why}"
    parts = beam_parts(model)
    start, size = fits[0]
    posts = _posts(ep)
    under = [float(s) for s, a in zip(ep.spans, posts) if start - 1.0 <= a < start + size - 1.0]
    return OpeningPick(ep.edge_index, model.face_name(ep.edge_index), start, size, parts.get(size, ""),
                       under, [(p, s, parts.get(s, "")) for p, s in fits[1:6]]), ""


def format_openings(items: list[dict]) -> str:
    """openings → 「南面 7316 3658 1 搬入口; …」（足場条件の部品の openList）."""
    out = []
    for o in items or []:
        face = o.get("face") or f"辺{int(o.get('edge_index', 0))}"
        out.append(f"{face} {float(o['start_mm']):.0f} {int(o['beam_span_mm'])} {int(o.get('level', 1))}"
                   + (f" {o['reason']}" if o.get("reason") else ""))
    return "; ".join(out)


def parse_openings(text) -> tuple[list[dict], list[str]]:
    """「南面 7316 3658 1 搬入口; …」→ (openings, 読めなかった項目)."""
    items, errs = [], []
    for part in str(text or "").replace("；", ";").split(";"):
        toks = part.split()
        if not toks:
            continue
        try:
            o = {"start_mm": float(toks[1]), "beam_span_mm": int(float(toks[2])),
                 "level": int(float(toks[3])) if len(toks) > 3 else 1}
        except (IndexError, ValueError):
            errs.append(part.strip())
            continue
        face = toks[0]
        if face.startswith("辺") and face[1:].isdigit():
            o["edge_index"] = int(face[1:])
        else:
            o["face"] = face
        if len(toks) > 4:
            o["reason"] = " ".join(toks[4:])
        items.append(o)
    return items, errs


def same_place(a: dict, b: dict) -> bool:
    """2つの開口が同じ面で重なるか（面名か辺番号で比べる）."""
    fa, fb = a.get("face") or a.get("edge_index"), b.get("face") or b.get("edge_index")
    if fa != fb:
        return False
    a0, a1 = float(a["start_mm"]), float(a["start_mm"]) + float(a["beam_span_mm"])
    b0, b1 = float(b["start_mm"]), float(b["start_mm"]) + float(b["beam_span_mm"])
    return min(a1, b1) - max(a0, b0) > 1.0
