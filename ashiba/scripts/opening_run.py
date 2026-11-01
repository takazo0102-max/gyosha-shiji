"""床の開口の養生・床の縁の手すり（パレットの「開口養生」「床の縁の手すり」「開口養生を消す」）.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の5番。

  python3 scripts/opening_run.py              # 選んだ床（無ければ全部の床）の開口に、大きさで蓋か手すり・幅木・ネット
  python3 scripts/opening_run.py --edges      # 床の縁（外に同じ高さの床が続かない辺）にも手すり・幅木
  python3 scripts/opening_run.py --edges-only # 床の縁だけ
  python3 scripts/opening_run.py --min 30     # これより小さい開口は数えない（mm。既定 30＝床材のすき間 3cm）
  python3 scripts/opening_run.py --post base  # 手すり柱を固定ベース PKB＋単管 1.0M（既定はスタンション NREG）
  python3 scripts/opening_run.py --remove     # 置いた養生を消す

部品 ashiba_opening を開口ごと・縁ごとに1つ（src/ashiba/opening_guard.py が区分・判定・数量）。落差は開口の真ん中から下の床
（開口に掛からない一番高い床）か地盤まで。前に同じ床に置いたものは控え（ashiba_out/開口養生.json）で消して置き直す。
帳票は ashiba_out/開口養生.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_opening"
RECORD = "開口養生.json"


def slab_info(d: dict) -> dict | None:
    """Tapir の床の詳細 → 外形・開口（mm）・上端の高さ・厚さ."""
    det = d.get("details", {})
    out = det.get("polygonOutline") or []
    if len(out) < 3:
        return None
    pts = [(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for p in out]
    holes = []
    for h in det.get("holes") or []:
        hp = h.get("polygonOutline", h) if isinstance(h, dict) else h
        if isinstance(hp, list) and len(hp) >= 3:
            holes.append([(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for p in hp])
    t = float(det.get("thickness") or 0.2) * 1000.0
    z = float(det.get("zCoordinate") or 0.0) * 1000.0
    ref = str(det.get("referencePlaneLocation") or "Top")
    top = z if ref == "Top" else z + t if ref == "Bottom" else z + t / 2.0
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    holes = [h[:-1] if h[0] == h[-1] else h for h in holes]
    return {"outline": pts, "holes": holes, "top": top, "t": t}


def guards_for(slabs: list, targets: list, ground, edges: bool, holes: bool, min_mm: float, post: str = "NREG"):
    from ashiba.opening_guard import Guard, drop_below, edge_runs, oriented_box, plan_guard

    out = []
    for key, s in targets:
        gs = []
        if holes:
            for h in s["holes"]:
                corner, w, d, ang = oriented_box(h)
                if min(w, d) < min_mm:
                    continue
                cx = sum(p[0] for p in h) / len(h)
                cy = sum(p[1] for p in h) / len(h)
                g0 = ground(cx, cy) if ground else 0.0
                gs.append(Guard("", w, d, drop_below((cx, cy), s["top"], slabs, g0), corner=corner, angle=ang, z=s["top"],
                                slab_t=s["t"], post=post))
        if edges:
            n = len(s["outline"])
            cx = sum(p[0] for p in s["outline"]) / n
            cy = sum(p[1] for p in s["outline"]) / n
            for a, b in edge_runs(s, slabs):
                m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                u = (b[0] - a[0], b[1] - a[1])
                side = 1 if u[0] * (cy - a[1]) - u[1] * (cx - a[0]) > 0 else -1
                L = math.dist(a, b)
                out_pt = (m[0] - side * (-u[1]) / L * 500.0, m[1] - side * u[0] / L * 500.0)
                g0 = ground(*out_pt) if ground else 0.0
                gs.append(Guard("", L, 0.0, drop_below(out_pt, s["top"], slabs, g0), kind=5, corner=a,
                                angle=math.degrees(math.atan2(u[1], u[0])), z=s["top"], slab_t=s["t"], side=side, post=post))
        out.append((key, [plan_guard(g) for g in gs]))
    return out


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.opening_guard import part_params, report
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--edges", action="store_true", help="床の縁にも手すり")
    ap.add_argument("--edges-only", action="store_true", help="床の縁だけ")
    ap.add_argument("--min", type=float, default=30.0, help="これより小さい開口は数えない mm")
    ap.add_argument("--post", default="stanchion", choices=("stanchion", "base"),
                    help="手すり柱（stanchion＝スタンション NREG で縁をくわえる・base＝固定ベース PKB＋単管 1.0M をアンカー）")
    ap.add_argument("--remove", action="store_true", help="置いた養生を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, [g for v in rec.values() for g in v])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"開口養生: {n}個を消しました")
        return 0
    all_els = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
    if not all_els:
        print("開口養生: 床（スラブ）がありません")
        return 1
    dets = c.get_details(all_els)
    slabs, by_guid = [], {}
    for e, d in zip(all_els, dets):
        s = slab_info(d)
        if s:
            slabs.append(s)
            by_guid[e["elementId"]["guid"]] = s
    sel = {e["elementId"]["guid"] for e in c.get_selected_elements()}
    keys = [g for g in by_guid if g in sel] or list(by_guid)
    pts = [p for g in keys for p in by_guid[g]["outline"]]
    gm = read_ground_model(c, pts)
    ground = gm.elevation_at if getattr(gm, "points", None) else None
    plans = guards_for(slabs, [(g, by_guid[g]) for g in keys], ground, a.edges or a.edges_only, not a.edges_only, a.min,
                       "PKB" if a.post == "base" else "NREG")
    if not any(gs for _k, gs in plans):
        print("開口養生: 開口（と床の縁）が見つかりません。床の開口は床の穴として描く")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    done, k_open, k_edge = [], 0, 0
    for key, gs in plans:
        if key in rec:
            _delete_alive(c, rec.pop(key))
        guids = []
        for g in gs:
            if g.kind == 5:
                k_edge += 1
                g.name = f"縁{k_edge}"
            else:
                k_open += 1
                g.name = f"開口{k_open}"
            el = _place(c, part, g.corner, g.z, g.angle)
            if el is None:
                continue
            c.set_gdl_parameters(el, {**part_params(g), **pens})
            guids.append(el["elementId"]["guid"])
            done.append(g)
        rec[key] = guids
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "開口養生.md"
    md.write_text(report(done), encoding="utf-8")
    bad = [g.name for g in done if any(x.status != "OK" for x in g.checks)]
    print(f"開口養生: 開口 {k_open}・縁 {k_edge}" + (f"・要確認 {'・'.join(bad)}" if bad else "") + f"（{md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
