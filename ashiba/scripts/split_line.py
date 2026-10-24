"""足場ラインを区切る／区切りを戻す（パレットのボタン「区切る」「区切りを戻す」）.

利用者の指定（2026-10-24）「区切るも3Dでなく平面で線で区切るように変更して」: 平面で、区切りたいところに足場を横切る線を
引き（何本でも）、その線を選んで押すと、線にいちばん近い支柱で縦に区切る（目印の線は消す）。線を選ばずに足場ラインを
選んで押したときは前のとおり 3D のつまみの位置で区切る（横の区切りは 3D のつまみだけ）。
以前の指定（2026-10-21）: 「垂直と水平で区切れるようにして」「クリックした次のところから区切るようなコマンド、3Dで」。
3D で足場ラインを選ぶと、上端に縦の区切りのつまみ、始点の支柱の外に横の区切りのつまみが出る。引いた位置の次の
支柱の芯・次の作業床に吸着して赤い面が出る（足場ライン vl.gdl・3d.gdl）。このスクリプトがそこで部品を分ける:
元の部品は始点側・下側の範囲になり、残りの範囲は同じ足場ラインの写し（範囲だけ違う）を置く。区切った部品は
それぞれ選んで消す・動かす・コピーでき、支柱だけ分解（「支柱だけ分解」）もできる。数量（一覧表の図示本数）は
部品ごとに自分の範囲だけを数える。

使い方（Archicad で足場ラインを選んでから）:
  python3 scripts/split_line.py            # つまみで決めた位置で区切る
  python3 scripts/split_line.py --undo     # 選んだ部品の面を1つに戻す
「配置」で置き直しても区切りの無い面に戻る。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.segments import WHOLE, piece_of, split_ranges  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError, is_ashiba_part  # noqa: E402
from explode_line import _all_members, _params, _selected, explode  # noqa: E402

LINE_PARAMS_XML = ROOT / "gdl" / "hsf" / "ashiba_line" / "paramlist.xml"


def _own_param_names() -> set[str]:
    """足場ラインの自前のパラメータ名（写しに写すもの。配列は除く）."""
    import re
    text = LINE_PARAMS_XML.read_text(encoding="utf-8")
    return {m.group(2) for m in re.finditer(r'<(Length|Integer|RealNum|String|Boolean|Material|PenColor|Angle)\s+Name="([^"]+)"', text)}


def _copy_params(p: dict) -> dict:
    names = _own_param_names()
    return {k: v for k, v in p.items() if k in names and not isinstance(v, (list, dict))}


def _drop_members(c: ArchicadClient, guids: set[str]) -> int:
    gone = [e for e, pid in _all_members(c) if pid in guids]
    if gone:
        c.delete_elements(gone)
    return len(gone)


def _face(p: dict, guid: str) -> str:
    return str(p.get("faceName") or "") or guid[:8]


def split(c: ArchicadClient, lines) -> int:
    made_total = 0
    for el, dd in lines:
        guid = el["elementId"]["guid"]
        p = _params(c, el)
        try:
            ranges = split_ranges(p)
        except ValueError as e:
            print(f"区切れません（{_face(p, guid)}）: {e}")
            continue
        if not ranges:
            print(f"区切る位置がありません（{_face(p, guid)}）。3Dで足場を選び、上端の縦のつまみか始点の横のつまみを"
                  "引いてから押してください")
            continue
        exploded = int(float(p.get("explodeMask") or 0)) > 0
        if exploded:
            _drop_members(c, {guid})
        group = str(p.get("segGroup") or "") or guid
        o = dd.get("origin") or {}
        name = (dd.get("libPart") or {}).get("name", "")
        base = _copy_params(p)
        news = []
        for rng in ranges[1:]:
            e2 = c.create_object(name, float(o.get("x", 0)) * 1000, float(o.get("y", 0)) * 1000,
                                 float(o.get("z", 0) or 0) * 1000)
            ang = float(dd.get("angle") or 0)
            if abs(ang) > 1e-9:
                c.rotate_element(e2, ang, float(o.get("x", 0)) * 1000, float(o.get("y", 0)) * 1000)
            news.append((e2, {**base, **rng, "segGroup": group, "editSpan": False, "explodeMask": 0}))
        c.set_gdl_parameters_many([(el, {**ranges[0], "segGroup": group, "editSpan": False, "explodeMask": 0})] + news)
        made_total += len(news)
        desc = []
        for rng in ranges:
            desc.append(f"スパン{rng['segSpanA']}〜{rng['segSpanB']}・{rng['segLevA']}〜{rng['segLevB']}層")
        print(f"{_face(p, guid)}: {len(ranges)}つに区切りました（" + "／".join(desc) + "）")
        if exploded:
            again = [(el, dd)] + [(e2, dd) for e2, _ in news]
            n = explode(c, again)
            print(f"  支柱の分解は区切った部品ごとにやり直しました（{n}本）")
    return made_total


def split_by_guides(c: ArchicadClient, guides) -> int:
    """平面の目印の線（足場を横切る）ごとに、線にいちばん近い支柱で縦に区切る → 足した部品の数."""
    from ashiba.plan_pick import across, nearest_post
    from ashiba.segments import piece_of
    from ashiba.span_readback import match_edge
    from guide_lines import building_plan

    pts = [p for _e, segs in guides for seg in segs for p in seg]
    plan = building_plan(pts)
    if plan is None:
        print("区切る: 線の近くの足場の配置の控え（plan.json）がありません。先に「配置」してください")
        return 0
    edges = plan.get("edges") or []
    made = 0
    for _e, segs in guides:
        for a, b in segs:
            hit = across(edges, a, b)
            if hit is None:
                print("区切る: 足場を横切っていない線がありました（区切りたいところで足場の帯をまたぐように引いてください）")
                continue
            e, t = hit
            xp = nearest_post(e, t)
            face = str(e.get("face") or f"辺{e['edge_index']}")
            # その面の部品のうち、支柱 xp を内側に持つもの（区切った部品は同じ原点）
            target = None
            objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
            for el, d in zip(objs, c.get_details(objs) if objs else []):
                dd = d.get("details") or {}
                if not is_ashiba_part((dd.get("libPart") or {}).get("name", ""), ("ashiba_line",)):
                    continue
                o = dd.get("origin") or {}
                if match_edge([e], (float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0)) is None:
                    continue
                p = _params(c, el)
                try:
                    pc = piece_of(p)
                except ValueError:
                    continue
                if pc.lA == 1 and pc.pxA * 1000 + 1.0 < xp < pc.pxB * 1000 - 1.0:
                    target = (el, dd, pc)
                    break
            if target is None:
                print(f"区切る: {face}の {xp:.0f} で区切れる部品がありません（もう区切ってあるか、面の端です）")
                continue
            el, dd, pc = target
            c.set_gdl_parameters_many([(el, {"cutAtX": xp / 1000.0 - pc.pxA, "cutAtZ": 0.0})])
            print(f"区切る: {face}の始点から {xp:.0f} の支柱で区切ります（線は {t:.0f}）")
            made += split(c, [(el, dd)])
    return made


def merge(c: ArchicadClient, lines, members) -> int:
    """選んだ部品の面（segGroup が同じ部品）を1つに戻す。始点・下端の部品を残し、ほかは消す."""
    groups = set()
    for el, _ in lines:
        g = str(_params(c, el).get("segGroup") or "")
        if g:
            groups.add(g)
    if members:
        ids = {e["elementId"]["guid"] for e in members}
        parents = {pid for e, pid in _all_members(c) if e["elementId"]["guid"] in ids}
        objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        for e in objs:
            if e["elementId"]["guid"] in parents:
                g = str(_params(c, e).get("segGroup") or "")
                if g:
                    groups.add(g)
    if not groups:
        return 0
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    pieces: dict[str, list] = {}
    details = c.get_details(objs) if objs else []
    for e, d in zip(objs, details):
        dd = d.get("details") or {}
        if not is_ashiba_part((dd.get("libPart") or {}).get("name", ""), ("ashiba_line",)):
            continue
        p = _params(c, e)
        g = str(p.get("segGroup") or "")
        if g in groups:
            pieces.setdefault(g, []).append((e, dd, p))
    removed = 0
    for g, items in pieces.items():
        def order(it):
            pc = piece_of(it[2])
            return (pc.lA, pc.sA)
        items.sort(key=order)
        keep, rest = items[0], items[1:]
        exploded = any(int(float(it[2].get("explodeMask") or 0)) > 0 for it in items)
        _drop_members(c, {it[0]["elementId"]["guid"] for it in items})
        if rest:
            c.delete_elements([it[0] for it in rest])
        c.set_gdl_parameters_many([(keep[0], {**WHOLE, "editSpan": True, "explodeMask": 0})])
        removed += len(rest)
        print(f"{_face(keep[2], keep[0]['elementId']['guid'])}: {len(items)}つの部品を1つに戻しました")
        if exploded:
            n = explode(c, [(keep[0], keep[1])])
            print(f"  支柱の分解は面全体でやり直しました（{n}本）")
    return removed


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    from ashiba.elevation_sections import activate_floor_plan

    c = ArchicadClient()
    lines, members = _selected(c)
    activate_floor_plan(c)
    try:
        if "--undo" in argv:
            n = merge(c, lines, members)
            if not n and not lines and not members:
                print("区切った足場ラインを選んでから押してください")
            elif not n:
                print("戻す区切りがありません（区切った足場ラインを選んでから押してください）")
            return 0
        from guide_lines import delete_guides, not_in_plan_hint, selected_guides

        guides = selected_guides(c)
        if guides:
            n = split_by_guides(c, guides)
            if n:
                delete_guides(c, guides)
                print("区切る: 目印の線を消しました")
        elif not lines:
            print("区切る: 平面で、区切りたいところに足場を横切る線を引き、その線を選んでから押してください"
                  + not_in_plan_hint(c) + "（横に区切るときは 3D で足場を選び、つまみで位置を決めて押す）")
            return 1
        else:
            n = split(c, lines)
    except TapirError as e:
        print(f"エラー: {e}")
        return 2
    if n:
        print(f"計 {n}個の部品を足しました。1つずつ選んで消す・動かす・支柱だけ分解ができます。戻すときは「区切りを戻す」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
