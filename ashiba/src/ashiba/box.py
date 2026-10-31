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


def corner_fill(end_i, di, Wi: float, start_j, dj, Wj: float, c, convex: bool,
                posts_j: Optional[list] = None) -> dict:
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
            end = hq[0]
            if posts_j:
                # 手すりの端は近い支柱に留める（利用者の指定 2026-10-31: 入隅の手すりは近い支柱に留めて）。後の足場の外の列の
                # 支柱のうち、外の線を延ばして当たる所にいちばん近いもの
                end = min(posts_j, key=lambda q: math.dist(q, hq[0]))
                end = (float(end[0]), float(end[1]))
            pts = [pi, qi, end] + mid + [hp[0]]
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
    # 渡る向き: 前の足場の終わりの端の中心 → 後の足場の始めの端の中心（アンチはこの向きに、両側の床に掛けて並べる）
    walk = (((pi[0] + qi[0]) / 2, (pi[1] + qi[1]) / 2), ((pj[0] + qj[0]) / 2, (pj[1] + qj[1]) / 2), max(Wi, Wj),
            (pi, qi), (pj, qj), (di[0] + dj[0], di[1] + dj[1]))
    return {"poly": clean, "rail": rail, "open_j": open_j, "walk": walk}


def corner_quantities(fill: dict, levels: int, deck: str = "アンチ", anti_l: int = 914, anti_w: int = 240,
                      layout: Optional[dict] = None) -> list[tuple[str, int, str]]:
    """隅のつなぎ1か所の材料の目安 → [(品名, 数, 注)].

    利用者の指定（2026-10-31: 三角の板じゃなく 900アンチを乗せる クランプもつけてね）: 外の辺に直角な単管の受け2本（間＝アンチの
    長さ）に、アンチ（長さ anti_l・幅 anti_w）を外の辺に平行に、外の辺から床の奥行きまで並べて掛ける（部品 ashiba_cfill と同じ数え方）."""
    poly = fill["poly"]
    k = fill["rail"][0]
    a, b = poly[k], poly[(k + 1) % len(poly)]
    edge = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / (edge or 1.0), (b[1] - a[1]) / (edge or 1.0)
    depth = max(max((p[0] - a[0]) * (-uy) + (p[1] - a[1]) * ux for p in poly), 0.0)
    boards = min(8, max(1, math.ceil(depth / anti_w)))
    n_sup = 2 if layout is None else len(layout["supports"])
    if layout is not None:
        boards = len(layout["planks"])
    tube_len = edge + 600.0                              # 両側の足場の支柱に 300 ずつかけてクランプで留める
    std = next((L for L in (1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000) if L >= tube_len), 6000)
    sup = next((L for L in (1000, 1500, 2000, 2500, 3000) if L >= depth + 300.0), 3000)
    if layout is not None:
        anti_l = int(layout.get("anti_l", anti_l))
    name = f"アンチ {anti_l}×{anti_w}" if deck == "アンチ" else f"足場板（{anti_l + 300} 以上に切る）"
    out = [(name, boards * levels, f"渡る向きに {boards}枚ずつ（両側の本足場の床に {ANTI_LAP_MM:.0f} 以上掛ける）"),
           (f"単管 {std / 1000:.1f}m（手すり 上桟・中桟）", 2 * levels, f"外の辺 {edge:.0f}。両側の足場の支柱に 300 ずつ掛ける"),
           (f"単管 {sup / 1000:.1f}m（アンチの受け）", n_sup * levels,
            f"外の辺に直角に、間 {anti_l}。すき間の中だけ（アンチは両側の本足場のアンチの上に重ねて載せる）"),
           ("自在クランプ", (4 + 2 * n_sup) * levels, f"手すり2本の両端を支柱に・受け {n_sup}本の両端を本足場の端の布材に"),
           (f"幅木（足場板 {std / 1000:.1f}m）", levels, "外の辺")]
    if edge > 1850.0:
        out.append(("単管の支柱（ジャッキ・敷板とも）", 1, f"外の辺 {edge:.0f} が 1800 を超えるので中間に1本"))
    out = [r for r in out if r[1] > 0]
    out.append(("（確認）", 0, "アンチは両側の本足場のアンチの上に重ねて載せる（段差 45。つまずかないよう端を番線で留め、"
                              "重ねは 200 以上）"))
    return out

DECK_TOP_MM = 66.4      # 本足場の布板の上面（段の高さ＝布材の芯から 布材の半径 21.35＋板の厚み 45。部品 ashiba_line の 870）
TUBE_R_MM = 24.3        # 単管 φ48.6


ANTI_LENGTHS = {"inch": (914, 1219, 1524, 1829), "metric": (900, 1200, 1500, 1800)}
ANTI_LAP_MM = 150.0      # アンチを両側の本足場の床に掛ける長さ（片側）


def corner_layout(fill: dict, anti_l: float = 914.0, anti_w: float = 240.0) -> dict:
    """隅のつなぎの部材の配置（世界座標 mm）.

    利用者の指定（2026-10-31: 高さがずれている 本足場のアンチの上に乗せるようにして／渡るようになってないよ）:
    - アンチ: 渡る向き（前の足場の終わりの端の中心 → 後の足場の始めの端の中心）に、両側の本足場のアンチの上に ANTI_LAP_MM
      ずつ掛かる長さ（anti_l で足りなければ次の定尺）で、渡る幅（足場の幅）いっぱいに並べる。下面は本足場の布板の上面
    - 受けの単管: アンチの両端の下に、渡る向きに直角に。隅のすき間（床の形）の中だけ（両側の床に載る所は要らない）
    → {"planks": [(x, y)]（アンチの始めの角）, "ang": アンチの向き（度）, "anti_l": アンチの長さ, "supports": [((x, y), (x, y))]}"""
    poly = fill["poly"]
    edges, bis = None, None
    if "walk" in fill:
        (ax, ay), (bx, by), width = fill["walk"][:3]
        edges = fill["walk"][3:5] if len(fill["walk"]) > 4 else None
        bis = fill["walk"][5] if len(fill["walk"]) > 5 else None
    else:
        k = fill["rail"][0]
        a, b = poly[k], poly[(k + 1) % len(poly)]
        ax, ay, bx, by, width = a[0], a[1], b[0], b[1], 0.0
    gap = math.hypot(bx - ax, by - ay) or 1.0
    u = ((bx - ax) / gap, (by - ay) / gap)
    if bis is not None and math.hypot(*bis) > 1e-6:
        # 渡る向きは前の足場の向きと後の足場の向きの二等分（端の中心どうしを結ぶと、入隅では後の足場の始めの端とほぼ平行に
        # なってアンチが遠くへ飛んだ。実機 2026-10-31）
        bl = math.hypot(*bis)
        u = (bis[0] / bl, bis[1] / bl)
    nI = (-u[1], u[0])
    m = ((ax + bx) / 2.0, (ay + by) / 2.0)
    std = ANTI_LENGTHS["inch" if int(anti_l) in ANTI_LENGTHS["inch"] else "metric"]
    if width <= 0:
        width = max(max((p[0] - m[0]) * nI[0] + (p[1] - m[1]) * nI[1] for p in poly) * 2, anti_w)
    n = min(8, max(1, math.ceil((width - 20.0) / anti_w)))
    off0 = -n * anti_w / 2.0
    # どのアンチも、前の足場の端の線より ANTI_LAP_MM 手前から、後の足場の始めの端の線より ANTI_LAP_MM 先まで掛かる長さ
    # （斜めの角では端の線が渡る向きに斜めなので、アンチの列ごとに長さが違う。いちばん長いものに合わせる）
    t0, t1 = -gap / 2.0, gap / 2.0
    if edges:
        def along(off, e):
            q = (m[0] + nI[0] * off, m[1] + nI[1] * off)
            x = _cross_line(q, u, e[0], (e[1][0] - e[0][0], e[1][1] - e[0][1]))
            return None if x is None else (x[0] - q[0]) * u[0] + (x[1] - q[1]) * u[1]
        offs = [off0 + anti_w * i + d for i in range(n) for d in (0.0, anti_w)]
        ti = [v for v in (along(o, edges[0]) for o in offs) if v is not None]
        tj = [v for v in (along(o, edges[1]) for o in offs) if v is not None]
        if ti and tj:
            t0, t1 = min(ti), max(tj)
    need = (t1 - t0) + 2 * ANTI_LAP_MM
    L = next((float(v) for v in std if v >= anti_l and v >= need), float(std[-1]))
    s0 = (t0 + t1) / 2.0 - L / 2.0
    planks = [(m[0] + u[0] * s0 + nI[0] * (off0 + anti_w * i), m[1] + u[1] * s0 + nI[1] * (off0 + anti_w * i))
              for i in range(n)]
    sups = []
    for s in (s0 + 30.0, s0 + L - 30.0):
        p0 = (m[0] + u[0] * s, m[1] + u[1] * s)
        ts = []
        for kk in range(len(poly)):
            c, d = poly[kk], poly[(kk + 1) % len(poly)]
            e = (d[0] - c[0], d[1] - c[1])
            den = nI[0] * e[1] - nI[1] * e[0]
            if abs(den) < 1e-9:
                continue
            tt = ((c[0] - p0[0]) * e[1] - (c[1] - p0[1]) * e[0]) / den
            w = ((c[0] - p0[0]) * nI[1] - (c[1] - p0[1]) * nI[0]) / den
            if -1e-9 <= w <= 1.0 + 1e-9:
                ts.append(tt)
        ts = sorted(set(round(v, 3) for v in ts))
        if len(ts) >= 2 and ts[-1] - ts[0] >= 150.0:                     # 150 未満はアンチが本足場の床に載るので要らない
            sups.append(((p0[0] + nI[0] * ts[0], p0[1] + nI[1] * ts[0]), (p0[0] + nI[0] * ts[-1], p0[1] + nI[1] * ts[-1])))
    return {"planks": planks, "ang": math.degrees(math.atan2(u[1], u[0])), "anti_l": L, "supports": sups}

# ---- 隅のアンチを支柱と支柱の間に（利用者の指定 2026-10-31: 支柱と支柱の間にしてね 近すぎる時は足場のスパンを下げて渡れるように
# 工夫してね）----
# 両側の足場の端の支柱の間に単管の受けを2本（前の足場の終わりの2本の支柱・後の足場の始めの2本の支柱を結ぶ線に沿って。両端を
# 支柱に自在クランプ）渡し、外の支柱どうしを結ぶ線に平行にアンチを外から 240 ずつ並べて両端を受けに掛ける。斜めの角は受けが
# 平行でないので列ごとに長さが違う: その列に入るいちばん長い定尺（両端のつめが受けに掛かるよう列の長さ＋HOOK_REACH_MM まで）。
# 外の列に最短のアンチも入らないほど支柱が近いときは、前の足場の最後のスパンを下げてすき間を広げる（between_trim）。

HOOK_REACH_MM = 40.0       # アンチのつめが受けの単管に掛かる分（列の長さよりこれだけ長くてよい）
MIN_HOLE_MM = 30.0         # これを超える残りのすき間は、すき間板（足場板を切って番線止め）でふさぐ（安衛則563条 床材間 3cm）


def between_layout(fill: dict, anti_lengths: tuple, di, anti_w: float = 240.0) -> dict:
    """隅のつなぎの、支柱の間に掛けるアンチの並び（世界座標 mm）.

    受けの単管は2本: 前の足場の終わりの2本の支柱を結ぶ線と、後の足場の始めの2本の支柱を結ぶ線（両端を支柱に自在クランプ）。
    アンチは前の足場の向き di に、前の足場の幅を 240 前後の列に分けて並べ、手前のつめを前の受けに、先のつめを後の受けに掛ける。
    長さは列の中心での受けから受けまでに入るいちばん長い定尺（＋HOOK_REACH_MM まで）。後の受けは斜めなので列の両側で長さが
    違い、その差が残りのすき間になる（MIN_HOLE_MM を超えればすき間板）.
    → {"planks": [((x, y) 手前の内側の角, 長さ)], "ang": アンチの向き（度）, "w": 列の幅, "supports": [((x, y), (x, y))],
       "holes": [列ごとの残りのすき間 mm], "short": いちばん短い列の長さ, "ok": どの列にもアンチが入るか}"""
    walk = fill.get("walk")
    if not walk or len(walk) < 5:
        return {"planks": [], "ang": 0.0, "w": anti_w, "supports": [], "holes": [], "short": 0.0, "ok": False}
    (pi, qi), (pj, qj) = walk[3], walk[4]
    wi = math.dist(pi, qi) or 1.0
    s_dir = ((qi[0] - pi[0]) / wi, (qi[1] - pi[1]) / wi)          # 内側の支柱から外側の支柱へ
    tj = (qj[0] - pj[0], qj[1] - pj[1])
    std = sorted(int(v) for v in anti_lengths)

    def reach(s):
        o = (pi[0] + s_dir[0] * s, pi[1] + s_dir[1] * s)
        x = _cross_line(o, di, pj, tj)
        return None if x is None else (x[0] - o[0]) * di[0] + (x[1] - o[1]) * di[1]

    planks, holes, short, ok = [], [], 1e9, True
    n = max(1, int(round(wi / anti_w)))
    w = wi / n
    for k in range(n):
        ra, rb, rc = reach(k * w), reach((k + 1) * w), reach((k + 0.5) * w)
        if ra is None or rb is None or rc is None:
            ok = False
            continue
        short = min(short, rc)
        fit = [v for v in std if v <= rc + HOOK_REACH_MM]
        if not fit:
            ok = False
            holes.append(max(ra, rb))
            continue
        L = float(fit[-1])
        o = (pi[0] + s_dir[0] * k * w, pi[1] + s_dir[1] * k * w)
        planks.append(((o[0], o[1]), L))
        holes.append(max(ra, rb) - L)
    sups = [((pi[0] - di[0] * TUBE_R_MM, pi[1] - di[1] * TUBE_R_MM), (qi[0] - di[0] * TUBE_R_MM, qi[1] - di[1] * TUBE_R_MM)),
            ((pj[0], pj[1]), (qj[0], qj[1]))]
    # 床の外の線（利用者の指定 2026-10-31: 外側にも単管で手すりして 足場板繋げつようにして）: 外の列は前の足場の外の線に沿って
    # 後の受けの線まで延びる（X）。手すり・幅木は 前の外の支柱 → X → 後の外の支柱（X が後の受けの区間の外のとき）。
    # 足場板は後の受けの線に沿って、内側の支柱から X（か後の外の支柱）まで一続きに、三角のすき間の幅だけの枚数を並べる
    X = _cross_line(qi, di, pj, tj)
    tl = math.hypot(*tj) or 1.0
    tdir = (tj[0] / tl, tj[1] / tl)
    sx = ((X[0] - pj[0]) * tdir[0] + (X[1] - pj[1]) * tdir[1]) if X else tl
    if X is not None and sx > tl + 1.0:
        outline = [pi, qi, X, qj, pj]
        rails = [1, 2]
    else:
        outline = [pi, qi, qj, pj]
        rails = [1]
    hole = max(holes) if holes else 0.0
    n_b = max(1, math.ceil((hole + 100.0) / anti_w)) if hole > MIN_HOLE_MM else 0
    dj_in = (tdir[1], -tdir[0])                       # 後の受けの線から前の足場の側（tdir の右）
    if (pi[0] - pj[0]) * dj_in[0] + (pi[1] - pj[1]) * dj_in[1] < 0:
        dj_in = (-dj_in[0], -dj_in[1])
    # 足場板は床の外形の中で切りそろえる（両端を延ばしていたときは、外の手すりの外と建物の側へ飛び出した。実機 2026-10-31:
    # 黄色いのが飛び出ている）。列の両側の線が外形に入る区間の重なり
    def inside(d):
        q = (pj[0] + dj_in[0] * d, pj[1] + dj_in[1] * d)
        ts = []
        for m in range(len(outline)):
            c0, c1 = outline[m], outline[(m + 1) % len(outline)]
            ed = (c1[0] - c0[0], c1[1] - c0[1])
            den = tdir[0] * ed[1] - tdir[1] * ed[0]
            if abs(den) < 1e-9:
                continue
            tt = ((c0[0] - q[0]) * ed[1] - (c0[1] - q[1]) * ed[0]) / den
            uu = ((c0[0] - q[0]) * tdir[1] - (c0[1] - q[1]) * tdir[0]) / den
            if -1e-9 <= uu <= 1.0 + 1e-9:
                ts.append(tt)
        return (min(ts), max(ts)) if len(ts) >= 2 else None

    boards = []
    for k in range(n_b):
        a, b = inside(anti_w * k + 5.0), inside(anti_w * (k + 1) - 5.0)
        if not a or not b:
            continue
        t0, t1 = max(a[0], b[0]), min(a[1], b[1])
        if t1 - t0 < 100.0:
            continue
        o = (pj[0] + dj_in[0] * anti_w * (k + 1) + tdir[0] * t0, pj[1] + dj_in[1] * anti_w * (k + 1) + tdir[1] * t0)
        boards.append((o, t1 - t0))
    return {"planks": planks, "ang": math.degrees(math.atan2(di[1], di[0])), "w": w, "supports": sups, "holes": holes,
            "short": 0.0 if short == 1e9 else short, "ok": ok, "outline": outline, "rails": rails, "boards": boards,
            "board_ang": math.degrees(math.atan2(tdir[1], tdir[0])), "board_left": dj_in}


def between_trim(si: dict, sj: dict, coins: list[int], c, convex: bool, wi: float, wj: float,
                 anti_lengths: tuple) -> Optional[list[int]]:
    """支柱が近すぎて、隅のすき間の列に最短のアンチも入らないとき、前の足場の最後のスパンを下げた（短くした）スパン（入るように
    なるまで。下げても入らなければ None）. そのままで入るなら None."""
    def ok(spans):
        L = float(sum(spans))
        end = (si["a"][0] + si["dir"][0] * L, si["a"][1] + si["dir"][1] * L)
        f = corner_fill(end, si["dir"], wi, sj["a"], sj["dir"], wj, c, convex)
        return between_layout(f, anti_lengths, si["dir"])["ok"]

    if ok(si["spans"]):
        return None
    sp = list(si["spans"])
    cs = sorted({int(v) for v in coins}, reverse=True)
    for _ in range(12):
        smaller = [v for v in cs if v < sp[-1]]
        if smaller:
            sp[-1] = smaller[0]
        elif len(sp) > 1:
            sp = sp[:-1]
        else:
            return None
        if ok(sp):
            return sp
    return None


LEDGER_R_MM = 21.35       # 布材・腕木 φ42.7 の半径（アンチの下面＝段の高さ＋これ。本足場の布板と同じ）


def anti_lengths(coins) -> tuple:
    """系列の定尺（スパン）→ 隅に掛けるアンチの長さの候補（610 以上）."""
    return tuple(sorted({int(v) for v in coins if int(v) >= 600}))


def between_quantities(planks: list, boards: list, fill: dict, levels: int, n_posts: int = 0) -> list[tuple[str, int, str]]:
    """支柱の間に掛ける隅のつなぎ1か所の材料の目安 → [(品名, 数, 注)]. 手すり・幅木は床の外の線（fill の poly・rail）."""
    from collections import Counter

    poly = fill["poly"]
    edges = [math.dist(poly[k], poly[(k + 1) % len(poly)]) for k in fill["rail"]]
    tubes = [next((L for L in (1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000) if L >= e + 600.0), 6000) for e in edges]
    out = [(f"アンチ {L}", n * levels, "両側の足場の端の布材に掛ける") for L, n in sorted(Counter(int(L) for _o, L in planks).items())]
    if boards:
        per = sum(math.ceil(L / 4000.0) for _o, L in boards)
        out.append(("足場板 4m", per * levels, f"後の受けの線に沿って一続きに {len(boards)}列（アンチの先の三角をふさぐ。番線止め）"))
    for e, L in Counter(tubes).items():
        out.append((f"単管 {e / 1000:.1f}m（手すり 上桟・中桟）", 2 * L * levels, "床の外の線。両端を支柱か手すりの角に"))
    out += [("自在クランプ", 4 * len(edges) * levels, "手すりの両端（支柱・角の支柱）"),
            ("幅木（足場板）", len(edges) * levels, "床の外の線")]
    if n_posts:
        out.append(("単管の支柱（ジャッキ・敷板とも）", n_posts, "手すりの曲がり角（外の角まで 1800 を超える）"))
    return out


# ---- 隅は足場板を本足場のアンチの上に載せて番線で留める（利用者の指定 2026-10-31: 支柱間を単管で結ぶ 白はいらない 黄色の足場板を
# 本足場のアンチ上に乗せて番線で固定する）----
BOARD_LAP_MM = 200.0              # 足場板を両側の本足場のアンチに重ねる長さ（安衛則563条 重ねは 20cm 以上）
BOARD_W_MM = 240.0
BOARD_LENGTHS = (2000, 3000, 4000)


def _in_poly(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def board_layout(fill: dict, band_i: list, band_j: list) -> dict:
    """隅のつなぎの足場板の並び（世界座標 mm）. 渡る向き（前後の足場の向きの二等分）に、足場の幅を 240 ずつの列に分け、
    列ごとに前の足場の床から後の足場の床まで、両側に BOARD_LAP_MM 以上重なる長さ。前の足場・隅のすき間・後の足場の床の外へは
    出さない（列の両側の線がその中にある区間だけ）. 床に BOARD_LAP_MM 重ならない列は置かない.
    → {"boards": [((x, y) 始めの右の角, 長さ)], "ang": 向き（度）, "ties": [((x, y), (x, y))]（支柱を結ぶ単管）}"""
    walk = fill["walk"]
    (pi, qi), (pj, qj) = walk[3], walk[4]
    bis = walk[5]
    bl = math.hypot(*bis) or 1.0
    u = (bis[0] / bl, bis[1] / bl)
    lf = (-u[1], u[0])
    m = ((walk[0][0] + walk[1][0]) / 2.0, (walk[0][1] + walk[1][1]) / 2.0)
    regions = [band_i, fill["poly"], band_j]
    inside = lambda p: any(_in_poly(p, r) for r in regions)
    width = max(math.dist(pi, qi), math.dist(pj, qj))
    w = BOARD_W_MM

    def row(off):
        """横の位置 off（中心線から左へ）の列の足場板 → ((始めの右の角), 長さ) か None."""
        ivs = []
        for side in (off + 5.0, off + w - 5.0):
            q = (m[0] + lf[0] * side, m[1] + lf[1] * side)
            if not inside(q):
                return None
            lo = hi = 0.0
            while lo > -3000.0 and inside((q[0] + u[0] * (lo - 10.0), q[1] + u[1] * (lo - 10.0))):
                lo -= 10.0
            while hi < 3000.0 and inside((q[0] + u[0] * (hi + 10.0), q[1] + u[1] * (hi + 10.0))):
                hi += 10.0
            ivs.append((lo, hi))
        lo, hi = max(v[0] for v in ivs), min(v[1] for v in ivs)

        def cross_t(e):
            x = _cross_line((m[0] + lf[0] * (off + w / 2), m[1] + lf[1] * (off + w / 2)), u, e[0],
                            (e[1][0] - e[0][0], e[1][1] - e[0][1]))
            return None if x is None else (x[0] - m[0]) * u[0] + (x[1] - m[1]) * u[1]
        ti, tj = cross_t((pi, qi)), cross_t((pj, qj))
        if ti is None or tj is None:
            return None
        a, b = min(ti, tj) - BOARD_LAP_MM, max(ti, tj) + BOARD_LAP_MM
        if a < lo - 1.0 or b > hi + 1.0:
            return None                                # 両側の床に 200 重ねられない（床の外へ出る）列は置かない
        L = next((float(v) for v in BOARD_LENGTHS if v >= b - a), b - a)
        if a + L > hi:
            L = hi - a                                 # 定尺では床の外へ出るので切って使う
        return (m[0] + u[0] * a + lf[0] * off, m[1] + u[1] * a + lf[1] * off), L

    # 列の並びを横に 20 ずつずらし、置ける列がいちばん多い並び（同じなら中心に近い並び）
    n_max = int(math.ceil(width / w)) + 2
    best = None
    s = -width
    while s <= width - w * 0 + 1e-6:
        got = []
        for k in range(n_max):
            r = row(s + k * w)
            if r is not None:
                got.append(r)
            elif got:
                break                                   # 列は続けて並べる（間をあけない）
        key = (len(got), -abs(s + len(got) * w / 2.0))
        if got and (best is None or key > best[0]):
            best = (key, got)
        s += 20.0
    boards = best[1] if best else []
    ties = []
    for p, q in ((pi, pj), (qi, qj)):
        if math.dist(p, q) >= 150.0:
            ties.append((tuple(p), tuple(q)))
    return {"boards": boards, "ang": math.degrees(math.atan2(u[1], u[0])), "ties": ties, "w": w}


def board_quantities(layout: dict, fill: dict, levels: int) -> list[tuple[str, int, str]]:
    """足場板で渡す隅のつなぎ1か所の材料の目安."""
    from collections import Counter

    out = []
    for L, n in sorted(Counter(int(next((v for v in BOARD_LENGTHS if v >= L), L)) for _o, L in layout["boards"]).items()):
        out.append((f"足場板 {L / 1000:.0f}m", n * levels, f"両側の本足場のアンチの上に {BOARD_LAP_MM:.0f} 以上重ねて載せる"))
    out.append(("番線（#8）", 4 * len(layout["boards"]) * levels, "足場板の両端を2か所ずつ下の単管・アンチに留める"))
    for p, q in layout["ties"]:
        L = next((v for v in (1000, 1500, 2000, 2500, 3000) if v >= math.dist(p, q) + 300.0), 3000)
        out.append((f"単管 {L / 1000:.1f}m（支柱を結ぶ）", levels, f"支柱から支柱へ {math.dist(p, q):.0f}。床の高さ"))
    if layout["ties"]:
        out.append(("自在クランプ（支柱を結ぶ単管）", 2 * len(layout["ties"]) * levels, "両端を支柱に"))
    poly = fill["poly"]
    edges = [math.dist(poly[k], poly[(k + 1) % len(poly)]) for k in fill["rail"]]
    for e in edges:
        L = next((v for v in (1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000) if v >= e + 600.0), 6000)
        out.append((f"単管 {L / 1000:.1f}m（手すり 上桟・中桟）", 2 * levels, f"外の辺 {e:.0f}"))
    out.append(("自在クランプ（手すり）", 4 * len(edges) * levels, "手すりの両端を支柱に"))
    out.append(("幅木（足場板）", len(edges) * levels, "外の辺"))
    return out
