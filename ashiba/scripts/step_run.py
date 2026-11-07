"""工程表に合わせた模型（パレットの「工程の模型を作る」「工程ステップ」「工程の模型を戻す」。利用者の指定 2026-11-04「工程表に合わせて
モデルを自動作成できるようにして」）.

工程表（scripts/schedule_run.py）が書いた ashiba_out/工程ステップ.json の節目ごとに、Archicad の模型をその日の姿にする:
- 「作る」（--make）: ashiba で置いた仮設を、作業ごとのレイヤー「仮設工程_仮囲い」「仮設工程_根切り」「仮設工程_構台」「仮設工程_外部足場」…
  に移す（もとのレイヤーは ashiba_out/工程模型.json に控える）。要素は控え（仮囲い.json・構台.json…の GUID）と、足場の部品は
  ライブラリ部品の名前（ashiba_line・ashiba_sheet…）で拾う
- 「ステップ」（--step N）: その節目に無い作業のレイヤーを隠し、外部足場はその日に組み上がった高さより上を描かない（部品の stepH。
  ashiba_line・ashiba_sheet と scripts/gdl_step.py で足した壁つなぎ・ネット・渡りなど。前の版で置いた部品は持たないので切れない。
  高さの基準は建物ごと（部品を近さでまとめた中の一番低い所）。--step 0 は全部を見せる
- 「戻す」（--undo）: 要素をもとのレイヤーに戻し、足場の高さを全部に、仮設工程のレイヤーを見せる

  python3 scripts/step_run.py --list          # 節目の一覧
  python3 scripts/step_run.py --make          # レイヤーに分ける
  python3 scripts/step_run.py --step 6        # 6 番めの節目（地上躯体 1階など）の姿
  python3 scripts/step_run.py --next          # 次の節目へ（--prev で前へ）
  python3 scripts/step_run.py --undo
"""

from __future__ import annotations

import os
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "ashiba_out"))  # 試験は ASHIBA_OUT で別の場所に
STEPS = "工程ステップ.json"
MODEL = "工程模型.json"
GUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", re.I)
NEAR_M = 30.0                                        # 足場の部品をひとつの建物にまとめる距離（原点どうし m）


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


def clusters(xy: dict[str, tuple[float, float]], near: float = NEAR_M) -> list[list[str]]:
    """原点が near m 以内でつながる部品の組（建物ごとの足場）."""
    keys = list(xy)
    parent = {k: k for k in keys}

    def root(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    cell = {}
    for k in keys:                                   # 升目で近くだけ比べる
        x, y = xy[k]
        cell.setdefault((int(x // near), int(y // near)), []).append(k)
    for (i, j), ks in cell.items():
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for k2 in cell.get((i + di, j + dj), []):
                    for k in ks:
                        if k < k2 and (xy[k][0] - xy[k2][0]) ** 2 + (xy[k][1] - xy[k2][1]) ** 2 <= near * near:
                            parent[root(k)] = root(k2)
    out = {}
    for k in keys:
        out.setdefault(root(k), []).append(k)
    return list(out.values())


def state_of(step: dict, layer: str) -> str:
    return step["layers"].get(layer, "なし")


def main(argv=None) -> int:
    import argparse

    from ashiba.pens import part_base
    from ashiba.schedule_steps import LAYERS, SCAFFOLD_PARTS
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

    def move(changes: list[dict]) -> list[str]:
        """要素のレイヤーを変える. 戻り値は変えられなかった要素の GUID（もう無い要素は除く。
        隠したレイヤーの要素は変えられないので、先に全部を見せておく）.

        まとめて送ると1つでも消えた要素があれば全部が失敗するので、そのときは1つずつ。要素ごとの失敗も数える
        （2026-11-05 の試験で、隠したレイヤーの 9 個が黙って戻らなかった）.
        """
        if not changes:
            return []
        try:
            res = (c.tapir("SetDetailsOfElements", {"elementsWithDetails": changes}) or {}).get("executionResults") or []
            bad = [ch for ch, r in zip(changes, res) if isinstance(r, dict) and r.get("success") is False]
        except Exception:
            bad = []
            for ch in changes:
                try:
                    res = (c.tapir("SetDetailsOfElements", {"elementsWithDetails": [ch]}) or {}).get("executionResults") or []
                    bad += [ch] if any(isinstance(r, dict) and r.get("success") is False for r in res) else []
                except Exception:
                    bad.append(ch)
        alive = []
        for ch in bad:
            try:
                if "error" not in c.get_details([{"elementId": ch["elementId"]}])[0]:
                    alive.append(ch["elementId"]["guid"])
            except Exception:
                pass
        return alive

    def cut(h: float | None) -> tuple[int, int]:
        """外部足場の部品に、組み上がった高さ h m（その建物の足場の下端から）を入れる. None は全部.

        stepH を持つ部品だけ（前の版で置いた部品は持たない）。建物ごとの足場の下端は、部品を近さでまとめた中の一番低い所.
        戻り値は (入れた数, stepH を持たず切れない数).
        """
        parts = [(g, d) for g, (b, d) in info.items() if b in SCAFFOLD_PARTS and model.get("elements", {}).get(g)]
        if not parts:
            return 0, 0
        has = []
        for i in range(0, len(parts), 200):
            got = c.tapir("GetGDLParametersOfElements", {"elements": [{"elementId": {"guid": g}} for g, _d in parts[i:i + 200]]})
            has += [any(p.get("name") == "stepH" for p in (r.get("parameters") or r.get("gdlParameters") or []))
                    for r in got.get("gdlParametersOfElements", [])]
        ok = [(g, d) for (g, d), y in zip(parts, has) if y]
        if not ok:
            return 0, len(parts)
        z, xy = {}, {}
        for g, d in ok:
            o = d.get("details", {}).get("origin") or {}
            z[g] = stories.get(int(d.get("floorIndex", 0)), 0.0) + float(o.get("z", 0))
            xy[g] = (float(o.get("x", 0)), float(o.get("y", 0)))
        base = {g: min(z[k] for k in grp) for grp in clusters(xy) for g in grp}
        pairs = [({"elementId": {"guid": g}}, {"stepH": 0.0 if h is None else max(0.001, base[g] + h - z[g])}) for g, _d in ok]
        return c.set_gdl_parameters_many(pairs), len(parts) - len(ok)

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
        bad = move(moves)
        mpath.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
        by = {}
        for v in els.values():
            by[v["group"]] = by.get(v["group"], 0) + 1
        if not by:                                           # 「工程の模型:  をレイヤーに分けました」と空で出ていた（2026-11-07 ループ）
            print("工程の模型: 分ける仮設がありません（先に足場・仮囲い・構台などを置いてから押してください）")
            return 1
        print("工程の模型: " + "・".join(f"{k.replace('仮設工程_', '')} {n}" for k, n in by.items()) + " をレイヤーに分けました"
              + (f"（注意: {len(bad)}個はレイヤーを変えられませんでした。固定・隠したレイヤーにないか確かめてください）" if bad else ""))
        return 0
    if a.undo:
        els = model.get("elements", {})
        back = [{"elementId": {"guid": g}, "details": {"layerIndex": v["layer"]}} for g, v in els.items()]
        show({n: False for n in LAYERS})                    # 隠したレイヤーの要素は動かせないので、先に見せる
        cut(None)
        bad = move(back)
        if bad:                                             # 戻せなかったものだけ控えに残し、もう一度「戻す」で戻せるように
            model["elements"] = {g: v for g, v in els.items() if g in bad}
            mpath.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"工程の模型: {len(back) - len(bad)} 個をもとのレイヤーに戻しました（{len(bad)}個は戻せませんでした。"
                  "もう一度「工程の模型を戻す」を押すか、固定したレイヤーがないか確かめてください）")
            return 2
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
    k, old = cut(s["scaffold_h"] if s["scaffold_h"] else None)
    model["step"] = n
    mpath.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
    on = "・".join(x.replace("仮設工程_", "") + ("（作業中）" if state_of(s, x) == "作業中" else "")
                  for x in LAYERS if state_of(s, x) != "なし")
    print(f"工程の模型: ステップ {n}/{len(steps)} {s['date']} {s['name']}: {on or '仮設なし'}"
          + (f"・足場 {s['scaffold_h']:.1f}m まで（{k} 部品）" if s["scaffold_h"] else ""))
    if old and s["scaffold_h"]:
        print(f"  注意: 前の版で置いた足場の部品 {old} 個は高さで切れません（全部の高さで見えます）。足場を置き直すと切れます")
    return 0


if __name__ == "__main__":
    sys.exit(main())
