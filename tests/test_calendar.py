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


# ---- quarterly (added 30-Aug-2026) ------------------------------------
#
# Found while trying to answer STAT-PDPL-REGS's open question. The
# register had no way to express a quarterly deadline, and the way that
# looked correct was silently wrong.

def test_a_named_date_with_a_quarterly_cadence_steps_by_three_months():
    """"1 October, quarterly" means 1 Jan, 1 Apr, 1 Jul, 1 Oct. The
    anchor names one of the four; the other three follow from it."""
    from control.loader import parse_due

    def due_on(today):
        due, problem = parse_due("1 October", "quarterly", today)
        assert due is not None, problem
        return due.date()

    assert due_on(date(2026, 8, 30)) == date(2026, 10, 1)
    assert due_on(date(2026, 10, 1)) == date(2026, 10, 1)   # today counts
    assert due_on(date(2026, 10, 2)) == date(2027, 1, 1)    # rolls the year
    assert due_on(date(2027, 3, 1)) == date(2027, 4, 1)


def test_a_bare_day_of_month_is_refused_for_a_quarterly_cadence():
    """It used to be accepted and then computed by MONTH, so a quarterly
    rule fired twelve times a year while looking like a working
    countdown. Nothing in the live register exercised it; the payroll
    quarters would have been the first (§1.1)."""
    from control.loader import parse_due

    due, problem = parse_due("day 1", "quarterly", date(2026, 8, 30))
    assert due is None
    assert "never which month" in problem
    assert "'1 October'" in problem, "the message must name the working form"


def test_a_bare_day_of_month_is_refused_for_an_annual_cadence():
    from control.loader import parse_due

    due, problem = parse_due("day 1", "annual", date(2026, 8, 30))
    assert due is None
    assert "never which month" in problem


def test_the_monthly_shapes_are_untouched():
    from control.loader import parse_due

    assert parse_due("day 20", "monthly", date(2026, 8, 30))[0].date() \
        == date(2026, 9, 20)
    assert parse_due("31 March", "annual", date(2026, 8, 30))[0].date() \
        == date(2027, 3, 31)


def test_a_quarterly_anchor_past_day_28_is_refused():
    """A quarterly cycle lands in months of different lengths, and a
    skipped quarter is a missed class 1 deadline."""
    from control.loader import parse_due

    due, problem = parse_due("31 October", "quarterly", date(2026, 8, 30))
    assert due is None
    assert "day 1..28" in problem
