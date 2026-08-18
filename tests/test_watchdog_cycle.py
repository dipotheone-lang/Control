"""The external watchdog, wired into the cycle — §8.5, finding V7.

`Watchdog` was built and tested. Nothing called it. `EXTERNAL_INBOUND`
fell into the cycle's "logged, not acted on" branch, so no thread was
ever opened, no SLA deadline was ever computed, no notice was ever
planned, and the report's SLA section read an empty table forever. The
CC-compliance metric — standing evidence for the §3.1a scope question —
measured nothing.

The link it was missing is a thread id. Graph selected `conversationId`
and discarded it; Outlook never read `ConversationID`. Without one, a
reply cannot be matched to the message it answers, which is exactly what
§8.5 means by closing on an observed reply.

What these tests hold: a thread opens, a visible reply closes it, a
`CLOSED` declaration closes it and is recorded as a different kind of
evidence, a breach notice reaches the owner and never the external
party, and the wording stays what V7 required — *no reply visible to
Control*, never *no reply sent*.
"""

import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from control.calendar import WorkingCalendar
from control.cycle import run_cycle
from control.db import connect
from control.startup import run_startup
from control.transport import FetchedMessage, MockTransport
from control.watchdog import Watchdog, parse_sla_config

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO, CFO = "ahmed@ubcsis.com", "ghareeb@ubcsis.com", "accounts@ubcsis.com"
CLIENT = "Procurement <buyer@enova.example>"


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
                          "2026-08-13")
    return startup, control_root


def inbound(sender=CLIENT, *, thread="T-1", at="2026-08-10T09:00:00",
            first_line="", message_id=None):
    return FetchedMessage(
        message_id=message_id or f"MSG-{thread}-{at}",
        sender=sender, received_at=datetime.fromisoformat(at),
        to="control@ubcsis.com", subject="Quotation request",
        first_line=first_line, thread_id=thread)


def _watchdog(startup, conn, config=None):
    return Watchdog(
        conn,
        parse_sla_config(config or startup.config["sla"]["external_sla"]),
        WorkingCalendar(),
        {"ghareeb@ubcsis.com": CEO, "donia@ubcsis.com": "info@ubcsis.com"},
    )


def sweep(env, messages, *, today=date(2026, 8, 13), config=None):
    """One cycle, then a fresh watchdog to inspect what it left.

    `run_cycle` owns and closes its connection, so the state has to be
    read back rather than held — which is the same thing the next
    sweep does, and therefore the more honest thing to assert on.
    """
    startup, control_root = env
    conn = connect(startup.db_path)
    try:
        result = run_cycle(
            startup, MockTransport(messages), control_root, specs={},
            watchdog=_watchdog(startup, conn, config), today=today,
            ceo=CEO, cfo=CFO, coo=COO)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    after = connect(startup.db_path)
    return result, _watchdog(startup, after, config)


# ---- threads open ------------------------------------------------------

def test_external_mail_opens_a_thread(env):
    result, _ = sweep(env, [inbound()])
    assert result.threads_opened == 1


def test_internal_mail_opens_nothing(env):
    result, _ = sweep(env, [inbound(sender="Hadeer <hadeer@ubcsis.com>")])
    assert result.threads_opened == 0


def test_a_thread_is_opened_once_however_many_messages_arrive(env):
    """A conversation is the unit, not a message."""
    result, watchdog = sweep(env, [
        inbound(at="2026-08-10T09:00:00"),
        inbound(at="2026-08-10T11:00:00", message_id="MSG-2"),
    ])
    assert result.threads_opened == 2          # both registered...
    assert watchdog.open_threads() == ["T-1"]  # ...as one thread


def test_a_message_with_no_thread_id_is_counted_not_dropped(env):
    """Old Outlook items and non-Exchange stores leave it empty."""
    result, watchdog = sweep(env, [inbound(thread="")])
    assert result.threads_without_id == 1
    assert len(watchdog.open_threads()) == 1


# ---- threads close -----------------------------------------------------

def test_a_visible_internal_reply_closes_the_thread(env):
    _, watchdog = sweep(env, [
        inbound(),
        inbound(sender="Donia <donia@ubcsis.com>", at="2026-08-10T10:00:00",
                message_id="MSG-REPLY"),
    ])
    assert watchdog.open_threads() == []
    assert watchdog.cc_compliance()["CLOSED_OBSERVED_REPLY"] == 1


def test_a_closed_declaration_closes_it_and_records_who_declared(env):
    """§8.5 distinguishes a seen reply from a declared one on purpose."""
    _, watchdog = sweep(env, [
        inbound(),
        inbound(sender="Donia <donia@ubcsis.com>", at="2026-08-10T10:00:00",
                first_line="CLOSED — answered by phone", message_id="MSG-C"),
    ])
    assert watchdog.open_threads() == []
    metric = watchdog.cc_compliance()
    assert metric["CLOSED_DECLARED"] == 1
    assert metric["CLOSED_OBSERVED_REPLY"] == 0


def test_the_cc_compliance_share_separates_the_two(env):
    """The §3.1a evidence: how much Control sees versus is told."""
    _, watchdog = sweep(env, [
        inbound(thread="T-1"),
        inbound(sender="Donia <donia@ubcsis.com>", thread="T-1",
                at="2026-08-10T10:00:00", message_id="A"),
        inbound(thread="T-2", at="2026-08-10T09:30:00", message_id="B"),
        inbound(sender="Donia <donia@ubcsis.com>", thread="T-2",
                at="2026-08-10T10:30:00", first_line="CLOSED", message_id="C"),
    ])
    assert watchdog.cc_compliance()["observed_share"] == 0.5


# ---- breaches ----------------------------------------------------------

def test_a_breach_notice_goes_to_the_owner_and_never_the_external_party(env):
    """§8.5: notices go to the internal owner, and their manager after
    the first breach. Never to the party waiting for the reply."""
    import json

    _, control_root = env
    result, _ = sweep(env, [inbound(at="2026-08-03T09:00:00")])
    assert result.sent

    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in (control_root / "outbox" / "sent").glob("*.json")]
    notices = [r for r in records if r.get("kind") == "WATCHDOG_NOTICE"]
    assert notices

    for notice in notices:
        addresses = notice["recipients"] + notice["cc"]
        external = [a for a in addresses
                    if not a.endswith("@ubcsis.com")
                    and a != "contact.ubcsis@gmail.com"]
        assert external == [], f"notice addressed outside the company: {external}"
        assert "enova.example" not in json.dumps(notice)


def test_the_notice_says_what_control_can_honestly_claim(env):
    """V7: under Option A a missing reply may only be invisible."""
    _, control_root = env
    sweep(env, [inbound(at="2026-08-03T09:00:00")])
    bodies = "".join(p.read_text(encoding="utf-8")
                     for p in (control_root / "outbox" / "sent").glob("*.json"))
    assert "no reply visible to Control" in bodies
    assert "no reply sent" not in bodies


def test_a_thread_within_sla_produces_no_notice(env):
    result, _ = sweep(env, [inbound(at="2026-08-13T09:00:00")])
    assert not any("WD:" in key for key in result.sent)


def test_a_breach_notice_is_not_repeated_on_the_next_sweep(env):
    """§1.10 — the register is checked before every send."""
    first, _ = sweep(env, [inbound(at="2026-08-03T09:00:00")])
    assert any("WD:" in key for key in first.sent)

    second, _ = sweep(env, [])
    assert not any("WD:" in key for key in second.sent)


# ---- no configuration, no theatre --------------------------------------

def test_no_external_sla_means_no_watchdog(env):
    """A watchdog with no rules breaches nothing while looking live."""
    from control.__main__ import _watchdog_for

    startup, _ = env
    startup.config.data["sla"] = {}

    class Loaded:
        roster = {}
        calendar = WorkingCalendar()

    assert _watchdog_for(startup, None, Loaded()) is None
