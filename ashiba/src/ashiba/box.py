"""足場の箱（超簡易モード。部品 ashiba_box）: 四角い足場を伸び縮みして形を決め、ボタンで本体にする.

利用者の指定（2026-10-30）「超簡易モードになってない いきなり足場が現れた」「なんか違う 箱を作って自分で伸び縮みするような
感じ」→ 一周の箱（四角）・ボタンで本体にする。

- 箱を置く: 平面の線の始点を箱の角（内側の建地の列）に、線の長さを長手の初めの長さにする。部品の右の辺・上の辺の中ほどの
  つまみで伸び縮みし、長さは定尺の組み合わせに吸着する（部品のパラメータスクリプト。snap_spans は同じ決め方）。
- 箱を足場に: 箱の角・向き・スパン・段数を読み、内側の建地の列の一周（manual.solve_manual_loop）として足場一式に置き直す。
"""

from __future__ import annotations

import math
from typing import Optional

BOX_OBJECT = "ashiba_box"
BOX_MIN_SPAN_MM = 600     # 箱の吸着に使う定尺の下限（アルバトロスの 457 は端数の調整用で、先行手摺・シート・朝顔の合う品が無い）
DEFAULT_LEVELS = 4
AXIS_TOL_DEG = 2.0
# 吸着で1本多い並びを 5mm 遠いとみる（引いた 9100 が 1829×4＋914×2＝9144 になり、1mm しか違わない 1829×5＝9145 にならなかった。
# 実機 2026-10-31）。部品のパラメータスクリプトも同じ値（0.005）
PIECE_PENALTY_MM = 5.0


def box_coins(coins: list[int]) -> list[int]:
    """箱の吸着に使う定尺（大きい順。BOX_MIN_SPAN_MM 未満は使わない。それしか無ければそのまま）."""
    big = sorted({int(c) for c in coins if c >= BOX_MIN_SPAN_MM}, reverse=True)
    return big or sorted({int(c) for c in coins}, reverse=True)


def snap_spans(length_mm: float, coins: list[int]) -> list[int]:
    """長さ → 定尺の最大を n 本並べ、端数を定尺 0〜2 本で埋めた並び（いちばん近い組。1本多いごとに PIECE_PENALTY_MM 遠いとみる）.
    部品 ashiba_box のパラメータスクリプト（つまみで引いたとき）と同じ決め方."""
    sz = sorted({int(c) for c in coins if c > 100}, reverse=True)
    if not sz:
        raise ValueError("定尺がありません")
    mx = sz[0]
    best = None
    for n in range(0, int(length_mm // mx) + 2):
        for i in range(0, len(sz) + 1):
            for j in range(i, len(sz) + 1):
                s = sz[i - 1] if i > 0 else 0
                t = sz[j - 1] if j > 0 else 0
                tot = n * mx + s + t
                if tot <= 100:
                    continue
                d = abs(tot - length_mm) + PIECE_PENALTY_MM * (n + (i > 0) + (j > 0))
                if best is None or d < best[0]:
                    best = (d, [mx] * n + [v for v in (s, t) if v])
    return best[1]


def box_loop(origin_mm: tuple[float, float], angle_rad: float, sx: list[int], sy: list[int]
             ) -> tuple[list[tuple[float, float]], list[list[int]]]:
    """箱の角（内側の建地の列の角）・向き・スパン → 内側の建地の列の一周の点（左回り）と辺ごとのスパン.

    足場は平面の縦・横にしか組まないので、向きは 90° の倍数（±2°）に限る。"""
    deg = math.degrees(angle_rad) % 360.0
    k = round(deg / 90.0) % 4
    if abs(deg - 90.0 * round(deg / 90.0)) > AXIS_TOL_DEG:
        raise ValueError(f"箱が斜め（{deg:.1f}°）です。足場は平面の縦・横に組むので、箱は 0・90・180・270° の向きにしてください")
    u = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)][k]
    v = (-u[1], u[0])
    lx, ly = float(sum(sx)), float(sum(sy))
    x0, y0 = origin_mm
    pts = [(x0, y0), (x0 + u[0] * lx, y0 + u[1] * lx),
           (x0 + u[0] * lx + v[0] * ly, y0 + u[1] * lx + v[1] * ly), (x0 + v[0] * ly, y0 + v[1] * ly)]
    return pts, [list(sx), list(sy), list(reversed(sx)), list(reversed(sy))]


def parse_box_params(params: dict) -> dict:
    """部品のパラメータ（GetGDLParametersOfElements の名前→値）→ スパン（mm）・段数・幅・離れ・系列."""
    from .manual import parse_spans

    sx = parse_spans(str(params.get("spanX") or ""))
    sy = parse_spans(str(params.get("spanY") or ""))
    if not sx or not sy:
        raise ValueError("箱のスパンが読めません（spanX・spanY）")
    return {"sx": sx, "sy": sy, "levels": max(1, int(float(params.get("nLev") or DEFAULT_LEVELS))),
            "thick_mm": snap_thickness(float(params.get("thick") or 0.9) * 1000.0),
            "base_mm": max(0.0, float(params.get("zBase") or 0.0) * 1000.0),
            "standoff": float(params.get("standoff") or 0.3) * 1000.0,
            "floor_mm": float(params.get("floorH") or 1.8) * 1000.0,
            "series_id": str(params.get("seriesId") or "")}


THICKNESSES = (300, 600, 900, 1200)   # 箱の厚み（部品が吸着する値）: 300＝一側足場、600／900／1200＝本足場の幅


def snap_thickness(t_mm: float) -> int:
    return min(THICKNESSES, key=lambda t: abs(t - t_mm))


def thickness_conditions(t_mm: float, standoff: float) -> tuple[str, dict]:
    """箱の厚み → (種類の名前, 解く条件). 利用者の指定 2026-10-30: 厚みで種類も変える.

    300 は一側足場。本足場が入らない狭い所の足場なので、使える幅を「離れ＋厚み＋100」とする（ブラケットの出 360 は収まり、
    本足場の幅 610 は収まらない。安衛則561条の2 の本足場原則のただし書き）。600・900・1200 は幅 610・914・1219 の本足場。"""
    t = snap_thickness(t_mm)
    if t == 300:
        return "一側足場", {"scaffold_form": "一側足場", "clearance_space_mm": standoff + t + 100.0}
    return f"本足場 幅{t}", {"scaffold_form": "本足場", "scaffold_width_mm": t}


def width_nominal(row_mm: float) -> int:
    """足場の幅（内外の建地の間 610・914・1219）→ 条件の足場の幅（600・900・1200）."""
    return min((600, 900, 1200), key=lambda w: abs(w - row_mm * 900.0 / 914.0))


def box_params(sx: list[int], sy: list[int], coins: list[int], thick_mm: float, levels: int, lev1_mm: float,
               floor_mm: float, series_id: str, standoff: float, pens: Optional[dict] = None,
               base_mm: float = 0.0) -> dict:
    """部品 ashiba_box に入れるパラメータ（m）."""
    out = {"spanX": ",".join(str(int(v)) for v in sx), "spanY": ",".join(str(int(v)) for v in sy),
           "szList": ",".join(str(int(c)) for c in sorted({int(c) for c in coins}, reverse=True)),
           "lenX": sum(sx) / 1000.0, "lenY": sum(sy) / 1000.0, "thick": snap_thickness(thick_mm) / 1000.0,
           "nLev": int(levels),
           "lev1": lev1_mm / 1000.0, "floorH": floor_mm / 1000.0,
           "topEdit": (lev1_mm + (levels - 1) * floor_mm) / 1000.0, "seriesId": series_id, "standoff": standoff / 1000.0,
           "zBase": max(0.0, base_mm) / 1000.0}
    out.update(pens or {})
    return out


def contains(outer_pts: list, inner_pts: list, tol: float = 1.0) -> bool:
    """箱の内側の建地の列（四角）inner が outer の中（辺の上も含む）にあるか."""
    xs, ys = [p[0] for p in outer_pts], [p[1] for p in outer_pts]
    return all(min(xs) - tol <= p[0] <= max(xs) + tol and min(ys) - tol <= p[1] <= max(ys) + tol for p in inner_pts)


def setback_spec(low: dict, uppers: list[dict], extra: dict) -> dict:
    """下の箱と、その中に立つ高さを上げて重ねた上の階の箱 → 下の足場と上段をつないで一度に解く条件.

    利用者の指定（2026-10-30）「下の足場と上段をつなげて」。建物の床から解くセットバック（setback_tiers）と同じ形にする:
    下の箱の内側を途中の屋根の床（天端＝上の箱の立つ高さ）、上の箱の内側を上の階の床（天端＝立つ高さ＋その箱の高さ）とし、
    本体は下の箱のスパン・離れで解く。上の階の面が下の箱の面にそろう所は本体の足場がそのまま上まで上がり、下がった面は屋根の
    上から上段の足場を建てて端を本体の支柱に乗せる。本体から途中の屋根へは屋上への渡りを付ける。low・uppers は {"pts", "sides", "standoff", "base_mm", "levels", "floor_mm"}."""
    from .manual import eaves_for_levels, loop_building

    outline, ms = loop_building(low["pts"], low["sides"], low["standoff"])
    roof = min(u["base_mm"] for u in uppers)
    slabs = [{"polygon_mm": outline, "top_mm": roof, "thickness_mm": 200.0}]
    for u in uppers:
        ol, _ = loop_building(u["pts"], u["sides"], u["standoff"])
        slabs.append({"polygon_mm": ol, "top_mm": u["base_mm"] + eaves_for_levels(u["levels"], int(u["floor_mm"])),
                      "thickness_mm": 200.0})
    so = float(low["standoff"])
    return {**extra, "outline_mm": outline, "eaves_height_mm": roof, "slabs": slabs,
            "span_overrides": [{"edge_index": i, "spans_mm": sp} for i, sp in enumerate(ms)],
            "standoff": {"target": so, "min": so, "max": so, "hard_min": so},
            # 屋根は利用者が箱で決めた本物の屋根なので、本体の足場から途中の屋根へ・上段から上の階の屋根へ渡る（上の箱が
            # 下の箱の内側に収まって面がそろわないときも、本体から屋根へ渡って上段へ行ける）
            "height_from_slabs": True, "avoid_obstacles": True, "roof_bridge": True}


# ---- 足場の辺（部品 ashiba_side）: 箱を1辺ずつに分けたもの ----
# 利用者の指定（2026-10-31）「箱は1辺ずつ別々にしてちょ」。箱は一周が1つの部品で、辺ごとに厚み（足場の種類）・段数を変えたり、
# 1辺だけ消してコの字・L字にしたりできなかった。「箱を置く」は四角の4辺を別々の部品で置き、「箱を足場に」は選んだ辺を
# 端どうしのつながりで組にして、閉じた組は一周、開いた組は L字（2辺）・コの字（3辺）・1本として足場一式に置き直す。
# 辺の原点＝内側の建地の列の始点、向き＝辺の向き、足場は進む向きの右（建物は左。左回りの一周の内側）。

SIDE_OBJECT = "ashiba_side"
JOIN_TOL_MM = 1000.0       # 辺の終わりと次の辺の始め（角）がこれ以内ならつながっているとみる（置き直しのずれ）


def side_axis(angle_rad: float) -> tuple[float, float]:
    """辺の向き（部品の回転）→ 縦・横の単位ベクトル。足場は平面の縦・横にしか組まないので ±2° まで."""
    deg = math.degrees(angle_rad) % 360.0
    if abs(deg - 90.0 * round(deg / 90.0)) > AXIS_TOL_DEG:
        raise ValueError(f"足場の辺が斜め（{deg:.1f}°）です。足場は平面の縦・横に組むので、0・90・180・270° の向きにしてください")
    return [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)][round(deg / 90.0) % 4]


def box_sides(origin_mm: tuple[float, float], angle_rad: float, sx: list[int], sy: list[int]
              ) -> list[tuple[tuple[float, float], float, list[int]]]:
    """箱（角・向き・スパン）→ 4辺 [(始点, 向きの角度, スパン)]. 左回り（下・右・上・左）で、足場は各辺の右（外）."""
    pts, sides = box_loop(origin_mm, angle_rad, sx, sy)
    out = []
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        out.append((a, math.atan2(b[1] - a[1], b[0] - a[0]), list(sides[i])))
    return out


def side_params(spans: list[int], coins: list[int], thick_mm: float, levels: int, lev1_mm: float, floor_mm: float,
                series_id: str, standoff: float, pens: Optional[dict] = None, base_mm: float = 0.0,
                corner_end: bool = True) -> dict:
    """部品 ashiba_side に入れるパラメータ（m）."""
    out = {"spanX": ",".join(str(int(v)) for v in spans),
           "szList": ",".join(str(int(c)) for c in sorted({int(c) for c in coins}, reverse=True)),
           "lenX": sum(spans) / 1000.0, "thick": snap_thickness(thick_mm) / 1000.0, "nLev": int(levels),
           "lev1": lev1_mm / 1000.0, "floorH": floor_mm / 1000.0,
           "topEdit": (lev1_mm + (levels - 1) * floor_mm) / 1000.0, "seriesId": series_id, "standoff": standoff / 1000.0,
           "zBase": max(0.0, base_mm) / 1000.0, "cornerE": bool(corner_end)}
    out.update(pens or {})
    return out


def parse_side_params(params: dict) -> dict:
    """部品 ashiba_side のパラメータ → スパン（mm）・段数・厚み・立つ高さ・離れ・系列."""
    from .manual import parse_spans

    sp = parse_spans(str(params.get("spanX") or ""))
    if not sp:
        raise ValueError("足場の辺のスパンが読めません（spanX）")
    return {"spans": sp, "levels": max(1, int(float(params.get("nLev") or DEFAULT_LEVELS))),
            "thick_mm": snap_thickness(float(params.get("thick") or 0.9) * 1000.0),
            "base_mm": max(0.0, float(params.get("zBase") or 0.0) * 1000.0),
            "standoff": float(params.get("standoff") or 0.3) * 1000.0,
            "floor_mm": float(params.get("floorH") or 1.8) * 1000.0,
            "series_id": str(params.get("seriesId") or "")}


def _side_end(s: dict) -> tuple[float, float]:
    L = float(sum(s["spans"]))
    return s["a"][0] + s["dir"][0] * L, s["a"][1] + s["dir"][1] * L


def _link_score(si: dict, sj: dict) -> Optional[float]:
    """辺 si の終わりから辺 sj の始めへつながるなら、そのずれ（mm）。つながらなければ None."""
    if abs(si["base_mm"] - sj["base_mm"]) > 1.0 or (si.get("series_id") or "") != (sj.get("series_id") or ""):
        return None
    di, dj = si["dir"], sj["dir"]
    dot = di[0] * dj[0] + di[1] * dj[1]
    ei = _side_end(si)
    aj = sj["a"]
    if dot < -0.5:
        return None
    if dot > 0.5:
        # まっすぐ続く辺（同じ面で厚みを変えるとき）: 同じ線の上で、終わりと始めが近い
        if abs(di[0] * (aj[1] - si["a"][1]) - di[1] * (aj[0] - si["a"][0])) > 1.0:
            return None
        g = abs((aj[0] - ei[0]) * di[0] + (aj[1] - ei[1]) * di[1])
        return g if g <= JOIN_TOL_MM else None
    # 直角に曲がる辺: 2本の線の交点（角）が si の終わりと sj の始めの近くにある
    c = (aj[0], si["a"][1]) if abs(di[0]) > 0.5 else (si["a"][0], aj[1])
    g1 = abs((c[0] - ei[0]) * di[0] + (c[1] - ei[1]) * di[1])
    g2 = abs((c[0] - aj[0]) * dj[0] + (c[1] - aj[1]) * dj[1])
    return g1 + g2 if g1 <= JOIN_TOL_MM and g2 <= JOIN_TOL_MM else None


def chain_sides(sides: list[dict]) -> list[tuple[list[int], bool]]:
    """辺（{"a", "dir", "spans", "base_mm", "series_id"}）→ 端どうしでつながる組 [(辺の番号の並び, 閉じているか)].
    つながりはずれの小さい順に、1本の辺の終わり・始めに1本ずつ決める."""
    cand = []
    for i, si in enumerate(sides):
        for j, sj in enumerate(sides):
            if i != j:
                g = _link_score(si, sj)
                if g is not None:
                    cand.append((g, i, j))
    nxt: dict[int, int] = {}
    prv: dict[int, int] = {}
    for _g, i, j in sorted(cand):
        if i not in nxt and j not in prv:
            nxt[i], prv[j] = j, i
    seen: set[int] = set()
    out = []
    for i in range(len(sides)):
        if i in seen or i in prv:
            continue
        ch = [i]
        seen.add(i)
        while ch[-1] in nxt and nxt[ch[-1]] not in seen:
            ch.append(nxt[ch[-1]])
            seen.add(ch[-1])
        out.append((ch, False))
    for i in range(len(sides)):
        if i in seen:
            continue
        ch = [i]
        seen.add(i)
        while nxt.get(ch[-1]) is not None and nxt[ch[-1]] not in seen:
            ch.append(nxt[ch[-1]])
            seen.add(ch[-1])
        out.append((ch, True))
    return out


def side_form(t_mm: int, main_mm: int) -> Optional[str]:
    """一周の足場の幅（主な厚み main_mm）と違う厚みの辺の、面ごとの足場の種類（face_forms）。切り替えられなければ None."""
    t, m = snap_thickness(t_mm), snap_thickness(main_mm)
    if t == m:
        return None
    if t == 300:
        return "一側足場（狭い所）"
    if m == 300:
        return "本足場"
    if t == 600:
        return "本足場（狭い幅）"
    return None


def plan_side_chain(sides: list[dict], chain: list[int], closed: bool) -> dict:
    """つながった辺の組 → 解く形 {"kind": "loop"/"open"/"line", "pts", "sides"（辺ごとのスパン）, "keep",
    "group_sides"（面ごとの元の辺の番号）, "main"（主な辺の属性）, "notes"}. まっすぐ続く辺は1つの面にまとめる."""
    from .manual import close_open_path

    ss = [sides[i] for i in chain]
    groups: list[list[int]] = []
    for k, s in enumerate(ss):
        if groups and ss[groups[-1][-1]]["dir"] == s["dir"]:
            groups[-1].append(k)
        else:
            groups.append([k])
    if closed and len(groups) > 1 and ss[groups[0][0]]["dir"] == ss[groups[-1][0]]["dir"]:
        groups[0] = groups.pop() + groups[0]
    notes = []
    for g in groups:
        if len({(ss[k]["thick_mm"], ss[k]["levels"]) for k in g}) > 1:
            notes.append("まっすぐ続く辺の厚み・段数が違うので、始めの辺にそろえました（面の途中で種類を変えるときは、"
                         "置いたあとに足場ラインを区切って「面の切替」）")
    # 主な厚み: 一側足場（300）でない辺の長さの合計がいちばん多い厚み。主な辺: その厚みでいちばん長い辺
    by_t: dict[int, float] = {}
    for s in ss:
        if s["thick_mm"] != 300:
            by_t[s["thick_mm"]] = by_t.get(s["thick_mm"], 0.0) + sum(s["spans"])
    main_t = max(by_t, key=lambda t: (by_t[t], t)) if by_t else 300
    main = max((s for s in ss if s["thick_mm"] == main_t), key=lambda s: sum(s["spans"]))
    gsp = [[v for k in g for v in ss[k]["spans"]] for g in groups]
    gdir = [ss[g[0]]["dir"] for g in groups]
    p = [tuple(map(float, ss[0]["a"]))]
    for d, sp in zip(gdir, gsp):
        L = float(sum(sp))
        p.append((p[-1][0] + d[0] * L, p[-1][1] + d[1] * L))
    gs = [[chain[k] for k in g] for g in groups]
    if closed:
        if len(groups) < 4:
            raise ValueError("つながった辺が一周になりません（縦横に4辺以上で囲んでください）")
        return {"kind": "loop", "pts": p[:-1], "sides": gsp, "keep": None, "group_sides": gs, "main": main,
                "main_t": main_t, "notes": notes}
    if len(groups) == 1:
        return {"kind": "line", "pts": p, "sides": gsp, "keep": None, "group_sides": gs, "main": main,
                "main_t": main_t, "notes": notes}
    if len(groups) > 3:
        raise ValueError(f"開いたままの辺が {len(groups)} 面つながっています。足場の辺は L字（2面）・コの字（3面）まで。"
                         "それより多いときは辺を足して一周に閉じてください")
    pts, sp, keep = close_open_path(p, gsp)
    return {"kind": "open", "pts": pts, "sides": sp, "keep": keep, "group_sides": gs, "main": main, "main_t": main_t,
            "notes": notes}


def loop_face_index(pts: list, n_faces: int) -> list[int]:
    """一周の点（描いた順）の辺 g → 解いた外形の辺の番号（右回りなら逆にそろえる。manual.solve_manual_loop と同じ）."""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)) / 2.0
    return list(range(n_faces)) if area > 0 else [(n - 1 - g) % n for g in range(n_faces)]


def solve_side_job(job: dict, sides: list[dict], extra: dict):
    """plan_side_chain の形を解く → (世界座標の外形, 条件, 解いた組 [(名前, 結果)]). 主な辺と厚み・段数の違う面は、面ごとの
    足場の種類（face_forms: 厚み 300 は一側足場（狭い所）、600 は本足場（狭い幅））と面ごとの高さ（face_eaves_mm）にする."""
    from .cli import solve_groups
    from .manual import SIDE_RIGHT, eaves_for_levels, solve_manual, solve_manual_loop

    main = job["main"]
    eaves = eaves_for_levels(main["levels"], int(main["floor_mm"]))
    if job["kind"] == "line":
        a, b = job["pts"][0], job["pts"][-1]
        world, spec, local = solve_manual(a, b, job["sides"][0], main["standoff"], SIDE_RIGHT, eaves, extra)
        return world, spec, [("", local)]
    world, spec, r = solve_manual_loop(job["pts"], job["sides"], main["standoff"], eaves, extra, keep_sides=job["keep"])
    names = {e.edge_index: n for e, n in zip(r.model.plan.edges, r.model.plan.face_names())}
    fi = loop_face_index(job["pts"], len(job["pts"]))
    forms, heights, wide = {}, {}, []
    for g, sids in enumerate(job["group_sides"]):
        s = sides[sids[0]]
        f = side_form(s["thick_mm"], job["main_t"])
        if f:
            forms[names[fi[g]]] = f
        elif s["thick_mm"] != job["main_t"]:
            wide.append(names[fi[g]])
        heights[fi[g]] = eaves_for_levels(s["levels"], int(s["floor_mm"]))
    # face_eaves_mm に無い面は、いちばん高い面の高さになる（全体の軒高＝面の高さの最大）。段数が違うときは全部の面を入れる
    # （北だけ 6段にした一周の南・東・西も 6段で置かれた。実機 2026-10-31）
    if len(set(heights.values())) <= 1:
        heights = {}
    if wide:
        job["notes"].append(f"{'・'.join(wide)} の厚みは本足場の幅 {job['main_t']} にそろえました（つながった本足場は同じ幅）")
    if not forms and not heights:
        return world, spec, [("", r)]
    spec = {**spec, **({"face_forms": forms} if forms else {}), **({"face_eaves_mm": heights} if heights else {})}
    return world, spec, solve_groups(spec)
