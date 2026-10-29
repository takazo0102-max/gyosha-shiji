"""手動配置（パレットのボタン「手動配置」）: スパンと高さを自分で決めて、線1本の上に足場を置く.

利用者の指定（2026-10-30）「初めにスパンを自分で決める超簡易モードでスパンが決まっているものに合わせやすいような手動モードを
取り入れて スパンと高さ決めたら配置ボタンで足場が配置できるような仕組みを作って」。

平面で、足場の内側の建地の列に線を1本（縦か横。始点が1本目の支柱）引いて選んで押す。窓でスパン（「1829×4, 914」。初期値は
線の長さに近い並び）・高さ（軒高）・離れ・足場の幅・手すり・足場の種類・足場を出す側を入れて「配置」。建物（スラブ）は要らない
（src/ashiba/manual.py が線から仮の躯体の面を作り、その面だけスパン固定で解いて、いつもの配置で置く）。目印の線は消す。

実機の確認（窓なし）: python3 scripts/manual_run.py --line x0,y0,x1,y1 --spans "1829x4,914" --height 6000
                       [--standoff 300] [--side left] [--series albatross] [--rail 先行手すり] [--width 900]
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


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.cli import resolve_series_id
    from ashiba.manual import SIDE_LEFT, SIDE_RIGHT, SIDES, parse_spans, solve_manual, span_text, suggest_spans
    from ashiba.master import SERIES_LABELS, load_master, series_from_label, series_module

    argv = sys.argv[1:]
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    c = ArchicadClient()
    if "--line" in argv:
        x0, y0, x1, y1 = (float(t) for t in opt("--line").split(","))
        guides, segs = [], [((x0, y0), (x1, y1))]
    else:
        guides = selected_guides(c)
        segs = [s for _e, ss in guides for s in ss]
    if len(segs) != 1:
        print("手動配置: 平面で、足場の内側の建地の列に線を1本（縦か横。始点が1本目の支柱）引いて選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    (a, b), = segs
    from ashiba.manual import general_conditions

    base = general_conditions(R.load_spec_override())
    sid0 = resolve_series_id({**R.SPEC, **base})
    length = math.dist(a, b)
    if "--line" in argv:
        vals = {"spans": opt("--spans", ""), "height": opt("--height", "6000"), "standoff": opt("--standoff", "300"),
                "width": next((k for k, v in WIDTHS.items() if str(v) == str(opt("--width", "900"))), "900（914）"),
                "rail": opt("--rail", RAILS[0]), "series": SERIES_LABELS.get(opt("--series", sid0), sid0),
                "side": SIDE_LEFT if opt("--side", "right") == "left" else SIDE_RIGHT}
    else:
        coins = load_master(sid0).span_lengths()
        res = show_form({"title": "手動配置（スパンを決めて置く）", "intro":
                         f"線の長さ {length:.0f}mm（内側の建地の列。始点が1本目の支柱）。スパンを並べて入れ、高さを決めて「配置」を"
                         "押すと、その線の上に足場を置きます（建物を選ばなくてよい）。スパンは「1829×4, 914」のように入れます。",
                         "fields": [{"key": "spans", "label": "スパン（始点から）", "kind": "text",
                                     "value": span_text(suggest_spans(length, coins))},
                                    {"key": "height", "label": "高さ（軒高）mm", "kind": "number",
                                     "value": str(int(R.SPEC.get("eaves_height_mm", 6000)))},
                                    {"key": "standoff", "label": "離れ mm（躯体から内側の建地まで）", "kind": "number",
                                     "value": "300"},
                                    {"key": "width", "label": "足場の幅", "kind": "choice", "options": list(WIDTHS),
                                     "value": "900（914）"},
                                    {"key": "rail", "label": "手すり", "kind": "choice", "options": list(RAILS),
                                     "value": str(base.get("guard_rail_type") or RAILS[0])},
                                    {"key": "series", "label": "足場の種類", "kind": "choice",
                                     "options": list(SERIES_LABELS.values()), "value": SERIES_LABELS.get(sid0, sid0)},
                                    {"key": "side", "label": "足場を出す側", "kind": "choice", "options": list(SIDES),
                                     "value": SIDE_RIGHT}],
                         "buttons": [{"id": "place", "label": "配置"}, {"id": "cancel", "label": "やめる"}]})
        if not res or res.get("button") != "place":
            print("手動配置: やめました（何も置いていません）")
            return 0
        vals = res.get("values") or {}
    sid = series_from_label(vals.get("series") or sid0)
    try:
        spans = parse_spans(vals.get("spans") or span_text(suggest_spans(length, load_master(sid).span_lengths())))
        height = float(str(vals.get("height") or "6000").replace(",", ""))
        standoff = float(str(vals.get("standoff") or "300").replace(",", ""))
        # 窓なし（実機の確認）は利用者の建物と工事名を分け、立面・断面は作らない（ashiba-live-test-cautions）
        dev = {"project_name": opt("--name", "検証_手動配置"), "elevation_mode": "none"} if "--line" in argv else {}
        extra = {**base, **dev, "series_id": sid, "module": series_module(sid),
                 "guard_rail_type": str(vals.get("rail") or RAILS[0]),
                 "scaffold_width_mm": WIDTHS.get(str(vals.get("width") or ""), 900)}
        world, spec, local = solve_manual(a, b, spans, standoff, str(vals.get("side") or SIDE_RIGHT), height, extra)
    except Exception as e:                       # 入力の誤り（スパン・斜めの線・解けない条件）は理由を出して止める
        print(f"手動配置: {e}")
        return 1
    print(f"手動配置: スパン {span_text(spans)}（{len(spans)}スパン・{sum(spans)}mm）・高さ {height:.0f}・離れ {standoff:.0f}・"
          f"{SERIES_LABELS.get(sid, sid)} で置きます")
    override = {k: v for k, v in spec.items() if k != "outline_mm"}
    R.main(outline_mm=world, spec_override=override, use_spec_object=False)
    if guides:
        delete_guides(c, guides)
    return 0


if __name__ == "__main__":
    sys.exit(main())
