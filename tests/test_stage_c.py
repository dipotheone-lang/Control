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


def test_d05_is_off_by_default(tmp_path):
    """The exception must be switched on deliberately, never assumed."""
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "master-agreement.txt").write_text(
        _contract_text(), encoding="utf-8")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS)

    assert len(result.blocked) == 1
    assert result.d05_extracted == []
    assert result.terms == []


def test_d05_extracts_dates_but_never_clause_text(tmp_path):
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "master-agreement.txt").write_text(
        _contract_text(), encoding="utf-8")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS,
                         permit_confidential_dates=True)

    assert result.blocked == []
    assert result.d05_extracted == ["KNAUF/master-agreement.txt"]
    assert result.terms, "dates should have been extracted"

    # The value survives; the clause text does not — and the redaction
    # happens at capture, so no report template can leak it.
    dated = [t for t in result.terms if t.found_date]
    assert any(t.found_date == "2026-11-30" for t in dated)
    for term in result.terms:
        assert term.context.startswith("[REDACTED")
        for fragment in ("Contractor", "liquidated damages of 0.5%",
                         "Taking Over", "net 60"):
            assert fragment not in term.context


def test_d05_keeps_only_dated_terms_from_confidential_documents(tmp_path):
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "agreement.txt").write_text(
        "Retention money of 5% shall be held.\n"
        "The performance bond is valid until 30/11/2026.\n", encoding="utf-8")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS,
                         permit_confidential_dates=True)
    # An undated term from a confidential document would carry no value
    # and only risk disclosure, so it is not retained at all.
    assert all(t.found_date for t in result.terms)


def test_report_scopes_itself_to_d05(tmp_path):
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "master-agreement.txt").write_text(
        _contract_text(), encoding="utf-8")
    result = run_stage_c(tmp_path, CLIENTS, FOLDERS,
                         permit_confidential_dates=True)
    text = render_commercial_exposure(result, today=date(2026, 8, 15))

    assert "dates extracted under D-05" in text
    assert "No clause text is stored" in text
    assert "does not widen §12.1 for anything else" in text
    # Still honest about what remains invisible
    assert "claim not noticed within its window is generally forfeited" in text
    assert "need OCR above the §5.5 confidence floor" in text


def test_the_scan_reports_progress_so_a_long_run_is_not_silence(tmp_path):
    """A run over a real document store takes hours. One that prints
    nothing for hours is indistinguishable from one that has hung, and
    the operator's only choices are waiting on faith or killing work
    that was fine.

    Enumeration is reported separately because walking a full drive is
    minutes of its own before the first document is opened — which is
    exactly where a silent run looks most like a hang.
    """
    from control.discovery.stage_c import run_stage_c

    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text("Bond valid until 30/11/2026.",
                                     encoding="utf-8")

    seen = []
    run_stage_c(tmp_path, [], [],
                progress=lambda *args: seen.append(args))

    stages = [s for s, *_ in seen]
    assert stages[0] == "enumerating", "the walk must announce itself"
    assert "enumerated" in stages
    assert stages[-1] == "done"

    enumerated = next(a for a in seen if a[0] == "enumerated")
    assert enumerated[2] == 3, "the total is known before processing starts"

    processing = [a for a in seen if a[0] == "processing"]
    assert processing, "every document reports, throttling is the caller's job"
    assert processing[0][1] == 1 and processing[-1][1] == 3
    assert all(a[3] for a in processing), "the current document is named"


def test_a_scan_without_a_progress_callback_still_runs(tmp_path):
    from control.discovery.stage_c import run_stage_c

    (tmp_path / "a.txt").write_text("Bond valid until 30/11/2026.",
                                    encoding="utf-8")
    assert run_stage_c(tmp_path, [], []).terms


# ---- the date belongs to the clause, or to nothing --------------------

CONTRACT = """SUPPLY AGREEMENT
Performance bond valid until 31 December 2026.
Advance payment guarantee expires on 15 March 2027.
Liquidated damages: 0.5% per week, capped at 10% of the contract value.
Any claim shall be notified within 21 days of the event giving rise to it.
Retention: 5% released 30 June 2027.
Defects liability period ends 31 January 2028.
Payment terms: 60 days from invoice date.
"""


def _by_kind(text=CONTRACT):
    from control.discovery.stage_c import find_terms

    out = {}
    for term in find_terms(text, "Supply Agreement.txt"):
        out.setdefault(term.kind, set()).add(term.found_date)
    return out


def test_every_term_carries_its_own_date_or_none():
    """One assertion over a whole contract, because the failure mode is
    a register that looks complete.

    Run on a real supplier agreement, the extractor produced: an LD
    clause reading "0.5% per week, capped at 10%" dated 31-Dec-2026,
    borrowed from the guarantee sentence before it; "Payment terms: 60
    days from invoice date" dated 30-Jun-2027, which was the retention
    release; the retention release itself missing; and no notice period
    at all, because the clause says "notified" and the pattern demanded
    "notice". Two fabricated dates, two silent omissions, and a report
    that read as a clean extraction.
    """
    assert _by_kind() == {
        "GUARANTEE_EXPIRY": {"2026-12-31", "2027-03-15"},
        "LIQUIDATED_DAMAGES": {""},
        "NOTICE_PERIOD": {""},
        "RETENTION": {"2027-06-30"},
        "DEFECTS_LIABILITY": {"2028-01-31"},
        "PAYMENT_TERMS": {""},
    }


def test_a_date_never_crosses_a_full_stop():
    """The fabrication, isolated. §2.1 rates a confident wrong date
    worse than no date."""
    terms = _by_kind("Performance bond valid until 31 December 2026. "
                     "Liquidated damages: 0.5% per week.")
    assert terms["LIQUIDATED_DAMAGES"] == {""}
    assert terms["GUARANTEE_EXPIRY"] == {"2026-12-31"}


def test_a_colon_introduces_a_clause_rather_than_ending_it():
    """The opposite error, and the same cost. Clipping at the colon
    threw the retention release away entirely."""
    assert _by_kind("Retention: 5% released 30 June 2027.")["RETENTION"] == {
        "2027-06-30"}


def test_a_claim_notified_within_a_window_is_found():
    """§2.2: "a claim not noticed within its window is generally
    forfeited" — the most expensive miss in the charter. "shall be
    notified within 21 days" is how the clause is normally written, and
    it was matching nothing."""
    for phrasing in (
        "Any claim shall be notified within 21 days of the event.",
        "The Contractor shall give notice within 14 days of any variation.",
        "Notification of a claim within (28) working days is required.",
    ):
        assert "NOTICE_PERIOD" in _by_kind(phrasing), phrasing


def test_one_guarantee_is_one_register_row():
    """"Performance bond valid until 31 December 2026" matches the
    instrument and the phrasing both. Two rows is two CEO alerts for one
    expiry."""
    terms = _by_kind("Performance bond valid until 31 December 2026.")
    assert "VALIDITY" not in terms
    assert terms["GUARANTEE_EXPIRY"] == {"2026-12-31"}


def test_a_validity_with_nothing_more_specific_still_counts():
    """A quotation has no instrument to defer to, so dropping the
    qualifier there would lose the only date in the document."""
    assert _by_kind("This quotation is valid until 30 June 2026.") == {
        "VALIDITY": {"2026-06-30"}}


def test_a_folder_that_does_not_exist_is_named_in_the_report():
    """A five-folder scan where one name is wrong used to refuse
    entirely, costing the whole run. Scanning the four that exist is the
    right behaviour — but only if the report says it covered four, or it
    reads as complete over ground it never searched (§1.1).
    """
    from control.discovery.stage_c import (
        StageCResult, render_commercial_exposure,
    )

    text = render_commercial_exposure(
        StageCResult(), not_scanned=[r"E:\UB\11. Vendor Registration Request"])
    assert "1 folder(s) named for this scan do not exist" in text
    assert "11. Vendor Registration Request" in text
    assert "not evidence that they hold nothing" in text


def test_a_complete_scan_claims_no_missing_folders():
    from control.discovery.stage_c import (
        StageCResult, render_commercial_exposure,
    )

    text = render_commercial_exposure(StageCResult(), not_scanned=[])
    assert "do not exist and were not searched" not in text


# ---- how contract text actually arrives -------------------------------

def test_a_clause_wrapped_across_lines_still_finds_its_date():
    """The regression that got to production, and why the suite missed it.

    Every contract in this file until now was written one tidy sentence
    per line with a full stop at the end. Real documents do not arrive
    that way: PDF extraction and OCR both emit a newline per rendered
    line, so a clause wraps mid-sentence. Treating that newline as a
    clause boundary produced **468 undated terms out of 470** on the
    first real run, over 957 documents — a register with two dates in
    it, reporting itself as "470 terms extracted". A §1.1 failure does
    not get worse than an empty result that announces a full one.
    """
    terms = _by_kind("CONTRACT UB-2026-014\n"
                     "The performance bond shall remain valid until\n"
                     "31 December 2026 and shall be released thereafter\n")
    assert terms["GUARANTEE_EXPIRY"] == {"2026-12-31"}


def test_a_date_two_rows_down_a_table_is_not_borrowed():
    """The other side of the same knob. One wrap is a wrapped clause;
    two is a different row, and a register row is worse for being
    confidently wrong than for being absent (§2.1)."""
    assert _by_kind("Performance bond\n"
                    "Supplier: Delta Steel\n"
                    "Signed: 31 December 2026\n")["GUARANTEE_EXPIRY"] == {""}


def test_a_paragraph_break_still_ends_the_clause():
    assert _by_kind("Performance bond details follow.\n\n"
                    "31 December 2026 is the audit date.\n"
                    )["GUARANTEE_EXPIRY"] == {""}


def test_the_whole_contract_survives_being_line_wrapped():
    """The same agreement as `test_every_term_carries_its_own_date_or_none`,
    re-flowed the way a PDF hands it over. The answers must not change
    because the line breaks moved."""
    wrapped = CONTRACT.replace(" capped", "\ncapped").replace(
        " released", "\nreleased").replace(" period ends", "\nperiod ends")
    assert _by_kind(wrapped) == _by_kind(CONTRACT)


@pytest.mark.parametrize("text,kind,expected", [
    ("performance\nbond valid until 31 December 2026", "GUARANTEE_EXPIRY",
     "2026-12-31"),
    ("The defects liability\nperiod ends 31 January 2028", "DEFECTS_LIABILITY",
     "2028-01-31"),
    ("liquidated\ndamages of 0.5% per week", "LIQUIDATED_DAMAGES", ""),
    ("payment\nterms: net 60 days", "PAYMENT_TERMS", ""),
    ("vendor\nregistration renewed 30 June 2027", "ACCREDITATION",
     "2027-06-30"),
    ("valid\nuntil 30/11/2026", "VALIDITY", "2026-11-30"),
])
def test_a_term_phrase_broken_by_a_line_wrap_is_still_found(text, kind,
                                                            expected):
    """Not the date this time — the term itself.

    "defects liability period" stopped matching the moment a PDF broke
    the line between "liability" and "period", losing the whole term.
    The patterns are written with plain spaces because they read as the
    phrases they are; `_phrase` turns each into `\\s+` at compile time
    so a pattern added later cannot forget.
    """
    assert _by_kind(text).get(kind) == {expected}


def test_the_cache_key_moves_when_extraction_logic_changes():
    """The cache served 957 of 957 documents from a superseded engine.

    `ruleset_fingerprint` keyed on the confidentiality inputs and the
    OCR floor — the rules that decide whether a document may be read —
    but not on the rules that read it. So a fix to the term patterns and
    the clause boundary changed nothing on re-run: every document came
    back from cache carrying the old answers, and the summary reported a
    successful scan. A cache that silently serves results from
    superseded logic is worse than no cache, because the operator has
    every reason to believe the fix ran.
    """
    import control.discovery.stage_c as sc

    args = (["Siemens Energy"], [], [], False, False, 60.0)
    before = sc.ruleset_fingerprint(*args)

    saved = sc._MAX_WRAPS
    try:
        sc._MAX_WRAPS = saved + 1
        assert sc.ruleset_fingerprint(*args) != before
    finally:
        sc._MAX_WRAPS = saved
    assert sc.ruleset_fingerprint(*args) == before


def test_the_cache_key_still_moves_when_the_confidential_list_grows():
    """The property the fingerprint existed for in the first place, kept
    intact: a client added by CEO decision must not replay as
    non-confidential with its clause text unredacted (§12.1)."""
    import control.discovery.stage_c as sc

    assert (sc.ruleset_fingerprint(["Siemens Energy"], [], [], False, False, 60.0)
            != sc.ruleset_fingerprint(["Siemens Energy", "KNAUF"], [], [],
                                      False, False, 60.0))
