"""足場ラインの支柱だけを部材（1本＝1部品 ashiba_member）に分解する.

利用者の指定（2026-10-21）: 最初は支柱・布材・踏板・手すりなど全部を1本ずつの部品にしたが、1面で250〜500本、
建物1棟で約1400本になり重い。「分解はやめて、支柱だけ分解できるように」。面は垂直・水平に区切れる（segments）。

足場ラインの GDL パラメータから同じ規則で支柱を並べ直す。くさび式は支柱を1本ずつ（コマ・継手付き。梁枠の上の
支柱と出隅の外側コーナー支柱も）、枠組（serType W）は建枠を1枚ずつ（脚2本・横架材・鳥居の縦材）。ジャッキ・
布材・踏板・手すり・ブレースなどは足場ラインのまま。区切った部品は、自分の持つ支柱（位置 x が [gxA, gxB)、
下端が [gzA, gzB)。segments.Piece）だけを分解する。分解した足場ラインは explodeMask=1 で、それらの支柱を描かない。

座標: 足場ラインの局所座標（x＝面に沿う向き、y＝躯体側が＋、外側建地列は y=-rowW、z＝足場の立つ面から）を、
足場ラインの原点・回転で平面の座標に直す。敷地の高低差（脚ごとの地盤高）は考えない。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .segments import piece_of

MEMBER_OBJECT = "ashiba_member"
KIND = {"支柱": 1, "建枠": 8}


@dataclass
class Member:
    kind: int
    x: float              # 局所 m
    y: float
    z: float
    ang: float = 0.0      # 局所の向き（度。0＝+x）
    L: float = 0.0
    W: float = 0.0
    H: float = 0.0
    koma: list = field(default_factory=list)   # 支柱のコマ（下端から mm）
    name: str = ""
    flags: int = 0        # 建枠: 1＝下の建枠との継ぎ目、2＝躯体側の脚を描かない


def _nums(v) -> list[float]:
    out = []
    for t in str(v or "").replace(" ", "").split(","):
        if t == "":
            continue
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


def koma_offsets(length_m: float, pitch: float, gap: float, nega: float, nega_lens_mm: list) -> list[int]:
    """支柱1本のコマの高さ（下端から mm）。足場ライン 3d.gdl の kzAll と同じ規則（master.post_koma_offsets）."""
    if pitch <= 0:
        return []
    out = set()
    z = length_m - gap
    while z >= 0.1 - 0.0001:
        out.add(round(z * 1000))
        z -= pitch
    if nega > 0.001 and any(abs(v / 1000 - length_m) < 0.0005 for v in nega_lens_mm):
        out.add(round(nega * 1000))
        zm = length_m - gap
        while zm - pitch > nega + 0.001:
            zm -= pitch
        if zm > nega + 0.75 * pitch + 0.001 and pitch - gap < length_m:
            out.add(round((pitch - gap) * 1000))
    return sorted(out)


def line_members(p: dict) -> list[Member]:
    """足場ラインの GDL パラメータ → この部品が持つ支柱（枠組は建枠）の並び（局所座標. 3d.gdl の支柱と同じ規則）."""
    frame = str(p.get("serType", "A")).strip() == "W"
    spans = [v / 1000 for v in _nums(p.get("spanList")) + _nums(p.get("spanList2"))]
    posts = [v / 1000 for v in _nums(p.get("postList"))]
    # 単管の千鳥（偶数番目の建地は postListAlt。3d.gdl と同じ）
    posts_alt = [v / 1000 for v in _nums(p.get("postListAlt"))] or posts
    if not spans or not posts:
        raise ValueError("足場ラインのスパン・支柱構成が読めません")
    pc = piece_of(p)
    row_w = _f(p, "rowW", 0.61)
    jack = _f(p, "jackOut", 0.2)
    n_rows = _i(p, "nRows", 2)
    row_start = 1 if n_rows < 2 else 0
    pitch, gap = _f(p, "komaPitch", 0.45), _f(p, "komaGap")
    nega, nega_lens = _f(p, "komaNega"), _nums(p.get("negaLens"))
    post_top = jack + sum(posts)
    skip_s, skip_e = _i(p, "skipInS"), _i(p, "skipInE")
    hug = _i(p, "hugMode") == 1     # 抱き足場は建地列が線の上で、隅の建地は隣の面と同じ1本
    bm = _nums(p.get("beamList"))
    beams = [(bm[i] / 1000, bm[i + 1] / 1000, bm[i + 2] / 1000) for i in range(0, len(bm) - 2, 3)]
    xs = [0.0]
    for sp in spans:
        xs.append(xs[-1] + sp)
    n_span = len(spans)
    out: list[Member] = []

    def stack(x, y, tag="", alt=False):
        z = jack
        for j, pl in enumerate(posts_alt if alt else posts):
            if pc.own_z(z):
                if frame:
                    shared = (abs(x) < 0.001 and skip_s) or (abs(x - xs[-1]) < 0.001 and skip_e)
                    out.append(Member(8, x, 0.0, z, L=pl, W=row_w, flags=(1 if j else 0) | (2 if shared else 0),
                                      name=f"建枠 {row_w * 1000:.0f}×{pl * 1000:.0f}"))
                else:
                    out.append(Member(1, x, y, z, L=pl, koma=koma_offsets(pl, pitch, gap, nega, nega_lens),
                                      name=f"支柱{tag} {pl * 1000:.0f}"))
            z += pl

    # ---- 支柱（各スパン境界に内外1対。隅の内側建地は隣の面が持つ。梁枠の内側は梁枠の上から1本） ----
    for ip, x in enumerate(xs):
        if not pc.own_x(x):
            continue
        b_base = next((h for s, ln, h in beams if s + 0.001 < x < s + ln - 0.001), 0.0)
        if frame and not b_base:
            stack(x, 0.0)                  # 建枠は内外の脚を1枚で
            continue
        for row in range(row_start, 2):
            if (row == 0 or hug) and ((ip == 0 and skip_s) or (ip == n_span and skip_e)):
                continue
            if b_base:
                if pc.own_z(b_base):
                    out.append(Member(1, x, -row * row_w, b_base, L=post_top - b_base,
                                      name=f"支柱（梁枠上）{(post_top - b_base) * 1000:.0f}"))
            else:
                stack(x, -row * row_w, alt=(ip + 1) % 2 == 0)

    # ---- 出隅の外側コーナー支柱（くさび式。始点側の部品が持つ） ----
    if not frame and _i(p, "cornerS") == 1 and pc.sA == 1:
        # 幅の違う本足場の組と出会う隅は、前の面の幅の位置（cornerSW）
        stack(-(_f(p, "cornerSW") or row_w), -row_w, "（出隅）")
    return out


def to_world(members: list[Member], origin_m: tuple, angle_rad: float, base_z_m: float = 0.0) -> list[dict]:
    """局所の部材 → 部品を置く位置（平面 m）と GDL パラメータ."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    deg = math.degrees(angle_rad)
    out = []
    for m in members:
        wx = origin_m[0] + m.x * c - m.y * s
        wy = origin_m[1] + m.x * s + m.y * c
        out.append({
            "x": wx, "y": wy,
            "params": {
                "kind": int(m.kind), "faceAng": (deg + m.ang) % 360.0, "zH": base_z_m + m.z,
                "memL": float(m.L), "memW": float(m.W), "memH": float(m.H),
                "komaList": ",".join(str(v) for v in m.koma), "partName": m.name, "frFlags": int(m.flags),
            },
        })
    return out


def member_counts(members: list[Member]) -> dict[str, int]:
    """部材名ごとの本数（分解の結果の確認用）."""
    out: dict[str, int] = {}
    for m in members:
        out[m.name] = out.get(m.name, 0) + 1
    return out
