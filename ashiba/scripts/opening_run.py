"""開口（梁枠）を線で指して付ける・外す（パレットのボタン「開口」）.

利用者の指定（2026-10-24）「開口のコマンド作って 開口に梁枠つける」。平面で、開けたい幅に足場の面に沿って線
（線・ポリライン）を1本引き、その線を選んで押す。線から面と位置を読み、両端が支柱に乗る規格の梁枠に寄せて窓に出す。
窓で梁枠・抜く層（何層目の床の下まで支柱を抜くか）・理由を確かめて「置く」で置き直す。同じ所に開口があれば
「外す」も出る。開口は足場条件の部品の「開口（梁枠）」（openList）に控える。置き直したら目印の線は消す。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.opening_pick import REASONS, format_openings, parse_openings, pick_opening, same_place  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402

OUT_DIR = Path.home() / "Desktop" / "ashiba_out"


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


def guide_line(c: ArchicadClient):
    """選んでいる線・ポリライン → (要素, 端の点 mm, もう一方の端 mm)。無ければ None."""
    sel = c.get_selected_elements()
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        if d.get("type") not in ("Line", "PolyLine", "Arc"):
            continue
        pts = _points(d.get("details") or {})
        if len(pts) < 2:
            continue
        a, b = max(((p, q) for p in pts for q in pts), key=lambda pq: (pq[0][0] - pq[1][0]) ** 2 + (pq[0][1] - pq[1][1]) ** 2)
        return e, (a[0] * 1000.0, a[1] * 1000.0), (b[0] * 1000.0, b[1] * 1000.0)
    return None


def building_of(p1, p2):
    """線の近くの建物の配置の控え → (plan.json の中身, 条件の控え spec_used の中身)。無ければ (None, None)."""
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    for plan_p in sorted(OUT_DIR.rglob("*_plan.json"), key=lambda p: -p.stat().st_mtime):
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
        ol = plan.get("outline_mm") or []
        if not ol:
            continue
        xs, ys = [float(p[0]) for p in ol], [float(p[1]) for p in ol]
        if min(xs) - 5000 <= mx <= max(xs) + 5000 and min(ys) - 5000 <= my <= max(ys) + 5000:
            used = plan_p.with_name(plan_p.name.replace("_plan.json", "_spec_used.json"))
            return plan, (json.loads(used.read_text(encoding="utf-8")) if used.exists() else None)
    return None, None


def ask(pick, model, existing: list[dict], hit_old) -> dict | None:
    """窓で梁枠・抜く層・理由を確かめる → {"button", "values"}."""
    from form_dialog import show_form

    lv = list(model.elevation_of(pick.edge_index).level_heights)
    levels = [f"{i}層目（床 GL+{int(h):,}）" for i, h in enumerate(lv[:4], start=1)]
    beams = [f"{pick.model_no or '梁枠'} {len(pick.spans)}スパン {pick.beam_span_mm}（始点 {pick.start_mm:.0f}）"]
    beams += [f"{no or '梁枠'} {s}（始点 {p:.0f}）" for p, s, no in pick.others]
    intro = (f"{pick.face}の始点から {pick.start_mm:.0f}〜{pick.start_mm + pick.beam_span_mm:.0f} を開口にして梁枠を入れます"
             f"（下のスパン {'・'.join(str(int(s)) for s in pick.spans)}）。抜く層は、その層の床の下まで支柱を抜き、"
             "床の高さに梁枠を入れます。頭上は 1800 以上が目安です。")
    buttons = [{"id": "place", "label": "置く"}]
    if hit_old is not None:
        buttons.append({"id": "remove", "label": "外す"})
        intro += f" この場所には開口があります（{format_openings([hit_old])}）。"
    buttons.append({"id": "cancel", "label": "やめる"})
    fields = [
        {"key": "_s", "label": f"開口（{pick.face}）", "kind": "section"},
        {"key": "beam", "label": "梁枠", "kind": "choice", "options": beams, "value": beams[0]},
        {"key": "level", "label": "抜く層", "kind": "choice", "options": levels,
         "value": levels[(int(hit_old.get("level", 1)) - 1) if hit_old else 0]},
        {"key": "reason", "label": "理由", "kind": "choice", "options": list(REASONS),
         "value": (hit_old or {}).get("reason") or REASONS[0]},
    ]
    return show_form({"title": "開口（梁枠）", "intro": intro, "fields": fields, "buttons": buttons})


def chosen(pick, values: dict) -> dict:
    """窓の値 → 開口1件（面・始点・梁枠・層・理由）."""
    beam = str(values.get("beam") or "")
    start, size = pick.start_mm, pick.beam_span_mm
    for p, s, no in pick.others:
        if beam.startswith(f"{no or '梁枠'} {s}（始点 {p:.0f}）"):
            start, size = p, s
    level = int(str(values.get("level") or "1").split("層")[0] or 1)
    return {"face": pick.face, "start_mm": round(start), "beam_span_mm": int(size), "level": level,
            "reason": str(values.get("reason") or "")}


def main() -> int:
    import run_from_archicad as R
    from ashiba.cli import solve_groups
    from ashiba.spec_object import pick_spec_object

    c = ArchicadClient()
    g = guide_line(c)
    if g is None:
        hint = ""
        try:
            if c.current_window_type() != "FloorPlan":
                hint = "（今は平面図ではありません。線は平面図で引いて選びます）"
        except TapirError:
            pass
        print("開口: 平面で、開けたい幅に足場の面に沿って線を1本引き、その線を選んでから押してください" + hint)
        return 1
    line_el, p1, p2 = g
    plan, used = building_of(p1, p2)
    if plan is None or used is None:
        print(f"開口: 線の近くの足場の配置の控え（plan.json・spec_used.json）が {OUT_DIR} にありません。先に「配置」してください")
        return 1
    outline = plan.get("outline_mm") or []
    pick, why, model = None, "", None
    for _label, run in solve_groups({**used, "outline_mm": outline}):
        pick, why = pick_opening(run.model, p1, p2)
        if pick is not None:
            model = run.model
            break
    if pick is None:
        print(f"開口: {why}")
        return 1
    # 今の開口（足場条件の部品が正。無ければ条件の控え）
    R.ensure_parts(c)
    spec = R.apply_spec_object(c, {**R.SPEC, **R.load_spec_override(), "outline_mm": outline})
    hit = pick_spec_object(R.read_spec_objects(c), outline)
    existing = list(spec.get("openings") or [])
    for o in existing:            # 辺番号の開口も面名で比べる
        if "face" not in o and "edge_index" in o:
            o["face"] = model.face_name(int(o["edge_index"]))
    probe = {"face": pick.face, "start_mm": pick.start_mm, "beam_span_mm": pick.beam_span_mm}
    hit_old = next((o for o in existing if same_place(o, probe)), None)
    res = ask(pick, model, existing, hit_old)
    if not res or res.get("button") in (None, "cancel"):
        print("開口: やめました（何も変えていません）")
        return 0
    rest = [o for o in existing if o is not hit_old]
    if res["button"] == "remove":
        new = rest
        msg = f"開口: {format_openings([hit_old])} を外しました"
    else:
        one = chosen(pick, res.get("values") or {})
        new = [o for o in rest if not same_place(o, one)] + [one]
        msg = f"開口: {format_openings([one])} を入れました"
    text = format_openings(new)
    if hit is not None:
        try:
            c.set_gdl_parameters(hit[0], {"openList": text})
        except TapirError as e:
            print(f"開口: 足場条件の部品に書けませんでした（{e}）")
            return 1
    else:
        body = R.load_spec_override()
        body["openings"] = new
        R.SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(msg)
    print("---- 置き直します")
    R.main(outline_mm=outline, out_dir=OUT_DIR)
    try:
        c.delete_elements([line_el])          # 目印の線
        print("開口: 目印の線を消しました")
    except TapirError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
