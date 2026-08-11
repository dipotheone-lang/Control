"""Working calendar — charter §8.3, §5.1.

Sunday–Thursday, Africa/Cairo (IANA zone — Egypt observes DST, never
hardcode an offset). Class 3 deadlines move to the next working day; the
callers for class 1 and 2 must NOT consult this module for suppression —
statutory and commercial alerts ignore the calendar entirely (§8.3).
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")

# Python weekday(): Monday=0 … Sunday=6. Working days Sun–Thu (§8.3).
_WEEKEND = {4, 5}  # Friday, Saturday


class WorkingCalendar:
    def __init__(self, holidays: list[date] | None = None):
        self.holidays = set(holidays or [])

    def is_working_day(self, d: date) -> bool:
        return d.weekday() not in _WEEKEND and d not in self.holidays

    def next_working_day(self, d: date) -> date:
        while not self.is_working_day(d):
            d += timedelta(days=1)
        return d

    def shift_deadline(self, d: date) -> date:
        """§8.3: deadlines falling on non-working days move forward."""
        return self.next_working_day(d)

    def add_working_days(self, d: date, n: int) -> date:
        """n working days after d (n >= 0). Day 0 is d itself if working."""
        if n < 0:
            raise ValueError("use working_days_between for past intervals")
        d = self.next_working_day(d)
        for _ in range(n):
            d = self.next_working_day(d + timedelta(days=1))
        return d

    def working_days_between(self, start: date, end: date) -> int:
        """Working days strictly after `start` up to and including `end`.

        This is the "n working days past due" number (§7.1 C1): a report
        due Thursday and received Sunday is 1 working day late.
        """
        if end <= start:
            return 0
        n, d = 0, start + timedelta(days=1)
        while d <= end:
            if self.is_working_day(d):
                n += 1
            d += timedelta(days=1)
        return n

    @staticmethod
    def now_cairo() -> datetime:
        return datetime.now(CAIRO)

    def holidays_stale(self, last_updated: date | None, today: date, limit_days: int = 60) -> bool:
        """§8.3: a holidays list stale by 60+ days is itself a flag."""
        if last_updated is None:
            return True
        return (today - last_updated).days >= limit_days
