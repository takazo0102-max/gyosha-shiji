"""詳細図5枚（設置届の添付図書）の要否判定とパラメータ導出.

指示書§6.7: 脚部・壁つなぎ部・朝顔取付部・コーナー部・開口梁枠部の5枚を
2DシンボルGDL（ashiba_detail）で作る。系列IDパラメータで寸法値のみ差替える。

どの詳細図が要るかは計画内容で決まる:
- 脚部・壁つなぎ・コーナー: 常に必要
- 朝顔: 高さ10m以上（10m以上で1段・20m以上で2段）
- 梁枠: 開口部（出入口等で支柱を抜く箇所）がある場合のみ

detailType は必ずASCIIキー。日本語文字列を外部からGDLへ渡すと比較が一致しない
（Archicad 28実機で確認済み）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import ScaffoldModel

# ASCIIキー → 日本語表示名
DETAIL_NAMES = {
    "base": "脚部詳細",
    "tie": "壁つなぎ部詳細",
    "asagao": "朝顔取付部詳細",
    "corner": "コーナー部詳細",
    "beam": "開口部 梁枠詳細",
}

ASAGAO_MIN_HEIGHT_MM = 10000   # 朝顔が必要になる高さ
ASAGAO_2ND_HEIGHT_MM = 20000   # 2段必要になる高さ


@dataclass
class DetailSheet:
    key: str                       # ASCIIキー（GDLのdetailType）
    title: str                     # 日本語の図面名
    params: dict = field(default_factory=dict)
    reason: str = ""               # なぜこの図が必要か（帳票に出す）

    @property
    def sheet_name(self) -> str:
        return DETAIL_NAMES.get(self.key, self.key)


def required_details(
    model: ScaffoldModel,
    openings: Optional[list[dict]] = None,
    force_all: bool = False,
    terrain=None,
) -> list[DetailSheet]:
    """この計画に必要な詳細図を決め、GDLパラメータまで埋めて返す.

    openings: [{"beam_span_mm": 3600}, ...] 開口部（梁枠が要る箇所）
    force_all: Trueなら不要な図も含め5枚すべて返す
    terrain: 敷地の解。渡すと脚部詳細のジャッキ繰出しを実際の最大値で描く
    """
    e = model.elevation
    # 枠組は "W"。くさびのA/Bと同じ扱いにすると、枠組の計画に
    # くさびの納まり図が注意書き無しで付いてしまう
    if model.master.is_frame:
        ser = "W"
    else:
        ser = "B" if model.master.series_id.endswith("_B") else "A"
    v_lim, h_lim, _ = model.wall_tie_limits()
    common = {
        "serType": ser,
        # 図面に埋め込む法規しきい値も系列で変わる（570条1項五号）
        "tieVLim": v_lim / 1000.0,
        "tieHLim": h_lim / 1000.0,
        "standoff": _median_standoff(model) / 1000.0,
        "rowW": model.post_row_spacing_mm / 1000.0,
        "spanW": _common_span(model) / 1000.0,
        "deckW1": model.deck_widths_in_use[0] / 1000.0,
        "deckW2": (model.deck_widths_in_use[1] / 1000.0
                   if len(model.deck_widths_in_use) > 1 else 0.0),
    }
    v_max, h_max = model.wall_tie_max_spacing()
    height = model.scaffold_height_mm

    # 脚部詳細は「実際に一番繰り出す支柱」で描く。平坦時の値で描くと、
    # 法規チェックが435mmを警告している横で図面は100mmを示すことになる
    jack_mm = e.jack_extension
    jack_note = ""
    if terrain is not None and getattr(terrain, "feet", None):
        worst = max(f.jack_mm for f in terrain.feet)
        if worst > jack_mm:
            jack_mm = int(round(worst))
            jack_note = f"（敷地高低差により最大繰出し{jack_mm}mmの支柱で作図）"

    sheets = [
        DetailSheet(
            key="base",
            title=DETAIL_NAMES["base"],
            params={**common,
                    "jackOut": jack_mm / 1000.0,
                    # 根がらみ高さは立面ソルバの結果から。コマピッチで決め打ちすると
                    # コマの概念が無い枠組で0になる
                    "negaLv": max(
                        0.0, (e.first_ledger_height - e.jack_extension) / 1000.0
                    )},
            reason="全ての足場に必要（脚部・根がらみ・ジャッキ）" + jack_note,
        ),
        DetailSheet(
            key="tie",
            title=DETAIL_NAMES["tie"],
            params={**common,
                    "tieV": v_max / 1000.0,
                    "tieH": h_max / 1000.0},
            reason=f"壁つなぎ{len(model.wall_ties)}箇所の取付方法を示すため",
        ),
        DetailSheet(
            key="corner",
            title=DETAIL_NAMES["corner"],
            params={**common},
            reason=f"出隅{_corner_count(model, '出隅')}／"
                   f"入隅{_corner_count(model, '入隅')}箇所の納まりを示すため",
        ),
    ]

    if force_all or height >= ASAGAO_MIN_HEIGHT_MM:
        need = 2 if height >= ASAGAO_2ND_HEIGHT_MM else 1
        # 突出・傾斜は計画値で描く。既定値で描くと、指定した朝顔と
        # 添付図書の朝顔が食い違う
        a = model.config.asagao
        proj = a.projection_mm if a else 2000.0
        angle = a.angle_deg if a else 25.0
        stages = a.stages if a else need
        reason = f"足場高さ{height / 1000:.1f}m ≧ 10m のため朝顔{need}段が必要"
        if stages != need:
            reason += f"（計画は{stages}段）"
        sheets.append(
            DetailSheet(
                key="asagao",
                title=DETAIL_NAMES["asagao"],
                params={**common,
                        "asagaoProj": proj / 1000.0,
                        "asagaoAngle": angle},
                reason=reason,
            )
        )

    spans = [o.get("beam_span_mm", 3600) for o in (openings or [])]
    if force_all and not spans:
        spans = [3600]
    for i, span in enumerate(spans):
        sheets.append(
            DetailSheet(
                key="beam",
                title=DETAIL_NAMES["beam"] + (f"（開口{i + 1}）" if len(spans) > 1 else ""),
                params={**common, "beamSpan": span / 1000.0},
                reason=f"開口部（梁枠{span}mm）で支柱を抜くため",
            )
        )
    return sheets


def _median_standoff(model: ScaffoldModel) -> float:
    ds = sorted(model.plan.standoffs)
    return ds[len(ds) // 2] if ds else 300.0


def _common_span(model: ScaffoldModel) -> int:
    """最も本数の多いスパン（詳細図に描く代表スパン）."""
    counts: dict[int, int] = {}
    for ep in model.plan.edges:
        for s in ep.spans:
            counts[s] = counts.get(s, 0) + 1
    return max(counts, key=counts.get) if counts else 1800


def _corner_count(model: ScaffoldModel, kind: str) -> int:
    return sum(1 for c in model.plan.outline.corners if c.kind == kind)
