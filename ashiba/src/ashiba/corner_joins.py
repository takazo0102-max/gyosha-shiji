"""ブラケット足場とくさびの本足場の出隅を繋ぐ（利用者の指定 2026-10-23: ブラケットとクサビ足場のコーナー部分は
くさび式がブラケットの支柱のところまで必要）.

面の組（face_forms）は組ごとに解くので、そのままだと出隅で本足場の面はブラケットの面の離れの線（約 300）で
開放端になり、ブラケットの支柱の列（離れ＋腕の長さ。約 900）まで届かない。ブラケットの面も隅の手前で終わる。

ここでは:
- 本足場の面を、ブラケットの面の側の端でスパンを足して、ブラケットの支柱の列まで延ばす
- ブラケットの面は、本足場の内側建地列の線から線まで（支柱を本足場の延長の端の内側建地に揃える）
- ブラケットの面の離れ（下限〜上限）は、延長の端がブラケットの支柱の列にちょうど揃う隅が多くなる値にする
- 揃わない隅・ブラケットの面の端数は、隙間をコーナーステップで納める（無理に繋がない）

結果は面の組の入力に「_joins」で渡し、build_model が割付に当てる（cli.solve_groups が2回解く）。
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .plan_solver import WEDGE_GAP_CLOSED_MM, CornerStep, _pick_spans, _wedge_gap_ok, achievable_sums


def _kind(model) -> str:
    c = model.config
    if c.scaffold_form == "本足場" and not model.master.is_frame:
        return "main"
    if c.scaffold_form == "一側足場" and c.single_row_kind == "ブラケット":
        return "bracket"
    return ""


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _coins(model) -> list[int]:
    return sorted({int(s) for s in model.master.span_lengths()})


def _extension(coins: list[int], need: float, clamp: bool = False) -> Optional[tuple[list[int], float]]:
    """本足場の面の延長: 合計 need 以下のスパン列と、残る隙間（0〜30 か 70〜400）。延長なし（隙間だけ）も可.

    clamp（単管のブラケット）: 単管はクランプでどこにでも留まるので、支柱の列を少し越えて延ばしてもよい
    （隙間は負＝越えた分。コーナーステップは要らない）。
    """
    cands = []
    if clamp:
        over = sorted(s for s in achievable_sums(coins, int(need), int(need) + max(coins)) if s >= need - 0.5)
        if over:
            cands.append((achievable_sums(coins, over[0], over[0])[over[0]], need - over[0]))
    if _wedge_gap_ok(need) or need <= WEDGE_GAP_CLOSED_MM:
        cands.append(([], need))
    got = _pick_spans(coins, need, max(coins), need_exact=False) if need >= min(coins) - WEDGE_GAP_CLOSED_MM else None
    if got is not None:
        cands.append(got)
    if not cands:
        return None
    # 揃う（隙間 30 以下）を先に、次にスパンの少ない方
    return min(cands, key=lambda c: (0 if c[1] <= WEDGE_GAP_CLOSED_MM else 1, len(c[0]), abs(c[1])))


def bracket_corner_joins(runs: list) -> dict[int, dict]:
    """面の組の結果 [(組の名前, PlanRun)] → {組の番号: _joins}. 繋ぐ隅が無ければ {}."""
    if len(runs) < 2:
        return {}
    owner: dict[int, int] = {}
    for k, (_lb, r) in enumerate(runs):
        for e in r.model.plan.edges:
            owner[e.edge_index] = k
    kinds = [_kind(r.model) for _lb, r in runs]
    outline = runs[0][1].model.plan.outline
    n = len(outline.edges)
    eps = {e.edge_index: e for _lb, r in runs for e in r.model.plan.edges}
    joins: dict[int, dict] = {}

    def slot(k: int) -> dict:
        return joins.setdefault(k, {"edges": {}, "steps": [], "drop_steps": [], "joined": [], "notes": []})

    for b, kb in sorted(owner.items()):
        if kinds[kb] != "bracket":
            continue
        ob = outline.edges[b]
        prev, nxt = (b - 1) % n, (b + 1) % n
        at_s = (ob.start_corner == "出隅" and prev in owner and owner[prev] != kb and kinds[owner[prev]] == "main")
        at_e = (ob.end_corner == "出隅" and nxt in owner and owner[nxt] != kb and kinds[owner[nxt]] == "main")
        if not (at_s or at_e):
            continue
        mb = runs[kb][1].model
        epb = eps[b]
        row_b = float(mb.post_row_spacing_mm)
        u_b, n_b = ob.direction, ob.outward
        # 本足場の面の、ブラケットの面の側の端の支柱（壁の線からの距離）
        ends = []                                      # (本足場の辺, 終点側か, 端の支柱の距離)
        if at_s:
            ep = eps[prev]
            q = (ep.start_post[0] + outline.edges[prev].direction[0] * sum(ep.spans),
                 ep.start_post[1] + outline.edges[prev].direction[1] * sum(ep.spans))
            ends.append((prev, True, _dot(_sub(q, ob.start), n_b)))
        if at_e:
            ep = eps[nxt]
            ends.append((nxt, False, _dot(_sub(ep.start_post, ob.start), n_b)))
        # 同じ組の隣の面と隅を共有していれば離れは動かせない（その隅が崩れる）
        so = mb.plan.standoff_spec
        fixed = ((not at_s and prev in owner and owner[prev] == kb) or (not at_e and nxt in owner and owner[nxt] == kb))
        lo, hi = (int(so.hard_min), int(so.max)) if so and not fixed else (int(epb.standoff), int(epb.standoff))
        target = float(so.target) if so else 300.0
        best = None
        for s2 in range(2 * lo, 2 * hi + 1):              # 0.5mm 刻み（本足場の離れは 334.5 など半端もある）
            s_b = s2 / 2.0
            d_b = s_b + row_b
            exts = []
            for ei, at_end, p in ends:
                got = (_extension(_coins(runs[owner[ei]][1].model), d_b - p, clamp=mb.master.is_tube)
                       if d_b - p >= 0 else None)
                if got is None:
                    break
                exts.append(got)
            else:
                key = (sum(1 for _sp, g in exts if g > WEDGE_GAP_CLOSED_MM), sum(len(sp) for sp, _g in exts),
                       round(sum(abs(g) for _sp, g in exts), 1), abs(s_b - target))
                if best is None or key < best[0]:
                    best = (key, float(s_b), exts)
        if best is None:
            slot(kb)["notes"].append(
                f"{mb.face_name(b)}（ブラケット）と隣の本足場の出隅は、本足場をブラケットの支柱の列まで延ばす"
                "スパンの組合せがありません。隅の納まりを別途検討してください")
            continue
        _key, s_b, exts = best
        # 本足場の面を延ばす
        msgs = []
        for (ei, at_end, _p), (ext, gap) in zip(ends, exts):
            km = owner[ei]
            ep = eps[ei]
            oe = outline.edges[ei]
            if at_end:
                new = dataclasses.replace(ep, spans=list(ep.spans) + list(ext),
                                          scaffold_length=float(sum(ep.spans) + sum(ext)),
                                          owned_post_count=ep.owned_post_count + len(ext),
                                          end_post=(ep.start_post[0] + oe.direction[0] * (sum(ep.spans) + sum(ext) + gap),
                                                    ep.start_post[1] + oe.direction[1] * (sum(ep.spans) + sum(ext) + gap)))
            else:
                L = sum(ext)
                new = dataclasses.replace(ep, spans=list(ext) + list(ep.spans),
                                          scaffold_length=float(sum(ep.spans) + L),
                                          owned_post_count=ep.owned_post_count + len(ext),
                                          start_post=(ep.start_post[0] - oe.direction[0] * L,
                                                      ep.start_post[1] - oe.direction[1] * L))
            slot(km)["edges"][ei] = new
            if at_end:
                slot(km)["drop_steps"].append(ei)          # 隅の手前で終わっていた隙間（終点の側）は延長に置き換わる
            if gap > WEDGE_GAP_CLOSED_MM:
                slot(km)["steps"].append(CornerStep(b if at_end else nxt, round(gap, 1), True, "", ei, at_start=not at_end))
            name = runs[km][1].model.face_name(ei)
            msgs.append(f"{name}を{'+'.join(str(s) for s in ext) or '延長なし'}"
                        + (f"・隙間 {gap:.0f}mm はコーナーステップ" if gap > WEDGE_GAP_CLOSED_MM else "") )
        # ブラケットの面: 本足場の内側建地列の線から線まで（繋がない端は元の位置）
        t0 = _dot(_sub(epb.start_post, ob.start), u_b)
        t1 = _dot(_sub(epb.end_post, ob.start), u_b)
        if at_s:
            t0 = -float(eps[prev].standoff)
        if at_e:
            t1 = ob.length + float(eps[nxt].standoff)
        got = _pick_spans(_coins(mb), t1 - t0, max(_coins(mb)), need_exact=False)
        if got is None:
            slot(kb)["notes"].append(f"{mb.face_name(b)}（ブラケット）を本足場の建地列の間に割り付けられません")
            continue
        spans, gap = got
        sp = (ob.start[0] + n_b[0] * s_b + u_b[0] * t0, ob.start[1] + n_b[1] * s_b + u_b[1] * t0)
        epp = (ob.start[0] + n_b[0] * s_b + u_b[0] * t1, ob.start[1] + n_b[1] * s_b + u_b[1] * t1)
        slot(kb)["edges"][b] = dataclasses.replace(epb, spans=spans, scaffold_length=float(sum(spans)), standoff=s_b,
                                                   owned_post_count=len(spans), start_post=sp, end_post=epp)
        slot(kb)["drop_steps"].append(b)
        if gap > WEDGE_GAP_CLOSED_MM and not mb.master.is_tube:     # 単管はクランプで留めるので隙間は布の重ねで
            slot(kb)["steps"].append(CornerStep(nxt, round(gap, 1), True, "", b))
        if at_s:
            slot(kb)["joined"].append((b, "s"))
        if at_e:
            slot(kb)["joined"].append((b, "e"))
        slot(kb)["notes"].append(
            f"{mb.face_name(b)}（ブラケット）の出隅は、隣のくさびの本足場をブラケットの支柱の列（壁から"
            f"{s_b + row_b:.0f}mm）まで延ばして繋ぎます（{'／'.join(msgs)}）。ブラケットの面は離れ {s_b:.0f}mm、"
            f"本足場の内側建地列の間に {'+'.join(str(s) for s in spans)}"
            + (("" if gap <= WEDGE_GAP_CLOSED_MM else
                f"、端の隙間 {gap:.0f}mm は単管の布を重ねてクランプで留める" if mb.master.is_tube else
                f"、端の隙間 {gap:.0f}mm はコーナーステップ")) + "（利用者の指定 2026-10-23）")
    return joins


def apply_joins(plan, joins: dict):
    """build_model から: 繋いだ隅の割付（面のスパン・端の位置・離れ）とコーナーステップを当てる."""
    if not joins:
        return plan
    edges = [joins["edges"].get(e.edge_index, e) for e in plan.edges]
    drop = set(joins.get("drop_steps") or [])
    steps = [c for c in (plan.corner_steps or []) if c.edge_index not in drop] + list(joins.get("steps") or [])
    standoffs = list(plan.standoffs)
    for ei, ep in joins["edges"].items():
        if 0 <= ei < len(standoffs):
            standoffs[ei] = float(ep.standoff)
    return dataclasses.replace(plan, edges=edges, corner_steps=steps, standoffs=standoffs,
                               warnings=list(plan.warnings) + list(joins.get("notes") or []))
