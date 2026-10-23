"""図面の右の帯（凡例・最大積載荷重・共通事項・注意の表示・方位・キープラン）.

利用者の指定（2026-10-23）: 足場図面の作図サービス（OGISHI の仮設計画図の例）の、図面に必要なところを取り入れる。
例の図面には、どの図にも次がある:
- 凡例（足場の種類と幅・作業床、壁つなぎ、階段、朝顔・養生）
- 最大積載荷重の表（同一層連続スパン／それ以外）
- 共通事項（敷板、水平養生ネット、離れ300以上の内手すり、墜落制止用器具、最上部の手すり、外部養生材、幅木 など）
- 赤字の注意（「安全帯を使用」、断面・詳細には「上下作業は禁止する」）
- 平面図には方位記号、断面図にはキープラン（建物の外形と切った位置 A-A・B-B）

レイアウトの右に帯（PANEL_W_MM）を空けて図面を並べ（elevation_sections._layout_paper_mm の reserve）、
図面を置いたあとにレイアウトのウィンドウへ文字（CreateTexts。赤はペン）と線（CreatePolylines）で書く。
中身は純粋関数 panel_content が作る（座標は帯の左上を原点にした用紙 mm、下が負）。
"""

from __future__ import annotations

import math
import re
from typing import Optional

from .model import ScaffoldModel

PANEL_W_MM = 175.0          # 右の帯の幅（用紙 mm）
PANEL_GAP_MM = 8.0          # 図面と帯の間
TEXT_MM = 2.5               # 文字の高さ
LINE_MM = 4.2               # 行送り
WRAP = 44                   # 共通事項の1行の文字数（全角）


def _t(items, x, y, text, h=TEXT_MM, red=False, just="Left"):
    items["texts"].append({"x": x, "y": y, "text": text, "h": h, "red": red, "just": just})


def _box(items, x0, y0, x1, y1):
    items["lines"].append([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])


def scaffold_type_label(model: ScaffoldModel) -> str:
    """凡例・荷重表の足場の種類（例: 日建 NDシステム1800（くさび） W=914（踏板 W=500+240））."""
    from .master import SERIES_LABELS

    kind = SERIES_LABELS.get(model.master.series_id, model.master.series_id)
    ws = list(model.deck_widths_in_use)
    name = "布板" if model.master.is_frame else ("足場板" if model.master.is_tube else "踏板")
    # 単管抱き足場は建地1列で幅も床の幅も無い（「W=0（足場板 W=-）」と出ていた）
    row = int(model.post_row_spacing_mm)
    out = kind + (f" W={row}" if row > 0 else "")
    if ws:
        out += f"（{name} W={'+'.join(str(int(w)) for w in ws)}）"
    return out


def max_load_rows(model: ScaffoldModel) -> list[tuple[str, str, str]]:
    """最大積載荷重の表 [(足場の種類, 同一層連続スパン, それ以外)]。capacity.csv の作業床許容積載荷重とその出典から."""
    try:
        from .structural import _width_item, load_capacities

        caps = load_capacities(model.master.series_id)
        item = _width_item(caps, "作業床許容積載荷重", model)
        cv = caps.get((item, "スパン"))
    except Exception:
        cv = None
    if cv is None:
        return []
    kg = round(float(cv.value) * 1000.0 / 9.80665 / 10.0) * 10
    note = str(getattr(cv, "source", "") or getattr(cv, "note", "") or "")
    other = ""
    m = re.search(rf"{int(model.post_row_spacing_mm)}幅(\d+)kg", note)
    if m is None:
        m = re.search(r"以外の載荷は(\d+)kg", note)
    if m:
        other = f"{m.group(1)} kg"
    return [(scaffold_type_label(model), f"{kg:.0f} kg", other or "－")]


def common_notes(model: ScaffoldModel, stair_plan=None) -> list[str]:
    """共通事項（計画の条件から）."""
    c = model.config
    out = ["作業床の最大積載荷重は表のとおりとし、足場に表示する。同時に積載する層は2層までとする。",
           "ジャッキベースの下には敷板を敷き、釘止めして脚部の滑動を防止する。"]
    nets = list(getattr(c, "horizontal_net_levels", []) or [])
    if nets:
        out.append(f"水平養生ネットを {'・'.join(str(n) for n in nets)} 層に設置する。")
    if getattr(c, "inner_guard_rail", False) and not model.master.is_frame:
        out.append("躯体と足場の離れが300以上となる部分は内側に手すり（布材）を設け、墜落防止措置を行う。")
    out.append("足場の組立て・解体・変更の作業ではフルハーネス型墜落制止用器具を使用する。")
    out.append("最上部の作業床には手すり（高さ900以上）・中桟を設置する。")
    if c.has_toe_board:
        out.append("作業床の外側には幅木（H150以上）を各段に設置する。")
    sheet = str(getattr(c, "sheet_type", "") or "")
    if sheet and sheet != "なし":
        out.append(f"外部養生材は{sheet}とする。")
    if model.master.is_frame:
        out.append("壁つなぎは垂直9m・水平8m以内ごとに設ける（図の位置による）。")
    else:
        out.append("壁つなぎは垂直5m・水平5.5m以内ごとに設ける（図の位置による）。")
    if stair_plan is not None and getattr(stair_plan, "towers", None):
        out.append("階段の昇降口には開口部手すり・幅木を設け、昇降は階段を使用する。")
    elif int(getattr(c, "ladders", 0) or 0) > 0:
        # 階段の入らない足場（単管抱き足場など。敷地境界に収めた計画）は、はしごで昇降する
        out.append(f"昇降設備は昇降用はしご {int(c.ladders)}箇所とし、水平移動30m以内に設ける（部材は別途手配）。")
    out.append("支柱の抜け止め（連結ピン等）の措置を行う。")
    return out


def _wrap(s: str, n: int = WRAP) -> list[str]:
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]


def _legend(items, model: ScaffoldModel, y: float, kind: str, stair_plan=None, extra=()) -> float:
    w = PANEL_W_MM
    _t(items, w / 2 - 5, y - 5, "凡例", h=3.5)
    y -= 8.0
    owners = [(model, stair_plan), *extra]
    rows = []
    # 足場の種類は図にある面の組ぶん（面ごとに足場を替えた建物で、替えた面の種類が凡例に無かった）
    rows += [("scaf", lb) for lb in dict.fromkeys(scaffold_type_label(m) for m, _sp in owners)]
    rows.append(("tie", "壁つなぎ（平面 ▽・立面 ◎）"))
    if any(sp is not None and getattr(sp, "towers", None) for _m, sp in owners):
        rows.append(("stair", "昇降階段（開口部手すり・幅木）"))
    if any(m.asagao_heights() for m, _sp in owners):
        rows.append(("asa", "朝顔（防護棚）"))
    sheet = str(getattr(model.config, "sheet_type", "") or "")
    if sheet and sheet != "なし":
        rows.append(("sheet", f"{sheet}（外側の構面）"))
    if getattr(model, "site_boundary_mm", None):
        rows.append(("bnd", "敷地境界線（道路・隣地。数は足場の外から境界まで）"))
    top = y
    for key, label in rows:
        yc = y - 4.0
        if key == "scaf":
            items["lines"] += [[(4, yc + 1.5), (34, yc + 1.5)], [(4, yc - 1.5), (34, yc - 1.5)],
                               [(4, yc + 1.5), (14, yc - 1.5)], [(14, yc + 1.5), (24, yc - 1.5)],
                               [(24, yc + 1.5), (34, yc - 1.5)]]
        elif key == "tie":
            items["lines"].append([(16, yc + 1.8), (22, yc + 1.8), (19, yc - 1.8), (16, yc + 1.8)])
        elif key == "stair":
            _box(items, 6, yc - 2, 32, yc + 2)
            items["lines"] += [[(6 + 3.25 * k, yc - 2), (6 + 3.25 * k, yc + 2)] for k in range(1, 8)]
        elif key == "asa":
            items["lines"] += [[(6, yc - 1.5), (32, yc + 1.5)], [(6, yc - 2.5), (20, yc - 0.5)]]
        elif key == "sheet":
            items["lines"] += [[(4 + 4 * k, yc), (6 + 4 * k, yc)] for k in range(8)]
        elif key == "bnd":
            items["lines"] += [[(4 + 9 * k, yc), (10 + 9 * k, yc)] for k in range(4)]
        _t(items, 40, yc - 1.2, label)
        items["lines"].append([(0, y - 8.0), (w, y - 8.0)])
        y -= 8.0
    _box(items, 0, top + 8.0, w, y)
    items["lines"].append([(38, top), (38, y)])
    return y - 6.0


def _load_table(items, model: ScaffoldModel, y: float, extra=()) -> float:
    rows = list(dict.fromkeys(r for m in (model, *(m_ for m_, _sp in extra)) for r in max_load_rows(m)))
    if not rows:
        return y
    w = PANEL_W_MM
    _t(items, w - 64, y - 4.5, "最大積載荷重（1層1スパン）", h=2.5)
    y -= 7.0
    _t(items, w - 64, y - 4.2, "同一層連続スパン", h=2.2)
    _t(items, w - 30, y - 4.2, "それ以外", h=2.2)
    top = y + 7.0
    y -= 6.0
    for label, a, b in rows:
        # 種類と作業床で行を分ける（「…W=600」「（踏板 W=400+250）」）
        head, _, tail = label.partition("（")
        lines = _wrap(head, 30) + ([f"（{tail}"] if tail else [])
        hgt = max(7.0, 4.2 * len(lines) + 2.5)
        for k, ln in enumerate(lines):
            _t(items, 2, y - 4.2 - k * 4.2, ln, h=2.2)
        _t(items, w - 60, y - hgt / 2 - 1, a)
        _t(items, w - 28, y - hgt / 2 - 1, b)
        y -= hgt
        items["lines"].append([(0, y), (w, y)])
    _box(items, 0, top, w, y)
    items["lines"] += [[(w - 66, top), (w - 66, y)], [(w - 32, top - 7.0), (w - 32, y)], [(w - 66, top - 7.0), (w, top - 7.0)]]
    return y - 6.0


def _notes(items, model: ScaffoldModel, y: float, stair_plan=None) -> float:
    _t(items, 2, y - 4.5, "共通事項", h=3.0)
    y -= 9.0
    top = y + 9.0
    for s in common_notes(model, stair_plan):
        for k, ln in enumerate(_wrap(s)):
            _t(items, 3, y - 3.2, ("※" if k == 0 else "　") + ln, h=2.2)
            y -= 3.9
        y -= 0.6
    _box(items, 0, top, PANEL_W_MM, y - 2.0)
    return y - 8.0


def _north(items, y: float) -> float:
    """方位記号（プロジェクトの北＝図の上）."""
    cx, cy, r = PANEL_W_MM - 20.0, y - 18.0, 11.0
    n = 24
    items["lines"].append([(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
                           for k in range(n + 1)])
    items["lines"].append([(cx, cy + r + 3), (cx - 4, cy - 6), (cx, cy - 2), (cx + 4, cy - 6), (cx, cy + r + 3)])
    _t(items, cx - 1.5, cy + r + 4.5, "N", h=4.0)
    return y - 36.0


def _key_plan(items, model: ScaffoldModel, cuts: list[dict], y: float, wpan: float = PANEL_W_MM - 30.0,
              hmax: float = 70.0) -> float:
    """キープラン（建物の外形と、切った位置）. cuts は [{"label": "A", "start": (x,y)mm, "end": (x,y)mm}]."""
    pts = [(float(x), float(yy)) for x, yy in model.plan.outline.vertices]
    allp = pts + [p for c in cuts for p in (c["start"], c["end"])]
    x0, x1 = min(p[0] for p in allp), max(p[0] for p in allp)
    y0, y1 = min(p[1] for p in allp), max(p[1] for p in allp)
    s = min(wpan / max(x1 - x0, 1.0), hmax / max(y1 - y0, 1.0))
    ox, oy = 15.0, y - 10.0 - (y1 - y0) * s
    tr = lambda p: (ox + (p[0] - x0) * s, oy + (p[1] - y0) * s)
    _t(items, 2, y - 4.5, "Key Plan", h=3.0)
    items["lines"].append([tr(p) for p in pts] + [tr(pts[0])])
    for c in cuts:
        a, b = tr(c["start"]), tr(c["end"])
        items["lines"].append([a, b])
        for p in (a, b):
            _t(items, p[0] - 1.5, p[1] + 1.5, c["label"], h=3.5, red=True)
    return oy - 10.0


def red_notes(model: ScaffoldModel) -> list[str]:
    """赤字の注意書き（例の立面図の左下の赤枠）. 作業床が40cm未満の面があればその注意も."""
    out = []
    if sum(model.deck_widths_in_use or [0]) < 400 or model.config.is_hug:
        out.append("作業床が40cm未満の部分は、安全帯の使用を徹底し看板を設置する。")
    if model.config.scaffold_form == "一側足場":
        out.append("一側足場部分は、安全帯の使用を徹底し看板を設置する。")
    out.append("足場上下層において、上下作業禁止。")
    return out


def _title(items, y: float, title: str) -> float:
    """図の見出し（例の図面の右上の大きな枠: 「南立面図」など）."""
    _t(items, 4.0, y - 12.0, title, h=8.0)
    _box(items, 0, y, PANEL_W_MM, y - 17.0)
    return y - 21.0


def _red_box(items, model: ScaffoldModel, y: float, extra=()) -> float:
    notes = dict.fromkeys(s for m in (model, *(m_ for m_, _sp in extra)) for s in red_notes(m))
    lines = [ln for s in notes for ln in _wrap("・" + s, 40)]
    top = y
    for k, ln in enumerate(lines):
        _t(items, 2.5, y - 4.2 - k * 4.2, ln, h=2.4, red=True)
    y -= 4.2 * len(lines) + 2.5
    _box(items, 0, top, PANEL_W_MM, y)
    return y - 5.0


def panel_content(kind: str, model: ScaffoldModel, stair_plan=None, cuts: Optional[list[dict]] = None,
                  title: str = "", extra=()) -> dict:
    """帯の中身 {"texts": [...], "lines": [...]}（帯の左上を原点、mm、下が負）. kind: plan / elev / cross.

    extra は同じ図にあるほかの面の組の (模型, 階段)。凡例・荷重表・赤字の注意に足す。
    """
    items: dict = {"texts": [], "lines": []}
    y = 0.0
    if title and kind != "cross":
        y = _title(items, y, title)
    if kind == "cross":
        # 断面図は図面で用紙が埋まりやすいので低い帯: 左にキープラン、右に赤字の注意2つ
        if cuts:
            _key_plan(items, model, cuts, y, wpan=70.0, hmax=28.0)
        _t(items, 98, y - 9.0, "安全帯を使用", h=6.0, red=True)
        _box(items, 95.5, y, 141.5, y - 12.0)
        _t(items, 98, y - 24.0, "上下作業は禁止する", h=6.0, red=True)
        return items
    _t(items, 2.5, y - 9.0, "安全帯を使用", h=6.0, red=True)
    _box(items, 0, y, 46, y - 12.0)
    y -= 16.0
    if kind == "plan":
        y = _north(items, y + 16.0) - 4.0
    if kind == "elev":
        y = _red_box(items, model, y, extra)
    if kind in ("plan", "elev"):
        y = _legend(items, model, y, kind, stair_plan, extra)
    y = _load_table(items, model, y, extra)
    if kind == "plan":
        y = _notes(items, model, y, stair_plan)
    return items


def panel_height_mm(content: dict) -> float:
    """帯の高さ（用紙 mm）."""
    ys = [t["y"] - t["h"] for t in content["texts"]] + [y for pts in content["lines"] for _, y in pts]
    return -min(ys + [0.0]) + 4.0


def write_panel(client, layout_item_guid: str, paper_mm: tuple[float, float],
                margins_mm: tuple[float, float, float, float], content: dict,
                top_mm: Optional[float] = None) -> int:
    """レイアウトの右（余白の内）に帯を書く。top_mm（用紙の y）を省けば右上。置いた要素の数を返す."""
    from .elevation_sections import _activate

    ox = paper_mm[0] - margins_mm[2] - PANEL_W_MM - 2.0
    oy = (paper_mm[1] - margins_mm[1] - 4.0) if top_mm is None else float(top_mm)
    m = lambda x, y: {"x": (ox + x) / 1000.0, "y": (oy + y) / 1000.0}
    _activate(client, layout_item_guid)
    n = 0
    try:
        red = client.find_red_pen() if hasattr(client, "find_red_pen") else 20
    except Exception:
        red = 20
    if content["lines"]:
        r = client.tapir("CreatePolylines", {"polylinesData": [
            {"coordinates": [m(x, y) for x, y in pts]} for pts in content["lines"]]})
        n += sum(1 for e in r.get("elements", []) if "elementId" in e)
    if content["texts"]:
        data = []
        for t in content["texts"]:
            d = {"coordinate": {**m(t["x"], t["y"]), "z": 0.0}, "text": t["text"], "height": float(t["h"]),
                 "justification": t.get("just", "Left")}
            if t.get("red"):
                d["pen"] = int(red)
            data.append(d)
        r = client.tapir("CreateTexts", {"textsData": data})
        n += sum(1 for e in r.get("elements", []) if "elementId" in e)
    return n


def boundary_overlay(model: ScaffoldModel, region_mm: tuple[float, float, float, float], scale: int,
                     paper_pos_mm: tuple[float, float], other_models=()) -> dict:
    """平面図の上に重ねる敷地境界線（破線）と名前・面ごとの境界までの離れ（用紙 mm の絶対座標）.

    平面図のビューのレイヤー組み合わせで境界線のレイヤーが隠れていても図に出るよう、レイアウトに直接書く。
    other_models は面の組（face_forms）のほかの組の模型（その面の離れも書く。先頭の組の面しか書いていなかった）。
    """
    from .site_boundary import face_clearances

    items: dict = {"texts": [], "lines": []}
    bnd = list(getattr(model, "site_boundary_mm", None) or [])
    if len(bnd) < 3:
        return items
    roads = set(getattr(model, "site_road_edges", None) or set())
    tr = lambda p: (paper_pos_mm[0] + (p[0] - region_mm[0]) / scale, paper_pos_mm[1] + (p[1] - region_mm[1]) / scale)
    dash, gap = 6.0, 2.5
    for i in range(len(bnd)):
        a, b = tr(bnd[i]), tr(bnd[(i + 1) % len(bnd)])
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        s = 0.0
        while s < L:
            e = min(L, s + dash)
            items["lines"].append([(a[0] + ux * s, a[1] + uy * s), (a[0] + ux * e, a[1] + uy * e)])
            s = e + gap
            if s < L:                              # 一点鎖線（境界線の約束）
                items["lines"].append([(a[0] + ux * (s - gap / 2), a[1] + uy * (s - gap / 2)),
                                       (a[0] + ux * (s - gap / 2 + 0.4), a[1] + uy * (s - gap / 2 + 0.4))])
        # 境界の名前は辺の始点寄り（20%）。中央だと面の 40% に書く「境界まで」に重なった
        mid = (a[0] + (b[0] - a[0]) * 0.2, a[1] + (b[1] - a[1]) * 0.2)
        # 外側へ。縦の辺は文字（横書き・中央揃え）の半分の幅だけさらに外へ（線と足場のラベルに掛かっていた）
        name = "道路境界線" if i in roads else "隣地境界線"
        off = 2.0 + abs(uy) * len(name) * 2.5 * 0.55
        _t(items, mid[0] + off * uy, mid[1] - 2.0 * ux + 1.0, name, h=2.5, red=True)
    for mdl, c in [(m_, c_) for m_ in (model, *other_models) for c_ in face_clearances(m_, bnd, roads)]:
        ep = next(e for e in mdl.plan.edges if e.edge_index == c.edge_index)
        (sx, sy), (ex, ey) = ep.start_post, ep.end_post
        L = math.hypot(ex - sx, ey - sy) or 1.0
        ux, uy = (ex - sx) / L, (ey - sy) / L
        row = float(mdl.post_row_spacing_mm)
        # 外側建地の外面から境界までの寸法線（面の 40% の位置。足場ラインの GDL のラベルは躯体側の 25%・70% なので
        # 外側に出す。躯体側に書いていたので「くさび緊結式足場 600」のラベルに重なった）
        ox, oy = uy, -ux                                    # 外向き（躯体側は左手）
        bx, by = sx + ux * L * 0.4, sy + uy * L * 0.4
        d0 = row + 25.0
        p0 = tr((bx + ox * d0, by + oy * d0))
        txt = f"境界まで {c.min_mm:.0f}"
        if c.min_mm > 0:
            p1 = tr((bx + ox * (d0 + c.min_mm), by + oy * (d0 + c.min_mm)))
            items["lines"].append([p0, p1])
            for q in (p0, p1):                              # 端の斜めの止め
                items["lines"].append([(q[0] - 0.7, q[1] - 0.7), (q[0] + 0.7, q[1] + 0.7)])
            # 文字は境界の側に寄せる（中央だと足場の外の寸法線（全長・スパン）に重なった）
            k = max(0.5, 1.0 - (2.2 * 0.8 + 1.0) / max(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 1e-6))
            m = (p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k)
        else:
            m = (p0[0] + ox * 3.0, p0[1] + oy * 3.0)
        h = 2.2
        if abs(ux) >= abs(uy):                              # 横の面: 寸法線は縦 → 文字は線の右に
            _t(items, m[0] + 1.5 + len(txt) * h * 0.45, m[1] + h / 2.0, txt, h=h, red=c.min_mm < 300.0)
        else:                                               # 縦の面: 寸法線は横 → 文字は線の上に
            _t(items, m[0], m[1] + 1.0 + h, txt, h=h, red=c.min_mm < 300.0)
    return items


def _clip_segment(p, q, box):
    """線分 p→q を箱 (xmin, ymin, xmax, ymax) で切る。箱に掛からなければ None."""
    (x0, y0), (x1, y1) = p, q
    t0, t1 = 0.0, 1.0
    dx, dy = x1 - x0, y1 - y0
    for pk, qk in ((-dx, x0 - box[0]), (dx, box[2] - x0), (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if abs(pk) < 1e-12:
            if qk < 0:
                return None
            continue
        r = qk / pk
        if pk < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return (x0 + dx * t0, y0 + dy * t0), (x0 + dx * t1, y0 + dy * t1)


def cut_overlay(cuts: list[dict], region_mm: tuple[float, float, float, float], scale: int,
                paper_pos_mm: tuple[float, float]) -> dict:
    """平面図の上に重ねる断面図の切断線（一点鎖線）と、両端の太い線と記号（A・B）. 用紙 mm の絶対座標."""
    items: dict = {"texts": [], "lines": []}
    tr = lambda p: (paper_pos_mm[0] + (p[0] - region_mm[0]) / scale, paper_pos_mm[1] + (p[1] - region_mm[1]) / scale)
    for c in cuts:
        # 平面図の切り抜きの範囲の 16mm（用紙）内側で切る（外に出た端の記号が図枠の外に書かれて見えなかった）
        inset = 16.0 * scale                               # 記号（文字高 5mm）が図枠に掛からない
        box = (region_mm[0] + inset, region_mm[1] + inset, region_mm[2] - inset, region_mm[3] - inset)
        seg = _clip_segment(c["start"], c["end"], box)
        if seg is None:
            continue
        a, b = tr(seg[0]), tr(seg[1])
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        s = 0.0
        while s < L:                                       # 一点鎖線（長い線 8・間 1.5・点 0.5・間 1.5）
            e = min(L, s + 8.0)
            items["lines"].append([(a[0] + ux * s, a[1] + uy * s), (a[0] + ux * e, a[1] + uy * e)])
            d0 = e + 1.5
            if d0 + 0.5 < L:
                d1 = d0 + 0.5
                items["lines"].append([(a[0] + ux * d0, a[1] + uy * d0), (a[0] + ux * d1, a[1] + uy * d1)])
            s = d0 + 2.0
        for p, sgn in ((a, 1.0), (b, -1.0)):
            # 端の太い線（3本を 0.25mm ずらして重ねる）と記号
            for k in (-0.25, 0.0, 0.25):
                ox, oy = -uy * k, ux * k
                items["lines"].append([(p[0] + ox, p[1] + oy), (p[0] + ox + sgn * ux * 6.0, p[1] + oy + sgn * uy * 6.0)])
            _t(items, p[0] - sgn * ux * 4.0, p[1] - sgn * uy * 4.0 + 2.0, str(c["label"]), h=5.0, red=True)
    return items


def write_overlay(client, layout_item_guid: str, items: dict) -> int:
    """boundary_overlay の中身（用紙 mm の絶対座標）をレイアウトに書く."""
    from .elevation_sections import _activate

    if not items["lines"] and not items["texts"]:
        return 0
    _activate(client, layout_item_guid)
    try:
        red = client.find_red_pen()
    except Exception:
        red = 20
    n = 0
    if items["lines"]:
        r = client.tapir("CreatePolylines", {"polylinesData": [
            {"coordinates": [{"x": x / 1000.0, "y": y / 1000.0} for x, y in pts]} for pts in items["lines"]]})
        n += sum(1 for e in r.get("elements", []) if "elementId" in e)
    if items["texts"]:
        r = client.tapir("CreateTexts", {"textsData": [
            {"coordinate": {"x": t["x"] / 1000.0, "y": t["y"] / 1000.0, "z": 0.0}, "text": t["text"],
             "height": float(t["h"]), "justification": "Center", **({"pen": int(red)} if t.get("red") else {})}
            for t in items["texts"]]})
        n += sum(1 for e in r.get("elements", []) if "elementId" in e)
    return n
