"""乗入れ構台・荷取り構台（パレットの「乗入れ構台」）.

開発ループ（2026-11-01）: 前に挙げた「他に必要な仮設材」の2番。

  python3 scripts/kodai_run.py                          # 選んだ線・ポリラインの範囲（始めの辺＝進行方向）に構台
  python3 scripts/kodai_run.py --vehicle R65 --load 5   # 重機（T25・R20・R25・R40・R65・C50）と吊荷 t
  python3 scripts/kodai_run.py --depth 6300 --embed 4700 --top 500 --n-value 30
  python3 scripts/kodai_run.py --deck3 1 --span 5000 --rails SNE --slope 8 --nitori   # 荷取り構台（手すりは既定で4辺）
  python3 scripts/kodai_run.py --recheck                # 置いた構台を、ホットスポットで動かした支柱・大引・水平つなぎの位置と
                                                        # 選んだ H形鋼で検定し直す（パレットの「構台の検定」）
  python3 scripts/kodai_run.py --remove                 # 置いた構台を消す

部品 ashiba_kodai を構台に1つ（src/ashiba/kodai.py が割付・検定・数量）。前に同じ線に置いたものは控え（ashiba_out/構台.json）で
消して置き直す。帳票は ashiba_out/構台.md（組立図の部材表として使える）.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_kodai"
RECORD = "構台.json"


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.kodai import VEHICLES, kodai_plan, part_params, plan_from_params, report
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains
    from plate_run import extent

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vehicle", default="R25", choices=list(VEHICLES), help="載る一番重い重機")
    ap.add_argument("--load", type=float, default=3.0, help="吊荷 t")
    ap.add_argument("--width", type=float, default=8000.0, help="線1本のときの幅 mm（既定 8,000）")
    ap.add_argument("--deck3", type=int, default=-1, help="3m の覆工板の列の数（省くと自動: 幅が奇数 m なら1列、ほかは 2m）")
    ap.add_argument("--deck3-at", type=int, default=1, help="3m の列を入れる位置（手前から何列目）")
    ap.add_argument("--span", type=float, default=6000.0, help="支柱の間隔の上限 mm")
    ap.add_argument("--ovh", type=float, default=1000.0, help="張出し mm")
    ap.add_argument("--top", type=float, default=500.0, help="床の上端 mm（地盤から）")
    ap.add_argument("--depth", type=float, default=6000.0, help="根切り底 mm（地盤から下へ）")
    ap.add_argument("--embed", type=float, default=4700.0, help="支柱の根入れ mm（根切り底から下へ）")
    ap.add_argument("--n-value", type=float, default=20.0, help="支柱の先の N 値（砂質土）")
    ap.add_argument("--slope", type=float, default=8.0, help="入口のスロープ 1/n（0＝なし）")
    ap.add_argument("--rails", default=None, help="手すりの辺 S・N・E・W（既定は乗入れ SNE・荷取り SNEW）")
    ap.add_argument("--nitori", action="store_true", help="荷取り構台（手すり4辺・スロープなし）")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--recheck", action="store_true", help="置いた構台を部品の今の形（動かした位置・H形鋼）で検定し直す")
    ap.add_argument("--remove", action="store_true", help="置いた構台を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        n = _delete_alive(c, list(rec.values()))
        rec_path.write_text("{}", encoding="utf-8")
        print(f"構台: {n}個を消しました")
        return 0
    if a.recheck:
        alive = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])}
        plans = []
        for n, g in enumerate([g for g in rec.values() if g in alive], 1):
            el = {"elementId": {"guid": g}}
            it = c.tapir("GetGDLParametersOfElements", {"elements": [el]})["gdlParametersOfElements"][0]
            ps = {x["name"]: x.get("value") for x in it.get("gdlParameters", it.get("parameters", []))}
            p = plan_from_params(ps, f"構台{n}")
            c.set_gdl_parameters(el, {"maxLd": f"最大積載荷重 {p.max_load_t:g}t"})
            plans.append(p)
            ng = [x.item for x in p.checks if x.status != "OK"]
            print(f"  {p.name}: 支柱 {len(p.xs)}×{len(p.ys)}（{p.post}）・根太 {p.joist}・大引 {p.girder}・水平つなぎ {len(p.levels)}段"
                  + (f"・要確認 {'・'.join(ng)}" if ng else "・検定 OK"))
        if not plans:
            print("構台の検定: 置いた構台がありません（先に「乗入れ構台」で置く）")
            return 1
        md = R.OUT_DIR / "構台.md"
        md.write_text(report(plans), encoding="utf-8")
        print(f"構台の検定: {len(plans)}か所（{md}）")
        return 0
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("構台: 構台の範囲の線（ポリライン・線。始めの辺＝進行方向）を選んでから押してください")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    kind = "荷取り構台" if a.nitori else "乗入れ構台"
    rails = a.rails if a.rails is not None else ("SNEW" if a.nitori else "SNE")
    plans = []
    for n, (key, pts) in enumerate(lines, 1):
        if key in rec:
            _delete_alive(c, [rec.pop(key)])
        corner, lx, ly, ang = extent(pts, a.width)
        p = kodai_plan(f"構台{n}", lx, ly, a.vehicle, a.load, a.n_value, n3=a.deck3, n3_at=a.deck3_at, sp_max=a.span, ov=a.ovh,
                       top=a.top, depth=a.depth, embed=a.embed, slope=0.0 if a.nitori else a.slope, rails=rails.upper(),
                       kind=kind)
        z = a.z if a.z is not None else (ground(*corner) if ground else 0.0)
        el = _place(c, part, corner, z, ang)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(p), **pens})
        rec[key] = el["elementId"]["guid"]
        plans.append(p)
        ng = [x.item for x in p.checks if x.status == "NG"]
        print(f"  構台{n}: {p.length / 1000:g}×{p.width / 1000:g}m・支柱 {len(p.xs)}×{len(p.ys)}・水平つなぎ {len(p.levels)}段"
              + (f"・NG {'・'.join(ng)}" if ng else "・検定 OK"))
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "構台.md"
    md.write_text(report(plans), encoding="utf-8")
    print(f"構台: {len(plans)}か所に置きました（検定・数量: {md}）。ホットスポットで広げられます")
    return 0


if __name__ == "__main__":
    sys.exit(main())
