"""Archicad 上でホットスポット編集したスパンを読み戻し、入力の span_overrides に落とす.

足場ラインの平面で支柱位置のホットスポットを引くと、部品が規格寸法に吸着して spanList を
書き戻す。このスクリプトは配置時の plan.json と突き合わせ、変わった面を span_overrides に
して ashiba_spec.json（ツールバーの条件ファイル）へ書く。次にツールバーを実行すると、
その割付のまま壁つなぎ・数量・法規・帳票が解き直される。

使い方:
  python3 scripts/read_back_spans.py [plan.json] [--write [spec.json]]
  plan.json 省略時は ~/Desktop/ashiba_out の最新。--write 省略時は表示だけ。
  スラブは選択中のもの、または環境変数 ASHIBA_SLAB=<GUID先頭>
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.span_readback import merge_overrides, overrides_from_readback  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    ArchicadClient,
    get_selected_outline_mm,
    slab_outline_mm_by_guid,
)

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
    write = "--write" in sys.argv
    plan_path = Path(args[0]) if args else _latest_plan()
    spec_path = Path(args[1]) if len(args) > 1 else SPEC_DEFAULT
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    c = ArchicadClient()
    guid = os.environ.get("ASHIBA_SLAB", "").strip()
    outline = slab_outline_mm_by_guid(c, guid) if guid else get_selected_outline_mm(c)
    readbacks = []
    for e, d in zip(*(lambda els: (els, c.get_details(els)))(c.objects_for_slab(outline))):
        dd = d["details"]
        if not dd["libPart"]["name"].startswith("ashiba_line"):
            continue
        p = _params(c, e)
        if p.get("viewMode") != "plan":
            continue
        o = dd["origin"]
        readbacks.append(((o["x"] * 1000.0, o["y"] * 1000.0), p))
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
    if write:
        spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
        spec = merge_overrides(spec, overrides)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"書き込み: {spec_path}（span_overrides {len(spec['span_overrides'])}件）。次にツールバーを実行すると解き直します")
    else:
        print("入力に書くには --write を付けてください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
