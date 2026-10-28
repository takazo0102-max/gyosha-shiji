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

import dataclasses

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
    sub._parent_model = model          # 隅の支柱の共有は面を絞る前の模型で決める（図と同じ）
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

    sub = dataclasses.replace(terrain, feet=[f for f in terrain.feet if nearest(f) in edges],
                              feet_outer=[f for f in getattr(terrain, "feet_outer", []) if nearest(f) in edges])
    # 継ぎ足し部の根がらみは区間の両端の脚で決まる（面の終点の脚は次の面の始点）。全体の脚と割付も持たせる
    object.__setattr__(sub, "_full", (getattr(terrain, "_full", None) or (terrain, model)))
    return sub


def standing_post_positions(model: ScaffoldModel, rows: int) -> int:
    """地盤に立つ支柱の位置の数（足場ラインの 3D と同じ。出隅の外側の角・隙間のある隅の支柱を含む）.

    面ごとに両端を含む支柱の位置 × 列から、隅で共有する内側建地と上段の端を除く。「始点＋中間（終点は次の面）」
    （plan.total_posts）× 列で数えると、各面の外側の列の終点の支柱と、隣の面の無い端の支柱が抜けていた（利用者の
    指摘 2026-10-25: 支柱の本数の数え漏れも直して）。単管抱き足場は建地が線の上の1列で、隅は隣の面と同じ1本.
    """
    n_extra = model.outer_corner_posts() + model.gap_corner_posts()
    if model.config.is_hug:
        return (model.plan.total_posts * rows + n_extra
                - rows * len(getattr(model, "skip_end_posts", None) or ()))
    return drawn_post_count(model, rows) + n_extra


def drawn_post_count(model: ScaffoldModel, rows: int) -> int:
    """足場ラインが描く支柱の位置の数（出隅の外側の角の支柱は除く）. 3d.gdl の支柱の描き分けと同じ.

    面ごとに支柱の位置（スパン数＋1）× 列。内側の列の隅の支柱は隣の面と共有して片方だけ（shared_corner_skips）、
    セットバックの上段の端（skip_end_posts）は両方の列とも描かない。一側足場は外側の1列.
    """
    return sum(face_post_positions(model, ep, rows) for ep in model.plan.edges
               if model.edge_subset is None or ep.edge_index in model.edge_subset)


def face_post_positions(model: ScaffoldModel, ep, rows: int) -> int:
    """1つの面の足場ラインが描く支柱の位置の数（両端を含む × 列。隅で共有する内側建地・上段の端は除く。出隅の
    外側の角の支柱は含まない）."""
    from .gdl_params import shared_corner_skips

    ei = ep.edge_index
    skip = getattr(model, "skip_end_posts", None) or set()
    sk = shared_corner_skips(getattr(model, "_parent_model", None) or model, ei)
    n = 0
    for row in ([1] if rows == 1 else [0, 1]):
        c = len(ep.spans) + 1
        if row == 0:
            c -= int(sk["skipInS"]) + int(sk["skipInE"])
        c -= int((ei, "s") in skip) + int((ei, "e") in skip)
        n += max(0, c)
    return n


def _feet_by_row(terrain, rows: int) -> tuple[list, int]:
    """数える脚と倍数。外側の列も地盤から解いてあれば内外の脚をそのまま（倍数1）、無ければ内側の列×列数."""
    feet = list(getattr(terrain, "feet", []) or [])
    outer = list(getattr(terrain, "feet_outer", []) or [])
    # 平らな地盤は図（足場ラインは高低差0なら脚ごとの地盤高・ジャッキを渡さない）と同じく立面の構成で数える
    # （上段で床の高さをそろえたジャッキ・敷板、千鳥の積み方が脚の一覧に入っていなかった）
    if feet and float(getattr(terrain, "gl_difference_mm", 0.0) or 0.0) <= 0.5:
        return [], rows
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
    """その面の開口部だけ. 抜いた支柱の本数・梁枠上の支柱・梁枠の高さ（開口部の番号で持つ）も付け直す（全体の抜いた
    本数のまま面ごとに引いて、面ごとの数量でジャッキが 18 本少なかった。2026-10-26 のループ）."""
    if openings is None:
        return None
    import dataclasses

    keep = [i for i, o in enumerate(openings.openings) if o.edge_index in edges]
    total_inner = sum(len(v) for v in openings.inner_posts.values())
    cut_total = getattr(openings, "cut_posts", 0)
    rows = ((openings.removed_posts + cut_total) // total_inner) if total_inner else 0
    inner = {k: openings.inner_posts[i] for k, i in enumerate(keep) if i in openings.inner_posts}
    mid = {k for k, i in enumerate(keep) if openings.openings[i].bottom_level > 0}
    return dataclasses.replace(
        openings, openings=[openings.openings[i] for i in keep],
        inner_posts=inner,
        beam_heights={k: openings.beam_heights[i] for k, i in enumerate(keep) if i in openings.beam_heights},
        bottom_heights={k: openings.bottom_heights[i] for k, i in enumerate(keep)
                        if i in getattr(openings, "bottom_heights", {})},
        # 途中の層の開口（荷受けステージの間口）は下の支柱が残るので、抜いた本数（ジャッキ）に入れない
        removed_posts=sum(len(v) for k, v in inner.items() if k not in mid) * rows,
        cut_posts=sum(len(v) for k, v in inner.items() if k in mid) * rows,
        issues=[dataclasses.replace(x, index=keep.index(x.index)) for x in openings.issues if x.index in keep])


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

    def sub(part: Optional[Part], qty: int, what: str) -> None:
        """数えた部材を差し引く（拡幅・縮幅で幅の違う腕木・布板に替える層など。内訳には負の数で残す）."""
        if qty <= 0 or part is None:
            return
        key = (part.model_no, part.category)
        counts[key] = max(0, counts.get(key, 0) - qty)
        parts[key] = part
        by = breakdown.setdefault(key, {})
        by[what] = by.get(what, 0) - qty

    rows = 1 if model.config.scaffold_form == "一側足場" else rules.rows
    posts_per_line = plan.total_posts        # 帰属ルールで二重計上なし
    # 出隅の外側コーナー支柱（内側列は隣の面とコーナー支柱を共有するが、外側列は
    # 面ごとに躯体コーナーで終わるので、四隅の外側に1本ずつ立つ）。3Dも同じ規則で描く
    n_corners = model.outer_corner_posts()
    # 隙間（コーナーステップ）のある出隅は、升目の前の面の側にも1本（model.gap_corner_post_start。3D と同じ）
    n_gap_posts = model.gap_corner_posts()
    n_posts = standing_post_positions(model, rows)
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
    # 千鳥（選んだとき）: 1本おきの支柱は隣の積み方（posts_alt）。3D と同じく半分を置き換える
    if not feet and sorted(elev.posts_alt or []) != sorted(elev.posts) and elev.posts_alt:
        n_alt = n_posts // 2
        for nominal in elev.posts:
            totals_posts[nominal] = totals_posts.get(nominal, 0) - n_alt
        for nominal in elev.posts_alt:
            totals_posts[nominal] = totals_posts.get(nominal, 0) + n_alt
        totals_posts = {k: v for k, v in totals_posts.items() if v > 0}
    if feet and n_corners + n_gap_posts:
        for nominal in elev.posts:
            totals_posts[nominal] = totals_posts.get(nominal, 0) + n_corners + n_gap_posts
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
    shim0 = int(getattr(elev, "base_shim", 0) or 0)
    _count_jacks(m, feet, per_foot, n_feet, add, notes, flat_need=float(elev.jack_extension - shim0))
    add(under, n_feet, "アンダーベース")
    _count_shims(m, feet, per_foot, add, notes)
    if not feet and shim0 > 0:
        # 全部の脚の下に重ねる敷板（セットバックの上段で床の高さをそろえるとき。ジャッキの上限を超える分）
        sp = next(iter(m.by_category("敷板")), None)
        mt = re.search(r"厚\s*(\d+)", sp.note) if sp is not None else None
        th = int(mt.group(1)) if mt else 35
        n_sh = int(math.ceil(shim0 / th - 1e-9))
        if sp is not None:
            add(sp, n_feet * n_sh, f"敷板調整（全脚 {shim0}mm・厚{th}mm×{n_sh}枚）")
        notes.action(f"ジャッキの繰出し上限を超える {shim0}mm は、全部の脚（{n_feet}脚）のジャッキの下に敷板を {n_sh}枚ずつ"
                     "重ねて持ち上げてください（床の高さを本体にそろえるため）", Notes.ORDER)
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
            + "を外しています（ステージの先端・妻側の手すり／乗り込み口のフロアーゲートか開閉式手すり／張出し外縁の手すりで防護）"
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
            # 途中の層の開口（荷受けステージの間口）があるときだけ区間の違いを書き添える
            + ("（荷受けステージの間口はステージの床より上の区間）"
               if openings is not None and openings.bottom_heights else "")
        )
    # 継ぎ足した脚の区間の根がらみ（敷地高低差）。基準の根がらみは低い脚の
    # 地盤から離れるので、区間ごとに1段追加する（図面も同じ規則で描く）
    _add_extra_negarami(model, terrain, add, notes, rows)

    # ---- 出隅コーナーの升目（外側コーナー支柱までの布材・手すり・踏板・幅木） ----
    if n_corners:
        _count_corner_parts(model, m, rules, add, notes, n_corners, n_levels)
    if n_gap_posts and not m.is_tube:
        # 隙間のある出隅の升目の前の面の側の布材（根がらみ＋各層の床。前の面の建地列間隔）
        for wa in sorted({model.row_spacing_of((e.index - 1) % len(model.plan.outline.edges))
                          for e in model.plan.outline.edges if model.gap_corner_post_start(e.index)}):
            k = len([e for e in model.plan.outline.edges if model.gap_corner_post_start(e.index)
                     and abs(model.row_spacing_of((e.index - 1) % len(model.plan.outline.edges)) - wa) < 0.5
                     and (model.edge_subset is None or e.index in model.edge_subset)
                     and (model.faces_only is None or e.index in model.faces_only)])
            ledger = m.find("布材", int(round(wa)))
            if ledger is None and not m.is_tube:
                notes.action(f"隙間のある出隅{k}箇所の升目の布材（{int(round(wa))}mm）は系列に無い長さなので、単管（1.0m）"
                             f"{k * (1 + n_levels)}本と直交クランプ{2 * k * (1 + n_levels)}個で組みます。別途手配してください",
                             Notes.ORDER)
            else:
                add(ledger, k * (1 + n_levels), f"隙間のある出隅の升目の布材{int(round(wa))}")
        notes.append(f"隅の隙間（コーナーステップ）のある出隅{n_gap_posts}箇所は、升目の前の面の側に建地1本（支柱位置数に"
                     f"含む）と布材（根がらみ＋各層の床）を足して、4本の建地で独り立ちさせて計上")

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
        # 根がらみ〜1段目の床が低い（1.0m 未満）層にはブレスを掛けず、1つ上の層へ入れる（図と同じ。利用者の指摘 2026-10-24:
        # 前も言ったけど1段目に変なブレス）。全層に入れる（1層ごと）ときは、その低い層の分だけ減る
        lv0 = list(getattr(elev, "level_heights", None) or [])
        first_lift = (float(lv0[0]) - float(getattr(elev, "first_ledger_height", 0) or 0)) if lv0 else 9999.0
        if every_l == 1 and first_lift < 999.0 and level_groups > 0:
            level_groups -= 1
        n_locations = 0
        shortfall = 0
        for e in plan.edges:
            # 斜材は規格スパン（1800）の構面に入れる。面の両端の構面には必ず（3d.gdl と同じ。brace_starts）
            fit_bays = sum(1 for s in e.spans if s == brace.nominal_dim)
            want = len(brace_starts(e.span_count, every_s))
            n_locations += min(want, fit_bays) * level_groups
            shortfall += max(0, want - fit_bays) * level_groups
        add(brace, n_locations * rules.braces_per_location, "斜材（ブレス）")
        notes.append(
            f"斜材は{every_s}スパン×{every_l}層以下毎に交さ2方向で計上"
            f"（{n_locations}箇所×{rules.braces_per_location}本）。"
            "全構面に入れる場合は QuantityRules の brace_every_spans/levels を1にしてください"
        )
        if openings is not None and getattr(openings, "openings", None):
            # 開口の通路（梁枠より下）は建地を抜くので筋かいを掛けられない。図には描かず、数量は隣の構面へ移す扱いで同じ
            # （利用者の指摘 2026-10-24: 1層目の両サイドに謎のブレス）
            notes.append("開口の通路（梁枠より下）に掛かる斜材は図に描かず、隣の構面へ移して入れる扱い（数量は同じ）")
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
    # はしごで昇降する計画（地足場の2層以下など。ladders）で階段室を置いていなければ階段は数えない（既定の階段数1で
    # 階段2台・階段手すり4本を数えていた。実機 2026-10-25）
    if stair_plan is not None and not stair_plan.towers and int(getattr(model.config, "ladders", 0) or 0) > 0:
        n_towers = 0
    add(stair, n_towers * n_levels, "階段")
    _count_stair_guards(model, add, notes, n_towers, n_levels,
                        outside=bool(getattr(stair_plan, "outside", False)))
    _count_outside_stairs(model, stair_plan, add, notes)

    _count_asagao_parts(model, span_counts, posts_per_line, add, notes, kt)
    _count_horizontal_net(model, add, notes)
    _count_sheets(model, add, notes, stair_plan)
    _count_open_ends(model, add, notes)
    _count_hane_brackets(model, notes)
    _count_widen_brackets(model, add, notes)
    _count_width_change(model, add, sub, notes, stair_plan)
    _count_sill_boards(model, notes, terrain, stair_plan)
    _count_roof_bridges(model, add, notes)
    _note_tier_gangways(model, notes)
    _count_intakes(model, notes)
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

    荷受けステージの間口（設置層）と、昇降機の乗り込み口（乗り込む層の、荷台の長さに掛かる
    スパン。固定の手すりの代わりに開閉式手すりが付く）。3D・立面も同じ区間を空ける
    """
    from .platforms import _edge, _span_index

    from .openings import stage_openings

    out: dict[int, int] = {}
    for s in (getattr(platforms, "stages", None) or []):
        # 間口の開口（途中の層の開口）の中に入る層は開口の控除で外してあるので、ここでは引かない（二重に引いていた）
        ops = stage_openings(model, [s])
        n_lv = sum(1 for lv in (s.levels or [1])
                   if not any(o.bottom_level < lv < o.level for o in ops))
        for nominal in s.spans(model):
            out[nominal] = out.get(nominal, 0) + n_lv
    from .openings import hoist_voids

    for h in (getattr(platforms, "hoists", None) or []):
        edge = _edge(model, h.edge_index)
        if edge is None or not edge.spans or hoist_voids(model, [h]):
            continue    # 昇降路（足場を全高で抜く）のスパンは開口部の控除で全部抜いてある（二重に引かない）
        # 荷台の長さに掛かるスパン（ロングスパンの荷台は 2〜3 スパンに掛かる。3D の開閉式手すりと同じ）
        for i in (h.gate_spans(model) or [min(_span_index(edge, h.position_mm), len(edge.spans) - 1)]):
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
    if m.find("布材", udegi) is None and not m.is_tube:
        # 系列に無い長さ（日建の一側足場のブラケット 350 の升目など）はくさびの布材で組めない。単管とクランプで組む
        n_t = n_corners * per_corner
        notes.action(f"出隅コーナー{n_corners}箇所の升目（{udegi}mm角）は系列 {m.series_id} に長さ{udegi}の布材が無いので、"
                     f"単管（1.0m）{n_t}本と直交クランプ{2 * n_t}個（2辺×〈根がらみ1＋各層の床・手すり・中桟3〉×{n_levels}層）"
                     "で組みます。別途手配してください", Notes.ORDER)
    else:
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
    if model.config.has_toe_board and toe is not None:
        add(toe, n_corners * n_levels * 2, f"出隅コーナーの幅木{udegi}")
    if toe is None and model.config.has_toe_board:
        # 同じ部材を「マスタに該当部材がありません」と二重に出さない
        notes.action(
            f"出隅コーナーの幅木（呼び{udegi}mm、{n_corners * n_levels * 2}本）が系列のマスタにありません。"
            "幅木（足場板・幅木の端材）を別途手配してください",
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


def _count_jacks(m: PartMaster, feet, rows: int, n_feet: int, add, notes, suffix: str = "",
                 flat_need: Optional[float] = None) -> None:
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
    if all(p.max_extension_mm() is None for p in jacks):
        add(default, n_feet, "ジャッキ" + suffix)
        return
    if not feet:
        # 平らな地盤: 全部の脚が同じ繰出し。受けられる中で最も短い品（標準のジャッキベースで届かなければロング）
        fit = default
        if flat_need is not None:
            fit = next((p for p in ranked if p.max_extension_mm() is None or flat_need <= p.max_extension_mm() + 1e-6),
                       ranked[-1])
        add(fit, n_feet, "ジャッキ" + suffix if fit is default
            else f"ジャッキ（繰出し{default.max_extension_mm()}mm超: {fit.model_no}）" + suffix)
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
        # 高低差の解は敷板（厚35）の枚数で持ち上げるので、マスタに無くても枚数で手配できる
        from .terrain import SHIM_UNIT_MM

        n = sum(math.ceil(a / SHIM_UNIT_MM - 1e-9) for _, a in raises) * rows
        notes.action(
            f"敷板調整の脚{len(raises) * rows}本に敷板（厚{SHIM_UNIT_MM}mm）計{n}枚を別途手配してください"
            "（系列のマスタに無い。ジャッキの下に重ねる短い板。脚ごとの枚数はジャッキ量一覧の敷板調整欄）",
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
    span_counts, posts_per_line, (skipped, partial) = _asagao_faces_only(model, span_counts, posts_per_line)
    if not span_counts:
        return
    if skipped:
        notes.append(f"朝顔は {'・'.join(skipped)} には付けていません（付ける面を選んだ計画）")
    if partial:
        notes.append(f"朝顔は {'、'.join(partial)}（面の始点の支柱から mm）だけに付けています（線で範囲を選んだ計画）")
    stages = asagao.stages
    # 途中の屋根で止めた面など、床の無い段の朝顔は付かない（asagao_heights_of）。面ごとの段数が全体の段数より少ない面が
    # あれば、スパン・支柱を面ごとの段数で数え直す（全体の段数×全部の面で数えていた。2026-10-27 のループ）
    own = {e.edge_index: len(model.asagao_heights_of(e.edge_index)) for e in model.plan.edges
           if model.asagao_on(e.edge_index) and (model.edge_subset is None or e.edge_index in model.edge_subset)}
    if own and any(v < stages for v in own.values()):
        w_counts: dict[int, int] = {}
        w_posts = 0
        for e in model.plan.edges:
            k = own.get(e.edge_index, 0)
            if not k:
                continue
            x = 0.0
            flags = []
            for sp in e.spans:
                flags.append(model.asagao_at(e.edge_index, x + sp / 2.0))
                x += sp
            for sp, f in zip(e.spans, flags):
                if f:
                    w_counts[sp] = w_counts.get(sp, 0) + k
            w_posts += k * (sum(flags) + sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1])))
        span_counts, posts_per_line, stages = w_counts, w_posts, 1
        asagao = dataclasses.replace(asagao, stages=1)
    span_counts, posts_per_line = _asagao_minus_hoists(model, span_counts, posts_per_line, own, asagao.stages, notes)
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
               and model.asagao_reaches(e.index, at_end=False)
               and model.asagao_reaches((e.index - 1) % len(model.plan.outline.edges), at_end=True)]
    if corners:
        corner_part = next((p for p in m.by_category("朝顔") if "コーナー" in p.note), None)
        n_out = len(model.plan.outline.edges)
        # 面ごとの段数で数え直したときは、隅を挟む2面の少ない方の段数
        c_stages = (sum(min(own.get(e.index, 0), own.get((e.index - 1) % n_out, 0)) for e in corners)
                    if stages == 1 and own and any(v != asagao.stages for v in own.values()) else len(corners) * asagao.stages)
        if corner_part is not None:
            add(corner_part, c_stages, "朝顔コーナー（出隅）")
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


def _asagao_minus_hoists(model: ScaffoldModel, span_counts: dict, posts_per_line: int, own: dict, stages: int,
                         notes) -> tuple[dict, int]:
    """昇降機のマスト・搬器が通るスパン（model.hoist_spans。図の asaCutList と同じ）は朝顔を切り欠くので、数量から引く
    （2026-10-27 のループ: 衝突の注意は「切り欠く」と言いながら、数量は切り欠き前の全スパンだった）.

    span_counts は段数を掛ける前（面ごとの段数で数え直したときは段数込み）。受けの支柱は切り欠きの両側に残るので、
    切り欠いたスパンの数−1 だけ減らす（面の端まで切り欠くときも安全側に同じ）。
    """
    spans_by_edge = getattr(model, "hoist_spans", None) or {}
    if not spans_by_edge:
        return span_counts, posts_per_line
    counts = dict(span_counts)
    posts = posts_per_line
    cut_txt = []
    for e in model.plan.edges:
        if not model.asagao_on(e.edge_index) or (model.edge_subset is not None and e.edge_index not in model.edge_subset):
            continue
        k = own.get(e.edge_index, stages) if own and any(v < stages for v in own.values()) else 1
        for s0, e0 in spans_by_edge.get(e.edge_index, []):
            x = 0.0
            n = 0
            for sp in e.spans:
                mid = x + sp / 2.0
                if s0 - 1.0 <= mid <= e0 + 1.0 and model.asagao_at(e.edge_index, mid) and counts.get(sp, 0) >= k:
                    counts[sp] -= k
                    n += 1
                x += sp
            if n:
                posts -= k * max(0, n - 1)
                cut_txt.append(f"{model.face_name(e.edge_index)} {s0:.0f}〜{e0:.0f}（{n}スパン）")
    if cut_txt:
        notes.append("昇降機が通るスパン（" + "・".join(cut_txt) + "）は朝顔を切り欠くので、数量から引いています"
                     "（その開口は昇降機メーカー仕様の防護で塞ぐ）")
    return {sp: n for sp, n in counts.items() if n > 0}, max(0, posts)


def _asagao_faces_only(model: ScaffoldModel, span_counts: dict, posts_per_line: int):
    """朝顔を付ける面・区間を選んだ計画（model.asagao_edges・asagao_ranges）なら、そのスパンだけのスパン数・支柱数
    → (スパン数, 支柱数, (付けない面名, 一部だけの面と区間の文)).

    付ける面が全部なら渡されたまま。支柱は続いたスパンの並びごとにスパン数＋1 を足し、隅で隣の面の朝顔に続くときは
    隅の支柱を1本に数える。区間はスパンの中ほどが入るスパンを数える。
    """
    if model.asagao_edges is None and not model.asagao_ranges:
        return span_counts, posts_per_line, ([], [])
    mine = [e for e in model.plan.edges if model.asagao_on(e.edge_index)
            and (model.edge_subset is None or e.edge_index in model.edge_subset)]
    counts: dict[int, int] = {}
    n = len(model.plan.outline.edges)
    on = {e.edge_index for e in mine}
    posts = 0
    for e in mine:
        x = 0.0
        flags = []
        for sp in e.spans:
            flags.append(model.asagao_at(e.edge_index, x + sp / 2.0))
            x += sp
        for sp, f in zip(e.spans, flags):
            if f:
                counts[sp] = counts.get(sp, 0) + 1
        runs = sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1]))
        posts += sum(flags) + runs
        nxt = (e.edge_index + 1) % n
        if flags and flags[-1] and nxt in on and model.asagao_reaches(nxt, at_end=False) \
                and model.asagao_reaches(e.edge_index, at_end=True):
            posts -= 1
    names = dict(zip([e.edge_index for e in model.plan.edges], model.plan.face_names()))
    skipped = [names[e.edge_index] for e in model.plan.edges if e.edge_index not in on]
    partial = [names[e.edge_index] + "の" + "・".join(f"{a:.0f}〜{b:.0f}" for a, b in model.asagao_parts(e.edge_index))
               for e in mine if model.asagao_parts(e.edge_index) is not None]
    return counts, posts, (skipped, partial)


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
        # 張出しの幅ちょうどの部材が無ければ、系列にある少し長いもの（＋100 まで。幅 600 に枠組の 610 など）
        rail = _fit_longer(m, "布材", w)
        add(rail, 2 * 2 * n_lv, f"張出し妻側の手すり・中桟{rail.nominal_dim if rail else w}")
        if model.config.has_toe_board:
            toe = _fit_longer(m, "幅木", w)
            add(toe, 2 * n_lv, f"張出し妻側の幅木{toe.nominal_dim if toe else w}")

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
        if o.void:
            continue     # 昇降路（全高で抜く）は梁枠を入れない
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
    # 補強のつなぎ材（日建 カタログ p010「梁枠の両サイドには、つなぎ材（補強）」と組立の標準例の図。3D と同じ）: 梁枠の高さで
    # 開口の両隣のスパン、床の高さで開口の上のスパンに、内外の建地列ごとに布材1本（利用者の指定 2026-10-24: つなぎ材も数量に入れて）
    ties_by_span: dict[int, int] = {}
    for o in openings.openings:
        ep = next((e for e in model.plan.edges if e.edge_index == o.edge_index), None)
        if ep is None or o.void:
            continue
        x = 0.0
        for sp in ep.spans:
            sp = float(sp)
            beside = abs(x + sp - o.start_mm) < 1.0 or abs(x - o.end_mm) < 1.0
            over = x >= o.start_mm - 1.0 and x + sp <= o.end_mm + 1.0
            if beside or over:
                ties_by_span[int(round(sp))] = ties_by_span.get(int(round(sp)), 0) + rows
            x += sp
    for sp, n in sorted(ties_by_span.items()):
        part = m.find("布材", sp)
        if part is None:
            notes.action(f"梁枠の補強のつなぎ材（布材{sp}・{n}本）がマスタにありません。別途手配してください")
        else:
            add(part, n, f"梁枠の補強のつなぎ材{sp}（梁枠の高さで両隣・床の高さで開口の上）")
    if ties_by_span:
        notes.append(f"梁枠の補強のつなぎ材 {sum(ties_by_span.values())}本（梁枠の高さで開口の両隣のスパン、床の高さで開口の上の"
                     "スパン。内外の建地列ごと）を計上")

    # 妻面のブレス材（先行手すり）と妻面幅木（日建 カタログ p010。3D と同じ）: 開口の両端の妻面に、梁枠より下の各段（根がらみの段
    # と作業床の段）の先行手すり、作業床の段に幅木。長さは建地列の間隔（利用者の指定 2026-10-24: 妻面のブレスと妻面幅木も入れて）
    if rows == 2 and not m.is_frame and not m.is_tube and not model.config.is_hug:
        row = int(round(model.post_row_spacing_mm))
        n_br = n_toe = 0
        for i, o in enumerate(openings.openings):
            ev = model.elevation_of(o.edge_index)
            bh = float(openings.beam_heights.get(i, 0.0))
            bb = float(openings.bottom_heights.get(i, -1.0))       # 途中の層の開口は床から上だけ
            below = [z for z in [ev.first_ledger_height] + list(ev.level_heights) if bb - 1e-6 <= z < bh - 1e-6]
            n_br += 2 * len(below)
            n_toe += 2 * sum(1 for z in ev.level_heights if bb + 1e-6 < z < bh - 1e-6)
        for cat, n, what in (("先行手摺", n_br, "ブレス材（先行手すり）"), ("幅木", n_toe, "妻面幅木")):
            if not n:
                continue
            part = m.find(cat, row)
            if part is None:
                notes.action(f"梁枠下の妻面の{what}（長さ{row}・{n}本）がマスタにありません。別途手配してください")
            else:
                add(part, n, f"梁枠下の妻面の{what}{row}")
        if n_br:
            # ミレニュームは Q&A Q16 に妻面の記載が無いが、ND と同じに入れる（利用者の指定 2026-10-24: ミレニュームにも妻面の
            # ブレスと幅木入れて）
            src = ("日建 カタログ p010「梁枠下の妻面全段」と同じ扱い（ミレニュームにも入れる。利用者の指定 2026-10-24）"
                   if m.series_id == "nikken_millennium" else "日建 カタログ p010「梁枠下の妻面全段」")
            notes.append(f"梁枠下の妻面（開口の両端の建地の内外）に、各段のブレス材（先行手すり）{n_br}本と作業床の段の妻面幅木"
                         f"{n_toe}本を計上（{src}）")

    # 梁枠の網掛け部（開口の両隣1スパンの全高と梁枠の上）の前踏み側の先行手すり筋交い（ミレニューム Q16）
    from .openings import beam_rules, front_adv_spans

    if beam_rules(model).get("front_adv"):
        per_span: dict[int, int] = {}
        for ep in model.plan.edges:
            lv = list(model.elevation_of(ep.edge_index).level_heights)
            starts = [0.0]
            for s in ep.spans:
                starts.append(starts[-1] + float(s))
            for a, b, z in front_adv_spans(model, ep.edge_index, openings):
                n_lv = sum(1 for h in lv if h >= z - 1e-6)
                for s0, sp in zip(starts, ep.spans):
                    if s0 >= a - 1.0 and s0 + sp <= b + 1.0:
                        per_span[int(sp)] = per_span.get(int(sp), 0) + n_lv
        for sp, n in sorted(per_span.items()):
            part = m.find("先行手摺", sp)
            if part is None:
                notes.action(f"前踏み側の先行手すり筋交い（スパン{sp}・{n}本）がマスタにありません。別途手配してください")
            else:
                add(part, n, f"梁枠の網掛け部の前踏み側の先行手すり筋交い スパン{sp}")
        if per_span:
            notes.append("梁枠の網掛け部（開口の両隣1スパンの全高と梁枠の上）は、前踏み側にも先行手すり筋交いを"
                         f"{sum(per_span.values())}本入れる（{beam_rules(model)['source']}。前踏み側の手すり・中桟は差し引いていない）")
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
    # 盛り替えるステージは1組だけ手配する（上の層へ組み直して使う。層の数だけ掛けない）
    for st in platforms.stages or []:
        if st.relocate_levels:
            notes.append(f"荷受けステージ（{model.face_name(st.edge_index)} 始点から{st.start_mm:.0f}mm）は"
                         f"{st.relocation_text()}。部材は1組で計上")
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

    # 昇降路の前養生は張る範囲を注記に残す（マスタにある品で拾えると、手配の注記に範囲が出ない）
    from .platforms import hoistway_guard_demands

    for h in platforms.hoists or []:
        g = hoistway_guard_demands(model, h)
        if g:
            notes.append(f"{model.face_name(h.edge_index)}の昇降機（始点から{h.position_mm:.0f}mm）の昇降路は前養生で塞ぐ: "
                         + g[0].detail + "（足場のシートは昇降路で途切れるため。落下物の防護 安衛則537条・建築基準法施行令"
                         "136条の5、国交省 建設工事安全マニュアル リフト工の養生囲い）")
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


def _count_intakes(model: ScaffoldModel, notes) -> None:
    """取り入れ口（資材の取り込み口。利用者の指定 2026-10-24）: 可動手すり・クランプとシートの開け方を手配に出す."""
    from .intakes import intake_note, mine

    if not mine(model):
        return

    notes.action(intake_note(model), Notes.ORDER)


def _fit_longer(m: PartMaster, category: str, length: int, slack: int = 100):
    """長さ length の部材。ちょうどが無ければ、それより長く slack 以内のいちばん短いもの（無ければ None）."""
    hit = m.find(category, length)
    if hit is not None:
        return hit
    longer = [p for p in m.by_category(category) if length < p.nominal_dim <= length + slack]
    return min(longer, key=lambda p: p.nominal_dim) if longer else None


GANGWAY_MIN_GAP_MM = 200.0     # これより広いあきは渡り板（足場板 厚28）。狭いあきはすき間板


def _note_tier_gangways(model: ScaffoldModel, notes) -> None:
    """屋根の縁の内側で止めた上段の端から本体の床へ渡る渡り板（足場板）を手配の注記に出す（利用者の指定 2026-10-26）."""
    ends = {k: g for k, g in (getattr(model, "free_gap_ends", None) or {}).items() if g > GANGWAY_MIN_GAP_MM}
    if not ends:
        return
    levels = max(1, int(model.elevation.n_levels))
    parts = []
    total = tubes = 0
    tube_l = 1000
    for (ei, end), g in sorted(ends.items(), key=lambda kv: (kv[0][0], kv[0][1] != "s")):
        # 両側の床に 150 ずつ掛ける長さ。足場板は 1.0・1.5・2.0m
        L = next((v for v in (1000, 1500, 2000) if v >= g + 300.0), 2000)
        per = max(1, int(round((model.row_spacing_of(ei) - 60.0) / 240.0)))
        total += per * levels
        tubes += 4 * levels
        tube_l = max(tube_l, L)
        parts.append(f"{model.face_name(ei)}の{'始点' if end == 's' else '終点'}（あき {g:.0f}）足場板{L / 1000:.1f}M×{per}枚×{levels}層")
    notes.action("上段の端から本体の床へ渡る渡り板: " + "・".join(parts) + f"（計 {total}枚）。両側の床に 150 以上掛けて"
                 f"番線で留め、両脇は手すり・中桟（単管{tube_l / 1000:.1f}M {tubes}本・直交クランプ {2 * tubes}個）で塞いでください"
                 "（数量に含んでいません）", Notes.ORDER)


def _count_roof_bridges(model: ScaffoldModel, add, notes) -> None:
    """屋上への渡り（足場の部材で組む。roof_bridges）の部材を拾う（利用者の指定 2026-10-26: 布材かブラケット出して
    支柱で足元つくかブラケットで浮かせる、アンチ引いて手すりも布材、枠の場合は単管と足場板）."""
    # 面ごとに高さが違えば数量は同じ高さの面の組ごと。渡りはその面の組でだけ出す（二重に手配しない）
    bs = [b for b in getattr(model, "roof_bridges", None) or []
          if model.edge_subset is None or b.edge_index in model.edge_subset]
    if not bs:
        return
    from .roof_bridges import bridge_note, plank_len

    m = model.master
    for b in bs:
        w, L = int(round(b.width_mm)), int(round(b.length_mm))
        tag = "屋上への渡り"
        if b.kind == "支柱":
            # 布材: 両脇の腕木（アンチを横引きで掛ける）・中桟・手すり（L×6）、屋上の支柱どうし（スパン×1）
            add(m.find("布材", L), 6, f"布材{L}（{tag}の両脇の腕木・中桟・手すり）")
            add(m.find("布材", w), 1, f"布材{w}（{tag}の屋上の支柱どうし）")
            add(m.find("支柱", int(b.post_mm)), 2, f"支柱{b.post_mm:.0f}（{tag}の屋上の支柱）")
            jack = next(iter(sorted(m.by_category("ジャッキ"), key=lambda p: p.nominal_dim, reverse=True)), None)
            add(jack, 2, f"ジャッキ（{tag}の屋上の支柱）")
            for dw in b.deck:
                add(m.deck_parts(int(dw), w), 1, f"アンチ 幅{dw}×{w}（{tag}。横引き）")
            add(m.find("幅木", L), 2, f"幅木{L}（{tag}の両脇）")
        elif b.kind == "ブラケット":
            br = m.get(b.bracket.split()[0]) if b.bracket else None
            add(br, 2, f"{b.bracket}（{tag}）")
            if m.find("布材", L) is not None:
                add(m.find("布材", L), 4, f"布材{L}（{tag}の両脇の中桟・手すり）")
            else:
                notes.action(f"{tag}: ブラケット{L}の長さの布材が系列のマスタに無いので、両脇の手すり・中桟は単管"
                             f"（1.0m）4本と直交クランプ8個で組みます。別途手配してください", Notes.ORDER)
            tip = int(b.post_mm)
            add(m.find("支柱", tip), 2, f"支柱{tip}（{tag}のブラケットの先端のホゾに立てて手すりを受ける）")
            for dw in b.deck:
                add(m.deck_parts(int(dw), w), 1, f"アンチ 幅{dw}×{w}（{tag}）")
        else:
            # 単管と足場板（枠組・単管）。単管は両脇の受け・中桟・手すり（3本×2）、2 は足場板の受け2本と屋上の支柱2本
            tube_need = L + 200.0
            n_side = 6
            from .roof_bridges import _tube_len

            add(m.find("単管", int(_tube_len(tube_need, m))), n_side, f"単管（{tag}の両脇の受け・中桟・手すり）")
            n_clamp = 2 * n_side
            if b.kind == "単管支柱":
                add(m.find("単管", int(_tube_len(w + 200.0, m))), 1, f"単管（{tag}の屋上の建地どうし）")
                add(m.find("単管", int(b.post_mm)), 2, f"単管（{tag}の屋上の建地）")
                base = m.get("A15")
                add(base, 2, f"ベース（{tag}の屋上の建地）")
                n_clamp += 2 + 6
            else:
                add(m.find("単管", 1000), 2, f"単管（{tag}の先端の手すり柱）")
                n_clamp += 4
            clamp = m.get("ARC1")
            add(clamp, n_clamp, f"直交クランプ（{tag}）")
            plank = next((p for p in m.parts if p.model_no.startswith("足場板") and p.actual_dim == b.deck_len_mm), None)
            add(plank, len(b.deck), f"足場板（{tag}の床）")
            toe = next((p for p in m.parts if p.model_no.startswith("足場板") and p.actual_dim == plank_len(L + 200.0, m)),
                       None)
            add(toe, 2, f"足場板（{tag}の幅木）")
    # 部材は数量に含める（足場の部材で組む）。組み方と段差は現場で確かめる項目として要確認へ
    for b in bs:
        if b.ext_mm:
            if b.tube:
                add(m.find("単管", int(b.ext_mm)), 2, "単管（屋上への渡りの手すりを受ける建地の継ぎ足し）")
                add(m.get("ARC1"), 4, "直交クランプ（屋上への渡りの建地の継ぎ足し）")
            else:
                add(m.find("支柱", int(b.ext_mm)), 2, f"支柱{b.ext_mm:.0f}（屋上への渡りの手すりを受ける内側の支柱の継ぎ足し）")
    notes.action(bridge_note(bs, model) + "。部材は数量に含めています（足場の部材で組む）。組み方・段差を現場で確かめてください",
                 Notes.SITE)


def _count_sill_boards(model: ScaffoldModel, notes, terrain=None, stair_plan=None) -> None:
    """ジャッキベースの下の敷板（杉の足場板 幅240・厚35。利用者の指定 2026-10-25: ジャッキベースの下に敷板規格の長さ…を
    配置して）。平らな地盤は建地の列に沿って規格の長さで通し、最後は切って使う（sill_boards。図と同じ）。高低差のある
    地盤は脚ごとに 1m を1枚（図と同じ）."""
    from .gdl_params import SILL_LENGTHS_MM, sill_on

    if not sill_on(model):
        return
    sloped = bool(terrain is not None and getattr(terrain, "feet", None) and terrain.gl_difference_mm > 0.5)
    if sloped:
        rows = 1 if model.config.scaffold_form == "一側足場" or model.master.is_tube and model.config.is_hug else 2
        n = sum(rows * (len(e.spans) + 1) for e in model.plan.edges
                if model.edge_subset is None or e.edge_index in model.edge_subset)
        counts, cut = ({SILL_LENGTHS_MM[-1]: n} if n else {}), 0
    else:
        from .sill_boards import counts as sill_counts

        counts, cut = sill_counts(model, stair_plan, model.edge_subset)
    if not counts:
        return
    notes.action(sill_note(counts, cut), Notes.ORDER)


SILL_NOTE_HEAD = "ジャッキベースの下の敷板"


# 手配の行の「品目×数」の並び（敷板 4m×11・3m×1、シート 幅914×3枚・幅1524×3枚）と「N個・N枚・N箇所」
_COUNT_RUN = re.compile(r"[^\s・：:、。（）()]+?×\d+(?![\d.])枚?(?:・[^\s・：:、。（）()]+?×\d+(?![\d.])枚?)*")
_COUNT_ITEM = re.compile(r"([^\s・：:、。（）()]+?)×(\d+)(?![\d.])(枚?)")
_COUNT_NUM = re.compile(r"(\d+)(個|枚|箇所)")
_COUNT_SLOT = re.compile(r"\{L\}|#(個|枚|箇所)")


def _count_shape(w: str):
    runs = [[(m.group(1), int(m.group(2)), m.group(3)) for m in _COUNT_ITEM.finditer(r.group(0))]
            for r in _COUNT_RUN.finditer(w)]
    key = _COUNT_RUN.sub("{L}", w)
    nums = [int(m.group(1)) for m in _COUNT_NUM.finditer(key)]
    return _COUNT_NUM.sub(r"#\2", key), runs, nums


def merge_counted_warnings(warnings: list[str]) -> tuple[list[str], dict[str, str]]:
    """数だけが違う手配の行（面の高さの組ごとに拾った敷板・シート・クランプ）を、品目ごとに足して1行にする
    → (まとめた一覧, 元の文 → まとめた文).

    面ごとに高さが違う建物は同じ高さの面の組ごとに数量を拾う（_merge_results）。手配の行が組ごとに別々に並び、
    合計がどこにも無かった（2026-10-27 のループ: 張り出しの検証で敷板が3行・特殊シートが3行）。
    """
    groups: dict[str, list] = {}
    order: list[str] = []
    for w in warnings:
        key, runs, nums = _count_shape(w)
        if not runs and not nums:
            key = "\0" + w
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((w, runs, nums))
    out: list[str] = []
    mapping: dict[str, str] = {}
    for key in order:
        g = groups[key]
        if len(g) == 1 or key.startswith("\0"):
            text = g[0][0]
        else:
            n_runs = max(len(x[1]) for x in g)
            merged_runs = []
            for k in range(n_runs):
                tot: dict[str, int] = {}
                suffix: dict[str, str] = {}
                for _w, runs, _n in g:
                    for name, cnt, suf in (runs[k] if k < len(runs) else []):
                        tot[name] = tot.get(name, 0) + cnt
                        suffix[name] = suf
                names = list(tot)
                lens = [re.fullmatch(r"(\d+(?:\.\d+)?)m", nm) for nm in names]
                widths = [re.fullmatch(r"幅(\d+)", nm) for nm in names]
                if all(lens):
                    names.sort(key=lambda nm: -float(nm[:-1]))
                elif all(widths):
                    names.sort(key=lambda nm: int(nm[1:]))
                # 「4m×4・3m×2枚」のように並びの末尾にだけ「枚」が付く書き方は、まとめても末尾にだけ付ける
                tail = any(len(runs[k]) > 1 and not all(sf for _n, _c, sf in runs[k])
                           for _w, runs, _n in g if k < len(runs))
                if tail:
                    end = next((sf for _w, runs, _n in g if k < len(runs) for _n2, _c, sf in runs[k] if sf), "")
                    merged_runs.append("・".join(f"{nm}×{tot[nm]}" for nm in names) + end)
                else:
                    merged_runs.append("・".join(f"{nm}×{tot[nm]}{suffix[nm]}" for nm in names))
            sums = [sum(x[2][k] for x in g) for k in range(len(g[0][2]))]
            it_runs, it_nums = iter(merged_runs), iter(sums)

            def fill(m, it_runs=it_runs, it_nums=it_nums):
                return next(it_runs) if m.group(0) == "{L}" else f"{next(it_nums)}{m.group(1)}"

            text = _COUNT_SLOT.sub(fill, key)
        if text not in out:
            out.append(text)
        for w, _r, _n in g:
            mapping[w] = text
    return out, mapping


def sill_note(counts: dict[int, int], cut: int) -> str:
    from .gdl_params import SILL_T_MM, SILL_W_MM

    txt = "・".join(f"{ln / 1000:g}m×{n}" for ln, n in sorted(counts.items(), reverse=True))
    return (f"{SILL_NOTE_HEAD}（杉の足場板 幅{SILL_W_MM:.0f}・厚{SILL_T_MM:.0f}）{txt}枚を手配してください"
            "（建地の列に沿って通す。ジャッキの繰出しは敷板の上から）"
            + (f"。うち{cut}枚は列の端で切って使う（端の脚の少し先まで。飛び出さない）" if cut else ""))


def _count_hane_brackets(model: ScaffoldModel, notes) -> None:
    """跳ね出しブラケット（張り出した上の階の上段の足場を、床スラブの縁から持ち出して受ける。利用者の指定 2026-10-24:
    上階で拡張する仕組み・2026-10-25: もっと詳細にして）。系列のマスタに無い（現場ごとの製作・リース品）ので、3D と
    同じ数え方で手配に出す: ブラケット（支柱の位置ごと。隅の支柱は両方の面から1基ずつ）、出隅の角の渡し梁、アンカー
    M16（床スラブの縁の取付プレート4本・方杖／吊り材の取付プレート2枚×2本）、横に流す H形鋼（内外の建地列の下に面の端から端まで）."""
    if not getattr(model, "hane_bracket", False):
        return
    eps = [e for e in model.plan.edges if model.edge_subset is None or e.edge_index in model.edge_subset]
    # 床スラブの外の端の支柱はブラケットを壁に留められず、床スラブの端の手前に足したブラケットから渡し梁で受ける
    # （setback_tiers.hane_bridges の hane_slab_range。3D と同じ）
    rng = getattr(model, "hane_slab_range", None) or {}
    n = 0
    beams: list[float] = []
    for e in eps:
        x0, x1 = rng.get(e.edge_index, (0.0, float(sum(e.spans))))
        xs = [0.0]
        for sp in e.spans:
            xs.append(xs[-1] + sp)
        n += sum(1 for x in xs if x0 - 1.0 <= x <= x1 + 1.0)
        for xa, xe in ((x0, 0.0), (x1, xs[-1])):
            if abs(xe - xa) > 10.0:
                n += 1
        # 横に流す H形鋼（内外の建地列の下に面の端から端まで。3D と同じ。利用者の指定 2026-10-25: 横に流すHこうもいるんじゃない？）
        beams += [xs[-1] + 150.0] * 2
    n_corner = sum(1 for e in eps if model.corner_kind_start(e.edge_index) == "出隅")
    brace = getattr(model, "hane_type", "方杖") == "方杖"
    strut = (f"方杖 φ48.6×2・下の階の壁の取付プレート 150×150×12×2（床の天端から "
             f"{int(round(float(getattr(model, 'hane_drop_mm', 900.0))))}mm 下）" if brace else
             f"吊り材 φ48.6×2・上の階の壁の取付プレート 150×150×12×2（床の天端から {HANE_NOTE_DEPTH}mm 上）")
    beam_txt = "・".join(f"L={v / 1000:.2f}m" for v in beams)
    notes.action(f"跳ね出しブラケット（{'方杖' if brace else '吊り'}）{n}基（溝形鋼［-100×50×5 の腕・床スラブの縁の取付プレート "
                 f"200×250×12・{strut}・受けプレート）、横に流す H形鋼 H-150×75×5×7 {len(beams)}本（{beam_txt}。内外の"
                 "建地列の下、支柱は H形鋼の上の受けプレートに立つ）"
                 + (f"、出隅の角の渡し梁（溝形鋼）{2 * n_corner}本" if n_corner else "")
                 + f"、あと施工アンカー M16 {8 * n}本。マスタに無いので別途手配し、アンカーの引抜き・床スラブの縁の"
                 "耐力・H形鋼の曲げを確認してください", Notes.ORDER)


HANE_NOTE_DEPTH = 600


def _count_widen_brackets(model: ScaffoldModel, add, notes) -> None:
    """跳ね出しの上段の端の張出ブラケットと、張り出しの横の本体の足場の隅の升目を広げる拡幅ブラケット（setback_tiers.
    hane_bridges・3D の gosub 758／759 と同じ。reports/くさび式足場の拡幅ブラケット.md）と、高さの違う出隅で低い面の
    天端より上の升目の辺の布材・手すり（gdl_params.corner_tower_params）.

    張出（端の先、各層）: ブラケット2基・先端の手すり柱（支柱 1350）2本・床（610 は 500 幅の布板1枚）・腕の先と外側の
    脇の手すり・中桟。拡幅（隅の升目の外、全高で1回）: ブラケット2基・補強単管2本（クランプ4個）・先端の支柱（天端まで）
    2本、各層に元の支柱と先端の支柱をつなぐ布材（床・手すり・中桟）・先端どうしの床の布材・240 幅の布板、隣の足場の
    床とのあきが 3cm を超えればすき間板."""
    from .gdl_params import corner_tower_params

    m = model.master
    row = int(model.post_row_spacing_mm)
    eps = [e for e in model.plan.edges if model.edge_subset is None or e.edge_index in model.edge_subset]

    def post_of(nominal: int):
        return next((p for p in m.by_category("支柱") if p.nominal_dim == nominal
                     and "根がらみ" not in p.note and "屋根" not in p.note), None)

    def bracket(w: int, kind: str):
        return next((p for p in m.by_category("ブラケット") if p.nominal_dim == w and kind in p.note), None)

    order: list[str] = []
    # ---- 張出ブラケット（跳ね出しの上段の端の先、各層） ----
    n_over: dict[int, int] = {}
    for (ei, _end), w in (getattr(model, "hane_end_ext", None) or {}).items():
        if model.edge_subset is not None and ei not in model.edge_subset:
            continue
        w = int(w)
        k = len(model.elevation_of(ei).level_heights)
        # 内側の支柱を本体の隅の升目と共有する端は、ブラケット・先端の手すり柱が外側の1本だけ
        nb = 1 if (ei, _end) in (getattr(model, "hane_shared_ends", None) or set()) else 2
        n_over[w] = n_over.get(w, 0) + nb * k
        add(post_of(1350), nb * k, "張出ブラケットの先端の手すり柱（支柱1350）")
        if w > 540:
            add(m.deck_parts(500, row), k, f"張出ブラケットの床（布板 500×{row}）")
        else:
            add(m.deck_parts(240, row), max(1, (w - 30) // 240) * k, f"張出ブラケットの床（布板 240×{row}）")
        add(m.find("布材", row), 2 * k, f"張出ブラケットの床の先の手すり・中桟（布材{row}）")
        side = m.find("布材", w)
        if side is not None:
            add(side, 2 * k, f"張出ブラケットの床の外側の脇の手すり・中桟（布材{w}）")
        else:
            order.append(f"張出ブラケット{w}の床の外側の脇の手すり・中桟 {2 * k}本（布材{w} がマスタに無い長さ。単管とクランプで）")
    for w, qty in sorted(n_over.items(), reverse=True):
        part = bracket(w, "張出ブラケット")
        if part is not None:
            add(part, qty, f"張出ブラケット{w}")
        else:
            order.append(f"張出ブラケット{w} {qty}基（系列のマスタに無い）")
    # ---- 拡幅ブラケット（張り出しの横の本体の足場の隅の升目の外、全高で1回） ----
    n_wide: dict[int, int] = {}
    n_tube = 0
    gaps: list[str] = []
    lengths = sorted({p.nominal_dim for p in m.by_category("支柱")
                      if "根がらみ" not in p.note and "屋根" not in p.note and p.nominal_dim > 0}, reverse=True)
    n_out = len(model.plan.outline.edges)
    for ei, cb in (getattr(model, "corner_bridges", None) or {}).items():
        if model.edge_subset is not None and ei not in model.edge_subset:
            continue
        w, side_, lv = int(cb[0]), cb[1], list(cb[2])
        gap = float(cb[3]) if len(cb) > 3 else 0.0
        cl = row if side_ == 1 else int(model.row_spacing_of((ei - 1) % n_out))
        k = len(lv)
        n_wide[w] = n_wide.get(w, 0) + 2
        n_tube += 2
        # 先端の支柱: ブラケットの床から隅の升目の天端まで（長い支柱から積む）
        top = max(model.own_height(ei), model.own_height((ei - 1) % n_out))
        need = top - lv[0]
        stack: list[int] = []
        rest = need
        while rest > 10 and lengths:
            pick = next((L for L in lengths if L <= rest + 10), lengths[-1])
            stack.append(int(pick))
            rest -= pick
        for L in stack:
            add(post_of(L), 2, f"拡幅ブラケットの先端の支柱{L}")
        rail_w = m.find("布材", w)
        if rail_w is not None:
            add(rail_w, (2 * (k - 1) + 4 * k), f"拡幅した升目の床・手すり・中桟の布材{w}")
        else:
            order.append(f"拡幅した升目の布材{w} {2 * (k - 1) + 4 * k}本（マスタに無い長さ）")
        add(m.find("布材", cl), k, f"拡幅した升目の先端の支柱どうしの床の布材{cl}")
        add(m.deck_parts(240, cl), max(1, (w - 30) // 240) * k, f"拡幅した升目の床（布板 240×{cl}）")
        if gap > 30.0:
            gaps.append(f"すき間板（幅 {int(round(gap + 160))}×長さ {cl - 60}）{k}枚")
    for w, qty in sorted(n_wide.items(), reverse=True):
        part = bracket(w, "拡幅ブラケット")
        if part is not None:
            add(part, qty, f"拡幅ブラケット{w}")
        else:
            order.append(f"拡幅ブラケット{w} {qty}基（系列のマスタに無い）")
    if n_tube:
        order.append(f"拡幅ブラケットの補強単管 2.0m {n_tube}本とクランプ（日建 スーパークランプ S2C 相当）{2 * n_tube}個"
                     "（先端から1層下の元の支柱へ）")
    order.extend(gaps)
    if order:
        notes.action("拡幅・張出ブラケットまわりで別途手配: " + "、".join(order)
                     + "。すき間板は床と床のあきを 3cm 以下にするため（安衛則563条1項2号ロ）", Notes.ORDER)
    if n_over:
        notes.append("張り出した上の階の上段の端は、各層で張出ブラケット（"
                     + "・".join(f"{w}×{q}基" for w, q in sorted(n_over.items())) + "）で端の先へ床を持ち出します")
    if n_wide:
        notes.append("張り出しの横の本体の足場の隅の升目は、拡幅ブラケット（"
                     + "・".join(f"{w}×{q}基" for w, q in sorted(n_wide.items())) + "）で1回だけ広げて先端に支柱を立てます。"
                     "拡幅した層の上下は前踏み側の全スパンに壁つなぎを付け、拡幅部の支柱の許容荷重（日建 ND1800 は 8.8kN/本）を"
                     "確かめてください")
    # 高さの違う出隅: 低い面の天端より上の層の、升目の低い面の側の辺（床の布材と躯体側の手すり・中桟）
    n_rail = 0
    for ep in eps:
        if model.master.is_frame:
            break
        c = corner_tower_params(model, ep)
        low = c["cnrLowS"] or c["cnrLowP"]
        if not low:
            continue
        lv = c["cnrLevels"] and [float(v) for v in c["cnrLevels"].split(",")] or list(model.elevation_of(ep.edge_index).level_heights)
        k = sum(1 for h in lv if h / 1000.0 > low + 0.01)
        n_rail += k * (1 + (2 if model.config.inner_guard_rail else 0))
    if n_rail:
        add(m.find("布材", row), n_rail, f"高さの違う出隅の升目の上の層の辺の布材・手すり（布材{row}）")



def _count_width_change(model: ScaffoldModel, add, sub, notes, stair_plan=None) -> None:
    """拡幅・縮幅（width_change）: 幅を変える範囲の床から上の腕木・布板・出隅の升目を新しい幅に替え、拡幅ブラケット・
    元の支柱の継ぎ足し（日建 ND1800 は NDP09N）・つなぎ材（NDT03）・範囲の端の支柱と出隅の角の納まりを足す（attachments._width_change_kbrk
    と同じ）.

    範囲の中の外側の支柱は幅を変える床で継ぎ、上はブラケットの先端のホゾに立てる（本数は元の外側の支柱と同じとみなす）。
    範囲の端は元の支柱が天端まで残るので、新しい外側の支柱（幅を変える床から天端まで）を足す."""
    from .width_change import (EXT_POST_MM, WIDTH_STEP_MM, bracket_specs, change_height_mm, corner_point, span_range,
                               start_corner, upper_levels)

    wc = getattr(model, "width_change", None)
    if wc is None:
        return
    m = model.master
    w1, w2 = int(wc.from_mm), int(wc.to_mm)
    d1 = list(model.deck_widths_in_use)
    d2 = list(wc.to_decks)
    eps = [e for e in model.plan.edges if model.edge_subset is None or e.edge_index in model.edge_subset]
    tag = f"{wc.mode}{w1}→{w2}"
    lengths = sorted({p.nominal_dim for p in m.by_category("支柱")
                      if "根がらみ" not in p.note and "屋根" not in p.note and p.nominal_dim > 0}, reverse=True)

    def post_of(nominal: int):
        return next((p for p in m.by_category("支柱") if p.nominal_dim == nominal
                     and "根がらみ" not in p.note and "屋根" not in p.note), None)

    def stack(height: float, what: str) -> None:
        rest = height
        while rest > 10 and lengths:
            pick = next((L for L in lengths if L <= rest + 10), lengths[-1])
            add(post_of(int(pick)), 1, f"{what}{int(pick)}")
            rest -= pick

    def swap(cat: str, a: int, b: int, qty: int, what: str) -> None:
        sub(m.find(cat, a), qty, f"{tag}で差し引いた{what}{a}")
        add(m.find(cat, b), qty, f"{tag}の{what}{b}")

    n_br = n_ext = n_tie = n_ud = 0
    n_corner = n_tie_c = tube_c = n_ends = 0
    faces_done: list[str] = []
    for ep in eps:
        sr = span_range(model, ep)
        corner = start_corner(model, ep)
        if not sr and corner not in ("prev",):
            continue
        k = upper_levels(model, ep.edge_index)
        if sr:
            sa, sb = sr
            n = len(ep.spans)
            faces_done.append(model.face_name(ep.edge_index) + ("" if (sa, sb) == (1, n) else f"（{sa}〜{sb}スパン）"))
            nt = (sb - sa + 1) + (1 if sb == n and model._no_next(ep.edge_index) else 0)
            swap("布材", w1, w2, nt * k, "腕木（布材）")
            for s in ep.spans[sa - 1:sb]:
                for w in d1:
                    sub(m.deck_parts(w, int(s)), k, f"{tag}で差し引いた踏板 幅{w}×{int(s)}")
                for w in d2:
                    add(m.deck_parts(w, int(s)), k, f"{tag}の踏板 幅{w}×{int(s)}")
        zk = change_height_mm(model, ep.edge_index)
        for b in bracket_specs(model, ep):
            n_br += 1
            n_tie += len(b["ties"])
            n_ud += len(b["ud"])
            if b["end"] == "s":
                # 元の支柱は天端まで残る。新しい外側の支柱（足場ラインが描く）を幅を変える床から天端まで足す
                n_ends += 1
                stack(float(model.own_height(ep.edge_index)) - zk, f"{tag}の範囲の端の新しい外側の支柱")
            elif b["end"] == "e":
                n_ends += 1
                stack(b["tip"], f"{tag}の範囲の端の新しい外側の支柱")
            elif b["ext"] > 1.0:
                n_ext += 1
        if corner == "both":
            n_corner += 1
            swap("布材", w1, w2, 6 * k, "出隅コーナーの布材")
            if model.config.has_toe_board:
                swap("幅木", w1, w2, 2 * k, "出隅コーナーの幅木")
            for w in d1:
                sub(m.deck_parts(w, w1), k, f"{tag}で差し引いた出隅コーナーの踏板 幅{w}×{w1}")
            for w in d2:
                add(m.deck_parts(w, w2), k, f"{tag}の出隅コーナーの踏板 幅{w}×{w2}")
            c = corner_point(model, ep)
            if wc.mode == "拡幅":
                stack(zk - model.elevation_of(ep.edge_index).jack_extension, f"{tag}の出隅の角の支柱（地上から）")
                from .gdl_params import _default_jack_no

                add(m.get(_default_jack_no(model)), 1, f"{tag}の出隅の角の支柱のジャッキ")
                n_tie_c += wc.level        # 根がらみ＋幅を変える床の下の各層
            else:
                tube_c = 1500 if c["beam_mm"] <= 1450 else 2000
        elif corner in ("self", "prev"):
            # 隅の升目の1辺（建地列に直角な辺）だけ新しい幅（3本＝床・手すり・中桟、幅木1枚）。床は長さが前の面の幅
            n_corner += 1
            swap("布材", w1, w2, 3 * k, "出隅コーナーの布材")
            if model.config.has_toe_board:
                swap("幅木", w1, w2, k, "出隅コーナーの幅木")
            n_out = len(model.plan.outline.edges)
            w1p = int(model.row_spacing_of((ep.edge_index - 1) % n_out))
            if corner == "self":
                for w in d1:
                    sub(m.deck_parts(w, w1p), k, f"{tag}で差し引いた出隅コーナーの踏板 幅{w}×{w1p}")
                for w in d2:
                    add(m.deck_parts(w, w1p), k, f"{tag}の出隅コーナーの踏板 幅{w}×{w1p}")
            else:
                for w in d1:
                    sub(m.deck_parts(w, w1p), k, f"{tag}で差し引いた出隅コーナーの踏板 幅{w}×{w1p}")
                    add(m.deck_parts(w, w2), k, f"{tag}の出隅コーナーの踏板 幅{w}×{w2}")
    if not n_br and not n_corner:
        return
    order: list[str] = []
    if n_tie_c:
        order.append(f"出隅の角の支柱（地上から）を元の角の支柱へ繋ぐ単管 0.5m {n_tie_c}本と自在クランプ {2 * n_tie_c}個"
                     "（根がらみと幅を変える床の下の各層）")
    if tube_c:
        nb = sum(1 for ep in eps if start_corner(model, ep) == "both")
        order.append(f"出隅の角の支柱を受ける対角の単管 {tube_c / 1000:.1f}m {nb}本と自在クランプ {3 * nb}個"
                     "（元の升目の内外の角の支柱に掛け、角の支柱は自在クランプで留める）")
    part = next((p for p in m.by_category("ブラケット") if p.nominal_dim == WIDTH_STEP_MM and "拡幅" in p.note), None)
    if part is not None:
        add(part, n_br, f"{tag}の拡幅ブラケット{WIDTH_STEP_MM}")
    else:
        order.append(f"拡幅ブラケット{WIDTH_STEP_MM} {n_br}基（系列のマスタに無い）")
    add(post_of(EXT_POST_MM), n_ext, f"{tag}で元の外側の支柱に継ぎ足す支柱{EXT_POST_MM}")
    add(m.find("布材", WIDTH_STEP_MM), n_tie, f"{tag}の元の支柱と新しい支柱のつなぎ材{WIDTH_STEP_MM}")
    add(m.find("布材", w2), n_ud, f"{tag}の範囲の終わりの端の腕木（布材{w2}）")
    ext_p, tie_p = post_of(EXT_POST_MM), m.find("布材", WIDTH_STEP_MM)
    ext_no = ext_p.model_no if ext_p is not None else f"支柱{EXT_POST_MM}"
    tie_no = tie_p.model_no if tie_p is not None else f"{WIDTH_STEP_MM}"
    if order:
        notes.action(f"{wc.label}で別途手配: " + "、".join(order), Notes.ORDER)
    # 外付け階段は外側の建地列に付く。幅を変えた範囲に階段の升目があると、上の層で外側の支柱が 305 ずれて食い違う
    if stair_plan is not None and getattr(stair_plan, "outside", False):
        hit = []
        for t in stair_plan.towers:
            ep = next((e for e in eps if e.edge_index == t.edge_index), None)
            sr = span_range(model, ep) if ep is not None else None
            if sr:
                from .width_change import posts_x

                xs = posts_x(ep)
                if t.start_mm < xs[sr[1]] - 1.0 and t.end_mm > xs[sr[0] - 1] + 1.0:
                    hit.append(model.face_name(t.edge_index))
        if hit:
            notes.action(f"{wc.label}: {'・'.join(sorted(set(hit)))}の外付け階段の升目が幅を変える範囲にかかります。外付け"
                         "階段は外側の建地列に付くため、幅を変えた層で階段と外側の支柱が食い違います。範囲から階段の升目を"
                         "外してください", Notes.SITE)
    notes.append(
        f"{wc.label}: {'・'.join(faces_done) or '隅の升目'}で、元の外側の支柱{n_br}本に拡幅ブラケット{WIDTH_STEP_MM}を掛け（"
        + ("外へ" if wc.mode == "拡幅" else "躯体側へ")
        + f"）、先端のホゾに新しい外側の支柱を天端まで立てます。元の支柱には {ext_no} を継ぎ足してつなぎ材"
        f"{tie_no}で繋ぎます" + (f"。範囲の端{n_ends}箇所は元の支柱を天端まで残し、各層の手すり・中桟の高さの"
                                 f"つなぎ材{tie_no}で塞ぎます" if n_ends else "")
        + f"。範囲の上の腕木・布板・出隅の升目は幅{w2}で計上。幅を変えるのは全高で1回、幅を変えた層の上下は前踏み側の"
        "全スパンに壁つなぎを付け、拡幅部の支柱の許容荷重（日建 ND1800 は 8.8kN/本）を確かめてください")


def brace_starts(n_spans: int, every: int) -> list[int]:
    """斜材（交さ2方向の1組＝隣り合う2スパン）を入れるスパン（1 始まり）. 始点から every スパンごと、間隔の最後の組が
    終点の2スパンに届かなければ終点の手前のスパンにも1組（面の両端の構面には必ず入れる。利用者の指定 2026-10-25）."""
    if n_spans <= 0:
        return []
    every = max(1, int(every))
    out = list(range(1, n_spans + 1, every))
    if n_spans >= 2 and out[-1] < n_spans - 1:
        out.append(n_spans - 1)
    return out


def _count_open_ends(model: ScaffoldModel, add, notes) -> None:
    """一部の面だけの足場の開放端（隣の面を掛けない端）: 妻側の手すり・中桟・幅木を各層に.

    参考: smartCON Planner の「墜落の危険箇所に手すりを設置（つま先板つき）」「エンドストッパー」。
    """
    from .gdl_params import end_brace

    m = model.master
    row = model.post_row_spacing_mm
    if row <= 0:
        return              # 建地1列（単管抱き足場）は妻側に渡す長さが無い（布材0 を手配に出していた）
    n_ends = 0
    for ep in model.plan.edges:
        lv = model.elevation_of(ep.edge_index).n_levels
        # 跳ね出しの上段の端に拡幅ブラケットを出した端は、その先の床の手すりが塞ぐ（_count_widen_brackets）
        ext = getattr(model, "hane_end_ext", None) or {}
        k = (int(model.open_start(ep.edge_index) and (ep.edge_index, "s") not in ext)
             + int(model.open_end(ep.edge_index) and (ep.edge_index, "e") not in ext))
        # 入隅でつないだ隅から始まる面の始点（躯体側に開く升目。gdl_params の endOpenS と同じ）
        if model.inner_join_start(ep.edge_index) and model.config.inner_guard_rail and not model.open_start(ep.edge_index):
            k += 1
        n_ends += k
        if not k:
            continue
        if end_brace(model):
            # 妻側をブレス材（先行手すり）で塞ぐ（利用者の指定 2026-10-24: 妻側を布材かブレス材か選択する仕組み）
            part = m.find("先行手摺", row)
            if part is None:
                notes.action(f"開放端の妻側のブレス材（先行手すり{row}・{k * lv}本）がマスタにありません。別途手配してください")
            else:
                add(part, k * lv, f"開放端の妻側のブレス材（先行手すり{row}）")
        elif m.find("布材", row) is None and not m.is_tube:
            # 系列に無い長さ（日建の一側足場のブラケット 350 など）は単管とクランプで塞ぐ
            notes.action(f"開放端の妻側の手すり・中桟（{row}mm・{k * lv * 2}本）は系列に無い長さなので、単管（1.0m）"
                         f"{k * lv * 2}本と直交クランプ{k * lv * 4}個で組みます。別途手配してください", Notes.ORDER)
        else:
            add(m.find("布材", row), k * lv * 2, f"開放端の妻側の手すり・中桟（布材{row}）")
        if model.config.has_toe_board:
            toe = m.find("幅木", row)
            if toe is None:
                notes.action(f"開放端の妻側の幅木（{row}mm・{k * lv}本）が系列のマスタにありません。幅木（足場板・幅木の"
                             "端材）を別途手配してください", Notes.ORDER)
            else:
                add(toe, k * lv, f"開放端の妻側の幅木{row}")
    if n_ends:
        notes.append(f"一部の面だけの足場の端・入隅でつないだ升目の躯体側の開放端{n_ends}箇所は、各層に妻側の"
                     + ("ブレス材（先行手すり）" if end_brace(model) else "手すり・中桟")
                     + ("・幅木" if model.config.has_toe_board else "") + "を計上")


def _count_sheets(model: ScaffoldModel, add, notes, stair_plan=None) -> None:
    """養生シート（足場の外側の構面）。マスタに無ければ枚数と面積を注記に出す（リースの別手配が多い）."""
    from .attachments import (SHEET_SIZES, sheet_clamp_count, sheet_corner_clamp_count, sheet_quantities, sheet_size,
                              special_sheets, standard_sheets)

    kind = model.config.sheet_type or ""
    if kind not in SHEET_SIZES:
        return
    if kind == "防音パネル":
        _count_sound_panels(model, add, notes, stair_plan)
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
    opened = [(model.face_name(ei), s0, e0) for ei, rs in (getattr(model, "sheet_open", None) or {}).items()
              if any(e.edge_index == ei for e in model.plan.edges) for s0, e0, _b in rs]
    if opened:
        notes.append("荷受けステージの間口（" + "・".join(f"{f} {s0:.0f}〜{e0:.0f}" for f, s0, e0 in opened)
                     + f"）は、ステージを置く層の作業床から手すりの高さに掛かる{kind}の段を外しています（ステージは外側の列の外へ"
                     "張り出すので、張ったままでは足場の床とステージの間を塞ぐ）")
    cut = [(model.face_name(ei), s0, e0) for ei, rs in (getattr(model, "sheet_cuts", None) or {}).items()
           if any(e.edge_index == ei for e in model.plan.edges) for s0, e0 in rs]
    if cut:
        notes.append(f"昇降機の乗り込み口のスパン（" + "・".join(f"{f} {s0:.0f}〜{e0:.0f}" for f, s0, e0 in cut)
                     + f"）は{kind}を張っていません（荷台がこのスパンを昇り降りし、乗り込み口にフロアーゲートが付く。"
                     "ロングスパンの昇降路は外面を前養生で別に塞ぐ）")
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
        notes.append(f"{kind}は仮囲いの天端（{hb:.0f}）から上に張り、足場の天端から下へ1枚の高さずつ割り付けています（いちばん下の段は残りの高さ）")


def _count_sound_panels(model: ScaffoldModel, add, notes, stair_plan=None) -> None:
    """防音パネル（日本セイフティー 防音パネル・BG）: スパンごとの長さのパネル × 段、出隅のコーナーパネル、専用クランプ・
    三つ爪クランプ（利用者の指定 2026-10-24: 防音パネルを追加して）. 割付・段・クランプの位置は図の部品と同じ."""
    from .attachments import (panel_corner_count, panel_corner_pieces, sheet_clamp_count, sheet_corner_clamp_count,
                              sheet_quantities, sheet_rows, sheet_size, special_sheets, standard_sheets)

    w, h = sheet_size(model)
    area, _n = sheet_quantities(model, stair_plan, (w, h))
    std = standard_sheets(model, stair_plan, (w, h))
    sp = special_sheets(model, stair_plan, (w, h))
    panels = [p for p in model.master.by_category("防音パネル") if p.nominal_dim]
    other = {}
    for wd, k in std.items():
        hit = next((p for p in panels if abs(p.nominal_dim - wd) <= 1), None)
        if hit is not None:
            add(hit, k, f"防音パネル スパン{wd}")
        else:
            other[wd] = k
    n_rows = max((len(sheet_rows(model, e.edge_index)) for e in model.plan.edges), default=0)
    notes.append(f"防音パネル（高さ{h:.0f}・厚み40）は外側の構面に、継ぎ目を足場のスパンにそろえて {area:.0f}m²・"
                 + "・".join(f"スパン{wd}×{k}枚" for wd, k in std.items())
                 + f" で計上。上から1枚ずつ割り付け、いちばん下の段は仮囲いの天端に重ねる（最大{n_rows}段）")
    if other:
        notes.action("防音パネル: " + "・".join(f"スパン{wd}×{k}枚" for wd, k in other.items())
                     + f"（系列 {model.master.series_id} のマスタに無い長さ）を別途手配してください", Notes.ORDER)
    if sp:
        notes.action("防音パネルの隙間（隅の隙間・入隅の取り合いなどスパンに無い幅）: "
                     + "・".join(f"幅{wd}×{k}段" for wd, k in sp.items())
                     + "。パネルが無い幅なので、防音シートか合板で塞いでください", Notes.ORDER)
    n_corner = panel_corner_pieces(model, stair_plan)
    if n_corner:
        cp = next((p for p in model.master.by_category("防音パネル") if not p.nominal_dim), None)
        if cp is not None:
            add(cp, n_corner, "防音パネル コーナー（出隅の角 × 段）")
        else:
            notes.action(f"防音パネル コーナー {n_corner}枚（出隅の角 × 段）を別途手配してください", Notes.ORDER)
    n_cl = sheet_clamp_count(model, stair_plan)
    if n_cl:
        notes.action(f"防音パネルの専用クランプ {n_cl}個（継ぎ目と端の建地に、段の継ぎ目ごと＝下端・継ぎ目・天端。"
                     "ピンで隣り合うパネルの枠を留める）。系列のマスタに品番が無いので別途手配してください", Notes.ORDER)
    n_cc = sheet_corner_clamp_count(model, stair_plan)
    if n_cc:
        notes.action(f"三つ爪クランプ {n_cc}個（出隅の角 {panel_corner_count(model, stair_plan)}箇所。コーナーパネルの数"
                     f"{n_corner}＋コーナーの箇所数。日本セイフティーのよくある質問の目安）。別途手配してください", Notes.ORDER)


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
    # 面の組・面ごとの数量では、全体の脚と割付で区間を判定し、この組の面の分だけ数える（面の中で脚の番号を数え直すと
    # 終点の脚がずれ、面ごとの根がらみが全体より少なかった。2026-10-26 のループ）
    terrain_all, model_all = getattr(terrain, "_full", None) or (terrain, model)
    outer = list(getattr(terrain_all, "feet_outer", []) or [])
    per_row = ([(terrain_all, 1), (dataclasses.replace(terrain_all, feet=outer), 1)] if outer and rows >= 2
               else [(terrain_all, rows)])
    for t, k in per_row:
        rows_by_edge = extra_negarami(model_all, t)
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
    # 鉄骨から取るときは仕上げの奥の梁まで（利用者の指定 2026-10-24）
    steel = float(getattr(model.config, "steel_depth_mm", 0.0) or 0.0) if getattr(model.config, "tie_source", "") == "鉄骨" else 0.0
    return standoff + model.tie_post_offset_mm + extra + dia / 2.0 + steel


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
    if notes is not None and getattr(model.config, "tie_source", "") == "鉄骨":
        # 鉄骨から取る（利用者の指定 2026-10-24）: 仕上げの奥の梁の上フランジにビームクランプ。長さは梁まで
        # 面ごとに高さが違えば数量は面の組ごと。その組の面の壁つなぎだけ数える（二重に手配しない）
        mine_t = [t for t in model.wall_ties if model.edge_subset is None or t.edge_index in model.edge_subset]
        n = len(mine_t)
        hs = sorted({int(t.height_mm) for t in mine_t})
        notes.action(f"壁つなぎは鉄骨の梁からビームクランプで取ります（仕上げ面から梁まで {model.config.steel_depth_mm:.0f}mm を"
                     f"足した長さで品を選定、取付の高さは梁の高さ {len(hs)}段）。ビームクランプ {n}個を手配し、仕上げ（外壁）に"
                     "壁つなぎを通す穴・目地を外装と打ち合わせてください", Notes.ORDER)
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


def _stack_prefix(stack, need: float) -> list:
    """全高の構成（下から）の下の部材を、合計が need 以上になるまで."""
    out, acc = [], 0.0
    for nominal in stack:
        if acc >= need - 1.0:
            break
        out.append(nominal)
        acc += float(nominal)
    return out


def mid_post_stacks(full_stack, table: dict, below: float, above: float) -> tuple[list, list]:
    """途中の層の開口（荷受けステージの間口）で途中だけ抜いた支柱の (下の構成, 上の構成).

    下: 全高の積み方の下の部材を、ステージの床を越える継ぎ目まで（規格の長さに合わなくても組める）。
    上: 梁枠上から天端までの構成（組めなければ全高の積み方の上の部材を、梁枠上の高さを越えるまで）。
    """
    cb = _stack_prefix(list(full_stack), below)
    ca = table.get(int(round(above))) or list(reversed(_stack_prefix(list(reversed(full_stack)), above)))
    return cb, list(ca)


def _replace_opening_stacks(model, openings, totals: dict[int, int], full_stack: list[int],
                            lengths: list[int], notes, label: str) -> int:
    """開口部で抜いた鉛直部材を、梁枠上（作業床〜天端）だけの構成に置き換える.

    totals（呼び寸法→本数）を書き換える。戻り値は縦継ぎ箇所数の増減（枠組の連結ピン用）。
    組める構成が無い高さは全高のまま残し、要確認に出す。
    """
    from .elevation_solver import _compose_table
    from .openings import opening_mid_posts, opening_post_heights

    heights = opening_post_heights(model, openings)
    mids = opening_mid_posts(model, openings)
    if not (heights or mids) or not lengths:
        return 0
    table = _compose_table(int(round(max(list(heights) + [max(a, b) for a, b in mids]))) + 1,
                           sorted(set(lengths), reverse=True))
    replaced = 0
    joints_delta = 0
    missing: list[float] = []
    done: dict[int, int] = {}
    # 途中の層の開口（荷受けステージの間口）で途中だけ抜いた支柱: 全高の構成を、下（地面〜床）と上（梁枠上〜天端）の
    # 2本の構成に置き換える（ジャッキと下の支柱は残る）
    mid_done = 0
    for below, above in mids:
        cb, ca = mid_post_stacks(full_stack, table, below, above)
        if not cb or not ca:
            missing.append(below if not cb else above)
            continue
        for nominal in full_stack:
            totals[nominal] = totals.get(nominal, 0) - 1
        for nominal in list(cb) + list(ca):
            totals[nominal] = totals.get(nominal, 0) + 1
        joints_delta += (len(cb) - 1) + (len(ca) - 1) - (len(full_stack) - 1)
        mid_done += 1
    if mid_done:
        notes.append(f"荷受けステージの間口（途中の層の開口）で途中を抜いた{label}{mid_done}本は、下（地面〜ステージの床）と"
                     "梁枠上（〜天端）の2本の構成で計上しています")
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
    lines = standing_post_positions(model, rows)
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
    from .tube_runs import BOARD_LAP_MM, board_limits, face_boards

    m = model.master
    lines = []
    long_laps: dict[str, int] = {}
    for ep in model.plan.edges:
        runs = face_boards(list(ep.spans), **board_limits(model, ep))
        if runs[0].laps and max(runs[0].laps) > BOARD_LAP_MM:
            long_laps[model.face_name(ep.edge_index)] = max(runs[0].laps)
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
    if long_laps:
        notes.append(f"足場板は{'・'.join(long_laps)}で規定の長さの継ぎがブラケットに乗らないため、重ねを最大"
                     f"{max(long_laps.values())}mm に伸ばして割り付けています（ブラケットの上で重ね、両側に 100 以上掛ける）")
    if cut_cells:
        notes.append(f"足場板は階段・開口部の区間（{cut_cells}スパン×層）も面の通しのまま計上しています")


def _count_tube_toe_boards(model: ScaffoldModel, n_levels: int, add, notes, cut_cells: int) -> None:
    """単管の幅木（足場板を立てたもの）: 面ごとの足場板の割付（face_boards の A）× 作業層."""
    from .tube_runs import BOARD_LAP_MM, board_limits, face_boards

    m = model.master
    lines = []
    for ep in model.plan.edges:
        run = face_boards(list(ep.spans), **board_limits(model, ep))[0]
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
    from .tube_runs import face_runs, run_rooms

    m = model.master
    hug_rows = 2 * n_levels if model.config.is_hug else 0
    clamps = joints = 0
    lines = []
    eave_lines = []
    for ep in model.plan.edges:
        a, _b = face_runs(list(ep.spans), *run_rooms(model, ep))
        for L in a.pieces:
            part = m.find("単管", L)
            add(part, rows, f"単管{L / 1000:.1f}M（布・手すりの通し）")
        clamps += (len(ep.spans) + 1) * (rows - hug_rows)
        joints += (len(a.pieces) - 1) * rows
        lines.append("+".join(f"{L / 1000:.1f}" for L in a.pieces))
        # 軒先の手すり（下屋の面。屋根からの墜落防止に軒先から 450・900。elevation_solver.truncate_elevation）
        eave = list(getattr(model.elevation_of(ep.edge_index), "eave_rails_mm", None) or [])
        if eave:
            for L in a.pieces:
                add(m.find("単管", L), len(eave), f"単管{L / 1000:.1f}M（軒先の手すり）")
            clamps += (len(ep.spans) + 1) * len(eave)
            joints += (len(a.pieces) - 1) * len(eave)
            eave_lines.append(f"{model.face_name(ep.edge_index)} " + "・".join(f"{h / 1000:.2f}" for h in eave) + "m")
    notes.append(
        f"単管の通し（根がらみ・" + ("床の布2本・" if hug_rows else "") + "手すり・中桟）は、面ごとに規定の長さの単管を"
        f"直線ジョイントで継いで通す（{'／'.join(lines)} m。継ぎは建地のクランプから離し、隣の通しとずらす）×"
        f"1面あたり{rows}通りで計上"
    )
    if eave_lines:
        notes.append("下屋の面は最上段の床を軒の下にし、屋根からの墜落防止に軒先の手すり（上端の桟は軒先から概ね 90cm 以上。"
                     "仮設工業会 技術基準）を通しで足しています: " + "／".join(eave_lines))
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
    # 建枠どうしは繋がらないので、出隅の隙間（70mm 以上）は内外の建地列を根がらみ＋各層で単管（直交クランプ2個）で繋ぐ
    # （利用者の指定 2026-10-24: 枠足場は繋がらないから70mm離して単管で繋げけるようにして。3D・平面と同じ）
    gaps = [model.frame_gap_end_mm(e.edge_index) for e in model.plan.edges
            if model.edge_subset is None or e.edge_index in model.edge_subset]
    gaps = [g for g in gaps if g > 0.5]
    if gaps:
        n_tube = len(gaps) * 2 * (n_levels + 1)
        tube = next(iter(m.by_category("単管")), None)
        orth = next((p for p in m.by_category("クランプ") if "直交" in p.note), None)
        if tube is None or orth is None:
            missing.append(f"出隅の連結用の単管 {n_tube}本・直交クランプ {2 * n_tube}個")
        else:
            add(tube, n_tube, f"出隅の建枠どうしを繋ぐ単管{tube.nominal_dim // 1000:.0f}m")
            add(orth, 2 * n_tube, "出隅の連結単管の直交クランプ")
        notes.append(f"枠組の出隅{len(gaps)}箇所は建枠どうしが繋がらないので隙間（{'・'.join(f'{g:.0f}' for g in sorted(set(gaps)))}mm）を"
                     f"空け、内外の建地列を根がらみと各層で単管{n_tube}本（直交クランプ{2 * n_tube}個）で繋ぐ")
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
    _count_hane_brackets(model, notes)
    _count_sill_boards(model, notes, terrain, stair_plan)
    _count_roof_bridges(model, add, notes)
    _note_tier_gangways(model, notes)
    _count_intakes(model, notes)
