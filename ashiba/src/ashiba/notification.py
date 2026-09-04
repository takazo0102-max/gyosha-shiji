"""設置届一式（様式第20号 下書き＋構造計算書＋数量表）のExcel出力.

届出要件（安衛法88条）: 高さ10m以上かつ設置期間60日以上 →
工事開始30日前までに所轄労働基準監督署へ。
添付図書: 案内図・工程表・平面図・立面図・詳細図・部材等明細書・構造計算書。

様式第20号は「計画の概要（種類・長さ・高さ・期間）」を自動記入し、
事業場情報・参画者など人が書く欄は空欄＋【記入】マーカーで残す。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .law_check import WARN, CheckResult
from .model import ScaffoldModel
from .quantity import QuantityResult
from .structural import StructuralResult
from .xlsx_writer import (
    STYLE_BOLD,
    STYLE_BORDER,
    STYLE_HEADER,
    Cell,
    Workbook,
)

FILL_IN = "【記入】"

DISCLAIMER = (
    "本書は計画作成参画者（有資格者）が確認・修正する前提の下書きです。"
    "部材形状はカタログ寸法からの再現であり、耐力値は data/capacity.csv の設定値です。"
    "提出前に必ず有資格者の確認を受けてください。"
)

ATTACHMENTS = [
    ("案内図", "別途作成", "現場位置がわかる地図"),
    ("工程表", "別途作成", "足場の組立・解体時期を含む工程"),
    ("平面図", "本ツール出力", "足場ライン配置＋スパン・離れ寸法"),
    ("立面図", "本ツール出力", "支柱構成・作業層・壁つなぎ位置"),
    ("詳細図", "本ツール出力", "脚部・壁つなぎ部・コーナー部ほか"),
    ("部材等明細書", "本ツール出力", "数量表シート（型番・数量・重量）"),
    ("構造計算書", "本ツール出力", "風荷重・壁つなぎ・建地圧縮シート"),
]


@dataclass
class NotificationInfo:
    """様式第20号の人が書く欄（分かる範囲で事前入力できる）."""

    business_type: str = ""          # 事業の種類
    site_name: str = ""              # 事業場の名称
    site_address: str = ""           # 設置地
    worker_count: str = ""           # 常時使用する労働者数
    planner_name: str = ""           # 計画作成参画者 氏名
    planner_career: str = ""         # 参画者の経歴
    start_date: Optional[_dt.date] = None   # 工事着手予定年月日
    contractor: str = ""             # 注文者／元方事業者
    labor_office: str = ""           # 所轄労働基準監督署

    def submission_deadline(self) -> Optional[_dt.date]:
        """提出期限＝工事開始30日前."""
        if self.start_date is None:
            return None
        return self.start_date - _dt.timedelta(days=30)


def notification_required(model: ScaffoldModel, terrain=None) -> bool:
    """設置届の要否（高さ10m以上かつ60日以上、安衛法88条）.

    高さは敷地の低い側の実高さで見る（名目9mでも2mの段差があれば11m）。
    """
    from .terrain import actual_max_height_mm

    return actual_max_height_mm(model, terrain)[0] >= 10000 and model.config.period_days >= 60


def scaffold_total_length_m(model: ScaffoldModel) -> float:
    """足場の設置延長（足場中心線ループの全長）."""
    return sum(ep.scaffold_length for ep in model.plan.edges) / 1000.0


def write_notification_xlsx(
    model: ScaffoldModel,
    quantity: QuantityResult,
    checks: list[CheckResult],
    structural: StructuralResult,
    path: Path,
    project_name: str = "",
    info: Optional[NotificationInfo] = None,
    details: Optional[list] = None,
    terrain=None,
    verdict=None,
    warnings=None,
    stair_plan=None,
    platforms=None,
    openings=None,
    bracket_sections=None,
) -> None:
    info = info or NotificationInfo()
    if details is None:
        from .details import required_details
        details = required_details(model)
    wb = Workbook()
    _sheet_form20(wb, model, quantity, project_name, info,
                  stair_plan=stair_plan, platforms=platforms,
                  openings=openings, bracket_sections=bracket_sections, terrain=terrain)
    # 確認する人が最初に見る位置に、是正項目と要確認事項をまとめて置く
    if verdict is not None:
        _sheet_todo(wb, verdict, checks, warnings)
    _sheet_conditions(wb, model, structural, project_name)
    _sheet_wind(wb, structural)
    _sheet_wall_tie(wb, structural, model)
    _sheet_post(wb, structural)
    _sheet_quantity(wb, quantity)
    _sheet_law_check(wb, checks)
    if terrain is not None and terrain.feet:
        _sheet_jack_table(wb, terrain, checks)
    _sheet_attachments(wb, info, details, model)
    wb.save(path)


def _sheet_jack_table(wb, terrain, checks=None) -> None:
    """支柱ごとのジャッキ量一覧（敷地高低差対応）."""
    from .terrain import jack_table_rows

    s = wb.sheet("ジャッキ量一覧")
    for c, wdt in enumerate([6, 12, 12, 14, 12, 18, 14, 30, 46]):
        s.set_width(c, wdt)
    vm = getattr(terrain, "vertical_member_name", "支柱")
    s.add_title(f"{vm}ごとのジャッキ量一覧（敷地高低差対応）", span=9)
    s.add_cells([Cell(f"作業床レベルは全周で通し、GL高低差は各{vm}のジャッキと{vm}長で吸収する")])
    s.add_blank()
    rows = jack_table_rows(terrain)
    s.add_header(rows[0])
    for row in rows[1:]:
        s.add_cells([Cell(v, STYLE_BORDER) for v in row])
    s.add_blank()
    s.add(["基準GL(mm)", round(terrain.reference_gl_mm, 1)], STYLE_BOLD)
    s.add(["高低差(mm)", round(terrain.gl_difference_mm, 1)], STYLE_BOLD)
    s.add(["ジャッキ繰出し範囲(mm)",
           round(terrain.jack_min_mm, 1), round(terrain.jack_max_mm, 1)], STYLE_BOLD)
    # 法規チェックシートに同じ文が出ているものは、ここでは見出しだけにする
    # （このシートは支柱ごとの数値が主役で、同じ長文を2枚に並べる必要はない）
    said = {c.message for c in (checks or []) if c.status == WARN}
    for note in terrain.warnings:
        if note in said:
            s.add_cells([
                Cell("注記"),
                Cell(note.split("。")[0] + "（法規チェックシートを参照）"),
            ])
        else:
            s.add_cells([Cell("注記"), Cell(note)])


# ---- 各シート -------------------------------------------------------------


def _rows(result) -> str:
    """未確認値の差し替え先（capacity.csv の行）を注記に添える."""
    rows = [r for c in getattr(result, "unverified_caps", []) for r in c.rows]
    if not rows:
        return ""
    return "（要差替: data/capacity.csv " + "・".join(dict.fromkeys(rows)) + "）"


def _kv(sheet, label: str, value, note: str = "") -> None:
    sheet.add_cells(
        [Cell(label, STYLE_BORDER), Cell(value, STYLE_BORDER), Cell(note)]
    )


def _sheet_form20(wb, model, quantity, project_name, info: NotificationInfo,
                  stair_plan=None, platforms=None, openings=None,
                  bracket_sections=None, terrain=None) -> None:
    s = wb.sheet("様式第20号(下書き)")
    s.set_width(0, 26)
    s.set_width(1, 34)
    s.set_width(2, 46)
    s.add_title("機械等設置届（様式第20号） 下書き", span=3)
    s.add_cells([Cell(DISCLAIMER)])
    s.add_blank()

    required = notification_required(model, terrain)
    s.add(["届出要否", "要" if required else "不要",
           "高さ10m以上かつ設置期間60日以上で届出（安衛法88条）"], STYLE_BOLD)
    s.add_blank()

    s.add(["■ 事業場等（人が記入）"], STYLE_BOLD)
    _kv(s, "事業の種類", info.business_type or FILL_IN)
    _kv(s, "事業場の名称", info.site_name or project_name or FILL_IN)
    _kv(s, "設置地", info.site_address or FILL_IN)
    _kv(s, "常時使用する労働者数", info.worker_count or FILL_IN)
    _kv(s, "注文者／元方事業者", info.contractor or FILL_IN)
    _kv(s, "所轄労働基準監督署", info.labor_office or FILL_IN)
    s.add_blank()

    s.add(["■ 計画の概要（本ツールが自動記入）"], STYLE_BOLD)
    _kv(s, "設置する機械等の種類",
        f"{model.master.system_name}（{model.config.scaffold_form}）",
        f"系列 {model.master.series_id}")
    _kv(s, "足場の長さ", round(scaffold_total_length_m(model), 2),
        "m（足場中心線の全長）")
    from .terrain import actual_max_height_mm

    h_mm, extra = actual_max_height_mm(model, terrain)
    _kv(s, "足場の高さ", round(h_mm / 1000.0, 3),
        f"m（ジャッキ下端〜{model.master.vertical_member_name}天端"
        + (f"。敷地の低い側の実高さ。名目{model.scaffold_height_mm / 1000:.3f}m＋脚の伸び{extra / 1000:.3f}m"
           "（継ぎ足しとジャッキ繰出しの差）"
           if extra > 1 else "") + "）")
    _kv(s, "架け面積", quantity.kake_menseki_m2, "m²（(建物外周+4m)×(建物高さ+0.5m)）")
    _kv(s, "作業床の層数", model.elevation.n_levels, "層")
    _kv(s, f"{model.master.vertical_member_name}位置数", model.plan.total_posts,
        "箇所/層（内外2列なら×2本）")
    _kv(s, "設置期間", model.config.period_days, "日")
    # 様式の「構造の概要」欄。作業床・手すり・壁つなぎ・昇降設備・朝顔は
    # 計画で変わるのに、この下書きは種類と寸法しか書いていなかった
    widths = "＋".join(str(w) for w in model.deck_widths_in_use)
    # 法規上の作業床幅は床材の合計（隙間は床ではない）。deck_width_total は
    # 隙間込みの被覆幅なので、ここで使うと法規チェックの650と食い違う
    _kv(s, "作業床", f"幅{sum(model.deck_widths_in_use)}mm（{widths}）",
        f"{model.elevation.n_levels}層・床材隙間{model.config.deck_gap_mm}mm・幅木H157"
        + ("" if model.config.has_toe_board else "（幅木なし）"))
    _kv(s, "手すり", model.guard_rail_method,
        f"手すり{model.guard_rail_height_mm}mm＋中桟")
    v_max, h_max = model.wall_tie_max_spacing()
    v_lim, h_lim, tie_basis = model.wall_tie_limits()
    _kv(s, "壁つなぎ", f"{len(model.wall_ties)}箇所",
        f"最大 垂直{v_max:.0f}×水平{h_max:.0f}mm（法定 {v_lim:.0f}×{h_lim:.0f}以下） "
        f"{tie_basis}")
    a = model.config.asagao
    _kv(s, "朝顔（防護棚）",
        f"{a.stages}段" if a and a.stages else "なし",
        (f"突出{a.projection_mm:.0f}mm・傾斜{a.angle_deg:.0f}度"
         if a and a.stages else "高さ10m未満または設置しない指定"))
    # 付帯設備。計画に入っているのに届の下書きに出ないと、審査側は
    # 「無い」ものとして読む（図面と食い違う届になる）
    if stair_plan is not None and getattr(stair_plan, "towers", None):
        _kv(s, "昇降設備（階段）", f"{len(stair_plan.towers)}箇所",
            f"最大水平移動{stair_plan.max_travel_mm / 1000:.1f}m（安衛則526条）")
    if platforms is not None and getattr(platforms, "stages", None):
        st = platforms.stages
        _kv(s, "荷受けステージ", f"{len(st)}基",
            "・".join(f"出{x.projection_mm:.0f}mm 第{'・'.join(str(l) for l in (x.levels or [1]))}層"
                      for x in st))
    if platforms is not None and getattr(platforms, "hoists", None):
        _kv(s, "昇降機", f"{len(platforms.hoists)}基",
            "乗り込み口は開閉式手すりで防護（安衛則563条）")
    if openings is not None and getattr(openings, "openings", None):
        _kv(s, "開口部（梁枠）", f"{len(openings.openings)}箇所",
            "・".join(f"梁枠{o.beam_span_mm}mm" for o in openings.openings)
            + f"／{model.master.vertical_member_name}{openings.removed_posts}本を抜き梁枠で受ける")
    if bracket_sections:
        _kv(s, "ブラケット区間", f"{len(bracket_sections)}区間",
            "作業床の幅を局所的に変更（数量・図面に反映済み）")
    s.add_blank()

    s.add(["■ 日程"], STYLE_BOLD)
    start = info.start_date
    deadline = info.submission_deadline()
    _kv(s, "工事着手予定年月日", start.isoformat() if start else FILL_IN)
    _kv(s, "届出期限（着手30日前）",
        deadline.isoformat() if deadline else "着手日の記入で自動算出",
        "安衛法88条")
    s.add_blank()

    s.add(["■ 計画作成参画者（人が記入・必須）"], STYLE_BOLD)
    _kv(s, "氏名", info.planner_name or FILL_IN)
    _kv(s, "経歴の概要", info.planner_career or FILL_IN,
        "足場の組立て等作業主任者技能講習修了者等")
    _kv(s, "確認欄", FILL_IN, "本下書きの内容を確認した旨の署名")


def _sheet_conditions(wb, model, structural: StructuralResult, project_name) -> None:
    s = wb.sheet("計算条件")
    s.set_width(0, 26)
    s.set_width(1, 24)
    s.set_width(2, 52)
    site = structural.site
    s.add_title("構造計算 条件一覧", span=3)
    s.add_cells([Cell(DISCLAIMER)])
    s.add_blank()
    s.add_header(["項目", "値", "備考・出典"])
    _kv(s, "工事名", project_name or "—")
    koma = model.master.koma_pitch
    _kv(s, "足場種別",
        f"{model.master.system_name}・{model.config.scaffold_form}",
        f"系列 {model.master.series_id}"
        + (f"（コマピッチ{koma}mm）" if koma else "（建枠を積む方式）"))
    _kv(s, "建設地（地域区分）", site.region, structural.wind.v0_source)
    _kv(s, "基準風速 V0", structural.wind.v0_ms, "m/s")
    _kv(s, "地表面粗度区分", site.roughness, "告示1454号の区分")
    _kv(s, "養生材仕様", site.sheet_type, f"充実率 R={structural.wind.fill_ratio}")
    _kv(s, "近接建物補正 E", site.adjacent_factor, "1.0〜1.3")
    _kv(s, "地域区分係数 S", site.region_factor, "")
    _kv(s, "設置期間", site.period_days, "日")
    _kv(s, "同時載荷層数", site.simultaneous_loaded_levels, "層（実務: 2層以内）")
    s.add_blank()
    if structural.warnings:
        s.add(["■ 対応が必要"], STYLE_BOLD)
        for w in structural.warnings:
            s.add_cells([Cell(w)])
    if structural.notes:
        s.add_blank()
        s.add(["■ 参考（どの条件で検定したか）"], STYLE_BOLD)
        for n in structural.notes:
            s.add_cells([Cell(n)])


def _sheet_wind(wb, structural: StructuralResult) -> None:
    s = wb.sheet("計算書1_風荷重")
    s.set_width(0, 30)
    s.set_width(1, 18)
    s.set_width(2, 52)
    w = structural.wind
    s.add_title("設計風速・速度圧・風力係数", span=3)
    s.add_cells([Cell("仮設工業会「風荷重に対する足場の安全技術指針」準拠")])
    s.add_blank()
    s.add_header(["項目", "値", "式・根拠"])
    _kv(s, "基準風速 V0", w.v0_ms, f"m/s  {w.v0_source}")
    _kv(s, "足場高さ H", w.height_m, "m")
    _kv(s, "高さ補正係数 K", w.k_height, "告示1454号 Er に準拠した高さ補正")
    _kv(s, "近接建物補正 E", w.e_adjacent, "1.0〜1.3")
    _kv(s, "地域区分係数 S", w.s_region, "")
    _kv(s, "設計風速 V", w.v_design_ms, "m/s  V = V0 × K × E × S")
    _kv(s, "速度圧 q", w.q_n_m2, "N/m²  q = 0.6 × V²")
    s.add_blank()
    _kv(s, "基本風力係数 Co", 1.57, "指針値")
    _kv(s, "養生材充実率 R", w.fill_ratio, "メッシュ0.7／防音・密閉1.0／なし0")
    _kv(s, "γ", structural.site.gamma, "躯体側の充実率パラメータ")
    _kv(s, "補正係数 F", structural.site.correction_f, "")
    _kv(s, "風力係数 C", w.c_force,
        "C = (0.11 + 0.09γ + 0.945×Co×R) × F")


def _sheet_wall_tie(wb, structural: StructuralResult, model) -> None:
    s = wb.sheet("計算書2_壁つなぎ")
    s.set_width(0, 30)
    s.set_width(1, 18)
    s.set_width(2, 52)
    t = structural.wall_tie
    w = structural.wind
    s.add_title("壁つなぎの検定", span=3)
    s.add_blank()
    s.add_header(["項目", "値", "式・根拠"])
    v_max, h_max = model.wall_tie_max_spacing()
    # 法定上限は足場の種類で違う（570条1項五号）。決め打ちすると届出書に
    # 誤った基準値が載る
    v_lim, h_lim, tie_basis = model.wall_tie_limits()
    _kv(s, "壁つなぎ本数", len(model.wall_ties), "箇所")
    _kv(s, "実配置の最大間隔", f"垂直{v_max:.0f} × 水平{h_max:.0f}",
        f"mm（法定 垂直{v_lim:.0f}以下 × 水平{h_lim:.0f}以下） {tie_basis}")
    untied = model.edges_without_wall_ties()
    if untied:
        _kv(s, "壁つなぎが入らない面",
            "、".join(model.face_name(i) for i in untied),
            "両隣の面にコーナー経由で支持される前提。単管等での別途拘束を検討")
    _kv(s, "支配的な壁つなぎ", t.governing or "—",
        "支配面積が最大となる1本で検定する")
    _kv(s, "支配幅 lh", t.lh_m, "m（隣の壁つなぎとの中間まで。端は支点として半分）")
    _kv(s, "支配高さ lw", t.lw_m,
        "m（下端は脚部が支点なので半分、上端は自由端なので全長）")
    _kv(s, "支配面積 lh×lw", t.tributary_area_m2, "m²")
    _kv(s, "風力係数 C", w.c_force, "計算書1より")
    _kv(s, "速度圧 q", w.q_n_m2, "N/m²  計算書1より")
    _kv(s, "壁つなぎ作用力 P", t.force_kn, "kN  P = C × q × lh × lw")
    s.add_blank()
    _kv(s, "許容耐力", t.allowable_kn,
        f"kN  {t.source}" + ("" if t.verified else "  ※未確認値 " + _rows(t)))
    _kv(s, "風荷重時割増後", t.allowable_increased_kn, "kN  許容耐力 × 1.3")
    _kv(s, "検定比 P/(許容×1.3)", t.ratio, "1.0以下で可")
    s.add_cells([
        Cell("判定", STYLE_HEADER),
        Cell("OK" if t.ok else "NG", STYLE_HEADER),
        Cell("" if t.ok else "壁つなぎ間隔の短縮または高耐力品を検討", STYLE_HEADER),
    ])


def _sheet_post(wb, structural: StructuralResult) -> None:
    s = wb.sheet("計算書3_建地圧縮")
    s.set_width(0, 30)
    s.set_width(1, 18)
    s.set_width(2, 52)
    p = structural.post
    vm = getattr(p, "vertical_member_name", "支柱")
    s.add_title(f"建地（{vm}）圧縮の検定", span=3)
    s.add_blank()
    s.add_header(["項目", "値", "式・根拠"])
    # 式だけ書いて元の数を出さないと、確認する人が値を追えない
    _kv(s, "足場総重量", p.total_weight_kg, "kg  部材等明細書の合計")
    _kv(s, "建地本数", p.n_posts, f"本（{vm}位置数×列数）")
    _kv(s, "自重 建地1本あたり", p.dead_load_kn, "kN  総重量×9.80665/建地本数")
    _kv(s, "作業床許容積載", p.deck_capacity_kn, "kN/スパン  " + (p.deck_source or "capacity.csv"))
    _kv(s, "同時載荷層数", p.loaded_levels, "層（実務: 2層以内）")
    _kv(s, "積載 建地1本あたり", p.live_load_kn,
        "kN  作業床許容積載×同時載荷層数÷2")
    if p.extra_load_kn > 0:
        _kv(s, "局所荷重 建地1本あたり", p.extra_load_kn,
            "kN  荷受けステージ等（直下の建地に張出しの偏心を割増して配分）")
        _kv(s, "軸力 N", p.total_kn, "kN  N = 自重 + 積載 + 局所荷重")
    else:
        _kv(s, "軸力 N", p.total_kn, "kN  N = 自重 + 積載")
    s.add_blank()
    _kv(s, "ジャッキ繰出し量", p.jack_extension_mm,
        f"mm（敷地高低差がある場合は最も繰り出している{vm}の値。"
        "許容支持力は繰出し長で低下する）")
    _kv(s, "支配する検定", p.governing, "")
    _kv(s, "許容支持力", p.allowable_kn,
        f"kN  {p.source}" + ("" if p.verified else "  ※未確認値 " + _rows(p)))
    _kv(s, "検定比 N/許容", p.ratio, "1.0以下で可")
    s.add_cells([
        Cell("判定", STYLE_HEADER),
        Cell("OK" if p.ok else "NG", STYLE_HEADER),
        Cell("" if p.ok else (
            "許容支持力が未確認の一般値。まずメーカー認定値へ差し替えて再判定"
            if not p.verified else "繰出し量低減・支柱2本組・スパン短縮を検討"), STYLE_HEADER),
    ])


def _sheet_quantity(wb, quantity: QuantityResult) -> None:
    s = wb.sheet("部材等明細書")
    for c, wdt in enumerate([14, 12, 12, 12, 12, 10, 14, 40]):
        s.set_width(c, wdt)
    s.add_title("部材等明細書（数量表）", span=8)
    s.add_blank()
    s.add_header(["型番", "分類", "呼び寸法", "実寸法", "単位重量kg",
                  "数量", "小計重量kg", "備考"])
    for line in quantity.lines:
        pt = line.part
        s.add_cells([
            Cell(pt.model_no, STYLE_BORDER), Cell(pt.category, STYLE_BORDER),
            Cell(pt.nominal_dim, STYLE_BORDER), Cell(pt.actual_dim, STYLE_BORDER),
            Cell(pt.weight_kg, STYLE_BORDER), Cell(line.qty, STYLE_BORDER),
            Cell(round(line.subtotal_weight, 1), STYLE_BORDER),
            Cell(pt.note + ("　" + line.note if line.note else ""), STYLE_BORDER),
        ])
    s.add_blank()
    # 分類別集計（発注前の規模感）。CSVの数量表と同じ内容
    s.add(["■分類別集計", "数量計", "重量計kg"], STYLE_HEADER)
    for c, q, wt in quantity.category_totals():
        s.add_cells([Cell(c, STYLE_BORDER), Cell(q, STYLE_BORDER),
                     Cell(wt, STYLE_BORDER)])
    s.add_blank()
    s.add(["総重量kg", quantity.total_weight_kg], STYLE_BOLD)
    s.add(["トラック台数概算(4t)", quantity.truck_count], STYLE_BOLD)
    s.add(["架け面積m²", quantity.kake_menseki_m2], STYLE_BOLD)
    for n in quantity.warnings:
        s.add_cells([Cell("要手配・要検討", STYLE_BOLD), Cell(n, STYLE_BOLD)])
    for n in quantity.notes:
        if n not in quantity.warnings:
            s.add_cells([Cell("注記"), Cell(n)])


def _sheet_todo(wb, verdict, checks: list[CheckResult], warnings=None) -> None:
    """是正項目と要確認事項（着手前チェックリスト）.

    法規・構造・付帯設備の判定が別々のシートに散っていると、確認する人が
    突き合わせないと可否が分からない。1枚目の次に総括を置く。
    """
    s = wb.sheet("要確認事項")
    for c, wdt in enumerate([6, 22, 96, 12]):
        s.set_width(c, wdt)
    s.add_title("総合判定と着手前チェックリスト", span=4)
    s.add_blank()
    s.add(["総合判定", "計画は成立しています" if verdict["ok"] else "是正が必要です"],
          STYLE_BOLD)
    for b in verdict.get("blockers", []):
        s.add_cells([Cell("是正"), Cell(b)])
    s.add(["要確認", f"{verdict.get('warn', 0)}件",
           "／".join(verdict.get("warn_breakdown", []))], STYLE_BOLD)
    s.add_blank()
    items = [("法規チェック", f"{c.name}: {c.message}（{c.basis}）")
             for c in checks if c.status == WARN]
    items += [(kind, text) for kind, sev, text in (warnings or []) if sev != "NG"]
    if not items:
        return
    s.add_header(["#", "分類", "内容", "確認"])
    for i, (kind, text) in enumerate(items, 1):
        s.add_cells([
            Cell(i, STYLE_BORDER), Cell(kind, STYLE_BORDER),
            Cell(text, STYLE_BORDER), Cell("", STYLE_BORDER),
        ])


def _sheet_law_check(wb, checks: list[CheckResult]) -> None:
    s = wb.sheet("法規チェック")
    for c, wdt in enumerate([6, 18, 10, 60, 46]):
        s.set_width(c, wdt)
    s.add_title("法規チェック結果", span=5)
    s.add_blank()
    s.add_header(["#", "項目", "判定", "内容", "根拠"])
    for c in checks:
        s.add_cells([
            Cell(c.check_id, STYLE_BORDER), Cell(c.name, STYLE_BORDER),
            Cell(c.status, STYLE_BORDER), Cell(c.message, STYLE_BORDER),
            Cell(c.basis, STYLE_BORDER),
        ])


def _sheet_attachments(wb, info: NotificationInfo, details=None, model=None) -> None:
    s = wb.sheet("添付図書チェック")
    for c, wdt in enumerate([26, 18, 52, 12]):
        s.set_width(c, wdt)
    s.add_title("添付図書チェックリスト（安衛法88条）", span=4)
    s.add_blank()
    s.add_header(["図書", "作成区分", "内容", "確認"])
    vm = model.master.vertical_member_name if model is not None else "支柱"
    for name, kind, desc in ATTACHMENTS:
        # 立面図の説明は方式で呼び分ける（枠組は建枠構成）
        if name == "立面図":
            desc = desc.replace("支柱構成", f"{vm}構成")
        s.add_cells([
            Cell(name, STYLE_BORDER), Cell(kind, STYLE_BORDER),
            Cell(desc, STYLE_BORDER), Cell("", STYLE_BORDER),
        ])
    if details:
        s.add_blank()
        s.add(["■ 詳細図の内訳（この計画に必要な図）"], STYLE_BOLD)
        s.add_header(["図面名", "detailType", "必要な理由", "確認"])
        for d in details:
            s.add_cells([
                Cell(d.title, STYLE_BORDER), Cell(d.key, STYLE_BORDER),
                Cell(d.reason, STYLE_BORDER), Cell("", STYLE_BORDER),
            ])
    s.add_blank()
    s.add(["提出先", info.labor_office or FILL_IN], STYLE_BOLD)
    s.add(["提出期限", (info.submission_deadline().isoformat()
                    if info.submission_deadline() else "工事着手30日前")], STYLE_BOLD)
