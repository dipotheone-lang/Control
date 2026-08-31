"""The tax advisor brief — execution order step 5.

*"Send the completed statutory table for correction, not blank rows.
Request the full filing archive in the same message. Lead with the
payroll cycle and the corporate return date."*

That reverses the original draft's method, which sent blank rows on the
reasoning that a proposed answer anchors the person correcting it. Right
when nothing was known; wrong now, because withholding what we hold
asks a paid professional to rediscover it.

The anchoring risk does not vanish, so it is named instead. These tests
are mostly about the brief refusing to look more certain than it is:
every row says where its value came from, the covering note says the
failure mode is agreeing with a plausible row, and the archive column
says what it cannot tell you as readily as what it can.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control.advisor import LEAD_WITH, build_rows, render
from control.extraction import observe, scan_paths

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
TODAY = date(2026, 8, 19)


@pytest.fixture(scope="module")
def statutory():
    return yaml.safe_load(
        (REPO_CONFIG / "statutory-calendar.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rules():
    return yaml.safe_load(
        (REPO_CONFIG / "filing-evidence.yaml").read_text(encoding="utf-8"))


def _archive(paths, rules):
    return observe(scan_paths(paths, rules))


# ---- what the order asked for -----------------------------------------

def test_the_table_is_completed_not_blank(statutory):
    """Step 5. Every row carries the CEO's stated rule."""
    rows, _ = build_rows(statutory, {})
    assert rows
    assert all(row.stated for row in rows)
    vat = next(r for r in rows if r.obligation_id == "STAT-VAT")
    assert vat.stated == "end of the following month, -5 working days"


def test_payroll_and_the_corporate_return_come_first(statutory):
    """"Lead with the payroll cycle and the corporate return date."
    A reviewer's attention is highest on the first thing they meet and
    lowest on the twelfth row."""
    rows, _ = build_rows(statutory, {})
    assert [r.obligation_id for r in rows[:len(LEAD_WITH)]] == list(LEAD_WITH)


def test_the_filing_archive_is_requested_in_the_same_message(statutory):
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "send the full filing archive" in text
    assert "checked against records rather than against filenames" in text


# ---- it never looks more certain than it is ---------------------------

def test_every_row_states_where_its_value_came_from(statutory):
    rows, _ = build_rows(statutory, {})
    assert all(row.provenance == "ceo_stated" for row in rows)


def test_the_covering_note_names_the_failure_mode(statutory):
    """Anchoring is not avoided here, it is disclosed. The brief says
    what going wrong looks like so the reviewer can watch for it."""
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "failure mode here is agreeing with a row because it looks" in text
    assert "none of them came from anyone qualified" in text
    assert "recorded from memory" in text


def test_the_brief_explains_why_it_changed_method(statutory):
    """An earlier version of this document did the opposite. Someone
    who read that one deserves to know why this one is different."""
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "earlier version of this brief sent blank rows" in text


def test_the_archive_column_is_not_offered_as_a_second_opinion(statutory):
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "evidence about practice, not about law" in text
    assert "that is your judgement and not ours" in text


# ---- the archive column ------------------------------------------------

def test_a_monthly_run_reads_as_consistent_with_a_monthly_rule(statutory,
                                                               rules):
    paths = [f"E:/UB/Tax/VAT {y}-{m:02d}.pdf"
             for y in (2023, 2024, 2025, 2026) for m in range(1, 13)]
    rows, _ = build_rows(statutory, _archive(paths, rules))
    vat = next(r for r in rows if r.obligation_id == "STAT-VAT")
    assert "consistent with monthly" in vat.observed


def test_twelve_filings_against_a_quarterly_rule_is_flagged_in_the_table(
        statutory, rules):
    """The order's own highest-value test, visible in the row the
    advisor reads first."""
    paths = [f"E:/UB/Tax/Payroll tax {y}-{m:02d}.pdf"
             for y in (2023, 2024, 2025, 2026) for m in range(1, 13)]
    rows, _ = build_rows(statutory, _archive(paths, rules))
    payroll = next(r for r in rows if r.obligation_id == "STAT-PAYROLL-REM")
    # The contradiction this check existed to surface was acted on: the
    # CEO split the row on 30-Aug-2026 into a monthly remittance and a
    # quarterly return, so twelve filings a year now agree with the
    # register instead of contradicting it.
    assert "consistent with monthly" in payroll.observed


def test_four_filings_against_the_monthly_rule_is_flagged(statutory, rules):
    """The same comparison, pointed the other way. Too few filings for
    the stated cadence is the direction that hides a missed filing, so
    it has to read as loudly as too many did."""
    paths = [f"E:/UB/Tax/Payroll tax {y}-{m:02d}.pdf"
             for y in (2023, 2024, 2025, 2026) for m in (3, 6, 9, 12)]
    rows, _ = build_rows(statutory, _archive(paths, rules))
    payroll = next(r for r in rows if r.obligation_id == "STAT-PAYROLL-REM")
    assert "FEWER than monthly would produce" in payroll.observed


def test_the_quarterly_return_is_shown_as_unevidenced(statutory, rules):
    """The cost of the split, stated rather than hidden: the filename
    markers cannot tell a remittance from a return, so the evidence is
    attributed to the monthly row and the quarterly one has none.
    Inventing a marker to separate them would be worse than the gap."""
    paths = [f"E:/UB/Tax/Payroll tax {y}-{m:02d}.pdf"
             for y in (2024, 2025) for m in range(1, 13)]
    rows, _ = build_rows(statutory, _archive(paths, rules))
    ret = next(r for r in rows if r.obligation_id == "STAT-PAYROLL-RET")
    assert ret.observed == "no filing evidence found"


def test_no_evidence_says_so_rather_than_being_left_blank(statutory):
    """A blank cell in a table of filings reads as "none filed". §1.1
    again: the gap is stated, not left to be inferred."""
    rows, _ = build_rows(statutory, {})
    assert all(row.observed == "no filing evidence found" for row in rows)


def test_a_missing_year_inside_the_span_is_called_out(statutory, rules):
    paths = [f"E:/UB/Legal/commercial register renewal {y}.pdf"
             for y in (2022, 2023, 2024, 2026, 2027)]
    rows, _ = build_rows(statutory, _archive(paths, rules))
    registers = next(r for r in rows if r.obligation_id == "STAT-REG")
    assert "holds no filing at all" in registers.observed


# ---- who the brief is for ----------------------------------------------

def test_data_protection_rows_are_not_sent_to_a_tax_advisor(statutory):
    """Asking a tax advisor about the PDPL executive regulations wastes
    their time and — worse — dilutes the rows that matter, by making the
    brief look like a form to work through rather than four questions
    that cost money to get wrong."""
    rows, excluded = build_rows(statutory, {})
    ids = {r.obligation_id for r in rows}
    assert "STAT-PDPL-REGS" not in ids and "STAT-PDPL-REG" not in ids
    assert len(excluded) == 2
    assert all("counsel" in item for item in excluded)


def test_the_excluded_rows_are_named_so_the_counts_reconcile(statutory):
    """Twelve in the register, ten in the brief. Silently dropping two
    leaves a reader unable to tell a routing decision from an omission."""
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "Not in this table, and why" in text
    assert "PDPL controller registration" in text
    assert f"{len(statutory['obligations'])} class 1 obligations" in text
    assert f"{len(rows)} of them are tax matters" in text


def test_the_brief_leaves_the_company_from_a_person(statutory):
    """§10. The external gate never opens, for anyone, in any mode."""
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "never from Control (§10)" in text


def test_promotion_still_requires_a_named_human(statutory):
    """§7 of the execution order makes it a stop condition, and the
    brief says so rather than implying the answers apply themselves."""
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "will not promote a rule to verified without a named person" in text
    assert "may never modify a statutory deadline" in text


def test_the_brief_is_bilingual(statutory):
    """§4. The Arabic carries the same request and is authoritative."""
    rows, excluded = build_rows(statutory, {})
    text = render(rows, statutory, TODAY, excluded)
    assert "تصحيح أو تأكيد" in text
    assert "أرشيف الإقرارات الكامل" in text
    assert "النص العربي هو النص المعتمد" in text
