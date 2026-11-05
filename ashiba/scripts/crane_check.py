"""移動式クレーンの揚重判定とブームの干渉チェック（パレットの「揚重判定」「ブームの干渉」「判定の色を消す」）.

利用者の指定（2026-11-01）: https://scp.global-bim.com/Content/download/manual/01_crane_20260213.pdf（smartCON Planner の
クレーン）を手本に「ホットスポットで姿勢・揚重判定・ブームの干渉チェック・半径の扇形・走行姿勢」。

  python3 scripts/crane_check.py --lift                 # 選んだクレーンと部材（柱・梁・壁・床・オブジェクト）の揚重判定
  python3 scripts/crane_check.py --lift --density 2.4   # 吊荷の重さ＝体積×密度（t/m³。省くと柱・梁 7.85・ほか 2.4）
  python3 scripts/crane_check.py --lift --weight 3.2    # 吊荷の重さを直接（t）
  python3 scripts/crane_check.py --lift --sling 2000    # 吊りしろ（部材の天端からフックまで mm。既定 2000）
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
          "高すぎ": [240, 210, 0, 200], "接触": [220, 30, 30, 220], "警告": [240, 210, 0, 200]}
TARGET_TYPES = ("Column", "Beam", "Wall", "Slab", "Object", "Roof")
STEEL_TYPES = ("Column", "Beam")


def _params(c, el) -> dict:
    it = c.tapir("GetGDLParametersOfElements", {"elements": [el]})["gdlParametersOfElements"][0]
    from ashiba.tapir_adapter import angle_values

    return angle_values(it.get("gdlParameters", it.get("parameters", [])))      # Angle は Tapir ではラジアン


def find_crane(c, sel, dets):
    """選んだ中のクレーン（ashiba_crane）。無ければ控えの1台目."""
    for e, d in zip(sel, dets):
        if d.get("type") == "Object" and (d.get("details", {}).get("libPart", {}).get("name", "")).startswith(
                ("ashiba_crane", "ashiba_tower")):
            return e, d
    import run_from_archicad as R

    for rec_name in ("クレーン.json", "タワークレーン.json"):
        try:
            rec = json.loads((R.OUT_DIR / rec_name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for v in rec.values():
            g = v["guid"] if isinstance(v, dict) else (v if isinstance(v, list) else [v])[0]
            el = {"elementId": {"guid": g}}
            try:
                return el, c.get_details([el])[0]
            except Exception:                                      # noqa: BLE001 消えていれば次へ
                continue
    return None, None


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


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.crane import (CLASH_CONTACT_MM, CLASH_WARN_MM, MODELS, boom_axis, effective_spread, judge, reach_for,
                              seg_box_distance)
    from ashiba.tapir_adapter import ArchicadClient

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lift", action="store_true", help="揚重判定")
    ap.add_argument("--clash", action="store_true", help="ブームの干渉チェック")
    ap.add_argument("--clear", action="store_true", help="判定の色を消す")
    ap.add_argument("--density", type=float, default=None, help="密度 t/m³（省くと柱・梁 7.85、ほか 2.4）")
    ap.add_argument("--weight", type=float, default=None, help="吊荷の重さ t（直接）")
    ap.add_argument("--sling", type=float, default=2000.0, help="吊りしろ mm（部材の天端からフック）")
    ap.add_argument("--warn", type=float, default=CLASH_WARN_MM, help="干渉の警告の距離 mm")
    ap.add_argument("--contact", type=float, default=CLASH_CONTACT_MM, help="干渉の接触の距離 mm")
    a = ap.parse_args(argv)
    c = ArchicadClient()
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
    is_tower = cd.get("details", {}).get("libPart", {}).get("name", "").startswith("ashiba_tower")
    m = next((x for x in MODELS.values() if x.kind == int(ps.get("crType", 1))), MODELS["25t"])
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
        targets = [(e, d) for e, d in zip(sel, dets) if d.get("type") in TARGET_TYPES and e["elementId"]["guid"] != cg
                   and not d.get("details", {}).get("libPart", {}).get("name", "").startswith("ashiba_")]
        if not targets:
            print("揚重判定: クレーンと一緒に、吊る部材（柱・梁・壁・床・オブジェクト）を選んでください")
            return 1
        els = [e for e, _d in targets]
        bbs, vols = boxes(c, els), volumes(c, els)
        rows, hl, cols = [], [], []
        ratio = float(ps.get("sfRate", 0.9))
        for (e, d), bb, vol in zip(targets, bbs, vols):
            if bb is None:
                continue
            cx, cy = (bb[0][0] + bb[1][0]) / 2.0, (bb[0][1] + bb[1][1]) / 2.0
            radius = math.hypot(cx - origin[0], cy - origin[1])
            need_z = bb[1][2] - origin[2] + a.sling
            dens = a.density if a.density is not None else (7.85 if d.get("type") in STEEL_TYPES else 2.4)
            w = a.weight if a.weight is not None else (vol or 0.0) * dens
            if tw is not None:
                res, cap = judge_lift(tw, float(ps.get("maxR", tw.jibs[0])), float(ps.get("msH", tw.free_h)), radius / 1000.0,
                                      need_z / 1000.0, w)
                x = type("X", (), {"boom": float(ps.get("maxR", 0)), "rated_t": cap or 0.0})()
            else:
                res, x = judge(m, effective_spread(ps) or max(m.spreads), radius, need_z, w, ratio, d.get("id") or d.get("type"))
            far = None                                   # 吊れる作業半径（重すぎ・遠すぎのとき、どこまで寄せればよいか）
            if tw is None and res in ("重すぎ", "遠すぎ"):
                far = reach_for(m, effective_spread(ps) or max(m.spreads), need_z, w, ratio)
            rows.append((d.get("id") or e["elementId"]["guid"][:8], d.get("type"), vol, w, radius, need_z, res, x, far))
            hl.append(e)
            cols.append(COLORS[res])
        c.tapir("HighlightElements", {"elements": hl, "highlightedColors": cols, "wireframe3D": False})
        head = (f"タワークレーン: {tw.name}（{tw.model}・ジブ {ps.get('maxR')}m・マスト {ps.get('msH')}m。定格荷重と吊り荷＋玉掛け用具 0.05t を"
                "比べる（ク則23条）。フックの限りはジブの先の 2m 下【目安】）" if tw is not None else
                f"クレーン: {m.name}（定格を読む張出 {effective_spread(ps):g}m・安全率 {ratio:g}）")
        md = ["# 揚重判定", "", f"{head}。吊りしろ {a.sling:.0f}・"
              + (f"重さ {a.weight}t（直接）" if a.weight is not None else
                 f"重さ＝体積×密度（{a.density}t/m³）" if a.density is not None else "重さ＝体積×密度（柱・梁 7.85・ほか 2.4t/m³）"),
              "", "| 部材 | 種類 | 体積 | 重さ | 作業半径 | 要るフックの高さ | 判定 | ブーム・定格 | 吊れる作業半径 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for nm, ty, vol, w, rad, nz, res, x, far in rows:
            md.append(f"| {nm} | {ty} | {vol or 0:.2f}m³ | {w:.2f}t | {rad / 1000:.1f}m | {nz / 1000:.1f}m | {res} | "
                      + (f"{x.boom}m・{x.rated_t:.2f}t" if x.boom else "-") + " | "
                      + (f"{far / 1000:.1f}m 以内" if far else "この機種では無理" if res in ("重すぎ", "遠すぎ") and tw is None else "-")
                      + " |")
        md += ["", "色: 揚重可能＝緑・重すぎ＝橙・遠すぎ＝灰・高すぎ＝黄（「判定の色を消す」で消える）。重さはフック・玉掛け用具を足して"
               "定格総荷重×安全率と比べる（クレーン等安全規則 69条）"]
        (R.OUT_DIR / "揚重判定.md").write_text("\n".join(md), encoding="utf-8")
        cnt = {k: sum(1 for r in rows if r[6] == k) for k in ("揚重可能", "重すぎ", "遠すぎ", "高すぎ")}
        print("揚重判定: " + "・".join(f"{k} {v}" for k, v in cnt.items()) + f"（{R.OUT_DIR / '揚重判定.md'}）")
        for nm, _ty, _v, w, rad, _nz, res, _x, far in rows:
            if res in ("重すぎ", "遠すぎ") and tw is None:
                print(f"揚重判定: {nm} {w:.2f}t・作業半径 {rad / 1000:.1f}m は{res}。"
                      + (f"作業半径 {far / 1000:.1f}m 以内に寄せれば吊れます" if far else "この機種ではどの半径でも吊れません（大きい機種に）"))
    if a.clash:
        p0, p1 = jib_axis(ps, origin, car) if tw is not None else boom_axis(ps, origin, car)
        els = []
        for ty in ("Wall", "Column", "Beam", "Slab", "Roof", "Object"):
            for e in c.tapir("GetElementsByType", {"elementType": ty}).get("elements", []):
                if e["elementId"]["guid"] != cg:
                    els.append((e, ty))
        objs = [e for e, ty in els if ty == "Object"]
        own = set()
        if objs:
            for e, d in zip(objs, c.get_details(objs)):
                if d.get("details", {}).get("libPart", {}).get("name", "").startswith("ashiba_"):
                    own.add(e["elementId"]["guid"])
        els = [(e, ty) for e, ty in els if e["elementId"]["guid"] not in own]
        bbs = boxes(c, [e for e, _t in els])
        hits = []
        for (e, ty), bb in zip(els, bbs):
            if bb is None:
                continue
            dist = seg_box_distance(p0, p1, bb[0], bb[1])
            if dist <= a.warn:
                hits.append((e, ty, dist, "接触" if dist <= a.contact else "警告"))
        c.tapir("HighlightElements", {"elements": [h[0] for h in hits], "highlightedColors": [COLORS[h[3]] for h in hits],
                                      "wireframe3D": False})
        md = ["# ブームの干渉", "", f"クレーン: {tw.model if tw is not None else m.name}。ブーム（ジブ）の中心軸（根元 {tuple(round(v) for v in p0)}・先 "
              f"{tuple(round(v) for v in p1)}）から部材の外形の箱まで。接触 {a.contact:.0f} 以内＝赤・警告 {a.warn:.0f} 以内＝黄", "",
              "| 部材 | 種類 | 距離 | 判定 |", "|---|---|---|---|"]
        md += [f"| {e['elementId']['guid'][:8]} | {ty} | {dist:.0f} | {res} |" for e, ty, dist, res in sorted(hits, key=lambda h: h[2])]
        (R.OUT_DIR / "ブームの干渉.md").write_text("\n".join(md), encoding="utf-8")
        print(f"ブームの干渉: 接触 {sum(1 for h in hits if h[3] == '接触')}・警告 {sum(1 for h in hits if h[3] == '警告')}"
              f"（{R.OUT_DIR / 'ブームの干渉.md'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
