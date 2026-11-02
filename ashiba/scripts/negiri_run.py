"""根切り図（パレットの「根切り図」「根切り図を消す」）.

利用者の指定（2026-11-02）「根切り図も作れるようにして 掘削のオブジェクト躯体選択して 掘削底深さと法面を選べるようにして
ねぎりずを作成できるようにしてちょ 山留めまでの中途半ば部分は掘削するようにして」。

掘る躯体（床・梁・柱・壁。基礎がオブジェクトやモルフなら外形の箱で）を選んで押す。窓で掘削底・法面の勾配・余掘り・砕石と捨てコン
の厚さ・地山・色分けを選ぶと、掘削の面を Archicad のメッシュ（3D・断面に出る）に、根切り図を平面の塗り（床付けの高さごとの色分けと
凡例）・線（法肩・法尻）・文字（床付けの高さ・勾配・土量）にして、レイヤー「仮設_根切り」に置く。帳票（判定・土量・地業の数量）は
ashiba_out/根切り_<名前>.md。

土間: 名前・レイヤーに「土間」「犬走」が付く床（か、厚さが --doma-thin 以下の床）は土間として、余掘り 100（積算基準の土間・犬走り等
のゆとり幅 0.1m）・砕石 60・捨てコン 0 で掘る。山留めがあれば、山留め壁と基礎の間が積算基準の標準 1.0m より狭いと知らせる。

山留め: 名前に「山留」が付くレイヤーの壁、か一緒に選んだ閉じた線（ポリライン）を山留めの内側の面とする。その内側は山留めまで
掘る（躯体の掘削と山留めの間の中途半端な所も一般の根切り底まで）。山留めの外は掘らない。

  python3 scripts/negiri_run.py                                  # 窓で選ぶ
  python3 scripts/negiri_run.py --slope 0.5 --depth -2000        # 窓なし: 法面 1:0.5・掘削底 GL−2000（全部その深さ）
  python3 scripts/negiri_run.py --slope 0 --general -1500        # 垂直（山留め）・山留めの内の一般の根切り底 GL−1500
  python3 scripts/negiri_run.py --margin 600 --gravel 100 --lean 50 --soil 砂 --gl 0 --name 根切り1
  python3 scripts/negiri_run.py --doma-margin 100 --doma-gravel 100 --doma-lean 0 --doma-thin 200 --color 白黒
  python3 scripts/negiri_run.py --remove [--name 根切り1]        # 置いた根切り図とメッシュを消す（控えの GUID だけ）
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LAYER = "仮設_根切り"
RECORD = "根切り.json"
COLORS = ("カラー", "白黒", "なし")
SLOPE_LABELS = {"自動（積算基準: 1.5m 未満は垂直・5m 未満 1:0.3・以上 1:0.6）": None, "垂直（山留め）": 0.0, "1:0.3": 0.3, "1:0.5": 0.5, "1:0.8": 0.8, "1:1.0": 1.0, "1:1.5": 1.5}


def _rect(c, u, w, d):
    """芯 c・向き u（単位）・長さ w（u 向き）・幅 d の矩形の4点."""
    v = (-u[1], u[0])
    return [(c[0] + sx * u[0] * w / 2 + sy * v[0] * d / 2, c[1] + sx * u[1] * w / 2 + sy * v[1] * d / 2)
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def footprints(c, sel: list, dets: list, yamadome_walls: bool, doma_thin: float | None = None):
    """選んだ要素 → (躯体の外形 [Footprint], 山留めの面の線 [(a, b, 内向きの法線の候補)], 山留めの閉じた線 [多角形], 読めなかった数)."""
    from opening_run import slab_info

    from ashiba.beams import beam_from_details
    from ashiba.column_form import column_from_details
    from ashiba.negiri import DOMA_WORDS, Footprint
    from ashiba.wall_form import wall_from_details

    layers = {}
    try:
        layers = {int(a.get("index", -1)): str(a.get("name", ""))
                  for a in c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])}
    except Exception:
        pass
    zones, walls, polys, others, skipped = [], [], [], [], 0
    for e, d in zip(sel, dets):
        typ = d.get("type")
        det = d.get("details") or {}
        name = f"{typ} {d.get('id') or e['elementId']['guid'][:8]}"
        lay = layers.get(int(d.get("layerIndex", -1)), "")
        if typ == "Slab":
            s = slab_info(d)
            if s:
                doma = any(w in name or w in lay for w in DOMA_WORDS) or (doma_thin is not None and s["t"] <= doma_thin + 1e-6)
                zones.append(Footprint(name, s["outline"], s["top"] - s["t"], "土間" if doma else "基礎"))
                continue
        elif typ == "Beam":
            bm = beam_from_details(det)
            if bm:
                L = math.dist(bm.a, bm.b)
                u = ((bm.b[0] - bm.a[0]) / L, (bm.b[1] - bm.a[1]) / L)
                zones.append(Footprint(name, _rect(((bm.a[0] + bm.b[0]) / 2, (bm.a[1] + bm.b[1]) / 2), u, L, bm.width),
                                       bm.bottom_mm))
                continue
        elif typ == "Column":
            col = column_from_details(d)
            if col:
                a = math.radians(col["ang"])
                zones.append(Footprint(name, _rect(col["c"], (math.cos(a), math.sin(a)), col["width"], col["depth"]), col["z0"]))
                continue
        elif typ == "Wall":
            w = wall_from_details(d)
            if w:
                if yamadome_walls or "山留" in lay:
                    walls.append(w)
                else:
                    c0 = ((w["ca"][0] + w["cb"][0]) / 2 + w["n"][0] * (w["lo"] + w["hi"]) / 2,
                          (w["ca"][1] + w["cb"][1]) / 2 + w["n"][1] * (w["lo"] + w["hi"]) / 2)
                    zones.append(Footprint(name, _rect(c0, w["u"], w["length"], w["thick"]), w["z0"]))
                continue
        elif typ in ("PolyLine", "Line"):
            pts = [(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for p in det.get("coordinates") or []]
            if len(pts) >= 4 and math.dist(pts[0], pts[-1]) < 1.0:
                polys.append(pts[:-1])
                continue
        else:
            others.append((e, name))
            continue
        skipped += 1
    if others:
        try:
            boxes = c.tapir("Get3DBoundingBoxes", {"elements": [e for e, _n in others]}).get("boundingBoxes3D", [])
            for (_e, name), bx in zip(others, boxes):
                b = bx.get("boundingBox3D") or {}
                if "xMin" in b:
                    x0, x1, y0, y1 = (b[k] * 1000.0 for k in ("xMin", "xMax", "yMin", "yMax"))
                    zones.append(Footprint(name + "（外形の箱）", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], b["zMin"] * 1000.0))
                else:
                    skipped += 1
        except Exception:
            skipped += len(others)
    return zones, walls, polys, skipped


def yamadome_polygon(walls: list, center) -> list:
    """山留めの壁 → 内側の面の多角形（壁を中心の周りの角度で並べ、隣どうしの内側の面の線を交わらせる）."""
    if len(walls) < 3:
        return []
    faces = []
    for w in walls:
        mid = ((w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2)
        # 右の面（lo）と左の面（hi）のうち中心に近い方が内側
        off = w["hi"] - w["lo"]
        alt = (mid[0] + w["n"][0] * off, mid[1] + w["n"][1] * off)
        p = mid if math.dist(mid, center) <= math.dist(alt, center) else alt
        faces.append((math.atan2(p[1] - center[1], p[0] - center[0]), p, w["u"]))
    faces.sort()
    pts = []
    for k in range(len(faces)):
        _a1, p1, u1 = faces[k - 1]
        _a2, p2, u2 = faces[k]
        den = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(den) < 1e-6:
            continue
        t = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / den
        pts.append((p1[0] + u1[0] * t, p1[1] + u1[1] * t))
    return pts if len(pts) >= 3 else []


def layer_index(c) -> int:
    attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
    hit = next((a for a in attrs if a.get("name") == LAYER), None)
    if hit is None:
        c.tapir("CreateLayers", {"layerDataArray": [{"name": LAYER}]})
        attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        hit = next(a for a in attrs if a.get("name") == LAYER)
    return int(hit["index"])


def drawing(n, li: int, fill=None) -> tuple[list, list, list]:
    """根切り図の平面の塗り・線・文字（Tapir の hatchesData・polylinesData・textsData。m）。fill は (塗りの GUID, 色→ペン, 白黒)
    で、床付けの高さごとに塗り分けて凡例を付ける（浅い順に塗り、深い所を上に重ねる）."""
    from ashiba.negiri import _centroid, contour_lines, level_color, slope_angle

    P = lambda p: {"x": round(p[0] / 1000.0, 6), "y": round(p[1] / 1000.0, 6)}
    lines, texts = [], []
    for r in n.top_rings:
        lines.append({"coordinates": [P(p) for p in r + r[:1]], "layerIndex": li})
    for L, r, _kind in contour_lines(n):
        lines.append({"coordinates": [P(p) for p in r + r[:1]], "layerIndex": li})
    hatches = []
    if fill and n.levels:
        fid, pen_of, gray = fill
        for L in n.levels:
            fp = pen_of(level_color(n, L, gray))
            hatches += [{"coordinates": [P(p) for p in r], "fillId": {"guid": fid}, "fillPenIndex": fp, "contourPenIndex": fp}
                        for r in n.bottom_rings.get(L, [])]
    h = 0.35                                              # 文字の高さ（mm 相当。1/100 で 3.5mm）
    txt = lambda p, s: {"coordinate": {**P(p), "z": 0.0}, "text": s, "height": h * 10, "justification": "Center",
                        "layerIndex": li}
    from ashiba.negiri import inside

    for L, rs in n.bottom_rings.items():
        deeper = n.edge_rings.get(L, [])
        for r in rs:
            cp = _centroid(r)
            if any(inside(cp, q) for q in deeper):
                # 真ん中がさらに深く掘る所なら、輪の角から内へ 1.5m（その高さの平らな所に書く）
                v0 = r[0]
                L0 = math.dist(v0, cp) or 1.0
                cp = (v0[0] + (cp[0] - v0[0]) * 1500.0 / L0, v0[1] + (cp[1] - v0[1]) * 1500.0 / L0)
            texts.append(txt(cp, f"床付け GL{L - n.gl:+,.0f}"))
    if n.top_rings:
        r = n.top_rings[0]
        a, b = r[0], r[1]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        used = sorted({s for _h, s in n.slopes}) if n.slope is None else [n.slope]
        lab = "・".join("垂直" if s <= 0 else f"1:{s:g}（{slope_angle(s):.0f}°）" for s in used)
        lab = ("垂直（山留め）" if n.yamadome and used == [0.0] else "法面 " + lab) + ("（自動）" if n.slope is None else "")
        texts.append(txt((mid[0], mid[1] - 600.0), lab))
        ys = [p[1] for p in r]
        xs = [p[0] for p in r]
        texts.append(txt(((min(xs) + max(xs)) / 2, max(ys) + 900.0),
                         f"根切り図 {n.name}  掘削 {n.area:,.0f}m²・{n.volume:,.0f}m³（地山）"))
        if fill and n.levels:
            # 凡例: 掘削の外形の右上から下へ、色の四角と床付けの高さ
            fid, pen_of, gray = fill
            lx, ly = max(xs) + 1000.0, max(ys)
            for k, L in enumerate(n.levels):
                y = ly - k * 900.0
                fp = pen_of(level_color(n, L, gray))
                hatches.append({"coordinates": [P(q) for q in ((lx, y - 600.0), (lx + 1000.0, y - 600.0), (lx + 1000.0, y),
                                                               (lx, y))], "fillId": {"guid": fid}, "fillPenIndex": fp,
                                "contourPenIndex": fp})
                texts.append({**txt((lx + 1300.0, y - 300.0), f"床付け GL{L - n.gl:+,.0f}"), "justification": "Left"})
    return hatches, lines, texts


def fill_style(c, color: str):
    """色分けの (塗りつぶしの GUID, 色→ペンの番号, 白黒)。「なし」か塗りが無ければ None."""
    if color == "なし":
        return None
    from pen_colors import pen_table

    from ashiba.form_layout import solid_fill_id
    from ashiba.pens import nearest_pen

    try:
        fid = solid_fill_id(c.tapir("GetAttributesByType", {"attributeType": "Fill"}).get("attributes", []))
    except Exception:
        fid = None
    if not fid:
        return None
    table = pen_table(c)[1]
    return fid, (lambda rgb: nearest_pen(table, rgb)), color == "白黒"


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.negiri import (DOMA_GRAVEL_MM, DOMA_LEAN_MM, DOMA_MARGIN_MM, GRAVEL_MM, LEAN_MM, MARGIN_MM, SOILS, Negiri,
                               mesh_data, report, solve)
    from ashiba.tapir_adapter import ArchicadClient

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", default=None, help="名前（同じ名前は置き直す）")
    ap.add_argument("--slope", default=None, help="法面の勾配 1:n の n（0＝垂直・auto＝積算基準の法の係数）")
    ap.add_argument("--depth", type=float, default=None, help="掘削底を全部この深さに（GL からの mm。例 -2000）")
    ap.add_argument("--general", type=float, default=None, help="山留めの内の一般の根切り底（GL からの mm）")
    ap.add_argument("--margin", type=float, default=None, help=f"余掘り mm（既定 {MARGIN_MM:.0f}）")
    ap.add_argument("--gravel", type=float, default=None, help=f"砕石の厚さ mm（既定 {GRAVEL_MM:.0f}。標仕 4.6.3）")
    ap.add_argument("--lean", type=float, default=None, help=f"捨てコンの厚さ mm（既定 {LEAN_MM:.0f}。標仕 4.6.4）")
    ap.add_argument("--doma-margin", type=float, default=None, help=f"土間の余掘り mm（既定 {DOMA_MARGIN_MM:.0f}）")
    ap.add_argument("--doma-gravel", type=float, default=None, help=f"土間の砕石 mm（既定 {DOMA_GRAVEL_MM:.0f}）")
    ap.add_argument("--doma-lean", type=float, default=None, help=f"土間の捨てコン mm（既定 {DOMA_LEAN_MM:.0f}）")
    ap.add_argument("--doma-thin", type=float, default=None, help="厚さがこれ以下の床も土間とする mm（既定 名前・レイヤーだけ）")
    ap.add_argument("--color", default=None, choices=COLORS, help="床付けの高さの色分け（既定 カラー）")
    ap.add_argument("--soil", default=None, choices=list(SOILS), help="地山の種類（安衛則356条・357条の判定）")
    ap.add_argument("--gl", type=float, default=0.0, help="GL のプロジェクトの高さ mm（既定 0）")
    ap.add_argument("--yamadome-walls", action="store_true", help="選んだ壁を全部 山留めとする")
    ap.add_argument("--remove", action="store_true", help="置いた根切り図を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        keys = [a.name] if a.name else list(rec)
        n = _delete_alive_any(c, [g for k in keys for g in rec.get(k, [])])
        for k in keys:
            rec.pop(k, None)
        rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"根切り図: {n}個を消しました")
        return 0
    sel = c.get_selected_elements()
    dets = c.get_details(sel) if sel else []
    zones, walls, polys, skipped = footprints(c, sel, dets, a.yamadome_walls, a.doma_thin)
    if not zones:
        print("根切り図: 掘る躯体（基礎・地中梁・耐圧盤などの床・梁・柱・壁）を選んでから押してください。山留めは名前に「山留」が"
              "付くレイヤーの壁か、閉じた線を一緒に選ぶ")
        return 1
    opts = (a.slope, a.depth, a.general, a.margin, a.gravel, a.lean, a.doma_margin, a.doma_gravel, a.doma_lean, a.doma_thin,
            a.soil, a.color, a.name)
    if all(v is None for v in opts):
        ndoma = sum(1 for f in zones if f.kind == "土間")
        res = show_form({"title": "根切り図", "intro": f"躯体 {len(zones)}個" + (f"・山留め（壁 {len(walls)}枚・線 {len(polys)}本）" if walls or polys else "")
                         + (f"（うち土間 {ndoma}個: 名前・レイヤーに「土間」「犬走」）" if ndoma else "")
                         + "。掘削底を空にすると、躯体の下端から砕石と捨てコンの厚さを引いた深さ（躯体ごと）で掘ります。",
                         "fields": [{"key": "name", "label": "名前", "kind": "text", "value": "根切り1"},
                                    {"key": "depth", "label": "掘削底 GL から mm（空＝躯体ごと。例 -2000）", "kind": "number", "value": ""},
                                    {"key": "slope", "label": "法面の勾配", "kind": "choice", "options": list(SLOPE_LABELS),
                                     "value": "垂直（山留め）" if (walls or polys) else next(iter(SLOPE_LABELS))},
                                    {"key": "margin", "label": "余掘り mm（積算基準 500）", "kind": "number", "value": f"{MARGIN_MM:.0f}"},
                                    {"key": "gravel", "label": "砕石の厚さ mm（標仕 60）", "kind": "number", "value": f"{GRAVEL_MM:.0f}"},
                                    {"key": "lean", "label": "捨てコンの厚さ mm（標仕 50）", "kind": "number", "value": f"{LEAN_MM:.0f}"},
                                    {"key": "doma_margin", "label": "土間の余掘り mm（積算基準 100）", "kind": "number",
                                     "value": f"{DOMA_MARGIN_MM:.0f}"},
                                    {"key": "doma_gravel", "label": "土間の砕石 mm", "kind": "number", "value": f"{DOMA_GRAVEL_MM:.0f}"},
                                    {"key": "doma_lean", "label": "土間の捨てコン mm", "kind": "number", "value": f"{DOMA_LEAN_MM:.0f}"},
                                    {"key": "general", "label": "山留めの内の一般の根切り底 GL から mm（空＝床付けのいちばん浅い高さ）",
                                     "kind": "number", "value": ""},
                                    {"key": "soil", "label": "地山の種類", "kind": "choice", "options": list(SOILS), "value": "その他"},
                                    {"key": "color", "label": "床付けの高さの色分け", "kind": "choice", "options": list(COLORS),
                                     "value": COLORS[0]}],
                         "buttons": [{"id": "place", "label": "作る"}, {"id": "cancel", "label": "やめる"}]})
        if not res or res.get("button") != "place":
            print("根切り図: やめました（何も作っていません）")
            return 0
        v = res.get("values") or {}
        num = lambda k: float(str(v[k]).replace(",", "")) if str(v.get(k) or "").strip() else None
        a.name, a.depth, a.general = str(v.get("name") or "根切り1"), num("depth"), num("general")
        a.slope = SLOPE_LABELS.get(str(v.get("slope")))
        a.margin, a.gravel, a.lean = num("margin"), num("gravel"), num("lean")
        a.doma_margin, a.doma_gravel, a.doma_lean = num("doma_margin"), num("doma_gravel"), num("doma_lean")
        a.soil, a.color = str(v.get("soil") or "その他"), str(v.get("color") or COLORS[0])
    elif a.slope is not None:
        a.slope = None if str(a.slope).lower() == "auto" else float(a.slope)
    name = a.name or "根切り1"
    center = (sum(p[0] for f in zones for p in f.pts) / sum(len(f.pts) for f in zones),
              sum(p[1] for f in zones for p in f.pts) / sum(len(f.pts) for f in zones))
    yam = polys[0] if polys else yamadome_polygon(walls, center)
    if walls and not yam:
        print("根切り図: 山留めの壁から内側の面の多角形を作れませんでした（壁が3枚以上で囲む形に）。山留め無しで掘ります")
    dv = lambda x, d: d if x is None else x
    n = solve(Negiri(name, zones, gl=a.gl, margin=dv(a.margin, MARGIN_MM), gravel=dv(a.gravel, GRAVEL_MM), lean=dv(a.lean, LEAN_MM),
                     doma_margin=dv(a.doma_margin, DOMA_MARGIN_MM), doma_gravel=dv(a.doma_gravel, DOMA_GRAVEL_MM),
                     doma_lean=dv(a.doma_lean, DOMA_LEAN_MM), slope=a.slope,
                     depth=None if a.depth is None else a.gl + a.depth, soil=a.soil or "その他", yamadome=yam,
                     general=None if a.general is None else a.gl + a.general))
    if name in rec:
        _delete_alive_any(c, rec.pop(name))
    li = layer_index(c)
    made = []
    for m in mesh_data(n):
        try:
            r = c.tapir("CreateMeshes", {"meshesData": [m]})
            ms = [e for e in r.get("elements", []) if "elementId" in e]
            made += [e["elementId"]["guid"] for e in ms]
            # メッシュは作るときのレイヤーの指定が効かないので、作ってからレイヤーを移す
            c.tapir("SetDetailsOfElements", {"elementsWithDetails": [
                {"elementId": e["elementId"], "details": {"layerIndex": li}} for e in ms]})
        except Exception as ex:
            print(f"  注意: 掘削のメッシュを作れませんでした（{ex}）")
    fill = fill_style(c, a.color or COLORS[0])
    if (a.color or COLORS[0]) != "なし" and fill is None:
        print("  注意: 塗りつぶしの塗りが見つからないので、色分けは描きません")
    hatches, lines, texts = drawing(n, li, fill)
    for cmd, key, items in (("CreateHatches", "hatchesData", hatches), ("CreatePolylines", "polylinesData", lines),
                            ("CreateTexts", "textsData", texts)):
        if items:
            try:
                r = c.tapir(cmd, {key: items})
                es = [e for e in r.get("elements", []) if "elementId" in e]
                made += [e["elementId"]["guid"] for e in es]
                if cmd == "CreateHatches" and es:          # 塗りもレイヤーを後から移す（メッシュと同じ）
                    c.tapir("SetDetailsOfElements", {"elementsWithDetails": [
                        {"elementId": e["elementId"], "details": {"layerIndex": li}} for e in es]})
            except Exception as ex:
                print(f"  注意: {cmd} が失敗（{ex}）")
    rec[name] = made
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / f"根切り_{name}.md"
    md.write_text(report(n), encoding="utf-8")
    print(f"根切り図: {name} 躯体 {len(zones)}個・掘削 {n.area:,.0f}m²・{n.volume:,.0f}m³・床付け "
          + "、".join(f"GL{L - n.gl:+,.0f}" for L in n.levels) + (f"（読めなかった要素 {skipped}個）" if skipped else ""))
    for ck in n.checks:
        if ck.status != "OK":
            print(f"  {ck.status} {ck.item}: {ck.message}")
    print(f"  帳票: {md}")
    return 0 if all(ck.status != "NG" for ck in n.checks) else 2


def _delete_alive_any(c, guids) -> int:
    """控えの GUID のうち、まだある要素（メッシュ・線・文字）だけ消す."""
    if not guids:
        return 0
    alive = set()
    for t in ("Mesh", "Hatch", "PolyLine", "Text"):
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
