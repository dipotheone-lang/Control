import json
from datetime import datetime, timedelta

from control.discovery.deliverables import (
    build_results,
    write_confidential_scope,
    write_discovery_report,
    write_paste_summary,
)

INFO = "info@ubcsis.com"
SITE = "a.elsayed@ubcsis.com"


def _write_scan(tmp_path, mailbox, rows):
    stem = mailbox.replace("@", "_at_").replace(".", "_")
    path = tmp_path / f"outlook-scan-{stem}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path


def _row(sender, subject, received, folder="Inbox", to=INFO, cc=""):
    return {"mailbox": INFO, "folder": folder, "sender": sender, "to": to,
            "cc": cc, "received": received.isoformat(), "subject": subject,
            "attachments": ["FRM-WPR.xlsx"]}


def _weekly_rows(n=14):
    start = datetime(2026, 1, 4, 9, 0)
    return [_row(SITE, f"Weekly Progress Report - Week {i}",
                 start + timedelta(days=7 * i)) for i in range(n)]


def test_discovery_report_leads_with_ten_things(tmp_path):
    _write_scan(tmp_path, INFO, _weekly_rows())
    results = build_results(tmp_path)
    text = write_discovery_report(results, tmp_path).read_text(encoding="utf-8")

    assert "The ten things you most need to know" in text
    for n in range(1, 11):
        assert f"\n{n}. " in text
    assert "high-confidence recurring patterns" in text
    # It must refuse to overclaim
    assert "Nothing in this report is an obligation" in text
    assert "Statutory deadlines are absent from this evidence" in text
    assert "A gap is a finding" in text


def test_report_flags_missing_sent_items(tmp_path):
    rows = _weekly_rows() + [_row("buyer@canalsugar.com", "PO 900",
                                  datetime(2026, 5, 1, 9, 0))]
    _write_scan(tmp_path, INFO, rows)
    results = build_results(tmp_path)
    text = write_discovery_report(results, tmp_path).read_text(encoding="utf-8")
    assert "unreliable: Sent Items was missing" in text


def test_report_credits_sent_items_when_present(tmp_path):
    rows = [
        _row("buyer@canalsugar.com", "PO 900", datetime(2026, 5, 1, 9, 0)),
        _row(INFO, "RE: PO 900", datetime(2026, 5, 1, 12, 0), folder="Sent Items"),
    ]
    _write_scan(tmp_path, INFO, rows)
    results = build_results(tmp_path)
    text = write_discovery_report(results, tmp_path).read_text(encoding="utf-8")
    assert "Sent Items was scanned, so this is a real signal" in text


def test_confidential_scope_matches_known_clients_and_defaults_others(tmp_path):
    rows = [
        _row("buyer@canalsugar.com", "PO 1", datetime(2026, 5, 1, 9, 0)),
        _row("rep@knauf.com", "Prequal", datetime(2026, 5, 2, 9, 0)),
        _row("someone@randomvendor.net", "Quote", datetime(2026, 5, 3, 9, 0)),
    ]
    _write_scan(tmp_path, INFO, rows)
    results = build_results(tmp_path)
    text = write_confidential_scope(results, tmp_path).read_text(encoding="utf-8")

    assert "Canal Sugar" in text and "KNAUF" in text
    assert "randomvendor.net" in text
    assert "CONFIDENTIAL (default, unconfirmed)" in text
    assert "O-04" in text
    # honest about what domain matching cannot see
    assert "not by contract" in text
    assert "Absence from this list is not evidence" in text


def test_gaps_appear_in_report(tmp_path):
    _write_scan(tmp_path, INFO, _weekly_rows())
    results = build_results(tmp_path)
    text = write_discovery_report(
        results, tmp_path, gaps=["sales@ubcsis.com: not in this Outlook profile"]
    ).read_text(encoding="utf-8")
    assert "sales@ubcsis.com: not in this Outlook profile" in text
    assert "1 source(s) could not be read" in text


def test_paste_summary_is_short_and_useful(tmp_path):
    _write_scan(tmp_path, INFO, _weekly_rows())
    results = build_results(tmp_path)
    text = write_paste_summary(results, tmp_path,
                               gaps=["hr@: not in profile"]).read_text(encoding="utf-8")
    assert "PHASE 0 SUMMARY" in text
    assert "candidates: 1 HIGH" in text
    assert "sent items scanned: NO" in text
    assert "GAPS:" in text
    assert len(text.splitlines()) < 60          # a digest, not a report
