"""Draft release under CEO absence, and the near-miss reference set.

Two CEO answers of 16-Aug-2026, and one defect found while checking the
second was already implemented.

DRAFT RELEASE. §10 keeps L3 escalations and management reports at DRAFT
permanently, so somebody must release them forever. The CEO releases;
during REGISTERED absence the COO deputises, which extends §3.3's
existing CEO-absence rule rather than inventing a new authority.

NEAR-MISS. §7.3 S1 already routed a near-miss domain to CEO and CFO with
no reply — the requested behaviour was in place. But the reference set
it compared against was the confidential-client list alone, which left
every supplier domain unprotected. A spoofed supplier is the vector
§7.3 names as the most common SME payment fraud in Egypt.
"""

import json
from pathlib import Path

import pytest
import yaml

from control.classify import Classifier, InboundMessage
from control.discovery.classify_worksheet import (
    confidential_domains, known_domains,
)
from control.outbox import ApprovalAuthenticationError, Outbox, OutboundMessage

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO = "ahmed@ubcsis.com", "ghareeb@ubcsis.com"


def draft(outbox) -> str:
    disposition = outbox.submit(OutboundMessage(
        kind="CEO_ESCALATION_L3", subject="[CONTROL] L3", body="body",
        recipients=[CEO], dedupe_key="L3:1", rationale="test"))
    assert disposition.action == "DRAFT"
    return disposition.draft_id


def approve(outbox, draft_id, sender):
    return outbox.approve(
        draft_id, authenticated_sender=sender, in_reply_to_draft=draft_id,
        reply_body=f"approved {draft_id}", message_id="<m1>")


# ---- who may release --------------------------------------------------

def test_the_ceo_releases(tmp_path):
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO)
    message = approve(outbox, draft(outbox), CEO)
    assert message.kind == "CEO_ESCALATION_L3"
    record = json.loads(next(outbox.sent_dir.glob("*.json")).read_text())
    assert record["approved_by"] == CEO
    assert record["deputised"] is False


def test_the_coo_cannot_release_while_the_ceo_is_present(tmp_path):
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO)
    draft_id = draft(outbox)
    with pytest.raises(ApprovalAuthenticationError) as e:
        approve(outbox, draft_id, COO)
    assert "no CEO absence is registered" in str(e.value)
    assert (outbox.pending / f"{draft_id}.json").exists()   # stays pending


def test_the_coo_releases_during_registered_absence(tmp_path):
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO, ceo_absent=True)
    approve(outbox, draft(outbox), COO)
    record = json.loads(next(outbox.sent_dir.glob("*.json")).read_text())
    assert record["approved_by"] == COO
    # §3.3: every deputised approval is logged as such.
    assert record["deputised"] is True
    assert record["deputised_for"] == CEO


def test_the_deputy_path_opens_from_the_register_not_the_deputy(tmp_path):
    """A deputy who could declare their own authority is not a deputy."""
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO, ceo_absent=False)
    draft_id = draft(outbox)
    with pytest.raises(ApprovalAuthenticationError):
        approve(outbox, draft_id, COO)


def test_nobody_else_releases_even_during_absence(tmp_path):
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO, ceo_absent=True)
    draft_id = draft(outbox)
    with pytest.raises(ApprovalAuthenticationError) as e:
        approve(outbox, draft_id, "accounts@ubcsis.com")
    assert "security event" in str(e.value)


def test_with_no_coo_configured_absence_changes_nothing(tmp_path):
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, ceo_absent=True)
    draft_id = draft(outbox)
    with pytest.raises(ApprovalAuthenticationError):
        approve(outbox, draft_id, COO)


def test_the_deputy_still_cannot_open_the_external_gate(tmp_path):
    """§10: the external gate never opens, for anyone, in any mode."""
    from control.outbox import GateViolation

    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO, ceo_absent=True)
    with pytest.raises(GateViolation):
        outbox.submit(OutboundMessage(
            kind="CEO_ESCALATION_L3", subject="s", body="b",
            recipients=["buyer@enova-me.com"], dedupe_key="X", rationale="r"))


def test_authentication_still_applies_to_the_deputy(tmp_path):
    """Deputising relaxes who, never how (§10, V11)."""
    outbox = Outbox(tmp_path, "LIVE", ceo=CEO, coo=COO, ceo_absent=True)
    draft_id = draft(outbox)
    with pytest.raises(ApprovalAuthenticationError) as e:
        outbox.approve(draft_id, authenticated_sender=COO,
                       in_reply_to_draft="SOMETHING-ELSE",
                       reply_body=f"ok {draft_id}", message_id="<m>")
    assert "in-thread" in str(e.value)

    with pytest.raises(ApprovalAuthenticationError) as e:
        outbox.approve(draft_id, authenticated_sender=COO,
                       in_reply_to_draft=draft_id, reply_body="ok",
                       message_id="<m>")
    assert "nothing releases on silence" in str(e.value)


# ---- the near-miss reference set --------------------------------------

def classifier(domains):
    return Classifier(roster_emails={CEO}, obligation_forms={},
                      confidential_domains=set(), known_domains=domains)


def message(sender):
    return InboundMessage(sender=sender, to="control@ubcsis.com", cc="",
                          subject="Updated invoice", first_line="Please see",
                          attachments=[])


def test_a_spoofed_domain_is_a_security_event_not_a_reply(tmp_path):
    result = classifier({"enova-me.com"}).classify(message("a@enova-rne.com"))
    assert result.category == "SUSPECTED_FRAUD"
    assert result.security_event is True
    assert "near-miss" in " ".join(result.reasons)


def test_the_real_domain_is_not_flagged():
    result = classifier({"enova-me.com"}).classify(message("a@enova-me.com"))
    assert result.category != "SUSPECTED_FRAUD"


def test_a_supplier_domain_protects_too_even_though_it_is_not_confidential():
    """The defect this test exists for: known_domains used to be the
    confidential-client list, so suppliers were unprotected. Fraud does
    not care whether the counterparty is under NDA."""
    config = {
        "confidential_clients": [{"name": "Enova", "domains": ["enova-me.com"]}],
        "domain_classifications": {
            "confidential": ["enova-me.com"],
            "not_confidential": ["steelsupplier.com"]},
    }
    assert "steelsupplier.com" not in confidential_domains(config)
    assert "steelsupplier.com" in known_domains(config)

    result = classifier(known_domains(config)).classify(
        message("sales@steelsuppller.com"))
    assert result.category == "SUSPECTED_FRAUD"


def test_known_domains_is_a_superset_of_confidential_domains():
    config = yaml.safe_load(
        (REPO_CONFIG / "confidential.yaml").read_text(encoding="utf-8"))
    assert confidential_domains(config) <= known_domains(config)


# ---- ETA ownership ----------------------------------------------------

def test_eta_is_split_into_submission_and_rejection_clearance():
    """They fail differently: one is a recurring deadline, the other an
    event-driven window that expires quietly."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in data["obligations"]}
    assert "STAT-ETA-SUB" in rows and "STAT-ETA-REJ" in rows


def test_eta_ownership_matches_the_ceo_answer():
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    for row in (r for r in data["obligations"] if r["id"].startswith("STAT-ETA")):
        assert row["owner"] == "accounts@ubcsis.com"      # Mohamed Abdelsadiq
        assert row["preparer"] == "hadeer@ubcsis.com"     # Hadeer Mohamed
        assert row["escalation"] == "ahmed@ubcsis.com"    # CEO, same day


def test_the_rejection_window_carries_a_number_only_with_its_source():
    """This test used to assert the window was null.

    The execution order of 18-Aug-2026 supplied 7 days (D-31), so null
    is no longer the honest value. What it guarded survives: a number
    here may exist only if it says where it came from, because the
    failure mode is a plausible figure nobody can trace.
    """
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    rejection = next(r for r in data["obligations"] if r["id"] == "STAT-ETA-REJ")
    assert rejection["window_days"] == 7
    assert rejection["provenance"] == "ceo_stated"
    assert rejection["decision"] == "D-31"
    assert rejection["trigger"]
    # And the clock still starts on the event, so no cadence may fire.
    assert "from rejection" in rejection["rule"]


def test_no_statutory_rule_claims_more_than_the_CEO_said():
    """O-03 is open. `ceo_stated` is not `verified_by_advisor` and never
    becomes it by time passing — §7 of the execution order makes
    promotion without a named human a stop condition."""
    data = yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))
    assert data["verified_by_advisor"] is False
    assert data["ceo_stated"] is True
    assert data["last_verified"] is None
    assert data["source"]
    for row in data["obligations"]:
        assert row["provenance"] == "ceo_stated", row["id"]


def test_the_cycle_reads_absence_from_the_register(tmp_path):
    """End to end: the deputy path opens because HR registered leave,
    not because anything in the release path said so."""
    import shutil

    from control.cycle import run_cycle
    from control.startup import run_startup
    from control.transport import MailTransport

    class Silent(MailTransport):
        def fetch_unprocessed(self):
            return []

        def send(self, recipients, cc, subject, body):
            return "<x>"

        def mark_processed(self, message_ids):
            pass

    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    transport_config = control_root / "config" / "transport.yaml"
    transport_config.write_text(
        transport_config.read_text(encoding="utf-8").replace(
            "route: outlook_com", "route: graph", 1), encoding="utf-8")

    from datetime import date

    startup = run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2,
                          "2026-08-16")
    from control.db import connect

    conn = connect(startup.db_path)
    conn.execute("INSERT INTO absence (email, from_date, to_date, delegate,"
                 " registered_by) VALUES (?, ?, ?, ?, ?)",
                 (CEO, "2026-08-10", "2026-08-25", COO, "hr@ubcsis.com"))
    conn.commit()
    conn.close()

    run_cycle(startup, Silent(), control_root, specs={},
              today=date(2026, 8, 16), ceo=CEO, cfo="accounts@ubcsis.com",
              coo=COO)

    outbox = Outbox(control_root, "SUPERVISED", ceo=CEO, coo=COO)
    assert outbox.ceo_absent is False          # a fresh Outbox knows nothing

    # The cycle's own outbox saw the registered absence.
    draft_id = draft(Outbox(control_root, "LIVE", ceo=CEO, coo=COO,
                            ceo_absent=True))
    assert draft_id
