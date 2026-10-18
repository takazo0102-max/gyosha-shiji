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
# 内ブラケットの踏板は支柱の芯から約25mm（支柱の半径）離れて掛かる
INNER_DECK_OFFSET_MM = 25.0
# 内ブラケットで詰めたあと、躯体との隙間はこれ以上残す（外壁の出入り・仕上げに当てない）
MIN_GAP_AFTER_INNER_MM = 50.0
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
    # 内ブラケットの上に躯体側へ敷く踏板の幅（離れを詰める用途）。None なら敷かない
    inner_deck_width: Optional[int] = None
    auto: bool = False         # ツールが自動で付けた区間か（入力にはない）

    @property
    def reach_mm(self) -> float:
        """床が内側建地から躯体側へ出る長さ（図・3Dの奥行き）。踏板を敷くならその幅＋支柱の半径分."""
        if self.inner_deck_width:
            return float(self.inner_deck_width) + INNER_DECK_OFFSET_MM
        return float(self.width)

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
        if s.width <= 0:
            issues.append(BracketIssue(
                i, "NG",
                f"辺{s.edge_index}: ブラケット幅{s.width:.0f}mmは0より大きい値で指定してください",
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

        if s.direction == OUTER:
            issues.append(BracketIssue(
                i, "WARN",
                f"{model.face_name(s.edge_index)}: 張出し区間の外縁は作業床の開放端になります。"
                "手すり・中桟・幅木が必要です（数量には計上しています）",
                "安衛則563条（作業床の開放端）"))

        if s.is_widening and s.on_kessokubu and not s.has_hozue:
            issues.append(BracketIssue(
                i, "NG",
                f"{model.face_name(s.edge_index)}: 緊結部付ブラケットでの拡幅には方杖が必須です",
                "仕様4.3"))

    # 逆向き取付禁止: 同一区間に内と張出が重なってはいけない
    for i, a in enumerate(sections):
        for j, b in enumerate(sections[i + 1:], start=i + 1):
            if a.overlaps(b) and a.direction != b.direction:
                issues.append(BracketIssue(
                    j, "NG",
                    f"{model.face_name(a.edge_index)}: 区間"
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
        base = model.post_row_spacing_mm
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


def outer_edge_quantities(
    model: ScaffoldModel, sections: list[BracketSection]
) -> dict[int, int]:
    """張出しブラケット床の外側縁に要る手すり・幅木の数（呼び寸法→スパン×層）.

    張出すと作業床の外縁が建地より外へ出る。既存の手すりは建地位置にあるので、
    新しい縁は無防備なまま。563条の墜落防止は「作業床の開放端」に要るので、
    ここを数えないと現場で手すりも幅木も足りない。
    """
    out: dict[int, int] = {}
    for s in sections:
        if s.direction != OUTER:
            continue
        edge = _find_edge(model, s.edge_index)
        if edge is None or s.length_mm <= 0:
            continue
        n_levels = len(s.levels) if s.levels else model.elevation.n_levels
        acc = 0.0
        for span in edge.spans:
            if s.start_mm - 1e-6 <= acc and acc + span <= s.end_mm + 1e-6:
                out[span] = out.get(span, 0) + n_levels
            acc += span
    return out


def inner_edge_cells(
    model: ScaffoldModel, sections: list[BracketSection]
) -> dict[int, int]:
    """内ブラケットで床を拡幅した区間のセル（呼び寸法→スパン×層）.

    拡幅で躯体との隙間が小さくなるので、その層・スパンには躯体側の手すり・中桟
    （inner_guard_rail）を付けない。3D・立面も同じ区間を空ける。
    """
    out: dict[int, int] = {}
    for s in sections:
        if s.direction != INNER:
            continue
        edge = _find_edge(model, s.edge_index)
        if edge is None or s.length_mm <= 0:
            continue
        n_levels = len(s.levels) if s.levels else model.elevation.n_levels
        acc = 0.0
        for span in edge.spans:
            if s.start_mm - 1e-6 <= acc and acc + span <= s.end_mm + 1e-6:
                out[span] = out.get(span, 0) + n_levels
            acc += span
    return out


def bracket_deck_changes(
    model: ScaffoldModel, sections: list[BracketSection]
) -> list[tuple[int, int, int, int]]:
    """踏板幅を変える区間の差し替え一覧 (スパン呼び寸法, 変更前幅, 変更後幅, 枚数).

    BracketSection.deck_width は入力として受け取っているのに数量へ反映されて
    いなかった。指定しても数量表が変わらないと、区間の踏板が現場で足りない。
    区間に完全に収まるスパンだけを対象にする（またぐスパンは敷き替えられない）。
    """
    out: list[tuple[int, int, int, int]] = []
    widths = list(model.deck_widths_in_use)
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



def inner_bracket_options(model: ScaffoldModel) -> list[tuple[int, int, str]]:
    """系列の内ブラケット（張出用でないもの）と、その上に敷く踏板の幅 → (腕の呼び, 踏板幅, 品番).

    品番の注記「踏板250用」「踏板240用」から踏板の幅を取る（「踏板500・400用」は最初の数字）。
    """
    import re

    out = []
    for p in model.master.by_category("ブラケット"):
        if "張出" in p.note:
            continue
        m = re.search(r"踏板(\d+)", p.note)
        if m:
            out.append((int(p.nominal_dim), int(m.group(1)), p.model_no))
    return sorted(out, key=lambda t: (t[1], t[0]))


def auto_inner_brackets(model: ScaffoldModel, existing: list[BracketSection],
                        limit_mm: float, fall_limit_mm: float = 300.0) -> tuple[list[BracketSection], list[str]]:
    """離れが limit（目標上限）を超える面に、内ブラケットを全層・全長に付ける.

    躯体までの隙間（離れ − 踏板幅 − 支柱の半径）が墜落防止の限度（300）以下、かつ
    MIN_GAP 以上になる最小の踏板を選ぶ。その面に入力の内ブラケット区間があれば触らない。
    入力の張出ブラケット区間とは重ねない（逆向き取付禁止）。その範囲を除いた残りに付ける。
    枠組・一側足場は対象外（枠組は張出用しか無く、一側はもともとブラケット床）。
    戻り値は (足す区間, 案内文)。
    """
    from .model import ScaffoldModel  # noqa: F401  (型の明示)

    if model.master.is_frame or model.config.scaffold_form == "一側足場":
        return [], []
    opts = inner_bracket_options(model)
    added: list[BracketSection] = []
    notes: list[str] = []
    grouped: dict[tuple, list[str]] = {}
    for ep in model.plan.edges:
        d = float(ep.standoff)
        if d <= limit_mm + 1e-6:
            continue
        if any(s.edge_index == ep.edge_index and s.direction == INNER for s in existing):
            continue
        face = model.face_name(ep.edge_index)
        pick = None
        for arm, deck, no in opts:
            gap = d - deck - INNER_DECK_OFFSET_MM
            if MIN_GAP_AFTER_INNER_MM - 1e-6 <= gap <= fall_limit_mm + 1e-6:
                pick = (arm, deck, no, gap)
                break
        if pick is None:
            notes.append(
                f"{face}: 離れ{d:.0f}mm を詰める内ブラケットが系列 {model.master.series_id} にありません"
                f"（隙間を{MIN_GAP_AFTER_INNER_MM:.0f}〜{fall_limit_mm:.0f}mm にできる踏板幅が無い）。"
                "落下防止材（層間ネット等）を検討してください")
            continue
        arm, deck, no, gap = pick
        length = float(ep.scaffold_length)
        free = _free_ranges(length, [(s.start_mm, s.end_mm) for s in existing
                                     if s.edge_index == ep.edge_index])
        for a, b in free:
            added.append(BracketSection(
                edge_index=ep.edge_index, start_mm=a, end_mm=b,
                direction=INNER, width=arm, inner_deck_width=deck, auto=True,
                reason=f"離れ{d:.0f}mm > {limit_mm:.0f}mm の墜落防止（自動）"))
        if not free:
            continue
        where = ("全長" if free == [(0.0, length)]
                 else "区間 " + "・".join(f"{a:.0f}〜{b:.0f}mm" for a, b in free)
                 + "（張出ブラケットの範囲は除く）")
        # 同じ離れ・同じ品で付けた面は1行にまとめる（向かい合う面は離れが同じになる）
        grouped.setdefault((round(d), no, deck, round(gap), where), []).append(face)
    for (d0, no, deck, gap0, where), faces in grouped.items():
        notes.append(
            f"{'・'.join(faces)}: 離れ{d0}mm が{limit_mm:.0f}mm を超えるので、内ブラケット {no}（踏板{deck}）を全層・{where}に"
            f"付けました。躯体までの隙間は約{gap0}mm です（入力 auto_inner_bracket=false で付けない）")
    return added, notes


def _free_ranges(length: float, taken: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """[0, length] から taken の区間を除いた残り（長さ1mm未満は捨てる）."""
    out = []
    cur = 0.0
    for a, b in sorted(taken):
        if a > cur + 1.0:
            out.append((cur, min(a, length)))
        cur = max(cur, b)
    if length > cur + 1.0:
        out.append((cur, length))
    return out
