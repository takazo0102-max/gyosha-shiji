"""立面図・断面図・平面図・詳細図のレイアウトと PDF を作る（パレットのボタン「図面を作る」）.

利用者の指定（2026-10-24）「立面図断面図は最後に調整してから作るようにして断面は線で好きなところを作るようにしたい」。
配置では図面を作らず、足場を調整し終えてからこのボタンで作る。足場は置き直さない（配置のときの条件の控え
<工事名>_spec_used.json で解き直して、図面だけ作る）。

断面: 平面図で切りたいところに足場を横切る線を引き（何本でも・ポリラインは折れ目ごと）、その線を選んでから押すと、
線を引いた向きのまま A-A・B-B・C-C… で切る（条件の上書き ashiba_spec.json の cross_cuts_mm に控え、次も同じ線で
切る）。線を選ばずに押すと、前に引いた線（無ければ自動の A-A・B-B）で作る。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import OUT_DIR, building_plan, delete_guides, selected_guides  # noqa: E402

AUTO = "自動（A-A・B-B）"


def cuts_of(guides) -> list[list[list[float]]]:
    """選んだ線 → 切断線 [[[x, y], [x, y]], …]（線を引いた向きのまま。ポリラインは折れ目ごと）."""
    return [[list(a), list(b)] for _el, segs in guides for a, b in segs]


def spec_used_for(plan: dict) -> dict | None:
    outline = plan.get("outline_mm") or []
    for p in sorted(OUT_DIR.glob("*_spec_used.json"), key=lambda q: -q.stat().st_mtime):
        spec = json.loads(p.read_text(encoding="utf-8"))
        if (spec.get("outline_mm") or []) == outline:
            return spec
    return None


def latest_plan() -> dict | None:
    plans = sorted(OUT_DIR.glob("*_plan.json"), key=lambda p: -p.stat().st_mtime)
    return json.loads(plans[0].read_text(encoding="utf-8")) if plans else None


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.cli import solve_groups

    c = ArchicadClient()
    guides = selected_guides(c)
    pts = [p for _el, segs in guides for seg in segs for p in seg]
    plan = building_plan(pts) if pts else latest_plan()
    if plan is None:
        print("図面を作る: 配置の控え（plan.json）がありません。先に「配置」してください")
        return 1
    spec = spec_used_for(plan)
    if spec is None:
        print("図面を作る: 配置のときの条件の控え（_spec_used.json）がありません。一度「配置」し直してください")
        return 1
    body = R.load_spec_override()
    if guides:
        cuts = cuts_of(guides)
        print(f"図面を作る: 断面は選んだ線 {len(cuts)}本で切ります（{'・'.join(f'{chr(65 + i)}-{chr(65 + i)}' for i in range(min(len(cuts), 8)))}）")
    else:
        cuts = list(body.get("cross_cuts_mm") or [])
        if cuts:
            res = show_form({"title": "図面を作る", "intro": f"断面は前に引いた線 {len(cuts)}本で切ります。自動の A-A・B-B に"
                             "戻すこともできます。別の所で切るときは、平面に足場を横切る線を引いて選んでから押してください。",
                             "fields": [], "buttons": [{"id": "keep", "label": "前の線で作る"},
                                                       {"id": "auto", "label": AUTO + "で作る"},
                                                       {"id": "cancel", "label": "やめる"}]})
            if not res or res.get("button") not in ("keep", "auto"):
                print("図面を作る: やめました")
                return 0
            if res["button"] == "auto":
                cuts = []
    # 切断線を条件の上書きに控える（次の配置・図面でも同じ線で切る）
    if cuts:
        body["cross_cuts_mm"] = cuts
    else:
        body.pop("cross_cuts_mm", None)
    R.SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    spec = {**spec, "cross_cuts_mm": cuts} if cuts else {k: v for k, v in spec.items() if k != "cross_cuts_mm"}
    groups = solve_groups(spec)
    _lb, r = groups[0]
    line_part, detail_part = R.ensure_parts(c)
    outline = r.model.plan.outline.vertices
    lines = c.objects_for_slab(outline, (R.LINE_OBJECT,))
    # 詳細図の部品は作り直す（前の分は消す）
    old_details = c.objects_for_slab(outline, (R.DETAIL_OBJECT,), elevation_offset_mm=R.ELEVATION_OFFSET_MM,
                                     detail_offset_mm=R.DETAIL_OFFSET_MM)
    old_details = [e for e in old_details if e not in lines]
    if old_details:
        c.delete_elements(old_details)
    tapir_v, _ac = c.versions()
    dw = R.make_drawings(c, spec, r, groups, lines, [], line_part, detail_part, tapir_v, mode="section")
    if guides:
        delete_guides(c, guides)
        print("図面を作る: 目印の線を消しました")
    n_sec = sum(1 for pl in dw["sections"] if pl.drawing_guid)
    print(f"図面を作る: 立面図 {n_sec}面・詳細図 {len(dw['details'])}枚" + (
        f"・PDF {len(dw['pdf'].files)}枚" if dw.get("pdf") and dw["pdf"].files else "") + "（足場は置き直していません）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
