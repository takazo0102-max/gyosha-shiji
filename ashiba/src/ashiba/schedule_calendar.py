"""工程表の暦（稼働日）: 日曜・国民の祝日・年末年始・夏季休暇を休み、土曜は選べる（利用者の指定 2026-11-04 工程表）.

国民の祝日は「国民の祝日に関する法律」（昭和23年法律第178号。最終改正 平成30年）の日付の決め方:
- 日が決まっている祝日: 元日 1/1・建国記念の日 2/11・天皇誕生日 2/23・昭和の日 4/29・憲法記念日 5/3・みどりの日 5/4・
  こどもの日 5/5・山の日 8/11・文化の日 11/3・勤労感謝の日 11/23
- 月曜に置く祝日（ハッピーマンデー）: 成人の日 1月第2月曜・海の日 7月第3月曜・敬老の日 9月第3月曜・スポーツの日 10月第2月曜
- 春分の日・秋分の日は国立天文台の暦要項で前年2月に決まる。ここでは 1980〜2099 年に当てはまる近似式（日 = int(20.8431 +
  0.242194(年−1980)) − int((年−1980)/4)。秋分は 23.2488）【目安】
- 振替休日（祝日が日曜なら次の平日）・国民の休日（祝日に挟まれた平日。9月にできることがある）
建設現場の休み: 年末年始 12/29〜1/3、夏季休暇 8/13〜8/16 は一般的な慣行【目安】（条件で外せる）.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from functools import lru_cache


def _nth_monday(y: int, m: int, n: int) -> _dt.date:
    d = _dt.date(y, m, 1)
    d += _dt.timedelta(days=(7 - d.weekday()) % 7)
    return d + _dt.timedelta(weeks=n - 1)


@lru_cache(maxsize=None)
def national_holidays(y: int) -> frozenset:
    days = {_dt.date(y, m, d) for m, d in ((1, 1), (2, 11), (2, 23), (4, 29), (5, 3), (5, 4), (5, 5), (8, 11), (11, 3), (11, 23))}
    days |= {_nth_monday(y, 1, 2), _nth_monday(y, 7, 3), _nth_monday(y, 9, 3), _nth_monday(y, 10, 2)}
    k = y - 1980
    days.add(_dt.date(y, 3, int(20.8431 + 0.242194 * k) - int(k / 4)))
    days.add(_dt.date(y, 9, int(23.2488 + 0.242194 * k) - int(k / 4)))
    out = set(days)
    for d in sorted(days):                           # 振替休日
        if d.weekday() == 6:
            n = d + _dt.timedelta(days=1)
            while n in out:
                n += _dt.timedelta(days=1)
            out.add(n)
    for d in sorted(days):                           # 国民の休日（祝日に挟まれた平日）
        n = d + _dt.timedelta(days=2)
        mid = d + _dt.timedelta(days=1)
        if n in days and mid not in out and mid.weekday() != 6:
            out.add(mid)
    return frozenset(out)


@dataclass
class WorkCalendar:
    """稼働日の暦. 休み: 日曜・国民の祝日・年末年始・夏季休暇（・土曜）."""

    sat_off: bool = False
    year_end: bool = True                 # 年末年始 12/29〜1/3
    summer: bool = True                   # 夏季休暇 8/13〜8/16
    extra_off: set = field(default_factory=set)

    def is_work(self, d: _dt.date) -> bool:
        if d.weekday() == 6 or (self.sat_off and d.weekday() == 5):
            return False
        if d in national_holidays(d.year) or d in self.extra_off:
            return False
        if self.year_end and ((d.month == 12 and d.day >= 29) or (d.month == 1 and d.day <= 3)):
            return False
        if self.summer and d.month == 8 and 13 <= d.day <= 16:
            return False
        return True

    def first_work(self, d: _dt.date) -> _dt.date:
        while not self.is_work(d):
            d += _dt.timedelta(days=1)
        return d

    def add(self, d: _dt.date, n: int) -> _dt.date:
        """稼働日 d から n 稼働日すすめた日（n＜0 は戻る）. d が休みなら次の稼働日から数える."""
        d = self.first_work(d)
        step = 1 if n >= 0 else -1
        for _ in range(abs(n)):
            d += _dt.timedelta(days=step)
            while not self.is_work(d):
                d += _dt.timedelta(days=step)
        return d

    def end_of(self, start: _dt.date, days: int) -> _dt.date:
        """start から days 稼働日かかる作業の終わりの日（その日を含む）."""
        return self.add(start, max(1, days) - 1)

    def count(self, a: _dt.date, b: _dt.date) -> int:
        """a〜b（両端を含む）の稼働日の数."""
        n, d = 0, a
        while d <= b:
            n += self.is_work(d)
            d += _dt.timedelta(days=1)
        return n
