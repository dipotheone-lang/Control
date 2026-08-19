"""The gap register — execution order step 3.

*"Build the gap register from every open item... Type each one."*

The typing is the whole point. §6 of the same order says legal coverage
*"will read 0% and must stay visible at 0%. That is D-52 working, not
failing."* A single "open items: 55" hides that, because the factual
gaps close when someone looks something up and the legal ones do not
close until counsel is engaged — and a number that averages the two is
comfortable and meaningless.

So the tests here are mostly about refusing to total, refusing to
silently invent a third type, and refusing to make the counts agree
with the order's own numbers when they do not.
"""

from datetime import date
from pathlib import Path

import pytest

from control.gaps import (
    BUILD, FACTUAL, LEGAL, TYPES, collect, counts, from_charter,
    from_documents, from_execution_order, from_loader, reconcile, render,
)

REPO = Path(__file__).resolve().parent.parent
ORDER = REPO / "docs" / "decisions" / "EXECUTION-ORDER-18-Aug-2026.md"
CHARTER = REPO / "CLAUDE.md"
TODAY = date(2026, 8, 18)


@pytest.fixture(scope="module")
def order_text():
    return ORDER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def charter_text():
    return CHARTER.read_text(encoding="utf-8")


# ---- the order's own table --------------------------------------------

def test_the_seven_items_the_ceo_listed_are_all_read(order_text):
    """The bug this pins actually happened: the section was split on the
    substring "---", which is also the table's own separator row, so the
    table ended at its header and returned nothing. The register then
    reported seven factual gaps from a different source and looked
    entirely plausible."""
    found = from_execution_order(order_text)
    assert len(found) == 7
    texts = [g.text for g in found]
    assert "Registered address (commercial register)" in texts
    assert "Payroll tax quarterly dates" in texts


def test_the_legal_row_is_typed_legal_not_factual(order_text):
    """"All 12 legal positions — No counsel engaged" is the row that
    must never read as closable."""
    legal = [g for g in from_execution_order(order_text) if g.kind == LEGAL]
    assert len(legal) == 1
    assert "legal positions" in legal[0].text
    assert "No counsel engaged" in legal[0].owner


def test_the_owner_survives_from_the_table(order_text):
    """A typed gap with no owner is a list, not a register."""
    found = from_execution_order(order_text)
    assert all(g.owner for g in found)
    payroll = next(g for g in found if "Payroll tax" in g.text)
    assert payroll.owner == "Hadeer"


# ---- the charter's open decisions -------------------------------------

def test_closed_decisions_are_not_collected(charter_text):
    """O-01, O-05, O-09 and O-11 are struck through in Appendix B. A
    register that re-raised a closed decision would be chasing the CEO
    for something already answered."""
    ids = {g.gap_id for g in from_charter(charter_text)}
    assert "O-02" in ids and "O-03" in ids
    for closed in ("O-01", "O-05", "O-09", "O-11"):
        assert closed not in ids, closed


def test_the_advisor_and_counsel_decisions_are_legal(charter_text):
    """LEGAL here means "answered by a qualified outsider", not "about
    law" — O-03 is the tax advisor and closes no faster for that."""
    by_id = {g.gap_id: g for g in from_charter(charter_text)}
    assert by_id["O-03"].kind == LEGAL
    assert by_id["O-07"].kind == LEGAL
    assert by_id["O-02"].kind == FACTUAL


# ---- the governance drafts --------------------------------------------

def test_unanswered_fields_in_the_drafts_are_counted(tmp_path):
    """The drafts say `TO BE CONFIRMED` rather than supplying a
    plausible figure, deliberately. Deliberate is not closed, and a
    marker nobody counts survives into the signed version."""
    doc = tmp_path / "RETENTION-SCHEDULE.md"
    doc.write_text("Retention for X: TO BE CONFIRMED\n"
                   "Filing procedure: UNVERIFIED against the 2025 law\n"
                   "Settled: 5 years\n", encoding="utf-8")
    found = from_documents([doc])
    assert len(found) == 2
    assert all(g.kind == LEGAL for g in found)
    assert found[0].source.endswith(":1")


def test_the_advisor_brief_is_owned_by_the_advisor(tmp_path):
    doc = tmp_path / "TAX-ADVISOR-BRIEF.md"
    doc.write_text("VAT deadline: UNVERIFIED\n", encoding="utf-8")
    assert from_documents([doc])[0].owner == "tax advisor"


# ---- the live gaps ----------------------------------------------------

def test_a_missing_detector_is_build_not_factual():
    """Calling it FACTUAL would put "the ETA exception detector is not
    built" on Hadeer's list, and she cannot close it by looking
    anything up."""
    found = from_loader([
        "STAT-ETA-SUB: real-time, and that detector is not built, so "
        "nothing is watching it today.",
    ])
    assert found[0].kind == BUILD
    assert found[0].owner == "Control"


def test_a_statutory_gap_is_owned_by_the_advisor():
    found = from_loader([
        "STAT-REG: due expression not understood — no class 1 alert can "
        "fire (O-03)",
    ])
    assert found[0].kind == LEGAL
    assert found[0].owner == "tax advisor"


def test_a_long_finding_is_truncated_visibly():
    """A sentence that stops mid-word with no mark reads as the whole
    item, and the reader acts on half a finding."""
    found = from_loader(["x" * 400])
    assert found[0].text.endswith("…")
    assert len(found[0].text) <= 240


# ---- the register never totals ----------------------------------------

def test_the_report_counts_per_type_and_never_across_them(order_text,
                                                          charter_text):
    gaps = collect(order_text, charter_text, [], ["sla.yaml: no holidays"])
    text = render(gaps, TODAY)
    per_type = counts(gaps)
    for kind in TYPES:
        assert f"**{kind}: {per_type[kind]}**" in text
    assert "never totalled" in text
    # The one number that must not appear as a headline figure.
    assert f"open items: {len(gaps)}" not in text


def test_the_zero_percent_rule_is_stated_in_the_document(order_text,
                                                         charter_text):
    """§6: "Legal coverage will read 0% and must stay visible at 0%.
    That is D-52 working, not failing"."""
    text = render(collect(order_text, charter_text, [], []), TODAY)
    assert "must stay visible at 0%" in text


def test_the_third_type_declares_itself_as_controls_own(order_text,
                                                        charter_text):
    """§1.3 — ambiguous, escalate, never invent a rule. BUILD is a
    useful label the order does not name, so it says so on the page
    rather than being adopted quietly."""
    text = render(collect(order_text, charter_text, [], []), TODAY)
    assert "BUILD is Control's type, not the order's" in text
    assert "asked to confirm the third type" in text


def test_the_register_says_it_closes_nothing(order_text, charter_text):
    """B8 is the register AND a closure engine, under a §18 that does
    not exist in the charter. Only the register is built."""
    text = render(collect(order_text, charter_text, [], []), TODAY)
    assert "Nothing here closes itself" in text
    assert "§18 does not exist in the charter" in text


def test_the_headline_counts_are_computed_not_written(order_text,
                                                      charter_text):
    """The intro sentence quoted the factual count. Hardcoding it meant
    the prose and the list could disagree, which is the shape of defect
    this project keeps finding."""
    gaps = collect(order_text, charter_text, [], [])
    per_type = counts(gaps)
    text = render(gaps, TODAY)
    assert f"The {per_type[FACTUAL]} factual gaps close" in text
    assert f"{per_type[LEGAL]} legal ones do not close" in text


# ---- reconciliation with the order's own numbers ----------------------

def test_a_count_that_disagrees_with_the_order_is_reported_not_adjusted(
        order_text, charter_text):
    """Step 3 names "40 unverified answers". Control counts what it
    found and reports the difference rather than tuning the count until
    it matches (§1.1)."""
    gaps = collect(order_text, charter_text, [], [])
    notes = reconcile(gaps, order_text)
    assert any("40 unverified answers" in n for n in notes)
    assert any("Reported, not reconciled" in n for n in notes)


def test_a_matching_count_raises_nothing(order_text):
    """Seven rows in §6's table is what step 3's sentence says, so that
    half reconciles silently."""
    notes = reconcile(from_execution_order(order_text), order_text)
    assert not [n for n in notes if "missing data points" in n]
