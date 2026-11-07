"""鉄骨の建て方（パレットの「鉄骨建て方」）: 柱と梁をピースに分け、節ごとの重量表を出す（利用者の指定 2026-11-07）.

  python3 scripts/steel_run.py --ask                    # 窓で符号の断面と切り方を決めて置く
  python3 scripts/steel_run.py --sec "C1=□-500×500×22,G1=H-500×200×10×16"
  python3 scripts/steel_run.py --table                  # 置かずに表だけ
  python3 scripts/steel_run.py --remove                 # 置いたピースを消す
  python3 scripts/steel_run.py --zones X3 --order 工区  # 工区の境の通りと建てる順（工区: 建て逃げ・節: 積み上げ）
  python3 scripts/steel_run.py --next / --prev / --step 3 / --undo   # 工区・節のステップの姿にする・全部に戻す
  python3 scripts/steel_run.py --machine                # 選んだ重機を今のステップへ（工区が複数なら工区ごと、1 つなら節ごと）
  python3 scripts/steel_run.py --machine-off            # 重機の登録を外す（選ばなければ全部）
  python3 scripts/steel_run.py --gear                   # 仮設材（溶接足場・ボルト足場・タラップ・ネットほか）を種類ごとのレイヤーに置く
  python3 scripts/steel_run.py --sheet                  # 建て方検討図（節ごとに A3 の PDF とレイアウト。クレーンを選ぶと揚重の判定が入る）

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
DRAWING = "鉄骨建て方_図.json"
ORIGINAL_LAYER = "鉄骨_元の柱梁"
MACHINE_LAYER = "鉄骨重機_"
MACHINE_PARTS = ("ashiba_crane", "ashiba_machine", "ashiba_tower")


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


PLATE_CHOICES = {"自動": "柱の形で（角形・丸は通し、H形は水平スチフナ）", "内": "内ダイアフラム", "なし": "なし"}


def zones_of(c) -> list:
    """名前に「工区」を含むゾーン → Zone の並び（番号の順）. 部屋のゾーンは使わない."""
    from ashiba.steel_erection import Zone

    es = c.tapir("GetElementsByType", {"elementType": "Zone"}).get("elements", [])
    rows = []
    for d in c.get_details(es) if es else []:
        q = d.get("details") or {}
        if "工区" not in str(q.get("name", "")):
            continue
        pts = [(p["x"] * 1000.0, p["y"] * 1000.0) for p in q.get("polygonOutline") or []]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        holes = [[(p["x"] * 1000.0, p["y"] * 1000.0) for p in (h.get("polygonOutline") if isinstance(h, dict) else h) or []] for h in q.get("holes") or []]
        rows.append((str(q.get("numberStr", "")), str(q.get("name")), pts, holes))

    def key(r):
        digits = "".join(ch for ch in r[0] if ch.isdigit())
        return (int(digits) if digits else 10 ** 6, r[0], r[1])

    return [Zone(i, n, pts, holes) for i, (_num, n, pts, holes) in enumerate(sorted(rows, key=key), 1)]


def ask(a, marks: list, table: dict) -> bool:
    """窓: 切り方とプレート、符号の断面. やめたら False."""
    from form_dialog import show_form

    res = show_form({
        "title": "鉄骨建て方",
        "intro": "柱は階の高さ＋指定の高さで節に切り、梁は柱の中心から指定の距離で切って端（ブラケット）と継手の添え板を柱と一体にします。断面が空の符号は仮の形で描き、重量は出しません。"
                 "名前に「工区」を含むゾーンがあれば、ゾーンで工区を分けます（番号の順に建てる）。"
                 "断面は H-500×200×10×16・□-500×500×22・P-318.5×10 の形で。",
        "fields": [{"key": "every", "label": "節は何階ごと", "kind": "number", "value": f"{a.every}"},
                   {"key": "offset", "label": "節の高さ mm（階の高さから）", "kind": "number", "value": f"{a.offset:g}"},
                   {"key": "bracket", "label": "梁を切る距離 mm（柱の中心から）", "kind": "number", "value": f"{a.bracket:g}"},
                   {"key": "base", "label": "下端の高さ m（これより下は見ない）", "kind": "number", "value": f"{a.base:g}"},
                   {"key": "bp_over", "label": "ベースプレートのはみ出し mm【目安】", "kind": "number", "value": f"{a.bp_over:g}"},
                   {"key": "bp_t", "label": "ベースプレートの厚さ mm【目安】", "kind": "number", "value": f"{a.bp_t:g}"},
                   {"key": "diaphragm", "label": "ダイアフラム", "kind": "choice", "options": list(PLATE_CHOICES), "value": PLATE_CHOICES.get(a.diaphragm, "")},
                   {"key": "extra", "label": "重量の割増 %（ボルト・溶接）【目安】", "kind": "number", "value": f"{a.extra:g}"},
                   {"key": "zones", "label": "工区の境の通り（X3,Y2 の形。空＝1工区）", "kind": "text", "value": a.zones},
                   {"key": "order", "label": "建てる順", "kind": "choice", "options": ["工区ごとに上まで（建て逃げ）", "節ごとに全工区（積み上げ）"],
                    "value": "節ごとに全工区（積み上げ）" if a.order == "節" else "工区ごとに上まで（建て逃げ）"},
                   {"key": "per_day", "label": "1 日のピース数（クレーン 1 台）【目安・出典なし】", "kind": "number", "value": f"{a.per_day:g}"},
                   {"key": "cranes", "label": "クレーンの台数", "kind": "number", "value": f"{a.cranes}"},
                   {"key": "start", "label": "建方の始まり（2027-04-01 の形）", "kind": "text", "value": a.start},
                   {"key": "sat_off", "label": "土曜を休みにする", "kind": "check", "value": "1" if a.sat_off else "0"},
                   {"key": "floor_order", "label": "節の中のデッキの階の順", "kind": "choice", "options": ["未定", "上から", "下から", "階ごとに追いかけ"], "value": a.floor_order},
                   {"key": "lag", "label": "デッキの遅れ（節の数）【目安】", "kind": "number", "value": f"{a.lag}"},
                   {"key": "work_stage", "label": "作業床に数える段階", "kind": "choice", "options": ["本付け（納め完了）", "仮留め"],
                    "value": "仮留め" if a.work_stage == 2 else "本付け（納め完了）"},
                   {"key": "done_node", "label": "納め完了の節（この節まで。0＝なし）", "kind": "number", "value": f"{a.done_node}"},
                   {"key": "cast_node", "label": "打設済みの節（この節まで。0＝なし）", "kind": "number", "value": f"{a.cast_node}"},
                   *[{"key": f"s_{m}", "label": f"断面 {m}", "kind": "text", "value": table.get(m, "")} for m in marks]],
        "buttons": [{"id": "go", "label": "置く"}, {"id": "table", "label": "表だけ"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") not in ("go", "table"):
        return False
    a.table = res.get("button") == "table"
    v = res.get("values") or {}
    a.zones = str(v.get("zones") or "").strip()
    a.diaphragm = next((k for k, x in PLATE_CHOICES.items() if x == v.get("diaphragm")), a.diaphragm)
    a.order = "節" if str(v.get("order", "")).startswith("節") else "工区"
    a.start = str(v.get("start") or a.start).strip()
    a.sat_off = str(v.get("sat_off")) in ("1", "true", "True")
    a.floor_order = str(v.get("floor_order") or a.floor_order)
    a.work_stage = 2 if str(v.get("work_stage", "")).startswith("仮留め") else 3
    for k in ("lag", "done_node", "cast_node"):
        try:
            setattr(a, k, max(0, int(float(str(v.get(k))))))
        except (TypeError, ValueError):
            pass
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


def unit_layer(steps: list, no: int) -> str:
    """ステップ no の重機のレイヤー. 工区が複数なら工区ごと、1 つなら節ごと（仮設材の見せ方と同じ）."""
    s = next(x for x in steps if x["no"] == no)
    many = len({x.get("zone") for x in steps}) > 1
    return MACHINE_LAYER + (s["name"].split()[0] if many else s["name"].replace(" ", ""))


def machine_view(rec: dict, no: int) -> dict:
    """重機のレイヤー {名前: 隠す}. 0 は全部を見せる. 登録していない重機はレイヤーが別なので、どのステップでも見えたまま."""
    now = unit_layer(rec.get("steps") or [], no) if no else ""
    return {m["unit"]: bool(no) and m["unit"] != now for m in rec.get("machines") or []}


def machine(c, path) -> int:
    """選んだ重機を今のステップへ登録する: 単位のレイヤーへ移す. もとのレイヤーは控える."""
    rec = read_json(path, {})
    steps = rec.get("steps") or []
    no = int(rec.get("current") or 0)
    if not steps or not no:
        print("鉄骨建て方: 先に「鉄骨の次のステップ」で、重機を置くステップへ送ってください")
        return 1
    sel = c.get_selected_elements()
    ds = c.get_details(sel) if sel else []
    picks = [(e, d) for e, d in zip(sel, ds) if d.get("type") == "Object"
             and str(((d.get("details") or {}).get("libPart") or {}).get("name", "")).startswith(MACHINE_PARTS)]
    if not picks:
        print("鉄骨建て方: 重機を選んで押してください（クレーン・クローラクレーン・タワークレーン・重機）")
        return 1
    unit = unit_layer(steps, no)
    old = {m["guid"]: m for m in rec.get("machines") or []}
    show_layers(c, {unit: False})
    idx = layer_map(c)[unit]
    c.tapir("SetDetailsOfElements", {"elementsWithDetails": [{"elementId": e["elementId"], "details": {"layerIndex": idx}} for e, _d in picks]})
    new = [{"guid": e["elementId"]["guid"], "unit": unit, "layer": old[e["elementId"]["guid"]]["layer"] if e["elementId"]["guid"] in old else int(d["layerIndex"])}
           for e, d in picks]
    keep = {m["guid"] for m in new}
    rec["machines"] = [m for m in old.values() if m["guid"] not in keep] + new
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"鉄骨建て方: 重機 {len(new)}台を「{unit[len(MACHINE_LAYER):]}」に登録しました")
    return 0


def machines_back(c, rec: dict, only: set | None = None) -> int:
    """重機をもとのレイヤーへ戻し、登録を外す. 重機そのものは消さない. 戻した数."""
    rows = [m for m in rec.get("machines") or [] if only is None or m["guid"] in only]
    if rows:
        show_layers(c, {m["unit"]: False for m in rows})
        c.tapir("SetDetailsOfElements", {"elementsWithDetails": [{"elementId": {"guid": m["guid"]}, "details": {"layerIndex": m["layer"]}} for m in rows]})
    rec["machines"] = [m for m in rec.get("machines") or [] if m not in rows]
    return len(rows)


def step_lifters(c, d: dict, rec: dict) -> tuple:
    """登録したクレーン → ({(工区, 節): [判定の関数]}, [{name, x, y, nodes}]). クレーンでない重機は見ない."""
    from crane_check import find_crane, lifter

    steps = rec.get("steps") or []
    fs: dict = {}
    infos: dict = {}
    for m in rec.get("machines") or []:
        el = {"elementId": {"guid": m["guid"]}}
        try:
            dt = c.get_details([el])[0]
        except Exception:                                  # noqa: BLE001 消されていれば飛ばす
            continue
        crane, cd = find_crane(c, [el], [dt])
        if crane is None or crane["elementId"]["guid"] != m["guid"]:   # 見つからないと控えの別のクレーンが返る
            continue
        f, info = lifter(c, crane, cd)
        fs.setdefault(m["unit"], []).append(tagged(f, info))
        infos.setdefault(m["unit"], []).append(info)
    by: dict = {}
    cranes: list = []
    seen: dict = {}
    for s in d.get("steps") or []:
        unit = unit_layer(steps, s["no"]) if any(x["no"] == s["no"] for x in steps) else ""
        if unit in fs:
            by[(s["zone"], s["node"])] = fs[unit]
            for info in infos[unit]:
                k = (info["x"], info["y"])
                if k not in seen:
                    seen[k] = {**info, "nodes": []}
                    cranes.append(seen[k])
                if s["node"] not in seen[k]["nodes"]:
                    seen[k]["nodes"].append(s["node"])
    return by, cranes


def tagged(f, info: dict):
    """判定の結果にクレーンの位置を足す（図の作業半径の中心）."""
    return lambda *a: {**f(*a), "cx": info["x"], "cy": info["y"]}


def restore(c, path) -> int:
    """元の柱と梁をもとのレイヤーへ戻し、ステップのレイヤーを全部見せる. 戻した数."""
    rec = read_json(path, {})
    steps = rec.get("steps") or []
    orig = rec.get("originals") or {}
    if steps:
        show_layers(c, {**visible_at(steps, 0), **machine_view(rec, 0)})
    if orig:
        show_layers(c, {ORIGINAL_LAYER: False})
        c.tapir("SetDetailsOfElements", {"elementsWithDetails": [{"elementId": {"guid": g}, "details": {"layerIndex": int(i)}} for g, i in orig.items()]})
    set_gear(c, rec, 0)
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
    show_layers(c, {**visible_at(steps, no), ORIGINAL_LAYER: True, **machine_view(rec, no)})
    set_gear(c, rec, no)
    rec["current"] = no
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    s = steps[no - 1]
    print(f"鉄骨建て方: ステップ {no}/{len(steps)} {s['name']}（柱 {s['columns']}・梁 {s['beams']}ピース）")
    return 0


def drawing_data(plan, steps, lx, ly, xs, ys, rows, deck_records, zones=()) -> dict:
    """建て方検討図の控え（mm）."""
    return {"columns": [{"node": p.node, "zone": p.zone, "grid": p.grid, "marks": p.marks, "x": p.x, "y": p.y, "z0": p.z0, "z1": p.z1, "w": p.w, "d": p.d,
                         "ang": p.ang, "weight": p.weight} for p in plan.columns],
            "beams": [{"mark": b.mark, "x": b.x, "y": b.y, "z": b.z, "h": b.h, "w": b.w, "ang": b.ang, "length": b.length, "node": b.node, "zone": b.zone,
                       "weight": b.weight} for b in plan.beams],
            "steps": [{"no": s.no, "zone": s.zone, "zone_name": s.zone_name or f"{s.zone}工区", "node": s.node, "columns": len(s.columns), "beams": len(s.beams),
                       "weight": s.weight} for s in steps],
            "zones": [{"name": z.name, "outline": [list(p) for p in z.outline], "holes": [[list(p) for p in h] for h in z.holes]} for z in zones],
            "lines_x": [list(x) for x in lx], "lines_y": [list(x) for x in ly], "xs": xs, "ys": ys,
            "deck": [{**d, "rope": r.rope} for d, r in zip(deck_records, rows)]}


def judge_pieces(d: dict, f, by: dict | None = None) -> None:
    """節のピースに揚重の判定を入れる. by は {(工区, 節): [判定の関数]}（ステップに登録したクレーン）で、無い工区は f. 2 台なら吊れて近いほう."""
    import math

    def lift(p: dict, *a) -> None:
        fs = (by or {}).get((p.get("zone"), p["node"])) or ([f] if f else [])
        if fs:
            p["lift"] = min((g(*a) for g in fs), key=lambda r: (r.get("res") != "揚重可能", r.get("radius") or 0.0))

    for p in d["columns"]:
        lift(p, p["x"], p["y"], p["z1"], p["weight"], p["grid"])
    for b in d["beams"]:
        a = math.radians(b["ang"])
        lift(b, b["x"] + b["length"] / 2.0 * math.cos(a), b["y"] + b["length"] / 2.0 * math.sin(a), b["z"] + b["h"] / 2.0, b["weight"], b["mark"])


def set_gear(c, rec: dict, no: int) -> None:
    """仮設材の表示: ステップ no の工区の分だけを描く（0 は全部）. 仮設材は工区を移るときに使い回す（利用者の指定 2026-11-07）.
    工区が 1 つなら節ごとに出し分ける（そのステップの分だけ）. 工区を持たない前の版の控えは、ステップ no までを描く."""
    items = rec.get("gear") or []
    steps = rec.get("steps") or []
    zone = next((s.get("zone") for s in steps if s.get("no") == no), None)
    single = len({s.get("zone") for s in steps}) == 1

    def on(g: dict) -> bool:
        if not no:
            return True
        if zone is None or "zone" not in g:
            return g["step"] <= no
        return g["step"] == no if single else g["zone"] == zone

    if items:
        c.set_gdl_parameters_many([({"elementId": {"guid": g["guid"]}}, {"sgOn": on(g)}) for g in items])


def gear_objects(d: dict) -> tuple:
    """控え → steel_gear が読む形（Plan と Step の代わり）."""
    from types import SimpleNamespace as NS

    cols = [NS(**{"ang": 0.0, **c}) for c in d["columns"]]          # 前の版の控えには向きと梁の幅が無い
    beams = [NS(**{"w": 200.0, **b}) for b in d["beams"]]
    steps = [NS(no=s["no"], zone=s["zone"], zone_name=s.get("zone_name", ""), node=s["node"], columns=[c for c in cols if (c.zone, c.node) == (s["zone"], s["node"])],
                beams=[b for b in beams if (b.zone, b.node) == (s["zone"], s["node"])]) for s in d["steps"]]
    return NS(columns=cols, beams=beams), steps


def gear(c, R) -> int:
    """仮設材を置く: 種類ごとのレイヤー「鉄骨仮設_…」を作り、節とピースから部品 ashiba_sgear を置く. 前に置いた分は控えで消す."""
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.steel_erection import parse_section, splice_of
    from ashiba.steel_gear import order_rows, plan_gear, to_sheet as gear_sheet
    from ashiba.xlsx_writer import Workbook
    from excav_run import _delete_alive

    d = read_json(R.OUT_DIR / DRAWING, {})
    if not d.get("columns"):
        print("鉄骨の仮設材: 先に「鉄骨建て方」で表か置くまで進めてください")
        return 1
    secs = {k: s for k, v in read_table(R.OUT_DIR / TABLE).items() if (s := parse_section(v))}
    plan, steps = gear_objects(d)
    items = plan_gear(plan, steps, secs, splice_of)
    step_path = R.OUT_DIR / STEPS
    rec = read_json(step_path, {})
    old = [g["guid"] for g in rec.get("gear") or []]
    if old:
        _delete_alive(c, old)
    R.ensure_parts(c)
    part = R.versioned_part_name("ashiba_sgear")
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), "ashiba_sgear")
    data = [{"libraryPartName": part, "coordinates": {"x": g.x / 1000.0, "y": g.y / 1000.0, "z": g.z / 1000.0}} for g in items]
    els = []
    for i in range(0, len(data), 100):
        els += c.tapir("CreateObjects", {"objectsData": data[i:i + 100]}).get("elements", [])
    pairs = [(e, {"sgK": g.kind, "sgOn": True, "sgName": g.name, **g.params, **pens}) for e, g in zip(els, items) if "elementId" in e]
    done = c.set_gdl_parameters_many(pairs)
    layers = sorted({g.layer for g in items})
    show_layers(c, {n: False for n in layers})
    idx = layer_map(c)
    moves = [{"elementId": e["elementId"], "details": {"layerIndex": idx[g.layer]}} for e, g in zip(els, items) if "elementId" in e]
    c.tapir("SetDetailsOfElements", {"elementsWithDetails": moves})
    rec["gear"] = [{"guid": e["elementId"]["guid"], "step": g.step, "zone": g.zone} for e, g in zip(els, items) if "elementId" in e]
    step_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    if rec.get("current"):
        set_gear(c, rec, int(rec["current"]))
    wb = Workbook()
    gear_sheet(wb, items, {s.zone: s.zone_name for s in steps})
    xl = R.OUT_DIR / "鉄骨仮設材.xlsx"
    wb.save(xl)
    print(f"鉄骨の仮設材: {done}個を置きました（{len(layers)}レイヤー。{xl}）")
    for kind, name, _n, need, _kg in order_rows(items)[1]:
        print(f"  {kind}: {name} 手配 {need}")
    return 0


def sheet(c, R) -> int:
    """建て方検討図: 控え 鉄骨建て方_図.json から節ごとの A3 の PDF とレイアウト「建て方 n」."""
    from ashiba.form_drawings import to_pdf
    from ashiba.steel_sheets import SERIES, SUBSET, build_html, page_list
    from crane_check import find_crane, lifter

    d = read_json(R.OUT_DIR / DRAWING, {})
    if not d.get("columns"):
        print("建て方検討図: 先に「鉄骨建て方」で表か置くまで進めてください")
        return 1
    if c.current_window_type() not in ("FloorPlan", "3DModel"):   # レイアウトが前面だと選択が読めず、図もそこに描かれる
        from ashiba.elevation_sections import activate_floor_plan

        activate_floor_plan(c)
    by, cranes = step_lifters(c, d, read_json(R.OUT_DIR / STEPS, {}))
    d["cranes"] = cranes
    crane = f = None
    if not by or any((s["zone"], s["node"]) not in by for s in d["steps"]):   # 登録が無い工区は、選んだクレーンで見る
        sel = c.get_selected_elements()
        crane, cd = find_crane(c, sel, c.get_details(sel) if sel else [])
    if crane is not None:
        f, info = lifter(c, crane, cd)
        f = tagged(f, info)
        d["crane"] = info
    if f or by:
        judge_pieces(d, f, by)
    project = str({**R.SPEC, **R.load_spec_override()}.get("project_name") or "")
    html_path = R.OUT_DIR / "建て方検討図.html"
    html_path.write_text(build_html(d, project), encoding="utf-8")
    pdf = R.OUT_DIR / "建て方検討図.pdf"
    ok = to_pdf(html_path, pdf)
    pages = page_list(d)
    print(f"建て方検討図: {len(pages)}節（{pdf if ok else html_path}）" + ("" if crane is not None or by else "。クレーンが無いので揚重の判定は入っていません"))
    try:
        from ashiba.form_layout import place_layouts

        res = place_layouts(c, pages, SERIES, SUBSET)
        print(f"  レイアウト: {len(res.layouts)}枚（サブセット「{SUBSET}」）")
        for x in res.notes:
            print(f"  注意: {x}")
    except Exception as ex:  # noqa: BLE001 Archicad が無くても PDF は残す
        print(f"  レイアウト: 置けませんでした（{ex}）")
    return 0


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba import deck_stage as D
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
    ap.add_argument("--diaphragm", default="自動", choices=("自動", "内", "なし"), help="自動: 角形・丸は通し、H形は水平スチフナ")
    ap.add_argument("--order", default="工区", choices=("工区", "節"), help="工区: 工区ごとに上まで・節: 節ごとに全工区")
    ap.add_argument("--per-day", dest="per_day", type=float, default=30.0, help="1 日のピース数（クレーン 1 台）【目安・出典なし】")
    ap.add_argument("--cranes", type=int, default=1, help="クレーンの台数")
    ap.add_argument("--start", default=_dt.date.today().isoformat(), help="建方の始まり")
    ap.add_argument("--sat-off", dest="sat_off", action="store_true", help="土曜を休みにする")
    ap.add_argument("--floor-order", dest="floor_order", default="未定", choices=("未定", "上から", "下から", "階ごとに追いかけ"), help="節の中のデッキの階の順")
    ap.add_argument("--lag", type=int, default=1, help="デッキの遅れ（節の数）")
    ap.add_argument("--work-stage", dest="work_stage", type=int, default=3, choices=(2, 3), help="作業床に数える段階（2 仮留め・3 本付け）")
    ap.add_argument("--done-node", dest="done_node", type=int, default=0, help="納め完了の節")
    ap.add_argument("--cast-node", dest="cast_node", type=int, default=0, help="打設済みの節")
    ap.add_argument("--step", type=int, default=None, help="その番号のステップの姿にする")
    ap.add_argument("--next", action="store_true", help="次のステップ")
    ap.add_argument("--prev", action="store_true", help="前のステップ")
    ap.add_argument("--undo", action="store_true", help="全部を見せて、元の柱と梁を戻す")
    ap.add_argument("--sheet", action="store_true", help="建て方検討図（節ごと）")
    ap.add_argument("--gear", action="store_true", help="仮設材を置く")
    ap.add_argument("--machine", action="store_true", help="選んだ重機を今のステップへ登録する")
    ap.add_argument("--machine-off", dest="machine_off", action="store_true", help="重機の登録を外す（選ばなければ全部）")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = []
    step_path = R.OUT_DIR / STEPS
    if a.sheet:
        return sheet(c, R)
    if a.gear:
        return gear(c, R)
    if a.machine:
        return machine(c, step_path)
    if a.machine_off:
        r0 = read_json(step_path, {})
        sel = {e["elementId"]["guid"] for e in c.get_selected_elements()}
        n = machines_back(c, r0, (sel & {m["guid"] for m in r0.get("machines") or []}) or None)
        step_path.write_text(json.dumps(r0, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"鉄骨建て方: 重機 {n}台の登録を外しました")
        return 0
    if a.undo:
        print(f"鉄骨建て方: 全部を見せました（元の柱と梁 {restore(c, step_path)}個を戻しました）")
        return 0
    if a.next or a.prev or a.step is not None:
        cur = int(read_json(step_path, {}).get("current", 0) or 0)
        return go_step(c, step_path, a.step if a.step is not None else cur + (1 if a.next else -1))
    restore(c, step_path)                                 # 隠したままだと柱を読めず、ピースも消せない
    if a.remove:
        back = machines_back(c, read_json(step_path, {}))
        if back:
            print(f"鉄骨建て方: 重機 {back}台はもとのレイヤーへ戻しました（消していません）")
        n = _delete_alive(c, rec + [g["guid"] for g in read_json(step_path, {}).get("gear") or []])
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
    o = Options(a.every, a.offset, a.bracket, a.base * 1000.0, a.bp_over, a.bp_t, a.extra, a.diaphragm)
    used = [g for (g, _d), x in zip(cols, colz) if x.z1 > o.base + 1.0] + [g for (g, _d), x in zip(beams, beamz) if x.zc >= o.base]
    levels = [float(s["level"]) * 1000.0 for s in c.tapir("GetStories", {}).get("stories", [])]
    lx, ly = grid_lines(c)
    plan = plan_pieces(colz, beamz, levels, secs, o, lx, ly)
    if not plan.columns:
        print(f"鉄骨建て方: 下端 {a.base:g}m より上に柱がありません（柱が隠れていないか、下端の高さを確かめてください）")
        return 1
    if bad:
        plan.warnings.append("読めない断面: " + "・".join(bad))
    xs, ys, unknown = zone_lines(a.zones, sorted({(p.x, p.y) for p in plan.columns}), lx, ly)
    if unknown:
        plan.warnings.append("読めない通り: " + "・".join(unknown))
    zones = zones_of(c)
    if zones:
        print("鉄骨建て方: 工区はゾーンで分けます（" + "・".join(z.name for z in zones) + "）")
        if xs or ys:
            plan.warnings.append("工区の境の通りは使いません（ゾーンを優先しました）")
        xs, ys = [], []
    steps = make_steps(plan, xs, ys, a.order, zones)
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
    rows = D.floor_rows(steps, o.base, D.DeckOptions(a.floor_order, a.lag, a.work_stage, a.done_node, a.cast_node),
                        D.bay_short([p.x for p in plan.columns], [p.y for p in plan.columns]))
    D.to_sheet(wb, rows)
    (R.OUT_DIR / "鉄骨デッキ判定.md").write_text(D.to_markdown(rows), encoding="utf-8")
    (R.OUT_DIR / "鉄骨デッキ判定.json").write_text(json.dumps({"rows": D.to_records(rows), "xs": xs, "ys": ys}, ensure_ascii=False, indent=1), encoding="utf-8")
    (R.OUT_DIR / DRAWING).write_text(json.dumps(drawing_data(plan, steps, lx, ly, xs, ys, rows, D.to_records(rows), zones), ensure_ascii=False, indent=1), encoding="utf-8")
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
        names = {s.no: f"鉄骨_{s.no:02d}_" + s.name.replace(" ", "") for s in steps}
        show_layers(c, {n: False for n in names.values()})
        idx = layer_map(c)
        moves = [{"elementId": {"guid": guid_of[id(p)]}, "details": {"layerIndex": idx[names[s.no]]}}
                 for s in steps for p in s.columns + s.beams if id(p) in guid_of]
        c.tapir("SetDetailsOfElements", {"elementsWithDetails": moves})
        old_gear = read_json(step_path, {}).get("gear") or []
        old_machines = read_json(step_path, {}).get("machines") or []
        step_path.write_text(json.dumps({"steps": [{"no": s.no, "zone": s.zone, "name": s.name, "layer": names[s.no], "columns": len(s.columns), "beams": len(s.beams)} for s in steps],
                                         "members": used, "originals": {}, "current": 0, "gear": old_gear, "machines": old_machines}, ensure_ascii=False, indent=1), encoding="utf-8")
        now_units = {unit_layer([{"no": s.no, "zone": s.zone, "name": s.name} for s in steps], s.no) for s in steps}
        lost = sorted({m["unit"][len(MACHINE_LAYER):] for m in old_machines if m["unit"] not in now_units})
        if lost:
            plan.warnings.append("工区や節が変わり、重機の登録が合いません: " + "・".join(lost) + "（ステップへ送って登録し直してください）")
    nodes: dict = {}
    for p in plan.columns:
        nodes.setdefault(p.node, []).append(p.weight)
    heavy = [f"{n}節 最大 {max(w):.2f}t" for n, ws in sorted(nodes.items()) if (w := [x for x in ws if x is not None])]
    print(f"鉄骨建て方: 柱 {len(plan.columns)}ピース・梁 {len(plan.beams)}ピース" + (f"を置きました（{placed}個）" if not a.table else "（表だけ）")
          + (f"。{'・'.join(heavy)}" if heavy else "") + f"（{xl}）")
    s0, s1 = span(tasks)
    print(f"鉄骨建て方: {len(steps)}ステップ・{sum(t.days for t in tasks)}日（{s0}〜{s1}。{sched}）")
    cnt = Counter(r.rope for r in rows if r.current)
    print("鉄骨建て方: 親綱の判定 " + "・".join(f"{k} {v}" for k, v in cnt.items()) + "（鉄骨デッキ判定.md）")
    for w in plan.warnings[:6]:
        print(f"鉄骨建て方: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
