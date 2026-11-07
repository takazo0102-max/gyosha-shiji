"""床の開口と床の縁の墜落・落下の防止（開発ループ 2026-11-01: 他に必要な仮設材の5番。部品 ashiba_opening）.

床（スラブ）の開口をモデルから拾い、大きさで蓋か手すり・幅木・水平ネットを決める。外部足場の無い床の縁には手すり。

出典（調べた資料。開口の大きさで方法を分ける公的な基準は無く、区分は目安）:
- 労働安全衛生規則 519条（高さ 2m 以上の作業床の端・開口部に囲い・手すり・覆い等）・552条（手すり 85cm 以上・中桟 35〜50cm）・
  563条（幅木 10cm 以上・床材のすき間 3cm 以下・建地とのすき間 12cm 未満）・536条（3m 以上からの投下は投下設備）・537条（防網）
- 仮設工業会 墜落防護工（厚労省 基安安発0515001）: 束柱の間隔 200cm 以下・各段の間隔 45cm 以下・第1種 95cm 以上・幅木 10cm 以上
- 社内基準・現場資料: 小さな開口は強固な材でずれ止めと「開口注意」（厚労省 教材）、コンパネは長辺 60cm を超えたら鋼製の蓋（芝建）、
  荷揚げ開口 1000×300 は合板 24mm・掛かり 50mm・ずれ止め桟木、EV・階段・大開口は手すり 90cm 以上＋幅木＋水平ネット（矢作建設）
- 墜落による危険を防止するためのネットの構造等の安全基準に関する技術上の指針（昭和51年 技術上の指針公示第8号）: 網目 10cm 以下、
  ネット下部の空き H2（10cm 網目）＝ 0.85(L＋3A)/4（L＜A）・0.85L（L≧A）、落下高さ H1 ＝ 0.25(L＋2A)・0.75L。支持点 600kg
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

SMALL_MM, MID_MM = 300.0, 900.0        # 短辺 30cm 未満は小開口、90cm 超は手すり（合板 910 に掛からない）
LONG_PLY_MM, LONG_LID_MM = 600.0, 1800.0   # 長辺 60cm 超は 24mm 合板か鋼製、1.8m 超は手すり
LAP_MM = 100.0                         # 蓋の掛かり（50〜100）
RAIL_H, MID_H, TOE_H = 950.0, 450.0, 210.0   # 手すり（第1種 95cm）・中桟・幅木（杉足場板 210）
POST_MM = 1800.0                       # 手すり柱の間隔（スタンションの標準取付間隔 2.0m 以下）
RAIL_OFF_MM = 100.0                    # 開口・床の縁から手すり柱の芯まで（スタンションがくわえる）
OVER_MM = 50.0                         # 手すりの端の柱からの突き出しの最小（クランプの掛かり。上限は支柱の間隔の 1/4）

# 発注の規格（利用者の指定 2026-11-01: イメージじゃなく実際の規定の長さで発注できるくらい詳細に）。日建リース 仮設資材カタログ Vol.10
# 単管パイプ p372（STK500 φ48.6×2.4。手すりは型枠用・ピン無しの長さも使う）: 長さ mm → kg
TUBES = {6000: 16.42, 5500: 14.83, 5000: 13.40, 4500: 12.05, 4000: 10.60, 3600: 9.78, 3500: 9.10, 3000: 7.95, 2700: 7.61,
         2500: 6.90, 2200: 5.98, 2000: 5.30, 1800: 4.80, 1500: 4.03, 1200: 3.18, 1000: 2.65, 900: 2.46, 800: 2.30, 700: 1.95,
         600: 1.64, 500: 1.36}
PARTS = {  # 品番 → (品名, kg)
    "PCJ": ("直線ジョイント", 0.60), "PKB": ("固定ベース", 0.78), "ARC1": ("兼用直交クランプ", 0.73),
    "NREG": ("スタンション NREG（第1種・締付厚 0〜600）", 8.10)}
PLANKS = {4000: "S3540", 3000: "S3530", 2000: "S3520"}   # 杉足場板 35×210（p370）を幅木に
NETS = [(1000, 6000), (3000, 6000), (5000, 5000), (6000, 6000), (5000, 10000), (8000, 8000), (10000, 10000)]  # 100mm 目（藤田）
CLEAT_MM = 4000.0                      # ずれ止めの桟木 30×40 の定尺（目安）
NET_LAP_MM, NET_SUP_MM = 300.0, 1000.0  # ネットの張り出し・支持点の間隔（1m。大手ゼネコン・研究で効果）
NET_DOWN_MM = 300.0                    # ネットは床の上端から 0.3m 下（目安）
DROP_MIN = 2000.0                      # 落差 2m 以上は義務（519条）
PLY = (910.0, 1820.0)                  # 合板の定尺
KINDS = {1: "小開口（蓋 12mm）", 2: "中開口（蓋 12mm）", 3: "中開口（蓋 24mm・鋼製）", 4: "大開口（手すり・幅木・ネット）",
         5: "床の縁（手すり・幅木）"}


def classify(w: float, d: float) -> int:
    """開口の内法 w×d mm → 区分 1〜4（調べたメモの §5 の目安）."""
    s, lg = min(w, d), max(w, d)
    if s < SMALL_MM and lg <= LONG_PLY_MM:
        return 1
    if s <= MID_MM and lg <= LONG_PLY_MM:
        return 2
    if s <= MID_MM and lg <= LONG_LID_MM:
        return 3
    return 4


def tube_pieces(need: float, max_waste: float = 600.0) -> list[int]:
    """長さ need mm の手すりを単管の定尺で（直線ジョイントで突き合わせ）。1本増えるのは 0.6m の余りと同じとみて、本数と余りの
    少ない組み合わせ。余り（両端の突き出しが増える分）は max_waste まで。長いときは 6.0m を並べて、残りを2本までの組み合わせで."""
    lens = sorted(TUBES, reverse=True)
    head = []
    while need - 6000.0 * len(head) > 12000.0:
        head.append(6000)
    rest = need - 6000.0 * len(head)
    best = None
    for a in lens:
        for cand in ([a], *([a, x] for x in lens if x <= a)):
            waste = sum(cand) - rest
            if waste < -1e-6 or waste > max_waste + 1e-6:
                continue
            key = (len(cand) * 600.0 + waste, len(cand))
            if best is None or key < best[0]:
                best = (key, cand)
    if best is None:                                         # 余りの上限で収まらなければ余りの一番少ないもの
        return tube_pieces(need, 1e9)
    return head + sorted(best[1], reverse=True)


def plank_pieces(need: float) -> list[int]:
    """幅木の杉足場板（4・3・2m）: 足りる組み合わせのうち余り（重ね）が少なく枚数が少ないもの."""
    n4 = max(0, int(need // 4000.0) - 1)
    rest = need - 4000.0 * n4
    best = None
    for c in ([4000], [3000], [2000], [4000, 4000], [4000, 3000], [4000, 2000], [3000, 3000], [3000, 2000], [2000, 2000]):
        if sum(c) >= rest - 1e-6:
            key = (sum(c) - rest, len(c))
            if best is None or key < best[0]:
                best = (key, c)
    if best is None:
        best = ((0, 0), [4000] * math.ceil(rest / 4000.0))
    return [4000] * n4 + best[1]


def net_pick(w: float, d: float) -> list[tuple[int, int]]:
    """w×d mm を覆う水平ネット（規格の大きさ）。1枚で覆えれば一番小さいもの、無ければ 10×10m を並べる."""
    ok = [n for n in NETS if (n[0] >= w and n[1] >= d) or (n[1] >= w and n[0] >= d)]
    if ok:
        return [min(ok, key=lambda n: n[0] * n[1])]
    return [(10000, 10000)] * (math.ceil(w / 10000.0) * math.ceil(d / 10000.0))


def posts_on(length: float) -> int:
    """長さ length mm の辺の柱の間の数（等分・POST_MM 以内）."""
    return max(1, math.ceil(length / POST_MM - 1e-6))


def net_clearance(w: float, d: float, support: float = NET_SUP_MM) -> float:
    """水平ネット（10cm 網目・単体）の下に要る空き H2 mm（安全ネット指針）。L＝短辺、A＝支持点の間隔."""
    L, A = min(w, d), support
    return 0.85 * (L + 3.0 * A) / 4.0 if L < A else 0.85 * L


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Guard:
    name: str
    w: float                           # 内法 長い辺 mm（edge は縁の長さ）
    d: float                           # 内法 短い辺 mm（edge は 0）
    drop: float                        # 下の床・地盤までの落差 mm
    kind: int = 0                      # 1〜5
    corner: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0                 # 度
    z: float = 0.0                     # 床の上端
    slab_t: float = 200.0
    net: bool = False
    side: int = 1                      # 床の縁: 床の側（1＝部品の +Y）
    post: str = "NREG"                 # 手すり柱（NREG＝スタンション・PKB＝固定ベース＋単管 1.0M）
    sides: list = field(default_factory=list)   # 手すりの辺ごと (柱の線の長さ, 間の数, 手すりの単管, 幅木の板)
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)


def plan_guard(g: Guard) -> Guard:
    if g.kind == 0:
        g.kind = classify(g.w, g.d)
    c = g.checks = []
    must = g.drop >= DROP_MIN
    need = "義務（安衛則 519条 2m 以上）" if must else "推奨（落差 2m 未満でも社内基準は養生を求める）"
    if g.kind in (1, 2, 3):
        t = 24 if g.kind == 3 else 12
        lw, ld = g.w + 2 * LAP_MM, g.d + 2 * LAP_MM
        c.append(Check(f"{g.name}", "OK", f"{KINDS[g.kind]}: 内法 {g.w:.0f}×{g.d:.0f}・落差 {g.drop / 1000:.1f}m で{need}。蓋 {lw:.0f}×{ld:.0f}"
                                          f"（掛かり {LAP_MM:.0f}）の合板 {t}mm" + ("か鋼製（長辺 60cm 超）" if g.kind == 3 else "")
                                          + "、裏にずれ止めの桟木、表に「開口注意」。乗る・物を置くなら 24mm か鋼製"))
    else:
        g.net = g.kind == 4 and must
        if g.kind == 4:
            msg = (f"{KINDS[4]}: 内法 {g.w:.0f}×{g.d:.0f}・落差 {g.drop / 1000:.1f}m で{need}。手すり {RAIL_H:.0f}・中桟 {MID_H:.0f}・"
                   f"幅木 {TOE_H:.0f}（杉足場板）、柱 {POST_MM:.0f} 以内（"
                   + ("固定ベース PKB＋単管 1.0M をアンカー" if g.post == "PKB" else "スタンション NREG で開口の縁をくわえる") + "）")
            st = "OK"
            if g.net:
                nw, nd = g.w + 2 * NET_LAP_MM, g.d + 2 * NET_LAP_MM
                h2 = net_clearance(nw, nd)
                room = g.drop - g.slab_t - NET_DOWN_MM
                ok = room >= h2
                st = "OK" if ok else "WARN"
                msg += (f"。水平ネット {nw / 1000:.1f}×{nd / 1000:.1f}m（10cm 網目）の下の空き {room / 1000:.1f}m ≧ H2 {h2 / 1000:.1f}m"
                        "（安全ネット指針）" + ("" if ok else "が取れない → 養生床か、ネットを複数に分けて L・A を小さく"))
            c.append(Check(g.name, st, msg))
        else:
            c.append(Check(g.name, "OK", f"{KINDS[5]}: 長さ {g.w / 1000:.1f}m・落差 {g.drop / 1000:.1f}m で{need}。手すり {RAIL_H:.0f}・"
                                         f"中桟 {MID_H:.0f}・幅木 {TOE_H:.0f}（杉足場板）、柱 {POST_MM:.0f} 以内（"
                                         + ("固定ベース PKB＋単管 1.0M をアンカー" if g.post == "PKB" else "スタンション NREG で床の縁をくわえる")
                                         + "）。"
                                         "S造のデッキ敷き込み中は親綱支柱＋親綱（スパン 10m 以下かつ 40(H−4)/11・1スパン1人）"))
    _quantity(g)
    return g


def _rail_sides(g: Guard) -> list[tuple[float, int, list, list]]:
    """手すりの辺: 大開口は開口の外 RAIL_OFF の長方形の4辺（手前・奥・左・右）、床の縁は1辺。単管は端の柱から OVER ずつ出す."""
    if g.kind == 4:
        lens = [g.w + 2 * RAIL_OFF_MM] * 2 + [g.d + 2 * RAIL_OFF_MM] * 2
    else:
        lens = [g.w]
    out = []
    for k, L in enumerate(lens):
        n = posts_on(L)
        extra = 2.0 * max(0.0, (L / n) / 4.0 - OVER_MM)          # 突き出しは支柱の間隔の 1/4 まで
        # 幅木: 手前・奥の板が隅を覆うので、左・右の板はその間（両端 100 ずつ短くてよい）
        board = L - 2 * RAIL_OFF_MM if g.kind == 4 and k >= 2 else L
        out.append((L, n, tube_pieces(L + 2 * OVER_MM, extra), plank_pieces(board)))
    return out


def _quantity(g: Guard) -> None:
    """発注の数（品番・規格の長さ別）。手すり柱・クランプ・単管・ジョイント・幅木・ネット・蓋."""
    q = g.quantity = []
    if g.kind in (1, 2, 3):
        lw, ld = g.w + 2 * LAP_MM, g.d + 2 * LAP_MM
        n = min(math.ceil(lw / PLY[0]) * math.ceil(ld / PLY[1]), math.ceil(lw / PLY[1]) * math.ceil(ld / PLY[0]))
        layers = 2 if g.kind == 3 else 1
        q.append(("合板 12mm 910×1820（蓋）", n * layers, "枚"))
        q.append(("桟木 30×40×4000（ずれ止め）", math.ceil(2 * (g.w + g.d) / (CLEAT_MM - 100.0)), "本"))
        q.append(("表示「開口注意」", 1, "枚"))
        return
    g.sides = _rail_sides(g)
    if g.kind == 4:
        n_post = sum(n for _L, n, _t, _p in g.sides)                     # 4辺の間の数＝柱の数（隅は共有）
    else:
        n_post = g.sides[0][1] + 1
    if g.post == "PKB":
        q.append(("PKB 固定ベース", n_post, "個（0.78kg）"))
        q.append(("単管 1.0M（手すり柱）", n_post, "本（2.65kg）"))
        q.append(("あと施工アンカー M10（固定ベース）", 2 * n_post, "本（1つに2本）"))
    else:
        q.append(("NREG スタンション（第1種・締付厚 0〜600）", n_post, "台（8.10kg）"))
    tubes: dict[int, int] = {}
    joints = clamps = 0
    planks: dict[int, int] = {}
    for _L, n, tp, pp in g.sides:
        for _r in (RAIL_H, MID_H):
            for t in tp:
                tubes[t] = tubes.get(t, 0) + 1
            joints += len(tp) - 1
            clamps += n + 1
        for b in pp:
            planks[b] = planks.get(b, 0) + 1
    for t in sorted(tubes, reverse=True):
        q.append((f"単管 {t / 1000:.1f}M（手すり・中桟）", tubes[t], f"本（{TUBES[t]:g}kg）"))
    if joints:
        q.append(("PCJ 直線ジョイント", joints, "個（0.60kg）"))
    q.append(("ARC1 兼用直交クランプ", clamps, "個（0.73kg。手すり・中桟と柱）"))
    for b in sorted(planks, reverse=True):
        q.append((f"杉足場板 {PLANKS[b]} 35×210×{b}（幅木）", planks[b], "枚"))
    q.append(("番線 #10（幅木の留め）", 2 * sum(planks.values()), "本（板の両端）"))
    if g.net:
        nw, nd = g.w + 2 * NET_LAP_MM, g.d + 2 * NET_LAP_MM
        for (a, b) in net_pick(nw, nd):
            q.append((f"水平ネット 100mm 目 {a / 1000:g}×{b / 1000:g}m", 1, "枚"))
        q.append(("ネットハンガー（支持点）", math.ceil(2 * (nw + nd) / NET_SUP_MM) + 4, f"個（{NET_SUP_MM:.0f} ごと＋隅）"))
    q.append(("表示「開口注意」" if g.kind == 4 else "表示「墜落注意」", 1 if g.kind == 4 else max(1, math.ceil(g.w / 5000.0)), "枚"))


def oriented_box(poly: list) -> tuple[tuple[float, float], float, float, float]:
    """多角形 → 一番長い辺の向きにそろえた外接長方形 (隅, 長さ 長い辺の向き, 幅, 向き 度)."""
    n = len(poly)
    i = max(range(n), key=lambda k: math.dist(poly[k], poly[(k + 1) % n]))
    a, b = poly[i], poly[(i + 1) % n]
    L = math.dist(a, b) or 1.0
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    v = (-u[1], u[0])
    s = [(p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1] for p in poly]
    t = [(p[0] - a[0]) * v[0] + (p[1] - a[1]) * v[1] for p in poly]
    corner = (a[0] + u[0] * min(s) + v[0] * min(t), a[1] + u[1] * min(s) + v[1] * min(t))
    return corner, max(s) - min(s), max(t) - min(t), math.degrees(math.atan2(u[1], u[0]))


def inside(p, poly) -> bool:
    x, y = p
    ins = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            ins = not ins
    return ins


def drop_below(p, z_top: float, slabs: list, ground: float = 0.0) -> float:
    """点 p（床の上端 z_top）から下の床（その点を含み開口に掛からない一番高い床）か地盤までの落差 mm."""
    best = ground
    for s in slabs:
        if s["top"] < z_top - 50.0 and s["top"] > best and inside(p, s["outline"]) and not any(inside(p, h) for h in s["holes"]):
            best = s["top"]
    return z_top - best


def edge_runs(slab: dict, others: list) -> list[tuple[tuple, tuple]]:
    """床の外形の辺のうち、外に同じ高さの床が続かない辺（床の縁）."""
    out = []
    pts = slab["outline"]
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        L = math.dist(a, b)
        if L < 100.0:
            continue
        m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        if (m[0] + nx - cx) ** 2 + (m[1] + ny - cy) ** 2 < (m[0] - nx - cx) ** 2 + (m[1] - ny - cy) ** 2:
            nx, ny = -nx, -ny                                # 外向き
        q = (m[0] + nx * 300.0, m[1] + ny * 300.0)
        if any(abs(o["top"] - slab["top"]) < 50.0 and inside(q, o["outline"]) for o in others if o is not slab):
            continue
        out.append((a, b))
    return out


def part_params(g: Guard) -> dict:
    """部品 ashiba_opening のパラメータ。手すりの単管・幅木の板は辺の番号（1〜4）と長さ（mm）の並び（3D で1本ずつ描く）."""
    rs, rl, bs, bl = [], [], [], []
    for k, (_L, _n, tp, pp) in enumerate(g.sides, 1):
        rs += [k] * len(tp)
        rl += tp
        bs += [k] * len(pp)
        bl += pp
    return {"rlS": ",".join(map(str, rs)), "rlL": ",".join(map(str, rl)), "tbS": ",".join(map(str, bs)),
            "tbL": ",".join(map(str, bl)), "postK": 2 if g.post == "PKB" else 1, "opW": g.w / 1000.0, "opD": g.d / 1000.0,
            "opKind": g.kind, "netOn": g.net, "slabT": g.slab_t / 1000.0, "edSide": g.side, "opName": g.name}


ORDER = ("NREG", "PKB", "単管 1.0M（手すり柱）", "あと施工", "単管", "PCJ", "ARC1", "杉足場板", "番線", "水平ネット", "ネットハンガー",
         "合板", "桟木", "表示")


def order_table(tot: dict, order: tuple = ORDER, title: str = "## 発注表（品番・規格の長さ別）") -> list[str]:
    """{品名: [数, 単位（1つの重さ kg を含めば重さ計を出す）]} → 発注表の行（種類の順・長い順）."""
    out = ["", title, "", "| 品名・品番・規格 | 数 | 単位・1つの重さ | 重さ計 |", "|---|---|---|---|"]
    total_kg = 0.0

    def key(item):
        name = item[0]
        cat = next((i for i, h in enumerate(order) if name.startswith(h)), len(order))
        m = re.search(r"L=([0-9.]+)m|([0-9.]+)M|×(\d+)（", name)
        ln = 0.0
        if m:
            ln = float(m.group(1)) * 1000 if m.group(1) else float(m.group(2)) * 1000 if m.group(2) else float(m.group(3))
        return (cat, -ln, name)

    for a, (n, u) in sorted(tot.items(), key=key):
        m = re.search(r"([0-9.]+)kg", u)
        kg = n * float(m.group(1)) if m else 0.0
        total_kg += kg
        out.append(f"| {a} | {round(n, 1):g} | {u} | {kg:.1f}kg |" if kg else f"| {a} | {round(n, 1):g} | {u} | |")
    out.append(f"| 計 | | | {total_kg:.0f}kg |")
    return out


def rail_order(lengths: list[float], post: str = "NREG") -> list[tuple[str, float, str]]:
    """手すりの辺（柱の線の長さ mm）の並び → 手すり柱・単管（定尺）・ジョイント・クランプ・幅木の板の発注の数（辺ごとに端の柱を数える）."""
    q = []
    n_post = joints = clamps = 0
    tubes: dict[int, int] = {}
    planks: dict[int, int] = {}
    for L in lengths:
        n = posts_on(L)
        extra = 2.0 * max(0.0, (L / n) / 4.0 - OVER_MM)
        tp = tube_pieces(L + 2 * OVER_MM, extra)
        n_post += n + 1
        for _r in (RAIL_H, MID_H):
            for t in tp:
                tubes[t] = tubes.get(t, 0) + 1
            joints += len(tp) - 1
            clamps += n + 1
        for b in plank_pieces(L):
            planks[b] = planks.get(b, 0) + 1
    if post == "PKB":
        q += [("PKB 固定ベース", n_post, "個（0.78kg）"), ("単管 1.0M（手すり柱）", n_post, "本（2.65kg）"),
              ("あと施工アンカー M10（固定ベース）", 2 * n_post, "本（1つに2本）")]
    else:
        q.append(("NREG スタンション（第1種・締付厚 0〜600）", n_post, "台（8.10kg）"))
    for t in sorted(tubes, reverse=True):
        q.append((f"単管 {t / 1000:.1f}M（手すり・中桟）", tubes[t], f"本（{TUBES[t]:g}kg）"))
    if joints:
        q.append(("PCJ 直線ジョイント", joints, "個（0.60kg）"))
    q.append(("ARC1 兼用直交クランプ", clamps, "個（0.73kg。手すり・中桟と柱）"))
    for b in sorted(planks, reverse=True):
        q.append((f"杉足場板 {PLANKS[b]} 35×210×{b}（幅木）", planks[b], "枚"))
    q.append(("番線 #10（幅木の留め）", 2 * sum(planks.values()), "本（板の両端）"))
    return q


def rail_strings(lengths: list[float], sides: list[int]) -> dict:
    """部品へ渡す手すりの単管・幅木の板の並び（辺の番号と長さ mm）."""
    rs, rl, bs, bl = [], [], [], []
    for k, L in zip(sides, lengths):
        n = posts_on(L)
        extra = 2.0 * max(0.0, (L / n) / 4.0 - OVER_MM)
        tp, pp = tube_pieces(L + 2 * OVER_MM, extra), plank_pieces(L)
        rs += [k] * len(tp)
        rl += tp
        bs += [k] * len(pp)
        bl += pp
    return {"rlS": ",".join(map(str, rs)), "rlL": ",".join(map(str, rl)), "tbS": ",".join(map(str, bs)), "tbL": ",".join(map(str, bl))}


def report(guards: list[Guard]) -> str:
    out = ["# 開口養生・床の縁の手すり", "",
           "出典: 安衛則 519・552・563・536・537条、仮設工業会 墜落防護工（基安安発0515001）、安全ネット指針（昭和51年 技術上の指針"
           "公示第8号）、厚労省の教材・芝建・矢作建設の社内基準。開口の大きさの区分は目安（公的な基準は無い）", "",
           "| 開口・縁 | 区分 | 大きさ | 落差 | 判定 | 内容 |", "|---|---|---|---|---|---|"]
    tot: dict[str, list] = {}
    for g in guards:
        for x in g.checks:
            out.append(f"| {g.name} | {KINDS[g.kind]} | {g.w:.0f}×{g.d:.0f} | {g.drop / 1000:.1f}m | {x.status} | {x.message} |")
        for a, n, unit in g.quantity:
            row = tot.setdefault(a, [0.0, unit])
            row[0] += n
    out += order_table(tot)
    out += ["", "ネットは使い始めて1年以内、その後6か月ごとに試験用の糸で試験（安全ネット指針）。手すりを作業で外したら墜落制止用器具と"
            "立入禁止で代え、終わればすぐ戻す（519条2項）。3m 以上の高さからの投下はダストシュート等（536条）", ""]
    return "\n".join(out)
