"""仮設工事の工程表の作業を並べる（数量 → 日数 → つながり）. 歩掛かりは schedule_rates.RATES（出典つき）.

条件（ScheduleConditions。ashiba_out/工程表_条件.json か scripts/schedule_run.py の引数）:
- 着工日・土曜を休むか・年末年始と夏季休暇
- 躯体: 基礎躯体の日数・地上の階数・1階あたりのサイクル（稼働日）・外装の日数（足場の解体の前）【目安】の既定
- 班の数（足場・型枠・山留め・根切り）・数量の上書き（帳票に無い山留めの延長など）
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from .schedule import Dep, Task, days_of
from .schedule_rates import DECK_T, RATES, rate_text, scaffold_rate
from .schedule_sources import Quantities


@dataclass
class ScheduleConditions:
    start: _dt.date = field(default_factory=lambda: _dt.date.today())
    sat_off: bool = False
    year_end: bool = True
    summer: bool = True
    floors: int = 0                    # 地上の階数（0 は足場の高さ ÷ 3.5m【目安】）
    floor_cycle: int = 20              # 地上躯体 1階あたりの稼働日【目安】
    base_days: int = 30                # 基礎躯体（地下を含む）の稼働日【目安】
    facade_days: int = 40              # 外装（躯体が上がってから足場を外すまで）の稼働日【目安】
    crews: dict = field(default_factory=dict)        # {"足場": 2, ...}
    override: dict = field(default_factory=dict)     # 数量の上書き {"retaining_m": 60, ...}
    name: str = ""

    def crew(self, k: str, default: int = 1) -> int:
        return int(self.crews.get(k, default) or default)


def _q(c: ScheduleConditions, q: Quantities, attr: str, default=0.0):
    return c.override.get(attr, getattr(q, attr, default) if hasattr(q, attr) else default)


def build(q: Quantities, c: ScheduleConditions) -> list[Task]:
    """作業の並び（つながりの前の作業が先）."""
    T: list[Task] = []
    basis = []

    def work(key, name, group, qty, unit, rate_key, deps=(), crew_key="", machine="", min_days=1, rate=None, extra=0):
        r = rate or RATES[rate_key]
        cr = c.crew(crew_key or rate_key, r.crews)
        d = max(min_days, days_of(qty, r.per_day, cr) + extra) if qty else 0
        if d <= 0:
            return None
        t = Task(key, name, group, d, qty, unit, rate_text(r, cr), list(deps), machine=machine)
        T.append(t)
        return t

    # 準備
    hm = _q(c, q, "hoarding_m")
    work("kakoi", "仮囲い・ゲートの設置", "準備", hm, "m", "仮囲い")
    hu = _q(c, q, "house_units") + _q(c, q, "toilet_units")
    work("house", "仮設建物の設置", "準備", hu, "棟", "仮設建物", [Dep("kakoi", "SS", 2)])
    if q.utility or c.override.get("utility"):
        T.append(Task("util", "仮設電気・給排水の引込み", "準備", RATES["仮設電気"].days, 0, "", rate_text(RATES["仮設電気"]),
                      [Dep("house", "SS", 1)]))
    pl = _q(c, q, "plates")
    work("plate", "敷鉄板・場内通路", "準備", pl, "枚", "敷鉄板", [Dep("kakoi", "FS")], machine="クレーン付きトラック")
    # 山留め・土工
    ret_m = float(c.override.get("retaining_m", 0) or 0) or q.retaining_m
    prev = "plate" if any(t.key == "plate" for t in T) else "kakoi"
    if ret_m or q.retaining:
        if ret_m:
            work("yama", "山留め（親杭の建込み・横矢板）", "山留め・土工", ret_m / RATES["親杭"].pitch, "本", "親杭",
                 [Dep(prev, "FS")], machine="杭打機")
        else:
            T.append(Task("yama", "山留め（数量は条件で: retaining_m）", "山留め・土工", 10, 0, "", "延長が分からないので 10 日【目安】",
                          [Dep(prev, "FS")], machine="杭打機"))
        prev = "yama"
    ex = _q(c, q, "excavation_m3")
    deck = _q(c, q, "deck_m2")
    if ex:
        if deck:
            work("ex1", "1次根切り", "山留め・土工", ex * 0.3, "m³", "掘削", [Dep(prev, "FS")], machine="バックホウ 0.45m³")
            work("kodai", "乗入れ構台の架設", "構台", deck, "m²", "構台架設", [Dep("ex1", "FS")], machine="25t ラフター",
                 extra=days_of(_q(c, q, "deck_t"), DECK_T["構台架設"]))
            # 2次根切りは構台から掘るので、構台の架設が進んでから始め、架設の終わりより後に終える
            work("ex2", "2次根切り・床付け", "山留め・土工", ex * 0.7, "m³", "掘削", [Dep("kodai", "SS", 3), Dep("kodai", "FF", 1)],
                 machine="バックホウ 0.45m³")
            exk = "ex2"
        else:
            work("ex2", "根切り・床付け", "山留め・土工", ex, "m³", "掘削", [Dep(prev, "FS")], machine="バックホウ 0.45m³")
            exk = "ex2"
        prev = exk
    elif deck:
        work("kodai", "乗入れ構台の架設", "構台", deck, "m²", "構台架設", [Dep(prev, "FS")], machine="25t ラフター",
             extra=days_of(_q(c, q, "deck_t"), DECK_T["構台架設"]))
        prev = "kodai"
    # 躯体（参考）
    T.append(Task("base", "基礎躯体（参考）", "躯体（参考）", c.base_days, 0, "", "条件（基礎躯体の日数）【目安】", [Dep(prev, "FS")],
                  ref=True))
    bf = _q(c, q, "backfill_m3")
    if bf:
        work("fill", "埋戻し", "山留め・土工", bf, "m³", "埋戻し", [Dep("base", "FS")], machine="バックホウ 0.45m³")
    floors = c.floors or (max(1, round(q.scaffold_h / 3.5)) if q.scaffold_h else 3)
    # 揚重: タワークレーンは地上躯体の前に
    if q.tower or c.override.get("tower"):
        T.append(Task("tc_up", "タワークレーンの組立", "揚重", RATES["タワークレーン組立"].days, 0, "",
                      rate_text(RATES["タワークレーン組立"]), [Dep("base", "SS", max(0, c.base_days - RATES["タワークレーン組立"].days))],
                      machine=q.tower or str(c.override.get("tower"))))
    T.append(Task("frame", f"地上躯体 {floors}階（参考）", "躯体（参考）", floors * c.floor_cycle, 0, "",
                  f"{c.floor_cycle} 稼働日/階 × {floors} 階（条件）【目安】", [Dep("base", "FS")] +
                  ([Dep("tc_up", "FS")] if any(t.key == "tc_up" for t in T) else []), ref=True))
    if any(t.key == "kodai" for t in T):
        work("kodai_x", "乗入れ構台の撤去", "構台", deck, "m²", "構台撤去", [Dep("fill" if bf else "base", "FS")],
             machine="25t ラフター", extra=days_of(_q(c, q, "deck_t"), DECK_T["構台撤去"]))
    if ret_m or q.retaining:
        T.append(Task("yama_x", "山留めの撤去（切梁・腹起し・親杭の引抜き）", "山留め・土工",
                      max(3, days_of(ret_m / RATES["親杭"].pitch, RATES["親杭引抜"].per_day, 1)) if ret_m else 8, 0, "",
                      rate_text(RATES["親杭引抜"]), [Dep("fill" if bf else "base", "FS")], machine="杭打機"))
    # 型枠・支保工（躯体の中で）
    fm = _q(c, q, "form_m2")
    if fm:
        f = work("form", "型枠・支保工（各階）", "型枠・支保工", fm * floors, "m²", "型枠", [Dep("frame", "SS")])
        if f:
            f.deps.append(Dep("frame", "FF"))
    # 外部足場: 地上躯体を追って組み上げ、外装の後に解体
    sm = _q(c, q, "scaffold_m2")
    hgt = float(c.override.get("scaffold_h", q.scaffold_h) or 15.0)
    if sm:
        ru = scaffold_rate(hgt, True)
        a = work("sc_up", "外部足場の組立（躯体を追って）", "外部足場", sm, "掛m²", "足場組立", [Dep("frame", "SS")], rate=ru)
        if a:
            a.deps.append(Dep("frame", "FF", ru.tail))
            r = RATES["養生シート"]
            T.append(Task("sheet", "養生シート張り（組立を追って）", "外部足場", days_of(sm, r.per_day, c.crew("養生シート")), sm, "掛m²",
                          rate_text(r, c.crew("養生シート")), [Dep("sc_up", "SS", 2), Dep("sc_up", "FF", 2)]))
    T.append(Task("facade", "外装（参考）", "外装（参考）", c.facade_days, 0, "", "条件（外装の日数）【目安】", [Dep("frame", "FS")],
                  ref=True))
    if sm:
        work("sc_dn", "外部足場の解体", "外部足場", sm, "掛m²", "足場解体", [Dep("facade", "FS")], rate=scaffold_rate(hgt, False))
    if any(t.key == "tc_up" for t in T):
        T.append(Task("tc_dn", "タワークレーンの解体", "揚重", RATES["タワークレーン解体"].days, 0, "",
                      rate_text(RATES["タワークレーン解体"]), [Dep("frame", "FS")], machine="解体用の移動式クレーン"))
    # 片付け
    last = "sc_dn" if sm else "facade"
    if hu:
        work("house_x", "仮設建物の撤去", "片付け", hu, "棟", "仮設建物", [Dep(last, "FS", 5)])
    if pl:
        work("plate_x", "敷鉄板の撤去", "片付け", pl, "枚", "敷鉄板", [Dep(last, "FS")])
    if hm:
        work("kakoi_x", "仮囲いの撤去", "片付け", hm, "m", "仮囲い撤去",
             [Dep(last, "FS")] + ([Dep("house_x", "FS")] if hu else []))
    return T
