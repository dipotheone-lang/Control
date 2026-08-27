"""Stage C terms to class 2 register rows — §2.2, §6.

`contracts` wrote COMMERCIAL-EXPOSURE.md and stopped. The 60/30/14/7-day
guarantee alerts run off the class 2 *registers*, populated by
`registers --import-file` from a YAML nothing produced — so a guarantee
expiry Stage C found sat in a markdown file and alerted on nothing.

These tests are about the wire between the two, and about it refusing to
invent the columns it does not have.
"""

from datetime import date

from control.discovery.class2_proposal import propose, render, to_yaml
from control.discovery.stage_c import CommercialTerm

TODAY = date(2026, 8, 27)


def term(**over):
    row = dict(kind="GUARANTEE_EXPIRY", source="7. Suppliers/Delta Steel.txt",
               context="Performance bond valid until 31 December 2026",
               found_date="2026-12-31", term_text="Performance bond")
    row.update(over)
    return CommercialTerm(**row)


def test_a_dated_guarantee_becomes_an_importable_row():
    rows = propose([term()], TODAY).rows["instruments"]
    assert rows[0]["instrument_type"] == "PERFORMANCE_BOND"
    assert rows[0]["expiry_date"] == "2026-12-31"
    assert rows[0]["status"] == "OPEN"
    # §5.2 — read out of a historical document, not received live.
    assert rows[0]["source"] == "BACKFILL"


def test_the_instrument_type_comes_from_the_matched_phrase():
    """Not from the context window, which spans neighbouring clauses by
    design — it is the citation. Reading the type out of it labelled a
    performance bond ADVANCE_PAYMENT_GUARANTEE because the next sentence
    mentioned one: the same disease as a date crossing a clause
    boundary, one field over."""
    rows = propose([term(
        context="Performance bond valid until 31 December 2026. Advance "
                "payment guarantee expires on 15 March 2027.",
        term_text="Performance bond")], TODAY).rows["instruments"]
    assert rows[0]["instrument_type"] == "PERFORMANCE_BOND"


def test_two_guarantees_in_one_document_keep_separate_references():
    """The register keys on `instrument_ref` and keeps one current row
    per key. With the file name as the reference, one supply agreement
    naming two guarantees produced two rows under one reference: the
    register accepted both and the horizon showed one. A guarantee
    silently gone from the register that exists to alert on it is §1.1's
    worst shape and §2.2's most expensive miss.
    """
    rows = propose([
        term(term_text="Performance bond", found_date="2026-12-31"),
        term(term_text="Advance payment guarantee", found_date="2027-03-15"),
    ], TODAY).rows["instruments"]
    assert len({r["instrument_ref"] for r in rows}) == 2
    # The file name still leads, so the document is findable.
    assert all(r["instrument_ref"].startswith("Delta Steel") for r in rows)


def test_a_unique_reference_is_left_readable():
    """Only collisions are extended. A generated id would not help
    whoever has to find the document again."""
    rows = propose([term()], TODAY).rows["instruments"]
    assert rows[0]["instrument_ref"] == "Delta Steel"


def test_the_same_scan_twice_proposes_the_same_references():
    """Deterministic, not counter-based: an append-only register must
    not gain a second copy of a guarantee because a scan was re-run."""
    terms = [term(term_text="Performance bond", found_date="2026-12-31"),
             term(term_text="Bid bond", found_date="2027-01-31")]
    first = propose(terms, TODAY).rows["instruments"]
    second = propose(terms, TODAY).rows["instruments"]
    assert [r["instrument_ref"] for r in first] == \
           [r["instrument_ref"] for r in second]


# ---- what is refused, and why -----------------------------------------

def _reason(terms):
    blocked = propose(terms, TODAY).blocked
    assert len(blocked) == 1
    return blocked[0]["reason"]


def test_a_confidential_guarantee_is_never_given_a_guessed_type():
    """D-05 extracts the date and redacts the clause text at capture, so
    which guarantee this is cannot be known without opening a
    confidential document. The schema demands one of five exact values;
    guessing would put a fabricated instrument type in the register of
    the company's largest clients."""
    reason = _reason([term(
        context="[REDACTED — D-05: date extracted, clause text not retained]",
        term_text="")])
    assert "redacted under D-05" in reason
    assert propose([term(context="[REDACTED", term_text="")],
                   TODAY).rows == {}


def test_an_expiry_already_passed_is_not_imported_as_open():
    """A 2023 expiry found in a 2021 document is most likely discharged.
    Importing it as OPEN fills the horizon with stale alerts, and a
    channel people learn to skim is a failed control (§13.3)."""
    assert "already passed" in _reason([term(found_date="2023-04-04")])


def test_an_undated_guarantee_is_reported_rather_than_dropped():
    assert "no date in the clause" in _reason([term(found_date="")])


def test_a_contract_term_is_not_forced_into_an_instrument_row():
    """A notice period is a duration running from an event. It belongs
    on a contract row, which needs a client this cannot read from a file
    path without guessing."""
    assert "not an instrument row" in _reason(
        [term(kind="NOTICE_PERIOD", found_date="", term_text="within 21 days")])


# ---- the files it writes ----------------------------------------------

def test_the_import_file_says_that_importing_is_the_decision():
    text = to_yaml(propose([term()], TODAY), TODAY)
    assert "NOTHING HERE IS" in text
    assert "registers --import-file" in text
    assert "instrument_type: PERFORMANCE_BOND" in text


def test_the_worksheet_leads_with_what_could_not_be_proposed():
    proposal = propose([term(), term(found_date="2023-01-01")], TODAY)
    text = render(proposal, TODAY)
    assert "1 row(s) ready to import" in text
    assert "1 term(s) that cannot become a row" in text
    assert "already passed" in text


def test_an_empty_proposal_says_which_kind_of_empty_it_is():
    text = render(propose([], TODAY), TODAY)
    assert "Ready to import — none" in text
    assert "a finding about the documents, not about the scan" in text


# ---- end to end, which is the only measure that matters ---------------

def test_every_proposed_row_reaches_the_horizon(tmp_path):
    """Three rows imported and two in the horizon was the actual bug,
    and nothing before this point could see it: the proposal was right,
    the import reported +3, and one guarantee was gone.
    """
    import yaml

    from control.db import init_db
    from control.registers import add_instrument, horizon

    proposal = propose([
        term(term_text="Performance bond", found_date="2026-12-31"),
        term(term_text="Advance payment guarantee", found_date="2027-03-15"),
        term(source="7. Suppliers/LG Nile Bank.txt",
             term_text="Letter of guarantee", found_date="2027-11-30"),
    ], TODAY)

    rows = yaml.safe_load(to_yaml(proposal, TODAY))["instruments"]
    assert len(rows) == 3

    conn = init_db(tmp_path / "control.db")
    try:
        for row in rows:
            add_instrument(conn, **row)
        conn.commit()
        due = {d.item.due.isoformat() for d in horizon(conn, TODAY, days=500)}
    finally:
        conn.close()

    assert due == {"2026-12-31", "2027-03-15", "2027-11-30"}
