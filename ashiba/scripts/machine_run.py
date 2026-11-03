"""重機（パレットの「重機」「重機を消す」）.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。

  python3 scripts/machine_run.py --type bh045            # 選んだ線の始め＝旋回中心（車は真ん中）、始めの辺の向き＝車体の前
  python3 scripts/machine_run.py --type pump36 --slew 90  # ブーム・上部を 90° 回す
  python3 scripts/machine_run.py --type cc50 --soil-q 150 --soil 3   # 地盤の許容支持力（短期 kN/m²）と土質（敷鉄板の表）
  python3 scripts/machine_run.py --type bh045 --att d135  # バックホウの先を解体アタッチメント（圧砕機）に（--att none でバケット）
  python3 scripts/machine_run.py --type lb4 --load 6.5,2.9,3.0,20   # 搬入車両に積荷（長さ,幅,高さ m,質量 t。高さ・総重量の判定に）
  python3 scripts/machine_run.py --type tr10 --turn 右     # 平面の旋回軌跡を右へ（--no-track で描かない）
  python3 scripts/machine_run.py --list                   # 機種の一覧（--list-att でアタッチメント）
  python3 scripts/machine_run.py --remove                 # 置いた重機を消す（--kinds 13,14 で搬入車両だけ）

部品 ashiba_machine を線1本に1台（src/ashiba/machine.py が機種・寸法・判定）。前に同じ線に置いたものは控え
（ashiba_out/重機.json）で消して置き直す。手配表と判定は ashiba_out/重機.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_machine"
RECORD = "重機.json"


def main(argv=None) -> int:
    import argparse

    from ashiba.machine import ATTACHMENTS, KEEP_OUT, MACHINES, SOIL_Q, SOILS, Placed, check, find, part_params, report

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", default="bh045", help="機種（" + "・".join(MACHINES) + "）")
    ap.add_argument("--slew", type=float, default=0.0, help="上部・ブームの旋回角（度。車体の前から左回り）")
    ap.add_argument("--soil-q", type=float, default=SOIL_Q, help="地盤の許容支持力（短期 kN/m²。地盤調査の値）")
    ap.add_argument("--soil", type=int, default=1, choices=list(SOILS),
                    help="土質（敷鉄板の表）: " + "・".join(f"{k} {v[0]}" for k, v in SOILS.items()))
    ap.add_argument("--keep-out", type=float, default=KEEP_OUT, help="立入禁止の余裕 m（公的な数値は無く社内の決め）")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--att", default=None, help="バックホウ・解体機の先（" + "・".join(ATTACHMENTS) + "・none＝バケット）")
    ap.add_argument("--list", action="store_true", help="機種の一覧を出す")
    ap.add_argument("--list-att", action="store_true", help="解体アタッチメントの一覧を出す")
    ap.add_argument("--remove", action="store_true", help="置いた重機を消す")
    ap.add_argument("--kinds", default="", help="--remove で消す種類（mcKind をカンマ区切り。空は全部）")
    ap.add_argument("--load", default="", help="搬入車両の積荷 長さ,幅,高さ m,質量 t")
    ap.add_argument("--turn", default="左", choices=("左", "右"), help="搬入車両の平面の旋回軌跡を描く側")
    ap.add_argument("--no-track", action="store_true", help="搬入車両の旋回軌跡を描かない")
    a = ap.parse_args(argv)
    if a.list:
        for k, m in MACHINES.items():
            print(f"{k:8s} {m.name}（{m.model}）")
        return 0
    if a.list_att:
        for k, v in ATTACHMENTS.items():
            print(f"{k:9s} {v[0]}（長さ {v[2]:g}m・{v[4]:,}kg）")
        return 0
    att = None if a.att is None else ("" if a.att == "none" else a.att)
    if att and att not in ATTACHMENTS:
        print(f"重機: アタッチメントは {'・'.join(ATTACHMENTS)} のどれか（{a.att}）")
        return 1
    try:
        mach = find(a.type)
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
        kinds = {int(k) for k in a.kinds.split(",") if k.strip()}
        gone = {k: v for k, v in rec.items() if not kinds or (v.get("type") in MACHINES and MACHINES[v["type"]].kind in kinds)}
        n = _delete_alive(c, [v["guid"] for v in gone.values()])
        rec_path.write_text(json.dumps({k: v for k, v in rec.items() if k not in gone}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"重機: {n}台を消しました")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("重機: 線（始め＝旋回中心・始めの辺の向き＝車体の前）を選んでから押してください")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    used = {v.get("name") for v in rec.values()}
    for key, pts in lines:
        name = None
        if key in rec:                               # 同じ線は前の名前のまま置き直す
            old = rec.pop(key)
            name = old.get("name")
            _delete_alive(c, [old["guid"]])
        if not name:
            name = next(f"重機{i}" for i in range(1, 10000) if f"重機{i}" not in used)
        used.add(name)
        (x0, y0), (x1, y1) = pts[0], pts[1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        extra = vehicle_extra(mach, a)
        p = check(Placed(name, mach, a.slew, params=extra, att=att if mach.kind in (1, 11) else None), a.soil_q, a.soil, a.keep_out)
        z = a.z if a.z is not None else (ground(x0, y0) if ground else 0.0)
        el = _place(c, part, (x0, y0), z, ang)
        if el is None:
            continue
        try:
            c.set_gdl_parameters(el, {**part_params(p), **pens})
        except Exception as ex:                       # 値が入らない部品は残さない（既定の形のまま残った。2026-11-03）
            _delete_alive(c, [el["elementId"]["guid"]])
            print(f"  {p.name}: パラメータを入れられず置きませんでした（{str(ex)[:120]}）")
            continue
        rec[key] = {"guid": el["elementId"]["guid"], "type": mach.key, "name": p.name, "slew": a.slew, "att": p.att, "params": extra}
        bad = sorted({x.item for x in p.checks if x.status not in ("OK", "注意")})
        print(f"  {p.name}: {mach.name}（{mach.model}）" + (f" 要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    placed = [check(Placed(v["name"], MACHINES[v["type"]], v.get("slew", 0.0), params=v.get("params") or {}, att=v.get("att")),
                    a.soil_q, a.soil, a.keep_out)
              for v in rec.values() if v.get("type") in MACHINES]
    md = R.OUT_DIR / "重機.md"
    md.write_text(report(placed, a.soil_q, a.soil), encoding="utf-8")
    print(f"重機: {len(placed)}台（{md}）")
    return 0


def vehicle_extra(mach, a) -> dict:
    """搬入車両（mcKind 13・14）の積荷と旋回軌跡のパラメータ（ほかの種類は空）."""
    if mach.kind not in (13, 14):
        return {}
    out = {"tkOn": 0 if a.no_track else 1, "tkS": 1 if a.turn == "左" else -1}
    if a.load:
        L, W, H, T = (float(v) for v in a.load.split(","))
        # トレーラーの積荷はキングピンから荷台の中心へ（低床は荷台、平床は前から、ポールは既定のまま）
        x = 0.0
        if mach.kind == 14:
            ps = mach.params
            x = {1: ps["tlF"] - ps["gnL"] - ps["dkL"] / 2, 2: ps["tlF"] - 0.3 - L / 2}.get(int(ps["tlK"]), ps.get("cgX", 0.0))
        out.update({"cgOn": 1, "cgL": L, "cgW": W, "cgH": H, "cgT": T, "cgX": x})
    return out


if __name__ == "__main__":
    sys.exit(main())
