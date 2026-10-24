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
    # 作業層あたり床レベルのスパン方向の布材。くさび式ではアンチ（踏板）は腕木に掛けるので付けない
    # （以前は内外2本を数えて3Dにも描いていた。2026-10-18 利用者の指摘）
    ledgers_per_level_floor: int = 0
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
    """数量拾い。面ごとに高さが違えば（セットバック）、同じ高さの面の組ごとに拾って合わせる."""
    rules = rules or QuantityRules()
    res = _take_off_groups(model, rules, bracket_sections, stair_plan, platforms, openings, terrain)
    if getattr(model, "member_edits", None):
        # 範囲を指定した部材の編集（外す・置換）。全体の計画で升目を数えて効かせる
        from .member_edits import apply_member_edits

        res = apply_member_edits(res, model, rules, openings=openings, stair_plan=stair_plan)
    return res


def _take_off_groups(model, rules, bracket_sections, stair_plan, platforms, openings, terrain) -> QuantityResult:
    groups = face_height_groups(model)
    if len(groups) <= 1:
        return _take_off_one(model, rules, bracket_sections, stair_plan, platforms, openings, terrain)
    names = model.plan.face_names()
    by_edge = {e.edge_index: n for e, n in zip(model.plan.edges, names)}
    results = []
    for ev, edges in groups:
        sub = _sub_model(model, ev, edges)
        label = "・".join(by_edge.get(i, f"辺{i}") for i in sorted(edges)) + f"（{ev.n_levels}層）"
        q = _take_off_one(sub, rules, _only_edges(bracket_sections, edges), _sub_stairs(stair_plan, edges),
                          _sub_platforms(platforms, edges), _sub_openings(openings, edges),
                          _sub_terrain(terrain, model, edges))
        results.append((label, q))
    res = _merge_results(model, rules, results)
    if _sub_terrain(terrain, model, set()) is not None:
        res.notes.append("敷地の高低差とセットバック（面ごとの高さ）が両方あるので、脚（ジャッキ・継ぎ足しの支柱）は"
                         "面ごとに近い脚を割り当てて全高の構成で拾っています。低い面の脚の支柱構成は要確認です")
    return res


def face_height_groups(model: ScaffoldModel) -> list[tuple]:
    """面を立面（高さ）ごとにまとめる [(立面, {辺番号})]。高い順."""
    groups: dict[int, tuple] = {}
    for e in model.plan.edges:
        ev = model.elevation_of(e.edge_index)
        key = id(ev)
        groups.setdefault(key, (ev, set()))[1].add(e.edge_index)
    return sorted(groups.values(), key=lambda g: -g[0].n_levels)


def _sub_model(model: ScaffoldModel, ev, edges: set) -> ScaffoldModel:
    import copy
    import dataclasses

    sub = copy.copy(model)
    sub.plan = dataclasses.replace(model.plan, edges=[e for e in model.plan.edges if e.edge_index in edges])
    sub.elevation = ev
    sub.face_elevations = {}
    sub.edge_subset = set(edges)
    sub.wall_ties = [t for t in model.wall_ties if t.edge_index in edges]
    return sub


def _only_edges(items, edges: set):
    if items is None:
        return None
    return [x for x in items if getattr(x, "edge_index", None) in edges]


def _sub_terrain(terrain, model: ScaffoldModel, edges: set):
    """敷地の脚を面の組に分ける。平坦なら None（脚ごとの構成は要らない。全周の脚を各組で数えると二重になる）."""
    if terrain is None:
        return None
    lo, hi = getattr(terrain, "gl_range_mm", (0.0, 0.0)) or (0.0, 0.0)
    if abs(float(hi) - float(lo)) < 1.0:
        return None
    if not edges:
        return terrain
    import dataclasses

    def nearest(f) -> int:
        best, bi = None, -1
        for e in model.plan.edges:
            (sx, sy), (ex, ey) = e.start_post, e.end_post
            dx, dy = ex - sx, ey - sy
            L2 = dx * dx + dy * dy or 1.0
            t = max(0.0, min(1.0, ((f.x - sx) * dx + (f.y - sy) * dy) / L2))
            d = (f.x - sx - t * dx) ** 2 + (f.y - sy - t * dy) ** 2
            if best is None or d < best:
                best, bi = d, e.edge_index
        return bi

    return dataclasses.replace(terrain, feet=[f for f in terrain.feet if nearest(f) in edges],
                               feet_outer=[f for f in getattr(terrain, "feet_outer", []) if nearest(f) in edges])


def _feet_by_row(terrain, rows: int) -> tuple[list, int]:
    """数える脚と倍数。外側の列も地盤から解いてあれば内外の脚をそのまま（倍数1）、無ければ内側の列×列数."""
    feet = list(getattr(terrain, "feet", []) or [])
    outer = list(getattr(terrain, "feet_outer", []) or [])
    if feet and outer:
        return feet + outer, 1
    return feet, rows


def _sub_stairs(stair_plan, edges: set):
    if stair_plan is None:
        return None
    import dataclasses
    sub = dataclasses.replace(stair_plan, towers=[t for t in stair_plan.towers if t.edge_index in edges])
    # 建物に階段があって、この面の組には無い → 0箇所（設定の既定の箇所数に戻さない）
    sub.subset = bool(stair_plan.towers)
    return sub


def _sub_platforms(platforms, edges: set):
    if platforms is None:
        return None
    import dataclasses
    return dataclasses.replace(platforms, stages=_only_edges(platforms.stages, edges),
                               hoists=_only_edges(platforms.hoists, edges))


def _sub_openings(openings, edges: set):
    if openings is None:
        return None
    import dataclasses
    return dataclasses.replace(openings, openings=_only_edges(openings.openings, edges))


def _merge_results(model: ScaffoldModel, rules: QuantityRules, results: list) -> QuantityResult:
    """面の組ごとの数量を合わせる（同じ品番・分類は足す）。注記は組の名前を付けて並べる."""
    merged: dict = {}
    order: list = []
    for _label, q in results:
        for ln in q.lines:
            key = (ln.part.model_no, ln.part.category)
            if key not in merged:
                merged[key] = BomLine(part=ln.part, qty=0, note="")
                order.append(key)
            merged[key].qty += ln.qty
    lines = [merged[k] for k in sorted(order)]
    total_weight = sum(l.subtotal_weight for l in lines)
    notes: list[str] = [
        "面ごとに高さが違うので（スラブの天端から。セットバック）、同じ高さの面の組ごとに拾って合わせています: "
        + "／".join(label for label, _q in results)]
    warnings: list[str] = []
    kinds: dict = {}
    for label, q in results:
        for n in q.notes:
            if n.startswith("トラック台数"):
                continue
            notes.append(f"【{label}】{n}")
        for w in q.warnings:
            if w not in warnings:
                warnings.append(w)
                kinds[w] = q.warning_kinds.get(w, Notes.ORDER)
    notes.append(f"トラック台数は1台あたり{rules.truck_payload_kg:.0f}kg（4t車の実効積載・積載効率0.8）で割った概算です。"
                 "長尺材の積み方や現場条件で変わります")
    perimeter_m = model.plan.outline.perimeter / 1000.0
    height_m = (model.building_height_mm or model.scaffold_height_mm) / 1000.0
    kake = (perimeter_m + 4.0) * (height_m + 0.5)
    return QuantityResult(lines=lines, kake_menseki_m2=round(kake, 2), total_weight_kg=round(total_weight, 1),
                          truck_count=math.ceil(total_weight / rules.truck_payload_kg) if total_weight else 0,
                          notes=notes, warnings=warnings, warning_kinds=kinds)


def _take_off_one(
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
        _note_inner_rail_if_wide(model, notes, bracket_sections)
        _note_bridged_zones(model, notes)
        _note_double_posts_if_tall(model, notes)
        return _assemble(model, rules, counts, parts, notes, breakdown)

    # ---- 支柱（1支柱位置あたりの積み上げ構成×位置数、内外同一構成） ----
    # 敷地に高低差があると、低い側の脚は下へ支柱を継ぎ足す。名目構成×位置数の
    # ままだと、その分の支柱が数量から抜ける（ジャッキ量一覧には出ているのに）
    counts_posts: dict[int, int] = {}
    # 外側の列も地盤から解いてあれば、内外の脚を1本ずつ数える（倍数1）
    feet, per_foot = _feet_by_row(terrain, rows)
    extra_posts = 0
    if feet:
        for f in feet:
            for nominal in f.posts:
                counts_posts[nominal] = counts_posts.get(nominal, 0) + 1
        extra_posts = sum(len(f.posts) - len(elev.posts) for f in feet) * per_foot
        if extra_posts > 0:
            notes.append(
                f"敷地高低差の継ぎ足し分として{model.master.vertical_member_name}"
                f"{extra_posts}本を含みます（脚ごとの構成はジャッキ量一覧のとおり。"
                "立面図・3Dも脚ごとの地盤高で描いています）"
            )
    else:
        for nominal in elev.posts:
            counts_posts[nominal] = counts_posts.get(nominal, 0) + 1
    totals_posts = {k: v * (per_foot if feet else n_posts) for k, v in counts_posts.items()}
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
    _count_jacks(m, feet, per_foot, n_feet, add, notes)
    add(under, n_feet, "アンダーベース")
    _count_shims(m, feet, per_foot, add, notes)
    # 支柱最下部にだけ付く附属品（日建NDの下部カラー材など）。脚の数だけ
    for p in m.by_category("支柱附属"):
        if "最下部" in p.note:
            add(p, n_feet * _units_per_place(p), f"{p.model_no}（支柱最下部）")
        elif "継ぎ目" in p.note:
            # 支柱を継ぐ金具（NDストロングの NSジョイント）。支柱の継ぎ目ごとに1個
            add(p, n_feet * max(0, len(elev.posts) - 1), f"{p.model_no}（支柱の継ぎ目）")

    # ---- 布材（スパン方向: 根がらみ＋床レベル＋手すり・中桟） ----
    # 手すり方式で外側の手すり・中桟の拾い方が変わる。
    # 先行手すり工法は専用部材（手すり＋斜材が一体）が布材2本を置き換える
    advance_rail = model.config.guard_rail_type == GUARD_RAIL_ADVANCE
    rails_outer = 0 if advance_rail else rules.rails_per_level_outer
    # 根がらみ・床レベルの布材は建地列ごとに1本。一側足場は建地1列なので
    # 本足場の「内外2本」のまま数えると1スパンあたり5本（4層で）多くなる
    negarami_n = min(rules.ledgers_negarami, rows)
    floor_n = min(rules.ledgers_per_level_floor, rows)
    # 単管抱き足場は各層の床の高さに、建地を両側から抱く布を2本（その上に足場板）
    if model.config.is_hug:
        floor_n = 2
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
    # 足場の中の階段室は外側の手すり（上の段の布材）を付けず、中桟だけ残す（階段手すり 2段が沿う。利用者の指定
    # 2026-10-24: 階段のところは布材不要、階段の1段目の布材だけある）。1セルあたり 1本
    from .stairs import stair_rail_cells
    stair_rail = stair_rail_cells(model, stair_plan, n_levels) if (stair_plan is not None and rails_outer) else {}
    # 差し引く布材は理由ごとに数えて注記する（以前は全部を「開口部」の本数として書いていた。
    # 開口部の無い計画で内ブラケットの手すり外しが「開口部の布材928本」と出ていた）
    open_rail_cut = stage_rail_cut = inner_rail_cut = 0
    for s, n in span_counts.items():
        c_open = open_cut.get(s, 0) * per_level_rails + open_spans.get(s, 0) * negarami_n
        c_stage = stage_cells.get(s, 0) * rails_outer
        c_inner = inner_cut_cells.get(s, 0) * rails_inner
        c_stage += stair_rail.get(s, 0)                         # 階段室の外側の手すり（別に注記する）
        open_rail_cut += c_open
        stage_rail_cut += c_stage - stair_rail.get(s, 0)
        inner_rail_cut += c_inner
        if not m.is_tube:
            add(m.find("布材", s), max(0, n * per_span_rails - c_open - c_stage - c_inner), f"布材{s}")
    stair_rail_cut = sum(stair_rail.values())
    # 単管は布・手すり・中桟・根がらみを規定の長さの単管で面の端から端まで通し、直線ジョイントで継ぐ
    # （スパンごとの1本ではない。利用者の指定 2026-10-22）
    tube_stats = (_count_tube_runs(model, per_span_rails, n_levels, add, notes,
                                   open_rail_cut + stage_rail_cut + inner_rail_cut + stair_rail_cut)
                  if m.is_tube else None)
    if stair_rail:
        notes.append(
            f"足場の中の階段室（{sum(stair_rail.values())}スパン×層）は階段手すり（2段）が外側に沿うので、外側の"
            f"手すり（布材{sum(stair_rail.values())}本）は付けず、中桟だけ残しています")
    if inner_cut_cells:
        notes.append(
            f"内ブラケットで床を拡幅した区間（{sum(inner_cut_cells.values())}スパン×層）は躯体との隙間が"
            f"小さくなるので、躯体側の手すり・中桟（布材{inner_rail_cut}本）を外しています"
        )
    if stage_cells and (rails_outer or advance_rail):
        notes.append(
            f"荷受けステージの間口・昇降機の乗り込み口・張出しブラケット区間（計{sum(stage_cells.values())}スパン×層"
            + (f"・布材{stage_rail_cut}本" if stage_rail_cut else "") + "）は本体の"
            + ("外側の手すり・中桟" if rails_outer else "先行手摺")
            + ("・幅木" if model.config.has_toe_board else "")
            + "を外しています（ステージの先端・妻側の手すり／乗り込み口の開閉式手すり／張出し外縁の手すりで防護）"
        )
    # 本数だけ出しても検算できない。1スパンあたりの内訳を書く
    per_level_parts = ([f"床レベル{floor_n}本"] if floor_n else []) + [
        f"外側の手すり・中桟{rails_outer}本" if rails_outer else "外側の手すりは先行手摺"]
    if rails_inner:
        per_level_parts.append(f"躯体側の手すり・中桟{rails_inner}本")
    notes.append(
        f"布材は1スパンあたり 根がらみ{negarami_n}本＋各層（" + "＋".join(per_level_parts)
        + f"）×{n_levels}層 ＝ {per_span_rails}本で計上"
        + ("（作業床の高さのスパン方向の布材は付けない。アンチは腕木に掛ける）" if not floor_n else "")
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
    stair_cells: dict[int, int] = {}
    if stair_plan is not None and stair_plan.towers and not getattr(stair_plan, "outside", False):
        # 階段室は各層で階段が上がってくる1スパンだけ開口（もう一方のスパンには床を敷く）。外側の幅木も付けない
        # （載せる布板が無く宙に浮く。利用者の指摘 2026-10-22。階段上の幅木も付けない 2026-10-24）
        from .stairs import stair_open_cells
        stair_cells = stair_open_cells(model, stair_plan, n_levels)
        for s, n in stair_cells.items():
            deck_cells[s] = max(0, deck_cells.get(s, 0) - n)
            stair_cut_cells += n
            if not m.is_tube:
                toe_cells[s] = max(0, toe_cells.get(s, 0) - n)
    if model.deck_widths_in_use:         # 単管抱き足場は床材が無い（抱き合わせた単管2本）
        _note_deck_cells(
            notes, m.deck_category, sum(span_counts.values()), n_levels,
            stair_cut_cells, len(stair_plan.towers) if stair_plan else 0,
            sum(open_cut.values()), sum(deck_cells.values()),
        )
    # 一側足場は建地1列で、作業床はブラケット受けの1枚敷き。本足場の内外2枚敷きを
    # そのまま数えると踏板が倍になる（実際、重量で3.7t多く出ていた）
    deck_widths = list(model.deck_widths_in_use)
    if rows == 1 and deck_widths and len(model.config.deck_widths) > len(deck_widths):
        notes.append(
            f"一側足場のため作業床は幅{deck_widths[0]}mmの1枚敷きで計上しています"
            f"（本足場の{'+'.join(str(w) for w in model.config.deck_widths)}ではなく）"
        )
    if m.is_tube and deck_widths:
        # 単管のブラケット足場の足場板は規定の長さで面に沿って敷き、継ぎは300重ねる（スパンごとの1枚ではない）
        _count_tube_boards(model, deck_widths, n_levels, add, notes,
                           sum(n * n_levels for n in span_counts.values()) - sum(deck_cells.values()))
    else:
        half = model.stair_half_deck and bool(stair_cells)
        # ハッチ付布板（梯子内蔵）の昇降口: そのスパンの同じ幅の踏板を各層ハッチ付布板に替える
        from .stairs import hatch_part

        hp, hw = hatch_part(model)
        mine = {e.edge_index: e for e in model.plan.edges
                if model.edge_subset is None or e.edge_index in model.edge_subset}
        hatch_cells: dict[int, int] = {}
        for ei, k in getattr(model, "hatch_ladders", None) or []:
            if ei in mine and hp is not None and 0 <= k < len(mine[ei].spans):
                s = int(mine[ei].spans[k])
                hatch_cells[s] = hatch_cells.get(s, 0) + n_levels
        for i, w in enumerate(deck_widths):
            for s, cells in deck_cells.items():
                # 階段を外側に寄せる床（幅914 の 500＋240 など）は、階段が上がってくる層も内側の板（ハーフアンチ）を敷く
                if half and i >= 1:
                    cells += stair_cells.get(s, 0)
                if hatch_cells and w == hw and i == list(deck_widths).index(hw):
                    cells = max(0, cells - hatch_cells.get(s, 0))
                add(m.deck_parts(w, s), cells, f"踏板 幅{w}×{s}")
        if hatch_cells:
            n_h = sum(hatch_cells.values())
            add(hp, n_h, f"ハッチ付布板（梯子内蔵）昇降口 {n_h // max(1, n_levels)}箇所×{n_levels}層")
            notes.append(f"昇降口はハッチ付布板（梯子内蔵 {hp.model_no}）{n_h // max(1, n_levels)}箇所×各層。"
                         f"その升目の幅{hw}の踏板は差し引いています")
        if half:
            notes.append(
                f"階段室は階段（外幅481）を外側の幅{deck_widths[0]}の板の位置に寄せ、階段が上がってくる層も内側の幅"
                f"{deck_widths[1]}の板（ハーフアンチ）を敷いて通れるようにしています（{sum(stair_cells.values())}枚）"
            )
    if rows == 1 and not model.config.is_hug:
        # 建地が1列なので床は片持ち。受けるブラケットが要る（本足場には無い部材）。単管は足場板2枚の幅で選ぶ
        need_w = deck_widths[0] if not m.is_tube else sum(deck_widths) + 20 * (len(deck_widths) - 1)
        brk = next((p for p in sorted(m.by_category("ブラケット"), key=lambda q: q.nominal_dim)
                    if p.nominal_dim >= need_w and "張出" not in p.note
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
    if model.config.has_toe_board and m.is_tube and model.deck_widths_in_use:
        # 単管の幅木は足場板を立てたもの。床の足場板と同じ割付で規定の長さを通し、継ぎは300重ねる
        _count_tube_toe_boards(model, n_levels, add, notes,
                               sum(n * n_levels for n in span_counts.values()) - sum(toe_cells.values()))
    elif model.config.has_toe_board:
        for s, cells in toe_cells.items():
            add(m.find("幅木", s), cells, f"幅木{s}")
    elif model.config.shita_san and not advance_rail:
        # 下さん（幅木を付けないとき。高さ15〜40cmの桟。利用者の資料 2026-10-24: 幅木を使用しない場合は下さんが必要）
        for s, cells in toe_cells.items():
            add(m.find("下さん", s), cells, f"下さん{s}（幅木の代わり・床から300の桟）")
        notes.append("幅木を付けないので、作業床の外側に下さん（高さ15〜40cmの桟）を各層に計上しています")

    # ---- 壁つなぎ ----
    kt = next(iter(m.by_category("壁つなぎ")), None)
    _add_wall_ties(model, platforms, kt, add, notes, openings=openings)

    # ---- 階段・階段まわりの手すり（自動配置があればその箇所数、なければ設定値）。踊り場の床は使わない ----
    stair = next((p for p in m.by_category("階段") if "ハーフ" not in p.note), None)
    n_towers = (
        stair_plan.count if stair_plan is not None and (stair_plan.towers or getattr(stair_plan, "subset", False))
        else model.config.n_stairs
    )
    # 単管抱き足場・単管のブラケット足場は階段が入らない（はしご等を別に。cli が階段を置かない）
    if model.no_stair_tower and stair_plan is not None and not stair_plan.towers:
        n_towers = 0
    add(stair, n_towers * n_levels, "階段")
    _count_stair_guards(model, add, notes, n_towers, n_levels,
                        outside=bool(getattr(stair_plan, "outside", False)))
    _count_outside_stairs(model, stair_plan, add, notes)

    _count_asagao_parts(model, span_counts, posts_per_line, add, notes, kt)
    _count_horizontal_net(model, add, notes)
    _count_sheets(model, add, notes, stair_plan)
    _count_open_ends(model, add, notes)
    _count_wedge_corner_steps(model, add, notes)

    _count_bracket_parts(model, bracket_sections, add, notes, counts)
    _count_platform_parts(model, platforms, add, notes)
    _count_opening_parts(model, openings, add, notes)
    _note_inner_rail_if_wide(model, notes, bracket_sections)
    _note_bridged_zones(model, notes)
    _note_double_posts_if_tall(model, notes)
    if m.is_tube:
        _count_tube_fittings(model, counts, parts, add, notes, tube_stats)
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
    if not m.is_tube and model.config.scaffold_form != "一側足場":
        # 幅の違う本足場の組（本足場（狭い幅）など）と出会う隅は、前の面の幅×この面の幅の長方形（3D・平面と同じ。
        # 2026-10-24）。布材・幅木は2辺の長さで、踏板は前の面の幅の長さで拾う
        mixed = [w for w in model.outer_corner_prev_widths() if abs(w - model.post_row_spacing_mm) > 0.5]
        for wa in sorted(set(mixed)):
            k = mixed.count(wa)
            wa_n = int(round(wa))
            per_side = 1 + n_levels * 3
            add(m.find("布材", udegi), k * per_side, f"出隅コーナーの布材{udegi}")
            add(m.find("布材", wa_n), k * per_side, f"出隅コーナーの布材{wa_n}（隣の組の幅）")
            if model.config.has_toe_board:
                add(m.find("幅木", udegi), k * n_levels, f"出隅コーナーの幅木{udegi}")
                add(m.find("幅木", wa_n), k * n_levels, f"出隅コーナーの幅木{wa_n}（隣の組の幅）")
            for w in model.deck_widths_in_use:
                part = m.deck_parts(w, wa_n)
                if part is None:
                    notes.action(f"出隅コーナー（{wa_n}×{udegi}）の床に敷く長さ{wa_n}の踏板（幅{w}）がマスタにありません"
                                 "（コーナー踏板または隙間塞ぎを別途手配）", Notes.ORDER)
                    continue
                add(part, k * n_levels, f"出隅コーナーの踏板 幅{w}×{wa_n}")
            notes.append(f"幅の違う本足場と出会う出隅{k}箇所は、升目 {wa_n}×{udegi} の布材（2辺×〈根がらみ1＋各層の床・"
                         f"手すり・中桟3〉×{n_levels}層）・幅木・長さ{wa_n}の踏板で計上")
        n_corners -= len(mixed)
        if n_corners <= 0:
            return
    per_corner = 2 * (1 + n_levels * 3)
    add(m.find("布材", udegi), n_corners * per_corner, f"出隅コーナーの布材{udegi}")
    notes.append(
        f"出隅コーナー{n_corners}箇所は、外側コーナー支柱1本（支柱位置数に含む）と"
        f"呼び{udegi}mmの布材{per_corner}本（2辺×〈根がらみ1＋各層の床・手すり・中桟3〉×{n_levels}層）"
        "ずつで計上"
    )
    if m.is_tube and model.deck_widths_in_use:
        # 単管の足場（本足場・ブラケット足場）の出隅は、足場板を床の列ごとに1枚、コーナーの単管から始点側の面の板の
        # 上に渡し、幅木（足場板）を外側2辺に2枚立てる（3D と同じ。利用者の指定 2026-10-22: 単管の本足場の出隅も
        # 単管の板に揃えて、巾木も）
        from .tube_runs import corner_board_mm

        cb = corner_board_mm(model.post_row_spacing_mm)
        for w in model.deck_widths_in_use:
            board = next((p for p in m.by_category("踏板") if p.actual_dim == cb and f"幅{w}" in p.note), None)
            add(board, n_corners * n_levels, f"出隅のコーナーの足場板 幅{w}×{cb / 1000:.1f}M")
        if model.config.has_toe_board:
            toe_b = next((p for p in m.by_category("幅木") if p.actual_dim == cb), None)
            add(toe_b, n_corners * n_levels * 2, f"出隅のコーナーの幅木（足場板）{cb / 1000:.1f}M")
        notes.append(f"単管の足場の出隅{n_corners}箇所×{n_levels}層は、足場板{cb / 1000:.1f}M を床の列ごとに1枚"
                     f"（コーナーの単管から渡して面の板に重ねる）" + ("と幅木（足場板）2枚" if model.config.has_toe_board else "")
                     + "で計上")
        return
    toe = m.find("幅木", udegi)
    if model.config.has_toe_board:
        add(toe, n_corners * n_levels * 2, f"出隅コーナーの幅木{udegi}")
    if toe is None and model.config.has_toe_board:
        notes.action(
            f"出隅コーナーの幅木（呼び{udegi}mm、{n_corners * n_levels * 2}本）がマスタにありません",
            Notes.ORDER,
        )
    # コーナーの床（{udegi}mm角）は、長さ{udegi}の踏板を本体の床と同じ幅の組み合わせで敷く
    # （升目は建地列間隔の長さのスパン1つと同じ形）。系列のマスタにある実在の踏板で拾い、
    # 無い幅だけ手配に出す（以前は全部を「別途手配」の注意にしていた）
    if model.config.scaffold_form == "一側足場":
        # 一側はコーナーの升目がブラケットの床幅で決まり、建地列間隔の正方形にならない。
        # 系列にコーナーステップ（日建 NDCS05・02）があれば、床の幅の品で出隅×層を拾う
        w0 = model.deck_widths_in_use[0] if model.deck_widths_in_use else 0
        step = next((p for p in m.by_category("コーナー踏板") if p.nominal_dim == w0), None)
        if step is not None:
            add(step, n_corners * n_levels, f"一側足場の出隅のコーナーステップ 幅{w0}")
            notes.append(f"一側足場の出隅{n_corners}箇所×{n_levels}層はコーナーステップ {step.model_no} で計上")
            return
        notes.action(
            f"外側コーナー{n_corners}箇所×{n_levels}層＝{n_corners * n_levels}枚のコーナー踏板"
            "は踏板の数量に含んでいません（一側足場のコーナーはコーナー踏板または隙間塞ぎを別途手配）",
            Notes.ORDER,
        )
        return
    missing = []
    for w in model.deck_widths_in_use:
        part = m.deck_parts(w, udegi)
        if part is None:
            missing.append(w)
            continue
        add(part, n_corners * n_levels, f"出隅コーナーの踏板 幅{w}×{udegi}")
    if missing:
        notes.action(
            f"出隅コーナー{n_corners}箇所×{n_levels}層の床に敷く長さ{udegi}の踏板"
            f"（幅{'・'.join(str(w) for w in missing)}）がマスタにありません"
            "（コーナー踏板または隙間塞ぎを別途手配）",
            Notes.ORDER,
        )
    else:
        notes.append(
            f"出隅コーナーの床は長さ{udegi}の踏板（幅{'+'.join(str(w) for w in model.deck_widths_in_use)}）"
            f"を{n_corners}箇所×{n_levels}層で計上"
        )


def _count_wedge_corner_steps(model: ScaffoldModel, add, notes) -> None:
    """くさびの隅の隙間（コーナーステップで納める）: 隙間ごとに層の数 × 床の幅の品（NDCS05・NDCS02 など）."""
    mine = {e.edge_index for e in model.plan.edges}           # 面ごとの数量ではその面の隙間だけ
    gaps = [c for c in getattr(model.plan, "corner_steps", []) or []
            if c.edge_index >= 0 and c.edge_index in mine]
    if not gaps:
        return
    steps = list(model.master.by_category("コーナー踏板"))
    total_lv = sum(len(model.elevation_of(c.edge_index).level_heights) for c in gaps)
    missing = []
    for w in model.deck_widths_in_use or []:
        hit = next((s for s in steps if int(s.nominal_dim) == int(w)), None)
        if hit is None:
            missing.append(int(w))
            continue
        add(hit, total_lv, f"隅の隙間のコーナーステップ 幅{int(w)}")
    notes.append(f"隅の隙間{len(gaps)}箇所（" + "・".join(f"{c.gap_mm:.0f}" for c in gaps)
                 + f"mm）×各層はコーナーステップで計上（離れを固定し、隅は無理に繋がない）")
    if missing:
        notes.action(f"コーナーステップ（幅{'・'.join(str(w) for w in missing)}）がマスタにありません。"
                     f"隅の隙間{len(gaps)}箇所×各層＝{total_lv}組を別途手配", Notes.ORDER)


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
    span_counts, posts_per_line, skipped = _asagao_faces_only(model, span_counts, posts_per_line)
    if not span_counts:
        return
    if skipped:
        notes.append(f"朝顔は {'・'.join(skipped)} には付けていません（付ける面を選んだ計画）")
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
    # 出隅はそれを始点に持つ面に属する（面の組・面ごとの数量で二重にしない）
    corners = [e for e in model.plan.outline.edges if model.corner_kind_start(e.index) == "出隅"
               and (model.edge_subset is None or e.index in model.edge_subset)
               and (model.faces_only is None or e.index in model.faces_only)
               and model.asagao_on(e.index) and model.asagao_on((e.index - 1) % len(model.plan.outline.edges))]
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


def _asagao_faces_only(model: ScaffoldModel, span_counts: dict, posts_per_line: int):
    """朝顔を付ける面を選んだ計画（model.asagao_edges）なら、その面だけのスパン数・支柱数 → (スパン数, 支柱数, 付けない面名).

    付ける面が全部なら渡されたまま。支柱は面のスパン数＋1 を足し、隣り合う付ける面どうしの隅の支柱は1本に数える。
    """
    if model.asagao_edges is None:
        return span_counts, posts_per_line, []
    mine = [e for e in model.plan.edges if model.asagao_on(e.edge_index)
            and (model.edge_subset is None or e.edge_index in model.edge_subset)]
    counts: dict[int, int] = {}
    for e in mine:
        for sp in e.spans:
            counts[sp] = counts.get(sp, 0) + 1
    n = len(model.plan.outline.edges)
    on = {e.edge_index for e in mine}
    posts = sum(len(e.spans) + (0 if (e.edge_index + 1) % n in on else 1) for e in mine)
    names = dict(zip([e.edge_index for e in model.plan.edges], model.plan.face_names()))
    skipped = [names[e.edge_index] for e in model.plan.edges if e.edge_index not in on]
    return counts, posts, skipped


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
    # 出隅はそれを始点に持つ面に属する（面の組・面ごとの数量で二重にしない）
    corners = [e for e in model.plan.outline.edges if model.corner_kind_start(e.index) == "出隅"
               and (model.edge_subset is None or e.index in model.edge_subset)
               and (model.faces_only is None or e.index in model.faces_only)]
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

    # 内ブラケットの上に躯体側へ敷く踏板（離れを詰める区間）。区間に収まるスパン×層
    from .brackets import _find_edge as _edge_of
    for sec in bracket_sections or []:
        if not getattr(sec, "inner_deck_width", None):
            continue
        edge = _edge_of(model, sec.edge_index)
        if edge is None:
            continue
        n_lv = len(sec.levels) if sec.levels else model.elevation.n_levels
        acc = 0.0
        for span in edge.spans:
            if sec.start_mm - 1e-6 <= acc and acc + span <= sec.end_mm + 1e-6:
                add(m.deck_parts(sec.inner_deck_width, span), n_lv, f"内ブラケットの踏板 幅{sec.inner_deck_width}×{span}")
            acc += span

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


def _count_horizontal_net(model: ScaffoldModel, add, notes) -> None:
    """水平ネット（躯体と足場の隙間）とネットブラケット。図の部品（attachments）と同じ数え方.

    マスタに無い系列は手配の注記に面積・個数で出す（ネットは m² 単位、ブラケットは内側建地ごと）。
    """
    from .attachments import (NETBK_MODEL, NETBK_PLATE_MM, NETBK_REACH_MAX_MM, NETBK_REACH_MIN_MM, NET_GAP_MM,
                              net_quantities, netbk_clash_faces)

    if not model.config.horizontal_net_levels:
        return
    area, n_bk = net_quantities(model)
    if area <= 0:
        return
    m = model.master
    lv = "・".join(str(v) for v in model.config.horizontal_net_levels)
    bk = next(iter(m.by_category("ネットブラケット")), None)
    if bk is not None and n_bk:
        add(bk, n_bk, f"ネットブラケット（第{lv}層・内側建地ごと）")
    net = next(iter(m.by_category("水平ネット")), None)
    if net is not None:
        # 層間ネット KSK-HV は 0.5×6m の1枚もの（利用者の資料 2026-10-24）。面ごと・層ごとに長さ6m・幅0.5m で割る
        from .attachments import net_pieces

        n_net = net_pieces(model, float(net.nominal_dim), float(net.actual_dim))
        add(net, n_net, f"層間ネット {net.actual_dim / 1000:.1f}×{net.nominal_dim / 1000:.0f}m（第{lv}層）")
    missing = []
    if net is None:
        missing.append(f"水平ネット {area:.1f}m²")
    if bk is None and n_bk:
        missing.append(f"ネットブラケット（ネット専用ブラケット {NETBK_MODEL} 相当）{n_bk}個")
    if model.config.net_brackets:
        notes.append(f"水平ネットは第{lv}層の床下（躯体と足場の隙間）に面ごと {area:.1f}m²、ネットブラケットは内側建地ごと"
                     f" {n_bk}個で計上（ネットブラケットは起立式。開口部で作業するときはパイプを立てる）")
    else:
        notes.append(f"水平ネットは第{lv}層の床下（躯体と足場の隙間）に面ごと {area:.1f}m² で計上。ネットブラケットは"
                     "付けない指定（ネットの取付け金具は別途）")
    # 層間ネットの決まり（利用者の資料 2026-10-24）: 幅木を使うなら2層毎、使わないなら全層
    have = sorted(model.config.horizontal_net_levels)
    n_lv = model.elevation.n_levels
    if not model.config.has_toe_board:
        miss = [k for k in range(2, n_lv + 1) if k not in have]              # 1段目は要らない
        if miss:
            notes.action(f"幅木を付けないので層間ネットは全層に要ります（第{'・'.join(str(k) for k in miss)}層に無い）",
                         Notes.SITE)
    else:
        gaps = [have[0] - 1] + [b - a for a, b in zip(have, have[1:])] + [n_lv + 1 - have[-1]]   # 1段目から数える
        if max(gaps) > 2:
            notes.action("幅木を付けるときも層間ネットは2層毎に要ります（張る層 第" + lv + "層。間が3層以上空いている）",
                         Notes.SITE)
    clash = netbk_clash_faces(model)
    if clash:
        need = NETBK_PLATE_MM + NETBK_REACH_MIN_MM + NET_GAP_MM
        faces = "・".join(f"{model.face_name(i)}（離れ{so:.0f}mm）" for i, so in clash)
        notes.action(f"ネットブラケット {NETBK_MODEL} の腕は受け板から {NETBK_REACH_MIN_MM:.0f}〜{NETBK_REACH_MAX_MM:.0f}mm"
                     f"（建地芯から最短 {NETBK_PLATE_MM + NETBK_REACH_MIN_MM:.0f}mm）で、{faces} では最短でも躯体に当たります。"
                     f"離れを {need:.0f}mm 以上にするか、腕の短いブラケット・内ブラケットで隙間を塞ぐ方法を検討してください",
                     Notes.SITE)
    if missing:
        notes.action("水平ネットの部材が系列 " + m.series_id + " のマスタにありません: " + "・".join(missing)
                     + "。別途手配してください", Notes.ORDER)


def _count_open_ends(model: ScaffoldModel, add, notes) -> None:
    """一部の面だけの足場の開放端（隣の面を掛けない端）: 妻側の手すり・中桟・幅木を各層に.

    参考: smartCON Planner の「墜落の危険箇所に手すりを設置（つま先板つき）」「エンドストッパー」。
    """
    m = model.master
    row = model.post_row_spacing_mm
    n_ends = 0
    for ep in model.plan.edges:
        lv = model.elevation_of(ep.edge_index).n_levels
        k = int(model.open_start(ep.edge_index)) + int(model.open_end(ep.edge_index))
        # 入隅でつないだ隅から始まる面の始点（躯体側に開く升目。gdl_params の endOpenS と同じ）
        if model.inner_join_start(ep.edge_index) and model.config.inner_guard_rail and not model.open_start(ep.edge_index):
            k += 1
        n_ends += k
        if not k:
            continue
        add(m.find("布材", row), k * lv * 2, f"開放端の妻側の手すり・中桟（布材{row}）")
        if model.config.has_toe_board:
            add(m.find("幅木", row), k * lv, f"開放端の妻側の幅木{row}")
    if n_ends:
        notes.append(f"一部の面だけの足場の端・入隅でつないだ升目の躯体側の開放端{n_ends}箇所は、各層に妻側の手すり・中桟"
                     + ("・幅木" if model.config.has_toe_board else "") + "を計上")


def _count_sheets(model: ScaffoldModel, add, notes, stair_plan=None) -> None:
    """養生シート（足場の外側の構面）。マスタに無ければ枚数と面積を注記に出す（リースの別手配が多い）."""
    from .attachments import (SHEET_SIZES, sheet_clamp_count, sheet_corner_clamp_count, sheet_quantities, sheet_size,
                              special_sheets, standard_sheets)

    kind = model.config.sheet_type or ""
    if kind not in SHEET_SIZES:
        return
    # 系列にある品はその大きさ（日建スプリングメッシュは 1829×5160、防音シート ♯1000 は 1.8×3.4）で数える
    w, h = sheet_size(model)
    area, n = sheet_quantities(model, stair_plan, (w, h))
    std = standard_sheets(model, stair_plan, (w, h))
    sp = special_sheets(model, stair_plan, (w, h))
    if n <= 0 and not sp:
        return
    # 足場のスパンと同じ幅のシート（インチ・メートルとも普通にある幅）。系列のマスタにある幅はその品で、無い幅は手配に
    other = {}
    for wd, k in std.items():
        # インチのスパンにはメートルの幅の品（1.8・1.5…）を当てる（50 以内の近い幅）
        cands = [p for p in model.master.by_category("養生シート") if kind in p.note and abs(p.nominal_dim - wd) <= 50]
        hit = min(cands, key=lambda p: abs(p.nominal_dim - wd)) if cands else None
        if hit is not None:
            add(hit, k, f"{kind} 幅{wd}")
        else:
            other[wd] = k
    notes.append(f"{kind}（{w / 1000:.1f}×{h / 1000:.1f}m）は外側の構面を地面から足場の天端まで、継ぎ目を足場のスパンに"
                 f"そろえて {area:.0f}m²・" + "・".join(f"幅{wd}×{k}枚" for wd, k in std.items()) + " で計上")
    if other:
        notes.action(f"{kind}（高さ {h / 1000:.1f}m）: " + "・".join(f"幅{wd}×{k}枚" for wd, k in other.items())
                     + f"（系列 {model.master.series_id} のマスタに無い幅）を別途手配してください", Notes.ORDER)
    if sp:
        # 角の升目・隅の隙間に伸ばす分は特殊シート（利用者の指定 2026-10-24）
        notes.action(f"特殊シート（{kind}・高さ {h / 1000:.1f}m）: "
                     + "・".join(f"幅{wd}×{k}枚" for wd, k in sp.items())
                     + "。角の升目・隅の隙間など足場のスパンに無い幅に伸ばす分。別途手配してください", Notes.ORDER)
    # シートクランプ（シートを外側建地の布材に留める。継ぎ目と端の支柱 × 根がらみと各層の手すり）
    n_cl = sheet_clamp_count(model, stair_plan)
    if n_cl:
        clamp = next(iter(model.master.by_category("シートクランプ")), None)
        if clamp is not None:
            add(clamp, n_cl, "シートクランプ（継ぎ目と端の建地に、根がらみと各層の手すりの高さで）")
        else:
            notes.action(f"シートクランプ {n_cl}個（シートの継ぎ目と端の建地に、各段のシートの上下で）。"
                         "系列のマスタに品番が無いので別途手配してください", Notes.ORDER)
    # 出隅の角は「養生クランプ コーナー用」1つで2面のシートを留める（利用者の指定 2026-10-24: コーナーはコーナー用に）
    n_cc = sheet_corner_clamp_count(model, stair_plan)
    if n_cc:
        cc = next(iter(model.master.by_category("コーナー用シートクランプ")), None)
        if cc is not None:
            add(cc, n_cc, "養生クランプ コーナー用（出隅の角の建地に、各段のシートの上下で）")
        else:
            notes.action(f"養生クランプ コーナー用 {n_cc}個（出隅の角の建地で2面のシートを留める。各段のシートの上下）。"
                         "系列のマスタに品番が無いので別途手配してください", Notes.ORDER)
    hb = getattr(model, "hoarding_height_mm", 0.0) or 0.0
    if hb > 0:
        notes.append(f"{kind}は仮囲いの天端（{hb:.0f}）から上に、天端から上へ1枚の高さずつ割り付けています（いちばん下の段は残りの高さ）")


def outside_stair_counts(model: ScaffoldModel, stair_plan) -> tuple[int, int]:
    """外付けの階段室の (支柱位置の数, 床のセル数（床の幅1列あたり）). 外付けでなければ (0, 0)."""
    if stair_plan is None or not stair_plan.towers or not getattr(stair_plan, "outside", False):
        return 0, 0
    from .stairs import flight_span_index, flight_spans, tower_spans

    n_pos = n_cells = 0
    for t in stair_plan.towers:
        ts = tower_spans(model, t)
        if not ts:
            continue
        first, fl = flight_spans(model, t, True)
        n_lv = model.elevation_of(t.edge_index).n_levels
        n_pos += len(ts) + 1
        for i, _sp in enumerate(ts):
            j = i - first
            n_cells += sum(1 for k in range(1, n_lv + 1)
                           if not (0 <= j < len(fl)) or (len(fl) > 1 and j != flight_span_index(k, len(fl))))
    return n_pos, n_cells


def _count_outside_stairs(model: ScaffoldModel, stair_plan, add, notes) -> None:
    """外付けの階段室: 外側建地列の外に建地1列（3列目）を立て、区間を 上り口＋階段2スパン＋降り口 にする.

    利用者の指摘（2026-10-20）: 階段は回れるように4スパン要る。上り口と降り口に横のスパンが必要。
    1箇所あたり（区間のスパン n、層数 N）:
    - 支柱: n+1 本の位置に本体と同じ積み上げ。ジャッキ・アンダーベース・最下部の附属品も位置ごと
    - 腕木（外側建地列〜3列目）: 位置×（作業層＋根がらみ）
    - 3列目のスパン方向: 根がらみ1本、各層の手すり・中桟（先行手すりなら先行手摺1本）、幅木
    - 妻側（区間の両端）: 各層の手すり・中桟（腕木と同じ呼び寸法）
    - 床: 両端（上り口・降り口）は各層、中の階段のスパンは下から階段が上がってくるスパン以外
    本体の作業床は切らない。上り口・降り口のスパンの本体外側の手すりは盛り替えで外す（数量は本体のまま）。
    階段の開口と本体の床の間は本体の外側の手すりで仕切るので、階段開口部手摺・幅木は使わない。
    """
    if stair_plan is None or not stair_plan.towers or not getattr(stair_plan, "outside", False):
        return
    from .stairs import flight_span_index, flight_spans, tower_spans

    m = model.master
    row = model.post_row_spacing_mm
    adv = model.config.guard_rail_type == GUARD_RAIL_ADVANCE
    under = next((p for p in m.by_category("ジャッキ") if "アンダーベース" in p.note), None)
    n_pos = 0
    for t in stair_plan.towers:
        ts = tower_spans(model, t)
        if not ts:
            continue
        first, fl = flight_spans(model, t, True)
        ev = model.elevation_of(t.edge_index)
        n_lv = ev.n_levels
        pos = len(ts) + 1
        n_pos += pos
        for nominal in ev.posts:
            part = next((p for p in m.by_category("支柱")
                         if p.nominal_dim == nominal and "根がらみ" not in p.note and "屋根" not in p.note), None)
            add(part, pos, f"支柱{nominal}（外付け階段）")
        _count_jacks(m, None, 1, pos, add, notes, suffix="（外付け階段）")
        add(under, pos, "アンダーベース（外付け階段）")
        for p in m.by_category("支柱附属"):
            if "最下部" in p.note:
                add(p, pos * _units_per_place(p), f"{p.model_no}（外付け階段の支柱最下部）")
            elif "継ぎ目" in p.note:
                # 支柱を継ぐ金具（NDストロングの NSジョイント）も本体と同じく継ぎ目ごとに（抜けていた）
                add(p, pos * max(0, len(ev.posts) - 1), f"{p.model_no}（外付け階段の支柱の継ぎ目）")
        add(m.find("布材", row), pos * (n_lv + 1), f"腕木（外付け階段、布材{row}）")
        add(m.find("布材", row), 2 * 2 * n_lv, f"外付け階段の妻側の手すり・中桟（布材{row}）")
        cells: dict[int, int] = {}
        for i, sp in enumerate(ts):
            add(m.find("布材", sp), 1, f"外付け階段の根がらみ（布材{sp}）")
            if adv:
                add(m.find("先行手摺", sp), n_lv, f"外付け階段の先行手摺{sp}")
            else:
                add(m.find("布材", sp), 2 * n_lv, f"外付け階段の手すり・中桟（布材{sp}）")
            if model.config.has_toe_board:
                add(m.find("幅木", sp), n_lv, f"外付け階段の幅木{sp}")
            j = i - first
            for k in range(1, n_lv + 1):
                if not (0 <= j < len(fl)) or (len(fl) > 1 and j != flight_span_index(k, len(fl))):
                    cells[sp] = cells.get(sp, 0) + 1
        for w in model.deck_widths_in_use:
            for sp, c in cells.items():
                add(m.deck_parts(w, sp), c, f"外付け階段の床 幅{w}×{sp}")
    if n_pos:
        notes.append(
            f"階段は外付け: 外側建地列の外に建地をもう1列（{len(stair_plan.towers)}箇所・支柱位置{n_pos}）立て、"
            f"間隔{row}mmの升目を 上り口＋階段2スパン＋降り口 にします（両端のスパンは各層に床）。本体の作業床は切りません。"
            "上り口・降り口のスパンは本体の外側の手すりを盛り替えで外します（数量は本体のまま）"
        )


def _count_stair_guards(model: ScaffoldModel, add, notes, n_towers: int, n_levels: int,
                        outside: bool = False) -> None:
    """階段まわりの手すり類（2026-10-18 利用者の決め）.

    - 専用階段手摺: 2段（手すりと中桟。利用者の指定 2026-10-24: 足場の手すりはこのかたち 2段）。階段1つにつき
      階段側（もう一方は開口部手摺。利用者の指摘 2026-10-22）。外付けは両側
    - 階段開口部手摺: 出入口1か所に1組。各層で下からの階段が上がってくる所が出入口
    - 階段開口部幅木は使わない（利用者の指定 2026-10-24: 階段上の幅木と布材不要）
    踊り場の部材（ハッチ付布板）は使わない。2層ごとに階段室を出て外の作業床へ出る（踊り場を兼ねる）。
    マスタに無い部材は手配の注記に出す。
    """
    if not n_towers or not n_levels:
        return
    m = model.master
    per = (2 if outside else 1) * 2                     # 2段（手すりと中桟）
    need = (("階段手摺", n_towers * n_levels * per,
             "専用階段手摺 2段（階段1つに両側）" if outside else "専用階段手摺 2段（階段1つに階段側）"),)
    # 外付けは階段の開口と本体の床の間を本体の外側の手すりで仕切るので、開口部手摺は使わない
    if not outside:
        need += (("階段開口部手摺", n_towers * n_levels, "階段開口部手摺（出入口1か所に1組）"),)
    missing = []
    for cat, qty, label in need:
        part = next(iter(m.by_category(cat)), None)
        if part is None:
            missing.append(f"{label} {qty}")
            continue
        add(part, qty, label)
    if missing:
        notes.action("階段まわりの部材が系列 " + m.series_id + " のマスタにありません: " + "・".join(missing)
                     + "。別途手配してください", Notes.ORDER)


def _add_extra_negarami(model: ScaffoldModel, terrain, add, notes, rows: int) -> None:
    """敷地高低差で継ぎ足した脚の区間に入れる根がらみ（布材）を計上する."""
    if terrain is None:
        return
    from .terrain import extra_negarami

    import dataclasses

    m = model.master
    n_extra = 0
    # 外側の列も地盤から解いてあれば、列ごとにその列の脚で数える（立面・3D と同じ）
    outer = list(getattr(terrain, "feet_outer", []) or [])
    per_row = [(terrain, 1), (dataclasses.replace(terrain, feet=outer), 1)] if outer and rows >= 2 else [(terrain, rows)]
    for t, k in per_row:
        rows_by_edge = extra_negarami(model, t)
        for ep in model.plan.edges:
            for i, _level in rows_by_edge.get(ep.edge_index, []):
                s = ep.spans[i]
                add(m.find("布材", s), k, f"継ぎ足し部の根がらみ（布材{s}）")
                n_extra += k
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
    return standoff + model.tie_post_offset_mm + extra + dia / 2.0


def _add_wall_ties(model: ScaffoldModel, platforms, kt, add, notes=None, openings=None) -> None:
    """壁つなぎを由来ごとに計上する（格子＋朝顔取付部＋ステージ取付部＋マスト控え）.

    取付部の分がまだ一覧に無ければここで統合する（take_off を単独で呼んでも
    数量が欠けないように。統合は何度呼んでも同じ結果）。

    伸縮範囲の違う壁つなぎが複数ある系列（日建 KS200/400/700）は、面ごとの離れに合う
    品を選ぶ。1品だけの系列は従来どおりその品で全数を数える。以前は日建で KS700
    （380〜760mm）だけを登録していて、離れ212mmの面にも KS700 を当てていた。
    """
    from .ties import has_attachment_ties, kind_labels, merge_attachment_ties, relocate_unreachable_ties, tie_counts

    labels = kind_labels(model)

    if not has_attachment_ties(model):
        merge_attachment_ties(model, platforms, openings)
        relocate_unreachable_ties(model, label="取付部の壁つなぎ")
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
        cuts.append(f"階段室{n_towers}箇所の開口{stair_cut}セル（各層で階段が上がってくる1スパン）")
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


def _note_inner_rail_if_wide(model: ScaffoldModel, notes: list[str], bracket_sections=None) -> None:
    """離れが300mmを超える面は躯体側にも墜落防止措置が要る.

    法規チェックと割付の警告では「手すりの設置または安全帯の使用等」と
    出しているが、数量表には躯体側の手すり材が入っていない。どちらを選ぶかは
    現場判断なので自動では計上しないが、入っていないことは書いておく。
    内ブラケットの踏板で全長を詰めた面（隙間300以下）は対象外。
    """
    closed = {s.edge_index for s in bracket_sections or []
              if getattr(s, "inner_deck_width", None) and s.start_mm <= 1e-6
              and s.end_mm >= next((e.scaffold_length for e in model.plan.edges
                                    if e.edge_index == s.edge_index), float("inf")) - 1e-6}
    wide = [
        (e.edge_index, e.standoff, e.span_count)
        for e in model.plan.edges
        if e.standoff > 300.0 + 1e-6 and e.edge_index not in closed
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


def _count_tube_boards(model: ScaffoldModel, deck_widths: list, n_levels: int, add, notes, cut_cells: int) -> None:
    """単管のブラケット足場の足場板: 面ごとの割付（tube_runs.face_boards）× 作業層 × 敷く枚数."""
    from .tube_runs import BOARD_LAP_MM, face_boards

    m = model.master
    lines = []
    for ep in model.plan.edges:
        runs = face_boards(list(ep.spans))
        for i, w in enumerate(deck_widths):
            run = runs[i % 2]
            for L in run.pieces:
                part = next((p for p in m.by_category("踏板") if p.actual_dim == L and f"幅{w}" in p.note), None)
                add(part, n_levels, f"足場板 幅{w}×{L / 1000:.1f}M")
        lines.append("+".join(f"{L / 1000:.1f}" for L in runs[0].pieces))
    notes.append(
        f"足場板は規定の長さで面に沿って敷き、継ぎは{BOARD_LAP_MM}mm 重ねてブラケットの上に掛ける"
        f"（{'／'.join(lines)} m）× {len(deck_widths)}枚敷き × {n_levels}層で計上"
    )
    if cut_cells:
        notes.append(f"足場板は階段・開口部の区間（{cut_cells}スパン×層）も面の通しのまま計上しています")


def _count_tube_toe_boards(model: ScaffoldModel, n_levels: int, add, notes, cut_cells: int) -> None:
    """単管の幅木（足場板を立てたもの）: 面ごとの足場板の割付（face_boards の A）× 作業層."""
    from .tube_runs import BOARD_LAP_MM, face_boards

    m = model.master
    lines = []
    for ep in model.plan.edges:
        run = face_boards(list(ep.spans))[0]
        for L in run.pieces:
            part = next((p for p in m.by_category("幅木") if p.actual_dim == L), None)
            add(part, n_levels, f"幅木（足場板）{L / 1000:.1f}M")
        lines.append("+".join(f"{L / 1000:.1f}" for L in run.pieces))
    notes.append(
        f"幅木は足場板を立てて規定の長さで通し、継ぎは{BOARD_LAP_MM}mm 重ねる（床の足場板と同じ割付"
        f" {'／'.join(lines)} m）× {n_levels}層で計上"
    )
    if cut_cells:
        notes.append(f"幅木は開口部・ステージ等の区間（{cut_cells}スパン×層）も面の通しのまま計上しています")


def _count_tube_runs(model: ScaffoldModel, rows: int, n_levels: int, add, notes, cut: int) -> dict:
    """単管の通し（布・手すり・中桟・根がらみ）: 面ごとに規定の長さの単管の割付（tube_runs）× 通しの数.

    通しは建地ごとに直交クランプで留める（抱き足場の床の布2本は3連クランプなので数えない）。継ぎは直線ジョイント。
    返り値: {"clamps": 直交クランプ, "joints": 直線ジョイント}
    """
    from .tube_runs import face_runs

    m = model.master
    hug_rows = 2 * n_levels if model.config.is_hug else 0
    clamps = joints = 0
    lines = []
    for ep in model.plan.edges:
        a, _b = face_runs(list(ep.spans))
        for L in a.pieces:
            part = m.find("単管", L)
            add(part, rows, f"単管{L / 1000:.1f}M（布・手すりの通し）")
        clamps += (len(ep.spans) + 1) * (rows - hug_rows)
        joints += (len(a.pieces) - 1) * rows
        lines.append("+".join(f"{L / 1000:.1f}" for L in a.pieces))
    notes.append(
        f"単管の通し（根がらみ・" + ("床の布2本・" if hug_rows else "") + "手すり・中桟）は、面ごとに規定の長さの単管を"
        f"直線ジョイントで継いで通す（{'／'.join(lines)} m。継ぎは建地のクランプから離し、隣の通しとずらす）×"
        f"1面あたり{rows}通りで計上"
    )
    if cut:
        notes.append(f"単管の通しは開口部・ステージ等の区間（スパン換算{cut}本分）も面の通しのまま計上しています（切らずに通す）")
    return {"clamps": clamps, "joints": joints}


def _count_tube_fittings(model: ScaffoldModel, counts: dict, parts: dict, add, notes,
                         tube_stats: Optional[dict] = None) -> None:
    """単管足場のクランプ・ジョイント（くさびの緊結部の代わり）.

    腕木・コーナーの短い管（布材）は両端を直交クランプで建地に、筋かいは両端を自在クランプで留める。
    布・手すりの通しは建地ごとに直交クランプ（_count_tube_runs）。建地と通しの継ぎは直線ジョイント。
    ブラケット・壁つなぎはクランプ付きの品なので数えない。
    """
    tube_stats = tube_stats or {"clamps": 0, "joints": 0}
    m = model.master
    by_cat: dict[str, int] = {}
    for key, qty in counts.items():
        part = parts.get(key)
        if part is not None:
            by_cat[part.category] = by_cat.get(part.category, 0) + qty
    clamps = m.by_category("クランプ")
    orth = next((p for p in clamps if "直交" in p.note and "3連" not in p.note), None)
    free = next((p for p in clamps if "自在" in p.note and "3連" not in p.note), None)
    triple = next((p for p in clamps if "3連" in p.note), None)
    n_ledgers = by_cat.get("布材", 0)
    n_braces = by_cat.get("筋交", 0)
    # 単管抱き足場: 床の高さの布2本は、建地ごと・層ごとに3連クランプ1個で建地と一緒に抱く（直交クランプではない）
    n_triple = 0
    if model.config.is_hug:
        n_triple = (model.plan.total_posts + model.outer_corner_posts()) * model.elevation.n_levels
        add(triple, n_triple, "3連クランプ（建地と抱き合わせた布2本）")
    n_orth = 2 * n_ledgers + tube_stats["clamps"]
    add(orth, n_orth, "直交クランプ（布・手すり・根がらみの通しを建地ごと、腕木・短い管は両端）")
    add(free, 2 * n_braces, "自在クランプ（筋かいの両端）")
    joint = next(iter(m.by_category("ジョイント")), None)
    n_posts = by_cat.get("支柱", 0)
    n_feet = by_cat.get("ジャッキ", 0)
    # ジャッキとアンダーベースは同じ数だけ入るので、脚の数はその半分
    legs = n_feet // 2 if any("アンダーベース" in p.note for p in m.by_category("ジャッキ")) else n_feet
    n_post_joints = max(0, n_posts - legs)
    n_joints = n_post_joints + tube_stats["joints"]
    add(joint, n_joints, "直線ジョイント（建地と通しの継ぎ）")
    if n_triple:
        notes.append(f"単管抱き足場: 床の高さの布（建地の両側に2本の通し）は、建地ごと・層ごとの3連クランプ{n_triple}個で留める。"
                     "布板・幅木は無い（抱き合わせた単管2本が床）")
    notes.append(
        f"単管足場: 直交クランプ{n_orth}個（通しを建地ごと{tube_stats['clamps']}個＋腕木・短い管{n_ledgers}本×両端）・"
        f"自在クランプ{2 * n_braces}個（筋かい{n_braces}本×両端）・直線ジョイント{n_joints}個（建地の継ぎ{n_post_joints}・"
        f"通しの継ぎ{tube_stats['joints']}）を計上。ブラケット・壁つなぎはクランプ付きの品"
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


def _count_frame_corners(model: ScaffoldModel, add, notes, n_levels: int) -> None:
    """枠組の出隅: ギャプレス（コーナー布受け）で納める（日建カタログ p104〜105）.

    出隅1箇所×1層に ギャプレス1本（建枠の幅の品）・ギャプレスクランプ3個（先行手すりの層は2個）、
    升目の床（長さ＝建枠の幅の布板、本体と同じ幅の組）と外周2辺の手すり・中桟。以前は枠組のコーナーを
    何も数えず、図にも隙間が空いていた（利用者の指摘 2026-10-21: 枠足場のコーナー部分も資料を見て見直して）。
    """
    m = model.master
    n_corners = len([e for e in model.plan.outline.edges if model.corner_kind_start(e.index) == "出隅"
                     and (model.edge_subset is None or e.index in model.edge_subset)
                     and (model.faces_only is None or e.index in model.faces_only)])
    if not n_corners or not n_levels:
        return
    row = model.post_row_spacing_mm
    cells = n_corners * n_levels
    cnu = next((p for p in m.by_category("コーナー布受け") if p.nominal_dim == row), None)
    clamp = next(iter(m.by_category("コーナー布受け金具")), None)
    adv = model.config.guard_rail_type == GUARD_RAIL_ADVANCE
    missing = []
    if cnu is None:
        missing.append(f"ギャプレス（{row}幅系）{cells}本")
    else:
        add(cnu, cells, f"出隅のギャプレス（{row}幅系）")
    if clamp is not None:
        add(clamp, cells * (2 if adv else 3), "ギャプレスクランプ")
    for w in model.deck_widths_in_use:
        part = m.deck_parts(w, row)
        if part is None:
            missing.append(f"出隅の床 幅{w}×長さ{row} {cells}枚")
        else:
            add(part, cells, f"出隅の床 幅{w}×{row}")
    rail = m.find("布材", row)
    if rail is None:
        missing.append(f"出隅の手すり・中桟（長さ{row}）{cells * 4}本")
    else:
        add(rail, cells * 4, f"出隅の手すり・中桟（外周2辺、{rail.model_no}）")
    notes.append(f"枠組の出隅{n_corners}箇所×{n_levels}層はギャプレス（コーナー布受け）で納め、升目の床・外周2辺の手すりを計上")
    if missing:
        notes.action("枠組の出隅の部材が系列のマスタにありません: " + "・".join(missing) + "。別途手配してください")


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
    legs, per_leg = _feet_by_row(terrain, rules.rows)
    _count_jacks(m, legs, per_leg, max(0, n_frame_legs - removed_legs), add, notes,
                 "（建枠1枚に2脚）")
    add(under, max(0, n_frame_legs - removed_legs), "アンダーベース（建枠1枚に2脚）")
    _count_shims(m, legs, per_leg, add, notes)

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
        from .stairs import stair_open_cells
        for s, n in stair_open_cells(model, stair_plan, n_levels).items():
            deck_cells[s] = max(0, deck_cells.get(s, 0) - n)
            stair_cut_cells += n
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
        # 開口部（梁枠より下）は床が無いので幅木も無い。階段が上がってくるスパンも外側の幅木は付けない（宙に浮く）
        st_cut: dict[int, int] = {}
        if stair_plan is not None and stair_plan.towers and not getattr(stair_plan, "outside", False):
            from .stairs import stair_open_cells
            st_cut = stair_open_cells(model, stair_plan, n_levels)
        for s, n in span_counts.items():
            add(m.find("幅木", s), max(0, n * n_levels - open_cut.get(s, 0) - st_cut.get(s, 0)), f"幅木{s}")
    kt = next(iter(m.by_category("壁つなぎ")), None)
    _add_wall_ties(model, platforms, kt, add, notes, openings=openings)
    stair = next(iter(m.by_category("階段")), None)
    n_towers = (
        stair_plan.count if stair_plan is not None and (stair_plan.towers or getattr(stair_plan, "subset", False))
        else model.config.n_stairs
    )
    # 単管抱き足場・単管のブラケット足場は階段が入らない（はしご等を別に。cli が階段を置かない）
    if model.no_stair_tower and stair_plan is not None and not stair_plan.towers:
        n_towers = 0
    add(stair, n_towers * n_levels, "階段枠")
    _count_stair_guards(model, add, notes, n_towers, n_levels)

    _count_frame_corners(model, add, notes, n_levels)

    # ---- 朝顔（くさび式と同じ数え方・同じ注記） ----
    _count_asagao_parts(model, span_counts, n_frame_lines, add, notes, kt)
    _count_horizontal_net(model, add, notes)
    _count_sheets(model, add, notes, stair_plan)
    _count_open_ends(model, add, notes)
