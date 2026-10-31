"""型枠支保工計画図（利用者の指定 2026-10-31: 型枠しほこう計画図作成できる？ → 伏図・断面図と詳細図・構造計算書・計画届の要否と様式）.

scripts/form_run.py が書く ashiba_out/型枠_計画.json から、A3 横の図面（HTML。Chrome で PDF にする）と計算書（xlsx）を作る.
- 1枚目 支保工伏図: スラブの外形・梁（破線）・壁と柱（塗り）、大引（一点鎖線）、パイプサポート（○。梁下は□）、敷き桟木、
  支柱の間隔の寸法、根太の向き、凡例と注記
- 2枚目 断面図: a－a（大引の向き）・b－b（大引に直角）。床・スラブ・梁、せき板・根太・大引・パイプサポート・敷き桟木・根がらみ・
  水平つなぎ、割付ピッチと高さの寸法、部材の引出し（手引の a－a 断面図の例にならう。利用者の指定 2026-10-31: 断面も）
- 3枚目 詳細図: スラブ・梁下の断面（利用者の詳細図の組み方）、柱の詳細（コラムクランプ／外端太とフォームタイ）、
  壁の断面（セパ・外端太）。値は計画の値
- 3枚目 構造計算書: 荷重・側圧、部材の曲げとたわみ、支柱の軸力、水平荷重（安衛則 240条）
- 部材等明細書: 計画届作成の手引（建災防東京支部 第6版）p.147 の例の欄（構造材料・材質と寸法・使用部位、設置箇所と高さ・
  設置期間・設計荷重と支柱1本当り・許容支持力、各部の構造・組立概要と詳細図の有無）に計画の値を入れる
- 4枚目 計画届: 支柱の高さ 3.5m 以上は届出（安衛則 88条・別表第7）。要るときは様式第20号の下書きと添付の一覧
"""

from __future__ import annotations

import datetime as _dt
import html
import math
from pathlib import Path

PAGE_W, PAGE_H = 420.0, 297.0          # A3 横（mm）
MARGIN = 10.0
TB_W, TB_H = 140.0, 34.0               # 表題欄
SCALES = (20, 30, 50, 100, 150, 200, 300, 500)
NOTICE_H_MM = 3500.0                   # 型枠支保工の計画届（支柱の高さ 3.5m 以上。安衛則 88条・別表第7）
H_LOAD_RATIO = 0.05                    # 水平荷重（設計荷重の 5%。パイプサポート等。安衛則 240条）

NOTE_CHARS = 44                        # 右の欄の注記の1行の字数（幅 100mm・2.1mm の文字）

ESC = html.escape


# ---------------------------------------------------------------- 共通
def _rot(p, ang_deg, o=(0.0, 0.0)):
    a = math.radians(ang_deg)
    return (o[0] + p[0] * math.cos(a) - p[1] * math.sin(a), o[1] + p[0] * math.sin(a) + p[1] * math.cos(a))


def _title_block(name: str, project: str, scale: str, no: int, total: int) -> str:
    x0, y0 = PAGE_W - MARGIN - TB_W, PAGE_H - MARGIN - TB_H
    today = _dt.date.today().strftime("%Y.%m.%d")
    rows = [("工事名", project or "（工事名）"), ("図名", name), ("縮尺", scale), ("日付", today),
            ("図番", f"型枠支保工 {no}/{total}")]
    out = [f'<rect x="{x0}" y="{y0}" width="{TB_W}" height="{TB_H}" class="frame"/>']
    h = TB_H / len(rows)
    for k, (a, b) in enumerate(rows):
        y = y0 + h * k
        if k:
            out.append(f'<line x1="{x0}" y1="{y}" x2="{x0 + TB_W}" y2="{y}" class="thin"/>')
        out.append(f'<text x="{x0 + 2}" y="{y + h * 0.7}" class="tb">{ESC(a)}</text>')
        out.append(f'<text x="{x0 + 22}" y="{y + h * 0.7}" class="tbv">{ESC(b)}</text>')
    out.append(f'<line x1="{x0 + 20}" y1="{y0}" x2="{x0 + 20}" y2="{y0 + TB_H}" class="thin"/>')
    return "".join(out)


def _page(body: str, name: str, project: str, scale: str, no: int, total: int) -> str:
    return (f'<section class="page"><svg viewBox="0 0 {PAGE_W} {PAGE_H}" width="{PAGE_W}mm" height="{PAGE_H}mm">'
            f'<rect x="{MARGIN / 2}" y="{MARGIN / 2}" width="{PAGE_W - MARGIN}" height="{PAGE_H - MARGIN}" class="frame"/>'
            f'<text x="{MARGIN}" y="{MARGIN + 6}" class="h1">{ESC(name)}</text>'
            + body + _title_block(name, project, scale, no, total) + "</svg></section>")


CSS = """
@page { size: A3 landscape; margin: 0; }
body { margin: 0; font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif; }
.page { width: 420mm; height: 297mm; page-break-after: always; overflow: hidden; }
svg text { font-family: "Hiragino Sans", sans-serif; }
.frame { fill: none; stroke: #000; stroke-width: 0.5; }
.thin { stroke: #000; stroke-width: 0.15; fill: none; }
.h1 { font-size: 6px; font-weight: bold; }
.h2 { font-size: 4px; font-weight: bold; }
.t { font-size: 2.6px; }
.ts { font-size: 2.1px; }
.tb { font-size: 2.8px; }
.tbv { font-size: 3.2px; }
.slab { fill: none; stroke: #000; stroke-width: 0.35; }
.hole { fill: #fff; stroke: #000; stroke-width: 0.2; stroke-dasharray: 1.5 0.8; }
.struct { fill: #bbb; stroke: #333; stroke-width: 0.2; }
.beam { fill: none; stroke: #444; stroke-width: 0.25; stroke-dasharray: 2 1; }
.obiki { stroke: #8a5a2b; stroke-width: 0.35; stroke-dasharray: 4 1 0.6 1; fill: none; }
.sill { stroke: #c49a6c; stroke-width: 0.6; fill: none; opacity: 0.8; }
.ps { fill: #fff; stroke: #333; stroke-width: 0.25; }
.psb { fill: #fff; stroke: #333; stroke-width: 0.25; }
.dim { stroke: #0050b4; stroke-width: 0.15; fill: none; }
.dimt { font-size: 2.1px; fill: #0050b4; }
.ply { fill: #e6c48a; stroke: #8a5a2b; stroke-width: 0.15; }
.wood { fill: #d9a56b; stroke: #6b4320; stroke-width: 0.15; }
.steel { fill: #9aa0a8; stroke: #333; stroke-width: 0.15; }
.conc { fill: #e8e8e8; stroke: #555; stroke-width: 0.2; }
.tie { stroke: #222; stroke-width: 0.25; }
.lead { stroke: #000; stroke-width: 0.12; fill: none; }
.neda { stroke: #7a7f87; stroke-width: 0.12; }
.obk { fill: #d9a56b; stroke: #6b4320; stroke-width: 0.1; }
.cut { stroke: #000; stroke-width: 0.25; stroke-dasharray: 4 1 0.6 1; fill: none; }
.mark { fill: #fff; stroke: #000; stroke-width: 0.25; }
.brace { stroke: #7b2d8b; stroke-width: 0.3; stroke-dasharray: 1.2 0.6; fill: none; }
.bracel { stroke: #555; stroke-width: 0.45; fill: none; }
.grid { stroke: #555; stroke-width: 0.15; stroke-dasharray: 4 1 0.6 1; fill: none; }
table { border-collapse: collapse; }
"""


def _wrap(text: str, n: int) -> list[str]:
    """n 字ごとに折り返す（全角・半角を区別しない目安）."""
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def _dim(x0, y0, x1, y1, text, off=4.0) -> str:
    """2点の寸法（紙の mm）. 線の左へ off ずらす."""
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = -(y1 - y0) / L * off, (x1 - x0) / L * off
    a, b = (x0 + nx, y0 + ny), (x1 + nx, y1 + ny)
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    if ang > 90 or ang < -90:
        ang += 180
    mx, my = (a[0] + b[0]) / 2 + nx * 0.25, (a[1] + b[1]) / 2 + ny * 0.25
    return (f'<line x1="{x0}" y1="{y0}" x2="{a[0]}" y2="{a[1]}" class="dim"/>'
            f'<line x1="{x1}" y1="{y1}" x2="{b[0]}" y2="{b[1]}" class="dim"/>'
            f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" class="dim"/>'
            f'<circle cx="{a[0]}" cy="{a[1]}" r="0.3" fill="#0050b4"/><circle cx="{b[0]}" cy="{b[1]}" r="0.3" fill="#0050b4"/>'
            f'<text x="{mx}" y="{my}" class="dimt" text-anchor="middle" transform="rotate({ang} {mx} {my})">{ESC(text)}</text>')


# ---------------------------------------------------------------- 1枚目 伏図
def _world(plan: dict) -> dict:
    """伏図に描くものを世界座標（mm）で."""
    out = {"slabs": [], "holes": [], "posts": [], "bposts": [], "obiki": [], "sills": [], "walls": [], "cols": [],
           "beams": [], "labels": []}
    for s in plan.get("slabs", []):
        o, a = s["origin"], s["ang"]
        W = lambda p: _rot(p, a, o)
        out["slabs"].append([W(p) for p in s["outer"]])
        out["holes"] += [[W(p) for p in h] for h in s["holes"]]
        out["posts"] += [W(p) for p in s["posts"]]
        out["obiki"] += [(W((u0, v)), W((u1, v))) for u0, u1, v in s["obiki"]]
        out["sills"] += [(W((u0, v)), W((u1, v))) for u0, u1, v in s["sills"]]
        out["labels"].append((W(s["outer"][0]), s))
    for b in plan.get("beams", []):
        u = b["u"]
        n = (-u[1], u[0])
        hw = b["width"] / 2.0
        a, c = b["ca"], b["cb"]
        out["beams"].append([(a[0] + n[0] * hw, a[1] + n[1] * hw), (c[0] + n[0] * hw, c[1] + n[1] * hw),
                             (c[0] - n[0] * hw, c[1] - n[1] * hw), (a[0] - n[0] * hw, a[1] - n[1] * hw)])
        for x in b["uke_x"]:
            for sg in (-1, 1):
                out["bposts"].append((a[0] + u[0] * x + n[0] * sg * b["psY"], a[1] + u[1] * x + n[1] * sg * b["psY"]))
    for w in plan.get("walls", []):
        u, n = w["u"], w["n"]
        a, c = w["ca"], w["cb"]
        out["walls"].append([(a[0] + n[0] * w["lo"], a[1] + n[1] * w["lo"]), (c[0] + n[0] * w["lo"], c[1] + n[1] * w["lo"]),
                             (c[0] + n[0] * w["hi"], c[1] + n[1] * w["hi"]), (a[0] + n[0] * w["hi"], a[1] + n[1] * w["hi"])])
    for col in plan.get("columns", []):
        hx, hy = col["width"] / 2.0, col["depth"] / 2.0
        out["cols"].append([_rot(p, col["ang"], col["c"]) for p in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])
    return out


def _fit(points, box_w, box_h):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    w, h = max(xs) - min(xs) or 1.0, max(ys) - min(ys) or 1.0
    for s in SCALES:
        if w / s <= box_w and h / s <= box_h:
            return s, (min(xs), min(ys), max(xs), max(ys))
    return SCALES[-1], (min(xs), min(ys), max(xs), max(ys))


GRID_MERGE_MM = 150.0                  # これより近い芯は同じ通り


def grid_lines(plan: dict) -> list[dict]:
    """通り芯（利用者の指定 2026-10-31: 通り芯も足して）: Archicad の通り芯は Tapir で読めないので、柱の芯と、まっすぐな壁
    （縦・横）の芯から作る. [{"name": "X1", "axis": "x", "pos": mm}]（X は左から、Y は下から）."""
    xs, ys = [], []
    for c in plan.get("columns", []):
        xs.append(float(c["c"][0]))
        ys.append(float(c["c"][1]))
    for w in plan.get("walls", []):
        u, n = w["u"], w["n"]
        off = (w["lo"] + w["hi"]) / 2.0
        if abs(u[0]) > 0.999:                      # 横の壁 → Y の通り
            ys.append(float(w["ca"][1] + n[1] * off))
        elif abs(u[1]) > 0.999:                    # 縦の壁 → X の通り
            xs.append(float(w["ca"][0] + n[0] * off))

    def merge(vals):
        out = []
        for v in sorted(vals):
            if out and v - out[-1][-1] <= GRID_MERGE_MM:
                out[-1].append(v)
            else:
                out.append([v])
        return [sum(g) / len(g) for g in out]

    return ([{"name": f"X{k}", "axis": "x", "pos": v} for k, v in enumerate(merge(xs), 1)]
            + [{"name": f"Y{k}", "axis": "y", "pos": v} for k, v in enumerate(merge(ys), 1)])


def _bubble(x: float, y: float, name: str) -> str:
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.8" class="mark"/>'
            f'<text x="{x:.2f}" y="{y + 0.9:.2f}" class="ts" text-anchor="middle">{ESC(name)}</text>')


def _local(s: dict):
    """スラブの局所座標（u＝大引の向き・v＝大引どうしの向き）と世界座標の行き来 (W, L)."""
    o, a = s["origin"], s["ang"]
    W = lambda p: _rot(p, a, o)
    L = lambda p: _rot((p[0] - o[0], p[1] - o[1]), -a)
    return W, L


def section_cuts(s: dict) -> tuple[float, float]:
    """断面の切る位置 (a－a の v, b－b の u): 支柱の列・行のまん中（支柱・大引・敷き桟木が切り口に乗る）."""
    vs = sorted({round(p[1], 1) for p in s["posts"]}) or [0.0]
    us = sorted({round(p[0], 1) for p in s["posts"]}) or [0.0]
    return vs[len(vs) // 2], us[len(us) // 2]


def _cut_intervals(poly, h: int, cut: float) -> list[tuple[float, float]]:
    """局所座標の多角形を、座標 1−h が cut の線で切った中の区間（座標 h）."""
    q = 1 - h
    ts = []
    n = len(poly)
    for k in range(n):
        p0, p1 = poly[k], poly[(k + 1) % n]
        if (p0[q] > cut) != (p1[q] > cut):
            f = (cut - p0[q]) / (p1[q] - p0[q])
            ts.append(p0[h] + (p1[h] - p0[h]) * f)
    ts.sort()
    return [(ts[i], ts[i + 1]) for i in range(0, len(ts) - 1, 2)]


def _minus(ivs, cuts) -> list[tuple[float, float]]:
    out = list(ivs)
    for c0, c1 in cuts:
        nxt = []
        for a, b in out:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if c0 > a:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        out = nxt
    return [(a, b) for a, b in out if b - a > 1.0]


def _chain(pts_paper: list, texts: list[str], off: float) -> str:
    """直線に並んだ点（紙の座標）の連続寸法. 方向の左へ off ずらす（_dim と同じ）."""
    return "".join(_dim(a[0], a[1], b[0], b[1], t_, off=off) for a, b, t_ in zip(pts_paper, pts_paper[1:], texts))


def _pitch_texts(vals: list[float]) -> list[str]:
    return [f"{b - a:.0f}" for a, b in zip(vals, vals[1:])]


def plan_page(plan: dict) -> tuple[str, str, str]:
    """(図名, 縮尺, 本文の SVG). 計画届作成の手引の型枠支保工計画図（平面図）の例にならい、根太・大引・支柱・敷き桟木、梁下の大引と
    支柱、割付ピッチの連続寸法（スラブ下・梁下）、部材の引出し、断面の切る位置（a－a・b－b）を描く（利用者の指定 2026-10-31:
    平面の詳細度あげて）."""
    wd = _world(plan)
    # 図の範囲はスラブ（と梁・梁下の支柱）のまわり 1.5m。外は切る（支保工の伏図）
    core = [p for g in ("slabs", "beams") for poly in wd[g] for p in poly] + wd["posts"] + wd["bposts"]
    pts = core or [p for g in ("walls", "cols") for poly in wd[g] for p in poly]
    if pts:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        pts = [(min(xs) - 1500.0, min(ys) - 1500.0), (max(xs) + 1500.0, max(ys) + 1500.0)]
    if not pts:
        return "型枠支保工 伏図", "-", '<text x="20" y="40" class="t">スラブの型枠がありません</text>'
    box_w, box_h = PAGE_W - 2 * MARGIN - 110.0, PAGE_H - 2 * MARGIN - 30.0
    lab_w = 52.0                                   # 右の引出しの欄
    scale, (x0, y0, x1, y1) = _fit(pts, box_w - 30.0 - lab_w, box_h - 30.0)
    ox = MARGIN + 20.0 + (box_w - 30.0 - lab_w - (x1 - x0) / scale) / 2.0
    oy = MARGIN + 20.0 + (box_h - 30.0 - (y1 - y0) / scale) / 2.0
    P = lambda p: (ox + (p[0] - x0) / scale, oy + (y1 - p[1]) / scale)        # 世界の y は上向き
    poly = lambda pp, cls: '<polygon points="' + " ".join(f"{P(p)[0]:.2f},{P(p)[1]:.2f}" for p in pp) + f'" class="{cls}"/>'
    line = lambda a, b, cls: f'<line x1="{P(a)[0]:.2f}" y1="{P(a)[1]:.2f}" x2="{P(b)[0]:.2f}" y2="{P(b)[1]:.2f}" class="{cls}"/>'

    def band(W, a, b, half, cls):
        """局所座標の線分 a→b を幅 2×half の帯に（紙で細すぎれば線）."""
        if 2 * half / scale < 0.5:
            return line(W(a), W(b), cls if cls != "obk" else "obiki")
        dx, dy = b[0] - a[0], b[1] - a[1]
        Ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / Ln * half, dx / Ln * half
        return poly([W((a[0] + nx, a[1] + ny)), W((b[0] + nx, b[1] + ny)), W((b[0] - nx, b[1] - ny)), W((a[0] - nx, a[1] - ny))], cls)

    out = [f'<clipPath id="pv"><rect x="{MARGIN + 5}" y="{MARGIN + 10}" width="{box_w + 5 - lab_w}" height="{box_h + 15}"/></clipPath>'
           '<g clip-path="url(#pv)">']
    out += [poly(s, "slab") for s in wd["slabs"]]
    out += [poly(h, "hole") for h in wd["holes"]]
    out += [poly(b, "beam") for b in wd["beams"]]
    out += [poly(w, "struct") for w in wd["walls"]]
    out += [poly(c, "struct") for c in wd["cols"]]
    labels = []                                    # (紙の点, 文字) 右の欄へ引き出す
    r = max(0.6, 80.0 / scale)
    for s in plan.get("slabs", []):
        W, _L = _local(s)
        # 敷き桟木（大引の下・支柱の列ごと）・根太（大引に直角 @300）・大引（帯）
        for u0, u1, v in s["sills"]:
            out.append(line(W((u0, v)), W((u1, v)), "sill"))
        for v0, v1, u in s.get("neda", []):
            out.append(line(W((u, v0)), W((u, v1)), "neda"))
        for u0, u1, v in s["obiki"]:
            out.append(band(W, (u0, v), (u1, v), 45.0, "obk"))
        # 大筋かい（支柱の列の鉛直面。平面では列に沿った破線）
        for b_ in s.get("braces", []):
            out.append(line(W((b_[0], b_[1])), W((b_[3], b_[4])), "brace"))
        if s.get("braces"):
            b_ = s["braces"][-1]
            labels.append((P(W(((b_[0] + b_[3]) / 2, (b_[1] + b_[4]) / 2))), "大筋かい：単管 φ48.6（自在クランプ）"))
        for p in s["posts"]:
            x, y = P(W(p))
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="ps"/>'
                       f'<line x1="{x - r:.2f}" y1="{y:.2f}" x2="{x + r:.2f}" y2="{y:.2f}" class="thin"/>'
                       f'<line x1="{x:.2f}" y1="{y - r:.2f}" x2="{x:.2f}" y2="{y + r:.2f}" class="thin"/>')
        if s["posts"]:
            umax = max(p[0] for p in s["posts"])
            vtop = max(p[1] for p in s["posts"])
            ob = max(s["obiki"], key=lambda o_: (o_[2], o_[1])) if s["obiki"] else None
            if ob:
                labels.append((P(W((ob[1] - 250.0, ob[2]))), "大引：杉 90×90"))
            ne = [n_ for n_ in s.get("neda", []) if n_[0] <= vtop - 450.0 <= n_[1]]
            if ne:
                n_ = max(ne, key=lambda n2: n2[2])
                labels.append((P(W((n_[2], vtop - 450.0))), "根太：角パイプ □50×50×2.3 @300"))
            labels.append((P(W((umax, vtop))), f"パイプサポート（{s['name']} 下・長さ {s['post_h']:.0f}）"))
            sl = max(s["sills"], key=lambda o_: (o_[2], o_[1])) if s["sills"] else None
            if sl:
                labels.append((P(W((sl[1] - 40.0, sl[2]))), "敷き桟木 45×60（寝かせ）"))
            labels.append((P(W((umax - 0.5 * s["su"], vtop - 0.5 * s["sv"]))), "せき板：合板 12mm"))
    for b in plan.get("beams", []):
        u = b["u"]
        n = (-u[1], u[0])
        a = b["ca"]
        Wb = lambda p, a=a, u=u, n=n: (a[0] + u[0] * p[0] + n[0] * p[1], a[1] + u[1] * p[0] + n[1] * p[1])
        half = b["psY"] + 120.0
        for x in b["uke_x"]:
            out.append(band(Wb, (x, -half), (x, half), 45.0, "obk"))
            for sg in (-1, 1):
                px, py = P(Wb((x, sg * b["psY"])))
                out.append(f'<rect x="{px - r:.2f}" y="{py - r:.2f}" width="{2 * r:.2f}" height="{2 * r:.2f}" class="psb"/>')
        if b["uke_x"]:
            x = b["uke_x"][-1]
            labels.append((P(Wb((x, b["psY"]))), f"梁下パイプサポート（{b['name']}・長さ {b['post_h']:.0f}）"))
            labels.append((P(Wb((x, half - 40.0))), "梁下大引：杉 90×90"))
    # 切る位置（a－a・b－b）
    for s in plan.get("slabs", [])[:1]:
        W, _L = _local(s)
        vc, uc = section_cuts(s)
        us = [p[0] for p in s["outer"]]
        vs = [p[1] for p in s["outer"]]
        ext_ = 22.0 * scale                        # 記号は連続寸法（2段）の外に
        for (pa, pb), name in ((((min(us) - ext_, vc), (max(us) + ext_, vc)), "a"),
                               (((uc, min(vs) - ext_), (uc, max(vs) + ext_)), "b")):
            out.append(line(W(pa), W(pb), "cut"))
            for q_ in (pa, pb):
                cx, cy = P(W(q_))
                out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="2.4" class="mark"/>'
                           f'<text x="{cx:.2f}" y="{cy + 1.0:.2f}" class="t" text-anchor="middle">{name}</text>')
    # 割付ピッチの連続寸法: スラブ下（大引の向きの支柱と、大引どうし）、梁下（大引の位置）
    for s in plan.get("slabs", []):
        W, L = _local(s)
        if not s["posts"]:
            continue
        us = [p[0] for p in s["outer"]]
        vs = [p[1] for p in s["outer"]]
        umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
        pu = [umin] + sorted({round(p[0], 1) for p in s["posts"]}) + [umax]
        pv = [vmin] + sorted({round(o_[2], 1) for o_ in s["obiki"]}) + [vmax]
        out.append(_chain([P(W((x, vmin))) for x in pu], _pitch_texts(pu), 6.0))
        out.append(_chain([P(W((umin, vmin))), P(W((umax, vmin)))], [f"{umax - umin:.0f}"], 13.0))
        out.append(_chain([P(W((umin, y))) for y in pv], _pitch_texts(pv), -6.0))
        out.append(_chain([P(W((umin, vmin))), P(W((umin, vmax)))], [f"{vmax - vmin:.0f}"], -13.0))
        tx, ty = P(W((umin, vmin)))
        out.append(f'<text x="{tx:.1f}" y="{ty + 18:.1f}" class="ts">スラブ（{ESC(s["name"])}）下 サポート割付ピッチ・全長</text>')
        tx, ty = P(W((umin, vmax)))
        out.append(f'<text x="{tx - 16:.1f}" y="{ty - 3:.1f}" class="ts">大引割付ピッチ</text>')
        # 梁下: 梁の向きに大引（受け）の位置。スラブの右（梁が v の向き）か上（u の向き）の外へ
        k_b = 0
        for b in plan.get("beams", []):
            if not b["uke_x"]:
                continue
            u = b["u"]
            ca = L(b["ca"])
            d = L((b["ca"][0] + u[0], b["ca"][1] + u[1]))
            d = (d[0] - ca[0], d[1] - ca[1])
            along_v = abs(d[1]) > abs(d[0])
            pos = [L((b["ca"][0] + u[0] * x, b["ca"][1] + u[1] * x)) for x in b["uke_x"]]
            ends = [L((b["ca"][0] + u[0] * x, b["ca"][1] + u[1] * x)) for x in b.get("ext", [0.0, 0.0])]
            if along_v:
                vals = sorted([p_[1] for p_ in pos] + [e_[1] for e_ in ends])
                out.append(_chain([P(W((umax, y))) for y in vals], _pitch_texts(vals), 6.0 + 9.0 * k_b))
                # 見出しは寸法の外に縦書きで（右の引出しと重ねない）
                (ax_, ay_), (bx_, by_) = P(W((umax, min(vals)))), P(W((umax, max(vals))))
                tx, ty = (ax_ + bx_) / 2.0 + 11.0 + 9.0 * k_b, (ay_ + by_) / 2.0
                out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" class="ts" text-anchor="middle" transform="rotate(90 {tx:.1f} {ty:.1f})">'
                           f'梁（{ESC(b["name"])}）下 サポート・大引割付ピッチ</text>')
            else:
                vals = sorted([p_[0] for p_ in pos] + [e_[0] for e_ in ends])
                out.append(_chain([P(W((x, vmax))) for x in vals], _pitch_texts(vals), -6.0 - 9.0 * k_b))
                tx, ty = P(W((min(vals), vmax)))
                out.append(f'<text x="{tx:.1f}" y="{ty - 10 - 9 * k_b:.1f}" class="ts">梁（{ESC(b["name"])}）下 サポート・大引割付ピッチ</text>')
            k_b += 1
        # スラブの名前と厚さ（まん中）
        cx_, cy_ = P(W((sum(us) / len(us), sum(vs) / len(vs))))
        out.append(f'<text x="{cx_:.1f}" y="{cy_ + 6:.1f}" class="t" text-anchor="middle">{ESC(s["name"])}（t{s["thick"]:.0f}）</text>')
    for b in plan.get("beams", []):
        m = ((b["ca"][0] + b["cb"][0]) / 2.0, (b["ca"][1] + b["cb"][1]) / 2.0)
        x, y = P(m)
        out.append(f'<text x="{x + 2:.1f}" y="{y:.1f}" class="ts">{ESC(b["name"])}：{b["width"]:.0f}×{b["depth"]:.0f}</text>')
    for c in plan.get("columns", []):
        x, y = P(c["c"])
        out.append(f'<text x="{x - 3:.1f}" y="{y + 0.8:.1f}" class="ts">{ESC(c["name"])} {c["width"]:.0f}×{c["depth"]:.0f}</text>')
    for w in plan.get("walls", []):
        m = ((w["ca"][0] + w["cb"][0]) / 2.0, (w["ca"][1] + w["cb"][1]) / 2.0)
        x, y = P(m)
        out.append(f'<text x="{x:.1f}" y="{y - 2:.1f}" class="ts">{ESC(w["name"])} t{w["thick"]:.0f}</text>')
    # 通り芯（一点鎖線。X は上、Y は左に記号。芯どうしの寸法）
    grids = grid_lines(plan)
    gx = sorted(g["pos"] for g in grids if g["axis"] == "x" and x0 <= g["pos"] <= x1)
    gy = sorted(g["pos"] for g in grids if g["axis"] == "y" and y0 <= g["pos"] <= y1)
    for g in grids:
        if g["axis"] == "x" and x0 <= g["pos"] <= x1:
            out.append(line((g["pos"], y0 + 200.0), (g["pos"], y1 - 200.0), "grid"))
            bx, by = P((g["pos"], y1 - 200.0))
            out.append(_bubble(bx, by - 2.8, g["name"]))
        elif g["axis"] == "y" and y0 <= g["pos"] <= y1:
            out.append(line((x0 + 200.0, g["pos"]), (x1 - 200.0, g["pos"]), "grid"))
            bx, by = P((x0 + 200.0, g["pos"]))
            out.append(_bubble(bx - 2.8, by, g["name"]))
    if len(gx) >= 2:
        out.append(_chain([P((v, y1 - 200.0)) for v in gx], _pitch_texts(gx), 9.0))
    if len(gy) >= 2:
        out.append(_chain([P((x0 + 200.0, v)) for v in gy], _pitch_texts(gy), 9.0))
    out.append("</g>")
    # 引出し（右の欄。指す所の高さの順に並べて線を交わらせない）
    lab_x = ox + (x1 - x0) / scale + 4.0
    top_y = oy + 1500.0 / scale
    for k_, ((x, y), t_) in enumerate(sorted(labels, key=lambda l_: l_[0][1])):
        out.append(_label(x, y, lab_x, top_y + k_ * 5.0, t_))
    # 凡例と注記（右の欄）
    lx = PAGE_W - MARGIN - 100.0
    leg = [("○", "パイプサポート（スラブ下）"), ("□", "パイプサポート（梁下）"), ("▬", "大引 杉 90×90"),
           ("─", "根太 角パイプ □50×50×2.3 @300（細線）"), ("━", "敷き桟木 45×60（寝かせる）"), ("- - -", "梁（スラブの下）"),
           ("■", "壁・柱"), ("─・─", "断面の切る位置（a－a・b－b は2枚目）"), ("○X1", "通り芯（柱・壁の芯から）"),
           ("- - -（紫）", "大筋かい 単管（列の鉛直面に X）")]
    out.append(f'<text x="{lx}" y="{MARGIN + 18}" class="h2">凡例</text>')
    for k, (sym, t_) in enumerate(leg):
        out.append(f'<text x="{lx}" y="{MARGIN + 25 + k * 4.5}" class="t">{ESC(sym)}　{ESC(t_)}</text>')
    notes = ["注記",
             "1. 支柱（パイプサポート）は敷き桟木の上に立て、上端は大引に釘止めする",
             "2. パイプサポートを継ぐのは2本まで。継ぐときは4本以上のボルトか専用の金具（安衛則 242条）",
             "3. 支柱の高さが 3.5m を超えるときは、高さ 2m 以内ごとに水平つなぎを2方向に設け、変位を防ぐ（同条）",
             "4. 地盤に立てるときは敷板・敷角を敷き、沈下を防ぐ（安衛則 242条）",
             "5. コンクリートの打設中は型枠支保工を点検し、異常があれば中止する（安衛則 244条）",
             "6. 組立て・解体は型枠支保工の組立て等作業主任者の直接の指揮で行う（安衛則 246・247条）",
             "7. パイプサポートの許容支持力はメーカーの表（仮設工業会認定品・使用高さと水平つなぎの有無）による。3.4m を超える支柱は水平つなぎを設ける",
             "8. 支柱の脚部は根がらみ（単管 φ48.6）を2方向に設けて滑動を防ぎ、支柱・大引・根太の接続は釘・クランプで緊結する"]
    y = MARGIN + 66.0
    for k, t_ in enumerate(notes):
        cls = "h2" if k == 0 else "ts"
        for j, part in enumerate(_wrap(t_, NOTE_CHARS) if k else [t_]):
            out.append(f'<text x="{lx + (3.0 if j else 0.0)}" y="{y:.1f}" class="{cls}">{ESC(part)}</text>')
            y += 3.4
        y += 0.8
    y0 = y + 4.0
    # 部材表
    mats = [("せき板", "型枠用合板 12mm"), ("根太", "角パイプ □50×50×2.3 @300"), ("大引", "杉 90×90 @900"),
            ("支柱", "パイプサポート（上端 釘止め）"), ("敷き桟木", "45×60 寝かせ"), ("根がらみ", "単管 φ48.6×2.4（2方向）"),
            ("大筋かい", "単管 φ48.6×2.4・自在クランプ（水平荷重 5%）"),
            ("柱", "コラムクランプ（壁の取り付く柱は外端太・フォームタイ）"),
            ("壁・梁の側板", "桟木 45×60・外端太 単管φ48.6 2本組・フォームタイ W5/16")]
    out.append(f'<text x="{lx}" y="{y0:.1f}" class="h2">部材</text>')
    for k, (a_, b_) in enumerate(mats):
        out.append(f'<text x="{lx}" y="{y0 + 6 + k * 4.0:.1f}" class="ts">{ESC(a_)}：{ESC(b_)}</text>')
    return "型枠支保工 伏図", f"1/{scale}", "".join(out)


# ---------------------------------------------------------------- 2枚目 断面図（a－a・b－b）
PLY_MM, NEDA_MM, OBIKI_MM, SILL_MM, PS_D_MM, TUBE_D_MM = 12.0, 50.0, 90.0, 45.0, 60.5, 48.6


def _struct_local(plan: dict, L) -> list[tuple[str, dict, list]]:
    """梁・壁・柱の平面の形（スラブの局所座標）: [(種類, 元のデータ, 多角形)]."""
    wd = _world(plan)
    out = [("beam", b, [L(p) for p in poly]) for b, poly in zip(plan.get("beams", []), wd["beams"])]
    out += [("wall", w, [L(p) for p in poly]) for w, poly in zip(plan.get("walls", []), wd["walls"])]
    out += [("col", c, [L(p) for p in poly]) for c, poly in zip(plan.get("columns", []), wd["cols"])]
    return out


def section_extent(plan: dict, s: dict, h: int) -> tuple[float, float, float]:
    """断面の横の範囲 (h の最小・最大) と高さ（床からスラブの天端まで）."""
    vc, uc = section_cuts(s)
    ivs = _cut_intervals(s["outer"], h, vc if h == 0 else uc)
    if not ivs:
        vals = [p[h] for p in s["outer"]]
        ivs = [(min(vals), max(vals))]
    return min(a for a, _b in ivs), max(b for _a, b in ivs), s["bottom"] + s["thick"] - s["floor"]


def _section_cut(plan: dict, s: dict, h: int, x0: float, ytop: float, sc: float, name: str) -> tuple[str, float]:
    """スラブを切った断面（h＝0: 大引の向き u に沿って a－a、1: 大引に直角 v に沿って b－b）. 戻り値は (SVG, 下の y)."""
    from .slab_form import ps_model

    k = 1.0 / sc
    W, L = _local(s)
    vc, uc = section_cuts(s)
    cut = vc if h == 0 else uc
    q = 1 - h
    floor, bottom, thick = s["floor"], s["bottom"], s["thick"]
    top = bottom + thick
    hmin, hmax, _H = section_extent(plan, s, h)
    X = lambda c: x0 + (c - hmin + 1200.0) * k
    ys = ytop + 22.0                               # スラブの天端の紙の y（上に連続寸法2段）
    Y = lambda z: ys + (top - z) * k
    rect = lambda a, b, z0, z1, cls: (f'<rect x="{X(min(a, b)):.2f}" y="{Y(max(z0, z1)):.2f}" width="{abs(b - a) * k:.2f}" '
                                      f'height="{abs(z1 - z0) * k:.2f}" class="{cls}"/>')
    out, labels = [], []
    # 床
    out.append(f'<rect x="{X(hmin - 1200):.2f}" y="{Y(floor):.2f}" width="{(hmax - hmin + 2400) * k:.2f}" height="1.2" class="conc"/>')
    out.append(f'<text x="{X(hmin - 1200):.2f}" y="{Y(floor) - 1:.2f}" class="ts">▽床 FL{floor:+.0f}</text>')
    # スラブ・梁・壁・柱のコンクリート
    ivs = _cut_intervals(s["outer"], h, cut) or [(hmin, hmax)]
    for a, b in ivs:
        out.append(rect(a, b, bottom, top, "conc"))
    out.append(f'<text x="{X(hmin - 1200):.2f}" y="{Y(top) - 1:.2f}" class="ts">▽スラブ天端 {top - floor:+.0f}</text>')
    hole_iv = [iv for hole in s["holes"] for iv in _cut_intervals(hole, h, cut)]
    beams_cut = []
    for kind, d, poly in _struct_local(plan, L):
        for a, b in _cut_intervals(poly, h, cut):
            if kind == "beam":
                out.append(rect(a, b, d["bottom"], bottom, "conc"))
                beams_cut.append((d, a, b))
            else:
                out.append(rect(a, b, floor, bottom, "conc"))
                labels.append(((X((a + b) / 2), Y((floor + bottom) / 2)), f"{'壁' if kind == 'wall' else '柱'} {d['name']}"))
    labels.append(((X(ivs[0][0] + 300.0), Y(top - thick / 2)), f"スラブ {s['name']}（t{thick:.0f}）"))
    # せき板・根太・大引（スラブの下。穴＝梁・壁・柱の所は抜く）
    zp, zn, zo = bottom - PLY_MM, bottom - PLY_MM - NEDA_MM, bottom - PLY_MM - NEDA_MM - OBIKI_MM
    free = _minus(ivs, hole_iv)
    for a, b in free:
        out.append(rect(a, b, zp, bottom, "ply"))
    if free:
        labels.append(((X(free[-1][1] - 200.0), Y(bottom - 6.0)), "せき板：合板 12mm"))
    neda = s.get("neda", [])
    if h == 0:                                     # 根太は v の向き → 切り口に □50 の断面
        cross = [n_[2] for n_ in neda if n_[0] <= cut <= n_[1]]
        for u in cross:
            out.append(rect(u - 25, u + 25, zn, zp, "steel"))
        if cross:
            labels.append(((X(max(cross)), Y(zn + 25)), "根太：角パイプ □50×50×2.3 @300"))
    elif neda:                                     # 根太に沿って切る → いちばん近い根太を長く
        un = min({n_[2] for n_ in neda}, key=lambda u: abs(u - cut))
        segs = [(n_[0], n_[1]) for n_ in neda if abs(n_[2] - un) < 1.0]
        for a, b in segs:
            out.append(rect(a, b, zn, zp, "steel"))
        if segs:
            labels.append(((X(segs[-1][1] - 300.0), Y(zn + 25)), "根太：角パイプ □50×50×2.3 @300"))
    if h == 0:                                     # 大引は u の向き → 切り口の列の大引を長く
        segs = [(o_[0], o_[1]) for o_ in s["obiki"] if abs(o_[2] - cut) < 1.0]
        for a, b in segs:
            out.append(rect(a, b, zo, zn, "wood"))
        if segs:
            labels.append(((X(segs[-1][1] - 450.0), Y(zo + 45)), f"大引：杉 90×90 @{s['sv']:.0f}"))
    else:
        cross = [o_[2] for o_ in s["obiki"] if o_[0] <= cut <= o_[1]]
        for v in cross:
            out.append(rect(v - 45, v + 45, zo, zn, "wood"))
        if cross:
            labels.append(((X(max(cross)), Y(zo + 45)), f"大引：杉 90×90 @{s['sv']:.0f}"))
    # 敷き桟木・支柱・根がらみ・水平つなぎ
    zs = floor + SILL_MM
    if h == 0:
        sills = [(a, b) for a, b, v in s["sills"] if abs(v - cut) < 1.0]
        posts = sorted(p[0] for p in s["posts"] if abs(p[1] - cut) < 1.0)
    else:
        sills = [(v - 30.0, v + 30.0) for a, b, v in s["sills"] if a <= cut <= b]
        posts = sorted(p[1] for p in s["posts"] if abs(p[0] - cut) < 1.0)
    for a, b in sills:
        out.append(rect(a, b, floor, zs, "wood"))
    if sills:
        labels.append(((X(sills[-1][1] - 20.0), Y(floor + SILL_MM / 2)), "敷き桟木 45×60（寝かせ）"))
    for p in posts:
        out.append(rect(p - PS_D_MM / 2, p + PS_D_MM / 2, zs, zo, "steel"))
        out.append(rect(p - 70, p + 70, zo - 6, zo, "steel"))           # 受け板（大引に釘止め）
        out.append(rect(p - 70, p + 70, zs, zs + 6, "steel"))           # 台板
    if posts:
        labels.append(((X(posts[-1] + 30), Y((zs + zo) / 2)), f"パイプサポート {ps_model(s['post_h'])}（長さ {s['post_h']:.0f}）"))
        tubes = [(s.get("negarami", 200.0), "根がらみ：単管 φ48.6（2方向）")] + [(z, "水平つなぎ：単管 φ48.6（2方向）") for z in s.get("ties", [])]
        for z, t_ in tubes:
            zz = floor + z
            out.append(rect(posts[0] - 150, posts[-1] + 150, zz - TUBE_D_MM / 2, zz + TUBE_D_MM / 2, "steel"))
            for p in posts:                        # 直交する単管（断面）
                out.append(f'<circle cx="{X(p + 60):.2f}" cy="{Y(zz + 55):.2f}" r="{max(0.3, 24.3 * k):.2f}" class="steel"/>')
            labels.append(((X(posts[-1] + 150), Y(zz)), t_))
    # 大筋かい（切り口と平行な列の筋かいを立面に写す）
    brs = [b_ for b_ in s.get("braces", []) if (abs(b_[1] - b_[4]) < 1.0 if h == 0 else abs(b_[0] - b_[3]) < 1.0)]
    for b_ in brs:
        out.append(f'<line x1="{X(b_[h]):.2f}" y1="{Y(floor + b_[2]):.2f}" x2="{X(b_[3 + h]):.2f}" y2="{Y(floor + b_[5]):.2f}" class="bracel"/>')
    if brs:
        b_ = brs[-1]
        labels.append(((X((b_[h] + b_[3 + h]) / 2), Y(floor + (b_[2] + b_[5]) / 2)), "大筋かい：単管 φ48.6（自在クランプ・端の列）"))
    # 梁（切り口を横切る梁）: 側板・底板・梁下の根太・大引・支柱
    for b, a0, a1 in beams_cut:
        bb = b["bottom"]
        for xs in (a0, a1):
            out.append(rect(xs - PLY_MM if xs == a0 else xs, xs if xs == a0 else xs + PLY_MM, bb - PLY_MM, bottom, "ply"))
        out.append(rect(a0, a1, bb - PLY_MM, bb, "ply"))
        c0 = (a0 + a1) / 2.0
        for yv in b.get("bot_y", []):
            out.append(rect(c0 + yv - 25, c0 + yv + 25, bb - PLY_MM - NEDA_MM, bb - PLY_MM, "steel"))
        half = b["psY"] + 120.0
        zbo = bb - PLY_MM - NEDA_MM - OBIKI_MM
        out.append(rect(c0 - half, c0 + half, zbo, zbo + OBIKI_MM, "wood"))
        for sg in (-1, 1):
            px = c0 + sg * b["psY"]
            out.append(rect(px - PS_D_MM / 2, px + PS_D_MM / 2, zs, zbo, "steel"))
            out.append(rect(px - 70, px + 70, zbo - 6, zbo, "steel"))
            out.append(rect(px - 100, px + 100, floor, zs, "wood"))
        for z in b.get("tate_z", []):              # 外端太（2本組）
            for xs, sg in ((a0, -1), (a1, 1)):
                for dz in (-27.0, 27.0):
                    out.append(f'<circle cx="{X(xs + sg * (PLY_MM + 60 + 24)):.2f}" cy="{Y(bb - PLY_MM + z + dz):.2f}" '
                               f'r="{max(0.3, 24.3 * k):.2f}" class="steel"/>')
        labels.append(((X(c0), Y((bb + bottom) / 2)), f"梁 {b['name']}（{b['width']:.0f}×{b['depth']:.0f}）"))
        labels.append(((X(c0 + b["psY"]), Y((zs + zbo) / 2)), f"梁下パイプサポート（長さ {b['post_h']:.0f}）"))
        labels.append(((X(c0 + half - 40), Y(zbo + 45)), "梁下大引：杉 90×90"))
    # 通り芯（切り口を横切るもの。記号は床の下）
    for g in grid_lines(plan):
        A = L((g["pos"], -1e7) if g["axis"] == "x" else (-1e7, g["pos"]))
        B = L((g["pos"], 1e7) if g["axis"] == "x" else (1e7, g["pos"]))
        if abs(B[q] - A[q]) < 1e-6:
            continue                               # 切り口と平行
        t_ = (cut - A[q]) / (B[q] - A[q])
        hh = A[h] + (B[h] - A[h]) * t_
        if hmin - 1200.0 <= hh <= hmax + 1200.0:
            out.append(f'<line x1="{X(hh):.2f}" y1="{Y(top) - 2:.2f}" x2="{X(hh):.2f}" y2="{Y(floor) + 6:.2f}" class="grid"/>')
            out.append(_bubble(X(hh), Y(floor) + 8.8, g["name"]))
    # 連続寸法: 上に支柱の割付ピッチ（スラブの端から）と全長、左に高さ、右に支柱の長さ・根がらみ
    if posts:
        pts = [hmin] + posts + [hmax]
        out.append(_chain([(X(p), Y(top)) for p in pts], _pitch_texts(pts), -6.0))
    out.append(_chain([(X(hmin), Y(top)), (X(hmax), Y(top))], [f"{hmax - hmin:.0f}"], -13.0))
    xl = X(hmin - 600.0)
    out.append(_dim(xl, Y(floor), xl, Y(bottom), f"{bottom - floor:.0f}", off=-3.0))
    out.append(_dim(xl, Y(bottom), xl, Y(top), f"{thick:.0f}", off=-3.0))
    out.append(_dim(xl - 9, Y(floor), xl - 9, Y(top), f"{top - floor:.0f}", off=-3.0))
    xr = X(hmax + 600.0)
    zl = [floor, zs, zo, bottom]
    for z0, z1 in zip(zl, zl[1:]):
        out.append(_dim(xr, Y(z0), xr, Y(z1), f"{z1 - z0:.0f}", off=3.0))
    if posts:
        zt = [floor] + [floor + z for z in [s.get("negarami", 200.0)] + list(s.get("ties", []))]
        for z0, z1 in zip(zt, zt[1:]):
            out.append(_dim(xr + 9, Y(z0), xr + 9, Y(z1), f"{z1 - z0:.0f}", off=3.0))
    # 引出し（右の欄）
    lab_x = X(hmax + 1200.0) + 16.0
    for k_, ((x, y), t_) in enumerate(sorted(labels, key=lambda l_: l_[0][1])):
        out.append(_label(x, y, lab_x, ys - 6.0 + k_ * 4.6, t_))
    # 題
    yb = max(Y(floor) + 17.0, ys - 6.0 + len(labels) * 4.6 + 2.0)     # 通り芯の記号の下
    out.append(f'<rect x="{X(hmin) - 2:.1f}" y="{yb - 4.2:.1f}" width="46" height="6" class="thin"/>'
               f'<text x="{X(hmin):.1f}" y="{yb:.1f}" class="h2">{name}断面図 S=1/{sc:.0f}</text>')
    return "".join(out), yb + 4.0


def section_page(plan: dict) -> tuple[str, str, str]:
    """断面図（a－a: 大引の向き・b－b: 大引に直角）. 計画届作成の手引の a－a 断面図の例にならい、床・スラブ・梁、せき板・根太・
    大引・パイプサポート・敷き桟木・根がらみ・水平つなぎ、割付ピッチと高さの寸法、部材の引出し（利用者の指定 2026-10-31: 断面も）."""
    slabs = plan.get("slabs") or []
    if not slabs or not slabs[0]["posts"]:
        return "型枠支保工 断面図", "―", '<text x="20" y="40" class="t">スラブの支保工がありません</text>'
    s = slabs[0]
    ext = [section_extent(plan, s, h) for h in (0, 1)]
    wmax = max(b - a for a, b, _H in ext) + 2400.0
    hmax_ = max(H for _a, _b, H in ext) + 600.0
    sc = next((v for v in SCALES if wmax / v <= 250.0 and hmax_ / v <= 72.0), SCALES[-1])
    body_a, y_a = _section_cut(plan, s, 0, MARGIN + 18.0, MARGIN + 12.0, float(sc), "a－a ")
    body_b, _y_b = _section_cut(plan, s, 1, MARGIN + 18.0, y_a + 4.0, float(sc), "b－b ")
    return "型枠支保工 断面図", f"1/{sc}", body_a + body_b


# ---------------------------------------------------------------- 3枚目 詳細図
def _label(x, y, tx, ty, text) -> str:
    return (f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{tx:.2f}" y2="{ty:.2f}" class="lead"/>'
            f'<line x1="{tx:.2f}" y1="{ty:.2f}" x2="{tx + len(text) * 2.0:.2f}" y2="{ty:.2f}" class="lead"/>'
            f'<text x="{tx:.2f}" y="{ty - 0.6:.2f}" class="ts">{ESC(text)}</text>')


def _section_slab_beam(plan: dict, x0: float, y0: float, scale: float) -> str:
    """スラブ・梁下の断面（梁に直角に切る）. 値は最初のスラブと梁."""
    s = (plan.get("slabs") or [{}])[0]
    b = (plan.get("beams") or [{}])[0]
    t = s.get("thick", 180.0)
    bw, bd = b.get("width", 400.0), b.get("depth", 700.0)
    floor = s.get("floor", 0.0)
    sb = s.get("bottom", 2820.0)
    k = 1.0 / scale
    half = 1800.0                                   # 梁の芯から両側に描く幅
    Y = lambda z: y0 - (z - floor) * k              # 紙の y（下が床）
    X = lambda v: x0 + v * k
    out = [f'<text x="{x0 - half * k}" y="{Y(sb + t) - 8}" class="h2">A　スラブ・梁下 断面（梁に直角）S=1/{scale:.0f}</text>']
    out.append(f'<line x1="{X(-half)}" y1="{Y(floor)}" x2="{X(half)}" y2="{Y(floor)}" class="thin"/>')
    # スラブ・梁のコンクリート
    out.append(f'<rect x="{X(-half)}" y="{Y(sb + t)}" width="{2 * half * k}" height="{t * k}" class="conc"/>')
    out.append(f'<rect x="{X(-bw / 2)}" y="{Y(sb + t)}" width="{bw * k}" height="{bd * k}" class="conc"/>')
    bb = sb + t - bd                                # 梁の下端
    # スラブ下: せき板・根太（□50 の断面 @300）・大引（梁と平行に見える長いもの）・支柱
    ply, ne, ob, sill = 12.0, 50.0, 90.0, 45.0
    for sg in (-1, 1):
        a, c = sg * (bw / 2 + 12 + 60 + 49 + 30), sg * half
        lo, hi = min(a, c), max(a, c)
        out.append(f'<rect x="{X(lo)}" y="{Y(sb)}" width="{(hi - lo) * k}" height="{ply * k}" class="ply"/>')
        v = lo + 100
        while v < hi - 30:
            out.append(f'<rect x="{X(v - 25)}" y="{Y(sb - ply)}" width="{50 * k}" height="{ne * k}" class="steel"/>')
            v += 300
        out.append(f'<rect x="{X(lo)}" y="{Y(sb - ply - ne)}" width="{(hi - lo) * k}" height="{ob * k}" class="wood"/>')
        for vv in (lo + 450, hi - 300):
            z_top = sb - ply - ne - ob
            out.append(f'<rect x="{X(vv - 30)}" y="{Y(z_top)}" width="{60 * k}" height="{(z_top - floor - sill) * k}" class="steel"/>')
            out.append(f'<rect x="{X(vv - 300)}" y="{Y(floor + sill)}" width="{600 * k}" height="{sill * k}" class="wood"/>')
    # 梁: 側板・桟木・外端太・フォームタイ・底板・根太・大引・支柱
    for sg in (-1, 1):
        xs = sg * bw / 2
        out.append(f'<rect x="{X(min(xs, xs + sg * ply))}" y="{Y(sb)}" width="{ply * k}" height="{(sb - bb + ply) * k}" class="ply"/>')
        out.append(f'<rect x="{X(min(xs + sg * ply, xs + sg * (ply + 60)))}" y="{Y(sb)}" width="{60 * k}" height="{(sb - bb + ply) * k}" class="wood"/>')
        for z in b.get("tate_z", [150.0, 450.0]):
            zz = bb - ply + z
            for dz in (-27, 27):
                out.append(f'<circle cx="{X(xs + sg * (ply + 60 + 24))}" cy="{Y(zz + dz)}" r="{24.3 * k}" class="steel"/>')
    for z in b.get("tie_z", []):
        zz = bb - ply + z
        out.append(f'<line x1="{X(-bw / 2 - 160)}" y1="{Y(zz)}" x2="{X(bw / 2 + 160)}" y2="{Y(zz)}" class="tie"/>')
    out.append(f'<rect x="{X(-bw / 2)}" y="{Y(bb)}" width="{bw * k}" height="{ply * k}" class="ply"/>')
    for yv in b.get("bot_y", [-bw / 2 + 25, bw / 2 - 25]):
        out.append(f'<rect x="{X(yv - 25)}" y="{Y(bb - ply)}" width="{50 * k}" height="{50 * k}" class="steel"/>')
    psy = b.get("psY", bw / 2 + 102)
    ob_w = 2 * (psy + 120)
    zob = bb - ply - 50
    out.append(f'<rect x="{X(-ob_w / 2)}" y="{Y(zob)}" width="{ob_w * k}" height="{90 * k}" class="wood"/>')
    for sg in (-1, 1):
        out.append(f'<rect x="{X(sg * psy - 30)}" y="{Y(zob - 90)}" width="{60 * k}" height="{(zob - 90 - floor - sill) * k}" class="steel"/>')
    out.append(f'<rect x="{X(-psy - 150)}" y="{Y(floor + sill)}" width="{(2 * psy + 300) * k}" height="{sill * k}" class="wood"/>')
    # 引出し
    lx = X(half) + 4
    labs = [(X(half * 0.7), Y(sb - 6), "せき板 合板 12mm"), (X(half * 0.62), Y(sb - ply - 25), "根太 □50×50×2.3 @300"),
            (X(half * 0.55), Y(sb - ply - ne - 45), "大引 杉 90×90 @900"), (X(half - 300), Y(sb - ply - ne - ob - 200), "パイプサポート（上端 釘止め）"),
            (X(half * 0.5), Y(floor + 20), "敷き桟木 45×60"), (X(bw / 2 + 80), Y(bb + 250), "外端太 単管φ48.6 2本組"),
            (X(bw / 2 + 140), Y(bb - ply + (b.get("tie_z") or [150])[0]), "フォームタイ W5/16"),
            (X(0), Y(zob + 45), "梁下 大引 杉 90×90"), (X(bw / 2 - 25), Y(bb - ply - 25), "梁下 根太 □50×50")]
    # 引出しは指す所の高さの順に並べる（線が交わらない）
    for k_, (x, y, t_) in enumerate(sorted(labs, key=lambda l_: l_[1])):
        out.append(_label(x, y, lx, Y(sb + t) + 4 + k_ * 5.2, t_))
    # 高さの寸法
    out.append(_dim(X(-half), Y(floor), X(-half), Y(sb), f"{sb - floor:.0f}", off=-5))
    out.append(_dim(X(-bw / 2), Y(bb), X(bw / 2), Y(bb), f"{bw:.0f}", off=-4))
    out.append(_dim(X(-half), Y(sb), X(-half), Y(sb + t), f"{t:.0f}", off=-5))
    return "".join(out)


def _detail_column(plan: dict, x0: float, y0: float, scale: float) -> str:
    """柱の詳細（平面と、段の高さの立面）. 値は最初の柱."""
    cols = plan.get("columns") or []
    if not cols:
        return ""
    c = next((x for x in cols if x.get("clamp")), cols[0])          # コラムクランプの柱を先に
    b, d = c["width"], c["depth"]
    k = 1.0 / scale
    out = [f'<text x="{x0}" y="{y0 - 4}" class="h2">B　柱の詳細 {ESC(c["name"])} {b:.0f}×{d:.0f}（平面 S=1/{scale:.0f}）</text>']
    cx, cy = x0 + (b / 2 + 250) * k, y0 + (d / 2 + 250) * k
    out.append(f'<rect x="{cx - b / 2 * k}" y="{cy - d / 2 * k}" width="{b * k}" height="{d * k}" class="conc"/>')
    for sg in (-1, 1):
        out.append(f'<rect x="{cx - (b / 2 + 12) * k}" y="{cy + sg * d / 2 * k - (12 * k if sg < 0 else 0)}" width="{(b + 24) * k}" height="{12 * k}" class="ply"/>')
        out.append(f'<rect x="{cx + sg * b / 2 * k - (12 * k if sg < 0 else 0)}" y="{cy - d / 2 * k}" width="{12 * k}" height="{d * k}" class="ply"/>')
    if c.get("clamp"):
        ext = 72 + 120
        for sg in (-1, 1):
            out.append(f'<rect x="{cx - (b / 2 + ext) * k}" y="{cy + sg * (d / 2 + 72) * k - (40 * k if sg < 0 else 0)}" width="{(b + 2 * ext) * k}" height="{40 * k}" class="steel"/>')
            out.append(f'<rect x="{cx + sg * (b / 2 + 72) * k - (40 * k if sg < 0 else 0)}" y="{cy - (d / 2 + ext) * k}" width="{40 * k}" height="{(d + 2 * ext) * k}" class="steel"/>')
        note = "コラムクランプ（4方の腕を角でくさび留め）"
    else:
        note = "外端太 単管2本組＋フォームタイ（壁の取り付く柱）"
    out.append(f'<text x="{x0}" y="{cy + (d / 2 + 320) * k}" class="ts">{ESC(note)}・桟木 45×60 @{c.get("sangi", 200):.0f}</text>')
    # 段の高さ（立面の目盛り）
    ex = cx + (b / 2 + 450) * k
    H = c["height"]
    kz = min(k, 60.0 / H)
    out.append(f'<line x1="{ex}" y1="{y0 + 60}" x2="{ex}" y2="{y0 + 60 - H * kz}" class="thin"/>')
    prev = 0.0
    for z in c["tate_z"]:
        out.append(f'<line x1="{ex - 2}" y1="{y0 + 60 - z * kz}" x2="{ex + 2}" y2="{y0 + 60 - z * kz}" class="tie"/>')
        out.append(f'<text x="{ex + 3}" y="{y0 + 60 - z * kz + 0.8}" class="ts">{z:.0f}（@{z - prev:.0f}）</text>')
        prev = z
    out.append(f'<text x="{ex - 4}" y="{y0 + 64}" class="ts">{"クランプ" if c.get("clamp") else "外端太"}の高さ（柱の下から）・柱の高さ {H:.0f}</text>')
    return "".join(out)


def _section_wall(plan: dict, x0: float, y0: float, scale: float) -> str:
    """壁の断面. 値は最初の壁."""
    w = (plan.get("walls") or [{}])[0]
    if not w:
        return ""
    t, H = w["thick"], w["height"]
    k = 1.0 / scale
    out = [f'<text x="{x0}" y="{y0 - H * k - 6}" class="h2">C　壁の断面 {ESC(w["name"])} t{t:.0f}（S=1/{scale:.0f}）</text>']
    X = lambda v: x0 + 200 * k + v * k
    Y = lambda z: y0 - z * k
    out.append(f'<rect x="{X(0)}" y="{Y(H)}" width="{t * k}" height="{H * k}" class="conc"/>')
    for sg, xs in ((-1, 0.0), (1, t)):
        out.append(f'<rect x="{X(xs if sg > 0 else xs - 12)}" y="{Y(H)}" width="{12 * k}" height="{H * k}" class="ply"/>')
        out.append(f'<rect x="{X(xs + 12 if sg > 0 else xs - 72)}" y="{Y(H)}" width="{60 * k}" height="{H * k}" class="wood"/>')
        for z in w["tate_z"]:
            for dz in (-27, 27):
                out.append(f'<circle cx="{X(xs + sg * 96.3)}" cy="{Y(z + dz)}" r="{24.3 * k}" class="steel"/>')
    for z in w["tate_z"]:
        out.append(f'<line x1="{X(-140)}" y1="{Y(z)}" x2="{X(t + 140)}" y2="{Y(z)}" class="tie"/>')
    out.append(_label(X(t + 96), Y(w["tate_z"][-1]), X(t + 320), Y(H) + 2, "外端太 単管φ48.6 2本組"))
    out.append(_label(X(t + 40), Y(w["tate_z"][0]), X(t + 320), Y(H) + 7, f"フォームタイ W5/16 @{w['tie_pitch']:.0f}（Pコン）"))
    out.append(_label(X(t + 40), Y(H * 0.5), X(t + 320), Y(H) + 12, f"桟木 45×60 @{w['sangi']:.0f}・せき板 合板 12mm"))
    prev = 0.0
    for z in w["tate_z"]:
        out.append(f'<text x="{X(-260)}" y="{Y(z) + 0.8}" class="ts">{z:.0f}</text>')
        prev = z
    out.append(_dim(X(t + 160), Y(0), X(t + 160), Y(H), f"{H:.0f}", off=-4))
    out.append(_dim(X(0), Y(0), X(t), Y(0), f"{t:.0f}", off=-4))
    return "".join(out)


def detail_page(plan: dict) -> tuple[str, str, str]:
    """(図名, 縮尺, 本文の SVG)."""
    s = (plan.get("slabs") or [{}])[0]
    hgt = (s.get("bottom", 2820.0) - s.get("floor", 0.0)) + s.get("thick", 180.0)
    sc = next((v for v in (20, 30, 40, 50) if hgt / v <= 125.0), 50)
    out = [_section_slab_beam(plan, 85.0, 30.0 + hgt / sc + 10.0, float(sc))]
    out.append(_detail_column(plan, 20.0, 195.0, 20.0))
    walls = plan.get("walls") or []
    if walls:
        H = walls[0]["height"]
        scw = next((v for v in (30, 40, 50, 60, 80, 100) if H / v <= 70.0), 100)
        out.append(_section_wall(plan, 150.0, 278.0, float(scw)))
    return "型枠支保工 詳細図", "図示", "".join(out)


# ---------------------------------------------------------------- 3枚目 計算書
def calc_lines(plan: dict) -> list[tuple[str, str]]:
    """[(見出し, 本文)] の並び."""
    out = [("前提", "側圧は JASS 5 の型枠設計用コンクリートの側圧（打込みの速さ 10m/h 以下、W0＝23.5kN/m³、液圧を上限）。"
                   "スラブ・梁の底はコンクリート 24kN/m³×厚さ＋型枠 0.4＋作業荷重 1.5kN/m²（安衛則 240条）。部材は単純梁で曲げ"
                   "（M＝wL²/8）とたわみ（δ＝5wL⁴/384EI、固定荷重、3mm 以下）。合板 12mm E5500・fb13.7、杉・桟木 E7000・fb10.3、"
                   "鋼 E205000・fb157 N/mm²（目安）。フォームタイ W5/16 は 13.7kN。パイプサポート1本の許容支持力は岡部 フラワーサポート／パイプサポート（仮設工業会認定品）の"
                   "表で、上下端 木材（上端 大引・下端 敷き桟木）・連係なしは使用高さ 2m 以下 19.6、2〜2.5m 17.6、2.5〜3m 13.7、"
                   "3〜3.4m 9.8kN、連係あり（水平つなぎ 2m 以内ごと・2方向）は 19.6kN。3.4m を超える支柱には水平つなぎを設ける")]
    for s in plan.get("slabs", []):
        q = s["q"]
        h_kn = q * H_LOAD_RATIO
        out.append((f"スラブ {s['name']}（厚さ {s['thick']:.0f}）", "\n".join(s["lines"])
                     + f"\n水平荷重 設計荷重の {H_LOAD_RATIO * 100:.0f}%＝{h_kn:.2f} kN/m²（安衛則 240条）。水平つなぎ・筋かいで受ける"))
    for b in plan.get("beams", []):
        out.append((f"梁 {b['name']}（{b['width']:.0f}×{b['depth']:.0f}）", "\n".join(b["lines"])))
    for c in plan.get("columns", []):
        out.append((f"柱 {c['name']}（{c['width']:.0f}×{c['depth']:.0f}・高さ {c['height']:.0f}）", "\n".join(c["lines"])))
    for w in plan.get("walls", []):
        out.append((f"壁 {w['name']}（厚さ {w['thick']:.0f}・高さ {w['height']:.0f}）", "\n".join(w["lines"])))
    return out


def calc_page(plan: dict) -> list[str]:
    """計算書（長ければ複数枚）."""
    items = calc_lines(plan)
    pages, cur, y = [], [], 18.0
    for head, body in items:
        lines = []
        for ln in body.split("\n"):
            while len(ln) > 92:
                lines.append(ln[:92])
                ln = "　" + ln[92:]
            lines.append(ln)
        need = 5 + 3.4 * len(lines)
        if y + need > PAGE_H - MARGIN - TB_H - 4 and cur:
            pages.append(cur)
            cur, y = [], 18.0
        cur.append(f'<text x="{MARGIN + 4}" y="{y + 4}" class="h2">{ESC(head)}</text>')
        for k, ln in enumerate(lines):
            cur.append(f'<text x="{MARGIN + 8}" y="{y + 8.5 + k * 3.4}" class="t">{ESC(ln)}</text>')
        y += need + 2
    pages.append(cur)
    sign = (f'<text x="{PAGE_W - MARGIN - 120}" y="{MARGIN + 6}" class="t">計算者：　　　　　　　　照査者：</text>'
            f'<line x1="{PAGE_W - MARGIN - 106}" y1="{MARGIN + 7}" x2="{PAGE_W - MARGIN - 68}" y2="{MARGIN + 7}" class="thin"/>'
            f'<line x1="{PAGE_W - MARGIN - 52}" y1="{MARGIN + 7}" x2="{PAGE_W - MARGIN - 4}" y2="{MARGIN + 7}" class="thin"/>')
    return [sign + "".join(p) for p in pages]


# ---------------------------------------------------------------- 部材等明細書
def _where(plan: dict) -> str:
    """使用部位（型枠を置いた躯体の種類）."""
    kinds = [k for k, key in (("スラブ", "slabs"), ("梁", "beams"), ("壁", "walls"), ("柱", "columns")) if plan.get(key)]
    return "・".join(kinds) or "―"


def member_rows(plan: dict) -> list[tuple[str, str, str]]:
    """部材等明細書の材料（構造材料の種類, 材料・材質及び主要寸法, 使用部位）. 手引 p.147 の例の欄、置いた型枠で使う物だけ."""
    from .slab_form import PS_SOURCE, ps_model

    slabs, beams, walls, cols = (plan.get(k) or [] for k in ("slabs", "beams", "walls", "columns"))
    sides = "・".join(k for k, v in (("壁", walls), ("梁の側板", beams), ("柱", [c for c in cols if not c.get("clamp")])) if v)
    out = [("せき板", "型枠用合板 12mm（JAS）", _where(plan))]
    if slabs or beams:
        sv = "・".join(sorted({f"@{s['sv']:.0f}" for s in slabs})) or "@900"
        models = []
        for x in slabs + [b for b in beams if b.get("post_h")]:
            m = ps_model(x["post_h"])
            if m not in models:
                models.append(m)
        aux = [m for m in models if "補助" in m]
        out += [("角パイプ", "JIS G 3466 STKR400 □50×50×2.3（根太 @300）", "根太（スラブ・梁下）"),
                ("木材（角材）", f"杉 90×90（大引 {sv}）", "大引（スラブ・梁下）"),
                ("パイプサポート", f"仮設工業会認定品 上柱管 φ48.6×2.4・下柱管 φ60.5×2.3（型式 {'・'.join(models) or '―'}）。"
                 f"許容支持力は{PS_SOURCE}", "支柱（スラブ・梁下）。上端は大引に釘止め"),
                ("補助サポート", f"有（{'・'.join(aux)}。継ぐのは2本まで、4本以上のボルトか専用の金具）" if aux
                 else "無（パイプサポートは継がない）", "支柱" if aux else "―")]
    ties = [s for s in slabs if s.get("ties")]
    out.append(("木材（桟木）", "杉 45×60", "・".join(x for x, v in (("縦桟木（" + (sides or "側板") + "）", sides),
                                                                    ("敷き桟木（支柱の下・寝かせ）", slabs or beams)) if v) or "―"))
    tube = [x for x, v in (("外端太（2本組）", sides), ("梁の受け", beams), ("根がらみ", slabs or beams),
                           ("水平つなぎ（2方向・2m 以内ごと）", ties)) if v]
    out.append(("単管", "JIS G 3444 STK500 φ48.6×2.4", "・".join(tube) or "―"))
    out.append(("水平つなぎ", "有（単管 φ48.6×2.4・2方向）" if ties else "無（支柱の高さ 3.4m 以下。メーカーの表の連係なしで受ける）", "支柱（スラブ下）" if ties else "―"))
    if sides:
        out.append(("フォームタイ", "W5/16（許容引張 13.7kN）・座金・ナット・Pコン", sides))
    if any(c.get("clamp") for c in cols):
        out.append(("コラムクランプ", "[-75×40×5 相当（4方の腕を角でくさび留め）", "柱（壁の取り付かない柱）"))
    out.append(("緊結金具", "直交クランプ・自在クランプ（JIS A 8951 相当）、釘", "単管の交差・支柱の上端・根がらみ"))
    return out


def load_rows(plan: dict) -> list[tuple[str, str, float, float, float, float, float]]:
    """部材等明細書の設計荷重（設置箇所, 設置高さ, 固定荷重 N/m², 積載荷重 N/m², 計 N/m², 支柱1本当り N, 許容支持力 N）."""
    from .slab_form import FORM_KN, PS_FREE_MAX_MM, RC_KN_M3, WORK_KN, ps_allow_kn

    out = []
    for s in plan.get("slabs", []):
        dead = (RC_KN_M3 * s["thick"] / 1000.0 + FORM_KN) * 1000.0
        out.append((f"スラブ {s['name']}（厚さ {s['thick']:.0f}）", f"床 {s['floor']:.0f} から型枠の下 {s['bottom']:.0f}（支柱 {s['post_h']:.0f}）",
                    dead, WORK_KN * 1000.0, dead + WORK_KN * 1000.0, s["post_kn"] * 1000.0,
                    s.get("ps_allow", ps_allow_kn(s["post_h"], bool(s.get("ties")))) * 1000.0))
    for b in plan.get("beams", []):
        if not b.get("post_h"):
            continue
        dead = (RC_KN_M3 * b["depth"] / 1000.0 + FORM_KN) * 1000.0
        out.append((f"梁 {b['name']}（{b['width']:.0f}×{b['depth']:.0f}）", f"梁の下 {b['bottom']:.0f}（支柱 {b['post_h']:.0f}）",
                    dead, WORK_KN * 1000.0, dead + WORK_KN * 1000.0, b["post_kn"] * 1000.0,
                    b.get("ps_allow", ps_allow_kn(b["post_h"], b["post_h"] > PS_FREE_MAX_MM)) * 1000.0))
    return out


def assembly_rows(plan: dict) -> list[tuple[str, str, str]]:
    """各部の構造・組立概要（項目, 内容, 詳細図 有・無）. 手引 p.147 の例の項目の順."""
    slabs, beams = plan.get("slabs") or [], plan.get("beams") or []
    shore = bool(slabs or beams)
    ties = [s for s in slabs if s.get("ties")]
    tie_txt = ("、".join(f"{s['name']} {len(s['ties'])}段" for s in ties) + "。高さ 2m 以内ごとに2方向に単管で設け、端は躯体に"
               "控えを取る（安衛則 242条）") if ties else "支柱の高さが 3.4m 以下なので水平つなぎは設けない（メーカーの表の連係なしの許容支持力で受ける。根がらみは設ける）"
    return [
        ("地盤（基礎）及び支柱支持物の強度検討", "下階のコンクリートスラブの上に立てる（支柱1本の荷重は設計荷重の表）。地盤に立てるときは敷板・"
         "敷角を敷き、地耐力を確かめる" if shore else "該当なし", "有" if shore else "無"),
        ("脚部の滑動・沈下防止措置", "敷き桟木 45×60 を寝かせて支柱の列ごとに通し、支柱を釘止め。根がらみ（単管）を2方向に設けクランプで緊結"
         if shore else "該当なし", "有" if shore else "無"),
        ("支柱上端の滑動防止措置", "パイプサポートの上端の受け板を大引に釘止めする" if shore else "該当なし", "有" if shore else "無"),
        ("水平つなぎ・筋かい・控え等の措置", tie_txt if shore else "該当なし", "有" if ties else "無"),
        ("支柱の継手", "パイプサポートは継がない（継ぐときは2本まで、4本以上のボルトか専用の金具。安衛則 242条）" if shore else "該当なし", "無"),
        ("枠組を支保工とした場合の措置", "該当なし（パイプサポートによる在来工法）", "無"),
        ("鋼管枠の組立", "該当なし", "無"),
        ("型枠段状組立の措置", "該当なし", "無"),
        ("梁の滑動・脱落・横振れ防止措置", "該当なし（梁式支保工を使わない）", "無"),
        ("梁受けとなる構造物の補助、取付け方法", "該当なし", "無"),
    ]


def concrete_outline(plan: dict) -> str:
    """打設コンクリート構造物の概要（置いた型枠の躯体）."""
    parts = [f"スラブ {s['name']} 厚さ {s['thick']:.0f}" for s in plan.get("slabs", [])]
    parts += [f"梁 {b['name']} {b['width']:.0f}×{b['depth']:.0f}" for b in plan.get("beams", [])]
    parts += [f"壁 {w['name']} 厚さ {w['thick']:.0f}・高さ {w['height']:.0f}" for w in plan.get("walls", [])]
    parts += [f"柱 {c['name']} {c['width']:.0f}×{c['depth']:.0f}" for c in plan.get("columns", [])]
    return "鉄筋コンクリート造（普通コンクリート 24kN/m³）。" + "、".join(parts)


def _wrap_w(text: str, width_mm: float, size: float) -> list[str]:
    """幅に入る字数で折り返す（全角は size、半角は size×0.55 の目安）."""
    out, cur, w = [], "", 0.0
    for ch in text:
        cw = size * (0.55 if ord(ch) < 0x2000 else 1.0)
        if w + cw > width_mm and cur:
            out.append(cur)
            cur, w = "", 0.0
        cur += ch
        w += cw
    out.append(cur)
    return out


def _table(x: float, y: float, widths: list[float], head: list[str], rows: list[list[str]], size: float = 2.1,
           aligns: str = "") -> tuple[str, float]:
    """罫線の表（左上 x, y）。戻り値は (SVG, 下の y)."""
    out, lh = [], size * 1.45
    cls = "ts" if size <= 2.2 else "t"
    for r, cells in enumerate([head] + rows):
        lines = [_wrap_w(str(c), w - 2.0, size) for c, w in zip(cells, widths)]
        h = max(len(ln) for ln in lines) * lh + 1.6
        cx = x
        for k, (ln, w) in enumerate(zip(lines, widths)):
            out.append(f'<rect x="{cx:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" class="thin"/>')
            right = r > 0 and k < len(aligns) and aligns[k] == "r"
            for j, t_ in enumerate(ln):
                tx = cx + w - 1.0 if right else cx + 1.0
                anchor = ' text-anchor="end"' if right else ""
                weight = ' font-weight="bold"' if r == 0 else ""
                out.append(f'<text x="{tx:.1f}" y="{y + 0.8 + (j + 0.8) * lh:.1f}" class="{cls}"{anchor}{weight}>{ESC(t_)}</text>')
            cx += w
        y += h
    return "".join(out), y


def member_page(plan: dict) -> tuple[str, str, str]:
    """型枠支保工部材等明細書（計画届作成の手引 第6版 p.147 の例の欄）."""
    x0 = MARGIN + 4
    out = [f'<text x="{x0}" y="{MARGIN + 14}" class="h2">打設コンクリート構造物の概要</text>']
    body, y = _table(x0, MARGIN + 16, [392.0], ["概要"], [[concrete_outline(plan)]], size=2.6)
    out.append(body)
    out.append(f'<text x="{x0}" y="{y + 6:.1f}" class="h2">構造材料（材料、材質及び主要寸法・使用部位）</text>')
    body, y = _table(x0, y + 8, [40.0, 200.0, 152.0], ["構造材料の種類", "材料、材質及び主要寸法", "使用部位"],
                     [list(r) for r in member_rows(plan)], size=2.6)
    out.append(body)
    out.append(f'<text x="{x0}" y="{y + 6:.1f}" class="h2">設置箇所・設置期間・設計荷重</text>')
    rows = [[a, b, f"{d:,.0f}", f"{l:,.0f}", f"{t:,.0f}", f"{n:,.0f}", f"{al:,.0f}", "可" if n <= al else "不可"]
            for a, b, d, l, t, n, al in load_rows(plan)] or [["―", "―", "", "", "", "", "", ""]]
    body, y = _table(x0, y + 8, [62.0, 92.0, 34.0, 34.0, 34.0, 38.0, 38.0, 16.0],
                     ["設置箇所", "設置高さ（mm）", "固定荷重 N/m²", "積載荷重 N/m²", "計 N/m²", "支柱1本当り N",
                      "支柱の許容支持力 N", "判定"], rows, size=2.6, aligns="__rrrrr")
    out.append(body)
    out.append(f'<text x="{x0}" y="{y + 4.5:.1f}" class="t">設置期間：組立開始　　　年　　月　　日　～　解体完了　　　年　　月　　日'
               f'　　固定荷重＝コンクリート 24kN/m³×厚さ＋型枠 0.4kN/m²、積載荷重＝作業荷重 1.5kN/m²（安衛則 240条）</text>')
    out.append(f'<text x="{x0}" y="{y + 12:.1f}" class="h2">各部の構造・組立概要</text>')
    body, y = _table(x0, y + 14, [80.0, 286.0, 26.0], ["項目", "構造・組立の概要", "詳細図"],
                     [[a, b, f"{c}（断面図・詳細図）" if c == "有" else c] for a, b, c in assembly_rows(plan)], size=2.6)
    out.append(body)
    return "型枠支保工 部材等明細書", "―", "".join(out)


# ---------------------------------------------------------------- 4枚目 計画届
def notice_info(plan: dict) -> dict:
    """支柱の高さ（床から型枠の下まで）の最大と、計画届の要否."""
    hs = []
    for s in plan.get("slabs", []):
        hs.append((s["bottom"] - s["floor"], f"スラブ {s['name']}"))
    for b in plan.get("beams", []):
        if b.get("post_h", 0) > 0:
            hs.append((b["bottom"] - (b["bottom"] - 12 - 50 - 90 - 45 - b["post_h"]), f"梁 {b['name']}"))
    hmax = max(hs) if hs else (0.0, "")
    return {"heights": hs, "max": hmax[0], "where": hmax[1], "required": hmax[0] >= NOTICE_H_MM}


def notice_page(plan: dict) -> tuple[str, str, str]:
    """(図名, 縮尺, 本文の SVG)."""
    ni = notice_info(plan)
    project = plan.get("project", "")
    out = [f'<text x="{MARGIN + 4}" y="22" class="h2">型枠支保工の計画届の要否（安衛則 88条・別表第7：支柱の高さが 3.5m 以上の型枠支保工）</text>']
    y = 30.0
    for h, where in ni["heights"]:
        out.append(f'<text x="{MARGIN + 8}" y="{y}" class="t">{ESC(where)}：支柱の高さ（床から型枠の下まで） {h:.0f} mm'
                   f'　{"≧" if h >= NOTICE_H_MM else "＜"} 3500 → {"要" if h >= NOTICE_H_MM else "不要"}</text>')
        y += 4.0
    verdict = "計画届が要る（工事開始の 30日前までに労働基準監督署長へ）" if ni["required"] else \
        "計画届は要らない（支柱の高さが 3.5m 未満）。ただし組立図は作り、作業主任者の指揮で組み立てる（安衛則 240・246条）"
    out.append(f'<text x="{MARGIN + 4}" y="{y + 4}" class="h2">判定：{ESC(verdict)}</text>')
    y += 14
    out.append(f'<text x="{MARGIN + 4}" y="{y}" class="h2">様式第20号（機械等設置・移転・変更届）の下書き{"" if ni["required"] else "（参考）"}</text>')
    y += 6
    rows = [("事業の種類", "建設業（建築工事）"), ("事業場の名称", project or ""), ("事業場の所在地", ""), ("電話", ""),
            ("計画の概要", "型枠支保工の設置"), ("製造し、又は取り扱う物質等", "―"),
            ("主要構造部分の概要", "パイプサポート（敷き桟木の上、上端は大引に釘止め）・大引 杉 90×90・根太 □50×50×2.3・せき板 合板 12mm"),
            ("支柱の高さの最大", f"{ni['max']:.0f} mm（{ni['where']}）"),
            ("設置期間", "　年　月　日 ～ 　年　月　日"), ("工事の開始予定", "　年　月　日"),
            ("参画者（計画の作成）", ""), ("事業者職氏名", "")]
    for a, b in rows:
        out.append(f'<rect x="{MARGIN + 6}" y="{y - 3.6}" width="70" height="5" class="thin"/>'
                   f'<rect x="{MARGIN + 76}" y="{y - 3.6}" width="230" height="5" class="thin"/>'
                   f'<text x="{MARGIN + 8}" y="{y}" class="t">{ESC(a)}</text><text x="{MARGIN + 78}" y="{y}" class="t">{ESC(b)}</text>')
        y += 5.0
    y += 6
    out.append(f'<text x="{MARGIN + 4}" y="{y}" class="h2">添付するもの（安衛則 別表第7）</text>')
    for k, t_ in enumerate(["型枠支保工を設置する場所の周囲の状況及び四隣との関係を示す図面", "型枠支保工の組立図（伏図・断面図 a－a・b－b・詳細図）",
                            "支柱等の配置図・使用する材料の種類と寸法（型枠支保工部材等明細書）", "構造計算書", "組立・解体の手順、作業主任者"]):
        out.append(f'<text x="{MARGIN + 8}" y="{y + 5 + k * 4}" class="t">・{ESC(t_)}</text>')
    return "型枠支保工 計画届の要否", "―", "".join(out)


# ---------------------------------------------------------------- まとめ
def page_list(plan: dict) -> list[tuple[str, str, str]]:
    """[(図名, 縮尺, 本文の SVG)] の並び（枠・表題欄は含まない。HTML とレイアウトの両方で使う）."""
    calc_bodies = calc_page(plan)
    out = [plan_page(plan), section_page(plan), detail_page(plan)]
    for k, body in enumerate(calc_bodies):
        out.append(("型枠支保工 構造計算書" + (f"（{k + 1}）" if len(calc_bodies) > 1 else ""), "―", body))
    out.append(member_page(plan))
    out.append(notice_page(plan))
    return out


def build_html(plan: dict) -> str:
    project = plan.get("project", "")
    pages = page_list(plan)
    html_pages = [_page(body, name, project, scale, k + 1, len(pages)) for k, (name, scale, body) in enumerate(pages)]
    return ("<!doctype html><html><head><meta charset='utf-8'><title>型枠支保工計画図</title><style>" + CSS
            + "</style></head><body>" + "".join(html_pages) + "</body></html>")


def build_xlsx(plan: dict, path: Path) -> None:
    from ashiba.xlsx_writer import Workbook

    wb = Workbook()
    sh = wb.sheet("構造計算書")
    sh.add_title("型枠支保工 構造計算書", 4)
    for head, body in calc_lines(plan):
        sh.add_blank()
        sh.add_header([head])
        for ln in body.split("\n"):
            sh.add([ln])
    sh.set_width(0, 120)
    sh = wb.sheet("材料")
    sh.add_header(["場所", "品名", "数", "注"])
    for r in plan.get("rows", []):
        sh.add(list(r))
    for k, wdt in enumerate((14, 36, 8, 60)):
        sh.set_width(k, wdt)
    sh = wb.sheet("支柱")
    sh.add_header(["場所", "支柱", "間隔", "長さ mm", "1本 kN", "本数"])
    for s in plan.get("slabs", []):
        sh.add([s["name"], "パイプサポート", f"{s['su']:.0f}×{s['sv']:.0f}", round(s["post_h"]), round(s["post_kn"], 1), len(s["posts"])])
    for b in plan.get("beams", []):
        sh.add([b["name"], "パイプサポート（梁下）", f"@{b['uke_pitch']:.0f}", round(b["post_h"]), round(b["post_kn"], 1),
                2 * len(b["uke_x"])])
    sh = wb.sheet("部材等明細書")
    sh.add_title("型枠支保工 部材等明細書", 8)
    sh.add(["打設コンクリート構造物の概要", concrete_outline(plan)])
    sh.add_blank()
    sh.add_header(["構造材料の種類", "材料、材質及び主要寸法", "使用部位"])
    for r in member_rows(plan):
        sh.add(list(r))
    sh.add_blank()
    sh.add_header(["設置箇所", "設置高さ", "固定荷重 N/m²", "積載荷重 N/m²", "計 N/m²", "支柱1本当り N", "許容支持力 N", "判定"])
    for a, b, d, l, t, n, al in load_rows(plan):
        sh.add([a, b, round(d), round(l), round(t), round(n), round(al), "可" if n <= al else "不可"])
    sh.add(["設置期間", "組立開始　年　月　日 ～ 解体完了　年　月　日"])
    sh.add_blank()
    sh.add_header(["各部の構造・組立概要", "内容", "詳細図"])
    for r in assembly_rows(plan):
        sh.add(list(r))
    for k, wdt in enumerate((30, 60, 40, 14, 14, 14, 14, 8)):
        sh.set_width(k, wdt)
    sh = wb.sheet("計画届の要否")
    ni = notice_info(plan)
    sh.add_header(["場所", "支柱の高さ mm", "3.5m 以上"])
    for h, where in ni["heights"]:
        sh.add([where, round(h), "要" if h >= NOTICE_H_MM else "不要"])
    sh.add(["判定", round(ni["max"]), "計画届が要る" if ni["required"] else "計画届は要らない"])
    wb.save(path)


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Chrome（ヘッドレス）で HTML を PDF に. Chrome が無ければ False."""
    import subprocess

    if not Path(CHROME).exists():
        return False
    r = subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()], capture_output=True, text=True, timeout=120)
    return pdf_path.exists() and r.returncode == 0
