"""鉄骨の建て方（パレットの「鉄骨建て方」）: 柱と梁をピースに分け、節ごとの重量表を出す（利用者の指定 2026-11-07）.

  python3 scripts/steel_run.py --ask                    # 窓で符号の断面と切り方を決めて置く
  python3 scripts/steel_run.py --sec "C1=□-500×500×22,G1=H-500×200×10×16"
  python3 scripts/steel_run.py --table                  # 置かずに表だけ
  python3 scripts/steel_run.py --remove                 # 置いたピースを消す

柱と梁を選んで押す（選んでいなければ表示中の全部）。元の柱と梁は触らず、部品 ashiba_steel のピースを重ねて置く。
重量表は ashiba_out/鉄骨節別重量表.xlsx、符号の断面は ashiba_out/鉄骨符号表.csv に残し、次からの既定にする.
"""

from __future__ import annotations

import csv
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
                   *[{"key": f"s_{m}", "label": f"断面 {m}", "kind": "text", "value": table.get(m, "")} for m in marks]],
        "buttons": [{"id": "go", "label": "置く"}, {"id": "table", "label": "表だけ"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") not in ("go", "table"):
        return False
    a.table = res.get("button") == "table"
    v = res.get("values") or {}
    for k in ("offset", "bracket", "base", "bp_over", "bp_t", "extra"):
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


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.steel_erection import Options, beam_params, column_params, parse_section, plan_pieces, to_markdown, to_sheet
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
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = []
    if a.remove:
        n = _delete_alive(c, rec)
        rec_path.write_text("[]", encoding="utf-8")
        print(f"鉄骨建て方: {n}個を消しました")
        return 0
    sel = c.get_selected_elements()
    ds = c.get_details(sel) if sel else []
    cols = [d for d in ds if d.get("type") == "Column"]
    beams = [d for d in ds if d.get("type") == "Beam"]
    if not cols:
        for ty, box in (("Column", cols), ("Beam", beams)):
            es = c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])
            if es:
                es = c.tapir("FilterElements", {"elements": es, "filters": ["IsVisibleByLayer", "IsVisibleIn3D"]}).get("elements", [])
            box[:] = c.get_details(es) if es else []
    if not cols:
        print("鉄骨建て方: 柱がありません（柱と梁を選ぶか、表示してから押してください）")
        return 1
    table_path = R.OUT_DIR / TABLE
    table = read_table(table_path)
    for kv in a.sec.replace("、", ",").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            table[k.strip()] = v.strip()
    colz = [column_of(d) for d in cols]
    beamz = [beam_of(d) for d in beams]
    marks = sorted({x.mark for x in colz if x.z1 > a.base * 1000.0 + 1.0} | {x.mark for x in beamz if x.zc >= a.base * 1000.0})
    if a.ask and not ask(a, marks, table):
        print("鉄骨建て方: やめました")
        return 0
    write_table(table_path, {k: v for k, v in table.items() if v})
    secs = {k: s for k, v in table.items() if (s := parse_section(v))}
    bad = [f"{k}（{v}）" for k, v in table.items() if v and k not in secs]
    o = Options(a.every, a.offset, a.bracket, a.base * 1000.0, a.bp_over, a.bp_t, a.extra)
    levels = [float(s["level"]) * 1000.0 for s in c.tapir("GetStories", {}).get("stories", [])]
    lx, ly = grid_lines(c)
    plan = plan_pieces(colz, beamz, levels, secs, o, lx, ly)
    if bad:
        plan.warnings.append("読めない断面: " + "・".join(bad))
    wb = Workbook()
    to_sheet(wb, plan)
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
        items = [((p.x, p.y, p.z0), column_params(p, secs, o)) for p in plan.columns] + [((p.x, p.y, p.z), beam_params(p, secs)) for p in plan.beams]
        data = [{"libraryPartName": part, "coordinates": {"x": x / 1000.0, "y": y / 1000.0, "z": z / 1000.0}} for (x, y, z), _q in items]
        els = []
        for i in range(0, len(data), 100):
            els += c.tapir("CreateObjects", {"objectsData": data[i:i + 100]}).get("elements", [])
        pairs = [(e, {**q, **pens}) for e, (_p, q) in zip(els, items) if "elementId" in e]
        rec = [e["elementId"]["guid"] for e, _q in pairs]
        rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        placed = c.set_gdl_parameters_many(pairs)
    nodes: dict = {}
    for p in plan.columns:
        nodes.setdefault(p.node, []).append(p.weight)
    heavy = [f"{n}節 最大 {max(w):.2f}t" for n, ws in sorted(nodes.items()) if (w := [x for x in ws if x is not None])]
    print(f"鉄骨建て方: 柱 {len(plan.columns)}ピース・梁 {len(plan.beams)}ピース" + (f"を置きました（{placed}個）" if not a.table else "（表だけ）")
          + (f"。{'・'.join(heavy)}" if heavy else "") + f"（{xl}）")
    for w in plan.warnings[:6]:
        print(f"鉄骨建て方: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
