"""壁の型枠を既存のモデルの壁に置く（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って
既存のモデルに自動配置するようにして）.

  python3 scripts/form_run.py            # 選んだ壁に（何も選んでいなければ全部の壁に）
  python3 scripts/form_run.py --all      # 全部の壁に

壁ごとに側圧から桟木・外端太・フォームタイの間隔を決め（src/ashiba/wall_form.py）、部品 ashiba_wform を1枚の壁に1つ置く。
柱（長方形）も同じ部材で（src/ashiba/column_form.py）、部品 ashiba_cform を1本の柱に1つ置く。
梁（まっすぐ）は側板・底板（src/ashiba/beam_form.py）、部品 ashiba_bform を1本の梁に1つ置く。
スラブは型枠と支保工（せき板・根太・大引・パイプサポート・水平つなぎ。src/ashiba/slab_form.py）、部品 ashiba_sform を1枚に1つ。
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
BEAM_OBJECT = "ashiba_bform"
SLAB_OBJECT = "ashiba_sform"
RECORD = "型枠.json"


TYPES = ("Wall", "Column", "Beam", "Slab")


def _targets(c, all_els: bool) -> list[list]:
    """→ [壁, 柱, 梁]（それぞれ [(要素, 詳細)]。選んだもの。選んだものにどれも無いか --all なら全部）."""
    sel = [] if all_els else c.get_selected_elements()
    if sel:
        det = c.get_details(sel)
        out = [[(e, d) for e, d in zip(sel, det) if d.get("type") == t] for t in TYPES]
        if any(out):
            return out
    out = []
    for t in TYPES:
        els = c.tapir("GetElementsByType", {"elementType": t}).get("elements", [])
        out.append(list(zip(els, c.get_details(els))) if els else [])
    return out


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
    from ashiba.beam_form import beam_extents, beam_from_details, plan_beam, slab_over
    from ashiba.column_form import DZ_MM, column_from_details, column_rect, plan_column, wall_hits
    from ashiba.slab_form import plan_slab, rect
    from ashiba.slab_heights import _inside, slabs_from_details
    from ashiba.wall_form import face_layout, free_ends, plan_wall, wall_from_details

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="全部の壁・柱に置く")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    walls, cols, beams, slabs_sel = _targets(c, a.all)
    if not walls and not cols and not beams and not slabs_sel:
        print("型枠: 壁も柱も梁もスラブもありません（壁・柱・梁・スラブを選ぶか、モデルに置いてから押してください）")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(FORM_OBJECT)
    cpart = R.versioned_part_name(COLUMN_OBJECT)
    bpart = R.versioned_part_name(BEAM_OBJECT)
    spart = R.versioned_part_name(SLAB_OBJECT)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), FORM_OBJECT)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    # 前に置いた型枠（この壁の分だけ）を消す
    old = [rec[e["elementId"]["guid"]] for e, _d in walls + cols + beams + slabs_sel if e["elementId"]["guid"] in rec]
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
    # 柱（壁の端が柱に入れば、壁の型枠は柱の型枠まで）
    everyc = c.tapir("GetElementsByType", {"elementType": "Column"}).get("elements", [])
    allc = [x for x in (column_from_details(d) for d in (c.get_details(everyc) if everyc else [])) if x is not None]
    rects = [column_rect(x) for x in allc]
    lay = dict(zip(keys, face_layout([allw[g] for g in keys], rects)))
    frees = dict(zip(keys, free_ends([allw[g] for g in keys], rects)))
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
        f = plan_column(col["width"], col["depth"], col["height"], wall_hits(col, list(allw.values())))
        name = d.get("id") or f"柱{k}"
        el = _place(c, cpart, col["c"], col["z0"], col["ang"])
        if el is None:
            print(f"  {name}: 型枠を置けませんでした")
            continue
        n_thr = sum(1 for x in f.tie_x if abs(x) <= col["width"] / 2) + sum(1 for y in f.tie_y if abs(y) <= col["depth"] / 2)
        c.set_gdl_parameters(el, {**pens, "A": col["width"] / 1000.0, "B": col["depth"] / 1000.0,
                                  "ZZYZX": col["height"] / 1000.0,
                                  **{f"ply{k}": ",".join(f"{v:.0f}" for seg in fc["ply"] for v in seg)
                                     for k, fc in enumerate(f.faces, 1)},
                                  **{f"sg{k}": ",".join(f"{v:.0f}" for v in fc["sangi"]) for k, fc in enumerate(f.faces, 1)},
                                  **{f"tb{k}": ",".join(f"{v:.0f}" for seg in fc["tube"] for v in seg)
                                     for k, fc in enumerate(f.faces, 1)},
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
        for note in f.notes():
            print(f"    注意: {note}")
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] 柱 {col['width']:.0f}×{col['depth']:.0f}・高さ {col['height']:.0f}")
        calc += ["  X の向き（±Y の面）: " + s_ for s_ in f.calc_x.lines()]
        calc += ["  Y の向き（±X の面）: " + s_ for s_ in f.calc_y.lines()]
    if skipped:
        print(f"  丸い柱・傾いた柱など {skipped}本は飛ばしました（長方形の柱だけ）")
    # 梁: 側板の高さは上のスラブの下端まで（側ごと）、端は柱の面で止める
    skipped = 0
    sels = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", []) if beams or slabs_sel else []
    slabs = slabs_from_details(c.get_details(sels)) if sels else []
    for k, (e, d) in enumerate(beams, 1):
        bm = beam_from_details(d)
        if bm is None:
            skipped += 1
            continue
        ex = beam_extents(bm, rects)
        st = slab_over(bm, slabs)
        f = plan_beam(bm["length"], bm["width"], bm["depth"], st, ex["ext"], ex["tubes"], ex["sangi"], ex["ends"])
        # 受けの単管を受けるパイプサポート: 下の床（下のスラブの天端。無ければ 0）から
        mid = ((bm["ca"][0] + bm["cb"][0]) / 2.0, (bm["ca"][1] + bm["cb"][1]) / 2.0)
        below = [o.top_mm for o in slabs if o.top_mm < bm["bottom"] - 300.0 and _inside(mid, o.polygon)]
        f.post_h = bm["bottom"] - 12.0 - 60.0 - 48.6 - (max(below) if below else 0.0)
        name = d.get("id") or f"梁{k}"
        el = _place(c, bpart, bm["ca"], bm["bottom"], bm["ang"])
        if el is None:
            print(f"  {name}: 型枠を置けませんでした")
            continue
        c.set_gdl_parameters(el, {**pens, "A": bm["length"] / 1000.0, "ZZYZX": bm["depth"] / 1000.0, "wB": bm["width"] / 1000.0,
                                  "sideH": f.side_hs[0] / 1000.0, "sideH2": f.side_hs[1] / 1000.0, "nTie": len(f.tie_z),
                                  "x0": ex["ext"][0] / 1000.0, "x1": ex["ext"][1] / 1000.0,
                                  "tb0": f.tubes[0] / 1000.0, "tb1": f.tubes[1] / 1000.0,
                                  "sgX": ",".join(f"{x:.0f}" for x in f.sangi_x),
                                  "tbZ": ",".join(f"{z:.0f}" for z in f.tate_z),
                                  "tiX": ",".join(f"{x:.0f}" for x in f.tie_x),
                                  "botY": ",".join(f"{y:.0f}" for y in f.bot_y),
                                  "ukeX": ",".join(f"{x:.0f}" for x in f.uke_x),
                                  "endS": bool(f.ends[0]), "endE": bool(f.ends[1]), "cName": f"梁型枠 {name}",
                                  "psH": max(0.0, f.post_h) / 1000.0, "psY": (bm["width"] / 2.0 + 12.0 + 60.0 + 30.0) / 1000.0,
                                  "cNote": f"桟木@{f.side.sangi_pitch:.0f} 外端太{len(f.tate_z)}段 FT@{f.side.tie_pitch:.0f} 受け@{f.uke_pitch:.0f}"},
                            object_name=BEAM_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        print(f"  {name}: {bm['width']:.0f}×{bm['depth']:.0f}・長さ {bm['length']:.0f}（スラブ {st[0]:.0f}・{st[1]:.0f}）→ 側板 "
              f"{f.side_hs[0]:.0f}・{f.side_hs[1]:.0f}・桟木 @{f.side.sangi_pitch:.0f}・外端太 {len(f.tate_z)}段・フォームタイ "
              f"@{f.side.tie_pitch:.0f}（{len(f.tie_z)}段）・底の受け @{f.uke_pitch:.0f}" + ("" if f.ok else "  注意: 計算が通らない"))
        if len(f.tie_z) < len(f.tate_z):
            print("    注意: 片側だけの高さにある外端太はフォームタイで締められない。スラブの止め型枠か控えで受ける")
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] 梁 {bm['width']:.0f}×{bm['depth']:.0f}・長さ {bm['length']:.0f}")
        calc += ["  " + s_ for s_ in f.lines()]
    if skipped:
        print(f"  曲がった梁・傾いた梁など {skipped}本は飛ばしました（まっすぐな梁だけ）")
    # スラブ: 型枠と支保工。梁・壁・柱の所は抜き、パイプサポートは下の床（下のスラブの天端。無ければ 0）から
    if slabs_sel:
        everyb = c.tapir("GetElementsByType", {"elementType": "Beam"}).get("elements", [])
        allb = [x for x in (beam_from_details(d) for d in (c.get_details(everyb) if everyb else [])) if x is not None]
    for k, (e, d) in enumerate(slabs_sel, 1):
        info = slabs_from_details([d])
        if not info or info[0].thickness_mm <= 0:
            continue
        sl = info[0]
        bottom = sl.top_mm - sl.thickness_mm
        cx = sum(p[0] for p in sl.polygon) / len(sl.polygon)
        cy = sum(p[1] for p in sl.polygon) / len(sl.polygon)
        below = [o.top_mm for o in slabs if o.top_mm < bottom - 300.0 and _inside((cx, cy), o.polygon)]
        floor = max(below) if below else 0.0
        holes = []
        for bm in allb:
            mid = ((bm["ca"][0] + bm["cb"][0]) / 2.0, (bm["ca"][1] + bm["cb"][1]) / 2.0)
            if abs(bm["top"] - sl.top_mm) <= 20.0 and _inside(mid, sl.polygon):
                holes.append(rect(mid, bm["u"], bm["length"] / 2.0, bm["width"] / 2.0, 12.0))
        for w in allw.values():
            if w["z0"] < bottom and w["z0"] + w["height"] >= bottom - 20.0:
                off = (w["lo"] + w["hi"]) / 2.0
                mid = ((w["ca"][0] + w["cb"][0]) / 2.0 + w["n"][0] * off, (w["ca"][1] + w["cb"][1]) / 2.0 + w["n"][1] * off)
                if _inside(mid, sl.polygon):
                    holes.append(rect(mid, w["u"], w["length"] / 2.0, w["thick"] / 2.0, 12.0))
        for col in allc:
            if col["z0"] < bottom and col["z0"] + col["height"] >= bottom - 20.0 and _inside(col["c"], sl.polygon):
                a_ = math.radians(col["ang"])
                holes.append(rect(col["c"], (math.cos(a_), math.sin(a_)), col["width"] / 2.0, col["depth"] / 2.0, 12.0))
        f = plan_slab(sl.polygon, sl.thickness_mm, bottom, floor, holes)
        name = d.get("id") or f"スラブ{k}"
        el = _place(c, spart, f.origin, bottom, f.ang)
        if el is None:
            print(f"  {name}: 型枠を置けませんでした")
            continue
        ring = [f.outer] + f.holes
        c.set_gdl_parameters(el, {**pens,
                                  "polyU": ",".join(f"{p[0]:.0f}" for r_ in ring for p in r_),
                                  "polyV": ",".join(f"{p[1]:.0f}" for r_ in ring for p in r_),
                                  "ringN": ",".join(str(len(r_)) for r_ in ring),
                                  "neU": ",".join(f"{x:.0f}" for _a, _b, x in f.neda),
                                  "neV0": ",".join(f"{a_:.0f}" for a_, _b, _x in f.neda),
                                  "neV1": ",".join(f"{b_:.0f}" for _a, b_, _x in f.neda),
                                  "obV": ",".join(f"{y:.0f}" for _a, _b, y in f.obiki),
                                  "obU0": ",".join(f"{a_:.0f}" for a_, _b, _y in f.obiki),
                                  "obU1": ",".join(f"{b_:.0f}" for _a, b_, _y in f.obiki),
                                  "psU": ",".join(f"{x:.0f}" for x, _y in f.posts),
                                  "psV": ",".join(f"{y:.0f}" for _x, y in f.posts),
                                  "postH": f.post_h / 1000.0, "tieZ": ",".join(f"{z:.0f}" for z in f.ties),
                                  "cName": f"スラブ型枠 {name}",
                                  "cNote": f"PS @{f.spacing.su:.0f}×{f.spacing.sv:.0f} 長さ {f.post_h:.0f}"},
                            object_name=SLAB_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        print(f"  {name}: 厚さ {sl.thickness_mm:.0f}・下端 {bottom:.0f}（床 {floor:.0f}）→ 根太 単管 @300・大引 □100×50 "
              f"@{f.spacing.sv:.0f}・パイプサポート @{f.spacing.su:.0f}×{f.spacing.sv:.0f}（{len(f.posts)}本・長さ {f.post_h:.0f}・"
              f"1本 {f.spacing.post_kn:.1f}kN）" + (f"・水平つなぎ {len(f.ties)}段" if f.ties else "")
              + (f"・梁・壁・柱の所 {len(holes)}か所を抜く" if holes else "") + ("" if f.spacing.ok else "  注意: 計算が通らない"))
        if not below:
            print("    注意: 下の床（スラブ）が見つからないので、パイプサポートは高さ 0 から。地盤なら敷板・敷角を")
        if f.post_h > 4800.0:
            print("    注意: パイプサポートが長すぎる（継ぐのは2本まで）。枠組・くさびの支保工（内部足場）を考える")
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] スラブ 厚さ {sl.thickness_mm:.0f}")
        calc += ["  " + s_ for s_ in f.lines()]
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"型枠: 壁 {sum(1 for e, _d in walls if e['elementId']['guid'] in rec)}枚・柱 "
          f"{sum(1 for e, _d in cols if e['elementId']['guid'] in rec)}本・梁 {sum(1 for e, _d in beams if e['elementId']['guid'] in rec)}本・"
          f"スラブ {sum(1 for e, _d in slabs_sel if e['elementId']['guid'] in rec)}枚に置きました")
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
