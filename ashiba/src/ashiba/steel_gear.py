"""鉄骨建て方の仮設材の割付（利用者の指定 2026-11-07「必要な仮設材はGDL作成して　LOD500で　新たに部材生成するときはレイヤー作成してちょ」）.

節とピース（steel_erection.py）から仮設材を生成する。部品は ashiba_sgear、種類ごとにレイヤー「鉄骨仮設_…」へ。

出典:
- 日建リース工業 仮設資材カタログ Vol.10: NK ステージ NKS 1860×710・24.70kg・200kg/台（p173）、手摺 NKSHT 550×H962 φ35・1.60kg（p173）、継手から床面 750（p173）、
  渡り足場 2NKS07 柱 200〜700（p176・179）、NK ハンガー NKH0714/1014/1414（p164）、NKS タラップ 幅 335・踏さん 350（p186）、ライフブロック LB15 224×284×107・6.93kg（p199）
- コンドー吊りピース（解説サイトの転記）: 底 130・高さ 100・孔 φ42、板厚 9・12・16（2 枚で 3t・6t・10t。柱は 1 段上）【目安】
- エレクションピース: 厚さ 12〜19・幅 100〜150（解説の目安）【目安】。建入れワイヤ φ12＋LB016 の組（参考セット）【目安】
- 水平ネット: 明治商工 クランプ＝外周÷1.5×枚数。ネットは梁の下 0.3m【目安】
本数の決めは公的な基準が見つからない: 溶接足場は節の継手ごと、ハンガーは継手の両側、タラップは柱ごと、ブロックは工区・節に 1 つ、ワイヤは柱に 2 本【目安】.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

KINDS = {1: "溶接足場", 2: "ボルト足場", 3: "昇降", 4: "水平ネット", 5: "安全ブロック", 6: "吊りピース", 7: "エレクションピース", 8: "建入れワイヤ"}
LAYER = "鉄骨仮設_"
HANGERS = ((650.0, "NKH0714", 0.812, 17.40), (950.0, "NKH1014", 1.112, 19.70), (1350.0, "NKH1414", 1.512, 23.50))
LADDERS = ((3.85, "NKSTR40", 10.00), (1.75, "NKSTR20", 4.50), (1.05, "NKSTR10T", 3.00))
STAGE_DOWN = 0.75                      # 継手からステージの床面（p173 の推奨）
NET_DOWN = 0.3                         # 梁の下のネット【目安】
LIFE_BLOCK = ("ライフブロック LB15", 15.0, 6.93)


@dataclass
class Gear:
    kind: int
    step: int
    x: float                           # mm
    y: float
    z: float
    name: str
    kg: float = 0.0
    params: dict = field(default_factory=dict)

    @property
    def layer(self) -> str:
        return LAYER + KINDS[self.kind]


def lug_t(weight: float | None) -> float:
    """吊りピースの板厚 mm（柱は 1 段上: 2t 以下 9・5t 以下 12・それ以上 16）【目安】."""
    w = weight or 0.0
    return 9.0 if w <= 2.0 else 12.0 if w <= 5.0 else 16.0


def hanger_of(splice_len: float) -> tuple:
    """継手の添え板の長さ mm からハンガーの型式."""
    return next((h for h in HANGERS if splice_len <= h[0]), HANGERS[-1])


def ladders_for(length: float) -> list:
    """長さ m に足りるタラップの組（長いものから）."""
    out = []
    left = length
    while left > 0.06:
        pick = next((t for t in LADDERS if t[0] <= left + 0.06), LADDERS[-1])
        out.append(pick)
        left -= pick[0]
    return out


def plan_gear(plan, steps: list, sections: dict, splice_of) -> list:
    """ピースと節から仮設材の一覧. 継手の高さは節の上端（最上節を除く）."""
    gears: list = []
    step_of = {(s.zone, s.node): s.no for s in steps}
    tops = {}
    for p in plan.columns:
        tops.setdefault((p.x, p.y), []).append(p)
    cx = sum(p.x for p in plan.columns) / max(1, len(plan.columns))
    cy = sum(p.y for p in plan.columns) / max(1, len(plan.columns))
    xs = sorted({round(p.x) for p in plan.columns})
    ys = sorted({round(p.y) for p in plan.columns})
    for key, pcs in tops.items():
        pcs = sorted(pcs, key=lambda q: q.node)
        last = pcs[-1].node
        for p in pcs:
            st = step_of[(p.zone, p.node)]
            cw, cd = p.w / 1000.0, p.d / 1000.0
            base = {"cW": cw, "cD": cd, "sgA": p.ang}
            # 吊りピース 2 枚
            t = lug_t(p.weight)
            gears.append(Gear(6, st, p.x, p.y, p.z1, f"吊りピース PL-{t:.0f}×2", 0.0, {**base, "sgT": t / 1000.0}))
            # タラップ（柱の外の面）
            side = -1 if p.y <= cy else 1
            z = p.z0
            for ln, code, kg in ladders_for((p.z1 - p.z0) / 1000.0 - 0.3):
                gears.append(Gear(3, st, p.x, p.y + side * (p.d / 2.0), z, code, kg, {**base, "sgL": ln, "sgS": side}))
                z += ln * 1000.0
            # 建入れワイヤ（X と Y の隣の柱へ）
            for axis, seq, v in ((0, xs, round(p.x)), (1, ys, round(p.y))):
                i = seq.index(v)
                j = i + 1 if i + 1 < len(seq) else i - 1
                if j < 0:
                    continue
                d = (seq[j] - v) / 1000.0
                gears.append(Gear(8, st, p.x, p.y, p.z1 - 300.0, "ワイヤ φ12＋レバーブロック LB016", 0.0,
                                  {"sgX": d if axis == 0 else 0.0, "sgY": d if axis == 1 else 0.0, "sgZ": -(p.z1 - p.z0 - 600.0) / 1000.0}))
            if p.node != last:
                gears.append(Gear(1, st, p.x, p.y, p.z1 - STAGE_DOWN * 1000.0, "NK ステージ NKS×2・2NKS07×2", 24.70 * 2 + 8.00 * 2 + 1.60 * 8, {**base}))
                gears.append(Gear(7, st, p.x, p.y, p.z1, "エレクションピース PL-16×100", 0.0, {**base, "sgH": 0.15, "sgT": 0.016}))
    for s in steps:
        if s.columns:
            p = max(s.columns, key=lambda q: q.z1)
            gears.append(Gear(5, s.no, p.x, p.y, p.z1 + 100.0, LIFE_BLOCK[0], LIFE_BLOCK[2], {"sgL": min(LIFE_BLOCK[1], (p.z1 - p.z0) / 1000.0)}))
    # ハンガー: 梁のピースの両端の継手に両側
    seen = set()
    for s in steps:
        for b in s.beams:
            sec = sections.get(b.mark)
            sp = splice_of(sec) if sec else None
            code = hanger_of(sp.length if sp else 650.0)
            a = math.radians(b.ang)
            for t in (0.0, b.length):
                x, y = b.x + t * math.cos(a), b.y + t * math.sin(a)
                k = (round(x), round(y), round(b.z))
                if k in seen:
                    continue
                seen.add(k)
                top = b.z + b.h / 2.0
                half = (sec.b if sec else b.w) / 2.0
                for side in (-1, 1):
                    gears.append(Gear(2, s.no, x - side * half * math.sin(a), y + side * half * math.cos(a), top, code[1], code[3],
                                      {"sgA": b.ang, "sgW": code[2], "sgB": 0.65, "sgH": 1.655, "sgS": side}))
    # 水平ネット: 柱の通りの区画ごと・階ごと
    floors = sorted({(round(b.z + b.h / 2.0), b.node) for b in plan.beams})
    for top, node in floors:
        for x0, x1 in zip(xs, xs[1:]):
            for y0, y1 in zip(ys, ys[1:]):
                zone = next((s.zone for s in steps if s.node == node and any(abs(q.x - x0) < 1 for q in s.columns)), 1)
                st = step_of.get((zone, node), steps[0].no if steps else 1)
                lx, ly = (x1 - x0) / 1000.0, (y1 - y0) / 1000.0
                gears.append(Gear(4, st, float(x0), float(y0), top - NET_DOWN * 1000.0, f"水平ネット {lx:.1f}×{ly:.1f}m", 0.0, {"sgX": lx, "sgY": ly}))
    return gears


def quantities(gears: list) -> list:
    """[(種類, 名前, 個数, 重量 kg)]（種類の順）."""
    tot: dict = {}
    for g in gears:
        k = (g.kind, g.name)
        n, w = tot.get(k, (0, 0.0))
        tot[k] = (n + 1, w + g.kg)
    return [(KINDS[k[0]], k[1], n, round(w, 1)) for k, (n, w) in sorted(tot.items())]


def to_sheet(wb, gears: list) -> None:
    sh = wb.sheet("仮設材の数量")
    sh.add_title("鉄骨建て方の仮設材", 4)
    sh.add_header(["種類", "品名", "数", "重量 kg"])
    for r in quantities(gears):
        sh.add(list(r))
    sh.add(["本数の決めに公的な基準は無い。溶接足場は節の継手ごと、ハンガーは継手の両側、タラップは柱ごと、ブロックは工区・節に 1 つ、ワイヤは柱に 2 本【目安】"])
    for i, wdt in enumerate((16, 34, 8, 10)):
        sh.set_width(i, wdt)
