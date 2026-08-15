"""A hostile mailbox must not stop the scan.

Reproduces the live failure: Outlook raised com_error 'No such
interface supported' on an item, hasattr propagated it (com_error is
not AttributeError), and a 10,000-item scan died at 500.
"""

import json
from datetime import datetime

from control.discovery.outlook_scan import run_outlook_scan, scan_folder
from control.outlook import is_mail_item, safe_get
from tests.test_outlook import FakeFolder, FakeItem, FakeNamespace, FakeStore

INFO = "info@ubcsis.com"


class ComError(Exception):
    """Stands in for pywintypes.com_error — NOT an AttributeError."""


class HostileItem:
    """Every property access explodes, the way an unsupported COM
    interface does."""

    def __getattr__(self, name):
        raise ComError("(-2147467262, 'No such interface supported')")


class PartiallyBrokenItem:
    """Readable sender, then explodes partway through — the nastiest
    case, because the item passes the is-mail check."""

    EntryID = "broken"
    SenderEmailAddress = "a@x.com"
    SenderEmailType = "SMTP"
    SenderName = ""
    Subject = "Looks fine"
    To = ""
    CC = ""
    ReceivedTime = datetime(2026, 5, 1, 9, 0)

    @property
    def Attachments(self):
        raise ComError("no such interface")


class ExplodingItems:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def Item(self, index):
        item = self._items[index - 1]
        if item == "RAISE_ON_FETCH":
            raise ComError("item cannot be materialised")
        return item


def test_safe_get_and_is_mail_item_swallow_com_errors():
    hostile = HostileItem()
    assert safe_get(hostile, "Subject", "fallback") == "fallback"
    assert is_mail_item(hostile) is False


def test_hostile_item_does_not_stop_the_scan():
    good = FakeItem(entry_id="1", sender="a@x.com", subject="Real",
                    received=datetime(2026, 5, 1, 9, 0))
    good2 = FakeItem(entry_id="2", sender="b@x.com", subject="Also real",
                     received=datetime(2026, 5, 2, 9, 0))
    folder = FakeFolder("Inbox")
    folder.Items = ExplodingItems([good, HostileItem(), good2])

    rows, summary = scan_folder(folder, mailbox=INFO, folder_name="Inbox")
    assert summary.total == 2                 # both good items survived
    assert summary.skipped_non_mail == 1      # hostile one counted, not fatal
    assert {r["subject"] for r in rows} == {"Real", "Also real"}


def test_unfetchable_item_is_counted_as_unreadable():
    good = FakeItem(entry_id="1", sender="a@x.com", received=datetime(2026, 5, 1, 9, 0))
    folder = FakeFolder("Inbox")
    folder.Items = ExplodingItems(["RAISE_ON_FETCH", good])

    _rows, summary = scan_folder(folder, mailbox=INFO, folder_name="Inbox")
    assert summary.total == 1
    assert summary.unreadable_items == 1


def test_item_failing_midway_is_counted_not_fatal():
    broken = PartiallyBrokenItem()
    good = FakeItem(entry_id="2", sender="b@x.com",
                    received=datetime(2026, 5, 2, 9, 0))
    folder = FakeFolder("Inbox")
    folder.Items = ExplodingItems([broken, good])

    rows, summary = scan_folder(folder, mailbox=INFO, folder_name="Inbox")
    # The item still yields usable metadata - partial data beats none.
    assert summary.total == 2
    # But the attachment gap is marked, never presented as "no attachments"
    assert summary.attachments_unreadable == 1
    broken_row = next(r for r in rows if r["sender"] == "a@x.com")
    assert broken_row["attachments_unreadable"] is True
    assert broken_row["attachments"] == []
    good_row = next(r for r in rows if r["sender"] == "b@x.com")
    assert "attachments_unreadable" not in good_row


def test_rows_are_on_disk_before_a_later_crash(tmp_path):
    """Streaming: work already done survives, rather than dying in memory."""
    items = [FakeItem(entry_id=str(i), sender=f"s{i}@x.com",
                      received=datetime(2026, 5, 1, 9, 0)) for i in range(5)]
    folder = FakeFolder("Inbox")
    folder.Items = ExplodingItems([*items, HostileItem()])
    store = FakeStore(INFO, [folder])

    summaries = run_outlook_scan(FakeNamespace([store]), INFO, ["Inbox"], tmp_path)
    written = (tmp_path / "outlook-scan-info_at_ubcsis_com.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(written) == 5
    assert json.loads(written[0])["sender"] == "s0@x.com"
    assert summaries[0].skipped_non_mail == 1


def test_unreadable_count_appears_in_the_report(tmp_path):
    folder = FakeFolder("Inbox")
    folder.Items = ExplodingItems(["RAISE_ON_FETCH",
                                   FakeItem(entry_id="1", sender="a@x.com")])
    store = FakeStore(INFO, [folder])
    run_outlook_scan(FakeNamespace([store]), INFO, ["Inbox"], tmp_path)
    report = (tmp_path / "OUTLOOK-SCAN-info_at_ubcsis_com.md").read_text(encoding="utf-8")
    assert "1 unreadable" in report
