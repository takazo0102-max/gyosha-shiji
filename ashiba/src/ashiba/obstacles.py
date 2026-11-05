"""庇・バルコニー・セットバックをかわす（利用者の指定 2026-10-21「セットバックや庇をかわせるような仕組みを作って」）.

庇（バルコニー・屋根の軒の出も同じ）: 面から外へ張り出すスラブ。張り出しが離れより大きいと内側建地が当たる。
  → その面の離れを「張り出し＋かわし代」まで広げる（plan_solver の face_min。足場ごと外へ出す）。広がった
  隙間は内ブラケット＋踏板で詰める。ただし庇の高さに当たる層・区間はブラケットを付けない（庇が邪魔）。
セットバック: 上の階が面から奥へ下がる。奥行きが小さい（既定 900 以下）なら、足場をそのまま上の屋根まで
  上げ、下の屋根より上の層は内ブラケットで奥の壁に寄せる。大きければ従来どおり（上のスラブを選んで
  もう一度実行すると、下の屋根の上から建てる）。

入力（条件ファイル）:
  obstacles: [{"face": "南面", "start_mm": 3000, "end_mm": 6000, "height_mm": 2700, "top_mm": 2850,
               "projection_mm": 900}]   # 位置は面の躯体の始点から、高さは GL（プロジェクトの0）から
  setbacks:  [{"face": "北面", "height_mm": 6000, "depth_mm": 600}]
  avoid_obstacles: true（既定）  setback_bracket_max_mm: 900
Archicad からは、まわりのスラブ（slabs。外形・天端・厚さ）から自動で拾う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

EAVE_CLEAR_MM = 100.0        # 庇の先端から内側建地の外面までのかわし代
POST_R_MM = 25.0             # 支柱の半径（φ48.6）
PROBE_STEP_MM = 50.0         # 面から外へ張り出しを探る刻み
PROBE_MAX_MM = 3000.0        # これより大きい張り出しは探らない（ステージ・別棟）
SAMPLE_PITCH_MM = 250.0      # 面に沿って点を並べる間隔
SETBACK_MAX_MM = 900.0       # これ以下の奥行きのセットバックは内ブラケットでかわす
SETBACK_PROBE_STEP_MM = 50.0
SETBACK_MIN_RISE_MM = 1000.0  # 下の屋根から上の屋根までこれ以上あればセットバック
INSIDE_MM = 200.0            # slab_heights と同じ（面から躯体側へ入った点）
BRACKET_BELOW_MM = 450.0     # 内ブラケットの方杖が床から下へ出る深さ
BRACKET_ABOVE_MM = 100.0


@dataclass
class Obstacle:
    """面から張り出すもの（庇・バルコニー・軒の出）。位置は面の躯体の始点から、高さは GL から."""
    edge_index: int
    start_mm: float
    end_mm: float
    bottom_mm: float
    top_mm: float
    projection_mm: float
    source: str = "スラブ"

    @property
    def need_standoff_mm(self) -> float:
        """内側建地が先端に当たらない離れ."""
        return self.projection_mm + EAVE_CLEAR_MM + POST_R_MM


@dataclass
class Setback:
    """面の上の階が奥へ下がる。height_mm（下の屋根の天端、GL から）より上は壁が depth_mm 奥."""
    edge_index: int
    height_mm: float
    depth_mm: float
    upper_top_mm: float = 0.0
    source: str = "スラブ"


@dataclass
class Avoidance:
    obstacles: list[Obstacle] = field(default_factory=list)
    setbacks: list[Setback] = field(default_factory=list)
    face_min: dict[int, float] = field(default_factory=dict)   # 辺 → 必要な最小の離れ
    notes: list[str] = field(default_factory=list)


# ---- スラブから拾う ----

def _inside(pt, poly) -> bool:
    x, y = pt
    n = len(poly)
    c = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            c = not c
        j = i
    return c


def _point(edge, t_mm: float, off_mm: float):
    (sx, sy), (ex, ey) = edge.start, edge.end
    L = edge.length or 1.0
    ox, oy = edge.outward
    return (sx + (ex - sx) * t_mm / L + ox * off_mm, sy + (ey - sy) * t_mm / L + oy * off_mm)


def detect_eaves(edges, slabs: list[dict], top_limit: dict[int, float] | None = None) -> list[Obstacle]:
    """面から外へ張り出すスラブ（庇・バルコニー）。slabs は {polygon_mm, top_mm, thickness_mm}.

    面に沿って点を並べ、外へ PROBE_STEP ずつ探って、その点を含むスラブがあれば張り出し。面に接していない
    スラブ（離れて建つ別棟・地盤のスラブ）は、面のすぐ外（50mm）の点を含まないので拾わない。
    top_limit（辺 → この高さより上の張り出しは足場に関係しない）。
    """
    out: list[Obstacle] = []
    polys = [([tuple(p) for p in s["polygon_mm"]], float(s["top_mm"]),
              float(s.get("thickness_mm") or 150.0)) for s in slabs]
    for e in edges:
        L = e.length
        n = max(1, int(L // SAMPLE_PITCH_MM))
        runs: dict[int, list] = {}
        for k in range(n + 1):
            t = min(L - 1.0, max(1.0, k * L / n))
            for si, (poly, top, th) in enumerate(polys):
                if top_limit and e.index in top_limit and top - th > top_limit[e.index]:
                    continue
                if not _inside(_point(e, t, PROBE_STEP_MM), poly):
                    continue
                d = PROBE_STEP_MM
                while d + PROBE_STEP_MM <= PROBE_MAX_MM and _inside(_point(e, t, d + PROBE_STEP_MM), poly):
                    d += PROBE_STEP_MM
                runs.setdefault(si, []).append((t, d))
        for si, pts in runs.items():
            poly, top, th = polys[si]
            pts.sort()
            # 連続した点の区間ごとに1つ
            seg = [pts[0]]
            for a, b in zip(pts, pts[1:]):
                if b[0] - a[0] > 1.5 * L / n + 1.0:
                    out.append(_obstacle(e.index, seg, top, th, L / n))
                    seg = []
                seg.append(b)
            out.append(_obstacle(e.index, seg, top, th, L / n))
    return out


def _obstacle(ei, seg, top, th, pitch) -> Obstacle:
    t0 = max(0.0, seg[0][0] - pitch / 2)
    t1 = seg[-1][0] + pitch / 2
    return Obstacle(ei, round(t0), round(t1), top - th, top, max(d for _t, d in seg) + PROBE_STEP_MM / 2)


def detect_setbacks(edges, slabs: list[dict], tops: dict[int, float],
                    max_depth: float = SETBACK_MAX_MM) -> list[Setback]:
    """面の軒高（tops。面の内側200の点のスラブ）より奥（max_depth まで）に、もっと高いスラブがあればセットバック."""
    out: list[Setback] = []
    polys = [([tuple(p) for p in s["polygon_mm"]], float(s["top_mm"])) for s in slabs]
    for e in edges:
        top = tops.get(e.index)
        if top is None:
            continue
        L = e.length
        n = max(1, int(L // 1000.0))
        best: Optional[tuple[float, float]] = None      # (上の天端, 奥行き)
        for k in range(n + 1):
            t = min(L - 1.0, max(1.0, (k + 0.5) * L / (n + 1)))
            d = INSIDE_MM
            while d <= INSIDE_MM + max_depth:
                p = _point(e, t, -d)
                hi = [tp for poly, tp in polys if tp > top + SETBACK_MIN_RISE_MM and _inside(p, poly)]
                if hi:
                    cand = (max(hi), d - SETBACK_PROBE_STEP_MM / 2)   # 面から奥の壁まで
                    if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                        best = cand
                    break
                d += SETBACK_PROBE_STEP_MM
        if best is not None:
            out.append(Setback(e.index, top, round(best[1] / 10.0) * 10.0, best[0]))
    return out


# ---- 入力から ----

def _face_index(face, names_by_index: dict[int, str]) -> Optional[int]:
    if isinstance(face, int) or str(face).isdigit():
        return int(face)
    key = str(face).replace("面", "")
    for i, n in names_by_index.items():
        if n == face or n.replace("面", "") == key:
            return i
    return None


def from_spec(spec: dict, names_by_index: dict[int, str]) -> tuple[list[Obstacle], list[Setback], list[str]]:
    obs, sbs, notes = [], [], []
    for o in spec.get("obstacles") or []:
        ei = _face_index(o.get("face", o.get("edge_index")), names_by_index)
        if ei is None:
            notes.append(f"obstacles: 面「{o.get('face')}」が分かりません")
            continue
        bottom = float(o.get("height_mm", 0))
        obs.append(Obstacle(ei, float(o.get("start_mm", 0)), float(o.get("end_mm", 1e9)), bottom,
                            float(o.get("top_mm", bottom + 150)), float(o["projection_mm"]), "入力"))
    for sb in spec.get("setbacks") or []:
        ei = _face_index(sb.get("face", sb.get("edge_index")), names_by_index)
        if ei is None:
            notes.append(f"setbacks: 面「{sb.get('face')}」が分かりません")
            continue
        sbs.append(Setback(ei, float(sb["height_mm"]), float(sb["depth_mm"]), float(sb.get("top_mm", 0)), "入力"))
    return obs, sbs, notes


def plan_avoidance(edges, standoffs: list[float], obstacles: list[Obstacle], names_by_index: dict[int, str],
                   target_mm: float = 300.0) -> Avoidance:
    """内側建地が庇に当たる面の、必要な最小の離れ（plan_solver の face_min）."""
    av = Avoidance(obstacles=list(obstacles))
    for o in obstacles:
        cur = standoffs[o.edge_index] if o.edge_index < len(standoffs) else target_mm
        need = o.need_standoff_mm
        name = names_by_index.get(o.edge_index, f"辺{o.edge_index}")
        if need <= cur + 1e-6:
            av.notes.append(f"{name}: 庇（出{o.projection_mm:.0f}・GL+{o.bottom_mm:.0f}）は離れ{cur:.0f}mm の内側に"
                            "収まります（内側建地は当たりません）")
            continue
        need = float(int(-(-need // 10)) * 10)     # 10mm に切り上げ
        if need > av.face_min.get(o.edge_index, 0.0):
            av.face_min[o.edge_index] = need
    return av


# ---- 内ブラケット（広げた隙間・セットバックの奥を詰める） ----

def avoidance_brackets(model, existing, obstacles: list[Obstacle], setbacks: list[Setback],
                       fall_limit_mm: float = 300.0, limit_mm: float = 350.0):
    """庇をかわして離れを広げた面・セットバックの面に、層ごとの内ブラケットを付ける.

    層ごとの実際の離れ（セットバックより上は奥行きを足す）から踏板を選ぶ（auto_inner_brackets と同じ規則）。
    庇の高さに方杖・床が当たる層は、庇の区間（前後100）を外す。戻り値は (区間, 案内文)。
    """
    from .brackets import INNER, INNER_DECK_OFFSET_MM, MIN_GAP_AFTER_INNER_MM, BracketSection, inner_bracket_options

    if model.master.is_frame or model.config.scaffold_form == "一側足場":
        return [], []
    opts = inner_bracket_options(model)
    base = float(getattr(model, "base_height_mm", 0.0) or 0.0)
    out, notes = [], []
    faces = sorted({o.edge_index for o in obstacles} | {s.edge_index for s in setbacks}
                   | set(model.plan.face_shift))
    for ep in model.plan.edges:
        ei = ep.edge_index
        if ei not in faces or any(s.edge_index == ei and s.direction == INNER for s in existing):
            continue
        name = model.face_name(ei)
        edge = model.plan.outline.edges[ei]
        dx, dy = edge.direction
        off = (edge.start[0] - ep.start_post[0]) * dx + (edge.start[1] - ep.start_post[1]) * dy
        L = float(ep.scaffold_length)
        sb = next((s for s in setbacks if s.edge_index == ei), None)
        levels = model.elevation_of(ei).level_heights
        per_level: dict[tuple, list[int]] = {}
        missing = set()
        for k, z in enumerate(levels, start=1):
            d = float(ep.standoff)
            if sb is not None and z + base >= sb.height_mm - 1.0:
                d += sb.depth_mm
            if d <= limit_mm + 1e-6:
                continue
            pick = None
            for arm, deck, no in opts:
                gap = d - deck - INNER_DECK_OFFSET_MM
                if MIN_GAP_AFTER_INNER_MM - 1e-6 <= gap <= fall_limit_mm + 1e-6:
                    pick = (arm, deck, no, round(gap))
                    break
            if pick is None:
                missing.add(round(d))
                continue
            # 庇に当たる区間を外す
            cut = []
            for o in obstacles:
                if o.edge_index != ei:
                    continue
                zb, zt = o.bottom_mm - base, o.top_mm - base
                if zt > z - BRACKET_BELOW_MM and zb < z + BRACKET_ABOVE_MM:
                    cut.append((o.start_mm + off - 100.0, o.end_mm + off + 100.0))
            free = _free(L, cut)
            per_level.setdefault((pick, tuple(free)), []).append(k)
        for (pick, free), lvs in per_level.items():
            arm, deck, no, gap = pick
            for a, b in free:
                out.append(BracketSection(edge_index=ei, start_mm=a, end_mm=b, direction=INNER, width=arm,
                                          inner_deck_width=deck, levels=list(lvs), auto=True,
                                          reason="庇・セットバックをかわした隙間を詰める（自動）"))
            notes.append(f"{name}: 内ブラケット {no}（踏板{deck}）を {_levels_text(lvs)}層に付けました"
                         f"（躯体までの隙間 約{gap}mm" + ("。庇の当たる区間は外しています" if len(free) != 1 or free[0] != (0.0, L) else "")
                         + "）")
        if missing:
            notes.append(f"{name}: 離れ{'・'.join(str(v) for v in sorted(missing))}mm を詰める内ブラケットが系列に"
                         "ありません。落下防止材（層間ネット等）を検討してください")
    return out, notes


def _levels_text(lvs: list[int]) -> str:
    """[1, 3, 4, 5] → "1・3〜5"."""
    out, run = [], [lvs[0]]
    for v in lvs[1:]:
        if v == run[-1] + 1:
            run.append(v)
        else:
            out.append(run)
            run = [v]
    out.append(run)
    return "・".join(str(r[0]) if len(r) == 1 else f"{r[0]}〜{r[-1]}" for r in out)


def _free(length: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [(0.0, length)]
    for a, b in sorted(cuts):
        nxt = []
        for x0, x1 in out:
            if b <= x0 or a >= x1:
                nxt.append((x0, x1))
                continue
            if a > x0 + 1.0:
                nxt.append((x0, a))
            if b < x1 - 1.0:
                nxt.append((b, x1))
        out = nxt
    return [(round(a, 1), round(b, 1)) for a, b in out if b - a > 300.0]
