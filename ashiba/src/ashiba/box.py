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


# 一側足場（厚み 300）の組み方（利用者の指定 2026-10-31: ブラケット足場と単管抱き足場はある？→ 選べるようにして）.
# 番号 → (名前, 解く条件, 本足場の一周の中の面にするときの面の切替の種類)。単管の2つは単管の系列で組む（cli.resolve_series_id）
ONE_KINDS = {
    1: ("ブラケット足場（支柱）", {"scaffold_form": "一側足場"}, "一側足場（狭い所）"),
    2: ("ブラケット足場（単管）", {"scaffold_form": "ブラケット足場", "bracket_post": "単管"}, "ブラケット足場（単管・狭い所）"),
    3: ("単管抱き足場", {"scaffold_form": "単管抱き足場"}, "単管抱き足場（狭い所）"),
}


def one_kind_of(value) -> int:
    try:
        k = int(float(value))
    except (TypeError, ValueError):
        return 1
    return k if k in ONE_KINDS else 1


def default_one(base: dict) -> tuple[Optional[int], int]:
    """条件の足場の種類 → (箱の厚みの初め（本足場なら None＝条件の幅）, 一側の組み方)."""
    form = str(base.get("scaffold_form") or "")
    if form in ("抱き足場", "単管抱き足場"):
        return 300, 3
    if form == "ブラケット足場":
        return 300, (2 if str(base.get("bracket_post") or "") == "単管" else 1)
    if form == "一側足場":
        return 300, 1
    return None, 1


def thickness_conditions(t_mm: float, standoff: float, one_kind: int = 1) -> tuple[str, dict]:
    """箱の厚み → (種類の名前, 解く条件). 利用者の指定 2026-10-30: 厚みで種類も変える.

    300 は一側足場（組み方は one_kind: ブラケット（支柱）・ブラケット（単管）・単管抱き）。本足場が入らない狭い所の足場として
    利用者が選んだので、本足場原則（安衛則561条の2）はただし書きとして要確認にする（one_row_by_choice。空きを「離れ＋厚み＋
    100」と仮に決めていたときは、床受けブラケット 900 の単管のブラケット足場が収まらず NG になった）。600・900・1200 は
    幅 610・914・1219 の本足場。"""
    t = snap_thickness(t_mm)
    if t == 300:
        name, cond, _f = ONE_KINDS[one_kind_of(one_kind)]
        return name, {**cond, "one_row_by_choice": True}
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
    """辺の向き（部品の回転）→ 単位ベクトル。縦・横から ±2° は縦・横にそろえ、それより斜めはそのまま（利用者の指定
    2026-10-31: 斜めの線にも対応できるようにしてちょ。斜めの辺の組は、組の向きにそろえた座標で解いて回して置く）."""
    deg = math.degrees(angle_rad) % 360.0
    if abs(deg - 90.0 * round(deg / 90.0)) <= AXIS_TOL_DEG:
        return [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)][round(deg / 90.0) % 4]
    return math.cos(math.radians(deg)), math.sin(math.radians(deg))


_PAR_COS = math.cos(math.radians(AXIS_TOL_DEG))   # これより揃っていれば平行・直角とみる
_PERP_SIN = math.sin(math.radians(AXIS_TOL_DEG))


def same_dir(d1, d2) -> bool:
    return d1[0] * d2[0] + d1[1] * d2[1] >= _PAR_COS


def chain_frame(sides: list[dict], chain: list[int]) -> float:
    """辺の組の向き（rad）: 始めの辺の向きを ±45° に収めたもの。縦・横の組は 0."""
    d = sides[chain[0]]["dir"]
    deg = math.degrees(math.atan2(d[1], d[0]))
    deg = (deg + 45.0) % 90.0 - 45.0
    return 0.0 if abs(deg) <= AXIS_TOL_DEG else math.radians(deg)


def rotate_pt(p, ang: float, pivot) -> tuple[float, float]:
    c, s = math.cos(ang), math.sin(ang)
    x, y = p[0] - pivot[0], p[1] - pivot[1]
    return pivot[0] + c * x - s * y, pivot[1] + s * x + c * y


def to_local(sides: list[dict], chain: list[int], ang: float, pivot) -> list[dict]:
    """辺の組を −ang 回した座標の辺（向きは縦・横にそろえる）. ang の組の向きで縦・横に解くため."""
    out = []
    for i in chain:
        s = dict(sides[i])
        s["a"] = rotate_pt(s["a"], -ang, pivot)
        d = rotate_pt(s["dir"], -ang, (0.0, 0.0))
        s["dir"] = side_axis(math.atan2(d[1], d[0]))
        out.append(s)
    return out


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
                corner_end: bool = True, one_kind: int = 1) -> dict:
    """部品 ashiba_side に入れるパラメータ（m）."""
    out = {"spanX": ",".join(str(int(v)) for v in spans),
           "szList": ",".join(str(int(c)) for c in sorted({int(c) for c in coins}, reverse=True)),
           "lenX": sum(spans) / 1000.0, "thick": snap_thickness(thick_mm) / 1000.0, "nLev": int(levels),
           "lev1": lev1_mm / 1000.0, "floorH": floor_mm / 1000.0,
           "topEdit": (lev1_mm + (levels - 1) * floor_mm) / 1000.0, "seriesId": series_id, "standoff": standoff / 1000.0,
           "zBase": max(0.0, base_mm) / 1000.0, "cornerE": bool(corner_end), "oneKind": one_kind_of(one_kind)}
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
            "series_id": str(params.get("seriesId") or ""), "one_kind": one_kind_of(params.get("oneKind"))}


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
    # 平行（まっすぐ続く）か直角に曲がる辺だけつなぐ。斜めの角（直角でない）はつながず、それぞれ1本で解く
    if dot < _PAR_COS and abs(dot) > _PERP_SIN:
        return None
    if dot < -0.5:
        return None
    if dot > 0.5:
        # まっすぐ続く辺（同じ面で厚みを変えるとき）: 同じ線の上で、終わりと始めが近い
        if abs(di[0] * (aj[1] - si["a"][1]) - di[1] * (aj[0] - si["a"][0])) > 1.0:
            return None
        g = abs((aj[0] - ei[0]) * di[0] + (aj[1] - ei[1]) * di[1])
        return g if g <= JOIN_TOL_MM else None
    # 直角に曲がる辺: 2本の線の交点（角）が si の終わりと sj の始めの近くにある
    den = di[0] * dj[1] - di[1] * dj[0]
    u = ((aj[0] - si["a"][0]) * dj[1] - (aj[1] - si["a"][1]) * dj[0]) / den
    c = (si["a"][0] + di[0] * u, si["a"][1] + di[1] * u)
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


def side_form(t_mm: int, main_mm: int, kind: int = 1, main_kind: int = 1) -> Optional[str]:
    """一周の主な辺（厚み main_mm・一側の組み方 main_kind）と違う辺の、面ごとの足場の種類（face_forms）。切り替えられなければ None."""
    t, m = snap_thickness(t_mm), snap_thickness(main_mm)
    if t == 300 and (m != 300 or one_kind_of(kind) != one_kind_of(main_kind)):
        return ONE_KINDS[one_kind_of(kind)][2]
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
        if groups and same_dir(ss[groups[-1][-1]]["dir"], s["dir"]):
            groups[-1].append(k)
        else:
            groups.append([k])
    if closed and len(groups) > 1 and same_dir(ss[groups[0][0]]["dir"], ss[groups[-1][0]]["dir"]):
        groups[0] = groups.pop() + groups[0]
    notes = []
    for g in groups:
        if len({(ss[k]["thick_mm"], ss[k]["levels"], ss[k].get("one_kind", 1)) for k in g}) > 1:
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


def joined_ends(job: dict, spec: dict, joined: tuple) -> list[list]:
    """辺の組の始め・終わりが斜めの角の隅のつなぎに続くとき、その端の妻側の手すりを外す指定（_joined_ends: [辺番号, "s"/"e"]）."""
    js, je = joined
    if not (js or je):
        return []
    if job["kind"] == "line":
        ei = int((spec.get("faces") or [0])[0])
        return ([[ei, "s"]] if js else []) + ([[ei, "e"]] if je else [])
    k = len(job["group_sides"])
    fi = loop_face_index(job["pts"], len(job["pts"]))
    ccw = _signed_area(job["pts"]) > 0
    out = []
    if js:
        out.append([fi[0], "s" if ccw else "e"])
    if je:
        out.append([fi[k - 1], "e" if ccw else "s"])
    return out


def solve_side_job(job: dict, sides: list[dict], extra: dict, joined: tuple = (False, False)):
    """plan_side_chain の形を解く → (世界座標の外形, 条件, 解いた組 [(名前, 結果)]). 主な辺と厚み・段数の違う面は、面ごとの
    足場の種類（face_forms: 厚み 300 は一側足場（狭い所）、600 は本足場（狭い幅））と面ごとの高さ（face_eaves_mm）にする."""
    from .cli import solve_groups
    from .manual import SIDE_RIGHT, eaves_for_levels, solve_manual, solve_manual_loop

    main = job["main"]
    eaves = eaves_for_levels(main["levels"], int(main["floor_mm"]))
    if job["main_t"] == 300 and one_kind_of(main.get("one_kind")) in (2, 3):
        # 単管で組む一側（ブラケット（単管）・単管抱き）は単管の系列の定尺で割り付ける（くさびの 1829 は単管の系列に無い）
        from .master import load_master
        from .manual import span_text

        coins = box_coins(load_master("tankan").span_lengths())
        new = [list(sp) if all(int(v) in coins for v in sp) else snap_spans(float(sum(sp)), coins) for sp in job["sides"]]
        if new != job["sides"]:
            k = len(job["group_sides"])
            job["notes"].append("単管で組むので、スパンを単管の定尺に直しました（"
                                + "・".join(f"{span_text(a)} → {span_text(b)}" for a, b in zip(job["sides"][:k], new[:k]))
                                + "）")
            job["sides"] = new
    if job["kind"] == "line":
        a, b = job["pts"][0], job["pts"][-1]
        world, spec, local = solve_manual(a, b, job["sides"][0], main["standoff"], SIDE_RIGHT, eaves, extra)
        je = joined_ends(job, spec, joined)
        if je:
            from .cli import solve_all

            spec = {**spec, "_joined_ends": je}
            local = solve_all(spec)
        return world, spec, [("", local)]
    world, spec, r = solve_manual_loop(job["pts"], job["sides"], main["standoff"], eaves, extra, keep_sides=job["keep"])
    je = joined_ends(job, spec, joined)
    if je:
        from .cli import solve_all

        spec = {**spec, "_joined_ends": je}
        r = solve_all(spec)
    names = {e.edge_index: n for e, n in zip(r.model.plan.edges, r.model.plan.face_names())}
    fi = loop_face_index(job["pts"], len(job["pts"]))
    forms, heights, wide = {}, {}, []
    for g, sids in enumerate(job["group_sides"]):
        s = sides[sids[0]]
        f = side_form(s["thick_mm"], job["main_t"], s.get("one_kind", 1), main.get("one_kind", 1))
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


# ---- 線から辺を置く（利用者の指定 2026-10-31: 線引っ張った範囲だけに配置するようにして 今一線だけで四角につくられてしまう）----
# 線1本は1辺、ポリラインは折れ目ごとに1辺。長さは線の範囲を超えない定尺の組み合わせ。足場を出す側は、閉じたポリラインなら外回り、
# 開いた線なら建物（近くのスラブ）の反対側、建物が無ければ線の右（始点から終点を見て）。

def snap_within(length_mm: float, coins: list[int]) -> list[int]:
    """線の長さを超えない定尺の組み合わせ（定尺の最大を並べ端数を定尺 0〜2 本で埋める組のうち、いちばん長いもの。1本多いごとに
    PIECE_PENALTY_MM 短いとみる）。いちばん短い定尺より短い線はその1本."""
    sz = sorted({int(c) for c in coins if c > 100}, reverse=True)
    if not sz:
        raise ValueError("定尺がありません")
    mx = sz[0]
    best = None
    for n in range(0, int(length_mm // mx) + 1):
        for i in range(0, len(sz) + 1):
            for j in range(i, len(sz) + 1):
                s = sz[i - 1] if i > 0 else 0
                t = sz[j - 1] if j > 0 else 0
                tot = n * mx + s + t
                if tot <= 100 or tot > length_mm + 1.0:
                    continue
                d = (length_mm - tot) + PIECE_PENALTY_MM * (n + (i > 0) + (j > 0))
                if best is None or d < best[0]:
                    best = (d, [mx] * n + [v for v in (s, t) if v])
    return best[1] if best else [sz[-1]]


def _signed_area(pts: list) -> float:
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)) / 2.0


def orient_path(segs: list, building: Optional[list] = None) -> tuple[list, str]:
    """線の区間の並び → 足場が進む向きの右に来るようにそろえた区間と、そろえ方の説明.
    閉じた線は左回り（足場は外回り）。開いた線は建物の外形（building）の重心が右にあれば逆向きにする（足場は建物の反対側）."""
    segs = [(tuple(map(float, a)), tuple(map(float, b))) for a, b in segs]
    rev = [(b, a) for a, b in reversed(segs)]
    closed = len(segs) >= 3 and math.dist(segs[0][0], segs[-1][1]) < 1.0
    if closed:
        return (segs if _signed_area([a for a, _b in segs]) > 0 else rev), "閉じた線の外回り"
    if building:
        cx = sum(p[0] for p in building) / len(building)
        cy = sum(p[1] for p in building) / len(building)
        # 重心にいちばん近い区間で、重心が線のどちら側か
        def dist(seg):
            (ax, ay), (bx, by) = seg
            L2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1.0
            t = max(0.0, min(1.0, ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / L2))
            return math.hypot(cx - ax - t * (bx - ax), cy - ay - t * (by - ay))
        (ax, ay), (bx, by) = min(segs, key=dist)
        right = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0
        return (rev if right else segs), "建物の反対側"
    return segs, "線の右（始点から終点を見て。反対に出すときは線を逆向きに引く）"


def sides_from_path(segs: list, coins: list[int]) -> list[tuple[tuple[float, float], float, list[int], bool]]:
    """向きをそろえた区間の並び → 辺 [(始点, 向きの角度, スパン, 終わりの出隅を描くか)]. 長さは区間を超えない定尺の組み合わせ."""
    closed = len(segs) >= 3 and math.dist(segs[0][0], segs[-1][1]) < 1.0
    dirs = [side_axis(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in segs]      # 斜めの線はその向きのまま
    out = []
    for k, (a, b) in enumerate(segs):
        d = dirs[k]
        nxt = dirs[(k + 1) % len(segs)] if closed or k + 1 < len(segs) else None
        corner = nxt is not None and d[0] * nxt[1] - d[1] * nxt[0] > 0.5      # 左に曲がる角（出隅。直角に近いとき）
        out.append((a, math.atan2(d[1], d[0]), snap_within(math.dist(a, b), coins), corner))
    return out


# ---- 斜めの角のつなぎ（利用者の指定 2026-10-31: 斜めの角もつながるようにしてちょ 無理な場合はかど合わせてアンチをし単管手すり
# 作成か足場板と単管手すりにするか）----
# 割付は縦・横しか解けないので、直角でない角の2本の足場はそれぞれ1本で解き、角に向く端の妻側の手すりを外す（_joined_ends）。
# 2本の足場の端のあいだのすき間（出隅は三角・入隅は前の足場を縮めたあとの四角）を「隅のつなぎ」（部品 ashiba_cfill）で
# ふさぐ: 各段に作業床（アンチ か 足場板）・その下に単管の受け・外に向く辺に単管手すり（上桟・中桟）と幅木。

CORNER_DECKS = ("アンチ", "足場板")
ROW_W = {300: 400.0, 600: 610.0, 900: 914.0, 1200: 1219.0}   # 厚み → 内側の列から外側の端までの目安（一側はブラケット＋支柱）
CORNER_TOL_MM = 1000.0


def _normal(d) -> tuple[float, float]:
    """足場の出る側（進む向きの右）."""
    return d[1], -d[0]


def band(a, d, L: float, W: float) -> list[tuple[float, float]]:
    """内側の列 a→a+d·L から右へ幅 W の帯（左回りの4点）."""
    n = _normal(d)
    e = (a[0] + d[0] * L, a[1] + d[1] * L)
    return [(a[0] + n[0] * W, a[1] + n[1] * W), (e[0] + n[0] * W, e[1] + n[1] * W), e, tuple(a)]


def _overlap(p: list, q: list) -> bool:
    """凸多角形 p・q が面積をもって重なるか（分離軸。辺が接するだけは重ならない）."""
    for poly in (p, q):
        for k in range(len(poly)):
            x1, y1 = poly[k]
            x2, y2 = poly[(k + 1) % len(poly)]
            ax, ay = y1 - y2, x2 - x1
            pa = [ax * x + ay * y for x, y in p]
            qa = [ax * x + ay * y for x, y in q]
            if max(pa) <= min(qa) + 1.0 or max(qa) <= min(pa) + 1.0:
                return False
    return True


def _cross_line(p, d, q, e) -> Optional[tuple[float, float]]:
    """直線 p+d·t と q+e·s の交点."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return p[0] + d[0] * t, p[1] + d[1] * t


def oblique_corners(sides: list[dict], chains: list[tuple[list[int], bool]]) -> list[dict]:
    """開いた組の終わりの辺 i と別の組の始めの辺 j が、直角でない角（線の交点）で出会うところ → [{"i", "j", "c", "convex"}].
    線の交点が i の終わり・j の始めから CORNER_TOL_MM 以内。立つ高さ・系列の同じ辺だけ."""
    ends = [ch[-1] for ch, closed in chains if not closed]
    starts = [ch[0] for ch, closed in chains if not closed]
    out = []
    used = set()
    cand = []
    for i in ends:
        for j in starts:
            si, sj = sides[i], sides[j]
            if i == j or abs(si["base_mm"] - sj["base_mm"]) > 1.0 or (si.get("series_id") or "") != (sj.get("series_id") or ""):
                continue
            di, dj = si["dir"], sj["dir"]
            dot = di[0] * dj[0] + di[1] * dj[1]
            if dot >= _PAR_COS or abs(dot) <= _PERP_SIN or dot <= -_PAR_COS:
                continue
            c = _cross_line(si["a"], di, sj["a"], dj)
            if c is None:
                continue
            Li = float(sum(si["spans"]))
            ti = (c[0] - si["a"][0]) * di[0] + (c[1] - si["a"][1]) * di[1]
            tj = (c[0] - sj["a"][0]) * dj[0] + (c[1] - sj["a"][1]) * dj[1]
            if abs(ti - Li) <= CORNER_TOL_MM and abs(tj) <= CORNER_TOL_MM and ti > 0:
                cand.append((abs(ti - Li) + abs(tj), i, j, c, di[0] * dj[1] - di[1] * dj[0] > 0))
    for _g, i, j, c, convex in sorted(cand):
        if i in used or ("j", j) in used:
            continue
        used |= {i, ("j", j)}
        out.append({"i": i, "j": j, "c": c, "convex": convex})
    return out


def trim_for_corner(si: dict, sj: dict, coins: list[int]) -> Optional[list[int]]:
    """入隅（右に曲がる斜めの角）で、前の辺 si の帯が後の辺 sj の帯に重なるなら、重ならない長さまで縮めたスパン（定尺の
    組み合わせ）。重ならなければ None."""
    Wi = ROW_W.get(int(si["thick_mm"]), 914.0)
    Wj = ROW_W.get(int(sj["thick_mm"]), 914.0)
    bj = band(sj["a"], sj["dir"], float(sum(sj["spans"])), Wj)
    L = float(sum(si["spans"]))
    if not _overlap(band(si["a"], si["dir"], L, Wi), bj):
        return None
    t = 0.0
    while t < L and _overlap(band(si["a"], si["dir"], L - t, Wi), bj):
        t += 10.0
    return snap_within(max(1.0, L - t), coins)


def _ray_hit(p, d, poly: list) -> Optional[tuple[tuple[float, float], int]]:
    """半直線 p+d·t（t≧0）が多角形の辺に最初に当たる点と、その辺の番号（辺 k は poly[k]→poly[k+1]）."""
    best = None
    for k in range(len(poly)):
        a, b = poly[k], poly[(k + 1) % len(poly)]
        e = (b[0] - a[0], b[1] - a[1])
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-9:
            continue
        t = ((a[0] - p[0]) * e[1] - (a[1] - p[1]) * e[0]) / den
        u = ((a[0] - p[0]) * d[1] - (a[1] - p[1]) * d[0]) / den
        if t >= -1e-6 and -1e-9 <= u <= 1.0 + 1e-9 and (best is None or t < best[0]):
            best = (t, (p[0] + d[0] * t, p[1] + d[1] * t), k)
    return None if best is None else (best[1], best[2])


def corner_fill(end_i, di, Wi: float, start_j, dj, Wj: float, c, convex: bool) -> dict:
    """隅のつなぎの床の形 → {"poly": 点（左回り）, "rail": 手すりを付ける辺の番号, "open_j": 後の足場の外の手すりを外す長さ}.

    出隅: 前の足場の終わりの端 → その外 → 後の足場の始めの外 → 後の始めの端 → 線の角（すき間が三角か五角）。外の辺に手すり。
    入隅: 前の足場（重ならないよう縮めたもの）の終わりの端から、外の線を後の足場の外の辺か始めの端に当たるまで延ばし、
          後の足場の始めの端へ戻る形。前の足場の外の延長に手すり。後の足場へは始めの端（妻側の手すりを外す）から渡る."""
    ni, nj = _normal(di), _normal(dj)
    pi, qi = tuple(end_i), (end_i[0] + ni[0] * Wi, end_i[1] + ni[1] * Wi)
    pj, qj = tuple(start_j), (start_j[0] + nj[0] * Wj, start_j[1] + nj[1] * Wj)
    if convex:
        pts = [pi, qi, qj, pj, tuple(c)]
    else:
        # 前の足場の終わりの端の内・外から前へ延ばした線が、後の足場の帯に当たるところまでの帯。2つの当たる点が帯の別の辺に
        # あるときは、その間の帯の角（後の足場の始めの外の角など）を通る（まっすぐ結ぶと後の足場の帯に食い込む）
        bj = band(pj, dj, 1.0e6, Wj)
        hq, hp = _ray_hit(qi, di, bj), _ray_hit(pi, di, bj)
        if hq is None or hp is None:
            pts = [pi, qi, qj, pj]
        else:
            n4 = len(bj)
            fwd = [(hq[1] + 1 + k) % n4 for k in range((hp[1] - hq[1]) % n4)]
            bwd = [(hq[1] - k) % n4 for k in range((hq[1] - hp[1]) % n4)]
            plen = lambda ks: sum(math.dist(a, b) for a, b in zip([hq[0]] + [bj[k] for k in ks], [bj[k] for k in ks] + [hp[0]]))
            mid = [bj[k] for k in min((fwd, bwd), key=plen)]                # 近い方を回る（帯の遠い端を回らない）
            pts = [pi, qi, hq[0]] + mid + [hp[0]]
    open_j = 0.0
    # 重なる点（端がちょうど角のとき）を除く
    clean = []
    for p in pts:
        if not clean or math.dist(clean[-1], p) > 1.0:
            clean.append(p)
    if len(clean) > 2 and math.dist(clean[0], clean[-1]) <= 1.0:
        clean.pop()
    # 手すりの辺の番号は、除いた点に合わせて外の辺（qi の次の辺）を探し直す
    k = next((n for n, p in enumerate(clean) if math.dist(p, qi) <= 1.0), 1)
    rail = [k]
    if _signed_area(clean) < 0:
        clean = list(reversed(clean))
        rail = [(len(clean) - 2 - k) % len(clean)]
    return {"poly": clean, "rail": rail, "open_j": open_j}


def corner_quantities(fill: dict, levels: int, deck: str = "アンチ") -> list[tuple[str, int, str]]:
    """隅のつなぎ1か所の材料の目安 → [(品名, 数, 注)]. 床は外の辺に平行に並べ、幅 240（足場板）・500（アンチ）で数える."""
    poly = fill["poly"]
    k = fill["rail"][0]
    a, b = poly[k], poly[(k + 1) % len(poly)]
    edge = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / (edge or 1.0), (b[1] - a[1]) / (edge or 1.0)
    depth = max(abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) for p in poly)
    span = max(abs((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) for p in poly)
    w = 500.0 if deck == "アンチ" else 240.0
    boards = max(1, math.ceil(depth / w))
    tube_len = edge + 600.0                              # 両側の足場の支柱に 300 ずつかけてクランプで留める
    std = next((L for L in (1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000) if L >= tube_len), 6000)
    out = [(f"{deck}（長さ {span + 300:.0f} 以上・{'幅500' if deck == 'アンチ' else '幅240 を切って'}）", boards * levels,
            "外の辺に平行に並べる"),
           (f"単管 {std / 1000:.1f}m（手すり 上桟・中桟）", 2 * levels, f"外の辺 {edge:.0f}"),
           (f"単管（床の受け・長さ {depth + 300:.0f} 以上）", 2 * levels, "外の辺に直角に2本。アンチは平行な受けにしか掛からない"),
           ("自在クランプ（斜めの取り付け）", 8 * levels, "手すり2本・受け2本の両端"),
           (f"幅木（足場板 {std / 1000:.1f}m）", levels, "外の辺")]
    if edge > 1850.0:
        out.append(("単管の支柱（ジャッキ・敷板とも）", 1, f"外の辺 {edge:.0f} が 1800 を超えるので中間に1本"))
    return out
