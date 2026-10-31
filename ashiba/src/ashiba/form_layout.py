"""型枠支保工計画図を Archicad のレイアウトに置く（利用者の指定 2026-10-31: Archicadのレイアウトにも置いて）.

form_drawings の各図（A3 横の SVG）を、レイアウト「型枠支保工 n 図名」（サブセット「型枠支保工」、マスターは A3）に
線（ポリライン）・塗り（ハッチ）・文字で直接描く。レイアウトの座標は用紙の m（左下が原点、y は上向き）で、文字の高さは
用紙の mm（実機で確かめた）。枠と表題欄はマスターのものを使い、図はマスターの下の表題の帯より上に縮めて収める。
平面の図面（切り抜き）にしないので、モデルの平面に作図用の線を残さない。
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from .form_drawings import CSS, MARGIN, PAGE_H, PAGE_W

SUBSET = "型枠支保工"
LAYOUT_PREFIX = "型枠支保工"
TITLE_STRIP_MM = 28.0          # マスター（A3テンプレート）の下の表題の帯の高さ（余白の内側）
TEXT_FACTOR = 0.8              # Archicad の文字の高さ＝SVG の font-size×これ（同じ値だと一回り大きく行が詰まる。実機で確かめた）
CIRCLE_SEG = 16                # 円をハッチ・線にするときの辺の数
WHITE = (1.0, 1.0, 1.0)
# SVG の破線（stroke-dasharray）→ Archicad の線種の名前の候補
DASH_NAMES = {"4 1 0.6 1": ("一点鎖線",), "2 1": ("破線",), "1.5 0.8": ("破線", "点線")}


# ---------------------------------------------------------------- SVG → 図形
def _css_rules(css: str) -> dict[str, dict[str, str]]:
    out = {}
    for sel, body in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css):
        out[sel] = {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in body.split(";") if ":" in d)}
    return out


RULES = _css_rules(CSS)


def _color(v: Optional[str]) -> Optional[tuple[float, float, float]]:
    if not v or v == "none":
        return None
    v = v.strip()
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (0.0, 0.0, 0.0)


def _mul(a, b):
    """アフィン（a, b, c, d, e, f）の積 a・b."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _transform(t: Optional[str]):
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    if not t:
        return m
    for name, args in re.findall(r"(translate|rotate|scale)\(([^)]*)\)", t):
        v = [float(x) for x in re.split(r"[ ,]+", args.strip()) if x]
        if name == "translate":
            m = _mul(m, (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0.0))
        elif name == "scale":
            m = _mul(m, (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0))
        else:
            a = math.radians(v[0])
            r = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0.0, 0.0)
            if len(v) == 3:
                m = _mul(_mul(_mul(m, (1, 0, 0, 1, v[1], v[2])), r), (1, 0, 0, 1, -v[1], -v[2]))
            else:
                m = _mul(m, r)
    return m


def _apply(m, p):
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def _style(el, inherited: dict) -> dict:
    st = dict(inherited)
    for c in (el.get("class") or "").split():
        st.update(RULES.get(c, {}))
    for k in ("fill", "stroke", "stroke-width", "stroke-dasharray", "text-anchor", "font-size", "font-weight"):
        if el.get(k) is not None:
            st[k] = el.get(k)
    return st


@dataclass
class Shape:
    kind: str                                   # "poly" | "text"
    pts: list = field(default_factory=list)     # 用紙の mm（y は下向き）
    closed: bool = False
    stroke: Optional[tuple] = None
    width: float = 0.0
    dash: Optional[str] = None
    fill: Optional[tuple] = None
    text: str = ""
    size: float = 2.5
    anchor: str = "start"
    angle: float = 0.0                          # 度（SVG の向き＝時計回り）
    bold: bool = False


def _clip_seg(a, b, box):
    """線分を箱 (x0, y0, x1, y1) で切る（Liang–Barsky）。外なら None."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return (a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1)


def _clip_poly(pts, box):
    """多角形を箱で切る（Sutherland–Hodgman）."""
    x0, y0, x1, y1 = box
    edges = ((lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
             (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1)))
    out = list(pts)
    for inside, cut in edges:
        if not out:
            break
        src, out = out, []
        for k, cur in enumerate(src):
            prev = src[k - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
    return out


def _clip(shape: Shape, box) -> list[Shape]:
    if box is None:
        return [shape]
    if shape.kind == "text":
        x, y = shape.pts[0]
        return [shape] if box[0] <= x <= box[2] and box[1] <= y <= box[3] else []
    if shape.closed:
        pts = _clip_poly(shape.pts, box)
        if len(pts) < 3:
            return []
        return [Shape("poly", pts, True, shape.stroke, shape.width, shape.dash, shape.fill)]
    out = []
    for a, b in zip(shape.pts, shape.pts[1:]):
        seg = _clip_seg(a, b, box)
        if seg:
            out.append(Shape("poly", list(seg), False, shape.stroke, shape.width, shape.dash))
    return out


def svg_shapes(body: str) -> list[Shape]:
    """form_drawings の本文の SVG（断片）を図形の並びに（変換・切り抜き・CSS のクラスを解く）."""
    root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{body}</svg>')
    ns = "{http://www.w3.org/2000/svg}"
    clips = {}
    for cp in root.iter(ns + "clipPath"):
        r = cp.find(ns + "rect")
        if r is not None:
            x, y, w, h = (float(r.get(k, 0)) for k in ("x", "y", "width", "height"))
            clips[cp.get("id")] = (x, y, x + w, y + h)
    out: list[Shape] = []

    def walk(el, m, st, box):
        tag = el.tag.replace(ns, "")
        if tag == "clipPath":
            return
        m = _mul(m, _transform(el.get("transform"))) if tag != "text" else m
        st = _style(el, st)
        cp = el.get("clip-path")
        if cp:
            box = clips.get(re.sub(r"url\(#(.*)\)", r"\1", cp), box)
        stroke, fill = _color(st.get("stroke")), _color(st.get("fill", "#000"))
        width = float(st.get("stroke-width", 1.0 if stroke else 0.0))
        dash = st.get("stroke-dasharray")
        shapes = []
        if tag == "line":
            a = (float(el.get("x1", 0)), float(el.get("y1", 0)))
            b = (float(el.get("x2", 0)), float(el.get("y2", 0)))
            shapes.append(Shape("poly", [_apply(m, a), _apply(m, b)], False, stroke or (0, 0, 0), width, dash))
        elif tag in ("rect", "polygon", "circle"):
            if tag == "rect":
                x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            elif tag == "polygon":
                v = [float(t) for t in re.split(r"[ ,]+", el.get("points", "").strip()) if t]
                pts = list(zip(v[0::2], v[1::2]))
            else:
                cx, cy, r = (float(el.get(k, 0)) for k in ("cx", "cy", "r"))
                pts = [(cx + r * math.cos(2 * math.pi * k / CIRCLE_SEG), cy + r * math.sin(2 * math.pi * k / CIRCLE_SEG))
                       for k in range(CIRCLE_SEG)]
            if len(pts) >= 3:
                shapes.append(Shape("poly", [_apply(m, p) for p in pts], True, stroke, width, dash, fill))
        elif tag == "text":
            txt = "".join(el.itertext()).strip()
            if txt:
                x, y = float(el.get("x", 0)), float(el.get("y", 0))
                tm = _mul(m, _transform(el.get("transform")))
                ang = math.degrees(math.atan2(tm[1], tm[0]))
                shapes.append(Shape("text", [_apply(tm, (x, y))], text=txt, size=float(str(st.get("font-size", "2.6")).rstrip("px")),
                                    anchor=st.get("text-anchor", "start"), angle=ang, fill=fill or (0, 0, 0),
                                    bold=st.get("font-weight") == "bold"))
        for sh in shapes:
            out.extend(_clip(sh, box))
        for ch in el:
            walk(ch, m, {k: v for k, v in st.items() if k in ("fill", "stroke", "stroke-width", "font-size", "text-anchor")}, box)

    for ch in root:
        walk(ch, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), {}, None)
    return out


# ---------------------------------------------------------------- 用紙への当てはめ
def shapes_bbox(shapes: list[Shape]) -> tuple[float, float, float, float]:
    """図形の範囲（SVG の mm）。文字は基準点から右へ字数×大きさ、上へ大きさ分の目安."""
    xs, ys = [], []
    for sh in shapes:
        if sh.kind == "text":
            x, y = sh.pts[0]
            w = len(sh.text) * sh.size * (0.5 if sh.anchor == "middle" else 1.0)
            xs += [x - (w if sh.anchor != "start" else 0.0), x + (w if sh.anchor != "end" else 0.0)]
            ys += [y - sh.size, y]
        else:
            xs += [p[0] for p in sh.pts]
            ys += [p[1] for p in sh.pts]
    if not xs:
        return (MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN)
    return (min(xs), min(ys), max(xs), max(ys))


def fit_area(paper: tuple[float, float], margins: tuple[float, float, float, float], strip: float = TITLE_STRIP_MM,
             bbox: tuple[float, float, float, float] = (MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN), pad: float = 4.0):
    """図の範囲 bbox（SVG の mm）をレイアウトの描ける範囲（余白の内側、下の表題の帯より上）に収める縮尺と原点.
    原図（A3 の PDF）より大きくはしない。戻り値は (縮尺, 用紙の左 mm, 用紙の上 mm)。用紙の座標 = 原点 + 縮尺 × SVG の座標
    （y は下向き）。図は上に寄せ、左右は真ん中に置く."""
    left, top, right, bottom = margins
    w = paper[0] - left - right - 2 * pad
    h = paper[1] - top - bottom - strip - 2 * pad
    bw, bh = max(1.0, bbox[2] - bbox[0]), max(1.0, bbox[3] - bbox[1])
    s = min(1.0, w / bw, h / bh)
    ox = left + pad + (w - bw * s) / 2.0 - bbox[0] * s
    oy = top + pad - bbox[1] * s
    return s, ox, oy


def scale_note(title: str, scale: str, s: float) -> Optional[str]:
    """表題の帯の上に書く「図名　縮尺」。原図より縮めたときはその割合も（図の中の S=1/n は原図のもの）.
    縮尺の無い計算書・届は書かない."""
    if scale in ("―", "-", ""):
        return None
    out = f"{title}　縮尺 {scale}（A3）"
    if s < 0.995:
        out += f"　※ 原図（A3 の PDF）の {s * 100:.0f}% に縮小。図中の縮尺は原図のもの"
    return out


def _nearest_pen(pens: list[dict], rgb) -> int:
    if not pens:
        return 1
    return int(min(pens, key=lambda p: sum((p["color"][k] - v) ** 2 for k, v in zip(("red", "green", "blue"), rgb)))["index"])


def layout_data(shapes: list[Shape], paper, fit, pens: list[dict], line_types: dict[str, int],
                solid_fill: Optional[str]) -> dict:
    """図形 → Tapir の CreateHatches・CreatePolylines・CreateTexts の中身（座標は用紙の m）."""
    s, ox, oy = fit
    H = paper[1]
    P = lambda p: {"x": round((ox + s * p[0]) / 1000.0, 6), "y": round((H - oy - s * p[1]) / 1000.0, 6)}
    pen = {}

    def pn(rgb):
        key = tuple(round(c, 3) for c in rgb)
        if key not in pen:
            pen[key] = _nearest_pen(pens, key)
        return pen[key]

    hatches, polys, texts = [], [], []
    for sh in shapes:
        if sh.kind == "text":
            anchor = {"start": "LeftBottom", "middle": "MiddleBottom", "end": "RightBottom"}.get(sh.anchor, "LeftBottom")
            just = {"start": "Left", "middle": "Center", "end": "Right"}.get(sh.anchor, "Left")
            texts.append({"coordinate": {**P(sh.pts[0]), "z": 0.0}, "text": sh.text, "height": round(sh.size * s * TEXT_FACTOR, 2),
                          "pen": pn(sh.fill or (0, 0, 0)), "angle": -math.radians(sh.angle), "justification": just,
                          "style": {"anchor": anchor, "bold": sh.bold}})
            continue
        if sh.closed and sh.fill and sh.fill != WHITE and solid_fill:
            fp = pn(sh.fill)
            hatches.append({"coordinates": [P(p) for p in sh.pts], "fillId": {"guid": solid_fill}, "fillPenIndex": fp,
                            "contourPenIndex": fp})
        if sh.stroke and sh.width > 0:
            pts = sh.pts + ([sh.pts[0]] if sh.closed else [])
            d = {"coordinates": [P(p) for p in pts], "linePenIndex": pn(sh.stroke),
                 "penWeightMm": round(max(0.05, sh.width * s), 3)}
            if sh.dash:
                lt = line_types.get(" ".join(sh.dash.split()))
                if lt:
                    d["lineTypeIndex"] = lt
            polys.append(d)
    return {"hatches": hatches, "polylines": polys, "texts": texts}


def line_type_indexes(attrs: list[dict]) -> dict[str, int]:
    """破線の並び → 線種の番号（名前で探す）."""
    by_name = {a["name"]: a["index"] for a in attrs}
    out = {}
    for dash, names in DASH_NAMES.items():
        for n in names:
            if n in by_name:
                out[dash] = int(by_name[n])
                break
    return out


def solid_fill_id(attrs: list[dict]) -> Optional[str]:
    """塗りつぶし（100%）の塗りの GUID."""
    for a in attrs:
        if a["name"].replace(" ", "") in ("100%", "塗りつぶし", "Solid", "Solid Fill"):
            return a["attributeId"]["guid"]
    return None


def layout_names(pages: list[tuple[str, str, str]]) -> list[str]:
    return [f"{LAYOUT_PREFIX} {k} {name.replace('型枠支保工 ', '')}" for k, (name, _sc, _b) in enumerate(pages, 1)]


# ---------------------------------------------------------------- Archicad
@dataclass
class LayoutResult:
    layouts: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def place_layouts(client, pages: list[tuple[str, str, str]]) -> LayoutResult:
    """図をレイアウトに描く。前に作った「型枠支保工 …」のレイアウトは消して作り直す."""
    from .elevation_sections import (_create_layout, _delete_items, _layout_paper_mm, _tree, activate_floor_plan,
                                     ensure_subset, pick_master_layout, walk_tree)

    out = LayoutResult()
    _delete_items(client, [it["guid"] for it in walk_tree(_tree(client, "LayoutBook"))
                           if it["type"] == "LayoutItem" and it["name"].startswith(LAYOUT_PREFIX + " ")])
    subset = ensure_subset(client, SUBSET)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]], prefer="A3")
    try:
        r = client.tapir("GetAttributesByType", {"attributeType": "PenTable"}).get("attributes", [])
        pens = client.tapir("GetPenTables", {"attributeIds": [{"attributeId": r[0]["attributeId"]}],
                                             "fields": ["pens"]})["penTables"][0].get("pens", []) if r else []
    except Exception:
        pens = []
    try:
        lts = line_type_indexes(client.tapir("GetAttributesByType", {"attributeType": "Line"}).get("attributes", []))
    except Exception:
        lts = {}
    try:
        solid = solid_fill_id(client.tapir("GetAttributesByType", {"attributeType": "Fill"}).get("attributes", []))
    except Exception:
        solid = None
    if solid is None:
        out.notes.append("塗りつぶしの塗りが見つからないので、塗りは描きません")
    # ナビゲータには後から作ったものが上に並ぶので、最後の図から作る
    for name, (title, scale, body) in reversed(list(zip(layout_names(pages), pages))):
        lay = _create_layout(client, name, subset, master)
        if not lay:
            out.notes.append(f"レイアウト「{name}」を作れませんでした")
            continue
        paper, margins = _layout_paper_mm(client, lay, fallback=(PAGE_W, PAGE_H))
        shapes = svg_shapes(body)
        fit = fit_area(paper, margins, TITLE_STRIP_MM if master else 0.0, shapes_bbox(shapes))
        note = scale_note(title, scale, fit[0])
        if note:
            # 表題の帯のすぐ上の左（用紙の mm → SVG の mm に戻して図形に足す）
            x = (margins[0] + 4.0 - fit[1]) / fit[0]
            y = (paper[1] - margins[3] - (TITLE_STRIP_MM if master else 0.0) - 2.0 - fit[2]) / fit[0]
            shapes.append(Shape("text", [(x, y)], text=note, size=2.6 / fit[0], fill=(0.0, 0.0, 0.0)))
        data = layout_data(shapes, paper, fit, pens, lts, solid)
        client.tapir("ChangeWindow", {"navigatorItemId": {"guid": lay}})
        if client.current_window_type() != "Layout":
            out.notes.append(f"レイアウト「{name}」を開けませんでした")
            continue
        n = 0
        for cmd, key, items in (("CreateHatches", "hatchesData", data["hatches"]),
                                ("CreatePolylines", "polylinesData", data["polylines"]),
                                ("CreateTexts", "textsData", data["texts"])):
            if not items:
                continue
            try:
                r = client.tapir(cmd, {key: items})
                n += sum(1 for e in r.get("elements", []) if "elementId" in e)
            except Exception as e:  # 1種類が失敗しても他は描く
                out.notes.append(f"{name}: {cmd} が失敗（{e}）")
        out.layouts.insert(0, name)
        out.counts.insert(0, n)
    activate_floor_plan(client)
    return out
