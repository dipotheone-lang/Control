from datetime import date

from control.calendar import WorkingCalendar


def test_friday_saturday_are_weekend():
    cal = WorkingCalendar()
    assert not cal.is_working_day(date(2026, 8, 14))  # Friday
    assert not cal.is_working_day(date(2026, 8, 15))  # Saturday
    assert cal.is_working_day(date(2026, 8, 16))      # Sunday works in Egypt


def test_deadline_shifts_over_weekend_and_holiday():
    holiday = date(2026, 8, 16)
    cal = WorkingCalendar(holidays=[holiday])
    # Friday deadline -> Saturday weekend -> Sunday holiday -> Monday
    assert cal.shift_deadline(date(2026, 8, 14)) == date(2026, 8, 17)


def test_working_days_late():
    cal = WorkingCalendar()
    due = date(2026, 8, 13)       # Thursday
    received = date(2026, 8, 16)  # Sunday
    assert cal.working_days_between(due, received) == 1
    assert cal.working_days_between(due, due) == 0


def test_add_working_days():
    cal = WorkingCalendar()
    # Thursday + 2 working days = Monday
    assert cal.add_working_days(date(2026, 8, 13), 2) == date(2026, 8, 17)


def test_holidays_staleness_flag():
    cal = WorkingCalendar()
    assert cal.holidays_stale(None, date(2026, 8, 11))
    assert cal.holidays_stale(date(2026, 6, 1), date(2026, 8, 11))
    assert not cal.holidays_stale(date(2026, 8, 1), date(2026, 8, 11))
