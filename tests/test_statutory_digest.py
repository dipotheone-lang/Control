"""The statutory horizon as a page — D-15, §2.1, §4.

Scope B was decided with the tax advisor unengaged and Graph
unprovisioned, and the CEO instructed proceeding without either. Neither
blocks the work: Graph is only needed to send, and §2.1 has unverified
rules alerting early provided they are marked as unverified rather than
presented as confirmed.
"""

from datetime import date

from control.statutory_digest import build, render

TODAY = date(2026, 8, 30)


def calendar(rows):
    return {"obligations": rows}


VAT = {"id": "STAT-VAT", "name": "VAT return and payment",
       "owner": "accounts@ubcsis.com", "cadence": "monthly",
       "rule": "day 20"}


def test_a_dated_rule_reaches_the_page():
    digest = build(calendar([VAT]), TODAY)
    assert [r.item_id for r in digest.rows] == ["STAT-VAT"]
    assert "VAT return and payment" in render(digest, TODAY)


def test_an_unverified_date_alerts_and_says_it_is_unverified():
    """§2.1: unverified rules still alert, erring early. What is
    forbidden is presenting one as verified."""
    text = render(build(calendar([VAT]), TODAY), TODAY)
    assert "[UNVERIFIED]" in text
    assert "NO RULE HERE HAS BEEN CONFIRMED BY A TAX ADVISOR" in text
    assert "prompt to verify, not as the deadline itself" in text


def test_a_verified_rule_loses_the_marking():
    verified = dict(VAT, verified_by_advisor=True)
    text = render(build(calendar([verified]), TODAY), TODAY)
    assert "[UNVERIFIED]" not in text
    assert "NO RULE HERE HAS BEEN CONFIRMED" not in text


def test_a_rule_with_no_usable_date_is_reported_not_dropped():
    """A silent class 1 register is the most expensive silence in this
    system (§1.1). The gap is the finding."""
    pending = {"id": "STAT-PAYROLL", "name": "Payroll tax",
               "owner": "accounts@ubcsis.com",
               "rule": "UNVERIFIED — quarterly dates pending"}
    digest = build(calendar([pending]), TODAY)
    assert digest.rows == []
    text = render(digest, TODAY)
    assert "WHAT IS NOT COUNTING DOWN — 1" in text
    assert "highest-priority gap in the system" in text


def test_an_empty_window_is_not_reported_as_a_clear_one():
    pending = {"id": "STAT-REG", "name": "Commercial register renewal",
               "rule": "UNVERIFIED — renewal dates pending"}
    text = render(build(calendar([pending]), TODAY), TODAY)
    assert "an empty window, not a clear one" in text


def test_the_alert_schedule_is_marked_rather_than_left_to_arithmetic():
    """§2.1 alerts at T-7, T-3, T-1 and on the day. A reader should not
    have to subtract to find out which rows are live."""
    soon = dict(VAT, rule="2026-09-02")
    text = render(build(calendar([soon]), TODAY), TODAY)
    assert " *   T-3" in text or "*    T-3" in text.replace("  ", " ")


def test_the_page_is_bilingual_in_full():
    """§4: both languages, in full, Western Arabic numerals in both, and
    the Arabic authoritative."""
    text = render(build(calendar([VAT]), TODAY), TODAY)
    assert "الالتزامات القانونية" in text
    assert "المسؤول:" in text
    assert "النص العربي هو النص المعتمد" in text
    # Western numerals in the Arabic half — Eastern ones break Excel paste.
    assert "٢٠٢٦" not in text


def test_the_page_states_that_it_sends_nothing():
    """D-15's whole basis. A page that could be mistaken for an outgoing
    notice would misrepresent the scope it was produced under."""
    text = render(build(calendar([VAT]), TODAY), TODAY)
    assert "sends nothing" in text
    assert "reads no mailbox" in text


def test_it_agrees_with_the_engine_about_what_is_tracked():
    """The trap the status page fell into once: a second reading of the
    same config, disagreeing with the engine about what is tracked."""
    from control.loader import build_statutory

    rows = [VAT, {"id": "STAT-X", "name": "Pending",
                  "rule": "UNVERIFIED — pending"}]
    tracked, _ = build_statutory(calendar(rows), TODAY)
    digest = build(calendar(rows), TODAY, horizon_days=3650)
    assert {r.item_id for r in digest.rows} == {t.item_id for t in tracked}


# ---- the missing dates ------------------------------------------------

PENDING = {"id": "STAT-REG", "name": "Commercial register renewal",
           "owner": "accounts@ubcsis.com", "preparer": "hadeer@ubcsis.com",
           "rule": "UNVERIFIED — renewal dates pending (Mohamed Ali)",
           "open_question": "renewal dates x 3"}

BY_DESIGN = {"id": "STAT-ETA-REJ", "name": "ETA rejection clearance",
             "rule": "7 days from rejection", "mechanism": "event_window"}


def test_a_rule_waiting_on_an_answer_is_separated_from_one_that_is_not():
    """The split that decides whether the page gets acted on: a rule
    somebody can answer today, and a rule waiting on something else."""
    from control.statutory_digest import missing_dates

    answerable, unanswerable = missing_dates(
        calendar([VAT, PENDING, BY_DESIGN]), TODAY)
    assert [r["id"] for r in answerable] == ["STAT-REG"]
    assert [r["id"] for r in unanswerable] == ["STAT-ETA-REJ"]


def test_the_question_and_the_holder_are_quoted_not_inferred():
    """§1.1 and §14.2 Tier C. Control asks; it does not parse a name out
    of prose and it does not propose a statutory date."""
    from control.statutory_digest import render_missing

    text = render_missing(calendar([VAT, PENDING]), TODAY)
    assert "renewal dates x 3" in text
    # The holder reaches the page only inside the register's own line.
    assert "rule: UNVERIFIED — renewal dates pending (Mohamed Ali)" in text
    assert "does not propose a" in text and "date" in text
    assert "hadeer@ubcsis.com" in text


def test_the_mechanism_separates_by_design_from_simply_unset():
    """Without it the list blurs an obligation with no deadline by
    design and one waiting on a date nobody has set."""
    from control.statutory_digest import render_missing

    text = render_missing(calendar([BY_DESIGN]), TODAY)
    assert "mechanism: event_window" in text
    assert "chased by" in text and "nothing" in text


def test_a_rule_with_no_mechanism_recorded_says_so_rather_than_blank():
    from control.statutory_digest import render_missing

    text = render_missing(
        calendar([{"id": "STAT-X", "name": "X", "rule": "UNVERIFIED — pending"}]),
        TODAY)
    assert "mechanism: NOT RECORDED" in text


def test_the_missing_page_is_bilingual():
    from control.statutory_digest import render_missing

    text = render_missing(calendar([PENDING]), TODAY)
    assert "الفئة 1 — التواريخ الناقصة" in text
    assert "النص العربي هو النص المعتمد" in text
    assert "٢٠٢٦" not in text
