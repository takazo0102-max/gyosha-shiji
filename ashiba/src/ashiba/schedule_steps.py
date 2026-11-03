"""工程表に合わせた模型（施工ステップ）: 工程表の節目ごとに、どの仮設が立っているか・足場がどの高さまで組み上がっているか
（利用者の指定 2026-11-04「工程表に合わせてモデルを自動作成できるようにして」）.

- 仮設の要素は控え（ashiba_out の *.json の GUID）ごとに「現れる作業」と「消える作業」に結びつける（GROUP_TASKS）。
  ステップの日に、現れる作業が始まっていて、消える作業が終わっていなければ見せる
- 節目: 準備の終わり・山留めの終わり・構台の架設の終わり・根切りの終わり・基礎躯体の終わり・地上躯体の各階の終わり・
  外装の終わり・足場の解体の終わり・片付けの終わり（工程表に無い作業の節目は出さない）
- 足場の高さ: 外部足場の組立の進み（稼働日の割合）× 足場の高さ（最初の層の高さより低くはしない）。地上躯体の各階の終わりでは
  その階の高さ＋1層（足場は躯体の1層先行）の目安
Archicad の側（scripts/step_run.py）は、要素を作業ごとのレイヤー「仮設工程_…」に移し、ステップを選ぶとレイヤーの表示を切り替え、
足場の部品の stepH（この高さより上を描かない）を入れる.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from .schedule import Task
from .schedule_calendar import WorkCalendar

# 控えの名前 → (レイヤー名, 現れる作業, 消える作業)。作業は前から順に工程表にあるものを使う
GROUP_TASKS = {
    "仮囲い.json": ("仮設工程_仮囲い", ("kakoi",), ("kakoi_x",)),
    "柵.json": ("仮設工程_仮囲い", ("kakoi",), ("kakoi_x",)),
    "仮設建物.json": ("仮設工程_仮設建物", ("house",), ("house_x",)),
    "仮設電気給排水.json": ("仮設工程_仮設建物", ("util", "house"), ("house_x",)),
    "敷鉄板.json": ("仮設工程_敷鉄板", ("plate",), ("plate_x",)),
    "場内通路.json": ("仮設工程_敷鉄板", ("plate",), ("plate_x",)),
    "根切り.json": ("仮設工程_根切り", ("ex1", "ex2"), ("fill",)),
    "山留め足場.json": ("仮設工程_山留め", ("ex1", "ex2", "yama"), ("yama_x", "fill")),
    "構台.json": ("仮設工程_構台", ("kodai",), ("kodai_x",)),
    "タワークレーン.json": ("仮設工程_揚重", ("tc_up",), ("tc_dn",)),
    "クレーン.json": ("仮設工程_揚重", ("frame",), ("frame",)),
    "@足場": ("仮設工程_外部足場", ("sc_up",), ("sc_dn",)),          # 足場の部品（ライブラリ部品の名前で拾う: SCAFFOLD_PARTS）
    "開口養生.json": ("仮設工程_開口養生・親綱", ("frame",), ("facade",)),
    "親綱.json": ("仮設工程_開口養生・親綱", ("frame",), ("frame",)),
    "支保工足場.json": ("仮設工程_型枠", ("form", "frame"), ("form", "frame")),
    "型枠.json": ("仮設工程_型枠", ("form", "frame"), ("form", "frame")),
}
LAYERS = tuple(dict.fromkeys(v[0] for v in GROUP_TASKS.values()))
# 外部足場の部品（ライブラリ部品の名前の頭。足場の高さで切る stepH は ashiba_line・ashiba_sheet・ashiba_net・ashiba_tie が持つ）
SCAFFOLD_PARTS = ("ashiba_line", "ashiba_tie", "ashiba_net", "ashiba_netbk", "ashiba_sheet", "ashiba_cstep", "ashiba_bridge",
                  "ashiba_stage", "ashiba_kbrk", "ashiba_hoist", "ashiba_hstage", "ashiba_member", "ashiba_box", "ashiba_side",
                  "ashiba_cfill")


@dataclass
class Step:
    no: int
    name: str
    date: _dt.date
    layers: dict = field(default_factory=dict)       # レイヤー名 → "作業中" / "あり" / "なし"
    scaffold_h: float = 0.0                         # 組み上がった足場の高さ m（0 は無し）
    note: str = ""


def _task(tasks: dict, keys) -> Task | None:
    for k in keys:
        if k in tasks and tasks[k].start:
            return tasks[k]
    return None


def layer_state(tasks: dict, group: str, d: _dt.date) -> str:
    """ステップの日 d に控え group の要素があるか: なし・作業中（現れる作業か消える作業の途中）・あり."""
    _layer, ups, downs = GROUP_TASKS[group]
    up, dn = _task(tasks, ups), _task(tasks, downs)
    if up is None or d < up.start:
        return "なし"
    if dn is not None and dn is not up and d > dn.end:
        return "なし"
    if dn is up and d > up.end:                      # 使う間だけ（移動式クレーン・型枠は躯体の間）
        return "なし"
    if d <= up.end or (dn is not None and dn is not up and d >= dn.start):
        return "作業中"
    return "あり"


def scaffold_height(tasks: dict, d: _dt.date, cal: WorkCalendar, height: float, first: float) -> float:
    up, dn = tasks.get("sc_up"), tasks.get("sc_dn")
    if up is None or up.start is None or d < up.start or height <= 0:
        return 0.0
    if dn is not None and dn.start and d > dn.end:
        return 0.0
    if d >= up.end:
        h = height
    else:
        h = height * cal.count(up.start, d) / max(1, cal.count(up.start, up.end))
    if dn is not None and dn.start and d >= dn.start:                 # 解体は上から（終わりの日に無くなる）
        h = height * (1 - cal.count(dn.start, d) / max(1, cal.count(dn.start, dn.end)))
        return round(max(0.0, h), 3)
    return round(min(height, max(first, h)), 3)


MILESTONES = (("kakoi", "準備（仮囲い・仮設建物・敷鉄板）"), ("yama", "山留め"), ("kodai", "構台の架設"), ("ex2", "根切り・床付け"),
              ("base", "基礎躯体"), ("frame", "地上躯体"), ("sc_up", "外部足場の組立の終わり"), ("facade", "外装"),
              ("sc_dn", "外部足場の解体"), ("kakoi_x", "片付け"))


def steps(tasks: list[Task], cal: WorkCalendar, floors: int, cycle: int, height: float, first: float,
          present: set | None = None) -> list[Step]:
    """節目ごとのステップ（日の順）. present は控えのある名前（無い控えのレイヤーは出さない）."""
    by = {t.key: t for t in tasks}
    marks = []
    prep = [by[k] for k in ("kakoi", "house", "util", "plate") if k in by and by[k].end]
    if prep:
        marks.append((max(t.end for t in prep), "準備（仮囲い・仮設建物・敷鉄板）"))
    for key, name in MILESTONES[1:]:
        t = by.get(key)
        if t is None or not t.end:
            continue
        if key == "frame":
            for k in range(1, max(1, floors) + 1):
                marks.append((cal.add(t.start, k * cycle - 1) if k < floors else t.end, f"地上躯体 {k}階"))
            continue
        marks.append((t.end, name))
    marks.sort(key=lambda m: m[0])
    groups = [g for g in GROUP_TASKS if present is None or g in present]
    out = []
    for i, (d, name) in enumerate(marks, 1):
        st = Step(i, name, d)
        for g in groups:
            lay = GROUP_TASKS[g][0]
            s = layer_state(by, g, d)
            prev = st.layers.get(lay, "なし")
            order = ("なし", "あり", "作業中")
            st.layers[lay] = max(prev, s, key=order.index)
        st.scaffold_h = scaffold_height(by, d, cal, height, first)
        out.append(st)
    return out


def present_groups(out, scaffold: bool) -> set:
    """控えのある名前（中に GUID が1つでもある JSON）と、足場があれば @足場."""
    import json
    from pathlib import Path

    have = set()
    for g in GROUP_TASKS:
        if g.startswith("@"):
            continue
        try:
            v = json.loads((Path(out) / g).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if v:
            have.add(g)
    if scaffold:
        have.add("@足場")
    return have


def to_json(st: list[Step]) -> list[dict]:
    return [{"no": x.no, "name": x.name, "date": f"{x.date:%Y-%m-%d}", "layers": x.layers, "scaffold_h": x.scaffold_h}
            for x in st]
