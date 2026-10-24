"""足場平面図の部材名ラベル（引出線つき）.

立面図と同じく、部材名は Archicad のラベルで付ける（参考: micotoworks「足場図面の書き方」の平面図。
壁つなぎ・昇降階段などに引出線）。平面のラベルは平面図（モデル）に直接置く要素なので、建物ごとに
GUID を控え（plan_labels.json）、次の配置・撤去で前のラベルを消す。

ラベルの文字は、足場の外（寸法線のさらに外）に下段（南側）と上段（北側）の2列に並べる。
矢先は部材の位置（壁つなぎの記号・階段室の中央・作業床・朝顔）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from .elevation_sections import label_text_width_m
from .model import ScaffoldModel

PLAN_LABELS_RECORD = "plan_labels.json"
ROW_GAP_M = 1.0            # 寸法（全長の寸法線と文字）からラベルの列まで
DIM_EXTENT_M = 1.9         # 外側建地列から平面の全長の寸法の文字まで（2d.gdl: 0.90＋0.70＋文字）


def _frame(ep):
    sx, sy = ep.start_post
    ex, ey = ep.end_post
    n = math.hypot(ex - sx, ey - sy) or 1.0
    ux, uy = (ex - sx) / n, (ey - sy) / n
    return (sx, sy), (ux, uy), (-uy, ux)          # 躯体側（左手）が +n


def _pt(origin, u, nrm, along_mm: float, inward_mm: float) -> tuple[float, float]:
    """面の局所座標（面に沿った距離, 躯体側への距離 mm）→ 平面の点（m）."""
    return ((origin[0] + u[0] * along_mm + nrm[0] * inward_mm) / 1000.0,
            (origin[1] + u[1] * along_mm + nrm[1] * inward_mm) / 1000.0)


def _part_name(model: ScaffoldModel, cat: str, fallback: str) -> str:
    p = next(iter(model.master.by_category(cat)), None)
    return f"{fallback} {p.model_no}" if p is not None and p.model_no else fallback


def plan_label_items(model: ScaffoldModel, stair_plan=None) -> list[tuple[float, float, str]]:
    """ラベルを付ける部材の (x m, y m, 文字)."""
    row_w = float(model.post_row_spacing_mm)
    edges = list(model.plan.edges)
    if not edges:
        return []
    # 下（南）を向く面（外向きの法線が -y に近い）を代表面に。壁つなぎ・作業床・建地・朝顔はこの面で指す
    def outward_y(ep):
        _o, _u, nrm = _frame(ep)
        return -nrm[1]
    south = min(edges, key=outward_y)
    o, u, nrm = _frame(south)
    xs = [0.0]
    for sp in south.spans:
        xs.append(xs[-1] + float(sp))
    towers = [t for t in (getattr(stair_plan, "towers", None) or []) if t.edge_index == south.edge_index]
    plain = [i for i in range(len(south.spans))
             if not any(xs[i] < t.end_mm - 1 and xs[i + 1] > t.start_mm + 1 for t in towers)] or list(range(len(south.spans)))
    items: list[tuple[float, float, str]] = []
    i0 = plain[0]
    x, y = _pt(o, u, nrm, xs[i0], -row_w)
    items.append((x, y, "建地（支柱）"))
    # 作業床（踏板の幅）・壁つなぎは足場ラインの GDL のラベル（「くさび緊結式足場 600／踏板 400+250」「壁つなぎ NK-3352II」）が面ごとに描く
    if model.config.horizontal_net_levels:
        i3 = plain[min(3, len(plain) - 1)]
        x, y = _pt(o, u, nrm, (xs[i3] + xs[i3 + 1]) / 2.0, float(south.standoff) / 2.0)
        lv = "・".join(str(v) for v in model.config.horizontal_net_levels)
        items.append((x, y, f"水平ネット（第{lv}層）" + ("・ネットブラケット" if model.config.net_brackets else "")))
    asg = getattr(model.config, "asagao", None)
    # 朝顔は代表面（南）に付いていればそこ、外していれば朝顔の付いている面で指す（朝顔の面で付け外しする。2026-10-24）
    asa_ep = south if model.asagao_on(south.edge_index) else next(
        (e for e in sorted(edges, key=outward_y) if model.asagao_on(e.edge_index)), None)
    if asg is not None and int(getattr(asg, "stages", 0) or 0) > 0 and asa_ep is not None:
        proj = float(getattr(asg, "projection_mm", 2000.0) or 2000.0)
        ao, au, an = _frame(asa_ep)
        ax = [0.0]
        for sp in asa_ep.spans:
            ax.append(ax[-1] + float(sp))
        i2 = (plain[min(2, len(plain) - 1)] if asa_ep is south else min(2, len(asa_ep.spans) - 1))
        x, y = _pt(ao, au, an, (ax[i2] + ax[i2 + 1]) / 2.0, -row_w - proj / 2.0)
        items.append((x, y, f"朝顔（突出 {proj:.0f}）"))
    stair = _part_name(model, "階段", "昇降階段")
    for t in getattr(stair_plan, "towers", None) or []:
        ep = next((e for e in edges if e.edge_index == t.edge_index), None)
        if ep is None:
            continue
        to, tu, tn = _frame(ep)
        # 外付けは外側建地列の外の升目の中央
        y_mm = -row_w / 2.0 - (row_w if getattr(stair_plan, "outside", False) else 0.0)
        x, y = _pt(to, tu, tn, (t.start_mm + t.end_mm) / 2.0, y_mm)
        items.append((x, y, stair))
    # ハッチ付布板（梯子内蔵）の昇降口（階段室が入らない小さい足場）。蓋の中央を指す
    from .stairs import hatch_part

    hp, hw = hatch_part(model)
    for ei, k in getattr(model, "hatch_ladders", None) or []:
        ep = next((e for e in edges if e.edge_index == ei), None)
        if ep is None or hp is None or not (0 <= k < len(ep.spans)):
            continue
        ho, hu, hn = _frame(ep)
        x0 = float(sum(ep.spans[:k]))
        x, y = _pt(ho, hu, hn, x0 + ep.spans[k] / 2.0, -row_w + 50.0 + hw / 2.0)
        items.append((x, y, f"昇降口 ハッチ付布板 {hp.model_no}"))
    return items


def _local_row(model: ScaffoldModel, x: float, y: float, w: float, h: float, standoff: float, row_w: float,
               out_dist: float, y_bottom: float, y_top: float):
    """部材 (x, y)（m）が外形の上下の端でない南北の面にあり、その面の外の列に空きがあれば (列の名前, y, 向き)."""
    verts = [(float(a) / 1000.0, float(b) / 1000.0) for a, b in model.plan.outline.vertices]
    n = len(verts)
    for i in range(n):
        (ax, ay), (bx, by) = verts[i], verts[(i + 1) % n]
        if abs(ay - by) > 1e-6 or abs(bx - ax) < 1e-6:
            continue                                       # 南北を向く（x 方向の）辺だけ
        north = bx < ax                                    # 反時計回り: 西へ向かう辺は北向き
        lo, hi = min(ax, bx), max(ax, bx)
        d = (y - ay) if north else (ay - y)                # 外向きの距離
        if not (lo <= x <= hi and 0.0 <= d <= standoff + row_w + 0.5):
            continue
        y0 = ay + (out_dist if north else -out_dist)
        if (north and y0 >= y_top - 0.5) or (not north and y0 <= y_bottom + 0.5):
            return None                                    # 外形の端の面: いつもの上段・下段
        # 列の文字の範囲が建物と足場（離れ＋建地列＋1m）から離れていること
        x0, x1 = x - 0.5, x - 0.5 + w
        y_lo, y_hi = (y0 - 3.0 * h, y0 + h) if north else (y0 - h, y0 + 3.0 * h)
        keep = standoff + row_w + 1.0
        for j in range(n):
            (cx, cy_), (ex, ey) = verts[j], verts[(j + 1) % n]
            if (min(cx, ex) - keep < x1 and max(cx, ex) + keep > x0
                    and min(cy_, ey) - keep < y_hi and max(cy_, ey) + keep > y_lo):
                return None
        return (f"face{i}", y0, h * 2.8 if north else -h * 2.8)
    return None


def outward_extra_m(model: ScaffoldModel, platforms=None) -> float:
    """外へ張り出すもの（朝顔・荷受けステージ・昇降機）の出（m）。平面の寸法はその外（2d.gdl の dOff）."""
    extra = 0.0
    asg = getattr(model.config, "asagao", None)
    if asg is not None and int(getattr(asg, "stages", 0) or 0) > 0:
        extra = float(getattr(asg, "projection_mm", 2000.0) or 2000.0) / 1000.0 + 0.35
    for st in getattr(platforms, "stages", None) or []:
        extra = max(extra, float(getattr(st, "projection_mm", 0.0) or 0.0) / 1000.0 + 0.1)
    for ho in getattr(platforms, "hoists", None) or []:
        extra = max(extra, 0.10 + float(getattr(ho, "cage_depth_mm", 0.0) or 0.0) / 1000.0 + 0.55)
    return extra


def plan_labels(model: ScaffoldModel, stair_plan=None, text_scale: float = 100.0,
                text_height_mm: float = 2.5, platforms=None) -> list[dict]:
    """平面のラベル {"beg","mid","end","text"}（m）。南半分の部材は下段、北半分は上段に並べる.

    平面の寸法は張り出すもの（朝顔・ステージ・昇降機）の外にあるので、列はさらにその外。
    """
    extra_out_m = outward_extra_m(model, platforms)
    items = plan_label_items(model, stair_plan)
    if not items:
        return []
    vx = [float(v[0]) / 1000.0 for v in model.plan.outline.vertices]
    vy = [float(v[1]) / 1000.0 for v in model.plan.outline.vertices]
    standoff = max((float(e.standoff) for e in model.plan.edges), default=300.0) / 1000.0
    row_w = float(model.post_row_spacing_mm) / 1000.0
    out_dist = standoff + row_w + extra_out_m + DIM_EXTENT_M + ROW_GAP_M
    y_bottom = min(vy) - out_dist
    y_top = max(vy) + out_dist
    cy = (min(vy) + max(vy)) / 2.0
    lo, hi = min(vx) - standoff - row_w, max(vx) + standoff + row_w
    h = text_height_mm * text_scale / 1000.0
    pitch = h * 2.8
    out: list[dict] = []
    # 列: 下段（南）・上段（北）。L 字の入隅など、外形の上下の端でない南北の面の部材（階段）は、その面の外に
    # 空きがあればその面の外の列に（上段まで引くと引出線が建物を縦断した）
    rows: dict = {"bottom": ([], y_bottom, -pitch), "top": ([], y_top, pitch)}
    for it in items:
        local = _local_row(model, it[0], it[1], label_text_width_m(it[2], h) + 0.4 + 1.2 * h, h,
                           standoff, row_w, out_dist, y_bottom, y_top)
        if local is not None:
            key, y0, step = local
            rows.setdefault(key, ([], y0, step))[0].append(it)
        else:
            rows["bottom" if it[1] < cy else "top"][0].append(it)
    for row, y0, step in ((sorted(r_[0]), r_[1], r_[2]) for r_ in rows.values()):
        ends: list[float] = []
        for x, y, text in row:
            w = label_text_width_m(text, h) + 0.4 + 1.2 * h
            pref = x - 0.5
            k = 0
            while True:
                if k == len(ends):
                    ends.append(-1e9)
                xe = max(pref, ends[k] + 0.6 * h / 0.25)
                if (xe + w <= hi + 4.0 and xe - pref <= 2.5) or k >= 3:
                    break
                k += 1
            ends[k] = xe + w
            y_row = y0 + step * k
            out.append({"beg": (x, y), "mid": (xe, y_row), "end": (xe + 0.4, y_row), "text": text})
    return out


# ---------------------------------------------------------------- 控え（建物ごとのラベルの GUID）

def load_label_record(out_dir) -> dict:
    p = Path(out_dir) / PLAN_LABELS_RECORD
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return {str(k): [str(g) for g in v] for k, v in d.items() if isinstance(v, list)}
    except Exception:
        return {}


def save_label_record(out_dir, building: str, guids: list[str]) -> None:
    rec = load_label_record(out_dir)
    if guids:
        rec[building] = list(guids)
    else:
        rec.pop(building, None)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / PLAN_LABELS_RECORD).write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")


def replace_plan_labels(client, out_dir, building: str, labels, floor_index=None) -> int:
    """平面の部材名ラベルだけを置き直す（寸法はそのまま）。控えの GUID のうち寸法でないものを消して、labels を置く.

    朝顔の面のように一部だけ直すボタンが使う（利用者の指定 2026-10-24: 朝顔の面でラベルも一緒に直して）。置いた数を返す.
    """
    from .elevation_sections import create_labels

    guids = load_label_record(out_dir).get(building, [])
    keep, gone = [], []
    if guids:
        els = [{"elementId": {"guid": g}} for g in guids]
        try:
            det = client.tapir("GetDetailsOfElements", {"elements": els}).get("detailsOfElements", [])
        except Exception:
            det = []
        for g, d in zip(guids, det):
            typ = str((d or {}).get("type") or "")
            if not typ:
                continue                       # 手で消されたもの
            (keep if "Dimension" in typ else gone).append(g)
    if gone:
        try:
            client.delete_elements([{"elementId": {"guid": g}} for g in gone])
        except Exception:
            pass
    made = create_labels(client, labels, floor_index=floor_index) if labels else []
    save_label_record(out_dir, building, keep + list(made))
    return len(made)


def remove_plan_labels(client, out_dir, building: Optional[str] = None) -> int:
    """控えにある平面のラベルを消す（building を省くと全建物）。消した数を返す."""
    rec = load_label_record(out_dir)
    keys = [building] if building is not None else list(rec)
    guids = [g for k in keys for g in rec.get(k, [])]
    if guids:
        try:
            client.delete_elements([{"elementId": {"guid": g}} for g in guids])
        except Exception:
            pass          # 手で消されていれば消せないだけ
    for k in keys:
        rec.pop(k, None)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / PLAN_LABELS_RECORD).write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    return len(guids)


# ---------------------------------------------------------------- 平面のスパン寸法（寸法ツール）

SPAN_DIM_OUT_M = 0.90      # 外側建地列（＋張り出し）からスパン寸法の寸法線まで（2d.gdl の yd と同じ）
TOTAL_DIM_OUT_M = 1.60     # 同じく全長の寸法線まで（yt）


def face_outward_m(model: ScaffoldModel, ep, platforms=None, stair_plan=None) -> float:
    """その面で外へ張り出すもの（昇降機・ステージ・朝顔・外付けの階段室）の出（m）. 2d.gdl の dOff と同じ考え方."""
    d = 0.0
    if getattr(stair_plan, "outside", False) and any(
            t.edge_index == ep.edge_index for t in getattr(stair_plan, "towers", None) or []):
        d = float(model.post_row_spacing_mm) / 1000.0 + 0.10
    for ho in getattr(platforms, "hoists", None) or []:
        if getattr(ho, "edge_index", None) == ep.edge_index:
            d = max(d, 0.10 + float(getattr(ho, "cage_depth_mm", 0.0) or 0.0) / 1000.0 + 0.55)
    for st in getattr(platforms, "stages", None) or []:
        if getattr(st, "edge_index", None) == ep.edge_index:
            d = max(d, float(getattr(st, "projection_mm", 0.0) or 0.0) / 1000.0 + 0.10)
    asg = getattr(model.config, "asagao", None)
    if asg is not None and int(getattr(asg, "stages", 0) or 0) > 0 and model.asagao_on(ep.edge_index):
        d = max(d, float(getattr(asg, "projection_mm", 2000.0) or 2000.0) / 1000.0 + 0.35)
    return d


def plan_dimension_data(model: ScaffoldModel, lines: list[dict], platforms=None, stair_plan=None) -> list[dict]:
    """足場ラインごとのスパン寸法と全長の寸法（Tapir CreateAssociativeDimensions の dimensionsData）.

    寸法の点は足場ラインの平面のホットスポット 1〜nSpan+1（外側建地列の支柱。2d.gdl が最初に出す）と、
    nSpan+2・nSpan+3（始点・終点の出隅コーナーの外側の角の支柱）。寸法は両端のコーナーまで張る
    （利用者の指摘 2026-10-20: 寸法は両端まで必要）。
    寸法線は外側建地列から張り出しの外へ SPAN_DIM_OUT_M・TOTAL_DIM_OUT_M 離す。
    """
    row_w = float(model.post_row_spacing_mm) / 1000.0
    out = []
    for ep, el in zip(model.plan.edges, lines):
        o, u, nrm = _frame(ep)
        n = len(ep.spans) + 1
        oe = model.plan.outline.edges[ep.edge_index]
        corner = not model.master.is_frame
        head = [n + 1] if corner and model.corner_kind_start(ep.edge_index) == "出隅" else []
        tail = [n + 2] if corner and model.corner_kind_end(ep.edge_index) == "出隅" else []
        # 隅の隙間（コーナーステップ）は寸法の並びに入れる（ホットスポット nSpan+8・nSpan+9）
        from .gdl_params import corner_gaps_m

        gp = corner_gaps_m(model, ep.edge_index)
        g_s = [n + 8] if gp["gapS"] > 0 else []
        g_e = [n + 7] if gp["gapE"] > 0 else []
        chain = head + g_s + list(range(1, n + 1)) + g_e + tail
        off = row_w + face_outward_m(model, ep, platforms, stair_plan)
        for dist, idx in ((off + SPAN_DIM_OUT_M, chain), (off + TOTAL_DIM_OUT_M, [chain[0], chain[-1]])):
            ref = (o[0] / 1000.0 - nrm[0] * dist, o[1] / 1000.0 - nrm[1] * dist)
            out.append({
                "referencePoint": {"x": ref[0], "y": ref[1]},
                "direction": {"x": u[0], "y": u[1]},
                "witnessPoints": [{"elementId": el["elementId"], "inIndex": i} for i in idx],
            })
    return out + standoff_dimension_data(model, lines)


def standoff_dim_positions(model: ScaffoldModel, ep) -> tuple[float, float]:
    """離れ寸法を引く2か所（足場ラインの始点からの mm）. 躯体に面したスパンのうち始点側・終点側の端のスパン中央.

    ブラケットの面へ延ばした本足場の端のスパン（隅の外。corner_joins）や出隅を回る端数スパンは躯体に面して
    いないので選ばない（実機 2026-10-23: 延長の 610 のスパンに離れ寸法が付いて躯体の無い所を測っていた）。
    """
    o, u, _n = _frame(ep)
    oe = model.plan.outline.edges[ep.edge_index]
    ts = sorted(((oe.start[0] - o[0]) * u[0] + (oe.start[1] - o[1]) * u[1],
                 (oe.end[0] - o[0]) * u[0] + (oe.end[1] - o[1]) * u[1]))
    mids, x = [], 0.0
    for s in ep.spans:
        mids.append(x + s / 2.0)
        x += s
    inside = [m for m in mids if ts[0] + 50.0 <= m <= ts[1] - 50.0]
    if not inside:
        return mids[0], mids[-1]
    return inside[0], inside[-1]


def standoff_dimension_data(model: ScaffoldModel, lines: list[dict]) -> list[dict]:
    """離れ寸法（躯体面〜内側建地列）を寸法ツールで。面ごとに両端のスパン中央の2本（利用者の指定 2026-10-23）.

    点は足場ラインの平面のホットスポット nSpan+4〜nSpan+7（2d.gdl の最初のホットスポットの並び）。
    寸法線は面に直交し、点から面に沿って 0.25m ずらした所に引く。plan_dimension_data の後ろに面ごとに2本ずつ並ぶ。
    """
    out = []
    for ep, el in zip(model.plan.edges, lines):
        o, u, nrm = _frame(ep)
        n = len(ep.spans) + 1
        xs = standoff_dim_positions(model, ep)
        for k, x in enumerate(xs):
            ref = ((o[0] + u[0] * (x + 250.0)) / 1000.0, (o[1] + u[1] * (x + 250.0)) / 1000.0)
            out.append({
                "referencePoint": {"x": ref[0], "y": ref[1]},
                "direction": {"x": nrm[0], "y": nrm[1]},
                "witnessPoints": [{"elementId": el["elementId"], "inIndex": n + 3 + 2 * k},
                                  {"elementId": el["elementId"], "inIndex": n + 4 + 2 * k}],
            })
    return out
