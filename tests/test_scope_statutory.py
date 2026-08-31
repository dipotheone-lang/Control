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


# ---- the transport itself ---------------------------------------------
#
# The three tests above cover what the cycle does with a transport it is
# handed. They passed while the command that builds one still opened a
# mailbox: `OutlookTransport` and `GraphTransport` both sign in when they
# are constructed, so a scope enforced only at the fetch had already done
# the thing §12.2 governs before deciding not to look.

def _report(scope=STATUTORY_ONLY, route="outlook_com"):
    from types import SimpleNamespace

    return SimpleNamespace(
        scope=scope,
        config={"transport": {"route": route},
                "mailbox-scope": {"control_mailbox": "control@ubcsis.com"}})


def test_a_scope_that_neither_reads_nor_sends_gets_no_transport(monkeypatch):
    """Not 'must not fetch' — must not connect. Opening the mailbox is
    the processing; reading a message afterwards is a second act."""
    from types import SimpleNamespace

    from control import scope_statutory
    from control.__main__ import _transport_for
    from control.transport import NullTransport

    # D-58 gave this scope sending. Withdraw it and the old contract
    # must still hold: no transport is constructed at all.
    monkeypatch.setitem(scope_statutory._WITHHELD,
                        scope_statutory.TRANSPORT_SEND, "is withdrawn here")
    transport = _transport_for(_report(), SimpleNamespace(allow_send=False))

    assert isinstance(transport, NullTransport)
    assert transport.fetch_unprocessed() == []


def test_a_send_only_scope_falls_back_instead_of_aborting_the_run():
    """D-58 makes Outlook the whole route, and Outlook is closed whenever
    the laptop is. Returning None there produced no alert, no record and
    nothing to retry — the run did nothing and called it a transport
    problem. It must degrade to a retryable non-delivery instead.

    (Outlook cannot be constructed in this environment, which is exactly
    the condition under test.)
    """
    from types import SimpleNamespace

    from control.__main__ import _transport_for
    from control.transport import NullTransport

    transport = _transport_for(_report(), SimpleNamespace(allow_send=False))
    assert isinstance(transport, NullTransport)
    assert transport.can_send is False


def test_a_reading_scope_still_aborts_when_the_transport_is_absent():
    """§5.1: an incomplete sweep is a FAILED cycle. Absences recorded
    from a partial view are not absences, so the fallback above must not
    apply where the mailbox is actually read."""
    from types import SimpleNamespace

    from control.__main__ import _transport_for

    assert _transport_for(_report(scope="FULL"),
                          SimpleNamespace(allow_send=False)) is None


def test_the_null_transport_refuses_to_send_rather_than_swallowing_it():
    """A transport that returned quietly would turn a delivered class 1
    alert into a silent one — the failure D-08 refuses a laptop
    transport over, arriving from inside."""
    from control.transport import NullTransport

    with pytest.raises(HaltError) as excinfo:
        NullTransport().send([CFO], [], "subject", "body")
    assert "Graph" in str(excinfo.value)


def test_a_class_1_alert_with_nowhere_to_go_is_reported_not_lost(env):
    """SUPERVISED sends class 1 alerts (§10). With no Graph there is
    nowhere to send them.

    Two responses are wrong. Raising kills a run with other work to
    finish. Writing an ordinary PENDING_APPROVAL draft turns an alert
    §10 required into one nobody knows was never delivered. So it is
    written, marked, and counted apart — a draft the mode asked for is
    the system working; a draft standing in for a send nobody received
    is not.
    """
    import json

    from control.transport import NullTransport

    startup, control_root = env
    report = run_cycle(startup, NullTransport(), control_root, specs={},
                       tracked_items=[_vat()], enforcer=_enforcer(),
                       today=date(2026, 8, 13), ceo=CEO, cfo=CFO)

    assert report.undelivered, "the class 1 alert vanished"
    assert not report.sent
    assert not report.drafted, "an undelivered send was counted as a draft"

    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in (control_root / "outbox" / "pending-approval")
               .glob("*.json")]
    assert [r["status"] for r in records] == ["UNDELIVERED_NO_TRANSPORT"]

    entries = [json.loads(line)
               for path in sorted((control_root / "logs").glob("*.jsonl"))
               for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    assert any(e["event"] == "outbox.undelivered" for e in entries)


def test_the_charter_s_own_state_for_d15_can_actually_be_entered(env):
    """§16 lists STATUTORY_ONLY at level 2, SUPERVISED, OBSERVE.

    D-08's route gate refused Outlook in SUPERVISED and so refused that
    row — the charter declared a state legal that the code would not
    enter. The gate exists to stop a laptop transport carrying a send
    schedule and to stop it seeing more mailboxes than D-07 authorises;
    a scope that opens no mailbox and sends through no route does
    neither.
    """
    startup, _ = env
    assert startup.state.run_mode == "SUPERVISED"
    assert startup.scope == STATUTORY_ONLY


def test_the_route_gate_still_refuses_the_wide_scope(tmp_path):
    """The relaxation is bounded by the scope, not removed. With a
    mailbox in play D-08 refuses exactly as before."""
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")

    with pytest.raises(HaltError) as excinfo:
        run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2,
                    "2026-08-13", scope="FULL")
    assert "not permitted in RUN_MODE=SUPERVISED" in str(excinfo.value)


def test_the_same_run_drafts_instead_of_halting_in_dry_run(tmp_path):
    """§10 drafts in DRY_RUN, so the identical run completes and the
    alert lands in outbox/pending-approval — which is what the machine
    can do today, before Graph."""
    from control.transport import NullTransport

    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    startup = run_startup(control_root, ub_root, "DRY_RUN", "OBSERVE", 1,
                          "2026-08-13", scope=STATUTORY_ONLY)

    report = run_cycle(startup, NullTransport(), control_root, specs={},
                       tracked_items=[_vat()], enforcer=_enforcer(),
                       today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert report.drafted, "no class 1 draft was produced"
    assert not report.sent


def test_an_unreachable_ub_root_does_not_stop_a_class_1_run(tmp_path):
    """§13.2 halts on an unreachable UB_ROOT to avoid operating on a
    partial view. A scope that reads no drive has no view to be partial,
    and halting would stop the statutory run because a USB disk is
    unplugged. It proceeds, and says it proceeded."""
    ub_root = tmp_path / "UB"
    control_root = tmp_path / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    assert not ub_root.exists()

    startup = run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2,
                          "2026-08-13", scope=STATUTORY_ONLY)
    assert startup.gaps, "proceeding past a halt condition left no trace"
    assert "UB_ROOT unreachable" in startup.gaps[0]
    assert "a widened scope halts on this again" in startup.gaps[0]


def test_the_wide_scope_still_halts_on_an_unreachable_ub_root(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = tmp_path / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")

    with pytest.raises(HaltError) as excinfo:
        run_startup(control_root, ub_root, "DRY_RUN", "OBSERVE", 1,
                    "2026-08-13", scope="FULL")
    assert "UB_ROOT unreachable" in str(excinfo.value)


def test_proceeding_past_a_halt_condition_is_logged(tmp_path):
    """§1.9. An unlogged decision did not happen, and this run made
    one."""
    import json

    ub_root = tmp_path / "UB"
    control_root = tmp_path / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2,
                "2026-08-13", scope=STATUTORY_ONLY)

    entries = [json.loads(line)
               for path in sorted((control_root / "logs").glob("*.jsonl"))
               for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    startup = next(e for e in entries if e["event"] == "startup")
    assert any("UB_ROOT unreachable" in g
               for g in startup["data"]["proceeded_past"])


def test_an_undelivered_alert_is_retried_on_the_next_run(env):
    """The defect D-58 makes critical.

    An UNDELIVERED record sits in outbox/pending-approval, and
    `known_dedupe_keys` counted every pending record as already handled.
    So a laptop closed on T-7 wrote one undelivered alert and then
    silenced T-3, T-1 and the deadline itself — each later run skipping
    it as a duplicate and reporting a clean sweep (§2.1, §1.1).
    """
    from control.transport import NullTransport

    startup, control_root = env
    for _ in range(3):
        report = run_cycle(startup, NullTransport(), control_root, specs={},
                           tracked_items=[_vat()], enforcer=_enforcer(),
                           today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
        assert report.undelivered, "the alert stopped being attempted"
        assert not report.skipped_duplicates

    # And the run says it is a repeat rather than a first miss: three
    # failures means the transport is not merely asleep.
    assert report.repeatedly_undelivered
    assert "3 failed attempts" in report.repeatedly_undelivered[0]


def test_a_delivered_alert_is_still_not_sent_twice(env):
    """The relaxation is bounded. Idempotency (§1.10) still holds for a
    message that actually reached somebody."""
    startup, control_root = env
    transport = MockTransport([])

    first = run_cycle(startup, transport, control_root, specs={},
                      tracked_items=[_vat()], enforcer=_enforcer(),
                      today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    second = run_cycle(startup, transport, control_root, specs={},
                       tracked_items=[_vat()], enforcer=_enforcer(),
                       today=date(2026, 8, 13), ceo=CEO, cfo=CFO)

    assert first.sent and not second.sent
    assert second.skipped_duplicates
