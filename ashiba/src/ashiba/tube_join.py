"""別の足場を単管でつなぐ（部品 ashiba_tube。GLOOBE の「別の足場と接続する単管」に当たる。2026-11-02 の開発ループ）.

隣り合う別の足場（別の面・別の系列・建物の間で繋がらない所）の支柱から支柱へ、平面に線を1本引き、層の高さごとに単管を
直交クランプで留めて繋ぐ。手すり・中桟の高さにも足せる（足場の間のすき間が開口になる所）、層の間に斜めの補強（自在クランプ）も。
規格品で発注できる詳細さで（利用者の指定 2026-11-01: イメージじゃなく実際の規定の長さで発注できるくらい詳細に）。

出典（調べた資料）:
- 日建リース工業 仮設資材カタログ Vol.10 p372 単管パイプ（STK500 φ48.6×2.4、長さ別の重さ。足場用は 2.0〜6.0M、0.5〜1.8M は
  型枠用・ピン無し）・p378 兼用直交クランプ ARC1（0.73kg・スベリ耐力 4.9kN）・兼用自在クランプ ARC2（0.70kg・3.43kN）
- 労働安全衛生規則 570条1項3号（鋼管の接続部又は交差部は適合した附属金具で確実に接続・緊結）・4号（筋かいで補強）、
  563条1項3号ロ（わく組以外の足場は手すり等及び中桟等。高さ 85cm 以上・35〜50cm は 552条1項4号）
単管の端の突き出し（クランプの外へ 50mm 以上・支柱の間隔の 1/4 以下）は opening_guard と同じ決め（目安）。クランプは支柱の
コマ・緊結部を避けて付ける（くさび式は布材の緊結部の上下）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .opening_guard import OVER_MM, MID_H, RAIL_H, TUBES, order_table

CLAMPS = {"ARC1": ("ARC1 兼用直交クランプ", 0.73, 4.9), "ARC2": ("ARC2 兼用自在クランプ", 0.70, 3.43)}   # 品番 → (品名, kg, スベリ耐力 kN)
TUBE_MAX = max(TUBES)                    # 6.0M（7.0M は型枠用のみ）
SPAN_MIN = 100.0                         # 支柱どうしが近すぎる（同じ支柱）


def pick_tube(need: float) -> int:
    """要る長さ need mm 以上でいちばん短い単管の長さ mm（無ければ 0）."""
    return min((t for t in TUBES if t >= need - 1e-6), default=0)


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Join:
    name: str
    a: tuple[float, float]               # 始めの足場の支柱の芯 mm
    b: tuple[float, float]               # 終わりの足場の支柱の芯 mm
    levels: list[float]                  # つなぐ高さ（足場の立つ面から）mm
    guard: bool = False                  # 各層の上に手すり・中桟の単管も
    brace: bool = False                  # 層の間に斜めの補強
    tube: int = 0                        # 横の単管の長さ mm
    brace_tubes: list[int] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)

    @property
    def span(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def rows(self) -> list[float]:
        """横の単管の高さ mm（層の高さ＋手すり・中桟）."""
        out = []
        for z in sorted(self.levels):
            out.append(z)
            if self.guard:
                out += [z + MID_H, z + RAIL_H]
        return out


def plan_join(j: Join) -> Join:
    c = j.checks = []
    L = j.span
    j.tube = pick_tube(L + 2.0 * OVER_MM) if L >= SPAN_MIN else 0
    if L < SPAN_MIN:
        c.append(Check("長さ", "NG", "線の始めと終わりが同じ支柱（つなぐ相手の足場の支柱まで線を引く）"))
    elif not j.tube:
        c.append(Check("長さ", "NG", f"支柱の間 {L:.0f}mm は単管 {TUBE_MAX / 1000:.1f}M に両端の突き出し {OVER_MM:.0f} を足して届かない → "
                                    "間に支柱（単管の建地とベース・根がらみ）を立てて2本に分ける"))
    else:
        ov = (j.tube - L) / 2.0
        st = "OK" if ov <= L / 4.0 + 1e-6 or j.tube == min(TUBES) else "WARN"
        c.append(Check("長さ", st, f"支柱の間 {L:.0f}mm に単管 {j.tube / 1000:.1f}M（両端の突き出し {ov:.0f}mm"
                                   + ("" if st == "OK" else f"。支柱の間の 1/4 {L / 4:.0f} を超えるので、短い単管を選ぶか端を切る") + "）"))
    if not j.levels:
        c.append(Check("高さ", "NG", "つなぐ高さが無い"))
    j.brace_tubes = []
    lv = sorted(j.levels)
    if j.brace and L >= SPAN_MIN:
        for z0, z1 in zip(lv, lv[1:]):
            need = math.hypot(L, z1 - z0) + 2.0 * OVER_MM
            t = pick_tube(need)
            j.brace_tubes.append(t)
            if not t:
                c.append(Check("斜めの補強", "NG", f"{z0:.0f}〜{z1:.0f} の斜めは {need:.0f}mm で単管 6.0M に入らない → 1層おきに掛ける"))
    nm, kg, slip = CLAMPS["ARC1"]
    c.append(Check("緊結", "OK", f"単管の両端を {nm}（スベリ耐力 {slip:g}kN）で支柱に留める（安衛則570条1項3号）。くさび式は支柱のコマ・"
                                "布材の緊結部を避けて上下にずらす"))
    if j.guard:
        c.append(Check("手すり", "OK", f"層ごとに手すり {RAIL_H:.0f}・中桟 {MID_H:.0f}（安衛則563条1項3号ロ・552条: 85cm 以上・35〜50cm）。足場の間の"
                                     "すき間に作業床が無いときは、床の端として幅木・ネットも要る"))
    if j.brace:
        nm2, _kg2, slip2 = CLAMPS["ARC2"]
        c.append(Check("斜めの補強", "OK", f"層の間に斜めの単管を {nm2}（スベリ耐力 {slip2:g}kN）で（向きを層ごとに変える。安衛則570条1項4号の筋かい）"))
    _quantity(j)
    return j


def _quantity(j: Join) -> None:
    q = j.quantity = []
    if not j.tube or not j.levels:
        return
    rows = j.rows
    q.append((f"単管 {j.tube / 1000:.1f}M（つなぎ・手すり）", len(rows), f"本（{TUBES[j.tube]:g}kg）"))
    braces = [t for t in j.brace_tubes if t]
    for t in sorted(set(braces), reverse=True):
        q.append((f"単管 {t / 1000:.1f}M（斜めの補強）", braces.count(t), f"本（{TUBES[t]:g}kg）"))
    nm, kg, _s = CLAMPS["ARC1"]
    q.append((nm, 2 * len(rows), f"個（{kg:g}kg。単管の両端）"))
    if braces:
        nm2, kg2, _s2 = CLAMPS["ARC2"]
        q.append((nm2, 2 * len(braces), f"個（{kg2:g}kg。斜めの両端）"))


def part_params(j: Join) -> dict:
    return {"tbL": j.span / 1000.0, "tbLen": (j.tube or j.span) / 1000.0, "zList": ",".join(f"{z:.0f}" for z in sorted(j.levels)),
            "gdOn": bool(j.guard), "brOn": bool(j.brace and any(j.brace_tubes)), "tbName": j.name,
            "tbNote": f"単管 {j.tube / 1000:.1f}M×{len(j.rows)}本" if j.tube else "単管が届かない"}


def report(joins: list[Join]) -> str:
    out = ["# 別の足場を単管でつなぐ", "",
           "出典: 日建リース工業 仮設資材カタログ Vol.10 p372（単管パイプ）・p378（兼用クランプ）、労働安全衛生規則 563条1項3号ロ・570条1項3号・4号。"
           "単管の端の突き出し（50mm 以上・支柱の間隔の 1/4 以下）は目安", "",
           "| つなぎ | 支柱の間 | 判定 | 内容 |", "|---|---|---|---|"]
    tot: dict[str, list] = {}
    for j in joins:
        for x in j.checks:
            out.append(f"| {j.name} | {j.span / 1000:.2f}m | {x.status} | {x.item}: {x.message} |")
        for a, n, u in j.quantity:
            row = tot.setdefault(a, [0.0, u])
            row[0] += n
    out += order_table(tot, ("単管", "ARC1", "ARC2")) + [""]
    return "\n".join(out)
