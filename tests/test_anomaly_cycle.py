"""§7.3 substantive signals, reaching the CEO — and the D-10 budget.

`anomaly.py` held all eleven S1–S4 detectors, tested, with **zero
callers**. The `anomalies` table was never written, so the report's
flags section was permanently empty and the D-10 budget of ten a week
metered nothing. R1 and R2 in Appendix A — both CRITICAL, both marked
resolved — rested on code that never ran.

Most of the detectors need a source the database does not hold: a
supplier bank register, invoices, purchase orders, approval records.
Those stay unrun, and the report names each one and what it needs,
because a flags section showing only what ran would read as *nothing
found* rather than *most of this is not looking* (§1.1).

What runs today is the out-of-hours timestamp — metadata only, so it
works on confidential items too — under a budget that suppresses
visibly rather than dropping silently.
"""

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from control.anomaly import (
    SUPPRESSED, Flag, record_flag, s1_out_of_hours, weekly_flag_count,
)
from control.db import init_db
from control.report import weekly_report

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
HOURS = {"start": "09:00", "end": "17:00", "confirmed_by_ceo": True}


@pytest.fixture
def conn(tmp_path):
    connection = init_db(tmp_path / "control.db")
    yield connection
    connection.close()


def flag(n=0, priority="NORMAL"):
    return Flag(signal="S1", code="OUT_OF_HOURS", priority=priority,
                detail=f"submission {n} outside working hours")


# ---- the signal that runs today ---------------------------------------

def test_a_submission_inside_working_hours_is_not_flagged():
    assert s1_out_of_hours(datetime(2026, 8, 13, 11, 0), HOURS) is None


def test_a_submission_outside_working_hours_is_flagged():
    result = s1_out_of_hours(datetime(2026, 8, 13, 23, 40), HOURS)
    assert result is not None
    assert result.code == "OUT_OF_HOURS"
    assert "09:00–17:00" in result.detail


def test_the_signal_stays_silent_without_the_ceo_confirmation():
    """§8.3, O-11: an unconfirmed config edit must not switch on a
    signal that observes when named people work."""
    unconfirmed = dict(HOURS, confirmed_by_ceo=False)
    assert s1_out_of_hours(datetime(2026, 8, 13, 23, 40), unconfirmed) is None
    assert s1_out_of_hours(datetime(2026, 8, 13, 23, 40), None) is None


# ---- the D-10 budget ---------------------------------------------------

def test_flags_reach_the_ceo_until_the_budget_is_spent(conn):
    since = datetime(2026, 8, 11)
    for n in range(10):
        assert record_flag(conn, flag(n), budget=10, since=since) == "CEO"
    assert weekly_flag_count(conn, since) == 10


def test_the_eleventh_flag_is_suppressed_and_still_recorded(conn):
    """D-10: reported as suppressed, never silently dropped."""
    since = datetime(2026, 8, 11)
    for n in range(10):
        record_flag(conn, flag(n), budget=10, since=since)

    assert record_flag(conn, flag(11), budget=10, since=since) == SUPPRESSED
    rows = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    assert rows == 11                       # written, not dropped
    assert weekly_flag_count(conn, since) == 10   # but not counted as raised


def test_the_highest_priority_flag_never_suppresses(conn):
    """The supplier bank-detail change. Rationing the highest-priority
    signal in the system for volume defeats the budget's own purpose."""
    since = datetime(2026, 8, 11)
    for n in range(20):
        record_flag(conn, flag(n), budget=10, since=since)

    assert record_flag(conn, flag(99, priority="HIGHEST"),
                       budget=10, since=since) == "CEO"


def test_last_weeks_flags_do_not_spend_this_weeks_budget(conn):
    conn.execute(
        "INSERT INTO anomalies (signal, detail, flagged_to, source, posted_at)"
        " SELECT 'S1', 'old', 'CEO', 'LIVE', '2026-07-01 09:00:00'"
        " FROM (SELECT 1) CROSS JOIN (SELECT 1)")
    conn.commit()
    assert weekly_flag_count(conn, datetime(2026, 8, 11)) == 0


def test_no_budget_configured_means_no_suppression(conn):
    for n in range(50):
        assert record_flag(conn, flag(n)) == "CEO"


# ---- what the report says ---------------------------------------------

def report_body(conn, tmp_path):
    return weekly_report(
        conn, as_of=date(2026, 8, 18), horizon=[], open_items=[],
        open_decisions=[], control_root=tmp_path,
        config_dir=REPO_CONFIG)["body"]


def test_suppressed_flags_are_shown_as_held_not_hidden(conn, tmp_path):
    since = datetime.now() - timedelta(days=1)
    for n in range(12):
        record_flag(conn, flag(n), budget=10, since=since)

    body = report_body(conn, tmp_path)
    assert "2 flag(s) held back over the D-10 budget" in body
    assert "recorded, not dropped" in body


def test_the_report_names_every_signal_that_is_not_running(conn, tmp_path):
    """§1.1 — an empty flags section must not read as 'nothing found'."""
    body = report_body(conn, tmp_path)
    assert "SIGNALS NOT RUNNING, AND WHAT EACH NEEDS" in body
    assert "bank-detail change" in body and "supplier bank register" in body
    assert "S2 authority" in body and "O-02" in body
    assert "S4 cross-source reconciliation" in body


def test_the_report_says_which_signals_do_run(conn, tmp_path):
    body = report_body(conn, tmp_path)
    assert "Out-of-hours timestamps and near-miss sender domains" in body
    assert "metadata alone" in body


# ---- end to end through a cycle ---------------------------------------

def test_a_late_night_submission_flags_without_touching_the_verdict(tmp_path):
    """§7.3: flags never change the verdict and never reach the
    submitter — they are recorded for the CEO alone."""
    import io

    import openpyxl

    from control.cycle import SubmissionSpec, run_cycle
    from control.db import connect
    from control.evaluate import ObligationSpec
    from control.startup import run_startup
    from control.transport import FetchedMessage, MockTransport

    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    startup = run_startup(control_root, ub_root, "DRY_RUN", "OBSERVE", 1,
                          "2026-08-13")

    wb = openpyxl.Workbook()
    wb.active["B2"] = 7
    buf = io.BytesIO()
    wb.save(buf)

    spec = ObligationSpec(
        obligation_id="OPS-1", name="Daily site", form_code="FRM-SITE",
        current_revision="1", due=datetime(2026, 8, 13, 17, 0),
        mandatory_fields=["B2"])
    specs = {"OPS-1": SubmissionSpec(
        spec=spec, mapping={"B2": "Sheet!B2"}, surname="Elsayed",
        period="2026-08-13")}

    result = run_cycle(
        startup, MockTransport([FetchedMessage(
            message_id="M1", sender="Ahmed Elsayed <a.elsayed@ubcsis.com>",
            received_at=datetime(2026, 8, 13, 23, 40),
            to="control@ubcsis.com", subject="FRM-SITE daily",
            attachments=[("FRM-SITE-rev1.xlsx", buf.getvalue())])]),
        control_root, specs=specs, today=date(2026, 8, 13),
        ceo="ahmed@ubcsis.com", cfo="accounts@ubcsis.com",
        coo="ghareeb@ubcsis.com")

    assert result.flags_raised == 1

    conn = connect(startup.db_path)
    try:
        signal, detail, to = conn.execute(
            "SELECT signal, detail, flagged_to FROM anomalies").fetchone()
    finally:
        conn.close()
    assert signal == "S1"
    assert "OUT_OF_HOURS" in detail
    assert to == "CEO"

    # The verdict is unaffected, and no reply carries the flag.
    for path in (control_root / "outbox").rglob("*.json"):
        assert "OUT_OF_HOURS" not in path.read_text(encoding="utf-8")
