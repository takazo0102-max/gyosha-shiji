"""置いたものの名前の番号（「柵1」「通路2」…）.

控え（線の GUID → 置いた部品）の並びで番号を振る: 前に同じ線に置いたものはその番号のまま、新しい線は控えの続きの番号。
（2本目の柵も「柵1」、2本目の通路も「通路1」になり、帳票と図面で見分けられなかった。利用者の指定 2026-11-05「使いやすいように」）
"""

from __future__ import annotations


def ordinal(rec: dict, key: str, new_so_far: int) -> int:
    """控え rec の中の key の番号（1から）. key が無ければ 控えの数＋この回で新しく足した数＋1."""
    keys = list(rec)
    if key in keys:
        return keys.index(key) + 1
    return len(keys) + new_so_far + 1
