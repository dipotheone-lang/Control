"""Dispute adjudication — §8.4, §3.3, §8.6, §13.1.

A dispute was detectable, loggable and clock-suspending, and had no way
to end. That is finding V4's stall lever: the appeal path is also the
route to stopping enforcement indefinitely, and it only closes if
somebody can actually rule.

The properties worth holding are about who may rule and what a ruling
leaves behind — an appended row rather than an edited one, a golden case
owed rather than invented, and a repeatedly-rejected disputant handled
as a pattern rather than argued with.
"""

import shutil
from datetime import date
from pathlib import Path

import pytest

from control.db import init_db
from control.disputes import (
    AuthorityError, adjudicate, assert_may_adjudicate, pending,
    record_golden_requirement, rejection_pattern,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO, HADEER = "ahmed@ubcsis.com", "ghareeb@ubcsis.com", "hadeer@ubcsis.com"


@pytest.fixture
def conn(tmp_path):
    connection = init_db(tmp_path / "control.db")
    connection.execute(
        "INSERT INTO submissions (id, obligation_id, verdict, source,"
        " submitted_by, period) VALUES (1, 'OB-VAT', 'RETURNED_FOR_REVISION',"
        " 'LIVE', ?, '2026-07')", (HADEER,))
    connection.execute(
        "INSERT INTO disputes (id, submission_id, raised_by, raised_at, state,"
        " source) VALUES (1, 1, ?, '2026-08-10', 'PENDING', 'LIVE')", (HADEER,))
    connection.commit()
    yield connection
    connection.close()


def rule(conn, dispute_id=1, outcome="UPHELD", by=CEO, reason="Form revision 3 "
         "was current on the submission date.", on=date(2026, 8, 18)):
    return adjudicate(conn, dispute_id, outcome=outcome, by=by, reason=reason,
                      ceo=CEO, coo=COO, on=on)


# ---- what is pending --------------------------------------------------

def test_a_pending_dispute_carries_what_is_needed_to_rule(conn):
    item = pending(conn, date(2026, 8, 18))[0]
    assert item.raised_by == HADEER
    assert item.obligation_id == "OB-VAT"
    assert item.verdict == "RETURNED_FOR_REVISION"
    assert item.days_open == 8
    assert item.linked


def test_an_unlinked_dispute_says_so_rather_than_implying_a_target(conn):
    conn.execute(
        "INSERT INTO disputes (id, raised_by, raised_at, state, source)"
        " VALUES (2, ?, '2026-08-12', 'PENDING', 'LIVE')", (HADEER,))
    conn.commit()
    unlinked = [d for d in pending(conn, date(2026, 8, 18))
                if d.dispute_id == 2][0]
    assert not unlinked.linked
    assert unlinked.obligation_id is None


def test_a_ruled_dispute_leaves_the_pending_list(conn):
    rule(conn)
    assert pending(conn, date(2026, 8, 18)) == []


# ---- who may rule (§3.3, D-12) ---------------------------------------

def test_the_ceo_rules_without_deputising(conn):
    assert assert_may_adjudicate(conn, CEO, ceo=CEO, coo=COO,
                                 on=date(2026, 8, 18)) is False


def test_the_coo_may_not_rule_while_the_ceo_is_present(conn):
    """The deputy path opens from the register, never from the deputy."""
    with pytest.raises(AuthorityError) as e:
        assert_may_adjudicate(conn, COO, ceo=CEO, coo=COO,
                              on=date(2026, 8, 18))
    assert "absence is not registered" in str(e.value)


def test_the_coo_rules_during_registered_absence(conn):
    conn.execute(
        "INSERT INTO absence (email, from_date, to_date, registered_by)"
        " VALUES (?, '2026-08-15', '2026-08-25', ?)", (CEO, "hr@ubcsis.com"))
    conn.commit()
    assert assert_may_adjudicate(conn, COO, ceo=CEO, coo=COO,
                                 on=date(2026, 8, 18)) is True


def test_a_deputised_ruling_is_logged_as_deputised(conn):
    conn.execute(
        "INSERT INTO absence (email, from_date, to_date, registered_by)"
        " VALUES (?, '2026-08-15', '2026-08-25', ?)", (CEO, "hr@ubcsis.com"))
    conn.commit()
    ruling = rule(conn, by=COO)
    assert ruling["deputised"] is True
    reason = conn.execute("SELECT correction_reason FROM disputes WHERE id = ?",
                          (ruling["ruling_id"],)).fetchone()[0]
    assert reason.startswith(f"[deputised for {CEO}]")


def test_nobody_else_may_rule(conn):
    with pytest.raises(AuthorityError) as e:
        rule(conn, by=HADEER)
    assert "§8.4 puts adjudication with the" in str(e.value)


# ---- what a ruling leaves behind (§5.2) ------------------------------

def test_a_ruling_is_appended_and_the_disputed_row_is_untouched(conn):
    ruling = rule(conn)
    original = conn.execute(
        "SELECT state, adjudicated_by FROM disputes WHERE id = 1").fetchone()
    assert original == ("PENDING", None)

    appended = conn.execute(
        "SELECT state, adjudicated_by, correction_of FROM disputes WHERE id = ?",
        (ruling["ruling_id"],)).fetchone()
    assert appended == ("UPHELD", CEO, 1)


def test_a_ruling_needs_a_reason(conn):
    """§8.6 reads the reason; §13.1 keeps it as the expected answer."""
    with pytest.raises(ValueError) as e:
        rule(conn, reason="   ")
    assert "needs a reason" in str(e.value)


def test_a_dispute_is_ruled_once(conn):
    rule(conn)
    with pytest.raises(ValueError) as e:
        rule(conn)
    assert "already" in str(e.value)


def test_an_unknown_outcome_is_refused(conn):
    with pytest.raises(ValueError):
        rule(conn, outcome="PARTIALLY")


# ---- §13.1: the case that is owed ------------------------------------

def test_an_upheld_dispute_queues_a_golden_case_it_cannot_write(tmp_path):
    """A case built from partial data would certify the engine against a
    document nobody read (§1.1)."""
    ruling = {"dispute_id": 1, "ruling_id": 2, "submission_id": 1}
    path = record_golden_requirement(
        tmp_path, ruling, reason="Revision 3 was current.",
        obligation_id="OB-VAT", verdict="RETURNED_FOR_REVISION",
        on=date(2026, 8, 18))

    text = path.read_text(encoding="utf-8")
    assert "Dispute 1 — upheld 18-Aug-2026" in text
    assert "Verdict contested: RETURNED_FOR_REVISION" in text
    assert "Expected answer (the ruling): Revision 3 was current." in text
    assert "closed by deleting a line" in text


def test_requirements_accumulate_rather_than_replace(tmp_path):
    for n in (1, 2):
        record_golden_requirement(
            tmp_path, {"dispute_id": n, "ruling_id": n + 10, "submission_id": n},
            reason="r", obligation_id="OB", verdict="NOT_ACCEPTED",
            on=date(2026, 8, 18))
    text = (tmp_path / "tests" / "golden-set" / "FROM-DISPUTES.md").read_text(
        encoding="utf-8")
    assert "Dispute 1" in text and "Dispute 2" in text


# ---- §8.6: a pattern, not an argument --------------------------------

def test_repeated_rejections_become_a_systemic_finding(conn):
    # Spaced apart: each ruling appends a row and takes the next id.
    for n in (100, 200, 300):
        conn.execute(
            "INSERT INTO disputes (id, submission_id, raised_by, raised_at,"
            " state, source) VALUES (?, 1, ?, '2026-08-10', 'PENDING', 'LIVE')",
            (n, HADEER))
        conn.commit()
        rule(conn, dispute_id=n, outcome="REJECTED", reason="Form was superseded.")

    lines = rejection_pattern(conn)
    assert len(lines) == 1
    assert HADEER in lines[0]
    assert "3 of 3 disputes rejected" in lines[0]
    assert "not re-argued item by item" in lines[0]


def test_one_rejection_is_not_a_pattern(conn):
    rule(conn, outcome="REJECTED", reason="Form was superseded.")
    assert rejection_pattern(conn) == []


# ---- end to end through the CLI and the report -----------------------

def test_the_command_rules_and_the_report_stops_counting_it(tmp_path, capsys):
    from control.__main__ import main
    from control.report import weekly_report

    control_root = tmp_path / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    shutil.copytree(REPO_CONFIG, control_root / "config")
    connection = init_db(control_root / "data" / "control.db")
    connection.execute(
        "INSERT INTO submissions (id, obligation_id, verdict, source,"
        " submitted_by, period) VALUES (1, 'OB-VAT', 'NOT_ACCEPTED', 'LIVE',"
        " ?, '2026-07')", (HADEER,))
    connection.execute(
        "INSERT INTO disputes (id, submission_id, raised_by, raised_at, state,"
        " source) VALUES (1, 1, ?, '2026-08-10', 'PENDING', 'LIVE')", (HADEER,))
    connection.commit()
    connection.close()

    def report_body():
        conn2 = init_db(control_root / "data" / "control.db")
        try:
            return weekly_report(
                conn2, as_of=date(2026, 8, 18), horizon=[], open_items=[],
                open_decisions=[], control_root=control_root,
                config_dir=control_root / "config")["body"]
        finally:
            conn2.close()

    assert "1 disputes pending adjudication, oldest 8 days" in report_body()

    code = main(["disputes", "--control-root", str(control_root),
                 "--uphold", "1", "--reason", "Revision 3 was current.",
                 "--today", "2026-08-18"])
    assert code == 0
    out = capsys.readouterr().out
    assert "dispute 1: UPHELD" in out
    assert "the original row is unchanged" in out
    assert "FROM-DISPUTES.md" in out

    assert "No disputes pending." in report_body()
