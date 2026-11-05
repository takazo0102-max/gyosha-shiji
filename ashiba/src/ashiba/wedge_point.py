"""くさび1点で部材を足す（GLOOBE 2026 の「くさび受け参照入力」に当たる。利用者の指定 2026-11-03「進めて」）.

平面に、足したい部材の始めのくさび受け（支柱の芯）から足す向きへ線を引いて選ぶ。線の向き＝部材の向き（4方向のどれでも。
梁間方向の腕木・桁方向の布材・先行手すり・踏板・幅木）、線の長さ＝部材の長さ（系列の部材マスタの規格の長さのうち、いちばん近い
もの）。高さは足場の立つ面からのくさび受けの高さで、コマのピッチ（系列の koma_pitch）にそろえる。部材は部品 ashiba_member
（足場ラインを分解したときと同じ形）で1本ずつ置き、品番・本数・重さを発注表に。

GLOOBE の梁枠・シートの4方向入力は、梁枠は「開口」（梁枠の開口）、シートは「足場の箱」・面の養生で置く（この入力では扱わない）.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 種類 → (ashiba_member の kind, 部材マスタの区分, 既定の高さの足し mm, 説明)
KINDS = {
    "布材・腕木": (2, "布材", 0.0, "くさび受けの高さに水平に（梁間方向なら腕木）"),
    "先行手すり": (5, "先行手摺", 0.0, "床の高さのくさび受けから H900 の先行手すり"),
    "踏板": (3, "踏板", 0.0, "布材の上に掛ける床（幅 500 の品を既定に）"),
    "幅木": (4, "幅木", 0.0, "床の縁に立てる幅木"),
}


@dataclass
class Piece:
    name: str
    kind: str
    at: tuple                  # くさび受け（支柱の芯）mm
    ang: float                 # 向き（度）
    length_mm: float           # 線の長さ
    z_mm: float                # くさび受けの高さ（足場の立つ面から）
    part: object = None        # 部材マスタの品（選んでから）
    notes: list = field(default_factory=list)


def snap_z(z_mm: float, pitch: float) -> float:
    """高さをコマのピッチにそろえる（pitch 0 はそのまま）."""
    return round(z_mm / pitch) * pitch if pitch > 0 else z_mm


def pick_part(master, kind: str, length_mm: float, deck_w: int = 500):
    """線の長さにいちばん近い規格の品（踏板は幅 deck_w の品。強力つなぎ材 S は腕木の方杖付きなので外す）."""
    cat = KINDS[kind][1]
    parts = [p for p in master.by_category(cat)]
    if kind == "布材・腕木":
        parts = [p for p in parts if not p.model_no.endswith("S")]
    if kind == "踏板":
        wide = [p for p in parts if f"幅{deck_w}" in (p.note or "")]
        parts = wide or parts
    if not parts:
        return None
    return min(parts, key=lambda p: (abs(p.nominal_dim - length_mm), -p.nominal_dim))


def plan(pieces: list[Piece], master, pitch: float) -> list[Piece]:
    for pc in pieces:
        pc.z_mm = snap_z(pc.z_mm, pitch)
        pc.part = pick_part(master, pc.kind, pc.length_mm)
        if pc.part is None:
            pc.notes.append(f"{KINDS[pc.kind][1]} が部材マスタの系列に無い")
            continue
        d = pc.length_mm - pc.part.nominal_dim
        if abs(d) > 150.0:
            pc.notes.append(f"線の長さ {pc.length_mm:,.0f} と規格 {pc.part.nominal_dim:,.0f} が {abs(d):,.0f} 違う（相手の支柱の芯まで引き直す）")
    return pieces


def member_params(pc: Piece) -> dict:
    """ashiba_member のパラメータ（m・度）."""
    kind = KINDS[pc.kind][0]
    L = (pc.part.nominal_dim if pc.part else pc.length_mm) / 1000.0
    out = {"kind": kind, "faceAng": pc.ang, "zH": pc.z_mm / 1000.0, "memL": L,
           "partName": pc.kind, "partNo": pc.part.model_no if pc.part else ""}
    if kind == 3:
        out["memW"] = 0.49 if pc.part is None or "幅500" in (pc.part.note or "") else 0.24
    if kind == 5:
        out["memH"] = 0.9
    return out


def order_rows(pieces: list[Piece]) -> list[tuple[str, int, float]]:
    """[(品名, 本数, 1本の重さ kg)]."""
    tot: dict[str, list] = {}
    for pc in pieces:
        if pc.part is None:
            continue
        key = f"{KINDS[pc.kind][1]} {pc.part.model_no}（{pc.part.nominal_dim}）"
        tot.setdefault(key, [0, float(pc.part.weight_kg)])[0] += 1
    return [(k, n, kg) for k, (n, kg) in tot.items()]


def report(pieces: list[Piece], series: str) -> str:
    out = ["# くさび1点で足した部材", "", f"系列 {series} の部材マスタの規格の長さ。高さはコマのピッチにそろえた", "",
           "| 部材 | 種類 | 品番 | 長さ | 高さ | 向き | 注意 |", "|---|---|---|---|---|---|---|"]
    for pc in pieces:
        out.append(f"| {pc.name} | {pc.kind} | {pc.part.model_no if pc.part else '-'} | {pc.part.nominal_dim if pc.part else 0} | "
                   f"{pc.z_mm:,.0f} | {pc.ang:.0f}° | {'。'.join(pc.notes)} |")
    out += ["", "## 発注表", "", "| 品名・品番・規格 | 本数 | 重さ計 |", "|---|---|---|"]
    total = 0.0
    for k, n, kg in order_rows(pieces):
        out.append(f"| {k} | {n} | {n * kg:.1f}kg |")
        total += n * kg
    out.append(f"| 計 | | {total:.1f}kg |")
    return "\n".join(out) + "\n"


def from_line(name: str, kind: str, a, b, z_mm: float) -> Piece:
    return Piece(name, kind, tuple(a), math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), math.dist(a, b), z_mm)
