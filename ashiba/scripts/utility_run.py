"""仮設電気・給排水（パレットの「仮設電気・給排水」「仮設電気・給排水を消す」）.

利用者の指定（2026-11-02）「各図面を参考にして、図面かボタンを追加してちょ」の続き（施工図の手引きの総合仮設計画図 p.23〜24）。
平面に線を引いて選び、窓で種類を選んで押す:
- 給水管・排水管・地中埋設電線・架空電線: 線のとおりに（排水管は線の向き＝流れ。終わりに矢じり）
- キュービクル・分電盤（電灯・動力・電灯動力）・量水器・止水栓・仮設便所・沈砂槽: 線の始め＝芯、線の向き＝向き
2D の線・塗り・文字をレイヤー「仮設_電気給排水」に置く。帳票 ashiba_out/仮設電気給排水.md（排水の落差・架空電線とクレーンの
離隔・数量）。判定と出典は src/ashiba/utility.py.

  python3 scripts/utility_run.py                                 # 窓で種類を選ぶ
  python3 scripts/utility_run.py --kind 排水管 --dia 100
  python3 scripts/utility_run.py --kind 架空電線 --volt 高圧 --wires 3
  python3 scripts/utility_run.py --kind キュービクル
  python3 scripts/utility_run.py --remove                        # 置いた記号を消す（控えの GUID だけ）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LAYER = "仮設_電気給排水"
RECORD = "仮設電気給排水.json"
DASH = {"chain": "4 1 0.6 1", "dash": "2 1"}


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from form_dialog import show_form
    from guide_lines import selected_guides
    from kakoi_run import chains

    from ashiba.elevation_sections import activate_floor_plan
    from ashiba.form_layout import line_type_indexes, solid_fill_id
    from ashiba.tapir_adapter import ArchicadClient
    from ashiba.utility import KINDS, VOLTAGES, Item, check, drawing, report

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", default=None, choices=KINDS, help="種類")
    ap.add_argument("--dia", type=float, default=None, help="管径 mm（給水 25・排水 100）")
    ap.add_argument("--volt", default="低圧", choices=list(VOLTAGES), help="架空電線の電圧の区分")
    ap.add_argument("--kv", type=float, default=0.0, help="特別高圧の電圧 kV（6万V 以上は離隔を足す）")
    ap.add_argument("--wires", type=int, default=3, help="架空電線の本数")
    ap.add_argument("--remove", action="store_true", help="置いた記号を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    try:
        activate_floor_plan(c)                       # 平面図に描く（前面がレイアウトだとそこへ描かれる）
    except Exception:
        pass
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete(c, [g for v in rec.values() for g in v.get("guids", [])])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"仮設電気・給排水: {n}個を消しました")
        return 0
    segs = [(key, [tuple(p) for p in pts]) for key, pts, _closed in chains(selected_guides(c))]
    if not segs:
        print("仮設電気・給排水: 線を引いて選んでから押してください（管・電線は線のとおり、機器は線の始め＝芯・向き＝向き）")
        return 1
    if a.kind is None:
        res = show_form({"title": "仮設電気・給排水", "intro": f"線 {len(segs)}本。管・電線は線のとおり（排水は線の向き＝流れ）、機器は線の始め＝芯。",
                         "fields": [{"key": "kind", "label": "種類", "kind": "choice", "options": list(KINDS), "value": KINDS[0]},
                                    {"key": "dia", "label": "管径 mm（空＝給水 25・排水 100）", "kind": "number", "value": ""},
                                    {"key": "volt", "label": "架空電線の電圧", "kind": "choice", "options": list(VOLTAGES), "value": "低圧"},
                                    {"key": "wires", "label": "架空電線の本数", "kind": "number", "value": "3"}],
                         "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
        if not res or res.get("button") != "place":
            print("仮設電気・給排水: やめました")
            return 0
        v = res.get("values") or {}
        a.kind = str(v.get("kind") or KINDS[0])
        a.dia = float(v["dia"]) if str(v.get("dia") or "").strip() else None
        a.volt = str(v.get("volt") or "低圧")
        a.wires = int(float(v.get("wires") or 3))
    dia = a.dia if a.dia is not None else {"給水管": 25.0, "排水管": 100.0}.get(a.kind, 0.0)
    cranes = crane_boxes(c, R.OUT_DIR)
    li = layer_index(c)
    lts = line_type_indexes(c.tapir("GetAttributesByType", {"attributeType": "Line"}).get("attributes", []))
    fid = solid_fill_id(c.tapir("GetAttributesByType", {"attributeType": "Fill"}).get("attributes", []))
    try:                                             # 塗りのペンはペンセットから近い色（黒・淡い灰）。番号を決め打ちすると色が違った
        from pen_colors import pen_table

        from ashiba.pens import nearest_pen

        table = pen_table(c)[1]
        dark, light = nearest_pen(table, (0.0, 0.0, 0.0)), nearest_pen(table, (0.8, 0.8, 0.8))
    except Exception:
        dark, light = 1, 1
    items = []
    for k, (key, pts) in enumerate(segs, 1):
        if key in rec:
            _delete(c, rec.pop(key).get("guids", []))
        it = check(Item(f"{a.kind}{k}", a.kind, pts, dia, a.wires, a.volt, a.kv), cranes)
        d = drawing(it)
        P = lambda p: {"x": p[0] / 1000.0, "y": p[1] / 1000.0}
        made = []
        lines = []
        for pl, style in d["lines"]:
            e = {"coordinates": [P(p) for p in pl], "layerIndex": li}
            if style in DASH and lts.get(DASH[style]):
                e["lineTypeIndex"] = lts[DASH[style]]
            lines.append(e)
        texts = [{"coordinate": {**P(p), "z": 0.0}, "text": t, "height": h / 100.0, "angle": ang, "justification": "Center",
                  "layerIndex": li} for p, t, h, ang in d["texts"]]
        hatches = [{"coordinates": [P(p) for p in pl], "fillId": {"guid": fid}, "fillPenIndex": dark if dk > 0.5 else light,
                    "contourPenIndex": dark} for pl, dk in d["fills"]] if fid else []
        for cmd, k2, data in (("CreateHatches", "hatchesData", hatches), ("CreatePolylines", "polylinesData", lines),
                              ("CreateTexts", "textsData", texts)):
            if data:
                try:
                    r = c.tapir(cmd, {k2: data})
                    es = [e for e in r.get("elements", []) if "elementId" in e]
                    made += [e["elementId"]["guid"] for e in es]
                    if cmd == "CreateHatches" and es:
                        c.tapir("SetDetailsOfElements", {"elementsWithDetails": [
                            {"elementId": e["elementId"], "details": {"layerIndex": li}} for e in es]})
                except Exception as ex:
                    print(f"  注意: {cmd} が失敗（{ex}）")
        rec[key] = {"kind": a.kind, "guids": made, "pts": [list(p) for p in pts], "dia": dia, "volt": a.volt, "kv": a.kv,
                    "wires": a.wires}
        items.append(it)
        bad = [f"{x.status} {x.item}" for x in it.checks if x.status != "OK"]
        print(f"  {it.name}: " + (f"{it.length / 1000:.1f}m" if it.kind in ("給水管", "排水管", "地中埋設電線", "架空電線") else "置いた")
              + (f"・{'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "仮設電気給排水.md"
    # 帳票は控えの全部（前に置いた種類も）から書き直す
    every = [check(Item(f"{v['kind']}{k}", v["kind"], [tuple(p) for p in v["pts"]], v.get("dia", 0.0), v.get("wires", 3),
                        v.get("volt", "低圧"), v.get("kv", 0.0)), cranes)
             for k, v in enumerate(rec.values(), 1) if v.get("pts")]
    md.write_text(report(every), encoding="utf-8")
    print(f"仮設電気・給排水: {a.kind} {len(items)}か所（帳票: {md}）")
    return 0


def crane_boxes(c, out_dir: Path) -> list:
    """置いたクレーン・タワークレーンの部品の外接箱（作業半径の円を含む）[(名前, (xMin, yMin, xMax, yMax))]（mm）."""
    guids = []
    for name in ("クレーン.json", "タワークレーン.json"):
        try:
            d = json.loads((out_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for v in (d.values() if isinstance(d, dict) else d):
            guids += [v] if isinstance(v, str) else [x for x in (v if isinstance(v, list) else []) if isinstance(x, str)]
    out = []
    if not guids:
        return out
    try:
        r = c.tapir("Get3DBoundingBoxes", {"elements": [{"elementId": {"guid": g}} for g in guids]})
    except Exception:
        return out
    for k, bx in enumerate(r.get("boundingBoxes3D", []), 1):
        b = bx.get("boundingBox3D") or {}
        if "xMin" in b:
            out.append((f"クレーン{k}", tuple(b[q] * 1000.0 for q in ("xMin", "yMin", "xMax", "yMax"))))
    return out


def layer_index(c) -> int:
    attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
    hit = next((a for a in attrs if a.get("name") == LAYER), None)
    if hit is None:
        c.tapir("CreateLayers", {"layerDataArray": [{"name": LAYER}]})
        attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        hit = next(a for a in attrs if a.get("name") == LAYER)
    return int(hit["index"])


def _delete(c, guids) -> int:
    alive = set()
    for t in ("Hatch", "PolyLine", "Text"):
        try:
            alive |= {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": t}).get("elements", [])}
        except Exception:
            pass
    gone = [{"elementId": {"guid": g}} for g in guids if g in alive]
    if gone:
        c.delete_elements(gone)
    return len(gone)


if __name__ == "__main__":
    sys.exit(main())
