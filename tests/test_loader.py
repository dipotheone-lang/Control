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

def test_unverified_statutory_rules_track_nothing_and_say_so():
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    tracked, gaps = build_statutory(data, SUNDAY)
    assert tracked == []
    assert any("highest-priority gap in the system" in g for g in gaps)
    assert any("only class carrying fines" in g for g in gaps)
    # Every obligation reports its own silence, not just the header.
    assert len([g for g in gaps if "no class 1 alert" in g]) == 9


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

    # Nothing is tracked, and every reason is named.
    assert result.approved == 0
    assert result.tracked == []
    text = " ".join(result.gaps)
    assert "obligations.yaml is empty" in text
    assert "verified_by_advisor is false" in text
    assert "no public holidays on file" in text

    # The roster is live even though the register is not.
    assert len(result.roster) >= 11
