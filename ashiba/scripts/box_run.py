"""足場の箱（超簡易モード）: パレットのボタン「箱を置く」「箱を足場に」.

利用者の指定（2026-10-30）「超簡易モードになってない いきなり足場が現れた」「なんか違う 箱を作って自分で伸び縮みするような
感じ」→ 一周の箱（四角）・ボタンで本体にする。

箱を置く（--place）: 平面で、箱の角にしたい所から長手の向きに線を1本引いて選んで押す（線の始点＝内側の建地の列の角、線の長さ＝
  長手の初めの長さ。短手はスパン3つ）。四角い足場の箱（部品 ashiba_box。厚みのある壁の形）が出るので、右の辺・上の辺の中ほどの
  つまみで伸び縮み（定尺に吸着）、下の辺の左寄りのつまみで厚み（300＝一側足場・600／900／1200＝幅の違う本足場）、3D の天端の
  つまみで作業床の段数を決める。
箱を足場に（--build）: 箱を選んで押すと、そのスパンと段数で足場一式（階段・壁つなぎ・シート・数量・帳票）に置き直し、箱を消す。
  セットバック（利用者の指定 2026-10-30: 高さも変えてセットバックにも対応）: 上の階の箱は立つ高さ（zBase。3D の右上の
  出隅のつまみ）を下の屋根の天端に上げて重ね、まとめて選んで押す。下の箱から順に、その高さから建つ足場を置く。

実機の確認（窓なし）: python3 scripts/box_run.py --place --at x,y [--len 9145] [--depth 5487] [--levels 4] [--thick 900]
                       [--zbase 6000] [--series albatross]
                     python3 scripts/box_run.py --build [--name 検証_箱]（選んだ箱を足場に）
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

    from ashiba.box import (BOX_OBJECT, DEFAULT_LEVELS, box_coins, box_loop, box_params, snap_spans, snap_thickness,
                            thickness_conditions)
    from ashiba.manual import axis_direction, eaves_for_levels, solve_manual_loop
    from ashiba.master import load_master, series_module
    from ashiba.pens import gdl_pens, parse_pens

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    guides = []
    if "--at" in argv:
        x0, y0 = (float(t) for t in opt("--at").split(","))
        a, ang, length = (x0, y0), 0.0, float(opt("--len", "7316"))
    else:
        guides = selected_guides(c)
        segs = [s for _e, ss in guides for s in ss]
        if len(segs) != 1:
            print("箱を置く: 平面で、箱の角にしたい所から長手の向きに線を1本（縦か横）引いて選んでから押してください"
                  "（線の始点が内側の建地の列の角、線の長さが長手の初めの長さ）" + not_in_plan_hint(c))
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
    (el,) = c.create_objects([(R.versioned_part_name(BOX_OBJECT), a[0], a[1])])
    spec = {**R.SPEC, **R.load_spec_override()}
    c.set_gdl_parameters(el, box_params(sx, sy, coins, thick, len(lv), lv[0], floor, sid, 300.0,
                                        gdl_pens(parse_pens(spec.get("pens")), BOX_OBJECT),
                                        base_mm=float(opt("--zbase", "0") or 0)))
    if abs(ang) > 1e-6:
        c.rotate_element(el, ang, a[0], a[1])
    if guides:
        delete_guides(c, guides)
    print(f"箱を置く: {sum(sx)}×{sum(sy)}（長手 {'+'.join(map(str, sx))}／短手 {'+'.join(map(str, sy))}）・作業床 {len(lv)}段を"
          "置きました。右の辺・上の辺の中ほどのつまみで伸び縮み（定尺に吸着）、3D の天端のつまみで段数。決まったら箱を選んで"
          "「箱を足場に」")
    print(f"BOX {el['elementId']['guid']}")
    return 0


def build(c, argv) -> int:
    import run_from_archicad as R

    from ashiba.box import BOX_OBJECT, box_loop, contains, parse_box_params, setback_spec, thickness_conditions
    from ashiba.cli import solve_groups
    from ashiba.manual import eaves_for_levels, solve_manual_loop, span_changes, span_text
    from ashiba.master import SERIES_LABELS, series_module

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    sel = c.get_selected_elements()
    boxes = []
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        dd = d.get("details") or {}
        if str((dd.get("libPart") or {}).get("name", "")).startswith(BOX_OBJECT):
            boxes.append((e, dd))
    if not boxes:
        print("箱を足場に: 足場の箱を選んでから押してください（箱は「箱を置く」で置きます。セットバックは立つ高さを上げた箱を"
              "重ねて、まとめて選ぶ）")
        return 1
    # 下の箱から順に置く（セットバックの上の階の箱は下の屋根の上から建つ。立つ高さ zBase）
    jobs = []
    for el, dd in boxes:
        resp = c.tapir("GetGDLParametersOfElements", {"elements": [el]})
        params = {}
        for item in resp.get("gdlParametersOfElements", []):
            for row in item.get("gdlParameters", item.get("parameters", [])):
                params[row.get("name")] = row.get("value")
        try:
            jobs.append((parse_box_params(params), el, dd))
        except ValueError as e:
            print(f"箱を足場に: {e}")
            return 1
    jobs.sort(key=lambda t: t[0]["base_mm"])
    name0 = opt("--name") or str({**R.SPEC, **R.load_spec_override()}.get("project_name") or "足場計画")
    for b, _el, dd in jobs:
        o = dd.get("origin") or {}
        try:
            b["pts"], b["sides"] = box_loop((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0),
                                            float(dd.get("angle") or 0.0), b["sx"], b["sy"])
        except ValueError as e:
            print(f"箱を足場に: {e}")
            return 1
    # セットバック（利用者の指定 2026-10-30: 下の足場と上段をつなげて）: いちばん下の箱の中に立つ高さを上げた箱があれば、
    # 建物の床から解くセットバックと同じ形で一度に解き、上段の端を本体の足場に繋ぐ
    low_b = jobs[0][0]
    ups = [t for t in jobs[1:] if t[0]["base_mm"] > low_b["base_mm"] + 500.0 and contains(low_b["pts"], t[0]["pts"])]
    if ups and low_b["base_mm"] <= 1.0:
        base, sid = _conditions(R, low_b["series_id"])
        kind, cond = thickness_conditions(low_b["thick_mm"], low_b["standoff"])
        dev = {"elevation_mode": "none"} if "--name" in argv else {}
        extra = {**base, **dev, **cond, "series_id": sid, "module": series_module(sid), "project_name": name0}
        try:
            spec = setback_spec(low_b, [t[0] for t in ups], extra)
            groups = solve_groups(spec)
        except Exception as e:
            print(f"箱を足場に: {e}")
            return 1
        print(f"箱を足場に: 下の箱 {sum(low_b['sx'])}×{sum(low_b['sy'])}（{kind}）と上の階の箱 {len(ups)}つを、途中の屋根"
              f"（{min(t[0]['base_mm'] for t in ups):.0f}）から上段を建てて下の足場に繋いで置きます（{SERIES_LABELS.get(sid, sid)}）")
        for lb, g in groups:
            lv = list(g.model.elevation.level_heights)
            print(f"  {lb or '本体'}: {'・'.join(g.model.plan.face_names() if g.model.faces_only is None else [g.model.face_name(i) for i in sorted(g.model.faces_only)])}"
                  + (f"・作業床 {len(lv)}段" if lv else ""))
        if any(t[0]["thick_mm"] != low_b["thick_mm"] for t in ups):
            print("  注意: 上段の足場の幅（厚み）は下の箱と同じにしています（つなぐ足場は同じ幅）")
        print("  注意: 上段のスパンは下の足場の支柱に端を乗せる割付で決めます（上の箱のスパンとは変わることがあります）")
        R.main(outline_mm=spec["outline_mm"], spec_override={k: v for k, v in spec.items() if k != "outline_mm"},
               use_spec_object=False)
        c.delete_elements([low_el for _b, low_el, _dd in [jobs[0]] + ups])
        jobs = [t for t in jobs[1:] if t not in ups]
        if not jobs:
            return 0
    for k, (b, el, dd) in enumerate(jobs):
        try:
            pts, sides = b["pts"], b["sides"]
            base, sid = _conditions(R, b["series_id"])
            kind, cond = thickness_conditions(b["thick_mm"], b["standoff"])
            # 箱が2つ以上なら工事名を分ける（帳票を上書きしない）。立つ高さの違う箱の足場は互いに片付けない
            name = name0 if len(jobs) == 1 else (name0 + ("" if k == 0 else f"_上段{k}"))
            dev = {"elevation_mode": "none"} if "--name" in argv else {}
            extra = {**base, **dev, **cond, "series_id": sid, "module": series_module(sid), "project_name": name,
                     "base_height_mm": b["base_mm"], "_same_base_only": True}
            world, spec, solved = solve_manual_loop(pts, sides, b["standoff"],
                                                    eaves_for_levels(b["levels"], int(b["floor_mm"])), extra)
        except Exception as e:
            print(f"箱を足場に: {e}")
            return 1
        lv = list(solved.model.elevation.level_heights)
        print(f"箱を足場に: {sum(b['sx'])}×{sum(b['sy'])}（長手 {span_text(b['sx'])}／短手 {span_text(b['sy'])}）・"
              f"作業床 {len(lv)}段（最上段 {b['base_mm'] + lv[-1]:.0f}mm）・{kind}"
              + (f"・立つ高さ {b['base_mm']:.0f}" if b["base_mm"] > 0 else "")
              + f"・離れ {b['standoff']:.0f}・{SERIES_LABELS.get(sid, sid)} で置きます（{name}）")
        for ch in span_changes(spec, solved):
            print(f"  スパンの変更: {ch}")
        R.main(outline_mm=world, spec_override={k2: v for k2, v in spec.items() if k2 != "outline_mm"}, use_spec_object=False)
        c.delete_elements([el])
    return 0


def main() -> int:
    argv = sys.argv[1:]
    c = ArchicadClient()
    if "--build" in argv:
        return build(c, argv)
    return place(c, argv)


if __name__ == "__main__":
    sys.exit(main())
