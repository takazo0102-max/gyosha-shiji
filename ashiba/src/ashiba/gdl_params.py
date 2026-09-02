"""GDL（足場ライン）へ渡すパラメータの導出.

平面配置・立面図・plan.json が別々に組み立てると、片方だけ渡し漏れる。
実際、内外建地間隔と踏板幅が平面側で渡されておらずGDL既定値のまま
描かれていた。導出はここ1箇所に置く。
"""

from __future__ import annotations

import math

from .model import ScaffoldModel


def line_params(model: ScaffoldModel, ep, rules=None, stair_plan=None) -> dict:
    """足場ラインGDLに渡す共通パラメータ.

    平面と立面で別々に組み立てると片方だけ渡し漏れる（実際、内外建地間隔と
    踏板幅が平面側で渡されておらずGDL既定値のまま描かれていた）。1箇所に集約する。

    作業床高さ・根がらみ高さ・手すり高さはPython側の解を渡す。GDLで
    komaPitch から再計算させると、コマの概念が無い枠組で破綻する。
    """
    from .quantity import QuantityRules

    rules = rules or QuantityRules()
    e = model.elevation
    widths = list(model.config.deck_widths or [])
    # 枠組の交差筋交は建枠と一体で全構面に入る。くさびの斜材だけ間隔を持つ
    brace_s = 1 if model.master.is_frame else max(1, rules.brace_every_spans)
    brace_l = 1 if model.master.is_frame else max(1, rules.brace_every_levels)
    return {
        "spanList": ",".join(str(s) for s in ep.spans),
        "postList": ",".join(str(p) for p in e.posts),
        "jackOut": e.jack_extension / 1000.0,
        "komaPitch": model.master.koma_pitch / 1000.0,
        "floorH": model.master.floor_height / 1000.0,
        "standoff": ep.standoff / 1000.0,
        "rowW": model.post_row_spacing_mm / 1000.0,
        "deckW1": (widths[0] if widths else 400) / 1000.0,
        "deckW2": (widths[1] if len(widths) > 1 else 0) / 1000.0,
        "levelList": ",".join(str(int(h)) for h in e.level_heights),
        "negaH": e.first_ledger_height / 1000.0,
        "railH": model.guard_rail_height_mm / 1000.0,
        "midH": model.config.midrail_height_mm / 1000.0,
        "serType": "B" if model.master.series_id.endswith("_B") else "A",
        # 一側足場は建地1列。渡さないと図面は本足場（2列）で描かれる
        "nRows": 1 if model.config.scaffold_form == "一側足場" else 2,
        # 数量拾いと同じ間隔で描く。全構面に描くと部材表と食い違う
        "braceEveryS": brace_s,
        "braceEveryL": brace_l,
        # 朝顔は突出2mの部材。干渉確認のためモデルにも図面にも出す
        # 階段室の区間（この辺のぶんだけ）。「開始,長さ」の繰り返し
        "stairList": _stair_list(ep, stair_plan),
        "asagaoList": ",".join(str(h) for h in model.asagao_heights()),
        "asagaoProj": (model.config.asagao.projection_mm / 1000.0
                       if model.config.asagao else 2.0),
        "asagaoAngle": (model.config.asagao.angle_deg
                        if model.config.asagao else 25.0),
    }


def _stair_list(ep, stair_plan) -> str:
    """この辺に載る階段室の区間を「開始,長さ」の繰り返しで返す."""
    if stair_plan is None or not getattr(stair_plan, "towers", None):
        return ""
    parts = []
    for t in stair_plan.towers:
        if t.edge_index == ep.edge_index:
            parts += [str(int(t.start_mm)), str(int(t.length_mm))]
    return ",".join(parts)


def placement_of(model: ScaffoldModel, edge_index: int) -> dict:
    """辺のオブジェクト配置（原点と回転角）.

    配置規約: 原点=始点コーナー支柱（内側建地列）、+X=辺方向。
    平面ループはCCWで躯体は進行方向左側なので、配置角は辺方向そのまま。
    """
    ep = next(e for e in model.plan.edges if e.edge_index == edge_index)
    edge = model.plan.outline.edges[edge_index]
    angle = math.atan2(edge.direction[1], edge.direction[0])
    return {
        "x_mm": ep.start_post[0],
        "y_mm": ep.start_post[1],
        "angle_deg": round(math.degrees(angle), 6),
    }
