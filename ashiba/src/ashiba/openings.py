"""開口部（出入口・仮設通路）の梁枠.

支柱を抜いて人や資材を通す箇所には、抜いた支柱を受けるトラス梁枠を入れる。
梁枠まわりは以下が付いてくる（仮設工業会 足場・型枠支保工設計指針）:
- 梁枠は規格品でしか飛ばせない（2スパン3600 / 3スパン5400）。中間の寸法は無い
- 梁枠上の作業床は積載荷重を低減する
- 梁枠の両端で支柱に集中荷重が入るので、その支柱は補強する
- 取付部の直近に壁つなぎを設ける

詳細図（ashiba_detail の detailType="beam"）は以前から描けたが、CLIから
開口部を渡す口が無く、数量にも梁枠が出ていなかった。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import ScaffoldModel

MIN_HEADROOM_MM = 1800.0   # 通路として使う開口の頭上高さの目安

# 系列ごとの梁枠の決め。ミレニューム Q&A「Q16. 梁枠を用いて開口部を設ける場合の組み立て方」（利用者の資料 2026-10-24。
# 組み立て条件は本足場の承認図書）:
# - 梁枠上の支柱1本あたりの許容支持力（2スパン 7.5kN は梁枠上に先行手すり筋交いを1層以上、3・4スパン 11.0kN は3層以上）
# - 網掛け部（開口の両隣1スパンの全高と、梁枠より上）は前踏み側にも先行手すり筋交いを設置する
# - 梁枠を支持する両端の支柱は必要に応じて補強（2本組 15.2・補剛材 19.6kN は本足場、26・33kN 仕様は型枠支保工の承認）
BEAM_RULES = {
    "nikken_millennium": {
        "support_kn": {3658: 7.5, 5487: 11.0, 7316: 11.0},
        "adv_levels": {3658: 1, 5487: 3, 7316: 3},
        "front_adv": True,
        "end_post_options": (("2本組", 15.2, "本足場の承認図書"), ("補剛材", 19.6, "本足場の承認図書"),
                             ("26kN仕様", 26.0, "型枠支保工の承認図書"), ("33kN仕様", 33.0, "型枠支保工の承認図書")),
        "source": "ミレニューム Q&A Q16（梁枠を用いて開口部を設ける場合の組み立て方。利用者の資料 2026-10-24）",
    },
}


def beam_rules(model) -> dict:
    """系列の梁枠の決め（無ければ空）."""
    return BEAM_RULES.get(model.master.series_id, {})


def front_adv_spans(model, edge_index: int, result) -> list[tuple[float, float, float]]:
    """前踏み側に先行手すり筋交いを入れる区間 [(始点, 終点, この高さ以上の作業層 mm)]（Q16 の網掛け部）.

    開口の両隣1スパンは全高（0 以上）、開口の上は梁枠の高さ（梁枠の上の床）から上。系列に決めが無ければ空。
    """
    if not beam_rules(model).get("front_adv") or result is None:
        return []
    ep = _edge(model, edge_index)
    if ep is None:
        return []
    posts = [0.0]
    for s in ep.spans:
        posts.append(posts[-1] + float(s))
    out = []
    for i, o in enumerate(result.openings):
        if o.edge_index != edge_index or o.void:
            continue
        h = float(result.beam_heights.get(i, 0.0))
        out.append((o.start_mm, o.end_mm, h))
        k0 = next((j for j, p in enumerate(posts) if abs(p - o.start_mm) < 1.0), None)
        k1 = next((j for j, p in enumerate(posts) if abs(p - o.end_mm) < 1.0), None)
        if k0 is not None and k0 > 0:
            out.append((posts[k0 - 1], posts[k0], 0.0))
        if k1 is not None and k1 < len(posts) - 1:
            out.append((posts[k1], posts[k1 + 1], 0.0))
    return out
# 梁枠の直近に壁つなぎが要る距離の目安
TIE_NEAR_MM = 1800.0
# 仮設工業会「はりわく等の使用基準」（2018 改正）: 開口部の寸法は幅4スパン以下・高さは原則3層以下。開口部端の支持部から
# 外方に、はりわくの種類に応じたスパン数のわく組足場を設ける（1種＝2スパン用は1スパン以上、2種＝3スパン用は2、
# 3種＝4スパン用は3）。開口部上方の全積載荷重は 1000kg 以下。外方のスパン内に建設用リフト等を設置しない
OPENING_MAX_SPANS = 4
OPENING_MAX_LEVELS = 3
STAGE_OPENING_LEVELS = 2       # 荷受けステージの間口の開口の高さ（層）
# 全高で抜く区間（void）の「梁下高さ」。足場より高い値にして、梁枠より下を抜く処理をそのまま全高に効かせる。
# 足場の線の部品は 999m 以上を梁枠なしとみなす（梁枠・梁枠上の支柱を描かない）
VOID_HEIGHT_MM = 999000.0


@dataclass
class Opening:
    """開口部1箇所（梁枠1本）."""

    edge_index: int
    start_mm: float           # 辺の始点コーナー支柱から梁枠左端までの距離
    beam_span_mm: int         # 梁枠が飛ばす距離。規格品のみ
    level: int = 1            # 支柱を抜く作業層（1=最下層）
    reason: str = ""
    # 梁枠を入れず全高で抜く区間（ロングスパンの昇降路。両隣の足場の間に荷取りステージだけ掛ける）
    void: bool = False
    # 途中の層の開口（0＝地面から）: この作業層の床から上だけ支柱を抜く。荷受けステージの間口（利用者の指定 2026-10-28:
    # 取り入れ口のブラケットも足場は開口になる、開口のところは梁枠を入れて）。床（bottom_level の層）と、その下の支柱は残す
    bottom_level: int = 0
    stage: bool = False       # 荷受けステージの間口に自動で入れた開口（ステージ×開口部の衝突にしない）

    @property
    def end_mm(self) -> float:
        return self.start_mm + self.beam_span_mm


@dataclass
class OpeningIssue:
    index: int
    severity: str    # "NG" / "WARN"
    message: str
    basis: str


@dataclass
class OpeningResult:
    openings: list[Opening] = field(default_factory=list)
    issues: list[OpeningIssue] = field(default_factory=list)
    removed_posts: int = 0        # 抜いた支柱の本数（内外列ぶん。地面から抜くもの）
    cut_posts: int = 0            # 途中の層の開口で、途中だけ抜いた支柱の本数（ジャッキと下の支柱は残る）
    # 開口部ごとの、途中の層の開口の床の高さ（抜く区間の下端。地面から抜くものは入れない）
    bottom_heights: dict = field(default_factory=dict)
    # 開口部ごとの、梁枠上に乗る支柱の位置（開口始点からのmm）
    inner_posts: dict = field(default_factory=dict)
    # 開口部ごとの梁枠下端＝開口高さ（GLからのmm）
    beam_heights: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not [i for i in self.issues if i.severity == "NG"]


def _edge(model: ScaffoldModel, edge_index: int):
    for ep in model.plan.edges:
        if ep.edge_index == edge_index:
            return ep
    return None


def beam_sizes(model: ScaffoldModel) -> list[int]:
    """カタログにある梁枠の呼び寸法（昇順）."""
    return sorted({p.nominal_dim for p in model.master.by_category("梁枠")})


def validate_openings(
    model: ScaffoldModel, openings: Optional[list[Opening]] = None
) -> OpeningResult:
    """開口部の指定を検証する.

    梁枠は規格品でしか飛ばせないので、中間寸法を黙って丸めない。
    支柱位置に合っていない指定も、そのままでは組めないのでNGにする。
    """
    openings = openings or []
    result = OpeningResult(openings=openings)
    sizes = beam_sizes(model)
    n_levels = model.elevation.n_levels
    rows = 1 if model.config.scaffold_form == "一側足場" else 2

    for i, o in enumerate(openings):
        edge = _edge(model, o.edge_index)
        if edge is None:
            result.issues.append(OpeningIssue(
                i, "NG", f"辺{o.edge_index}は存在しません", "入力エラー"))
            continue
        if sizes and o.beam_span_mm not in sizes:
            result.issues.append(OpeningIssue(
                i, "NG",
                f"梁枠{o.beam_span_mm}mmは規格外です（規格: "
                + "、".join(str(s) for s in sizes) + "）",
                "梁枠は規格品のみ。現場での切詰めはできない"))
        if not (1 <= o.level <= n_levels):
            result.issues.append(OpeningIssue(
                i, "NG",
                f"作業層{o.level}は存在しません（1〜{n_levels}）", "入力エラー"))

        posts = [0.0]
        for s in edge.spans:
            posts.append(posts[-1] + s)
        on_start = any(abs(p - o.start_mm) < 1e-6 for p in posts)
        on_end = any(abs(p - o.end_mm) < 1e-6 for p in posts)
        if o.end_mm > edge.scaffold_length + 1e-6:
            result.issues.append(OpeningIssue(
                i, "NG",
                f"辺{o.edge_index}: 梁枠終点{o.end_mm:.0f}mmが面長"
                f"{edge.scaffold_length:.0f}mmを超えています", "入力エラー"))
            continue
        if not (on_start and on_end):
            # 「一致しません」だけでは、どこに直せばよいか分からない。
            # 始点に最も近い支柱位置と、そこから梁枠長ぶん先が支柱に乗るかを示す
            near = min(posts, key=lambda p: abs(p - o.start_mm))
            near_end = near + o.beam_span_mm
            end_ok = any(abs(p - near_end) < 1e-6 for p in posts)
            hint = (f"始点を{near:.0f}mmにすれば両端とも支柱に乗ります" if end_ok else
                    f"支柱位置は {'・'.join(f'{p:.0f}' for p in posts)}mm です")
            result.issues.append(OpeningIssue(
                i, "NG",
                f"辺{o.edge_index}: 梁枠の両端（{o.start_mm:.0f}・{o.end_mm:.0f}mm）が"
                f"支柱位置に一致しません。スパン割を調整してください（{hint}）",
                "梁枠は支柱で受ける"))
            continue

        inner = [p for p in posts if o.start_mm + 1e-6 < p < o.end_mm - 1e-6]
        n_sp = len(inner) + 1
        face = model.face_name(o.edge_index)
        if not o.void:
            # 仮設工業会 はりわく等の使用基準: 幅4スパン以下・高さ原則3層以下・開口部端から外方のスパン数
            n_lv_open = max(0, o.level - max(o.bottom_level, 1)) if o.bottom_level > 0 else max(0, o.level - 1)
            if n_sp > OPENING_MAX_SPANS:
                result.issues.append(OpeningIssue(
                    i, "NG", f"{face}の開口部（{o.start_mm:.0f}〜{o.end_mm:.0f}）は幅{n_sp}スパンで、はりわくの開口は"
                             f"{OPENING_MAX_SPANS}スパン以下です", "仮設工業会 はりわく等の使用基準 2e"))
            if n_lv_open > OPENING_MAX_LEVELS:
                result.issues.append(OpeningIssue(
                    i, "WARN", f"{face}の開口部の高さが{n_lv_open}層です。開口部の高さは原則3層以下です（障害物がある等"
                               "やむを得ないとき以外）", "仮設工業会 はりわく等の使用基準 2e"))
            need_out = max(1, n_sp - 1)
            k0 = next((j for j, p in enumerate(posts) if abs(p - o.start_mm) < 1.0), None)
            k1 = next((j for j, p in enumerate(posts) if abs(p - o.end_mm) < 1.0), None)
            if k0 is not None and k1 is not None:
                left, right = k0, len(posts) - 1 - k1
                if min(left, right) < need_out:
                    side = "始点側" if left < need_out else "終点側"
                    result.issues.append(OpeningIssue(
                        i, "WARN", f"{face}の開口部（{n_sp}スパン用のはりわく）の{side}の外方の足場が{min(left, right)}スパン"
                                   f"しかありません。開口部端の支持部から外方へ{need_out}スパン以上のわく組足場が要ります"
                                   "（足りないときは、はりわく支持部の建わくを補強）", "仮設工業会 はりわく等の使用基準 2f"))
        if o.bottom_level > 0:
            result.cut_posts += len(inner) * rows
            lvb = model.elevation_of(o.edge_index).level_heights
            result.bottom_heights[i] = float(lvb[o.bottom_level - 1]) if 0 < o.bottom_level <= len(lvb) else 0.0
        else:
            result.removed_posts += len(inner) * rows
        # 梁枠上に乗る支柱の位置。図がスパン割から推定すると、開口部だけ
        # 割付が違う場合（900+1800+900など）に本数が食い違う
        result.inner_posts[i] = [round(p - o.start_mm, 1) for p in inner]
        lv = model.elevation.level_heights
        result.beam_heights[i] = (
            lv[o.level - 1] if 0 < o.level <= len(lv) else 0.0
        )

        vm = model.master.vertical_member_name
        result.issues.append(OpeningIssue(
            i, "WARN",
            f"{model.face_name(o.edge_index)}の梁枠（{o.beam_span_mm}mm・{vm}{len(inner)}本を受ける）: "
            f"両端{vm}の軸力（反力込み）と梁枠上の積載制限は計算書4で検定します。取付部直近の壁つなぎは両端{vm}の梁枠高さに計上しています（同じ位置の格子の金具で兼ねる）",
            "仮設工業会 足場・型枠支保工設計指針"))

        # 通路として使う開口なので、頭上の高さが要る
        levels = model.elevation.level_heights
        h = levels[o.level - 1] if 0 < o.level <= len(levels) else 0
        if 0 < h - result.bottom_heights.get(i, 0.0) < MIN_HEADROOM_MM and o.bottom_level == 0:
            result.issues.append(OpeningIssue(
                i, "WARN",
                f"{model.face_name(o.edge_index)}の開口高さ{h:.0f}mm < {MIN_HEADROOM_MM:.0f}mm。"
                "通路として使うなら梁枠を1層上げてください",
                "通路の頭上高さ（実務の目安）",
            ))

        # 梁枠上の先行手すり筋交いの層数（系列の決め。ミレニューム Q16: 2スパン 1層以上、3・4スパン 3層以上）
        need_adv = beam_rules(model).get("adv_levels", {}).get(int(o.beam_span_mm))
        if need_adv:
            above = sum(1 for z in levels if z >= h - 1e-6)
            if above < need_adv:
                result.issues.append(OpeningIssue(
                    i, "WARN",
                    f"{model.face_name(o.edge_index)}の梁枠（{o.beam_span_mm}mm）の上の作業層が{above}層です。"
                    f"梁枠上に先行手すり筋交いを{need_adv}層以上設けた場合の許容支持力で検定しているので、"
                    "梁枠を下げるか足場を上げてください",
                    beam_rules(model)["source"]))

        near = [
            t for t in model.wall_ties
            if t.edge_index == o.edge_index
            and (abs(t.position_mm - o.start_mm) <= TIE_NEAR_MM
                 or abs(t.position_mm - o.end_mm) <= TIE_NEAR_MM)
        ]
        if not near:
            result.issues.append(OpeningIssue(
                i, "WARN",
                f"{model.face_name(o.edge_index)}の梁枠取付部から{TIE_NEAR_MM:.0f}mm以内に"
                "壁つなぎがありません。増設を検討してください",
                "仮設工業会 設計指針"))

    for i, a in enumerate(openings):
        for j, b in list(enumerate(openings))[i + 1:]:
            if a.edge_index != b.edge_index:
                continue
            if a.start_mm < b.end_mm and b.start_mm < a.end_mm:
                result.issues.append(OpeningIssue(
                    j, "NG",
                    f"{model.face_name(a.edge_index)}で開口部{i + 1}と{j + 1}が重なっています",
                    "入力エラー"))
    return result


def opening_post_heights(model: ScaffoldModel, result: Optional[OpeningResult]) -> list[float]:
    """開口部で抜いた鉛直部材1本ごとの、梁枠上に乗る部材の高さ（梁枠上端＝作業床〜天端, mm）.

    抜く前と同じ全高の構成で数えると、梁枠より下の分が余計に入る。
    """
    if result is None or not result.openings:
        return []
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    top = float(model.elevation.total_height)
    out: list[float] = []
    for i, _o in enumerate(result.openings):
        if _o.bottom_level > 0:
            continue                # 途中の層の開口は opening_mid_posts
        n = len(result.inner_posts.get(i, [])) * rows
        beam_h = float(result.beam_heights.get(i, 0.0))
        out.extend([max(0.0, top - beam_h)] * n)
    return out


def opening_mid_posts(model: ScaffoldModel, result: Optional[OpeningResult]) -> list[tuple[float, float]]:
    """途中の層の開口で途中だけ抜いた支柱1本ごとの (下の支柱の高さ＝地面から床まで, 上の支柱の高さ＝梁枠上〜天端) mm."""
    if result is None or not result.openings:
        return []
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    top = float(model.elevation.total_height)
    out: list[tuple[float, float]] = []
    for i, o in enumerate(result.openings):
        if o.bottom_level <= 0:
            continue
        n = len(result.inner_posts.get(i, [])) * rows
        out.extend([(float(result.bottom_heights.get(i, 0.0)), max(0.0, top - float(result.beam_heights.get(i, 0.0))))] * n)
    return out


def opening_ranges(result: Optional[OpeningResult]) -> dict[int, list[tuple[float, float]]]:
    """開口部が占める区間（辺 → [(始点, 終点)]）. 階段室の自動配置が避けるために使う.

    梁枠より下は支柱を抜いた通路で、階段室を組めない。自動配置がここに
    階段を置くと、割付は通っても衝突検査で止まる（実際にサンプル2件で起きた）。
    """
    out: dict[int, list[tuple[float, float]]] = {}
    if result is None:
        return out
    for o in result.openings:
        out.setdefault(o.edge_index, []).append((o.start_mm, o.end_mm))
    return out


def opening_deck_deduction(
    model: ScaffoldModel, result: Optional[OpeningResult]
) -> dict[int, int]:
    """開口部で敷かない床の枚数（呼び寸法 → スパン×層のセル数）.

    梁枠より下は通路（支柱を抜いた開口）なので、床も幅木も無い。
    数えたままにすると、実際には存在しない作業床が数量表に出る。
    """
    out: dict[int, int] = {}
    if result is None or not result.openings:
        return out
    for o in result.openings:
        edge = _edge(model, o.edge_index)
        if edge is None:
            continue
        below = max(0, o.level - 1)      # 梁枠のある層より下の層数
        if o.bottom_level > 0:
            below = max(0, o.level - o.bottom_level - 1)   # 途中の層の開口: 床（bottom_level）は残し、その上から梁枠まで
        if below == 0:
            continue
        acc = 0.0
        for sp in edge.spans:
            if o.start_mm - 1e-6 <= acc < o.end_mm - 1e-6:
                out[sp] = out.get(sp, 0) + below
            acc += sp
    return out


def opening_span_counts(
    model: ScaffoldModel, result: Optional[OpeningResult]
) -> dict[int, int]:
    """開口部が占めるスパン（呼び寸法 → 本数）.

    層に依らない部材（根がらみ）の控除に使う。開口はGLから梁枠までなので、
    最下段の布材（根がらみ）もその区間には入らない。
    """
    out: dict[int, int] = {}
    if result is None or not result.openings:
        return out
    for o in result.openings:
        edge = _edge(model, o.edge_index)
        if edge is None or o.bottom_level > 0:
            continue                # 途中の層の開口は根がらみを残す
        acc = 0.0
        for sp in edge.spans:
            if o.start_mm - 1e-6 <= acc < o.end_mm - 1e-6:
                out[sp] = out.get(sp, 0) + 1
            acc += sp
    return out


def opening_removed_udegi(
    model: ScaffoldModel, result: Optional[OpeningResult]
) -> int:
    """開口部で抜いた支柱位置ぶんの腕木の本数（建地1列あたり）.

    抜いた支柱にはGLから梁枠下端まで腕木が付かない。段数は
    根がらみ1＋梁枠より下の作業層（= o.level - 1）＝ o.level。
    """
    if result is None or not result.openings:
        return 0
    out = 0
    for i, o in enumerate(result.openings):
        inner = len(result.inner_posts.get(i, []))
        # 途中の層の開口: 床（bottom_level）の腕木は残し、その上から梁枠の下まで
        out += inner * (max(0, o.level - o.bottom_level - 1) if o.bottom_level > 0 else max(0, o.level))
    return out


def opening_detail_specs(result: OpeningResult) -> list[dict]:
    """詳細図（detailType="beam"）に渡す指定."""
    return [
        {"beam_span_mm": o.beam_span_mm,
         "inner_posts_mm": result.inner_posts.get(i, []),
         "beam_height_mm": result.beam_heights.get(i, 0.0)}
        for i, o in enumerate(result.openings) if not o.void
    ]


def hoist_voids(model: ScaffoldModel, hoists) -> list[Opening]:
    """ロングスパンの昇降路: 乗り込み口のスパン（荷台の掛かるスパン）の足場を全高で抜く区間.

    両隣の足場を塔にして、その間に乗り込む層ごとの荷取りステージ（荷取用金具＋梁枠）だけを掛ける（利用者の指摘
    2026-10-28: ステージの上下は足場ないよ。施工写真でもロングスパンの前の足場は抜いてあり、ステージだけが各階に掛かる）。
    ステージの梁枠が掛かる 2・3 スパンのときだけ（それ以外は荷取りステージが別計画なので抜かない）。
    """
    from .platforms import LANDING_BEAM_SPANS

    out: list[Opening] = []
    for h in hoists or []:
        hm = h.spec
        inside = bool(getattr(h, "inside", False))
        # 足場の幅の中に据える昇降機（利用者の指定 2026-10-28）は機種によらず荷台の掛かるスパンを抜く
        if not inside and (hm is None or hm.kind != "ロングスパン"):
            continue
        ep = _edge(model, h.edge_index)
        if ep is None or (model.edge_subset is not None and h.edge_index not in model.edge_subset):
            continue
        gs = h.gate_spans(model)
        if not gs or (not inside and len(gs) not in LANDING_BEAM_SPANS):
            continue
        posts = [0.0]
        for sp in ep.spans:
            posts.append(posts[-1] + float(sp))
        a, b = posts[min(gs)], posts[max(gs) + 1]
        out.append(Opening(h.edge_index, a, int(round(b - a)), model.elevation_of(h.edge_index).n_levels + 1,
                           reason=f"昇降機 {hm.name if hm else ''} の昇降路", void=True))
    return out


def add_voids(model: ScaffoldModel, result: OpeningResult, voids: list[Opening]) -> None:
    """全高で抜く区間を開口部の結果に足す（梁枠の検定・壁つなぎ・数量の梁枠は void を除いて扱う）."""
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    for o in voids:
        ep = _edge(model, o.edge_index)
        if ep is None:
            continue
        posts = [0.0]
        for sp in ep.spans:
            posts.append(posts[-1] + float(sp))
        inner = [p for p in posts if o.start_mm + 1e-6 < p < o.end_mm - 1e-6]
        i = len(result.openings)
        result.openings.append(o)
        result.removed_posts += len(inner) * rows
        result.inner_posts[i] = [round(p - o.start_mm, 1) for p in inner]
        result.beam_heights[i] = VOID_HEIGHT_MM


def cut_height(o: Opening, levels) -> float:
    """支柱・部材を抜く高さ（この高さより下を抜く）. 梁枠の開口は支柱を抜く層の床の高さ、void は全高."""
    if o.void:
        return VOID_HEIGHT_MM
    if not levels:
        return 0.0
    return float(levels[min(max(o.level, 1), len(levels)) - 1])


def removed_posts_split(model: ScaffoldModel, result: Optional[OpeningResult]) -> tuple[int, int]:
    """抜いた支柱の本数を (梁枠の開口, 昇降路) に分けて返す."""
    if result is None:
        return 0, 0
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    beam = void = 0
    for i, o in enumerate(result.openings):
        n = len(result.inner_posts.get(i, [])) * rows
        if o.void:
            void += n
        else:
            beam += n
    return beam, void


def cut_bottom(o: Opening, levels) -> float:
    """抜く区間の下端（途中の層の開口はその層の床の高さ、ほかは 0＝地面）."""
    if o.bottom_level <= 0 or not levels:
        return 0.0
    return float(levels[min(o.bottom_level, len(levels)) - 1])


def stage_openings(model: ScaffoldModel, stages) -> list[Opening]:
    """荷受けステージの間口を途中の層の開口にする（利用者の指定 2026-10-28: 取り入れ口のブラケットも足場は開口になる、
    開口のところは梁枠を入れて）. 間口の中の支柱を、ステージの層の床から1つ上の層の床まで抜き、そこに梁枠を入れて上の
    支柱を受ける。間口が1スパン（中の支柱が無い）・最上層（上に支柱が無い）・規格の梁枠が無い長さは入れない。"""
    out: list[Opening] = []
    sizes = beam_sizes(model)
    for st in stages or []:
        ep = _edge(model, st.edge_index)
        if ep is None or st.span_count < 2:
            continue
        length = int(round(st.length_mm(model)))
        size = next((b for b in sizes if abs(b - length) <= 2), None)
        if size is None:
            continue
        n = model.elevation_of(st.edge_index).n_levels
        # 開口の高さは2層（ステージの床から2つ上の層の床まで。1層 1.8m では荷を立てて取り込めない。利用者の指定
        # 2026-10-28: 荷物取り入れられないから1スパン上になると思う）。上に2層が無ければ1層。ステージは1フロアずつ
        # 組み直す（levels を並べても今組むのは1層。残りは relocate_levels）ので、開口も今の層の1つだけ
        groups: list[list[int]] = []
        for lv in sorted(set(v for v in (st.levels or [1]) if 1 <= v < n)):
            if groups and lv < min(groups[-1][-1] + STAGE_OPENING_LEVELS, n):
                groups[-1].append(lv)
            else:
                groups.append([lv])
        for g in groups:
            out.append(Opening(st.edge_index, float(st.post_start_mm(model)), int(size), min(g[-1] + STAGE_OPENING_LEVELS, n),
                               reason="荷受けステージの間口", bottom_level=g[0], stage=True))
    return out
