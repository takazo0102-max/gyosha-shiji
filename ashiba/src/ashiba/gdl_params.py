"""GDL（足場ライン）へ渡すパラメータの導出.

平面配置・立面図・plan.json が別々に組み立てると、片方だけ渡し漏れる。
実際、内外建地間隔と踏板幅が平面側で渡されておらずGDL既定値のまま
描かれていた。導出はここ1箇所に置く。
"""

from __future__ import annotations

import math

from .model import ScaffoldModel


# GDLの文字列パラメータは255文字で切れる（実機で確認: 枠組9層×6列の壁つなぎで
# tieList が途中で切れ、上層の壁つなぎが図から黙って消えていた）。
# 長いリストは続きパラメータ（name2, name3, …）に分けて渡し、GDL側で続けて読む。
GDL_STR_MAX = 255
LIST_CHUNKS = {"tieList": 5, "tieHeightList": 5, "spanList": 2, "brktList": 4,
               "glList": 2, "jackList": 2}
# レコード単位のリストは、レコードの途中で切らない（GDLは項目を順に読む）
LIST_GROUP = {"brktList": 6}
# GDL側の配列上限（1d.gdl の dim と一致させる。テストで突き合わせる）
GDL_ARRAY_CAP = {"spanList": 60, "postList": 40, "tieList": 200,
                 "tieHeightList": 200, "brktList": 24 * 6,
                 "glList": 61, "jackList": 61, "bridgeList": 8 * 4}
_LIST_LABEL = {"spanList": "スパン", "postList": "支柱構成", "tieList": "壁つなぎ",
               "tieHeightList": "壁つなぎ高さ", "brktList": "ブラケット区間の項目",
               "glList": "支柱位置の地盤高", "jackList": "支柱位置のジャッキ",
               "bridgeList": "渡した区間の項目"}


class GdlCapacityError(ValueError):
    """足場ラインGDLの上限（配列・文字列長）を超える入力.

    黙って切り捨てると図面から部材が消える（安全側に倒れない）。止めて知らせる。
    """


def _split_chunks(value: str, group: int) -> list[str]:
    items = value.split(",") if value else []
    chunks: list[str] = []
    cur: list[str] = []
    for i in range(0, len(items), group):
        rec = items[i:i + group]
        if cur and len(",".join(cur + rec)) > GDL_STR_MAX:
            chunks.append(",".join(cur))
            cur = list(rec)
        else:
            cur = cur + rec
    if cur:
        chunks.append(",".join(cur))
    return chunks


def fit_gdl_lists(params: dict, edge_index: int) -> dict:
    """リスト文字列を GDL の上限に収める。収まらなければ止める."""
    out = dict(params)
    for key, cap in GDL_ARRAY_CAP.items():
        value = params.get(key, "")
        count = len(value.split(",")) if value else 0
        if count > cap:
            raise GdlCapacityError(
                f"辺{edge_index}の{_LIST_LABEL[key]}が{count}個で、足場ラインGDLの"
                f"上限{cap}個を超えます。面を分割して配置するか、GDLの配列上限"
                "（1d.gdl の dim）と GDL_ARRAY_CAP を上げてください"
            )
    for key, n_chunks in LIST_CHUNKS.items():
        chunks = _split_chunks(params.get(key, ""), LIST_GROUP.get(key, 1))
        if len(chunks) > n_chunks:
            raise GdlCapacityError(
                f"辺{edge_index}の{key}が{len(params.get(key, ''))}文字で、"
                f"続きパラメータ{n_chunks}個（{GDL_STR_MAX * n_chunks}文字）に"
                "収まりません。面を分割して配置してください"
            )
        for k in range(n_chunks):
            out[key if k == 0 else f"{key}{k + 1}"] = chunks[k] if k < len(chunks) else ""
    for key, value in params.items():
        if isinstance(value, str) and key not in LIST_CHUNKS and len(value) > GDL_STR_MAX:
            raise GdlCapacityError(
                f"辺{edge_index}の{key}が{len(value)}文字で、GDLの文字列上限"
                f"{GDL_STR_MAX}文字を超えます（黙って切れるので止めています）"
            )
    return out


def _foot_lists(model: ScaffoldModel, ep, terrain) -> tuple[str, str]:
    """この辺の支柱位置ごとの地盤高（基準GLからの差）とジャッキ量（mm）.

    立面・3Dは平坦なGLに共通のジャッキで描いていたので、敷地高低差で
    継ぎ足した支柱（数量には入る）が図に出ず、図面と数量が食い違っていた。
    平坦（terrain無し／高低差0）なら空文字を返し、GDLは従来どおり描く。
    """
    feet = list(getattr(terrain, "feet", []) or [])
    if not feet:
        return "", ""
    # post_positions() の順（各辺の始点＋中間支柱）に feet が並ぶ。
    # この辺のぶんは連続ブロックで、終点は次の辺の始点
    edges = model.plan.edges
    offset = sum(e.span_count for e in edges if e.edge_index < ep.edge_index)
    idx = list(range(offset, offset + ep.span_count))
    nxt = offset + ep.span_count
    idx.append(nxt if nxt < len(feet) else 0)
    if max(idx) >= len(feet):
        return "", ""
    gl_ref = max(f.gl_mm for f in feet)
    picked = [feet[i] for i in idx]
    if all(abs(f.gl_mm - gl_ref) < 0.5 for f in feet):
        return "", ""          # 平坦。空にしておけば図は従来どおり
    # 図の作業床・根がらみは名目のジャッキ量を前提に描く。敷地を解くと基準面の
    # 最適化でジャッキ量が名目から動く（例: 名目100→基準脚35）ので、その差を
    # 地盤高に乗せて「脚の下端＋ジャッキ＝名目のジャッキ天端」を保つ。
    # これが無いと、脚は実ジャッキで描かれ根がらみは名目高さに残り、
    # 基準の脚でさえ緊結部が最大コマ1つぶんずれて描かれていた
    from .terrain import datum_first_ledger_mm

    shift = datum_first_ledger_mm(model, terrain) - model.elevation.first_ledger_height
    gl = ",".join(str(int(round(f.gl_mm - gl_ref - shift))) for f in picked)
    jack = ",".join(
        str(int(round(f.jack_mm + f.base_plate_adjust_mm))) for f in picked
    )
    return gl, jack


def _bridge_list(model: ScaffoldModel, ep) -> str:
    """この辺の渡した区間「開始,長さ,増える離れ,種別」.

    種別: 0=凹み／1=張り出し／2=斜辺（終点側で離れ最大）／3=斜辺（始点側で最大）
    """
    zones = [z for z in (getattr(model.plan, "bridged_zones", None) or [])
             if z.edge_index == ep.edge_index]

    def code(z) -> int:
        if z.kind == "斜辺":
            return 3 if getattr(z, "deep_end", "end") == "start" else 2
        return 1 if z.kind == "張り出し" else 0

    return ",".join(
        f"{z.start_mm:.0f},{z.end_mm - z.start_mm:.0f},{z.depth_mm:.0f},{code(z)}"
        for z in zones
    )


def line_params(
    model: ScaffoldModel, ep, rules=None, stair_plan=None, openings=None,
    platforms=None, bracket_sections=None, terrain=None,
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
    gl_list, jack_list = _foot_lists(model, ep, terrain)
    # 継ぎ足し部の根がらみをGDLが同じ規則で描くための刻み（平坦なら0で描かない）
    from .terrain import terrain_step_mm

    foot_step = terrain_step_mm(model) / 1000.0 if gl_list else 0.0
    return fit_gdl_lists({
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
        # 荷受けステージ。「開始,長さ,出,設置高さ,方杖」の繰り返し
        "stageList": _stage_list(model, ep, platforms),
        # 昇降機。「位置,到達高さ」／乗り込み口「位置,作業床高さ」の繰り返し。
        # 数量（乗り込み口の開閉式手すり）と構造（マストの局所荷重）には
        # 出ていたのに、図面には昇降機がまったく現れていなかった
        "hoistList": _hoist_list(model, ep, platforms),
        "landingList": _landing_list(model, ep, platforms),
        # ブラケット区間。「開始,終了,幅,向き,高さ」の繰り返し
        "brktList": _bracket_list(model, ep, bracket_sections),
        # 壁つなぎ。平面にも描画コードがあるのに立面でしか渡しておらず、
        # 平面では一度も描かれていなかった
        # 渡した凹み・張り出し（実際の躯体線を平面に破線で示す）
        "bridgeList": _bridge_list(model, ep),
        # 敷地高低差: 支柱位置ごとの地盤高とジャッキ（平坦なら空）
        "glList": gl_list,
        "jackList": jack_list,
        "footStep": foot_step,
        "tieList": ",".join(str(int(t.position_mm)) for t in ties),
        "tieHeightList": ",".join(str(int(t.height_mm)) for t in ties),
        "asagaoList": ",".join(str(h) for h in model.asagao_heights()),
        # 朝顔を切り欠く区間「開始,終了」の繰り返し（昇降機のマスト・搬器が通るスパン）。
        # 衝突検査が切り欠きを指示するのに、図面と3Dは全長の板のままだった
        "asaCutList": _asagao_cut_list(model, ep, platforms),
        "asagaoProj": (model.config.asagao.projection_mm / 1000.0
                       if model.config.asagao else 2.0),
        "asagaoAngle": (model.config.asagao.angle_deg
                        if model.config.asagao else 25.0),
    }, ep.edge_index)


def _asagao_cut_list(model: ScaffoldModel, ep, platforms) -> str:
    """この辺の朝顔（セーフウイング）を切り欠く区間を「開始,終了」の繰り返しで返す."""
    if not model.asagao_heights() or platforms is None or not getattr(platforms, "hoists", None):
        return ""
    from .platforms import hoist_cut_ranges

    parts = []
    for s0, e0 in hoist_cut_ranges(model, ep.edge_index, platforms.hoists):
        parts += [str(int(round(s0))), str(int(round(e0)))]
    return ",".join(parts)


def _hoist_list(model: ScaffoldModel, ep, platforms) -> str:
    """この辺の昇降機を「位置,到達高さ」の繰り返しで返す.

    到達高さの指定が無ければ足場天端まで。干渉確認のためにマストの
    占有範囲を図面と3Dに出す。
    """
    if platforms is None or not getattr(platforms, "hoists", None):
        return ""
    top = model.elevation.total_height
    parts = []
    for h in platforms.hoists:
        if h.edge_index != ep.edge_index:
            continue
        reach = h.reach_height_mm or top
        parts += [str(int(h.position_mm)), str(int(reach))]
    return ",".join(parts)


def _landing_list(model: ScaffoldModel, ep, platforms) -> str:
    """この辺の乗り込み口を「位置,作業床高さ」の繰り返しで返す.

    乗り込み口は足場側の開口。開閉式手すりを数量で拾っているので、
    どの層に開口があるかを図面にも出す（安衛則563条）。
    """
    if platforms is None or not getattr(platforms, "hoists", None):
        return ""
    levels = model.elevation.level_heights
    parts = []
    for h in platforms.hoists:
        if h.edge_index != ep.edge_index or not levels:
            continue
        for lv in h.landings(model):
            idx = min(max(int(lv), 1), len(levels)) - 1
            parts += [str(int(h.position_mm)), str(int(levels[idx]))]
    return ",".join(parts)


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
    """この辺の荷受けステージを「開始,長さ,出,設置高さ,方杖(0/1)」で返す.

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
                "1" if st.has_hozue else "0",
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
