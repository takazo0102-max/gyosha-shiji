"""壁の型枠を既存のモデルの壁に置く（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って
既存のモデルに自動配置するようにして）.

  python3 scripts/form_run.py            # 選んだ壁に（何も選んでいなければ全部の壁に）
  python3 scripts/form_run.py --all      # 全部の壁に

壁ごとに側圧から桟木・外端太・フォームタイの間隔を決め（src/ashiba/wall_form.py）、部品 ashiba_wform を1枚の壁に1つ置く。
柱（長方形）も同じ部材で（src/ashiba/column_form.py）、部品 ashiba_cform を1本の柱に1つ置く。
前に置いた型枠は壁ごとの控え（ashiba_out/型枠.json の GUID）で消してから置き直す。材料の目安と計算を ashiba_out に書く.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

FORM_OBJECT = "ashiba_wform"
COLUMN_OBJECT = "ashiba_cform"
RECORD = "型枠.json"


def _targets(c, all_els: bool) -> tuple[list, list]:
    """→ (壁 [(要素, 詳細)], 柱 [(要素, 詳細)])（選んだ壁・柱。選んだものに壁も柱も無いか --all なら全部）."""
    sel = [] if all_els else c.get_selected_elements()
    if sel:
        det = c.get_details(sel)
        w = [(e, d) for e, d in zip(sel, det) if d.get("type") == "Wall"]
        k = [(e, d) for e, d in zip(sel, det) if d.get("type") == "Column"]
        if w or k:
            return w, k
    out = []
    for t in ("Wall", "Column"):
        els = c.tapir("GetElementsByType", {"elementType": t}).get("elements", [])
        out.append(list(zip(els, c.get_details(els))) if els else [])
    return out[0], out[1]


def _place(c, part: str, at, z: float, ang_deg: float):
    """部品を (x, y, z) mm に置いて ang_deg 回す → 要素か None."""
    res = c.tapir("CreateObjects", {"objectsData": [{"libraryPartName": part, "coordinates": {
        "x": at[0] / 1000.0, "y": at[1] / 1000.0, "z": z / 1000.0}}]}).get("elements", [])
    if not res or "elementId" not in res[0]:
        return None
    if abs(ang_deg) > 1e-6:
        c.rotate_element(res[0], math.radians(ang_deg), at[0], at[1])
    return res[0]


def main(argv=None) -> int:
    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient
    from ashiba.column_form import DZ_MM, column_from_details, plan_column
    from ashiba.wall_form import face_layout, free_ends, plan_wall, wall_from_details

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="全部の壁・柱に置く")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    walls, cols = _targets(c, a.all)
    if not walls and not cols:
        print("型枠: 壁も柱もありません（壁・柱を選ぶか、モデルに置いてから押してください）")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(FORM_OBJECT)
    cpart = R.versioned_part_name(COLUMN_OBJECT)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), FORM_OBJECT)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    # 前に置いた型枠（この壁の分だけ）を消す
    old = [rec[e["elementId"]["guid"]] for e, _d in walls + cols if e["elementId"]["guid"] in rec]
    if old:
        alive = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])}
        gone = [{"elementId": {"guid": g}} for g in old if g in alive]
        if gone:
            c.delete_elements(gone)
            print(f"  前に置いた型枠 {len(gone)}個を消しました")
    # 角（L字・T字）の面の延ばし・縮めは、置かない壁も含めたモデルの全部の壁で決める
    every = c.tapir("GetElementsByType", {"elementType": "Wall"}).get("elements", [])
    allw = {}
    for e, d in zip(every, c.get_details(every) if every else []):
        w = wall_from_details(d)
        if w is not None:
            allw[e["elementId"]["guid"]] = w
    keys = list(allw)
    lay = dict(zip(keys, face_layout([allw[g] for g in keys])))
    frees = dict(zip(keys, free_ends([allw[g] for g in keys])))
    rows, calc, skipped = [], [], 0
    for k, (e, d) in enumerate(walls, 1):
        w = allw.get(e["elementId"]["guid"])
        if w is None or w["height"] <= 0:
            skipped += 1
            continue
        fl = lay[e["elementId"]["guid"]]
        f = plan_wall(w["length"], w["height"], w["thick"], fl["faces"], frees[e["elementId"]["guid"]], fl["tubes"], fl["sangi"],
                      fl["cuts"])
        name = d.get("id") or f"壁{k}"
        el = _place(c, part, w["a"], w["z0"], w["ang"])
        if el is None:
            print(f"  {name}: 型枠を置けませんでした")
            continue
        ch = f.calc
        c.set_gdl_parameters(el, {**pens, "A": w["length"] / 1000.0, "ZZYZX": w["height"] / 1000.0, "wT": w["thick"] / 1000.0,
                                  "sgX": ",".join(f"{x:.0f}" for x in f.sangi_x[0]),
                                  "sgX2": ",".join(f"{x:.0f}" for x in f.sangi_x[1]),
                                  "p1Seg": ",".join(f"{v:.0f}" for seg in f.ply_segs[0] for v in seg),
                                  "p2Seg": ",".join(f"{v:.0f}" for seg in f.ply_segs[1] for v in seg),
                                  "t1Seg": ",".join(f"{v:.0f}" for seg in f.tube_segs[0] for v in seg),
                                  "t2Seg": ",".join(f"{v:.0f}" for seg in f.tube_segs[1] for v in seg),
                                  "tbZ": ",".join(f"{z:.0f}" for z in f.tate_z),
                                  "tiX": ",".join(f"{x:.0f}" for x in f.tie_x),
                                  "endS": bool(f.ends[0]), "endE": bool(f.ends[1]),
                                  "cName": f"型枠 {name}",
                                  "cNote": f"桟木@{ch.sangi_pitch:.0f} 外端太@{ch.tate_pitch:.0f} FT@{ch.tie_pitch:.0f}"},
                            object_name=FORM_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        print(f"  {name}: 長さ {w['length']:.0f}・高さ {w['height']:.0f}・厚さ {w['thick']:.0f} → 桟木 @{ch.sangi_pitch:.0f}・"
              f"外端太 @{ch.tate_pitch:.0f}（{len(f.tate_z)}段）・フォームタイ @{ch.tie_pitch:.0f}（{len(f.tie_x)}列）"
              + ("" if ch.ok else "  注意: 計算が通らない（間隔をいちばん密にしても足りない。打ち継ぎで高さを分ける）"))
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] 長さ {w['length']:.0f}・高さ {w['height']:.0f}・厚さ {w['thick']:.0f}")
        calc += ["  " + s for s in ch.lines()]
    if skipped:
        print(f"  曲がった壁・傾いた壁など {skipped}枚は飛ばしました（直線の壁だけ）")
    skipped = 0
    for k, (e, d) in enumerate(cols, 1):
        col = column_from_details(d)
        if col is None or col["height"] <= 0:
            skipped += 1
            continue
        f = plan_column(col["width"], col["depth"], col["height"])
        name = d.get("id") or f"柱{k}"
        el = _place(c, cpart, col["c"], col["z0"], col["ang"])
        if el is None:
            print(f"  {name}: 型枠を置けませんでした")
            continue
        n_thr = len(f.tie_x) - 2 + len(f.tie_y) - 2
        c.set_gdl_parameters(el, {**pens, "A": col["width"] / 1000.0, "B": col["depth"] / 1000.0,
                                  "ZZYZX": col["height"] / 1000.0,
                                  "sgX": ",".join(f"{x:.0f}" for x in f.sangi_x),
                                  "sgY": ",".join(f"{y:.0f}" for y in f.sangi_y),
                                  "tbZ": ",".join(f"{z:.0f}" for z in f.tate_z),
                                  "tiX": ",".join(f"{x:.0f}" for x in f.tie_x),
                                  "tiY": ",".join(f"{y:.0f}" for y in f.tie_y),
                                  "dzB": DZ_MM / 1000.0, "cName": f"柱型枠 {name}",
                                  "cNote": f"桟木@{f.calc_x.sangi_pitch:.0f} 外端太@{f.calc_x.tate_pitch:.0f}"
                                           + (f" 貫通FT {n_thr}" if n_thr else "")},
                            object_name=COLUMN_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        print(f"  {name}: {col['width']:.0f}×{col['depth']:.0f}・高さ {col['height']:.0f} → 桟木 @{f.calc_x.sangi_pitch:.0f}・"
              f"外端太 @{f.calc_x.tate_pitch:.0f}（{len(f.tate_z)}段）・フォームタイは角の外"
              + (f"＋柱を貫く {n_thr}本/段" if n_thr else "") + ("" if f.ok else "  注意: 計算が通らない"))
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] 柱 {col['width']:.0f}×{col['depth']:.0f}・高さ {col['height']:.0f}")
        calc += ["  X の向き（±Y の面）: " + s_ for s_ in f.calc_x.lines()]
        calc += ["  Y の向き（±X の面）: " + s_ for s_ in f.calc_y.lines()]
    if skipped:
        print(f"  丸い柱・傾いた柱など {skipped}本は飛ばしました（長方形の柱だけ）")
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        out = R.OUT_DIR / "型枠_材料.csv"
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["壁", "品名", "数", "注"])
            wr.writerows(rows)
            tot = {}
            for _n, item, q, _note in rows:
                tot[item] = tot.get(item, 0) + q
            wr.writerow([])
            for item, q in tot.items():
                wr.writerow(["合計", item, q, ""])
        (R.OUT_DIR / "型枠_計算.txt").write_text("\n".join(calc) + "\n", encoding="utf-8")
        print(f"  型枠の材料の目安: {out}")
        print(f"  型枠の計算: {R.OUT_DIR / '型枠_計算.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
