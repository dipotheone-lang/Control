"""A cycle driven entirely from configuration — Phase 1's actual shape.

Everything before this was tested from hand-built objects. This runs
the real path: `config/*.yaml` on disk, through the loader, through
`run_cycle`, against a transport, with the §10 gates deciding what
sends and what waits.

The two claims worth proving are the ones a Phase 1 gate depends on:
in DRY_RUN **nothing sends**, and an obligation the CEO has not
approved changes nothing about the run.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from control.cycle import run_cycle
from control.db import connect
from control.enforce import Enforcer
from control.loader import load_class2, load_for_cycle
from control.startup import run_startup
from control.transport import FetchedMessage, MailTransport

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO, CFO = ("ahmed@ubcsis.com", "ghareeb@ubcsis.com",
                 "accounts@ubcsis.com")
OWNER = "a.elsayed@ubcsis.com"
TODAY = date(2026, 8, 20)          # Thursday


class Recorder(MailTransport):
    """Records sends so 'nothing sent' can be proved, not assumed."""

    def __init__(self, inbox=None):
        self.inbox = inbox or []
        self.sent: list[tuple] = []
        self.processed: list[str] = []

    def fetch_unprocessed(self):
        return self.inbox

    def send(self, recipients, cc, subject, body):
        self.sent.append((recipients, cc, subject))
        return f"<sent-{len(self.sent)}>"

    def mark_processed(self, message_ids):
        self.processed.extend(
            message_ids if isinstance(message_ids, list) else [message_ids])


OBLIGATION = {
    "id": "OPS-WPR-001",
    "class": 3,
    "name": "Weekly progress report",
    "owner": OWNER,
    "form": "FRM-WPR-01 rev 3",
    "cadence": "weekly",
    # Explicit and in the past, so the ladder is at a known stage rather
    # than depending on which weekday the suite runs.
    "due": "2026-08-16 10:00",
    "approved_by_ceo": CEO,
    "mandatory_fields": ["B12"],
}


def build_root(tmp_path, *, obligations, run_mode="DRY_RUN"):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")

    (control_root / "config" / "obligations.yaml").write_text(
        yaml.safe_dump({"obligations": obligations}), encoding="utf-8")
    if run_mode in ("SUPERVISED", "LIVE"):
        # D-08 refuses the interim Outlook route beyond DRY_RUN.
        transport = control_root / "config" / "transport.yaml"
        transport.write_text(
            transport.read_text(encoding="utf-8").replace(
                "route: outlook_com", "route: graph", 1), encoding="utf-8")

    level = {"DRY_RUN": 1, "SUPERVISED": 2}[run_mode]
    startup = run_startup(control_root, ub_root, run_mode, "OBSERVE", level,
                          TODAY.isoformat())
    return startup, control_root


def run(startup, control_root, transport, today=TODAY):
    conn = connect(startup.db_path)
    try:
        loaded = load_for_cycle(startup.config, conn, today)
        return loaded, run_cycle(
            startup, transport, control_root,
            specs=loaded.specs,
            tracked_items=loaded.tracked + load_class2(conn),
            class3_state=loaded.class3_state,
            enforcer=Enforcer(loaded.calendar, loaded.roster,
                              ceo=CEO, coo=COO, cfo=CFO),
            today=today, ceo=CEO, cfo=CFO, coo=COO)
    finally:
        conn.close()


# ---- the Phase 1 claim -----------------------------------------------

def test_dry_run_sends_nothing_at_all(tmp_path):
    """The whole point of Phase 1. Proved against a recording transport
    rather than inferred from the gate table."""
    startup, control_root = build_root(tmp_path, obligations=[OBLIGATION])
    transport = Recorder()
    loaded, result = run(startup, control_root, transport)

    assert loaded.approved == 1
    assert transport.sent == []
    assert result.sent == []
    assert result.drafted                      # it did produce work
    pending = list((control_root / "outbox" / "pending-approval").glob("*.json"))
    assert pending, "an overdue item should have drafted a reminder"


def test_the_drafts_are_real_bilingual_messages(tmp_path):
    startup, control_root = build_root(tmp_path, obligations=[OBLIGATION])
    run(startup, control_root, Recorder())
    record = json.loads(
        next((control_root / "outbox" / "pending-approval").glob("*.json"))
        .read_text(encoding="utf-8"))
    assert record["status"] != "APPROVED"
    assert record["headers"]["To"]
    assert record["rationale"]


DUE_TODAY = dict(OBLIGATION, id="OPS-DPR-001", name="Daily progress report",
                 due="2026-08-20 10:00")


def test_supervised_sends_the_reminder_and_drafts_the_escalation(tmp_path):
    """§10's gate table, exercised end to end rather than unit-tested.

    Two items, deliberately at different ladder stages: one due today,
    one four working days late. In SUPERVISED the deadline reminder
    SENDS and the L2 escalation DRAFTS. Both in one run, so the
    distinction is proved rather than assumed from the table.
    """
    startup, control_root = build_root(
        tmp_path, obligations=[OBLIGATION, DUE_TODAY], run_mode="SUPERVISED")
    transport = Recorder()
    _, result = run(startup, control_root, transport)

    assert transport.sent, "a deadline reminder sends in SUPERVISED"
    assert result.drafted, "an L2 escalation still drafts in SUPERVISED"

    # §10: nothing leaves the company, in any mode. The continuity CC is
    # the one scoped exception (D-04).
    for recipients, cc, _ in transport.sent:
        for address in list(recipients) + list(cc):
            assert (address.endswith("ubcsis.com")
                    or address == "contact.ubcsis@gmail.com")


# ---- what an unapproved register does --------------------------------

def test_an_unapproved_obligation_changes_nothing(tmp_path):
    """Phase 0 ends on CEO approval (§6). Until then the cycle runs and
    tracks nothing — and says which obligation it skipped."""
    unapproved = dict(OBLIGATION, approved_by_ceo=None)
    startup, control_root = build_root(tmp_path, obligations=[unapproved])
    transport = Recorder()
    loaded, result = run(startup, control_root, transport)

    assert loaded.approved == 0
    assert result.drafted == []
    assert transport.sent == []
    assert any("OPS-WPR-001" in gap and "not approved" in gap
               for gap in loaded.gaps)


def test_the_empty_repo_register_runs_without_pretending(tmp_path):
    startup, control_root = build_root(tmp_path, obligations=[])
    loaded, result = run(startup, control_root, Recorder())
    assert loaded.approved == 0
    assert result.processed == 0
    assert any("empty register" in gap for gap in loaded.gaps)


# ---- inbound ----------------------------------------------------------

def test_a_spoofed_sender_flags_to_ceo_and_cfo_and_never_replies(tmp_path):
    startup, control_root = build_root(tmp_path, obligations=[OBLIGATION])
    # A near-miss of a domain the repo config already knows.
    spoof = FetchedMessage(
        message_id="<evil>", sender="accounts@enova-rne.com",
        to="control@ubcsis.com", cc="", subject="Updated bank details",
        first_line="Please update our account", received_at=None,
        attachments=[], in_reply_to_control=False)
    spoof.received_at = __import__("datetime").datetime(2026, 8, 20, 11, 0)

    transport = Recorder([spoof])
    _, result = run(startup, control_root, transport)

    assert result.security_events == ["<evil>"]
    flags = [json.loads(p.read_text(encoding="utf-8"))
             for p in (control_root / "outbox" / "pending-approval").glob("*.json")]
    fraud = [f for f in flags if f["kind"] == "FRAUD_FLAG"]
    assert fraud, "a spoofed sender must produce a flag"
    to = fraud[0]["headers"]["To"]
    assert set(to) == {CEO, CFO}
    assert "enova-rne.com" not in " ".join(to)      # never a reply
    # D-04: the continuity CC never carries a fraud flag.
    assert fraud[0]["headers"]["Cc"] == []


def test_an_unknown_sender_is_not_evaluated(tmp_path):
    """§13.2: new joiner or impersonation — either way, not judged."""
    startup, control_root = build_root(tmp_path, obligations=[OBLIGATION])
    stranger = FetchedMessage(
        message_id="<who>", sender="someone@unknown-counterparty.eg",
        to="control@ubcsis.com", cc="", subject="Weekly progress report",
        first_line="attached", received_at=None,
        attachments=[], in_reply_to_control=False)
    stranger.received_at = __import__("datetime").datetime(2026, 8, 20, 9, 0)

    _, result = run(startup, control_root, Recorder([stranger]))
    assert result.verdicts == {}


# ---- the record ------------------------------------------------------

def test_the_cycle_writes_a_verifiable_audit_chain(tmp_path):
    from control.audit import AuditLog

    startup, control_root = build_root(tmp_path, obligations=[OBLIGATION])
    run(startup, control_root, Recorder())
    ok, detail = AuditLog(control_root / "logs").verify()
    assert ok, detail


def test_a_second_run_does_not_repeat_itself(tmp_path):
    """§1.10 idempotency: the register is checked before every send."""
    startup, control_root = build_root(tmp_path, obligations=[OBLIGATION])
    _, first = run(startup, control_root, Recorder())
    _, second = run(startup, control_root, Recorder())
    assert first.drafted
    assert second.drafted == []
    assert second.skipped_duplicates >= 1
