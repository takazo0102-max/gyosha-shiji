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


# ---------------------------------------------------------------- 階段室の位置（Phase 10-2）

def stairs_from_params(params: dict) -> list[tuple[int, int]]:
    """読み戻した stairList（「開始,長さ」の繰り返し mm）→ [(開始, 長さ)]."""
    vals = []
    for t in str(params.get("stairList") or "").split(","):
        t = t.strip()
        if not t:
            continue
        try:
            vals.append(int(round(float(t))))
        except ValueError:
            return []
    return [(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]


def stair_positions_from_readback(
    plan_edges: Iterable[dict], towers: Iterable[dict], readbacks: Iterable[tuple[tuple[float, float], dict]],
) -> tuple[Optional[list[dict]], list[str]]:
    """平面で引いた階段室の位置 → 入力の stairs.positions（全階段室ぶん）と案内.

    どれも動いていなければ None（入力を変えない）。動いていれば、全部の階段室を位置指定に
    する（positions を書くと自動配置をやめるので、動かしていない階段室も今の位置で書く）。
    スパン数は配置時の階段室のものを使う（部品は同じスパン数で長さを取り直している）。
    """
    plan_edges = list(plan_edges)
    by_edge: dict[int, list[dict]] = {}
    for t in towers:
        by_edge.setdefault(int(t["edge_index"]), []).append(t)
    for v in by_edge.values():
        v.sort(key=lambda t: float(t["start_mm"]))
    read: dict[int, list[tuple[int, int]]] = {}
    for origin, params in readbacks:
        e = match_edge(plan_edges, origin)
        if e is not None:
            read[int(e["edge_index"])] = stairs_from_params(params)
    face = {int(e["edge_index"]): e.get("face") or f"辺{e['edge_index']}" for e in plan_edges}
    notes: list[str] = []
    out: list[dict] = []
    moved = False
    for ei in sorted(by_edge):
        planned = by_edge[ei]
        got = read.get(ei)
        if got is None or len(got) != len(planned):
            if got is not None:
                notes.append(f"{face.get(ei, ei)}: 階段室の数が配置時と違うので位置は読み戻しません"
                             f"（配置{len(planned)}・部品{len(got)}）")
            got = [(int(float(t["start_mm"])), int(t.get("length_mm") or 0)) for t in planned]
        for t, (start, _length) in zip(planned, sorted(got)):
            if abs(start - float(t["start_mm"])) > 1:
                moved = True
                notes.append(f"{face.get(ei, ei)}: 階段室 {float(t['start_mm']):.0f} → {start}mm")
            out.append({"edge_index": ei, "start_mm": start, "span_count": int(t.get("span_count") or 2),
                        "reason": "平面で位置を指定（読み戻し）"})
    return (out if moved else None), notes


def merge_stairs(spec: dict, positions: list[dict]) -> dict:
    """入力の stairs.positions を置き換える（stairs の他の項目は残す）."""
    out = dict(spec)
    st = dict(out.get("stairs") or {})
    st["positions"] = [dict(p) for p in positions]
    st.pop("count", None)          # 位置指定のときは箇所数は positions の数
    out["stairs"] = st
    return out


# ---------------------------------------------------------------- 荷受けステージ・昇降機の位置（Phase 10-2）

def _groups(text, size: int) -> list[list[int]]:
    vals = []
    for t in str(text or "").split(","):
        t = t.strip()
        if not t:
            continue
        try:
            vals.append(int(round(float(t))))
        except ValueError:
            return []
    return [vals[i:i + size] for i in range(0, len(vals) - size + 1, size)]


def _distinct_firsts(groups: list[list[int]]) -> list[int]:
    out: list[int] = []
    for g in groups:
        if g and g[0] not in out:
            out.append(g[0])
    return out


def platform_moves_from_readback(
    plan_edges: Iterable[dict], platforms: Optional[dict], readbacks: Iterable[tuple[tuple[float, float], dict]],
) -> tuple[list[tuple[int, float, int]], list[tuple[int, float, int]], list[str]]:
    """平面で引いたステージ・昇降機 → (ステージの移動, 昇降機の移動, 案内).

    移動は (辺, 配置時の位置, 読み戻した位置)。部品のリストは Python が送った順
    （plan.json の platforms の順を辺で絞ったもの）に並んでいるので、順番で対応を取る。
    ステージは層ごとに同じ開始の組が並ぶので、最初に現れた開始位置の順で数える。
    """
    plan_edges = list(plan_edges)
    platforms = platforms or {}
    face = {int(e["edge_index"]): e.get("face") or f"辺{e['edge_index']}" for e in plan_edges}
    read: dict[int, dict] = {}
    for origin, params in readbacks:
        e = match_edge(plan_edges, origin)
        if e is not None:
            read[int(e["edge_index"])] = params
    stage_moves: list[tuple[int, float, int]] = []
    hoist_moves: list[tuple[int, float, int]] = []
    notes: list[str] = []
    for kind, key, items, moves, size in (
        ("荷受けステージ", "stageList", platforms.get("stages") or [], stage_moves, 5),
        ("昇降機", "hoistList", platforms.get("hoists") or [], hoist_moves, 5),
    ):
        field_name = "start_mm" if key == "stageList" else "position_mm"
        by_edge: dict[int, list[dict]] = {}
        for it in items:
            by_edge.setdefault(int(it["edge_index"]), []).append(it)
        for ei, planned in by_edge.items():
            if ei not in read:
                continue
            got = _distinct_firsts(_groups(read[ei].get(key), size))
            if len(got) != len(planned):
                notes.append(f"{face.get(ei, ei)}: {kind}の数が配置時と違うので位置は読み戻しません"
                             f"（配置{len(planned)}・部品{len(got)}）")
                continue
            for it, new in zip(planned, got):
                old = float(it[field_name])
                if abs(new - old) > 1:
                    moves.append((ei, old, new))
                    notes.append(f"{face.get(ei, ei)}: {kind} {old:.0f} → {new}mm")
    return stage_moves, hoist_moves, notes


def merge_platform_moves(spec: dict, plan_edges: Iterable[dict], stage_moves, hoist_moves) -> tuple[dict, list[str]]:
    """入力の loading_stages・hoists の位置を書き換える（辺は edge_index か face で照合）."""
    face = {int(e["edge_index"]): e.get("face") for e in plan_edges}
    out = dict(spec)
    notes: list[str] = []
    for key, field_name, moves, kind in (("loading_stages", "start_mm", stage_moves, "荷受けステージ"),
                                         ("hoists", "position_mm", hoist_moves, "昇降機")):
        if not moves:
            continue
        items = [dict(x) for x in (spec.get(key) or [])]
        for ei, old, new in moves:
            hit = next((x for x in items
                        if (x.get("edge_index") == ei or (x.get("edge_index") is None and x.get("face") == face.get(ei)))
                        and abs(float(x.get(field_name, -1e9)) - old) <= 1), None)
            if hit is None:
                notes.append(f"{face.get(ei) or ei}: 入力に位置{old:.0f}の{kind}が見つからないので書き換えません")
                continue
            hit[field_name] = new
        out[key] = items
    return out, notes


def levels_from_params(params: dict) -> list[int]:
    """読み戻した levelList（作業床の高さ mm, 下から）→ 整数の列."""
    out: list[int] = []
    for tok in str(params.get("levelList") or "").split(","):
        tok = tok.strip()
        if tok:
            out.append(int(round(float(tok))))
    return out


def height_from_readback(plan: dict, readbacks: Iterable[tuple[tuple[float, float], dict]]) -> tuple[Optional[int], list[str]]:
    """3D の天端のホットスポットで引いた足場高さ → 新しい scaffold_height_mm（変わっていなければ None）.

    部品は引いた量を作業層の単位に丸めて levelList を書き換える（この面だけ）。最上層の作業床が
    配置時からいくつ動いたかを、配置時の足場高さに足して全面の目標高さにする。面ごとに違う量を
    引いていれば、いちばん大きく動いた面を採って注意に出す。
    """
    elev = plan.get("elevation") or {}
    old_levels = [int(v) for v in elev.get("level_heights") or []]
    base = plan.get("scaffold_height_mm")
    if not old_levels or base is None:
        return None, []
    old_top = old_levels[-1]
    deltas: list[tuple[int, str]] = []
    for origin, params in readbacks:
        got = levels_from_params(params)
        if not got or got == old_levels:
            continue
        e = match_edge(plan.get("edges") or [], origin)
        label = (e.get("face") if e else None) or (f"辺{e.get('edge_index')}" if e else "足場ライン")
        deltas.append((got[-1] - old_top, label))
    deltas = [(d, lb) for d, lb in deltas if d != 0]
    if not deltas:
        return None, []
    d, label = max(deltas, key=lambda t: abs(t[0]))
    notes = []
    if len({v for v, _ in deltas}) > 1:
        notes.append("面ごとに違う高さに引かれています（" + "・".join(f"{lb} {v:+d}mm" for v, lb in deltas)
                     + f"）。{label}の {d:+d}mm を全面に使います")
    new_h = int(base) + d
    notes.append(f"足場高さ: {int(base)} → {new_h}mm（{label}の天端を {d:+d}mm 引いた。全面をこの高さで解き直します）")
    return new_h, notes
