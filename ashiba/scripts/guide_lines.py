"""平面に引いた目印の線（線・ポリライン）を選択から取り出す（開口・階段の位置・区切る・面の切替で共通）."""

from __future__ import annotations

import os
import json
from pathlib import Path

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "ashiba_out"))  # 試験は ASHIBA_OUT で別の場所に


def _points(obj) -> list[tuple[float, float]]:
    """要素の詳細から座標（m）を拾う（線の始点・終点、ポリラインの点）."""
    out = []
    if isinstance(obj, dict):
        if set(obj) >= {"x", "y"} and all(isinstance(obj[k], (int, float)) for k in ("x", "y")):
            out.append((float(obj["x"]), float(obj["y"])))
        for v in obj.values():
            out += _points(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _points(v)
    return out


def selected_guides(c) -> list[tuple[dict, list[tuple[tuple[float, float], tuple[float, float]]]]]:
    """選んでいる線・ポリライン → [(要素, [(端 mm, 端 mm), …])]。線は1区間、ポリラインは折れ目ごとの区間."""
    sel = c.get_selected_elements()
    out = []
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        if d.get("type") not in ("Line", "PolyLine"):
            continue
        det = d.get("details") or {}
        if d.get("type") == "PolyLine" and det.get("coordinates"):
            pts = [(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for p in det["coordinates"]]
        else:
            pts = [(x * 1000.0, y * 1000.0) for x, y in _points(det)][:2]
        segs = [(a, b) for a, b in zip(pts, pts[1:]) if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1.0]
        if segs:
            out.append((e, segs))
    return out


def building_plan(points) -> dict | None:
    """点の近くの建物の配置の控え（plan.json の中身。新しい順に見て、外形の 5m 以内）。無ければ None."""
    if not points:
        return None
    mx = sum(p[0] for p in points) / len(points)
    my = sum(p[1] for p in points) / len(points)
    # 本体の控え（ashiba_out 直下）を先に。上段・面の切替の組の控え（下のフォルダ）は外形が違うことがある
    for plan_p in sorted(OUT_DIR.rglob("*_plan.json"), key=lambda p: (p.parent != OUT_DIR, -p.stat().st_mtime)):
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
        ol = plan.get("outline_mm") or []
        if not ol:
            continue
        xs, ys = [float(p[0]) for p in ol], [float(p[1]) for p in ol]
        if min(xs) - 5000 <= mx <= max(xs) + 5000 and min(ys) - 5000 <= my <= max(ys) + 5000:
            plan["_path"] = str(plan_p)
            return plan
    return None


def not_in_plan_hint(c) -> str:
    try:
        return "" if c.current_window_type() == "FloorPlan" else "（今は平面図ではありません。線は平面図で引いて選びます）"
    except Exception:
        return ""


def delete_guides(c, guides) -> None:
    """目印の線を消す（置き直したあと）."""
    els = [e for e, _segs in guides]
    if els:
        try:
            c.delete_elements(els)
        except Exception:
            pass
