"""足場ラインから分けた部材（壁つなぎ・水平ネット・ネットブラケット）の置き場所（純粋関数）.

利用者の指定（2026-10-20）: 壁つなぎ・水平ネット・ネットブラケットは足場ラインの GDL とは別の部品に
する。ツールバーが自動で置く。水平ネットは躯体と足場の隙間（内側建地〜躯体面）に、足場条件で指定した層に張る。

座標の決め（足場ラインと同じ）: 面の始点＝内側建地列の始点支柱、+X＝面に沿う方向、+Y＝躯体側。
部品は原点にこの点、faceAng に面の向き（度）を入れて置く（回転を要素ごとに送らないので、数百本でも1回で置ける）。
"""

from __future__ import annotations

from typing import Optional

import math
from dataclasses import dataclass, field

from .model import ScaffoldModel

TIE_OBJECT = "ashiba_tie"
NET_OBJECT = "ashiba_net"
NETBK_OBJECT = "ashiba_netbk"
SHEET_OBJECT = "ashiba_sheet"
CSTEP_OBJECT = "ashiba_cstep"
BRIDGE_OBJECT = "ashiba_bridge"

# 養生シート1枚の大きさ（幅, 高さ mm）。メッシュシート 1類は 1.8×5.1m、防音シートは 1.8×3.4m が標準
SHEET_SIZES = {"メッシュシート": (1800, 5100), "防音シート": (1800, 3400), "密閉シート": (1800, 3400),
               "防音パネル": (1829, 862)}
# 防音パネル（日本セイフティー 防音パネル・BG。利用者の指定 2026-10-24: 防音パネルを追加して）: 厚み 40、高さはインチ規格
# 862・メーター規格 850。長さはスパン−10（1829→1819）。継ぎ目の建地の専用クランプのピンで隣り合うパネルの枠を留め、
# 出隅の角はコーナーパネルを三つ爪クランプで留める（三つ爪の数＝コーナーパネルの数＋コーナーの箇所数。同社のよくある質問）
PANEL_KIND = "防音パネル"
PANEL_T_MM = 40.0
PANEL_H_MM = {"inch": 862.0, "metric": 850.0}
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


def _with_pens(model: ScaffoldModel, pls: list[Placement]) -> list[Placement]:
    """部品の図面のペン（区分ごと。ashiba.pens）を足す."""
    from .pens import gdl_pens

    for p in pls:
        p.params.update(gdl_pens(model.config.pens, p.part))
    return pls


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
            # 鉄骨から取る: 仕上げの奥の梁まで延ばし、先はビームクランプ（利用者の指定 2026-10-24）
            "steelD": (float(model.config.steel_depth_mm) / 1000.0
                       if getattr(model.config, "tie_source", "") == "鉄骨" else 0.0),
            "tieName": tie_name(model, need), "lineMode": bool(line_mode)}))
    return _with_pens(model, out)


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
            # セットバックの上段が本体に繋がる升目（上段の床の下）は張らない（利用者の指摘 2026-10-25: ネットクランプが
            # 足場の下まで入っている）。ネットはその升目の手前の建地で止め、升目の中の建地のブラケットも付けない
            n0, n1 = 0.0, length
            for pe, x0, x1, zp in getattr(model, "tier_passages", None) or []:
                if pe != ep.edge_index or z - model.base_height_mm < zp - NET_BELOW_DECK_MM - 1.0:
                    continue
                if x0 <= 1.0:
                    n0 = max(n0, x1)
                else:
                    n1 = min(n1, x0)
            if n1 - n0 < 100.0:
                continue
            out.append(Placement(NET_OBJECT, o[0] + nrm[0] * NET_EDGE_MM + u[0] * n0,
                                 o[1] + nrm[1] * NET_EDGE_MM + u[1] * n0, {
                "faceAng": ang, "zH": z / 1000.0, "netL": (n1 - n0) / 1000.0, "netW": width / 1000.0,
                "lineMode": bool(line_mode)}))
            x = 0.0
            for sp in (ep.spans if model.config.net_brackets else []):     # 終点の建地は次の面が受け持つ
                if x < n0 - 1.0 or x > n1 + 1.0:
                    x += float(sp)
                    continue
                bx, by = o[0] + u[0] * x, o[1] + u[1] * x
                b_ang, b_arm = ang, arm
                if x == 0.0:
                    b_ang, b_arm = netbk_corner_aim(model, ep, (bx, by), ang, arm)
                out.append(Placement(NETBK_OBJECT, bx, by, {
                    "faceAng": b_ang, "zH": z / 1000.0, "armL": b_arm / 1000.0,
                    "lineMode": bool(line_mode)}))
                x += float(sp)
    return _with_pens(model, out)


def netbk_corner_aim(model: ScaffoldModel, ep, post, ang: float, arm: float) -> tuple[float, float]:
    """面の始点の建地のネットブラケットの向き（度）と腕の先端（建地芯から mm）.

    躯体の出隅の角に立つ建地は、ブラケットを躯体の角へ斜めに向ける（2面のネットの角を1本で受ける）。利用者の指定
    2026-10-24: コーナーのネットブラケットは斜めにして。それ以外（入隅・開放端・角から外れた建地）は面に直角のまま.
    """
    if model.corner_kind_start(ep.edge_index) != "出隅":
        return ang, arm
    cx, cy = model.plan.outline.edges[ep.edge_index].start
    vx, vy = cx - post[0], cy - post[1]
    _o, u, nrm, _a = _frame(ep)
    if vx * u[0] + vy * u[1] < 1.0 or vx * nrm[0] + vy * nrm[1] < 1.0:
        return ang, arm
    diag, _fits = netbk_arm_mm(math.hypot(vx, vy))
    # 部品の +Y が腕の向き（faceAng で回す）
    return math.degrees(math.atan2(vy, vx)) - 90.0, diag


def net_quantities(model: ScaffoldModel) -> tuple[float, int]:
    """水平ネットの面積（m²）とネットブラケットの個数（net_placements と同じ数え方）."""
    area = 0.0
    n_bk = 0
    for p in net_placements(model):
        if p.part == NET_OBJECT:
            area += float(p.params["netL"]) * float(p.params["netW"])
        elif p.part == NETBK_OBJECT:
            n_bk += 1
    return area, n_bk


def net_pieces(model: ScaffoldModel, length_mm: float = 6000.0, width_mm: float = 500.0) -> int:
    """層間ネットの枚数（1枚 幅×長さ。面ごと・層ごとに張る長さを長さで、隙間の幅を幅で割って切り上げ）."""
    import math

    n = 0
    for p in net_placements(model):
        if p.part == NET_OBJECT:
            n += (math.ceil(float(p.params["netL"]) * 1000.0 / length_mm - 1e-6)
                  * max(1, math.ceil(float(p.params["netW"]) * 1000.0 / width_mm - 1e-6)))
    return n


def netbk_clash_faces(model: ScaffoldModel) -> list[tuple[int, float]]:
    """ネットを張る面のうち、NL500 が最短でも躯体に当たる面（辺番号, 離れ mm）."""
    if not model.config.horizontal_net_levels or not model.config.net_brackets:
        return []
    return [(ep.edge_index, float(ep.standoff)) for ep in model.plan.edges
            if net_heights_mm(model, ep.edge_index) and not netbk_arm_mm(ep.standoff)[1]]


def is_panel(model: ScaffoldModel) -> bool:
    """外側の養生が防音パネルか（シートと同じ割付・段・クランプの決めで、板を建地にクランプで留める）."""
    return (model.config.sheet_type or "") == PANEL_KIND


def panel_height_mm(model: ScaffoldModel) -> float:
    """防音パネル1枚の高さ（インチ規格 862・メーター規格 850）."""
    from .master import series_module

    try:
        return PANEL_H_MM[series_module(model.master.series_id)]
    except KeyError:
        return PANEL_H_MM["inch"]


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
    # 防音パネルは出隅の角の建地で止める（角はコーナーパネルで塞ぐ）。シートは角の建地の外まで回す
    wrap = 0.0 if is_panel(model) else SHEET_GAP_MM
    sc, ec = model.corner_kind_start(ei), model.corner_kind_end(ei)
    x0 = -gs - (d_s - SHEET_GAP_MM + wrap) if sc == "出隅" else (d_s if sc == "入隅" else -gs)
    joined_end = next((g for a, _b, g in getattr(model, "inner_corner_joins", None) or [] if a == ei), None)
    if ec == "出隅":
        x1 = length + ge + d_e - SHEET_GAP_MM + wrap
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
    if is_panel(model):
        # 防音パネルは隅の隙間の両側の建地でも切る（隙間は特殊な幅、角の升目はスパンにある幅のパネル）
        for c in getattr(model.plan, "corner_steps", None) or []:
            if c.edge_index == ep.edge_index:
                posts.append(-float(c.gap_mm) if getattr(c, "at_start", False) else posts[len(ep.spans)] + float(c.gap_mm))
        posts.sort()
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


def sheet_size(model: ScaffoldModel) -> Optional[tuple[float, float]]:
    """シート1枚の (幅, 高さ) mm。系列のマスタにその種類の品があればその大きさ（幅はいちばん広い品）、無ければ既定."""
    kind = model.config.sheet_type or ""
    if kind == PANEL_KIND:
        coins = model.master.span_lengths() or [1829]
        return float(max(coins)), panel_height_mm(model)
    parts = [p for p in model.master.by_category("養生シート") if kind and kind in p.note and p.nominal_dim]
    if parts:
        top = max(parts, key=lambda p: p.nominal_dim)
        return float(top.nominal_dim), float(top.actual_dim or SHEET_SIZES.get(kind, (0, 5100))[1])
    size = SHEET_SIZES.get(kind)
    return (float(size[0]), float(size[1])) if size else None


GROMMET_EDGE_MM = 20.0       # シートの縁からハトメの芯まで（上下の辺）
GROMMET_SIDE_MM = 16.0       # シートの左右の辺からハトメの芯まで（クランプのフック φ9 ×2 の間隔 32 の半分。継ぎ目の支柱の
                             # クランプの2本のフックが左右のシートのハトメに掛かる）


def _sheet_pitch(model: ScaffoldModel) -> float:
    """シートの左右の辺のハトメの間隔＝段の送りの単位 mm（くさびはコマのピッチ。単管・枠組は 450）."""
    m = model.master
    p = float(m.koma_pitch or 0)
    return p if not m.is_tube and not m.is_frame and p >= 300 else 450.0


def sheet_top_mm(model: ScaffoldModel, edge_index: int) -> float:
    """シートの天端 mm（足場の立つ面から）.

    くさびは、いちばん上のハトメ（天端の 20 下）が最上のコマとその下のコマのちょうど中ほどに来る高さ。クランプは
    ハトメの高さに付くので、どのクランプもコマから半ピッチ離れて先行手すり・布材を掛けるコマをふさがない
    （利用者の指摘 2026-10-25: これだと先行手すりかけれないよ・フックとメッシュの穴の位置合わせて）。
    防音パネル・単管・枠組は支柱の天端。
    """
    return sheet_top_of(model, model.elevation_of(edge_index))


def sheet_top_of(model: ScaffoldModel, ev) -> float:
    """立面 ev の足場に張るシートの天端 mm（sheet_top_mm の決め）."""
    top = float(ev.total_height)
    m = model.master
    if is_panel(model) or m.is_tube or m.is_frame or float(m.koma_pitch or 0) < 300 or not ev.posts:
        return top
    pitch = float(m.koma_pitch)
    offs = m.post_koma_offsets(int(ev.posts[-1]))
    z_top_koma = (float(ev.jack_extension) + float(sum(ev.posts[:-1])) + max(offs)) if offs \
        else top - float(m.koma_top_gap)
    return z_top_koma - pitch / 2.0 + GROMMET_EDGE_MM


def sheet_bottom_mm(model: ScaffoldModel, edge_index: int) -> float:
    """外部シートの下端 mm（足場の立つ面から）＝仮囲いの天端（利用者の指定 2026-10-24: 仮囲いまでにする）.

    セットバックの上段は、下段の足場（低い所のメッシュ）の天端から上だけ（sheet_bottom_override_mm。利用者の指定
    2026-10-25: セットバック部分もメッシュシートは低いところのメッシュの高さまででいいよ）."""
    top = sheet_top_mm(model, edge_index)
    over = getattr(model, "sheet_bottom_override_mm", None)
    if over is not None:
        return min(max(0.0, float(over)), max(0.0, top - 500.0))
    return min(max(0.0, float(getattr(model, "hoarding_height_mm", 0.0) or 0.0)), max(0.0, top - 500.0))


def sheet_rows(model: ScaffoldModel, edge_index: int, bottom: Optional[float] = None) -> list[tuple[float, float]]:
    """シートの段 [(下, 上) mm] を上から割り付ける（下から順に返す）。bottom を渡すとその高さまで（妻側のシート）.

    段の継ぎ目は作業床の高さにそろえる: 床（コマ）の半ピッチ上（床＋225）で、上の段の下のハトメと下の段の上のハトメが
    同じ高さに来て1つのクランプで掛ける（上下 20 ずつ重なる）。1枚の高さに収まる範囲でいちばん下の床で継ぐ（5.1m の
    シートは2層ごと）。余る長さは継ぎ目で内側へ折り返す扱い。いちばん下の段は仮囲いの天端まで（利用者の指定
    2026-10-24: 上から割り付けて・2026-10-25: メッシュに変な割り付けになっているよ→段の継ぎ目の高さ）。
    """
    size = sheet_size(model)
    top = sheet_top_mm(model, edge_index)
    if bottom is None:
        bottom = sheet_bottom_mm(model, edge_index)
    if size is None or top <= bottom:
        return []
    if is_panel(model):
        # 防音パネルは切れない。上から1枚ずつ下ろし、いちばん下の段は仮囲いの天端に重ねて隙間を残さない
        n_rows = int(math.ceil((top - bottom) / size[1] - 1e-6))
        return [(top - (i + 1) * size[1], top - i * size[1]) for i in reversed(range(n_rows))]
    h = float(size[1])
    p = _sheet_pitch(model)
    e = GROMMET_EDGE_MM
    joints = sorted({float(f) + p / 2.0 for f in model.elevation_of(edge_index).level_heights})
    out = []
    hi = top
    while True:
        if hi - bottom <= h + 0.5:
            out.append((bottom, hi))
            break
        # 継ぎ目 J: 上の段の下端（J−20）が1枚の高さに収まる、いちばん下の床。床が無ければハトメの並びで1枚いっぱい
        cand = [j for j in joints if j - e >= hi - h - 0.5 and j + e < hi - p]
        j = min(cand) if cand else hi - e - p * math.floor((h - 2 * e) / p)
        if j - e <= bottom + 1.0:
            out.append((bottom, hi))
            break
        out.append((j - e, hi))
        hi = j + e
    return list(reversed(out))


def sheet_step_mm(model: ScaffoldModel) -> float:
    """シートの段の送りの目安 mm（1枚の高さに収まる作業床の層の数 × 階高）."""
    size = sheet_size(model)
    if size is None:
        return 0.0
    if is_panel(model):
        return float(size[1])
    fh = float(model.master.floor_height or 1800)
    return fh * max(1, math.floor((float(size[1]) - 2 * GROMMET_EDGE_MM) / fh))


def sheet_grommet_heights(model: ScaffoldModel, lo: float, hi: float) -> list[float]:
    """シートの段 (lo, hi) の左右の辺のハトメの高さ mm（上の縁の 20 下から間隔ごとに下へ。下から順）. GDL と同じ."""
    p = _sheet_pitch(model)
    out = []
    z = hi - GROMMET_EDGE_MM
    while z >= lo + GROMMET_EDGE_MM - 0.5:
        out.append(z)
        z -= p
    return list(reversed(out))


def _clamp_heights_of_rows(model: ScaffoldModel, rows) -> list[float]:
    if not rows:
        return []
    if is_panel(model):
        # 防音パネルは段の継ぎ目ごと（下端・継ぎ目・天端）に専用クランプのピンで上下のパネルの枠を留める
        return sorted({round(v) for v in [lo for lo, _hi in rows] + [rows[-1][1]]})
    # 各段のシートの上と下のハトメ（利用者の指定 2026-10-25: メッシュクランプは上と下につけて）。上下の段の重ねでは
    # 上の段の下のハトメと下の段の上のハトメが同じ高さで、1つのクランプで掛ける
    out: list[float] = []
    for lo, hi in rows:
        g = sheet_grommet_heights(model, lo, hi)
        if g:
            out += [g[0], g[-1]]
    hs: list[float] = []
    for v in sorted(round(v) for v in out):
        if not hs or v - hs[-1] > 5:
            hs.append(v)
    return hs


def sheet_clamp_heights(model: ScaffoldModel, edge_index: int) -> list[float]:
    """シートクランプを付ける高さ mm（足場の立つ面から）: 各段のシートの上と下のハトメ.

    日本セイフティー 次世代シートクランプのカタログの取付図（支柱の上部・下部でシートを掛ける）。段の継ぎ目は上下の
    シートのハトメを1つのクランプで掛ける（利用者の資料 2026-10-24）。段は上から割り付ける。
    """
    return _clamp_heights_of_rows(model, sheet_rows(model, edge_index))


def sheet_rows_from(model: ScaffoldModel, edge_index: int, z0: float) -> list[tuple[float, float]]:
    """下端 z0 から上だけ張るシートの段（天端から z0 まで割り付け直す。継ぎ目は面のシートと同じ床の高さ）."""
    if is_panel(model):
        return [(max(lo, z0), hi) for lo, hi in sheet_rows(model, edge_index) if hi > z0 + 1.0]
    return sheet_rows(model, edge_index, bottom=z0)


def sheet_clamp_heights_from(model: ScaffoldModel, edge_index: int, z0: float) -> list[float]:
    """下端 z0 から上だけ張るシート（開放端の妻側）のクランプの高さ: 各段のシートの上と下のハトメ
    （利用者の指定 2026-10-25: メッシュクランプは上と下につけて）."""
    return _clamp_heights_of_rows(model, sheet_rows_from(model, edge_index, z0))


def sheet_clamp_ends(model: ScaffoldModel, ep) -> tuple[bool, bool]:
    """(始点の角にコーナー用のクランプを付けるか, 終点の角のクランプを付けないか).

    出隅の角の支柱は、2面のシートを1つの「養生クランプ コーナー用」で留める（利用者の指定 2026-10-24: コーナーは
    コーナー用にして）。各面は始点の出隅を受け持ち（支柱と同じ決め）、終点の出隅は次の面に任せる。"""
    return (model.corner_kind_start(ep.edge_index) == "出隅", model.corner_kind_end(ep.edge_index) == "出隅")


def _clamp_post(ep, x: float) -> float:
    """シートの端 x にいちばん近い支柱の位置 mm（面の始点の支柱から）."""
    posts = [0.0]
    for sp in ep.spans:
        posts.append(posts[-1] + float(sp))
    return min(posts, key=lambda p: abs(p - x))


def sheet_clamp_positions(model: ScaffoldModel, ep, stair_plan=None) -> list[float]:
    """普通のシートクランプを付ける面に沿った位置 mm（シートの継ぎ目＝支柱と、区間の端の支柱。出隅の角はコーナー用）."""
    corner_s, skip_e = sheet_clamp_ends(model, ep)
    segs = [p for p in sheet_panels(model, ep, stair_plan) if p]
    # 端のクランプは、シートの端にいちばん近い支柱に付ける。出隅はシートが角の支柱の外へあきだけ回り、範囲の端・
    # セットバックの継ぎ目・入隅はシートの端が支柱から外れている（シートの端の 60 先に付けると宙に浮く。
    # 実機 2026-10-25: シートクランプが浮いてる箇所がある）
    xs: list[float] = []
    for k, panels in enumerate(segs):
        if not (k == 0 and corner_s):
            xs.append(_clamp_post(ep, panels[0][0]))
        xs += [a for a, _b, _s in panels[1:]]
        if not (k == len(segs) - 1 and skip_e):
            xs.append(_clamp_post(ep, panels[-1][1]))
    out: list[float] = []
    for x in xs:
        if not out or abs(x - out[-1]) > 1.0:
            out.append(x)
    return out


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


def open_end_sheets(model: ScaffoldModel, ep) -> list[tuple[str, float]]:
    """開放端の妻側のシート [(端 "s"/"e", 下端 mm（足場の立つ面から）)]: 内側建地列から外側のシートの面まで.

    利用者の指摘 2026-10-25: 妻側にもシートいるよ（一部の面だけの足場の端・セットバックの先で本体を途中の屋根より上で
    止めた端）。途中の屋根より上だけ開く端は、その高さから上だけ張る。
    """
    if sheet_size(model) is None or model.master.is_frame and is_panel(model):
        return []
    out = []
    # 妻側のシートは下段のシートの天端から（無ければ妻側を塞ぐ高さから）
    above = {**(getattr(model, "open_above_mm", {}) or {}), **(getattr(model, "open_sheet_above_mm", {}) or {})}
    bottom = sheet_bottom_mm(model, ep.edge_index)
    top = sheet_top_mm(model, ep.edge_index)
    for end, is_open in (("s", model.open_start(ep.edge_index)), ("e", model.open_end(ep.edge_index))):
        if not is_open:
            continue
        z0 = max(bottom, float(above.get((ep.edge_index, end), 0.0)))
        if top - z0 > 100.0:
            out.append((end, z0))
    return out


def _n_rows_from(model: ScaffoldModel, edge_index: int, z0: float) -> int:
    return len(sheet_rows_from(model, edge_index, z0))


def sheet_placements(model: ScaffoldModel, line_mode: bool = False, stair_plan=None) -> list[Placement]:
    """養生シート（面の区間ごとに1部品）。足場の外側の構面を、地面から支柱の天端まで覆う."""
    size = sheet_size(model)
    if size is None:
        return []
    out: list[Placement] = []
    pitch = _sheet_pitch(model) / 1000.0

    def row_list(rows) -> str:
        return ",".join(f"{v:.0f}" for lo, hi in rows for v in (lo, hi))

    for ep in model.plan.edges:
        o, _u, _n, ang = _frame(ep)
        top = sheet_top_mm(model, ep.edge_index)
        rows = sheet_rows(model, ep.edge_index)
        ends = dict(open_end_sheets(model, ep))
        segs = list(zip(sheet_segments(model, ep, stair_plan), sheet_panels(model, ep, stair_plan, float(size[0]))))
        nseg = len(segs)
        for segi, ((x0, x1, off), panels) in enumerate(segs):
            out.append(Placement(SHEET_OBJECT, o[0], o[1], {
                # シートの段（下,上 mm。上下の段は重ねる）と左右の辺のハトメの間隔（クランプの高さと同じ並び）
                "rowList": row_list(rows), "gromPitch": pitch,
                # 開放端の妻側にシートを張る高さから上は、端の建地のクランプを妻側のシートのコーナー用に任せる
                "clampSZ": (ends.get("s", 0.0) if segi == 0 else 0.0) / 1000.0,
                "clampEZ": (ends.get("e", 0.0) if segi == nseg - 1 else 0.0) / 1000.0,
                "faceAng": ang, "zH": model.base_height_mm / 1000.0, "offY": off / 1000.0,
                "x0": x0 / 1000.0, "x1": x1 / 1000.0, "zT": top / 1000.0,
                # 下端は仮囲いの天端（利用者の指定 2026-10-24: 仮囲いまでにする）。防音パネルはいちばん下の段の下端
                # （仮囲いの天端に重なる）
                "zB": (sheet_rows(model, ep.edge_index)[0][0] if is_panel(model) and sheet_rows(model, ep.edge_index)
                       else sheet_bottom_mm(model, ep.edge_index)) / 1000.0,
                "sheetW": size[0] / 1000.0, "sheetKind": model.config.sheet_type, "lineMode": bool(line_mode),
                # 出隅の角はコーナー用のクランプ（始点を受け持ち、終点は次の面）
                "clampCS": int(segi == 0 and sheet_clamp_ends(model, ep)[0]),
                "clampSkipE": int(segi == nseg - 1 and sheet_clamp_ends(model, ep)[1]),
                # 区間の端のクランプは、シートの端にいちばん近い支柱に（sheet_clamp_positions と同じ）
                "clampEnd": 1 if panels else 0,
                "clampXS": (_clamp_post(ep, panels[0][0]) if panels else 0.0) / 1000.0,
                "clampXE": (_clamp_post(ep, panels[-1][1]) if panels else 0.0) / 1000.0,
                # 継ぎ目は足場の支柱の位置。「始点,終点,特殊(0/1)」の繰り返し mm（特殊シートは色を替える）
                "panelList": ",".join(f"{a:.0f},{b:.0f},{int(sp)}" for a, b, sp in panels),
                # シートクランプ（継ぎ目と端の支柱に、各段のシートの上下で。利用者の指定・資料 2026-10-24）
                "clampList": ",".join(f"{h:.0f}" for h in sheet_clamp_heights(model, ep.edge_index)),
                # 段の高さ（1枚の高さ）と、縁の縫い代・ハトメを描くか（線表示では描かない）
                "sheetH": size[1] / 1000.0, "fineOn": not bool(line_mode)}))
        # 外付け階段室の妻側: 部品の x を面の外向きにして（面の向き−90°）、外側建地列から3列目まで
        row = float(model.post_row_spacing_mm)
        for pos, shift in sheet_end_pieces(model, ep, stair_plan):
            out.append(Placement(SHEET_OBJECT, o[0] + _u[0] * pos, o[1] + _u[1] * pos, {
                "faceAng": ang - 90.0, "zH": model.base_height_mm / 1000.0, "offY": shift / 1000.0,
                "x0": (row + SHEET_GAP_MM) / 1000.0, "x1": (2 * row + SHEET_GAP_MM) / 1000.0,
                "zB": sheet_bottom_mm(model, ep.edge_index) / 1000.0, "zT": top / 1000.0, "sheetW": size[0] / 1000.0,
                "rowList": row_list(rows), "gromPitch": pitch,
                "sheetH": size[1] / 1000.0, "sheetKind": model.config.sheet_type, "lineMode": bool(line_mode)}))
        # 開放端の妻側: 始点は x を外向き（面の向き−90°）、終点は x を躯体向き（面の向き＋90°）にして、シートの面を端の
        # 支柱のあきだけ外へ。クランプは端の内側の建地に普通のもの、外側の建地（面のシートとの角）にコーナー用
        # （利用者の指定 2026-10-25: コーナー部分はコーナー用にして）。部品の +y 側が建地
        gap = SHEET_GAP_MM
        for end, z0 in open_end_sheets(model, ep):
            pos = 0.0 if end == "s" else float(sum(ep.spans))
            a, b = (0.0, row + gap) if end == "s" else (-(row + gap), 0.0)
            cs, ce = (0.0, row) if end == "s" else (-row, 0.0)
            out.append(Placement(SHEET_OBJECT, o[0] + _u[0] * pos, o[1] + _u[1] * pos, {
                "faceAng": ang - 90.0 if end == "s" else ang + 90.0, "zH": model.base_height_mm / 1000.0,
                "offY": gap / 1000.0, "x0": a / 1000.0, "x1": b / 1000.0,
                "zB": z0 / 1000.0, "zT": top / 1000.0, "sheetW": size[0] / 1000.0,
                "rowList": row_list(sheet_rows_from(model, ep.edge_index, z0)), "gromPitch": pitch,
                "panelList": f"{a:.0f},{b:.0f},{int(not any(abs(row - c) <= 1.0 for c in model.master.span_lengths()))}",
                "clampList": ",".join(f"{h:.0f}" for h in sheet_clamp_heights_from(model, ep.edge_index, z0)),
                "clampEnd": 1, "clampXS": cs / 1000.0, "clampXE": ce / 1000.0,
                "clampCS": int(end == "e"), "clampCE": int(end == "s"), "clampSkipE": int(end == "s"),
                "sheetH": size[1] / 1000.0, "sheetKind": model.config.sheet_type, "lineMode": bool(line_mode),
                "fineOn": not bool(line_mode)}))
    return _with_pens(model, out)


def sheet_quantities(model: ScaffoldModel, stair_plan=None, size=None) -> tuple[float, int]:
    """養生シートの面積（m²）と、足場のスパンと同じ幅のシートの枚数（升目 × 高さ÷1枚の高さ）。size で1枚の大きさを
    替えられる。幅ごとの内訳は standard_sheets、特殊シート（角・隙間）は special_sheets."""
    if (size or sheet_size(model)) is None:
        return 0.0, 0
    area = 0.0
    for ep in model.plan.edges:
        top = sheet_top_mm(model, ep.edge_index) - sheet_bottom_mm(model, ep.edge_index)
        for panels in sheet_panels(model, ep, stair_plan):
            area += sum(b - a for a, b, _sp in panels) / 1000.0 * top / 1000.0
        area += len(sheet_end_pieces(model, ep, stair_plan)) * float(model.post_row_spacing_mm) / 1000.0 * top / 1000.0
        full = sheet_top_mm(model, ep.edge_index)
        area += sum(float(model.post_row_spacing_mm) / 1000.0 * (full - z0) / 1000.0 for _e, z0 in open_end_sheets(model, ep))
    return area, sum(standard_sheets(model, stair_plan, size).values())


def _sheets_by_width(model: ScaffoldModel, stair_plan, size, special: bool) -> dict[int, int]:
    import math as _m

    size = size or sheet_size(model)
    if size is None:
        return {}
    out: dict[int, int] = {}
    for ep in model.plan.edges:
        rows = len(sheet_rows(model, ep.edge_index))
        ws = [b - a for panels in sheet_panels(model, ep, stair_plan) for a, b, sp in panels if sp == special]
        # 外付け階段の妻側は建地列の間隔の幅（スパンにある幅なら標準）
        row = float(model.post_row_spacing_mm)
        row_std = any(abs(row - c) <= 1.0 for c in model.master.span_lengths())
        if special != row_std:
            ws += [row] * len(sheet_end_pieces(model, ep, stair_plan))
        for w in ws:
            k = int(round(w))
            out[k] = out.get(k, 0) + rows
        # 開放端の妻側（建地列の間隔の幅。途中の屋根より上だけの端はその段だけ）
        if special != row_std:
            for _e, z0 in open_end_sheets(model, ep):
                k = int(round(row))
                out[k] = out.get(k, 0) + _n_rows_from(model, ep.edge_index, z0)
    return dict(sorted(out.items()))


def standard_sheets(model: ScaffoldModel, stair_plan=None, size=None) -> dict[int, int]:
    """足場のスパンと同じ幅のシートの {幅 mm: 枚数}（インチ・メートルとも普通にある幅）."""
    return _sheets_by_width(model, stair_plan, size, False)


def special_sheets(model: ScaffoldModel, stair_plan=None, size=None) -> dict[int, int]:
    """特殊シート（スパンに無い幅）の {幅 mm: 枚数}。角の升目・隅の隙間・入隅の取り合い、外付け階段の妻側."""
    return _sheets_by_width(model, stair_plan, size, True)


def sheet_clamp_count(model: ScaffoldModel, stair_plan=None) -> int:
    """シートクランプの数（sheet_placements の clampList と同じ: 継ぎ目と端の支柱 × 根がらみと各層の手すり）."""
    if sheet_size(model) is None:
        return 0
    n = sum(len(sheet_clamp_positions(model, ep, stair_plan)) * len(sheet_clamp_heights(model, ep.edge_index))
            for ep in model.plan.edges)
    # 開放端の妻側のシート: 端の内側の建地に普通のもの（外側の建地の角はコーナー用。面のシートの端の建地のクランプも
    # その高さから上はコーナー用に任せる）
    for ep in model.plan.edges:
        for _e, z0 in open_end_sheets(model, ep):
            hs = sheet_clamp_heights_from(model, ep.edge_index, z0)
            n += len(hs) - sum(1 for h in sheet_clamp_heights(model, ep.edge_index) if h >= z0 - 1.0)
    return n


def panel_corner_count(model: ScaffoldModel, stair_plan=None) -> int:
    """防音パネルの出隅の角の数（始点が出隅で、その面にパネルを張るもの）."""
    if not is_panel(model):
        return 0
    return len([ep for ep in model.plan.edges if sheet_clamp_ends(model, ep)[0] and any(sheet_panels(model, ep, stair_plan))])


def panel_corner_pieces(model: ScaffoldModel, stair_plan=None) -> int:
    """コーナーパネルの枚数（出隅の角 × 段）."""
    return sum(len(sheet_rows(model, ep.edge_index)) for ep in model.plan.edges
               if is_panel(model) and sheet_clamp_ends(model, ep)[0] and any(sheet_panels(model, ep, stair_plan)))


def sheet_corner_clamp_count(model: ScaffoldModel, stair_plan=None) -> int:
    """出隅の角の「養生クランプ コーナー用」の数（始点が出隅の面 × 各段のシートの上下）."""
    if sheet_size(model) is None:
        return 0
    n = sum(len(sheet_clamp_heights(model, ep.edge_index)) for ep in model.plan.edges
            if sheet_clamp_ends(model, ep)[0] and any(sheet_panels(model, ep, stair_plan)))
    # 開放端の妻側のシートと面のシートの角（外側の建地）
    n += sum(len(sheet_clamp_heights_from(model, ep.edge_index, z0)) for ep in model.plan.edges
             for _e, z0 in open_end_sheets(model, ep))
    return n


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
    return _with_pens(model, out)



def bridge_placements(model: ScaffoldModel, line_mode: bool = False) -> list[Placement]:
    """屋上への渡り（model.roof_bridges）ごとの部品. 原点は渡りの始めの位置の内側建地列（利用者の指定 2026-10-24）."""
    out: list[Placement] = []
    edges = {e.edge_index: e for e in model.plan.edges}
    base = float(model.base_height_mm or 0.0)
    for b in getattr(model, "roof_bridges", None) or []:
        ep = edges.get(b.edge_index)
        if ep is None:
            continue
        o, u, _nrm, ang = _frame(ep)
        out.append(Placement(BRIDGE_OBJECT, o[0] + u[0] * b.x_mm, o[1] + u[1] * b.x_mm, {
            "faceAng": ang, "brW": b.width_mm / 1000.0, "brL": b.length_mm / 1000.0,
            "zFrom": (base + b.z_from_mm) / 1000.0, "zTo": (base + b.z_to_mm) / 1000.0,
            "paraH": b.parapet_mm / 1000.0, "paraX": float(ep.standoff) / 1000.0,
            "lineMode": bool(line_mode)}))
    return _with_pens(model, out)
