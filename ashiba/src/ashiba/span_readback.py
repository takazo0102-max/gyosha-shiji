"""Archicad 上でホットスポット編集したスパンを読み戻し、span_overrides にする.

足場ラインは平面の支柱位置を引くと、1D スクリプトが規格寸法に吸着して spanList を
書き戻す。その spanList をこのモジュールで plan.json（配置時の割付）と突き合わせ、
変わった面だけを入力の span_overrides に落とす。次の実行は同じ割付を再現しつつ、
壁つなぎ・数量・法規を解き直す（部品の編集だけでは帳票が追従しない）。
"""

from __future__ import annotations

import math
from typing import Iterable, Optional


def spans_from_params(params: dict) -> list[int]:
    """読み戻した GDL パラメータ（spanList, spanList2）→ スパン列[mm]."""
    out: list[int] = []
    for key in ("spanList", "spanList2"):
        raw = str(params.get(key) or "").strip()
        if not raw:
            continue
        for tok in raw.split(","):
            tok = tok.strip()
            if tok:
                out.append(int(round(float(tok))))
    return out


def match_edge(plan_edges: Iterable[dict], origin_mm: tuple[float, float], tol_mm: float = 5.0) -> Optional[dict]:
    """オブジェクトの原点に一致する plan.json の辺（配置位置が tol 以内）."""
    for e in plan_edges:
        pl = e.get("placement") or {}
        if math.hypot(pl.get("x_mm", 1e18) - origin_mm[0], pl.get("y_mm", 1e18) - origin_mm[1]) <= tol_mm:
            return e
    return None


def overrides_from_readback(
    plan_edges: Iterable[dict], readbacks: Iterable[tuple[tuple[float, float], dict]], allowed: Iterable[int] = (),
) -> tuple[list[dict], list[str]]:
    """(原点, 読み戻しパラメータ) の列 → 変わった面の span_overrides と注意.

    面の長さが変わる読み戻し（吸着の残りが規格外になった等）はそのまま通さず注意に出す。
    """
    allowed_set = {int(v) for v in allowed}
    overrides: list[dict] = []
    warnings: list[str] = []
    for origin, params in readbacks:
        e = match_edge(plan_edges, origin)
        if e is None:
            continue
        got = spans_from_params(params)
        want = [int(v) for v in e.get("spans") or []]
        if not got or got == want:
            continue
        label = e.get("face") or f"辺{e.get('edge_index')}"
        if abs(sum(got) - sum(want)) > 1:
            warnings.append(f"{label}: 読み戻したスパンの合計{sum(got)}が面の長さ{sum(want)}と違うので採用しません（{got}）")
            continue
        odd = [v for v in got if allowed_set and v not in allowed_set]
        if odd:
            warnings.append(f"{label}: 規格外のスパン {sorted(set(odd))} を含みます（吸着の残り）。隣の境界も動かして規格に揃えてください")
        overrides.append({"edge_index": int(e["edge_index"]), "face": e.get("face"), "spans_mm": got})
    return overrides, warnings


def merge_overrides(spec: dict, overrides: list[dict]) -> dict:
    """入力 JSON の span_overrides に、同じ辺のものは置き換えて足す（他は残す）."""
    out = dict(spec)
    current = [dict(o) for o in (spec.get("span_overrides") or [])]
    by_edge = {int(o["edge_index"]): o for o in current if o.get("edge_index") is not None}
    for o in overrides:
        by_edge[int(o["edge_index"])] = {"edge_index": int(o["edge_index"]), "spans_mm": list(o["spans_mm"])}
    out["span_overrides"] = [by_edge[k] for k in sorted(by_edge)]
    return out


def snap_boundary(spans: list[int], i: int, want_mm: float, allowed: Iterable[int]) -> list[int]:
    """部品の1Dスクリプトと同じ吸着規則（境界 i の手前のスパン長を want_mm に引いたとき）.

    1) 隣の境界まで引いた（残りが最小規格の半分未満）: 2本を結合。合計が規格寸法のときだけ
    2) 手前を規格寸法に吸着。残りが規格ならそのまま、違えば規格2本（大＋小）に分けて1本挿入
    3) どちらもできなければ動かさない
    i は 1 始まりの境界番号（spans[i-2] と spans[i-1] の間）。GDL のテストはこの関数の値と突き合わせる。
    """
    sizes = sorted({int(v) for v in allowed}, reverse=True)
    if not sizes or i < 2 or i > len(spans):
        return list(spans)
    out = list(spans)
    a, b = out[i - 2], out[i - 1]
    pair = a + b
    smin = min(sizes)
    if (want_mm < smin / 2 or want_mm > pair - smin / 2) and pair in sizes:
        return out[: i - 2] + [pair] + out[i:]
    best, bd = 0, float("inf")
    for s_ in sizes:
        rem = pair - s_
        ok = rem in sizes or any(rem - x in sizes for x in sizes if rem - x > 0)
        if ok and abs(s_ - want_mm) < bd:
            best, bd = s_, abs(s_ - want_mm)
    if best == 0 or best == a:
        return out
    rem = pair - best
    if rem in sizes:
        return out[: i - 2] + [best, rem] + out[i:]
    if len(out) >= 60:
        return out
    for x in sizes:
        y = rem - x
        if y in sizes and y <= x:
            return out[: i - 2] + [best, x, y] + out[i:]
    return out
