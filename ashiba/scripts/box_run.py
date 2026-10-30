"""足場の箱（超簡易モード）: パレットのボタン「箱を置く」「箱を足場に」.

利用者の指定（2026-10-30）「超簡易モードになってない いきなり足場が現れた」「なんか違う 箱を作って自分で伸び縮みするような
感じ」→ 一周の箱（四角）・ボタンで本体にする。

箱を置く（--place）: 平面で、箱の角にしたい所から長手の向きに線を1本引いて選んで押す（線の始点＝内側の建地の列の角、線の長さ＝
  長手の初めの長さ。短手はスパン3つ）。四角い足場の箱（部品 ashiba_box）が出るので、右の辺・上の辺の中ほどのつまみで伸び縮み
  （定尺に吸着）、3D の天端のつまみで作業床の段数を決める。
箱を足場に（--build）: 箱を選んで押すと、そのスパンと段数で足場一式（階段・壁つなぎ・シート・数量・帳票）に置き直し、箱を消す。

実機の確認（窓なし）: python3 scripts/box_run.py --place --at x,y [--len 9145] [--depth 5487] [--levels 4] [--series albatross]
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

    from ashiba.box import BOX_OBJECT, DEFAULT_LEVELS, box_loop, box_params, snap_spans
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
    coins = sorted(master.span_lengths(), reverse=True)
    sx = snap_spans(length, coins)
    sy = snap_spans(float(opt("--depth", "0") or 0) or 3 * coins[0], coins)
    levels = int(opt("--levels", DEFAULT_LEVELS))
    # 段の高さと足場の幅は、その系列で同じ大きさの一周を解いて決める（1段目 1.8m 前後・層の高さ・建地の間隔）
    extra = {**base, "series_id": sid, "module": series_module(sid)}
    pts, sides = box_loop(a, 0.0, sx, sy)
    _w, _spec, solved = solve_manual_loop(pts, sides, 300.0, eaves_for_levels(levels, int(master.floor_height or 1800)), extra)
    lv = list(solved.model.elevation.level_heights) or [1800.0]
    floor = float(lv[1] - lv[0]) if len(lv) > 1 else float(master.floor_height or 1800)
    row = float(solved.model.post_row_spacing_mm or 914.0)
    R.ensure_parts(c)
    (el,) = c.create_objects([(R.versioned_part_name(BOX_OBJECT), a[0], a[1])])
    spec = {**R.SPEC, **R.load_spec_override()}
    c.set_gdl_parameters(el, box_params(sx, sy, coins, row, len(lv), lv[0], floor, sid, 300.0,
                                        gdl_pens(parse_pens(spec.get("pens")), BOX_OBJECT)))
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

    from ashiba.box import BOX_OBJECT, box_loop, parse_box_params, width_nominal
    from ashiba.manual import eaves_for_levels, solve_manual_loop, span_changes, span_text
    from ashiba.master import SERIES_LABELS, series_module

    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    sel = c.get_selected_elements()
    boxes = []
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        dd = d.get("details") or {}
        if str((dd.get("libPart") or {}).get("name", "")).startswith(BOX_OBJECT):
            boxes.append((e, dd))
    if len(boxes) != 1:
        print("箱を足場に: 足場の箱を1つ選んでから押してください（箱は「箱を置く」で置きます）")
        return 1
    el, dd = boxes[0]
    resp = c.tapir("GetGDLParametersOfElements", {"elements": [el]})
    params = {}
    for item in resp.get("gdlParametersOfElements", []):
        for row in item.get("gdlParameters", item.get("parameters", [])):
            params[row.get("name")] = row.get("value")
    o = dd.get("origin") or {}
    try:
        b = parse_box_params(params)
        pts, sides = box_loop((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0),
                              float(dd.get("angle") or 0.0), b["sx"], b["sy"])
        base, sid = _conditions(R, b["series_id"])
        dev = {"project_name": opt("--name"), "elevation_mode": "none"} if "--name" in argv else {}
        extra = {**base, **dev, "series_id": sid, "module": series_module(sid),
                 "scaffold_width_mm": width_nominal(b["row_mm"])}
        world, spec, solved = solve_manual_loop(pts, sides, b["standoff"], eaves_for_levels(b["levels"], int(b["floor_mm"])),
                                                extra)
    except Exception as e:
        print(f"箱を足場に: {e}")
        return 1
    lv = list(solved.model.elevation.level_heights)
    print(f"箱を足場に: {sum(b['sx'])}×{sum(b['sy'])}（長手 {span_text(b['sx'])}／短手 {span_text(b['sy'])}）・"
          f"作業床 {len(lv)}段（最上段 {lv[-1]:.0f}mm）・離れ {b['standoff']:.0f}・{SERIES_LABELS.get(sid, sid)} で置きます")
    for ch in span_changes(spec, solved):
        print(f"  スパンの変更: {ch}")
    R.main(outline_mm=world, spec_override={k: v for k, v in spec.items() if k != "outline_mm"}, use_spec_object=False)
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
