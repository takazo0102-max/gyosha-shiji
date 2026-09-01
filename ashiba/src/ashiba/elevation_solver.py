"""立面割付ソルバ.

仕様4.4:
- 固定点は最上層作業床（軒高＋手すり分）、端数吸収は最下部（ジャッキ＋短支柱）
- 縦方向はコマピッチ刻み（A:450 / B:475）で考える
- 支柱組合せはDP（本数最小・長尺優先）。基本形: 根がらみ用支柱＋長尺×n＋最上部短支柱
- 実例: G(ジャッキ270)+3800×4+900=16370
- 隣接支柱でジョイント位置が揃わないよう千鳥制約
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .master import PartMaster

JACK_MAX_EXTENSION = 270  # mm 安衛則上の実務上限（超過は法規チェックで警告）
JACK_MIN_EXTENSION = 30   # mm 調整代として最低限残す


@dataclass
class ElevationResult:
    required_height: int          # ジャッキベース下端→支柱天端の要求高さ [mm]
    jack_extension: int           # ジャッキ繰り出し量 [mm]
    posts: list[int]              # 下から順の支柱呼び寸法
    posts_alt: list[int]          # 千鳥用の代替構成（隣接支柱に交互適用）
    has_negarami: bool            # 根がらみを最下コマに設置
    first_ledger_height: int      # 第一の布（根がらみ）高さ [mm, GLから]
    n_levels: int                 # 作業層数
    level_heights: list[int]      # 各作業床高さ [mm, GLから]
    warnings: list[str] = field(default_factory=list)

    @property
    def total_height(self) -> int:
        return self.jack_extension + sum(self.posts)

    def joint_heights(self, posts: Optional[list[int]] = None) -> list[int]:
        """支柱ジョイント（ほぞ接続部）高さのリスト."""
        ps = posts if posts is not None else self.posts
        out = []
        h = self.jack_extension
        for p in ps[:-1]:
            h += p
            out.append(h)
        return out

    def is_staggered(self) -> bool:
        """隣接支柱でジョイント高さが1つも一致しないか."""
        a = set(self.joint_heights(self.posts))
        b = set(self.joint_heights(self.posts_alt))
        return not (a & b) if (a and b) else self.posts != self.posts_alt


def _compose_table(max_total: int, lengths: list[int], max_pieces: int = 60) -> dict[int, list[int]]:
    """0..max_total の各合計に対する最良構成（本数最小、次に長尺優先）DPテーブル."""
    best: dict[int, list[int]] = {0: []}
    for s in range(1, max_total + 1):
        cand_best = None
        for c in lengths:
            if s - c >= 0 and (s - c) in best:
                cand = best[s - c] + [c]
                if len(cand) > max_pieces:
                    continue
                if cand_best is None or _better(cand, cand_best):
                    cand_best = cand
        if cand_best is not None:
            best[s] = cand_best
    return best


def compose_posts(total: int, lengths: list[int], max_pieces: int = 60) -> Optional[list[int]]:
    """合計totalを支柱呼び寸法の組合せで構成（本数最小、次に長尺優先）."""
    return _compose_table(total, lengths, max_pieces).get(total)


def _better(a: list[int], b: list[int]) -> bool:
    if len(a) != len(b):
        return len(a) < len(b)
    return sorted(a, reverse=True) > sorted(b, reverse=True)


def _order_bottom_up(pieces: list[int]) -> list[int]:
    """基本形: 長尺を下から積み、最上部に短支柱（端数）を置く並び."""
    return sorted(pieces, reverse=True)


def _alt_order(pieces: list[int]) -> list[int]:
    """千鳥用: 短い支柱を最下部に回した並び（ジョイント高さをずらす）."""
    if len(set(pieces)) < 2:
        return list(pieces)
    ordered = sorted(pieces, reverse=True)
    return [ordered[-1]] + ordered[:-1]


def solve_elevation(
    required_height: int,
    master: Optional[PartMaster] = None,
    post_lengths: Optional[list[int]] = None,
    floor_height: Optional[int] = None,
    koma_pitch: Optional[int] = None,
    jack_max: int = JACK_MAX_EXTENSION,
    jack_min: int = JACK_MIN_EXTENSION,
) -> ElevationResult:
    """要求高さ（ジャッキベース下端→支柱天端）から支柱構成を解く.

    post_lengths を渡すとマスタより優先（テスト・実例再現用）。
    """
    if post_lengths is None:
        assert master is not None, "master か post_lengths のどちらかが必要です"
        post_lengths = master.post_lengths()
    if floor_height is None:
        floor_height = master.floor_height if master else 1800
    if koma_pitch is None:
        koma_pitch = master.koma_pitch if master else 450
    lengths = sorted(set(post_lengths), reverse=True)

    # 端数は最下部のジャッキで吸収。要求高さと厳密一致しない場合は
    # ±許容窓（下-150〜上+1コマ）内で偏差最小の解を許す。
    # 優先順位: 要求高さとの偏差最小 → 支柱本数最小 → 繰り出し大（短支柱削減）
    under_allow, over_allow = 150, koma_pitch
    max_total = required_height + over_allow
    table = _compose_table(max_total, lengths)
    best: Optional[tuple[tuple, int, list[int]]] = None
    for jack in range(jack_min, jack_max + 1, 5):
        for delta in range(-under_allow, over_allow + 1, 5):
            posts_total = required_height + delta - jack
            if posts_total <= 0:
                continue
            pieces = table.get(posts_total)
            if pieces is None:
                continue
            score = (abs(delta), len(pieces), jack_max - jack)
            if best is None or score < best[0]:
                best = (score, jack, pieces)
    if best is None:
        raise ValueError(
            f"要求高さ{required_height}mmを構成できません"
            f"（支柱規格{lengths}、ジャッキ{jack_min}〜{jack_max}）"
        )
    _score, jack, pieces = best

    posts = _order_bottom_up(pieces)
    posts_alt = _alt_order(pieces)

    warnings = []
    if len(set(pieces)) < 2 and len(pieces) > 1:
        warnings.append(
            "支柱が単一寸法のため千鳥（ジョイント位置ずらし）を構成できません。"
            "隣接支柱の最下部を根がらみ用支柱等に置換してください"
        )

    # 根がらみ＝最下コマ（支柱下端から1コマ目）
    first_ledger = jack + koma_pitch
    # 作業層: 固定点は最上層作業床（支柱天端から手すり2コマ分下）。
    # そこから floor_height ピッチで下へ展開する（端数吸収は最下部）
    top = jack + sum(pieces)
    top_floor = top - 2 * koma_pitch
    level_heights = []
    h = top_floor
    while h > first_ledger + koma_pitch:
        level_heights.append(h)
        h -= floor_height
    level_heights.sort()

    return ElevationResult(
        required_height=required_height,
        jack_extension=jack,
        posts=posts,
        posts_alt=posts_alt,
        has_negarami=True,
        first_ledger_height=first_ledger,
        n_levels=len(level_heights),
        level_heights=level_heights,
        warnings=warnings,
    )
