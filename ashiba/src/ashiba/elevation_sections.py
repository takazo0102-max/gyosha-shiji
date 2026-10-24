"""足場の立面図を Archicad の断面図（立面ツール相当）で作り、レイアウトに置く.

以前は立面図を平面図の下に 2D オブジェクト（ashiba_line の viewMode=elev）として並べていた。
Archicad の流儀では立面は立面図／断面図ビューポイントで 3D から投影し、図面としてレイアウトに
置く。Tapir には立面図マーカーを作る命令が無いので、切断線を足場の外側に置いて躯体側を見る
断面図を面ごとに作る（見え方は立面図と同じ）。断面はモデルの 3D（支柱・布材・斜材・階段・
付帯設備）をそのまま映すので、平面の 2D オブジェクトと食い違わない。

面ごとに:
  1. 切断線: 足場の外側建地列からさらに clearance 外、面の両端を ext 延長。向きは
     始点→終点（外形が反時計回りなので左手＝躯体側を見る。Tapir の CreateSections は
     始点→終点の左手を見る向きで作る）
  2. 奥行き: 切断線から躯体の最も遠い頂点まで（向こう側の足場は入れない）
  3. レイアウトブックのサブセット「仮設足場」の下に面ごとのレイアウトを作り、
     用紙（マスターレイアウト）に収まる縮尺で図面を置く
同じ名前の断面・レイアウトが残っていれば先に消す（再実行で置き換え）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .model import ScaffoldModel

SUBSET_NAME = "仮設足場"
CLEARANCE_MM = 3500.0        # 外側建地列から切断線まで（ステージ出1500・昇降機の搬器と マストの外側 ≈2.5m を越える）
END_EXT_MM = 2000.0          # 面の両端の延長（出隅コーナー・隣の面の端部が入る）
DEPTH_MARGIN_MM = 300.0      # 躯体の最遠点からの余裕
# 用紙に入るいちばん大きい縮尺から（利用者の指定 2026-10-23: 出力の図面はなるべく大きくして縮尺変えて）
# JIS Z 8314 の推奨・許容の縮尺（1/80・1/150 は許容）
SCALE_CANDIDATES = (50, 60, 80, 100, 150, 200, 300, 500)


@dataclass
class SectionSpec:
    face_name: str
    name: str
    start_mm: tuple[float, float]
    end_mm: tuple[float, float]
    depth_mm: float
    length_mm: float
    edge_index: int = -1


@dataclass
class DrawingPlan:
    scale: int                       # 縮尺の分母（100 → 1/100）
    position_mm: tuple[float, float]  # 用紙上の図面の左下（mm）
    paper_mm: tuple[float, float]     # 用紙の幅・高さ（mm）


@dataclass
class ElevationPlacement:
    """1面ぶんの結果（再配置・撤去・帳票の照合用）."""
    face_name: str
    section_name: str
    section_guid: str = ""
    section_item_guid: str = ""
    layout_name: str = ""
    layout_item_guid: str = ""
    drawing_guid: str = ""
    scale: int = 100
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 幾何（純粋関数）

def section_name(prefix: str, face_name: str) -> str:
    return f"{prefix} {face_name} 足場立面"


def layout_name(prefix: str, face_name: str) -> str:
    return f"{prefix} 足場立面図 {face_name}"


CURTAIN_BEHIND_MM = 1000.0   # 足場ラインの幕は躯体面のこれだけ奥（3d.gdl の standoff + 1.0）


def _end_ext(model: ScaffoldModel, edge_index: int, side: int, end_ext_mm: float) -> float:
    """立面の切断線を面の端（始点 -1・終点 +1）から延ばす長さ。入隅の端は隣の面の幕の手前まで."""
    verts = [(float(x), float(y)) for x, y in model.plan.outline.vertices]
    n = len(verts)
    if n < 3:
        return end_ext_mm
    a, b = verts[edge_index], verts[(edge_index + 1) % n]
    if side < 0:
        p, q = verts[(edge_index - 1) % n], a                 # 前の辺 p→a、この辺 a→b
        cross = (a[0] - p[0]) * (b[1] - a[1]) - (a[1] - p[1]) * (b[0] - a[0])
    else:
        q = verts[(edge_index + 2) % n]                       # この辺 a→b、次の辺 b→q
        cross = (b[0] - a[0]) * (q[1] - b[1]) - (b[1] - a[1]) * (q[0] - b[0])
    if cross >= 0:                                            # 出隅（反時計回りで左折）
        return end_ext_mm
    adj = (edge_index + side) % n
    so = next((float(e.standoff) for e in model.plan.edges if e.edge_index == adj), 300.0)
    return min(end_ext_mm, so + CURTAIN_BEHIND_MM / 2.0)


def section_specs(model: ScaffoldModel, prefix: str = "足場",
                  clearance_mm: float = CLEARANCE_MM, end_ext_mm: float = END_EXT_MM) -> list[SectionSpec]:
    """面ごとの切断線（mm, 絶対座標）と奥行き.

    足場ラインの配置と同じ座標系: 面の始点支柱 start_post → 終点支柱 end_post が内側建地列。
    外形は反時計回りなので躯体は進行方向の左、外側建地列は右（局所 y=-rowW）。
    """
    verts = [(float(x), float(y)) for x, y in model.plan.outline.vertices]
    row_w = float(model.post_row_spacing_mm)
    out: list[SectionSpec] = []
    for ep in model.plan.edges:
        sx, sy = ep.start_post
        ex, ey = ep.end_post
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        ux, uy = dx / length, dy / length
        # 右手（外側）と左手（躯体側）
        ox, oy = uy, -ux
        nx, ny = -ox, -oy
        off = row_w + clearance_mm
        # 入隅の端は延ばしすぎない。隣の面の足場ラインが躯体面の 1m 奥に立てる幕（3d.gdl）を切ると、
        # 切り口が縦の線になって立面図に出た（L 字の入隅の面、2026-10-23 実機）
        ext_s = _end_ext(model, ep.edge_index, -1, end_ext_mm)
        ext_e = _end_ext(model, ep.edge_index, +1, end_ext_mm)
        s = (sx + ox * off - ux * ext_s, sy + oy * off - uy * ext_s)
        e = (ex + ox * off + ux * ext_e, ey + oy * off + uy * ext_e)
        # 奥行き: 切断線から躯体の最も遠い頂点まで
        far = max(((vx - s[0]) * nx + (vy - s[1]) * ny) for vx, vy in verts) if verts else off
        depth = max(far, off) + DEPTH_MARGIN_MM
        face = model.face_name(ep.edge_index)
        out.append(SectionSpec(face, section_name(prefix, face), s, e, depth, length + ext_s + ext_e, ep.edge_index))
    return out


def drawing_plan(section_length_mm: float, scaffold_height_mm: float, paper_mm: tuple[float, float],
                 margins_mm: tuple[float, float, float, float] = (20.0, 20.0, 20.0, 20.0),
                 title_band_mm: float = 60.0) -> DrawingPlan:
    """用紙に収まる縮尺（1/100 から）と図面の位置（用紙の左下から mm）.

    margins は (左, 上, 右, 下)。下に図面タイトル帯（title_band）を空ける。
    """
    pw, ph = paper_mm
    left, top, right, bottom = margins_mm
    usable_w = pw - left - right - 10.0
    usable_h = ph - top - bottom - title_band_mm
    scale = SCALE_CANDIDATES[-1]
    for cand in SCALE_CANDIDATES:
        if section_length_mm / cand <= usable_w and (scaffold_height_mm + 2000.0) / cand <= usable_h:
            scale = cand
            break
    return DrawingPlan(scale=scale, position_mm=(left + 10.0, bottom + title_band_mm), paper_mm=paper_mm)


def sheet_layout_name(prefix: str, k: int = 0) -> str:
    """立面図のレイアウト名. 2面ごとに1枚（利用者の指定 2026-10-23）なので k 枚目は「… 足場立面図 k」（1枚だけなら番号なし）."""
    return f"{prefix} 足場立面図" + (f" {k}" if k else "")


FACES_PER_SHEET = 2   # 立面図は1枚に2面（利用者の指定 2026-10-23: 立面は1枚の図面に2面毎）


def sheet_layout_names(prefix: str, n: int = 8) -> list[str]:
    """片付け用: 1枚の名前と番号付きの名前."""
    return [sheet_layout_name(prefix)] + [sheet_layout_name(prefix, k) for k in range(1, n + 1)]


def scaffold_layout_names(prefix: str, faces: Iterable[str] = ()) -> list[str]:
    """片付け用: この工事の足場のレイアウトの名前すべて（面ごとの立面・2面ごとの立面・平面・詳細・断面）.
    断面図は A-A などごと（cross_sections.cross_sheet_name）と、入らず面ごとに分けた「… 1」「… 2」も."""
    cross = [f"{prefix} 足場断面図"] + [f"{prefix} 足場断面図 {c}-{c}{k}" for c in "ABCDEFGH"
                                     for k in ("", " 1", " 2", " 3", " 4")]
    return ([layout_name(prefix, f) for f in faces] + sheet_layout_names(prefix)
            + [f"{prefix} 足場平面図", f"{prefix} 足場詳細図"] + cross)


@dataclass
class SheetPlan:
    scale: int
    positions_mm: list[tuple[float, float]]   # 各面の図面の左下（用紙 mm、specs と同じ順）
    paper_mm: tuple[float, float]


# 注記ぶんの余白（モデル mm）。左は Archicad のフロアマーカー、右は高さの注記と寸法、上は面の注記
NOTE_EXTRA_W_MM = 9000.0
NOTE_EXTRA_H_MM = 8000.0


def arrange_boxes(boxes_mm: list[tuple[float, float]], paper_mm: tuple[float, float],
                  margins_mm: tuple[float, float, float, float] = (20.0, 20.0, 20.0, 20.0),
                  title_band_mm: float = 60.0, gap_mm: float = 25.0, caption_mm: float = 15.0,
                  scales: Iterable[int] = SCALE_CANDIDATES, max_scale: int = 200) -> Optional[SheetPlan]:
    """図面の箱（モデル mm の幅・高さ）を1枚の用紙に並べる縮尺と位置。左上から右へ、入らなければ次の行.

    1/100 から試し、1/max_scale より小さくなるなら None（1/300 の立面では部材が読めない）。
    各図面の下に図面タイトルの帯（caption）を見込む。位置は図面の左下（用紙 mm）。
    """
    pw, ph = paper_mm
    left, top, right, bottom = margins_mm
    usable_w = pw - left - right - 10.0
    usable_h = ph - top - bottom - title_band_mm
    for scale in scales:
        if scale > max_scale:
            break
        x = 0.0
        rows: list[list[tuple[int, float]]] = [[]]
        ok = True
        for i, (bw, _bh) in enumerate(boxes_mm):
            w = bw / scale
            if w > usable_w:
                ok = False
                break
            if rows[-1] and x + w > usable_w:
                rows.append([])
                x = 0.0
            rows[-1].append((i, x))
            x += w + gap_mm
        if not ok:
            continue
        row_h = [max(boxes_mm[i][1] / scale for i, _ in row) + caption_mm for row in rows]
        if sum(row_h) + (len(rows) - 1) * gap_mm > usable_h:
            continue
        positions: list[tuple[float, float]] = [(0.0, 0.0)] * len(boxes_mm)
        y_cursor = ph - top
        for row, h in zip(rows, row_h):
            y_cursor -= h
            for i, x0 in row:
                positions[i] = (left + 10.0 + x0, y_cursor + caption_mm)
            y_cursor -= gap_mm
        return SheetPlan(scale=scale, positions_mm=positions, paper_mm=paper_mm)
    return None


def arrange_on_one_sheet(lengths_mm: list[float], scaffold_height_mm: float, paper_mm: tuple[float, float],
                         margins_mm: tuple[float, float, float, float] = (20.0, 20.0, 20.0, 20.0),
                         title_band_mm: float = 60.0, gap_mm: float = 25.0, caption_mm: float = 15.0,
                         max_scale: int = 200, extra_w_mm: float = 0.0, extra_h_mm: float = 0.0) -> Optional[SheetPlan]:
    """全面を1枚の用紙に並べる（見積りの箱 = 切断線の長さ×(足場高さ+2m)＋注記の余白）."""
    boxes = [(length + extra_w_mm, scaffold_height_mm + 2000.0 + extra_h_mm) for length in lengths_mm]
    return arrange_boxes(boxes, paper_mm, margins_mm, title_band_mm, gap_mm, caption_mm, max_scale=max_scale)


# ---------------------------------------------------------------- 断面への注記（純粋関数）

@dataclass
class SectionNotes:
    texts: list[dict] = field(default_factory=list)                    # {"x","y","text","just"}（m、断面座標）
    lines: list[list[tuple[float, float]]] = field(default_factory=list)
    labels: list[dict] = field(default_factory=list)                   # {"beg","mid","end","text"}（引出線つき）
    # 寸法ツールの寸法（利用者の指定 2026-10-23: 立面図・断面図は寸法に）。{"points": 測る点, "ref": 寸法線の通る点,
    # "dir": 寸法線の向き, "fallback": {"lines", "texts"}}。点は見えない所に置く「寸法の芯」の線の頂点に取り、
    # 寸法を置けなければ fallback（線と文字で描いた寸法）を描く
    dims: list[dict] = field(default_factory=list)

    def shifted(self, dy: float) -> "SectionNotes":
        """全体を上へ dy ずらした写し（下の屋根の上に建てた足場）."""
        mv = lambda pts: [(x, y + dy) for x, y in pts]
        return SectionNotes(
            texts=[{**t, "y": t["y"] + dy} for t in self.texts],
            lines=[mv(pts) for pts in self.lines],
            labels=[{**lb, "beg": (lb["beg"][0], lb["beg"][1] + dy), "mid": (lb["mid"][0], lb["mid"][1] + dy),
                     "end": (lb["end"][0], lb["end"][1] + dy)} for lb in self.labels],
            dims=[{**d, "points": mv(d["points"]), "ref": (d["ref"][0], d["ref"][1] + dy),
                   "fallback": {"lines": [mv(pts) for pts in d["fallback"]["lines"]],
                                "texts": [{**t, "y": t["y"] + dy} for t in d["fallback"]["texts"]]}}
                  for d in self.dims])


def section_axis(spec: SectionSpec) -> tuple[float, float]:
    dx, dy = spec.end_mm[0] - spec.start_mm[0], spec.end_mm[1] - spec.start_mm[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def section_x(spec: SectionSpec, p_mm: tuple[float, float]) -> float:
    """平面の点 → 断面図ウィンドウの横座標（m）.

    断面の横軸は「切断線の向きへの平面座標の射影」（実機で確認: 南面＝+x の断面では x そのまま、
    北面＝-x の断面では -x）。縦軸は標高（m）。
    """
    ux, uy = section_axis(spec)
    return (p_mm[0] * ux + p_mm[1] * uy) / 1000.0


TIE_MARK_RADII_M = (0.12, 0.065)     # 立面の壁つなぎ記号 ◎ の外輪・内輪（モデル m。1/100 で径2.4mm）


def circle_points(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
    """円を n 角形の閉じた折れ線で（最初の点に戻る）."""
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return pts + [pts[0]]


def tie_marks(ep, spec: SectionSpec, wall_ties) -> list[tuple[float, float]]:
    """この面の壁つなぎの断面座標（横＝切断線方向への射影 m、縦＝高さ m）."""
    sx, sy = ep.start_post
    ex, ey = ep.end_post
    length = math.hypot(ex - sx, ey - sy) or 1.0
    ux, uy = (ex - sx) / length, (ey - sy) / length
    out = []
    for t in wall_ties:
        if t.edge_index != ep.edge_index:
            continue
        p = (sx + ux * t.position_mm, sy + uy * t.position_mm)
        out.append((section_x(spec, p), t.height_mm / 1000.0))
    return out


# 寸法・注記の位置（断面座標 m。1/100 で 1m＝10mm）。足場から離して、部材と寸法線が重ならないように
# （参考: micotoworks「足場図面の書き方」の立面・平面。寸法は足場の外に離し、部材名は引出線のラベルで）
SPAN_DIM_OFFSET_M = 1.2       # 天端からスパン寸法の寸法線まで
TOTAL_DIM_OFFSET_M = 2.0      # 天端から全長の寸法線まで
LEVEL_DIM_OFFSET_M = 1.5      # 外側（右端の建地）から高さの寸法線（1本目＝段の高さ）まで
CHAIN_GAP_M = 1.8             # 高さの寸法線の間隔（段の高さ → 支柱の高さ → 足場の高さ）
HEIGHT_DIM_OFFSET_M = LEVEL_DIM_OFFSET_M + 2 * CHAIN_GAP_M   # 外側から足場の高さの寸法線まで
LABEL_ROW_BOTTOM_M = -1.6     # 下段のラベル（GL の下）
LABEL_ROW_TOP_OFFSET_M = 3.2  # 上段のラベル（全長の寸法の上）
HEADER_OFFSET_M = 4.3         # 面の要約（上段のラベルの上）
TICK_M = 0.1                  # 寸法の目盛り（斜めの短線の半長）


def _tick(x: float, y: float) -> list[tuple[float, float]]:
    """寸法の目盛り（右上がりの短い斜線）."""
    return [(x - TICK_M, y - TICK_M), (x + TICK_M, y + TICK_M)]


def height_chains(e) -> list[tuple[str, list[float], list[str]]]:
    """高さの寸法の3本（利用者の指定 2026-10-23: 立面図・断面図は寸法に、層の高さは不要、段の高さ・支柱の高さ・
    全体の足場の高さ）. [(見出し, 目盛りの高さ mm, 区間の文字)]。区間の文字は目盛りの間の数.

    - 段の高さ: GL・各作業床・天端（支柱の上端）
    - 支柱の高さ: GL・ジャッキの上・支柱の継ぎ目・天端（区間は ジャッキの繰出し・支柱の長さ）
    - 足場の高さ: GL・天端
    """
    top = float(e.total_height)
    steps = [0.0] + [float(h) for h in e.level_heights if 0.0 < float(h) < top - 1.0] + [top]
    jack = float(e.jack_extension)
    posts = [0.0] + ([jack] if jack > 1.0 else [])
    for ln in e.posts:
        posts.append(posts[-1] + float(ln))
    post_texts = ([f"ジャッキ{jack:.0f}"] if jack > 1.0 else []) + [f"{float(ln):.0f}" for ln in e.posts]
    return [("段の高さ", steps, [f"{b - a:.0f}" for a, b in zip(steps, steps[1:])]),
            ("支柱の高さ", posts, post_texts),
            ("足場の高さ", [0.0, top], [f"{top:.0f}"])]


def draw_height_chains(out: "SectionNotes", e, x_scaffold: float, x_first: float, side: float,
                       text_scale: float = 100.0) -> float:
    """高さの寸法を3本（寸法ツール）、足場の外（side=+1 は右、-1 は左）に x_first から CHAIN_GAP_M おきに置く.
    測る点は外側の建地の線（x_scaffold）に取る。見出しは天端の上、ジャッキの繰出しは GL の下に文字で。
    寸法を置けないときの描き方（線・目盛り・区間の数）は fallback に持つ。戻り値はいちばん外の寸法線の x."""
    th = 0.25 * text_scale / 100.0
    xc = x_first
    for k, (title, marks, texts) in enumerate(height_chains(e)):
        xc = x_first + side * k * CHAIN_GAP_M
        top = marks[-1] / 1000.0
        fb = {"lines": [[(xc, 0.0), (xc, top)]], "texts": []}
        for h in marks:
            y = h / 1000.0
            fb["lines"].append(_tick(xc, y))
            fb["lines"].append([(x_scaffold + side * 0.1 if k == 0 else xc - side * (CHAIN_GAP_M - 0.15), y),
                                (xc - side * 0.15, y)])         # 補助線（足場から、または内側の寸法線から）
        for (a, b), text in zip(zip(marks, marks[1:]), texts):
            if text.startswith("ジャッキ"):
                # ジャッキの区間は短い（150 など）ので、名前と数は GL の下、寸法線の真下に（寸法でも文字を添える）
                out.texts.append({"x": xc - label_text_width_m(text, th) / 2.0, "y": -0.45, "text": text,
                                  "just": "Left", "chain": title})
                continue
            gx = xc - side * 0.15
            if side >= 0:
                gx -= label_text_width_m(text, th)               # 右寄せが効かない版があるので幅を見積もって左寄せ
            fb["texts"].append({"x": gx, "y": (a + b) / 2000.0, "text": text, "just": "Left", "gap": True,
                                "chain": title})
        if k == 0:
            # 段の番号（例の立面図: 段の高さの寸法線の外に 1・2・3…）。作業床の高さに
            for n_lv, h in enumerate(marks[1:-1], start=1):
                num = str(n_lv)
                out.texts.append({"x": xc + side * 0.25 - (label_text_width_m(num, th) if side < 0 else 0.0),
                                  "y": h / 1000.0 + 0.05, "text": num, "just": "Left", "level_no": n_lv})
        out.dims.append({"points": [(x_scaffold, h / 1000.0) for h in marks], "ref": (xc, 0.0), "dir": (0.0, 1.0),
                         "chain": title, "values": [b - a for a, b in zip(marks, marks[1:])], "fallback": fb})
        out.texts.append({"x": xc - label_text_width_m(title, th) / 2.0, "y": top + 0.35, "text": title,
                          "just": "Left", "chain_title": True})
    return xc


def section_annotations(model: ScaffoldModel, spec: SectionSpec, terrain=None,
                        label_pitch_m: float = 0.7, stair_plan=None, text_scale: float = 100.0) -> SectionNotes:
    """断面立面に置く注記: GL線・寸法（スパン・全長・段の高さ・支柱の高さ・足場の高さ）・部材名のラベル・面の要約."""
    ep = next(e for e in model.plan.edges if e.edge_index == spec.edge_index)
    e = model.elevation_of(ep.edge_index)
    row_w = float(model.post_row_spacing_mm) / 1000.0
    a, b = section_x(spec, ep.start_post), section_x(spec, ep.end_post)
    lo, hi = min(a, b) - row_w, max(a, b) + row_w
    top = float(e.total_height) / 1000.0
    out = SectionNotes()
    # GL（敷地に高低差があれば基準高さ。脚ごとの地盤はジャッキ量一覧）
    out.lines.append([(lo - 1.0, 0.0), (hi + 1.0, 0.0)])
    gl_note = "GL±0"
    diff = float(getattr(terrain, "gl_difference_mm", 0.0) or 0.0) if terrain is not None else 0.0
    if diff > 1.0:
        gl_note += f"（基準。敷地高低差 {diff:.0f}）"
    # 高さの寸法（右に離して縦の寸法線を3本: 段の高さ・支柱の高さ・足場の高さ。層の高さの文字は書かない）
    xd = draw_height_chains(out, e, hi, hi + LEVEL_DIM_OFFSET_M, 1.0, text_scale)
    out.texts.append({"x": xd + 0.25, "y": 0.05, "text": gl_note, "just": "Left"})
    # スパン寸法と全長（寸法ツール。天端から離した寸法線、測る点は天端の支柱の位置）
    sgn = 1.0 if b >= a else -1.0
    ys = top + SPAN_DIM_OFFSET_M
    yt = top + TOTAL_DIM_OFFSET_M
    xs = [a + sgn * v / 1000.0 for v in _cumulative(ep.spans)]
    fb = {"lines": [[(min(xs), ys), (max(xs), ys)]], "texts": []}
    for k, x in enumerate(xs):
        fb["lines"].append(_tick(x, ys))
        fb["lines"].append([(x, top + 0.15), (x, ys + 0.15)])          # 補助線
        if k < len(ep.spans):
            fb["texts"].append({"x": (x + xs[k + 1]) / 2.0, "y": ys + 0.12, "text": f"{ep.spans[k]:.0f}",
                                "just": "Center", "span": True})
    out.dims.append({"points": [(x, top) for x in sorted(xs)], "ref": (min(xs), ys), "dir": (1.0, 0.0),
                     "chain": "スパン", "values": [float(v) for v in (ep.spans if sgn > 0 else list(ep.spans)[::-1])],
                     "fallback": fb})
    fb = {"lines": [[(min(xs), yt), (max(xs), yt)], _tick(min(xs), yt), _tick(max(xs), yt),
                    [(min(xs), ys + 0.15), (min(xs), yt + 0.15)], [(max(xs), ys + 0.15), (max(xs), yt + 0.15)]],
          "texts": [{"x": (min(xs) + max(xs)) / 2.0, "y": yt + 0.12, "text": f"{sum(ep.spans):.0f}",
                     "just": "Center", "total": True}]}
    out.dims.append({"points": [(min(xs), top), (max(xs), top)], "ref": (min(xs), yt), "dir": (1.0, 0.0),
                     "chain": "全長", "values": [float(sum(ep.spans))], "fallback": fb})
    # 壁つなぎの位置に ◎（2重の円）。3D の部品には持たせず、立面図の注記として描く
    for cx, cy in tie_marks(ep, spec, model.wall_ties):
        for r in TIE_MARK_RADII_M:
            out.lines.append(circle_points(cx, cy, r))
    # 部材名のラベル（引出線つき。下段は GL の下、上段は寸法の上）
    out.labels.extend(section_labels(model, spec, ep, stair_plan, lo, hi, top, text_scale=text_scale))
    # 面の要約（ラベルの上に2行。上段のラベルが何段かになればその上）
    head_y = max([top + HEADER_OFFSET_M] + [lb["end"][1] + 0.9 * text_scale / 100.0 for lb in out.labels
                                             if lb["end"][1] > top])
    ties = sum(1 for t in model.wall_ties if t.edge_index == ep.edge_index)
    mod = "インチ" if model.master.module == "inch" else "メートル"
    from .master import SERIES_LABELS

    kind = SERIES_LABELS.get(model.master.series_id, model.master.series_id)
    line1 = (f"{spec.face_name} 足場立面図　{kind}（{mod}）・作業層 {e.n_levels}層・"
             f"階高 {model.master.floor_height}")
    line2 = (f"壁つなぎ {ties}箇所（◎印）・離れ {ep.standoff:.0f}・ジャッキ繰出し {e.jack_extension:.0f}")
    out.texts.append({"x": lo, "y": head_y + label_pitch_m * text_scale / 100.0, "text": line1, "just": "Left"})
    out.texts.append({"x": lo, "y": head_y, "text": line2, "just": "Left"})
    base = float(getattr(model, "base_height_mm", 0.0) or 0.0) / 1000.0
    if base:
        # 下の屋根の上に建てた足場（セットバックの上の部分）。注記の高さは立つ面からなので、断面の標高へずらす
        out = out.shifted(base)
        for t in out.texts:
            if t["text"].startswith("GL±0"):
                t["text"] = f"足場の立つ面（下の屋根）GL+{base * 1000:.0f}"
    return out


def _cumulative(spans) -> list[float]:
    out = [0.0]
    for sp in spans:
        out.append(out[-1] + float(sp))
    return out


def label_text_width_m(text: str, h: float) -> float:
    """ラベル文字の幅の見積り（全角1字＝文字高、半角＝0.55倍）."""
    return sum(1.15 * h if ord(c) > 0x7F else 0.65 * h for c in text)


def section_labels(model: ScaffoldModel, spec: SectionSpec, ep, stair_plan, lo: float, hi: float,
                   top: float, text_scale: float = 100.0, text_height_mm: float = 2.5) -> list[dict]:
    """部材名のラベル（引出線の先＝部材の位置、文字は下段か上段に左から順に並べる）.

    返す要素: {"beg": (x, y) 部材, "mid": (x, y) 折れ点, "end": (x, y) 文字, "text": 部材名}。
    階段室・開口部のスパンは避けて、普通のスパンの部材を指す。
    """
    e = model.elevation_of(ep.edge_index)
    m = model.master
    sgn = 1.0 if section_x(spec, ep.end_post) >= section_x(spec, ep.start_post) else -1.0
    a = section_x(spec, ep.start_post)
    xs = _cumulative(ep.spans)
    towers = [t for t in (getattr(stair_plan, "towers", None) or []) if t.edge_index == ep.edge_index]
    plain = [i for i in range(len(ep.spans))
             if not any(xs[i] < t.end_mm - 1 and xs[i + 1] > t.start_mm + 1 for t in towers)]
    if not plain:
        plain = list(range(len(ep.spans)))

    def at(i: int, frac: float = 0.5) -> float:
        i = plain[min(i, len(plain) - 1)]
        return a + sgn * (xs[i] + ep.spans[i] * frac) / 1000.0

    def name(cat: str, fallback: str) -> str:
        p = next(iter(m.by_category(cat)), None)
        return f"{fallback} {p.model_no}" if p is not None and p.model_no else fallback

    lv = [float(h) / 1000.0 for h in e.level_heights]
    first = float(e.first_ledger_height) / 1000.0
    rail = float(model.guard_rail_height_mm) / 1000.0
    mid = float(model.midrail_height_mm) / 1000.0
    items: list[tuple[float, float, str]] = []      # (x, y, 文字)
    ties = tie_marks(ep, spec, model.wall_ties)
    if ties:
        tx, ty = min(ties, key=lambda p: (p[1], abs(p[0] - lo)))
        items.append((tx, ty, name("壁つなぎ", "壁つなぎ")))
    items.append((at(0, 0.3), first, "根がらみ"))
    items.append((a + sgn * xs[plain[0]] / 1000.0, float(e.jack_extension) / 2000.0, "ジャッキベース"))
    if lv:
        items.append((at(1), lv[0] + 0.03, "作業床（踏板）・幅木"))
        advance = model.config.guard_rail_type == "先行手すり" and not m.is_frame
        if advance:
            items.append((at(2), lv[-1] + rail, "先行手すり（手すり＋斜材）"))
        else:
            items.append((at(2), lv[-1] + rail, "手すり"))
            items.append((at(3), lv[-1] + mid, "中桟"))
    from .attachments import net_heights_mm
    nets = net_heights_mm(model)
    if nets:
        items.append((at(3, 0.0), nets[0] / 1000.0,
                      "水平ネット・ネットブラケット" if model.config.net_brackets else "水平ネット"))
    outside = bool(getattr(stair_plan, "outside", False))
    for t in towers[:1]:
        start = t.start_mm
        if outside:
            # 外付けは区間の1つ目が上り口。階段はその次のスパンから
            start += next((sp for x0, sp in zip(xs, ep.spans) if abs(x0 - t.start_mm) < 1), 0.0)
        t0 = a + sgn * start / 1000.0
        sp0 = next((sp for x0, sp in zip(xs, ep.spans) if abs(x0 - start) < 1), 1800.0) / 1000.0
        if len(lv) >= 1:
            items.append((t0 + sgn * sp0 * 0.5, (first + lv[0]) / 2.0, name("階段", "昇降階段")))
            items.append((t0 + sgn * sp0 * 0.25, (first + lv[0]) / 2.0 + 0.90,
                          name("階段手摺", "階段手摺") + ("（両側）" if outside else "")))
            # 1層目の開口の長手に沿う開口部手摺（SG918SW、高さ922）＋開口部幅木（3d.gdl と同じ。上がり口側で折れて端も塞ぐ）。
            # 外付けには付けない
            if not outside:
                items.append((t0 + sgn * sp0 * 0.5, lv[0] + 0.92, name("階段開口部手摺", "階段開口部手摺") + "・幅木"))
    bottom = sorted([it for it in items if it[1] < top / 2.0], key=lambda it: it[0])
    upper = sorted([it for it in items if it[1] >= top / 2.0], key=lambda it: it[0])
    h = text_height_mm * text_scale / 1000.0                      # 文字高（モデル m）
    pitch = h * 2.8
    out = []
    for row, y0, step in ((bottom, LABEL_ROW_BOTTOM_M, -pitch), (upper, top + LABEL_ROW_TOP_OFFSET_M, pitch)):
        ends: list[float] = []                                     # 段ごとの右端
        for x, y, text in row:
            w = label_text_width_m(text, h) + 0.4 + 1.2 * h            # 引出しの横線＋枠の余白
            pref = x - 0.5
            k = 0
            while True:
                if k == len(ends):
                    ends.append(-1e9)
                xe = max(pref, ends[k] + 0.6 * h / 0.25)
                # 部材の近くに置けない（右へ 2.5m 以上押される・図の右端を越える）なら次の段へ
                if (xe + w <= hi + 4.0 and xe - pref <= 2.5) or k >= 3:
                    break
                k += 1
            ends[k] = xe + w
            y_row = y0 + step * k
            out.append({"beg": (x, y), "mid": (xe, y_row), "end": (xe + 0.4, y_row), "text": text})
    return out


def open_section_window(client, section_item_guid: str, tries: int = 3, wait_s: float = 1.0) -> bool:
    """断面図のウィンドウを前面に出し、本当に断面図が前面になったかを確かめる（なれば True）."""
    import time

    for _ in range(max(1, tries)):
        try:
            client.tapir("ChangeWindow", {"navigatorItemId": {"guid": section_item_guid}})
        except Exception:
            pass
        if client.current_window_type() == "Section":
            return True
        time.sleep(wait_s)
    return False


def write_section_dims(client, dims: list[dict]) -> tuple[int, list[dict]]:
    """寸法ツールの寸法を置く（現在の断面図ウィンドウ）. 測る点は寸法の芯の線（頂点＝点）に取る.
    戻り値は (置いた要素の数, 置けなかった寸法の fallback の並び)."""
    if not dims:
        return 0, []
    try:
        r = client.tapir("CreatePolylines", {"polylinesData": [
            {"coordinates": [{"x": x, "y": y} for x, y in d["points"]]} for d in dims]})
        cores = [el.get("elementId") for el in r.get("elements", [])]
    except Exception:
        return 0, [d["fallback"] for d in dims]
    n = sum(1 for c in cores if c)
    data, owner = [], []
    for d, core in zip(dims, cores):
        if not core:
            continue
        data.append({"referencePoint": {"x": d["ref"][0], "y": d["ref"][1]},
                     "direction": {"x": d["dir"][0], "y": d["dir"][1]},
                     "witnessPoints": [{"elementId": core, "inIndex": i} for i in range(1, len(d["points"]) + 1)]})
        owner.append(d)
    made = []
    if data:
        try:
            made = client.tapir("CreateAssociativeDimensions", {"dimensionsData": data}).get("elements", [])
        except Exception:
            made = []
    ok = {id(d) for d, el in zip(owner, made) if "elementId" in el}
    n += len(ok)
    return n, [d["fallback"] for d in dims if id(d) not in ok]


def write_section_notes(client, notes: SectionNotes, text_height_mm: float = 2.5) -> int:
    """現在の断面図ウィンドウに注記を置く（ChangeWindow で開いてから呼ぶ）。置いた数を返す.
    寸法は寸法ツールで置き、置けなかった分だけ線と文字で描く."""
    n, fallback = write_section_dims(client, notes.dims)
    if fallback:
        notes = SectionNotes(texts=list(notes.texts) + [t for fb in fallback for t in fb["texts"]],
                             lines=list(notes.lines) + [pts for fb in fallback for pts in fb["lines"]],
                             labels=notes.labels)
    if notes.texts:
        r = client.tapir("CreateTexts", {"textsData": [
            {"coordinate": {"x": t["x"], "y": t["y"], "z": 0.0}, "text": t["text"], "height": text_height_mm,
             "justification": t.get("just", "Left")} for t in notes.texts]})
        n += sum(1 for el in r.get("elements", []) if "elementId" in el)
    if notes.lines:
        r = client.tapir("CreatePolylines", {"polylinesData": [
            {"coordinates": [{"x": x, "y": y} for x, y in pts]} for pts in notes.lines]})
        n += sum(1 for el in r.get("elements", []) if "elementId" in el)
    if notes.labels:
        n += write_section_labels(client, notes.labels, text_height_mm)
    return n


def write_section_labels(client, labels: list[dict], text_height_mm: float = 2.5) -> int:
    """部材名を Archicad のラベル（文字ラベル・引出線つき）で置く。置いた数を返す."""
    return len(create_labels(client, labels, text_height_mm, fallback=True))


def create_labels(client, labels: list[dict], text_height_mm: float = 2.5, fallback: bool = False,
                  floor_index: Optional[int] = None) -> list[str]:
    """文字ラベル（引出線の矢先 beg＝部材、折れ点 mid、文字 end）を現在のウィンドウに置き、GUID を返す.

    文字の大きさが指定できなければラベルツールの既定で置く。fallback=True ならラベルが作れない版でも
    折れ線＋文字で同じ見た目に描く（その場合 GUID は返さない）。
    """
    if not labels:
        return []

    # 引出線はプロジェクトのラベルツールの既定に任せない（既定で引出線が無いプロジェクトでは、文字が部材の上に
    # 重なった。2026-10-19 実機）。折れ線の引出線＋矢印、枠なし（参考図と同じ下線つき文字の見え方）
    leader = {"hasLeaderLine": True, "leaderShape": "Segmented", "framed": False,
              "arrowVisible": True, "arrowType": "FullArrow15"}

    def data(with_style: bool, with_leader: bool) -> list[dict]:
        out = []
        for lb in labels:
            d = {"labelClass": "Text", "text": lb["text"],
                 "begCoordinate": {"x": lb["beg"][0], "y": lb["beg"][1]},
                 "midCoordinate": {"x": lb["mid"][0], "y": lb["mid"][1]},
                 "endCoordinate": {"x": lb["end"][0], "y": lb["end"][1]}}
            if with_style:
                d["style"] = {"height": text_height_mm}
            if with_leader:
                d["leaderLine"] = dict(leader)
            if floor_index is not None:
                # 省くと「いまのフロア」に入る。断面を開いたりしたあとは足場と別のフロアになり、
                # 平面図に出なかった（2026-10-19 実機: 足場は 0 階、ラベルは 2 階）
                d["floorInd"] = floor_index
            out.append(d)
        return out

    for with_style, with_leader in ((True, True), (False, True), (True, False), (False, False)):
        try:
            r = client.tapir("CreateLabels", {"labelsData": data(with_style, with_leader)})
        except Exception:
            continue
        guids = [el["elementId"]["guid"] for el in r.get("elements", []) if "elementId" in el]
        if guids:
            return guids
    if fallback:
        client.tapir("CreatePolylines", {"polylinesData": [
            {"coordinates": [{"x": x, "y": y} for x, y in (lb["beg"], lb["mid"], lb["end"])]} for lb in labels]})
        client.tapir("CreateTexts", {"textsData": [
            {"coordinate": {"x": lb["end"][0], "y": lb["end"][1] + 0.05, "z": 0.0}, "text": lb["text"],
             "height": text_height_mm, "justification": "Left"} for lb in labels]})
    return []


# ---------------------------------------------------------------- ナビゲータツリー

def walk_tree(node: dict, depth: int = 0) -> Iterable[dict]:
    """GetNavigatorItemTree の応答を平らに（type, name, guid, depth）."""
    yield {"type": node.get("type"), "name": node.get("name", ""), "prefix": node.get("prefix", ""),
           "guid": (node.get("navigatorItemId") or {}).get("guid", ""), "depth": depth}
    for ch in node.get("children", []) or []:
        yield from walk_tree(ch.get("navigatorItem", ch), depth + 1)


def find_items(tree: dict, item_type: str, name: Optional[str] = None, contains: Optional[str] = None) -> list[dict]:
    out = []
    for it in walk_tree(tree):
        if it["type"] != item_type:
            continue
        if name is not None and it["name"] != name:
            continue
        if contains is not None and contains not in it["name"]:
            continue
        out.append(it)
    return out


def pick_master_layout(masters: list[dict], prefer: str = "A1") -> Optional[dict]:
    """マスターレイアウト（用紙）。A1 を優先、無ければ最初のもの（フォルダ「マスタ」は除く）."""
    cands = [m for m in masters if m["name"] not in ("マスタ", "マスターレイアウト", "")]
    for m in cands:
        if prefer in m["name"]:
            return m
    return cands[0] if cands else None


# ---------------------------------------------------------------- Tapir 操作

def story_items(tree: dict) -> list[dict]:
    return find_items(tree, "StoryItem")


def activate_floor_plan(client) -> bool:
    """平面図のウィンドウを前面にする（Tapir 1.7.0 の ChangeWindow）.

    断面の作成・削除・スラブの作成は平面図が前面のときだけ通る。ツールバーがレイアウトを作ると
    Archicad はそのタブを前面にするので、次の実行がそのままだと "Failed to create section" で止まる。
    """
    try:
        if client.current_window_type() == "FloorPlan":
            return True
        stories = client.tapir("GetStories", {})
        act = int(stories.get("actStory", 0))
        items = story_items(_tree(client, "ProjectMap"))
        hit = [it for it in items if str(it.get("prefix", "")).strip() == str(act)]
        target = hit[0] if hit else (items[0] if items else None)
        if target is None:
            return False
        client.tapir("ChangeWindow", {"navigatorItemId": {"guid": target["guid"]}})
        return client.current_window_type() == "FloorPlan"
    except Exception:
        return False


def _tree(client, map_id: str) -> dict:
    return client.tapir("GetNavigatorItemTree", {"navigatorMapId": map_id})["navigatorItemTree"]


def _delete_items(client, guids: list[str]) -> int:
    if not guids:
        return 0
    client.tapir("DeleteNavigatorItems", {"navigatorItemIds": [{"navigatorItemId": {"guid": g}} for g in guids]})
    return len(guids)


def remove_elevations(client, names: Iterable[str], layout_names: Iterable[str],
                      section_guids: Iterable[str] = ()) -> tuple[int, int, list[str]]:
    """前回の断面（要素 GUID）とレイアウト（名前）を消す。戻り値は (断面, レイアウト, 消せなかった断面名).

    断面のナビゲータ項目は DeleteNavigatorItems で消せない（実機で "Failed to delete navigator item"）。
    断面は CutPlane 要素として DeleteElements で消えるので、配置時に控えた GUID で消す。
    GUID が無い（控えが消えた）同名の断面は残るので名前を返して注意に出す。
    """
    names = set(names)
    layout_names = set(layout_names)
    guids = [g for g in section_guids if g]
    n_sec = 0
    if guids:
        _delete_sections(client, guids)
        n_sec = len(guids)
    lb = _tree(client, "LayoutBook")
    lays = [it["guid"] for it in walk_tree(lb) if it["type"] == "LayoutItem" and it["name"] in layout_names]
    n_lay = _delete_items(client, lays)
    pm = _tree(client, "ProjectMap")
    left = [it["name"] for it in walk_tree(pm) if it["type"] == "SectionItem" and it["name"] in names]
    return n_sec, n_lay, left


def remove_all_scaffold_elevations(client, section_guids: Iterable[str] = (), prefix_contains: str = "足場立面") -> tuple[int, int, list[str]]:
    """控えた断面（要素）と、名前に「足場立面」を含むレイアウトを全部消す（撤去 --all 用）.

    サブセットは Archicad API で消せない（"Deleting layout subsets is not supported"）ので残る。
    戻り値は (断面, レイアウト, 残った断面名)。
    """
    lb = _tree(client, "LayoutBook")
    lays = [it["guid"] for it in walk_tree(lb) if it["type"] == "LayoutItem"
            and (prefix_contains in it["name"] or "足場平面図" in it["name"] or "足場断面図" in it["name"])]
    guids = [g for g in section_guids if g]
    if guids:
        _delete_sections(client, guids)
    n_l = _delete_items(client, lays)
    pm = _tree(client, "ProjectMap")
    secs = [it for it in walk_tree(pm) if it["type"] == "SectionItem"]
    left = [it["name"] for it in secs if prefix_contains in it["name"] or "足場断面" in it["name"]]
    n_extra = 0
    if left and all(prefix_contains in it["name"] or "足場断面" in it["name"] for it in secs):
        # 控えに無い断面（時間切れで控える前に止まった回の残骸）。断面要素と名前は API で
        # 対応が取れないが、プロジェクトの断面がすべて足場の立面なら全部消してよい
        activate_floor_plan(client)
        extra = client.tapir("GetElementsByType", {"elementType": "CutPlane"}).get("elements", [])
        if extra:
            _delete_sections(client, [e["elementId"]["guid"] for e in extra])
            n_extra = len(extra)
        left = [it["name"] for it in walk_tree(_tree(client, "ProjectMap"))
                if it["type"] == "SectionItem" and (prefix_contains in it["name"] or "足場断面" in it["name"])]
    return len(guids) + n_extra, n_l, left


def ensure_subset(client, name: str = SUBSET_NAME) -> str:
    """レイアウトブック直下のサブセット（無ければ作る）。ID を返す.

    CreateLayoutSubset は作っても ID を返せないことがある（実機で確認）ので、作った後に
    ツリーを引き直して名前で見つける。
    """
    lb = _tree(client, "LayoutBook")
    hit = find_items(lb, "SubSetItem", name=name)
    if hit:
        return hit[0]["guid"]
    books = find_items(lb, "BookItem")
    if not books:
        raise RuntimeError("レイアウトブックが見つかりません")
    client.tapir("CreateLayoutSubset", {"subsetsData": [{"name": name, "parentNavigatorItemId": {"guid": books[0]["guid"]}}]})
    lb = _tree(client, "LayoutBook")
    hit = find_items(lb, "SubSetItem", name=name)
    if not hit:
        raise RuntimeError(f"サブセット「{name}」を作れませんでした")
    return hit[0]["guid"]


def _layout_paper_mm(client, layout_item_guid: str, fallback=(841.0, 594.0)) -> tuple[tuple[float, float], tuple[float, float, float, float]]:
    """レイアウトの用紙サイズと余白（mm）。取れなければ A1 横."""
    try:
        r = client.tapir("GetLayoutSettings", {"layoutDatabaseIds": [{"navigatorItemId": {"guid": layout_item_guid}}]})
        s = (r.get("layoutSettings") or [{}])[0]
        s = s.get("layoutSettings", s)
        pw, ph = float(s.get("horizontalSize", 0)), float(s.get("verticalSize", 0))
        if pw > 0 and ph > 0:
            m = (float(s.get("leftMargin", 20)), float(s.get("topMargin", 20)), float(s.get("rightMargin", 20)), float(s.get("bottomMargin", 20)))
            return (pw, ph), m
    except Exception:
        pass
    return fallback, (20.0, 20.0, 20.0, 20.0)


def _create_layout(client, name: str, subset: str, master: Optional[dict]) -> Optional[str]:
    data = {"layoutName": name, "parentNavigatorItemId": {"guid": subset}}
    if master:
        data["masterNavigatorItemId"] = {"guid": master["guid"]}
    client.tapir("CreateLayout", {"layoutsData": [data]})
    hit = find_items(_tree(client, "LayoutBook"), "LayoutItem", name=name)
    return hit[-1]["guid"] if hit else None


def _drawing_boxes(client, made: list[dict]) -> Optional[tuple[list[tuple[float, float]], float]]:
    """置いた図面の実寸（bounds）からモデル mm の箱と、元ビューの縮尺（1/100 なら 0.01）を求める.

    図面の大きさ = モデル × 元ビューの縮尺 × 比率（ratio）。drawingScale は表示上の縮尺名で、
    大きさは変えない（実機で 1/200 を指定しても 1/100 の大きさで置かれた）。
    """
    try:
        dets = client.get_details(made)
    except Exception:
        return None
    boxes, src = [], None
    for d in dets:
        dd = d.get("details") or {}
        bnd, ds, ratio = dd.get("bounds"), float(dd.get("drawingScale") or 0), float(dd.get("ratio") or 1)
        if not bnd or ds <= 0:
            return None
        k = ds * ratio                                   # 用紙 m / モデル m
        src = ds if src is None else src
        boxes.append(((bnd["xMax"] - bnd["xMin"]) / k * 1000.0, (bnd["yMax"] - bnd["yMin"]) / k * 1000.0))
    return boxes, (src or 0.01)


def _activate(client, item_guid: str) -> None:
    try:
        client.tapir("ChangeWindow", {"navigatorItemId": {"guid": item_guid}})
    except Exception:
        pass


def refresh_scaffold_drawings(client, prefix: str) -> int:
    """この工事の立面図・断面図のレイアウトの図面を更新する（足場ラインを書き換えたあと。断面図ビューポイントは 3D からの
    投影なので、図面を更新すれば変えた足場が出る）。更新した図面の数を返す.

    朝顔の面のように全部を置き直さないボタンが使う（利用者の指定 2026-10-24: 立面も朝顔の面で一緒に直して）。
    """
    lb = _tree(client, "LayoutBook")
    lays = [it for it in find_items(lb, "LayoutItem")
            if it["name"].startswith(f"{prefix} 足場立面図") or it["name"].startswith(f"{prefix} 足場断面図")]
    n = 0
    for it in lays:
        _activate(client, it["guid"])
        try:
            els = client.tapir("GetElementsByType", {"elementType": "Drawing"}).get("elements", [])
            if els:
                client.tapir("UpdateDrawings", {"elements": els})
                n += len(els)
        except Exception:
            continue
    activate_floor_plan(client)
    return n


def _delete_drawings(client, layout_item_guid: str, made: list[dict]) -> bool:
    """図面の削除はそのレイアウトが前面のときだけ通る."""
    if not made:
        return True
    _activate(client, layout_item_guid)
    r = client.tapir("DeleteElements", {"elements": made})
    return all(x.get("success", True) for x in r.get("executionResults", []))


def _create_drawings(client, dbid, results, positions_mm, scale: int, src_scale: float,
                     kind: str = "足場立面図", layout_item_guid: str = "") -> list[dict]:
    """図面を置く。比率 = (1/scale) / 元ビューの縮尺（元が 1/100 なら 1/200 は 0.5）."""
    ratio = (1.0 / scale) / src_scale
    data = [{"navigatorItemId": {"guid": pl.section_item_guid}, "layoutDatabaseId": dbid,
             "position": {"x": pos[0] / 1000.0, "y": pos[1] / 1000.0},
             "scale": ratio, "drawingScale": float(scale), "name": f"{pl.face_name} {kind} {scale_caption(scale)}"}
            for pl, pos in zip(results, positions_mm)]
    # 1回の作成の最初の1枚が白紙になる不具合を避ける（_create_drawings_safely）
    made = []
    for pl, el in zip(results, _create_drawings_safely(client, data, layout_item_guid or (results[0].layout_item_guid
                                                                                      if results else ""))):
        pl.scale = scale
        if "elementId" in el:
            pl.drawing_guid = el["elementId"]["guid"]
            made.append(el)
        else:
            pl.drawing_guid = ""
            pl.notes.append(f"図面を置けませんでした: {el.get('error', el)}")
    if made:
        try:
            client.tapir("UpdateDrawings", {"elements": made})
        except Exception:
            pass
    return made


def scale_caption(scale: int) -> str:
    """図面名に添える縮尺（A1 の縮尺と、半分に縮めた A3 の縮尺。例の仮設計画図に倣う）."""
    return f"A1 1/{int(scale)}・A3 1/{int(scale) * 2}"


def _with_panel(margins: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """右の帯（凡例・荷重表・共通事項。sheet_panel）の分だけ右の余白を広げる."""
    from .sheet_panel import PANEL_GAP_MM, PANEL_W_MM

    return (margins[0], margins[1], margins[2] + PANEL_W_MM + PANEL_GAP_MM, margins[3])


def _write_panel(client, model, lay, paper, margins, kind: str, stair_plan=None, cuts=None,
                 top_mm: Optional[float] = None, title: str = "", extra=()) -> list[str]:
    """図面を置いたレイアウトの右の帯に書く。書けなければ注意の文を返す（図面の配置は止めない）."""
    from .sheet_panel import panel_content, write_panel

    try:
        write_panel(client, lay, paper, margins, panel_content(kind, model, stair_plan, cuts, title, extra), top_mm)
        return []
    except Exception as e:
        return [f"凡例・荷重表・共通事項を書けませんでした（{e}）"]


def panel_spot(plan: "SheetPlan", boxes_mm: list[tuple[float, float]], paper: tuple[float, float],
               margins: tuple[float, float, float, float], panel_h_mm: float, title_band_mm: float = 60.0,
               caption_mm: float = 15.0) -> Optional[float]:
    """帯を置ける上端（用紙 mm の y）. 右上が空いていれば右上、だめなら図面の下の右（表題欄の上）。どちらも無理なら None."""
    from .sheet_panel import PANEL_GAP_MM, PANEL_W_MM

    occ = [(x, y - caption_mm, x + bw / plan.scale, y + bh / plan.scale)
           for (x, y), (bw, bh) in zip(plan.positions_mm, boxes_mm)]
    x_left = paper[0] - margins[2] - PANEL_W_MM - 2.0 - PANEL_GAP_MM
    top = paper[1] - margins[1] - 4.0
    if all(o[2] <= x_left or o[1] >= top or o[3] <= top - panel_h_mm for o in occ):
        return top
    low = min([o[1] for o in occ if o[2] > x_left] + [top])
    floor = margins[3] + title_band_mm
    if low - PANEL_GAP_MM - panel_h_mm >= floor:
        return low - PANEL_GAP_MM
    return None


def _place_on_one_sheet(client, model, prefix, specs, results, subset, master, annotate: bool = False,
                        name: Optional[str] = None, kind: str = "足場立面図",
                        scales: Iterable[int] = SCALE_CANDIDATES, panel_kind: Optional[str] = None,
                        stair_plan=None, cuts=None, extra=()) -> bool:
    """全面を1枚のレイアウトに。用紙に収まらなければ何もせず False（面ごとの配置に戻る）.

    1) 元の大きさ（比率1）で仮置きして実寸を測る（注記・フロアマーカーの張り出しまで入る）
    2) 実寸の箱で縮尺と並びを決める  3) 仮置きを消して本配置
    """
    name = name or sheet_layout_name(prefix)
    lay = _create_layout(client, name, subset, master)
    if not lay:
        return False
    paper, margins = _layout_paper_mm(client, lay)
    db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": lay}}]})
    dbid = db["databases"][0]["databaseId"]
    for pl in results:
        pl.layout_name = name
        pl.layout_item_guid = lay
    probe = _create_drawings(client, dbid, results, [(margins[0], margins[3])] * len(results), 100, 0.01, kind)
    _activate(client, lay)
    measured = _drawing_boxes(client, probe) if len(probe) == len(results) else None
    if measured:
        boxes, src = measured
    else:
        # 測れなければ見積り（切断線の長さ×(足場高さ+2m)＋注記の余白）
        ex_w = NOTE_EXTRA_W_MM if annotate else 2500.0
        ex_h = NOTE_EXTRA_H_MM if annotate else 0.0
        boxes = [(s_.length_mm + ex_w, float(model.scaffold_height_mm) + 2000.0 + ex_h) for s_ in specs]
        src = 0.01
    plan = arrange_boxes(boxes, paper, margins, scales=scales)
    panel_top: Optional[float] = None
    if panel_kind:
        # 右の帯は、図面を並べて右上か下の右が空いていればそこに。空かなければ右の余白を広げて並べ直す
        from .sheet_panel import panel_content, panel_height_mm

        title = ("・".join(pl.face_name for pl in results) + " " + kind) if panel_kind == "elev" else ""
        ph = panel_height_mm(panel_content(panel_kind, model, stair_plan, cuts, title, extra))
        panel_top = panel_spot(plan, boxes, paper, margins, ph) if plan is not None else None
        if panel_top is None and plan is not None:
            reserved = arrange_boxes(boxes, paper, _with_panel(margins), scales=scales)
            if reserved is not None and reserved.scale == plan.scale:
                plan = reserved
            else:
                # 帯の分を空けると縮尺が下がるか入らない → 図面を優先し、帯は書かない（立面の2面・断面の2面を1枚に）
                panel_kind = None
    if not _delete_drawings(client, lay, probe):
        for pl in results:
            pl.notes.append("仮置きした図面を消せませんでした（レイアウトに重なって残っています）")
    if plan is None:
        _delete_items(client, [lay])
        for pl in results:
            pl.drawing_guid = ""
            pl.layout_name = ""
            pl.layout_item_guid = ""
        return False
    _create_drawings(client, dbid, results, plan.positions_mm, plan.scale, src, kind)
    if panel_kind:
        # 右の帯: 凡例・最大積載荷重・注意（例の仮設計画図に倣う。利用者の指定 2026-10-23）
        notes = _write_panel(client, model, lay, paper, margins, panel_kind, stair_plan, cuts, panel_top, title, extra)
        if notes and results:
            results[0].notes.extend(notes)
    return True


def elevation_specs_with_owner(prefix: str, owners) -> list[tuple[SectionSpec, tuple]]:
    """面の組ごとの (模型, 階段, 地盤) → 全部の面の切断線と、その面の組 [(spec, owner)]（外形の辺の順）."""
    pairs = [(s, tuple(own)) for own in owners for s in section_specs(own[0], prefix)]
    return sorted(pairs, key=lambda x: x[0].edge_index)


SECTION_MARKER_LAYER = "足場_断面マーカー"


def _delete_sections(client, guids: list[str]) -> None:
    """断面（CutPlane）を消す。隠したレイヤーの要素は API で消せない（前回の断面が残って重なり、
    図面の作成が1件60秒かかって止まった 2026-10-23）ので、マーカーのレイヤーを一度表示してから消し、また隠す."""
    if not guids:
        return
    # 今ある断面だけを1つずつ消す（控えの無い古い GUID と一緒にまとめて渡すと、今ある断面が
    # 「Failed to delete the element」で残った 2026-10-23 実機）
    try:
        r = client.tapir("GetElementsByType", {"elementType": "CutPlane"})
        if isinstance(r, dict) and "elements" in r:
            have = {e["elementId"]["guid"] for e in r["elements"]}
            guids = [g for g in guids if g in have]
    except Exception:
        pass
    if not guids:
        return
    _set_marker_layer_hidden(client, False)
    try:
        for g in guids:
            client.tapir("DeleteElements", {"elements": [{"elementId": {"guid": g}}]})
    finally:
        _set_marker_layer_hidden(client, True)


OLD_MARKER_LAYERS = ("足場_立面マーカー",)   # 名前を変える前のマーカーのレイヤー（残っている断面を消すため）


def _set_marker_layer_hidden(client, hidden: bool) -> None:
    try:
        attrs = client.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        have = {a.get("name") for a in attrs}
        names = [SECTION_MARKER_LAYER] + [n for n in OLD_MARKER_LAYERS if n in have]
        client.tapir("CreateLayers", {"layerDataArray": [{"name": n, "isHidden": bool(hidden)} for n in names],
                                      "overwriteExisting": True})
    except Exception:
        pass


def hide_section_markers(client, section_guids: list[str], layer_name: str = SECTION_MARKER_LAYER) -> str:
    """断面（CutPlane）を隠したレイヤーに移す（図面・断面図はそのまま）。できなければ注意の文を返す."""
    if not section_guids:
        return ""
    try:
        client.tapir("CreateLayers", {"layerDataArray": [{"name": layer_name, "isHidden": True}],
                                      "overwriteExisting": True})
        attrs = client.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        li = next(int(a["index"]) for a in attrs if a.get("name") == layer_name)
        client.tapir("SetDetailsOfElements", {"elementsWithDetails": [
            {"elementId": {"guid": g}, "details": {"layerIndex": li}} for g in section_guids]})
        return ""
    except Exception as e:
        return f"立面の断面のマーカーを隠せませんでした（{e}）"


def place_section_elevations(model: ScaffoldModel, client, prefix: str = "足場", replace: bool = True,
                             previous: Optional[dict] = None, one_sheet: bool = True,
                             annotate: bool = True, terrain=None, on_sections=None,
                             stair_plan=None, others=()) -> list[ElevationPlacement]:
    """面ごとの断面図を作り、サブセット「仮設足場」の下のレイアウトに図面として置く.

    previous は前回の控え {断面名: 要素GUID}（run_from_archicad が書く）。再実行で置き換える。
    one_sheet なら、全面が1枚の用紙に収まるときは1枚のレイアウト「<prefix> 足場立面図」にまとめ、
    収まらなければ面ごとのレイアウトにする。
    others は面の組（face_forms）のほかの組の (模型, 階段, 地盤)。その面も同じ並び（辺の順）で立面図にする
    （先頭の組の面しか立面図が無く、境界に合わせて替えた面の図が出ていなかった）。
    """
    pairs = elevation_specs_with_owner(prefix, [(model, stair_plan, terrain), *others])
    specs = [s for s, _own in pairs]
    owner_of = {s.name: own for s, own in pairs}
    stale_notes: list[str] = []
    if not activate_floor_plan(client):
        stale_notes.append("平面図のウィンドウを前面にできませんでした。断面の作成・削除は平面図が前面のときだけ通ります")
    if replace:
        prev = previous or {}
        _, _, left = remove_elevations(client, [s.name for s in specs],
                                       [layout_name(prefix, s.face_name) for s in specs] + sheet_layout_names(prefix),
                                       [prev.get(s.name, "") for s in specs])
        if left:
            stale_notes.append("前回の断面「" + "・".join(left) + "」は控えが無く消せませんでした。プロジェクトマップで手で消してください")
    # 1. 断面（CutPlane 要素）
    resp = client.tapir("CreateSections", {"sectionsData": [
        {"startCoordinate": {"x": s.start_mm[0] / 1000.0, "y": s.start_mm[1] / 1000.0},
         "endCoordinate": {"x": s.end_mm[0] / 1000.0, "y": s.end_mm[1] / 1000.0},
         "depth": s.depth_mm / 1000.0, "name": s.name} for s in specs]})
    results: list[ElevationPlacement] = []
    for s, el in zip(specs, resp.get("elements", [])):
        pl = ElevationPlacement(face_name=s.face_name, section_name=s.name)
        pl.notes.extend(stale_notes)
        stale_notes = []
        if "elementId" in el:
            pl.section_guid = el["elementId"]["guid"]
        else:
            pl.notes.append(f"断面を作れませんでした（{el.get('error', {}).get('message', el)}）。同名の断面が残っていればそれを図面に使います")
        results.append(pl)
    # 断面のマーカーは平面図に要らない（面のまわりに「S-01」が12個並んで読みにくかった）。隠したレイヤーに移す。
    # 断面図 A-A・B-B は足場平面図に切断線と記号を書く（cut_overlay）
    note = hide_section_markers(client, [pl.section_guid for pl in results if pl.section_guid])
    if note and results:
        results[0].notes.append(note)
    # 作った断面はすぐ控える（この後で時間切れ等で止まっても、次回の実行で消せるように）
    if on_sections is not None:
        try:
            on_sections(results)
        except Exception:
            pass
    # 2. プロジェクトマップの項目（図面の元）
    pm = _tree(client, "ProjectMap")
    for pl in results:
        # 同名が残っていれば新しい方（最後）を使う
        hit = find_items(pm, "SectionItem", name=pl.section_name)
        if hit:
            pl.section_item_guid = hit[-1]["guid"]
        else:
            pl.notes.append("プロジェクトマップに断面が見つかりません")
    # 2b. 注記（各断面を開いて文字と線を置く。断面を消すと中の注記も消えるので控えは要らない）
    if annotate:
        by_name = {s.name: s for s in specs}
        # ラベルの文字幅は図面の縮尺で決まる（文字は用紙の mm）。縮尺は図面を置くまで決まらないので、
        # A1 に2面ずつ並べたときの縮尺で見積もる（面ごとに、その組の縮尺）
        est_by: dict[str, float] = {}
        for g in range(0, len(specs), FACES_PER_SHEET):
            grp = specs[g:g + FACES_PER_SHEET]
            est = arrange_on_one_sheet([s_.length_mm for s_ in grp],
                                       max(float(owner_of[s_.name][0].scaffold_height_mm) for s_ in grp), (841.0, 594.0),
                                       extra_w_mm=NOTE_EXTRA_W_MM, extra_h_mm=NOTE_EXTRA_H_MM)
            for s_ in grp:
                est_by[s_.name] = float(est.scale) if est is not None else 200.0
        for pl in results:
            if not pl.section_item_guid or not pl.section_guid:
                continue
            try:
                if not open_section_window(client, pl.section_item_guid):
                    # 断面が前面に出ないまま書くと、注記（線・文字・ラベル）が平面図に入ってしまう
                    # （2026-10-18 実機: 平面図の y≈-687m に立面の注記が53個入り、足場平面図が白紙になった）
                    pl.notes.append("断面図のウィンドウが開かなかったので注記を置きませんでした（もう一度実行してください）")
                    continue
                om, osp, ot = owner_of[pl.section_name]
                write_section_notes(client, section_annotations(om, by_name[pl.section_name], ot, stair_plan=osp,
                                                                 text_scale=est_by.get(pl.section_name, 200.0)))
            except Exception as ex:          # 注記が置けなくても図面は置く
                pl.notes.append(f"注記を置けませんでした: {ex}")
        activate_floor_plan(client)
    # 3. レイアウトと図面
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    left_over = set(range(len(results)))
    if one_sheet and results:
        # 2面ずつ1枚のレイアウト（「… 足場立面図 1」「… 2」。2面以下なら番号なし）。入らない組は面ごとのレイアウトへ
        idx = [i for i, pl in enumerate(results) if pl.section_item_guid]
        groups = [idx[g:g + FACES_PER_SHEET] for g in range(0, len(idx), FACES_PER_SHEET)]
        for k, grp in enumerate(groups, start=1):
            name = sheet_layout_name(prefix, k if len(groups) > 1 else 0)
            # 帯の凡例・荷重表は図にある面の組ぶん（先頭の面の組と、ほかの組を extra に）
            sheet_owners = list({id(owner_of[specs[i].name][0]): owner_of[specs[i].name] for i in grp}.values())
            om, osp, _ot = sheet_owners[0]
            if _place_on_one_sheet(client, om, prefix, [specs[i] for i in grp], [results[i] for i in grp],
                                   subset, master, annotate=annotate, name=name, panel_kind="elev",
                                   stair_plan=osp, extra=[(m_, sp_) for m_, sp_, _t in sheet_owners[1:]]):
                left_over -= set(grp)
        if not left_over:
            activate_floor_plan(client)
            return results
    for i, (pl, s) in enumerate(zip(results, specs)):
        if not pl.section_item_guid or i not in left_over:
            continue
        pl.layout_name = layout_name(prefix, pl.face_name)
        data = {"layoutName": pl.layout_name, "parentNavigatorItemId": {"guid": subset}}
        if master:
            data["masterNavigatorItemId"] = {"guid": master["guid"]}
        client.tapir("CreateLayout", {"layoutsData": [data]})
        lb = _tree(client, "LayoutBook")
        hit = find_items(lb, "LayoutItem", name=pl.layout_name)
        if not hit:
            pl.notes.append("レイアウトを作れませんでした")
            continue
        pl.layout_item_guid = hit[-1]["guid"]
        db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": pl.layout_item_guid}}]})
        dbid = db["databases"][0]["databaseId"]
        paper, margins = _layout_paper_mm(client, pl.layout_item_guid)
        plan = drawing_plan(s.length_mm, float(owner_of[s.name][0].scaffold_height_mm), paper, margins)
        # 断面の元ビューは 1/100（Archicad の断面の既定）。比率で縮尺を付ける
        _create_drawings(client, dbid, [pl], [plan.position_mm], plan.scale, 0.01)
    activate_floor_plan(client)
    return results


ELEVATIONS_RECORD = "elevation_sections.json"


def load_record(out_dir) -> dict:
    """前回の控え {断面名: 要素GUID}（無ければ空）."""
    import json
    from pathlib import Path

    p = Path(out_dir) / ELEVATIONS_RECORD
    if not p.exists():
        return {}
    try:
        return {str(k): str(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not str(k).startswith("_")}
    except Exception:
        return {}


def save_record(out_dir, placements: list[ElevationPlacement], previous: Optional[dict] = None,
                building: str = "", prefix: str = "") -> dict:
    """今回置いた断面の GUID を控えに足して書く（他の建物の分は残す）.

    建物（外形の外接矩形）と工事名も控える。工事名を変えて再実行したとき、同じ建物の
    古い名前の断面・レイアウトを片付けるため（名前だけでは同じ建物と分からない）。
    """
    import json
    from pathlib import Path

    rec = dict(previous or {})
    meta = dict(load_record_meta(out_dir))
    for pl in placements:
        if pl.section_guid:
            rec[pl.section_name] = pl.section_guid
            if building:
                meta[pl.section_name] = {"building": building, "prefix": prefix}
    out = {**rec, "_meta": {k: v for k, v in meta.items() if k in rec}}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / ELEVATIONS_RECORD).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec


def load_record_meta(out_dir) -> dict:
    """控えの付帯情報 {断面名: {"building", "prefix"}}."""
    import json
    from pathlib import Path

    p = Path(out_dir) / ELEVATIONS_RECORD
    try:
        meta = json.loads(p.read_text(encoding="utf-8")).get("_meta", {}) if p.exists() else {}
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def building_key(outline_mm) -> str:
    """建物を外形の外接矩形で識別する（0.1m 単位）."""
    xs = [float(p[0]) for p in outline_mm]
    ys = [float(p[1]) for p in outline_mm]
    return ",".join(f"{v / 1000.0:.1f}" for v in (min(xs), min(ys), max(xs), max(ys)))


def stale_prefixes(record: dict, meta: dict, building: str, prefix: str) -> dict:
    """同じ建物で工事名が違う控え → {古い工事名: [断面名, ...]}."""
    out: dict = {}
    for name in record:
        m = meta.get(name) or {}
        if m.get("building") == building and m.get("prefix") and m.get("prefix") != prefix:
            out.setdefault(m["prefix"], []).append(name)
    return out


def remove_stale_prefixes(client, record: dict, meta: dict, building: str, prefix: str) -> tuple[dict, list[str]]:
    """同じ建物の古い工事名の断面とレイアウトを消す。消した分を除いた控えと、消した工事名を返す."""
    stale = stale_prefixes(record, meta, building, prefix)
    if not stale:
        return record, []
    rec = dict(record)
    for old, names in stale.items():
        faces = [n[len(old) + 1:-len(" 足場立面")] for n in names if n.endswith(" 足場立面")]
        lays = scaffold_layout_names(old, faces)
        activate_floor_plan(client)
        remove_elevations(client, names, lays, [rec.get(n, "") for n in names])
        for n in names:
            rec.pop(n, None)
    activate_floor_plan(client)
    return rec, sorted(stale)



# ---------------------------------------------------------------- 足場平面図のレイアウト（Phase 9-2）

def plan_layout_name(prefix: str) -> str:
    return f"{prefix} 足場平面図"


def plan_region_mm(model: ScaffoldModel, margin_mm: float = 1500.0) -> tuple[float, float, float, float]:
    """平面図で切り抜く範囲（モデル mm: xmin, ymin, xmax, ymax）.

    躯体外形に、最大の離れ＋建地列間隔＋断面の切断線（外側建地列から CLEARANCE_MM 外）と
    その延長・マーカーを足す。朝顔（突出2m）・ステージの張出し・昇降機の搬器はこの中に入る。
    """
    xs = [float(v[0]) for v in model.plan.outline.vertices]
    ys = [float(v[1]) for v in model.plan.outline.vertices]
    standoff = max((float(e.standoff) for e in model.plan.edges), default=300.0)
    # 朝顔・ステージ・昇降機の張り出しの分も（平面の寸法とラベルの列はその外。入れないとラベルの文字が切れた）
    from .plan_labels import outward_extra_m

    grow = standoff + float(model.post_row_spacing_mm) + CLEARANCE_MM + margin_mm + outward_extra_m(model) * 1000.0
    box = [min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow]
    # 敷地境界線も入れる（境界と足場の離れが読めるように）
    for bx, by in getattr(model, "site_boundary_mm", None) or []:
        box = [min(box[0], bx - margin_mm), min(box[1], by - margin_mm), max(box[2], bx + margin_mm), max(box[3], by + margin_mm)]
    return tuple(box)


def fit_scale(box_mm: tuple[float, float], paper_mm: tuple[float, float],
              margins_mm: tuple[float, float, float, float] = (20.0, 20.0, 20.0, 20.0),
              title_band_mm: float = 60.0, caption_mm: float = 15.0) -> Optional[int]:
    """モデル mm の箱が用紙に収まる最大の縮尺（1/50 から）。収まらなければ None."""
    pw, ph = paper_mm
    left, top, right, bottom = margins_mm
    uw = pw - left - right - 10.0
    uh = ph - top - bottom - title_band_mm - caption_mm
    for sc in SCALE_CANDIDATES:
        if box_mm[0] / sc <= uw and box_mm[1] / sc <= uh:
            return sc
    return None


def clipped_drawing_geometry(region_mm: tuple[float, float, float, float], scale: int,
                             paper_pos_mm: tuple[float, float], source_scale: int = 100) -> tuple[list[dict], dict]:
    """平面の範囲を用紙の位置に切り抜いて置くときの clipPolygon と position（どちらも用紙 m）.

    実機で確かめた関係: 図面の枠（clipPolygon）は用紙の絶対座標、中身は「用紙 = pos + モデル×k」
    （k = 1/縮尺）、Tapir は pos = position − clip の最小角 × 比率（比率 = 元の図の縮尺/縮尺、
    1/100 の平面を 1/20 で置けば 5）にする。よって枠を P に置き、モデルの範囲の最小角を P に
    合わせるには position = P×(1+比率) − Rmin×k、clip = P から R×k の大きさの矩形。
    （比率1のときは 2P − Rmin×k。詳細図を 1/20 で置いて比率の項が要ると分かった、2026-10-18）
    """
    k = 1.0 / scale
    ratio = source_scale / scale
    x0, y0, x1, y1 = region_mm
    px, py = paper_pos_mm[0] / 1000.0, paper_pos_mm[1] / 1000.0
    w, h = (x1 - x0) / 1000.0 * k, (y1 - y0) / 1000.0 * k
    clip = [{"x": px, "y": py}, {"x": px + w, "y": py}, {"x": px + w, "y": py + h}, {"x": px, "y": py + h}]
    position = {"x": px * (1 + ratio) - x0 / 1000.0 * k, "y": py * (1 + ratio) - y0 / 1000.0 * k}
    return clip, position


def _create_drawings_safely(client, data: list[dict], layout_item_guid: str = "") -> list[dict]:
    """CreateDrawings の先頭に捨てる図面を1枚入れて作り、それを消す. 戻り値は data と同じ並びの elements.

    原点が移ったプロジェクト（保存・再起動で Archicad が原点を要素の近くへ寄せる）では、1回の CreateDrawings で
    作る図面のうち最初の1枚だけ中身が映らない（白紙）。2枚目以降は正しく映る（2026-10-24 実機で何度も確かめた）。
    """
    if not data:
        return []
    r = client.tapir("CreateDrawings", {"drawingsData": [{**data[0], "name": "（捨てる図面）"}] + list(data)})
    els = list(r.get("elements") or [])
    if els and "elementId" in els[0]:
        try:
            # 図面の削除はそのレイアウトが前面のときだけ通る（_delete_drawings）
            if layout_item_guid:
                _delete_drawings(client, layout_item_guid, [els[0]])
            else:
                client.tapir("DeleteElements", {"elements": [els[0]]})
        except Exception:
            pass
    return els[1:]


def create_clipped_drawings(client, data: list[dict], layout_item_guid: str) -> list[dict]:
    """切り抜いた図面を置き、置いた位置（pos）を読み戻して、ずれていれば1回置き直す。戻り値は CreateDrawings の elements.

    clipped_drawing_geometry は「pos = position − 枠の最小角 × 比率」（プロジェクトマップのフロアでの関係）で位置を
    決めるが、ビューマップのフロアにズームが保存されていると、pos がズームの左下の分だけずれて図面が白紙になった
    （2026-10-23 実機: 平面図・詳細図・断面図がすべて白紙。ズームの左下 (-12.3, -7.1) m × 1/縮尺 だけずれていた）。
    ずれは置く位置に依らない一定量なので、読み戻した差を足して置き直せば合う。

    原点が移ったプロジェクト（modelOffset）では、中身は「いまの座標＋ずれ」で映る（元の原点が中身の左下に来る）。
    ずれ×1/縮尺 だけ手前に置き直す。このとき読み戻す pos は当てにならないので使わない（2026-10-24 実機）。
    """
    els = _create_drawings_safely(client, data, layout_item_guid)
    ok = [i for i, e in enumerate(els) if "elementId" in e]
    if not ok:
        return els
    _activate(client, layout_item_guid)
    try:
        # 原点のずれ（modelOffset）は図面を更新してから読める（置いた直後は 0）
        client.tapir("UpdateDrawings", {"elements": [els[i] for i in ok]})
    except Exception:
        pass
    try:
        dets = client.get_details([els[i] for i in ok])
    except Exception:
        return els
    redo = []
    for i, det in zip(ok, dets):
        dd = det.get("details") or {}
        pos = dd.get("pos")
        d = data[i]
        if not pos or not d.get("clipPolygon"):
            continue
        off = dd.get("modelOffset") or {}
        ox, oy = float(off.get("x", 0.0) or 0.0), float(off.get("y", 0.0) or 0.0)
        if abs(ox) > 1e-6 or abs(oy) > 1e-6:
            k = 1.0 / float(d.get("drawingScale") or 100.0)
            dx, dy = -ox * k, -oy * k
        else:
            ratio = float(d.get("scale", 1.0))
            want_x = d["position"]["x"] - d["clipPolygon"][0]["x"] * ratio
            want_y = d["position"]["y"] - d["clipPolygon"][0]["y"] * ratio
            dx, dy = want_x - float(pos["x"]), want_y - float(pos["y"])
        if abs(dx) > 1e-6 or abs(dy) > 1e-6:
            redo.append((i, dx, dy))
    if not redo:
        return els
    try:
        client.tapir("DeleteElements", {"elements": [els[i] for i, _, _ in redo]})
        again = _create_drawings_safely(client, [
            {**data[i], "position": {"x": data[i]["position"]["x"] + dx, "y": data[i]["position"]["y"] + dy}}
            for i, dx, dy in redo], layout_item_guid)
        for (i, _, _), e in zip(redo, again):
            els[i] = e
    except Exception:
        pass
    return els


def plan_source(client, floor_index: Optional[int] = None) -> tuple[Optional[dict], int, str]:
    """足場平面図・詳細図を切り抜く元の図と、その縮尺 → (項目, 元の縮尺, 注意).

    元はプロジェクトマップのフロア。ビューマップの同じフロアのビューはズームが保存されていると、その範囲しか
    図面に映らない（2026-10-24 実機: 保存・再起動で原点が移り、見本がズームの範囲 x −12〜30m の外に出て平面図が
    白紙）。プロジェクトマップのフロアは「いまの平面図ウィンドウの縮尺」で図面になるので、その縮尺は試しの図面を
    1枚置いて読む（以前は 1:100 とみなし、平面図を 1:50 にしていると位置がずれて白紙になった。2026-10-20 実機）。
    """
    story = active_story_item(client, floor_index)
    if story is None:
        return None, 100, "フロアがプロジェクトマップに見つかりません"
    sc = _probe_drawing_scale(client, story["guid"])
    if sc:
        return story, sc, ""
    return story, 100, (f"「{story.get('name')}」の図面の縮尺を読めないので、平面図ウィンドウの縮尺を 1:100 とみなして"
                        "切り抜きます（平面図を 1:100 以外にしているとずれます）")


def _probe_drawing_scale(client, item_guid: str) -> Optional[int]:
    """その項目を図面にしたときの元の縮尺（1/n の n）. いちばん上のレイアウトに試しの図面を置いて読み、消す."""
    try:
        lays = [it for it in walk_tree(_tree(client, "LayoutBook")) if it.get("type") == "LayoutItem"]
        if not lays:
            return None
        lay = lays[0]["guid"]
        db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": lay}}]})
        dbid = db["databases"][0]["databaseId"]
        r = client.tapir("CreateDrawings", {"drawingsData": [{
            "navigatorItemId": {"guid": item_guid}, "layoutDatabaseId": dbid, "position": {"x": 0.0, "y": 0.0},
            "clipPolygon": [{"x": 0.0, "y": 0.0}, {"x": 0.01, "y": 0.0}, {"x": 0.01, "y": 0.01}, {"x": 0.0, "y": 0.01}],
            "scale": 1.0, "drawingScale": 100.0, "name": "縮尺の確認（消す）"}]})
        el = (r.get("elements") or [{}])[0]
        if "elementId" not in el:
            return None
        try:
            _activate(client, lay)
            det = (client.get_details([el]) or [{}])[0].get("details") or {}
        finally:
            client.tapir("DeleteElements", {"elements": [el]})
            activate_floor_plan(client)
        ds = float(det.get("drawingScale") or 0.0)
        return int(round(1.0 / ds)) if ds > 0 else None
    except Exception:
        return None


def active_story_item(client, floor_index: Optional[int] = None) -> Optional[dict]:
    """足場を置いたフロアのプロジェクトマップ項目（floor_index を省くと現在のフロア）."""
    if floor_index is not None:
        act = int(floor_index)
    else:
        try:
            act = int(client.tapir("GetStories", {}).get("actStory", 0))
        except Exception:
            act = 0
    items = story_items(_tree(client, "ProjectMap"))
    hit = [it for it in items if str(it.get("prefix", "")).strip() == str(act)]
    return hit[0] if hit else (items[0] if items else None)


@dataclass
class PlanSheet:
    layout_name: str = ""
    layout_item_guid: str = ""
    drawing_guid: str = ""
    scale: int = 100
    notes: list[str] = field(default_factory=list)


def place_plan_sheet(model: ScaffoldModel, client, prefix: str = "足場", replace: bool = True,
                     floor_index: Optional[int] = None, stair_plan=None, other_models=(), cuts=()) -> PlanSheet:
    """配置フロアの平面図を足場の範囲で切り抜き、サブセット「仮設足場」のレイアウト「<prefix> 足場平面図」に置く.

    cuts は断面図の切断線 [{"label", "start", "end"}]（mm）。平面図に一点鎖線と記号（A・B）で書く
    （Archicad の断面のマーカーは「S-01」で読めないので隠している）。
    """
    out = PlanSheet(layout_name=plan_layout_name(prefix))
    activate_floor_plan(client)
    # 現在のフロアは断面を開いたりすると変わる。足場ラインのフロアを渡されればそれを使う
    story, src_scale, src_note = plan_source(client, floor_index)
    if src_note:
        out.notes.append(src_note)
    if story is None:
        return out
    if replace:
        lb = _tree(client, "LayoutBook")
        _delete_items(client, [it["guid"] for it in walk_tree(lb) if it["type"] == "LayoutItem" and it["name"] == out.layout_name])
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    lay = _create_layout(client, out.layout_name, subset, master)
    if not lay:
        out.notes.append("レイアウトを作れませんでした")
        return out
    out.layout_item_guid = lay
    paper, margins0 = _layout_paper_mm(client, lay)
    margins = _with_panel(margins0)                 # 右の帯（方位・凡例・荷重表・共通事項）の分を空ける
    region = plan_region_mm(model)
    box = (region[2] - region[0], region[3] - region[1])
    scale = fit_scale(box, paper, margins)
    if scale is None:
        scale = SCALE_CANDIDATES[-1]
        out.notes.append(f"平面が用紙に収まりません（1/{scale} で置きます）")
    out.scale = scale
    # 用紙の左上寄せ（タイトル帯の上）
    pos = (margins[0] + 10.0, paper[1] - margins[1] - box[1] / scale)
    clip, position = clipped_drawing_geometry(region, scale, pos, source_scale=src_scale)
    db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": lay}}]})
    dbid = db["databases"][0]["databaseId"]
    els = create_clipped_drawings(client, [{
        "navigatorItemId": {"guid": story["guid"]}, "layoutDatabaseId": dbid, "position": position,
        "clipPolygon": clip, "scale": src_scale / scale, "drawingScale": float(scale),
        "name": f"足場平面図 {scale_caption(scale)}"}], lay)
    el = (els or [{}])[0]
    if "elementId" in el:
        out.drawing_guid = el["elementId"]["guid"]
        try:
            client.tapir("UpdateDrawings", {"elements": [el]})
        except Exception:
            pass
    else:
        out.notes.append(f"図面を置けませんでした: {el.get('error', el)}")
    out.notes.extend(_write_panel(client, model, lay, paper, margins0, "plan", stair_plan, title="足場平面図",
                                  extra=[(m_, None) for m_ in other_models]))
    if cuts:
        from .sheet_panel import cut_overlay, write_overlay

        try:
            write_overlay(client, lay, cut_overlay(cuts, region, scale, pos))
        except Exception as e:
            out.notes.append(f"断面図の切断線を書けませんでした（{e}）")
    if getattr(model, "site_boundary_mm", None):
        # 敷地境界線（一点鎖線）と面ごとの境界までの離れ（ビューのレイヤーで境界が隠れていても図に出す）
        from .sheet_panel import boundary_overlay, write_overlay

        try:
            write_overlay(client, lay, boundary_overlay(model, region, scale, pos, other_models))
        except Exception as e:
            out.notes.append(f"敷地境界線を書けませんでした（{e}）")
    activate_floor_plan(client)
    return out
