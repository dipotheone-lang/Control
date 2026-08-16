"""Decision O-04 — the confidentiality worksheet.

486 domains is too many to classify from a summary table, and §12.1.1
makes each one a judgement with an asymmetric cost. So the worksheet's
job is to carry evidence to a human and carry a decision back — without
ever deciding anything itself.

The tests that matter here are the ones about what the worksheet does
NOT do: it must never promote a domain out of confidential on silence,
never lose an NDA client's domains, and never touch D-01.
"""

import csv
from pathlib import Path

import pytest
import yaml

from control.discovery.classify_worksheet import (
    apply_worksheet, build_rows, client_hints_from_config,
    confidential_domains, read_worksheet, write_worksheet,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


def row(sender, to="", cc="", received="2026-03-01T09:00:00",
        attachments=None, mailbox="info@ubcsis.com", subject="s"):
    return {"sender": sender, "to": to, "cc": cc, "received": received,
            "attachments": attachments or [], "mailbox": mailbox,
            "subject": subject}


# ---- building the evidence -------------------------------------------

def test_internal_domain_is_never_a_counterparty():
    rows = [row("ahmed@ubcsis.com", to="ghareeb@ubcsis.com")]
    assert build_rows(rows) == []


def test_counts_inbound_and_outbound_separately():
    rows = [
        row("buyer@enova-me.com", to="info@ubcsis.com"),
        row("info@ubcsis.com", to="buyer@enova-me.com"),
        row("info@ubcsis.com", to="buyer@enova-me.com"),
    ]
    entry = build_rows(rows)[0]
    assert entry.domain == "enova-me.com"
    assert (entry.messages, entry.inbound, entry.outbound) == (3, 1, 2)


def test_one_message_counts_once_per_domain():
    """Same counterparty as sender and recipient is still one message."""
    rows = [row("a@suezsteel.com", to="b@suezsteel.com; info@ubcsis.com")]
    entry = build_rows(rows)[0]
    assert entry.messages == 1
    assert entry.inbound == 1 and entry.outbound == 1


def test_recipients_without_an_address_are_skipped_not_guessed():
    """Outlook often gives display names. A name is not a domain."""
    rows = [row("info@ubcsis.com", to="Mohamed Sayed; Purchasing Dept")]
    assert build_rows(rows) == []


def test_evidence_carried_for_the_judgement():
    rows = [
        row("x@lafarge.com", received="2024-01-05T08:00:00",
            attachments=["boq.xlsx"]),
        row("y@lafarge.com", received="2026-02-20T08:00:00", mailbox="sales@ubcsis.com"),
    ]
    entry = build_rows(rows)[0]
    assert entry.first_seen == "2024-01-05"
    assert entry.last_seen == "2026-02-20"
    assert entry.with_attachments == 1
    assert entry.mailboxes == {"info@ubcsis.com", "sales@ubcsis.com"}


def test_unparseable_timestamps_leave_the_dates_empty_not_invented():
    entry = build_rows([row("x@lafarge.com", received="not a date")])[0]
    assert entry.first_seen == "" and entry.last_seen == ""


def test_rows_are_ordered_by_volume():
    rows = ([row("a@small.com")]
            + [row(f"u{i}@big.com") for i in range(5)])
    assert [r.domain for r in build_rows(rows)] == ["big.com", "small.com"]


# ---- the proposals ----------------------------------------------------

def test_known_client_is_proposed_confidential_with_its_name():
    entry = build_rows([row("eng@siemens-energy.com")])[0]
    assert entry.proposed == "CONFIDENTIAL"
    assert entry.matched_client == "Siemens Energy"
    assert "confirmed client" in entry.note


def test_clients_found_in_the_mail_are_recognised_too():
    """The charter's list was written from memory; these came from
    Phase 0 evidence and were CEO-confirmed on 16-Aug-2026."""
    for domain, name in (("enova-me.com", "Enova"),
                         ("suezsteel.com", "Suez Steel"),
                         ("lafarge.com", "Lafarge"),
                         ("eg.ivldhunseri.com", "IVL Dhunseri")):
        entry = build_rows([row(f"x@{domain}")])[0]
        assert entry.matched_client == name
        assert entry.proposed == "CONFIDENTIAL"


def test_hints_are_derived_from_the_confirmed_client_list():
    """Adding a client to config must not leave the worksheet
    proposing NOT_CONFIDENTIAL for its domain."""
    hints = client_hints_from_config(
        {"confidential_clients": [{"name": "New Co", "domains": ["newco.eg"]}]})
    entry = build_rows([row("a@newco.eg")], hints)[0]
    assert entry.matched_client == "New Co"


def test_the_repo_client_list_covers_every_confirmed_domain():
    data = yaml.safe_load(
        (REPO_CONFIG / "confidential.yaml").read_text(encoding="utf-8"))
    hints = client_hints_from_config(data)
    for client in data["confidential_clients"]:
        for domain in client.get("domains") or []:
            entry = build_rows([row(f"x@{domain}")], hints)[0]
            assert entry.matched_client, f"{domain} matched nothing"


def test_platform_noise_is_proposed_not_confidential():
    entry = build_rows([row("no-reply@linkedin.com")])[0]
    assert entry.proposed == "NOT_CONFIDENTIAL"
    assert "counterparty" in entry.note


def test_an_unrecognised_counterparty_defaults_to_confidential():
    """The §12.1.1 asymmetry: a wrong check costs less than a client."""
    entry = build_rows([row("procurement@unknown-counterparty.eg")])[0]
    assert entry.proposed == "CONFIDENTIAL"
    assert "conservative default" in entry.note


# ---- the worksheet round trip ----------------------------------------

def test_worksheet_has_a_blank_decision_column(tmp_path):
    path = write_worksheet(build_rows([row("x@enova-me.com")]),
                           tmp_path / "w.csv")
    with path.open(encoding="utf-8-sig", newline="") as f:
        record = next(csv.DictReader(f))
    assert record["YOUR_DECISION"] == ""
    assert record["proposed"] == "CONFIDENTIAL"
    assert record["domain"] == "enova-me.com"


def test_blank_decisions_are_not_read_as_answers(tmp_path):
    path = write_worksheet(build_rows([row("x@enova-me.com")]), tmp_path / "w.csv")
    decisions, problems = read_worksheet(path)
    assert decisions == {} and problems == []


def test_decisions_are_read_case_insensitively(tmp_path):
    path = tmp_path / "w.csv"
    path.write_text(
        "domain,YOUR_DECISION\nenova-me.com,confidential\nsuezsteel.com, NOT_CONFIDENTIAL \n",
        encoding="utf-8")
    decisions, problems = read_worksheet(path)
    assert decisions == {"enova-me.com": "CONFIDENTIAL",
                         "suezsteel.com": "NOT_CONFIDENTIAL"}
    assert problems == []


def test_a_typo_is_reported_not_interpreted(tmp_path):
    path = tmp_path / "w.csv"
    path.write_text("domain,YOUR_DECISION\nenova-me.com,confidentail\n",
                    encoding="utf-8")
    decisions, problems = read_worksheet(path)
    assert decisions == {}
    assert len(problems) == 1
    assert "enova-me.com" in problems[0] and "line 2" in problems[0]


# ---- applying to config ----------------------------------------------

@pytest.fixture
def config(tmp_path):
    path = tmp_path / "confidential.yaml"
    path.write_text(
        (REPO_CONFIG / "confidential.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    return path


def test_applying_records_who_decided_and_when(config):
    apply_worksheet({"enova-me.com": "CONFIDENTIAL"}, config,
                    "ahmed@ubcsis.com", "2026-08-16")
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    decided = data["domain_classifications"]
    assert decided["confidential"] == ["enova-me.com"]
    assert decided["decided_by"] == "ahmed@ubcsis.com"
    assert decided["decided_on"] == "2026-08-16"
    assert decided["unclassified_default"] == "CONFIDENTIAL"


def test_d01_survives_the_write(config):
    """O-04 sets scope. It must not touch the processing decision."""
    apply_worksheet({"x.com": "NOT_CONFIDENTIAL"}, config, "ahmed@ubcsis.com",
                    "2026-08-16")
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert data["processing"] == "DISABLED"
    # 7 charter defaults + 5 confirmed from Phase 0 evidence.
    assert len(data["confidential_clients"]) == 12


def test_a_decided_domain_is_attached_to_its_client(config):
    apply_worksheet({"siemens-energy.com": "CONFIDENTIAL"}, config,
                    "ahmed@ubcsis.com", "2026-08-16")
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    siemens = next(c for c in data["confidential_clients"]
                   if c["name"] == "Siemens Energy")
    assert siemens["domains"] == ["siemens-energy.com"]


def test_the_d01_header_prose_survives_the_write(config):
    """A config that no longer says why it is locked is a weaker config."""
    apply_worksheet({"enova-me.com": "CONFIDENTIAL"}, config,
                    "ahmed@ubcsis.com", "2026-08-16")
    text = config.read_text(encoding="utf-8")
    assert "CLIENT_CONFIDENTIAL_PROCESSING=DISABLED" in text
    assert "never reads their contents" in text
    assert yaml.safe_load(text)["processing"] == "DISABLED"


def test_undecided_domains_do_not_appear_anywhere(config):
    """Silence must not become an answer in either direction."""
    apply_worksheet({"enova-me.com": "CONFIDENTIAL"}, config,
                    "ahmed@ubcsis.com", "2026-08-16")
    text = config.read_text(encoding="utf-8")
    assert "never-decided.example" not in text


# ---- what the engine reads -------------------------------------------

def test_engine_reads_both_sources():
    config = {
        "confidential_clients": [{"name": "KNAUF", "domains": ["knauf.com.eg"]}],
        "domain_classifications": {"confidential": ["enova-me.com"],
                                   "not_confidential": ["linkedin.com"]},
    }
    assert confidential_domains(config) == {"knauf.com.eg", "enova-me.com"}


def test_not_confidential_never_subtracts_from_an_nda_list():
    """The NDA list was set against a contract; the worksheet was not."""
    config = {
        "confidential_clients": [{"name": "KNAUF", "domains": ["knauf.com.eg"]}],
        "domain_classifications": {"not_confidential": ["knauf.com.eg"]},
    }
    assert "knauf.com.eg" in confidential_domains(config)


def test_empty_config_yields_no_domains_without_crashing():
    assert confidential_domains({}) == set()
    assert confidential_domains(None) == set()


def test_repo_config_still_parses_through_the_reader():
    data = yaml.safe_load((REPO_CONFIG / "confidential.yaml").read_text(encoding="utf-8"))
    # The five CEO-confirmed clients carry domains; the charter's seven
    # do not yet, and O-04 remains open for the long tail. Partial
    # population is the honest state and the reader must survive it.
    assert confidential_domains(data) == {
        "enova-me.com", "suezsteel.com", "lafarge.com", "eg.ivldhunseri.com"}
    assert data["processing"] == "DISABLED"
