from datetime import date
from pathlib import Path

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


# ---- the holiday list itself — §8.3 -----------------------------------

def test_an_empty_holiday_list_is_reported_not_treated_as_no_holidays():
    """These are indistinguishable downstream, so the distinction has to
    be made in words. While it is empty, Eid is a working day."""
    from control.calendar import holiday_calendar_status

    lines = holiday_calendar_status(
        {"working_calendar": {"holidays": []}}, date(2026, 8, 16))
    assert len(lines) == 1
    assert "empty" in lines[0]
    assert "do not shift" in lines[0]
    assert "Owner: HR" in lines[0]


def test_missing_config_is_reported_the_same_way():
    from control.calendar import holiday_calendar_status

    assert holiday_calendar_status({}, date(2026, 8, 16))
    assert holiday_calendar_status(None, date(2026, 8, 16))


def test_dates_without_an_update_stamp_cannot_be_aged():
    from control.calendar import holiday_calendar_status

    lines = holiday_calendar_status(
        {"working_calendar": {"holidays": [date(2026, 4, 20)]}},
        date(2026, 8, 16))
    assert "staleness cannot be checked" in lines[0]


def test_a_stale_list_is_flagged_at_sixty_days():
    from control.calendar import holiday_calendar_status

    calendar = {"working_calendar": {
        "holidays": [date(2026, 4, 20)],
        "holidays_last_updated": "2026-06-01"}}
    assert holiday_calendar_status(calendar, date(2026, 7, 15)) == []
    stale = holiday_calendar_status(calendar, date(2026, 8, 16))
    assert "76 days ago" in stale[0]
    # Islamic dates are announced, so an old list is wrong, not just old.
    assert "announced rather than fixed" in stale[0]


def test_the_repo_config_reports_the_gap_honestly():
    import yaml

    from control.calendar import holiday_calendar_status

    path = Path(__file__).resolve().parent.parent / "config" / "sla.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    lines = holiday_calendar_status(data, date(2026, 8, 16))
    assert lines and "empty" in lines[0]
