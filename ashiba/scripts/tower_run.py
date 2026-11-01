"""タワークレーン（パレットの「タワークレーン」「タワークレーンを消す」）.

利用者の指定（2026-11-01）「タワークレーンも追加してちょ」。

  python3 scripts/tower_run.py --type v720 --mast 45          # 選んだ線の始め＝マストの芯、始めの辺の向き＝ジブの向き
  python3 scripts/tower_run.py --type v720 --radius 25 --load 6.0      # 作業半径 m・吊り荷 t（定格荷重の判定）
  python3 scripts/tower_run.py --ties 20000,32000 --tie-dir 180        # 壁つなぎの高さ mm と建物の向き（度）
  python3 scripts/tower_run.py --list                         # 機種の一覧
  python3 scripts/tower_run.py --remove                       # 置いたタワークレーンを消す

部品 ashiba_tower を線1本に1基（src/ashiba/tower.py が機種・寸法・判定）。敷地境界（足場条件か Archicad）があれば、
ジブ・カウンタウエイトが敷地の外へ出る辺（オーバースイング）を判定する。控えは ashiba_out/タワークレーン.json、帳票は
ashiba_out/タワークレーン.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_tower"
RECORD = "タワークレーン.json"


def main(argv=None) -> int:
    import argparse

    from ashiba.tower import TOWERS, Placed, check, find, part_params, report

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", default="", help="機種（" + "・".join(TOWERS) + "）")
    ap.add_argument("--mast", type=float, default=0.0, help="マストの高さ m（基礎の上面から旋回輪の下。省くと機種の自立高さ）")
    ap.add_argument("--radius", type=float, default=0.0, help="作業半径 m（省くと最大作業半径の 6 割）")
    ap.add_argument("--jib", type=float, default=0.0, help="ジブの呼び m（省くと作業半径に届く一番短いもの）")
    ap.add_argument("--load", type=float, default=0.0, help="吊り荷 t（フック・玉掛け用具を含む。定格荷重の判定）")
    ap.add_argument("--ties", default="", help="壁つなぎの高さ mm（カンマ区切り）")
    ap.add_argument("--tie-dir", type=float, default=None, help="壁つなぎの向き 度（省くとジブの反対）")
    ap.add_argument("--tie-len", type=float, default=2.0, help="壁つなぎの長さ m（マストの面から建物まで）")
    ap.add_argument("--erect-radius", type=float, default=10.0, help="組立ての移動式クレーンの作業半径 m（帳票の機種選び）")
    ap.add_argument("--erect-mast", type=float, default=0.0, help="組み始めの高さ m（省くと最小クライミング寸法）")
    ap.add_argument("--z", type=float, default=None, help="基礎の上面の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--list", action="store_true", help="機種の一覧を出す")
    ap.add_argument("--remove", action="store_true", help="置いたタワークレーンを消す")
    a = ap.parse_args(argv)
    if a.list:
        for k, t in TOWERS.items():
            print(f"{k:8s} {t.name}（{t.model}）")
        return 0
    try:
        tw = find(a.type) if a.type else next(iter(TOWERS.values()))
    except KeyError as e:
        print(e.args[0])
        return 1

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, [v["guid"] for v in rec.values()])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"タワークレーン: {n}基を消しました")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("タワークレーン: 線（始め＝マストの芯・始めの辺の向き＝ジブの向き）を選んでから押してください")
        return 1
    spec = {**R.SPEC, **R.load_spec_override()}
    bnd = [tuple(map(float, p)) for p in (spec.get("site_boundary_mm") or [])]
    roads = {int(i) for i in (spec.get("road_edges") or [])}
    if not bnd:
        try:
            from ashiba.site_boundary import read_boundary_from_archicad
            from guide_lines import building_plan

            plan = building_plan([(0.0, 0.0)]) or {}
            bnd, roads = read_boundary_from_archicad(c, plan.get("outline_mm") or [])
        except Exception:  # noqa: BLE001 — 敷地境界が無くても置ける（判定だけ省く）
            bnd = []
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    ties = [float(v) for v in a.ties.replace("、", ",").split(",") if v.strip()]
    n0 = len(rec)
    placed = []
    for n, (key, pts) in enumerate(lines, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)["guid"]])
        (x0, y0), (x1, y1) = pts[0], pts[1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        tie_dir = a.tie_dir if a.tie_dir is not None else 180.0
        p = Placed(f"タワー{n0 + n}", tw, mast=a.mast or tw.free_h, radius=a.radius, load_t=a.load, jib=a.jib, ties_mm=ties,
                   tie_dir=tie_dir, tie_len=a.tie_len, origin=(x0, y0), heading=ang)
        check(p, bnd, roads)
        z = a.z if a.z is not None else (ground(x0, y0) if ground else 0.0)
        el = _place(c, part, (x0, y0), z, ang)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(p), **pens})
        rec[key] = {"guid": el["elementId"]["guid"], "type": tw.key, "name": p.name, "mast": p.mast, "radius": p.radius,
                    "load": a.load, "jib": p.jib, "ties": ties, "tie_dir": tie_dir, "tie_len": a.tie_len, "origin": [x0, y0], "heading": ang}
        bad = sorted({x.item for x in p.checks if x.status not in ("OK", "注意")})
        print(f"  {p.name}: {tw.name}（{tw.model}）マスト {p.mast:g}m" + (f" 要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    for v in rec.values():
        if v.get("type") in TOWERS:
            p = Placed(v["name"], TOWERS[v["type"]], mast=v["mast"], radius=v["radius"], load_t=v.get("load", 0.0), jib=v.get("jib", 0.0),
                       ties_mm=v.get("ties", []), tie_dir=v.get("tie_dir", 180.0), tie_len=v.get("tie_len", 2.0),
                       origin=tuple(v.get("origin", (0.0, 0.0))), heading=v.get("heading", 0.0))
            placed.append(check(p, bnd, roads))
    md = R.OUT_DIR / "タワークレーン.md"
    md.write_text(report(placed, a.erect_radius, a.erect_mast), encoding="utf-8")
    print(f"タワークレーン: {len(placed)}基（{md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
