"""梁の型枠: 側板（せき板・桟木・外端太・フォームタイ）と底板（せき板・桟木・受けの単管）（利用者の指定 2026-10-31: 型枠を作る
仕組みを作成して さんぎ そとばた フォームタイを作って既存のモデルに自動配置するようにして）.

組み方:
- 側板: 底板の下面から、梁の上端（上にスラブがあればスラブの下端）まで。合板の外に桟木を縦、外端太（単管2本組）を梁の向きに、
  フォームタイは梁を貫いて両側の外端太を締める（壁の型枠と同じ計算。側圧は側板の高さで JASS 5 の壁の式）
- 底板: 梁の幅の合板。下に根太（角パイプ □50×50×2.3）を梁の向きに BOTTOM_SANGI 本、その下に杉大引 90×90 を梁に直角に
  UKE_PITCHES ごと（両側の側板の外へ出して側板の下端を押さえる）、大引の両端の下にパイプサポート（上端は大引に釘止め）。
  スラブ・梁下の詳細図（利用者の指定 2026-10-31）
- 底板の計算（formwork.py と同じ単純梁、たわみ 3mm）: 荷重はコンクリート W0×梁せい＋型枠 0.4＋作業 1.5 kN/m²。せき板のスパン＝
  根太の間、根太のスパン＝大引の間、大引のスパン＝両側のパイプサポートの間
- 梁の端: 柱の中に入れば柱の面で止め（外端太・桟木は柱の型枠の外）、どこにも入らなければ止め型枠
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ashiba.formwork import NEDA, OBIKI, PLY_E, PLY_FB, PLY_T_MM, Member, _beam
from ashiba.wall_form import (BAND_MM, EDGE_MM, PANEL_W_MM, SANGI, SANGI_B_MM, SANGI_H_MM, TUBE_FREE_MM, TUBE_OFF_MM,
                              W0_KN_M3, FormCheck, _rect_entry, _stations, choose, graded_levels, in_column, tube_pieces)

BOTTOM_SANGI = 3                      # 底板の下の桟木（梁の向き）のいちばん少ない本数（幅 300 以下は2本。合板が通るまで増やす）
UKE_PITCHES = (900.0, 750.0, 600.0, 450.0)   # 大引（杉 90×90。梁に直角）の間隔の候補（詳細図は @900）
BOT_NEDA_H_MM, BOT_OBIKI_H_MM = 50.0, 90.0   # 底の根太（角パイプ □50×50）・大引（杉 90×90）のせい
BEAM_MIN_LEVELS = 2                          # 側板の外端太のいちばん少ない段数（利用者の指定 2026-10-31）
UKE_OUT_MM = 150.0                    # 受けの単管の、側板の外端太の外への出
DEAD_FORM_KN = 0.4
LIVE_KN = 1.5


@dataclass
class BeamForm:
    length: float              # 型枠の範囲の長さ
    x0: float                  # 型枠の始め（梁の始めから）
    width: float
    depth: float               # 梁せい
    side_h: float              # 側板の高さ（底板の下面から。高い方）
    side: FormCheck            # 側板の計算
    bottom: list               # 底板の計算 [BeamCheck]
    uke_pitch: float
    sangi_x: list[float]       # 側板の桟木（梁の始めから）
    tate_z: list[float]        # 外端太の高さ（底板の下面から）
    tie_x: list[float]         # フォームタイ（梁の始めから）
    bot_y: list[float]         # 底の桟木の位置（梁の芯から）
    uke_x: list[float]         # 受けの単管（梁の始めから）
    tubes: tuple[float, float] = (0.0, 0.0)   # 側板の外端太の範囲（梁の始めから）
    ends: tuple[bool, bool] = (False, False)  # 止め型枠
    side_hs: tuple[float, float] = (0.0, 0.0)  # −Y・+Y の側板の高さ（片側だけスラブのある外周の梁は違う）
    tie_z: list[float] = field(default_factory=list)   # フォームタイを入れる外端太の高さ（両側の側板がある高さ）
    post_h: float = 0.0        # 受けの単管を受けるパイプサポートの長さ（床から。0 は床が分からない）
    sill_cross: bool = False   # 敷き桟木を梁に直角に（上のスラブの敷き桟木と向きを揃える）

    @property
    def post_kn(self) -> float:
        """パイプサポート1本の軸力（梁の幅の荷重×受けの間隔を両端の2本で）."""
        q = W0_KN_M3 * self.depth / 1000.0 + DEAD_FORM_KN + LIVE_KN
        return q * (self.width + 2 * (PLY_T_MM + BAND_MM)) / 1000.0 * self.uke_pitch / 1000.0 / 2.0

    @property
    def ok(self) -> bool:
        return self.side.ok and all(b.ok for b in self.bottom)

    def lines(self) -> list[str]:
        out = ["側板: " + s for s in self.side.lines()]
        for b in self.bottom:
            out.append(f"底板 {b.part}（{b.member}）スパン {b.span_mm:.0f}: σ {b.sigma:.1f}／{b.fb:.1f} N/mm²・"
                       f"たわみ {b.deflection_mm:.2f} mm {'可' if b.ok else '不可'}")
        if self.post_h:
            from ashiba.slab_form import ps_condition, ps_model

            out.append(f"パイプサポート 1本 {self.post_kn:.1f}／{self.ps_allow:.1f} kN（許容支持力。メーカーの表） "
                       f"{'可' if self.post_kn <= self.ps_allow + 1e-9 else '不可'}・長さ {self.post_h:.0f}（型式 {ps_model(self.post_h)}）・"
                       f"{ps_condition(self.post_h, self.ps_tied)}")
        return out

    @property
    def ps_tied(self) -> bool:
        """梁下の支柱も 3.4m を超えれば水平つなぎ（スラブの支保工の水平つなぎと一緒に）を設けて連係ありとする."""
        from ashiba.slab_form import PS_FREE_MAX_MM

        return self.post_h > PS_FREE_MAX_MM

    @property
    def ps_allow(self) -> float:
        """梁下のパイプサポート1本の許容支持力（kN。メーカーの表）."""
        from ashiba.slab_form import ps_allow_kn

        return ps_allow_kn(self.post_h, self.ps_tied)

    def quantities(self) -> list[tuple[str, int, str]]:
        from collections import Counter

        L = self.length
        n_side = sum(math.ceil(L / 1800.0) * math.ceil(h / PANEL_W_MM) for h in self.side_hs)
        n_bot = math.ceil(L / 1800.0) * math.ceil(self.width / PANEL_W_MM)
        tubes = Counter()
        n_lv = sum(1 for h in self.side_hs for z in self.tate_z if z < h - 30.0)
        for v in tube_pieces(self.tubes[1] - self.tubes[0]):
            tubes[v] += 2 * n_lv
        uke = next(v for v in (1000, 1500, 2000, 2500, 3000) if v >= self.width + 2 * (PLY_T_MM + BAND_MM + UKE_OUT_MM))
        n_sangi_side = 2 * len(self.sangi_x)
        out = [("型枠用合板 12mm（梁の側板）", n_side, f"両側・高さ {self.side_hs[0]:.0f}・{self.side_hs[1]:.0f}（1800 を横使い）"),
               ("型枠用合板 12mm（梁の底板）", n_bot, f"幅 {self.width:.0f}"),
               (f"桟木 {SANGI_B_MM:.0f}×{SANGI_H_MM:.0f}（側板・縦）", n_sangi_side, f"長さ {self.side_h:.0f}・@{self.side.sangi_pitch:.0f}"),
               ("角パイプ □50×50×2.3（底の根太・4m）", len(self.bot_y) * math.ceil(L / 4000.0), "梁の向き")]
        for v, n in sorted(tubes.items(), reverse=True):
            out.append((f"単管 {v / 1000:.1f}m（梁の外端太）", n, f"2本組・両側・{len(self.tate_z)}段"))
        out.append((f"杉大引 90×90 {uke / 1000:.1f}m（底）", len(self.uke_x), f"梁に直角 @{self.uke_pitch:.0f}。両端をパイプサポートで受け、釘止め"))
        if self.uke_x and self.sill_cross:
            w = self.width + 2 * (PLY_T_MM + 60.0 + 30.0) + 300.0
            out.append(("桟木 45×60（敷き桟木・4m）", math.ceil(len(self.uke_x) * w / 4000.0),
                        f"大引ごとに梁に直角（長さ {w:.0f}×{len(self.uke_x)}本。スラブの敷き桟木と向きを揃える）"))
        elif self.uke_x:
            sill = 2 * (self.uke_x[-1] - self.uke_x[0] + 300.0)
            out.append(("桟木 45×60（敷き桟木・4m）", math.ceil(sill / 4000.0), "パイプサポートの下に梁の向きに2列"))
        out.append(("パイプサポート", 2 * len(self.uke_x), "大引の両端の下"
                    + (f"・長さ {self.post_h:.0f}・1本 {self.post_kn:.1f}kN" if self.post_h > 0 else "")))
        if self.tie_x and self.tie_z:
            n = len(self.tie_x) * len(self.tie_z)
            out.append((f"フォームタイ（梁幅 {self.width:.0f}）", n, f"@{self.side.tie_pitch:.0f}"))
            out.append(("Pコン", 2 * n, "両端"))
        if any(self.ends):
            out.append(("型枠用合板 12mm（梁の止め型枠）", sum(self.ends), f"{self.width + 2 * PLY_T_MM:.0f}×{self.side_h:.0f}"))
        return out


def _bottom_check(depth: float, width: float, n_sangi: int, uke_pitch: float) -> list:
    q = (W0_KN_M3 * depth / 1000.0 + DEAD_FORM_KN + LIVE_KN) * 1e-3     # N/mm²
    qd = (W0_KN_M3 * depth / 1000.0 + DEAD_FORM_KN) * 1e-3
    ply = Member(f"合板 {PLY_T_MM:.0f}mm", PLY_E, PLY_FB, 1000.0 * PLY_T_MM ** 2 / 6.0, 1000.0 * PLY_T_MM ** 3 / 12.0)
    span = width / max(1, n_sangi - 1)
    trib = width / max(1, n_sangi - 1)
    # 大引は両側のパイプサポートの間（梁の幅＋側板の外まで）を、梁の幅の荷重で受ける（中央集中に近いが等分布で見る）
    ob_span = width + 2 * (PLY_T_MM + 60.0 + 30.0)
    w_ob = q * uke_pitch * width / ob_span
    wd_ob = qd * uke_pitch * width / ob_span
    return [_beam("せき板", ply, span, q * 1000.0, qd * 1000.0),
            _beam("根太", NEDA["角パイプ50"], uke_pitch, q * trib, qd * trib),
            _beam("大引", OBIKI["杉90"], ob_span, w_ob, wd_ob)]


def plan_beam(length_mm: float, width_mm: float, depth_mm: float, slab_t_mm=0.0, ext=None,
              tubes=None, sangi_rng=None, ends=(False, False), post_h_mm: float = 0.0) -> BeamForm:
    """1本の梁の型枠の割付. slab_t_mm＝上のスラブの厚さ（数か、−Y・+Y の側ごとの組）、ext＝側板・底板の範囲（梁の始めから）、
    tubes＝外端太の範囲、sangi_rng＝桟木を置ける範囲、post_h_mm＝梁下のパイプサポートの長さ（分かれば、1本の荷重が
    メーカーの許容支持力に入る大引の間隔にする）."""
    x0, x1 = ext or (0.0, length_mm)
    tub = tubes or (x0 - TUBE_FREE_MM, x1 + TUBE_FREE_MM)
    s0, s1 = sangi_rng or (x0, x1)
    ts = tuple(slab_t_mm) if isinstance(slab_t_mm, (tuple, list)) else (slab_t_mm, slab_t_mm)
    side_hs = tuple(max(100.0, depth_mm - t) + PLY_T_MM for t in ts)
    side_h = max(side_hs)
    side = choose(side_h, x1 - x0)
    sangi = [s0 + x for x in _stations(s1 - s0, side.sangi_pitch, SANGI_B_MM / 2.0 + 30.0)]
    edge = min(EDGE_MM, side_h / 4.0)
    tate = graded_levels(side_h, side.sangi_pitch, side.tie_pitch, x1 - x0, edge=edge)
    # 側板の外端太は2段以上（利用者の指定 2026-10-31: 側板の外端太は2段にして）. 1段なら上端の近くに足す
    if len(tate) < BEAM_MIN_LEVELS and side_h - edge - tate[-1] > 100.0:
        tate = tate + [side_h - edge]
    ties = [x0 + x for x in _stations(x1 - x0, side.tie_pitch, EDGE_MM)]
    # 底の桟木は、合板が通るまで本数を増やす（幅 300 以下は2本から）
    best = None
    allow = None
    if post_h_mm > 0:
        from ashiba.slab_form import PS_FREE_MAX_MM, ps_allow_kn

        allow = ps_allow_kn(post_h_mm, post_h_mm > PS_FREE_MAX_MM)
    q_ps = (W0_KN_M3 * depth_mm / 1000.0 + DEAD_FORM_KN + LIVE_KN) * (width_mm + 2 * (PLY_T_MM + BAND_MM)) / 1000.0 / 2.0
    for n in range(2 if width_mm <= 300.0 else BOTTOM_SANGI, 9):
        for p in UKE_PITCHES:
            chk = _bottom_check(depth_mm, width_mm, n, p)
            if all(c.ok for c in chk) and (allow is None or q_ps * p / 1000.0 <= allow + 1e-9):
                best = (p, chk, n)
                break
        if best:
            break
    if best is None:
        best = (UKE_PITCHES[-1], _bottom_check(depth_mm, width_mm, 8, UKE_PITCHES[-1]), 8)
    n = best[2]
    bot_y = [-width_mm / 2.0 + SANGI_B_MM / 2.0 + (width_mm - SANGI_B_MM) * k / (n - 1) for k in range(n)]
    uke = [x0 + x for x in _stations(x1 - x0, best[0], 150.0)]
    tie_z = [z for z in tate if z < min(side_hs) - 30.0]
    f = BeamForm(x1 - x0, x0, width_mm, depth_mm, side_h, side, best[1], best[0], sangi, tate, ties, bot_y, uke,
                 tub, tuple(ends), side_hs, tie_z)
    f.post_h = post_h_mm
    return f


def beam_extents(bm: dict, cols=()) -> dict:
    """梁の端が柱に入れば柱の面まで（外端太は柱の外端太の線、桟木は柱の型枠の外）→ {"ext", "tubes", "sangi", "ends"}."""
    L, u = bm["length"], bm["u"]
    ext, tub, sng = [0.0, L], [-TUBE_FREE_MM, L + TUBE_FREE_MM], [0.0, L]
    free = [True, True]
    n = (-u[1], u[0])
    for end, P in ((0, bm["ca"]), (1, bm["cb"])):
        for col in cols:
            if not in_column(P, col, 5.0):
                continue
            free[end] = False
            for arr, grow, side in ((ext, 0.0, 0.0), (tub, TUBE_OFF_MM, TUBE_OFF_MM), (sng, BAND_MM, BAND_MM)):
                ts = []
                for sg in (-1.0, 1.0):
                    off = sg * (bm["width"] / 2.0 + side)
                    q = (bm["ca"][0] + n[0] * off, bm["ca"][1] + n[1] * off)
                    t = _rect_entry(q, u, col, grow, end)
                    if t is not None:
                        ts.append(t)
                if ts:
                    arr[end] = min(ts) if end == 1 else max(ts)
    return {"ext": tuple(ext), "tubes": tuple(tub), "sangi": tuple(sng), "ends": tuple(free)}


def slab_over(bm: dict, slabs) -> tuple[float, float]:
    """梁の −Y・+Y の側の上にあるスラブの厚さ（天端が梁の上端と ±20 で、梁の脇 100 の点がスラブの中）. 無ければ 0."""
    from ashiba.slab_heights import _inside

    u, L = bm["u"], bm["length"]
    n = (-u[1], u[0])
    out = []
    for sg in (-1.0, 1.0):
        t = 0.0
        for f in (0.25, 0.5, 0.75):
            q = (bm["ca"][0] + u[0] * L * f + n[0] * sg * (bm["width"] / 2.0 + 100.0),
                 bm["ca"][1] + u[1] * L * f + n[1] * sg * (bm["width"] / 2.0 + 100.0))
            for sl in slabs:
                if abs(sl.top_mm - bm["top"]) <= 20.0 and _inside(q, sl.polygon):
                    t = max(t, sl.thickness_mm)
        out.append(t)
    return out[0], out[1]


def beam_from_details(det: dict) -> dict | None:
    """Tapir の梁の詳細 → {"ca", "cb"（芯 mm）, "u", "length", "width", "depth", "top", "ang"}. まっすぐな梁だけ."""
    from ashiba.beams import beam_from_details as _b

    d = det.get("details") or {}
    bm = _b(d)
    if bm is None or bm.width < 100.0:
        return None
    L = math.dist(bm.a, bm.b)
    if L < 300.0:
        return None
    u = ((bm.b[0] - bm.a[0]) / L, (bm.b[1] - bm.a[1]) / L)
    return {"ca": bm.a, "cb": bm.b, "u": u, "length": L, "width": bm.width, "depth": bm.top_mm - bm.bottom_mm,
            "top": bm.top_mm, "bottom": bm.bottom_mm, "ang": math.degrees(math.atan2(u[1], u[0]))}
