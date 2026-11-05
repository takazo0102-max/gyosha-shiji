"""根切りの山留めまわり（パレットの「切梁上の足場」「山留めの手すり」）.

利用者の指定（2026-10-31）「https://www.seinankizai.jp/product/b_b/136/ 切張り上の足場を追加して 山留め上の手すり リサーチして
追加して」。

  python3 scripts/excav_run.py --kiribari         # 選んだ切梁（梁）の上に切梁上の足場（西南機材 切梁ブラケット）
  python3 scripts/excav_run.py --rail             # 選んだ山留め（壁）か線の上に手すり（親杭の天端・キャッチクランプ）
  python3 scripts/excav_run.py --haraokoshi      # 選んだ山留め（壁）の内側の腹起しの上に外周の足場（西南機材 腹起ブラケット）
  python3 scripts/excav_run.py --haraokoshi --z -1500 --wale 300   # 腹起しの天端の高さ・H形鋼（省くと切梁の天端・幅）
  python3 scripts/excav_run.py --rail --z -300    # 線のときの天端の高さ（階の高さから mm）
  python3 scripts/excav_run.py --remove           # 置いたものを消す

部品 ashiba_yamadome を1本の切梁・1辺の山留めに1つ（src/ashiba/excavation.py が割付・数量・検定）。山留めの手すりは根切りの
反対の側（選んだ山留めの重心から遠い側）を地山として、その縁に柱を立てる。前に同じ要素に置いたものは控え
（ashiba_out/山留め足場.json）で消して置き直す。数量と検定は ashiba_out/山留め足場.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_yamadome"
RECORD = "山留め足場.json"


def _place(c, part: str, at, z: float, ang_deg: float):
    res = c.tapir("CreateObjects", {"objectsData": [{"libraryPartName": part, "coordinates": {
        "x": at[0] / 1000.0, "y": at[1] / 1000.0, "z": z / 1000.0}}]}).get("elements", [])
    if not res or "elementId" not in res[0]:
        return None
    if abs(ang_deg) > 1e-6:
        c.rotate_element(res[0], math.radians(ang_deg), at[0], at[1])
    return res[0]


def _delete_alive(c, guids) -> int:
    alive = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])}
    gone = [{"elementId": {"guid": g}} for g in guids if g in alive]
    if gone:
        c.delete_elements(gone)
    return len(gone)


def rail_lines(walls: list[dict]) -> list[tuple[tuple, tuple, float, str]]:
    """山留めの壁 → 手すりの線 [(始め, 終わり, 天端 z, 名前)]. 地山の側が線の左（部品の +Y）になる向きにそろえる
    （根切りの中＝選んだ壁の重心の側を右に）."""
    if not walls:
        return []
    mids = []
    for w in walls:
        off = (w["lo"] + w["hi"]) / 2.0
        a = (w["ca"][0] + w["n"][0] * off, w["ca"][1] + w["n"][1] * off)
        b = (w["cb"][0] + w["n"][0] * off, w["cb"][1] + w["n"][1] * off)
        mids.append((a, b, w))
    cx = sum((a[0] + b[0]) / 2 for a, b, _w in mids) / len(mids)
    cy = sum((a[1] + b[1]) / 2 for a, b, _w in mids) / len(mids)
    out = []
    for a, b, w in mids:
        side = (b[0] - a[0]) * (cy - a[1]) - (b[1] - a[1]) * (cx - a[0])     # 正なら重心（根切りの中）が左
        if side > 0:
            a, b = b, a
        out.append((a, b, w["z0"] + w["height"], w.get("name") or "山留め"))
    return out


def _seg_dist(p, a, b) -> float:
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay or 1.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - a[0] - ax * t, p[1] - a[1] - ay * t)


def _match(lines, walls) -> list:
    """rail_lines は壁の並びのまま返すので、そのまま対応づける."""
    return list(walls)


def place_walkways(c, rec: dict, part: str, pens: dict, z_opt=None, wale_opt: float = 0.0) -> tuple[list, int]:
    """控え（rec の「切梁:」「腹起し:」）の切梁上の足場と外周の腹起し上の足場を全部置き直す（利用者の指定 2026-10-31: 角の重なりと
    切梁との取り合いも直して）. 外周は perimeter_layout（角の受け持ち・内側の角で手すりを折る・切梁上の足場の幅だけ手すりを切る）、
    切梁上は strut_insets（外周の足場の縁で床を止める）. 戻り値は (計画, 置いた数)."""
    from ashiba.beam_form import beam_from_details
    from ashiba.excavation import (DECK_Z_MM, haraokoshi_plan, kiribari_plan, part_params, perimeter_layout,
                                   strut_insets)
    from ashiba.wall_form import wall_from_details

    # 前の版の控え（切梁の GUID だけのキー）を「切梁:」に
    raw = [k for k in rec if ":" not in k]
    if raw:
        for k, d in zip(raw, c.get_details([{"elementId": {"guid": k}} for k in raw])):
            if d.get("type") == "Beam":
                rec["切梁:" + k] = rec.pop(k)
    from ywall_run import YW_STRUT, struts_for

    import run_from_archicad as R

    kk = [k for k in rec if k.startswith(("切梁:", "腹起し:"))]
    _delete_alive(c, [rec[k] for k in kk if rec[k]])
    beams, walls = [], []
    # 「山留め壁」の切梁（Archicad の梁は無い。控え 山留め壁.json から）
    virt = [k for k in kk if k.startswith(YW_STRUT)]
    if virt:
        have = struts_for(R.OUT_DIR)
        for k in virt:
            if k in have:
                beams.append((k, have[k]))
            else:
                rec.pop(k)                           # 消した・置き直した山留め壁の切梁
    kk = [k for k in kk if not k.startswith(YW_STRUT)]
    dets = c.get_details([{"elementId": {"guid": k.split(":", 1)[1]}} for k in kk]) if kk else []
    for k, d in zip(kk, dets):
        if k.startswith("切梁:"):
            b = beam_from_details(d) if d.get("type") == "Beam" else None
            if b is None:
                rec.pop(k)                           # 消えた切梁
                continue
            beams.append((k, b))
        else:
            w = wall_from_details(d) if d.get("type") == "Wall" else None
            if w is None:
                rec.pop(k)
                continue
            w["guid"] = k
            w["name"] = d.get("id") or ""
            walls.append(w)
    every = c.tapir("GetElementsByType", {"elementType": "Beam"}).get("elements", [])
    struts = [b for b in (beam_from_details(d) for d in (c.get_details(every) if every else [])) if b is not None]
    lines = rail_lines(walls)
    segs = [(p0, p1) for p0, p1, _z, _n in lines]
    thicks = [w["thick"] for w in walls]
    plans, made = [], 0
    # 外周の腹起し上の足場
    around = [b for b in struts if any(min(_seg_dist(b["ca"], q0_, q1_), _seg_dist(b["cb"], q0_, q1_)) < 1500.0 for q0_, q1_ in segs)]
    ends = [pt for _k, b in beams for pt in (b["ca"], b["cb"])]
    wale_z = {}
    for k, (lay, (p0, p1, ztop, nm), w) in enumerate(zip(perimeter_layout(segs, thicks, ends), lines, walls), 1):
        near = [b for b in struts if min(_seg_dist(b["ca"], p0, p1), _seg_dist(b["cb"], p0, p1)) < 1500.0] or around
        z = z_opt if z_opt is not None else (max(b["top"] for b in near) if near else None)
        if z is None:
            print(f"  {nm}: 腹起しの高さが分かりません（近くに切梁が無い）。--z で腹起しの天端を指定してください")
            rec[w["guid"]] = ""
            continue
        wale = wale_opt or (max(b["width"] for b in near) if near else 300.0)
        wale_z[w["guid"]] = z
        p = haraokoshi_plan(f"{nm or '山留め'}{k}", lay["length"], wale, depth_mm=ztop - z)
        p.rail, p.gaps = lay["rail"], lay["gaps"]
        el = _place(c, part, lay["origin"], z, lay["ang"])
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(p, wale), **pens})
        rec[w["guid"]] = el["elementId"]["guid"]
        plans.append(p)
        made += 1
        print(f"  {p.name}: 床 {lay['length']:.0f}・腹起し H{wale:.0f}・天端 {z:.0f} → 腹起ブラケット {len(p.xs)}基"
              + (f"・切梁上の足場との取り合い {len(lay['gaps'])}か所" if lay["gaps"] else ""))
    # 切梁上の足場（外周の足場があれば、その縁で床を止める）
    z_wale = max(wale_z.values()) if wale_z else None
    for k, (key, bm) in enumerate(beams, 1):
        d0, d1 = strut_insets(bm["ca"], bm["cb"], segs, thicks) if walls else (0.0, 0.0)
        step = abs((bm["top"] + DECK_Z_MM) - (z_wale + 73.0)) if (z_wale is not None and (d0 or d1)) else 0.0
        p = kiribari_plan(f"切梁{k}", bm["length"], bm["width"], deck0=d0, deck1=d1, step_mm=step)
        el = _place(c, part, bm["ca"], bm["top"], bm["ang"])
        if el is None:
            print(f"  切梁{k}: 置けませんでした")
            continue
        c.set_gdl_parameters(el, {**part_params(p, bm["width"]), **pens})
        rec[key] = el["elementId"]["guid"]
        plans.append(p)
        made += 1
        bad = [ck for ck in p.checks if ck.status == "NG"]
        print(f"  切梁{k}: 長さ {bm['length']:.0f}・フランジ {bm['width']:.0f}・天端 {bm['top']:.0f} → ブラケット {len(p.xs)}基"
              + (f"・床は外周の足場の縁まで（始め {d0:.0f}・終わり {d1:.0f} 止め・段差 {step:.0f}）" if (d0 or d1) else "")
              + (f"・NG {len(bad)}件（{bad[0].item}）" if bad else ""))
    return plans, made


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.beam_form import beam_from_details
    from ashiba.excavation import haraokoshi_plan, kiribari_plan, part_params, rail_plan, report
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient
    from ashiba.wall_form import wall_from_details

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kiribari", action="store_true", help="選んだ切梁の上に足場")
    ap.add_argument("--rail", action="store_true", help="選んだ山留め（壁）か線の上に手すり")
    ap.add_argument("--haraokoshi", action="store_true", help="選んだ山留め（壁）の腹起しの上に外周の足場")
    ap.add_argument("--wale", type=float, default=0.0, help="腹起しの H形鋼の大きさ（省くと切梁の幅、無ければ 300）")
    ap.add_argument("--z", type=float, default=None, help="線に置くときの天端の高さ・腹起しの天端（mm）")
    ap.add_argument("--remove", action="store_true", help="置いたものを消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, list(rec.values()))
        rec_path.write_text("{}", encoding="utf-8")
        print(f"山留めまわり: 切梁上の足場・山留めの手すり {n}個を消しました")
        return 0
    if not (a.kiribari or a.rail or a.haraokoshi):
        print("山留めまわり: --kiribari（切梁上の足場）・--haraokoshi（外周の腹起し上の足場）・--rail（山留めの手すり）を付けてください")
        return 1
    sel = c.get_selected_elements()
    det = c.get_details(sel) if sel else []
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    plans, made = [], 0
    if a.kiribari:
        beams = [e for e, d in zip(sel, det) if d.get("type") == "Beam" and beam_from_details(d) is not None]
        from ywall_run import struts_for

        yw = struts_for(R.OUT_DIR, [e["elementId"]["guid"] for e in sel]) if sel else {}
        if not beams and not yw:
            print("切梁上の足場: 切梁（梁）か、切梁のある「山留め壁」の部品を選んでから押してください（まっすぐな梁。H形鋼のフランジ幅が梁の幅）")
            return 1
        for e in beams:
            rec.setdefault("切梁:" + e["elementId"]["guid"], "")
        for k in yw:
            rec.setdefault(k, "")
    if a.rail:
        walls = []
        for e, d in zip(sel, det):
            if d.get("type") == "Wall":
                w = wall_from_details(d)
                if w is not None:
                    w["guid"] = e["elementId"]["guid"]
                    w["name"] = d.get("id") or ""
                    walls.append(w)
        lines = rail_lines(walls)
        keys = [w["guid"] for w in walls]
        named = set()                                  # 名前がそのまま使える線（山留め壁の辺「山留め1-1」）
        if not lines:
            # 「山留め壁」で置いた部品を選んだら、その辺の線（左が地山）と天端（GL＋天端）で
            from ywall_run import edges_for

            for a0, b0, z0, nm, g in edges_for(R.OUT_DIR, [e["elementId"]["guid"] for e in sel]):
                lines.append((a0, b0, z0, nm))
                keys.append(g)
                named.add(g)
        if not lines:
            from guide_lines import selected_guides

            guides = selected_guides(c)
            for el_, segs in guides:
                for s_ in segs:
                    lines.append((s_[0], s_[1], a.z or 0.0, "線"))
                    keys.append(el_["elementId"]["guid"] if isinstance(el_, dict) else str(el_))
        if not lines:
            print("山留めの手すり: 山留め（壁）か「山留め壁」の部品か、根切りの縁に引いた線を選んでから押してください")
            return 1
        for k, ((p0, p1, z, nm), key) in enumerate(zip(lines, keys), 1):
            if key in rec:
                _delete_alive(c, [rec.pop(key)])
            L = math.dist(p0, p1)
            if L < 300.0:
                continue
            p = rail_plan(nm if key in named else f"{nm or '山留め'}{k}", L)
            ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            el = _place(c, part, p0, z, ang)
            if el is None:
                continue
            c.set_gdl_parameters(el, {**part_params(p), **pens})
            rec[key] = el["elementId"]["guid"]
            plans.append(p)
            made += 1
            print(f"  {p.name}: 長さ {L:.0f}・天端 {z:.0f} → 手すり柱 {len(p.xs)}本")
    if a.haraokoshi:
        ws = [e for e, d in zip(sel, det) if d.get("type") == "Wall" and wall_from_details(d) is not None]
        if not ws:
            print("外周の足場: 山留め（壁）を選んでから押してください（腹起しの天端は切梁の天端か --z）")
            return 1
        for e in ws:
            rec.setdefault("腹起し:" + e["elementId"]["guid"], "")
    if a.kiribari or a.haraokoshi:
        # 切梁上の足場と外周の足場は取り合う（角の受け持ち・手すりの切れ目・切梁上の床の止め）ので、控えのものを全部置き直す
        got, n_made = place_walkways(c, rec, part, pens, a.z, a.wale)
        plans += got
        made += n_made
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "山留め足場.md"
    md.write_text(report(plans), encoding="utf-8")
    print(f"山留めまわり: {made}個を置きました（数量と検定: {md}）")
    for p in plans:
        for ck in p.checks:
            if ck.status != "OK":
                print(f"  {ck.status} {p.name} {ck.item}: {ck.message}")
                break
    return 0 if all(p.ok for p in plans) else 2


if __name__ == "__main__":
    sys.exit(main())
