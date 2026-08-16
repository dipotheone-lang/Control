from datetime import date

import pytest

from control.discovery.stage_c import (
    classify_confidential,
    find_terms,
    render_commercial_exposure,
    run_stage_c,
)

CLIENTS = ["Siemens Energy", "Saint-Gobain", "KNAUF", "Canal Sugar"]
FOLDERS = ["NDA-clients"]


def _contract_text():
    return (
        "CONTRACT No. UB-2026-014 for structural works.\n"
        "The performance bond shall remain valid until 30/11/2026 and shall be "
        "released thereafter.\n"
        "Liquidated damages of 0.5% per week apply, capped at 10% of contract "
        "value.\n"
        "The Contractor shall give notice of any claim within 28 days of the "
        "event giving rise to it.\n"
        "The defects liability period is 12 months from Taking Over.\n"
        "Retention money of 5% shall be held.\n"
        "Payment terms: net 60 days from invoice.\n"
    )


def test_finds_the_commercial_terms_that_matter():
    terms = find_terms(_contract_text(), "contracts/UB-2026-014.txt")
    kinds = {t.kind for t in terms}
    assert "GUARANTEE_EXPIRY" in kinds
    assert "LIQUIDATED_DAMAGES" in kinds
    assert "NOTICE_PERIOD" in kinds
    assert "DEFECTS_LIABILITY" in kinds
    assert "RETENTION" in kinds
    assert "PAYMENT_TERMS" in kinds


def test_dates_are_parsed_day_first():
    terms = find_terms("valid until 30/11/2026 thereafter", "x.txt")
    assert terms and terms[0].found_date == "2026-11-30"
    # DD-MMM-YYYY
    terms = find_terms("expiry date 05-Mar-2027 confirmed", "x.txt")
    assert terms[0].found_date == "2027-03-05"


def test_confidential_classification_is_conservative():
    from pathlib import Path
    assert classify_confidential(Path("a/Siemens Energy/contract.pdf"),
                                 CLIENTS, FOLDERS)[0] is True
    assert classify_confidential(Path("a/NDA-clients/x.pdf"),
                                 CLIENTS, FOLDERS)[0] is True
    assert classify_confidential(Path("a/CONFIDENTIAL-terms.pdf"),
                                 CLIENTS, FOLDERS)[0] is True
    assert classify_confidential(Path("a/local-supplier/quote.pdf"),
                                 CLIENTS, FOLDERS)[0] is False


def test_multi_segment_confidential_folder_matches_on_any_platform():
    """A config folder is written with forward slashes; str(Path) yields
    backslashes on Windows. If the two are compared raw, the folder the
    CEO classified confidential does not match and the document gets
    opened — D-01 breached on one platform only (§12.1.2)."""
    from pathlib import Path
    folders = ["clients/NDA-clients"]
    for candidate in (
        Path("clients/NDA-clients/x.pdf"),
        Path("clients") / "NDA-clients" / "x.pdf",
        Path(r"clients\NDA-clients\x.pdf"),
    ):
        confidential, reason = classify_confidential(candidate, [], folders)
        assert confidential is True, candidate
        assert "classified confidential" in reason
    # Separator style in the config entry must not decide it either.
    assert classify_confidential(
        Path("clients/NDA-clients/x.pdf"), [], [r"clients\NDA-clients"])[0] is True


def test_confidential_documents_are_never_opened(tmp_path):
    (tmp_path / "Siemens Energy").mkdir()
    secret = tmp_path / "Siemens Energy" / "contract.txt"
    secret.write_text(_contract_text(), encoding="utf-8")
    ordinary = tmp_path / "supplier-agreement.txt"
    ordinary.write_text(_contract_text(), encoding="utf-8")

    result = run_stage_c(tmp_path, CLIENTS, FOLDERS)

    assert len(result.blocked) == 1
    assert result.blocked[0].path.endswith("contract.txt")
    # No term from the confidential file reached the register
    assert all("Siemens" not in t.source for t in result.terms)
    # The ordinary one was read
    assert any(t.source == "supplier-agreement.txt" for t in result.terms)


def test_scanned_documents_are_recorded_not_guessed(tmp_path):
    (tmp_path / "scan.jpg").write_bytes(b"\xff\xd8\xff not really an image")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS)
    assert len(result.unreadable) == 1
    assert "OCR" in result.unreadable[0].note
    assert result.terms == []


def test_report_sorts_by_urgency_and_separates_past(tmp_path):
    (tmp_path / "a.txt").write_text(
        "performance bond valid until 30/11/2026\n"
        "bank guarantee valid until 01/02/2026\n", encoding="utf-8")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS)
    text = render_commercial_exposure(result, today=date(2026, 8, 15))

    ahead, _, passed = text.partition("## Dates already passed")
    assert "2026-11-30" in ahead
    assert "2026-02-01" in passed


def test_report_states_the_charter_conflict(tmp_path):
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "master-agreement.txt").write_text(
        _contract_text(), encoding="utf-8")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS)
    text = render_commercial_exposure(result, today=date(2026, 8, 15))

    assert "incomplete by design" in text
    assert "D-01" in text
    assert "cannot see a guarantee expiry" in text
    assert "governance decision, not a technical one" in text
    assert "must not happen by a code change" in text
    # All three options put to the CEO
    assert "Accept the gap" in text
    assert "written amendment to D-01" in text
    assert "Extract the dates manually" in text
