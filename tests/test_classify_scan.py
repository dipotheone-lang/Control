"""§9 classification over scan metadata — the honest-gap behaviour."""

from control.classify import Classifier
from control.discovery.classify_scan import (
    BODY_DEPENDENT, build_classifier, classify_rows, merge, render,
)


class FakeConfig:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, name):
        return self.data[name]


def _config(*, domains=None, obligations=None):
    return FakeConfig({
        "people": {"people": [
            {"email": "ahmed@ubcsis.com", "tier": 4},
            {"email": "donia@ubcsis.com", "tier": 2},
        ]},
        "confidential": {"confidential_clients": [
            {"name": "KNAUF", "domains": domains or []},
        ]},
        "obligations": {"obligations": obligations or []},
    })


def _row(**kw):
    row = {"mailbox": "control@ubcsis.com", "folder": "Inbox",
           "sender": "someone@example.com", "to": "control@ubcsis.com",
           "cc": "", "received": "2026-08-01T09:00:00", "subject": "Hello",
           "attachments": []}
    row.update(kw)
    return row


def test_empty_register_and_domains_are_reported_not_silently_defaulted():
    _, limitations = build_classifier(_config())
    joined = " ".join(limitations)
    assert "obligations.yaml is empty" in joined
    assert "OBLIGATION_SUBMISSION therefore cannot be produced" in joined
    assert "no domains populated" in joined or "no domains" in joined


def test_populated_register_produces_no_register_limitation():
    _, limitations = build_classifier(_config(
        domains=["knauf.com"],
        obligations=[{"id": "OPS-WPR-001", "form": "UB-WPR"}],
    ))
    assert not any("obligations.yaml is empty" in n for n in limitations)


def test_dispute_marker_in_subject_does_not_produce_a_dispute():
    """The marker is the first line of the BODY (§8.4). Metadata has no
    body, so DISPUTE must stay unreachable rather than be approximated
    from the subject — a guessed dispute suspends an escalation clock."""
    classifier, _ = build_classifier(_config())
    report = classify_rows(
        [_row(sender="donia@ubcsis.com", subject="DISPUTE — weekly report")],
        classifier,
    )
    assert "DISPUTE" not in report.by_category


def test_internal_attachment_falls_to_unscheduled_when_register_is_empty():
    classifier, _ = build_classifier(_config())
    report = classify_rows(
        [_row(sender="donia@ubcsis.com", attachments=["UB-WPR rev2.xlsx"])],
        classifier,
    )
    assert report.by_category["UNSCHEDULED_SUBMISSION"] == 1


def test_internal_sender_off_roster_is_ambiguous_never_evaluated():
    classifier, _ = build_classifier(_config())
    report = classify_rows([_row(sender="newjoiner@ubcsis.com")], classifier)
    assert report.by_category["AMBIGUOUS"] == 1


def test_backup_address_is_its_own_category():
    classifier, _ = build_classifier(_config())
    report = classify_rows(
        [_row(sender="contact.ubcsis@gmail.com", mailbox="sales@ubcsis.com")],
        classifier,
    )
    assert report.by_category["BACKUP_CHANNEL"] == 1


def test_near_miss_domain_is_a_security_event_carrying_its_evidence():
    classifier = Classifier(
        roster_emails={"ahmed@ubcsis.com"},
        known_domains={"knauf.com"},
    )
    report = classify_rows([_row(sender="billing@knauf.co")], classifier)
    assert report.by_category["SUSPECTED_FRAUD"] == 1
    assert len(report.security_events) == 1
    assert "near-miss" in " ".join(report.security_events[0].reasons)


def test_redacted_subjects_are_counted_so_silence_is_attributable():
    classifier, _ = build_classifier(_config())
    report = classify_rows(
        [_row(mailbox="hr@ubcsis.com", subject="[REDACTED]")], classifier)
    assert report.redacted_subjects == 1


def test_merge_sums_counts_and_dedupes_limitations():
    classifier, limitations = build_classifier(_config())
    a = classify_rows([_row(sender="a@example.com")], classifier)
    b = classify_rows([_row(sender="b@example.com")], classifier)
    a.limitations = list(limitations)
    b.limitations = list(limitations)
    merged = merge([a, b])
    assert merged.rows == 2
    assert merged.by_category["EXTERNAL_INBOUND"] == 2
    assert merged.limitations == limitations


def test_render_names_unreachable_categories_rather_than_showing_zero():
    classifier, limitations = build_classifier(_config())
    report = classify_rows([_row()], classifier)
    report.limitations = limitations
    text = render(report)
    for category in BODY_DEPENDENT:
        assert category in text
    assert "not detectable from metadata" in text
    assert "structurally unavailable" in text
    # A zero must never be presented as an all-clear.
    assert "not as an all-clear" in text
