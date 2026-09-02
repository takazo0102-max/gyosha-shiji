"""ブラケット区間（仕様4.3）.

⚠️ データ構造の決定:
ブラケットは **「支柱ラインの変更」ではなく「面の区間属性」** として持つ。
支柱ラインは真っ直ぐ通したまま、区間[12m-18m]は内ブラケットW300 のように面へ属性を付ける。
支柱位置を動かす実装にすると割付が壊れ、数量も二重計上になる。

調整手段の優先順位（これも仕様4.3）: ①スパン → ②離れ → ③ブラケット
ブラケットは最後の手段。スパン割・離れで吸収できるものをブラケットで解決しない。

用途:
- 床追従: 躯体の凹凸に作業床だけを追従させる（支柱ラインは通す）
- 張出: 下屋上・狭小部で作業床を外へ張り出す
- 幅切替: 踏板幅を区間ごとに変える

ルール:
- 逆向き取付禁止（内ブラケットと張出ブラケットを同一区間で相反する向きに付けない）
- 拡幅は下層建地間隔が上層の60%以上、かつ全層で1回まで
- 緊結部付ブラケットで拡幅する場合は方杖が必須
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import ScaffoldModel

INNER = "内"      # 床追従・幅切替（躯体側へ）
OUTER = "張出"    # 外側へ張り出す

WIDEN_MIN_LOWER_RATIO = 0.60   # 拡幅時、下層建地間隔は上層の60%以上
MAX_WIDEN_TIMES = 1            # 拡幅は全層で1回まで


@dataclass
class BracketSection:
    """1つの面（辺）の一区間に付くブラケット属性."""

    edge_index: int
    start_mm: float            # 辺の始点コーナー支柱からの距離
    end_mm: float
    direction: str = INNER     # INNER / OUTER
    width: int = 600           # ブラケット呼び寸法 600/400/300/200
    deck_width: Optional[int] = None   # この区間の踏板幅（Noneなら変更なし）
    levels: list[int] = field(default_factory=list)  # 適用作業層(1始まり、空=全層)
    has_hozue: bool = False    # 方杖の有無
    is_widening: bool = False  # 拡幅目的か（床追従・幅切替と区別する）
    on_kessokubu: bool = False # 緊結部付ブラケットか
    reason: str = ""

    @property
    def length_mm(self) -> float:
        return max(0.0, self.end_mm - self.start_mm)

    def overlaps(self, other: "BracketSection") -> bool:
        if self.edge_index != other.edge_index:
            return False
        if self.levels and other.levels and not (set(self.levels) & set(other.levels)):
            return False
        return self.start_mm < other.end_mm and other.start_mm < self.end_mm


@dataclass
class BracketIssue:
    section_index: int
    severity: str      # "NG" / "WARN"
    message: str
    basis: str


def validate_bracket_sections(
    model: ScaffoldModel, sections: list[BracketSection]
) -> list[BracketIssue]:
    """仕様4.3のルールでブラケット区間を検証する."""
    issues: list[BracketIssue] = []
    n_levels = model.elevation.n_levels

    for i, s in enumerate(sections):
        edge = _find_edge(model, s.edge_index)
        if edge is None:
            issues.append(BracketIssue(
                i, "NG", f"辺{s.edge_index}は存在しません", "入力エラー"))
            continue
        if s.length_mm <= 0:
            issues.append(BracketIssue(
                i, "NG",
                f"辺{s.edge_index}: 区間の長さが0以下です"
                f"（{s.start_mm:.0f}〜{s.end_mm:.0f}）",
                "入力エラー"))
        if s.end_mm > edge.scaffold_length + 1e-6:
            issues.append(BracketIssue(
                i, "NG",
                f"辺{s.edge_index}: 区間終点{s.end_mm:.0f}mmが"
                f"面長{edge.scaffold_length:.0f}mmを超えています",
                "入力エラー"))
        if s.direction not in (INNER, OUTER):
            issues.append(BracketIssue(
                i, "NG", f"ブラケット向きが不正です: {s.direction}",
                "仕様4.3（逆向き取付禁止）"))
        for lv in s.levels:
            if not (1 <= lv <= n_levels):
                issues.append(BracketIssue(
                    i, "NG",
                    f"作業層{lv}は存在しません（1〜{n_levels}）", "入力エラー"))

        if s.is_widening and s.on_kessokubu and not s.has_hozue:
            issues.append(BracketIssue(
                i, "NG",
                f"辺{s.edge_index}: 緊結部付ブラケットでの拡幅には方杖が必須です",
                "仕様4.3"))

    # 逆向き取付禁止: 同一区間に内と張出が重なってはいけない
    for i, a in enumerate(sections):
        for j, b in enumerate(sections[i + 1:], start=i + 1):
            if a.overlaps(b) and a.direction != b.direction:
                issues.append(BracketIssue(
                    j, "NG",
                    f"辺{a.edge_index}: 区間"
                    f"[{max(a.start_mm, b.start_mm):.0f}-"
                    f"{min(a.end_mm, b.end_mm):.0f}]で"
                    f"{a.direction}と{b.direction}が逆向きに重なっています",
                    "仕様4.3（逆向き取付禁止）"))

    # 拡幅は全層で1回まで
    widen = [s for s in sections if s.is_widening]
    if len(widen) > MAX_WIDEN_TIMES:
        issues.append(BracketIssue(
            sections.index(widen[-1]), "NG",
            f"拡幅が{len(widen)}箇所あります。全層で{MAX_WIDEN_TIMES}回までです",
            "仕様4.3"))

    # 拡幅時: 下層建地間隔が上層の60%以上
    for s in widen:
        base = model.deck_width_total
        widened = base + s.width
        if base < widened * WIDEN_MIN_LOWER_RATIO:
            issues.append(BracketIssue(
                sections.index(s), "NG",
                f"拡幅後の建地間隔{widened}mmに対し下層{base}mmは"
                f"{base / widened * 100:.0f}%で、60%を下回ります",
                "仕様4.3"))
    return issues


def bracket_quantities(
    model: ScaffoldModel, sections: list[BracketSection]
) -> dict[tuple[int, str], int]:
    """ブラケット区間から数量を算出する（(呼び寸法, 用途) → 本数）.

    ブラケットは支柱位置ごとに付くので、区間に含まれる支柱数 × 適用層数で数える。
    """
    counts: dict[tuple[int, str], int] = {}
    for s in sections:
        edge = _find_edge(model, s.edge_index)
        if edge is None or s.length_mm <= 0:
            continue
        n_posts = _posts_in_section(edge, s.start_mm, s.end_mm)
        n_levels = len(s.levels) if s.levels else model.elevation.n_levels
        key = (s.width, s.direction)
        counts[key] = counts.get(key, 0) + n_posts * n_levels
        if s.has_hozue:
            hz = (s.width, "方杖")
            counts[hz] = counts.get(hz, 0) + n_posts * n_levels
    return counts


def bracket_deck_changes(
    model: ScaffoldModel, sections: list[BracketSection]
) -> list[tuple[int, int, int, int]]:
    """踏板幅を変える区間の差し替え一覧 (スパン呼び寸法, 変更前幅, 変更後幅, 枚数).

    BracketSection.deck_width は入力として受け取っているのに数量へ反映されて
    いなかった。指定しても数量表が変わらないと、区間の踏板が現場で足りない。
    区間に完全に収まるスパンだけを対象にする（またぐスパンは敷き替えられない）。
    """
    out: list[tuple[int, int, int, int]] = []
    widths = list(model.config.deck_widths or [])
    if not widths:
        return out
    base_width = widths[0]           # 差し替えるのは主となる幅の踏板
    for s in sections:
        if s.deck_width is None or s.deck_width == base_width:
            continue
        edge = _find_edge(model, s.edge_index)
        if edge is None or s.length_mm <= 0:
            continue
        n_levels = len(s.levels) if s.levels else model.elevation.n_levels
        acc = 0.0
        for span in edge.spans:
            if s.start_mm - 1e-6 <= acc and acc + span <= s.end_mm + 1e-6:
                out.append((span, base_width, s.deck_width, n_levels))
            acc += span
    return out


def _find_edge(model: ScaffoldModel, edge_index: int):
    for ep in model.plan.edges:
        if ep.edge_index == edge_index:
            return ep
    return None


def _posts_in_section(edge, start_mm: float, end_mm: float) -> int:
    """区間内にある支柱本数（区間端の支柱を含む）."""
    acc = 0.0
    positions = [0.0]
    for s in edge.spans:
        acc += s
        positions.append(acc)
    return sum(1 for p in positions if start_mm - 1e-6 <= p <= end_mm + 1e-6)
