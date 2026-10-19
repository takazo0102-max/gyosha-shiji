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
    from .quantity import wall_tie_required_length_mm

    out: list[Placement] = []
    edges = {e.edge_index: e for e in model.plan.edges}
    for t in model.wall_ties:
        ep = edges.get(t.edge_index)
        if ep is None:
            continue
        o, u, _n, ang = _frame(ep)
        need = wall_tie_required_length_mm(model, t.edge_index, t.position_mm)
        out.append(Placement(TIE_OBJECT, o[0] + u[0] * t.position_mm, o[1] + u[1] * t.position_mm, {
            "faceAng": ang, "zH": (t.height_mm + model.base_height_mm) / 1000.0, "tieL": need / 1000.0,
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
            for sp in ep.spans:          # 終点の建地は次の面が受け持つ
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
            n_bk += len(ep.spans)
    return area, n_bk


def netbk_clash_faces(model: ScaffoldModel) -> list[tuple[int, float]]:
    """ネットを張る面のうち、NL500 が最短でも躯体に当たる面（辺番号, 離れ mm）."""
    if not model.config.horizontal_net_levels:
        return []
    return [(ep.edge_index, float(ep.standoff)) for ep in model.plan.edges
            if net_heights_mm(model, ep.edge_index) and not netbk_arm_mm(ep.standoff)[1]]
