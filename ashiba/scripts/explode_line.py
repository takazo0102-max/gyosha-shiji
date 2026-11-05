"""足場ラインの支柱だけを分解する／分解を戻す（パレットのボタン「支柱だけ分解」「分解を戻す」）.

利用者の指定（2026-10-21）: 最初は支柱・布材・踏板・手すりなど全部を1本ずつの部品にしたが、建物1棟で約1400本になり
重かった。「分解はやめて垂直と水平で区切れるようにして、支柱だけ分解できるようにして」。足場ライン（面ごと、または
区切った部品ごとに1部品）の支柱（コマ・継手付き。枠組は建枠）を1本ずつの部品（ashiba_member）にする。分解した支柱は
1本ずつ選んで消す・動かす・コピーできる（Archicad の一覧表にも1本ずつ出る）。ジャッキ・布材・踏板・手すり・
ブレース・階段・朝顔などは足場ラインのまま描く（explodeMask=1 は支柱だけを描かない）。

使い方（Archicad で足場ラインを選んでから）:
  python3 scripts/explode_line.py            # 選んだ足場ラインの支柱を分解
  python3 scripts/explode_line.py --undo     # 選んだ足場ライン（または分解した支柱）の分解を戻す
「配置」で置き直すと分解していない状態に戻る（分解した支柱も消える）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.explode import MEMBER_OBJECT, line_members, member_counts, to_world  # noqa: E402
from ashiba.segments import piece_of  # noqa: E402
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


def lite_3d(p: dict) -> bool:
    """足場ラインが軽量で描いているか（3d.gdl の d3: 2＝軽量、0＝自動はスパン数×作業層数 > 40 で軽量）.

    分解した支柱も同じ細かさで描く（自動の長い面で、分解した支柱だけ精細で濃く見えた 2026-10-21 実機）。
    """
    d3 = int(float(p.get("detail3d") or 0))
    if d3 == 0:
        try:
            pc = piece_of(p)
            return pc.n_span * pc.n_levels > 40
        except ValueError:
            return False
    return d3 == 2


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
                  "liteMode": lite_3d(p),
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
        print(f"{p.get('faceName') or '面'}: 支柱を{n}本に分解（" + "・".join(f"{k}{v}" for k, v in kinds.items()) + "）")
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
    # 選択は平面に切り替える前に読む（3D で選んで押すと、平面に切り替えたときに選択が外れていた 2026-10-21 実機）
    lines, members = _selected(c)
    activate_floor_plan(c)
    if "--undo" in argv:
        n = undo(c, lines, members)
        print(f"分解を戻しました（支柱 {n}本を消し、足場ラインで描きます）" if n else
              "戻す分解がありません（分解した足場ラインか支柱を選んでから押してください）")
        return 0
    if not lines:
        print("足場ラインを選んでから押してください（面ごとの足場の部品。平面で足場をクリック）")
        return 1
    try:
        n = explode(c, lines)
    except TapirError as e:
        print(f"エラー: {e}")
        return 2
    print(f"計 {n}本の支柱にしました。1本ずつ選んで消す・動かすことができます。戻すときは「分解を戻す」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
