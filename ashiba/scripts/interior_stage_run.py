"""内部ステージ足場を平面の長方形で置く（パレットのボタン「内部足場」）.

利用者の指定（2026-10-24）「内部足場の内部ステージ足場の機能追加して検証して」。平面で、ステージを組む室内の範囲に
長方形（ポリラインの4点か、対角の線1本）を引いて選んで押す。窓で名前・作業床の高さ・積載を入れて「置く」と、
系列のスパンで格子に割って部品 ashiba_stage を置き、検証（支柱の軸力・作業床の積載・高さと短辺の比・墜落防止）と
数量を ashiba_out/内部足場_<名前>.md に書く。同じ範囲に前に置いたステージは置き換える。目印の線は消す。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import OUT_DIR, delete_guides, not_in_plan_hint, selected_guides  # noqa: E402

STAGE_OBJECT = "ashiba_stage"


def corners_of(guides) -> list[list[float]] | None:
    """選んだ線 → 長方形の4点（ポリラインの4点、または対角の線1本なら軸にそろえた長方形）."""
    pts: list[tuple[float, float]] = []
    for _el, segs in guides:
        for a, b in segs:
            for p in (a, b):
                if not any(abs(p[0] - q[0]) + abs(p[1] - q[1]) < 1.0 for q in pts):
                    pts.append(p)
    if len(pts) >= 4:
        return [list(p) for p in pts[:4]]
    if len(pts) == 2:
        (x0, y0), (x1, y1) = pts
        return [[min(x0, x1), min(y0, y1)], [max(x0, x1), min(y0, y1)], [max(x0, x1), max(y0, y1)],
                [min(x0, x1), max(y0, y1)]]
    return None


def _inside(p, corners) -> bool:
    from ashiba.obstacles import _inside as inside

    return inside(p, [tuple(c) for c in corners])


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.cli import resolve_series_id
    from ashiba.interior_stage import LIVE_DEFAULT_KN_M2, solve_stage, stage_params, stage_report
    from ashiba.master import load_master
    from ashiba.structural import load_capacities

    c = ArchicadClient()
    guides = selected_guides(c)
    corners = corners_of(guides) if guides else None
    if corners is None:
        print("内部足場: 平面で、ステージを組む範囲に長方形（ポリラインの4点か対角の線1本）を引いて選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    res = show_form({"title": "内部足場（内部ステージ足場）", "intro": "範囲に支柱を格子に立て、最上段に全面の作業床を張ります。"
                     "作業床の高さは床から（天井の作業なら 天井高−1800 前後）。",
                     "fields": [{"key": "name", "label": "名前", "kind": "text", "value": "内部ステージ足場"},
                                {"key": "deck", "label": "作業床の高さ mm", "kind": "number", "value": "4000"},
                                {"key": "live", "label": "積載 kN/m²", "kind": "number", "value": f"{LIVE_DEFAULT_KN_M2}"}],
                     "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        print("内部足場: やめました（何も置いていません）")
        return 0
    vals = res.get("values") or {}
    item = {"name": str(vals.get("name") or "内部ステージ足場"), "corners_mm": corners,
            "deck_mm": float(str(vals.get("deck") or "4000").replace(",", "")),
            "live_kn_m2": float(str(vals.get("live") or LIVE_DEFAULT_KN_M2))}
    spec = {**R.SPEC, **R.load_spec_override()}
    sid = resolve_series_id(spec)
    master = load_master(sid)
    try:
        st = solve_stage(item, master, load_capacities(sid))
    except ValueError as e:
        print(f"内部足場: {e}")
        return 1
    R.ensure_parts(c)
    name = R.versioned_part_name(STAGE_OBJECT)
    # 同じ範囲に前に置いたステージは置き換える
    old = []
    try:
        objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        for e, d in zip(objs, c.get_details(objs) if objs else []):
            dd = d.get("details") or {}
            if not str((dd.get("libPart") or {}).get("name", "")).startswith(STAGE_OBJECT):
                continue
            o = dd.get("origin") or {}
            if _inside((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0), corners):
                old.append(e)
    except Exception:
        old = []
    if old:
        c.delete_elements(old)
    (el,) = c.create_objects([(name, st.origin[0], st.origin[1])])
    from ashiba.pens import gdl_pens, parse_pens

    params = {**stage_params(st), **gdl_pens(parse_pens(spec.get("pens")), STAGE_OBJECT)}
    try:
        mats = c.find_member_surfaces()
        if mats.get("matScaf"):
            params["matScaf"] = mats["matScaf"]
        if mats.get("matDeck"):
            params["matDeck"] = mats["matDeck"]
    except Exception:
        pass
    c.set_gdl_parameters(el, params)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rep = OUT_DIR / f"内部足場_{st.name}.md"
    rep.write_text(stage_report(st), encoding="utf-8")
    (OUT_DIR / f"内部足場_{st.name}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"内部足場: {st.name} {st.length_u:.0f}×{st.length_v:.0f}（スパン {len(st.spans_u)}×{len(st.spans_v)}・床高 {st.deck_mm}）を置きました"
          + (f"（前の {len(old)}個を置き換え）" if old else ""))
    for ck in st.checks:
        print(f"  検証 {ck.item}: {ck.status} — {ck.message}")
    print(f"  数量と検証: {rep}")
    delete_guides(c, guides)
    return 0 if st.ok else 2


if __name__ == "__main__":
    sys.exit(main())
