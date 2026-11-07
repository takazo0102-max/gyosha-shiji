"""デッキの状態と、建て方の時点の親綱・水平ネットの判定（利用者の指定 2026-11-07「その作りで進めて」）.

reports/デッキプレートの敷設時期.md の提案による。どの階から敷くかの標準は見つからないので、状態を階×工区ごとに持ち、階の順が未定の間は
H（下の面までの落差）の下限と上限を両方出す。下限で親綱とネット、上限で器具を判定する。

段階: 0 なし・1 先行敷き・敷き込み中・2 仮留め済み・3 納め完了・4 打設済み。役目を分ける: 落ちたら当たる面は 1 から、作業床は 3 から
（既定。仮留めで足りるかは資料で決まらないので安全側）、落下を受ける床は 4 から。
既定の時系列: 節 n を建てるとき、節 n−lag 以下は 2、節 n の中は未定（0 か 1）。3 と 4 は自動で進めず、done_node・cast_node で入れる.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lifeline import HARNESS_BUILD, HARNESS_MUST, judge_drop
from .opening_guard import NET_DOWN_MM

STAGES = ("なし", "先行敷き・敷き込み中", "仮留め済み", "納め完了", "打設済み")
UNDECIDED = "0か1"
ORDERS = ("未定", "上から", "下から", "階ごとに追いかけ")


@dataclass
class DeckOptions:
    floor_order: str = "未定"            # 節の中のデッキの階の順
    lag: int = 1                         # 下の節の遅れ（節の数。数字の資料は無く【目安】）
    work_stage: int = 3                  # 作業床に数える段階（2 仮留め・3 本付け）
    done_node: int = 0                   # この節まで納め完了
    cast_node: int = 0                   # この節まで打設済み


@dataclass
class FloorRow:
    step: int
    step_name: str
    zone: int
    node: int
    top: float                           # 階の梁の上端 mm
    stage: str                           # 段階の名前
    h_low: float
    h_high: float
    rope: str                            # 親綱の判定
    rope_note: str
    harness: str
    net: str
    current: bool                        # このステップで建てる節の階か


def floors_of(steps: list) -> dict:
    """工区ごとの階 {工区: {梁の上端 mm: 節}}（梁のある高さ）."""
    out: dict = {}
    for s in steps:
        for b in s.beams:
            out.setdefault(b.zone, {})[round(b.z + b.h / 2.0)] = b.node
    return out


def stage_of(node: int, current_node: int, o: DeckOptions) -> int | None:
    """節 node の階の段階（建てている節が current_node のとき）. None は未定（0 か 1）."""
    if o.cast_node and node <= o.cast_node:
        return 4
    if o.done_node and node <= o.done_node:
        return 3
    if node <= current_node - o.lag:
        return 2
    return None


def harness_note(h: float) -> str:
    """器具（H の上限で見る）."""
    if h > HARNESS_MUST:
        return "フルハーネス型（6.75m 超）"
    if h > HARNESS_BUILD:
        return "フルハーネス型（建設業 5m 超）"
    return "フルハーネス推奨"


def net_note(h_low: float, bay: float) -> str:
    """水平ネットの判定: 下の空き＝H の下限−ネットの下がり と 0.85L を比べる（10cm 網目。L は区画の短辺）."""
    if bay <= 0:
        return "-"
    room = h_low - NET_DOWN_MM
    need = 0.85 * bay
    if room >= need:
        return f"空き {room / 1000:.2f}m ≧ {need / 1000:.2f}m"
    return f"空き {room / 1000:.2f}m ＜ {need / 1000:.2f}m → 短辺を {room / 0.85 / 1000:.1f}m 以下に"


def floor_rows(steps: list, base: float, o: DeckOptions, bay: float = 0.0) -> list:
    """ステップごと・建てた階ごとの判定. base は地盤の高さ mm."""
    floors = floors_of(steps)
    done: dict = {}                      # 工区 → 建て終えた節
    rows = []
    for s in steps:
        done[s.zone] = max(done.get(s.zone, 0), s.node)
        cur = done[s.zone]
        tops = sorted(t for t, n in floors.get(s.zone, {}).items() if n <= cur)
        for t in tops:
            n = floors[s.zone][t]
            st = stage_of(n, cur, o)
            below = [x for x in tops if x < t]
            near = below[-1] if below else base
            sure = [x for x in below if stage_of(floors[s.zone][x], cur, o) is not None]
            if o.floor_order in ("下から", "階ごとに追いかけ"):
                far = near
            else:
                far = sure[-1] if sure else base
            if o.floor_order == "上から":
                near = far
            lo, hi = t - near, t - far
            if st is not None and st >= o.work_stage:
                rope, note = "対象外", "作業床として第519条の端部と開口の判定へ。外周の親綱は残す"
            else:
                rope, note = judge_drop(lo)
            label = UNDECIDED if st is None else f"{st} {STAGES[st]}"
            rows.append(FloorRow(s.no, s.name, s.zone, n, float(t), label, lo, hi, rope, note, harness_note(hi), net_note(lo, bay), n == s.node))
    return rows


def bay_short(xs: list, ys: list) -> float:
    """区画の短辺の大きいほう mm（柱の通りの間隔から。水平ネットの L に使う）."""
    def widest(v):
        v = sorted(set(round(x) for x in v))
        return max((b - a for a, b in zip(v, v[1:])), default=0.0)

    dx, dy = widest(xs), widest(ys)
    return min(d for d in (dx, dy) if d > 0) if dx > 0 or dy > 0 else 0.0


def lookup(table: list, zone: int, top: float) -> tuple | None:
    """建てるときの H の (下限, 上限) mm. 控え（to_records）から、その工区・階を探す. 無ければ None."""
    hit = [r for r in table if r["zone"] == zone and abs(r["top"] - top) <= 300.0 and r["current"]]
    if not hit:
        return None
    return min(r["h_low"] for r in hit), max(r["h_high"] for r in hit)


def to_records(rows: list) -> list:
    return [{"step": r.step, "zone": r.zone, "node": r.node, "top": r.top, "h_low": r.h_low, "h_high": r.h_high, "current": r.current} for r in rows]


def to_sheet(wb, rows: list) -> None:
    sh = wb.sheet("墜落防止の段階")
    sh.add_title("デッキの段階と親綱・水平ネットの判定", 9)
    sh.add_header(["ステップ", "工区・節", "階の高さ m", "デッキ", "H 下限 m", "H 上限 m", "親綱", "器具", "水平ネット"])
    for r in rows:
        sh.add([r.step, r.step_name, round(r.top / 1000.0, 2), r.stage, round(r.h_low / 1000.0, 2), round(r.h_high / 1000.0, 2), r.rope, r.harness, r.net])
    sh.add(["", "", "", "", "", "", "", "", ""])
    sh.add(["デッキを敷く階の下には防網を張る。未固定のデッキに人も荷も載せない。段階の見方と H の区分は報告（デッキプレートの敷設時期）の提案で、実務者の確認が要る"])
    for i, wdt in enumerate((8, 14, 10, 18, 9, 9, 8, 24, 34)):
        sh.set_width(i, wdt)


def to_markdown(rows: list) -> str:
    md = ["# デッキの段階と親綱・水平ネットの判定", "", "| ステップ | 工区・節 | 階の高さ | デッキ | H 下限 | H 上限 | 親綱 | 内容 | 器具 | 水平ネット |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r.step} | {r.step_name} | {r.top / 1000:.2f}m | {r.stage} | {r.h_low / 1000:.2f}m | {r.h_high / 1000:.2f}m | {r.rope} | {r.rope_note} | {r.harness} | {r.net} |")
    md += ["", "H は親綱を張る梁の上端から下の面まで。下限は親綱とネット、上限は器具の判定に使う。デッキを敷く階の下には防網を張る。",
           "段階と H の区分は reports/デッキプレートの敷設時期.md の提案で、実務者の確認が要る。別表6 の式の扱いは通達の値で、法令違反の判定ではない。"]
    return "\n".join(md) + "\n"
