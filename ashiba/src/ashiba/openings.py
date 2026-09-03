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
# 梁枠の直近に壁つなぎが要る距離の目安
TIE_NEAR_MM = 1800.0


@dataclass
class Opening:
    """開口部1箇所（梁枠1本）."""

    edge_index: int
    start_mm: float           # 辺の始点コーナー支柱から梁枠左端までの距離
    beam_span_mm: int         # 梁枠が飛ばす距離。規格品のみ
    level: int = 1            # 支柱を抜く作業層（1=最下層）
    reason: str = ""

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
    removed_posts: int = 0        # 抜いた支柱の本数（内外列ぶん）
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
            result.issues.append(OpeningIssue(
                i, "NG",
                f"辺{o.edge_index}: 梁枠の両端（{o.start_mm:.0f}・{o.end_mm:.0f}mm）が"
                "支柱位置に一致しません。スパン割を調整してください",
                "梁枠は支柱で受ける"))
            continue

        inner = [p for p in posts if o.start_mm + 1e-6 < p < o.end_mm - 1e-6]
        result.removed_posts += len(inner) * rows
        # 梁枠上に乗る支柱の位置。図がスパン割から推定すると、開口部だけ
        # 割付が違う場合（900+1800+900など）に本数が食い違う
        result.inner_posts[i] = [round(p - o.start_mm, 1) for p in inner]
        lv = model.elevation.level_heights
        result.beam_heights[i] = (
            lv[o.level - 1] if 0 < o.level <= len(lv) else 0.0
        )

        result.issues.append(OpeningIssue(
            i, "WARN",
            f"辺{o.edge_index}の梁枠（{o.beam_span_mm}mm・支柱{len(inner)}本を受ける）: "
            "両端支柱の補強、梁枠上の積載荷重低減、取付部直近の壁つなぎが必要です",
            "仮設工業会 足場・型枠支保工設計指針"))

        # 通路として使う開口なので、頭上の高さが要る
        levels = model.elevation.level_heights
        h = levels[o.level - 1] if 0 < o.level <= len(levels) else 0
        if 0 < h < MIN_HEADROOM_MM:
            result.issues.append(OpeningIssue(
                i, "WARN",
                f"辺{o.edge_index}の開口高さ{h:.0f}mm < {MIN_HEADROOM_MM:.0f}mm。"
                "通路として使うなら梁枠を1層上げてください",
                "通路の頭上高さ（実務の目安）",
            ))

        near = [
            t for t in model.wall_ties
            if t.edge_index == o.edge_index
            and (abs(t.position_mm - o.start_mm) <= TIE_NEAR_MM
                 or abs(t.position_mm - o.end_mm) <= TIE_NEAR_MM)
        ]
        if not near:
            result.issues.append(OpeningIssue(
                i, "WARN",
                f"辺{o.edge_index}の梁枠取付部から{TIE_NEAR_MM:.0f}mm以内に"
                "壁つなぎがありません。増設を検討してください",
                "仮設工業会 設計指針"))

    for i, a in enumerate(openings):
        for j, b in list(enumerate(openings))[i + 1:]:
            if a.edge_index != b.edge_index:
                continue
            if a.start_mm < b.end_mm and b.start_mm < a.end_mm:
                result.issues.append(OpeningIssue(
                    j, "NG",
                    f"辺{a.edge_index}で開口部{i + 1}と{j + 1}が重なっています",
                    "入力エラー"))
    return result


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
        if edge is None:
            continue
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
        out += inner * max(0, o.level)
    return out


def opening_detail_specs(result: OpeningResult) -> list[dict]:
    """詳細図（detailType="beam"）に渡す指定."""
    return [
        {"beam_span_mm": o.beam_span_mm,
         "inner_posts_mm": result.inner_posts.get(i, []),
         "beam_height_mm": result.beam_heights.get(i, 0.0)}
        for i, o in enumerate(result.openings)
    ]
