"""仮設工事の工程表（利用者の指定 2026-11-04「工程表作れる？」→ 仮設工事の工程表を Excel で）.

ashiba で置いた仮設の数量（ashiba_out の帳票: 仮囲い・仮設建物・敷鉄板・場内通路・根切り・構台・足場・型枠・クレーン）から、
作業ごとの日数＝数量 ÷（歩掛かりの日当り量 × 班の数）を出し、作業のつながり（前の作業が終わってから・始まってから何日）で
稼働日の暦（schedule_calendar.WorkCalendar）に並べる。躯体（基礎・地上の階ごと）と外装は仮設の段取りの物差しとして条件から
並べる（工程表の上で灰色の参考の線）。

作業のつながり（仮設計画の一般的な順。【目安】）:
- 準備: 仮囲い・ゲート → 仮設建物・仮設電気給排水・場内通路と敷鉄板
- 土工事: 山留め → 1次根切り → 構台の架設 → 根切り（床付け）→ 基礎躯体 → 埋戻し → 構台・山留めの撤去
- 揚重: タワークレーンの組立は地上躯体の前に、解体は躯体が上がってから
- 外部足場: 地上躯体を追って組み上げ（始めは地上躯体の始め、終わりは躯体の終わり＋最上部の手すりの日数）、外装が終わってから解体
- 型枠・支保工: 階ごとに躯体の中（基礎・地上の階のサイクル）
- 片付け: 仮設建物・仮囲いの撤去は最後
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field

from .schedule_calendar import WorkCalendar

GROUPS = ("準備", "山留め・土工", "構台", "揚重", "躯体（参考）", "外部足場", "型枠・支保工", "外装（参考）", "片付け")


@dataclass
class Dep:
    key: str
    kind: str = "FS"          # FS: 前が終わった翌稼働日から・SS: 前の始まりから・FF: 前の終わりまでは終わらない
    lag: int = 0              # 稼働日（負は先行）


@dataclass
class Task:
    key: str
    name: str
    group: str
    days: int = 1                         # 稼働日
    qty: float = 0.0
    unit: str = ""
    rate: str = ""                        # 歩掛かりの説明（日当り量・班・出典）
    deps: list = field(default_factory=list)
    ref: bool = False                     # 参考（躯体・外装）
    machine: str = ""                     # 使う重機・揚重機
    start: _dt.date | None = None
    end: _dt.date | None = None
    fixed: _dt.date | None = None         # 決めた始まり

    @property
    def label(self) -> str:
        return self.name


def days_of(qty: float, per_day: float, crews: int = 1) -> int:
    """数量 qty を日当り per_day（1班）× crews 班で → 稼働日（切り上げ、1日以上）."""
    if qty <= 0 or per_day <= 0:
        return 0
    return max(1, math.ceil(qty / (per_day * max(1, crews)) - 1e-9))


def schedule(tasks: list[Task], cal: WorkCalendar, start: _dt.date) -> list[Task]:
    """つながりを順に解いて始まりと終わりを入れる（前の作業が先に並んでいること）. 前に無い作業へのつながりは捨てる."""
    by = {}
    for t in tasks:
        s = cal.first_work(t.fixed or start)
        ff = None
        for d in t.deps:
            p = by.get(d.key)
            if p is None:
                continue
            if d.kind == "FS":
                s = max(s, cal.add(p.end, 1 + d.lag))
            elif d.kind == "SS":
                s = max(s, cal.add(p.start, d.lag))
            elif d.kind == "FF":
                e = cal.add(p.end, d.lag)
                ff = e if ff is None else max(ff, e)
        t.start = s
        t.end = cal.end_of(s, t.days)
        if ff is not None and ff > t.end:
            t.end = ff
            t.days = cal.count(t.start, t.end)
        by[t.key] = t
    return tasks


def display_order(tasks: list[Task]) -> list[Task]:
    """表の行の順: 区分（GROUPS の順）・始まり."""
    return sorted((t for t in tasks if t.start), key=lambda t: (GROUPS.index(t.group) if t.group in GROUPS else 99, t.start))


def span(tasks: list[Task]) -> tuple[_dt.date, _dt.date]:
    xs = [t for t in tasks if t.start]
    return min(t.start for t in xs), max(t.end for t in xs)


WEEKDAYS = "月火水木金土日"


def to_xlsx(tasks: list[Task], cal: WorkCalendar, path, title: str, notes: list[str] = (), basis: list[list] = (),
            conditions: list[tuple[str, str]] = (), steps: list = ()) -> None:
    """工程表の Excel（線表）: 見出し（月・日・曜）と作業の行。休みの日は灰、作業の線は区分の色、参考（躯体・外装）は灰の線.
    190 日を超えると1列＝1週."""
    from .xlsx_writer import (STYLE_BAR, STYLE_BOLD, STYLE_HEADER, STYLE_OFF, STYLE_SMALL, STYLE_TEXT, STYLE_TITLE, Cell,
                              Workbook, _col_name)

    s0, s1 = span(tasks)
    s0 = s0 - _dt.timedelta(days=s0.weekday())                         # 週の始め（月曜）から
    weekly = (s1 - s0).days > 190
    step = 7 if weekly else 1
    cols = []
    d = s0
    while d <= s1:
        cols.append(d)
        d += _dt.timedelta(days=step)
    wb = Workbook()
    sh = wb.sheet("工程表")
    head = ["区分", "作業", "数量", "単位", "日数", "始め", "終わり"]
    n0 = len(head)
    sh.add_cells([Cell(title, STYLE_TITLE)])
    sh.merges.append(f"A1:{_col_name(n0 + min(len(cols), 40) - 1)}1")
    sh.add_cells([Cell("　".join(notes))])
    # 月の行・日の行・曜の行
    rm = [Cell(h, STYLE_HEADER) for h in head] + [Cell("", STYLE_SMALL) for _ in cols]
    rd = [Cell("", STYLE_HEADER) for _ in head]
    rw = [Cell("", STYLE_HEADER) for _ in head]
    r_month = len(sh.rows) + 1
    m_start = 0
    for i, c in enumerate(cols):
        if i == 0 or c.month != cols[i - 1].month:
            if i:
                sh.merges.append(f"{_col_name(n0 + m_start)}{r_month}:{_col_name(n0 + i - 1)}{r_month}")
            m_start = i
            rm[n0 + i] = Cell(f"{c.year}年{c.month}月" if (i == 0 or c.month == 1) else f"{c.month}月", STYLE_SMALL)
        off = (not weekly) and not cal.is_work(c)
        rd.append(Cell(c.day, STYLE_OFF if off else STYLE_SMALL))
        rw.append(Cell(("週" if weekly else WEEKDAYS[c.weekday()]), STYLE_OFF if off else STYLE_SMALL))
    sh.merges.append(f"{_col_name(n0 + m_start)}{r_month}:{_col_name(n0 + len(cols) - 1)}{r_month}")
    for k in range(n0):
        sh.merges.append(f"{_col_name(k)}{r_month}:{_col_name(k)}{r_month + 2}")
    sh.add_cells(rm)
    sh.add_cells(rd)
    sh.add_cells(rw)
    sh.freeze = (len(sh.rows), n0)
    sh.landscape_a3 = True
    last = None
    for t in display_order(tasks):
        g = GROUPS.index(t.group) if t.group in GROUPS else 0
        row = [Cell(t.group if t.group != last else "", STYLE_TEXT), Cell(t.name + (f"（{t.machine}）" if t.machine else ""), STYLE_TEXT),
               Cell(round(t.qty, 1) if t.qty else "", STYLE_SMALL), Cell(t.unit, STYLE_SMALL), Cell(t.days, STYLE_SMALL),
               Cell(f"{t.start.month}/{t.start.day}", STYLE_SMALL), Cell(f"{t.end.month}/{t.end.day}", STYLE_SMALL)]
        last = t.group
        for c in cols:
            c1 = c + _dt.timedelta(days=step - 1)
            on = t.start <= c1 and t.end >= c and (weekly or cal.is_work(c))
            off = (not weekly) and not cal.is_work(c)
            row.append(Cell("", STYLE_BAR + (4 if t.ref else g) if on else (STYLE_OFF if off else STYLE_SMALL)))
        sh.add_cells(row)
        sh.row_heights[len(sh.rows) - 1] = 18
    for k, w in enumerate((11, 30, 7, 5, 5, 6, 6)):
        sh.set_width(k, w)
    for i in range(len(cols)):
        sh.set_width(n0 + i, 3.2 if weekly else 2.6)
    # 根拠
    b = wb.sheet("歩掛かり・根拠")
    b.add_title("作業の日数の根拠（数量 ÷（日当り × 班））", 6)
    b.add_header(["作業", "数量", "単位", "日数", "歩掛かり・班・出典", "数量の帳票"])
    for r in basis:
        b.add_cells([Cell(v, STYLE_TEXT) for v in r])
    for k, w in enumerate((30, 9, 6, 6, 80, 24)):
        b.set_width(k, w)
    if steps:
        st = wb.sheet("施工ステップ")
        st.add_title("施工ステップ（工程表の節目ごとの仮設。scripts/step_run.py で Archicad の模型を切り替える）", 6)
        lays = list(dict.fromkeys(k for x in steps for k in x.layers))
        st.add_header(["No", "節目", "日", "足場の高さ m"] + [k.replace("仮設工程_", "") for k in lays])
        for x in steps:
            st.add_cells([Cell(x.no, STYLE_SMALL), Cell(x.name, STYLE_TEXT), Cell(f"{x.date:%Y-%m-%d}", STYLE_SMALL),
                          Cell(x.scaffold_h or "", STYLE_SMALL)] +
                         [Cell({"作業中": "▲作業中", "あり": "●", "なし": ""}[x.layers.get(k, "なし")], STYLE_SMALL) for k in lays])
        for k, w in enumerate([5, 30, 11, 10] + [9] * len(lays)):
            st.set_width(k, w)
    c = wb.sheet("条件")
    c.add_title("工程表の条件", 3)
    for k, v in conditions:
        c.add_cells([Cell(k, STYLE_BOLD), Cell(v)])
    c.set_width(0, 26)
    c.set_width(1, 90)
    wb.save(path)


def to_markdown(tasks: list[Task], title: str, notes: list[str] = ()) -> str:
    out = [f"# {title}", ""] + [f"- {n}" for n in notes] + ["", "| 区分 | 作業 | 数量 | 日数 | 始め | 終わり | 歩掛かり |",
                                                          "|---|---|---|---|---|---|---|"]
    for t in display_order(tasks):
        if t.start:
            q = f"{t.qty:.1f}{t.unit}" if t.qty else ""
            out.append(f"| {t.group} | {t.name} | {q} | {t.days} | {t.start:%Y-%m-%d} | {t.end:%Y-%m-%d} | {t.rate} |")
    return "\n".join(out) + "\n"
