import json
from datetime import datetime

import pytest

from control import HaltError
from control.discovery.outlook_scan import run_outlook_scan, scan_folder
from tests.test_outlook import (
    FakeAttachment,
    FakeFolder,
    FakeItem,
    FakeNamespace,
    FakeStore,
)

CONTROL = "control@ubcsis.com"


def _items():
    return [
        FakeItem(entry_id="1", sender="donia@ubcsis.com", subject="RFQ 114",
                 to=CONTROL, received=datetime(2026, 5, 4, 9, 0),
                 attachments=[FakeAttachment("RFQ-114.pdf", b"x")]),
        FakeItem(entry_id="2", sender="donia@ubcsis.com", subject="RFQ 115",
                 to="ahmed@ubcsis.com", received=datetime(2026, 5, 20, 9, 0)),
        FakeItem(entry_id="3", sender="buyer@canalsugar.com", subject="PO 900",
                 to=CONTROL, cc="info@ubcsis.com",
                 received=datetime(2026, 6, 1, 9, 0),
                 attachments=[FakeAttachment("PO-900.xlsx", b"x")]),
        FakeItem(entry_id="4", sender="rep@siemens-energy.com", subject="Prequal",
                 to="info@ubcsis.com", received=datetime(2026, 6, 15, 9, 0)),
    ]


def test_scan_collects_metadata_and_stats():
    folder = FakeFolder("Inbox", _items())
    rows, summary = scan_folder(folder, mailbox=CONTROL, folder_name="Inbox")

    assert summary.total == 4
    assert summary.with_attachments == 2
    assert summary.internal_count == 2
    assert summary.external_count == 2
    assert summary.earliest == "04-May-2026" and summary.latest == "15-Jun-2026"
    assert summary.by_month == {"2026-05": 2, "2026-06": 2}
    assert dict(summary.top_senders)["donia@ubcsis.com"] == 2
    assert dict(summary.external_domains)["canalsugar.com"] == 1
    assert summary.attachment_types == {"pdf": 1, "xlsx": 1}
    # CC-discipline evidence for O-05: 2 of 4 reached control@
    assert summary.copied_to_control == 2
    # metadata only - no body field is ever emitted
    assert all("body" not in row for row in rows)
    assert rows[0]["attachments"] == ["RFQ-114.pdf"]


def test_non_mail_items_are_counted_not_crashed():
    class Appointment:
        Subject = "Site visit"

    folder = FakeFolder("Inbox", [Appointment(), *_items()])
    _rows, summary = scan_folder(folder, mailbox=CONTROL, folder_name="Inbox")
    assert summary.skipped_non_mail == 1
    assert summary.total == 4


def test_limit_caps_the_scan():
    folder = FakeFolder("Inbox", _items())
    _rows, summary = scan_folder(folder, mailbox=CONTROL, folder_name="Inbox", limit=2)
    assert summary.total == 2


def test_run_writes_jsonl_and_report(tmp_path):
    store = FakeStore(CONTROL, [FakeFolder("Inbox", _items()),
                                FakeFolder("Sent Items", [])])
    namespace = FakeNamespace([store])
    summaries = run_outlook_scan(namespace, CONTROL, ["Inbox"], tmp_path)

    assert len(summaries) == 1
    jsonl = tmp_path / "outlook-scan-control_at_ubcsis_com.jsonl"
    lines = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 4

    report = (tmp_path / "OUTLOOK-SCAN-control_at_ubcsis_com.md").read_text(encoding="utf-8")
    assert "Metadata only" in report
    assert "copied to control@: 2" in report
    assert "canalsugar.com" in report


def test_unknown_mailbox_halts(tmp_path):
    namespace = FakeNamespace([FakeStore("someone@ubcsis.com", [FakeFolder("Inbox")])])
    with pytest.raises(HaltError, match="not in this Outlook profile"):
        run_outlook_scan(namespace, CONTROL, ["Inbox"], tmp_path)
