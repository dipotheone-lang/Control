import json

import pytest

from control.outbox import (
    ApprovalAuthenticationError,
    BACKUP_CC,
    GateViolation,
    Outbox,
    OutboundMessage,
    decide,
)

CEO = "ahmed@ubcsis.com"


def msg(**kw):
    base = dict(
        kind="VERDICT_REPLY",
        subject="[CONTROL] ACCEPTED — Weekly — W32 — Elsayed",
        body="…bilingual body…",
        recipients=["a.elsayed@ubcsis.com"],
        dedupe_key="OPS-WPR-001:VERDICT:W32",
        rationale="Verdict on weekly progress W32",
    )
    base.update(kw)
    return OutboundMessage(**base)


@pytest.fixture
def outbox_live(tmp_path):
    return Outbox(tmp_path, "LIVE", ceo=CEO)


@pytest.fixture
def outbox_supervised(tmp_path):
    return Outbox(tmp_path, "SUPERVISED", ceo=CEO)


# -- gate table ----------------------------------------------------------

def test_gate_matrix_spot_checks():
    assert decide("VERDICT_REPLY", "SUPERVISED") == "DRAFT"
    assert decide("VERDICT_REPLY", "LIVE") == "SEND"
    assert decide("CLASS12_ALERT", "SUPERVISED") == "SEND"
    assert decide("CEO_ESCALATION_L3", "LIVE") == "DRAFT"      # permanently gated
    assert decide("MANAGEMENT_REPORT", "LIVE") == "DRAFT"      # permanently gated
    assert decide("FRAUD_FLAG", "SUPERVISED") == "SEND"
    assert decide("CLASS3_REMINDER", "DISCOVERY") == "DRAFT"   # discovery sends nothing


def test_unknown_kind_never_passes():
    with pytest.raises(GateViolation):
        decide("COMMITMENT", "LIVE")


def test_external_recipient_blocked_in_every_mode(outbox_live):
    with pytest.raises(GateViolation, match="external"):
        outbox_live.submit(msg(recipients=["supplier@steelworks.net"]))


# -- continuity CC (D-04) ------------------------------------------------

def test_backup_cc_appended_on_routine_send(outbox_live):
    d = outbox_live.submit(msg())
    assert d.action == "SEND"
    assert BACKUP_CC in d.message.cc


def test_backup_cc_withheld_on_excluded_classes(outbox_supervised):
    d = outbox_supervised.submit(
        msg(kind="FRAUD_FLAG", recipients=[CEO, "accounts@ubcsis.com"],
            content_classes={"SUSPECTED_FRAUD", "S1"},
            dedupe_key="FRAUD-1")
    )
    assert d.action == "SEND"
    assert BACKUP_CC not in d.message.cc


def test_backup_cc_withheld_on_confidential(outbox_live):
    d = outbox_live.submit(msg(content_classes={"CONFIDENTIAL_CLIENT"}))
    assert BACKUP_CC not in d.message.cc


# -- drafts and approval -------------------------------------------------

def test_draft_written_with_rationale_and_headers(outbox_supervised):
    d = outbox_supervised.submit(msg())
    assert d.action == "DRAFT"
    record = json.loads(open(d.draft_path, encoding="utf-8").read())
    assert record["status"] == "PENDING_APPROVAL"
    assert record["rationale"].startswith("Verdict")
    assert record["headers"]["To"] == ["a.elsayed@ubcsis.com"]


def test_authenticated_approval_releases(outbox_supervised):
    d = outbox_supervised.submit(msg())
    released = outbox_supervised.approve(
        d.draft_id,
        authenticated_sender=CEO,
        in_reply_to_draft=d.draft_id,
        reply_body=f"Approved: {d.draft_id}",
        message_id="<m1@ubcsis.com>",
    )
    assert released.dedupe_key == "OPS-WPR-001:VERDICT:W32"
    # moved pending -> sent
    assert not (outbox_supervised.pending / f"{d.draft_id}.json").exists()
    assert (outbox_supervised.sent_dir / f"{d.draft_id}.json").exists()


def test_wrong_sender_is_security_event(outbox_supervised):
    d = outbox_supervised.submit(msg())
    with pytest.raises(ApprovalAuthenticationError, match="not the CEO"):
        outbox_supervised.approve(
            d.draft_id,
            authenticated_sender="info@ubcsis.com",
            in_reply_to_draft=d.draft_id,
            reply_body=f"Approved: {d.draft_id}",
            message_id="<m2@ubcsis.com>",
        )
    assert (outbox_supervised.pending / f"{d.draft_id}.json").exists()  # stays pending


def test_out_of_thread_or_unquoted_approval_fails(outbox_supervised):
    d = outbox_supervised.submit(msg())
    with pytest.raises(ApprovalAuthenticationError, match="in-thread"):
        outbox_supervised.approve(
            d.draft_id, authenticated_sender=CEO, in_reply_to_draft=None,
            reply_body=f"Approved: {d.draft_id}", message_id="<m3@x>",
        )
    with pytest.raises(ApprovalAuthenticationError, match="quote"):
        outbox_supervised.approve(
            d.draft_id, authenticated_sender=CEO, in_reply_to_draft=d.draft_id,
            reply_body="Approved.", message_id="<m4@x>",
        )


# -- idempotency ---------------------------------------------------------

def test_duplicate_dedupe_key_skipped(outbox_live):
    already = {"OPS-WPR-001:VERDICT:W32"}
    d = outbox_live.submit(msg(), already_sent=already)
    assert d.action == "SKIPPED_DUPLICATE"
