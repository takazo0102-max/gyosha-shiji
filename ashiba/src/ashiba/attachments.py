"""足場ラインから分けた部材（壁つなぎ・水平ネット・ネットブラケット）の置き場所（純粋関数）.

利用者の指定（2026-10-20）: 壁つなぎ・水平ネット・ネットブラケットは足場ラインの GDL とは別の部品に
する。ツールバーが自動で置く。水平ネットは躯体と足場の隙間（内側建地〜躯体面）に、足場条件で指定した層に張る。

座標の決め（足場ラインと同じ）: 面の始点＝内側建地列の始点支柱、+X＝面に沿う方向、+Y＝躯体側。
部品は原点にこの点、faceAng に面の向き（度）を入れて置く（回転を要素ごとに送らないので、数百本でも1回で置ける）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import ScaffoldModel

TIE_OBJECT = "ashiba_tie"
NET_OBJECT = "ashiba_net"
NETBK_OBJECT = "ashiba_netbk"
SHEET_OBJECT = "ashiba_sheet"
CSTEP_OBJECT = "ashiba_cstep"

# 養生シート1枚の大きさ（幅, 高さ mm）。メッシュシート 1類は 1.8×5.1m、防音シートは 1.8×3.4m が標準
SHEET_SIZES = {"メッシュシート": (1800, 5100), "防音シート": (1800, 3400), "密閉シート": (1800, 3400)}
SHEET_GAP_MM = 60.0          # 外側建地列の芯からシートの面まで（緊結金具の出）

TIE_BELOW_DECK_MM = 300.0  # 壁つなぎの取付位置（作業床の高さから下へ。床の高さは腕木・ネットブラケットと同じコマ）
NET_GAP_MM = 50.0          # ネットブラケットの先端と躯体面のあき
NET_BELOW_DECK_MM = 50.0   # 作業床の天端からネットまで（床の下に張る）

# ネットブラケットはネット専用ブラケット NL500 の形（利用者の資料 2026-10-20）: φ42.7/48.6 兼用クランプで
# 内側建地を抱き、受け板（幅75）から φ34 の外管と φ27.2 の内管の伸縮腕を躯体側へ出す（方杖なし）。
# 腕の届きは受け板の建地側の面から 300〜470mm。ネットは受け板・外管の端・先端のフックに掛ける
NETBK_MODEL = "NL500"
NETBK_PLATE_MM = 42.0          # 建地芯から受け板の建地側の面（クランプの出。全伸 512 − 470）
NETBK_REACH_MIN_MM = 300.0
NETBK_REACH_MAX_MM = 470.0
NET_EDGE_MM = 120.0            # ネットの建地側の端（建地芯から。受け板のフック）
NET_TIP_MM = 20.0              # ネットの躯体側の端（腕の先端のフックから手前）


def netbk_arm_mm(standoff_mm: float) -> tuple[float, bool]:
    """ブラケットの先端（建地芯から mm）と、躯体に当たらずに収まるか.

    先端は躯体面から NET_GAP_MM 手前を狙い、NL500 の伸縮範囲に丸める。最短でも躯体に届く
    （離れ＜建地芯から 342＋あき）ときは最短で描き、収まらない（False）と返す。
    """
    want = float(standoff_mm) - NET_GAP_MM
    lo = NETBK_PLATE_MM + NETBK_REACH_MIN_MM
    hi = NETBK_PLATE_MM + NETBK_REACH_MAX_MM
    return min(max(want, lo), hi), want >= lo - 1e-6


def net_width_mm(standoff_mm: float) -> float:
    """水平ネットの幅（受け板のフック〜腕の先端のフック。腕が躯体に当たるときは躯体面のあきまで）."""
    arm, _fits = netbk_arm_mm(standoff_mm)
    tip = min(arm, float(standoff_mm) - NET_GAP_MM)
    return tip - NET_TIP_MM - NET_EDGE_MM


@dataclass
class Placement:
    part: str                     # 部品の基本名（版は配置時に付ける）
    x_mm: float
    y_mm: float
    params: dict = field(default_factory=dict)


def _frame(ep):
    sx, sy = ep.start_post
    ex, ey = ep.end_post
    n = math.hypot(ex - sx, ey - sy) or 1.0
    ux, uy = (ex - sx) / n, (ey - sy) / n
    return (sx, sy), (ux, uy), (-uy, ux), math.degrees(math.atan2(uy, ux))


def tie_name(model: ScaffoldModel, need_mm: float) -> str:
    """必要長さに合う壁つなぎの品番（数量と同じ選び方: 伸縮範囲が合う最短の品、無ければ最長）."""
    cands = sorted((p for p in model.master.by_category("壁つなぎ") if p.adjustable_range()),
                   key=lambda p: p.adjustable_range()[1])
    if not cands:
        p = next(iter(model.master.by_category("壁つなぎ")), None)
        return p.model_no if p is not None else ""
    fit = next((p for p in cands if p.covers(int(round(need_mm)))), None)
    return (fit or cands[-1]).model_no


def tie_placements(model: ScaffoldModel, line_mode: bool = False) -> list[Placement]:
    """壁つなぎ1本ごとの部品（長さは数量と同じ必要長さ＝躯体面まで）."""
    from .quantity import bridged_extra_standoff_mm, wall_tie_required_length_mm

    out: list[Placement] = []
    edges = {e.edge_index: e for e in model.plan.edges}
    for t in model.wall_ties:
        ep = edges.get(t.edge_index)
        if ep is None:
            continue
        o, u, nrm, ang = _frame(ep)
        need = wall_tie_required_length_mm(model, t.edge_index, t.position_mm)
        # 建地1列の足場は外側の列の建地から取る（nrm は躯体側）
        off = model.tie_post_offset_mm
        wall = float(ep.standoff) + off + bridged_extra_standoff_mm(model, t.edge_index, t.position_mm)
        z = max(float(t.height_mm) - TIE_BELOW_DECK_MM, model.elevation_of(t.edge_index).first_ledger_height)
        out.append(Placement(TIE_OBJECT, o[0] + u[0] * t.position_mm - nrm[0] * off,
                             o[1] + u[1] * t.position_mm - nrm[1] * off, {
            "faceAng": ang, "zH": (z + model.base_height_mm) / 1000.0, "tieL": need / 1000.0,
            "wallD": wall / 1000.0,
            "tieName": tie_name(model, need), "lineMode": bool(line_mode)}))
    return out


def net_heights_mm(model: ScaffoldModel, edge_index: int = None) -> list[float]:
    """水平ネットを張る高さ（指定した作業層の床の天端の少し下。面を渡すとその面の層だけ）."""
    ev = model.elevation if edge_index is None else model.elevation_of(edge_index)
    lv = list(ev.level_heights)
    return [float(lv[k - 1]) - NET_BELOW_DECK_MM for k in model.config.horizontal_net_levels if 1 <= k <= len(lv)]


def net_placements(model: ScaffoldModel, line_mode: bool = False) -> list[Placement]:
    """水平ネット（1面1層に1部品）とネットブラケット（内側建地ごと。各面は始点の建地を受け持つ）."""
    out: list[Placement] = []
    for ep in model.plan.edges:
        for z in net_heights_mm(model, ep.edge_index):
            z = z + model.base_height_mm
            o, u, nrm, ang = _frame(ep)
            width = net_width_mm(ep.standoff)
            if width <= 0:
                continue
            arm, _fits = netbk_arm_mm(ep.standoff)
            length = float(sum(ep.spans))
            out.append(Placement(NET_OBJECT, o[0] + nrm[0] * NET_EDGE_MM, o[1] + nrm[1] * NET_EDGE_MM, {
                "faceAng": ang, "zH": z / 1000.0, "netL": length / 1000.0, "netW": width / 1000.0,
                "lineMode": bool(line_mode)}))
            x = 0.0
            for sp in (ep.spans if model.config.net_brackets else []):     # 終点の建地は次の面が受け持つ
                out.append(Placement(NETBK_OBJECT, o[0] + u[0] * x, o[1] + u[1] * x, {
                    "faceAng": ang, "zH": z / 1000.0, "armL": arm / 1000.0,
                    "lineMode": bool(line_mode)}))
                x += float(sp)
    return out


def net_quantities(model: ScaffoldModel) -> tuple[float, int]:
    """水平ネットの面積（m²）とネットブラケットの個数（net_placements と同じ数え方）."""
    area = 0.0
    n_bk = 0
    for ep in model.plan.edges:
        for _z in net_heights_mm(model, ep.edge_index):
            width = net_width_mm(ep.standoff)
            if width <= 0:
                continue
            area += float(sum(ep.spans)) / 1000.0 * width / 1000.0
            n_bk += len(ep.spans) if model.config.net_brackets else 0
    return area, n_bk


def net_pieces(model: ScaffoldModel, length_mm: float = 6000.0, width_mm: float = 500.0) -> int:
    """層間ネットの枚数（1枚 幅×長さ。面ごと・層ごとに面の長さを長さで、隙間の幅を幅で割って切り上げ）."""
    import math

    n = 0
    for ep in model.plan.edges:
        width = net_width_mm(ep.standoff)
        if width <= 0:
            continue
        per = math.ceil(float(sum(ep.spans)) / length_mm) * max(1, math.ceil(width / width_mm - 1e-6))
        n += per * len(net_heights_mm(model, ep.edge_index))
    return n


def netbk_clash_faces(model: ScaffoldModel) -> list[tuple[int, float]]:
    """ネットを張る面のうち、NL500 が最短でも躯体に当たる面（辺番号, 離れ mm）."""
    if not model.config.horizontal_net_levels or not model.config.net_brackets:
        return []
    return [(ep.edge_index, float(ep.standoff)) for ep in model.plan.edges
            if net_heights_mm(model, ep.edge_index) and not netbk_arm_mm(ep.standoff)[1]]


def _sheet_extent(model: ScaffoldModel, ep) -> tuple[float, float]:
    """シートの面に沿った範囲（mm。内側建地列の始点から）。出隅は外側の角の支柱の外まで回し、
    入隅は隣の面のシートの面で止める（外側建地列＋シートのあきだけ戻る）.

    隅の隙間（コーナーステップ）も覆う（利用者の指摘 2026-10-24: 間が開いてる部分は特殊シートとして伸ばす）。
    角の升目の辺は隣の面の建地列間隔（幅の違う本足場の組と出会う隅）。入隅でつないだ隅で終わる面は隣の面の
    外側建地列で止まっているので、そこから隣のシートの面までにする（inner_corners）。
    """
    n = len(model.plan.outline.edges)
    ei = ep.edge_index
    length = float(sum(ep.spans))
    gs = ge = 0.0
    for c in getattr(model.plan, "corner_steps", None) or []:
        if c.edge_index == ei:
            if getattr(c, "at_start", False):
                gs = float(c.gap_mm)
            else:
                ge = float(c.gap_mm)
    d_s = model.row_spacing_of((ei - 1) % n) + SHEET_GAP_MM
    d_e = model.row_spacing_of((ei + 1) % n) + SHEET_GAP_MM
    sc, ec = model.corner_kind_start(ei), model.corner_kind_end(ei)
    x0 = -gs - d_s if sc == "出隅" else (d_s if sc == "入隅" else -gs)
    joined_end = next((g for a, _b, g in getattr(model, "inner_corner_joins", None) or [] if a == ei), None)
    if ec == "出隅":
        x1 = length + ge + d_e
    elif ec == "入隅" and joined_end is not None:
        x1 = length + float(joined_end) - SHEET_GAP_MM
    elif ec == "入隅":
        x1 = length - d_e
    else:
        x1 = length + ge
    return x0, x1


def sheet_panels(model: ScaffoldModel, ep, stair_plan=None, sheet_w: float = 1829.0) -> list[list[tuple[float, float, bool]]]:
    """シートの割付（区間ごとに [(始点, 終点, 特殊か)] mm）。継ぎ目は足場の支柱の位置（スパン）にそろえる.

    足場のスパンと同じ幅（インチ 610〜1829・メートル 600〜1800。どの幅のシートも普通にある）は標準のシート、
    スパンに無い幅（端の角の升目・隅の隙間・入隅の取り合い）だけ特殊シートとして伸ばす（利用者の指定 2026-10-24:
    外部シートの割り付けは足場と同じに、間が開いてる部分は特殊シート。インチも普通にあるから特殊シートじゃない）."""
    coins = [float(c) for c in model.master.span_lengths()] or [float(sheet_w)]
    posts = [0.0]
    for sp in ep.spans:
        posts.append(posts[-1] + float(sp))
    out = []
    for x0, x1, _off in sheet_segments(model, ep, stair_plan):
        cuts = [x0] + [p for p in posts if x0 + 1.0 < p < x1 - 1.0] + [x1]
        panels = []
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 1.0:
                continue
            panels.append((a, b, not any(abs((b - a) - c) <= 1.0 for c in coins)))
        out.append(panels)
    return out


def sheet_clamp_heights(model: ScaffoldModel, edge_index: int) -> list[float]:
    """シートクランプを付ける高さ mm（GLから）: 根がらみと各層の手すり（シートを外側建地の布材に留める）."""
    ev = model.elevation_of(edge_index)
    out = [float(ev.first_ledger_height)] if getattr(ev, "has_negarami", True) else []
    out += [float(h) + float(model.guard_rail_height_mm) for h in ev.level_heights[1:]]
    return sorted({round(v) for v in out if 0 < v <= ev.total_height})


def sheet_clamp_positions(model: ScaffoldModel, ep, stair_plan=None) -> list[float]:
    """シートクランプを付ける面に沿った位置 mm（シートの継ぎ目＝支柱と、区間の両端の角の支柱）."""
    xs: list[float] = []
    for panels in sheet_panels(model, ep, stair_plan):
        if not panels:
            continue
        xs.append(panels[0][0] + SHEET_GAP_MM)                 # 端は角の支柱（シートはあきだけ外へ出ている）
        xs += [a for a, _b, _s in panels[1:]]
        xs.append(panels[-1][1] - SHEET_GAP_MM)
    return xs


def sheet_segments(model: ScaffoldModel, ep, stair_plan=None) -> list[tuple[float, float, float]]:
    """面のシートの区間 [(始点, 終点, 内側建地芯からシートの面まで) mm].

    外付けの階段室の区間は、本体の外側でシートを切り（乗り移りの通路）、階段室の外側に張る。
    """
    x0, x1 = _sheet_extent(model, ep)
    off = float(model.post_row_spacing_mm) + SHEET_GAP_MM
    cuts = []
    if stair_plan is not None and getattr(stair_plan, "outside", False):
        cuts = sorted((t.start_mm, t.end_mm) for t in stair_plan.towers if t.edge_index == ep.edge_index)
    out = []
    cur = x0
    for s0, e0 in cuts:
        if s0 > cur:
            out.append((cur, s0, off))
        out.append((s0, e0, off + float(model.post_row_spacing_mm)))
        cur = max(cur, e0)
    if x1 > cur:
        out.append((cur, x1, off))
    return out


def sheet_end_pieces(model: ScaffoldModel, ep, stair_plan=None) -> list[tuple[float, float]]:
    """外付けの階段室の妻側（区間の両端）のシート [(面に沿った位置, 位置からシートまでのずれ) mm].

    妻側は外側建地列から3列目まで（建地列の間隔1つぶん）。始点側は区間の外（−あき）、終点側も外（＋あき）。
    """
    if stair_plan is None or not getattr(stair_plan, "outside", False):
        return []
    out = []
    for t in stair_plan.towers:
        if t.edge_index == ep.edge_index:
            out += [(t.start_mm, SHEET_GAP_MM), (t.end_mm, -SHEET_GAP_MM)]
    return out


def sheet_placements(model: ScaffoldModel, line_mode: bool = False, stair_plan=None) -> list[Placement]:
    """養生シート（面の区間ごとに1部品）。足場の外側の構面を、地面から支柱の天端まで覆う."""
    size = SHEET_SIZES.get(model.config.sheet_type or "")
    if size is None:
        return []
    # 系列にある品（日建スプリングメッシュ 1829×5160）なら継ぎ目はその幅で
    part = next((p for p in model.master.by_category("養生シート") if (model.config.sheet_type or "") in p.note), None)
    if part is not None and part.nominal_dim:
        size = (part.nominal_dim, part.actual_dim or size[1])
    out: list[Placement] = []
    for ep in model.plan.edges:
        o, _u, _n, ang = _frame(ep)
        top = float(model.elevation_of(ep.edge_index).total_height)
        for (x0, x1, off), panels in zip(sheet_segments(model, ep, stair_plan),
                                         sheet_panels(model, ep, stair_plan, float(size[0]))):
            out.append(Placement(SHEET_OBJECT, o[0], o[1], {
                "faceAng": ang, "zH": model.base_height_mm / 1000.0, "offY": off / 1000.0,
                "x0": x0 / 1000.0, "x1": x1 / 1000.0, "zB": 0.0, "zT": top / 1000.0,
                "sheetW": size[0] / 1000.0, "sheetKind": model.config.sheet_type, "lineMode": bool(line_mode),
                # 継ぎ目は足場の支柱の位置。「始点,終点,特殊(0/1)」の繰り返し mm（特殊シートは色を替える）
                "panelList": ",".join(f"{a:.0f},{b:.0f},{int(sp)}" for a, b, sp in panels),
                # シートクランプ（継ぎ目と端の支柱に、根がらみと各層の手すりの高さで。利用者の指定 2026-10-24）
                "clampList": ",".join(f"{h:.0f}" for h in sheet_clamp_heights(model, ep.edge_index))}))
        # 外付け階段室の妻側: 部品の x を面の外向きにして（面の向き−90°）、外側建地列から3列目まで
        row = float(model.post_row_spacing_mm)
        for pos, shift in sheet_end_pieces(model, ep, stair_plan):
            out.append(Placement(SHEET_OBJECT, o[0] + _u[0] * pos, o[1] + _u[1] * pos, {
                "faceAng": ang - 90.0, "zH": model.base_height_mm / 1000.0, "offY": shift / 1000.0,
                "x0": (row + SHEET_GAP_MM) / 1000.0, "x1": (2 * row + SHEET_GAP_MM) / 1000.0,
                "zB": 0.0, "zT": top / 1000.0, "sheetW": size[0] / 1000.0,
                "sheetKind": model.config.sheet_type, "lineMode": bool(line_mode)}))
    return out


def sheet_quantities(model: ScaffoldModel, stair_plan=None, size=None) -> tuple[float, int]:
    """養生シートの面積（m²）と、足場のスパンと同じ幅のシートの枚数（升目 × 高さ÷1枚の高さ）。size で1枚の大きさを
    替えられる。幅ごとの内訳は standard_sheets、特殊シート（角・隙間）は special_sheets."""
    if (size or SHEET_SIZES.get(model.config.sheet_type or "")) is None:
        return 0.0, 0
    area = 0.0
    for ep in model.plan.edges:
        top = float(model.elevation_of(ep.edge_index).total_height)
        for panels in sheet_panels(model, ep, stair_plan):
            area += sum(b - a for a, b, _sp in panels) / 1000.0 * top / 1000.0
        area += len(sheet_end_pieces(model, ep, stair_plan)) * float(model.post_row_spacing_mm) / 1000.0 * top / 1000.0
    return area, sum(standard_sheets(model, stair_plan, size).values())


def _sheets_by_width(model: ScaffoldModel, stair_plan, size, special: bool) -> dict[int, int]:
    import math as _m

    size = size or SHEET_SIZES.get(model.config.sheet_type or "")
    if size is None:
        return {}
    out: dict[int, int] = {}
    for ep in model.plan.edges:
        top = float(model.elevation_of(ep.edge_index).total_height)
        rows = _m.ceil(top / size[1] - 1e-6)
        ws = [b - a for panels in sheet_panels(model, ep, stair_plan) for a, b, sp in panels if sp == special]
        # 外付け階段の妻側は建地列の間隔の幅（スパンにある幅なら標準）
        row = float(model.post_row_spacing_mm)
        row_std = any(abs(row - c) <= 1.0 for c in model.master.span_lengths())
        if special != row_std:
            ws += [row] * len(sheet_end_pieces(model, ep, stair_plan))
        for w in ws:
            k = int(round(w))
            out[k] = out.get(k, 0) + rows
    return dict(sorted(out.items()))


def standard_sheets(model: ScaffoldModel, stair_plan=None, size=None) -> dict[int, int]:
    """足場のスパンと同じ幅のシートの {幅 mm: 枚数}（インチ・メートルとも普通にある幅）."""
    return _sheets_by_width(model, stair_plan, size, False)


def special_sheets(model: ScaffoldModel, stair_plan=None, size=None) -> dict[int, int]:
    """特殊シート（スパンに無い幅）の {幅 mm: 枚数}。角の升目・隅の隙間・入隅の取り合い、外付け階段の妻側."""
    return _sheets_by_width(model, stair_plan, size, True)


def sheet_clamp_count(model: ScaffoldModel, stair_plan=None) -> int:
    """シートクランプの数（sheet_placements の clampList と同じ: 継ぎ目と端の支柱 × 根がらみと各層の手すり）."""
    if SHEET_SIZES.get(model.config.sheet_type or "") is None:
        return 0
    return sum(len(sheet_clamp_positions(model, ep, stair_plan)) * len(sheet_clamp_heights(model, ep.edge_index))
               for ep in model.plan.edges)


def corner_step_name(model: ScaffoldModel) -> str:
    """コーナーステップの品番（床の幅の組合せ。例: 踏板 500+240 → NDCS05＋NDCS02）."""
    steps = list(model.master.by_category("コーナー踏板"))
    names = []
    for w in model.deck_widths_in_use or []:
        hit = next((s for s in steps if int(s.nominal_dim) == int(w)), None)
        names.append(hit.model_no if hit is not None else f"幅{int(w)}")
    return "＋".join(names) or "コーナーステップ"


def cstep_placements(model: ScaffoldModel, line_mode: bool = False) -> list[Placement]:
    """くさびの隅の隙間（plan.corner_steps のうち面の終点のもの）ごとのコーナーステップ.

    原点はその面の最後の支柱（内側建地列）。各層の床の高さに踏板を描く（利用者の指定 2026-10-23）。
    """
    out: list[Placement] = []
    edges = {e.edge_index: e for e in model.plan.edges}
    widths = [float(w) for w in (model.deck_widths_in_use or [])][:2]
    for cs in getattr(model.plan, "corner_steps", []) or []:
        ep = edges.get(cs.edge_index)
        if ep is None or cs.edge_index < 0:
            continue
        o, u, _nrm, ang = _frame(ep)
        # 隙間は面の終点の先（始点の側の隙間は始点の手前）
        x = -float(cs.gap_mm) if getattr(cs, "at_start", False) else float(sum(ep.spans))
        lv = [float(h) + model.base_height_mm for h in model.elevation_of(ep.edge_index).level_heights]
        out.append(Placement(CSTEP_OBJECT, o[0] + u[0] * x, o[1] + u[1] * x, {
            "faceAng": ang, "gapL": float(cs.gap_mm) / 1000.0,
            "rowW": float(model.post_row_spacing_mm) / 1000.0,
            "lvList": ",".join(f"{v:.0f}" for v in lv), "stepName": corner_step_name(model),
            # 踏板の幅は床の幅ごと（CS05＝500・CS02＝240）。始点の側の隙間は爪を +X の端（始点の支柱）に掛ける
            "plW1": widths[0] / 1000.0 if widths else 0.5, "plW2": widths[1] / 1000.0 if len(widths) > 1 else 0.0,
            "flipX": bool(getattr(cs, "at_start", False)),
            # 踏板は床の上面に（足場ラインの床と同じ: 布材 φ42.7 の半径＋踏板の厚み 45）
            "deckTop": 0.0427 / 2 + 0.045,
            "lineMode": bool(line_mode)}))
    return out

