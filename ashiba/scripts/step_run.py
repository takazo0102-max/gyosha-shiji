"""工程表に合わせた模型（パレットの「工程の模型を作る」「工程ステップ」「工程の模型を戻す」。利用者の指定 2026-11-04「工程表に合わせて
モデルを自動作成できるようにして」）.

工程表（scripts/schedule_run.py）が書いた ashiba_out/工程ステップ.json の節目ごとに、Archicad の模型をその日の姿にする:
- 「作る」（--make）: ashiba で置いた仮設を、作業ごとのレイヤー「仮設工程_仮囲い」「仮設工程_根切り」「仮設工程_構台」「仮設工程_外部足場」…
  に移す（もとのレイヤーは ashiba_out/工程模型.json に控える）。要素は控え（仮囲い.json・構台.json…の GUID）と、足場の部品は
  ライブラリ部品の名前（ashiba_line・ashiba_sheet…）で拾う
- 「ステップ」（--step N）: その節目に無い作業のレイヤーを隠し、外部足場はその日に組み上がった高さより上を描かない（部品の stepH。
  ashiba_line・ashiba_sheet）。--step 0 は全部を見せる
- 「戻す」（--undo）: 要素をもとのレイヤーに戻し、足場の高さを全部に、仮設工程のレイヤーを見せる

  python3 scripts/step_run.py --list          # 節目の一覧
  python3 scripts/step_run.py --make          # レイヤーに分ける
  python3 scripts/step_run.py --step 6        # 6 番めの節目（地上躯体 1階など）の姿
  python3 scripts/step_run.py --next          # 次の節目へ（--prev で前へ）
  python3 scripts/step_run.py --undo
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT_DIR = Path.home() / "Desktop" / "ashiba_out"
STEPS = "工程ステップ.json"
MODEL = "工程模型.json"
GUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", re.I)
CUT_PARTS = ("ashiba_line", "ashiba_sheet")          # stepH を持つ部品


def guids_in(v) -> list[str]:
    """控えの JSON の値の中の GUID（鍵は線の GUID のことがあるので値だけ）."""
    out = []
    if isinstance(v, str) and GUID.match(v):
        out.append(v.upper())
    elif isinstance(v, dict):
        for x in v.values():
            out += guids_in(x)
    elif isinstance(v, list):
        for x in v:
            out += guids_in(x)
    return out


def groups_of(out: Path, objects: list[tuple[str, str]]) -> dict[str, str]:
    """GUID → 仮設工程のレイヤー名. objects は (GUID, ライブラリ部品の基本名)."""
    from ashiba.schedule_steps import GROUP_TASKS, SCAFFOLD_PARTS

    found = {}
    for name, (layer, _u, _d) in GROUP_TASKS.items():
        if name.startswith("@"):
            continue
        try:
            v = json.loads((out / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for g in guids_in(v):
            found.setdefault(g, layer)
    sc = GROUP_TASKS["@足場"][0]
    for g, base in objects:
        if base in SCAFFOLD_PARTS:
            found.setdefault(g.upper(), sc)
    return found


def state_of(step: dict, layer: str) -> str:
    return step["layers"].get(layer, "なし")


def main(argv=None) -> int:
    import argparse

    from ashiba.pens import part_base
    from ashiba.schedule_steps import LAYERS
    from ashiba.tapir_adapter import ArchicadClient

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--step", type=int, default=None)
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--prev", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args(argv)
    out = Path(a.out)
    try:
        sd = json.loads((out / STEPS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("工程の模型: 先に「工程表」（scripts/schedule_run.py）で工程ステップを作ってください")
        return 1
    steps = sd.get("steps") or []
    if a.list or not (a.make or a.undo or a.next or a.prev or a.step is not None):
        for s in steps:
            on = "・".join(k.replace("仮設工程_", "") + ("（作業中）" if v == "作業中" else "")
                          for k, v in s["layers"].items() if v != "なし")
            print(f"  {s['no']:2d} {s['date']} {s['name']}: {on or '仮設なし'}" + (f"・足場 {s['scaffold_h']:.1f}m" if s["scaffold_h"] else ""))
        return 0
    c = ArchicadClient()
    mpath = out / MODEL
    try:
        model = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        model = {}
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    dets = c.get_details(objs) if objs else []
    info = {}
    for e, d in zip(objs, dets):
        lp = (d.get("details", {}).get("libPart") or {})
        info[e["elementId"]["guid"].upper()] = (part_base(lp.get("name", "") if isinstance(lp, dict) else ""), d)
    stories = {int(s.get("index", 0)): float(s.get("level", 0) or 0)
               for s in (c.tapir("GetStories", {}).get("stories") or [])}

    def layer_index() -> dict[str, int]:
        attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        return {x.get("name"): int(x["index"]) for x in attrs}

    def show(hidden: dict[str, bool]) -> None:
        c.tapir("CreateLayers", {"layerDataArray": [{"name": n, "isHidden": bool(h)} for n, h in hidden.items()],
                                 "overwriteExisting": True})

    def cut(h: float | None) -> int:
        """足場の部品（stepH を持つもの）に、組み上がった高さ h m（全体の足場の下端から）を入れる. None は全部."""
        parts = [(g, d) for g, (b, d) in info.items() if b in CUT_PARTS and model.get("elements", {}).get(g)]
        if not parts:
            return 0
        z = {g: stories.get(int(d.get("floorIndex", 0)), 0.0) + float((d.get("details", {}).get("origin") or {}).get("z", 0))
             for g, d in parts}
        base = min(z.values())
        pairs = [({"elementId": {"guid": g}}, {"stepH": 0.0 if h is None else max(0.001, base + h - z[g])}) for g, _d in parts]
        return c.set_gdl_parameters_many(pairs)

    if a.make:
        found = groups_of(out, [(g, b) for g, (b, _d) in info.items()])
        show({n: False for n in LAYERS})
        li = layer_index()
        els = model.setdefault("elements", {})
        moves = []
        dets_all = {}
        others = [g for g in found if g not in info]          # オブジェクト以外（メッシュ・塗り・線・梁）
        try:
            dets_all = dict(zip(others, c.get_details([{"elementId": {"guid": g}} for g in others]))) if others else {}
        except Exception:                                    # 消えた要素があるとまとめて失敗するので1つずつ（消えたものは飛ばす）
            for g in others:
                try:
                    dets_all[g] = c.get_details([{"elementId": {"guid": g}}])[0]
                except Exception:
                    pass
        for g, lay in found.items():
            d = info[g][1] if g in info else dets_all.get(g)
            if not d or "layerIndex" not in d:
                continue
            if g not in els:
                els[g] = {"layer": int(d["layerIndex"]), "group": lay}
            moves.append({"elementId": {"guid": g}, "details": {"layerIndex": li[lay]}})
        if moves:
            c.tapir("SetDetailsOfElements", {"elementsWithDetails": moves})
        mpath.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
        by = {}
        for v in els.values():
            by[v["group"]] = by.get(v["group"], 0) + 1
        print("工程の模型: " + "・".join(f"{k.replace('仮設工程_', '')} {n}" for k, n in by.items()) + " をレイヤーに分けました")
        return 0
    if a.undo:
        els = model.get("elements", {})
        back = [{"elementId": {"guid": g}, "details": {"layerIndex": v["layer"]}} for g, v in els.items()]
        if back:
            try:
                c.tapir("SetDetailsOfElements", {"elementsWithDetails": back})
            except Exception as ex:                         # 消えた要素があると全部が失敗するので1つずつ
                print(f"  注意: まとめて戻せませんでした（{ex}）。1つずつ戻します")
                for b in back:
                    try:
                        c.tapir("SetDetailsOfElements", {"elementsWithDetails": [b]})
                    except Exception:
                        pass
        cut(None)
        show({n: False for n in LAYERS})
        mpath.write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")
        print(f"工程の模型: {len(back)} 個をもとのレイヤーに戻しました")
        return 0
    if not model.get("elements"):
        print("工程の模型: 先に「工程の模型を作る」（--make）でレイヤーに分けてください")
        return 1
    cur = int(model.get("step", 0) or 0)
    n = a.step if a.step is not None else min(len(steps), cur + 1) if a.next else max(0, cur - 1)
    if n == 0:
        show({x: False for x in LAYERS})
        cut(None)
        model["step"] = 0
        mpath.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
        print("工程の模型: 全部を見せました")
        return 0
    if not 1 <= n <= len(steps):
        print(f"工程の模型: ステップは 1〜{len(steps)}")
        return 1
    s = steps[n - 1]
    show({x: state_of(s, x) == "なし" for x in LAYERS})
    k = cut(s["scaffold_h"] if s["scaffold_h"] else None)
    model["step"] = n
    mpath.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
    on = "・".join(x.replace("仮設工程_", "") + ("（作業中）" if state_of(s, x) == "作業中" else "")
                  for x in LAYERS if state_of(s, x) != "なし")
    print(f"工程の模型: ステップ {n}/{len(steps)} {s['date']} {s['name']}: {on or '仮設なし'}"
          + (f"・足場 {s['scaffold_h']:.1f}m まで（{k} 部品）" if s["scaffold_h"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
