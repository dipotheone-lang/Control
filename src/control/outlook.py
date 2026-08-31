"""Outlook desktop transport — local COM alternative to Microsoft Graph.

Implements the same MailTransport interface as GraphTransport, so the
engine is unchanged: only the transport handed to run_cycle() differs.

**Requires classic Outlook for Windows.** The "new Outlook" app has no
COM automation interface; File → Options in classic Outlook is the
quick way to tell them apart.

GOVERNANCE NOTE — read before using this beyond Phase 0 discovery.
The charter (§5.1) specifies Graph with certificate auth and a
*mandatory* Exchange Application Access Policy restricting the engine
to control@ubcsis.com alone. COM automation cannot reproduce that
control: it runs as the signed-in Windows user and can therefore reach
every mailbox in that Outlook profile. This is a WIDER permission
surface than the charter's design, not a narrower one, and it touches
§12.2 (PDPL data minimisation).

Two guards are implemented here rather than left to discipline:

- `expected_mailbox` — the store to read is resolved by address and the
  transport refuses to operate against a different one
- sending refuses unless the sending account's SMTP address matches
  `expected_mailbox`, so drafts can never leave under a person's own
  identity by accident

Using this path in Phase 2+ is a charter deviation and belongs in the
CEO decisions register (§17), not in a code comment.
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import HaltError
from .transport import FetchedMessage, MailTransport

# PidTagSmtpAddress — resolves an Exchange DN sender to a real address.
_PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"

OL_FOLDER_INBOX = 6


def safe_get(item, attribute: str, default=""):
    """Read a COM property without trusting the object model.

    hasattr() is not usable here: Outlook raises com_error ('No such
    interface supported') for items that are not mail — some IMAP and
    Gmail items, calendar artefacts, corrupt entries — and com_error is
    not an AttributeError, so hasattr propagates it instead of
    returning False.
    """
    try:
        value = getattr(item, attribute)
    except Exception:
        return default
    return default if value is None else value


def is_mail_item(item) -> bool:
    try:
        getattr(item, "SenderEmailAddress")
    except Exception:
        return False
    return True


def _dispatch_namespace():
    try:
        import win32com.client
    except ImportError as e:  # pragma: no cover - platform dependent
        raise HaltError(
            "pywin32 is required for the Outlook transport: "
            "python -m pip install pywin32 (Windows only)"
        ) from e
    try:
        application = win32com.client.Dispatch("Outlook.Application")
        return application.GetNamespace("MAPI")
    except Exception as e:  # pragma: no cover - platform dependent
        raise HaltError(
            f"cannot attach to Outlook via COM: {e}. Classic Outlook for "
            "Windows must be installed and running; the 'new Outlook' app "
            "does not expose COM."
        ) from e


def available_mailboxes(namespace=None) -> tuple[list[str], str]:
    """(mailboxes the local profile exposes, why it could not be asked).

    `doctor` reported the Outlook route as ready when `win32com.client`
    imported — which says a Python package is installed, not that Outlook
    is reachable, not that it is the classic build with a COM interface
    at all, and not that the mailbox Control is scoped to is in the
    profile. Those are three different failures with three different
    fixes, and all of them looked like "[ok] win32com.client".

    Metadata only: store addresses, never a message. Naming which
    mailboxes the profile exposes is the same class of fact as §12.1.2
    permits about a confidential document.
    """
    try:
        namespace = namespace if namespace is not None else _dispatch_namespace()
    except HaltError as e:
        return [], str(e)

    found: list[str] = []
    try:
        for store in namespace.Folders:
            for attribute in ("SmtpAddress", "Name", "DisplayName"):
                value = getattr(store, attribute, "") or ""
                if "@" in value:
                    found.append(value.lower())
                    break
            else:
                name = getattr(store, "Name", "")
                if name:
                    found.append(f"{name} (no SMTP address on the store)")
    except Exception as e:                      # noqa: BLE001
        return found, f"Outlook answered but the profile could not be read: {e}"
    return found, ""


@dataclass
class _Resolved:
    folder: object
    store_address: str


class OutlookTransport(MailTransport):
    """Reads and sends through the local Outlook profile.

    namespace is injectable so the logic is testable without COM.
    """

    def __init__(self, expected_mailbox: str, *, namespace=None,
                 folder_name: str = "Inbox", allow_send: bool = False):
        self.expected_mailbox = expected_mailbox.lower()
        self.folder_name = folder_name
        self.allow_send = allow_send
        self.namespace = namespace if namespace is not None else _dispatch_namespace()
        self._entry_ids: dict[str, str] = {}
        self._resolved: _Resolved | None = None

    # -- store resolution ---------------------------------------------------

    def _smtp_of_store(self, store) -> str:
        for attr in ("SmtpAddress", "Name", "DisplayName"):
            value = getattr(store, attr, "") or ""
            if "@" in value:
                return value.lower()
        return ""

    def _resolve(self) -> _Resolved:
        """Find the folder belonging to expected_mailbox. Refuses to fall
        back to 'whatever the default store is' — reading the wrong
        mailbox silently is exactly the failure this guard exists for."""
        if self._resolved is not None:
            return self._resolved

        candidates = []
        for store in self.namespace.Folders:
            address = self._smtp_of_store(store)
            candidates.append(address or getattr(store, "Name", "?"))
            if address != self.expected_mailbox:
                continue
            folder = None
            for child in store.Folders:
                if str(getattr(child, "Name", "")).lower() == self.folder_name.lower():
                    folder = child
                    break
            if folder is None:
                raise HaltError(
                    f"mailbox {self.expected_mailbox} has no folder "
                    f"{self.folder_name!r}"
                )
            self._resolved = _Resolved(folder=folder, store_address=address)
            return self._resolved

        raise HaltError(
            f"mailbox {self.expected_mailbox} is not in this Outlook profile. "
            f"Accounts found: {', '.join(str(c) for c in candidates) or 'none'}. "
            "Add the mailbox to Outlook (File - Account Settings), or pass the "
            "address that this profile actually holds."
        )

    # -- reading ------------------------------------------------------------

    @staticmethod
    def _sender_address(item) -> str:
        """Exchange senders carry a DN, not an address; resolve to SMTP."""
        if str(getattr(item, "SenderEmailType", "") or "").upper() == "EX":
            try:
                accessor = item.PropertyAccessor
                address = accessor.GetProperty(_PR_SMTP_ADDRESS)
                if address:
                    return str(address)
            except Exception:
                pass
            try:
                user = item.Sender.GetExchangeUser()
                if user and user.PrimarySmtpAddress:
                    return str(user.PrimarySmtpAddress)
            except Exception:
                pass
        return str(getattr(item, "SenderEmailAddress", "") or "")

    @staticmethod
    def _first_line(item) -> str:
        body = str(getattr(item, "Body", "") or "")
        for line in body.splitlines():
            if line.strip():
                return line.strip()
        return ""

    @staticmethod
    def _received_at(item) -> datetime:
        value = getattr(item, "ReceivedTime", None)
        if isinstance(value, datetime):
            return value
        try:  # pywin32 returns a COM time object
            return datetime.fromtimestamp(float(value))
        except Exception:
            return datetime.now()

    def _attachments(self, item) -> list[tuple[str, bytes]]:
        collected: list[tuple[str, bytes]] = []
        attachments = getattr(item, "Attachments", None)
        if attachments is None:
            return collected
        count = int(getattr(attachments, "Count", 0) or 0)
        if not count:
            return collected
        with tempfile.TemporaryDirectory(prefix="control-att-") as tmp:
            for index in range(1, count + 1):
                attachment = attachments.Item(index)
                name = str(getattr(attachment, "FileName", "") or f"attachment-{index}")
                # Path is taken from the attachment name only; join to the
                # isolated temp directory and never to a caller-supplied path.
                target = Path(tmp) / os.path.basename(name)
                try:
                    attachment.SaveAsFile(str(target))
                    collected.append((name, target.read_bytes()))
                except Exception:
                    # An unreadable attachment is a recorded fact, not a
                    # crash; evaluation will treat it as missing content.
                    continue
        return collected

    def fetch_unprocessed(self) -> list[FetchedMessage]:
        resolved = self._resolve()
        items = resolved.folder.Items
        try:
            unread = items.Restrict("[Unread]=true")
        except Exception:
            unread = items

        messages: list[FetchedMessage] = []
        count = int(getattr(unread, "Count", 0) or 0)
        for index in range(1, count + 1):
            item = unread.Item(index)
            # Non-mail items (meeting requests, reports) have no sender.
            if not hasattr(item, "SenderEmailAddress"):
                continue
            entry_id = str(getattr(item, "EntryID", "") or f"idx-{index}")
            message_id = str(
                getattr(item, "InternetMessageID", "") or entry_id
            )
            sender = self._sender_address(item)
            display = str(getattr(item, "SenderName", "") or "")
            messages.append(FetchedMessage(
                message_id=message_id,
                sender=f"{display} <{sender}>" if display else sender,
                received_at=self._received_at(item),
                to=str(getattr(item, "To", "") or ""),
                cc=str(getattr(item, "CC", "") or ""),
                subject=str(getattr(item, "Subject", "") or ""),
                first_line=self._first_line(item),
                attachments=self._attachments(item),
                in_reply_to_control=bool(
                    self.expected_mailbox in str(getattr(item, "To", "") or "").lower()
                    and str(getattr(item, "Subject", "") or "").upper().startswith("RE:")
                ),
                # Outlook exposes the conversation directly. Older items
                # and some non-Exchange stores leave it empty, so it is
                # read defensively and the watchdog falls back rather
                # than failing the sweep.
                thread_id=str(getattr(item, "ConversationID", "") or ""),
            ))
            self._entry_ids[message_id] = entry_id
        return messages

    # -- writing ------------------------------------------------------------

    def send(self, recipients: list[str], cc: list[str], subject: str,
             body: str) -> str:
        if not self.allow_send:
            raise HaltError(
                "OutlookTransport is read-only unless allow_send=True. "
                "Phase 0 sends nothing (§6); enable sending only after the "
                "§16 phase gates have been passed."
            )
        resolved = self._resolve()
        if resolved.store_address != self.expected_mailbox:
            raise HaltError(
                f"refusing to send: resolved store {resolved.store_address!r} "
                f"is not {self.expected_mailbox!r}"
            )
        application = self.namespace.Application
        # Identity first, and nothing may swallow it. An earlier version
        # wrapped this in `try/except: pass` and then called Send()
        # anyway — so when no account matched control@, Outlook sent
        # under the profile's DEFAULT account, and on the operating
        # machine that is info@ubcsis.com: a statutory notice apparently
        # from a person, with replies going where Control cannot see
        # them. Found live on 31-Aug-2026, on the first real send.
        account = self._account_for(application)
        mail = application.CreateItem(0)      # olMailItem
        mail.To = "; ".join(recipients)
        mail.CC = "; ".join(cc)
        mail.Subject = subject
        mail.Body = body
        self._pin_account(mail, account)
        pinned = self._pinned_address(mail)
        if pinned != self.expected_mailbox:
            raise HaltError(
                "refusing to send: Outlook would send as "
                f"{pinned or 'the profile default account'!r}, not "
                f"{self.expected_mailbox!r}. The message identity is part "
                "of the message — it is verified, never assumed."
            )
        mail.Send()
        return f"<outlook-{datetime.now():%Y%m%d%H%M%S%f}@{self.expected_mailbox}>"

    @staticmethod
    def _pin_account(mail, account) -> None:
        """Set SendUsingAccount by both known routes. The plain
        assignment silently no-ops on some pywin32/Outlook builds, which
        is why the COM Invoke (dispid 64209) follows it; either may
        fail, because `_pinned_address` verifies the result and `send`
        refuses when it did not hold."""
        try:
            mail.SendUsingAccount = account
        except Exception:
            pass
        try:
            mail._oleobj_.Invoke(64209, 0, 8, 0, account)  # noqa: SLF001
        except Exception:
            pass

    def _pinned_address(self, mail) -> str:
        try:
            account = mail.SendUsingAccount
        except Exception:
            return ""
        return str(getattr(account, "SmtpAddress", "") or "").lower()

    def identity_check(self) -> tuple[bool, list[str]]:
        """Verify the sending identity without creating or sending
        anything: the store (for reading, where the scope permits it)
        and the account (for sending — the thing that failed live on
        31-Aug-2026). Profile metadata only; no message is touched."""
        ok, lines = True, []
        try:
            resolved = self._resolve()
            lines.append(f"store:   OK — {resolved.store_address} "
                         f"(folder {self.folder_name!r} present)")
        except HaltError as e:
            ok = False
            lines.append(f"store:   FAIL — {e}")
        try:
            account = self._account_for(self.namespace.Application)
            lines.append("account: OK — sends as "
                         f"{str(getattr(account, 'SmtpAddress', '?')).lower()}")
        except HaltError as e:
            ok = False
            lines.append(f"account: FAIL — {e}")
        return ok, lines

    def _account_for(self, application):
        candidates = []
        for account in application.Session.Accounts:
            address = str(getattr(account, "SmtpAddress", "")).lower()
            candidates.append(address or "?")
            if address == self.expected_mailbox:
                return account
        raise HaltError(
            f"no Outlook account matches {self.expected_mailbox} — the "
            f"profile's accounts are: {', '.join(candidates) or 'none'}. "
            "Refusing to send under a different identity: add "
            f"{self.expected_mailbox} as an account in Outlook "
            "(File - Add Account), not only as a shared folder."
        )

    def mark_processed(self, message_id: str) -> None:
        entry_id = self._entry_ids.get(message_id)
        if not entry_id:
            return
        try:
            item = self.namespace.GetItemFromID(entry_id)
        except Exception:
            return
        item.UnRead = False
        item.Save()
