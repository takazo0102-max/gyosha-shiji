"""足場ラインを部材に分解する／分解を戻す（パレットのボタン「部材に分解」「分解を戻す」）.

利用者の指定（2026-10-21）: 部材を分解できるコマンドを Tapir に。足場ライン（面ごとに1部品）を、支柱・ジャッキ・
布材（根がらみ・腕木・手すり・中桟）・先行手すり・踏板・幅木・ブレースの1本ずつの部品（ashiba_member）にする。
分解した部材は1本ずつ選んで、消す・動かす・コピーできる（Archicad の一覧表にも1本ずつ出る）。
足場ラインは残し、分解した部材を描かない状態（explodeMask=1）にする。階段・朝顔・出隅・開口部の梁枠・
ステージ・壁つなぎ・寸法は足場ラインのまま。

使い方（Archicad で足場ラインを選んでから）:
  python3 scripts/explode_line.py            # 選んだ足場ラインを分解
  python3 scripts/explode_line.py --undo     # 選んだ足場ライン（または分解した部材）の分解を戻す
数量表（帳票）は足場ラインの計画のまま。分解後に消した・足した部材は、「配置」で置き直すと元に戻る。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.explode import MEMBER_OBJECT, line_members, member_counts, to_world  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError, is_ashiba_part  # noqa: E402


def _params(c: ArchicadClient, el: dict) -> dict:
    r = c.tapir("GetGDLParametersOfElements", {"elements": [el]})
    item = (r.get("gdlParametersOfElements") or [{}])[0]
    return {p.get("name"): p.get("value") for p in item.get("gdlParameters", item.get("parameters", []))}


def _selected(c: ArchicadClient):
    sel = c.get_selected_elements()
    if not sel:
        return [], []
    lines, members = [], []
    for e, d in zip(sel, c.get_details(sel)):
        dd = d.get("details", {})
        name = (dd.get("libPart") or {}).get("name", "")
        if is_ashiba_part(name, ("ashiba_line",)):
            lines.append((e, dd))
        elif is_ashiba_part(name, (MEMBER_OBJECT,)):
            members.append(e)
    return lines, members


def _all_members(c: ArchicadClient) -> list[tuple[dict, str]]:
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    out = []
    for e, d in zip(objs, c.get_details(objs) if objs else []):
        name = ((d.get("details") or {}).get("libPart") or {}).get("name", "")
        if is_ashiba_part(name, (MEMBER_OBJECT,)):
            out.append(e)
    if not out:
        return []
    res = []
    for i in range(0, len(out), 200):
        part = out[i:i + 200]
        r = c.tapir("GetGDLParametersOfElements", {"elements": part})
        for e, item in zip(part, r.get("gdlParametersOfElements", [])):
            ps = {p.get("name"): p.get("value") for p in item.get("gdlParameters", item.get("parameters", []))}
            res.append((e, str(ps.get("parentId") or "")))
    return res


def explode(c: ArchicadClient, lines) -> int:
    from run_from_archicad import GDL_DIR, versioned_part_name

    name = versioned_part_name(MEMBER_OBJECT)
    c.ensure_embedded_parts([(GDL_DIR / f"{MEMBER_OBJECT}.gsm", name)])
    total = 0
    for el, dd in lines:
        p = _params(c, el)
        guid = el["elementId"]["guid"]
        if int(float(p.get("explodeMask") or 0)) > 0:
            print(f"分解済み（{p.get('faceName') or guid[:8]}）。戻すときは「分解を戻す」")
            continue
        try:
            ms = line_members(p)
        except ValueError as e:
            print(f"分解できません（{p.get('faceName') or guid[:8]}）: {e}")
            continue
        o = dd.get("origin") or {}
        world = to_world(ms, (float(o.get("x", 0)), float(o.get("y", 0))), float(dd.get("angle") or 0),
                         base_z_m=float(o.get("z", 0) or 0))
        made = c.create_objects([(name, w["x"] * 1000.0, w["y"] * 1000.0) for w in world])
        common = {"parentId": guid, "postDia": float(p.get("postDia") or 0.0427),
                  "postShape": int(float(p.get("postShape") or 0)),
                  "liteMode": int(float(p.get("detail3d") or 0)) == 2,
                  "matScaf": int(float(p.get("matScaf") or 0)), "matDeck": int(float(p.get("matDeck") or 0)),
                  "matToe": int(float(p.get("matToe") or 0))}
        pairs = [(el2, {**w["params"], **common}) for el2, w in zip(made, world) if el2]
        n = c.set_gdl_parameters_many(pairs)
        c.set_gdl_parameters_many([(el, {"explodeMask": 1})])
        total += n
        counts = member_counts(ms)
        kinds = {}
        for k, v in counts.items():
            head = k.split(" ")[0].split("（")[0]
            kinds[head] = kinds.get(head, 0) + v
        print(f"{p.get('faceName') or '面'}: {n}本に分解（" + "・".join(f"{k}{v}" for k, v in kinds.items()) + "）")
    return total


def undo(c: ArchicadClient, lines, members) -> int:
    ids = {el["elementId"]["guid"] for el, _ in lines}
    allm = _all_members(c)
    if members:
        sel_ids = {e["elementId"]["guid"] for e in members}
        ids |= {pid for e, pid in allm if e["elementId"]["guid"] in sel_ids and pid}
    if not ids:
        return 0
    gone = [e for e, pid in allm if pid in ids]
    if gone:
        c.delete_elements(gone)
    # 足場ラインを元の描き方に
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    back = [(e, {"explodeMask": 0}) for e in objs if e["elementId"]["guid"] in ids]
    c.set_gdl_parameters_many(back)
    return len(gone)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    from ashiba.elevation_sections import activate_floor_plan

    c = ArchicadClient()
    activate_floor_plan(c)
    lines, members = _selected(c)
    if "--undo" in argv:
        n = undo(c, lines, members)
        print(f"分解を戻しました（部材 {n}本を消し、足場ラインで描きます）" if n else
              "戻す分解がありません（分解した足場ラインか部材を選んでから押してください）")
        return 0
    if not lines:
        print("足場ラインを選んでから押してください（面ごとの足場の部品。平面で足場をクリック）")
        return 1
    try:
        n = explode(c, lines)
    except TapirError as e:
        print(f"エラー: {e}")
        return 2
    print(f"計 {n}本の部材にしました。1本ずつ選んで消す・動かすことができます。戻すときは「分解を戻す」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
