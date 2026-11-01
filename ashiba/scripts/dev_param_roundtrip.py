"""実機検証: 重機・タワークレーン・ラフタークレーンの全機種を置き、入れたパラメータと部品に残った値を比べる.

Tapir の SetGDLParametersOfElements はパラメータを1つずつ入れ、そのたびに部品のパラメータスクリプトを走らせる。
脚の吸い付きのような書き戻しが、まだ入っていない古い値で走ると、入れた値が部品に残らない（2026-11-02 実機でクレーンの
脚 3.8m が既定の 25t の段の 3.3m になった）。食い違いは「名前 入れた値 残った値」で出す。置いた部品は最後に GUID で消す。

  python3 scripts/dev_param_roundtrip.py                       # 利用者の建物（x≈-3327m・y≈-2000m）の 260m 南に並べる
  python3 scripts/dev_param_roundtrip.py --at x,y --only crane # 位置（mm）と部品（machine・tower・crane）を選ぶ
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def mismatches(sent: dict, got: dict) -> list[tuple]:
    """入れた値と残った値の食い違い。角度は Tapir がラジアンで返すので度でも見る。文字は 255 字で切れる."""
    bad = []
    for k, v in sent.items():
        g = got.get(k)
        if isinstance(v, bool) or isinstance(g, bool):
            ok = bool(v) == bool(g)
        elif isinstance(v, (int, float)) and isinstance(g, (int, float)):
            ok = abs(v - g) < 1e-4 or abs(math.radians(v) - g) < 1e-4
        else:
            ok = str(v)[:255] == str(g)
        if not ok:
            bad.append((k, v, g))
    return bad


def cases(only: set[str]):
    """(部品, 機種, 先に入れる値, 全部の値, 後で入れる値)。クレーンは crane_run と同じ3回に分けて入れる."""
    from ashiba import crane as CR
    from ashiba import machine as MC
    from ashiba import tower as TW

    if "machine" in only:
        for k, m in MC.MACHINES.items():
            yield "ashiba_machine", k, None, MC.part_params(MC.Placed(k, m)), None
    if "tower" in only:
        for k, t in TW.TOWERS.items():
            yield "ashiba_tower", k, None, TW.part_params(t), None
    if "crane" in only:
        for k in CR.MODELS:
            p = CR.crane_plan("試験", [CR.Lift("吊り荷1", 8000.0, 1.0, 10000.0)], k, None, CR.SOIL_Q, CR.LOAD_RATIO)
            yield "ashiba_crane", k, {"oSnap": False}, CR.part_params(p, 30.0), {"oSnap": True}


def main(argv=None) -> int:
    import argparse

    import run_from_archicad as R
    from ashiba.tapir_adapter import ArchicadClient
    from excav_run import _delete_alive, _place

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--at", default="-3327000,-2260000", help="1台目の位置 mm（2台目からは +X へ 30m おき）")
    ap.add_argument("--only", default="machine,tower,crane", help="machine・tower・crane をカンマ区切り")
    a = ap.parse_args(argv)
    x0, y0 = (float(v) for v in a.at.split(","))
    c = ArchicadClient()
    R.ensure_parts(c)
    made, n_bad = [], 0
    try:
        for i, (base, key, pre, ps, post) in enumerate(cases(set(a.only.split(",")))):
            el = _place(c, R.versioned_part_name(base), (x0 + 30000.0 * i, y0), 0.0, 0.0)
            if el is None:
                print(f"{base} {key}: 置けませんでした")
                n_bad += 1
                continue
            made.append(el["elementId"]["guid"])
            for q in (pre, ps, post):
                if q:
                    c.set_gdl_parameters(el, q, base)
            r = c.get_gdl_parameters(el)
            got = {q["name"]: q.get("value") for q in r["gdlParametersOfElements"][0]["parameters"]}
            bad = mismatches({**ps, **(post or {})}, got)
            n_bad += bool(bad)
            print(f"{base} {key}: " + ("OK" if not bad else "  ".join(f"{k} {v}→{g}" for k, v, g in bad)))
    finally:
        print(f"置いた {len(made)}台を消しました（{_delete_alive(c, made)}）")
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
