"""手動配置（パレットのボタン「手動配置」）: スパンと高さを自分で決めて、線1本の上に足場を置く.

利用者の指定（2026-10-30）「初めにスパンを自分で決める超簡易モードでスパンが決まっているものに合わせやすいような手動モードを
取り入れて スパンと高さ決めたら配置ボタンで足場が配置できるような仕組みを作って」。

平面で、足場の内側の建地の列に線を1本（縦か横。始点が1本目の支柱）引いて選んで押す。窓でスパン（「1829×4, 914」。初期値は
線の長さに近い並び）・高さ（軒高）・離れ・足場の幅・手すり・足場の種類・足場を出す側を入れて「配置」。建物（スラブ）は要らない
（src/ashiba/manual.py が線から仮の躯体の面を作り、その面だけスパン固定で解いて、いつもの配置で置く）。目印の線は消す。

一周: 内側の建地の列を縦横の閉じたポリラインで描いて選ぶと、辺ごとにスパンを入れる窓になる（辺の長さはスパンの合計。向かい合う
辺の合計がそろわなければ止める。入隅で変わったスパンは置いたあとに知らせる）。

実機の確認（窓なし）: python3 scripts/manual_run.py --line x0,y0,x1,y1 --spans "1829x4,914" --height 6000
                       [--standoff 300] [--side left] [--series albatross] [--rail 先行手すり] [--width 900]
                     python3 scripts/manual_run.py --loop "x0,y0;x1,y1;x2,y2;x3,y3" --spans "1829x4,914/1829x3/1829x4,914/1829x3"
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

WIDTHS = {"600（610）": 600, "900（914）": 900, "1200（1219）": 1200}
RAILS = ("布材", "先行手すり")


def _open_points(segs) -> list | None:
    """選んだ線の区間が開いたポリライン（2辺の角・3辺のコの字）ならその点."""
    if len(segs) not in (2, 3) or math.dist(segs[0][0], segs[-1][1]) <= 1.0:
        return None
    if any(math.dist(segs[i][1], segs[i + 1][0]) > 1.0 for i in range(len(segs) - 1)):
        return None
    return [a for a, _b in segs] + [segs[-1][1]]


def _loop_points(segs) -> list | None:
    """選んだ線の区間 → 閉じたポリラインの点（閉じていなければ None）."""
    if len(segs) < 3 or math.dist(segs[0][0], segs[-1][1]) > 1.0:
        return None
    return [a for a, _b in segs]


def _common_fields(R, base, sid0, SERIES_LABELS, last: dict) -> list[dict]:
    """高さ・離れ・幅・手すり・足場の種類（初期値は前回の入力。無ければ条件）."""
    pick = lambda k, opts, d: last[k] if last.get(k) in opts else d
    return [{"key": "height", "label": "高さ（軒高）mm", "kind": "number",
             "value": str(last.get("height") or int(R.SPEC.get("eaves_height_mm", 6000)))},
            {"key": "levels", "label": "作業床の段数（入れると高さより優先）", "kind": "number",
             "value": str(last.get("levels") or "")},
            {"key": "standoff", "label": "離れ mm（躯体から内側の建地まで）", "kind": "number",
             "value": str(last.get("standoff") or "300")},
            {"key": "width", "label": "足場の幅", "kind": "choice", "options": list(WIDTHS),
             "value": pick("width", list(WIDTHS), "900（914）")},
            {"key": "rail", "label": "手すり", "kind": "choice", "options": list(RAILS),
             "value": pick("rail", RAILS, str(base.get("guard_rail_type") or RAILS[0]))},
            {"key": "series", "label": "足場の種類", "kind": "choice", "options": list(SERIES_LABELS.values()),
             "value": pick("series", list(SERIES_LABELS.values()), SERIES_LABELS.get(sid0, sid0))}]


def _keep(vals: dict, is_loop: bool, n_sides: int) -> dict:
    """窓の入力 → 次の窓の初期値（前回の入力）."""
    keep = {k: vals.get(k) for k in ("height", "levels", "standoff", "width", "rail", "series", "side") if vals.get(k)}
    if is_loop:
        keep["sides"] = [str(vals.get(f"s{i}") or "") for i in range(n_sides)]
    else:
        keep["spans"] = str(vals.get("spans") or "")
    return keep


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.cli import resolve_series_id
    from ashiba.elevation_sections import activate_floor_plan
    from ashiba.manual import (LAST_FILE, SIDE_LEFT, SIDE_RIGHT, SIDES, axis_direction, close_open_path,
                               default_spans, eaves_for_levels, general_conditions, line_xform, place_preview,
                               preview_drawing,
                               load_last, loop_directions, parse_spans, save_last, solve_manual, solve_manual_loop,
                               span_changes, span_text, suggest_spans)
    from guide_lines import OUT_DIR
    from ashiba.master import SERIES_LABELS, load_master, series_from_label, series_module

    argv = sys.argv[1:]
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    c = ArchicadClient()
    if "--line" in argv:
        x0, y0, x1, y1 = (float(t) for t in opt("--line").split(","))
        guides, segs = [], [((x0, y0), (x1, y1))]
    elif "--loop" in argv:
        pts = [tuple(float(v) for v in t.split(",")) for t in opt("--loop").split(";")]
        guides, segs = [], [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    elif "--path" in argv:
        pts = [tuple(float(v) for v in t.split(",")) for t in opt("--path").split(";")]
        guides, segs = [], [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    else:
        guides = selected_guides(c)
        segs = [s for _e, ss in guides for s in ss]
    loop = _loop_points(segs)
    opened = None if loop is not None else _open_points(segs)
    if opened is not None:
        loop = opened                                      # 開いたポリライン（角・コの字）も辺ごとのスパンで窓を出す
    if len(segs) != 1 and loop is None:
        print("手動配置: 平面で、足場の内側の建地の列に線を1本（縦か横。始点が1本目の支柱）か、2〜3辺の開いたポリライン"
              "（角・コの字）か、一周を縦横の閉じたポリラインで引いて選んでから押してください" + not_in_plan_hint(c))
        return 1
    base = general_conditions(R.load_spec_override())
    sid0 = resolve_series_id({**R.SPEC, **base})
    coins = load_master(sid0).span_lengths()
    headless = "--line" in argv or "--loop" in argv or "--path" in argv
    # 前回の入力を窓の初期値に（スパンを少し変えて置き直すことが多い）。窓なしの確認では読まず書かない
    last = {} if headless else load_last(OUT_DIR / LAST_FILE)
    if loop is not None:
        n_sides = len(loop) - 1 if opened is not None else len(loop)
        try:
            dirs = ([axis_direction(loop[i], loop[i + 1]) for i in range(n_sides)] if opened is not None
                    else loop_directions(loop))
        except ValueError as e:
            print(f"手動配置: {e}")
            return 1
        arrow = {(1.0, 0.0): "→", (-1.0, 0.0): "←", (0.0, 1.0): "↑", (0.0, -1.0): "↓"}
        lens = [math.dist(loop[i], loop[(i + 1) % len(loop)]) for i in range(n_sides)]
    while True:
        if loop is not None:
            if headless:
                side_txt = opt("--spans", "").split("/")
                vals = {f"s{i}": (side_txt[i] if i < len(side_txt) else "") for i in range(n_sides)}
            else:
                res = show_form({"title": "手動配置（" + ("角・コの字" if opened is not None else "一周") + "・スパンを決めて置く）",
                                 "intro": ("描いた2〜3辺だけに足場を置きます（向かい合う辺を同じスパンで仮に足して解く）。"
                                           if opened is not None else "") +
                                 "内側の建地の列を一周する閉じたポリライン。辺ごとにスパンを入れます（辺の長さはスパンの合計で決まり、描いた"
                                 "長さは目安。向かい合う辺の合計をそろえてください）。入隅は2つの面を 610 などの升目でつなぐので、そこだけ"
                                 "スパンが変わることがあります（置いたあとに知らせます）。",
                                 "fields": [{"key": f"s{i}", "label": f"辺{i + 1} {arrow.get(d, '')}（描いた長さ {lens[i]:.0f}）",
                                             "kind": "text",
                                             "value": default_spans(lens[i], coins, (last.get("sides") or [""] * len(dirs))[i]
                                                                    if len(last.get("sides") or []) == len(dirs) else "")}
                                            for i, d in enumerate(dirs)] + _common_fields(R, base, sid0, SERIES_LABELS, last),
                                 "buttons": [{"id": "place", "label": "配置"}, {"id": "cancel", "label": "やめる"}]})
                if not res or res.get("button") != "place":
                    print("手動配置: やめました（何も置いていません）")
                    return 0
                vals = res.get("values") or {}
        elif headless:
            vals = {"spans": opt("--spans", ""), "side": SIDE_LEFT if opt("--side", "right") == "left" else SIDE_RIGHT}
        else:
            (a, b), = segs
            length = math.dist(a, b)
            res = show_form({"title": "手動配置（スパンを決めて置く）", "intro":
                             f"線の長さ {length:.0f}mm（内側の建地の列。始点が1本目の支柱）。スパンを並べて入れ、高さを決めて「配置」を"
                             "押すと、その線の上に足場を置きます（建物を選ばなくてよい）。スパンは「1829×4, 914」のように入れます。",
                             "fields": [{"key": "spans", "label": "スパン（始点から）", "kind": "text",
                                         "value": default_spans(length, coins, str(last.get("spans") or ""))}]
                             + _common_fields(R, base, sid0, SERIES_LABELS, last)
                             + [{"key": "side", "label": "足場を出す側", "kind": "choice", "options": list(SIDES),
                                 "value": last.get("side") if last.get("side") in SIDES else SIDE_RIGHT}],
                             "buttons": [{"id": "place", "label": "配置"}, {"id": "cancel", "label": "やめる"}]})
            if not res or res.get("button") != "place":
                print("手動配置: やめました（何も置いていません）")
                return 0
            vals = res.get("values") or {}
        if headless:
            vals.update({"height": opt("--height", "6000"), "levels": opt("--levels", ""), "standoff": opt("--standoff", "300"),
                         "width": next((k for k, v in WIDTHS.items() if str(v) == str(opt("--width", "900"))), "900（914）"),
                         "rail": opt("--rail", RAILS[0]), "series": SERIES_LABELS.get(opt("--series", sid0), sid0)})
        sid = series_from_label(vals.get("series") or sid0)
        try:
            height = float(str(vals.get("height") or "6000").replace(",", ""))
            lv_txt = str(vals.get("levels") or "").strip()
            if lv_txt:
                # 段数を入れたら、その段数ちょうどになる高さで解く（高さ 6000 で最上段 7180＝4段になるのを避ける）
                height = eaves_for_levels(int(float(lv_txt)), int(load_master(sid).floor_height or 1800))
            standoff = float(str(vals.get("standoff") or "300").replace(",", ""))
            # 窓なし（実機の確認）は利用者の建物と工事名を分け、立面・断面は作らない（ashiba-live-test-cautions）
            dev = {"project_name": opt("--name", "検証_手動配置"), "elevation_mode": "none"} if headless else {}
            extra = {**base, **dev, "series_id": sid, "module": series_module(sid),
                     "guard_rail_type": str(vals.get("rail") or RAILS[0]),
                     "scaffold_width_mm": WIDTHS.get(str(vals.get("width") or ""), 900)}
            if loop is not None:
                sides = [parse_spans(vals.get(f"s{i}") or "") for i in range(n_sides)]
                if opened is not None:
                    lp, all_sides, keep_sides = close_open_path(loop, sides)
                    world, spec, solved = solve_manual_loop(lp, all_sides, standoff, height, extra, keep_sides=keep_sides)
                    what = f"{'角' if n_sides == 2 else 'コの字'} {n_sides}辺（" + "／".join(span_text(sp) for sp in sides) + "）"
                else:
                    world, spec, solved = solve_manual_loop(loop, sides, standoff, height, extra)
                    what = f"一周 {len(sides)}辺（" + "／".join(span_text(sp) for sp in sides) + "）"
            else:
                (a, b), = segs
                spans = parse_spans(vals.get("spans") or span_text(suggest_spans(math.dist(a, b), coins)))
                world, spec, solved = solve_manual(a, b, spans, standoff, str(vals.get("side") or SIDE_RIGHT), height, extra)
                what = f"スパン {span_text(spans)}（{len(spans)}スパン・{sum(spans)}mm）"
        except Exception as e:                       # 入力の誤り（スパン・斜めの線・閉じない一周・解けない条件）は理由を出して止める
            print(f"手動配置: {e}")
            if headless:
                return 1
            res = show_form({"title": "手動配置（入力の確認）", "intro": f"置けません: {e}", "fields": [],
                             "buttons": [{"id": "fix", "label": "入力を直す"}, {"id": "cancel", "label": "やめる"}]})
            if not res or res.get("button") != "fix":
                return 1
            last = _keep(vals, loop is not None, n_sides if loop is not None else 0)
            continue
        if headless and "--preview" not in argv:
            break
        # 割付の下見（利用者の指定 2026-10-30: 超簡易モードは割付を見てから配置）: 平面に内外の建地の列・支柱の位置・スパンを
        # 出し、確認の窓で「配置」を押したら下見を消して足場を置く
        lv = list(solved.model.elevation.level_heights)
        lines = [f"{what}・離れ {standoff:.0f}・{SERIES_LABELS.get(sid, sid)}",
                 f"作業床 {len(lv)}段（1段目 {lv[0]:.0f}・最上段 {lv[-1]:.0f}mm）" if lv else ""]
        activate_floor_plan(c)
        xf = None if loop is not None else line_xform(solved, spec, a, b, str(vals.get("side") or SIDE_RIGHT))
        shown = place_preview(c, preview_drawing(solved, "割付の下見: " + "・".join(x for x in lines[:2] if x), xf))
        if loop is not None:
            lines += [f"スパンの変更: {ch}" for ch in span_changes(spec, solved)]
        if headless:
            print("  割付の下見: " + " / ".join(x for x in lines if x) + f"（線・文字 {len(shown)}個）")
            if "--keep-preview" not in argv:
                c.delete_elements(shown)
            return 0
        res = show_form({"title": "手動配置（割付の確認）",
                         "intro": "平面に割付（内外の建地の列・支柱の位置・スパン）を出しました。よければ「配置」で足場を置きます。\n"
                                  + "\n".join(x for x in lines if x),
                         "fields": [],
                         "buttons": [{"id": "place", "label": "配置"}, {"id": "fix", "label": "スパンを直す"},
                                     {"id": "cancel", "label": "やめる"}]})
        try:
            c.delete_elements(shown)
        except Exception:
            pass
        button = (res or {}).get("button")
        if button == "place":
            break
        if button != "fix":
            print("手動配置: やめました（何も置いていません）")
            return 0
        last = _keep(vals, loop is not None, n_sides if loop is not None else 0)
    print(f"手動配置: {what}・高さ {height:.0f}・離れ {standoff:.0f}・{SERIES_LABELS.get(sid, sid)} で置きます")
    if not headless:
        save_last(OUT_DIR / LAST_FILE, _keep(vals, loop is not None, n_sides if loop is not None else 0))
    lv = list(solved.model.elevation.level_heights)
    if lv:
        print(f"  作業床 {len(lv)}段（最上段 {lv[-1]:.0f}mm・1段目 {lv[0]:.0f}mm）")
    if loop is not None:
        for ch in span_changes(spec, solved):
            print(f"  スパンの変更: {ch}")
    override = {k: v for k, v in spec.items() if k != "outline_mm"}
    R.main(outline_mm=world, spec_override=override, use_spec_object=False)
    if guides:
        delete_guides(c, guides)
    return 0


if __name__ == "__main__":
    sys.exit(main())
