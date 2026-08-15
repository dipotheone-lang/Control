import json
from datetime import datetime, timedelta

from control.discovery.analyse import (
    analyse_responses,
    infer_obligations,
    load_rows,
    normalise_subject,
    render_stage_d,
    render_stage_h,
)

SITE = "a.elsayed@ubcsis.com"
CLIENT = "buyer@canalsugar.com"
INFO = "info@ubcsis.com"


def _row(sender, subject, received, attachments=None, folder="Inbox"):
    return {
        "mailbox": INFO, "folder": folder, "sender": sender,
        "to": INFO, "cc": "", "received": received.isoformat(),
        "subject": subject, "attachments": attachments or [],
    }


def test_subject_normalisation_collapses_variants():
    assert normalise_subject("RE: Weekly Progress Report - Week 32") == \
           normalise_subject("Weekly Progress Report - Week 33")
    assert normalise_subject("FW: RE: Invoice 4501") == "invoice #"
    assert normalise_subject("  Multiple   spaces  ") == "multiple spaces"


def test_weekly_series_is_high_confidence():
    start = datetime(2026, 1, 4, 9, 0)
    rows = [
        _row(SITE, f"Weekly Progress Report - Week {i}",
             start + timedelta(days=7 * i), attachments=["FRM-WPR.xlsx"])
        for i in range(14)
    ]
    candidates = infer_obligations(rows)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.confidence == "HIGH"
    assert c.cadence == "weekly"
    assert c.occurrences == 14
    assert c.regular is True
    assert c.attachment_rate == 1.0
    assert "FRM-WPR.xlsx" in c.example_attachments


def test_monthly_series_detected():
    start = datetime(2026, 1, 31, 9, 0)
    rows = [_row("hadeer@ubcsis.com", f"Trial balance {i}",
                 start + timedelta(days=30 * i)) for i in range(6)]
    c = infer_obligations(rows)[0]
    assert c.cadence == "monthly"
    assert c.confidence == "MEDIUM"       # 6 occurrences: 4-11 band


def test_irregular_series_is_not_high_confidence():
    base = datetime(2026, 1, 1, 9, 0)
    offsets = [0, 2, 40, 41, 90, 91, 200, 201, 250, 251, 300, 340]
    rows = [_row(SITE, "Site update", base + timedelta(days=d)) for d in offsets]
    c = infer_obligations(rows)[0]
    assert c.regular is False
    assert c.confidence == "MEDIUM"       # 12+ but irregular -> not HIGH


def test_rare_patterns_are_excluded():
    rows = [_row(SITE, "One off", datetime(2026, 1, 1, 9, 0))]
    assert infer_obligations(rows) == []


def test_redacted_subjects_are_skipped():
    rows = [_row("x@ubcsis.com", "[REDACTED]", datetime(2026, 1, i + 1, 9, 0))
            for i in range(6)]
    assert infer_obligations(rows) == []


def test_response_matching_and_unanswered():
    inbound = datetime(2026, 5, 4, 9, 0)
    rows = [
        _row(CLIENT, "RFQ 114 pricing", inbound),
        _row(INFO, "RE: RFQ 114 pricing", inbound + timedelta(hours=5),
             folder="Sent Items"),
        _row(CLIENT, "RFQ 200 urgent", datetime(2026, 6, 1, 9, 0)),
    ]
    report = analyse_responses(rows)
    assert report.answered == 1
    assert report.unanswered == 1
    assert report.median_hours == 5.0
    assert report.sent_items_present is True


def test_reply_outside_window_is_not_a_reply():
    inbound = datetime(2026, 5, 4, 9, 0)
    rows = [
        _row(CLIENT, "RFQ 114", inbound),
        _row(INFO, "RE: RFQ 114", inbound + timedelta(days=45), folder="Sent Items"),
    ]
    assert analyse_responses(rows, window_days=30).unanswered == 1


def test_missing_sent_items_is_flagged_in_the_report():
    rows = [_row(CLIENT, "RFQ 114", datetime(2026, 5, 4, 9, 0))]
    report = analyse_responses(rows)
    assert report.sent_items_present is False
    text = render_stage_h(report, INFO)
    assert "Sent Items was not in this scan" in text
    assert "not 'no reply given'" in text


def test_stage_d_report_states_it_is_not_a_register():
    start = datetime(2026, 1, 4, 9, 0)
    rows = [_row(SITE, f"Weekly report {i}", start + timedelta(days=7 * i))
            for i in range(13)]
    text = render_stage_d(infer_obligations(rows), INFO)
    assert "Nothing here is an obligation until the CEO approves the register" in text
    assert "Absence of a pattern is not absence of an obligation" in text
    assert "HIGH" in text


def test_load_rows(tmp_path):
    path = tmp_path / "scan.jsonl"
    path.write_text(json.dumps(_row(SITE, "x", datetime(2026, 1, 1, 9, 0))) + "\n",
                    encoding="utf-8")
    assert len(load_rows(path)) == 1
