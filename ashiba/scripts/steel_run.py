"""鉄骨の建て方（パレットの「鉄骨建て方」）: 柱と梁をピースに分け、節ごとの重量表を出す（利用者の指定 2026-11-07）.

  python3 scripts/steel_run.py --ask                    # 窓で符号の断面と切り方を決めて置く
  python3 scripts/steel_run.py --sec "C1=□-500×500×22,G1=H-500×200×10×16"
  python3 scripts/steel_run.py --table                  # 置かずに表だけ
  python3 scripts/steel_run.py --remove                 # 置いたピースを消す
  python3 scripts/steel_run.py --zones X3 --order 工区  # 工区の境の通りと建てる順（工区: 建て逃げ・節: 積み上げ）
  python3 scripts/steel_run.py --next / --prev / --step 3 / --undo   # 工区・節のステップの姿にする・全部に戻す

柱と梁を選んで押す（選んでいなければ表示中の全部）。元の柱と梁は触らず、部品 ashiba_steel のピースを重ねて置く。
重量表と工区のピース数は ashiba_out/鉄骨節別重量表.xlsx、工程表は ashiba_out/鉄骨建方工程表.xlsx、符号の断面は ashiba_out/鉄骨符号表.csv に残し、次からの既定にする.
ピースはステップごとのレイヤー「鉄骨_01_1工区1節」に置く。ステップの間は元の柱と梁をレイヤー「鉄骨_元の柱梁」へ移して隠し、--undo で元のレイヤーへ戻す（控えは ashiba_out/鉄骨ステップ.json）.
1 日のピース数の公開の歩掛かりは見つからなかったので窓で入れる（既定 30 は【目安・出典なし】）.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_steel"
RECORD = "鉄骨建て方.json"
TABLE = "鉄骨符号表.csv"
STEPS = "鉄骨ステップ.json"
ORIGINAL_LAYER = "鉄骨_元の柱梁"


def read_table(path) -> dict:
    """符号表 {符号: 断面の文字}."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return {r[0].strip(): r[1].strip() for r in csv.reader(f) if len(r) >= 2 and r[0].strip() and r[0].strip() != "符号"}
    except OSError:
        return {}


def write_table(path, table: dict) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["符号", "断面"])
        w.writerows(sorted(table.items()))


def column_of(d: dict):
    """Archicad の柱の詳細 → Column（mm）."""
    from ashiba.steel_erection import Column
    import math

    q = d["details"]
    o = q["origin"]
    z = float(q["zCoordinate"]) * 1000.0
    return Column(d.get("id") or "", o["x"] * 1000.0, o["y"] * 1000.0, z, z + float(q["height"]) * 1000.0, float(q["width"]) * 1000.0,
                  float(q["depth"]) * 1000.0, math.degrees(float(q.get("axisRotationAngle", 0.0))))


def beam_of(d: dict):
    """Archicad の梁の詳細 → Beam（mm）. 梁の中心の高さは基準線の位置から."""
    from ashiba.steel_erection import Beam

    q = d["details"]
    h = float(q["height"]) * 1000.0
    z = float(q["zCoordinate"]) * 1000.0
    a = str(q.get("anchorPoint", "TopCenter"))
    zc = z - h / 2.0 if a.startswith("Top") else z + h / 2.0 if a.startswith("Bottom") else z
    p0, p1 = q["begCoordinate"], q["endCoordinate"]
    return Beam(d.get("id") or "", (p0["x"] * 1000.0, p0["y"] * 1000.0), (p1["x"] * 1000.0, p1["y"] * 1000.0), zc, float(q["width"]) * 1000.0, h)


def grid_lines(c) -> tuple:
    """通り芯の記号 → (X の線 [(名前, x)], Y の線 [(名前, y)]). 同じ y に並ぶ記号が X の通り、同じ x に並ぶ記号が Y の通り."""
    es = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    ds = c.get_details(es) if es else []
    marks = [(e, d["details"]["origin"]) for e, d in zip(es, ds) if "通り芯" in d.get("details", {}).get("libPart", {}).get("name", "")]
    if not marks:
        return [], []
    rows = c.tapir("GetGDLParametersOfElements", {"elements": [e for e, _o in marks]}).get("gdlParametersOfElements", [])
    named = []
    for (_e, o), r in zip(marks, rows):
        name = next((p.get("value") for p in r.get("parameters", []) if p.get("name") == "AC_MarkerText_1"), "")
        if name:
            named.append((str(name), o["x"] * 1000.0, o["y"] * 1000.0))
    my = Counter(round(y) for _n, _x, y in named).most_common(1)
    mx = Counter(round(x) for _n, x, _y in named).most_common(1)
    xs = [(n, x) for n, x, y in named if my and round(y) == my[0][0]]
    ys = [(n, y) for n, x, y in named if mx and round(x) == mx[0][0]]
    return xs, ys


def ask(a, marks: list, table: dict) -> bool:
    """窓: 切り方とプレート、符号の断面. やめたら False."""
    from form_dialog import show_form

    res = show_form({
        "title": "鉄骨建て方",
        "intro": "柱は階の高さ＋指定の高さで節に切り、梁は柱の中心から指定の距離で切って端（ブラケット）と継手の添え板を柱と一体にします。断面の無い符号は重量を出しません。"
                 "断面は H-500×200×10×16・□-500×500×22・P-318.5×10 の形で。",
        "fields": [{"key": "every", "label": "節は何階ごと", "kind": "number", "value": f"{a.every}"},
                   {"key": "offset", "label": "節の高さ mm（階の高さから）", "kind": "number", "value": f"{a.offset:g}"},
                   {"key": "bracket", "label": "梁を切る距離 mm（柱の中心から）", "kind": "number", "value": f"{a.bracket:g}"},
                   {"key": "base", "label": "下端の高さ m（これより下は見ない）", "kind": "number", "value": f"{a.base:g}"},
                   {"key": "bp_over", "label": "ベースプレートのはみ出し mm【目安】", "kind": "number", "value": f"{a.bp_over:g}"},
                   {"key": "bp_t", "label": "ベースプレートの厚さ mm【目安】", "kind": "number", "value": f"{a.bp_t:g}"},
                   {"key": "extra", "label": "重量の割増 %（ボルト・溶接・ダイアフラム）【目安】", "kind": "number", "value": f"{a.extra:g}"},
                   {"key": "zones", "label": "工区の境の通り（X3,Y2 の形。空＝1工区）", "kind": "text", "value": a.zones},
                   {"key": "order", "label": "建てる順", "kind": "choice", "options": ["工区ごとに上まで（建て逃げ）", "節ごとに全工区（積み上げ）"],
                    "value": "節ごとに全工区（積み上げ）" if a.order == "節" else "工区ごとに上まで（建て逃げ）"},
                   {"key": "per_day", "label": "1 日のピース数（クレーン 1 台）【目安・出典なし】", "kind": "number", "value": f"{a.per_day:g}"},
                   {"key": "cranes", "label": "クレーンの台数", "kind": "number", "value": f"{a.cranes}"},
                   {"key": "start", "label": "建方の始まり（2027-04-01 の形）", "kind": "text", "value": a.start},
                   {"key": "sat_off", "label": "土曜を休みにする", "kind": "check", "value": "1" if a.sat_off else "0"},
                   *[{"key": f"s_{m}", "label": f"断面 {m}", "kind": "text", "value": table.get(m, "")} for m in marks]],
        "buttons": [{"id": "go", "label": "置く"}, {"id": "table", "label": "表だけ"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") not in ("go", "table"):
        return False
    a.table = res.get("button") == "table"
    v = res.get("values") or {}
    a.zones = str(v.get("zones") or "").strip()
    a.order = "節" if str(v.get("order", "")).startswith("節") else "工区"
    a.start = str(v.get("start") or a.start).strip()
    a.sat_off = str(v.get("sat_off")) in ("1", "true", "True")
    try:
        a.cranes = max(1, int(float(str(v.get("cranes")))))
    except (TypeError, ValueError):
        pass
    for k in ("offset", "bracket", "base", "bp_over", "bp_t", "extra", "per_day"):
        try:
            setattr(a, k, float(str(v.get(k)).replace(",", "")))
        except (TypeError, ValueError):
            pass
    try:
        a.every = max(1, int(float(str(v.get("every")))))
    except (TypeError, ValueError):
        pass
    for m in marks:
        table[m] = str(v.get(f"s_{m}") or "").strip()
    return True


def read_json(path, empty):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty


def layer_map(c) -> dict:
    return {x.get("name"): int(x["index"]) for x in c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])}


def show_layers(c, hidden: dict) -> None:
    c.tapir("CreateLayers", {"layerDataArray": [{"name": n, "isHidden": bool(h)} for n, h in hidden.items()], "overwriteExisting": True})


def visible_at(steps: list, no: int) -> dict:
    """ステップ no の姿のレイヤー {名前: 隠す}. no までのピースを見せ、0 は全部を見せる."""
    return {s["layer"]: bool(no) and s["no"] > no for s in steps}


def restore(c, path) -> int:
    """元の柱と梁をもとのレイヤーへ戻し、ステップのレイヤーを全部見せる. 戻した数."""
    rec = read_json(path, {})
    steps = rec.get("steps") or []
    orig = rec.get("originals") or {}
    if steps:
        show_layers(c, visible_at(steps, 0))
    if orig:
        show_layers(c, {ORIGINAL_LAYER: False})
        c.tapir("SetDetailsOfElements", {"elementsWithDetails": [{"elementId": {"guid": g}, "details": {"layerIndex": int(i)}} for g, i in orig.items()]})
    rec["originals"] = {}
    rec["current"] = 0
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(orig)


def go_step(c, path, no: int) -> int:
    """ステップ no の姿にする（元の柱と梁は隠す）."""
    rec = read_json(path, {})
    steps = rec.get("steps") or []
    if not steps:
        print("鉄骨建て方: 先に「鉄骨建て方」でピースを置いてください")
        return 1
    no = max(1, min(len(steps), no))
    if not rec.get("originals") and rec.get("members"):
        show_layers(c, {ORIGINAL_LAYER: False})
        idx = layer_map(c)[ORIGINAL_LAYER]
        ds = c.get_details([{"elementId": {"guid": g}} for g in rec["members"]])
        rec["originals"] = {g: int(d["layerIndex"]) for g, d in zip(rec["members"], ds) if "layerIndex" in d}
        c.tapir("SetDetailsOfElements", {"elementsWithDetails": [{"elementId": {"guid": g}, "details": {"layerIndex": idx}} for g in rec["originals"]]})
    show_layers(c, {**visible_at(steps, no), ORIGINAL_LAYER: True})
    rec["current"] = no
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    s = steps[no - 1]
    print(f"鉄骨建て方: ステップ {no}/{len(steps)} {s['name']}（柱 {s['columns']}・梁 {s['beams']}ピース）")
    return 0


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.schedule import schedule, span, to_xlsx
    from ashiba.schedule_calendar import WorkCalendar
    from ashiba.steel_erection import (Options, beam_params, column_params, make_steps, parse_section, plan_pieces, schedule_tasks, to_markdown,
                                       to_sheet, zone_lines, zone_sheet)
    from ashiba.tapir_adapter import ArchicadClient
    from ashiba.xlsx_writer import Workbook
    from excav_run import _delete_alive

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ask", action="store_true", help="窓で決める")
    ap.add_argument("--sec", default="", help="符号の断面（C1=□-500×500×22,G1=H-… の形）")
    ap.add_argument("--every", type=int, default=2, help="節は何階ごと（既定 2）")
    ap.add_argument("--offset", type=float, default=1000.0, help="節の高さ mm（階の高さから）")
    ap.add_argument("--bracket", type=float, default=1000.0, help="梁を切る距離 mm（柱の中心から）")
    ap.add_argument("--base", type=float, default=0.0, help="下端の高さ m")
    ap.add_argument("--bp-over", dest="bp_over", type=float, default=100.0)
    ap.add_argument("--bp-t", dest="bp_t", type=float, default=36.0)
    ap.add_argument("--extra", type=float, default=5.0, help="重量の割増 %")
    ap.add_argument("--table", action="store_true", help="置かずに表だけ")
    ap.add_argument("--remove", action="store_true", help="置いたピースを消す")
    ap.add_argument("--zones", default="", help="工区の境の通り（X3,Y2 の形）")
    ap.add_argument("--order", default="工区", choices=("工区", "節"), help="工区: 工区ごとに上まで・節: 節ごとに全工区")
    ap.add_argument("--per-day", dest="per_day", type=float, default=30.0, help="1 日のピース数（クレーン 1 台）【目安・出典なし】")
    ap.add_argument("--cranes", type=int, default=1, help="クレーンの台数")
    ap.add_argument("--start", default=_dt.date.today().isoformat(), help="建方の始まり")
    ap.add_argument("--sat-off", dest="sat_off", action="store_true", help="土曜を休みにする")
    ap.add_argument("--step", type=int, default=None, help="その番号のステップの姿にする")
    ap.add_argument("--next", action="store_true", help="次のステップ")
    ap.add_argument("--prev", action="store_true", help="前のステップ")
    ap.add_argument("--undo", action="store_true", help="全部を見せて、元の柱と梁を戻す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = []
    step_path = R.OUT_DIR / STEPS
    if a.undo:
        print(f"鉄骨建て方: 全部を見せました（元の柱と梁 {restore(c, step_path)}個を戻しました）")
        return 0
    if a.next or a.prev or a.step is not None:
        cur = int(read_json(step_path, {}).get("current", 0) or 0)
        return go_step(c, step_path, a.step if a.step is not None else cur + (1 if a.next else -1))
    restore(c, step_path)                                 # 隠したままだと柱を読めず、ピースも消せない
    if a.remove:
        n = _delete_alive(c, rec)
        rec_path.write_text("[]", encoding="utf-8")
        step_path.write_text("{}", encoding="utf-8")
        print(f"鉄骨建て方: {n}個を消しました")
        return 0
    sel = c.get_selected_elements()
    ds = c.get_details(sel) if sel else []
    cols = [(e["elementId"]["guid"], d) for e, d in zip(sel, ds) if d.get("type") == "Column"]
    beams = [(e["elementId"]["guid"], d) for e, d in zip(sel, ds) if d.get("type") == "Beam"]
    if not cols:
        for ty, box in (("Column", cols), ("Beam", beams)):
            es = c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])
            if es:
                es = c.tapir("FilterElements", {"elements": es, "filters": ["IsVisibleByLayer", "IsVisibleIn3D"]}).get("elements", [])
            box[:] = [(e["elementId"]["guid"], d) for e, d in zip(es, c.get_details(es))] if es else []
    if not cols:
        print("鉄骨建て方: 柱がありません（柱と梁を選ぶか、表示してから押してください）")
        return 1
    table_path = R.OUT_DIR / TABLE
    table = read_table(table_path)
    for kv in a.sec.replace("、", ",").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            table[k.strip()] = v.strip()
    colz = [column_of(d) for _g, d in cols]
    beamz = [beam_of(d) for _g, d in beams]
    marks = sorted({x.mark for x in colz if x.z1 > a.base * 1000.0 + 1.0} | {x.mark for x in beamz if x.zc >= a.base * 1000.0})
    if a.ask and not ask(a, marks, table):
        print("鉄骨建て方: やめました")
        return 0
    write_table(table_path, {k: v for k, v in table.items() if v})
    secs = {k: s for k, v in table.items() if (s := parse_section(v))}
    bad = [f"{k}（{v}）" for k, v in table.items() if v and k not in secs]
    o = Options(a.every, a.offset, a.bracket, a.base * 1000.0, a.bp_over, a.bp_t, a.extra)
    used = [g for (g, _d), x in zip(cols, colz) if x.z1 > o.base + 1.0] + [g for (g, _d), x in zip(beams, beamz) if x.zc >= o.base]
    levels = [float(s["level"]) * 1000.0 for s in c.tapir("GetStories", {}).get("stories", [])]
    lx, ly = grid_lines(c)
    plan = plan_pieces(colz, beamz, levels, secs, o, lx, ly)
    if bad:
        plan.warnings.append("読めない断面: " + "・".join(bad))
    xs, ys, unknown = zone_lines(a.zones, sorted({(p.x, p.y) for p in plan.columns}), lx, ly)
    if unknown:
        plan.warnings.append("読めない通り: " + "・".join(unknown))
    steps = make_steps(plan, xs, ys, a.order)
    tasks = schedule_tasks(steps, a.per_day, a.cranes)
    try:
        start = _dt.date.fromisoformat(a.start)
    except ValueError:
        start = _dt.date.today()
        plan.warnings.append(f"建方の始まり {a.start} を読めないので今日からにしました")
    cal = WorkCalendar(sat_off=a.sat_off)
    schedule(tasks, cal, start)
    sched = R.OUT_DIR / "鉄骨建方工程表.xlsx"
    to_xlsx(tasks, cal, sched, "鉄骨建方工程表", [f"クレーン {a.cranes}台・1 日 {a.per_day:g}ピース（【目安】）・"
                                                  + ("工区ごとに上まで" if a.order != "節" else "節ごとに全工区")])
    wb = Workbook()
    to_sheet(wb, plan)
    zone_sheet(wb, steps)
    xl = R.OUT_DIR / "鉄骨節別重量表.xlsx"
    wb.save(xl)
    (R.OUT_DIR / "鉄骨節別重量表.md").write_text(to_markdown(plan), encoding="utf-8")
    placed = 0
    if not a.table:
        R.ensure_parts(c)
        part = R.versioned_part_name(PART)
        _delete_alive(c, rec)
        spec = {**R.SPEC, **R.load_spec_override()}
        pens = gdl_pens(parse_pens(spec.get("pens")), PART)
        items = [((p.x, p.y, p.z0), column_params(p, secs, o), p) for p in plan.columns] + [((p.x, p.y, p.z), beam_params(p, secs), p) for p in plan.beams]
        data = [{"libraryPartName": part, "coordinates": {"x": x / 1000.0, "y": y / 1000.0, "z": z / 1000.0}} for (x, y, z), _q, _p in items]
        els = []
        for i in range(0, len(data), 100):
            els += c.tapir("CreateObjects", {"objectsData": data[i:i + 100]}).get("elements", [])
        pairs = [(e, {**q, **pens}) for e, (_c, q, _p) in zip(els, items) if "elementId" in e]
        rec = [e["elementId"]["guid"] for e, _q in pairs]
        rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        placed = c.set_gdl_parameters_many(pairs)
        guid_of = {id(p): e["elementId"]["guid"] for e, (_c, _q, p) in zip(els, items) if "elementId" in e}
        names = {s.no: f"鉄骨_{s.no:02d}_{s.zone}工区{s.node}節" for s in steps}
        show_layers(c, {n: False for n in names.values()})
        idx = layer_map(c)
        moves = [{"elementId": {"guid": guid_of[id(p)]}, "details": {"layerIndex": idx[names[s.no]]}}
                 for s in steps for p in s.columns + s.beams if id(p) in guid_of]
        c.tapir("SetDetailsOfElements", {"elementsWithDetails": moves})
        step_path.write_text(json.dumps({"steps": [{"no": s.no, "name": s.name, "layer": names[s.no], "columns": len(s.columns), "beams": len(s.beams)} for s in steps],
                                         "members": used, "originals": {}, "current": 0}, ensure_ascii=False, indent=1), encoding="utf-8")
    nodes: dict = {}
    for p in plan.columns:
        nodes.setdefault(p.node, []).append(p.weight)
    heavy = [f"{n}節 最大 {max(w):.2f}t" for n, ws in sorted(nodes.items()) if (w := [x for x in ws if x is not None])]
    print(f"鉄骨建て方: 柱 {len(plan.columns)}ピース・梁 {len(plan.beams)}ピース" + (f"を置きました（{placed}個）" if not a.table else "（表だけ）")
          + (f"。{'・'.join(heavy)}" if heavy else "") + f"（{xl}）")
    s0, s1 = span(tasks)
    print(f"鉄骨建て方: {len(steps)}ステップ・{sum(t.days for t in tasks)}日（{s0}〜{s1}。{sched}）")
    for w in plan.warnings[:6]:
        print(f"鉄骨建て方: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
