"""鉄骨の建て方のピース割りと節ごとの重量表（利用者の指定 2026-11-07）.

「表は節、通り、符号、重量で良い　ガセットプレートのこと梁も柱の中心から距離で分けて柱とガセットプレートと一体にしたい　柱はフロア＋１mで区切る」。

Archicad の柱と梁（符号・位置・高さ）を読み、次のピースに分ける。
- 柱: 同じ位置の柱を1本に通して、階の高さ＋offset で切る（every 階ごと）。これが節
- 梁: 柱の中心から bracket の所で切る。端の側は柱と一体（ブラケット形式。利用者の確認 2026-11-07「短い梁の形」）。真ん中は梁のピース
- 継手: 利用者の言う「ガセット」はブラケット先端の梁継手の添え板（SPL）に当たる（reports/ガセットプレートの実務と標準値.md）。
  ウェブ両面 2 枚とフランジの外 1＋内 2 を上下に。値は SPLICE_400（400N 級の大梁継手の表。structure.jp の転載で原本は未確認）、表に無い断面は【目安】
- 重量: 符号表の断面（H-500×200×10×16・□-500×500×22・P-318.5×10）の断面積×長さ×7.85t/m³。H 形鋼はフィレット 0.858r² を足す（BH は足さない）。
  ブラケットと添え板一式、1 節目のベースプレートを柱のピースに足す（添え板は工場でブラケット側に付けて運ぶ前提）。断面の無い符号は重量を出さない（外形で計算すると中実の重さになる）。
  ボルトは数えず、割増 extra に含める。ダイアフラムと柱頭の板は 1 枚ずつ足す。ベースプレートの大きさは窓の値で【目安】.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .opening_guard import inside

DENSITY = 7.85e-9                                # t/mm³
PLATE_SIZES = (9.0, 12.0, 16.0, 19.0, 22.0, 25.0, 28.0, 32.0, 36.0, 40.0, 45.0, 50.0)   # 鋼板の板厚の並び mm
MIN_PIECE = 2000.0                               # 節のいちばん短い長さ mm【目安】
MAX_PIECE = 12000.0                              # 節の長さの目安 mm（structure-design の解説。車両の制限 12m）
TRAILER_BED = 9200.0                             # 10t 平車の荷台の長さ mm（丸五運輸の例）
MAX_WIDTH = 2400.0                               # 荷台の幅 mm（同じ例の 2,300〜2,400）

# 400N 級の大梁継手（H, B, tw, tf）: (外添板 厚, 長さ, 幅, 内添板 厚, 幅, ウェブ添板 厚, 高さ, 幅)
# https://www.structure.jp/databook/data127.htm の表（並びは厚×長さ×幅と推定。原本 SCSS-H97 は未確認）
SPLICE_400 = {(250, 125, 6, 9): (9, 285, 120, 9, 45, 6, 170, 165), (300, 150, 6.5, 9): (9, 285, 145, 9, 55, 6, 200, 165),
              (350, 175, 7, 11): (9, 285, 170, 9, 65, 9, 200, 165), (400, 200, 8, 13): (9, 405, 195, 12, 70, 9, 260, 165),
              (450, 200, 9, 14): (12, 405, 195, 12, 70, 9, 320, 165), (500, 200, 10, 16): (12, 405, 195, 16, 70, 9, 350, 165),
              (600, 200, 11, 17): (16, 405, 195, 16, 70, 9, 440, 165), (588, 300, 12, 20): (16, 435, 295, 16, 105, 9, 440, 165),
              (700, 300, 13, 24): (19, 525, 295, 19, 105, 9, 530, 165)}


@dataclass(frozen=True)
class Section:
    text: str
    kind: str                                    # H・BOX・PIPE
    h: float
    b: float
    tw: float
    tf: float

    @property
    def area(self) -> float:
        """断面積 mm²（H 形鋼はフィレットを含む。日本製鉄の式 2B·t2＋(H−2t2)·t1＋0.858r²）."""
        if self.kind == "H":
            plate = 2 * self.b * self.tf + (self.h - 2 * self.tf) * self.tw
            if self.text.strip().upper().startswith("BH"):
                return plate                     # 溶接組立はフィレットなし
            r = 8.0 if self.b <= 100 else 22.0 if self.b >= 400 else 13.0
            return plate + 0.858 * r * r
        if self.kind == "BOX":
            return 2 * self.tf * (self.h + self.b - 2 * self.tf)
        return math.pi * self.tf * (self.h - self.tf)

    def weight(self, length: float) -> float:
        """長さ mm の重さ t."""
        return self.area * max(0.0, length) * DENSITY


def parse_section(text: str) -> Section | None:
    """断面の文字 → Section. H-500×200×10×16・BH-…・□-500×500×22・□-500×22・P-318.5×10・○-318.5×10. 読めなければ None."""
    s = str(text or "").strip().upper().replace("Ｈ", "H").replace("－", "-").replace("ー", "-")
    m = re.match(r"^(B?H|□|BOX|P|○|PIPE)\s*-?\s*(.+)$", s)
    if not m:
        return None
    try:
        v = [float(x) for x in re.split(r"[×X*xｘ]", m.group(2)) if x.strip()]
    except ValueError:
        return None
    head = m.group(1)
    if head in ("H", "BH") and len(v) == 4:
        return Section(str(text).strip(), "H", v[0], v[1], v[2], v[3])
    if head in ("□", "BOX") and len(v) in (2, 3):
        h, b, t = (v[0], v[0], v[1]) if len(v) == 2 else v
        return Section(str(text).strip(), "BOX", h, b, t, t)
    if head in ("P", "○", "PIPE") and len(v) == 2:
        return Section(str(text).strip(), "PIPE", v[0], v[0], v[1], v[1])
    return None


@dataclass
class Column:
    mark: str
    x: float
    y: float
    z0: float
    z1: float
    w: float
    d: float
    ang: float = 0.0


@dataclass
class Beam:
    mark: str
    p0: tuple
    p1: tuple
    zc: float                                    # 梁の中心の高さ
    w: float
    h: float


@dataclass
class Options:
    every: int = 2                               # 節は何階ごと（実務は 2〜3 階で 1 節。利用者の指定 2026-11-07）
    offset: float = 1000.0                       # 階の高さからの切る高さ
    bracket: float = 1000.0                      # 柱の中心からの距離
    base: float = 0.0                            # これより下の柱・梁は見ない
    bp_over: float = 100.0                       # ベースプレートのはみ出し【目安】
    bp_t: float = 36.0                           # ベースプレートの厚さ【目安】
    extra: float = 5.0                           # 重量の割増 %（ボルト・溶接・フィレット）【目安】
    diaphragm: str = "自動"                      # 自動（角形・丸は通し、H形は水平スチフナ）・内・なし


@dataclass(frozen=True)
class Plate:
    """柱のダイアフラム（H形は水平スチフナ）1 枚 mm."""
    z: float                                     # 板の中心（ピースの下端から）
    t: float
    kind: int                                    # 1 通し・2 内・3 水平スチフナ


@dataclass
class Bracket:
    mark: str
    ang: float                                   # 柱から外への向き（度）
    z: float                                     # 高さ（絶対）
    start: float                                 # 柱の中心から根元まで
    end: float                                   # 柱の中心から先まで
    w: float = 200.0                             # 梁の幅（断面が無いときの仮の形に使う）
    h: float = 400.0                             # 梁のせい


@dataclass
class ColumnPiece:
    node: int
    grid: str
    x: float
    y: float
    z0: float
    z1: float
    marks: list
    ang: float
    w: float
    d: float
    brackets: list = field(default_factory=list)
    base_plate: bool = False
    top_plate: bool = False                      # いちばん上の節の柱頭の板
    weight: float | None = None
    zone: int = 1


@dataclass
class BeamPiece:
    mark: str
    x: float
    y: float
    z: float
    ang: float
    length: float
    w: float
    h: float
    weight: float | None = None
    zone: int = 1
    node: int = 1


@dataclass
class Zone:
    """工区のゾーン（Archicad のゾーン。外形 mm）. 名前に「工区」を含むゾーンだけを使う."""
    no: int
    name: str
    outline: list
    holes: list = field(default_factory=list)


@dataclass
class Step:
    """建て方のステップ（工区ごと・節ごと）."""
    no: int
    zone: int
    node: int
    columns: list
    beams: list
    zone_name: str = ""

    @property
    def name(self) -> str:
        return f"{self.zone_name or str(self.zone) + '工区'} {self.node}節"

    @property
    def pieces(self) -> int:
        return len(self.columns) + len(self.beams)

    @property
    def weight(self) -> float:
        return sum(p.weight or 0.0 for p in self.columns + self.beams)


@dataclass
class Plan:
    columns: list
    beams: list
    warnings: list


@dataclass(frozen=True)
class Splice:
    """梁継手の添え板一式 mm. listed が偽なら表に無い断面の【目安】."""
    out_t: float
    length: float
    out_w: float
    in_t: float
    in_w: float
    web_t: float
    web_h: float
    web_w: float
    listed: bool = True

    @property
    def weight(self) -> float:
        """一式の重さ t（ウェブ両面 2 枚・フランジ外 2 枚・内 4 枚）."""
        return (2 * self.web_t * self.web_h * self.web_w + 2 * self.out_t * self.length * self.out_w
                + 4 * self.in_t * self.length * self.in_w) * DENSITY


def splice_of(s: Section | None) -> Splice | None:
    """H 形の梁の添え板一式. 継手表に無い断面は【目安】（幅 165、高さはフランジの内側から 20 ずつ控える、厚さは tf の 0.8 倍以上の段）."""
    if s is None or s.kind != "H":
        return None
    row = SPLICE_400.get((s.h, s.b, s.tw, s.tf))
    if row:
        return Splice(*row)
    t = next((x for x in (9, 12, 16, 19, 22, 25, 28) if x >= s.tf * 0.8), 32)
    return Splice(t, 405.0, s.b - 5.0, t, max(45.0, (s.b - s.tw) / 2.0 - 30.0), 9.0, max(50.0, s.h - 2 * s.tf - 40.0), 165.0, False)


def size_up(t: float, n: int) -> float:
    """板厚 t の n サイズ上（並びに無い厚さは、その下の板から数える【目安】。13 の 2 サイズ上は 19）. t より薄くはしない."""
    k = max((i for i, x in enumerate(PLATE_SIZES) if x <= t), default=0)
    return next((x for x in PLATE_SIZES[min(k + n, len(PLATE_SIZES) - 1):] if x >= t), PLATE_SIZES[-1])


def cap_plate(col: Section, flange: float = 0.0) -> tuple:
    """柱頭の板の (板厚, 出) mm. 最上部の板に限った公開の基準は見つからないので、通しダイアフラムの値を当てる:
    板厚は梁フランジの最大厚の 2 サイズ上、出は柱の板厚 28 未満で 25・以上で 30（建築研究所の資料 https://www.kenken.go.jp/japanese/contents/publications/data/143/2 、
    日建連 鉄骨工事 Q&A A-2-18 https://www.nikkenren.com/kenchiku/sekou/steel_frame_Q&A/A-2-18.pdf）.
    梁が付かない柱は柱の板厚から 2 サイズ上（【目安】）."""
    return max(size_up(flange or col.tf, 2), size_up(col.tf, 0)), 30.0 if col.tf >= 28.0 else 25.0


def cap_of(p: ColumnPiece, col: Section, rows: list) -> tuple:
    """柱頭の板の (板厚, 出, 上端の高さ) mm. rows は (Bracket, 梁の Section). 柱頭に梁が付くなら板の中心を上フランジの中心に."""
    t, e = cap_plate(col, max((q.tf for _b, q in rows), default=0.0))
    z = p.z1 - p.z0
    for br, q in rows:
        if abs(br.z - p.z0 + q.h / 2.0 - (p.z1 - p.z0)) <= 50.0:
            z = br.z - p.z0 + q.h / 2.0 - q.tf / 2.0 + t / 2.0
    return t, e, z


def plate_kind(col: Section, o: Options) -> int:
    """板の種類. 既定は角形・丸が通し、H形が水平スチフナ（reports/鉄骨柱のダイアフラムの実務と標準値.md）. 丸の既定は公開の出典が無く【目安】."""
    if o.diaphragm == "なし":
        return 0
    if col.kind == "H":
        return 3
    return 2 if o.diaphragm == "内" else 1


def plate_t(kind: int, flange: float, col: Section) -> float:
    """板厚. 通しは梁フランジ最大厚の 2 サイズ上で柱の板厚以上、内は 1 サイズ上（日建連 Q&A A-3-12 の抜粋）、水平スチフナはフランジ厚以上（建研 No.143 の抜粋）."""
    t = size_up(flange, {1: 2, 2: 1, 3: 0}[kind])
    return max(t, size_up(col.tf, 0)) if kind == 1 else t


def diaphragms(p: ColumnPiece, col: Section, rows: list, o: Options) -> list:
    """ピースのダイアフラム. 全方向の梁のフランジの高さを並べ、1 枚の板厚に収まるものを 1 枚にする（告示 1464 号: フランジは板厚の内部で溶接）.
    枚数を定めた規定は無く、この手順は調査からの推論. 柱頭の板と重なる段は足さない."""
    kind = plate_kind(col, o)
    if not kind:
        return []
    flanges = sorted({(br.z - p.z0 + s * (q.h - q.tf) / 2.0, q.tf) for br, q in rows for s in (1, -1)})

    def plate(g: list) -> tuple:
        hi, lo = max(z + t / 2.0 for z, t in g), min(z - t / 2.0 for z, t in g)
        return (hi + lo) / 2.0, max(plate_t(kind, max(t for _z, t in g), col), size_up(hi - lo, 0)), hi - lo

    groups: list = []
    for f in flanges:
        if groups:
            a, b = plate(groups[-1]), plate([f])
            one = plate(groups[-1] + [f])
            if one[2] <= plate_t(kind, max(t for _z, t in groups[-1] + [f]), col) or b[0] - b[1] / 2.0 <= a[0] + a[1] / 2.0:
                groups[-1].append(f)                       # 1 枚に収まる。重なる 2 枚も 1 枚にまとめる【目安】
                continue
        groups.append([f])
    cap = cap_of(p, col, rows) if p.top_plate else None
    out = []
    for g in groups:
        z, t, _span = plate(g)
        if not cap or abs(z - (cap[2] - cap[0] / 2.0)) > cap[0]:
            out.append(Plate(z, t, kind))
    return out


def plate_weight(d: Plate, col: Section) -> float:
    """1 枚の重さ t. 通しは中抜きの無い板なので外形の全面で数える（公共建築数量積算基準の考えからの推論）."""
    e = cap_plate(col)[1]
    if d.kind == 3:
        area = (col.h - 2 * col.tf) * (col.b - col.tw)
    elif d.kind == 2:
        area = math.pi * (col.h / 2.0 - col.tf) ** 2 if col.kind == "PIPE" else (col.h - 2 * col.tf) * (col.b - 2 * col.tf)
    else:
        area = math.pi * (col.h / 2.0 + e) ** 2 if col.kind == "PIPE" else (col.h + 2 * e) * (col.b + 2 * e)
    return area * d.t * DENSITY


def plate_gap_notes(p: ColumnPiece, col: Section, rows: list, plates: list) -> list:
    """板と板の内法の注意 → (内法 mm, 文). 150mm 未満は溶接と探傷の可否の検討（建研 No.143 の抜粋）、10t は探傷の目安（日建連 A-4-7 の抜粋）."""
    if col.kind == "H":
        return []
    cap = cap_of(p, col, rows)
    rows2 = sorted([(d.z, d.t) for d in plates] + ([(cap[2] - cap[0] / 2.0, cap[0])] if p.top_plate else []))
    out = []
    for (a, ta), (b, tb) in zip(rows2, rows2[1:]):
        gap = b - tb / 2.0 - a - ta / 2.0
        if gap < 100.0:
            out.append((gap, "内法 100mm 未満: 溶接できない恐れ。ハンチか梁せいの調整を検討"))
        elif gap < 150.0:
            out.append((gap, "内法 150mm 未満: 溶接と探傷の可否を検討"))
        elif gap < max(200.0, 10.0 * col.tf):
            out.append((gap, "内法が短い: 探傷（10t）と開先の加工を確認【目安】"))
    return out


def bracket_root(col: Section | None, ang: float, w: float, d: float, flange_w: float) -> float:
    """柱の中心からブラケットの根元まで mm. 断面があれば断面の面に合わせる（利用者の指定 2026-11-07）.
    ang は柱の向きから測った梁の向き（度）. 断面が無ければ Archicad の柱の大きさ w・d. H 形の弱軸はウェブまで（図は未確認の【目安】）、丸はフランジの端が管に届く位置まで."""
    c, s = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
    if col is None:
        return (c * w + s * d) / 2.0
    if col.kind == "PIPE":
        return math.sqrt(max(0.0, (col.h / 2.0) ** 2 - (flange_w / 2.0) ** 2))
    if col.kind == "H":
        return col.h / 2.0 if c >= s else col.tw / 2.0
    return (c * col.h + s * col.b) / 2.0


def cut_heights(levels: list, z0: float, z1: float, o: Options) -> list:
    """柱の切る高さ（階の高さ＋offset。every 階ごと）. いちばん下の階は切らない。節が MIN_PIECE より短くなる切り目は使わない
    （足場.pln の 9m と 9.7m の階で 0.7m の節ができた）."""
    ls = sorted(x for x in levels if x > z0 + 1.0)
    out: list = []
    for x in ls[max(1, o.every) - 1::max(1, o.every)]:
        z = x + o.offset
        if z - (out[-1] if out else z0) >= MIN_PIECE and z1 - z >= MIN_PIECE:
            out.append(z)
    return out


def grid_names(pts: list, lines_x: list, lines_y: list, tol: float = 300.0) -> dict:
    """柱の位置 → 通りの名前（X1-Y2）. 通り芯の記号が近くに無ければ、位置の順に X1・Y1 と振る."""
    xs = sorted({round(p[0]) for p in pts})
    ys = sorted({round(p[1]) for p in pts})

    def name(v, lines, values, head):
        near = [n for n, c in lines if abs(c - v) <= tol]
        return near[0] if near else f"{head}{values.index(round(v)) + 1}"

    return {p: f"{name(p[0], lines_x, xs, 'X')}-{name(p[1], lines_y, ys, 'Y')}" for p in pts}


def _stacks(cols: list, base: float) -> dict:
    out: dict = {}
    for c in sorted(cols, key=lambda q: q.z0):
        if c.z1 <= base + 1.0:
            continue
        key = next((k for k in out if math.hypot(k[0] - c.x, k[1] - c.y) < 50.0), (c.x, c.y))
        out.setdefault(key, []).append(c)
    return out


def _on_beam(key, stack, b: Beam):
    """梁の線の上の柱なら、梁の始めからの距離. 梁の高さに柱が無い・線から外れるなら None."""
    (x0, y0), (x1, y1) = b.p0, b.p1
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    t = (key[0] - x0) * ux + (key[1] - y0) * uy
    off = abs(-(key[0] - x0) * uy + (key[1] - y0) * ux)
    half = max(max(c.w, c.d) for c in stack) / 2.0
    if off > half or not -half <= t <= L + half:
        return None
    if not any(c.z0 - 1.0 <= b.zc <= c.z1 + 1.0 for c in stack):
        return None
    return t


def plan_pieces(cols: list, beams: list, levels: list, sections: dict, o: Options, lines_x=(), lines_y=()) -> Plan:
    """柱と梁 → ピース. sections は {符号: Section}."""
    warns: list = []
    stacks = _stacks(cols, o.base)
    grid = grid_names(list(stacks), list(lines_x), list(lines_y))
    pieces: dict = {}
    for key, st in stacks.items():
        z0, z1 = max(st[0].z0, o.base), max(c.z1 for c in st)
        edges = [z0, *cut_heights(levels, z0, z1, o), z1]
        pieces[key] = []
        for n, (a, b) in enumerate(zip(edges, edges[1:]), 1):
            inside = [c for c in st if min(c.z1, b) - max(c.z0, a) > 1.0]
            marks = list(dict.fromkeys(c.mark for c in inside))
            top = inside[0] if inside else st[0]
            pieces[key].append(ColumnPiece(n, grid[key], key[0], key[1], a, b, marks, top.ang, top.w, top.d, base_plate=n == 1,
                                        top_plate=n == len(edges) - 1))
    out_beams: list = []
    for b in beams:
        if b.zc < o.base:
            continue
        L = math.dist(b.p0, b.p1)
        if L < 1.0:
            continue
        ux, uy = (b.p1[0] - b.p0[0]) / L, (b.p1[1] - b.p0[1]) / L
        ang = math.degrees(math.atan2(uy, ux))
        hits = sorted((t, k) for k, st in stacks.items() if (t := _on_beam(k, st, b)) is not None)
        stops = [(0.0, None)] * (not hits or hits[0][0] > 1.0) + hits + [(L, None)] * (not hits or hits[-1][0] < L - 1.0)
        for (ta, ka), (tb, kb) in zip(stops, stops[1:]):
            a = tb - ta
            la = o.bracket if ka else 0.0
            lb = o.bracket if kb else 0.0
            if a - la - lb < 1.0:
                warns.append(f"梁 {b.mark}: 柱の間 {a:.0f} が短く、中心から {o.bracket:.0f} で切れません（切らずに梁のピースにしました）")
                la = lb = 0.0
            for key, length, turn in ((ka, la, 0.0), (kb, lb, 180.0)):
                if key and length:
                    hit = next((p for p in pieces[key] if p.z0 - 1.0 <= b.zc <= p.z1 + 1.0), None)
                    if hit:
                        c = hit
                        q = sections.get(b.mark)
                        half = bracket_root(sections.get(c.marks[0]) if c.marks else None, ang + turn - c.ang, c.w, c.d, q.b if q else b.w)
                        c.brackets.append(Bracket(b.mark, (ang + turn) % 360.0, b.zc, half, length, b.w, b.h))
            x = b.p0[0] + ux * (ta + la)
            y = b.p0[1] + uy * (ta + la)
            out_beams.append(BeamPiece(b.mark, x, y, b.zc, ang, a - la - lb, b.w, b.h))
    plan = Plan([p for key in pieces for p in pieces[key]], out_beams, warns)
    weigh(plan, stacks, sections, o)
    return plan


def weigh(plan: Plan, stacks: dict, sections: dict, o: Options) -> None:
    """ピースの重量 t. 断面の無い符号が1つでもあれば None（重量を出さない）."""
    missing: set = set()
    guess: set = set()
    gaps: dict = {}
    for p in plan.columns:
        total = 0.0
        st = next(s for k, s in stacks.items() if math.hypot(k[0] - p.x, k[1] - p.y) < 50.0)
        ok = True
        for c in st:
            over = min(c.z1, p.z1) - max(c.z0, p.z0)
            if over <= 1.0:
                continue
            s = sections.get(c.mark)
            if s is None:
                missing.add(c.mark)
                ok = False
            else:
                total += s.weight(over)
        s0 = sections.get(p.marks[0]) if p.marks else None
        if p.base_plate and s0:
            total += (s0.h + 2 * o.bp_over) * (s0.b + 2 * o.bp_over) * o.bp_t * DENSITY
        if s0:
            rows = [(br, sections.get(br.mark) or shape_of("beam", br.w, br.h)) for br in p.brackets]
            if p.top_plate:
                t, e, _z = cap_of(p, s0, rows)
                plate = math.pi * (s0.h / 2.0 + e) ** 2 if s0.kind == "PIPE" else (s0.h + 2 * e) * (s0.b + 2 * e)
                total += plate * t * DENSITY
            plates = diaphragms(p, s0, rows, o)
            total += sum(plate_weight(d, s0) for d in plates)
            for gap, text in plate_gap_notes(p, s0, rows, plates):
                gaps.setdefault(text, []).append((gap, f"{p.node}節 {p.grid}"))
        for br in p.brackets:
            s = sections.get(br.mark)
            if s is None:
                missing.add(br.mark)
                ok = False
            else:
                sp = splice_of(s)
                total += s.weight(br.end - br.start) + (sp.weight if sp else 0.0)
                if sp and not sp.listed:
                    guess.add(br.mark)
        p.weight = total * (1 + o.extra / 100.0) if ok else None
    for b in plan.beams:
        s = sections.get(b.mark)
        if s is None:
            missing.add(b.mark)
        else:
            b.weight = s.weight(b.length) * (1 + o.extra / 100.0)
    for text, rows in gaps.items():
        low = min(rows)
        plan.warnings.append(f"ダイアフラムの{text}（{low[1]} {low[0]:.0f}mm ほか 計{len(rows)}か所）")
    if missing:
        plan.warnings.append("断面が無い符号: " + "・".join(sorted(missing)) + "（柱と梁の大きさから仮の形で描きます。符号表に入れると重量が出ます）")
    if guess:
        plan.warnings.append("継手表に無い断面: " + "・".join(sorted(guess)) + "（添え板は【目安】の大きさ）")
    long_n = sorted({p.node for p in plan.columns if p.z1 - p.z0 > MAX_PIECE})
    if long_n:
        plan.warnings.append("節の長さが 12m を超えます: " + "・".join(f"{n}節" for n in long_n))
    bed_n = sorted({p.node for p in plan.columns if TRAILER_BED < p.z1 - p.z0 <= MAX_PIECE})
    if bed_n:
        plan.warnings.append("節の長さが 10t 平車の荷台 9.2m を超えます（トレーラーの手配）: " + "・".join(f"{n}節" for n in bed_n))
    wide = sorted({f"{p.node}節 {p.grid}" for p in plan.columns if piece_width(p) > MAX_WIDTH})
    if wide:
        plan.warnings.append("ブラケットの全幅が 2.4m を超えます（荷台の幅）: " + "・".join(wide[:6]) + ("ほか" if len(wide) > 6 else ""))


def piece_width(p: ColumnPiece) -> float:
    """向かい合うブラケットの先から先まで mm（片側だけなら柱の半分を足す）."""
    worst = 0.0
    for b in p.brackets:
        opp = max((c.end for c in p.brackets if abs((c.ang - b.ang) % 360.0 - 180.0) < 1.0), default=max(p.w, p.d) / 2.0)
        worst = max(worst, b.end + opp)
    return worst


def table_rows(plan: Plan) -> list:
    """重量表の行 [(節, 通り, 符号, 重量 t か None)]. 節・通りの順."""
    rows = sorted(plan.columns, key=lambda p: (p.node, p.grid))
    return [(f"{p.node}節", p.grid, "・".join(p.marks), p.weight) for p in rows]


def zone_lines(text: str, pts: list, lines_x=(), lines_y=()) -> tuple:
    """工区の境の通り（X3,Y2 の形）→ (X の境 mm, Y の境 mm, 読めない名前). 通り芯の記号が無い通りは位置の順の X1・Y1 で読む."""
    named = grid_names(pts, list(lines_x), list(lines_y))
    xs: list = []
    ys: list = []
    bad: list = []
    for raw in re.split(r"[,、\s]+", str(text or "").strip()):
        if not raw:
            continue
        hit_x = [p[0] for p, n in named.items() if n.split("-")[0] == raw]
        hit_y = [p[1] for p, n in named.items() if n.split("-")[-1] == raw]
        if hit_x:
            xs.append(hit_x[0])
        elif hit_y:
            ys.append(hit_y[0])
        else:
            bad.append(raw)
    return sorted(set(xs)), sorted(set(ys)), bad


def zone_of(x: float, y: float, xs: list, ys: list) -> int:
    """工区の番号（1 から）. 境の通りの上は手前の工区に入れる."""
    ix = sum(1 for c in xs if x > c + 1.0)
    iy = sum(1 for c in ys if y > c + 1.0)
    return ix * (len(ys) + 1) + iy + 1


def _edge_gap(p, poly: list) -> float:
    """点から多角形の辺までの距離 mm."""
    best = math.inf
    for a, b in zip(poly, poly[1:] + poly[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


def zone_at(p, zones: list, tol: float = 100.0) -> int:
    """点の工区の番号. 線の上（tol 以内）は番号の小さいゾーン。どれにも入らなければ最後の番号＋1（工区なし）."""
    for z in zones:
        if _edge_gap(p, z.outline) <= tol:
            return z.no
        if inside(p, z.outline) and not any(inside(p, h) for h in z.holes):
            return z.no
    return len(zones) + 1


def label_point(poly: list, holes: list = (), n: int = 24) -> tuple:
    """ゾーンの名前を置く点（升目のうち辺から一番遠い点）. L字でも形の中に入る."""
    x0, x1 = min(q[0] for q in poly), max(q[0] for q in poly)
    y0, y1 = min(q[1] for q in poly), max(q[1] for q in poly)
    pts = [(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n) for i in range(n) for j in range(n)]
    pts = [p for p in pts if inside(p, poly) and not any(inside(p, h) for h in holes)]
    return max(pts, key=lambda p: min([_edge_gap(p, poly)] + [_edge_gap(p, h) for h in holes]), default=poly[0])


def make_steps(plan: Plan, xs: list, ys: list, order: str = "工区", zones: list | None = None) -> list:
    """工区ごと・節ごとのステップ. order「工区」は工区を上まで建てて次の工区へ（建て逃げ）、「節」は節を全部の工区で建てて上へ（積み上げ）.
    zones（Zone の並び）があれば通りの境より優先する."""
    place = (lambda x, y: zone_at((x, y), zones)) if zones else (lambda x, y: zone_of(x, y, xs, ys))
    for p in plan.columns:
        p.zone = place(p.x, p.y)
    for b in plan.beams:
        ang = math.radians(b.ang)
        mx, my = b.x + b.length / 2.0 * math.cos(ang), b.y + b.length / 2.0 * math.sin(ang)
        b.zone = place(mx, my)
        near = [p for p in plan.columns if p.z0 - 1.0 <= b.z <= p.z1 + 1.0]
        if near:
            b.node = min(near, key=lambda p: math.hypot(p.x - mx, p.y - my)).node
    keys = sorted({(p.zone, p.node) for p in plan.columns} | {(b.zone, b.node) for b in plan.beams},
                  key=(lambda k: k) if order != "節" else (lambda k: (k[1], k[0])))
    names = {z.no: z.name for z in zones or []}
    if zones:
        names[len(zones) + 1] = "工区なし"
        lost = sum(1 for p in plan.columns + plan.beams if p.zone == len(zones) + 1)
        if lost:
            plan.warnings.append(f"どのゾーンにも入らないピース {lost}個（「工区なし」にしました）")
    return [Step(n, z, d, [p for p in plan.columns if (p.zone, p.node) == (z, d)], [b for b in plan.beams if (b.zone, b.node) == (z, d)], names.get(z, ""))
            for n, (z, d) in enumerate(keys, 1)]


def schedule_tasks(steps: list, per_day: float, cranes: int = 1) -> list:
    """工程表の作業（ステップを順につなぐ）. per_day はクレーン 1 台の 1 日のピース数."""
    from .schedule import Dep, Task, days_of

    out = []
    for s in steps:
        out.append(Task(f"steel{s.no}", f"{s.name} 建方", "鉄骨建方", days_of(s.pieces, per_day, cranes), float(s.pieces), "ピース",
                        f"{per_day:g}ピース/日×{cranes}台", [Dep(f"steel{s.no - 1}")] if s.no > 1 else []))
    return out


def zone_sheet(wb, steps: list) -> None:
    """工区のピース数のシート."""
    sh = wb.sheet("工区のピース数")
    sh.add_title("工区のピース数", 7)
    sh.add_header(["ステップ", "工区", "節", "柱", "梁", "計", "重量 t"])
    for s in steps:
        sh.add([s.no, s.zone_name or f"{s.zone}工区", f"{s.node}節", len(s.columns), len(s.beams), s.pieces, round(s.weight, 2)])
    for z in sorted({s.zone for s in steps}):
        ss = [s for s in steps if s.zone == z]
        sh.add(["", f"{ss[0].zone_name or str(z) + '工区'} 計", "", sum(len(s.columns) for s in ss), sum(len(s.beams) for s in ss), sum(s.pieces for s in ss),
                round(sum(s.weight for s in ss), 2)])
    sh.add(["", "合計", "", sum(len(s.columns) for s in steps), sum(len(s.beams) for s in steps), sum(s.pieces for s in steps),
            round(sum(s.weight for s in steps), 2)])
    for i, wdt in enumerate((8, 12, 8, 8, 8, 8, 10)):
        sh.set_width(i, wdt)


def to_markdown(plan: Plan, title: str = "鉄骨 節ごとの重量表") -> str:
    md = [f"# {title}", "", "| 節 | 通り | 符号 | 重量 |", "|---|---|---|---|"]
    for n, g, m, w in table_rows(plan):
        md.append(f"| {n} | {g} | {m} | " + ("断面なし" if w is None else f"{w:.2f}t") + " |")
    if plan.warnings:
        md += ["", "## 注意", "", *[f"- {w}" for w in plan.warnings]]
    md += ["", "重量＝符号表の断面の断面積×長さ×7.85t/m³ に割増を掛けた値。柱のブラケットと継手の添え板一式、1 節目のベースプレート、ダイアフラム、柱頭の板を含む。ボルトは割増に含む。"]
    return "\n".join(md) + "\n"


def to_sheet(wb, plan: Plan, title: str = "鉄骨 節ごとの重量表") -> None:
    sh = wb.sheet("節ごとの重量")
    sh.add_title(title, 4)
    sh.add_header(["節", "通り", "符号", "重量 t"])
    total = 0.0
    for n, g, m, w in table_rows(plan):
        sh.add([n, g, m, "断面なし" if w is None else round(w, 2)])
        total += w or 0.0
    sh.add(["合計", "", "", round(total, 2)])
    for i, wdt in enumerate((8, 12, 14, 10)):
        sh.set_width(i, wdt)


def shape_of(kind: str, w: float, h: float) -> Section:
    """断面が空のときの形だけの仮の断面（Archicad の大きさから。板厚は【目安】。重量には使わない）."""
    if kind == "column":
        t = max(9.0, round(min(w, h) / 25.0))
        return Section("（仮）", "BOX", w, h, t, t)
    return Section("（仮）", "H", h, w, max(6.0, round(h / 50.0)), max(9.0, round(h / 30.0)))


def _sec(s: Section | None) -> tuple:
    if s is None:
        return 0, 0.0, 0.0, 0.0, 0.0
    return {"H": 1, "BOX": 2, "PIPE": 3}[s.kind], s.h / 1000.0, s.b / 1000.0, s.tw / 1000.0, s.tf / 1000.0


def column_params(p: ColumnPiece, sections: dict, o: Options) -> dict:
    """部品 ashiba_steel のパラメータ（柱のピース）."""
    s = (sections.get(p.marks[0]) if p.marks else None) or shape_of("column", p.w, p.d)
    t, h, b, tw, tf = _sec(s)
    rows = [(br, sections.get(br.mark) or shape_of("beam", br.w, br.h)) for br in p.brackets]
    cap_t, cap_o, cap_z = cap_of(p, s, rows)
    plates = diaphragms(p, s, rows, o)
    return {"spK": 1, "spT": t, "spH": h, "spB": b, "spW": tw, "spF": tf, "spL": (p.z1 - p.z0) / 1000.0, "spAng": p.ang,
            "bpOn": p.base_plate, "bpO": o.bp_over / 1000.0, "bpT": o.bp_t / 1000.0,
            "capOn": p.top_plate, "capO": cap_o / 1000.0, "capT": cap_t / 1000.0, "capZ": cap_z / 1000.0,
            "dpK": plate_kind(s, o), "dpO": cap_o / 1000.0, "dpZ": ",".join(f"{d.z:.1f}" for d in plates), "dpT": ",".join(f"{d.t:.0f}" for d in plates),
            "brA": ",".join(f"{br.ang:.1f}" for br, _s in rows), "brZ": ",".join(f"{br.z - p.z0:.0f}" for br, _s in rows),
            "brS": ",".join(f"{br.start:.0f}" for br, _s in rows), "brE": ",".join(f"{br.end:.0f}" for br, _s in rows),
            "brT": ",".join(str(_sec(q)[0]) for _b, q in rows),
            "brH": ",".join(f"{(q.h if q else 300):.0f}" for _b, q in rows), "brB": ",".join(f"{(q.b if q else 150):.0f}" for _b, q in rows),
            "brW": ",".join(f"{(q.tw if q else 9):.1f}" for _b, q in rows), "brF": ",".join(f"{(q.tf if q else 12):.1f}" for _b, q in rows),
            **{k: ",".join(f"{getattr(sp, a) if sp else 0:.0f}" for sp in (splice_of(q) for _b, q in rows))
               for k, a in (("spoT", "out_t"), ("spoL", "length"), ("spoW", "out_w"), ("spiT", "in_t"), ("spiW", "in_w"),
                            ("spwT", "web_t"), ("spwH", "web_h"), ("spwW", "web_w"))},
            "pcW": p.weight or 0.0, "pcName": f"{p.node}節 {p.grid} {'・'.join(p.marks)}" + ("" if p.weight is None else f" {p.weight:.2f}t")}


def beam_params(p: BeamPiece, sections: dict) -> dict:
    """部品 ashiba_steel のパラメータ（梁のピース）."""
    s = sections.get(p.mark) or shape_of("beam", p.w, p.h)
    t, h, b, tw, tf = _sec(s)
    return {"spK": 2, "spT": t, "spH": h, "spB": b, "spW": tw, "spF": tf, "spL": p.length / 1000.0, "spAng": p.ang,
            "bpOn": False, "capOn": False, "dpK": 0, "pcW": p.weight or 0.0, "pcName": p.mark + ("" if p.weight is None else f" {p.weight:.2f}t")}
