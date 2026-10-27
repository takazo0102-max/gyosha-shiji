"""置いてある昇降機の部品（ashiba_hoist）→ 入力の hoists（面・位置・機種・乗り込む層）.

利用者の指定（2026-10-27）: 昇降機は別オブジェクトで配置できるように。利用者が Archicad で ashiba_hoist を置き、部品の設定で
機種（hoModel）と乗り込む層（landLevels）を選ぶ。配置はそれを読み、いちばん近い面の外側建地の列に合わせて面と位置を決め、
解いたあとで面に合わせた位置に置き直す（attachments.hoist_placements）。
"""

from __future__ import annotations

import math

from .hoist_models import hoist_model
from .platforms import fewest_gate_spans_center, frame_runs

SNAP_MAX_MM = 3000.0     # 外側建地の列からこれより離れた部品は、その面の昇降機とみなさない


def _levels(v) -> list[int]:
    out = []
    for t in str(v or "").replace("、", ",").split(","):
        t = t.strip()
        if t.isdigit():
            out.append(int(t))
    return out


def hoists_from_objects(objs: list, groups: list) -> tuple[list[dict], list[str]]:
    """objs: [(要素, (x, y) mm, パラメータ)]、groups: solve_groups の結果（面を探す割付）→ (hoists の入力, 注意)."""
    faces = []
    for _label, r in groups:
        m = r.model
        for ep in m.plan.edges:
            (sx, sy), (ex, ey) = ep.start_post, ep.end_post
            n = math.hypot(ex - sx, ey - sy) or 1.0
            ux, uy = (ex - sx) / n, (ey - sy) / n
            nx, ny = -uy, ux                                  # 躯体側
            row = float(m.row_spacing_of(ep.edge_index))
            faces.append((ep.edge_index, m.face_name(ep.edge_index), sx - nx * row, sy - ny * row, ux, uy, nx, ny,
                          float(sum(ep.spans)), list(ep.spans)))
    out: list[dict] = []
    notes: list[str] = []
    for _e, (x, y), params in objs:
        best = None
        for ei, name, ox, oy, ux, uy, nx, ny, length, spans in faces:
            t = (x - ox) * ux + (y - oy) * uy
            d = abs((x - ox) * nx + (y - oy) * ny)
            if -500.0 <= t <= length + 500.0 and (best is None or d < best[0]):
                best = (d, ei, name, min(max(t, 0.0), length), spans)
        model_id = str(params.get("hoModel") or "")
        # ロングスパンは枠組の両端が足場の建地に乗る位置（スパンの続きの中心）へ寄せる（枠組間隔の半分以内）
        hm = hoist_model(model_id)
        if best is not None and hm is not None and hm.kind == "ロングスパン" and hm.frame_span_mm > 0:
            runs = frame_runs(best[4], hm.frame_span_mm)
            if runs:
                c = min((c for _i, _j, c in runs), key=lambda c: abs(c - best[3]))
                if abs(c - best[3]) <= hm.frame_span_mm / 2.0:
                    best = best[:3] + (c,) + best[4:]
        elif best is not None and hm is not None and hm.cage_len_mm > 0:
            # 枠組の無い機種（工事用エレベーター・1本構・荷揚げ機）は、乗り込み口の手すりを外すスパンがいちばん少ない位置
            # （建地の芯かスパンの中央。半スパン以内）へ寄せる。スパンの中央に 3m の荷台を置くと 3 スパン開く
            reach = max(best[4]) / 2.0 if best[4] else 0.0
            best = best[:3] + (fewest_gate_spans_center(best[4], best[3], hm.cage_len_mm, reach),) + best[4:]
        if best is None or best[0] > SNAP_MAX_MM:
            notes.append(f"昇降機の部品（{model_id or '機種なし'}）が足場の面から離れています（{SNAP_MAX_MM / 1000:.0f}m 以上）。"
                         "面の外側に寄せて置き直してください")
            continue
        h = {"edge_index": best[1], "position_mm": round(best[3], 1)}
        if model_id:
            h["model"] = model_id
        lv = _levels(params.get("landLevels"))
        if lv:
            h["landing_levels"] = lv
        out.append(h)
        notes.append(f"昇降機の部品（{model_id or '機種なし'}）を {best[2]} の始点から {best[3]:.0f}mm に合わせました")
    return out, notes
