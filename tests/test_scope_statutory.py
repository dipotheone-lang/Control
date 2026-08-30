"""Statutory-only operation — decision D-15.

The CEO narrowed the project on 30-Aug-2026 after reading the status
page: no mailbox scan had ever completed on the operating machine, 130
of 314 documents in the contract folders were unreadable, and nothing in
§12 was circulated. Class 1 needs none of that — the deadline engine
computes from a calendar, not an inbox.

The narrowing is enforced rather than documented. Its whole basis for
operating without the §12 pre-conditions is that no mailbox is read, so
a single sweep would not be an inconvenience: it would process personal
data with no lawful basis documented and nobody notified.
"""

import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from control import HaltError
from control.calendar import WorkingCalendar
from control.cycle import run_cycle
from control.enforce import Enforcer, Person, TrackedItem
from control.scope_statutory import (
    CLASS3_LADDER,
    MAILBOX_READ,
    STATUTORY_ONLY,
    assert_scope_permits,
    normalise,
    permits,
    summary,
)
from control.startup import run_startup
from control.transport import FetchedMessage, MockTransport

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO, CFO = "ahmed@ubcsis.com", "ghareeb@ubcsis.com", "accounts@ubcsis.com"


# ---- the scope itself --------------------------------------------------

def test_an_unrecognised_scope_halts_rather_than_defaulting():
    """Defaulting would pick the wider one, so a typo would widen what
    Control may read (§5.6)."""
    with pytest.raises(HaltError) as caught:
        normalise("statutory")
    assert "not one of FULL, STATUTORY_ONLY" in str(caught.value)


def test_the_full_scope_permits_everything():
    assert permits("FULL", MAILBOX_READ)
    assert permits("FULL", CLASS3_LADDER)


def test_the_narrowed_scope_refuses_with_the_reason():
    with pytest.raises(HaltError) as caught:
        assert_scope_permits(STATUTORY_ONLY, MAILBOX_READ)
    message = str(caught.value)
    assert "does not permit mailbox_read" in message
    # The reason, not just the refusal: it is why the §12 pre-conditions
    # do not apply, and somebody widening the scope has to meet it.
    assert "no PDPL lawful basis is documented" in message
    assert "Nothing is deleted" in message


def test_statutory_alerts_are_still_permitted():
    """The point of the scope. Everything else may be withheld; this may
    not, or there is nothing left."""
    from control.scope_statutory import STATUTORY_ALERTS

    assert permits(STATUTORY_ONLY, STATUTORY_ALERTS)


def test_the_summary_states_what_is_given_up():
    text = " ".join(" ".join(summary(STATUTORY_ONLY)).split())
    assert "class 1 statutory deadlines" in text
    assert "report chasing, external SLA, verdicts" in text
    # The exposure does not disappear because Control stops looking.
    assert "segregation-of-duties exposure" in text
    assert "Narrowing the software does not narrow it" in text


# ---- the cycle ---------------------------------------------------------

@pytest.fixture
def env(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    transport = control_root / "config" / "transport.yaml"
    transport.write_text(
        transport.read_text(encoding="utf-8").replace(
            "route: outlook_com", "route: graph", 1), encoding="utf-8")
    startup = run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2,
                          "2026-08-13", scope=STATUTORY_ONLY)
    return startup, control_root


def _enforcer():
    roster = {"accounts@ubcsis.com": Person("accounts@ubcsis.com", CEO, 3)}
    return Enforcer(WorkingCalendar(), roster, ceo=CEO, coo=COO, cfo=CFO)


def _vat():
    return TrackedItem(item_id="STAT-VAT", obligation_class=1,
                       name="VAT return and payment", owner=CFO,
                       due=date(2026, 8, 20))


def _weekly_report():
    return TrackedItem(item_id="OPS-WPR-001", obligation_class=3,
                       name="Weekly progress", owner="a.elsayed@ubcsis.com",
                       due=date(2026, 8, 13))


def test_the_mailbox_is_not_read(env):
    """Not skipped — not read. A message in the inbox is left there."""
    startup, control_root = env
    transport = MockTransport([FetchedMessage(
        message_id="<s1@ubcsis.com>", sender="a.elsayed@ubcsis.com",
        received_at=datetime(2026, 8, 13, 9, 0), subject="Weekly progress",
        attachments=[("FRM-WPR_w33.xlsx", b"not read")])])

    report = run_cycle(startup, transport, control_root, specs={},
                       tracked_items=[_vat()], enforcer=_enforcer(),
                       today=date(2026, 8, 13), ceo=CEO, cfo=CFO)

    assert report.processed == 0
    assert report.verdicts == {}


def test_not_reading_the_mailbox_is_stated_as_a_gap(env):
    """A narrowed scope that leaves no trace in the cycle's own output
    reads as a full sweep that found nothing (§1.1)."""
    startup, control_root = env
    report = run_cycle(startup, MockTransport([]), control_root, specs={},
                       tracked_items=[_vat()], enforcer=_enforcer(),
                       today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    gaps = " ".join(report.gaps)
    assert "Mailbox not read" in gaps
    assert "that is the scope, not a quiet week" in gaps


def test_the_class_1_alert_still_fires(env):
    """The whole point. Class 1 computes from the calendar, not the
    inbox, so it must survive the mailbox being closed."""
    startup, control_root = env
    transport = MockTransport([])
    report = run_cycle(startup, transport, control_root, specs={},
                       tracked_items=[_vat()], enforcer=_enforcer(),
                       today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert transport.outgoing or report.drafted, \
        "a statutory-only run produced no statutory alert"


def test_the_class_3_ladder_does_not_run(env):
    startup, control_root = env
    transport = MockTransport([])
    run_cycle(startup, transport, control_root, specs={},
              tracked_items=[_weekly_report()], enforcer=_enforcer(),
              today=date(2026, 8, 20), ceo=CEO, cfo=CFO)
    for message in transport.outgoing:
        assert "OPS-WPR-001" not in str(message)


def test_the_withholding_is_written_to_the_audit_chain(env):
    """§1.9. A capability withheld without a record is indistinguishable
    from one that was never asked for."""
    startup, control_root = env
    run_cycle(startup, MockTransport([]), control_root, specs={},
              tracked_items=[_vat()], enforcer=_enforcer(),
              today=date(2026, 8, 13), ceo=CEO, cfo=CFO)

    ok, detail = startup.audit.verify()
    assert ok, detail
    import json
    entries = [json.loads(line)
               for path in sorted((control_root / "logs").glob("*.jsonl"))
               for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    assert any(e["event"] == "scope.mailbox_read_withheld" for e in entries)
    assert any(e["event"] == "startup"
               and e["data"].get("scope") == STATUTORY_ONLY for e in entries)
