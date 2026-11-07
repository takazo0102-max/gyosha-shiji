"""移動式クレーンの揚重判定とブームの干渉チェック（パレットの「揚重判定」「ブームの干渉」「判定の色を消す」）.

利用者の指定（2026-11-01）: https://scp.global-bim.com/Content/download/manual/01_crane_20260213.pdf（smartCON Planner の
クレーン）を手本に「ホットスポットで姿勢・揚重判定・ブームの干渉チェック・半径の扇形・走行姿勢」。

  python3 scripts/crane_check.py --lift                 # 選んだクレーンと部材（柱・梁・壁・床・オブジェクト）の揚重判定
  python3 scripts/crane_check.py --lift --density 2.4   # 吊荷の重さ＝体積×密度（t/m³。省くと柱・梁 7.85・ほか 2.4）
  python3 scripts/crane_check.py --lift --weight 3.2    # 吊荷の重さを直接（t）
  python3 scripts/crane_check.py --lift --sling 6000    # 吊りしろ（部材の天端からフックまで mm。既定 6000）
  python3 scripts/crane_check.py --lift --bm            # 重さ＝ビルディングマテリアルの密度×体積
  python3 scripts/crane_check.py --lift --all           # 一括揚重判定（表示中の柱・梁・壁・床・屋根・オブジェクト）
  python3 scripts/crane_check.py --lift --draw          # 吊荷作図（判定した部材のコピーをフックの下へ。重すぎは赤）
  python3 scripts/crane_check.py --erase                # 吊荷削除（吊荷作図のコピーを消す）
  python3 scripts/crane_check.py --lift --ask           # 吊りしろ・重さの出し方・フック・治具・補正を窓で（パレットのボタン）
  python3 scripts/crane_check.py --clash                # 選んだクレーンのブームと躯体の干渉（警告 4000・接触 1000）
  python3 scripts/crane_check.py --clear                # 判定の色を消す

タワークレーン（ashiba_tower。利用者の指定 2026-11-01「タワークレーンも追加してちょ」の続き）も同じボタンで判定する: 据え付けた
ジブの呼びのまま、src/ashiba/tower.py の judge_lift（定格荷重は吊り荷＋玉掛け用具と比べる。ク則23条）と jib_axis（ジブの中心軸）。
クレーンを選んでいなければ、置いたクレーン（ashiba_out/クレーン.json、無ければ タワークレーン.json）の1台目。クレーンの姿勢・機種・張出幅・安全率は置いた部品の
パラメータ（平面・3D のホットスポットで動かしたあと）から読む。揚重判定は src/ashiba/crane.py の judge（揚重可能・重すぎ・遠すぎ・
高すぎ）で、部材を色分け（緑・橙・灰・黄）し、帳票は ashiba_out/揚重判定.md。干渉はブームの中心軸から部材の外形の箱までの距離で、
接触は赤・警告は黄、帳票は ashiba_out/ブームの干渉.md。色は Tapir の HighlightElements（--clear で消える）.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

COLORS = {"揚重可能": [40, 170, 60, 160], "重すぎ": [255, 140, 0, 200], "遠すぎ": [150, 150, 150, 160],
          "高すぎ": [170, 80, 200, 200], "判定不可": [240, 210, 0, 200], "接触": [220, 30, 30, 220], "警告": [240, 210, 0, 200],
          "吊荷の赤": [230, 30, 30, 220]}
SLING_MM = 6000.0                                # 吊りしろの既定（SCP の手引 p.6 の画面の値）
RECORD_COPIES = "吊荷のコピー.json"
FACTOR_KEYS = (("Column", "柱"), ("Beam", "梁"), ("Wall", "壁"), ("Slab", "床"), ("Roof", "屋根"), ("Object", "オブジェクト"))
TARGET_TYPES = ("Column", "Beam", "Wall", "Slab", "Object", "Roof")
STEEL_TYPES = ("Column", "Beam")


def _params(c, el) -> dict:
    it = c.tapir("GetGDLParametersOfElements", {"elements": [el]})["gdlParametersOfElements"][0]
    from ashiba.tapir_adapter import angle_values

    return angle_values(it.get("gdlParameters", it.get("parameters", [])))      # Angle は Tapir ではラジアン


def find_crane(c, sel, dets):
    """選んだ中のクレーン（ラフター ashiba_crane・タワー ashiba_tower・クローラ ashiba_machine の mcKind 2）。無ければ控えの1台目."""
    for e, d in zip(sel, dets):
        name = d.get("details", {}).get("libPart", {}).get("name", "") if d.get("type") == "Object" else ""
        if name.startswith(("ashiba_crane", "ashiba_tower")) or (name.startswith("ashiba_machine") and _is_crawler(c, e)):
            return e, d
    import run_from_archicad as R

    for rec_name in ("クレーン.json", "タワークレーン.json", "重機.json"):
        try:
            rec = json.loads((R.OUT_DIR / rec_name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for v in rec.values():
            g = v["guid"] if isinstance(v, dict) else (v if isinstance(v, list) else [v])[0]
            el = {"elementId": {"guid": g}}
            try:
                d = c.get_details([el])[0]
                if "details" not in d:                             # 消えた要素は止まらずに error を返す
                    continue
                if rec_name == "重機.json" and not _is_crawler(c, el):
                    continue
                return el, d
            except Exception:                                      # noqa: BLE001 消えていれば次へ
                continue
    return None, None


def _is_crawler(c, el) -> bool:
    return int(_params(c, el).get("mcKind", 0) or 0) == 2


def crawler_model(ps: dict):
    """置いたクローラの機種（mcModel。手入力は 50t の表で読む）."""
    from ashiba.machine import MACHINES, model_code

    code = int(ps.get("mcModel", 0) or 0)
    return next((m for k, m in MACHINES.items() if model_code(k) == code and m.kind == 2), MACHINES["cc50"])


def boxes(c, els) -> list:
    r = c.tapir("Get3DBoundingBoxes", {"elements": els}).get("boundingBoxes3D", [])
    out = []
    for b in r:
        bb = b.get("boundingBox3D") or {}
        if not bb:
            out.append(None)
            continue
        out.append(((bb["xMin"] * 1000, bb["yMin"] * 1000, bb["zMin"] * 1000), (bb["xMax"] * 1000, bb["yMax"] * 1000, bb["zMax"] * 1000)))
    return out


def volumes(c, els) -> list:
    """部材の正味の体積 m³（Archicad の組み込みのプロパティ General_NetVolume）。読めなければ None."""
    try:
        pid = c.post("API.GetPropertyIds", {"properties": [{"type": "BuiltIn", "nonLocalizedName": "General_NetVolume"}]})
        pid = pid["properties"][0]["propertyId"]
        r = c.post("API.GetPropertyValuesOfElements", {"elements": els, "properties": [{"propertyId": pid}]})
    except Exception:                                              # noqa: BLE001
        return [None] * len(els)
    out = []
    for v in r.get("propertyValuesForElements", []):
        try:
            out.append(float(v["propertyValues"][0]["propertyValue"]["value"]))
        except (KeyError, IndexError, TypeError, ValueError):
            out.append(None)
    return out


def _density_of(node) -> float | None:
    """GetBuildingMaterialPhysicalProperties の1件から密度を探す（kg/m³）."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() == "density" and isinstance(v, (int, float)):
                return float(v)
            d = _density_of(v)
            if d is not None:
                return d
    return None


def bm_weights(c, els) -> list:
    """ビルディングマテリアルの密度×体積 t（層ごとに足す）. 読めなければ None（判定不可）."""
    try:
        qs = c.tapir("GetQuantitiesOfElements", {"elements": els}).get("quantitiesOfElements", [])
    except Exception:                                              # noqa: BLE001
        return [None] * len(els)
    ids, dens = [], {}
    for q in qs:
        for x in q.get("composites") or []:
            g = x["buildingMaterialId"]["attributeId"]["guid"]
            if g not in ids:
                ids.append(g)
    if ids:
        r = c.tapir("GetBuildingMaterialPhysicalProperties",
                    {"attributeIds": [{"attributeId": {"guid": g}} for g in ids]}).get("properties", [])
        dens = {g: _density_of(p) for g, p in zip(ids, r)}
    out = []
    for q in qs:
        parts = [(x["buildingMaterialId"]["attributeId"]["guid"], float(x.get("volume") or 0.0)) for x in q.get("composites") or []]
        if not parts or any(not dens.get(g) for g, _v in parts):
            out.append(None)
        else:
            out.append(sum(dens[g] * v for g, v in parts) / 1000.0)
    return out + [None] * (len(els) - len(out))


def weigh(mode: str, vol, bm, kind: str, density, weight, factors: dict) -> float | None:
    """吊荷の重さ t. mode は bm（ビルディングマテリアル）・density（指定の密度×体積）・direct（直接）. 読めなければ None."""
    if mode == "direct":
        return weight
    f = factors.get(kind, 1.0)
    if mode == "bm":
        return None if bm is None else bm * f
    if not vol:
        return None                                  # 体積が読めないものを 0t で合格にしない
    return vol * (density if density is not None else (7.85 if kind in STEEL_TYPES else 2.4)) * f


def ask_lift(a, ps, hook_t: float, rig_t: float) -> bool:
    """吊りしろ・重さの出し方・フック・治具・補正を窓で. やめたら False."""
    from form_dialog import show_form

    modes = {"ビルディングマテリアル密度×体積": "bm", "指定密度×体積": "density", "重量直接指定": "direct"}
    now = next(k for k, v in modes.items() if v == a.mode)
    res = show_form({
        "title": "揚重判定",
        "intro": "判定は置いたクレーンの機種の性能表で、半径に届くブームから探します（ジブ付きのクローラは置いた組）。"
                 "定格総荷重 × 安全率 ≧ 吊荷＋フック＋治具 で見ます。",
        "fields": [{"key": "scope", "label": "判定する部材", "kind": "choice", "options": ["選んだ部材", "表示中の全部（一括）"],
                    "value": "表示中の全部（一括）" if a.all else "選んだ部材"},
                   {"key": "sling", "label": "吊りしろ mm（部材の天端からフック）", "kind": "number", "value": f"{a.sling:g}"},
                   {"key": "mode", "label": "吊荷重量", "kind": "choice", "options": list(modes), "value": now},
                   {"key": "density", "label": "指定密度 t/m³（空＝柱・梁 7.85、ほか 2.4）", "kind": "number",
                    "value": "" if a.density is None else f"{a.density:g}"},
                   {"key": "weight", "label": "重量直接指定 t", "kind": "number", "value": f"{a.weight or 0:g}"},
                   {"key": "hook", "label": "フック重量 t", "kind": "number", "value": f"{hook_t:g}"},
                   {"key": "rig", "label": "吊り治具等の重量 t", "kind": "number", "value": f"{rig_t:g}"},
                   *[{"key": f"f{k}", "label": f"重量補正 {n}（倍。直接指定では使わない）", "kind": "number", "value": "1"}
                     for k, n in FACTOR_KEYS],
                   {"key": "draw", "label": "吊荷作図（選んだ部材のコピーをフックの下へ。重すぎは赤。一括では作らない）", "kind": "check", "value": "1" if a.draw else "0"}],
        "buttons": [{"id": "go", "label": "判定する"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "go":
        return False
    v = res.get("values") or {}

    def num(key, default):
        try:
            return float(str(v.get(key)).replace(",", ""))
        except (TypeError, ValueError):
            return default

    a.all = str(v.get("scope", "")).startswith("表示中")
    a.sling = num("sling", a.sling)
    a.mode = modes.get(str(v.get("mode")), a.mode)
    a.density = num("density", None)
    a.weight = num("weight", a.weight)
    a.hook = num("hook", hook_t)
    a.rig = num("rig", rig_t)
    a.factors = {k: num(f"f{k}", 1.0) for k, _n in FACTOR_KEYS}
    a.draw = str(v.get("draw")) in ("1", "true", "True")
    return True


def ask_clash(a) -> bool:
    """警告・接触の距離と、仮設も見るかを窓で. やめたら False."""
    from form_dialog import show_form

    res = show_form({
        "title": "ブームの干渉",
        "intro": "ブームとジブの中心軸から部材の外形の箱までの距離で見ます（太い部材は色の付く範囲が指定より大きく見えます）。",
        "fields": [{"key": "warn", "label": "警告距離 mm（黄）", "kind": "number", "value": f"{a.warn:g}"},
                   {"key": "contact", "label": "接触距離 mm（赤）", "kind": "number", "value": f"{a.contact:g}"},
                   {"key": "temp", "label": "足場などの仮設も見る", "kind": "check", "value": "1" if a.temp else "0"}],
        "buttons": [{"id": "go", "label": "調べる"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "go":
        return False
    v = res.get("values") or {}
    for key in ("warn", "contact"):
        try:
            setattr(a, key, float(str(v.get(key)).replace(",", "")))
        except (TypeError, ValueError):
            pass
    a.temp = str(v.get("temp")) in ("1", "true", "True")
    return True


def visible_targets(c) -> list:
    """一括揚重判定の対象: 表示中の柱・梁・壁・床・屋根・オブジェクト（ashiba の仮設は除く）."""
    out = []
    for ty in TARGET_TYPES:
        es = c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])
        if es:
            es = c.tapir("FilterElements", {"elements": es, "filters": ["IsVisibleByLayer", "IsVisibleIn3D"]}).get("elements", [])
        if es:
            out += list(zip(es, c.get_details(es)))
    return out


def judge_one(m, cm, tw, ps: dict, radius: float, need_z: float, w, hook_t: float, rig_t: float, ratio: float, name: str) -> tuple:
    """1 つの吊荷の判定 → (判定, 結果（boom・rated_t）, 吊れる作業半径 mm か None). tw はタワー、cm はクローラ、どちらも None ならラフター m."""
    from ashiba.crane import RIGGING_T, effective_spread, judge, reach_for
    from ashiba.machine import crawler_judge, crawler_reach

    far = None
    if w is None:
        return "判定不可", type("X", (), {"boom": 0, "rated_t": 0.0})(), far
    if tw is not None:
        from ashiba.tower import judge_lift

        res, cap = judge_lift(tw, float(ps.get("maxR", tw.jibs[0])), float(ps.get("msH", tw.free_h)), radius / 1000.0, need_z / 1000.0, w)
        return res, type("X", (), {"boom": float(ps.get("maxR", 0)), "rated_t": cap or 0.0})(), far
    if cm is not None:
        total = w + hook_t + rig_t
        r = crawler_judge(cm, ps, radius / 1000.0, need_z / 1000.0, total, ratio)
        res = r["判定"]
        if res in ("重すぎ", "遠すぎ"):
            far = crawler_reach(cm, ps, need_z / 1000.0, total, ratio)
            far = far * 1000.0 if far else None
        return res, type("X", (), {"boom": r["ブーム"], "rated_t": r["定格"]})(), far
    adj = w + hook_t + rig_t - m.hook_t - RIGGING_T          # judge は機種のフックと治具を足す
    res, x = judge(m, effective_spread(ps) or max(m.spreads), radius, need_z, adj, ratio, name)
    if res in ("重すぎ", "遠すぎ"):
        far = reach_for(m, effective_spread(ps) or max(m.spreads), need_z, adj, ratio)
    return res, x, far


def lifter(c, crane, cd, sling: float | None = None):
    """置いたクレーンの判定の関数 f(x, y, 上端 z, 重さ t, 名前) → {res, rated, radius} と、名前・位置 {name, x, y}（mm）."""
    from ashiba.crane import MODELS, RIGGING_T
    from ashiba.machine import HOOK_T

    ps = _params(c, crane)
    part = cd.get("details", {}).get("libPart", {}).get("name", "")
    kind = "tower" if part.startswith("ashiba_tower") else "crawler" if part.startswith("ashiba_machine") else "rough"
    m = next((x for x in MODELS.values() if x.kind == int(ps.get("crType", 1))), MODELS["25t"])
    cm = crawler_model(ps) if kind == "crawler" else None
    tw = None
    if kind == "tower":
        from ashiba.tower import tower_from_params

        tw = tower_from_params(ps)
    o = cd["details"]["origin"]
    ox, oy, oz = o["x"] * 1000.0, o["y"] * 1000.0, o.get("z", 0.0) * 1000.0
    hook_t = float(ps.get("hookT", m.hook_t if kind == "rough" else HOOK_T if kind == "crawler" else 0.0))
    rig_t = float(ps.get("rigT", RIGGING_T))
    ratio = float(ps.get("sfRate", 0.9))
    sl = sling if sling is not None else float(ps.get("slgH", SLING_MM / 1000.0)) * 1000.0
    name = tw.name if tw is not None else cm.name if cm is not None else m.name

    def f(x: float, y: float, top: float, w, label: str = "") -> dict:
        radius = math.hypot(x - ox, y - oy)
        res, r, _far = judge_one(m, cm, tw, ps, radius, top - oz + sl, w, hook_t, rig_t, ratio, label)
        return {"res": res, "rated": float(getattr(r, "rated_t", 0.0) or 0.0), "radius": radius}

    return f, {"name": name, "x": ox, "y": oy}


def lift_targets(pool: list, crane_guid: str, copy_guids) -> list:
    """判定する部材: クレーン・ashiba の仮設・通り芯の記号・吊荷作図のコピーは除く（コピーをまた判定してコピーしない）."""
    out = []
    for e, d in pool:
        name = d.get("details", {}).get("libPart", {}).get("name", "")
        g = e["elementId"]["guid"]
        if d.get("type") in TARGET_TYPES and g != crane_guid and g not in copy_guids and (name.startswith("ashiba_steel") or not name.startswith("ashiba_")) and "通り芯" not in name:
            out.append((e, d))
    return out


def reach_notes(rows: list, limit: int = 5) -> list:
    """重すぎ・遠すぎの部材の案内（一括で 92 行出たので limit 行まで。残りは帳票に）.

    重すぎを先に出し、同じ名前・重さ・半径・案内の行は 1 行にまとめて数を添える（2026-11-07 ループの試験で、一括の
    5 行が同じ「C1 … 遠すぎ」で埋まり、重すぎ 2 個が見えなかった）."""
    bad = sorted((r for r in rows if r[6] in ("重すぎ", "遠すぎ")), key=lambda r: r[6] != "重すぎ")
    groups: dict = {}
    for nm, _ty, _v, w, rad, _nz, res, _x, far in bad:
        line = (f"揚重判定: {nm} {w:.2f}t・作業半径 {rad / 1000:.1f}m は{res}。"
                + (f"作業半径 {far / 1000:.1f}m 以内に寄せれば吊れます" if far else "この機種ではどの半径でも吊れません（大きい機種に）"))
        groups[line] = groups.get(line, 0) + 1
    items = list(groups.items())
    out = [line + (f"（同じもの {n}個）" if n > 1 else "") for line, n in items[:limit]]
    rest = sum(n for _line, n in items[limit:])
    if rest:
        out.append(f"揚重判定: ほか {rest}個は帳票に")
    return out


def read_copies(path) -> list:
    """吊荷作図の控え（GUID の一覧）."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def hook_point(ps: dict, origin: tuple, car: float, kind: str) -> tuple:
    """今の姿勢のフックの位置（図面の座標 mm。高さはフックの下端）."""
    a = math.radians(car + float(ps.get("slew", 0.0)))
    if kind == "crawler":
        from ashiba.machine import hook_radius

        r = hook_radius(ps)
        ang = math.radians(float(ps["lbA"]))
        tip = float(ps["pvH"]) + float(ps["lbL"]) * math.sin(ang)
        jib = float(ps.get("jbL", 0) or 0)
        if jib > 0:
            tip += jib * math.sin(ang - math.radians(float(ps.get("jbO", 10.0))))
        z = tip - float(ps.get("hkD", 6.0))
    elif kind == "tower":
        r = float(ps.get("jbL", 30.0)) * math.cos(math.radians(float(ps.get("jbA", 45.0)))) + float(ps.get("pvX", 1.0))
        z = float(ps.get("msH", 40.0))
    else:
        r = float(ps.get("hkR", 10.0))
        bl, ba = float(ps.get("boomL", 10.0)), math.radians(float(ps.get("boomA", 45.0)))
        z = float(ps.get("hkZ", 0.0) or 0.0) or (float(ps.get("pivH", 2.3)) + bl * math.sin(ba) - float(ps.get("tipHk", 3.0)))
    return (origin[0] + r * 1000.0 * math.cos(a), origin[1] + r * 1000.0 * math.sin(a), origin[2] + z * 1000.0)


def copy_loads(c, rows, hook, sling: float, rec_path) -> list:
    """吊荷作図: 揚重可能・重すぎの部材をフックの下へ複製し、GUID を控える. 重すぎは赤に."""
    done = []
    for e, ty, bb, res in rows:
        if res not in ("揚重可能", "重すぎ") or bb is None:
            continue
        before = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])}
        cx, cy = (bb[0][0] + bb[1][0]) / 2.0, (bb[0][1] + bb[1][1]) / 2.0
        vec = {"x": (hook[0] - cx) / 1000.0, "y": (hook[1] - cy) / 1000.0, "z": (hook[2] - sling - bb[1][2]) / 1000.0}
        c.tapir("MoveElements", {"elementsWithMoveVectors": [{**e, "moveVector": vec, "copy": True}]})
        after = c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])
        done += [(x, res) for x in after if x["elementId"]["guid"] not in before]
    try:
        old = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = []
    rec_path.write_text(json.dumps(old + [x["elementId"]["guid"] for x, _r in done], ensure_ascii=False, indent=1), encoding="utf-8")
    return done


def erase_copies(c, guids) -> int:
    """吊荷作図のコピーを消す（控えの GUID だけ。コピーは柱・梁など部材の種類のまま）."""
    alive = {x["elementId"]["guid"] for ty in TARGET_TYPES for x in c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])}
    gone = [{"elementId": {"guid": g}} for g in guids if g in alive]
    if gone:
        c.delete_elements(gone)
    return len(gone)


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.crane import (CLASH_CONTACT_MM, CLASH_WARN_MM, MODELS, RIGGING_T, crane_axes, effective_spread, judge, reach_for,
                              seg_box_distance)
    from ashiba.machine import HOOK_T, crawler_axes, crawler_judge, crawler_reach
    from ashiba.tapir_adapter import ArchicadClient

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lift", action="store_true", help="揚重判定")
    ap.add_argument("--clash", action="store_true", help="ブームの干渉チェック")
    ap.add_argument("--clear", action="store_true", help="判定の色を消す")
    ap.add_argument("--erase", action="store_true", help="吊荷削除（吊荷作図のコピーを消す）")
    ap.add_argument("--ask", action="store_true", help="条件を窓で")
    ap.add_argument("--all", action="store_true", help="一括揚重判定（表示中の部材）")
    ap.add_argument("--draw", action="store_true", help="吊荷作図")
    ap.add_argument("--bm", action="store_true", help="重さ＝ビルディングマテリアルの密度×体積")
    ap.add_argument("--density", type=float, default=None, help="密度 t/m³（省くと柱・梁 7.85、ほか 2.4）")
    ap.add_argument("--weight", type=float, default=None, help="吊荷の重さ t（直接）")
    ap.add_argument("--hook", type=float, default=None, help="フック重量 t（省くと部品の値か機種の値）")
    ap.add_argument("--rig", type=float, default=None, help="吊り治具等の重量 t（省くと部品の値）")
    ap.add_argument("--sling", type=float, default=SLING_MM, help="吊りしろ mm（部材の天端からフック）")
    ap.add_argument("--warn", type=float, default=CLASH_WARN_MM, help="干渉の警告の距離 mm")
    ap.add_argument("--contact", type=float, default=CLASH_CONTACT_MM, help="干渉の接触の距離 mm")
    ap.add_argument("--temp", action="store_true", help="干渉で足場などの仮設も見る")
    a = ap.parse_args(argv)
    sling_given = a.sling != SLING_MM
    a.mode = "direct" if a.weight is not None else "bm" if a.bm else "density"
    a.factors = {}
    c = ArchicadClient()
    copies = R.OUT_DIR / RECORD_COPIES
    if a.erase:
        n = erase_copies(c, read_copies(copies))
        copies.write_text("[]", encoding="utf-8")
        print(f"吊荷削除: {n}個を消しました")
        return 0
    if a.clear or not (a.lift or a.clash):
        c.tapir("HighlightElements", {"elements": [], "highlightedColors": []})
        print("判定の色を消しました")
        return 0
    sel = c.get_selected_elements()
    dets = c.get_details(sel) if sel else []
    crane, cd = find_crane(c, sel, dets)
    if crane is None:
        print("クレーンを選んでから押してください（置いたクレーンが無ければ先に「クレーン」で置く）")
        return 1
    ps = _params(c, crane)
    if not sling_given and "slgH" in ps:
        a.sling = float(ps["slgH"]) * 1000.0                  # 部品の吊りしろ（吊り点の印と同じ所で判定する）
    part_name = cd.get("details", {}).get("libPart", {}).get("name", "")
    kind = "tower" if part_name.startswith("ashiba_tower") else "crawler" if part_name.startswith("ashiba_machine") else "rough"
    is_tower = kind == "tower"
    m = next((x for x in MODELS.values() if x.kind == int(ps.get("crType", 1))), MODELS["25t"])
    cm = crawler_model(ps) if kind == "crawler" else None
    tw = None
    if is_tower:
        from ashiba.tower import jib_axis, judge_lift, tower_from_params

        tw = tower_from_params(ps)
    o = cd["details"]["origin"]
    origin = (o["x"] * 1000.0, o["y"] * 1000.0, o.get("z", 0.0) * 1000.0)
    car = math.degrees(cd["details"].get("angle", 0.0))
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    cg = crane["elementId"]["guid"]
    if a.lift:
        hook_t = float(ps.get("hookT", m.hook_t if kind == "rough" else HOOK_T if kind == "crawler" else 0.0))
        rig_t = float(ps.get("rigT", RIGGING_T))
        if a.ask and not ask_lift(a, ps, hook_t, rig_t):
            print("揚重判定: やめました")
            return 0
        hook_t = a.hook if getattr(a, "hook", None) is not None else hook_t
        rig_t = a.rig if getattr(a, "rig", None) is not None else rig_t
        pool = visible_targets(c) if a.all else list(zip(sel, dets))
        targets = lift_targets(pool, cg, set(read_copies(copies)))
        # 一括では吊荷作図をしない（表示中の全部をフックの下へ複製して部材が増えた。利用者の報告 2026-11-07）
        skip_draw = a.all and a.draw
        a.draw = a.draw and not a.all
        if not targets:
            print("揚重判定: クレーンと一緒に、吊る部材（柱・梁・壁・床・屋根・オブジェクト）を選んでください")
            return 1
        els = [e for e, _d in targets]
        bbs, vols = boxes(c, els), volumes(c, els)
        bms = bm_weights(c, els) if a.mode == "bm" else [None] * len(els)
        rows, hl, cols, drawn = [], [], [], []
        ratio = float(ps.get("sfRate", 0.9))
        for (e, d), bb, vol, bm in zip(targets, bbs, vols, bms):
            if bb is None:
                continue
            cx, cy = (bb[0][0] + bb[1][0]) / 2.0, (bb[0][1] + bb[1][1]) / 2.0
            radius = math.hypot(cx - origin[0], cy - origin[1])
            need_z = bb[1][2] - origin[2] + a.sling
            w = weigh(a.mode, vol, bm, d.get("type"), a.density, a.weight, a.factors)
            if a.mode != "direct" and d.get("details", {}).get("libPart", {}).get("name", "").startswith("ashiba_steel"):
                w = float(_params(c, e).get("pcW", 0.0)) or None             # 鉄骨のピースは部品の重量（断面の無いものは判定不可）
            name = d.get("id") or e["elementId"]["guid"][:8]
            far = None                                   # 吊れる作業半径（重すぎ・遠すぎのとき、どこまで寄せればよいか）
            res, x, far = judge_one(m, cm, tw, ps, radius, need_z, w, hook_t, rig_t, ratio, name)
            rows.append((name, d.get("type"), vol, w, radius, need_z, res, x, far))
            hl.append(e)
            cols.append(COLORS[res])
            drawn.append((e, d.get("type"), bb, res))
        made = copy_loads(c, drawn, hook_point(ps, origin, car, kind), a.sling, copies) if a.draw else []
        hl += [e for e, _r in made]
        cols += [COLORS["吊荷の赤" if r == "重すぎ" else r] for _e, r in made]
        c.tapir("HighlightElements", {"elements": hl, "highlightedColors": cols, "wireframe3D": False})
        label = (f"タワークレーン: {tw.name}（{tw.model}・ジブ {ps.get('maxR')}m・マスト {ps.get('msH')}m。定格荷重と吊り荷＋玉掛け用具 0.05t を"
                 "比べる（ク則23条）。フックの限りはジブの先の 2m 下【目安】）" if tw is not None else
                 f"クレーン: {cm.name}（{cm.model}・安全率 {ratio:g}。フックの上限はブームの先の 3m 下【目安】）" if cm is not None else
                 f"クレーン: {m.name}（定格を読む張出 {effective_spread(ps):g}m・安全率 {ratio:g}）")
        how = {"direct": f"重さ {a.weight}t（直接）", "bm": "重さ＝ビルディングマテリアルの密度×体積",
               "density": f"重さ＝体積×密度（{a.density}t/m³）" if a.density is not None else "重さ＝体積×密度（柱・梁 7.85・ほか 2.4t/m³）"}[a.mode]
        md = ["# 揚重判定", "", f"{label}。吊りしろ {a.sling:.0f}・{how}・フック {hook_t:g}t・吊り治具 {rig_t:g}t",
              "", "| 部材 | 種類 | 体積 | 重さ | 作業半径 | 要るフックの高さ | 判定 | ブーム・定格 | 吊れる作業半径 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for nm, ty, vol, w, rad, nz, res, x, far in rows:
            md.append(f"| {nm} | {ty} | {vol or 0:.2f}m³ | " + ("-" if w is None else f"{w:.2f}t") + f" | {rad / 1000:.1f}m | {nz / 1000:.1f}m | {res} | "
                      + (f"{x.boom}m・{x.rated_t:.2f}t" if x.boom else "-") + " | "
                      + (f"{far / 1000:.1f}m 以内" if far else "この機種では無理" if res in ("重すぎ", "遠すぎ") and tw is None else "-")
                      + " |")
        md += ["", "色: 揚重可能＝緑・重すぎ＝橙・遠すぎ＝灰・高すぎ＝紫・判定不可（体積や密度が読めない）＝黄（「判定の色を消す」で消える）。"
               "定格総荷重×安全率と 吊荷＋フック＋治具 を比べる（クレーン等安全規則 69条）"]
        (R.OUT_DIR / "揚重判定.md").write_text("\n".join(md), encoding="utf-8")
        cnt = {k: sum(1 for r in rows if r[6] == k) for k in ("揚重可能", "重すぎ", "遠すぎ", "高すぎ", "判定不可")}
        print("揚重判定: " + "・".join(f"{k} {v}" for k, v in cnt.items()) + f"（{R.OUT_DIR / '揚重判定.md'}）"
              + (f"。吊荷のコピー {len(made)}個" if a.draw else "")
              + ("。一括では吊荷作図をしません（部材を選んで判定すると作ります）" if skip_draw else ""))
        if len(rows) <= 5:
            for nm, _ty, _v, w, rad, _nz, res, x, far in rows:
                if res == "揚重可能":
                    print(f"揚重判定: {nm} {w:.2f}t・作業半径 {rad / 1000:.1f}m は揚重可能（ブーム {x.boom}m・定格 {x.rated_t:.2f}t × {ratio:g}）")
        if tw is None:
            for line in reach_notes(rows):
                print(line)
    if a.clash:
        if a.ask and not ask_clash(a):
            print("ブームの干渉: やめました")
            return 0
        segs = [jib_axis(ps, origin, car)] if tw is not None else crawler_axes(ps, origin, car) if cm is not None else crane_axes(ps, origin, car)
        els = []
        for ty in ("Wall", "Column", "Beam", "Slab", "Roof", "Object"):
            for e in c.tapir("GetElementsByType", {"elementType": ty}).get("elements", []):
                if e["elementId"]["guid"] != cg:
                    els.append((e, ty))
        objs = [e for e, ty in els if ty == "Object"]
        own = set()
        if objs and not a.temp:
            for e, d in zip(objs, c.get_details(objs)):
                if d.get("details", {}).get("libPart", {}).get("name", "").startswith("ashiba_"):
                    own.add(e["elementId"]["guid"])
        els = [(e, ty) for e, ty in els if e["elementId"]["guid"] not in own]
        bbs = boxes(c, [e for e, _t in els])
        hits = []
        for (e, ty), bb in zip(els, bbs):
            if bb is None:
                continue
            dist = min(seg_box_distance(p0, p1, bb[0], bb[1]) for p0, p1 in segs)
            if dist <= a.warn:
                hits.append((e, ty, dist, "接触" if dist <= a.contact else "警告"))
        c.tapir("HighlightElements", {"elements": [h[0] for h in hits], "highlightedColors": [COLORS[h[3]] for h in hits],
                                      "wireframe3D": False})
        p0, p1 = segs[0][0], segs[-1][1]
        md = ["# ブームの干渉", "", f"クレーン: {tw.model if tw is not None else cm.name if cm is not None else m.name}。ブーム（ジブ）の中心軸（根元 {tuple(round(v) for v in p0)}・先 "
              f"{tuple(round(v) for v in p1)}）から部材の外形の箱まで。接触 {a.contact:.0f} 以内＝赤・警告 {a.warn:.0f} 以内＝黄", "",
              "| 部材 | 種類 | 距離 | 判定 |", "|---|---|---|---|"]
        md += [f"| {e['elementId']['guid'][:8]} | {ty} | {dist:.0f} | {res} |" for e, ty, dist, res in sorted(hits, key=lambda h: h[2])]
        (R.OUT_DIR / "ブームの干渉.md").write_text("\n".join(md), encoding="utf-8")
        print(f"ブームの干渉: 接触 {sum(1 for h in hits if h[3] == '接触')}・警告 {sum(1 for h in hits if h[3] == '警告')}"
              f"（{R.OUT_DIR / 'ブームの干渉.md'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
