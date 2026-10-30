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
                     python3 scripts/box_run.py --build [--name 検証_箱]（選んだ箱・辺を足場に）
"""

from __future__ import annotations

import math
import sys
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

    from ashiba.box import (BOX_OBJECT, DEFAULT_LEVELS, SIDE_OBJECT, box_coins, box_loop, box_params, box_sides,
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
    coins = box_coins(master.span_lengths())
    sx = snap_spans(length, coins)
    sy = snap_spans(float(opt("--depth", "0") or 0) or 3 * coins[0], coins)
    levels = int(opt("--levels", DEFAULT_LEVELS))
    # 厚み（足場の種類）の初めは条件の足場の幅。段の高さはその系列で同じ大きさの一周を解いて決める（1段目 1.8m 前後・層の高さ）
    thick = snap_thickness(float(opt("--thick", base.get("scaffold_width_mm") or 900)))
    _kind, cond = thickness_conditions(thick, 300.0)
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
              "4辺別々に置きました。辺ごとに、終わりの端のつまみで長さ（定尺に吸着）、中ほどのつまみで厚み（300＝一側足場・"
              "600／900／1200＝本足場の幅）、3D の天端のつまみで段数。要らない辺は消す（コの字・L字・1本）。伸ばしたら隣の辺を"
              "動かして角に合わせ、決まったら辺をまとめて選んで「箱を足場に」")
    for el in made:
        print(f"BOX {el['elementId']['guid']}")
    return 0


def _levels(R, master, sid: str, base: dict, coins: list[int], thick: int, levels: int) -> tuple[list[float], float]:
    """作業床の段の高さ（その系列で同じ段数の一周を解いて、1段目 1.8m 前後・層の高さ）と層の高さ."""
    from ashiba.box import box_loop, thickness_conditions
    from ashiba.manual import eaves_for_levels, solve_manual_loop
    from ashiba.master import series_module

    _kind, cond = thickness_conditions(thick, 300.0)
    extra = {**base, **cond, "series_id": sid, "module": series_module(sid)}
    pts, sides = box_loop((0.0, 0.0), 0.0, [coins[0]] * 3, [coins[0]] * 3)
    _w, _spec, solved = solve_manual_loop(pts, sides, 300.0, eaves_for_levels(levels, int(master.floor_height or 1800)), extra)
    lv = list(solved.model.elevation.level_heights) or [1800.0]
    return lv, (float(lv[1] - lv[0]) if len(lv) > 1 else float(master.floor_height or 1800))


def place_on_lines(c, argv, guides) -> int:
    """選んだ線・ポリラインの範囲だけに足場の辺を置く（利用者の指定 2026-10-31: 線引っ張った範囲だけに配置するようにして
    今一線だけで四角につくられてしまう）. 線1本は1辺、ポリラインは折れ目ごとに1辺. 長さは線を超えない定尺の組み合わせ."""
    import run_from_archicad as R

    from ashiba.box import (DEFAULT_LEVELS, SIDE_OBJECT, box_coins, orient_path, side_params, sides_from_path,
                            snap_thickness)
    from ashiba.master import load_master
    from ashiba.pens import gdl_pens, parse_pens

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    base, sid = _conditions(R, opt("--series", ""))
    master = load_master(sid)
    coins = box_coins(master.span_lengths())
    levels = int(opt("--levels", DEFAULT_LEVELS))
    thick = snap_thickness(float(opt("--thick", base.get("scaffold_width_mm") or 900)))
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
    lv, floor = _levels(R, master, sid, base, coins, thick, levels)
    R.ensure_parts(c)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), SIDE_OBJECT)
    made = []
    for osegs, how, sides in plan:
        els = c.create_objects([(R.versioned_part_name(SIDE_OBJECT), p[0], p[1]) for p, _g, _s, _ce in sides])
        for el, (p, g, sp, ce) in zip(els, sides):
            c.set_gdl_parameters(el, side_params(sp, coins, thick, len(lv), lv[0], floor, sid, 300.0, pens, base_mm=zb,
                                                 corner_end=ce))
            if abs(g) > 1e-6:
                c.rotate_element(el, g, p[0], p[1])
        made += els
        got = "・".join(f"{sum(sp)}（線 {math.dist(a, b):.0f}）" for (a, b), (_p, _g, sp, _ce) in zip(osegs, sides))
        print(f"箱を置く: 辺 {len(sides)}本 {got}・作業床 {len(lv)}段を {how}に置きました")
    delete_guides(c, guides)
    print("  長さは線を超えない定尺の組み合わせ。辺ごとに、終わりの端のつまみで長さ（定尺に吸着）、中ほどのつまみで厚み"
          "（300＝一側足場・600／900／1200＝本足場の幅）、3D の天端のつまみで段数。決まったら辺をまとめて選んで「箱を足場に」")
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


def _read_items(c) -> list[dict]:
    """選んだ箱（ashiba_box）と辺（ashiba_side）→ 解く単位. 辺は端どうしのつながりで組にする（一周・コの字・L字・1本）.
    各単位は {"pts", "sides", "levels", "thick_mm", "base_mm", "standoff", "floor_mm", "series_id", "els", "desc",
    "loop"（一周で辺ごとの違いが無い＝セットバックの箱として扱える）, "side_job"（辺の組。箱なら None）}."""
    from ashiba.box import (BOX_OBJECT, SIDE_OBJECT, box_loop, chain_sides, parse_box_params, parse_side_params,
                            plan_side_chain, side_axis)
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
    for ch, closed in chain_sides(sides):
        job = plan_side_chain(sides, ch, closed)
        m = job["main"]
        same = all(sides[i]["thick_mm"] == m["thick_mm"] and sides[i]["levels"] == m["levels"] for i in ch)
        shape = {"loop": "一周", "open": "コの字" if len(job["group_sides"]) == 3 else "L字", "line": "1本"}[job["kind"]]
        items.append({**{k: m[k] for k in ("levels", "thick_mm", "base_mm", "standoff", "floor_mm", "series_id")},
                      "pts": job["pts"], "sides": job["sides"], "els": [side_els[i] for i in ch],
                      "loop": job["kind"] == "loop" and same, "side_job": (job, sides),
                      "desc": f"辺 {len(ch)}本の{shape}（{'・'.join(span_text(sp) for sp in job['sides'][:len(job['group_sides'])])}）"})
    return items


def build(c, argv) -> int:
    import run_from_archicad as R

    from ashiba.box import contains, setback_spec, solve_side_job, thickness_conditions
    from ashiba.cli import solve_groups
    from ashiba.manual import eaves_for_levels, solve_manual_loop, span_changes
    from ashiba.master import SERIES_LABELS, series_module

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    try:
        jobs = _read_items(c)
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
        kind, cond = thickness_conditions(low_b["thick_mm"], low_b["standoff"])
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
    for k, b in enumerate(jobs):
        try:
            base, sid = _conditions(R, b["series_id"])
            kind, cond = thickness_conditions(b["thick_mm"], b["standoff"])
            # 2つ以上なら工事名を分ける（帳票を上書きしない）。立つ高さの違う箱の足場は互いに片付けない
            name = name0 if len(jobs) == 1 or k == 0 else (
                name0 + (f"_上段{k}" if b["base_mm"] > jobs[0]["base_mm"] + 1.0 else f"_{k + 1}"))
            extra = {**base, **dev, **cond, "series_id": sid, "module": series_module(sid), "project_name": name,
                     "base_height_mm": b["base_mm"], "_same_base_only": True}
            if b["side_job"] is not None:
                job, sides = b["side_job"]
                world, spec, groups = solve_side_job(job, sides, extra)
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
              + f"・離れ {b['standoff']:.0f}・{SERIES_LABELS.get(sid, sid)} で置きます（{name}）")
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
        R.main(outline_mm=world, spec_override={k2: v for k2, v in spec.items() if k2 != "outline_mm"}, use_spec_object=False)
        c.delete_elements(b["els"])
    return 0


def main() -> int:
    argv = sys.argv[1:]
    c = ArchicadClient()
    if "--build" in argv:
        return build(c, argv)
    return place(c, argv)


if __name__ == "__main__":
    sys.exit(main())
