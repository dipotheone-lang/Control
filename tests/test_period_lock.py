"""The §5.2 period lock, actually applied — finding F8.

The lock existed at both ends and connected in the middle to nothing.
`period_locks` was only ever read; no code inserted a row, so no period
was ever locked. And `insert_submission` — the helper that honours the
lock — was not what the cycle used: the cycle wrote submissions with
raw SQL, walking straight past the check. Two halves of a control, each
inert because of the other.

F8 in Appendix A is marked resolved. It was resolved as a schema and a
function, not as a behaviour.

What matters here is that the lock is narrow and that refusal is not
silent. A lock that reached periods the report never mentioned would
refuse legitimate work; a refusal that vanished would lose a submission
somebody sent.
"""

import io
import shutil
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from control import HaltError
from control.cycle import SubmissionSpec, run_cycle
from control.db import (
    connect, init_db, insert_submission, lock_period, locked_periods,
    period_is_locked, reported_periods,
)
from control.evaluate import ObligationSpec
from control.startup import run_startup
from control.transport import FetchedMessage, MockTransport

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def conn(tmp_path):
    connection = init_db(tmp_path / "control.db")
    yield connection
    connection.close()


def submission(conn, period, **over):
    row = {"obligation_id": "OB-1", "verdict": "ACCEPTED", "source": "LIVE",
           "submitted_by": "hadeer@ubcsis.com", "period": period}
    row.update(over)
    return insert_submission(conn, row)


# ---- locking -----------------------------------------------------------

def test_a_period_locks_once(conn):
    assert lock_period(conn, "2026-07", "WEEKLY-2026-08-01") is True
    assert period_is_locked(conn, "2026-07")


def test_relocking_does_not_stack_rows(conn):
    """Re-running a report for the same date must not add lock rows, and
    the FIRST report to cover a period is the one a correction reissues."""
    lock_period(conn, "2026-07", "WEEKLY-2026-08-01")
    assert lock_period(conn, "2026-07", "WEEKLY-2026-08-08") is False

    assert locked_periods(conn) == [("2026-07", "WEEKLY-2026-08-01")]


def test_an_unreported_period_is_not_locked(conn):
    assert period_is_locked(conn, "2026-09") is False


# ---- which periods a report covers -------------------------------------

def test_only_periods_with_rows_in_the_window_count_as_reported(conn):
    submission(conn, "2026-08", submitted_at="2026-08-14")
    conn.execute(
        "INSERT INTO submissions (obligation_id, period, source, posted_at)"
        " VALUES ('OB-OLD', '2026-05', 'LIVE', '2026-05-02 09:00:00')")
    conn.commit()

    covered = reported_periods(conn, "2026-08-11 00:00:00")
    assert covered == ["2026-08"]      # the May row is outside the window


def test_rows_with_no_period_are_not_locked_as_a_blank(conn):
    conn.execute(
        "INSERT INTO submissions (obligation_id, source) VALUES ('OB-X', 'LIVE')")
    conn.commit()
    assert reported_periods(conn, "2000-01-01 00:00:00") == []


# ---- what the lock refuses ---------------------------------------------

def test_a_late_entry_into_a_locked_period_is_refused(conn):
    lock_period(conn, "2026-07", "WEEKLY-2026-08-01")
    with pytest.raises(HaltError) as e:
        submission(conn, "2026-07")
    assert "locked" in str(e.value)
    assert "reissued report revision" in str(e.value)


def test_a_ceo_approved_correction_still_goes_in(conn):
    """The lock does not freeze the record — it requires the correction
    to be deliberate, and the report reissued (§5.2)."""
    original = submission(conn, "2026-07")
    lock_period(conn, "2026-07", "WEEKLY-2026-08-01")

    corrected = submission(
        conn, "2026-07", correction_of=original,
        correction_reason="CEO-approved: revision 3 was current")
    assert corrected != original


def test_an_unlocked_period_is_unaffected(conn):
    lock_period(conn, "2026-07", "WEEKLY-2026-08-01")
    assert submission(conn, "2026-08")


# ---- the cycle honours it ----------------------------------------------

@pytest.fixture
def env(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    startup = run_startup(control_root, ub_root, "DRY_RUN", "OBSERVE", 1,
                          "2026-08-13")
    return startup, control_root


def _book():
    wb = openpyxl.Workbook()
    wb.active["B2"] = 7
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SPEC = ObligationSpec(
    obligation_id="OPS-1", name="Daily site", form_code="FRM-SITE",
    current_revision="1", due=datetime(2026, 8, 13, 17, 0),
    mandatory_fields=["B2"])


def run(env, period="2026-08-13"):
    startup, control_root = env
    specs = {"OPS-1": SubmissionSpec(
        spec=SPEC, mapping={"B2": "Sheet!B2"}, surname="Elsayed",
        period=period)}
    return run_cycle(
        startup, MockTransport([FetchedMessage(
            message_id="M1", sender="Ahmed Elsayed <a.elsayed@ubcsis.com>",
            received_at=datetime(2026, 8, 13, 10, 0),
            to="control@ubcsis.com", subject="FRM-SITE daily",
            attachments=[("FRM-SITE-rev1.xlsx", _book())])]),
        control_root, specs=specs, today=date(2026, 8, 13),
        ceo="ahmed@ubcsis.com", cfo="accounts@ubcsis.com",
        coo="ghareeb@ubcsis.com")


def test_the_cycle_posts_into_an_unlocked_period(env):
    startup, _ = env
    result = run(env)
    assert result.locked_period_refusals == []

    conn = connect(startup.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 1
    finally:
        conn.close()


def test_the_cycle_refuses_a_locked_period_without_dying(env):
    """§13.2: one refused submission must not abandon the sweep."""
    startup, _ = env
    conn = connect(startup.db_path)
    try:
        lock_period(conn, "2026-08-13", "WEEKLY-2026-08-13")
    finally:
        conn.close()

    result = run(env)
    assert result.processed == 1                      # the sweep completed
    assert len(result.locked_period_refusals) == 1
    assert "OPS-1 2026-08-13" in result.locked_period_refusals[0]

    conn = connect(startup.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 0
    finally:
        conn.close()


def test_the_report_locks_the_periods_it_reported(env, capsys):
    from control.__main__ import main

    startup, control_root = env
    run(env)

    code = main(["report", "--control-root", str(control_root),
                 "--ub-root", str(control_root.parent), "--run-mode", "DRY_RUN",
                 "--learning-mode", "OBSERVE", "--as-of", "2026-08-13"])
    assert code == 0
    assert "PERIOD LOCK (§5.2): 2026-08-13" in capsys.readouterr().out

    conn = connect(startup.db_path)
    try:
        assert period_is_locked(conn, "2026-08-13")
    finally:
        conn.close()


def test_reissuing_the_report_does_not_relock_or_claim_to(env, capsys):
    from control.__main__ import main

    _, control_root = env
    run(env)
    args = ["report", "--control-root", str(control_root),
            "--ub-root", str(control_root.parent), "--run-mode", "DRY_RUN",
            "--learning-mode", "OBSERVE", "--as-of", "2026-08-13"]
    main(args)
    capsys.readouterr()

    main(args)
    assert "PERIOD LOCK" not in capsys.readouterr().out
