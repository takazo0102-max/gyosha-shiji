"""工程表・仮設の金額の前に、拾った数量のおかしな所を点検する（利用者の指定 2026-11-04「工程表と連動した施工計画の精度を
高めておかしなところは修正して」）.

帳票の写しで工程表を流して見つけたこと（足場の計画が1面 3.7m だけで 29.7掛m²、消したタワークレーンの帳票が残る など）を、
数量から分かる範囲で「注意」として工程表と金額の帳票に出す。直すのは利用者（置き直す・条件を入れる）.
"""

from __future__ import annotations

from .schedule import Task
from .schedule_sources import Quantities


def checks(q: Quantities, tasks: list[Task], floors: int = 0) -> list[str]:
    by = {t.key: t for t in tasks}
    out = []
    if q.scaffold_m2 and q.scaffold_edges and q.scaffold_edges < 3:
        out.append(f"外部足場の計画（{q.sources.get('外部足場', '')}）は {q.scaffold_edges}面・延べ {q.scaffold_len:g}m だけ。建物の全部の面を"
                   "置いた計画で流さないと、足場の日数・金額が小さく出る")
    if "frame" in by and not q.scaffold_m2:
        out.append("外部足場の計画（*_plan.json）が無い。工程表に足場が出ず、金額にも入らない")
    nfl = floors or (round(q.scaffold_h / 3.5) if q.scaffold_h else 0)
    if not q.hoarding_m and nfl >= 2:
        out.append("仮囲いが無い。木造以外で2階以上（木造は高さ13m・軒9m 超）の工事は、高さ 1.8m 以上の仮囲いが要る"
                   "（建築基準法施行令 136条の2の20。周りに同じ高さ以上の塀があるなどの除外あり）")
    if not q.house_units and not q.toilet_units:
        out.append("仮設建物（現場事務所・休憩所・便所）が無い。便所は労働安全衛生規則 628条（男性用・女性用の別、人数に応じた数）")
    if q.retaining and q.retaining_m == 0 and not ("yama" in by and by["yama"].qty):
        out.append("山留めの延長が分からない（山留め足場.md の腹起し上の足場が無い）。工程表_条件.json の override に retaining_m を入れる")
    if q.excavation_m3 and not q.backfill_m3:
        out.append("根切りはあるが埋戻しが 0。根切り図の埋戻しを確かめる")
    if q.deck_m2 and "ex2" not in by:
        out.append("乗入れ構台があるが根切りが無い（構台の撤去と2次根切りの順が決まらない）")
    if q.tower and q.scaffold_h and "frame" not in by:
        out.append("タワークレーンがあるが地上躯体の工程が無い")
    return out
