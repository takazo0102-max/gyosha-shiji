"""支保工足場: 内部足場（内部ステージ足場）をスラブの型枠支保工として置く（利用者の指定 2026-10-31: しほこう足場を内部足場から
作成して 図面化までしてちょ）.

「型枠」で置いたスラブの型枠（せき板・根太）の下に、パイプサポートの代わりにくさび緊結式などの系列の支柱を格子に立てる。
- 範囲: スラブの外形の外接長方形（大引の向き u・それに直角 v）を、端から端まで横切る梁・壁（の型枠の外 BEAM_CLEAR_MM）で
  区切った長方形ごとに1つの内部足場（ashiba_stage・用途 支保工）。端から端まで横切らない柱・壁は支柱をよけられないので知らせる
- 向き: 内部足場の長手（u）をスラブの大引の向きにそろえる（大引は支柱の u の列ごと、根太はその上に直角 @300。型枠の根太と同じ向き）
- 高さ: 床（下のスラブの天端）からスラブの下端−（せき板 12＋根太 50＋大引 90）まで。支柱の積み方・ジャッキ・大引受けジャッキの
  繰出しは内部足場が決める（interior_stage.solve_stage の use＝支保工）。作業床は大引の下 1.8m 前後の段
- 検定: 内部足場の支保工の検定（承認値・つなぎ方別の軸力、水平荷重 5%、水平つなぎ、Uジャッキの繰出し、設置届）
- 図面: スラブの計画の posts・obiki などを内部足場の格子に置き換え、"system" に系列・段・ジャッキ・検定を持たせる
  （form_drawings が支保工足場として描く）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

BEAM_CLEAR_MM = 250.0        # 梁・壁・柱の面から支保工の範囲まで（側板 12・桟木 60・外端太 2本と手間）
MIN_CELL_MM = 1200.0         # これより狭い範囲には組まない
FORM_NEDA = "角パイプ50"     # スラブ・梁下の詳細図（利用者の指定 2026-10-31）の根太・大引
FORM_OBIKI = "杉90"
FORM_DEPTH_MM = 12.0 + 50.0 + 90.0   # スラブの下端から大引の下端まで（せき板・根太・大引）
DECK_BELOW_MM = 1000.0       # 作業床は大引の下からこれくらい下の段（手すり 900 が大引の下に収まる。階段枠 1800 に合わせやすい）
RECORD = "支保工足場.json"


@dataclass
class Cell:
    u0: float
    u1: float
    v0: float
    v1: float

    @property
    def size(self) -> tuple[float, float]:
        return self.u1 - self.u0, self.v1 - self.v0


def _bbox(poly) -> tuple[float, float, float, float]:
    us, vs = [p[0] for p in poly], [p[1] for p in poly]
    return min(us), max(us), min(vs), max(vs)


def _merge(iv: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _between(lo: float, hi: float, bands: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out, cur = [], lo
    for a, b in _merge(bands):
        if b <= lo or a >= hi:
            continue
        if a > cur:
            out.append((cur, a))
        cur = max(cur, b)
    if hi > cur:
        out.append((cur, hi))
    return out


def shoring_cells(outer, holes, clear: float = BEAM_CLEAR_MM) -> tuple[list[Cell], list[str]]:
    """スラブの局所座標の外形・穴（梁・壁・柱）→ 支保工を組む長方形と注意.

    穴の外接長方形が v の端から端まで（両端 300 以内）にかかれば u を区切る帯、u の端から端までなら v を区切る帯。どちらでも
    ない穴（柱・短い壁）は区切らず、支柱がかかるかもしれないので知らせる."""
    u0, u1, v0, v1 = _bbox(outer)
    bu, bv, notes = [], [], []
    for h in holes:
        a, b, c, d = _bbox(h)
        if c <= v0 + 300.0 and d >= v1 - 300.0:
            bu.append((a - clear, b + clear))
        elif a <= u0 + 300.0 and b >= u1 - 300.0:
            bv.append((c - clear, d + clear))
        elif a > u0 + 1.0 and b < u1 - 1.0 and c > v0 + 1.0 and d < v1 - 1.0:
            notes.append(f"スラブの中の柱・壁（{b - a:.0f}×{d - c:.0f}）は支保工の範囲を区切らない。かかる支柱は抜くかずらす")
    cells = []
    for a, b in _between(u0, u1, bu):
        for c, d in _between(v0, v1, bv):
            if b - a >= MIN_CELL_MM and d - c >= MIN_CELL_MM:
                cells.append(Cell(a, b, c, d))
            else:
                notes.append(f"梁・壁の間の狭い所（{b - a:.0f}×{d - c:.0f}）には組まない（パイプサポートか梁の型枠で受ける）")
    return cells, notes


def stage_item(name: str, cell: Cell, W, u_dir, floor: float, story: float, bottom: float, thick: float, tie: str) -> dict:
    """1つの長方形の内部足場（用途 支保工）の入力. W はスラブの局所座標 → 世界座標、u_dir は大引の向き（世界）."""
    ceil = bottom - floor
    corners = [list(W((cell.u0, cell.v0))), list(W((cell.u1, cell.v0))), list(W((cell.u1, cell.v1))), list(W((cell.u0, cell.v1)))]
    deck = max(1000.0, ceil - FORM_DEPTH_MM - DECK_BELOW_MM)
    return {"name": name, "corners_mm": corners, "u_dir": list(u_dir), "deck_mm": deck, "base_mm": floor - story,
            "ceiling_mm": ceil, "use": "支保工", "slab_mm": thick, "tie": tie, "live_kn_m2": 1.47,
            "form": {"neda": FORM_NEDA, "obiki": FORM_OBIKI}, "form_depth_mm": FORM_DEPTH_MM}


def post_force(st, caps) -> tuple[float, Optional[float]]:
    """支柱1本の軸力（kN）と支保工の許容支持力（承認値・つなぎ方別。無ければ None）."""
    from .interior_stage import POST_SELF_KN_PER_M, _cap, _trib_m2

    n_kn = _trib_m2(st) * st.design_kn_m2 + POST_SELF_KN_PER_M * st.top_mm / 1000.0
    return n_kn, _cap(caps, "支保工許容支持力", st.tie)


def system_summary(st, master, caps, L) -> dict:
    """内部足場（支保工）の結果 → 図面・計算書に使う控え（スラブの局所座標。高さは床から mm）."""
    from .interior_stage import SHORING_APPROVAL
    from .master import SERIES_LABELS

    cu, cv = [0.0], [0.0]
    for s in st.spans_u:
        cu.append(cu[-1] + s)
    for s in st.spans_v:
        cv.append(cv[-1] + s)
    W = lambda a, b: (st.origin[0] + st.u[0] * a + st.v[0] * b, st.origin[1] + st.u[1] * a + st.v[1] * b)
    posts = [list(L(W(a, b))) for b in cv for a in cu]
    obiki = []
    for b in cv:
        p0, p1 = L(W(-150.0, b)), L(W(cu[-1] + 150.0, b))
        obiki.append([min(p0[0], p1[0]), max(p0[0], p1[0]), p0[1]])
    n_kn, allow = post_force(st, caps)
    o = L(W(0.0, 0.0))
    return {"name": st.name, "series": master.series_id, "series_name": SERIES_LABELS.get(master.series_id, master.series_id),
            "approval": SHORING_APPROVAL.get(master.series_id, ""), "tie": st.tie,
            "origin": list(o), "spans_u": list(st.spans_u), "spans_v": list(st.spans_v),
            "posts": posts, "obiki": obiki, "levels": sorted(set(st.levels + st.upper_levels)), "deck": st.deck_mm,
            "top": st.top_mm, "jack": st.jack_mm, "uhead": st.uhead_ext_mm or 0, "post_stack": list(st.posts),
            "koma": int(getattr(master, "koma_pitch", 0) or 0), "design_kn_m2": st.design_kn_m2, "post_kn": n_kn,
            "allow_kn": allow, "h_ratio": st.h_ratio, "inner_braces": st.inner_braces,
            "checks": [[c.item, c.status, c.message] for c in st.checks],
            "quantity": [list(q) for q in st.quantity], "notes": list(st.notes), "ok": st.ok}


def merge_system(slab: dict, systems: list[dict]) -> dict:
    """型枠_計画.json のスラブを支保工足場に置き換える: 支柱・大引は内部足場の格子、敷き桟木・筋かい・水平つなぎは内部足場が持つ."""
    out = dict(slab)
    out["system"] = systems
    out["posts"] = [p for s in systems for p in s["posts"]]
    out["obiki"] = [o for s in systems for o in s["obiki"]]
    out["sills"], out["braces"], out["ties"], out["brace_info"] = [], [], [], {}
    if systems:
        out["post_h"] = max(s["top"] for s in systems)
        out["post_kn"] = max(s["post_kn"] for s in systems)
        out["sv"] = max(max(s["spans_v"]) for s in systems)
        out["su"] = max(max(s["spans_u"]) for s in systems)
        out["lines"] = [f"支保工足場 {s['name']}（{s['series_name']}・{s['tie']}）: " + c[0] + " " + c[1] + " — " + c[2]
                        for s in systems for c in s["checks"]]
    return out
