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
- 荷受けステージの部材と取付部の壁つなぎ、先端と妻側の手すり（platforms=）
- 昇降機の乗り込み口の防護（platforms=）
- 開口部の梁枠（openings=）
- ブラケット区間の踏板幅の差し替えと、張出しの外縁の手すり（bracket_sections=）
マスタに無い寸法は代用せず注記に出す（出1500mmのステージに600のブラケットを
当てる、といった置き換えをしない）。

**床が無い区間は差し引く**（図面も同じ区間を空ける）:
- 階段室は全層（段板で上がるので踏板を敷かない。stair_plan=）
- 開口部は梁枠より下の層（通路なので床も幅木も無い。openings=）
床の枚数は「スパン×層」のセル数で数える。スパン本数の引き算では、
階段室（全層）と開口部（一部の層）を区別できない。

対応が要る注記は Notes.action() で分けて持ち、さらに「手配」（発注に足す）と
「現場対応」（塞ぐ・検討する）を区別する。計上ルールの説明と同じ扱いで並べると、
発注漏れや未措置がそこに埋もれる。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .master import Part, PartMaster
from .model import GUARD_RAIL_ADVANCE, ScaffoldModel
from .model import ASAGAO_KIND_SAFE_WING

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

    ORDER = "手配"     # 発注に足すもの（マスタに無い部材など）
    SITE = "現場対応"  # 塞ぐ・検討する・確認するもの

    def __init__(self, *a):
        super().__init__(*a)
        self.actions: list[str] = []
        self.kinds: dict[str, str] = {}

    def action(self, msg: str, kind: str = ORDER) -> None:
        """対応が要る注記。発注に足すのか現場で対応するのかで分けて持つ.

        まとめて1つの分類に放り込むと、発注担当と現場担当のどちらが動く
        項目なのかを読む側が毎回判断することになる。
        """
        self.append(msg)
        self.actions.append(msg)
        self.kinds[msg] = kind


@dataclass
class QuantityResult:
    lines: list[BomLine]
    kake_menseki_m2: float              # 架け面積 [m2]
    total_weight_kg: float
    truck_count: int
    notes: list[str] = field(default_factory=list)
    # notes のうち手配・検討が要るもの（説明だけの注記は含めない）
    warnings: list[str] = field(default_factory=list)
    # 上の各項目が「手配」か「現場対応」か。発注担当と現場担当で見る先が違う
    warning_kinds: dict = field(default_factory=dict)

    def qty_of(self, category: str, nominal: Optional[int] = None) -> int:
        return sum(
            l.qty
            for l in self.lines
            if l.part.category == category
            and (nominal is None or l.part.nominal_dim == nominal)
        )

    def category_totals(self) -> list[tuple[str, int, float]]:
        """分類別の (分類名, 数量計, 重量計) を明細の出現順で返す.

        数量表CSV・部材等明細書・割付レポートで同じ集計を出すための唯一の出所。
        3箇所で別々に集計するとズレるので1メソッドに寄せる。
        """
        qty: dict = {}
        wt: dict = {}
        order: list = []
        for line in self.lines:
            c = line.part.category
            if c not in qty:
                order.append(c)
            qty[c] = qty.get(c, 0) + line.qty
            wt[c] = wt.get(c, 0.0) + line.subtotal_weight
        return [(c, qty[c], round(wt[c], 1)) for c in order]


def take_off(
    model: ScaffoldModel,
    rules: Optional[QuantityRules] = None,
    bracket_sections: Optional[list] = None,
    stair_plan: Optional["StairPlan"] = None,
    platforms=None,
    openings=None,
    terrain=None,
) -> QuantityResult:
    rules = rules or QuantityRules()
    m = model.master
    plan = model.plan
    elev = model.elevation
    counts: dict[str, int] = {}   # model_no -> qty
    parts: dict[str, Part] = {}
    # model_no -> {用途ラベル: 本数}。同じ型番が別々の用途で足されるとき
    # （壁つなぎ＝躯体＋朝顔取付＋ステージ取付 など）1行に潰れて内訳が消えるので、
    # 発注担当が図面の本数と照合できるよう用途別に持つ
    breakdown: dict[str, dict[str, int]] = {}
    notes = Notes()

    def add(part: Optional[Part], qty: int, what: str) -> None:
        if qty <= 0:
            return
        if part is None:
            notes.action(f"マスタに該当部材がありません: {what}（数量{qty}）")
            return
        m.assert_series(part)
        # 行は（品番, 分類）で持つ。同じ品番が別の分類でも使われる（信和の踊り場は踏板
        # SD-4018T そのもの）ときに、踏板の行へ黙って合算されて分類別の数が崩れないように
        key = (part.model_no, part.category)
        counts[key] = counts.get(key, 0) + qty
        parts[key] = part
        by = breakdown.setdefault(key, {})
        by[what] = by.get(what, 0) + qty

    rows = 1 if model.config.scaffold_form == "一側足場" else rules.rows
    posts_per_line = plan.total_posts        # 帰属ルールで二重計上なし
    # 出隅の外側コーナー支柱（内側列は隣の面とコーナー支柱を共有するが、外側列は
    # 面ごとに躯体コーナーで終わるので、四隅の外側に1本ずつ立つ）。3Dも同じ規則で描く
    n_corners = model.outer_corner_posts()
    n_posts = posts_per_line * rows + n_corners
    n_levels = elev.n_levels

    # 枠組式は建枠が支柱＋腕木＋手すりを兼ねるため、部材構成がくさび式と根本的に違う
    if m.is_frame:
        _count_frame_parts(model, rules, add, notes, stair_plan, openings, terrain,
                           platforms)
        _count_bracket_parts(model, bracket_sections, add, notes, counts)
        _count_platform_parts(model, platforms, add, notes)
        _count_opening_parts(model, openings, add, notes)
        _note_inner_rail_if_wide(model, notes)
        _note_bridged_zones(model, notes)
        _note_double_posts_if_tall(model, notes)
        return _assemble(model, rules, counts, parts, notes, breakdown)

    # ---- 支柱（1支柱位置あたりの積み上げ構成×位置数、内外同一構成） ----
    # 敷地に高低差があると、低い側の脚は下へ支柱を継ぎ足す。名目構成×位置数の
    # ままだと、その分の支柱が数量から抜ける（ジャッキ量一覧には出ているのに）
    counts_posts: dict[int, int] = {}
    feet = list(getattr(terrain, "feet", []) or [])
    extra_posts = 0
    if feet:
        for f in feet:
            for nominal in f.posts:
                counts_posts[nominal] = counts_posts.get(nominal, 0) + 1
        extra_posts = sum(len(f.posts) - len(elev.posts) for f in feet) * rows
        if extra_posts > 0:
            notes.append(
                f"敷地高低差の継ぎ足し分として{model.master.vertical_member_name}"
                f"{extra_posts}本を含みます（脚ごとの構成はジャッキ量一覧のとおり。"
                "立面図・3Dも脚ごとの地盤高で描いています）"
            )
    else:
        for nominal in elev.posts:
            counts_posts[nominal] = counts_posts.get(nominal, 0) + 1
    totals_posts = {k: v * (rows if feet else n_posts) for k, v in counts_posts.items()}
    if feet and n_corners:
        for nominal in elev.posts:
            totals_posts[nominal] = totals_posts.get(nominal, 0) + n_corners
    # 開口部で抜いた支柱は梁枠上（作業床〜天端）だけの短い構成に置き換える。
    # 全高のまま数えると梁枠より下の分が余計に入る（以前は「拾い直して」と注記していた）
    _replace_opening_stacks(
        model, openings, totals_posts, list(elev.posts),
        m.post_lengths(include_negarami=True), notes, "支柱",
    )
    for nominal, total in totals_posts.items():
        part = next(
            (p for p in m.by_category("支柱")
             if p.nominal_dim == nominal and "根がらみ" not in p.note and "屋根" not in p.note),
            None,
        )
        add(part, total, f"支柱{nominal}")

    # ---- ジャッキ・アンダーベース（アンダーベース数=ジャッキ数） ----
    # 「ベース」で除外すると品名が「パイプジャッキベース」の系列（日建ND）で
    # ジャッキが拾えなくなる。除外するのはアンダーベース（敷板）だけ
    under = next((p for p in m.by_category("ジャッキ") if "アンダーベース" in p.note), None)
    # 開口部で抜いた支柱は地面に達しないので、ジャッキもアンダーベースも要らない
    removed = openings.removed_posts if openings is not None else 0
    n_feet = max(0, n_posts - removed)
    _count_jacks(m, feet, rows, n_feet, add, notes)
    add(under, n_feet, "アンダーベース")
    _count_shims(m, feet, rows, add, notes)
    # 支柱最下部にだけ付く附属品（日建NDの下部カラー材など）。脚の数だけ
    for p in m.by_category("支柱附属"):
        if "最下部" in p.note:
            add(p, n_feet * _units_per_place(p), f"{p.model_no}（支柱最下部）")

    # ---- 布材（スパン方向: 根がらみ＋床レベル＋手すり・中桟） ----
    # 手すり方式で外側の手すり・中桟の拾い方が変わる。
    # 先行手すり工法は専用部材（手すり＋斜材が一体）が布材2本を置き換える
    advance_rail = model.config.guard_rail_type == GUARD_RAIL_ADVANCE
    rails_outer = 0 if advance_rail else rules.rails_per_level_outer
    # 根がらみ・床レベルの布材は建地列ごとに1本。一側足場は建地1列なので
    # 本足場の「内外2本」のまま数えると1スパンあたり5本（4層で）多くなる
    negarami_n = min(rules.ledgers_negarami, rows)
    floor_n = min(rules.ledgers_per_level_floor, rows)
    # 躯体側（内側建地列）の手すり＋中桟。3Dに描くのと同じ条件で数える
    rails_inner = 2 if (model.config.inner_guard_rail and rows >= 2) else 0
    per_span_rails = negarami_n + n_levels * (floor_n + rails_outer + rails_inner)
    span_counts: dict[int, int] = {}
    for e in plan.edges:
        for s in e.spans:
            span_counts[s] = span_counts.get(s, 0) + 1
    # 開口部（梁枠より下）は支柱を抜いた通路。布材も手すりも根がらみも入らない。
    # 図面はその区間を空けているのに数量だけ数えていた
    from .openings import opening_deck_deduction, opening_span_counts
    open_cut = opening_deck_deduction(model, openings)
    open_spans = opening_span_counts(model, openings)
    per_level_rails = floor_n + rails_outer + rails_inner
    # 荷受けステージの間口は、設置層で本体の外側手すり・中桟・幅木を外す（ステージ側の
    # 先端・妻側の手すりで防護し、荷を通す）。3D・立面も同じ区間を空ける
    stage_cells = _stage_cells(model, platforms)
    # 張出しブラケットで床を広げた層・スパンは、建地位置の手すり・中桟・幅木が床の途中に
    # 立つことになるので外し、新しい縁の手すり・幅木（_count_bracket_parts）に置き換える
    for s_, c_ in _outer_bracket_cells(model, bracket_sections).items():
        stage_cells[s_] = stage_cells.get(s_, 0) + c_
    # 内ブラケットで床を拡幅した区間は躯体との隙間が小さいので、躯体側の手すり・中桟は付けない
    from .brackets import inner_edge_cells
    inner_cut_cells = inner_edge_cells(model, bracket_sections or []) if rails_inner else {}
    open_rail_cut = 0
    for s, n in span_counts.items():
        cut = (open_cut.get(s, 0) * per_level_rails
               + open_spans.get(s, 0) * negarami_n
               + stage_cells.get(s, 0) * rails_outer
               + inner_cut_cells.get(s, 0) * rails_inner)
        open_rail_cut += cut
        add(m.find("布材", s), max(0, n * per_span_rails - cut), f"布材{s}")
    if inner_cut_cells:
        notes.append(
            f"内ブラケットで床を拡幅した区間（{sum(inner_cut_cells.values())}スパン×層）は躯体との隙間が"
            "小さくなるので、躯体側の手すり・中桟を外しています"
        )
    if stage_cells and (rails_outer or advance_rail):
        notes.append(
            f"荷受けステージの間口・昇降機の乗り込み口・張出しブラケット区間（計{sum(stage_cells.values())}スパン×層）は本体の"
            + ("外側の手すり・中桟" if rails_outer else "先行手摺")
            + ("・幅木" if model.config.has_toe_board else "")
            + "を外しています（ステージの先端・妻側の手すり／乗り込み口の開閉式手すり／張出し外縁の手すりで防護）"
        )
    # 本数だけ出しても検算できない。1スパンあたりの内訳を書く
    notes.append(
        f"布材は1スパンあたり 根がらみ{negarami_n}本"
        f"＋各層（床レベル{floor_n}本"
        + (f"＋外側の手すり・中桟{rails_outer}本" if rails_outer else "＋外側の手すりは先行手摺")
        + (f"＋躯体側の手すり・中桟{rails_inner}本" if rails_inner else "")
        + f"）×{n_levels}層 ＝ {per_span_rails}本で計上"
    )
    if open_rail_cut:
        notes.append(
            f"開口部（梁枠より下）は通路なので、その区間の布材{open_rail_cut}本"
            "（根がらみ・床レベル・手すり）を差し引いています"
        )
    # 継ぎ足した脚の区間の根がらみ（敷地高低差）。基準の根がらみは低い脚の
    # 地盤から離れるので、区間ごとに1段追加する（図面も同じ規則で描く）
    _add_extra_negarami(model, terrain, add, notes, rows)

    # ---- 出隅コーナーの升目（外側コーナー支柱までの布材・手すり・踏板・幅木） ----
    if n_corners:
        _count_corner_parts(model, m, rules, add, notes, n_corners, n_levels)

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
            add(part, max(0, n * n_levels - open_cut.get(s, 0) - stage_cells.get(s, 0)), f"先行手摺{s}")

    # ---- 腕木（内外連結。支柱位置×(作業層+根がらみ)） ----
    if rows >= 2:
        udegi = rules.udegi_nominal or model.post_row_spacing_mm
        from .openings import opening_removed_udegi
        udegi_cut = opening_removed_udegi(model, openings)
        n_udegi = max(0, posts_per_line * (n_levels + 1) - udegi_cut)
        notes.append(
            f"腕木は呼び{udegi}mmの布材を、支柱位置{posts_per_line}箇所×"
            f"（作業層{n_levels}＋根がらみ1）＝{posts_per_line * (n_levels + 1)}本で計上"
            + (f"（開口部で抜いた支柱ぶん{udegi_cut}本を差し引いて{n_udegi}本）"
               if udegi_cut else "")
            + "（布材の合計にはこの分も含む）"
        )
        reinf = getattr(model.config, "post_reinforcement", "") or ""
        if reinf:
            # 補強仕様: 腕木を強力つなぎ材（方杖付き）に替える。無ければ手配を出す
            strong = m.find("布材", udegi, reinf)
            add(strong, n_udegi, f"腕木（{reinf}{udegi}）")
            if strong is None:
                notes.action(f"{reinf}{udegi}mmが系列 {m.series_id} のマスタにありません（{n_udegi}本）")
        else:
            add(m.find("布材", udegi), n_udegi, f"腕木（布材{udegi}）")

    # ---- 踏板（スパン×作業層×幅構成。階段室の区間には敷かない） ----
    # 床は「スパン×層」のセル数で数える。階段室は全層、開口部は梁枠より下の
    # 層だけ敷かないので、スパン本数の引き算では表せない
    deck_cells = {s: n * n_levels for s, n in span_counts.items()}
    # 開口部（梁枠より下）は通路。床も幅木も無い（open_cut は布材と共通）
    toe_cells = {
        s: max(0, n - open_cut.get(s, 0) - stage_cells.get(s, 0)) for s, n in deck_cells.items()
    }
    for s, cells in open_cut.items():
        deck_cells[s] = max(0, deck_cells.get(s, 0) - cells)
    stair_cut_cells = 0
    if stair_plan is not None and stair_plan.towers:
        # 階段室には踏板を敷かないが、外構面の幅木は残る（階段側の落下防止）
        from .stairs import stair_deck_deduction
        for s, n in stair_deck_deduction(model, stair_plan).items():
            deck_cells[s] = max(0, deck_cells.get(s, 0) - n * n_levels)
            stair_cut_cells += n * n_levels
    _note_deck_cells(
        notes, m.deck_category, sum(span_counts.values()), n_levels,
        stair_cut_cells, len(stair_plan.towers) if stair_plan else 0,
        sum(open_cut.values()), sum(deck_cells.values()),
    )
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
                "その区間は布板ブレス等の別手段を検討してください",
                Notes.SITE,
            )

    # ---- 幅木（各作業層 外側スパン毎） ----
    if model.config.has_toe_board:
        for s, cells in toe_cells.items():
            add(m.find("幅木", s), cells, f"幅木{s}")

    # ---- 壁つなぎ ----
    kt = next(iter(m.by_category("壁つなぎ")), None)
    _add_wall_ties(model, platforms, kt, add, notes, openings=openings)

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
    _note_bridged_zones(model, notes)
    _note_double_posts_if_tall(model, notes)
    return _assemble(model, rules, counts, parts, notes, breakdown)


def _stage_cells(model: ScaffoldModel, platforms) -> dict[int, int]:
    """本体の外側手すり・中桟・幅木を外すセル（スパン呼び寸法 → スパン数×層数）.

    荷受けステージの間口（設置層）と、昇降機の乗り込み口（乗り込む層の、位置を含む
    1スパン。固定の手すりの代わりに開閉式手すりが付く）。3D・立面も同じ区間を空ける
    """
    from .platforms import _edge, _span_index

    out: dict[int, int] = {}
    for s in (getattr(platforms, "stages", None) or []):
        n_lv = max(1, len(s.levels) or 1)
        for nominal in s.spans(model):
            out[nominal] = out.get(nominal, 0) + n_lv
    for h in (getattr(platforms, "hoists", None) or []):
        edge = _edge(model, h.edge_index)
        if edge is None or not edge.spans:
            continue
        i = min(_span_index(edge, h.position_mm), len(edge.spans) - 1)
        nominal = edge.spans[i]
        out[nominal] = out.get(nominal, 0) + len(h.landings(model))
    return out


def _outer_bracket_cells(model: ScaffoldModel, bracket_sections) -> dict[int, int]:
    """張出しブラケットで床を広げた層・スパン（建地位置の外側手すり・幅木は新しい縁へ移る）."""
    from .brackets import outer_edge_quantities

    return outer_edge_quantities(model, bracket_sections or [])


def _count_corner_parts(model: ScaffoldModel, m: PartMaster, rules, add, notes,
                        n_corners: int, n_levels: int) -> None:
    """出隅の外側コーナー升目の部材（支柱・ジャッキは支柱位置数に足してある）.

    升目は建地列間隔（腕木の呼び寸法）角。布材は前の面の外側列の延長と、この面の
    外側列の手前の2本を、根がらみ＋各層（床レベル＋手すり＋中桟）に入れる。
    """
    udegi = rules.udegi_nominal or model.post_row_spacing_mm
    per_corner = 2 * (1 + n_levels * 3)
    add(m.find("布材", udegi), n_corners * per_corner, f"出隅コーナーの布材{udegi}")
    notes.append(
        f"出隅コーナー{n_corners}箇所は、外側コーナー支柱1本（支柱位置数に含む）と"
        f"呼び{udegi}mmの布材{per_corner}本（2辺×〈根がらみ1＋各層の床・手すり・中桟3〉×{n_levels}層）"
        "ずつで計上"
    )
    toe = m.find("幅木", udegi)
    if model.config.has_toe_board:
        add(toe, n_corners * n_levels * 2, f"出隅コーナーの幅木{udegi}")
    if toe is None and model.config.has_toe_board:
        notes.action(
            f"出隅コーナーの幅木（呼び{udegi}mm、{n_corners * n_levels * 2}本）がマスタにありません",
            Notes.ORDER,
        )
    # コーナーの床（{udegi}mm角）は踏板のセル数（スパン×層）には入れない。
    # 専用のコーナー踏板か隙間塞ぎで対応するので、手配として枚数を出す
    notes.action(
        f"外側コーナー{n_corners}箇所×{n_levels}層＝{n_corners * n_levels}枚のコーナー踏板"
        f"（{udegi}mm角）は踏板の数量に含んでいません（コーナー踏板または隙間塞ぎを別途手配）",
        Notes.ORDER,
    )


def _count_jacks(m: PartMaster, feet, rows: int, n_feet: int, add, notes, suffix: str = "") -> None:
    """ジャッキを脚ごとの繰出し量に合う品で数える.

    敷地に高低差があると脚ごとに繰出し量が違う。日建 ND752P は繰出し最大292mmで、
    それを超える脚はロング（ND752SP・432mm）が要る。平坦時の1品で全脚を数えると、
    ジャッキ量一覧では444mmと出ているのに数量は届かない品になっていた。
    繰出し上限の書いていない品（信和 SE-6 等）は従来どおり全脚をその品で数える。
    """
    jacks = [p for p in m.by_category("ジャッキ") if "アンダーベース" not in p.note]
    if not jacks:
        add(None, n_feet, "ジャッキ" + suffix)
        return
    ranked = sorted(jacks, key=lambda p: (p.max_extension_mm() is None, p.max_extension_mm() or 0))
    default = ranked[0]
    if not feet or all(p.max_extension_mm() is None for p in jacks):
        add(default, n_feet, "ジャッキ" + suffix)
        return
    # 脚ごとに、繰出し量を受けられる中で最も短い品。どれも届かない脚は最長の品で数え、
    # 差は敷板調整（ジャッキ量一覧の備考）として残る
    per_part: dict[str, int] = {}
    parts_by_no = {p.model_no: p for p in ranked}
    unreachable = 0
    for f in feet:
        need = float(getattr(f, "jack_mm", 0.0))
        fit = next((p for p in ranked
                    if p.max_extension_mm() is None or need <= p.max_extension_mm() + 1e-6), None)
        if fit is None:
            fit = ranked[-1]
            unreachable += 1
        per_part[fit.model_no] = per_part.get(fit.model_no, 0) + rows
    # 開口部で抜いた脚のぶんは、既定の品から引く（脚一覧には抜く前の脚も入っている）。
    # 脚一覧に無い脚（出隅の外側コーナー支柱）は既定の品で足す
    over = sum(per_part.values()) - n_feet
    if over > 0 and default.model_no in per_part:
        per_part[default.model_no] = max(0, per_part[default.model_no] - over)
    elif over < 0:
        per_part[default.model_no] = per_part.get(default.model_no, 0) - over
    for no, qty in per_part.items():
        p = parts_by_no[no]
        label = "ジャッキ" + suffix
        if p is not default:
            label = f"ジャッキ（繰出し{default.max_extension_mm()}mm超の脚: {p.model_no}）" + suffix
        add(p, qty, label)
    if unreachable:
        top = ranked[-1]
        notes.action(
            f"繰出し量がジャッキの上限{top.max_extension_mm()}mm（{top.model_no}）を超える脚が"
            f"{unreachable}箇所あります。敷板・床均しで下端を上げてください（ジャッキ量一覧の備考参照）",
            Notes.SITE,
        )


def _count_shims(m: PartMaster, feet, rows: int, add, notes) -> None:
    """敷板調整（ジャッキで届かない分を敷板で持ち上げる脚）の敷板を数える.

    高低差の解は「敷板でNNmm持ち上げる」を脚ごとに出すが、数量には載っていなかった。
    マスタの敷板（note の「厚35」）で枚数に換算する。敷板が無い系列は合計量を手配に出す。
    """
    raises = [(f, float(getattr(f, "base_plate_adjust_mm", 0.0))) for f in (feet or [])]
    raises = [(f, a) for f, a in raises if a > 1e-6]
    if not raises:
        return
    shim = next(iter(m.by_category("敷板")), None)
    thick = None
    if shim is not None:
        mt = re.search(r"厚\s*(\d+)", shim.note)
        thick = int(mt.group(1)) if mt else None
    if shim is None or not thick:
        total = sum(a for _, a in raises)
        notes.action(
            f"敷板調整が要る脚が{len(raises) * rows}本あります（合計{total * rows:.0f}mm相当）。"
            "敷板がマスタに無いので別途手配してください（ジャッキ量一覧の備考参照）",
        )
        return
    n = sum(math.ceil(a / thick - 1e-9) for _, a in raises) * rows
    add(shim, n, f"敷板調整（{len(raises) * rows}脚・厚{thick}mm換算）")
    notes.append(
        f"敷板調整の脚{len(raises) * rows}本に敷板{shim.model_no}（厚{thick}mm）を"
        f"計{n}枚で計上（脚ごとの調整量はジャッキ量一覧）"
    )


def _units_per_place(part: Part) -> int:
    """1箇所に何個要る部材か。マスタの note の「N個組」から読む（無ければ1）.

    例: 日建の朝顔受け金具 ALA7N は支柱1本に上下2個。品番は1つなので、
    数量表では箇所数×2で計上する。
    """
    m = re.search(r"(\d+)個組", part.note)
    return int(m.group(1)) if m else 1


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
    if asagao.kind == ASAGAO_KIND_SAFE_WING:
        _count_safe_wing_parts(model, span_counts, posts_per_line, add, notes)
        return
    panel = next((p for p in m.by_category("朝顔") if "防護棚" in p.note), None)
    bracket = next((p for p in m.by_category("朝顔") if "受けブラケット" in p.note), None)
    # 「方杖不要」と書いた本体を方杖として拾わない（実際に朝顔本体の行に
    # 方杖58本が足されていた）
    hozue = next((p for p in m.by_category("朝顔")
                  if "方杖" in p.note and "方杖不要" not in p.note), None)

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
            "現場で切り詰めるか、隙間を板・シートで塞いでください",
            Notes.SITE,
        )
    n_places = posts_per_line * asagao.stages
    if bracket is not None:
        add(bracket, n_places * _units_per_place(bracket), "朝顔受けブラケット")
    else:
        add(None, n_places, "朝顔受けブラケット")
    # 斜材を内蔵する朝顔（日建アルミ軽量アサガオ等）は方杖が要らない。
    # 「マスタに無い」と出すと別途手配させてしまう
    if hozue is None and panel is not None and "方杖不要" in panel.note:
        pass
    else:
        add(hozue, n_places, "朝顔方杖")

    # 出隅では2面の朝顔が突き合わず、隅に三角の隙間が残る（落下物が抜ける）。
    # 隅部はコーナー材で塞ぐ。マスタにあれば出隅×段数で計上、無ければ現場対応を出す
    corners = [c for c in model.plan.outline.corners if c.kind == "出隅"]
    if corners:
        corner_part = next((p for p in m.by_category("朝顔") if "コーナー" in p.note), None)
        if corner_part is not None:
            add(corner_part, len(corners) * asagao.stages, "朝顔コーナー（出隅）")
            notes.append(
                f"出隅{len(corners)}箇所×{asagao.stages}段の隅部は朝顔コーナー"
                f"（{corner_part.model_no}）で計上しています"
            )
        else:
            notes.action(
                f"出隅{len(corners)}箇所は朝顔が突き合わない隅部になります"
                f"（{asagao.stages}段ぶん）。隅角部の板・シート等で塞いでください"
                "（朝顔コーナーがマスタに無いため計上していません）",
                Notes.SITE,
            )

    # 取付部の壁つなぎは ties.merge_attachment_ties で格子と同じ一覧に入れて
    # 数える（図面にも出る。同じ位置の格子の金具で兼ねる分は二重に数えない）


def _count_safe_wing_parts(
    model: ScaffoldModel, span_counts: dict, posts_per_line: int, add, notes
) -> None:
    """信和セーフウイング（簡易落下物防止機材）の数量.

    資料（swg.pdf）: 張出1,280mm・25°、支柱ごとに1本（1スパンに2本）、張出部には
    SD-4018 なら3枚の踏板を敷く。キャッチャーB用も踏板はキャッチャー用（A系列）を使う
    指示なので、B系列ではマスタに無い＝手配項目に出す（黙って0枚にしない）。
    """
    asagao = model.config.asagao
    m = model.master
    wing = next((p for p in m.by_category("朝顔") if p.note.startswith("セーフウイング")), None)
    n_places = posts_per_line * asagao.stages
    if wing is None:
        add(None, n_places, f"セーフウイング（系列 {m.series_id} のマスタに無い）")
        return
    add(wing, n_places * _units_per_place(wing), "セーフウイング本体")
    missing: dict[int, int] = {}
    for sp, n in span_counts.items():
        deck = m.deck_parts(400, sp)
        qty = 3 * n * asagao.stages
        # マスタ note の「B用踏板は使用不可」= その系列の踏板を張出部に使わない指示
        if deck is None or "B用踏板は使用不可" in wing.note:
            missing[sp] = qty
            continue
        add(deck, qty, f"セーフウイング張出部の踏板{sp}（3枚/スパン）")
    if missing:
        notes.action(
            "セーフウイング張出部の踏板（幅400・3枚/スパン）が系列 "
            f"{m.series_id} のマスタにありません: "
            + "、".join(f"{sp}mm×{n}枚" for sp, n in sorted(missing.items()))
            + "。資料の指示どおりキャッチャー用踏板 SD-40xx を別途手配してください"
            "（Bタイプ用踏板は使用不可）",
        )
    corners = [c for c in model.plan.outline.corners if c.kind == "出隅"]
    if corners:
        notes.action(
            f"出隅{len(corners)}箇所はセーフウイングが突き合わない隅部になります"
            f"（{asagao.stages}段ぶん）。隅角部の板・シート等で塞いでください",
            Notes.SITE,
        )


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
            notes.action(f"方杖{qty}本が必要です（緊結部付ブラケット拡幅部）", Notes.SITE)
            continue
        # 定尺の一致→伸縮範囲、の順で当てる（PartMaster.bracket_for）
        part = m.bracket_for(width, outward=(purpose == "張出"))
        if part is not None and part.nominal_dim != width:
            notes.append(
                f"ブラケット{width}mm（{purpose}）は伸縮品 {part.model_no}"
                f"（{part.note.split()[0]}）を{width}mmに合わせて使う前提で計上"
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
    # 張出し区間の両端（妻側）も開放端。前面だけ手すりを立てても横から落ちる
    # （荷受けステージの妻側と同じ扱い。3Dも同じ位置に描く）
    from .brackets import OUTER as _OUTER
    for sec in bracket_sections or []:
        if sec.direction != _OUTER or sec.length_mm <= 0:
            continue
        n_lv = len(sec.levels) if sec.levels else model.elevation.n_levels
        w = int(sec.width)
        add(m.find("布材", w), 2 * 2 * n_lv, f"張出し妻側の手すり・中桟{w}")
        if model.config.has_toe_board:
            add(m.find("幅木", w), 2 * n_lv, f"張出し妻側の幅木{w}")

    # 区間で踏板幅を変える指定は、数量にも反映しないと現場で足りない
    for span, from_w, to_w, n_lv in bracket_deck_changes(model, bracket_sections):
        new_part = m.deck_parts(to_w, span)
        if new_part is None:
            notes.action(
                f"区間指定の踏板 幅{to_w}×{span}がマスタにありません"
                f"（{n_lv}枚）。幅{from_w}のままで計上しています",
                Notes.SITE,
            )
            continue
        old_part = m.deck_parts(from_w, span)
        if old_part is not None:
            okey = (old_part.model_no, old_part.category)
            counts[okey] = max(0, counts.get(okey, 0) - n_lv)
        add(new_part, n_lv, f"踏板 幅{to_w}×{span}（区間指定）")


def _count_opening_parts(model: ScaffoldModel, openings, add, notes) -> None:
    """開口部の梁枠を数量表に載せる.

    マスタに梁枠はあるのに、どこからも拾っていなかった。梁枠が要る計画で
    数量表に出てこないと、支柱を抜いた開口が受けられない。
    梁枠は内外の建地列それぞれに1枚（本足場は2枚、一側は1枚）。以前は開口部ごとに
    1枚で数えていて、後踏み側の梁枠が抜けていた。
    """
    if openings is None or not openings.openings:
        return
    m = model.master
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    saddles = m.by_category("梁渡し")
    for i, o in enumerate(openings.openings):
        part = next(
            (p for p in m.by_category("梁枠") if p.nominal_dim == o.beam_span_mm),
            None,
        )
        if part is None:
            notes.action(
                f"梁枠{o.beam_span_mm}mmがマスタにありません（{model.face_name(o.edge_index)}）。"
                "規格品の梁枠で計画し直してください"
            )
            continue
        add(part, rows, f"梁枠{o.beam_span_mm}（{model.face_name(o.edge_index)}・内外{rows}枚）")
        # 梁枠上に支柱を建てる系列（日建ND）は、内外の梁枠に渡す梁渡しに支柱を立てる。
        # 梁枠上の支柱1本（位置）に1個
        n_inner = len(openings.inner_posts.get(i, []))
        if saddles and n_inner and rows == 2:
            span = model.post_row_spacing_mm
            saddle = next((p for p in saddles if p.nominal_dim == span or p.covers(span)), None)
            if saddle is None:
                notes.action(
                    f"梁渡し{span}mm（建地列間隔）がマスタにありません（{model.face_name(o.edge_index)}・{n_inner}個）。"
                    "別途手配してください"
                )
            else:
                add(saddle, n_inner, f"梁渡し（{model.face_name(o.edge_index)}の梁枠上の支柱{n_inner}本）")
    if openings.removed_posts:
        vm = model.master.vertical_member_name
        # 補強・積載低減が要ることは openings.issues が開口部ごとに言う。
        # ここで同じ対応をもう一度挙げると要確認一覧に二重で並ぶ
        notes.append(
            f"開口部で{vm}{openings.removed_posts}本を抜いています。"
            f"梁枠の両端{vm}の補強の要否と梁枠上の積載制限は、構造計算（計算書4）の結果に従ってください"
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
                + (f"：{d.detail}" if d.detail else "")
            )
            continue
        add(cands[0], d.qty, d.label)

    for st in platforms.stages:
        if _bracket_nominal(model, st.projection_mm) is None:
            notes.action(
                f"{model.face_name(st.edge_index)}のステージは出{st.projection_mm:.0f}mmで、"
                "カタログの張出ブラケットでは受けられません。"
                "単管等による支持を個別に検討してください",
                Notes.SITE,
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


def _add_extra_negarami(model: ScaffoldModel, terrain, add, notes, rows: int) -> None:
    """敷地高低差で継ぎ足した脚の区間に入れる根がらみ（布材）を計上する."""
    if terrain is None:
        return
    from .terrain import extra_negarami

    m = model.master
    n_extra = 0
    for ep in model.plan.edges:
        for i, _level in extra_negarami(model, terrain).get(ep.edge_index, []):
            s = ep.spans[i]
            add(m.find("布材", s), rows, f"継ぎ足し部の根がらみ（布材{s}）")
            n_extra += rows
    if n_extra:
        notes.append(
            f"敷地高低差で継ぎ足した脚の区間に根がらみ（布材）{n_extra}本を追加しています"
            "（基準の根がらみが低い脚の地盤から離れるため。立面・3Dにも同じ高さで描いています）"
        )


CORNER_MARGIN_MM = 600.0   # 区間がこの範囲で面の端に接していれば、外側の残りはコーナーの離れ分


def bridged_extra_standoff_mm(model: ScaffoldModel, edge_index: int, position_mm: float) -> float:
    """渡した区間（凹み・張り出し・斜辺）の中で増える離れ（その位置での値）.

    凹みは区間で一定、斜辺は深い側で最大・反対側で0の線形。区間外は0。
    """
    extra = 0.0
    ep = next((e for e in model.plan.edges if e.edge_index == edge_index), None)
    length = float(ep.scaffold_length) if ep is not None else float("inf")
    for z in getattr(model.plan, "bridged_zones", None) or []:
        if z.edge_index != edge_index:
            continue
        deep = getattr(z, "deep_end", "uniform")
        width = max(z.end_mm - z.start_mm, 1e-9)
        # 斜辺の区間が面の端（コーナー）から始まる／で終わるとき、区間の外側に残る
        # コーナー支柱までの離れ分（0〜区間の始点）も深い側の値になる。コーナー支柱に
        # 通常長さの壁つなぎを付けていた（実機の立面で発見）
        if deep == "start" and position_mm < z.start_mm and z.start_mm <= CORNER_MARGIN_MM:
            extra = max(extra, z.depth_mm)
            continue
        if deep == "end" and position_mm > z.end_mm and z.end_mm >= length - CORNER_MARGIN_MM:
            extra = max(extra, z.depth_mm)
            continue
        if not (z.start_mm - 1e-6 <= position_mm <= z.end_mm + 1e-6):
            continue
        if deep == "end":
            v = z.depth_mm * (position_mm - z.start_mm) / width
        elif deep == "start":
            v = z.depth_mm * (z.end_mm - position_mm) / width
        else:
            v = z.depth_mm
        extra = max(extra, v)
    return extra


def wall_tie_required_length_mm(
    model: ScaffoldModel, edge_index: int, position_mm: Optional[float] = None
) -> float:
    """その面の壁つなぎに要る長さ（躯体面〜支柱芯＝離れ＋支柱半径）.

    position_mm を渡すと、渡した区間（凹み・斜辺）の中ではそこで増える離れを足す。
    区間の中の壁つなぎを面の離れで選ぶと、実際の躯体に届かない品を計上する。
    """
    standoff = float(model.plan.standoffs[edge_index]) if edge_index < len(model.plan.standoffs) else 0.0
    posts = model.master.by_category(model.master.vertical_member_name if not model.master.is_frame else "建枠")
    dia = next((p.diameter for p in posts if p.diameter > 0), 42.7)
    extra = bridged_extra_standoff_mm(model, edge_index, position_mm) if position_mm is not None else 0.0
    return standoff + extra + dia / 2.0


def _add_wall_ties(model: ScaffoldModel, platforms, kt, add, notes=None, openings=None) -> None:
    """壁つなぎを由来ごとに計上する（格子＋朝顔取付部＋ステージ取付部＋マスト控え）.

    取付部の分がまだ一覧に無ければここで統合する（take_off を単独で呼んでも
    数量が欠けないように。統合は何度呼んでも同じ結果）。

    伸縮範囲の違う壁つなぎが複数ある系列（日建 KS200/400/700）は、面ごとの離れに合う
    品を選ぶ。1品だけの系列は従来どおりその品で全数を数える。以前は日建で KS700
    （380〜760mm）だけを登録していて、離れ212mmの面にも KS700 を当てていた。
    """
    from .ties import has_attachment_ties, kind_labels, merge_attachment_ties, tie_counts

    labels = kind_labels(model)

    if not has_attachment_ties(model):
        merge_attachment_ties(model, platforms, openings)
    cands = [p for p in model.master.by_category("壁つなぎ") if p.adjustable_range()]
    # 1品だけでも伸縮範囲が書いてあれば、面の必要長さが範囲外なら手配項目に出す
    if not cands or kt is None:
        for kind, n in tie_counts(model).items():
            add(kt, n, labels.get(kind, kind))
        return
    cands.sort(key=lambda p: p.adjustable_range()[1])
    counts: dict[tuple[str, str], int] = {}
    parts = {p.model_no: p for p in cands}
    uncovered: dict[int, tuple[int, Part, int]] = {}   # 辺 -> (本数, 当てた品, 範囲までの差mm)
    unreachable: dict[int, tuple[int, int]] = {}       # 辺 -> (本数, 最大の必要長さ)
    by_face: dict[int, dict[str, int]] = {}            # 辺 -> {品番: 本数}
    longest = max(p.adjustable_range()[1] for p in cands)
    for t in model.wall_ties:
        need = int(round(wall_tie_required_length_mm(model, t.edge_index, t.position_mm)))
        fit = next((p for p in cands if p.covers(need)), None)
        if fit is None and need > longest:
            # 渡した区間（凹み・斜辺）の中で、最長の壁つなぎでも躯体に届かない位置。
            # 本数は図面と合わせて最長品で計上し、別途の控えを名指しで出す
            fit = cands[-1]
            n, mx = unreachable.get(t.edge_index, (0, 0))
            unreachable[t.edge_index] = (n + 1, max(mx, need))
        if fit is None:
            # 範囲の隙間（日建 KS200 160〜240 と KS400 250〜420 の間の 241〜249 など）に
            # 落ちた面は、いちばん近い範囲の品を当てる。以前は既定品（最長の KS700）に
            # 落としていて、245mm の面に 380〜760mm の壁つなぎを載せていた
            def gap(p):
                lo, hi = p.adjustable_range()
                return lo - need if need < lo else need - hi

            # 同じ差なら長い側（最短が need を超える品）。短い側は届かないが、
            # 長い側は離れを数mm広げれば納まる
            fit = min(cands, key=lambda p: (gap(p), 0 if p.adjustable_range()[0] > need else 1))
            n, _, _ = uncovered.get(t.edge_index, (0, fit, 0))
            uncovered[t.edge_index] = (n + 1, fit, gap(fit))
        parts[fit.model_no] = fit
        key = (fit.model_no, t.kind)
        counts[key] = counts.get(key, 0) + 1
        by_face.setdefault(t.edge_index, {})
        by_face[t.edge_index][fit.model_no] = by_face[t.edge_index].get(fit.model_no, 0) + 1
    for (no, kind), n in counts.items():
        add(parts[no], n, labels.get(kind, kind))
    # 面ごとの本数と品番。壁つなぎは離れで品番が面ごとに変わるので、行の合計だけでは
    # どの面に何本持って行くか分からない
    if by_face and notes is not None:
        face_txt = "／".join(
            f"{model.face_name(e)} {sum(m.values())}本（"
            + "・".join(f"{no} {n}" for no, n in sorted(m.items(), key=lambda kv: -kv[1])) + "）"
            for e, m in sorted(by_face.items())
        )
        notes.append(f"壁つなぎの面別本数: {face_txt}")
    if unreachable and notes is not None and hasattr(notes, "action"):
        faces = "・".join(
            f"{model.face_name(e)} {n}本（最大 要{mx}mm）" for e, (n, mx) in sorted(unreachable.items())
        )
        notes.action(
            f"渡した区間（凹み・斜辺）の中の壁つなぎは離れが増え、最長の壁つなぎ"
            f"（{cands[-1].model_no} 〜{longest}mm）でも躯体に届きません: {faces}。"
            "その位置は単管等で躯体まで控えを取るか、区間の外の支柱へ壁つなぎを移してください"
            "（数量は最長品で計上しています）"
        )
    if uncovered and notes is not None and hasattr(notes, "action"):
        faces = "・".join(
            f"{model.face_name(e)}（要{wall_tie_required_length_mm(model, e):.0f}mm・{n}本、"
            f"{p.model_no} {p.adjustable_range()[0]}〜{p.adjustable_range()[1]}mm まで{g}mm）"
            for e, (n, p, g) in sorted(uncovered.items())
        )
        notes.action(
            f"壁つなぎの伸縮範囲に合う品が無い面があります: {faces}。いちばん近い範囲の品で計上して"
            "いますが、離れを範囲内に調整するか、取付金具側で差を吸収できるか確認してください"
        )


def _replace_opening_stacks(model, openings, totals: dict[int, int], full_stack: list[int],
                            lengths: list[int], notes, label: str) -> int:
    """開口部で抜いた鉛直部材を、梁枠上（作業床〜天端）だけの構成に置き換える.

    totals（呼び寸法→本数）を書き換える。戻り値は縦継ぎ箇所数の増減（枠組の連結ピン用）。
    組める構成が無い高さは全高のまま残し、要確認に出す。
    """
    from .elevation_solver import _compose_table
    from .openings import opening_post_heights

    heights = opening_post_heights(model, openings)
    if not heights or not lengths:
        return 0
    table = _compose_table(int(round(max(heights))) + 1, sorted(set(lengths), reverse=True))
    replaced = 0
    joints_delta = 0
    missing: list[float] = []
    done: dict[int, int] = {}
    for h in heights:
        comp = table.get(int(round(h)))
        if comp is None:
            missing.append(h)
            continue
        for nominal in full_stack:
            totals[nominal] = totals.get(nominal, 0) - 1
        for nominal in comp:
            totals[nominal] = totals.get(nominal, 0) + 1
        joints_delta += (len(comp) - 1) - (len(full_stack) - 1)
        done[int(round(h))] = done.get(int(round(h)), 0) + 1
        replaced += 1
    for k in [k for k, v in totals.items() if v <= 0]:
        del totals[k]
    if replaced:
        notes.append(
            f"開口部で抜いた{label}{replaced}本は梁枠上（作業床〜天端）の構成で計上しています（"
            + "、".join(f"高さ{h}mm×{n}本" for h, n in sorted(done.items())) + "）"
        )
    if missing:
        notes.action(
            f"開口部の梁枠上に乗る{label}{len(missing)}本は、規格の長さでは高さ"
            f"{'・'.join(f'{h:.0f}' for h in sorted(set(missing)))}mmに組めないため全高で計上しています。"
            "梁枠の位置か支柱規格を見直してください",
            Notes.ORDER,
        )
    return joints_delta


def _note_deck_cells(notes, name: str, n_spans: int, n_levels: int,
                     stair_cut: int, n_towers: int, open_cut: int, final: int) -> None:
    """作業床の枚数の検算メモ。スパン×層から何をいくつ引いたかを書く.

    布材には1スパンあたりの内訳があるのに、踏板は本数だけで、
    「スパン×層」より少ない理由（階段室・開口部）が読み手に分からなかった。
    """
    base = n_spans * n_levels
    text = f"{name}はスパン{n_spans}×作業層{n_levels}層＝{base}セル"
    cuts = []
    if stair_cut:
        cuts.append(f"階段室{n_towers}箇所の{stair_cut}セル")
    if open_cut:
        cuts.append(f"開口部（梁枠より下）の{open_cut}セル")
    if cuts:
        text += "から" + "と".join(cuts) + f"を差し引いた{final}セル"
    notes.append(text + "で計上（幅ごとに同数）")


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
    # 建地2本組は単管足場（安衛則571条）の概念。枠組足場は対象外で、
    # 高さがある場合は最下段建枠・ジャッキベースの強度検討で対応する
    # （法規チェック8が枠組用の文面を出す）。ここで2本組を数えると誤り
    if model.master.is_frame:
        return
    below = h - DOUBLE_POST_HEIGHT_MM
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    lines = model.plan.total_posts * rows
    notes.action(
        f"足場高さ{h / 1000:.2f}mは31mを超えます。最高部から31mを超える部分"
        f"（GL〜{below / 1000:.2f}m）の建地は2本組が必要ですが、追加の支柱・"
        f"ジャッキは数量に含んでいません（該当は支柱{lines}本ぶん）。"
        "建地下端の設計荷重が最大使用荷重以内と確認できる場合は除外できます",
        Notes.SITE,
    )


def _note_bridged_zones(model: ScaffoldModel, notes) -> None:
    """直線で渡した凹み・張り出しの区間は離れが増える。措置の部材を本数で出す.

    どちらの措置（内ブラケットでの床の拡幅／躯体側手すり）を取るかは現場判断
    なので自動では計上しないが、区間・スパン数・本数まで書いて手配できるようにする。
    """
    zones = getattr(model.plan, "bridged_zones", None) or []
    if not zones:
        return
    n_levels = model.elevation.n_levels
    for z in zones:
        posts = z.span_count + 1
        brackets = posts * n_levels
        rails = z.span_count * n_levels * 2      # 手すり＋中桟
        deep = getattr(z, "deep_end", "uniform")
        how = (f"躯体との離れが{'終点' if deep == 'end' else '始点'}側で最大{z.depth_mm:.0f}mm増えます"
               f"（斜辺に沿って0から線形に増加）" if z.kind == "斜辺"
               else f"躯体との離れが{z.depth_mm:.0f}mm増えます")
        inner_counted = (model.config.inner_guard_rail and not model.master.is_frame
                         and model.config.scaffold_form != "一側足場")
        rail_text = (f"躯体側手すり（布材{rails}本）は計上済み" if inner_counted
                     else f"躯体側手すりで対応する場合 布材{rails}本（手すり・中桟）は数量に含んでいません")
        notes.action(
            f"{z.kind}を渡した区間（{model.face_name(z.edge_index)} 始点から"
            f"{z.start_mm:.0f}〜{z.end_mm:.0f}mm・{z.span_count}スパン×{n_levels}層）は"
            f"{how}。内ブラケットで床を拡幅する場合 内ブラケット{brackets}本（{posts}位置×{n_levels}層）と"
            f"その踏板は数量に含んでいません。{rail_text}",
            Notes.ORDER,
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
    if model.config.inner_guard_rail and not model.master.is_frame \
            and model.config.scaffold_form != "一側足場":
        return    # 躯体側の手すり・中桟は布材として計上済み
    spans = sum(w[2] for w in wide)
    faces = "、".join(f"{model.face_name(i)} {d:.0f}mm" for i, d, _ in wide)
    # 措置が要ること自体は割付の警告が言う。ここは数量側の話に絞る
    notes.action(
        f"離れが300mmを超える面（{faces}）の躯体側手すり材は数量に含んでいません"
        f"（該当{spans}スパン）。躯体側手すりで対応する場合は布材を別途計上してください",
        Notes.SITE,
    )


def _assemble(
    model: ScaffoldModel,
    rules: QuantityRules,
    counts: dict[str, int],
    parts: dict[str, Part],
    notes: list[str],
    breakdown: Optional[dict[str, dict[str, int]]] = None,
) -> QuantityResult:
    """集計結果を QuantityResult に組み立てる（くさび式・枠組式で共通）."""
    breakdown = breakdown or {}
    # 型番仮（カタログに該当が無く仮の品番・概算重量）の部材は、実品番と同じ顔で
    # 発注書に載せない。手配項目として名指しで出す
    provisional = sorted(
        {p.model_no for k, p in parts.items() if "型番仮" in p.note and counts.get(k, 0) > 0}
    )
    if provisional and hasattr(notes, "action"):
        notes.action(
            "型番仮の部材があります（カタログ未照合の仮品番・概算重量）: "
            + "・".join(provisional)
            + "。発注前に実品番と重量をマスタ（part_master.csv）で差し替えてください"
        )
    lines = []
    for k, v in sorted(counts.items()):
        # 同じ型番が2つ以上の用途で足された行は、備考に用途別の内訳を出す。
        # 図面に出るのは躯体ぶんだけなので、照合できるよう本数を分けて書く
        by = breakdown.get(k, {})
        detail = ""
        if len(by) >= 2:
            detail = "内訳: " + "／".join(
                f"{lbl} {n}本" for lbl, n in sorted(by.items(), key=lambda x: -x[1])
            )
        lines.append(BomLine(part=parts[k], qty=v, note=detail))
    total_weight = sum(l.subtotal_weight for l in lines)

    # ---- 架け面積: (建物外周+4m)×(建物高さ+0.5m) ----
    perimeter_m = model.plan.outline.perimeter / 1000.0
    height_m = (model.building_height_mm or model.scaffold_height_mm) / 1000.0
    kake = (perimeter_m + 4.0) * (height_m + 0.5)

    # 台数だけ出しても検算できない。1台あたりの実効積載を書く
    notes.append(
        f"トラック台数は1台あたり{rules.truck_payload_kg:.0f}kg"
        "（4t車の実効積載・積載効率0.8）で割った概算です。"
        "長尺材の積み方や現場条件で変わります"
    )
    return QuantityResult(
        lines=lines,
        kake_menseki_m2=round(kake, 2),
        total_weight_kg=round(total_weight, 1),
        truck_count=math.ceil(total_weight / rules.truck_payload_kg) if total_weight else 0,
        notes=list(notes),
        warnings=list(getattr(notes, "actions", [])),
        warning_kinds=dict(getattr(notes, "kinds", {})),
    )


def _count_frame_parts(
    model: ScaffoldModel,
    rules: QuantityRules,
    add,
    notes: list[str],
    stair_plan=None,
    openings=None,
    terrain=None,
    platforms=None,
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
    # 高低差のある敷地では低い側の脚に調整枠を継ぎ足す。名目の段数×位置数の
    # ままだと、その建枠と連結ピンが数量から抜ける
    feet = list(getattr(terrain, "feet", []) or [])
    if feet:
        for f in feet:
            for h in f.posts:
                stage_counts[h] = stage_counts.get(h, 0) + 1
        extra = sum(len(f.posts) - len(elev.posts) for f in feet)
        if extra > 0:
            notes.append(
                f"敷地高低差の継ぎ足し分として建枠{extra}枚を含みます"
                "（脚ごとの構成はジャッキ量一覧のとおり。立面図・3Dも脚ごとの地盤高で描いています）"
            )
    else:
        for h in elev.posts:
            stage_counts[h] = stage_counts.get(h, 0) + 1
    # 建枠幅は「近い幅」ではなく「布板が載る最小幅」を選ぶ
    # （近似で選ぶと布板より狭い建枠になり、実際には組めない）
    need_width = model.deck_width_total
    frame_width, fits = m.frame_width_for(need_width)
    if not fits:
        notes.action(
            f"布板幅の合計{need_width}mmに対し建枠幅が不足しています"
            f"（最大{frame_width}mm）。布板構成か建枠規格を見直してください",
            Notes.SITE,
        )
    totals_frames = {k: v * (1 if feet else n_frame_lines) for k, v in stage_counts.items()}
    # 開口部で抜いた建枠は梁枠上（作業床〜天端）だけの段数に置き換える
    joints_delta = _replace_opening_stacks(
        model, openings, totals_frames, list(elev.posts), m.frame_heights(), notes, "建枠",
    )
    for h, total in totals_frames.items():
        part = next(
            (p for p in m.by_category("建枠")
             if p.nominal_dim == h and f"幅{frame_width}" in p.note),
            None,
        )
        add(part, total, f"建枠 幅{frame_width}×高{h}")

    # ---- ジャッキ・アンダーベース ----
    under = next((p for p in m.by_category("ジャッキ") if "アンダーベース" in p.note), None)
    # 建枠は1枚で2脚（内外の建地を兼ねる）。建枠の枚数で数えると脚が半分になり、
    # 現場でジャッキが足りなくなる
    n_frame_legs = n_frame_lines * rules.rows
    # 開口部で抜いた建枠は地面に達しない。その脚のジャッキ・アンダーベースは要らない
    # （くさび経路は控除していたのに、枠組経路だけ全脚で数えていた）
    removed_legs = openings.removed_posts if openings is not None else 0
    _count_jacks(m, feet, rules.rows, max(0, n_frame_legs - removed_legs), add, notes,
                 "（建枠1枚に2脚）")
    add(under, max(0, n_frame_legs - removed_legs), "アンダーベース（建枠1枚に2脚）")
    _count_shims(m, feet, rules.rows, add, notes)

    # ---- 布板（作業床）。階段枠の区間には敷かない ----
    span_counts: dict[int, int] = {}
    for e in plan.edges:
        for s in e.spans:
            span_counts[s] = span_counts.get(s, 0) + 1
    # くさびの踏板と同じくセル（スパン×層）で数える。開口部（梁枠より下）は
    # 通路で床が無い。図面は空けているのに数量だけ数えていた
    from .openings import opening_deck_deduction
    open_cut = opening_deck_deduction(model, openings)
    deck_cells = {s: n * n_levels for s, n in span_counts.items()}
    for s, cells in open_cut.items():
        deck_cells[s] = max(0, deck_cells.get(s, 0) - cells)
    stair_cut_cells = 0
    if stair_plan is not None and stair_plan.towers:
        from .stairs import stair_deck_deduction
        for s, n in stair_deck_deduction(model, stair_plan).items():
            deck_cells[s] = max(0, deck_cells.get(s, 0) - n * n_levels)
            stair_cut_cells += n * n_levels
    _note_deck_cells(
        notes, m.deck_category, sum(span_counts.values()), n_levels,
        stair_cut_cells, len(stair_plan.towers) if stair_plan else 0,
        sum(open_cut.values()), sum(deck_cells.values()),
    )
    for w in model.config.deck_widths:
        for s, cells in deck_cells.items():
            part = next(
                (p for p in m.by_category("布板")
                 if p.nominal_dim == s and f"幅{w}" in p.note),
                None,
            )
            add(part, cells, f"布板 幅{w}×{s}")

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
    n_joints = (sum(max(0, len(f.posts) - 1) for f in feet) if feet
                else max(0, n_stages - 1) * n_frame_lines) + joints_delta
    add(pin, max(0, n_joints), "連結ピン（縦継ぎ1箇所に1本）")

    # 継ぎ足した脚（調整枠）の区間の根がらみ（敷地高低差）。建枠の両脚に入るので2本
    _add_extra_negarami(model, terrain, add, notes, 2)

    # ---- 幅木・壁つなぎ・階段枠 ----
    if model.config.has_toe_board:
        # 開口部（梁枠より下）は床が無いので幅木も無い（階段室の外構面には残す）
        for s, n in span_counts.items():
            add(m.find("幅木", s), max(0, n * n_levels - open_cut.get(s, 0)), f"幅木{s}")
    kt = next(iter(m.by_category("壁つなぎ")), None)
    _add_wall_ties(model, platforms, kt, add, notes, openings=openings)
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
