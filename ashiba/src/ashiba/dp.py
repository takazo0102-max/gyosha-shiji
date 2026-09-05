"""割付DPで共通の「良い構成」の判断.

平面（スパン割）と立面（支柱の積み上げ）は別のソルバだが、構成の良し悪しの
基準は同じ: **本数が少ない方が良く、同数なら大きい部材を使う方が良い**。
以前は両方に同じ関数が別々に置かれており、片方だけ直せば静かに食い違った。
"""

from __future__ import annotations


def better(a, b) -> bool:
    """構成 a が b より良いか（本数最小、同数なら長尺優先）."""
    if len(a) != len(b):
        return len(a) < len(b)
    return tuple(sorted(a, reverse=True)) > tuple(sorted(b, reverse=True))


def better_desc(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """降順で持っている構成どうしの比較（ソートを省ける速い版）."""
    if len(a) != len(b):
        return len(a) < len(b)
    return a > b


def insert_desc(seq: tuple[int, ...], value: int) -> tuple[int, ...]:
    """降順のタプルに1要素を降順のまま挿入する."""
    i = 0
    while i < len(seq) and seq[i] >= value:
        i += 1
    return seq[:i] + (value,) + seq[i:]


def spans_text(spans) -> str:
    """寸法の並びを読める形に（連続する同じ寸法は「1829×16」にまとめ、並び順は保つ）.

    30m面のスパン構成や支柱構成を「1829+1829+…」と並べても読む側は数えるしかない。
    割付レポート・ジャッキ量一覧で共用。
    """
    out = []
    run = None
    n = 0
    for sp in list(spans) + [None]:
        if sp == run:
            n += 1
            continue
        if run is not None:
            out.append(f"{run}×{n}" if n > 1 else str(run))
        run, n = sp, 1
    return "+".join(out)
