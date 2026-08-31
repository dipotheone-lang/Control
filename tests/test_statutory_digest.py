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


# ---- the live register ------------------------------------------------

def _live_calendar():
    import yaml

    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "config" / "statutory-calendar.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_rule_awaiting_a_date_carries_a_question():
    """The drift this caught once, asserted so it cannot return.

    The engine classifies a silent rule as awaiting a date; the
    missing-dates page splits on whether a question is recorded against
    it. A rule in the first set but not the second is waiting on an
    answer that nothing is asking for — which is how STAT-PDPL-REGS sat
    silent with nobody chasing it.
    """
    from control.loader import SILENCE_AWAITING_DATE, _no_countdown, parse_due
    from control.statutory_digest import missing_dates

    config = _live_calendar()
    awaiting = set()
    for row in config["obligations"]:
        due, problem = parse_due(str(row.get("rule") or ""),
                                 str(row.get("cadence") or ""), TODAY)
        if due is not None:
            continue
        if _no_countdown(row, problem)[0] == SILENCE_AWAITING_DATE:
            awaiting.add(str(row["id"]))

    answerable, _ = missing_dates(config, TODAY)
    assert awaiting == {str(r["id"]) for r in answerable}, (
        "a rule is awaiting a date with no open_question recorded — "
        "nothing is chasing it")


def test_the_routing_field_is_not_read_as_the_holder_of_the_date():
    """`answered_by` routes an obligation's subject away from the tax
    advisor brief. Printed as "answered by" under a missing date it said
    the wrong thing — on STAT-PDPL-REGS the subject was counsel's while
    the date was an internal scheduling choice, so the page read as
    though counsel had to be asked for a calendar entry.

    Written against a fixture rather than the live register: which live
    rows are still open changes as they are answered, and a test that
    drifts with the data is testing the data.
    """
    from control.statutory_digest import render_missing

    row = dict(PENDING, answered_by="counsel")
    text = render_missing(calendar([row]), TODAY)
    assert "subject sits with counsel, not the tax advisor" in text
    assert "answered by:" not in text


# ---- the forwardable ask ----------------------------------------------

PEOPLE = {"people": [
    {"name": "Hadeer Mohamed", "email": "hadeer@ubcsis.com", "tier": 1},
    {"name": "Mohamed Ali", "email": "hr@ubcsis.com", "tier": 2},
]}


def test_requests_are_grouped_by_the_person_who_holds_the_answer():
    from control.statutory_digest import render_ask

    rows = [dict(PENDING, id="STAT-REG", answer_held_by="hr@ubcsis.com"),
            {"id": "STAT-PAYROLL", "name": "Payroll tax",
             "rule": "UNVERIFIED — quarterly dates pending",
             "open_question": "payroll tax quarterly dates",
             "answer_held_by": "hadeer@ubcsis.com"}]
    text = render_ask(calendar(rows), TODAY, PEOPLE)

    assert "TO: Hadeer Mohamed <hadeer@ubcsis.com>" in text
    assert "TO: Mohamed Ali <hr@ubcsis.com>" in text
    # Each person sees only what they can answer.
    hadeer = text.split("TO: Hadeer Mohamed")[1].split("TO: Mohamed Ali")[0]
    assert "payroll tax quarterly dates" in hadeer
    assert "renewal dates x 3" not in hadeer


def test_a_row_with_no_holder_is_listed_rather_than_guessed_at():
    """A name in the `rule` prose is not a routable address. Control does
    not parse one out, so an unrouted row is named as unrouted (§1.1)."""
    from control.statutory_digest import render_ask

    rows = [{"id": "STAT-X", "name": "Something",
             "rule": "UNVERIFIED — pending (Mohamed Ali)",
             "open_question": "the date"}]
    text = render_ask(calendar(rows), TODAY, PEOPLE)

    assert "NO HOLDER RECORDED — 1" in text
    assert "STAT-X — the date" in text
    assert "TO:" not in text, "an unrouted row must not be addressed to anyone"


def test_the_request_is_bilingual_and_does_not_blame_the_reader():
    """§4 in full, and §1.4: the message addresses a gap in the records,
    never the person's conduct."""
    from control.statutory_digest import render_ask

    rows = [dict(PENDING, answer_held_by="hr@ubcsis.com")]
    text = render_ask(calendar(rows), TODAY, PEOPLE)

    assert "المطلوب:" in text and "النص العربي هو النص المعتمد" in text
    assert "This is a gap in the records, not a question about your work." in text
    assert "٢٠٢٦" not in text
    # D-62: the run sends these; the page must say what actually happens
    # rather than keep the pre-D-62 claim that only the CEO sends.
    assert "D-62" in text and "internal ubcsis.com addresses only" in text


def test_one_item_is_not_reported_as_one_items():
    from control.statutory_digest import render_ask

    text = render_ask(calendar([dict(PENDING, answer_held_by="hr@ubcsis.com")]),
                      TODAY, PEOPLE)
    assert "1 item" in text and "1 items" not in text


def test_nothing_outstanding_says_so():
    from control.statutory_digest import render_ask

    text = render_ask(calendar([VAT]), TODAY, PEOPLE)
    assert "Nothing outstanding" in text
    assert "TO:" not in text


def test_the_live_register_routes_every_open_question():
    """Whoever holds an answer must be reachable from a field. If this
    fails, a real outstanding date is sitting in the register with
    nobody being asked for it."""
    from control.statutory_digest import render_ask

    text = render_ask(_live_calendar(), TODAY, PEOPLE)
    assert "NO HOLDER RECORDED" not in text


# ---- D-62: the run sends the requests itself --------------------------
#
# The CEO's instruction of 31-Aug-2026: the system was built to send
# email, not to hand the CEO a page to forward. These tests pin the
# bounds that made that instruction safe to take: internal addresses
# only, weekly not daily, self-terminating, and never guessing a
# recipient.

def test_ask_messages_addresses_the_holder_and_ccs_the_owner():
    from control.statutory_digest import ask_messages

    rows = [dict(PENDING, answer_held_by="hr@ubcsis.com")]
    messages, unrouted = ask_messages(calendar(rows), TODAY, PEOPLE)

    assert unrouted == []
    assert len(messages) == 1
    msg = messages[0]
    assert msg.holder == "hr@ubcsis.com"
    assert msg.holder_name == "Mohamed Ali"
    assert msg.cc == ["accounts@ubcsis.com"]
    assert msg.rule_ids == ["STAT-REG"]
    assert "1 item" in msg.subject and "1 items" not in msg.subject


def test_the_sent_body_and_the_page_are_the_same_text():
    """§13.1 bilingual equivalence has one cheap enforcement: a single
    source. If the page and the email could drift, the page would stop
    being a record of what went out."""
    from control.statutory_digest import ask_messages, render_ask

    rows = [dict(PENDING, answer_held_by="hr@ubcsis.com")]
    messages, _ = ask_messages(calendar(rows), TODAY, PEOPLE)
    page = render_ask(calendar(rows), TODAY, PEOPLE)

    assert messages[0].body in page
    assert "النص العربي هو النص المعتمد" in messages[0].body


def test_an_unrouted_row_produces_no_message():
    from control.statutory_digest import ask_messages

    rows = [{"id": "STAT-X", "name": "Something",
             "rule": "UNVERIFIED — pending (Mohamed Ali)",
             "open_question": "the date"}]
    messages, unrouted = ask_messages(calendar(rows), TODAY, PEOPLE)

    assert messages == []
    assert [r.get("id") for r in unrouted] == ["STAT-X"]


def test_gate_row_sends_in_supervised_and_drafts_in_dry_run():
    from control.outbox import decide

    assert decide("REGISTER_GAP_REQUEST", "DRY_RUN") == "DRAFT"
    assert decide("REGISTER_GAP_REQUEST", "SUPERVISED") == "SEND"
    assert decide("REGISTER_GAP_REQUEST", "LIVE") == "SEND"
    assert decide("REGISTER_GAP_REQUEST", "DISCOVERY") == "DRAFT"


def _cycle_config(rows):
    return {"statutory-calendar": calendar(rows), "people": PEOPLE}


def test_gap_requests_are_internal_only_and_external_holders_are_refused():
    """D-62 changed who sends, not who may receive. A holder outside
    ubcsis.com gets nothing, and the refusal is reported rather than
    silent — the block stays on the page to forward by hand."""
    from control.__main__ import _gap_request_messages

    rows = [dict(PENDING, answer_held_by="hr@ubcsis.com"),
            {"id": "STAT-Y", "name": "Other", "rule": "UNVERIFIED — pending",
             "open_question": "the date",
             "answer_held_by": "advisor@taxfirm-egypt.com"}]
    messages, notes = _gap_request_messages(_cycle_config(rows), TODAY)

    assert [m.recipients for m in messages] == [["hr@ubcsis.com"]]
    assert any("advisor@taxfirm-egypt.com" in n and "refused" in n
               for n in notes)


def test_gap_request_cc_never_carries_an_external_address():
    from control.__main__ import _gap_request_messages

    rows = [dict(PENDING, owner="outside@gmail.com",
                 answer_held_by="hr@ubcsis.com")]
    messages, _ = _gap_request_messages(_cycle_config(rows), TODAY)

    assert messages[0].cc == []


def test_gap_requests_ask_weekly_not_daily():
    """Same week, same key — the outbox dedupe holds it. Next week, a
    new key — the question asks again. A daily nag teaches people to
    filter the sender, which silences the class 1 alerts travelling
    under the same name."""
    from control.__main__ import _gap_request_messages

    rows = [dict(PENDING, answer_held_by="hr@ubcsis.com")]
    config = _cycle_config(rows)

    monday, _ = _gap_request_messages(config, date(2026, 8, 31))
    thursday, _ = _gap_request_messages(config, date(2026, 9, 3))
    next_week, _ = _gap_request_messages(config, date(2026, 9, 7))

    assert monday[0].dedupe_key == thursday[0].dedupe_key
    assert monday[0].dedupe_key != next_week[0].dedupe_key
    assert "GAPASK/hr@ubcsis.com/STAT-REG/" in monday[0].dedupe_key


def test_gap_requests_stop_the_moment_the_register_gains_the_date():
    from control.__main__ import _gap_request_messages

    answered = dict(PENDING, rule="15 January",
                    answer_held_by="hr@ubcsis.com")
    messages, _ = _gap_request_messages(_cycle_config([answered]), TODAY)

    assert messages == []


def test_a_rule_with_a_question_and_no_holder_is_a_reported_gap():
    from control.__main__ import _gap_request_messages

    rows = [{"id": "STAT-X", "name": "Something",
             "rule": "UNVERIFIED — pending", "open_question": "the date"}]
    _, notes = _gap_request_messages(_cycle_config(rows), TODAY)

    assert any("STAT-X" in n and "answer_held_by" in n for n in notes)
