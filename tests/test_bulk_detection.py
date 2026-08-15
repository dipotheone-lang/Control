"""A burst is not a cadence.

From the first real Phase 0 run: sales@ubcsis.com returned six HIGH
confidence "obligations" that were outbound marketing campaigns —
"send us your next rfq?" (n=188), "should i close your file?" (n=43) —
all sent on a single day. The regularity test passed them trivially:
when every gap is zero, the spread is zero, so the series looked
perfectly regular. Marketing traffic reached the top of an obligation
register.
"""

from datetime import datetime, timedelta

from control.discovery.analyse import infer_obligations, render_stage_d

GMAIL = "contact.ubcsis@gmail.com"
SITE = "a.elsayed@ubcsis.com"


def _row(sender, subject, received):
    return {"mailbox": "sales@ubcsis.com", "folder": "Inbox", "sender": sender,
            "to": "sales@ubcsis.com", "cc": "",
            "received": received.isoformat(), "subject": subject,
            "attachments": []}


def test_single_day_blast_is_not_a_high_confidence_obligation():
    day = datetime(2026, 6, 1, 9, 0)
    rows = [_row(GMAIL, f"Send us your next RFQ? {i}", day + timedelta(minutes=i))
            for i in range(188)]
    candidate = infer_obligations(rows)[0]

    assert candidate.pattern_kind == "BULK"
    assert candidate.confidence == "LOW"        # never HIGH, whatever the volume
    assert candidate.regular is False
    assert "bulk send" in candidate.cadence
    assert candidate.distinct_days == 1


def test_campaign_over_a_few_days_is_still_bulk():
    start = datetime(2026, 6, 1, 9, 0)
    rows = []
    for day in range(3):
        for i in range(40):
            rows.append(_row(GMAIL, "United Brothers Co. - industrial supplies",
                             start + timedelta(days=day, minutes=i)))
    candidate = infer_obligations(rows)[0]
    assert candidate.pattern_kind == "BULK"
    assert candidate.per_active_day == 40.0


def test_genuine_weekly_series_is_unaffected():
    start = datetime(2026, 1, 4, 9, 0)
    rows = [_row(SITE, f"Weekly Progress Report - Week {i}",
                 start + timedelta(days=7 * i)) for i in range(14)]
    candidate = infer_obligations(rows)[0]
    assert candidate.pattern_kind == "RECURRING"
    assert candidate.confidence == "HIGH"
    assert candidate.cadence == "weekly"
    assert candidate.per_active_day == 1.0


def test_daily_report_is_recurring_not_bulk():
    """One a day is a cadence; four a day is a campaign."""
    start = datetime(2026, 3, 2, 8, 0)
    rows = [_row(SITE, f"Daily site log {i}", start + timedelta(days=i))
            for i in range(20)]
    candidate = infer_obligations(rows)[0]
    assert candidate.pattern_kind == "RECURRING"
    assert candidate.cadence == "daily"


def test_report_separates_bulk_from_candidates():
    day = datetime(2026, 6, 1, 9, 0)
    start = datetime(2026, 1, 4, 9, 0)
    rows = [_row(GMAIL, "Should I close your file?", day + timedelta(minutes=i))
            for i in range(43)]
    rows += [_row(SITE, f"Weekly Progress Report - Week {i}",
                  start + timedelta(days=7 * i)) for i in range(14)]

    text = render_stage_d(infer_obligations(rows), "sales@ubcsis.com")
    obligations, _, bulk_section = text.partition("## Bulk sends — NOT obligations")

    # Subject templates are normalised to lowercase.
    assert "weekly progress report" in obligations
    assert "should i close your file" not in obligations
    assert "should i close your file" in bulk_section
    assert "A burst is not a cadence" in bulk_section
    assert "not in the obligation register" in text
