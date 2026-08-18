"""Config to engine — the bridge Phase 1 runs on.

`run_cycle` was tested from hand-built objects, so nothing could
actually run a cycle from configuration. This module builds the specs,
roster, calendar and tracked items from `config/*.yaml`.

Most of these tests are about refusals, because that is where the
charter lives. An unapproved obligation is a Stage D proposal and must
not be tracked (§6). An unparseable due expression must not become a
date — a wrong deadline alerts confidently on the wrong day, which is
worse than no deadline at all. And config is never executed: C6 rules
come from a fixed vocabulary, so a config file cannot decide what code
runs (§13.2).
"""

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from control.db import init_db
from control.loader import (
    build_calendar, build_class3_state, build_obligations, build_roster,
    build_statutory, load_for_cycle, parse_due,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
SUNDAY = date(2026, 8, 16)          # a working day in Egypt


def approved(**over):
    row = {
        "id": "OPS-WPR-001", "class": 3, "name": "Weekly progress report",
        "owner": "a.elsayed@ubcsis.com", "form": "FRM-WPR-01 rev 3",
        "cadence": "weekly", "due": "sunday 10:00",
        "approved_by_ceo": "ahmed@ubcsis.com",
    }
    row.update(over)
    return {"obligations": [row]}


PEOPLE = {"people": [
    {"email": "a.elsayed@ubcsis.com", "name": "Ahmed Elsayed",
     "reports_to": "ghareeb@ubcsis.com", "tier": 2},
    {"email": "hadeer@ubcsis.com", "name": "Hadeer Mohamed",
     "reports_to": "accounts@ubcsis.com", "tier": 1,
     "also_reports_to": "hr@ubcsis.com", "also_reports_to_domain": "hr"},
]}


# ---- the refusal that ends Phase 0 -----------------------------------

def test_an_unapproved_obligation_is_not_tracked():
    """§6: CEO approval of the register is what ends Phase 0. Acting on
    a Stage D proposal is acting on an inference."""
    specs, tracked, gaps = build_obligations(
        approved(approved_by_ceo=None), PEOPLE, SUNDAY)
    assert specs == {} and tracked == []
    assert any("not approved by the CEO" in g for g in gaps)
    assert any("Stage D proposal" in g for g in gaps)


def test_an_approved_obligation_is_tracked():
    specs, tracked, gaps = build_obligations(approved(), PEOPLE, SUNDAY)
    assert list(specs) == ["OPS-WPR-001"]
    assert specs["OPS-WPR-001"].spec.form_code == "FRM-WPR-01"
    assert specs["OPS-WPR-001"].spec.current_revision == "3"
    assert specs["OPS-WPR-001"].surname == "Elsayed"
    assert tracked[0].owner == "a.elsayed@ubcsis.com"
    assert tracked[0].due == SUNDAY


def test_an_empty_register_says_so_rather_than_looking_clear():
    _, _, gaps = build_obligations({"obligations": []}, PEOPLE, SUNDAY)
    assert any("empty register, not a clear week" in g for g in gaps)


# ---- due dates are computed or refused, never guessed ----------------

@pytest.mark.parametrize("expression,cadence,expected", [
    ("sunday 10:00", "weekly", datetime(2026, 8, 16, 10, 0)),
    ("thursday 14:30", "weekly", datetime(2026, 8, 20, 14, 30)),
    ("day 5 09:00", "monthly", datetime(2026, 9, 5, 9, 0)),
    ("2026-12-31 12:00", "", datetime(2026, 12, 31, 12, 0)),
])
def test_understood_expressions_produce_dates(expression, cadence, expected):
    due, problem = parse_due(expression, cadence, SUNDAY)
    assert due == expected and problem == ""


@pytest.mark.parametrize("expression,cadence", [
    ("end of month", "monthly"),
    ("when the site closes", "weekly"),
    ("", "weekly"),
    ("day 31 09:00", "monthly"),          # not every month has one
    ("sunday 10:00", "monthly"),          # weekday with a monthly cadence
])
def test_unclear_expressions_produce_a_gap_not_a_date(expression, cadence):
    due, problem = parse_due(expression, cadence, SUNDAY)
    assert due is None and problem


def test_a_missing_time_defaults_to_end_of_day_not_midnight():
    due, _ = parse_due("sunday", "weekly", SUNDAY)
    assert due.time() == datetime(2026, 1, 1, 17, 0).time()


def test_an_obligation_with_no_computable_deadline_alerts_on_nothing():
    specs, tracked, gaps = build_obligations(
        approved(due="whenever the report is ready"), PEOPLE, SUNDAY)
    assert specs == {} and tracked == []
    assert any("nothing is alerted for it" in g for g in gaps)


def test_periods_follow_the_cadence():
    weekly, _, _ = build_obligations(approved(), PEOPLE, SUNDAY)
    assert weekly["OPS-WPR-001"].period == "2026-W33"
    monthly, _, _ = build_obligations(
        approved(cadence="monthly", due="day 5 09:00"), PEOPLE, SUNDAY)
    assert monthly["OPS-WPR-001"].period == "2026-09"


# ---- form control -----------------------------------------------------

def test_a_form_without_a_revision_is_reported():
    _, _, gaps = build_obligations(approved(form="FRM-WPR-01"), PEOPLE, SUNDAY)
    assert any("cannot detect a superseded revision" in g for g in gaps)


def test_no_form_at_all_is_reported():
    _, _, gaps = build_obligations(approved(form=""), PEOPLE, SUNDAY)
    assert any("C2 form control cannot be checked" in g for g in gaps)


# ---- C6: compiled, never executed ------------------------------------

def test_a_declared_rule_compiles_and_runs():
    specs, _, gaps = build_obligations(approved(manual_rules=[{
        "check": "field_present", "field": "B12",
        "clause": "4.2.1", "requirement": "Man-hours must be stated"}]),
        PEOPLE, SUNDAY)
    rule = specs["OPS-WPR-001"].spec.manual_rules[0]
    assert rule.clause == "4.2.1"
    assert rule.predicate({"B12": 120}) is True
    assert rule.predicate({"B12": ""}) is False
    assert rule.predicate({}) is False


def test_numeric_rules_compare_rather_than_guess():
    specs, _, _ = build_obligations(approved(manual_rules=[{
        "check": "field_at_least", "field": "B12", "value": 100,
        "clause": "4.2", "requirement": "at least 100"}]), PEOPLE, SUNDAY)
    predicate = specs["OPS-WPR-001"].spec.manual_rules[0].predicate
    assert predicate({"B12": 150}) is True
    assert predicate({"B12": 50}) is False
    assert predicate({"B12": "not a number"}) is False


def test_an_unknown_check_is_a_gap_not_an_improvisation():
    """Config is data, never code. A check this module does not know
    must not become one it invents (§13.2)."""
    specs, _, gaps = build_obligations(approved(manual_rules=[{
        "check": "python_expression", "field": "B12",
        "clause": "4.2", "requirement": "anything"}]), PEOPLE, SUNDAY)
    assert specs["OPS-WPR-001"].spec.manual_rules == []
    assert any("is not one of" in g for g in gaps)


def test_a_rule_without_its_clause_is_refused():
    """§1.2: a C6 finding must quote the clause. No clause, no rule."""
    _, _, gaps = build_obligations(approved(manual_rules=[{
        "check": "field_present", "field": "B12"}]), PEOPLE, SUNDAY)
    assert any("requires the clause quoted" in g for g in gaps)


def test_a_governing_clause_with_no_checkable_rule_says_c6_is_not_assessed():
    _, _, gaps = build_obligations(
        approved(governing_clause="QMS Manual, clause 4.2"), PEOPLE, SUNDAY)
    assert any("NOT ASSESSED rather than CONFORMS" in g for g in gaps)


# ---- class 1: the loudest gap in the system --------------------------

def test_partial_statutory_coverage_never_reads_as_coverage():
    """This test used to assert the register tracked nothing at all.

    The execution order of 18-Aug-2026 supplied dates for four of the
    twelve, so "tracking nothing" is no longer true — but the thing the
    test guarded is: the loudest fact must still be the share that is
    dark, because a register that shows four alerts and eight technical
    lines reads as coverage to anyone skimming it.
    """
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    tracked, gaps = build_statutory(data, SUNDAY)
    assert tracked, "four CEO-stated dates should now alert"
    assert any("highest-priority gap in the system" in g for g in gaps)
    assert any("only class carrying fines" in g for g in gaps)
    # The header states it as a share, so it cannot be skimmed past.
    assert any(f"{len(tracked)} of {len(data['obligations'])}" in g
               for g in gaps)
    # Every silent obligation names itself somewhere — either here, or
    # in the event register, which owns the reporting for its two.
    silent = {r["id"] for r in data["obligations"]} - {t.item_id for t in tracked}
    event_driven = {r["id"] for r in data["obligations"]
                    if r.get("mechanism") == "event_window"}
    joined = " ".join(gaps)
    for obligation_id in silent - event_driven:
        assert obligation_id in joined, obligation_id


def test_the_four_kinds_of_silence_are_counted_apart():
    """All four are "no countdown"; the remedies are four different
    people. A missing date is chased from the advisor or from HR, an
    event window waits for an event, an exception-detected obligation
    waits for a detector to be built, and a registration nobody can
    perform waits for regulations. One merged count would send the CEO
    to the wrong one.
    """
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    _, gaps = build_statutory(data, SUNDAY)
    coverage = next(g for g in gaps if "have a usable date" in g)
    for phrase in ("awaiting a date", "event-driven",
                   "monitored by exception", "no mechanism exists"):
        assert phrase in coverage


def test_a_real_time_obligation_is_not_reported_as_a_missing_date():
    """B2. ETA submission has no deadline by design. Listing it beside
    the rules Hadeer still owes would send someone to ask her for a date
    that does not exist — and would hide the real gap, which is that the
    detector is not built."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    _, gaps = build_statutory(data, SUNDAY)
    line = next(g for g in gaps if g.startswith("STAT-ETA-SUB"))
    assert "no deadline by design (B2)" in line
    assert "that detector is not built" in line
    assert "O-03" not in line


def test_an_obligation_with_no_way_to_discharge_it_says_exactly_that():
    """B7. Recording it as absent would be false; recording it as met
    would be worse. It is owed, and the mechanism does not exist."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    _, gaps = build_statutory(data, SUNDAY)
    line = next(g for g in gaps if g.startswith("STAT-PDPL-REG:"))
    assert "no known way to discharge it yet" in line
    assert "rather than as absent or as met" in line
    assert "D-40" in line


def test_the_event_windows_are_left_to_the_event_register():
    """Two modules reporting the same obligation would say "no alert can
    fire" about one that is working as designed."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    _, gaps = build_statutory(data, SUNDAY)
    per_row = [g for g in gaps if not g.startswith("statutory-calendar.yaml")]
    assert not [g for g in per_row
                if g.startswith(("STAT-ETA-REJ", "STAT-SI-HEADCOUNT"))]
    # But they are still counted in the coverage share.
    coverage = next(g for g in gaps if "have a usable date" in g)
    assert "2 event-driven" in coverage


def test_a_verified_statutory_rule_with_a_date_is_tracked():
    tracked, _ = build_statutory({
        "verified_by_advisor": True,
        "obligations": [{"id": "STAT-VAT", "name": "VAT",
                         "rule": "2026-09-10 17:00",
                         "owner": "accounts@ubcsis.com"}]}, SUNDAY)
    assert len(tracked) == 1
    assert tracked[0].obligation_class == 1
    assert tracked[0].due == date(2026, 9, 10)


# ---- roster and calendar ---------------------------------------------

def test_the_roster_carries_the_dotted_line():
    roster = build_roster(PEOPLE)
    hadeer = roster["hadeer@ubcsis.com"]
    assert hadeer.manager_for(None) == "accounts@ubcsis.com"
    assert hadeer.manager_for("hr") == "hr@ubcsis.com"


def test_an_empty_holiday_list_is_a_reported_gap():
    calendar, gaps = build_calendar(
        yaml.safe_load((REPO_CONFIG / "sla.yaml").read_text(encoding="utf-8")))
    assert calendar.holidays == set()
    assert any("no public holidays on file" in g for g in gaps)


def test_a_malformed_holiday_is_reported_not_silently_dropped():
    _, gaps = build_calendar({"working_calendar": {"holidays": ["eid"]}})
    assert any("is not a date" in g for g in gaps)


# ---- state from the database -----------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def test_a_registered_absence_routes_to_the_delegate(conn):
    _, tracked, _ = build_obligations(approved(), PEOPLE, SUNDAY)
    conn.execute("INSERT INTO absence (email, from_date, to_date, delegate,"
                 " registered_by) VALUES (?, ?, ?, ?, ?)",
                 ("a.elsayed@ubcsis.com", "2026-08-10", "2026-08-25",
                  "shymaa@ubcsis.com", "hr@ubcsis.com"))
    conn.commit()
    state = build_class3_state(conn, tracked, SUNDAY)
    assert state["OPS-WPR-001"].absence.delegate == "shymaa@ubcsis.com"


def test_an_unregistered_delegate_is_absence_without_a_delegate(conn):
    """§3.3: the finding is 'delegation not registered' — a process
    finding, not a finding about the absent person."""
    _, tracked, _ = build_obligations(approved(), PEOPLE, SUNDAY)
    conn.execute("INSERT INTO absence (email, from_date, to_date, delegate,"
                 " registered_by) VALUES (?, ?, ?, NULL, ?)",
                 ("a.elsayed@ubcsis.com", "2026-08-10", "2026-08-25",
                  "hr@ubcsis.com"))
    conn.commit()
    state = build_class3_state(conn, tracked, SUNDAY)
    assert state["OPS-WPR-001"].absence is not None
    assert state["OPS-WPR-001"].absence.delegate is None


def test_a_pending_dispute_suspends_the_item(conn):
    from control.db import insert_submission

    _, tracked, _ = build_obligations(approved(), PEOPLE, SUNDAY)
    submission_id = insert_submission(conn, {
        "obligation_id": "OPS-WPR-001", "verdict": "RETURNED_FOR_REVISION",
        "source": "LIVE", "submitted_by": "a.elsayed@ubcsis.com",
        "period": "2026-W33", "submitted_at": "2026-08-16 09:00",
        "source_email_id": "<m1>"})
    conn.execute("INSERT INTO disputes (submission_id, raised_by, raised_at,"
                 " state, source) VALUES (?, ?, ?, 'PENDING', 'LIVE')",
                 (submission_id, "a.elsayed@ubcsis.com", "2026-08-16"))
    conn.commit()
    state = build_class3_state(conn, tracked, SUNDAY)
    assert state["OPS-WPR-001"].dispute_active is True


def test_an_accepted_submission_stops_the_ladder(conn):
    from control.db import insert_submission

    specs, tracked, _ = build_obligations(approved(), PEOPLE, SUNDAY)
    insert_submission(conn, {
        "obligation_id": "OPS-WPR-001", "verdict": "ACCEPTED", "source": "LIVE",
        "submitted_by": "a.elsayed@ubcsis.com", "period": "2026-W33",
        "submitted_at": "2026-08-16 09:00", "source_email_id": "<m1>"})
    conn.commit()
    state = build_class3_state(conn, tracked, SUNDAY,
                               {"OPS-WPR-001": specs["OPS-WPR-001"].period})
    assert state["OPS-WPR-001"].submitted is True


def test_a_submission_for_another_period_does_not_count(conn):
    from control.db import insert_submission

    specs, tracked, _ = build_obligations(approved(), PEOPLE, SUNDAY)
    insert_submission(conn, {
        "obligation_id": "OPS-WPR-001", "verdict": "ACCEPTED", "source": "LIVE",
        "submitted_by": "a.elsayed@ubcsis.com", "period": "2026-W20",
        "submitted_at": "2026-05-16 09:00", "source_email_id": "<m0>"})
    conn.commit()
    state = build_class3_state(conn, tracked, SUNDAY,
                               {"OPS-WPR-001": specs["OPS-WPR-001"].period})
    assert state["OPS-WPR-001"].submitted is False


# ---- the whole load against the real repository config ---------------

def test_the_repo_config_loads_and_reports_exactly_what_is_missing(conn):
    from control.config import load_config

    config = load_config(REPO_CONFIG)
    result = load_for_cycle(config, conn, SUNDAY)

    # Class 3 tracks nothing, class 1 tracks only what the CEO stated,
    # and every reason is named.
    assert result.approved == 0
    assert {t.item_id for t in result.tracked} == {
        "STAT-VAT", "STAT-WHT", "STAT-SOCINS", "STAT-CIT"}
    text = " ".join(result.gaps)
    assert "obligations.yaml is empty" in text
    assert "not advisor-verified" in text
    assert "no public holidays on file" in text

    # The roster is live even though the register is not.
    assert len(result.roster) >= 11


# ---- statutory shapes from the execution order of 18-Aug-2026 --------

def test_an_event_window_is_never_read_as_a_day_of_month():
    """The defect this guards actually happened.

    "7 days from rejection" is the ETA clearance window — the tightest
    statutory window in the system, whose clock starts when ETA rejects
    an invoice. The day-of-month branch matched its leading "7" and
    produced day 7 of the month: a confidently wrong statutory date,
    which §2.1 rates worse than no date at all.
    """
    from control.loader import parse_due

    for text in ("7 days from rejection", "30 days from event",
                 "5 working days after notification",
                 "14 calendar days from the award"):
        due, problem = parse_due(text, "", date(2026, 8, 18))
        assert due is None, f"{text!r} became a calendar date"
        assert "event-driven window" in problem


def test_month_end_is_expressible_because_it_is_a_real_statutory_shape():
    """Several Egyptian filings land on month-end, and month-end cannot
    be written as a day-of-month: the day it falls on changes."""
    from control.loader import parse_due

    due, problem = parse_due("end of the following month", "",
                             date(2026, 8, 18))
    assert problem == ""
    assert due.date() == date(2026, 9, 30)

    # February, and a leap year, without a special case.
    due, _ = parse_due("end of the following month", "", date(2028, 1, 5))
    assert due.date() == date(2028, 2, 29)


def test_the_operative_lead_moves_earlier_without_moving_the_statutory_date():
    """VAT's operative date is five working days before the statutory
    one. The statutory date stays the anchor; the lead is when Control
    acts, not when the law falls due."""
    from control.loader import parse_due

    statutory, _ = parse_due("end of the following month", "",
                             date(2026, 8, 18))
    operative, _ = parse_due("end of the following month, -5 working days",
                             "", date(2026, 8, 18))
    assert statutory.date() == date(2026, 9, 30)
    # Sunday-Thursday week (§8.3): back over 29, 28, 27, 24, 23.
    assert operative.date() == date(2026, 9, 23)
    assert operative < statutory


def test_a_fixed_calendar_date_is_unambiguous_where_a_day_number_is_not():
    """31 March is a real date; "day 31" monthly is not."""
    from control.loader import parse_due

    for text in ("31 March", "March 31"):
        due, problem = parse_due(text, "", date(2026, 8, 18))
        assert problem == ""
        assert due.date() == date(2027, 3, 31), text

    # ...and the bare day number is still refused.
    due, problem = parse_due("day 31", "", date(2026, 8, 18))
    assert due is None
    assert "1..28" in problem


def test_a_date_that_does_not_exist_is_refused_not_clamped():
    from control.loader import parse_due

    due, problem = parse_due("31 February", "", date(2026, 8, 18))
    assert due is None
    assert "not a real date" in problem


def test_an_undated_rule_still_produces_no_date():
    """§2.1: unverified rules alert early, but only where a date exists.
    'dates pending' is not a date."""
    from control.loader import parse_due

    for text in ("annual — dates pending", "real-time",
                 "UNVERIFIED — CONFIRM WITH ADVISOR"):
        due, problem = parse_due(text, "", date(2026, 8, 18))
        assert due is None, text
        assert problem


def test_the_provenance_line_distinguishes_nothing_from_unverified():
    """"Tracking nothing" and "tracking four dates nobody qualified has
    checked" are different states with different remedies. One message
    for both would be false in whichever case it did not fit."""
    from control.loader import build_statutory

    today = date(2026, 8, 18)
    stated = {
        "verified_by_advisor": False, "ceo_stated": True,
        "source": "Execution order 18-Aug-2026 §2.3",
        "obligations": [{"id": "STAT-X", "name": "X", "rule": "day 15"}],
    }
    tracked, gaps = build_statutory(stated, today)
    assert len(tracked) == 1
    line = gaps[-1]
    assert "CEO-STATED" in line
    assert "time passing does not confirm them" in line
    assert "tracking nothing" not in line

    empty = dict(stated, obligations=[
        {"id": "STAT-Y", "name": "Y", "rule": "UNVERIFIED — pending"}])
    _, gaps = build_statutory(empty, today)
    assert "tracking nothing" in gaps[-1]

    bare = {"verified_by_advisor": False,
            "obligations": [{"id": "STAT-Z", "name": "Z", "rule": "day 15"}]}
    _, gaps = build_statutory(bare, today)
    assert "no recorded provenance" in gaps[-1]


def test_the_shipped_calendar_alerts_on_the_recurring_obligations():
    """What the execution order's step 1 actually buys, asserted rather
    than assumed: the four with known dates alert; the rest stay visible
    gaps naming what each needs."""
    import pathlib

    import yaml

    from control.loader import build_statutory

    config = yaml.safe_load(
        (pathlib.Path(__file__).resolve().parent.parent
         / "config" / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    tracked, gaps = build_statutory(config, date(2026, 8, 18))

    assert {t.item_id for t in tracked} == {
        "STAT-VAT", "STAT-WHT", "STAT-SOCINS", "STAT-CIT"}

    # VAT alerts on its operative date, five working days early.
    vat = next(t for t in tracked if t.item_id == "STAT-VAT")
    assert vat.due == date(2026, 9, 23)

    # The event windows produce no invented date and no line here —
    # they are counted in the coverage share and reported by the event
    # register, which knows whether any events are on record.
    joined = " ".join(gaps)
    assert "2 event-driven" in joined
    assert not [g for g in gaps if g.startswith("STAT-ETA-REJ")]
