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
                for item in getattr(folder.Items, "_items", []):
                    # Hostile/unfetchable items cannot be indexed - real
                    # Outlook profiles contain them too.
                    try:
                        self._by_id[item.EntryID] = item
                    except Exception:
                        continue

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


# ---- sending identity --------------------------------------------------
#
# Found live on 31-Aug-2026, on the first real send: the account guard
# raised correctly when no Outlook account matched control@ — and a
# `try/except: pass` swallowed the refusal and called Send() anyway, so
# Outlook sent under the profile's DEFAULT account, info@ubcsis.com. A
# statutory notice apparently from a person, replies going where Control
# cannot see them. No test had ever exercised a successful send, which
# is exactly how a swallowed guard survives.

class FakeAccount:
    def __init__(self, smtp):
        self.SmtpAddress = smtp


class FakeSession:
    def __init__(self, accounts):
        self.Accounts = accounts


class FakeMailItem:
    def __init__(self):
        self.To = ""
        self.CC = ""
        self.Subject = ""
        self.Body = ""
        self.SendUsingAccount = None
        self.sent = False

    def Send(self):
        self.sent = True


class StubbornMailItem(FakeMailItem):
    """Ignores the SendUsingAccount assignment — the real pywin32
    failure mode this guard exists for: the property set silently
    no-ops and the mail would go out as the profile default."""

    def __setattr__(self, name, value):
        if name == "SendUsingAccount" and value is not None:
            return
        super().__setattr__(name, value)


class FakeApplication:
    def __init__(self, accounts, item_factory=FakeMailItem):
        self.Session = FakeSession(accounts)
        self._factory = item_factory
        self.created = []

    def CreateItem(self, kind):
        item = self._factory()
        self.created.append(item)
        return item


def _sending_namespace(accounts, item_factory=FakeMailItem):
    inbox = FakeFolder("Inbox", [])
    return FakeNamespace([FakeStore(CONTROL, [inbox])],
                         application=FakeApplication(accounts, item_factory))


def test_send_goes_out_as_the_control_mailbox():
    namespace = _sending_namespace(
        [FakeAccount("info@ubcsis.com"), FakeAccount(CONTROL)])
    t = OutlookTransport(CONTROL, namespace=namespace, allow_send=True)

    message_id = t.send(["hr@ubcsis.com"], ["accounts@ubcsis.com"], "s", "b")

    mail = namespace.Application.created[0]
    assert mail.sent is True
    assert mail.SendUsingAccount.SmtpAddress == CONTROL
    assert CONTROL in message_id


def test_no_matching_account_refuses_and_names_what_the_profile_holds():
    """The refusal must reach the caller — nothing may swallow it and
    send as whoever the profile defaults to."""
    namespace = _sending_namespace([FakeAccount("info@ubcsis.com")])
    t = OutlookTransport(CONTROL, namespace=namespace, allow_send=True)

    with pytest.raises(HaltError) as e:
        t.send(["hr@ubcsis.com"], [], "s", "b")

    assert "info@ubcsis.com" in str(e.value)
    assert "Add Account" in str(e.value)
    assert namespace.Application.created == [], \
        "no mail item may even exist when the identity is refused"


def test_identity_check_passes_when_store_and_account_both_match():
    namespace = _sending_namespace([FakeAccount(CONTROL)])
    t = OutlookTransport(CONTROL, namespace=namespace)

    ok, lines = t.identity_check()

    assert ok is True
    assert any(line.startswith("store:   OK") for line in lines)
    assert any(line.startswith("account: OK") for line in lines)


def test_identity_check_reports_a_missing_account_without_sending():
    """The exact 31-Aug configuration: control@ present as a store,
    absent as an account — the shape that sent as info@."""
    namespace = _sending_namespace([FakeAccount("info@ubcsis.com")])
    t = OutlookTransport(CONTROL, namespace=namespace)

    ok, lines = t.identity_check()

    assert ok is False
    assert any(line.startswith("store:   OK") for line in lines)
    assert any("account: FAIL" in line and "info@ubcsis.com" in line
               for line in lines)
    assert namespace.Application.created == []


def test_a_pin_that_does_not_hold_refuses_rather_than_sending():
    """Setting SendUsingAccount can silently no-op. The send verifies
    the pin held and refuses when it did not — identity is verified,
    never assumed."""
    namespace = _sending_namespace(
        [FakeAccount(CONTROL)], item_factory=StubbornMailItem)
    t = OutlookTransport(CONTROL, namespace=namespace, allow_send=True)

    with pytest.raises(HaltError, match="profile default"):
        t.send(["hr@ubcsis.com"], [], "s", "b")

    assert namespace.Application.created[0].sent is False


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
