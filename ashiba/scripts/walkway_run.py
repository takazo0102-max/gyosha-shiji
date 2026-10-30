"""仮設通路（日工セック ライトブリッジ）を平面の線1本で置く（パレットのボタン「仮設通路」）.

利用者の指定（2026-10-29）「https://www.nikkosec.co.jp/page-73/ 次足場はこういうのにも対応できるようにしたい」。
平面で、渡す所に線を1本（始め→終わりの向き。島の布材の間）引いて選んで押す。窓で名前・両端の床の高さ・機種を入れて
「置く」と、両端の島（部品 ashiba_stage。始めは階段つき2スパン、終わりは1スパン）と通路（部品 ashiba_walkway）を置き、
検証と数量を ashiba_out/仮設通路_<名前>.md に書く。同じ線の上に前に置いた通路と島は置き換える。目印の線は消す。

実機の確認（窓なし）: python3 scripts/walkway_run.py --line x0,y0,x1,y1 [--deck 1800] [--end 2100] [--name 検証_仮設通路]
片付け: python3 scripts/walkway_run.py --clear（--line で置いた部品を消す。GUID は ashiba_out/仮設通路_検証.json）
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import OUT_DIR, delete_guides, not_in_plan_hint, selected_guides  # noqa: E402
from interior_stage_run import STAGE_OBJECT, room_heights  # noqa: E402

WALKWAY_OBJECT = "ashiba_walkway"
DEV_REC = OUT_DIR / "仮設通路_検証.json"
AUTO = "自動（長さに合ういちばん軽い機種）"


def _on_island(p, st, tol: float = 300.0) -> bool:
    """点 p が島（内部ステージ）の外周の支柱の範囲（tol 広げる）に入るか."""
    d = (p[0] - st.origin[0], p[1] - st.origin[1])
    a = d[0] * st.u[0] + d[1] * st.u[1]
    b = d[0] * st.v[0] + d[1] * st.v[1]
    return -tol <= a <= sum(st.spans_u) + tol and -tol <= b <= sum(st.spans_v) + tol


def _old_parts(c, r) -> list:
    """前に置いた同じ通路（原点が始めの点の 0.5m 以内）と、島の範囲に原点がある内部ステージ."""
    old = []
    try:
        objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        for e, d in zip(objs, c.get_details(objs) if objs else []):
            dd = d.get("details") or {}
            lib = str((dd.get("libPart") or {}).get("name", ""))
            o = dd.get("origin") or {}
            p = (float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0)
            if lib.startswith(WALKWAY_OBJECT) and math.dist(p, r.start) < 500.0:
                old.append(e)
            elif lib.startswith(STAGE_OBJECT) and any(_on_island(p, st) for st in r.islands):
                old.append(e)
    except Exception:
        return []
    return old


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.cli import resolve_series_id
    from ashiba.interior_stage import stage_params
    from ashiba.master import load_master
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.structural import load_capacities
    from ashiba.walkways import load_walkway_models, solve_walkway, walkway_params, walkway_report

    c = ArchicadClient()
    argv = sys.argv[1:]
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    if "--clear" in argv:
        guids = json.loads(DEV_REC.read_text(encoding="utf-8")) if DEV_REC.exists() else []
        if guids:
            c.delete_elements([{"elementId": {"guid": g}} for g in guids])
        DEV_REC.unlink(missing_ok=True)
        print(f"仮設通路: 検証で置いた {len(guids)}個を消しました")
        return 0
    if "--line" in argv:
        x0, y0, x1, y1 = (float(t) for t in opt("--line").split(","))
        guides, segs = [], [((x0, y0), (x1, y1))]
    else:
        guides = selected_guides(c)
        segs = [s for _e, ss in guides for s in ss]
    if len(segs) != 1:
        print("仮設通路: 平面で、渡す所に線を1本（始め→終わりの向き。両端の島の布材の間）引いて選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    (s, e), = segs
    floor, story, _ceil = room_heights(c, [list(s), list(e), list(e), list(s)])
    models = load_walkway_models()
    if "--line" in argv:
        res = {"button": "place", "values": {"name": opt("--name", "検証_仮設通路"), "deck": opt("--deck", "1800"),
                                             "end": opt("--end", ""), "model": AUTO}}
    else:
        res = show_form({"title": "仮設通路（ライトブリッジ）", "intro":
                         f"線の長さ {math.dist(s, e):.0f}mm。両端に島（足場の塔）を立て、その布材に通路のフックを掛けます。"
                         f"始めの島に階段を付けます。床の高さは足場の立つ面（{floor:.0f}）から。",
                         "fields": [{"key": "name", "label": "名前", "kind": "text", "value": "仮設通路"},
                                    {"key": "deck", "label": "始めの床の高さ mm", "kind": "number", "value": "1800"},
                                    {"key": "end", "label": "終わりの床の高さ mm（空は始めと同じ）", "kind": "number", "value": ""},
                                    {"key": "model", "label": "機種", "kind": "choice",
                                     "options": [AUTO] + [m.model for m in models], "value": AUTO}],
                         "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        print("仮設通路: やめました（何も置いていません）")
        return 0
    vals = res.get("values") or {}
    num = lambda k, d: float(str(vals.get(k) or d).replace(",", ""))
    item = {"name": str(vals.get("name") or "仮設通路"), "start_mm": list(s), "end_mm": list(e),
            "deck_mm": num("deck", "1800"), "base_mm": floor - story,
            "model": "" if str(vals.get("model") or AUTO) == AUTO else str(vals.get("model"))}
    if str(vals.get("end") or "").strip():
        item["end_deck_mm"] = num("end", item["deck_mm"])
    spec = {**R.SPEC, **R.load_spec_override()}
    sid = resolve_series_id(spec)
    master = load_master(sid)
    try:
        r = solve_walkway(item, master, load_capacities(sid))
    except ValueError as ex:
        print(f"仮設通路: {ex}")
        return 1
    # 梁をまたぐ所のあき・島の支柱が梁に乗らないか（利用者の指定 2026-10-30: 根切り底と梁を置いてテストして）
    from ashiba.beams import posts_on_beams, read_beams, walkway_beam_checks
    from ashiba.walkways import WalkwayCheck

    beams = read_beams(c, [list(s), list(e)])
    # 島の足元の地盤の高さの差（根切り底の法面にかかる島）
    try:
        from ashiba.beams import ground_spread, ground_spread_message
        from ashiba.tapir_adapter import read_ground_model

        gmod = read_ground_model(c, outline_mm=[list(s), list(e), list(e), list(s)])
        for isl in r.islands:
            cu = [0.0]
            for s_ in isl.spans_u:
                cu.append(cu[-1] + s_)
            cv = [0.0]
            for s_ in isl.spans_v:
                cv.append(cv[-1] + s_)
            pts = [(isl.origin[0] + isl.u[0] * a + isl.v[0] * b, isl.origin[1] + isl.u[1] * a + isl.v[1] * b)
                   for a in cu for b in cv]
            gm = ground_spread_message(ground_spread(pts, gmod, floor))
            if gm:
                r.checks.append(WalkwayCheck(f"{isl.name}の足元", gm[0], gm[1]))
    except Exception:
        pass
    if beams:
        for st_, msg in walkway_beam_checks(s, e, floor + r.deck_mm, floor + r.end_deck_mm, beams,
                                                 r.model.overall_w_mm if r.model else 0.0):
            r.checks.append(WalkwayCheck("梁のまたぎ", st_, msg))
        for isl in r.islands:
            cu = [0.0]
            for s_ in isl.spans_u:
                cu.append(cu[-1] + s_)
            cv = [0.0]
            for s_ in isl.spans_v:
                cv.append(cv[-1] + s_)
            grid = [(isl.origin[0] + isl.u[0] * a + isl.v[0] * b, isl.origin[1] + isl.u[1] * a + isl.v[1] * b)
                    for a in cu for b in cv]
            hit = posts_on_beams(grid, beams, floor)
            if hit:
                r.checks.append(WalkwayCheck("島の支柱と梁", "WARN", f"{isl.name}の支柱 {len(hit)}本が梁の上に乗る。島をずらす"
                                             "か、梁の上の支柱を短くしてジャッキで高さを合わせる"))
    R.ensure_parts(c)
    old = _old_parts(c, r)
    if old:
        c.delete_elements(old)
    pens = parse_pens(spec.get("pens"))
    try:
        mats = c.find_member_surfaces()
    except Exception:
        mats = {}
    made = []
    for st in r.islands:
        (el,) = c.create_objects([(R.versioned_part_name(STAGE_OBJECT), st.origin[0], st.origin[1])])
        params = {**stage_params(st, master=master), **gdl_pens(pens, STAGE_OBJECT)}
        params.update({k: v for k, v in mats.items() if k in ("matScaf", "matDeck") and v})
        c.set_gdl_parameters(el, params)
        made.append(el)
    if r.model is not None:
        (el,) = c.create_objects([(R.versioned_part_name(WALKWAY_OBJECT), s[0], s[1])])
        c.set_gdl_parameters(el, {**walkway_params(r), **gdl_pens(pens, WALKWAY_OBJECT)})
        made.append(el)
    if "--line" in argv:
        DEV_REC.parent.mkdir(parents=True, exist_ok=True)
        DEV_REC.write_text(json.dumps([e["elementId"]["guid"] for e in made]), encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rep = OUT_DIR / f"仮設通路_{r.name}.md"
    rep.write_text(walkway_report(r), encoding="utf-8")
    (OUT_DIR / f"仮設通路_{r.name}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"仮設通路: {r.name} {r.length_mm:.0f}mm（{r.model.model if r.model else '合う機種なし・島だけ'}）と島 {len(r.islands)}つを"
          "置きました" + (f"（前の {len(old)}個を置き換え）" if old else ""))
    for ck in r.checks:
        print(f"  検証 {ck.item}: {ck.status} — {ck.message}")
    print(f"  数量と検証: {rep}")
    if guides:
        delete_guides(c, guides)
    return 0 if r.ok else 2


if __name__ == "__main__":
    sys.exit(main())
