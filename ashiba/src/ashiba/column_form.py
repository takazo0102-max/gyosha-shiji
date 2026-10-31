"""柱の型枠: せき板・桟木・外端太（単管2本組）・フォームタイ（利用者の指定 2026-10-31: 型枠を作る仕組みを作成して さんぎ
そとばた フォームタイを作って既存のモデルに自動配置するようにして）.

組み方（壁の型枠 wall_form.py と同じ部材）:
- せき板は4面。±Y の面（幅 b の面）は ±X の面の合板の小口を覆う幅 b＋2×12、±X の面は奥行き d
- 桟木は面ごとに縦（SANGI_PITCH の候補から）
- 外端太は面ごとに単管2本組を横に。±Y の面の外端太（X の向き）は高さ tz、±X の面の外端太（Y の向き）は DZ_MM 上げて交差を逃がす
- フォームタイは柱の角の外（相手の面の型枠の外 COL_OUT_MM）で外端太どうしを締める。外端太のスパンが長すぎるときは柱を貫く
  フォームタイを間に足す
計算は壁と同じ（側圧は JASS 5 の柱の式）。外端太のスパン＝フォームタイの間.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ashiba.wall_form import (BAND_MM, EDGE_MM, PANEL_H_MM, PANEL_W_MM, PLY_T_MM, SANGI_B_MM, SANGI_H_MM, SANGI_PITCHES,
                              TATE_PITCHES, TIE_ALLOW_KN, TUBE_LENGTHS, FormCheck, _stations, check, tube_pieces)

COL_OUT_MM = 30.0          # 角の外のフォームタイと、直交する面の型枠（外端太の外）のあき
TUBE_OVER_MM = 100.0       # 外端太の、角の外のフォームタイからの出
DZ_MM = 120.0              # ±X の面の外端太を上げる高さ（±Y の面の外端太と交差させない）
COL_TATE_PITCHES = TATE_PITCHES + (250.0, 200.0)   # 柱は側圧が高いので外端太をつめて、柱を貫くフォームタイを減らす


@dataclass
class ColumnForm:
    width: float               # b（X）
    depth: float               # d（Y）
    height: float
    calc_x: FormCheck          # ±Y の面（外端太は X の向き。スパン＝X の向きのフォームタイの間）
    calc_y: FormCheck          # ±X の面
    sangi_x: list[float]       # ±Y の面の桟木の位置（柱の芯から X）
    sangi_y: list[float]       # ±X の面の桟木の位置（芯から Y）
    tate_z: list[float]        # 外端太の高さ（柱の下から。±X の面は DZ_MM 上）
    tie_x: list[float]         # Y の向きに締めるフォームタイの X の位置（芯から。両端は角の外）
    tie_y: list[float]         # X の向きに締めるフォームタイの Y の位置

    def tube_len_x(self) -> float:
        return self.tie_x[-1] - self.tie_x[0] + 2 * TUBE_OVER_MM

    def tube_len_y(self) -> float:
        return self.tie_y[-1] - self.tie_y[0] + 2 * TUBE_OVER_MM

    @property
    def ok(self) -> bool:
        return self.calc_x.ok and self.calc_y.ok

    def quantities(self) -> list[tuple[str, int, str]]:
        from collections import Counter

        rows = math.ceil(self.height / PANEL_H_MM)
        n_ply = 0
        for w in (self.width + 2 * PLY_T_MM, self.width + 2 * PLY_T_MM, self.depth, self.depth):
            n_ply += math.ceil(w / PANEL_W_MM) * rows
        n_sangi = 2 * (len(self.sangi_x) + len(self.sangi_y))
        per = max(1, math.floor(4000.0 / self.height)) if self.height <= 4000.0 else 0
        sangi_pcs = math.ceil(n_sangi / per) if per else n_sangi * math.ceil(self.height / 4000.0)
        tubes = Counter()
        for L in (self.tube_len_x(), self.tube_len_y()):
            for v in tube_pieces(L):
                tubes[v] += 2 * 2 * len(self.tate_z)
        out = [("型枠用合板 12mm（柱）", n_ply, f"4面 {self.width:.0f}×{self.depth:.0f}（幅 b の面は小口を覆って b＋24）"),
               (f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}（4m）", sangi_pcs,
                f"縦・長さ {self.height:.0f}×{n_sangi}本（@{self.calc_x.sangi_pitch:.0f}・@{self.calc_y.sangi_pitch:.0f}）")]
        for v, n in sorted(tubes.items(), reverse=True):
            out.append((f"単管 {v / 1000:.1f}m（柱の外端太）", n, "2本組・4面"))
        n_out = 2 * 2 * len(self.tate_z)
        n_thr = (len(self.tie_x) - 2 + len(self.tie_y) - 2) * len(self.tate_z)
        out.append(("フォームタイ（柱の角の外）", n_out, "外端太どうしを角の外で締める（コンクリートに入らない）"))
        if n_thr:
            out.append(("フォームタイ（柱を貫く）", n_thr, "外端太のスパンを縮めるために柱を貫く"))
            out.append(("Pコン", 2 * n_thr, "柱を貫くフォームタイの両端"))
        return out


def _check_span(height: float, span: float) -> FormCheck:
    """柱の側圧で、外端太のスパン span のときの、みな通る組のうち桟木の間隔がいちばん広く、次に外端太の間隔がいちばん広い組."""
    best = None
    for tate in COL_TATE_PITCHES:
        for sg in SANGI_PITCHES:
            c = check(height, sg, tate, span, column=True)
            if c.ok:
                key = (sg, tate)
                if best is None or key > best[0]:
                    best = (key, c)
    return best[1] if best else check(height, SANGI_PITCHES[-1], COL_TATE_PITCHES[-1], span, column=True)


def _ties(half: float, other_half: float, height: float) -> tuple[list[float], FormCheck]:
    """面の幅の半分 half の向きのフォームタイの位置（芯から）と、その外端太の計算. 両端は直交する面の型枠の外（角の外）、
    スパンが通らなければ間に柱を貫くフォームタイを足す（間隔は等しく）."""
    edge = half + BAND_MM + COL_OUT_MM
    for n in range(0, 8):
        span = 2 * edge / (n + 1)
        c = _check_span(height, span)
        if c.ok:
            return [-edge + 2 * edge * k / (n + 1) for k in range(n + 2)], c
    return [-edge + 2 * edge * k / 8 for k in range(9)], c


def plan_column(width_mm: float, depth_mm: float, height_mm: float) -> ColumnForm:
    """1本の柱（長方形）の型枠の割付."""
    tie_x, cx = _ties(width_mm / 2.0, depth_mm / 2.0, height_mm)      # ±Y の面の外端太（X の向き）のスパンで決まる
    tie_y, cy = _ties(depth_mm / 2.0, width_mm / 2.0, height_mm)
    tate_pitch = min(cx.tate_pitch, cy.tate_pitch)
    if cx.tate_pitch != tate_pitch:
        cx = check(height_mm, cx.sangi_pitch, tate_pitch, cx.tie_pitch, column=True)
    if cy.tate_pitch != tate_pitch:
        cy = check(height_mm, cy.sangi_pitch, tate_pitch, cy.tie_pitch, column=True)
    tate = _stations(height_mm, tate_pitch, EDGE_MM)
    sx = [x - width_mm / 2.0 for x in _stations(width_mm, cx.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    sy = [y - depth_mm / 2.0 for y in _stations(depth_mm, cy.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    return ColumnForm(width_mm, depth_mm, height_mm, cx, cy, sx, sy, tate, tie_x, tie_y)


def column_from_details(det: dict) -> dict | None:
    """Tapir の柱の詳細 → {"c"（芯 mm）, "width", "depth", "ang"（度）, "z0", "height"}. 長方形でまっすぐな柱だけ."""
    d = det.get("details") or {}
    if d.get("circleBased") or d.get("isSlanted"):
        return None
    o = d.get("origin")
    if not o:
        return None
    w, dp = float(d.get("width", 0.0)) * 1000.0, float(d.get("depth", 0.0)) * 1000.0
    if w < 100.0 or dp < 100.0:
        return None
    # 芯の位置は平面の外形の中心（基点が角のこともある）
    pts = [(float(p["x"]) * 1000.0, float(p["y"]) * 1000.0) for poly in (det.get("floorPlanPolygons") or [])
           for p in poly.get("coordinates", [])]
    if pts:
        c = ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0, (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0)
        if math.dist(c, (float(o["x"]) * 1000.0, float(o["y"]) * 1000.0)) > max(w, dp):
            c = (float(o["x"]) * 1000.0, float(o["y"]) * 1000.0)
    else:
        c = (float(o["x"]) * 1000.0, float(o["y"]) * 1000.0)
    if abs(float(d.get("axisRotationAngle", 0.0))) > 1e-6 and pts:
        c = (sum(p[0] for p in pts[:-1]) / max(1, len(pts) - 1), sum(p[1] for p in pts[:-1]) / max(1, len(pts) - 1))
    z0 = (float(d.get("zCoordinate", 0.0)) + float(d.get("bottomOffset", 0.0))) * 1000.0
    return {"c": c, "width": w, "depth": dp, "ang": math.degrees(float(d.get("axisRotationAngle", 0.0))), "z0": z0,
            "height": float(d.get("height", 0.0)) * 1000.0}
