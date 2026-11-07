"""建て方検討図（節ごと。利用者の指定 2026-11-07「建て方検討図も作成できるようにして　節毎に」）.

節ごとに A3 の 1 枚。平面に通り芯・工区の境・その節のピース（揚重の判定の色と重量）・下の節・クレーンと作業半径、右の欄に節の範囲と立面の帯、
工区のピース数、クレーンの判定、一番重いピース・一番遠いピース、デッキと親綱の判定を書く。入力は scripts/steel_run.py の 鉄骨建て方_図.json.
"""

from __future__ import annotations

import html
import math

from .form_drawings import CSS, MARGIN, PAGE_H, PAGE_W, SCALES, TB_H, _page
from .steel_erection import label_point

ESC = html.escape
SERIES = "建て方"
SUBSET = "建て方検討図"
AREA = (MARGIN + 6.0, MARGIN + 14.0, PAGE_W - MARGIN - 118.0, PAGE_H - MARGIN - 8.0)
SIDE_X = PAGE_W - MARGIN - 112.0
SIDE_END = PAGE_H - MARGIN - TB_H - 3.0
COLORS = {"揚重可能": "#2e9e4f", "重すぎ": "#e8862a", "遠すぎ": "#8a8a8a", "高すぎ": "#8a3fb0", "判定不可": "#e3c22b", "": "#ffffff"}


def _t(x, y, s, cls="t", anchor="start") -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}" text-anchor="{anchor}">{ESC(str(s))}</text>'


def _line(a, b, width=0.15, color="#000", dash="") -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke="{color}" stroke-width="{width}"{d}/>'


def _rect(cx, cy, w, h, fill, stroke="#000", width=0.2) -> str:
    return f'<rect x="{cx - w / 2:.2f}" y="{cy - h / 2:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'


def _scale_for(w: float, h: float, bw: float, bh: float) -> int:
    for s in SCALES:
        if w / s <= bw and h / s <= bh:
            return s
    return int(math.ceil(max(w / bw, h / bh) / 100.0)) * 100


def beam_mid(b: dict) -> tuple:
    a = math.radians(b["ang"])
    return b["x"] + b["length"] / 2.0 * math.cos(a), b["y"] + b["length"] / 2.0 * math.sin(a)


def node_list(d: dict) -> list:
    return sorted({c["node"] for c in d["columns"]} | {b["node"] for b in d["beams"]})


def worst(items: list, key) -> dict | None:
    """判定のあるピースのうち key が最大のもの."""
    xs = [i for i in items if i.get("lift")]
    return max(xs, key=key) if xs else None


def piece_label(p: dict) -> str:
    return p.get("grid") or p.get("mark") or ""


def arc_lines(q: tuple, r: float) -> str:
    """作業半径の円を短い線に分け、図の範囲の中だけ描く（レイアウトの変換は切り抜きの円を枠の形にした）."""
    def inside(p):
        return AREA[0] <= p[0] <= AREA[2] and AREA[1] <= p[1] <= AREA[3]

    out = []
    n = max(60, int(r))
    for k in range(0, n, 2):                                   # 1 本おきで破線
        a, b = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        p0 = (q[0] + r * math.cos(a), q[1] + r * math.sin(a))
        p1 = (q[0] + r * math.cos(b), q[1] + r * math.sin(b))
        if inside(p0) and inside(p1):
            out.append(_line(p0, p1, 0.2, "#0050b4"))
    return "".join(out)


def plan_svg(d: dict, node: int) -> tuple:
    """節 node の平面 → (SVG, 縮尺)."""
    cols = d["columns"]
    now = [c for c in cols if c["node"] == node]
    beams = [b for b in d["beams"] if b["node"] == node]
    crane = d.get("crane")
    pts = [(c["x"], c["y"]) for c in cols] + [(b["x"], b["y"]) for b in d["beams"]]
    if crane:
        pts.append((crane["x"], crane["y"]))
    x0, x1 = min(p[0] for p in pts) - 2000.0, max(p[0] for p in pts) + 2000.0
    y0, y1 = min(p[1] for p in pts) - 2000.0, max(p[1] for p in pts) + 2000.0
    bw, bh = AREA[2] - AREA[0] - 16.0, AREA[3] - AREA[1] - 16.0
    sc = _scale_for(x1 - x0, y1 - y0, bw, bh)
    ox = AREA[0] + 8.0 + (bw - (x1 - x0) / sc) / 2.0
    oy = AREA[1] + 8.0 + (bh - (y1 - y0) / sc) / 2.0
    P = lambda x, y: (ox + (x - x0) / sc, oy + (y1 - y) / sc)
    out = []
    # 通り芯
    for name, x in d.get("lines_x", []):
        out.append(_line(P(x, y0), P(x, y1), 0.12, "#555", "3 1 0.6 1"))
        out.append(_t(P(x, y1)[0], P(x, y1)[1] - 1.5, name, "t", "middle"))
    for name, y in d.get("lines_y", []):
        out.append(_line(P(x0, y), P(x1, y), 0.12, "#555", "3 1 0.6 1"))
        out.append(_t(P(x0, y)[0] - 1.5, P(x0, y)[1] + 1.0, name, "t", "end"))
    # 工区の境
    for x in d.get("xs", []):
        out.append(_line(P(x + 1.0, y0), P(x + 1.0, y1), 0.45, "#c0392b", "5 1.5"))
    for y in d.get("ys", []):
        out.append(_line(P(x0, y + 1.0), P(x1, y + 1.0), 0.45, "#c0392b", "5 1.5"))
    # 工区のゾーン
    for z in d.get("zones", []):
        for ring in [z["outline"]] + z.get("holes", []):
            ring = [P(*q) for q in ring]
            for a, b in zip(ring, ring[1:] + ring[:1]):
                out.append(_line(a, b, 0.45, "#c0392b", "5 1.5"))
        out.append(_t(*P(*label_point(z["outline"], z.get("holes", []))), z["name"], "h2", "middle"))
    # 下の節（灰）
    for c in cols:
        if c["node"] < node:
            out.append(_rect(*P(c["x"], c["y"]), c["w"] / sc, c["d"] / sc, "#d5d5d5", "#888", 0.1))
    for b in d["beams"]:
        if b["node"] < node:
            a = math.radians(b["ang"])
            out.append(_line(P(b["x"], b["y"]), P(b["x"] + b["length"] * math.cos(a), b["y"] + b["length"] * math.sin(a)), 0.2, "#bbb"))
    # この節の梁
    for b in beams:
        a = math.radians(b["ang"])
        color = COLORS.get((b.get("lift") or {}).get("res", ""), "#444") if b.get("lift") else "#444"
        out.append(_line(P(b["x"], b["y"]), P(b["x"] + b["length"] * math.cos(a), b["y"] + b["length"] * math.sin(a)), 0.5, color))
    # この節の柱
    for c in now:
        fill = COLORS.get((c.get("lift") or {}).get("res", ""), "#fff")
        q = P(c["x"], c["y"])
        out.append(_rect(q[0], q[1], max(2.2, c["w"] / sc), max(2.2, c["d"] / sc), fill))
        out.append(_t(q[0] + 2.0, q[1] - 1.6, "-" if c.get("weight") is None else f"{c['weight']:.2f}t"))
    # クレーンと作業半径
    if crane:
        q = P(crane["x"], crane["y"])
        out.append(_line((q[0] - 3, q[1]), (q[0] + 3, q[1]), 0.3, "#0050b4"))
        out.append(_line(q, (q[0], q[1] - 3), 0.3, "#0050b4"))
        out.append(_line(q, (q[0], q[1] + 3), 0.3, "#0050b4"))
        out.append(_t(q[0] + 3.5, q[1] + 1.0, crane["name"], "t"))
        far = worst(now + beams, lambda p: p["lift"]["radius"])
        if far:
            r = far["lift"]["radius"] / sc
            out.append(arc_lines(q, r))
            out.append(_t(q[0] + 3.5, q[1] + 4.5, f"作業半径 {far['lift']['radius'] / 1000:.1f}m（一番遠いピース）", "t"))
    return "".join(out), sc


def elevation_svg(d: dict, node: int, x: float, y: float, w: float, h: float) -> str:
    """右の欄の立面の帯: 節の範囲を塗る."""
    cols = d["columns"]
    z0, z1 = min(c["z0"] for c in cols), max(c["z1"] for c in cols)
    k = h / max(1.0, z1 - z0)
    Y = lambda z: y + h - (z - z0) * k
    out = []
    for c in sorted({(c["node"], c["z0"], c["z1"]) for c in cols}):
        n, a, b = c
        fill = "#f4c27a" if n == node else "#e6e6e6" if n < node else "#ffffff"
        out.append(f'<rect x="{x:.2f}" y="{Y(b):.2f}" width="{w:.2f}" height="{(b - a) * k:.2f}" fill="{fill}" stroke="#000" stroke-width="0.15"/>')
        out.append(_t(x + w + 1.5, Y(b) + 2.8, f"{n}節 上端 {b / 1000:.2f}m"))
    return "".join(out)


def side_svg(d: dict, node: int) -> str:
    now = [c for c in d["columns"] if c["node"] == node]
    beams = [b for b in d["beams"] if b["node"] == node]
    steps = [s for s in d["steps"] if s["node"] == node]
    out = []
    y = AREA[1]
    z0, z1 = min(c["z0"] for c in now), max(c["z1"] for c in now)
    out.append(_t(SIDE_X, y, f"{node}節 GL{z0 / 1000:+.2f}〜{z1 / 1000:+.2f}m", "h2"))
    out.append(elevation_svg(d, node, SIDE_X + 2, y + 3, 10.0, 34.0))
    y += 42.0
    out.append(_t(SIDE_X, y, "工区のピース数", "h2"))
    y += 5.0
    out.append(_t(SIDE_X + 2, y, "順　工区　柱　梁　計　重量"))
    y += 3.8
    for s in steps:
        out.append(_t(SIDE_X + 2, y, f"{s['no']}　{s.get('zone_name') or str(s['zone']) + '工区'}　{s['columns']}　{s['beams']}　{s['columns'] + s['beams']}　{s['weight']:.2f}t"))
        y += 3.8
    total = sum(p.get("weight") or 0.0 for p in now + beams)
    out.append(_t(SIDE_X + 2, y, f"計 柱 {len(now)}・梁 {len(beams)}・{len(now) + len(beams)}ピース・{total:.2f}t"))
    y += 6.0
    crane = d.get("crane")
    out.append(_t(SIDE_X, y, "揚重の判定", "h2"))
    y += 5.0
    if crane:
        out.append(_t(SIDE_X + 2, y, crane["name"]))
        y += 3.8
        cnt: dict = {}
        for p in now + beams:
            k = (p.get("lift") or {}).get("res", "")
            cnt[k] = cnt.get(k, 0) + 1
        for k in ("揚重可能", "重すぎ", "遠すぎ", "高すぎ", "判定不可"):
            if cnt.get(k):
                out.append(f'<rect x="{SIDE_X + 2:.2f}" y="{y - 2.2:.2f}" width="4" height="2.4" fill="{COLORS[k]}" stroke="#000" stroke-width="0.1"/>')
                out.append(_t(SIDE_X + 8, y, f"{k} {cnt[k]}"))
                y += 3.8
        for head, key in (("一番重い", lambda p: p.get("weight") or 0.0), ("一番遠い", lambda p: p["lift"]["radius"])):
            p = worst(now + beams, key)
            if p:
                L = p["lift"]
                out.append(_t(SIDE_X + 2, y, f"{head}: {piece_label(p)} {(p.get('weight') or 0):.2f}t・R {L['radius'] / 1000:.1f}m・定格 {L['rated']:.2f}t・{L['res']}"))
                y += 3.8
    else:
        out.append(_t(SIDE_X + 2, y, "クレーンを選んで作ると判定が入ります"))
        y += 3.8
    y += 3.0
    rows = [r for r in d.get("deck", []) if r["node"] == node and r["current"]]
    if rows and y < SIDE_END - 12:
        out.append(_t(SIDE_X, y, "デッキと親綱（H の下限〜上限）", "h2"))
        y += 5.0
        seen = set()
        for r in rows:
            k = (r["top"], r["h_low"], r["h_high"], r["rope"])
            if k in seen or y > SIDE_END:
                continue
            seen.add(k)
            out.append(_t(SIDE_X + 2, y, f"{r['top'] / 1000:.2f}m　H {r['h_low'] / 1000:.2f}〜{r['h_high'] / 1000:.2f}m　親綱 {r['rope']}"))
            y += 3.8
    return "".join(out)


def page_list(d: dict) -> list:
    pages = []
    for n in node_list(d):
        svg, sc = plan_svg(d, n)
        pages.append((f"建て方検討図 {n}節", f"1/{sc}", svg + side_svg(d, n)))
    return pages


def build_html(d: dict, project: str = "") -> str:
    pages = page_list(d)
    body = "".join(_page(b, name, project, sc, k + 1, len(pages), SERIES) for k, (name, sc, b) in enumerate(pages))
    return "<!doctype html><html><head><meta charset='utf-8'><title>建て方検討図</title><style>" + CSS + "</style></head><body>" + body + "</body></html>"
