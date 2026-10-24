"""法規チェック.

仕様5の自動判定リスト10項目に、建地間隔（#11）と昇降設備（#12）を加えた12項目。
判定は OK / WARN / NG の3値。根拠条文を basis に必ず持つ。
"""

from __future__ import annotations

from dataclasses import dataclass

from .elevation_solver import JACK_MAX_EXTENSION
from .master import SeriesLockError
from .model import GUARD_RAIL_ADVANCE, ScaffoldModel
from .model import ASAGAO_KIND_SAFE_WING

OK = "OK"
WARN = "WARN"
NG = "NG"


@dataclass
class CheckResult:
    check_id: int
    name: str
    status: str
    message: str
    basis: str


def run_all_checks(
    model: ScaffoldModel, stair_plan=None, terrain=None
) -> list[CheckResult]:
    """法規チェック12項目.

    stair_plan / terrain を渡すと、その結果を使って判定する:
    - 昇降設備(#12)は階段の配置が無いと判定できない
    - ジャッキ(#6)は敷地高低差で支柱ごとに繰出し量が違う。平坦時の値だけ
      見ていると、実際には上限超過の支柱があるのにOKと出る
    """
    checks = [
        check_full_scaffold_principle,
        check_working_deck,
        check_guard_rail,
        check_negarami,
        check_wall_ties,
        check_series_lock,
        check_post_spacing,
    ]
    results = [fn(model) for fn in checks]
    results.append(check_asagao(model, terrain))
    # 高さ(#8)は敷地の低い側で実高さが伸びる。名目高さだけ見ると、崖地で
    # 36mになっている足場を「16m ≦ 31m」で通してしまう
    results.append(check_first_ledger(model, terrain))
    results.append(check_height_reinforcement(model, terrain))
    results.append(check_jack_extension(model, terrain))
    results.append(check_stairs(model, stair_plan))
    return sorted(results, key=lambda r: r.check_id)


def asagao_height_mm(height_mm: float, master) -> float:
    """朝顔の段数を決める高さ。単管は手すりの上に建地を 100 出すが、そこは作業する高さではないので除く.

    除かないと同じ建物で単管抱き足場の面だけ 10.03m になって朝顔が付いた（ほかの面は 9.93m で付かない）。
    """
    from .elevation_solver import TUBE_POST_ABOVE_RAIL_MM

    return float(height_mm) - (TUBE_POST_ABOVE_RAIL_MM if master is not None and master.is_tube else 0.0)


def required_asagao_stages(height_mm: float) -> int:
    """必要な朝顔の段数: 10m以上で1段、20m以上で2段."""
    if height_mm >= 20000:
        return 2
    if height_mm >= 10000:
        return 1
    return 0


def summary(results: list[CheckResult]) -> dict:
    return {
        "total": len(results),
        "ok": sum(1 for r in results if r.status == OK),
        "warn": sum(1 for r in results if r.status == WARN),
        "ng": sum(1 for r in results if r.status == NG),
    }


# ---- #1 本足場原則 -------------------------------------------------------

def check_full_scaffold_principle(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則561条の2（2024/4施行）"
    if m.clearance_space_mm >= 1000 and m.config.scaffold_form == "一側足場":
        # ただし書き: 障害物その他の場所の状況により本足場を使用することが困難なときは一側足場でよい。
        # 本足場がいちばん細くても（離れ 250＋床を載せられる最小の建地間隔＋支柱の半径）収まらない空きなら困難
        rows = [p.nominal_dim for p in m.master.by_category("布材") if p.nominal_dim >= 500]
        full_need = 250.0 + float(min(rows) if rows else 600) + 25.0
        if full_need > m.clearance_space_mm + 1e-6:
            return CheckResult(
                1, "本足場原則", WARN,
                f"躯体外面から水平{m.clearance_space_mm:.0f}mm≧1mですが、本足場はいちばん細くても{full_need:.0f}mm"
                "（離れ250＋建地間隔＋支柱）要り収まらないため、一側足場としています（本足場の使用が困難な場合の"
                "ただし書き）。敷地境界・隣地との取り合いを記録に残してください", basis + "（ただし書き）",
            )
        return CheckResult(
            1, "本足場原則", NG,
            f"躯体外面から水平{m.clearance_space_mm:.0f}mm≧1mのスペースがあるため"
            "一側足場は使用できません。本足場としてください", basis,
        )
    # 確保できるスペースに足場が物理的に収まるか。入力は受け取っていたのに
    # 一側足場かどうかの判定にしか使っておらず、収まらない計画も素通りしていた
    if m.master.is_frame and m.config.scaffold_form == "一側足場":
        # 建枠そのものが内外2列を成す。一側で組める製品ではない
        return CheckResult(
            1, "本足場原則", NG,
            "枠組足場は建枠が内外2列を成すため一側足場にはできません。"
            "本足場とするか、くさび緊結式（一側可）で計画してください",
            basis + "／枠組足場の構造",
        )
    # 一側足場も建地1列＋躯体側へ張り出す床（ブラケット長＝建地列間隔）で幅を取る。
    # 離れだけで見ると床と建地の幅が抜けて、収まらない計画を通していた
    single = m.config.scaffold_form == "一側足場"
    # 単管抱き足場は離れが建地の芯まで。幅は外側の布（直交クランプで建地の脇）の外まで 100
    width = 100 if m.config.is_hug else m.post_row_spacing_mm
    need = max((e.standoff for e in m.plan.edges), default=0.0) + width
    if m.clearance_space_mm and need > m.clearance_space_mm + 1e-6:
        return CheckResult(
            1, "本足場原則", NG,
            f"確保できるスペース{m.clearance_space_mm:.0f}mmに対し、"
            f"{m.config.form_label}の必要幅{need:.0f}mm"
            f"（離れ{max(e.standoff for e in m.plan.edges):.0f}＋"
            + ("抱き足場の床の外側" if m.config.is_hug else "床受けブラケット長" if single else "建地間隔")
            + f"{width:.0f}）が収まりません。離れの見直し、または足場形式の変更が要ります",
            basis + "／敷地条件",
        )
    return CheckResult(1, "本足場原則", OK, f"足場形式: {m.config.form_label}", basis)


# ---- #2 作業床 -----------------------------------------------------------

def check_working_deck(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則563条"
    problems = []
    width = sum(m.deck_widths_in_use)
    if m.config.is_hug:
        # 一側足場は安衛則563条（作業床）の適用外だが、単管2本の床は墜落の危険が大きい
        return CheckResult(
            2, "作業床", WARN,
            "単管抱き足場の床は建地を両側から抱き合わせた単管2本です（布板なし）。一側足場は563条の作業床の規定の"
            "適用外ですが、高さ2m以上で作業するならブラケット足場・本足場や安全帯の使用を検討してください（墜落防止）",
            basis + "（一側足場は適用外）")
    narrow_note = ""
    if width < 400 and m.config.scaffold_form == "一側足場":
        # 一側足場は563条1項の作業床の規定（幅40cm以上）の適用外。単管のブラケット足場は足場板1列（利用者の指定
        # 2026-10-22）、くさびのブラケット足場はハーフアンチ1枚で狭いところに使う足場（利用者の指定 2026-10-24）。
        # 幅だけを外す（床材の隙間・作業床の間隔は見る）
        board = "足場板1列" if m.master.is_tube else "ハーフアンチ1枚"
        wider = "足場板2列" if m.master.is_tube else "本足場か、幅の広い床"
        narrow_note = (f"ブラケット足場の床は{board}（幅{width}mm）です。一側足場は563条の作業床の規定（幅40cm以上）の"
                       f"適用外ですが、高さ2m以上で作業するなら幅40cm以上（{wider}）や安全帯の使用を検討してください（墜落防止）")
    elif width < 400:
        problems.append(f"作業床幅{width}mm < 400mm")
    if m.config.deck_gap_mm > 30:
        problems.append(f"床材隙間{m.config.deck_gap_mm}mm > 30mm")
    if m.config.deck_to_post_gap_mm >= 120:
        problems.append(f"床材と建地の隙間{m.config.deck_to_post_gap_mm}mm ≧ 120mm")
    # 作業床の垂直間隔は2m以下（くさび緊結式足場の基準）
    levels = m.elevation.level_heights
    if len(levels) >= 2:
        v_pitch = max(b - a for a, b in zip(levels, levels[1:]))
        if v_pitch > 2000:
            problems.append(f"作業床の垂直間隔{v_pitch}mm > 2000mm")
    if problems:
        return CheckResult(2, "作業床", NG, "、".join(problems + ([narrow_note] if narrow_note else [])), basis)
    if narrow_note:
        return CheckResult(2, "作業床", WARN, narrow_note, basis + "（一側足場は適用外）")
    return CheckResult(
        2, "作業床", OK,
        f"幅{width}mm・床材隙間{m.config.deck_gap_mm}mm・建地との隙間{m.config.deck_to_post_gap_mm}mm",
        basis,
    )


# ---- #3 手すり -----------------------------------------------------------

def check_guard_rail(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則563条"
    h = m.guard_rail_height_mm
    if h < 850:
        return CheckResult(3, "手すり", NG, f"手すり高さ{h}mm < 850mm", basis)
    # 先行手摺は手すりと斜材が一体で、中桟の機能を兼ねる
    advance = m.config.guard_rail_type == GUARD_RAIL_ADVANCE
    if not advance and not m.config.has_midrail:
        return CheckResult(3, "手すり", NG, f"手すり高さ{h}mmだが中桟がありません", basis)
    problems = []
    mh = m.midrail_height_mm
    if not advance and not (350 <= mh <= 500):
        problems.append(f"中桟高さ{mh}mm が35〜50cmの範囲外")
    if m.config.has_toe_board and m.config.toe_board_height_mm < 100:
        problems.append(
            f"幅木高さ{m.config.toe_board_height_mm}mm < 100mm（落下物防止）"
        )
    if problems:
        return CheckResult(3, "手すり", NG, "、".join(problems), basis)
    detail = f"手すり高さ{h}mm＋" + ("先行手摺（手すり＋X斜材が一体、中桟を兼ねる）" if advance
                                    else f"中桟{mh}mm")
    if m.config.has_toe_board:
        detail += f"＋幅木{m.config.toe_board_height_mm}mm"
    elif advance:
        detail += "＋幅木なし（先行手すり方式。落下物防止はメッシュシート・防網等で〈563条1項六号〉）"
    else:
        detail += "＋幅木なし（落下物防止はメッシュシート・防網等で〈563条1項六号〉）"
    return CheckResult(3, "手すり", OK, detail, basis)


# ---- #4 第一の布 ---------------------------------------------------------

def check_first_ledger(m: ScaffoldModel, terrain=None) -> CheckResult:
    # 「地上第一の布は2m以下」は単管足場（安衛則571条1項四号）の規定。
    # くさびは単管に準じる。枠組は建枠脚部（根がらみ）が最下の横架材なので、
    # 同条ではなく建枠脚部が低いことの確認として扱う
    h = m.elevation.first_ledger_height
    # 敷地に高低差があると、下げた脚では基準の根がらみが地盤から離れる。
    # 継ぎ足し部の根がらみを含めた「その脚の地盤からの高さ」で最も高い脚を見る
    from .terrain import first_ledger_heights

    heights = first_ledger_heights(m, terrain)
    site_note = ""
    if heights:
        h = int(round(max(heights)))
        over = [x for x in heights if x > 2000]
        if over:
            site_note = (
                f"（敷地の低い側{len(over)}本。継ぎ足し部の根がらみを入れても、"
                "1スパン内の段差が大きく2mを超えます。段差位置での床均しか支柱位置の追加を検討）"
            )
        elif max(heights) > m.elevation.first_ledger_height + 1:
            site_note = "（敷地の低い側の脚。継ぎ足し部の根がらみを含む）"
    if m.master.is_frame:
        name = "建枠脚部（第一の布）"
        basis = "安衛則570条・仮設工業会技術基準（建枠脚部・根がらみをできる限り低く）"
    else:
        name = "第一の布"
        basis = "安衛則571条1項四号（単管足場に準じる: 地上第一の布は2m以下）"
    if h > 2000:
        return CheckResult(4, "第一の布", NG, f"{name}高さ{h}mm > 2000mm{site_note}", basis)
    return CheckResult(4, "第一の布", OK, f"{name}高さ{h}mm ≦ 2000mm{site_note}", basis)


# ---- #5 根がらみ ---------------------------------------------------------

def check_negarami(m: ScaffoldModel) -> CheckResult:
    basis = "安衛則570条・仮設工業会技術基準（できる限り低く）"
    # 「コマ」はくさび式の概念。枠組の図書に書くと通じない
    where = "建枠脚部" if m.master.is_frame else "最下コマ"
    if not m.elevation.has_negarami:
        return CheckResult(5, "根がらみ", NG, f"{where}に根がらみがありません", basis)
    return CheckResult(
        5, "根がらみ", OK,
        f"{where}（高さ{m.elevation.first_ledger_height}mm）に設置", basis,
    )


# ---- #6 ジャッキ ---------------------------------------------------------

def check_jack_extension(m: ScaffoldModel, terrain=None) -> CheckResult:
    """ジャッキ繰出し量。傾斜地では支柱ごとに違うので最大の1本で見る.

    平坦時の値だけ見ていると、敷地の警告では「上限超過が16本」と出ている
    のに法規チェックはOK、という食い違いが起きる。
    """
    basis = f"実務基準（繰り出し{JACK_MAX_EXTENSION}mm以下）"
    j = m.elevation.jack_extension
    over = []
    if terrain is not None and getattr(terrain, "feet", None):
        over = [f for f in terrain.all_feet if f.jack_mm > JACK_MAX_EXTENSION]
        j = max(j, max((f.jack_mm for f in terrain.all_feet), default=0))
    if over:
        # 地形ソルバは「なぜ超えるのか・どれだけ床均しすれば収まるのか」まで
        # 出している。同じ事象を別文面で二度言わず、その本文をそのまま使う
        vm = m.master.vertical_member_name
        msg = getattr(terrain, "over_jack_warning", "") or (
            f"敷地高低差により繰り出しが{JACK_MAX_EXTENSION}mmを超える{vm}が"
            f"{len(over)}本あります（最大{j:.0f}mm）。"
            f"該当{vm}は敷板調整または部分的な床均しで対応してください"
        )
        return CheckResult(6, "ジャッキ", WARN, msg, basis)
    if j > JACK_MAX_EXTENSION:
        return CheckResult(
            6, "ジャッキ", WARN, f"繰り出し{j:.0f}mm > {JACK_MAX_EXTENSION}mm", basis
        )
    # 上限超えの脚を敷板で持ち上げて収めた場合は、その旨を判定に残す（黙ってOKにしない）
    if terrain is not None and any(
        getattr(f, "base_plate_adjust_mm", 0) > 1e-6 and any("敷板" in w for w in f.warnings)
        for f in getattr(terrain, "feet", []) or []
    ):
        return CheckResult(6, "ジャッキ", OK, getattr(terrain, "over_jack_warning", "") or
                           f"上限超えの脚は敷板で持ち上げて繰り出し{j:.0f}mm ≦ {JACK_MAX_EXTENSION}mm", basis)
    return CheckResult(
        6, "ジャッキ", OK, f"繰り出し{j:.0f}mm ≦ {JACK_MAX_EXTENSION}mm", basis
    )


# ---- #12 昇降設備 --------------------------------------------------------

def check_stairs(m: ScaffoldModel, stair_plan=None) -> CheckResult:
    """昇降設備の有無と、昇降設備までの水平移動距離.

    ツールは階段を自動配置しているのに、法規チェックの一覧には入って
    いなかった。設置届の法規チェック表に昇降設備の行が無いのはまずい。
    """
    from .stairs import (
        DEFAULT_MAX_TRAVEL_MM,
        MIN_HEIGHT_FOR_STAIRS_MM,
        validate_stairs,
    )

    basis = "安衛則526条（高さ1.5m超は昇降設備）／実務指針（水平移動30m以内）"
    h = m.scaffold_height_mm
    if h <= MIN_HEIGHT_FOR_STAIRS_MM:
        return CheckResult(
            12, "昇降設備", OK,
            f"足場高さ{h}mm ≦ {MIN_HEIGHT_FOR_STAIRS_MM}mm のため昇降設備は不要",
            basis,
        )
    if stair_plan is None:
        return CheckResult(
            12, "昇降設備", WARN,
            f"足場高さ{h / 1000:.1f}mには昇降設備が必要ですが、"
            "階段の配置が未指定のため判定できません",
            basis,
        )
    elsewhere = list(getattr(m, "stairs_elsewhere", None) or [])
    if not stair_plan.towers and elsewhere:
        # 面ごとに足場を切り替えた建物（面の組）で、この組には階段が無いが、ほかの組の面に階段がある
        return CheckResult(
            12, "昇降設備", OK,
            f"この面の組には階段がありません。昇降は {'・'.join(elsewhere)} の階段を使います（足場はつながっている）",
            basis,
        )
    hatches = list(getattr(m, "hatch_ladders", None) or [])
    if not stair_plan.towers and hatches:
        return CheckResult(
            12, "昇降設備", OK,
            f"ハッチ付布板（梯子内蔵）の昇降口{len(hatches)}箇所（各層。水平移動30m以内に配置）",
            basis,
        )
    if not stair_plan.towers and m.config.ladders > 0:
        return CheckResult(
            12, "昇降設備", OK,
            f"はしご等の昇降設備{m.config.ladders}箇所（入力 ladders。部材は別途手配。水平移動30m以内に配置）",
            basis,
        )
    issues = validate_stairs(m, stair_plan)
    if issues:
        return CheckResult(12, "昇降設備", NG, "、".join(issues), basis)
    return CheckResult(
        12, "昇降設備", OK,
        f"階段{stair_plan.count}箇所（最大水平移動"
        f"{stair_plan.max_travel_mm / 1000:.1f}m ≦ "
        f"{DEFAULT_MAX_TRAVEL_MM / 1000:.0f}m）"
        "／2層ごとに外の作業床へ出る（作業床が踊り場を兼ねる）",
        basis,
    )


# ---- #7 壁つなぎ ---------------------------------------------------------

def check_wall_ties(m: ScaffoldModel) -> CheckResult:
    v_lim, h_lim, basis = m.wall_tie_limits()
    if not m.wall_ties:
        return CheckResult(7, "壁つなぎ", NG, "壁つなぎが配置されていません", basis)
    v_max, h_max = m.wall_tie_max_spacing()
    problems = []
    if v_max > v_lim:
        problems.append(f"垂直間隔{v_max:.0f}mm > {v_lim:.0f}mm")
    if h_max > h_lim:
        problems.append(f"水平間隔{h_max:.0f}mm > {h_lim:.0f}mm")
    if problems:
        return CheckResult(7, "壁つなぎ", NG, "、".join(problems), basis)
    # 渡した区間の深い所（壁つなぎが届かない帯）は別途の控えで拘束する前提で間隔から
    # 除いている。黙って通さず、帯と前提を書く
    from .ties import unreachable_bands

    bands = unreachable_bands(m)
    if bands:
        _v_raw, h_raw = m.wall_tie_max_spacing(exclude_unreachable=False)
        detail = "、".join(
            f"{m.face_name(e)} {a:.0f}〜{b:.0f}mm" for e, bs in sorted(bands.items()) for a, b in bs
        )
        return CheckResult(
            7, "壁つなぎ", WARN,
            f"最大 垂直{v_max:.0f}mm×水平{h_max:.0f}mm（{len(m.wall_ties)}箇所）"
            f"／壁つなぎが届かない帯: {detail}。帯は単管等の別途の控えで躯体に固定する前提で"
            f"間隔から除いています（帯を含めた水平間隔は{h_raw:.0f}mm）",
            basis,
        )
    # 間隔が法規内でも、壁つなぎが1本も入らない面は別に挙げる。
    # 間隔の最大値だけ見ていると、その面の存在が結果に出てこない
    untied = m.edges_without_wall_ties()
    if untied:
        lengths = {
            e.edge_index: e.scaffold_length for e in m.plan.edges
        }
        detail = "、".join(
            f"{m.face_name(i)} {lengths.get(i, 0):.0f}mm" for i in untied
        )
        return CheckResult(
            7, "壁つなぎ", WARN,
            f"最大 垂直{v_max:.0f}mm×水平{h_max:.0f}mm（{len(m.wall_ties)}箇所）"
            f"／壁つなぎが入らない面: {detail}。"
            "両隣の面にコーナー経由で支持される前提です。単管等での別途拘束を検討してください",
            basis,
        )
    return CheckResult(
        7, "壁つなぎ", OK,
        f"最大 垂直{v_max:.0f}mm×水平{h_max:.0f}mm（{len(m.wall_ties)}箇所）", basis,
    )


# ---- #8 高さ31m超の補強 --------------------------------------------------

def actual_max_height_mm(m: ScaffoldModel, terrain=None) -> tuple[float, float]:
    """判定に使う足場高さと、敷地の低い側で伸びた分（terrain.actual_max_height_mm）."""
    from .terrain import actual_max_height_mm as _actual

    return _actual(m, terrain)


def check_height_reinforcement(m: ScaffoldModel, terrain=None) -> CheckResult:
    h, extra = actual_max_height_mm(m, terrain)
    site_note = (
        f"（敷地の低い側の実高さ。名目{m.scaffold_height_mm / 1000:.2f}m＋脚の伸び{extra / 1000:.2f}m"
        "＝継ぎ足しとジャッキ繰出しの差）"
        if extra > 1 else ""
    )
    # 枠組足場は「建地2本組」（単管足場＝安衛則571条の概念）ではなく、
    # 仮設工業会の枠組指針で最下段建枠・ジャッキベースの強度を検討する。
    # くさび式は単管足場に準じて31m超の2本組で保守的に警告する。
    if m.master.is_frame:
        basis = "仮設工業会 足場・型枠支保工設計指針（枠組足場・高さ45m超／最下段の強度検討）"
        if h > 45000:
            return CheckResult(
                8, "高さ", NG,
                f"足場高さ{h / 1000:.2f}m{site_note} > 45m: 本ツールの適用範囲外です（個別設計が必要）",
                basis,
            )
        if h > 31000:
            return CheckResult(
                8, "高さ", WARN,
                f"足場高さ{h / 1000:.2f}m{site_note}（枠組）: 高さが大きいので最下段の建枠・"
                "ジャッキベースが自重＋積載に対して許容支持力以内か強度検討してください"
                "（枠組は単管足場の建地2本組の対象外）",
                basis,
            )
        return CheckResult(8, "高さ", OK,
                           f"足場高さ{h / 1000:.2f}m{site_note} ≦ 45m（枠組）", basis)

    basis = "安衛則571条（単管足場: 高さ31m超は建地2本組等の補強）"
    if h > 45000:
        return CheckResult(
            8, "高さ", NG,
            f"足場高さ{h / 1000:.2f}m{site_note} > 45m: 本ツールの適用範囲外です（個別設計が必要）", basis,
        )
    if h > 31000:
        # どこからどこまでを2本組にするのかまで言わないと手が打てない
        return CheckResult(
            8, "高さ", WARN,
            f"足場高さ{h / 1000:.2f}m{site_note} > 31m: 最高部から31mを超える部分"
            f"（GL〜{(h - 31000) / 1000:.2f}m）の建地は2本組が必要です。"
            "建地下端の設計荷重が最大使用荷重以内と確認できる場合は除外できます",
            basis,
        )
    return CheckResult(8, "高さ", OK, f"足場高さ{h / 1000:.2f}m{site_note} ≦ 31m", basis)


# ---- #9 規格混在 ---------------------------------------------------------

def check_series_lock(m: ScaffoldModel) -> CheckResult:
    basis = "本ツール運用規則（系列ロック。インチ/センチ混在は組めない）"
    # 系列の集合を見る分岐も持っていたが、assert_series が全部材を見るので
    # 同じ条件しか捕まえない。1本にして、混在した部材の型番まで挙げる方を残す
    try:
        for p in m.master.parts:
            m.master.assert_series(p)
    except SeriesLockError as exc:
        return CheckResult(9, "規格混在", NG, str(exc), basis)
    return CheckResult(9, "規格混在", OK, f"全部材が {m.master.series_id} に統一", basis)


# ---- #10 朝顔（防護棚） --------------------------------------------------

def check_asagao(m: ScaffoldModel, terrain=None) -> CheckResult:
    basis = (
        "安衛則563条・537条（落下物防護）: 高さ10m以上で1段・20m以上で2段、"
        "突出2m以上・傾斜20度以上、取付部は2スパン毎に壁つなぎ"
    )
    # 落下物防護は地盤からの高さで決まる。敷地の低い側では継ぎ足した分だけ
    # 高くなるので、名目ではなく実高さで段数を決める
    h_mm, extra = actual_max_height_mm(m, terrain)
    h_mm = asagao_height_mm(h_mm, m.master)
    need = required_asagao_stages(h_mm)
    spec = m.config.asagao
    if m.master.is_tube:
        basis += "／高さは手すりまで（単管の手すりの上の建地の出100は除く）"
    h_m = h_mm / 1000.0
    if extra > 1:
        basis += f"／敷地の低い側の実高さ{h_m:.2f}m（名目{m.scaffold_height_mm / 1000:.2f}m）で判定"

    if need == 0:
        if spec is None or spec.stages == 0:
            return CheckResult(
                10, "朝顔", OK, f"足場高さ{h_m:.2f}m < 10m のため朝顔は不要", basis
            )
        if spec.kind == ASAGAO_KIND_SAFE_WING:
            return CheckResult(
                10, "朝顔", OK,
                f"足場高さ{h_m:.2f}m < 10m。簡易落下物防止機材セーフウイング{spec.stages}段"
                f"（張出{spec.projection_mm:.0f}mm・{spec.angle_deg:.0f}度）を設置",
                basis,
            )
        return CheckResult(
            10, "朝顔", OK,
            f"足場高さ{h_m:.2f}m（不要だが{spec.stages}段を設置）", basis,
        )

    # セーフウイングは張出1,280mmの簡易落下物防止機材で、防護棚（突出2m以上）の
    # 要件を満たさない。「突出が足りない」ではなく、朝顔が別途要ると明言する
    if spec is not None and spec.stages > 0 and spec.kind == ASAGAO_KIND_SAFE_WING:
        return CheckResult(
            10, "朝顔", NG,
            f"セーフウイング{spec.stages}段（張出{spec.projection_mm:.0f}mm）は簡易落下物"
            f"防止機材で、突出2m以上の朝顔（防護棚）の要件を満たしません。"
            f"足場高さ{h_m:.2f}m には朝顔{need}段が別途必要です",
            basis,
        )

    if spec is None or spec.stages == 0:
        return CheckResult(
            10, "朝顔", NG,
            f"足場高さ{h_m:.2f}m には朝顔{need}段が必要ですが設置されていません",
            basis,
        )

    problems = []
    if spec.stages < need:
        problems.append(f"段数{spec.stages} < 必要{need}段")
    if spec.projection_mm < 2000:
        problems.append(f"突出{spec.projection_mm:.0f}mm < 2000mm")
    if spec.angle_deg < 20:
        problems.append(f"傾斜{spec.angle_deg:.0f}度 < 20度")
    if spec.tie_every_spans > 2:
        problems.append(f"取付部の壁つなぎが{spec.tie_every_spans}スパン毎 > 2スパン毎")
    if problems:
        return CheckResult(10, "朝顔", NG, "、".join(problems), basis)
    # 付ける面を選んだ計画（利用者の指定 2026-10-24: 朝顔あとで必要箇所を選べるようにしたい）。付けない面は、
    # 道路・隣地・人の通る側でない（落下物が及ばない）ことを確かめる
    off = [n for e, n in zip(m.plan.edges, m.plan.face_names()) if not m.asagao_on(e.edge_index)]
    if off:
        on = [n for e, n in zip(m.plan.edges, m.plan.face_names()) if m.asagao_on(e.edge_index)]
        return CheckResult(
            10, "朝顔", WARN,
            f"{spec.stages}段（必要{need}段）を{'・'.join(on) or 'どの面にも'}に設置。{'・'.join(off)}には付けていません"
            "（道路・隣地・人の通る側でないこと、落下物の及ぶ範囲を立入禁止にすることを確認）",
            basis,
        )
    return CheckResult(
        10, "朝顔", OK,
        f"{spec.stages}段（必要{need}段）・突出{spec.projection_mm:.0f}mm・"
        f"傾斜{spec.angle_deg:.0f}度・取付部{spec.tie_every_spans}スパン毎に壁つなぎ",
        basis,
    )


# ---- #11 建地間隔 --------------------------------------------------------

# くさび緊結式足場の建地間隔（安衛則571条 わく組足場以外の支柱式足場に準じる）
MAX_SPAN_ALONG_MM = 1850    # 桁行方向（スパン方向）
MAX_SPAN_ACROSS_MM = 1500   # 梁間方向（内外建地間隔）


MAX_FRAME_HEIGHT_MM = 2000   # わく組足場の主わく高さ（571条1項一号）


def check_post_spacing(m: ScaffoldModel) -> CheckResult:
    """建地（枠組は主わく）の間隔.

    571条は足場の種類で条文が違う:
      一号 わく組足場: 主わく高さ2m以下・主わく間隔1.85m以下
      二号 それ以外の支柱式: 桁行1.85m以下・梁間1.5m以下

    梁間1.5mの制限はわく組には無い（建枠の幅で決まる）ので当てない。
    スパン割は真物の呼び寸法から決まるので通常は満たすが、
    系列やマスタを差し替えたときに黙って超えないよう検査する。
    """
    spans = [s for ep in m.plan.edges for s in ep.spans]
    longest = max(spans) if spans else 0
    problems = []

    if m.master.is_frame:
        basis = "安衛則571条1項一号（わく組足場: 主わく高さ2m以下・主わく間隔1.85m以下）"
        if longest > MAX_SPAN_ALONG_MM:
            problems.append(f"主わくの間隔{longest}mm > {MAX_SPAN_ALONG_MM}mm")
        frame_h = max(m.elevation.posts) if m.elevation.posts else 0
        if frame_h > MAX_FRAME_HEIGHT_MM:
            problems.append(f"主わくの高さ{frame_h}mm > {MAX_FRAME_HEIGHT_MM}mm")
        if problems:
            return CheckResult(11, "建地間隔", NG, "、".join(problems), basis)
        return CheckResult(
            11, "建地間隔", OK, f"主わく間隔{longest}mm・主わく高さ{frame_h}mm", basis
        )

    basis = "安衛則571条1項二号（支柱式足場の建地間隔: 桁行方向1.85m以下・梁間方向1.5m以下）"
    if longest > MAX_SPAN_ALONG_MM:
        problems.append(f"桁行方向の建地間隔{longest}mm > {MAX_SPAN_ALONG_MM}mm")
    # 梁間方向の建地間隔は建地列の芯々。作業床の被覆幅ではない
    across = m.post_row_spacing_mm
    if m.config.scaffold_form != "一側足場" and across > MAX_SPAN_ACROSS_MM:
        problems.append(f"梁間方向の建地間隔{across}mm > {MAX_SPAN_ACROSS_MM}mm")
    if problems:
        return CheckResult(11, "建地間隔", NG, "、".join(problems), basis)
    detail = f"桁行{longest}mm"
    if m.config.scaffold_form != "一側足場":
        detail += f"・梁間{across}mm"
    return CheckResult(11, "建地間隔", OK, detail, basis)
