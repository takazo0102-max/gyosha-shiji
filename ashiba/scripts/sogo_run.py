"""総合仮設計画図（パレットの「総合仮設計画図」。利用者の指定 2026-11-02: 各図面を参考にして、図面かボタンを追加してちょ）.

施工図の手引き（建築施工図研究会 平成16年）の総合仮設計画図にならう。ashiba で置いた仮設（足場・仮囲い・ゲート・仮設建物・
クレーン・場内通路・敷鉄板・構台・重機・根切り図など）がみな映る平面図（いまのフロア）を、置いた物の範囲で切り抜いて
レイアウト「総合仮設 1 総合仮設計画図」（サブセット「総合仮設」）に置き、右の欄に線種の凡例・道路占用の許可基準・主な届出・
事前に確かめる項目を書く。同じ欄を ashiba_out/総合仮設計画図_凡例・確認.pdf にも。

  python3 scripts/sogo_run.py                              # いまのフロアの平面図で
  python3 scripts/sogo_run.py --road-width 3000            # 前面の歩道の有効幅員 3.0m → 足場・仮囲いの出幅の上限
  python3 scripts/sogo_run.py --road-width 6000 --no-sidewalk          # 歩道の無い道路の幅員 6.0m
  python3 scripts/sogo_run.py --road-width 4000 --guard-inner 2400     # ガードレールの内側まで 2.4m
  python3 scripts/sogo_run.py --remove                     # 作ったレイアウトを消す

範囲: 何か選んで押せば、選んだ物（敷地を囲む線・仮囲い・建物など）の外接箱を 3m 広げたもの。選んでいなければ、配置の控え
（いちばん新しい *_plan.json の躯体の外形）と、ashiba_out の控え（クレーン・仮囲い・仮設建物…の GUID）の要素のうち躯体から
60m 以内のものの外接箱を合わせて 3m 広げたもの（控えには前の試しの離れた場所の物も残るので、遠い物は入れない。2026-11-03 の
実機で 1/500 でも用紙からはみ出した）。レイヤーの表示はいまの平面図のまま（隠したレイヤーは図にも出ない）.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LAYOUT = "総合仮設 1 総合仮設計画図"
RECORDS = ("クレーン.json", "タワークレーン.json", "仮囲い.json", "仮設建物.json", "場内通路.json", "敷鉄板.json", "構台.json",
           "重機.json", "根切り.json", "柵.json", "開口養生.json", "親綱.json", "単管でつなぐ.json", "山留め足場.json")
GUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", re.I)
MARGIN_MM = 3000.0
NEAR_MM = 60000.0           # 躯体からこれより遠い控えの仮設は範囲に入れない


def record_guids(out_dir: Path) -> list[str]:
    """控えの JSON の中の GUID（値の方。鍵は線の GUID のことがあるので値だけ）."""
    found = []

    def walk(v):
        if isinstance(v, str) and GUID.match(v):
            found.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for name in RECORDS:
        try:
            walk(json.loads((out_dir / name).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return list(dict.fromkeys(found))


def near_boxes(points_mm: list, boxes: list, near: float = NEAR_MM) -> list:
    """躯体の外形（点）の外接箱から near 以内に掛かる外接箱だけ（点が無ければ全部）."""
    if not points_mm:
        return list(boxes)
    x0, x1 = min(p[0] for p in points_mm) - near, max(p[0] for p in points_mm) + near
    y0, y1 = min(p[1] for p in points_mm) - near, max(p[1] for p in points_mm) + near
    return [b for b in boxes if b[2] >= x0 and b[0] <= x1 and b[3] >= y0 and b[1] <= y1]


def boxes_of(c, guids: list) -> list:
    """要素の平面の外接箱（mm の xMin, yMin, xMax, yMax）."""
    out = []
    if not guids:
        return out
    r = c.tapir("Get3DBoundingBoxes", {"elements": [{"elementId": {"guid": g}} for g in guids]})
    for bx in r.get("boundingBoxes3D", []):
        b = bx.get("boundingBox3D") or {}
        if "xMin" in b:
            out.append(tuple(b[k] * 1000.0 for k in ("xMin", "yMin", "xMax", "yMax")))
    return out


def region_of(points_mm: list, boxes: list, margin: float = MARGIN_MM):
    """点と外接箱（mm の xMin, yMin, xMax, yMax）を合わせた範囲を margin 広げる. 何も無ければ None."""
    xs = [p[0] for p in points_mm] + [b[0] for b in boxes] + [b[2] for b in boxes]
    ys = [p[1] for p in points_mm] + [b[1] for b in boxes] + [b[3] for b in boxes]
    if not xs:
        return None
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.elevation_sections import (_create_layout, _delete_items, _layout_paper_mm, _tree, activate_floor_plan,
                                           clipped_drawing_geometry, create_clipped_drawings, ensure_subset, fit_scale,
                                           pick_master_layout, plan_source, scale_caption, walk_tree)
    from ashiba.form_drawings import to_pdf
    from ashiba.form_layout import draw_shapes, layout_attrs, svg_shapes
    from ashiba.sheet_panel import PANEL_GAP_MM, PANEL_W_MM
    from ashiba.sogo_sheet import SUBSET, build_html, panel_svg, road_limit
    from ashiba.tapir_adapter import ArchicadClient

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--road-width", type=float, default=None, help="前面道路の幅 mm（歩道なら有効幅員、--no-sidewalk なら道路幅員）")
    ap.add_argument("--no-sidewalk", action="store_true", help="歩道の無い道路（車道上の基準 1/8）")
    ap.add_argument("--guard-inner", type=float, default=None, help="ガードレール・植樹帯の内側（路端側）までの幅 mm")
    ap.add_argument("--scale", type=int, default=None, help="縮尺 1/n の n（省くと用紙に収まるいちばん大きい縮尺）")
    ap.add_argument("--remove", action="store_true", help="作ったレイアウトを消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    lb = _tree(c, "LayoutBook")
    old = [it["guid"] for it in walk_tree(lb) if it["type"] == "LayoutItem" and it["name"] == LAYOUT]
    if a.remove:
        print(f"総合仮設計画図: レイアウトを {_delete_items(c, old) if old else 0} 枚消しました")
        return 0
    road = desc = None
    if a.road_width:
        road = road_limit(a.road_width, not a.no_sidewalk, a.guard_inner)
        desc = f"{'歩道の有効幅員' if not a.no_sidewalk else '道路幅員'} {a.road_width / 1000:g}m"
        print(f"  道路占用: 出幅の上限 {road.max_out_mm:,.0f}mm（{road.rule}）")
        for x in road.notes:
            print(f"    {x}")
    spec = {**R.SPEC, **R.load_spec_override()}
    project = str(spec.get("project_name") or "")
    html_path = R.OUT_DIR / "総合仮設計画図_凡例・確認.html"
    html_path.write_text(build_html(project, road, desc or ""), encoding="utf-8")
    pdf = R.OUT_DIR / "総合仮設計画図_凡例・確認.pdf"
    ok = to_pdf(html_path, pdf)
    # 範囲: 選んだ物か、躯体の外形とその近くに置いた仮設（選択は平面図のウィンドウのもの。レイアウトが前面だと読めない）
    activate_floor_plan(c)
    pts, boxes, how = [], [], ""
    sel = c.get_selected_elements()
    if sel:
        boxes = boxes_of(c, [e["elementId"]["guid"] for e in sel])
        how = f"選んだ {len(sel)} 個"
    else:
        for p in sorted(R.OUT_DIR.glob("*_plan.json"), key=lambda q: -q.stat().st_mtime)[:1]:
            pts = [tuple(v) for v in json.loads(p.read_text(encoding="utf-8")).get("outline_mm", [])]
            how = f"配置の控え {p.name}"
        try:
            near = near_boxes(pts, boxes_of(c, record_guids(R.OUT_DIR)))
        except Exception as ex:
            near = []
            print(f"  注意: 置いた仮設の範囲を読めませんでした（{ex}）")
        boxes = near
        how += f"・近くの仮設 {len(near)} 個"
    region = region_of(pts, boxes)
    if region is None:
        print("総合仮設計画図: 配置の控え（*_plan.json）も置いた仮設も無いので、平面図の範囲を決められません。先に「配置」か仮設を置いてください")
        return 1
    notes = []
    activate_floor_plan(c)
    story, src_scale, note = plan_source(c)
    if note:
        notes.append(note)
    if story is None:
        print(f"総合仮設計画図: {note}")
        return 1
    if old:
        _delete_items(c, old)
    subset = ensure_subset(c, SUBSET)
    lb = _tree(c, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    lay = _create_layout(c, LAYOUT, subset, master)
    if not lay:
        print("総合仮設計画図: レイアウトを作れませんでした")
        return 1
    paper, m0 = _layout_paper_mm(c, lay)
    margins = (m0[0], m0[1], m0[2] + PANEL_W_MM + PANEL_GAP_MM, m0[3])
    box = (region[2] - region[0], region[3] - region[1])
    scale = a.scale or fit_scale(box, paper, margins)
    if scale is None:
        scale = 500
        notes.append(f"範囲 {box[0] / 1000:.0f}×{box[1] / 1000:.0f}m が 1/500 でも用紙に収まらない。敷地を囲む線などを選んで押す")
    pos = (margins[0] + 10.0, paper[1] - margins[1] - box[1] / scale)
    clip, position = clipped_drawing_geometry(region, scale, pos, source_scale=src_scale)
    dbid = c.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": lay}}]})["databases"][0]["databaseId"]
    # 作ったばかりのレイアウトを開いてから置く（開かずに置くと、原点が移ったプロジェクトで図面の原点のずれ（modelOffset）が
    # 0 と読めて置き直しが外れ、白紙になった。2026-11-03 の実機）
    c.tapir("ChangeWindow", {"navigatorItemId": {"guid": lay}})
    els = create_clipped_drawings(c, [{"navigatorItemId": {"guid": story["guid"]}, "layoutDatabaseId": dbid, "position": position,
                                       "clipPolygon": clip, "scale": src_scale / scale, "drawingScale": float(scale),
                                       "name": f"総合仮設計画図 {scale_caption(scale)}"}], lay)
    if not els or "elementId" not in els[0]:
        notes.append(f"平面図を置けませんでした: {(els or [{}])[0]}")
    # 右の欄（用紙 mm、左上が原点・下向き）
    x0 = paper[0] - m0[2] - PANEL_W_MM
    body, _y = panel_svg(x0, m0[1] + 4.0, PANEL_W_MM, road, desc or "")
    body += (f'<text x="{margins[0] + 10.0:.1f}" y="{m0[1] + 6.0:.1f}" class="h1">総合仮設計画図　{scale_caption(scale)}</text>')
    n = draw_shapes(c, lay, svg_shapes(body), paper, (1.0, 0.0, 0.0), layout_attrs(c), notes, LAYOUT)
    activate_floor_plan(c)
    print(f"総合仮設計画図: レイアウト「{LAYOUT}」（{scale_caption(scale)}・範囲 {box[0] / 1000:.0f}×{box[1] / 1000:.0f}m＝{how}・"
          f"右の欄 {n or 0} 個）・{pdf if ok else html_path}")
    for x in notes:
        print(f"  注意: {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
