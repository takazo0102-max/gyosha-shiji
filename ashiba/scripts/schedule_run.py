"""仮設工事の工程表（パレットの「工程表」。利用者の指定 2026-11-04「工程表作れる？」→ 仮設工事の工程表を Excel で）.

ashiba で置いた仮設の帳票（ashiba_out の仮囲い・仮設建物・敷鉄板・場内通路・根切り・構台・足場の配置・型枠・クレーン）から
数量を拾い、歩掛かり（src/ashiba/schedule_rates.py。出典つき）で日数を出して、作業のつながりで稼働日の暦に並べる。
Archicad は要らない（帳票を読むだけ）。

  python3 scripts/schedule_run.py --start 2027-04-01            # 着工日
  python3 scripts/schedule_run.py --floors 5 --cycle 18         # 地上 5 階・1 階 18 稼働日
  python3 scripts/schedule_run.py --sat-off                     # 土曜も休み（4週8休）
  python3 scripts/schedule_run.py --crew 足場組立=2 --crew 型枠=3 # 班の数
  python3 scripts/schedule_run.py --set retaining_m=60          # 帳票に無い数量（山留めの延長 m など）

条件は ashiba_out/工程表_条件.json にも書ける（引数が優先。初めて流すと雛形を書く）。出力は ashiba_out/仮設工程表.xlsx（工程表・
歩掛かりと根拠・条件の3枚）と 仮設工程表.md.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT_DIR = Path.home() / "Desktop" / "ashiba_out"
COND = "工程表_条件.json"


def _date(s: str) -> _dt.date:
    return _dt.date.fromisoformat(str(s).replace("/", "-"))


def conditions(a, saved: dict):
    from ashiba.schedule_plan import ScheduleConditions

    c = ScheduleConditions()
    for k in ("sat_off", "year_end", "summer", "floors", "floor_cycle", "base_days", "facade_days", "name"):
        if k in saved:
            setattr(c, k, saved[k])
    if saved.get("start"):
        c.start = _date(saved["start"])
    c.crews = dict(saved.get("crews") or {})
    c.override = dict(saved.get("override") or {})
    if a.start:
        c.start = _date(a.start)
    if a.floors:
        c.floors = a.floors
    if a.cycle:
        c.floor_cycle = a.cycle
    if a.base_days:
        c.base_days = a.base_days
    if a.facade_days:
        c.facade_days = a.facade_days
    if a.sat_off:
        c.sat_off = True
    if a.name:
        c.name = a.name
    for s in a.crew or ():
        k, _, v = s.partition("=")
        c.crews[k.strip()] = int(v)
    for s in a.set or ():
        k, _, v = s.partition("=")
        try:
            c.override[k.strip()] = float(v)
        except ValueError:
            c.override[k.strip()] = v.strip()
    return c


def main(argv=None) -> int:
    import argparse

    from ashiba.schedule import schedule, span, to_markdown, to_xlsx
    from ashiba.schedule_calendar import WorkCalendar
    from ashiba.schedule_plan import build
    from ashiba.schedule_sources import collect

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", help="着工日（2027-04-01）")
    ap.add_argument("--floors", type=int, default=0, help="地上の階数（省くと足場の高さ ÷ 3.5m）")
    ap.add_argument("--cycle", type=int, default=0, help="地上躯体 1 階あたりの稼働日（既定 20【目安】）")
    ap.add_argument("--base-days", type=int, default=0, help="基礎躯体の稼働日（既定 30【目安】）")
    ap.add_argument("--facade-days", type=int, default=0, help="外装の稼働日（躯体の後、足場を外すまで。既定 40【目安】）")
    ap.add_argument("--sat-off", action="store_true", help="土曜も休み")
    ap.add_argument("--crew", action="append", help="班の数 作業=数（足場組立・足場解体・型枠・掘削・仮囲い…）")
    ap.add_argument("--set", action="append", help="数量の上書き 名前=値（retaining_m・scaffold_m2・excavation_m3…）")
    ap.add_argument("--name", default="", help="工事名（表題）")
    ap.add_argument("--out", default=str(OUT_DIR), help="帳票のフォルダ")
    a = ap.parse_args(argv)
    out = Path(a.out)
    cpath = out / COND
    try:
        saved = json.loads(cpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    c = conditions(a, saved)
    q = collect(out, c.name or _project_name())
    tasks = build(q, c)
    cal = WorkCalendar(sat_off=c.sat_off, year_end=c.year_end, summer=c.summer)
    schedule(tasks, cal, c.start)
    s0, s1 = span(tasks)
    title = f"仮設工事工程表　{c.name}".rstrip()
    notes = [f"着工 {c.start:%Y-%m-%d}", f"仮設の終わり {s1:%Y-%m-%d}",
             "休み: 日曜・国民の祝日" + ("・土曜" if c.sat_off else "") + ("・年末年始" if c.year_end else "") + ("・夏季" if c.summer else ""),
             "躯体・外装は参考（灰）。日数は数量 ÷ 歩掛かり（根拠は2枚め）。【目安】は出典で確かめていない値"]
    basis = [[t.name, round(t.qty, 1) if t.qty else "", t.unit, t.days, t.rate, q.sources.get(_src_key(t.key), "")] for t in tasks]
    conds = [("着工日", f"{c.start:%Y-%m-%d}"), ("地上の階数", str(c.floors or "足場の高さから")),
             ("地上躯体のサイクル", f"{c.floor_cycle} 稼働日/階【目安】"), ("基礎躯体", f"{c.base_days} 稼働日【目安】"),
             ("外装", f"{c.facade_days} 稼働日【目安】"), ("班の数", json.dumps(c.crews, ensure_ascii=False) or "既定"),
             ("数量の上書き", json.dumps(c.override, ensure_ascii=False)),
             ("拾った帳票", "・".join(f"{k}={v}" for k, v in q.sources.items()))]
    from ashiba.schedule_steps import present_groups, steps as make_steps, to_json

    lv = []
    try:
        pj = sorted(out.glob("*_plan.json"), key=lambda p: p.stat().st_mtime)[-1]
        lv = (json.loads(pj.read_text(encoding="utf-8")).get("elevation") or {}).get("level_heights") or []
    except (IndexError, OSError, ValueError):
        pass
    has_frame = any(t.key == "frame" for t in tasks)
    nfl = c.floors or (max(1, round(q.scaffold_h / 3.5)) if q.scaffold_h else 3)
    st = make_steps(tasks, cal, nfl, c.floor_cycle, q.scaffold_h, (lv[0] / 1000.0) if lv else 1.8,
                    present_groups(out, q.scaffold_m2 > 0)) if has_frame else []
    out.mkdir(parents=True, exist_ok=True)
    xl = out / "仮設工程表.xlsx"
    to_xlsx(tasks, cal, xl, title, notes, basis, conds, st)
    (out / "工程ステップ.json").write_text(json.dumps({"title": title, "steps": to_json(st)}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    (out / "仮設工程表.md").write_text(to_markdown(tasks, title, notes), encoding="utf-8")
    if not cpath.exists():
        cpath.write_text(json.dumps({"start": f"{c.start:%Y-%m-%d}", "sat_off": c.sat_off, "floors": c.floors,
                                     "floor_cycle": c.floor_cycle, "base_days": c.base_days, "facade_days": c.facade_days,
                                     "crews": c.crews, "override": c.override, "name": c.name}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"仮設工程表: {len(tasks)} 作業・{s0:%Y-%m-%d}〜{s1:%Y-%m-%d}・施工ステップ {len(st)}（{xl}）")
    return 0


def _project_name() -> str:
    """足場の条件ファイル（ASHIBA_SPEC か ~/Desktop/ashiba_spec.json）の工事名。無ければ既定の「足場計画」."""
    import os

    p = Path(os.environ.get("ASHIBA_SPEC") or Path.home() / "Desktop" / "ashiba_spec.json")
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("project_name") or "足場計画")
    except (OSError, ValueError, AttributeError):
        return "足場計画"


def _src_key(key: str) -> str:
    return {"kakoi": "仮囲い", "kakoi_x": "仮囲い", "house": "仮設建物", "house_x": "仮設建物", "plate": "敷鉄板", "plate_x": "敷鉄板",
            "ex1": "根切り", "ex2": "根切り", "fill": "根切り", "kodai": "構台", "kodai_x": "構台", "sc_up": "外部足場",
            "sc_dn": "外部足場", "form": "型枠"}.get(key, "")


if __name__ == "__main__":
    sys.exit(main())
