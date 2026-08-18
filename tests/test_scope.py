"""Mailbox scope — O-05 closed as D-07 (Option C), 16-Aug-2026.

The decision is settled. The deployment is not, and the charter says
why: Option C "requires the §12.4 usage policy to state it explicitly,"
and §12.2 requires a PDPL basis covering the wider ingestion.

Everything here tests one distinction — what was decided versus what
Control may read today. A system that quietly widened its own reach
because a decision had been recorded would be exactly the surveillance
the §12.4 gate exists to prevent.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control import HaltError
from control.db import init_db
from control.report import weekly_report
from control.scope import (
    assert_readable, limitation_lines, load_scope, load_scope_file,
    open_precondition_lines,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CONTROL = "control@ubcsis.com"


def scope_data(**over):
    base = {
        "option": "C",
        "state": "DECIDED",
        "control_mailbox": CONTROL,
        "mailboxes": ["sales@ubcsis.com", "procure@ubcsis.com"],
        "preconditions": [{"id": "O-08", "requirement": "usage policy",
                           "closed": False}],
    }
    base.update(over)
    return base


# ---- the operative scope ---------------------------------------------

def test_no_file_means_option_a_not_a_halt():
    """§3.1a's own default. Absence is a safe state, not a crash."""
    scope = load_scope(None)
    assert scope.effective == [CONTROL]
    assert scope.operating_option == "A"


def test_a_decision_alone_does_not_widen_the_scope():
    scope = load_scope(scope_data())
    assert scope.option == "C"
    assert scope.effective == [CONTROL]
    assert scope.operating_option == "A"
    assert scope.pending is True


def test_closed_preconditions_are_still_not_enough():
    """Closing the conditions permits the change; it does not make it."""
    scope = load_scope(scope_data(
        preconditions=[{"id": "O-08", "closed": True}]))
    assert scope.state == "DECIDED"
    assert scope.effective == [CONTROL]


def test_live_with_closed_preconditions_widens_the_scope():
    scope = load_scope(scope_data(
        state="LIVE", preconditions=[{"id": "O-08", "closed": True}]))
    assert scope.effective == [CONTROL, "sales@ubcsis.com", "procure@ubcsis.com"]
    assert scope.operating_option == "C"
    assert scope.pending is False


def test_live_with_an_open_precondition_halts():
    """The one combination that must never pass quietly."""
    with pytest.raises(HaltError) as e:
        load_scope(scope_data(state="LIVE"))
    assert "O-08" in str(e.value)
    assert "does not widen its own scope" in str(e.value)


def test_an_unknown_state_halts_rather_than_defaulting():
    with pytest.raises(HaltError) as e:
        load_scope(scope_data(state="ENABLED"))
    assert "ENABLED" in str(e.value)


def test_control_mailbox_is_never_duplicated_when_also_listed():
    scope = load_scope(scope_data(
        state="LIVE", mailboxes=[CONTROL, "sales@ubcsis.com"],
        preconditions=[]))
    assert scope.effective == [CONTROL, "sales@ubcsis.com"]


def test_addresses_are_compared_lowercased():
    scope = load_scope(scope_data(
        state="LIVE", mailboxes=["Sales@UBCSIS.com"], preconditions=[]))
    assert "sales@ubcsis.com" in scope.effective


# ---- the guard --------------------------------------------------------

def test_reading_an_out_of_scope_mailbox_is_refused():
    scope = load_scope(scope_data())
    with pytest.raises(HaltError) as e:
        assert_readable("sales@ubcsis.com", scope)
    assert "D-07" in str(e.value)
    assert "preconditions close" in str(e.value)


def test_control_is_always_readable():
    assert_readable(CONTROL, load_scope(scope_data()))
    assert_readable("CONTROL@ubcsis.com", load_scope(scope_data()))


# ---- what the report says --------------------------------------------

def test_option_a_wording_is_the_chartered_line():
    en, ar = limitation_lines(load_scope(None))
    assert "limited to threads copied to control@" in en
    assert "sales@ and procure@ is not visible" in en
    assert "control@" in ar


def test_a_pending_decision_is_disclosed_not_hidden():
    en, ar = limitation_lines(load_scope(scope_data()))
    assert "not visible to this system" in en      # still true
    assert "D-07" in en and "not yet in effect" in en
    assert "1 precondition(s) remain open" in en
    assert "D-07" not in ar or "الخيار" in ar      # Arabic says the same


def test_the_pending_line_counts_the_real_preconditions():
    """The number is read from config, not written into the sentence —
    so it stays true as preconditions close one at a time."""
    en, _ = limitation_lines(load_scope_file(REPO_CONFIG))
    assert "3 precondition(s) remain open" in en


def test_live_scope_stops_claiming_a_blind_spot_it_no_longer_has():
    """Overstating the blind spot understates what Control holds."""
    en, ar = limitation_lines(load_scope(scope_data(
        state="LIVE", preconditions=[])))
    assert "sales@ and procure@ is not visible" not in en
    assert "sales@ubcsis.com" in en
    assert "D-07" in en and "D-07" in ar


def test_open_preconditions_become_decision_lines():
    lines = open_precondition_lines(load_scope(scope_data()))
    assert "O-05 is closed" in lines[0]
    assert "operating on Option A" in lines[0]
    assert any("O-08" in line and "usage policy" in line for line in lines[1:])


def test_no_lines_once_the_scope_is_actually_live():
    assert open_precondition_lines(load_scope(scope_data(
        state="LIVE", preconditions=[]))) == []


def test_no_lines_when_option_a_was_the_choice():
    assert open_precondition_lines(load_scope({"option": "A"})) == []


# ---- the repository config -------------------------------------------

def test_repo_config_records_the_ceo_decision():
    data = yaml.safe_load(
        (REPO_CONFIG / "mailbox-scope.yaml").read_text(encoding="utf-8"))
    assert data["option"] == "C"
    assert data["decided"] == date(2026, 8, 16)
    assert data["decided_by"] == "ahmed@ubcsis.com"
    # Decided, not deployed.
    assert data["state"] == "DECIDED"


def test_repo_config_names_the_seven_shared_mailboxes():
    scope = load_scope_file(REPO_CONFIG)
    assert set(scope.declared) == {
        "sales@ubcsis.com", "procure@ubcsis.com", "info@ubcsis.com",
        "accounts@ubcsis.com", "hr@ubcsis.com", "hse@ubcsis.com",
        "marketing@ubcsis.com"}


def test_individual_and_external_mailboxes_are_excluded_on_purpose():
    """A CEO's own mailbox is a different decision with a different footprint."""
    scope = load_scope_file(REPO_CONFIG)
    excluded = {e["address"] for e in scope.excluded}
    assert excluded == {"ahmed@ubcsis.com", "contact.ubcsis@gmail.com"}
    assert "ahmed@ubcsis.com" not in scope.declared


def test_repo_config_still_operates_on_option_a():
    scope = load_scope_file(REPO_CONFIG)
    assert scope.effective == [CONTROL]
    assert {p["id"] for p in scope.open_preconditions} == {"O-07", "O-08", "O-10"}


def test_unparseable_scope_file_halts(tmp_path):
    (tmp_path / "mailbox-scope.yaml").write_text("{{ not yaml", encoding="utf-8")
    with pytest.raises(HaltError):
        load_scope_file(tmp_path)


# ---- end to end through the report -----------------------------------

def test_weekly_report_carries_the_pending_scope(tmp_path):
    conn = init_db(tmp_path / "control.db")
    try:
        report = weekly_report(
            conn, as_of=date(2026, 8, 20), horizon=[], open_items=[],
            open_decisions=[], control_root=tmp_path, config_dir=REPO_CONFIG)
    finally:
        conn.close()
    body = report["body"]
    assert "O-05 is closed" in body
    assert "O-07" in body and "O-08" in body and "O-10" in body
    assert "not yet in effect" in body
