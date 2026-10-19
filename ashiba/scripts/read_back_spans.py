"""Archicad 上でホットスポット編集したスパンと階段室の位置（と、動かした壁つなぎの部品）を読み戻し、入力に落とす.

スパン → span_overrides、階段室（建地列の中央のホットスポット）→ stairs.positions、
荷受けステージ・昇降機（張り出し床・搬器の中央）→ loading_stages・hoists の位置、
足場の高さ（3D の天端のホットスポット）→ 足場条件の部品の足場高さ（部品が無ければ scaffold_height_mm）。

足場ラインの平面で支柱位置のホットスポットを引くと、部品が規格寸法に吸着して spanList を
書き戻す。このスクリプトは配置時の plan.json と突き合わせ、変わった面を span_overrides に
して ashiba_spec.json（ツールバーの条件ファイル）へ書く。次にツールバーを実行すると、
その割付のまま壁つなぎ・数量・法規・帳票が解き直される。

使い方:
  python3 scripts/read_back_spans.py [plan.json] [--write [spec.json]] [--apply]
  plan.json 省略時は ~/Desktop/ashiba_out の最新。--write 省略時は表示だけ。
  --apply は --write のあと続けてツールバー（run_from_archicad.py）を実行して解き直す
  （スラブは選択中のもの、または ASHIBA_SLAB=<GUID先頭>）。
  足場ラインは plan.json の配置位置で見つけるので、スラブの選択や GUID は読み戻しには要らない。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.span_readback import (  # noqa: E402
    height_from_readback,
    match_edge,
    merge_overrides,
    merge_platform_moves,
    merge_stairs,
    overrides_from_readback,
    platform_moves_from_readback,
    ties_from_readback,
    stair_positions_from_readback,
)
from ashiba.tapir_adapter import ArchicadClient, is_ashiba_part  # noqa: E402

OUT_DIR = Path.home() / "Desktop" / "ashiba_out"
SPEC_DEFAULT = Path.home() / "Desktop" / "ashiba_spec.json"


def _latest_plan() -> Path:
    cands = sorted(OUT_DIR.glob("*_plan.json"), key=lambda p: p.stat().st_mtime)
    if not cands:
        raise SystemExit(f"plan.json がありません: {OUT_DIR}（先にツールバーで配置してください）")
    return cands[-1]


def _params(client: ArchicadClient, element: dict) -> dict:
    resp = client.tapir("GetGDLParametersOfElements", {"elements": [element]})
    out = {}
    for item in resp.get("gdlParametersOfElements", []):
        for row in item.get("gdlParameters", item.get("parameters", [])):
            out[row.get("name")] = row.get("value")
    return out


def _write_height(client: ArchicadClient, plan: dict, spec: dict, height_mm: int) -> str:
    """足場高さを書く先: 足場条件の部品があればその「足場高さ」（JSON より優先される）、無ければ JSON."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_from_archicad as tb
    from ashiba.spec_object import pick_spec_object

    hit = None
    try:
        hit = pick_spec_object(tb.read_spec_objects(client), plan.get("outline_mm") or [])
    except Exception:          # 部品が読めなくても JSON に書けば解き直しは通る
        hit = None
    if hit is not None and hit[1]:
        try:
            client.set_gdl_parameters(hit[0], {"scaffH": height_mm / 1000.0})
            return "足場条件の部品"
        except Exception as e:
            print(f"注意: 足場条件の部品に高さを書けませんでした（{e}）。JSON に書きます")
    spec["scaffold_height_mm"] = int(height_mm)
    return "ashiba_spec.json"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    write = "--write" in sys.argv or apply
    plan_path = Path(args[0]) if args else _latest_plan()
    spec_path = Path(args[1]) if len(args) > 1 else SPEC_DEFAULT
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    c = ArchicadClient()
    from ashiba.elevation_sections import activate_floor_plan
    activate_floor_plan(c)           # 足場ラインは平面図のデータベースにある
    # 足場ラインは plan.json の配置位置（原点）で見つける。スラブの選択や GUID は要らない
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    readbacks = []
    tie_els = []
    for e, d in zip(objs, c.get_details(objs) if objs else []):
        dd = d.get("details", {})
        lp = dd.get("libPart") or {}
        lp_name = lp.get("name", "") if isinstance(lp, dict) else ""
        if is_ashiba_part(lp_name, ("ashiba_tie",)):
            tie_els.append((e, dd.get("origin") or {}))
            continue
        if not is_ashiba_part(lp_name, ("ashiba_line",)):
            continue
        o = dd.get("origin") or {}
        origin = (float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0)
        if match_edge(plan["edges"], origin) is None:
            continue
        p = _params(c, e)
        if p.get("viewMode") != "plan":
            continue
        readbacks.append((origin, p))
    if not readbacks:
        print(f"plan: {plan_path.name} の配置位置に足場ラインがありません。先にツールバーで配置してください"
              "（別の建物の plan.json を見ているなら、そのファイルを引数で指定）")
        return 1
    # 規格寸法は部品が吸着に使う sizeList（系列の布材）。配置時のスパンだけだと 1500 等が規格外扱いになる
    allowed = {int(v) for e in plan["edges"] for v in e.get("spans") or []}
    for _, p in readbacks:
        allowed |= {int(float(t)) for t in str(p.get("sizeList") or "").split(",") if t.strip()}
    overrides, warnings = overrides_from_readback(plan["edges"], readbacks, allowed)
    towers = (plan.get("stairs") or {}).get("towers") or []
    stair_pos, stair_notes = stair_positions_from_readback(plan["edges"], towers, readbacks)
    stage_moves, hoist_moves, pf_notes = platform_moves_from_readback(plan["edges"], plan.get("platforms"), readbacks)
    stair_notes += pf_notes
    new_height, height_notes = height_from_readback(plan, readbacks)
    stair_notes += height_notes
    # 壁つなぎの部品（動かした・消した・コピーで足した）。取付高さ＝部品の高さ＋zH
    tie_pts = []
    for e, o in tie_els:
        zh = float(_params(c, e).get("zH") or 0.0)
        tie_pts.append((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0,
                        (float(o.get("z", 0)) + zh) * 1000.0))
    ties, tie_notes = ties_from_readback(plan["edges"], tie_pts, plan.get("wall_ties") or [],
                                         float(plan.get("base_height_mm") or 0.0))
    stair_notes += tie_notes
    print(f"plan: {plan_path.name}  足場ライン {len(readbacks)}本を読み戻し")
    for w in warnings:
        print("注意:", w)
    if not overrides and stair_pos is None and not stage_moves and not hoist_moves and new_height is None \
            and ties is None:
        for n in stair_notes:
            print("注意:", n)
        print("配置時と同じ割付・階段・ステージ・昇降機の位置・足場高さ・壁つなぎです（変更なし）")
        return 0
    for o in overrides:
        print(f"{o.get('face') or '辺' + str(o['edge_index'])}: {o['spans_mm']}")
    for n in stair_notes:
        print(n)
    if not write:
        print("入力に書くには --write、続けて解き直すには --apply を付けてください")
        return 0
    spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
    if overrides:
        spec = merge_overrides(spec, overrides)
    if stair_pos is not None:
        spec = merge_stairs(spec, stair_pos)
    if stage_moves or hoist_moves:
        spec, merge_notes = merge_platform_moves(spec, plan["edges"], stage_moves, hoist_moves)
        for n in merge_notes:
            print("注意:", n)
    what = []
    if ties is not None:
        spec["wall_ties_manual"] = ties
        what.append(f"wall_ties_manual {len(ties)}本")
    if new_height is not None:
        where = _write_height(c, plan, spec, new_height)
        what.append(f"足場高さ {new_height}mm（{where}）")
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if overrides:
        what.append(f"span_overrides {len(spec['span_overrides'])}件")
    if stair_pos is not None:
        what.append(f"stairs.positions {len(stair_pos)}箇所")
    if stage_moves:
        what.append(f"loading_stages の位置 {len(stage_moves)}件")
    if hoist_moves:
        what.append(f"hoists の位置 {len(hoist_moves)}件")
    print(f"書き込み: {spec_path}（{'・'.join(what)}）")
    if not apply:
        print("次にツールバーを実行すると解き直します")
        return 0
    # 続けて解き直す（ツールバーと同じ入口。条件ファイルは今書いたもの）
    os.environ["ASHIBA_SPEC"] = str(spec_path)
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_from_archicad

    outline = plan.get("outline_mm")
    if not outline:
        print("この plan.json には躯体外形がありません（古い版の配置）。スラブを選択してツールバーを実行してください")
        return 1
    print("---- ツールバーを実行して解き直します（plan.json の躯体外形を使うので、スラブの選択は要りません）")
    run_from_archicad.main(outline_mm=outline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
