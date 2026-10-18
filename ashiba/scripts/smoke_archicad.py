"""実機スモーク: 小型入力と 30×20m（メートル・インチ）を順に Archicad に置いて照合する.

1件ごとに、利用者のモデルから離れた所（x=2000m〜、100m おき）へ躯体スラブを作り、
ツールバーと同じ run_from_archicad.main() で置いてから次を確かめる。

- 足場ラインの本数＝面の数
- 部品が書き戻した図示本数（qty*）が Python の式（face_drawn_counts）と同じ。すべて 0 なら
  1D スクリプトが途中で止まっている
- 足場ラインの 2D・3D プレビューが真っ白でない（GDL のエラーは黙って何も描かない）
- 断面図方式なら、断面の図面が面の数だけレイアウトにあり、足場平面図も置けた
- 総合判定の是正項目が CLI（solve_all）と同じ

終わったら置いたもの（部品・断面・レイアウト・スラブ）を消す（--keep で残す）。帳票と立面の
控えは out/smoke/<件名>/ に書く（利用者の Desktop/ashiba_out は触らない）。足場条件の部品は使わない。

使い方:
  python3 scripts/smoke_archicad.py                      # 全件（小型5件＋30×20m 2件）
  python3 scripts/smoke_archicad.py --only=small_stage,rect_inch
  python3 scripts/smoke_archicad.py --keep               # 置いたまま残す（目で見る用）
  python3 scripts/smoke_archicad.py --cleanup --only=rect_metric   # --keep で残したものを後で片付ける
  python3 scripts/smoke_archicad.py --verbose            # 通った項目も中身を出す
終了コード: すべて OK なら 0、NG があれば 1。
"""

from __future__ import annotations

import base64
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.cli import solve_all  # noqa: E402
from ashiba.elevation_sections import (  # noqa: E402
    activate_floor_plan,
    layout_name,
    load_record,
    plan_layout_name,
    remove_elevations,
    sheet_layout_name,
)
from ashiba.detail_sheet import detail_layout_name  # noqa: E402
from ashiba.gdl_params import FACE_COUNT_PARAMS, face_drawn_counts  # noqa: E402
from ashiba.smoke import CaseReport, all_zero, cases, count_mismatches, placed_spec, select, summary_lines  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402
from bisect_gdl import is_blank  # noqa: E402
import run_from_archicad as tb  # noqa: E402

OUT = ROOT / "out" / "smoke"


def _params(client, el) -> dict:
    item = client.tapir("GetGDLParametersOfElements", {"elements": [el]})["gdlParametersOfElements"][0]
    return {p["name"]: p.get("value") for p in item.get("gdlParameters", item.get("parameters", []))}


def _preview_blank(client, el, view: str, save_to: Path) -> bool:
    resp = client.tapir("GetElementPreviewImage", {"elementId": el["elementId"], "imageType": view,
                                                   "width": 2400, "height": 1500})
    png = base64.b64decode(resp["previewImage"])
    save_to.write_bytes(png)
    return is_blank(png)


def run_case(client, case, index: int, keep: bool) -> CaseReport:
    rep = CaseReport(case.name)
    spec, outline = placed_spec(case, index)
    out_dir = OUT / case.name
    out_dir.mkdir(parents=True, exist_ok=True)
    activate_floor_plan(client)
    slab = client.create_slab([tuple(p) for p in outline])
    res = None
    try:
        res = tb.main(outline_mm=outline, spec_override=spec, out_dir=out_dir, use_spec_object=False,
                      fill_title=False)
        r = res["result"]
        edges = r.model.plan.edges
        rep.add("足場ラインの本数", len(res["lines"]) == len(edges), f"置いた{len(res['lines'])}本・面{len(edges)}")

        # 置いた順は面の順（place_scaffold_lines）
        for ep, el in zip(edges, res["lines"]):
            face = r.model.face_name(ep.edge_index)
            got = _params(client, el)
            if all_zero(got, FACE_COUNT_PARAMS):
                rep.add(f"{face} 図示本数", False, "すべて0（1D スクリプトが止まっている可能性）")
                continue
            want = face_drawn_counts(r.model, ep, stair_plan=r.stair_plan, openings=r.openings)
            if not any(k in got for k in want):
                rep.add(f"{face} 図示本数", False, "部品に図示本数のパラメータが無い（古い部品？）")
                continue
            bad = count_mismatches(want, got)
            rep.add(f"{face} 図示本数", not bad, "・".join(bad) or f"{sum(k in got for k in want)}項目一致")
        if res["lines"]:
            for view in ("2D", "3D"):
                blank = _preview_blank(client, res["lines"][0], view, out_dir / f"preview_{view}.png")
                rep.add(f"プレビュー {view}", not blank, f"真っ白（{out_dir / f'preview_{view}.png'}）" if blank else "")

        if res["elevation_mode"] == "section":
            secs = res["sections"]
            drawn = [s for s in secs if s.drawing_guid]
            rep.add("断面の立面図", len(drawn) == len(edges), f"図面{len(drawn)}・面{len(edges)}")
            ps = res["plan_sheet"]
            rep.add("足場平面図のレイアウト", bool(ps and ps.drawing_guid), "; ".join(ps.notes) if ps else "置いていない")
            ds = res.get("detail_sheet")
            n_det = len(res["details"])
            rep.add("足場詳細図のレイアウト", bool(ds) and len(ds.drawing_guids) == n_det,
                    (f"図面{len(ds.drawing_guids)}・詳細図{n_det}・1/{ds.scale}" + ("; " + "; ".join(ds.notes) if ds.notes else ""))
                    if ds else "置いていない")
            pdf = res.get("pdf")
            rep.add("PDF の発行（立面・平面・詳細）", bool(pdf) and len(pdf.files) == 3,
                    (f"{len(pdf.files)}枚" + ("; " + "; ".join(pdf.notes) if pdf.notes else "")) if pdf else "発行していない")
        else:
            rep.add("立面図（部品）", len(res["elevations"]) == len(edges), f"{len(res['elevations'])}面")

        offline = solve_all(res["spec"])
        same = list(offline.verdict["blockers"]) == list(res["verdict"]["blockers"])
        rep.add("総合判定が CLI と同じ", same, f"CLI {offline.verdict['blockers']}・実機 {res['verdict']['blockers']}")
    except (TapirError, Exception) as e:      # 1件の失敗で残りを止めない
        rep.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        if not keep:
            _cleanup(client, spec, outline, out_dir, slab)
    return rep


def _cleanup(client, spec: dict, outline, out_dir: Path, slab) -> None:
    prefix = spec["project_name"]
    try:
        activate_floor_plan(client)
        objs = client.objects_for_slab([tuple(p) for p in outline], (tb.LINE_OBJECT, tb.DETAIL_OBJECT),
                                       elevation_offset_mm=tb.ELEVATION_OFFSET_MM,
                                       detail_offset_mm=tb.DETAIL_OFFSET_MM)
        if objs:
            client.delete_elements(objs)
        rec = load_record(out_dir)
        faces = [k[len(prefix) + 1:-len(" 足場立面")] for k in rec if k.startswith(prefix + " ")]
        remove_elevations(client, list(rec), [layout_name(prefix, f) for f in faces]
                          + [sheet_layout_name(prefix), plan_layout_name(prefix), detail_layout_name(prefix)],
                          rec.values())
        (out_dir / "elevation_sections.json").write_text("{}\n", encoding="utf-8")
        from ashiba.elevation_sections import building_key
        from ashiba.plan_labels import remove_plan_labels
        activate_floor_plan(client)
        remove_plan_labels(client, out_dir, building_key([tuple(p) for p in outline]))
        activate_floor_plan(client)
        if slab is not None:
            client.delete_elements([slab])
    except TapirError as e:
        print(f"  片付けに失敗（手で消してください）: {e}")


def _find_slab(client, outline):
    """スモークが作った躯体スラブ（外形の外接矩形が一致するもの）. 無ければ None."""
    xs = [p[0] / 1000.0 for p in outline]
    ys = [p[1] / 1000.0 for p in outline]
    want = (min(xs), min(ys), max(xs), max(ys))
    els = client.post("API.GetElementsByType", {"elementType": "Slab"}).get("elements", [])
    if not els:
        return None
    boxes = client.post("API.Get2DBoundingBoxes", {"elements": els}).get("boundingBoxes2D", [])
    for el, b in zip(els, boxes):
        bb = b.get("boundingBox2D") if isinstance(b, dict) else None
        if not bb:
            continue
        got = (bb["xMin"], bb["yMin"], bb["xMax"], bb["yMax"])
        if all(abs(g - w) < 0.01 for g, w in zip(got, want)):
            return el
    return None


def cleanup_kept(client, case, index: int) -> None:
    """--keep で残した1件（部品・断面・レイアウト・スラブ）を片付ける."""
    spec, outline = placed_spec(case, index)
    activate_floor_plan(client)
    slab = _find_slab(client, outline)
    if slab is None:
        print(f"  {case.name}: スモークのスラブが見つかりません（部品・断面・レイアウトだけ片付けます）")
    _cleanup(client, spec, outline, OUT / case.name, slab)
    print(f"  {case.name}: 片付けました")


def main() -> int:
    only = [s for a in sys.argv[1:] if a.startswith("--only=") for s in a.split("=", 1)[1].split(",") if s]
    keep = "--keep" in sys.argv
    todo = select(cases(ROOT / "examples" / "dev"), only)
    client = ArchicadClient()
    if not client.wait_ready():
        print("Archicad が応答しません")
        return 2
    tv, av = client.versions()
    print(f"Archicad {av} ＋ Tapir {tv}・{len(todo)}件")
    all_names = [c.name for c in cases(ROOT / "examples" / "dev")]
    if "--cleanup" in sys.argv:
        for case in todo:
            cleanup_kept(client, case, all_names.index(case.name))
        activate_floor_plan(client)
        return 0
    reports = []
    for case in todo:
        print(f"--- {case.name}")
        reports.append(run_case(client, case, all_names.index(case.name), keep))
    activate_floor_plan(client)
    print()
    for line in summary_lines(reports, verbose="--verbose" in sys.argv):
        print(line)
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
