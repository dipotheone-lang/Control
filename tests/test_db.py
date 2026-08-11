import sqlite3

import pytest

from control import HaltError
from control.db import init_db, insert_submission, integrity_check


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def test_append_only_blocks_update_and_delete(conn):
    conn.execute(
        "INSERT INTO submissions (obligation_id, verdict, source) VALUES ('X', 'ACCEPTED', 'LIVE')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE submissions SET verdict = 'NOT_ACCEPTED' WHERE obligation_id = 'X'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM submissions WHERE obligation_id = 'X'")


def test_correction_requires_reason(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO submissions (obligation_id, source, correction_of) VALUES ('X', 'LIVE', 1)"
        )
    # With a reason it is allowed
    conn.execute(
        "INSERT INTO submissions (obligation_id, source, correction_of, correction_reason)"
        " VALUES ('X', 'LIVE', 1, 'CEO-approved correction #7')"
    )


def test_currency_discipline(conn):
    # Non-EGP without fx_rate/date must fail (§5.2)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO anomalies (signal, detail, amount, currency_code, source)"
            " VALUES ('S1', 'x', 100.0, 'USD', 'LIVE')"
        )
    # EGP needs no rate; USD with rate and date passes
    conn.execute(
        "INSERT INTO anomalies (signal, detail, amount, currency_code, source)"
        " VALUES ('S1', 'x', 100.0, 'EGP', 'LIVE')"
    )
    conn.execute(
        "INSERT INTO anomalies (signal, detail, amount, currency_code, fx_rate, fx_rate_date, source)"
        " VALUES ('S1', 'x', 100.0, 'USD', 48.6, '2026-08-11', 'LIVE')"
    )
    # An amount with no currency at all must fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO anomalies (signal, detail, amount, source) VALUES ('S1', 'x', 5.0, 'LIVE')"
        )


def test_period_lock(conn):
    conn.execute(
        "INSERT INTO period_locks (period, locked_by_report, source) VALUES ('2026-07', 'MGMT-2026-07', 'LIVE')"
    )
    conn.commit()
    with pytest.raises(HaltError, match="locked"):
        insert_submission(conn, {"obligation_id": "X", "period": "2026-07", "source": "LIVE"})
    # A CEO-approved correction passes
    rowid = insert_submission(
        conn,
        {
            "obligation_id": "X",
            "period": "2026-07",
            "source": "LIVE",
            "correction_of": 1,
            "correction_reason": "CEO approval D-ref",
        },
    )
    assert rowid > 0
    # Unlocked periods pass normally
    assert insert_submission(conn, {"obligation_id": "X", "period": "2026-08", "source": "LIVE"}) > 0


def test_integrity_check_passes(conn):
    integrity_check(conn)
