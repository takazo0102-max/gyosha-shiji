"""躯体外形ポリゴン処理と足場中心線ループ生成.

MVP制約: 直交ポリゴン（90度コーナーのみ）。非直交はValidationErrorで明示的に拒否する。

座標系はmm。外形は反時計回り(CCW)に正規化して扱う。
CCWのとき進行方向の右手側が外側（足場側）になる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

Point = tuple[float, float]


class ValidationError(Exception):
    pass


@dataclass
class Corner:
    index: int
    point: Point
    kind: str  # "出隅" (convex) | "入隅" (reflex)


@dataclass
class Edge:
    """躯体外形の1辺（足場の1面に対応する）."""

    index: int
    start: Point
    end: Point
    direction: Point       # 単位ベクトル（軸平行）
    outward: Point         # 外向き法線（単位ベクトル）
    start_corner: str      # 始点コーナーの種別 "出隅"/"入隅"
    end_corner: str
    # 足場中心線長 = length + start_sign*d_prev + end_sign*d_next
    # 出隅=+1（回しで延長）、入隅=-1（短縮）
    start_sign: int = 0
    end_sign: int = 0

    @property
    def length(self) -> float:
        return abs(self.end[0] - self.start[0]) + abs(self.end[1] - self.start[1])

    @property
    def axis(self) -> str:
        """辺が走る軸。'x'なら外向き法線はy方向."""
        return "x" if abs(self.direction[0]) > 0.5 else "y"


@dataclass
class Outline:
    vertices: list[Point]
    edges: list[Edge] = field(default_factory=list)
    corners: list[Corner] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # 外形の整理内容（黙って直さない）

    @property
    def perimeter(self) -> float:
        return sum(e.length for e in self.edges)


def _signed_area(vertices: list[Point]) -> float:
    s = 0.0
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _clean_vertices(verts: list[Point], tol: float = 1e-6) -> tuple[list[Point], list[str]]:
    """重複頂点と共線頂点を取り除く.

    Archicadのスラブ外形は編集の履歴で、同じ点が2度入っていたり、
    直線の途中に頂点が残っていたりする。そのまま扱うと:
    - 重複頂点は長さ0の辺になり、方向ベクトルが作れない
    - 共線頂点は cross=0 なので入隅と判定され、そこに存在しないコーナーが
      でき、両側の面が離れの分だけ短くなる（足場ループが閉じない）
    30m壁の中央に頂点が1つ余分にあるだけで、足場長が600mm不足した。
    """
    notes: list[str] = []
    out = list(verts)

    # 連続する同一点
    deduped = [out[0]]
    for v in out[1:]:
        if abs(v[0] - deduped[-1][0]) > tol or abs(v[1] - deduped[-1][1]) > tol:
            deduped.append(v)
    if len(deduped) > 1 and (
        abs(deduped[0][0] - deduped[-1][0]) <= tol
        and abs(deduped[0][1] - deduped[-1][1]) <= tol
    ):
        deduped.pop()
    if len(deduped) != len(out):
        notes.append(f"外形の重複頂点を{len(out) - len(deduped)}点除去しました")
    out = deduped

    # 共線頂点（直線の途中に残った頂点）
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cross) <= tol:
                out.pop(i)
                notes.append(
                    f"外形の共線頂点({b[0]:.0f}, {b[1]:.0f})を除去しました"
                    "（直線の途中に頂点があると、そこに無いコーナーができます）"
                )
                changed = True
                break
    return out, notes


def build_outline(vertices: list[Point]) -> Outline:
    """外形ポリゴンを検証しCCW正規化、辺・コーナー情報を構築する."""
    if len(vertices) < 4:
        raise ValidationError("外形ポリゴンには4点以上が必要です")
    verts = [tuple(map(float, v)) for v in vertices]
    verts, notes = _clean_vertices(verts)
    if len(verts) < 4:
        raise ValidationError(
            f"重複・共線の頂点を除くと{len(verts)}点しか残りません"
            "（外形ポリゴンには4点以上が必要です）"
        )
    if _signed_area(verts) < 0:
        verts = list(reversed(verts))

    n = len(verts)
    # 直交チェック
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        if (abs(dx) > 1e-6) == (abs(dy) > 1e-6):
            raise ValidationError(
                f"非直交の辺があります（頂点{i}→{(i + 1) % n}）。"
                "MVPは90度コーナーのみ対応です"
            )

    outline = Outline(vertices=verts, notes=notes)
    corner_kinds: list[str] = []
    for i in range(n):
        p_prev = verts[(i - 1) % n]
        p = verts[i]
        p_next = verts[(i + 1) % n]
        d1 = (p[0] - p_prev[0], p[1] - p_prev[1])
        d2 = (p_next[0] - p[0], p_next[1] - p[1])
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        kind = "出隅" if cross > 0 else "入隅"
        corner_kinds.append(kind)
        outline.corners.append(Corner(index=i, point=p, kind=kind))

    for i in range(n):
        p1, p2 = verts[i], verts[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = abs(dx) + abs(dy)
        direction = (dx / length, dy / length)
        # CCWで外側は進行方向の右手側
        outward = (direction[1], -direction[0])
        sk = corner_kinds[i]
        ek = corner_kinds[(i + 1) % n]
        outline.edges.append(
            Edge(
                index=i,
                start=p1,
                end=p2,
                direction=direction,
                outward=outward,
                start_corner=sk,
                end_corner=ek,
                start_sign=+1 if sk == "出隅" else -1,
                end_sign=+1 if ek == "出隅" else -1,
            )
        )
    return outline


def scaffold_loop_vertices(outline: Outline, standoffs: list[float]) -> list[Point]:
    """各辺を外向きに standoff[i] だけオフセットし、隣接オフセット線の交点で
    足場中心線ループの頂点列を返す（頂点i = 辺i-1と辺iの交点 = コーナー支柱位置）."""
    n = len(outline.edges)
    lines = []  # (point_on_line, direction)
    for e, d in zip(outline.edges, standoffs):
        px = e.start[0] + e.outward[0] * d
        py = e.start[1] + e.outward[1] * d
        lines.append(((px, py), e.direction))
    verts: list[Point] = []
    for i in range(n):
        (p1, d1) = lines[(i - 1) % n]
        (p2, d2) = lines[i]
        # 軸平行前提の交点
        if abs(d1[0]) > 0.5:  # 前辺がx方向 → y固定、後辺がy方向 → x固定
            verts.append((p2[0], p1[1]))
        else:
            verts.append((p1[0], p2[1]))
    return verts


def edge_scaffold_length(edge: Edge, d_prev: float, d_self_unused: float, d_next: float) -> float:
    """辺の足場中心線長（コーナー支柱間距離）."""
    return edge.length + edge.start_sign * d_prev + edge.end_sign * d_next
