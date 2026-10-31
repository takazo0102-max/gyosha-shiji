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
                              TATE_PITCHES, TIE_ALLOW_KN, TUBE_LENGTHS, TUBE_OFF_MM, FormCheck, _stations, _subtract, check,
                              graded_levels, in_column, tube_pieces)

# 面の番号と向き（柱の芯からの回し角。面の上の座標 s は回したあとの X）: 1＝+Y、2＝−X、3＝−Y、4＝+X
FACE_ROT = (0.0, 90.0, 180.0, 270.0)

COL_OUT_MM = 30.0          # 角の外のフォームタイと、直交する面の型枠（外端太の外）のあき
TUBE_OVER_MM = 100.0       # 外端太の、角の外のフォームタイからの出
DZ_MM = 120.0              # ±X の面の外端太を上げる高さ（±Y の面の外端太と交差させない）
COL_TATE_PITCHES = TATE_PITCHES + (250.0, 200.0)   # 柱は側圧が高いので外端太をつめて、柱を貫くフォームタイを減らす

# コラムクランプ（利用者の指定 2026-10-31: コラムクランプで締める）: 壁の取り付かない柱は、外端太と角の外のフォームタイの
# かわりに、段ごとに4方から抱くコラムクランプ（腕は柱の面を角から角へ飛ばし、角で腕どうしをくさびで留める）. 腕の強さは
# 溝形鋼 [-75×40×5 相当の目安（使う製品の表で確かめる）、角の留め1か所の力は CLAMP_CORNER_KN まで
CLAMP_ARM = None
CLAMP_CORNER_KN = 20.0
CLAMP_H_MM, CLAMP_T_MM = 75.0, 40.0      # 腕のせい（縦）・出（合板に直角）
CLAMP_PITCHES = (600.0, 450.0, 300.0, 250.0, 200.0, 150.0)


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
    faces: list[dict] = None   # 面ごと {"ply": [(s, s)], "sangi": [s], "tube": [(s, s)]}（FACE_ROT の順。壁の取り付く所で分ける）
    dropped: int = 0           # 壁を貫くので外したフォームタイ（1段あたり）
    clamp: bool = False        # コラムクランプで締める（外端太・フォームタイなし）


    @property
    def ok(self) -> bool:
        return self.calc_x.ok and self.calc_y.ok

    def quantities(self) -> list[tuple[str, int, str]]:
        from collections import Counter

        rows = math.ceil(self.height / PANEL_H_MM)
        if self.clamp:
            n_ply = sum(math.ceil((b - a) / PANEL_W_MM) * rows for f in self.faces for a, b in f["ply"])
            n_sangi = sum(len(f["sangi"]) for f in self.faces)
            per = max(1, math.floor(4000.0 / self.height)) if self.height <= 4000.0 else 0
            sangi_pcs = math.ceil(n_sangi / per) if per else n_sangi * math.ceil(self.height / 4000.0)
            return [("型枠用合板 12mm（柱）", n_ply, f"4面 {self.width:.0f}×{self.depth:.0f}（幅 b の面は小口を覆って b＋24）"),
                    (f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}（4m）", sangi_pcs, f"縦・長さ {self.height:.0f}×{n_sangi}本"),
                    (f"コラムクランプ（{self.width:.0f}×{self.depth:.0f} 用）", len(self.tate_z),
                     f"{len(self.tate_z)}段・4方の腕を角でくさび留め（メーカーの使える柱の大きさ・間隔の表で確かめる）")]
        n_ply = sum(math.ceil((b - a) / PANEL_W_MM) * rows for f in self.faces for a, b in f["ply"])
        n_sangi = sum(len(f["sangi"]) for f in self.faces)
        per = max(1, math.floor(4000.0 / self.height)) if self.height <= 4000.0 else 0
        sangi_pcs = math.ceil(n_sangi / per) if per else n_sangi * math.ceil(self.height / 4000.0)
        tubes = Counter()
        for f in self.faces:
            for a, b in f["tube"]:
                for v in tube_pieces(b - a):
                    tubes[v] += 2 * len(self.tate_z)
        out = [("型枠用合板 12mm（柱）", n_ply, f"4面 {self.width:.0f}×{self.depth:.0f}（幅 b の面は小口を覆って b＋24）"),
               (f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}（4m）", sangi_pcs,
                f"縦・長さ {self.height:.0f}×{n_sangi}本（@{self.calc_x.sangi_pitch:.0f}・@{self.calc_y.sangi_pitch:.0f}）")]
        for v, n in sorted(tubes.items(), reverse=True):
            out.append((f"単管 {v / 1000:.1f}m（柱の外端太）", n, "2本組・4面"))
        hx, hy = self.width / 2.0, self.depth / 2.0
        n_out = sum(1 for x in self.tie_x if abs(x) > hx) * len(self.tate_z) + \
            sum(1 for y in self.tie_y if abs(y) > hy) * len(self.tate_z)
        n_thr = (sum(1 for x in self.tie_x if abs(x) <= hx) + sum(1 for y in self.tie_y if abs(y) <= hy)) * len(self.tate_z)
        out.append(("フォームタイ（柱の角の外）", n_out, "外端太どうしを角の外で締める（コンクリートに入らない）"))
        if n_thr:
            out.append(("フォームタイ（柱を貫く）", n_thr, "外端太のスパンを縮めるために柱を貫く"))
            out.append(("Pコン", 2 * n_thr, "柱を貫くフォームタイの両端"))
        return out

    def notes(self) -> list[str]:
        if self.clamp:
            return [] if self.ok else ["コラムクランプの間隔をいちばんつめても計算が通らない。セパを足すか大きいクランプを"]
        return ([f"壁を貫くのでフォームタイ {self.dropped}本/段を外しました。その面の外端太は壁の型枠の外端太に直交クランプで留める"]
                if self.dropped else [])


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


def _clamp_arm():
    from ashiba.formwork import STEEL_E, STEEL_FB, Member
    # 溝形鋼 [-75×40×5×7（強軸）: I＝75.3×10⁴ mm⁴、Z＝20.1×10³ mm³
    return Member("[-75×40×5 相当", STEEL_E, STEEL_FB, 20.1e3, 75.3e4)


def plan_column_clamp(width_mm: float, depth_mm: float, height_mm: float) -> ColumnForm:
    """壁の取り付かない柱をコラムクランプで締める型枠（せき板・桟木・コラムクランプ。フォームタイなし）."""
    arm = _clamp_arm()
    span_x = width_mm + 2 * (PLY_T_MM + SANGI_H_MM)          # ±Y の面の腕のスパン（角から角）
    span_y = depth_mm + 2 * (PLY_T_MM + SANGI_H_MM)
    # 角の留め: 腕1本の両端に p×間隔×スパン の半分ずつ。tie の値（p×間隔×スパン）で 2×CLAMP_CORNER_KN まで
    kw = dict(column=True, waler=arm, waler_name="コラムクランプの腕", tie_allow=2 * CLAMP_CORNER_KN,
              tie_name="コラムクランプの腕1本の力（角の留め2か所で受ける）")

    def best(span):
        top = None
        for sg in SANGI_PITCHES:
            for t in CLAMP_PITCHES:
                c = check(height_mm, sg, t, span, **kw)
                if c.ok:
                    key = (sg, t)
                    if top is None or key > top[0]:
                        top = (key, c)
        return top[1] if top else check(height_mm, SANGI_PITCHES[-1], CLAMP_PITCHES[-1], span, **kw)
    cx, cy = best(span_x), best(span_y)
    lx = graded_levels(height_mm, cx.sangi_pitch, span_x, cands=CLAMP_PITCHES, **kw)
    ly = graded_levels(height_mm, cy.sangi_pitch, span_y, cands=CLAMP_PITCHES, **kw)
    tate = lx if len(lx) >= len(ly) else ly
    sx = [x - width_mm / 2.0 for x in _stations(width_mm, cx.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    sy = [y - depth_mm / 2.0 for y in _stations(depth_mm, cy.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    hA, hB = width_mm / 2.0, depth_mm / 2.0
    faces = []
    for k in range(4):
        half = hA + PLY_T_MM if k % 2 == 0 else hB
        faces.append({"ply": [(-half, half)], "sangi": sorted(sx if k % 2 == 0 else sy), "tube": []})
    return ColumnForm(width_mm, depth_mm, height_mm, cx, cy, sx, sy, tate, [], [], faces, 0, clamp=True)


def plan_column(width_mm: float, depth_mm: float, height_mm: float, walls_local=(), clamp: bool = True) -> ColumnForm:
    """1本の柱（長方形）の型枠の割付. walls_local＝取り付く壁（柱の芯からの座標。wall_hits）. 壁が取り付かなければ
    コラムクランプで締める（clamp）。壁が取り付く柱は外端太とフォームタイ."""
    if clamp and not walls_local:
        return plan_column_clamp(width_mm, depth_mm, height_mm)
    tie_x, cx = _ties(width_mm / 2.0, depth_mm / 2.0, height_mm)      # ±Y の面の外端太（X の向き）のスパンで決まる
    tie_y, cy = _ties(depth_mm / 2.0, width_mm / 2.0, height_mm)
    tate_pitch = min(cx.tate_pitch, cy.tate_pitch)
    if cx.tate_pitch != tate_pitch:
        cx = check(height_mm, cx.sangi_pitch, tate_pitch, cx.tie_pitch, column=True)
    if cy.tate_pitch != tate_pitch:
        cy = check(height_mm, cy.sangi_pitch, tate_pitch, cy.tie_pitch, column=True)
    # 外端太の段は上ほど広げる（側圧は上ほど小さい。利用者の指定 2026-10-31: 柱のパイプピッチ多くね？）. 2つの向きのうち
    # 密な方にそろえる
    lx = graded_levels(height_mm, cx.sangi_pitch, cx.tie_pitch, column=True, cands=COL_TATE_PITCHES)
    ly = graded_levels(height_mm, cy.sangi_pitch, cy.tie_pitch, column=True, cands=COL_TATE_PITCHES)
    tate = lx if len(lx) >= len(ly) else ly
    sx = [x - width_mm / 2.0 for x in _stations(width_mm, cx.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    sy = [y - depth_mm / 2.0 for y in _stations(depth_mm, cy.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    hA, hB = width_mm / 2.0, depth_mm / 2.0
    # 壁の取り付く面は、壁の所でせき板・桟木・外端太を分ける（T 字と同じ納まり）
    faces = []
    for k, rot in enumerate(FACE_ROT):
        a = math.radians(rot)
        e, nrm = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        h = hB if k % 2 == 0 else hA
        half = hA + PLY_T_MM if k % 2 == 0 else hB
        sg = [x * e[0] + 0.0 for x in sx] if k % 2 == 0 else [y * e[1] for y in sy]
        sg = sorted(v * (1 if k % 2 == 0 else 1) for v in sg)
        ties = tie_x if k % 2 == 0 else tie_y
        tube = (min(ties) - TUBE_OVER_MM, max(ties) + TUBE_OVER_MM)
        gp, gt, gs = [], [], []
        for wl in walls_local:
            if abs((wl["dir"][0] * nrm[0] + wl["dir"][1] * nrm[1]) - 1.0) > 0.3:
                continue                                          # この面に取り付く壁でない
            for arr, grow, side in ((gp, 0.0, 0.0), (gt, TUBE_OFF_MM, TUBE_OFF_MM), (gs, 0.0, BAND_MM)):
                ss = []
                for p, sgn in ((wl["lo_pt"], -1.0), (wl["hi_pt"], 1.0)):
                    q = (p[0] + wl["n"][0] * sgn * side, p[1] + wl["n"][1] * sgn * side)
                    u = wl["dir"]
                    den = u[0] * nrm[0] + u[1] * nrm[1]
                    if abs(den) < 1e-9:
                        continue
                    t = (h + grow - (q[0] * nrm[0] + q[1] * nrm[1])) / den
                    x = (q[0] + u[0] * t, q[1] + u[1] * t)
                    ss.append(x[0] * e[0] + x[1] * e[1])
                if len(ss) == 2:
                    arr.append((min(ss), max(ss)))
        ply = _subtract((-half, half), gp)
        sangi = [v for v in sg if not any(a - SANGI_B_MM / 2.0 < v < b + SANGI_B_MM / 2.0 for a, b in gs)]
        faces.append({"ply": ply, "sangi": sangi, "tube": _subtract(tube, gt)})
    # 壁を貫くフォームタイは外す
    dropped = 0

    def through_wall(p0, p1):
        for k in range(41):
            q = (p0[0] + (p1[0] - p0[0]) * k / 40.0, p0[1] + (p1[1] - p0[1]) * k / 40.0)
            if abs(q[0]) <= hA and abs(q[1]) <= hB:
                continue
            if any(_in_poly_local(q, wl["poly"]) for wl in walls_local):
                return True
        return False
    yT, xT = hB + TUBE_OFF_MM, hA + TUBE_OFF_MM
    keep_x = [x for x in tie_x if not through_wall((x, -yT), (x, yT))]
    keep_y = [y for y in tie_y if not through_wall((-xT, y), (xT, y))]
    dropped = len(tie_x) - len(keep_x) + len(tie_y) - len(keep_y)
    return ColumnForm(width_mm, depth_mm, height_mm, cx, cy, sx, sy, tate, keep_x or tie_x, keep_y or tie_y, faces, dropped)


def _in_poly_local(p, poly) -> bool:
    inside = False
    for k in range(len(poly)):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % len(poly)]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def column_rect(col: dict) -> dict:
    """column_from_details の柱 → in_column 用の {"c", "ux", "uy", "hw", "hd"}."""
    a = math.radians(col["ang"])
    return {"c": col["c"], "ux": (math.cos(a), math.sin(a)), "uy": (-math.sin(a), math.cos(a)),
            "hw": col["width"] / 2.0, "hd": col["depth"] / 2.0}


def wall_hits(col: dict, walls: list[dict]) -> list[dict]:
    """柱に端が入る壁 → 柱の芯からの座標で [{"dir"（柱から離れる向き）, "n", "lo_pt", "hi_pt"（両面の線の上の点）, "poly"（壁の外形）}]."""
    r = column_rect(col)
    L = lambda p: ((p[0] - r["c"][0]) * r["ux"][0] + (p[1] - r["c"][1]) * r["ux"][1],
                   (p[0] - r["c"][0]) * r["uy"][0] + (p[1] - r["c"][1]) * r["uy"][1])
    V = lambda v: (v[0] * r["ux"][0] + v[1] * r["ux"][1], v[0] * r["uy"][0] + v[1] * r["uy"][1])
    out = []
    for A in walls:
        for P, sgn in ((A["ca"], 1.0), (A["cb"], -1.0)):
            if not in_column(P, r, 5.0):
                continue
            d = V((A["u"][0] * sgn, A["u"][1] * sgn))
            n = V(A["n"])
            lo = L((A["ca"][0] + A["n"][0] * A["lo"], A["ca"][1] + A["n"][1] * A["lo"]))
            hi = L((A["ca"][0] + A["n"][0] * A["hi"], A["ca"][1] + A["n"][1] * A["hi"]))
            poly = [L((Q[0] + A["n"][0] * o, Q[1] + A["n"][1] * o)) for Q, o in
                    ((A["ca"], A["lo"]), (A["cb"], A["lo"]), (A["cb"], A["hi"]), (A["ca"], A["hi"]))]
            # 面の線の点は向きに関わらず lo（n の負の側）・hi（正の側）。外へ延ばす向きは n の符号で
            out.append({"dir": d, "n": n, "lo_pt": lo, "hi_pt": hi, "poly": poly})
    return out


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
    # zCoordinate は下端の絶対の高さ（階の高さ＋bottomOffset。実機で確かめた: 基礎下端 −2000 の階に −500 で作ると
    # bottomOffset 1.5）。足すと二重になる（根切りの山留め −6000〜0 の天端を −6000 と読んでいた。2026-10-31）
    z0 = float(d.get("zCoordinate", 0.0)) * 1000.0
    return {"c": c, "width": w, "depth": dp, "ang": math.degrees(float(d.get("axisRotationAngle", 0.0))), "z0": z0,
            "height": float(d.get("height", 0.0)) * 1000.0}
