"""数量拾いエンジン.

従属部材（ブレス・アンダーベース等）は配置せず数量ルールで自動算出する（仕様3）。
拾いルールは QuantityRules に集約し、会社ごとの拾い方の違いに合わせて調整できる。

前提（MVPの構造モデル・READMEにも明記）:
- 本足場＝内外2列建地。支柱構成は内外同一とみなす
- 布材は手すり兼用。各作業層: 外側に手すり＋中桟2本、床レベルに内外2本
- 腕木（内外建地を繋ぐ布材）: 支柱位置ごと×(作業層数＋根がらみ)。呼び寸法は
  ScaffoldModel.post_row_spacing_mm（発注する部材の寸法）から引く
- くさびの斜材は設置間隔（既定6層6スパン以下毎に交さ2方向）から算出。
  全構面で拾うと1桁多くなるので、採用した間隔は必ず注記に出す
- 枠組は交差筋交が全スパン×全段×2本（外構面・内構面）。布材は根がらみと
  最上層の手すりだけ（中間層の手すりは1つ上の建枠が兼ねる）

数量表に載せるのは足場本体だけではない。以下も同じ表に出す:
- 荷受けステージの部材と取付部の壁つなぎ（platforms=）
- 開口部の梁枠（openings=）
- 階段室の区間は踏板を差し引く（stair_plan=）
- ブラケット区間の踏板幅の差し替え（bracket_sections=）
マスタに無い寸法は代用せず注記に出す（出1500mmのステージに600のブラケットを
当てる、といった置き換えをしない）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .master import Part, PartMaster
from .model import GUARD_RAIL_ADVANCE, ScaffoldModel

if TYPE_CHECKING:
    from .stairs import StairPlan


@dataclass
class QuantityRules:
    rows: int = 2                       # 建地列数（本足場=2、一側=1）
    rails_per_level_outer: int = 2      # 作業層あたり外側の手すり＋中桟
    ledgers_per_level_floor: int = 2    # 作業層あたり床レベルの布材（内外）
    ledgers_negarami: int = 2           # 根がらみ（内外）
    # 腕木の呼び寸法。Noneならモデルの建地列間隔から引く
    # （固定値にすると系列や次世代足場で図面と発注部材がズレる）
    udegi_nominal: Optional[int] = None
    # 斜材（ブレス）の設置間隔。くさび式足場用斜材は「6層6スパン以下毎に交さ2方向」が基準。
    # 全スパン・全層に入れる会社もあるので、その場合は1/1にする（数量が大きく変わる）
    brace_every_spans: int = 6
    brace_every_levels: int = 6
    braces_per_location: int = 2        # 交さ2方向＝1箇所にX形で2本
    # 枠組の交差筋交は外構面と内構面の両方に入れる。片面だけの現場は1にする
    frame_braces_per_bay: int = 2
    truck_payload_kg: float = 3200.0    # 4t車の実効積載（積載効率0.8）


@dataclass
class BomLine:
    part: Part
    qty: int
    note: str = ""

    @property
    def subtotal_weight(self) -> float:
        return self.part.weight_kg * self.qty


class Notes(list):
    """数量の注記。手配・検討が要るものは action() で分けて持つ.

    「マスタに部材が無い」「カタログ品では受けられない」は、放っておくと
    現場で足りない・受けられないになる。計上ルールの説明と同じ扱いで
    注記に埋もれると読み飛ばされるので、要確認一覧へ回す分を区別する。
    """

    def __init__(self, *a):
        super().__init__(*a)
        self.actions: list[str] = []

    def action(self, msg: str) -> None:
        self.append(msg)
        self.actions.append(msg)


@dataclass
class QuantityResult:
    lines: list[BomLine]
    kake_menseki_m2: float              # 架け面積 [m2]
    total_weight_kg: float
    truck_count: int
    notes: list[str] = field(default_factory=list)
    # notes のうち手配・検討が要るもの（説明だけの注記は含めない）
    warnings: list[str] = field(default_factory=list)

    def qty_of(self, category: str, nominal: Optional[int] = None) -> int:
        return sum(
            l.qty
            for l in self.lines
            if l.part.category == category
            and (nominal is None or l.part.nominal_dim == nominal)
        )


def take_off(
    model: ScaffoldModel,
    rules: Optional[QuantityRules] = None,
    bracket_sections: Optional[list] = None,
    stair_plan: Optional["StairPlan"] = None,
    platforms=None,
    openings=None,
) -> QuantityResult:
    rules = rules or QuantityRules()
    m = model.master
    plan = model.plan
    elev = model.elevation
    counts: dict[str, int] = {}   # model_no -> qty
    parts: dict[str, Part] = {}
    notes = Notes()

    def add(part: Optional[Part], qty: int, what: str) -> None:
        if qty <= 0:
            return
        if part is None:
            notes.action(f"マスタに該当部材がありません: {what}（数量{qty}）")
            return
        m.assert_series(part)
        counts[part.model_no] = counts.get(part.model_no, 0) + qty
        parts[part.model_no] = part

    rows = 1 if model.config.scaffold_form == "一側足場" else rules.rows
    posts_per_line = plan.total_posts        # 帰属ルールで二重計上なし
    n_posts = posts_per_line * rows
    n_levels = elev.n_levels
    total_spans = plan.total_spans

    # 枠組式は建枠が支柱＋腕木＋手すりを兼ねるため、部材構成がくさび式と根本的に違う
    if m.is_frame:
        _count_frame_parts(model, rules, add, notes, stair_plan)
        _count_bracket_parts(model, bracket_sections, add, notes, counts)
        _count_platform_parts(model, platforms, add, notes)
        _count_opening_parts(model, openings, add, notes)
        _note_inner_rail_if_wide(model, notes)
        _note_double_posts_if_tall(model, notes)
        return _assemble(model, rules, counts, parts, notes)

    # ---- 支柱（1支柱位置あたりの積み上げ構成×位置数、内外同一構成） ----
    counts_posts: dict[int, int] = {}
    for nominal in elev.posts:
        counts_posts[nominal] = counts_posts.get(nominal, 0) + 1
    for nominal, per_line in counts_posts.items():
        part = next(
            (p for p in m.by_category("支柱")
             if p.nominal_dim == nominal and "根がらみ" not in p.note and "屋根" not in p.note),
            None,
        )
        add(part, per_line * n_posts, f"支柱{nominal}")

    # ---- ジャッキ・アンダーベース（アンダーベース数=ジャッキ数） ----
    jack = next((p for p in m.by_category("ジャッキ") if "ベース" not in p.note and "アンダー" not in p.note), None)
    under = next((p for p in m.by_category("ジャッキ") if "アンダーベース" in p.note), None)
    add(jack, n_posts, "ジャッキ")
    add(under, n_posts, "アンダーベース")

    # ---- 布材（スパン方向: 根がらみ＋床レベル＋手すり・中桟） ----
    # 手すり方式で外側の手すり・中桟の拾い方が変わる。
    # 先行手すり工法は専用部材（手すり＋斜材が一体）が布材2本を置き換える
    advance_rail = model.config.guard_rail_type == GUARD_RAIL_ADVANCE
    rails_outer = 0 if advance_rail else rules.rails_per_level_outer
    per_span_rails = (
        rules.ledgers_negarami
        + n_levels * (rules.ledgers_per_level_floor + rails_outer)
    )
    span_counts: dict[int, int] = {}
    for e in plan.edges:
        for s in e.spans:
            span_counts[s] = span_counts.get(s, 0) + 1
    for s, n in span_counts.items():
        add(m.find("布材", s), n * per_span_rails, f"布材{s}")

    # ---- 先行手摺（手すり先行工法の場合。スパン×層に1本） ----
    if advance_rail:
        for s, n in span_counts.items():
            part = m.find("先行手摺", s)
            if part is None:
                notes.action(
                    f"先行手摺{s}がマスタにありません（{n * n_levels}本）。"
                    "この寸法は布材による手すり＋中桟で計画してください"
                )
                continue
            add(part, n * n_levels, f"先行手摺{s}")

    # ---- 腕木（内外連結。支柱位置×(作業層+根がらみ)） ----
    if rows >= 2:
        udegi = rules.udegi_nominal or model.post_row_spacing_mm
        add(
            m.find("布材", udegi),
            posts_per_line * (n_levels + 1),
            f"腕木（布材{udegi}）",
        )

    # ---- 踏板（スパン×作業層×幅構成。階段室の区間には敷かない） ----
    # 床は「スパン×層」のセル数で数える。階段室は全層、開口部は梁枠より下の
    # 層だけ敷かないので、スパン本数の引き算では表せない
    deck_cells = {s: n * n_levels for s, n in span_counts.items()}
    from .openings import opening_deck_deduction
    open_cut = opening_deck_deduction(model, openings)
    # 開口部（梁枠より下）は通路。床も幅木も無い
    toe_cells = {
        s: max(0, n - open_cut.get(s, 0)) for s, n in deck_cells.items()
    }
    for s, cells in open_cut.items():
        deck_cells[s] = max(0, deck_cells.get(s, 0) - cells)
    if stair_plan is not None and stair_plan.towers:
        # 階段室には踏板を敷かないが、外構面の幅木は残る（階段側の落下防止）
        from .stairs import stair_deck_deduction
        for s, n in stair_deck_deduction(model, stair_plan).items():
            deck_cells[s] = max(0, deck_cells.get(s, 0) - n * n_levels)
    # 一側足場は建地1列で、作業床はブラケット受けの1枚敷き。本足場の内外2枚敷きを
    # そのまま数えると踏板が倍になる（実際、重量で3.7t多く出ていた）
    deck_widths = list(model.deck_widths_in_use)
    if rows == 1 and len(model.config.deck_widths) > len(deck_widths):
        notes.append(
            f"一側足場のため作業床は幅{deck_widths[0]}mmの1枚敷きで計上しています"
            f"（本足場の{'+'.join(str(w) for w in model.config.deck_widths)}ではなく）"
        )
    for w in deck_widths:
        for s, cells in deck_cells.items():
            add(m.deck_parts(w, s), cells, f"踏板 幅{w}×{s}")
    if rows == 1:
        # 建地が1列なので床は片持ち。受けるブラケットが要る（本足場には無い部材）
        brk = next((p for p in m.by_category("ブラケット")
                    if p.nominal_dim >= deck_widths[0] and "張出" not in p.note
                    and "内" not in p.note), None)
        need = posts_per_line * n_levels
        if brk is None:
            notes.action(
                f"一側足場の作業床を受けるブラケット（幅{deck_widths[0]}mm以上）が"
                f"マスタにありません（{need}本）。別途手配してください"
            )
        else:
            add(brk, need, f"一側足場の床受けブラケット{brk.nominal_dim}")

    # ---- 斜材（ブレス）: 6層6スパン以下毎に交さ2方向 ----
    # 全スパン×全層に入れるのではなく設置間隔から算出する。
    # 枠組の交差筋交とは考え方が違う（あちらは建枠と一体で構面を成すので全スパン）
    brace = next(iter(m.by_category("筋交")), None)
    if brace:
        every_s = max(1, rules.brace_every_spans)
        every_l = max(1, rules.brace_every_levels)
        level_groups = math.ceil(n_levels / every_l) if n_levels else 0
        n_locations = 0
        shortfall = 0
        for e in plan.edges:
            # 斜材は規格スパン（1800）の構面に入れる
            fit_bays = sum(1 for s in e.spans if s == brace.nominal_dim)
            want = math.ceil(e.span_count / every_s) if e.span_count else 0
            n_locations += min(want, fit_bays) * level_groups
            shortfall += max(0, want - fit_bays) * level_groups
        add(brace, n_locations * rules.braces_per_location, "斜材（ブレス）")
        notes.append(
            f"斜材は{every_s}スパン×{every_l}層以下毎に交さ2方向で計上"
            f"（{n_locations}箇所×{rules.braces_per_location}本）。"
            "全構面に入れる場合は QuantityRules の brace_every_spans/levels を1にしてください"
        )
        if shortfall > 0:
            notes.action(
                f"斜材を入れる規格スパン（{brace.nominal_dim}）が"
                f"{shortfall}箇所分不足しています。"
                "その区間は布板ブレス等の別手段を検討してください"
            )

    # ---- 幅木（各作業層 外側スパン毎） ----
    if model.config.has_toe_board:
        for s, cells in toe_cells.items():
            add(m.find("幅木", s), cells, f"幅木{s}")

    # ---- 壁つなぎ ----
    kt = next(iter(m.by_category("壁つなぎ")), None)
    add(kt, len(model.wall_ties), "壁つなぎ")

    # ---- 階段・踊り場（自動配置があればその箇所数、なければ設定値） ----
    stair = next((p for p in m.by_category("階段") if "ハーフ" not in p.note), None)
    landing = next(iter(m.by_category("踊り場")), None)
    n_towers = (
        stair_plan.count if stair_plan is not None and stair_plan.towers
        else model.config.n_stairs
    )
    add(stair, n_towers * n_levels, "階段")
    # 昇降階段は2層以下毎に踊り場を設ける。階段を計上したのに踊り場だけ0本に
    # なると、必須部材が黙って発注から抜ける
    add(landing, _landing_count(model, stair_plan, n_towers), "踊り場（2層以下毎）")

    _count_asagao_parts(model, span_counts, posts_per_line, add, notes, kt)

    _count_bracket_parts(model, bracket_sections, add, notes, counts)
    _count_platform_parts(model, platforms, add, notes)
    _count_opening_parts(model, openings, add, notes)
    _note_inner_rail_if_wide(model, notes)
    _note_double_posts_if_tall(model, notes)
    return _assemble(model, rules, counts, parts, notes)


def _count_asagao_parts(
    model: ScaffoldModel, span_counts: dict, posts_per_line: int, add, notes, kt
) -> None:
    """朝顔（防護棚）の部材と、隙間が残る箇所の注記（くさび式・枠組式で共通）.

    朝顔は落下物を受ける設備なので、隙間が残る箇所（出隅・端数スパン）を
    黙ってはいけない。枠組の経路にだけ注記が無い、という状態も作らない。
    """
    asagao = model.config.asagao
    if not asagao or asagao.stages <= 0:
        return
    m = model.master
    panel = next((p for p in m.by_category("朝顔") if "防護棚" in p.note), None)
    bracket = next((p for p in m.by_category("朝顔") if "受けブラケット" in p.note), None)
    hozue = next((p for p in m.by_category("朝顔") if "方杖" in p.note), None)

    # 朝顔本体はスパンに合う寸法で拾う。1種類しか無い系列では、
    # 短いスパンに長い板を当てることになるので、そうと書く
    odd: dict[int, int] = {}
    for sp, n in span_counts.items():
        fit = next(
            (q for q in m.by_category("朝顔")
             if "防護棚" in q.note and q.nominal_dim == sp), None
        )
        if fit is not None:
            add(fit, n * asagao.stages, f"朝顔本体{sp}")
        elif panel is not None:
            odd[sp] = n
            add(panel, n * asagao.stages,
                f"朝顔本体（{sp}スパンに{panel.nominal_dim}）")
        else:
            add(None, n * asagao.stages, f"朝顔本体{sp}")
    if odd and panel is not None:
        notes.action(
            "朝顔本体の呼び寸法が合わないスパンがあります（"
            + "、".join(f"{sp}mm×{n}" for sp, n in sorted(odd.items()))
            + f"）。{panel.nominal_dim}mmの板で計上しているので、"
            "現場で切り詰めるか、隙間を板・シートで塞いでください"
        )
    add(bracket, posts_per_line * asagao.stages, "朝顔受けブラケット")
    add(hozue, posts_per_line * asagao.stages, "朝顔方杖")

    # 出隅では2面の朝顔が突き合わず、隅に三角の隙間が残る（落下物が抜ける）
    corners = [c for c in model.plan.outline.corners if c.kind == "出隅"]
    if corners:
        notes.action(
            f"出隅{len(corners)}箇所は朝顔が突き合わない隅部になります"
            f"（{asagao.stages}段ぶん）。隅角部の板・シート等で塞いでください"
            "（本ツールは隅の部材を計上していません）"
        )

    # 取付部は所定スパン毎に壁つなぎを増設
    extra_ties = 0
    for e in model.plan.edges:
        extra_ties += max(1, e.span_count // max(asagao.tie_every_spans, 1))
    add(kt, extra_ties * asagao.stages, "朝顔取付部の壁つなぎ")


def _count_bracket_parts(
    model: ScaffoldModel, bracket_sections, add, notes, counts
) -> None:
    """ブラケット区間の部材を数量表に載せる（くさび式・枠組式で共通）.

    枠組式ではこの処理を通しておらず、区間を指定しても検証は通るのに
    数量表には1本も出なかった（指定が黙って消えていた）。
    """
    if not bracket_sections:
        return
    from .brackets import bracket_deck_changes, bracket_quantities

    m = model.master
    for (width, purpose), qty in bracket_quantities(model, bracket_sections).items():
        if purpose == "方杖":
            notes.action(f"方杖{qty}本が必要です（緊結部付ブラケット拡幅部）")
            continue
        note_key = "張出" if purpose == "張出" else ""
        part = next(
            (p for p in m.by_category("ブラケット")
             if p.nominal_dim == width
             and (note_key in p.note if note_key else "張出" not in p.note)),
            None,
        )
        if part is None:
            notes.action(
                f"ブラケット{width}mm（{purpose}）が系列 {m.series_id} のマスタに"
                f"ありません（{qty}本）。別途手配してください"
            )
            continue
        add(part, qty, f"ブラケット{width}（{purpose}）")

    # 張出し区間は作業床の外縁が建地より外に出る。その縁の手すり・中桟・幅木は
    # 通常の（建地位置の）手すりとは別に要る
    from .brackets import outer_edge_quantities

    for span, cells in outer_edge_quantities(model, bracket_sections).items():
        add(m.find("布材", span), cells * 2, f"張出し外縁の手すり・中桟{span}")
        if model.config.has_toe_board:
            add(m.find("幅木", span), cells, f"張出し外縁の幅木{span}")

    # 区間で踏板幅を変える指定は、数量にも反映しないと現場で足りない
    for span, from_w, to_w, n_lv in bracket_deck_changes(model, bracket_sections):
        new_part = m.deck_parts(to_w, span)
        if new_part is None:
            notes.action(
                f"区間指定の踏板 幅{to_w}×{span}がマスタにありません"
                f"（{n_lv}枚）。幅{from_w}のままで計上しています"
            )
            continue
        old_part = m.deck_parts(from_w, span)
        if old_part is not None:
            counts[old_part.model_no] = max(
                0, counts.get(old_part.model_no, 0) - n_lv
            )
        add(new_part, n_lv, f"踏板 幅{to_w}×{span}（区間指定）")


def _count_opening_parts(model: ScaffoldModel, openings, add, notes) -> None:
    """開口部の梁枠を数量表に載せる.

    マスタに梁枠はあるのに、どこからも拾っていなかった。梁枠が要る計画で
    数量表に出てこないと、支柱を抜いた開口が受けられない。
    """
    if openings is None or not openings.openings:
        return
    m = model.master
    for o in openings.openings:
        part = next(
            (p for p in m.by_category("梁枠") if p.nominal_dim == o.beam_span_mm),
            None,
        )
        if part is None:
            notes.action(
                f"梁枠{o.beam_span_mm}mmがマスタにありません（辺{o.edge_index}）。"
                "規格品の梁枠で計画し直してください"
            )
            continue
        add(part, 1, f"梁枠{o.beam_span_mm}（辺{o.edge_index}）")
    if openings.removed_posts:
        # 補強・積載低減が要ることは openings.issues が開口部ごとに言う。
        # ここで同じ対応をもう一度挙げると要確認一覧に二重で並ぶ
        notes.append(
            f"開口部で支柱{openings.removed_posts}本を抜いています。"
            "梁枠の両端支柱は補強し、梁枠上の作業床は積載荷重を低減してください"
        )


def _count_platform_parts(model: ScaffoldModel, platforms, add, notes) -> None:
    """荷受けステージ・昇降機の部材を数量表に載せる.

    ここを繋がないと、ステージの張出ブラケット・踏板・幅木・手すりと
    取付部の壁つなぎが発注リストから丸ごと抜ける。構造計算では直下の建地を
    見ているのに、部材だけ数量表に出てこない状態だった。
    """
    if platforms is None or not (platforms.stages or platforms.hoists):
        return
    from .platforms import _bracket_nominal, platform_part_demands

    m = model.master
    for d in platform_part_demands(model, platforms):
        if d.qty <= 0:
            continue
        if d.nominal_dim is None and d.note_contains:
            # 出を受けられる寸法がカタログに無い。分類だけで引き当てると
            # 出1500mmのステージに600のブラケットを当ててしまう
            continue
        cands = [
            p for p in m.by_category(d.category)
            if (d.nominal_dim is None or p.nominal_dim == d.nominal_dim)
            and (not d.note_contains or d.note_contains in p.note)
        ]
        if not cands:
            # ラベルは何の部材かを自分で名乗る（ステージ／昇降機の両方が来る）
            notes.action(
                f"{d.label}"
                + (f"（呼び{d.nominal_dim}）" if d.nominal_dim else "")
                + f"がマスタにありません（{d.qty}）。別途手配してください"
            )
            continue
        add(cands[0], d.qty, d.label)

    for st in platforms.stages:
        if _bracket_nominal(model, st.projection_mm) is None:
            notes.action(
                f"辺{st.edge_index}のステージは出{st.projection_mm:.0f}mmで、"
                "カタログの張出ブラケットでは受けられません。"
                "単管等による支持を個別に検討してください"
            )


def _landing_count(model: ScaffoldModel, stair_plan, n_towers: int) -> int:
    """踊り場の本数.

    stair_plan があればその配置から、無ければ階段箇所数×1箇所あたりの段数で
    求める。階段を計上しているのに踊り場だけ0本になるのを防ぐ。
    """
    if stair_plan is not None and stair_plan.towers:
        return stair_plan.total_landings
    from .stairs import landings_per_tower

    return landings_per_tower(model) * n_towers


DOUBLE_POST_HEIGHT_MM = 31000   # これを超える部分の建地は2本組（安衛則571条）


def _note_double_posts_if_tall(model: ScaffoldModel, notes) -> None:
    """31m超の2本組は数量に含めていないことを、必要本数つきで書く.

    法規チェックは警告を出すのに数量表は単管1本組のままで、部材が足りない。
    除外規定（設計荷重が最大使用荷重以内）があるので自動では計上せず、
    どれだけ要るのかを数字で出して判断できるようにする。
    """
    h = model.scaffold_height_mm
    if h <= DOUBLE_POST_HEIGHT_MM:
        return
    below = h - DOUBLE_POST_HEIGHT_MM
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    lines = model.plan.total_posts * rows
    notes.action(
        f"足場高さ{h / 1000:.2f}mは31mを超えます。最高部から31mを超える部分"
        f"（GL〜{below / 1000:.2f}m）の建地は2本組が必要ですが、追加の支柱・"
        f"ジャッキは数量に含んでいません（該当は支柱{lines}本ぶん）。"
        "建地下端の設計荷重が最大使用荷重以内と確認できる場合は除外できます"
    )


def _note_inner_rail_if_wide(model: ScaffoldModel, notes: list[str]) -> None:
    """離れが300mmを超える面は躯体側にも墜落防止措置が要る.

    法規チェックと割付の警告では「手すりの設置または安全帯の使用等」と
    出しているが、数量表には躯体側の手すり材が入っていない。どちらを選ぶかは
    現場判断なので自動では計上しないが、入っていないことは書いておく。
    """
    wide = [
        (e.edge_index, e.standoff, e.span_count)
        for e in model.plan.edges if e.standoff > 300.0 + 1e-6
    ]
    if not wide:
        return
    spans = sum(w[2] for w in wide)
    faces = "、".join(f"{model.face_name(i)} {d:.0f}mm" for i, d, _ in wide)
    # 措置が要ること自体は割付の警告が言う。ここは数量側の話に絞る
    notes.action(
        f"離れが300mmを超える面（{faces}）の躯体側手すり材は数量に含んでいません"
        f"（該当{spans}スパン）。躯体側手すりで対応する場合は布材を別途計上してください"
    )


def _assemble(
    model: ScaffoldModel,
    rules: QuantityRules,
    counts: dict[str, int],
    parts: dict[str, Part],
    notes: list[str],
) -> QuantityResult:
    """集計結果を QuantityResult に組み立てる（くさび式・枠組式で共通）."""
    lines = [BomLine(part=parts[k], qty=v) for k, v in sorted(counts.items())]
    total_weight = sum(l.subtotal_weight for l in lines)

    # ---- 架け面積: (建物外周+4m)×(建物高さ+0.5m) ----
    perimeter_m = model.plan.outline.perimeter / 1000.0
    height_m = (model.building_height_mm or model.scaffold_height_mm) / 1000.0
    kake = (perimeter_m + 4.0) * (height_m + 0.5)

    return QuantityResult(
        lines=lines,
        kake_menseki_m2=round(kake, 2),
        total_weight_kg=round(total_weight, 1),
        truck_count=math.ceil(total_weight / rules.truck_payload_kg) if total_weight else 0,
        notes=list(notes),
        warnings=list(getattr(notes, "actions", [])),
    )


def _count_frame_parts(
    model: ScaffoldModel,
    rules: QuantityRules,
    add,
    notes: list[str],
    stair_plan=None,
) -> None:
    """枠組足場の数量ルール.

    建枠が支柱・腕木・手すりを兼ねる。従属部材は建枠数から自動算出する（仕様3.1）:
    - アームロック: 建枠2枚（1構面）に1個
    - 連結ピン: 建枠の縦継ぎ1箇所に1本＝(段数-1)×建枠列数
    - 交差筋交: 構面数（スパン×段数）に1組
    """
    m = model.master
    plan = model.plan
    elev = model.elevation

    n_bays = plan.total_spans          # 構面数（スパン数）
    n_frame_lines = plan.total_posts   # 建枠が建つ位置（＝支柱位置）
    n_stages = len(elev.posts)         # 建枠の段数
    n_levels = elev.n_levels

    # ---- 建枠（1構面に2枚＝両側。段数ぶん積む） ----
    stage_counts: dict[int, int] = {}
    for h in elev.posts:
        stage_counts[h] = stage_counts.get(h, 0) + 1
    # 建枠幅は「近い幅」ではなく「布板が載る最小幅」を選ぶ
    # （近似で選ぶと布板より狭い建枠になり、実際には組めない）
    need_width = model.deck_width_total
    frame_width, fits = m.frame_width_for(need_width)
    if not fits:
        notes.action(
            f"布板幅の合計{need_width}mmに対し建枠幅が不足しています"
            f"（最大{frame_width}mm）。布板構成か建枠規格を見直してください"
        )
    for h, per_line in stage_counts.items():
        part = next(
            (p for p in m.by_category("建枠")
             if p.nominal_dim == h and f"幅{frame_width}" in p.note),
            None,
        )
        add(part, per_line * n_frame_lines, f"建枠 幅{frame_width}×高{h}")

    # ---- ジャッキ・アンダーベース ----
    jack = next((p for p in m.by_category("ジャッキ") if "アンダー" not in p.note), None)
    under = next((p for p in m.by_category("ジャッキ") if "アンダーベース" in p.note), None)
    # 建枠は1枚で2脚（内外の建地を兼ねる）。建枠の枚数で数えると脚が半分になり、
    # 現場でジャッキが足りなくなる
    n_frame_legs = n_frame_lines * rules.rows
    add(jack, n_frame_legs, "ジャッキ（建枠1枚に2脚）")
    add(under, n_frame_legs, "アンダーベース（建枠1枚に2脚）")

    # ---- 布板（作業床）。階段枠の区間には敷かない ----
    span_counts: dict[int, int] = {}
    for e in plan.edges:
        for s in e.spans:
            span_counts[s] = span_counts.get(s, 0) + 1
    deck_counts = dict(span_counts)
    if stair_plan is not None and stair_plan.towers:
        from .stairs import stair_deck_deduction
        for s, n in stair_deck_deduction(model, stair_plan).items():
            deck_counts[s] = max(0, deck_counts.get(s, 0) - n)
    for w in model.config.deck_widths:
        for s, n in deck_counts.items():
            part = next(
                (p for p in m.by_category("布板")
                 if p.nominal_dim == s and f"幅{w}" in p.note),
                None,
            )
            add(part, n * n_levels, f"布板 幅{w}×{s}")

    # ---- 布材（根がらみ＋最上層の手すり） ----
    # 枠組は各作業層の手すりを「1つ上の建枠」が兼ねるので中間層には要らない。
    # ただし次の2箇所は建枠が無いので布材で組む:
    #   - 脚部の根がらみ（内外2本／スパン）
    #   - 最上層の作業床の手すり・中桟（外側2本／スパン）
    # ここを拾っていなかったため、枠組の部材表には根がらみも最上段の
    # 手すりも出ていなかった
    frame_rails_per_span = rules.ledgers_negarami + rules.rails_per_level_outer
    for s, n in span_counts.items():
        add(m.find("布材", s), n * frame_rails_per_span, f"布材{s}（根がらみ・最上層手すり）")
    notes.append(
        f"枠組の布材は根がらみ{rules.ledgers_negarami}本＋最上層の手すり・中桟"
        f"{rules.rails_per_level_outer}本＝1スパンあたり{frame_rails_per_span}本で計上"
        "（中間層の手すりは1つ上の建枠が兼ねる）"
    )

    # ---- 交差筋交（構面数×段数）。建枠間隔ごとに規格がある ----
    # 枠組は交差筋交が建枠と一体で構面を成すため全スパン・全段に入る。
    # くさび式の斜材（6層6スパン以下毎）とは考え方が違う
    per_bay = max(1, rules.frame_braces_per_bay)
    for s, n in span_counts.items():
        brace = next(
            (p for p in m.by_category("筋交") if p.nominal_dim == s), None
        )
        add(brace, n * n_stages * per_bay, f"交差筋交{s}")
    notes.append(
        f"交差筋交は1構面あたり{per_bay}本で計上（外構面・内構面の両方）。"
        "片面のみの場合は QuantityRules の frame_braces_per_bay を1にしてください"
    )

    # ---- 従属部材: 建枠数から自動算出 ----
    armlock = next(iter(m.by_category("アームロック")), None)
    pin = next(iter(m.by_category("連結ピン")), None)
    add(armlock, n_bays * n_stages, "アームロック（建枠2枚に1個）")
    add(pin, max(0, n_stages - 1) * n_frame_lines, "連結ピン（縦継ぎ1箇所に1本）")

    # ---- 幅木・壁つなぎ・階段枠 ----
    if model.config.has_toe_board:
        for s, n in span_counts.items():
            add(m.find("幅木", s), n * n_levels, f"幅木{s}")
    kt = next(iter(m.by_category("壁つなぎ")), None)
    add(kt, len(model.wall_ties), "壁つなぎ")
    stair = next(iter(m.by_category("階段")), None)
    landing = next(iter(m.by_category("踊り場")), None)
    n_towers = (
        stair_plan.count if stair_plan is not None and stair_plan.towers
        else model.config.n_stairs
    )
    add(stair, n_towers * n_levels, "階段枠")
    add(landing, _landing_count(model, stair_plan, n_towers), "踊り場（2層以下毎）")

    # ---- 朝顔（くさび式と同じ数え方・同じ注記） ----
    _count_asagao_parts(model, span_counts, n_frame_lines, add, notes, kt)
