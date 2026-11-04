"""仮設の金額の概算（利用者の指定 2026-11-04「仮設の金額を出せるようにしたい」）."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from _path import SRC  # noqa: F401

from ashiba import cost
from ashiba.schedule import schedule
from ashiba.schedule_calendar import WorkCalendar
from ashiba.schedule_plan import ScheduleConditions, build
from ashiba.schedule_sources import Quantities


def _rows(**kw):
    q = Quantities(hoarding_m=40, gates=1, house_units=6, plates=10, excavation_m3=400, backfill_m3=200, retaining=True,
                   retaining_m=36, deck_m2=144, deck_t=30, scaffold_m2=1200, scaffold_h=15, utility=True)
    c = ScheduleConditions(start=dt.date(2027, 4, 1), floors=4)
    t = build(q, c)
    schedule(t, WorkCalendar(), c.start)
    return t, q, cost.estimate(t, q, {k: v[0] for k, v in cost.DEFAULTS.items()}, **kw)


class TestUnits(unittest.TestCase):
    def test_labor_rates_and_formula(self):
        """手間＝正味の日数 × 班の編成 × 労務単価（国交省 R8.3 東京）×（1＋諸経費 47％）."""
        self.assertEqual(cost.LABOR["とび工"], 33100)
        self.assertEqual(cost.LABOR["普通作業員"], 27000)
        yen, text = cost.labor_cost("仮囲い", 25.6)               # 1班1日 25.6m → 1日、普通作業員 4人
        self.assertEqual(yen, round(4 * 27000 * 1.47))
        self.assertIn("1日×1班", text)

    def test_kusabi_by_months_and_height(self):
        self.assertEqual(cost.kusabi_unit(0.9, 10)[0], 1330)       # 東京都 幅900 12m未満 1か月未満
        self.assertEqual(cost.kusabi_unit(2.5, 10)[0], 1750)
        self.assertEqual(cost.kusabi_unit(5.0, 10)[:2], (2170, False))
        y, g, _ = cost.kusabi_unit(7.2, 10)                          # 6か月を超える分は +210／月【目安】
        self.assertEqual((y, g), (2170 + 2 * 210, True))
        y, g, _ = cost.kusabi_unit(2.5, 15)                          # 12m 以上は手間の差を足す【目安】
        self.assertEqual((y, g), (1750 + round(0.005 * 33100 * 1.47), True))
        self.assertEqual(cost.kusabi_unit(1.5, 10, 610)[0], 1350)

    def test_common_rate(self):
        """共通仮設費率（新営建築）: P＝1億円・T＝8か月で 4.05％（research_notes/仮設の金額/単価.md の計算例）."""
        self.assertEqual(cost.common_rate(100000, 8), 4.05)
        self.assertEqual(cost.common_rate(500000, 12), 3.32)
        self.assertEqual(cost.common_rate(0, 8), 0.0)


class TestEstimate(unittest.TestCase):
    def test_rows_follow_the_schedule(self):
        t, q, rows = _rows()
        by = {r.item: r for r in rows}
        sc = by["外部足場（くさび緊結式・手すり先行。材工共）"]
        tk = {k.key: k for k in t}
        m = ((tk["sc_dn"].end - tk["sc_up"].start).days + 1) / 30.0
        self.assertEqual(sc.rent, round(cost.kusabi_unit(m, 15)[0] * 1200))   # 存置は工程表の組立の始め〜解体の終わり
        self.assertEqual(sc.labor, 0)                                        # 材工共なので手間は足さない
        sheet = by["養生シート（張り・払い）"]
        self.assertIn("養生シート 賃料（掛m2・日）", sheet.missing)          # 公開値が無いものは「単価なし」
        self.assertGreater(sheet.labor, 0)
        plate = by["敷鉄板 22mm（場内通路）敷設・撤去"]
        days = (tk["plate_x"].end - tk["plate"].start).days + 1
        self.assertEqual(plate.rent, round((200 * days + 2200) * 10))
        self.assertIn("出入口ゲート W6000×H5000（材工共）", by)
        self.assertTrue(all(r.basis for r in rows))                           # どの行にも根拠

    def test_totals_do_not_double_count(self):
        _t, _q, rows = _rows()
        tt = cost.totals(rows)
        self.assertEqual(tt["仮設の合計"], tt["直接仮設"] + tt["共通仮設（積み上げ）"] + tt["共通仮設（率に含む）"])
        _t, _q, rows = _rows(direct_k=300000, work_months=12)
        tt = cost.totals(rows)
        rate = next(r for r in rows if r.group == "共通仮設費率")
        self.assertEqual(rate.total, round(300000 * 1000 * cost.common_rate(300000, 12) / 100))
        # 率を入れたら「率に含む」（仮設建物・仮設電気）は合計に足さない
        self.assertEqual(tt["仮設の合計"], tt["直接仮設"] + tt["共通仮設（積み上げ）"] + rate.total)

    def test_price_file_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            prices = cost.load_prices(p)                                    # 無ければ雛形を書く
            self.assertTrue((p / cost.PRICE_FILE).exists())
            self.assertIsNone(prices["養生シート 賃料（掛m2・日）"])
            text = (p / cost.PRICE_FILE).read_text(encoding="utf-8-sig")
            text = text.replace("養生シート 賃料（掛m2・日）,,", "養生シート 賃料（掛m2・日）,2,")
            (p / cost.PRICE_FILE).write_text(text, encoding="utf-8-sig")
            self.assertEqual(cost.load_prices(p)["養生シート 賃料（掛m2・日）"], 2.0)
        md = cost.to_markdown(_rows()[2], "試験")
        self.assertIn("**仮設の合計**", md)
        self.assertIn("単価なし", md)


class TestMonthly(unittest.TestCase):
    def test_monthly_adds_up_and_follows_the_schedule(self):
        """月ごとの金額（工程表の作業の期間へ割り振り）は合計と一致し、工程の期間の月だけに出る."""
        t, _q, rows = _rows()
        m = cost.monthly(rows, t)
        self.assertAlmostEqual(sum(m.values()), cost.totals(rows)["仮設の合計"], delta=len(m))
        s0 = min(k.start for k in t if k.start)
        s1 = max(k.end for k in t if k.end)
        self.assertEqual(min(m), f"{s0:%Y-%m}")
        self.assertEqual(max(m), f"{s1:%Y-%m}")
        tk = {k.key: k for k in t}
        sc = next(r for r in rows if r.item.startswith("外部足場"))
        months = {f"{tk['sc_up'].start:%Y-%m}", f"{tk['sc_dn'].end:%Y-%m}"}
        for k in months:                                       # 足場の存置の月には足場の賃料が入る
            self.assertGreater(m[k], 0)
        self.assertGreater(sc.rent, 0)
        md = cost.monthly_markdown(m)
        self.assertIn("| 月 | 金額 | 累計 |", md)


if __name__ == "__main__":
    unittest.main()
