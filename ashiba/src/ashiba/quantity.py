"""数量拾いエンジン.

従属部材（ブレス・アンダーベース等）は配置せず数量ルールで自動算出する（仕様3）。
拾いルールは QuantityRules に集約し、会社ごとの拾い方の違いに合わせて調整できる。

前提（MVPの構造モデル・READMEにも明記）:
- 本足場＝内外2列建地。支柱構成は内外同一とみなす
- 布材は手すり兼用。各作業層: 外側に手すり＋中桟2本、床レベルに内外2本
- 腕木（内外建地を繋ぐ布材）: 支柱位置ごと×(作業層数＋根がらみ)
- ブレスは外側構面数（スパン×層）から算出。W1800用のみ（他スパンは注記）
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
    udegi_nominal: int = 600            # 腕木の呼び寸法（内外建地間隔）
    brace_per_face: int = 1             # 構面あたりブレス本数
    truck_payload_kg: float = 3200.0    # 4t車の実効積載（積載効率0.8）


@dataclass
class BomLine:
    part: Part
    qty: int
    note: str = ""

    @property
    def subtotal_weight(self) -> float:
        return self.part.weight_kg * self.qty


@dataclass
class QuantityResult:
    lines: list[BomLine]
    kake_menseki_m2: float              # 架け面積 [m2]
    total_weight_kg: float
    truck_count: int
    notes: list[str] = field(default_factory=list)

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
) -> QuantityResult:
    rules = rules or QuantityRules()
    m = model.master
    plan = model.plan
    elev = model.elevation
    counts: dict[str, int] = {}   # model_no -> qty
    parts: dict[str, Part] = {}
    notes: list[str] = []

    def add(part: Optional[Part], qty: int, what: str) -> None:
        if qty <= 0:
            return
        if part is None:
            notes.append(f"マスタに該当部材がありません: {what}（数量{qty}）")
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
                notes.append(
                    f"先行手摺{s}がマスタにありません（{n * n_levels}本）。"
                    "この寸法は布材による手すり＋中桟で計画してください"
                )
                continue
            add(part, n * n_levels, f"先行手摺{s}")

    # ---- 腕木（内外連結。支柱位置×(作業層+根がらみ)） ----
    if rows >= 2:
        add(
            m.find("布材", rules.udegi_nominal),
            posts_per_line * (n_levels + 1),
            f"腕木（布材{rules.udegi_nominal}）",
        )

    # ---- 踏板（スパン×作業層×幅構成。階段室の区間には敷かない） ----
    deck_span_counts = dict(span_counts)
    if stair_plan is not None and stair_plan.towers:
        from .stairs import stair_deck_deduction
        for s, n in stair_deck_deduction(model, stair_plan).items():
            deck_span_counts[s] = max(0, deck_span_counts.get(s, 0) - n)
    for w in model.config.deck_widths:
        for s, n in deck_span_counts.items():
            add(m.deck_parts(w, s), n * n_levels, f"踏板 幅{w}×{s}")

    # ---- ブレス（構面数から自動算出。外側のみ） ----
    brace = next(iter(m.by_category("筋交")), None)
    if brace:
        n_brace_spans = span_counts.get(brace.nominal_dim, 0)
        add(brace, n_brace_spans * n_levels * rules.brace_per_face, "ブレス")
        other = total_spans - n_brace_spans
        if other > 0:
            notes.append(
                f"1800以外のスパン{other}箇所はブレス規格外のため未計上"
                "（布板ブレス等を別途検討）"
            )

    # ---- 幅木（各作業層 外側スパン毎） ----
    if model.config.has_toe_board:
        for s, n in span_counts.items():
            add(m.find("幅木", s), n * n_levels, f"幅木{s}")

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
    # 昇降階段は2層以下毎に踊り場を設ける
    n_landings = (
        stair_plan.total_landings if stair_plan is not None and stair_plan.towers
        else 0
    )
    add(landing, n_landings, "踊り場（2層以下毎）")

    # ---- 朝顔（設置段数×外周スパン数。受けブラケットと方杖は支柱位置ごと） ----
    asagao = model.config.asagao
    if asagao and asagao.stages > 0:
        panel = next((p for p in m.by_category("朝顔") if "防護棚" in p.note), None)
        bracket = next((p for p in m.by_category("朝顔") if "受けブラケット" in p.note), None)
        hozue = next((p for p in m.by_category("朝顔") if "方杖" in p.note), None)
        add(panel, total_spans * asagao.stages, "朝顔本体")
        add(bracket, posts_per_line * asagao.stages, "朝顔受けブラケット")
        add(hozue, posts_per_line * asagao.stages, "朝顔方杖")
        # 取付部は2スパン毎に壁つなぎを増設
        extra_ties = 0
        for e in plan.edges:
            extra_ties += max(1, e.span_count // max(asagao.tie_every_spans, 1))
        add(kt, extra_ties * asagao.stages, "朝顔取付部の壁つなぎ")

    # ---- ブラケット区間（面の区間属性から算出。支柱ラインは動かさない） ----
    if bracket_sections:
        from .brackets import bracket_quantities
        for (width, purpose), qty in bracket_quantities(model, bracket_sections).items():
            if purpose == "方杖":
                part = next((p for p in m.by_category("ブラケット")
                             if p.nominal_dim == width), None)
                notes.append(f"方杖{qty}本が必要です（緊結部付ブラケット拡幅部）")
                continue
            note_key = "張出" if purpose == "張出" else ""
            part = next(
                (p for p in m.by_category("ブラケット")
                 if p.nominal_dim == width and (note_key in p.note if note_key else "張出" not in p.note)),
                None,
            )
            add(part, qty, f"ブラケット{width}（{purpose}）")

    return _assemble(model, rules, counts, parts, notes)


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
        notes=notes,
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
    widths = m.frame_widths()
    fits = [w for w in widths if w >= need_width]
    if fits:
        frame_width = min(fits)
    else:
        frame_width = max(widths) if widths else 1219
        notes.append(
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
    add(jack, n_frame_lines, "ジャッキ")
    add(under, n_frame_lines, "アンダーベース")

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

    # ---- 交差筋交（構面数×段数）。建枠間隔ごとに規格がある ----
    for s, n in span_counts.items():
        brace = next(
            (p for p in m.by_category("筋交") if p.nominal_dim == s), None
        )
        add(brace, n * n_stages, f"交差筋交{s}")

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
    add(
        landing,
        stair_plan.total_landings if stair_plan is not None and stair_plan.towers else 0,
        "踊り場（2層以下毎）",
    )

    # ---- 朝顔 ----
    asagao = model.config.asagao
    if asagao and asagao.stages > 0:
        panel = next((p for p in m.by_category("朝顔") if "防護棚" in p.note), None)
        bracket = next((p for p in m.by_category("朝顔") if "受けブラケット" in p.note), None)
        hozue = next((p for p in m.by_category("朝顔") if "方杖" in p.note), None)
        add(panel, n_bays * asagao.stages, "朝顔本体")
        add(bracket, n_frame_lines * asagao.stages, "朝顔受けブラケット")
        add(hozue, n_frame_lines * asagao.stages, "朝顔方杖")
