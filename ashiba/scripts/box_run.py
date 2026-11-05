"""足場の箱（超簡易モード）: パレットのボタン「箱を置く」「箱を足場に」.

利用者の指定（2026-10-30）「超簡易モードになってない いきなり足場が現れた」「なんか違う 箱を作って自分で伸び縮みするような
感じ」→ 一周の箱（四角）・ボタンで本体にする。

箱を置く（--place）: 平面で、足場を置きたい所に線かポリライン（内側の建地の列）を引いて選んで押すと、線の範囲だけに足場の辺を
  置く（利用者の指定 2026-10-31: 線引っ張った範囲だけに配置するようにして 今一線だけで四角につくられてしまう）。線1本は1辺、
  ポリラインは折れ目ごとに1辺、長さは線を超えない定尺の組み合わせ。足場を出す側は、閉じたポリラインなら外回り、開いた線なら
  近くのスラブ（建物）の反対側、建物が無ければ線の右（始点から終点を見て）。
  --whole（前の一周の箱）: 箱の角にしたい所から長手の向きに線を1本引いて選んで押す（線の始点＝内側の建地の列の角、線の長さ＝
  長手の初めの長さ。短手はスパン3つ）。四角い足場の箱（部品 ashiba_box。厚みのある壁の形）が出るので、右の辺・上の辺の中ほどの
  つまみで伸び縮み（定尺に吸着）、下の辺の左寄りのつまみで厚み（300＝一側足場・600／900／1200＝幅の違う本足場）、3D の天端の
  つまみで作業床の段数を決める。
辺ごと（利用者の指定 2026-10-31: 箱は1辺ずつ別々にしてちょ）: 箱は四角の4辺を別々の部品（ashiba_side）で置く。辺ごとに長さ・
  厚み・段数を変えられ、1辺を消せば コの字、2辺を消せば L字、1辺だけなら1本の足場になる（辺は Archicad で動かして角に合わせる。
  終わりと次の始めが 1m 以内ならつながっているとみる）。
  前の一周の箱（ashiba_box）を選んで「箱を置く」を押すと、同じ形の4辺に分ける。
箱を足場に（--build）: 箱（辺）を選んで押すと、そのスパンと段数で足場一式（階段・壁つなぎ・シート・数量・帳票）に置き直し、箱を消す。
  厚みの違う辺の面は面ごとの足場の種類（300＝一側足場（狭い所）・600＝本足場（狭い幅））、段数の違う辺の面は面ごとの高さで解く。
  セットバック（利用者の指定 2026-10-30: 高さも変えてセットバックにも対応）: 上の階の箱は立つ高さ（zBase。3D の右上の
  出隅のつまみ）を下の屋根の天端に上げて重ね、まとめて選んで押す。下の箱から順に、その高さから建つ足場を置く。

実機の確認（窓なし）: python3 scripts/box_run.py --place --at x,y [--len 9145] [--depth 5487] [--levels 4] [--thick 900]
                       [--zbase 6000] [--series albatross]
                     [--whole]（辺に分けず、前の一周の箱 ashiba_box で置く）
                     python3 scripts/box_run.py --place [--thick 150|300 --kind 1|2|3]（選んだ線に辺。--thick 150 は抱き足場。
                       一側の組み方: 1＝ブラケット（支柱）・2＝ブラケット（単管）・3＝抱き足場（厚み 150）。省くと条件の足場の種類から）
                     python3 scripts/box_run.py --build [--name 検証_箱]（選んだ箱・辺を足場に）
"""

from __future__ import annotations

import math
import sys
from typing import Optional
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import delete_guides, not_in_plan_hint, selected_guides  # noqa: E402


def _conditions(R, series: str = ""):
    from ashiba.cli import resolve_series_id
    from ashiba.manual import general_conditions

    base = general_conditions(R.load_spec_override())
    sid = series or resolve_series_id({**R.SPEC, **base})
    return base, sid


def place(c, argv) -> int:
    import run_from_archicad as R

    from ashiba.box import (BOX_OBJECT, DAKI_MM, DEFAULT_LEVELS, SIDE_OBJECT, box_coins, box_loop, box_params, box_sides,
                            side_params, snap_spans, snap_thickness, thickness_conditions)
    from ashiba.manual import axis_direction, eaves_for_levels, solve_manual_loop
    from ashiba.master import load_master, series_module
    from ashiba.pens import gdl_pens, parse_pens

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    guides = []
    if "--at" not in argv:
        # 前の一周の箱を選んで押したら、その箱を4辺に分ける（同じスパン・厚み・段数・立つ高さ）
        sel = c.get_selected_elements()
        boxes = [(e, d.get("details") or {}) for e, d in zip(sel, c.get_details(sel) if sel else [])
                 if str(((d.get("details") or {}).get("libPart") or {}).get("name", "")).startswith(BOX_OBJECT)]
        if boxes:
            return split_boxes(c, boxes)
    if "--at" in argv:
        x0, y0 = (float(t) for t in opt("--at").split(","))
        a, ang, length = (x0, y0), 0.0, float(opt("--len", "7316"))
    else:
        guides = selected_guides(c)
        if not guides:
            print("箱を置く: 平面で、足場を置きたい所に線（縦か横）かポリラインを引いて選んでから押してください（線の範囲だけに"
                  "足場の辺を置きます。線は内側の建地の列。四角に囲むときは閉じたポリライン）" + not_in_plan_hint(c))
            return 1
        if "--whole" not in argv:
            return place_on_lines(c, argv, guides)
        segs = [s for _e, ss in guides for s in ss]
        if len(segs) != 1:
            print("箱を置く: 一周の箱は、箱の角にしたい所から長手の向きに線を1本引いて選んでから押してください")
            return 1
        (a, b), = segs
        try:
            u = axis_direction(a, b)
        except ValueError as e:
            print(f"箱を置く: {e}")
            return 1
        ang, length = math.atan2(u[1], u[0]), math.dist(a, b)
    base, sid = _conditions(R, opt("--series", ""))
    master = load_master(sid)
    levels = int(opt("--levels", DEFAULT_LEVELS))
    # 厚み（足場の種類）の初めは条件の足場の幅。段の高さはその系列で同じ大きさの一周を解いて決める（1段目 1.8m 前後・層の高さ）
    thick = snap_thickness(float(opt("--thick", base.get("scaffold_width_mm") or 900)))
    _kind, cond = thickness_conditions(thick, 300.0)
    # 抱き足場（厚み 150）は単管の定尺で割り付ける（くさびの 1829 は単管の系列に無い）
    coins = box_coins((load_master("tankan") if thick == DAKI_MM else master).span_lengths())
    sx = snap_spans(length, coins)
    sy = snap_spans(float(opt("--depth", "0") or 0) or 3 * coins[0], coins)
    extra = {**base, **cond, "series_id": sid, "module": series_module(sid)}
    pts, sides = box_loop(a, 0.0, sx, sy)
    _w, _spec, solved = solve_manual_loop(pts, sides, 300.0, eaves_for_levels(levels, int(master.floor_height or 1800)), extra)
    lv = list(solved.model.elevation.level_heights) or [1800.0]
    floor = float(lv[1] - lv[0]) if len(lv) > 1 else float(master.floor_height or 1800)
    R.ensure_parts(c)
    spec = {**R.SPEC, **R.load_spec_override()}
    zb = float(opt("--zbase", "0") or 0)
    if "--whole" in argv:
        (el,) = c.create_objects([(R.versioned_part_name(BOX_OBJECT), a[0], a[1])])
        c.set_gdl_parameters(el, box_params(sx, sy, coins, thick, len(lv), lv[0], floor, sid, 300.0,
                                            gdl_pens(parse_pens(spec.get("pens")), BOX_OBJECT), base_mm=zb))
        if abs(ang) > 1e-6:
            c.rotate_element(el, ang, a[0], a[1])
        made = [el]
    else:
        # 4辺を別々の部品で（利用者の指定 2026-10-31: 箱は1辺ずつ別々にしてちょ）。左回りで、各辺が終わりの出隅を受け持つ
        sides = box_sides(a, ang, sx, sy)
        made = c.create_objects([(R.versioned_part_name(SIDE_OBJECT), p[0], p[1]) for p, _g, _s in sides])
        pens = gdl_pens(parse_pens(spec.get("pens")), SIDE_OBJECT)
        for el, (p, g, sp) in zip(made, sides):
            c.set_gdl_parameters(el, side_params(sp, coins, thick, len(lv), lv[0], floor, sid, 300.0, pens, base_mm=zb))
            if abs(g) > 1e-6:
                c.rotate_element(el, g, p[0], p[1])
    if guides:
        delete_guides(c, guides)
    if "--whole" in argv:
        print(f"箱を置く: {sum(sx)}×{sum(sy)}（長手 {'+'.join(map(str, sx))}／短手 {'+'.join(map(str, sy))}）・作業床 {len(lv)}段を"
              "置きました。右の辺・上の辺の中ほどのつまみで伸び縮み（定尺に吸着）、3D の天端のつまみで段数。決まったら箱を選んで"
              "「箱を足場に」")
    else:
        print(f"箱を置く: {sum(sx)}×{sum(sy)}（長手 {'+'.join(map(str, sx))}／短手 {'+'.join(map(str, sy))}）・作業床 {len(lv)}段を"
              "4辺別々に置きました。辺ごとに、終わりの端のつまみで長さ（定尺に吸着）、中ほどのつまみで厚み（150＝抱き足場・"
              "300＝ブラケット足場・600／900／1200＝本足場の幅）、3D の天端のつまみで段数。要らない辺は消す（コの字・L字・1本）。伸ばしたら隣の辺を"
              "動かして角に合わせ、決まったら辺をまとめて選んで「箱を足場に」")
    for el in made:
        print(f"BOX {el['elementId']['guid']}")
    return 0


def _levels(R, master, sid: str, base: dict, coins: list[int], thick: int, levels: int) -> tuple[list[float], float]:
    """作業床の段の高さ（その系列で同じ段数の一周を解いて、1段目 1.8m 前後・層の高さ）と層の高さ."""
    from ashiba.box import box_loop, thickness_conditions
    from ashiba.manual import eaves_for_levels, solve_manual_loop
    from ashiba.master import series_module

    _kind, cond = thickness_conditions(thick, 300.0)          # 段の高さは系列で決まる（一側の組み方によらない）
    extra = {**base, **cond, "series_id": sid, "module": series_module(sid)}
    pts, sides = box_loop((0.0, 0.0), 0.0, [coins[0]] * 3, [coins[0]] * 3)
    _w, _spec, solved = solve_manual_loop(pts, sides, 300.0, eaves_for_levels(levels, int(master.floor_height or 1800)), extra)
    lv = list(solved.model.elevation.level_heights) or [1800.0]
    return lv, (float(lv[1] - lv[0]) if len(lv) > 1 else float(master.floor_height or 1800))


def place_on_lines(c, argv, guides) -> int:
    """選んだ線・ポリラインの範囲だけに足場の辺を置く（利用者の指定 2026-10-31: 線引っ張った範囲だけに配置するようにして
    今一線だけで四角につくられてしまう）. 線1本は1辺、ポリラインは折れ目ごとに1辺. 長さは線を超えない定尺の組み合わせ."""
    import run_from_archicad as R

    from ashiba.box import (DAKI_MM, DEFAULT_LEVELS, ONE_KINDS, SIDE_OBJECT, box_coins, default_one, one_kind_of, orient_path,
                            side_params, sides_from_path, snap_thickness)
    from ashiba.master import load_master
    from ashiba.pens import gdl_pens, parse_pens

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    base, sid = _conditions(R, opt("--series", ""))
    master = load_master(sid)
    box_c = box_coins(master.span_lengths())
    levels = int(opt("--levels", DEFAULT_LEVELS))
    # 厚み・一側の組み方の初めは条件の足場の種類（ブラケット足場なら厚み 300 とその組み方、抱き足場なら 150）
    t0, k0 = default_one(base)
    thick = snap_thickness(float(opt("--thick", t0 or base.get("scaffold_width_mm") or 900)))
    kind = one_kind_of(opt("--kind", k0))
    if thick == DAKI_MM or (thick == 300 and kind == 3):          # 抱き足場は厚み 150（ブラケット足場より狭く）
        thick, kind = DAKI_MM, 3
    # 単管で組む一側（ブラケット（単管）・抱き足場）は単管の定尺で
    coins = box_coins(load_master("tankan").span_lengths()) if thick <= 300 and kind in (2, 3) else box_c
    zb = float(opt("--zbase", "0") or 0)
    pts = [p for _e, ss in guides for s in ss for p in s]
    slabs = [s["polygon_mm"] for s in R.read_slabs_near(c, pts, margin_mm=5000.0)]
    plan = []
    try:
        for _e, segs in guides:
            mx = sum(p[0] for s in segs for p in s) / (2 * len(segs))
            my = sum(p[1] for s in segs for p in s) / (2 * len(segs))
            # 建物: 線のいちばん近くにあるスラブ（重心）
            bld = min(slabs, key=lambda pg: math.hypot(sum(q[0] for q in pg) / len(pg) - mx,
                                                       sum(q[1] for q in pg) / len(pg) - my)) if slabs else None
            osegs, how = orient_path(segs, bld)
            plan.append((osegs, how, sides_from_path(osegs, coins)))
    except ValueError as e:
        print(f"箱を置く: {e}")
        return 1
    lv, floor = _levels(R, master, sid, base, box_c, thick, levels)
    R.ensure_parts(c)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), SIDE_OBJECT)
    made = []
    for osegs, how, sides in plan:
        els = c.create_objects([(R.versioned_part_name(SIDE_OBJECT), p[0], p[1]) for p, _g, _s, _ce in sides])
        for el, (p, g, sp, ce) in zip(els, sides):
            c.set_gdl_parameters(el, side_params(sp, coins, thick, len(lv), lv[0], floor, sid, 300.0, pens, base_mm=zb,
                                                 corner_end=ce, one_kind=kind))
            if abs(g) > 1e-6:
                c.rotate_element(el, g, p[0], p[1])
        made += els
        got = "・".join(f"{sum(sp)}（線 {math.dist(a, b):.0f}）" for (a, b), (_p, _g, sp, _ce) in zip(osegs, sides))
        what = ONE_KINDS[kind][0] if thick <= 300 else f"本足場 幅{thick}"
        print(f"箱を置く: 辺 {len(sides)}本 {got}・{what}・作業床 {len(lv)}段を {how}に置きました")
    delete_guides(c, guides)
    print("  長さは線を超えない定尺の組み合わせ。辺ごとに、終わりの端のつまみで長さ（定尺に吸着）、中ほどのつまみで厚み"
          "（150＝抱き足場・300＝ブラケット足場・600／900／1200＝本足場の幅）、3D の天端のつまみで段数。一側の組み方（ブラケット（支柱）・"
          "ブラケット（単管）・抱き足場）は辺の設定の「一側の組み方」でも選べる（抱き足場を選ぶと厚み 150）。決まったら辺をまとめて選んで「箱を足場に」")
    for el in made:
        print(f"BOX {el['elementId']['guid']}")
    return 0


def split_boxes(c, boxes: list) -> int:
    """一周の箱（ashiba_box）→ 同じ形の4辺（ashiba_side）に置き換える（利用者の指定 2026-10-31: 箱は1辺ずつ別々に）."""
    import run_from_archicad as R

    from ashiba.box import SIDE_OBJECT, box_sides, parse_box_params, side_params
    from ashiba.manual import parse_spans
    from ashiba.pens import gdl_pens, parse_pens

    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), SIDE_OBJECT)
    R.ensure_parts(c)
    for el, dd in boxes:
        prm = _params(c, el)
        try:
            b = parse_box_params(prm)
            o = dd.get("origin") or {}
            sides = box_sides((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0), float(dd.get("angle") or 0.0),
                              b["sx"], b["sy"])
        except ValueError as e:
            print(f"箱を置く: {e}")
            return 1
        coins = parse_spans(str(prm.get("szList") or "")) or sorted(set(b["sx"] + b["sy"]), reverse=True)
        lev1 = float(prm.get("lev1") or 1.78) * 1000.0
        made = c.create_objects([(R.versioned_part_name(SIDE_OBJECT), p[0], p[1]) for p, _g, _s in sides])
        for se, (p, g, sp) in zip(made, sides):
            c.set_gdl_parameters(se, side_params(sp, coins, b["thick_mm"], b["levels"], lev1, b["floor_mm"], b["series_id"],
                                                 b["standoff"], pens, base_mm=b["base_mm"]))
            if abs(g) > 1e-6:
                c.rotate_element(se, g, p[0], p[1])
        c.delete_elements([el])
        print(f"箱を置く: 選んだ箱 {sum(b['sx'])}×{sum(b['sy'])} を4辺別々に分けました（辺ごとに長さ・厚み・段数を変え、要らない辺は"
              "消す。決まったら辺をまとめて選んで「箱を足場に」）")
        for se in made:
            print(f"BOX {se['elementId']['guid']}")
    return 0


def _params(c, el) -> dict:
    resp = c.tapir("GetGDLParametersOfElements", {"elements": [el]})
    out = {}
    for item in resp.get("gdlParametersOfElements", []):
        for row in item.get("gdlParameters", item.get("parameters", [])):
            out[row.get("name")] = row.get("value")
    return out


def _read_items(c, corner_info: Optional[dict] = None) -> list[dict]:
    """選んだ箱（ashiba_box）と辺（ashiba_side）→ 解く単位. 辺は端どうしのつながりで組にする（一周・コの字・L字・1本）.
    各単位は {"pts", "sides", "levels", "thick_mm", "base_mm", "standoff", "floor_mm", "series_id", "els", "desc",
    "loop"（一周で辺ごとの違いが無い＝セットバックの箱として扱える）, "side_job"（辺の組。箱なら None）}.
    corner_info に {"sides", "corners", "notes"} を返す（直角でない角。利用者の指定 2026-10-31: 斜めの角もつながるように）."""
    from ashiba.box import (BOX_OBJECT, DAKI_MM, SIDE_OBJECT, box_coins, box_loop, chain_frame,
                            chain_sides, oblique_corners, parse_box_params, parse_side_params, plan_side_chain, side_axis,
                            to_local, trim_to_lines)
    from ashiba.master import load_master
    from ashiba.manual import span_text

    sel = c.get_selected_elements()
    items, sides, side_els = [], [], []
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        dd = d.get("details") or {}
        name = str((dd.get("libPart") or {}).get("name", ""))
        o = dd.get("origin") or {}
        at = (float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0)
        if name.startswith(BOX_OBJECT):
            b = parse_box_params(_params(c, e))
            b["pts"], b["sides"] = box_loop(at, float(dd.get("angle") or 0.0), b["sx"], b["sy"])
            b.update(els=[e], loop=True, side_job=None,
                     desc=f"{sum(b['sx'])}×{sum(b['sy'])}（長手 {span_text(b['sx'])}／短手 {span_text(b['sy'])}）")
            items.append(b)
        elif name.startswith(SIDE_OBJECT):
            s = parse_side_params(_params(c, e))
            s.update(a=at, dir=side_axis(float(dd.get("angle") or 0.0)))
            sides.append(s)
            side_els.append(e)
    chains = chain_sides(sides)
    # 直角でない角: 入隅は前の辺の帯が後の辺の帯に重ならない長さまで縮める（重なると2本の足場がぶつかる）
    corners = oblique_corners(sides, chains)
    notes = []
    for cn in corners:
        si, sj = sides[cn["i"]], sides[cn["j"]]
        try:
            coins = box_coins(load_master(si.get("series_id") or "albatross").span_lengths())
        except Exception:
            coins = sorted({int(v) for v in si["spans"]}, reverse=True)
        # 前の足場の終わりの支柱は、後の足場の支柱の列の延長線（2本とも）より前へ出さない（利用者の指定 2026-10-31: 支柱の位置を
        # 両方の延長線上より前には行かないようにする／前の足場だけ下げる）
        tr = trim_to_lines(si, sj, coins)
        if tr is not None:
            notes.append(f"斜めの{'出隅' if cn['convex'] else '入隅'}: 前の辺を {sum(si['spans'])} → {sum(tr)} に縮めて、終わりの"
                         "支柱を後の辺の足場の支柱の列の延長線より前へ出さない")
            si["spans"] = tr
    first = {ch[0]: k for k, (ch, closed) in enumerate(chains) if not closed}
    last = {ch[-1]: k for k, (ch, closed) in enumerate(chains) if not closed}
    if corner_info is not None:
        corner_info.update(sides=sides, corners=corners, notes=notes)
    for ch, closed in chains:
        # 斜めの辺の組（利用者の指定 2026-10-31: 斜めの線にも対応）: 組の向きにそろえた座標で縦・横に解き、置いたあと回す
        ang = chain_frame(sides, ch)
        pivot = sides[ch[0]]["a"]
        loc = to_local(sides, ch, ang, pivot) if ang else sides
        job = plan_side_chain(loc, list(range(len(ch))) if ang else ch, closed)
        m = job["main"]
        same = all(sides[i]["thick_mm"] == m["thick_mm"] and sides[i]["levels"] == m["levels"]
                   and sides[i]["one_kind"] == m["one_kind"] for i in ch)
        shape = {"loop": "一周", "open": "コの字" if len(job["group_sides"]) == 3 else "L字", "line": "1本"}[job["kind"]]
        items.append({**{k: m[k] for k in ("levels", "thick_mm", "base_mm", "standoff", "floor_mm", "series_id", "one_kind")},
                      "pts": job["pts"], "sides": job["sides"], "els": [side_els[i] for i in ch],
                      "loop": job["kind"] == "loop" and same and not ang, "side_job": (job, loc),
                      "rot": (ang, pivot) if ang else None, "chain": ch,
                      "join_start": any(cn["j"] == ch[0] for cn in corners) and ch[0] in first,
                      "join_end": any(cn["i"] == ch[-1] for cn in corners) and ch[-1] in last,
                      "desc": f"辺 {len(ch)}本の{shape}（{'・'.join(span_text(sp) for sp in job['sides'][:len(job['group_sides'])])}）"})
    return items


def build(c, argv) -> int:
    import run_from_archicad as R

    from ashiba.box import contains, setback_spec, solve_side_job, thickness_conditions
    from ashiba.cli import solve_groups
    from ashiba.manual import eaves_for_levels, solve_manual_loop, span_changes
    from ashiba.master import SERIES_LABELS, series_module

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    corner_info: dict = {}
    try:
        jobs = _read_items(c, corner_info)
    except ValueError as e:
        print(f"箱を足場に: {e}")
        return 1
    if not jobs:
        print("箱を足場に: 足場の箱（辺）を選んでから押してください（箱は「箱を置く」で置きます。セットバックは立つ高さを"
              "上げた箱を重ねて、まとめて選ぶ）")
        return 1
    # 下の箱から順に置く（セットバックの上の階の箱は下の屋根の上から建つ。立つ高さ zBase）
    jobs.sort(key=lambda b: b["base_mm"])
    name0 = opt("--name") or str({**R.SPEC, **R.load_spec_override()}.get("project_name") or "足場計画")
    dev = {"elevation_mode": "none"} if "--name" in argv else {}
    # セットバック（利用者の指定 2026-10-30: 下の足場と上段をつなげて）: いちばん下の一周の中に立つ高さを上げた一周があれば、
    # 建物の床から解くセットバックと同じ形で一度に解き、上段の端を本体の足場に繋ぐ
    loops = [b for b in jobs if b["loop"]]
    low_b = loops[0] if loops else None
    ups = [b for b in loops[1:] if low_b and b["base_mm"] > low_b["base_mm"] + 500.0 and contains(low_b["pts"], b["pts"])]
    if ups and low_b["base_mm"] <= 1.0:
        base, sid = _conditions(R, low_b["series_id"])
        kind, cond = thickness_conditions(low_b["thick_mm"], low_b["standoff"], low_b.get("one_kind", 1))
        extra = {**base, **dev, **cond, "series_id": sid, "module": series_module(sid), "project_name": name0}
        try:
            spec = setback_spec(low_b, ups, extra)
            groups = solve_groups(spec)
        except Exception as e:
            print(f"箱を足場に: {e}")
            return 1
        print(f"箱を足場に: 下の {low_b['desc']}（{kind}）と上の階の {len(ups)}つを、途中の屋根"
              f"（{min(b['base_mm'] for b in ups):.0f}）から上段を建てて下の足場に繋いで置きます（{SERIES_LABELS.get(sid, sid)}）")
        for lb, g in groups:
            lv = list(g.model.elevation.level_heights)
            print(f"  {lb or '本体'}: {'・'.join(g.model.plan.face_names() if g.model.faces_only is None else [g.model.face_name(i) for i in sorted(g.model.faces_only)])}"
                  + (f"・作業床 {len(lv)}段" if lv else ""))
        if any(b["thick_mm"] != low_b["thick_mm"] for b in ups):
            print("  注意: 上段の足場の幅（厚み）は下の箱と同じにしています（つなぐ足場は同じ幅）")
        print("  注意: 上段のスパンは下の足場の支柱に端を乗せる割付で決めます（上の箱のスパンとは変わることがあります）")
        R.main(outline_mm=spec["outline_mm"], spec_override={k: v for k, v in spec.items() if k != "outline_mm"},
               use_spec_object=False)
        c.delete_elements([e for b in [low_b] + ups for e in b["els"]])
        jobs = [b for b in jobs if b is not low_b and b not in ups]
        if not jobs:
            return 0
    placed: list[str] = []          # この「箱を足場に」で先に置いた要素（後の足場の片付けで消さない）
    for k, b in enumerate(jobs):
        try:
            base, sid = _conditions(R, b["series_id"])
            kind, cond = thickness_conditions(b["thick_mm"], b["standoff"], b.get("one_kind", 1))
            # 2つ以上なら工事名を分ける（帳票を上書きしない）。立つ高さの違う箱の足場は互いに片付けない
            name = name0 if len(jobs) == 1 or k == 0 else (
                name0 + (f"_上段{k}" if b["base_mm"] > jobs[0]["base_mm"] + 1.0 else f"_{k + 1}"))
            extra = {**base, **dev, **cond, "series_id": sid, "module": series_module(sid), "project_name": name,
                     "base_height_mm": b["base_mm"], "_same_base_only": True}
            if b["side_job"] is not None:
                job, sides = b["side_job"]
                world, spec, groups = solve_side_job(job, sides, extra, (b.get("join_start"), b.get("join_end")))
                solved = groups[0][1]
            else:
                world, spec, solved = solve_manual_loop(b["pts"], b["sides"], b["standoff"],
                                                        eaves_for_levels(b["levels"], int(b["floor_mm"])), extra)
                groups = [("", solved)]
        except Exception as e:
            print(f"箱を足場に: {e}")
            return 1
        lv = list(solved.model.elevation.level_heights)
        if len(lv) > b["levels"]:
            lv = lv[:b["levels"]]           # 段数を上げた面のある辺の組: 全体は高い面の段数で解くので、主な辺の段数で書く
        print(f"箱を足場に: {b['desc']}・作業床 {len(lv)}段（最上段 {b['base_mm'] + lv[-1]:.0f}mm）・{kind}"
              + (f"・立つ高さ {b['base_mm']:.0f}" if b["base_mm"] > 0 else "")
              + f"・離れ {b['standoff']:.0f}・{SERIES_LABELS.get(solved.model.master.series_id, sid)} で置きます（{name}）")
        for lb, g in groups[1:]:
            print(f"  {lb}: {'・'.join(g.model.face_name(i) for i in sorted(g.model.faces_only or []))}")
        if spec.get("face_eaves_mm"):
            ms = [g.model for _lb, g in groups]
            fl = [f"{m.face_name(ei)} {(m.face_elevations.get(ei) or m.elevation).n_levels}段"
                  for m in ms for ei in sorted(m.faces_only if m.faces_only is not None else range(len(m.plan.edges)))]
            print(f"  面ごとの段数: {'・'.join(fl)}")
        for note in (b["side_job"][0]["notes"] if b["side_job"] else []):
            print(f"  注意: {note}")
        for ch in span_changes(spec, solved):
            print(f"  スパンの変更: {ch}")
        b["solved"] = solved
        spec = {**spec, "_protect_guids": list(placed)}
        if b.get("rot"):
            print(f"  斜めの辺: {math.degrees(b['rot'][0]):.1f}° 回した向きで縦・横に解き、置いたあと線の向きに回します")
            res = _place_rotated(c, R, world, spec, b["rot"], name)
        else:
            res = R.main(outline_mm=world, spec_override={k2: v for k2, v in spec.items() if k2 != "outline_mm"},
                         use_spec_object=False)
        placed += _placed_guids(res)
        c.delete_elements(b["els"])
    if corner_info.get("corners"):
        place_corner_fills(c, R, jobs, corner_info, name0)
    return 0


CFILL_OBJECT = "ashiba_cfill"


def place_corner_fills(c, R, jobs: list[dict], info: dict, name0: str) -> None:
    """直角でない角に隅のつなぎ（部品 ashiba_cfill）を置き、材料の目安を書く（利用者の指定 2026-10-31: 斜めの角もつながる
    ようにしてちょ 無理な場合はかど合わせてアンチをし単管手すり作成か足場板と単管手すりにするか）."""
    import csv

    from ashiba.box import (DECK_TOP_MM, _cross_line, band, board_quantities, corner_fill, corner_outline, corner_posts, corner_region,
                            corner_supports, extension_board_layout)
    from ashiba.pens import gdl_pens, parse_pens

    sides = info["sides"]
    for n in info.get("notes") or []:
        print(f"  {n}")
    by_end = {b["chain"][-1]: b for b in jobs if b.get("chain")}
    by_start = {b["chain"][0]: b for b in jobs if b.get("chain")}
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), CFILL_OBJECT)
    rows = []
    k = 0
    for cn in info["corners"]:
        bi, bj = by_end.get(cn["i"]), by_start.get(cn["j"])
        if not bi or not bj or "solved" not in bi or "solved" not in bj:
            print(f"  （隅の候補を飛ばしました: 辺 {cn['i']}→{cn['j']}。両側の足場が置けていない）")
            continue
        k += 1
        si, sj = sides[cn["i"]], sides[cn["j"]]
        end_i = _chain_end(bi, sides)
        mi, mj = bi["solved"].model, bj["solved"].model
        # 後の足場の外の列の支柱（入隅の手すりの端を留める）
        wj = float(mj.post_row_spacing_mm)
        nj = (sj["dir"][1], -sj["dir"][0])
        acc, posts_j = 0.0, []
        for sp in [0] + list(sj["spans"]):
            acc += sp
            posts_j.append((sj["a"][0] + nj[0] * wj + sj["dir"][0] * acc, sj["a"][1] + nj[1] * wj + sj["dir"][1] * acc))
        fill = corner_fill(end_i, si["dir"], float(mi.post_row_spacing_mm), sj["a"], sj["dir"], wj, cn["c"], cn["convex"],
                           posts_j=posts_j)
        # アンチの長さ（利用者の指定 2026-10-31: 900アンチを乗せる）: インチの系列は 914、メートルは 900
        anti_l = 914 if 914 in [int(v) for v in mi.master.span_lengths()] else 900
        lv_i, lv_j = list(mi.elevation.level_heights), list(mj.elevation.level_heights)
        lv = lv_i if len(lv_i) <= len(lv_j) else lv_j
        base = float(si["base_mm"])
        cx, cy = cn["c"]
        # 同じ角に前に置いた隅のつなぎは消す
        old = []
        try:
            objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
            for e, d in zip(objs, c.get_details(objs) if objs else []):
                dd = d.get("details") or {}
                o = dd.get("origin") or {}
                if str((dd.get("libPart") or {}).get("name", "")).startswith(CFILL_OBJECT) and \
                        math.hypot(float(o.get("x", 0)) * 1000.0 - cx, float(o.get("y", 0)) * 1000.0 - cy) < 1500.0:
                    old.append(e)
        except Exception:
            pass
        if old:
            c.delete_elements(old)
        # 隅は白のアンチを使わず、支柱どうしを単管で結び、足場板（黄）を本足場のアンチの上に載せて番線で留める（利用者の指定
        # 2026-10-31: 支柱間を単管で結ぶ 白はいらない 黄色の足場板を本足場のアンチ上に乗せて番線で固定する）
        wi = float(mi.post_row_spacing_mm)
        band_i = band(si["a"], si["dir"], float(sum(si["spans"])), wi)
        band_j = band(sj["a"], sj["dir"], float(sum(sj["spans"])), wj)
        # 足場板を置ける範囲は元のすき間の形（手すりの端を近い支柱へ寄せた形で探すと、入隅で1列しか置けなかった）
        region = corner_fill(end_i, si["dir"], wi, sj["a"], sj["dir"], wj, cn["c"], cn["convex"])
        # 足場板は支柱の列の延長ラインに沿って渡す（利用者の指定 2026-10-31: その向きはできないよ ここまで下げないとできないね
        # 支柱の延長ラインで行こうか）。前の足場の列の延長で 400 に足りなければ、後の足場の列の延長も試して多い方
        def used_spans(b, s):
            job = b["side_job"][0] if b.get("side_job") else None
            return list(job["sides"][0]) if job and job["kind"] == "line" else list(s["spans"])
        posts = corner_posts({**si, "spans": used_spans(bi, si)}, {**sj, "spans": used_spans(bj, sj)}, wi, wj)
        # 隅の床は両方の延長線で囲まれた所まで。支柱は立てず、両側の足場の支柱から延長線に沿って出した単管で受ける（利用者の
        # 指定 2026-10-31: 支柱は立てず単管で受ける）
        reg = corner_region(end_i, si["dir"], wi, sj["a"], sj["dir"], wj)
        sups = corner_supports(end_i, si["dir"], wi, sj["a"], sj["dir"], wj, band_i, band_j, reg)
        corner = {"walk": region["walk"], "region": reg, "supports": sups}
        lay = extension_board_layout(corner, band_i, band_j, posts, si["dir"])
        line_of = "前の足場"
        if len(lay["boards"]) * 240 < 400:
            lay_j = extension_board_layout(corner, band_i, band_j, posts, si["dir"], dj=sj["dir"])
            if len(lay_j["boards"]) > len(lay["boards"]):
                lay, line_of = lay_j, "後の足場"
        boards = lay["boards"]
        # 受けの単管は支柱の脇（右へ 支柱半径＋単管半径）を通す（部品は支柱が左にある形でクランプを描く）
        ties = []
        for p0, p1 in lay["ties"]:
            L = math.dist(p0, p1) or 1.0
            r_ = ((p1[1] - p0[1]) / L * 48.6, -(p1[0] - p0[0]) / L * 48.6)
            ties.append(((p0[0] + r_[0], p0[1] + r_[1]), (p1[0] + r_[0], p1[1] + r_[1])))
        # 手すりは外側の列の延長線に沿って後の足場の外側の列の延長線との交点まで（その先は後の足場の外の支柱へ）と、離れていれば
        # 内側の支柱どうしにも（利用者の指定 2026-10-31: 手すりがない）
        poly, rails = corner_outline(region["walk"], si["dir"], sj["dir"])
        fill = {**fill, "poly": poly, "rail": rails}
        (el,) = c.create_objects([(R.versioned_part_name(CFILL_OBJECT), cx, cy)])
        c.set_gdl_parameters(el, {**pens,
                                  "polyX": ",".join(f"{p[0] - cx:.0f}" for p in poly),
                                  "polyY": ",".join(f"{p[1] - cy:.0f}" for p in poly),
                                  "railE": ",".join(str(r) for r in fill["rail"]),
                                  "levList": ",".join(f"{base + h:.0f}" for h in lv),
                                  "deckKind": 2, "antiOn": False, "antiW": lay["w"] / 1000.0, "cName": f"隅のつなぎ{k}",
                                  "deckTop": DECK_TOP_MM / 1000.0, "deckT": 0.0,
                                  "plkX": "", "plkY": "", "plkL": "",
                                  "fbX": ",".join(f"{o[0] - cx:.0f}" for o, _L in boards),
                                  "fbY": ",".join(f"{o[1] - cy:.0f}" for o, _L in boards),
                                  "fbL": ",".join(f"{L:.0f}" for _o, L in boards),
                                  "fbAng": lay["ang"], "pstX": "", "pstY": "",
                                  "supX0": ",".join(f"{s[0][0] - cx:.0f}" for s in ties),
                                  "supY0": ",".join(f"{s[0][1] - cy:.0f}" for s in ties),
                                  "supX1": ",".join(f"{s[1][0] - cx:.0f}" for s in ties),
                                  "supY1": ",".join(f"{s[1][1] - cy:.0f}" for s in ties)})
        turn = math.degrees(math.acos(max(-1.0, min(1.0, si["dir"][0] * sj["dir"][0] + si["dir"][1] * sj["dir"][1]))))
        print(f"  隅のつなぎ{k}: {'出隅' if cn['convex'] else '入隅'}（{turn:.0f}° 曲がる角）に {len(lv)}段、受けの単管 {len(ties)}本を両側の"
              + f"足場の支柱から延長線に沿って出し、足場板 {len(boards)}列（幅 {len(boards) * 240}）を{line_of}の支柱の列の延長ラインに沿って、本足場の"
              "アンチに 200 以上重ね、先は後の足場の床か受けの単管に載せて番線で留め、"
              + (f"（{'・'.join(f'{g:.0f}' for g in lay['gaps'] if g > 0)} は支柱をよけたすき間）" if any(g > 0 for g in lay["gaps"]) else "")
              + "単管の上桟・中桟・幅木・自在クランプを置きました（両側の足場の角の側の妻側の手すりは外す）")
        (_pi, qi_), (_pj, qj_) = region["walk"][3], region["walk"][4]
        xo = _cross_line(qi_, si["dir"], qj_, sj["dir"])
        if xo is not None and (xo[0] - qi_[0]) * si["dir"][0] + (xo[1] - qi_[1]) * si["dir"][1] > 1.0 \
                and (xo[0] - qj_[0]) * sj["dir"][0] + (xo[1] - qj_[1]) * sj["dir"][1] > 1.0:
            print("    注意: 後の足場の始めのスパンの外側の手すりが隅の床を横切ります。そのスパンの外側の手すりは外し、単管の手すりを"
                  "前の足場の外側の延長線との交点から後の足場の次の支柱まで回してください")
        if len(boards) * 240 < 400:
            print("    注意: 足場板が 400 の幅に足りない（作業床は幅 40cm 以上。安衛則563条）。角の形を見直す")
        if len(lv_i) != len(lv_j):
            print(f"    注意: 両側の足場の段数が違う（{len(lv_i)}段・{len(lv_j)}段）ので、少ない方の {len(lv)}段にしました")
        for item, q, note in board_quantities(lay, fill, len(lv)):
            rows.append((f"隅のつなぎ{k}", item, q, note))
            print(f"    {item} {q} — {note}")
    if rows:
        out = R.OUT_DIR / f"{name0}_隅のつなぎ.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["場所", "品名", "数", "注"])
            w.writerows(rows)
        print(f"  隅のつなぎの材料の目安: {out}")


def _chain_end(b: dict, sides: list[dict]) -> tuple[float, float]:
    """辺の組の終わりの内側の列の点（世界座標。解いたスパンの合計で）."""
    job, _loc = b["side_job"]
    ch = b["chain"]
    p = sides[ch[0]]["a"]
    k = len(job["group_sides"])
    gfirst = [g[0] for g in job["group_sides"]]
    # 面ごとの始めの辺（世界座標の向き）。斜めの組は loc の番号が組の中の順
    for g, sp in zip(gfirst[:k], job["sides"][:k]):
        s = sides[ch[g]] if b.get("rot") else sides[g]
        L = float(sum(sp))
        p = (p[0] + s["dir"][0] * L, p[1] + s["dir"][1] * L)
    return p


ROTATED_RECORD = "斜めの足場.json"   # 斜めに回して置いた足場の GUID（工事名ごと。置き直すときに前のものを消す）
ROTATE_TYPES = ("Object", "Label", "Dimension")


def _placed_guids(res) -> list[str]:
    """R.main の戻り（足場ライン・壁つなぎなど・詳細図）→ 置いた要素の GUID."""
    out = []
    for k in ("lines", "attachments", "details", "elevations"):
        for e in (res or {}).get(k) or []:
            if isinstance(e, dict) and "elementId" in e:
                out.append(e["elementId"]["guid"])
    return out


def _guids(c, types=ROTATE_TYPES) -> set:
    out = set()
    for ty in types:
        try:
            out |= {e["elementId"]["guid"] for e in c.tapir("GetElementsByType", {"elementType": ty}).get("elements", [])}
        except Exception:
            pass
    return out


def _place_rotated(c, R, world, spec: dict, rot, name: str):
    """組の向きにそろえた座標の外形で置き（R.main）、新しく置いた平面の要素（足場ライン・壁つなぎ・シート・ラベル）を
    線の向きへ回す（寸法は足場ラインに関連付けてあるのでついてくる）。立面図・詳細図の行（外形から 20m 以上下）は回さない. 回した要素は工事名ごとに控え、置き直すときに消す
    （外形の範囲で前の配置を拾う片付けは、回したあとの位置では拾えないため）."""
    import json

    ang, pivot = rot
    rec_p = R.OUT_DIR / ROTATED_RECORD
    try:
        rec = json.loads(rec_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    old = [g for g in rec.get(name, []) if g in _guids(c)]
    if old:
        c.delete_elements([{"elementId": {"guid": g}} for g in old])
        print(f"  前に斜めに置いた {name} の要素 {len(old)}個を消しました")
    before = _guids(c)
    res = R.main(outline_mm=world, spec_override={k: v for k, v in spec.items() if k != "outline_mm"}, use_spec_object=False)
    skip = {e["elementId"]["guid"] for k in ("details", "elevations") for e in (res or {}).get(k) or [] if isinstance(e, dict)
            and "elementId" in e}
    new = [g for g in _guids(c) - before if g not in skip]
    xs, ys = [p[0] for p in world], [p[1] for p in world]
    x0, x1, y0, y1 = min(xs) - 12000, max(xs) + 12000, min(ys) - 12000, max(ys) + 12000
    els = [{"elementId": {"guid": g}} for g in new]
    keep, rec_only = [], []
    for e, d in zip(els, c.get_details(els) if els else []):
        if d.get("type") == "Dimension":
            # 寸法は足場ラインの点に関連付けてあるので、ラインを回すとついてくる。寸法も回すと二重に回って線の向きから
            # ずれた（実機 2026-10-31: 60° の足場の寸法が 30° の向きに出た）。控えには入れて置き直しで消す
            rec_only.append(e)
            continue
        dd = d.get("details") or {}
        o = dd.get("origin") or dd.get("begCoordinate") or {}
        if o and not (x0 <= float(o.get("x", 0)) * 1000.0 <= x1 and y0 <= float(o.get("y", 0)) * 1000.0 <= y1):
            continue
        keep.append(e)
    ox, oy = pivot[0] / 1000.0, pivot[1] / 1000.0
    for i in range(0, len(keep), 200):
        c.tapir("RotateElements", {"elementsWithRotations": [
            {"elementId": e["elementId"], "rotation": {"origin": {"x": ox, "y": oy}, "beginPoint": {"x": ox + 1.0, "y": oy},
                                                       "endPoint": {"x": ox + math.cos(ang), "y": oy + math.sin(ang)}}}
            for e in keep[i:i + 200]]})
    rec[name] = [e["elementId"]["guid"] for e in keep + rec_only]
    rec_p.parent.mkdir(parents=True, exist_ok=True)
    rec_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  斜めの向きに {len(keep)}個を回しました（立面図・詳細図の行は回さない）")
    return res


def main() -> int:
    argv = sys.argv[1:]
    c = ArchicadClient()
    if "--build" in argv:
        return build(c, argv)
    return place(c, argv)


if __name__ == "__main__":
    sys.exit(main())
