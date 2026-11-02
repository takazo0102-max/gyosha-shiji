"""仮設電気・給排水（利用者の指定 2026-11-02「各図面を参考にして、図面かボタンを追加してちょ」の続き。施工図の手引き
（建築施工図研究会 平成16年）p.23〜24 の総合仮設計画図の「電気・給排水設備」）.

平面に引いた線を、窓で選んだ種類の仮設電気・給排水として描く（2D の線・塗り・文字。レイヤー「仮設_電気給排水」）:
- 線のもの: 給水管（実線と「25-V」）・排水管（太い実線と「100-V」・流れの向き）・地中埋設電線（一点鎖線）・架空電線
  （実線に電線の数の斜線と「(22)」）。線の向き＝排水の流れの向き
- 機器（線の始め＝芯、線の向き＝向き）: キュービクル（点の塗り）・電灯用分電盤（半分の塗り）・動力用分電盤（×）・電灯動力用
  分電盤（塗りの×）・量水器（□に M）・止水栓（向かい合う三角）・仮設便所（ユニット）・沈砂槽（□に「沈砂槽」）
記号の形は手引き p.24 の描き方にならう（ashiba の線で描き直したもの）。

判定（帳票 ashiba_out/仮設電気給排水.md）:
- 排水管の勾配: SHASE-S206-2009（豊橋市 排水設備指針 表5-1-2 の引用）の標準 管径 65 以下 1/50・75 と 100 は 1/100・125 以上
  1/200 で、線の長さの落差を出す（手引き p.24: 排水は勾配が要るので長くしない）。下水に放流する前に沈砂槽で土砂を除く
  （手引き p.24。掘削の湧水・雨水は直接下水へ流せない）
- 架空電線と移動式クレーン: 送配電線からの離隔の目安 低圧 1m・高圧 1.2m・特別高圧 2m（6万V 以上は 1万V ごとに 20cm 足す。
  厚生労働省 職場のあんぜんサイト 災害事例 https://anzeninfo.mhlw.go.jp/anzen/sai/taisaku/sai10-71-40-1.htm）。置いたクレーンの
  作業半径の円（クレーンの控えの外接箱）と架空電線が近ければ要確認（安衛則349条: 監視人・防護管、電力会社と事前に打合せ）。
  敷地の周りの架空線は防護管（養生管）で感電防止（手引き p.23）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

LINE_KINDS = ("給水管", "排水管", "地中埋設電線", "架空電線")
UNIT_KINDS = ("キュービクル", "電灯用分電盤", "動力用分電盤", "電灯動力用分電盤", "量水器", "止水栓", "仮設便所", "沈砂槽")
KINDS = LINE_KINDS + UNIT_KINDS
VOLTAGES = {"低圧": 1000.0, "高圧": 1200.0, "特別高圧": 2000.0}      # 離隔の目安 mm（6万V 以上は別に足す）
SLOPES = ((65.0, 50.0), (100.0, 100.0), (1e9, 200.0))               # 管径 mm 以下 → 勾配 1/n（SHASE-S206-2009）
UNIT_SIZE = {"キュービクル": (2000.0, 1200.0), "電灯用分電盤": (600.0, 300.0), "動力用分電盤": (600.0, 300.0),
             "電灯動力用分電盤": (800.0, 300.0), "量水器": (400.0, 400.0), "止水栓": (300.0, 300.0),
             "仮設便所": (900.0, 1400.0), "沈砂槽": (1500.0, 1000.0)}   # 平面の大きさ（記号。製品の寸法ではない・目安）
SOURCE_SEP = "厚生労働省 職場のあんぜんサイト 災害事例（送配電線からの離隔の目安）"
SOURCE_SLOPE = "SHASE-S206-2009（豊橋市 排水設備指針 表5-1-2）"


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Item:
    name: str
    kind: str
    pts: list                      # 線は点列、機器は [芯, 向きの点]（mm）
    dia: float = 0.0               # 管径 mm（給水 25・排水 100）
    wires: int = 3                 # 架空電線の本数
    volt: str = "低圧"             # 架空電線の電圧の区分
    kv: float = 0.0                # 特別高圧の電圧 kV（6万V 以上の加算）
    checks: list = field(default_factory=list)

    @property
    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.pts, self.pts[1:]))


def slope_of(dia: float) -> float:
    """排水管の標準の勾配 1/n の n."""
    return next(n for d, n in SLOPES if dia <= d + 1e-6)


def separation(volt: str, kv: float = 0.0) -> float:
    """送配電線からの離隔の目安 mm（特別高圧は 6万V 以上で 1万V ごとに 200 足す）."""
    base = VOLTAGES.get(volt, 1000.0)
    if volt == "特別高圧" and kv > 60.0:
        base += 200.0 * math.ceil((kv - 60.0) / 10.0)
    return base


def _seg_dist(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _box_dist(pts, box) -> float:
    """線（点列）と矩形（xMin, yMin, xMax, yMax）の平面の距離（重なれば 0）."""
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    d = min(_seg_dist(c, a, b) for c in corners for a, b in zip(pts, pts[1:]))
    for p in pts:
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            return 0.0
        d = min(d, min(_seg_dist(p, corners[k], corners[(k + 1) % 4]) for k in range(4)))
    return d


def check(it: Item, cranes: list | None = None) -> Item:
    """判定（排水の落差・架空電線とクレーン）. cranes はクレーンの外接箱 [(名前, (xMin, yMin, xMax, yMax))]（mm）."""
    c = it.checks = []
    if it.kind == "排水管":
        n = slope_of(it.dia or 100.0)
        fall = it.length / n
        c.append(Check("勾配", "OK", f"管径 {it.dia or 100:.0f} の標準の勾配 1/{n:.0f} で、長さ {it.length / 1000:.1f}m の落差 {fall:,.0f}mm"
                                    f"（{SOURCE_SLOPE}）。長くするほど深くなるので、放流先の桝の高さを確かめる"))
        c.append(Check("沈砂槽", "OK", "掘削の湧水・雨水は直接下水へ流せない。沈砂槽で土砂を除いてから放流し、下水道局へ届出（手引き p.24）"))
    elif it.kind == "架空電線":
        need = separation(it.volt, it.kv)
        near = []
        for nm, box in cranes or []:
            d = _box_dist(it.pts, box)
            if d < need + 1e-6:
                near.append((nm, d))
        if near:
            nm, d = min(near, key=lambda x: x[1])
            c.append(Check("離隔", "WARN", f"{it.volt}の架空電線と {nm} の範囲が {d:,.0f}mm（離隔の目安 {need:,.0f}mm 以上）。ジブ・ワイヤが近づかない"
                                         "ように監視人を置き、防護管で養生し、電力会社と事前に打合せる（安衛則349条。" + SOURCE_SEP + "）"))
        else:
            c.append(Check("離隔", "OK", f"{it.volt}の架空電線（離隔の目安 {need:,.0f}mm 以上）。クレーンで荷取りするときは監視人・防護管・"
                                       "電力会社との打合せ（安衛則349条。" + SOURCE_SEP + "）"))
    elif it.kind == "キュービクル":
        c.append(Check("受電", "OK", "高圧受電（50kW 以上）はキュービクルと引込柱。申込みから使えるまで時間がかかる（手引き p.27）"))
    return it


def _rot(p, ang, o):
    ca, sa = math.cos(ang), math.sin(ang)
    return (o[0] + p[0] * ca - p[1] * sa, o[1] + p[0] * sa + p[1] * ca)


def drawing(it: Item) -> dict:
    """記号 → {"lines": [(点列, 破線の種類)], "fills": [(多角形, 塗りの濃さ 0〜1)], "texts": [(点, 文字, 高さ mm, 角度 rad)]}（mm）.
    破線の種類は "solid"・"dash"・"chain"（一点鎖線）."""
    lines, fills, texts = [], [], []
    if it.kind in LINE_KINDS:
        pts = it.pts
        a, b = pts[0], pts[-1]
        mid = len(pts) // 2
        p, q = pts[max(0, mid - 1)], pts[mid] if mid < len(pts) else pts[-1]
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        lab = {"給水管": f"{it.dia or 25:.0f}-V（ビニール管 φ{it.dia or 25:.0f}）",
               "排水管": f"{it.dia or 100:.0f}-V（ビニール管 φ{it.dia or 100:.0f}）",
               "地中埋設電線": "地中埋設電線", "架空電線": f"架空電線 {it.volt}（{it.wires}本）"}[it.kind]
        lines.append((pts, "chain" if it.kind == "地中埋設電線" else "solid"))
        texts.append((_rot((0.0, 250.0), ang, m), lab, 250.0, ang))
        if it.kind == "架空電線":
            for k in range(max(1, it.wires)):                       # 電線の数の斜線
                o = _rot((-150.0 * (it.wires - 1) / 2 + 150.0 * k, 0.0), ang, m)
                lines.append(([_rot((-80.0, -150.0), ang, o), _rot((80.0, 150.0), ang, o)], "solid"))
        if it.kind == "排水管":                                      # 流れの向き（終わりへ）の矢じり
            ang2 = math.atan2(b[1] - pts[-2][1], b[0] - pts[-2][0])
            lines.append(([_rot((-300.0, 150.0), ang2, b), b, _rot((-300.0, -150.0), ang2, b)], "solid"))
        return {"lines": lines, "fills": fills, "texts": texts}
    o = it.pts[0]
    d = it.pts[1] if len(it.pts) > 1 else (o[0] + 1.0, o[1])
    ang = math.atan2(d[1] - o[1], d[0] - o[0])
    w, h = UNIT_SIZE[it.kind]
    R = lambda x, y: _rot((x, y), ang, o)
    box = [R(-w / 2, -h / 2), R(w / 2, -h / 2), R(w / 2, h / 2), R(-w / 2, h / 2)]
    lines.append((box + box[:1], "solid"))
    if it.kind == "キュービクル":
        fills.append((box, 0.25))
    elif it.kind == "電灯用分電盤":
        fills.append(([box[0], box[1], box[2]], 0.9))
    elif it.kind in ("動力用分電盤", "電灯動力用分電盤"):
        lines += [([box[0], box[2]], "solid"), ([box[1], box[3]], "solid")]
        if it.kind == "電灯動力用分電盤":
            fills += [([box[0], box[1], R(0, 0)], 0.9), ([box[2], box[3], R(0, 0)], 0.9)]
    elif it.kind == "量水器":
        texts.append((R(0, -100.0), "M", 250.0, ang))
    elif it.kind == "止水栓":
        lines = [([R(-w / 2, -h / 2), R(w / 2, h / 2), R(w / 2, -h / 2), R(-w / 2, h / 2), R(-w / 2, -h / 2)], "solid")]
        fills = [([R(-w / 2, -h / 2), R(0, 0), R(-w / 2, h / 2)], 0.9), ([R(w / 2, -h / 2), R(0, 0), R(w / 2, h / 2)], 0.9)]
    elif it.kind == "仮設便所":
        lines += [([R(-w / 2, h / 2 - 300.0), R(w / 2, h / 2 - 300.0)], "solid")]
    elif it.kind == "沈砂槽":
        lines += [([R(-w / 2 + 100.0, -h / 2 + 100.0), R(w / 2 - 100.0, -h / 2 + 100.0), R(w / 2 - 100.0, h / 2 - 100.0),
                    R(-w / 2 + 100.0, h / 2 - 100.0), R(-w / 2 + 100.0, -h / 2 + 100.0)], "solid")]
    texts.append((R(0, h / 2 + 200.0), it.kind, 250.0, ang))
    return {"lines": lines, "fills": fills, "texts": texts}


def report(items: list[Item]) -> str:
    out = ["# 仮設電気・給排水", "",
           f"出典: 施工図の手引き（建築施工図研究会）p.23〜24・p.27、{SOURCE_SLOPE}、{SOURCE_SEP}、労働安全衛生規則349条。"
           "記号の大きさは目安", "", "| 名前 | 種類 | 長さ・大きさ | 判定 | 内容 |", "|---|---|---|---|---|"]
    count: dict[str, int] = {}
    total: dict[str, float] = {}
    for it in items:
        count[it.kind] = count.get(it.kind, 0) + 1
        size = (f"{it.length / 1000:.1f}m" if it.kind in LINE_KINDS else "□{:.0f}×{:.0f}".format(*UNIT_SIZE[it.kind]))
        if it.kind in LINE_KINDS:
            key = it.kind + (f" φ{it.dia:.0f}" if it.dia else "")
            total[key] = total.get(key, 0.0) + it.length
        rows = it.checks or [Check("", "OK", "")]
        for ck in rows:
            out.append(f"| {it.name} | {it.kind} | {size} | {ck.status} | {ck.item + ': ' if ck.item else ''}{ck.message} |")
    out += ["", "## 数量", "", "| 品 | 数・長さ |", "|---|---|"]
    out += [f"| {k} | {v / 1000:.1f}m |" for k, v in total.items()]
    out += [f"| {k} | {n} |" for k, n in count.items() if k in UNIT_KINDS]
    return "\n".join(out) + "\n"
