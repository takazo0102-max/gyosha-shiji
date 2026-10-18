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
    ties = sorted((t for t in model.wall_ties if t.edge_index == south.edge_index), key=lambda t: t.position_mm)
    if ties:
        t = ties[len(ties) // 2]
        x, y = _pt(o, u, nrm, t.position_mm, float(south.standoff) / 2.0)
        items.append((x, y, _part_name(model, "壁つなぎ", "壁つなぎ")))
    i0 = plain[0]
    x, y = _pt(o, u, nrm, xs[i0], -row_w)
    items.append((x, y, "建地（支柱）"))
    i1 = plain[min(1, len(plain) - 1)]
    widths = "+".join(str(w) for w in model.deck_widths_in_use)
    x, y = _pt(o, u, nrm, (xs[i1] + xs[i1 + 1]) / 2.0, -row_w / 2.0)
    items.append((x, y, f"作業床（踏板 {widths}）" if widths else "作業床（踏板）"))
    asg = getattr(model.config, "asagao", None)
    if asg is not None and int(getattr(asg, "stages", 0) or 0) > 0:
        proj = float(getattr(asg, "projection_mm", 2000.0) or 2000.0)
        i2 = plain[min(2, len(plain) - 1)]
        x, y = _pt(o, u, nrm, (xs[i2] + xs[i2 + 1]) / 2.0, -row_w - proj / 2.0)
        items.append((x, y, f"朝顔（突出 {proj:.0f}）"))
    stair = _part_name(model, "階段", "昇降階段")
    for t in getattr(stair_plan, "towers", None) or []:
        ep = next((e for e in edges if e.edge_index == t.edge_index), None)
        if ep is None:
            continue
        to, tu, tn = _frame(ep)
        x, y = _pt(to, tu, tn, (t.start_mm + t.end_mm) / 2.0, -row_w / 2.0)
        items.append((x, y, stair))
    return items


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
    for row, y0, step in ((sorted([it for it in items if it[1] < cy]), y_bottom, -pitch),
                          (sorted([it for it in items if it[1] >= cy]), y_top, pitch)):
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


def face_outward_m(model: ScaffoldModel, ep, platforms=None) -> float:
    """その面で外へ張り出すもの（昇降機・ステージ・朝顔）の出（m）. 2d.gdl の dOff と同じ考え方."""
    d = 0.0
    for ho in getattr(platforms, "hoists", None) or []:
        if getattr(ho, "edge_index", None) == ep.edge_index:
            d = max(d, 0.10 + float(getattr(ho, "cage_depth_mm", 0.0) or 0.0) / 1000.0 + 0.55)
    for st in getattr(platforms, "stages", None) or []:
        if getattr(st, "edge_index", None) == ep.edge_index:
            d = max(d, float(getattr(st, "projection_mm", 0.0) or 0.0) / 1000.0 + 0.10)
    asg = getattr(model.config, "asagao", None)
    if asg is not None and int(getattr(asg, "stages", 0) or 0) > 0:
        d = max(d, float(getattr(asg, "projection_mm", 2000.0) or 2000.0) / 1000.0 + 0.35)
    return d


def plan_dimension_data(model: ScaffoldModel, lines: list[dict], platforms=None) -> list[dict]:
    """足場ラインごとのスパン寸法と全長の寸法（Tapir CreateAssociativeDimensions の dimensionsData）.

    寸法の点は足場ラインの平面のホットスポット 1〜nSpan+1（外側建地列の支柱。2d.gdl が最初に出す）。
    寸法線は外側建地列から張り出しの外へ SPAN_DIM_OUT_M・TOTAL_DIM_OUT_M 離す。
    """
    row_w = float(model.post_row_spacing_mm) / 1000.0
    out = []
    for ep, el in zip(model.plan.edges, lines):
        o, u, nrm = _frame(ep)
        n = len(ep.spans) + 1
        off = row_w + face_outward_m(model, ep, platforms)
        for dist, idx in ((off + SPAN_DIM_OUT_M, list(range(1, n + 1))), (off + TOTAL_DIM_OUT_M, [1, n])):
            ref = (o[0] / 1000.0 - nrm[0] * dist, o[1] / 1000.0 - nrm[1] * dist)
            out.append({
                "referencePoint": {"x": ref[0], "y": ref[1]},
                "direction": {"x": u[0], "y": u[1]},
                "witnessPoints": [{"elementId": el["elementId"], "inIndex": i} for i in idx],
            })
    return out
