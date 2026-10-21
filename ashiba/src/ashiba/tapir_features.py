"""Tapir・Archicad の版と、ツールの機能の対応（どの版で何が使えるか）.

実機で確かめた組み合わせだけを「使える」とする。断面図方式の立面（断面の作成・
ChangeWindow で断面を開いて注記・レイアウトへの図面配置）と足場平面図のレイアウトは
Tapir 1.7.0 ＋ Archicad 30 で確認した命令に頼るので、それより古い Tapir では
部品方式の立面（elevation_mode=object、Archicad 28 ＋ Tapir 1.5.8 で確認済み）に戻す。
新しい版は止めずに「未確認」とだけ伝える（Tapir は後方互換で命令を足していく）。
"""

from __future__ import annotations

import re
from typing import Optional

# 断面図方式の立面・平面図レイアウトに要る Tapir の版（実機で確認した最小の版）
SECTION_MODE_MIN_TAPIR = (1, 7, 0)
# 実機で確認した組み合わせ（Archicad の版 → Tapir の版）
VERIFIED = {28: (1, 5, 8), 30: (1, 7, 0)}


def parse_version(text: str) -> Optional[tuple[int, int, int]]:
    """'1.7.0' → (1, 7, 0)。'1.7' は (1, 7, 0)。読めなければ None."""
    m = re.match(r"\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text or ""))
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())  # type: ignore[return-value]


def fmt(v: Optional[tuple]) -> str:
    return ".".join(str(x) for x in v) if v else "不明"


def choose_elevation_mode(requested: str, tapir_version: str) -> tuple[str, list[str]]:
    """入力の立面方式と Tapir の版から、実際に使う方式と案内文を決める.

    断面方式を頼まれても Tapir が 1.7.0 より古い（または版を読めない＝GetAddOnVersion が
    無いほど古い）なら部品方式に戻す。部品方式を頼まれたときはそのまま。
    """
    # none＝立面・断面を作らない（3D を直している間など。利用者の指定 2026-10-22: 立面断面の生成は不要）。
    # 以前は section・object 以外を section にしていて、none を指定しても断面方式で作っていた
    mode = requested if requested in ("section", "object", "none") else "section"
    if mode != "section":
        return mode, []
    v = parse_version(tapir_version)
    if v is None or v < SECTION_MODE_MIN_TAPIR:
        return "object", [
            f"Tapir {fmt(v)} では断面図方式の立面（断面ビューポイント→レイアウト）が使えないため、"
            f"平面に部品で立面を描く方式にしました。Tapir {fmt(SECTION_MODE_MIN_TAPIR)} 以上に更新すると"
            "断面図方式と足場平面図のレイアウトが使えます"]
    return mode, []


def environment_notes(tapir_version: str, archicad_version: Optional[int]) -> list[str]:
    """実機で確認していない組み合わせなら、その旨を1行で（止めはしない）."""
    v = parse_version(tapir_version)
    if v is None:
        return []          # choose_elevation_mode が案内する
    known = VERIFIED.get(archicad_version) if archicad_version is not None else None
    if known is not None and v >= known:
        return []
    ac = f"Archicad {archicad_version}" if archicad_version is not None else "Archicad（版不明）"
    checked = "・".join(f"Archicad {a} ＋ Tapir {fmt(t)}" for a, t in sorted(VERIFIED.items()))
    return [f"{ac} ＋ Tapir {fmt(v)} は実機で未確認の組み合わせです（確認済み: {checked}）。"
            "おかしな描画があれば知らせてください"]
