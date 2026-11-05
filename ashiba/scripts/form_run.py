"""壁の型枠を既存のモデルの壁に置く（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ そとばた フォームタイを作って
既存のモデルに自動配置するようにして）.

  python3 scripts/form_run.py            # 選んだ壁に（何も選んでいなければ全部の壁に）
  python3 scripts/form_run.py --all      # 全部の壁に
  python3 scripts/form_run.py --remove   # 置いた型枠（控えの GUID）・支保工足場と型枠支保工のレイアウトを消す
  python3 scripts/form_run.py --shoring  # 選んだスラブの支保工を支保工足場（内部足場）に（scripts/shoring_run.py）
  python3 scripts/form_run.py --pipe     # 選んだスラブの支保工をパイプサポートに戻す

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
SYSTEM_RECORD = "支保工足場.json"     # 支保工足場にしたスラブ（GUID → 置いた内部足場の GUID）
STAGE_OBJECT = "ashiba_stage"
# 支保工足場のスラブの型枠の部品: パイプサポート・大引・敷き桟木・根がらみ・水平つなぎ・筋かいは内部足場が持つ
NO_POSTS = {k: "" for k in ("obV", "obU0", "obU1", "psU", "psV", "slU0", "slU1", "slV", "tieZ",
                            "brU", "brV", "brZ", "brAz", "brPo", "brL")}
FORM_PARTS = (FORM_OBJECT, COLUMN_OBJECT, BEAM_OBJECT, SLAB_OBJECT)


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


def _delete_alive(c, guids) -> int:
    """控えの GUID のうち、まだある部品だけ消す."""
    if not guids:
        return 0
    alive = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])}
    gone = [{"elementId": {"guid": g}} for g in guids if g in alive]
    if gone:
        c.delete_elements(gone)
    return len(gone)


def place_shoring(c, R, f, name: str, floor: float, bottom: float, thick: float, rec: dict) -> list:
    """支保工足場: スラブの型枠 f の下を梁・壁で区切った長方形ごとに内部足場（用途 支保工）を解いて置く。控え rec の
    stages を置き直す. 戻り値は図面・計算書の控え（shoring_stage.system_summary）の並び."""
    from ashiba.cli import resolve_series_id
    from ashiba.interior_stage import shoring_ties, solve_stage, stage_params
    from ashiba.master import load_master
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.shoring_stage import shoring_cells, stage_item, system_summary
    from ashiba.structural import load_capacities

    _delete_alive(c, rec.get("stages", []))
    rec["stages"] = []
    spec = {**R.SPEC, **R.load_spec_override()}
    sid = resolve_series_id(spec)
    master, caps = load_master(sid), load_capacities(sid)
    tie = rec.get("tie") or shoring_ties(caps)[0]
    try:
        st_ = c.tapir("GetStories", {})
        act = int(st_.get("actStory", 0))
        story = next((float(x["level"]) * 1000.0 for x in st_.get("stories", []) if int(x.get("index", -99)) == act), 0.0)
    except Exception:
        story = 0.0
    a = math.radians(f.ang)
    u, v = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    o = f.origin
    W = lambda p: (o[0] + u[0] * p[0] + v[0] * p[1], o[1] + u[1] * p[0] + v[1] * p[1])
    L = lambda p: ((p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1], (p[0] - o[0]) * v[0] + (p[1] - o[1]) * v[1])
    cells, notes = shoring_cells(f.outer, f.holes)
    for n_ in notes:
        print(f"    注意: {n_}")
    part = R.versioned_part_name(STAGE_OBJECT)
    try:
        mats = c.find_member_surfaces()
    except Exception:
        mats = {}
    out = []
    for k, cell in enumerate(cells, 1):
        item = stage_item(f"{name} 支保工{k}", cell, W, u, floor, story, bottom, thick, tie)
        try:
            st = solve_stage(item, master, caps)
        except ValueError as ex:
            print(f"    注意: {item['name']}: {ex}")
            continue
        (el,) = c.create_objects([(part, st.origin[0], st.origin[1])])
        params = {**stage_params(st, master=master), **gdl_pens(parse_pens(spec.get("pens")), STAGE_OBJECT)}
        for key in ("matScaf", "matDeck"):
            if mats.get(key):
                params[key] = mats[key]
        c.set_gdl_parameters(el, params)
        rec["stages"].append(el["elementId"]["guid"])
        sy = system_summary(st, master, caps, L)
        out.append(sy)
        bad = [ck for ck in st.checks if ck.status != "OK"]
        print(f"  {item['name']}: {st.length_u:.0f}×{st.length_v:.0f}（{'+'.join(map(str, st.spans_u))} × {'+'.join(map(str, st.spans_v))}）"
              f"・支柱の天端 {st.top_mm}・Uジャッキ {st.uhead_ext_mm}・支柱1本 {sy['post_kn']:.1f}"
              + (f"／{sy['allow_kn']:.1f}kN" if sy["allow_kn"] else "kN") + f"（{tie}）"
              + (f"・要確認 {len(bad)}件" if bad else "・検定 OK"))
    return out


def brace_params(braces) -> dict:
    """大筋かい → 部品 ashiba_sform のパラメータ（始めの点・方位・鉛直からの角・長さ。角は度×1000）."""
    cols = {k: [] for k in ("brU", "brV", "brZ", "brAz", "brPo", "brL")}
    for u0, v0, z0, u1, v1, z1 in braces:
        du, dv, dz = u1 - u0, v1 - v0, z1 - z0
        L = math.sqrt(du * du + dv * dv + dz * dz)
        if L < 1.0:
            continue
        for k, val in (("brU", u0), ("brV", v0), ("brZ", z0), ("brAz", math.degrees(math.atan2(dv, du)) * 1000.0),
                       ("brPo", math.degrees(math.acos(max(-1.0, min(1.0, dz / L)))) * 1000.0), ("brL", L)):
            cols[k].append(f"{val:.0f}")
    return {k: ",".join(v) for k, v in cols.items()}


def remove(c, out_dir: Path) -> int:
    """型枠の撤去（パレットの「型枠の撤去」）: 型枠の部品（控え 型枠.json の GUID と、控えに無くても壁・柱・梁・スラブの型枠の
    部品。控えが古くなって残った分も）を消し、レイアウト「型枠支保工 …」も消す。躯体・足場の部品は消さない."""
    from ashiba.elevation_sections import _delete_items, _tree, walk_tree
    from ashiba.form_layout import LAYOUT_PREFIX
    from ashiba.tapir_adapter import is_ashiba_part

    rec_path = out_dir / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    alive = {x["elementId"]["guid"] for x in objs}
    forms = {e["elementId"]["guid"] for e, d in zip(objs, c.get_details(objs) if objs else [])
             if is_ashiba_part(str(((d.get("details") or {}).get("libPart") or {}).get("name", "")), FORM_PARTS)}
    gone = [{"elementId": {"guid": g}} for g in (set(rec.values()) & alive) | forms]
    if gone:
        c.delete_elements(gone)
    if rec:
        rec_path.write_text("{}", encoding="utf-8")
    # 支保工足場（内部足場）も型枠支保工なので消す。スラブの控えも外す（次の「型枠」はパイプサポート）
    sys_path = out_dir / SYSTEM_RECORD
    try:
        sysrec = json.loads(sys_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sysrec = {}
    stages = [g for v in (sysrec.get("slabs") or {}).values() for g in v.get("stages", [])]
    n_st = _delete_alive(c, stages)
    if sysrec:
        sys_path.write_text("{}", encoding="utf-8")
    lays = [it["guid"] for it in walk_tree(_tree(c, "LayoutBook"))
            if it["type"] == "LayoutItem" and it["name"].startswith(LAYOUT_PREFIX + " ")]
    _delete_items(c, lays)
    print(f"型枠の撤去: 型枠 {len(gone)}個・支保工足場 {n_st}個・レイアウト {len(lays)}枚を消しました")
    return 0


def main(argv=None) -> int:
    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient
    from ashiba.beam_form import beam_extents, beam_from_details, plan_beam, slab_over
    from ashiba.column_form import DZ_MM, column_from_details, column_rect, plan_column, wall_hits
    from ashiba.slab_form import NEGARAMI_Z_MM, obiki_angle, plan_slab, rect
    from ashiba.shoring_stage import merge_system
    from ashiba.slab_heights import _inside, slabs_from_details
    from ashiba.wall_form import face_layout, free_ends, in_column, plan_wall, wall_from_details

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="全部の壁・柱に置く")
    ap.add_argument("--remove", action="store_true", help="置いた型枠と型枠支保工のレイアウトを消す")
    ap.add_argument("--shoring", action="store_true", help="選んだスラブ（無ければ全部）の支保工を支保工足場（内部足場）にする")
    ap.add_argument("--pipe", action="store_true", help="選んだスラブ（無ければ全部）の支保工をパイプサポートに戻す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    if a.remove:
        return remove(c, R.OUT_DIR)
    walls, cols, beams, slabs_sel = _targets(c, a.all)
    if not walls and not cols and not beams and not slabs_sel:
        print("型枠: 壁も柱も梁もスラブもありません（壁・柱・梁・スラブを選ぶか、モデルに置いてから押してください）")
        return 1
    # 支保工足場（利用者の指定 2026-10-31: しほこう足場を内部足場から作成して）: 控えにあるスラブはパイプサポートの代わりに内部足場
    sys_path = R.OUT_DIR / SYSTEM_RECORD
    try:
        sysrec = json.loads(sys_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sysrec = {}
    sysrec.setdefault("slabs", {})
    if a.shoring or a.pipe:
        if not slabs_sel:
            print("支保工足場: スラブがありません（スラブを選ぶか、モデルに置いてから押してください）")
            return 1
        for e, _d in slabs_sel:
            g = e["elementId"]["guid"]
            if a.shoring:
                sysrec["slabs"].setdefault(g, {"stages": []})
            elif g in sysrec["slabs"]:
                _delete_alive(c, sysrec["slabs"].pop(g).get("stages", []))
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
    # スラブと梁（壁・柱の型枠はスラブ・梁の下端で止める。梁の型枠の側板の高さ・スラブの穴にも使う）
    sels = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
    slabs = slabs_from_details(c.get_details(sels)) if sels else []
    everyb = c.tapir("GetElementsByType", {"elementType": "Beam"}).get("elements", [])
    allb = [x for x in (beam_from_details(d) for d in (c.get_details(everyb) if everyb else [])) if x is not None]

    def cap_top(top: float, pts: list, rect_=None) -> float:
        """壁・柱の型枠の上端: 上にかかるスラブの下端・取り付く梁の下端より上へ出さない（利用者の指定 2026-10-31: せぱ
        飛び出てない？？ 梁・スラブの中を外端太・フォームタイが貫いていた）."""
        out = top
        for o in slabs:
            bot = o.top_mm - o.thickness_mm
            if bot < out - 1.0 and any(_inside(p, o.polygon) for p in pts):
                out = bot
        if rect_ is not None:
            for bm in allb:
                if bm["bottom"] < out - 1.0 and (in_column(bm["ca"], rect_, 5.0) or in_column(bm["cb"], rect_, 5.0)):
                    out = bm["bottom"]
        return out

    rows, calc, skipped = [], [], 0
    # 型枠支保工計画図の控え（scripts/form_plan_run.py が図面・計算書・計画届の判定を作る）
    plan = {"walls": [], "columns": [], "beams": [], "slabs": []}
    r2 = lambda p: [round(p[0], 1), round(p[1], 1)]
    for k, (e, d) in enumerate(walls, 1):
        w = allw.get(e["elementId"]["guid"])
        if w is None or w["height"] <= 0:
            skipped += 1
            continue
        fl = lay[e["elementId"]["guid"]]
        mids = [(w["ca"][0] + (w["cb"][0] - w["ca"][0]) * t_, w["ca"][1] + (w["cb"][1] - w["ca"][1]) * t_) for t_ in (0.25, 0.5, 0.75)]
        top = cap_top(w["z0"] + w["height"], mids)
        if top < w["z0"] + w["height"] - 1.0:
            w = {**w, "height": top - w["z0"]}
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
        plan["walls"].append({"name": name, "ca": r2(w["ca"]), "cb": r2(w["cb"]), "u": list(w["u"]), "n": list(w["n"]),
                              "lo": w["lo"], "hi": w["hi"], "thick": w["thick"], "z0": w["z0"], "height": w["height"],
                              "ply": [[list(s_) for s_ in segs] for segs in f.ply_segs], "sangi": ch.sangi_pitch,
                              "tate_z": f.tate_z, "tie_x": f.tie_x, "tie_pitch": ch.tie_pitch, "ends": list(f.ends),
                              "lines": ch.lines(), "pressure": ch.pressure})
    if skipped:
        print(f"  曲がった壁・傾いた壁など {skipped}枚は飛ばしました（直線の壁だけ）")
    skipped = 0
    for k, (e, d) in enumerate(cols, 1):
        col = column_from_details(d)
        if col is None or col["height"] <= 0:
            skipped += 1
            continue
        r_ = column_rect(col)
        corners = [(col["c"][0] + r_["ux"][0] * sx * col["width"] / 2 + r_["uy"][0] * sy * col["depth"] / 2,
                    col["c"][1] + r_["ux"][1] * sx * col["width"] / 2 + r_["uy"][1] * sy * col["depth"] / 2)
                   for sx in (-0.99, 0.99) for sy in (-0.99, 0.99)] + [col["c"]]
        top = cap_top(col["z0"] + col["height"], corners, r_)
        if top < col["z0"] + col["height"] - 1.0:
            print(f"  {d.get('id') or ''}: 柱の型枠は梁・スラブの下端 {top:.0f} まで（上は梁・スラブの型枠で）")
            col = {**col, "height": top - col["z0"]}
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
                                  "dzB": DZ_MM / 1000.0, "cName": f"柱型枠 {name}", "clampOn": bool(f.clamp),
                                  "cNote": f"桟木@{f.calc_x.sangi_pitch:.0f} " + (f"コラムクランプ{len(f.tate_z)}段" if f.clamp else f"外端太{len(f.tate_z)}段")
                                           + (f" 貫通FT {n_thr}" if n_thr else "")},
                            object_name=COLUMN_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        gaps = [b - a for a, b in zip(f.tate_z, f.tate_z[1:])] or [0.0]
        print(f"  {name}: {col['width']:.0f}×{col['depth']:.0f}・高さ {col['height']:.0f} → 桟木 @{f.calc_x.sangi_pitch:.0f}・"
              + (f"コラムクランプ {len(f.tate_z)}段（下 @{gaps[0]:.0f}〜上 @{max(gaps):.0f}）" if f.clamp else
                 f"外端太 {len(f.tate_z)}段（下 @{gaps[0]:.0f}〜上 @{max(gaps):.0f}）・フォームタイは角の外"
                 + (f"＋柱を貫く {n_thr}本/段" if n_thr else "") + "（壁が取り付くのでクランプは使えない）")
              + ("" if f.ok else "  注意: 計算が通らない"))
        for note in f.notes():
            print(f"    注意: {note}")
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] 柱 {col['width']:.0f}×{col['depth']:.0f}・高さ {col['height']:.0f}")
        calc += ["  X の向き（±Y の面）: " + s_ for s_ in f.calc_x.lines()]
        calc += ["  Y の向き（±X の面）: " + s_ for s_ in f.calc_y.lines()]
        plan["columns"].append({"name": name, "c": r2(col["c"]), "ang": col["ang"], "width": col["width"], "depth": col["depth"],
                                "z0": col["z0"], "height": col["height"], "clamp": bool(f.clamp), "tate_z": f.tate_z,
                                "tie_x": f.tie_x, "tie_y": f.tie_y, "sangi": f.calc_x.sangi_pitch,
                                "lines": ["X の向き: " + s_ for s_ in f.calc_x.lines()] + ["Y の向き: " + s_ for s_ in f.calc_y.lines()],
                                "pressure": f.calc_x.pressure})
    if skipped:
        print(f"  丸い柱・傾いた柱など {skipped}本は飛ばしました（長方形の柱だけ）")
    # 梁: 側板の高さは上のスラブの下端まで（側ごと）、端は柱の面で止める
    skipped = 0
    for k, (e, d) in enumerate(beams, 1):
        bm = beam_from_details(d)
        if bm is None:
            skipped += 1
            continue
        ex = beam_extents(bm, rects)
        st = slab_over(bm, slabs)
        # 受けの単管を受けるパイプサポート: 下の床（下のスラブの天端。無ければ 0）から。1本の荷重がメーカーの許容支持力に
        # 入るように大引の間隔を決めるので、長さを先に求めて渡す
        mid = ((bm["ca"][0] + bm["cb"][0]) / 2.0, (bm["ca"][1] + bm["cb"][1]) / 2.0)
        below = [o.top_mm for o in slabs if o.top_mm < bm["bottom"] - 300.0 and _inside(mid, o.polygon)]
        post_h = bm["bottom"] - 12.0 - 50.0 - 90.0 - 45.0 - (max(below) if below else 0.0)    # 根太 50・大引 90・敷き桟木 45
        f = plan_beam(bm["length"], bm["width"], bm["depth"], st, ex["ext"], ex["tubes"], ex["sangi"], ex["ends"], post_h)
        # 敷き桟木の向きは上のスラブの敷き桟木（大引の向き）に揃える（利用者の指定 2026-10-31: さんぎの向き揃えて）
        over = [o for o in slabs if abs(o.top_mm - bm["top"]) <= 20.0 and any(_inside((mid[0] + bm["u"][1] * s_, mid[1] - bm["u"][0] * s_), o.polygon)
                                                                           for s_ in (bm["width"], -bm["width"]))]
        if over:
            da = math.radians(obiki_angle(over[0].polygon) - bm["ang"])
            f.sill_cross = abs(math.cos(da)) < 0.7
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
                                  "psH": max(0.0, f.post_h) / 1000.0, "sillCross": bool(f.sill_cross), "psY": (bm["width"] / 2.0 + 12.0 + 60.0 + 30.0) / 1000.0,
                                  "cNote": f"桟木@{f.side.sangi_pitch:.0f} 外端太{len(f.tate_z)}段 FT@{f.side.tie_pitch:.0f} 大引@{f.uke_pitch:.0f}"},
                            object_name=BEAM_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        print(f"  {name}: {bm['width']:.0f}×{bm['depth']:.0f}・長さ {bm['length']:.0f}（スラブ {st[0]:.0f}・{st[1]:.0f}）→ 側板 "
              f"{f.side_hs[0]:.0f}・{f.side_hs[1]:.0f}・桟木 @{f.side.sangi_pitch:.0f}・外端太 {len(f.tate_z)}段・フォームタイ "
              f"@{f.side.tie_pitch:.0f}（{len(f.tie_z)}段）・底 根太 □50×50・杉大引 @{f.uke_pitch:.0f}" + ("" if f.ok else "  注意: 計算が通らない"))
        if len(f.tie_z) < len(f.tate_z):
            print("    注意: 片側だけの高さにある外端太はフォームタイで締められない。スラブの止め型枠か控えで受ける")
        for item, q, note in f.quantities():
            rows.append((name, item, q, note))
        calc.append(f"[{name}] 梁 {bm['width']:.0f}×{bm['depth']:.0f}・長さ {bm['length']:.0f}")
        calc += ["  " + s_ for s_ in f.lines()]
        plan["beams"].append({"name": name, "ca": r2(bm["ca"]), "cb": r2(bm["cb"]), "u": list(bm["u"]), "width": bm["width"],
                              "depth": bm["depth"], "top": bm["top"], "bottom": bm["bottom"], "ext": list(ex["ext"]),
                              "side_hs": list(f.side_hs), "tate_z": f.tate_z, "tie_z": f.tie_z, "tie_x": f.tie_x,
                              "tie_pitch": f.side.tie_pitch, "sangi": f.side.sangi_pitch, "uke_x": f.uke_x,
                              "uke_pitch": f.uke_pitch, "bot_y": f.bot_y, "post_h": f.post_h, "post_kn": f.post_kn,
                              "ps_allow": f.ps_allow, "ps_tied": f.ps_tied,
                              "psY": bm["width"] / 2.0 + 12.0 + 60.0 + 30.0, "sill_cross": bool(f.sill_cross),
                              "slab_t": list(st), "lines": f.lines()})
    if skipped:
        print(f"  曲がった梁・傾いた梁など {skipped}本は飛ばしました（まっすぐな梁だけ）")
    # スラブ: 型枠と支保工。梁・壁・柱の所は抜き、パイプサポートは下の床（下のスラブの天端。無ければ 0）から
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
        sguid = e["elementId"]["guid"]
        systems = None
        if sguid in sysrec["slabs"]:
            systems = place_shoring(c, R, f, name, floor, bottom, sl.thickness_mm, sysrec["slabs"][sguid])
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
                                  "postH": f.post_h / 1000.0, "tieZ": ",".join(f"{z:.0f}" for z in [NEGARAMI_Z_MM] + list(f.ties)),
                                  **brace_params(f.braces),
                                  "slU0": ",".join(f"{a_:.0f}" for a_, _b, _v in f.sills()),
                                  "slU1": ",".join(f"{b_:.0f}" for _a, b_, _v in f.sills()),
                                  "slV": ",".join(f"{v_:.0f}" for _a, _b, v_ in f.sills()),
                                  "cName": f"スラブ型枠 {name}",
                                  "cNote": (f"PS @{f.spacing.su:.0f}×{f.spacing.sv:.0f} 長さ {f.post_h:.0f}" if systems is None
                                            else f"支保工足場 {len(systems)}か所"),
                                  # 支保工足場のスラブは支柱まわりを内部足場が持つ（最後に上書きする）
                                  **(NO_POSTS if systems is not None else {})},
                            object_name=SLAB_OBJECT)
        rec[e["elementId"]["guid"]] = el["elementId"]["guid"]
        if systems is not None:
            print(f"  {name}: 厚さ {sl.thickness_mm:.0f}・下端 {bottom:.0f}（床 {floor:.0f}）→ せき板・根太 □50×50 @300、支保工足場 {len(systems)}か所（上に書いた内部足場）")
        else:
            print(f"  {name}: 厚さ {sl.thickness_mm:.0f}・下端 {bottom:.0f}（床 {floor:.0f}）→ 根太 □50×50 @300・杉大引 90×90 "
                f"@{f.spacing.sv:.0f}・パイプサポート @{f.spacing.su:.0f}×{f.spacing.sv:.0f}（{len(f.posts)}本・長さ {f.post_h:.0f}・"
                f"1本 {f.spacing.post_kn:.1f}kN）" + (f"・水平つなぎ {len(f.ties)}段" if f.ties else "")
                + (f"・梁・壁・柱の所 {len(holes)}か所を抜く" if holes else "") + ("" if f.spacing.ok else "  注意: 計算が通らない"))
        if not below:
            print("    注意: 下の床（スラブ）が見つからないので、パイプサポートは高さ 0 から。地盤なら敷板・敷角を")
        if f.post_h > 4800.0:
            print("    注意: パイプサポートが長すぎる（継ぐのは2本まで）。枠組・くさびの支保工（内部足場）を考える")
        if systems is None:
            for item, q, note in f.quantities():
                rows.append((name, item, q, note))
            calc.append(f"[{name}] スラブ 厚さ {sl.thickness_mm:.0f}")
            calc += ["  " + s_ for s_ in f.lines()]
        else:
            # せき板・根太は型枠、支柱から大引までは支保工足場（内部足場）の数量
            for item, q, note in f.quantities():
                if "合板" in item or "根太" in item:
                    rows.append((name, item, q, note))
            for sy in systems:
                for cls, size, n, use in sy["quantity"]:
                    rows.append((name, f"{cls}" + (f" {size}" if size else ""), n, f"支保工足場 {sy['name']}・{use}"))
            calc.append(f"[{name}] スラブ 厚さ {sl.thickness_mm:.0f}（支保工足場）")
            calc += ["  " + s_ for s_ in f.spacing.lines(f.q)[:3]]
            for sy in systems:
                calc += [f"  {sy['name']}: {c_[0]} {c_[1]} — {c_[2]}" for c_ in sy["checks"]]
        plan["slabs"].append({"name": name, "origin": r2(f.origin), "ang": f.ang, "outer": [r2(p_) for p_ in f.outer],
                              "holes": [[r2(p_) for p_ in h_] for h_ in f.holes], "thick": sl.thickness_mm, "top": sl.top_mm,
                              "bottom": bottom, "floor": floor, "floor_found": bool(below), "su": f.spacing.su,
                              "sv": f.spacing.sv, "posts": [r2(p_) for p_ in f.posts],
                              "obiki": [[round(a_, 1), round(b_, 1), round(v_, 1)] for a_, b_, v_ in f.obiki],
                              "neda_n": len(f.neda), "neda": [[round(a_, 1), round(b_, 1), round(x_, 1)] for a_, b_, x_ in f.neda],
                              "negarami": NEGARAMI_Z_MM,
                              "braces": [[round(x_, 1) for x_ in b_] for b_ in f.braces], "brace_info": f.brace_info,
                              "sills": [[round(a_, 1), round(b_, 1), round(v_, 1)] for a_, b_, v_ in f.sills()],
                              "ties": f.ties, "post_h": f.post_h, "post_kn": f.spacing.post_kn, "q": f.q, "lines": f.lines(),
                              "ps_allow": f.spacing.allow_kn, "guid": sguid})
        if systems is not None:
            plan["slabs"][-1] = merge_system(plan["slabs"][-1], systems)
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    sys_path.write_text(json.dumps(sysrec, ensure_ascii=False, indent=1), encoding="utf-8")
    plan["rows"] = [list(r_) for r_ in rows]
    plan["project"] = str(spec.get("project_name") or spec.get("name") or "")
    (R.OUT_DIR / "型枠_計画.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
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
