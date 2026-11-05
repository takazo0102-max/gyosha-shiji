"""ジャッキベースの下の敷板の割付（杉の足場板 幅240・厚35を建地の列に沿って通す）.

利用者の指定（2026-10-25）「敷板が飛び出ている 繋がるようにして 規格の大きさを基本で カット必要な箇所はカットして
飛び出ないようにして」。
- 列ごとに、端の脚のベース板の少し先（SILL_END_MM）まで。長いもの（4m）から詰め、最後は残りの長さに切る
  （残りが短すぎるときは1つ手前を短い規格にして、切るのは1枚だけ）
- 出隅の外側の角の支柱は、その角を描く面（始点が出隅の面）の外側の列を延ばして載せる（1m を別に敷かない）。
  外付け階段の3列目も列として通す
- 隅で直交する列が重なるところは、そこで終わる列を相手の板の手前で止める（共有の支柱は相手の板に載る）。
  同じ線の上で続く組（下段と本体など）は、後の組の板を前の組の板の端から始める
- 高低差のある地盤は脚ごとにいちばん短い規格を1枚（GDL の glList の側で描く。ここでは割り付けない）
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .gdl_params import SILL_LENGTHS_MM, SILL_W_MM

SILL_END_MM = 150.0          # 端の脚の芯から敷板の端まで（ベース板 140角の半分 70 の先）
SILL_MIN_MM = float(SILL_LENGTHS_MM[-1])
JOINT_GAP_MM = 5.0           # 直交する板の手前で止めるあき


@dataclass
class SillRun:
    """建地の1列の敷板（面の始点の内側建地から x、y は内側建地列 0・外側 −建地列間隔・3列目 −2倍）."""
    edge_index: int
    y_mm: float
    x0_mm: float
    x1_mm: float
    feet: list[float]

    def layout(self) -> list[tuple[float, int, float]]:
        """[(始めの位置, 規格の長さ, 使う長さ)]（使う長さ < 規格なら切る）."""
        out = []
        x = self.x0_mm
        for std, ln in piece_lengths(self.x1_mm - self.x0_mm):
            out.append((x, std, ln))
            x += ln
        return out


def piece_lengths(length_mm: float) -> list[tuple[int, float]]:
    """列の長さ → [(規格の長さ, 使う長さ)]。長いものから詰め、最後は残りに足りる最短の規格を残りの長さに切る.
    最後の残りが最短の規格（1m）に満たないときは、1つ手前を残りが 1m 以上になる規格にする（切るのは1枚だけ）."""
    stds = sorted(SILL_LENGTHS_MM, reverse=True)
    big = stds[0]
    out: list[tuple[int, float]] = []
    rest = float(length_mm)
    while rest > big + 1.0:
        take = big
        if rest - big < SILL_MIN_MM:
            take = next((s for s in stds if rest - s >= SILL_MIN_MM), stds[-1])
        out.append((take, float(take)))
        rest -= take
    if rest > 1.0:
        std = min((s for s in stds if s >= rest - 1.0), default=big)
        out.append((std, rest if std - rest > 1.0 else float(std)))
    return out


def _frame(ep):
    sx, sy = ep.start_post
    ex, ey = ep.end_post
    n = math.hypot(ex - sx, ey - sy) or 1.0
    ux, uy = (ex - sx) / n, (ey - sy) / n
    return (sx, sy), (ux, uy), (-uy, ux)


def _rows(model) -> list[int]:
    """敷板を通す建地列（0 内側・1 外側）。一側足場は外側の1列（GDL の rowStart と同じ）."""
    return [1] if model.config.scaffold_form == "一側足場" else [0, 1]


def _runs_of(model, stair_plan=None) -> list[SillRun]:
    from .gdl_params import shared_corner_skips

    out: list[SillRun] = []
    row_w = float(model.post_row_spacing_mm)
    skip = getattr(model, "skip_end_posts", None) or set()
    n = len(model.plan.outline.edges)
    hug = bool(model.config.is_hug)
    corner_ok = not model.master.is_frame and not hug
    for ep in model.plan.edges:
        ei = ep.edge_index
        xs = [0.0]
        for sp in ep.spans:
            xs.append(xs[-1] + float(sp))
        sk = shared_corner_skips(model, ei)
        c_sw = float(model.row_spacing_of((ei - 1) % n))
        corner_s = corner_ok and model.corner_kind_start(ei) == "出隅"
        corner_sp = model.gap_corner_post_start(ei)
        for row in _rows(model):
            feet = []
            for i, x in enumerate(xs):
                first, last = i == 0, i == len(xs) - 1
                if (first and (ei, "s") in skip) or (last and (ei, "e") in skip):
                    continue
                if (row == 0 or hug) and ((first and sk["skipInS"]) or (last and sk["skipInE"])):
                    continue
                feet.append(x)
            # 出隅の外側の角の支柱（この面が描く）は外側の列の延長に載る。隅の隙間の手前で止まる前の面の側の支柱は内側の列
            if corner_s and (row == 1 or corner_sp):
                feet.insert(0, -c_sw)
            if feet:
                out.append(SillRun(ei, -row * row_w, feet[0] - SILL_END_MM, feet[-1] + SILL_END_MM, feet))
        # 外付けの階段室の3列目
        if stair_plan is not None and getattr(stair_plan, "outside", False):
            for t in stair_plan.towers:
                if t.edge_index != ei:
                    continue
                feet = [x for x in xs if float(t.start_mm) - 1.0 <= x <= float(t.end_mm) + 1.0]
                if feet:
                    out.append(SillRun(ei, -2 * row_w, feet[0] - SILL_END_MM, feet[-1] + SILL_END_MM, feet))
    return out


def _world(model, run: SillRun):
    ep = next(e for e in model.plan.edges if e.edge_index == run.edge_index)
    o, u, nv = _frame(ep)
    p = (o[0] + nv[0] * run.y_mm, o[1] + nv[1] * run.y_mm)
    return p, u, nv


def _pt(base, u, x):
    return base[0] + u[0] * x, base[1] + u[1] * x


def _covered(model_b, rb: SillRun, q) -> bool:
    """点 q（世界座標）が板 rb の上か."""
    p, u, nv = _world(model_b, rb)
    dx, dy = q[0] - p[0], q[1] - p[1]
    a = dx * u[0] + dy * u[1]
    b = dx * nv[0] + dy * nv[1]
    return rb.x0_mm - 1.0 <= a <= rb.x1_mm + 1.0 and abs(b) <= SILL_W_MM / 2 + 1.0


def _cross(ma, ra: SillRun, mb, rb: SillRun):
    """ra の線の上で rb の板と重なる区間 (lo, hi)（ra の x）。同じ線の上なら ("par", lo, hi)、離れていれば None."""
    pa, ua, na = _world(ma, ra)
    pb, ub, nb = _world(mb, rb)
    dot = ua[0] * ub[0] + ua[1] * ub[1]
    half = SILL_W_MM / 2
    if abs(dot) > 0.99:
        off = (pb[0] - pa[0]) * na[0] + (pb[1] - pa[1]) * na[1]
        if abs(off) > half:
            return None
        b0 = (pb[0] - pa[0]) * ua[0] + (pb[1] - pa[1]) * ua[1]
        lo, hi = sorted((b0 + dot * rb.x0_mm, b0 + dot * rb.x1_mm))
        if hi <= ra.x0_mm + 1.0 or lo >= ra.x1_mm - 1.0:
            return None
        return ("par", lo, hi)
    den = ua[0] * nb[0] + ua[1] * nb[1]
    if abs(den) < 1e-6:
        return None
    t = ((pb[0] - pa[0]) * nb[0] + (pb[1] - pa[1]) * nb[1]) / den
    q = _pt(pa, ua, t)
    s = (q[0] - pb[0]) * ub[0] + (q[1] - pb[1]) * ub[1]
    if not (rb.x0_mm - half / abs(den) <= s <= rb.x1_mm + half / abs(den)):
        return None
    band = half / abs(den)
    lo, hi = t - band, t + band
    if hi <= ra.x0_mm or lo >= ra.x1_mm:
        return None
    return ("x", lo, hi)


def _end_at(ra: SillRun, lo: float, hi: float) -> str | None:
    """ra が区間 [lo, hi] で終わるか: 終点 "e"・始点 "s"・通り抜ける（か中に収まる）None."""
    if ra.x1_mm <= hi + SILL_END_MM + 1.0 and ra.x0_mm < lo:
        return "e"
    if ra.x0_mm >= lo - SILL_END_MM - 1.0 and ra.x1_mm > hi:
        return "s"
    return None


def _cut(ma, ra: SillRun, mb, rb: SillRun, end: str, lo: float, hi: float, gap: float) -> bool:
    """ra の end の側を [lo, hi] の手前で止める（外れる脚が rb に載るときだけ）→ 止めたか."""
    new0, new1 = (ra.x0_mm, lo - gap) if end == "e" else (hi + gap, ra.x1_mm)
    if new1 - new0 < 100.0:
        return False
    pa, ua, _na = _world(ma, ra)
    for x in ra.feet:
        if not (new0 - 1.0 <= x <= new1 + 1.0) and not _covered(mb, rb, _pt(pa, ua, x)):
            return False
    ra.x0_mm, ra.x1_mm = new0, new1
    return True


def layout_models(models_and_stairs) -> None:
    """組ごとの模型 [(model, stair_plan)] の敷板を割り付け、model.sill_runs（{辺: [SillRun]}）に入れる.

    同じ高さに立つ組どうしの重なりも見る（途中の屋根に立つ上段は別）。直交して重なるところは、そこで終わる板を
    相手の手前で止める。両方ともそこで終わる（出隅の共有の支柱）なら、終点で終わる板（前の面）を止めて、始点の角を
    受け持つ面の板を通す。同じ線の上で重なるところは、後の板を前の板の端から始める。
    """
    items = []
    for model, sp in models_and_stairs:
        model.sill_runs = {}
        for r in _runs_of(model, sp):
            items.append((model, r))
    for i, (ma, ra) in enumerate(items):
        for mb, rb in items[i + 1:]:
            if abs(float(ma.base_height_mm) - float(mb.base_height_mm)) > 1.0:
                continue
            ca, cb = _cross(ma, ra, mb, rb), _cross(mb, rb, ma, ra)
            if ca is None or cb is None:
                continue
            if ca[0] == "par":
                eb = _end_at(rb, cb[1], cb[2])
                if eb:
                    _cut(mb, rb, ma, ra, eb, cb[1], cb[2], 0.0)
                continue
            ea, eb = _end_at(ra, ca[1], ca[2]), _end_at(rb, cb[1], cb[2])
            if ea and (not eb or (ea == "e" and eb == "s")):
                _cut(ma, ra, mb, rb, ea, ca[1], ca[2], JOINT_GAP_MM)
            elif eb:
                _cut(mb, rb, ma, ra, eb, cb[1], cb[2], JOINT_GAP_MM)
    for model, r in items:
        model.sill_runs.setdefault(r.edge_index, []).append(r)


def runs_of(model, stair_plan=None) -> dict[int, list[SillRun]]:
    """模型の敷板の列（組をまたいだ割付が済んでいなければ、この模型だけで割り付ける）."""
    runs = getattr(model, "sill_runs", None)
    if runs is None:
        layout_models([(model, stair_plan)])
        runs = model.sill_runs
    return runs


def sill_list(model, ep, stair_plan=None) -> str:
    """足場ラインの sillList: 「列の y,始め,終わり」（mm）の繰り返し。GDL が piece_lengths と同じ割付で板を並べる."""
    parts = []
    for r in runs_of(model, stair_plan).get(ep.edge_index, []):
        parts += [f"{r.y_mm:.0f}", f"{r.x0_mm:.0f}", f"{r.x1_mm:.0f}"]
    return ",".join(parts)


def counts(model, stair_plan=None, edges=None) -> tuple[dict[int, int], int]:
    """({規格の長さ: 枚数}, 切って使う枚数)."""
    out: dict[int, int] = {}
    cut = 0
    for ei, runs in runs_of(model, stair_plan).items():
        if edges is not None and ei not in edges:
            continue
        for r in runs:
            for _x, std, ln in r.layout():
                out[std] = out.get(std, 0) + 1
                if std - ln > 1.0:
                    cut += 1
    return out, cut
