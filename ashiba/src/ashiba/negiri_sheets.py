"""根切り・山留計画図（利用者の指定 2026-11-02: 各図面を参考にして、図面かボタンを追加してちょ）.

施工図の手引き（建築施工図研究会 平成16年。利用者が渡した PDF）の「根切・山留計画図」の組み方にならう: 平面図と断面図を併用し、
躯体の輪郭は破線、寸法の基準は通り芯（ここでは掘削の外形）と設計 GL、掘削の最終形（法肩・法尻・掘削深さ・余掘り）と山留め、
事前に確かめる項目のチェックシート。根切り図（negiri_run.py）が控える ashiba_out/根切り_<名前>_図.json（躯体の外形と条件）から
解き直して、型枠支保工計画図と同じ A3 横の HTML・PDF とレイアウト（「根切り n 図名」・サブセット「根切り・山留」）にする.

- 1枚目 平面図: 躯体（破線）・掘削の外形（法肩）・法尻・床付けの高さごとの色・山留め（太線）・断面の位置（A－A・B－B）・
  外形の寸法・床付けと法面の文字、右の欄に凡例と条件
- 2枚目 断面図: 切断線の上の掘削面（升目の高さ）・GL と地山の記号・躯体（破線。下端から天端まで）と砕石・捨てコン・
  山留め（根入れは山留め計算書による）・掘削深さと床付けの高さ・掘削の幅の寸法
- 3枚目 数量・判定・確認: 根切り・埋戻し・建設発生土・ダンプ・地業の数量、判定（安衛則・建築基準法施行令）、
  事前に確かめる項目（手引きの根切・山留のチェックシートの項目を、ashiba の言葉で）
"""

from __future__ import annotations

import html
import math

from .form_drawings import CSS, MARGIN, PAGE_H, PAGE_W, SCALES, TB_H, _dim, _page, _wrap
from .negiri import (DUMP_M3, LOOSE, Footprint, Negiri, dumps, inside, layers_of, level_color, slope_angle, solve, surplus)

ESC = html.escape
SERIES = "根切り"
SUBSET = "根切り・山留"
AREA = (MARGIN + 6.0, MARGIN + 14.0, PAGE_W - MARGIN - 118.0, PAGE_H - MARGIN - 8.0)   # 図を描く所（左・上・右・下 mm）
SIDE_X = PAGE_W - MARGIN - 112.0                                                    # 右の欄の左
EMBED_MM = 1000.0                  # 断面の山留めを床付けからこれだけ下まで描く（根入れの長さは山留め計算書。図の目安）
CHECKS = (   # 事前に確かめる項目（施工図の手引き 根切・山留計画図のチェックシートの項目を要約）
    ("敷地と周辺", "敷地の余裕と1日の掘削量", "近隣建物の境界からの離れ（重機の近接作業）",
     "周辺道路・敷地内の埋設管（沿道掘削の届出: 道路法44条。沿道区域は前面道路 20m 以上で 5m・6〜20m で 3m・6m 未満で幅員の 1/2）"),
    ("山留め", "掘削の深さと土質（山留めの工法）", "地下水位（止水壁が要るか）", "地下躯体と敷地境界の離れ（山留め壁を組む空き）",
     "躯体の施工順序（逆打ち・アイランド工法）", "山留め壁を撤去するか（撤去の工事ができるか）"),
    ("掘削", "基礎・基礎梁の下端の高さの基準（設計 GL か 1FL に統一）", "地業・捨てコンの厚さ（根切りの深さに入る）",
     "外部に防水等の作業があるか（躯体と掘削面の間隔）", "掘削機・ダンプの種類と大きさ（作業量・旋回）",
     "排水の方法（釜場・水中ポンプ・沈砂槽。下水への放流は届出）", "掘削の順序（出入口から遠い所から。最終段階の掘削機とダンプの位置）",
     "根切り底への昇降設備（鉄筋・型枠の動線）"),
)


def negiri_of(d: dict) -> Negiri:
    """控え（根切り_<名前>_図.json の中身）→ 解いた根切り."""
    zones = [Footprint(z["name"], [tuple(p) for p in z["pts"]], float(z["bottom"]), z.get("kind", "基礎"), z.get("top"))
             for z in d.get("zones", [])]
    keys = ("gl", "margin", "gravel", "lean", "doma_margin", "doma_gravel", "doma_lean", "slope", "depth", "soil", "general",
            "road_width", "kamaba_auto", "machine", "dump")
    kw = {k: d[k] for k in keys if k in d}
    road = [(tuple(a), tuple(b)) for a, b in d.get("road", [])]
    pits = [[tuple(p) for p in k] for k in d.get("kamaba", [])]
    return solve(Negiri(d.get("name", "根切り1"), zones, yamadome=[tuple(p) for p in d.get("yamadome", [])], road=road,
                        kamaba=pits, ywall=dict(d.get("ywall") or {}), **kw))


def _site_normal(n: Negiri, a, b) -> tuple[float, float]:
    """道路境界線 a→b の、敷地（躯体の重心）の側の単位法線."""
    L = math.dist(a, b) or 1.0
    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    pts = [p for f in n.zones for p in f.pts]
    if pts:
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        if (cx - a[0]) * nx + (cy - a[1]) * ny < 0:
            nx, ny = -nx, -ny
    return nx, ny


def default_cuts(n: Negiri) -> list[tuple[str, tuple, tuple]]:
    """断面の位置: 掘削の外形の真ん中を通る横（A－A）と縦（B－B）。外形の外へ 2m 延ばす."""
    pts = [p for r in n.top_rings for p in r] or [p for f in n.zones for p in f.pts]
    if not pts:
        return []
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # 真ん中が深い所を外れないよう、いちばん深い躯体の重心を通す
    deep = min(n.zones, key=lambda f: f.bottom, default=None)
    if deep is not None:
        cx = sum(p[0] for p in deep.pts) / len(deep.pts)
        cy = sum(p[1] for p in deep.pts) / len(deep.pts)
    return [("A", (x0 - 2000.0, cy), (x1 + 2000.0, cy)), ("B", (cx, y0 - 2000.0), (cx, y1 + 2000.0))]


def _scale_for(w_mm: float, h_mm: float, box_w: float, box_h: float) -> int:
    """図の大きさ w×h（実寸 mm）が box（紙 mm）に入るいちばん大きい縮尺 1/n."""
    for s in SCALES:
        if w_mm / s <= box_w and h_mm / s <= box_h:
            return s
    return int(math.ceil(max(w_mm / box_w, h_mm / box_h) / 100.0)) * 100


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in rgb)


def _poly(pts, cls: str, closed: bool = True) -> str:
    """多角形（closed）か、線の並び（開いた線は line で。レイアウトの変換は polyline を読まない）."""
    if closed and len(pts) >= 3:
        return f'<polygon points="{" ".join(f"{x:.2f},{y:.2f}" for x, y in pts)}" class="{cls}"/>'
    return "".join(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" class="{cls}"/>'
                   for a, b in zip(pts, pts[1:]))


def _text(x, y, s, cls="t", anchor="start", extra="") -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}" text-anchor="{anchor}"{extra}>{ESC(s)}</text>'


def _side(lines: list[tuple[str, str]], y: float) -> tuple[str, float]:
    """右の欄の見出しと箇条（折り返す）→ (SVG, 次の y)."""
    out = []
    for k, (head, body) in enumerate(lines):
        if head:
            y += 2.5 if k else 0.0
            out.append(_text(SIDE_X, y, head, "h2"))
            y += 5.0
        for ln in _wrap(body, 44):
            out.append(_text(SIDE_X + 2, y, ln, "ts"))
            y += 3.0
        y += 1.5
    return "".join(out), y


def cond_lines(n: Negiri) -> list[tuple[str, str]]:
    lf = LOOSE.get(n.soil, 1.2)
    slope = ("自動（積算基準の法の係数）" if n.slope is None else ("垂直" if n.slope <= 0 else f"1:{n.slope:g}（{slope_angle(n.slope):.0f}°）"))
    return ([("条件", f"GL＝設計 GL（プロジェクトの高さ {n.gl:,.0f}）。余掘り {n.margin:.0f}（土間 {n.doma_margin:.0f}）、"
                     f"砕石 {n.gravel:.0f}・捨てコン {n.lean:.0f}（土間 {n.doma_gravel:.0f}・{n.doma_lean:.0f}）、法面 {slope}、"
                     f"地山「{n.soil}」" + ("、山留めの内は山留めまで掘る" if n.yamadome else "")),
            ("数量（地山）", f"掘削 {n.area:,.1f}m²・{n.volume:,.1f}m³、埋戻し {n.backfill:,.1f}m³、建設発生土 {surplus(n):,.1f}m³"
                          f"（ほぐし L {lf:g} で {surplus(n) * lf:,.1f}m³・10t ダンプ 延べ {dumps(n)} 台。1台 {DUMP_M3:g}m³ は目安）")]
            + ([("沿道掘削", f"沿道区域 {n.endo['zone'] / 1000:g}m（前面道路 {n.road_width / 1000:g}m）。道路境界から 45° の影響斜線より"
                            + ("深く掘る所があるので道路管理者と事前協議" if n.endo.get("over") else "浅い")
                            + "（東京都の建設事務所の沿道掘削協議申請案内）")] if n.endo else []))


# ---------------------------------------------------------------- 1枚目 平面図
def plan_page(n: Negiri, cuts: list) -> tuple[str, str, str]:
    pts = [p for r in n.top_rings for p in r] + [p for f in n.zones for p in f.pts] + list(n.yamadome)
    for _l, a, b in cuts:
        pts += [a, b]
    for a, b in n.road:
        pts += [a, b]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    bw, bh = AREA[2] - AREA[0] - 16.0, AREA[3] - AREA[1] - 16.0
    sc = _scale_for(x1 - x0, y1 - y0, bw, bh)
    ox = AREA[0] + 8.0 + (bw - (x1 - x0) / sc) / 2
    oy = AREA[1] + 8.0 + (bh - (y1 - y0) / sc) / 2
    P = lambda p: (ox + (p[0] - x0) / sc, oy + (y1 - p[1]) / sc)
    out = []
    # 床付けの高さごとの色（浅い順に塗り、深い所を上に）
    for L in n.levels:
        col = _hex(level_color(n, L))
        out += [f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in map(P, r))}" fill="{col}" stroke="none"/>'
                for r in n.bottom_rings.get(L, [])]
    for r in n.top_rings:
        out.append(_poly([P(p) for p in r], "slab"))
    for L in n.levels:
        out += [_poly([P(p) for p in r], "thin") for r in n.bottom_rings.get(L, [])]
    for f in n.zones:
        out.append(_poly([P(p) for p in f.pts], "beam"))                  # 躯体の輪郭は破線（手引き）
    if n.yamadome:
        out.append(f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in map(P, n.yamadome))}" fill="none" '
                   'stroke="#000" stroke-width="0.7"/>')
        ya = P(max(n.yamadome, key=lambda p: (p[1], -p[0])))
        out.append(_text(ya[0] + 1.5, ya[1] - 1.5, "山留め（内面）", "ts"))
    # 床付けの文字（平らな所の重心。さらに深く掘る所の中なら輪の角寄り）
    for L, rs in n.bottom_rings.items():
        for r in rs:
            cx = sum(p[0] for p in r) / len(r)
            cy = sum(p[1] for p in r) / len(r)
            if any(inside((cx, cy), q) for q in n.edge_rings.get(L, [])):
                v = r[0]
                d = math.dist(v, (cx, cy)) or 1.0
                cx, cy = v[0] + (cx - v[0]) * 1500.0 / d, v[1] + (cy - v[1]) * 1500.0 / d
            q = P((cx, cy))
            out.append(_text(q[0], q[1], f"床付け GL{L - n.gl:+,.0f}", "ts", "middle"))
    # 外形の寸法（法肩の外接矩形）
    tp = [p for r in n.top_rings for p in r]
    if tp:
        ax0, ax1 = min(p[0] for p in tp), max(p[0] for p in tp)
        ay0, ay1 = min(p[1] for p in tp), max(p[1] for p in tp)
        a, b = P((ax0, ay0)), P((ax1, ay0))
        out.append(_dim(a[0], a[1] + 6, b[0], b[1] + 6, f"{ax1 - ax0:,.0f}", off=-3.0))
        a, b = P((ax1, ay0)), P((ax1, ay1))
        out.append(_dim(a[0] + 6, a[1], b[0] + 6, b[1], f"{ay1 - ay0:,.0f}", off=-3.0))
    # 釜場（太線の矩形と底の高さ）
    for k, p in enumerate(n.pits, 1):
        out.append(f'<polygon points="{" ".join(f"{a:.2f},{b:.2f}" for a, b in map(P, p["pts"]))}" fill="#9cc3e6" stroke="#000" '
                   'stroke-width="0.35"/>')
        q = P((sum(v[0] for v in p["pts"]) / len(p["pts"]), max(v[1] for v in p["pts"])))
        out.append(_text(q[0], q[1] - 1.0, f"釜場{k} 底 GL{p['bottom'] - n.gl:+,.0f}", "ts", "middle"))
    # 道路境界線（二点鎖線）と沿道区域（破線）
    for a, b in n.road:
        pa, pb = P(a), P(b)
        out.append(f'<line x1="{pa[0]:.2f}" y1="{pa[1]:.2f}" x2="{pb[0]:.2f}" y2="{pb[1]:.2f}" stroke="#000" stroke-width="0.25" '
                   'stroke-dasharray="4 1 0.6 1 0.6 1"/>')
        if n.endo:
            nx, ny = _site_normal(n, a, b)
            z = n.endo["zone"]
            qa, qb = P((a[0] + nx * z, a[1] + ny * z)), P((b[0] + nx * z, b[1] + ny * z))
            out.append(f'<line x1="{qa[0]:.2f}" y1="{qa[1]:.2f}" x2="{qb[0]:.2f}" y2="{qb[1]:.2f}" class="beam"/>')
            out.append(_text((qa[0] + qb[0]) / 2, (qa[1] + qb[1]) / 2 - 1.0, f"沿道区域 {z / 1000:g}m", "ts", "middle"))
            out.append(_text((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2 + 3.0, "道路境界線", "ts", "middle"))
    # 断面の位置
    for lab, a, b in cuts:
        pa, pb = P(a), P(b)
        out.append(f'<line x1="{pa[0]:.2f}" y1="{pa[1]:.2f}" x2="{pb[0]:.2f}" y2="{pb[1]:.2f}" class="cut"/>')
        for q in (pa, pb):
            out.append(f'<circle cx="{q[0]:.2f}" cy="{q[1]:.2f}" r="2.2" class="mark"/>')
            out.append(_text(q[0], q[1] + 1.0, lab, "t", "middle"))
    # 右の欄: 凡例・条件
    side = [_text(SIDE_X, AREA[1] + 2, "凡例", "h2")]
    y = AREA[1] + 7
    for cls, label in (("slab", "法肩（掘削の外形・GL）"), ("thin", "法尻（床付けの平らな所の外形）"), ("beam", "躯体の輪郭（破線）"),
                       ("cut", "断面の位置")):
        side.append(f'<line x1="{SIDE_X}" y1="{y - 1:.2f}" x2="{SIDE_X + 12}" y2="{y - 1:.2f}" class="{cls}"/>')
        side.append(_text(SIDE_X + 15, y, label, "ts"))
        y += 4.0
    if n.yamadome:
        side.append(f'<line x1="{SIDE_X}" y1="{y - 1:.2f}" x2="{SIDE_X + 12}" y2="{y - 1:.2f}" stroke="#000" stroke-width="0.7"/>')
        side.append(_text(SIDE_X + 15, y, "山留め壁の内面", "ts"))
        y += 4.0
        if n.ywall:
            # 「山留め壁」で割り付けた山留め（施工図の手引き p.38〜39: 種類・打設ピッチ・長さを書く）
            side.append(_text(SIDE_X, y, f"{n.ywall.get('name', '')}: {n.ywall.get('label', '')}", "ts"))
            y += 4.0
            if n.ywall.get("wales"):
                side.append(_text(SIDE_X, y, f"腹起し・切梁 {n.ywall.get('wale', '')} "
                                  + "・".join(f"GL-{z:,.0f}" for z in n.ywall["wales"]), "ts"))
                y += 4.0
    for L in n.levels:
        side.append(f'<rect x="{SIDE_X}" y="{y - 3:.2f}" width="12" height="3" fill="{_hex(level_color(n, L))}" stroke="#000" '
                    'stroke-width="0.1"/>')
        side.append(_text(SIDE_X + 15, y, f"床付け GL{L - n.gl:+,.0f}", "ts"))
        y += 4.0
    body, y = _side(cond_lines(n), y + 3)
    return "根切り 平面図", f"1/{sc}", "".join(out) + "".join(side) + body


# ---------------------------------------------------------------- 2枚目 断面図
def z_at(n: Negiri, p) -> float:
    """点の掘削面の高さ（いちばん近い升目）。升目の外は GL."""
    i = int(round((p[0] - n.origin[0]) / n.step))
    j = int(round((p[1] - n.origin[1]) / n.step))
    if 0 <= i < n.nx and 0 <= j < n.ny:
        return n.z[j][i]
    return n.gl


def crossings(a, b, poly) -> list[float]:
    """線分 a→b が多角形の辺と交わる所（a からの距離 mm、小さい順）."""
    L = math.dist(a, b) or 1.0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    out = []
    for k in range(len(poly)):
        p, q = poly[k], poly[(k + 1) % len(poly)]
        ex, ey = q[0] - p[0], q[1] - p[1]
        den = ux * ey - uy * ex
        if abs(den) < 1e-9:
            continue
        t = ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / den
        s = ((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) / den
        if 0.0 <= t <= L and 0.0 <= s <= 1.0:
            out.append(t)
    return sorted(out)


def _seg_cross(a, b, p, q) -> list[float]:
    """線分 a→b が線分 p→q と交わる所（a からの mm）."""
    L = math.dist(a, b) or 1.0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    ex, ey = q[0] - p[0], q[1] - p[1]
    den = ux * ey - uy * ex
    if abs(den) < 1e-9:
        return []
    t = ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / den
    s = ((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) / den
    return [t] if 0.0 <= t <= L and 0.0 <= s <= 1.0 else []


def spans_inside(a, b, poly) -> list[tuple[float, float]]:
    """線分のうち多角形の中の区間 [(始め, 終わり)]（a からの mm）."""
    ts = crossings(a, b, poly)
    L = math.dist(a, b) or 1.0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    pts = [0.0] + ts + [L]
    out = []
    for t0, t1 in zip(pts, pts[1:]):
        m = (t0 + t1) / 2
        if t1 - t0 > 1.0 and inside((a[0] + ux * m, a[1] + uy * m), poly):
            out.append((t0, t1))
    return out


def profile(n: Negiri, a, b) -> list[tuple[float, float]]:
    """切断線の上の掘削面 [(a からの mm, 高さ mm)]（升目ごと。高さの変わる所だけ残す）."""
    L = math.dist(a, b)
    k = max(2, int(L / n.step) + 1)
    raw = [(L * i / (k - 1), z_at(n, (a[0] + (b[0] - a[0]) * i / (k - 1), a[1] + (b[1] - a[1]) * i / (k - 1)))) for i in range(k)]
    out = [raw[0]]
    for i in range(1, len(raw) - 1):
        (t0, z0), (t1, z1), (t2, z2) = out[-1], raw[i], raw[i + 1]
        if abs((z1 - z0) * (t2 - t0) - (z2 - z0) * (t1 - t0)) > 1e-3 * max(1.0, t2 - t0):
            out.append(raw[i])
    out.append(raw[-1])
    return out


def machines_svg(n: Negiri, prof, X, Y, sc: float, L: float) -> str:
    """最終段階の掘削機（バックホウ）とダンプ（施工図の手引き p.39 の根切・山留断面図の例）: 掘削のいちばん左の縁の外の GL に
    バックホウ（クローラ・上部旋回体・ブーム・アーム・バケット）、その外にダンプ。寸法は machine.MACHINES（メーカーの仕様書）."""
    from .machine import MACHINES
    from .negiri import pick_backhoe

    exc = [(t, z) for t, z in prof if z < n.gl - 1.0]
    if not exc:
        return ""
    deep = n.gl - min(z for _t, z in exc)
    m = MACHINES[pick_backhoe(deep, n.machine)[0]]
    P = m.params
    edge = min(t for t, _z in exc)                                     # 掘削の左の縁
    tl, th, uh = P["trkL"] * 1000, P["trkH"] * 1000, P["upH"] * 1000
    cx = edge - tl / 2 - 500.0                                         # 縁から 0.5m 離して据える（目安）
    out = []
    g = n.gl
    out.append(f'<rect x="{X(cx - tl / 2):.2f}" y="{Y(g + th):.2f}" width="{tl / sc:.2f}" height="{th / sc:.2f}" '
               'fill="#666" stroke="#000" stroke-width="0.15"/>')                      # クローラ
    out.append(f'<rect x="{X(cx - tl * 0.45):.2f}" y="{Y(g + uh):.2f}" width="{tl * 0.8 / sc:.2f}" height="{(uh - th) / sc:.2f}" '
               'fill="#f2c94c" stroke="#000" stroke-width="0.15"/>')                   # 上部旋回体
    # ブームの根元（旋回体の前・上）から、掘削の中（縁から 1m・床付け）のバケットまで、ブームとアームの2本で
    piv = (cx + tl * 0.3, g + uh * 0.7)
    tip = (min(edge + 1000.0, L), min(z for t, z in exc if t >= edge))
    bl, al = P["boomL"] * 1000, P["armL"] * 1000
    dx, dz = tip[0] - piv[0], tip[1] - piv[1]
    d = math.hypot(dx, dz)
    if d < bl + al:                                                    # 2本の腕の肘（上へ曲げる）
        a0 = math.atan2(dz, dx)
        cosb = max(-1.0, min(1.0, (bl * bl + d * d - al * al) / (2 * bl * d)))
        a1 = a0 + math.acos(cosb)
        elbow = (piv[0] + bl * math.cos(a1), piv[1] + bl * math.sin(a1))
    else:
        elbow = ((piv[0] + tip[0]) / 2, (piv[1] + tip[1]) / 2)
    for p, q in ((piv, elbow), (elbow, tip)):
        out.append(f'<line x1="{X(p[0]):.2f}" y1="{Y(p[1]):.2f}" x2="{X(q[0]):.2f}" y2="{Y(q[1]):.2f}" stroke="#000" stroke-width="0.5"/>')
    out.append(f'<circle cx="{X(tip[0]):.2f}" cy="{Y(tip[1]):.2f}" r="{max(0.6, 300.0 / sc):.2f}" fill="#666" stroke="#000" stroke-width="0.1"/>')
    out.append(_text(X(cx), Y(g + uh) - 1.2, f"{m.name}（最大掘削深さ {P['maxD']:.2f}m）", "ts", "middle"))
    dm = MACHINES.get(n.dump)
    if dm:
        Q = dm.params
        cl, ch = Q["carL"] * 1000, Q["cabH"] * 1000
        x1 = cx - tl / 2 - 800.0                                       # ダンプの後ろの端（バックホウの外）
        out.append(f'<rect x="{X(x1 - cl * 0.72):.2f}" y="{Y(g + ch * 0.85):.2f}" width="{cl * 0.72 / sc:.2f}" height="{ch * 0.55 / sc:.2f}" '
                   'fill="#9aa0a8" stroke="#000" stroke-width="0.15"/>')               # 荷台
        out.append(f'<rect x="{X(x1 - cl):.2f}" y="{Y(g + ch):.2f}" width="{cl * 0.26 / sc:.2f}" height="{ch * 0.8 / sc:.2f}" '
                   'fill="#e8e8e8" stroke="#000" stroke-width="0.15"/>')               # 運転室
        for wx in (x1 - cl * 0.85, x1 - cl * 0.25):
            out.append(f'<circle cx="{X(wx):.2f}" cy="{Y(g + 450.0):.2f}" r="{450.0 / sc:.2f}" fill="#333"/>')
        out.append(_text(X(x1 - cl / 2), Y(g + ch) - 1.2, dm.name, "ts", "middle"))
    return "".join(out)


def _section(n: Negiri, lab: str, a, b, x0: float, y0: float, w: float, h: float, machines: bool = False) -> str:
    """1つの断面（紙の範囲 x0, y0, w, h の中）."""
    L = math.dist(a, b)
    prof = profile(n, a, b)
    zmin = min([z for _t, z in prof] + [f.bottom - sum(layers_of(n, f)) for f in n.zones]) - EMBED_MM - 500.0
    if n.yamadome and (n.ywall or {}).get("length"):                    # 山留め壁の先（根入れ）まで入るように
        zmin = min(zmin, n.gl + float(n.ywall.get("top_up", 0.0)) - float(n.ywall["length"]) - 500.0)
    zmax = n.gl + (3500.0 if machines else 1500.0)                    # 掘削機の背の分
    pre = 14000.0 if machines else 0.0                                 # 左にバックホウとダンプを置く分（GL の外）
    sc = _scale_for(L + pre, zmax - zmin, w - 30.0, h - 16.0)
    left = x0 + 18.0 + pre / sc
    top = y0 + 8.0
    X = lambda t: left + t / sc
    Y = lambda z: top + (zmax - z) / sc
    out = [_text(x0, y0 + 4.0, f"{lab}－{lab}' 断面図　S=1/{sc}", "h2")]
    # 掘削面と GL
    pts = [(X(t), Y(z)) for t, z in prof]
    out.append(_poly(pts, "slab", closed=False))
    # 地山の記号（GL の両脇に斜めの短い線）
    exc = [t for t, z in prof if z < n.gl - 1.0]
    if exc:
        for t0, t1 in ((0.0, min(exc)), (max(exc), L)):
            k = t0
            while k + 400.0 * sc / 100.0 <= t1:
                gx = X(k)
                out.append(f'<line x1="{gx:.2f}" y1="{Y(n.gl):.2f}" x2="{gx + 1.2:.2f}" y2="{Y(n.gl) + 1.2:.2f}" class="thin"/>')
                k += 3.0 * sc
    # 躯体（破線）と砕石・捨てコン
    for f in n.zones:
        top_z = n.gl if f.top is None else f.top
        g, le = layers_of(n, f)
        for t0, t1 in spans_inside(a, b, f.pts):
            out.append(f'<rect x="{X(t0):.2f}" y="{Y(top_z):.2f}" width="{(t1 - t0) / sc:.2f}" height="{(top_z - f.bottom) / sc:.2f}" '
                       'class="beam"/>')
            if g + le > 0:
                e0, e1 = max(0.0, t0 - 100.0), min(L, t1 + 100.0)                 # 出幅 0.1m
                out.append(f'<rect x="{X(e0):.2f}" y="{Y(f.bottom):.2f}" width="{(e1 - e0) / sc:.2f}" height="{(g + le) / sc:.2f}" '
                           'fill="#d8d8d8" stroke="#555" stroke-width="0.1"/>')
    # 山留め
    if n.yamadome:
        deep = min(z for _t, z in prof)
        yw = n.ywall or {}
        z_top = n.gl + float(yw.get("top_up", 300.0)) if yw else n.gl + 300.0
        z_bot = z_top - float(yw["length"]) if yw.get("length") else deep - EMBED_MM
        tt = sorted(crossings(a, b, n.yamadome))
        for t in tt:
            out.append(f'<line x1="{X(t):.2f}" y1="{Y(z_top):.2f}" x2="{X(t):.2f}" y2="{Y(z_bot):.2f}" '
                       'stroke="#000" stroke-width="0.7"/>')
        if tt:
            note = (f"{yw.get('label', '')}（根入れ {float(yw.get('embed', 0)) / 1000:.1f}m）" if yw else
                    "山留め（根入れは山留め計算書による）")
            out.append(_text(X(tt[0]) - 1.0, Y(z_bot) + 3.0, note, "ts"))
        if yw and len(tt) >= 2:
            t0, t1 = tt[0], tt[-1]
            hw = float(yw.get("wale_h") or 300.0)
            for z in yw.get("wales") or []:
                zc = n.gl - float(z)
                for tx, sg in ((t0, 1.0), (t1, -1.0)):
                    x0 = X(tx + (100.0 if sg > 0 else -100.0 - hw))
                    out.append(f'<rect x="{x0:.2f}" y="{Y(zc + hw / 2):.2f}" width="{hw / sc:.2f}" height="{hw / sc:.2f}" '
                               'fill="#b03020" stroke="#000" stroke-width="0.1"/>')
                # 切梁は狭い向きだけ。この断面の腹起しの間が切梁の長さと合うときに線で描く（長い向きの断面には出ない）
                span = (t1 - t0) - 2 * (100.0 + hw)
                along = yw.get("struts") and abs(span - float(yw.get("strut_len") or span)) < 1000.0
                if along:
                    out.append(f'<line x1="{X(t0 + 100.0 + hw):.2f}" y1="{Y(zc):.2f}" x2="{X(t1 - 100.0 - hw):.2f}" y2="{Y(zc):.2f}" '
                               'stroke="#b03020" stroke-width="0.35" stroke-dasharray="3 1"/>')
                out.append(_text(X(t1) + 1.0, Y(zc) + 1.0, f"腹起し{'・切梁' if along else ''} {yw.get('wale', '')} "
                                 f"GL-{float(z):,.0f}", "ts", "start"))
            for nm, zb in (yw.get("stages") or [])[:-1]:
                zz = n.gl - float(zb)
                out.append(f'<line x1="{X(t0):.2f}" y1="{Y(zz):.2f}" x2="{X(t1):.2f}" y2="{Y(zz):.2f}" stroke="#2050a0" '
                           'stroke-width="0.25" stroke-dasharray="1.5 1"/>')
                out.append(_text(X(t0) + 1.0, Y(zz) - 0.8, f"{nm}の底 GL-{float(zb):,.0f}", "ts"))
    # 道路境界と 45° の影響斜線（沿道掘削。境界から敷地の側へ、深さ＝境界からの距離）
    for ra, rb in n.road:
        for t in _seg_cross(a, b, ra, rb):
            nx, ny = _site_normal(n, ra, rb)
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            side = 1.0 if ux * nx + uy * ny > 0 else -1.0             # 切断線の向きで敷地は前か後ろか
            cosv = abs(ux * nx + uy * ny) or 1.0                       # 斜めに切るときは断面の上で斜線がゆるくなる
            depth = (n.gl - zmin) * 0.9
            t1 = t + side * depth / cosv
            out.append(f'<line x1="{X(t):.2f}" y1="{Y(n.gl + 800.0):.2f}" x2="{X(t):.2f}" y2="{Y(zmin):.2f}" stroke="#000" '
                       'stroke-width="0.2" stroke-dasharray="4 1 0.6 1 0.6 1"/>')
            out.append(f'<line x1="{X(t):.2f}" y1="{Y(n.gl):.2f}" x2="{X(t1):.2f}" y2="{Y(n.gl - depth):.2f}" class="cut"/>')
            out.append(_text(X(t) + 1.0, Y(n.gl + 800.0), "道路境界", "ts"))
            out.append(_text(X(t + side * 1500.0 / cosv) + side * 1.0, Y(n.gl - 1500.0), "45° 影響斜線", "ts",
                             "start" if side > 0 else "end"))
    if machines:
        out.append(machines_svg(n, prof, X, Y, sc, L))
        out.append(f'<line x1="{X(-pre):.2f}" y1="{Y(n.gl):.2f}" x2="{X(0):.2f}" y2="{Y(n.gl):.2f}" class="slab"/>')
    # 高さの文字と掘削深さの寸法
    gx = X(-pre) - 2.0                                                 # 重機を描くときはその外（左端）に
    out.append(_text(X(L) + 1.0, Y(n.gl) - 0.8, "▽設計GL±0", "ts"))
    seen = set()
    for t, z in prof:
        if z < n.gl - 1.0 and round(z) not in seen and any(abs(z - L2) < 1.0 for L2 in n.levels):
            seen.add(round(z))
            out.append(_dim(gx, Y(n.gl), gx, Y(z), f"{n.gl - z:,.0f}", off=4.0 + 5.0 * (len(seen) - 1)))
            out.append(_text(X(t) + 1.0, Y(z) - 0.8, f"▽床付け GL{z - n.gl:+,.0f}", "ts"))
    if exc:
        out.append(_dim(X(min(exc)), Y(zmax) + 3.0, X(max(exc)), Y(zmax) + 3.0, f"{max(exc) - min(exc):,.0f}", off=-2.0))
    return "".join(out)


def section_page(n: Negiri, cuts: list) -> tuple[str, str, str]:
    out = []
    h = (AREA[3] - AREA[1]) / max(1, len(cuts))
    for k, (lab, a, b) in enumerate(cuts):
        out.append(_section(n, lab, a, b, AREA[0], AREA[1] + k * h, AREA[2] - AREA[0], h, machines=(k == 0)))
    notes = [("断面図の見方", "躯体の輪郭は破線、灰色は砕石・捨てコン（出幅 0.1m）。寸法の基準は設計 GL。掘削面は升目 "
                         f"{n.step:.0f}mm の高さで、法面は勾配どおりの斜めの線"),
             ("山留め", (f"「山留め壁」の {n.ywall.get('name', '')}（{n.ywall.get('kind', '')}）。長さ・根入れ・腹起しの段・"
                       "1次・2次根切りの底は割付の値（数量は ashiba_out/山留め壁.md）。根入れ・部材は山留め計算書で確かめる。"
                       "山留め壁は施工誤差を見て躯体と離す（50〜100 前後が目安）") if n.ywall else
                      "山留め壁は施工誤差を見て躯体と離す（山留めを型枠に兼ねるときのクリアランスは 50〜100 前後が目安）。"
                      "根入れ・親杭の間隔・横矢板は山留め計算書で決め、図に書き込む" if n.yamadome else
                      "山留めなし。深さ 1.5m 以上を垂直に掘るなら山留めか法面（建築基準法施行令136条の3第4項）"),
             ("掘削機とダンプ", "最終段階の掘削機とダンプの位置・動線は、重機の部品（バックホウ・ダンプ）を平面に置いて確かめる。"
                             "道路で積むときは道路使用の許可と誘導員")]
    body, _y = _side(notes, AREA[1] + 2)
    return "根切り 断面図", "―" if not cuts else "図中", "".join(out) + body


# ---------------------------------------------------------------- 3枚目 数量・判定・確認
def table_page(n: Negiri) -> tuple[str, str, str]:
    out = []
    x, y = AREA[0], AREA[1] + 2
    out.append(_text(x, y, "数量（公共建築数量積算基準 令和5年。地山の数量）", "h2"))
    y += 5
    rows = [("根切り", f"{n.volume:,.1f} m³", f"面積 {n.area:,.1f} m²")]
    rows += [(k, f"{v:,.2f} m³", f"面積 {a2:,.1f} m²（出幅 0.1m）") for k, (a2, v) in n.ground.items()]
    rows += [("GL 以下の躯体", f"{n.body:,.1f} m³", "ピット・地下室の空洞を含む"),
             ("埋戻し", f"{n.backfill:,.1f} m³", "根切り−躯体−砕石−捨てコン（本文 p.7）"),
             ("建設発生土", f"{surplus(n):,.1f} m³", "根切り−埋戻し（本文 p.7〜8）"),
             ("10t ダンプ", f"延べ {dumps(n)} 台", f"1台 地山 {DUMP_M3:g}m³（目安）")]
    for a, b, c in rows:
        out.append(_text(x + 2, y, a, "t"))
        out.append(_text(x + 40, y, b, "t"))
        out.append(_text(x + 70, y, c, "ts"))
        y += 4.2
    y += 4
    out.append(_text(x, y, "判定", "h2"))
    y += 5
    for c in n.checks:
        lines = _wrap(f"{c.item}: {c.message}", 120)
        out.append(_text(x + 2, y, c.status, "t", extra=' font-weight="bold"' if c.status != "OK" else ""))
        for ln in lines:
            out.append(_text(x + 14, y, ln, "ts"))
            y += 3.0
        y += 1.2
    # 右の欄: 事前に確かめる項目
    side = [_text(SIDE_X, AREA[1] + 2, "事前に確かめる項目", "h2")]
    yy = AREA[1] + 7
    for group in CHECKS:
        side.append(_text(SIDE_X, yy, group[0], "t", extra=' font-weight="bold"'))
        yy += 4.0
        for item in group[1:]:
            for k, ln in enumerate(_wrap(item, 42)):
                side.append(_text(SIDE_X + 2, yy, ("□ " if k == 0 else "　 ") + ln, "ts"))
                yy += 3.0
        yy += 1.5
    return "根切り 数量・判定・確認", "―", "".join(out) + "".join(side)


# ---------------------------------------------------------------- まとめ
def page_list(n: Negiri, cuts: list | None = None) -> list[tuple[str, str, str]]:
    cuts = cuts or default_cuts(n)
    return [plan_page(n, cuts), section_page(n, cuts), table_page(n)]


def build_html(n: Negiri, project: str = "", cuts: list | None = None) -> str:
    pages = page_list(n, cuts)
    body = "".join(_page(b, name, project, sc, k + 1, len(pages), SERIES) for k, (name, sc, b) in enumerate(pages))
    return ("<!doctype html><html><head><meta charset='utf-8'><title>根切り・山留計画図</title><style>" + CSS
            + "</style></head><body>" + body + "</body></html>")
