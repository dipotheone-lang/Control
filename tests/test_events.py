"""Event-driven statutory windows — §2.1, execution order B1 and B4.

Two class 1 obligations have no cadence: ETA rejection clearance (7
days from a rejection) and the social insurance headcount declaration
(30 days from a joiner or leaver). `parse_due` refuses both on purpose,
so until this register existed they were configured, correct, and
completely untracked.

The tests here are mostly about what the register refuses to smooth
over. A window computed from the registration date instead of the event
date would report a comfortable thirty days that does not exist. An
empty register would read as nothing overdue. Both are the same failure
— a reassuring number where a gap belongs.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control.db import init_db
from control.events import (
    build_event_items, discharge_event, open_events, record_event,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
TODAY = date(2026, 8, 18)

CONFIG = {"obligations": [
    {"id": "STAT-ETA-REJ", "name": "ETA rejection clearance",
     "owner": "accounts@ubcsis.com", "mechanism": "event_window",
     "window_days": 7, "check_frequency": "daily", "manual_detection": True,
     "manual_detection_reason": "Rejections arrive in accounts@, outside M1 scope."},
    {"id": "STAT-SI-HEADCOUNT", "name": "SI headcount declaration",
     "owner": "accounts@ubcsis.com", "mechanism": "event_window",
     "window_days": 30, "hr_registration_target_working_days": 5},
    {"id": "STAT-VAT", "name": "VAT", "owner": "accounts@ubcsis.com",
     "rule": "end of the following month"},
]}


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


# ---- the clock starts at the event ------------------------------------

def test_the_deadline_counts_from_the_event_not_the_registration(conn):
    """B4. The whole point: registering late does not buy back time."""
    record_event(conn, "STAT-SI-HEADCOUNT", "JOINER", date(2026, 8, 1),
                 "EMP-204", "MANUAL", "hr@ubcsis.com",
                 registered_at=date(2026, 8, 12))
    tracked, _ = build_event_items(conn, CONFIG, TODAY)
    assert len(tracked) == 1
    # 1-Aug + 30 days, not 12-Aug + 30 days.
    assert tracked[0].due == date(2026, 8, 31)
    assert tracked[0].obligation_class == 1


def test_the_consumed_share_of_the_window_is_reported(conn):
    """The erosion B4 exists to keep visible. Eleven of thirty days were
    gone before Control could count any of them."""
    record_event(conn, "STAT-SI-HEADCOUNT", "JOINER", date(2026, 8, 1),
                 "EMP-204", "MANUAL", "hr@ubcsis.com",
                 registered_at=date(2026, 8, 12))
    _, gaps = build_event_items(conn, CONFIG, TODAY)
    erosion = next(g for g in gaps if "already spent" in g)
    assert "registered 11 day(s) after it happened" in erosion
    assert "11 of the 30 days were already spent" in erosion
    assert "13 day(s) remain" in erosion


def test_late_registration_is_a_process_finding_not_a_personal_one(conn):
    """§1.4 and §1.6. The target was missed; the sentence says so about
    the process and names no conduct."""
    record_event(conn, "STAT-SI-HEADCOUNT", "LEAVER", date(2026, 8, 1),
                 "EMP-101", "MANUAL", "hr@ubcsis.com",
                 registered_at=date(2026, 8, 12))
    _, gaps = build_event_items(conn, CONFIG, TODAY)
    erosion = next(g for g in gaps if "already spent" in g)
    assert "process finding, not a finding about the sender" in erosion
    for word in ("failure", "negligence", "breach", "late submission by"):
        assert word not in erosion


def test_registration_on_the_day_reports_no_erosion(conn):
    record_event(conn, "STAT-SI-HEADCOUNT", "JOINER", date(2026, 8, 12),
                 None, "MANUAL", "hr@ubcsis.com",
                 registered_at=date(2026, 8, 12))
    _, gaps = build_event_items(conn, CONFIG, TODAY)
    assert not [g for g in gaps if "already spent" in g]


# ---- silence is never mistaken for compliance -------------------------

def test_an_empty_register_says_so_rather_than_reading_as_clear(conn):
    """Nothing is overdue because nothing is recorded. That is not the
    same as nothing having happened (§1.1)."""
    _, gaps = build_event_items(conn, CONFIG, TODAY)
    for obligation in ("STAT-ETA-REJ", "STAT-SI-HEADCOUNT"):
        line = next(g for g in gaps if g.startswith(obligation))
        assert "no events on record" in line
        assert "not that none occurred" in line


def test_the_manual_detection_cost_is_carried_on_the_gap(conn):
    """M1 keeps Control on control@, so ETA rejections are invisible to
    it. The empty register and the reason it may be empty belong in the
    same sentence."""
    _, gaps = build_event_items(conn, CONFIG, TODAY)
    line = next(g for g in gaps if g.startswith("STAT-ETA-REJ"))
    assert "Detection of this event is MANUAL" in line
    assert "accounts@" in line
    # And the obligation without manual detection does not claim it.
    other = next(g for g in gaps if g.startswith("STAT-SI-HEADCOUNT"))
    assert "MANUAL" not in other


def test_an_event_without_a_window_length_is_not_given_one(conn):
    """§1.1. A clock is running; Control says it cannot count it rather
    than picking a plausible number."""
    config = {"obligations": [
        {"id": "STAT-ETA-REJ", "name": "ETA rejection clearance",
         "owner": "accounts@ubcsis.com", "mechanism": "event_window",
         "window_days": None}]}
    record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14),
                 "INV-9912", "MANUAL", "hadeer@ubcsis.com",
                 registered_at=date(2026, 8, 14))
    tracked, gaps = build_event_items(conn, config, TODAY)
    assert tracked == []
    line = next(g for g in gaps if "window_days is not set" in g)
    assert "The clock is running and Control is not counting it" in line


def test_an_event_for_an_unconfigured_obligation_is_kept_but_not_tracked(conn):
    record_event(conn, "STAT-MYSTERY", "SOMETHING", date(2026, 8, 14),
                 None, "MANUAL", "hadeer@ubcsis.com",
                 registered_at=date(2026, 8, 14))
    tracked, gaps = build_event_items(conn, CONFIG, TODAY)
    assert tracked == []
    assert any("is not configured as an event window" in g for g in gaps)
    # The event itself is not discarded — it is evidence of something.
    assert len(open_events(conn)) == 1


# ---- closure -----------------------------------------------------------

def test_a_discharged_event_stops_being_tracked(conn):
    event_id = record_event(
        conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14), "INV-9912",
        "MANUAL", "hadeer@ubcsis.com", registered_at=date(2026, 8, 14))
    tracked, _ = build_event_items(conn, CONFIG, TODAY)
    assert [t.item_id for t in tracked] == [f"STAT-ETA-REJ#{event_id}"]

    discharge_event(conn, event_id, date(2026, 8, 17), "hadeer@ubcsis.com",
                    reference="resubmitted 17-Aug")
    tracked, _ = build_event_items(conn, CONFIG, TODAY)
    assert tracked == []
    assert open_events(conn) == []


def test_discharge_does_not_alter_the_event_row(conn):
    """§5.2 append-only. The event happened; closing it does not make
    the record of it untrue, so closure is its own row."""
    event_id = record_event(
        conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14), "INV-9912",
        "MANUAL", "hadeer@ubcsis.com", registered_at=date(2026, 8, 14))
    discharge_event(conn, event_id, date(2026, 8, 17), "hadeer@ubcsis.com")
    row = conn.execute(
        "SELECT event_date, registered_at FROM statutory_events WHERE id = ?",
        (event_id,)).fetchone()
    assert row == ("2026-08-14", "2026-08-14")


def test_the_event_tables_are_append_only(conn):
    """The trigger, not a convention (§5.2)."""
    import sqlite3

    event_id = record_event(
        conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14), None,
        "MANUAL", "hadeer@ubcsis.com", registered_at=date(2026, 8, 14))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE statutory_events SET event_date = '2026-08-16'"
                     " WHERE id = ?", (event_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM statutory_events WHERE id = ?", (event_id,))


def test_detection_must_be_stated_and_cannot_be_invented(conn):
    """An event register that cannot say which rows a machine saw is
    reporting confidence it has not got."""
    with pytest.raises(ValueError):
        record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION",
                     date(2026, 8, 14), None, "PROBABLY",
                     "hadeer@ubcsis.com")


# ---- the shipped config -----------------------------------------------

def test_the_shipped_calendar_declares_both_event_windows():
    """The two obligations `parse_due` refuses are exactly the two this
    register is responsible for. If that stops being true, one of them
    is tracked by nothing at all."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    windows = {r["id"]: r for r in data["obligations"]
               if r.get("mechanism") == "event_window"}
    assert set(windows) == {"STAT-ETA-REJ", "STAT-SI-HEADCOUNT"}
    assert windows["STAT-ETA-REJ"]["window_days"] == 7
    assert windows["STAT-SI-HEADCOUNT"]["window_days"] == 30
    # B1 specifies a daily check for the 7-day window and only that one.
    # A weekly check there burns six of the seven days. The 30-day
    # window is served by the §2.1 ladder, and giving it a cadence the
    # order does not state would be inventing a rule (§1.3).
    assert windows["STAT-ETA-REJ"]["check_frequency"] == "daily"
    assert "check_frequency" not in windows["STAT-SI-HEADCOUNT"]
    for rule in windows.values():
        assert rule["owner"] and rule["trigger"]


def test_the_shipped_config_computes_real_deadlines(conn):
    """End to end against the file that actually ships."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14),
                 "INV-9912", "MANUAL", "hadeer@ubcsis.com",
                 registered_at=date(2026, 8, 14))
    tracked, _ = build_event_items(conn, data, TODAY)
    assert [(t.name, t.due) for t in tracked] == [
        ("ETA electronic invoicing — rejection clearance — INV-9912",
         date(2026, 8, 21))]
    assert tracked[0].owner == "accounts@ubcsis.com"


# ---- B1: Control observes its own cadence -----------------------------

def _log_days(logs_dir, *days):
    logs_dir.mkdir(parents=True, exist_ok=True)
    for day in days:
        (logs_dir / f"{day}.jsonl").write_text("{}\n", encoding="utf-8")


def test_no_cadence_finding_when_nothing_is_running(conn, tmp_path):
    """B1's check is about open windows. With none open, a quiet week
    is not a finding — there was nothing to miss."""
    from control.events import observed_cadence_gaps

    logs = tmp_path / "logs"
    _log_days(logs, "2026-08-01")
    assert observed_cadence_gaps(logs, CONFIG, conn, TODAY) == []


def test_a_missed_day_on_an_open_seven_day_window_is_a_finding(conn, tmp_path):
    """A weekly check burns six of the seven days, and Control cannot
    schedule itself — so it reports the cadence it actually ran at."""
    from control.events import observed_cadence_gaps

    record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14),
                 "INV-9912", "MANUAL", "hadeer@ubcsis.com",
                 registered_at=date(2026, 8, 14))
    logs = tmp_path / "logs"
    _log_days(logs, "2026-08-14", "2026-08-15", "2026-08-18")
    line = observed_cadence_gaps(logs, CONFIG, conn, TODAY)[0]
    assert "last ran on 15-Aug-2026; 2 day(s) since then had no cycle" in line
    assert "STAT-ETA-REJ" in line


def test_running_yesterday_is_not_a_finding(conn, tmp_path):
    from control.events import observed_cadence_gaps

    record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14),
                 None, "MANUAL", "hadeer@ubcsis.com",
                 registered_at=date(2026, 8, 14))
    logs = tmp_path / "logs"
    _log_days(logs, "2026-08-17", "2026-08-18")
    assert observed_cadence_gaps(logs, CONFIG, conn, TODAY) == []


def test_no_history_at_all_is_reported_as_no_evidence(conn, tmp_path):
    """Not "it ran fine" and not "it never ran" — no evidence either
    way, which for a 7-day window is most of the window (§1.1)."""
    from control.events import observed_cadence_gaps

    record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14),
                 None, "MANUAL", "hadeer@ubcsis.com",
                 registered_at=date(2026, 8, 14))
    logs = tmp_path / "logs"
    logs.mkdir()
    line = observed_cadence_gaps(logs, CONFIG, conn, TODAY)[0]
    assert "no prior cycle on record" in line
    assert "no evidence it has been running daily" in line
    assert "shortest window open is 7 days" in line


def test_the_thirty_day_window_alone_raises_no_cadence_finding(conn, tmp_path):
    """It carries no check_frequency, so there is no stated cadence to
    have missed."""
    from control.events import observed_cadence_gaps

    record_event(conn, "STAT-SI-HEADCOUNT", "JOINER", date(2026, 8, 1),
                 None, "MANUAL", "hr@ubcsis.com",
                 registered_at=date(2026, 8, 1))
    logs = tmp_path / "logs"
    _log_days(logs, "2026-08-01")
    assert observed_cadence_gaps(logs, CONFIG, conn, TODAY) == []


# ---- the migration this register found --------------------------------

def test_a_table_added_after_deployment_reaches_an_existing_database(tmp_path):
    """`ensure_schema` used to run only when the file was absent.

    A database created before the event register existed would never
    get its tables, and the first query against them failed at the
    point of use — mid-command, on the user's machine, rather than at
    startup. This is that bug, pinned.
    """
    from control.db import connect, ensure_schema, init_db

    path = tmp_path / "control.db"
    conn = init_db(path)
    conn.execute("DROP TRIGGER statutory_events_no_update")
    conn.execute("DROP TRIGGER statutory_events_no_delete")
    conn.execute("DROP TABLE statutory_events")     # simulate an older schema
    conn.commit()
    conn.close()

    conn = connect(path)
    try:
        added = ensure_schema(conn)
        assert added == ["statutory_events"]
        # And it is usable, triggers and all.
        record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION", date(2026, 8, 14),
                     None, "MANUAL", "hadeer@ubcsis.com",
                     registered_at=date(2026, 8, 14))
        assert len(open_events(conn)) == 1
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM statutory_events")
    finally:
        conn.close()


def test_ensure_schema_is_a_no_op_on_a_current_database(tmp_path):
    """It runs on every open, so it has to be silent when there is
    nothing to do — otherwise the notice means nothing."""
    from control.db import ensure_schema, init_db

    conn = init_db(tmp_path / "control.db")
    try:
        assert ensure_schema(conn) == []
        assert ensure_schema(conn) == []
    finally:
        conn.close()


def test_existing_rows_survive_a_schema_addition(tmp_path):
    """§5.2. There is no ALTER and no DROP in the path, and this is the
    test that says so rather than the comment."""
    from control.db import connect, ensure_schema, init_db

    path = tmp_path / "control.db"
    conn = init_db(path)
    event_id = record_event(conn, "STAT-ETA-REJ", "ETA_REJECTION",
                            date(2026, 8, 14), "INV-1", "MANUAL",
                            "hadeer@ubcsis.com",
                            registered_at=date(2026, 8, 14))
    conn.close()

    conn = connect(path)
    try:
        ensure_schema(conn)
        assert [e.row_id for e in open_events(conn)] == [event_id]
    finally:
        conn.close()
