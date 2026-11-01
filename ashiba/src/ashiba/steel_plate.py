"""敷鉄板（利用者の指定 2026-11-01: 敷鉄板はホットスポットで広げれるようにして 別オブジェクトにして）.
部品 ashiba_plate（広げる範囲に1つ。平面のホットスポットで lenX・lenY を引き、1枚の倍数に切り上げる）。

日建リース工業 仮設資材カタログ Vol.10 p394 の厚板鋼板（厚さ 22）: NT22×5×20＝1,524×6,096・1,604kg、NT22×5×10＝1,524×3,048・
802kg、NT22×4×8＝1,219×2,438・513kg、NT22×3×6＝914×1,829・289kg。継ぎ目は敷鉄板固定金具 小判君 NTK（2.80kg）で留める。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 品番 → (部品の plType, 短い辺 mm, 長い辺 mm, kg)
PLATES = {"NT22×5×20": (1, 1524.0, 6096.0, 1604.0), "NT22×5×10": (2, 1524.0, 3048.0, 802.0),
          "NT22×4×8": (3, 1219.0, 2438.0, 513.0), "NT22×3×6": (4, 914.0, 1829.0, 289.0)}
THICK_MM = 22.0
NTK_KG = 2.8


@dataclass
class PlateLayout:
    code: str
    nx: int
    ny: int
    px: float                      # 1枚の X（下の段）mm
    py: float
    layers: int = 1

    @property
    def count(self) -> int:
        n = self.nx * self.ny
        if self.layers >= 2:                             # 上の段は向きを変えた板で同じ範囲を
            n += math.ceil(self.lx / self.py - 0.02) * math.ceil(self.ly / self.px - 0.02)
        return n

    @property
    def lx(self) -> float:
        return self.nx * self.px

    @property
    def ly(self) -> float:
        return self.ny * self.py

    @property
    def kg(self) -> float:
        return self.count * PLATES[self.code][3]

    @property
    def joints(self) -> int:
        """継ぎ目の固定金具（小判君 NTK）の目安: 隣り合う板の継ぎ目ごとに1つ（下の段）."""
        return (self.nx - 1) * self.ny + self.nx * (self.ny - 1)


def layout(len_x: float, len_y: float, code: str = "NT22×5×10", along_y: bool = False, layers: int = 1) -> PlateLayout:
    """広さ len_x × len_y（mm）を覆う枚数（1枚の倍数に切り上げ。部品の 1d.gdl と同じ）."""
    _k, s, lg, _kg = PLATES[code]
    px, py = (s, lg) if along_y else (lg, s)
    return PlateLayout(code, max(1, math.ceil(len_x / px - 0.02)), max(1, math.ceil(len_y / py - 0.02)), px, py, layers)


def part_params(lay: PlateLayout, name: str = "敷鉄板", text: bool = True) -> dict:
    """部品 ashiba_plate のパラメータ（m）。種類・向き・段数を広さより先に（パラメータスクリプトが広さを1枚の倍数に切り上げる
    ので、向きを後から変えると前の向きの板で切り上がった。2026-11-01 クレーンの十字の板が 3,048 角になった）."""
    k = PLATES[lay.code][0]
    along_y = lay.px < lay.py
    return {"plType": k, "plDir": 1 if along_y else 0, "plLay": lay.layers, "lenX": lay.lx / 1000.0,
            "lenY": lay.ly / 1000.0, "plText": bool(text), "plName": name}


def quantity(lays: list[PlateLayout]) -> list[tuple[str, float, str]]:
    out: dict[str, list] = {}
    joints = 0
    for lay in lays:
        _k, s, lg, kg = PLATES[lay.code]
        row = out.setdefault(lay.code, [0, s, lg, kg])
        row[0] += lay.count
        joints += lay.joints
    q = [(f"厚板鋼板 {c}（{s:.0f}×{lg:.0f}×{THICK_MM:.0f}）", n, f"1枚 {kg:g}kg・計 {n * kg / 1000:.1f}t")
         for c, (n, s, lg, kg) in out.items()]
    if joints:
        q.append(("敷鉄板固定金具 小判君 NTK", joints, "継ぎ目ごとに1つ（目安）"))
    return q
