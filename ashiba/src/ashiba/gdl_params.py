"""GDL（足場ライン）へ渡すパラメータの導出.

平面配置・立面図・plan.json が別々に組み立てると、片方だけ渡し漏れる。
実際、内外建地間隔と踏板幅が平面側で渡されておらずGDL既定値のまま
描かれていた。導出はここ1箇所に置く。
"""

from __future__ import annotations

import math

from .model import ScaffoldModel


def line_params(
    model: ScaffoldModel, ep, rules=None, stair_plan=None, openings=None,
    platforms=None, bracket_sections=None,
) -> dict:
    """足場ラインGDLに渡す共通パラメータ.

    平面と立面で別々に組み立てると片方だけ渡し漏れる（実際、内外建地間隔と
    踏板幅が平面側で渡されておらずGDL既定値のまま描かれていた）。1箇所に集約する。

    作業床高さ・根がらみ高さ・手すり高さはPython側の解を渡す。GDLで
    komaPitch から再計算させると、コマの概念が無い枠組で破綻する。
    """
    from .quantity import QuantityRules

    rules = rules or QuantityRules()
    e = model.elevation
    ties = [t for t in model.wall_ties if t.edge_index == ep.edge_index]
    widths = list(model.deck_widths_in_use)
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
        "midH": model.midrail_height_mm / 1000.0,
        # 枠組は "W"。図面側が方式を知らないと、くさび専用の特記
        # （根がらみ＝最下コマ など）を枠組の図に書いてしまう
        "serType": ("W" if model.master.is_frame
                    else "B" if model.master.series_id.endswith("_B") else "A"),
        # 一側足場は建地1列。渡さないと図面は本足場（2列）で描かれる
        "nRows": 1 if model.config.scaffold_form == "一側足場" else 2,
        # 数量拾いと同じ間隔で描く。全構面に描くと部材表と食い違う
        "braceEveryS": brace_s,
        "braceEveryL": brace_l,
        # 朝顔は突出2mの部材。干渉確認のためモデルにも図面にも出す
        # 階段室の区間（この辺のぶんだけ）。「開始,長さ」の繰り返し
        "stairList": _stair_list(ep, stair_plan),
        # 梁枠。「開始,スパン,梁下高さ」の繰り返し
        "beamList": _beam_list(model, ep, openings),
        # 荷受けステージ。「開始,長さ,出,設置高さ」の繰り返し
        "stageList": _stage_list(model, ep, platforms),
        # ブラケット区間。「開始,終了,幅,向き,高さ」の繰り返し
        "brktList": _bracket_list(model, ep, bracket_sections),
        # 壁つなぎ。平面にも描画コードがあるのに立面でしか渡しておらず、
        # 平面では一度も描かれていなかった
        "tieList": ",".join(str(int(t.position_mm)) for t in ties),
        "tieHeightList": ",".join(str(int(t.height_mm)) for t in ties),
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


def _beam_list(model: ScaffoldModel, ep, openings) -> str:
    """この辺の梁枠を「開始,スパン,梁下高さ」の繰り返しで返す.

    梁下高さは支柱を抜く作業層の高さ。図面が抜いた支柱を描いたままだと、
    実際には無い建地を図面が示すことになる。
    """
    if openings is None or not getattr(openings, "openings", None):
        return ""
    levels = model.elevation.level_heights
    parts = []
    for o in openings.openings:
        if o.edge_index != ep.edge_index:
            continue
        idx = min(max(o.level, 1), len(levels)) - 1 if levels else 0
        h = levels[idx] if levels else 0
        parts += [str(int(o.start_mm)), str(int(o.beam_span_mm)), str(int(h))]
    return ",".join(parts)


def _stage_list(model: ScaffoldModel, ep, platforms) -> str:
    """この辺の荷受けステージを「開始,長さ,出,設置高さ」の繰り返しで返す.

    出1.5mの張り出し床で、構造計算では直下の建地を個別に検定している
    のに図面にも3Dにも出ていなかった。設置層が複数なら層ごとに1組。
    """
    if platforms is None or not getattr(platforms, "stages", None):
        return ""
    levels = model.elevation.level_heights
    parts = []
    for st in platforms.stages:
        if st.edge_index != ep.edge_index or not levels:
            continue
        length = st.length_mm(model)
        for lv in (st.levels or [1]):
            idx = min(max(int(lv), 1), len(levels)) - 1
            parts += [
                str(int(st.start_mm)), str(int(length)),
                str(int(st.projection_mm)), str(int(levels[idx])),
            ]
    return ",".join(parts)


# GDL側の配列上限。層数×区間数で増えるので、超える分は描かず注記に任せる
MAX_BRACKET_GROUPS = 24


def _bracket_list(model: ScaffoldModel, ep, sections) -> str:
    """この辺のブラケット区間を「開始,終了,幅,向き,高さ,床幅」の繰り返しで返す.

    向きは 1=内（躯体側）/ -1=張出。作業層の指定が無ければ全層に効く。
    区間の幅指定は数量にも反映しているので、図面にも出さないと
    実際と違う幅の床を描いたままになる。
    """
    if not sections:
        return ""
    from .brackets import INNER

    levels = model.elevation.level_heights
    parts = []
    for sec in sections:
        if sec.edge_index != ep.edge_index or not levels:
            continue
        d = 1 if sec.direction == INNER else -1
        for lv in (sec.levels or range(1, len(levels) + 1)):
            idx = min(max(int(lv), 1), len(levels)) - 1
            if len(parts) // 6 >= MAX_BRACKET_GROUPS:
                break
            parts += [
                str(int(sec.start_mm)), str(int(sec.end_mm)),
                str(int(sec.width)), str(d), str(int(levels[idx])),
                str(int(sec.deck_width or 0)),
            ]
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
