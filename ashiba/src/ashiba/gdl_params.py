"""GDL（足場ライン）へ渡すパラメータの導出.

平面配置・立面図・plan.json が別々に組み立てると、片方だけ渡し漏れる。
実際、内外建地間隔と踏板幅が平面側で渡されておらずGDL既定値のまま
描かれていた。導出はここ1箇所に置く。
"""

from __future__ import annotations

import math

from .model import ScaffoldModel
from .model import GUARD_RAIL_ADVANCE
from .segments import WHOLE


# GDLの文字列パラメータは255文字で切れる（実機で確認: 枠組9層×6列の壁つなぎで
# tieList が途中で切れ、上層の壁つなぎが図から黙って消えていた）。
# 長いリストは続きパラメータ（name2, name3, …）に分けて渡し、GDL側で続けて読む。
GDL_STR_MAX = 255
LIST_CHUNKS = {"tieList": 5, "tieHeightList": 5, "spanList": 2, "brktList": 4,
               "glList": 2, "jackList": 2, "shimList": 2, "glListO": 2, "jackListO": 2, "shimListO": 2}
# レコード単位のリストは、レコードの途中で切らない（GDLは項目を順に読む）
LIST_GROUP = {"brktList": 6}
# GDL側の配列上限（1d.gdl の dim と一致させる。テストで突き合わせる）
GDL_ARRAY_CAP = {"spanList": 60, "postList": 40, "tieList": 200,
                 "tieHeightList": 200, "brktList": 24 * 6,
                 "glList": 61, "jackList": 61, "shimList": 61, "bridgeList": 8 * 4,
                 "glListO": 61, "jackListO": 61, "shimListO": 61,
                 "editList": 16 * 5}
_LIST_LABEL = {"spanList": "スパン", "postList": "支柱構成", "tieList": "壁つなぎ",
               "tieHeightList": "壁つなぎ高さ", "brktList": "ブラケット区間の項目",
               "glList": "支柱位置の地盤高", "jackList": "支柱位置のジャッキ",
               "shimList": "支柱位置の敷板調整",
               "glListO": "外側の列の地盤高", "jackListO": "外側の列のジャッキ", "shimListO": "外側の列の敷板調整",
               "bridgeList": "渡した区間の項目", "editList": "部材編集の項目"}


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


def _foot_lists(model: ScaffoldModel, ep, terrain, outer: bool = False) -> tuple[str, str, str]:
    """この辺の支柱位置ごとの地盤高（基準GLからの差）とジャッキ量（mm）.

    立面・3Dは平坦なGLに共通のジャッキで描いていたので、敷地高低差で
    継ぎ足した支柱（数量には入る）が図に出ず、図面と数量が食い違っていた。
    平坦（terrain無し／高低差0）なら空文字を返し、GDLは従来どおり描く。
    """
    feet = list(getattr(terrain, "feet", []) or [])
    if not feet:
        return "", "", ""
    # 外側の列（本足場。地盤を内側とは別に解いたもの）。基準（gl_ref・shift）は内側の列と同じにする
    rows_feet = list(getattr(terrain, "feet_outer", []) or []) if outer else feet
    if outer and len(rows_feet) != len(feet):
        return "", "", ""
    # post_positions() の順（各辺の始点＋中間支柱）に feet が並ぶ。
    # この辺のぶんは連続ブロックで、終点は次の辺の始点
    edges = model.plan.edges
    offset = sum(e.span_count for e in edges if e.edge_index < ep.edge_index)
    idx = list(range(offset, offset + ep.span_count))
    nxt = offset + ep.span_count
    idx.append(nxt if nxt < len(feet) else 0)
    if max(idx) >= len(feet):
        return "", "", ""
    gl_ref = max(f.gl_mm for f in feet)
    picked = [rows_feet[i] for i in idx]
    if all(abs(f.gl_mm - gl_ref) < 0.5 for f in list(feet) + list(getattr(terrain, "feet_outer", []) or [])):
        return "", "", ""      # 平坦。空にしておけば図は従来どおり
    # 図の作業床・根がらみは名目のジャッキ量を前提に描く。敷地を解くと基準面の
    # 最適化でジャッキ量が名目から動く（例: 名目100→基準脚35）ので、その差を
    # 地盤高に乗せて「脚の下端＋ジャッキ＝名目のジャッキ天端」を保つ。
    # これが無いと、脚は実ジャッキで描かれ根がらみは名目高さに残り、
    # 基準の脚でさえ緊結部が最大コマ1つぶんずれて描かれていた
    from .terrain import datum_first_ledger_mm

    shift = datum_first_ledger_mm(model, terrain) - model.elevation_of(ep.edge_index).first_ledger_height
    gl = ",".join(str(int(round(f.gl_mm - gl_ref - shift))) for f in picked)
    jack = ",".join(
        str(int(round(f.jack_mm + f.base_plate_adjust_mm))) for f in picked
    )
    # 敷板で持ち上げた分（正のみ）。図では敷板を重ねて描き、ねじ棒はその上から
    shim = ",".join(str(int(round(max(0.0, f.base_plate_adjust_mm)))) for f in picked)
    return gl, jack, shim


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
    # 面ごとの立面（セットバックで低い面は全体の立面を軒高で切ったもの）
    e = model.elevation_of(ep.edge_index)
    ties = [t for t in model.wall_ties if t.edge_index == ep.edge_index]
    widths = list(model.deck_widths_in_use)
    # 枠組の交差筋交は建枠と一体で全構面に入る。くさびの斜材だけ間隔を持つ
    brace_s = 1 if model.master.is_frame else max(1, rules.brace_every_spans)
    brace_l = 1 if model.master.is_frame else max(1, rules.brace_every_levels)
    gl_list, jack_list, shim_list = _foot_lists(model, ep, terrain)
    gl_o, jack_o, shim_o = _foot_lists(model, ep, terrain, outer=True)
    # 継ぎ足し部の根がらみをGDLが同じ規則で描くための刻み（平坦なら0で描かない）
    from .terrain import terrain_step_mm

    foot_step = terrain_step_mm(model) / 1000.0 if gl_list else 0.0
    return fit_gdl_lists({
        "spanList": ",".join(str(s) for s in ep.spans),
        "postList": ",".join(str(p) for p in e.posts),
        # 単管の建地は継手を千鳥にする（偶数番目の建地はこの並び。利用者の指定 2026-10-22）。くさび・枠組は空
        "postListAlt": (",".join(str(p) for p in e.posts_alt)
                        if model.master.is_tube and list(e.posts_alt) != list(e.posts) else ""),
        "jackOut": e.jack_extension / 1000.0,
        # 単管はコマが無い（高さの刻みは描かない）
        "komaPitch": 0.0 if model.master.is_tube else model.master.koma_pitch / 1000.0,
        # コマの位置（カタログの支柱図。master.post_koma_offsets と同じ規則を 3d.gdl で支柱1本ごとに計算）
        "komaGap": model.master.koma_top_gap / 1000.0,
        "komaNega": _koma_const(model, "koma_nega") / 1000.0,
        "negaLens": ",".join(str(v) for v in _koma_const(model, "nega_koma_lengths", ())),
        "floorH": model.master.floor_height / 1000.0,
        "standoff": ep.standoff / 1000.0,
        "rowW": model.post_row_spacing_mm / 1000.0,
        "deckW1": (widths[0] if widths else (0 if model.config.is_hug else 400)) / 1000.0,
        "deckW2": (widths[1] if len(widths) > 1 else 0) / 1000.0,
        # 単管の足場板の枚数（3枚以上は deckW1 と同じ幅で並べる）。くさび・枠組は0
        "deckN": len(widths) if model.master.is_tube else 0,
        # 階段を外側の板の位置に寄せ、内側の板（ハーフアンチ）を階段の層も敷く（model.stair_half_deck）
        "stHalf": 1 if model.stair_half_deck else 0,
        "levelList": ",".join(str(int(h)) for h in e.level_heights),
        # 3D の天端のホットスポット（足場高さの編集）。部品の天端（ジャッキ＋支柱）と同じ値で送り、
        # 食い違ったら「引かれた」とみなして層を足し引きする（vl.gdl）
        "topEdit": (e.jack_extension + sum(e.posts)) / 1000.0,
        "negaH": e.first_ledger_height / 1000.0,
        "railH": model.guard_rail_height_mm / 1000.0,
        "midH": model.midrail_height_mm / 1000.0,
        # 先行手すり工法は手すり＋斜材の一体部材で、斜材が中桟を兼ねる。数量と法規は
        # そう扱っているのに、図面と3Dは布材の手すり＋中桟のままだった（実機で発見）
        "railAdv": 1 if (model.config.guard_rail_type == GUARD_RAIL_ADVANCE and not model.master.is_frame) else 0,
        # 躯体側の手すり・中桟（布材）。数量の rails_inner と同じ条件（列数はGDL側の nRows で見る）
        "railIn": 1 if (model.config.inner_guard_rail and not model.master.is_frame) else 0,
        # 3Dの線表示（Boolean は bool で送る。int だと Tapir が全パラメータを落とす）
        "lineMode": bool(model.config.line_mode_3d),
        # 表示設定を読むライブラリグローバル部品の名前（配布部品は版付きで埋め込まれる）
        "mvoName": mvo_part_name(),
        "planSimple": False,
        # 平面のスパン寸法を寸法ツールで付けたら True にする（配置後に。部品の寸法と二重にしない）
        "dimTool": False,
        # 壁つなぎを別の部品（ashiba_tie）で置けたら True にする（配置後に。部品の壁つなぎと二重にしない）
        "tieObj": False,
        # 平面のホットスポット編集。吸着先は系列の布材の呼び寸法（xEdit は部品が作る）
        "editSpan": True,
        "sizeList": ",".join(str(v) for v in model.master.span_lengths()),
        # 枠組は "W"。図面側が方式を知らないと、くさび専用の特記
        # （根がらみ＝最下コマ など）を枠組の図に書いてしまう
        # 単管は "T"（布・腕木・手すりは建地の脇にクランプで留めた管、コマは無い）
        "serType": ("W" if model.master.is_frame else "T" if model.master.is_tube
                    else "B" if model.master.series_id.endswith("_B") else "A"),
        # 単管抱き足場（建地1列を布2本で抱き、その上に足場板）
        "hugMode": 1 if model.config.is_hug else 0,
        # 単管抱き足場の隅の建地では、直交する2つの面の布・手すりが同じ高さだと交わる。南北に走る面は
        # クランプ1つ分（60）上で留める（実際も直交する管は上下にずらして留める）
        "hugDz": (0.06 if model.config.is_hug and _runs_north_south(model, ep.edge_index) else 0.0),
        # 単管の通し（布・手すり・中桟・根がらみ）: 規定の長さの単管の割付 A・B（tube_runs。数量と同じ割付）
        **_tube_run_params(model, ep),
        # 一側足場は建地1列。渡さないと図面は本足場（2列）で描かれる
        "nRows": 1 if model.config.scaffold_form == "一側足場" else 2,
        # 始点が出隅なら、その外側のコーナー（外側建地・布材・踏板・幅木）をこの面が描く
        # （各面は始点支柱を所有する規則と同じ向き。実機の3Dで四隅が抜けていた）
        # 単管抱き足場は建地列が線の上で、出隅の建地は隣の面と同じ1本（skipInS・skipInE で片方が描く）
        "cornerS": 1 if (not model.master.is_frame and not model.config.is_hug
                         and model.corner_kind_start(ep.edge_index) == "出隅") else 0,
        # 隅の内側建地は隣の面と同じ1本。高い方の面（同じなら次の面）だけが描く
        **shared_corner_skips(model, ep.edge_index),
        # 終点が出隅か（コーナーは次の面が描く）。平面の寸法を外側の角の支柱まで張るのに使う
        "cornerE": 1 if (not model.master.is_frame and not model.config.is_hug
                         and model.corner_kind_end(ep.edge_index) == "出隅") else 0,
        # 数量拾いと同じ間隔で描く。全構面に描くと部材表と食い違う
        "braceEveryS": brace_s,
        "braceEveryL": brace_l,
        # 朝顔は突出2mの部材。干渉確認のためモデルにも図面にも出す
        # 階段室の区間（この辺のぶんだけ）。「開始,長さ」の繰り返し
        "stairList": _stair_list(ep, stair_plan),
        # 支柱の径（足場の種類ごと。マスタの支柱の径）
        "postDia": _post_diameter_m(model),
        # 一部の面だけの足場の開放端（隣の面を掛けない端）は、妻側に手すり・中桟・幅木を付ける
        # （参考: smartCON Planner の「墜落の危険箇所に手すり」「エンドストッパー」）
        "endOpenS": 1 if model.open_start(ep.edge_index) else 0,
        "endOpenE": 1 if model.open_end(ep.edge_index) else 0,
        # 枠組の出隅はギャプレス（コーナー布受け）で納める（日建カタログ p104〜105）
        "cornerG": 1 if (model.master.is_frame
                         and model.corner_kind_start(ep.edge_index) == "出隅") else 0,
        # 支柱の形（NDストロングは φ42.7・φ48.6 の異形断面）
        "postShape": 1 if model.master.series_id == "nikken_strong" else 0,
        # 外付け: 外側建地列の外の升目（上り口＋階段＋降り口）。本体の床は切らない
        "stOut": 1 if getattr(stair_plan, "outside", False) else 0,
        # 階段室の開始位置（平面の編集ホットスポット）。stairList とそろえて送る。部品は両者が
        # 食い違えば「引かれた」とみなしてスパン境界へ吸着する（vl.gdl）
        "stEdit": _stair_edit(ep, stair_plan),
        # ステージ・昇降機の位置（同じく stageList・hoistList とそろえて送る）
        "sgEdit": _list_edit(_stage_list(model, ep, platforms), 5),
        "hoEdit": _list_edit(_hoist_list(model, ep, platforms), 5),
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
        # 範囲を指定して外した部材「スパン始,スパン終,層始,層終,ビット（1踏板 2外側手すり 4幅木 8筋かい 16内側手すり）」
        "editList": _edit_list(model, ep),
        # 支柱だけ分解した状態（scripts/explode_line.py が 1 にする）と、区切った部品の範囲・区切る位置
        # （scripts/split_line.py）。置き直したら分解・区切りの無い面に戻す
        "explodeMask": 0,
        **WHOLE,
        # 敷地高低差: 支柱位置ごとの地盤高とジャッキ（平坦なら空）
        "glList": gl_list,
        "jackList": jack_list,
        "shimList": shim_list,
        # 外側の建地列の地盤高・ジャッキ・敷板（本足場で地盤を内外別に解いたとき。空なら内側の列と同じ）
        "glListO": gl_o,
        "jackListO": jack_o,
        "shimListO": shim_o,
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


def _koma_const(model: ScaffoldModel, key: str, default=0):
    from .master import SERIES_CONST

    return SERIES_CONST.get(model.master.series_id, {}).get(key, default) or default


def _edit_list(model: ScaffoldModel, ep) -> str:
    from .member_edits import edit_list

    return edit_list(model, ep, getattr(model, "member_edits", None))


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
    """この辺の昇降機を「位置,到達高さ,搬器幅,搬器奥行,控えピッチ」の繰り返しで返す.

    到達高さの指定が無ければ足場天端まで。干渉確認のためにマストの
    占有範囲を図面と3Dに出す。控えピッチはマスト控え（足場外側建地へ）の
    間隔で、3Dに控えを描く。
    """
    if platforms is None or not getattr(platforms, "hoists", None):
        return ""
    top = model.elevation_of(ep.edge_index).total_height
    parts = []
    for h in platforms.hoists:
        if h.edge_index != ep.edge_index:
            continue
        reach = h.reach_height_mm or top
        # 搬器の幅・奥行も渡す（詳細図と同じ寸法で平面・立面・3Dに出す）
        parts += [str(int(h.position_mm)), str(int(reach)),
                  str(int(getattr(h, "cage_width_mm", 2000) or 2000)),
                  str(int(getattr(h, "cage_depth_mm", 2000) or 2000)),
                  str(int(getattr(h, "tie_every_mm", 3600) or 3600))]
    return ",".join(parts)


def _landing_list(model: ScaffoldModel, ep, platforms) -> str:
    """この辺の乗り込み口を「位置,作業床高さ」の繰り返しで返す.

    乗り込み口は足場側の開口。開閉式手すりを数量で拾っているので、
    どの層に開口があるかを図面にも出す（安衛則563条）。
    """
    if platforms is None or not getattr(platforms, "hoists", None):
        return ""
    levels = model.elevation_of(ep.edge_index).level_heights
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


def _stair_edit(ep, stair_plan) -> list[float]:
    """stairList の開始位置（m）の配列。階段室が無ければ [0]（配列は空にできない）."""
    starts = [float(t.start_mm) / 1000.0 for t in (getattr(stair_plan, "towers", None) or [])
              if t.edge_index == ep.edge_index]
    return starts or [0.0]


def _list_edit(text: str, group: int) -> list[float]:
    """「位置,…」が group 個ずつ並ぶリストの、各組の先頭（m）の配列。空なら [0]."""
    vals = [v for v in text.split(",") if v.strip()]
    starts = [float(vals[i]) / 1000.0 for i in range(0, len(vals) - group + 1, group)]
    return starts or [0.0]


def _beam_list(model: ScaffoldModel, ep, openings) -> str:
    """この辺の梁枠を「開始,スパン,梁下高さ」の繰り返しで返す.

    梁下高さは支柱を抜く作業層の高さ。図面が抜いた支柱を描いたままだと、
    実際には無い建地を図面が示すことになる。
    """
    if openings is None or not getattr(openings, "openings", None):
        return ""
    levels = model.elevation_of(ep.edge_index).level_heights
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
    levels = model.elevation_of(ep.edge_index).level_heights
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

    levels = model.elevation_of(ep.edge_index).level_heights
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
                str(int(round(getattr(sec, "reach_mm", sec.width)))), str(d), str(int(levels[idx])),
                str(int(sec.deck_width or 0)),
            ]
    return ",".join(parts)


def _post_diameter_m(model: ScaffoldModel) -> float:
    """マスタの支柱（枠組は建枠）の径 m。無ければ 0（部品の既定 φ48.6）."""
    cat = "建枠" if model.master.is_frame else "支柱"
    dia = next((p.diameter for p in model.master.by_category(cat) if p.diameter > 0), 0.0)
    return round(float(dia) / 1000.0, 4)


def _tube_run_params(model: ScaffoldModel, ep) -> dict:
    """単管の通しの割付（くさび・枠組は空）."""
    if not model.master.is_tube:
        return {"tubeRunA": "", "tubeRunB": "", "tubeRunS": -0.1, "deckRunA": "", "deckRunB": "", "deckRunS": -0.1}
    from .tube_runs import face_runs

    a, b = face_runs(list(ep.spans))
    out = {"tubeRunA": ",".join(str(v) for v in a.pieces), "tubeRunB": ",".join(str(v) for v in b.pieces),
           "tubeRunS": a.start_mm / 1000.0, "deckRunA": "", "deckRunB": "", "deckRunS": -0.1}
    # 足場板（ブラケット足場の床）: 規定の長さで面に沿って敷き、継ぎは300重ねる（数量と同じ割付）
    if model.deck_widths_in_use:
        from .tube_runs import face_boards

        da, db = face_boards(list(ep.spans))
        out.update({"deckRunA": ",".join(str(v) for v in da.pieces), "deckRunB": ",".join(str(v) for v in db.pieces),
                    "deckRunS": da.start_mm / 1000.0})
    return out


def _runs_north_south(model: ScaffoldModel, edge_index: int) -> bool:
    """その面の辺が南北（Y）に走るか."""
    e = model.plan.outline.edges[edge_index]
    return abs(e.direction[1]) > abs(e.direction[0])


def shared_corner_skips(model: ScaffoldModel, edge_index: int) -> dict:
    """隅の内側建地（この面の終点＝次の面の始点）をどちらの面が描くか.

    両方の面が描くと同じ位置に支柱が2本重なる（利用者の指摘 2026-10-20）。面の高さが違う
    （セットバック）ときは高い方が描かないと隅の支柱が途中で切れるので、高い方、同じなら次の面が描く。
    隣の面を建てていない（上の部分だけ・面の一部だけ）ときは自分で描く。
    """
    n = len(model.plan.outline.edges)
    built = {e.edge_index for e in model.plan.edges}
    h = model.elevation_of(edge_index).total_height
    prev_i, next_i = (edge_index - 1) % n, (edge_index + 1) % n
    skip_s = prev_i in built and prev_i != edge_index and model.elevation_of(prev_i).total_height > h
    skip_e = next_i in built and next_i != edge_index and model.elevation_of(next_i).total_height >= h
    return {"skipInS": 1 if skip_s else 0, "skipInE": 1 if skip_e else 0}


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


def mvo_part_name(gdl_dir=None) -> str:
    """モデル表示オプション部品（ashiba_mvo）の埋め込み名。配布版は「ashiba_mvo_<HSFハッシュ8桁>」.

    足場ラインは LIBRARYGLOBAL でこの名前の部品から表示設定を読む。版付きで埋め込む
    （埋め込み部品は上書きできない）ので、名前を部品に渡す。ハッシュが無ければ基本名。
    """
    from pathlib import Path

    base = "ashiba_mvo"
    root = Path(gdl_dir) if gdl_dir else Path(__file__).resolve().parents[2] / "gdl"
    stamp = root / f"{base}.gsm.hash"
    if not stamp.exists():
        return base
    h = stamp.read_text(encoding="utf-8").strip()
    return f"{base}_{h}" if h.isalnum() and len(h) == 8 else base


FACE_COUNT_PARAMS = ("qtyPostPos", "qtyPost", "qtyNuno", "qtyDeck", "qtyToe", "qtyAdv", "qtyTie", "qtyBrace", "qtyStair")


def _span_starts(spans) -> list[float]:
    out, x = [], 0.0
    for sp in spans:
        out.append(x)
        x += sp
    return out


def face_drawn_counts(model: ScaffoldModel, ep, stair_plan=None, openings=None, rules=None) -> dict[str, int]:
    """足場ラインの1Dスクリプトが書き戻す「図示本数」と同じ式（面ごと）.

    部品側は Archicad の一覧表で集計するための値で、発注数量の正は take_off。
    この関数はテストで take_off と突き合わせ、図面の本数と数量表がずれていないことを
    確かめるためのもの（GDL の式を変えたらここも変える）。
    """
    from .quantity import QuantityRules

    rules = rules or QuantityRules()
    e = model.elevation_of(ep.edge_index)
    n_levels = e.n_levels
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    corner = 1 if (not model.master.is_frame
                   and model.corner_kind_start(ep.edge_index) == "出隅") else 0
    adv = 1 if (model.config.guard_rail_type == GUARD_RAIL_ADVANCE and not model.master.is_frame) else 0
    outer = 0 if adv else 2
    inner = 2 if (model.config.inner_guard_rail and not model.master.is_frame and rows >= 2) else 0
    levels = [e.first_ledger_height] + list(e.level_heights)
    beams = []
    if openings is not None:
        # 梁下高さは _beam_list と同じ: 支柱を抜く層の作業床高さ
        for o in openings.openings:
            if o.edge_index == ep.edge_index and e.level_heights:
                idx = min(max(o.level, 1), len(e.level_heights)) - 1
                beams.append((o.start_mm, o.end_mm, e.level_heights[idx]))
    # 外付けの階段は本体の床を切らない（1d.gdl の stOut と同じ）
    outside = bool(getattr(stair_plan, "outside", False))
    all_towers = [(t.start_mm, t.start_mm + t.length_mm) for t in getattr(stair_plan, "towers", []) or []
                  if t.edge_index == ep.edge_index]
    towers = [] if outside else all_towers
    nuno = deck = toe = advq = 0
    x = 0.0
    for sp in ep.spans:
        open_lv = 0
        open_nega = 0
        for s0, e0, bh in beams:
            if x >= s0 - 1e-6 and x + sp <= e0 + 1e-6 and bh is not None:
                if levels[0] < bh - 1e-6:
                    open_nega = 1
                open_lv += sum(1 for h in levels[1:] if h < bh - 1e-6)
        # 階段室: 各層で階段が上がってくる1スパンだけ開口（奇数層は始点側、偶数層は終点側。1d.gdl と同じ）
        stair_open = 0
        for s0, e0 in towers:
            if x >= s0 - 1e-6 and x + sp <= e0 + 1e-6:
                pos = sum(1 for xx in _span_starts(ep.spans) if s0 - 1e-6 <= xx < x - 1e-6)
                one = e0 - s0 <= sp + 1e-6
                stair_open = n_levels if one else ((n_levels + 1) // 2 if pos == 0 else n_levels // 2 if pos == 1 else 0)
        # 作業床の高さのスパン方向の布材は付けない（1d.gdl と同じ）
        nuno += rows * (1 - open_nega) + (n_levels - open_lv) * (outer + inner)
        deck += max(0, n_levels - open_lv - stair_open)
        if adv:
            advq += n_levels - open_lv
        else:
            # 階段が上がってくるスパンは外側の幅木も付けない（載せる布板が無い。3d.gdl・数量と同じ）
            toe += max(0, n_levels - open_lv - (0 if model.master.is_tube else stair_open))
        x += sp
    ev_s = 1 if model.master.is_frame else max(1, rules.brace_every_spans)
    ev_l = 1 if model.master.is_frame else max(1, rules.brace_every_levels)
    brace = 2 * sum(1 for il in range(n_levels) if il % ev_l == 0) * sum(1 for ip in range(len(ep.spans)) if ip % ev_s == 0)
    ties = sum(1 for t in model.wall_ties if t.edge_index == ep.edge_index)
    post_pos = len(ep.spans) * rows + corner
    # 範囲を指定して外した部材（1d.gdl の editList と同じ）
    from .member_edits import drawn_deltas

    dd = drawn_deltas(model, ep, getattr(model, "member_edits", None), stair_plan, openings)
    nuno -= dd["qtyNuno"]
    deck -= dd["qtyDeck"]
    toe -= dd["qtyToe"]
    advq -= dd["qtyAdv"]
    return {
        "qtyPostPos": post_pos, "qtyPost": post_pos * len(e.posts), "qtyNuno": nuno, "qtyDeck": deck,
        "qtyToe": toe, "qtyAdv": advq, "qtyTie": ties, "qtyBrace": brace, "qtyStair": len(all_towers) * n_levels,
    }
