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

from .dp import better
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
                if cand_best is None or better(cand, cand_best):
                    cand_best = cand
        if cand_best is not None:
            best[s] = cand_best
    return best


def _order_bottom_up(pieces: list[int]) -> list[int]:
    """基本形: 長尺を下から積み、最上部に短支柱（端数）を置く並び."""
    return sorted(pieces, reverse=True)


def _order_with_first(pieces: list[int], first: int) -> list[int]:
    """1段目を first（2700 等）にし、その上は長い順（3600 を積んで端数は最上部）."""
    rest = list(pieces)
    if first and first in rest:
        rest.remove(first)
        return [first] + _order_bottom_up(rest)
    return _order_bottom_up(rest)


def _alt_order(pieces: list[int]) -> list[int]:
    """千鳥用: 短い支柱を最下部に回した並び（ジョイント高さをずらす）."""
    if len(set(pieces)) < 2:
        return list(pieces)
    ordered = sorted(pieces, reverse=True)
    return [ordered[-1]] + ordered[:-1]


def solve_elevation_frame(
    required_height: int,
    master: PartMaster,
    jack_max: int = JACK_MAX_EXTENSION,
    jack_min: int = JACK_MIN_EXTENSION,
) -> ElevationResult:
    """枠組足場の立面: 建枠を積み上げる.

    くさび式と違いコマピッチの概念がなく、1層＝建枠1段。
    端数はくさび式と同じく最下部のジャッキ＋調整枠（高さの低い建枠）で吸収する。
    posts には建枠の高さを下から順に入れる（数量拾いが建枠段数として使う）。
    """
    heights = master.frame_heights()
    if not heights:
        raise ValueError(f"系列 {master.series_id} に建枠がありません")
    smallest = min(heights)

    # 建枠1段＋最小繰出しより低い足場は組めない
    min_buildable = jack_min + smallest
    if required_height < min_buildable:
        raise ValueError(
            f"要求高さ{required_height}mmは組立可能な最小高さ{min_buildable}mm"
            f"（ジャッキ{jack_min} + 最小建枠{smallest}）を下回ります"
        )

    # 超過側の許容は最小建枠まで。これ以上緩めると要求より大幅に高い解を許してしまう
    under_allow, over_allow = 150, smallest
    table = _compose_table(required_height + over_allow, heights)
    best: Optional[tuple[tuple, int, list[int]]] = None
    # ジャッキは1mm刻みで探す。5mm刻みだとインチ寸法の建枠（914・1219・1524）を
    # 混ぜた構成は総高さが5の倍数にならず候補から落ち、1524×5 のような
    # 「たまたま5の倍数になる」構成しか残らない
    for jack in range(jack_min, jack_max + 1):
        for delta in range(-under_allow, over_allow + 1, 5):
            total = required_height + delta - jack
            if total <= 0:
                continue
            pieces = table.get(total)
            if pieces is None:
                continue
            # 同じ枚数なら調整枠（標準枠より低い建枠）が少ない構成。
            # 日建の建枠は 1524/1219/914/490 と刻みが細かく、枚数だけで選ぶと
            # 1700×5＋1524×5 のような半分が調整枠の構成になっていた
            n_adjust = sum(1 for q in pieces if q != heights[0])
            score = (abs(delta), len(pieces), n_adjust, jack_max - jack)
            if best is None or score < best[0]:
                best = (score, jack, pieces)
    if best is None:
        raise ValueError(
            f"要求高さ{required_height}mmを建枠{heights}で構成できません"
        )
    _score, jack, pieces = best

    frames = sorted(pieces, reverse=True)     # 標準枠を下に、調整枠を上に
    frames_alt = _alt_order(pieces)
    top = jack + sum(frames)

    # 作業床は各建枠の天端。最上段は手すり分として使うため作業床から除く
    level_heights = []
    h = jack
    for f in frames[:-1] if len(frames) > 1 else frames:
        h += f
        level_heights.append(h)

    warnings = []
    if len(set(pieces)) < 2 and len(pieces) > 1:
        warnings.append(
            "建枠が単一高さのため千鳥（縦継ぎ位置ずらし）を構成できません。"
            "最下段を調整枠に置換してください"
        )
    if not level_heights:
        warnings.append(
            f"足場高さ{top}mmでは作業床が1層も取れません。"
            "要求高さを上げるか、作業床の要否を見直してください"
        )

    return ElevationResult(
        required_height=required_height,
        jack_extension=jack,
        posts=frames,
        posts_alt=frames_alt,
        has_negarami=True,
        first_ledger_height=jack,   # 枠組は建枠脚部が第一の布に相当
        n_levels=len(level_heights),
        level_heights=level_heights,
        warnings=warnings,
    )


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
    枠組系列のマスタが渡された場合は建枠の積み上げ（solve_elevation_frame）へ委譲する。
    """
    if post_lengths is None and master is not None and master.is_frame:
        return solve_elevation_frame(required_height, master, jack_max, jack_min)
    if post_lengths is None:
        assert master is not None, "master か post_lengths のどちらかが必要です"
        post_lengths = master.post_lengths()
    if floor_height is None:
        floor_height = master.floor_height if master else 1800
    if koma_pitch is None:
        koma_pitch = master.koma_pitch if master else 450
    lengths = sorted(set(post_lengths), reverse=True)

    # 支柱1本＋最小繰出しより低い足場は組めない
    min_buildable = jack_min + min(lengths)
    if required_height < min_buildable:
        raise ValueError(
            f"要求高さ{required_height}mmは組立可能な最小高さ{min_buildable}mm"
            f"（ジャッキ{jack_min} + 最小支柱{min(lengths)}）を下回ります"
        )

    # 端数は最下部のジャッキで吸収。要求高さと厳密一致しない場合は
    # ±許容窓（下-150〜上+1コマ）内で偏差最小の解を許す。
    # 優先順位: 要求高さとの偏差最小 → 支柱本数最小 → 繰り出し大（短支柱削減）
    # （受け入れ基準の実例 G(ジャッキ270)+3800×4+900=16370 を再現するため、この順は変えない。
    # 繰出しが上限に張り付いた場合は、調整代のある代替構成を警告で添える）
    under_allow, over_allow = 150, koma_pitch
    # 単管の建地は1m刻みで、布・手すりはどの高さにもクランプで付く。天端は手すりより上へ出てよい
    if master is not None and master.is_tube:
        over_allow = max(over_allow, 1000)
    band_lo, band_hi = jack_min + 50, jack_max - 70
    max_total = required_height + over_allow
    table = _compose_table(max_total, lengths)
    # 1段目（最下部）の支柱は基本 2700（階高1800の系列。1900 の系列は 2850＝階高×1.5）、そのあと 3600 を積み、
    # 端数は最上部（利用者の決め 2026-10-20）。1段目を短くすると最初の継ぎ目が低くなり、根がらみ・1層目の
    # 布材と継ぎ目がずれる。その系列に該当の長さが無い・高さが足りないときは従来の積み方
    first = int(round(floor_height * 1.5))
    if first not in lengths:
        first = 0
    best: Optional[tuple[tuple, int, list[int]]] = None
    best_band: Optional[tuple[tuple, int, list[int]]] = None
    # 支柱の和は5mmの倍数なので、繰出しは要求高さと5mmの端数を揃えて回す（スラブの天端から決めた
    # 5928mm のような高さで、5mm刻みの繰出しが一つも合わず「構成できません」になった）
    jack_start = jack_min + int(round(required_height - jack_min)) % 5
    for jack in range(jack_start, jack_max + 1, 5):
        for delta in range(-under_allow, over_allow + 1, 5):
            posts_total = required_height + delta - jack
            if posts_total <= 0:
                continue
            pieces = None
            lead = 1
            if first and posts_total >= first:
                rest = posts_total - first
                rest_pieces = [] if rest == 0 else table.get(rest)
                if rest_pieces is not None:
                    pieces = [first] + list(rest_pieces)
                    lead = 0
            if pieces is None:
                pieces = table.get(posts_total)
            if pieces is None:
                continue
            score = (lead, abs(delta), len(pieces), jack_max - jack)
            if best is None or score < best[0]:
                best = (score, jack, pieces)
            if band_lo <= jack <= band_hi:
                bscore = (lead, abs(delta), len(pieces), abs(jack - (band_lo + band_hi) / 2))
                if best_band is None or bscore < best_band[0]:
                    best_band = (bscore, jack, pieces)
    if best is None:
        raise ValueError(
            f"要求高さ{required_height}mmを構成できません"
            f"（支柱規格{lengths}、ジャッキ{jack_min}〜{jack_max}）"
        )
    _score, jack, pieces = best

    posts = _order_with_first(pieces, first)
    posts_alt = _alt_order(pieces)
    # 単管の建地は継手を千鳥にする（利用者の指定 2026-10-22）。同じ長さだけの構成は、隣の建地の最下部に半分の長さ
    # （6m→3m、4m→2m）を入れて上に回し、継ぎ目の高さを半分ずらす（本数・総長は同じ）
    if master is not None and master.is_tube and len(set(pieces)) < 2 and pieces:
        half = pieces[0] // 2
        if half in lengths and len(pieces) >= 1:
            posts_alt = [half] + list(pieces[:-1]) + [half]

    warnings = []
    # 繰出しが実務上限に張り付くと、地盤の凹凸を上へ吸収できない（L字棟で270mmちょうどが
    # 選ばれた）。調整代のある帯の構成を案として添える（採るかは計画者の判断）
    if jack > band_hi and best_band is not None and (best_band[1], best_band[2]) != (jack, pieces):
        alt_jack, alt_pieces = best_band[1], best_band[2]
        alt_total = alt_jack + sum(alt_pieces)
        alt_desc = "+".join(str(v) for v in _order_with_first(alt_pieces, first))
        warnings.append(
            f"ジャッキ繰出し{jack}mmは実務上限{jack_max}mmに近く、上への調整代がありません。"
            f"調整代を残すなら ジャッキ{alt_jack}+{alt_desc}＝{alt_total}mm"
            f"（要求高さとの差{alt_total - required_height:+d}mm）の構成も検討してください"
            "（scaffold_height_mm で高さを指定すれば切り替えられます）"
        )
    if len(set(pieces)) < 2 and len(pieces) > 1:
        warnings.append(
            "支柱が単一寸法のため千鳥（ジョイント位置ずらし）を構成できません。"
            "隣接支柱の最下部を根がらみ用支柱等に置換してください"
        )

    # コマの位置はカタログの支柱図（master.post_koma_offsets）。ND1800 は上端から55下が最上のコマで、
    # そこから450ピッチ。1段目の2700には下端から170に根がらみ用のコマがある（利用者の指摘 2026-10-21:
    # 支柱のフックの高さは450ピッチ、2700は根がらみ用のフックがある）。マスタが無ければ従来の
    # 「下端から1コマ目・上端がコマ」
    gap = master.koma_top_gap if master is not None else 0
    offs = master.post_koma_offsets(posts[0]) if master is not None else []
    # 根がらみ＝最下段の支柱の最下のコマ
    first_ledger = jack + (min(offs) if offs else koma_pitch)
    # 作業層: 固定点は最上層作業床（最上のコマから手すり2コマ分下）。
    # そこから floor_height ピッチで下へ展開する（端数吸収は最下部）
    top = jack + sum(pieces)
    top_floor = top - gap - 2 * koma_pitch
    level_heights = []
    h = top_floor
    while h > first_ledger + koma_pitch:
        level_heights.append(h)
        h -= floor_height
    level_heights.sort()
    if not level_heights:
        warnings.append(
            f"足場高さ{top}mmでは作業床が1層も取れません"
            f"（最上層は支柱天端から手すり{gap + 2 * koma_pitch}mm下、"
            f"最下層は根がらみ{first_ledger}mmより上に必要）。"
            "要求高さを上げるか、作業床の要否を見直してください"
        )

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


def truncate_elevation(elev: ElevationResult, eaves_mm: float, master: PartMaster) -> ElevationResult:
    """全体の立面（いちばん高い面）を、低い面の軒高で切った立面（セットバックの面ごとの高さ）.

    隣の面とコーナーの支柱・作業床の高さを共有するので、低い面は全体の作業床の並びのうち軒高に
    届く層までを使う（新しく解き直すと作業床の高さが隣とずれる）。支柱は下から全体の構成を積み、
    天端の余り（作業床から支柱天端まで）は全体と同じにして、足りない分を短い支柱1本で埋める。
    軒高が全体の最上層以上なら全体のまま返す。
    """
    levels = list(elev.level_heights)
    if not levels or eaves_mm >= levels[-1] - 1:
        return elev
    k = next((i for i, h in enumerate(levels) if h >= eaves_mm - 1), len(levels) - 1)
    keep = levels[:k + 1]
    margin = elev.total_height - levels[-1]           # 最上層の床から支柱天端まで（手すり分）
    target = keep[-1] + margin
    acc = elev.jack_extension
    posts: list[int] = []
    for p in elev.posts:
        if acc + p > target:
            break
        posts.append(p)
        acc += p
    rest = target - acc
    if rest > 0:
        lengths = sorted(master.post_lengths()) if not master.is_frame else sorted(set(elev.posts))
        fit = next((L for L in lengths if L >= rest), None)
        if fit is None and lengths:
            fit = lengths[-1]
        if fit:
            posts.append(int(fit))
    return ElevationResult(
        required_height=int(target), jack_extension=elev.jack_extension, posts=posts,
        posts_alt=_alt_order(posts), has_negarami=elev.has_negarami,
        first_ledger_height=elev.first_ledger_height, n_levels=len(keep), level_heights=keep,
        warnings=[],
    )
