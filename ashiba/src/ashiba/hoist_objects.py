"""置いてある昇降機の部品（ashiba_hoist）→ 入力の hoists（面・位置・機種・乗り込む層）.

利用者の指定（2026-10-27）: 昇降機は別オブジェクトで配置できるように。利用者が Archicad で ashiba_hoist を置き、部品の設定で
機種（hoModel）と乗り込む層（landLevels）を選ぶ。配置はそれを読み、いちばん近い面の外側建地の列に合わせて面と位置を決め、
解いたあとで面に合わせた位置に置き直す（attachments.hoist_placements）。
"""

from __future__ import annotations

import math

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
                          float(sum(ep.spans))))
    out: list[dict] = []
    notes: list[str] = []
    for _e, (x, y), params in objs:
        best = None
        for ei, name, ox, oy, ux, uy, nx, ny, length in faces:
            t = (x - ox) * ux + (y - oy) * uy
            d = abs((x - ox) * nx + (y - oy) * ny)
            if -500.0 <= t <= length + 500.0 and (best is None or d < best[0]):
                best = (d, ei, name, min(max(t, 0.0), length))
        model_id = str(params.get("hoModel") or "")
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
