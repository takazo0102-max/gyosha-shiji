"""型枠支保工の型枠の計算: せき板 → 根太 → 大引の曲げ応力とたわみで支柱の間隔を決める.

利用者の指定（2026-10-29）「型枠の計算をしないとスパン決めれないよ　1800飛ばせないと思う」。支柱の間隔は支柱1本の
軸力だけでなく、せき板（合板）・根太・大引がその間隔を飛ばせるかで決まる。

- 並び: 大引は長手（u）の向きに支柱の列ごと、根太は短手（v）の向きに大引の間を渡り、せき板は根太の間を渡る
  （interior_stage の大引の数え方と同じ）。大引のスパン＝長手の支柱の間隔、根太のスパン＝短手の支柱の間隔、
  せき板のスパン＝根太の間隔
- 計算は単純梁（M＝wL²/8、δ＝5wL⁴/384EI）。曲げは設計荷重（固定＋積載）、たわみは固定荷重だけ（コンクリート＋型枠）。
  たわみの上限 3mm。KKL の型枠支保工強度計算書の例（スラブ 400・合板 12・根太 @300）のせき板 σ0.70kN/cm²・
  δ0.14cm と一致する（研究メモ research_notes/地足場と内部足場/interior_stage_shoring.md）
- 部材の値: 合板 12mm は E 5500N/mm²・許容曲げ 13.7N/mm²（KKL 例）。鋼管は E 205000N/mm²・許容曲げ 157N/mm²
  （KKL 例の根太 15.7kN/cm²）。断面は寸法から求める
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFLECTION_MAX_MM = 3.0       # せき板・根太・大引のたわみの上限（KKL 例 0.30cm）
NEDA_PITCH_MM = 300.0         # 根太の間隔（せき板のスパン）
PLY_T_MM = 12.0               # せき板（型枠用合板）の厚さ
PLY_E = 5500.0                # N/mm²
PLY_FB = 13.7                 # N/mm²
STEEL_E = 205000.0
STEEL_FB = 157.0


@dataclass(frozen=True)
class Member:
    name: str
    E: float        # N/mm²
    fb: float       # 許容曲げ N/mm²
    Z: float        # mm³
    I: float        # mm⁴


def _pipe(name: str, d: float, t: float) -> Member:
    i = math.pi * (d ** 4 - (d - 2 * t) ** 4) / 64.0
    return Member(name, STEEL_E, STEEL_FB, i / (d / 2.0), i)


def _box(name: str, h: float, b: float, t: float) -> Member:
    """角形鋼管（高さ h を縦に使う＝強軸）."""
    i = (b * h ** 3 - (b - 2 * t) * (h - 2 * t) ** 3) / 12.0
    return Member(name, STEEL_E, STEEL_FB, i / (h / 2.0), i)


NEDA = {
    "単管": _pipe("単管 φ48.6×2.4", 48.6, 2.4),
    "角パイプ60": _box("角パイプ □60×60×2.3", 60.0, 60.0, 2.3),
    "角パイプ50": _box("角パイプ □50×50×2.3", 50.0, 50.0, 2.3),     # スラブ・梁下の詳細図（利用者 2026-10-31）
}
WOOD_E, WOOD_FB = 7000.0, 10.3   # 杉の角材の目安（N/mm²）


def _wood(name: str, h: float, b: float) -> Member:
    return Member(name, WOOD_E, WOOD_FB, b * h * h / 6.0, b * h ** 3 / 12.0)
OBIKI = {
    "角形鋼管100x50": _box("角形鋼管 □100×50×2.3", 100.0, 50.0, 2.3),
    "単管2本": Member("単管 φ48.6×2.4 2本", STEEL_E, STEEL_FB, 2 * NEDA["単管"].Z, 2 * NEDA["単管"].I),
    "角パイプ60": NEDA["角パイプ60"],
    "杉90": _wood("杉大引 90×90", 90.0, 90.0),                  # スラブ・梁下の詳細図（利用者 2026-10-31）
}
DEFAULT_NEDA = "単管"
DEFAULT_OBIKI = "角形鋼管100x50"


@dataclass
class BeamCheck:
    part: str
    member: str
    span_mm: float
    load_n_mm: float        # 線荷重（曲げ用）N/mm
    sigma: float            # N/mm²
    fb: float
    deflection_mm: float
    ok: bool


def _beam(part: str, m: Member, span: float, w_bend: float, w_defl: float) -> BeamCheck:
    sigma = w_bend * span ** 2 / 8.0 / m.Z
    delta = 5.0 * w_defl * span ** 4 / (384.0 * m.E * m.I)
    return BeamCheck(part, m.name, span, w_bend, sigma, m.fb, delta,
                     sigma <= m.fb + 1e-9 and delta <= DEFLECTION_MAX_MM + 1e-9)


def check(q_kn_m2: float, q_dead_kn_m2: float, su_mm: float, sv_mm: float,
          neda: str = DEFAULT_NEDA, obiki: str = DEFAULT_OBIKI, pitch_mm: float = NEDA_PITCH_MM) -> list[BeamCheck]:
    """せき板（1m 幅）・根太・大引の検定. q は kN/m²（＝N/mm² ×1e-3）."""
    ply = Member(f"合板 {PLY_T_MM:.0f}mm", PLY_E, PLY_FB, 1000.0 * PLY_T_MM ** 2 / 6.0, 1000.0 * PLY_T_MM ** 3 / 12.0)
    q, qd = q_kn_m2 * 1e-3, q_dead_kn_m2 * 1e-3            # N/mm²
    return [
        _beam("せき板", ply, pitch_mm, q * 1000.0, qd * 1000.0),
        _beam("根太", NEDA[neda], sv_mm, q * pitch_mm, qd * pitch_mm),
        _beam("大引", OBIKI[obiki], su_mm, q * sv_mm, qd * sv_mm),
    ]


def max_spans(q_kn_m2: float, q_dead_kn_m2: float, coins_u: list[int], coins_v: list[int],
              post_ok, neda: str = DEFAULT_NEDA, obiki: str = DEFAULT_OBIKI) -> tuple[int, int] | None:
    """型枠の部材と支柱1本の軸力（post_ok(su, sv) が True）がみな通る、いちばん広い支柱の間隔（長手, 短手）."""
    best = None
    for su in coins_u:
        for sv in coins_v:
            if not post_ok(su, sv):
                continue
            if all(c.ok for c in check(q_kn_m2, q_dead_kn_m2, su, sv, neda, obiki)):
                key = (su * sv, su)
                if best is None or key > best[0]:
                    best = (key, (su, sv))
    return best[1] if best else None
