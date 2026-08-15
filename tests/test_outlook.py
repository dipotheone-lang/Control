"""Outlook transport tests using a fake COM namespace.

The COM object model is duck-typed, so a faithful fake exercises every
branch of the transport on any platform.
"""

from datetime import datetime

import pytest

from control import HaltError
from control.outlook import OutlookTransport


class FakeAttachment:
    def __init__(self, name, payload):
        self.FileName = name
        self._payload = payload

    def SaveAsFile(self, path):
        with open(path, "wb") as f:
            f.write(self._payload)


class FakeAttachments:
    def __init__(self, attachments):
        self._items = attachments
        self.Count = len(attachments)

    def Item(self, index):
        return self._items[index - 1]


class FakeItem:
    def __init__(self, *, entry_id, sender, subject="", body="", to="", cc="",
                 received=None, attachments=None, internet_id=None,
                 sender_name="", sender_type="SMTP", smtp_property=None):
        self.EntryID = entry_id
        self.InternetMessageID = internet_id or ""
        self.SenderEmailAddress = sender
        self.SenderEmailType = sender_type
        self.SenderName = sender_name
        self.Subject = subject
        self.Body = body
        self.To = to
        self.CC = cc
        self.ReceivedTime = received or datetime(2026, 8, 13, 9, 0)
        self.Attachments = FakeAttachments(attachments or [])
        self.UnRead = True
        self.saved = False
        self._smtp_property = smtp_property

    @property
    def PropertyAccessor(self):
        item = self

        class Accessor:
            def GetProperty(self, _tag):
                if item._smtp_property is None:
                    raise RuntimeError("no such property")
                return item._smtp_property

        return Accessor()

    def Save(self):
        self.saved = True


class FakeItems:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def Restrict(self, _query):
        unread = [i for i in self._items if i.UnRead]
        return FakeItems(unread)

    def Item(self, index):
        return self._items[index - 1]


class FakeFolder:
    def __init__(self, name, items=None):
        self.Name = name
        self.Items = FakeItems(items or [])


class FakeStore:
    def __init__(self, address, folders):
        self.SmtpAddress = address
        self.Name = address
        self.Folders = folders


class FakeNamespace:
    def __init__(self, stores, application=None):
        self.Folders = stores
        self.Application = application
        self._by_id = {}
        for store in stores:
            for folder in store.Folders:
                for item in folder.Items._items:
                    self._by_id[item.EntryID] = item

    def GetItemFromID(self, entry_id):
        return self._by_id[entry_id]


CONTROL = "control@ubcsis.com"


def _namespace(items=None, address=CONTROL):
    inbox = FakeFolder("Inbox", items or [])
    return FakeNamespace([FakeStore(address, [inbox])])


def test_fetches_unread_with_metadata():
    item = FakeItem(
        entry_id="E1", internet_id="<m1@ubcsis.com>",
        sender="donia@ubcsis.com", sender_name="Donia Ali",
        subject="RFQ 114", body="\n\nPlease review.\nSecond line",
        to=CONTROL,
    )
    t = OutlookTransport(CONTROL, namespace=_namespace([item]))
    messages = t.fetch_unprocessed()
    assert len(messages) == 1
    m = messages[0]
    assert m.message_id == "<m1@ubcsis.com>"
    assert m.sender == "Donia Ali <donia@ubcsis.com>"
    assert m.subject == "RFQ 114"
    assert m.first_line == "Please review."      # blank lines skipped
    assert m.received_at == datetime(2026, 8, 13, 9, 0)


def test_read_items_are_skipped():
    read_item = FakeItem(entry_id="E2", sender="x@ubcsis.com")
    read_item.UnRead = False
    t = OutlookTransport(CONTROL, namespace=_namespace([read_item]))
    assert t.fetch_unprocessed() == []


def test_exchange_sender_resolved_to_smtp():
    item = FakeItem(
        entry_id="E3", sender="/O=UBCSIS/CN=RECIPIENTS/CN=HADEER",
        sender_type="EX", smtp_property="hadeer@ubcsis.com",
    )
    t = OutlookTransport(CONTROL, namespace=_namespace([item]))
    assert t.fetch_unprocessed()[0].sender == "hadeer@ubcsis.com"


def test_attachments_are_read():
    item = FakeItem(
        entry_id="E4", sender="a.elsayed@ubcsis.com",
        attachments=[FakeAttachment("FRM-WPR.xlsx", b"PK\x03\x04data")],
    )
    t = OutlookTransport(CONTROL, namespace=_namespace([item]))
    assert t.fetch_unprocessed()[0].attachments == [("FRM-WPR.xlsx", b"PK\x03\x04data")]


def test_wrong_mailbox_refuses_rather_than_falling_back():
    namespace = _namespace([], address="ahmed@ubcsis.com")
    t = OutlookTransport(CONTROL, namespace=namespace)
    with pytest.raises(HaltError, match="not in this Outlook profile"):
        t.fetch_unprocessed()


def test_missing_folder_halts():
    store = FakeStore(CONTROL, [FakeFolder("Sent Items")])
    t = OutlookTransport(CONTROL, namespace=FakeNamespace([store]))
    with pytest.raises(HaltError, match="no folder"):
        t.fetch_unprocessed()


def test_send_blocked_by_default():
    t = OutlookTransport(CONTROL, namespace=_namespace())
    with pytest.raises(HaltError, match="read-only"):
        t.send(["ahmed@ubcsis.com"], [], "s", "b")


def test_mark_processed_clears_unread():
    item = FakeItem(entry_id="E5", internet_id="<m5@x>", sender="d@ubcsis.com")
    namespace = _namespace([item])
    t = OutlookTransport(CONTROL, namespace=namespace)
    t.fetch_unprocessed()
    t.mark_processed("<m5@x>")
    assert item.UnRead is False and item.saved is True


def test_unknown_message_id_is_a_noop():
    t = OutlookTransport(CONTROL, namespace=_namespace())
    t.mark_processed("<never-seen@x>")      # must not raise
