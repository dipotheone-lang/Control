import json
from datetime import datetime

from control.discovery.outlook_scan import (
    run_outlook_scan,
    scan_folder,
    write_overview,
)
from tests.test_outlook import FakeFolder, FakeItem, FakeNamespace, FakeStore

CONTROL = "control@ubcsis.com"
INFO = "info@ubcsis.com"
HR = "hr@ubcsis.com"


def test_subject_redaction_keeps_everything_else():
    item = FakeItem(entry_id="1", sender="lawyer@firm.com",
                    subject="Termination of Mr X - final settlement",
                    received=datetime(2026, 5, 4, 9, 0))
    rows, summary = scan_folder(FakeFolder("Inbox", [item]), mailbox=HR,
                                folder_name="Inbox", redact_subjects=True)
    assert rows[0]["subject"] == "[REDACTED]"
    assert rows[0]["sender"] == "lawyer@firm.com"       # cadence data intact
    assert summary.external_count == 1


def test_empty_folder_list_scans_every_folder(tmp_path):
    store = FakeStore(INFO, [
        FakeFolder("Inbox", [FakeItem(entry_id="1", sender="a@x.com")]),
        FakeFolder("Sent Items", [FakeItem(entry_id="2", sender=INFO)]),
    ])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO, [], tmp_path)
    assert {s.folder for s in summaries} == {"Inbox", "Sent Items"}
    assert sum(s.total for s in summaries) == 2


def test_named_folders_are_filtered(tmp_path):
    store = FakeStore(INFO, [
        FakeFolder("Inbox", [FakeItem(entry_id="1", sender="a@x.com")]),
        FakeFolder("Sent Items", [FakeItem(entry_id="2", sender=INFO)]),
    ])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO, ["Inbox"], tmp_path)
    assert [s.folder for s in summaries] == ["Inbox"]


def test_overview_reports_cc_coverage(tmp_path):
    info_items = [
        FakeItem(entry_id="1", sender="buyer@canalsugar.com", to=INFO,
                 received=datetime(2026, 5, 1, 9, 0)),
        FakeItem(entry_id="2", sender="rep@knauf.com", to=INFO,
                 received=datetime(2026, 5, 2, 9, 0)),
        FakeItem(entry_id="3", sender="x@sukari.com", to=INFO, cc=CONTROL,
                 received=datetime(2026, 5, 3, 9, 0)),
    ]
    store = FakeStore(INFO, [FakeFolder("Inbox", info_items)])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO, ["Inbox"], tmp_path)
    path = write_overview({INFO: summaries}, tmp_path)
    text = path.read_text(encoding="utf-8")

    assert "CC-discipline coverage: **33.3%**" in text     # 1 of 3 external
    assert "O-05" in text
    assert "cannot tell you" in text
    assert "Commercial value" in text


def test_overview_lists_each_mailbox(tmp_path):
    stores = [
        FakeStore(INFO, [FakeFolder("Inbox", [FakeItem(entry_id="1", sender="a@x.com")])]),
        FakeStore(HR, [FakeFolder("Inbox", [FakeItem(entry_id="2", sender="b@y.com")])]),
    ]
    namespace = FakeNamespace(stores)
    collected = {
        mailbox: run_outlook_scan(namespace, mailbox, ["Inbox"], tmp_path)
        for mailbox in (INFO, HR)
    }
    text = write_overview(collected, tmp_path).read_text(encoding="utf-8")
    assert INFO in text and HR in text


def test_per_mailbox_files_do_not_collide(tmp_path):
    stores = [
        FakeStore(INFO, [FakeFolder("Inbox", [FakeItem(entry_id="1", sender="a@x.com")])]),
        FakeStore(HR, [FakeFolder("Inbox", [FakeItem(entry_id="2", sender="b@y.com")])]),
    ]
    namespace = FakeNamespace(stores)
    for mailbox in (INFO, HR):
        run_outlook_scan(namespace, mailbox, ["Inbox"], tmp_path)
    names = {p.name for p in tmp_path.glob("outlook-scan-*.jsonl")}
    assert names == {"outlook-scan-info_at_ubcsis_com.jsonl",
                     "outlook-scan-hr_at_ubcsis_com.jsonl"}
    rows = [json.loads(line) for line in
            (tmp_path / "outlook-scan-hr_at_ubcsis_com.jsonl").read_text().splitlines()]
    assert rows[0]["mailbox"] == HR
