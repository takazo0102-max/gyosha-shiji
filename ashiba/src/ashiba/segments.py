"""足場ラインを垂直・水平に区切る（利用者の指定 2026-10-21「垂直と水平で区切れるように」「クリックした次のところから区切る、3Dで」）.

足場ライン（面ごとに1部品）を、スパン segSpanA〜segSpanB・作業層 segLevA〜segLevB の部品に分ける（0＝端まで）。
3D は部品の範囲の箱の外を切り取り（縦は支柱の芯、横は作業床の 100 下）、平面・数量は範囲の中だけを数える。
区切る位置は 3D のつまみ（cutAtX・cutAtZ）で引き、次の支柱の芯・次の作業床に吸着する（足場ライン vl.gdl）。

範囲の持ち主（3d.gdl・1d.gdl と同じ規則）: 位置 x は [gxA, gxB)（始点側の支柱は自分、終点側は隣の部品）、
高さ z は [gzA, gzB)。面の端の部品は端の外まで（出隅・開放端・面の終点の支柱も持つ）。
"""

from __future__ import annotations

from dataclasses import dataclass

CUT_BELOW_FLOOR = 0.1     # 横の区切りは作業床の 100 下（床・腕木・布材は上の部品、手すりは下の部品）
FAR = 1000.0


def _nums(v) -> list[float]:
    out = []
    for t in str(v or "").replace(" ", "").split(","):
        if t:
            try:
                out.append(float(t))
            except ValueError:
                pass
    return out


def _f(p: dict, k: str, d: float = 0.0) -> float:
    try:
        return float(p.get(k, d))
    except (TypeError, ValueError):
        return d


def _i(p: dict, k: str, d: int = 0) -> int:
    try:
        return int(round(float(p.get(k, d))))
    except (TypeError, ValueError):
        return d


def spans_m(p: dict) -> list[float]:
    return [v / 1000 for v in _nums(p.get("spanList")) + _nums(p.get("spanList2"))]


def levels_m(p: dict) -> list[float]:
    """lv（足場ライン 1d.gdl と同じ）: [根がらみ, 1層の床, 2層の床, ...]（m）."""
    pitch = _f(p, "komaPitch", 0.45)
    return [_f(p, "negaH") or (_f(p, "jackOut", 0.2) + pitch)] + [v / 1000 for v in _nums(p.get("levelList"))]


@dataclass(frozen=True)
class Piece:
    """区切った部品の範囲（スパン・作業層は1始まり、両端を含む）と、その座標の範囲."""
    sA: int
    sB: int
    lA: int
    lB: int
    n_span: int
    n_levels: int
    pxA: float      # 部品の始点・終点の支柱の位置（面の始点から m）
    pxB: float
    gxA: float      # 持ち主の範囲 [gxA, gxB)・[gzA, gzB)。面の端は ±FAR
    gxB: float
    gzA: float
    gzB: float

    @property
    def split(self) -> bool:
        return self.sA > 1 or self.sB < self.n_span or self.lA > 1 or self.lB < self.n_levels

    @property
    def base(self) -> bool:
        """下の端の部品（根がらみ・ジャッキ・平面の本体を持つ）."""
        return self.lA == 1

    def own_x(self, x: float) -> bool:
        return self.gxA - 0.001 <= x < self.gxB - 0.001

    def own_z(self, z: float) -> bool:
        return self.gzA - 0.001 <= z < self.gzB - 0.001

    @property
    def z_base(self) -> float:
        """横の区切りのつまみの基点（部品の下端。下の端の部品は 0）."""
        return self.gzA if self.lA > 1 else 0.0


def piece_of(p: dict) -> Piece:
    """足場ラインのパラメータ → 部品の範囲（1d.gdl の sA・sB・lA・lB・gxA… と同じ）."""
    spans = spans_m(p)
    lv = levels_m(p)
    n_span, n_lev = len(spans), len(lv) - 1
    if not spans or n_lev < 1:
        raise ValueError("足場ラインのスパン・作業層が読めません")
    sA = _i(p, "segSpanA")
    sA = sA if 1 <= sA <= n_span else 1
    sB = _i(p, "segSpanB")
    sB = sB if sA <= sB <= n_span else n_span
    lA = _i(p, "segLevA")
    lA = lA if 1 <= lA <= n_lev else 1
    lB = _i(p, "segLevB")
    lB = lB if lA <= lB <= n_lev else n_lev
    pxA, pxB = sum(spans[:sA - 1]), sum(spans[:sB])
    return Piece(sA, sB, lA, lB, n_span, n_lev, pxA, pxB,
                 pxA if sA > 1 else -FAR, pxB if sB < n_span else FAR,
                 lv[lA] - CUT_BELOW_FLOOR if lA > 1 else -FAR,
                 lv[lB + 1] - CUT_BELOW_FLOOR if lB < n_lev else FAR)


def vertical_cut(p: dict, piece: Piece | None = None) -> int | None:
    """縦に区切るスパン k（スパン k と k+1 の間の支柱で切る）。cutAtX（部品の始点から）の次の支柱. 無ければ None."""
    at = _f(p, "cutAtX")
    if at <= 0.0005:
        return None
    pc = piece or piece_of(p)
    spans = spans_m(p)
    x = 0.0
    for k in range(1, pc.sB):
        x += spans[k - 1]
        if k >= pc.sA and x >= pc.pxA + at - 0.001:
            return k
    return None


def horizontal_cut(p: dict, piece: Piece | None = None) -> int | None:
    """横に区切る作業層 m（m 層から上を上の部品に）。cutAtZ（部品の下端から）の次の作業床. 無ければ None."""
    at = _f(p, "cutAtZ")
    if at <= 0.0005:
        return None
    pc = piece or piece_of(p)
    lv = levels_m(p)
    for m in range(pc.lA + 1, pc.lB + 1):
        if lv[m] - CUT_BELOW_FLOOR >= pc.z_base + at - 0.001:
            return m
    return None


def split_ranges(p: dict) -> list[dict]:
    """区切ったあとの部品のパラメータ（範囲）。先頭は元の部品が引き継ぐ（始点側・下側）。区切らなければ空."""
    pc = piece_of(p)
    k, m = vertical_cut(p, pc), horizontal_cut(p, pc)
    if k is None and m is None:
        return []
    xs = [(pc.sA, k), (k + 1, pc.sB)] if k is not None else [(pc.sA, pc.sB)]
    zs = [(pc.lA, m - 1), (m, pc.lB)] if m is not None else [(pc.lA, pc.lB)]
    out = []
    for la, lb in zs:
        for sa, sb in xs:
            out.append({"segSpanA": sa, "segSpanB": sb, "segLevA": la, "segLevB": lb, "cutAtX": 0.0, "cutAtZ": 0.0})
    return out


WHOLE = {"segSpanA": 0, "segSpanB": 0, "segLevA": 0, "segLevB": 0, "cutAtX": 0.0, "cutAtZ": 0.0, "segGroup": ""}
