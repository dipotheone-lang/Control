"""Requested folders must match real ones, or say they didn't.

Three real runs reported 'sent items scanned: NO' with an unchanged
message count. Sent Items WAS requested — it is the default — but the
Gmail store nests sent mail under '[Gmail]/Sent Mail' and control@ has
no Sent Items folder at all. The scan matched nothing, said nothing,
and every thread was reported unanswered.
"""

from datetime import datetime

from control.discovery.outlook_scan import folder_matches, run_outlook_scan
from tests.test_outlook import FakeFolder, FakeItem, FakeNamespace, FakeStore

INFO = "info@ubcsis.com"


def test_exchange_and_gmail_sent_folders_both_match():
    assert folder_matches("Sent Items", "Sent Items", ["Sent Items"])
    assert folder_matches("Sent Mail", "[Gmail]/Sent Mail", ["Sent Items"])
    assert folder_matches("Sent", "Sent", ["Sent Items"])
    assert folder_matches("sent items", "sent items", ["Sent Items"])


def test_arabic_folder_names_match():
    assert folder_matches("العناصر المرسلة", "العناصر المرسلة", ["Sent Items"])
    assert folder_matches("البريد الوارد", "البريد الوارد", ["Inbox"])


def test_unrelated_folders_do_not_match():
    assert not folder_matches("Drafts", "Drafts", ["Sent Items"])
    assert not folder_matches("Outbox", "Outbox", ["Sent Items"])
    assert not folder_matches("Deleted Items", "Deleted Items", ["Inbox"])


def test_nested_gmail_sent_is_scanned(tmp_path):
    sent = FakeFolder("Sent Mail", [
        FakeItem(entry_id="1", sender=INFO, subject="RE: RFQ",
                 received=datetime(2026, 5, 1, 9, 0))])
    gmail = FakeFolder("[Gmail]")
    gmail.Folders = [sent]
    inbox = FakeFolder("Inbox", [
        FakeItem(entry_id="2", sender="client@x.com", subject="RFQ",
                 received=datetime(2026, 5, 1, 8, 0))])
    store = FakeStore(INFO, [inbox, gmail])

    summaries = run_outlook_scan(FakeNamespace([store]), INFO,
                                 ["Inbox", "Sent Items"], tmp_path, recurse=True)
    scanned = {s.folder for s in summaries if not s.not_found}
    assert "Inbox" in scanned
    assert "[Gmail]/Sent Mail" in scanned
    assert not any(s.not_found for s in summaries)


def test_missing_folder_is_reported_with_what_exists(tmp_path):
    store = FakeStore(INFO, [FakeFolder("Inbox", []), FakeFolder("Outbox", [])])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO,
                                 ["Inbox", "Sent Items"], tmp_path)

    missing = [s for s in summaries if s.not_found]
    assert len(missing) == 1
    assert "Sent Items" in missing[0].folder
    assert "NOT FOUND" in missing[0].folder
    # The operator must be able to see what to ask for instead
    assert "Inbox" in missing[0].available_folders
    assert "Outbox" in missing[0].available_folders


def test_present_folder_is_not_reported_missing(tmp_path):
    store = FakeStore(INFO, [
        FakeFolder("Inbox", []),
        FakeFolder("Sent Items", [FakeItem(entry_id="1", sender=INFO)]),
    ])
    summaries = run_outlook_scan(FakeNamespace([store]), INFO,
                                 ["Inbox", "Sent Items"], tmp_path)
    assert not any(s.not_found for s in summaries)
