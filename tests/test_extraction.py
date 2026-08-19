"""The extraction brief — execution order step 2.

Four class 1 deadlines alert on dates the CEO stated from memory. The
filing archive is evidence about those same rules and nobody has looked
at it.

Two things decide whether this module is worth trusting.

**It must count periods, not documents.** One return exists as a draft,
a signed copy and a scan. Counting documents would produce "twelve
payroll filings" out of four quarterly ones and manufacture exactly the
finding the order says to look for — the worst possible failure here,
because it is a confident wrong answer to the highest-value question.

**It must not turn a habit into a rule.** The archive shows when
filings happened, not when they were due. Nothing here produces a date,
and nothing here is applied — §14.2 puts statutory deadlines in Tier C.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control.extraction import (
    ANNUAL, MONTHLY, QUARTERLY, Period, disagreements, observe,
    paths_from_inventory, read_period, render_brief, scan_paths,
    upgrade_candidates,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
TODAY = date(2026, 8, 18)


@pytest.fixture
def rules():
    return yaml.safe_load(
        (REPO_CONFIG / "filing-evidence.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def statutory():
    return yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))


# ---- reading the period ------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("E:/Tax/VAT 2026-03 return.pdf", Period(MONTHLY, 2026, 3)),
    ("E:/Tax/VAT 2026_03.pdf", Period(MONTHLY, 2026, 3)),
    ("E:/Tax/VAT 03-2026.pdf", Period(MONTHLY, 2026, 3)),
    ("E:/Tax/VAT March 2026.pdf", Period(MONTHLY, 2026, 3)),
    ("E:/Tax/VAT mar 2026.pdf", Period(MONTHLY, 2026, 3)),
    ("E:/Tax/اقرار مارس 2026.pdf", Period(MONTHLY, 2026, 3)),
    ("E:/Tax/يونيه 2025 تأمينات.pdf", Period(MONTHLY, 2025, 6)),
    ("E:/Tax/Payroll Q2 2026.xlsx", Period(QUARTERLY, 2026, 2)),
    ("E:/Tax/Payroll 2026 Q2.xlsx", Period(QUARTERLY, 2026, 2)),
    ("E:/Tax/Corporate return 2025.pdf", Period(ANNUAL, 2025)),
])
def test_the_most_specific_period_wins(text, expected):
    assert read_period(text) == expected


@pytest.mark.parametrize("text", [
    "E:/Tax/VAT return final.pdf",
    "E:/Tax/scan0012.pdf",
    "E:/Tax/VAT 1998 archive.pdf",     # outside the plausible range
])
def test_a_path_naming_no_period_reads_as_none(text):
    """None is a real answer. A filing whose name does not say which
    period it covers cannot be counted, and guessing would put a
    fabricated period into the count that answers the payroll test."""
    assert read_period(text) is None


def test_a_month_number_is_not_read_out_of_a_longer_number():
    assert read_period("E:/Tax/invoice 20260312345.pdf") is None


# ---- matching ----------------------------------------------------------

def test_documents_match_the_obligation_they_name(rules):
    found = scan_paths([
        "E:/UB/Tax/VAT/VAT return 2026-01.pdf",
        "E:/UB/Tax/Withholding/WHT 2026-01.xlsx",
        "E:/UB/HR/تأمينات يناير 2026.pdf",
        "E:/UB/Tax/ضريبة كسب العمل 2026-01.pdf",
    ], rules)
    assert {e.obligation_id for e in found} == {
        "STAT-VAT", "STAT-WHT", "STAT-SOCINS", "STAT-PAYROLL"}


def test_a_supplier_invoice_is_not_our_vat_return(rules):
    """The exclusion that stops every purchase invoice in the company
    becoming evidence of a monthly filing — which would have produced a
    spectacular and completely false cadence finding."""
    found = scan_paths([
        "E:/UB/Purchases/VAT invoice 2026-01 supplier.pdf",
        "E:/UB/Purchases/فاتورة قيمة مضافة 2026-01.pdf",
    ], rules)
    assert found == []


def test_templates_and_blanks_are_not_filings(rules):
    found = scan_paths([
        "E:/UB/Templates/VAT return template 2026-01.xlsx",
        "E:/UB/Forms/blank VAT 2026-02.xlsx",
    ], rules)
    assert found == []


def test_one_document_matches_one_obligation(rules):
    """A path naming two obligations counts once, for the first rule
    that claims it — otherwise a folder called "Tax" doubles every
    count in the brief."""
    found = scan_paths(["E:/UB/VAT and withholding 2026-01.pdf"], rules)
    assert len(found) == 1


# ---- the count that answers the order's question -----------------------

def _payroll(n_per_year, years=(2023, 2024, 2025, 2026), copies=1):
    paths = []
    for year in years:
        for month in range(1, n_per_year + 1):
            for copy in range(copies):
                paths.append(
                    f"E:/UB/Tax/Payroll tax {year}-{month:02d} v{copy}.pdf")
    return paths


def test_periods_are_counted_not_documents(rules):
    """The failure this guards would have been a confident wrong answer
    to the single highest-value question in the brief."""
    found = scan_paths(_payroll(12, copies=3), rules)
    record = observe(found)["STAT-PAYROLL"]
    assert record.documents == 12 * 4 * 3
    assert len(record.periods) == 48
    assert record.per_year(MONTHLY)[2025] == 12


def test_twelve_monthly_payroll_periods_contradict_the_quarterly_rule(
        rules, statutory):
    """The order's own highest-value test: "Twelve means D-23/24 is
    wrong and eleven obligations are missing"."""
    observed = observe(scan_paths(_payroll(12), rules))
    found = disagreements(statutory, observed)
    payroll = next(d for d in found if d.obligation_id == "STAT-PAYROLL")
    assert "quarterly — 4 period(s) a year" in payroll.stated
    assert "2024: 12, 2025: 12" in payroll.observed
    assert "about 8 obligation(s) a year are missing" in payroll.consequence
    # One entry per obligation, not one per contradicting year — a
    # paragraph repeated says nothing the first one did not, and a
    # reader who skims the second stops reading the section.
    assert len([d for d in found if d.obligation_id == "STAT-PAYROLL"]) == 1
    # And it is raised, not acted on.
    assert "raised, not acted on" in payroll.consequence


def test_four_quarterly_filings_contradict_nothing(rules, statutory):
    observed = observe(scan_paths(_payroll(4), rules))
    assert disagreements(statutory, observed) == []


def test_the_ragged_edges_of_the_archive_never_speak_alone(rules):
    """Collections start and end mid-year. A partial first year is not
    evidence of a cadence, and treating it as such would produce a
    finding out of the archive's shape rather than the company's."""
    paths = ([f"E:/UB/Tax/Payroll tax 2024-{m:02d}.pdf" for m in (11, 12)]
             + [f"E:/UB/Tax/Payroll tax 2025-{m:02d}.pdf" for m in range(1, 13)]
             + ["E:/UB/Tax/Payroll tax 2026-01.pdf"])
    record = observe(scan_paths(paths, {"obligations": [
        {"id": "STAT-PAYROLL", "markers": ["payroll tax"]}]}))["STAT-PAYROLL"]
    assert record.per_year(MONTHLY) == {2024: 2, 2025: 12, 2026: 1}
    assert record.complete_years == {2025: 12}


# ---- provenance --------------------------------------------------------

def test_a_corroborated_rule_is_offered_not_applied(rules, statutory):
    paths = [f"E:/UB/Tax/VAT {year}-{m:02d}.pdf"
             for year in (2024, 2025, 2026) for m in range(1, 13)]
    observed = observe(scan_paths(paths, rules))
    candidates = upgrade_candidates(statutory, observed, [])
    vat = next(c for c in candidates if c["id"] == "STAT-VAT")
    assert vat["from"] == "ceo_stated" and vat["to"] == "document_evidenced"
    assert "matching the stated monthly cadence" in vat["evidence"]
    # The rung that is never reached this way.
    assert "verified_by_advisor" not in str(vat)
    assert "O-03 is unaffected" in vat["still_open"]
    # And the config on disk is untouched — nothing here applies.
    assert statutory["verified_by_advisor"] is False
    assert all(r["provenance"] == "ceo_stated" for r in statutory["obligations"])


def test_a_contested_rule_is_never_offered_an_upgrade(rules, statutory):
    """Evidence that contradicts a rule is not evidence for it."""
    observed = observe(scan_paths(_payroll(12), rules))
    contested = disagreements(statutory, observed)
    candidates = upgrade_candidates(statutory, observed, contested)
    assert not [c for c in candidates if c["id"] == "STAT-PAYROLL"]


def test_thin_evidence_is_not_corroboration(rules, statutory):
    """Two filings are not a cadence. §7.2's minimum-sample rule is the
    same idea and this is the same failure — a distribution of three."""
    observed = observe(scan_paths(
        ["E:/UB/Tax/VAT 2026-01.pdf", "E:/UB/Tax/VAT 2026-02.pdf"], rules))
    assert upgrade_candidates(statutory, observed, []) == []


# ---- the brief itself --------------------------------------------------

def test_disagreements_come_first_in_the_document(rules, statutory):
    observed = observe(scan_paths(_payroll(12), rules))
    contested = disagreements(statutory, observed)
    text = render_brief(statutory, observed, contested, [], "test", 36, TODAY)
    assert text.index("DISAGREEMENTS") < text.index("WHAT THE ARCHIVE HOLDS")
    assert text.index("DISAGREEMENTS") < text.index("PROVENANCE UPGRADES")


def test_no_disagreement_is_not_reported_as_a_clean_bill(rules, statutory):
    """§1.1. "The archive agreed" and "the archive could not be asked"
    produce the same empty section, and must not read the same."""
    text = render_brief(statutory, {}, [], [], "test", 0, TODAY)
    assert "This is not a clean bill" in text
    assert "could not be asked" in text
    # And each silent obligation says why it was silent.
    assert "no filing evidence matched at all" in text


def test_the_brief_states_what_it_cannot_tell_you(rules, statutory):
    text = render_brief(statutory, {}, [], [], "test", 0, TODAY)
    assert "Whether a filing was on time" in text
    assert "Whether a filing is missing" in text
    assert "Absence of evidence is reported as absence of evidence" in text
    assert "answered by an advisor, not by a folder" in text


def test_the_brief_says_nothing_was_applied(rules, statutory):
    text = render_brief(statutory, {}, [], [], "test", 0, TODAY)
    assert "Nothing in this brief has been applied" in text
    assert "Tier C" in text
    assert "stop condition" in text
    assert "Observed is not due" in text


def test_duplicate_copies_are_explained_rather_than_hidden(rules, statutory):
    observed = observe(scan_paths(_payroll(4, copies=4), rules))
    text = render_brief(statutory, observed, [], [], "test", 48, TODAY)
    assert "per period" in text
    assert "manufactured a cadence finding" in text


# ---- input -------------------------------------------------------------

def test_the_stage_b_inventory_is_reused_rather_than_rewalked(tmp_path):
    """The laptop already walked thirteen thousand documents once."""
    csv_path = tmp_path / "file-inventory.csv"
    csv_path.write_text(
        "path,size_bytes,ext\n"
        "E:/UB/Tax/VAT 2026-01.pdf,1024,.pdf\n"
        "E:/UB/Tax/VAT 2026-02.pdf,1024,.pdf\n",
        encoding="utf-8")
    assert paths_from_inventory(csv_path) == [
        "E:/UB/Tax/VAT 2026-01.pdf", "E:/UB/Tax/VAT 2026-02.pdf"]


# ---- the false positive that would have wrecked the count --------------

@pytest.mark.parametrize("path", [
    "E:/UB/Projects/Sukari/excavation drawings 2025-04.dwg",
    "E:/UB/HR/private medical scheme 2025-04.xlsx",
    "E:/UB/Projects/renovation works 2025-06.pdf",
    "E:/UB/Sales/Elevator maintenance 2025-06.pdf",
    "E:/UB/Projects/metal cladding detail 2025-07.pdf",
    "E:/UB/Projects/concrete details 2025-07.dwg",
])
def test_a_marker_never_fires_inside_a_longer_word(rules, path):
    """`vat` is inside "excavation" and `eta` is inside "metal" and
    "detail". Substring matching gave every one of these a VAT or ETA
    match, a month from its filename, and a place in the count that
    answers the payroll question. This is a contracting company: the
    archive is full of them."""
    assert scan_paths([path], rules) == []


def test_the_real_markers_still_match(rules):
    """The boundary must not be so tight that nothing gets through."""
    matched = scan_paths([
        "E:/UB/Tax/VAT 2026-01.pdf",
        "E:/UB/Tax/vat-return-2026-02.pdf",
        "E:/UB/Tax/ETA submission log 2026-01.xlsx",
        "E:/UB/Tax/e-invoicing 2026-03.pdf",
    ], rules)
    assert {e.obligation_id for e in matched} == {"STAT-VAT", "STAT-ETA-SUB"}
    assert len(matched) == 4


def test_arabic_keeps_substring_matching(rules):
    """Arabic attaches the article to the word, so `تأمينات` has to
    match `والتأمينات`. Word boundaries would silently drop the Arabic
    half of the archive."""
    matched = scan_paths(["E:/UB/HR/كشف والتأمينات 2026-01.pdf"], rules)
    assert [e.obligation_id for e in matched] == ["STAT-SOCINS"]


def test_etabs_models_are_not_eta_filings(rules):
    """ETABS is structural software; a technical office is full of its
    model files. `eta` inside "etabs" was the case that decided the
    trailing boundary blocks letters but not digits."""
    assert scan_paths(["E:/UB/Technical/ETABS model rev3 2025-04.edb"],
                      rules) == []


def test_a_marker_followed_by_digits_still_matches(rules):
    """"VAT2026-01.pdf" is a real filename, and a boundary tight enough
    to reject it would lose filings to punctuation habits."""
    found = scan_paths(["E:/UB/Tax/VAT2026-01.pdf"], rules)
    assert [e.obligation_id for e in found] == ["STAT-VAT"]


# ---- the blindness that made "no disagreement" meaningless ------------

def test_quarterly_named_filings_are_compared_as_quarters(rules, statutory):
    """The defect this pins ran against the real archive and reported
    "No disagreement" — which was a fact about the naming convention,
    not about the company.

    The comparison only ever looked at monthly periods. An obligation
    whose filings are named "Q1 2025" had no monthly periods at all, so
    nothing could contradict its stated cadence and the brief came back
    clean. The order's single highest-value test would have returned
    silence and been read as agreement.
    """
    paths = [f"E:/UB/Tax/Payroll tax Q{q} {y}.pdf"
             for y in (2023, 2024, 2025, 2026) for q in (1, 2, 3, 4)]
    record = observe(scan_paths(paths, rules))["STAT-PAYROLL"]
    assert record.granularity == QUARTERLY
    assert record.complete_years == {2024: 4, 2025: 4}
    # Four quarterly filings a year agree with a quarterly rule.
    assert disagreements(statutory, observe(scan_paths(paths, rules))) == []


def test_eight_quarterly_periods_in_a_year_contradict_a_quarterly_rule(
        rules, statutory):
    """Impossible at that granularity, and now visible. Before, only a
    monthly count could contradict anything."""
    paths = ([f"E:/UB/Tax/Payroll tax Q{q} {y}.pdf"
              for y in (2023, 2026) for q in (1, 2, 3, 4)]
             + [f"E:/UB/Tax/Payroll tax Q{q} {y} part{p}.pdf"
                for y in (2024, 2025) for q in (1, 2, 3, 4) for p in (1, 2)])
    found = disagreements(statutory, observe(scan_paths(paths, rules)))
    assert found == [], "duplicate copies of the same quarter are one period"


def test_an_annual_rule_is_not_corroborated_by_monthly_coincidence(
        rules, statutory):
    """One monthly-dated document a year "matched" an annual cadence of
    one a year, and the brief offered a provenance upgrade on it. Like
    is now compared with like."""
    paths = [f"E:/UB/Legal/commercial register {y}-{y % 12 + 1:02d}.pdf"
             for y in (2021, 2022, 2023, 2024, 2025, 2026)]
    observed = observe(scan_paths(paths, rules))
    assert observed["STAT-REG"].granularity == MONTHLY
    assert upgrade_candidates(statutory, observed, []) == []


def test_an_annual_rule_is_corroborated_by_annual_filings(rules, statutory):
    paths = [f"E:/UB/Legal/commercial register renewal {y}.pdf"
             for y in range(2019, 2027)]
    observed = observe(scan_paths(paths, rules))
    assert observed["STAT-REG"].granularity == ANNUAL
    candidate = next(c for c in upgrade_candidates(statutory, observed, [])
                     if c["id"] == "STAT-REG")
    assert "annual period(s)" in candidate["evidence"]


def test_the_brief_says_which_obligations_could_not_be_asked(rules, statutory):
    """"The archive agreed" and "the archive could not be asked" produce
    the same empty disagreements section."""
    from control.extraction import silent_obligations

    paths = [f"E:/UB/Tax/VAT {y}-{m:02d}.pdf"
             for y in (2023, 2024, 2025, 2026) for m in range(1, 13)]
    observed = observe(scan_paths(paths, rules))
    notes = silent_obligations(statutory, observed)
    assert any(n.startswith("STAT-PAYROLL") and "no filing evidence" in n
               for n in notes)
    # VAT was asked, so it is not on the list.
    assert not [n for n in notes if n.startswith("STAT-VAT")]


def test_a_granularity_mismatch_says_so_rather_than_reading_as_agreement(
        rules, statutory):
    from control.extraction import silent_obligations

    paths = [f"E:/UB/Tax/Payroll tax {y}.pdf" for y in range(2019, 2027)]
    observed = observe(scan_paths(paths, rules))
    note = next(n for n in silent_obligations(statutory, observed)
                if n.startswith("STAT-PAYROLL"))
    assert "stated quarterly, but the filings are named by year" in note
    assert "cannot confirm a quarterly rule" in note
