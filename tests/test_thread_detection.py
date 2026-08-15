"""A conversation is not a recurrence.

From the second real Phase 0 run: 'price offer for structural
reinforcement' appeared as n=16 from info@ubcsis.com AND n=8 from
ahmed.ezz@eg.ivldhunseri.com — one negotiation counted from both ends,
presented as two recurring obligations on a ~3-day cadence. Subject
normalisation strips Re:/Fw:, so a long thread collapses into what
looks like a series.
"""

from datetime import datetime, timedelta

from control.discovery.analyse import infer_obligations, render_stage_d

INFO = "info@ubcsis.com"
CLIENT = "ahmed.ezz@eg.ivldhunseri.com"
SITE = "a.elsayed@ubcsis.com"


def _row(sender, subject, received):
    return {"mailbox": "sales@ubcsis.com", "folder": "Inbox", "sender": sender,
            "to": "sales@ubcsis.com", "cc": "",
            "received": received.isoformat(), "subject": subject,
            "attachments": []}


def test_negotiation_thread_is_not_an_obligation():
    start = datetime(2026, 5, 4, 9, 0)
    rows = [_row(INFO, "Price offer for structural reinforcement of floor", start)]
    rows += [_row(INFO, "RE: Price offer for structural reinforcement of floor",
                  start + timedelta(days=3 * i)) for i in range(1, 16)]

    candidate = infer_obligations(rows)[0]
    assert candidate.pattern_kind == "THREAD"
    assert candidate.confidence == "LOW"
    assert "conversation" in candidate.cadence
    assert candidate.reply_ratio >= 0.9


def test_fresh_sends_stay_recurring_even_at_the_same_cadence():
    """The distinguishing feature is replies, not timing."""
    start = datetime(2026, 1, 4, 9, 0)
    rows = [_row(SITE, f"Weekly Progress Report - Week {i}",
                 start + timedelta(days=7 * i)) for i in range(14)]
    candidate = infer_obligations(rows)[0]
    assert candidate.pattern_kind == "RECURRING"
    assert candidate.confidence == "HIGH"
    assert candidate.reply_ratio == 0.0


def test_mixed_series_with_few_replies_is_still_recurring():
    """A recurring report someone occasionally replies to is still a report."""
    start = datetime(2026, 1, 4, 9, 0)
    rows = [_row(SITE, f"Weekly Progress Report - Week {i}",
                 start + timedelta(days=7 * i)) for i in range(12)]
    rows += [_row(SITE, "RE: Weekly Progress Report - Week 3",
                  start + timedelta(days=22)),
             _row(SITE, "RE: Weekly Progress Report - Week 7",
                  start + timedelta(days=50))]
    candidate = infer_obligations(rows)[0]
    assert candidate.pattern_kind == "RECURRING"
    assert candidate.reply_ratio < 0.5


def test_arabic_reply_prefix_recognised():
    start = datetime(2026, 5, 4, 9, 0)
    rows = [_row(CLIENT, "عرض سعر", start)]
    rows += [_row(CLIENT, "رد: عرض سعر", start + timedelta(days=i))
             for i in range(1, 8)]
    assert infer_obligations(rows)[0].pattern_kind == "THREAD"


def test_report_gives_threads_their_own_section_and_says_why_they_matter():
    start = datetime(2026, 5, 4, 9, 0)
    rows = [_row(INFO, "Price offer for manlift rental", start)]
    rows += [_row(INFO, "RE: Price offer for manlift rental",
                  start + timedelta(days=2 * i)) for i in range(1, 10)]

    text = render_stage_d(infer_obligations(rows), "sales@ubcsis.com")
    _before, _, threads_section = text.partition("## Conversations — NOT obligations")

    assert "price offer for manlift rental" in threads_section
    # The commercial significance must not be lost by demoting them
    assert "most commercially interesting" in threads_section
    assert "2.2 commercial cycle" in threads_section or "§2.2" in threads_section
