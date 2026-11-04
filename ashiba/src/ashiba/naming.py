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


def _guids(v) -> list[str]:
    if isinstance(v, str) and len(v) == 36 and v.count("-") == 4:
        return [v]
    if isinstance(v, dict):
        return [g for x in v.values() for g in _guids(x)]
    if isinstance(v, (list, tuple)):
        return [g for x in v for g in _guids(x)]
    return []


def prune_gone(client, rec: dict) -> dict:
    """控えから、置いた要素がもう1つも無いもの（Archicad で消した）を除く. 読めなければそのまま.

    消したクレーンが控えに残り、次に置いたクレーンが「クレーン2」になって帳票にも消したものが出ていた（2026-11-05）.
    """
    keys = [k for k, v in rec.items() if _guids(v)]
    flat = [(k, g) for k in keys for g in _guids(rec[k])]
    if not flat:
        return rec
    try:
        dets = client.tapir("GetDetailsOfElements", {"elements": [{"elementId": {"guid": g}} for _k, g in flat]})
        rows = dets.get("detailsOfElements") or []
    except Exception:
        return rec
    if len(rows) != len(flat):
        return rec
    alive = {k for (k, _g), d in zip(flat, rows) if isinstance(d, dict) and "error" not in d}
    return {k: v for k, v in rec.items() if k in alive or not _guids(v)}
