"""Manual entry for what OCR could not reach — §2.2, §5.5.

OCR raises the ceiling; it does not remove the floor. A below-floor
reading is a document the engine looked at and could not be trusted on,
and §5.5 forbids guessing from those. Sealed documents outside D-05's
contract scope stay closed by decision. Both leave real guarantee
expiries and claim windows outside the register.

Without a path back in, UNREADABLE is a dead end. These tests are about
making it a work queue instead — and about the apply step refusing to
interpret, because a guessed date in a class 2 register alerts
confidently on the wrong day.
"""

import csv
from datetime import date
from pathlib import Path

import pytest

from control.db import init_db
from control.discovery.manual_terms import (
    HEADERS, TERM_KINDS, Pending, apply_rows, pending_from_result,
    read_worksheet, write_worksheet,
)


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def sheet(tmp_path, rows):
    path = tmp_path / "MANUAL-TERMS.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**{h: "" for h in HEADERS}, **row})
    return path


# ---- building the queue -----------------------------------------------

class FakeResult:
    def __init__(self, unreadable=(), blocked=(), ocr_below_floor=()):
        self.unreadable = list(unreadable)
        self.blocked = list(blocked)
        self.ocr_below_floor = list(ocr_below_floor)


class FakeRecord:
    def __init__(self, path, note="", confidential=False):
        self.path = path
        self.note = note
        self.confidential = confidential


def test_the_queue_carries_why_not_just_which():
    """A below-floor scan is legible to a human, a sealed document may
    need permission, an engine failure may just need the engine. Those
    are different next actions."""
    pending = pending_from_result(FakeResult(
        unreadable=[FakeRecord("Legal/g.png", "OCR: mean confidence 42.0 "
                               "is below the §5.5 floor")],
        blocked=[FakeRecord("Enova/nda.pdf",
                            "not opened — D-01 metadata-only scope", True)],
        # Stage C records this as a note, not an object, so a cached
        # document replays without holding an OCR result in memory.
        ocr_below_floor=["g.png (mean confidence 42.0)"]))

    assert len(pending) == 2
    assert "below the §5.5 floor" in pending[0].why
    assert pending[0].ocr_confidence == 42.0
    assert pending[1].confidential is True


def test_the_worksheet_has_blank_answer_columns(tmp_path):
    path = write_worksheet(
        [Pending(document="Legal/g.png", why="below floor",
                 ocr_confidence=42.0)],
        tmp_path / "w.csv")
    with path.open(encoding="utf-8-sig", newline="") as f:
        record = next(csv.DictReader(f))
    assert record["document"] == "Legal/g.png"
    assert record["ocr_confidence"] == "42.0"
    assert record["TERM_KIND"] == ""
    assert record["DATE_yyyy_mm_dd"] == ""


# ---- the apply step refuses to interpret ------------------------------

def test_an_empty_row_is_not_an_entry(tmp_path):
    rows, problems = read_worksheet(sheet(tmp_path, [{"document": "a.png"}]))
    assert rows == [] and problems == []


def test_a_date_term_without_a_date_is_refused(tmp_path):
    _, problems = read_worksheet(sheet(tmp_path, [
        {"document": "a.png", "TERM_KIND": "GUARANTEE_EXPIRY"}]))
    assert "needs a date" in problems[0]
    assert "alerts on nothing" in problems[0]


def test_a_malformed_date_is_named_not_guessed(tmp_path):
    _, problems = read_worksheet(sheet(tmp_path, [
        {"document": "a.png", "TERM_KIND": "GUARANTEE_EXPIRY",
         "DATE_yyyy_mm_dd": "30/11/2026"}]))
    assert "not interpreted" in problems[0]
    assert "line 2" in problems[0]


def test_an_unknown_term_kind_is_refused(tmp_path):
    _, problems = read_worksheet(sheet(tmp_path, [
        {"document": "a.png", "TERM_KIND": "WARRANTY_THING",
         "DATE_yyyy_mm_dd": "2026-11-30"}]))
    assert "is not one of" in problems[0]


def test_a_non_numeric_value_is_refused_not_stored_as_null(tmp_path):
    """The defect this test exists for: 'NOTICE_PERIOD_DAYS = 0.5% per
    week' silently became NULL, dropping a term the person believed they
    had entered."""
    rows, problems = read_worksheet(sheet(tmp_path, [
        {"document": "a.png", "TERM_KIND": "NOTICE_PERIOD_DAYS",
         "VALUE": "within a fortnight"}]))
    assert rows == []
    assert "needs a number" in problems[0]
    assert "nothing was stored for it" in problems[0]


def test_free_text_terms_accept_prose(tmp_path):
    """Contracts phrase LD rates and payment terms in words, and the
    schema stores them as text."""
    rows, problems = read_worksheet(sheet(tmp_path, [
        {"document": "a.png", "TERM_KIND": "LD_RATE",
         "VALUE": "0.5% of contract value per week, capped at 10%"}]))
    assert problems == [] and len(rows) == 1


def test_a_good_row_reads_cleanly(tmp_path):
    rows, problems = read_worksheet(sheet(tmp_path, [
        {"document": "Legal/g.png", "TERM_KIND": "guarantee_expiry",
         "DATE_yyyy_mm_dd": "2026-11-30", "COUNTERPARTY": "Enova"}]))
    assert problems == []
    assert rows[0]["kind"] == "GUARANTEE_EXPIRY"
    assert rows[0]["date"] == "2026-11-30"
    assert rows[0]["counterparty"] == "Enova"


# ---- what lands in the registers --------------------------------------

def entry(kind, **over):
    base = {"document": "Legal/g.png", "kind": kind, "date": "2026-11-30",
            "value": "", "counterparty": "Enova", "notes": "", "line": 2}
    base.update(over)
    return base


def test_a_guarantee_becomes_an_alerting_deadline(conn):
    from control import registers as reg

    apply_rows(conn, [entry("GUARANTEE_EXPIRY")],
               entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))
    horizon = reg.horizon(conn, date(2026, 11, 1), days=60)
    assert len(horizon) == 1
    assert horizon[0].item.due == date(2026, 11, 30)
    assert horizon[0].register == "instruments"


def test_provenance_stays_inside_the_charter_vocabulary(conn):
    """§5.2 fixes source at LIVE | BACKFILL. Inventing a third value for
    convenience is how a schema stops meaning what the charter says."""
    apply_rows(conn, [entry("GUARANTEE_EXPIRY")],
               entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))
    source, by, ref = conn.execute(
        "SELECT source, submitted_by, instrument_ref FROM registers_instruments"
    ).fetchone()
    assert source == "BACKFILL"
    assert by == "ahmed@ubcsis.com"     # what marks it hand-read
    assert ref.startswith("MAN-")       # and greppable as a pass


def test_a_retention_records_release_as_well_as_expiry(conn):
    """expiry_date is NOT NULL, and for a retention the two are the same
    event — recorded on both rather than inventing a filler."""
    apply_rows(conn, [entry("RETENTION_RELEASE")],
               entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))
    expiry, release = conn.execute(
        "SELECT expiry_date, release_date FROM registers_instruments").fetchone()
    assert expiry == release == "2026-11-30"


def test_contract_terms_reach_their_real_columns(conn):
    apply_rows(conn, [
        entry("CONTRACT_END"),
        entry("DEFECTS_LIABILITY_END"),
        entry("NOTICE_PERIOD_DAYS", date="", value="28"),
        entry("RETENTION_PERCENT", date="", value="10"),
        entry("PAYMENT_TERMS", date="", value="net 60 days"),
    ], entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))

    rows = conn.execute(
        "SELECT end_date, dlp_end_date, notice_period_days, retention_pct,"
        " payment_terms FROM registers_contracts").fetchall()
    assert any(r[0] == "2026-11-30" for r in rows)
    assert any(r[1] == "2026-11-30" for r in rows)
    assert any(r[2] == 28 for r in rows)
    assert any(r[3] == 10.0 for r in rows)
    assert any(r[4] == "net 60 days" for r in rows)


def test_a_notice_period_becomes_a_standing_claim_window(conn):
    """§2.2: a claim not noticed within its window is generally
    forfeited. Typed by hand, it still has to show up."""
    from control import registers as reg

    apply_rows(conn, [entry("NOTICE_PERIOD_DAYS", date="", value="28")],
               entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))
    windows = reg.notice_periods(conn)
    assert len(windows) == 1
    assert windows[0]["notice_period_days"] == 28


def test_an_accreditation_lands_on_its_own_register(conn):
    apply_rows(conn, [entry("ACCREDITATION_EXPIRY")],
               entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))
    client, expiry = conn.execute(
        "SELECT client, expiry_date FROM registers_accreditations").fetchone()
    assert client == "Enova" and expiry == "2026-11-30"


def test_a_missing_counterparty_is_recorded_as_not_provided(conn):
    """§1.1 — an unnamed counterparty is a visible gap, not a blank."""
    apply_rows(conn, [entry("ACCREDITATION_EXPIRY", counterparty="")],
               entered_by="ahmed@ubcsis.com", on_date=date(2026, 8, 17))
    assert conn.execute(
        "SELECT client FROM registers_accreditations").fetchone()[0] \
        == "NOT PROVIDED"


# ---- the vocabulary itself --------------------------------------------

def test_milestone_is_absent_because_no_column_holds_it():
    """§2.2 lists milestones, registers_contracts has no column, and
    squeezing one into end_date would put a wrong date where an alert
    reads a real one."""
    assert "MILESTONE" not in TERM_KINDS


def test_every_kind_can_actually_be_stored(conn):
    """A vocabulary offering a kind no register accepts would collect
    work from a human and drop it."""
    dated = {"GUARANTEE_EXPIRY", "BOND_EXPIRY", "RETENTION_RELEASE",
             "CONTRACT_END", "DEFECTS_LIABILITY_END", "ACCREDITATION_EXPIRY"}
    numeric = {"NOTICE_PERIOD_DAYS", "RETENTION_PERCENT"}
    rows = [entry(kind,
                  date="2026-11-30" if kind in dated else "",
                  value="" if kind in dated else ("28" if kind in numeric
                                                  else "net 60"))
            for kind in TERM_KINDS]
    counts = apply_rows(conn, rows, entered_by="ahmed@ubcsis.com",
                        on_date=date(2026, 8, 17))
    assert sum(counts.values()) == len(TERM_KINDS)
