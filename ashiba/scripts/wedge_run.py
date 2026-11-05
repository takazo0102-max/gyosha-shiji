"""くさび1点で部材を足す（パレットの「くさび1点で部材」「くさび1点の部材を消す」。GLOOBE 2026 のくさび受け参照入力）.

平面で、足したい部材の始めのくさび受け（支柱の芯）から足す向きへ線を引いて選び、窓で種類（布材・腕木・先行手すり・踏板・幅木）と
くさび受けの高さを選ぶ。線の向き＝部材の向き（梁間方向の腕木・桁方向の布材など4方向のどれでも）、線の長さ＝部材の長さ（系列の
規格の長さのいちばん近いもの）。部品 ashiba_member を1本ずつ置き、発注表は ashiba_out/くさび1点の部材.md。判定と選び方は
src/ashiba/wedge_point.py.

  python3 scripts/wedge_run.py                                     # 窓で選ぶ
  python3 scripts/wedge_run.py --kind 布材・腕木 --levels 1800,3600  # 高さ mm（足場の立つ面から。コマのピッチにそろえる）
  python3 scripts/wedge_run.py --remove                            # 置いた部材を消す（控えの GUID だけ）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

RECORD = "くさび1点の部材.json"


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from excav_run import _delete_alive, _place
    from form_dialog import show_form
    from guide_lines import selected_guides
    from kakoi_run import chains

    from ashiba.elevation_sections import activate_floor_plan
    from ashiba.explode import MEMBER_OBJECT
    from ashiba.master import SERIES_CONST, load_master
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from ashiba.wedge_point import KINDS, from_line, member_params, plan, report

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", default=None, choices=list(KINDS), help="部材の種類")
    ap.add_argument("--levels", default=None, help="くさび受けの高さ mm（カンマ区切り。足場の立つ面から）")
    ap.add_argument("--z", type=float, default=None, help="足場の立つ面の高さ mm（省くと地盤から）")
    ap.add_argument("--remove", action="store_true", help="置いた部材を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    try:
        activate_floor_plan(c)
    except Exception:
        pass
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, [g for v in rec.values() for g in v.get("guids", [])])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"くさび1点の部材: {n}本を消しました")
        return 0
    segs = []
    for key, pts, _closed in chains(selected_guides(c)):
        for i, (p0, p1) in enumerate(zip(pts, pts[1:])):
            segs.append((f"{key}:{i}", tuple(p0), tuple(p1)))
    if not segs:
        print("くさび1点の部材: くさび受け（支柱の芯）から足す向きへ、部材の長さの線を引いて選んでから押してください")
        return 1
    spec = {**R.SPEC, **R.load_spec_override()}
    series = spec.get("series_id") or "nikken_nd1800"
    try:
        master = load_master(series)
    except Exception:
        series = "nikken_nd1800"
        master = load_master(series)
    pitch = float(SERIES_CONST.get(series, {}).get("koma_pitch", 0) or 0)
    if a.kind is None:
        res = show_form({"title": "くさび1点で部材", "intro": f"線 {len(segs)}本。線の始め＝くさび受け、向き＝部材の向き、長さ＝部材の長さ"
                                                         f"（系列 {series} の規格にそろえる）。",
                         "fields": [{"key": "kind", "label": "部材", "kind": "choice", "options": list(KINDS), "value": next(iter(KINDS))},
                                    {"key": "levels", "label": f"くさび受けの高さ mm（カンマ区切り。コマ {pitch:.0f} にそろえる）",
                                     "kind": "text", "value": "1800"}],
                         "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
        if not res or res.get("button") != "place":
            print("くさび1点の部材: やめました")
            return 0
        v = res.get("values") or {}
        a.kind = str(v.get("kind") or next(iter(KINDS)))
        a.levels = str(v.get("levels") or "1800")
    levels = [float(x) for x in str(a.levels or "1800").replace("、", ",").split(",") if x.strip()]
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, p0, p1 in segs for p in (p0, p1)])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    part = R.versioned_part_name(MEMBER_OBJECT)
    c.ensure_embedded_parts([(R.GDL_DIR / f"{MEMBER_OBJECT}.gsm", part)])
    pieces = []
    for key, p0, p1 in segs:
        if key in rec:
            _delete_alive(c, rec.pop(key).get("guids", []))
        z0 = a.z if a.z is not None else (ground(*p0) if ground else 0.0)
        made, mine = [], []
        for lv in levels:
            pc = plan([from_line(f"部材{len(pieces) + len(mine) + 1}", a.kind, p0, p1, lv)], master, pitch)[0]
            if pc.part is None:
                print(f"  注意: {'。'.join(pc.notes)}")
                continue
            el = _place(c, part, p0, z0, 0.0)
            if el is None:
                continue
            c.set_gdl_parameters(el, member_params(pc), MEMBER_OBJECT)
            made.append(el["elementId"]["guid"])
            mine.append(pc)
        rec[key] = {"kind": a.kind, "guids": made, "a": list(p0), "b": list(p1), "levels": levels}
        pieces += mine
        for pc in mine:
            print(f"  {pc.name}: {pc.kind} {pc.part.model_no}（{pc.part.nominal_dim}）高さ {pc.z_mm:,.0f}"
                  + (f"・{'。'.join(pc.notes)}" if pc.notes else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    # 帳票は控えの全部から
    every = [pc for k, v in rec.items() for lv in v.get("levels", []) if v.get("a")
             for pc in plan([from_line(v["kind"], v["kind"], v["a"], v["b"], lv)], master, pitch)]
    for i, pc in enumerate(every, 1):
        pc.name = f"部材{i}"
    md = R.OUT_DIR / "くさび1点の部材.md"
    md.write_text(report(every, series), encoding="utf-8")
    print(f"くさび1点の部材: {len(pieces)}本を置きました（発注表: {md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
