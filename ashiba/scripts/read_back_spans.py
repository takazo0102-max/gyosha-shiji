"""Archicad 上でホットスポット編集したスパンを読み戻し、入力の span_overrides に落とす.

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

from ashiba.span_readback import match_edge, merge_overrides, overrides_from_readback  # noqa: E402
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


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    write = "--write" in sys.argv or apply
    plan_path = Path(args[0]) if args else _latest_plan()
    spec_path = Path(args[1]) if len(args) > 1 else SPEC_DEFAULT
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    c = ArchicadClient()
    # 足場ラインは plan.json の配置位置（原点）で見つける。スラブの選択や GUID は要らない
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    readbacks = []
    for e, d in zip(objs, c.get_details(objs) if objs else []):
        dd = d.get("details", {})
        lp = dd.get("libPart") or {}
        if not is_ashiba_part(lp.get("name", "") if isinstance(lp, dict) else "", ("ashiba_line",)):
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
    print(f"plan: {plan_path.name}  足場ライン {len(readbacks)}本を読み戻し")
    for w in warnings:
        print("注意:", w)
    if not overrides:
        print("配置時と同じ割付です（変更なし）")
        return 0
    for o in overrides:
        print(f"{o.get('face') or '辺' + str(o['edge_index'])}: {o['spans_mm']}")
    if not write:
        print("入力に書くには --write、続けて解き直すには --apply を付けてください")
        return 0
    spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
    spec = merge_overrides(spec, overrides)
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"書き込み: {spec_path}（span_overrides {len(spec['span_overrides'])}件）")
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
