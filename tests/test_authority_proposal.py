"""Delegated limits read out of the delegation documents — O-02, §3.2.

D-06 set the interim on 16-Aug-2026 to observe one month of real
commitment volume, so thresholds would come from evidence rather than
estimate. Phase 0 records no transactions, so that month produced none:
the review due 16-Sep-2026 would arrive with the evidence it started
with. `13. Delegations` predates the interim and answers the same
question.
"""

from datetime import date

from control.discovery.authority_proposal import Proposal, extract, render, to_yaml

TODAY = date(2026, 8, 30)

DOCUMENT = (
    "DELEGATION OF AUTHORITY — approved 12/01/2026\n"
    "The Head of Procurement is authorised to approve purchase orders up to "
    "EGP 250,000.\n"
    "Commitments not exceeding LE 1,000,000 may be approved by the Chief "
    "Operating Officer.\n"
)


def test_an_amount_inside_an_authority_statement_is_a_candidate():
    found = extract(DOCUMENT, "Delegation 2026.docx")
    assert {c.amount for c in found} == {250000.0, 1000000.0}
    assert all(c.currency == "EGP" for c in found)


def test_a_year_is_not_a_limit():
    """A delegation document is full of dates, and 2026 with no currency
    beside it is one."""
    assert extract("Approved 12/01/2026 under the authority of the Board.",
                   "x.docx") == []


def test_an_amount_with_no_authority_wording_is_not_a_limit():
    """An amount alone is a number in a contract. An amount inside "may
    approve up to" is a delegated limit, and that difference is the only
    thing that makes the document worth reading."""
    assert extract("The contract value is EGP 4,500,000 in total.",
                   "x.docx") == []


def test_arabic_authority_wording_is_read():
    found = extract("تفويض: يحق للمدير اعتماد المشتريات حتى مبلغ 250,000 جنيه",
                    "x.docx")
    assert found and found[0].amount == 250000.0
    assert found[0].currency == "EGP"


def test_a_currency_that_was_not_stated_says_so():
    """§5.2 requires a currency code on every monetary field. A limit
    read as EGP when the document said USD is a control that passes the
    transactions it exists to stop."""
    found = extract("The manager may approve up to 250,000 per order.",
                    "x.docx")
    assert found and found[0].currency == "NOT STATED"


def test_the_holder_is_never_inferred():
    """A delegation document names a role. Mapping it to an address is a
    judgement about who holds what authority — the substance of the
    decision, not a step towards it — and a guessed holder would put a
    fabricated limit into the check that decides whether a commitment
    needed a second signature (§7.3 S2)."""
    found = extract(DOCUMENT, "Delegation 2026.docx")
    assert all(c.holder == "" for c in found)

    proposal = Proposal(candidates=found, documents_read=1)
    assert "holder: ''" in to_yaml(proposal, TODAY)
    assert "holder column is deliberately empty" in render(proposal, TODAY)


def test_nothing_proposed_is_in_force():
    """§14.2 Tier C: authority limits are never applied by the system,
    and §10 makes anything touching authority a Never in every mode."""
    text = render(Proposal(candidates=extract(DOCUMENT, "d.docx"),
                           documents_read=1), TODAY)
    assert "Nothing here is in force" in text
    assert "Tier C" in text
    assert "edited by a person or not at all" in text


def test_an_empty_result_is_a_finding_about_the_documents():
    text = render(Proposal(documents_read=17, documents_with_no_amount=17),
                  TODAY)
    assert "No candidate limits found" in text
    assert "a finding about the documents, not a reading of them" in text
    assert "OCR floor" in text
